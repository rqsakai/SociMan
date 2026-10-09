# Implementation Plan: Base de UI e layout de painel (005-ui-base)

**Branch**: `005-ui-base` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

## Summary
- Adotar o shadcn/ui (Radix) e o TanStack Table no `apps/web`, sobre Tailwind 4.
- Criar o painel (AppShell), a tabela de dados genérica (DataTable) e o layout de acesso
  (AuthShell), seguindo `docs/design/layout-referencia.md`.
- Migrar todas as telas atuais para os novos componentes.
- Aplicar a CSP da constitution 2.0.0, com `style-src 'unsafe-inline'`, no `vite.config.ts` e no
  edge.

## Technical Context
**Language/Version**: TypeScript 5, React 19, Vite 8, Tailwind 4

**Primary Dependencies**:
- **novas:** componentes do shadcn/ui, gerados via CLI em `apps/web/src/components/ui/`, com as
  dependências que eles puxam (`@radix-ui/*`, `class-variance-authority`, `clsx`,
  `tailwind-merge`, `tw-animate-css`), mais `@tanstack/react-table`, `sonner` e
  `@fontsource-variable/roboto` (fonte local, sem CDN);
- **já existentes:** `lucide-react` (ícones) e `@tanstack/react-query`.

**Testing**:
- `npm run check:web`, com `check:csp` atualizado;
- os e2e de dev (`test:e2e`) e de PWA (`test:e2e:pwa`), que precisam continuar verdes;
- e2e novo `e2e/layout.spec.ts`: menu por papel, item ativo, gaveta em 390 px, ordenação e
  paginação da tabela de perfis e ausência de rolagem horizontal;
- no modo casa, `test:e2e:pwa` coleta violações de CSP do console.

**Constraints**:
- a CSP é exatamente a da ADR 0001;
- nenhuma origem externa;
- `<select>` nativo nos formulários (a acessibilidade e os e2e dependem dele); o Radix Select só
  em filtros, quando não houver e2e dependente;
- os textos das telas não mudam.

## Constitution Check
| Princípio | Situação |
|---|---|
| III | ✅ as cores e raios viram tokens CSS do tema (`--primary`…), sem hex solto nos componentes |
| IV | ✅ nenhum contrato muda |
| V | ✅ só o `style-src` relaxa (constitution 2.0.0 e ADR 0001); `script-src` segue estrito; `check:csp` segue anti-drift |
| VI | ✅ e2e existentes, mais `layout.spec.ts` e a checagem de CSP no modo casa |
| VIII | ✅ dependências previstas na constitution 2.0.0 (stack fixa) |

## Structure
```text
apps/web/
├── components.json                      # config do shadcn (aliases @/components, @/lib)
├── src/index.css                        # tema: tokens (cores, raio, sombras), fonte Roboto local
├── src/lib/utils.ts                     # cn()
├── src/components/ui/*                  # gerados pelo shadcn (button, input, label, card, badge, table,
│                                        #   dialog, alert-dialog, dropdown-menu, tabs, sheet, avatar,
│                                        #   separator, switch, tooltip, alert, sonner, skeleton, breadcrumb, textarea)
├── src/components/shell/{AppShell,Sidebar,Topbar,Footer,AuthShell,MetricCard,HeaderCard}.tsx
├── src/components/data-table/{DataTable,DataTablePagination,SortableHeader}.tsx   # TanStack Table
└── src/pages/**                         # migradas (Home nova no lugar de AppHome)
apps/web/vite.config.ts                  # strictCsp: style-src 'self' 'unsafe-inline'
docker/nginx/05-edge-mode.envsh          # STRICT_CSP idem
scripts/check-csp-sync.ts                # passa a exigir script-src 'self' sem unsafe-* e aceitar só o style-src relaxado
e2e/layout.spec.ts
```
O `components/ui.tsx` antigo sai quando não houver mais nenhum uso dele.

## Complexity Tracking
| Item | Por quê |
|---|---|
| shadcn/ui + Radix | decisão do dono (constitution 2.0.0): componentes acessíveis e consistentes |
| TanStack Table | ordenação, filtro e paginação sem reescrever a lógica em cada tela |
| sonner | toasts do shadcn |
| @fontsource-variable/roboto | tipografia da referência servida localmente (FR-007) |
