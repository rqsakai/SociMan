import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getEnv, resetEnvForTests } from "../src/lib/env";

// vi.stubEnv restaura tudo no unstubAllEnvs — a suíte roda com NODE_ENV=test
// e sem JWT_SECRET, mas não podemos depender disso.
beforeEach(() => {
  vi.stubEnv("JWT_SECRET", undefined);
  vi.stubEnv("VOLANS_ENV", undefined);
  vi.stubEnv("NODE_ENV", undefined);
  resetEnvForTests();
});

afterEach(() => {
  vi.unstubAllEnvs();
  resetEnvForTests();
});

describe("guards de JWT_SECRET", () => {
  it("dev sem secret: gera um efêmero forte e cacheia por processo", () => {
    const env = getEnv();
    expect(env.JWT_SECRET.length).toBeGreaterThanOrEqual(32);
    // cache: mesma instância na segunda chamada
    expect(getEnv().JWT_SECRET).toBe(env.JWT_SECRET);
  });

  it("secret curto (<32 chars) é rejeitado mesmo em dev", () => {
    vi.stubEnv("JWT_SECRET", "curto-demais");
    expect(() => getEnv()).toThrow(/32 caracteres/);
  });

  it("produção (VOLANS_ENV) sem secret lança erro claro", () => {
    vi.stubEnv("VOLANS_ENV", "production");
    expect(() => getEnv()).toThrow(/JWT_SECRET é obrigatório em produção/);
  });

  it("NODE_ENV=production também ativa o guard (defesa dupla)", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(() => getEnv()).toThrow(/JWT_SECRET é obrigatório em produção/);
  });

  it("produção com secret forte funciona", () => {
    vi.stubEnv("VOLANS_ENV", "production");
    vi.stubEnv("JWT_SECRET", "um-secret-forte-de-32-caracteres!!");
    expect(getEnv().JWT_SECRET).toBe("um-secret-forte-de-32-caracteres!!");
  });
});
