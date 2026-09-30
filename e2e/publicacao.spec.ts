import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER, PG_DB, PG_USER } from "./fixtures";
import {
  apiToken,
  compose,
  createPerfilViaApi,
  createVerifiedMember,
  falharTikTok,
  interceptarLoginTikTok,
  login,
  logout,
  pedidosTikTok,
  syntheticMp4,
  type Member,
} from "./helpers";

// Spec 015 (T039, T040, T059, T070): conexão, rascunho no horário e o interruptor, na stack
// isolada com a TikTok FALSA do `openshorts-fake` (`TIKTOK_API_URL`) e o `agendador` com a trilha
// `publicacao` a cada 2 s. O login no navegador é interceptado (`interceptarLoginTikTok`): nada
// sai da máquina. Em todos os testes, o navegador nunca fala com a TikTok real (só o login
// interceptado), e um teste próprio prova que a API e o agendador só enxergam a falsa.
// US3 (T090): "Publicar no horário" com a tela obrigatória, no sandbox (só "Só você").

const SHOTS = ".playwright-mcp/sociman";
const TIKTOK_REAL = /tiktok\.com|tiktokapis\.com|tiktokcdn/i;

type Auth = { Authorization: string };

interface Tentativa {
  numero: number;
  fase: string;
  disparo: string;
  publishId: string | null;
  motivo: string | null;
  partesEnviadas: number;
  totalPartes: number;
}

interface Destino {
  id: string;
  conteudoId: string;
  conta: { id: string; handle: string };
  estado: string;
  estadoEfetivo: string;
  modo: string;
  plannedAt: string | null;
  falhaIncerta: boolean;
  version: number;
}

interface Conexao {
  estado: string;
  username: string | null;
  displayName: string | null;
  avatarUrl: string | null;
  modos: { modo: string; disponivel: boolean; motivo: string | null }[];
  version?: number;
}

interface Version {
  details: Record<string, unknown> & { acao?: string };
  actor: { name: string } | null;
}

// ---------------------------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------------------------

async function getJson<T>(request: APIRequestContext, auth: Auth, url: string): Promise<T> {
  const res = await request.get(url, { headers: auth });
  expect(res.status(), `GET ${url}: ${res.status() === 200 ? "" : await res.text()}`).toBe(200);
  return (await res.json()) as T;
}

async function acoes(request: APIRequestContext, auth: Auth, url: string): Promise<(string | undefined)[]> {
  return (await getJson<{ items: Version[] }>(request, auth, url)).items.map((v) => v.details.acao);
}

// Perfil novo com uma conta TikTok ativa; o @ é o que a TikTok falsa devolve no login.
async function perfilComConta(request: APIRequestContext, token: string, nome: string, sfx: string) {
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `${nome} ${sfx}`, slug: `${nome.toLowerCase()}-${sfx}` });
  const handle = `${nome.toLowerCase()}${sfx}`;
  const res = await request.post(`/api/perfis/${perfilId}/contas`, {
    headers: auth,
    data: { platform: "tiktok", handle, status: "ativa" },
  });
  expect(res.status(), `POST contas: ${await res.text()}`).toBe(201);
  const contaId = ((await res.json()) as { conta: { id: string } }).conta.id;
  return { perfilId, contaId, handle };
}

async function conexao(request: APIRequestContext, auth: Auth, contaId: string): Promise<Conexao> {
  return (await getJson<{ conexao: Conexao }>(request, auth, `/api/contas/${contaId}/conexao`)).conexao;
}

// Conecta pela API (o fluxo pelo navegador é coberto na US1): iniciar → o "login" devolve
// `code=e2e-<handle>` com o mesmo `state` → retorno.
async function conectarViaApi(request: APIRequestContext, auth: Auth, contaId: string, handle: string): Promise<void> {
  const ini = await request.post(`/api/contas/${contaId}/conexao/iniciar`, { headers: auth, data: {} });
  expect(ini.status(), `iniciar: ${await ini.text()}`).toBe(200);
  const url = new URL(((await ini.json()) as { autorizarUrl: string }).autorizarUrl);
  const ret = await request.post("/api/conexoes/retorno", {
    headers: auth,
    data: { state: url.searchParams.get("state"), code: `e2e-${handle}` },
  });
  expect(ret.status(), `retorno: ${await ret.text()}`).toBe(200);
  expect((await conexao(request, auth, contaId)).estado).toBe("conectada");
}

// Liga ou desliga o botão "Publicação automática" pela API (a tela é coberta na US4).
async function enviosAutomaticos(request: APIRequestContext, auth: Auth, ligado: boolean): Promise<void> {
  const { config } = await getJson<{ config: { version: number; enviosHabilitados: boolean } }>(request, auth, "/api/publicacao/config");
  if (config.enviosHabilitados === ligado) return;
  const res = await request.put("/api/publicacao/config", {
    headers: auth,
    data: { version: config.version, enviosHabilitados: ligado },
  });
  expect(res.status(), `PUT config: ${await res.text()}`).toBe(200);
}

async function videoProprio(request: APIRequestContext, auth: Auth, perfilId: string, video: Buffer, titulo: string): Promise<string> {
  const res = await request.post(`/api/perfis/${perfilId}/conteudos/arquivo`, {
    headers: auth,
    multipart: { file: { name: `${titulo}.mp4`, mimeType: "video/mp4", buffer: video }, titulo },
  });
  expect(res.status(), `POST conteudos/arquivo (${titulo}): ${await res.text()}`).toBe(201);
  return ((await res.json()) as { conteudo: { id: string } }).conteudo.id;
}

