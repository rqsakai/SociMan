import { expect, test } from "@playwright/test";
import { OWNER } from "./fixtures";
import { login, uniqueEmail } from "./helpers";

test("senha errada e e-mail inexistente mostram a mesma mensagem e não abrem sessão", async ({ page }) => {
  await login(page, OWNER.email, "Senha-completamente-errada");
  await expect(page.getByRole("alert")).toHaveText("E-mail ou senha incorretos");
  await expect(page).toHaveURL(/\/login$/);

  // mesma resposta para e-mail inexistente — sem enumeração de usuário
  await login(page, uniqueEmail("nao-existe"), "Senha-completamente-errada");
  await expect(page.getByRole("alert")).toHaveText("E-mail ou senha incorretos");
  await expect(page).toHaveURL(/\/login$/);

  const cookies = await page.context().cookies();
  expect(cookies.find((c) => c.name === "sociman_rt")).toBeUndefined();
});
