// Checagem da spec 002 (PWA): valida o build da SPA depois de
// `npm run build -w @sociman/web`. Confere o manifest (data-model.md), os ícones
// citados, o sw.js (sem runtimeCaching além do chunk de gráficos da spec 019,
// sem /api ou /img no precache, com o denylist de navegação) e o index.html (sem script inline, com manifest,
// theme-color e apple-touch-icon). Aceita outro dist como argumento (testes).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const distDir = process.argv[2]
  ? resolve(process.argv[2])
  : fileURLToPath(new URL("../apps/web/dist", import.meta.url));

if (!existsSync(distDir)) {
  console.error(`${distDir} não existe — rode \`npm run build -w @sociman/web\` antes.`);
  process.exit(1);
}

const errors = [];
const fail = (msg) => errors.push(msg);

// Manifest
const expectedManifest = {
  name: "SociMan",
  short_name: "SociMan",
  lang: "pt-BR",
  start_url: "/app",
  scope: "/",
  id: "/",
  display: "standalone",
  theme_color: "#0f172a",
  background_color: "#0f172a",
};
const expectedIcons = [
  { sizes: "64x64", purpose: "any" },
  { sizes: "192x192", purpose: "any" },
  { sizes: "512x512", purpose: "any" },
  { sizes: "512x512", purpose: "maskable" },
];

const manifestPath = join(distDir, "manifest.webmanifest");
if (!existsSync(manifestPath)) {
  fail("falta manifest.webmanifest no build");
} else {
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  } catch (err) {
    fail(`manifest.webmanifest não é JSON válido: ${err.message}`);
  }
  if (manifest) {
    for (const [key, value] of Object.entries(expectedManifest)) {
      if (manifest[key] !== value) {
        fail(`manifest: "${key}" é ${JSON.stringify(manifest[key])}, esperado ${JSON.stringify(value)}`);
      }
    }
    const icons = Array.isArray(manifest.icons) ? manifest.icons : [];
    for (const { sizes, purpose } of expectedIcons) {
      if (!icons.some((i) => i.sizes === sizes && (i.purpose ?? "any") === purpose)) {
        fail(`manifest: falta o ícone ${sizes} com purpose "${purpose}"`);
      }
    }
    for (const icon of icons) {
      if (!icon.src || !existsSync(join(distDir, icon.src.replace(/^\//, "")))) {
        fail(`manifest: o ícone "${icon.src}" não existe no build`);
      }
    }
  }
}

// Service worker
const swPath = join(distDir, "sw.js");
if (!existsSync(swPath)) {
  fail("falta sw.js no build");
} else {
  const sw = readFileSync(swPath, "utf8");
  // O Workbox só emite registerRoute com estratégia (CacheFirst etc.) quando há
  // runtimeCaching; o único registerRoute permitido é o NavigationRoute.
  // Exceção da spec 019 (R1, cuidado 2): o chunk do ECharts (`/assets/graficos-*.js`) fica fora do
  // precache e entra num StaleWhileRevalidate. É a ÚNICA rota com estratégia aceita; nada de /api,
  // /img nem outra estratégia.
  const graficos = /registerRoute\(\s*\/\\\/assets\\\/graficos-[^,]*,\s*new \w+\.StaleWhileRevalidate\(/g;
  const semGraficos = sw.replace(graficos, "");
  if (/runtimeCaching/.test(sw) || /new \w+\.(CacheFirst|NetworkFirst|StaleWhileRevalidate|NetworkOnly|CacheOnly)\b/.test(semGraficos)) {
    fail("sw.js tem runtimeCaching (proibido: o SW só pode precachear o build, salvo o chunk de gráficos da spec 019)");
  }
  if (!graficos.test(sw) && existsSync(join(distDir, "assets")) && readdirSync(join(distDir, "assets")).some((f) => /^graficos-.*\.js$/.test(f))) {
    fail("sw.js não tem a rota StaleWhileRevalidate do chunk de gráficos (spec 019)");
  }
  const precache = sw.match(/precacheAndRoute\(\s*(\[[\s\S]*?\])\s*,/);
  if (!precache) {
    fail("sw.js não tem a lista de precache (precacheAndRoute)");
  } else {
    const urls = [...precache[1].matchAll(/url:\s*"([^"]+)"/g)].map((m) => m[1]);
    for (const url of urls) {
      if (/^\/?(api|img)(\/|$)/.test(url)) fail(`sw.js: a lista de precache cita "${url}"`);
      if (/(^|\/)graficos-[^/]*\.js$/.test(url)) fail(`sw.js: o chunk de gráficos "${url}" está no precache (spec 019)`);
    }
  }
  const denylist = sw.match(/denylist:\s*\[([^\]]*)\]/);
  const deny = denylist ? denylist[1] : "";
  for (const [label, re] of [["/api", "/^\\/api\\//"], ["/img", "/^\\/img\\//"]]) {
    if (!deny.includes(re)) fail(`sw.js: o denylist de navegação não cobre ${label}`);
  }
}

// index.html
const indexPath = join(distDir, "index.html");
if (!existsSync(indexPath)) {
  fail("falta index.html no build");
} else {
  const html = readFileSync(indexPath, "utf8");
  for (const tag of html.match(/<script\b[^>]*>/gi) ?? []) {
    if (!/\ssrc\s*=/.test(tag)) fail(`index.html tem <script> inline (sem src): ${tag}`);
  }
  if (!/<link\b[^>]*rel="manifest"[^>]*href="\/manifest\.webmanifest"/.test(html)) {
    fail('index.html não tem <link rel="manifest" href="/manifest.webmanifest">');
  }
  if (!/<meta\b[^>]*name="theme-color"[^>]*content="#0f172a"/.test(html)) {
    fail('index.html não tem <meta name="theme-color" content="#0f172a">');
  }
  if (!/<link\b[^>]*rel="apple-touch-icon"[^>]*href="\/apple-touch-icon-180x180\.png"/.test(html)) {
    fail('index.html não tem <link rel="apple-touch-icon" href="/apple-touch-icon-180x180.png">');
  }
}

if (errors.length) {
  for (const msg of errors) console.error(`✗ ${msg}`);
  console.error("\ncheck:pwa falhou — o build do PWA não segue a spec 002.");
  process.exit(1);
}
console.log("check:pwa ok — manifest, ícones, sw.js (só precache, sem /api nem /img) e index.html conferidos.");
