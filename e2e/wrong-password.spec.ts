import { expect, test } from "@playwright/test";
import { createVerifiedUser, loginViaUi, uniqueEmail } from "./helpers";

test("login com senha errada mostra erro genérico e não abre sessão", async ({ page }) => {
  const email = uniqueEmail("senha-errada");
  await createVerifiedUser(email);

  await loginViaUi(page, email, "senha-completamente-errada");

  await expect(page.getByRole("alert")).toHaveText("E-mail ou senha incorretos");
  await expect(page).toHaveURL(/\/login$/);

  // mesmo erro para e-mail inexistente — sem enumeração de usuário
  await loginViaUi(page, uniqueEmail("nao-existe"), "senha-completamente-errada");
  await expect(page.getByRole("alert")).toHaveText("E-mail ou senha incorretos");
});
