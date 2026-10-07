import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, login, logout, syntheticMp4 } from "./helpers";

// Spec 008 (T033, T038, T042, T046): o assistente de IA com o Claude falso do `openshorts-fake`
// (`POST /v1/messages`, e2e/fakes/server.py). O fake devolve textos determinísticos por tipo de
// campo; "lento" na instrução passa do timeout e "fora do limite" devolve um texto enorme. Nas
// sugestões, nunca repete o que já está no pedido. Nenhuma chamada sai para a Anthropic.

const SHOTS = ".playwright-mcp/sociman";

type Auth = { Authorization: string };

interface Chamada {
  id: string;
  tipoCampo: string;
  sessaoId: string | null;
  desfecho: string;
  proposta: { texto?: string; itens?: string[]; titulo?: string } | null;
  aceitos: string[];
  rejeitados: string[];
  itensAplicados: string[] | null;
  custoUsd: number | null;
}

interface Version {
  version: number;
  changedFields: string[];
  details: { ia?: { campo: string; tipoCampo: string; chamadaId: string; desfecho: string; itens?: string[] }[] };
  actorKind: string;
  actor: { name: string } | null;
}

// Botão "Melhorar com IA" e painel de um tipo de campo (data-testid do IaAssist).
function botaoIa(scope: Page | Locator, tipo: string): Locator {
  return scope.getByTestId(`ia-botao-${tipo}`);
}

function painelIa(scope: Page | Locator, tipo: string): Locator {
  return scope.getByTestId(`ia-painel-${tipo}`);
}

async function abrirPainel(page: Page, tipo: string, instrucao = ""): Promise<Locator> {
  await botaoIa(page, tipo).click();
  const painel = painelIa(page, tipo);
  await expect(painel).toBeVisible();
  if (instrucao) await painel.getByLabel("Como a IA deve ajudar?").fill(instrucao);
  return painel;
}

// Gera e espera a explicação do fake ("Proposta N do Claude falso do e2e."); `texto`, quando dado,
// também tem de aparecer no painel (como texto ou valor de um campo da proposta).
async function gerar(painel: Locator, texto?: RegExp): Promise<void> {
  await painel.getByRole("button", { name: "Gerar", exact: true }).click();
  await expect(painel.getByText(/Claude falso do e2e/).last()).toBeVisible({ timeout: 25_000 });
  if (texto) await expect(painel.getByText(texto).or(painel.getByRole("textbox").filter({ hasText: texto })).first()).toBeVisible();
}

function tab(page: Page, name: string): Locator {
  return page.getByRole("tab", { name, exact: true });
}

async function getJson<T>(request: APIRequestContext, auth: Auth, url: string): Promise<T> {
  const res = await request.get(url, { headers: auth });
  expect(res.status(), `GET ${url}: ${res.status() === 200 ? "" : await res.text()}`).toBe(200);
  return (await res.json()) as T;
}

async function chamadas(request: APIRequestContext, auth: Auth, query: Record<string, string>): Promise<Chamada[]> {
  const qs = new URLSearchParams({ limit: "100", ...query }).toString();
  return (await getJson<{ items: Chamada[] }>(request, auth, `/api/ia/chamadas?${qs}`)).items;
}

async function versions(request: APIRequestContext, auth: Auth, url: string): Promise<Version[]> {
  return (await getJson<{ items: Version[] }>(request, auth, url)).items;
}

// Avatar "Achadinhos" pela API, com descrição, tom de voz e regras de imagem.
async function seedAvatar(request: APIRequestContext, auth: Auth, perfilId: string): Promise<string> {
  const res = await request.post(`/api/perfis/${perfilId}/assets`, {
    headers: auth,
    data: { tipo: "avatar", name: "Achadinhos", tags: ["persona"] },
  });
  expect(res.status(), `POST assets: ${await res.text()}`).toBe(201);
  const { asset } = (await res.json()) as { asset: { id: string; version: number } };
  const patch = await request.patch(`/api/assets/${asset.id}`, {
    headers: auth,
    data: {
      version: asset.version,
      prompt: "A cheerful 1950s pin-up woman, red victory-roll hair, polka-dot dress.",
      voiceTone: "Animado e próximo.",
      imageRules: "Evitar textos em inglês no fundo.",
      description: "Notas originais.",
    },
  });
  expect(patch.status(), `PATCH asset: ${await patch.text()}`).toBe(200);
  return asset.id;
}

