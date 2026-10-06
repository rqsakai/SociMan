import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { inflateRawSync } from "node:zlib";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import {
  adiantarBusca,
  adiantarColeta,
  apiToken,
  createPerfilViaApi,
  createVerifiedMember,
  criarVideoTikTok,
  escoposTikTok,
  interceptarLoginTikTok,
  login,
  logout,
  pedidosTikTok,
  publicarRascunhoTikTok,
  sqlE2e,
  syntheticMp4,
  type Member,
  type VideoTikTok,
} from "./helpers";

// Spec 016 (T080): métricas do TikTok na stack isolada, com a TikTok FALSA do `openshorts-fake`
// (`video/list`, `video/query`, stats no `user/info` e o post id de um rascunho finalizado) e o
// `agendador` com a trilha `metricas` a cada 2 s. A cadência por idade é a real (de hora em
// hora no começo): o teste adianta a agenda pelo banco da stack efêmera (`adiantarColeta`,
// `adiantarBusca`) e semeia o histórico longo por INSERT (o trigger das fotos aceita INSERT).
// Em todo teste, a coleta só LÊ: nenhum init, nenhum PUT de parte e nenhum Direct Post sai por
// causa dela (princípio I).

const SHOTS = ".playwright-mcp/sociman";
const LEITURA = new Set(["token", "user_info", "video_list", "video_query", "status"]);
const ENVIO = new Set(["inbox_init", "video_init", "put"]);

type Auth = { Authorization: string };

interface MarcoValor {
  valor: number | null;
  estimado: boolean;
  motivo: null | "ainda_nao" | "sem_dado";
}

interface Marcos {
  h1: Record<"views" | "likes" | "comments" | "shares", MarcoValor>;
  h24: Record<"views" | "likes" | "comments" | "shares", MarcoValor>;
  d7: Record<"views" | "likes" | "comments" | "shares", MarcoValor>;
  d30: Record<"views" | "likes" | "comments" | "shares", MarcoValor>;
}

interface FotoVideo {
  coletadoEm: string;
  idadeS: number;
  alvoIdadeMin: number;
  views: number | null;
  likes: number | null;
}

interface VideoResumo {
  id: string;
  contaId: string | null;
  conta: { id: string; handle: string } | null;
  serieRotulo: string | null;
  origem: "corte" | "video_proprio" | "fora" | "anonima";
  publicadoEm: string;
  duracaoS: number;
  legenda: string | null;
  url: string | null;
  conteudoId: string | null;
  destinoId: string | null;
  vinculoMetodo: string | null;
  views24h: MarcoValor;
  views7d: MarcoValor;
  ultima: FotoVideo | null;
}

interface VideoDetalhe extends VideoResumo {
  fotos: FotoVideo[];
  marcos: Marcos;
  coletaParadaEm: string | null;
}

interface EstadoColeta {
  permissao: "ok" | "faltando" | "sem_conexao";
  escoposFaltando: string[];
  coletando: boolean;
  habilitada: boolean;
  ultimaColetaEm: string | null;
  varreduraConcluida: boolean;
  videos: number;
  fotos: number;
}

interface Conexao {
  estado: string;
  version?: number;
  metricas: EstadoColeta | null;
}

interface Destino {
  id: string;
  conteudoId: string;
  estado: string;
  modo: string;
  version: number;
}

interface Candidato {
  video: VideoResumo;
  duracaoDiferencaS: number;
  legenda: "compativel" | "neutra" | "incompativel";
}

interface Vinculo {
  estado: "vinculado" | "buscando" | "a_confirmar" | "sem_vinculo" | "indisponivel";
  video: VideoResumo | null;
  metodo: string | null;
  ancora: "entrega" | "postado" | null;
  candidatos: Candidato[];
  bloqueado: boolean;
  automatico: boolean;
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
  return (await getJson<{ items: { details: { acao?: string } }[] }>(request, auth, url)).items.map((v) => v.details.acao);
}

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

// Conecta pela API (iniciar → "login" com `code=e2e-<handle>` → retorno). Os escopos concedidos
// são os que a TikTok falsa tem para o handle (`escoposTikTok`).
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

async function agendar(
  request: APIRequestContext,
  auth: Auth,
  body: { conteudoId: string; contaId: string; plannedAt: string; modo: "lembrete" | "criar_rascunho"; legenda: string },
): Promise<Destino> {
  const res = await request.post("/api/agendamentos", {
    headers: auth,
    data: {
      conteudoId: body.conteudoId,
      contaId: body.contaId,
      plannedAt: body.plannedAt,
      modo: body.modo,
      ignorarIntervalo: true,
      textos: { descricao: body.legenda },
    },
  });
  expect([200, 201], `POST /api/agendamentos: ${await res.text()}`).toContain(res.status());
  return ((await res.json()) as { destino: Destino }).destino;
}

async function destino(request: APIRequestContext, auth: Auth, id: string): Promise<Destino> {
  return (await getJson<{ destino: Destino }>(request, auth, `/api/destinos/${id}`)).destino;
}

async function esperarEstado(request: APIRequestContext, auth: Auth, id: string, estado: string, timeout = 120_000): Promise<void> {
  await expect
    .poll(async () => (await destino(request, auth, id)).estado, { timeout, intervals: [1_000, 2_000], message: `destino ${id} → ${estado}` })
    .toBe(estado);
}

async function vinculo(request: APIRequestContext, auth: Auth, destinoId: string): Promise<Vinculo> {
  return getJson<Vinculo>(request, auth, `/api/destinos/${destinoId}/vinculo`);
}

async function esperarVinculo(request: APIRequestContext, auth: Auth, destinoId: string, estado: Vinculo["estado"], timeout = 60_000): Promise<Vinculo> {
  let atual: Vinculo | undefined;
  await expect
    .poll(async () => (atual = await vinculo(request, auth, destinoId)).estado, { timeout, intervals: [1_000, 2_000], message: `vínculo ${destinoId} → ${estado}` })
    .toBe(estado);
  return atual!;
}

