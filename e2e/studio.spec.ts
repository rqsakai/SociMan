import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import {
  apiToken,
  createPerfilViaApi,
  createVerifiedMember,
  csvOverview,
  login,
  logout,
  sqlE2e,
  zipsStudio,
  type DiaOverview,
  type Member,
} from "./helpers";

// Spec 020 (T022, T027, T035, T039, T046): o histórico do TikTok Studio. Os ZIPs são SINTÉTICOS,
// montados em memória (zipStudio, "stored" com crc32); nunca o arquivo real do dono. A série da 016
// é semeada por SQL (sem coleta), então todos os dias importados valem o Studio no analytics.

const SHOTS = ".playwright-mcp/sociman";

// "Hoje" no fuso da casa, e dias relativos a ele (AAAA-MM-DD).
const hoje = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
function dia(delta: number): string {
  const [y, m, d] = hoje().split("-").map(Number);
  return new Date(Date.UTC(y!, m! - 1, d! + delta)).toISOString().slice(0, 10);
}
const br = (d: string) => d.split("-").reverse().join("/");

// 7 dias com views e seguidores inventados (picos e zeros, como no real).
function semana(fim: number, base = 100): (DiaOverview & { seguidores: number })[] {
  const views = [base, base * 2, 1, 2, 6, base * 8, base * 9];
  return views.map((v, i) => ({ dia: dia(fim - 6 + i), views: v, likes: i, visitasPerfil: i * 2, seguidores: i }));
}

