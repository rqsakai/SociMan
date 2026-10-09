import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { BASE_URL, OWNER } from "./fixtures";
import {
  apiToken,
  chamarTool,
  createPerfilViaApi,
  createVerifiedMember,
  criarClienteMcp,
  interruptorMcp,
  login,
  logout,
  nav,
  pngBuffer,
  syntheticMp4,
} from "./helpers";

// Spec 010 (T020, T027, T034, T039, T044): cenas para o Flow/Veo.
// - US1: criar a cena pela tela; o prompt começa pela descrição do avatar (idêntica); "Copiar prompt"
//   copia o texto exato; 3 ingredientes; aviso de fala longa;
// - US2: pronta congela o prompt; mudar o avatar mostra o aviso e "Remontar"; editar a ação volta a
//   rascunho; duplicar, filtrar e arquivar; o membro não vê "Reverter";
// - US3: tomada sintética enviada e escolhida; vídeo próprio liga a cena (usada); a cena usada só
//   muda por "Duplicar"; tirar o vínculo volta a pronta;
// - US4: "Melhorar com IA" na ação com o Claude falso; "Ajustar cena com IA" mantém o avatar;
// - US5: proposta de cena gravada pelo MCP → Aceitar → Salvar → cena em rascunho e proposta aplicada.

type Auth = { Authorization: string };

const DESCRICAO = "A cheerful 1950s pin-up style woman with red curly hair, pink apron, warm smile.";
const AMBIENTE = "Retro 1950s kitchen with mint cabinets and checkered floor";
const ACAO = "lifts the lid and steam comes out";
const FALA = "Gente, olha essa panela!";
const FALA_LONGA = "Gente olha essa panela que eu achei hoje cedo e que cozinha arroz feijão e carne em vinte minutos sem sujeira";

// As respostas da API vêm embrulhadas (`{ cena }`) ou não; aceita as duas formas.
async function json<T>(res: Awaited<ReturnType<APIRequestContext["get"]>>, chave: string): Promise<T> {
  const body = (await res.json()) as Record<string, unknown>;
  return (body[chave] ?? body) as T;
}

interface Asset {
  id: string;
  version: number;
}

