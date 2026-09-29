import { expect, test } from "@playwright/test";
import { OWNER } from "./fixtures";
import {
  changeProvisionalPassword,
  clearInbox,
  createMember,
  extractLink,
  login,
  logout,
  newMember,
  waitForEmail,
} from "./helpers";

// US2: o dono cria um membro → e-mail de verificação → login antes de
// verificar é recusado → reenvio → verifica pelo link novo → entra com a
// senha provisória → é forçado a trocar → usa o app → /app/usuarios nega.
test("dono cria membro, que verifica, troca a senha provisória e não gerencia usuários", async ({ page }) => {
  const member = newMember();

  // dono cria o membro
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("link", { name: "Segurança" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Minha conta" })).toBeVisible();
  await createMember(page, member);

  // e-mail de verificação chega
  const first = await waitForEmail(member.email, "Confirme seu e-mail");
  extractLink(first, "/verify-email");

  await logout(page);

  // login antes de verificar é recusado, com opção de reenviar
  await login(page, member.email, member.provisional);
  await expect(page.getByText("Confirme seu e-mail antes de entrar")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);

  // limpa a caixa para que o próximo e-mail seja, sem ambiguidade, o do reenvio
  await clearInbox();
  await page.getByRole("button", { name: "Reenviar link" }).click();
  await expect(page.getByText("Se o e-mail estiver cadastrado, enviamos um novo link")).toBeVisible();

  const resent = await waitForEmail(member.email, "Confirme seu e-mail");
  expect(resent.ID).not.toBe(first.ID);
  await page.goto(extractLink(resent, "/verify-email"));
  await expect(page.getByText("E-mail confirmado, faça login")).toBeVisible();

  // primeiro login com a senha provisória força a troca
  await login(page, member.email, member.provisional);
  await expect(page).toHaveURL(/\/trocar-senha$/);

  // /app não é acessível enquanto a troca estiver pendente
  await page.goto("/app");
  await expect(page).toHaveURL(/\/trocar-senha$/);

  await changeProvisionalPassword(page, member);

  // usa o app normalmente, mas não gerencia usuários
  await page.reload();
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/usuarios");
  await expect(page.getByText("Sem permissão")).toBeVisible();

  // a senha nova vale no próximo login
  await page.goto("/app");
  await logout(page);
  await login(page, member.email, member.final);
  await expect(page).toHaveURL(/\/app$/);
});
