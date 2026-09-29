import type { HandlerDeps } from "./deps";
import { json } from "./http";

// Config PÚBLICA do app: espelha para o front os valores [config] que ele
// precisa validar igual ao servidor (política de senha, versão da política de
// consentimento) — sem isso o browser valida com defaults e divergiria do
// backend configurado. NADA sensível pode entrar aqui: o endpoint é aberto.
// Cache público de 5 min: o valor só muda em redeploy, e cada hit evitado é
// compute economizado na borda (compute é custo — modelo do produto).
export async function handleConfig(_req: Request, deps: HandlerDeps): Promise<Response> {
  return json(
    {
      passwordMinLength: deps.env.PASSWORD_MIN_LENGTH,
      consentPolicyVersion: deps.env.CONSENT_POLICY_VERSION,
    },
    { headers: { "Cache-Control": "public, max-age=300" } },
  );
}
