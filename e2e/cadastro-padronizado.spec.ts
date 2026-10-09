import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, compose, createPerfilViaApi, login, pngBuffer, preencherData, sqlE2e } from "./helpers";

// Spec 025 (T037, T048): cadastro padronizado com o ComfyUI, o shop-tts e o Claude falsos
// (`e2e/fakes/geracao_fake.py` e `server.py`, no `openshorts-fake`) e o serviço `gerador`.
// - US1: o kit do avatar pela tela, da descrição da pessoa até a checagem de identidade;
// - US2/US3: a voz de gravação com consentimento, candidatos, escolha, sincronização e teste; a
//   voz padrão do avatar; a revogação tira a voz do shop-tts;
// - pessoa real: consentimento, a foto no slot de origem e a revogação com a prévia;
// - US5: a cena do cenário e uma variação.

type Auth = { Authorization: string };

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

const vozesTts = () => geracaoFake("GET", "/geracao-e2e/vozes-tts") as { vozes: string[]; importadas: { nome: string }[]; apagadas: string[] };

// WAV mono 24 kHz, 16 bits, com um tom (o ffprobe da API aceita).
function wavBuffer(segundos = 3, freq = 440): Buffer {
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

async function preparar(request: APIRequestContext, sfx: string): Promise<{ auth: Auth; perfilId: string }> {
  geracaoFake("POST", "/geracao-e2e/gpu", { ocupada: false });
  geracaoFake("POST", "/geracao-e2e/lento", { segundos: 1 });
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Kit ${sfx}`, slug: `kit-${sfx}` });
  return { auth, perfilId };
}

async function criarAsset(request: APIRequestContext, auth: Auth, perfilId: string, data: Record<string, unknown>): Promise<string> {
  const r = await request.post(`/api/perfis/${perfilId}/assets`, { headers: auth, data: { tags: [], ...data } });
  expect(r.status(), `asset: ${await r.text()}`).toBe(201);
  return ((await r.json()) as { asset: { id: string } }).asset.id;
}

async function entrar(page: Page, caminho: string): Promise<void> {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(caminho);
}

async function confirmar(page: Page, botao: string, escopo: Locator): Promise<void> {
  await escopo.getByRole("button", { name: botao }).click();
  const dialogo = page.getByRole("alertdialog");
  await expect(dialogo).toBeVisible();
  await dialogo.getByRole("button", { name: botao }).click();
  await expect(dialogo).toBeHidden();
}

async function gerarEUsar(page: Page, passo: string, botao: string, opcao = 1, preencher?: (f: Locator) => Promise<void>): Promise<void> {
  const form = page.getByTestId(`pedir-${passo}`);
  await expect(form).toBeVisible({ timeout: 15_000 });
  if (preencher) await preencher(form);
  await form.getByRole("button", { name: botao }).click();
  const g = page.getByTestId(`geracao-${passo}`);
  await expect(g.getByTestId(`opcao-${opcao}`)).toBeVisible({ timeout: 60_000 });
  await confirmar(page, `Usar opção ${opcao}`, g.getByTestId(`opcao-${opcao}`));
}

test.describe.configure({ mode: "serial" });

test("US1: monta o kit do avatar pela tela até a checagem de identidade", async ({ page, request }) => {
  const { auth, perfilId } = await preparar(request, `us1-${Date.now()}`);
  const avatarId = await criarAsset(request, auth, perfilId, { tipo: "avatar", name: "Ana" });
  await entrar(page, `/app/assets/${avatarId}`);
  const kit = page.getByTestId("kit-padrao");
  await expect(kit.getByTestId("kit-status")).toHaveText(/Sem kit padrão|Incompleto/);
  await expect(page.getByTestId("slot-rosto_frontal").getByTestId("motivo-bloqueio")).toContainText("Escolha o rosto de origem antes");

  // Menoridade recusada antes de gerar.
  const origem = page.getByTestId("pedir-avatar.rosto_origem");
  await origem.getByLabel("Descrição da pessoa (inglês)").fill("a teen girl smiling");
  await origem.getByRole("button", { name: "Gerar 4 opções" }).click();
  await expect(origem.getByRole("alert")).toBeVisible();
  await expect(page.getByTestId("geracao-avatar.rosto_origem")).toHaveCount(0);

  await gerarEUsar(page, "avatar.rosto_origem", "Gerar 4 opções", 2, (f) =>
    f.getByLabel("Descrição da pessoa (inglês)").fill("an adult woman in her early thirties with dark curly hair"));
  await expect(page.getByTestId("slot-arquivo-rosto_origem")).toBeVisible({ timeout: 15_000 });
  await gerarEUsar(page, "avatar.rosto_frontal", "Gerar 2 opções");
  await expect(page.getByTestId("slot-arquivo-rosto_frontal")).toBeVisible({ timeout: 15_000 });
  await gerarEUsar(page, "avatar.rostos_34", "Gerar 2 opções");
  await expect(page.getByTestId("slot-arquivo-rosto_34_dir")).toBeVisible({ timeout: 15_000 });
  await gerarEUsar(page, "avatar.corpo_base", "Gerar 2 opções");

  // A checagem de identidade é pedida pelo servidor e roda na linha Claude.
  await expect(kit.getByTestId("kit-status")).toHaveText("Completo", { timeout: 60_000 });
  await expect(page.getByTestId("nota-corpo_base")).toContainText("Nota 8/10");
  await expect(page.getByTestId("kit-descricao")).toContainText("Adult woman in her early thirties");
  await expect(page.getByTestId("gerar-look").getByRole("button", { name: "Gerar look" })).toBeEnabled();

  // Nota abaixo de 7 no corpo-base → "Atenção" e "Refazer este passo".
  sqlE2e(`update assets set identidade = jsonb_set(identidade, '{notas,corpo_base,nota}', '6'), kit_status = 'atencao' where id = '${avatarId}'`);
  await page.reload();
  await expect(kit.getByTestId("kit-status")).toHaveText("Atenção");
  await expect(page.getByTestId("slot-corpo_base").getByRole("button", { name: "Refazer este passo" })).toBeVisible();
});

test("US2/US3: voz de gravação com consentimento, escolha, teste, voz padrão e revogação", async ({ page, request }) => {
  const { auth, perfilId } = await preparar(request, `voz-${Date.now()}`);
  const avatarId = await criarAsset(request, auth, perfilId, { tipo: "avatar", name: "Bia" });
  // spec 029: AI Studio › Vozes, filtrada pelo perfil; a voz nasce com ele como perfil base
  await entrar(page, `/app/estudio/vozes?perfil=${perfilId}`);
  await expect(page.getByRole("heading", { level: 1, name: "Vozes" })).toBeVisible();
  await page.getByRole("button", { name: "Nova voz" }).first().click();
  const novo = page.getByRole("dialog", { name: "Nova voz" });
  await expect(novo.getByTestId("perfil-base")).toHaveValue(perfilId);
  await novo.getByLabel("Nome da voz").fill("Bia vendas");
  await novo.getByLabel("Tom").fill("vendas animada");
  await novo.getByRole("button", { name: "Criar voz" }).click();
  await expect(page).toHaveURL(/\/app\/vozes\/[0-9a-f-]+$/);
  const vozId = page.url().split("/").at(-1) as string;

  await expect(page.getByTestId("voz-gravacao")).toContainText("Falta o consentimento");
  const cons = page.getByTestId("consentimento-form");
  await cons.getByLabel("Nome da pessoa").fill("Bia Souza");
  await preencherData(cons.getByLabel("Data do consentimento"), "2026-10-01");
  await cons.getByRole("button", { name: "Registrar consentimento" }).click();
  await expect(page.getByTestId("consentimento-registrado")).toBeVisible();

  const grav = page.getByTestId("voz-gravacao");
  await grav.getByLabel("Arquivo da gravação").setInputFiles({ name: "gravacao.wav", mimeType: "audio/wav", buffer: wavBuffer() });
  await grav.getByRole("button", { name: "Enviar gravação" }).click();
  await expect(grav.getByText("Gravação atual")).toBeVisible({ timeout: 15_000 });
  await grav.getByRole("button", { name: "Gerar candidatos" }).click();
  const cands = page.getByTestId("geracao-voz.gravacao");
  await expect(cands.getByTestId("opcao-2")).toBeVisible({ timeout: 60_000 });
  await expect(cands.getByTestId("metricas-opcao-2")).toContainText("Oi, gente!");
  await expect(page.getByTestId("voz-analise")).toBeVisible();
  await confirmar(page, "Usar opção 2", cands.getByTestId("opcao-2"));
  await expect(page.getByTestId("voz-status")).toHaveText("Aprovada", { timeout: 15_000 });
  await expect(page.getByTestId("voz-sincronizacao")).toContainText("Sincronizada", { timeout: 30_000 });

  const det = (await (await request.get(`/api/vozes/${vozId}`, { headers: auth })).json()) as { ttsId: string };
  expect(vozesTts().importadas.map((i) => i.nome)).toContain(det.ttsId);

  const teste = page.getByTestId("voz-teste");
  await teste.getByLabel("Texto do teste").fill("Olha que achadinho!");
  await teste.getByRole("button", { name: "Testar" }).click();
  await expect(page.getByTestId("geracao-voz.teste").getByTestId("opcao-1")).toBeVisible({ timeout: 60_000 });

  // Voz padrão do avatar.
  await page.goto(`/app/assets/${avatarId}`);
  // (spec 029: as opções são "Nome · Perfil", das vozes aprovadas da agência inteira)
  await page.getByRole("combobox", { name: "Voz padrão" }).selectOption(vozId);
  await expect(page.getByText("Voz padrão salva.")).toBeVisible();
  await page.goto(`/app/vozes/${vozId}`);
  await expect(page.getByTestId("voz-usada-por")).toContainText("Bia");

  // Revogar: a voz sai do shop-tts.
  await page.getByTestId("consentimento-card").getByRole("button", { name: "Revogar consentimento" }).click();
  const dlg = page.getByRole("alertdialog");
  await dlg.getByLabel("Entendi o que será apagado").click();
  await dlg.getByRole("button", { name: "Revogar" }).click();
  await expect(page.getByTestId("voz-revogada")).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => vozesTts().apagadas, { timeout: 30_000 }).toContain(det.ttsId);
});

test("Pessoa real: consentimento, foto no slot de origem e revogação com a prévia", async ({ page, request }) => {
  const { auth, perfilId } = await preparar(request, `real-${Date.now()}`);
  const avatarId = await criarAsset(request, auth, perfilId, { tipo: "avatar", name: "Carla" });
  await entrar(page, `/app/assets/${avatarId}`);
  const slot = page.getByTestId("slot-rosto_origem");
  const enviar = page.getByTestId("enviar-rosto_origem");
  const foto = { name: "carla.png", mimeType: "image/png", buffer: pngBuffer(800, 900) };
  // Sem consentimento, a foto de pessoa real é recusada.
  await slot.getByRole("button", { name: "Enviar no slot" }).click();
  await enviar.getByLabel("Origem da foto").selectOption({ label: "Pessoa real" });
  await enviar.getByLabel("Imagem para rosto de origem").setInputFiles(foto);
  await enviar.getByRole("button", { name: "Enviar imagem" }).click();
  await expect(enviar.getByRole("alert")).toContainText(/consentimento/i);

  const cons = page.getByTestId("consentimento-form");
  await expect(cons).toContainText("Antes de usar a foto de uma pessoa real");
  await cons.getByLabel("Nome da pessoa").fill("Carla Lima");
  await preencherData(cons.getByLabel("Data do consentimento"), "2026-10-01");
  await cons.getByRole("button", { name: "Registrar consentimento" }).click();
  await expect(page.getByTestId("consentimento-registrado")).toBeVisible();

  if (!(await enviar.isVisible())) await slot.getByRole("button", { name: "Enviar no slot" }).click();
  await enviar.getByLabel("Origem da foto").selectOption({ label: "Pessoa real" });
  await enviar.getByLabel("Imagem para rosto de origem").setInputFiles(foto);
  await enviar.getByRole("button", { name: "Enviar imagem" }).click();
  await expect(page.getByTestId("slot-arquivo-rosto_origem")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("slot-rosto_frontal").getByRole("button", { name: "Gerar 2 opções" })).toBeVisible();

  await page.getByTestId("consentimento-card").getByRole("button", { name: "Revogar consentimento" }).click();
  const dlg = page.getByRole("alertdialog", { name: "Revogar o consentimento?" });
  await expect(dlg.getByTestId("previa-revogacao")).toContainText(/imag/i);
  await dlg.getByLabel("Entendi o que será apagado").click();
  await dlg.getByRole("button", { name: "Revogar" }).click();
  await expect(page.getByTestId("asset-revogado")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Restaurar" })).toBeDisabled();

  const r = await request.get(`/api/assets/${avatarId}`, { headers: auth });
  const asset = ((await r.json()) as { asset: { files: unknown[]; revogado: boolean; archived: boolean } }).asset;
  expect(asset.revogado).toBe(true);
  expect(asset.archived).toBe(true);
  expect(asset.files).toHaveLength(0);
});

test("US5: a cena do cenário e uma variação", async ({ page, request }) => {
  const { auth, perfilId } = await preparar(request, `cen-${Date.now()}`);
  const cenarioId = await criarAsset(request, auth, perfilId, { tipo: "cenario", name: "Cozinha", prompt: "retro kitchen" });
  await entrar(page, `/app/assets/${cenarioId}`);
  const variacoes = page.getByTestId("cenario-variacoes");
  await expect(variacoes.getByTestId("motivo-bloqueio")).toContainText("escolha a cena antes");

  const form = page.getByTestId("pedir-geracao");
  await form.getByRole("button", { name: "Gerar" }).click();  // instrução vazia: usa o prompt do cenário
  const item = page.getByTestId("geracao-item").first();
  await expect(item.getByTestId("estado-geracao")).toHaveText("Em revisão", { timeout: 60_000 });
  await confirmar(page, "Usar opção 1", item.getByTestId("opcao-1"));
  await expect(page.getByTestId("cenario-cena").getByTestId("slot-arquivo-cena")).toBeVisible({ timeout: 15_000 });

  await variacoes.getByRole("button", { name: "Gerar variação" }).click();
  const fv = page.getByTestId("pedir-cenario.variacao");
  await fv.getByLabel("Rótulo da variação").fill("noite");
  await fv.getByLabel("O que muda (inglês)").fill("same kitchen at night, warm lamps");
  await fv.getByRole("button", { name: "Gerar variação" }).click();
  const v = page.getByTestId("geracao-item").first();
  await expect(v.getByTestId("estado-geracao")).toHaveText("Em revisão", { timeout: 60_000 });
  await confirmar(page, "Usar opção 1", v.getByTestId("opcao-1"));
  await expect(variacoes).toContainText("noite", { timeout: 15_000 });
});