// Os vídeos coletados de uma conta (o ranking pela data de publicação).
async function videosDaConta(request: APIRequestContext, auth: Auth, contaId: string, extra = ""): Promise<VideoResumo[]> {
  return (await getJson<{ items: VideoResumo[] }>(request, auth, `/api/metricas/videos?contaId=${contaId}&ordem=publicadoEm&limite=100${extra}`)).items;
}

async function esperarVideo(request: APIRequestContext, auth: Auth, contaId: string, v: VideoTikTok, timeout = 60_000): Promise<VideoResumo> {
  let achado: VideoResumo | undefined;
  await expect
    .poll(async () => {
      achado = (await videosDaConta(request, auth, contaId)).find((x) => x.url?.endsWith(`/video/${v.id}`));
      return Boolean(achado);
    }, { timeout, intervals: [1_000, 2_000], message: `vídeo ${v.legenda} descoberto` })
    .toBe(true);
  return achado!;
}

async function videoDetalhe(request: APIRequestContext, auth: Auth, id: string): Promise<VideoDetalhe> {
  return getJson<VideoDetalhe>(request, auth, `/api/metricas/videos/${id}`);
}

// Princípio I: nenhum pedido de envio (init, parte, Direct Post) para a conta depois do índice
// `desde` (o total de pedidos dela antes do trecho que só coleta), e nada fora da lista fechada.
function soLeitura(handle: string, desde = 0): void {
  const pedidos = pedidosTikTok(handle).slice(desde);
  expect(pedidos.filter((p) => p.endpoint === "desconhecido"), "nenhum pedido fora da lista fechada").toEqual([]);
  expect(pedidos.filter((p) => ENVIO.has(p.endpoint)).map((p) => p.endpoint), "a coleta nunca envia").toEqual([]);
  const fora = pedidos.filter((p) => !LEITURA.has(p.endpoint) && p.endpoint !== "revoke");
  expect(fora.map((p) => p.endpoint), "só token, user_info, video_list, video_query e status").toEqual([]);
}

// ---------------------------------------------------------------------------------------------
// ZIP e CSV (sem dependência nova)
// ---------------------------------------------------------------------------------------------

function lerZip(buf: Buffer): Map<string, Buffer> {
  let eocd = buf.length - 22;
  while (eocd >= 0 && buf.readUInt32LE(eocd) !== 0x06054b50) eocd--;
  expect(eocd, "ZIP sem o diretório central").toBeGreaterThanOrEqual(0);
  const total = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  const arquivos = new Map<string, Buffer>();
  for (let i = 0; i < total; i++) {
    expect(buf.readUInt32LE(p)).toBe(0x02014b50);
    const metodo = buf.readUInt16LE(p + 10);
    const tamanho = buf.readUInt32LE(p + 20);
    const [n, e, c] = [buf.readUInt16LE(p + 28), buf.readUInt16LE(p + 30), buf.readUInt16LE(p + 32)];
    const local = buf.readUInt32LE(p + 42);
    const nome = buf.subarray(p + 46, p + 46 + n).toString("utf8");
    const inicio = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
    const dados = buf.subarray(inicio, inicio + tamanho);
    arquivos.set(nome, metodo === 8 ? inflateRawSync(dados) : Buffer.from(dados));
    p += 46 + n + e + c;
  }
  return arquivos;
}

// CSV com aspas (RFC 4180), sem o BOM; devolve as linhas como listas de campos.
function lerCsv(texto: string): string[][] {
  const s = texto.replace(/^﻿/, "");
  const linhas: string[][] = [];
  let linha: string[] = [];
  let campo = "";
  let aspas = false;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (aspas) {
      if (ch === '"' && s[i + 1] === '"') {
        campo += '"';
        i++;
      } else if (ch === '"') aspas = false;
      else campo += ch;
    } else if (ch === '"') aspas = true;
    else if (ch === ",") {
      linha.push(campo);
      campo = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && s[i + 1] === "\n") i++;
      linha.push(campo);
      linhas.push(linha);
      linha = [];
      campo = "";
    } else campo += ch;
  }
  if (campo !== "" || linha.length) linhas.push([...linha, campo]);
  return linhas;
}

// "AAAA-MM-DD" em São Paulo, `dias` a partir de hoje.
function diaSp(dias: number): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date(Date.now() + dias * 86_400_000));
}

// ---------------------------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------------------------

async function abrirContas(page: Page, perfilId: string): Promise<void> {
  await page.goto(`/app/perfis/${perfilId}`);
  await page.getByRole("tab", { name: "Contas", exact: true }).click();
}

// Filtros globais do analytics (spec 019): perfil e conta (a conta só abre depois do perfil).
async function escolherConta(page: Page, perfil: string, handle: string): Promise<void> {
  await page.getByLabel("Perfil", { exact: true }).selectOption({ label: perfil });
  const conta = page.getByRole("combobox", { name: "Conta", exact: true });
  await expect(conta).toBeEnabled();
  await conta.selectOption({ label: `@${handle} (TikTok)` });
}

