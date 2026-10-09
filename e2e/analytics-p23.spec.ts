import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, login, logout, sqlE2e } from "./helpers";

// Spec 019, abas P2/P3 (T039, T043, T047, T051, T055): Curvas, Contas, Funil, Mercado e Alertas na
// stack isolada. Os dados são semeados por INSERT no banco efêmero (séries, vídeos e fotos da 016,
// envios, canal-fonte e vídeo-fonte), sem conexão com a TikTok: o analytics só lê. Cada teste cria o
// próprio perfil e filtra por ele.

const SHOTS = ".playwright-mcp/sociman";

type Auth = { Authorization: string };

async function perfilComContas(request: APIRequestContext, nome: string, redes: ("tiktok" | "youtube")[] = ["tiktok"]) {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth: Auth = { Authorization: `Bearer ${token}` };
  const sfx = randomUUID().slice(0, 6);
  const perfilId = await createPerfilViaApi(request, token, { name: `${nome} ${sfx}`, slug: `${nome.toLowerCase()}-${sfx}` });
  const contas: { id: string; handle: string }[] = [];
  for (const platform of redes) {
    const handle = `${nome.toLowerCase()}${platform.slice(0, 2)}${sfx}`;
    const res = await request.post(`/api/perfis/${perfilId}/contas`, { headers: auth, data: { platform, handle, status: "ativa" } });
    expect(res.status(), `POST contas: ${await res.text()}`).toBe(201);
    contas.push({ id: ((await res.json()) as { conta: { id: string } }).conta.id, handle });
  }
  return { perfilId, contas, auth };
}

interface VideoSemente {
  legenda: string;
  /** publicado há N horas */
  pubH: number;
  /** [idade em horas, views acumuladas] */
  fotos: [number, number][];
}

// Uma série viva da conta com os vídeos e as fotos (INSERT, como a 016 semeia o histórico).
function semearSerie(contaId: string, rede: "tiktok" | "youtube", videos: VideoSemente[]): string[] {
  const [serieId] = sqlE2e(`insert into metricas_series (id, rede, conta_id) values (gen_random_uuid(), '${rede}', '${contaId}') returning id`);
  return videos.map((v, i) => {
    const [videoId] = sqlE2e(
      `insert into metricas_videos (id, serie_id, rede_video_id, share_url, legenda, duracao_s, publicado_em, descoberto_em) ` +
        `values (gen_random_uuid(), '${serieId}', '${Date.now()}${i}', 'https://www.tiktok.com/@e2e/video/${Date.now()}${i}', ` +
        `'${v.legenda}', 30, now() - interval '${v.pubH} hours', now() - interval '${v.pubH} hours') returning id`,
    );
    for (const [idadeH, views] of v.fotos) foto(videoId!, idadeH, views);
    return videoId!;
  });
}

function foto(videoId: string, idadeH: number, views: number): void {
  const idadeS = Math.round(idadeH * 3600);
  sqlE2e(
    `insert into metricas_video_fotos (video_id, coletado_em, idade_s, alvo_idade_min, views, likes, comments, shares) ` +
      `select id, publicado_em + interval '${idadeS} seconds', ${idadeS}, ${Math.floor(idadeS / 60)}, ${views}, ${Math.round(views / 10)}, 1, 1 ` +
      `from metricas_videos where id = '${videoId}'`,
  );
}

const ABA: Record<string, string> = { curvas: "Curvas", contas: "Contas", funil: "Funil", mercado: "Fontes", alertas: "Alertas" };

async function abrirAba(page: Page, aba: string, perfilId: string): Promise<void> {
  await page.goto(`/app/metricas?aba=${aba}&perfil=${perfilId}`);
  await expect(page.getByRole("tab", { selected: true })).toContainText(ABA[aba]!);
}

// o <div role="img"> do Grafico (o SVG do ECharts dentro dele também tem role img)
const GRAFICO = 'div[role="img"][aria-label]';
const card = (page: Page, titulo: string) => page.locator(`section[data-card="${titulo}"]`);

