import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, compose, createPerfilViaApi, login, nav, pngBuffer } from "./helpers";

// Spec 031 (T022, T030): o vídeo guiado, com o Claude, o ComfyUI e o shop-tts falsos
// (`e2e/fakes/server.py` e `geracao_fake.py`, no `openshorts-fake`) e o serviço `gerador`.
// - blocos: criar pela tela (AI Studio › Vídeos › Novo vídeo) com um avatar que tem voz padrão (a
//   voz vem pré-escolhida), o produto em revisão fica de fora (contador), e voltar ao bloco 2 e
//   trocar o perfil não desmarca nada (só avisa que o guia muda);
// - chat: as 3 perguntas do Claude falso respondidas só com cliques, "Montar o vídeo" e o resumo
//   do plano com a soma igual à duração escolhida;
// - wizard: do chat ao conteúdo, tudo em 1 versão, recusando 1 quadro;
// - modal de cenas (T043): o reuso sem custo proposto (uma cena do vídeo pronto do wizard), a troca
//   por "criar nova" e por uma cena de outro avatar da biblioteca (só pelo plano);
// - avançado (T054, SC-007): trocar de modo no meio, pedir 2 opções de um quadro e voltar ao wizard
//   com as aprovações de antes.

type Auth = { Authorization: string };
type Base = { auth: Auth; perfilA: string; perfilB: string; nomeA: string; nomeB: string; avatarId: string; cenarioId: string; produtoId: string; vozId: string; sfx: number };

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

async function json<T>(r: { status(): number; text(): Promise<string>; json(): Promise<unknown> }, status: number): Promise<T> {
  expect(r.status(), await r.text()).toBe(status);
  return (await r.json()) as T;
}

async function ate<T>(ler: () => Promise<T>, ok: (v: T) => boolean, timeout = 90_000): Promise<T> {
  let atual = await ler();
  await expect.poll(async () => ok((atual = await ler())), { timeout, intervals: [500, 1000] }).toBe(true);
  return atual;
}

// WAV mono 24 kHz, 16 bits (a gravação da voz).
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

// Um produto (012) com a ficha do Claude falso e o recorte; `aprovar` decide se sai de revisão.
async function produto(request: APIRequestContext, auth: Auth, perfilId: string, aprovar: boolean): Promise<string> {
  const r = await request.post(`/api/perfis/${perfilId}/produtos`, {
    headers: auth,
    multipart: { name: `shorts_canelado ${aprovar ? "ok" : "revisao"}`, obs: "sem flat", fotos: { name: "foto1.png", mimeType: "image/png", buffer: pngBuffer(800, 900) } },
  });
  const { id } = await json<{ id: string }>(r, 201);
  const ler = async () => json<{ status: string; version: number }>(await request.get(`/api/produtos/${id}`, { headers: auth }), 200);
  const p = await ate(ler, (x) => x.status === "revisao");
  if (aprovar) await json(await request.post(`/api/produtos/${id}/aprovar`, { headers: auth, data: { version: p.version } }), 200);
  return id;
}

async function escolherOpcao1(request: APIRequestContext, auth: Auth, geracaoId: string, alvoVersion: () => Promise<number>): Promise<void> {
  const lerG = async () =>
    json<{ status: string; version: number; candidatos: { id: string; numero: number }[] }>(await request.get(`/api/geracoes/${geracaoId}`, { headers: auth }), 200);
  const g = await ate(lerG, (x) => x.status === "revisao");
  await json(
    await request.post(`/api/geracoes/${geracaoId}/escolher`, {
      headers: auth,
      data: { candidatoId: g.candidatos.find((c) => c.numero === 1)?.id, version: g.version, alvoVersion: await alvoVersion() },
    }),
    200,
  );
}

