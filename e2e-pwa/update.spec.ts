import { expect, test } from "@playwright/test";
import { OWNER } from "../e2e/fixtures";
import { login } from "../e2e/helpers";
import { buildWeb, waitForActiveSW } from "./helpers";

// US3: um build novo no dist montado vira "Nova versão disponível"; "Atualizar"
// troca a versão sem derrubar a sessão. O afterAll devolve o build normal,
// mesmo se o teste falhar.

test.afterAll(() => {
  buildWeb();
});

test("versão nova aparece no aviso e Atualizar mantém a sessão", async ({ page }) => {
  test.setTimeout(240_000); // inclui um build de produção (tsc + vite)

  await page.goto("/login");
  await waitForActiveSW(page);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  const html = page.locator("html");
  const oldBuild = await html.getAttribute("data-build");
  const newBuild = `e2e-${Date.now()}`;
  expect(newBuild).not.toBe(oldBuild);

  buildWeb(newBuild);
  await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.getRegistration("/");
    if (!reg) throw new Error("sem registro de service worker");
    await reg.update();
  });

  const prompt = page.getByRole("status").filter({ hasText: "Nova versão disponível" });
  await expect(prompt).toBeVisible({ timeout: 30_000 });
  await prompt.getByRole("button", { name: "Atualizar" }).click();

  await expect(html).toHaveAttribute("data-build", newBuild, { timeout: 15_000 });
  await expect(page).toHaveURL(/\/app$/);
});
