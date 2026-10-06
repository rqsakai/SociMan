# Feature Specification: Cenas para o Flow/Veo (010-cenas)

**Feature Branch**: `010-cenas`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Definir a entidade Cena como unidade reutilizável de produção: uma tomada
de até 8 s para o Google Flow/Veo, com avatar/pose, cenário, enquadramento, ação, fala/texto na tela,
duração, produto opcional (referência leve; o catálogo é a 012), prompt montado para o Flow (com as
regras visuais do avatar e do cenário e as proibidas do guia), versões e histórico, status
(rascunho/pronta/usada) e o vínculo com o vídeo gerado à mão pelo dono. O roteiro (sequência de cenas
com narrativa) é a 011. O assistente de IA (008) sugere o prompt; o shop-diretor propõe cenas pelo MCP
(009) como proposta que o dono aceita. Nada publica."

## Clarifications

### Session 2026-10-06

- Q: Como o shop-diretor propõe uma cena pelo MCP? → A: Como **proposta de cena**, um novo tipo de
  anotação da 009 (`proposta_cena`), presa ao perfil (cena nova) ou a uma cena (alteração); um humano
  aceita (formulário preenchido, nada salvo até o "Salvar") ou descarta. O agente não cria entidade de
  domínio (FR-023 da 009 intacto).
- Q: O que a cena guarda do resultado gerado no Flow? → A: As **tomadas** (vídeos curtos, várias
  tentativas, uma escolhida) **e** o vínculo da cena com o vídeo final (conteúdo vídeo próprio da 014),
  que define o status `usada`.
- Q: O prompt montado acompanha as mudanças do avatar e do cenário? → A: **Ao vivo em `rascunho`;
  congelado em `pronta` e `usada`**, com o aviso "o avatar/cenário mudou" e o botão "Remontar prompt".

## Contexto

A fábrica TikTok Shop (`../shared/shop/`) já trabalha em cenas, só que em arquivos soltos:

- o **shop-roteirista** grava roteiros JSON com 3 a 5 cenas de até 8 s, cada uma com `acao`, `fala`
  (até ~15 palavras, no máximo 2 cenas com fala para a câmera), `narracao` e `produto_visivel`;
- o **shop-diretor** transforma cada roteiro num **pacote** em markdown, com uma seção por cena pronta
  para copiar no Flow: prompt em inglês na ordem *aparência da persona (texto fixo) → ação com o
  produto → cenário → câmera (plano e movimento) → iluminação e estilo → áudio*, a fala em português
  entre aspas com verbo de fala, o **modo do Flow** (`Ingredients to Video`, `Frames to Video`,
  `Extend`), a **duração** (4, 6 ou 8 s; 8 s com ingredientes), os **ingredientes** (até 3 imagens: a
  da persona e a foto real do produto) e um **negative prompt** fixo;
- o **dono gera cada tomada à mão** no Google Flow/Gemini (Veo), edita, junta a narração e posta com o
  selo de IA. O Flow não tem API (2026-09) e o HeyGen está pausado.

No SociMan já existem as peças que uma cena reaproveita:

- **Biblioteca de assets (007):** o **avatar** (descrição fixa para prompts, tom de voz, regras de
  imagem, looks com imagens de referência e poses com "quando usar") e o **cenário** (prompt do
  ambiente e imagens de referência). A Achadinhos e os cenários "Cozinha retrô" e "Diner" de
  `persona.md` cabem nesses tipos. A 007 já previa "onde é usado: … no futuro, roteiros e cenas".
- **Assistente de IA (008) e guia de comunicação (017):** "Melhorar com IA" por tipo de campo, com os
  campos visuais (`avatar.descricao_prompt`, `cenario.prompt_ambiente`, `avatar.regras_imagem`)
  recebendo só as palavras proibidas do perfil.
- **Central de conteúdos (014):** o vídeo pronto entra como conteúdo de origem **vídeo próprio**, que
  depois é aprovado e agendado pelo dono.
- **MCP (009):** agentes leem tudo e, com o escopo "leitura e propostas", deixam anotações e propostas
  que um humano aplica; nunca aprovam, agendam ou publicam.

