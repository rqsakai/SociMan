# Implementation Plan: Autenticação e papéis (001-auth)

**Branch**: `001-auth` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-auth/spec.md`

## Summary

Portar para o FastAPI a autenticação do volans e adaptá-la ao SociMan:
- login por e-mail e senha (Argon2id), com JWT curto só em memória e renovação por cookie httpOnly
  rotacionado, com as famílias de sessão e os limites de tentativa no **Redis**;
- sem cadastro público: só o dono cria usuários, a verificação de e-mail é obrigatória e a senha
  provisória precisa ser trocada;
- papéis `dono` e `membro`, rotina de instalação por CLI, log de eventos de segurança com tela para
  o dono, e identidade do autor pronta para as próximas specs;
- e-mail por SMTP, capturado pelo Mailpit em dev;
- o contrato do SPA passa a ser gerado do OpenAPI do FastAPI (princípio IV).

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.12 (API, uv); TypeScript 5 / React 19 (SPA)

**Primary Dependencies**:
- já existentes: FastAPI, SQLAlchemy 2 (síncrono, psycopg 3), Alembic, pydantic-settings;
- **novas na API:** `argon2-cffi`, `PyJWT`, `redis`, `typer`;
- **novas no web:** `openapi-typescript`, `openapi-fetch`.

**Storage**: PostgreSQL 17 (users, one_time_tokens, security_events); Redis 7 com AOF (sessões e
limites de tentativa)

**Testing**: pytest contra o Postgres (`sociman_test`) e o Redis (DB 15) do compose; ruff;
`npm run check:web`; Playwright e2e contra o edge `:8180`, com os e-mails lidos pela API do Mailpit

**Target Platform**: Linux (docker compose no `sakai-desktop`), navegador moderno (SPA/PWA)

**Project Type**: web application (SPA + API)

**Performance Goals**: login em menos de 1 s no servidor (o Argon2id custa uns 50 ms); o resto é
trivial para menos de 10 usuários

**Constraints**:
- CSP estrita (`connect-src 'self'`) sem mudança;
- API só via edge;
- containers com UID 1000;
- portas do host 6379, 1025 e 8025 ocupadas pelo arka-manager, então o Mailpit UI fica em
  `127.0.0.1:8126` e o Redis não é publicado.

**Scale/Scope**: menos de 10 usuários; 17 endpoints; 4 telas novas e 4 ajustadas; 1 CLI

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Nenhum agente publica | ✅ | nenhuma integração com rede social; teste-guarda T023 |
| II. Direito primeiro | ✅ | entrega a base: o papel `dono` e o `require_owner` no servidor; o status de direito em si fica na 008 |
| III. Marca em tokens | n/a | |
| IV. Contrato é a fonte única | ✅ com trabalho | o OpenAPI do FastAPI gera `packages/contract` e `check:contract` acusa diff (R7); os schemas Zod escritos à mão saem |
| V. Segurança e segredos | ✅ | `JWT_SECRET` só em `.env` (gitignored) e obrigatório em produção; cookie `HttpOnly`/`Secure`/`SameSite=Strict`; senha e token nunca vão para o log; Redis e SMTP sem porta publicada |
| VI. Testes antes de pronto | ✅ | a lista obrigatória está no [quickstart](quickstart.md#7-testes-automatizados-princípio-vi); as regras de II e VII têm teste no backend |
| VII. Humano no controle | ✅ | `Actor` em toda requisição; `created_by`/`updated_by`; usuários nunca são apagados; `security_events` imutável com antes e depois. **Reversão na 001:** o dono refaz a edição pela gestão de usuários com base no antes/depois do evento; a reversão genérica com um clique vem na primeira spec de domínio (R8) |
| VIII. Simplicidade | ✅ com justificativa | as dependências novas estão na tabela abaixo; Redis e Mailpit são respaldados pela constitution 1.1.0 |

**Reavaliação pós-design:** mantida. O desenho não adiciona nada fora da tabela.

## Project Structure

### Documentation (this feature)

```text
specs/001-auth/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── pyproject.toml                  # + argon2-cffi, pyjwt, redis, typer; script "sociman"
├── start.sh                        # sem mudança (alembic upgrade + uvicorn)
├── migrations/versions/0001_auth.py
├── scripts/export_openapi.py       # grava packages/contract/openapi.json
├── src/sociman_api/
│   ├── main.py                     # cria app, handlers de erro (envelope), inclui routers
│   ├── config.py                   # + JWT_SECRET, REDIS_URL, SMTP_*, APP_URL, TTLs
│   ├── db.py                       # + SessionLocal e dependência get_db
│   ├── redis.py                    # cliente Redis (lru_cache)
│   ├── errors.py                   # ApiError(code, message, status) e handlers
│   ├── auth/
│   │   ├── models.py               # User, OneTimeToken, SecurityEvent, AuditMixin
│   │   ├── schemas.py              # modelos Pydantic (viram o OpenAPI)
│   │   ├── passwords.py            # Argon2id, política (12..128, lista comum), equalize_timing
│   │   ├── tokens.py               # JWT e famílias de renovação no Redis (rotação atômica)
│   │   ├── rate_limit.py
│   │   ├── email.py                # EmailSender, SmtpEmailSender, MemoryEmailSender e templates pt-BR
│   │   ├── events.py               # record_event(...)
│   │   ├── deps.py                 # get_actor, current_user, require_owner, bloqueio de troca pendente
│   │   ├── service.py              # regras: login, reset, verify, criar e editar usuário, último dono
│   │   ├── router_auth.py          # /api/auth/*
│   │   ├── router_users.py         # /api/users/*
│   │   └── router_events.py        # /api/security-events
│   └── cli.py                      # Typer: create-owner, set-password, reset-db
└── tests/
    ├── conftest.py                 # sociman_test, Redis DB 15, TRUNCATE/FLUSHDB, override de e-mail
    ├── unit/                       # passwords, tokens (rotação, carência, reuso), rate_limit
    └── integration/                # rotas: auth, users (403 membro, last_owner), events, autor

