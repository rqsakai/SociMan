import { expect, test } from "@playwright/test";
import { BASE_URL, OWNER } from "./fixtures";
import { login } from "./helpers";

// Login → reload mantém a sessão → sair → /app exige login (FR-002: token
// nenhum no storage do navegador; renovação só pelo cookie HttpOnly).
test("sessão sobrevive ao reload, não vaza token e termina no sair", async ({ page }) => {
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  const cookies = await page.context().cookies(`${BASE_URL}/api/auth/refresh`);
  const rt = cookies.find((c) => c.name === "sociman_rt");
  expect(rt).toBeDefined();
  expect(rt!.httpOnly).toBe(true);
  expect(rt!.path).toBe("/api/auth/refresh");

  // access token só em memória: o reload o perde e o cookie restaura a sessão
  await page.reload();
  await expect(page).toHaveURL(/\/app$/);

  const stored = await page.evaluate(() => {
    const values: string[] = [];
    for (const storage of [localStorage, sessionStorage]) {
      for (let i = 0; i < storage.length; i++) {
        const key = storage.key(i)!;
        values.push(key, storage.getItem(key) ?? "");
      }
    }
    return values;
  });
  expect(stored.filter((v) => v.includes("eyJ"))).toEqual([]);

  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/app");
  await expect(page).toHaveURL(/\/login$/);
});
