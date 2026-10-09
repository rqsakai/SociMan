import { request } from "@playwright/test";
import e2eGlobalSetup from "../e2e/global-setup";
import { HTTPS_URL } from "./helpers";

// Espera o edge HTTPS (modo prod) e reaproveita o setup do e2e:
// reset-db, dono de teste e Mailpit vazio.
async function waitForHttpsHealth(timeoutMs: number): Promise<void> {
  const ctx = await request.newContext({ ignoreHTTPSErrors: true });
  const deadline = Date.now() + timeoutMs;
  let last = "sem resposta";
  try {
    while (Date.now() < deadline) {
      try {
        const res = await ctx.get(`${HTTPS_URL}/api/health`);
        if (res.status() === 200) return;
        last = `HTTP ${res.status()}`;
      } catch (err) {
        last = String(err);
      }
      await new Promise((r) => setTimeout(r, 1_000));
    }
  } finally {
    await ctx.dispose();
  }
  throw new Error(
    `${HTTPS_URL}/api/health não respondeu 200 em ${timeoutMs} ms (${last}). A stack e2e subiu no perfil pwa (npm run test:e2e:pwa)?`,
  );
}

export default async function globalSetup(): Promise<void> {
  await waitForHttpsHealth(60_000);
  await e2eGlobalSetup();
}
