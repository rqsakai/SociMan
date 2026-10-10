import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, compose, createPerfilViaApi, login, nav, pngBuffer } from "./helpers";

// Spec 011 (T057): roteiros com vídeo local, com o Claude, o ComfyUI e o shop-tts falsos
// (`e2e/fakes/server.py` e `geracao_fake.py`, no `openshorts-fake`) e o serviço `gerador`. O plano
// tem 3 frases, uma por cena (todas novas: o perfil não tem cena para reaproveitar); os clipes e o
// upscale devolvem o mp4 fixo de 8 s; a narração é o wav fixo de 6 s. A montagem e o acabamento
// usam o ffmpeg de verdade do gerador.
// - revisar: criar pela tela, planejar, aprovar o texto e a narração (com a pronúncia do perfil no
//   pedido ao shop-tts), usar uma opção de keyframe e enviar outro pronto, aprovar os clipes e o
//   final; o conteúdo abre com o selo "Gerado por IA" e o vínculo com o roteiro;
// - automático: criar, ligar o automático e planejar (3 ações humanas, SC-001) e o roteiro chega
//   a "Pronto" sem parar.

type Auth = { Authorization: string };
type Base = { auth: Auth; perfilId: string; produtoId: string; vozId: string };
type Versao = { autor?: { tipo: string; nome: string }; details?: { geracaoId?: string; acao?: string; automatico?: boolean } };

test.describe.configure({ mode: "serial" });

function geracaoFake(metodo: "GET" | "POST", caminho: string, corpo?: unknown): unknown {
  const script = [
    "import json, sys, urllib.request",
    "corpo = sys.stdin.read().encode() or None",
    `req = urllib.request.Request("http://localhost:8000${caminho}", data=corpo, method="${metodo}",`,
    "                             headers={'content-type': 'application/json'})",
    "print(urllib.request.urlopen(req, timeout=5).read().decode())",
  ].join("\n");
  return JSON.parse(compose(["exec", "-T", "openshorts-fake", "python", "-c", script], corpo === undefined ? "" : JSON.stringify(corpo)));
}

const pronunciasTts = () => geracaoFake("GET", "/geracao-e2e/pronuncias") as { ultimo: Record<string, string> | null };

// WAV mono 24 kHz, 16 bits (a gravação da voz; o ffprobe da API aceita).
function wavBuffer(segundos = 20, freq = 440): Buffer {
  const taxa = 24000;
  const n = Math.floor(taxa * segundos);
  const buf = Buffer.alloc(44 + n * 2);
  buf.write("RIFF", 0);
  buf.writeUInt32LE(36 + n * 2, 4);
  buf.write("WAVEfmt ", 8);
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(taxa, 24);
  buf.writeUInt32LE(taxa * 2, 28);
  buf.writeUInt16LE(2, 32);
  buf.writeUInt16LE(16, 34);
  buf.write("data", 36);
  buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) buf.writeInt16LE(Math.round(8000 * Math.sin((2 * Math.PI * freq * i) / taxa)), 44 + i * 2);
  return buf;
}

async function json<T>(r: { status(): number; text(): Promise<string>; json(): Promise<unknown> }, status: number): Promise<T> {
  expect(r.status(), await r.text()).toBe(status);
  return (await r.json()) as T;
}

async function ate<T>(ler: () => Promise<T>, ok: (v: T) => boolean, timeout = 90_000): Promise<T> {
  let atual = await ler();
  await expect.poll(async () => ok((atual = await ler())), { timeout, intervals: [500, 1000] }).toBe(true);
  return atual;
}

// O produto do catálogo (012) aprovado: ficha (Claude falso), recorte (ComfyUI falso), sem flat.
async function produtoAprovado(request: APIRequestContext, auth: Auth, perfilId: string): Promise<string> {
  const r = await request.post(`/api/perfis/${perfilId}/produtos`, {
    headers: auth,
    multipart: { name: "shorts_canelado", obs: "sem flat", fotos: { name: "foto1.png", mimeType: "image/png", buffer: pngBuffer(800, 900) } },
  });
  const { id } = await json<{ id: string }>(r, 201);
  const ler = async () => json<{ status: string; version: number }>(await request.get(`/api/produtos/${id}`, { headers: auth }), 200);
  const p = await ate(ler, (x) => x.status === "revisao");
  await json(await request.post(`/api/produtos/${id}/aprovar`, { headers: auth, data: { version: p.version } }), 200);
  return id;
}

