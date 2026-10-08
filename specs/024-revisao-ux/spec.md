# Feature Specification: Revisão de UX tela a tela (024-revisao-ux)

**Feature Branch**: `024-revisao-ux`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Revisão de UX do SPA do SociMan: layout conciso e alinhado, menu agrupado e
ajustes de telas. Fontes: docs/handoffs/2026-10-06-revisao-ux.md e o critique do impeccable
(.impeccable/critique/2026-10-07T02-14-59Z__apps-web-src-pages.md, nota 24/40). Pedidos: (1) menu agrupado e
colapsável; (2) perfil sem a aba Cortes e Aprendizado como página própria sob Analytics; (3) Descobrir com
tema e motivo da pontuação; (4) Gerações com contagem de clipes aceitos, arquivados, pendentes e com falha;
(5) Conteúdos com paginação numerada; (6) Propostas com estado vazio explicativo; (7) UX geral com todos os
achados do critique (espaçamento, cartão, larguras, filtros, Perfil, atalhos, Agentes e menores). Sem mudar
regras de negócio, permissões nem a constitution; API só aditiva."

## Contexto

O SociMan já tem todas as telas, mas o dono acha o layout pouco conciso e desalinhado. A análise de
2026-10-06 (critique do impeccable com medição no navegador, nota 24/40) achou a causa principal: o espaço
entre blocos é definido dentro do cartão com faixa colorida, e não pela página. Por isso, a faixa encosta
(0 px) no bloco de cima em Agentes e Propostas, fica a 8 px das abas em Gerar cortes e deixa de 16 a 68 px
vazios dentro do cartão. Somam-se larguras soltas (um cartão de 672 px sobre outro de 1569 px), dois
"dialetos" de cartão, cinco padrões de filtro e um menu de 16 itens planos. Esta spec reorganiza a
navegação, ajusta seis telas e cria um sistema único de espaçamento, cartão, largura e filtros.

**Decisões do dono já tomadas (2026-10-06):** spec própria; o conteúdo exclusivo da aba Cortes do perfil vai
para Conteúdos; grupos do menu colapsáveis com estado lembrado; tema e motivo na linha do Descobrir, mais o
diálogo completo; a faixa colorida dos cartões **fica**, mas é consertada e só usa tons com significado; a
largura do conteúdo tem um limite único na área principal; todos os achados do critique entram.

## Clarifications

### Session 2026-10-07

- Q: A barra de filtros única vale só para as 4 telas ou para todas as listas com filtro? → A: Todas as listas com filtro do app.
- Q: Como fica a faixa neutra padrão dos cartões? → A: Na cor primária do SociMan nos dois temas, com texto claro; outros tons só para estado.
- Q: O que acontece com os atalhos zerados de Conteúdos? → A: Ficam escondidos; aparecem só os com contagem > 0, mais "Ver todos os atalhos"; sem nenhum, a linha "Nada pedindo ação agora".
- Q: O que conta como clipe "aceito" numa geração? → A: Clipe com a marca aplicada (saiu da revisão), sem depender da aprovação do destino.
- Q: Qual a largura máxima única do conteúdo? → A: 1440 px, centralizado.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Achar as telas por grupo no menu (Priority: P1)

O dono (ou o membro) abre o menu e vê poucos itens de primeiro nível. Os itens relacionados ficam em grupos
que abrem e fecham: **Cortes** (Canais-fonte, Descobrir, Gerar cortes), **Analytics** (Métricas,
Aprendizado, Importar da agência) e **Configurações** (Assistente de IA, Usuários, Segurança, Publicação
automática, Agentes (MCP)). Fora dos grupos ficam Início, Perfis, Conteúdos, Calendário, Propostas dos
agentes e Minha conta. O grupo da tela atual abre sozinho, e o que o usuário abriu ou fechou é lembrado no
mesmo aparelho.

**Why this priority**: o menu é usado em toda sessão. Com 16 itens planos, as configurações mensais competem
com o fluxo diário.

**Independent Test**: entrar como dono e como membro, abrir e fechar grupos, navegar e recarregar, no desktop
e no menu do celular.

**Acceptance Scenarios**:

1. **Given** o dono em Início, **When** abre o grupo Cortes e clica em Descobrir, **Then** a tela Descobrir
   abre, o item fica marcado como atual e o grupo Cortes continua aberto.
