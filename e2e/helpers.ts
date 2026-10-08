import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { crc32, deflateSync } from "node:zlib";
import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { BASE_URL, COMPOSE_ARGS, MAILPIT_URL, OWNER, PG_DB, PG_USER } from "./fixtures";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${randomUUID().slice(0, 8)}@example.com`;
}

// --- docker compose ---

// Roda `docker compose <args>` na stack e2e (E2E_COMPOSE), na raiz do repo; `input` vai para o stdin.
export function compose(args: string[], input?: string): string {
  return execFileSync("docker", ["compose", ...COMPOSE_ARGS, ...args], {
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
    "exec", "-T", "postgres", "psql", "-U", PG_USER, "-d", PG_DB, "-c",
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

// Zera os contadores de limite de tentativa (chaves rl:* no Redis da stack e2e). A suíte faz muitos
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

// Cria um perfil via POST /api/perfis (status padrão: Em preparação) e devolve o id.
export async function createPerfilViaApi(
  request: APIRequestContext,
  token: string,
  perfil: { name: string; slug: string; niche?: string },
): Promise<string> {
  const res = await request.post("/api/perfis", {
    headers: { Authorization: `Bearer ${token}` },
    data: perfil,
  });
  expect(res.status(), `POST /api/perfis (${perfil.slug})`).toBe(201);
  return ((await res.json()) as { perfil: { id: string } }).perfil.id;
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

// Link do menu principal (só os visíveis: o de um grupo fechado não conta).
export function navLink(page: Page, label: string): Locator {
  return page.getByRole("navigation", { name: "Menu principal" }).getByRole("link", { name: label, exact: true });
}

// Navega pelo menu principal (spec 024): se o item está num grupo fechado, abre o grupo antes.
// O Sidebar mantém os links de grupo fechado no DOM (hidden), e o botão do grupo aponta para eles
// por aria-controls.
export async function nav(page: Page, label: string): Promise<void> {
  const menu = page.getByRole("navigation", { name: "Menu principal" });
  const link = menu.getByRole("link", { name: label, exact: true, includeHidden: true });
  await expect(link).toHaveCount(1);
  if (!(await link.isVisible())) {
    const fechados = menu.locator('button[aria-expanded="false"][aria-controls]');
    for (const botao of await fechados.all()) {
      const regiao = page.locator(`[id="${await botao.getAttribute("aria-controls")}"]`);
      if (await regiao.getByRole("link", { name: label, exact: true, includeHidden: true }).count()) {
        await botao.click();
        break;
      }
    }
  }
  await navLink(page, label).click();
}

// Digita a data no DateField (spec 024, R12) como o dono digitaria: dd/mm/aaaa (e hh:mm, se vier).
export async function preencherData(campo: Locator, iso: string): Promise<void> {
  const [, ano, mes, dia, hora] = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}:\d{2}))?/.exec(iso) ?? [];
  if (!ano) throw new Error(`preencherData: data ISO inválida: ${iso}`);
  await campo.fill("");
  await campo.pressSequentially(`${dia}/${mes}/${ano}${hora ? ` ${hora}` : ""}`);
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
  await nav(page, "Usuários");
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

// --- vídeo ---

// MP4 sintético (H.264 + AAC, 9:16) de `seconds` segundos em `outPath`, com o ffmpeg do host.
// Sem ffmpeg no host, gera no container da API (que tem ffmpeg) e copia com `docker compose cp`.
export function syntheticMp4(outPath: string, seconds = 6, size = "540x960"): void {
  const args = [
    "-v", "error", "-y",
    "-f", "lavfi", "-i", `testsrc2=size=${size}:rate=30`,
    "-f", "lavfi", "-i", "sine=frequency=440",
    "-t", String(seconds),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
  ];
  try {
    execFileSync("ffmpeg", [...args, outPath], { stdio: ["ignore", "ignore", "inherit"] });
    return;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
  }
  const tmp = `/tmp/e2e-${randomUUID()}.mp4`;
  compose(["exec", "-T", "api", "ffmpeg", ...args, tmp]);
  compose(["cp", `api:${tmp}`, outPath]);
  compose(["exec", "-T", "api", "rm", "-f", tmp]);
}

// --- biblioteca de assets (spec 007) ---

// PNG RGBA de `width`×`height` com transparência de verdade (metade esquerda opaca, metade
// direita transparente): o que o sticker e a marca d'água exigem. `pngBuffer` é RGB (opaco).
export function pngAlphaBuffer(width: number, height: number): Buffer {
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
  ihdr[9] = 6; // RGBA
  const row = Buffer.alloc(1 + width * 4);
  for (let x = 0; x < width; x++) row.set([40, 160, 90, x < width / 2 ? 255 : 0], 1 + x * 4);
  const raw = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

export interface SeedAsset {
  tipo: "avatar" | "cenario" | "fundo" | "sticker" | "marca_dagua" | "imagem";
  name: string;
  tags: string[];
}

// Cria assets pela API: avatar e cenário sem arquivo (POST …/assets), os demais com uma imagem
// pequena (POST …/assets/arquivo). Um por vez e com pausa: o edge limita /api/ a 20 req/s.
export async function seedAssets(request: APIRequestContext, token: string, perfilId: string, assets: SeedAsset[]): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` };
  const opaque = pngBuffer(540, 540);
  const alpha = pngAlphaBuffer(64, 64);
  for (const a of assets) {
    const res =
      a.tipo === "avatar" || a.tipo === "cenario"
        ? await request.post(`/api/perfis/${perfilId}/assets`, { headers, data: { tipo: a.tipo, name: a.name, tags: a.tags } })
        : await request.post(`/api/perfis/${perfilId}/assets/arquivo`, {
            headers,
            multipart: {
              tipo: a.tipo,
              name: a.name,
              tags: a.tags.join(","),
              file: {
                name: `${a.name}.png`,
                mimeType: "image/png",
                buffer: a.tipo === "sticker" || a.tipo === "marca_dagua" ? alpha : opaque,
              },
            },
          });
    expect(res.status(), `seed ${a.tipo} "${a.name}": ${await res.text()}`).toBe(201);
    await new Promise((r) => setTimeout(r, 60));
  }
}