// Recarrega até o texto aparecer no painel (a tela não tem tempo real).
async function esperarNoPainel(page: Page, texto: string | RegExp, timeout = 60_000): Promise<void> {
  await expect(async () => {
    await page.reload();
    await expect(page.getByRole("main").getByText(texto).first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout, intervals: [1_000, 2_000] });
}

// ---------------------------------------------------------------------------------------------
// US1 + US2: reconectar libera as métricas; fotos da conta e dos vídeos; membro só vê o estado
// ---------------------------------------------------------------------------------------------
test("US1/US2: reconectar libera a coleta; fotos da conta e dos vídeos; membro só vê o estado", async ({ page, request }) => {
  test.setTimeout(360_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Taverna", sfx);
  const member: Member = await createVerifiedMember(page);

  // a conta tem 2 posts públicos (um com mais de 1 ano) e 1 privado
  const recente = criarVideoTikTok(p.handle, { duracao: 31, legenda: `Recente ${sfx} #taverna`, idadeS: 3 * 3600, views: 900 });
  const antigo = criarVideoTikTok(p.handle, { duracao: 45, legenda: `Antigo ${sfx}`, idadeS: 400 * 86_400, views: 50_000, ritmo: { views: 0 } });
  criarVideoTikTok(p.handle, { duracao: 20, legenda: `Privado ${sfx}`, idadeS: 3600, publico: false });

  // ---- conectada antes da 016 (sem os escopos de métricas): aviso, e nenhuma coleta ----
  await conectarViaApi(request, auth, p.contaId, p.handle);
  const antes = (await conexao(request, auth, p.contaId)).metricas!;
  expect(antes).toMatchObject({ permissao: "faltando", coletando: false, habilitada: true });
  expect(antes.escoposFaltando).toEqual(expect.arrayContaining(["user.info.stats", "video.list"]));
  await page.waitForTimeout(6_000); // três voltas da trilha
  expect(pedidosTikTok(p.handle).filter((x) => x.endpoint === "video_list" || x.endpoint === "video_query"), "sem escopos, nada é coletado").toEqual([]);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrirContas(page, p.perfilId);
  const painel = page.getByRole("tabpanel");
  const reconectar = painel.getByRole("button", { name: "Reconectar para liberar métricas" });
  await expect(reconectar).toBeVisible();
  await expect(painel.getByText(/Faltam permissões/).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-conta-sem-escopos.png`, fullPage: true });

  // ---- o dono reconecta marcando as permissões novas: a mesma conexão é ampliada ----
  escoposTikTok(p.handle);
  await interceptarLoginTikTok(page, p.handle);
  await reconectar.click();
  await expect(page).toHaveURL(new RegExp(`/app/perfis/${p.perfilId}`));
  await expect
    .poll(async () => (await conexao(request, auth, p.contaId)).metricas?.coletando, { timeout: 30_000 })
    .toBe(true);
  expect(await acoes(request, auth, `/api/contas/${p.contaId}/conexao/versions`)).toContain("ampliada");

  // ---- a 1ª volta: foto da conta, varredura com os 2 públicos (o privado não aparece) ----
  await expect
    .poll(async () => {
      const m = (await conexao(request, auth, p.contaId)).metricas!;
      return m.varreduraConcluida && m.videos === 2 && m.fotos >= 2;
    }, { timeout: 60_000, intervals: [1_000, 2_000], message: "varredura inicial" })
    .toBe(true);
  const conta = await getJson<{ coleta: EstadoColeta; fotos: { seguidores: number | null; videos: number | null }[] }>(
    request, auth, `/api/contas/${p.contaId}/metricas`,
  );
  expect(conta.fotos.length, "1ª foto da conta (SC-001)").toBeGreaterThanOrEqual(1);
  expect(conta.fotos[0].seguidores).not.toBeNull();
  expect(conta.fotos[0].videos).toBe(2);
  const vAntigo = await videoDetalhe(request, auth, (await esperarVideo(request, auth, p.contaId, antigo)).id);
  expect(vAntigo.fotos, "vídeo com mais de 1 ano: só a foto da descoberta (Q2 = A)").toHaveLength(1);
  expect(vAntigo.fotos[0].views).toBe(50_000);
  expect(vAntigo.coletaParadaEm).not.toBeNull();
  const vRecente = await esperarVideo(request, auth, p.contaId, recente);
  expect(vRecente).toMatchObject({ origem: "fora", duracaoS: 31, legenda: `Recente ${sfx} #taverna` });

  await esperarNoPainel(page, "Coletando métricas");
  await expect(painel.getByRole("button", { name: "Reconectar para liberar métricas" })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/016-coletando.png`, fullPage: true });

  // ---- um post novo, com 59 min 40 s: a descoberta tira a 1ª foto e a fila tira a de 1 h ----
  const novo = criarVideoTikTok(p.handle, { duracao: 12, legenda: `Novo ${sfx}`, idadeS: 59 * 60 + 40, views: 100 });
  adiantarColeta(p.contaId);
  const vNovo = await esperarVideo(request, auth, p.contaId, novo, 30_000);
  let fotos: FotoVideo[] = [];
  await expect
    .poll(async () => (fotos = (await videoDetalhe(request, auth, vNovo.id)).fotos).length, { timeout: 60_000, intervals: [2_000], message: "foto de 1 h" })
    .toBeGreaterThanOrEqual(2);
  fotos.sort((a, b) => a.idadeS - b.idadeS);
  expect(fotos[1].alvoIdadeMin).toBe(60);
  expect(fotos[1].views!, "os números crescem entre as fotos").toBeGreaterThan(fotos[0].views!);
  expect(new Set(fotos.map((f) => f.alvoIdadeMin)).size, "uma foto por janela").toBe(fotos.length);
  await logout(page);

  // ---- membro: vê "Coletando métricas", sem reconectar nem desconectar ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await abrirContas(page, p.perfilId);
  await expect(page.getByRole("tabpanel").getByText("Coletando métricas").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Reconectar para liberar métricas" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Desconectar" })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/016-coletando-membro.png`, fullPage: true });
  const memberAuth = { Authorization: `Bearer ${await apiToken(request, member.email, member.final)}` };
  const ini = await request.post(`/api/contas/${p.contaId}/conexao/iniciar`, { headers: memberAuth, data: {} });
  expect(ini.status(), "membro não reconecta").toBe(403);

  soLeitura(p.handle);
});

// ---------------------------------------------------------------------------------------------
// US3 nível 1: o rascunho finalizado no app vira "Publicado" com o link; link de outra conta
// recusado; desfazer (bloqueia o automático) e refazer pelo link; a coleta só lê
// ---------------------------------------------------------------------------------------------
test("US3: rascunho publicado no app é ligado sozinho; link de outra conta recusado; desfazer e refazer", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Rascunho", sfx);
  const outra = await perfilComConta(request, token, "Outra", sfx);
  escoposTikTok(p.handle);
  escoposTikTok(outra.handle);
  await conectarViaApi(request, auth, p.contaId, p.handle);
  await conectarViaApi(request, auth, outra.contaId, outra.handle);
  await enviosAutomaticos(request, auth, true);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 2);
  const conteudo = await videoProprio(request, auth, p.perfilId, readFileSync(video), `Rascunho ${sfx}`);
  const legenda = `Legenda do rascunho ${sfx} achados da semana`;
  const d = await agendar(request, auth, { conteudoId: conteudo, contaId: p.contaId, plannedAt: new Date(Date.now() + 3_000).toISOString(), modo: "criar_rascunho", legenda });
  await esperarEstado(request, auth, d.id, "rascunho_criado");
  const aposEntrega = pedidosTikTok(p.handle).length;

  // ---- entregue: "Procurando o post" (nível 1) ----
  await expect.poll(() => sqlE2e(`select count(*) from metricas_buscas_post where destino_id = '${d.id}'`)[0], { timeout: 30_000 }).toBe("1");
  expect((await vinculo(request, auth, d.id))).toMatchObject({ estado: "buscando", ancora: "entrega" });
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos/${conteudo}?conta=${p.contaId}`);
  // spec 018: o desempenho fica na coluna da direita, fora do painel da conta.
  const aba = page.getByRole("main");
  await expect(aba.getByText("Desempenho").first()).toBeVisible();
  await expect(aba.getByText("Procurando o post").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-procurando-post.png`, fullPage: true });

  // ---- o dono finaliza o rascunho no app: o status traz o post id e o destino vira Publicado ----
  const post = publicarRascunhoTikTok(p.handle, { duracao: 2, legenda });
  adiantarBusca(d.id);
  await esperarEstado(request, auth, d.id, "publicado", 60_000);
  const v1 = await vinculo(request, auth, d.id);
  expect(v1).toMatchObject({ estado: "vinculado", metodo: "envio", automatico: true });
  expect(v1.video?.url).toBe(post.share_url);
  expect(v1.video?.origem).toBe("video_proprio");
  expect(await acoes(request, auth, `/api/destinos/${d.id}/versions`)).toContain("vinculo_feito");
  const notif = await getJson<{ items: { tipo: string }[] }>(request, auth, "/api/notificacoes");
  expect(notif.items.map((n) => n.tipo)).toContain("post_detectado");
  await esperarNoPainel(page, "Publicado", 30_000);
  await expect(aba.getByRole("link", { name: "ver post na TikTok" }).first()).toHaveAttribute("href", post.share_url);
  await expect(aba.getByText(/pelo envio/).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-publicado-vinculado.png`, fullPage: true });
  // o histórico do destino não guarda id nem link da TikTok (R11)
  const hist = await getJson<{ items: unknown[] }>(request, auth, `/api/destinos/${d.id}/versions`);
  expect(JSON.stringify(hist)).not.toContain(post.id);

  // ---- desfazer: volta a "Rascunho criado", sem vínculo e bloqueado para o automático ----
  await aba.getByRole("button", { name: "Desfazer vínculo" }).click();
  const desfazer = page.getByRole("alertdialog");
  await expect(desfazer).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-desfazer-vinculo.png`, fullPage: true });
  await desfazer.getByRole("button", { name: "Desfazer vínculo" }).click();
  await expect(desfazer).toBeHidden();
  await esperarEstado(request, auth, d.id, "rascunho_criado", 15_000);
  const v2 = await vinculo(request, auth, d.id);
  expect(v2).toMatchObject({ estado: "sem_vinculo", bloqueado: true });
  expect(await acoes(request, auth, `/api/destinos/${d.id}/versions`)).toContain("vinculo_desfeito");
  adiantarColeta(p.contaId);
  await page.waitForTimeout(6_000);
  expect((await vinculo(request, auth, d.id)).estado, "desfeito não volta sozinho").toBe("sem_vinculo");
  const solto = (await videosDaConta(request, auth, p.contaId)).find((x) => x.url === post.share_url);
  expect(solto?.origem, "sem vínculo, o post é de fora").toBe("fora");

  // ---- link de outra conta: recusado com os dois @ ----
  const deOutra = criarVideoTikTok(outra.handle, { duracao: 2, legenda: `Outra ${sfx}` });
  await page.reload();
  await aba.getByRole("button", { name: "Ligar a um post" }).click();
  const ligar = page.getByRole("form", { name: "Ligar pelo link do post" });
  await ligar.getByLabel("Link do post").fill(deOutra.share_url);
  await ligar.getByRole("button", { name: "Ligar", exact: true }).click();
  await expect(aba.getByText(`O link é de @${outra.handle}; este destino é de @${p.handle}`).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-link-outra-conta.png`, fullPage: true });
  const recusa = await request.post(`/api/destinos/${d.id}/vinculo`, {
    headers: auth,
    data: { version: (await destino(request, auth, d.id)).version, link: deOutra.share_url },
  });
  expect(recusa.status()).toBe(409);
  expect(((await recusa.json()) as { error: { code: string } }).error.code).toBe("link_outra_conta");

  // ---- o link certo refaz o vínculo (nível 3) ----
  await ligar.getByLabel("Link do post").fill(post.share_url);
  await ligar.getByRole("button", { name: "Ligar", exact: true }).click();
  await expect(ligar).toBeHidden();
  await esperarEstado(request, auth, d.id, "publicado", 15_000);
  expect(await vinculo(request, auth, d.id)).toMatchObject({ estado: "vinculado", metodo: "link", automatico: false });
  await expect(aba.getByText(/pelo link/).first()).toBeVisible();

  // ---- a coleta e o vínculo só leram: nenhum init nem parte depois da entrega ----
  soLeitura(p.handle, aposEntrega);
  soLeitura(outra.handle);
});

// ---------------------------------------------------------------------------------------------
// US3 nível 2: dois posts possíveis → nada é ligado sozinho → "Escolha o post" em 1 clique
// ---------------------------------------------------------------------------------------------
test("US3: casamento ambíguo não liga sozinho; o dono escolhe o post em 1 clique", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Ambiguo", sfx);
  escoposTikTok(p.handle);
  await conectarViaApi(request, auth, p.contaId, p.handle);
  await enviosAutomaticos(request, auth, true);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 2);
  const conteudo = await videoProprio(request, auth, p.perfilId, readFileSync(video), `Ambiguo ${sfx}`);
  const legenda = `Dois achados iguais ${sfx} para a cozinha`;
  const d = await agendar(request, auth, { conteudoId: conteudo, contaId: p.contaId, plannedAt: new Date(Date.now() + 3_000).toISOString(), modo: "criar_rascunho", legenda });
  await esperarEstado(request, auth, d.id, "rascunho_criado");
  const aposEntrega = pedidosTikTok(p.handle).length;

  // o rascunho vira post, mas o status não traz o id; outro post igual sai na mesma hora
  const a = publicarRascunhoTikTok(p.handle, { duracao: 2, legenda, informarId: false });
  const b = criarVideoTikTok(p.handle, { duracao: 2, legenda });
  adiantarColeta(p.contaId);
  await esperarVideo(request, auth, p.contaId, a, 30_000);
  await esperarVideo(request, auth, p.contaId, b, 30_000);
  const v = await esperarVinculo(request, auth, d.id, "a_confirmar");
  expect(v.candidatos.map((c) => c.video.url).sort()).toEqual([a.share_url, b.share_url].sort());
  expect((await destino(request, auth, d.id)).estado, "nada ligado sozinho").toBe("rascunho_criado");
  await expect
    .poll(async () => (await getJson<{ items: { tipo: string }[] }>(request, auth, "/api/notificacoes")).items.filter((n) => n.tipo === "vinculo_a_confirmar").length)
    .toBeGreaterThanOrEqual(1);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos/${conteudo}?conta=${p.contaId}`);
  // spec 018: o desempenho fica na coluna da direita, fora do painel da conta.
  const aba = page.getByRole("main");
  await expect(aba.getByText("Escolha o post").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-escolha-o-post.png`, fullPage: true });
  await aba.getByRole("button", { name: "Este é o post" }).first().click();
  await esperarEstado(request, auth, d.id, "publicado", 15_000);
  const ligado = await vinculo(request, auth, d.id);
  expect(ligado).toMatchObject({ estado: "vinculado", metodo: "escolha" });
  expect([a.share_url, b.share_url]).toContain(ligado.video?.url);
  await expect(aba.getByText(/escolhido/i).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-escolhido.png`, fullPage: true });

  soLeitura(p.handle, aposEntrega);
});

