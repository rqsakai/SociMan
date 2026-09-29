# Pesquisa (Fase 0): 001-auth

Referência de comportamento: `reference/volans-api/src/handlers/auth.ts`, `services/tokenService.ts`,
`services/passwordService.ts` e `lib/rateLimit.ts`. Quando algo não é citado aqui, vale o volans.

## R1. Hash de senha
- **Decisão:** Argon2id com `argon2-cffi`, m=19456 KiB, t=2, p=1, salt de 16 bytes e hash de 32 bytes
  (os mesmos parâmetros do volans e o mínimo da OWASP), no formato PHC. `check_needs_rehash` é
  chamado no login para que a troca futura de parâmetros aconteça sem migração.
- **Por quê:** é o padrão da OWASP e o mesmo do volans, com uma lib madura e binários prontos.
- **Alternativas:** `passlib` (sem manutenção); PBKDF2 (o volans tinha como fallback para o
  Workers, o que aqui não é necessário).
- **Tempo constante:** e-mail desconhecido verifica contra um hash fictício calculado uma vez
  (`equalizeTiming` do volans).

## R2. Token de acesso
- **Decisão:** JWT HS256 com `PyJWT`. Claims: `sub` (user id), `fam` (família), `iss="sociman-auth"`,
  `aud="sociman"`, `iat` e `exp` (15 min), com tolerância de 30 s. `JWT_SECRET` precisa ter
  32 caracteres ou mais: em `ENV=production` a falta dele impede o boot, e em dev é gerado um
  segredo efêmero, como no volans.
- **Por quê:** o SPA já guarda o token só em memória e manda `Authorization: Bearer`.
- **Alternativas:** `python-jose` (manutenção fraca); sessão opaca por cookie (exigiria CSRF e
  reescrita do SPA).

## R3. Sessões e renovação no Redis (decisão do dono)
- **Decisão:** `redis` (redis-py, cliente síncrono, porque a API já é síncrona) com o mesmo
  desenho do volans:
  - chave `rt:{fam}` com `{userId, tokenHash, prevTokenHash, prevExpiresAt, expiresAt}` e TTL igual
    ao tempo restante absoluto da família;
  - índice `uf:{userId}`, um SET com as famílias do usuário, para encerrar todas as sessões dele;
  - token de renovação opaco `{fam}.{32 bytes base64url}`. Só o sha256 do token é guardado, e a
    comparação é em tempo constante;
  - a rotação a cada uso aceita o token imediatamente anterior por 60 s, o que resolve duas abas
    renovando ao mesmo tempo; qualquer outro token da família conta como reuso e revoga a família.
    A rotação é atômica: um script Lua (ou `WATCH/MULTI`) evita corrida entre dois refresh;
  - cada requisição autenticada exige JWT válido, família viva no Redis e usuário ativo no banco.
    A consulta ao banco é barata (menos de 10 usuários) e faz a desativação (FR-014) valer na hora,
    não em até 15 min.
- **Persistência:** o Redis roda com `appendonly yes` (AOF, `everysec`) num volume próprio, então
  reiniciar não desloga ninguém. Se o volume for perdido, os usuários só precisam entrar de novo
  (constitution 1.1.0).
- **Alternativas:** tabela de sessões no Postgres, rejeitada por decisão do dono; `redis.asyncio`,
  rejeitado porque misturaria assíncrono numa API síncrona sem ganho para menos de 10 usuários.

## R4. Limite de tentativas
- **Decisão:** janela fixa no Redis com `INCR` + `EXPIRE`, nas chaves
  `rl:{ação}:ip:{bucket}:{ip}` e `rl:{ação}:acct:{bucket}:{email}`. Os limites são os do volans:
  login 30/IP e 10/conta em 15 min; forgot 10/IP e 5/conta por hora; reset 10/IP por hora;
  verify 30/IP por hora (sem conta: o token identifica); resend-verification 30/IP e 5/conta por
  hora; troca de senha 10/conta em 15 min.
  A resposta é 429 `rate_limited` com `Retry-After`.
- **IP do cliente:** o nginx sobrescreve `X-Forwarded-For` com `$remote_addr`, e o uvicorn roda com
  `--proxy-headers`, então `request.client.host` é o IP real. Nada de `TRUSTED_PROXY`.

## R5. Cookie de renovação
- **Decisão:** `sociman_rt`; `Path=/api/auth/refresh`; `HttpOnly`; `Secure`; `SameSite=Strict`;
  `Max-Age` igual ao tempo restante da família. É apagado com os mesmos atributos e `Max-Age=0`.
- **Nota:** `Secure` funciona em `http://localhost` no Chromium (localhost é contexto seguro).
  Pela rede de casa, use o edge HTTPS (:8543).