**Atenção ao nome:** a `docs/visao.md` chamava de "cenas" os *fundos e ambientes reutilizáveis*. Isso
virou o **cenário** da 007. Nesta spec, **cena** é a *tomada*: o que acontece em até 8 s, com quem,
onde e como filmar.

**Limites com as próximas specs:**

- **011-scripts** faz o **roteiro**: a sequência ordenada de cenas com narrativa (gancho, dor, formato,
  narração completa, CTA, título, legenda e hashtags) e o pacote do vídeo inteiro. A 010 entrega a peça
  avulsa e reutilizável; não tem ordem entre cenas, narração completa nem pacote por vídeo.
- **012-produtos-shop** faz o **catálogo** de produtos (dados, USPs, fotos oficiais, preços). Na 010, o
  produto é uma **referência leve**: nome curto e, opcionalmente, uma foto de referência da biblioteca
  de assets, que a 012 depois troca por um vínculo ao catálogo.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Montar uma cena e copiar o prompt para o Flow (Priority: P1)

O dono cria, no perfil, a cena "Achadinhos abre a panela" escolhendo o avatar Achadinhos (com o look
"Cozinha, corpo inteiro" ou uma pose), o cenário "Cozinha retrô", o enquadramento (plano médio, câmera
parada), a ação ("levanta a tampa, sai vapor"), a fala ("Gente, olha essa panela!"), a duração de 8 s e
o modo "Ingredients to Video". O SociMan monta o prompt em inglês no formato do diretor de criação, com
a descrição fixa do avatar com as mesmas palavras, as regras de imagem do avatar e do cenário e o
negative prompt, e lista os ingredientes (até 3 imagens) para baixar. O dono clica em "Copiar prompt",
baixa os ingredientes e gera a tomada no Flow.

**Why this priority**: É o trabalho que hoje sai do markdown do shop-diretor e o motivo da spec: um
prompt consistente, sempre com a mesma descrição da persona, sem copiar e colar entre arquivos.

**Independent Test**: Com o avatar e o cenário da Achadinhos cadastrados (007), criar uma cena e
conferir o prompt montado (ordem das partes, descrição fixa idêntica à do avatar, fala entre aspas com
verbo de fala, negative prompt), a lista de ingredientes e o "Copiar prompt".

**Acceptance Scenarios**:

1. **Given** um perfil com o avatar e o cenário cadastrados, **When** o usuário cria uma cena com
   avatar, look ou pose, cenário, enquadramento, ação, fala e duração, **Then** a cena é salva como
   `rascunho` e mostra o prompt montado com as partes na ordem: aparência do avatar → ação → cenário →
   câmera → iluminação e estilo → áudio/fala.
2. **Given** a cena salva, **When** o usuário abre o prompt, **Then** a descrição do avatar aparece
   **exatamente** como está no avatar (mesmas palavras), e a fala aparece em português, entre aspas, com
   verbo de fala (ex.: `She looks at the camera and says: "Gente, olha essa panela!"`).
3. **Given** uma cena com avatar, cenário e foto de produto, **When** o usuário abre os ingredientes,
   **Then** vê no máximo 3 imagens, na ordem referência do avatar, foto do produto e imagem do cenário,
   cada uma com "Baixar".
4. **Given** uma cena, **When** o usuário clica em "Copiar prompt" ou "Copiar negative prompt", **Then**
   o texto exato vai para a área de transferência.
5. **Given** uma cena com fala acima do que cabe na duração (mais de ~15 palavras em 8 s), **When** ela é
   salva, **Then** aparece o aviso "fala longa para 8 s" (não bloqueia).

---

### User Story 2 - Biblioteca de cenas, status e reaproveitamento (Priority: P1)

O dono vê as cenas do perfil numa aba própria, filtra por avatar, cenário, status, tag e produto, e busca
por texto. Marca uma cena como `pronta` quando o prompt está bom para gerar, e ela vira `usada` quando já
gerou uma tomada que entrou num vídeo. Para reaproveitar, "Duplicar" cria uma cena nova em rascunho a
partir de outra (ex.: a mesma abertura com outro produto). Nada é apagado: arquivar e restaurar.

