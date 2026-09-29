import { and, eq, gt, isNull } from "drizzle-orm";
import {
  forgotPasswordRequestSchema,
  loginRequestSchema,
  registerRequestSchema,
  resetPasswordRequestSchema,
  verifyEmailRequestSchema,
  type User,
} from "@volans/contract";
import { emailVerificationTokens, passwordResetTokens, users } from "../db/schema";
import { randomToken, sha256Hex } from "../lib/crypto";
import { checkRateLimit } from "../lib/rateLimit";
import type { PasswordService } from "../services/passwordService";
import type { AccessTokenClaims } from "../services/tokenService";
import type { HandlerDeps } from "./deps";
import {
  buildRefreshCookie,
  clearRefreshCookie,
  errorResponse,
  getBearerToken,
  getClientIp,
  json,
  parseBody,
  rateLimitedResponse,
  readRefreshCookie,
} from "./http";

type UserRow = typeof users.$inferSelect;

function toApiUser(row: UserRow): User {
  return {
    id: row.id,
    name: row.name,
    email: row.email,
    emailVerified: row.emailVerified,
    createdAt: row.createdAt.toISOString(),
  };
}

async function sessionResponse(deps: HandlerDeps, user: UserRow): Promise<Response> {
  const session = await deps.tokens.createSession(user.id);
  return json(
    { accessToken: session.accessToken, user: toApiUser(user) },
    { headers: { "Set-Cookie": buildRefreshCookie(session.refreshToken, deps.env.REFRESH_TTL) } },
  );
}

// Verificação "fantasma" quando o e-mail não existe: iguala o tempo de resposta
// do login com e sem usuário, fechando o canal de timing para enumeração.
const dummyHashCache = new WeakMap<PasswordService, Promise<string>>();
async function equalizeTiming(passwords: PasswordService): Promise<void> {
  let dummy = dummyHashCache.get(passwords);
  if (!dummy) {
    dummy = passwords.hash(`dummy-${randomToken()}`);
    dummyHashCache.set(passwords, dummy);
  }
  await passwords.verify("senha-fantasma", await dummy);
}

async function findUserByEmail(deps: HandlerDeps, email: string): Promise<UserRow | undefined> {
  return deps.db.query.users.findFirst({ where: eq(users.email, email) });
}

// Autenticação com checagem de SESSÃO VIVA: além de assinatura/expiração do
// JWT, a família de refresh (claim `fam`) precisa existir no KV. Logout e —
// crucialmente — reset de senha (conta possivelmente comprometida) revogam a
// família; sem esta checagem, um access token roubado continuaria valendo por
// até ACCESS_TTL depois da revogação. O preço é 1 leitura de KV por request.
export async function authenticate(
  req: Request,
  deps: HandlerDeps,
): Promise<AccessTokenClaims | null> {
  const accessToken = getBearerToken(req);
  if (!accessToken) return null;
  const claims = await deps.tokens.verifyAccessToken(accessToken);
  if (!claims) return null;
  if (!(await deps.tokens.isFamilyAlive(claims.familyId))) return null;
  return claims;
}

export async function handleRegister(req: Request, deps: HandlerDeps): Promise<Response> {
  const body = await parseBody(req, registerRequestSchema);
  if (!body.ok) return body.response;

  const limit = await checkRateLimit(deps.kv, "register", { ip: getClientIp(req, deps.env.TRUSTED_PROXY) });
  if (limit.limited) return rateLimitedResponse(limit.retryAfterSeconds);

  if (body.data.password.length < deps.env.PASSWORD_MIN_LENGTH) {
    return errorResponse(
      400,
      "validation_error",
      `A senha precisa ter pelo menos ${deps.env.PASSWORD_MIN_LENGTH} caracteres`,
    );
  }

  const existing = await findUserByEmail(deps, body.data.email);
  if (existing) {
    return errorResponse(409, "email_in_use", "Este e-mail já está cadastrado");
  }

  const now = new Date();
  const user: UserRow = {
    id: crypto.randomUUID(),
    name: body.data.name ?? null,
    email: body.data.email,
    passwordHash: await deps.passwords.hash(body.data.password),
    emailVerified: false,
    createdAt: now,
    updatedAt: now,
  };
  await deps.db.insert(users).values(user);

  await sendVerificationEmail(deps, user);

  return sessionResponse(deps, user);
}