// --- TikTok falsa (spec 015) ---

const LOGIN_TIKTOK = /^https:\/\/www\.tiktok\.com\/v2\/auth\/authorize\//;

// Intercepta o login da TikTok no navegador: em vez de sair da máquina, volta direto para o
// `redirect_uri` do SociMan com `code=e2e-<handle>` e o mesmo `state` (a TikTok falsa do
// `openshorts-fake` responde como a conta `<handle>`). Chamar de novo troca o handle. Devolve a
// lista (viva) das URLs interceptadas, sem o `state`.
export async function interceptarLoginTikTok(page: Page, handle: string): Promise<string[]> {
  const interceptados: string[] = [];
  await page.unroute(LOGIN_TIKTOK);
  await page.route(LOGIN_TIKTOK, async (route) => {
    const url = new URL(route.request().url());
    const volta = new URL(url.searchParams.get("redirect_uri")!);
    volta.searchParams.set("code", `e2e-${handle}`);
    volta.searchParams.set("state", url.searchParams.get("state") ?? "");
    url.searchParams.delete("state");
    interceptados.push(url.toString());
    await route.fulfill({ status: 302, headers: { location: volta.toString() } });
  });
  return interceptados;
}

// Chama as rotas de controle da TikTok falsa de dentro do container (ela não é publicada no host).
function tiktokFake(metodo: "GET" | "POST", caminho: string, corpo?: unknown): unknown {
  const script = [
    "import json, sys, urllib.request",
    "corpo = sys.stdin.read().encode() or None",
    `req = urllib.request.Request("http://localhost:8000${caminho}", data=corpo, method="${metodo}",`,
    "                             headers={'content-type': 'application/json'})",
    "print(urllib.request.urlopen(req, timeout=5).read().decode())",
  ].join("\n");
  return JSON.parse(compose(["exec", "-T", "openshorts-fake", "python", "-c", script], corpo === undefined ? "" : JSON.stringify(corpo)));
}

export interface PedidoTikTok {
  metodo: string;
  endpoint: string; // token, revoke, user_info, creator_info, inbox_init, video_init, status, put
  handle: string | null;
  em: string;
  grant?: string;
  pkce?: boolean;
  post_info?: boolean;
  privacy_level?: string | null; // Direct Post (US3)
  title?: string | null;
}

// Tudo o que a TikTok falsa recebeu (de uma conta, ou de todas).
export function pedidosTikTok(handle?: string): PedidoTikTok[] {
  const q = handle ? `?handle=${encodeURIComponent(handle)}` : "";
  return (tiktokFake("GET", `/tiktok-e2e/pedidos${q}`) as { items: PedidoTikTok[] }).items;
}

