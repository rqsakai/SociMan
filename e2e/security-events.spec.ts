import { expect, test } from "@playwright/test";
import { OWNER } from "./fixtures";
import { createVerifiedMember, login, nav } from "./helpers";

// US3: depois do fluxo do membro, o dono filtra os eventos de segurança pelo
// membro e vê a criação, a verificação do e-mail e a troca de senha.
test("dono filtra os eventos de segurança pelo membro", async ({ page }) => {
  const member = await createVerifiedMember(page);

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await nav(page, "Segurança");
  await expect(page).toHaveURL(/\/app\/seguranca$/);
  await expect(page.getByRole("heading", { name: "Eventos de segurança" })).toBeVisible();

  // spec 024: o filtro vale ao escolher (sem "Filtrar"), vira etiqueta e fica na URL
  await page.getByLabel("Usuário", { exact: true }).selectOption({ label: member.name });
  await expect(page).toHaveURL(/usuario=/);
  await expect(page.getByRole("button", { name: "Remover filtro: Usuário" })).toBeVisible();

  for (const label of ["Usuário criado", "E-mail verificado", "Senha trocada"]) {
    await expect(page.getByRole("cell", { name: label }).first()).toBeVisible();
  }
});
