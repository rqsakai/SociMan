# ADR 0007 — Driver REST do Edge SQL na borda + inlining seguro de params

**Status:** Aceita (com ressalva de performance — depende da Azion)

## Contexto

O Edge SQL da Azion é baseado em libSQL, com réplicas de leitura na borda. O
binding nativo `azion:sql` foi testado no isolate (via `/api/_canary`) e revelou:

- **Escrita bloqueada**: `INSERT/UPDATE` retorna *"attempt to write a readonly
  database"* (réplica de borda read-only; write-forwarding não configurado).
- **Bind de string quebrado**: parâmetro string → *"unknown variant `String`,
  expected `Text`"*.
- **Leitura funciona** in-process (rápida).

Docs confirmam: não há caminho documentado de escrita nativa; escrita vai ao
primário via REST/`useExecute` (control-plane).

## Decisão

Na borda, usar um **driver Drizzle sobre o REST do Edge SQL**
(`api.azion.com/v4/edge_sql/.../query`, formato service-worker ESM), com
**parâmetros inlinados** com escaping rigoroso (`sqlInline.ts`) porque o bind
nativo está quebrado. Os valores já passaram por Zod; o inlining é defesa em
profundidade, com testes (aspas dobradas, payloads inertes, tipos rejeitados).

## Consequências

- **Ressalva de performance**: cada query REST custa **~1,9s** de TTFB do
  control-plane, embora o banco execute em **0,067ms**. Login ~3,5s, register
  ~11s. Não é o banco nem o código — é a escolha forçada de driver. Evidência e
  medições em [../../PRODUCTION.md](../../PRODUCTION.md).
- Descobertas do driver: (a) entry precisa ser ESM (iife quebra o import
  `azion:sql`); (b) `sqlite-proxy` "get" sem linha deve retornar `undefined`, não
  `[]` (senão `findFirst` acha fantasma); (c) `Set-Cookie` é removido sem o
  behavior `forward_cookies` na regra.
- Resolve com Edge KV nativo (ver [0008](0008-kv-hibrido-borda.md)) + leitura
  nativa `azion:sql`. Depende da Azion.
- Implementação: `apps/api-edge/src/edgeDb.ts`, `apps/api/src/lib/sqlInline.ts`.
