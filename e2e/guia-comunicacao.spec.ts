import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, login, logout, syntheticMp4 } from "./helpers";

// Spec 017 (T045): o guia de comunicação do perfil e da conta, com o Claude falso do
// `openshorts-fake` (e2e/fakes/server.py). O fake devolve textos de postagem SEM as hashtags fixas
// (quem inclui é o servidor), responde os formatos `guia` e `variacoes`, e "proibida" na instrução
// devolve a 1ª palavra de "Palavras proibidas:" do `system` nas duas tentativas.

const SHOTS = ".playwright-mcp/sociman";

type Auth = { Authorization: string };

interface GuiaCampos {
  tom: string;
  faca: string[];
  naoFaca: string[];
  vocabulario: string[];
  proibidas: string[];
  emojis: "nao" | "moderado" | "livre" | null;
  emojisPreferidos: string[];
  hashtagsFixas: string[];
  maxHashtagsFixas: number | null;
  exemplos: { tipo: "titulo" | "legenda" | "bordao"; texto: string }[];
}

interface Guia {
  id: string | null;
  version: number;
  campos: GuiaCampos;
}

interface Chamada {
  id: string;
  tipoCampo: string;
  desfecho: string;
  guiaPerfilVersion: number | null;
  guiaContaVersion: number | null;
  guiaRascunho: "perfil" | "conta" | null;
  proibidas: string[];
  proposta: { titulo?: string; descricao?: string; hashtags?: string[]; variacoes?: { hashtags: string[] }[] } | null;
}

interface Version {
  version: number;
  action: string;
  details: { ia?: { tipoCampo: string; desfecho: string }[]; from_version?: number };
  actor: { name: string } | null;
}

interface Destino {
  id: string;
  version: number;
  titulo: string;
  descricao: string;
  hashtags: string[];
}

const VAZIO: GuiaCampos = {
  tom: "",
  faca: [],
  naoFaca: [],
  vocabulario: [],
  proibidas: [],
  emojis: null,
  emojisPreferidos: [],
  hashtagsFixas: [],
  maxHashtagsFixas: null,
  exemplos: [],
};

// ---- API ----

async function getJson<T>(request: APIRequestContext, auth: Auth, url: string): Promise<T> {
  const res = await request.get(url, { headers: auth });
  expect(res.status(), `GET ${url}: ${res.status() === 200 ? "" : await res.text()}`).toBe(200);
  return (await res.json()) as T;
}

async function guiaPerfil(request: APIRequestContext, auth: Auth, perfilId: string): Promise<Guia> {
  return (await getJson<{ guia: Guia }>(request, auth, `/api/perfis/${perfilId}/guia`)).guia;
}

async function guiaConta(request: APIRequestContext, auth: Auth, contaId: string): Promise<Guia> {
  return (await getJson<{ guia: Guia }>(request, auth, `/api/contas/${contaId}/guia`)).guia;
}

// PUT do guia (perfil ou conta) sobre a versão atual; devolve a resposta crua.
async function putGuia(request: APIRequestContext, auth: Auth, url: string, campos: Partial<GuiaCampos>) {
  const atual = (await getJson<{ guia: Guia }>(request, auth, url)).guia;
  return request.put(url, { headers: auth, data: { version: atual.version, campos: { ...VAZIO, ...campos } } });
}

async function versions(request: APIRequestContext, auth: Auth, url: string): Promise<Version[]> {
  return (await getJson<{ items: Version[] }>(request, auth, url)).items;
}

async function chamadas(request: APIRequestContext, auth: Auth, query: Record<string, string>): Promise<Chamada[]> {
  const qs = new URLSearchParams({ limit: "100", ...query }).toString();
  return (await getJson<{ items: Chamada[] }>(request, auth, `/api/ia/chamadas?${qs}`)).items;
}

async function novaConta(request: APIRequestContext, auth: Auth, perfilId: string, platform: string, handle: string): Promise<string> {
  const res = await request.post(`/api/perfis/${perfilId}/contas`, { headers: auth, data: { platform, handle, status: "ativa" } });
  expect(res.status(), `POST contas: ${await res.text()}`).toBe(201);
  return ((await res.json()) as { conta: { id: string } }).conta.id;
}

