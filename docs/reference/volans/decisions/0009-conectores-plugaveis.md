# ADR 0009 — Arquitetura de conectores plugáveis

**Status:** Aceita

## Contexto

A regra de portabilidade exige que nada essencial dependa de serviço fechado, e o
mesmo código roda em três lugares (dev local, Docker, borda Azion) com backings
diferentes. Precisamos trocar backing sem tocar na lógica.

## Decisão

Todo recurso externo é um **conector plugável**: uma **interface** (contrato),
uma ou mais **implementações** (adapters), escolhida por **variável de ambiente**,
injetada nos handlers via `HandlerDeps`. Os handlers dependem só das interfaces.

- Contratos: `lib/{kv,storage,imaging}.ts`, `services/emailService.ts`.
- Adapters: `lib/adapters/*.ts` (Node/infra) e `apps/api-edge/*` (borda).
- Seleção: `select*()` em `deps.ts` (Node) e a montagem em `edgeDeps.ts` (borda).

**Regra dos dois runtimes**: adapters usados pela borda só podem usar APIs
web-standard (`fetch`/WebCrypto) — sem `node:*` nem socket TCP. Por isso a seleção
é separada: `deps.ts` importa todos; `edgeDeps.ts` só os edge-safe.

## Consequências

- Trocar backing (banco, KV, e-mail, storage, imagem) é **configuração, não
  código**. Adicionar um adapter novo é um arquivo + um `case` + a env.
- Guia completo e catálogo: [../architecture/connectors.md](../architecture/connectors.md).
- Conectores: banco (Drizzle), KV, e-mail, object storage, image processor, hash
  de senha, env/segredos.
