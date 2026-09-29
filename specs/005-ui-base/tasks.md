---

description: "Tarefas da feature 005-ui-base"
---

# Tasks: Base de UI e layout de painel (005-ui-base)

**Tests**: OBRIGATÓRIOS. Os e2e existentes continuam verdes, entra `e2e/layout.spec.ts`, e o modo
casa não pode ter violação de CSP.

## Phase 1: Setup

- [X] T001 CSP da constitution 2.0.0:
  - em `apps/web/vite.config.ts` (`strictCsp`) e em `docker/nginx/05-edge-mode.envsh`
    (`STRICT_CSP`), trocar `style-src 'self'` por `style-src 'self' 'unsafe-inline'`;
  - em `scripts/check-csp-sync.ts`, além de comparar os dois, falhar se o `script-src` de produção
    tiver `unsafe-inline`, `unsafe-eval` ou alguma origem externa, e se qualquer diretiva tiver
    origem externa;
  - rodar `docker compose restart edge` e `npm run check:csp`.
- [X] T002 Instalar o shadcn/ui em `apps/web`:
  - `components.json` com Tailwind 4, alias `@/`, estilo `new-york` e `baseColor` neutral;
  - alias `@` no `vite.config.ts` e no `tsconfig`;
  - `src/lib/utils.ts` com `cn()`;
  - gerar os componentes listados no plan.md com `npx shadcn@latest add …`;
  - `npm i @tanstack/react-table sonner @fontsource-variable/roboto`.
- [X] T003 Tema em `apps/web/src/index.css`:
  - tokens (`--background` cinza-claro `#f0f2f5`, `--primary` azul-índigo, `--sidebar` escuro em
    degradê, sucesso, aviso, erro, info, `--radius` 0.75rem, sombras);
  - Roboto local.

  O `npm run check:web` continua verde.

## Phase 2: Foundational

- [X] T004 Criar `src/components/shell/`:
  - `AppShell`: menu, barra e rodapé;
  - `Sidebar`: flutuante escura, com marca SociMan, itens por papel, item ativo em pílula
    primária e gaveta (`Sheet`) abaixo de 1024 px;
  - `Topbar`: trilha, título, busca, menu de conta com "Minha conta" e "Sair";
  - `Footer`;
  - `AuthShell`: fundo escuro e cartão central com cabeçalho colorido sobreposto;
  - `MetricCard`: selo de ícone saindo do topo;
  - `HeaderCard`: faixa colorida sobreposta ao topo.

  Montar o `Toaster` do sonner no `App.tsx`.
- [X] T005 Criar `src/components/data-table/`:
  - `DataTable<T>` (TanStack Table) com colunas, ordenação, filtro global, paginação 10/25/50 com
    total, estado carregando (Skeleton) e vazio ("Nenhum resultado");
  - cabeçalho em caixa alta pequena;
  - rolagem horizontal dentro do cartão;
  - `SortableHeader` indica a direção.

## Phase 3: US1 + US2 (P1): painel e tabelas

- [X] T006 [US1] Colocar todas as rotas logadas dentro do `AppShell`. Substituir o `AppLayout` e o
  `AppHome` pelo `Home` novo (FR-006): cartões de métrica com perfis ativos, contas ativas por
  plataforma e usuários ativos (dono), e os eventos de segurança recentes em linha do tempo (dono)
- [X] T007 [US2] Migrar para o `DataTable` as páginas `PerfisList`, `Users` e `SecurityEvents`. Os
  filtros de servidor continuam onde existem (SecurityEvents usa cursor: o DataTable aceita
  paginação externa com "Carregar mais"). Manter textos e rótulos
- [X] T008 [US1] Migrar para os componentes shadcn o `PerfilDetalhe` (cabeçalho estilo "profile":
  banner, logo e abas em pílula), `ContasTab`, `ContaHistorico`, `VersionHistory` (linha do tempo),
  `ImageUpload`, `PerfilNovo` e `Account`. Manter o `<select>` nativo e os textos. Confirmações em
  `AlertDialog` (role dialog, botões "Reverter", "Arquivar" e "Restaurar")

## Phase 4: US3 + US4 (P2)

- [X] T009 [US3] Migrar para o `AuthShell` as páginas `Login`, `ForgotPassword`, `ResetPassword`,
  `VerifyEmail`, `ChangePassword` e `Offline`. Os textos atuais continuam iguais: "E-mail ou senha
  incorretos", "Esqueci a senha", "Entrar", "Confirme seu e-mail antes de entrar" e "Reenviar link"
- [X] T010 [US4] Padronizar os avisos: sucesso vira toast; erro da API e conflito de versão ficam
  em `Alert` com a mensagem da API (e "Recarregar"). O `UpdatePrompt` do PWA passa a usar o estilo
  novo e mantém `role="status"` e os textos. Remover o `components/ui.tsx` antigo quando ele não
  tiver mais uso

## Phase 5: Polish

- [X] T011 Criar `e2e/layout.spec.ts` (FR-001–003, SC-003):
  - menu por papel (dono e membro);
  - item ativo;
  - gaveta a 390 px;
  - ordenação e paginação da tabela de perfis (criar 12 perfis pela API no teste);
  - `document.documentElement.scrollWidth <= innerWidth` em todas as telas a 390 px.
- [X] T012 Verificação:
  - `npm run check:web` e `npm run test:e2e` (dev), com 9/9 incluindo o `layout.spec`;
  - `npm run casa:up && npm run test:e2e:pwa`, com uma checagem nova de console sem violação de
    CSP (SC-004), e depois voltar ao modo dev;
  - capturas das telas principais em `.playwright-mcp/sociman/` (fora do git) para o dono comparar
    com a referência;
  - atualizar o CLAUDE.md (shadcn: `npx shadcn@latest add`; componentes em `components/ui`; shell
    e data-table).

## Dependencies
T001–T003 → T004–T005 → T006–T010. A T006 e a T007 podem andar juntas depois da T005; a T008 e a
T009 também. A T011 e a T012 vêm no fim.

## Resultado da verificação (2026-09-29)
- `npm run check:web`: verde. O `check:csp` exige agora `script-src 'self'` exato e proíbe origem externa.
- `npm run test:e2e` (dev): 13/13 em 4 rodadas seguidas, incluindo `layout.spec.ts`. Duas correções:
  - os e2e zeravam o limite de tentativas só no início da suíte; agora o helper de login limpa as chaves `rl:*` antes de entrar (o limite do app não mudou);
  - o teste de confirmação passou a aceitar `alertdialog`, que é o papel correto do shadcn.
- `npm run casa:up && npm run test:e2e:pwa`: 10/10, incluindo o `csp.spec.ts` novo, sem violação de CSP no build de produção (SC-004).
- `ui.tsx`, `layout.tsx`, `AppLayout.tsx`, `AppHome.tsx`, `FormField.tsx` e os aliases de CSS legados foram removidos. A fonte woff2 entrou no precache do PWA.
- As capturas para o dono estão em `.playwright-mcp/sociman/` (fora do git).
