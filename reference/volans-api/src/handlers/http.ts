import type { z } from "zod";
import type { ErrorCode } from "@volans/contract";

// Helpers HTTP dos handlers. Os handlers core são (Request, deps) => Response
// puros — sem Next internals — para serem testáveis direto no vitest.

export const REFRESH_COOKIE_NAME = "volans_rt";
export const REFRESH_COOKIE_PATH = "/api/auth/refresh";

export function json(data: unknown, init?: ResponseInit): Response {
  return Response.json(data, init);
}

export function errorResponse(
  status: number,
  code: ErrorCode,
  message: string,
  headers?: HeadersInit,
): Response {
  return Response.json({ error: { code, message } }, { status, headers });
}

export type ParsedBody<T> = { ok: true; data: T } | { ok: false; response: Response };

export async function parseBody<T>(req: Request, schema: z.ZodType<T>): Promise<ParsedBody<T>> {
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return { ok: false, response: errorResponse(400, "validation_error", "Corpo JSON inválido") };
  }
  const result = schema.safeParse(raw);
  if (!result.success) {
    const message = result.error.issues[0]?.message ?? "Entrada inválida";
    return { ok: false, response: errorResponse(400, "validation_error", message) };
  }
  return { ok: true, data: result.data };
}

// IP do cliente para rate limit/auditoria. X-Forwarded-For cru NUNCA é usado:
// qualquer cliente pode forjá-lo. Só o X-Real-IP reescrito por um proxy
// confiável (nginx do compose / edge da Azion) conta — e apenas quando
// TRUSTED_PROXY está ligado. Sem proxy, todo mundo é "local" (ok em dev).
export function getClientIp(req: Request, trustProxy: boolean): string {
  if (trustProxy) {
    const realIp = req.headers.get("x-real-ip")?.trim();
    if (realIp) return realIp;
  }
  return "local";
}

export function getBearerToken(req: Request): string | null {
  const header = req.headers.get("authorization");
  if (!header?.startsWith("Bearer ")) return null;
  return header.slice("Bearer ".length).trim() || null;
}

// O ÚNICO cookie do app (§6.3): httpOnly, Secure, SameSite=Strict e com Path
// restrito ao endpoint de refresh — nenhuma outra rota o recebe.
export function buildRefreshCookie(token: string, maxAgeSeconds: number): string {
  return [
    `${REFRESH_COOKIE_NAME}=${token}`,
    `Max-Age=${maxAgeSeconds}`,
    `Path=${REFRESH_COOKIE_PATH}`,
    "HttpOnly",
    "Secure",
    "SameSite=Strict",
  ].join("; ");
}

export function clearRefreshCookie(): string {
  return buildRefreshCookie("", 0);
}

export function readRefreshCookie(req: Request): string | null {
  const header = req.headers.get("cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === REFRESH_COOKIE_NAME) {
      const value = part.slice(eq + 1).trim();
      return value || null;
    }
  }
  return null;
}

export function rateLimitedResponse(retryAfterSeconds: number): Response {
  return Response.json(
    { error: { code: "rate_limited", message: "Muitas tentativas. Tente novamente mais tarde." } },
    { status: 429, headers: { "Retry-After": String(retryAfterSeconds) } },
  );
}
