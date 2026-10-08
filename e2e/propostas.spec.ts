import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import {
  apiToken,
  chamarTool,
  createPerfilViaApi,
  createVerifiedMember,
  criarClienteMcp,
  interruptorMcp,
  login,
  syntheticMp4,
} from "./helpers";

// Spec 009 (T052): o agente com escopo "propostas" grava pelo `/mcp` e o dono decide.
// - a edição de textos de um destino pendente leva o selo "Agente" no histórico, e o dono reverte em
//   2 cliques (SC-004);
// - a proposta de texto aparece na caixa e no destino; "Aplicar" preenche o formulário, o "Salvar"
//   grava com a proposta de origem, e a proposta fica "aplicada";
// - descartar com motivo;
// - destino aprovado: a tool recusa com `destino_aprovado` e os textos não mudam;
// - o envio selecionado pela tool aparece em "Gerar cortes", sem ir ao OpenShorts.

type Auth = { Authorization: string };

interface DestinoE2e {
  id: string;
  conta: { id: string };
  descricao: string;
  estado: string;
  version: number;
}

async function getJson<T>(request: APIRequestContext, auth: Auth, url: string): Promise<T> {
  const res = await request.get(url, { headers: auth });
  expect(res.status(), `GET ${url}`).toBe(200);
  return (await res.json()) as T;
}

async function destinoAtual(request: APIRequestContext, auth: Auth, destinoId: string): Promise<DestinoE2e> {
  return (await getJson<{ destino: DestinoE2e }>(request, auth, `/api/destinos/${destinoId}`)).destino;
}