**Why this priority**: A cena só vale como unidade reutilizável se for fácil achar, saber em que pé
está e copiar uma variação.

**Independent Test**: Criar 3 cenas com avatares e status diferentes, filtrar, duplicar uma, marcar
outra como pronta e arquivar a terceira; conferir a lista, os filtros e o histórico.

**Acceptance Scenarios**:

1. **Given** cenas em vários status, **When** o usuário filtra por status `pronta` e pelo avatar
   Achadinhos, **Then** só aparecem as cenas prontas daquele avatar, com miniatura (imagem do avatar ou
   da tomada escolhida), nome, duração, status e produto.
2. **Given** uma cena `pronta`, **When** o usuário clica em "Duplicar", **Then** nasce uma cena nova em
   `rascunho` com os mesmos campos, nome "(cópia)" e sem tomadas, e o histórico da nova registra a
   origem.
3. **Given** uma cena `rascunho` com campos obrigatórios faltando (avatar ou ação), **When** o usuário
   tenta marcar `pronta`, **Then** a mudança é recusada com a lista do que falta.
4. **Given** uma cena `pronta`, **When** o usuário edita um campo que muda o prompt, **Then** ela volta a
   `rascunho` e o histórico registra a mudança de status.
5. **Given** qualquer alteração, **When** é salva, **Then** fica no histórico com autor, antes e depois,
   com reversão pelo dono, e dois usuários editando ao mesmo tempo recebem conflito de versão em vez de
   sobrescrever.

---

### User Story 3 - Tomadas geradas e vínculo com o vídeo final (Priority: P2)

Depois de gerar no Flow, o dono envia a tomada (o MP4 de até 8 s) para a cena, pode enviar mais de uma
(tentativas) e marca a escolhida. Quando edita o vídeo final fora do SociMan e o envia como vídeo próprio
na Central de conteúdos (014), ele indica quais cenas entraram, e essas cenas passam a `usada`, com o
link para o conteúdo. Cada tomada guarda o prompt com que foi gerada (Clarifications Q2 e Q3).

**Why this priority**: Fecha o ciclo (prompt → tomada → vídeo publicado) e permite reaproveitar uma tomada
boa em outros vídeos e, mais tarde, ligar desempenho (016/019) às cenas. O prompt (US1) já tem valor sem
isso.

**Independent Test**: Enviar duas tomadas para uma cena, marcar a escolhida, enviar um vídeo próprio com
o vínculo a essa cena e conferir o status `usada`, o link nos dois sentidos e o histórico.

**Acceptance Scenarios**:

1. **Given** uma cena `pronta`, **When** o usuário envia um MP4 de 1 a 8 s (ou até o limite de uma
   tomada estendida), **Then** a tomada aparece na cena com miniatura, duração, data, o player e o prompt
   com que foi gerada.
2. **Given** duas tomadas, **When** o usuário marca uma como escolhida, **Then** ela vira a miniatura da
   cena e a outra continua guardada.
3. **Given** um vídeo próprio enviado na 014, **When** o usuário indica as cenas que o compõem, **Then**
   cada cena vira `usada` e mostra "Usada em: <conteúdo>", e o conteúdo mostra "Cenas: …".
4. **Given** uma tomada com proporção diferente de 9:16, **When** enviada, **Then** é aceita com o aviso
   "não é vertical".
5. **Given** uma cena em `rascunho`, **When** o usuário tenta enviar uma tomada, **Then** é orientado a
   marcar a cena como pronta antes (o prompt precisa estar congelado).

---

### User Story 4 - Sugerir o prompt da cena com IA (Priority: P2)

No formulário da cena, o usuário usa "Melhorar com IA" nos campos de texto (ação, câmera, iluminação e
estilo, áudio) e "Ajustar cena com IA", que propõe esses campos juntos a partir de uma instrução opcional
("mais close no produto", "câmera lenta"). O assistente segue as regras do tipo de campo, recebe as
palavras proibidas do guia do perfil e nunca muda a descrição fixa do avatar nem o prompt do cenário,
que não são campos da cena (vêm dos assets).

