# Arquitetura — Segurança

Segurança é o produto, não uma feature. Os itens [NÃO-NEGOCIÁVEL] do brief (§6)
são obrigatórios. Este é o modelo, item a item, com os arquivos.

## Checklist do brief (§6)

| # | Item | Onde |
|---|---|---|
| 1 | **Hash edge-compatible**: Argon2id via WASM (`hash-wasm`, m=19456 KiB, t=2, p=1 — OWASP). Fallback PBKDF2-SHA256/WebCrypto (600k iter) via `PASSWORD_HASH=pbkdf2`. PHC string; `verify` despacha pelo **prefixo do hash** → trocar de algoritmo não quebra contas antigas. | `services/passwordService.ts` |
| 2 | **Access só em memória**, TTL ~15min — nunca em localStorage. | `apps/web/src/lib/authStore.ts` |
| 3 | **Refresh** em cookie `httpOnly; Secure; SameSite=Strict; Path=/api/auth/refresh`, rotação a cada uso + detecção de reuso + revogação no KV. | `services/tokenService.ts`, `handlers/http.ts` |
| 4 | **CSP estrita** sem `unsafe-inline` em produção (o build do Vite não emite script inline). Servida pela borda. | `apps/web/vite.config.ts`, nginx/Rules Engine |
| 5 | **Rate limit** em login/register/forgot/reset/verify/consent, por IP e por conta, fixed-window no KV. | `lib/rateLimit.ts` |
| 6 | **Sem enumeração**: `forgot` sempre 200; `login` erro genérico + **verificação de hash fantasma** para igualar timing. | `handlers/auth.ts` |
| 7 | **CSRF**: API é Bearer (imune); o único cookie é `SameSite=Strict` + path-scoped ao refresh. Sem CORS (cross-origin bloqueado por default). | — |
| 8 | **Zod** em toda entrada; e-mail lowercase/trim; senha mín. 8 (`PASSWORD_MIN_LENGTH`) + blocklist das óbvias. | `packages/contract/src/` |
| 9 | **Zero segredo no bundle** do front — checado por `npm run check:bundle`. | `scripts/check-bundle.mjs` |
| 10 | **Tokens de reset/verificação**: 256-bit aleatórios, guardados só como **SHA-256**, single-use, TTL curto. | `handlers/auth.ts`, `db/schema.ts` |

## Headers de segurança

- **API** (`lib/securityHeaders.ts`): `Content-Security-Policy: default-src 'none'`,
  HSTS `max-age=63072000; includeSubDomains`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store`.
- **SPA** (borda): CSP estrita `default-src 'self'; script-src 'self'; style-src
  'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';
  base-uri 'none'; object-src 'none'; form-action 'self'` + HSTS + XCTO + Referrer.
- **Anti-drift**: `npm run check:csp` garante que a CSP estrita bate entre
  `vite.config.ts` e o nginx do edge.

## Hardening da sessão (decisões desta fase)

- **Segredos em Azion Variables**: `JWT_SECRET`, `AZION_SQL_TOKEN`,
  `RESEND_API_KEY` como secrets no painel, lidos por `Azion.env.get()` — nunca em
  texto plano nos `function_args`, nunca no repo. Ver [`../config/secrets.md`](../config/secrets.md).
- **JWT com `iss`/`aud`**: dois apps Volans com o mesmo secret por engano NÃO
  aceitam tokens um do outro. `clockTolerance` de 30s cobre skew entre instâncias
  de borda.
- **Sessão viva** (`authenticate`): revogação (logout/reset) é efetiva na hora,
  não em até `ACCESS_TTL`.
- **Defesa de SQL injection testada**: o driver da borda inlina parâmetros
  (o bind nativo está quebrado — ver [`edge-azion.md`](edge-azion.md)); a barreira
  de escaping vive em `lib/sqlInline.ts` (módulo puro) e é travada por 8 testes
  (aspas dobradas, payloads inertes, tipos rejeitados). As entradas já passaram
  por Zod — isto é defesa em profundidade.
- **Guardrail `check:secrets`**: trava no CI que impede qualquer chave (padrões
  de token Azion/Resend/AWS/PEM) em arquivo rastreado pelo git.

## Limitações conhecidas (leia antes de "melhorar")

- **XSS pode usar a sessão** (não roubá-la): um script injetado consegue chamar
  `/api/auth/refresh` same-origin e receber um access token. O cookie httpOnly
  impede o roubo do refresh; a **CSP estrita é a defesa real** contra a injeção —
  por isso ela é inegociável.
- **Rotação de refresh não é transacional** no KV (get→set): rotações
  concorrentes têm uma race rara em que um token legítimo é tratado como reuso →
  re-login forçado (não vazamento). A janela de graça cobre os casos comuns; a
  versão robusta é CAS/Lua no KV nativo.
- **Sem CORS de propósito**: a API não emite headers CORS → cross-origin
  bloqueado. Não "conserte" isso.
- **Rate limit best-effort**: fixed-window com possível supercount sob
  concorrência (direção segura). Na Azion, reforçado pelo Edge Firewall.
- **WAF em modo logging no dia 1**: ver [ADR 0011](../decisions/0011-waf-edge-firewall-logging.md).
  WAF inspeciona `/api/*` (SQLi, XSS, RFI, LFI, evading tricks) e loga em RTE,
  mas **não bloqueia** até virar `blocking` via `terraform apply -var waf_mode=blocking`.
  Antes de flipar: revisar Real-Time Events por false-positives (senhas com
  aspa disparam `sql_injection` fácil), calibrar sensibilidade por threat.

## Pendências de segurança (ação humana)

Registradas em [`../../PRODUCTION.md`](../../PRODUCTION.md): rotacionar o
`AZION_SQL_TOKEN` (hoje token de conta inteiro, foi exposto) para um escopado, e
trocar a key do Resend por uma sending-only.
