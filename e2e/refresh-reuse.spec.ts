import { expect, request, test } from "@playwright/test";
import { PASSWORD, createVerifiedUser, loginViaUi, uniqueEmail } from "./helpers";

// §11: "reuso de refresh revoga a família (teste automatizado)".
test("reuso de refresh token revoga a família e derruba a sessão", async ({ page }) => {
  const email = uniqueEmail("reuso");
  await createVerifiedUser(email);

  await loginViaUi(page, email, PASSWORD);
  await expect(page).toHaveURL(/\/app$/);

  // captura o cookie de refresh atual do navegador ("roubado" pelo atacante)
  const cookies = await page.context().cookies("http://localhost:5173/api/auth/refresh");
  const stolenCookie = cookies.find((c) => c.name === "sociman_rt");
  expect(stolenCookie).toBeDefined();

  // dois refreshes legítimos pelo jar do navegador → o cookie roubado fica
  // duas gerações para trás, fora da janela de graça de rotação
  const rotate1 = await page.context().request.post("/api/auth/refresh");
  expect(rotate1.ok()).toBeTruthy();
  const rotate2 = await page.context().request.post("/api/auth/refresh");
  expect(rotate2.ok()).toBeTruthy();

  // o atacante apresenta o cookie roubado → reuso detectado, família revogada
  const attacker = await request.newContext({ baseURL: "http://localhost:5173" });
  const reuse = await attacker.post("/api/auth/refresh", {
    headers: { cookie: `sociman_rt=${stolenCookie!.value}` },
  });
  expect(reuse.status()).toBe(401);
  await attacker.dispose();

  // a família inteira morreu: até o cookie "legítimo" rotacionado falha,
  // então o reload não consegue restaurar a sessão e cai no login
  await page.reload();
  await expect(page).toHaveURL(/\/login$/);
});
