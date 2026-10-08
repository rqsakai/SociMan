import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, login, logout, nav, sqlE2e } from "./helpers";

// Spec 023 (T025, T035, T043): a área Aprendizado do perfil, página /app/aprendizado?perfil= desde a
// spec 024 (T029; o link antigo /app/perfis/:id/aprendizado redireciona).
// Os posts são semeados por SQL (série, vídeos e fotos de 1 h a 36 h, como no e2e da 019); os temas
// pela API do dono; as classificações "da IA" por SQL (a trilha e o Claude falso entram nos testes
// que dependem deles). A estatística é a da API: aqui só se confere o que a tela mostra.

interface Semeado {
  token: string;
  perfilId: string;
  /** a conta com amostra (16 posts entregues): efeitos, bloco e "não separável" */
  contaId: string;
  handle: string;
  /** a conta travada (5 de 8 estagnados) */
  travadaId: string;
  travadaHandle: string;
  temas: { marvel: string; dc: string; animes: string };
  /** os 5 estagnados da conta travada */
  estagnados: string[];
}

const MARVEL = "#multiversomarvel #vingadoresdoomsday #geek";

async function api<T>(request: APIRequestContext, token: string, method: "post" | "get" | "patch", url: string, data?: unknown): Promise<T> {
  const res = await request[method](url, { headers: { Authorization: `Bearer ${token}` }, data });
  expect(res.ok(), `${method.toUpperCase()} ${url}: ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

interface PostSemeado {
  legenda: string;
  tema: string;
  /** horas desde a publicação */
  idadeH: number;
  /** fotos [idade em h, views] */
  fotos: [number, number][];
}

// Série, vídeos, fotos e a classificação "da IA" (origem ia, evidência parcial) de uma conta, num
// só comando; devolve os ids dos vídeos na ordem dos posts.
function semearConta(perfilId: string, contaId: string, posts: PostSemeado[], classificar = true): string[] {
  const d = posts.map((p, g) => `(${g + 1}, '${p.legenda}', '${p.tema}'::uuid, ${p.idadeH})`).join(",");
  const f = posts.flatMap((p, g) => p.fotos.map(([h, v]) => `(${g + 1}, ${h}, ${v})`)).join(",");
  // o psql devolve as linhas do SELECT final; só os uuids interessam
  return sqlE2e(
    `with s as (insert into metricas_series (id, rede, conta_id) values (gen_random_uuid(), 'tiktok', '${contaId}') returning id),` +
      ` d(g, legenda, tema, idade_h) as (values ${d}),` +
      ` fv(g, h, views) as (values ${f}),` +
      ` v as (insert into metricas_videos (id, serie_id, rede_video_id, legenda, duracao_s, publicado_em, descoberto_em)` +
      ` select gen_random_uuid(), s.id, (7490000000000000000 + floor(random() * 1e12)::bigint + d.g)::text, d.legenda, 30,` +
      ` now() - d.idade_h * interval '1 hour', now() - d.idade_h * interval '1 hour' from s, d returning id, publicado_em, legenda),` +
      ` f as (insert into metricas_video_fotos (video_id, coletado_em, idade_s, alvo_idade_min, views, likes, comments, shares)` +
      ` select v.id, v.publicado_em + fv.h * interval '1 hour', fv.h * 3600, fv.h * 60, fv.views, 0, 0, 0` +
      ` from v join d on d.legenda = v.legenda join fv on fv.g = d.g returning video_id),` +
      ` c as (insert into aprendizado_classificacoes (id, video_id, perfil_id, tema_id, estilo_gancho, justificativa, origem, evidencia_parcial, taxonomia_versao)` +
      ` select gen_random_uuid(), v.id, '${perfilId}', d.tema, 'pergunta', 'Fala de ' || split_part(v.legenda, ' ', 1), 'ia', true, 3` +
      ` from v join d on d.legenda = v.legenda where ${classificar} returning video_id)` +
      ` select v.id from v join d on d.legenda = v.legenda where (select count(*) from f) > 0 and (select count(*) from c) >= 0 order by d.g`,
  ).filter((l) => /^[0-9a-f-]{36}$/.test(l));
}

const curva = (mult: number): [number, number][] => [1, 2, 6, 12, 24, 36].map((h) => [h, h * mult]);

// Perfil com 3 temas e 2 contas:
// - a conta com amostra: 16 posts entregues em 8 dias (6 de Marvel com o bloco das 3 hashtags,
//   4 de DC e 6 de Animes), todos com views (nenhum estagnado);
// - a conta travada: 3 posts com views e 5 com 0 view, cada um com uma foto só, em idades bem
//   distantes (menos de 5 referências na mesma idade: estagnado por "≤ 1 view"), 5 de 8 = 62%.
async function semear(request: APIRequestContext): Promise<Semeado> {
  const sfx = Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Aprendizado ${sfx}`, slug: `aprendizado-${sfx}` });
  // uma conta ativa por rede no perfil: a segunda entra pausada (as métricas dela continuam valendo)
  const conta = async (handle: string, status: "ativa" | "pausada") =>
    (await api<{ conta: { id: string } }>(request, token, "post", `/api/perfis/${perfilId}/contas`, { platform: "tiktok", handle, status })).conta.id;
  const handle = `aprende${sfx}`;
  const travadaHandle = `travada${sfx}`;
  const contaId = await conta(handle, "ativa");
  const travadaId = await conta(travadaHandle, "pausada");
  const tema = async (nome: string, palavrasChave: string[]) =>
    (await api<{ id: string }>(request, token, "post", `/api/perfis/${perfilId}/aprendizado/temas`, { nome, descricao: `Posts sobre ${nome}`, palavrasChave })).id;
  const temas = { marvel: await tema("Marvel", ["marvel", "vingadores"]), dc: await tema("DC", ["batman", "superman"]), animes: await tema("Animes", ["anime", "naruto"]) };

  const comAmostra: PostSemeado[] = [
    ...Array.from({ length: 6 }, (_, i) => ({ legenda: `Marvel ${sfx} ${i} ${MARVEL}`, tema: temas.marvel, mult: 15 + i })),
    ...Array.from({ length: 4 }, (_, i) => ({ legenda: `Batman ${sfx} ${i} #dc`, tema: temas.dc, mult: 8 + i })),
    ...Array.from({ length: 6 }, (_, i) => ({ legenda: `Naruto ${sfx} ${i} #anime`, tema: temas.animes, mult: 5 + i })),
  ].map((p, g) => ({ legenda: p.legenda, tema: p.tema, idadeH: 40 + g * 11, fotos: curva(p.mult) }));
  const ids = semearConta(perfilId, contaId, comAmostra);
  expect(ids).toHaveLength(16);

  const travada: PostSemeado[] = [
    ...Array.from({ length: 3 }, (_, i) => ({ legenda: `Goku ${sfx} ${i} #anime`, tema: temas.animes, idadeH: 31 + i, fotos: [1, 2, 6, 12, 24, 30].map((h) => [h, h * 10] as [number, number]) })),
    ...[60, 130, 250, 500, 900].map((h, i) => ({ legenda: `Sasuke ${sfx} ${i} #anime`, tema: temas.animes, idadeH: h + 1, fotos: [[h, 0]] as [number, number][] })),
  ];
  const idsTravada = semearConta(perfilId, travadaId, travada);
  expect(idsTravada).toHaveLength(8);
  return { token, perfilId, contaId, handle, travadaId, travadaHandle, temas, estagnados: idsTravada.slice(3) };
}

