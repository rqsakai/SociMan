import { readFile } from "node:fs/promises";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, login, sqlE2e } from "./helpers";

// Spec 019 (T022): smoke da base do analytics. "Métricas" abre as 8 abas; a aba ativa mora na
// URL (?aba=, com o padrão fora dela) e o voltar do navegador troca de aba; os atalhos de período
// gravam `de`/`ate` e o padrão (7 d) some da URL. As histórias acrescentam os cards.

const ABAS = ["Visão geral", "Quando postar", "O que funciona", "Curvas", "Contas", "Funil", "Mercado", "Alertas"];

test("019 base: 8 abas, aba e período na URL", async ({ page }) => {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.getByRole("link", { name: "Métricas" }).click();
  await expect(page).toHaveURL(/\/app\/metricas$/);

  const abas = page.getByRole("tablist", { name: "Seções do analytics" }).getByRole("tab");
  await expect(abas).toHaveText(ABAS);
  await expect(page.getByRole("tab", { name: "Visão geral" })).toHaveAttribute("aria-selected", "true");

  // ---- a URL escolhe a aba; clicar grava ?aba=; o padrão some; voltar desfaz ----
  await page.goto("/app/metricas?aba=funil");
  await expect(page.getByRole("tab", { name: "Funil" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel").getByRole("heading", { name: "Funil de produção" })).toBeVisible();
  await page.getByRole("tab", { name: "Curvas" }).click();
  await expect(page).toHaveURL(/[?&]aba=curvas\b/);
  await expect(page.getByRole("tab", { name: "Curvas" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Visão geral" }).click();
  await expect(page).not.toHaveURL(/aba=/);
  await page.goBack();
  await expect(page.getByRole("tab", { name: "Curvas" })).toHaveAttribute("aria-selected", "true");
  await page.goto("/app/metricas?aba=inexistente");
  await expect(page.getByRole("tab", { name: "Visão geral" })).toHaveAttribute("aria-selected", "true");

  // ---- período: 7 d é o padrão (fora da URL); 30 d grava de/ate ----
  const atalhos = page.getByRole("group", { name: "Atalhos de período" });
  await expect(atalhos.getByRole("button", { name: "7 d" })).toHaveAttribute("aria-pressed", "true");
  await atalhos.getByRole("button", { name: "30 d" }).click();
  await expect(page).toHaveURL(/[?&]de=\d{4}-\d{2}-\d{2}.*&ate=\d{4}-\d{2}-\d{2}/);
  await expect(atalhos.getByRole("button", { name: "30 d" })).toHaveAttribute("aria-pressed", "true");
  await atalhos.getByRole("button", { name: "7 d" }).click();
  await expect(page).not.toHaveURL(/[?&](de|ate)=/);

  // ---- medida do post: o padrão (24 h) fora da URL ----
  await page.getByLabel("Medida do post").selectOption("h1");
  await expect(page).toHaveURL(/[?&]medida=h1\b/);
  await page.getByLabel("Medida do post").selectOption("h24");
  await expect(page).not.toHaveURL(/medida=/);
});

// ---- T057: transversais (FR-005, FR-006, FR-008, FR-009; SC-005, SC-006) ----

// Perfil e conta próprios, com 3 vídeos de 2–3 dias semeados por SQL (série, vídeos e fotos de
// 1 h a 48 h): a Visão geral filtrada nesta conta tem "Views por dia" e "Principais vídeos".
async function semearConta(request: APIRequestContext) {
  const sfx = Date.now().toString(36);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Transversal ${sfx}`, slug: `transversal-${sfx}` });
  const res = await request.post(`/api/perfis/${perfilId}/contas`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { platform: "tiktok", handle: `transversal${sfx}`, status: "ativa" },
  });
  expect(res.status(), `POST contas: ${await res.text()}`).toBe(201);
  const contaId = ((await res.json()) as { conta: { id: string } }).conta.id;
  sqlE2e(
    `with s as (insert into metricas_series (id, rede, conta_id) values (gen_random_uuid(), 'tiktok', '${contaId}') returning id),` +
      ` v as (insert into metricas_videos (id, serie_id, rede_video_id, legenda, duracao_s, publicado_em, descoberto_em)` +
      ` select gen_random_uuid(), s.id, (7480000000000000000 + floor(random() * 1e12)::bigint + g)::text, 'Transversal ${sfx} n' || g, 30,` +
      ` now() - (40 + g * 8) * interval '1 hour', now() - (40 + g * 8) * interval '1 hour' from s, generate_series(1, 3) g returning id, publicado_em)` +
      ` insert into metricas_video_fotos (video_id, coletado_em, idade_s, alvo_idade_min, views, likes, comments, shares)` +
      ` select v.id, v.publicado_em + h * interval '1 hour', h * 3600, h * 60, h * 100 + floor(random() * 50)::int, h * 5, h, h` +
      ` from v, unnest(array[1, 2, 6, 12, 24, 36]) h`,
  );
  return { perfilId, contaId, sfx };
}

function vigiarCsp(page: Page): string[] {
  const erros: string[] = [];
  const csp = /Content Security Policy|Refused to (evaluate|execute|load|apply)/i;
  page.on("console", (m) => {
    if (m.type() === "error" && csp.test(m.text())) erros.push(m.text());
  });
  page.on("pageerror", (e) => {
    if (csp.test(e.message)) erros.push(e.message);
  });
  return erros;
}

const SLUGS = ["visao-geral", "quando-postar", "o-que-funciona", "curvas", "contas", "funil", "mercado", "alertas"];

test("019 transversal: só GET em /api/analytics nas 8 abas, sem erro de CSP", async ({ page, request }) => {
  const { perfilId, contaId } = await semearConta(request);
  const csp = vigiarCsp(page);
  const reprovadas: string[] = [];
  const lidas = new Set<string>();
  await page.route("**/api/**", (route) => {
    const req = route.request();
    const caminho = new URL(req.url()).pathname;
    if (req.method() !== "GET" && !caminho.startsWith("/api/auth/")) {
      reprovadas.push(`${req.method()} ${caminho}`);
      return route.abort();
    }
    const aba = /^\/api\/analytics\/([a-z-]+)$/.exec(caminho)?.[1];
    // "ordem-contas" não é aba: é a ordem da cor fixa por conta, lida uma vez por todas as abas
    if (aba && aba !== "ordem-contas") lidas.add(aba);
    return route.continue();
  });
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/metricas?perfil=${perfilId}&conta=${contaId}`);
  const erros: string[] = [];
  page.on("pageerror", (e) => erros.push(e.message));
  for (const nome of ABAS) {
    // "Alertas" ganha o contador no rótulo
    const aba = page.getByRole("tablist", { name: "Seções do analytics" }).getByRole("tab", { name: new RegExp(`^${nome}`) });
    await aba.click();
    await expect(aba, `aba ${nome} (${erros.join(" | ")})`).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel").locator("section[data-card]").first()).toBeVisible();
    await expect(page.getByRole("tabpanel").locator(".animate-pulse")).toHaveCount(0);
  }
  expect([...lidas].sort(), "uma leitura por aba").toEqual([...SLUGS].sort());
  expect(reprovadas, "nenhuma escrita a partir do analytics").toEqual([]);
  expect(csp, "erros de CSP no console").toEqual([]);
});

test("019 transversal: 390 px sem rolagem horizontal da página, com as views nas tabelas", async ({ page, request }) => {
  const { perfilId, contaId } = await semearConta(request);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  for (const slug of SLUGS) {
    await page.goto(`/app/metricas?perfil=${perfilId}&conta=${contaId}${slug === "visao-geral" ? "" : `&aba=${slug}`}`);
    await expect(page.getByRole("tabpanel").locator("section[data-card]").first()).toBeVisible();
    await expect(page.getByRole("tabpanel").locator(".animate-pulse")).toHaveCount(0);
    const { scroll, client } = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(scroll, `rolagem horizontal em ${slug}`).toBeLessThanOrEqual(client);
  }
  await page.goto(`/app/metricas?perfil=${perfilId}&conta=${contaId}`);
  const card = page.locator('section[data-card="Principais vídeos"]');
  await card.getByRole("button", { name: "Ver tabela" }).click();
  await expect(card.getByRole("columnheader", { name: "Views no período" })).toBeVisible();
  // no celular, as colunas secundárias somem: ficam o vídeo e as views
  const celulas = card.getByRole("row").nth(1).getByRole("cell");
  await expect(celulas).toHaveCount(2);
  await expect(celulas.last()).toHaveText(/^\d[\d.,]*$/);
  const { scroll, client } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(scroll, "rolagem horizontal com a tabela aberta").toBeLessThanOrEqual(client);
});

test("019 transversal: \"Ver tabela\" por teclado e \"CSV\" igual à tabela", async ({ page, request }) => {
  const { perfilId, contaId, sfx } = await semearConta(request);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/metricas?perfil=${perfilId}&conta=${contaId}`);
  const card = page.locator('section[data-card="Principais vídeos"]');
  await expect(card.getByText(`Transversal ${sfx} n1`)).toBeVisible();

  // ---- teclado: foco no botão, Enter alterna gráfico ⇄ tabela ----
  const verTabela = card.getByRole("button", { name: "Ver tabela" });
  await verTabela.focus();
  await expect(verTabela).toBeFocused();
  await page.keyboard.press("Enter");
  const tabela = card.getByRole("table", { name: "Principais vídeos" });
  await expect(tabela).toBeVisible();
  await expect(card.getByRole("button", { name: "Ver gráfico" })).toHaveAttribute("aria-pressed", "true");
  await expect(card.getByRole("button", { name: "Ver gráfico" })).toBeFocused();
  await page.keyboard.press("Space");
  await expect(tabela).toHaveCount(0);
  await page.keyboard.press("Enter");
  await expect(tabela).toBeVisible();

  // ---- CSV: cabeçalho = colunas da tabela; 1ª linha = 1ª linha da tabela ----
  const [download] = await Promise.all([page.waitForEvent("download"), card.getByRole("button", { name: "CSV" }).click()]);
  expect(download.suggestedFilename()).toBe("principais-videos.csv");
  const csv = (await readFile((await download.path())!, "utf8")).replace(/^﻿/, "");
  const [cabecalho, primeira] = csv.split("\r\n");
  const colunas = (await tabela.getByRole("columnheader").allTextContents()).map((t) => t.trim());
  expect(cabecalho).toBe(colunas.join(","));
  const celulas = (await tabela.getByRole("row").nth(1).getByRole("cell").allTextContents()).map((t) => t.trim());
  const campos = primeira.split(",");
  expect(campos[0], "título").toBe(celulas[0]);
  expect(campos[1], "o @ da conta sai limpo, sem apóstrofo").toMatch(/^@transversal/);
  expect(campos[1]).toBe(celulas[1]);
  expect(Number(campos[3]).toLocaleString("pt-BR"), "views no período").toBe(celulas[3]);
  expect(campos[6], "id do vídeo").toBe(celulas[6]);

  // ---- injeção de fórmula: texto que começa com "=" sai com apóstrofo; números seguem números ----
  sqlE2e(`update metricas_videos set legenda = '=1+1 Formula ${sfx}' where legenda = 'Transversal ${sfx} n2'`);
  await page.reload();
  await card.getByRole("button", { name: "Ver tabela" }).click();
  await expect(tabela.getByRole("cell", { name: `=1+1 Formula ${sfx}`, exact: true })).toBeVisible();
  const [download2] = await Promise.all([page.waitForEvent("download"), card.getByRole("button", { name: "CSV" }).click()]);
  const linhas2 = (await readFile((await download2.path())!, "utf8")).split("\r\n");
  const formula = linhas2.find((l) => l.includes(`Formula ${sfx}`));
  expect(formula?.split(",")[0], "fórmula neutralizada").toBe(`'=1+1 Formula ${sfx}`);
  expect(formula?.split(",")[3], "views continuam número").toMatch(/^\d+$/);
});

test("019 transversal: trocar o tema muda as cores dos gráficos sem recarregar", async ({ page, request }) => {
  const { perfilId, contaId } = await semearConta(request);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const escolherTema = async (tema: "Claro" | "Escuro") => {
    await page.getByRole("button", { name: "Conta", exact: true }).click();
    await page.getByRole("menuitemradio", { name: tema }).click();
    await page.keyboard.press("Escape");
  };
  await page.goto(`/app/metricas?perfil=${perfilId}&conta=${contaId}`);
  await escolherTema("Claro");
  const svg = page.locator('section[data-card="Views por dia"] [_echarts_instance_] svg').first();
  await expect(svg).toBeVisible();
  const cores = () =>
    svg.evaluate((el) =>
      [...el.querySelectorAll("[stroke],[fill]")]
        .flatMap((n) => [n.getAttribute("stroke"), n.getAttribute("fill")])
        .filter((c): c is string => Boolean(c) && c !== "none" && c !== "transparent")
        .sort()
        .join(" "),
    );
  const claro = await cores();
  await page.evaluate(() => ((window as unknown as { __semRecarga: boolean }).__semRecarga = true));
  await escolherTema("Escuro");
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await expect.poll(cores, { message: "as cores do gráfico mudam com o tema" }).not.toBe(claro);
  expect(await page.evaluate(() => (window as unknown as { __semRecarga?: boolean }).__semRecarga), "sem recarregar").toBe(true);
  await escolherTema("Claro");
  await expect.poll(cores, { message: "e voltam no claro" }).toBe(claro);
});
