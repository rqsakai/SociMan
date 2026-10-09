# Feature Specification: Geração local com candidatos (021-geracao-local)

**Feature Branch**: `021-geracao-local`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Jobs de geração local com candidatos (insumo `docs/insumos/021-geracao-local.md`).
Todo cadastro padronizado segue o mesmo ciclo: pedir uma geração → a IA local gera N opções → o dono
escolhe → a escolhida vira o arquivo oficial. Hoje isso vive em pastas (`_candidatos/<lote>/opcao_N.png`).
O SociMan precisa de uma entidade única para esse ciclo, usada por todos os tipos de asset (e, depois, pelo
render de storyboards). Pré-requisito da 025-cadastro-padronizado (avatar, voz, cenário) e da 012
(produtos)."

## Contexto

O pipeline de referência (`../comfyui-docker/pipeline/`, só leitura) já testou os padrões que os modelos
locais precisam (rosto frontal limpo, corpo-base neutro, referência de voz de 8 a 13 s, cena 9:16 sem
pessoas, recorte e flat lay de produto; ver `PADROES.md`). Nele, cada passo gera opções numa pasta de
candidatos, para, e o dono escolhe pela linha de comando (`escolher --como kit:<passo>`). Há também um
`--auto`, que escolhe a opção 1 sem parar.

Esta spec leva esse ciclo para o SociMan como **um motor só**:
- **o pedido** (a "geração"): o que gerar, para quem, com que motor e com que entrada;
- **as opções** (os "candidatos"): as imagens ou os áudios que o motor devolveu, com as medidas de cada um;
- **a escolha humana**: só ela transforma uma opção no arquivo oficial do alvo.

Ela também cria o armazenamento de **áudios** (irmão das imagens da 003), porque os candidatos de voz são
áudio, e a fila que divide a **GPU** (RTX 5060 Ti 16 GB) entre o ComfyUI, o serviço de voz `shop-tts` e o
OpenShorts.

Os fluxos de cada cadastro (kit do avatar, voz, cenário, produto) **não** são desta spec: eles ficam na
025 e na 012, que usam este motor. Aqui entram o motor, a fila, a tela de revisão das opções, os
adaptadores dos três motores (`comfyui`, `tts`, `claude`), os áudios e a limpeza.

## Clarifications

### Session 2026-10-06

Decisões já tomadas pelo dono (não perguntar de novo):

- Q: Como o ComfyUI ganha memória para os modelos grandes? → A: O worker **sobe o limite de RAM do
  container do ComfyUI para 28 GB só durante o job `comfyui`** e **devolve para 12 GB logo em seguida**,
  inclusive quando o job falha ou é cancelado. Ao subir, o worker confere se o limite voltou; se não
  voltou, registra o erro e tenta devolver de novo antes do próximo job.
- Q: A GPU tem fila única com o OpenShorts? → A: **Não.** Antes de começar um job `comfyui` ou `tts`, o
  worker confere se a GPU está desocupada (nenhum job do OpenShorts processando e VRAM livre suficiente).
  Se não estiver, o job continua na fila e tenta de novo depois, com a mensagem "Aguardando a GPU ficar
  livre".
- Q: A voz é do perfil ou do avatar? → A: **Do perfil.** O avatar pode ter uma voz padrão
  (`assets.voz_id`, definido na 025). Para esta spec, o alvo `voz` pertence ao perfil.
- Q: O produto é do perfil ou compartilhado? → A: **Do perfil** (definido na 012). Para esta spec, o alvo
  `produto` pertence ao perfil.
- Q: O que acontece com as opções não escolhidas? → A: São **apagadas 90 dias** depois que a geração
  termina (os arquivos também). A opção escolhida **nunca** é apagada.
- Q: Existe escolha automática ("auto")? → A: **Não.** Toda escolha de opção é humana. A única exceção são
  os **passos só de texto** (ficha do produto, checagem de identidade do avatar): o resultado vai direto
  para o alvo e continua editável.
- Q: Qual passo esta spec entrega de ponta a ponta, com a GPU real (FR-030)? → A: `cenario.cena` num
  cenário da 007: instrução → 2 opções 768×1344 sem pessoas → escolher → vira arquivo do cenário. A 025
  depois liga a cena ao slot `cena`.
- Q: O `produto.recorte` (BiRefNet, um resultado só) vai direto para o alvo (FR-031)? → A: Sim. O recorte é
  determinístico (sem seed nem opções) e vai direto, como os passos de texto. A conferência humana fica na
  aprovação do produto (012), que mostra todos os recortes. A exceção da decisão 6 passa a ser "passos só
  de texto e passos de resultado único e determinístico".
- Q (coordenado com a 025, 2026-10-07): Como fica a opção de `avatar.rostos_34`, que é um par? → A: Um passo
  só; **cada opção é um par** (imagem esquerda + imagem direita), e escolher a opção preenche os dois
  slots. A escolha continua uma só (`escolhido_id` aponta um candidato).
- Q (coordenado com a 025, 2026-10-07): Como o "Testar" da voz (texto livre narrado com a voz aprovada)
  passa pela fila da GPU? → A: Passo novo **`voz.teste`** (motor `tts`, alvo `voz`, 1 opção, resultado
  áudio). Ele não muda o alvo e não tem escolha: termina num estado final novo, **`entregue`**, e o áudio
  entra na limpeza de 90 dias.