packages/contract/
├── openapi.json                    # GERADO (commitado)
└── src/
    ├── generated/schema.d.ts       # GERADO pelo openapi-typescript
    ├── client.ts                   # wrapper openapi-fetch; mantém ApiError e a mesma API
    ├── errors.ts                   # códigos (tipados a partir do OpenAPI)
    └── index.ts                    # remove schemas/{auth,config,consent}.ts e password.ts

apps/web/src/
├── lib/{api.ts,authStore.ts,authActions.ts,forms.ts}   # forms.ts recebe os Zod de UI
├── components/{RequireAuth.tsx,RequireOwner.tsx}
└── pages/{Login,ForgotPassword,ResetPassword,VerifyEmail,AppHome,
           ChangePassword,Account,Users,SecurityEvents}.tsx     # Register.tsx e o banner de consentimento saem

docker-compose.yml                  # + redis (AOF, volume redis-data), + mailpit (127.0.0.1:8126), api depends_on redis
docker/postgres/init/01-test-db.sql # cria o banco sociman_test
.env.docker                         # + REDIS_URL, SMTP_HOST=mailpit, SMTP_PORT=1025, APP_URL (sem segredo)
e2e/                                # global-setup via CLI e Mailpit; specs reescritos (sem /register)
playwright.config.ts                # baseURL http://localhost:8180, sem webServer próprio
package.json                        # + gen:contract, check:contract (dentro de check:web)
```

**Structure Decision**: web application já existente (`apps/api` + `apps/web` +
`packages/contract`). O domínio de auth fica agrupado em `sociman_api/auth/`, e as próximas specs
seguem o mesmo padrão (`sociman_api/<dominio>/`).

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Redis (serviço novo) | decisão do dono; TTL nativo e operações atômicas para rotação e limite de tentativas | tabela no Postgres: rejeitada pelo dono; constitution 1.1.0 |
| Mailpit (serviço de dev) | a verificação de e-mail é obrigatória (FR-020), e os e2e precisam ler e-mails reais | e-mail em arquivo JSONL (volans): não testa o SMTP de verdade |
| `openapi-typescript` + `openapi-fetch` | o princípio IV exige cliente gerado do OpenAPI | continuar com Zod à mão: viola o princípio IV |
| `typer` | CLI com prompt oculto e subcomandos (FR-011) | `argparse`: viável, mas o prompt de senha e a ajuda saem mais trabalhosos; troca aceitável se o dono preferir zero dependências |
| Troca da base dos e2e (SQLite → stack do compose) | a API agora é Python e Postgres; os helpers do volans acessavam o SQLite direto | manter os e2e antigos: quebrariam |