- **Logout:** como o cookie só vai para `/refresh`, o logout lê `fam` do Bearer (aceitando token
  expirado) e revoga a família, como no volans. A resposta é sempre 200.

## R6. E-mail
- **Decisão:** interface `EmailSender` com dois adaptadores: `SmtpEmailSender` (stdlib `smtplib`)
  e `MemoryEmailSender` (testes unitários). Em dev e e2e, o SMTP aponta para o **Mailpit**
  (`axllent/mailpit`, SMTP 1025 na rede interna; UI e API em `127.0.0.1:8025`, só dev). Os links
  usam `APP_URL`, que em dev é `https://localhost:8543`.
- **Envio:** síncrono dentro da requisição, com timeout de 5 s. Uma falha não desfaz a criação do
  usuário: o dono recebe `emailSent: false` e pode reenviar (caso de borda da spec).
- **Alternativas:** fila de e-mail (YAGNI, princípio VIII); Resend ou outro provedor (fica para a
  produção).

## R7. Contrato gerado do OpenAPI (princípio IV)
- **Situação:** `packages/contract` é Zod escrito à mão (herança do volans), o que viola o
  princípio IV.
- **Decisão:** a fonte passa a ser o OpenAPI do FastAPI.
  - `apps/api/scripts/export_openapi.py` grava `packages/contract/openapi.json`;
  - `openapi-typescript` gera `packages/contract/src/generated/schema.d.ts`;
  - o cliente vira um wrapper fino sobre `openapi-fetch`, que mantém o `ApiError(status, code,
    message)` e o `authFetch` do SPA;
  - `npm run check:contract` regenera tudo e falha se houver diff, e entra no `check:web`.
- **Validação de formulário:** os schemas Zod de formulário saem do contrato e vão para
  `apps/web/src/lib/forms.ts`. São regra de UI (o mínimo de 12 caracteres vem de `GET /api/config`)
  e o servidor continua sendo a autoridade.
- **Alternativas:** manter o Zod e comparar com o OpenAPI (dupla manutenção); `orval`, que gera
  cliente e Zod (mais pesado, e gera hooks que não usamos).

## R8. Papéis, troca obrigatória de senha e autoria
- **Papéis:** enum `dono` | `membro` no Postgres. A dependência `require_owner` retorna 403
  `forbidden` para quem não é dono.
- **Troca obrigatória (FR-012a):** com `must_change_password = true`, toda rota autenticada, exceto
  `GET /api/auth/me`, `POST /api/auth/password/change` e `POST /api/auth/logout`, responde 403
  `password_change_required`. O SPA redireciona para `/trocar-senha`.
- **Autoria (FR-016):** a dependência `get_actor()` devolve `Actor(kind="user", user_id)`.
  O mixin `AuditMixin` (`created_at`, `created_by`, `updated_at`, `updated_by`) fica pronto para as
  próximas specs. `Actor.kind` já prevê `"mcp_client"` (spec 009) sem precisar implementá-lo.
- **Histórico de usuários (VII):** cada mudança em usuário (papel, nome, e-mail, ativo, senha
  redefinida) gera um evento de segurança com `details` guardando o antes e o depois. A reversão é
  manual pela gestão de usuários; um histórico genérico com reversão vem com a primeira spec de
  domínio.

## R9. Testes
- **Decisão:** pytest com Postgres e Redis **reais** do compose.
  - Banco `sociman_test`, criado por `docker/postgres/init/01-test-db.sql`; Redis DB 15.
  - O `conftest.py` roda `alembic upgrade head` uma vez e faz `TRUNCATE` e `FLUSHDB` entre os testes.
  - Os testes rodam no container: `docker compose exec api uv run pytest`.
  - E-mail: `MemoryEmailSender` via override de dependência.
- **e2e (Playwright):** passa a usar a stack do compose (`http://localhost:8180`). O
  `global-setup` zera o banco pela CLI de teste, cria o dono pela CLI e limpa o Mailpit
  (`DELETE /api/v1/messages`). Os links são lidos pela API do Mailpit.
  Os specs herdados são reescritos: não há mais cadastro público.
- **Alternativas:** SQLite em memória (esconde diferenças do Postgres); testcontainers (mais uma
  dependência, e o compose já existe).

## R10. Rotina de instalação (FR-011)
- **Decisão:** CLI `sociman` (Typer, entry point no `pyproject`), com os comandos:
  - `create-owner --email --name`: senha via prompt oculto, nasce com e-mail verificado e sem troca
    obrigatória, e recusa se já existir um dono ativo, salvo `--force`;
  - `set-password --email`: redefinição de emergência, que encerra as sessões;
  - `reset-db --yes`: só com `ENV != production`, usado pelo e2e.

  Cada comando gera um evento de segurança com o autor `system:cli`.
- **Alternativas:** endpoint de bootstrap na web (superfície pública desnecessária); script solto
  sem entry point.
