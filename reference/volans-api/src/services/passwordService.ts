import { argon2id, argon2Verify } from "hash-wasm";
import { constantTimeEqual, fromBase64Url, randomBytes, toBase64Url } from "../lib/crypto";

// Hash de senha edge-compatible (§6.1):
// - default: Argon2id via hash-wasm (WASM roda em isolate V8, sem native addon)
// - alternativa zero-WASM: PBKDF2-SHA256 via WebCrypto (PASSWORD_HASH=pbkdf2)
// O hash é armazenado como PHC string; verify() despacha pelo PREFIXO do hash
// armazenado, então trocar PASSWORD_HASH só afeta hashes novos e a migração de
// algoritmo é transparente (re-hash no próximo login fica como evolução).

export interface PasswordHashConfig {
  algorithm: "argon2id" | "pbkdf2";
  argon2: { memoryKib: number; iterations: number; parallelism: number };
  pbkdf2: { iterations: number };
}

export interface PasswordService {
  hash(password: string): Promise<string>;
  verify(password: string, storedHash: string): Promise<boolean>;
}

const PBKDF2_PREFIX = "$pbkdf2-sha256$";

async function pbkdf2Derive(password: string, salt: Uint8Array, iterations: number): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: salt as BufferSource, iterations },
    key,
    256,
  );
  return new Uint8Array(bits);
}

async function pbkdf2Hash(password: string, iterations: number): Promise<string> {
  const salt = randomBytes(16);
  const derived = await pbkdf2Derive(password, salt, iterations);
  return `${PBKDF2_PREFIX}i=${iterations}$${toBase64Url(salt)}$${toBase64Url(derived)}`;
}

async function pbkdf2VerifyHash(password: string, storedHash: string): Promise<boolean> {
  const parts = storedHash.slice(PBKDF2_PREFIX.length).split("$");
  const [params, saltB64, hashB64] = parts;
  if (!params?.startsWith("i=") || !saltB64 || !hashB64) return false;
  const iterations = Number(params.slice(2));
  if (!Number.isInteger(iterations) || iterations < 1) return false;
  const derived = await pbkdf2Derive(password, fromBase64Url(saltB64), iterations);
  return constantTimeEqual(toBase64Url(derived), hashB64);
}

export function createPasswordService(config: PasswordHashConfig): PasswordService {
  return {
    async hash(password) {
      if (config.algorithm === "pbkdf2") {
        return pbkdf2Hash(password, config.pbkdf2.iterations);
      }
      return argon2id({
        password,
        salt: randomBytes(16),
        memorySize: config.argon2.memoryKib,
        iterations: config.argon2.iterations,
        parallelism: config.argon2.parallelism,
        hashLength: 32,
        outputType: "encoded", // PHC string ($argon2id$v=19$m=...,t=...,p=...$...)
      });
    },

    async verify(password, storedHash) {
      if (storedHash.startsWith("$argon2id$")) {
        return argon2Verify({ password, hash: storedHash });
      }
      if (storedHash.startsWith(PBKDF2_PREFIX)) {
        return pbkdf2VerifyHash(password, storedHash);
      }
      return false;
    },
  };
}
