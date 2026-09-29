import { describe, expect, it } from "vitest";
import { inlineParams, inlineSqlValue } from "../src/lib/sqlInline";

describe("inlineSqlValue — escaping por tipo", () => {
  it("dobra aspas simples em strings (neutraliza injeção)", () => {
    expect(inlineSqlValue("o'brien")).toBe("'o''brien'");
    expect(inlineSqlValue("'; DROP TABLE users; --")).toBe("'''; DROP TABLE users; --'");
  });

  it("números finitos entram crus; NaN/Infinity são rejeitados", () => {
    expect(inlineSqlValue(42)).toBe("42");
    expect(inlineSqlValue(-1.5)).toBe("-1.5");
    expect(() => inlineSqlValue(Number.NaN)).toThrow();
    expect(() => inlineSqlValue(Number.POSITIVE_INFINITY)).toThrow();
  });

  it("null/undefined viram NULL; boolean vira 0/1; Date vira epoch ms", () => {
    expect(inlineSqlValue(null)).toBe("NULL");
    expect(inlineSqlValue(undefined)).toBe("NULL");
    expect(inlineSqlValue(true)).toBe("1");
    expect(inlineSqlValue(false)).toBe("0");
    expect(inlineSqlValue(new Date(1700000000000))).toBe("1700000000000");
  });

  it("Uint8Array vira literal blob hex X'..'", () => {
    expect(inlineSqlValue(new Uint8Array([0, 255, 16]))).toBe("X'00ff10'");
  });

  it("tipo não suportado (objeto) é rejeitado — não vira SQL cru", () => {
    expect(() => inlineSqlValue({ evil: true } as unknown)).toThrow(/não suportado/);
  });
});

describe("inlineParams — substituição posicional segura", () => {
  it("substitui ? na ordem, com escaping", () => {
    expect(inlineParams("SELECT * FROM u WHERE email = ? AND age > ?", ["a'b@x.com", 30])).toBe(
      "SELECT * FROM u WHERE email = 'a''b@x.com' AND age > 30",
    );
  });

  it("payload de injeção clássico fica inerte dentro das aspas", () => {
    const evil = "x' OR '1'='1";
    const sql = inlineParams("SELECT * FROM u WHERE name = ?", [evil]);
    expect(sql).toBe("SELECT * FROM u WHERE name = 'x'' OR ''1''=''1'");
    // não há aspa solta que quebre a string literal
    expect((sql.match(/'/g) ?? []).length % 2).toBe(0);
  });

  it("divergência entre placeholders e params é erro (não silencia)", () => {
    expect(() => inlineParams("SELECT ?", [])).toThrow();
    expect(() => inlineParams("SELECT ?", [1, 2])).toThrow();
  });
});
