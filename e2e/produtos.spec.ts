import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, login, pngBuffer } from "./helpers";

// Spec 012 (T047): o cadastro do produto pela tela, com o Claude falso (a ficha do
// `shorts_canelado`) e o ComfyUI falso da 021 (recorte e flat) rodando no serviço `gerador`.
// - criar com 2 fotos e ver a ficha;
// - esperar os recortes e escolher os 2 flats (um com "Gerar outras");
// - editar uma cor e aprovar;
// - ligar uma cena ao produto e conferir o prompt e o ingrediente;
// - editar a ficha → revisão, e o seletor da cena não oferece mais o produto;
// - no celular (390 px), a folha sem rolagem horizontal.

type Auth = { Authorization: string };
type Produto = { id: string; version: number; estado: string; variantes: { id: string }[] };

test.describe.configure({ mode: "serial" });

async function produtoApi(request: APIRequestContext, auth: Auth, id: string): Promise<Produto> {
  const r = await request.get(`/api/produtos/${id}`, { headers: auth });
  expect(r.status()).toBe(200);
  return (await r.json()) as Produto;
}

async function confirmar(page: Page, botao: string, escopo: Locator): Promise<void> {
  await escopo.getByRole("button", { name: botao }).first().click();
  const dialogo = page.getByRole("alertdialog");
  await expect(dialogo).toBeVisible();
  await dialogo.getByRole("button", { name: botao }).click();
  await expect(dialogo).toBeHidden();
}

test("cadastro completo: ficha, flats, cor, aprovar, cena e celular", async ({ page, request }) => {
  test.setTimeout(240_000);
  const sfx = Date.now();
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Shop ${sfx}`, slug: `shop-${sfx}` });

  // Criar com 2 fotos.
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  // spec 029: AI Studio › Produtos, filtrada pelo perfil; o produto nasce com ele como perfil base
  await page.goto(`/app/estudio/produtos?perfil=${perfilId}`);
  await expect(page.getByRole("heading", { level: 1, name: "Produtos" })).toBeVisible();
  await page.getByRole("button", { name: "Novo produto" }).first().click();
  const dialogo = page.getByRole("dialog");
  await expect(dialogo.getByTestId("perfil-base")).toHaveValue(perfilId);
  await dialogo.getByLabel("Nome do produto").fill("shorts_canelado");
  await dialogo.getByLabel("Fotos").setInputFiles([
    { name: "foto1.png", mimeType: "image/png", buffer: pngBuffer(800, 900) },
    { name: "foto2.png", mimeType: "image/png", buffer: pngBuffer(820, 900) },
  ]);
  await expect(dialogo.getByTestId("foto-2")).toBeVisible();
  await dialogo.getByLabel("Observação").fill("shorts de cintura alta canelados, logo LS");
  await dialogo.getByRole("button", { name: "Criar produto" }).click();
  await expect(page).toHaveURL(/\/app\/produtos\/[0-9a-f-]+$/, { timeout: 30_000 });
  const produtoId = page.url().split("/").pop() as string;

  // A ficha chega (Claude falso) e o material vem das fotos.
  await expect(page.getByTestId("ficha-por")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel("Material para prompts (inglês)")).toHaveValue("ribbed knit");

  // Recortes e flats; a variante 2 pede "Gerar outras" antes de escolher.
  const flat1 = page.getByTestId("flat-variante-1");
  const flat2 = page.getByTestId("flat-variante-2");
  await expect(flat1.getByRole("button", { name: "Usar opção 1" })).toBeVisible({ timeout: 120_000 });
  await confirmar(page, "Usar opção 1", flat1);
  await expect(flat2.getByRole("button", { name: "Gerar outras" })).toBeVisible({ timeout: 120_000 });
  await confirmar(page, "Gerar outras", flat2);
  await expect(flat2.getByRole("button", { name: "Usar opção 2" })).toBeVisible({ timeout: 120_000 });
  await confirmar(page, "Usar opção 2", flat2);
  await expect(page.getByTestId("estado-produto")).toHaveText("Em revisão", { timeout: 30_000 });
  await expect(page.getByTestId("folha-flat-2")).toBeVisible();

  // Editar a cor da variante 1 e aprovar.
  await page.getByLabel("Cor da variante 1 (inglês)").fill("jet black");
  await page.getByRole("button", { name: "Salvar ficha" }).click();
  await expect(page.getByTestId("ficha-por")).toContainText(/edit/i, { timeout: 15_000 });
  await page.getByRole("button", { name: "Aprovar" }).click();
  await expect(page.getByTestId("estado-produto")).toHaveText("Aprovado", { timeout: 15_000 });

  // Ligar uma cena ao produto (pela API) e conferir o prompt e o ingrediente na tela.
  const p = await produtoApi(request, auth, produtoId);
  const rc = await request.post(`/api/perfis/${perfilId}/cenas`, {
    headers: auth,
    data: { nome: "Mostra o shorts", acao: "holds the shorts up and smiles", produtoId, produtoVarianteId: p.variantes[0].id },
  });
  expect(rc.status(), await rc.text()).toBe(201);
  const cenaId = ((await rc.json()) as { id: string }).id;
  await page.goto(`/app/cenas/${cenaId}`);
  await expect(page.getByTestId("cena-produto")).toBeVisible();
  const prompt = page.getByTestId("prompt-texto");
  await expect(prompt).toContainText("with the product exactly as in the reference image");
  await expect(prompt).toContainText("Color: jet black.");

  // Editar a ficha volta o produto a revisão; o seletor da cena deixa de oferecê-lo.
  await page.goto(`/app/produtos/${produtoId}`);
  await page.getByLabel("Descrição de venda").fill("Short canelado confortável. Logo LS discreto.");
  await page.getByRole("button", { name: "Salvar ficha" }).click();
  await expect(page.getByTestId("estado-produto")).toHaveText("Em revisão", { timeout: 15_000 });
  // (o endereço antigo da cena nova redireciona para o AI Studio; o seletor lista os aprovados da
  // agência inteira, então confere só que este produto saiu)
  await page.goto(`/app/perfis/${perfilId}/cenas/nova`);
  await expect(page).toHaveURL(new RegExp(`/app/estudio/cenas/nova\\?perfil=${perfilId}$`));
  const seletor = page.getByLabel("Produto do catálogo");
  await expect(seletor).toBeVisible();
  await expect(seletor.locator("option").first()).toHaveText("Nenhum");
  await expect(seletor.locator(`option[value="${produtoId}"]`)).toHaveCount(0);

  // No celular, a folha cabe sem rolagem horizontal.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/app/produtos/${produtoId}`);
  await expect(page.getByTestId("folha-revisao")).toBeVisible();
  const sobra = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(sobra).toBeLessThanOrEqual(0);
});