// A voz (025) gravada, com consentimento, a referência escolhida e sincronizada no shop-tts.
async function vozAprovada(request: APIRequestContext, auth: Auth, perfilId: string, nome: string): Promise<string> {
  let v = await json<{ id: string; version: number }>(
    await request.post(`/api/perfis/${perfilId}/vozes`, { headers: auth, data: { name: nome, origem: "gravacao", tom: "vendas animada" } }),
    201,
  );
  const audio = await json<{ id: string }>(
    await request.post(`/api/perfis/${perfilId}/audios`, { headers: auth, multipart: { arquivo: { name: "gravacao.wav", mimeType: "audio/wav", buffer: wavBuffer() } } }),
    201,
  );
  v = await json(await request.patch(`/api/vozes/${v.id}`, { headers: auth, data: { version: v.version, gravacaoAudioId: audio.id } }), 200);
  v = await json(
    await request.put(`/api/vozes/${v.id}/consentimento`, { headers: auth, data: { version: v.version, nome: "Pessoa Teste", data: "2026-10-01", observacao: "termo assinado" } }),
    200,
  );
  const g = await json<{ id: string }>(
    await request.post(`/api/perfis/${perfilId}/geracoes`, { headers: auth, data: { alvoTipo: "voz", alvoId: v.id, passo: "voz.gravacao", instrucao: "" } }),
    201,
  );
  await escolherOpcao1(request, auth, g.id, async () => (await json<{ version: number }>(await request.get(`/api/vozes/${v.id}`, { headers: auth }), 200)).version);
  const lerV = async () => json<{ status: string; sincronizadaEm: string | null }>(await request.get(`/api/vozes/${v.id}`, { headers: auth }), 200);
  await ate(lerV, (x) => x.status === "aprovada" && x.sincronizadaEm !== null);
  return v.id;
}

type AssetOut = { asset: { id: string; version: number; kitStatus: string | null } };
const lerAsset = async (request: APIRequestContext, auth: Auth, id: string) => json<AssetOut>(await request.get(`/api/assets/${id}`, { headers: auth }), 200);

// O avatar (sem kit) com a voz padrão.
async function avatarComVoz(request: APIRequestContext, auth: Auth, perfilId: string, nome: string, vozId: string): Promise<string> {
  const a = await json<AssetOut>(await request.post(`/api/perfis/${perfilId}/assets`, { headers: auth, data: { tipo: "avatar", name: nome, tags: [], prompt: "adult woman" } }), 201);
  await json(await request.patch(`/api/assets/${a.asset.id}`, { headers: auth, data: { version: a.asset.version, vozId } }), 200);
  return a.asset.id;
}

// O cenário com a imagem da cena (o slot `cena` do cadastro padronizado, pelo ComfyUI falso).
async function cenarioComCena(request: APIRequestContext, auth: Auth, perfilId: string, nome: string): Promise<string> {
  const c = await json<AssetOut>(await request.post(`/api/perfis/${perfilId}/assets`, { headers: auth, data: { tipo: "cenario", name: nome, tags: [], prompt: "bright bedroom" } }), 201);
  const g = await json<{ id: string }>(
    await request.post(`/api/perfis/${perfilId}/geracoes`, { headers: auth, data: { alvoTipo: "asset", alvoId: c.asset.id, passo: "cenario.cena", instrucao: "bright bedroom, morning sun" } }),
    201,
  );
  await escolherOpcao1(request, auth, g.id, async () => (await lerAsset(request, auth, c.asset.id)).asset.version);
  await ate(() => lerAsset(request, auth, c.asset.id), (x) => x.asset.kitStatus !== null, 30_000);
  return c.asset.id;
}

let base: Base | null = null;
// O vídeo pronto do teste do wizard: as cenas dele (mesmo avatar, cenário e produto, com os quadros
// e os clipes aprovados) são as candidatas a reuso total do teste do modal de cenas.
let prontoId: string | null = null;

async function preparar(request: APIRequestContext): Promise<Base> {
  if (base) return base;
  geracaoFake("POST", "/geracao-e2e/gpu", { ocupada: false });
  geracaoFake("POST", "/geracao-e2e/lento", { segundos: 1 });
  const sfx = Date.now();
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const nomeA = `Guiado A ${sfx}`;
  const nomeB = `Guiado B ${sfx}`;
  const perfilA = await createPerfilViaApi(request, token, { name: nomeA, slug: `guiado-a-${sfx}` });
  const perfilB = await createPerfilViaApi(request, token, { name: nomeB, slug: `guiado-b-${sfx}` });
  const produtoId = await produto(request, auth, perfilA, true);
  await produto(request, auth, perfilA, false); // fica em revisão: fora do bloco 5
  const vozId = await vozAprovada(request, auth, perfilA, `Voz guiada ${sfx}`);
  const avatarId = await avatarComVoz(request, auth, perfilA, `Avatar guiado ${sfx}`, vozId);
  const cenarioId = await cenarioComCena(request, auth, perfilA, `Quarto guiado ${sfx}`);
  base = { auth, perfilA, perfilB, nomeA, nomeB, avatarId, cenarioId, produtoId, vozId, sfx };
  return base;
}

const bloco = (page: Page, n: number) => page.getByTestId(`bloco-${n}`);
const radio = (page: Page, n: number, nome: string | RegExp) => bloco(page, n).getByRole("radio", { name: nome });

