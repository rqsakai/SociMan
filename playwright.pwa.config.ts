import { defineConfig } from "@playwright/test";
import { BASE_URL } from "./e2e/fixtures";

// e2e do PWA (spec 002): roda na stack EFÊMERA em modo prod (`npm run test:e2e:pwa`, que
// faz o build em .e2e/pwa-dist e sobe o perfil `pwa` do docker-compose.e2e.yml).
// O service worker só existe no build de produção. A base é o HTTP de localhost
// (contexto seguro): pelo HTTPS o Chromium do teste, que não tem a CA
// da casa, RECUSA registrar o SW ("SSL certificate error") mesmo com
// ignoreHTTPSErrors. A cadeia do HTTPS é testada à parte (install.spec, com a CA).
export default defineConfig({
  testDir: "e2e-pwa",
  globalSetup: "./e2e-pwa/global-setup.ts",
  timeout: 60_000,
  workers: 1, // mesmo banco, mesmo dist (o update.spec reconstrói o build)
  use: {
    baseURL: BASE_URL,
    serviceWorkers: "allow",
  },
});
