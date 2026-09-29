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
redis / mailpit     sessões e limites de tentativa (Redis, AOF) / e-mail de dev (Mailpit)
docker/nginx        edge: /api → api:3001, /img → imgproxy, / → SPA; headers e CSP
reference/volans-api  API TypeScript original do volans (SÓ referência para portar a auth; não roda)
docs/reference/volans arquitetura, ADRs e produto do volans (referência)
.specify/ .claude/skills  Spec Kit
```

## Comandos
```bash
docker compose up -d                        # stack: http://localhost:8180  https://localhost:8543
curl http://localhost:8180/api/health       # {"status":"ok","db":"ok","redis":"ok"}
docker compose exec api uv run pytest       # API (banco sociman_test + Redis DB 15; NUNCA duas suítes ao mesmo tempo)
docker compose exec api uv run ruff check .
npm run check:web                           # check:contract + typecheck + build + check:bundle/csp/secrets
npm run gen:contract                        # OpenAPI do FastAPI → packages/contract (roda no host, sem Docker)
npm run test:e2e                            # Playwright contra :8180 — ATENÇÃO: zera o banco de dev (reset-db)
docker compose exec api uv run sociman create-owner --email E --name N [--force]   # primeiro dono
docker compose exec api uv run sociman set-password --email E                      # senha de emergência
docker compose exec api uv run sociman reset-db --yes                              # zera banco+Redis (não roda em produção)
```
Portas: edge 8180/8543, console do MinIO 9101 (minioadmin/minioadmin, **só dev**), Mailpit (e-mails de dev) em **127.0.0.1:8126**. Postgres, API, Redis, SMTP e imgproxy ficam só na rede interna. **Não use** 8000/5175 (OpenShorts), 18789 (OpenClaw) nem 6379/1025/8025 (arka-manager, já ocupadas no host).

## Armadilhas
1. **Containers rodam como UID 1000.** Se uma pasta de bind mount não existir, o Docker a cria como root (foi o que aconteceu com `docker/certs`). Crie antes.
2. **CSP estrita em produção** (herdada do volans). `check:csp` compara `apps/web/vite.config.ts` com `docker/nginx/05-edge-mode.envsh`. Mudou um, mude o outro.
3. **A API confia em `X-Forwarded-*`** (`--forwarded-allow-ips='*'`) porque só o edge a alcança. Nunca publique a porta da API.
4. **Não mate processos por nome** (`pkill -f vite` mata processos dentro dos containers). Use porta ou PID.
5. **Segredos:** `.env` é gitignored, e `check:secrets` roda sobre os arquivos rastreados. Credenciais do compose são só de dev.
6. **O contrato é gerado** (constitution, princípio IV): não edite `packages/contract/openapi.json` nem `src/generated/` à mão. Mudou rota ou schema na API → `npm run gen:contract`. O `check:contract` acusa divergência.
7. **Sessão do banco com `DbSession` (scope="function")**: no escopo padrão o FastAPI commita depois de enviar a resposta e o SPA lê dado velho. Nunca declare `Depends(get_db)` direto (há teste de regressão).
8. **Negação que precisa ficar registrada** (ex.: `login_failed`) é commitada antes do erro (`_deny` em `auth/service.py`), porque o `get_db` faz rollback quando a rota levanta exceção. Revogação de sessões no Redis só **depois** do commit.
9. **E-mail que não pode revelar se a conta existe** (reenvio de verificação, esqueci a senha) sai em BackgroundTask, para o tempo de resposta ser igual.
10. **`JWT_SECRET`** fica em `apps/api/.env` (gitignored). Sem ele a API usa um segredo efêmero e toda sessão cai a cada reload.

## Regras de negócio herdadas da agência (não mudam)
- O SociMan **nunca publica** em rede social.
- Corte só de canal `autorizado` ou `programa-de-cortes`, e só o dono muda esse status.