async function enviarCorte(request: APIRequestContext, auth: Auth, perfilId: string, video: string, gancho: string): Promise<string> {
  const res = await request.post(`/api/perfis/${perfilId}/cortes`, {
    headers: auth,
    multipart: { file: { name: "corte.mp4", mimeType: "video/mp4", buffer: readFileSync(video) }, hookText: gancho },
  });
  expect(res.status(), `POST cortes: ${await res.text()}`).toBe(201);
  const corteId = ((await res.json()) as { corte: { id: string } }).corte.id;
  await expect
    .poll(async () => (await getJson<{ corte: { status: string } }>(request, auth, `/api/cortes/${corteId}`)).corte.status, {
      timeout: 180_000,
      intervals: [1_000, 2_000],
      message: `corte ${corteId} não ficou pronto`,
    })
    .toBe("pronto");
  return corteId;
}

async function agendarRascunho(
  request: APIRequestContext,
  auth: Auth,
  body: { conteudoId: string; contaId: string; plannedAt: string; titulo: string },
): Promise<Destino> {
  const res = await request.post("/api/agendamentos", {
    headers: auth,
    data: {
      conteudoId: body.conteudoId,
      contaId: body.contaId,
      plannedAt: body.plannedAt,
      modo: "criar_rascunho",
      ignorarIntervalo: true,
      textos: { descricao: body.titulo },  // na TikTok, a legenda (descrição) é obrigatória
    },
  });
  expect([200, 201], `POST /api/agendamentos: ${await res.text()}`).toContain(res.status());
  return ((await res.json()) as { destino: Destino }).destino;
}

async function destino(request: APIRequestContext, auth: Auth, id: string): Promise<Destino> {
  return (await getJson<{ destino: Destino }>(request, auth, `/api/destinos/${id}`)).destino;
}

async function tentativas(request: APIRequestContext, auth: Auth, id: string): Promise<Tentativa[]> {
  return (await getJson<{ items: Tentativa[] }>(request, auth, `/api/destinos/${id}/tentativas`)).items;
}

async function esperarEstado(request: APIRequestContext, auth: Auth, id: string, estado: string, timeout = 120_000): Promise<void> {
  await expect
    .poll(async () => (await destino(request, auth, id)).estado, { timeout, intervals: [1_000, 2_000], message: `destino ${id} → ${estado}` })
    .toBe(estado);
}

function inits(handle: string): number {
  return pedidosTikTok(handle).filter((p) => p.endpoint === "inbox_init" || p.endpoint === "video_init").length;
}

function envios(handle: string): number {
  return pedidosTikTok(handle).filter((p) => ["inbox_init", "video_init", "put"].includes(p.endpoint)).length;
}

// Horário daqui a `ms`, em ISO (a API aceita qualquer offset).
function daquiA(ms: number): string {
  return new Date(Date.now() + ms).toISOString();
}

// "2026-09-30T19:07" em São Paulo (para o <input type="datetime-local">), no próximo minuto cheio
// que esteja pelo menos `minMs` à frente.
function proximoMinutoSp(minMs: number): string {
  const alvo = new Date(Math.ceil((Date.now() + minMs) / 60_000) * 60_000);
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Sao_Paulo",
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
      .formatToParts(alvo)
      .map((x) => [x.type, x.value]),
  );
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

// ---------------------------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------------------------

async function abrirContas(page: Page, perfilId: string): Promise<void> {
  await page.goto(`/app/perfis/${perfilId}`);
  await page.getByRole("tab", { name: "Contas", exact: true }).click();
}

function sino(page: Page): Locator {
  return page.getByRole("button", { name: /^Notificações/ });
}

async function esperarNoSino(page: Page, nome: RegExp, timeout = 60_000): Promise<void> {
  await expect
    .poll(
      async () => {
        await page.reload();
        await sino(page).click();
        const n = await page.getByRole("menuitem", { name: nome }).count();
        await page.keyboard.press("Escape");
        return n;
      },
      { timeout, intervals: [2_000, 5_000] },
    )
    .toBeGreaterThan(0);
}

