---

description: "Tarefas da feature 001-auth"
---

# Tasks: Autenticação e papéis (001-auth)

**Input**: Design documents from `/specs/001-auth/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-api.md, quickstart.md

**Tests**: OBRIGATÓRIOS. O princípio VI da constitution exige pytest, ruff, check:web e e2e, e as
regras I, II e VII precisam de teste no backend. A lista mínima está no quickstart, §7.

**Organization**: tarefas agrupadas por user story; cada story é testável sozinha.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US4, conforme o spec.md
- Caminhos relativos à raiz do repo. API em `apps/api/src/sociman_api/` (abreviado `api/` abaixo
  só na explicação; nas tarefas o caminho vai completo)

---

## Phase 1: Setup (infraestrutura compartilhada)

**Purpose**: serviços, dependências e configuração

- [X] T001 Adicionar o serviço `redis` (`redis:7-alpine`, `command: redis-server --appendonly yes --appendfsync everysec`, volume `redis-data:/data`, healthcheck `redis-cli ping`, SEM `ports`) e o serviço `mailpit` (`axllent/mailpit`, `ports: ["127.0.0.1:8126:8025"]`, SMTP 1025 só na rede interna) em `docker-compose.yml`; em `api.depends_on`, acrescentar `redis: service_healthy` e `mailpit: service_started`; declarar o volume `redis-data`
- [X] T002 [P] Criar `docker/postgres/init/01-test-db.sql` (`CREATE DATABASE sociman_test OWNER sociman;`) e montá-lo em `postgres` como `./docker/postgres/init:/docker-entrypoint-initdb.d:ro` em `docker-compose.yml`. Documentar em `quickstart.md` que um volume `postgres-data` já existente exige `docker compose exec postgres createdb -U sociman sociman_test` uma vez
- [X] T003 [P] Acrescentar a `.env.docker` e a `.env.example` (sem segredos): `REDIS_URL` (`redis://redis:6379/0`, e `localhost` no example), `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_FROM="SociMan <nao-responda@sociman.local>"`, `APP_URL=http://localhost:8180`, `TEST_DATABASE_URL` (…/sociman_test), `TEST_REDIS_URL` (…/15); `JWT_SECRET` só como comentário, dizendo "defina em apps/api/.env"
- [X] T004 Adicionar as dependências `argon2-cffi`, `pyjwt`, `redis` e `typer` e o script `[project.scripts] sociman = "sociman_api.cli:app"` em `apps/api/pyproject.toml`; rodar `uv lock` (atualiza `apps/api/uv.lock`) e reconstruir a imagem (`docker compose build api`)
- [X] T005 [P] Adicionar `openapi-typescript` e `openapi-fetch` a `packages/contract/package.json` e rodar `npm install` na raiz (atualiza `package-lock.json`)
- [X] T006 Estender `apps/api/src/sociman_api/config.py`:
  - campos `jwt_secret: str | None`, `redis_url`, `smtp_host`, `smtp_port`, `smtp_from`, `smtp_timeout=5`, `app_url`, `access_ttl=900`, `refresh_ttl=604800`, `refresh_grace=60`, `verify_ttl=86400`, `reset_ttl=900`, `password_min_length=12` e `password_max_length=128`;
  - um validador que falha se `env == "production"` e `jwt_secret` tiver menos de 32 caracteres ou estiver ausente;
  - em dev, um segredo efêmero via `secrets.token_urlsafe(48)`, com aviso no log.

---

## Phase 2: Foundational (pré-requisitos bloqueantes)

**Purpose**: banco, Redis, erros, tokens, eventos e o pipeline do contrato, usados por todas as stories

**⚠️ CRITICAL**: nenhuma story começa antes do fim desta fase

- [X] T007 Adicionar `SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)` e a dependência `get_db()` (yield, com commit ou rollback) em `apps/api/src/sociman_api/db.py`
- [X] T008 [P] Criar `apps/api/src/sociman_api/redis.py` com `get_redis()` (`lru_cache`, `redis.Redis.from_url(settings.redis_url, decode_responses=True)`) e incluir `redis: "ok"|"unavailable"` no `/api/health` em `apps/api/src/sociman_api/main.py` (503 se o banco ou o Redis falhar)
- [X] T009 [P] Criar `apps/api/src/sociman_api/errors.py`:
  - `ApiError(status, code, message, headers=None)`;
  - handlers que produzem `{"error":{"code","message"}}`;
  - um handler de `RequestValidationError` que devolve 400 `validation_error` com a mensagem do primeiro erro, em pt-BR;
  - um handler genérico 500 `internal_error`, sem vazar o stack.

  Registrar tudo em `apps/api/src/sociman_api/main.py`.
