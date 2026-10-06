import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

// CSP de produção (constitution 2.0.0, ADR 0001). O pipeline de deploy serve
// estes headers; aqui ela é aplicada no `vite preview` para validar o app.
// - script-src é estrito, sem exceções.
// - style-src aceita 'unsafe-inline': Radix (react-remove-scroll no Dialog/Sheet)
//   e o sonner injetam <style> em tempo de execução. Risco aceito na ADR 0001.
// Em dev, o preamble do @vitejs/plugin-react (react-refresh) é um <script>
// inline, então a CSP de dev relaxa também o script-src. O build de produção
// emite os scripts como arquivos externos. `npm run check:csp` garante que o
// edge (docker/nginx/05-edge-mode.envsh) usa a mesma política.
export const strictCsp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  "object-src 'none'",
  "form-action 'self'",
].join("; ");

export const devCsp = strictCsp.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'");

const securityHeaders = (csp: string) => ({
  "Content-Security-Policy": csp,
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
});

export default defineConfig({
  // identifica o build no <html data-build> (VITE_BUILD_ID tem prioridade; senão a data do build)
  define: { __BUILD_DATE__: JSON.stringify(new Date().toISOString()) },
  // alias "@/" → src/ (o mesmo do tsconfig; usado pelos componentes do shadcn)
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
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
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"] /* woff2: a Roboto local também offline */,
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/img\//, /^\/sociman-ca\./],
        cleanupOutdatedCaches: true,
        // clique na notificação do navegador (spec 006, R11): foca o app e abre o link
        importScripts: ["/sw-notificacoes.js"],
        // ECharts do analytics (spec 019, R1 cuidado 2): ~234 kB gz que só quem abre /app/metricas
        // precisa. Fica fora do precache (instalar o PWA não baixa) e entra num cache em runtime;
        // é a única rota de runtime do SW (check:pwa confere).
        globIgnores: ["**/graficos-*.js"],
        runtimeCaching: [
          {
            urlPattern: /\/assets\/graficos-[\w-]+\.js$/,
            handler: "StaleWhileRevalidate",
            options: { cacheName: "sociman-graficos", expiration: { maxEntries: 4 } },
          },
        ],
      },
    }),
  ],
  build: {
    rollupOptions: {
      output: {
        // nome fixo para o chunk do ECharts (spec 019): o SW o reconhece por `graficos-*.js`
        manualChunks(id) {
          if (/[\\/]node_modules[\\/](echarts|zrender)[\\/]/.test(id)) return "graficos";
        },
      },
    },
  },
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
