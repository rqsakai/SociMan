import { randomUUID } from "node:crypto";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, login } from "./helpers";

// Spec 005 (FR-001–003, SC-003): menu por papel, item ativo, gaveta no celular,
// tabela de perfis (ordenação, paginação, vazio) e nenhuma tela rolando de lado a 390 px.

const MOBILE = { width: 390, height: 844 };
const OWNER_ITEMS = ["Início", "Perfis", "Usuários", "Segurança", "Minha conta"];

function mainNav(page: Page): Locator {
  return page.getByRole("navigation", { name: "Menu principal" });
}

function navLink(scope: Locator, name: string): Locator {
  return scope.getByRole("link", { name, exact: true });
}

// O item ativo é o NavLink com aria-current="page"; só um por vez.
async function expectActive(page: Page, name: string): Promise<void> {
  const nav = mainNav(page);
  await expect(navLink(nav, name)).toHaveAttribute("aria-current", "page");
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
}

async function loginOwner(page: Page): Promise<void> {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
}

async function expectNoHorizontalScroll(page: Page, path: string): Promise<void> {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(scrollWidth, `${path}: scrollWidth ${scrollWidth} > innerWidth ${innerWidth}`).toBeLessThanOrEqual(
    innerWidth,
  );
}

test("dono vê o menu completo e o item ativo acompanha a navegação", async ({ page }) => {
  await loginOwner(page);
  const nav = mainNav(page);
  for (const item of OWNER_ITEMS) await expect(navLink(nav, item)).toBeVisible();
  await expectActive(page, "Início");

  const routes: [string, RegExp][] = [
    ["Perfis", /\/app\/perfis$/],
    ["Usuários", /\/app\/usuarios$/],
    ["Segurança", /\/app\/seguranca$/],
    ["Minha conta", /\/app\/conta$/],
    ["Início", /\/app$/],
  ];
  for (const [item, url] of routes) {
    await navLink(nav, item).click();
    await expect(page).toHaveURL(url);
    await expectActive(page, item);
  }
});

test("membro não vê Usuários nem Segurança no menu", async ({ page }) => {
  const member = await createVerifiedMember(page);
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);

  const nav = mainNav(page);
  for (const item of ["Início", "Perfis", "Minha conta"]) await expect(navLink(nav, item)).toBeVisible();
  await expect(navLink(nav, "Usuários")).toHaveCount(0);
  await expect(navLink(nav, "Segurança")).toHaveCount(0);
  await expectActive(page, "Início");
});

test("a 390 px o menu vira gaveta: abre pelo botão, navega e fecha", async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await loginOwner(page);

  // o menu fixo fica escondido abaixo de 1024 px
  await expect(mainNav(page)).toBeHidden();
  await page.getByRole("button", { name: "Abrir menu" }).click();

  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();
  for (const item of OWNER_ITEMS) await expect(navLink(drawer, item)).toBeVisible();

  await navLink(drawer, "Perfis").click();
  await expect(page).toHaveURL(/\/app\/perfis$/);
  await expect(drawer).toBeHidden();
  await expect(mainNav(page)).toBeHidden();
});

test("tabela de perfis ordena por nome, pagina de 10 em 10 e mostra o vazio", async ({ page, request }) => {
  const sfx = randomUUID().slice(0, 8);
  const prefix = `Layout ${sfx}`;
  const token = await apiToken(request, OWNER.email, OWNER.password);
  for (let i = 1; i <= 12; i++) {
    const n = String(i).padStart(2, "0");
    await createPerfilViaApi(request, token, { name: `${prefix} ${n}`, slug: `layout-${sfx}-${n}` });
  }

  await loginOwner(page);
  await navLink(mainNav(page), "Perfis").click();
  await expect(page).toHaveURL(/\/app\/perfis$/);

  // filtra pelo sufixo: só os 12 deste teste ficam na tabela
  const search = page
    .getByRole("searchbox", { name: "Filtrar" })
    .or(page.getByRole("searchbox", { name: "Buscar" }))
    .first();
  await search.fill(sfx);
  await expect(page.getByText("12 itens")).toBeVisible();
  await expect(page.getByText("Página 1 de 2")).toBeVisible();

  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(10);

  // ordenação por nome: o aria-sort do <th> e a primeira linha mudam a cada clique
  const nameHeader = page.getByRole("columnheader", { name: "Nome" });
  await nameHeader.getByRole("button").click();
  await expect(nameHeader).toHaveAttribute("aria-sort", /^(ascending|descending)$/);
  const first = await nameHeader.getAttribute("aria-sort");
  const [firstTop, secondTop, second] =
    first === "ascending" ? ["01", "12", "descending"] : ["12", "01", "ascending"];
  await expect(rows.first()).toContainText(`${prefix} ${firstTop}`);

  await nameHeader.getByRole("button").click();
  await expect(nameHeader).toHaveAttribute("aria-sort", second);
  await expect(rows.first()).toContainText(`${prefix} ${secondTop}`);

  // paginação: a página 2 tem as 2 linhas restantes
  await page.getByRole("button", { name: "Próxima página" }).click();
  await expect(page.getByText("Página 2 de 2")).toBeVisible();
  await expect(rows).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Próxima página" })).toBeDisabled();

  // 25 por página: tudo numa página só
  await page.getByLabel("Por página").selectOption("25");
  await expect(page.getByText("Página 1 de 1")).toBeVisible();
  await expect(rows).toHaveCount(12);

  // busca sem resultado
  await search.fill(`sem-resultado-${sfx}`);
  await expect(page.getByText("Nenhum resultado")).toBeVisible();
});

test("a 390 px nenhuma tela rola na horizontal", async ({ page }) => {
  await page.setViewportSize(MOBILE);

  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expectNoHorizontalScroll(page, "/login");

  await loginOwner(page);
  for (const path of ["/app", "/app/perfis", "/app/usuarios", "/app/seguranca", "/app/conta"]) {
    await page.goto(path);
    await expect(page.getByRole("button", { name: "Abrir menu" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expectNoHorizontalScroll(page, path);
  }
});