- [X] T010 Criar os modelos em `apps/api/src/sociman_api/auth/models.py`, exatamente como no data-model.md:
  - `AuditMixin`: `created_at`, `created_by` e `updated_at`, `updated_by`, todos uuid null FK→users.id;
  - `User`:
    - `id` uuid;
    - `name` text not null, "1..120 caracteres, sem espaço nas pontas";
    - `email` text not null UNIQUE, "normalizado (trim + minúsculas)";
    - `password_hash` text not null;
    - `role` enum `user_role` (`dono`, `membro`);
    - `is_active` bool default true;
    - `email_verified_at` timestamptz null;
    - `must_change_password` bool default false;
    - `password_changed_at` timestamptz not null;
  - `OneTimeToken`:
    - `token_hash` text PK;
    - `user_id` FK;
    - `purpose` enum `token_purpose` (`verify_email`, `reset_password`);
    - `email` text not null;
    - `expires_at`;
    - `used_at` null;
    - `created_at`;
    - índice `(user_id, purpose)`;
  - `SecurityEvent`:
    - `id` bigint identity;
    - `occurred_at` default now();
    - `type` text;
    - `outcome` (`ok`|`denied`);
    - `actor_user_id` null;
    - `actor_kind` (`user`|`anonymous`|`system:cli`);
    - `subject_user_id` null;
    - `ip` inet null;
    - `user_agent` text null, truncado em 300;
    - `details` jsonb default '{}';
    - índices `(occurred_at desc)`, `(subject_user_id, occurred_at desc)` e `(type, occurred_at desc)`.

  Importar os modelos em `apps/api/migrations/env.py`.
- [X] T011 Gerar e revisar a migration `apps/api/migrations/versions/0001_auth.py` (enums, tabelas e índices do T010). Aplicar com `docker compose exec api uv run alembic upgrade head` e conferir com `\d users` no psql
- [X] T012 [P] Criar `apps/api/src/sociman_api/auth/passwords.py`:
  - `hash_password` e `verify_password` com `argon2.PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16)`;
  - `needs_rehash`;
  - `validate_password_policy(pw, current=None)`: 12..128 caracteres, recusa uma lista de senhas comuns (portar a de `packages/contract/src/password.ts` e ampliar com as 100 mais comuns, comparando em minúsculas) e recusa a senha igual à atual;
  - `equalize_timing()`, que verifica contra um hash fictício calculado uma vez.
- [X] T013 [P] Criar `apps/api/src/sociman_api/auth/tokens.py`:
  - access token:
    - JWT HS256 com `sub`, `fam`, `iss="sociman-auth"`, `aud="sociman"`, `iat`, `exp=access_ttl` e leeway de 30 s;
    - `decode_access(token, allow_expired=False)`, porque o logout precisa aceitar token expirado;
  - famílias de renovação no Redis:
    - `create_family(user_id)` devolve `(access, refresh, fam)`;
    - `rt:{fam}` é um hash `{userId, tokenHash, prevTokenHash, prevExpiresAt, expiresAt}` com TTL do tempo restante absoluto;
    - o SET `uf:{userId}` indexa as famílias do usuário;
  - `rotate(refresh)`, atômica via script Lua:
    - token atual: gira, e o anterior ganha carência de `refresh_grace`;
    - token anterior dentro da carência: devolve um novo token sem estender a carência;
    - qualquer outro token: revoga a família e devolve `reused`;
  - `family_alive(fam)`, `revoke_family(fam)` e `revoke_all_for_user(user_id, except_fam=None)`;
  - o token de renovação tem o formato `{fam}.{token_urlsafe(32)}`, o hash é sha256 hex e a comparação usa `hmac.compare_digest`.
- [X] T014 [P] Criar `apps/api/src/sociman_api/auth/rate_limit.py` com `check(action, ip, account=None)`:
  - janela fixa com `INCR`+`EXPIRE`, nas chaves `rl:{ação}:ip:{bucket}:{ip}` e `rl:{ação}:acct:{bucket}:{email}`;
  - limites:
    - login: 30/IP e 10/conta em 15 min;
    - forgot: 10/IP e 5/conta por hora;
    - reset: 10/IP por hora;
    - verify: 30/IP por hora;
    - resend: 30/IP e 5/conta por hora;
    - change: 10/conta em 15 min;
  - quando o limite estoura, levanta `ApiError(429, "rate_limited", …, headers={"Retry-After": …})`.
