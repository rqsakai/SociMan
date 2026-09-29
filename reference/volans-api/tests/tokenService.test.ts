import { beforeEach, describe, expect, it } from "vitest";
import type { SqliteKV } from "../src/lib/kv";
import { createTokenService, type TokenService } from "../src/services/tokenService";
import { setupTestDb, testTokenConfig } from "./helpers";

let kv: SqliteKV;
let tokens: TokenService;

beforeEach(async () => {
  ({ kv } = await setupTestDb());
  tokens = createTokenService(kv, testTokenConfig);
});

describe("access token", () => {
  it("assina e verifica claims (sub + fam)", async () => {
    const jwt = await tokens.signAccessToken({ userId: "u1", familyId: "f1" });
    await expect(tokens.verifyAccessToken(jwt)).resolves.toEqual({ userId: "u1", familyId: "f1" });
  });

  it("rejeita token expirado (além da tolerância de skew de 30s)", async () => {
    const expired = createTokenService(kv, { ...testTokenConfig, accessTtlSeconds: -60 });
    const jwt = await expired.signAccessToken({ userId: "u1", familyId: "f1" });
    await expect(tokens.verifyAccessToken(jwt)).resolves.toBeNull();
  });

  it("aceita token dentro da tolerância de skew (exp há poucos segundos)", async () => {
    const justExpired = createTokenService(kv, { ...testTokenConfig, accessTtlSeconds: -5 });
    const jwt = await justExpired.signAccessToken({ userId: "u1", familyId: "f1" });
    await expect(tokens.verifyAccessToken(jwt)).resolves.toEqual({ userId: "u1", familyId: "f1" });
  });

  it("rejeita token assinado com outro segredo", async () => {
    const other = createTokenService(kv, { ...testTokenConfig, jwtSecret: "outro-segredo-outro-segredo-32ch" });
    const jwt = await other.signAccessToken({ userId: "u1", familyId: "f1" });
    await expect(tokens.verifyAccessToken(jwt)).resolves.toBeNull();
  });

  it("rejeita token de outro app (claim aud diferente, mesmo secret)", async () => {
    const otherApp = createTokenService(kv, { ...testTokenConfig, audience: "outro-app-volans" });
    const jwt = await otherApp.signAccessToken({ userId: "u1", familyId: "f1" });
    await expect(tokens.verifyAccessToken(jwt)).resolves.toBeNull();
  });
});

describe("refresh: rotação e detecção de reuso", () => {
  it("rotaciona o refresh e o novo token continua válido", async () => {
    const session = await tokens.createSession("u1");
    const first = await tokens.rotateRefresh(session.refreshToken);
    expect(first.ok).toBe(true);
    if (!first.ok) return;
    expect(first.userId).toBe("u1");
    expect(first.refreshToken).not.toBe(session.refreshToken);

    const second = await tokens.rotateRefresh(first.refreshToken);
    expect(second.ok).toBe(true);
  });

  it("reuso de refresh antigo revoga a família inteira", async () => {
    const session = await tokens.createSession("u1");
    const rotated = await tokens.rotateRefresh(session.refreshToken);
    expect(rotated.ok).toBe(true);
    if (!rotated.ok) return;

    // token antigo apresentado de novo → reuso
    const reuse = await tokens.rotateRefresh(session.refreshToken);
    expect(reuse).toEqual({ ok: false, reason: "reused" });

    // a família morreu: nem o token "legítimo" mais recente funciona
    const afterRevoke = await tokens.rotateRefresh(rotated.refreshToken);
    expect(afterRevoke).toEqual({ ok: false, reason: "invalid" });
  });

  it("com janela de graça, o token da geração anterior ainda funciona (resposta perdida)", async () => {
    const graceful = createTokenService(kv, { ...testTokenConfig, graceSeconds: 60 });
    const session = await graceful.createSession("u1");

    // rotação cujo Set-Cookie "se perdeu": o cliente continua com o token antigo
    const lost = await graceful.rotateRefresh(session.refreshToken);
    expect(lost.ok).toBe(true);

    // cliente reapresenta o token antigo dentro da graça → aceito, nova rotação
    const recovered = await graceful.rotateRefresh(session.refreshToken);
    expect(recovered.ok).toBe(true);

    // mas um token de 2+ gerações atrás continua sendo reuso → revoga tudo
    if (!lost.ok || !recovered.ok) return;
    const reuse = await graceful.rotateRefresh(session.refreshToken);
    // session.refreshToken segue sendo o prev em graça (rotação via graça não estende)
    expect(reuse.ok).toBe(true);
    const twoGenerationsOld = await graceful.rotateRefresh(lost.refreshToken);
    expect(twoGenerationsOld).toEqual({ ok: false, reason: "reused" });
  });

  it("refresh token malformado ou de família inexistente é inválido", async () => {
    await expect(tokens.rotateRefresh("sem-separador")).resolves.toEqual({ ok: false, reason: "invalid" });
    await expect(tokens.rotateRefresh("familia-fantasma.segredo")).resolves.toEqual({
      ok: false,
      reason: "invalid",
    });
  });
});

describe("revogação", () => {
  it("revokeFamily invalida a sessão", async () => {
    const session = await tokens.createSession("u1");
    await tokens.revokeFamily(session.familyId);
    await expect(tokens.rotateRefresh(session.refreshToken)).resolves.toEqual({
      ok: false,
      reason: "invalid",
    });
  });

  it("revokeAllForUser derruba todas as sessões do usuário e só dele", async () => {
    const a = await tokens.createSession("u1");
    const b = await tokens.createSession("u1");
    const other = await tokens.createSession("u2");

    await tokens.revokeAllForUser("u1");

    await expect(tokens.rotateRefresh(a.refreshToken)).resolves.toEqual({ ok: false, reason: "invalid" });
    await expect(tokens.rotateRefresh(b.refreshToken)).resolves.toEqual({ ok: false, reason: "invalid" });
    const otherRotate = await tokens.rotateRefresh(other.refreshToken);
    expect(otherRotate.ok).toBe(true);
  });
});
