import { beforeEach, describe, expect, it } from "vitest";
import {
  handleForgotPassword,
  handleLogin,
  handleLogout,
  handleMe,
  handleRefresh,
  handleRegister,
  handleResetPassword,
  handleVerifyEmail,
} from "../src/handlers/auth";
import { handleConsent } from "../src/handlers/consent";
import {
  cookiePairFrom,
  get,
  post,
  postJson,
  setupTestDeps,
  type TestContext,
} from "./helpers";

const EMAIL = "user@example.com";
const PASSWORD = "senha-forte-123";

let ctx: TestContext;

beforeEach(async () => {
  ctx = await setupTestDeps();
});

async function registerAndVerify(): Promise<void> {
  await handleRegister(postJson("/api/auth/register", { name: "Ana", email: EMAIL, password: PASSWORD }), ctx.deps);
  await handleVerifyEmail(
    postJson("/api/auth/verify-email", { token: ctx.lastTokenFor("verification") }),
    ctx.deps,
  );
}

async function login(): Promise<Response> {
  return handleLogin(postJson("/api/auth/login", { email: EMAIL, password: PASSWORD }), ctx.deps);
}

describe("register", () => {
  it("cria usuário não verificado, envia e-mail e abre sessão com cookie path-scoped", async () => {
    const res = await handleRegister(
      postJson("/api/auth/register", { name: "Ana", email: "  ANA@Example.COM ", password: PASSWORD }),
      ctx.deps,
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.accessToken).toBeTypeOf("string");
    expect(body.user.email).toBe("ana@example.com"); // normalizado
    expect(body.user.emailVerified).toBe(false);

    const setCookie = res.headers.get("set-cookie")!;
    expect(setCookie).toContain("volans_rt=");
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("Secure");
    expect(setCookie).toContain("SameSite=Strict");
    expect(setCookie).toContain("Path=/api/auth/refresh");

    expect(ctx.sentEmails).toHaveLength(1);
    expect(ctx.sentEmails[0]!.kind).toBe("verification");
  });

  it("rejeita e-mail duplicado com email_in_use", async () => {
    await registerAndVerify();
    const res = await handleRegister(
      postJson("/api/auth/register", { email: EMAIL, password: PASSWORD }),
      ctx.deps,
    );
    expect(res.status).toBe(409);
    expect((await res.json()).error.code).toBe("email_in_use");
  });

  it("rejeita senha curta e senha comum", async () => {
    const curta = await handleRegister(
      postJson("/api/auth/register", { email: EMAIL, password: "curta12" }),
      ctx.deps,
    );
    expect(curta.status).toBe(400);
    const comum = await handleRegister(
      postJson("/api/auth/register", { email: EMAIL, password: "password123" }),
      ctx.deps,
    );
    expect(comum.status).toBe(400);
    expect((await comum.json()).error.code).toBe("validation_error");
  });
});

describe("login", () => {
  it("bloqueia login antes da verificação de e-mail (default do brief)", async () => {
    await handleRegister(postJson("/api/auth/register", { email: EMAIL, password: PASSWORD }), ctx.deps);
    const res = await login();
    expect(res.status).toBe(403);
    expect((await res.json()).error.code).toBe("email_not_verified");
  });

  it("após verificação, autentica e abre sessão", async () => {
    await registerAndVerify();
    const res = await login();
    expect(res.status).toBe(200);
    expect((await res.json()).user.emailVerified).toBe(true);
    expect(res.headers.get("set-cookie")).toContain("volans_rt=");
  });

  it("erro genérico idêntico para senha errada e e-mail inexistente (sem enumeração)", async () => {
    await registerAndVerify();
    const wrongPassword = await handleLogin(
      postJson("/api/auth/login", { email: EMAIL, password: "senha-errada-99" }),
      ctx.deps,
    );
    const unknownEmail = await handleLogin(
      postJson("/api/auth/login", { email: "ninguem@example.com", password: PASSWORD }),
      ctx.deps,
    );
    expect(wrongPassword.status).toBe(401);
    expect(unknownEmail.status).toBe(401);
    expect(await wrongPassword.json()).toEqual(await unknownEmail.json());
  });

  it("rate limit por conta responde 429 com Retry-After", async () => {
    await registerAndVerify();
    let last: Response | null = null;
    for (let i = 0; i < 11; i++) {
      last = await handleLogin(
        postJson("/api/auth/login", { email: EMAIL, password: "senha-errada-99" }),
        ctx.deps,
      );
    }
    expect(last!.status).toBe(429);
    expect(last!.headers.get("retry-after")).toBeTruthy();
    expect((await last!.json()).error.code).toBe("rate_limited");
  });
});

