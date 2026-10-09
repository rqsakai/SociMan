import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { expect, type Page } from "@playwright/test";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export const HOME_IP = "192.168.86.47"; // o LAN_HOST do edge em docker-compose.e2e.yml

// HTTPS do edge e2e (E2E_HTTPS_URL, do scripts/test-e2e.sh) e o dist que o web-prod serve.
function e2eEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} não definida: rode via \`npm run test:e2e:pwa\` (stack efêmera).`);
  return value;
}
export const HTTPS_URL = e2eEnv("E2E_HTTPS_URL");
const WEB_DIST = e2eEnv("E2E_WEB_DIST");

// Espera o SW do escopo "/" ficar `activated` (o UpdatePrompt o registra).
export async function waitForActiveSW(page: Page): Promise<void> {
  await expect
    .poll(
      () =>
        page.evaluate(async () => {
          const reg = await navigator.serviceWorker.getRegistration("/");
          return reg?.active?.state ?? "nenhum";
        }),
      { timeout: 20_000, message: "service worker não ficou activated" },
    )
    .toBe("activated");
}

// Build de produção do SPA no dist do e2e (E2E_WEB_DIST), montado pelo web-prod (sem restart).
// Nunca o apps/web/dist do modo casa. `buildId` indefinido = build normal (sem VITE_BUILD_ID).
export function buildWeb(buildId?: string): void {
  const env = { ...process.env };
  if (buildId === undefined) delete env.VITE_BUILD_ID;
  else env.VITE_BUILD_ID = buildId;
  execFileSync("npm", ["run", "build", "-w", "@sociman/web", "--", "--outDir", WEB_DIST, "--emptyOutDir"], {
    cwd: repoRoot,
    env,
    stdio: ["ignore", "inherit", "inherit"],
  });
}
