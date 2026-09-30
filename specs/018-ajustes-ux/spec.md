# Feature Specification: Ajustes de UX (018-ajustes-ux)

**Feature Branch**: `018-ajustes-ux`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "1) Toda a aplicação em dark mode (conteúdo, fundo e menu da esquerda); o layout
continua. 2) Na página do post: no topo, aprovar/desaprovar e arquivar; as contas em destaque na coluna da
esquerda, em vermelho como obrigatório; agendamento e envio ficam no bloco de cada conta. 3) Trocar o nome
OpenShorts por SociShorts em todos os lugares."

## Clarifications

### Session 2026-09-30

- Q: Só dark ou com opção? → A: Dark por **padrão** em todo o app (inclusive login e PWA), com um seletor
  "Tema: escuro / claro / do sistema" no menu da conta (preferência guardada no aparelho).
- Q: Aprovar/desaprovar no topo vale para quê? → A: Para **todas as contas do post**: "Aprovar" aprova as que
  estão prontas (dono); "Desaprovar" volta as aprovadas a "pronto" e cancela agendamentos, com confirmação.
  Ações por conta continuam no bloco da conta.
- Q: Onde muda o nome? → A: Em todo texto visível (telas, avisos, sino, ajuda, capturas do e2e). Nomes técnicos
  (variáveis, código, endereço do serviço, contrato) não mudam.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dark mode (Priority: P1)
O app abre em tema escuro: menu da esquerda, barra do topo, conteúdo, cartões, tabelas, diálogos, gráficos,
login e tela de "sem conexão". Contraste AA; badges e estados continuam distinguíveis. O seletor de tema no
menu da conta permite escuro, claro ou do sistema.

**Independent Test**: abrir Conteúdos, detalhe de um post, Métricas, Calendário e o login; tudo escuro, legível,
sem blocos brancos; trocar para claro e voltar.

### User Story 2 - Página do post centrada nas contas (Priority: P1)
No detalhe do conteúdo:
- **Topo**: Aprovar, Desaprovar, Arquivar (só dono aprova/desaprova; membro vê "Pedir aprovação").
- **Coluna da esquerda — Contas**: bloco em destaque; sem nenhuma conta, borda e aviso vermelhos
  "Obrigatório: escolha ao menos uma conta para este post". Cada conta mostra status, legenda/textos e as ações
  Agendar, Enviar rascunho agora e Publicar agora (conforme os modos da conta).
- **Coluna da direita**: player, proposta do SociShorts, desempenho, histórico.

**Independent Test**: abrir um post sem conta (bloco vermelho), adicionar a conta TikTok, aprovar pelo topo,
agendar pelo bloco da conta; desaprovar pelo topo e ver o agendamento cancelado após confirmar.

### User Story 3 - SociShorts (Priority: P2)
Todo texto visível que diz "OpenShorts" passa a dizer "SociShorts".

**Independent Test**: buscar "OpenShorts" na interface (telas, sino, ajuda) e não encontrar.

## Requirements *(mandatory)*
- **FR-001**: O app DEVE abrir em tema escuro por padrão, em todas as telas, com seletor escuro/claro/sistema.
- **FR-002**: O detalhe do conteúdo DEVE ter no topo Aprovar, Desaprovar e Arquivar, valendo para todas as
  contas do post; Desaprovar volta aprovados a "pronto" e cancela agendamentos, com confirmação e histórico.
- **FR-003**: O bloco Contas DEVE ficar na coluna da esquerda, em destaque, e em vermelho com aviso de
  obrigatório quando o post não tem conta; agendar e enviar ficam dentro do bloco de cada conta.
- **FR-004**: Todo texto visível DEVE usar "SociShorts" no lugar de "OpenShorts".
- **FR-005**: Nada muda nas regras de publicação (princípio I) nem nas permissões (dono aprova).

## Success Criteria *(mandatory)*
- **SC-001**: 0 telas com fundo claro no tema escuro (verificado no e2e com capturas).
- **SC-002**: Aprovar e agendar um post numa conta leva no máximo 3 cliques a partir do detalhe.
- **SC-003**: 0 ocorrências de "OpenShorts" em textos visíveis.

## Assumptions
- Tokens de cor do tema (Tailwind/shadcn) já existem; o dark mode é ativar e ajustar, sem redesenho.
- "Desaprovar" é uma ação nova da API (revogar aprovação), só para dono humano, com histórico; não apaga nada.
