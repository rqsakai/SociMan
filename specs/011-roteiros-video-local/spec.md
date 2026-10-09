# Feature Specification: Roteiros com vídeo local (011-roteiros-video-local)

**Feature Branch**: `011-roteiros-video-local`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "Roteiro com cenas reaproveitáveis, keyframes, narração e vídeo local
(insumo `docs/insumos/011-roteiros-video-local.md`, handoff do pipeline que gerou o primeiro vídeo aprovado
pelo dono, `../comfyui-docker/output/candidatos/candidato_01_bia_vestido_verde.mp4`). O texto de venda vira
uma narração contínua; cada cena tem um keyframe aprovado; cada keyframe vira um clipe; os clipes são
cortados no ritmo da fala e montados com acabamento HD. Cria o roteiro e estende a 010 (cena) e a 021
(geração local). Portões opcionais (texto, narração, keyframes, clipes, final) ou modo automático. Depende
da 010, 021, 012, 025 e 014."

> **Achado de escopo da 029 (2026-10-09):** a 029 (AI Studio) entra antes da 011 e torna avatar, voz, produto, cena e
> keyframes itens **da agência, com perfil base opcional**. Nesta spec, onde estiver "do perfil" para esses itens, leia
> "de qualquer perfil base"; o roteiro continua do perfil do vídeo. A migration da 011 passa a `0027_roteiros_video_local`
> (`down_revision = "0026_uniao_mercado"`). Rodar o `/speckit-analyze` da 011 antes do implement.

## Contexto

Hoje a cena da 010 é uma tomada para gerar **à mão no Flow**: o SociMan monta o prompt, o dono gera fora e
envia o arquivo. O vídeo de produto que funcionou foi feito de outro jeito, **localmente**, por scripts no
`../comfyui-docker/pipeline/` (só leitura): o texto de venda vira uma narração contínua com a voz do
perfil; cada cena ganha um **keyframe** (a imagem de partida) aprovado; cada keyframe vira um **clipe**; os
clipes são cortados no tempo da fala de cada cena e montados; um acabamento leva o vídeo a 1080×1920.

Para fazer isso no SociMan faltam três coisas:
- o **roteiro**: a sequência de cenas com o texto de venda, os produtos, o avatar e a voz;
- o **reuso de cenas** entre roteiros: a mesma cena aprovada serve a vários vídeos, sem gastar GPU de novo;
- **portões opcionais**: o operador pode parar e aprovar ou mudar só pedaços (principalmente os keyframes e
  o texto da narração) antes de o vídeo ser gerado, ou deixar tudo automático.

Esta spec **cria** o roteiro e **estende** a 010 (a cena ganha keyframe, motor e tomada gerada localmente) e
a 021 (a lista fechada de passos cresce, os candidatos ganham vídeo, e o modo automático pode escolher a
opção 1 **só dentro do roteiro**). O vídeo final vira um **conteúdo** da 014 (origem `video_proprio`) que
ninguém aprovou ainda: publicar e agendar continuam com a aprovação humana da 014 e da 015 (princípio I).

## Clarifications

### Session 2026-10-08

Decisões já tomadas pelo dono (vêm do insumo; não perguntar de novo):

- Q: Quem aprova os portões do roteiro? → A: **Dono ou membro** (como a aprovação do produto na 012). O
  histórico registra quem aprovou cada portão.
- Q: Um roteiro tem um produto ou vários? → A: **Um ou vários** (vídeo "3 achadinhos"), na lista ordenada
  de produtos do roteiro. Cada cena aponta o seu produto pela ponte que a 012 criou em `cenas`.
- Q: O que o modo automático faz nos passos de escolha? → A: **Escolhe a opção 1** e segue. O histórico
  registra o autor **"sistema (automático)"**. Isso vale **só dentro do roteiro** com o modo ligado; fora
  dele, a regra da 021 ("toda escolha é humana") continua igual.
- Q: No automático, o vídeo final vai direto para publicação? → A: **Não.** Vai para a 014 **como
  rascunho** (conteúdo sem destino aprovado). Publicar e agendar seguem a aprovação humana da 014 e da 015.
- Q: Quais formatos de vídeo? → A: **Só voice over** nesta spec. A avatar aparece sorrindo, mostrando o
  produto, sem falar. Fala na câmera e lip-sync ficam fora do escopo.

Perguntas do clarify (respondidas pelo dono):

- Q: Quantas cenas um roteiro pode ter? → A: **Até 8** por padrão, mas o limite é **configurável** pelo
  dono numa variável de ambiente (`ROTEIRO_MAX_CENAS`), sem mudar código.
- Q: Por quanto tempo ficam as tomadas, narrações e prévias que não foram para o vídeo final? → A: São
  **apagadas 90 dias** depois, como os candidatos da 021. Fica guardado só o que foi usado nos **vídeos
  finais entregues** (o conteúdo da 014 e o que ele precisa para ser reaproveitado: as tomadas e os
  keyframes que entraram nele). Isso amplia a exceção (1) do princípio VII e exige **emenda da
  constitution 4.4.0 → 4.5.0**, aplicada em 2026-10-09 (a 4.4.0 foi usada pela 026).
- Q: O que acontece com o que já foi gerado com a voz ou o rosto de uma pessoa real que revogou o
  consentimento? → A: **O que foi criado fica** (keyframes, tomadas, narrações, vídeos finais e
  conteúdos não são apagados pela revogação). A revogação só **proíbe gerar coisa nova** com aquela voz
  ou aquele avatar.


### Session 2026-10-09

- Q: Quais cenas existentes o planejador pode reaproveitar, agora que a biblioteca é da agência (029)? → A: As do perfil do roteiro **e** as sem perfil base, com aquele avatar e aqueles produtos. As cenas sem perfil base são os **modelos públicos da plataforma**, disponíveis para todas as contas; no multi-tenant futuro, viram modelos da plataforma visíveis a todos os clientes (FR-013).
- Q: Onde ficam os roteiros e vídeos no menu, com o grupo AI Studio da 029? → A: Item "Vídeos" no AI Studio (o primeiro do grupo), com filtro de perfil e "Novo vídeo" escolhendo o perfil/conta; portões e pronúncias do perfil na página do perfil, como o guia (FR-051).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Criar o roteiro e planejar com a IA (Priority: P1)

O operador (dono ou membro) cria um roteiro no perfil: dá um nome, escreve o **brief** (o que o vídeo deve
mostrar), escolhe um ou mais **produtos** aprovados, o **avatar** (opcional; sem avatar o vídeo é só de
produto) e a **voz** (já vem a voz padrão do avatar). Ao pedir o plano, a IA escreve as **frases de venda**
em pt-BR e propõe a **lista de cenas**, **reaproveitando cenas do perfil e os modelos públicos (cenas sem perfil base)** sempre que servem
e criando as que faltam. Cada frase fica atribuída a exatamente uma cena. Com o portão TEXTO ligado, o
roteiro para e o operador edita: inclui, remove ou reescreve frases; troca, reordena, reaproveita ou
duplica cenas; muda qual frase vai em qual cena. Depois aprova e o roteiro segue.

**Why this priority**: É a porta de entrada. Sem o roteiro e o plano, nenhum dos passos de vídeo tem o que
gerar.

**Independent Test**: Com o Claude falso, criar um roteiro com 2 produtos, um avatar e uma voz, pedir o
plano e conferir que:
- as frases e as cenas chegaram, com cada frase em exatamente uma cena;
- uma cena da biblioteca foi reaproveitada (a mesma cena, sem cópia) e as outras foram criadas;
- o roteiro está em "aguardando texto";
- uma edição de frase e uma reordenação de cena são salvas com histórico;
- a aprovação do portão registra quem aprovou e leva o roteiro à narração;
- a chamada ao Claude está no registro do assistente de IA, com custo.

**Acceptance Scenarios**:

1. **Given** um perfil com produtos aprovados, um avatar com kit e uma voz aprovada, **When** o operador
   cria um roteiro com nome, brief, produtos e avatar, **Then** o roteiro nasce em `rascunho`, com a voz
   padrão do avatar já escolhida (trocável) e os portões com o padrão do perfil.
