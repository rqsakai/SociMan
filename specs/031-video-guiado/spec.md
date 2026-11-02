# Feature Specification: Vídeo guiado (031-video-guiado)

**Feature Branch**: `031-video-guiado`

**Created**: 2026-10-13

**Status**: Draft

**Input**: User description: "031-video-guiado". Insumo: `docs/insumos/031-video-guiado.md`, o pedido do dono de
2026-10-13, feito depois do primeiro teste real da 011 (saída de praia kaftan preta).

## Contexto

A 011 já gera um vídeo de produto inteiro na máquina da casa. O fluxo é este:
- o operador escreve um brief;
- a IA planeja o texto e as cenas;
- sai a narração;
- cada cena ganha **um** keyframe aprovado, que vira um clipe;
- os clipes são montados e passam pelo acabamento.

No primeiro teste real, o dono encontrou quatro problemas:
1. **As cenas surgem de forma obscura.** A IA reaproveita uma cena da biblioteca ou cria uma nova, mas essa
   decisão fica escondida dentro da etapa Texto. O dono achou que a cena precisava existir antes.
2. **Um keyframe só por cena.** O gerador de vídeo não sabe onde a cena deve terminar e "delira".
3. **A duração não é escolhida.** Ela sai do texto, e não de uma grade que o gerador cumpra bem.
4. **A tela é de especialista.** Mostra prompts e textos de fala que o operador comum não precisa ver.

O que esta spec **adiciona**:
- um **"Novo vídeo" guiado**: blocos grandes e simples, depois um chat em que a IA faz perguntas fechadas
  e, no fim, monta sozinha tudo o que precisa;
- um **modo wizard** (padrão), em que o operador só ouve o áudio, vê os keyframes e aprova ou pede troca
  pelo chat;
- um **modo avançado**: a tela da 011, com textos, prompts e portões;
- **reuso de cenas transparente**;
- **2 a 4 keyframes por cena**: início, meio 1 e meio 2 opcionais, e fim;
- uma **grade de duração** em múltiplos do tamanho de trecho que o gerador cumpre bem.

O que esta spec **não muda**:
- só humano aprova;
- o vídeo final continua sendo um conteúdo da 014, sem conta e sem aprovação de postagem;
- a IA nunca publica (princípio I).

A 032 (variantes por combinação de cenas) depende da grade desta spec.

## Clarifications

### Session 2026-10-13

- Q: Quantas perguntas a IA faz no chat antes de montar o plano? → A: até 5 (FR-009).
- Q: O vídeo guiado substitui o "Novo vídeo" atual da 011 ou fica ao lado? → A: substitui; o especialista
  usa o modo avançado, e os roteiros antigos abrem nele (FR-018).
- Q: Quantos keyframes por cena por padrão? → A: a IA decide por cena, de 2 a 4 (FR-029).
- Q: Quanto dura cada trecho entre dois keyframes? → A: exatamente 1 trecho-base. Uma cena de k
  trechos-base tem k+1 keyframes, e por isso tem no máximo 3 trechos-base (FR-027, FR-031).
- Q: Como o operador aprova os keyframes de uma cena com 3 ou 4 quadros no wizard? → A: a sequência
  inteira é gerada de uma vez (cada quadro nascendo do anterior) e aprovada junto. Recusar um quadro refaz
  ele e os seguintes (FR-026).
- Q: No wizard, 1 versão por item para aprovar ou 2 para escolher? → A: 1 versão no wizard; o avançado pode
  pedir 2 ou mais para escolher (FR-015).
- Q: O que se reaproveita quando a cena da biblioteca vai para um vídeo com outro avatar, cenário ou
  produto? → A: dois níveis. **Reuso total** (mesmo avatar, cenário e produto) usa os keyframes e os clipes
  aprovados sem GPU. **Reuso do plano** (algo diferente) usa a ação, a câmera, o movimento e os trechos,
  e gera tudo de novo numa cena derivada (FR-019, FR-022).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Começar um vídeo em blocos simples (Priority: P1)

