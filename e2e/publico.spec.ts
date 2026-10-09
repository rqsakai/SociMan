import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import {
  apiToken,
  createPerfilViaApi,
  csvGenero,
  login,
  sqlE2e,
  zipsPublico,
  type ItemDistribuicao,
  type LinhaAtividade,
  type LinhaEspectadores,
} from "./helpers";

// Spec 022 (T026, T029, T037, T041): o público do TikTok Studio. Todos os arquivos são SINTÉTICOS
// (zipsPublico: os 3 CSVs no formato da 020 e um Viewers.xlsx de verdade, montados em memória);
// nunca o arquivo real do dono. A série da 016 é semeada por SQL (sem coleta). As datas são
// relativas a hoje no fuso de São Paulo, sempre antes de hoje (o Studio ignora o dia corrente).

const SHOTS = ".playwright-mcp/sociman";

const hoje = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
function dia(delta: number): string {
  const [y, m, d] = hoje().split("-").map(Number);
  return new Date(Date.UTC(y!, m! - 1, d! + delta)).toISOString().slice(0, 10);
}
const br = (d: string) => d.split("-").reverse().join("/");

// Histórico de seguidores de `de` a `ate` (deltas), crescendo 1 por dia.
const historico = (de: number, ate: number) => Array.from({ length: ate - de + 1 }, (_, i) => ({ dia: dia(de + i), seguidores: 120 + i }));

// Duas fotos: a antiga (histórico até −11 → foto de −10) e a nova (histórico até −3 → foto de −2).
const GENERO_ANTIGO: ItemDistribuicao[] = [
  { rotulo: "Female", pct: "58%" },
  { rotulo: "Male", pct: "40%" },
  { rotulo: "Other", pct: "2%" },
];
const GENERO_NOVO: ItemDistribuicao[] = [
  { rotulo: "Female", pct: "61%" },
  { rotulo: "Male", pct: "37.5%" },
  { rotulo: "Other", pct: "1.5%" },
];
const TERRITORIOS_ANTIGO: ItemDistribuicao[] = [
  { rotulo: "BR", pct: "90%" },
  { rotulo: "PT", pct: "5%" },
];
const TERRITORIOS_NOVO: ItemDistribuicao[] = [
  { rotulo: "BR", pct: "92.5%" },
  { rotulo: "PT", pct: "4%" },
  { rotulo: "US", pct: "2%" },
];
// 14 dias × 24 horas; o valor só depende da hora (a média de qualquer célula é 100 + hora).
const ATIVIDADE: LinhaAtividade[] = Array.from({ length: 14 }, (_, d) => Array.from({ length: 24 }, (_, h) => ({ dia: dia(-14 + d), hora: h, ativos: 100 + h }))).flat();
// Os espectadores do arquivo real (o 1º dia "undefined"), em datas inventadas: −7 … −1.
const TOTAL = ["undefined", 104, 181, 1, 2, 3, 663] as const;
const NOVOS = [0, 104, 181, 1, 2, 3, 622];
const RECORRENTES = [0, 0, 0, 0, 0, 0, 41];
const ESPECTADORES: LinhaEspectadores[] = TOTAL.map((t, i) => ({ dia: dia(-7 + i), total: t, novos: NOVOS[i]!, recorrentes: RECORRENTES[i]! }));

interface Conta {
  perfilId: string;
  contaId: string;
  handle: string;
}

async function contaComSerie(request: APIRequestContext, nome = "Publico"): Promise<Conta> {
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `${nome} ${sfx}`, slug: `${nome.toLowerCase()}-${sfx}` });
  const handle = `${nome.toLowerCase()}_${sfx}`;
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

// Importa pela API (prévia → confirmar), como o dono faria na tela; usado para semear o analytics.
async function importarPelaApi(request: APIRequestContext, contaId: string, arquivos: Arquivo[]) {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const form = new FormData();
  for (const a of arquivos) form.append("arquivos", new Blob([new Uint8Array(a.buffer)], { type: a.mimeType }), a.name);
  const previa = await request.post(`/api/contas/${contaId}/studio/previa`, { headers: { Authorization: `Bearer ${token}` }, multipart: form });
  expect(previa.status(), `prévia: ${await previa.text()}`).toBe(201);
  const { previaId } = (await previa.json()) as { previaId: string };
  const conf = await request.post(`/api/contas/${contaId}/studio/importacoes`, { headers: { Authorization: `Bearer ${token}` }, data: { previaId, confirmoConta: false } });
  expect(conf.status(), `confirmar: ${await conf.text()}`).toBe(201);
}