- Q: Como a limpeza de 90 dias (e a revogação LGPD da 025), que apagam de fato, convivem com o princípio
  VII? → A: Por uma **emenda da constitution 4.2.0 → 4.3.0**: o princípio VII ganha 2 exceções nomeadas
  (limpeza de candidatos não escolhidos e revogação LGPD), cada apagamento auditado por evento. A emenda
  é **pré-requisito** desta spec e será a 1ª tarefa da implementação.
- Q: Como o worker muda a RAM do container do ComfyUI sem ganhar poder de root sobre o host? → A: O plano
  propõe um proxy do socket do Docker restrito a `update` do container `comfyui`, e o dono decide no
  plano.

### Session 2026-10-07 (decisões do plano)

- Q (D1): Onde fica o acesso ao Docker? → A: Num container **`dockerctl`** mínimo, o **único** com o
  socket do Docker. Ele aceita 3 ações fixas sem parâmetros, fica numa rede `internal` só com o gerador,
  exige token e roda com `read_only`, `cap_drop ALL` e `no-new-privileges`.
- Q (D2): Como alcançar o ComfyUI e o shop-tts, que escutam em `127.0.0.1`? → A: Pela rede Docker externa
  **`gpu-local`**, com `comfyui`, `shop-tts` e só o gerador. A mudança no compose do `../comfyui-docker` é
  uma dependência externa.
- Q (D3): Quando muda o contrato do shop-tts? → A: **Antes da 025**, feito pelo dono ou noutra sessão, no
  `../comfyui-docker`. Na 021, o motor de voz é testado contra o fake do contrato novo.
- A emenda 4.3.0 teve o texto da exceção (2) ajustado: na revogação LGPD, são apagados os arquivos e os
  textos que descrevem a pessoa (inclusive em versões antigas do histórico); fica só o registro de que
  houve consentimento e revogação (texto final na T001).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pedir uma geração e escolher uma das opções (Priority: P1)

Numa tela de cadastro (o piloto desta spec é a cena de um cenário; ver FR-030), o dono pede uma geração:
escreve a instrução e, se o passo pedir, escolhe as referências. O SociMan cria o pedido "na fila" e
mostra o andamento ("Gerando opção 2 de 2", com porcentagem). Quando termina, a tela mostra as opções lado
a lado, numeradas ("Opção 1", "Opção 2"), em tamanho bom para comparar. O dono clica em **"Usar opção N"**:
a opção vira o arquivo oficial do alvo, e o histórico do alvo registra que ela veio daquela geração.

**Why this priority**: É o ciclo que todas as specs de cadastro (025, 012) vão usar. Sem ele, os
candidatos continuam em pastas fora do SociMan.

**Independent Test**: Com o ComfyUI falso dos testes, pedir a cena de um cenário de teste com 2 opções,
esperar a revisão, escolher a opção 2 e conferir que:
- o cenário ganhou o arquivo da opção 2;
- a nova versão do cenário aponta a geração de origem;
- a geração está "escolhida", com a opção 2 marcada;
- a opção 1 continua visível na geração até a limpeza.

**Acceptance Scenarios**:

1. **Given** um cenário do perfil, **When** o dono pede a cena com uma instrução, **Then** é criada uma
   geração "na fila", com o passo, o motor, a entrada resolvida, o número de opções (padrão 2) e o autor
   do pedido, e a tela mostra o andamento.
2. **Given** a geração rodando, **When** o worker avança, **Then** a tela mostra a porcentagem e a
   mensagem curta da etapa em pt-BR, sem precisar recarregar.
3. **Given** a geração em revisão com 2 opções, **When** o dono clica em "Usar opção 2", **Then** a opção
   vira o arquivo oficial do alvo, a geração passa a "escolhida" (final) e a nova versão do alvo grava a
   geração de origem.
4. **Given** uma geração já escolhida, **When** alguém tenta escolher outra opção, **Then** é recusado
   ("esta geração já foi decidida"), e o caminho é pedir uma nova geração.
5. **Given** a tela de revisão, **When** um membro humano escolhe uma opção, **Then** a escolha vale como
   a do dono (é humana). **When** um cliente MCP, agente ou IA tenta escolher, **Then** é recusado com
   "somente humano", e a recusa fica registrada.
6. **Given** uma geração em revisão, **When** o dono abre a geração mais tarde, **Then** as opções, as
   seeds e as medidas de cada uma continuam lá.

---

### User Story 2 - A fila respeita a GPU e a memória (Priority: P1)

O dono pede várias gerações seguidas, às vezes com o OpenShorts cortando um vídeo ao mesmo tempo. O SociMan
roda **um job de GPU por vez** (`comfyui` ou `tts`) e só começa quando a GPU está livre. Enquanto espera,
o job mostra "Aguardando a GPU ficar livre". Antes de um job do ComfyUI, o SociMan dá mais memória ao
ComfyUI e, quando o job termina (bem, mal ou cancelado), devolve a memória ao normal. Entre o ComfyUI e o
serviço de voz, o SociMan libera a VRAM de um antes de usar o outro. As chamadas ao Claude não esperam a
GPU.

**Why this priority**: Sem isso, dois modelos disputam os 16 GB da GPU e falham por falta de memória, ou o
ComfyUI fica preso com 28 GB de RAM e a máquina inteira sofre.

