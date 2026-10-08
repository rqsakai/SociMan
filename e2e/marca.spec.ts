import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, login, syntheticMp4 } from "./helpers";

// Aba do detalhe do perfil (TabsTrigger, role "tab").
function tab(page: Page, name: string): Locator {
  return page.getByRole("tab", { name, exact: true });
}

// Seção do editor do kit (SectionCard: role "region" com o título como nome).
function section(page: Page, name: string): Locator {
  return page.getByRole("region", { name, exact: true });
}

interface KitExport {
  perfil: { slug: string };
  kit: { version: number };
  tokens: { hook: { cor_fundo: string; fonte: { ref: string; name: string } } };
  openshorts: { hook: { enabled: boolean } };
  assets: { fonts: { ref: string; name: string; url: string; expiresAt: string | null }[] };
}

// T028 (quickstart §1–4): o dono põe uma cor nova na paleta e a usa no fundo do gancho, envia
// uma fonte e a usa no gancho, exporta o JSON (gancho do OpenShorts desligado, link da fonte sem
// validade) e aplica a marca num MP4 sintético até "Pronto", com o player carregando o resultado.
// Precisa do `worker` no ar.
test("dono edita o kit, envia fonte, exporta e aplica a marca num corte", async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);

  const sfx = randomUUID().slice(0, 8);
  const slug = `marca-e2e-${sfx}`;
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Marca E2E ${sfx}`, slug });
  const auth = { Authorization: `Bearer ${token}` };

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/perfis/${perfilId}`);

  // §1: nova cor na paleta, usada no fundo do gancho; salvar cria a v1
  await tab(page, "Marca").click();
  await expect(page.getByText("Kit padrão (ainda não salvo)")).toBeVisible();
  const paleta = section(page, "Paleta");
  await paleta.getByRole("button", { name: "Adicionar cor" }).click();
  const cores = paleta.getByRole("list", { name: "Cores da paleta" }).getByRole("listitem");
  const nova = await cores.count();
  await paleta.getByLabel(`Cor ${nova}: nome`).fill("Rosa E2E");
  await paleta.getByLabel(`Cor ${nova}: hex`).fill("#FF5FA2");
  const gancho = section(page, "Gancho");
  await gancho.getByLabel("Cor do fundo", { exact: true }).selectOption({ label: "Rosa E2E (#FF5FA2)" });
  await page.getByRole("button", { name: "Salvar kit" }).click();
  await expect(page.getByText("Kit salvo.")).toBeVisible();
  await expect(page.getByText("Versão 1", { exact: true })).toBeVisible();

  const kitRes = await request.get(`/api/perfis/${perfilId}/kit`, { headers: auth });
  expect(kitRes.status()).toBe(200);
  const { kit } = (await kitRes.json()) as {
    kit: { version: number; palette: { chave: string; nome: string; valor: string }[]; hook: { cor_fundo: string } };
  };
  const rosa = kit.palette.find((c) => c.nome === "Rosa E2E");
  expect(rosa?.valor).toBe("#FF5FA2");
  expect(kit.hook.cor_fundo).toBe(`paleta:${rosa!.chave}`);

  // §2: enviar uma fonte (a Anton padrão, baixada da API, com outro nome)
  const fontName = `Pergaminho ${sfx}`;
  const ttf = await request.get("/api/fontes-padrao/anton");
  expect(ttf.status(), "GET /api/fontes-padrao/anton").toBe(200);
  await tab(page, "Fontes").click();
  await page.getByLabel("Arquivo da fonte").setInputFiles({
    name: "Pergaminho.ttf",
    mimeType: "font/ttf",
    buffer: await ttf.body(),
  });
  await page.getByLabel("Nome da fonte").fill(fontName);
  await page.getByRole("button", { name: "Enviar fonte" }).click();
  await expect(page.getByText(`Fonte "${fontName}" enviada.`)).toBeVisible();
  await expect(page.getByRole("listitem", { name: `Fonte ${fontName}` })).toBeVisible();

  // a fonte do perfil vira a fonte do gancho (v2); só as fontes usadas no kit vão para a exportação
  await tab(page, "Marca").click();
  await section(page, "Gancho").getByLabel("Fonte", { exact: true }).selectOption({ label: fontName });
  await page.getByRole("button", { name: "Salvar kit" }).click();
  await expect(page.getByText("Versão 2", { exact: true })).toBeVisible();

  // §3: exportar o JSON pelo botão (download de verdade)
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar kit (JSON)" }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe(`kit-${slug}-v2.json`);
  const doc = JSON.parse(await readFile(await download.path(), "utf8")) as KitExport;
  expect(doc.perfil.slug).toBe(slug);
  expect(doc.kit.version).toBe(2);
  expect(doc.openshorts.hook.enabled).toBe(false);
  expect(doc.tokens.hook.cor_fundo).toBe("#FF5FA2");
  expect(doc.tokens.hook.fonte.name).toBe(fontName);
  const asset = doc.assets.fonts.find((f) => f.name === fontName);
  expect(asset, "a fonte do gancho está nos assets").toBeDefined();
  expect(asset!.expiresAt).toBeNull();
  expect(asset!.url).toMatch(/^\/api\/midia\//);
  // o link é público (sem login) e não vence; com um caractere trocado, 403
  const fontFile = await request.get(asset!.url);
  expect(fontFile.status(), `GET ${asset!.url}`).toBe(200);
  expect((await fontFile.body()).equals(await ttf.body())).toBe(true);
  const tampered = asset!.url.slice(0, -1) + (asset!.url.endsWith("A") ? "B" : "A");
  expect((await request.get(tampered)).status()).toBe(403);

  // §4: aplicar a marca num MP4 sintético de 6 s
  const video = testInfo.outputPath("corte.mp4");
  syntheticMp4(video, 6);
  const hookText = `Achadinho E2E ${sfx}`;
  await page.goto(`/app/conteudos?perfil=${perfilId}`);
  await page.getByRole("button", { name: "Aplicar marca num corte" }).click();
  const dialogo = page.getByRole("dialog", { name: "Aplicar marca num corte" });
  await expect(dialogo.getByLabel("Perfil")).toHaveValue(perfilId);
  await dialogo.getByLabel("Vídeo do corte").setInputFiles(video);
  await dialogo.getByLabel("Texto do gancho").fill(hookText);
  await dialogo.getByRole("button", { name: "Enviar corte" }).click();
  await expect(page).toHaveURL(/\/app\/cortes\/[0-9a-f-]{36}$/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: hookText })).toBeVisible();
  await expect(page.getByText("Kit v2").first()).toBeVisible();

  // o SPA faz polling de 2 s; o worker processa um corte por vez
  await expect(page.getByText("Pronto", { exact: true }).first()).toBeVisible({ timeout: 180_000 });
  await expect(page.getByText("Resultado com a marca aplicada.")).toBeVisible();

  // o <video> do resultado carrega (preload=metadata: força o carregamento de dados)
  const player = page.getByLabel("Vídeo com a marca");
  await expect(player).toBeVisible();
  await player.evaluate((el: HTMLVideoElement) => {
    el.muted = true;
    el.preload = "auto";
    el.load();
  });
  await expect
    .poll(() => player.evaluate((el: HTMLVideoElement) => (el.error ? `erro ${el.error.code}` : el.readyState)), {
      timeout: 30_000,
      message: "o <video> do resultado não chegou a HAVE_CURRENT_DATA",
    })
    .toBeGreaterThanOrEqual(2);
  expect(await player.evaluate((el: HTMLVideoElement) => el.duration)).toBeCloseTo(6, 0);

  // "Baixar" aponta para o MP4 marcado, que responde a Range (206)
  const baixar = page.getByRole("link", { name: "Baixar", exact: true });
  await expect(baixar).toBeVisible();
  await expect(page.getByRole("link", { name: "Baixar original", exact: true })).toBeVisible();
  const href = await baixar.getAttribute("href");
  expect(href).toMatch(/^\/api\/midia\/.+download=1/);
  const partial = await request.get(href!, { headers: { Range: "bytes=0-1023" } });
  expect(partial.status()).toBe(206);
  expect(partial.headers()["content-type"]).toContain("video/mp4");
});