2. **Given** o dono fechou o grupo Configurações, **When** recarrega a página, **Then** o grupo continua
   fechado, salvo se a tela atual for de Configurações (aí ele abre).
3. **Given** um membro, **When** abre o menu, **Then** não vê os itens só do dono (Usuários, Segurança,
   Publicação automática, Agentes (MCP)); um grupo sem nenhum item visível não aparece.
4. **Given** há propostas abertas, **When** o menu é exibido, **Then** o contador continua no item Propostas
   dos agentes.
5. **Given** o celular (390 px), **When** o dono abre o menu lateral, **Then** os mesmos grupos aparecem,
   colapsáveis, e o menu fecha ao escolher uma tela.
6. **Given** a lembrança do navegador está indisponível (janela privada ou bloqueada), **When** o menu
   abre, **Then** funciona normalmente, só sem lembrar o estado.

---

### User Story 2 - Espaçamento, cartões e larguras consistentes (Priority: P1)

Em qualquer tela, os blocos ficam separados por um ritmo único, sem nada encostado e sem vazios dentro dos
cartões. Os cartões seguem um padrão só: a faixa colorida continua, mas sem invadir o bloco de cima, e o
tom indica estado (ex.: alerta, erro) em vez de decorar. No tema escuro, a faixa neutra deixa de virar um
bloco cinza-claro. O conteúdo tem uma largura máxima única, centralizada em telas grandes. Nenhum cartão
tem largura própria menor que a dos vizinhos, e a largura não "pula" entre páginas com e sem barra de
rolagem.

**Why this priority**: é a queixa central do dono, e a causa é única (sistêmica). Corrigida no padrão, todas
as telas melhoram juntas.

**Independent Test**: medir, em 1280 e 390 px, o espaço entre blocos consecutivos e a largura dos blocos nas
telas listadas em SC-002, nos temas claro e escuro.

**Acceptance Scenarios**:

1. **Given** a tela Agentes (MCP), **When** é exibida, **Then** o cartão do interruptor e o cartão dos
   agentes conectados têm a mesma largura, e o espaço entre eles é igual ao das outras telas.
2. **Given** qualquer página com abas, **When** é exibida, **Then** o espaço entre as abas e o primeiro
   cartão é o mesmo em todas as páginas.
3. **Given** um cartão com faixa, **When** é exibido, **Then** não há área vazia entre a faixa e o conteúdo
   maior que o espaço interno padrão.
4. **Given** uma tela larga (1920 px), **When** qualquer página é exibida, **Then** o conteúdo tem no máximo
   1440 px de largura e fica centralizado.
5. **Given** o tema escuro, **When** um cartão de tom padrão é exibido, **Then** a faixa tem a cor primária
   do SociMan, com texto legível, e não um bloco cinza-claro.

---

### User Story 3 - Perfil enxuto e Aprendizado como página própria (Priority: P2)

O perfil perde a aba Cortes (Padrões de corte continua). As peças exclusivas dessa aba vão para Conteúdos:
"Aplicar marca num corte" (envio de arquivo) e o estado do HD de dados. A tabela de cortes do perfil deixa
de existir, porque Conteúdos já lista os cortes por perfil, com filtro de arquivados. O Aprendizado sai do
perfil e vira uma página no grupo Analytics, com seletor de perfil. Os endereços antigos continuam
funcionando por redirecionamento. Sem imagem de banner, o perfil mostra um cabeçalho compacto, e as abas
são usáveis no celular.

**Why this priority**: o perfil tem 10 abas e um banner vazio que empurra o conteúdo para baixo da dobra. O
Aprendizado é análise, e o lugar dele é Analytics.

**Independent Test**: abrir um perfil sem banner, conferir as abas; abrir Conteúdos e aplicar a marca num
arquivo; abrir Aprendizado pelo menu, trocar de perfil e abrir um link antigo.

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o dono o abre, **Then** não há aba Cortes, e a aba Padrões de corte
   continua com o mesmo comportamento.
2. **Given** um link antigo para a aba Cortes do perfil, **When** é aberto, **Then** leva a Conteúdos já
   filtrado por aquele perfil.
3. **Given** Conteúdos, **When** o dono usa "Aplicar marca num corte" para um perfil, **Then** o corte é
   criado como antes e aparece na lista.
