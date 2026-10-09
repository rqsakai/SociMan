import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, login, logout, nav, type Member } from "./helpers";

// Spec 013 (T023, T029, T035, T044, T048): importação da agência. A pasta lida é a SINTÉTICA de
// e2e/fixtures/agencia (montada só leitura em /agencia/shared e /agencia/clipes na stack e2e);
// nunca a pasta real do dono. Os canais dos fontes.md (@canalimportacao, @parceiroimportacao) só
// existem no YouTube falso e nenhum outro e2e os usa. Os testes são em série: cada um parte do
// que o anterior gravou (a stack é efêmera).

const SHOTS = ".playwright-mcp/sociman";
const PAGINA = "/app/configuracoes/importacao";

let member: Member;
let achadosId: string;

const previa = (page: Page) => page.locator("[data-previa]");
const tabela = (page: Page) => previa(page).getByRole("table", { name: "Itens da leitura" });
// Linha da tabela da prévia que contém o texto (nome do item ou trecho de origem).
const linha = (page: Page, texto: string | RegExp) => tabela(page).getByRole("row").filter({ hasText: texto });
const contagem = (page: Page, chave: string) => previa(page).locator(`[data-contagem="${chave}"] dd`);

async function auth(request: APIRequestContext) {
  return { Authorization: `Bearer ${await apiToken(request, OWNER.email, OWNER.password)}` };
}

async function lerPasta(page: Page) {
  await page.goto(PAGINA);
  await page.getByRole("button", { name: "Ler a pasta da agência" }).click();
  await expect(previa(page)).toBeVisible({ timeout: 30_000 });
}

// Todas as linhas da tabela na mesma página (50 por página é o padrão da prévia).
async function filtrarSituacao(page: Page, situacao: string) {
  await previa(page).getByLabel("Filtrar por situação").selectOption(situacao);
}