// A próxima chamada de `endpoint` para `handle` falha: "sem_resposta" (a TikTok falsa cria e não
// responde), "5xx" ou um código da TikTok; no "status", `falha` é o `fail_reason` do FAILED.
export function falharTikTok(handle: string, endpoint: string, falha: string): void {
  tiktokFake("POST", "/tiktok-e2e/falhas", { handle, endpoint, falha });
}

// --- métricas (spec 016, T079) ---

// Os escopos de métricas da TikTok (research R1).
export const ESCOPOS_METRICAS = "user.info.basic,user.info.profile,video.upload,video.publish,user.info.stats,video.list";

// O que o dono "marca" na tela de autorização da TikTok falsa: vale para os próximos logins da
// conta. Sem chamar isto, a TikTok falsa concede só os escopos da 015 (sem métricas).
export function escoposTikTok(handle: string, escopos: string = ESCOPOS_METRICAS): void {
  tiktokFake("POST", "/tiktok-e2e/escopos", { handle, escopos });
}

export interface VideoTikTok {
  id: string; // texto: passa de 2^53
  handle: string;
  create_time: number;
  duracao: number;
  legenda: string;
  publico: boolean;
  share_url: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
}

type Contadores = { views?: number; likes?: number; comments?: number; shares?: number };
type Ritmo = { ritmo?: Partial<Record<"views" | "likes" | "comments" | "shares", number>> };

// Um post público (ou privado) na conta, publicado há `idadeS` segundos. Os contadores crescem
// sozinhos (`ritmo` por minuto; 0 congela).
export function criarVideoTikTok(
  handle: string,
  video: { duracao: number; legenda: string; idadeS?: number; publico?: boolean } & Contadores & Ritmo,
): VideoTikTok {
  const { idadeS, ...resto } = video;
  return (tiktokFake("POST", "/tiktok-e2e/videos", { acao: "criar", handle, idade_s: idadeS ?? 0, ...resto }) as { video: VideoTikTok }).video;
}

export function ajustarVideoTikTok(id: string, acao: "contadores" | "privado" | "publico", valores: Contadores & Ritmo = {}): VideoTikTok {
  return (tiktokFake("POST", "/tiktok-e2e/videos", { acao, id, ...valores }) as { video: VideoTikTok }).video;
}

// O dono finaliza no app o último rascunho entregue da conta, como post público. Com
// `informarId: false`, o `status/fetch` não devolve o id (o vínculo sai pelo casamento).
export function publicarRascunhoTikTok(handle: string, post: { duracao: number; legenda: string; informarId?: boolean }): VideoTikTok {
  const r = tiktokFake("POST", "/tiktok-e2e/publicar-rascunho", {
    handle,
    duracao: post.duracao,
    legenda: post.legenda,
    informar_id: post.informarId ?? true,
  }) as { video: VideoTikTok };
  return r.video;
}

// SQL no Postgres da stack e2e (só o projeto sociman-e2e, pelo `compose()`); devolve as linhas
// sem cabeçalho, com `|` entre as colunas. Serve para semear fotos (o trigger das fotos aceita
// INSERT) e para adiantar a agenda da coleta, que é por hora.
export function sqlE2e(sql: string): string[] {
  const out = compose(["exec", "-T", "postgres", "psql", "-U", PG_USER, "-d", PG_DB, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql]);
  return out.split("\n").filter((l) => l.trim() !== "");
}

// Adianta a série viva da conta: a próxima volta da trilha `metricas` (2 s no e2e) faz a
// descoberta (1ª página do `video/list`), a fila de vídeos e a foto da conta.
export function adiantarColeta(contaId: string): void {
  sqlE2e(
    `update metricas_series set lista_proxima_em = now(), conta_proxima_em = now(), adiar_ate = null ` +
      `where conta_id = '${contaId}' and anonimizada_em is null`,
  );
}

// Adianta a busca do post (nível 1) de um destino de rascunho entregue.
export function adiantarBusca(destinoId: string): void {
  sqlE2e(`update metricas_buscas_post set proxima_em = now() where destino_id = '${destinoId}' and encerrada_em is null`);
}

// --- histórico do TikTok Studio (spec 020, T022) ---