O operador abre **AI Studio → Vídeos → Novo vídeo** e vê uma sequência de blocos grandes, um por vez:
1. **tipo de vídeo**: hoje só "Avatar & POV", com espaço para tipos futuros;
2. **perfil**;
3. **avatar e voz**: a voz padrão do avatar vem pré-escolhida e pode ser trocada;
4. **cenário**;
5. **produto**: só os aprovados;
6. **duração**, escolhida na grade.

Cada bloco mostra as opções como cartões com imagem: avatar, cenário e produto aparecem pela foto, e a voz
pode ser ouvida. O operador pode voltar a qualquer bloco anterior.

**Why this priority**: É a porta de entrada. Sem ela, o operador comum continua na tela de especialista.

**Independent Test**: Escolher os 6 blocos com um avatar que tenha voz padrão e confirmar:
- a voz vem pré-escolhida;
- só os produtos aprovados aparecem;
- voltar a um bloco mantém as outras escolhas;
- o resumo final mostra as 6 escolhas.

**Acceptance Scenarios**:

1. **Given** um avatar com voz padrão, **When** o operador o escolhe, **Then** o bloco de voz já vem com
   essa voz marcada e permite trocar por outra voz aprovada.
2. **Given** um avatar sem voz padrão, **When** o operador o escolhe, **Then** o bloco de voz pede uma voz
   aprovada antes de seguir. Sem nenhuma voz aprovada na agência, o bloco explica o motivo e mostra o
   caminho para cadastrar uma.
3. **Given** o bloco de produto, **When** ele abre, **Then** só aparecem produtos aprovados. Um produto em
   revisão não aparece, e o bloco mostra quantos ficaram de fora.
4. **Given** o operador no bloco 5, **When** ele volta ao bloco 2 e troca o perfil, **Then** avatar,
   cenário e produto continuam escolhidos (a biblioteca é da agência, 029). Só mudam o guia e as palavras
   proibidas que valem para o vídeo, e a tela avisa.
5. **Given** os 6 blocos preenchidos, **When** o operador segue, **Then** o vídeo é criado como rascunho e
   o chat da User Story 2 abre.

---

### User Story 2 - Chat com perguntas fechadas, e a IA monta tudo (Priority: P1)

Depois dos blocos, abre um chat. A IA faz algumas perguntas **específicas e de múltipla escolha** sobre o
produto e sobre o que o operador espera. Exemplos:
- quais aspectos do produto focar;
- tipo de chamada (CTA);
- tipo de movimento;
- tom.

Cada pergunta traz opções clicáveis. O operador pode marcar uma ou mais, quando a pergunta permitir, ou
escrever uma resposta curta. O chat também mostra **exemplos de pedidos prontos** para clicar, como "mostrar
o caimento", "foco no preço" e "estilo antes/depois".

Ao fim das perguntas, a IA monta sozinha:
- o texto da narração;
- as cenas: reaproveitadas ou novas, ver User Story 4;
- os keyframes de cada cena;
- os movimentos;
- a divisão do tempo na grade.

**Why this priority**: É o que tira o operador da folha em branco do brief. Junto com a User Story 1,
forma o fluxo mínimo útil.

**Independent Test**: Responder às perguntas só com cliques, sem digitar nada, e receber um plano completo:
narração, cenas e keyframes previstos, com a soma dos tempos igual à duração escolhida.

**Acceptance Scenarios**:

1. **Given** o chat aberto, **When** a IA pergunta, **Then** cada pergunta tem de 2 a 6 opções clicáveis,
   e no máximo uma pergunta por vez fica sem responder.
2. **Given** o operador responde a todas só por cliques, **When** a IA termina, **Then** o plano está
   completo, e nada pede texto livre.
3. **Given** uma resposta que contém uma palavra proibida pelo guia do perfil, **When** a IA monta o plano,
   **Then** a palavra não entra no texto, e o chat avisa.
4. **Given** o plano montado, **When** o operador olha o resumo, **Then** a soma da duração das cenas é
   **exatamente** a duração escolhida no bloco 6.
5. **Given** a IA fora do ar, **When** o chat tenta perguntar ou montar, **Then** aparece "a IA não
   respondeu; tentar de novo". As escolhas dos blocos e as respostas já dadas não se perdem.