**Why this priority**: Acelera o trabalho, mas a cena funciona sem IA (US1).

**Independent Test**: Com o Claude falso, pedir uma sugestão de ação e um ajuste de prompt; conferir que
a proposta vem com explicação, que "Aplicar" salva só o campo com o selo "com ajuda da IA", que a
descrição do avatar continua idêntica e que uma proibida na proposta é marcada.

**Acceptance Scenarios**:

1. **Given** uma cena, **When** o usuário pede "Melhorar com IA" na ação, **Then** recebe proposta e
   explicação, com "Aplicar", "Outra versão" e "Descartar", como nos outros campos da 008.
2. **Given** um guia do perfil com palavras proibidas, **When** o assistente gera para a cena, **Then** o
   pedido leva só as proibidas (como os campos visuais da 017), e uma proposta que ainda contenha uma
   proibida sai marcada.
3. **Given** uma proposta de "Ajustar cena com IA", **When** aplicada, **Then** só os campos da cena
   (ação, câmera, iluminação e estilo, áudio) mudam, e o prompt montado continua com a descrição do avatar
   e o prompt do cenário com as mesmas palavras dos assets.

---

### User Story 5 - O shop-diretor propõe cenas pelo MCP (Priority: P3)

O shop-diretor, com escopo "leitura e propostas", lê avatares, cenários, guia e cenas do perfil e grava
**propostas de cena** (os mesmos campos de uma cena). O dono vê as propostas na caixa "Propostas dos
agentes" e na aba de cenas, e decide: "Aceitar" vira uma cena em `rascunho` com ele como autor e a
referência da proposta; "Descartar" fecha a proposta. O agente nunca marca pronta, nunca envia tomada e
nunca liga cena a conteúdo. A proposta é um novo tipo de anotação da 009 (`proposta_cena`), presa ao
perfil (cena nova) ou a uma cena (alteração) (Clarification Q1).

**Why this priority**: Migra o pacote do shop-diretor do markdown para o banco (visão do SociMan), mas
depende do resto pronto e da validação real do MCP com o OpenClaw (009, T061).

**Independent Test**: Com um cliente MCP "leitura e propostas", gravar uma proposta de cena; conferir o
selo do agente, a caixa de propostas, o aceitar (cena nova com o dono como autor) e a recusa de qualquer
outra escrita em cena pelo agente.

**Acceptance Scenarios**:

1. **Given** um cliente MCP "leitura e propostas", **When** grava uma proposta de cena com avatar,
   cenário, ação e fala, **Then** ela aparece com o selo "Agente: <nome>" e a data, sem criar cena.
2. **Given** uma proposta aberta, **When** o dono clica em "Aceitar", **Then** o formulário de nova cena
   abre preenchido e, ao salvar, a cena nasce em `rascunho` com o humano como autor e a proposta passa a
   `aplicada`.
3. **Given** um cliente MCP, **When** tenta criar, editar, mudar status, arquivar cena, enviar tomada ou
   ligar cena a conteúdo, **Then** a chamada é recusada e fica no registro do MCP.
4. **Given** uma proposta que referencia avatar ou cenário arquivado ou de outro perfil, ou que é presa
   a uma cena arquivada ou `usada`, **When** é gravada, **Then** é recusada com o motivo.

---

### Edge Cases

- **Avatar ou cenário mudou depois de a cena ficar pronta:** a cena mostra "a descrição do avatar mudou
  desde que esta cena ficou pronta" com a diferença e "Remontar prompt". Em `rascunho` o prompt acompanha
  sozinho; em `pronta` e `usada` fica congelado até o "Remontar" (Clarification Q3). As tomadas já
  enviadas guardam o prompt com que foram geradas e não mudam.
- **Avatar ou cenário arquivado:** a cena continua legível com o nome e a última descrição usada, mas não
  pode ser marcada `pronta` até trocar a referência. Arquivar um asset usado por cena **não** é bloqueado
  (como cortes na 007), só informado em "onde é usado".
- **Cena sem avatar** (ex.: close do produto girando): permitida; o prompt começa pela ação e não leva
  descrição de persona.
