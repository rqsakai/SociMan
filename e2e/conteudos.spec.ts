import { randomUUID } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER, PG_DB, PG_USER } from "./fixtures";
import { apiToken, compose, createPerfilViaApi, createVerifiedMember, login, logout, nav, preencherData, syntheticMp4 } from "./helpers";

// Spec 014 (T025, T033, T052, T059, T065): a central de conteúdos na stack isolada, com o
// `worker` (cortes), o `agendador` (lembretes a cada 2 s) e o Claude falso do `openshorts-fake`.
// US1 lista, filtros na URL e páginas numeradas (spec 024); US2 pedido de aprovação pelo membro e resposta do
// dono; US3 agendar direto no corte (modos indisponíveis com o motivo, intervalo mínimo com
// "Manter mesmo assim", lembrete → "A postar" → "Postado"); US4 sequência com prévia; US5 vídeo
// próprio. Em todos: nenhuma requisição sai para rede social, e os modos automáticos são recusados.

const SHOTS = ".playwright-mcp/sociman";
// Guarda do princípio I pelo DOMÍNIO (e por /api/social): o caminho de módulos locais do Vite
// (ex.: /src/components/publicacao/TikTokPostForm.tsx em localhost) não é rede social.
const SOCIAL_HOST = /(^|\.)(tiktok\.com|tiktokapis\.com|tiktokcdn\.com|upload-post\.com|facebook\.com|instagram\.com|youtube\.com|googleapis\.com)$/i;
const ehRedeSocial = (url: string): boolean => {
  const u = new URL(url);
  return SOCIAL_HOST.test(u.hostname) || /\/api\/social/i.test(u.pathname) || /videos\.insert/i.test(u.pathname);
};
const UUID = /[0-9a-f-]{36}/;

type Auth = { Authorization: string };

interface Destino {
  id: string;
  conteudoId: string;
  conta: { id: string; handle: string };
  titulo: string;
  estado: string;
  estadoEfetivo: string;
  modo: string;
  plannedAt: string | null;
  postedUrl: string | null;
  version: number;
}

interface ConteudoItem {
  id: string;
  titulo: string;
  origem: string;
  situacao: string;
  destinos: { id: string; conta: { id: string }; estado: string; estadoEfetivo: string; plannedAt: string | null }[];
}

interface Version {
  version: number;
  changedFields: string[];
  details: Record<string, unknown> & { acao?: string; intervaloIgnorado?: boolean };
  actor: { name: string } | null;
}

// ---------------------------------------------------------------------------------------------
// Datas no fuso de São Paulo (APP_TZ)
// ---------------------------------------------------------------------------------------------

function spParts(date: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Sao_Paulo",
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
      .formatToParts(date)
      .map((p) => [p.type, p.value]),
  );
}

// "2026-09-30" em São Paulo, `offset` dias a partir de hoje.
function spDay(offset: number): string {
  const p = spParts(new Date(Date.now() + offset * 86_400_000));
  return `${p.year}-${p.month}-${p.day}`;
}

