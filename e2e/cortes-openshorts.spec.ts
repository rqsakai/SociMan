import { randomUUID } from "node:crypto";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, login, logout, sqlE2e } from "./helpers";

// T079 (spec 006): o fluxo inteiro na stack isolada, com o `openshorts-fake` (OpenShorts e
// YouTube de mentira), o `agendador` (intervalos curtos) e o `worker` reais.
// US1 cadastrar canal, dono muda o direito, membro vê só leitura; US2 Descobrir com o motivo e
// dois vídeos selecionados; US3 envio com o aviso de "Sem acordo" confirmado pelo MEMBRO, status
// até "Pronto" e notificação no sino; US4 revisão: arquivar um clipe e aplicar a marca nos outros;
// US5 agendar pelo AgendarDialog da 014 (textos à mão, daqui a 1 min), "Hora de postar" no sino
// e "Postado" na aba da conta em Conteúdos.
// Nenhuma requisição sai para rede social.

const SHOTS = ".playwright-mcp/sociman";
// Guarda do princípio I pelo DOMÍNIO (e por /api/social): o caminho de módulos locais do Vite
// (ex.: /src/components/publicacao/TikTokPostForm.tsx em localhost) não é rede social.
const SOCIAL_HOST = /(^|\.)(tiktok\.com|tiktokapis\.com|tiktokcdn\.com|upload-post\.com|facebook\.com|instagram\.com|youtube\.com|googleapis\.com)$/i;
const ehRedeSocial = (url: string): boolean => {
  const u = new URL(url);
  return SOCIAL_HOST.test(u.hostname) || /\/api\/social/i.test(u.pathname) || /videos\.insert/i.test(u.pathname);
};

// Data e hora locais de São Paulo ("2026-09-30T19:07") para o <input type="datetime-local">.
function spLocalInput(date: Date): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Sao_Paulo",
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
      .formatToParts(date)
      .map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function nav(page: Page, name: string): Locator {
  return page.getByRole("navigation", { name: "Menu principal" }).getByRole("link", { name, exact: true });
}

function sino(page: Page): Locator {
  return page.getByRole("button", { name: /^Notificações/ });
}

