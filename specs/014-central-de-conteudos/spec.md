# Feature Specification: Central de conteúdos, aprovação e agendamento (014-central-de-conteudos)

**Feature Branch**: `014-central-de-conteudos`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Senti falta de agendar direto no clipe pronto e de uma lista com todos os
vídeos disponíveis, pendentes etc., não só dos cortes, mas também dos futuros (avatar, afiliado,
vídeos próprios), para buscar o que está agendado, ainda não agendado, aprovado… e facilitar a
gestão de várias contas e de vários vídeos por conta. Quero poder agendar: só a criação de
rascunhos; posts aprovados criados e publicados automaticamente; ou rascunho criado antes e
publicado na hora."

## Clarifications

### Session 2026-09-29

- Q: Uma spec ou duas? → A: Duas. Esta (014) cobre a central de conteúdos, a aprovação e o
  agendamento; a execução na rede (rascunho no TikTok) é a 015, depois da emenda do princípio I.
- Q: Existe o passo "aprovado"? → A: Sim, separado de agendar. Aprovar = "este conteúdo pode ir
  para a conta X". Donos aprovam; membros pedem aprovação.
- Q: Quais modos de agendamento? → A: Quatro: lembrete manual; criar rascunho na rede no horário;
  publicar no horário; criar rascunho antes e publicar no horário. Cada conta mostra só os modos que
  a rede dela oferece, com o motivo dos indisponíveis. Nesta spec só o lembrete manual executa.
- Q: Quem conecta contas e envia para as redes? → A: Só donos (vale para a 015 em diante).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver tudo o que pode ser publicado, num lugar só (Priority: P1)

O usuário abre **Conteúdos** e vê todos os vídeos publicáveis de todos os perfis: hoje os cortes
(em revisão e prontos); no futuro, vídeos de avatar/afiliado e vídeos próprios enviados. Cada linha
mostra miniatura, título, perfil, origem, duração e, **por conta de destino**, o estado na esteira:

`em revisão → pronto → aprovado → agendado → rascunho criado / publicado`, além de `falhou` e
`arquivado`.

Ele filtra por perfil, conta, rede, estado, origem e período, busca por texto e usa atalhos:
"Prontos sem agendamento", "Aprovados sem data", "Agendados hoje", "Esta semana", "Falharam".

**Why this priority**: é o pedido central: gerenciar várias contas e vários vídeos por conta sem
abrir envio por envio.

**Independent Test**: com os 43 cortes reais do dev (36 em revisão, 7 prontos) em 2 perfis, abrir
Conteúdos, filtrar "A Taverna Nerd · prontos sem agendamento" e ver exatamente os prontos daquele
perfil que ainda não têm postagem agendada.

**Acceptance Scenarios**:

1. **Given** cortes de vários perfis, **When** o usuário abre Conteúdos, **Then** vê todos numa lista
   paginada, com estado por conta de destino, ordenada pelos mais recentes.
2. **Given** a lista, **When** ele combina filtros (perfil, conta, estado, período) e busca, **Then** vê
   só os itens correspondentes, e os filtros ficam na URL (dá para voltar e compartilhar o link).
3. **Given** um atalho ("Agendados hoje"), **When** clicado, **Then** a lista mostra só aquele recorte
   com a contagem.
4. **Given** um item, **When** o usuário clica, **Then** abre o detalhe com o player, os textos por conta,
   o histórico e as ações disponíveis.
5. **Given** um conteúdo sem conta de destino definida, **When** listado, **Then** aparece como "sem
   conta" e pode receber uma ou mais contas.

---

### User Story 2 - Aprovar para uma conta (Priority: P1)

Num conteúdo pronto, o usuário escolhe as contas de destino (ex.: TikTok @atavernanerd). Um **dono**
aprova ("pode ir para esta conta"); um **membro** pede aprovação, e os donos são avisados no sino.
Aprovação e pedido ficam no histórico. Aprovar vários de uma vez é possível pela seleção em lote.

**Why this priority**: separa "está bom para publicar" de "quando publicar", o que permite montar uma
fila de aprovados e agendar depois.