- [X] T015 [P] Criar `apps/api/src/sociman_api/auth/events.py` com `record_event(db, type, outcome, actor, subject_user_id=None, request=None, details=None)`. Ele pega o IP de `request.client.host` e o user agent truncado em 300. Deve filtrar de `details` qualquer chave `password`, `token` ou `hash`
- [X] T016 Criar `apps/api/src/sociman_api/auth/deps.py`:
  - `Actor` (dataclass `kind`, `user_id`, `user`);
  - `get_actor`;
  - `current_user`: Bearer → JWT → `family_alive` → usuário `is_active`; se falhar, 401 `unauthorized`;
  - `require_user`: igual ao `current_user`, e mais 403 `password_change_required` quando `must_change_password`, exceto nas rotas isentas;
  - `require_owner`: 403 `forbidden` para quem não é `dono`.
- [X] T017 [P] Criar `apps/api/src/sociman_api/auth/email.py`:
  - o protocolo `EmailSender.send(to, subject, text, html)`;
  - `SmtpEmailSender` (smtplib, timeout `smtp_timeout`), que devolve `bool` e loga falha sem o conteúdo;
  - `MemoryEmailSender` (lista `outbox`);
  - a dependência `get_email_sender`;
  - os templates pt-BR "Confirme seu e-mail" (link `{app_url}/verify-email?token=`) e "Redefinir senha" (link `{app_url}/reset-password?token=`).
- [X] T018 [P] Criar `apps/api/src/sociman_api/auth/schemas.py` com os modelos Pydantic de contracts/http-api.md:
  - `User`, `AuthSession`, `Ok`, `AppConfig`, `SecurityEvent` e `Page`, com saída camelCase via `alias_generator=to_camel` e `populate_by_name`;
  - `LoginIn`, que normaliza o e-mail com strip+lower;
  - `ForgotIn`, `ResetIn`, `VerifyIn`, `ResendIn`, `ChangePasswordIn`, `CreateUserIn` (`name` 1..120, `role`, `provisionalPassword`), `UpdateUserIn` e `SetPasswordIn`;
  - `ErrorEnvelope`, que é documentado nas respostas 4xx.
- [X] T019 Criar `apps/api/tests/conftest.py`:
  - usa `TEST_DATABASE_URL` e `TEST_REDIS_URL` (override de `get_settings`);
  - roda `alembic upgrade head` uma vez por sessão;
  - fixture autouse com `TRUNCATE users, one_time_tokens, security_events RESTART IDENTITY CASCADE` e `FLUSHDB`;
  - override de `get_email_sender` por `MemoryEmailSender`;
  - fixtures `client`, `make_user(role, verified=True, must_change=False, password=…)` e `login(client, email, pw)`, que devolve os headers com Bearer.

  Adaptar `apps/api/tests/test_health.py` ao Redis.
- [X] T020 [P] Testes unitários em `apps/api/tests/unit/test_passwords.py`: hash e verify; política de 11 e 12 caracteres, senha comum e igual à atual; o `equalize_timing` não levanta exceção
- [X] T021 [P] Testes unitários em `apps/api/tests/unit/test_tokens.py`:
  - a rotação gira o token;
  - o token anterior dentro da carência passa, e fora dela conta como reuso e revoga a família;
  - duas rotações concorrentes (threads) com o mesmo token não derrubam a família;
  - a expiração absoluta não é estendida;
  - `revoke_all_for_user` com `except_fam` funciona.
- [X] T022 [P] Testes unitários em `apps/api/tests/unit/test_rate_limit.py`: o 11º login da mesma conta em 15 min dá 429 com `Retry-After`; contas diferentes não interferem
- [X] T023 [P] Teste-guarda do princípio I (nenhum agente publica) em `apps/api/tests/unit/test_constitution_guards.py`:
  - falha se alguma rota do `app.openapi()` tiver no caminho ou no `operationId` termos de publicação (`publish`, `post-to`, `upload-to`, `share`, `tiktok`, `youtube`, `instagram`);
  - falha se o `apps/api/pyproject.toml` declarar SDK de rede social (lista negra: `tiktok`, `google-api-python-client`, `instagrapi`, `facebook`, `tweepy`);
  - as próximas specs só ampliam as listas. O teste também documenta, em comentário, que o princípio II ganha teste na 008.