// A voz (025) gravada, com consentimento, a referência escolhida e sincronizada no shop-tts.
async function vozAprovada(request: APIRequestContext, auth: Auth, perfilId: string): Promise<string> {
  let v = await json<{ id: string; version: number }>(
    await request.post(`/api/perfis/${perfilId}/vozes`, { headers: auth, data: { name: "Roberta vendas", origem: "gravacao", tom: "vendas animada" } }), 201);
  const audio = await json<{ id: string }>(
    await request.post(`/api/perfis/${perfilId}/audios`, { headers: auth, multipart: { arquivo: { name: "gravacao.wav", mimeType: "audio/wav", buffer: wavBuffer() } } }), 201);
  v = await json(await request.patch(`/api/vozes/${v.id}`, { headers: auth, data: { version: v.version, gravacaoAudioId: audio.id } }), 200);
  v = await json(await request.put(`/api/vozes/${v.id}/consentimento`, {
    headers: auth, data: { version: v.version, nome: "Roberta Souza", data: "2026-10-01", observacao: "termo assinado" } }), 200);
  const g0 = await json<{ id: string }>(await request.post(`/api/perfis/${perfilId}/geracoes`, {
    headers: auth, data: { alvoTipo: "voz", alvoId: v.id, passo: "voz.gravacao", instrucao: "" } }), 201);
  const lerG = async () => json<{ id: string; status: string; version: number; candidatos: { id: string; numero: number }[] }>(
    await request.get(`/api/geracoes/${g0.id}`, { headers: auth }), 200);
  const g = await ate(lerG, (x) => x.status === "revisao");
  const atual = await json<{ version: number }>(await request.get(`/api/vozes/${v.id}`, { headers: auth }), 200);
  await json(await request.post(`/api/geracoes/${g.id}/escolher`, {
    headers: auth, data: { candidatoId: g.candidatos.find((c) => c.numero === 1)?.id, version: g.version, alvoVersion: atual.version } }), 200);
  const lerV = async () => json<{ status: string; sincronizadaEm: string | null }>(await request.get(`/api/vozes/${v.id}`, { headers: auth }), 200);
  await ate(lerV, (x) => x.status === "aprovada" && x.sincronizadaEm !== null);
  return v.id;
}

let base: Base | null = null;