4. **Given** o HD de dados indisponível, **When** o dono abre Conteúdos, **Then** vê o estado do HD e não
   consegue enviar arquivo, com a mesma mensagem de antes.
5. **Given** o menu Analytics › Aprendizado, **When** o dono o abre, **Then** escolhe o perfil (o último
   usado vem selecionado; se houver um perfil só, ele já vem escolhido) e vê as mesmas abas e filtros de
   antes.
6. **Given** um link antigo do aprendizado de um perfil com aba, conta e medida, **When** é aberto, **Then**
   a nova página abre com o mesmo perfil, aba, conta e medida.
7. **Given** um perfil sem banner, **When** é aberto, **Then** o cabeçalho ocupa no máximo a altura de uma
   linha de identificação (sem faixa vazia), e com banner continua como hoje.
8. **Given** o celular, **When** o perfil é aberto, **Then** todas as abas são alcançáveis, e há indicação
   visível de que existem mais abas.

---

### User Story 4 - Entender a pontuação no Descobrir (Priority: P2)

Na lista de vídeos recomendados, cada linha mostra o tema (assunto) que casou com o vídeo e um motivo curto
da pontuação. No diálogo "Por quê?", aparece a parcela de afinidade (até ±20 pontos) e todos os temas
casados, para a soma bater com a pontuação exibida. A escala das notas fica explícita.

**Why this priority**: o dono escolhe o que cortar por esta tela. Hoje a soma do diálogo não fecha quando há
afinidade, e o tema não aparece.

**Independent Test**: num perfil com temas e casamento em dia, abrir o Descobrir, conferir tema e motivo
numa linha e somar as parcelas do diálogo.

**Acceptance Scenarios**:

1. **Given** um vídeo com tema casado, **When** a lista é exibida, **Then** a linha mostra o nome do tema e
   o motivo resumido.
2. **Given** um vídeo com afinidade diferente de zero, **When** o dono abre "Por quê?", **Then** vê a
   parcela de afinidade, e a soma das parcelas é igual à pontuação exibida (com tolerância de arredondamento
   de 1 ponto).
3. **Given** um vídeo que casa com mais de um tema, **When** abre "Por quê?", **Then** vê todos os temas
   casados, com o que decidiu a afinidade destacado.
4. **Given** um perfil sem temas, ou com casamento desatualizado, **When** o Descobrir é exibido, **Then** a
   linha não mostra tema, e o diálogo explica que a afinidade está neutra e por quê.
5. **Given** a coluna Nota no diálogo, **When** é exibida, **Then** a escala fica clara (ex.: "de 0 a 1").

---

### User Story 5 - Ver o resultado de cada geração de cortes (Priority: P2)

Na aba Gerações, cada geração mostra, além do estado, quantos clipes foram **aceitos**, **pendentes** (em
revisão), **arquivados** e **com falha**.

**Why this priority**: hoje "Pronto: N clipes" não diz se ainda há trabalho de revisão naquela geração.

**Independent Test**: com uma geração que tem clipes em vários estados, conferir as contagens na lista e no
detalhe.

**Acceptance Scenarios**:

1. **Given** uma geração pronta com 6 clipes (3 com marca aplicada, 2 em revisão, 1 arquivado), **When** a
   lista é exibida, **Then** a linha mostra 3 aceitos, 2 pendentes e 1 arquivado.
2. **Given** um clipe com marca que falhou, **When** a lista é exibida, **Then** ele conta em "com falha", e
   não em aceitos.
3. **Given** uma geração ainda processando, **When** a lista é exibida, **Then** o estado de progresso
   continua como hoje, e as contagens aparecem quando houver clipes importados.
4. **Given** o dono arquiva um clipe no detalhe, **When** volta à lista, **Then** as contagens já refletem a
   mudança.

---

### User Story 6 - Paginar Conteúdos por número (Priority: P2)

Conteúdos troca "Carregar mais" por paginação numerada: o dono vê a página atual, o total de páginas e de
itens, vai para a anterior ou a próxima, e escolhe quantos itens por página. A página e o tamanho ficam no
endereço, para recarregar ou compartilhar sem perder o lugar.

**Why this priority**: com centenas de conteúdos, "Carregar mais" obriga a rolar desde o início e perde a
posição ao voltar do detalhe.