async function sendVerificationEmail(deps: HandlerDeps, user: UserRow): Promise<void> {
  const token = randomToken();
  await deps.db.insert(emailVerificationTokens).values({
    tokenHash: await sha256Hex(token),
    userId: user.id,
    expiresAt: new Date(Date.now() + deps.env.VERIFY_TOKEN_TTL * 1000),
  });
  await deps.email.sendVerificationEmail(
    user.email,
    `${deps.env.APP_URL}/verify-email?token=${token}`,
  );
}

export async function handleLogin(req: Request, deps: HandlerDeps): Promise<Response> {
  const body = await parseBody(req, loginRequestSchema);
  if (!body.ok) return body.response;

  const limit = await checkRateLimit(deps.kv, "login", {
    ip: getClientIp(req, deps.env.TRUSTED_PROXY),
    account: body.data.email,
  });
  if (limit.limited) return rateLimitedResponse(limit.retryAfterSeconds);

  const user = await findUserByEmail(deps, body.data.email);
  if (!user) {
    await equalizeTiming(deps.passwords);
    // Erro genérico (§6.6): não revela se o e-mail existe.
    return errorResponse(401, "invalid_credentials", "E-mail ou senha incorretos");
  }

  const valid = await deps.passwords.verify(body.data.password, user.passwordHash);
  if (!valid) {
    return errorResponse(401, "invalid_credentials", "E-mail ou senha incorretos");
  }

  if (!user.emailVerified) {
    // Só chega aqui com a senha correta — dizer "verifique o e-mail" não abre
    // enumeração. Default do brief: verificação obrigatória para login (§12).
    return errorResponse(403, "email_not_verified", "Confirme seu e-mail antes de entrar");
  }

  return sessionResponse(deps, user);
}

export async function handleRefresh(req: Request, deps: HandlerDeps): Promise<Response> {
  const refreshToken = readRefreshCookie(req);
  if (!refreshToken) {
    return errorResponse(401, "invalid_token", "Sessão ausente");
  }

  const rotated = await deps.tokens.rotateRefresh(refreshToken);
  if (!rotated.ok) {
    return errorResponse(401, "invalid_token", "Sessão expirada ou revogada — entre novamente", {
      "Set-Cookie": clearRefreshCookie(),
    });
  }

  const user = await deps.db.query.users.findFirst({ where: eq(users.id, rotated.userId) });
  if (!user) {
    await deps.tokens.revokeFamily(rotated.familyId);
    return errorResponse(401, "invalid_token", "Sessão inválida", {
      "Set-Cookie": clearRefreshCookie(),
    });
  }

  return json(
    { accessToken: rotated.accessToken, user: toApiUser(user) },
    { headers: { "Set-Cookie": buildRefreshCookie(rotated.refreshToken, deps.env.REFRESH_TTL) } },
  );
}

export async function handleLogout(req: Request, deps: HandlerDeps): Promise<Response> {
  // O cookie é path-scoped a /api/auth/refresh e não chega aqui; a família vem
  // da claim `fam` do access token — aceito mesmo expirado (revogação é benigna).
  const accessToken = getBearerToken(req);
  if (accessToken) {
    const claims = await deps.tokens.verifyAccessToken(accessToken, { ignoreExpiration: true });
    if (claims) await deps.tokens.revokeFamily(claims.familyId);
  }
  return json({ ok: true }, { headers: { "Set-Cookie": clearRefreshCookie() } });
}

