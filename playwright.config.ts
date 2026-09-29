import { defineConfig } from "@playwright/test";
import { BASE_URL } from "./e2e/fixtures";

// e2e roda numa stack EFÊMERA e isolada (docker-compose.e2e.yml, projeto sociman-e2e):
// rode com `npm run test:e2e`, que sobe a stack, passa os endereços por variável
// (E2E_BASE_URL, E2E_MAILPIT_URL, E2E_COMPOSE) e a destrói no fim. Sem essas variáveis
// o import de ./e2e/fixtures falha: nunca cai na stack de dev (:8180).
// O global setup espera o /api/health, zera o banco pela CLI, cria o dono de
// teste e limpa o Mailpit.
export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 60_000,
  workers: 1, // fluxos compartilham o mesmo banco e o mesmo Mailpit — serializa
  use: {
    baseURL: BASE_URL,
  },
});