2. **Given** um roteiro em `rascunho`, **When** o operador pede o plano, **Then** o roteiro passa a
   `planejando` e, quando a IA responde, ganha as frases de venda e a lista de cenas, preferindo cenas que
   já existem no perfil para aquele avatar e produto.
3. **Given** o portão TEXTO ligado, **When** o plano chega, **Then** o roteiro para em `aguardando_texto`
   e mostra as frases, as cenas (com a marca "reaproveitada" ou "nova") e a atribuição frase → cena.
4. **Given** o roteiro em `aguardando_texto`, **When** o operador edita, inclui ou remove uma frase, troca
   uma cena por outra da biblioteca, duplica uma cena ou muda a ordem, **Then** a mudança é salva com
   histórico e a regra "toda frase em exatamente uma cena" continua valendo (senão o salvar é recusado
   com o motivo).
5. **Given** o roteiro em `aguardando_texto`, **When** o operador aprova o portão, **Then** o histórico
   registra quem aprovou e o roteiro segue para a narração.
6. **Given** o portão TEXTO desligado (ou o modo automático), **When** o plano chega, **Then** o roteiro
   segue direto para a narração, sem parar.
7. **Given** o produto escolhido deixou de estar aprovado ou foi arquivado, **When** o operador pede o
   plano, **Then** é recusado com o nome do produto.

---

### User Story 2 - Narração contínua com a voz do roteiro (Priority: P1)

Depois do texto, o SociMan pede a **narração**: um take **contínuo** de todas as frases, com a voz do
roteiro, na velocidade escolhida (padrão 1,08) e com o **dicionário de pronúncia** do perfil (ex.: "levinho"
é falado "lévinho"; a legenda e o roteiro continuam com a grafia certa). A narração volta com o tempo de
cada frase, e a **duração de cada cena** sai daí: a cena dura o tempo das suas frases. Com o portão
NARRAÇÃO ligado, o operador ouve, edita uma frase (o que refaz a narração inteira, porque ela é contínua),
troca a voz ou a velocidade, e aprova.

**Why this priority**: O ritmo do vídeo vem da fala. Sem a narração, as cenas não têm duração e os clipes
não podem ser gerados no tamanho certo.

**Independent Test**: Com o serviço de voz falso, levar um roteiro de 3 cenas até a narração e conferir
que:
- a narração é um áudio só, com o tempo de cada frase;
- o pedido levou as pronúncias do perfil e a velocidade;
- a duração de cada cena bate com o tempo das suas frases (com as margens de corte);
- editar uma frase marca a narração como desatualizada e pede outra;
- trocar a voz ou a velocidade também marca desatualizada.

**Acceptance Scenarios**:

1. **Given** o texto aprovado e uma voz aprovada com consentimento (ou sintética), **When** a narração é
   pedida, **Then** o serviço de voz recebe as frases na ordem, a voz, a velocidade e as pronúncias do
   perfil, e devolve um áudio contínuo com o início e o fim de cada frase.
2. **Given** a narração pronta, **When** o SociMan calcula as cenas, **Then** cada cena começa um pouco
   antes da sua primeira frase (cerca de 0,08 s) e termina onde a cena seguinte começa; a última termina
   cerca de 0,45 s depois do fim da fala. As durações não são editáveis à mão.
3. **Given** a transcrição da narração que não bate com o texto (similaridade abaixo de 0,95), **When** o
   serviço de voz devolve o take, **Then** a narração é refeita com outra seed, até o limite de tentativas
   do motor; se não bater, a etapa falha com a mensagem em pt-BR.
4. **Given** o portão NARRAÇÃO ligado, **When** a narração chega, **Then** o roteiro para em
   `aguardando_narracao`, e o operador ouve o áudio inteiro e cada frase com o seu tempo.
5. **Given** o roteiro em `aguardando_narracao`, **When** o operador edita uma frase, troca a voz ou muda a
   velocidade, **Then** a narração atual fica "desatualizada" e uma nova é pedida; a antiga continua no
   histórico do roteiro.
6. **Given** uma voz de pessoa real sem consentimento, revogada ou arquivada, **When** o operador a
   escolhe no roteiro, **Then** é recusado com o motivo.

---

### User Story 3 - Keyframe aprovado por cena (Priority: P1)

Para cada cena que ainda não tem keyframe atual, o SociMan gera **2 opções** de keyframe (a imagem de
partida do clipe), a partir das referências da cena: o kit do avatar, o look, o recorte ou flat do produto
e o cenário. Com o portão KEYFRAMES ligado, o operador vê as cenas lado a lado e, em cada uma, escolhe uma
opção, **regera só aquela cena**, edita a instrução, troca as referências ou **sobe uma imagem pronta**. A
escolhida vira o keyframe da cena.

**Why this priority**: O keyframe é o maior ponto de erro (rosto que muda, produto recolorido, moldura de
celular). É o portão que o dono mais quer ver antes de gastar minutos de GPU no clipe.

**Independent Test**: Com o ComfyUI falso, levar um roteiro de 3 cenas (uma reaproveitada com keyframe
atual) até os keyframes e conferir que:
- só as 2 cenas sem keyframe ganharam gerações, com 2 opções cada;
- a cena reaproveitada não gerou nada;
- escolher a opção 2 de uma cena a grava como keyframe daquela cena, com a geração de origem;
- regerar uma cena cria só a geração dela, com seeds novas;
- subir uma imagem pronta vira o keyframe sem passar pela GPU.

**Acceptance Scenarios**:

1. **Given** a narração aprovada, **When** o roteiro entra em `gerando_keyframes`, **Then** é criada uma
   geração `cena.keyframe` (2 opções) para cada cena sem keyframe atual, na fila da GPU, e as cenas que já
   têm keyframe atual não geram nada.
2. **Given** o portão KEYFRAMES ligado e todas as gerações em revisão, **When** o operador abre o
   roteiro, **Then** vê, por cena, as opções numeradas e a cena na ordem do roteiro, e o roteiro está em
   `aguardando_keyframes`.
3. **Given** uma cena em revisão, **When** o operador clica em "Usar opção N", **Then** a opção vira o
   keyframe inicial da cena, a cena ganha uma versão com a geração de origem e o autor humano.
4. **Given** uma cena, **When** o operador pede "Regerar esta cena" (com a instrução editada ou outras
   referências, se quiser), **Then** só aquela cena ganha uma geração nova, com seeds novas, e a anterior
   fica descartada.
5. **Given** uma cena, **When** o operador sobe uma imagem pronta, **Then** ela vira o keyframe da cena
   (validada como as outras imagens, na resolução da cena), sem passar pela GPU.
6. **Given** todas as cenas com keyframe atual, **When** o operador aprova o portão, **Then** o histórico
   registra quem aprovou e o roteiro segue para os clipes.
7. **Given** o portão KEYFRAMES desligado ou o modo automático, **When** as opções ficam prontas, **Then**
   a **opção 1** de cada cena é escolhida pelo "sistema (automático)", registrado no histórico, e o
   roteiro segue sem parar.
8. **Given** uma cena `usada` (já ligada a um conteúdo), **When** alguém tenta trocar o keyframe dela,
   **Then** é recusado com "cena usada: duplique para variar", como na 010.

---

### User Story 4 - Clipe por cena, com reuso sem GPU (Priority: P1)

Para cada cena sem tomada útil, o SociMan gera o **clipe** a partir do keyframe, com o **motor** da cena
(padrão MiniMax; Wan para plano de rosto sem fala; Wan qualidade para tecido ou giro quando a física
importa). O clipe vira uma **tomada** da cena (origem "geração local"), guardada como as tomadas da 010. Uma
cena reaproveitada que já tem tomada atual, com duração suficiente, **não gera nada**. Com o portão CLIPES
ligado, o operador assiste a cada tomada e, por cena, **regera só aquela**, troca o motor ou escolhe outra
tomada existente da cena.

**Why this priority**: É o vídeo propriamente dito, e o passo mais caro (3 a 8 minutos por cena; 40
minutos no Wan qualidade). O reuso é o que torna o segundo vídeo muito mais barato que o primeiro.

