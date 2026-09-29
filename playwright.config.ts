import { defineConfig } from "@playwright/test";

// e2e sobe os dois apps de verdade (api 3001 + web 5173 com proxy) e roda os
// fluxos no navegador. A API usa EMAIL_PROVIDER=file para os testes lerem os
// links de verificação/reset de apps/api/data/outbox.jsonl.
export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 60_000,
  workers: 1, // fluxos compartilham o mesmo banco de dev — serializa
  use: {
    baseURL: "http://localhost:5173",
  },
  webServer: [
    {
      command: "npm run dev -w @sociman/api",
      url: "http://localhost:3001/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        EMAIL_PROVIDER: "file",
        EMAIL_FILE: "./data/outbox.jsonl",
      },
    },
    {
      command: "npm run dev -w @sociman/web",
      url: "http://localhost:5173",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
