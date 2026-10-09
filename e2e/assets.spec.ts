import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { BASE_URL, OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, login, nav, pngAlphaBuffer, pngBuffer } from "./helpers";

// Biblioteca de assets (spec 007), aberta pelo AI Studio (spec 029): avatares, cenários e os assets
// de arquivo único têm cada um a sua página. Cada teste cria o próprio perfil pela API e filtra a
// lista por ele (a biblioteca é da agência inteira).

function tab(page: Page, name: string): Locator {
  return page.getByRole("tab", { name, exact: true });
}

function section(page: Page, name: string): Locator {
  return page.getByRole("region", { name, exact: true });
}

// Formulário de envio do detalhe do asset (Looks, Poses ou referências), pelo botão de envio.
function uploadForm(page: Page, submit: string): Locator {
  return page.locator("form").filter({ has: page.getByRole("button", { name: submit, exact: true }) });
}

type PaginaEstudio = "avatares" | "cenarios" | "assets";
const TITULO: Record<PaginaEstudio, string> = { avatares: "Avatares", cenarios: "Cenários", assets: "Assets" };

// AI Studio › <tipo>, com o filtro "Perfil base" no perfil do teste.
async function openEstudio(page: Page, pagina: PaginaEstudio, perfilId: string): Promise<void> {
  await page.goto(`/app/estudio/${pagina}?perfil=${perfilId}`);
  await expect(page.getByRole("heading", { level: 1, name: TITULO[pagina] })).toBeVisible();
  await expect(page.getByText("Biblioteca da agência")).toBeVisible();
}

// A grade da página (o rótulo é o nome do tipo).
function grade(page: Page, pagina: PaginaEstudio): Locator {
  return page.getByRole("list", { name: TITULO[pagina], exact: true });
}