**Independent Test**: Com o ComfyUI falso, levar um roteiro de 3 cenas até os clipes, sendo uma
reaproveitada com tomada de duração suficiente, e conferir que:
- só 2 clipes foram gerados, cada um com o motor da sua cena;
- cada clipe virou uma tomada da cena com a geração de origem;
- a cena reaproveitada usou a tomada que já tinha, sem job de GPU;
- regerar uma cena com outro motor cria só aquela geração;
- escolher outra tomada existente troca a tomada do roteiro sem gerar nada.

**Acceptance Scenarios**:

1. **Given** os keyframes aprovados, **When** o roteiro entra em `gerando_clipes`, **Then** é criada uma
   geração `cena.clipe` para cada cena sem tomada útil, no motor da cena, na resolução nativa da cena
   (padrão 736×1280) e com duração suficiente para a cena no roteiro.
2. **Given** uma cena com tomada atual (não arquivada, do keyframe atual) de duração maior ou igual à
   necessária, **When** o roteiro chega aos clipes, **Then** ela é usada direto e nenhuma geração é
   criada para aquela cena.
3. **Given** o clipe pronto, **When** a geração termina, **Then** ele vira uma tomada da cena (origem
   `geracao_local`, com a geração de origem e o prompt usado) e passa a ser a tomada daquela cena **neste
   roteiro**.
4. **Given** o portão CLIPES ligado, **When** todas as tomadas estão prontas, **Then** o roteiro para em
   `aguardando_clipes`, e o operador assiste a cada uma.
5. **Given** o roteiro em `aguardando_clipes`, **When** o operador regera uma cena (com outro motor, se
   quiser), **Then** só aquela cena ganha uma geração nova. **When** escolhe outra tomada existente da
   cena, **Then** ela passa a ser a tomada do roteiro, sem gerar nada.
6. **Given** uma cena com rosto, **When** o prompt do clipe é montado, **Then** ele diz que a boca fica
   fechada e a pessoa não fala; e, em toda cena, que o quarto, as paredes e a luz não mudam.
7. **Given** o portão CLIPES desligado ou o modo automático, **When** as tomadas ficam prontas, **Then** o
   roteiro segue para a montagem sem parar.

---

### User Story 5 - Prévia, acabamento HD e conteúdo na 014 (Priority: P2)

Com todas as tomadas prontas, o SociMan **monta a prévia**: corta cada tomada na duração da sua cena,
junta na ordem e mistura a narração. Com o portão FINAL ligado, o operador assiste à prévia e aprova; só
então vem o **acabamento** (ampliação para 1080×1920, 24 quadros por segundo, com o filtro que tira a
cintilação), o passo mais demorado. O vídeo HD vira um **conteúdo** da 014 (origem vídeo próprio), marcado
como **gerado por IA**, sem destino aprovado: dali em diante, aprovar, agendar e publicar são as telas da
014 e da 015.

**Why this priority**: Fecha o ciclo e entrega o vídeo onde ele já é publicado. Depende das histórias
anteriores.

**Independent Test**: Com os serviços falsos, levar um roteiro até a prévia, aprovar o portão final e
conferir que:
- a prévia tem a duração da soma das cenas e o áudio da narração;
- o acabamento rodou na fila da GPU e produziu o vídeo 1080×1920 a 24 quadros por segundo;
- o roteiro ficou `pronto`, ligado a um conteúdo novo da 014 de origem vídeo próprio;
- o conteúdo está marcado como gerado por IA e não tem nenhum destino aprovado nem agendado;
- as cenas do roteiro passaram a `usada`, ligadas a esse conteúdo.

**Acceptance Scenarios**:

1. **Given** todas as cenas com tomada, **When** o roteiro entra em `montando`, **Then** a montagem roda
   **fora** da fila da GPU, corta cada tomada exatamente na duração da sua cena, junta na ordem e mistura
   a narração a −14 LUFS.
2. **Given** uma cena cuja duração passou da duração da tomada, **When** a montagem vai começar, **Then**
   ela não congela quadro nem estica o clipe: a cena fica com o aviso "tomada curta, regerar clipe" e o
   roteiro volta para os clipes daquela cena.
3. **Given** o portão FINAL ligado, **When** a prévia fica pronta, **Then** o roteiro para em
   `aguardando_final`, com a prévia para assistir.
4. **Given** o roteiro em `aguardando_final`, **When** o operador aprova, **Then** o histórico registra
   quem aprovou e o roteiro passa a `finalizando`, com o acabamento na fila da GPU.
5. **Given** o acabamento pronto, **When** o SociMan entrega, **Then** cria um conteúdo de origem vídeo
   próprio com o vídeo HD (1080×1920, 24 quadros por segundo, sem interpolação), marcado como gerado por
   IA, sem destino aprovado; o roteiro fica `pronto` e aponta o conteúdo.
6. **Given** um conteúdo criado por um roteiro, **When** alguém vê o conteúdo, **Then** ele mostra de que
   roteiro veio e, se alguma tomada usada veio do MiniMax, o aviso de atribuição exigido pela licença do
   modelo.
7. **Given** o modo automático, **When** o vídeo fica pronto, **Then** o conteúdo é criado do mesmo jeito,
   sem destino aprovado nem agendamento: nenhuma etapa do roteiro aprova, agenda ou publica.

---

### User Story 6 - Portões configuráveis e modo automático (Priority: P2)

Cada roteiro tem cinco **portões** (TEXTO, NARRAÇÃO, KEYFRAMES, CLIPES, FINAL), cada um ligado ou
desligado, e um **modo** (`revisar` ou `automatico`). Em `revisar`, o roteiro para em cada portão ligado e
passa direto pelos desligados. Em `automatico`, não para em nenhum. Os portões podem ser ligados ou
desligados a qualquer momento. O perfil tem um **padrão de portões**, usado por todo roteiro novo. O
operador vê tudo sempre: com ou sem portão, cada etapa mostra o que foi gerado e escolhido.

**Why this priority**: É o que permite tanto o "quero ver cada keyframe" quanto o "faz tudo e me mostra o
vídeo". Sem isso, todo roteiro para cinco vezes.

**Independent Test**: Com os serviços falsos, rodar três roteiros iguais: um com todos os portões
ligados, um só com KEYFRAMES ligado e um no modo automático, e conferir:
- onde cada um parou;
- que as escolhas automáticas têm o autor "sistema (automático)";
- que ligar um portão no meio faz o roteiro parar nele;
- que um cliente MCP não consegue ligar o modo automático nem aprovar portão.

**Acceptance Scenarios**:

1. **Given** um perfil com padrão de portões definido, **When** um roteiro novo é criado, **Then** ele
   herda esse padrão; sem padrão definido, vale o padrão do código (todos ligados, modo `revisar`).
2. **Given** um roteiro rodando, **When** o operador liga um portão de uma etapa que ainda não começou,
   **Then** o roteiro para nela. **When** desliga o portão da etapa em que está parado, **Then** o roteiro
   segue como se tivesse sido aprovado, com a aprovação registrada no nome de quem desligou.
3. **Given** o modo `automatico`, **When** um passo de escolha (keyframe) termina, **Then** a opção 1 é
   escolhida com o autor "sistema (automático)", e o histórico mostra quem ligou o modo e quando.
4. **Given** qualquer modo, **When** um cliente MCP, agente ou IA tenta ligar o modo automático, mudar
   portões, aprovar um portão ou escolher uma opção, **Then** é recusado com "somente humano", e a
   recusa fica registrada.
5. **Given** o modo automático, **When** o operador abre o roteiro, **Then** vê todas as etapas, as
   opções geradas e qual foi escolhida, e pode voltar a qualquer etapa (US7).

---

### User Story 7 - Voltar uma etapa e invalidações em cascata (Priority: P2)

O operador pode mexer numa etapa anterior a qualquer momento: editar o texto quando o roteiro já está nos
clipes, trocar o keyframe de uma cena depois de ver a prévia. O SociMan **nunca apaga** o que já foi
gerado: ele **marca** o que ficou desatualizado e pede de novo só o necessário.
- texto mudou → narração desatualizada → durações recalculadas → montagem refeita;
- keyframe mudou → tomadas daquela cena desatualizadas ("keyframe antigo") → clipe refeito;
- duração da cena cresceu além da tomada → "tomada curta, regerar clipe".

