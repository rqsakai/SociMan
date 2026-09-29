// Anti-drift da CSP: a política estrita vive em DOIS lugares por necessidade —
// apps/web/vite.config.ts (preview/validação local) e docker/nginx/05-edge-mode.envsh
// (servida pelo edge). Este check falha se elas divergirem, para ninguém
// "endurecer" uma e esquecer a outra. Roda via `npm run check:csp`.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { strictCsp } from "../apps/web/vite.config";

const envshPath = fileURLToPath(new URL("../docker/nginx/05-edge-mode.envsh", import.meta.url));
const envsh = readFileSync(envshPath, "utf8");

function extract(pattern: RegExp, label: string): string {
  const match = envsh.match(pattern);
  if (!match?.[1]) {
    console.error(`✗ não achei ${label} em 05-edge-mode.envsh — o formato mudou?`);
    process.exit(1);
  }
  return match[1];
}

const nginxStrict = extract(/STRICT_CSP="([^"]+)"/, "STRICT_CSP");
const nginxDev = extract(/WEB_CSP="(default-src[^"]+)"\n/, "WEB_CSP do modo dev");

// a CSP de dev é derivada da estrita com 'unsafe-inline' em script/style
// (injeções inline do Vite dev) — mesma derivação feita no vite.config
const expectedDev = strictCsp
  .replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
  .replace("style-src 'self'", "style-src 'self' 'unsafe-inline'");

let failed = false;
if (nginxStrict !== strictCsp) {
  console.error("✗ CSP ESTRITA divergiu entre vite.config.ts e 05-edge-mode.envsh:");
  console.error(`  vite : ${strictCsp}`);
  console.error(`  nginx: ${nginxStrict}`);
  failed = true;
}
if (nginxDev !== expectedDev) {
  console.error("✗ CSP de DEV do nginx não é a derivação esperada da estrita:");
  console.error(`  esperada: ${expectedDev}`);
  console.error(`  nginx   : ${nginxDev}`);
  failed = true;
}

if (failed) process.exit(1);
console.log("✓ CSP em sincronia (vite.config × nginx edge, modos estrito e dev).");
