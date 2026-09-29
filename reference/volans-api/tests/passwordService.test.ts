import { describe, expect, it } from "vitest";
import { createPasswordService } from "../src/services/passwordService";
import { testHashConfig } from "./helpers";

const argonService = createPasswordService({ ...testHashConfig, algorithm: "argon2id" });
const pbkdf2Service = createPasswordService({ ...testHashConfig, algorithm: "pbkdf2" });

describe("passwordService — argon2id", () => {
  it("gera PHC string e verifica a senha correta", async () => {
    const hash = await argonService.hash("correct horse battery");
    expect(hash.startsWith("$argon2id$")).toBe(true);
    await expect(argonService.verify("correct horse battery", hash)).resolves.toBe(true);
  });

  it("rejeita senha errada", async () => {
    const hash = await argonService.hash("correct horse battery");
    await expect(argonService.verify("wrong horse", hash)).resolves.toBe(false);
  });

  it("gera salt distinto por hash", async () => {
    const [a, b] = await Promise.all([argonService.hash("mesma senha"), argonService.hash("mesma senha")]);
    expect(a).not.toBe(b);
  });
});

describe("passwordService — pbkdf2", () => {
  it("gera PHC string e verifica a senha correta", async () => {
    const hash = await pbkdf2Service.hash("correct horse battery");
    expect(hash.startsWith("$pbkdf2-sha256$i=1000$")).toBe(true);
    await expect(pbkdf2Service.verify("correct horse battery", hash)).resolves.toBe(true);
  });

  it("rejeita senha errada", async () => {
    const hash = await pbkdf2Service.hash("correct horse battery");
    await expect(pbkdf2Service.verify("wrong horse", hash)).resolves.toBe(false);
  });
});

describe("passwordService — dispatch pelo prefixo do hash armazenado", () => {
  it("serviço configurado como pbkdf2 ainda verifica hash argon2id (e vice-versa)", async () => {
    const argonHash = await argonService.hash("senha antiga");
    const pbkdf2Hash = await pbkdf2Service.hash("senha nova");
    await expect(pbkdf2Service.verify("senha antiga", argonHash)).resolves.toBe(true);
    await expect(argonService.verify("senha nova", pbkdf2Hash)).resolves.toBe(true);
  });

  it("hash com formato desconhecido nunca verifica", async () => {
    await expect(argonService.verify("qualquer", "texto-plano-nao-e-hash")).resolves.toBe(false);
  });
});