- [X] T024 Criar `apps/api/scripts/export_openapi.py`, que grava `app.openapi()` com `sort_keys=True` em `packages/contract/openapi.json`. Na raiz, em `package.json`, criar:
  - `gen:contract`: `uv run --directory apps/api python scripts/export_openapi.py && openapi-typescript packages/contract/openapi.json -o packages/contract/src/generated/schema.d.ts`. Roda no host, sem Docker nem Postgres: o script só importa o `app` e chama `app.openapi()`, e nenhum import pode abrir conexão;
  - `check:contract`: `gen:contract` seguido de `git diff --exit-code packages/contract`;
  - `check:contract` também entra no `check:web`.
- [X] T025 Reescrever `packages/contract/src/client.ts` sobre `openapi-fetch` (`createClient<paths>`), mantendo a assinatura pública `createApiClient({baseUrl, fetchFn})` e o `ApiError(status, code, message)` com fallback `internal_error`. Tipar os códigos em `packages/contract/src/errors.ts` a partir de `components["schemas"]`. Apagar `packages/contract/src/schemas/{auth,config,consent}.ts` e `packages/contract/src/password.ts` e atualizar `packages/contract/src/index.ts`
- [X] T026 Mover a validação de formulário para `apps/web/src/lib/forms.ts`: Zod de e-mail, com trim e minúsculas, e de senha com o mínimo vindo de `GET /api/config` (fallback 12). Ajustar os imports em `apps/web/src/pages/*.tsx` e `apps/web/src/lib/useAppConfig.ts` (tirar o `consentPolicyVersion`)

**Checkpoint**: `uv run pytest tests/unit`, `alembic upgrade head` e `npm run check:contract` verdes. Aí as stories podem começar.

---

## Phase 3: User Story 1 – Entrar e sair do SociMan (Priority: P1) 🎯 MVP

**Goal**: o dono, criado pela CLI, entra, mantém a sessão ao recarregar e sai.

**Independent Test**: `sociman create-owner` → login → recarregar → abrir `/app` → sair → `/app` exige login de novo (quickstart §2–3).

### Testes da US1

- [X] T027 [P] [US1] Testes de integração em `apps/api/tests/integration/test_auth_session.py`:
  - login ok devolve `accessToken` + `user` e o `Set-Cookie` `sociman_rt` com `Path=/api/auth/refresh; HttpOnly; Secure; SameSite=Strict`;
  - senha errada e e-mail inexistente dão o mesmo 401 `invalid_credentials` com o mesmo corpo (SC-006);
  - e-mail não verificado dá 403 `email_not_verified`;
  - usuário inativo dá 401;
  - `/refresh` rotaciona e o replay do cookie antigo fora da carência dá 401 e derruba a família;
  - `/logout` com Bearer expirado revoga a família e `/me` depois dá 401;
  - `/me` sem token dá 401;
  - `/api/config` devolve `passwordMinLength: 12`.
- [X] T028 [P] [US1] Testes da CLI em `apps/api/tests/integration/test_cli.py` (Typer `CliRunner`):
  - `create-owner` cria um dono verificado sem troca obrigatória e grava o evento `user_created` com `actor_kind=system:cli`;
  - a segunda execução é recusada sem `--force`;
  - `set-password` troca a senha e revoga as sessões;
  - `reset-db` recusa com `ENV=production`.

### Implementação da US1

- [X] T029 [US1] Implementar em `apps/api/src/sociman_api/auth/service.py`:
  - `login(db, email, pw, request)`:
    - roda o rate limit;
    - e-mail inexistente chama `equalize_timing`;
    - verifica a senha, com rehash se `needs_rehash`;
    - `is_active` falso, e também senha errada, dão 401 `invalid_credentials`;
    - `email_verified_at` null dá 403;
    - cria a família;
    - grava os eventos `login_succeeded` e `login_failed`;
  - `refresh(token)`: em reuso grava `refresh_reuse_detected`, e um usuário inativo revoga a família;
  - `logout(bearer)`: grava o evento `logout` quando o Bearer identifica o usuário.
- [X] T030 [US1] Criar `apps/api/src/sociman_api/auth/router_auth.py` com `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`, `GET /api/auth/me` e `GET /api/config`:
  - helper de cookie `sociman_rt`: define com `Max-Age` igual ao tempo restante e apaga com os mesmos atributos e `Max-Age=0`;
  - `responses` documentando o `ErrorEnvelope`;
  - incluir o router em `main.py`.