// ZIP "stored" (sem compressão, como os do Studio) montado em memória: cabeçalho local + dados de
// cada entrada, diretório central e fim do diretório. CRC pelo `zlib.crc32` do Node; sem dependência.
export function zipStudio(entradas: { nome: string; dados: Buffer }[]): Buffer {
  const locais: Buffer[] = [];
  const centrais: Buffer[] = [];
  let offset = 0;
  for (const e of entradas) {
    const nome = Buffer.from(e.nome, "utf8");
    const crc = crc32(e.dados) >>> 0;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4); // versão necessária
    local.writeUInt16LE(0, 6); // flags
    local.writeUInt16LE(0, 8); // método: stored
    local.writeUInt16LE(0, 10); // hora
    local.writeUInt16LE(0x21, 12); // data: 1980-01-01
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(e.dados.length, 18);
    local.writeUInt32LE(e.dados.length, 22);
    local.writeUInt16LE(nome.length, 26);
    local.writeUInt16LE(0, 28);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt16LE(0, 12);
    central.writeUInt16LE(0x21, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(e.dados.length, 20);
    central.writeUInt32LE(e.dados.length, 24);
    central.writeUInt16LE(nome.length, 28);
    central.writeUInt32LE(offset, 42);
    locais.push(local, nome, e.dados);
    centrais.push(central, nome);
    offset += local.length + nome.length + e.dados.length;
  }
  const dirCentral = Buffer.concat(centrais);
  const fim = Buffer.alloc(22);
  fim.writeUInt32LE(0x06054b50, 0);
  fim.writeUInt16LE(entradas.length, 8);
  fim.writeUInt16LE(entradas.length, 10);
  fim.writeUInt32LE(dirCentral.length, 12);
  fim.writeUInt32LE(offset, 16);
  return Buffer.concat([...locais, dirCentral, fim]);
}

const MESES_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// "2026-09-25" → "September 25" (o Studio não traz o ano).
export function diaStudio(dia: string): string {
  const [, m, d] = dia.split("-").map(Number);
  return `${MESES_EN[m! - 1]} ${d}`;
}

// CSV no formato real: UTF-8 com BOM, tudo entre aspas, sem quebra de linha no fim.
function csvStudio(cabecalho: string[], linhas: (string | number)[][]): Buffer {
  const linha = (campos: (string | number)[]) => campos.map((c) => `"${String(c)}"`).join(",");
  return Buffer.from(`\ufeff${[linha(cabecalho), ...linhas.map(linha)].join("\n")}`, "utf8");
}

export interface DiaOverview {
  dia: string; // AAAA-MM-DD
  views: number;
  visitasPerfil?: number;
  likes?: number;
  comments?: number;
  shares?: number;
}

export function csvOverview(dias: DiaOverview[]): Buffer {
  return csvStudio(
    ["Date", "Video Views", "Profile Views", "Likes", "Comments", "Shares"],
    dias.map((d) => [diaStudio(d.dia), d.views, d.visitasPerfil ?? 0, d.likes ?? 0, d.comments ?? 0, d.shares ?? 0]),
  );
}

export function csvSeguidores(dias: { dia: string; seguidores: number }[]): Buffer {
  return csvStudio(
    ["Date", "Followers", "Difference in followers from previous day"],
    dias.map((d, i) => [diaStudio(d.dia), d.seguidores, i === 0 ? 0 : d.seguidores - dias[i - 1]!.seguidores]),
  );
}

// Os dois ZIPs como o Studio entrega: `Overview_<1º dia>_<epoch do fim>_<handle>.zip` e
// `Followers_<handle>.zip` (com as 3 entradas extras só com cabeçalho). O epoch é 18:46 (−03) do
// último dia. Prontos para `setInputFiles`.
export function zipsStudio(handle: string, dias: (DiaOverview & { seguidores: number })[]) {
  const ultimo = dias[dias.length - 1]!.dia;
  const [y, m, d] = ultimo.split("-").map(Number);
  const epoch = Math.floor(Date.UTC(y!, m! - 1, d!, 21, 46, 14) / 1000);
  const vazio = (cab: string[]) => csvStudio(cab, []);
  return {
    overview: {
      name: `Overview_${dias[0]!.dia}_${epoch}_${handle}.zip`,
      mimeType: "application/zip",
      buffer: zipStudio([{ nome: "Overview.csv", dados: csvOverview(dias) }]),
    },
    seguidores: {
      name: `Followers_${handle}.zip`,
      mimeType: "application/zip",
      buffer: zipStudio([
        { nome: "FollowerHistory.csv", dados: csvSeguidores(dias) },
        { nome: "FollowerActivity.csv", dados: vazio(["Date", "Hour", "Active followers"]) },
        { nome: "FollowerGender.csv", dados: vazio(["Gender", "Distribution"]) },
        { nome: "FollowerTopTerritories.csv", dados: vazio(["Top territories", "Distribution"]) },
      ]),
    },
  };
}

