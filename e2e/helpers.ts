import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { crc32, deflateSync } from "node:zlib";
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { BASE_URL, MAILPIT_URL, OWNER } from "./fixtures";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${randomUUID().slice(0, 8)}@example.com`;
}

// --- docker compose ---

// Roda `docker compose <args>` na raiz do repo; `input` vai para o stdin.
export function compose(args: string[], input?: string): string {
  return execFileSync("docker", ["compose", ...args], {
    cwd: repoRoot,
    input,
    encoding: "utf8",
    stdio: [input === undefined ? "ignore" : "pipe", "pipe", "inherit"],
  });
}

export async function waitForHealth(timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let last = "sem resposta";
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE_URL}/api/health`);
      if (res.status === 200) return;
      last = `HTTP ${res.status}`;
    } catch (err) {
      last = String(err);
    }
    await new Promise((r) => setTimeout(r, 1_000));
  }
  throw new Error(`/api/health não respondeu 200 em ${timeoutMs} ms (${last}). A stack está no ar?`);
}

// Vence todos os tokens de reset de senha direto no Postgres.
export function expireResetTokens(): void {
  compose([
    "exec", "-T", "postgres", "psql", "-U", "sociman", "-d", "sociman", "-c",
    "update one_time_tokens set expires_at = now() - interval '1 minute' where purpose='reset_password'",
  ]);
}

// --- Mailpit ---

export interface MailSummary {
  ID: string;
  Subject: string;
  To: { Address: string }[];
  Created: string;
}

export interface Mail extends MailSummary {
  Text: string;
  HTML: string;
}