**Independent Test**: um membro pede aprovação de 3 cortes para a conta TikTok da Taverna; um dono
recebe o aviso, aprova 2 e recusa 1 com motivo; a lista reflete os estados e o histórico mostra quem
fez o quê.

**Acceptance Scenarios**:

1. **Given** um conteúdo pronto e uma conta, **When** um dono aprova, **Then** o estado para aquela
   conta vira `aprovado`, com autor e data no histórico.
2. **Given** um membro, **When** ele tenta aprovar, **Then** a ação disponível é "Pedir aprovação", e
   os donos recebem o aviso.
3. **Given** um pedido de aprovação, **When** um dono recusa, **Then** informa um motivo e o conteúdo
   volta a `pronto` para aquela conta, com o motivo visível.
4. **Given** um conteúdo ainda em revisão (sem marca aplicada), **When** alguém tenta aprovar, **Then**
   é recusado com "Aplique a marca antes de aprovar".
5. **Given** vários selecionados, **When** um dono aprova em lote, **Then** todos os elegíveis viram
   `aprovado` e os não elegíveis aparecem listados com o motivo.

---

### User Story 3 - Agendar com o modo certo (Priority: P1)

Num conteúdo aprovado (ou direto no corte pronto, que passa pela aprovação no mesmo passo quando
quem agenda é dono), o usuário clica em **Agendar**: escolhe conta, data e hora, confere ou gera os
textos (assistente de IA da 008) e escolhe o **modo**:

1. **Lembrete manual**: no horário, o SociMan avisa "Hora de postar" e o humano posta (é o que
   existe hoje).
2. **Criar rascunho no horário**: no horário, o SociMan cria o rascunho na conta; o humano finaliza no
   app da rede.
3. **Publicar no horário**: no horário, o SociMan publica o post aprovado.
4. **Rascunho antes, publicar no horário**: o rascunho é criado ao agendar (ou numa antecedência
   escolhida) e publicado no horário.

A tela mostra **só os modos que aquela conta oferece**, e os indisponíveis aparecem desabilitados com
o motivo (ex.: "TikTok: a rede não permite publicar um rascunho pela API"; "conta não conectada";
"aguardando a spec de integração"). Nesta spec, só o **lembrete manual** executa.

**Why this priority**: é o "agendar direto no clipe" pedido pelo dono, já com o modelo pronto para os
modos automáticos das próximas specs.

**Independent Test**: num corte pronto, clicar em Agendar, escolher TikTok @atavernanerd, amanhã
19h, gerar os textos com a IA e o modo "Lembrete manual"; ver o item em "Agendados" no calendário e
na lista, e os modos 2–4 desabilitados com o motivo.

**Acceptance Scenarios**:

1. **Given** um corte pronto, **When** um dono clica em Agendar e confirma, **Then** o conteúdo fica
   aprovado e agendado para a conta, com modo, data e textos.
2. **Given** a escolha do modo, **When** a conta não oferece um modo, **Then** ele aparece desabilitado
   com o motivo e não pode ser escolhido.
3. **Given** um agendamento em lembrete manual, **When** chega o horário, **Then** os donos e o autor
   recebem "Hora de postar" (como na 006), e o item vai para "a postar" até alguém marcar
   "Postado" (com link opcional).
4. **Given** um agendamento, **When** o usuário reagenda (data, hora, modo) ou cancela, **Then** a
   mudança fica no histórico e o calendário atualiza.
5. **Given** um horário no passado ou um conteúdo não aprovado para aquela conta, **When** o usuário
   tenta agendar, **Then** é recusado com a razão.
6. **Given** o mesmo conteúdo, **When** agendado para duas contas, **Then** cada conta tem seu
   agendamento, modo e textos independentes.

---

### User Story 4 - Agendar em lote e em sequência (Priority: P2)

O usuário seleciona vários conteúdos aprovados e escolhe **Agendar em sequência**: conta, primeira
data, cadência (ex.: 1 por dia às 19h, ou 2 por dia às 12h e 19h), modo e se os textos devem ser
gerados pela IA para os que não têm. A prévia mostra o calendário resultante antes de confirmar.
Horários que conflitam com agendamentos existentes da mesma conta são pulados.