test("cortes com o OpenShorts: canal → descobrir → enviar → revisar → agendar", async ({ page, request }) => {
  test.setTimeout(480_000);

  const social: string[] = [];
  page.on("request", (req) => {
    if (ehRedeSocial(req.url())) social.push(`${req.method()} ${req.url()}`);
  });

  // ---- dados de base pela API: perfil, conta TikTok ativa e o membro ----
  const sfx = randomUUID().slice(0, 8);
  const perfilName = `Cortes E2E ${sfx}`;
  const ownerToken = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${ownerToken}` };
  const perfilId = await createPerfilViaApi(request, ownerToken, { name: perfilName, slug: `cortes-e2e-${sfx}` });
  const conta = await request.post(`/api/perfis/${perfilId}/contas`, {
    headers: auth,
    data: { platform: "tiktok", handle: `cortese2e${sfx}`, status: "ativa" },
  });
  expect(conta.status(), "POST contas").toBe(201);
  const member = await createVerifiedMember(page);

  // ---- US1: o dono cadastra o canal pelo link e muda o direito ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await nav(page, "Canais-fonte").click();
  await expect(page.getByRole("heading", { name: "Canais-fonte", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Adicionar canal" }).click();
  const addDialog = page.getByRole("dialog", { name: "Adicionar canal" });
  await addDialog.getByLabel("Link, @ ou ID do canal").fill("https://www.youtube.com/@canaldementira");
  await addDialog.getByRole("button", { name: "Buscar canal" }).click();
  const previa = addDialog.getByRole("region", { name: "Prévia do canal" });
  await expect(previa.getByText("Canal de Mentira")).toBeVisible();
  await expect(previa.getByText("Sem acordo", { exact: true })).toBeVisible();
  await previa.getByLabel(perfilName).check();
  await addDialog.getByRole("button", { name: "Salvar canal" }).click();
  await expect(page).toHaveURL(/\/app\/fontes\/[0-9a-f-]{36}$/);
  const canalAId = page.url().split("/").pop()!;
  await expect(page.getByRole("heading", { name: "Canal de Mentira", level: 1 })).toBeVisible();

  // a busca dos vídeos começa sozinha (agendador) e termina "Atualizado"
  await expect(page.getByText("Atualizado", { exact: true })).toBeVisible({ timeout: 60_000 });

  // o dono muda o direito para "Próprio" (vai para o histórico com autor)
  await page.getByLabel("Status de direito").selectOption({ label: "Próprio" });
  await page.getByLabel("Evidência (nota)").fill("Canal da própria agência (e2e)");
  await page.getByRole("button", { name: "Salvar direito" }).click();
  await expect(page.getByText("Direito atualizado.")).toBeVisible();
  await expect(page.getByRole("listitem", { name: "Versão 2" })).toContainText(OWNER.name);
  await page.screenshot({ path: `${SHOTS}/006-canal-detalhe.png`, fullPage: true });

  // o segundo canal entra pela API e fica "Sem acordo" (o membro vai confirmar o aviso)
  const canalB = await request.post("/api/canais", {
    headers: auth,
    data: { youtubeChannelId: "UCe2eOutroCanalFake0000B", perfilIds: [perfilId] },
  });
  expect(canalB.status(), "POST /api/canais (B)").toBe(201);

  await nav(page, "Canais-fonte").click();
  await expect(page.getByRole("table", { name: "Canais-fonte" }).getByText("Outro Canal Fake")).toBeVisible();
  // escopo na linha do canal B: outros specs (ex.: Mercado da 019) também criam canais "Sem acordo"
  await expect(
    page.getByRole("table", { name: "Canais-fonte" }).getByRole("row").filter({ hasText: "Outro Canal Fake" })
      .getByText("Sem acordo", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/006-canais.png`, fullPage: true });
  await logout(page);

  // ---- US1: o membro vê o direito só leitura (e a API responde 403) ----
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/fontes/${canalAId}`);
  await expect(page.getByText("Só o dono muda o status de direito.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Salvar direito" })).toHaveCount(0);
  const memberToken = await apiToken(request, member.email, member.final);
  const forbidden = await request.put(`/api/canais/${canalAId}/direito`, {
    headers: { Authorization: `Bearer ${memberToken}` },
    data: { version: 99, direito: "sem_acordo" },
  });
  expect(forbidden.status(), "membro muda o direito").toBe(403);

  // ---- US2: Descobrir, com o motivo; o membro seleciona dois vídeos ----
  await nav(page, "Descobrir").click();
  await page.getByLabel("Cortar para o perfil").selectOption({ label: perfilName });
  await page.getByLabel("Mostrar não recomendados").check();
  const tabela = page.getByRole("table", { name: "Vídeos recomendados" });
  await expect(tabela.getByText("Review do notebook gamer")).toBeVisible({ timeout: 60_000 });
  await expect(tabela.getByText("Entrevista com dev")).toBeVisible({ timeout: 60_000 });
  await expect(tabela.getByRole("button", { name: "Por quê? (Review do notebook gamer)" })).toBeVisible();
  await tabela.getByRole("button", { name: "Por quê? (Review do notebook gamer)" }).click();
  await expect(page.getByRole("dialog", { name: /Por que \d+ pontos\?/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: /Por que \d+ pontos\?/ })).toBeHidden();
  await page.screenshot({ path: `${SHOTS}/006-descobrir.png`, fullPage: true });

  await tabela.getByRole("button", { name: "Selecionar para corte: Review do notebook gamer" }).click();
  await expect(tabela.getByRole("button", { name: "Desfazer seleção: Review do notebook gamer" })).toBeVisible();
  await tabela.getByRole("button", { name: "Selecionar para corte: Entrevista com dev" }).click();
  await expect(tabela.getByRole("button", { name: "Desfazer seleção: Entrevista com dev" })).toBeVisible();
  const barra = page.getByRole("region", { name: "Selecionados" });
  await expect(barra).toContainText("2 vídeos selecionados");

  // ---- US3: enviar; o aviso de direito aparece (canal "Sem acordo") e o membro confirma ----
  await barra.getByRole("button", { name: "Gerar cortes" }).click();
  const enviar = page.getByRole("dialog", { name: "Gerar cortes" });
  await expect(enviar.getByLabel("Duração mínima (s)")).toHaveValue("15");
  await expect(enviar.getByLabel("Duração máxima (s)")).toHaveValue("60");
  await enviar.getByRole("button", { name: "Gerar cortes de 2 vídeos" }).click();
  const aviso = page.getByRole("alertdialog");
  await expect(aviso).toContainText("O direito autoral deste vídeo é de sua responsabilidade");
  await expect(aviso).toContainText("Entrevista com dev");
  await page.screenshot({ path: `${SHOTS}/006-aviso-direito.png`, fullPage: true });
  await aviso.getByRole("button", { name: "Confirmo e quero gerar" }).click();
  await expect(page.getByText("Geração de cortes iniciada: 2 vídeos.")).toBeVisible();

  // status ao vivo até "Pronto" (3 clipes importados cada)
  await nav(page, "Gerar cortes").click();
  await page.getByRole("tab", { name: "Gerações" }).click();
  const envios = page.getByRole("table", { name: "Gerações" });
  // FR-010a: "Processando N% · <etapa real>" (o fake revela logs de um job real em ~12 s), com
  // ícone e a barra do % geral, enquanto o envio anda
  const etapa = envios.locator("[data-etapa]").first();
  await expect(etapa).toHaveText(
    /^Processando \d+% · (Baixando o vídeo|Vídeo baixado|Transcrevendo o vídeo|Escolhendo os momentos|Cortando clipe \d de 3|Aplicando legendas do kit \d de 3|Importando)/,
    { timeout: 30_000 },
  );
  await expect(envios.getByRole("progressbar", { name: "Progresso da geração" }).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/006-envios-etapa.png`, fullPage: true });
  await expect(envios.getByText("Pronto: 3 clipes")).toHaveCount(2, { timeout: 180_000 });
  await expect(envios.locator("[data-etapa]")).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/006-envios.png`, fullPage: true });

  // a notificação chega no sino (polling de 20 s)
  await expect(sino(page)).toHaveAccessibleName(/não lidas/, { timeout: 45_000 });
  await sino(page).click();
  await expect(page.getByRole("menuitem", { name: /Review do notebook gamer/ }).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/006-sino.png`, fullPage: true });
  await page.keyboard.press("Escape");

  // a versão do envio registra o membro como autor e o direito "Sem acordo"
  await envios.getByRole("link", { name: /Entrevista com dev/ }).click();
  await expect(page.getByRole("heading", { name: "Entrevista com dev", level: 1 })).toBeVisible();
  // o detalhe lista as etapas; no fim, todas concluídas (legenda do kit incluída)
  const etapas = page.getByRole("list", { name: "Etapas da geração" });
  await expect(etapas.getByRole("listitem")).toHaveCount(8);
  await expect(etapas).toContainText("Aplicando legendas do kit");
  await expect(etapas.getByText("(concluída)")).toHaveCount(8);
  await expect(page.getByRole("list").filter({ has: page.getByRole("listitem", { name: /Versão/ }) })).toContainText(member.name);

  // ---- US4: revisão do outro envio: arquivar um clipe e aplicar a marca nos outros ----
  await nav(page, "Gerar cortes").click();
  await page.getByRole("tab", { name: "Gerações" }).click();
  await page.getByRole("table", { name: "Gerações" }).getByRole("link", { name: /Review do notebook gamer/ }).click();
  await expect(page.getByRole("heading", { name: "Review do notebook gamer", level: 1 })).toBeVisible();
  const clipes = page.getByRole("article", { name: /^Clipe:/ });
  await expect(clipes).toHaveCount(3);
  await expect(clipes.first().getByText("Em revisão")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/006-revisao.png`, fullPage: true });
  await clipes.nth(0).getByRole("button", { name: "Arquivar" }).click();
  await expect(page.getByText("Clipe arquivado.")).toBeVisible();
  await expect(clipes).toHaveCount(2);
  await page.getByRole("button", { name: "Aplicar marca em todos" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Aplicar marca em todos" }).click();
  await expect(page.getByText("Marca na fila para 2 clipes.")).toBeVisible();
  await expect(clipes.getByText("Pronto", { exact: true })).toHaveCount(2, { timeout: 180_000 });
  await page.screenshot({ path: `${SHOTS}/006-revisao-marca.png`, fullPage: true });

  // ---- US5: agendar direto no clipe pronto (spec 014: AgendarDialog), textos à mão, ~1 min ----
  await clipes.first().getByRole("link", { name: "Abrir" }).click();
  await expect(page).toHaveURL(/\/app\/cortes\/[0-9a-f-]{36}$/);
  // spec 014: só o dono aprova; ele aprova e agenda no mesmo passo (o membro veria "Pedir aprovação")
  const corteUrl = page.url();
  await logout(page);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(corteUrl);
  await page.getByRole("button", { name: "Agendar / Publicar", exact: true }).first().click();
  const agendar = page.getByRole("dialog", { name: "Agendar ou publicar" });
  const contaOpt = agendar.getByLabel("Conta").and(page.locator("select")).locator("option").filter({ hasText: `cortese2e${sfx}` }).first();
  await agendar.getByLabel("Conta").and(page.locator("select")).selectOption((await contaOpt.getAttribute("value"))!);
  // spec 015 (T103): na TikTok não há título, só a legenda (descrição + hashtags), obrigatória
  await expect(agendar.getByLabel("Título", { exact: true })).toHaveCount(0);
  await agendar.getByRole("textbox", { name: /^Legenda/ }).fill("Notebook gamer: vale a pena? O review completo no canal. Corte feito no e2e.");
  const tags = agendar.getByLabel("Hashtags", { exact: true });
  for (const t of ["#notebook", "#gamer", "#tecnologia"]) {
    await tags.fill(t);
    await tags.press("Enter");
  }
  await expect(agendar.getByRole("list", { name: "Hashtags escolhidas" }).getByRole("listitem")).toHaveCount(3);
  const quando = new Date(Date.now() + 70_000);
  await agendar.getByLabel("Data e hora (horário de Brasília)").fill(spLocalInput(quando));
  await expect(agendar.getByLabel("Modo", { exact: true })).toHaveValue("lembrete");
  await agendar.getByRole("button", { name: "Aprovar e agendar" }).click();
  await expect(agendar).toBeHidden();
  await expect(page.getByText("Agendado", { exact: true }).first()).toBeVisible();
  // o título que o calendário e o sino mostram é o do conteúdo (a TikTok não tem título)
  const corteId = corteUrl.split("/").pop()!;
  const conteudoRes = await request.get(`/api/conteudos/${corteId}`, { headers: { Authorization: `Bearer ${ownerToken}` } });
  const agendado = ((await conteudoRes.json()) as { conteudo: { destinos: { titulo: string; descricao: string; hashtags: string[] }[] } }).conteudo.destinos[0];
  expect(agendado.descricao).toContain("Notebook gamer: vale a pena?");
  expect(agendado.hashtags).toEqual(["#notebook", "#gamer", "#tecnologia"]);
  const tituloPost = agendado.titulo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  await page.screenshot({ path: `${SHOTS}/006-postagem.png`, fullPage: true });

  // calendário: a postagem aparece na semana
  await nav(page, "Calendário").click();
  await expect(page.getByRole("button", { name: new RegExp(tituloPost) }).first()).toBeVisible();
  await expect(page.getByRole("list", { name: "Cores dos perfis" })).toContainText(perfilName);
  await page.screenshot({ path: `${SHOTS}/006-calendario.png` });

  // na hora, "Hora de postar" no sino
  await expect
    .poll(
      async () => {
        await page.reload();
        await sino(page).click();
        const found = await page.getByRole("menuitem", { name: new RegExp(`Hora de postar: ${tituloPost}`) }).count();
        await page.keyboard.press("Escape");
        return found;
      },
      { timeout: 150_000, intervals: [10_000] },
    )
    .toBeGreaterThan(0);
  await sino(page).click();
  // outros testes da suíte também geram "Hora de postar" para o mesmo dono: clicar no DESTE post
  await page.getByRole("menuitem", { name: new RegExp(`Hora de postar: ${tituloPost}`) }).first().click();
  await expect(page).toHaveURL(/\/app\/conteudos\/[0-9a-f-]{36}\?conta=/);

  // "Postado" (manual; nada é publicado)
  const destino = page.getByRole("tabpanel");
  await expect(destino.getByText("A postar", { exact: true }).first()).toBeVisible();
  await destino.getByRole("button", { name: "Postado", exact: true }).click();
  await page.getByRole("dialog", { name: "Marcar como postado" }).getByRole("button", { name: "Confirmar postado" }).click();
  await expect(destino.getByText("Postado", { exact: true }).first()).toBeVisible();

  expect(social, "nenhuma requisição para rede social").toEqual([]);
});

// Spec 023 (T052): com o perfil escolhido, os vídeos-fonte de um tema "cortar" (preferência do dono)
// saem do Descobrir, com "N ocultos por tema cortado"; "Mostrar temas cortados" os traz de volta com o
// selo. O direito do canal não muda (o aviso continua no envio, coberto pelo pytest da 023).
test("023 Descobrir: tema cortado oculto por padrão, com contador e filtro", async ({ page, request }) => {
  test.setTimeout(180_000);
  const sfx = randomUUID().slice(0, 8);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Cortado ${sfx}`, slug: `cortado-${sfx}` });
  // o canal B (vídeos "Entrevista com dev" e "Dicas de carreira") ligado a este perfil; se outro
  // teste já o cadastrou, só a ligação
  const canal = await request.post("/api/canais", { headers: auth, data: { youtubeChannelId: "UCe2eOutroCanalFake0000B", perfilIds: [perfilId] } });
  if (canal.status() !== 201) {
    sqlE2e(
      `insert into canal_perfis (canal_id, perfil_id) select id, '${perfilId}' from canais_fonte where youtube_channel_id = 'UCe2eOutroCanalFake0000B'`,
    );
  }
  const tema = await request.post(`/api/perfis/${perfilId}/aprendizado/temas`, {
    headers: auth,
    data: { nome: "Carreira", descricao: "Vida profissional", palavrasChave: ["carreira"] },
  });
  expect(tema.status(), `POST temas: ${await tema.text()}`).toBe(201);
  const temaId = ((await tema.json()) as { id: string }).id;
  // criar o tema já cria a linha das preferências do perfil (a versão da taxonomia): usa a versão atual
  const atual = (await (await request.get(`/api/perfis/${perfilId}/aprendizado/preferencias`, { headers: auth })).json()) as { perfil: { version: number } };
  const prefs = await request.patch(`/api/perfis/${perfilId}/aprendizado/preferencias`, {
    headers: auth,
    data: { version: atual.perfil.version, temas: { [temaId]: "cortar" } },
  });
  expect(prefs.status(), `PATCH preferências: ${await prefs.text()}`).toBe(200);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const tabela = page.getByRole("table", { name: "Vídeos recomendados" });
  // a busca do canal e o casamento vídeo-fonte × tema (`aprendizado_fonte_temas`) são do agendador:
  // recarrega até os vídeos chegarem e o tema cortado sair da lista
  await expect(async () => {
    await page.goto(`/app/descobrir?perfil=${perfilId}&todos=1`);
    await expect(tabela.getByText("Entrevista com dev")).toBeVisible({ timeout: 3_000 });
    await expect(page.getByText(/1 ocultos por tema cortado/)).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 90_000 });
  await expect(tabela.getByText("Dicas de carreira")).toHaveCount(0);

  await page.getByLabel("Mostrar temas cortados").check();
  await expect(page).toHaveURL(/[?&]cortados=1\b/);
  const linha = tabela.getByRole("row").filter({ hasText: "Dicas de carreira" });
  await expect(linha).toBeVisible();
  await expect(linha.locator("[data-tema-cortado]")).toHaveText("tema cortado: Carreira");
  await expect(tabela.getByRole("row").filter({ hasText: "Entrevista com dev" }).locator("[data-tema-cortado]")).toHaveCount(0);
  await expect(page.getByText(/ocultos por tema cortado/)).toHaveCount(0);
});