**Why this priority**: Sem invalidação, um ajuste pequeno obriga a começar do zero ou, pior, monta um vídeo
com áudio e cenas fora de sincronia.

**Independent Test**: Com os serviços falsos, levar um roteiro até `aguardando_final`, editar uma frase e
conferir que:
- a narração ficou desatualizada e foi pedida de novo;
- as durações mudaram;
- só a cena cuja duração cresceu além da tomada pediu clipe novo;
- a montagem foi refeita;
- nada foi apagado (as narrações e prévias antigas continuam no histórico).

Trocar o keyframe de uma cena deve regerar só o clipe dela.

**Acceptance Scenarios**:

1. **Given** um roteiro em qualquer etapa depois do texto, **When** o operador edita uma frase, **Then** o
   status volta para a narração, a narração atual fica desatualizada e as etapas seguintes refazem só o
   que mudou.
2. **Given** um roteiro depois dos keyframes, **When** o keyframe de uma cena muda, **Then** as tomadas
   locais dessa cena ficam marcadas "keyframe antigo" (continuam guardadas), o roteiro volta para os
   clipes e só aquela cena gera clipe novo.
3. **Given** uma mudança de duração, **When** a nova duração de uma cena ainda cabe na tomada, **Then** a
   tomada é reaproveitada e só a montagem é refeita.
4. **Given** gerações abertas de uma etapa que ficou desatualizada, **When** a invalidação acontece,
   **Then** essas gerações são canceladas, e o cancelamento é registrado como ação de quem fez a mudança.
5. **Given** qualquer invalidação, **When** ela acontece, **Then** nenhum arquivo, tomada, narração ou
   prévia é apagado; tudo continua no histórico.

---

### User Story 8 - Dicionário de pronúncia do perfil (Priority: P3)

