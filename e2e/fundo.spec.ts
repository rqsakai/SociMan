import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, login, pngBuffer, syntheticMp4 } from "./helpers";

function tab(page: Page, name: string): Locator {
  return page.getByRole("tab", { name, exact: true });
}

function section(page: Page, name: string): Locator {
  return page.getByRole("region", { name, exact: true });
}

interface ExportAsset {
  id?: string | null;
  url: string;
  expiresAt: string | null;
}

// Desvio padrão de cada canal numa faixa do topo do último quadro do MP4 (ffmpeg do host). A
// faixa fica longe do CTA (centro) e da marca d'água (desligada); num card de cor sólida ela é
// uniforme (desvio ~0), com a imagem de fundo ela mostra o degradê do PNG.
function lastFrameTopStripStddev(mp4: string): { r: number; g: number; b: number } {
  const raw = execFileSync(
    "ffmpeg",
    ["-v", "error", "-sseof", "-0.3", "-i", mp4, "-frames:v", "1", "-vf", "crop=iw:trunc(ih*0.1):0:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
    { maxBuffer: 64 * 1024 * 1024 },
  );
  expect(raw.length, "o ffmpeg não extraiu o último quadro").toBeGreaterThan(0);
  const stats = [0, 1, 2].map((c) => {
    let sum = 0;
    let sq = 0;
    let n = 0;
    for (let i = c; i < raw.length; i += 3) {
      sum += raw[i]!;
      sq += raw[i]! ** 2;
      n++;
    }
    const mean = sum / n;
    return Math.sqrt(Math.max(0, sq / n - mean ** 2));
  });
  return { r: stats[0]!, g: stats[1]!, b: stats[2]! };
}

// T034 (FR-005a e FR-005b): o dono envia uma imagem de fundo pela aba Marca, usa no card final
// (tipo de fundo = Imagem), salva, exporta (a imagem nos assets, com link sem validade) e processa
// um corte curto até "Pronto"; o último quadro do resultado mostra a imagem, não uma cor sólida.
// Precisa do `worker` no ar.
test("dono usa uma imagem de fundo no card final e ela aparece no corte", async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);

  const sfx = randomUUID().slice(0, 8);
  const slug = `fundo-e2e-${sfx}`;
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Fundo E2E ${sfx}`, slug });
  const auth = { Authorization: `Bearer ${token}` };

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/perfis/${perfilId}`);
  await tab(page, "Marca").click();
  await expect(page.getByText("Kit padrão (ainda não salvo)")).toBeVisible();

  // Card final (nasce desligado) com imagem: a camada nasce com 0,45 e o seletor pede a imagem
  const card = section(page, "Card final");
  await card.getByRole("switch", { name: "Ligado" }).click();
  await expect(card.getByRole("switch", { name: "Ligado" })).toBeChecked();
  await card.getByLabel("Tipo de fundo", { exact: true }).selectOption({ label: "Imagem" });
  await expect(card.getByLabel("Opacidade da camada")).toHaveValue("0.45");
  await expect(card.getByText("Nenhuma imagem enviada ainda.")).toBeVisible();

  // Salvar sem imagem é recusado no navegador
  await page.getByRole("button", { name: "Salvar kit" }).click();
  await expect(card.getByText("Escolha ou envie uma imagem de fundo")).toBeVisible();

  // Imagem pequena demais é barrada antes do envio (mínimo 540×540)
  const input = card.locator('input[type="file"]');
  await input.setInputFiles({ name: "pequena.png", mimeType: "image/png", buffer: pngBuffer(300, 300) });
  await expect(card.getByText("Imagem pequena demais")).toBeVisible();

  // Envio de verdade: 1080×1920 com degradê horizontal; fica escolhida no rascunho
  await input.setInputFiles({ name: "fundo.png", mimeType: "image/png", buffer: pngBuffer(1080, 1920) });
  const escolhida = card.getByRole("radio", { name: "Imagem 1" });
  await expect(escolhida).toHaveAttribute("aria-checked", "true", { timeout: 15_000 });
  await expect(card.getByText("Imagem pequena demais")).toBeHidden();
  await expect(card.getByText("Escolha ou envie uma imagem de fundo")).toBeHidden();

  // Prévia do fim: a imagem sob a camada
  await page.getByRole("button", { name: "Fim (card final)" }).click();
  const previewCard = page.locator('[data-preview="card"]');
  await expect(previewCard).toHaveAttribute("data-fundo", "imagem");
  await expect.poll(() => previewCard.evaluate((el) => getComputedStyle(el).backgroundImage)).toContain("url(");
  await page.screenshot({ path: ".playwright-mcp/sociman/fundo-marca.png", fullPage: true });

  await page.getByRole("button", { name: "Salvar kit" }).click();
  await expect(page.getByText("Kit salvo.")).toBeVisible();
  await expect(page.getByText("Versão 1", { exact: true })).toBeVisible();

  const kitRes = await request.get(`/api/perfis/${perfilId}/kit`, { headers: auth });
  expect(kitRes.status()).toBe(200);
  const { kit } = (await kitRes.json()) as {
    kit: {
      endCard: { fundo_tipo: string; fundo_imagem_id: string | null; opacidade_fundo: number };
      hook: { fundo_tipo: string; fundo_imagem_id: string | null };
    };
  };
  expect(kit.endCard.fundo_tipo).toBe("imagem");
  expect(kit.endCard.opacidade_fundo).toBe(0.45);
  expect(kit.hook.fundo_tipo).toBe("cor");
  const fundoId = kit.endCard.fundo_imagem_id;
  expect(fundoId).toMatch(/^[0-9a-f-]{36}$/);

  // A lista de fundos do perfil tem a imagem enviada
  const fundosRes = await request.get(`/api/perfis/${perfilId}/fundos`, { headers: auth });
  expect(fundosRes.status()).toBe(200);
  const fundos = (await fundosRes.json()) as { items: { id: string; width: number; height: number }[] };
  expect(fundos.items.map((i) => i.id)).toContain(fundoId);

  // Exportação: a imagem de fundo nos assets, com link público e sem validade
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar kit (JSON)" }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe(`kit-${slug}-v1.json`);
  const doc = JSON.parse(await readFile(await download.path(), "utf8")) as {
    tokens: { endCard: { fundo_tipo: string; fundo_imagem_url?: string } };
    assets: { backgroundImages: ExportAsset[] };
  };
  expect(doc.tokens.endCard.fundo_tipo).toBe("imagem");
  const fundoAsset = doc.assets.backgroundImages.find((a) => a.id === fundoId);
  expect(fundoAsset, `a imagem de fundo está nos assets: ${JSON.stringify(doc.assets)}`).toBeDefined();
  expect(doc.tokens.endCard.fundo_imagem_url).toBe(fundoAsset!.url);
  expect(fundoAsset!.expiresAt).toBeNull();
  expect(fundoAsset!.url).toMatch(/^\/api\/midia\//);
  const fundoFile = await request.get(fundoAsset!.url);
  expect(fundoFile.status(), `GET ${fundoAsset!.url}`).toBe(200);
  expect(fundoFile.headers()["content-type"]).toMatch(/^image\//);

  // Corte curto (4 s; o card final dura 2 s) até "Pronto"
  const video = testInfo.outputPath("corte.mp4");
  syntheticMp4(video, 4);
  const hookText = `Fundo E2E ${sfx}`;
  await tab(page, "Cortes").click();
  await page.getByLabel("Vídeo do corte").setInputFiles(video);
  await page.getByLabel("Texto do gancho").fill(hookText);
  await page.getByRole("button", { name: "Enviar corte" }).click();
  await expect(page).toHaveURL(/\/app\/cortes\/[0-9a-f-]{36}$/, { timeout: 30_000 });
  await expect(page.getByText("Kit v1").first()).toBeVisible();
  await expect(page.getByText("Pronto", { exact: true }).first()).toBeVisible({ timeout: 180_000 });
  await page.screenshot({ path: ".playwright-mcp/sociman/fundo-corte.png", fullPage: true });

  // Último quadro do MP4 marcado: a faixa do topo mostra o degradê da imagem (azul de 0 a 255 na
  // largura, sob 45% de preto), não a cor sólida do card
  const href = await page.getByRole("link", { name: "Baixar", exact: true }).getAttribute("href");
  expect(href).toMatch(/^\/api\/midia\/.+download=1/);
  const mp4 = await request.get(href!);
  expect(mp4.status()).toBe(200);
  const out = testInfo.outputPath("resultado.mp4");
  await writeFile(out, await mp4.body());
  const sd = lastFrameTopStripStddev(out);
  testInfo.annotations.push({ type: "desvio do último quadro", description: JSON.stringify(sd) });
  expect(sd.b, `desvio do azul na faixa do topo do último quadro: ${JSON.stringify(sd)}`).toBeGreaterThan(15);
});