// Perfil com o avatar Achadinhos (descrição + look), o cenário Cozinha retrô (prompt + imagem) e a
// foto de um produto, tudo pela API.
async function cenario(request: APIRequestContext, token: string, sfx: string) {
  const auth: Auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Cenas ${sfx}`, slug: `cenas-${sfx}` });
  const img = pngBuffer(540, 540);

  const av = await request.post(`/api/perfis/${perfilId}/assets`, {
    headers: auth,
    data: { tipo: "avatar", name: "Achadinhos", tags: [], prompt: DESCRICAO, imageRules: "Always the pink apron" },
  });
  expect(av.status(), `avatar: ${await av.text()}`).toBe(201);
  const avatar = await json<Asset>(av, "asset");
  const look = await request.post(`/api/assets/${avatar.id}/arquivos`, {
    headers: auth,
    multipart: { role: "referencia", look: "Cozinha, corpo inteiro", file: { name: "look.png", mimeType: "image/png", buffer: img } },
  });
  expect(look.status(), `look: ${await look.text()}`).toBe(201);

  const ce = await request.post(`/api/perfis/${perfilId}/assets`, { headers: auth, data: { tipo: "cenario", name: "Cozinha retrô", tags: [], prompt: AMBIENTE } });
  expect(ce.status(), `cenário: ${await ce.text()}`).toBe(201);
  const cen = await json<Asset>(ce, "asset");
  const cenImg = await request.post(`/api/assets/${cen.id}/arquivos`, {
    headers: auth,
    multipart: { role: "referencia", file: { name: "cozinha.png", mimeType: "image/png", buffer: img } },
  });
  expect(cenImg.status(), `imagem do cenário: ${await cenImg.text()}`).toBe(201);

  const pr = await request.post(`/api/perfis/${perfilId}/assets/arquivo`, {
    headers: auth,
    multipart: { tipo: "imagem", name: "Foto panela", tags: "", file: { name: "panela.png", mimeType: "image/png", buffer: img } },
  });
  expect(pr.status(), `produto: ${await pr.text()}`).toBe(201);
  const produto = await json<Asset>(pr, "asset");
  return { perfilId, avatarId: avatar.id, cenarioId: cen.id, produtoId: produto.id };
}

interface CenaApi {
  id: string;
  version: number;
  status: string;
}

async function criarCenaApi(request: APIRequestContext, auth: Auth, perfilId: string, corpo: Record<string, unknown>): Promise<CenaApi> {
  const res = await request.post(`/api/perfis/${perfilId}/cenas`, { headers: auth, data: corpo });
  expect(res.status(), `POST cenas: ${await res.text()}`).toBe(201);
  return json<CenaApi>(res, "cena");
}

async function cenaApi(request: APIRequestContext, auth: Auth, id: string): Promise<CenaApi> {
  const res = await request.get(`/api/cenas/${id}`, { headers: auth });
  expect(res.status(), `GET cena: ${await res.text()}`).toBe(200);
  return json<CenaApi>(res, "cena");
}

async function prontaApi(request: APIRequestContext, auth: Auth, id: string): Promise<void> {
  const c = await cenaApi(request, auth, id);
  const res = await request.post(`/api/cenas/${id}/pronta`, { headers: auth, data: { version: c.version } });
  expect(res.status(), `pronta: ${await res.text()}`).toBe(200);
}

function status(page: Page) {
  return page.getByTestId("cena-status");
}

test("US1 e US2: montar a cena, copiar o prompt, pronta, mudou/remontar, rascunho, duplicar, filtrar e arquivar", async ({ page, request, context }) => {
  test.setTimeout(240_000);
  const sfx = randomUUID().slice(0, 6);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const { perfilId, avatarId } = await cenario(request, token, sfx);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  // spec 029: AI Studio › Cenas, filtrada pelo perfil; a cena nova nasce com ele como perfil base
  await nav(page, "Cenas");
  await expect(page).toHaveURL(/\/app\/estudio\/cenas$/);
  await page.getByTestId("filtro-perfil-base").selectOption(perfilId);
  await expect(page).toHaveURL(new RegExp(`perfil=${perfilId}`));
  await page.getByRole("link", { name: "Nova cena" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/estudio/cenas/nova\\?perfil=${perfilId}$`));
  await expect(page.getByTestId("perfil-base")).toHaveValue(perfilId);

  await page.getByLabel("Nome da cena").fill("Achadinhos abre a panela");
  // as opções dos seletores são "Nome · Perfil" (a biblioteca é da agência)
  await page.getByLabel("Avatar", { exact: true }).selectOption({ label: `Achadinhos · Cenas ${sfx}` });
  await page.getByLabel("Look ou pose").selectOption({ label: "Referência: Cozinha, corpo inteiro" });
  await page.getByLabel("Cenário", { exact: true }).selectOption({ label: `Cozinha retrô · Cenas ${sfx}` });
  await page.getByLabel("Plano").selectOption("medio");
  await page.getByLabel("Movimento").selectOption("parada");
  await page.getByLabel("Ação", { exact: true }).fill(ACAO);
  await page.getByLabel("Fala para a câmera").fill(FALA_LONGA);
  await page.getByLabel("Produto", { exact: true }).fill("Panela elétrica");
  await page.getByRole("button", { name: "Abrir biblioteca" }).click();
  await page.getByRole("button", { name: "Escolher Foto panela" }).click();
  await expect(page.getByTestId("produto-foto")).toContainText("Foto panela");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();

  await expect(page).toHaveURL(/\/app\/cenas\/[0-9a-f-]{36}$/);
  await expect(status(page)).toHaveText("Rascunho");
  const cenaId = page.url().split("/").pop()!;

  // Prompt: começa pela descrição do avatar, idêntica; a fala longa dá aviso (não bloqueia)
  const prompt = page.getByTestId("prompt-texto");
  await expect(prompt).toContainText(ACAO);
  expect((await prompt.textContent())!.startsWith(DESCRICAO)).toBe(true);
  await expect(page.getByRole("list", { name: "Avisos da cena" })).toContainText(/[Ff]ala longa/);
  await expect(page.getByRole("list", { name: "Ingredientes" }).getByRole("listitem")).toHaveCount(3);
  await expect(page.getByRole("link", { name: /^Baixar avatar/ })).toBeVisible();

  // Fala curta: o aviso some e o prompt traz a fala entre aspas com verbo de fala
  await page.getByLabel("Fala para a câmera").fill(FALA);
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Alterações salvas.").first()).toBeVisible();
  await expect(prompt).toContainText(`says: "${FALA}"`);
  await expect(page.getByRole("list", { name: "Avisos da cena" })).toHaveCount(0);

  // "Copiar prompt": o texto exato
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE_URL });
  const textoPrompt = (await prompt.textContent())!;
  await page.getByRole("button", { name: "Copiar prompt" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Prompt copiado" })).toHaveCount(1);
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(textoPrompt);
  await page.screenshot({ path: ".playwright-mcp/sociman/010-cena.png", fullPage: true });

  // Pronta: congela o prompt
  await page.getByRole("button", { name: "Marcar como pronta" }).click();
  await expect(status(page)).toHaveText("Pronta");
  await expect(page.getByText("congelado", { exact: true })).toBeVisible();

  // O avatar muda pela API → aviso com a diferença; o prompt continua o antigo; Remontar recongela
  const av = await json<Asset>(await request.get(`/api/assets/${avatarId}`, { headers: auth }), "asset");
  const patch = await request.patch(`/api/assets/${avatarId}`, { headers: auth, data: { version: av.version, prompt: `${DESCRICAO} Freckles.` } });
  expect(patch.status(), `PATCH avatar: ${await patch.text()}`).toBe(200);
  await page.reload();
  const mudou = page.getByRole("region", { name: "O avatar ou o cenário mudou" });
  await expect(mudou).toBeVisible();
  expect((await prompt.textContent())!.startsWith(`${DESCRICAO} Freckles.`)).toBe(false);
  await mudou.getByRole("button", { name: "Remontar prompt" }).click();
  await expect(mudou).toHaveCount(0);
  await expect(status(page)).toHaveText("Pronta");
  expect((await prompt.textContent())!.startsWith(`${DESCRICAO} Freckles.`)).toBe(true);

  // Editar a ação numa cena pronta: volta a rascunho
  await page.getByLabel("Ação", { exact: true }).fill(`${ACAO} slowly`);
  await expect(page.getByText("Salvar esta mudança volta a cena para rascunho")).toBeVisible();
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(status(page)).toHaveText("Rascunho");

  // Duplicar: nova cena em rascunho, "(cópia)"
  await page.getByRole("button", { name: "Duplicar" }).click();
  await expect(page).not.toHaveURL(new RegExp(cenaId));
  await expect(page.getByRole("heading", { level: 1 })).toContainText("(cópia)");
  await expect(status(page)).toHaveText("Rascunho");
  const copiaId = page.url().split("/").pop()!;

  // Arquivar a cópia
  await page.getByRole("button", { name: "Arquivar" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Arquivar" }).click();
  await expect(page.getByText("Arquivada", { exact: true }).first()).toBeVisible();

  // Lista (AI Studio › Cenas do perfil): a original pronta de novo; filtro por status e a arquivada fora
  await prontaApi(request, auth, cenaId);
  await page.goto(`/app/estudio/cenas?perfil=${perfilId}`);
  const tabela = page.getByRole("table", { name: "Cenas", exact: true });
  await expect(tabela.getByRole("link", { name: "Achadinhos abre a panela", exact: true })).toBeVisible();
  await expect(tabela.getByRole("link", { name: /\(cópia\)/ })).toHaveCount(0);
  // spec 024: os filtros valem ao escolher (sem "Filtrar"), viram etiquetas e ficam na URL
  await page.getByLabel("Status", { exact: true }).selectOption("rascunho");
  await expect(tabela.getByText("Nenhuma cena com esses filtros", { exact: false }).or(page.getByText("Nenhuma cena com esses filtros", { exact: false }))).toBeVisible();
  await page.getByLabel("Status", { exact: true }).selectOption("pronta");
  // o filtro de avatar lista os da agência inteira (vários "Achadinhos"): escolhe pelo id
  await page.getByLabel("Avatar", { exact: true }).selectOption(avatarId);
  await expect(page).toHaveURL(/status=pronta/);
  await expect(page.getByRole("button", { name: "Remover filtro: Avatar" })).toBeVisible();
  await expect(tabela.getByRole("link", { name: "Achadinhos abre a panela", exact: true })).toBeVisible();
  await page.getByLabel("Mostrar arquivadas").click();
  await page.getByRole("button", { name: "Remover filtro: Status" }).click();
  await expect(tabela.getByRole("link", { name: /\(cópia\)/ })).toBeVisible();

  // 390 px sem rolagem horizontal na cena
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/app/cenas/${cenaId}`);
  await expect(status(page)).toHaveText("Pronta");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.goto(`/app/estudio/cenas?perfil=${perfilId}`);
  await expect(page.getByRole("table", { name: "Cenas", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  // Histórico: o dono vê "Reverter"
  await page.goto(`/app/cenas/${copiaId}/historico`);
  await expect(page.getByRole("button", { name: /Reverter/ }).first()).toBeVisible();
  await logout(page);

  // O membro não vê "Reverter"
  const membro = await createVerifiedMember(page);
  await login(page, membro.email, membro.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/cenas/${copiaId}/historico`);
  await expect(page.getByRole("heading", { name: /Histórico de/ })).toBeVisible();
  await expect(page.getByText("Criado").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Reverter/ })).toHaveCount(0);
});

