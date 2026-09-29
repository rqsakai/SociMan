import { createHash, randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createClient } from "@libsql/client";
import { expect, request, type Page } from "@playwright/test";

export const API_URL = "http://localhost:3001";
export const PASSWORD = "senha-forte-123";

const outboxPath = fileURLToPath(new URL("../apps/api/data/outbox.jsonl", import.meta.url));
const dbPath = fileURLToPath(new URL("../apps/api/data/dev.db", import.meta.url));

interface OutboxEntry {
  kind: "verification" | "reset";
  to: string;
  link: string;
  at: number;
}

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${randomUUID().slice(0, 8)}@example.com`;
}

function readOutbox(): OutboxEntry[] {
  if (!existsSync(outboxPath)) return [];
  return readFileSync(outboxPath, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as OutboxEntry);
}

export async function waitForEmailLink(kind: OutboxEntry["kind"], to: string): Promise<string> {
  await expect
    .poll(() => readOutbox().some((e) => e.kind === kind && e.to === to), { timeout: 10_000 })
    .toBe(true);
  const entry = [...readOutbox()].reverse().find((e) => e.kind === kind && e.to === to)!;
  return entry.link;
}

export function tokenFromLink(link: string): string {
  return new URL(link).searchParams.get("token")!;
}

// Cria e verifica um usuário direto pela API (setup rápido para specs de erro).
export async function createVerifiedUser(email: string): Promise<void> {
  const api = await request.newContext({ baseURL: API_URL });
  const res = await api.post("/api/auth/register", {
    data: { name: "Usuária E2E", email, password: PASSWORD },
  });
  expect(res.ok()).toBeTruthy();
  const link = await waitForEmailLink("verification", email);
  const verify = await api.post("/api/auth/verify-email", { data: { token: tokenFromLink(link) } });
  expect(verify.ok()).toBeTruthy();
  await api.dispose();
}

// Backdoor de teste: insere um token de reset JÁ EXPIRADO direto no SQLite de
// dev, para exercitar o caminho "token expirado" de forma determinística.
export async function insertExpiredResetToken(email: string): Promise<string> {
  const rawToken = `expired-${randomUUID()}`;
  const tokenHash = createHash("sha256").update(rawToken).digest("hex");
  const db = createClient({ url: `file:${dbPath}` });
  try {
    const user = await db.execute({ sql: "SELECT id FROM users WHERE email = ?", args: [email] });
    const userId = user.rows[0]!.id as string;
    await db.execute({
      sql: "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, used_at) VALUES (?, ?, ?, NULL)",
      args: [tokenHash, userId, Date.now() - 60_000],
    });
  } finally {
    db.close();
  }
  return rawToken;
}

export async function dismissConsentIfVisible(page: Page): Promise<void> {
  const button = page.getByRole("button", { name: "Só o essencial" });
  if (await button.isVisible().catch(() => false)) {
    await button.click();
  }
}

export async function loginViaUi(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await dismissConsentIfVisible(page);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}