- **Cena sem produto:** permitida (ex.: abertura genérica com a persona acenando).
- **Produto sem foto:** a cena mostra o aviso do diretor "sem foto do produto: não invente a aparência" e
  o prompt não descreve o produto além do nome.
- **Limite de 3 ingredientes:** a cena tem no máximo um arquivo do avatar, uma foto de produto e uma
  imagem de cenário, então nunca passa de 3. Uma referência extra (ex.: segunda pose) fica para a 011.
- **Duração com ingredientes:** "Ingredients to Video" fixa 8 s; escolher 4 ou 6 s nesse modo mostra o
  aviso do limite do Flow.
- **"Frames to Video":** exige descrição (ou imagem) do quadro inicial e do final; sem eles, a cena não
  fica pronta.
- **Fala em português dentro de prompt em inglês:** a fala fica em pt-BR e entre aspas; o resto do
  prompt fica em inglês.
- **Texto na tela pedido ao Veo:** desaconselhado (o negative prompt bloqueia texto); o texto na tela da
  cena é **guia de edição** para o dono pôr depois, e não entra no prompt.
- **Cena de outro perfil:** nunca aparece nem pode ser referenciada fora do perfil.
- **Tomada inválida ou fora do limite:** recusada pela validação de conteúdo, com o motivo, sem ocupar
  espaço.

## Requirements *(mandatory)*

### Functional Requirements

**Cena (US1, US2)**

- **FR-001**: Cada perfil DEVE ter uma biblioteca de **cenas** (aba "Cenas"). Uma cena DEVE ter: nome,
  avatar (opcional, da biblioteca do perfil) com look ou pose (opcional), cenário (opcional),
  enquadramento (plano: close, busto, médio, americano, aberto, detalhe do produto; movimento: parada,
  aproximação, afastamento, panorâmica, câmera na mão; e um detalhe de câmera em texto livre, opcional),
  ação (obrigatória), fala para a câmera (opcional,
  pt-BR), texto na tela (opcional, guia de edição), iluminação e estilo (opcional, com padrão do perfil),
  áudio/ambiente (opcional), duração (4, 6 ou 8 s), modo do Flow (`ingredientes`, `quadros`, `estender`),
  quadros inicial e final (no modo `quadros`), produto (referência leve, opcional), tags, notas e status.
- **FR-002**: O **produto** DEVE ser uma referência leve: nome curto e, opcionalmente, uma foto da
  biblioteca de assets do perfil (tipo imagem). Não há catálogo, preço nem USP nesta spec (012).
