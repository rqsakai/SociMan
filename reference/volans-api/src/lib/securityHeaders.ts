// Headers de segurança aplicados a TODAS as respostas da API (via next.config).
// A CSP da SPA vive em apps/web/vite.config.ts; em produção real, o pipeline
// de deploy do Volans consome estes valores para servir nos dois componentes.
export const apiSecurityHeaders: Record<string, string> = {
  // API é só JSON — CSP restritiva aqui é defesa em profundidade.
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Cache-Control": "no-store",
};
