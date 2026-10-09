import { expect, test } from "@playwright/test";
import { createVerifiedMember, extractLink, login, logout, waitForEmail } from "./helpers";

// US4: esqueci a senha → link no Mailpit → nova senha → a nova entra e a
// antiga é recusada.
test("membro recupera o acesso pelo link do e-mail", async ({ page }) => {
  const member = await createVerifiedMember(page);
  const reset = "Recuperada-e2e-Membro-2026";

  await page.goto("/login");
  await page.getByRole("link", { name: "Esqueci a senha" }).click();
  await expect(page).toHaveURL(/\/forgot-password$/);
  // a URL muda antes de o React trocar a tela: espere a página nova antes de preencher
  await expect(page.getByRole("heading", { name: "Recuperar senha" })).toBeVisible();
  await page.getByLabel("E-mail").fill(member.email);
  await page.getByRole("button", { name: "Enviar link de recuperação" }).click();
  await expect(page.getByText("Se existir uma conta com esse e-mail")).toBeVisible();

  const mail = await waitForEmail(member.email, "Redefinir");
  await page.goto(extractLink(mail, "/reset-password"));
  await page.getByLabel("Nova senha", { exact: true }).fill(reset);
  await page.getByLabel("Confirmar nova senha").fill(reset);
  await page.getByRole("button", { name: "Redefinir senha" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText("Senha redefinida")).toBeVisible();

  await login(page, member.email, reset);
  await expect(page).toHaveURL(/\/app$/);
  await logout(page);

  await login(page, member.email, member.final);
  await expect(page.getByRole("alert")).toHaveText("E-mail ou senha incorretos");
  await expect(page).toHaveURL(/\/login$/);
});
