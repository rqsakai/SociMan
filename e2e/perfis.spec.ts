import { randomUUID } from "node:crypto";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { login, pngBuffer } from "./helpers";

// Aba do detalhe do perfil (role "tab"; aceita botão ou link como alternativa).
function tab(page: Page, name: string): Locator {
  return page
    .getByRole("tab", { name, exact: true })
    .or(page.getByRole("button", { name, exact: true }))
    .or(page.getByRole("link", { name, exact: true }));
}

// Ações destrutivas podem pedir confirmação num modal (role "dialog"); o
// `window.confirm` é aceito pelo handler registrado no início do teste.
async function confirmIfAsked(page: Page, confirmLabel: string): Promise<void> {
  const button = page.getByRole("dialog").getByRole("button", { name: confirmLabel });
  try {
    await button.waitFor({ state: "visible", timeout: 2_000 });
  } catch {
    return;
  }
  await button.click();
}

// Com o perfil aberto na aba Contas: adiciona uma conta TikTok com status Ativa.
async function addTikTok(page: Page, value: string): Promise<void> {
  const field = page.getByLabel("@ ou link");
  if (!(await field.isVisible())) await page.getByRole("button", { name: "Adicionar conta" }).click();
  await page.getByLabel("Plataforma").selectOption({ label: "TikTok" });
  await field.fill(value);
  await page.getByLabel("Status").selectOption({ label: "Ativa" });
  await page.getByRole("button", { name: "Adicionar conta" }).click();
}

// Versão do histórico: um <li> (com a tabela interna Campo | Antes | Depois).
function historyEntries(page: Page): Locator {
  return page.locator("li");
}

// Quickstart §1–4: o dono cria o perfil (slug sugerido), adiciona a conta
// TikTok por link, tem a segunda ativa recusada, envia o logo, edita a
// descrição duas vezes, vê o antes/depois no histórico, reverte, arquiva e
// restaura.
test("dono cria perfil, conta, logo, edita, reverte, arquiva e restaura", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());

  const sfx = randomUUID().slice(0, 8);
  const name = `Taverna E2E ${sfx}`;
  const slug = `taverna-e2e-${sfx}`;
  const handle = `taverna_e2e_${sfx}`;
  const bio0 = `Descrição original ${sfx}`;
  const bio1 = `Descrição editada um ${sfx}`;
  const bio2 = `Descrição editada dois ${sfx}`;

  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  // §1: criar o perfil com o slug sugerido
  await page.getByRole("link", { name: "Perfis", exact: true }).first().click();
  await expect(page).toHaveURL(/\/app\/perfis$/);
  await page.getByRole("button", { name: "Novo perfil" })
    .or(page.getByRole("link", { name: "Novo perfil" }))
    .click();
  await expect(page).toHaveURL(/\/app\/perfis\/novo$/);
  await page.getByLabel("Nome").fill(name);
  await expect(page.getByLabel("Identificador")).toHaveValue(slug);
  await page.getByLabel("Nicho").fill("Geek, games, RPG");
  await page.getByLabel("Descrição").fill(bio0);
  await page.getByRole("button", { name: "Criar perfil" }).click();
  await expect(page).toHaveURL(/\/app\/perfis\/[0-9a-f-]{36}$/);
  const perfilUrl = page.url();
  await expect(page.getByText(name).first()).toBeVisible();
  await expect(page.getByText("Em preparação").first()).toBeVisible();

  // §2: conta TikTok por link colado; o @ é extraído
  await tab(page, "Contas").click();
  await addTikTok(page, `https://www.tiktok.com/@${handle}`);
  await expect(page.getByText(`@${handle}`).first()).toBeVisible();

  // segunda conta TikTok ativa no mesmo perfil é recusada
  await addTikTok(page, `@${handle}_outra`);
  await expect(page.getByText("Este perfil já tem uma conta ativa no TikTok")).toBeVisible();
  await expect(page.getByText(`@${handle}_outra`)).toHaveCount(0);

  // §3: logo (PNG 300×300 gerado aqui) vira miniatura servida pelo /img/
  await tab(page, "Dados").click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Trocar logo" }).click();
  await (await chooser).setFiles({ name: "logo.png", mimeType: "image/png", buffer: pngBuffer(300, 300) });
  const thumb = page.locator('img[src^="/img/"]').first();
  await expect(thumb).toBeVisible();
  await expect.poll(() => thumb.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);

  // §4: editar a descrição duas vezes
  for (const bio of [bio1, bio2]) {
    await page.getByLabel("Descrição").fill(bio);
    await page.getByRole("button", { name: "Salvar" }).click();
    await expect(page.getByLabel("Descrição")).toHaveValue(bio);
    await page.reload();
    await expect(page.getByLabel("Descrição")).toHaveValue(bio);
  }

  // histórico: as duas edições, com o antes e o depois da descrição
  await tab(page, "Histórico").click();
  const firstEdit = historyEntries(page).filter({ hasText: bio0 }).filter({ hasText: bio1 });
  const secondEdit = historyEntries(page).filter({ hasText: bio1 }).filter({ hasText: bio2 });
  await expect(firstEdit.first()).toBeVisible();
  await expect(firstEdit.first()).toContainText("Alterado");
  await expect(secondEdit.first()).toBeVisible();
  await expect(secondEdit.first()).toContainText("Alterado");

  // o dono reverte para a versão da primeira edição
  await firstEdit.first().getByRole("button", { name: "Reverter para esta versão" }).click();
  await confirmIfAsked(page, "Reverter");
  await expect(page.getByText("Revertido").first()).toBeVisible();
  await tab(page, "Dados").click();
  await expect(page.getByLabel("Descrição")).toHaveValue(bio1);

  // arquivar: some da lista e aparece com o filtro "Arquivados"
  await page.getByRole("button", { name: "Arquivar", exact: true }).click();
  await confirmIfAsked(page, "Arquivar");
  await expect(page.getByRole("button", { name: "Restaurar", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Perfis", exact: true }).first().click();
  await expect(page).toHaveURL(/\/app\/perfis$/);
  await expect(page.getByText(name)).toHaveCount(0);
  await page.getByLabel("Arquivados").check();
  await expect(page.getByText(name).first()).toBeVisible();

  // restaurar: volta para a lista padrão
  await page.goto(perfilUrl);
  await page.getByRole("button", { name: "Restaurar", exact: true }).click();
  await confirmIfAsked(page, "Restaurar");
  await expect(page.getByRole("button", { name: "Arquivar", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Perfis", exact: true }).first().click();
  await expect(page).toHaveURL(/\/app\/perfis$/);
  await expect(page.getByText(name).first()).toBeVisible();
});