- [X] T031 [US1] Criar `apps/api/src/sociman_api/cli.py` (Typer):
  - `create-owner --email --name [--force]`, com a senha por `typer.prompt(hide_input=True, confirmation_prompt=True)` e validação pela política;
  - `set-password --email`;
  - `reset-db --yes`, só com `ENV != production`, que faz TRUNCATE e FLUSHDB.

  Cada comando grava o evento com `actor_kind=system:cli`.
- [X] T032 [US1] Regenerar o contrato (`npm run gen:contract`) e ajustar `apps/web/src/lib/api.ts`, `apps/web/src/lib/authStore.ts` e `apps/web/src/lib/authActions.ts`:
  - remover `register`;
  - o `User` passa a ter `role`, `isActive` e `mustChangePassword`;
  - manter o refresh single-flight e o `sessionEpoch`.
- [X] T033 [US1] Ajustar as páginas e rotas:
  - `apps/web/src/pages/Login.tsx`: sem link de cadastro; mensagem "E-mail ou senha incorretos";
  - `apps/web/src/App.tsx`: remover a rota `/register` e apagar `apps/web/src/pages/Register.tsx`;
  - remover o consentimento: apagar `apps/web/src/components/ConsentBanner.tsx` e `apps/web/src/lib/consent.ts` e tirar as referências em `apps/web/src/App.tsx` e `apps/web/src/lib/useAppConfig.ts`;
  - `RequireAuth.tsx`: redirecionar para a rota pedida depois do login (cenário US1-5).
- [X] T034 [US1] Reescrever a base dos e2e:
  - `playwright.config.ts`: `baseURL` `http://localhost:8180`, sem `webServer`, com checagem de `/api/health` no global setup;
  - `e2e/global-setup.ts`: `docker compose exec -T api uv run sociman reset-db --yes`, depois o dono de teste via `create-owner`, com a senha por stdin;
  - `e2e/helpers.ts`: cliente da API do Mailpit, com `DELETE /api/v1/messages` e a busca do último e-mail para um destinatário para extrair o link, e um helper para expirar tokens via `docker compose exec -T postgres psql`.
- [X] T035 [US1] Reescrever os specs `e2e/wrong-password.spec.ts` (mesma mensagem para senha errada e e-mail inexistente) e `e2e/refresh-reuse.spec.ts` (cookie `sociman_rt`, rotação dupla e replay → `/login`), e criar `e2e/session.spec.ts` (login → reload mantém a sessão → sair → `/app` exige login; confere que o cookie `sociman_rt` é `HttpOnly` e que o `localStorage` e o `sessionStorage` não guardam token, FR-002). Apagar `e2e/happy.spec.ts`, porque dependia do cadastro público e do consentimento, e o fluxo completo fica coberto pelos specs novos

**Checkpoint**: a US1 funciona sozinha. Pontos de validação: quickstart §1–3, `pytest tests/integration/test_auth_session.py tests/integration/test_cli.py` e os e2e da US1.

---

## Phase 4: User Story 2 – Papel de dono e usuários da casa (Priority: P1)

**Goal**: o dono cria e gerencia membros. A verificação de e-mail é obrigatória e a senha provisória tem de ser trocada. O membro não acessa o que é só do dono.

**Independent Test**: quickstart §4, do cadastro do membro até o 403 nas telas só-dono e o `last_owner`.

### Testes da US2

- [X] T036 [P] [US2] Testes de integração em `apps/api/tests/integration/test_users_admin.py`:
  - `POST /api/users`: cria com `must_change_password=true` e `email_verified_at=null`, e envia o e-mail de verificação (outbox);
  - e-mail duplicado dá 409 `email_in_use`;
  - `PATCH`: trocar o e-mail zera a verificação, reenvia o link e revoga as sessões;
  - desativar revoga as sessões, e o `/me` seguinte do usuário dá 401;
  - rebaixar ou desativar o último dono ativo dá 409 `last_owner`;
  - `POST /api/users/{id}/password` revoga as sessões e liga a troca obrigatória;
  - `POST /api/users/{id}/verification` em usuário já verificado dá 409;
  - falha simulada de SMTP devolve `emailSent: false` e o usuário é criado.
- [X] T037 [P] [US2] Testes em `apps/api/tests/integration/test_permissions.py`:
  - parametrizar TODAS as rotas só-dono (`GET/POST /api/users`, `PATCH /api/users/{id}`, `POST …/password`, `POST …/verification`, `GET /api/security-events`) e verificar 403 `forbidden` para `membro` (SC-003);
  - com `must_change_password`, qualquer rota fora de `me`, `password/change` e `logout` dá 403 `password_change_required`.
