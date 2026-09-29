import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { expect, type Page } from "@playwright/test";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export const HOME_IP = "192.168.86.47";

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

// Build de produção do SPA no dist montado pelo web-prod (sem restart).
// `buildId` indefinido = build normal (sem VITE_BUILD_ID).
export function buildWeb(buildId?: string): void {
  const env = { ...process.env };
  if (buildId === undefined) delete env.VITE_BUILD_ID;
  else env.VITE_BUILD_ID = buildId;
  execFileSync("npm", ["run", "build", "-w", "@sociman/web"], {
    cwd: repoRoot,
    env,
    stdio: ["ignore", "inherit", "inherit"],
  });
}
