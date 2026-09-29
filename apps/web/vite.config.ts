import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

// CSP estrita usada em produção (o pipeline de deploy serve estes headers; aqui
// ela é aplicada no `vite preview` para validar que o app funciona sob ela).
// Em dev, DUAS injeções do Vite são inline por design e precisam de exceção:
// - script: preamble do @vitejs/plugin-react (react-refresh)
// - style: o CSS em dev chega via <style> injetada por JS (é assim que o HMR
//   de CSS funciona) — sem 'unsafe-inline' em style-src o app renderiza sem
//   estilo nenhum e o console mostra "Applying inline style violates ..."
// O build de produção emite script e CSS como ARQUIVOS externos, então a
// política estrita vale lá — validada por `npm run preview:csp`.
export const strictCsp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  "object-src 'none'",
  "form-action 'self'",
].join("; ");

const devCsp = strictCsp
  .replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
  .replace("style-src 'self'", "style-src 'self' 'unsafe-inline'");

const securityHeaders = (csp: string) => ({
  "Content-Security-Policy": csp,
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
});

export default defineConfig({
  // identifica o build no <html data-build> (VITE_BUILD_ID tem prioridade; senão a data do build)
  define: { __BUILD_DATE__: JSON.stringify(new Date().toISOString()) },
  plugins: [
    react(),
    tailwindcss(),
    // PWA (spec 002): SW gerado pelo Workbox que só precacheia o build. /api e
    // /img nunca passam pelo cache (sem runtimeCaching + denylist de navegação).
    // O registro vem de `virtual:pwa-register/react` (sem script inline, CSP intacta).
    VitePWA({
      registerType: "prompt",
      injectRegister: null,
      includeManifestIcons: false, // os ícones já entram pelo globPatterns (evita duplicata no precache)
      devOptions: { enabled: false },
      manifest: {
        name: "SociMan",
        short_name: "SociMan",
        description: "Gestão das contas de mídia social da agência",
        lang: "pt-BR",
        start_url: "/app",
        scope: "/",
        id: "/",
        display: "standalone",
        theme_color: "#0f172a",
        background_color: "#0f172a",
        icons: [
          { src: "pwa-64x64.png", sizes: "64x64", type: "image/png", purpose: "any" },
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "maskable-icon-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/img\//, /^\/sociman-ca\./],
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  // cache separado quando rodando no docker-compose (repo bind-mount; o cache
  // do host em node_modules/.vite não pode ser compartilhado entre processos)
  cacheDir: process.env.VITE_CACHE_DIR || "node_modules/.vite",
  server: {
    port: 5173,
    headers: securityHeaders(devCsp),
    proxy: {
      "/api": {
        target: "http://localhost:3001",
        changeOrigin: false,
      },
    },
  },
  preview: {
    port: 5173,
    headers: securityHeaders(strictCsp),
    proxy: {
      "/api": {
        target: "http://localhost:3001",
        changeOrigin: false,
      },
    },
  },
});
