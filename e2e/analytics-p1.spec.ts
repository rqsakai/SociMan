import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, login, sqlE2e } from "./helpers";

// Spec 019, histórias P1 (T027, T031, T035): Visão geral, Quando postar e O que funciona, com
// métricas semeadas por INSERT na stack efêmera (série, vídeos e fotos; o trigger das fotos aceita
// INSERT). Cada teste cria o próprio perfil e conta e filtra a tela por eles (?perfil&conta), então
// os dados dos outros testes não entram. As datas são relativas a hoje no fuso de São Paulo.
//
// Semeadura (a mesma nos 3 testes): 6 vídeos já com o marco de 24 h e 1 vídeo de 2 h (aguardando).
//   A: 3 dias atrás 19:00, 1 h = 100, 24 h = 1000, #comum   (o único vinculado a um destino)
//   B..E: 2/4/5/6 dias atrás 10:00, 24 h = 400/300/200/100, #comum
//   F: 2 dias atrás 14:00, 24 h = 50, #raro (n = 1 < 5: fora do lift)
//   G: há 2 h, 1 h = 30 (aguardando o marco de 24 h)

const SHOTS = ".playwright-mcp/sociman";
const TZ = "America/Sao_Paulo";

interface Video {
  letra: string;
  dias: number | null; // null: há 2 h
  hora: number;
  v1: number;
  v24: number | null;
  tag: string;
  duracao: number;
}

const VIDEOS: Video[] = [
  { letra: "A", dias: 3, hora: 19, v1: 100, v24: 1000, tag: "comum", duracao: 45 },
  { letra: "B", dias: 2, hora: 10, v1: 40, v24: 400, tag: "comum", duracao: 30 },
  { letra: "C", dias: 4, hora: 10, v1: 30, v24: 300, tag: "comum", duracao: 30 },
  { letra: "D", dias: 5, hora: 10, v1: 20, v24: 200, tag: "comum", duracao: 30 },
  { letra: "E", dias: 6, hora: 10, v1: 10, v24: 100, tag: "comum", duracao: 30 },
  { letra: "F", dias: 2, hora: 14, v1: 5, v24: 50, tag: "raro", duracao: 20 },
  { letra: "G", dias: null, hora: 0, v1: 30, v24: null, tag: "comum", duracao: 20 },
];
const VIEWS_TOTAL = VIDEOS.reduce((t, v) => t + (v.v24 ?? v.v1), 0); // 2080

interface Cena {
  perfilId: string;
  contaId: string;
  sfx: string;
  ids: Record<string, string>;
  url: (extra?: string) => string;
}

// spec 024: a medida do post fica em "Mais filtros" (Sheet); escolhe e fecha a gaveta.
async function escolherMedida(page: Page, valor: "h1" | "h24" | "d7"): Promise<void> {
  await page.getByRole("button", { name: /^Mais filtros/ }).click();
  const gaveta = page.getByRole("dialog", { name: "Mais filtros" });
  await gaveta.getByLabel("Medida do post").selectOption(valor);
  await page.keyboard.press("Escape");
  await expect(gaveta).toBeHidden();
}