async function getAsset(request: APIRequestContext, auth: Auth, id: string) {
  return (
    await getJson<{
      asset: { version: number; name: string; prompt: string; voiceTone: string; imageRules: string; description: string };
    }>(request, auth, `/api/assets/${id}`)
  ).asset;
}

async function getKit(request: APIRequestContext, auth: Auth, perfilId: string) {
  return (
    await getJson<{
      kit: { version: number; catchphrases: string[]; series: string[]; palette: { chave: string; nome: string; valor: string }[] } & Record<string, unknown>;
    }>(request, auth, `/api/perfis/${perfilId}/kit`)
  ).kit;
}

// Salva o kit pela API com `mudar` aplicado sobre os tokens atuais.
async function putKit(request: APIRequestContext, auth: Auth, perfilId: string, mudar: (kit: Record<string, unknown>) => void): Promise<void> {
  const kit = (await getKit(request, auth, perfilId)) as Record<string, unknown>;
  const body = { ...kit };
  for (const k of ["perfilId", "persisted", "updatedAt", "updatedBy"]) delete body[k];
  mudar(body);
  const res = await request.put(`/api/perfis/${perfilId}/kit`, { headers: auth, data: body });
  expect(res.status(), `PUT kit: ${await res.text()}`).toBe(200);
}

