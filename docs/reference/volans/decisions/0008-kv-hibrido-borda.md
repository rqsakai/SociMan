# ADR 0008 — KV híbrido na borda (Edge SQL hoje, AzionKV nativo pronto)

**Status:** Aceita (bloqueada no provisionamento do Edge KV pela Azion)

## Contexto

Rate-limit e sessão são o **hot path** (a cada request). O lugar certo é um KV
**in-process** (µs), não escrita SQL (um dos 4 limites de custo, e ~1,9s/op via
REST — ver [0007](0007-driver-rest-edge-sql.md)). A Azion tem KV Store nativo
(`Azion.KV`, compatível com Workers KV).

## Decisão

- A interface `KV` (`get/set/delete/incr` com TTL) é o contrato; os handlers e o
  tokenService não sabem o backing.
- **Alvo**: adapter `AzionKV` (nativo, in-process) para rate-limit e sessão.
- **Hoje**: `SqliteKV` sobre o Edge SQL (a tabela `kv_store`), porque o **Edge KV
  não está provisionado** para o runtime da conta — `Azion.KV.open("volans-poc")`
  retorna *"namespace does not exist"* mesmo com o namespace criado, e o CLI
  (4.22.2) não tem comando de KV.

## Consequências

- **Bloqueio na Azion**: precisa habilitar/provisionar o Edge KV (pedido no
  chamado de suporte — ver [../../PRODUCTION.md](../../PRODUCTION.md)).
- Pronto do nosso lado: `AzionKV` escrito (`apps/api-edge/src/azionKv.ts`),
  namespace criado, canário testando `open/put/get/consistência`. Quando
  habilitar, é trocar `sessionKv`/`rateLimitKv` em `edgeDeps.ts` → login/refresh
  em ~ms.
- Mitigações de latência já aplicadas no SQL: `incr` com `RETURNING` (1
  round-trip) e rate-limit por IP/conta em paralelo (`Promise.all`) — login caiu
  de ~8s para ~3,5s.
- Otimização atômica do `incr` no KV nativo tem race benigna (só superconta —
  direção segura para rate-limit).