// Vídeo próprio pela API (spec 014): 201 e já "pronto", sem esperar o worker.
async function videoProprio(request: APIRequestContext, auth: Auth, perfilId: string, arquivo: string, titulo: string): Promise<string> {
  syntheticMp4(arquivo, 3);
  const res = await request.post(`/api/perfis/${perfilId}/conteudos/arquivo`, {
    headers: auth,
    multipart: { file: { name: `${titulo}.mp4`, mimeType: "video/mp4", buffer: readFileSync(arquivo) }, titulo },
  });
  expect(res.status(), `POST conteudos/arquivo: ${await res.text()}`).toBe(201);
  return ((await res.json()) as { conteudo: { id: string } }).conteudo.id;
}

async function destinos(request: APIRequestContext, auth: Auth, conteudoId: string): Promise<Destino[]> {
  return (await getJson<{ conteudo: { destinos: Destino[] } }>(request, auth, `/api/conteudos/${conteudoId}`)).conteudo.destinos;
}

// Perfil novo com uma conta TikTok ativa.
async function perfilComConta(request: APIRequestContext, token: string, nome: string, sfx: string) {
  const auth = { Authorization: `Bearer ${token}` };
  const perfilName = `${nome} ${sfx}`;
  const perfilId = await createPerfilViaApi(request, token, {
    name: perfilName,
    slug: `${nome.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${sfx}`,
    niche: "achadinhos",
  });
  const handle = `${nome.toLowerCase().replace(/[^a-z0-9]+/g, "")}${sfx}`;
  const contaId = await novaConta(request, auth, perfilId, "tiktok", handle);
  return { auth, perfilId, perfilName, contaId, handle };
}

// ---- UI ----

function botaoIa(page: Page, tipo: string): Locator {
  return page.getByTestId(`ia-botao-${tipo}`);
}

function painelIa(page: Page, tipo: string): Locator {
  return page.getByTestId(`ia-painel-${tipo}`);
}

async function abrirPainel(page: Page, tipo: string, instrucao = ""): Promise<Locator> {
  await botaoIa(page, tipo).click();
  const painel = painelIa(page, tipo);
  await expect(painel).toBeVisible();
  if (instrucao) await painel.getByLabel("Como a IA deve ajudar?").fill(instrucao);
  return painel;
}

async function gerar(painel: Locator): Promise<void> {
  await painel.getByRole("button", { name: "Gerar", exact: true }).click();
  await expect(painel.getByText(/Claude falso do e2e/).last()).toBeVisible({ timeout: 25_000 });
}

// Listas do formulário do guia: "uma por linha".
function linhas(...itens: string[]): string {
  return itens.join("\n");
}

async function salvarGuia(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Salvar guia", exact: true }).click();
}

// Escolhe no <select> nativo a opção cuja legenda contém `texto`.
async function escolher(select: Locator, texto: string): Promise<void> {
  select = select.and(select.page().locator("select")).first();
  const opcao = select.locator("option").filter({ hasText: texto }).first();
  await expect(opcao).toBeAttached();
  await select.selectOption((await opcao.getAttribute("value"))!);
}