**Independent Test**: Com os serviços falsos, enfileirar 3 gerações `comfyui`, 1 `tts` e 1 `claude`,
marcar a GPU como ocupada pelo OpenShorts e conferir que:
- nenhuma geração de GPU começa e todas mostram "Aguardando a GPU ficar livre";
- a `claude` roda e termina;
- ao liberar a GPU, as de GPU rodam uma de cada vez, em ordem de pedido;
- o limite de RAM do ComfyUI sobe antes de cada job `comfyui` e volta a 12 GB depois de cada um,
  inclusive num job que falha e num que é cancelado;
- a VRAM do ComfyUI é liberada antes do job `tts`, e a do `tts` antes do próximo `comfyui`.

**Acceptance Scenarios**:

1. **Given** um job `comfyui` rodando, **When** o dono pede outra geração `comfyui` ou `tts`, **Then** ela
   fica "na fila" até a primeira terminar.
2. **Given** o OpenShorts processando um corte ou pouca VRAM livre, **When** chega a vez de um job de GPU,
   **Then** ele continua "na fila", com a mensagem "Aguardando a GPU ficar livre" e a próxima tentativa
   agendada, sem contar como falha.
3. **Given** um job `comfyui` que vai começar, **When** o worker o pega, **Then** sobe o limite de RAM do
   ComfyUI para 28 GB antes de mandar o trabalho, e **When** o job termina, falha ou é cancelado, **Then**
   devolve o limite para 12 GB e confere que voltou.
4. **Given** o limite que não voltou para 12 GB (falha ao devolver ou worker reiniciado no meio), **When**
   o worker sobe ou vai pegar o próximo job, **Then** registra o erro, tenta devolver de novo e só pega um
   job de GPU depois de confirmar os 12 GB.
5. **Given** o serviço de voz respondendo "ocupado" (503) ou o ComfyUI sem memória na GPU, **When** o job
   está rodando, **Then** ele volta para "na fila" com espera crescente, a mensagem diz o motivo, e as
   tentativas são contadas.
6. **Given** uma geração `claude` (passo só de texto), **When** há um job de GPU rodando ou esperando,
   **Then** a `claude` roda mesmo assim.

---

### User Story 3 - Acompanhar, cancelar, tentar de novo e gerar outras (Priority: P2)

O dono vê as gerações do perfil (e as de cada alvo) com o estado, o andamento e o erro em pt-BR. Pode
**cancelar** qualquer geração que ainda não terminou, **tentar de novo** uma que falhou e, numa geração
em revisão de que não gostou de nenhuma opção, **gerar outras** (seeds novas). A antiga fica
"descartada", e a nova aparece no lugar.

**Why this priority**: Modelos locais erram com frequência (rosto que muda, corte que entra no produto). O
dono precisa refazer sem sair da tela e sem perder o que já foi gerado.

**Independent Test**: Com os serviços falsos, cancelar uma geração na fila e outra rodando, forçar uma
falha e tentar de novo, e pedir "gerar outras" numa em revisão. Conferir os estados finais, a mensagem de
erro, as seeds diferentes e o histórico com o autor de cada ação.

**Acceptance Scenarios**:

1. **Given** uma geração "na fila" ou "rodando", **When** o dono cancela (com confirmação), **Then** ela
   passa a "cancelada" (final), o motor é avisado para parar quando possível e nenhuma opção dela pode ser
   escolhida.
2. **Given** uma geração "em revisão", **When** o dono cancela, **Then** ela passa a "cancelada" e o alvo
   não muda.
3. **Given** uma geração que falhou, **When** o dono clica em "Tentar de novo", **Then** ela volta para
   "na fila" com a mesma entrada, e o erro anterior fica no histórico.
4. **Given** uma geração em revisão, **When** o dono clica em "Gerar outras", **Then** é criada uma geração
   nova com a mesma entrada e **seeds novas**, a antiga passa a "descartada" (final) e a nova entra na
   fila.
5. **Given** um erro do motor, **When** a geração falha, **Then** a tela mostra uma mensagem em pt-BR para
   cada código (`gpu_ocupada`, `servico_fora`, `sem_memoria`, `entrada_invalida`, `internal`), sem
   detalhes técnicos crus.
6. **Given** uma geração em estado final, **When** alguém tenta cancelar, tentar de novo ou gerar outras,
   **Then** é recusado com o motivo.

---

### User Story 4 - Passos só de texto vão direto para o alvo (Priority: P2)

Alguns passos não produzem imagem nem áudio, só texto estruturado, escrito pelo Claude: a **ficha do
produto** (`produto.ficha`, da 012) e a **checagem de identidade** do avatar (`avatar.identidade`, da 025).
Nesses passos não há opções para escolher: o resultado é gravado direto no alvo, marcado como "feito pela
IA", e o dono pode editá-lo como qualquer outro campo. A chamada entra no registro do assistente de IA
(008), com o custo.

**Why this priority**: A ficha precisa ficar gravada antes de qualquer passo de GPU (se a GPU falhar, não
se paga o Claude de novo). Sem esta história, a 012 e a 025 não fecham.

**Independent Test**: Com o Claude falso, rodar um passo só de texto num alvo de teste e conferir que:
- a geração vai de "rodando" direto a "escolhida", sem revisão;
- o resultado está no alvo, numa versão com a geração de origem e o autor do pedido;
- a chamada aparece no registro do assistente com custo;
- uma edição manual depois salva normalmente.

**Acceptance Scenarios**:

1. **Given** um passo só de texto, **When** o Claude responde, **Then** o resultado vai para o alvo na
   mesma hora e a geração termina como "escolhida", sem passar por "em revisão".
