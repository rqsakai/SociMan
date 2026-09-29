import { expect, test } from "@playwright/test";
import {
  createVerifiedUser,
  dismissConsentIfVisible,
  insertExpiredResetToken,
  uniqueEmail,
} from "./helpers";

test("token de reset expirado é rejeitado com mensagem clara", async ({ page }) => {
  const email = uniqueEmail("expirado");
  await createVerifiedUser(email);
  const expiredToken = await insertExpiredResetToken(email);

  await page.goto(`/reset-password?token=${expiredToken}`);
  await dismissConsentIfVisible(page);
  await page.getByLabel("Nova senha").fill("nova-senha-456");
  await page.getByRole("button", { name: "Redefinir senha" }).click();

  await expect(page.getByRole("alert")).toContainText("inválido ou expirado");
  await expect(page).toHaveURL(/\/reset-password/);
});
