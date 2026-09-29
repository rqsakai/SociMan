# Arquitetura — Como roda na borda Azion

A borda (isolate V8, não Node completo) roda os **mesmos handlers** do
`apps/api` através de um entry de edge function. O que muda é o injetor de
dependências e os adapters (só web-standard).

## A Edge Function

`apps/api-edge/src/index.ts` — entry no formato **service-worker**:

```js
addEventListener("fetch", (event) => event.respondWith(route(event.request, event.args)));
```

- Bundle **ESM** via esbuild (`format: "esm"`) — `iife` quebraria o `import` do
  módulo `azion:sql`. `external: ["azion:sql"]` (o runtime fornece).
- Roteia `/api/*` para os handlers importados de `apps/api` — **nenhuma mudança
  neles**. O Next fica fora do isolate.
- Roteia pelo **sufixo** `/api/*` (imune ao rewrite que a Rules Engine faça no path).
- Aplica os headers de segurança da API e a exceção de cache do `/api/config`.
- `/api/_canary` — endpoint de diagnóstico que exercita WASM/jose/SQL/KV no isolate.

## Conectores na borda

- **Banco**: `apps/api-edge/src/edgeDb.ts` — driver Drizzle `sqlite-proxy` que
  fala o **REST do Edge SQL** (`api.azion.com/v4/edge_sql/databases/{id}/query`).
  Ver a ressalva de latência abaixo.
- **KV**: híbrido em `edgeDeps.ts` — `SqliteKV` sobre o Edge SQL para sessão e
  rate-limit (hoje). Adapter `AzionKV` (nativo, in-process) pronto, aguardando o
  Edge KV ser habilitado.
- **E-mail**: `resendEmail` (fetch, BYOK). Ver [`../config/email.md`](../config/email.md).
- **Env/segredos**: `Azion.env.get()` (Variables) — `process.env` é congelado.

## O edge na frente (Rules Engine)

O deploy (`infra/azion/main.tf`) configura, via Rules Engine:
- `/api/*` → **run_function** + **`forward_cookies`** (sem isso o edge **remove o
  Set-Cookie** da resposta — o cookie de refresh nunca chegaria ao browser).
- `/*` sem extensão → SPA fallback (rewrite p/ index.html no bucket).
- `/*` com extensão → assets direto do **Edge Storage** (bucket com o build da SPA).
- Regra de response → **CSP estrita** + HSTS + XCTO + Referrer na SPA.
- **Workload** com domínio custom + **TLS Let's Encrypt** (HTTP-01, pedido via API).

## ⚠️ Ressalva 1 — Edge KV nativo desabilitado

O KV nativo (`Azion.KV`, in-process) **não está provisionado** para o runtime da
conta: `Azion.KV.open("volans-poc")` retorna *"namespace does not exist"* mesmo
com o namespace criado via API, e o CLI (4.22.2) não tem comando de KV. Por isso
sessão e rate-limit rodam sobre o Edge SQL (lento — ver ressalva 2).

- **Pronto do nosso lado**: adapter `AzionKV`, namespace criado, canário testando
  `open/put/get/consistência`. Quando a Azion habilitar, é trocar
  `sessionKv`/`rateLimitKv` em `edgeDeps.ts` → login/refresh em ~ms.

## ⚠️ Ressalva 2 — Latência do Edge SQL via REST (~1,9s/query)

A escrita no Edge SQL a partir da borda vai pela **API REST de gestão**
(control-plane), não por um caminho de dados in-process. Medições:

| Fase | Tempo |
|---|---|
| Execução da query no banco (`query_duration_ms`) | **0,067 ms** |
| Conexão (DNS+TCP+TLS) | ~36 ms |
| **Servidor REST processando (TTFB)** | **~1,9 s** |
| **5 queries numa chamada** | **~1,6 s** (= 1 query) |

O banco é instantâneo; o custo é 100% overhead de round-trip do `api.azion.com`
(5 queries custam o mesmo que 1 → é por-requisição, não por-query). Impacto:
login ~3,5s, register ~11s — enquanto a lógica de auth em si é ~40ms.

## Descobertas do runtime (via `/api/_canary`)

| Teste | Resultado |
|---|---|
| Argon2id-WASM (`hash-wasm`) | ✅ funciona no isolate |
| `jose` HS256 (sign+verify) | ✅ funciona |
| PBKDF2-SHA256 (WebCrypto) | ✅ funciona |
| `azion:sql` leitura (`query`) | ✅ funciona (in-process) |
| `azion:sql` escrita (`execute`) | ❌ `attempt to write a readonly database` (réplica read-only) |
| `azion:sql` bind de string | ❌ `unknown variant 'String', expected 'Text'` (bug de serialização) |
| `process.env` gravável | ❌ congelado — `getEnv(source)` recebe os args |
| `Set-Cookie` sem `forward_cookies` | ❌ removido pelo edge |

Consequência: escrita → REST (lento, mas funciona); parâmetros → inlinados com
escaping seguro (`lib/sqlInline.ts`); env → injetado dos args; cookie →
`forward_cookies` na regra `/api/*`.

## Correções pontuais aprendidas no deploy

- `application_accelerator = true` é obrigatório junto com `functions` (10069).
- Módulo do Next 16 tem lock em `.next/dev` → `NEXT_DIST_DIR=.next-docker` no
  container (repo é bind-mount).
- `sqlite-proxy` "get" sem linha deve retornar `{rows: undefined}`, não `[]`
  (senão `findFirst` acha um usuário-fantasma).
