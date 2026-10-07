import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, compose, createPerfilViaApi, login, sqlE2e } from "./helpers";

// Spec 021 (T030, T039, T045): geração local com candidatos, com o ComfyUI, o shop-tts e o
// dockerctl falsos (`e2e/fakes/geracao_fake.py`, no `openshorts-fake`) e o serviço `gerador`.
// - US1: no cenário, pedir uma cena, ver o andamento, ver as 2 opções e usar a 2; o arquivo entra
//   no cenário e a versão do cenário aponta a geração;
// - US2: com a GPU ocupada, a tela mostra "Aguardando a GPU ficar livre"; ao liberar, a geração
//   roda, e a RAM do ComfyUI vai a 28 GB durante o job e volta a 12 GB;
// - US3: cancelar na fila; "Gerar outras" deixa a antiga descartada e a nova em revisão.

const GiB = 1024 ** 3;
type Auth = { Authorization: string };

// Rotas de controle do fake, de dentro do container (o openshorts-fake não é publicado no host).
function geracaoFake(metodo: "GET" | "POST", caminho: string, corpo?: unknown): unknown {
  const script = [
    "import json, sys, urllib.request",
    "corpo = sys.stdin.read().encode() or None",
    `req = urllib.request.Request("http://localhost:8000${caminho}", data=corpo, method="${metodo}",`,
    "                             headers={'content-type': 'application/json'})",
    "print(urllib.request.urlopen(req, timeout=5).read().decode())",
  ].join("\n");
  return JSON.parse(compose(["exec", "-T", "openshorts-fake", "python", "-c", script], corpo === undefined ? "" : JSON.stringify(corpo)));
}

const gpuOcupada = (ocupada: boolean) => geracaoFake("POST", "/geracao-e2e/gpu", { ocupada });
const lento = (segundos: number) => geracaoFake("POST", "/geracao-e2e/lento", { segundos });
const memoria = () => geracaoFake("GET", "/geracao-e2e/memoria") as { historico: number[]; memoria_bytes: number };

// A fila espera 30 s depois de "Aguardando a GPU ficar livre"; o teste não precisa esperar.
const semEspera = () => sqlE2e("update geracoes set next_attempt_at = null where status = 'na_fila'");

async function cenario(request: APIRequestContext, sfx: string): Promise<{ auth: Auth; perfilId: string; cenarioId: string }> {
  const token = await apiToken(request, OWNER.email, OWNER.password);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Geração ${sfx}`, slug: `geracao-${sfx}` });
  const r = await request.post(`/api/perfis/${perfilId}/assets`, {
    headers: auth,
    data: { tipo: "cenario", name: "Quarto claro", tags: [], prompt: "bright bedroom" },
  });
  expect(r.status(), `cenário: ${await r.text()}`).toBe(201);
  const cenarioId = ((await r.json()) as { asset: { id: string } }).asset.id;
  return { auth, perfilId, cenarioId };
}

async function abrir(page: Page, cenarioId: string): Promise<void> {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/assets/${cenarioId}`);
  await expect(page.getByRole("heading", { name: "Gerar cena" })).toBeVisible();
}

async function pedirPelaTela(page: Page, instrucao: string): Promise<void> {
  const form = page.getByTestId("pedir-geracao");
  await form.getByLabel("Instrução").fill(instrucao);
  await form.getByRole("button", { name: "Gerar" }).click();
}

async function confirmar(page: Page, botao: string, escopo = page.locator("body")): Promise<void> {
  await escopo.getByRole("button", { name: botao }).click();
  const dialogo = page.getByRole("alertdialog");
  await expect(dialogo).toBeVisible();
  await dialogo.getByRole("button", { name: botao }).click();
  await expect(dialogo).toBeHidden();
}

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  gpuOcupada(false);
  lento(2);
});