describe("refresh", () => {
  it("rotaciona o cookie e emite novo access token", async () => {
    await registerAndVerify();
    const loginRes = await login();
    const cookie = cookiePairFrom(loginRes);

    const res = await handleRefresh(post("/api/auth/refresh", { cookie }), ctx.deps);
    expect(res.status).toBe(200);
    expect((await res.json()).accessToken).toBeTypeOf("string");
    expect(cookiePairFrom(res)).not.toBe(cookie);
  });

  it("reuso de refresh antigo revoga a família inteira", async () => {
    await registerAndVerify();
    const loginRes = await login();
    const oldCookie = cookiePairFrom(loginRes);

    const first = await handleRefresh(post("/api/auth/refresh", { cookie: oldCookie }), ctx.deps);
    const newCookie = cookiePairFrom(first);

    const reuse = await handleRefresh(post("/api/auth/refresh", { cookie: oldCookie }), ctx.deps);
    expect(reuse.status).toBe(401);

    const afterRevoke = await handleRefresh(post("/api/auth/refresh", { cookie: newCookie }), ctx.deps);
    expect(afterRevoke.status).toBe(401);
  });

  it("sem cookie responde 401", async () => {
    const res = await handleRefresh(post("/api/auth/refresh"), ctx.deps);
    expect(res.status).toBe(401);
  });
});

describe("logout", () => {
  it("revoga a família via claim fam e limpa o cookie", async () => {
    await registerAndVerify();
    const loginRes = await login();
    const cookie = cookiePairFrom(loginRes);
    const { accessToken } = await loginRes.json();

    const res = await handleLogout(post("/api/auth/logout", { authorization: `Bearer ${accessToken}` }), ctx.deps);
    expect(res.status).toBe(200);
    expect(res.headers.get("set-cookie")).toContain("Max-Age=0");

    const refresh = await handleRefresh(post("/api/auth/refresh", { cookie }), ctx.deps);
    expect(refresh.status).toBe(401);
  });
});