2. **Given** um passo só de texto, **When** a geração é criada, **Then** ela não espera a GPU.
3. **Given** a chamada ao Claude, **When** ela termina (com sucesso ou erro), **Then** fica no registro de
   chamadas do assistente de IA (008), com o custo aproximado.
4. **Given** um resultado de texto já gravado, **When** o dono o edita, **Then** a edição é salva como
   mudança humana, com histórico.
5. **Given** a chave do Claude ausente, **When** um passo só de texto é pedido, **Then** a geração falha
   com mensagem clara (sem ficar presa na fila).

---

### User Story 5 - Áudios guardados e ouvidos no SociMan (Priority: P2)

O SociMan passa a guardar **áudios** como guarda imagens: o dono envia uma gravação (wav, m4a, ogg ou mp3,
até 25 MB), e o motor de voz devolve candidatos e testes em áudio. Cada áudio tem duração, formato e taxa
de amostragem, e toca na tela de revisão com o player do navegador, inclusive avançando no meio do áudio.
O serviço de voz passa a receber e devolver arquivos (e não caminhos de pasta), e a voz aprovada pode ser
**importada** no serviço de voz, porque a fonte da verdade passa a ser o SociMan.

**Why this priority**: É a base da voz da 025. Sem guardar áudio, os candidatos de voz ficariam presos na
pasta do serviço.

**Independent Test**: Enviar um wav e um m4a de teste, conferir duração, formato, taxa de amostragem e
impressão digital gravados, e tocar pelo link com avanço. Com o serviço de voz falso, rodar uma geração
`tts` e conferir os candidatos de áudio com as medidas (segundos, similaridade, transcrição, áudio de
teste).

**Acceptance Scenarios**:

1. **Given** uma gravação válida até 25 MB, **When** o dono a envia, **Then** o áudio é guardado no
   armazenamento do HD com duração, formato, taxa de amostragem e impressão digital, ligado ao perfil.
2. **Given** um arquivo acima de 25 MB, de outro formato ou que não é áudio de verdade, **When** o dono o
   envia, **Then** é recusado com o motivo, e nada é guardado.
3. **Given** um candidato de voz, **When** o dono abre a revisão, **Then** ouve o candidato e o áudio de
   teste dele, e vê os segundos, a similaridade e a transcrição.
4. **Given** um áudio guardado, **When** alguém tenta mudá-lo, **Then** não há como: o áudio é imutável.
5. **Given** o HD sem o marcador ou abaixo do piso de espaço livre, **When** um áudio seria gravado,
   **Then** a gravação é recusada com a mesma mensagem das imagens e dos vídeos.

---

### User Story 6 - Limpeza das opções não escolhidas (Priority: P3)

Noventa dias depois que uma geração termina, o SociMan apaga as opções que não foram escolhidas e os
arquivos delas. A opção escolhida nunca é apagada. A geração continua na lista, com a indicação "opções
não escolhidas removidas em <data>".

**Why this priority**: Cada geração de avatar deixa 2 a 4 imagens grandes que ninguém vai usar. A limpeza
evita encher o HD, mas pode esperar: nos primeiros 90 dias nada é apagado.

**Independent Test**: Semear gerações terminadas há 89 e há 91 dias (escolhidas, descartadas, canceladas
e com falha), rodar a limpeza e conferir que só as de 91 dias perderam as opções não escolhidas, que o
arquivo escolhido continua e que rodar de novo não faz nada.

**Acceptance Scenarios**:

1. **Given** uma geração escolhida que terminou há mais de 90 dias, **When** a limpeza roda, **Then** as
   opções não escolhidas e os arquivos delas são apagados, e a escolhida continua intacta.
2. **Given** uma geração descartada, cancelada ou com falha que terminou há mais de 90 dias, **When** a
   limpeza roda, **Then** todas as opções dela e os arquivos são apagados.
3. **Given** uma geração em revisão (sem fim), **When** a limpeza roda, **Then** nada dela é apagado, por
   mais antiga que seja.
4. **Given** um arquivo de opção não escolhida que também está em uso em outro lugar, **When** a limpeza
   roda, **Then** esse arquivo não é apagado.
5. **Given** a limpeza já rodada, **When** ela roda de novo, **Then** não apaga nada novo.

---

### Edge Cases

- **Worker reiniciado no meio de um job:** a geração que estava "rodando" volta para "na fila" (com a
  tentativa contada) e o limite de RAM do ComfyUI é conferido e devolvido antes de qualquer outro job.
- **Cancelar durante o envio ao ComfyUI:** o cancelamento vale; o resultado que chegar depois é
  descartado, sem virar opção.
- **Duas abas escolhendo opções diferentes ao mesmo tempo:** só a primeira escolha vale. A outra recebe
  "esta geração já foi decidida".
- **Alvo mudou entre o pedido e a escolha** (outra pessoa trocou o arquivo do alvo): a escolha usa o
  controle de versão do alvo e devolve conflito, com "recarregue e escolha de novo".
- **Alvo arquivado:** não aceita geração nova. As gerações abertas dele podem ser canceladas, mas não
  escolhidas, até o alvo ser restaurado.
- **Motor devolve menos opções do que o pedido:** a geração vai para revisão com as que vieram, e a tela
  diz "veio 1 de 2". Se não vier nenhuma, falha com `internal`.
- **Serviço fora do ar** (ComfyUI, serviço de voz): a geração volta para a fila com espera crescente e,
  depois do limite de tentativas, falha com `servico_fora`.