// ---------------------------------------------------------------------------------------------
// US1 (T033): no avatar, gerar e Aplicar em 1 clique com outro campo editado sem salvar (R-9),
// Editar e aplicar, Outra versão, Descartar, limite excedido e conflito de versão.
// ---------------------------------------------------------------------------------------------
test("avatar: aplicar em 1 clique salva só o campo e preserva o formulário", async ({ page, request }) => {
  test.setTimeout(240_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `IA Avatar ${sfx}`, slug: `ia-avatar-${sfx}`, niche: "achadinhos" });
  const assetId = await seedAvatar(request, auth, perfilId);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/assets/${assetId}`);
  await expect(page.getByRole("heading", { level: 1, name: "Achadinhos" })).toBeVisible();

  // gerar a descrição para prompts com instrução
  const desc = await abrirPainel(page, "avatar.descricao_prompt", "mais detalhes do rosto");
  await gerar(desc, /Vintage 1950s shop girl/);
  await expect(desc.getByText(/Segui a instrução: mais detalhes do rosto/)).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/008-painel-avatar.png`, fullPage: true });
  const proposta = (await chamadas(request, auth, { perfilId, tipoCampo: "avatar.descricao_prompt" }))[0].proposta!.texto!;
  expect(proposta).toContain("Vintage 1950s shop girl");

  // o tom de voz editado à mão, sem salvar, antes de aplicar
  const tomEditado = `Tom editado à mão ${sfx}`;
  await page.getByLabel("Tom de voz", { exact: true }).fill(tomEditado);

  // Aplicar (1 clique): toast, o campo com a proposta e o tom de voz intacto no formulário
  await desc.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  await expect(page.getByLabel("Descrição para prompts", { exact: true })).toHaveValue(proposta);
  await expect(page.getByLabel("Tom de voz", { exact: true })).toHaveValue(tomEditado);

  // na API: só a descrição mudou, com o selo e autor humano
  let asset = await getAsset(request, auth, assetId);
  expect(asset.prompt).toBe(proposta);
  expect(asset.voiceTone).toBe("Animado e próximo.");
  let hist = await versions(request, auth, `/api/assets/${assetId}/versions`);
  expect(hist[0].actorKind).toBe("user");
  expect(hist[0].changedFields).toEqual(["prompt"]);
  expect(hist[0].details.ia?.[0]).toMatchObject({ tipoCampo: "avatar.descricao_prompt", desfecho: "aplicada" });
  await expect(page.getByText("com ajuda da IA").first()).toBeVisible();

  // "Salvar" da tela grava o tom de voz sem 409 (o formulário já usa a versão nova)
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Alterações salvas.")).toBeVisible();
  asset = await getAsset(request, auth, assetId);
  expect(asset.voiceTone).toBe(tomEditado);
  expect(asset.prompt).toBe(proposta);
  await page.screenshot({ path: `${SHOTS}/008-historico-selo.png`, fullPage: true });

  // Tom de voz: Gerar → Outra versão (abas) → Editar e aplicar
  const tom = await abrirPainel(page, "avatar.tom_de_voz");
  await gerar(tom, /Animada e próxima/);
  await tom.getByRole("button", { name: "Outra versão", exact: true }).click();
  const versao = (n: number) => tom.getByRole("button", { name: `Versão ${n}`, exact: true });
  await expect(versao(2)).toBeVisible({ timeout: 25_000 });
  await expect(versao(2)).toHaveAttribute("aria-pressed", "true");
  const [v2, v1] = (await chamadas(request, auth, { perfilId, tipoCampo: "avatar.tom_de_voz" })).map((c) => c.proposta!.texto!);
  expect(v2).not.toBe(v1);
  await versao(1).click();
  await expect(versao(1)).toHaveAttribute("aria-pressed", "true");
  await expect(tom.getByText(v1)).toBeVisible();
  await versao(2).click();
  await expect(tom.getByText(v2)).toBeVisible();
  await tom.getByRole("button", { name: "Editar e aplicar", exact: true }).click();
  const editado = `Animada, próxima e editada ${sfx}`;
  await tom.getByLabel("Proposta (editável)").fill(editado);
  await tom.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  await expect(page.getByLabel("Tom de voz", { exact: true })).toHaveValue(editado);
  hist = await versions(request, auth, `/api/assets/${assetId}/versions`);
  expect(hist[0].changedFields).toEqual(["voice_tone"]);
  expect(hist[0].details.ia?.[0]).toMatchObject({ tipoCampo: "avatar.tom_de_voz", desfecho: "editada" });
  const tomChamadas = await chamadas(request, auth, { perfilId, tipoCampo: "avatar.tom_de_voz" });
  expect(tomChamadas).toHaveLength(2);
  expect(new Set(tomChamadas.map((c) => c.sessaoId)).size).toBe(1);
  // ao aplicar, o painel fecha e descarta a outra versão (melhor esforço)
  await expect
    .poll(async () => (await chamadas(request, auth, { perfilId, tipoCampo: "avatar.tom_de_voz" })).map((c) => c.desfecho).sort())
    .toEqual(["descartada", "editada"]);

  // Regras de imagem: Descartar não muda nada; a chamada fica "descartada"
  const regras = await abrirPainel(page, "avatar.regras_imagem");
  await gerar(regras, /Sempre com o avental rosa/);
  await regras.getByRole("button", { name: "Descartar", exact: true }).click();
  await expect(painelIa(page, "avatar.regras_imagem")).toBeHidden();
  await expect(page.getByLabel("Regras de imagem", { exact: true })).toHaveValue("Evitar textos em inglês no fundo.");
  await expect
    .poll(async () => (await chamadas(request, auth, { perfilId, tipoCampo: "avatar.regras_imagem" }))[0]?.desfecho)
    .toBe("descartada");
  expect((await getAsset(request, auth, assetId)).imageRules).toBe("Evitar textos em inglês no fundo.");

  // "fora do limite": proposta marcada, Aplicar desabilitado até editar
  const nome = await abrirPainel(page, "asset.nome", "fora do limite");
  await gerar(nome, /Texto longo demais/);
  await expect(nome.getByRole("button", { name: "Aplicar", exact: true })).toBeDisabled();
  await page.screenshot({ path: `${SHOTS}/008-fora-do-limite.png`, fullPage: true });
  await nome.getByRole("button", { name: "Descartar", exact: true }).click();

  // conflito: a versão muda por fora no meio; Aplicar avisa e nada é salvo
  const notas = await abrirPainel(page, "asset.descricao");
  await gerar(notas, /Notas sugeridas pela IA/);
  const atual = await getAsset(request, auth, assetId);
  const fora = await request.patch(`/api/assets/${assetId}`, { headers: auth, data: { version: atual.version, tags: ["persona", "conflito"] } });
  expect(fora.status()).toBe(200);
  await notas.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(notas.getByText("Conflito de versão")).toBeVisible();
  await expect(notas.getByRole("button", { name: "Recarregar" })).toBeVisible();
  await expect(notas.getByText(/Notas sugeridas pela IA/).first()).toBeVisible();
  expect((await getAsset(request, auth, assetId)).description).toBe("Notas originais.");
});