// "2026-09-30T19:07" (para o <input type="datetime-local">).
function spLocalInput(date: Date): string {
  const p = spParts(date);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

// ISO com o offset de São Paulo (sem horário de verão desde 2019: -03:00).
function spIso(day: string, hhmm: string): string {
  return `${day}T${hhmm}:00-03:00`;
}

// "HH:MM" de um ISO, em São Paulo.
function spHhmm(iso: string): string {
  const p = spParts(new Date(iso));
  return `${p.hour}:${p.minute}`;
}

// ---------------------------------------------------------------------------------------------
// Dados de base pela API
// ---------------------------------------------------------------------------------------------

async function getJson<T>(request: APIRequestContext, auth: Auth, url: string): Promise<T> {
  const res = await request.get(url, { headers: auth });
  expect(res.status(), `GET ${url}: ${res.status() === 200 ? "" : await res.text()}`).toBe(200);
  return (await res.json()) as T;
}

async function versions(request: APIRequestContext, auth: Auth, url: string): Promise<Version[]> {
  return (await getJson<{ items: Version[] }>(request, auth, url)).items;
}

async function novaConta(request: APIRequestContext, auth: Auth, perfilId: string, handle: string): Promise<string> {
  const res = await request.post(`/api/perfis/${perfilId}/contas`, {
    headers: auth,
    data: { platform: "tiktok", handle, status: "ativa" },
  });
  expect(res.status(), `POST contas: ${await res.text()}`).toBe(201);
  return ((await res.json()) as { conta: { id: string } }).conta.id;
}

// Perfil novo com uma conta TikTok ativa.
async function perfilComConta(request: APIRequestContext, token: string, nome: string, sfx: string) {
  const auth = { Authorization: `Bearer ${token}` };
  const slug = `${nome.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${sfx}`;
  const perfilName = `${nome} ${sfx}`;
  const perfilId = await createPerfilViaApi(request, token, { name: perfilName, slug });
  const handle = `${nome.toLowerCase().replace(/[^a-z0-9]+/g, "")}${sfx}`;
  const contaId = await novaConta(request, auth, perfilId, handle);
  return { perfilId, perfilName, contaId, handle };
}

// Corte pela API da 004 (o worker aplica a marca em segundo plano). Não espera.
async function enviarCorte(request: APIRequestContext, auth: Auth, perfilId: string, video: string, gancho: string): Promise<string> {
  const res = await request.post(`/api/perfis/${perfilId}/cortes`, {
    headers: auth,
    multipart: {
      file: { name: "corte.mp4", mimeType: "video/mp4", buffer: readFileSync(video) },
      hookText: gancho,
    },
  });
  expect(res.status(), `POST cortes: ${await res.text()}`).toBe(201);
  return ((await res.json()) as { corte: { id: string } }).corte.id;
}

async function esperarCortePronto(request: APIRequestContext, auth: Auth, corteId: string): Promise<void> {
  await expect
    .poll(async () => (await getJson<{ corte: { status: string } }>(request, auth, `/api/cortes/${corteId}`)).corte.status, {
      timeout: 180_000,
      intervals: [1_000, 2_000],
      message: `corte ${corteId} não ficou pronto`,
    })
    .toBe("pronto");
}

// Devolve o corte a "em revisão" (como um clipe recém-importado do OpenShorts, sem a marca): só no
// banco da stack e2e, para não esperar o fluxo inteiro da 006.
function voltarParaRevisao(corteId: string): void {
  compose([
    "exec", "-T", "postgres", "psql", "-U", PG_USER, "-d", PG_DB, "-v", "ON_ERROR_STOP=1", "-c",
    `update cortes set status = 'revisao' where id = '${corteId}'`,
  ]);
}

// Vídeo próprio pela API (201, já "pronto").
async function enviarVideoProprio(
  request: APIRequestContext,
  auth: Auth,
  perfilId: string,
  video: Buffer,
  titulo: string,
): Promise<string> {
  const res = await request.post(`/api/perfis/${perfilId}/conteudos/arquivo`, {
    headers: auth,
    multipart: { file: { name: `${titulo}.mp4`, mimeType: "video/mp4", buffer: video }, titulo },
  });
  expect(res.status(), `POST conteudos/arquivo (${titulo}): ${await res.text()}`).toBe(201);
  return ((await res.json()) as { conteudo: { id: string } }).conteudo.id;
}

async function destinosDoConteudo(request: APIRequestContext, auth: Auth, conteudoId: string): Promise<Destino[]> {
  return (await getJson<{ conteudo: { destinos: Destino[] } }>(request, auth, `/api/conteudos/${conteudoId}`)).conteudo.destinos;
}

async function agendarViaApi(
  request: APIRequestContext,
  auth: Auth,
  body: { conteudoId: string; contaId: string; plannedAt: string; ignorarIntervalo?: boolean; textos?: { titulo?: string; descricao?: string } },
): Promise<Destino> {
  // spec 015 (T103): na TikTok a legenda (descrição) é obrigatória em qualquer modo
  const textos = { descricao: "Legenda do e2e", ...body.textos };
  const res = await request.post("/api/agendamentos", { headers: auth, data: { modo: "lembrete", ...body, textos } });
  expect([200, 201], `POST /api/agendamentos: ${await res.text()}`).toContain(res.status());
  return ((await res.json()) as { destino: Destino }).destino;
}

// ---------------------------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------------------------

function sino(page: Page): Locator {
  return page.getByRole("button", { name: /^Notificações/ });
}

// Escolhe no <select> nativo a opção cuja legenda contém o @ da conta.
async function escolherConta(select: Locator, handle: string): Promise<void> {
  select = select.and(select.page().locator("select")).first();
  const opcao = select.locator("option").filter({ hasText: handle }).first();
  await expect(opcao).toBeAttached();
  await select.selectOption((await opcao.getAttribute("value"))!);
}

function tabela(page: Page): Locator {
  return page.getByRole("table", { name: "Conteúdos" });
}

function linha(page: Page, titulo: string): Locator {
  return tabela(page).getByRole("row").filter({ hasText: titulo });
}

// Espera uma notificação cujo título casa com `nome` no sino (o polling do sino é de 20 s).
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

// Guarda do princípio I: registra toda requisição do navegador para domínios de rede social.
function vigiarRedesSociais(page: Page): string[] {
  const social: string[] = [];
  page.on("request", (req) => {
    if (ehRedeSocial(req.url())) social.push(`${req.method()} ${req.url()}`);
  });
  return social;
}

// ---------------------------------------------------------------------------------------------
// US1 (T025): lista, filtros na URL, busca, páginas numeradas (spec 024, T047) e detalhe
// ---------------------------------------------------------------------------------------------
test("US1: a central lista os conteúdos, filtra pela URL e pagina", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const social = vigiarRedesSociais(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const taverna = await perfilComConta(request, token, "Taverna", sfx);
  const outro = await perfilComConta(request, token, "Outro", sfx);

  // três cortes na Taverna (dois prontos e um em revisão) e um no outro perfil
  const video = testInfo.outputPath("corte.mp4");
  syntheticMp4(video, 3);
  const cortes = [];
  for (const g of [`Gancho alfa ${sfx}`, `Gancho beta ${sfx}`, `Gancho gama ${sfx}`]) {
    cortes.push(await enviarCorte(request, auth, taverna.perfilId, video, g));
  }
  const corteOutro = await enviarCorte(request, auth, outro.perfilId, video, `Gancho delta ${sfx}`);
  for (const id of [...cortes, corteOutro]) await esperarCortePronto(request, auth, id);
  voltarParaRevisao(cortes[2]);
  // um deles já agendado: sai do atalho "Prontos sem agendamento"
  await agendarViaApi(request, auth, { conteudoId: cortes[1], contaId: taverna.contaId, plannedAt: spIso(spDay(3), "19:00") });

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await nav(page, "Conteúdos");
  await expect(page).toHaveURL(/\/app\/conteudos/);
  await expect(page.getByRole("heading", { name: "Conteúdos", level: 1 })).toBeVisible();
  await expect(linha(page, `Gancho alfa ${sfx}`)).toBeVisible();
  await expect(linha(page, `Gancho delta ${sfx}`)).toBeVisible();
  // estados por conta e "Sem conta"
  await expect(linha(page, `Gancho gama ${sfx}`)).toContainText("Em revisão");
  await expect(linha(page, `Gancho alfa ${sfx}`)).toContainText("Sem conta");
  await expect(linha(page, `Gancho beta ${sfx}`)).toContainText("Agendado");
  await expect(linha(page, `Gancho alfa ${sfx}`)).toContainText("Corte");
  await page.screenshot({ path: `${SHOTS}/014-conteudos-lista.png`, fullPage: true });

  // filtro de perfil + atalho: só o pronto sem agendamento da Taverna
  await page.getByLabel("Perfil").selectOption({ label: taverna.perfilName });
  await page.getByRole("button", { name: /Prontos sem agendamento/ }).click();
  await expect(page).toHaveURL(new RegExp(`perfil=${taverna.perfilId}`));
  await expect(page).toHaveURL(/atalho=prontos_sem_agendamento/);
  await expect(linha(page, `Gancho alfa ${sfx}`)).toBeVisible();
  await expect(linha(page, `Gancho beta ${sfx}`)).toHaveCount(0);
  await expect(linha(page, `Gancho gama ${sfx}`)).toHaveCount(0);
  await expect(linha(page, `Gancho delta ${sfx}`)).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/014-conteudos-atalho.png`, fullPage: true });

  // o link com os filtros abre a mesma lista; recarregar mantém; voltar desfaz o último filtro
  const filtrada = page.url();
  await page.reload();
  await expect(linha(page, `Gancho alfa ${sfx}`)).toBeVisible();
  await expect(linha(page, `Gancho beta ${sfx}`)).toHaveCount(0);
  await page.goBack();
  await expect(page).not.toHaveURL(/atalho=/);
  await expect(linha(page, `Gancho beta ${sfx}`)).toBeVisible();
  await expect(linha(page, `Gancho delta ${sfx}`)).toHaveCount(0);
  await page.goto(filtrada);
  await expect(linha(page, `Gancho alfa ${sfx}`)).toBeVisible();
  await expect(linha(page, `Gancho beta ${sfx}`)).toHaveCount(0);

  // busca por trecho do título (sem o atalho)
  await page.goto(`/app/conteudos?perfil=${taverna.perfilId}`);
  await page.getByLabel("Buscar").fill(`beta ${sfx}`);
  await expect(page).toHaveURL(/q=beta/);
  await expect(linha(page, `Gancho beta ${sfx}`)).toBeVisible();
  await expect(linha(page, `Gancho alfa ${sfx}`)).toHaveCount(0);

  // clique abre o detalhe: player, abas por conta e histórico
  await linha(page, `Gancho beta ${sfx}`).getByRole("link").first().click();
  await expect(page).toHaveURL(/\/app\/conteudos\/[0-9a-f-]{36}/);
  await expect(page.locator("video")).toBeVisible();
  await expect(page.getByRole("tab", { name: new RegExp(taverna.handle) })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/014-conteudo-detalhe.png`, fullPage: true });

  // Páginas numeradas (spec 024, US6): 55 vídeos próprios num perfil novo, 25 por página
  const muitos = await perfilComConta(request, token, "Muitos", sfx);
  const curto = testInfo.outputPath("curto.mp4");
  syntheticMp4(curto, 1);
  const buf = readFileSync(curto);
  for (let i = 0; i < 55; i++) {
    await enviarVideoProprio(request, auth, muitos.perfilId, buf, `Item ${String(i).padStart(2, "0")} ${sfx}`);
    await new Promise((r) => setTimeout(r, 60)); // o edge limita /api/ a 20 req/s
  }
  await page.goto(`/app/conteudos?perfil=${muitos.perfilId}`);
  const linhas = tabela(page).getByRole("row").filter({ hasText: sfx });
  const rodape = (texto: string) => page.getByText(texto, { exact: true });
  await expect(linhas).toHaveCount(25);
  await expect(rodape("Página 1 de 3")).toBeVisible();
  await expect(rodape("55 itens")).toBeVisible();
  await expect(page.getByRole("button", { name: "Página anterior" })).toBeDisabled();
  const titulos = await linhas.allInnerTexts();
  await page.getByRole("button", { name: "Próxima página" }).click();
  await expect(page).toHaveURL(/pagina=2/);
  await expect(rodape("Página 2 de 3")).toBeVisible();
  // o rodapé muda antes das linhas (a página anterior fica na tela até a nova chegar): espera o
  // título do 1º item ("Item NN <sfx>") mudar
  const primeiro = titulos[0]!.match(/Item \d+ \S+/)![0];
  await expect(linhas.first()).not.toContainText(primeiro);
  await expect(linhas).toHaveCount(25);
  titulos.push(...(await linhas.allInnerTexts()));
  await page.getByRole("button", { name: "Próxima página" }).click();
  await expect(page).toHaveURL(/pagina=3/);
  await expect(linhas).toHaveCount(5);
  await expect(page.getByRole("button", { name: "Próxima página" })).toBeDisabled();
  titulos.push(...(await linhas.allInnerTexts()));
  expect(new Set(titulos).size, "sem linhas repetidas nem puladas").toBe(55);

  // voltar do detalhe mantém a página e os filtros
  await linhas.first().getByRole("link").first().click();
  await expect(page).toHaveURL(/\/app\/conteudos\/[0-9a-f-]{36}/);
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`perfil=${muitos.perfilId}`));
  await expect(page).toHaveURL(/pagina=3/);
  await expect(rodape("Página 3 de 3")).toBeVisible();
  await expect(linhas).toHaveCount(5);

  // mudar um filtro volta à página 1
  await page.getByLabel("Buscar").fill("Item 0");
  await expect(page).toHaveURL(/q=Item/);
  await expect(page).not.toHaveURL(/pagina=/);
  await expect(rodape("Página 1 de 1")).toBeVisible();
  await expect(linhas).toHaveCount(10);

  // página além da última cai na última; o tamanho fica na URL
  await page.goto(`/app/conteudos?perfil=${muitos.perfilId}&pagina=9`);
  await expect(page).toHaveURL(/pagina=3/);
  await expect(rodape("Página 3 de 3")).toBeVisible();
  await expect(linhas).toHaveCount(5);
  await page.getByLabel("Itens por página").selectOption("50");
  await expect(page).toHaveURL(/tamanho=50/);
  await expect(page).not.toHaveURL(/pagina=/);
  await expect(rodape("Página 1 de 2")).toBeVisible();
  await expect(linhas).toHaveCount(50);

  expect(social, "nenhuma requisição para rede social").toEqual([]);
});

