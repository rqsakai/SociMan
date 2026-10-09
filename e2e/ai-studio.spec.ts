import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, compose, createPerfilViaApi, login, nav } from "./helpers";

// Spec 029 (T019, T026, T030, T033): AI Studio, a biblioteca da agência com perfil base opcional.
// - US1: o grupo AI Studio no menu; as listas com itens de 2 perfis e sem perfil; o filtro de perfil
//   base na URL; Movimentos "em breve";
// - US2: criar um cenário sem perfil, gerar a cena (o pedido grava "sem perfil") e trocar o perfil
//   base pelo cabeçalho;
// - US3: uma cena do perfil B com um cenário do perfil A e um avatar criado pelo "+ Novo avatar";
// - US4: os links antigos das abas do perfil redirecionam e o card "Ver no AI Studio" conta.

type Auth = { Authorization: string };

const ITENS = ["Avatares", "Cenários", "Vozes", "Produtos", "Cenas", "Assets", "Movimentos"];

function geracaoFake(metodo: "GET" | "POST", caminho: string, corpo?: unknown): unknown {
  const script = [
    "import json, sys, urllib.request",
    "corpo = sys.stdin.read().encode() or None",
    `req = urllib.request.Request("http://localhost:8000${caminho}", data=corpo, method="${metodo}",`,
    "                             headers={'content-type': 'application/json'})",
    "print(urllib.request.urlopen(req, timeout=5).read().decode())",
  ].join("\n");
  return JSON.parse(compose(["exec", "-T", "openshorts-fake", "python", "-c", script], corpo === undefined ? "" : JSON.stringify(corpo)));
}

async function base(request: APIRequestContext): Promise<{ auth: Auth; sfx: string; a: string; b: string; nomeA: string; nomeB: string }> {
  const sfx = randomUUID().slice(0, 6);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const nomeA = `Studio A ${sfx}`;
  const nomeB = `Studio B ${sfx}`;
  const a = await createPerfilViaApi(request, token, { name: nomeA, slug: `studio-a-${sfx}` });
  const b = await createPerfilViaApi(request, token, { name: nomeB, slug: `studio-b-${sfx}` });
  return { auth: { Authorization: `Bearer ${token}` }, sfx, a, b, nomeA, nomeB };
}

async function asset(request: APIRequestContext, auth: Auth, data: Record<string, unknown>): Promise<string> {
  const r = await request.post("/api/assets", { headers: auth, data: { tags: [], ...data } });
  expect(r.status(), `asset: ${await r.text()}`).toBe(201);
  return ((await r.json()) as { asset: { id: string } }).asset.id;
}

async function entrar(page: Page, caminho?: string): Promise<void> {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  if (caminho) await page.goto(caminho);
}

test.describe.configure({ mode: "serial" });

test("US1: menu AI Studio, listas da agência e filtro de perfil base", async ({ page, request }) => {
  const { auth, sfx, a, b, nomeA } = await base(request);
  await asset(request, auth, { tipo: "avatar", name: `Ana ${sfx}`, perfilId: a });
  await asset(request, auth, { tipo: "avatar", name: `Bia ${sfx}`, perfilId: b });
  await asset(request, auth, { tipo: "avatar", name: `Cris ${sfx}`, perfilId: null });
  await entrar(page);
  const menu = page.getByRole("navigation", { name: "Menu principal" });
  for (const item of ITENS) await expect(menu.getByRole("link", { name: item, exact: true })).toBeVisible();

  await nav(page, "Avatares");
  await expect(page).toHaveURL(/\/app\/estudio\/avatares/);
  await expect(page.getByRole("heading", { level: 1, name: "Avatares" })).toBeVisible();
  for (const nome of ["Ana", "Bia", "Cris"]) await expect(page.getByText(`${nome} ${sfx}`)).toBeVisible();

  const filtro = page.getByTestId("filtro-perfil-base");
  await filtro.selectOption({ label: "Sem perfil" });
  await expect(page).toHaveURL(/perfil=sem/);
  await page.reload();
  await expect(page.getByText(`Cris ${sfx}`)).toBeVisible();
  await expect(page.getByText(`Ana ${sfx}`)).toBeHidden();
  await page.getByTestId("filtro-perfil-base").selectOption({ label: nomeA });
  await expect(page.getByText(`Ana ${sfx}`)).toBeVisible();
  await expect(page.getByText(`Cris ${sfx}`)).toBeHidden();

  await nav(page, "Movimentos");
  await expect(page.getByTestId("movimentos-em-breve")).toBeVisible();
});