// Recarrega o destino até o texto aparecer no painel da conta (a tela não tem tempo real).
async function esperarNoPainel(page: Page, texto: string | RegExp, timeout = 120_000): Promise<void> {
  await expect(async () => {
    await page.reload();
    await expect(page.getByRole("tabpanel").getByText(texto).first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout, intervals: [1_000, 2_000] });
}

// Princípio I no navegador: toda requisição para um domínio da TikTok. Só o login interceptado
// (que nunca sai da máquina) pode aparecer.
function vigiarTikTok(page: Page): string[] {
  const vistos: string[] = [];
  page.on("request", (req) => {
    if (TIKTOK_REAL.test(req.url())) vistos.push(req.url());
  });
  return vistos;
}

function soLoginInterceptado(vistos: string[], interceptados: string[][]): void {
  const logins = interceptados.flat();
  for (const url of vistos) {
    expect(url, "o navegador só vai à TikTok pelo login interceptado").toMatch(/^https:\/\/www\.tiktok\.com\/v2\/auth\/authorize\//);
  }
  expect(vistos.length, "cada ida à TikTok foi interceptada").toBe(logins.length);
}

async function conectarPelaTela(page: Page, perfilId: string, handle: string): Promise<string[]> {
  const interceptados = await interceptarLoginTikTok(page, handle);
  await abrirContas(page, perfilId);
  await page.getByRole("button", { name: "Conectar", exact: true }).click();
  return interceptados;
}

// ---------------------------------------------------------------------------------------------
// US1 (T040): conectar, conta diferente, membro sem botões, desconectar e reconectar
// ---------------------------------------------------------------------------------------------
test("US1: o dono conecta a conta TikTok; conta diferente é recusada; membro só vê o estado", async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);
  const vistos = vigiarTikTok(page);
  const logins: string[][] = [];
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Taverna", sfx);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 2);
  const conteudo = await videoProprio(request, auth, p.perfilId, readFileSync(video), `Conexao ${sfx}`);
  const member: Member = await createVerifiedMember(page);

  // ---- antes de conectar: os modos automáticos pedem a conexão ----
  const antes = await conexao(request, auth, p.contaId);
  expect(antes.estado).toBe("nao_conectada");
  expect(antes.modos.find((m) => m.modo === "criar_rascunho")?.disponivel).toBe(false);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  // ---- login com outra conta TikTok: recusado com a explicação, nada gravado ----
  logins.push(await conectarPelaTela(page, p.perfilId, `outra${sfx}`));
  await expect(page).toHaveURL(/\/app\/conexoes\/retorno/);
  const recusa = page.getByRole("alert");
  await expect(recusa).toContainText("Você entrou com outra conta da TikTok");
  await expect(recusa).toContainText(`Você autorizou @outra${sfx}, mas esta conta é @${p.handle}`);
  await expect(page.getByRole("button", { name: "Tentar de novo" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/015-conta-diferente.png`, fullPage: true });
  expect((await conexao(request, auth, p.contaId)).estado).toBe("nao_conectada");
  expect(await acoes(request, auth, `/api/contas/${p.contaId}/conexao/versions`)).toEqual([]);

  // ---- a conta certa: "Conectada" com @, apelido e modos ----
  logins.push(await conectarPelaTela(page, p.perfilId, p.handle));
  await expect(page).toHaveURL(new RegExp(`/app/perfis/${p.perfilId}`));
  const painel = page.getByRole("tabpanel");
  await expect(painel.getByText("Conectada", { exact: true }).first()).toBeVisible();
  await expect(painel.getByText(`Apelido ${p.handle}`).first()).toBeVisible();
  await expect(painel.getByRole("button", { name: "Desconectar" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/015-conexao-conectada.png`, fullPage: true });
  const c1 = await conexao(request, auth, p.contaId);
  expect(c1).toMatchObject({ estado: "conectada", username: p.handle, displayName: `Apelido ${p.handle}` });
  expect(c1.avatarUrl, "avatar pelo /img (sem abrir a CSP)").toMatch(/^\/img\//);
  expect(c1.modos.find((m) => m.modo === "criar_rascunho")?.disponivel).toBe(true);
  // pelo localhost é o Login Kit Desktop: a troca do código leva o PKCE
  const troca = pedidosTikTok(p.handle).find((x) => x.endpoint === "token" && x.grant === "authorization_code");
  expect(troca?.pkce, "troca do código com code_verifier").toBe(true);
  expect(await acoes(request, auth, `/api/contas/${p.contaId}/conexao/versions`)).toContain("conectada");
  await logout(page);

  // ---- membro: vê o estado, sem Conectar/Desconectar, sem a tela de configuração e sem o modo ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await abrirContas(page, p.perfilId);
  await expect(page.getByRole("tabpanel").getByText("Conectada", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Conectar", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Desconectar" })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/015-conexao-membro.png`, fullPage: true });
  await expect(page.getByRole("link", { name: "Publicação automática" })).toHaveCount(0);
  const memberAuth = { Authorization: `Bearer ${await apiToken(request, member.email, member.final)}` };
  const ini = await request.post(`/api/contas/${p.contaId}/conexao/iniciar`, { headers: memberAuth, data: {} });
  expect(ini.status(), "membro não conecta").toBe(403);
  const ag = await request.post("/api/agendamentos", {
    headers: memberAuth,
    data: { conteudoId: conteudo, contaId: p.contaId, plannedAt: daquiA(86_400_000), modo: "criar_rascunho", textos: { descricao: `Legenda ${sfx}` } },
  });
  expect(ag.status(), "membro não agenda em modo automático").toBe(403);
  const cfg = await request.put("/api/publicacao/config", { headers: memberAuth, data: { version: 1, enviosHabilitados: true } });
  expect(cfg.status(), "membro não mexe no interruptor").toBe(403);
  await logout(page);

  // ---- dono desconecta (credencial apagada, revogação na TikTok) e reconecta ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrirContas(page, p.perfilId);
  await page.getByRole("button", { name: "Desconectar" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Desconectar" }).click();
  await expect(page.getByRole("tabpanel").getByText("Não conectada", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Conectar", exact: true })).toBeVisible();
  expect((await conexao(request, auth, p.contaId)).estado).toBe("nao_conectada");
  expect(pedidosTikTok(p.handle).some((x) => x.endpoint === "revoke"), "revogação em melhor esforço").toBe(true);
  await page.screenshot({ path: `${SHOTS}/015-conexao-desconectada.png`, fullPage: true });

  logins.push(await conectarPelaTela(page, p.perfilId, p.handle));
  await expect(page).toHaveURL(new RegExp(`/app/perfis/${p.perfilId}`));
  await expect(page.getByRole("tabpanel").getByText("Conectada", { exact: true }).first()).toBeVisible();
  expect((await conexao(request, auth, p.contaId)).username).toBe(p.handle);
  expect(await acoes(request, auth, `/api/contas/${p.contaId}/conexao/versions`)).toEqual(
    expect.arrayContaining(["conectada", "desconectada"]),
  );

  // nenhum envio aconteceu nesta história
  expect(envios(p.handle)).toBe(0);
  soLoginInterceptado(vistos, logins);
});

// ---------------------------------------------------------------------------------------------
// US2 (T059): corte pronto em "Criar rascunho" daqui a ~1 min → Enviando → Rascunho criado
// ---------------------------------------------------------------------------------------------
test("US2: rascunho criado no horário, com Copiar textos e Postado", async ({ page, request, context }, testInfo) => {
  test.setTimeout(420_000);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const vistos = vigiarTikTok(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Rascunho", sfx);
  await conectarViaApi(request, auth, p.contaId, p.handle);
  await enviosAutomaticos(request, auth, true);
  const video = testInfo.outputPath("corte.mp4");
  syntheticMp4(video, 3);
  const corte = await enviarCorte(request, auth, p.perfilId, video, `Rascunho ${sfx}`);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/cortes/${corte}`);
  await page.getByRole("button", { name: "Agendar" }).first().click();
  const dlg = page.getByRole("dialog", { name: "Agendar" });
  const conta = dlg.getByLabel("Conta").and(page.locator("select")).first();
  const opcao = conta.locator("option").filter({ hasText: p.handle }).first();
  await conta.selectOption((await opcao.getAttribute("value"))!);
  await dlg.getByLabel(/Data e hora/).fill(proximoMinutoSp(45_000));
  const modo = dlg.getByLabel("Modo", { exact: true });
  await expect(modo.locator("option[value=criar_rascunho]")).toBeEnabled();
  await modo.selectOption("criar_rascunho");
  // TikTok não tem título: só a legenda (descrição + hashtags), obrigatória para agendar
  await expect(dlg.getByLabel("Título", { exact: true })).toHaveCount(0);
  await dlg.getByRole("textbox", { name: /^Legenda/ }).fill("");
  await expect(dlg).toContainText("Descreva o post: na TikTok a legenda (descrição + hashtags) é obrigatória.");
  await expect(dlg.getByRole("button", { name: "Aprovar e agendar" })).toBeDisabled();
  await dlg.getByRole("textbox", { name: /^Legenda/ }).fill(`Legenda do rascunho ${sfx}`);
  const hashtags = dlg.getByLabel("Hashtags", { exact: true });
  for (const h of ["#achados", "#e2e"]) {
    await hashtags.fill(h);
    await hashtags.press("Enter");
  }
  const legenda = `Legenda do rascunho ${sfx}\n\n#achados #e2e`;
  await expect(dlg.getByRole("region", { name: "Legenda final" })).toContainText(`Legenda do rascunho ${sfx}`);
  await page.screenshot({ path: `${SHOTS}/015-agendar-rascunho.png`, fullPage: true });
  await dlg.getByRole("button", { name: "Aprovar e agendar" }).click();
  await expect(dlg).toBeHidden();

  const [d] = (await getJson<{ conteudo: { destinos: Destino[] } }>(request, auth, `/api/conteudos/${corte}`)).conteudo.destinos;
  expect(d).toMatchObject({ estado: "agendado", modo: "criar_rascunho" });
  expect(inits(p.handle), "nada sai antes do horário").toBe(0);

  // ---- no horário: "Enviando" e depois "Rascunho criado" ----
  let visto = "";
  await expect
    .poll(async () => (visto = JSON.stringify(await destino(request, auth, d.id))) && JSON.parse(visto).estado, {
      timeout: 150_000,
      intervals: [500],
      message: "o destino passa por enviando",
    })
    .toBe("enviando");
  await page.goto(`/app/conteudos/${corte}?conta=${p.contaId}`);
  await expect(page.getByRole("tabpanel").getByText("Enviando para TikTok").first(), visto).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/015-enviando.png`, fullPage: true });
  await expect
    .poll(async () => (visto = JSON.stringify({ d: await destino(request, auth, d.id), t: await tentativas(request, auth, d.id) })) && JSON.parse(visto).d.estado, {
      timeout: 120_000,
      intervals: [1_000],
      message: "o destino chega a rascunho_criado",
    })
    .toBe("rascunho_criado");
  await esperarNoPainel(page, "Rascunho criado na caixa de entrada", 30_000);
  await page.screenshot({ path: `${SHOTS}/015-rascunho-criado.png`, fullPage: true });
  expect((await destino(request, auth, d.id)).estado).toBe("rascunho_criado");
  const [t] = await tentativas(request, auth, d.id);
  expect(t).toMatchObject({ numero: 1, fase: "entregue", disparo: "agendador" });
  expect(t.publishId).toBeTruthy();
  expect(t.partesEnviadas).toBe(t.totalPartes);
  // na TikTok falsa: UM init de inbox, sem textos (a API do inbox não recebe post_info), e as partes
  const pedidos = pedidosTikTok(p.handle);
  expect(pedidos.filter((x) => x.endpoint === "inbox_init")).toHaveLength(1);
  expect(pedidos.find((x) => x.endpoint === "inbox_init")?.post_info).toBe(false);
  expect(pedidos.filter((x) => x.endpoint === "video_init")).toHaveLength(0);
  expect(pedidos.filter((x) => x.endpoint === "put").length).toBe(t.totalPartes);

  // ---- sino: "Rascunho na TikTok" leva ao destino; "Copiar textos" põe a legenda composta na área de transferência ----
  await esperarNoSino(page, /Rascunho na TikTok/);
  await sino(page).click();
  await page.getByRole("menuitem", { name: /Rascunho na TikTok/ }).first().click();
  await expect(page).toHaveURL(new RegExp(`/app/conteudos/${corte}\\?conta=${p.contaId}`));
  const aba = page.getByRole("tabpanel");
  await aba.getByRole("button", { name: "Copiar textos" }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(legenda);

  // ---- o dono publica no app e marca "Postado" ----
  await aba.getByRole("button", { name: "Marcar como postado" }).click();
  const postado = page.getByRole("dialog", { name: "Marcar como postado" });
  await postado.getByLabel("Link do post (opcional)").fill("https://example.com/post/rascunho-e2e");
  await postado.getByRole("button", { name: "Confirmar postado" }).click();
  await expect(aba.getByText("Postado", { exact: true }).first()).toBeVisible();
  expect((await destino(request, auth, d.id)).estado).toBe("postado");
  expect(await acoes(request, auth, `/api/destinos/${d.id}/versions`)).toEqual(
    expect.arrayContaining(["aprovado", "agendado", "envio_iniciado", "rascunho_criado"]),
  );
  expect(inits(p.handle), "nunca dois inits para o mesmo agendamento").toBe(1);
  soLoginInterceptado(vistos, []);
});

// ---------------------------------------------------------------------------------------------
// US2 (T059): falha com motivo e "Tentar de novo"; incerta exige a confirmação (Q4)
// ---------------------------------------------------------------------------------------------
test("US2: falha com motivo em pt-BR e Tentar de novo; incerta pede a confirmação", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const vistos = vigiarTikTok(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Falhas", sfx);
  await conectarViaApi(request, auth, p.contaId, p.handle);
  await enviosAutomaticos(request, auth, true);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 2);
  const buf = readFileSync(video);
  const recusado = await videoProprio(request, auth, p.perfilId, buf, `Recusado ${sfx}`);
  const incerto = await videoProprio(request, auth, p.perfilId, buf, `Incerto ${sfx}`);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  // ---- a TikTok recusa no processamento: "Falhou" com o motivo e "Tentar de novo" ----
  falharTikTok(p.handle, "status", "internal");
  const d1 = await agendarRascunho(request, auth, { conteudoId: recusado, contaId: p.contaId, plannedAt: daquiA(3_000), titulo: `Recusado ${sfx}` });
  await esperarEstado(request, auth, d1.id, "falhou");
  expect((await destino(request, auth, d1.id)).falhaIncerta).toBe(false);
  await page.goto(`/app/conteudos/${recusado}?conta=${p.contaId}`);
  const aba = page.getByRole("tabpanel");
  await expect(aba.getByText("Falhou o envio para TikTok").first()).toBeVisible();
  await expect(aba.getByText("A TikTok teve um erro interno ao processar o vídeo").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/015-falhou.png`, fullPage: true });
  await aba.getByRole("button", { name: "Tentar de novo" }).click();
  const confirmar1 = page.getByRole("dialog", { name: "Tentar de novo?" });
  await expect(confirmar1.getByRole("checkbox")).toHaveCount(0);
  await confirmar1.getByRole("button", { name: "Tentar de novo" }).click();
  await esperarEstado(request, auth, d1.id, "rascunho_criado");
  const t1 = await tentativas(request, auth, d1.id);
  expect(t1.map((t) => [t.numero, t.fase, t.disparo])).toEqual([
    [2, "entregue", "tentar_de_novo"],
    [1, "recusada", "agendador"],
  ]);

  // ---- a resposta do init se perde: "Falhou: a TikTok pode ter recebido" ----
  falharTikTok(p.handle, "inbox_init", "sem_resposta");
  const d2 = await agendarRascunho(request, auth, { conteudoId: incerto, contaId: p.contaId, plannedAt: daquiA(3_000), titulo: `Incerto ${sfx}` });
  await esperarEstado(request, auth, d2.id, "falhou");
  const incerta = await destino(request, auth, d2.id);
  expect(incerta.falhaIncerta).toBe(true);
  expect((await tentativas(request, auth, d2.id))[0].fase).toBe("incerta");
  const initsAntes = inits(p.handle);
  // a API recusa "Tentar de novo" sem a confirmação (Q4); nada volta à fila
  const semConfirmar = await request.post(`/api/destinos/${d2.id}/tentar-de-novo`, { headers: auth, data: { version: incerta.version } });
  expect(semConfirmar.status()).toBe(409);
  expect(((await semConfirmar.json()) as { error: { code: string } }).error.code).toBe("confirmacao_necessaria");
  await page.waitForTimeout(5_000); // duas voltas da trilha
  expect(inits(p.handle), "o init nunca se repete sozinho").toBe(initsAntes);
  expect((await destino(request, auth, d2.id)).estado).toBe("falhou");

  await page.goto(`/app/conteudos/${incerto}?conta=${p.contaId}`);
  await expect(aba.getByText(/pode ter recebido/).first()).toBeVisible();
  await aba.getByRole("button", { name: "Tentar de novo" }).click();
  const confirmar2 = page.getByRole("dialog", { name: "Tentar de novo?" });
  const conferi = confirmar2.getByRole("checkbox", { name: /Conferi no app e o rascunho não chegou/ });
  await expect(conferi).toBeVisible();
  const botao = confirmar2.getByRole("button", { name: "Tentar de novo" });
  await expect(botao).toBeDisabled();
  await page.screenshot({ path: `${SHOTS}/015-incerta-confirmacao.png`, fullPage: true });
  await conferi.check();
  await botao.click();
  await esperarEstado(request, auth, d2.id, "rascunho_criado");
  expect(inits(p.handle)).toBe(initsAntes + 1);
  // um init por tentativa, nunca mais: recusado (2) + incerto (2)
  expect(inits(p.handle)).toBe(4);
  soLoginInterceptado(vistos, []);
});