async function preparar(request: APIRequestContext): Promise<Base> {
  if (base) return base;
  geracaoFake("POST", "/geracao-e2e/gpu", { ocupada: false });
  geracaoFake("POST", "/geracao-e2e/lento", { segundos: 1 });
  const sfx = Date.now();
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Vídeos ${sfx}`, slug: `videos-${sfx}` });
  const produtoId = await produtoAprovado(request, auth, perfilId);
  const vozId = await vozAprovada(request, auth, perfilId);
  // Uma pronúncia do perfil: vai no pedido da narração (contracts/shop-tts-pronuncias.md).
  await json(await request.post(`/api/perfis/${perfilId}/pronuncias`, { headers: auth, data: { escrita: "canelado", falada: "canelâdo" } }), 201);
  base = { auth, perfilId, produtoId, vozId };
  return base;
}

async function confirmar(page: Page, botao: string, escopo: Locator): Promise<void> {
  await escopo.getByRole("button", { name: botao }).first().click();
  const dialogo = page.getByRole("alertdialog");
  await expect(dialogo).toBeVisible();
  await dialogo.getByRole("button", { name: botao }).click();
  await expect(dialogo).toBeHidden();
}

// Pela tela: AI Studio › Vídeos › Novo vídeo, sem avatar (vídeo só de produto) e com a voz.
async function criarPelaTela(page: Page, b: Base, nome: string): Promise<string> {
  await nav(page, "Vídeos");
  await expect(page.getByRole("heading", { level: 1, name: "Vídeos" })).toBeVisible();
  await page.getByRole("link", { name: "Novo vídeo" }).first().click();
  await expect(page).toHaveURL(/\/app\/estudio\/videos\/novo/);
  const form = page.getByTestId("roteiro-novo");
  await form.getByLabel("Perfil do vídeo").selectOption(b.perfilId);
  await form.getByLabel("Nome do vídeo").fill(nome);
  await form.getByLabel("Brief").fill("Short canelado de cintura alta, venda animada.");
  const produtos = form.getByTestId("roteiro-produtos");
  await produtos.getByLabel("Produto aprovado").selectOption(b.produtoId);
  await produtos.getByRole("button", { name: "Adicionar produto" }).click();
  await expect(produtos.getByRole("button", { name: /^Tirar / })).toHaveCount(1);
  await form.getByLabel("Avatar").selectOption("");
  await form.getByLabel("Voz").selectOption(b.vozId);
  await form.getByRole("button", { name: "Criar vídeo" }).click();
  await expect(page).toHaveURL(/\/app\/roteiros\/[0-9a-f-]+$/, { timeout: 15_000 });
  return page.url().split("/").at(-1) as string;
}

const status = (page: Page) => page.getByTestId("roteiro-status");

async function aprovar(page: Page, portao: string, botao: string, rotulo: string): Promise<void> {
  await expect(status(page)).toHaveText(rotulo, { timeout: 120_000 });
  const caixa = page.getByTestId(`aprovar-${portao}`);
  await expect(caixa.getByRole("button", { name: botao })).toBeEnabled({ timeout: 15_000 });
  await caixa.getByRole("button", { name: botao }).click();
  await expect(caixa).toHaveCount(0, { timeout: 15_000 });
}

test("revisar: do plano ao conteúdo com todos os portões", async ({ page, request }) => {
  test.setTimeout(420_000);
  const b = await preparar(request);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const roteiroId = await criarPelaTela(page, b, "Short canelado · revisar");
  await expect(status(page)).toHaveText("Rascunho");
  await expect(page.getByTestId("roteiro-pecas")).toContainText("Roberta vendas");

  // 1. Texto: o plano chega com 3 cenas novas; aprovar.
  await page.getByRole("button", { name: "Planejar com IA" }).click();
  const texto = page.getByTestId("etapa-texto");
  await expect(texto.getByTestId("texto-cena-3")).toBeVisible({ timeout: 60_000 });
  await expect(texto.getByTestId("texto-cena-1").getByTestId("cena-origem")).toHaveText("nova");
  await expect(texto.getByLabel("Cena 1, frase 1")).toHaveValue("Gente, achei o short perfeito!");
  await aprovar(page, "texto", "Aprovar texto", "Aguardando o texto");

  // 2. Narração: o take inteiro com os tempos; a pronúncia do perfil foi no pedido.
  await expect(status(page)).toHaveText("Aguardando a narração", { timeout: 120_000 });
  const narracao = page.getByTestId("etapa-narracao");
  await expect(narracao.getByTestId("player-narracao")).toBeVisible();
  await expect(narracao.getByTestId("frase-tempo-3")).toBeVisible();
  await expect(narracao.getByTestId("narracao-desatualizada")).toHaveCount(0);
  expect(pronunciasTts().ultimo).toEqual({ canelado: "canelâdo" });
  await aprovar(page, "narracao", "Aprovar narração", "Aguardando a narração");

  // 3. Keyframes: a opção 1 na cena 1, um keyframe pronto na cena 2, a opção 2 na cena 3.
  await expect(status(page)).toHaveText("Aguardando os keyframes", { timeout: 120_000 });
  const kf = page.getByTestId("etapa-keyframes");
  const cena1 = kf.getByTestId("keyframe-cena-1");
  await expect(cena1.getByTestId("opcao-1")).toBeVisible({ timeout: 60_000 });
  await confirmar(page, "Usar opção 1", cena1.getByTestId("opcao-1"));
  await expect(cena1.getByRole("img", { name: "Keyframe da cena 1" })).toBeVisible({ timeout: 15_000 });
  const cena2 = kf.getByTestId("keyframe-cena-2");
  await cena2.getByLabel("Keyframe pronto da cena 2").setInputFiles({ name: "kf2.png", mimeType: "image/png", buffer: pngBuffer(736, 1280) });
  await cena2.getByRole("button", { name: "Enviar keyframe" }).click();
  await expect(cena2.getByRole("img", { name: "Keyframe da cena 2" })).toBeVisible({ timeout: 15_000 });
  const cena3 = kf.getByTestId("keyframe-cena-3");
  await expect(cena3.getByTestId("opcao-2")).toBeVisible({ timeout: 60_000 });
  await confirmar(page, "Usar opção 2", cena3.getByTestId("opcao-2"));
  await expect(cena3.getByRole("img", { name: "Keyframe da cena 3" })).toBeVisible({ timeout: 15_000 });
  await aprovar(page, "keyframes", "Aprovar keyframes", "Aguardando os keyframes");

  // 4. Clipes: um por cena, gerados aqui; aprovar.
  await expect(status(page)).toHaveText("Aguardando os clipes", { timeout: 180_000 });
  const clipes = page.getByTestId("etapa-clipes");
  for (const n of [1, 2, 3]) {
    const c = clipes.getByTestId(`clipe-cena-${n}`);
    await expect(c.getByTestId(`player-clipe-${n}`)).toBeVisible();
    await expect(c).toContainText("gerado aqui");
  }
  await aprovar(page, "clipes", "Aprovar clipes", "Aguardando os clipes");

  // 5. Final: a prévia montada; aprovar faz o acabamento HD e entrega o conteúdo.
  await expect(status(page)).toHaveText("Aguardando o final", { timeout: 120_000 });
  await expect(page.getByTestId("roteiro-previa").getByTestId("player-previa")).toBeVisible();
  await aprovar(page, "final", "Aprovar o final", "Aguardando o final");
  await expect(status(page)).toHaveText("Pronto", { timeout: 180_000 });
  const pronto = page.getByTestId("roteiro-pronto");
  await expect(page.getByTestId("roteiro-hd").getByTestId("player-hd")).toBeVisible();

  // O conteúdo: "Gerado por IA" e o vínculo com o roteiro.
  await pronto.getByRole("link", { name: "Abrir o conteúdo" }).click();
  await expect(page).toHaveURL(/\/app\/conteudos\/[0-9a-f-]+/, { timeout: 15_000 });
  await expect(page.getByTestId("selo-gerado-ia")).toHaveText(/Gerado por IA/);
  const vinculo = page.getByTestId("conteudo-roteiro");
  await expect(vinculo).toContainText("Short canelado · revisar");
  await expect(page.getByTestId("aviso-atribuicao")).toContainText("MiniMax H3");
  await vinculo.getByRole("link", { name: "Short canelado · revisar" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/roteiros/${roteiroId}$`));
  // O detalhe do roteiro marca "Vídeos" no menu.
  await expect(page.getByRole("navigation", { name: "Menu principal" }).getByRole("link", { name: "Vídeos", exact: true }))
    .toHaveAttribute("aria-current", "page");
});