test("US3: tomadas, escolher, ligar ao vídeo próprio (usada) e desligar (pronta)", async ({ page, request }) => {
  test.setTimeout(240_000);
  const sfx = randomUUID().slice(0, 6);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const { perfilId, avatarId, cenarioId } = await cenario(request, token, sfx);
  const cena = await criarCenaApi(request, auth, perfilId, { nome: `Abertura ${sfx}`, acao: ACAO, fala: FALA, avatarId, cenarioId });

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/cenas/${cena.id}`);
  // Rascunho não recebe tomada
  await expect(page.getByText("Marque a cena como pronta antes de enviar tomadas", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Marcar como pronta" }).click();
  await expect(status(page)).toHaveText("Pronta");

  const t1 = join(tmpdir(), `sociman-e2e-tomada1-${sfx}.mp4`);
  const t2 = join(tmpdir(), `sociman-e2e-tomada2-${sfx}.mp4`);
  syntheticMp4(t1, 2);
  syntheticMp4(t2, 3, "960x540");
  await page.getByLabel("Nova tomada").setInputFiles(t1);
  await page.getByRole("button", { name: "Enviar tomada" }).click();
  const tomadas = page.getByRole("list", { name: "Tomadas" });
  await expect(tomadas.getByRole("article")).toHaveCount(1);
  await expect(tomadas.getByRole("article").first().getByText("Escolhida")).toBeVisible();
  await page.getByLabel("Nova tomada").setInputFiles(t2);
  await page.getByRole("button", { name: "Enviar tomada" }).click();
  await expect(tomadas.getByRole("article")).toHaveCount(2);
  const segunda = tomadas.getByRole("article", { name: "Tomada 2" });
  await expect(segunda.getByText("não é vertical")).toBeVisible();
  await segunda.getByRole("button", { name: "Escolher" }).click();
  await expect(segunda.getByText("Escolhida")).toBeVisible();
  await expect(tomadas.getByRole("article", { name: "Tomada 1" }).getByText("Escolhida")).toHaveCount(0);

  // Vídeo próprio (014) pela API, e o vínculo pela tela do conteúdo
  const arquivo = join(tmpdir(), `sociman-e2e-video-cenas-${sfx}.mp4`);
  syntheticMp4(arquivo, 4);
  const up = await request.post(`/api/perfis/${perfilId}/conteudos/arquivo`, {
    headers: auth,
    multipart: { file: { name: "final.mp4", mimeType: "video/mp4", buffer: readFileSync(arquivo) }, titulo: `Final ${sfx}` },
  });
  expect(up.status(), `vídeo próprio: ${await up.text()}`).toBe(201);
  const conteudoId = ((await up.json()) as { conteudo: { id: string } }).conteudo.id;
  await page.goto(`/app/conteudos/${conteudoId}`);
  await page.getByRole("button", { name: "Escolher cenas" }).click();
  const dialogo = page.getByRole("dialog", { name: "Cenas deste vídeo" });
  await dialogo.getByRole("checkbox", { name: `Abertura ${sfx}` }).click();
  await dialogo.getByRole("button", { name: "Salvar cenas" }).click();
  await expect(page.getByRole("list", { name: "Cenas do vídeo" }).getByRole("link", { name: `Abertura ${sfx}` })).toBeVisible();

  // A cena virou usada, com "Usada em"; o prompt só muda duplicando
  await page.goto(`/app/cenas/${cena.id}`);
  await expect(status(page)).toHaveText("Usada");
  await expect(page.getByRole("link", { name: `Final ${sfx}` })).toBeVisible();
  await expect(page.getByText("Para variar o prompt, duplique a cena.")).toBeVisible();
  await expect(page.getByLabel("Ação", { exact: true })).toBeDisabled();
  // A API também recusa (409 cena_usada)
  const atual = await cenaApi(request, auth, cena.id);
  const recusa = await request.patch(`/api/cenas/${cena.id}`, { headers: auth, data: { version: atual.version, acao: "waves" } });
  expect(recusa.status()).toBe(409);

  // Desligar no conteúdo → pronta
  await page.goto(`/app/conteudos/${conteudoId}`);
  await page.getByRole("button", { name: "Escolher cenas" }).click();
  await dialogo.getByRole("checkbox", { name: `Abertura ${sfx}` }).click();
  await dialogo.getByRole("button", { name: "Salvar cenas" }).click();
  await expect(page.getByText("Nenhuma cena ligada.")).toBeVisible();
  await page.goto(`/app/cenas/${cena.id}`);
  await expect(status(page)).toHaveText("Pronta");
});

test("US4: IA na ação (selo no histórico) e Ajustar cena com IA mantém a descrição do avatar", async ({ page, request }) => {
  test.setTimeout(180_000);
  const sfx = randomUUID().slice(0, 6);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const { perfilId, avatarId, cenarioId } = await cenario(request, token, sfx);
  const cena = await criarCenaApi(request, auth, perfilId, { nome: `IA ${sfx}`, acao: ACAO, fala: FALA, avatarId, cenarioId });

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/cenas/${cena.id}`);

  // "Melhorar com IA" na ação → Aplicar salva só o campo
  await page.getByTestId("ia-botao-cena.acao").click();
  const painel = page.getByTestId("ia-painel-cena.acao");
  await painel.getByRole("button", { name: "Gerar", exact: true }).click();
  await expect(painel.getByText(/Claude falso do e2e/)).toBeVisible({ timeout: 25_000 });
  await painel.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByText("Salvo com ajuda da IA.").first()).toBeVisible();
  await expect(page.getByLabel("Ação", { exact: true })).toHaveValue(/Texto sugerido pela IA/);

  // "Ajustar cena com IA": os 4 campos mudam; o prompt continua começando pela descrição do avatar
  await page.getByTestId("ia-botao-cena.ajustar").click();
  const ajuste = page.getByTestId("ia-painel-cena.ajustar");
  await ajuste.getByLabel("Como a IA deve ajustar? (opcional)").fill("mais close no produto");
  await ajuste.getByRole("button", { name: "Gerar", exact: true }).click();
  await expect(ajuste.getByText(/Claude falso do e2e/)).toBeVisible({ timeout: 25_000 });
  await ajuste.getByRole("button", { name: "Aplicar", exact: true }).click();
  await expect(page.getByLabel("Ação", { exact: true })).toHaveValue(/lifts the lid slowly and smiles/);
  await expect(page.getByLabel("Áudio e ambiente")).toHaveValue("gentle kitchen ambience");
  const prompt = page.getByTestId("prompt-texto");
  await expect(prompt).toContainText("lifts the lid slowly and smiles");
  expect((await prompt.textContent())!.startsWith(DESCRICAO)).toBe(true);

  // O histórico mostra o selo
  await page.goto(`/app/cenas/${cena.id}/historico`);
  await expect(page.getByText("com ajuda da IA").first()).toBeVisible();
});