**Independent Test**: com mais de 2 páginas, navegar até a página 3, abrir um conteúdo, voltar e conferir
que continua na página 3; trocar o filtro e conferir que volta à página 1.

**Acceptance Scenarios**:

1. **Given** 120 conteúdos e 25 por página, **When** o dono abre Conteúdos, **Then** vê "Página 1 de 5" e o
   total de 120.
2. **Given** a página 3, **When** o dono abre um conteúdo e volta, **Then** continua na página 3, com os
   mesmos filtros.
3. **Given** a página 3, **When** muda um filtro, **Then** volta para a página 1.
4. **Given** um endereço com página além da última (ex.: depois de arquivar itens), **When** é aberto,
   **Then** mostra a última página existente.
5. **Given** a seleção em lote, **When** troca de página, **Then** a seleção é limpa, porque a seleção vale
   só para a página visível e nenhuma ação em lote age sobre itens que o dono não vê.

---

### User Story 7 - Filtros iguais em todas as listas (Priority: P3)

Todas as listas com filtro do app (entre elas Descobrir, Propostas, Conteúdos, Gerar cortes, Canais-fonte,
Calendário, Métricas, Segurança, Registro da IA, Registro do MCP, Cenas e Assets) usam a mesma barra de filtros, dentro do cartão da lista: os
filtros principais ficam visíveis (com rótulo), o resto vai para "Mais filtros", os filtros ativos aparecem
como etiquetas removíveis e a lista se atualiza ao mudar um filtro. Propostas perde a busca duplicada.

**Why this priority**: hoje há cinco padrões (com e sem rótulo, com e sem botão "Filtrar", dentro e fora do
cartão), o que obriga a reaprender cada tela.

**Independent Test**: em cada tela com filtro, aplicar e remover um filtro principal e um de "Mais
filtros", e conferir o endereço.

**Acceptance Scenarios**:

1. **Given** qualquer tela com filtro, **When** o dono muda um filtro, **Then** a lista se atualiza sem
   botão de aplicar, e o filtro vai para o endereço.
2. **Given** um filtro ativo dentro de "Mais filtros", **When** o painel está fechado, **Then** aparece uma
   etiqueta do filtro, com um botão para removê-lo, e o botão "Mais filtros" mostra quantos estão ativos.
3. **Given** Propostas, **When** o dono busca, **Then** há uma busca só, e ela vale para todas as propostas
   (não só as carregadas).
4. **Given** o celular, **When** o dono abre "Mais filtros", **Then** os filtros aparecem num painel de
   tela cheia ou lateral, sem rolagem horizontal.

---

### User Story 8 - Telas com estado vazio e ajustes pontuais (Priority: P3)

- **Propostas:** sem propostas, a tela explica o que são (sugestões dos agentes da agência que só valem
  depois que alguém aplica), que elas chegam quando os agentes do OpenClaw forem ligados ao SociMan, e, para
  o dono, leva à configuração de Agentes (MCP).
- **Agentes (MCP):** o interruptor vira uma faixa de estado compacta (ligado/desligado, servidor), o botão
  de criar fica no cabeçalho do cartão e "Clientes" passa a se chamar "Agentes conectados".
- **Conteúdos:** os atalhos mostram só os que pedem ação (com contagem maior que zero); os demais ficam em
  "Ver todos os atalhos".
- **Menores:** a barra fixa de selecionados do Descobrir alinha com o conteúdo; as datas aparecem no formato
  brasileiro (dd/mm/aaaa); o seletor de arquivo está em português; os estados vazios seguem um só padrão.

**Why this priority**: são melhorias de compreensão sem impacto em fluxo crítico.

**Independent Test**: abrir Propostas sem propostas (como dono e como membro), abrir Agentes e Conteúdos e
conferir cada item.

**Acceptance Scenarios**:

1. **Given** nenhuma proposta aberta, **When** o dono abre Propostas, **Then** vê a explicação e um link para
   Agentes (MCP); o membro vê a explicação sem o link.
2. **Given** filtros que não retornam nada em Propostas, **When** a lista fica vazia, **Then** a mensagem diz
   que nenhum item bate com os filtros e oferece limpá-los (diferente do vazio "nunca houve proposta").
