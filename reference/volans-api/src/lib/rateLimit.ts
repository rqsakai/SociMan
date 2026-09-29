import type { KV } from "./kv";

// Rate limit fixed-window no KV (§6.5), por IP e (quando fizer sentido) por
// conta. No runtime real da Azion isto é reforçado pelo Edge Firewall — este
// módulo garante que o app fica seguro sozinho (regra de portabilidade).

export type RateLimitedAction = "login" | "register" | "forgot" | "reset" | "consent" | "verify";

interface ActionLimits {
  windowSeconds: number;
  maxPerIp: number;
  maxPerAccount?: number;
}

export const rateLimits: Record<RateLimitedAction, ActionLimits> = {
  login: { windowSeconds: 15 * 60, maxPerIp: 30, maxPerAccount: 10 },
  register: { windowSeconds: 60 * 60, maxPerIp: 10 },
  forgot: { windowSeconds: 60 * 60, maxPerIp: 10, maxPerAccount: 5 },
  reset: { windowSeconds: 60 * 60, maxPerIp: 10 },
  // Escrita em SQL e compute são limites do modelo de custo (§A do brief):
  // consent grava linha de auditoria por request; verify custa hash+query.
  consent: { windowSeconds: 60 * 60, maxPerIp: 20 },
  verify: { windowSeconds: 60 * 60, maxPerIp: 30 },
};

export interface RateLimitResult {
  limited: boolean;
  retryAfterSeconds: number;
}

export async function checkRateLimit(
  kv: KV,
  action: RateLimitedAction,
  identifiers: { ip: string; account?: string },
): Promise<RateLimitResult> {
  const limits = rateLimits[action];
  const bucket = Math.floor(Date.now() / (limits.windowSeconds * 1000));
  const checkAccount = identifiers.account !== undefined && limits.maxPerAccount !== undefined;

  // Os contadores de IP e de conta são independentes — dispara os dois incrs em
  // PARALELO. Na borda cada incr é um round-trip ao Edge SQL (~2s); em série
  // dobrava a latência do login. Ambos são incrementados mesmo que um já
  // estoure — inconsequente para rate limit (o efeito é só contar +1 a mais).
  const [ipCount, accountCount] = await Promise.all([
    kv.incr(`rl:${action}:ip:${bucket}:${identifiers.ip}`, { ttlSeconds: limits.windowSeconds }),
    checkAccount
      ? kv.incr(`rl:${action}:acct:${bucket}:${identifiers.account}`, {
          ttlSeconds: limits.windowSeconds,
        })
      : Promise.resolve(0),
  ]);

  if (ipCount > limits.maxPerIp) {
    return { limited: true, retryAfterSeconds: limits.windowSeconds };
  }
  if (checkAccount && accountCount > limits.maxPerAccount!) {
    return { limited: true, retryAfterSeconds: limits.windowSeconds };
  }

  return { limited: false, retryAfterSeconds: 0 };
}