O perfil tem um **dicionário de pronúncia**: pares "como se escreve → como se fala" (ex.: "levinho →
lévinho", "leve → lévi"; o agudo indica vogal aberta e o circunflexo, fechada). Ele vale só para a voz: o
roteiro, a legenda e o post continuam com a grafia certa. O operador edita o dicionário numa tela do
perfil, e ele vai junto em todo pedido de narração.

**Why this priority**: Corrige pronúncias que o modelo de voz erra, mas o vídeo sai sem isso, só com um
ou outro erro.

**Independent Test**: Cadastrar duas pronúncias, pedir uma narração com o serviço de voz falso e conferir
que o pedido levou as duas; editar uma, conferir o histórico e que a narração que usava aquela palavra
ficou desatualizada.

**Acceptance Scenarios**:

1. **Given** o perfil, **When** o operador cadastra "levinho → lévinho", **Then** o par é salvo com
   histórico, e uma segunda entrada com a mesma grafia escrita (sem diferenciar maiúsculas) é recusada.
2. **Given** pronúncias cadastradas, **When** uma narração é pedida, **Then** o pedido leva o dicionário do
   perfil, e o texto mostrado no roteiro continua com a grafia original.
3. **Given** uma narração feita com uma pronúncia, **When** essa pronúncia muda e a palavra aparece nas
   frases, **Then** a narração do roteiro fica desatualizada.

---

### Edge Cases

- **Cena longa demais para o motor:** cada motor tem uma duração máxima de clipe. Se as frases de uma
  cena passarem dela, a aprovação do TEXTO (e a passagem automática) é recusada, com a cena e a sugestão
  de dividir as frases em duas cenas.
- **Roteiro sem avatar** (vídeo só de produto): as cenas não usam as regras de rosto (boca fechada), e o
  plano não propõe cenas com avatar.
- **Avatar sem kit completo** (025): a criação do roteiro aceita, mas o plano e o keyframe avisam que a
  identidade pode variar; o kit em "atenção" aparece como aviso no roteiro.
- **Cena reaproveitada de outro avatar ou produto:** o plano só reaproveita cena do mesmo avatar e do
  mesmo produto (ou variante); para variar, o caminho é "Duplicar", que pede keyframe novo.
- **Mesma cena duas vezes no mesmo roteiro:** permitido (ex.: abertura e fechamento iguais); cada posição
  tem a sua tomada e a sua duração.
- **Cena arquivada depois de entrar no roteiro:** o roteiro avisa e não segue a partir dos keyframes até a
  cena ser trocada ou restaurada.
- **Dois roteiros usando a mesma cena ao mesmo tempo:** um keyframe novo pedido por um roteiro vale para a
  cena (e, portanto, para o outro: todo roteiro não arquivado com aquela cena é reposicionado na etapa
  de clipes daquela posição), exceto se a cena estiver `usada` e já tiver keyframe, quando a troca é
  recusada (o primeiro keyframe de uma cena usada é aceito, FR-024).
- **Voz ou avatar de pessoa real revogado depois de usado:** o que já foi gerado fica (narrações,
  keyframes, tomadas, prévias, vídeos finais e conteúdos). O roteiro passa a mostrar "consentimento
  revogado" e recusa qualquer geração nova com aquela voz ou aquele avatar (narração, keyframe, clipe);
  montar e finalizar com o que já existe continua permitido. A limpeza de 90 dias continua valendo para o
  que não foi usado.
- **Produto desaprovado depois do plano:** o roteiro avisa e não pede keyframe novo com ele; o que já foi
  gerado continua.
- **GPU ocupada por muito tempo** (OpenShorts, outro roteiro, cadastros): as gerações do roteiro esperam
  na fila da 021 com "Aguardando a GPU ficar livre", sem falhar; o roteiro mostra a etapa e a posição.
- **Falha numa etapa:** o roteiro vai para `falhou` com a etapa e o erro em pt-BR; "Tentar de novo" retoma
  daquela etapa, sem refazer as anteriores.
- **Cancelar um roteiro em andamento:** arquivar o roteiro cancela as gerações abertas dele (com
  registro); o que já foi gerado continua guardado.
- **Upload de keyframe com resolução diferente da cena:** aspecto até ±1% do da cena é aceito e
  normalizado para a resolução da cena; fora disso, recusado com o tamanho esperado.
- **Tomada da 010 enviada à mão (Flow):** pode ser escolhida no portão CLIPES como qualquer tomada da
  cena, se tiver duração suficiente; o reuso automático só usa tomadas locais do keyframe atual.
- **Roteiro `pronto` editado:** editar um roteiro pronto reabre a etapa (US7); o conteúdo já criado não
  muda, e uma nova entrega cria um conteúdo novo (o antigo continua, com os destinos que tiver).
- **HD desmontado:** as etapas que gravam arquivo falham com a mesma mensagem das outras gravações.

## Requirements *(mandatory)*

### Functional Requirements

**Roteiro**

- **FR-001**: O SociMan DEVE ter o **roteiro**, do perfil, com: nome (1..120), brief (texto livre),
  avatar (asset `avatar` de qualquer perfil base, opcional; 029), voz (de qualquer perfil base), formato, frases de venda (lista ordenada
  em pt-BR), velocidade da narração (0,9..1,2, padrão 1,08), modo (`revisar` padrão ou `automatico`),
  portões (`texto`, `narracao`, `keyframes`, `clipes`, `final`, cada um ligado ou desligado), status e o
  conteúdo entregue. O roteiro é versionado, arquivável e nunca muda de perfil. O perfil do roteiro é o
  **perfil base** de todas as gerações dele (guia, proibidas e padrões, `perfis.base.resolver` da 029).
- **FR-002**: O **formato** DEVE ter um único valor nesta spec, `voice_over`. Fala na câmera e lip-sync
  ficam fora.
- **FR-003**: A **voz** do roteiro DEVE vir, por padrão, da voz padrão do avatar (025) e DEVE ser uma voz
  aprovada (de qualquer perfil base, 029), não arquivada e, se for de gravação de pessoa real, com
  consentimento não revogado.
  Sem voz válida, o roteiro não pede narração.
- **FR-004**: O roteiro DEVE ter **um ou mais produtos** (012), numa lista ordenada, cada um aprovado e não
  arquivado ao entrar, opcionalmente com a variante. Cada cena do roteiro aponta o seu produto pela ponte
  que a 012 criou em `cenas`.
- **FR-005**: O roteiro DEVE ter a **lista ordenada de cenas** (posições 0..n-1 sem buracos), cada posição
  com: a cena (010), as frases que ela cobre, o início e a duração (derivados da narração, nunca
  editáveis) e a tomada usada neste roteiro. **Toda frase DEVE estar em exatamente uma cena.** A mesma
  cena PODE estar em vários roteiros e em mais de uma posição do mesmo roteiro.
- **FR-006**: Criar, editar, arquivar e restaurar um roteiro, aprovar portões, mudar portões e modo e
  escolher opções DEVEM ser ações de usuário humano (dono ou membro), com histórico (autor, data, antes e
  depois; princípio VII). Reverter uma versão do roteiro é só do dono.

**Estados e portões**

- **FR-007**: O roteiro DEVE seguir os estados `rascunho` → `planejando` → `aguardando_texto` → `narrando`
  → `aguardando_narracao` → `gerando_keyframes` → `aguardando_keyframes` → `gerando_clipes` →
  `aguardando_clipes` → `montando` → `aguardando_final` → `finalizando` → `pronto`, mais `falhou` (com a
  etapa e o erro) a partir de qualquer etapa de trabalho, e o arquivado como em toda entidade. Os
  `aguardando_*` só acontecem com o portão correspondente ligado (e o modo `revisar`).
- **FR-008**: Em cada portão ligado, o roteiro DEVE parar e esperar a aprovação de um humano (dono ou
  membro). A aprovação DEVE ficar no histórico com quem aprovou. Em portão desligado ou no modo
  `automatico`, o roteiro DEVE seguir sem parar.
- **FR-009**: Os portões e o modo DEVEM poder mudar a qualquer momento. Ligar o portão de uma etapa que
  ainda não começou faz o roteiro parar nela; desligar o portão da etapa em que o roteiro está parado
  equivale a aprovar, no nome de quem desligou.
- **FR-010**: O perfil DEVE ter um **padrão de portões e modo**, usado por todo roteiro novo, editável por
  dono e membro, com histórico. Sem padrão gravado, vale o do código: todos os portões ligados, modo
  `revisar`.
- **FR-011**: **"Tentar de novo"** num roteiro `falhou` DEVE retomar da etapa que falhou, sem refazer as
  etapas anteriores que continuam atuais.
- **FR-012**: O operador DEVE poder ver tudo em qualquer etapa e modo: as frases, a narração com os
  tempos, as opções de keyframe e qual foi escolhida (e por quem: humano ou "sistema (automático)"), as
  tomadas, a prévia e o vídeo final.

**Plano (texto)**

- **FR-013**: O passo **`roteiro.plano`** (Claude, só texto) DEVE receber o brief, os produtos (com a ficha
  da 012), o avatar (com a descrição fixa do kit da 025) e a lista de cenas com aquele avatar e aqueles
  produtos cujo perfil base é o perfil do roteiro **ou** que não têm perfil base (os modelos públicos da
  plataforma, para todas as contas), e devolver as frases de venda em pt-BR, a lista de cenas (reaproveitadas ou novas) e
  a atribuição frase → cena. Ele DEVE **preferir reaproveitar** cenas existentes. Como passo só de texto
  (021, FR-010), o resultado vai direto para o roteiro e continua editável.
- **FR-014**: As cenas **novas** do plano DEVEM ser criadas como cenas normais da 010 (em `rascunho`), com
  os campos em inglês que vão ao prompt (ação, câmera, plano, movimento), o avatar, o cenário, o produto,
  o motor e a instrução do keyframe. O autor é o humano que pediu o plano, marcado como feito pela IA.
- **FR-015**: A chamada do plano DEVE entrar no registro do assistente de IA (008), com custo e desfecho,
  inclusive com erro, ligada à geração.
- **FR-016**: No portão TEXTO, o operador DEVE poder: editar, incluir e remover frases; trocar uma cena
  por outra da biblioteca; reordenar; reaproveitar ou duplicar cenas; e mudar a atribuição frase → cena.

**Narração**

- **FR-017**: O passo **`roteiro.narracao`** (motor de voz, 1 opção, resultado áudio e tempos) DEVE pedir
  um take **contínuo** de todas as frases na ordem, com a voz, a velocidade e o dicionário de pronúncia do
  perfil, e receber o áudio e o início e o fim de cada frase. A velocidade DEVE ser aplicada **antes** de
  calcular as durações.
- **FR-018**: A narração DEVE guardar: o áudio (da 021), a voz, a velocidade, os tempos por frase, a
  similaridade da transcrição, a seed e a impressão do que foi narrado (frases, pronúncias, voz e
  velocidade). Só uma narração DEVE estar **ativa** por roteiro; as anteriores continuam guardadas.
- **FR-019**: Uma narração DEVE ficar **desatualizada** quando o texto narrado, a voz, a velocidade ou uma
  pronúncia de palavra presente nas frases mudar.
- **FR-020**: Se a transcrição da narração não bater com o texto (similaridade abaixo de **0,95**), o
  motor DEVE refazer com outra seed, até o seu limite de tentativas; se não bater, a etapa falha com
  mensagem em pt-BR.
- **FR-021**: As **durações das cenas** DEVEM sair da narração: cada cena começa cerca de **0,08 s** antes
  da sua primeira frase e vai até o início da cena seguinte; a última termina cerca de **0,45 s** depois do
  fim da fala. Não há duração editável à mão.

**Cena (extensões da 010)**

- **FR-022**: A cena da 010 DEVE ganhar:
  - o **motor** do clipe: `minimax` (padrão), `wan` (plano de rosto sem fala), `wan_qualidade` (tecido ou
    giro em que a física importa) e `ltx`;
  - a **resolução** do clipe (largura e altura, padrão **736×1280**, a nativa dos modelos);
  - o **keyframe inicial** (obrigatório para gerar clipe) e o **keyframe final** (opcional), como imagens
    da biblioteca (qualquer perfil base) do tipo novo `keyframe`;
  - a **instrução do keyframe** (inglês, o que gerou o inicial) e as **referências do keyframe** (imagens
    do kit do avatar, do look, do recorte ou flat do produto e do cenário);
  - a **duração máxima** que a tomada local pode ter (o clipe é cortado na duração da cena no roteiro).
- **FR-023**: A tomada da 010 DEVE ganhar a origem **`geracao_local`** e a geração de origem. A tomada
  local guarda o prompt usado no clipe, como as tomadas do Flow guardam o prompt congelado.
- **FR-024**: Trocar o keyframe de uma cena DEVE marcar as tomadas locais dela como **"keyframe antigo"**
  (elas continuam guardadas e visíveis). A cena `usada` pode ser reaproveitada em qualquer roteiro e, se
  ainda não tiver keyframe (por exemplo, uma cena do Flow), DEVE poder ganhar o **primeiro** keyframe, a
  resolução e o motor (campos vazios, não há tomada local a invalidar). **Trocar** um keyframe, uma
  resolução ou um motor já definidos numa cena usada DEVE ser recusado com "cena usada: duplique para
  variar" (regra da 010).
- **FR-025**: **"Duplicar"** (010) DEVE copiar os campos novos, exceto o keyframe e as tomadas: a cena
  duplicada pede **keyframe novo**. As referências e a instrução do keyframe são copiadas para servirem de
  ponto de partida.

**Keyframes**

- **FR-026**: O passo **`cena.keyframe`** (ComfyUI, **2 opções**, resultado imagem) DEVE gerar o keyframe
  com o bloco de edição de imagem, a instrução e as referências da cena. A opção escolhida vira o keyframe
  inicial da cena, numa versão da cena com a geração de origem.
- **FR-027**: O roteiro DEVE pedir `cena.keyframe` só para as cenas **sem keyframe atual**. No portão
  KEYFRAMES, o operador DEVE poder, por cena: escolher entre as opções, regerar só aquela cena (seeds
  novas), editar a instrução, trocar as referências ou subir uma imagem pronta (que vira o keyframe sem
  geração).
- **FR-028**: A instrução do keyframe DEVE descrever o **estado final** da cena. Para evitar erros já
  vistos, o SociMan DEVE avisar (sem bloquear) quando a instrução pede mudança de luz (recolore o
  produto) ou cita "phone video" (desenha moldura de celular).

**Clipes**

- **FR-029**: O passo **`cena.clipe`** (ComfyUI, 1 opção, resultado **vídeo**) DEVE gerar o clipe a partir
  do keyframe inicial (e do final, se houver), com o bloco do motor da cena, na resolução da cena e com
  duração suficiente para a cena no roteiro. O resultado vira uma tomada da cena (FR-023) e a tomada
  daquela posição no roteiro.
- **FR-030**: O prompt do clipe DEVE: dizer que a boca fica fechada e a pessoa não fala quando há rosto; e
  dizer, em toda cena, que o quarto, as paredes e a luz não mudam. A fala da cena da 010 **não** entra no
  prompt do clipe (formato voice over).
- **FR-031**: **Reuso sem GPU:** uma posição cuja cena tem tomada **útil** (não arquivada, do keyframe
  atual, com duração maior ou igual à necessária) NÃO DEVE gerar clipe. No portão CLIPES, o operador DEVE
  poder regerar só uma cena (inclusive com outro motor) ou escolher outra tomada existente da cena.

**Montagem e acabamento**

- **FR-032**: O passo **`roteiro.montagem`** (sem GPU, fora da fila da GPU, 1 resultado vídeo) DEVE cortar
  cada tomada na duração da sua posição, juntar na ordem e misturar a narração a **−14 LUFS**. Se uma
  tomada for mais curta que a sua posição, a montagem NÃO DEVE congelar quadro nem esticar o clipe: a
  posição fica com o aviso "tomada curta, regerar clipe" e o roteiro volta para os clipes daquela cena.
- **FR-033**: O passo **`roteiro.acabamento`** (ComfyUI, na fila da GPU, 1 resultado vídeo) DEVE: ampliar
  cada cena com o modelo de super-resolução em blocos de **41 quadros** (blocos menores dão tranco); aplicar
  o filtro temporal leve que tira a cintilação a cada 4 quadros; levar a **1080×1920, 24 quadros por
  segundo, sem interpolação de quadros**; e misturar a narração a −14 LUFS.
- **FR-034**: Ao terminar o acabamento, o SociMan DEVE criar um **conteúdo** da 014 de origem vídeo
  próprio com o vídeo HD e:
  - marcá-lo como **gerado por IA** (o "conteúdo gerado por IA" que a 015 envia à rede deve vir ligado por
    padrão);
  - guardar de que roteiro veio e quais motores geraram as tomadas, mostrando o aviso de **atribuição do
    MiniMax** quando ele foi usado;
  - ligar as cenas do roteiro ao conteúdo (o vínculo da 010), o que as deixa `usada`;
  - **não** criar destino aprovado nem agendamento: o conteúdo nasce como rascunho da 014.

  O roteiro fica `pronto` e aponta o conteúdo.

**Invalidações**

- **FR-035**: Mudanças em etapas anteriores DEVEM invalidar em cascata, **sem apagar nada**:
  - texto, voz, velocidade ou pronúncia → narração desatualizada → durações recalculadas → montagem
    refeita;
  - keyframe → tomadas locais daquela cena "keyframe antigo" → clipe refeito;
  - duração da cena maior que a tomada → "tomada curta, regerar clipe".
- **FR-036**: Voltar a uma etapa anterior DEVE reposicionar o status do roteiro naquela etapa, cancelar as
  gerações abertas das etapas que ficaram desatualizadas (registrado como ação de quem fez a mudança) e
  refazer só o que mudou.

**Modo automático (extensão da 021)**

- **FR-037**: Num roteiro em modo `automatico`, ou com o portão KEYFRAMES desligado, o SociMan DEVE escolher
  a **opção 1** das gerações `cena.keyframe` daquele roteiro, com o autor **"sistema (automático)"** no
  histórico da cena e da geração. Essa é a **única** escolha automática: ela altera a regra da 021 ("toda
  escolha de opção é humana", FR-008 da 021) **só dentro do roteiro**. Fora de um roteiro, nada muda.
- **FR-038**: Só um usuário humano (dono ou membro) DEVE poder criar roteiro, pedir o plano, ligar o modo
  automático, mudar portões, aprovar portão e escolher opção. IA, agente ou cliente MCP DEVE ser recusado
  com "somente humano", e a recusa DEVE ficar registrada (como na 015).
- **FR-039**: Nenhuma etapa do roteiro DEVE aprovar, agendar ou publicar conteúdo, nem falar com rede
  social (princípio I).

**Geração local (extensões da 021)**

- **FR-040**: A lista fechada de passos da 021 (FR-002 de lá) DEVE ganhar os 6 passos desta spec:
  `roteiro.plano` (Claude, texto, sem escolha), `roteiro.narracao` (voz, áudio e tempos, 1 resultado),
  `cena.keyframe` (ComfyUI, imagem, 2 opções), `cena.clipe` (ComfyUI, vídeo, 1 resultado),
  `roteiro.montagem` (sem GPU, vídeo, 1 resultado) e `roteiro.acabamento` (ComfyUI, vídeo, 1 resultado).
- **FR-041**: Os passos de resultado único do roteiro (`roteiro.narracao`, `cena.clipe`,
  `roteiro.montagem`, `roteiro.acabamento`) DEVEM ir direto para o roteiro ou para a cena (como o
  `produto.recorte` da 021), porque a conferência humana deles é o **portão** do roteiro. O único passo
  do roteiro com escolha de opção é o `cena.keyframe`.
- **FR-042**: Os candidatos da 021 DEVEM ganhar mídia de **vídeo** (o vídeo no armazenamento de vídeos do
  HD e uma miniatura), além de imagem e áudio.
- **FR-043**: A trava de GPU da 021 (um job de GPU por vez, GPU livre antes de começar) e a RAM de 28 GB
  do ComfyUI DEVEM valer para `cena.keyframe`, `cena.clipe` e `roteiro.acabamento`. A narração segue a
  regra do motor de voz da 021. A **montagem** NÃO DEVE esperar a GPU.
- **FR-044**: Os alvos da 021 DEVEM ganhar a **cena** (`cena.keyframe`, `cena.clipe`) e o **roteiro**
  (`roteiro.plano`, `roteiro.narracao`, `roteiro.montagem`, `roteiro.acabamento`), com as mesmas regras
  de perfil, arquivamento e histórico dos outros alvos.

**Pronúncia**

- **FR-045**: O perfil DEVE ter um **dicionário de pronúncia** (grafia escrita → grafia falada), editável
  por dono e membro, com histórico, sem duas entradas com a mesma grafia escrita (sem diferenciar
  maiúsculas). Ele DEVE ir em todo pedido de narração e **nunca** muda o texto mostrado, a legenda ou o
  post.

**MCP e limites**

- **FR-046**: Nenhum cliente MCP DEVE criar ou editar roteiro, pedir etapa, aprovar portão, ligar o modo
  automático ou editar pronúncias. As leituras de roteiro seguem a decisão do plano (padrão da 021: fora
  do MCP).
- **FR-047**: Um roteiro DEVE ter no mínimo 1 e no máximo **8** cenas por padrão. O máximo DEVE ser
  configurável pelo dono por variável de ambiente (`ROTEIRO_MAX_CENAS`), sem mudar código. Mudar o limite
  não afeta roteiros que já passam dele: eles continuam válidos, mas não aceitam cena nova.

**Revogação de pessoa real (025)**

- **FR-048**: A revogação do consentimento de uma voz ou de um avatar (025) NÃO DEVE apagar o que já foi
  gerado com eles nos roteiros (narrações, keyframes, tomadas, prévias, vídeos finais, conteúdos). Depois
  da revogação, o SociMan DEVE recusar toda geração nova que use aquela voz ou aquele avatar (narração,
  keyframe, clipe), com a mensagem "consentimento revogado", e o roteiro DEVE mostrar o aviso.

**Limpeza de 90 dias (pré-requisito: emenda 4.5.0 da constitution)**

- **FR-049**: Noventa dias depois de ficar sem uso, os artefatos intermediários dos roteiros DEVEM ser
  apagados (as linhas e os arquivos): as tomadas locais, as narrações, as prévias de montagem e os
  acabamentos que **não** estão num vídeo final entregue. O prazo conta da última vez que o artefato deixou
  de ser atual (substituído, desatualizado ou com o roteiro arquivado).
- **FR-050**: NUNCA DEVEM ser apagados: o vídeo final entregue (o conteúdo da 014); as tomadas, os
  keyframes e a narração que entraram num vídeo final entregue; o keyframe atual de cada cena; a tomada
  escolhida de cada cena e a tomada atual de cada posição de roteiro não arquivado; as tomadas enviadas à
  mão (Flow, 010). A limpeza DEVE ser idempotente e DEVE registrar cada apagamento num evento (o que, quando,
  contagem e a exceção do princípio VII), como a limpeza da 021.
- **FR-051** (Clarification 2026-10-09): os roteiros ficam no item **"Vídeos"** do grupo **AI Studio** do
  menu (029), o primeiro do grupo: a lista tem o filtro de perfil e o "Novo vídeo" começa pela escolha do
  perfil (e da conta) do vídeo. O padrão de portões e o dicionário de pronúncia do perfil ficam na página do
  perfil, como o guia (são configuração, não criação). Nada de item "Roteiros" solto no menu.

### Key Entities

- **Roteiro:** o pedido de um vídeo do perfil: nome, brief, avatar, voz, formato, frases de venda,
  velocidade, modo, portões, status (com a etapa e o erro quando falha) e o conteúdo entregue. Versionado.
- **Produto do roteiro:** um produto (e a variante, opcional) da 012 na lista ordenada do roteiro.
- **Cena do roteiro:** uma posição do roteiro: a cena (010), as frases que cobre, o início e a duração
  derivados da narração e a tomada usada neste roteiro.
- **Narração do roteiro:** um take contínuo (áudio da 021) com a voz, a velocidade, os tempos por frase,
  a similaridade, a seed e a impressão do que foi narrado; uma ativa por roteiro, as outras guardadas e
  marcadas desatualizadas.
- **Pronúncia:** um par "grafia escrita → grafia falada" do perfil, só para a voz.
- **Padrão de portões do perfil:** os portões e o modo que todo roteiro novo do perfil herda.
- **Cena (010, estendida):** ganha motor, resolução, keyframe inicial e final, instrução e referências do
  keyframe e duração máxima da tomada local.
- **Tomada (010, estendida):** ganha a origem "geração local", a geração de origem e a marca "keyframe
  antigo".
- **Geração e candidato (021, estendidos):** 6 passos novos, os alvos cena e roteiro, o resultado em vídeo
  e a escolha automática só dentro do roteiro.
- **Conteúdo (014):** o vídeo final, de origem vídeo próprio, marcado como gerado por IA e ligado ao
  roteiro, sem destino aprovado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um roteiro de 4 cenas, do zero, no modo automático, chega ao conteúdo na 014 com **no máximo
  3 ações humanas** (criar, pedir o plano, ligar o automático), sem contar o tempo da GPU.
- **SC-002**: Na GPU real, um vídeo de 4 cenas feito do zero fica pronto em **até 75 minutos** (referência
  do pipeline: 45 a 60 minutos), e um roteiro que reaproveita todas as cenas com tomada útil fica pronto
  sem nenhum job de keyframe ou clipe.
- **SC-003**: Em 100% dos testes, uma cena com tomada útil não gera job de GPU de keyframe nem de clipe.
- **SC-004**: Em 100% dos testes, toda escolha automática tem o autor "sistema (automático)" e acontece só
  dentro de um roteiro em modo automático ou com o portão KEYFRAMES desligado; fora disso, **0** escolhas
  automáticas (o SC-004 da 021 continua valendo fora do roteiro).
- **SC-005**: **0** conteúdos criados por roteiro com destino aprovado, agendado ou publicado sem uma ação
  humana na 014 ou na 015 (verificado por teste).
- **SC-006**: Em 100% dos testes de invalidação, nenhuma narração, tomada, prévia ou arquivo é apagado, e
  a prévia montada depois de uma edição tem o áudio e as cenas na duração nova (diferença de no máximo 1
  quadro por cena).
- **SC-007**: O vídeo final sai em 1080×1920, 24 quadros por segundo, com a narração a −14 LUFS (±1),
  conferido por medição no teste com o fake.
- **SC-008**: 0 portões aprovados, modos automáticos ligados ou opções escolhidas por cliente MCP, agente ou
  IA (verificado por teste).
- **SC-009**: Depois da limpeza, 0 artefatos intermediários sem uso há mais de 90 dias continuam
  guardados, e 100% dos vídeos finais entregues e do que eles usaram continuam intactos (verificado por
  teste).

## Assumptions

- **Emenda da constitution 4.5.0:** a exceção (1) do princípio VII ("candidatos de geração não
  escolhidos, 90 dias depois") passa a cobrir também os artefatos intermediários de roteiro sem uso num
  vídeo final entregue (FR-049, FR-050). O texto final é aprovado pelo dono na 1ª tarefa da
  implementação, como a 4.3.0 na 021.
- **Limite de cenas pela variável de ambiente:** o dono pediu "admin ou variável de ambiente"; a spec
  usa só a variável (princípio VIII: sem tela nova). Uma tela de configuração pode vir depois.
- **Ordem de implementação:** esta spec depende de tabelas que ainda não existem no banco: produtos e
  variantes (012) e o kit do avatar, as vozes e a voz padrão do avatar (025). Ela só é implementada
  depois das duas. A 025 depende do contrato v2 do shop-tts (X2 do dono).
- **"Rascunho" na 014:** a 014 não tem estado de conteúdo; "como rascunho" quer dizer conteúdo de origem
  vídeo próprio **sem destino aprovado nem agendado** (os destinos são criados e aprovados pelas telas da
  014). O roteiro não cria destinos.
- **Padrão dos portões:** sem padrão gravado no perfil, todos os portões ligados e modo `revisar` (é o
  comportamento mais conservador; o dono desliga o que não quer ver).
- **Quem faz o quê:** dono e membro humanos criam roteiros, aprovam portões e escolhem opções (decisão
  1); reverter é só do dono (princípio VII).
- **Motores e tempos** de referência na RTX 5060 Ti: keyframe ~1 min; clipe MiniMax 3 a 8 min; Wan ~3 min;
  Wan qualidade ~40 min por 6,7 s; acabamento ~16 a 20 min para 17 s; 4 cenas do zero ~45 a 60 min.
- **Licenças:** o MiniMax-H3 tem licença comunitária (Brasil ok) que exige exibir "MiniMax H3" em produto
  comercial; o Seed-VC e o restante do serviço de voz são dependências externas do dono.
- **Avatar:** a identidade vem do kit da 025. Para corpo fora do padrão (plus size), o kit nasce do corpo
  inteiro (regra da 025), e esta spec só usa o kit.
- **Fora do escopo:** fala na câmera e lip-sync; música de fundo; legendas queimadas no vídeo (a legenda
  do post é da 014); LoRA por avatar; molde de movimento a partir de gravação; vídeo horizontal; edição
  manual de áudio ou de vídeo quadro a quadro.
- **Dependências:** 010 (cenas, tomadas, vínculo com conteúdo, Duplicar), 021 (gerações, candidatos,
  áudios, fila da GPU, `dockerctl`, limpeza), 012 (produtos, variantes, ponte nas cenas), 025 (kit do
  avatar, vozes, `assets.voz_id`, consentimento), 014 (conteúdo vídeo próprio), 015 (marca de conteúdo
  gerado por IA no envio), 008 (registro de chamadas), 009 (classificação das rotas no MCP).

## Notas para o plano

Detalhes técnicos do insumo que a spec não fixa como requisito de negócio, mas que o plano deve seguir.

**`roteiros`** (nova, versionada, `entity_type = roteiro`):
- `perfil_id` (imutável); `nome` 1..120; `brief` texto livre;
- `avatar_id` asset `avatar` de qualquer perfil base (029), null; `voz_id` → `vozes` (025), padrão `assets.voz_id` do avatar;
- `formato` enum `roteiro_formato` (`voice_over`, único); `frases` lista ordenada (pt-BR); `velocidade`
  0,9..1,2 padrão 1,08;
- `modo` enum `roteiro_modo` (`revisar` padrão, `automatico`); `portoes` jsonb
  `{texto, narracao, keyframes, clipes, final}` (`true` = para e espera);
- `status` enum `roteiro_status` (a máquina do FR-007), com a etapa e o erro do `falhou`;
- `conteudo_id` FK → `conteudos` (014), preenchido na entrega;
- `version`, `archived_*`, AuditMixin.

**`roteiro_produtos`**: `roteiro_id`, `produto_id` (012), `produto_variante_id` null, `ordem`.

**`roteiro_cenas`**: `roteiro_id`, `ordem` (0..n-1 sem buracos), `cena_id` FK → `cenas` (reuso), `frases`
(índices de `roteiros.frases`; toda frase em exatamente uma cena), `inicio_s` e `duracao_s` (derivados),
`tomada_id` → `cena_tomadas`.

**`cenas`** (010), só acréscimos: `motor` enum `cena_motor` (`minimax` padrão, `wan`, `wan_qualidade`,
`ltx`); `largura`, `altura` (padrão 736×1280); `keyframe_inicial_id`, `keyframe_final_id` → `images`
(`kind` novo `keyframe`); `keyframe_instrucao` (en); `keyframe_refs` (image ids); `duracao_max_s`.
`tomada_origem` ganha `geracao_local` (`ALTER TYPE … ADD VALUE`, ponto de extensão previsto no data-model
da 010) e `cena_tomadas` ganha `geracao_id` FK → `geracoes`, mais a marca "keyframe antigo".

**`roteiro_narracoes`** (uma ativa por roteiro): `roteiro_id`, `audio_id` → `audios` (021, take contínuo),
`voz_id`, `texto_hash` (das frases narradas), `tempos` jsonb `[{frase, inicio_s, fim_s}]` (alinhamento do
Whisper), `similaridade`, `seed`, `velocidade`. Sugestão: o `texto_hash` cobre as frases já com as
pronúncias aplicadas, a voz e a velocidade, para o FR-019 sair da comparação do hash.

**`pronuncias`** (nova, por perfil): grafia escrita → grafia falada; hoje é
`../comfyui-docker/input/vozes/pronuncia.json` no shop-tts; passa a vir do SociMan em cada pedido de
narração (mudança de contrato, dependência externa, documentar em `contracts/`).

**Passos novos da 021** (a lista fechada cresce de 15 para 21):

| Passo | Motor | Resultado | Opções | Observação |
|---|---|---|---|---|
| `roteiro.plano` | claude | texto | — | brief + produtos + avatar → frases + cenas, preferindo reusar; direto e editável |
| `roteiro.narracao` | tts | áudio + tempos | 1 | `/tts_paragraph` contínuo, com `pronuncias`; refaz com outra seed se a transcrição não bater (≥ 0,95) |
| `cena.keyframe` | comfyui | imagem | 2 | Qwen Image Edit com as refs da cena; o escolhido vira `keyframe_inicial_id` |
| `cena.clipe` | comfyui | vídeo | 1 | bloco do `motor` da cena; vira `cena_tomadas` (origem `geracao_local`) |
| `roteiro.montagem` | ffmpeg (worker) | vídeo | 1 | corta cada tomada na `duracao_s`, junta, mistura a narração a −14 LUFS |
| `roteiro.acabamento` | comfyui | vídeo | 1 | SeedVR2 + filtro + 1080×1920 24 fps |

- `geracao_motor` ganha um valor para a montagem (sem GPU) e `geracao_alvo` ganha `cena` e `roteiro`;
- os candidatos ganham `video_key` (bucket de vídeos) e miniatura; o `ck_candidatos_midia` e o trigger
  `geracao_candidatos_midia` passam a aceitar vídeo;
- a escolha automática (FR-037) é a exceção nova à guarda AST da 021 ("o gerador só aplica passos
  `sem_escolha`"): precisa de uma guarda equivalente que só a permita para `cena.keyframe` de cena ligada
  a um roteiro em modo automático ou com o portão desligado, com o autor `system:roteiro` (exibido
  "sistema (automático)").

**Dependências externas (`../comfyui-docker`), documentar em `contracts/`**:
- blocos por contrato (`workflows/api/*.params.json`): `V2 - Keyframe (Qwen Edit)`, `V2 - Clip MiniMax-H3 …`,
  `V2 - Clip Wan 2.2 14B …` (rápido e `qualidade`), `V3 - Upscale vídeo SeedVR2 3B`;
- lógica de referência: `pipeline/run_storyboard.py` (`run_block`, `concat` com `durations`, `comfy_free`),
  `pipeline/finalizar_hd.py`, `runs/bia_vo/gerar.py` e `refazer.py`;
- shop-tts: `POST /tts_paragraph` (frases, voz, seed → `narracao.wav` + tempos) e o `pronuncia.json`
  passando a vir do SociMan no pedido.

**Regras aprendidas que o plano deve levar ao código** (fonte: `../CLAUDE.md`, `PADROES.md`, candidato 1):
- resolução nativa 736×1280 (480p ampliado ficou borrado; o MiniMax turbo é treinado em 768p);
- motor por cena: MiniMax gera vídeo e áudio juntos e mexe a boca em plano de rosto ("boca de fantoche"),
  por isso o plano de rosto sem fala vai no Wan;
- keyframe descreve o estado final; nunca pedir mudança de luz; sem "phone video"; close de produto de
  lado (manga, laço), nunca centrado no decote;
- acabamento: SeedVR2 3B em blocos de 41 quadros, `hqdn3d=0:0:3:3`, lanczos para 1080×1920, 24 fps, sem
  FILM.

## Divergências entre o insumo e a referência (para o plano decidir)

1. **Duração da cena da 010:** a 010 tem `cenas.duracao_s` com CHECK `IN (4, 6, 8)` (duração do Flow). No
   roteiro, a duração é derivada da narração (3,3 s, 6,7 s…) e fica em `roteiro_cenas.duracao_s`. O plano
   confirma que o CHECK da 010 continua só para o Flow e que o `duracao_max_s` novo é o limite da tomada
   local.
2. **Tomada exige cena congelada:** na 010, tomada só entra em cena `pronta`/`usada`, com o prompt
   congelado. O clipe local precisa da cena `pronta`: o plano decide se o roteiro marca a cena `pronta`
   (congela) ao passar do portão KEYFRAMES, com o autor de quem aprovou (ou "sistema (automático)").
3. **Prompt local × prompt do Flow:** o `cenas/prompt.py` da 010 inclui a fala e a descrição do avatar para o
   Flow; o clipe local não leva a fala e soma as regras fixas do FR-030. O plano define a montagem do
   prompt local sem mudar o do Flow.
4. **Resolução do acabamento:** o insumo diz "SeedVR2 na resolução da cena"; o `finalizar_hd.py` aprovado
   amplia para 720×1248 antes do lanczos para 1080×1920. Resolvido no plano (research R11): vale a
   resolução da cena (736×1280), que foi a usada no vídeo aprovado.
5. **Vínculo da 010 no automático:** `cena_usos.criado_por` é um humano. No modo automático, o plano usa o
   humano que pediu o plano do roteiro (ou que ligou o modo).
6. **Retenção (resolvida no clarify):** a limpeza de 90 dias passa a cobrir as tomadas locais, as
   narrações, as prévias e os acabamentos sem uso num vídeo final entregue (FR-049, FR-050), com a emenda
   4.5.0. O plano define:
   - onde fica a data de "deixou de ser atual" (coluna técnica ou cálculo pelas versões);
   - como a limpeza da 021 (`geracao/limpeza.py`, trilha `geracao_limpeza`) passa a apagar
     `cena_tomadas`, `roteiro_narracoes` e os candidatos aplicados direto;
   - a guarda AST: só a limpeza chama `storage.apagar_por_excecao`.
   A linha da tomada fica, sem a mídia e com "arquivo removido em <data>" (research R12).
7. **Revogação × LGPD:** o dono decidiu que o já gerado com pessoa real revogada fica (FR-048). A exceção
   (2) da 4.3.0 continua apagando só a mídia e os textos da própria voz ou avatar (025). Risco: um pedido
   de remoção por parte da pessoa pode exigir apagar também os vídeos derivados; fica para uma decisão
   futura do dono.