3. **Given** Agentes (MCP) com o MCP ligado, **When** a tela abre, **Then** o estado cabe numa faixa só, e o
   aviso de desligado só aparece quando está desligado.
4. **Given** Conteúdos com 3 atalhos com contagem e 8 com zero, **When** a tela abre, **Then** só os 3
   aparecem, e "Ver todos os atalhos" mostra os 11.

---

### Edge Cases

- Usuário com um único perfil: o seletor do Aprendizado já vem com ele, e Conteúdos não pede perfil para
  "Aplicar marca num corte".
- Usuário sem nenhum perfil: Aprendizado e "Aplicar marca num corte" mostram o vazio com o caminho para
  criar um perfil.
- Link antigo de aprendizado com perfil inexistente ou arquivado: a nova página abre com o erro "perfil não
  encontrado", como hoje.
- Grupo do menu em que todos os itens são só do dono, para um membro: o grupo não aparece.
- O item atual está num grupo que o usuário tinha fechado: o grupo abre ao chegar na tela.
- Paginação com filtros que mudam o total enquanto o dono navega (ex.: um agendamento vence): a contagem é
  recalculada a cada página, e a página fora do intervalo vai para a última.
- Geração com clipes que mudaram de estado durante a importação: as contagens refletem o estado no momento
  da leitura.
- Vídeo-fonte com tema na lista de temas "cortar" (oculto por padrão): continua oculto; com "mostrar
  cortados", a linha mostra o tema com a indicação de cortado.
- Tela muito estreita (≤ 360 px): menu, barra de filtros, paginação e cabeçalho do perfil sem rolagem
  horizontal.
- Tema escuro e claro: as faixas e os selos mantêm contraste legível nos dois.

## Requirements *(mandatory)*

### Functional Requirements

**Navegação**

- **FR-001**: O menu principal MUST ter, nesta ordem: Início, Perfis, grupo Cortes (Canais-fonte, Descobrir,
  Gerar cortes), Conteúdos, Calendário, Propostas dos agentes, grupo Analytics (Métricas, Aprendizado,
  Importar da agência), grupo Configurações (Assistente de IA, Usuários, Segurança, Publicação automática,
  Agentes (MCP)) e Minha conta.
- **FR-002**: Os grupos MUST abrir e fechar por clique ou teclado, com estado acessível (aberto/fechado)
  anunciado a leitores de tela.
- **FR-003**: O estado aberto/fechado de cada grupo MUST ser lembrado por aparelho/navegador. Sem
  lembrança disponível, o menu MUST funcionar com os grupos no estado padrão.
- **FR-004**: O grupo que contém a tela atual MUST abrir automaticamente.
- **FR-005**: Os itens só do dono MUST continuar escondidos para o membro, e um grupo sem itens visíveis
  MUST não ser exibido.
- **FR-006**: O contador de propostas MUST continuar no item Propostas dos agentes. Com o grupo fechado, não
  há item com contador escondido (Propostas fica fora de grupo).
- **FR-007**: O menu do celular MUST ter a mesma estrutura e fechar ao escolher uma tela.

**Perfil e Aprendizado**

- **FR-008**: A aba Cortes MUST ser removida do perfil. O endereço antigo da aba MUST redirecionar para
  Conteúdos filtrado pelo perfil.
- **FR-009**: Conteúdos MUST oferecer "Aplicar marca num corte" (escolher perfil e arquivo, com as mesmas
  validações e limites de hoje) e mostrar o estado do HD de dados, bloqueando o envio quando o HD estiver
  indisponível.
- **FR-010**: O Aprendizado MUST ser uma página do grupo Analytics, com seletor de perfil e as mesmas abas,
  filtros (conta, medida) e permissões de hoje.
- **FR-011**: Todo endereço antigo do aprendizado de um perfil MUST redirecionar para a nova página,
  preservando perfil, aba, conta e medida. Os links internos (perfil, "O que funciona", detalhe do vídeo,
  avisos) MUST apontar para o novo endereço.
- **FR-012**: O seletor do Aprendizado MUST lembrar o último perfil escolhido e pré-selecionar o perfil
  quando houver um só.
- **FR-013**: Sem imagem de banner, o perfil MUST exibir um cabeçalho compacto, sem área vazia decorativa.
- **FR-014**: No celular, todas as abas do perfil MUST ser alcançáveis, com indicação visível de que há mais
  abas além das exibidas.