test("US5: proposta de cena do agente → Aceitar → Salvar → cena em rascunho e proposta aplicada", async ({ page, request }) => {
  test.setTimeout(180_000);
  const sfx = randomUUID().slice(0, 6);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  await interruptorMcp(request, token, true);
  const { perfilId, avatarId, cenarioId } = await cenario(request, token, sfx);
  const agente = await criarClienteMcp(request, token, `Diretor ${sfx}`, "propostas");

  const nome = `Proposta panela ${sfx}`;
  const r = await chamarTool(agente.token, "anotacoes_create", {
    alvoTipo: "perfil",
    alvoId: perfilId,
    tipo: "proposta_cena",
    texto: "Abertura com a Achadinhos levantando a tampa.",
    campos: { nome, avatarId, cenarioId, acao: ACAO, fala: FALA, duracaoS: 8, modo: "ingredientes" },
  });
  expect(r.status, "tools/call").toBe(200);
  const res = r.body?.result as { isError?: boolean; structuredContent?: unknown };
  expect(res.isError, JSON.stringify(res.structuredContent)).toBeFalsy();

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/propostas");
  const linha = page.getByRole("row").filter({ hasText: "Abertura com a Achadinhos" });
  await expect(linha.getByText(`Agente: Diretor ${sfx}`)).toBeVisible();
  await linha.getByRole("link", { name: "Aceitar" }).click();
  await expect(page).toHaveURL(/\/app\/estudio\/cenas\/nova\?(.*&)?proposta=/);
  await expect(page.getByRole("region", { name: "Proposta do agente" })).toContainText(`Diretor ${sfx}`);
  await expect(page.getByLabel("Nome da cena")).toHaveValue(nome);
  await expect(page.getByLabel("Ação", { exact: true })).toHaveValue(ACAO);
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/cenas\/[0-9a-f-]{36}$/);
  await expect(status(page)).toHaveText("Rascunho");

  await page.goto(`/app/estudio/cenas?perfil=${perfilId}`);
  await expect(page.getByRole("table", { name: "Cenas", exact: true }).getByRole("link", { name: nome })).toBeVisible();
  await page.goto("/app/propostas");
  await page.getByLabel("Situação", { exact: true }).selectOption("aplicada");
  await expect(page.getByRole("row").filter({ hasText: "Abertura com a Achadinhos" }).getByText("Aplicada")).toBeVisible();
});