test.describe.serial("013 importação da agência", () => {
  test("US1: prévia com novo, diverge lado a lado e fora com motivo; membro só vê", async ({ page, request }) => {
    test.setTimeout(240_000);
    const headers = await auth(request);

    // ---- estado anterior: o perfil achados-teste já existe com outro nicho (vai divergir) e o
    // canal @parceiroimportacao já é "parceiro" (o markdown diz `pendente` → diverge de direito) ----
    achadosId = await createPerfilViaApi(request, headers.Authorization.slice(7), {
      name: "Achados Teste",
      slug: "achados-teste",
      niche: "Nicho editado no SociMan",
    });
    const canal = await request.post("/api/canais", { headers, data: { youtubeChannelId: "UCe2eImportacaoPar00000D", perfilIds: [achadosId] } });
    expect(canal.status(), `POST /api/canais: ${await canal.text()}`).toBe(201);
    const c = ((await canal.json()) as { canal: { id: string; version: number } }).canal;
    const direito = await request.put(`/api/canais/${c.id}/direito`, { headers, data: { version: c.version, direito: "parceiro", evidenciaNota: "acordo do e2e" } });
    expect(direito.status(), `PUT direito: ${await direito.text()}`).toBe(200);

    member = await createVerifiedMember(page);

    // ---- o dono lê a pasta ----
    await login(page, OWNER.email, OWNER.password);
    await expect(page).toHaveURL(/\/app$/);
    await nav(page, "Importar da agência");
    await expect(page.getByRole("heading", { name: "Importar da agência", level: 1 })).toBeVisible();
    await expect(page.locator('[data-raiz="shared"]')).toContainText("disponível");
    await expect(page.locator('[data-raiz="clipes"]')).toContainText("disponível");
    await page.getByRole("button", { name: "Ler a pasta da agência" }).click();
    await expect(previa(page)).toBeVisible({ timeout: 30_000 });
    await expect(previa(page)).toContainText("Nada foi gravado.");

    // contagens: há novos, divergentes e itens fora; nenhum arquivo "não reconhecido"
    expect(Number(await contagem(page, "novo").textContent())).toBeGreaterThan(0);
    expect(Number(await contagem(page, "diverge").textContent())).toBeGreaterThanOrEqual(2);
    expect(Number(await contagem(page, "fora").textContent())).toBeGreaterThan(0);
    await expect(contagem(page, "naoReconhecido")).toHaveText("0");

    // o perfil novo e o perfil que diverge, com os dois lados
    await expect(linha(page, "Taverna Teste").first()).toContainText("novo");
    const achados = linha(page, "Achados Teste").filter({ has: page.locator("[data-diverge]") }).first();
    await expect(achados.locator('[data-lado="sociman"]')).toContainText("Nicho editado no SociMan");
    await expect(achados.locator('[data-lado="markdown"]')).toContainText("Utilidades de cozinha baratas");
    await expect(achados.getByRole("combobox")).toHaveValue("sociman");

    // canal novo: direito proposto "Sem acordo" para `autorizado`; o existente diverge no direito
    const novo = linha(page, "Canal da Importação").first();
    await expect(novo).toContainText("novo");
    await expect(novo.getByLabel(/^Direito de/)).toHaveValue("sem_acordo");
    await expect(novo).toContainText("No markdown: autorizado");
    const par = linha(page, "Parceiro da Importação").filter({ has: page.locator("[data-diverge]") });
    await expect(par).toContainText("diverge");
    await expect(par.getByRole("combobox")).toHaveValue("sociman");
    await expect(par.locator('[data-lado="sociman"]')).toContainText("parceiro");

    // fora, com o motivo: molde, arquivo operacional, "não usar ainda" e fontes sem YouTube
    await filtrarSituacao(page, "fora");
    await expect(linha(page, "_modelo/perfil.md").first()).toContainText(/molde/i);
    await expect(linha(page, "candidatos/2026-10-02.md").first()).toContainText(/operacional/i);
    await expect(linha(page, "marca-nao-usar-ainda.png").first()).toContainText(/não usar ainda/i);
    const aMao = previa(page).locator("[data-fontes-a-mao]");
    await expect(aMao).toContainText("Mestre Sem Link");
    await expect(aMao).toContainText("Streamer da Twitch");
    await filtrarSituacao(page, "");
    await page.screenshot({ path: `${SHOTS}/013-previa.png`, fullPage: true });

    // 390 px: sem rolagem horizontal da página
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(previa(page)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.screenshot({ path: `${SHOTS}/013-previa-390.png`, fullPage: true });
    await page.setViewportSize({ width: 1280, height: 800 });

    // a leitura não gravou nada: o perfil novo não existe
    const perfis = await request.get("/api/perfis", { headers });
    expect(JSON.stringify(await perfis.json())).not.toContain("taverna-teste");
    await logout(page);

    // ---- o membro vê a página sem "Ler"; a rota da prévia responde 403 ----
    await login(page, member.email, member.final);
    await expect(page).toHaveURL(/\/app$/);
    await nav(page, "Importar da agência");
    await expect(page.getByRole("heading", { name: "Importar da agência", level: 1 })).toBeVisible();
    await expect(page.getByText("Só o dono lê a pasta e confirma a importação.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Ler a pasta da agência" })).toHaveCount(0);
    const memberToken = await apiToken(request, member.email, member.final);
    const negado = await request.post("/api/agencia/previa", { headers: { Authorization: `Bearer ${memberToken}` } });
    expect(negado.status(), "membro lê a pasta").toBe(403);
    await logout(page);
  });

  test("US2/US3/US6: confirmar com escolhas, andamento até concluída e reler sem novos", async ({ page, request }) => {
    test.setTimeout(240_000);
    const headers = await auth(request);
    await login(page, OWNER.email, OWNER.password);
    await expect(page).toHaveURL(/\/app$/);
    await lerPasta(page);

    // escolhas: o perfil que diverge usa o markdown; o canal novo vira "Parceiro"; o direito do
    // canal existente fica como está (padrão); o achados-teste fica sem o TikTok (desmarcado)
    await linha(page, "Achados Teste").filter({ has: page.locator("[data-diverge]") }).first().getByRole("combobox").selectOption("markdown");
    await linha(page, "Canal da Importação").first().getByLabel(/^Direito de/).selectOption("parceiro");
    const tiktok = linha(page, "@achadosteste").first();
    await tiktok.getByRole("checkbox", { name: /^Importar/ }).click();
    await expect(tiktok.getByRole("checkbox", { name: /^Importar/ })).not.toBeChecked();
    // a persona da fábrica não tem perfil padrão (nenhum perfil tem a imagem dela): sem a escolha,
    // "Confirmar" fica desligado
    await expect(previa(page).getByRole("button", { name: "Confirmar importação" })).toBeDisabled();
    await previa(page).getByLabel("Em qual perfil a persona entra?").selectOption("achados-teste");

    await previa(page).getByRole("button", { name: "Confirmar importação" }).click();
    const dialogo = page.getByRole("alertdialog", { name: "Confirmar a importação?" });
    await expect(dialogo).toContainText("trocados 1 pelo markdown");
    await dialogo.getByRole("button", { name: "Confirmar importação" }).click();

    // andamento até "concluída" (a gravação é de fundo, com os 2 clipes)
    await expect(page.locator('[data-andamento="concluida"]')).toBeVisible({ timeout: 90_000 });
    await expect(page.locator('[data-andamento="concluida"] [data-contagem="criado"] dd')).not.toHaveText("0");
    await page.screenshot({ path: `${SHOTS}/013-concluida.png`, fullPage: true });

    // o canal novo entrou como "Parceiro"; o existente continua "Parceiro" (manter o SociMan)
    const canais = (await (await request.get("/api/canais", { headers })).json()) as { items: { youtubeChannelId: string; direito: string }[] };
    expect(canais.items.find((c) => c.youtubeChannelId === "UCe2eImportacaoNovo0000C")?.direito).toBe("parceiro");
    expect(canais.items.find((c) => c.youtubeChannelId === "UCe2eImportacaoPar00000D")?.direito).toBe("parceiro");

    // o perfil trocado tem o nicho do markdown e a versão nova com o dono como autor
    const achados = (await (await request.get(`/api/perfis/${achadosId}`, { headers })).json()) as { perfil: { niche: string } };
    expect(achados.perfil.niche).toBe("Utilidades de cozinha baratas");

    // ---- US6: os 2 clipes viraram conteúdos do taverna-teste, sem destino ----
    await nav(page, "Conteúdos");
    await expect(page.getByText("A jogada que virou a partida")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Regra de iniciativa em 30 segundos")).toBeVisible();

    // ---- ler de novo: nada novo, exceto o item desmarcado ----
    await lerPasta(page);
    await expect(contagem(page, "novo")).toHaveText("1");
    await expect(linha(page, "@achadosteste").first()).toContainText("novo");
    await expect(linha(page, "Taverna Teste").first()).toContainText("igual");
    await expect(linha(page, "Canal da Importação").first()).toContainText("igual");
    await previa(page).getByRole("button", { name: "Descartar a leitura" }).click();
    await expect(previa(page)).toHaveCount(0);
  });

  test("US7: desfazer arquiva o perfil criado e a lista mostra desfeita", async ({ page, request }) => {
    test.setTimeout(120_000);
    const headers = await auth(request);
    await login(page, OWNER.email, OWNER.password);
    await expect(page).toHaveURL(/\/app$/);
    await page.goto(PAGINA);
    const lista = page.getByRole("region", { name: "Importações" });
    await expect(lista.locator('[data-importacao="concluida"]')).toHaveCount(1);
    await lista.locator('[data-importacao="concluida"]').getByRole("link").click();
    await expect(page).toHaveURL(/\/app\/configuracoes\/importacao\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("table", { name: "Itens da importação" })).toBeVisible();

    await page.getByRole("button", { name: "Desfazer importação" }).click();
    const dialogo = page.getByRole("alertdialog", { name: "Desfazer esta importação?" });
    await expect(dialogo).toContainText("arquivad");
    await dialogo.getByRole("button", { name: "Desfazer importação" }).click();
    await expect(page.locator('[data-andamento="desfeita"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Desfazer importação" })).toHaveCount(0);
    await page.screenshot({ path: `${SHOTS}/013-desfeita.png`, fullPage: true });

    // o perfil criado pela importação foi arquivado (nada apagado)
    const ativos = (await (await request.get("/api/perfis", { headers })).json()) as { items: { slug: string }[] };
    expect(ativos.items.map((p) => p.slug)).not.toContain("taverna-teste");
    const arquivados = (await (await request.get("/api/perfis?archived=true", { headers })).json()) as { items: { slug: string }[] };
    expect(arquivados.items.map((p) => p.slug)).toContain("taverna-teste");
  });
});
