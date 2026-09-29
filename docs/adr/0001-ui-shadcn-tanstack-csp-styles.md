# ADR 0001: UI com shadcn/ui + TanStack e CSP com estilos inline

**Status:** Aceita (2026-09-29, decisão do dono) · **Constitution:** 2.0.0 (princípio V)

## Contexto
- O SPA herdou do volans componentes feitos à mão e uma CSP **totalmente estrita**
  (`style-src 'self'`, sem `unsafe-inline`).
- O SociMan vai ganhar muitas telas de gestão (tabelas, formulários, editor de kit de marca,
  filas). O dono quer um painel com cara profissional, com layout inspirado no Material Dashboard
  React, da Creative Tim.
- Os componentes do shadcn/ui usam Radix, e alguns dependências, como `react-remove-scroll` no
  Dialog, Sheet e Select e o `sonner` nos toasts, **injetam `<style>` em tempo de execução**. Com
  `style-src 'self'`, isso é bloqueado.
- O SociMan é uma **ferramenta interna**, usada na rede de casa por poucos usuários.

## Decisão
- A stack do SPA passa a ser **shadcn/ui (Radix) + Tailwind 4 + TanStack Query + TanStack Table**,
  com layout de painel inspirado no Material Dashboard React. A demo serve só de **referência
  visual**: nenhum código, imagem ou marca da Creative Tim é copiado.
- A CSP de produção passa a ser
  `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'`
  - `script-src` continua **estrito, sem exceções**.
  - Só o `style-src` é relaxado.
  - Nenhuma origem externa.
- O `check:csp` continua garantindo que `vite.config.ts` e o edge usem a mesma política.

## Consequências
- **Risco aceito:** injeção de CSS, por exemplo exfiltração por seletores CSS ou disfarce visual,
  se houver uma falha que deixe injetar HTML. Esse risco é menor que o de XSS, porque CSS não
  executa código, e a defesa contra XSS (o `script-src` estrito) continua intacta. O conteúdo
  vindo da API é sempre renderizado como texto pelo React.
- As fontes e os ícones continuam servidos da própria origem: nada de Google Fonts nem de CDN.
- **Documentos superados:**
  - `docs/reference/volans/decisions/0003-padrao-hibrido-cookieless.md`, nas consequências ("CSP
    estrita é inegociável"): no SociMan, vale o `script-src` estrito;
  - `docs/reference/volans/architecture/security.md`, no item 4 e na seção "SPA (borda)";
  - `docs/visao.md`, no princípio candidato 4.
- A mudança de código (CSP no `vite.config.ts` e no edge, adoção do shadcn e reestruturação do
  layout) é feita numa spec própria, porque a constitution exige spec antes de código de feature.
