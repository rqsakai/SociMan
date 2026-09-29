import { randomUUID } from "node:crypto";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, login, logout } from "./helpers";

// T079 (spec 006): o fluxo inteiro na stack isolada, com o `openshorts-fake` (OpenShorts e
// YouTube de mentira), o `agendador` (intervalos curtos) e o `worker` reais.
// US1 cadastrar canal, dono muda o direito, membro vê só leitura; US2 Descobrir com o motivo e
// dois vídeos selecionados; US3 envio com o aviso de "Sem acordo" confirmado pelo MEMBRO, status
// até "Pronto" e notificação no sino; US4 revisão: arquivar um clipe e aplicar a marca nos outros;
// US5 textos à mão, agendar para daqui a 1 min, "Hora de postar" no sino e "Marcar como postado".
// Nenhuma requisição sai para rede social.

const SHOTS = ".playwright-mcp/sociman";
const SOCIAL = /tiktok|open\.tiktokapis|upload-post|graph\.facebook|instagram\.com|youtube\.com\/upload|googleapis\.com|\/api\/social|videos\.insert/i;

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
    if (SOCIAL.test(req.url())) social.push(`${req.method()} ${req.url()}`);
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
  await expect(page.getByRole("table", { name: "Canais-fonte" }).getByText("Sem acordo", { exact: true })).toBeVisible();
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
  await barra.getByRole("button", { name: "Enviar para corte" }).click();
  const enviar = page.getByRole("dialog", { name: "Enviar para corte" });
  await expect(enviar.getByLabel("Duração mínima (s)")).toHaveValue("15");
  await expect(enviar.getByLabel("Duração máxima (s)")).toHaveValue("60");
  await enviar.getByRole("button", { name: "Enviar 2 vídeos" }).click();
  const aviso = page.getByRole("alertdialog");
  await expect(aviso).toContainText("O direito autoral deste vídeo é de sua responsabilidade");
  await expect(aviso).toContainText("Entrevista com dev");
  await page.screenshot({ path: `${SHOTS}/006-aviso-direito.png`, fullPage: true });
  await aviso.getByRole("button", { name: "Confirmo e quero enviar" }).click();
  await expect(page.getByText("2 vídeos enviados para corte.")).toBeVisible();

  // status ao vivo até "Pronto" (3 clipes importados cada)
  await nav(page, "Envios").click();
  await page.getByRole("tab", { name: "Envios" }).click();
  const envios = page.getByRole("table", { name: "Envios" });
  await expect(envios.getByText("Pronto: 3 clipes")).toHaveCount(2, { timeout: 180_000 });
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
  await expect(page.getByRole("list").filter({ has: page.getByRole("listitem", { name: /Versão/ }) })).toContainText(member.name);

  // ---- US4: revisão do outro envio: arquivar um clipe e aplicar a marca nos outros ----
  await nav(page, "Envios").click();
  await page.getByRole("tab", { name: "Envios" }).click();
  await page.getByRole("table", { name: "Envios" }).getByRole("link", { name: /Review do notebook gamer/ }).click();
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

  // ---- US5: textos à mão e agendar para daqui a ~1 min ----
  await clipes.first().getByRole("link", { name: "Abrir" }).click();
  await expect(page).toHaveURL(/\/app\/cortes\/[0-9a-f-]{36}$/);
  const postagem = page.getByRole("group", { name: /^Postagem em TikTok/ });
  await postagem.getByLabel("Título").fill("Notebook gamer: vale a pena?");
  await postagem.getByLabel("Descrição").fill("O review completo no canal. Corte feito no e2e.");
  const tags = postagem.getByLabel("Hashtags", { exact: true });
  for (const t of ["#notebook", "#gamer", "#tecnologia"]) {
    await tags.fill(t);
    await tags.press("Enter");
  }
  await expect(postagem.getByRole("list", { name: "Hashtags escolhidas" }).getByRole("listitem")).toHaveCount(3);
  const quando = new Date(Date.now() + 70_000);
  await postagem.getByLabel("Data e hora (horário de Brasília)").fill(spLocalInput(quando));
  await postagem.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText(/^Agendado para /)).toBeVisible();
  await expect(postagem.getByText("Agendado", { exact: true })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/006-postagem.png`, fullPage: true });

  // calendário: a postagem aparece na semana
  await nav(page, "Calendário").click();
  await expect(page.getByRole("button", { name: /Notebook gamer: vale a pena\?/ })).toBeVisible();
  await expect(page.getByRole("list", { name: "Cores dos perfis" })).toContainText(perfilName);
  await page.screenshot({ path: `${SHOTS}/006-calendario.png` });

  // na hora, "Hora de postar" no sino
  await expect
    .poll(
      async () => {
        await page.reload();
        await sino(page).click();
        const found = await page.getByRole("menuitem", { name: /Hora de postar/ }).count();
        await page.keyboard.press("Escape");
        return found;
      },
      { timeout: 150_000, intervals: [10_000] },
    )
    .toBeGreaterThan(0);
  await sino(page).click();
  await page.getByRole("menuitem", { name: /Hora de postar/ }).first().click();
  await expect(page).toHaveURL(/\/app\/cortes\//);

  // "Marcar como postado" (manual; nada é publicado)
  const post = page.getByRole("group", { name: /^Postagem em TikTok/ });
  await post.getByRole("button", { name: "Marcar como postado" }).click();
  await page.getByRole("dialog", { name: "Marcar como postado" }).getByRole("button", { name: "Confirmar postado" }).click();
  await expect(page.getByText("Marcado como postado.")).toBeVisible();
  await expect(post.getByText("Postado", { exact: true })).toBeVisible();

  expect(social, "nenhuma requisição para rede social").toEqual([]);
});