// Spec 024 (T025): o "Aplicar marca num corte" de Conteúdos lê o estado do HD ao abrir; HD
// indisponível bloqueia o envio com o aviso. O fake não desmonta o HD: a resposta de
// /api/armazenamento é interceptada no navegador.
test("HD indisponível bloqueia o envio do corte", async ({ page, request }) => {
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `HD E2E ${sfx}`, slug: `hd-e2e-${sfx}` });
  await page.route("**/api/armazenamento", (route) =>
    route.fulfill({
      json: { available: false, reason: "sem_sentinela", freeBytes: null, totalBytes: null, cortesBytes: 0, minFreeBytes: 5 * 1024 ** 3 },
    }),
  );

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos?perfil=${perfilId}`);
  await page.getByRole("button", { name: "Aplicar marca num corte" }).click();
  const dialogo = page.getByRole("dialog", { name: "Aplicar marca num corte" });
  await expect(dialogo.getByText("O HD de dados não está disponível", { exact: true })).toBeVisible();
  await expect(dialogo.getByText("Envio desabilitado: O HD de dados não está disponível.")).toBeVisible();
  await expect(dialogo.getByLabel("Vídeo do corte")).toBeDisabled();
  await expect(dialogo.getByRole("button", { name: "Enviar corte" })).toBeDisabled();
});