export async function handleForgotPassword(req: Request, deps: HandlerDeps): Promise<Response> {
  const body = await parseBody(req, forgotPasswordRequestSchema);
  if (!body.ok) return body.response;

  const limit = await checkRateLimit(deps.kv, "forgot", {
    ip: getClientIp(req, deps.env.TRUSTED_PROXY),
    account: body.data.email,
  });
  if (limit.limited) return rateLimitedResponse(limit.retryAfterSeconds);

  const user = await findUserByEmail(deps, body.data.email);
  if (user) {
    const token = randomToken();
    await deps.db.insert(passwordResetTokens).values({
      tokenHash: await sha256Hex(token),
      userId: user.id,
      expiresAt: new Date(Date.now() + deps.env.RESET_TOKEN_TTL * 1000),
      usedAt: null,
    });
    await deps.email.sendPasswordResetEmail(
      user.email,
      `${deps.env.APP_URL}/reset-password?token=${token}`,
    );
  }

  // Sempre 200 (§6.6): a resposta não revela se a conta existe.
  return json({ ok: true });
}

export async function handleResetPassword(req: Request, deps: HandlerDeps): Promise<Response> {
  const body = await parseBody(req, resetPasswordRequestSchema);
  if (!body.ok) return body.response;

  const limit = await checkRateLimit(deps.kv, "reset", { ip: getClientIp(req, deps.env.TRUSTED_PROXY) });
  if (limit.limited) return rateLimitedResponse(limit.retryAfterSeconds);

  if (body.data.newPassword.length < deps.env.PASSWORD_MIN_LENGTH) {
    return errorResponse(
      400,
      "validation_error",
      `A senha precisa ter pelo menos ${deps.env.PASSWORD_MIN_LENGTH} caracteres`,
    );
  }

  const tokenHash = await sha256Hex(body.data.token);
  const row = await deps.db.query.passwordResetTokens.findFirst({
    where: and(
      eq(passwordResetTokens.tokenHash, tokenHash),
      isNull(passwordResetTokens.usedAt),
      gt(passwordResetTokens.expiresAt, new Date()),
    ),
  });
  if (!row) {
    return errorResponse(400, "invalid_token", "Link inválido ou expirado — peça um novo");
  }

  await deps.db
    .update(passwordResetTokens)
    .set({ usedAt: new Date() })
    .where(eq(passwordResetTokens.tokenHash, tokenHash));
  await deps.db
    .update(users)
    .set({ passwordHash: await deps.passwords.hash(body.data.newPassword), updatedAt: new Date() })
    .where(eq(users.id, row.userId));

  // Troca de senha derruba TODAS as sessões do usuário (§5).
  await deps.tokens.revokeAllForUser(row.userId);

  return json({ ok: true });
}

export async function handleVerifyEmail(req: Request, deps: HandlerDeps): Promise<Response> {
  const body = await parseBody(req, verifyEmailRequestSchema);
  if (!body.ok) return body.response;

  const limit = await checkRateLimit(deps.kv, "verify", {
    ip: getClientIp(req, deps.env.TRUSTED_PROXY),
  });
  if (limit.limited) return rateLimitedResponse(limit.retryAfterSeconds);

  const tokenHash = await sha256Hex(body.data.token);
  const row = await deps.db.query.emailVerificationTokens.findFirst({
    where: and(
      eq(emailVerificationTokens.tokenHash, tokenHash),
      gt(emailVerificationTokens.expiresAt, new Date()),
    ),
  });
  if (!row) {
    return errorResponse(400, "invalid_token", "Link inválido ou expirado");
  }

  await deps.db
    .update(users)
    .set({ emailVerified: true, updatedAt: new Date() })
    .where(eq(users.id, row.userId));
  await deps.db
    .delete(emailVerificationTokens)
    .where(eq(emailVerificationTokens.tokenHash, tokenHash));

  return json({ ok: true });
}

export async function handleMe(req: Request, deps: HandlerDeps): Promise<Response> {
  const claims = await authenticate(req, deps);
  if (!claims) {
    return errorResponse(401, "unauthorized", "Não autenticado");
  }
  const user = await deps.db.query.users.findFirst({ where: eq(users.id, claims.userId) });
  if (!user) {
    return errorResponse(401, "unauthorized", "Não autenticado");
  }
  return json({ user: toApiUser(user) });
}