test("automático: termina sem parar com no máximo 3 ações humanas (SC-001)", async ({ page, request }) => {
  test.setTimeout(420_000);
  const b = await preparar(request);
  let acoes = 0;
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  const roteiroId = await criarPelaTela(page, b, "Short canelado · automático");
  acoes++; // 1. criar

  const portoes = page.getByTestId("portoes");
  await portoes.getByTestId("modo-roteiro").selectOption({ label: "Automático" });
  await expect(page.getByText("Portões salvos.")).toBeVisible();
  await expect(portoes.getByTestId("portao-texto").getByRole("switch", { name: "Portão Texto" })).toBeDisabled();
  acoes++; // 2. ligar o automático

  await page.getByRole("button", { name: "Planejar com IA" }).click();
  acoes++; // 3. planejar

  // Nenhum portão para: texto, narração, keyframes (a escolha automática), clipes, prévia e HD.
  await expect(status(page)).toHaveText("Pronto", { timeout: 360_000 });
  await expect(page.getByTestId("roteiro-pronto").getByRole("link", { name: "Abrir o conteúdo" })).toBeVisible();
  await expect(page.locator('[data-testid^="aprovar-"]')).toHaveCount(0);
  expect(acoes).toBeLessThanOrEqual(3);

  // O histórico confirma: as versões do roteiro sem geração por trás são as 3 ações humanas
  // (criar, controle, planejar). As que aplicam um passo (o plano, a entrega) trazem o
  // `geracaoId` e ficam com o autor de quem pediu (regra da 021, R9), sem clique novo.
  const versoes = await json<{ items: Versao[] }>(await request.get(`/api/roteiros/${roteiroId}/versoes`, { headers: b.auth }), 200);
  const diretas = versoes.items.filter((v) => !v.details?.geracaoId);
  expect(diretas.length).toBeLessThanOrEqual(3);
  expect(diretas.every((v) => v.autor?.tipo === "usuario")).toBe(true);
  expect(versoes.items.some((v) => v.details?.acao === "entregue")).toBe(true);

  // A escolha do keyframe foi automática: a versão da cena que grava o keyframe é do ator
  // `system:roteiro` ("sistema (automático)"), e a da geração leva `details.automatico`.
  // (a 1ª posição reaproveita uma cena do roteiro anterior, que já tinha keyframe: olha uma nova)
  const detalhe = await json<{ posicoes: { reaproveitada: boolean; cena: { id: string; keyframeGeracaoId: string | null } }[] }>(
    await request.get(`/api/roteiros/${roteiroId}`, { headers: b.auth }), 200);
  expect(detalhe.posicoes[0].reaproveitada).toBe(true);
  const nova = detalhe.posicoes.find((pos) => !pos.reaproveitada);
  expect(nova).toBeDefined();
  const { id: cenaId, keyframeGeracaoId } = nova!.cena;
  const vCena = await json<{ items: Versao[] }>(await request.get(`/api/cenas/${cenaId}/versions`, { headers: b.auth }), 200);
  expect(vCena.items.some((v) => v.autor?.tipo === "sistema" && v.autor.nome === "sistema (automático)")).toBe(true);
  expect(keyframeGeracaoId).not.toBeNull();
});
