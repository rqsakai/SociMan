# Modelo de dados: 001-auth

Os dados permanentes ficam no PostgreSQL (migration Alembic `0001_auth`). O estado efêmero fica no
Redis (constitution 1.1.0: o Redis não é banco de registro).

## PostgreSQL

### `users`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | gerado pela aplicação (uuid4) |
| `name` | text not null | 1..120 caracteres, sem espaço nas pontas |
| `email` | text not null | normalizado (trim + minúsculas); `UNIQUE` |
| `password_hash` | text not null | PHC Argon2id; nunca sai da API nem vai para o log |
| `role` | enum `user_role` (`dono`, `membro`) not null | |
| `is_active` | bool not null default true | a desativação substitui o delete (FR-018) |
| `email_verified_at` | timestamptz null | null = não verificado; bloqueia o login (FR-020) |
| `must_change_password` | bool not null default false | true na criação pelo dono e na senha provisória |
| `password_changed_at` | timestamptz not null | |
| `created_at`, `updated_at` | timestamptz not null | |
| `created_by`, `updated_by` | uuid null FK → users.id | null = rotina de instalação (`system:cli`) |

**Invariantes (validadas no serviço, dentro de transação com `SELECT … FOR UPDATE`):**
- existe pelo menos um usuário com `role = dono` e `is_active = true` (FR-013);
- nenhuma linha é apagada; só existe `UPDATE`.

**Estados:**
```
criado pelo dono ──(verifica e-mail)──▶ verificado + troca pendente ──(troca senha)──▶ ativo normal
      ▲                                                                                     │
      └──(dono troca o e-mail: email_verified_at = null, sessões revogadas)─────────────────┤
ativo normal ──(dono define senha provisória)──▶ troca pendente (sessões revogadas)          │
qualquer estado ──(dono desativa)──▶ inativo (sessões revogadas) ──(dono reativa)──▶ estado anterior
```
O dono criado pela CLI nasce `verificado` e com `must_change_password = false`.

### `one_time_tokens`
| Coluna | Tipo | Regras |
|---|---|---|
| `token_hash` | text PK | sha256 hex do token bruto (32 bytes base64url) |
| `user_id` | uuid FK → users.id not null | |
| `purpose` | enum `token_purpose` (`verify_email`, `reset_password`) | |
| `email` | text not null | o e-mail que o token verifica; se o e-mail mudar depois, o token perde a validade |
| `expires_at` | timestamptz not null | verify: +24 h; reset: +15 min |
| `used_at` | timestamptz null | uso único: é marcado dentro da transação que consome o token |
| `created_at` | timestamptz not null | |

Índice: `(user_id, purpose)`. Um token novo do mesmo propósito invalida os anteriores ainda não usados
(marca `used_at`).

### `security_events`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `occurred_at` | timestamptz not null default now() | índice desc |
| `type` | text not null | um de: `login_succeeded`, `login_failed`, `logout`, `refresh_reuse_detected`, `refresh_concorrente` (informativo: token anterior dentro da carência, spec de correção 2026-10-06), `password_reset_requested`, `password_reset_completed`, `password_changed`, `password_set_by_owner`, `email_verification_sent`, `email_verified`, `user_created`, `user_updated`, `role_changed`, `email_changed`, `user_deactivated`, `user_reactivated` |
| `outcome` | text not null | `ok` ou `denied` |
| `actor_user_id` | uuid null FK | quem agiu (null = anônimo ou CLI) |
| `actor_kind` | text not null | `user`, `anonymous` ou `system:cli` (`mcp_client` fica reservado para a 009) |
| `subject_user_id` | uuid null FK | o usuário afetado |
| `ip` | inet null | |
| `user_agent` | text null | truncado em 300 caracteres |
| `details` | jsonb not null default '{}' | ex.: `{"before": {...}, "after": {...}}`; nunca senha, token nem hash |

Imutável: a aplicação só faz `INSERT`. Índices: `(occurred_at desc)`, `(subject_user_id, occurred_at desc)`,
`(type, occurred_at desc)`.

### `AuditMixin` (para as próximas specs)
Colunas `created_at`, `created_by`, `updated_at` e `updated_by` preenchidas a partir do `Actor` da
requisição (FR-016). Na 001, só `users` usa o mixin.

## Redis (efêmero, AOF ligado)
| Chave | Valor | TTL |
|---|---|---|
| `rt:{fam}` | hash `{userId, tokenHash, prevTokenHash, prevExpiresAt, expiresAt}` | tempo restante absoluto da família (7 dias desde o login) |
| `uf:{userId}` | SET de `fam` | 7 dias, renovado a cada login |
| `rl:{ação}:ip:{bucket}:{ip}` / `rl:{ação}:acct:{bucket}:{email}` | contador | a janela da ação |

**Revogar todas as sessões de um usuário:** `SMEMBERS uf:{id}`, depois `DEL rt:{fam}…` e `DEL uf:{id}`.
Isso acontece na troca de senha (exceto na sessão atual, FR-015), na senha provisória, na troca de
e-mail, na desativação e no reset.