// ---------------------------------------------------------------------------------------------
// US4 (T070): interruptor desligado → "Pausado" e nada enviado; religar envia; vencido pede
// "Confirmar envio agora"
// ---------------------------------------------------------------------------------------------
test("US4: interruptor da tela pausa os envios; vencido pede confirmação do dono", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const vistos = vigiarTikTok(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Interruptor", sfx);
  await conectarViaApi(request, auth, p.contaId, p.handle);
  await enviosAutomaticos(request, auth, true);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 2);
  const buf = readFileSync(video);
  const pausado = await videoProprio(request, auth, p.perfilId, buf, `Pausado ${sfx}`);
  const vencido = await videoProprio(request, auth, p.perfilId, buf, `Vencido ${sfx}`);

  // ---- a tela: desligar "Publicação automática" ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/configuracoes/publicacao");
  const chave = page.getByRole("switch", { name: /Publicação automática/ });
  await expect(chave).toBeChecked();
  await chave.click(); // desligar não pede confirmação
  await expect(chave).not.toBeChecked();
  await page.screenshot({ path: `${SHOTS}/015-config-desligado.png`, fullPage: true });

  // ---- no horário, com o botão desligado: "Pausado" e nenhum pedido de envio na TikTok ----
  const d1 = await agendarRascunho(request, auth, { conteudoId: pausado, contaId: p.contaId, plannedAt: daquiA(3_000), titulo: `Pausado ${sfx}` });
  await expect
    .poll(async () => (await destino(request, auth, d1.id)).estadoEfetivo, { timeout: 30_000 })
    .toBe("pausado");
  await page.waitForTimeout(6_000); // três voltas da trilha
  expect((await destino(request, auth, d1.id)).estado).toBe("agendado");
  expect(envios(p.handle), "nenhum init e nenhuma parte com o interruptor desligado").toBe(0);
  await page.goto(`/app/conteudos/${pausado}?conta=${p.contaId}`);
  await expect(page.getByRole("tabpanel").getByText("Pausado: nada foi enviado").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/015-pausado.png`, fullPage: true });

  // ---- religar (com a confirmação): o pausado sai na próxima volta ----
  await page.goto("/app/configuracoes/publicacao");
  await chave.click();
  const ligar = page.getByRole("alertdialog");
  await expect(ligar).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/015-config-ligar.png`, fullPage: true });
  await ligar.getByRole("button", { name: "Ligar", exact: true }).click();
  await expect(chave).toBeChecked();
  await esperarEstado(request, auth, d1.id, "rascunho_criado");
  expect(inits(p.handle)).toBe(1);

  // ---- vencido (horário há 2 h, gravado no banco da stack e2e): nada sai sem "Confirmar envio agora" ----
  const d2 = await agendarRascunho(request, auth, { conteudoId: vencido, contaId: p.contaId, plannedAt: daquiA(86_400_000), titulo: `Vencido ${sfx}` });
  compose([
    "exec", "-T", "postgres", "psql", "-U", PG_USER, "-d", PG_DB, "-v", "ON_ERROR_STOP=1", "-c",
    `update postagens set planned_at = now() - interval '2 hours' where id = '${d2.id}'`,
  ]);
  await expect.poll(async () => (await destino(request, auth, d2.id)).estadoEfetivo, { timeout: 15_000 }).toBe("vencido");
  await page.waitForTimeout(6_000);
  expect(inits(p.handle), "vencido não sai sozinho").toBe(1);
  const cfg = await getJson<{ config: { vencidos: number } }>(request, auth, "/api/publicacao/config");
  expect(cfg.config.vencidos).toBeGreaterThanOrEqual(1);
  await page.goto(`/app/conteudos/${vencido}?conta=${p.contaId}`);
  const aba = page.getByRole("tabpanel");
  await expect(aba.getByText("Vencido: passou do horário há mais de 1 hora").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/015-vencido.png`, fullPage: true });
  await aba.getByRole("button", { name: "Confirmar envio agora" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Confirmar envio agora" }).click();
  await esperarEstado(request, auth, d2.id, "rascunho_criado");
  expect(inits(p.handle)).toBe(2);
  const [t2] = await tentativas(request, auth, d2.id);
  expect(t2.disparo).toBe("confirmado");
  expect(await acoes(request, auth, `/api/destinos/${d2.id}/versions`)).toEqual(
    expect.arrayContaining(["envio_confirmado", "envio_iniciado", "rascunho_criado"]),
  );
  soLoginInterceptado(vistos, []);
});

// ---------------------------------------------------------------------------------------------
// US3 (T090): "Publicar no horário" com a tela obrigatória da TikTok (sandbox: só "Só eu")
// ---------------------------------------------------------------------------------------------
test("US3: publicar no horário exige a tela da TikTok e chega a Publicado", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const vistos = vigiarTikTok(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Publicar", sfx);
  await conectarViaApi(request, auth, p.contaId, p.handle);
  await enviosAutomaticos(request, auth, true);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 3);
  const conteudo = await videoProprio(request, auth, p.perfilId, readFileSync(video), `Publicar ${sfx}`);

  // ---- a API: parceria paga como "só você" é recusada, com o problema; nada é gravado ----
  const opcoes = (privacidade: string, comercial: string) => ({
    privacidade,
    permitirComentario: true,
    permitirDueto: false,
    permitirCostura: false,
    comercial,
    conteudoIa: false,
    consentimento: {
      texto: "Ao postar, você concorda com a Política de Conteúdo de Marca e com a Confirmação de Uso de Música da TikTok.",
      aceitoEm: new Date().toISOString(),
    },
  });
  const recusa = await request.post("/api/agendamentos", {
    headers: auth,
    data: { conteudoId: conteudo, contaId: p.contaId, plannedAt: daquiA(86_400_000), modo: "publicar", opcoes: opcoes("SELF_ONLY", "parceria_paga"), textos: { descricao: `Legenda ${sfx}` } },
  });
  expect(recusa.status(), await recusa.text()).toBe(400);
  const erro = ((await recusa.json()) as { error: { code: string; details: { problemas: { campo: string }[] } } }).error;
  expect(erro.code).toBe("opcoes_invalidas");
  expect(erro.details.problemas.map((x) => x.campo)).toContain("comercial");
  // sem as opções, também não agenda
  const semOpcoes = await request.post("/api/agendamentos", {
    headers: auth,
    data: { conteudoId: conteudo, contaId: p.contaId, plannedAt: daquiA(86_400_000), modo: "publicar", textos: { descricao: `Legenda ${sfx}` } },
  });
  expect(semOpcoes.status()).toBe(400);
  // sem legenda, nenhum modo agenda na TikTok (nem o lembrete): 400 legenda_obrigatoria
  for (const m of ["lembrete", "criar_rascunho", "publicar"]) {
    const semLegenda = await request.post("/api/agendamentos", {
      headers: auth,
      data: {
        conteudoId: conteudo, contaId: p.contaId, plannedAt: daquiA(86_400_000), modo: m,
        ...(m === "publicar" ? { opcoes: opcoes("SELF_ONLY", "nenhum") } : {}),
      },
    });
    expect(semLegenda.status(), `sem legenda (${m}): ${await semLegenda.text()}`).toBe(400);
    expect(((await semLegenda.json()) as { error: { code: string } }).error.code).toBe("legenda_obrigatoria");
  }
  expect(((await getJson<{ conteudo: { destinos: Destino[] } }>(request, auth, `/api/conteudos/${conteudo}`)).conteudo.destinos)).toEqual([]);

  // ---- a tela: dados da conta na hora, privacidade sem valor, toggles desmarcados ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos/${conteudo}`);
  await page.getByRole("button", { name: "Agendar" }).first().click();
  const dlg = page.getByRole("dialog", { name: "Agendar" });
  const conta = dlg.getByLabel("Conta").and(page.locator("select")).first();
  const opcao = conta.locator("option").filter({ hasText: p.handle }).first();
  await conta.selectOption((await opcao.getAttribute("value"))!);
  await dlg.getByLabel(/Data e hora/).fill(proximoMinutoSp(45_000));
  const modo = dlg.getByLabel("Modo", { exact: true });
  await expect(modo.locator("option[value=publicar]")).toBeEnabled();
  await modo.selectOption("publicar");
  await expect(dlg.getByText(`Apelido ${p.handle}`).first()).toBeVisible();
  const privacidade = dlg.getByLabel("Privacidade", { exact: true });
  await expect(privacidade).toHaveValue("");
  // sandbox: só "Só você"; as outras aparecem indisponíveis
  await expect(privacidade.locator("option[value=SELF_ONLY]")).toBeEnabled();
  await expect(privacidade.locator("option[value=PUBLIC_TO_EVERYONE]")).toBeDisabled();
  for (const nome of [/Permitir comentários/, /Permitir dueto/, /Permitir costura/]) {
    await expect(dlg.getByRole("checkbox", { name: nome })).not.toBeChecked();
  }
  // a conta desligou a costura no app: o toggle fica bloqueado
  await expect(dlg.getByRole("checkbox", { name: /Permitir costura/ })).toBeDisabled();
  await expect(dlg).toContainText("Confirmação de Uso de Música");
  const agendar = dlg.getByRole("button", { name: "Aprovar e agendar" });
  await expect(agendar).toBeDisabled();
  await page.screenshot({ path: `${SHOTS}/015-publicar-tela.png`, fullPage: true });

  // parceria paga + "Só você": a tela recusa com a regra da TikTok
  await privacidade.selectOption("SELF_ONLY");
  await dlg.getByLabel("Divulgação comercial", { exact: true }).selectOption("parceria_paga");
  await expect(dlg).toContainText(/Parceria paga não pode ser publicada como "só você"/);
  await expect(agendar).toBeDisabled();
  await page.screenshot({ path: `${SHOTS}/015-publicar-parceria.png`, fullPage: true });

  // ---- "Só você", sem divulgação, comentários liberados: sem legenda ainda não agenda ----
  await dlg.getByLabel("Divulgação comercial", { exact: true }).selectOption("nenhum");
  await dlg.getByRole("checkbox", { name: /Permitir comentários/ }).check();
  await dlg.getByRole("textbox", { name: /^Legenda/ }).fill("");
  await expect(dlg).toContainText("Descreva o post: na TikTok a legenda (descrição + hashtags) é obrigatória.");
  await expect(agendar).toBeDisabled();
  await expect(dlg.getByRole("button", { name: "Publicar agora" })).toBeDisabled();
  await dlg.getByRole("textbox", { name: /^Legenda/ }).fill(`Legenda publicada ${sfx}`);
  const hashtags = dlg.getByLabel("Hashtags", { exact: true });
  await hashtags.fill("#publicado");
  await hashtags.press("Enter");
  await expect(agendar).toBeEnabled();
  await agendar.click();
  await expect(dlg).toBeHidden();
  const [d] = (await getJson<{ conteudo: { destinos: Destino[] } }>(request, auth, `/api/conteudos/${conteudo}`)).conteudo.destinos;
  expect(d).toMatchObject({ estado: "agendado", modo: "publicar" });
  expect(inits(p.handle), "nada sai antes do horário").toBe(0);

  await esperarEstado(request, auth, d.id, "publicado", 180_000);
  await page.goto(`/app/conteudos/${conteudo}?conta=${p.contaId}`);
  await esperarNoPainel(page, "Publicado na TikTok", 30_000);
  const link = page.getByRole("tabpanel").getByRole("link", { name: /Ver o post/ });
  await expect(link).toHaveAttribute("href", new RegExp(`^https://www\\.tiktok\\.com/@${p.handle}/video/\\d+$`));
  await page.screenshot({ path: `${SHOTS}/015-publicado.png`, fullPage: true });
  const [t] = await tentativas(request, auth, d.id);
  expect(t).toMatchObject({ numero: 1, fase: "publicada", disparo: "agendador" });

  // na TikTok falsa: UM Direct Post com o que o dono escolheu (só do snapshot), nenhum inbox
  const pedidos = pedidosTikTok(p.handle);
  const diretos = pedidos.filter((x) => x.endpoint === "video_init");
  expect(diretos).toHaveLength(1);
  expect(diretos[0]).toMatchObject({ post_info: true, privacy_level: "SELF_ONLY" });
  // o `post_info.title` é a legenda composta (descrição + hashtags)
  expect(diretos[0].title).toBe(`Legenda publicada ${sfx}\n\n#publicado`);
  expect(pedidos.filter((x) => x.endpoint === "inbox_init")).toHaveLength(0);
  expect(pedidos.some((x) => x.endpoint === "creator_info"), "a tela consultou a conta na hora").toBe(true);
  expect(await acoes(request, auth, `/api/destinos/${d.id}/versions`)).toEqual(
    expect.arrayContaining(["agendado", "envio_iniciado", "publicado"]),
  );

  // ---- "Publicar agora" (só dono): mesma tela obrigatória, confirmação com o aviso do sandbox ----
  const agora = await videoProprio(request, auth, p.perfilId, readFileSync(video), `Agora ${sfx}`);
  await page.goto(`/app/conteudos/${agora}`);
  await page.getByRole("button", { name: "Agendar" }).first().click();
  const dlgA = page.getByRole("dialog", { name: "Agendar" });
  const contaA = dlgA.getByLabel("Conta").and(page.locator("select")).first();
  await contaA.selectOption((await contaA.locator("option").filter({ hasText: p.handle }).first().getAttribute("value"))!);
  await dlgA.getByLabel("Modo", { exact: true }).selectOption("publicar");
  const publicarAgora = dlgA.getByRole("button", { name: "Publicar agora" });
  await expect(publicarAgora).toBeDisabled();
  await dlgA.getByLabel("Privacidade", { exact: true }).selectOption("SELF_ONLY");
  await dlgA.getByRole("textbox", { name: /^Legenda/ }).fill(`Legenda agora ${sfx}`);
  await expect(publicarAgora).toBeEnabled();
  await publicarAgora.click();
  const confirmarAgora = page.getByRole("alertdialog", { name: `Publicar em @${p.handle} agora?` });
  await expect(confirmarAgora).toContainText("Sandbox: sai só para você, com a conta privada.");
  await page.screenshot({ path: `${SHOTS}/015-publicar-agora.png`, fullPage: true });
  await confirmarAgora.getByRole("button", { name: "Publicar agora" }).click();
  // o clique cria o destino e dispara o envio: esperar o destino existir antes de ler o id
  let dA: Destino | undefined;
  await expect
    .poll(async () => {
      [dA] = (await getJson<{ conteudo: { destinos: Destino[] } }>(request, auth, `/api/conteudos/${agora}`)).conteudo.destinos;
      return dA?.id ?? null;
    }, { timeout: 15_000 })
    .not.toBeNull();
  await esperarEstado(request, auth, dA!.id, "publicado", 120_000);
  const diretosAgora = pedidosTikTok(p.handle).filter((x) => x.endpoint === "video_init");
  expect(diretosAgora).toHaveLength(2);
  expect(diretosAgora[1]).toMatchObject({ privacy_level: "SELF_ONLY", title: `Legenda agora ${sfx}` });

  // o link do post no clique não sai do navegador de teste: só conferimos o href
  soLoginInterceptado(vistos, []);
});