// As duas exportações da conta: a antiga (só gênero e territórios) e a nova (tudo).
async function semearPublico(request: APIRequestContext, c: Conta) {
  const antiga = zipsPublico(c.handle, historico(-17, -11), { genero: GENERO_ANTIGO, territorios: TERRITORIOS_ANTIGO });
  await importarPelaApi(request, c.contaId, [antiga.seguidores]);
  const nova = zipsPublico(c.handle, historico(-9, -3), { genero: GENERO_NOVO, territorios: TERRITORIOS_NOVO, atividade: ATIVIDADE, espectadores: ESPECTADORES });
  await importarPelaApi(request, c.contaId, [nova.seguidores, nova.espectadores]);
}

async function lerArquivos(page: Page, arquivos: Arquivo[]) {
  const importar = page.getByRole("region", { name: "Importar" });
  await importar.getByLabel("Arquivos do Studio").setInputFiles(arquivos);
  await importar.getByRole("button", { name: "Ler arquivos" }).click();
}

const previa = (page: Page) => page.locator("[data-previa]");
const importacoes = (page: Page) => page.getByRole("region", { name: "Importações" });
const card = (page: Page, titulo: string) => page.locator(`section[data-card="${titulo}"]`);
const semRolagem = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);

async function baixarCsv(c: Locator): Promise<string[]> {
  const page = c.page();
  const [download] = await Promise.all([page.waitForEvent("download"), c.getByRole("button", { name: "CSV" }).click()]);
  return (await readFile((await download.path())!, "utf8")).replace(/^﻿/, "").trimEnd().split("\r\n");
}

