# CLAUDE.md: SociMan

Gestão de contas de mídia social da agência: contas, kit de marca, avatares e poses, cenas, scripts, canais-fonte, vídeos e padrões de corte. A IA acessa tudo por MCP. Docs em pt-BR.

## Como trabalhar (o dono)
- **Um passo por vez:** mostre o comando, explique em uma linha, rode, leia a saída e só então siga.
- **Spec Driven Development com o GitHub Spec Kit:** `/speckit-constitution`, depois `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks` e `/speckit-implement`. **Nada de código de feature sem spec aprovada.** As specs ficam em `specs/NNN-nome/`.
- A visão e o backlog de specs estão em `docs/visao.md`. A constitution está em `.specify/memory/constitution.md`.
- Commit e push só quando o dono pedir. Mensagens em pt-BR, no imperativo.

## Stack
```
apps/web            SPA React 19 + Vite + Tailwind 4 (copiado do volans; auth UI pronta)
packages/contract   Zod + client tipado (herdado do volans; será gerado do OpenAPI do FastAPI)
apps/api            FastAPI (Python 3.12, uv), SQLAlchemy 2 + Alembic, PostgreSQL
docker/nginx        edge: /api → api:3001, /img → imgproxy, / → SPA; headers e CSP
reference/volans-api  API TypeScript original do volans (SÓ referência para portar a auth; não roda)
docs/reference/volans arquitetura, ADRs e produto do volans (referência)
.specify/ .claude/skills  Spec Kit
```

## Comandos
```bash
docker compose up -d                        # stack: http://localhost:8180  https://localhost:8543
curl http://localhost:8180/api/health       # {"status":"ok","db":"ok"}
cd apps/api && uv run pytest && uv run ruff check .   # API
npm run check:web                           # typecheck + build + check:bundle/csp/secrets
```
Portas: edge 8180/8543, console do MinIO 9101 (minioadmin/minioadmin, **só dev**). Postgres, API e imgproxy ficam só na rede interna. **Não use** 8000/5175 (OpenShorts) nem 18789 (OpenClaw).

## Armadilhas
1. **Containers rodam como UID 1000.** Se uma pasta de bind mount não existir, o Docker a cria como root (foi o que aconteceu com `docker/certs`). Crie antes.
2. **CSP estrita em produção** (herdada do volans). `check:csp` compara `apps/web/vite.config.ts` com `docker/nginx/05-edge-mode.envsh`. Mudou um, mude o outro.
3. **A API confia em `X-Forwarded-*`** (`--forwarded-allow-ips='*'`) porque só o edge a alcança. Nunca publique a porta da API.
4. **Não mate processos por nome** (`pkill -f vite` mata processos dentro dos containers). Use porta ou PID.
5. **Segredos:** `.env` é gitignored, e `check:secrets` roda sobre os arquivos rastreados. Credenciais do compose são só de dev.

## Regras de negócio herdadas da agência (não mudam)
- O SociMan **nunca publica** em rede social.
- Corte só de canal `autorizado` ou `programa-de-cortes`, e só o dono muda esse status.
