# Feature Specification: Base de UI e layout de painel (005-ui-base)

**Feature Branch**: `005-ui-base`

**Created**: 2026-09-29

**Status**: Draft (aprovada pelo dono para implementação imediata: "vamos iniciar as mudanças de código")

**Input**: Decisão do dono: stack shadcn/ui + TanStack + Tailwind, layout baseado no Material
Dashboard React (referência visual), aceitando a injeção de estilos dos componentes (constitution
2.0.0, ADR 0001). A referência observada está em `docs/design/layout-referencia.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Painel com menu lateral, barra superior e rodapé (Priority: P1)

Depois do login, todas as telas usam o mesmo painel:
- à esquerda, um menu lateral escuro e flutuante com a marca SociMan, os itens (Início, Perfis,
  Usuários, Segurança e Minha conta, conforme o papel) e o item ativo destacado;
- no topo, a trilha de navegação, o título da página, a busca e os atalhos de conta e sair;
- embaixo, um rodapé discreto.

No celular, o menu vira uma gaveta aberta por um botão.

**Why this priority**: é a base visual de todas as telas atuais e futuras.

**Independent Test**: entrar e navegar por Início, Perfis, Usuários (dono), Segurança (dono) e
Minha conta: o menu mostra o item ativo, a barra superior mostra a trilha e, a 390 px de largura,
o menu abre e fecha como gaveta.

**Acceptance Scenarios**:

1. **Given** um dono logado, **When** ele abre qualquer tela, **Then** vê o menu lateral com
   Início, Perfis, Usuários, Segurança e Minha conta, com o item atual destacado.
2. **Given** um membro, **When** ele abre o painel, **Then** Usuários e Segurança não aparecem.
3. **Given** uma tela larga (1280 px ou mais), **When** o painel abre, **Then** o menu fica fixo à
   esquerda; **Given** uma tela estreita (menos de 1024 px), **Then** ele vira uma gaveta aberta
   pelo botão de menu.
4. **Given** a barra superior, **When** o usuário clica em "Sair", **Then** a sessão termina, como
   hoje.

---

### User Story 2 - Tabelas ricas (Priority: P1)

As listas de Perfis, Usuários e Eventos de segurança viram tabelas com ordenação por coluna,
filtro por texto, paginação e estados de carregando e vazio, no estilo da referência:
- cabeçalho em caixa alta pequena;
- linhas altas;
- avatar e nome em negrito na primeira coluna;
- status como badges.

**Why this priority**: as tabelas são o centro do uso diário.

**Independent Test**: na lista de Perfis, ordenar por nome e por status, filtrar por texto, e
paginar quando houver mais de 10 linhas; ver o estado vazio quando o filtro não encontra nada.

**Acceptance Scenarios**:

1. **Given** uma tabela, **When** o usuário clica no cabeçalho de uma coluna ordenável, **Then** a
   ordem alterna entre crescente e decrescente, e o cabeçalho indica a direção.
2. **Given** uma tabela com mais linhas que o tamanho da página, **When** o usuário avança,
   **Then** vê a próxima página e o total de itens.
3. **Given** uma busca sem resultado, **When** a tabela filtra, **Then** mostra "Nenhum resultado"
   em vez de uma tabela vazia.

---

### User Story 3 - Telas de acesso no novo visual (Priority: P2)

Entrar, esqueci a senha, redefinir senha, trocar senha e verificar e-mail usam um cartão central
com cabeçalho colorido sobre um fundo escuro, sem cadastro público e sem login social.

**Why this priority**: primeira impressão e consistência; o funcionamento não muda.

**Independent Test**: abrir `/login`, errar a senha e ver o alerta; entrar; pedir recuperação e
redefinir, tudo no novo visual.

**Acceptance Scenarios**:

1. **Given** a tela de login, **When** ela abre, **Then** mostra o cartão com o cabeçalho
   "Entrar no SociMan", os campos E-mail e Senha, o botão "Entrar" e o link "Esqueci a senha".
2. **Given** qualquer tela de acesso, **When** ela é usada, **Then** os textos, mensagens e fluxos
   atuais continuam os mesmos.

---

### User Story 4 - Avisos e confirmações consistentes (Priority: P2)

Sucessos, erros e conflitos aparecem como avisos (toasts) ou alertas no padrão visual.
Confirmações (reverter, arquivar) usam uma janela de diálogo.

**Independent Test**: salvar um perfil (aviso de sucesso), provocar um conflito de versão (alerta
com "Recarregar") e reverter uma versão (diálogo de confirmação).

**Acceptance Scenarios**:

1. **Given** uma ação concluída, **When** ela termina, **Then** aparece um aviso breve de sucesso.
2. **Given** um erro da API, **When** ele ocorre, **Then** a mensagem da API aparece num alerta de
   erro.

---

### Edge Cases

- Tela muito estreita (360 px): tabelas rolam na horizontal dentro do cartão, e a página não rola
  para o lado.
- Nomes longos no menu ou na trilha: truncados com reticências e texto completo no título.
- Sem JavaScript de terceiros: fontes e ícones servidos da própria origem.
- Modo casa (build de produção e PWA): o visual novo funciona sob a CSP da constitution 2.0.0.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Todas as telas logadas DEVEM usar o mesmo painel (menu lateral, barra superior,
  conteúdo e rodapé), com menu responsivo (fixo em tela larga, gaveta em tela estreita).
- **FR-002**: O menu DEVE respeitar o papel (Usuários e Segurança só para o dono) e destacar o item
  ativo.
- **FR-003**: As listas de Perfis, Usuários e Eventos de segurança DEVEM ter ordenação, filtro por
  texto, paginação (10, 25 ou 50 por página) e estados de carregando e vazio.
- **FR-004**: As telas de acesso DEVEM usar o novo visual sem mudar os textos, as mensagens e os
  fluxos atuais (os e2e existentes continuam válidos).
- **FR-005**: Sucessos DEVEM aparecer como avisos breves; erros, como alertas com a mensagem da
  API; confirmações, como diálogo.
- **FR-006**: A tela Início DEVE mostrar cartões de métrica com os números reais disponíveis
  (perfis ativos, contas ativas por plataforma, usuários ativos) e os eventos de segurança
  recentes (para o dono).
- **FR-007**: Fontes e ícones DEVEM ser servidos da própria origem; nenhuma origem externa entra
  na CSP.
- **FR-008**: A CSP de produção DEVE ser a da constitution 2.0.0: `script-src` estrito e
  `style-src` com `'unsafe-inline'`, idêntica no build e no edge.
- **FR-009**: Os campos de formulário continuam acessíveis: rótulos associados e seletores nativos
  onde já existem.

### Key Entities

Nenhuma entidade de dados nova. A tela Início reaproveita as consultas existentes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das telas logadas usam o painel novo, sem sobras do visual antigo.
- **SC-002**: Os e2e existentes (dev e PWA) passam sem mudar o que verificam. Seletores podem se
  adaptar, mas textos e fluxos não mudam.
- **SC-003**: A 390 px de largura, nenhuma tela rola na horizontal.
- **SC-004**: No modo casa (build de produção), nenhuma violação de CSP aparece no console ao
  navegar por todas as telas.
- **SC-005**: A tela Início abre em menos de 1 s na rede de casa.

## Assumptions

- Referência visual apenas: nada de código, imagem ou marca da Creative Tim.
- A paleta do SociMan (tokens do tema) é própria: primária azul-índigo e cores de estado. O modo
  escuro fica para depois.
- Gráficos (charts) ficam fora desta spec, porque ainda não há séries de dados. Os cartões de
  métrica usam números.
- O conteúdo das telas (campos, regras) não muda; só o visual e os componentes.
