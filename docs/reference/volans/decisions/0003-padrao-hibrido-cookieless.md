# ADR 0003 — Sessão híbrida cookieless (access em memória + refresh em cookie)

**Status:** Aceita

## Contexto

Precisamos de sessão segura sem depender de servidor de sessão pesado, resistente
a XSS (roubo de token) e a CSRF. O design doc (§8.8-B) define o padrão híbrido.

## Decisão

- **Access token**: JWT HS256 curto (`ACCESS_TTL`, 15 min), entregue no body e
  guardado **só em memória** no front (store Zustand, sem `persist`). Nunca em
  localStorage. Carrega claims `sub`, `fam` (familyId), `iss`, `aud`.
- **Refresh token**: **opaco** (`familyId.segredo-256-bit`), no **único cookie**
  do app: `httpOnly; Secure; SameSite=Strict; Path=/api/auth/refresh`. O KV
  guarda só o SHA-256 do token corrente da família.
- **Claim `fam` no access token**: o cookie é path-scoped e **não chega** em
  `/api/auth/logout` — o logout revoga a família pela claim `fam` (aceita JWT
  expirado com assinatura válida; revogação é benigna).
- **CSRF**: a API é Bearer (imune); o único cookie é `SameSite=Strict` e
  path-scoped ao refresh. Sem CSRF token adicional porque não há superfície.

## Consequências

> **Nota do SociMan (2026-09-29):** no SociMan, apenas o `script-src` segue estrito; o `style-src` permite `'unsafe-inline'`. Ver [ADR 0001 do SociMan](../../../adr/0001-ui-shadcn-tanstack-csp-styles.md).

- Access morre no reload; a sessão é restaurada pelo refresh no boot do app.
- XSS não *rouba* o refresh (httpOnly), mas pode *usá-lo* same-origin — por isso
  a CSP estrita é inegociável (ver [../architecture/security.md](../architecture/security.md)).
- Rotação e detecção de reuso: ver [0004](0004-janela-graca-refresh.md).
- Implementação: `apps/api/src/services/tokenService.ts`.