async function abrir(page: Page, perfilId: string, query = "") {
  await page.goto(`/app/aprendizado?perfil=${perfilId}${query.replace(/^\?/, "&")}`);
  // a rota é lazy (chunk do ECharts): no Vite de dev do e2e, a 1ª compilação pode demorar
  await expect(page.getByRole("heading", { name: /^Aprendizado:/ })).toBeVisible({ timeout: 20_000 });
}

const painel = (page: Page) => page.getByRole("tabpanel");

test("023 US2: travada, bloco de hashtags e não separável do tema, só com GET", async ({ page, request }) => {
  const s = await semear(request);
  const escritas: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url()).pathname;
    if (r.method() !== "GET" && u.startsWith("/api/") && !u.startsWith("/api/auth/")) escritas.push(`${r.method()} ${u}`);
  });
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  // spec 024: o link antigo do perfil redireciona para a página, preservando aba, conta e medida
  await page.goto(`/app/perfis/${s.perfilId}/aprendizado?aba=recomendacoes&conta=${s.contaId}&medida=d7`);
  await expect(page).toHaveURL(new RegExp(`/app/aprendizado\\?perfil=${s.perfilId}&aba=recomendacoes&conta=${s.contaId}&medida=d7$`));
  await expect(page.getByRole("tab", { name: "Recomendações" })).toHaveAttribute("aria-selected", "true");
  const filtros = page.getByRole("region", { name: "Filtros do aprendizado" });
  await expect(filtros.getByLabel("Conta", { exact: true })).toHaveValue(s.contaId);
  await expect(filtros.getByLabel("Medida do post")).toHaveValue("d7");
  // o perfil não tem mais o botão "Aprendizado"; a área abre pela página
  await page.goto(`/app/perfis/${s.perfilId}`);
  await expect(page.getByRole("tab", { name: "Dados", exact: true })).toBeVisible();
  await expect(page.locator("main").getByRole("link", { name: "Aprendizado", exact: true })).toHaveCount(0);
  await abrir(page, s.perfilId);
  await expect(page.getByRole("tab", { name: "Por que deu certo" })).toHaveAttribute("aria-selected", "true");

  // a conta com 5 de 8 estagnados: distribuição travada, com o link para o diagnóstico
  const travada = page.locator(`[data-travada="@${s.travadaHandle}"]`);
  await expect(travada).toBeVisible();
  await expect(travada).toContainText("Distribuição travada");
  await expect(page.locator("[data-exploratorio]")).toContainText("Exploratório");

  // as 3 hashtags da Marvel aparecem sempre juntas (um bloco) e não se separam do tema
  const blocos = painel(page).getByRole("list", { name: "Blocos de hashtags" });
  await expect(blocos.locator("li")).toContainText([/multiversomarvel.*vingadoresdoomsday.*geek|geek.*multiversomarvel/]);
  const blocoMarvel = painel(page).locator('[data-efeito^="hashtag:"]').filter({ hasText: "#multiversomarvel" }).first();
  await expect(blocoMarvel.locator('[data-aviso="nao_separavel"]')).toContainText("não separável do tema Marvel");
  // todo efeito mostra o n de posts distintos
  await expect(painel(page).locator("[data-efeito]").first()).toContainText("posts distintos");

  // a matriz hashtag × tema tem tabela alternativa
  const matriz = page.locator('section[data-card="Hashtag × tema"]');
  await matriz.getByRole("button", { name: "Ver tabela" }).click();
  await expect(matriz.getByRole("table")).toContainText("Marvel");

  // o link do aviso abre o diagnóstico da conta
  await travada.getByRole("link", { name: "Ver o diagnóstico" }).click();
  await expect(page).toHaveURL(/aba=diagnostico/);
  await expect(page.locator(`[data-conta="@${s.travadaHandle}"]`)).toBeVisible();
  await expect(page.getByRole("list", { name: "O que conferir no app" })).toBeVisible();
  expect(escritas, "a análise e o diagnóstico não escrevem nada").toEqual([]);
});