// ---------------------------------------------------------------------------------------------
// US3 (Q3 = A): lembrete — candidatos antes do clique; "Marcar como postado" liga sozinho;
// escolher o candidato marca como postado
// ---------------------------------------------------------------------------------------------
test("US3 (Q3 = A): lembrete mostra candidatos; Marcar como postado liga sozinho; escolher marca postado", async ({ page, request }, testInfo) => {
  test.setTimeout(360_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Lembrete", sfx);
  escoposTikTok(p.handle);
  await conectarViaApi(request, auth, p.contaId, p.handle);
  const video = testInfo.outputPath("v.mp4");
  syntheticMp4(video, 2);
  const buf = readFileSync(video);
  const cA = await videoProprio(request, auth, p.perfilId, buf, `Panela ${sfx}`);
  const cB = await videoProprio(request, auth, p.perfilId, buf, `Mochila ${sfx}`);
  const amanha = new Date(Date.now() + 86_400_000).toISOString();
  const legA = `Panela antiaderente ${sfx} que não gruda nada`;
  const legB = `Mochila impermeável ${sfx} para viagem longa`;
  const dA = await agendar(request, auth, { conteudoId: cA, contaId: p.contaId, plannedAt: amanha, modo: "lembrete", legenda: legA });
  const dB = await agendar(request, auth, { conteudoId: cB, contaId: p.contaId, plannedAt: amanha, modo: "lembrete", legenda: legB });

  // o dono postou os dois à mão no app, com a legenda do "Copiar textos"
  const postA = criarVideoTikTok(p.handle, { duracao: 2, legenda: legA });
  const postB = criarVideoTikTok(p.handle, { duracao: 2, legenda: legB });
  adiantarColeta(p.contaId);
  await esperarVideo(request, auth, p.contaId, postA, 30_000);
  await esperarVideo(request, auth, p.contaId, postB, 30_000);

  // ---- antes do clique: só candidatos, nada ligado sozinho ----
  await expect
    .poll(async () => (await vinculo(request, auth, dA.id)).candidatos.map((c) => c.video.url), { timeout: 30_000 })
    .toEqual([postA.share_url]);
  await page.waitForTimeout(6_000);
  const antes = await vinculo(request, auth, dA.id);
  expect(antes).toMatchObject({ estado: "sem_vinculo", ancora: null });
  expect((await destino(request, auth, dA.id)).estado).toBe("agendado");

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos/${cB}?conta=${p.contaId}`);
  // spec 018: o desempenho fica na coluna da direita, fora do painel da conta.
  const aba = page.getByRole("main");
  await expect(aba.getByRole("button", { name: "Este é o post" }).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-lembrete-candidatos.png`, fullPage: true });

  // ---- escolher em 1 clique: o destino vira Postado ligado ao post ----
  await aba.getByRole("button", { name: "Este é o post" }).first().click();
  await esperarEstado(request, auth, dB.id, "postado", 15_000);
  expect(await vinculo(request, auth, dB.id)).toMatchObject({ estado: "vinculado", metodo: "escolha" });
  expect((await vinculo(request, auth, dB.id)).video?.url).toBe(postB.share_url);
  await expect(aba.getByText("Postado", { exact: true }).first()).toBeVisible();

  // ---- o outro: "Marcar como postado" sem link → a próxima volta liga sozinho (casamento) ----
  await page.goto(`/app/conteudos/${cA}?conta=${p.contaId}`);
  // no lembrete, o botão é "Postado" (014); no rascunho criado, "Marcar como postado" (015)
  await aba.getByRole("button", { name: "Postado", exact: true }).click();
  const postado = page.getByRole("dialog", { name: "Marcar como postado" });
  await postado.getByRole("button", { name: "Confirmar postado" }).click();
  await expect(postado).toBeHidden();
  const ligado = await esperarVinculo(request, auth, dA.id, "vinculado", 30_000);
  expect(ligado).toMatchObject({ metodo: "casamento", ancora: "postado", automatico: true });
  expect(ligado.video?.url).toBe(postA.share_url);
  expect((await destino(request, auth, dA.id)).estado, "continua Postado").toBe("postado");
  await esperarNoPainel(page, "pela lista de vídeos", 15_000);
  await page.screenshot({ path: `${SHOTS}/016-lembrete-ligado.png`, fullPage: true });

  soLeitura(p.handle);
});

