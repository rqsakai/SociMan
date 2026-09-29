# Escopo e defaults de produto

## Dentro do escopo

- **Cadastro** (registro com hash de senha, dispara verificação de e-mail).
- **Login** (erro genérico, sem enumeração, rate-limited).
- **Logout** (revoga a família de refresh).
- **Recuperação de senha** (pedir + redefinir; sem enumeração de usuário).
- **Verificação de e-mail** (token single-use, TTL curto).
- **Sessão via JWT** — padrão híbrido cookieless: access curto em memória +
  refresh opaco em cookie httpOnly path-scoped. Ver
  [../architecture/auth-flow.md](../architecture/auth-flow.md).
- **Banner de consentimento LGPD** (essencial informado; não-essencial off por
  default; auditoria em `consent_records`).
- **Rota protegida de exemplo** (`/app`).
- **Tailwind** como estilo padrão, com tokens de tema neutro.

## Fora do escopo (não fazer agora)

- Login social / **OAuth**.
- **MFA / 2FA**.
- **Magic link**.
- **Papéis / organizações / multi-tenant**.
- O app em si além do esqueleto.
- **i18n** além de pt-BR default.
- **SSR** — este starter é **100% SPA/CSR** (é app atrás de login).

## Defaults de produto (§12 do brief)

Pontos de ajuste marcados: `[config]` = variável de ambiente; `[decisão]` = ponto
que o sócio/cliente pode querer mudar.

| Item | Default | Tipo |
|---|---|---|
| Verificação de e-mail | **Obrigatória para login** | `[decisão]` |
| Hash de senha | **Argon2id** (WASM); PBKDF2 alternativo | `[decisão]` |
| TTL do access token | **15 min** | `[config]` `ACCESS_TTL` |
| TTL do refresh token | **7 dias** | `[config]` `REFRESH_TTL` |
| Janela de graça do refresh | **60s** | `[config]` `REFRESH_GRACE` |
| Política de senha | mín. 8 + blocklist | `[config]` `PASSWORD_MIN_LENGTH` |
| Provider de e-mail | stub (dev) → Resend (prod, BYOK) | `[config]` `EMAIL_PROVIDER` |

Detalhes de cada decisão em [../decisions/](../decisions/). Todas as variáveis em
[../config/environment.md](../config/environment.md).

## Definition of Done (do brief)

Cadastro → verificação → login → rota protegida → refresh no reload → logout →
esqueci a senha → redefinir, tudo funcionando; segurança da §6 verificada;
access só em memória; refresh só em cookie path-scoped; forgot sem enumeração;
rate-limit ativo; reuso de refresh revoga a família (testado); CSP estrita ativa;
banner LGPD; testes unit/integração/e2e; zero segredo no bundle.
