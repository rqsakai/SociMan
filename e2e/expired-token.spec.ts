import { expect, test } from "@playwright/test";
import { createVerifiedMember, expireResetTokens, extractLink, waitForEmail } from "./helpers";

// US4: o link de recuperação vencido é recusado com mensagem clara e oferta
// de pedir outro.
test("link de recuperação expirado é rejeitado com mensagem clara", async ({ page }) => {
  const member = await createVerifiedMember(page);

  await page.goto("/forgot-password");
  await page.getByLabel("E-mail").fill(member.email);
  await page.getByRole("button", { name: "Enviar link de recuperação" }).click();
  await expect(page.getByText("Se existir uma conta com esse e-mail")).toBeVisible();

  const mail = await waitForEmail(member.email, "Redefinir");
  expireResetTokens();
  await page.goto(extractLink(mail, "/reset-password"));

  // a SPA pode recusar o token ao abrir ou só ao enviar a nova senha
  const invalid = page.getByText("inválido ou expirado");
  const newPassword = page.getByLabel("Nova senha", { exact: true });
  await expect(invalid.or(newPassword)).toBeVisible();
  if (await newPassword.isVisible()) {
    await newPassword.fill("Nunca-aplicada-e2e-2026");
    await page.getByLabel("Confirmar nova senha").fill("Nunca-aplicada-e2e-2026");
    await page.getByRole("button", { name: "Redefinir senha" }).click();
  }

  await expect(invalid).toBeVisible();
  await expect(page.getByRole("link", { name: "Pedir novo link" })).toBeVisible();
  await expect(page).toHaveURL(/\/reset-password/);
});