async function continuar(page: Page, de: number): Promise<void> {
  await bloco(page, de).getByRole("button", { name: "Continuar" }).click();
  await expect(de < 6 ? bloco(page, de + 1) : page.getByTestId("bloco-resumo")).toBeVisible();
}

test("blocos: cria pela tela com a voz pré-escolhida, o produto em revisão fora e a troca de perfil", async ({ page, request }) => {
  test.setTimeout(240_000);
  const b = await preparar(request);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await nav(page, "Vídeos");
  await page.getByRole("link", { name: "Novo vídeo" }).first().click();
  await expect(page).toHaveURL(/\/app\/estudio\/videos\/novo/);

  // 1. Tipo de vídeo: só "Avatar & POV"; os outros "em breve".
  await expect(radio(page, 1, /^Avatar & POV/)).toHaveAttribute("aria-checked", "true");
  await expect(radio(page, 1, /^Só produto/)).toBeDisabled();
  await continuar(page, 1);

  // 2. Perfil.
  await radio(page, 2, b.nomeA).click();
  await continuar(page, 2);

  // 3. Avatar e voz: a voz padrão do avatar vem marcada.
  await radio(page, 3, new RegExp(`^Avatar guiado ${b.sfx}`)).click();
  const voz = radio(page, 3, new RegExp(`^Voz guiada ${b.sfx}`));
  await expect(voz).toHaveAttribute("aria-checked", "true", { timeout: 15_000 });
  await expect(voz).toHaveAccessibleName(/Voz padrão do avatar/);
  await continuar(page, 3);

  // 4. Cenário.
  await radio(page, 4, new RegExp(`^Quarto guiado ${b.sfx}`)).click();
  await continuar(page, 4);

  // 5. Produto: só os aprovados; os outros contam no "N fora".
  const ativos = await json<{ itens: { status: string }[] }>(await request.get("/api/produtos?arquivados=false&limit=100", { headers: b.auth }), 200);
  const aprovados = ativos.itens.filter((p) => p.status === "aprovado").length;
  await expect(bloco(page, 5).getByRole("radio")).toHaveCount(aprovados);
  await expect(bloco(page, 5).getByTestId("bloco-fora")).toHaveText(`${ativos.itens.length - aprovados} fora (${ativos.itens.length - aprovados === 1 ? "não aprovado" : "não aprovados"})`);
  await radio(page, 5, new RegExp(b.nomeA)).click();
  await expect(radio(page, 5, new RegExp(b.nomeA))).toHaveAttribute("aria-checked", "true");

  // Volta ao bloco 2 e troca o perfil: nada é desmarcado, e a tela avisa.
  await page.getByRole("navigation", { name: "Blocos do novo vídeo" }).getByRole("button", { name: /^2\. Perfil/ }).click();
  await radio(page, 2, b.nomeB).click();
  await expect(page.getByTestId("aviso-perfil")).toContainText(b.nomeB);
  await continuar(page, 2);
  await expect(radio(page, 3, new RegExp(`^Avatar guiado ${b.sfx}`))).toHaveAttribute("aria-checked", "true");
  await expect(radio(page, 3, new RegExp(`^Voz guiada ${b.sfx}`))).toHaveAttribute("aria-checked", "true");
  await continuar(page, 3);
  await expect(radio(page, 4, new RegExp(`^Quarto guiado ${b.sfx}`))).toHaveAttribute("aria-checked", "true");
  await continuar(page, 4);
  await expect(radio(page, 5, new RegExp(b.nomeA))).toHaveAttribute("aria-checked", "true");
  await continuar(page, 5);

  // 6. Duração, na grade.
  await radio(page, 6, /^10 s/).click();
  await continuar(page, 6);

  // Resumo das 6 escolhas e criar: o roteiro abre com o chat.
  const resumo = page.getByTestId("resumo-escolhas");
  await expect(resumo.getByTestId("resumo-1")).toContainText("Avatar & POV");
  await expect(resumo.getByTestId("resumo-2")).toContainText(b.nomeB);
  await expect(resumo.getByTestId("resumo-3")).toContainText(`Avatar guiado ${b.sfx} · voz Voz guiada ${b.sfx}`);
  await expect(resumo.getByTestId("resumo-4")).toContainText(`Quarto guiado ${b.sfx}`);
  await expect(resumo.getByTestId("resumo-5")).toContainText("Short canelado");
  await expect(resumo.getByTestId("resumo-6")).toContainText("10 s");
  await page.getByRole("button", { name: "Criar vídeo" }).click();
  await expect(page).toHaveURL(/\/app\/roteiros\/[0-9a-f-]+$/, { timeout: 15_000 });
  await expect(page.getByTestId("conversa")).toBeVisible();
  await expect(page.getByTestId("roteiro-pecas")).toContainText(`Voz guiada ${b.sfx}`);

  const id = page.url().split("/").at(-1) as string;
  const r = await json<{ tipoVideo: string; perfilId: string; duracaoAlvoS: number; cenarioId: string }>(await request.get(`/api/roteiros/${id}`, { headers: b.auth }), 200);
  expect(r).toMatchObject({ tipoVideo: "avatar_pov", perfilId: b.perfilB, duracaoAlvoS: 10, cenarioId: b.cenarioId });
});

