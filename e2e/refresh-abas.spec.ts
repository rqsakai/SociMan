import { expect, type Page, request, test } from "@playwright/test";
import { BASE_URL, OWNER } from "./fixtures";
import { login, sqlE2e } from "./helpers";

// Duas abas (ou aba + PWA) do mesmo navegador dividem o cookie de renovação, que gira a cada uso.
// Renovarem juntas não pode derrubar a sessão: o cliente coordena pelo Web Lock + BroadcastChannel,
// e o servidor tolera o token imediatamente anterior por 10 s (`refresh_concorrente`).

// Access token "expirado": a 1ª requisição autenticada da aba toma 401, como o servidor faz quando
// o JWT vence. O authFetch então renova pelo cookie e repete a requisição.
async function expirarAccessUmaVez(page: Page): Promise<void> {
  let expirou = false;
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    if (!expirou && req.headers()["authorization"] && !req.url().includes("/api/auth/")) {
      expirou = true;
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "invalid_token", message: "Token expirado" } }),
      });
      return;
    }
    await route.continue();
  });
}

function eventos(tipo: string, desde: string): number {
  const [n] = sqlE2e(`select count(*) from security_events where type = '${tipo}' and occurred_at >= '${desde}'`);
  return Number(n);
}

test("duas abas renovando ao mesmo tempo não derrubam a sessão", async ({ page, context }) => {
  const desde = new Date().toISOString();
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  const outra = await context.newPage();
  await outra.goto("/app");
  await expect(outra).toHaveURL(/\/app$/);

  const renovacoes: number[] = [];
  context.on("response", (res) => {
    if (res.url().includes("/api/auth/refresh")) renovacoes.push(res.status());
  });

  // As duas abas recarregam juntas (renovação do boot) e, logo depois, a 1ª chamada autenticada
  // de cada uma toma 401 (renovação pelo interceptor): duas rodadas de renovação simultânea.
  await expirarAccessUmaVez(page);
  await expirarAccessUmaVez(outra);
  await Promise.all([page.reload(), outra.reload()]);
  for (const aba of [page, outra]) {
    await expect(aba).toHaveURL(/\/app$/);
    await expect(aba.getByRole("button", { name: "Sair" })).toBeVisible();
  }
  await expect.poll(() => renovacoes.length).toBeGreaterThanOrEqual(2);
  expect(renovacoes.every((s) => s === 200), `renovações: ${renovacoes.join(",")}`).toBe(true);

  // Sem o lock (ex.: navegador sem Web Locks), o servidor ainda tolera: duas renovações com o
  // MESMO cookie, em paralelo, respondem 200 com o mesmo token novo e não revogam nada. O
  // navegador fica com o cookie anterior e o apresenta no reload abaixo, ainda dentro dos 10 s.
  const [rt] = (await context.cookies(`${BASE_URL}/api/auth/refresh`)).filter((c) => c.name === "sociman_rt");
  expect(rt).toBeDefined();
  const cliente = await request.newContext({ baseURL: BASE_URL });
  const headers = { cookie: `sociman_rt=${rt.value}` };
  const [a, b] = await Promise.all([
    cliente.post("/api/auth/refresh", { headers }),
    cliente.post("/api/auth/refresh", { headers }),
  ]);
  expect(a.status()).toBe(200);
  expect(b.status()).toBe(200);
  await cliente.dispose();

  // ninguém foi deslogado: o cookie que ficou no navegador ainda restaura as duas abas
  await page.unrouteAll();
  await outra.unrouteAll();
  await Promise.all([page.reload(), outra.reload()]);
  for (const aba of [page, outra]) {
    await expect(aba).toHaveURL(/\/app$/);
    await expect(aba.getByRole("button", { name: "Sair" })).toBeVisible();
  }

  expect(eventos("refresh_reuse_detected", desde)).toBe(0);
  expect(eventos("refresh_concorrente", desde)).toBeGreaterThanOrEqual(1);
});
