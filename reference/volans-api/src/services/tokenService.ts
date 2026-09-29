import { SignJWT, jwtVerify } from "jose";
import { constantTimeEqual, randomToken, sha256Hex } from "../lib/crypto";
import type { KV } from "../lib/kv";

// Padrão híbrido cookieless (§8.8-B do design doc):
// - access token: JWT HS256 curto, entregue no body e mantido só em memória no front.
//   Carrega a claim `fam` (familyId) porque o cookie de refresh é path-scoped a
//   /api/auth/refresh e NÃO chega em /api/auth/logout — o logout revoga pela claim.
// - refresh token: OPACO, formato `${familyId}.${secret 256-bit}`. O KV guarda
//   apenas o SHA-256 do token corrente da família. Rotação a cada uso; token
//   antigo apresentado com a família viva = reuso → revoga a família inteira.
// - janela de graça (graceSeconds): o token da geração IMEDIATAMENTE anterior é
//   aceito por alguns segundos após a rotação. Sem isso, uma navegação que
//   aborta a resposta do refresh (Set-Cookie novo se perde) deixa o navegador
//   com o cookie antigo e o próximo load seria tratado como "ataque",
//   derrubando um usuário legítimo. Tokens de 2+ gerações atrás, ou fora da
//   janela, continuam revogando a família inteira.
// - expiração da família é ABSOLUTA (rotação não estende os REFRESH_TTL segundos).

export interface TokenServiceConfig {
  jwtSecret: string;
  accessTtlSeconds: number;
  refreshTtlSeconds: number;
  graceSeconds: number;
  // claim `aud` — nome do app. Dois apps Volans que compartilhem secret por
  // engano não aceitam tokens um do outro (defense in depth, custo zero).
  audience: string;
}

const ISSUER = "volans-auth";

// Skew de relógio tolerado entre instâncias de borda ao validar `exp`:
// um token recém-emitido por um nó ligeiramente adiantado não pode ser
// rejeitado pelos vizinhos. 30s é o padrão conservador da indústria.
const CLOCK_TOLERANCE_SECONDS = 30;

export interface AccessTokenClaims {
  userId: string;
  familyId: string;
}

interface RefreshFamily {
  userId: string;
  tokenHash: string;
  prevTokenHash: string | null;
  prevExpiresAt: number | null; // fim da janela de graça do token anterior (epoch ms)
  expiresAt: number; // epoch ms
}

export type RotateResult =
  | { ok: true; userId: string; familyId: string; accessToken: string; refreshToken: string }
  | { ok: false; reason: "invalid" | "reused" };

const familyKey = (familyId: string) => `rt:${familyId}`;
const userFamiliesKey = (userId: string) => `uf:${userId}`;

