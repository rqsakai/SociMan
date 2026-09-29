import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

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
  plugins: [react(), tailwindcss()],
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