- [X] T038 [P] [US2] Testes em `apps/api/tests/integration/test_verification_and_change.py`:
  - `verify-email` com token válido marca como verificado, e o reuso dá 400 `invalid_token`;
  - token expirado dá 400;
  - token de um e-mail antigo, depois da troca de e-mail, dá 400;
  - `resend` devolve 200 idêntico para e-mail existente e inexistente, e aplica rate limit;
  - `password/change` com a senha atual errada dá 400 `invalid_credentials`;
  - a troca zera `must_change_password`, mantém a sessão atual e revoga as outras;
  - trocar pela mesma senha dá 400.

### Implementação da US2

- [X] T039 [US2] Implementar em `apps/api/src/sociman_api/auth/service.py`:
  - `issue_token(db, user, purpose)`: invalida os anteriores do mesmo propósito e guarda o sha256 com o e-mail atual e `expires_at` (+24 h verify, +15 min reset);
  - `consume_token(db, raw, purpose)`: faz `SELECT … FOR UPDATE`, confere validade, uso e se o e-mail ainda é o mesmo, e marca `used_at`;
  - `verify_email`, que grava o evento `email_verified`;
  - `resend_verification`, que grava `email_verification_sent` só quando o usuário existe e não está verificado (a resposta pública é sempre igual);
  - `change_password(actor, current, new, current_fam)`, que grava o evento `password_changed`.
- [X] T040 [US2] Implementar em `apps/api/src/sociman_api/auth/service.py` a gestão de usuários:
  - `create_user`: dono only; normaliza o e-mail; `must_change_password=true`; envia a verificação e devolve `emailSent`;
  - `update_user`: `name`, `email`, `role`, `isActive`;
  - `set_provisional_password`;
  - `resend_user_verification`;
  - guarda do último dono: `SELECT … FOR UPDATE` nos donos ativos antes de rebaixar ou desativar;
  - `updated_by` e `created_by` vindos do `Actor`;
  - eventos `user_created`, `user_updated`, `role_changed`, `email_changed`, `user_deactivated`, `user_reactivated`, `password_set_by_owner` e `email_verification_sent`, com `details` antes e depois.
- [X] T041 [US2] Acrescentar `POST /api/auth/verify-email`, `POST /api/auth/verify-email/resend` e `POST /api/auth/password/change` em `apps/api/src/sociman_api/auth/router_auth.py`. A troca devolve `AuthSession`, com um novo access token para a mesma família
- [X] T042 [US2] Criar `apps/api/src/sociman_api/auth/router_users.py` com `GET /api/users`, `POST /api/users`, `PATCH /api/users/{id}`, `POST /api/users/{id}/password` e `POST /api/users/{id}/verification`, todas com `require_owner`. Incluir em `main.py`
- [X] T043 [US2] Regenerar o contrato e, no SPA:
  - `apps/web/src/pages/VerifyEmail.tsx`: depois de confirmar, mostra "E-mail confirmado, faça login" e não cria sessão;
  - `apps/web/src/pages/Login.tsx`: no 403 `email_not_verified`, mostra "Confirme seu e-mail" com o botão "Reenviar link";
  - nova `apps/web/src/pages/ChangePassword.tsx` (`/trocar-senha`): senha atual e nova duas vezes;
  - `RequireAuth.tsx`: força `/trocar-senha` quando `mustChangePassword`, e o `authFetch` trata 403 `password_change_required` da mesma forma.
- [X] T044 [P] [US2] Criar `apps/web/src/components/RequireOwner.tsx`, que mostra "Sem permissão" para `membro`, e `apps/web/src/pages/Users.tsx` (`/app/usuarios`):
  - lista com papel, situação e verificado;
  - formulário de criar (nome, e-mail, papel, senha provisória);
  - editar nome, e-mail e papel;
  - ativar e desativar;
  - definir senha provisória;
  - reenviar verificação;
  - aviso quando `emailSent=false` ou no `last_owner`.