// Spec 024 (T029): o item Analytics › Aprendizado do menu abre no último perfil visto neste aparelho.
test("024: o item do menu abre o Aprendizado no último perfil", async ({ page, request }) => {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const sfx = Math.random().toString(36).slice(2, 8);
  const outro = await createPerfilViaApi(request, token, { name: `Ultimo ${sfx}`, slug: `ultimo-${sfx}` });
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrir(page, outro);
  await page.goto("/app");
  await nav(page, "Aprendizado");
  await expect(page).toHaveURL(new RegExp(`/app/aprendizado\\?perfil=${outro}$`));
  await expect(page.getByRole("heading", { name: `Aprendizado: Ultimo ${sfx}` })).toBeVisible();
  await expect(page.getByLabel("Perfil", { exact: true })).toHaveValue(outro);
});
test("023 US1: criar, corrigir, juntar e reverter; o membro só vê", async ({ page, request }) => {
  test.setTimeout(150_000);
  const s = await semear(request);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrir(page, s.perfilId, "?aba=temas");

  // ---- criar um tema à mão ----
  await page.getByRole("button", { name: "Novo tema" }).click();
  const form = page.getByRole("form", { name: "Criar tema" });
  await form.getByLabel("Nome do tema").fill("Bastidores");
  await form.getByLabel("Palavras-chave").fill("bastidores, making of");
  await form.getByRole("button", { name: "Criar tema" }).click();
  await expect(page.getByRole("listitem", { name: "Tema Bastidores" })).toBeVisible();
  // nome repetido (sem acento e sem caixa) é recusado
  await form.getByLabel("Nome do tema").fill("marvel");
  await form.getByRole("button", { name: "Criar tema" }).click();
  await expect(form.getByRole("alert")).toBeVisible();

  // ---- corrigir a classificação de um post: passa a "corrigida pelo dono" ----
  const classificacoes = page.getByRole("list", { name: "Classificações" });
  const post = classificacoes.getByRole("listitem").filter({ hasText: "Batman" }).first();
  await expect(post).toContainText("classificada pela IA");
  await post.getByRole("button", { name: /^Corrigir/ }).click();
  await post.getByLabel("Tema principal").selectOption({ label: "Marvel" });
  await post.getByLabel("Estilo do gancho").selectOption({ label: "Revelação" });
  await post.getByRole("button", { name: "Salvar correção" }).click();
  const corrigido = classificacoes.getByRole("listitem").filter({ hasText: "corrigida pelo dono" }).first();
  await expect(corrigido).toContainText("Marvel");
  await expect(corrigido).toContainText("Revelação");

  // ---- juntar DC em Marvel: os posts de DC vão para Marvel; reverter devolve ----
  const dc = page.getByRole("listitem", { name: "Tema DC" });
  await dc.getByRole("button", { name: "Juntar o tema DC a outro" }).click();
  const juntar = page.getByRole("alertdialog");
  await juntar.getByLabel("Juntar em").selectOption({ label: "Marvel" });
  await juntar.getByRole("button", { name: "Juntar" }).click();
  await expect(page.getByRole("listitem", { name: "Tema DC" })).toHaveCount(0);
  await page.getByLabel("Tema", { exact: true }).selectOption({ label: "Marvel" });
  await expect(classificacoes.getByRole("listitem").filter({ hasText: "Batman" })).toHaveCount(4);

  await page.getByText("Mostrar arquivados").click();
  const dcArquivado = page.getByRole("listitem", { name: "Tema DC" });
  await expect(dcArquivado).toContainText("juntado em Marvel");
  await dcArquivado.getByRole("button", { name: "Histórico do tema DC" }).click();
  const historico = page.getByRole("dialog", { name: /Histórico do tema "DC"/ });
  await historico.getByRole("button", { name: "Reverter para esta versão" }).first().click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reverter" }).click();
  await expect(page.getByText("Revertido para a versão")).toBeVisible();
  await historico.getByRole("button", { name: "Close" }).click();
  await expect(historico).toHaveCount(0);
  await page.getByText("Mostrar arquivados").click();
  await expect(page.getByRole("listitem", { name: "Tema DC" })).toBeVisible();
  await page.getByLabel("Tema", { exact: true }).selectOption({ label: "DC" });
  // os 3 que eram de DC voltam; o corrigido pelo dono continua em Marvel
  await expect(classificacoes.getByRole("listitem").filter({ hasText: "Batman" })).toHaveCount(3);
  await logout(page);

  // ---- o membro vê tudo, sem botões de escrita ----
  const membro = await createVerifiedMember(page);
  await login(page, membro.email, membro.final);
  await expect(page).toHaveURL(/\/app$/);
  await abrir(page, s.perfilId, "?aba=temas");
  await expect(page.getByRole("listitem", { name: "Tema Marvel" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Novo tema" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Propor com IA" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Corrigir/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Classificar pendentes" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Análises da IA" }).click();
  await expect(page.getByRole("button", { name: "Estimar custo" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Recomendações" }).click();
  await expect(page.getByRole("switch", { name: "Classificação automática" })).toBeDisabled();
});

test("023 US5: sinais do post estagnado e a conferência do dono no detalhe do vídeo", async ({ page, request }) => {
  const s = await semear(request);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const estagnado = s.estagnados[s.estagnados.length - 1]!;
  await page.goto(`/app/metricas/videos/${estagnado}`);
  const diag = page.getByRole("region", { name: "Diagnóstico de distribuição" });
  await expect(diag).toBeVisible();
  await expect(diag).toContainText("estagnado");
  const item = diag.locator("li[data-resultado]").first();
  await item.getByLabel("Resultado").selectOption({ label: "Conferi: está ok" });
  await item.getByLabel("Nota (opcional)").fill("não estava restrito");
  await item.getByRole("button", { name: "Registrar" }).click();
  await expect(item).toHaveAttribute("data-resultado", "ok");
  await page.reload();
  await expect(diag.locator('li[data-resultado="ok"]')).toHaveCount(1);
  await expect(diag.locator('li[data-resultado="ok"]').getByLabel("Nota (opcional)")).toHaveValue("não estava restrito");
});

test("023: 390 px sem rolagem horizontal nas 5 abas", async ({ page, request }) => {
  const s = await semear(request);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  for (const aba of ["", "?aba=temas", "?aba=recomendacoes", "?aba=diagnostico", "?aba=ia"]) {
    await abrir(page, s.perfilId, aba);
    await expect(painel(page).locator(".animate-pulse")).toHaveCount(0);
    const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(scroll, `rolagem horizontal em ${aba || "analise"}`).toBeLessThanOrEqual(client);
  }
});

// ---- com o Claude falso do e2e e a trilha `aprendizado` (AGENDADOR_APRENDIZADO_S=2) ----

test("023 US1 com IA: propor, salvar, classificar pendentes pela trilha e corrigir", async ({ page, request }) => {
  const sfx = Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Propor ${sfx}`, slug: `propor-${sfx}` });
  const { conta } = await api<{ conta: { id: string } }>(request, token, "post", `/api/perfis/${perfilId}/contas`, { platform: "tiktok", handle: `propor${sfx}`, status: "ativa" });
  // 6 posts com mais de 24 h, sem classificação: 4 de Marvel e 2 de Games (as hashtags dão os temas)
  const posts: PostSemeado[] = [
    ...Array.from({ length: 4 }, (_, i) => ({ legenda: `Trailer novo ${sfx} ${i} #marvel #cinema`, tema: "", idadeH: 40 + i * 10, fotos: curva(10 + i) })),
    ...Array.from({ length: 2 }, (_, i) => ({ legenda: `Gameplay ${sfx} ${i} #games`, tema: "", idadeH: 90 + i * 10, fotos: curva(5) })),
  ].map((p) => ({ ...p, tema: "00000000-0000-4000-8000-000000000000" }));
  expect(semearConta(perfilId, conta.id, posts, false)).toHaveLength(6);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrir(page, perfilId, "?aba=temas");
  await expect(page.getByText("Nenhum tema ainda.")).toBeVisible();
  // sem temas, os posts aparecem aguardando classificação
  await expect(page.getByRole("list", { name: "Classificações" }).getByRole("listitem").filter({ hasText: "aguardando classificação" })).toHaveCount(6);

  // ---- a proposta da IA não salva nada até "Salvar temas" ----
  await page.getByRole("button", { name: "Propor com IA" }).click();
  const proposta = page.getByRole("list", { name: "Temas propostos" });
  await expect(proposta.getByRole("listitem")).toHaveCount(3);
  await expect(page.getByLabel("Nome do tema proposto 1")).toHaveValue("Marvel");
  await expect(page.getByRole("list", { name: "Temas", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Tirar Cinema da proposta" }).click();
  await page.getByRole("button", { name: "Salvar temas" }).click();
  await expect(page.getByRole("listitem", { name: "Tema Marvel" })).toBeVisible();
  await expect(page.getByRole("listitem", { name: "Tema Games" })).toBeVisible();
  await expect(page.getByRole("listitem", { name: "Tema Cinema" })).toHaveCount(0);

  // ---- classificar pendentes: a trilha atende em segundos no e2e ----
  await page.getByRole("button", { name: "Classificar pendentes" }).click();
  const classificacoes = page.getByRole("list", { name: "Classificações" });
  await expect(async () => {
    await page.reload();
    await expect(classificacoes.getByRole("listitem").filter({ hasText: "classificada pela IA" })).toHaveCount(6, { timeout: 1_000 });
  }).toPass({ timeout: 60_000 });
  await expect(classificacoes.getByRole("listitem").filter({ hasText: "Trailer novo" }).first()).toContainText("Marvel");
  await expect(page.getByText(/usadas hoje 6 \/ 50/)).toBeVisible();

  // ---- a correção do dono prevalece ----
  const post = classificacoes.getByRole("listitem").filter({ hasText: "Gameplay" }).first();
  await post.getByRole("button", { name: /^Corrigir/ }).click();
  await post.getByLabel("Tema principal").selectOption({ label: "Marvel" });
  await post.getByRole("button", { name: "Salvar correção" }).click();
  await expect(classificacoes.getByRole("listitem").filter({ hasText: "corrigida pelo dono" })).toHaveCount(1);
  await page.getByRole("button", { name: "Classificar pendentes" }).click();
  await page.waitForTimeout(4_000);
  await page.reload();
  const corrigido = classificacoes.getByRole("listitem").filter({ hasText: "corrigida pelo dono" });
  await expect(corrigido).toHaveCount(1);
  await expect(corrigido).toContainText("Marvel");
});

test("023 US2/US3 com IA: análise sem quadros, hipótese vira recomendação, aceitar, rejeitar e reverter", async ({ page, request }) => {
  const s = await semear(request);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrir(page, s.perfilId, `?aba=ia&conta=${s.contaId}`);

  // ---- estimativa (nenhuma chamada) e "Confirmar custo" ----
  await page.getByRole("button", { name: "Estimar custo" }).click();
  await expect(page.locator("[data-estimativa]")).toContainText("Custo estimado");
  await page.getByRole("button", { name: /^Confirmar custo/ }).click();
  const analise = page.getByRole("list", { name: "Análises da IA" }).getByRole("listitem").first();
  await expect(analise).toHaveAttribute("data-estado", "pronta", { timeout: 60_000 });
  const hipoteses = analise.getByRole("list", { name: "Hipóteses" });
  await expect(hipoteses.locator("[data-hipotese]")).toHaveCount(2);
  await expect(hipoteses).toContainText("Gancho com pergunta prende mais");
  await expect(hipoteses.locator("[data-hipotese]").first()).toContainText("a conferir");
  await expect(hipoteses.locator("[data-hipotese]").first().getByRole("link").first()).toBeVisible();

  // ---- as 2 hipóteses viram recomendações de padrão ----
  for (const [i, tipo] of [[0, "Padrão de gancho"], [1, "Padrão de duração"]] as const) {
    const h = hipoteses.locator(`[data-hipotese="${i}"]`);
    await h.getByRole("button", { name: "Transformar em recomendação" }).click();
    await h.getByLabel("Tipo de padrão").selectOption({ label: tipo });
    await h.getByRole("button", { name: "Criar recomendação" }).click();
    await expect(h.getByRole("button", { name: "Transformar em recomendação" })).toBeVisible();
  }

  await page.getByRole("tab", { name: "Recomendações" }).click();
  const abertas = page.getByRole("list", { name: "Recomendações abertas" });
  await expect(abertas.getByRole("listitem")).toHaveCount(2);

  // ---- aceitar o gancho: vira preferência (v1 do nível da recomendação) ----
  await abertas.getByRole("button", { name: /^Aceitar: Padrão de gancho/ }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Aceitar" }).click();
  await expect(abertas.getByRole("listitem")).toHaveCount(1);
  const prefs = page.locator('[aria-label^="Itens das preferências"]');
  await expect(prefs).toContainText("Gancho: Gancho com pergunta prende mais");

  // ---- rejeitar a duração com motivo: some das abertas e fica nas decididas ----
  await abertas.getByRole("button", { name: /^Rejeitar: Padrão de duração/ }).click();
  await page.getByRole("alertdialog").getByLabel("Motivo (opcional)").fill("Os cortes já são curtos");
  await page.getByRole("alertdialog").getByRole("button", { name: "Rejeitar" }).click();
  await expect(page.getByText("Nenhuma recomendação agora.")).toBeVisible();
  const decididas = page.getByRole("list", { name: "Recomendações decididas" });
  await expect(decididas.getByRole("listitem")).toHaveCount(2);
  await expect(decididas).toContainText("Motivo: Os cortes já são curtos");

  // ---- reverter o aceite: a preferência sai ----
  const aceita = decididas.getByRole("listitem").filter({ hasText: "Aceita" });
  await aceita.getByRole("button", { name: "Reverter" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reverter" }).click();
  await expect(aceita).toContainText("revertida em");
  await expect(prefs).toHaveCount(0);
});

test("023 US3: aceitar \"fixar hashtag\" grava no guia; a decisão revertida avisa e o guia fica", async ({ page, request }) => {
  const sfx = Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const perfilId = await createPerfilViaApi(request, token, { name: `Fixar ${sfx}`, slug: `fixar-${sfx}` });
  const { conta } = await api<{ conta: { id: string } }>(request, token, "post", `/api/perfis/${perfilId}/contas`, { platform: "tiktok", handle: `fixar${sfx}`, status: "ativa" });
  const tema = async (nome: string) => (await api<{ id: string }>(request, token, "post", `/api/perfis/${perfilId}/aprendizado/temas`, { nome, palavrasChave: [nome.toLowerCase()] })).id;
  const marvel = await tema("Marvel");
  const dc = await tema("DC");
  // 18 posts entregues: em Marvel, 6 com #matchcut rendem bem mais que os 6 sem (separável dentro do tema)
  const posts: PostSemeado[] = [
    ...Array.from({ length: 6 }, (_, i) => ({ legenda: `Cena ${sfx} ${i} #matchcut`, tema: marvel, mult: 40 + i })),
    ...Array.from({ length: 6 }, (_, i) => ({ legenda: `Teoria ${sfx} ${i}`, tema: marvel, mult: 6 + (i % 2) })),
    ...Array.from({ length: 6 }, (_, i) => ({ legenda: `Batman ${sfx} ${i}`, tema: dc, mult: 8 + (i % 3) })),
  ].map((p, g) => ({ legenda: p.legenda, tema: p.tema, idadeH: 40 + g * 7, fotos: curva(p.mult) }));
  expect(semearConta(perfilId, conta.id, posts)).toHaveLength(18);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await abrir(page, perfilId, "?aba=recomendacoes");
  const abertas = page.getByRole("list", { name: "Recomendações abertas" });
  const fixar = abertas.getByRole("listitem").filter({ hasText: /Fixar hashtag: #?matchcut/ });
  await expect(fixar).toHaveCount(1);
  await expect(fixar).toContainText("Se aceitar:");
  await fixar.getByRole("button", { name: /^Aceitar:/ }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Aceitar" }).click();
  await expect(page.getByText(/Hashtag fixada no guia/)).toBeVisible();
  await expect(fixar).toHaveCount(0);

  // a hashtag está nas fixas do guia (com o histórico do guia)
  const decididas = page.getByRole("list", { name: "Recomendações decididas" });
  const aceita = decididas.getByRole("listitem").filter({ hasText: "matchcut" });
  await aceita.getByRole("link", { name: "Ver no guia de comunicação" }).click();
  await expect(page.getByLabel(/Hashtags fixas/).first()).toHaveValue(/#matchcut/);

  // reverter a decisão avisa que a hashtag continua no guia
  await page.goBack();
  await aceita.getByRole("button", { name: "Reverter" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reverter" }).click();
  await expect(aceita).toContainText("revertida em");
});