- **FR-003**: O SociMan DEVE montar o **prompt para o Flow** em inglês, sempre na ordem: descrição fixa
  do avatar (texto idêntico ao do avatar) → regras de imagem do avatar → ação (com "exactly as in the
  reference image" quando há foto do produto) → prompt do ambiente do cenário → câmera → iluminação e
  estilo → áudio e fala (em pt-BR, entre aspas, com verbo de fala). O **negative prompt** DEVE ter um
  padrão (`text, subtitles, watermark, logo changes, extra fingers, distorted product`) e ser editável
  por cena.
- **FR-004**: A cena DEVE listar os **ingredientes** (até 3 imagens: referência do avatar ou pose,
  imagem do cenário, foto do produto), com download do original de cada uma, e "Copiar prompt" e "Copiar
  negative prompt" com o texto exato.
- **FR-005**: Avisos (não bloqueiam): fala acima de ~15 palavras para 8 s (proporcional à duração),
  duração diferente de 8 s no modo `ingredientes`, produto sem foto, palavra proibida
  do guia do perfil na fala, na ação ou no texto na tela.
- **FR-006**: Status da cena: `rascunho` → `pronta` → `usada`. Marcar `pronta` DEVE exigir ação, duração,
  modo e, no modo `quadros`, os dois quadros, e avatar e cenário não arquivados quando referenciados.
  Editar campo que muda o prompt numa cena `pronta` a devolve a `rascunho`. `usada` é definida pelo
  vínculo com um conteúdo (US3) e volta a `pronta` quando o último vínculo é desfeito. Numa cena `usada`,
  só nome, tags, notas e tomadas mudam; para variar o prompt, "Duplicar" (409 com a explicação). A
  reversão do dono numa cena `usada` também é recusada; nas demais, o status volta com a versão, e
  `usada` só vale se ainda houver vínculo ativo (senão vira `pronta`).
- **FR-006a**: O prompt montado DEVE acompanhar o avatar e o cenário enquanto a cena está em `rascunho` e
  ficar **congelado** (texto e versões do avatar e do cenário usadas) ao marcar `pronta`. Se o avatar ou o
  cenário mudarem depois, a cena DEVE mostrar o aviso com a diferença e o botão "Remontar prompt", que
  atualiza o prompt congelado (com histórico) sem mudar o status.
- **FR-007**: A lista de cenas DEVE ter filtros por avatar, cenário, status, tag e produto, busca por nome,
  ação e fala, e mostrar miniatura, nome, duração, status, produto e data. "Duplicar" cria uma cena nova
  em `rascunho` sem tomadas nem vínculos, com a origem no histórico.
- **FR-008**: Cenas NUNCA são apagadas: arquivar e restaurar. Toda mutação DEVE registrar autor, antes e
  depois, com versão (conflito de versão em edição concorrente) e reversão pelo dono (princípio VII).
- **FR-009**: A cena DEVE aparecer em "onde é usado" do avatar, do cenário e da foto do produto (007),
  sem bloquear o arquivamento desses assets.
- **FR-010**: Dono e membro criam, editam, duplicam, mudam status e arquivam cenas; reverter é só do dono
  (como nos assets da 007).

**Tomadas e vínculo (US3)**

- **FR-011**: A cena DEVE aceitar o envio de **tomadas** (vídeo gerado no Flow): MP4/MOV/WebM, de 1 s até
  o limite de tomada (padrão 30 s, cobrindo `estender`), qualquer proporção com aviso fora de 9:16,
  guardadas no armazenamento de vídeos (HD com sentinela e piso); várias por cena, uma marcada como
  escolhida; sem apagar (arquivar a tomada). Só cenas `pronta` ou `usada` recebem tomadas, e cada tomada
  guarda o prompt congelado do momento do envio (não muda com um "Remontar" posterior).
- **FR-012**: Um conteúdo de origem vídeo próprio (014) DEVE poder indicar as cenas que o compõem (de
  qualquer status exceto `rascunho` e arquivada, do mesmo perfil). A cena mostra "Usada em", o conteúdo
  mostra "Cenas", e o vínculo e o desfazer ficam no histórico dos dois lados.
- **FR-013**: Nenhuma ação desta spec publica, aprova ou agenda: o vídeo final segue o caminho da 014
  (aprovação e agendamento só por humanos, princípio I).

**IA (US4)**

- **FR-014**: O assistente de IA DEVE ganhar tipos de campo para a cena (ação, câmera, iluminação e
  estilo, áudio, e "ajustar cena", que propõe esses quatro juntos), com regras padrão editáveis pelo dono e registro de chamadas como na 008.
  Esses tipos usam o guia no modo "só proibidas" (como os campos visuais da 017) e levam o avatar, o
  cenário e o produto da cena como contexto.
- **FR-015**: A IA da cena NUNCA DEVE alterar a descrição fixa do avatar, as regras de imagem nem o prompt
  do cenário: eles não são campos da cena e entram no prompt montado só a partir dos assets. "Aplicar"
  salva só os campos propostos, com o humano como autor e o selo "com ajuda da IA".

**MCP (US5)**

- **FR-016**: As cenas (lista, detalhe, prompt montado e ingredientes) DEVEM ser legíveis pelo MCP com
  escopo de leitura.
- **FR-017**: Com escopo "leitura e propostas", o agente DEVE poder gravar **propostas de cena** num
  perfil (ou numa cena existente, como proposta de alteração), com os campos da cena; aceitar ou
  descartar é ato humano, e aceitar abre o formulário preenchido sem salvar até o "Salvar".
- **FR-018**: O MCP NÃO DEVE criar, editar, mudar status, duplicar, arquivar, restaurar ou reverter
  cenas, nem enviar tomadas ou ligar cena a conteúdo. Propostas de cena contam no limite de escritas do
  cliente e ficam no registro do MCP.

### Key Entities

- **Cena**: tomada reutilizável de um perfil (até 8 s por geração). Nome, avatar e look/pose, cenário,
  enquadramento, ação, fala, texto na tela, iluminação e estilo, áudio, duração, modo do Flow, quadros,
  produto (referência leve), negative prompt, tags, notas, status, versão e histórico.
- **Prompt montado**: texto em inglês derivado da cena e dos assets referenciados, na ordem fixa, com a
  marca das versões do avatar e do cenário usadas.
- **Ingrediente**: imagem de referência para o Flow (avatar/pose, cenário, produto), até 3 por cena.
- **Referência de produto**: nome curto e foto opcional da biblioteca; ponte para o catálogo da 012.
- **Tomada**: vídeo gerado à mão no Flow e enviado para a cena; uma por cena é a escolhida.
- **Uso da cena**: vínculo entre cena e conteúdo vídeo próprio (014), que define o status `usada`.
- **Proposta de cena**: anotação do MCP (009) com os campos de uma cena, aberta até um humano aceitar ou
  descartar.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com o avatar e o cenário cadastrados, o dono monta uma cena e copia o prompt e os
  ingredientes em menos de 2 minutos.
- **SC-002**: Em 100% dos prompts montados, a descrição do avatar é idêntica (caractere a caractere) à
  do avatar na versão marcada, e as partes seguem a ordem fixa.
- **SC-003**: As cenas de um roteiro de exemplo no formato do shop-roteirista (3 a 5 cenas) são recriadas
  como cenas do SociMan, e os prompts montados equivalem aos do pacote do shop-diretor (mesmas partes, mesma
  descrição da persona, mesmo negative prompt).
- **SC-004**: Nenhuma escrita em cena, tomada ou vínculo é aceita de um cliente MCP; 100% das tentativas
  são recusadas e registradas (teste automatizado).
- **SC-005**: Toda mudança em cena aparece no histórico com autor e é reversível pelo dono (teste
  automatizado).
- **SC-006**: Achar uma cena pronta de um avatar com um produto leva menos de 15 segundos com os filtros,
  com 200 cenas no perfil.

## Assumptions

- **Escopo por perfil:** cenas pertencem a um perfil (como os assets da 007) e não a uma conta; a conta
  entra quando o vídeo final vira destino na 014.
- **Geração manual:** o SociMan não chama o Flow, o Veo nem o HeyGen (sem API do Flow; HeyGen pausado). A
  automação pelo Veo 3.1 na API do Gemini, se vier, é outra spec.
- **Idioma do prompt:** inglês para o prompt e o negative prompt; fala e texto na tela em pt-BR, como no
  pacote do shop-diretor.
- **Limites do Flow** (até 3 ingredientes, 8 s com ingredientes, 4/6/8 s nos outros modos) ficam em
  constantes no código e geram avisos, não bloqueios, porque o Flow muda sem aviso.
- **Iluminação e estilo padrão** do perfil vêm de um texto padrão editável na própria aba de cenas (não
  no kit de marca, que é para o produtor de cortes).
- **Texto na tela** é guia de edição (o dono põe na edição); não entra no prompt, porque o negative
  prompt bloqueia texto no vídeo gerado.
- **Narração em off** é do roteiro (011), não da cena; a cena só tem a fala para a câmera.
- **Palavras proibidas:** comparação por palavra inteira, sem acento e sem caixa (017), aplicada à fala,
  à ação e ao texto na tela; na cena só avisa. Na proposta da IA vale a regra da 017 (marcar e recusar o
  salvar igual à proposta).
- **Tomadas:** contam no armazenamento de vídeos do HD; o limite de 30 s por tomada cobre o `estender`.
- **Importação** das cenas dos roteiros e pacotes existentes em `../shared/shop/` fica para a
  013-importacao (hoje as pastas `roteiros/` e `pacotes/` estão vazias).
- **Selo de IA ao postar** continua sendo conferido pelo dono no momento de postar (checklist do
  diretor); a 010 só mostra o lembrete na cena e no vínculo com o conteúdo.