// Perfil e conta TikTok próprios, com a série viva da 016 (sem fotos).
async function contaComSerie(request: APIRequestContext) {
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Studio ${sfx}`, slug: `studio-${sfx}` });
  const handle = `studio_${sfx}`;
  const res = await request.post(`/api/perfis/${perfilId}/contas`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { platform: "tiktok", handle, status: "ativa" },
  });
  expect(res.status(), `POST contas: ${await res.text()}`).toBe(201);
  const contaId = ((await res.json()) as { conta: { id: string } }).conta.id;
  sqlE2e(`insert into metricas_series (id, rede, conta_id) values (gen_random_uuid(), 'tiktok', '${contaId}')`);
  return { perfilId, contaId, handle };
}

type Arquivo = { name: string; mimeType: string; buffer: Buffer };

async function lerArquivos(page: Page, arquivos: Arquivo[]) {
  const importar = page.getByRole("region", { name: "Importar" });
  await importar.getByLabel("Arquivos do Studio").setInputFiles(arquivos);
  await importar.getByRole("button", { name: "Ler arquivos" }).click();
}

const previa = (page: Page) => page.locator("[data-previa]");
const importacoes = (page: Page) => page.getByRole("region", { name: "Importações" });

test("020 US1/US2: prévia, confirmar, já importado, conta errada, CSV solto e data futura", async ({ page, request }) => {
  test.setTimeout(180_000);
  const c = await contaComSerie(request);
  const dias = semana(-3);
  const zips = zipsStudio(c.handle, dias);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  // ---- a conta TikTok tem o link "Histórico do Studio" ----
  await page.goto(`/app/perfis/${c.perfilId}?aba=contas`);
  await page.getByRole("link", { name: "Histórico do Studio" }).first().click();
  await expect(page).toHaveURL(new RegExp(`/app/contas/${c.contaId}/studio$`));
  await expect(page.getByRole("heading", { level: 1 })).toContainText(`@${c.handle}`);
  await expect(page.locator("[data-cobertura]")).toContainText("Nenhum dia importado do Studio ainda.");
  await expect(importacoes(page)).toContainText("Nenhuma importação nesta conta.");

  // ---- US2: ZIP de outra conta é recusado com a mensagem ----
  await lerArquivos(page, [zipsStudio("outraconta", dias).overview]);
  await expect(page.locator('[data-erro-studio="studio_conta_diferente"]')).toContainText("outraconta");
  await expect(previa(page)).toHaveCount(0);

  // ---- US2: data futura mostra a linha do problema ----
  const futuro = zipsStudio(c.handle, [
    { dia: dia(-1), views: 5, seguidores: 0 },
    { dia: dia(1), views: 7, seguidores: 0 },
  ]).overview;
  await lerArquivos(page, [futuro]);
  await expect(page.locator("[data-erro-studio]")).toBeVisible();
  await expect(page.locator("[data-erro-studio]")).toContainText(/linha|futur/i);

  // ---- US1: os 2 ZIPs → prévia (nada gravado) → confirmar ----
  await lerArquivos(page, [zips.overview, zips.seguidores]);
  await expect(previa(page)).toContainText(`${br(dias[0]!.dia)} a ${br(dias[6]!.dia)}`);
  await expect(previa(page)).toContainText("ano pelo nome do ZIP");
  await expect(previa(page)).toContainText("FollowerActivity.csv");
  const fmt = (n: number) => new Intl.NumberFormat("pt-BR").format(n);
  await expect(previa(page).locator('[data-secao="visao_geral"]')).toContainText(`Views: ${fmt(dias.reduce((t, d) => t + d.views, 0))}`);
  await expect(previa(page).locator('[data-secao="seguidores"]')).toBeVisible();
  await expect(previa(page).locator('[data-secao="visao_geral"] tbody tr')).not.toHaveCount(0);
  await expect(importacoes(page)).toContainText("Nenhuma importação nesta conta.");
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(previa(page)).toHaveCount(0);
  await expect(importacoes(page).locator('[data-importacao="ativa"]')).toHaveCount(1);
  await expect(importacoes(page)).toContainText(`${br(dias[0]!.dia)} a ${br(dias[6]!.dia)}`);
  await expect(page.locator("[data-cobertura]")).toContainText("Importado do Studio");

  // ---- reenviar os mesmos ZIPs: "já importado", sem confirmar ----
  await lerArquivos(page, [zips.overview, zips.seguidores]);
  await expect(previa(page).locator("[data-ja-importado]")).toBeVisible();
  await expect(previa(page).locator("[data-ja-importada]")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Confirmar importação" })).toHaveCount(0);
  await page.getByRole("button", { name: "Fechar" }).click();

  // ---- US2: CSV solto exige a caixa "confirmo que é de @conta" ----
  const antes = semana(-20);
  await lerArquivos(page, [{ name: "Overview.csv", mimeType: "text/csv", buffer: csvOverview(antes) }]);
  await expect(previa(page)).toContainText("ano deduzido");
  const confirmar = page.getByRole("button", { name: "Confirmar importação" });
  await expect(confirmar).toBeDisabled();
  await page.getByLabel(new RegExp(`Confirmo que este arquivo é de @${c.handle}`)).check();
  await expect(confirmar).toBeEnabled();
  await confirmar.click();
  await expect(importacoes(page).locator('[data-importacao="ativa"]')).toHaveCount(2);

  // ---- celular: sem rolagem horizontal ----
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(importacoes(page).locator('[data-importacao="ativa"]')).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: `${SHOTS}/020-studio-celular.png`, fullPage: true });
  await lerArquivos(page, [zips.overview, zips.seguidores]);
  await expect(previa(page)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: `${SHOTS}/020-studio-previa-celular.png`, fullPage: true });
});

test("020 US3/US4: o analytics mostra os dias do Studio; desfazer tira", async ({ page, request }) => {
  test.setTimeout(180_000);
  const c = await contaComSerie(request);
  const dias = semana(-3);
  const zips = zipsStudio(c.handle, dias);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/contas/${c.contaId}/studio`);
  await lerArquivos(page, [zips.overview, zips.seguidores]);
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(importacoes(page).locator('[data-importacao="ativa"]')).toHaveCount(1);

  // ---- US3: a Visão geral filtrada na conta usa os dias do Studio ----
  const url = `/app/metricas?perfil=${c.perfilId}&conta=${c.contaId}&de=${dia(-13)}&ate=${hoje()}`;
  await page.goto(url);
  const views = page.locator('[data-indicador="Views ganhas"]');
  await expect(views).toContainText("inclui 7 dias importados do Studio");
  const total = dias.reduce((t, d) => t + d.views, 0);
  await expect(views).toContainText(new Intl.NumberFormat("pt-BR").format(total));
  const card = page.locator('section[data-card="Views por dia"]');
  await expect(card).toContainText("importado do Studio");
  await card.getByRole("button", { name: "Ver tabela" }).click();
  await expect(card.getByRole("columnheader", { name: "Fonte" })).toBeVisible();
  await expect(card.getByRole("cell", { name: "studio" }).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/020-visao-geral-studio.png`, fullPage: true });

  // ---- Quando postar: o calendário marca os dias do Studio na tabela ----
  await page.goto(`${url}&aba=quando-postar`);
  const cal = page.locator('section[data-card="Calendário"]');
  await cal.getByRole("button", { name: "Ver tabela" }).click();
  await expect(cal.getByRole("columnheader", { name: "Fonte" })).toBeVisible();
  await expect(cal.getByRole("cell", { name: "studio" }).first()).toBeVisible();

  // ---- a aba Contas do analytics leva ao histórico ----
  await page.goto(`${url}&aba=contas`);
  await page.getByRole("link", { name: `Histórico do Studio de @${c.handle}` }).click();
  await expect(page).toHaveURL(new RegExp(`/app/contas/${c.contaId}/studio$`));

  // ---- US4: desfazer (com confirmação) → "desfeita" e os dias somem do analytics ----
  await importacoes(page).getByRole("button", { name: "Desfazer" }).click();
  const dialogo = page.getByRole("alertdialog");
  await expect(dialogo).toContainText("continuam guardados");
  await dialogo.getByRole("button", { name: "Desfazer" }).click();
  await expect(importacoes(page).locator('[data-importacao="desfeita"]')).toHaveCount(1);
  await expect(importacoes(page)).toContainText(`por ${OWNER.name}`);
  await expect(page.locator("[data-cobertura]")).toContainText("Nenhum dia importado do Studio ainda.");

  await page.goto(url);
  await expect(page.locator('[data-indicador="Views ganhas"]')).not.toContainText("importados do Studio");
  await expect(page.locator('section[data-card="Views por dia"]')).not.toContainText("importado do Studio");
});

test("020 US5: o membro vê a cobertura e a lista, sem importar nem desfazer", async ({ page, request }) => {
  test.setTimeout(180_000);
  const c = await contaComSerie(request);
  const member: Member = await createVerifiedMember(page);
  const zips = zipsStudio(c.handle, semana(-5));

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/contas/${c.contaId}/studio`);
  await lerArquivos(page, [zips.overview, zips.seguidores]);
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(importacoes(page).locator('[data-importacao="ativa"]')).toHaveCount(1);
  // o aviso "Importação confirmada" cobre o "Sair" (canto superior direito) até sumir
  await page.mouse.move(0, 400);
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
  await logout(page);

  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/contas/${c.contaId}/studio`);
  await expect(importacoes(page).locator('[data-importacao="ativa"]')).toHaveCount(1);
  await expect(page.locator("[data-cobertura]")).toContainText("Importado do Studio");
  await expect(page.getByRole("region", { name: "Importar" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Ler arquivos" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Desfazer" })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/020-studio-membro.png`, fullPage: true });
});