describe("forgot/reset password", () => {
  it("forgot responde 200 para conta inexistente sem enviar e-mail (sem enumeração)", async () => {
    const res = await handleForgotPassword(
      postJson("/api/auth/password/forgot", { email: "ninguem@example.com" }),
      ctx.deps,
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    expect(ctx.sentEmails).toHaveLength(0);
  });

  it("fluxo completo: forgot → reset troca a senha e revoga todas as sessões", async () => {
    await registerAndVerify();
    const loginRes = await login();
    const sessionCookie = cookiePairFrom(loginRes);

    await handleForgotPassword(postJson("/api/auth/password/forgot", { email: EMAIL }), ctx.deps);
    const token = ctx.lastTokenFor("reset");

    const reset = await handleResetPassword(
      postJson("/api/auth/password/reset", { token, newPassword: "nova-senha-456" }),
      ctx.deps,
    );
    expect(reset.status).toBe(200);

    // sessão antiga morreu
    const refresh = await handleRefresh(post("/api/auth/refresh", { cookie: sessionCookie }), ctx.deps);
    expect(refresh.status).toBe(401);

    // senha antiga não vale mais; a nova sim
    const oldLogin = await login();
    expect(oldLogin.status).toBe(401);
    const newLogin = await handleLogin(
      postJson("/api/auth/login", { email: EMAIL, password: "nova-senha-456" }),
      ctx.deps,
    );
    expect(newLogin.status).toBe(200);
  });

  it("token de reset é single-use e expira", async () => {
    await registerAndVerify();
    await handleForgotPassword(postJson("/api/auth/password/forgot", { email: EMAIL }), ctx.deps);
    const token = ctx.lastTokenFor("reset");

    await handleResetPassword(postJson("/api/auth/password/reset", { token, newPassword: "nova-senha-456" }), ctx.deps);
    const secondUse = await handleResetPassword(
      postJson("/api/auth/password/reset", { token, newPassword: "outra-senha-789" }),
      ctx.deps,
    );
    expect(secondUse.status).toBe(400);
    expect((await secondUse.json()).error.code).toBe("invalid_token");
  });

  it("token de reset expirado é rejeitado", async () => {
    const expired = await setupTestDeps({ RESET_TOKEN_TTL: -1 });
    await handleRegister(postJson("/api/auth/register", { email: EMAIL, password: PASSWORD }), expired.deps);
    await handleForgotPassword(postJson("/api/auth/password/forgot", { email: EMAIL }), expired.deps);
    const res = await handleResetPassword(
      postJson("/api/auth/password/reset", {
        token: expired.lastTokenFor("reset"),
        newPassword: "nova-senha-456",
      }),
      expired.deps,
    );
    expect(res.status).toBe(400);
  });
});

describe("verify-email", () => {
  it("token inválido é rejeitado", async () => {
    const res = await handleVerifyEmail(postJson("/api/auth/verify-email", { token: "nao-existe" }), ctx.deps);
    expect(res.status).toBe(400);
    expect((await res.json()).error.code).toBe("invalid_token");
  });

  it("rate limit por IP responde 429 com Retry-After", async () => {
    let last: Response | null = null;
    for (let i = 0; i < 31; i++) {
      last = await handleVerifyEmail(
        postJson("/api/auth/verify-email", { token: `tentativa-${i}` }, { "x-real-ip": "203.0.113.51" }),
        ctx.deps,
      );
    }
    expect(last!.status).toBe(429);
    expect(last!.headers.get("retry-after")).toBeTruthy();
  });
});

describe("me", () => {
  it("retorna o usuário com access token válido e 401 sem token", async () => {
    await registerAndVerify();
    const { accessToken } = await (await login()).json();

    const ok = await handleMe(get("/api/auth/me", { authorization: `Bearer ${accessToken}` }), ctx.deps);
    expect(ok.status).toBe(200);
    expect((await ok.json()).user.email).toBe(EMAIL);

    const missing = await handleMe(get("/api/auth/me"), ctx.deps);
    expect(missing.status).toBe(401);

    const invalid = await handleMe(get("/api/auth/me", { authorization: "Bearer lixo" }), ctx.deps);
    expect(invalid.status).toBe(401);
  });

  it("após logout, o access token antigo (ainda não expirado) deixa de valer", async () => {
    await registerAndVerify();
    const { accessToken } = await (await login()).json();

    await handleLogout(post("/api/auth/logout", { authorization: `Bearer ${accessToken}` }), ctx.deps);

    // família revogada → sessão morta, mesmo com JWT válido por mais ~15 min
    const res = await handleMe(get("/api/auth/me", { authorization: `Bearer ${accessToken}` }), ctx.deps);
    expect(res.status).toBe(401);
  });

  it("após reset de senha, o access token antigo deixa de valer (conta comprometida)", async () => {
    await registerAndVerify();
    const { accessToken } = await (await login()).json();

    await handleForgotPassword(postJson("/api/auth/password/forgot", { email: EMAIL }), ctx.deps);
    await handleResetPassword(
      postJson("/api/auth/password/reset", {
        token: ctx.lastTokenFor("reset"),
        newPassword: "nova-senha-456",
      }),
      ctx.deps,
    );

    const res = await handleMe(get("/api/auth/me", { authorization: `Bearer ${accessToken}` }), ctx.deps);
    expect(res.status).toBe(401);
  });
});

describe("consent", () => {
  it("grava o registro de auditoria com ip e user-agent", async () => {
    const res = await handleConsent(
      postJson(
        "/api/consent",
        {
          categories: { essential: true, analytics: false },
          policyVersion: "test-policy",
          anonId: "anon-123",
        },
        { "x-real-ip": "203.0.113.9", "user-agent": "vitest" },
      ),
      ctx.deps,
    );
    expect(res.status).toBe(200);

    const rows = await ctx.db.query.consentRecords.findMany();
    expect(rows).toHaveLength(1);
    expect(rows[0]!.ip).toBe("203.0.113.9");
    expect(rows[0]!.userAgent).toBe("vitest");
    expect(rows[0]!.anonId).toBe("anon-123");
    expect(JSON.parse(rows[0]!.categories)).toEqual({ essential: true, analytics: false });
  });

  it("X-Forwarded-For cru NUNCA é confiável (só o X-Real-IP do proxy)", async () => {
    const res = await handleConsent(
      postJson(
        "/api/consent",
        { categories: { essential: true, analytics: false }, policyVersion: "test-policy" },
        { "x-forwarded-for": "6.6.6.6" }, // spoof do cliente — deve ser ignorado
      ),
      ctx.deps,
    );
    expect(res.status).toBe(200);
    const rows = await ctx.db.query.consentRecords.findMany();
    expect(rows[0]!.ip).toBe("local");
  });

  it("rate limit por IP responde 429 (escrita SQL é limite de custo)", async () => {
    let last: Response | null = null;
    for (let i = 0; i < 21; i++) {
      last = await handleConsent(
        postJson(
          "/api/consent",
          { categories: { essential: true, analytics: false }, policyVersion: "test-policy" },
          { "x-real-ip": "203.0.113.50" },
        ),
        ctx.deps,
      );
    }
    expect(last!.status).toBe(429);
    expect((await last!.json()).error.code).toBe("rate_limited");
    // as gravações pararam no teto
    const rows = await ctx.db.query.consentRecords.findMany();
    expect(rows.length).toBe(20);
  });
});
