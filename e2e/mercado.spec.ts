import { expect, test, type Locator, type Page } from "@playwright/test";
import { aceitarRiscoEligar, criarClienteColeta, PROTOCOLO_COLETA, semearDetalhe, semearMercado, semearVitrine } from "./coletor";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, createVerifiedMember, criarClienteMcp, interruptorMcp, login, logout, nav, navLink } from "./helpers";
import { randomUUID } from "node:crypto";
import { BASE_URL } from "./fixtures";

// Spec 026 (US1, T032): com o coletor falso semeando 3 produtos × 10 dias (e um 4º com 1 dia só),
// /app/mercado mostra os cartões com o selo "estimado", o "coletando" no produto de 1 foto, o
// período na URL, "Ver tabela" e CSV do card Mais vendidos com as mesmas linhas, e o detalhe abre
// com a série. O membro vê os mesmos números.

async function abrirMercado(page: Page): Promise<void> {
  await nav(page, "Mercado de produtos");
  await expect(page).toHaveURL(/\/app\/mercado$/);
  await expect(page.getByRole("heading", { name: "Mercado de produtos", level: 1 })).toBeVisible();
}

test("026 US1: cockpit com cartões estimados, coletando, tabela, CSV e detalhe", async ({ page, request }) => {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const semente = await semearMercado(request, token, { produtos: 3, dias: 10 });
  await semearMercado(request, token, { produtos: 1, dias: 1, primeiro: 3, cliente: semente.cliente, ranking: false });

  await login(page, OWNER.email, OWNER.password);
  await abrirMercado(page);

  // ---- cards do cockpit ----
  const mais = page.locator('[data-card="Mais vendidos"]');
  await expect(mais.getByRole("heading", { name: "Mais vendidos" })).toBeVisible();
  const cartoes = mais.locator("[data-produto]");
  await expect(cartoes).toHaveCount(4);
  // o 1º é o que mais vende (20/dia): Produto e2e 0, com o selo "estimado" nos derivados
  await expect(cartoes.first()).toContainText("Produto e2e 0");
  await expect(cartoes.first().locator('[data-estimado="sim"]').first()).toBeVisible();
  await expect(cartoes.first().getByText("Loja oficial")).toBeVisible();
  // o produto de 1 foto aparece "coletando" e sem números de período
  const coletando = cartoes.filter({ hasText: "Produto e2e 3" });
  await expect(coletando.getByText("coletando", { exact: true }).first()).toBeVisible();
  // o produto sem Affiliate mostra "sem dado de afiliado"
  await expect(cartoes.filter({ hasText: "Produto e2e 2" }).getByText("sem dado de afiliado").first()).toBeVisible();

  // ---- estado da coleta ----
  const estado = page.locator('[data-card="Estado da coleta"]');
  await expect(estado.getByText("Páginas hoje")).toBeVisible();

  // ---- período na URL: 30 d é o padrão (fora); 7 d grava de/ate ----
  const atalhos = page.getByRole("group", { name: "Atalhos de período" });
  await expect(atalhos.getByRole("button", { name: "30 d" })).toHaveAttribute("aria-pressed", "true");
  await atalhos.getByRole("button", { name: "7 d" }).click();
  await expect(page).toHaveURL(/[?&]de=\d{4}-\d{2}-\d{2}.*&ate=\d{4}-\d{2}-\d{2}/);
  await expect(page.getByRole("button", { name: "Remover filtro: Período" })).toBeVisible();

  // ---- "Ver tabela" e CSV com as mesmas linhas ----
  await mais.getByRole("button", { name: "Ver tabela" }).click();
  const tabela = mais.getByRole("table");
  await expect(tabela.getByRole("row")).toHaveCount(5); // cabeçalho + 4
  await expect(tabela).toContainText("Produto e2e 0");
  const [download] = await Promise.all([page.waitForEvent("download"), mais.getByRole("button", { name: "CSV" }).click()]);
  expect(download.suggestedFilename()).toBe("mais-vendidos.csv");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const c of stream) chunks.push(Buffer.from(c));
  const csv = Buffer.concat(chunks).toString("utf8");
  expect(csv).toContain("Produto e2e 0");
  expect(csv.split("\r\n").filter(Boolean)).toHaveLength(5); // cabeçalho + 4 linhas
  expect(csv).toContain("Vendas no período");

  // ---- aba Produtos: tabela paginada no servidor e a aba na URL ----
  await page.getByRole("tab", { name: "Produtos" }).click();
  await expect(page).toHaveURL(/[?&]aba=produtos\b/);
  await expect(page.getByRole("table", { name: "Produtos do mercado" }).getByRole("row")).toHaveCount(5);
  await expect(page.getByText(/4 produtos neste recorte/)).toBeVisible();

  // ---- detalhe com a série ----
  await page.getByRole("link", { name: "Produto e2e 0" }).first().click();
  await expect(page).toHaveURL(/\/app\/mercado\/produtos\/[0-9a-f-]+/);
  await expect(page.getByRole("heading", { name: "Produto e2e 0", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Série do produto" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ficha" })).toBeVisible();
  await expect(page.getByText("Descrição do produto 0")).toBeVisible();
  // Sem perfil cadastrado ainda, os dois botões existem mas ficam desabilitados (nada a escolher).
  await expect(page.getByRole("button", { name: "Acompanhar neste perfil" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Adotar no catálogo" })).toBeVisible();
});

test("026 US1: a aba Mercado do analytics agora se chama Fontes", async ({ page }) => {
  await login(page, OWNER.email, OWNER.password);
  await nav(page, "Métricas");
  await expect(page.getByRole("tab", { name: "Fontes" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Mercado", exact: true })).toHaveCount(0);
});

// ---------------------------------------------------------------------------------------------
// US3 (T048): /app/configuracoes/coleta. O dono vê o aviso de risco, ligar sem aceite é recusado
// pela API, aceita, cria um coletor (token mostrado uma vez), liga; desligar esvazia a fila do
// coletor; o membro só vê o estado; o sino recebe "Coleta: verificação na tela" quando o coletor
// manda o evento de captcha.
// ---------------------------------------------------------------------------------------------

function sino(page: Page): Locator {
  return page.getByRole("button", { name: /^Notificações/ });
}

async function esperarNoSino(page: Page, nome: RegExp, timeout = 60_000): Promise<void> {
  await expect
    .poll(
      async () => {
        await page.reload();
        await sino(page).click();
        const n = await page.getByRole("menuitem", { name: nome }).count();
        await page.keyboard.press("Escape");
        return n;
      },
      { timeout, intervals: [2_000, 5_000] },
    )
    .toBeGreaterThan(0);
}

test("026 US3: aceite de risco, interruptor, token uma vez, fila vazia ao desligar, membro só vê o estado", async ({ page, request }) => {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };

  // Estado inicial pela API: sem aceite, ligar é 409 risco_nao_aceito (a stack e2e começa limpa).
  const cfg0 = (await (await request.get("/api/coleta/config", { headers: auth })).json()) as { version: number; riscoAceito: boolean; habilitada: boolean };
  if (!cfg0.riscoAceito) {
    const r = await request.put("/api/coleta/config", {
      headers: auth,
      data: { version: cfg0.version, habilitada: true, janelaInicio: 0, janelaFim: 23, paginasDia: 300, imagensDia: 1500, imagensPorProduto: 9, itensPorColeta: 40, pausaMinS: 5, pausaMaxS: 40 },
    });
    expect(r.status(), "ligar sem aceite").toBe(409);
    expect(((await r.json()) as { error: { code: string } }).error.code).toBe("risco_nao_aceito");
  }

  await login(page, OWNER.email, OWNER.password);
  await nav(page, "Coleta de mercado");
  await expect(page).toHaveURL(/\/app\/configuracoes\/coleta$/);
  await expect(page.getByRole("heading", { name: "Coleta de mercado", level: 1 })).toBeVisible();
  await expect(page.getByTestId("coleta-estado")).toBeVisible();

  const interruptor = page.getByRole("switch", { name: "Coleta" });
  if (!cfg0.riscoAceito) {
    // Aviso de risco e interruptor travado até o aceite.
    await expect(page.getByTestId("coleta-risco")).toContainText("conta de afiliado");
    await expect(interruptor).toBeDisabled();
    await page.getByRole("button", { name: "Aceito o risco" }).first().click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText("Aceitar o risco da coleta?");
    await dialog.getByRole("button", { name: "Aceito o risco" }).click();
    await expect(page.getByTestId("coleta-risco")).toContainText("Risco aceito");
  }
  await expect(interruptor).toBeEnabled();

  // Novo coletor: o token aparece uma vez e some ao fechar.
  await page.getByRole("button", { name: "Novo coletor" }).click();
  const nome = `Desktop e2e ${Date.now()}`;
  await page.getByLabel("Nome").fill(nome);
  await page.getByRole("button", { name: "Criar e mostrar o token" }).click();
  const tokenDialog = page.getByRole("dialog", { name: `Credencial de ${nome}` });
  await expect(tokenDialog).toBeVisible();
  const scol = await tokenDialog.getByLabel("Credencial").inputValue();
  expect(scol).toMatch(/^scol_[A-Za-z0-9_-]{8}_[A-Za-z0-9_-]{43}$/);
  await tokenDialog.getByRole("button", { name: "Já guardei" }).click();
  await expect(tokenDialog).toHaveCount(0);
  const linha = page.getByRole("table", { name: "Coletores" }).getByRole("row").filter({ hasText: nome });
  await expect(linha).toBeVisible();
  await expect(linha).toContainText(scol.split("_")[1]!);
  await expect(linha).not.toContainText(scol);

  // Liga pela tela; a fila responde habilitada ao coletor.
  if (!(await interruptor.isChecked())) await interruptor.click();
  await expect(page.getByTestId("coleta-interruptor-estado")).toHaveText("Ligada");
  const hCol = { Authorization: `Bearer ${scol}`, ...PROTOCOLO_COLETA };
  const fila1 = (await (await request.get("/api/coleta/fila", { headers: hCol })).json()) as { habilitada: boolean; motivoVazia: string | null };
  expect(fila1.habilitada).toBe(true);

  // Desliga: a fila vem vazia com o motivo.
  await interruptor.click();
  await expect(page.getByTestId("coleta-interruptor-estado")).toHaveText("Desligada");
  const fila2 = (await (await request.get("/api/coleta/fila", { headers: hCol })).json()) as { habilitada: boolean; tarefas: unknown[]; motivoVazia: string | null };
  expect(fila2.habilitada).toBe(false);
  expect(fila2.tarefas).toEqual([]);
  expect(fila2.motivoVazia).toBe("desligada");
  // Liga de volta para o resto do arquivo.
  await interruptor.click();
  await expect(page.getByTestId("coleta-interruptor-estado")).toHaveText("Ligada");

  // Sino: o coletor abre uma rodada e manda "captcha" → notificação para o dono.
  const aberta = await request.post("/api/coleta/coletas", { headers: hCol, data: { versaoColetor: "0.1.0-e2e", protocolo: 1 } });
  expect(aberta.status(), "abrir rodada").toBe(201);
  const coletaId = ((await aberta.json()) as { id: string }).id;
  const ev = await request.post("/api/coleta/eventos", { headers: hCol, data: { tipo: "captcha", coletaId } });
  expect(ev.status(), "evento captcha").toBe(201);
  await esperarNoSino(page, /Coleta pausada: verificação na rede/);
  await expect(page.getByTestId("coleta-situacao")).toContainText(/Aguardando Continuar|Pausada/);
  await page.getByRole("button", { name: "Continuar" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Continuar" }).click();
  await expect(page.getByTestId("coleta-situacao")).toContainText("Pausada: verificação na tela");
  await request.post(`/api/coleta/coletas/${coletaId}/fim`, { headers: hCol, data: { motivo: "parado" } });
  await logout(page);

  // Membro: sem o item no menu; a tela mostra só o estado; a API recusa as escritas.
  const member = await createVerifiedMember(page);
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await expect(navLink(page, "Coleta de mercado")).toHaveCount(0);
  await page.goto("/app/configuracoes/coleta");
  await expect(page.getByTestId("coleta-estado")).toBeVisible();
  await expect(page.getByRole("switch", { name: "Coleta" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Novo coletor" })).toHaveCount(0);
  const memberToken = await apiToken(request, member.email, member.final);
  for (const [metodo, url] of [
    ["GET", "/api/coleta/config"],
    ["GET", "/api/coleta/clientes"],
    ["POST", "/api/coleta/clientes"],
  ] as const) {
    const res = await request.fetch(url, { method: metodo, headers: { Authorization: `Bearer ${memberToken}` }, data: metodo === "GET" ? undefined : { nome: "x", mercado: "BR" } });
    expect(res.status(), `${metodo} ${url} pelo membro`).toBe(403);
  }
  expect((await request.get("/api/coleta/estado", { headers: { Authorization: `Bearer ${memberToken}` } })).status()).toBe(200);
});

test("026 US3: o semeador do e2e grava pela ingestão com um token real", async ({ request }) => {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  await aceitarRiscoEligar(request, token);
  const cliente = await criarClienteColeta(request, token, `semeador ${Date.now()}`);
  const semente = await semearMercado(request, token, { produtos: 1, dias: 2, primeiro: 90, cliente, ranking: false });
  expect(semente.produtos).toHaveLength(1);
  const lista = (await (await request.get("/api/mercado/produtos", { headers: { Authorization: `Bearer ${token}` }, params: { q: "Produto e2e 90" } })).json()) as { total: number };
  expect(lista.total).toBe(1);
});

// ---------------------------------------------------------------------------------------------
// US4 (T057): o dono escolhe 2 categorias do nicho; cola um link → interesse manual aparece; o
// membro pausa e reativa; a vitrine semeada vira interesse "vitrine" nos dois perfis; um cliente
// MCP não cria interesse (somente_humano).
// ---------------------------------------------------------------------------------------------

test("026 US4: nicho, link manual, pausar/reativar pelo membro, vitrine para todos e MCP só lê", async ({ page, request }) => {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const sfx = randomUUID().slice(0, 6);
  const perfilA = await createPerfilViaApi(request, token, { name: `Mercado A ${sfx}`, slug: `mercado-a-${sfx}` });
  const perfilB = await createPerfilViaApi(request, token, { name: `Mercado B ${sfx}`, slug: `mercado-b-${sfx}` });
  // Lago com categorias (Moda > Feminino > Shorts) e a vitrine com o produto 20.
  const semente = await semearMercado(request, token, { produtos: 2, dias: 2, primeiro: 20, rankingJanela: "1d" });
  await semearVitrine(request, semente.cliente, [20]);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/perfis/${perfilA}?aba=mercado`);
  await expect(page.getByRole("heading", { name: "Nicho no TikTok Shop" })).toBeVisible();

  // ---- categorias do nicho (dono) ----
  const select = page.getByLabel("Adicionar categoria");
  const escolherCategoria = async (caminho: string) => {
    const opcao = select.locator("option").filter({ hasText: new RegExp(`^${caminho.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")} \\(`) }).first();
    await expect(opcao).toBeAttached();
    await select.selectOption((await opcao.getAttribute("value"))!);
    await page.getByRole("button", { name: "Adicionar", exact: true }).click();
  };
  await escolherCategoria("Moda > Feminino");
  await escolherCategoria("Moda > Feminino > Shorts");
  await expect(page.getByRole("list", { name: "Categorias escolhidas" }).getByRole("listitem")).toHaveCount(2);
  await page.getByRole("button", { name: "Salvar nicho" }).click();
  await expect(page.getByText("Nicho salvo.")).toBeVisible();
  const cfg = (await (await request.get(`/api/perfis/${perfilA}/mercado/config`, { headers: auth })).json()) as { categoriaIds: string[]; version: number };
  expect(cfg.categoriaIds).toHaveLength(2);

  // ---- link manual ----
  const linkId = `74${sfx.replace(/\D/g, "1").padEnd(17, "7")}`;
  await page.getByLabel("Link do produto").fill(`https://www.tiktok.com/shop/pdp/legging/${linkId}?utm=x`);
  await page.getByLabel("Nota (opcional)").fill("visto no vídeo");
  await page.getByRole("button", { name: "Acompanhar", exact: true }).click();
  await expect(page.getByText(/Acompanhando/)).toBeVisible();
  const tabela = page.getByRole("table", { name: "Acompanhamentos" });
  const linhaManual = tabela.getByRole("row").filter({ hasText: linkId });
  await expect(linhaManual).toContainText("Manual (link)");
  await expect(linhaManual).toContainText("Ativo");
  // A vitrine vale para todos os perfis: aparece em A e em B.
  const linhaVitrine = tabela.getByRole("row").filter({ hasText: "Produto e2e 20" }).filter({ hasText: "Vitrine do dono" });
  await expect(linhaVitrine).toContainText("todos os perfis");
  await page.goto(`/app/perfis/${perfilB}?aba=mercado`);
  await expect(page.getByRole("table", { name: "Acompanhamentos" }).getByRole("row").filter({ hasText: "Vitrine do dono" })).toHaveCount(1);
  await logout(page);

  // ---- membro pausa e reativa ----
  const member = await createVerifiedMember(page);
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/perfis/${perfilA}?aba=mercado`);
  await expect(page.getByRole("button", { name: "Salvar nicho" })).toHaveCount(0); // só o dono edita o nicho
  const tabelaM = page.getByRole("table", { name: "Acompanhamentos" });
  const linhaM = tabelaM.getByRole("row").filter({ hasText: linkId });
  await linhaM.getByRole("button", { name: "Pausar" }).click();
  await expect(page.getByText("Acompanhamento pausado")).toBeVisible();
  await expect(linhaM).toContainText("Pausado");
  await linhaM.getByRole("button", { name: "Reativar" }).click();
  await expect(linhaM).toContainText("Ativo");
  // A aba Acompanhamentos do cockpit lista com o perfil.
  await nav(page, "Mercado de produtos");
  await page.getByRole("tab", { name: "Acompanhamentos" }).click();
  await expect(page.getByRole("table", { name: "Acompanhamentos" }).getByRole("row").filter({ hasText: linkId })).toContainText(`Mercado A ${sfx}`);
  await logout(page);

  // ---- MCP: lê, mas não cria interesse ----
  await interruptorMcp(request, token, true);
  const mcp = await criarClienteMcp(request, token, `analista ${sfx}`, "propostas");
  const antes = ((await (await request.get(`/api/perfis/${perfilA}/mercado/interesses`, { headers: auth })).json()) as { total: number }).total;
  const leitura = await fetch(new URL(`/api/perfis/${perfilA}/mercado/interesses`, BASE_URL).toString(), { headers: { Authorization: `Bearer ${mcp.token}` } });
  expect(leitura.status).toBe(200);
  const escrita = await fetch(new URL(`/api/perfis/${perfilA}/mercado/interesses`, BASE_URL).toString(), {
    method: "POST",
    headers: { Authorization: `Bearer ${mcp.token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ url: `https://www.tiktok.com/shop/pdp/x/${linkId}1` }),
  });
  expect(escrita.status).toBe(403);
  expect(((await escrita.json()) as { error: { code: string } }).error.code).toBe("somente_humano");
  const total = (await (await request.get(`/api/perfis/${perfilA}/mercado/interesses`, { headers: auth })).json()) as { total: number };
  expect(total.total).toBe(antes); // o MCP não criou nada (a trilha pode ter criado interesses de ranking antes)
});

// ---------------------------------------------------------------------------------------------
// US5 (T062) e US6 (T066): o detalhe com ficha versionada, galeria, rankings com variação, vídeos
// e avaliações sem nome; a aba Lojas → seguir loja para um perfil → aparece na aba Mercado do
// perfil; "Adotar no catálogo" responde `passo_indisponivel` enquanto a 012 não está nesta
// instalação.
// ---------------------------------------------------------------------------------------------

test("026 US5/US6: detalhe completo, lojas e seguir loja, adotar indisponível sem a 012", async ({ page, request }) => {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const sfx = randomUUID().slice(0, 6);
  const perfilId = await createPerfilViaApi(request, token, { name: `Mercado L ${sfx}`, slug: `mercado-l-${sfx}` });
  const semente = await semearMercado(request, token, { produtos: 3, dias: 2, primeiro: 40, rankingJanela: "30d" });
  await semearDetalhe(request, semente.cliente, 40);
  const lista = (await (await request.get("/api/mercado/produtos", { headers: auth, params: { q: "Produto e2e 40" } })).json()) as { itens: { id: string }[] };
  const produtoId = lista.itens[0]!.id;

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/mercado/produtos/${produtoId}`);
  await expect(page.getByRole("heading", { name: "Produto e2e 40 v2", level: 1 })).toBeVisible();
  // Ficha versionada: 2 versões, com "Ver versões anteriores".
  await expect(page.getByRole("heading", { name: "Ficha" })).toBeVisible();
  await page.getByRole("button", { name: "Ver versões anteriores" }).click();
  await expect(page.getByTestId("ficha-versoes")).toContainText("Produto e2e 40");
  await expect(page.getByTestId("ficha-versoes")).toContainText("título");
  // Rankings: no 2º dia o produto 40 caiu de 1 para 2 (o semeador alterna); com 2 dias não há
  // variação de 7 dias, mas a linha mostra o ranking, a posição atual (2) e a melhor (1).
  const rankings = page.getByTestId("rankings-produto");
  await expect(rankings).toContainText("Mais vendidos · 30d");
  const linhaRk = rankings.getByRole("row").filter({ hasText: "Mais vendidos" });
  await expect(linhaRk.getByRole("cell").nth(1)).toHaveText("2");
  await expect(linhaRk.getByRole("cell").nth(2)).toHaveText("1");
  // Vídeos: só o @ e contadores.
  const videos = page.getByRole("list", { name: "Vídeos top" });
  await expect(videos.getByRole("listitem")).toHaveCount(3);
  await expect(videos).toContainText("@criadora.0");
  await expect(videos).toContainText("300.000 views");
  // Avaliações: 5, sem nome, uma com foto.
  const avaliacoes = page.getByRole("list", { name: "Avaliações" });
  await expect(avaliacoes.locator("> li")).toHaveCount(5); // só os itens diretos (as fotos têm lista própria)
  await expect(avaliacoes).not.toContainText("autor-");
  await expect(page.getByRole("list", { name: "Fotos da avaliação" }).getByRole("img")).toHaveCount(1);
  await expect(page.getByText(/5 avaliações · 1 com foto · nunca mostramos quem escreveu/)).toBeVisible();

  // Adotar: a 012 não está nesta instalação → passo_indisponivel (aviso na tela).
  await page.getByRole("button", { name: "Adotar no catálogo" }).click();
  const dialogo = page.getByRole("dialog", { name: "Adotar no catálogo" });
  await dialogo.getByRole("button", { name: "Adotar", exact: true }).click();
  await expect(dialogo).toContainText(/cadastro de produtos \(spec 012\)/);
  await page.keyboard.press("Escape");

  // Aba Lojas → seguir a Loja X para o perfil → aparece na aba Mercado do perfil.
  await nav(page, "Mercado de produtos");
  await page.getByRole("tab", { name: "Lojas" }).click();
  const cartao = page.locator('[data-loja="loja123"]').first();
  await expect(cartao).toContainText("Loja X");
  await expect(cartao).toContainText("Loja oficial");
  await cartao.getByRole("button", { name: "Seguir loja neste perfil" }).click();
  const seguir = page.getByRole("dialog", { name: /Seguir Loja X/ });
  await seguir.getByLabel("Perfil").selectOption({ label: `Mercado L ${sfx}` });
  await seguir.getByRole("button", { name: "Seguir", exact: true }).click();
  await expect(page.getByText(/Loja X seguida/)).toBeVisible();
  await page.goto(`/app/perfis/${perfilId}?aba=mercado`);
  await expect(page.getByRole("list", { name: "Lojas seguidas" })).toContainText("Loja X");
  const cfg = (await (await request.get(`/api/perfis/${perfilId}/mercado/config`, { headers: auth })).json()) as { lojasSeguidas: { nome: string }[] };
  expect(cfg.lojasSeguidas.map((l) => l.nome)).toEqual(["Loja X"]);
});