// --- público do TikTok Studio (spec 022, T026) ---
// Tudo SINTÉTICO: os CSVs de público preenchidos no formato da 020 e um `Viewers.xlsx` de verdade
// (um ZIP "stored" com os XML mínimos, todas as células `t="str"`, como o real). Nunca o arquivo do dono.

export interface ItemDistribuicao {
  rotulo: string; // "Female", "BR"…
  pct: string; // como no arquivo: "61%", "37.5%"…
}
export interface LinhaAtividade {
  dia: string; // AAAA-MM-DD
  hora: number;
  ativos: number | "undefined";
}
export interface LinhaEspectadores {
  dia: string;
  total: number | "undefined";
  novos: number | "undefined";
  recorrentes: number | "undefined";
}

export const csvGenero = (itens: ItemDistribuicao[]) => csvStudio(["Gender", "Distribution"], itens.map((i) => [i.rotulo, i.pct]));
export const csvTerritorios = (itens: ItemDistribuicao[]) => csvStudio(["Top territories", "Distribution"], itens.map((i) => [i.rotulo, i.pct]));
export const csvAtividade = (linhas: LinhaAtividade[]) => csvStudio(["Date", "Hour", "Active followers"], linhas.map((l) => [diaStudio(l.dia), l.hora, l.ativos]));

const xmlEsc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const colunaXlsx = (i: number) => String.fromCharCode(65 + i); // até 4 colunas: A–D