// ---------------------------------------------------------------------------------------------
// US4: ranking com fotos semeadas e curva com os marcos
// ---------------------------------------------------------------------------------------------
test("US4: ranking ordenável e curva com os marcos 1 h/24 h/7 d/30 d", async ({ page, request }) => {
  test.setTimeout(300_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Ranking", sfx);
  escoposTikTok(p.handle);
  const dia = 86_400;
  const vA = criarVideoTikTok(p.handle, { duracao: 30, legenda: `Campeão da semana ${sfx}`, idadeS: 10 * dia, views: 6000, ritmo: { views: 0, likes: 0, comments: 0, shares: 0 } });
  const vB = criarVideoTikTok(p.handle, { duracao: 25, legenda: `Segundo lugar ${sfx}`, idadeS: 9 * dia, views: 3500, ritmo: { views: 0, likes: 0, comments: 0, shares: 0 } });
  const vC = criarVideoTikTok(p.handle, { duracao: 20, legenda: `Estreia forte ${sfx}`, idadeS: 3 * dia, views: 2600, ritmo: { views: 0, likes: 0, comments: 0, shares: 0 } });
  await conectarViaApi(request, auth, p.contaId, p.handle);
  const ids = {
    A: (await esperarVideo(request, auth, p.contaId, vA)).id,
    B: (await esperarVideo(request, auth, p.contaId, vB)).id,
    C: (await esperarVideo(request, auth, p.contaId, vC)).id,
  };

  // histórico semeado: fotos exatamente em 1 h, 24 h e 7 d (o trigger aceita INSERT)
  const semear: [string, number, number][] = [
    [ids.A, 60, 500], [ids.A, 1440, 2000], [ids.A, 10080, 5000],
    [ids.B, 60, 300], [ids.B, 1440, 1500], [ids.B, 10080, 3000],
    [ids.C, 60, 800], [ids.C, 1440, 2500],
  ];
  const valores = semear.map(([id, alvo, views]) => `('${id}'::uuid, ${alvo}, ${views})`).join(", ");
  sqlE2e(
    `insert into metricas_video_fotos (video_id, coletado_em, idade_s, alvo_idade_min, views, likes, comments, shares) ` +
      `select v.id, v.publicado_em + make_interval(mins => s.alvo), s.alvo * 60, s.alvo, s.views, s.views / 10, s.views / 100, s.views / 200 ` +
      `from (values ${valores}) as s(id, alvo, views) join metricas_videos v on v.id = s.id on conflict do nothing`,
  );

  // ---- API: marcos exatos, 30 d "ainda não"; ranking por 7 d e por 24 h ----
  const a = await videoDetalhe(request, auth, ids.A);
  expect(a.marcos.h1.views).toMatchObject({ valor: 500, estimado: false });
  expect(a.marcos.h24.views).toMatchObject({ valor: 2000, estimado: false });
  expect(a.marcos.d7.views).toMatchObject({ valor: 5000, estimado: false });
  expect(a.marcos.d30.views).toMatchObject({ valor: null, motivo: "ainda_nao" });
  expect(a.fotos.length).toBeGreaterThanOrEqual(4);
  const c = await videoDetalhe(request, auth, ids.C);
  expect(c.marcos.d7.views.motivo).toBe("ainda_nao");
  const por7d = (await getJson<{ items: VideoResumo[] }>(request, auth, `/api/metricas/videos?contaId=${p.contaId}&ordem=views7d&direcao=desc`)).items;
  expect(por7d.slice(0, 2).map((x) => x.id)).toEqual([ids.A, ids.B]);
  const por24h = (await getJson<{ items: VideoResumo[] }>(request, auth, `/api/metricas/videos?contaId=${p.contaId}&ordem=views24h&direcao=desc`)).items;
  expect(por24h.map((x) => x.id)).toEqual([ids.C, ids.A, ids.B]);
  const padrao = (await getJson<{ items: VideoResumo[] }>(request, auth, `/api/metricas/videos?contaId=${p.contaId}`)).items;
  expect(padrao.map((x) => x.id), "padrão: views total").toEqual([ids.A, ids.B, ids.C]);
  const conta = await getJson<{ viewsTotal: number | null; fotos: { views: number | null }[] }>(request, auth, `/api/contas/${p.contaId}/metricas`);
  expect(conta.viewsTotal, "views da conta = soma da última foto de cada vídeo").toBe(6000 + 3500 + 2600);
  const soCortes = (await getJson<{ items: VideoResumo[] }>(request, auth, `/api/metricas/videos?contaId=${p.contaId}&origem=corte`)).items;
  expect(soCortes, "filtro de origem").toEqual([]);

  // ---- a tela: Ranking filtrado pela conta e ordenado por views em 7 dias ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.getByRole("link", { name: "Métricas" }).click();
  await expect(page).toHaveURL(/\/app\/metricas/);
  // spec 019: o ranking fica na aba Visão geral (a padrão)
  await expect(page.getByRole("tab", { name: "Visão geral" })).toHaveAttribute("aria-selected", "true");
  // o ranking segue o período global (padrão 7 d): os vídeos de 9 e 10 dias pedem 30 d
  const trinta = page.getByRole("group", { name: "Atalhos de período" }).getByRole("button", { name: "30 d" });
  await trinta.click();
  await expect(page).toHaveURL(/[?&]de=\d{4}-\d{2}-\d{2}/);
  await escolherConta(page, `Ranking ${sfx}`, p.handle);
  // padrão: views total (a última foto), sempre visível
  const linhas = page.getByRole("row");
  await expect(page.getByLabel("Ordenar por")).toHaveValue("views");
  await expect(linhas.nth(1)).toContainText(`Campeão da semana ${sfx}`);
  await expect(linhas.nth(1)).toContainText("6.000");
  await page.getByLabel("Ordenar por").selectOption("views7d");
  await expect(linhas.nth(1)).toContainText(`Campeão da semana ${sfx}`);
  await expect(linhas.nth(2)).toContainText(`Segundo lugar ${sfx}`);
  await page.screenshot({ path: `${SHOTS}/016-ranking.png`, fullPage: true });
  await page.getByLabel("Ordenar por").selectOption("views24h");
  await expect(linhas.nth(1)).toContainText(`Estreia forte ${sfx}`);

  // ---- o vídeo de fora abre a curva com os marcos ----
  // spec 019: "Principais vídeos" da Visão geral também liga o vídeo; o clique é no ranking
  await page.getByRole("table").getByRole("link", { name: `Campeão da semana ${sfx}` }).click();
  await expect(page).toHaveURL(new RegExp(`/app/metricas/videos/${ids.A}`));
  await expect(page.getByRole("img", { name: /Visualizações pela idade do vídeo/ }).first()).toBeVisible();
  await expect(page.getByText("ainda não").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "ver post na TikTok" }).first()).toHaveAttribute("href", vA.share_url);
  await page.screenshot({ path: `${SHOTS}/016-curva-marcos.png`, fullPage: true });

  // ---- a conta: gráfico de seguidores com o estado da coleta ----
  await page.goto("/app/metricas?aba=contas");
  await expect(page.getByRole("tab", { name: "Contas" })).toHaveAttribute("aria-selected", "true");
  await escolherConta(page, `Ranking ${sfx}`, p.handle);
  await expect(page.getByText("Coletando métricas").first()).toBeVisible();
  // views da conta: derivadas dos vídeos (card com o total atual e gráfico padrão)
  await expect(page.getByText("12.100", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: /Views totais dos vídeos ao longo do tempo/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "Seguidores", exact: true }).click();
  await expect(page.getByRole("img", { name: /Seguidores ao longo do tempo/ }).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-conta-grafico.png`, fullPage: true });

  soLeitura(p.handle);
});

// ---------------------------------------------------------------------------------------------
// US5: exportar o dataset (ZIP) com o dicionário; membro sem os botões de dono
// ---------------------------------------------------------------------------------------------
test("US5: exportar o ZIP em CSV com o cabeçalho do dicionário; membro não exporta", async ({ page, request }) => {
  test.setTimeout(300_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Exportar", sfx);
  escoposTikTok(p.handle);
  const v = criarVideoTikTok(p.handle, { duracao: 18, legenda: `Exportado, com "aspas" ${sfx}`, idadeS: 5 * 3600, views: 1234 });
  await conectarViaApi(request, auth, p.contaId, p.handle);
  await esperarVideo(request, auth, p.contaId, v);
  const member: Member = await createVerifiedMember(page);

  // ---- a API: ZIP com os 5 arquivos, cabeçalhos iguais ao dicionário ----
  const de = diaSp(-1);
  const ate = diaSp(1);
  const url = `/api/metricas/export?formato=csv&de=${de}&ate=${ate}&contaId=${p.contaId}`;
  const res = await request.get(url, { headers: auth });
  expect(res.status(), await res.text().catch(() => "")).toBe(200);
  expect(res.headers()["content-type"]).toContain("application/zip");
  expect(res.headers()["content-disposition"]).toContain(`sociman-metricas-${de.replaceAll("-", "")}-${ate.replaceAll("-", "")}.zip`);
  const zip = lerZip(await res.body());
  // spec 020 (FR-023): o dataset ganhou a série diária importada do Studio (vazia sem importação)
  expect([...zip.keys()].sort()).toEqual(["LEIAME.txt", "dicionario.csv", "fotos_conta.csv", "fotos_videos.csv", "studio_dias.csv", "videos.csv"]);
  const dic = lerCsv(zip.get("dicionario.csv")!.toString("utf8"));
  expect(dic[0]).toEqual(["arquivo", "coluna", "tipo", "unidade", "significado", "origem"]);
  for (const arquivo of ["fotos_videos", "videos", "fotos_conta", "studio_dias"]) {
    const bruto = zip.get(`${arquivo}.csv`)!;
    expect(bruto.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf])), `${arquivo}.csv em UTF-8 com BOM`).toBe(true);
    const cabecalho = lerCsv(bruto.toString("utf8"))[0];
    const doDicionario = dic.slice(1).filter((l) => l[0].replace(/\.[a-z]+$/, "") === arquivo).map((l) => l[1]);
    expect(cabecalho, `cabeçalho de ${arquivo}.csv = dicionário`).toEqual(doDicionario);
  }
  const videos = lerCsv(zip.get("videos.csv")!.toString("utf8"));
  const col = (nome: string) => videos[0].indexOf(nome);
  const linha = videos.find((l) => l[col("legenda")] === `Exportado, com "aspas" ${sfx}`);
  expect(linha, "o vídeo está no videos.csv, com a legenda intacta").toBeTruthy();
  expect(linha![col("origem")]).toBe("fora");
  for (const soSociman of ["conteudo_id", "destino_id", "gancho", "canal_fonte"]) expect(linha![col(soSociman)], soSociman).toBe("");
  expect(linha![col("video_ref")], "video_ref é o uuid do SociMan, nunca o id da TikTok").not.toBe(v.id);
  const fotos = lerCsv(zip.get("fotos_videos.csv")!.toString("utf8"));
  expect(fotos.slice(1).some((l) => l[fotos[0].indexOf("video_ref")] === linha![col("video_ref")])).toBe(true);
  expect(zip.get("LEIAME.txt")!.toString("utf8")).toMatch(/dicion/i);
  const semPeriodo = await request.get(`/api/metricas/export?formato=csv&contaId=${p.contaId}`, { headers: auth });
  expect(semPeriodo.status()).toBe(400);

  // ---- a tela: "Exportar" (dono) baixa o ZIP ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/metricas");
  await page.getByRole("button", { name: "Exportar" }).click();
  const dlg = page.getByRole("dialog", { name: "Exportar métricas" });
  await expect(dlg).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-exportar.png`, fullPage: true });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    dlg.getByRole("button", { name: "Exportar", exact: true }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^sociman-metricas-\d{8}-\d{8}\.zip$/);
  // o aviso de sucesso fica no canto de cima, sobre o "Sair": fecha antes de sair
  const aviso = page.locator("[data-sonner-toast]").filter({ hasText: "Métricas exportadas" });
  await expect(aviso).toBeVisible();
  await aviso.getByRole("button", { name: "Close toast" }).click();
  await expect(aviso).toHaveCount(0);
  await logout(page);

  // ---- membro: vê as métricas, sem Exportar; a API recusa ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/metricas");
  await expect(page.getByRole("tab", { name: "Visão geral" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Exportar" })).toHaveCount(0);
  const memberAuth = { Authorization: `Bearer ${await apiToken(request, member.email, member.final)}` };
  expect((await request.get(url, { headers: memberAuth })).status()).toBe(403);
  expect((await request.get(`/api/metricas/videos?contaId=${p.contaId}`, { headers: memberAuth })).status(), "membro vê o ranking").toBe(200);

  soLeitura(p.handle);
});

// ---------------------------------------------------------------------------------------------
// FR-009: desconectar pede a confirmação e anonimiza; a série anônima fica no ranking
// ---------------------------------------------------------------------------------------------
test("FR-009: desconectar com confirmação anonimiza a série; reconectar começa outra", async ({ page, request }) => {
  test.setTimeout(300_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const p = await perfilComConta(request, token, "Anonima", sfx);
  escoposTikTok(p.handle);
  const v = criarVideoTikTok(p.handle, { duracao: 22, legenda: `Vai sumir ${sfx}`, idadeS: 2 * 86_400, views: 777, ritmo: { views: 0 } });
  await conectarViaApi(request, auth, p.contaId, p.handle);
  const coletado = await esperarVideo(request, auth, p.contaId, v);

  // ---- a API recusa sem a confirmação, com as contagens; nada muda ----
  const c = await conexao(request, auth, p.contaId);
  const sem = await request.post(`/api/contas/${p.contaId}/conexao/desconectar`, { headers: auth, data: { version: c.version } });
  expect(sem.status()).toBe(409);
  const erro = ((await sem.json()) as { error: { code: string; details: { videos: number; fotos: number } } }).error;
  expect(erro.code).toBe("confirmar_anonimizacao");
  expect(erro.details.videos).toBe(1);
  expect((await conexao(request, auth, p.contaId)).estado).toBe("conectada");

  // ---- a tela: o aviso com N vídeos e M fotos, e a confirmação ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrirContas(page, p.perfilId);
  await page.getByRole("button", { name: "Desconectar" }).click();
  const dlg = page.getByRole("alertdialog");
  await expect(dlg).toContainText(`As métricas de @${p.handle} (1 vídeo,`);
  await expect(dlg).toContainText(/serão anonimizadas/);
  await expect(dlg).toContainText(/não pode ser desfeito/);
  await page.screenshot({ path: `${SHOTS}/016-anonimizar-confirmacao.png`, fullPage: true });
  await dlg.getByRole("button", { name: "Desconectar e anonimizar" }).click();
  await expect(page.getByRole("tabpanel").getByText("Não conectada", { exact: true }).first()).toBeVisible();
  expect(await acoes(request, auth, `/api/contas/${p.contaId}/conexao/versions`)).toContain("metricas_anonimizadas");

  // ---- a série virou "Conta anônima N", sem conta, link nem legenda; os números ficaram ----
  const anonimas = (await getJson<{ items: VideoResumo[] }>(request, auth, "/api/metricas/videos?origem=anonima&limite=100")).items;
  const anon = anonimas.find((x) => x.id === coletado.id);
  expect(anon, "o mesmo vídeo, agora anônimo").toBeTruthy();
  expect(anon).toMatchObject({ origem: "anonima", conta: null, contaId: null, url: null, legenda: null, destinoId: null });
  expect(anon!.serieRotulo).toMatch(/^Conta anônima \d+$/);
  expect(anon!.ultima?.views).toBe(777);
  expect(JSON.stringify(anonimas)).not.toContain(p.handle);
  expect(await videosDaConta(request, auth, p.contaId), "a conta não tem mais série").toEqual([]);

  await page.goto("/app/metricas");
  await page.getByRole("tab", { name: "Visão geral" }).click();
  await page.getByLabel("Origem").selectOption("anonima");
  await expect(page.getByText(anon!.serieRotulo!).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/016-serie-anonima.png`, fullPage: true });

  // ---- reconectar começa uma série nova; a anônima continua sem conta ----
  await conectarViaApi(request, auth, p.contaId, p.handle);
  const novo = await esperarVideo(request, auth, p.contaId, v);
  expect(novo.id, "outra série, outro video_ref").not.toBe(coletado.id);
  expect((await videoDetalhe(request, auth, coletado.id)).conta).toBeNull();

  soLeitura(p.handle);
});
