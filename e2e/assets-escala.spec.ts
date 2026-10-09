import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, login, seedAssets, type SeedAsset } from "./helpers";

// SC-002 (T040): com 200 assets no perfil (tipos e tags variados), achar um asset por tag e por
// nome leva menos de 10 s cada, cronometrado da abertura da página do AI Studio (filtrada pelo
// perfil) até o card aparecer. Spec 029: o sticker fica em Assets; o cenário, em Cenários.
test("biblioteca com 200 assets: achar por tag e por nome em menos de 10 s", async ({ page, request }, testInfo) => {
  test.setTimeout(300_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Escala E2E ${sfx}`, slug: `escala-e2e-${sfx}` });

  // 199 assets de enchimento + os 2 alvos (um achado pela tag, outro pelo nome)
  const tipos: SeedAsset["tipo"][] = ["avatar", "cenario", "avatar", "cenario", "fundo", "sticker", "marca_dagua", "imagem"];
  const tagPool = ["reação", "promo", "cozinha", "persona", "fundo-claro", "fundo-escuro", "natal", "tiktok-shop"];
  const seed: SeedAsset[] = Array.from({ length: 198 }, (_, i) => ({
    tipo: tipos[i % tipos.length]!,
    name: `Asset ${String(i + 1).padStart(3, "0")}`,
    tags: [tagPool[i % tagPool.length]!, tagPool[(i * 3 + 1) % tagPool.length]!],
  }));
  seed.splice(37, 0, { tipo: "sticker", name: "Selo raro", tags: ["alvo-da-tag", "promo"] });
  seed.splice(142, 0, { tipo: "cenario", name: "Praia ao entardecer", tags: ["natal"] });
  await seedAssets(request, token, perfilId, seed);

  const list = await request.get(`/api/perfis/${perfilId}/assets?limit=1`, { headers: { Authorization: `Bearer ${token}` } });
  expect(list.status()).toBe(200);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  let grade = page.getByRole("list", { name: "Assets", exact: true });

  // Por tag: abre AI Studio › Assets e clica no chip da tag
  let start = Date.now();
  await page.goto(`/app/estudio/assets?perfil=${perfilId}`);
  await page.getByRole("button", { name: /^Mais filtros/ }).click();
  await page.getByRole("dialog", { name: "Mais filtros" }).getByRole("group", { name: "Filtrar por tag" }).getByRole("button", { name: /#alvo-da-tag/ }).click();
  await page.keyboard.press("Escape");
  await expect(grade.getByRole("link", { name: "Selo raro (Sticker)" })).toBeVisible();
  await expect(grade.getByRole("listitem")).toHaveCount(1);
  const porTag = Date.now() - start;
  await page.screenshot({ path: ".playwright-mcp/sociman/007-escala.png", fullPage: true });

  // Por nome: abre AI Studio › Cenários e busca
  grade = page.getByRole("list", { name: "Cenários", exact: true });
  start = Date.now();
  await page.goto(`/app/estudio/cenarios?perfil=${perfilId}`);
  await page.getByLabel("Buscar por nome ou tag").fill("praia");
  await expect(grade.getByRole("link", { name: "Praia ao entardecer (Cenário)" })).toBeVisible();
  await expect(grade.getByRole("listitem")).toHaveCount(1);
  const porNome = Date.now() - start;

  testInfo.annotations.push({ type: "SC-002", description: `200 assets; por tag ${porTag} ms, por nome ${porNome} ms` });
  console.log(`SC-002: 200 assets; por tag ${porTag} ms, por nome ${porNome} ms`);
  expect(porTag, "achar por tag").toBeLessThan(10_000);
  expect(porNome, "achar por nome").toBeLessThan(10_000);
});