// Perfil + conta TikTok + vídeo próprio (já "pronto") com um destino pendente na conta.
async function cenario(request: APIRequestContext, token: string, sfx: string) {
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Propostas ${sfx}`, slug: `propostas-${sfx}` });
  const conta = await request.post(`/api/perfis/${perfilId}/contas`, { headers: auth, data: { platform: "tiktok", handle: `prop${sfx}`, status: "ativa" } });
  expect(conta.status(), `POST contas: ${await conta.text()}`).toBe(201);
  const contaId = ((await conta.json()) as { conta: { id: string } }).conta.id;

  const arquivo = join(tmpdir(), `sociman-e2e-propostas-${sfx}.mp4`);
  syntheticMp4(arquivo, 3);
  const titulo = `Receita ${sfx}`;
  const up = await request.post(`/api/perfis/${perfilId}/conteudos/arquivo`, {
    headers: auth,
    multipart: { file: { name: `${titulo}.mp4`, mimeType: "video/mp4", buffer: readFileSync(arquivo) }, titulo },
  });
  expect(up.status(), `POST conteudos/arquivo: ${await up.text()}`).toBe(201);
  const conteudoId = ((await up.json()) as { conteudo: { id: string } }).conteudo.id;

  const d = await request.post(`/api/conteudos/${conteudoId}/destinos`, { headers: auth, data: { contaId, descricao: "Legenda do dono" } });
  expect([200, 201], `POST destinos: ${await d.text()}`).toContain(d.status());
  const destinos = (await getJson<{ conteudo: { destinos: DestinoE2e[] } }>(request, auth, `/api/conteudos/${conteudoId}`)).conteudo.destinos;
  const destino = destinos.find((x) => x.conta.id === contaId)!;
  return { perfilId, contaId, conteudoId, destinoId: destino.id, titulo };
}

function resultado(r: Awaited<ReturnType<typeof chamarTool>>) {
  expect(r.status, "tools/call").toBe(200);
  return r.body?.result as { isError?: boolean; structuredContent?: Record<string, unknown> & { code?: string } };
}

function painel(page: Page): Locator {
  return page.getByRole("region", { name: "Anotações e propostas desta conta" });
}

test("US4: proposta do agente → aplicar e salvar; descartar; selo e reversão; aprovado recusa; seleção de vídeo", async ({ page, request }) => {
  test.setTimeout(300_000);
  const sfx = randomUUID().slice(0, 6);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  await interruptorMcp(request, token, true);
  const { perfilId, conteudoId, contaId, destinoId } = await cenario(request, token, sfx);
  const agente = await criarClienteMcp(request, token, `Planejador ${sfx}`, "propostas");

  // ---- o agente edita os textos do destino pendente (escrita direta permitida) ----
  let d = await destinoAtual(request, auth, destinoId);
  expect(d.estado).toBe("pendente");
  const edicao = resultado(await chamarTool(agente.token, "destinos_update", { destino_id: destinoId, version: d.version, descricao: "Legenda escrita pelo agente" }));
  expect(edicao.isError ?? false, JSON.stringify(edicao.structuredContent)).toBe(false);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/conteudos/${conteudoId}?conta=${contaId}`);
  await expect(page.getByRole("textbox", { name: /^Legenda/ })).toHaveValue("Legenda escrita pelo agente");
  await page.getByRole("button", { name: "Histórico desta conta" }).click();
  const versaoAgente = page.getByRole("listitem", { name: `Versão ${d.version + 1}` });
  await expect(versaoAgente.getByText(`Agente: ${agente.nome}`)).toBeVisible();

  // o dono reverte a edição do agente em 2 cliques (SC-004)
  await page.getByRole("listitem", { name: `Versão ${d.version}` }).getByRole("button", { name: "Reverter para esta versão" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reverter", exact: true }).click();
  await expect(page.getByRole("textbox", { name: /^Legenda/ })).toHaveValue("Legenda do dono");
  d = await destinoAtual(request, auth, destinoId);
  expect(d.descricao).toBe("Legenda do dono");

  // o link do registro MCP (`/app/conteudos?destino=<id>`) abre o detalhe do conteúdo do destino
  await page.goto(`/app/conteudos?destino=${destinoId}`);
  await expect(page).toHaveURL(new RegExp(`/app/conteudos/${conteudoId}\\?destino=${destinoId}`));
  await expect(page.getByRole("textbox", { name: /^Legenda/ })).toHaveValue("Legenda do dono");

  // ---- proposta de texto: aparece na caixa (com o contador) e no destino; aplicar + salvar ----
  const proposta = resultado(
    await chamarTool(agente.token, "anotacoes_create", {
      alvoTipo: "destino",
      alvoId: destinoId,
      tipo: "proposta_texto",
      texto: "Legenda mais curta e com gancho",
      campos: { descricao: "Airfryer em 10 minutos", hashtags: ["receita", "airfryer"] },
    }),
  );
  expect(proposta.isError ?? false, JSON.stringify(proposta.structuredContent)).toBe(false);
  // os textos do destino não mudam com a proposta
  expect((await destinoAtual(request, auth, destinoId)).descricao).toBe("Legenda do dono");

  await page.goto("/app/propostas");
  await expect(page.getByRole("navigation", { name: "Menu principal" }).getByRole("link", { name: /^Propostas dos agentes \d+$/ })).toBeVisible();
  const caixa = page.getByRole("table", { name: "Propostas dos agentes" });
  const linha = caixa.getByRole("row").filter({ hasText: "Legenda mais curta e com gancho" });
  await expect(linha.getByText(`Agente: ${agente.nome}`)).toBeVisible();
  await linha.getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`/app/conteudos/${conteudoId}`));

  const card = painel(page).getByRole("article").filter({ hasText: "Legenda mais curta e com gancho" });
  await expect(card.getByText(`Agente: ${agente.nome}`)).toBeVisible();
  await card.getByRole("button", { name: "Aplicar" }).click();
  await expect(page.getByRole("textbox", { name: /^Legenda/ })).toHaveValue("Airfryer em 10 minutos");
  await expect(page.getByText(`Proposta de ${agente.nome} no formulário`)).toBeVisible();
  // nada salvo antes do clique humano
  expect((await destinoAtual(request, auth, destinoId)).descricao).toBe("Legenda do dono");
  await page.getByRole("button", { name: "Salvar textos" }).click();
  await expect(page.getByText("Textos salvos a partir da proposta.")).toBeVisible();
  await expect(card.getByText("Aplicada", { exact: true })).toBeVisible();
  d = await destinoAtual(request, auth, destinoId);
  expect(d.descricao).toBe("Airfryer em 10 minutos");
  await page.getByRole("button", { name: "Histórico desta conta" }).click();
  await expect(page.getByRole("listitem", { name: `Versão ${d.version}` }).getByText(`a partir da proposta de ${agente.nome}`)).toBeVisible();
  const versoes = await getJson<{ items: { autor?: { tipo: string }; details: Record<string, unknown> }[] }>(request, auth, `/api/destinos/${destinoId}/versions`);
  expect(versoes.items[0]?.autor?.tipo).toBe("usuario");
  expect(versoes.items[0]?.details.proposta).toBeTruthy();

  // ---- descartar com motivo ----
  resultado(await chamarTool(agente.token, "anotacoes_create", { alvoTipo: "destino", alvoId: destinoId, tipo: "observacao", texto: "Talvez postar à noite" }));
  await page.reload();
  const obs = painel(page).getByRole("article").filter({ hasText: "Talvez postar à noite" });
  await obs.getByRole("button", { name: "Descartar" }).click();
  const dialogo = page.getByRole("dialog");
  await dialogo.getByLabel("Motivo (opcional)").fill("Já temos horário fixo");
  await dialogo.getByRole("button", { name: "Descartar" }).click();
  await expect(obs.getByText("Descartada", { exact: true })).toBeVisible();
  await expect(obs).toContainText("Motivo: Já temos horário fixo");

  // ---- destino aprovado: a tool recusa e os textos não mudam ----
  d = await destinoAtual(request, auth, destinoId);
  const aprovar = await request.post(`/api/destinos/${destinoId}/aprovar`, { headers: auth, data: { version: d.version } });
  expect(aprovar.status(), `aprovar: ${await aprovar.text()}`).toBe(200);
  d = await destinoAtual(request, auth, destinoId);
  const recusada = resultado(await chamarTool(agente.token, "destinos_update", { destino_id: destinoId, version: d.version, descricao: "Outra legenda" }));
  expect(recusada.isError).toBe(true);
  expect(recusada.structuredContent?.code).toBe("destino_aprovado");
  expect((await destinoAtual(request, auth, destinoId)).descricao).toBe("Airfryer em 10 minutos");

  // ---- a tool seleciona um vídeo-fonte: aparece em "Gerar cortes", sem envio ----
  const tituloVideo = `Vídeo escolhido pelo agente ${sfx}`;
  const sel = resultado(
    await chamarTool(agente.token, "envios_selecionar", { perfil_id: perfilId, url: `https://www.youtube.com/watch?v=e2e${sfx}xx`, titulo: tituloVideo }),
  );
  expect(sel.isError ?? false, JSON.stringify(sel.structuredContent)).toBe(false);
  await page.goto(`/app/envios?perfil=${perfilId}`);
  await expect(page.getByText(tituloVideo).first()).toBeVisible();
});

