import { describe, expect, it } from "vitest";
import { isReadOnlyStatement } from "../src/lib/sqlKind";

describe("isReadOnlyStatement — só SELECT puro vai pra leitura nativa", () => {
  it("aceita SELECT direto", () => {
    expect(isReadOnlyStatement("SELECT 1")).toBe(true);
    expect(isReadOnlyStatement("SELECT * FROM users WHERE id = 1")).toBe(true);
  });

  it("aceita SELECT com whitespace, newlines e case misturado", () => {
    expect(isReadOnlyStatement("  SELECT 1")).toBe(true);
    expect(isReadOnlyStatement("\n\n\tSELECT * FROM u")).toBe(true);
    expect(isReadOnlyStatement("select 1")).toBe(true);
    expect(isReadOnlyStatement("Select * From x")).toBe(true);
  });

  it("aceita SELECT depois de comentário -- de linha", () => {
    expect(isReadOnlyStatement("-- drizzle emit\nSELECT * FROM users")).toBe(true);
    expect(isReadOnlyStatement("-- linha 1\n-- linha 2\n  SELECT 1")).toBe(true);
  });

  it("aceita SELECT depois de comentário /* */ de bloco", () => {
    expect(isReadOnlyStatement("/* meta */ SELECT 1")).toBe(true);
    expect(isReadOnlyStatement("/* linha 1\n   linha 2 */\nSELECT * FROM u")).toBe(true);
  });

  it("rejeita writes explícitos", () => {
    expect(isReadOnlyStatement("INSERT INTO u VALUES (1)")).toBe(false);
    expect(isReadOnlyStatement("UPDATE u SET x = 1")).toBe(false);
    expect(isReadOnlyStatement("DELETE FROM u WHERE id = 1")).toBe(false);
    expect(isReadOnlyStatement("REPLACE INTO u VALUES (1)")).toBe(false);
  });

  it("rejeita INSERT ... RETURNING (parece SELECT mas escreve)", () => {
    expect(
      isReadOnlyStatement(
        "INSERT INTO kv_store (key, value) VALUES ('k', 'v') RETURNING value",
      ),
    ).toBe(false);
  });

  it("rejeita INSERT ... SELECT (write que contém SELECT dentro)", () => {
    expect(isReadOnlyStatement("INSERT INTO t (a) SELECT a FROM u")).toBe(false);
  });

  it("conservador: WITH/CTE fica no REST (pode conter DML)", () => {
    // Um WITH ... SELECT seria seguro, mas WITH ... INSERT/UPDATE/DELETE não.
    // Não vale o custo do parser SQL — WITH raramente aparece no caminho
    // quente (login/me), então mandamos tudo pro REST.
    expect(isReadOnlyStatement("WITH t AS (SELECT 1) SELECT * FROM t")).toBe(false);
    expect(isReadOnlyStatement("WITH t AS (SELECT 1) INSERT INTO u VALUES (1)")).toBe(false);
  });

  it("rejeita PRAGMA/ATTACH/BEGIN e outros comandos com efeito colateral", () => {
    expect(isReadOnlyStatement("PRAGMA journal_mode = WAL")).toBe(false);
    expect(isReadOnlyStatement("BEGIN")).toBe(false);
    expect(isReadOnlyStatement("COMMIT")).toBe(false);
    expect(isReadOnlyStatement("ATTACH DATABASE 'x' AS y")).toBe(false);
  });

  it("rejeita string vazia ou só whitespace/comentário", () => {
    expect(isReadOnlyStatement("")).toBe(false);
    expect(isReadOnlyStatement("   \n\t  ")).toBe(false);
    expect(isReadOnlyStatement("-- só comentário")).toBe(false);
    expect(isReadOnlyStatement("/* nada */")).toBe(false);
  });

  it("SELECTFOO não é SELECT — checa fronteira de palavra", () => {
    expect(isReadOnlyStatement("SELECTFOO 1")).toBe(false);
  });
});