async function semear(request: APIRequestContext, nome: string): Promise<Cena> {
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `${nome} ${sfx}`, slug: `${nome.toLowerCase()}-${sfx}` });
  const res = await request.post(`/api/perfis/${perfilId}/contas`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { platform: "tiktok", handle: `${nome.toLowerCase()}${sfx}`, status: "ativa" },
  });
  expect(res.status(), `POST contas: ${await res.text()}`).toBe(201);
  const contaId = ((await res.json()) as { conta: { id: string } }).conta.id;

  const base = 7_460_000_000_000_000_000n + BigInt(Number.parseInt(sfx, 16)) * 100n;
  const rid = (i: number) => String(base + BigInt(i));
  const pub = (v: Video) =>
    v.dias === null
      ? "now() - interval '2 hours'"
      : `(date_trunc('day', now() at time zone '${TZ}') - make_interval(days => ${v.dias}) + make_interval(hours => ${v.hora})) at time zone '${TZ}'`;
  const valores = VIDEOS.map((v, i) => `('${rid(i)}', 'Post ${v.letra} ${sfx} #${v.tag}', ${v.duracao}, ${pub(v)}, ${v.v1}, ${v.v24 ?? "null"})`).join(", ");
  sqlE2e(
    `with s as (insert into metricas_series (id, rede, conta_id) values (gen_random_uuid(), 'tiktok', '${contaId}') returning id), ` +
      `x(rid, leg, dur, pub, v1, v24) as (values ${valores}), ` +
      `v as (insert into metricas_videos (id, serie_id, rede_video_id, share_url, legenda, duracao_s, publicado_em, descoberto_em) ` +
      `select gen_random_uuid(), s.id, x.rid, 'https://www.tiktok.com/@e2e/video/' || x.rid, x.leg, x.dur, x.pub, x.pub from s, x returning id, rede_video_id, publicado_em) ` +
      `insert into metricas_video_fotos (video_id, coletado_em, idade_s, alvo_idade_min, views, likes, comments, shares) ` +
      `select v.id, v.publicado_em + make_interval(mins => f.alvo), f.alvo * 60, f.alvo, f.views, f.views / 10, f.views / 100, f.views / 200 ` +
      `from v join x on x.rid = v.rede_video_id cross join lateral (values (60, x.v1), (1440, x.v24)) as f(alvo, views) where f.views is not null`,
  );
  const linhas = sqlE2e(`select rede_video_id || '|' || id from metricas_videos where rede_video_id in (${VIDEOS.map((_, i) => `'${rid(i)}'`).join(", ")})`);
  const ids: Record<string, string> = {};
  for (const l of linhas) {
    const [r, id] = l.split("|");
    ids[VIDEOS[Number(BigInt(r!) - base)]!.letra] = id!;
  }
  expect(Object.keys(ids).sort()).toEqual(VIDEOS.map((v) => v.letra));

  // A vira um post do SociMan: vídeo próprio → destino Postado (lembrete) → vínculo "escolha"
  sqlE2e(
    `with c as (insert into conteudos (id, perfil_id, origem, titulo, video_key, poster_key, duration_ms) ` +
      `values (gen_random_uuid(), '${perfilId}', 'video_proprio', 'Post A ${sfx}', 'e2e/${sfx}/a.mp4', 'e2e/${sfx}/a.jpg', 45000) returning id), ` +
      `d as (insert into postagens (id, conta_id, conteudo_id, estado, modo, hashtags, aprovado_em, posted_at) ` +
      `select gen_random_uuid(), '${contaId}', c.id, 'postado', 'lembrete', '{comum}', now(), (select publicado_em from metricas_videos where id = '${ids.A}') from c returning id) ` +
      `update metricas_videos set destino_id = d.id, vinculo_metodo = 'escolha', vinculado_em = now() from d where metricas_videos.id = '${ids.A}'`,
  );
  return { perfilId, contaId, sfx, ids, url: (extra = "") => `/app/metricas?perfil=${perfilId}&conta=${contaId}${extra}` };
}

async function analytics<T>(request: APIRequestContext, aba: string, c: Cena, extra = ""): Promise<T> {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const res = await request.get(`/api/analytics/${aba}?perfilId=${c.perfilId}&contaId=${c.contaId}${extra}`, { headers: { Authorization: `Bearer ${token}` } });
  expect(res.status(), await res.text()).toBe(200);
  return (await res.json()) as T;
}

const card = (page: Page, titulo: string): Locator => page.locator(`section[data-card="${titulo}"]`);

async function verTabela(c: Locator): Promise<Locator> {
  await c.getByRole("button", { name: "Ver tabela" }).click();
  return c.getByRole("table");
}

const DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
// dia da semana (0 = segunda) e hora em SP de um vídeo semeado
function diaHora(id: string): { dia: string; hora: string } {
  const [l] = sqlE2e(`select (extract(isodow from publicado_em at time zone '${TZ}')::int - 1) || '|' || extract(hour from publicado_em at time zone '${TZ}')::int from metricas_videos where id = '${id}'`);
  const [d, h] = l!.split("|").map(Number);
  return { dia: DIAS[d!]!, hora: `${String(h).padStart(2, "0")}h–${String((h! + 1) % 24).padStart(2, "0")}h` };
}

// ---------------------------------------------------------------------------------------------
// US1 (T027)
// ---------------------------------------------------------------------------------------------
test("019 US1: indicadores batem com a semeadura, 30 d na URL com voltar e período vazio", async ({ page, request }) => {
  test.setTimeout(120_000);
  const c = await semear(request, "Visao");

  type Ind = { chave: string; valor: number | null; anterior: number | null };
  const api = await analytics<{ indicadores: Ind[]; contexto: { aguardando: number } }>(request, "visao-geral", c);
  const ind = Object.fromEntries(api.indicadores.map((i) => [i.chave, i]));
  expect(ind.views!.valor, "views ganhas = soma das últimas fotos").toBe(VIEWS_TOTAL);
  expect(ind.posts!.valor).toBe(7);
  expect(ind.mediana_post!.valor, "mediana de 24 h de A..F").toBe(250);
  expect(api.contexto.aguardando).toBe(1);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(c.url());
  const views = page.locator('[data-indicador="Views ganhas"]');
  await expect(views).toContainText("2.080");
  await expect(views).toContainText("sem base de comparação");
  await expect(page.locator('[data-indicador="Posts publicados"]')).toContainText("7");
  await expect(page.locator('[data-indicador="Mediana por post (24 h)"]')).toContainText("250");
  await expect(page.locator('[data-indicador="Mediana por post (24 h)"]')).toContainText("1 aguardando o marco");

  // série diária: o gráfico e a tabela alternativa (com o CSV) somam as views
  const serie = card(page, "Views por dia");
  await expect(serie.getByRole("img", { name: /Views ganhas por dia/ })).toBeVisible();
  await expect(serie.getByRole("img", { name: /Views ganhas por dia/ })).toHaveAttribute("aria-label", /Total: 2\.080/);
  await expect(serie.getByRole("button", { name: "CSV" })).toBeVisible();

  // principais: A no topo, com link para o detalhe do vídeo
  const principais = card(page, "Principais vídeos");
  const primeiro = principais.getByRole("listitem").first();
  await expect(primeiro).toContainText(`Post A ${c.sfx}`);
  await expect(primeiro.getByRole("link")).toHaveAttribute("href", `/app/metricas/videos/${c.ids.A}`);

  // ranking da 016 dentro do card, com o período e a conta do filtro global: os 7, A no topo;
  // a ordem continua mudando pelo "Ordenar por" (na URL)
  const ranking = card(page, "Ranking");
  const linhasRanking = ranking.getByRole("table", { name: "Ranking de vídeos" }).getByRole("row");
  await expect(linhasRanking).toHaveCount(8);
  await expect(linhasRanking.nth(1)).toContainText(`Post A ${c.sfx}`);
  await expect(linhasRanking.nth(1)).toContainText("1.000");
  await expect(ranking.getByRole("group", { name: "Publicado" })).toHaveCount(0);
  await ranking.getByLabel("Direção").selectOption("asc");
  await expect(page).toHaveURL(/[?&]direcao=asc\b/);
  await expect(linhasRanking.nth(1)).toContainText(`Post G ${c.sfx}`);
  await ranking.getByLabel("Direção").selectOption("desc");

  // insights: as regras aparecem, as sem amostra dizem que falta
  await expect(card(page, "Insights").locator("[data-insight]").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/019-visao-geral.png`, fullPage: true });

  // ---- 30 d grava de/ate; voltar restaura os 7 d ----
  const atalhos = page.getByRole("group", { name: "Atalhos de período" });
  await atalhos.getByRole("button", { name: "30 d" }).click();
  await expect(page).toHaveURL(/[?&]de=\d{4}-\d{2}-\d{2}/);
  await expect(atalhos.getByRole("button", { name: "30 d" })).toHaveAttribute("aria-pressed", "true");
  await expect(views).toContainText("2.080");
  await page.goBack();
  await expect(page).not.toHaveURL(/[?&]de=/);
  await expect(atalhos.getByRole("button", { name: "7 d" })).toHaveAttribute("aria-pressed", "true");

  // ---- período sem dado: estado vazio com "Ampliar período" ----
  await page.goto(c.url("&de=2020-01-01&ate=2020-01-07"));
  await expect(serie.getByRole("status")).toContainText("Nenhuma view ganha neste período.");
  await expect(serie.getByRole("button", { name: "Ampliar período" })).toBeVisible();
  await expect(card(page, "Principais vídeos").getByRole("status")).toBeVisible();
  await expect(card(page, "Ranking")).toContainText("Nenhum vídeo coletado neste filtro.");

  // ---- celular: indicadores em 2 colunas, sem rolagem horizontal da página ----
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(c.url());
  await expect(views).toContainText("2.080");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: `${SHOTS}/019-visao-geral-celular.png`, fullPage: true });
});

// ---------------------------------------------------------------------------------------------
// US2 (T031)
// ---------------------------------------------------------------------------------------------
test("019 US2: célula do mapa com o valor e o n certos; a medida 1 h muda valores e aguardando", async ({ page, request }) => {
  test.setTimeout(120_000);
  const c = await semear(request, "Quando");
  const a = diaHora(c.ids.A!);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(c.url("&aba=quando-postar"));
  const mapa = card(page, "Desempenho por horário de publicação");
  await expect(mapa.getByRole("img", { name: /Mapa de calor/ })).toBeVisible();
  await expect(mapa).toContainText("Horário de Brasília");
  await expect(mapa).toContainText("Aguardando o marco (fora do mapa): 1.");
  await page.screenshot({ path: `${SHOTS}/019-quando-postar.png`, fullPage: true });

  let tabela = await verTabela(mapa);
  let linhaA = tabela.getByRole("row").filter({ hasText: a.dia }).filter({ hasText: a.hora });
  await expect(linhaA).toHaveCount(1);
  await expect(linhaA.getByRole("cell").nth(2)).toHaveText("1.000");
  await expect(linhaA.getByRole("cell").nth(3)).toHaveText("1");

  // audiência: o ganho da 1ª hora tem hora; o de 1 h → 24 h fica "sem hora atribuída"
  const audiencia = card(page, "Audiência por hora");
  await expect(audiencia.locator("[data-sem-hora]")).toContainText("sem hora atribuída");

  // calendário com os dias semeados
  const cal = card(page, "Calendário");
  await expect(cal.getByRole("img", { name: /Calendário de/ })).toHaveAttribute("aria-label", /7 posts/);

  // ---- medida 1 h: a célula de A vira 100 e G sai do "aguardando" ----
  await escolherMedida(page, "h1");
  await expect(page).toHaveURL(/[?&]medida=h1\b/);
  await expect(mapa).not.toContainText("Aguardando o marco");
  await expect(mapa).toContainText("Mediana de views em 1 h");
  tabela = mapa.getByRole("table");
  if (!(await tabela.isVisible())) tabela = await verTabela(mapa);
  linhaA = tabela.getByRole("row").filter({ hasText: a.dia }).filter({ hasText: a.hora });
  await expect(linhaA.getByRole("cell").nth(2)).toHaveText("100");
  const api = await analytics<{ contexto: { aguardando: number } }>(request, "quando-postar", c, "&medida=h1");
  expect(api.contexto.aguardando).toBe(0);

  // ---- celular: o mapa rola dentro do card, nunca a página ----
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(c.url("&aba=quando-postar"));
  await expect(mapa.getByRole("img", { name: /Mapa de calor/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  expect(await mapa.locator("[data-mapa-semana]").evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
  // card no celular: os botões numa linha abaixo do título e o "Como ler" com a largura do card
  const titulo = (await mapa.getByRole("heading").boundingBox())!;
  const botao = (await mapa.getByRole("button", { name: "Ver tabela" }).boundingBox())!;
  const comoLer = (await mapa.getByText("Como ler:").locator("..").boundingBox())!;
  const caixa = (await mapa.boundingBox())!;
  expect(botao.y).toBeGreaterThanOrEqual(titulo.y + titulo.height - 1);
  expect(comoLer.y).toBeGreaterThanOrEqual(botao.y + botao.height - 1);
  expect(comoLer.width).toBeGreaterThan(caixa.width - 48);
  await page.screenshot({ path: `${SHOTS}/019-quando-postar-celular.png`, fullPage: true });
});

// ---------------------------------------------------------------------------------------------
// US3 (T035)
// ---------------------------------------------------------------------------------------------
test("019 US3: clicar num ponto abre o vídeo; hashtag com n < 5 fica fora do lift", async ({ page, request }) => {
  test.setTimeout(120_000);
  const c = await semear(request, "Funciona");

  type Linha = { rotulo: string; n: number; lift: number | null };
  const api = await analytics<{ hashtags: Linha[]; excluidosSemVinculo: number; dispersoes: { duracao: { pontos: { videoId: string }[] } } }>(request, "o-que-funciona", c);
  expect(api.hashtags.map((h) => h.rotulo)).toEqual(["#comum"]);
  expect(api.dispersoes.duracao.pontos.map((p) => p.videoId)).toEqual([c.ids.A]);
  expect(api.excluidosSemVinculo).toBe(6);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(c.url("&aba=o-que-funciona"));
  await expect(page.locator("[data-excluidos]")).toContainText("fora das análises de corte: 6");

  const duracao = card(page, "Duração × desempenho");
  await expect(duracao.locator("[data-correlacao]")).toContainText("Correlação só com 8 vídeos ou mais (faltam 7)");
  await expect(duracao.locator("[data-amostra=pequena]")).toContainText("amostra pequena (n = 1 de 8)");

  // hashtags: #comum (n = 6) está no lift; #raro (n = 1) não
  const hashtags = card(page, "Hashtags");
  await expect(hashtags.getByRole("img", { name: /Lift das hashtags/ })).toHaveAttribute("aria-label", /#comum/);
  const tabela = await verTabela(hashtags);
  await expect(tabela).toContainText("#comum");
  await expect(tabela).not.toContainText("#raro");
  await hashtags.getByRole("button", { name: "Ver gráfico" }).click();
  await page.screenshot({ path: `${SHOTS}/019-o-que-funciona.png`, fullPage: true });

  // ---- o único ponto da dispersão (o vídeo A): clicar abre o detalhe ----
  const grafico = duracao.getByRole("img", { name: /Dispersão de duração/ });
  await expect(grafico).toBeVisible();
  const centro = await grafico.evaluate((el) => {
    // os símbolos do scatter são os <path> preenchidos e pequenos do SVG (eixos e grade não têm fill)
    const caixa = el.getBoundingClientRect();
    const alvos = [...el.querySelectorAll("path")]
      .filter((p) => p.getAttribute("fill") && p.getAttribute("fill") !== "none")
      .map((p) => p.getBoundingClientRect())
      .filter((r) => r.width >= 6 && r.width <= 24 && Math.abs(r.width - r.height) < 2);
    const r = alvos[0];
    return r ? { x: r.x + r.width / 2 - caixa.x, y: r.y + r.height / 2 - caixa.y, n: alvos.length } : null;
  });
  expect(centro, "o ponto do vídeo A no SVG").not.toBeNull();
  expect(centro!.n).toBe(1);
  await grafico.click({ position: { x: centro!.x, y: centro!.y } });
  await expect(page).toHaveURL(new RegExp(`/app/metricas/videos/${c.ids.A}$`));
});