// ---------------------------------------------------------------------------------------------
// US2 (T033): o membro pede aprovação (1 individual, 2 em lote); o dono aprova 2 e recusa 1
// ---------------------------------------------------------------------------------------------
test("US2: membro pede aprovação e o dono aprova ou recusa com motivo", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const social = vigiarRedesSociais(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Aprovacao", sfx);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 2);
  const buf = readFileSync(video);
  const ids: string[] = [];
  for (const t of ["Um", "Dois", "Tres"]) ids.push(await enviarVideoProprio(request, auth, p.perfilId, buf, `${t} ${sfx}`));
  // um corte em revisão (sem a marca)
  const corte = await enviarCorte(request, auth, p.perfilId, video, `Revisao ${sfx}`);
  await esperarCortePronto(request, auth, corte);
  voltarParaRevisao(corte);

  const member = await createVerifiedMember(page);

  // ---- membro: pedir aprovação no detalhe (com nota) ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos/${ids[0]}`);
  await page.getByRole("button", { name: "Adicionar conta" }).click();
  const add = page.getByRole("dialog", { name: "Adicionar conta" });
  await escolherConta(add.getByLabel("Conta"), p.handle);
  await add.getByRole("button", { name: "Adicionar" }).click();
  const painel = page.getByRole("tabpanel");
  await expect(painel.getByRole("button", { name: "Aprovar", exact: true })).toHaveCount(0);
  await painel.getByRole("button", { name: "Pedir aprovação" }).click();
  const pedir = page.getByRole("dialog", { name: /^Pedir aprovação/ });
  await pedir.getByLabel("Nota para o dono (opcional)").fill("Pode ir hoje?");
  await pedir.getByRole("button", { name: "Pedir aprovação" }).click();
  await expect(painel.getByText("Aguardando aprovação").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/014-pedido-aprovacao.png`, fullPage: true });

  // ---- membro: pedir aprovação em lote (2) ----
  await page.goto(`/app/conteudos?perfil=${p.perfilId}`);
  for (const t of [`Dois ${sfx}`, `Tres ${sfx}`]) await linha(page, t).getByRole("checkbox").check();
  const barra = page.getByRole("region", { name: "Selecionados" });
  await expect(barra.getByRole("button", { name: "Aprovar", exact: true })).toHaveCount(0);
  await escolherConta(barra.getByLabel("Conta"), p.handle);
  await barra.getByRole("button", { name: "Pedir aprovação" }).click();
  await expect(barra.getByRole("alert")).toContainText(/: 2 ok(?!.*falha)/);

  // a API recusa "aprovar" para o membro (403)
  const memberToken = await apiToken(request, member.email, member.final);
  const d0 = (await destinosDoConteudo(request, auth, ids[0]))[0];
  const forbidden = await request.post(`/api/destinos/${d0.id}/aprovar`, {
    headers: { Authorization: `Bearer ${memberToken}` },
    data: { version: d0.version },
  });
  expect(forbidden.status(), "membro aprova").toBe(403);
  await logout(page);

  // ---- dono: 3 pedidos no sino e no atalho ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await esperarNoSino(page, /aprovação/i);
  const notif = await getJson<{ items: { tipo: string }[] }>(request, auth, "/api/notificacoes");
  expect(notif.items.filter((n) => n.tipo === "aprovacao_pedida").length).toBeGreaterThanOrEqual(3);
  await page.goto(`/app/conteudos?perfil=${p.perfilId}`);
  const atalho = page.getByRole("button", { name: /Aguardando aprovação/ });
  await expect(atalho).toContainText("3");
  await atalho.click();
  await expect(tabela(page).getByRole("row").filter({ hasText: sfx })).toHaveCount(3);
  await page.screenshot({ path: `${SHOTS}/014-aguardando-aprovacao.png`, fullPage: true });

  // aprova o primeiro no detalhe
  await linha(page, `Um ${sfx}`).getByRole("link").first().click();
  await page.getByRole("tabpanel").getByRole("button", { name: "Aprovar", exact: true }).click();
  await expect(page.getByRole("tabpanel").getByText("Aprovado").first()).toBeVisible();

  // aprova o segundo pela barra de lote
  await page.goto(`/app/conteudos?perfil=${p.perfilId}`);
  await linha(page, `Dois ${sfx}`).getByRole("checkbox").check();
  const barraDono = page.getByRole("region", { name: "Selecionados" });
  await escolherConta(barraDono.getByLabel("Conta"), p.handle);
  await barraDono.getByRole("button", { name: "Aprovar", exact: true }).click();
  await expect(barraDono.getByRole("alert")).toContainText(/: 1 ok(?!.*falha)/);

  // recusa o terceiro: sem motivo o botão fica desabilitado
  await page.goto(`/app/conteudos/${ids[2]}`);
  await page.getByRole("tabpanel").getByRole("button", { name: "Recusar" }).click();
  const recusar = page.getByRole("dialog", { name: /^Recusar/ });
  await expect(recusar.getByRole("button", { name: "Recusar" })).toBeDisabled();
  await recusar.getByLabel("Motivo da recusa").fill("O áudio está baixo.");
  await recusar.getByRole("button", { name: "Recusar" }).click();
  await expect(page.getByRole("tabpanel").getByText("O áudio está baixo.")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/014-recusa.png`, fullPage: true });

  // conteúdo em revisão: "Aplique a marca antes de aprovar"
  await page.goto(`/app/conteudos/${corte}`);
  await page.getByRole("button", { name: "Adicionar conta" }).click();
  const add2 = page.getByRole("dialog", { name: "Adicionar conta" });
  await escolherConta(add2.getByLabel("Conta"), p.handle);
  await add2.getByRole("button", { name: "Adicionar" }).click();
  await expect(page.getByRole("tabpanel").getByRole("button", { name: "Aprovar", exact: true })).toBeDisabled();
  await expect(page.getByRole("tabpanel").getByText(/Aplique a marca antes de aprovar/)).toBeVisible();
  const [dRev] = await destinosDoConteudo(request, auth, corte);
  const rev = await request.post(`/api/destinos/${dRev.id}/aprovar`, { headers: auth, data: { version: dRev.version } });
  expect(rev.status()).toBe(409);
  expect(((await rev.json()) as { error: { code: string } }).error.code).toBe("conteudo_nao_pronto");

  // histórico com os autores (pedido pelo membro, aprovação e recusa pelo dono)
  const d1 = (await destinosDoConteudo(request, auth, ids[0]))[0];
  expect(d1.estado).toBe("aprovado");
  const h1 = await versions(request, auth, `/api/destinos/${d1.id}/versions`);
  expect(h1.find((v) => v.details.acao === "aprovacao_pedida")?.actor?.name).toBe(member.name);
  expect(h1.find((v) => v.details.acao === "aprovado")?.actor?.name).toBe(OWNER.name);
  const d3 = (await destinosDoConteudo(request, auth, ids[2]))[0];
  expect(d3.estado).toBe("pendente");
  const h3 = await versions(request, auth, `/api/destinos/${d3.id}/versions`);
  expect(h3.find((v) => v.details.acao === "recusado")?.actor?.name).toBe(OWNER.name);
  await logout(page);

  // ---- membro: "Aprovação respondida" para os 3 ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await esperarNoSino(page, /aprova/i);
  const respondidas = await getJson<{ items: { tipo: string }[] }>(
    request, { Authorization: `Bearer ${memberToken}` }, "/api/notificacoes",
  );
  expect(respondidas.items.filter((n) => n.tipo === "aprovacao_respondida")).toHaveLength(3);

  expect(social, "nenhuma requisição para rede social").toEqual([]);
});