- [X] T045 [P] [US2] Criar `apps/web/src/pages/Account.tsx` (`/app/conta`), com os dados do usuário e a troca voluntária de senha. Adicionar a navegação em `apps/web/src/pages/AppHome.tsx`: links "Usuários" e "Segurança" só para o dono, e "Minha conta"
- [X] T046 [US2] Registrar as rotas `/trocar-senha`, `/app/conta` e `/app/usuarios` em `apps/web/src/App.tsx`
- [X] T047 [US2] Criar `e2e/users.spec.ts`:
  - o dono cria um membro;
  - o e-mail chega no Mailpit;
  - o login antes de verificar é recusado e o reenvio funciona;
  - o membro verifica, entra, é forçado a trocar a senha e depois usa o app;
  - o membro em `/app/usuarios` vê "Sem permissão".

**Checkpoint**: US1 e US2 funcionam juntas. Validar pelo quickstart §4.

---

## Phase 5: User Story 3 – Autor registrado em toda mutação (Priority: P1)

**Goal**: autoria em toda alteração e tela de eventos de segurança para o dono.

**Independent Test**: dois usuários alteram dados, e os registros mostram autor e data. O dono filtra os eventos por usuário, tipo e data (quickstart §6).

### Testes da US3

- [X] T048 [P] [US3] Testes em `apps/api/tests/integration/test_authorship.py`:
  - toda rota de mutação da 001 deixa `updated_by` ou `created_by` igual ao ator e grava um `security_event` com `actor_user_id` (SC-004);
  - requisição de mutação sem token dá 401 e nada é gravado (contar as linhas antes e depois);
  - nenhum `details` contém chaves `password`, `token` ou `hash`.
- [X] T049 [P] [US3] Testes em `apps/api/tests/integration/test_security_events.py`: filtros `userId`, `type`, `from` e `to`; ordem decrescente; paginação por `cursor` com `limit` (1..100, padrão 50); `limit=0` dá 400; `membro` dá 403

### Implementação da US3

- [X] T050 [US3] Criar `apps/api/src/sociman_api/auth/router_events.py` com `GET /api/security-events`:
  - query `userId` (casa com o ator OU com o sujeito), `type`, `from`, `to`, `cursor` e `limit`;
  - o cursor é opaco, base64 de `(occurred_at, id)`;
  - join para devolver `actorName` e `subjectName`;
  - `require_owner`;
  - incluir em `main.py`.
- [X] T051 [US3] Regenerar o contrato e criar `apps/web/src/pages/SecurityEvents.tsx` (`/app/seguranca`, dentro de `RequireOwner`):
  - tabela com data, tipo (rótulo pt-BR), resultado, autor, usuário afetado e IP;
  - filtros de usuário (select), tipo e intervalo de datas;
  - botão "Carregar mais".

  Registrar a rota em `apps/web/src/App.tsx`.
- [X] T052 [US3] Criar `e2e/security-events.spec.ts`: depois do fluxo do membro, o dono filtra pelo membro e vê `user_created`, `email_verified` e `password_changed`

**Checkpoint**: US1, US2 e US3 prontas. Validar pelo quickstart §6.

---

## Phase 6: User Story 4 – Recuperar o acesso (Priority: P2)

**Goal**: esqueci a senha → link por e-mail → nova senha → as sessões antigas caem.

**Independent Test**: quickstart §5.

### Testes da US4

- [X] T053 [P] [US4] Testes em `apps/api/tests/integration/test_password_reset.py`:
  - `forgot` devolve 200 com o mesmo corpo para e-mail existente, inexistente e de usuário inativo, e só envia e-mail para o ativo;
  - aplica rate limit por conta;
  - `reset` com token válido troca a senha, revoga todas as sessões, zera `must_change_password` e grava `password_reset_completed`;
  - o reuso do token dá 400 `invalid_token`;
  - token expirado (+15 min) dá 400;
  - pedir de novo invalida o link anterior;
  - a senha antiga falha e a nova entra.

### Implementação da US4

- [X] T054 [US4] Implementar `request_password_reset` e `reset_password` em `apps/api/src/sociman_api/auth/service.py`, reaproveitando `issue_token` e `consume_token` do T039. Gravar os eventos `password_reset_requested` e `password_reset_completed`
- [X] T055 [US4] Acrescentar `POST /api/auth/password/forgot` e `POST /api/auth/password/reset` em `apps/api/src/sociman_api/auth/router_auth.py`
- [X] T056 [US4] Regenerar o contrato e conferir `apps/web/src/pages/ForgotPassword.tsx` e `apps/web/src/pages/ResetPassword.tsx`, que já existem: mínimo de 12 via `forms.ts` e a mensagem "Link inválido ou expirado — peça um novo" com link para `/forgot-password`
- [X] T057 [US4] Criar `e2e/password-reset.spec.ts` (esqueci → link no Mailpit → nova senha → login; a senha antiga falha) e reescrever `e2e/expired-token.spec.ts` (expira o token via psql → "inválido ou expirado")

