# ADR 0010 — Monorepo (npm workspaces) + handlers puros

**Status:** Aceita

## Contexto

O starter tem frontend (SPA), backend (REST) e um contrato compartilhado, e o
backend precisa rodar em Node (dev), Docker e no isolate da borda Azion — sem
reescrever a lógica para cada runtime.

## Decisão

- **Monorepo com npm workspaces** (npm já presente; pnpm seria fricção sem
  ganho): `apps/web` (React+Vite), `apps/api` (Next route handlers = REST),
  `apps/api-edge` (bundle da edge function), `packages/contract` (Zod + client +
  OpenAPI).
- **Handlers puros**: cada endpoint é uma função `(Request, deps) => Response`,
  sem Next internals. O `route.ts` do Next é um wrapper de 1 linha; a edge
  function roteia as mesmas funções. Assim o **mesmo código** roda em Node,
  Docker e borda.
- Injeção de dependências via `HandlerDeps` (ver [0009](0009-conectores-plugaveis.md)).

## Consequências

- Testabilidade: os handlers são testados como funções puras (Request→Response)
  com DB `:memory:`, sem subir o Next.
- Portabilidade comprovada: o mesmo boilerplate roda em dev, na topologia Docker
  (que espelha a Azion) e na borda real — validado ponta a ponta.
- O Next fica de fora do isolate (a borda usa o bundle `apps/api-edge`).
- Estrutura e runtimes: [../architecture/overview.md](../architecture/overview.md).