// ---------------------------------------------------------------------------------------------
// Princípio I: a API e o agendador só enxergam a TikTok falsa
// ---------------------------------------------------------------------------------------------
test("Princípio I: nenhuma requisição sai para a TikTok real", async () => {
  for (const servico of ["api", "agendador"]) {
    // o cliente aponta para o fake, e só o fake é host extra de upload/avatar
    const alvo = compose([
      "exec", "-T", servico, "python", "-c",
      "from sociman_api.publicacao.tiktok.cliente import get_tiktok_client as g; c = g(); print(c.api_url, sorted(c.hosts_extras))",
    ]).trim();
    expect(alvo, `${servico}: cliente da TikTok`).toBe("http://openshorts-fake:8000/tiktok ['openshorts-fake']");
    // e os hosts reais da TikTok nem resolvem para fora (extra_hosts → 127.0.0.1)
    const hosts = compose([
      "exec", "-T", servico, "python", "-c",
      "import socket; print(' '.join(socket.gethostbyname(h) for h in ('open.tiktokapis.com', 'open-upload.tiktokapis.com', 'www.tiktok.com')))",
    ]).trim();
    expect(hosts, `${servico}: hosts reais da TikTok`).toBe("127.0.0.1 127.0.0.1 127.0.0.1");
  }
  // tudo o que a stack pediu à TikTok chegou ao fake, só nos caminhos do cliente (R21)
  const todos = pedidosTikTok();
  expect(todos.length).toBeGreaterThan(0);
  expect(todos.filter((x) => x.endpoint === "desconhecido")).toEqual([]);
});
