# ADR 0005 — Segredos em Azion Variables (não em function args)

**Status:** Aceita

## Contexto

Na primeira versão do deploy, `JWT_SECRET` e `AZION_SQL_TOKEN` iam nos
`json_args` da edge function — **texto plano, legível por qualquer um com acesso
à conta**. O `AZION_SQL_TOKEN` é o token de conta inteiro (acesso total). Achado
crítico (S1/S2) do review de produção. O runtime Deno da Azion congela
`process.env` ("Cannot set on process.env").

## Decisão

- Segredos vivem como **Azion Variables (secret)**, lidos em runtime via
  **`Azion.env.get("NOME")`** — nunca nos args, nunca no repo.
- Na borda, `getEnv(source)` recebe uma fonte montada com os secrets do
  `Azion.env.get()` + a config não-sensível dos args.
- `JWT_SECRET` foi **rotacionado** (o anterior havia sido exposto). Rotação é
  quase transparente: o refresh é opaco (hash no KV, independe do JWT), então a
  sessão se re-emite no próximo refresh.
- Config **não-sensível** (VOLANS_ENV, APP_NAME, APP_URL, IDs) continua nos
  `function_args` do Terraform.

## Consequências

- Variables atuais: `JWT_SECRET`, `AZION_SQL_TOKEN`, `RESEND_API_KEY`.
- Guardrail `check:secrets` impede qualquer chave em arquivo rastreado.
- **Pendência de higiene**: o `AZION_SQL_TOKEN` ainda é o token de conta inteiro
  (deve ser rotacionado e escopado só para Edge SQL). Ver
  [../../PRODUCTION.md](../../PRODUCTION.md).
- Detalhes: [../config/secrets.md](../config/secrets.md).