- **GPU ocupada por muito tempo:** a geração espera sem prazo e sem virar falha, sempre com "Aguardando a
  GPU ficar livre" e a hora da próxima tentativa. O dono pode cancelar.
- **Referência que deixou de existir ou foi arquivada antes do job começar:** a geração falha com
  `entrada_invalida`, dizendo qual referência.
- **HD desmontado** durante o job: a geração falha sem gravar nada fora do HD, e a mensagem é a mesma das
  outras gravações.
- **Seeds repetidas:** "Gerar outras" nunca repete uma seed já usada naquele alvo e passo.
- **Passo só de texto com resposta fora do formato:** a geração falha com `entrada_invalida` ou
  `internal`, nada vai para o alvo, e a chamada fica no registro da 008 com o erro.
- **Arquivo da opção escolhida em uso:** nunca é apagado, nem pela limpeza nem por "Gerar outras".
- **Permissão por perfil:** o SociMan não tem acesso por perfil (todo usuário vê todos os perfis); as
  gerações seguem a mesma regra das outras telas do perfil.

## Requirements *(mandatory)*

### Functional Requirements

**Geração e opções**

- **FR-001**: O SociMan DEVE ter uma entidade única de **geração** (o pedido) para todo ciclo "pedir →
  gerar opções → escolher", com: perfil, alvo (tipo `asset`, `voz` ou `produto`, e o id do alvo), passo,
  motor (`comfyui`, `tts` ou `claude`), entrada resolvida, número de opções, estado, andamento, mensagem
  da etapa, tentativas, próxima tentativa, erro, opção escolhida, início, fim e autor do pedido.
- **FR-002**: O **passo** DEVE ser um de uma lista fechada: `avatar.rosto_origem`, `avatar.rosto_frontal`,
  `avatar.rostos_34`, `avatar.corpo_base`, `avatar.look`, `avatar.pose`, `avatar.identidade`,
  `voz.gravacao`, `voz.design`, `voz.teste`, `produto.ficha`, `produto.recorte`, `produto.flat`,
  `cenario.cena`, `cenario.variacao` (15 passos). Cada passo DEVE ter, no código, o motor, o tipo de alvo aceito, o tipo de resultado
  (imagem, áudio ou só texto) e o número padrão de opções.
- **FR-003**: O número de opções DEVE ter padrão **2**, com **4** no `avatar.rosto_origem` e **até 3** nos
  passos de voz.
- **FR-004**: A **entrada resolvida** DEVE guardar tudo o que o motor recebe: instrução ou prompt, as
  referências (ids de imagem), as seeds, o número de opções e o rótulo (nome do look, da pose ou da
  variação). Ela DEVE bastar para "Tentar de novo" e "Gerar outras" sem perguntar nada ao dono.
- **FR-005**: Cada **opção** (candidato) DEVE ter o número que o dono vê (1..n), a imagem **ou** o áudio
  dela, a seed (quando houver) e as medidas por tipo:
  - voz: segundos, similaridade, transcrição e o áudio de teste;
  - identidade: nota e observação.

  Uma opção DEVE ter exatamente uma imagem ou um áudio, com duas exceções:
  - nos passos só de texto (`produto.ficha`, `avatar.identidade`), não há mídia, e o resultado fica nas
    medidas e no alvo;
  - no `avatar.rostos_34`, a opção é um **par**: a imagem do lado esquerdo e a do lado direito.
- **FR-006**: As referências, as opções e o alvo DEVEM pertencer ao **mesmo perfil** da geração.

**Estados e ações (US1, US3)**

- **FR-007**: A geração DEVE seguir os estados:
  - `na_fila` → `rodando` (o worker pega);
  - `rodando` → `revisao` (opções prontas), → `na_fila` (GPU ocupada, serviço respondendo "ocupado" ou
    sem memória, com espera) ou → `falhou` (erro);
  - `revisao` → `escolhido` ("Usar opção N") ou → `descartada` ("Gerar outras");
  - `falhou` → `na_fila` ("Tentar de novo");
  - `rodando` → `entregue` (só no `voz.teste`: o áudio fica pronto para ouvir, sem escolha e sem mudar o
    alvo);
  - qualquer estado não final → `cancelada`.

  `escolhido`, `descartada`, `cancelada` e `entregue` são finais. Nenhum outro caminho é aceito.
- **FR-008**: **Toda escolha de opção DEVE ser humana.** Não existe escolha automática nem "usar a opção
  1" (as únicas exceções são os passos sem escolha do FR-010 e do FR-031). Só um usuário humano (dono ou membro) pode escolher; outro ator (IA, agente, cliente MCP) DEVE ser
  recusado com "somente humano", e a recusa DEVE ficar registrada como nas ações exclusivas de humano da
  015.
- **FR-009**: **Escolher** DEVE, numa transação só:
  - copiar a referência da opção para o alvo (por exemplo, o arquivo vira o arquivo do alvo);
  - gravar a nova versão do alvo no histórico, com a geração de origem nos detalhes e o humano que
    escolheu como autor;
  - marcar a geração como `escolhido`, com a opção escolhida.

  Escolher numa geração que não está em `revisao` DEVE ser recusado. Duas escolhas simultâneas DEVEM
  resultar em uma só.
- **FR-010**: **Passos só de texto** (`produto.ficha`, `avatar.identidade`) DEVEM ir de `rodando` direto
  para `escolhido`: o resultado vai para o alvo sem revisão, marcado como feito pela IA, numa versão do
  alvo com a geração de origem e o autor do pedido. O resultado DEVE continuar editável pelo save normal
  do alvo.