// ---- spec 024 (T051, T060, T062): FilterBar, busca no servidor e os dois vazios ----

test("024: busca no servidor, filtro de 'Mais filtros' vira etiqueta, recarregar mantém, remover pela etiqueta", async ({ page, request }) => {
  const sfx = randomUUID().slice(0, 6);
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Filtros ${sfx}`, slug: `filtros-${sfx}` });
  const texto = `Observação única ${sfx} sobre a legenda`;
  const r = await request.post("/api/anotacoes", { headers: auth, data: { alvoTipo: "perfil", alvoId: perfilId, texto } });
  expect(r.status(), `POST anotacoes: ${await r.text()}`).toBe(201);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/propostas");
  const tabela = page.getByRole("table", { name: "Propostas dos agentes" });
  // sem botão "Filtrar" e com uma busca só
  await expect(page.getByRole("button", { name: "Filtrar" })).toHaveCount(0);
  await expect(page.getByRole("searchbox", { name: "Buscar nas propostas" })).toHaveCount(0);

  // busca no servidor, sem acento e sem caixa
  await page.getByRole("searchbox", { name: "Buscar", exact: true }).fill(`OBSERVACAO UNICA ${sfx}`);
  await expect(page).toHaveURL(new RegExp(`[?&]q=OBSERVACAO`));
  await expect(tabela.getByRole("row").filter({ hasText: texto })).toBeVisible();
  await expect(tabela.getByRole("row")).toHaveCount(2); // cabeçalho + a linha

  // filtro dentro de "Mais filtros": vira etiqueta e conta no botão
  await page.getByRole("button", { name: "Mais filtros" }).click();
  const gaveta = page.getByRole("dialog", { name: "Mais filtros" });
  await gaveta.getByLabel("Tipo").selectOption({ label: "Observação" });
  await page.keyboard.press("Escape");
  await expect(gaveta).toBeHidden();
  const ativos = page.getByRole("group", { name: "Filtros ativos" });
  await expect(ativos.getByText("Tipo:")).toBeVisible();
  await expect(page.getByRole("button", { name: "Mais filtros (1)" })).toBeVisible();
  await expect(page).toHaveURL(/[?&]tipo=observacao/);

  // recarregar mantém os filtros
  await page.reload();
  await expect(page.getByRole("searchbox", { name: "Buscar", exact: true })).toHaveValue(`OBSERVACAO UNICA ${sfx}`);
  await expect(ativos.getByText("Tipo:")).toBeVisible();
  await expect(tabela.getByRole("row").filter({ hasText: texto })).toBeVisible();

  // remover pela etiqueta
  await ativos.getByRole("button", { name: "Remover filtro: Tipo" }).click();
  await expect(ativos.getByText("Tipo:")).toHaveCount(0);
  await expect(page).not.toHaveURL(/[?&]tipo=/);
  await expect(page.getByRole("button", { name: "Mais filtros", exact: true })).toBeVisible();
});

test("024: vazio com filtro mostra 'Limpar filtros', que volta à caixa padrão", async ({ page }) => {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/propostas?q=nada-${randomUUID().slice(0, 8)}`);
  const tabela = page.getByRole("table", { name: "Propostas dos agentes" });
  await expect(tabela.getByRole("status")).toHaveText("Nenhuma proposta com estes filtros");
  await tabela.getByRole("button", { name: "Limpar filtros" }).click();
  await expect(page).toHaveURL(/\/app\/propostas$/);
  await expect(page.getByRole("searchbox", { name: "Buscar", exact: true })).toHaveValue("");
});