test("US2: cenário sem perfil gera sem perfil base; o perfil base muda pelo cabeçalho", async ({ page, request }) => {
  const { auth, sfx, nomeA } = await base(request);
  geracaoFake("POST", "/geracao-e2e/gpu", { ocupada: false });
  geracaoFake("POST", "/geracao-e2e/lento", { segundos: 1 });
  await entrar(page, "/app/estudio/cenarios");
  await page.getByRole("button", { name: "Novo cenário" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Nome").fill(`Cozinha ${sfx}`);
  await dlg.getByTestId("perfil-base").selectOption({ label: "Nenhum" });
  await dlg.getByRole("button", { name: "Criar" }).click();
  await expect(page).toHaveURL(/\/app\/assets\/[0-9a-f-]{36}/, { timeout: 15_000 });
  const cenarioId = page.url().split("/").pop()!.split("?")[0]!;

  const form = page.getByTestId("pedir-geracao");
  await expect(form.getByText("Sem perfil base: só as regras do tipo, sem guia")).toBeVisible();
  await form.getByLabel("Instrução").fill("bright retro kitchen");
  await form.getByRole("button", { name: "Gerar" }).click();
  await expect(page.getByTestId("geracao-item").first().getByTestId("estado-geracao")).toHaveText("Em revisão", { timeout: 60_000 });
  const lista = await request.get(`/api/geracoes?alvoTipo=asset&alvoId=${cenarioId}`, { headers: auth });
  const geracoes = (await lista.json()) as { itens: { perfilId: string | null }[] };
  expect(geracoes.itens[0]!.perfilId).toBeNull();

  const editavel = page.getByTestId("perfil-base-editavel");
  await editavel.getByLabel("Perfil base").selectOption({ label: nomeA });
  await expect(page.getByText("Perfil base trocado.")).toBeVisible();
  const det = (await (await request.get(`/api/assets/${cenarioId}`, { headers: auth })).json()) as { asset: { perfilNome: string } };
  expect(det.asset.perfilNome).toBe(nomeA);
});

test("US3: cena do perfil B com cenário do perfil A e avatar criado no lugar", async ({ page, request }) => {
  const { auth, sfx, a, b, nomeA, nomeB } = await base(request);
  await asset(request, auth, { tipo: "cenario", name: `Varanda ${sfx}`, perfilId: a, prompt: "sunny balcony" });
  await entrar(page, `/app/estudio/cenas/nova?perfil=${b}`);
  await page.getByLabel("Nome da cena").fill(`Cena cruzada ${sfx}`);
  await page.getByLabel("Cenário", { exact: true }).selectOption({ label: `Varanda ${sfx} · ${nomeA}` });
  await page.getByLabel("Ação", { exact: true }).fill("waves to the camera");

  // "+ Novo avatar": cancelar não cria; criar volta escolhido e mantém a cena preenchida.
  await page.getByRole("button", { name: "Novo avatar" }).click();
  await page.getByRole("dialog").getByLabel("Nome").fill(`Descartado ${sfx}`);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.getByRole("button", { name: "Novo avatar" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Nome").fill(`Duda ${sfx}`);
  await dlg.getByRole("button", { name: "Criar" }).click();
  await expect(dlg).toBeHidden();
  await expect(page.getByLabel("Avatar", { exact: true }).locator("option:checked")).toHaveText(`Duda ${sfx} · ${nomeB}`);
  await expect(page.getByLabel("Nome da cena")).toHaveValue(`Cena cruzada ${sfx}`);
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/cenas\/[0-9a-f-]{36}$/, { timeout: 15_000 });

  const r = await request.get(`/api/assets?tipo=avatar&q=${encodeURIComponent(`Descartado ${sfx}`)}`, { headers: auth });
  expect(((await r.json()) as { items: unknown[] }).items).toHaveLength(0);
});

test("US4: links antigos redirecionam e o perfil mostra o card Ver no AI Studio", async ({ page, request }) => {
  const { auth, sfx, a } = await base(request);
  await asset(request, auth, { tipo: "avatar", name: `Eva ${sfx}`, perfilId: a });
  await entrar(page, `/app/perfis/${a}?aba=vozes`);
  await expect(page).toHaveURL(new RegExp(`/app/estudio/vozes\\?perfil=${a}`));
  await page.goto(`/app/perfis/${a}?aba=assets`);
  await expect(page).toHaveURL(new RegExp(`/app/estudio/assets\\?perfil=${a}`));
  await page.goto("/app/estudio");
  await expect(page).toHaveURL(/\/app\/estudio\/avatares/);

  await page.goto(`/app/perfis/${a}`);
  const card = page.getByTestId("ver-no-estudio");
  await expect(card.getByTestId("ver-no-estudio-avatares")).toContainText("1");
  await card.getByTestId("ver-no-estudio-avatares").click();
  await expect(page).toHaveURL(new RegExp(`/app/estudio/avatares\\?perfil=${a}`));
  await expect(page.getByText(`Eva ${sfx}`)).toBeVisible();
  await expect(page.getByRole("tab", { name: "Assets" })).toHaveCount(0);
});
