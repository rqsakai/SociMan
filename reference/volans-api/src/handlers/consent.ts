import { consentRequestSchema } from "@volans/contract";
import { consentRecords } from "../db/schema";
import { checkRateLimit } from "../lib/rateLimit";
import { authenticate } from "./auth";
import type { HandlerDeps } from "./deps";
import { getClientIp, json, parseBody, rateLimitedResponse } from "./http";

export async function handleConsent(req: Request, deps: HandlerDeps): Promise<Response> {
  const body = await parseBody(req, consentRequestSchema);
  if (!body.ok) return body.response;

  // Cada consent grava uma linha de auditoria — escrita em SQL é um dos 4
  // limites do modelo de custo, então flood anônimo precisa de teto aqui
  // mesmo com o rate limit volumétrico do edge na frente.
  const ip = getClientIp(req, deps.env.TRUSTED_PROXY);
  const limit = await checkRateLimit(deps.kv, "consent", { ip });
  if (limit.limited) return rateLimitedResponse(limit.retryAfterSeconds);

  // Se vier autenticado (com sessão viva), amarra o registro ao usuário;
  // senão fica só o anon_id.
  const claims = await authenticate(req, deps);

  await deps.db.insert(consentRecords).values({
    id: crypto.randomUUID(),
    userId: claims?.userId ?? null,
    anonId: body.data.anonId ?? null,
    categories: JSON.stringify(body.data.categories),
    policyVersion: body.data.policyVersion,
    ip,
    userAgent: req.headers.get("user-agent"),
    createdAt: new Date(),
  });

  return json({ ok: true });
}