- **FR-011**: **Cancelar** DEVE valer para `na_fila`, `rodando`, `revisao` e `falhou`, pedir confirmação
  e avisar o motor para parar quando possível. Resultado que chegar depois de cancelar DEVE ser
  descartado.
- **FR-012**: **Tentar de novo** (só em `falhou`) DEVE recolocar a geração em `na_fila` com a mesma
  entrada, zerar a espera e manter o erro anterior no histórico.
- **FR-013**: **Gerar outras** (só em `revisao`) DEVE criar uma geração nova com a mesma entrada e
  **seeds novas** (nunca uma já usada naquele alvo e passo) e marcar a antiga como `descartada`, na mesma
  transação.
- **FR-014**: Pedir, cancelar, tentar de novo, gerar outras e escolher DEVEM ser ações de usuário humano
  (dono ou membro) e DEVEM ficar no histórico com o autor, a data e o estado anterior
  (princípio VII). As mudanças feitas pelo worker (andamento, espera, erro, opções) são estado de job,
  como no envio da 006.
- **FR-015**: Alvo arquivado NÃO DEVE aceitar geração nova nem escolha; suas gerações abertas podem ser
  canceladas.

**Andamento e erros**

- **FR-016**: O andamento DEVE ser uma porcentagem de 0 a 100 e uma mensagem curta em pt-BR ("Gerando
  opção 2 de 2", "Aguardando a GPU ficar livre"), atualizada pelo worker e vista na tela sem recarregar.
- **FR-017**: Os erros DEVEM usar os códigos `gpu_ocupada`, `servico_fora`, `sem_memoria`,
  `entrada_invalida` e `internal`, cada um com uma mensagem em pt-BR para a tela. Detalhes técnicos ficam
  no log.
- **FR-018**: Serviço de voz respondendo "ocupado" (503), falta de memória no ComfyUI e serviço fora do ar
  DEVEM devolver a geração para `na_fila` com espera crescente e contar a tentativa; depois do limite de
  tentativas (padrão 6), a geração vai para `falhou`. Um erro de entrada ou interno leva a `falhou` na
  hora. A espera pela **GPU ocupada** NÃO conta tentativa e NÃO DEVE virar falha.

**Fila e GPU (US2)**

- **FR-019**: No máximo **um** job `comfyui` ou `tts` DEVE rodar por vez, na ordem de pedido. Jobs
  `claude` DEVEM rodar fora dessa fila.
- **FR-020**: Antes de começar um job `comfyui` ou `tts`, o worker DEVE conferir que a GPU está
  desocupada: nenhum job do OpenShorts processando e VRAM livre suficiente. Se não estiver, o job DEVE
  continuar `na_fila` com "Aguardando a GPU ficar livre" e a próxima tentativa agendada. Não há fila única
  com o OpenShorts.
- **FR-021**: Antes de um job `comfyui`, o worker DEVE subir o limite de RAM do container do ComfyUI para
  **28 GB** e, ao fim do job (sucesso, falha ou cancelamento), devolvê-lo para **12 GB** e conferir que
  voltou. Ao iniciar, o worker DEVE conferir o limite; se não estiver em 12 GB, DEVE registrar o erro e
  devolver antes de pegar o próximo job de GPU.
- **FR-022**: O worker DEVE liberar a VRAM do ComfyUI antes de chamar o serviço de voz, e a do serviço de
  voz antes de chamar o ComfyUI.
- **FR-023**: Uma geração `rodando` cujo worker parou DEVE voltar para `na_fila` quando o worker voltar,
  com a tentativa contada.

**Motores**

- **FR-024**: O motor `comfyui` DEVE usar os blocos de workflow do pipeline (`cutout`, `keyframe`,
  `retrato`, `cena`), preenchendo os parâmetros pelo contrato de cada bloco, sem editar o workflow.
- **FR-025**: O motor `tts` DEVE usar o serviço de voz (`shop-tts`) para cadastrar uma gravação, desenhar
  uma voz sintética, aprovar, narrar frases e narrar um parágrafo, **enviando e recebendo arquivos** (e
  não caminhos de pasta). O serviço de voz DEVE ganhar uma rota para **importar** uma voz aprovada (áudio
  de referência e transcrição), porque a fonte da verdade da voz passa a ser o SociMan.
- **FR-026**: O motor `claude` DEVE registrar cada chamada no registro do assistente de IA (008), com
  custo aproximado e desfecho, inclusive com erro.
- **FR-027**: Nenhum motor DEVE falar com rede social nem publicar nada (princípio I). O SociMan só fala
  com o ComfyUI, o serviço de voz, o Claude e o ajuste de memória (`dockerctl`, D1) nesta spec.

**Áudios (US5)**

- **FR-028**: O SociMan DEVE guardar **áudios** como guarda imagens: imutáveis, ligados ao perfil, no
  armazenamento do HD (com o marcador e o piso de espaço livre), com formato, taxa de amostragem, duração
  e impressão digital, e com autor e data.
- **FR-029**: O envio de áudio DEVE aceitar wav, m4a, ogg e mp3 até **25 MB**, conferidos pelo conteúdo
  (e não só pela extensão). Os áudios DEVEM tocar por link assinado, com avanço no meio do áudio (como os
  vídeos da 004).

**Piloto e limpeza**

- **FR-030**: Esta spec DEVE entregar o ciclo completo do passo **`cenario.cena`** num cenário da 007,
  para provar o motor de ponta a ponta com a GPU real: instrução (e foto de referência opcional) → 2
  opções 768×1344 sem pessoas → "Usar opção N" → a opção vira arquivo do cenário, numa versão com a
  geração de origem.
- **FR-031**: O **`produto.recorte`** (resultado único e determinístico, sem seed nem opções) DEVE ir de
  `rodando` direto para `escolhido`, como os passos só de texto: o recorte vai para o alvo sem revisão,
  numa versão com a geração de origem e o autor do pedido. A conferência humana fica na aprovação do
  produto (012). Nenhum outro passo de imagem ou áudio pula a revisão.
- **FR-032**: (Pré-requisito: emenda 4.3.0 da constitution, ver Clarifications.) As opções **não escolhidas** e os arquivos delas DEVEM ser apagados **90 dias** depois do
  fim da geração (`escolhido`, `descartada`, `cancelada`, `entregue` ou `falhou`). A opção escolhida e qualquer
  arquivo em uso por outra entidade NUNCA DEVEM ser apagados. A geração DEVE continuar listada, com a data
  da limpeza. A limpeza DEVE ser idempotente e não apaga gerações em `revisao`, `na_fila` ou `rodando`.
  Cada apagamento DEVE ser auditado por evento (o que foi apagado, quando e por qual exceção do princípio
  VII).

### Key Entities

- **Geração:** o pedido de uma geração para um alvo de um perfil. Guarda o alvo (asset, voz ou produto), o
  passo, o motor, a entrada resolvida, o número de opções, o estado, o andamento, a mensagem, as
  tentativas e a próxima tentativa, o erro, a opção escolhida, o início, o fim e o autor do pedido.
  Estados: `na_fila`, `rodando`, `revisao`, `escolhido`, `descartada`, `cancelada`, `entregue`, `falhou`.
- **Opção (candidato):** uma das saídas de uma geração. Tem o número que o dono vê, uma imagem, um par de
  imagens (`avatar.rostos_34`) ou um áudio (ou nada, nos passos só de texto), a seed e as medidas por tipo. Pode ser apagada pela limpeza, exceto a
  escolhida.
- **Áudio:** arquivo de áudio imutável do perfil (irmão da imagem da 003), com formato, taxa de
  amostragem, duração e impressão digital. Só é apagado pelas duas exceções da 4.3.0: a limpeza das opções
  não escolhidas (aqui) e a revogação LGPD (025).
- **Alvo:** quem recebe o resultado escolhido. Nesta spec, um asset da 007; a voz (025) e o produto (012)
  usam o mesmo motor quando existirem. Cada escolha vira uma versão do alvo com a geração de origem.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono pede uma geração do piloto e escolhe uma opção em menos de 1 minuto de cliques (sem
  contar o tempo da GPU), sem sair da tela do alvo.
- **SC-002**: Em 100% dos testes, nenhum job de GPU começa com outro job de GPU rodando ou com a GPU
  marcada como ocupada.
- **SC-003**: Em 100% dos testes de job `comfyui` (sucesso, falha, cancelamento e worker reiniciado), o
  limite de RAM do ComfyUI está em 12 GB antes do próximo job de GPU.
- **SC-004**: 0 escolhas de opção aceitas de IA, agente ou cliente MCP, e 0 escolhas automáticas
  (verificado por teste).
- **SC-005**: 100% das escolhas geram uma versão do alvo com a geração de origem e o autor humano.
- **SC-006**: Depois da limpeza, 0 opções não escolhidas com mais de 90 dias continuam guardadas, e 100%
  das opções escolhidas continuam intactas.
- **SC-007**: Todo passo só de texto deixa uma chamada no registro do assistente de IA com custo
  (verificado por teste).

## Assumptions

- **Alvos que já existem:** nesta spec, só o alvo `asset` (007) existe. Os alvos `voz` e `produto` entram
  no tipo de alvo desde já, mas só passam a ser usados quando a 025 (vozes) e a 012 (produtos) criarem as
  tabelas. Os passos de cada fluxo (o kit do avatar, a análise e o corte da voz, a ficha e o flat do
  produto) são definidos nessas specs.
- **Quem pede:** dono e membro humanos. O MCP (009) não ganha ferramentas de geração
  nesta spec; se ganhar depois, poderá no máximo ler, nunca escolher.
- **Seeds:** cada opção tem a sua seed; "Gerar outras" escolhe seeds novas de forma determinística a
  partir das já usadas.
- **Ordem da fila:** a ordem de pedido; não há prioridade nem reordenação nesta spec.
- **"VRAM livre suficiente":** um piso fixo no código por motor, calibrado no plano com os blocos do
  pipeline. "Job do OpenShorts processando" usa o que o SociMan já sabe dos envios da 006 e o que o
  OpenShorts informa.
- **Ambiente:** o ComfyUI e o serviço de voz rodam no host (projeto `../comfyui-docker`), na mesma GPU, e
  continuam fora do compose do SociMan. São alcançados só pela rede `gpu-local` (D2).
- **Fora do escopo:** render de storyboards e vídeos (spec futura do motor de cenas); LoRA por avatar;
  edição manual de áudio; fila única com o OpenShorts; prioridade de jobs.
- **Dependências:** emenda 4.3.0 da constitution (exceções nomeadas do princípio VII); imagens e armazenamento no HD (003, 004); assets e o histórico deles (007); registro
  de chamadas do assistente de IA (008); padrão de job, trilha e worker da 004/006; ações só de humano e
  registro de recusa da 015; histórico (princípio VII).

## Notas para o plano

Detalhes técnicos do insumo que a spec não fixa como requisito de negócio, mas que o plano deve seguir.

**`geracoes`**:
- `id` uuid PK; `perfil_id` FK → perfis; `alvo_tipo` enum `geracao_alvo` (`asset`, `voz`, `produto`);
  `alvo_id` uuid (sem FK: alvo polimórfico);
- `passo` text com CHECK da lista do FR-002; `motor` enum `geracao_motor` (`comfyui`, `tts`, `claude`);
- `params` jsonb (instrução/prompt, referências por `image_id`, seeds, `n`, rótulo);
- `n_opcoes` smallint (padrão 2; `avatar.rosto_origem` 4; voz até 3);
- `status` enum `geracao_status` (`na_fila`, `rodando`, `revisao`, `escolhido`, `descartada`, `cancelada`,
  `entregue`, `falhou`); `progress` smallint 0..100; `etapa_mensagem` text null;
- `attempts`, `next_attempt_at`; `error_code`, `error_message` text null;
- `escolhido_id` uuid null FK → geracao_candidatos; `started_at`, `finished_at` timestamptz null;
- AuditMixin (`created_by` = quem pediu).

**`geracao_candidatos`**: `id` uuid PK; `geracao_id` FK; `numero` smallint 1..n; `image_id` uuid null FK →
images; `image_par_id` uuid null FK → images (lado direito do par, só `avatar.rostos_34`); `audio_id` uuid
null FK → audios; `seed` bigint null; `metricas` jsonb (voz:
`{segundos, similaridade, transcricao, teste_audio_id}`; identidade: `{nota, observacao}`); `created_at`.
CHECK: exatamente um de `image_id`/`audio_id`, exceto passos só de texto.

**`audios`**: `id`, `perfil_id`, `object_key` (`perfis/{perfil_id}/{uuid}.wav`), `formato`, `sample_rate`,
`duracao_ms`, `sha256`, `created_at`/`created_by`. Imutável; só a limpeza de 90 dias apaga.

**Worker (trilha `geracao`)**:
- ComfyUI: blocos de `workflows/api/*.params.json` preenchidos como o `run_block` do pipeline
  (`run_storyboard.py`); liberar VRAM com `POST /free` (`unload_models`, `free_memory`) antes do TTS e
  `POST /unload` do shop-tts antes do ComfyUI;
- shop-tts: `/voices/register`, `/voices/design`, `/voices/approve`, `/tts`, `/tts_paragraph`. Mudança de
  contrato: hoje recebem caminhos (`/in`, `/out`, `/vozes`); passar a multipart ou URL assinada do MinIO,
  e uma rota nova de importar voz aprovada (wav + transcrição). É mudança no projeto `../comfyui-docker`,
  fora do repositório do SociMan;
- RAM: equivalente a `docker update --memory 28g --memory-swap 28g comfyui` e volta a 12g (comentário do
  `../comfyui-docker/docker-compose.yml`), num `finally`, com conferência ao subir. O worker precisa de
  acesso ao Docker (ver riscos abaixo);
- GPU livre: estado dos envios da 006 (`processando`) + VRAM livre medida (ex.: `nvidia-smi`), com piso
  por motor; backoff em `next_attempt_at`;
- claim com `SKIP LOCKED` (padrão da fila de cortes da 004), com a regra "um job de GPU por vez" garantida
  no banco (ex.: advisory lock ou índice parcial em `status = 'rodando' AND motor IN ('comfyui','tts')`).

**Rede e edge**:
- o ComfyUI publica em `127.0.0.1:8188` e o shop-tts em `127.0.0.1:8200`. Pelo `host.docker.internal`
  (como o OpenShorts na 006), portas presas ao loopback do host **não** são alcançadas: o plano precisa de
  outra ligação (rede Docker compartilhada ou bind no IP do bridge), sem abrir na LAN;
- o envio de áudio de 25 MB passa do limite geral do edge (8 MB): precisa de `location` própria (ex.: 26m),
  como as rotas de upload grande da 004/007;
- os links de áudio usam o `midia.py` (HMAC, com Range), com um `MidiaKind` novo.

**Histórico**: o insumo não lista `version` em `geracoes`. Para registrar as ações humanas do FR-014 com o
`history.py`, o plano decide entre dar `version` e `entity_type = "geracao"` à geração (como o envio da
006) ou registrar só na versão do alvo e nas colunas de auditoria (o que não cobre cancelar e tentar de
novo).

**Riscos que o plano precisa tratar**:
1. **Apagar arquivos x "nada é apagado":** resolvido pela emenda 4.3.0 da constitution (Clarifications),
   que é a 1ª tarefa da implementação. A limpeza apaga linhas de `geracao_candidatos`, `images`, `audios`
   e objetos do MinIO; o `storage.py` ganha um delete restrito a essa exceção, e cada apagamento gera um
   evento de auditoria. A regra "`images` nunca apagada" da 003/007 passa a ter essa exceção.
2. **Acesso ao Docker pelo worker:** decidido (D1 = A): o container `dockerctl` mínimo é o único com o
   socket (princípios V e VIII, em "Complexity Tracking").
3. **`avatar.rostos_34` gera "2 pares"** (esquerda + direita): resolvido com a 025 (Clarifications): a
   opção é um par, com a coluna `image_par_id` no candidato.
