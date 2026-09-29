import { defineConfig } from "@playwright/test";

// e2e do PWA (spec 002): roda contra a stack em modo prod (`npm run casa:up`).
// O service worker só existe no build de produção. A base é http://localhost:8180
// (localhost é contexto seguro): pelo HTTPS o Chromium do teste, que não tem a CA
// da casa, RECUSA registrar o SW ("SSL certificate error") mesmo com
// ignoreHTTPSErrors. A cadeia do HTTPS é testada à parte (install.spec, com a CA).
// Não rode junto com o `test:e2e` (dev): os dois zeram o mesmo banco.
export default defineConfig({
  testDir: "e2e-pwa",
  globalSetup: "./e2e-pwa/global-setup.ts",
  timeout: 60_000,
  workers: 1, // mesmo banco, mesmo dist (o update.spec reconstrói o build)
  use: {
    baseURL: "http://localhost:8180",
    serviceWorkers: "allow",
  },
});