// ---------------------------------------------------------------------------------------------
// US1: o dono escreve o guia do perfil e o da conta (herdado visível, limites, soma das fixas,
// máximo por conta, conflito avisado), reverte; o membro só vê.
// ---------------------------------------------------------------------------------------------
test("US1: guia do perfil e da conta, limites, conflito, membro e reversão", async ({ page, request }) => {
  test.setTimeout(240_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const { auth, perfilId, contaId } = await perfilComConta(request, token, "Guia Taverna", sfx);
  const youtubeId = await novaConta(request, auth, perfilId, "youtube", `guiayt${sfx}`);
  const member = await createVerifiedMember(page);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  // ---- guia do perfil ----
  await page.goto(`/app/perfis/${perfilId}?aba=guia`);
  await expect(page.getByRole("tab", { name: "Guia", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.getByLabel("Tom de voz", { exact: true }).fill("Narrador de RPG, íntimo e bem-humorado.");
  await page.getByLabel("Faça", { exact: true }).fill(linhas("Fale com o público de você", "Comece pelo gancho"));
  await page.getByLabel("Vocabulário da casa", { exact: true }).fill(linhas("taverneiro", "aventureiro", "rolar dados"));
  await page.getByLabel("Palavras proibidas", { exact: true }).fill("clickbait");
  await page.getByLabel("Emojis", { exact: true }).selectOption("nao");
  await page.getByLabel("Hashtags fixas", { exact: true }).fill("#atavernanerd");
  await salvarGuia(page);
  await expect.poll(async () => (await guiaPerfil(request, auth, perfilId)).version).toBe(1);
  const perfilV1 = await guiaPerfil(request, auth, perfilId);
  expect(perfilV1.campos.hashtagsFixas).toEqual(["#atavernanerd"]);
  expect(perfilV1.campos.proibidas).toEqual(["clickbait"]);
  await page.screenshot({ path: `${SHOTS}/017-guia-perfil.png`, fullPage: true });

  // limites pela API: 6º exemplo e máximo de fixas no guia do perfil
  const seis = await putGuia(request, auth, `/api/perfis/${perfilId}/guia`, {
    ...perfilV1.campos,
    exemplos: Array.from({ length: 6 }, (_, i) => ({ tipo: "legenda" as const, texto: `Exemplo ${i + 1}` })),
  });
  expect(seis.status()).toBe(400);
  expect(((await seis.json()) as { error: { details: { fields: Record<string, string> } } }).error.details.fields.exemplos).toMatch(/5 exemplos/);
  const maxPerfil = await putGuia(request, auth, `/api/perfis/${perfilId}/guia`, { ...perfilV1.campos, maxHashtagsFixas: 3 });
  expect(maxPerfil.status()).toBe(400);
  expect(((await maxPerfil.json()) as { error: { details: { fields: Record<string, string> } } }).error.details.fields).toHaveProperty("maxHashtagsFixas");

  // ---- guia da conta: herdado visível, soma das fixas, máximo 6, conflito de emojis ----
  await page.goto(`/app/contas/${contaId}/guia`);
  const herdado = page.getByRole("region", { name: "Vem do perfil" });
  await expect(herdado.getByText("Narrador de RPG, íntimo e bem-humorado.")).toBeVisible();
  await expect(herdado.getByText("#atavernanerd")).toBeVisible();
  await page.getByLabel("Faça", { exact: true }).fill("No TikTok, frase curta com gancho na 1ª linha");
  await page.getByLabel("Emojis", { exact: true }).selectOption("livre");
  // exemplo com a proibida do perfil → recusado no campo
  await page.getByRole("button", { name: "Adicionar exemplo" }).click();
  await page.getByLabel("Exemplo 1", { exact: true }).fill("Não é clickbait!");
  await page.getByLabel("Hashtags fixas", { exact: true }).fill(linhas("#rpg", "#dados", "#nerd", "#mesa", "#taverna"));
  await salvarGuia(page);
  await expect(page.getByText(/usa a palavra proibida/).first()).toBeVisible();
  await expect(page.getByText(/perfil e conta somam 6 hashtags fixas; o máximo desta conta é 5/)).toBeVisible();
  expect((await guiaConta(request, auth, contaId)).version).toBe(0);
  await page.screenshot({ path: `${SHOTS}/017-guia-conta-erros.png`, fullPage: true });

  await page.getByLabel("Exemplo 1", { exact: true }).fill("Rolei os dados e deu crítico: olha esse achado!");
  await page.getByLabel("Máximo de hashtags fixas", { exact: true }).fill("6");
  await salvarGuia(page);
  await expect.poll(async () => (await guiaConta(request, auth, contaId)).version).toBe(1);
  const contaV1 = await guiaConta(request, auth, contaId);
  expect(contaV1.campos.maxHashtagsFixas).toBe(6);
  await expect(page.getByText(/sobram 2 vagas para a IA/)).toBeVisible();
  // emojis "não usar" no perfil e "livre" na conta: salva, com o aviso de conflito
  await expect(page.getByText(/vale a conta/).first()).toBeVisible();
  const efetivo = (await getJson<{ efetivo: { hashtagsFixas: string[]; maxHashtagsFixas: number }; conflitos: { campo: string }[] }>(
    request, auth, `/api/contas/${contaId}/guia`,
  ));
  expect(efetivo.efetivo.hashtagsFixas[0]).toBe("#atavernanerd");
  expect(efetivo.efetivo.maxHashtagsFixas).toBe(6);
  expect(efetivo.conflitos.map((c) => c.campo)).toContain("emojis");
  await page.screenshot({ path: `${SHOTS}/017-guia-conta.png`, fullPage: true });

  // validação cruzada: com a conta YouTube no máximo 1, a 2ª fixa do perfil é recusada citando a conta
  const yt = await putGuia(request, auth, `/api/contas/${youtubeId}/guia`, { maxHashtagsFixas: 1 });
  expect(yt.status(), await yt.text()).toBe(200);
  const segunda = await putGuia(request, auth, `/api/perfis/${perfilId}/guia`, { ...perfilV1.campos, hashtagsFixas: ["#atavernanerd", "#rpg2"] });
  expect(segunda.status()).toBe(400);
  const cruz = (await segunda.json()) as { error: { details: { contas: { contaId: string; campos: string[] }[] } } };
  expect(cruz.error.details.contas.map((c) => c.contaId)).toContain(youtubeId);

  // ---- reverter: muda o tom e volta para a v1 pelo histórico ----
  await page.goto(`/app/perfis/${perfilId}?aba=guia`);
  await page.getByLabel("Tom de voz", { exact: true }).fill("Tom trocado para testar a reversão.");
  await salvarGuia(page);
  await expect.poll(async () => (await guiaPerfil(request, auth, perfilId)).version).toBe(2);
  await page.reload();
  await page.getByRole("button", { name: "Reverter para esta versão" }).last().click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reverter", exact: true }).click();
  await expect.poll(async () => (await guiaPerfil(request, auth, perfilId)).campos.tom).toBe("Narrador de RPG, íntimo e bem-humorado.");
  const hist = await versions(request, auth, `/api/perfis/${perfilId}/guia/versions`);
  expect(hist[0]).toMatchObject({ action: "reverted", details: { from_version: 1 } });
  expect(hist[0].actor?.name).toBe(OWNER.name);
  await logout(page);

  // ---- membro: tudo visível, desabilitado, sem Salvar/Montar/Testar; PUT → 403 ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/perfis/${perfilId}?aba=guia`);
  await expect(page.getByLabel("Tom de voz", { exact: true })).toHaveValue("Narrador de RPG, íntimo e bem-humorado.");
  await expect(page.getByLabel("Tom de voz", { exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Salvar guia" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Montar com IA" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Testar guia" })).toHaveCount(0);
  await page.goto(`/app/contas/${contaId}/guia`);
  await expect(page.getByLabel("Faça", { exact: true })).toBeDisabled();
  await page.screenshot({ path: `${SHOTS}/017-guia-membro.png`, fullPage: true });
  const mtoken = await apiToken(request, member.email, member.final);
  const mput = await putGuia(request, { Authorization: `Bearer ${mtoken}` }, `/api/perfis/${perfilId}/guia`, { tom: "x" });
  expect(mput.status()).toBe(403);
});

// ---------------------------------------------------------------------------------------------
// US2: o guia entra no pedido. "Sugerir textos" num destino TikTok traz as fixas e a linha "Guia
// usado"; a proibida marca a proposta (Aplicar desabilitado, "Editar e aplicar" salva; a API
// recusa sem edição); o avatar recebe só as proibidas e mostra o link do guia; o registro mostra
// as versões.
// ---------------------------------------------------------------------------------------------
test("US2: sugerir textos com o guia, proibida, avatar e registro", async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const { auth, perfilId, perfilName, contaId, handle } = await perfilComConta(request, token, "Guia Post", sfx);
  const gp = await putGuia(request, auth, `/api/perfis/${perfilId}/guia`, {
    tom: "Narrador de RPG.",
    proibidas: ["clickbait"],
    hashtagsFixas: ["#atavernanerd"],
  });
  expect(gp.status(), await gp.text()).toBe(200);
  const gc = await putGuia(request, auth, `/api/contas/${contaId}/guia`, { faca: ["Gancho na 1ª linha"], hashtagsFixas: ["#rpg"] });
  expect(gc.status(), await gc.text()).toBe(200);
  const conteudoId = await videoProprio(request, auth, perfilId, testInfo.outputPath("guia.mp4"), `Guia video ${sfx}`);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos/${conteudoId}`);
  await page.getByRole("button", { name: "Adicionar conta" }).click();
  const add = page.getByRole("dialog", { name: "Adicionar conta" });
  await escolher(add.getByLabel("Conta"), handle);
  await add.getByRole("button", { name: "Adicionar" }).click();
  const legenda = page.getByRole("tabpanel").getByRole("textbox", { name: "Legenda *" });
  await expect(legenda).toBeVisible();

  // ---- Sugerir textos: as fixas (perfil, depois conta) vêm primeiro; "Guia usado" ----
  const textos = await abrirPainel(page, "postagem.textos");
  await gerar(textos);
  await expect(textos.getByText(/Guia usado: perfil v1 · conta v1/)).toBeVisible();
  let [ch] = await chamadas(request, auth, { perfilId, tipoCampo: "postagem.textos" });
  expect(ch).toMatchObject({ guiaPerfilVersion: 1, guiaContaVersion: 1, proibidas: [] });
  expect(ch.proposta!.hashtags!.slice(0, 2)).toEqual(["#atavernanerd", "#rpg"]);
  expect(ch.proposta!.hashtags!.length).toBeLessThanOrEqual(8);
  await textos.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  let [dest] = await destinos(request, auth, conteudoId);
  expect(dest.hashtags.slice(0, 2)).toEqual(["#atavernanerd", "#rpg"]);
  await page.screenshot({ path: `${SHOTS}/017-sugerir-textos.png`, fullPage: true });

  // ---- proibida: aviso, Aplicar desabilitado; a API recusa sem edição; Editar e aplicar salva ----
  const proib = await abrirPainel(page, "postagem.textos", "use a palavra proibida");
  await gerar(proib);
  await expect(proib.getByText(/A proposta usa uma palavra proibida pelo guia \(clickbait\); edite antes de aplicar\./)).toBeVisible();
  await expect(proib.getByRole("button", { name: "Aplicar", exact: true })).toBeDisabled();
  await expect(proib.getByRole("button", { name: "Editar e aplicar", exact: true })).toBeEnabled();
  await page.screenshot({ path: `${SHOTS}/017-proibida.png`, fullPage: true });
  [ch] = await chamadas(request, auth, { perfilId, tipoCampo: "postagem.textos" });
  expect(ch.proibidas).toEqual(["clickbait"]);
  [dest] = await destinos(request, auth, conteudoId);
  const recusa = await request.patch(`/api/destinos/${dest.id}`, {
    headers: auth,
    data: {
      version: dest.version,
      titulo: ch.proposta!.titulo,
      descricao: ch.proposta!.descricao,
      hashtags: ch.proposta!.hashtags,
      ia: [{ tipoCampo: "postagem.textos", chamadaId: ch.id }],
    },
  });
  expect(recusa.status()).toBe(400);
  const erro = ((await recusa.json()) as { error: { code: string; details: { palavras: string[]; campos: string[] } } }).error;
  expect(erro.code).toBe("ia_proibida");
  expect(erro.details.palavras).toEqual(["clickbait"]);

  await proib.getByRole("button", { name: "Editar e aplicar", exact: true }).click();
  await proib.getByLabel("Proposta: primeira linha").fill(`Título limpo ${sfx}`);
  await proib.getByLabel("Proposta: texto").fill(`Legenda limpa ${sfx}, sem a palavra.`);
  await proib.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(legenda).toHaveValue(`Legenda limpa ${sfx}, sem a palavra.`);
  [dest] = await destinos(request, auth, conteudoId);
  const hv = await versions(request, auth, `/api/destinos/${dest.id}/versions`);
  expect(hv[0].details.ia?.[0]).toMatchObject({ tipoCampo: "postagem.textos", desfecho: "editada" });

  // ---- avatar: link para o guia e só as proibidas no pedido ----
  const av = await request.post(`/api/perfis/${perfilId}/assets`, {
    headers: auth,
    data: { tipo: "avatar", name: "Taverneiro", tags: ["persona"] },
  });
  expect(av.status(), await av.text()).toBe(201);
  const assetId = ((await av.json()) as { asset: { id: string } }).asset.id;
  await page.goto(`/app/assets/${assetId}`);
  const desc = await abrirPainel(page, "avatar.descricao_prompt", "proibida");
  await gerar(desc);
  await expect(desc.getByText(/palavra proibida pelo guia \(clickbait\)/)).toBeVisible();
  await expect(desc.getByRole("button", { name: "Aplicar", exact: true })).toBeDisabled();
  const [cav] = await chamadas(request, auth, { perfilId, tipoCampo: "avatar.descricao_prompt" });
  expect(cav).toMatchObject({ guiaPerfilVersion: 1, guiaContaVersion: null, proibidas: ["clickbait"] });
  await page.screenshot({ path: `${SHOTS}/017-avatar.png`, fullPage: true });
  await page.getByRole("link", { name: "Ver guia de comunicação do perfil" }).first().click();
  await expect(page).toHaveURL(new RegExp(`/app/perfis/${perfilId}\\?aba=guia$`));
  await expect(page.getByLabel("Tom de voz", { exact: true })).toHaveValue("Narrador de RPG.");

  // ---- registro: as versões dos dois guias na chamada ----
  await page.goto("/app/assistente-ia?aba=registro");
  await page.getByLabel("Perfil", { exact: true }).selectOption({ label: perfilName });
  const tabela = page.getByRole("table", { name: "Chamadas ao assistente de IA" });
  await tabela.getByRole("row").filter({ hasText: /Textos da postagem/ }).first().getByRole("button", { name: "Ver a chamada" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByText(/Guia do perfil v1/)).toBeVisible();
  await expect(sheet.getByText(/Guia da conta v1/)).toBeVisible();
  await expect(sheet.getByText("clickbait").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/017-registro.png`, fullPage: true });
});

// ---------------------------------------------------------------------------------------------
// US3: "Montar com IA" preenche o formulário (versão 0 até salvar); "Testar guia" mostra 3
// variações com o guia do formulário e grava só a chamada.
// ---------------------------------------------------------------------------------------------
test("US3: montar e testar o guia com a IA", async ({ page, request }, testInfo) => {
  test.setTimeout(240_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const { auth, perfilId, handle } = await perfilComConta(request, token, "Guia Montar", sfx);
  const titulo = `Guia montar video ${sfx}`;
  const conteudoId = await videoProprio(request, auth, perfilId, testInfo.outputPath("montar.mp4"), titulo);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/perfis/${perfilId}?aba=guia`);

  // ---- montar: preenche o formulário, nada salvo ----
  await page.getByRole("button", { name: "Montar com IA" }).click();
  const montar = page.getByRole("dialog", { name: /Montar/ });
  await montar.getByLabel("Descrição curta").fill("perfil de achadinhos de cozinha, fala como amiga");
  await montar.getByRole("button", { name: "Gerar proposta", exact: true }).click();
  await expect(montar.getByText(/Claude falso do e2e/)).toBeVisible({ timeout: 25_000 });
  await page.screenshot({ path: `${SHOTS}/017-montar.png`, fullPage: true });
  await montar.getByRole("button", { name: "Usar no formulário", exact: true }).click();
  await expect(page.getByLabel("Tom de voz", { exact: true })).toHaveValue(/^Descontraído e direto, versão \d+ do Claude falso\.$/);
  await expect(page.getByLabel("Palavras proibidas", { exact: true })).toHaveValue("clickbait");
  expect((await guiaPerfil(request, auth, perfilId)).version).toBe(0);
  await page.getByLabel("Hashtags fixas", { exact: true }).fill("#queridinhos");

  // ---- testar: 3 variações com as fixas do formulário; nada gravado além da chamada ----
  await page.getByRole("button", { name: "Testar guia" }).click();
  const testar = page.getByRole("dialog", { name: /Testar/ });
  await escolher(testar.getByLabel("Conteúdo", { exact: true }), titulo);
  await escolher(testar.getByLabel("Conta"), handle);
  await testar.getByRole("button", { name: "Gerar 3 exemplos", exact: true }).click();
  for (const v of [1, 2, 3]) await expect(testar.getByText(new RegExp(`Variação ${v} sugerida pela IA`))).toBeVisible({ timeout: 25_000 });
  await expect(testar.getByText("#queridinhos").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/017-testar.png`, fullPage: true });
  const [teste] = await chamadas(request, auth, { perfilId, tipoCampo: "guia.testar" });
  expect(teste).toMatchObject({ guiaRascunho: "perfil", desfecho: "sem_acao" });
  expect(teste.proposta!.variacoes).toHaveLength(3);
  for (const v of teste.proposta!.variacoes!) expect(v.hashtags[0]).toBe("#queridinhos");
  expect(await destinos(request, auth, conteudoId)).toHaveLength(0);
  expect((await guiaPerfil(request, auth, perfilId)).version).toBe(0);
  await page.keyboard.press("Escape");

  // ---- salvar: versão 1 com a chamada do montar ----
  await page.getByLabel("Tom de voz", { exact: true }).fill("Amiga que acha tudo de cozinha, animada.");
  await salvarGuia(page);
  await expect.poll(async () => (await guiaPerfil(request, auth, perfilId)).version).toBe(1);
  const hist = await versions(request, auth, `/api/perfis/${perfilId}/guia/versions`);
  expect(hist[0].details.ia?.[0]).toMatchObject({ tipoCampo: "guia.montar", desfecho: "editada" });
  const [montada] = await chamadas(request, auth, { perfilId, tipoCampo: "guia.montar" });
  expect(montada.desfecho).toBe("editada");
});