// ---------------------------------------------------------------------------------------------
// US1 (T033): perfil (bio com o nicho editado sem salvar) e kit (bordões com seleção, Gerar mais,
// paleta alterada sem salvar fora da versão, lista cheia) — riscos R-9/R-10.
// ---------------------------------------------------------------------------------------------
test("perfil e kit: bio e bordões com seleção preservam o que foi digitado", async ({ page, request }) => {
  test.setTimeout(240_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `IA Kit ${sfx}`, slug: `ia-kit-${sfx}`, niche: "achadinhos" });
  await putKit(request, auth, perfilId, (k) => {
    k.version = 0;
    k.catchphrases = ["Corre que acaba!"];
  });

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  // ---- perfil: bio aplicada com o nicho editado e não salvo ----
  await page.goto(`/app/perfis/${perfilId}`);
  const nicho = `Nicho digitado ${sfx}`;
  await page.getByLabel("Nicho", { exact: true }).fill(nicho);
  const bio = await abrirPainel(page, "perfil.bio");
  await gerar(bio, /Bio sugerida pela IA/);
  await bio.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  await expect(page.getByLabel("Nicho", { exact: true })).toHaveValue(nicho);
  let perfil = (await getJson<{ perfil: { niche: string; bio: string } }>(request, auth, `/api/perfis/${perfilId}`)).perfil;
  expect(perfil.bio).toMatch(/^Bio sugerida pela IA/);
  expect(perfil.niche).toBe("achadinhos");
  const hp = await versions(request, auth, `/api/perfis/${perfilId}/versions`);
  expect(hp[0].changedFields).toEqual(["bio"]);
  expect(hp[0].details.ia?.[0]).toMatchObject({ tipoCampo: "perfil.bio", desfecho: "aplicada" });
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect
    .poll(async () => (await getJson<{ perfil: { niche: string } }>(request, auth, `/api/perfis/${perfilId}`)).perfil.niche)
    .toBe(nicho);

  // ---- kit: paleta mudada sem salvar; bordões com seleção ----
  await page.goto(`/app/perfis/${perfilId}?aba=marca`);
  await expect(tab(page, "Marca")).toHaveAttribute("aria-selected", "true");
  const kitAntes = await getKit(request, auth, perfilId);
  const paleta = page.getByRole("region", { name: "Paleta", exact: true });
  await paleta.getByLabel("Cor 1: hex").fill("#123456");

  const bordoes = await abrirPainel(page, "kit.bordoes", "crie 5 bordões no tom da Achadinhos");
  await gerar(bordoes, /Achado bom é achado dividido/);
  const sug = bordoes.getByRole("checkbox");
  await expect(sug).toHaveCount(5);
  const primeira = await bordoes.getByRole("checkbox").nth(0).getAttribute("aria-label");
  const segunda = await bordoes.getByRole("checkbox").nth(1).getAttribute("aria-label");
  const naoMarcadas = [];
  for (let i = 2; i < 5; i++) naoMarcadas.push(await bordoes.getByRole("checkbox").nth(i).getAttribute("aria-label"));
  await bordoes.getByRole("checkbox", { name: primeira!, exact: true }).check();
  await bordoes.getByRole("checkbox", { name: segunda!, exact: true }).check();
  await expect(bordoes.getByText("3 de 20")).toBeVisible();
  const editadoBordao = `${segunda} editado`;
  await bordoes.getByLabel(`Editar: ${segunda}`, { exact: true }).fill(editadoBordao);

  // Gerar mais: 5 novas abaixo, sem repetir as marcadas, as rejeitadas nem a lista do kit
  await bordoes.getByRole("button", { name: "Gerar mais", exact: true }).click();
  await expect(bordoes.getByRole("checkbox")).toHaveCount(10, { timeout: 25_000 });
  const todas = await bordoes.getByRole("checkbox").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""));
  expect(new Set(todas.map((t) => t.toLowerCase())).size).toBe(10);
  await expect(bordoes.getByRole("checkbox", { name: primeira!, exact: true })).toBeChecked();
  const terceira = todas[5];
  await bordoes.getByRole("checkbox", { name: terceira, exact: true }).check();
  await page.screenshot({ path: `${SHOTS}/008-bordoes-sugestoes.png`, fullPage: true });

  await bordoes.getByRole("button", { name: "Aplicar 3", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  const kitDepois = await getKit(request, auth, perfilId);
  expect(kitDepois.catchphrases).toEqual(["Corre que acaba!", primeira, editadoBordao, terceira]);
  expect(kitDepois.palette).toEqual(kitAntes.palette); // a cor mudada não entrou na versão
  await expect(paleta.getByLabel("Cor 1: hex")).toHaveValue("#123456"); // e continua no formulário
  const hk = await versions(request, auth, `/api/perfis/${perfilId}/kit/versions`);
  expect(hk[0].changedFields).toEqual(["catchphrases"]);
  expect(hk[0].details.ia?.map((i) => i.desfecho).sort()).toEqual(["aplicada", "editada"]);
  const cb = await chamadas(request, auth, { perfilId, tipoCampo: "kit.bordoes" });
  const gerarMais = cb.find((c) => c.aceitos.length > 0)!;
  expect(gerarMais.aceitos.map((a) => a.toLowerCase()).sort()).toEqual([primeira!, editadoBordao].map((a) => a.toLowerCase()).sort());
  expect(gerarMais.rejeitados.map((r) => r.toLowerCase()).sort()).toEqual(naoMarcadas.map((r) => r!.toLowerCase()).sort());
  await expect(bordoes.getByText("no kit")).toHaveCount(3);
  await bordoes.getByRole("button", { name: "Fechar", exact: true }).click();

  // ---- lista cheia: 19 bordões; só cabe 1; depois de aplicar (20), Gerar desabilitado ----
  await putKit(request, auth, perfilId, (k) => {
    k.catchphrases = Array.from({ length: 19 }, (_, i) => `Bordão fixo ${i + 1}`);
  });
  await page.reload();
  const cheio = await abrirPainel(page, "kit.bordoes");
  await gerar(cheio, /Achado bom é achado dividido/);
  await cheio.getByRole("checkbox").nth(0).check();
  await expect(cheio.getByText("20 de 20")).toBeVisible();
  await expect(cheio.getByText("A lista está cheia (máximo de 20)")).toBeVisible();
  await expect(cheio.getByRole("checkbox").nth(1)).toBeDisabled();
  await page.screenshot({ path: `${SHOTS}/008-lista-cheia.png`, fullPage: true });
  await cheio.getByRole("button", { name: "Aplicar 1", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  expect((await getKit(request, auth, perfilId)).catchphrases).toHaveLength(20);
  await expect(cheio.getByRole("button", { name: "Gerar mais", exact: true })).toBeDisabled();
});

// ---------------------------------------------------------------------------------------------
// US2 (T038) + US4 (T046): o dono edita a regra do título e vê o efeito na postagem; Sugerir
// textos cria o rascunho com o selo; título "mais polêmico" em 1 clique; voltar ao padrão e
// reverter; o membro vê as regras sem edição e leva 403 nas rotas do dono.
// ---------------------------------------------------------------------------------------------
test("regras do título e textos da postagem pelo mesmo painel", async ({ page, request }, testInfo) => {
  test.setTimeout(420_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `IA Post ${sfx}`, slug: `ia-post-${sfx}`, niche: "achadinhos" });
  const conta = await request.post(`/api/perfis/${perfilId}/contas`, {
    headers: auth,
    data: { platform: "youtube", handle: `iapost${sfx}`, status: "ativa" },
  });
  expect(conta.status(), "POST contas").toBe(201);
  const member = await createVerifiedMember(page);

  // um corte pronto (MP4 sintético pela aba Cortes; o worker processa em segundo plano)
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const video = testInfo.outputPath("corte.mp4");
  syntheticMp4(video, 4);
  await page.goto(`/app/perfis/${perfilId}`);
  await tab(page, "Cortes").click();
  await page.getByLabel("Vídeo do corte").setInputFiles(video);
  await page.getByLabel("Texto do gancho").fill(`Gancho IA ${sfx}`);
  await page.getByRole("button", { name: "Enviar corte" }).click();
  await expect(page).toHaveURL(/\/app\/cortes\/[0-9a-f-]{36}$/, { timeout: 30_000 });
  const corteUrl = page.url();

  // ---- US2: regra do título com emoji ----
  await page.goto("/app/assistente-ia");
  await expect(tab(page, "Regras")).toBeVisible();
  await expect(tab(page, "Registro")).toBeVisible();
  await expect(tab(page, "Resumo do mês")).toBeVisible();
  await page.getByRole("link", { name: "Título da postagem" }).click();
  await expect(page).toHaveURL(/\/app\/assistente-ia\/regras\/postagem\.titulo$/);
  const regra = page.getByLabel("Regras em vigor", { exact: true });
  await regra.fill(`${await regra.inputValue()}\n- sempre termine com um emoji`);
  await page.getByRole("button", { name: "Salvar regras", exact: true }).click();
  await expect(page.getByText("Personalizada").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/008-regra-titulo.png`, fullPage: true });

  // ---- US4: o corte pronto em Conteúdos (spec 014: conteúdo = corte, destino por conta);
  // "Sugerir textos" preenche os três campos do destino ----
  await page.goto(corteUrl);
  await expect(page.getByText("Pronto", { exact: true }).first()).toBeVisible({ timeout: 180_000 });
  const corteId = corteUrl.split("/").pop()!;
  await page.goto(`/app/conteudos/${corteId}`);
  await page.getByRole("button", { name: "Adicionar conta" }).click();
  const add = page.getByRole("dialog", { name: "Adicionar conta" });
  const contaOpt = add.getByLabel("Conta").and(page.locator("select")).locator("option").filter({ hasText: `iapost${sfx}` }).first();
  await add.getByLabel("Conta").and(page.locator("select")).selectOption((await contaOpt.getAttribute("value"))!);
  await add.getByRole("button", { name: "Adicionar" }).click();
  const postagem = page.getByRole("tabpanel");
  await expect(postagem.getByLabel("Título", { exact: true })).toBeVisible();
  // spec 023 (T052): uma preferência do perfil (v1) faz o bloco <desempenho> ir no pedido; a
  // hashtag evitada não é das que o Claude falso propõe (os textos continuam os mesmos)
  const pref = await request.patch(`/api/perfis/${perfilId}/aprendizado/preferencias`, { headers: auth, data: { version: 0, hashtagsEvitar: ["#nuncausada"] } });
  expect(pref.status(), "PATCH preferências (023)").toBe(200);
  const versaoPref = ((await pref.json()) as { version: number }).version;
  const textos = await abrirPainel(page, "postagem.textos");
  await gerar(textos);
  await textos.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  // a regra editada vale só para o tipo "Título da postagem", não para "Sugerir textos"
  await expect(postagem.getByLabel("Título", { exact: true })).toHaveValue(/^Título sugerido pela IA \d+$/);
  const conteudo = await getJson<{ conteudo: { destinos: { id: string; titulo: string; descricao: string; hashtags: string[] }[] } }>(
    request, auth, `/api/conteudos/${corteId}`,
  );
  expect(conteudo.conteudo.destinos).toHaveLength(1);
  const post = conteudo.conteudo.destinos[0];
  expect(post.titulo).toMatch(/^Título sugerido pela IA \d+$/);
  expect(post.descricao).toMatch(/^Descrição sugerida pela IA/);
  expect(post.hashtags.length).toBeGreaterThanOrEqual(3);
  let hv = await versions(request, auth, `/api/destinos/${post.id}/versions`);
  expect(hv[0].details.ia?.[0]).toMatchObject({ tipoCampo: "postagem.textos", desfecho: "aplicada" });
  // spec 023: o registro mostra a versão do desempenho usada (a do perfil; a conta sem preferências)
  const chamadaTextos = (await chamadas(request, auth, { perfilId, tipoCampo: "postagem.textos" }))[0];
  await page.goto(`/app/assistente-ia?aba=registro&chamada=${chamadaTextos.id}`);
  await expect(page.getByRole("dialog").locator("[data-desempenho]")).toHaveText(new RegExp(`Desempenho: perfil v${versaoPref}, conta v0, \\d+ exemplos?`));
  await page.goto(`/app/conteudos/${corteId}`);
  await expect(postagem.getByLabel("Título", { exact: true })).toBeVisible();

  // título "mais polêmico" em 1 clique
  const titulo = await abrirPainel(page, "postagem.titulo", "mais polêmico");
  await gerar(titulo, /\(mais polêmico\)/);
  await titulo.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  await expect(postagem.getByLabel("Título", { exact: true })).toHaveValue(/\(mais polêmico\) 🔥$/); // a regra chegou ao Claude
  hv = await versions(request, auth, `/api/destinos/${post.id}/versions`);
  expect(hv[0].changedFields).toEqual(["titulo"]);
  expect(hv[0].details.ia?.[0]).toMatchObject({ tipoCampo: "postagem.titulo", desfecho: "aplicada" });
  await expect(page.getByText("com ajuda da IA").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/008-postagem.png`, fullPage: true });

  // ---- US2: voltar ao padrão (e o histórico da regra), depois reverter para a versão com emoji ----
  await page.goto("/app/assistente-ia/regras/postagem.titulo");
  await page.getByRole("button", { name: "Voltar ao padrão", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Voltar ao padrão" }).click();
  await expect(page.getByText("Padrão", { exact: true }).first()).toBeVisible();
  const rv = await versions(request, auth, "/api/ia/tipos/postagem.titulo/versions");
  expect(rv.map((v) => v.version)).toEqual([2, 1]);
  expect(rv[0].details).toMatchObject({ padrao: true });
  const tipo = async () =>
    (await getJson<{ tipo: { regras: { texto: string; personalizada: boolean; version: number } } }>(request, auth, "/api/ia/tipos/postagem.titulo")).tipo.regras;
  expect((await tipo()).personalizada).toBe(false);
  await page.getByRole("button", { name: "Reverter para esta versão" }).first().click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reverter", exact: true }).click();
  await expect.poll(async () => (await tipo()).texto).toContain("sempre termine com um emoji");
  // deixa a regra no padrão para os outros testes
  const r = await tipo();
  const padrao = await request.post("/api/ia/tipos/postagem.titulo/padrao", { headers: auth, data: { version: r.version } });
  expect(padrao.status()).toBe(200);
  await logout(page);

  // ---- US2-3: o membro vê as regras, sem edição, e sem Registro/Resumo ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/assistente-ia");
  await expect(page.getByRole("link", { name: "Título da postagem" })).toBeVisible();
  await expect(tab(page, "Registro")).toHaveCount(0);
  await expect(tab(page, "Resumo do mês")).toHaveCount(0);
  await page.getByRole("link", { name: "Título da postagem" }).click();
  await expect(page.getByText("Só o dono edita as regras.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Salvar regras" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reverter para esta versão" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Voltar ao padrão" })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/008-regras-membro.png`, fullPage: true });
  const mtoken = await apiToken(request, member.email, member.final);
  const mauth = { Authorization: `Bearer ${mtoken}` };
  const put = await request.put("/api/ia/tipos/postagem.titulo/regras", { headers: mauth, data: { version: 0, texto: "x" } });
  expect(put.status()).toBe(403);
  expect((await request.get("/api/ia/chamadas", { headers: mauth })).status()).toBe(403);
  expect((await request.get("/api/ia/resumo", { headers: mauth })).status()).toBe(403);
});

// ---------------------------------------------------------------------------------------------
// US3 (T042): 3 gerações (aplicar 1, descartar 1, outra versão em 1) → 4 linhas no registro com
// os desfechos certos; resumo com a soma; modo "lento" → "A IA demorou demais" e "Tentar de novo".
// ---------------------------------------------------------------------------------------------
test("registro e resumo das chamadas, e o tempo esgotado", async ({ page, request }) => {
  test.setTimeout(240_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilName = `IA Registro ${sfx}`;
  const perfilId = await createPerfilViaApi(request, token, { name: perfilName, slug: `ia-registro-${sfx}` });
  const assetId = await seedAvatar(request, auth, perfilId);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/assets/${assetId}`);

  // 1: aplicar
  const a = await abrirPainel(page, "asset.descricao");
  await gerar(a, /Notas sugeridas pela IA/);
  await a.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA")).toBeVisible();
  // 2: descartar
  const d = await abrirPainel(page, "avatar.regras_imagem");
  await gerar(d, /Sempre com o avental rosa/);
  await d.getByRole("button", { name: "Descartar", exact: true }).click();
  // 3: outra versão (2 chamadas na mesma sessão), sem aplicar
  const o = await abrirPainel(page, "asset.nome");
  await gerar(o, /Nome sugerido pela IA/);
  await o.getByRole("button", { name: "Outra versão", exact: true }).click();
  await expect(o.getByRole("button", { name: "Versão 2", exact: true })).toBeVisible({ timeout: 25_000 });

  await expect
    .poll(async () => (await chamadas(request, auth, { perfilId })).map((c) => `${c.tipoCampo}:${c.desfecho}`).sort())
    .toEqual(["asset.descricao:aplicada", "asset.nome:sem_acao", "asset.nome:sem_acao", "avatar.regras_imagem:descartada"]);
  const nomes = await chamadas(request, auth, { perfilId, tipoCampo: "asset.nome" });
  expect(nomes[0].sessaoId).not.toBeNull();
  expect(nomes[0].sessaoId).toBe(nomes[1].sessaoId);

  // modo "lento": mensagem clara, "Tentar de novo" e o campo continua editável
  const lento = await abrirPainel(page, "avatar.tom_de_voz", "lento");
  await lento.getByRole("button", { name: "Gerar", exact: true }).click();
  await expect(lento.getByText("Não foi possível gerar")).toBeVisible({ timeout: 40_000 });
  await expect(lento.getByText(/A IA demorou demais/)).toBeVisible();
  await expect(lento.getByRole("button", { name: "Tentar de novo" })).toBeVisible();
  await page.getByLabel("Tom de voz", { exact: true }).fill("Editável à mão depois do erro.");
  await expect(page.getByLabel("Tom de voz", { exact: true })).toHaveValue("Editável à mão depois do erro.");
  await page.screenshot({ path: `${SHOTS}/008-timeout.png`, fullPage: true });
  const erro = (await chamadas(request, auth, { perfilId, desfecho: "erro" }))[0];
  expect(erro.tipoCampo).toBe("avatar.tom_de_voz");

  // Registro: filtrado por perfil, as 5 linhas (4 + o erro)
  await page.goto("/app/assistente-ia?aba=registro");
  await page.getByLabel("Perfil", { exact: true }).selectOption({ label: perfilName });
  const linhas = page.getByRole("table", { name: "Chamadas ao assistente de IA" }).getByRole("row").filter({ hasText: perfilName });
  await expect(linhas).toHaveCount(5);
  await expect(linhas.filter({ hasText: /aplicada/i })).toHaveCount(1);
  await expect(linhas.filter({ hasText: /descartada/i })).toHaveCount(1);
  await page.screenshot({ path: `${SHOTS}/008-registro.png`, fullPage: true });

  // Resumo: a soma do mês bate com o registro inteiro
  const resumo = await getJson<{ chamadas: number; custoUsd: number; porPerfil: { perfil: { id: string }; chamadas: number }[] }>(
    request, auth, "/api/ia/resumo",
  );
  expect(resumo.porPerfil.find((p) => p.perfil.id === perfilId)?.chamadas).toBe(5);
  expect(resumo.custoUsd).toBeGreaterThan(0);
  await tab(page, "Resumo do mês").click();
  await expect(page.getByText("Custo aproximado")).toBeVisible();
  await expect(page.getByRole("table", { name: "Gasto por perfil" }).getByText(perfilName)).toBeVisible();
  await expect(page.getByText(/US\$/).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/008-resumo.png`, fullPage: true });
});