export function createTokenService(kv: KV, config: TokenServiceConfig) {
  const secret = new TextEncoder().encode(config.jwtSecret);

  async function signAccessToken(claims: AccessTokenClaims): Promise<string> {
    const nowS = Math.floor(Date.now() / 1000);
    return new SignJWT({ fam: claims.familyId })
      .setProtectedHeader({ alg: "HS256" })
      .setSubject(claims.userId)
      .setIssuer(ISSUER)
      .setAudience(config.audience)
      .setIssuedAt(nowS)
      .setExpirationTime(nowS + config.accessTtlSeconds)
      .sign(secret);
  }

  // `ignoreExpiration` existe SÓ para o logout: um access expirado (mas com
  // assinatura válida) ainda identifica a família a revogar — operação benigna.
  async function verifyAccessToken(
    token: string,
    opts?: { ignoreExpiration?: boolean },
  ): Promise<AccessTokenClaims | null> {
    try {
      const { payload } = await jwtVerify(token, secret, {
        algorithms: ["HS256"],
        issuer: ISSUER,
        audience: config.audience,
        clockTolerance: opts?.ignoreExpiration ? config.refreshTtlSeconds : CLOCK_TOLERANCE_SECONDS,
      });
      if (typeof payload.sub !== "string" || typeof payload.fam !== "string") return null;
      return { userId: payload.sub, familyId: payload.fam };
    } catch {
      return null;
    }
  }

  async function addFamilyToUserIndex(userId: string, familyId: string): Promise<void> {
    const families = (await kv.get<string[]>(userFamiliesKey(userId))) ?? [];
    if (!families.includes(familyId)) families.push(familyId);
    // Índice para "revogar todas as sessões" (reset de senha). Entradas velhas
    // expiram sozinhas no rt:*; ids obsoletos aqui são tolerados. A escrita
    // read-modify-write tem uma race benigna entre logins simultâneos — o pior
    // caso é um id obsoleto a mais na lista, nunca uma sessão órfã de revogação
    // "esquecida" com dados válidos.
    await kv.set(userFamiliesKey(userId), families, { ttlSeconds: config.refreshTtlSeconds });
  }

  async function removeFamilyFromUserIndex(userId: string, familyId: string): Promise<void> {
    const families = (await kv.get<string[]>(userFamiliesKey(userId))) ?? [];
    const remaining = families.filter((id) => id !== familyId);
    if (remaining.length === 0) {
      await kv.delete(userFamiliesKey(userId));
    } else {
      await kv.set(userFamiliesKey(userId), remaining, { ttlSeconds: config.refreshTtlSeconds });
    }
  }

  async function createSession(userId: string) {
    const familyId = crypto.randomUUID();
    const refreshToken = `${familyId}.${randomToken()}`;
    const expiresAt = Date.now() + config.refreshTtlSeconds * 1000;
    const family: RefreshFamily = {
      userId,
      tokenHash: await sha256Hex(refreshToken),
      prevTokenHash: null,
      prevExpiresAt: null,
      expiresAt,
    };
    await kv.set(familyKey(familyId), family, { ttlSeconds: config.refreshTtlSeconds });
    await addFamilyToUserIndex(userId, familyId);
    const accessToken = await signAccessToken({ userId, familyId });
    return { accessToken, refreshToken, familyId };
  }

  async function revokeFamily(familyId: string): Promise<void> {
    const family = await kv.get<RefreshFamily>(familyKey(familyId));
    await kv.delete(familyKey(familyId));
    if (family) await removeFamilyFromUserIndex(family.userId, familyId);
  }

  async function rotateRefresh(refreshToken: string): Promise<RotateResult> {
    const separator = refreshToken.indexOf(".");
    if (separator <= 0) return { ok: false, reason: "invalid" };
    const familyId = refreshToken.slice(0, separator);

    const family = await kv.get<RefreshFamily>(familyKey(familyId));
    if (!family) return { ok: false, reason: "invalid" };

    const now = Date.now();
    const presentedHash = await sha256Hex(refreshToken);
    const isCurrent = constantTimeEqual(presentedHash, family.tokenHash);
    const isPrevInGrace =
      !isCurrent &&
      family.prevTokenHash !== null &&
      family.prevExpiresAt !== null &&
      now < family.prevExpiresAt &&
      constantTimeEqual(presentedHash, family.prevTokenHash);

    if (!isCurrent && !isPrevInGrace) {
      // Reuso detectado: um token já rotacionado (fora da janela de graça) foi
      // apresentado enquanto a família vive → alguém tem uma cópia. Revoga tudo.
      await revokeFamily(familyId);
      return { ok: false, reason: "reused" };
    }

    const remainingSeconds = Math.ceil((family.expiresAt - now) / 1000);
    if (remainingSeconds <= 0) {
      await revokeFamily(familyId);
      return { ok: false, reason: "invalid" };
    }

    const nextToken = `${familyId}.${randomToken()}`;
    const rotated: RefreshFamily = {
      userId: family.userId,
      tokenHash: await sha256Hex(nextToken),
      // rotação normal abre a janela de graça para o token que acabou de ser
      // usado; rotação via graça NÃO estende a janela original
      prevTokenHash: isCurrent ? presentedHash : family.prevTokenHash,
      prevExpiresAt: isCurrent ? now + config.graceSeconds * 1000 : family.prevExpiresAt,
      expiresAt: family.expiresAt,
    };
    await kv.set(familyKey(familyId), rotated, { ttlSeconds: remainingSeconds });
    const accessToken = await signAccessToken({ userId: family.userId, familyId });
    return { ok: true, userId: family.userId, familyId, accessToken, refreshToken: nextToken };
  }

  // Sessão "viva" = família ainda existe no KV. Endpoints autenticados checam
  // isto além da assinatura do JWT (ver authenticate em handlers/auth.ts).
  async function isFamilyAlive(familyId: string): Promise<boolean> {
    return (await kv.get(familyKey(familyId))) !== null;
  }

  async function revokeAllForUser(userId: string): Promise<void> {
    const families = (await kv.get<string[]>(userFamiliesKey(userId))) ?? [];
    for (const familyId of families) {
      await kv.delete(familyKey(familyId));
    }
    await kv.delete(userFamiliesKey(userId));
  }

  return {
    signAccessToken,
    verifyAccessToken,
    createSession,
    rotateRefresh,
    revokeFamily,
    revokeAllForUser,
    isFamilyAlive,
  };
}

export type TokenService = ReturnType<typeof createTokenService>;
