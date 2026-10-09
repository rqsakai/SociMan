import { expect, test } from "@playwright/test";
import { OWNER } from "../e2e/fixtures";
import { login } from "../e2e/helpers";

// SC-004 (spec 005): no modo casa (build de produção sob a CSP da constitution 2.0.0), navegar por
// todas as telas — inclusive abrindo gaveta, diálogo e toast, que injetam <style> — sem nenhuma
// violação de CSP no console.
test("nenhuma violação de CSP ao navegar pelo painel no build de produção", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (msg) => {
    const text = msg.text();
    if (/Content Security Policy|Refused to (apply|load|execute|connect)/i.test(text)) violations.push(text);
  });

  const header = (await page.request.get("/")).headers()["content-security-policy"] ?? "";
  expect(header).toContain("script-src 'self';");
  expect(header).toContain("style-src 'self' 'unsafe-inline'");

  await page.goto("/login");
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  for (const path of ["/app", "/app/perfis", "/app/perfis/novo", "/app/usuarios", "/app/seguranca", "/app/conta"]) {
    await page.goto(path);
    await expect(page.locator("h1").first()).toBeAttached();
    await page.waitForLoadState("networkidle");
  }

  // componentes que injetam <style>: gaveta (Sheet) em tela estreita e menu da conta
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/perfis");
  await page.getByRole("button", { name: "Abrir menu" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");

  expect(violations, violations.join("\n")).toEqual([]);
});