// "Novo avatar"/"Novo cenário": nome, perfil base (o do filtro) e "Criar"; cai no detalhe.
async function createNamedAsset(page: Page, tipo: "Avatar" | "Cenário", name: string, perfilId: string): Promise<void> {
  await page.getByRole("button", { name: tipo === "Avatar" ? "Novo avatar" : "Novo cenário", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Nome").fill(name);
  await expect(dialog.getByTestId("perfil-base")).toHaveValue(perfilId);
  await dialog.getByRole("button", { name: "Criar" }).click();
  await expect(page).toHaveURL(/\/app\/assets\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
}

// "Novo asset" → tipo de um arquivo só: abre o seletor de arquivos (vários de uma vez).
async function uploadSingleFiles(
  page: Page,
  tipo: "Fundo" | "Sticker" | "Marca d'água" | "Imagem",
  files: { name: string; mimeType: string; buffer: Buffer }[],
): Promise<void> {
  await page.getByRole("button", { name: "Novo asset" }).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("menuitem", { name: tipo, exact: true }).click();
  await (await chooser).setFiles(files);
}

async function libraryImageId(request: APIRequestContext, token: string, perfilId: string, tipo: string, name: string) {
  const res = await request.get(`/api/perfis/${perfilId}/assets/imagens?tipo=${tipo}`, { headers: { Authorization: `Bearer ${token}` } });
  expect(res.status()).toBe(200);
  const { items } = (await res.json()) as { items: { assetName: string; assetId: string; image: { id: string } }[] };
  const item = items.find((i) => i.assetName === name);
  expect(item, `imagem de "${name}" na biblioteca`).toBeDefined();
  return item!;
}

// Texto com aspas, acentos e quebras de linha: a cópia tem de ser idêntica ao salvo (FR-009).
const DESCRICAO = [
  "A cheerful 1950s pin-up style woman with voluminous red victory-roll hair, bright red lipstick,",
  'polka-dot dress (red with white dots) and a white apron; warm smile, "Achadinhos" persona.',
  "Estilo: ilustração retrô, cores pastel, luz suave.",
].join("\n");

// US1 (T022): avatar "Achadinhos" com descrição, 2 looks e 3 poses; 4ª pose com rótulo repetido
// recusada; reordenar com os botões e recarregar; copiar a descrição; avatar sem imagem com
// iniciais.
test("avatar com looks e poses, reordenação e cópia da descrição", async ({ page, request, context }) => {
  test.setTimeout(180_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Assets E2E ${sfx}`, slug: `assets-e2e-${sfx}` });

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  // entra pelo menu (AI Studio › Avatares) e filtra pelo perfil base
  await nav(page, "Avatares");
  await expect(page).toHaveURL(/\/app\/estudio\/avatares$/);
  await page.getByTestId("filtro-perfil-base").selectOption(perfilId);
  await expect(page).toHaveURL(new RegExp(`perfil=${perfilId}`));
  await expect(page.getByText(/Nenhum item com o perfil base .+ ainda\./)).toBeVisible();  // 029: só o filtro de perfil

  await createNamedAsset(page, "Avatar", "Achadinhos", perfilId);
  await page.getByLabel("Tags").fill("persona, tiktok-shop");
  await page.getByLabel("Descrição para prompts").fill(DESCRICAO);
  await page.getByLabel("Tom de voz").fill("Animado, próximo, 'amiga que achou uma pechincha'. Português do Brasil.");
  await page.getByLabel("Regras de imagem").fill("Evitar textos em inglês no fundo (cartazes).");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Alterações salvas.")).toBeVisible();
  await expect(page.getByText("#tiktok-shop")).toBeVisible();

  // Looks: duas referências 1080×1080, cada uma com look e uso
  const looks = uploadForm(page, "Enviar referência");
  for (const [file, look, uso] of [
    ["achadinhos-cozinha.png", "Cozinha, corpo inteiro", "cenas de cozinha"],
    ["achadinhos-diner.png", "Diner, busto", "cenas de fala em close"],
  ] as const) {
    await looks.getByLabel("Imagem").setInputFiles({ name: file, mimeType: "image/png", buffer: pngBuffer(1080, 1080) });
    await looks.getByLabel("Look").fill(look);
    await looks.getByLabel("Uso").fill(uso);
    await looks.getByRole("button", { name: "Enviar referência" }).click();
    await expect(page.getByRole("listitem", { name: `Imagem ${look}` })).toBeVisible({ timeout: 15_000 });
  }
  await expect(page.getByRole("region", { name: "Look Cozinha, corpo inteiro" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Look Diner, busto" })).toBeVisible();
  // a primeira referência é a principal; marcar a outra troca o selo
  const cozinha = page.getByRole("listitem", { name: "Imagem Cozinha, corpo inteiro" });
  const diner = page.getByRole("listitem", { name: "Imagem Diner, busto" });
  await expect(cozinha.getByText("Principal", { exact: true })).toBeVisible();
  await diner.getByRole("button", { name: "Marcar como principal" }).click();
  await expect(diner.getByText("Principal", { exact: true })).toBeVisible();
  await expect(cozinha.getByText("Principal", { exact: true })).toBeHidden();

  // Poses: três, com rótulo e "quando usar"
  const poses = uploadForm(page, "Enviar pose");
  for (const [label, quando] of [
    ["apontando para o produto", "mostrar o item na mão"],
    ["surpresa", "reação ao preço"],
    ["piscando", "fechamento"],
  ] as const) {
    await poses.getByLabel("Imagem").setInputFiles({ name: `${label}.png`, mimeType: "image/png", buffer: pngBuffer(512, 512) });
    await poses.getByLabel("Rótulo da pose").fill(label);
    await poses.getByLabel("Quando usar").fill(quando);
    await poses.getByRole("button", { name: "Enviar pose" }).click();
    await expect(page.getByRole("listitem", { name: `Pose ${label}` })).toBeVisible({ timeout: 15_000 });
  }

  // 4ª pose com o rótulo "Surpresa" (repetido, outra caixa): recusada
  await poses.getByLabel("Imagem").setInputFiles({ name: "surpresa2.png", mimeType: "image/png", buffer: pngBuffer(512, 512) });
  await poses.getByLabel("Rótulo da pose").fill("Surpresa");
  await poses.getByRole("button", { name: "Enviar pose" }).click();
  await expect(page.getByText("Já existe uma pose com esse rótulo neste avatar")).toBeVisible();
  const lista = page.getByRole("list", { name: "Poses" }).getByRole("listitem");
  await expect(lista).toHaveCount(3);

  // Texto digitado e ainda não salvo sobrevive às outras mutações (cada uma gera versão nova):
  // "piscando" para o início com os botões (uma versão por movimento), com as notas pendentes
  const NOTAS = "Notas digitadas antes de reordenar, ainda sem salvar.";
  const notas = page.getByLabel("Notas");
  await notas.fill(NOTAS);
  await page.getByRole("button", { name: "Mover piscando para a esquerda" }).click();
  await expect(lista.nth(1)).toHaveAccessibleName("Pose piscando");
  await expect(notas).toHaveValue(NOTAS);
  await page.getByRole("button", { name: "Mover piscando para a esquerda" }).click();
  await expect(lista.nth(0)).toHaveAccessibleName("Pose piscando");
  await expect(notas).toHaveValue(NOTAS);
  // Salvar depois das reordenações usa a versão nova (sem 409) e persiste
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Alterações salvas.").first()).toBeVisible();
  await page.reload();
  await expect(notas).toHaveValue(NOTAS);
  await expect(lista.nth(0)).toHaveAccessibleName("Pose piscando");
  await expect(lista.nth(1)).toHaveAccessibleName("Pose apontando para o produto");
  await expect(lista.nth(2)).toHaveAccessibleName("Pose surpresa");
  await page.screenshot({ path: ".playwright-mcp/sociman/007-avatar.png", fullPage: true });

  // "Copiar descrição para prompt": o texto na área de transferência é idêntico ao salvo
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE_URL });
  await page.getByRole("button", { name: "Copiar descrição para prompt" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Copiado" })).toHaveCount(1);
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(DESCRICAO);

  // Histórico: uma versão por ação
  await page.getByRole("link", { name: "Histórico" }).click();
  await expect(page).toHaveURL(/\/historico$/);
  await expect(page.getByText("Reverter").first()).toBeVisible();

  // Avatar sem imagem: iniciais "TE" no card (primeira e última palavra, como no perfil)
  await openEstudio(page, "avatares", perfilId);
  await createNamedAsset(page, "Avatar", "Teste Estrela", perfilId);
  await openEstudio(page, "avatares", perfilId);
  const avatares = grade(page, "avatares");
  await expect(avatares.getByRole("link", { name: "Teste Estrela (Avatar)" }).getByTestId("asset-initials")).toHaveText("TE");
  await expect(avatares.getByRole("link", { name: "Achadinhos (Avatar)" }).locator("img")).toBeVisible();
  await page.screenshot({ path: ".playwright-mcp/sociman/007-biblioteca.png", fullPage: true });
});

// US2 e US4 (T029, T038): cenário "Cozinha retrô" escolhido como fundo do card final pelo
// "Abrir biblioteca"; o envio pelo seletor cria um "Fundo"; arquivar o cenário em uso no kit é
// recusado; trocado o fundo, arquiva; "Mostrar arquivados" e "Restaurar"; "Copiar link" abre sem
// sessão.
test("cenário como fundo do kit, arquivar bloqueado pelo kit, restaurar e link público", async ({ page, request, context, browser }) => {
  test.setTimeout(180_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Cenario E2E ${sfx}`, slug: `cenario-e2e-${sfx}` });
  const auth = { Authorization: `Bearer ${token}` };

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await openEstudio(page, "cenarios", perfilId);
  await createNamedAsset(page, "Cenário", "Cozinha retrô", perfilId);
  await page.getByLabel("Tags").fill("cozinha");
  await page.getByLabel("Prompt do ambiente").fill("1950s kitchen with mint-green countertops, wooden cabinets, copper pots hanging.");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Alterações salvas.")).toBeVisible();
  const refs = uploadForm(page, "Enviar referência");
  await refs.getByLabel("Imagem").setInputFiles({ name: "cozinha.png", mimeType: "image/png", buffer: pngBuffer(1080, 1080) });
  await refs.getByLabel("Uso").fill("fundo do card final");
  await refs.getByRole("button", { name: "Enviar referência" }).click();
  await expect(page.getByRole("list", { name: "Referências" }).getByRole("listitem")).toHaveCount(1, { timeout: 15_000 });
  const cenarioUrl = page.url();

  // Aba Marca → Card final → fundo Imagem: o seletor lista o cenário da biblioteca
  await page.goto(`/app/perfis/${perfilId}`);
  await tab(page, "Marca").click();
  const card = section(page, "Card final");
  await card.getByRole("switch", { name: "Ligado" }).click();
  await card.getByLabel("Tipo de fundo", { exact: true }).selectOption({ label: "Imagem" });
  await expect(card.getByRole("radio", { name: "Cozinha retrô", exact: true })).toBeVisible();

  // "Enviar imagem de fundo" no seletor: vira um "Fundo" na biblioteca e fica escolhido
  await card.locator('input[type="file"]').setInputFiles({ name: "fundo-novo.png", mimeType: "image/png", buffer: pngBuffer(1080, 1920) });
  await expect(card.getByRole("radio", { name: "fundo-novo", exact: true })).toHaveAttribute("aria-checked", "true", { timeout: 15_000 });

  // "Abrir biblioteca", busca "cozinha", escolhe a referência do cenário
  await card.getByRole("button", { name: "Abrir biblioteca" }).click();
  const biblioteca = page.getByRole("dialog", { name: "Biblioteca da agência" });
  await expect(biblioteca.getByRole("button", { name: "Escolher fundo-novo" })).toBeVisible();
  await biblioteca.getByLabel("Buscar na biblioteca").fill("cozinha");
  await expect(biblioteca.getByRole("button", { name: "Escolher fundo-novo" })).toBeHidden();
  await page.screenshot({ path: ".playwright-mcp/sociman/007-abrir-biblioteca.png" });
  await biblioteca.getByRole("button", { name: "Escolher Cozinha retrô" }).click();
  await expect(biblioteca).toBeHidden();
  await expect(card.getByRole("radio", { name: "Cozinha retrô", exact: true })).toHaveAttribute("aria-checked", "true");

  await page.getByRole("button", { name: "Fim (card final)" }).click();
  const previewCard = page.locator('[data-preview="card"]');
  await expect(previewCard).toHaveAttribute("data-fundo", "imagem");
  await expect.poll(() => previewCard.evaluate((el) => getComputedStyle(el).backgroundImage)).toContain("url(");
  await page.getByRole("button", { name: "Salvar kit" }).click();
  await expect(page.getByText("Kit salvo.")).toBeVisible();
  await expect(page.getByText("Versão 1", { exact: true })).toBeVisible();
  await page.screenshot({ path: ".playwright-mcp/sociman/007-marca-seletor.png", fullPage: true });

  const cozinha = await libraryImageId(request, token, perfilId, "cenario", "Cozinha retrô");
  const kitRes = await request.get(`/api/perfis/${perfilId}/kit`, { headers: auth });
  const { kit } = (await kitRes.json()) as { kit: { endCard: { fundo_imagem_id: string | null } } };
  expect(kit.endCard.fundo_imagem_id).toBe(cozinha.image.id);

  // O "Fundo" enviado pelo seletor está na biblioteca (Assets); o cenário, em Cenários, "Em uso"
  await openEstudio(page, "assets", perfilId);
  await expect(grade(page, "assets").getByRole("link", { name: "fundo-novo (Fundo)" })).toBeVisible();
  await openEstudio(page, "cenarios", perfilId);
  await expect(grade(page, "cenarios").getByRole("link", { name: "Cozinha retrô (Cenário)" }).getByText("Em uso")).toBeVisible();

  // Arquivar o cenário em uso no card final: recusado, com o uso
  await page.goto(cenarioUrl);
  await expect(page.getByRole("list", { name: "Onde é usado" }).getByText("Card final (kit v1)")).toBeVisible();
  await page.getByRole("button", { name: "Arquivar", exact: true }).first().click();
  const confirm = page.getByRole("alertdialog");
  await expect(confirm).toContainText("Card final (kit v1)");
  await confirm.getByRole("button", { name: "Arquivar" }).click();
  await expect(page.getByText(/Em uso em: Card final \(kit v1\)/).first()).toBeVisible();
  await page.screenshot({ path: ".playwright-mcp/sociman/007-arquivar-bloqueado.png", fullPage: true });

  // "Copiar link" da referência: abre numa sessão sem login
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE_URL });
  const ref = page.getByRole("list", { name: "Referências" }).getByRole("listitem").first();
  await ref.getByRole("button", { name: "Copiar link" }).click();
  const link = await page.evaluate(() => navigator.clipboard.readText());
  expect(link).toMatch(/\/api\/midia\//);
  const anon = await browser.newContext();
  const res = await anon.request.get(link);
  expect(res.status(), `GET ${link} sem sessão`).toBe(200);
  expect(res.headers()["content-type"]).toMatch(/^image\/png/);
  await anon.close();
  // o link é estável: recarregar e copiar de novo dá o mesmo
  await page.reload();
  await ref.getByRole("button", { name: "Copiar link" }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(link);

  // Trocar o fundo do card final para o "fundo-novo" e salvar (v2): o cenário fica livre
  await page.goto(`/app/perfis/${perfilId}`);
  await tab(page, "Marca").click();
  await section(page, "Card final").getByRole("radio", { name: "fundo-novo", exact: true }).click();
  await page.getByRole("button", { name: "Salvar kit" }).click();
  await expect(page.getByText("Versão 2", { exact: true })).toBeVisible();

  await page.goto(cenarioUrl);
  await expect(page.getByText("Não é usado em nenhum lugar.")).toBeVisible();
  await page.getByRole("button", { name: "Arquivar", exact: true }).first().click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Arquivar" }).click();
  await expect(page.getByText("Asset arquivado.")).toBeVisible();
  await expect(page.getByText("Arquivado", { exact: true }).first()).toBeVisible();

  // Fora da biblioteca e do seletor; "Mostrar arquivados" traz de volta, com o selo
  await openEstudio(page, "assets", perfilId);
  await expect(grade(page, "assets").getByRole("link", { name: "fundo-novo (Fundo)" })).toBeVisible();
  await openEstudio(page, "cenarios", perfilId);
  await expect(page.getByText(/Nenhum item com o perfil base .+ ainda\./)).toBeVisible();  // 029: só o filtro de perfil
  await page.getByLabel("Mostrar arquivados").click();
  const arquivado = grade(page, "cenarios").getByRole("link", { name: "Cozinha retrô (Cenário)" });
  await expect(arquivado.getByText("Arquivado")).toBeVisible();
  await arquivado.click();
  await page.getByRole("button", { name: "Restaurar", exact: true }).first().click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Restaurar" }).click();
  await expect(page.getByText("Asset restaurado.")).toBeVisible();
  await openEstudio(page, "cenarios", perfilId);
  await expect(grade(page, "cenarios").getByRole("link", { name: "Cozinha retrô (Cenário)" })).toBeVisible();
});

// US3 (T033): stickers com transparência, tags e filtros; sticker sem transparência recusado;
// sticker como marca d'água do kit.
test("stickers com tags, filtro e busca, sticker opaco recusado e sticker na marca d'água", async ({ page, request }) => {
  test.setTimeout(180_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Sticker E2E ${sfx}`, slug: `sticker-e2e-${sfx}` });
  const auth = { Authorization: `Bearer ${token}` };

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await openEstudio(page, "assets", perfilId);

  // Envio múltiplo: 3 PNG com alfa, um asset por arquivo
  await uploadSingleFiles(
    page,
    "Sticker",
    ["joinha", "uau", "promo-10"].map((n) => ({ name: `${n}.png`, mimeType: "image/png", buffer: pngAlphaBuffer(256, 256) })),
  );
  await expect(page.getByText("3 arquivos enviados como Sticker.")).toBeVisible({ timeout: 20_000 });
  const stickers = grade(page, "assets");
  await expect(stickers.getByRole("listitem")).toHaveCount(3);

  // Tags: reação (joinha, uau) e promo (promo-10, e uau com as duas)
  const tags: Record<string, string[]> = { joinha: ["reação"], uau: ["reação", "promo"], "promo-10": ["promo"] };
  for (const [name, list] of Object.entries(tags)) {
    const { assetId } = await libraryImageId(request, token, perfilId, "sticker", name);
    const got = await request.get(`/api/assets/${assetId}`, { headers: auth });
    const { asset } = (await got.json()) as { asset: { version: number } };
    const res = await request.patch(`/api/assets/${assetId}`, { headers: auth, data: { version: asset.version, tags: list } });
    expect(res.status(), `PATCH tags de ${name}`).toBe(200);
  }
  await page.reload();

  // Filtro pela tag "promo" (spec 024: chips em "Mais filtros", etiqueta na barra): só promo-10 e uau
  await page.getByRole("button", { name: /^Mais filtros/ }).click();
  const porTag = page.getByRole("dialog", { name: "Mais filtros" }).getByRole("group", { name: "Filtrar por tag" });
  await expect(porTag.getByRole("button", { name: /#reação\s*2/ })).toBeVisible();
  await porTag.getByRole("button", { name: /#promo/ }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Mais filtros (1)" })).toBeVisible();
  await expect(stickers.getByRole("listitem")).toHaveCount(2);
  await expect(stickers.getByRole("link", { name: "promo-10 (Sticker)" })).toBeVisible();
  await expect(stickers.getByRole("link", { name: "uau (Sticker)" })).toBeVisible();
  await page.screenshot({ path: ".playwright-mcp/sociman/007-filtro-tag.png", fullPage: true });
  await page.getByRole("button", { name: "Remover filtro: Tag" }).click();
  await expect(stickers.getByRole("listitem")).toHaveCount(3);

  // Busca pelo nome
  await page.getByLabel("Buscar por nome ou tag").fill("joinha");
  await expect(stickers.getByRole("listitem")).toHaveCount(1);
  await expect(stickers.getByRole("link", { name: "joinha (Sticker)" })).toBeVisible();
  await page.getByLabel("Buscar por nome ou tag").fill("");
  await expect(stickers.getByRole("listitem")).toHaveCount(3);

  // Sticker sem transparência: JPG barrado no navegador, PNG opaco recusado pela API
  await uploadSingleFiles(page, "Sticker", [{ name: "foto.jpg", mimeType: "image/jpeg", buffer: Buffer.from("nao-e-jpg") }]);
  await expect(page.getByText("foto.jpg: O sticker precisa ter fundo transparente")).toBeVisible();
  await uploadSingleFiles(page, "Sticker", [{ name: "opaco.png", mimeType: "image/png", buffer: pngBuffer(256, 256) }]);
  await expect(page.getByText("opaco.png: O sticker precisa ter fundo transparente")).toBeVisible();
  await expect(stickers.getByRole("listitem")).toHaveCount(3);

  // Aba Marca → Marca d'água → Imagem própria: o seletor lista os stickers
  await page.goto(`/app/perfis/${perfilId}`);
  await tab(page, "Marca").click();
  const marca = section(page, "Marca d'água");
  await marca.getByLabel("Tipo", { exact: true }).selectOption({ label: "Imagem própria" });
  await marca.getByRole("radio", { name: "joinha", exact: true }).click();
  await expect(marca.getByRole("radio", { name: "joinha", exact: true })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "Salvar kit" }).click();
  await expect(page.getByText("Kit salvo.")).toBeVisible();

  const joinha = await libraryImageId(request, token, perfilId, "sticker", "joinha");
  const kitRes = await request.get(`/api/perfis/${perfilId}/kit`, { headers: auth });
  const { kit } = (await kitRes.json()) as { kit: { watermark: { tipo: string; imagem_id: string | null } } };
  expect(kit.watermark.tipo).toBe("imagem");
  expect(kit.watermark.imagem_id).toBe(joinha.image.id);
});
