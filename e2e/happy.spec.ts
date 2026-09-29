import { expect, test } from "@playwright/test";
import {
  PASSWORD,
  loginViaUi,
  tokenFromLink,
  uniqueEmail,
  waitForEmailLink,
} from "./helpers";

// Jornada completa do DoD (§11): cadastro → consentimento → verificação →
// login → rota protegida → sessão sobrevive ao reload (refresh) → logout →
// esqueci a senha → redefinir → login com a senha nova.
test("fluxo feliz ponta a ponta", async ({ page }) => {
  const email = uniqueEmail("feliz");

  // --- cadastro (com banner LGPD na primeira visita) ---
  await page.goto("/register");
  const consentResponse = page.waitForResponse(
    (res) => res.url().includes("/api/consent") && res.status() === 200,
  );
  await expect(page.getByText("um único cookie", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Só o essencial" }).click();
  await consentResponse; // consentimento gravado no backend
  await expect(page.getByRole("region", { name: "Preferências de privacidade" })).toBeHidden();

  await page.getByLabel("Nome (opcional)").fill("Ana E2E");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Criar conta" }).click();

  // sessão aberta, mas e-mail ainda não verificado
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText("Confirme seu e-mail", { exact: false })).toBeVisible();

  // --- verificação de e-mail (link capturado do outbox de dev) ---
  const verifyLink = await waitForEmailLink("verification", email);
  await page.goto(`/verify-email?token=${tokenFromLink(verifyLink)}`);
  await expect(page.getByText("E-mail confirmado", { exact: false })).toBeVisible();

  // --- logout e login "de verdade" ---
  await page.goto("/app");
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await loginViaUi(page, email, PASSWORD);
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText(email)).toBeVisible();

  // --- reload: access token (memória) morre, refresh cookie restaura ---
  await page.reload();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText(email)).toBeVisible();

  // --- logout ---
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // --- esqueci a senha → redefinir → login com a nova ---
  await page.goto("/forgot-password");
  await page.getByLabel("E-mail").fill(email);
  await page.getByRole("button", { name: "Enviar link de recuperação" }).click();
  await expect(page.getByText("enviamos um link", { exact: false })).toBeVisible();

  const resetLink = await waitForEmailLink("reset", email);
  await page.goto(`/reset-password?token=${tokenFromLink(resetLink)}`);
  const newPassword = "nova-senha-456";
  await page.getByLabel("Nova senha").fill(newPassword);
  await page.getByRole("button", { name: "Redefinir senha" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText("Senha redefinida", { exact: false })).toBeVisible();

  await loginViaUi(page, email, newPassword);
  await expect(page).toHaveURL(/\/app$/);
});