**Descobrir**

- **FR-015**: Cada linha de vídeo recomendado MUST mostrar o tema casado (quando houver) e o motivo resumido
  da pontuação.
- **FR-016**: O diálogo "Por quê?" MUST mostrar a parcela de afinidade, todos os temas casados (com o que
  decidiu a afinidade destacado) e a escala das notas. A soma das parcelas MUST bater com a pontuação
  exibida (tolerância de 1 ponto por arredondamento).
- **FR-017**: Sem afinidade disponível (sem temas, casamento desatualizado ou tudo neutro), o diálogo MUST
  dizer que a afinidade está neutra e o motivo.

**Gerações**

- **FR-018**: Cada geração MUST expor e exibir as contagens de clipes: aceitos (não arquivados, com marca
  aplicada ou em aplicação; a aprovação do destino não entra), pendentes (em revisão, não arquivados), arquivados e com falha (não
  arquivados).
- **FR-019**: As contagens MUST aparecer na lista de Gerações e no detalhe, e refletir mudanças de estado
  na próxima leitura.

**Conteúdos**

- **FR-020**: Conteúdos MUST ter paginação numerada com página atual, total de páginas, total de itens,
  anterior/próxima e escolha do tamanho (10, 25, 50). O padrão MUST ser 25.
- **FR-021**: Página e tamanho MUST ficar no endereço. Mudar qualquer filtro ou a ordenação MUST voltar à
  página 1. Página fora do intervalo MUST mostrar a última página existente.
- **FR-022**: A seleção em lote MUST deixar claro sobre quais itens a ação vai agir.
- **FR-023**: Os atalhos de Conteúdos MUST mostrar só os que têm contagem maior que zero, mais um "Ver todos
  os atalhos" que abre a lista completa. Sem nenhum atalho com contagem, MUST aparecer a linha "Nada pedindo
  ação agora". Um atalho ativo (no endereço) MUST continuar visível mesmo com zero.

**Propostas e Agentes**

- **FR-024**: Propostas MUST ter dois estados vazios distintos: "nunca chegou proposta" (explica o que são e
  como chegam; para o dono, link para Agentes (MCP)) e "nada com estes filtros" (oferece limpar os filtros).
- **FR-025**: Propostas MUST ter uma única busca, válida para todas as propostas.
- **FR-026**: Agentes (MCP) MUST mostrar o interruptor como uma faixa de estado compacta. O aviso de
  desligado só aparece quando estiver desligado, e a ação de criar fica no cabeçalho do cartão.
- **FR-027**: O rótulo "Clientes" MUST passar a "Agentes conectados" na tela de Agentes (MCP).

**Sistema de layout (todas as telas do app)**

- **FR-028**: O espaço vertical entre blocos de uma página MUST ser definido pela página, com um valor único
  em todas as telas. Nenhum cartão MUST adicionar margem externa própria.
- **FR-029**: O espaço entre abas e o conteúdo da aba MUST ser o mesmo valor em todas as telas com abas.
- **FR-030**: Deve haver um padrão único de cartão, com espaçamento interno único. A faixa colorida MUST
  ficar no fluxo normal (sem invadir o bloco de cima nem deixar vazio abaixo).
- **FR-031**: O tom da faixa MUST ter significado: o padrão é a cor primária do SociMan, igual nos temas claro
  e escuro, com texto claro de contraste adequado (nunca um bloco cinza-claro); alerta, erro e sucesso só
  para estado.
- **FR-032**: A área de conteúdo MUST ter uma largura máxima única de 1440 px, centralizada em telas grandes. Nenhum
  cartão MUST ter largura máxima própria que o desalinhe dos vizinhos.
- **FR-033**: A largura útil MUST não mudar entre páginas com e sem barra de rolagem.
- **FR-034**: Toda lista com filtro do app MUST usar a mesma barra de filtros, dentro do
  cartão da lista: principais visíveis e rotulados, o resto em "Mais filtros" com a contagem de ativos,
  etiquetas removíveis dos filtros ativos, aplicação imediata e estado no endereço.
- **FR-035**: Elementos fixos (como a barra de selecionados do Descobrir) MUST alinhar com as bordas do
  conteúdo.