**Checkpoint**: todas as stories prontas.

---

## Phase 7: Polish e transversais

- [X] T058 [P] Revisar os logs da API: nenhum log com senha, token, hash ou corpo de requisição de auth. Rodar `grep` no código por `logger.*(password|token)` e corrigir `apps/api/src/sociman_api/auth/*.py`
- [X] T059 [P] Atualizar `CLAUDE.md` (SociMan): os comandos `sociman create-owner`, `set-password` e `reset-db`, Mailpit em `127.0.0.1:8126`, as portas 6379, 1025 e 8025 ocupadas pelo arka-manager, `docker compose exec api uv run pytest` e `npm run check:contract`
- [X] T060 [P] Atualizar `docs/visao.md`: o backlog marca a 001 como especificada e as decisões dela (sem cadastro público, Redis)
- [X] T061 Remover o Sync Impact Report do topo de `.specify/memory/constitution.md` (pedido da própria constitution antes do commit)
- [X] T062 Rodar a verificação completa do quickstart §7 e os passos manuais §1–6: `docker compose exec api uv run pytest`, `docker compose exec api uv run ruff check .`, `npm run check:web` (com `check:contract`, `check:csp` e `check:secrets`) e `npm run test:e2e`. Nos passos manuais, medir e registrar SC-001 (login em menos de 15 s), SC-005 (recuperação em menos de 3 min), SC-008 (e-mail de verificação em menos de 1 min) e SC-009 (achar um evento em menos de 30 s). Registrar a saída e só declarar pronto com tudo verde

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (1)** → **Foundational (2)** → stories. A fase 2 bloqueia todas.
- **US1 (3)** vem primeiro porque é o MVP: entrega login, cookie, refresh, CLI e a base dos e2e.
- **US2 (4)** depende da US1: o fluxo do membro usa login e refresh, e o T047 usa os helpers do T034.
- **US3 (5)** depende da US2 para ter as rotas de mutação a auditar. O `record_event` já existe desde o T015.
- **US4 (6)** depende só da US1 e do `issue_token`/`consume_token` (T039). Se o T039 for antecipado, pode rodar em paralelo com a US2 ou a US3.
- **Polish (7)** vem depois de todas.

### Dentro de cada story
Testes primeiro, falhando; depois o service, o router, o contrato regenerado, o SPA e o e2e.
O contrato é regenerado depois de cada router novo.

### Parallel Opportunities
- **Setup:** T002, T003 e T005 em paralelo; o T004 antes do T006.
- **Foundational:**
  - T008, T009, T012, T013, T014, T015, T017 e T018 em paralelo, porque são arquivos diferentes;
  - T020, T021, T022 e T023 em paralelo depois do T019;
  - T025 e T026 depois do T024.
- **US1:** T027 e T028 em paralelo.
- **US2:** T036, T037 e T038 em paralelo; T044 e T045 em paralelo.
- **US3:** T048 e T049 em paralelo.
- **Polish:** T058, T059 e T060 em paralelo.

## Parallel Example: Foundational

```text
Task: "T012 passwords.py"   Task: "T013 tokens.py"   Task: "T014 rate_limit.py"
Task: "T015 events.py"      Task: "T017 email.py"    Task: "T018 schemas.py"
```

## Parallel Example: User Story 2

```text
Task: "T036 test_users_admin.py"   Task: "T037 test_permissions.py"   Task: "T038 test_verification_and_change.py"
(depois da implementação) Task: "T044 Users.tsx + RequireOwner"   Task: "T045 Account.tsx"
```

## Implementation Strategy

### MVP (só a US1)
1. Setup (T001–T006) e Foundational (T007–T026).
2. US1 (T027–T035).
3. **Parar e validar:** quickstart §1–3 e os testes da US1. O dono já entra no SociMan.

### Incremental
US1 (login do dono) → US2 (membros, verificação e troca obrigatória) → US3 (auditoria e tela
de eventos) → US4 (recuperação) → Polish. Cada checkpoint é validado antes do próximo, um passo
por vez (regra do dono).

## Notes
- [P] = arquivos diferentes, sem dependência pendente.
- Commit só quando o dono pedir (constitution, Fluxo de desenvolvimento).
- Porta: não usar 8000, 5175, 18789, 6379, 1025 nem 8025 no host.