**Why this priority**: acelera muito a operação com dezenas de cortes, mas o agendamento individual já
resolve o essencial.

**Independent Test**: selecionar 7 cortes aprovados da Taverna, "1 por dia às 19h a partir de amanhã",
ver a prévia com 7 dias, confirmar e ver os 7 no calendário, um por dia.

**Acceptance Scenarios**:

1. **Given** N conteúdos e uma cadência, **When** o usuário pede a prévia, **Then** vê a data de cada
   um e os que foram pulados por conflito, antes de confirmar.
2. **Given** a prévia confirmada, **When** aplicada, **Then** todos ficam agendados de uma vez, e uma
   falha em um item não desfaz os outros (o que falhou aparece com o motivo).
3. **Given** agendamentos em sequência, **When** o usuário reordena na lista ou arrasta no calendário,
   **Then** as datas mudam só dos itens mexidos.

---

### User Story 5 - Conteúdos de outras origens (Priority: P3)

O usuário envia um vídeo próprio já pronto (arquivo) para um perfil, e ele entra em Conteúdos como
origem "vídeo próprio", pronto para aprovar e agendar como um corte. A lista já mostra a origem de
cada item (corte, vídeo próprio e, no futuro, avatar/afiliado), e o filtro por origem funciona.

**Why this priority**: prepara a central para os vídeos de avatar/afiliado sem esperar a spec deles.

**Independent Test**: enviar um MP4 vertical como vídeo próprio da Queridinhos, vê-lo em Conteúdos
com a origem "vídeo próprio", aprovar e agendar em lembrete manual.

**Acceptance Scenarios**:

1. **Given** um arquivo de vídeo válido, **When** enviado como vídeo próprio, **Then** entra em
   Conteúdos como `pronto` para o perfil escolhido, com título editável.
2. **Given** a lista, **When** filtrada por origem, **Then** mostra só os itens daquela origem.

---

### Edge Cases

- Conteúdo arquivado com agendamento ativo: arquivar cancela os agendamentos (com aviso e histórico).
- Conta de destino arquivada ou desativada: os agendamentos dela ficam em "atenção" com o motivo e não
  executam.
- Duas pessoas reagendando o mesmo item: conflito de versão com o aviso de sempre.
- Corte refeito (nova aplicação de marca) depois de aprovado: a aprovação continua, mas o detalhe
  avisa "o vídeo mudou desde a aprovação".
- Agendamento em lembrete manual não marcado como "Postado" 24 h depois: vira "atrasado" nos atalhos.
- Centenas de conteúdos: a lista pagina e os filtros respondem rápido.
- Fuso: datas e horas sempre no horário de São Paulo, como no calendário da 006.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O SociMan DEVE ter a tela **Conteúdos**, que lista todo vídeo publicável de todos os
  perfis, com miniatura, título, perfil, origem, duração e o estado por conta de destino.
- **FR-002**: O **estado por conta** DEVE seguir a esteira `em_revisao → pronto → aprovado → agendado →
  rascunho_criado | publicado`, mais `a_postar` (lembrete vencido), `atrasado`, `falhou` e `arquivado`.
  Mudanças do sistema e humanas ficam no histórico.
- **FR-003**: A lista DEVE ter filtros (perfil, conta, rede, estado, origem, período), busca por texto,
  atalhos (prontos sem agendamento, aprovados sem data, agendados hoje, esta semana, atrasados,
  falharam) e paginação; os filtros ficam na URL.
- **FR-004**: **Aprovar** um conteúdo para uma conta DEVE ser ação de dono; membro DEVE poder **pedir
  aprovação** (com aviso aos donos). Recusar DEVE exigir motivo. Só conteúdo `pronto` (marca aplicada)
  pode ser aprovado.
- **FR-005**: **Agendar** DEVE registrar conta, data e hora, textos e **modo** (`lembrete`,
  `criar_rascunho`, `publicar`, `rascunho_e_publicar`, com a antecedência do rascunho no último).
  Agendar direto num conteúdo pronto, por um dono, aprova e agenda no mesmo passo.