export async function clearInbox(): Promise<void> {
  const res = await fetch(`${MAILPIT_URL}/api/v1/messages`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Mailpit: DELETE /api/v1/messages respondeu ${res.status}`);
}

async function searchMail(to: string): Promise<MailSummary[]> {
  const query = encodeURIComponent(`to:"${to}"`);
  const res = await fetch(`${MAILPIT_URL}/api/v1/search?query=${query}`);
  if (!res.ok) throw new Error(`Mailpit: busca respondeu ${res.status}`);
  const body = (await res.json()) as { messages: MailSummary[] | null };
  return body.messages ?? [];
}

// Espera o e-mail mais recente para `to` cujo assunto contém `subjectContains`.
export async function waitForEmail(to: string, subjectContains: string, timeoutMs = 15_000): Promise<Mail> {
  let found: MailSummary | undefined;
  await expect
    .poll(
      async () => {
        // o Mailpit devolve do mais recente para o mais antigo
        found = (await searchMail(to)).find((m) => m.Subject.includes(subjectContains));
        return Boolean(found);
      },
      { timeout: timeoutMs, message: `e-mail "${subjectContains}" para ${to} não chegou no Mailpit` },
    )
    .toBe(true);
  const res = await fetch(`${MAILPIT_URL}/api/v1/message/${found!.ID}`);
  if (!res.ok) throw new Error(`Mailpit: GET /api/v1/message respondeu ${res.status}`);
  return (await res.json()) as Mail;
}

// Acha no corpo do e-mail o link `<path>?token=...` (ex.: "/verify-email",
// "/reset-password") e devolve o caminho relativo, pronto para `page.goto`
// (os links usam APP_URL, que aponta para o edge HTTPS).
export function extractLink(mail: Mail, path: string): string {
  const escaped = path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`https?://[^\\s"'<>]*${escaped}\\?token=[^\\s"'<>&]+`);
  const match = mail.Text.match(pattern) ?? mail.HTML.match(pattern);
  if (!match) throw new Error(`link ${path}?token= não encontrado no e-mail "${mail.Subject}"`);
  const url = new URL(match[0].replace(/&amp;/g, "&"));
  return `${url.pathname}${url.search}`;
}

export function tokenFromLink(link: string): string {
  return new URL(link, BASE_URL).searchParams.get("token")!;
}

// Zera os contadores de limite de tentativa (chaves rl:* no Redis de dev). A suíte faz muitos
// logins com o mesmo dono e o mesmo IP e estouraria o limite do app (10/conta e 30/IP a cada
// 15 min), que é testado no pytest. Isto só mexe nos contadores, nunca no limite.
export function resetRateLimits(): void {
  compose(["exec", "-T", "redis", "sh", "-c", "redis-cli --scan --pattern 'rl:*' | xargs -r redis-cli del >/dev/null"]);
}

// --- API ---

// Access token do usuário via POST /api/auth/login (para montar dados sem passar pela UI).
export async function apiToken(request: APIRequestContext, email: string, password: string): Promise<string> {
  resetRateLimits();
  const res = await request.post("/api/auth/login", { data: { email, password } });
  expect(res.status(), "POST /api/auth/login").toBe(200);
  return ((await res.json()) as { accessToken: string }).accessToken;
}

// Cria um perfil via POST /api/perfis (status padrão: Em preparação).
export async function createPerfilViaApi(
  request: APIRequestContext,
  token: string,
  perfil: { name: string; slug: string; niche?: string },
): Promise<void> {
  const res = await request.post("/api/perfis", {
    headers: { Authorization: `Bearer ${token}` },
    data: perfil,
  });
  expect(res.status(), `POST /api/perfis (${perfil.slug})`).toBe(201);
}

// --- UI ---

export async function login(page: Page, email: string, password: string): Promise<void> {
  resetRateLimits();
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

export interface Member {
  email: string;
  name: string;
  provisional: string;
  final: string;
}

// Membro com e-mail e nome únicos (o nome aparece nos selects de filtro).
export function newMember(): Member {
  const email = uniqueEmail("membro");
  const suffix = email.slice("membro-".length, email.indexOf("@"));
  return {
    email,
    name: `Membro ${suffix}`,
    provisional: "Provisoria-e2e-Membro-2026",
    final: "Definitiva-e2e-Membro-2026",
  };
}

// Com o dono logado em /app: cria o membro em /app/usuarios.
export async function createMember(page: Page, member: Member): Promise<void> {
  await page.getByRole("link", { name: "Usuários" }).click();
  await expect(page).toHaveURL(/\/app\/usuarios$/);
  await page.getByLabel("Nome").fill(member.name);
  await page.getByLabel("E-mail").fill(member.email);
  await page.getByLabel("Papel").selectOption({ label: "Membro" });
  await page.getByLabel("Senha provisória").fill(member.provisional);
  await page.getByRole("button", { name: "Criar usuário" }).click();
  await expect(page.getByRole("cell", { name: member.email })).toBeVisible();
}

// Em /trocar-senha: troca a senha provisória e cai em /app.
export async function changeProvisionalPassword(page: Page, member: Member): Promise<void> {
  await page.getByLabel("Senha atual").fill(member.provisional);
  await page.getByLabel("Nova senha", { exact: true }).fill(member.final);
  await page.getByLabel("Confirmar nova senha").fill(member.final);
  await page.getByRole("button", { name: "Trocar senha" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

// Fluxo completo pela UI: o dono cria o membro, o membro verifica o e-mail,
// entra com a senha provisória e troca para `member.final`. Termina deslogado.
export async function createVerifiedMember(page: Page, member: Member = newMember()): Promise<Member> {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await createMember(page, member);
  await logout(page);

  const mail = await waitForEmail(member.email, "Confirme seu e-mail");
  await page.goto(extractLink(mail, "/verify-email"));
  await expect(page.getByText("E-mail confirmado, faça login")).toBeVisible();

  await login(page, member.email, member.provisional);
  await expect(page).toHaveURL(/\/trocar-senha$/);
  await changeProvisionalPassword(page, member);
  await logout(page);
  return member;
}

// --- imagens ---

// PNG RGB válido de `width`×`height`, montado em memória (sem dependência nova):
// assinatura + IHDR + IDAT (linhas com filtro 0, deflate) + IEND.
export function pngBuffer(width: number, height: number): Buffer {
  const chunk = (type: string, data: Buffer): Buffer => {
    const typeAndData = Buffer.concat([Buffer.from(type, "ascii"), data]);
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(typeAndData));
    return Buffer.concat([len, typeAndData, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bits por canal
  ihdr[9] = 2; // RGB
  const row = Buffer.alloc(1 + width * 3);
  for (let x = 0; x < width; x++) row.set([200, 60, (x * 255) / width], 1 + x * 3);
  const raw = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}