test("022 US1/US2: prévia e importação do público, já importado, vazias e recusas", async ({ page, request }) => {
  test.setTimeout(180_000);
  const c = await contaComSerie(request);
  const zips = zipsPublico(c.handle, historico(-9, -3), { genero: GENERO_NOVO, territorios: TERRITORIOS_NOVO, atividade: ATIVIDADE, espectadores: ESPECTADORES });

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/contas/${c.contaId}/studio`);
  await expect(importacoes(page)).toContainText("Nenhuma importação nesta conta.");

  // ---- US2: recusas, nada gravado ----
  // a planilha com fórmula cita a célula
  const comFormula = zipsPublico(c.handle, historico(-9, -3), { espectadores: ESPECTADORES, defeitoXlsx: "formula" });
  await lerArquivos(page, [comFormula.espectadores]);
  await expect(page.locator('[data-erro-studio="studio_planilha"]')).toContainText("B3");
  await expect(previa(page)).toHaveCount(0);
  // gênero com soma 80%
  await lerArquivos(page, [
    {
      name: "FollowerGender.csv",
      mimeType: "text/csv",
      buffer: csvGenero([
        { rotulo: "Female", pct: "50%" },
        { rotulo: "Male", pct: "30%" },
      ]),
    },
  ]);
  await expect(page.locator('[data-erro-studio="studio_invalido"]')).toBeVisible();
  await expect(page.locator('[data-erro-studio="studio_invalido"]')).toContainText("FollowerGender.csv");
  // só o cabeçalho: "sem dados de público"
  await lerArquivos(page, [{ name: "FollowerGender.csv", mimeType: "text/csv", buffer: csvGenero([]) }]);
  await expect(page.locator('[data-erro-studio="studio_sem_dados"]')).toContainText(/100/);
  await expect(importacoes(page)).toContainText("Nenhuma importação nesta conta.");

  // ---- US1: os 2 ZIPs → prévia com o público (nada gravado) → confirmar ----
  await lerArquivos(page, [zips.seguidores, zips.espectadores]);
  const p = previa(page);
  await expect(p.locator('[data-secao="seguidores"]')).toBeVisible();
  // a foto é o dia seguinte ao último do histórico (−3 + 1)
  await expect(p.locator('[data-secao="genero"] [data-data-foto]')).toContainText(br(dia(-2)));
  await expect(p.locator('[data-secao="genero"]')).toContainText("Feminino");
  await expect(p.locator('[data-secao="genero"]')).toContainText("61%");
  await expect(p.locator('[data-secao="territorios"]')).toContainText("92,5%");
  await expect(p.locator('[data-secao="atividade"] [data-pico]')).toContainText("123");
  await expect(p.locator('[data-secao="atividade"]')).toContainText(`${br(dia(-14))} a ${br(dia(-1))}`);
  await expect(p.locator('[data-secao="espectadores"]')).toContainText("sem dado");
  await expect(p.locator('[data-secao="espectadores"]')).toContainText("913");
  await expect(importacoes(page)).toContainText("Nenhuma importação nesta conta.");
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(previa(page)).toHaveCount(0);
  const ativa = importacoes(page).locator('[data-importacao="ativa"]');
  await expect(ativa).toHaveCount(1);
  await expect(ativa).toContainText("Espectadores");
  await expect(ativa).toContainText("Atividade dos seguidores");
  await expect(ativa).toContainText(`foto de ${br(dia(-2))}`);
  await expect(page.locator("[data-cobertura]")).toContainText("Fotos de público");
  await expect(page.locator('[data-cobertura] [data-cobertura-secao="espectadores"]')).toBeVisible();

  // ---- reenviar: "já importado" em todas as seções, sem confirmar ----
  await lerArquivos(page, [zips.seguidores, zips.espectadores]);
  await expect(previa(page).locator("[data-ja-importado]")).toBeVisible();
  await expect(previa(page).locator("[data-ja-importada]")).toHaveCount(5);
  await expect(page.getByRole("button", { name: "Confirmar importação" })).toHaveCount(0);
  await page.getByRole("button", { name: "Fechar" }).click();

  // ---- o real: os 3 CSVs só com o cabeçalho → "ainda sem dados de público", anotados na importação ----
  const vazio = zipsPublico(c.handle, historico(-30, -24), {});
  await lerArquivos(page, [vazio.seguidores]);
  await expect(previa(page).locator("[data-sem-dados-publico]")).toHaveCount(3);
  await expect(previa(page).locator("[data-sem-dados-publico]").first()).toContainText("cerca de 100");
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(importacoes(page).locator('[data-importacao="ativa"]')).toHaveCount(2);
  await expect(importacoes(page).locator("[data-secoes-vazias]").first()).toContainText("Gênero");

  // ---- celular: sem rolagem horizontal, com a prévia aberta ----
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await lerArquivos(page, [zips.seguidores, zips.espectadores]);
  await expect(previa(page)).toBeVisible();
  expect(await semRolagem(page)).toBe(true);
  await page.screenshot({ path: `${SHOTS}/022-previa-celular.png`, fullPage: true });
});

test("022 US3: aba Público com as fotos, o mapa, os espectadores, a tabela, o CSV e os estados vazios", async ({ page, request }) => {
  test.setTimeout(240_000);
  const c = await contaComSerie(request);
  await semearPublico(request, c);
  const vazia = await contaComSerie(request, "Vazia");
  await importarPelaApi(request, vazia.contaId, [zipsPublico(vazia.handle, historico(-9, -3), {}).seguidores]);
  const nada = await contaComSerie(request, "Nada");

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const url = (conta: Conta, extra = "") => `/app/metricas?aba=publico&perfil=${conta.perfilId}&conta=${conta.contaId}${extra}`;

  // ---- de −7 a hoje: a aba vem da URL; os 7 dias de espectadores e de atividade entram ----
  await page.goto(url(c, `&de=${dia(-7)}`));
  await expect(page.getByRole("tab", { name: "Público" })).toHaveAttribute("aria-selected", "true");

  // gênero: a foto de −2 (dentro do período), comparada com a de −10, em p.p.
  const genero = card(page, "Gênero dos seguidores");
  await expect(genero).toContainText("TikTok Studio");
  await expect(genero.locator("[data-data-foto]")).toContainText(`Foto de ${br(dia(-2))}`);
  await expect(genero).toContainText(`comparada com a de ${br(dia(-10))}`);
  await expect(genero).toContainText("61% · ▲ 3 p.p.");
  await expect(genero).toContainText("37,5% · ▼ 2,5 p.p.");
  await genero.getByRole("button", { name: "Ver tabela" }).click();
  for (const col of ["data_foto", "rotulo", "pct", "dif_pp"]) await expect(genero.getByRole("columnheader", { name: col, exact: true })).toBeVisible();
  await expect(genero.getByRole("cell", { name: "Feminino" })).toBeVisible();
  const csvGen = await baixarCsv(genero);
  expect(csvGen[0]).toBe("fonte,data_foto,rotulo,pct,pct_comparacao,dif_pp");
  expect(csvGen).toContain(`studio,${dia(-2)},Feminino,61,58,3`);

  // territórios: o novo país e "Outros"
  const territorios = card(page, "Territórios dos seguidores");
  await expect(territorios).toContainText("2% · novo");
  await expect(territorios).toContainText("Outros");
  await expect(territorios).toContainText("1,5%");

  // atividade: 7 dias no período, n = 1 em cada célula → amostra pequena; a nota das horas
  const atividade = card(page, "Atividade dos seguidores");
  await expect(atividade.locator("[data-nota-horas]")).toContainText("Horas conforme a TikTok");
  await expect(atividade.locator("[data-dias-cobertos]")).toContainText("7 dias");
  await atividade.getByRole("button", { name: "Ver tabela" }).click();
  const celula = atividade.getByRole("row").filter({ hasText: "20h–21h" }).first();
  await expect(celula).toContainText("120");
  await expect(celula).toContainText("sim");

  // espectadores: buraco no "sem dado", os novos somados e as médias diárias
  const esp = card(page, "Espectadores");
  await expect(esp.locator('[data-indicador="Novos espectadores (soma)"]')).toContainText("913");
  await expect(esp.locator('[data-indicador="Espectadores por dia (média)"]')).toContainText("159");
  await expect(esp.locator('[data-indicador="Recorrentes por dia (média)"]')).toContainText("5,9");
  await expect(esp.locator("[data-dias-cobertos]")).toContainText('1 "sem dado"');
  const csvEsp = await baixarCsv(esp);
  expect(csvEsp[0]).toBe("fonte,dia,total,novos,recorrentes");
  expect(csvEsp).toContain(`studio,${dia(-7)},,0,0`);
  await page.screenshot({ path: `${SHOTS}/022-publico.png`, fullPage: true });

  // ---- paleta: as barras usam um tom só da rampa sequencial, e mudam com o tema ----
  const barras = genero.locator("[_echarts_instance_] svg").first();
  await genero.getByRole("button", { name: "Ver gráfico" }).click();
  await expect(barras).toBeVisible();
  const corDasBarras = () =>
    barras.evaluate((el) => {
      const cores = new Set([...el.querySelectorAll("path[fill]")].map((n) => n.getAttribute("fill")!).filter((c) => c !== "none" && c !== "transparent"));
      return [...cores].sort().join(" ");
    });
  const escolherTema = async (tema: "Claro" | "Escuro") => {
    await page.getByRole("button", { name: "Conta", exact: true }).click();
    await page.getByRole("menuitemradio", { name: tema }).click();
    await page.keyboard.press("Escape");
  };
  await escolherTema("Claro");
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
  await expect.poll(async () => (await corDasBarras()).split(" ").length, { message: "um tom só nas barras" }).toBe(1);
  const claro = await corDasBarras();
  await escolherTema("Escuro");
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await expect.poll(corDasBarras).not.toBe(claro);
  expect((await corDasBarras()).split(" ").length).toBe(1);
  await escolherTema("Claro");

  // ---- 14 dias (−13 a hoje): 13 dias de atividade; a foto de −2 continua, sem comparação (nada antes de −13) ----
  await page.getByRole("button", { name: "14 d", exact: true }).click();
  await expect(atividade.locator("[data-dias-cobertos]")).toContainText("13 dias");
  await expect(genero).toContainText("sem foto anterior para comparar");

  // ---- foto anterior ao período (24 h: ontem e hoje) ----
  await page.getByRole("button", { name: "24 h", exact: true }).click();
  await expect(genero.locator("[data-anterior-ao-periodo]")).toBeVisible();

  // ---- período sem atividade → atalho "ver os últimos dias com dado" ----
  await page.goto(url(c, `&de=${dia(-60)}&ate=${dia(-50)}`));
  await atividade.getByRole("button", { name: "Ver os últimos dias com dado" }).click();
  await expect(page).toHaveURL(new RegExp(`de=${dia(-7)}&ate=${dia(-1)}|ate=${dia(-1)}&de=${dia(-7)}|de=${dia(-7)}.*ate=${dia(-1)}`));
  await expect(atividade.locator("[data-dias-cobertos]")).toContainText("7 dias");

  // ---- estados vazios: veio vazia e nenhuma importação, com o atalho do dono ----
  await page.goto(url(vazia));
  await expect(card(page, "Gênero dos seguidores")).toContainText("Ainda sem dados de público");
  await expect(card(page, "Atividade dos seguidores")).toContainText("Ainda sem dados de público");
  await expect(card(page, "Gênero dos seguidores").getByRole("link", { name: "Histórico do Studio" })).toBeVisible();
  await page.goto(url(nada));
  for (const t of ["Gênero dos seguidores", "Territórios dos seguidores", "Atividade dos seguidores", "Espectadores"]) {
    await expect(card(page, t)).toContainText("Nenhuma importação de público ainda.");
  }
  await card(page, "Espectadores").getByRole("link", { name: "Histórico do Studio" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/contas/${nada.contaId}/studio$`));

  // ---- celular: uma coluna, sem rolagem horizontal; o mapa rola dentro do card ----
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url(c, "&de=" + dia(-13)));
  await expect(card(page, "Atividade dos seguidores").locator("[data-mapa-semana]")).toBeVisible();
  expect(await semRolagem(page)).toBe(true);
  expect(await card(page, "Atividade dos seguidores").locator("[data-mapa-semana]").evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
  await page.screenshot({ path: `${SHOTS}/022-publico-celular.png`, fullPage: true });
});