// A caixa é global (outros testes gravam propostas): a lista vazia vem de uma resposta interceptada.
async function semPropostas(page: Page) {
  await page.route(
    (url) => url.pathname === "/api/anotacoes",
    (route) =>
      route.request().method() === "GET"
        ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ anotacoes: [], nextCursor: null }) })
        : route.fallback(),
  );
}

const SEM_PROPOSTA = "Ainda não chegou nenhuma proposta";

test("024: vazio sem filtro — o dono vê 'Configurar agentes (MCP)'", async ({ page }) => {
  await semPropostas(page);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/propostas");
  const tabela = page.getByRole("table", { name: "Propostas dos agentes" });
  await expect(tabela.getByRole("status")).toHaveText(SEM_PROPOSTA);
  await expect(tabela.getByText(/só chegam depois que os agentes forem ligados ao SociMan pelo MCP/)).toBeVisible();
  await tabela.getByRole("link", { name: "Configurar agentes (MCP)" }).click();
  await expect(page).toHaveURL(/\/app\/configuracoes\/agentes$/);
});

test("024: vazio sem filtro — o membro não vê a ação de configurar", async ({ page }) => {
  test.setTimeout(120_000);
  const membro = await createVerifiedMember(page);
  await semPropostas(page);
  await login(page, membro.email, membro.final);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/propostas");
  const tabela = page.getByRole("table", { name: "Propostas dos agentes" });
  await expect(tabela.getByRole("status")).toHaveText(SEM_PROPOSTA);
  await expect(tabela.getByText(/só chegam depois que os agentes forem ligados/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Configurar agentes (MCP)" })).toHaveCount(0);
});