// ---------------------------------------------------------------------------------------------
// US3 (T052): agendar direto no corte, modos indisponíveis, intervalo, membro, reagendar e
// cancelar, intervalo da conta, e o lembrete até "Postado"
// ---------------------------------------------------------------------------------------------
test("US3: agendar direto no corte pronto, com o modo certo e o intervalo mínimo", async ({ page, request }, testInfo) => {
  test.setTimeout(480_000);
  const social = vigiarRedesSociais(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Agenda", sfx);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 3);
  const corte = await enviarCorte(request, auth, p.perfilId, video, `Agendar ${sfx}`);
  const outro = await enviarCorte(request, auth, p.perfilId, video, `Vizinho ${sfx}`);
  const doMembro = await enviarCorte(request, auth, p.perfilId, video, `Membro ${sfx}`);
  for (const id of [corte, outro, doMembro]) await esperarCortePronto(request, auth, id);
  const member = await createVerifiedMember(page);
  const amanha = spDay(1);

  // ---- dono agenda direto no corte pronto: IA falsa, modos 2–4 desabilitados com o motivo ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/cortes/${corte}`);
  await page.getByRole("button", { name: "Agendar / Publicar" }).first().click();
  const dlg = page.getByRole("dialog", { name: "Agendar ou publicar" });
  await escolherConta(dlg.getByLabel("Conta"), p.handle);
  await preencherData(dlg.getByLabel(/Data e hora/), `${amanha}T19:00`);
  const modo = dlg.getByLabel("Modo", { exact: true });
  await expect(modo.locator("option[value=lembrete]")).toBeEnabled();
  for (const m of ["criar_rascunho", "publicar", "rascunho_e_publicar"]) {
    await expect(modo.locator(`option[value=${m}]`)).toBeDisabled();
  }
  // cada modo indisponível traz o motivo (na 014, "Aguardando a spec de integração (015)"; com a
  // 015 no código, "Conecte a conta")
  const motivos = dlg.getByRole("list", { name: "Modos desta conta" }).getByRole("listitem");
  for (const m of ["Criar rascunho no horário", "Publicar no horário"]) {
    await expect(motivos.filter({ hasText: m }).first()).toContainText(/:\s*(Aguardando a spec de integração \(015\)|Conecte a conta)/);
  }
  await expect(dlg).toContainText("O TikTok não permite publicar um rascunho pela API");
  await dlg.getByTestId("ia-botao-postagem.textos").click();
  const ia = dlg.getByTestId("ia-painel-postagem.textos");
  await ia.getByRole("button", { name: "Gerar", exact: true }).click();
  await expect(ia.getByText(/Claude falso do e2e/).last()).toBeVisible({ timeout: 25_000 });
  await ia.getByRole("button", { name: "Aplicar", exact: true }).click();
  // TikTok: sem campo de título (spec 015, T103); a IA preenche a legenda
  await expect(dlg.getByLabel("Título", { exact: true })).toHaveCount(0);
  await expect(dlg.getByRole("textbox", { name: /^Legenda/ })).toHaveValue(/^Descrição sugerida pela IA, versão \d+\.$/);
  await page.screenshot({ path: `${SHOTS}/014-agendar-modos.png`, fullPage: true });
  await dlg.getByRole("button", { name: "Aprovar e agendar" }).click();
  await expect(dlg).toBeHidden();
  const [dest] = await destinosDoConteudo(request, auth, corte);
  expect(dest).toMatchObject({ estado: "agendado", modo: "lembrete" });
  expect(spHhmm(dest.plannedAt!)).toBe("19:00");
  expect(dest.titulo).toMatch(/^Título sugerido pela IA \d+$/);
  const h = await versions(request, auth, `/api/destinos/${dest.id}/versions`);
  expect(h.map((v) => v.details.acao)).toEqual(expect.arrayContaining(["aprovado", "agendado"]));

  // chip na lista e cartão no calendário
  await page.goto(`/app/conteudos?perfil=${p.perfilId}`);
  await expect(linha(page, `Agendar ${sfx}`)).toContainText("Agendado");
  await page.goto(`/app/calendario?perfil=${p.perfilId}`);
  await expect(page.getByRole("button", { name: /Título sugerido pela IA/ }).first()).toBeVisible();

  // ---- intervalo mínimo: outro às 19:10 na mesma conta avisa; "Manter mesmo assim" grava ----
  await page.goto(`/app/conteudos/${outro}`);
  await page.getByRole("button", { name: "Agendar / Publicar" }).first().click();
  const dlg2 = page.getByRole("dialog", { name: "Agendar ou publicar" });
  await escolherConta(dlg2.getByLabel("Conta"), p.handle);
  await preencherData(dlg2.getByLabel(/Data e hora/), `${amanha}T19:10`);
  await dlg2.getByRole("textbox", { name: /^Legenda/ }).fill(`Vizinho agendado ${sfx}`);
  await dlg2.getByRole("button", { name: "Aprovar e agendar" }).click();
  await expect(dlg2).toContainText("Há outro post perto deste horário; o intervalo mínimo é 30 min.");
  await expect(dlg2.getByRole("button", { name: "Escolher outro horário" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/014-intervalo.png`, fullPage: true });
  await dlg2.getByRole("button", { name: "Manter mesmo assim" }).click();
  await expect(dlg2).toBeHidden();
  const [vizinho] = await destinosDoConteudo(request, auth, outro);
  expect(vizinho.estado).toBe("agendado");
  expect(spHhmm(vizinho.plannedAt!)).toBe("19:10");
  const hv = await versions(request, auth, `/api/destinos/${vizinho.id}/versions`);
  expect(hv[0].details.intervaloIgnorado).toBe(true);

  // a API recusa os modos automáticos e o horário no passado (nada é gravado)
  for (const m of ["criar_rascunho", "publicar", "rascunho_e_publicar"]) {
    const r = await request.post("/api/agendamentos", {
      headers: auth,
      data: { conteudoId: doMembro, contaId: p.contaId, plannedAt: spIso(spDay(5), "10:00"), modo: m, textos: { descricao: `Legenda ${sfx}` } },
    });
    expect(r.status(), `modo ${m}`).toBe(409);
    expect(((await r.json()) as { error: { code: string } }).error.code).toBe("modo_indisponivel");
  }
  const passado = await request.post("/api/agendamentos", {
    headers: auth,
    data: { conteudoId: doMembro, contaId: p.contaId, plannedAt: spIso(spDay(-1), "10:00"), modo: "lembrete", textos: { descricao: `Legenda ${sfx}` } },
  });
  expect(passado.status()).toBe(400);

  // ---- reagendar arrastando no calendário (semana de amanhã) ----
  await page.goto(`/app/calendario?perfil=${p.perfilId}`);
  const cartao = page.getByRole("button", { name: new RegExp(`Vizinho ${sfx}`) }).first();
  await expect(cartao).toBeVisible();
  const dia = page.getByRole("group", { name: /^Dia / }).and(page.locator(`[data-day="${amanha}"]`));
  // rola a grade da semana para 18:00 (o ponto de soltura precisa estar visível no scroller)
  const HOUR_PX = await dia.evaluate((el) => {
    const hora = el.getBoundingClientRect().height / 24;
    const scroller = el.closest(".overflow-y-auto");
    if (scroller) scroller.scrollTop = 18 * hora;
    return hora;
  });
  // arrasto HTML5 por eventos (dragstart no cartão, dragover e drop na coluna do dia às 21:00): o
  // mouse do Playwright não completa o drop nesta grade rolável
  const box = (await dia.boundingBox())!;
  const ponto = { clientX: box.x + box.width / 2, clientY: box.y + 21 * HOUR_PX + 4 };
  const dt = await page.evaluateHandle(() => new DataTransfer());
  await cartao.dispatchEvent("dragstart", { dataTransfer: dt });
  await dia.dispatchEvent("dragover", { dataTransfer: dt, ...ponto });
  await dia.dispatchEvent("drop", { dataTransfer: dt, ...ponto });
  await expect(page.getByText(/^Remarcado para /)).toBeVisible();
  await expect.poll(async () => spHhmm((await destinosDoConteudo(request, auth, outro))[0].plannedAt!)).toBe("21:00");

  // ---- cancelar pela aba da conta ----
  await page.goto(`/app/conteudos/${outro}`);
  await page.getByRole("tabpanel").getByRole("button", { name: "Cancelar agendamento" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: /Cancelar agendamento/ }).click();
  await expect.poll(async () => (await destinosDoConteudo(request, auth, outro))[0].estado).toBe("aprovado");
  const hc = await versions(request, auth, `/api/destinos/${vizinho.id}/versions`);
  // arrastar no calendário remarca por `lote/reagendar` (acao "lote", com loteId)
  expect(hc.map((v) => v.details.acao)).toEqual(expect.arrayContaining(["lote", "agendamento_cancelado"]));
  expect(hc.find((v) => v.details.acao === "lote")?.changedFields).toContain("planned_at");

  // ---- dono muda o intervalo da conta na aba Contas ----
  await page.goto(`/app/perfis/${p.perfilId}`);
  await page.getByRole("tab", { name: "Contas", exact: true }).click();
  await page.getByRole("button", { name: /Editar/ }).first().click();
  const intervalo = page.getByLabel("Intervalo mínimo entre posts (min)");
  await expect(intervalo).toHaveValue("30");
  await intervalo.fill("45");
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect
    .poll(async () =>
      (await getJson<{ contas: { id: string; intervaloMinMinutos: number }[] }>(request, auth, `/api/perfis/${p.perfilId}`)).contas.find(
        (c) => c.id === p.contaId,
      )?.intervaloMinMinutos,
    )
    .toBe(45);
  await logout(page);

  // ---- membro: diante de um não aprovado vê "Pedir aprovação"; o intervalo só para leitura ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/cortes/${doMembro}`);
  await page.getByRole("button", { name: "Agendar / Publicar" }).first().click();
  const dlgM = page.getByRole("dialog", { name: "Agendar ou publicar" });
  await escolherConta(dlgM.getByLabel("Conta"), p.handle);
  await expect(dlgM.getByRole("button", { name: "Aprovar e agendar" })).toHaveCount(0);
  await expect(dlgM.getByRole("button", { name: "Pedir aprovação" })).toBeVisible();
  await page.keyboard.press("Escape");
  const memberToken = await apiToken(request, member.email, member.final);
  const semAprovacao = await request.post("/api/agendamentos", {
    headers: { Authorization: `Bearer ${memberToken}` },
    data: { conteudoId: doMembro, contaId: p.contaId, plannedAt: spIso(spDay(6), "10:00"), modo: "lembrete", textos: { descricao: `Legenda ${sfx}` } },
  });
  expect(semAprovacao.status()).toBe(403);
  await page.goto(`/app/perfis/${p.perfilId}`);
  await page.getByRole("tab", { name: "Contas", exact: true }).click();
  await expect(page.getByText(/Intervalo mínimo entre posts/)).toBeVisible();
  await expect(page.getByRole("spinbutton", { name: "Intervalo mínimo entre posts (min)" })).toHaveCount(0);
  await logout(page);

  // ---- lembrete: "Hora de postar" no horário, chip "A postar" e "Postado" com link ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const logo = await agendarViaApi(request, auth, {
    conteudoId: doMembro,
    contaId: p.contaId,
    plannedAt: new Date(Date.now() + 65_000).toISOString(),
    ignorarIntervalo: true,
    textos: { titulo: `Lembrete ${sfx}` },
  });
  await esperarNoSino(page, /Hora de postar/, 150_000);
  await sino(page).click();
  await page.getByRole("menuitem", { name: /Hora de postar/ }).first().click();
  await expect(page).toHaveURL(new RegExp(`/app/conteudos/${doMembro}\\?conta=${p.contaId}`));
  const aba = page.getByRole("tabpanel");
  await expect(aba.getByText("A postar", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/014-a-postar.png`, fullPage: true });
  await aba.getByRole("button", { name: "Postado", exact: true }).click();
  const postado = page.getByRole("dialog", { name: "Marcar como postado" });
  await postado.getByLabel("Link do post (opcional)").fill("https://example.com/post/e2e");
  await postado.getByRole("button", { name: "Confirmar postado" }).click();
  await expect(aba.getByText("Postado", { exact: true }).first()).toBeVisible();
  const final = await getJson<{ destino: Destino }>(request, auth, `/api/destinos/${logo.id}`);
  expect(final.destino).toMatchObject({ estado: "postado", postedUrl: "https://example.com/post/e2e" });

  expect(social, "nenhuma requisição para rede social").toEqual([]);
});

// ---------------------------------------------------------------------------------------------
// US4 (T059): sequência de 7 com um conflito pulado, prévia desatualizada, textos da IA e
// "Trocar horários"
// ---------------------------------------------------------------------------------------------
test("US4: agendar em sequência com prévia e trocar horários", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const social = vigiarRedesSociais(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Sequencia", sfx);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 2);
  const buf = readFileSync(video);
  const ids: string[] = [];
  for (let i = 1; i <= 7; i++) ids.push(await enviarVideoProprio(request, auth, p.perfilId, buf, `Seq ${i} ${sfx}`));
  // dois de fora da sequência: um já agendado amanhã às 19:00 (conflito) e outro para a outra aba
  const ocupante = await enviarVideoProprio(request, auth, p.perfilId, buf, `Ocupante ${sfx}`);
  const intruso = await enviarVideoProprio(request, auth, p.perfilId, buf, `Intruso ${sfx}`);
  await agendarViaApi(request, auth, { conteudoId: ocupante, contaId: p.contaId, plannedAt: spIso(spDay(1), "19:00"), textos: { titulo: `Ocupante ${sfx}` } });

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos?perfil=${p.perfilId}`);
  for (let i = 1; i <= 7; i++) await linha(page, `Seq ${i} ${sfx}`).getByRole("checkbox").check();
  await page.getByRole("region", { name: "Selecionados" }).getByRole("button", { name: "Agendar em sequência" }).click();
  const seq = page.getByRole("dialog", { name: "Agendar em sequência" });
  await escolherConta(seq.getByLabel("Conta"), p.handle);
  await preencherData(seq.getByLabel("Primeira data"), spDay(1));
  await seq.getByRole("textbox", { name: "Horários" }).fill("19:00");
  await seq.getByRole("textbox", { name: "Horários" }).press("Enter");
  await expect(seq.getByRole("list", { name: "Horários escolhidos" })).toContainText("19:00");
  await seq.getByLabel("Gerar textos com IA para os que não têm").check();
  await seq.getByRole("button", { name: "Ver prévia" }).click();
  const previa = seq.getByRole("table", { name: "Prévia da sequência" });
  await expect(previa.getByRole("row").filter({ hasText: sfx })).toHaveCount(7);
  await expect(seq).toContainText("30 min");
  await expect(seq).toContainText(/pulado|conflito/i);
  await page.screenshot({ path: `${SHOTS}/014-sequencia-previa.png`, fullPage: true });

  // outra aba agenda um horário da prévia antes da confirmação: a prévia muda
  await agendarViaApi(request, auth, { conteudoId: intruso, contaId: p.contaId, plannedAt: spIso(spDay(3), "19:00"), textos: { titulo: `Intruso ${sfx}` } });
  await seq.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(seq.getByRole("alert").filter({ hasText: "A prévia mudou" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/014-sequencia-desatualizada.png`, fullPage: true });
  await seq.getByRole("button", { name: "Confirmar", exact: true }).click();

  // os 7 agendados, um por dia, pulando amanhã e o dia do intruso; textos gerados pela IA falsa
  await expect
    .poll(
      async () => {
        const ds = await Promise.all(ids.map((id) => destinosDoConteudo(request, auth, id)));
        return ds.filter((d) => d[0]?.estado === "agendado" && /^Título sugerido pela IA/.test(d[0].titulo)).length;
      },
      { timeout: 90_000, message: "7 agendados com textos da IA" },
    )
    .toBe(7);
  const datas = (await Promise.all(ids.map(async (id) => (await destinosDoConteudo(request, auth, id))[0].plannedAt!))).map((iso) =>
    spParts(new Date(iso)),
  );
  const dias = datas.map((d) => `${d.year}-${d.month}-${d.day}`);
  expect(new Set(dias).size, "um por dia").toBe(7);
  expect(dias).not.toContain(spDay(1));
  expect(dias).not.toContain(spDay(3));
  expect(datas.every((d) => `${d.hour}:${d.minute}` === "19:00")).toBe(true);
  await page.screenshot({ path: `${SHOTS}/014-sequencia-feita.png`, fullPage: true });

  // "Trocar horários": só os dois mudam
  const antes = await Promise.all(ids.map(async (id) => (await destinosDoConteudo(request, auth, id))[0].plannedAt));
  await page.goto(`/app/conteudos?perfil=${p.perfilId}`);
  await linha(page, `Seq 1 ${sfx}`).getByRole("checkbox").check();
  await linha(page, `Seq 2 ${sfx}`).getByRole("checkbox").check();
  const barraSeq = page.getByRole("region", { name: "Selecionados" });
  await escolherConta(barraSeq.getByLabel("Conta"), p.handle);
  await barraSeq.getByRole("button", { name: "Trocar horários" }).click();
  await expect(barraSeq.getByRole("alert")).toContainText(/: 2 ok(?!.*falha)/);
  await expect
    .poll(async () => (await destinosDoConteudo(request, auth, ids[0]))[0].plannedAt)
    .toBe(antes[1]);
  const depois = await Promise.all(ids.map(async (id) => (await destinosDoConteudo(request, auth, id))[0].plannedAt));
  expect(depois[1]).toBe(antes[0]);
  expect(depois.slice(2)).toEqual(antes.slice(2));

  expect(social, "nenhuma requisição para rede social").toEqual([]);
});

// ---------------------------------------------------------------------------------------------
// US5 (T065): vídeo próprio pela UI; filtro de origem; aprovar e agendar; horizontal e inválido
// ---------------------------------------------------------------------------------------------
test("US5: vídeo próprio entra pronto, filtra por origem e agenda em lembrete", async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);
  const social = vigiarRedesSociais(page);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Queridinhos", sfx);
  const corte = await (async () => {
    const v = testInfo.outputPath("corte.mp4");
    syntheticMp4(v, 2);
    return enviarCorte(request, auth, p.perfilId, v, `Corte ${sfx}`);
  })();
  await esperarCortePronto(request, auth, corte);
  const vertical = testInfo.outputPath("vertical.mp4");
  syntheticMp4(vertical, 3, "540x960");
  const horizontal = testInfo.outputPath("horizontal.mp4");
  syntheticMp4(horizontal, 2, "960x540");
  const falso = testInfo.outputPath("falso.mp4");
  writeFileSync(falso, "isto não é um vídeo\n");

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/conteudos");

  // vertical: entra "Pronto" com origem "Vídeo próprio"
  await page.getByRole("button", { name: "Enviar vídeo próprio" }).click();
  let dlg = page.getByRole("dialog", { name: "Enviar vídeo próprio" });
  await dlg.getByLabel("Perfil").selectOption({ label: p.perfilName });
  await dlg.getByLabel("Vídeo", { exact: true }).setInputFiles(vertical);
  await dlg.getByLabel("Título").fill(`Próprio ${sfx}`);
  await dlg.getByRole("button", { name: "Enviar vídeo", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/conteudos\/[0-9a-f-]{36}/, { timeout: 60_000 });
  const proprioId = page.url().match(UUID)![0];
  await expect(page.getByText("Vídeo próprio").first()).toBeVisible();
  await expect(page.getByText("Pronto", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("não é vertical")).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/014-video-proprio.png`, fullPage: true });

  // filtro por origem: só ele
  await page.goto(`/app/conteudos?perfil=${p.perfilId}`);
  await expect(linha(page, `Corte ${sfx}`)).toBeVisible();
  await page.getByRole("button", { name: /Mais filtros/ }).click();
  await page.getByRole("dialog", { name: "Mais filtros" }).getByLabel("Origem").selectOption({ label: "Vídeo próprio" });
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/origem=video_proprio/);
  await expect(linha(page, `Próprio ${sfx}`)).toBeVisible();
  await expect(linha(page, `Próprio ${sfx}`)).toContainText("Vídeo próprio");
  await expect(linha(page, `Corte ${sfx}`)).toHaveCount(0);

  // aprovar e agendar em lembrete (o dono aprova e agenda no mesmo passo)
  await page.goto(`/app/conteudos/${proprioId}`);
  await page.getByRole("button", { name: "Agendar / Publicar" }).first().click();
  const ag = page.getByRole("dialog", { name: "Agendar ou publicar" });
  await escolherConta(ag.getByLabel("Conta"), p.handle);
  await preencherData(ag.getByLabel(/Data e hora/), `${spDay(2)}T12:00`);
  await ag.getByRole("textbox", { name: /^Legenda/ }).fill(`Próprio agendado ${sfx}`);
  await ag.getByRole("button", { name: "Aprovar e agendar" }).click();
  await expect(ag).toBeHidden();
  const [d] = await destinosDoConteudo(request, auth, proprioId);
  expect(d).toMatchObject({ estado: "agendado", modo: "lembrete" });

  // horizontal: aceito com o aviso "não é vertical"
  await page.goto("/app/conteudos");
  await page.getByRole("button", { name: "Enviar vídeo próprio" }).click();
  dlg = page.getByRole("dialog", { name: "Enviar vídeo próprio" });
  await dlg.getByLabel("Perfil").selectOption({ label: p.perfilName });
  await dlg.getByLabel("Vídeo", { exact: true }).setInputFiles(horizontal);
  await dlg.getByLabel("Título").fill(`Deitado ${sfx}`);
  await dlg.getByRole("button", { name: "Enviar vídeo", exact: true }).click();
  await expect(page.getByText(/não é vertical/).first()).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: `${SHOTS}/014-nao-vertical.png`, fullPage: true });

  // um .txt renomeado para .mp4: erro, nada entra
  await page.goto("/app/conteudos");
  await page.getByRole("button", { name: "Enviar vídeo próprio" }).click();
  dlg = page.getByRole("dialog", { name: "Enviar vídeo próprio" });
  await dlg.getByLabel("Perfil").selectOption({ label: p.perfilName });
  await dlg.getByLabel("Vídeo", { exact: true }).setInputFiles(falso);
  await dlg.getByLabel("Título").fill(`Falso ${sfx}`);
  await dlg.getByRole("button", { name: "Enviar vídeo", exact: true }).click();
  await expect(dlg.getByRole("alert")).toBeVisible({ timeout: 30_000 });
  const lista = await getJson<{ items: ConteudoItem[] }>(request, auth, `/api/conteudos?perfilId=${p.perfilId}&q=Falso`);
  expect(lista.items).toHaveLength(0);

  expect(social, "nenhuma requisição para rede social").toEqual([]);
});