- **FR-036**: Datas exibidas e campos de data MUST usar o formato brasileiro (dd/mm/aaaa), e os campos de
  arquivo MUST ter texto em português.
- **FR-037**: Os estados vazios de listas MUST seguir um padrão único (mensagem, explicação opcional e ação
  opcional).
- **FR-038**: Nenhuma tela MUST ter rolagem horizontal da página em 360 px ou mais.

**Restrições**

- **FR-039**: Esta spec MUST NOT mudar regras de negócio, permissões, o que o MCP pode fazer, nem a
  constitution. Mudanças na API MUST ser só aditivas (campos novos e parâmetros opcionais), e toda rota ou
  parâmetro novo MUST ser classificado no mapa do MCP.
- **FR-040**: Os endereços antigos (aba Cortes do perfil e aprendizado do perfil) MUST continuar funcionando
  por redirecionamento.

### Key Entities

- **Grupo do menu**: rótulo, itens, estado aberto/fechado lembrado por aparelho. Não é dado do servidor.
- **Contagem de clipes da geração**: aceitos, pendentes, arquivados e com falha, derivados do estado de cada
  corte da geração no momento da leitura. Nada é gravado.
- **Explicação da pontuação**: parcelas da pontuação (as quatro de hoje mais a afinidade), temas casados do
  vídeo-fonte para o perfil e o motivo resumido. Calculada na leitura.
- **Página de Conteúdos**: número da página, tamanho e total, com os mesmos filtros de hoje.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O menu de primeiro nível tem no máximo 9 entradas visíveis com os grupos fechados (hoje: 16).
- **SC-002**: Em Agentes (MCP), Propostas, Gerar cortes, Conteúdos, Descobrir e Perfil, medidos em 1280 e
  390 px, o espaço entre blocos consecutivos varia no máximo 4 px entre as telas, e nenhum bloco encosta no
  outro (0 px).
- **SC-003**: Dentro de um cartão, a distância entre a faixa e o primeiro conteúdo é no máximo o espaçamento
  interno padrão (hoje há até 68 px).
- **SC-004**: Em 1280 px, todos os cartões empilhados de uma página têm a mesma largura (diferença zero).
- **SC-005**: No Descobrir, em 100% dos vídeos com afinidade, a soma das parcelas do diálogo bate com a
  pontuação exibida (±1).
- **SC-006**: Na lista de Gerações, o dono identifica se uma geração ainda tem clipes pendentes sem abrir o
  detalhe.
- **SC-007**: Ao voltar do detalhe de um conteúdo, o dono está na mesma página e com os mesmos filtros em
  100% dos casos.
- **SC-008**: No celular (390 px), o primeiro conteúdo da lista de Conteúdos aparece com no máximo 1,5 tela
  de rolagem (hoje: cerca de 3 telas).
- **SC-009**: A revisão final do impeccable (critique) dá nota maior ou igual a 30/40, sem P0, nas mesmas
  telas.
- **SC-010**: Todos os testes automatizados existentes (API, e2e e PWA) continuam passando, e os endereços
  antigos continuam abrindo a tela certa.

## Assumptions

- "Aceito" = clipe com a marca aplicada ou em aplicação (`na_fila`, `processando`, `pronto`), não arquivado.
  "Com falha" é contado à parte. Pendente = em revisão e não arquivado. Arquivado vale para qualquer estado.
- A paginação numerada de Conteúdos usa o total que a lista já calcula. O modo antigo por cursor continua
  aceito (para o MCP e quem já o usa).
- O Aprendizado continua por perfil (todas as análises são por perfil). Não há visão de vários perfis
  somados nesta spec.
- A tabela de cortes por perfil sai sem substituto próprio, porque Conteúdos lista os cortes (com filtro de
  perfil, origem e arquivados) e permite agendar.
- A barra de filtros única vale para toda lista com filtro. O inventário exato das telas sai do plano. Filtros
  que hoje não ficam no endereço passam a ficar.
- O estado lembrado do menu fica só no navegador (não sincroniza entre aparelhos).
- Os grupos começam abertos na primeira visita, salvo Configurações, que começa fechado.
- A verificação visual é feita com Playwright em 1280 e 390 px e pela revisão final do impeccable. O
  critique de 2026-10-06 é a linha de base.
