import { fileURLToPath } from "node:url";
import { migrate } from "drizzle-orm/libsql/migrator";
import { buildDeps, type HandlerDeps } from "../src/handlers/deps";
import { createTestDb, type Db } from "../src/lib/adapters/db";
import type { Env } from "../src/lib/env";
import { SqliteKV } from "../src/lib/kv";

const migrationsFolder = fileURLToPath(new URL("../drizzle", import.meta.url));

export async function setupTestDb(): Promise<{ db: Db; kv: SqliteKV }> {
  const { db } = createTestDb();
  await migrate(db, { migrationsFolder });
  return { db, kv: new SqliteKV(db) };
}

// Parâmetros de hash mínimos para testes rápidos — NÃO usar em produção.
export const testHashConfig = {
  algorithm: "argon2id" as const,
  argon2: { memoryKib: 1024, iterations: 2, parallelism: 1 },
  pbkdf2: { iterations: 1000 },
};

// graceSeconds 0 = modo estrito: qualquer reuso revoga imediatamente (os
// testes de graça criam um serviço próprio com janela > 0).
export const testTokenConfig = {
  jwtSecret: "test-secret-test-secret-test-32ch!",
  accessTtlSeconds: 900,
  refreshTtlSeconds: 3600,
  graceSeconds: 0,
  audience: "boilerplate-01-auth",
};

export const baseTestEnv: Env = {
  APP_URL: "http://localhost:5173",
  APP_NAME: testTokenConfig.audience,
  VOLANS_ENV: "development",
  JWT_SECRET: testTokenConfig.jwtSecret,
  ACCESS_TTL: testTokenConfig.accessTtlSeconds,
  REFRESH_TTL: testTokenConfig.refreshTtlSeconds,
  REFRESH_GRACE: 0,
  PASSWORD_HASH: "argon2id",
  PASSWORD_MIN_LENGTH: 8,
  ARGON2_MEMORY_KIB: testHashConfig.argon2.memoryKib,
  ARGON2_ITERATIONS: testHashConfig.argon2.iterations,
  ARGON2_PARALLELISM: testHashConfig.argon2.parallelism,
  PBKDF2_ITERATIONS: testHashConfig.pbkdf2.iterations,
  RESET_TOKEN_TTL: 900,
  VERIFY_TOKEN_TTL: 3600,
  DATABASE_URL: ":memory:",
  KV_DRIVER: "sqlite",
  REDIS_URL: "redis://localhost:6379",
  STORAGE_DRIVER: "none",
  S3_ENDPOINT: undefined,
  S3_REGION: "us-east-1",
  S3_ACCESS_KEY: undefined,
  S3_SECRET_KEY: undefined,
  S3_BUCKET: "volans-test",
  IMAGE_DRIVER: "none",
  IMGPROXY_PUBLIC_PATH: "/img",
  IMGPROXY_KEY: undefined,
  IMGPROXY_SALT: undefined,
  EMAIL_PROVIDER: "stub",
  EMAIL_FILE: "./data/outbox.test.jsonl",
  EMAIL_FROM: "Volans <no-reply@test.local>",
  RESEND_API_KEY: undefined,
  SMTP_HOST: "localhost",
  SMTP_PORT: 1025,
  SMTP_FROM: "test@volans.local",
  SMTP_USER: undefined,
  SMTP_PASS: undefined,
  SMTP_SECURE: false,
  CONSENT_POLICY_VERSION: "test-policy",
  // como atrás do nginx do compose: X-Real-IP reescrito pelo proxy é confiável
  TRUSTED_PROXY: true,
};

export interface SentEmail {
  kind: "verification" | "reset";
  to: string;
  link: string;
}

export interface TestContext {
  deps: HandlerDeps;
  db: Db;
  kv: SqliteKV;
  sentEmails: SentEmail[];
  lastTokenFor(kind: SentEmail["kind"]): string;
}

export async function setupTestDeps(envOverrides?: Partial<Env>): Promise<TestContext> {
  const { db, kv } = await setupTestDb();
  const deps = buildDeps(db, kv, { ...baseTestEnv, ...envOverrides });
  const sentEmails: SentEmail[] = [];
  deps.email = {
    async sendVerificationEmail(to, link) {
      sentEmails.push({ kind: "verification", to, link });
    },
    async sendPasswordResetEmail(to, link) {
      sentEmails.push({ kind: "reset", to, link });
    },
  };
  return {
    deps,
    db,
    kv,
    sentEmails,
    lastTokenFor(kind) {
      const email = [...sentEmails].reverse().find((e) => e.kind === kind);
      if (!email) throw new Error(`nenhum e-mail "${kind}" enviado`);
      return new URL(email.link).searchParams.get("token")!;
    },
  };
}

export function postJson(url: string, body: unknown, headers?: Record<string, string>): Request {
  return new Request(`http://localhost${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

export function post(url: string, headers?: Record<string, string>): Request {
  return new Request(`http://localhost${url}`, { method: "POST", headers });
}

export function get(url: string, headers?: Record<string, string>): Request {
  return new Request(`http://localhost${url}`, { method: "GET", headers });
}

// Extrai o par nome=valor do Set-Cookie para reapresentar como Cookie header.
export function cookiePairFrom(res: Response): string {
  const setCookie = res.headers.get("set-cookie");
  if (!setCookie) throw new Error("resposta sem Set-Cookie");
  return setCookie.split(";")[0]!;
}
