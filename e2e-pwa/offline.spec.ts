import { expect, type Page, test } from "@playwright/test";
import { OWNER } from "../e2e/fixtures";
import { login, logout } from "../e2e/helpers";
import { waitForActiveSW } from "./helpers";

// US2: o SW não guarda nada de /api nem /img, nenhum token fica no navegador,
// e sem rede o app mostra a tela de "Sem conexão".

interface StorageSnapshot {
  cachedUrls: string[];
  tokenPlaces: string[];
}

// Lista as URLs do Cache Storage e procura JWT ("eyJ") em localStorage,
// sessionStorage e em todos os object stores do IndexedDB.
async function snapshotStorage(page: Page): Promise<StorageSnapshot> {
  return page.evaluate(async () => {
    const cachedUrls: string[] = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      for (const req of await cache.keys()) cachedUrls.push(req.url);
    }

    const tokenPlaces: string[] = [];
    const scan = (where: string, value: unknown) => {
      if (JSON.stringify(value ?? null).includes("eyJ")) tokenPlaces.push(where);
    };
    for (const [label, store] of [["localStorage", localStorage], ["sessionStorage", sessionStorage]] as const) {
      for (let i = 0; i < store.length; i++) {
        const key = store.key(i)!;
        scan(`${label}:${key}`, `${key}=${store.getItem(key)}`);
      }
    }
    for (const info of await indexedDB.databases()) {
      if (!info.name) continue;
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        const req = indexedDB.open(info.name!);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      for (const storeName of Array.from(db.objectStoreNames)) {
        const values = await new Promise<unknown[]>((resolve, reject) => {
          const req = db.transaction(storeName, "readonly").objectStore(storeName).getAll();
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => reject(req.error);
        });
        scan(`indexedDB:${info.name}/${storeName}`, values);
      }
      db.close();
    }
    return { cachedUrls, tokenPlaces };
  });
}

function expectNothingSensitive(snapshot: StorageSnapshot): void {
  expect(snapshot.cachedUrls.length, "o precache deveria ter o app shell").toBeGreaterThan(0);
  const leaked = snapshot.cachedUrls.filter((url) => {
    const path = new URL(url).pathname;
    return path.startsWith("/api/") || path.startsWith("/img/");
  });
  expect(leaked, "URLs de /api ou /img no Cache Storage").toEqual([]);
  expect(snapshot.tokenPlaces, "token no armazenamento do navegador").toEqual([]);
}

test("cache e armazenamento sem dados da API nem token, antes e depois de Sair", async ({ page }) => {
  await page.goto("/login");
  await waitForActiveSW(page);
  await login(page, OWNER.email, OWNER.password);
  await expect(page).toHaveURL(/\/app$/);

  await page.getByRole("link", { name: "Usuários" }).click();
  await expect(page).toHaveURL(/\/app\/usuarios$/);
  await page.getByRole("link", { name: "Segurança" }).click();
  await expect(page).toHaveURL(/\/app\/seguranca$/);

  expectNothingSensitive(await snapshotStorage(page));

  await logout(page);
  expectNothingSensitive(await snapshotStorage(page));
});

test("sem rede mostra 'Sem conexão' e 'Tentar de novo' volta", async ({ page, context }) => {
  await page.goto("/login");
  await waitForActiveSW(page);

  await context.setOffline(true);
  const start = Date.now();
  await page.reload();
  await expect(page.getByText("Sem conexão com o SociMan")).toBeVisible({ timeout: 2_000 });
  expect(Date.now() - start).toBeLessThan(2_000);

  await context.setOffline(false);
  await page.getByRole("button", { name: "Tentar de novo" }).click();
  await expect(page.getByText("Sem conexão com o SociMan")).toBeHidden();
  await expect(page).toHaveURL(/\/(login|app)(\/.*)?$/);
});