test("chat: responde só com cliques, monta o vídeo e a soma fecha na duração", async ({ page, request }) => {
  test.setTimeout(240_000);
  const b = await preparar(request);
  const criado = await json<{ id: string }>(
    await request.post("/api/roteiros", {
      headers: b.auth,
      data: { perfilId: b.perfilA, tipoVideo: "avatar_pov", avatarId: b.avatarId, cenarioId: b.cenarioId, produtoId: b.produtoId, duracaoS: 10 },
    }),
    201,
  );
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/roteiros/${criado.id}`);

  // As 3 perguntas do Claude falso, uma por vez, respondidas só com cliques.
  const conversa = page.getByTestId("conversa");
  const pergunta = conversa.getByTestId("pergunta-atual");
  for (const n of [1, 2, 3]) {
    await expect(pergunta.locator("legend")).toContainText(`Pergunta ${n} de 3`, { timeout: 60_000 });
    const opcao = pergunta.getByRole("group", { name: "Opções" }).getByRole("button").first();
    await opcao.click();
    await expect(opcao).toHaveAttribute("aria-pressed", "true");
    await pergunta.getByRole("button", { name: "Responder" }).click();
    await expect(conversa.getByTestId("chat-resposta")).toHaveCount(n);
  }
  await expect(pergunta).toHaveCount(0);

  // Montar o vídeo: o plano chega e a soma das cenas é a duração escolhida.
  await conversa.getByRole("button", { name: "Montar o vídeo" }).click();
  const plano = conversa.getByTestId("plano-resumo");
  await expect(plano).toBeVisible({ timeout: 90_000 });
  await expect(plano.getByTestId("plano-soma")).toHaveText("Total: 10 s de 10 s");
  const r = await json<{ posicoes: { trechos: number | null }[]; trechoBaseS: number }>(await request.get(`/api/roteiros/${criado.id}`, { headers: b.auth }), 200);
  expect(r.posicoes.reduce((s, p) => s + (p.trechos ?? 0) * r.trechoBaseS, 0)).toBe(10);
});

// T038 (US3, SC-002): o wizard do chat ao final, com tudo em 1 versão. Nenhuma tela mostra texto de
// prompt nem frase de fala; recusar o 1º quadro de uma cena refaz só aquele e os seguintes da cena.
type QuadroApi = { ordem: number; imageId: string | null; instrucao: string };
type RoteiroApi = {
  status: string;
  version: number;
  frases: string[];
  conteudoId: string | null;
  posicoes: { ordem: number; quadros: QuadroApi[] | null; cena: { keyframeInstrucao: string | null } }[];
};

async function semTextoInterno(page: Page, request: APIRequestContext, auth: Auth, id: string, tela: string): Promise<void> {
  const r = await json<RoteiroApi>(await request.get(`/api/roteiros/${id}`, { headers: auth }), 200);
  const proibidos = [...r.frases, ...r.posicoes.flatMap((p) => [...(p.quadros ?? []).map((q) => q.instrucao), p.cena.keyframeInstrucao ?? ""])]
    .map((s) => s.trim())
    .filter((s) => s.length >= 8);
  expect(proibidos.length, "o roteiro tem frases e instruções para conferir").toBeGreaterThan(0);
  const texto = await page.locator("body").innerText();
  for (const s of proibidos) expect(texto, `${tela}: a tela não pode mostrar "${s}"`).not.toContain(s);
}

test("wizard: aprova a narração, recusa 1 quadro e conclui com o conteúdo sem destino", async ({ page, request }) => {
  test.setTimeout(600_000);
  const b = await preparar(request);
  const criado = await json<{ id: string }>(
    await request.post("/api/roteiros", {
      headers: b.auth,
      data: { perfilId: b.perfilA, tipoVideo: "avatar_pov", avatarId: b.avatarId, cenarioId: b.cenarioId, produtoId: b.produtoId, duracaoS: 10 },
    }),
    201,
  );
  const id = criado.id;
  const lerR = async () => json<RoteiroApi>(await request.get(`/api/roteiros/${id}`, { headers: b.auth }), 200);
  const status = page.getByTestId("roteiro-status");
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/roteiros/${id}`);
  const wizard = page.getByTestId("wizard");
  await expect(wizard.getByTestId("passo-texto")).toHaveAttribute("aria-current", "step");

  // Conversa: só cliques (a 1ª resposta pede cenas novas, para a cadeia de quadros ser gerada aqui).
  const conversa = page.getByTestId("conversa");
  const pergunta = conversa.getByTestId("pergunta-atual");
  for (const n of [1, 2, 3]) {
    await expect(pergunta.locator("legend")).toContainText(`Pergunta ${n} de 3`, { timeout: 60_000 });
    await pergunta.getByRole("group", { name: "Opções" }).getByRole("button").first().click();
    if (n === 1) await pergunta.getByLabel("Resposta curta (opcional)").fill("cenas novas");
    await pergunta.getByRole("button", { name: "Responder" }).click();
    await expect(conversa.getByTestId("chat-resposta")).toHaveCount(n);
  }
  await conversa.getByRole("button", { name: "Montar o vídeo" }).click();
  await expect(conversa.getByTestId("plano-resumo")).toBeVisible({ timeout: 90_000 });
  await expect(status).toHaveText("Aguardando o texto", { timeout: 60_000 });
  await semTextoInterno(page, request, b.auth, id, "conversa");
  await page.getByTestId("aprovar-texto").getByRole("button", { name: "Confirmar cenas" }).click();

  // Narração: só o áudio; aprovar.
  await expect(status).toHaveText("Aguardando a narração", { timeout: 120_000 });
  await expect(wizard.getByTestId("passo-narracao")).toHaveAttribute("aria-current", "step");
  const narracao = wizard.getByTestId("wizard-narracao");
  await expect(narracao.getByTestId("player-narracao")).toBeVisible();
  await semTextoInterno(page, request, b.auth, id, "narração");
  await narracao.getByRole("button", { name: "Aprovar narração" }).click();

  // Quadros: as 2 cenas novas, 2 quadros cada, todos gerados.
  const quadros = wizard.getByTestId("wizard-quadros");
  await expect(quadros).toBeVisible({ timeout: 120_000 });
  const completos = (r: RoteiroApi) => r.posicoes.length === 2 && r.posicoes.every((p) => (p.quadros ?? []).length >= 2 && (p.quadros ?? []).every((q) => q.imageId));
  const antes = await ate(lerR, completos, 180_000);
  const cena1 = quadros.getByTestId("quadros-cena-1");
  await expect(cena1.getByRole("img")).toHaveCount(antes.posicoes[0]?.quadros?.length ?? 2, { timeout: 30_000 });
  await semTextoInterno(page, request, b.auth, id, "quadros");
  const ids = (r: RoteiroApi, ordem: number) => (r.posicoes[ordem]?.quadros ?? []).map((q) => q.imageId);
  const antes1 = ids(antes, 0);
  const antes2 = ids(antes, 1);

  // Recusa o quadro de início da cena 1 com uma troca pronta: ele e os seguintes da cena voltam; a cena 2 fica.
  await cena1.getByRole("button", { name: "Não aprovo o quadro Início da cena 1" }).click();
  const naoAprovo = cena1.getByTestId("nao-aprovo");
  const troca = naoAprovo.getByRole("group", { name: "Trocas prontas" }).getByRole("button", { name: "mais de lado" });
  await troca.click();
  await expect(troca).toHaveAttribute("aria-pressed", "true");
  await naoAprovo.getByRole("button", { name: "Pedir a troca" }).click();
  await expect(naoAprovo.getByTestId("nao-aprovo-pedido_troca")).toContainText("mais de lado", { timeout: 15_000 });
  const depois = await ate(lerR, (r) => completos(r) && ids(r, 0).every((x, i) => x !== antes1[i]), 180_000);
  expect(ids(depois, 1)).toEqual(antes2);
  await expect(cena1.getByTestId("quadro-0")).toHaveAttribute("data-image-id", String(ids(depois, 0)[0]), { timeout: 15_000 });
  await expect(naoAprovo.getByTestId("ajuste-feito")).toBeVisible();
  await semTextoInterno(page, request, b.auth, id, "quadros refeitos");

  for (const n of [1, 2]) {
    const cena = quadros.getByTestId(`quadros-cena-${n}`);
    const aprovar = cena.getByRole("button", { name: `Aprovar a sequência da cena ${n}` });
    await expect(aprovar).toBeEnabled({ timeout: 60_000 });
    await aprovar.click();
    // a última aprovação passa o portão, e o wizard vai para os clipes
    if (n === 1) await expect(cena.getByTestId("sequencia-aprovada")).toBeVisible({ timeout: 15_000 });
  }

  // Clipes: um player por trecho; aprovar as 2 cenas.
  await expect(status).toHaveText("Aguardando os clipes", { timeout: 240_000 });
  const clipes = wizard.getByTestId("wizard-clipes");
  for (const n of [1, 2]) await expect(clipes.getByTestId(`clipes-cena-${n}`).getByTestId(`player-trecho-${n}-0`)).toBeVisible({ timeout: 30_000 });
  await semTextoInterno(page, request, b.auth, id, "clipes");
  for (const n of [1, 2]) {
    const cena = clipes.getByTestId(`clipes-cena-${n}`);
    const aprovar = cena.getByRole("button", { name: `Aprovar os clipes da cena ${n}` });
    await expect(aprovar).toBeEnabled({ timeout: 30_000 });
    await aprovar.click();
    if (n === 1) await expect(cena.getByTestId("clipes-aprovados")).toBeVisible({ timeout: 15_000 });
  }

  // Final: a prévia; aprovar faz o acabamento e entrega o conteúdo sem destino.
  await expect(status).toHaveText("Aguardando o final", { timeout: 180_000 });
  const final = wizard.getByTestId("wizard-final");
  await expect(final.getByTestId("player-previa")).toBeVisible();
  await semTextoInterno(page, request, b.auth, id, "final");
  await final.getByRole("button", { name: "Aprovar o vídeo" }).click();
  await expect(status).toHaveText("Pronto", { timeout: 240_000 });
  await expect(final.getByTestId("player-hd")).toBeVisible();
  await semTextoInterno(page, request, b.auth, id, "pronto");

  const pronto = await lerR();
  expect(pronto.conteudoId).not.toBeNull();
  prontoId = id;
  const conteudo = await json<{ conteudo: { geradoIa: boolean; destinos: unknown[] } }>(await request.get(`/api/conteudos/${pronto.conteudoId}`, { headers: b.auth }), 200);
  expect(conteudo.conteudo.geradoIa).toBe(true);
  expect(conteudo.conteudo.destinos).toHaveLength(0);
  await final.getByTestId("roteiro-pronto").getByRole("link", { name: "Abrir o conteúdo" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/conteudos/${pronto.conteudoId}$`), { timeout: 15_000 });
  await expect(page.getByTestId("selo-gerado-ia")).toHaveText(/Gerado por IA/);
});

// O chat respondido só com cliques e "Montar o vídeo" (com "cenas novas", a IA não reaproveita nada).
async function conversarEMontar(page: Page, cenasNovas: boolean): Promise<void> {
  const conversa = page.getByTestId("conversa");
  const pergunta = conversa.getByTestId("pergunta-atual");
  for (const n of [1, 2, 3]) {
    await expect(pergunta.locator("legend")).toContainText(`Pergunta ${n} de 3`, { timeout: 60_000 });
    await pergunta.getByRole("group", { name: "Opções" }).getByRole("button").first().click();
    if (n === 1 && cenasNovas) await pergunta.getByLabel("Resposta curta (opcional)").fill("cenas novas");
    await pergunta.getByRole("button", { name: "Responder" }).click();
    await expect(conversa.getByTestId("chat-resposta")).toHaveCount(n);
  }
  await conversa.getByRole("button", { name: "Montar o vídeo" }).click();
  await expect(conversa.getByTestId("plano-resumo")).toBeVisible({ timeout: 90_000 });
}

async function criarGuiado(request: APIRequestContext, b: Base): Promise<string> {
  const criado = await json<{ id: string }>(
    await request.post("/api/roteiros", {
      headers: b.auth,
      data: { perfilId: b.perfilA, tipoVideo: "avatar_pov", avatarId: b.avatarId, cenarioId: b.cenarioId, produtoId: b.produtoId, duracaoS: 10 },
    }),
    201,
  );
  return criado.id;
}

type PosicaoApi = { ordem: number; reuso: string | null; motivo: string | null; aprovadoKeyframesEm: string | null; cena: { id: string }; quadros: QuadroApi[] | null };

test("modal de cenas: propõe o reuso sem custo e troca por nova e pela biblioteca", async ({ page, request }) => {
  test.setTimeout(420_000);
  const b = await preparar(request);
  expect(prontoId, "o teste do wizard deixa um vídeo pronto (cenas para o reuso total)").not.toBeNull();
  const pronto = await json<{ posicoes: PosicaoApi[] }>(await request.get(`/api/roteiros/${prontoId}`, { headers: b.auth }), 200);
  const cenasDoPronto = pronto.posicoes.map((p) => p.cena.id);

  // A cena de outro avatar (010), no perfil B: não é proposta, mas aparece na biblioteca, só pelo plano.
  const outro = await json<AssetOut>(
    await request.post(`/api/perfis/${b.perfilB}/assets`, { headers: b.auth, data: { tipo: "avatar", name: `Outro avatar ${b.sfx}`, tags: [], prompt: "adult man" } }),
    201,
  );
  const nomeOutra = `Cena outro avatar ${b.sfx}`;
  const outra = await json<{ id: string }>(
    await request.post(`/api/perfis/${b.perfilB}/cenas`, { headers: b.auth, data: { nome: nomeOutra, acao: "He shows the shorts to the camera", avatarId: outro.asset.id } }),
    201,
  );

  const id = await criarGuiado(request, b);
  const lerR = async () => json<{ status: string; posicoes: PosicaoApi[] }>(await request.get(`/api/roteiros/${id}`, { headers: b.auth }), 200);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/roteiros/${id}`);
  await conversarEMontar(page, false);
  await expect(page.getByTestId("roteiro-status")).toHaveText("Aguardando o texto", { timeout: 60_000 });

  // As propostas: a 1ª posição reaproveita uma cena do vídeo pronto como está; a 2ª é nova.
  const modal = page.getByTestId("modal-cenas");
  const cena1 = modal.getByTestId("modal-cena-1");
  const cena2 = modal.getByTestId("modal-cena-2");
  await expect(cena1).toHaveAttribute("data-reuso", "total");
  await expect(cena1.getByTestId("nivel")).toHaveText("Sem custo");
  await expect(cena1.getByTestId("motivo")).toContainText("Esta cena da biblioteca serve.");
  await expect(cena1.getByTestId("usos")).toContainText("Já usada em");
  await expect(cena2).toHaveAttribute("data-reuso", "nova");
  await expect(cena2.getByTestId("nivel")).toHaveText("Criar nova");
  await expect(cena2.getByTestId("motivo")).toContainText("Nenhuma cena serve.");
  const antes = await lerR();
  expect(cenasDoPronto).toContain(antes.posicoes[0]?.cena.id);
  expect(antes.posicoes.map((p) => p.cena.id)).not.toContain(outra.id);

  // A 1ª posição troca por "criar nova": a IA cria a cena, e o modal mostra o novo nível.
  await cena1.getByRole("button", { name: "Criar nova" }).click();
  await expect(cena1).toHaveAttribute("data-reuso", "nova", { timeout: 90_000 });
  await expect(cena1.getByRole("button", { name: "Criar nova" })).toHaveCount(0);

  // A 2ª posição troca pela cena de outro avatar: sem o "sem custo", só pelo plano (refaz as imagens).
  await expect(cena2.getByRole("button", { name: "Escolher da biblioteca" })).toBeEnabled({ timeout: 30_000 });
  await cena2.getByRole("button", { name: "Escolher da biblioteca" }).click();
  const biblioteca = page.getByTestId("biblioteca-cena-2");
  await biblioteca.getByRole("searchbox", { name: "Buscar cena pelo nome" }).fill(nomeOutra);
  const opcao = biblioteca.getByTestId("opcao-cena").filter({ hasText: nomeOutra });
  await expect(opcao).toContainText("outro avatar");
  await expect(opcao.getByRole("button", { name: `Usar ${nomeOutra} sem custo` })).toHaveCount(0);
  await opcao.getByRole("button", { name: `Usar o plano de ${nomeOutra} (refaz as imagens)` }).click();
  await expect(biblioteca).toBeHidden();
  await expect(cena2).toHaveAttribute("data-reuso", "plano", { timeout: 30_000 });
  await expect(cena2.getByTestId("nivel")).toHaveText("Refaz as imagens");

  const depois = await lerR();
  expect(depois.posicoes.map((p) => p.reuso)).toEqual(["nova", "plano"]);
  // a cena reaproveitada não muda (FR-022): a 2ª posição ganhou uma derivada, não a cena original
  expect(depois.posicoes[1]?.cena.id).not.toBe(outra.id);

  // "Confirmar cenas" aprova o portão do texto.
  await modal.getByTestId("aprovar-texto").getByRole("button", { name: "Confirmar cenas" }).click();
  await ate(lerR, (r) => r.status !== "aguardando_texto", 30_000);
});

