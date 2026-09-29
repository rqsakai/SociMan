import { expect, request, test } from "@playwright/test";
import { BASE_URL, OWNER } from "./fixtures";
import { login } from "./helpers";

// Reuso de refresh token revoga a família inteira.
test("reuso de refresh token revoga a família e derruba a sessão", async ({ page }) => {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  // captura o cookie de renovação atual ("roubado" pelo atacante)
  const cookies = await page.context().cookies(`${BASE_URL}/api/auth/refresh`);
  const stolen = cookies.find((c) => c.name === "sociman_rt");
  expect(stolen).toBeDefined();
  expect(stolen!.path).toBe("/api/auth/refresh");

  // duas renovações legítimas pelo jar do navegador: o cookie roubado fica
  // duas gerações para trás, fora da janela de graça da rotação
  const rotate1 = await page.request.post("/api/auth/refresh");
  expect(rotate1.ok()).toBeTruthy();
  const rotate2 = await page.request.post("/api/auth/refresh");
  expect(rotate2.ok()).toBeTruthy();

  // o atacante apresenta o cookie roubado → reuso detectado, família revogada
  const attacker = await request.newContext({ baseURL: BASE_URL });
  const reuse = await attacker.post("/api/auth/refresh", {
    headers: { cookie: `sociman_rt=${stolen!.value}` },
  });
  expect(reuse.status()).toBe(401);
  await attacker.dispose();

  // até o cookie legítimo mais novo morreu: o reload não restaura a sessão
  await page.reload();
  await expect(page).toHaveURL(/\/login$/);
});