test("US1: pede a cena, vê o andamento e usa a opção 2", async ({ page, request }) => {
  const { auth, cenarioId } = await cenario(request, `us1-${Date.now()}`);
  lento(4);
  await abrir(page, cenarioId);
  await pedirPelaTela(page, "cozy bright bedroom, morning sun");
  const item = page.getByTestId("geracao-item").first();
  await expect(item.getByTestId("andamento-geracao")).toContainText(/Gerando opção [12] de 2|Começando|Esperando a vez/, { timeout: 30_000 });
  await expect(item.getByTestId("estado-geracao")).toHaveText("Em revisão", { timeout: 60_000 });
  await expect(item.getByTestId("opcao-1")).toBeVisible();
  const op2 = item.getByTestId("opcao-2");
  await expect(op2.getByRole("img")).toBeVisible();
  await confirmar(page, "Usar opção 2", op2);
  await expect(item.getByTestId("estado-geracao")).toHaveText("Escolhida", { timeout: 15_000 });

  const geracaoId = await item.getAttribute("data-geracao-id");
  const det = await request.get(`/api/assets/${cenarioId}`, { headers: auth });
  const asset = ((await det.json()) as { asset: { files: { notes: string; role: string }[] } }).asset;
  expect(asset.files.some((f) => f.role === "referencia" && f.notes === "Gerado (opção 2)")).toBe(true);
  const versoes = await request.get(`/api/assets/${cenarioId}/versions`, { headers: auth });
  const itens = ((await versoes.json()) as { items: { details: Record<string, unknown> }[] }).items;
  expect(itens[0].details.geracao_id).toBe(geracaoId);
});

test("US2: espera a GPU livre e a RAM do ComfyUI vai a 28 GB e volta a 12 GB", async ({ page, request }) => {
  const { cenarioId } = await cenario(request, `us2-${Date.now()}`);
  const antes = memoria().historico.length;
  gpuOcupada(true);
  await abrir(page, cenarioId);
  await pedirPelaTela(page, "minimal living room, soft light");
  const item = page.getByTestId("geracao-item").first();
  await expect(item.getByTestId("andamento-geracao")).toContainText("Aguardando a GPU ficar livre", { timeout: 30_000 });
  await expect(item.getByTestId("estado-geracao")).toHaveText("Na fila");
  gpuOcupada(false);
  semEspera();
  await expect(item.getByTestId("estado-geracao")).toHaveText("Em revisão", { timeout: 60_000 });
  const m = memoria();
  const desteJob = m.historico.slice(antes);
  expect(desteJob).toContain(28 * GiB);
  expect(desteJob.at(-1)).toBe(12 * GiB);
  expect(m.memoria_bytes).toBe(12 * GiB);
});

test("US3: cancela na fila e gera outras", async ({ page, request }) => {
  const { cenarioId } = await cenario(request, `us3-${Date.now()}`);
  gpuOcupada(true);
  await abrir(page, cenarioId);
  await pedirPelaTela(page, "kitchen at night");
  const primeira = page.getByTestId("geracao-item").first();
  await expect(primeira.getByTestId("estado-geracao")).toHaveText("Na fila");
  await confirmar(page, "Cancelar geração", primeira);
  await expect(primeira.getByTestId("estado-geracao")).toHaveText("Cancelada", { timeout: 15_000 });

  gpuOcupada(false);
  await pedirPelaTela(page, "garden in the morning");
  const aberta = page.locator('[data-testid="geracao-item"][data-status="revisao"]');
  await expect(aberta).toHaveCount(1, { timeout: 60_000 });
  const antigaId = await aberta.getAttribute("data-geracao-id");
  await confirmar(page, "Gerar outras", aberta);
  const antiga = page.locator(`[data-testid="geracao-item"][data-geracao-id="${antigaId}"]`);
  await expect(antiga.getByTestId("estado-geracao")).toHaveText("Descartada", { timeout: 15_000 });
  const nova = page.locator(`[data-testid="geracao-item"]:not([data-geracao-id="${antigaId}"])[data-status="revisao"]`);
  await expect(nova).toHaveCount(1, { timeout: 60_000 });
  const seeds = sqlE2e(
    `select string_agg(c.seed::text, ',' order by c.seed) from geracao_candidatos c join geracoes g on g.id = c.geracao_id ` +
      `where g.id = '${antigaId}' or g.de_geracao_id = '${antigaId}' group by g.id`,
  );
  expect(seeds).toHaveLength(2);
  expect(new Set(seeds[0].split(",")).size + new Set(seeds[1].split(",")).size).toBe(
    new Set([...seeds[0].split(","), ...seeds[1].split(",")]).size,
  );
});