test("022 US4: o 3º mapa de Quando postar é o mesmo da aba Público; sem dado, o estado vazio", async ({ page, request }) => {
  test.setTimeout(180_000);
  const c = await contaComSerie(request);
  await semearPublico(request, c);
  const nada = await contaComSerie(request, "Nada");

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const filtro = (conta: Conta) => `perfil=${conta.perfilId}&conta=${conta.contaId}&de=${dia(-13)}&ate=${hoje()}`;

  await page.goto(`/app/metricas?aba=publico&${filtro(c)}`);
  const doPublico = await baixarCsv(card(page, "Atividade dos seguidores"));

  await page.goto(`/app/metricas?aba=quando-postar&${filtro(c)}`);
  const terceiro = card(page, "Seguidores on-line (TikTok Studio)");
  await expect(terceiro.locator("[data-nota-horas]")).toContainText("Horas conforme a TikTok");
  await expect(terceiro.locator("[data-dias-cobertos]")).toContainText("13 dias");
  expect(await baixarCsv(terceiro)).toEqual(doPublico);
  // os dois mapas da 019 continuam lá
  await expect(card(page, "Desempenho por horário de publicação")).toBeVisible();
  await expect(card(page, "Audiência por hora")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/022-quando-postar.png`, fullPage: true });

  await page.goto(`/app/metricas?aba=quando-postar&${filtro(nada)}`);
  await expect(card(page, "Seguidores on-line (TikTok Studio)")).toContainText("Nenhuma importação de público ainda.");
  await expect(card(page, "Seguidores on-line (TikTok Studio)").getByRole("link", { name: "Histórico do Studio" })).toBeVisible();
  await expect(card(page, "Desempenho por horário de publicação")).toBeVisible();
});
