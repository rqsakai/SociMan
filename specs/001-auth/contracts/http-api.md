# Contrato HTTP: 001-auth

Este arquivo é a fonte de verdade de desenho. Na implementação, a fonte passa a ser o OpenAPI
gerado pelo FastAPI (`/api/openapi.json`), exportado para `packages/contract/openapi.json`
(princípio IV). Tudo fica sob `/api` e é servido via edge.

## Convenções
- **Erro:** `{"error": {"code": string, "message": string}}`, com a mensagem em pt-BR. Os códigos
  são os herdados (`validation_error`, `invalid_credentials`, `email_not_verified`, `email_in_use`,
  `invalid_token`, `unauthorized`, `rate_limited`, `internal_error`) mais os novos `forbidden`,
  `password_change_required`, `last_owner`, `not_found` e `conflict` (ex.: reenviar verificação de e-mail já verificado).
- **Validação:** um corpo inválido responde 400 `validation_error` com a mensagem do primeiro erro.
  O handler do FastAPI é substituído para não devolver o 422 padrão.
- **429:** `rate_limited` com o header `Retry-After` em segundos.
- **Auth:** `Authorization: Bearer <access>`. Um token inválido ou uma família revogada responde 401
  `unauthorized`. Um usuário inativo também responde 401.
- **Troca pendente:** com `mustChangePassword`, todas as rotas autenticadas, exceto `me`,
  `password/change` e `logout`, respondem 403 `password_change_required`.

## Tipos
```text
User          { id: uuid, name: string, email: string, role: "dono"|"membro",
                isActive: bool, emailVerified: bool, mustChangePassword: bool,
                createdAt: datetime, updatedAt: datetime }
AuthSession   { accessToken: string, user: User }
Ok            { ok: true }
AppConfig     { passwordMinLength: 12, passwordMaxLength: 128 }
SecurityEvent { id: int, occurredAt: datetime, type: string, outcome: "ok"|"denied",
                actorKind: string, actorUserId: uuid|null, actorName: string|null,
                subjectUserId: uuid|null, subjectName: string|null, ip: string|null,
                details: object }
Page<T>       { items: T[], nextCursor: string|null }
```

## Público (sem Bearer)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/health` | – | `{status, db, redis}` | 503 degraded |
| `GET /api/config` | – | `AppConfig` | – |
| `POST /api/auth/login` | `{email, password}` | `AuthSession` + `Set-Cookie sociman_rt` | 401 `invalid_credentials` (mesma resposta para e-mail inexistente ou senha errada); 403 `email_not_verified`; 429 |
| `POST /api/auth/refresh` | – (cookie) | `AuthSession` + cookie rotacionado | 401 `invalid_token` + cookie apagado (ausente, expirado, reuso ou usuário inativo) |
| `POST /api/auth/logout` | – (Bearer opcional, mesmo expirado) | `Ok` + cookie apagado | – |
| `POST /api/auth/password/forgot` | `{email}` | `Ok` (sempre) | 429 |
| `POST /api/auth/password/reset` | `{token, newPassword}` | `Ok`; encerra todas as sessões; zera `mustChangePassword` | 400 `invalid_token`, 400 `validation_error`; 429 |
| `POST /api/auth/verify-email` | `{token}` | `Ok` | 400 `invalid_token`; 429 |
| `POST /api/auth/verify-email/resend` | `{email}` | `Ok` (sempre, sem revelar nada) | 429 |

**Removidos do volans:** `POST /api/auth/register` (FR-012) e `POST /api/consent`.

## Autenticado (qualquer papel)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/auth/me` | – | `{user: User}` | 401 |
| `POST /api/auth/password/change` | `{currentPassword, newPassword}` | `AuthSession` (a sessão atual continua, as outras são encerradas, `mustChangePassword` volta a false) | 400 `invalid_credentials` (senha atual errada), 400 `validation_error` (senha fraca ou igual à atual); 429 |

## Só dono (`require_owner` → 403 `forbidden`)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/users` | – | `{items: User[]}` (inclui inativos) | |
| `POST /api/users` | `{name, email, role, provisionalPassword}` | `{user: User, emailSent: bool}` | 409 `email_in_use`; 400 |
| `PATCH /api/users/{id}` | `{name?, email?, role?, isActive?}` | `{user: User, emailSent: bool\|null}` | 404; 409 `email_in_use`; 409 `last_owner` (rebaixar ou desativar o último dono ativo) |
| `POST /api/users/{id}/password` | `{provisionalPassword}` | `{user: User}`; encerra as sessões do usuário | 404; 400 |
| `POST /api/users/{id}/verification` | – | `{emailSent: bool}` | 404; 409 se já estiver verificado |
| `GET /api/security-events` | query `userId?`, `type?`, `from?`, `to?`, `cursor?`, `limit?` (1..100, padrão 50) | `Page<SecurityEvent>`, do mais recente para o mais antigo | 400 |

**Efeitos colaterais de `PATCH`:**
- `email` alterado: `emailVerified` volta a false, um link é enviado para o novo e-mail e as sessões
  são encerradas;
- `isActive=false`: as sessões são encerradas;
- `role` alterado: gera o evento `role_changed` com o antes e o depois.

Toda mutação grava `updated_by` e um `security_event`.

## Rotas do SPA
| Rota | Estado |
|---|---|
| `/login` | existente; ganha o link "reenviar verificação" quando a resposta é 403 `email_not_verified` |
| `/forgot-password`, `/reset-password?token=` | existentes |
| `/verify-email?token=` | existente; depois de confirmar, mostra "E-mail confirmado, faça login" (não cria sessão) |
| `/trocar-senha` | nova; obrigatória quando `mustChangePassword` |
| `/app/conta` | nova; troca de senha voluntária e "quem sou eu" |
| `/app/usuarios` | nova, só dono: listar, criar, editar, senha provisória e reenviar verificação |
| `/app/seguranca` | nova, só dono: eventos de segurança com filtros |
| `/register` | removida |

## CLI (`sociman`, dentro do container `api`)
| Comando | Efeito |
|---|---|
| `sociman create-owner --email E --name N` | pede a senha (oculta, duas vezes) e cria um dono verificado, sem troca obrigatória; recusa se já houver dono ativo (salvo `--force`) |
| `sociman set-password --email E` | redefine a senha em emergência, encerra as sessões e zera `mustChangePassword` |
| `sociman reset-db --yes` | só com `ENV != production`: `TRUNCATE` das tabelas e `FLUSHDB` (e2e) |