- **FR-006**: Cada conta DEVE expor os **modos disponíveis** e o motivo dos indisponíveis, de acordo
  com as capacidades da rede e o estado da conexão. Nesta spec, só `lembrete` está disponível.
- **FR-007**: O modo `lembrete` DEVE avisar "Hora de postar" no horário e deixar o item "a postar" até
  alguém marcar "Postado" (com link opcional); depois de 24 h vira "atrasado".
- **FR-008**: DEVE ser possível reagendar, trocar o modo e cancelar, individualmente e em lote, com
  histórico e reversão pelo dono.
- **FR-009**: **Agendar em sequência** DEVE aceitar conta, primeira data, cadência (N por dia em
  horários fixos), modo e geração de textos pela IA para os que não têm; DEVE mostrar a prévia antes
  de confirmar e pular horários que conflitam com a mesma conta.
- **FR-010**: O **agendar direto** DEVE existir no corte pronto (detalhe do corte e lista de cortes do
  perfil), no detalhe do conteúdo e na lista de Conteúdos.
- **FR-011**: O modelo de conteúdo DEVE aceitar origens diferentes (corte, vídeo próprio e, no futuro,
  avatar/afiliado), e esta spec DEVE permitir enviar **vídeo próprio** pronto para um perfil.
- **FR-012**: O calendário (006) DEVE mostrar os agendamentos com o modo e o estado, e continuar
  permitindo arrastar para reagendar.
- **FR-013**: Nada nesta spec publica nem envia conteúdo para rede social (princípio I); os modos
  automáticos ficam registrados e visíveis, mas só executam quando uma spec de integração (015+) e a
  emenda da constitution os liberarem.

### Key Entities

- **Conteúdo**: vídeo publicável de um perfil. Origem (corte, vídeo próprio, futuramente avatar e
  afiliado), título, duração, miniatura, arquivo final, estado geral e histórico.
- **Destino** (conteúdo × conta): estado na esteira para aquela conta, aprovação (quem, quando,
  motivo de recusa), pedidos de aprovação. Evolui a Postagem da 006, que já é uma por corte e conta.
- **Agendamento**: data e hora, modo, antecedência do rascunho, textos, autor, estado de execução,
  resultado (link, motivo de falha).
- **Capacidade de rede**: para cada rede (e conta), quais modos existem e por quê não quando
  indisponíveis.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono responde "o que está agendado esta semana em cada conta" e "quais prontos ainda
  não têm data" em menos de 30 segundos cada, a partir da tela Conteúdos.
- **SC-002**: Agendar um corte pronto (conta, data, textos com IA e modo) leva menos de 1 minuto.
- **SC-003**: Agendar 10 conteúdos em sequência (1 por dia) leva menos de 2 minutos, com prévia.
- **SC-004**: 100% das aprovações, recusas, agendamentos, reagendamentos e cancelamentos aparecem no
  histórico com autor e data.
- **SC-005**: 0 publicações ou envios a redes sociais nesta spec (verificado por teste).
- **SC-006**: A lista com 500 conteúdos filtra e pagina sem espera perceptível (menos de 1 segundo
  para o usuário).

## Assumptions

- A Postagem da 006 (uma por corte e conta, com textos e data) é a base do destino e do agendamento;
  os dados existentes migram sem perda (postagens em rascunho viram destinos `pronto`/`aprovado`
  conforme o caso; `agendado` e `postado` mantêm o estado).
- Cortes em `revisao` aparecem como `em_revisao`; cortes com marca aplicada, como `pronto`.
- "Rascunho criado" e "publicado" automáticos, conexão de contas (OAuth) e o envio real ficam para a
  015 (TikTok) e seguintes; aqui só o modelo, as capacidades e o lembrete manual.
- Para o TikTok, a pesquisa de 2026-09-29 (`docs/pesquisa/publicacao-redes.md`) indica que "criar
  rascunho" é viável; "publicar" só sai privado sem auditoria; "rascunho e publicar" não existe na API.
  As capacidades da 015 refletirão isso.
- O vídeo próprio segue os limites de upload da 004/006 (formato vertical recomendado, até 2 GB).
- Aprovação e agendamento são por conta; um conteúdo pode ir para várias contas.