test("avançado: troca de modo no meio, pede 2 opções de um quadro e volta sem perder aprovações", async ({ page, request }) => {
  test.setTimeout(600_000);
  const b = await preparar(request);
  const id = await criarGuiado(request, b);
  const lerR = async () => json<{ status: string; posicoes: PosicaoApi[] }>(await request.get(`/api/roteiros/${id}`, { headers: b.auth }), 200);
  const status = page.getByTestId("roteiro-status");
  const modoTela = page.getByRole("radiogroup", { name: "Modo da tela" });
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/roteiros/${id}`);
  await expect(modoTela.getByRole("radio", { name: "Wizard" })).toHaveAttribute("aria-checked", "true");

  // No wizard: o plano com cenas novas, as cenas confirmadas, a narração aprovada e a sequência da cena 1.
  await conversarEMontar(page, true);
  await page.getByTestId("aprovar-texto").getByRole("button", { name: "Confirmar cenas" }).click();
  await expect(status).toHaveText("Aguardando a narração", { timeout: 120_000 });
  const wizard = page.getByTestId("wizard");
  await wizard.getByTestId("wizard-narracao").getByRole("button", { name: "Aprovar narração" }).click();
  const completos = (r: { posicoes: PosicaoApi[] }) => r.posicoes.length === 2 && r.posicoes.every((p) => (p.quadros ?? []).length >= 2 && (p.quadros ?? []).every((q) => q.imageId));
  await ate(lerR, completos, 180_000);
  const quadros = wizard.getByTestId("wizard-quadros");
  const aprovar1 = quadros.getByTestId("quadros-cena-1").getByRole("button", { name: "Aprovar a sequência da cena 1" });
  await expect(aprovar1).toBeEnabled({ timeout: 60_000 });
  await aprovar1.click();
  await expect(quadros.getByTestId("quadros-cena-1").getByTestId("sequencia-aprovada")).toBeVisible({ timeout: 15_000 });
  const aprovados = await lerR();
  const aprovadoEm = aprovados.posicoes[0]?.aprovadoKeyframesEm;
  expect(aprovadoEm).toBeTruthy();
  const quadro0Antes = aprovados.posicoes[1]?.quadros?.[0]?.imageId;

  // Avançado (lembrado ao recarregar): na etapa Keyframes, 2 opções do quadro de início da cena 2.
  await modoTela.getByRole("radio", { name: "Avançado" }).click();
  await expect(page.getByTestId("wizard")).toHaveCount(0);
  await page.reload();
  await expect(modoTela.getByRole("radio", { name: "Avançado" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("portoes")).toBeVisible();
  await page.getByTestId("aba-etapa-keyframes").click();
  const cena2 = page.getByTestId("keyframe-cena-2");
  await cena2.getByTestId("quadro-avancado-0").getByRole("button", { name: "Regerar daqui" }).click();
  const regerar = cena2.getByTestId("regerar-quadro-2-0");
  await regerar.getByLabel("Quantas opções").selectOption("2");
  await regerar.getByRole("button", { name: "Gerar 2 opções" }).click();
  await expect(cena2.getByTestId("opcao-2")).toBeVisible({ timeout: 90_000 });
  await cena2.getByTestId("opcao-1").getByRole("button", { name: "Usar opção 1" }).click();
  const dialogo = page.getByRole("alertdialog");
  await dialogo.getByRole("button", { name: "Usar opção 1" }).click();
  await expect(dialogo).toBeHidden();
  const refeito = await ate(lerR, (r) => {
    const q0 = r.posicoes[1]?.quadros?.[0]?.imageId;
    return q0 != null && q0 !== quadro0Antes;
  });

  // De volta ao wizard: a narração e a sequência da cena 1 continuam aprovadas (SC-007), e a cena 2 mostra o quadro novo.
  await modoTela.getByRole("radio", { name: "Wizard" }).click();
  await expect(wizard.getByTestId("passo-narracao")).toContainText("(feito)");
  await expect(wizard.getByTestId("quadros-cena-1").getByTestId("sequencia-aprovada")).toBeVisible();
  await expect(wizard.getByTestId("quadros-cena-2").getByTestId("quadro-0")).toHaveAttribute("data-image-id", String(refeito.posicoes[1]?.quadros?.[0]?.imageId), { timeout: 15_000 });
  const final = await lerR();
  expect(final.posicoes[0]?.aprovadoKeyframesEm).toBe(aprovadoEm);
});
