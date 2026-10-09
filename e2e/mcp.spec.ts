import { randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { BASE_URL, OWNER } from "./fixtures";
import {
  apiToken,
  chamarMcp,
  chamarTool,
  createPerfilViaApi,
  createVerifiedMember,
  criarClienteMcp,
  interruptorMcp,
  login,
  logout,
  nav,
  navLink,
} from "./helpers";

// Spec 009 (T030, T038, T059): a tela "Agentes (MCP)" e o endpoint `/mcp` pelo edge efêmero.
// US1: o dono cria o cliente e vê a credencial UMA vez; rotacionar invalida a antiga; revogar corta
// na hora; o interruptor corta todos; o membro não vê o menu e a API responde 403. US2: `tools/list`
// do escopo, `perfis_list` igual à tela, `Origin` de navegador → 403, PROIBIDAS → somente_humano.
// US5: o registro filtra por cliente e mostra o "limite"; nenhuma credencial aparece na página.
// As credenciais nascem aqui e só vivem em memória (o `chamarMcp` usa o fetch do Node).

const SMCP = /smcp_[a-z2-7]{8}_[A-Za-z0-9_-]{43}/;

// Quantas tools cada escopo tem, pelo `packages/contract/mcp-tools.json` gerado (R2).
function toolsEsperadas(): { leitura: number; propostas: number } {
  const arq = new URL("../packages/contract/mcp-tools.json", import.meta.url);
  if (!existsSync(arq)) return { leitura: 62, propostas: 67 };
  const j = JSON.parse(readFileSync(arq, "utf8")) as { leitura: unknown[]; propostas: unknown[] };
  const propostas = j.propostas.length >= j.leitura.length ? j.propostas.length : j.leitura.length + j.propostas.length;
  return { leitura: j.leitura.length, propostas };
}

function linhaCliente(page: Page, nome: string): Locator {
  return page.getByRole("table", { name: "Agentes conectados (MCP)" }).getByRole("row").filter({ hasText: nome });
}

async function nomesDasTools(token: string): Promise<string[]> {
  const r = await chamarMcp(token, "tools/list");
  expect(r.status, "tools/list").toBe(200);
  const tools = (r.body?.result as { tools: { name: string }[] }).tools;
  return tools.map((t) => t.name);
}

// Lê a credencial do diálogo "uma vez" e fecha (o valor só fica nesta variável).
async function lerTokenDoDialogo(page: Page): Promise<string> {
  const dialogo = page.getByRole("dialog");
  await expect(dialogo.getByText("Guarde agora, ela não será mostrada de novo")).toBeVisible();
  await expect(dialogo.getByRole("button", { name: "Copiar" })).toBeVisible();
  const token = await dialogo.getByLabel("Credencial").inputValue();
  expect(token).toMatch(SMCP);
  await dialogo.getByRole("button", { name: "Já guardei" }).click();
  await expect(dialogo).toBeHidden();
  return token;
}

async function ligarPelaTela(page: Page, ligar: boolean): Promise<void> {
  const sw = page.getByRole("switch", { name: "Acesso MCP" });
  if ((await sw.getAttribute("aria-checked")) !== String(ligar)) await sw.click();
  await expect(page.getByTestId("mcp-estado")).toHaveText(ligar ? "Ligado" : "Desligado");
}

async function apiDireta(token: string, metodo: "GET" | "POST", url: string, data?: unknown) {
  // fetch do Node: o token MCP não passa pelo `request` do Playwright
  const res = await fetch(new URL(url, BASE_URL).toString(), {
    method: metodo,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  return { status: res.status, body: (await res.json().catch(() => null)) as { error?: { code: string } } | null };
}

test.describe.configure({ mode: "serial" });

test("US1: o dono cria, rotaciona e revoga clientes; o interruptor corta todos; o membro não acessa", async ({ page, request }) => {
  test.setTimeout(240_000);
  const sfx = randomUUID().slice(0, 6);
  const esperado = toolsEsperadas();
  const donoToken = await apiToken(request, OWNER.email, OWNER.password);

  // ---- tela: interruptor começa desligado; o dono liga ----
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await nav(page, "Agentes (MCP)");
  await expect(page).toHaveURL(/\/app\/configuracoes\/agentes$/);
  await expect(page.getByRole("heading", { name: "Agentes (MCP)" })).toBeVisible();
  await ligarPelaTela(page, true);

  // ---- criar "Caçador": a credencial aparece uma vez ----
  const cacador = `Caçador ${sfx}`;
  await page.getByRole("button", { name: "Novo cliente" }).click();
  const novo = page.getByRole("dialog", { name: "Novo cliente MCP" });
  await novo.getByLabel("Nome").fill(cacador);
  await novo.getByLabel("Escopo").selectOption({ label: "Só leitura" });
  await novo.getByRole("button", { name: "Criar cliente" }).click();
  const token1 = await lerTokenDoDialogo(page);
  await expect(linhaCliente(page, cacador).getByText("Ativo", { exact: true })).toBeVisible();
  await expect(linhaCliente(page, cacador).getByText("sem uso")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(SMCP);

  // a credencial autentica um tools/list (só as de leitura, em ordem alfabética)
  const nomes = await nomesDasTools(token1);
  expect(nomes).toHaveLength(esperado.leitura);
  expect(nomes).toEqual([...nomes].sort());
  expect(nomes).toContain("perfis_list");
  expect(nomes).not.toContain("anotacoes_create");
  expect(nomes).not.toContain("destinos_aprovar");

  // ---- rotacionar: a antiga para na hora, a nova vale ----
  await linhaCliente(page, cacador).getByRole("button", { name: "Rotacionar" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Rotacionar" }).click();
  const token2 = await lerTokenDoDialogo(page);
  expect(token2).not.toBe(token1);
  expect((await chamarMcp(token1, "tools/list")).status, "token antigo depois da rotação").toBe(401);
  expect((await chamarMcp(token2, "tools/list")).status, "token novo").toBe(200);

  // ---- um segundo cliente (pela API) para provar que o interruptor corta todos ----
  const outro = await criarClienteMcp(request, donoToken, `Analista ${sfx}`, "leitura");
  expect((await chamarMcp(outro.token, "tools/list")).status).toBe(200);

  // ---- interruptor desligado: os dois recusados ----
  await ligarPelaTela(page, false);
  for (const t of [token2, outro.token]) {
    const r = await chamarMcp(t, "tools/list");
    expect(r.status, "interruptor desligado").toBe(503);
    expect(JSON.stringify(r.body)).toContain("desligado");
  }
  await ligarPelaTela(page, true);
  expect((await chamarMcp(outro.token, "tools/list")).status).toBe(200);

  // ---- revogar: corta só o Caçador, que continua na lista como "Revogado" ----
  await linhaCliente(page, cacador).getByRole("button", { name: "Revogar" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Revogar" }).click();
  await expect(linhaCliente(page, cacador).getByText("Revogado", { exact: true })).toBeVisible();
  await expect(linhaCliente(page, cacador)).toContainText(OWNER.name);
  await expect(linhaCliente(page, cacador).getByRole("button", { name: "Rotacionar" })).toHaveCount(0);
  const revogado = await chamarMcp(token2, "tools/list");
  expect(revogado.status, "token revogado").toBe(401);
  expect(revogado.headers.get("www-authenticate") ?? "").toMatch(/^Bearer/);
  expect((await chamarMcp(outro.token, "tools/list")).status, "o outro cliente segue").toBe(200);

  // histórico do cliente: criação, rotação e revogação, sem credencial
  await linhaCliente(page, cacador).getByRole("button", { name: "Histórico" }).click();
  const hist = page.getByRole("dialog", { name: `Histórico de ${cacador}` });
  await expect(hist.getByText("Criado", { exact: true })).toBeVisible();
  await expect(hist.getByText("Arquivado", { exact: true })).toBeVisible();
  await expect(hist).not.toContainText(SMCP);
  await page.keyboard.press("Escape");
  await logout(page);

  // ---- membro: sem o menu, a tela recusa e a API responde somente_humano ----
  const member = await createVerifiedMember(page);
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
  await expect(navLink(page, "Agentes (MCP)")).toHaveCount(0);
  await expect(navLink(page, "Propostas dos agentes")).toBeVisible();
  await page.goto("/app/configuracoes/agentes");
  await expect(page.getByText("Esta área é só para o dono.")).toBeVisible();
  const memberToken = await apiToken(request, member.email, member.final);
  for (const [metodo, url] of [
    ["GET", "/api/mcp/clientes"],
    ["POST", "/api/mcp/clientes"],
    ["PUT", "/api/mcp/config"],
  ] as const) {
    const res = await request.fetch(url, {
      method: metodo,
      headers: { Authorization: `Bearer ${memberToken}` },
      data: metodo === "GET" ? undefined : { nome: "x", escopo: "leitura", habilitado: true, version: 1 },
    });
    expect(res.status(), `${metodo} ${url} pelo membro`).toBe(403);
  }
  // um cliente MCP também não mexe em clientes MCP
  const pelaCredencial = await apiDireta(outro.token, "GET", "/api/mcp/clientes");
  expect(pelaCredencial.status).toBe(403);
  expect(pelaCredencial.body?.error?.code).toBe("somente_humano");
});

test("US2/US3: o agente lê pelo /mcp o mesmo que a tela; Origin e PROIBIDAS são recusados", async ({ page, request }) => {
  test.setTimeout(180_000);
  const sfx = randomUUID().slice(0, 6);
  const donoToken = await apiToken(request, OWNER.email, OWNER.password);
  await interruptorMcp(request, donoToken, true);
  const perfilNome = `Perfil MCP ${sfx}`;
  await createPerfilViaApi(request, donoToken, { name: perfilNome, slug: `perfil-mcp-${sfx}` });
  const leitor = await criarClienteMcp(request, donoToken, `Leitor ${sfx}`, "leitura");

  // perfis_list bate com a tela de perfis: a mesma consulta que a tela faz (`archived=false`) devolve
  // os mesmos perfis, na mesma ordem, e o perfil deste teste aparece na tabela (pela busca).
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  const daTela = page.waitForResponse((res) => new URL(res.url()).pathname === "/api/perfis" && res.request().method() === "GET");
  await nav(page, "Perfis");
  const telaRes = await daTela;
  expect(new URL(telaRes.url()).searchParams.get("archived")).toBe("false");
  const tela = (await telaRes.json()) as { items: { id: string; name: string }[] };

  const r = await chamarTool(leitor.token, "perfis_list", { archived: false });
  expect(r.status).toBe(200);
  const result = r.body?.result as { isError?: boolean; structuredContent: { items: { id: string; name: string }[] } };
  expect(result.isError ?? false).toBe(false);
  const doMcp = result.structuredContent.items;
  expect(doMcp.map((p) => p.id)).toEqual(tela.items.map((p) => p.id));
  expect(doMcp).toEqual(tela.items);
  expect(doMcp.map((p) => p.name)).toContain(perfilNome);
  await page.getByLabel("Buscar").fill(perfilNome);
  await expect(page.getByRole("table", { name: "Perfis" }).getByText(perfilNome, { exact: true })).toBeVisible();

  // Origin de navegador → 403 antes de autenticar
  const origem = await chamarMcp(leitor.token, "tools/list", {}, { headers: { Origin: "https://evil.example" } });
  expect(origem.status, "Origin de navegador").toBe(403);

  // sem credencial → 401 com WWW-Authenticate
  const anon = await chamarMcp("", "tools/list", {}, { semToken: true });
  expect(anon.status).toBe(401);
  expect(anon.headers.get("www-authenticate") ?? "").toMatch(/^Bearer/);

  // PROIBIDA pelo /mcp: a tool não existe; direto na API: somente_humano
  const proibida = await chamarTool(leitor.token, "destinos_aprovar", { destino_id: randomUUID(), version: 1 });
  expect(proibida.body?.error?.code, "tool proibida pelo /mcp").toBe(-32602);
  const direta = await apiDireta(leitor.token, "POST", `/api/destinos/${randomUUID()}/aprovar`, { version: 1 });
  expect(direta.status).toBe(403);
  expect(direta.body?.error?.code).toBe("somente_humano");

  // escrita com escopo "leitura": escopo insuficiente
  const escrita = await chamarTool(leitor.token, "anotacoes_create", { alvoTipo: "perfil", alvoId: randomUUID(), tipo: "observacao", texto: "oi" });
  const er = escrita.body?.result as { isError?: boolean; structuredContent?: { code?: string } } | undefined;
  expect(er?.isError, "escrita por cliente leitura").toBe(true);
  expect(er?.structuredContent?.code).toBe("escopo_mcp");
});

test("US5: o registro filtra por cliente e mostra o limite; nenhuma credencial na página", async ({ page, request }) => {
  test.setTimeout(180_000);
  const sfx = randomUUID().slice(0, 6);
  const donoToken = await apiToken(request, OWNER.email, OWNER.password);
  await interruptorMcp(request, donoToken, true);
  const a = await criarClienteMcp(request, donoToken, `Registro A ${sfx}`, "leitura");
  const b = await criarClienteMcp(request, donoToken, `Rajada B ${sfx}`, "leitura", { limitePorMinuto: 3 });

  expect((await chamarTool(a.token, "perfis_list")).status).toBe(200);
  expect((await chamarTool(a.token, "destinos_aprovar", { destino_id: randomUUID(), version: 1 })).status).toBe(200);
  // rajada acima de 3 por minuto
  const statusB: number[] = [];
  for (let i = 0; i < 6; i++) {
    const res = await chamarTool(b.token, "perfis_list");
    const sc = (res.body?.result as { structuredContent?: { code?: string } } | undefined)?.structuredContent;
    statusB.push(res.status === 429 || sc?.code === "mcp_limite" ? 429 : res.status);
  }
  expect(statusB).toContain(429);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/configuracoes/agentes");
  await expect(linhaCliente(page, b.nome).getByText("no limite")).toBeVisible();

  await page.getByRole("tab", { name: "Registro" }).click();
  await expect(page).toHaveURL(/aba=registro/);
  const registro = page.getByRole("tabpanel", { name: "Registro" });
  const tabela = registro.getByRole("table", { name: "Registro de chamadas MCP" });
  // spec 024: os filtros valem ao escolher (sem "Filtrar") e ficam na URL com o prefixo reg_
  await registro.getByLabel("Cliente", { exact: true }).selectOption({ label: a.nome });
  await expect(page).toHaveURL(/reg_cliente=/);
  await expect(tabela.getByRole("row").filter({ hasText: "perfis_list" }).first()).toBeVisible();
  await expect(tabela.getByRole("row").filter({ hasText: b.nome })).toHaveCount(0);
  await expect(tabela.getByRole("row").filter({ hasText: a.nome }).first()).toBeVisible();

  await registro.getByLabel("Cliente", { exact: true }).selectOption({ label: b.nome });
  await registro.getByLabel("Resultado", { exact: true }).selectOption({ label: "limite" });
  await expect(page).toHaveURL(/reg_resultado=/);
  await expect(registro.getByRole("button", { name: "Remover filtro: Resultado" })).toBeVisible();
  await expect(tabela.getByRole("row").filter({ hasText: "limite" }).first()).toBeVisible();
  await expect(tabela.getByRole("row").filter({ hasText: a.nome })).toHaveCount(0);

  await expect(page.locator("body")).not.toContainText(SMCP);
  expect(await page.content()).not.toMatch(SMCP);
});
