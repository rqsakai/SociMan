// Anti-drift da CSP: a política de produção vive em DOIS lugares por necessidade —
// apps/web/vite.config.ts (preview/validação local) e docker/nginx/05-edge-mode.envsh
// (servida pelo edge). Este check falha se:
// - elas divergirem (ninguém "endurece" ou relaxa uma e esquece a outra);
// - o script-src de produção não for exatamente 'self' (sem unsafe-*, sem origem externa);
// - o style-src passar do relaxamento aceito na ADR 0001 ('self' 'unsafe-inline');
// - qualquer diretiva (produção ou dev) tiver origem externa.
// Roda via `npm run check:csp`.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { devCsp, strictCsp } from "../apps/web/vite.config";

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

const errors: string[] = [];

if (nginxStrict !== strictCsp) {
  errors.push(
    "CSP de PRODUÇÃO divergiu entre vite.config.ts e 05-edge-mode.envsh:\n" +
      `  vite : ${strictCsp}\n  nginx: ${nginxStrict}`,
  );
}
if (nginxDev !== devCsp) {
  errors.push(
    "CSP de DEV divergiu entre vite.config.ts e 05-edge-mode.envsh:\n" +
      `  vite : ${devCsp}\n  nginx: ${nginxDev}`,
  );
}

function parse(csp: string): Map<string, string[]> {
  const directives = new Map<string, string[]>();
  for (const part of csp.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) directives.set(name, sources);
  }
  return directives;
}

// Só palavras-chave e o esquema data: (img-src) — qualquer outra coisa é origem externa.
const allowedSources = new Set(["'self'", "'none'", "'unsafe-inline'", "data:"]);

function checkPolicy(label: string, csp: string, allowedScript: string) {
  const directives = parse(csp);
  for (const [name, sources] of directives) {
    for (const source of sources) {
      if (!allowedSources.has(source)) {
        errors.push(`${label}: ${name} tem origem/valor não permitido: ${source}`);
      }
    }
  }
  const script = directives.get("script-src")?.join(" ");
  if (script !== allowedScript) {
    errors.push(`${label}: script-src deve ser exatamente "${allowedScript}" (está "${script ?? "ausente"}")`);
  }
  const style = directives.get("style-src")?.join(" ");
  if (style !== "'self'" && style !== "'self' 'unsafe-inline'") {
    errors.push(`${label}: style-src só pode ser "'self'" ou "'self' 'unsafe-inline'" (está "${style ?? "ausente"}")`);
  }
  for (const [name, sources] of directives) {
    if (name !== "style-src" && name !== "script-src" && sources.includes("'unsafe-inline'")) {
      errors.push(`${label}: ${name} não pode ter 'unsafe-inline'`);
    }
  }
}

checkPolicy("produção", strictCsp, "'self'");
// em dev, o preamble inline do react-refresh exige 'unsafe-inline' no script-src
checkPolicy("dev", devCsp, "'self' 'unsafe-inline'");

if (errors.length) {
  for (const e of errors) console.error(`✗ ${e}`);
  process.exit(1);
}
console.log("✓ CSP em sincronia (vite.config × nginx edge) e dentro da ADR 0001 (script-src estrito, sem origem externa).");
