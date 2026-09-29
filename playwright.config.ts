import { defineConfig } from "@playwright/test";

// e2e roda contra a stack do docker compose (edge em :8180 servindo SPA + API).
// Suba antes com `docker compose up -d`; o Playwright não sobe servidor nenhum.
// O global setup espera o /api/health, zera o banco pela CLI, cria o dono de
// teste e limpa o Mailpit.
export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 60_000,
  workers: 1, // fluxos compartilham o mesmo banco e o mesmo Mailpit — serializa
  use: {
    baseURL: "http://localhost:8180",
  },
});
