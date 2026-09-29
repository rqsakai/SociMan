# Arquitetura — Modelo de dados

Duas camadas: **SQL relacional** (Drizzle sobre Edge SQL/libSQL) para dado
durável, e **KV** (chave→valor com TTL) para sessão e rate-limit. Schema em
`apps/api/src/db/schema.ts`; migrations em `apps/api/drizzle/` (expand/contract,
nunca `push`).

## Tabelas SQL

### `users`
| Coluna | Tipo | Nota |
|---|---|---|
| `id` | text PK | uuid (`crypto.randomUUID()`) |
| `name` | text? | opcional |
| `email` | text unique | lowercase/trim (normalizado no Zod) |
| `password_hash` | text | PHC string (Argon2id ou PBKDF2) |
| `email_verified` | boolean | default `false` |
| `created_at` / `updated_at` | timestamp_ms | |

### `password_reset_tokens` / `email_verification_tokens`
Tokens single-use enviados por e-mail, guardados **só como SHA-256** do token
(nunca em claro).
| Coluna | Nota |
|---|---|
| `token_hash` | text PK — SHA-256 do token de 256-bit |
| `user_id` | FK → users (cascade) |
| `expires_at` | timestamp_ms — TTL curto |
| `used_at` | (só reset) nullable — marca consumo single-use |

Índice por `user_id` em ambas.

### `consent_records` (auditoria LGPD)
| Coluna | Nota |
|---|---|
| `id` | uuid PK |
| `user_id` | FK nullable (set null) — nulo para anônimo |
| `anon_id` | identifica visitante anônimo |
| `categories` | JSON (`{ essential, analytics }`) |
| `policy_version` | versão da política aceita |
| `ip` / `user_agent` | do request |
| `created_at` | timestamp_ms |

### `kv_store`
Backing do KV em dev/borda-sem-KV-nativo (SQLite/Edge SQL). Em produção o adapter
troca para o Edge KV mantendo a **mesma interface** (`lib/kv.ts`).
| Coluna | Nota |
|---|---|
| `key` | text PK |
| `value` | text (JSON) |
| `expires_at` | timestamp_ms nullable — expiração lazy no `get` |

## A interface KV

`lib/kv.ts` — o contrato que sessão e rate-limit usam (independe do backing):
```ts
get<T>(key): Promise<T | null>
set(key, value, { ttlSeconds? }): Promise<void>
delete(key): Promise<void>
incr(key, { ttlSeconds }): Promise<number>   // atômico, reinicia por janela
```
Adapters: `SqliteKV` (sobre o Db), `redisKv` (Redis), `AzionKV` (nativo, borda).

## Design das chaves do KV

| Chave | Valor | Uso |
|---|---|---|
| `rt:{familyId}` | `{ userId, tokenHash, prevTokenHash, prevExpiresAt, expiresAt }` | **família de refresh** — o token corrente (SHA-256) + o anterior (janela de graça 60s) |
| `uf:{userId}` | `string[]` (familyIds) | índice das famílias do usuário — usado para **revogar todas** as sessões (reset de senha) |
| `rl:{ação}:ip:{bucket}:{ip}` | contador | rate-limit por IP (fixed-window; `bucket = floor(now/janela)`) |
| `rl:{ação}:acct:{bucket}:{conta}` | contador | rate-limit por conta |

### Refresh families e revogação
- Uma **família** = uma sessão (um login). `createSession` gera `familyId` (uuid)
  e o primeiro refresh; grava `rt:{familyId}` e adiciona ao índice `uf:{userId}`.
- **Rotação** (`rotateRefresh`): valida o hash apresentado contra `tokenHash`
  (ou `prevTokenHash` dentro da graça), grava o novo, guarda o anterior. Expiração
  **absoluta** (não estende).
- **Reuso**: hash desconhecido com família viva → `delete rt:{familyId}` (revoga
  a família) → re-login.
- **`revokeFamily(familyId)`**: apaga `rt:{familyId}` e tira do índice.
- **`revokeAllForUser(userId)`**: apaga todas as `rt:*` do índice `uf:{userId}` —
  usado no reset de senha.
- A race no `uf:{userId}` (read-modify-write) é benigna: o pior caso é um id
  obsoleto a mais na lista, nunca uma revogação esquecida.