---

### User Story 3 - Modo wizard: ouvir, ver e aprovar ou pedir troca (Priority: P1)

No modo wizard, que é o padrão, o operador **não vê** texto de prompt nem texto de fala. Ele vê, em ordem:
- a **narração gerada**, como áudio, para aprovar ou não;
- os **keyframes de cada cena**, de 2 a 4 imagens, para aprovar ou não;
- os **clipes**;
- o **vídeo final**.

"Não aprovo" abre o chat naquele ponto: o operador diz o que quer trocar, por clique ou por texto curto, e a
IA ajusta o que for preciso e gera de novo **só o que mudou**.

**Why this priority**: É o modo do operador comum, e sem ele a simplificação não se completa.

**Independent Test**: Num vídeo planejado, recusar 1 keyframe pelo chat ("mais de lado, mostrando a
manga") e confirmar:
- só aquele keyframe e o que depende dele são refeitos;
- os outros keyframes aprovados continuam;
- em nenhum momento aparece texto de prompt.

**Acceptance Scenarios**:

1. **Given** o modo wizard, **When** a narração fica pronta, **Then** o operador ouve o áudio e tem
   "Aprovar" e "Não aprovo", sem ver o texto.
2. **Given** "Não aprovo" na narração, **When** o operador escolhe "mais animada" no chat, **Then** a
   narração é refeita com a mudança, e os keyframes não são refeitos.
3. **Given** "Não aprovo" no keyframe do meio de uma cena, **When** o pedido é aplicado, **Then** são
   refeitos esse keyframe e os seguintes daquela cena, porque cada um nasce do anterior. Os keyframes de
   antes e os das outras cenas ficam.
4. **Given** um pedido de troca que a IA não entendeu, **When** ela responde, **Then** pede um
   esclarecimento com opções clicáveis, em vez de gerar no escuro.
5. **Given** as aprovações feitas, **When** o vídeo final fica pronto, **Then** ele vira um conteúdo da 014
   sem destino, como na 011.

---

### User Story 4 - Reuso de cenas transparente (Priority: P1)

Antes de gerar, a IA mostra, num **modal de cenas**, a proposta para cada posição do vídeo:
- **reaproveitar** uma cena da biblioteca (miniatura, nome e onde já foi usada);
- ou **criar uma nova**, com uma frase do que ela mostra.

O padrão é **sempre propor o reuso** quando uma cena da biblioteca serve. Só se propõe criar quando nenhuma
serve, ou quando o operador pede cenas novas. Pelo modal, o operador pode:
- trocar o reuso por "criar nova";
- trocar "criar nova" por uma cena da biblioteca;
- conversar com a IA sobre uma posição.

Toda cena nova é **salva na biblioteca** para uso futuro, com o perfil base do vídeo.

**Why this priority**: É o primeiro problema que o dono viu no teste (cenas obscuras), e o reuso é o que
economiza GPU.

**Independent Test**: Com 2 cenas na biblioteca que servem e 1 posição sem cena adequada, confirmar:
- o modal propõe 2 reusos e 1 nova;
- trocar um reuso por "criar nova" funciona;
- depois de gerar, a cena nova aparece na biblioteca.

**Acceptance Scenarios**:

1. **Given** uma biblioteca com cenas que servem, **When** o plano é montado, **Then** o modal propõe o
   reuso nessas posições e mostra por quê, em uma frase.
2. **Given** a biblioteca vazia, **When** o plano é montado, **Then** todas as posições aparecem como "criar
   nova", e o fluxo segue sem pedir que o operador crie cenas antes.
3. **Given** o operador marca "quero cenas novas" no chat, **When** o plano é montado, **Then** o modal
   propõe "criar nova" em todas as posições, e o reuso continua disponível para trocar.
4. **Given** uma cena nova aprovada, **When** o vídeo é entregue, **Then** a cena está na biblioteca, com
   os keyframes aprovados, e serve para os próximos vídeos.
5. **Given** uma cena reaproveitada, **When** o vídeo é gerado, **Then** a cena reaproveitada não é
   alterada: um ajuste vira uma cena nova, derivada dela.
6. **Given** uma cena da biblioteca com o mesmo avatar, cenário e produto, **When** o operador aceita o
   reuso total, **Then** nenhum keyframe nem clipe daquela posição é gerado, e a GPU não é usada para ela.
7. **Given** uma cena da biblioteca com outro avatar, **When** o operador aceita o reuso do plano, **Then**
   os keyframes e os clipes são gerados de novo com o avatar do vídeo, mantendo a ação, a câmera, o
   movimento e os trechos, e a cena derivada vai para a biblioteca.

---

### User Story 5 - De 2 a 4 keyframes por cena (Priority: P2)

Cada cena tem **no mínimo** um keyframe de **início** e um de **fim**. Pode ter também **meio 1** e
**meio 2**. Cada keyframe nasce do anterior, para o avatar e o produto não mudarem entre os quadros. O
gerador de vídeo produz **um trecho entre cada par de keyframes vizinhos**, e os trechos são colados na
ordem: 4 keyframes dão 3 trechos.

**Why this priority**: Reduz o "delírio" do gerador, mas o fluxo das User Stories 1 a 4 já entrega vídeo
com o mínimo de 2 keyframes.

**Independent Test**: Gerar uma cena com 4 keyframes e confirmar:
- saem 3 trechos;
- o último quadro de cada trecho é o keyframe seguinte;
- o trecho final termina no keyframe de fim;
- a cena montada não tem salto visível entre os trechos.

**Acceptance Scenarios**:

1. **Given** uma cena com início e fim, **When** o clipe é gerado, **Then** ele começa no keyframe de
   início e termina no de fim.
2. **Given** uma cena com 4 keyframes, **When** os trechos são gerados, **Then** são 3 trechos, cada um
   entre um par vizinho e com 1 trecho-base de duração, e a cena dura 3 trechos-base.
3. **Given** o keyframe do meio 1 refeito, **When** os trechos são atualizados, **Then** os trechos que
   tocam o meio 1 (início→meio 1 e meio 1→meio 2) são refeitos, e o trecho meio 2→fim é reaproveitado.
4. **Given** uma cena que não pede quadros do meio, **When** a IA planeja, **Then** ela ocupa 1
   trecho-base e tem só início e fim. Os quadros do meio aparecem quando o movimento pede uma cena de 2 ou 3
   trechos-base.

---

### User Story 6 - Grade de duração (Priority: P2)

A duração do vídeo é escolhida numa **grade de múltiplos** do tamanho de trecho que o gerador cumpre bem. Com
um trecho-base de 6 s, as opções seriam 6, 12, 18, 24 e 30 s; com um de 8 s, 8, 16, 24 e 32 s. Cada cena ocupa
de 1 a 3 trechos-base (com 2 a 4 keyframes), e a soma das cenas é a duração escolhida. A narração é ajustada para
caber, e cada cena fica com o seu bloco de fala.

**Why this priority**: Torna o tempo previsível e é pré-requisito da 032. O mínimo útil, nas User Stories
1 a 4, já pode usar a grade com cenas de 1 trecho.

**Independent Test**: Escolher 24 s com trecho-base de 6 s e confirmar:
- o vídeo final tem 24 s, com tolerância de ±0,5 s;
- cada cena dura um múltiplo de 6 s;
- cada bloco de fala cabe na sua cena.

**Acceptance Scenarios**:

1. **Given** um trecho-base configurado, **When** o bloco de duração abre, **Then** só aparecem múltiplos
   dele, do menor ao máximo permitido.
2. **Given** a narração ficou mais longa que a duração, **When** ela é ajustada, **Then** a velocidade
   muda dentro do limite natural. Se mesmo assim não couber, o operador é avisado para escolher uma duração
   maior ou aceitar um texto mais curto, que a IA propõe.
3. **Given** um vídeo de 5 cenas e 30 s com trecho-base de 6 s, **When** é montado, **Then** cada cena
   tem 6 s, e o total é 30 s.
4. **Given** o trecho-base muda na configuração, **When** um vídeo novo é criado, **Then** a grade nova
   vale para ele, e os vídeos já existentes mantêm a grade com que foram criados.

---

### User Story 7 - Modo avançado (Priority: P3)

Um switch no topo do vídeo troca o wizard pelo **modo avançado**. O avançado mostra o que a 011 já
mostra: o texto, o prompt de cada cena e de cada keyframe, os portões, o modo automático e as trocas
manuais. A troca de modo não perde nada: o que foi feito num modo aparece no outro.

**Why this priority**: Mantém o especialista produtivo, e a tela da 011 já existe.

**Independent Test**: Começar um vídeo no wizard, trocar para o avançado no meio, editar o prompt de 1
keyframe, voltar ao wizard e confirmar:
- o keyframe aparece como a refazer;
- as aprovações anteriores continuam.

**Acceptance Scenarios**:

1. **Given** o wizard, **When** o operador liga o avançado, **Then** a mesma etapa aparece com os textos e
   os prompts visíveis.
2. **Given** uma edição no avançado, **When** o operador volta ao wizard, **Then** o wizard mostra o efeito
   (o item a refazer ou refeito), não o texto.
3. **Given** a escolha do modo, **When** o operador sai e volta ao vídeo, **Then** a tela abre no último
   modo que ele usou.

---

### Edge Cases

- **Nenhum avatar, cenário ou produto aprovado na agência:** o bloco explica o que falta e leva ao cadastro
  certo no AI Studio, sem travar os outros blocos.
- **Item arquivado ou voz revogada depois da escolha:** antes de gerar, o vídeo avisa e pede outra escolha.
  Com voz ou avatar de consentimento revogado, nada é gerado (regra da 025).
- **Perfil base arquivado:** vale a regra da 029. A geração é recusada com aviso, e o rascunho continua
  editável.
- **O operador fecha a tela no meio do chat:** as respostas dadas ficam salvas, e o chat continua de onde
  parou.
- **A IA propõe reuso de uma cena que tem produto diferente:** o modal mostra o aviso "produto diferente",
  e o reuso só segue se a cena não mostrar produto.
- **Duração escolhida menor que o mínimo de cenas que a IA quer:** a IA planeja menos cenas, nunca cenas
  menores que o trecho-base.
- **Movimento que pede mais de 3 trechos-base:** a IA divide o movimento em duas cenas seguidas. O fim de
  uma é o início da outra.
- **Keyframe do meio que não fica coerente** (o avatar muda de rosto entre quadros): no wizard, o operador
  recusa e pede "manter o rosto", e a IA refaz a partir do keyframe anterior aprovado.
- **Emenda visível entre trechos:** o operador recusa o clipe, e o pedido de troca refaz o trecho com
  problema, não a cena toda.
- **Dois operadores no mesmo vídeo:** vale o controle de versão da 011 (quem salvou depois recebe "foi
  alterado por outra pessoa").
- **GPU ocupada ou serviço de geração fora do ar:** como na 011/021, o vídeo mostra "aguardando a GPU" ou
  "tentando de novo", e o operador não perde aprovações.

## Requirements *(mandatory)*

### Functional Requirements

**Novo vídeo em blocos**
- **FR-001**: O "Novo vídeo" DEVE apresentar, em ordem, os blocos tipo de vídeo, perfil, avatar e voz,
  cenário, produto e duração, um por vez. O operador DEVE poder voltar a qualquer bloco anterior.
- **FR-002**: O bloco de tipo de vídeo DEVE oferecer "Avatar & POV" e DEVE estar preparado para tipos
  futuros. Um tipo ainda indisponível aparece como "em breve".
- **FR-003**: Ao escolher um avatar com voz padrão, a voz DEVE vir pré-escolhida. O operador DEVE poder
  trocá-la por qualquer voz aprovada. Sem voz padrão, a escolha de uma voz aprovada DEVE ser obrigatória.
- **FR-004**: Os blocos de avatar, cenário e produto DEVEM listar só itens utilizáveis: não arquivados,
  avatar sem consentimento revogado e produto aprovado. Cada bloco DEVE mostrar quantos itens ficaram de
  fora e por quê.
- **FR-005**: Os itens DEVEM vir da biblioteca da agência (029), de qualquer perfil base. O perfil escolhido
  no bloco 2 é o perfil base do vídeo: guia, palavras proibidas e padrões.
- **FR-006**: Trocar um bloco anterior DEVE manter as escolhas seguintes que continuam válidas, desmarcar
  as inválidas e dizer quais foram desmarcadas. Trocar o avatar refaz a voz pré-escolhida (se a voz não foi
  trocada à mão), e trocar o produto refaz a variante. Trocar o perfil não desmarca nada.
- **FR-007**: Concluir os blocos DEVE criar o vídeo como rascunho, com as escolhas gravadas e no histórico.

**Chat com perguntas fechadas**
- **FR-008**: Depois dos blocos, o sistema DEVE abrir um chat em que a IA faz perguntas sobre o produto e
  sobre o objetivo do vídeo. Cada pergunta DEVE ter de 2 a 6 opções clicáveis, com escolha única ou
  múltipla, indicada na pergunta. Uma resposta curta escrita é opcional.
- **FR-009**: O chat DEVE ter no máximo **5 perguntas** antes de montar o plano. DEVE ser possível montar o
  plano só com cliques.
- **FR-010**: O chat DEVE oferecer exemplos de pedidos prontos para clicar, sobre foco, chamada,
  movimento e tom.
- **FR-011**: As perguntas, as respostas e o plano montado DEVEM ficar gravados no vídeo, com autor e data.
  Fechar e reabrir o vídeo DEVE retomar o chat de onde parou.
- **FR-012**: A IA DEVE respeitar o guia de comunicação e as palavras proibidas do perfil base (017). Uma
  palavra proibida numa resposta não entra no texto, e o chat avisa.
- **FR-013**: Ao fim do chat, a IA DEVE montar sozinha o plano completo: narração, cenas (com reuso ou
  novas), keyframes por cena, movimentos e divisão do tempo na grade.

**Modo wizard e modo avançado**
- **FR-014**: O vídeo DEVE ter dois modos, wizard (padrão) e avançado, trocados por um switch no topo. A
  troca DEVE preservar todo o estado. O último modo usado pelo operador naquele vídeo DEVE ser lembrado.
- **FR-015**: No wizard, o operador NÃO DEVE ver texto de prompt nem texto da narração. Ele DEVE ver e
  aprovar: o áudio da narração, os keyframes de cada cena, os clipes e o vídeo final. No wizard, cada item
  DEVE ser gerado em **1 versão**, para aprovar ou não. No avançado, o operador DEVE poder pedir 2 ou mais
  versões de um item para escolher.
- **FR-016**: Em cada item do wizard, "Não aprovo" DEVE abrir o chat naquele item. A IA DEVE transformar o
  pedido em ajuste e gerar de novo **só o item e o que depende dele**. Quando o pedido for ambíguo, ela
  pergunta com opções antes de gerar.
- **FR-017**: O avançado DEVE oferecer o que a 011 oferece hoje: texto, prompts, portões, modo automático e
  trocas manuais. Uma edição feita nele DEVE aparecer no wizard como efeito: item a refazer ou refeito.
- **FR-018**: O vídeo guiado DEVE **substituir** o "Novo vídeo" atual da 011: há um só caminho de criação.
  O especialista usa o switch do modo avançado. Os roteiros já criados pela 011 abrem no modo avançado.

**Reuso de cenas**
- **FR-019**: Antes de gerar keyframes, o sistema DEVE mostrar o modal de cenas. Para cada posição, ele
  traz a proposta, com uma frase de motivo:
  - **reuso total**: cena com o mesmo avatar, cenário e produto; usa os keyframes e os clipes aprovados,
    sem gerar nada;
  - **reuso do plano**: algo diferente; usa a ação, a câmera, o movimento e os trechos da cena, e gera
    keyframes e clipes novos;
  - **criar nova**.

  O modal DEVE mostrar qual dos três vale em cada posição.
- **FR-020**: A IA DEVE propor o reuso sempre que uma cena da biblioteca servir à posição. Ela só propõe
  "criar nova" quando nenhuma serve ou quando o operador pediu cenas novas.
- **FR-021**: No modal, o operador DEVE poder trocar o reuso por nova, trocar nova por qualquer cena da
  biblioteca e pedir ajuste de uma posição pelo chat.
- **FR-022**: Uma cena reaproveitada NÃO DEVE ser alterada. O reuso do plano e qualquer ajuste sobre uma
  cena reaproveitada DEVEM criar uma cena nova, derivada, com a origem registrada, que vai para a
  biblioteca.
- **FR-023**: Toda cena nova DEVE ser salva na biblioteca, com o perfil base do vídeo, os keyframes
  aprovados e o movimento, e DEVE ficar disponível para reuso em vídeos futuros.
- **FR-024**: Uma cena que mostra outro produto NÃO DEVE ser proposta para reuso num vídeo de produto
  diferente. O operador pode escolhê-la à mão, com aviso.

**Keyframes por cena**
- **FR-025**: Cada cena DEVE ter keyframe de início e keyframe de fim. Pode ter também meio 1 e meio 2,
  num total de 2 a 4.
- **FR-026**: Cada keyframe depois do de início DEVE ser gerado a partir do keyframe anterior da mesma
  sequência, para manter o avatar, o produto e o cenário. A sequência da cena (2 a 4 quadros) DEVE ser
  gerada **de uma vez** e mostrada junta para aprovação. O operador aprova a sequência ou recusa um quadro;
  o recusado e os seguintes são refeitos a partir do último quadro mantido, e a nova sequência volta para
  aprovação.
- **FR-027**: O clipe da cena DEVE ser feito de um trecho por par de keyframes vizinhos (N keyframes, N−1
  trechos). Cada trecho começa num keyframe, termina no seguinte e dura **exatamente 1 trecho-base**. Os
  trechos são colados na ordem.
- **FR-028**: Refazer um keyframe DEVE invalidar só os keyframes seguintes da mesma cena e os trechos que
  tocam os keyframes refeitos. Os outros keyframes e trechos ficam e são reaproveitados.
- **FR-029**: A **IA DEVE decidir, por cena**, quantos trechos-base a cena ocupa (de 1 a 3), conforme o
  movimento. A quantidade de keyframes é consequência: trechos + 1, de 2 a 4. Movimento simples fica com 1
  trecho (2 keyframes); giro, caminhada ou mão no produto ganham 2 ou 3. O operador pode pedir uma cena
  mais curta ou mais longa pelo chat ou no avançado.

**Grade de duração**
- **FR-030**: O sistema DEVE ter um **trecho-base** (em segundos) configurável. A duração do vídeo DEVE
  ser escolhida entre múltiplos inteiros dele, do 1× até um máximo configurável.
- **FR-031**: Cada cena DEVE durar de 1 a 3 trechos-base (inteiro). A soma das cenas DEVE ser igual à
  duração escolhida, com tolerância de ±0,5 s no vídeo final.
- **FR-032**: Cada cena DEVE ter o seu bloco de fala, que cabe na duração dela. Se a narração não couber
  com o ajuste de velocidade dentro do limite natural, o operador DEVE ser avisado, e a IA propõe um texto
  mais curto ou uma duração maior.
- **FR-033**: Um vídeo DEVE guardar a grade (trecho-base) com que foi criado. Mudar a configuração depois
  NÃO DEVE alterar vídeos existentes. A duração do vídeo PODE mudar, dentro da grade guardada, e isso refaz
  o plano a partir do texto.

**Regras que continuam**
- **FR-034**: Aprovar, recusar e escolher DEVEM ser ações de usuário humano (dono ou membro), com histórico.
  Nenhuma IA, agente ou MCP aprova.
- **FR-035**: O modo automático e os portões da 011 DEVEM continuar valendo no modo avançado. No wizard, **todos**
  os portões ficam ligados (narração, keyframes, clipes e final), e o portão de texto é o modal de cenas
  (FR-019).
- **FR-036**: O vídeo final DEVE virar um conteúdo da 014 marcado como gerado por IA, sem destino, como na
  011.
- **FR-037**: Toda mutação (escolhas, respostas, ajustes, aprovações) DEVE ir para o histórico, com autor,
  antes e depois (princípio VII).

### Key Entities

- **Vídeo guiado** (o roteiro da 011, ampliado): tipo de vídeo, perfil base, avatar, voz, cenário, produto,
  duração-alvo, grade usada (trecho-base no momento da criação), modo preferido do operador e estado do chat.
- **Conversa do vídeo**: a sequência de perguntas da IA (com as opções), as respostas do operador (cliques
  e texto curto) e os pedidos de troca do wizard, cada um com o item a que se refere, autor e data.
- **Posição do vídeo**: a cena usada (reaproveitada ou nova), o motivo da proposta, a duração em
  trechos-base e o bloco de fala.
- **Keyframe da cena**: papel (início, meio 1, meio 2 ou fim), ordem, o keyframe de que nasceu e o estado
  de aprovação.
- **Trecho da cena**: o par de keyframes que liga, a duração e o vídeo gerado. A cena montada é a colagem
  dos trechos.
- **Configuração da grade**: o trecho-base e o máximo de múltiplos oferecidos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um operador sem treino vai do "Novo vídeo" ao plano montado em **até 5 minutos**, só com
  cliques, sem digitar nada.
- **SC-002**: No modo wizard, nenhum texto de prompt ou de fala aparece em nenhuma tela do fluxo (verificável
  percorrendo o fluxo inteiro).
- **SC-003**: Com cenas adequadas na biblioteca, **100%** das posições que podem reaproveitar recebem a
  proposta de reuso, e o modal mostra a decisão de **todas** as posições antes de gerar. Uma posição em
  reuso total consome **0** geração de imagem ou vídeo.
- **SC-004**: A duração do vídeo final fica dentro de **±0,5 s** da escolhida, em 100% dos vídeos.
- **SC-005**: Um pedido de troca no wizard refaz **só** o item recusado e o que depende dele: nenhuma
  imagem ou trecho aprovado e independente é gerado de novo.
- **SC-006**: No teste com o dono, o mesmo produto do teste de 2026-10-13, com 2 ou mais keyframes por cena,
  tem **menos cenas recusadas por "delírio"** (o fim da cena diferente do planejado) do que o teste com 1
  keyframe.
- **SC-007**: Trocar de modo (wizard ↔ avançado) em qualquer etapa não perde nenhuma aprovação nem resposta
  (0 perdas no teste).
- **SC-008**: Toda cena nova aprovada fica disponível na biblioteca para o próximo vídeo, sem cadastro
  manual.

## Assumptions

- **Base existente:** a 011 (roteiro, narração, keyframes, clipes, montagem, acabamento, portões e
  automático), a 029 (biblioteca da agência com perfil base), a 025 (avatar com kit e voz padrão), a 012
  (produto aprovado com ficha), a 017 (guia e palavras proibidas) e a 021 (fila de geração local). Esta spec
  amplia a 011, não a substitui.
- **Quem usa:** dono e membro humanos criam vídeos, respondem ao chat e aprovam (como na 011). O modo
  avançado fica disponível para os dois.
- **Limite do gerador:** o gerador de vídeo aceita só um quadro inicial e um quadro final por geração. Por
  isso, os keyframes do meio viram trechos encadeados, não uma geração única.
- **Trecho-base:** o valor certo sai da medição de cada gerador, na pesquisa do plano. Hoje se usa até 5 s
  por cena. Enquanto a medição não sai, o padrão é 5 s com máximo de 6× (30 s).
- **Formato:** voice over, sem fala na câmera (decisão de 2026-10-08). As lições do pipeline continuam:
  nada de mudança de luz, quarto, paredes e luz fixos, close de lado e nunca centrado no decote, e a última
  cena termina em keyframe.
- **Tipo de vídeo:** só "Avatar & POV" agora. Outros tipos são specs futuras.
- **Custo da IA:** o chat e a montagem do plano usam a IA de texto, e o custo é registrado como no assistente
  (008). Só o dono vê valores.
- **Fora desta spec:** variantes por combinação de cenas (032), clonagem de movimento (030) e publicação
  (continua na 014/015, com aprovação humana).