// `Viewers.xlsx` mínimo. `defeito`: "formula" põe uma fórmula em B3; "macro" acrescenta um vbaProject.bin.
export function xlsxViewers(linhas: LinhaEspectadores[], defeito?: "formula" | "macro"): Buffer {
  const tabela: string[][] = [
    ["Date", "Total Viewers", "New Viewers", "Returning Viewers"],
    ...linhas.map((l) => [diaStudio(l.dia), String(l.total), String(l.novos), String(l.recorrentes)]),
  ];
  const rows = tabela
    .map((campos, r) => {
      const celulas = campos
        .map((v, c) => {
          const ref = `${colunaXlsx(c)}${r + 1}`;
          if (defeito === "formula" && ref === "B3") return `<c r="${ref}"><f>1+1</f><v>2</v></c>`;
          return `<c r="${ref}" t="str"><v>${xmlEsc(v)}</v></c>`;
        })
        .join("");
      return `<row r="${r + 1}">${celulas}</row>`;
    })
    .join("");
  const xml = (s: string) => Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n${s}`, "utf8");
  const ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"';
  const entradas = [
    {
      nome: "[Content_Types].xml",
      dados: xml(
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
          '<Default Extension="xml" ContentType="application/xml"/>' +
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
          "</Types>",
      ),
    },
    {
      nome: "_rels/.rels",
      dados: xml(
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
          '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
          "</Relationships>",
      ),
    },
    { nome: "xl/workbook.xml", dados: xml(`<workbook ${ns}><sheets><sheet name="Viewers" sheetId="1" r:id="rId1"/></sheets></workbook>`) },
    {
      nome: "xl/_rels/workbook.xml.rels",
      dados: xml(
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
          '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' +
          "</Relationships>",
      ),
    },
    { nome: "xl/worksheets/sheet1.xml", dados: xml(`<worksheet ${ns}><sheetData>${rows}</sheetData></worksheet>`) },
    ...(defeito === "macro" ? [{ nome: "xl/vbaProject.bin", dados: Buffer.from("macro sintetica") }] : []),
  ];
  return zipStudio(entradas);
}

export interface PublicoSintetico {
  genero?: ItemDistribuicao[];
  territorios?: ItemDistribuicao[];
  atividade?: LinhaAtividade[];
  espectadores?: LinhaEspectadores[];
  /** "formula"/"macro" no Viewers.xlsx */
  defeitoXlsx?: "formula" | "macro";
}

// Os ZIPs de público como o Studio entrega: `Followers_<handle>.zip` (o histórico + os 3 CSVs, cada um
// preenchido ou só com o cabeçalho) e `Viewers_<handle>.zip` (o `Viewers.xlsx` dentro).
export function zipsPublico(handle: string, seguidores: { dia: string; seguidores: number }[], p: PublicoSintetico) {
  return {
    seguidores: {
      name: `Followers_${handle}.zip`,
      mimeType: "application/zip",
      buffer: zipStudio([
        { nome: "FollowerHistory.csv", dados: csvSeguidores(seguidores) },
        { nome: "FollowerActivity.csv", dados: csvAtividade(p.atividade ?? []) },
        { nome: "FollowerGender.csv", dados: csvGenero(p.genero ?? []) },
        { nome: "FollowerTopTerritories.csv", dados: csvTerritorios(p.territorios ?? []) },
      ]),
    },
    espectadores: {
      name: `Viewers_${handle}.zip`,
      mimeType: "application/zip",
      buffer: zipStudio([{ nome: "Viewers.xlsx", dados: xlsxViewers(p.espectadores ?? [], p.defeitoXlsx) }]),
    },
  };
}

// --- MCP (spec 009, T030) ---

// Versão de protocolo do cliente do OpenClaw (@modelcontextprotocol/sdk 1.30.0).
export const MCP_PROTOCOLO = "2025-11-25";

export interface RespostaMcp {
  status: number;
  headers: Headers;
  // corpo JSON-RPC (ou o JSON de erro HTTP); null quando não veio JSON
  body: { result?: Record<string, unknown>; error?: { code: number; message: string }; [k: string]: unknown } | null;
}

// Chama o `/mcp` do edge efêmero com o Bearer de um cliente MCP. Usa o `fetch` do Node, e não o
// `request` do Playwright, para o token não entrar em trace nem em relatório. `extras.headers`
// sobrescreve cabeçalhos (ex.: `Origin`); `extras.semToken` manda sem Authorization.
export async function chamarMcp(
  token: string,
  metodo: string,
  params: Record<string, unknown> = {},
  extras: { headers?: Record<string, string>; semToken?: boolean } = {},
): Promise<RespostaMcp> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
    "MCP-Protocol-Version": MCP_PROTOCOLO,
    ...(extras.semToken ? {} : { Authorization: `Bearer ${token}` }),
    ...extras.headers,
  };
  const res = await fetch(`${BASE_URL}/mcp`, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", id: randomUUID(), method: metodo, params }),
  });
  const texto = await res.text();
  let body: RespostaMcp["body"] = null;
  try {
    body = JSON.parse(texto) as RespostaMcp["body"];
  } catch {
    // SSE de uma mensagem só: pega o último `data:`
    const data = texto.split("\n").filter((l) => l.startsWith("data:")).pop();
    if (data) body = JSON.parse(data.slice(5)) as RespostaMcp["body"];
  }
  return { status: res.status, headers: res.headers, body };
}

// `tools/call` de uma tool: devolve o `result` do JSON-RPC (com `isError` e `structuredContent`).
export async function chamarTool(token: string, nome: string, args: Record<string, unknown> = {}): Promise<RespostaMcp> {
  return chamarMcp(token, "tools/call", { name: nome, arguments: args });
}

export interface ClienteMcpE2e {
  id: string;
  nome: string;
  token: string; // só em memória, nunca em arquivo nem log
  version: number;
}

// Cria um cliente MCP pela API (dono humano) e devolve o token emitido UMA vez.
export async function criarClienteMcp(
  request: APIRequestContext,
  donoToken: string,
  nome: string,
  escopo: "leitura" | "propostas",
  extras: { limitePorMinuto?: number; limiteEscritasDia?: number } = {},
): Promise<ClienteMcpE2e> {
  const res = await request.post("/api/mcp/clientes", {
    headers: { Authorization: `Bearer ${donoToken}` },
    data: { nome, escopo, ...extras },
  });
  expect(res.status(), `POST /api/mcp/clientes (${nome})`).toBe(201);
  const body = (await res.json()) as { cliente: { id: string; nome: string; version: number }; token: string };
  return { id: body.cliente.id, nome: body.cliente.nome, token: body.token, version: body.cliente.version };
}

// Liga ou desliga o interruptor da tela (o servidor da stack e2e já vem com MCP_HABILITADO=true).
export async function interruptorMcp(request: APIRequestContext, donoToken: string, habilitado: boolean): Promise<void> {
  const auth = { Authorization: `Bearer ${donoToken}` };
  const atual = await request.get("/api/mcp/config", { headers: auth });
  expect(atual.status(), "GET /api/mcp/config").toBe(200);
  const { version } = (await atual.json()) as { version: number };
  const res = await request.put("/api/mcp/config", { headers: auth, data: { version, habilitado } });
  expect(res.status(), "PUT /api/mcp/config").toBe(200);
}