test("019 US4: curvas alinhadas pela idade, com um vídeo em destaque escolhido pela lista", async ({ page, request }) => {
  const { perfilId, contas } = await perfilComContas(request, "Curvas");
  const conta = `@${contas[0]!.handle}`;
  semearSerie(contas[0]!.id, "tiktok", [
    { legenda: "Curva alfa e2e", pubH: 30, fotos: [[1, 50], [6, 300], [24, 900]] },
    { legenda: "Curva beta e2e", pubH: 50, fotos: [[1, 10], [6, 40], [24, 120]] },
    { legenda: "Curva gama e2e", pubH: 70, fotos: [[1, 200], [6, 1500], [24, 4000]] },
  ]);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrirAba(page, "curvas", perfilId);

  const curvas = card(page, "Curvas de crescimento");
  const grafico = curvas.locator(GRAFICO).first();
  await expect(grafico).toHaveAttribute("aria-label", /Views por idade de 3 vídeos.*Em destaque: "/);

  // trocar o destaque pela lista muda o aria-label e a tabela alternativa
  await page.getByLabel("Vídeo em destaque").selectOption({ label: `Curva beta e2e (${conta})` });
  await expect(grafico).toHaveAttribute("aria-label", /Em destaque: "Curva beta e2e"/);
  await curvas.getByRole("button", { name: "Ver tabela" }).click();
  const linhaBeta = curvas.getByRole("row", { name: /Curva beta e2e/ });
  await expect(linhaBeta).toContainText("sim");
  await expect(curvas.getByRole("row", { name: /Curva gama e2e/ })).toContainText("não");
  // vídeos com menos de 7 dias: meia-vida "ainda não calculável"
  await expect(linhaBeta).toContainText("ainda não calculável");

  await page.getByLabel("Vídeo em destaque").selectOption({ label: `Curva gama e2e (${conta})` });
  await expect(curvas.getByRole("row", { name: /Curva gama e2e/ })).toContainText("sim");
  await expect(card(page, "Distribuição por conta")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${SHOTS}/019-curvas-390.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "sem rolagem horizontal em 390 px").toBe(true);
});

test("019 US5: com duas contas, o radar aparece; clicar na conta aplica ?conta= e mostra a trilha", async ({ page, request }) => {
  const { perfilId, contas } = await perfilComContas(request, "Radar", ["tiktok", "youtube"]);
  semearSerie(contas[0]!.id, "tiktok", [
    { legenda: "Radar tiktok um", pubH: 30, fotos: [[1, 100], [24, 800]] },
    { legenda: "Radar tiktok dois", pubH: 54, fotos: [[1, 80], [24, 600]] },
  ]);
  semearSerie(contas[1]!.id, "youtube", [{ legenda: "Radar youtube um", pubH: 40, fotos: [[1, 20], [24, 150]] }]);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrirAba(page, "contas", perfilId);

  const radar = card(page, "Radar contra a média");
  await expect(radar.locator(GRAFICO).first()).toHaveAttribute("aria-label", /Radar de @.* contra a média das contas \(100\)/);
  await radar.getByRole("button", { name: "Ver tabela" }).click();
  await expect(radar.getByRole("columnheader", { name: "Índice" })).toBeVisible();
  await expect(radar.getByRole("row", { name: /Views por post/ })).toBeVisible();

  const segunda = contas[1]!;
  await card(page, "Comparação entre contas").getByRole("button", { name: `Ver @${segunda.handle}` }).click();
  await expect(page).toHaveURL(new RegExp(`[?&]conta=${segunda.id}`));
  const trilha = page.getByRole("navigation", { name: "Trilha da conta" });
  await expect(trilha).toContainText(`@${segunda.handle}`);
  // a trilha volta à aba Contas sem a conta
  await trilha.getByRole("link", { name: "Contas" }).click();
  await expect(page).not.toHaveURL(/[?&]conta=/);
  await expect(page.getByRole("tab", { name: "Contas" })).toHaveAttribute("aria-selected", "true");
});

test("019 US6: funil com as perdas; o membro não vê o custo de IA e a API manda null", async ({ page, request }) => {
  const { perfilId } = await perfilComContas(request, "Funil");
  // `config` completa, como o envio real grava: a lista de gerações (/api/envios) valida a config
  // de cada envio na saída, e uma incompleta derrubaria a lista dos outros testes.
  const config = JSON.stringify({ clip_min_s: 15, clip_max_s: 60, quantidade: null, layout: "auto", formato: "vertical", legenda: "kit", marca_automatica: false, kit_version: null });
  for (const status of ["sem_clipes", "falhou"]) {
    sqlE2e(
      `insert into envios (id, perfil_id, origem, source_url, source_title, status, config, direito_no_envio, aviso_confirmado, sent_at, started_at, finished_at) ` +
        `values (gen_random_uuid(), '${perfilId}', 'avulso_link', 'https://www.youtube.com/watch?v=e2eFunil${status.slice(0, 3)}', ` +
        `'Envio ${status}', '${status}', '${config}'::jsonb, 'avulso', true, now() - interval '1 day', now() - interval '1 day', now() - interval '23 hours')`,
    );
  }

  // dono: funil, sankey e custo
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrirAba(page, "funil", perfilId);
  const funil = card(page, "Funil de produção");
  await expect(funil.locator(GRAFICO).first()).toHaveAttribute("aria-label", /Vídeos-fonte enviados 2/);
  await funil.getByRole("button", { name: "Ver tabela" }).click();
  await expect(funil.getByRole("row", { name: /Vídeos-fonte enviados/ })).toContainText("sem clipes: 1");
  await expect(card(page, "Para onde vai o material").locator(GRAFICO).first()).toHaveAttribute("aria-label", /sem clipes: 1/);
  await expect(page.getByRole("heading", { name: "Custo de IA" })).toBeVisible();
  // o patamar mexe na consulta (parâmetro `patamar`)
  const comPatamar = page.waitForRequest((r) => r.url().includes("/api/analytics/funil") && r.url().includes("patamar=50"));
  await page.getByLabel("Patamar de views em 24 h").fill("50");
  await comPatamar;
  await logout(page);

  // membro: sem custo na tela e null na API
  const membro = await createVerifiedMember(page);
  await login(page, membro.email, membro.final);
  await expect(page).toHaveURL(/\/app$/);
  await abrirAba(page, "funil", perfilId);
  await expect(card(page, "Funil de produção").locator(GRAFICO).first()).toHaveAttribute("aria-label", /Vídeos-fonte enviados 2/);
  await expect(page.getByRole("heading", { name: "Custo de IA" })).toHaveCount(0);
  await expect(page.getByText("Custo por mil views")).toHaveCount(0);
  const token = await apiToken(request, membro.email, membro.final);
  const res = await request.get(`/api/analytics/funil?perfilId=${perfilId}`, { headers: { Authorization: `Bearer ${token}` } });
  expect(res.status()).toBe(200);
  const corpo = (await res.json()) as { custoIaUsd: unknown; custoPorMilViewsUsd: unknown; etapas: unknown[] };
  expect(corpo.custoIaUsd).toBeNull();
  expect(corpo.custoPorMilViewsUsd).toBeNull();
  expect(corpo.etapas.length).toBeGreaterThan(0);
});

test("019 US7: oportunidade de canal sem acordo leva ao Descobrir e o aviso de direito aparece como sempre", async ({ page, request }) => {
  const { perfilId } = await perfilComContas(request, "Mercado");
  const n = randomUUID().replace(/-/g, "").slice(0, 22);
  // sem sync nem métricas agendadas (a trilha `sync` não mexe no canal semeado)
  const [canalId] = sqlE2e(
    `insert into canais_fonte (id, youtube_channel_id, title, uploads_playlist_id, direito, next_sync_at) ` +
      `values (gen_random_uuid(), 'UC${n}', 'Canal Mercado e2e', 'UU${n}', 'sem_acordo', now() + interval '30 days') returning id`,
  );
  sqlE2e(`insert into canal_perfis (canal_id, perfil_id) values ('${canalId}', '${perfilId}')`);
  const titulo = "Oportunidade quente e2e";
  const [videoId] = sqlE2e(
    `insert into videos_fonte (id, canal_id, youtube_video_id, title, published_at, views, vph_recente, duration_s, next_metrics_at, score, recomendavel) ` +
      `values (gen_random_uuid(), '${canalId}', 'e2eMerc${n.slice(0, 4)}', '${titulo}', now() - interval '10 hours', 5000, 500, 1200, now() + interval '30 days', 60, true) returning id`,
  );

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrirAba(page, "mercado", perfilId);

  const item = page.locator(`[data-oportunidade="${videoId}"]`);
  await expect(item).toContainText(titulo);
  await expect(item.getByText("Sem acordo", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${SHOTS}/019-mercado-390.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "sem rolagem horizontal em 390 px").toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  await item.getByRole("link", { name: `Gerar cortes: ${titulo}` }).click();
  await expect(page).toHaveURL(new RegExp(`/app/descobrir\\?.*video=${videoId}`));
  await expect(page).toHaveURL(new RegExp(`[?&]perfil=${perfilId}`));

  // o vídeo aparece em destaque, com o selo de direito; a seleção e a geração são as de sempre
  const destaque = page.getByRole("region", { name: "Vídeo escolhido nas métricas" });
  await expect(destaque).toContainText(titulo);
  await expect(destaque.getByText("Sem acordo", { exact: true }).first()).toBeVisible();
  await destaque.getByRole("button", { name: `Selecionar para corte: ${titulo}` }).click();
  await expect(destaque.getByRole("button", { name: `Desfazer seleção: ${titulo}` })).toBeVisible();
  const barra = page.getByRole("region", { name: "Selecionados" });
  await expect(barra).toContainText("1 vídeo selecionado");
  await barra.getByRole("button", { name: "Gerar cortes" }).click();
  const enviar = page.getByRole("dialog", { name: "Gerar cortes" });
  await enviar.getByRole("button", { name: "Gerar cortes de 1 vídeo" }).click();
  const aviso = page.getByRole("alertdialog");
  await expect(aviso).toContainText("O direito autoral deste vídeo é de sua responsabilidade");
  await expect(aviso).toContainText(titulo);
  await page.screenshot({ path: `${SHOTS}/019-mercado-aviso.png`, fullPage: true });
  // o analytics não pula o aviso: cancelar não envia nada
  await aviso.getByRole("button", { name: "Cancelar" }).click();
  expect(sqlE2e(`select status from envios where video_fonte_id = '${videoId}' and archived_at is null`)).toEqual(["selecionado"]);
});

test("019 US8: vídeo com 0 view depois de 6 h aparece como estagnado e some com uma foto com views", async ({ page, request }) => {
  const { perfilId, contas } = await perfilComContas(request, "Alerta");
  const [videoId] = semearSerie(contas[0]!.id, "tiktok", [{ legenda: "Post parado e2e", pubH: 8, fotos: [[1, 0], [7, 0]] }]);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrirAba(page, "alertas", perfilId);

  await expect(page.getByRole("tab", { name: "Alertas (1)" })).toBeVisible();
  const alerta = page.locator('[data-alerta="estagnado"]');
  await expect(alerta).toHaveCount(1);
  await expect(alerta).toContainText("Atenção:");
  await expect(alerta).toContainText("Post estagnado");
  await expect(alerta).toContainText("Post parado e2e");
  await expect(alerta).toContainText("Confira no app");
  await expect(alerta.getByRole("link", { name: "Abrir o vídeo" })).toHaveAttribute("href", `/app/metricas/videos/${videoId}`);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${SHOTS}/019-alertas-390.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "sem rolagem horizontal em 390 px").toBe(true);

  // a condição deixa de valer: nada foi gravado, o alerta some sozinho
  foto(videoId!, 7.9, 500);
  await page.reload();
  await expect(page.getByText("Nenhum alerta")).toBeVisible();
  await expect(page.locator('[data-alerta="estagnado"]')).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Alertas", exact: true })).toBeVisible();
});
