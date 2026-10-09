# Feature Specification: Aprender com o desempenho (023-aprendizado)

**Feature Branch**: `023-aprendizado`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Aprender com os posts que deram certo. Entender por que um vídeo teve resultado
(foi o assunto? o gancho? o horário? a duração? o canal-fonte? as hashtags?), propor melhorias para os
próximos posts e ampliar ou cortar assuntos que não trazem views. Assunto (tema) por vídeo com taxonomia
por perfil editável pelo dono e classificação pela IA corrigível; análise 'por que deu certo' com
estatística robusta e hipóteses da IA sobre os melhores; recomendações que o dono aceita ou rejeita e que
viram preferências do perfil; fechar o ciclo no buscador de vídeos-fonte e no gerador de textos;
diagnóstico de distribuição para posts estagnados; custo de IA visível só para o dono; nada aplicado sem
o dono e nada publicado."

## Contexto

O dono já posta e mede: a 016 coleta as métricas dos vídeos da TikTok e liga cada vídeo ao corte que o
gerou (destino → conteúdo → corte → envio → canal-fonte), e a 019 mostra o analytics de decisão (medida do
post em 1 h / 24 h / 7 d, lift de hashtags, insights determinísticos com amostra mínima). Em 2026-10-06,
o lift de hashtags mostrou algumas hashtags que "bombam" (#multiversomarvel, #vingadoresdoomsday,
#matchcut, #geek, com medianas entre 90 e 217 views), enquanto a **maioria dos posts tem 0 a 2 views**.

O dono quer passar de "ver números" para **aprender**: por que os poucos vencedores venceram, o que repetir,
que assuntos ampliar e quais cortar, e levar isso de volta para a escolha dos vídeos-fonte (Descobrir e
Mercado, 006/019) e para o assistente que escreve títulos, legendas e hashtags (008/017).

**Atenção estatística (motiva várias decisões desta spec):**

1. **O lift explode quando a mediana geral é ~0.** Com mediana geral de 1 view, um grupo com mediana 90 dá
   "90×", número que não significa nada além de "esses posts saíram do zero". A 019 já trata mediana geral
   0 como "sem base"; esta spec troca a razão de medianas por uma medida em escala logarítmica, com
   encolhimento para amostra pequena (FR-020 a FR-023).
2. **Hashtags coocorrem nos mesmos poucos posts.** #multiversomarvel, #vingadoresdoomsday e #geek
   aparecem juntas nos mesmos 3 ou 4 posts de tema Marvel: o tema puxa a hashtag. Contar cada hashtag como
   evidência independente multiplica um único achado. A spec exige mostrar **quantos posts distintos**
   sustentam cada número e a coocorrência hashtag × tema (FR-024, FR-025).
3. **A maioria em 0 view sugere distribuição travada, não efeito de assunto ou hashtag.** Um post que a
   rede não entregou a ninguém não diz nada sobre o assunto dele. A análise separa "a rede entregou?" de
   "quanto rendeu quando entregou" e tem um diagnóstico próprio de distribuição (US5).

## Clarifications

### Session 2026-10-06

- Q: A análise da IA dos melhores olha quadros do vídeo por visão? → A: **Opcional por análise (B).** Até 4
  quadros por vídeo (abertura, 2 s, meio e fim), só dos N melhores e dos piores comparáveis, com o custo
  estimado mostrado antes de o dono confirmar.
- Q: O buscador só ordena ou também esconde temas cortados? → A: **Esconde por padrão (B).** Vídeos-fonte de
  tema "cortar" saem de "Recomendados" e das oportunidades do Mercado, com o contador "N ocultos por tema
  cortado" e o filtro "mostrar temas cortados"; continuam penalizados na pontuação.
- Q: Quando a IA classifica e analisa? → A: **Híbrido (C).** A estatística é calculada na leitura, sem custo;
  o agendador classifica os posts novos assim que chegam ao marco da medida, com limite diário; a análise
  da IA dos melhores é só sob demanda.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assunto (tema) de cada vídeo (Priority: P1)

O dono define, por perfil, a lista de **temas** em que os vídeos se encaixam (ex.: na Taverna Nerd,
"Marvel/MCU", "DC", "Animes", "RPG de mesa", "Games", "Bastidores de cinema"). Cada tema tem nome, uma
descrição curta e palavras-chave. A IA pode **propor a lista inicial** a partir dos posts já publicados; o
dono revisa e salva. Depois, a IA **classifica cada vídeo publicado** num tema principal (e até 2
secundários), lendo o título e a legenda publicada, a transcrição e o gancho do corte e as hashtags, e
marca também o **estilo do gancho** (ex.: pergunta, revelação, número, polêmica, humor, "você sabia").
O dono vê a classificação com uma linha de justificativa e corrige quando discorda. Tudo fica no
histórico.

**Why this priority**: sem saber o assunto de cada post, não dá para dizer que assunto rende; é a base de
todas as outras histórias.

**Independent Test**: no perfil A Taverna Nerd, pedir a lista inicial, ajustar para 5 temas e salvar;
classificar 10 posts semeados; corrigir 2; conferir que a correção prevalece sobre uma nova
classificação da IA e que o histórico mostra a versão da taxonomia, quem classificou e quem corrigiu.

**Acceptance Scenarios**:

1. **Given** um perfil sem temas e com posts publicados, **When** o dono pede a proposta, **Then** a IA
   devolve de 3 a 15 temas com descrição e palavras-chave, que só passam a valer quando o dono salva.
2. **Given** a taxonomia salva, **When** um vídeo do perfil é classificado, **Then** ele recebe um tema
   principal (ou "Sem tema" quando nada se encaixa), até 2 secundários, o estilo do gancho, a
   justificativa em uma linha e a marca "classificado pela IA".
3. **Given** um vídeo classificado pela IA, **When** o dono troca o tema, **Then** a classificação passa a
   ser "corrigida pelo dono", a IA nunca mais a sobrescreve, e a mudança vai para o histórico com o
   estado anterior.
4. **Given** um tema renomeado, juntado a outro ou arquivado, **When** a mudança é salva, **Then** as
   classificações dos vídeos seguem a mudança (juntar move os vídeos para o tema de destino; arquivar os
   manda para "Sem tema" e pede reclassificação), e tudo pode ser revertido pelo dono.
5. **Given** um vídeo publicado fora do SociMan (sem corte), **When** ele é classificado, **Then** a IA usa
   só a legenda e as hashtags publicadas, e a classificação aparece com "evidência parcial".
6. **Given** um membro, **When** abre os temas e as classificações, **Then** vê tudo, sem editar.

---

### User Story 2 - Por que deu certo (Priority: P1)

Numa área **Aprendizado** do perfil (com atalho a partir da aba "O que funciona" do analytics), o dono vê,
para o período de análise, uma comparação **vencedores × resto** por fator: tema, estilo e tamanho do
gancho, duração, faixa de horário e dia da semana, canal-fonte, hashtags e modo de envio. Cada linha diz
quanto aquele fator rende em relação à conta ("posts de Marvel/MCU rendem cerca de 2,4× o típico da
conta"), com **quantos posts distintos** sustentam o número, o grau de confiança em palavras e um aviso
quando o número é puxado por um só post ou quando o efeito não se separa de outro fator (ex.: a hashtag
só aparece junto do tema). Além disso, o dono pode pedir uma **análise da IA dos melhores posts**: a IA lê
transcrição, gancho, legenda e hashtags dos N melhores e dos piores comparáveis e devolve **hipóteses**
legíveis ("os 4 melhores abrem com uma pergunta direta sobre o filme novo nos 2 primeiros segundos"), cada
uma com a evidência (quais posts) e o n.

**Why this priority**: é o pedido central do dono: entender por que um vídeo teve resultado.

**Independent Test**: com 30 posts semeados (views conhecidas, temas, ganchos, horários, hashtags que
coocorrem com um tema), conferir que cada efeito bate com o cálculo de referência, que a hashtag que só
aparece no tema vencedor sai como "não separável do tema", que um grupo puxado por um viral recebe o
aviso, e que a análise da IA traz hipóteses citando posts existentes.

**Acceptance Scenarios**:

1. **Given** posts medidos com tema, **When** o dono abre a análise, **Then** cada tema com amostra mínima
   mostra o efeito em "× o típico da conta", o intervalo plausível, o n de posts distintos e a confiança
   (forte, moderada, fraca, indício); abaixo do mínimo, mostra só os números brutos e "faltam N posts".
2. **Given** um tema com 3 posts, um deles com 2.000 views e os outros com 1, **When** a análise é
   calculada, **Then** o efeito é encolhido em direção ao típico da conta (não aparece como "vencedor
   forte") e o aviso diz "puxado por 1 post".
3. **Given** #vingadoresdoomsday presente só em posts do tema Marvel/MCU, **When** a análise de hashtags
   aparece, **Then** a hashtag mostra "não separável do tema Marvel/MCU (aparece em 4 de 4 posts do
   tema)" em vez de um efeito próprio, e a matriz hashtag × tema mostra a coocorrência.
4. **Given** uma conta com a maioria dos posts estagnados (US5), **When** a análise é aberta, **Then** a
   tela avisa que a distribuição está travada e que conclusões sobre assunto ficam suspensas para aquela
   conta, mostrando a análise só como indício.
5. **Given** o dono pede a análise da IA dos melhores, **When** ela termina, **Then** cada hipótese cita os
   posts (link), o n e o contraste com os piores comparáveis; o dono vê o custo da chamada e ela fica no
   registro do assistente (008).
6. **Given** um membro, **When** abre a análise, **Then** vê os números e as hipóteses já geradas, mas não
   vê custo e não pode pedir análise da IA.

---

### User Story 3 - Recomendações com decisão do dono (Priority: P1)

A partir da análise, o SociMan propõe **recomendações**: temas para **ampliar** ou **cortar**, hashtags a
**fixar** (entram nas hashtags fixas do guia, 017) ou a **evitar**, e **padrões** de gancho, duração e
janela de horário. Cada recomendação mostra o motivo, a evidência (números, n, posts) e o que muda se for
aceita. O dono **aceita** ou **rejeita** (com motivo opcional). Aceita, ela vira **preferência do perfil**
(ou da conta), versionada, com histórico e reversão. Rejeitada, não volta a ser sugerida até a evidência
mudar de forma relevante.

**Why this priority**: o aprendizado só vale se mudar o que se faz; e nada pode mudar sem o dono
(princípio VII).

**Independent Test**: com a análise semeada, aceitar "ampliar Marvel/MCU", "cortar Bastidores de cinema" e
"fixar #multiversomarvel" e rejeitar "evitar #fyp"; conferir as preferências salvas, a hashtag no guia da
conta (com o limite de fixas respeitado), o histórico de cada uma e a reversão de uma delas.

**Acceptance Scenarios**:

1. **Given** uma recomendação "ampliar tema X", **When** o dono aceita, **Then** o tema X fica marcado como
   "ampliar" nas preferências do perfil, com autor, data, evidência no momento e versão nova das
   preferências.
2. **Given** uma recomendação "fixar #h" numa conta que já está no máximo de hashtags fixas, **When** o dono
   tenta aceitar, **Then** a tela pede para escolher qual fixa sai ou recusa com a regra da 017 (perfil +
   conta, sem repetir, até o máximo da conta).
3. **Given** uma recomendação rejeitada, **When** a análise é recalculada com a mesma evidência, **Then**
   ela não reaparece; **When** o número de posts que a sustenta dobra ou o efeito muda de faixa de
   confiança, **Then** ela pode reaparecer, mostrando "já rejeitada em DD/MM".
4. **Given** uma preferência aceita, **When** o dono reverte, **Then** ela volta ao estado anterior e a
   reversão fica no histórico.
5. **Given** um cliente MCP ou um membro, **When** tenta aceitar ou rejeitar, **Then** é recusado (só dono
   humano).
6. **Given** uma recomendação de "janela de horário", **When** aceita, **Then** ela aparece como dica no
   agendamento do destino (014), sem agendar, reagendar nem mudar nada sozinha (princípio I).

---

### User Story 4 - Fechar o ciclo: buscador e gerador (Priority: P2)

As preferências e o que rendeu passam a orientar duas pontas:

- **Buscador:** no Descobrir (006) e nas oportunidades do Mercado (019), a pontuação dos vídeos-fonte
  ganha um componente de **afinidade com o que funciona** (tema do vídeo-fonte casado pelas palavras-chave
  dos temas e desempenho dos posts derivados do mesmo canal-fonte) e o motivo em uma linha passa a citar
  isso quando é o principal ("tema Marvel/MCU: 2,4× o típico da conta"). Vídeos de temas **cortados** são
  penalizados e escondidos por padrão, com contador e filtro "mostrar temas cortados". O aviso de direito da 006
  continua exatamente igual.
- **Gerador:** o assistente (008/017) recebe, ao gerar títulos, legendas e hashtags de uma postagem, um
  bloco **de desempenho** com o que rendeu naquele perfil e conta (preferências aceitas e até 3 exemplos
  de posts vencedores), escolhido por regras fixas e registrado na chamada pela versão, como o guia. As
  hashtags fixas continuam incluídas pelo servidor e as proibidas continuam bloqueando.

**Why this priority**: é o que transforma aprendizado em próximos posts melhores; depende de US1 a US3.

**Independent Test**: com o tema Marvel/MCU "ampliar" e Bastidores "cortar", abrir o Descobrir e conferir a
ordem, o motivo e a penalidade de vídeos semeados; gerar uma legenda e conferir no registro da chamada a
versão do bloco de desempenho, os exemplos usados, as fixas presentes e nenhuma proibida aplicável.

**Acceptance Scenarios**:

1. **Given** dois vídeos-fonte iguais em velocidade, um com palavras-chave de um tema "ampliar" e outro sem
   tema, **When** o Descobrir ordena, **Then** o do tema ampliado vem antes, e o motivo cita o tema.
2. **Given** um vídeo-fonte de tema "cortar", **When** o Descobrir abre, **Then** ele perde pontos e fica escondido
   por padrão, com a contagem "N ocultos por tema cortado"; **When** o dono liga "mostrar temas
   cortados", **Then** ele aparece com o selo "tema cortado" (FR-040).
3. **Given** um vídeo-fonte de canal `sem_acordo` com afinidade alta, **When** o dono o seleciona e envia
   para corte, **Then** o aviso de direito aparece como sempre (princípio II); a afinidade nunca muda o
   status nem pula o aviso.
4. **Given** preferências aceitas e posts vencedores na conta, **When** o assistente gera textos de uma
   postagem dessa conta, **Then** o pedido leva o bloco de desempenho depois dos guias e antes do contexto
   do perfil, e a chamada grava a versão das preferências e os ids dos exemplos.
5. **Given** uma hashtag "evitar" aceita, **When** o assistente propõe hashtags, **Then** o servidor a tira
   da proposta (como inclui as fixas), e a tela informa a remoção.
6. **Given** o dono desliga "usar desempenho no assistente" do perfil, **When** gera textos, **Then** o
   bloco não é enviado e a chamada registra "sem bloco de desempenho".

---

### User Story 5 - Diagnóstico de distribuição (Priority: P2)

Para os posts **estagnados** (0 a 1 view depois do prazo da 019), o SociMan separa "a rede não entregou"
de "o assunto não interessou". Por conta, mostra os sinais que costumam travar a entrega e um checklist do
que conferir no app: conta nova ou com poucos posts, muitos posts no mesmo dia ou em sequência curta,
horário fora da janela em que a audiência assiste (019), possível conteúdo repostado (mesmo vídeo-fonte já
postado em outra conta, marca d'água de terceiros, canal `sem_acordo`), duração muito curta, legenda vazia
ou excesso de hashtags. O checklist lembra de conferir no app: post restrito ou "não elegível para o Para
Você", aviso de conteúdo não original, privacidade, música sem licença, violação de diretrizes.

**Why this priority**: com a maioria dos posts em 0 view, sem esse corte a análise de assunto aprenderia o
errado; é o que torna a US2 honesta.

**Independent Test**: semear uma conta nova com 8 posts em 1 dia, 6 deles estagnados, e um vídeo-fonte
postado em duas contas; conferir os sinais, o checklist, a separação na análise e que nada é gravado como
tarefa automática.

**Acceptance Scenarios**:

1. **Given** uma conta com mais da metade dos posts estagnados no período, **When** o dono abre o
   diagnóstico, **Then** vê "distribuição travada" com os sinais encontrados (cada um com o número que o
   sustenta) e o checklist do app.
2. **Given** um post estagnado, **When** o dono abre o detalhe, **Then** vê os sinais daquele post e pode
   marcar o que conferiu no app ("conferi: não estava restrito"), registrado no histórico.
3. **Given** posts estagnados, **When** a análise da US2 calcula efeitos de tema, **Then** eles entram só
   na parte "a rede entregou?" e não puxam para baixo o "quanto rendeu" do tema.
4. **Given** o diagnóstico, **When** a condição deixa de valer, **Then** o sinal some sozinho (calculado na
   leitura); só as marcações do dono ficam guardadas.

---

### User Story 6 - Custo, cadência e controle (Priority: P3)

O dono vê o custo das chamadas de IA desta spec (proposta de taxonomia, classificação, análise dos
melhores) no registro e no resumo do assistente (008), separado por finalidade; antes de uma análise da
IA, vê o custo estimado. A análise estatística é recalculada sem custo; a classificação dos posts novos é
feita pelo agendador com limite diário, e a análise dos melhores só quando o dono pede (FR-051). O dono
pode pausar a classificação automática e o uso do desempenho no assistente, por perfil.

**Why this priority**: controle e previsibilidade de gasto; o restante funciona com os padrões.

**Independent Test**: classificar 20 posts e pedir uma análise da IA; conferir no resumo do mês o custo por
finalidade, o custo estimado mostrado antes da análise e que um membro não vê nenhum valor.

**Acceptance Scenarios**:

1. **Given** chamadas desta spec, **When** o dono abre o resumo do assistente, **Then** vê o custo por
   finalidade (taxonomia, classificação, análise) junto do custo dos outros campos.
2. **Given** a classificação automática pausada no perfil, **When** um post novo é vinculado, **Then** ele
   fica "aguardando classificação" e entra na análise como "Sem tema" até ser classificado.

---

### Edge Cases

- **Mediana da conta 0:** a medida em escala logarítmica continua definida (log(0+1) = 0); efeitos são
  mostrados como diferença de "chance de sair do zero" e não como razão infinita.
- **Um viral só:** o encolhimento e o aviso "puxado por 1 post" impedem que um único post vire um tema
  vencedor; o efeito sem esse post é mostrado lado a lado ("sem o maior post: 1,1×").
- **Fatores confundidos:** se um tema só foi postado num horário, ou uma hashtag só aparece num tema, a
  tela diz "não separável" e não atribui o efeito a nenhum dos dois.
- **Muitos fatores, poucos posts:** comparar dezenas de hashtags e faixas acha "vencedores" por acaso; os
  achados são rotulados "exploratórios", só os de confiança moderada ou forte viram recomendação.
- **Post em várias contas:** o mesmo conteúdo publicado em duas contas conta como dois posts, cada um
  medido contra a própria conta; a coocorrência entre contas aparece no diagnóstico (repostagem).
- **Conta nova ou poucos dados:** sem a amostra mínima por conta, a análise mostra só os números brutos e
  "faltam N posts"; nenhuma recomendação é gerada.
- **Taxonomia mudou depois da análise:** recomendações abertas citam a versão da taxonomia; ao juntar ou
  arquivar o tema, as recomendações dele são marcadas "superadas".
- **Vídeo-fonte sem palavras-chave de tema:** afinidade neutra (0), sem penalidade.
- **Preferência em conflito com o guia** (ex.: fixar uma hashtag que está nas proibidas): recusado ao
  aceitar, citando a regra.
- **Dados antigos:** pesam menos (esquecimento gradual); um tema forte há 6 meses e fraco agora aparece
  como "em queda".
- **Conta anonimizada (016):** seus posts entram nas estatísticas do perfil como "Conta anônima N", sem
  texto; não são usados como exemplos no gerador nem na análise da IA (só números).
- **IA indisponível:** a classificação fica "aguardando classificação" e é tentada de novo na próxima
  volta; a análise da IA termina em "erro" com o motivo e pode ser pedida de novo; ambas ficam no registro
  (008). A análise estatística continua funcionando.
- **Classificação da IA fora da taxonomia** (tema inventado): recusada pelo servidor e marcada como "Sem
  tema", com o texto da IA guardado como sugestão de tema novo para o dono.

## Requirements *(mandatory)*

### Functional Requirements

**Temas e classificação (US1)**

- **FR-001**: Cada perfil DEVE ter uma taxonomia de temas editável só pelo dono: nome (único no perfil),
  descrição curta, palavras-chave (para casar vídeos-fonte) e estado (ativo ou arquivado), com até 30
  temas ativos e o tema reservado "Sem tema". Criar, renomear, juntar, arquivar e restaurar DEVEM ficar no
  histórico com reversão (princípio VII); não há exclusão.
- **FR-002**: O dono DEVE poder pedir à IA uma proposta de taxonomia a partir dos posts publicados do
  perfil (títulos, legendas, transcrições, hashtags); a proposta só vale quando o dono salva, como no
  "montar guia" da 017.
- **FR-003**: Cada vídeo publicado de uma conta do perfil DEVE poder ter uma classificação: tema principal
  (ou "Sem tema"), até 2 secundários, estilo do gancho (lista fixa em código, com "outro"), justificativa
  em uma linha, origem (`ia` ou `dono`), versão da taxonomia e a chamada do assistente que a gerou.
- **FR-004**: A classificação pela IA DEVE usar título e legenda publicados, hashtags, e, quando o vídeo
  tem corte, a transcrição e o texto do gancho; sem corte, DEVE ser marcada "evidência parcial".
- **FR-005**: O servidor DEVE recusar tema fora da taxonomia vigente (vira "Sem tema" com a sugestão
  guardada) e DEVE nunca sobrescrever uma classificação de origem `dono`.
- **FR-006**: Só o dono DEVE corrigir classificações; toda escrita (da IA ou do dono) DEVE registrar autor,
  data e estado anterior. A IA aparece como autor de sistema identificado, nunca como um humano.
- **FR-007**: Juntar temas DEVE mover as classificações para o tema de destino; arquivar DEVE levá-las a
  "Sem tema" e marcá-las para reclassificação; reverter DEVE restaurar ambos.

**Medida e estatística (US2)**

- **FR-010**: A análise DEVE usar a medida do post da 019 (views no marco escolhido, padrão 24 h, com
  "estimado" quando interpolado), excluindo posts que ainda não chegaram ao marco ("aguardando").
- **FR-011**: Todo efeito DEVE ser calculado **relativo à conta** do post (posts de contas grandes e
  pequenas comparados ao típico da própria conta no período), para que o tamanho da conta não seja
  confundido com o assunto.
- **FR-012**: A análise DEVE ter duas partes, nesta ordem: (a) **entrega**: a proporção de posts que saíram
  da estagnação (critério da 019); (b) **rendimento**: entre os que saíram, a medida em escala
  logarítmica (log(views + 1)). Os efeitos de cada fator DEVEM aparecer nas duas partes, e posts
  estagnados NÃO DEVEM entrar na parte (b).
- **FR-013**: Fatores analisados: tema principal, estilo do gancho, tamanho do gancho (faixas), duração do
  clipe (faixas da 019), faixa de 3 h de publicação, dia da semana, canal-fonte, cada hashtag (normalizada
  sem acento e sem caixa) e modo de envio. Faixas e fatores ficam em constantes no código, visíveis na
  nota de leitura.
- **FR-014**: Esquecimento gradual: cada post DEVE pesar segundo a idade da publicação, com meia-vida
  padrão de 30 dias e janela máxima padrão de 180 dias (constantes, visíveis na tela); a tela DEVE indicar
  efeitos "em alta" ou "em queda" quando o efeito recente (30 dias) e o do resto da janela diferirem de
  faixa.

**Robustez (US2)**

- **FR-020**: Todo efeito de grupo DEVE ser **encolhido** em direção ao típico da conta segundo o tamanho
  da amostra (um grupo pequeno empresta força da média geral; padrão: peso equivalente a 5 posts para a
  média), e DEVE ser mostrado como fator multiplicativo aproximado ("≈ 2,4× o típico") e, na parte de
  entrega, como diferença de pontos percentuais.
- **FR-021**: Todo efeito DEVE mostrar o **n de posts distintos** (e de dias distintos) que o sustentam e
  um intervalo plausível obtido por reamostragem dos posts; a confiança em palavras (forte, moderada,
  fraca, indício) DEVE sair do intervalo e do n, por regra fixa em código.
- **FR-022**: Amostra mínima por grupo: padrão de 5 posts distintos em pelo menos 2 dias distintos, e 15
  posts medidos na conta; abaixo disso, a tela DEVE mostrar só os números brutos e "faltam N posts", sem
  efeito nem recomendação.
- **FR-023**: **Concentração:** quando um só post responde por mais da metade do total do grupo, o efeito
  DEVE trazer o aviso "puxado por 1 post" e o efeito recalculado sem ele.
- **FR-024**: **Coocorrência:** a análise DEVE mostrar a matriz hashtag × tema (quantos posts de cada tema
  usam cada hashtag) e, para cada hashtag, o efeito **dentro do tema** (posts do mesmo tema com e sem a
  hashtag); se não houver posts do tema sem a hashtag (ou com ela) em número mínimo, a hashtag DEVE sair
  "não separável do tema X", sem efeito próprio.
- **FR-025**: Grupos de hashtags que aparecem sempre juntas (nos mesmos posts) DEVEM ser mostrados como um
  bloco único ("#a + #b + #c, sempre juntas em 4 posts"), contados uma vez.
- **FR-026**: O mesmo tratamento de confusão DEVE valer para fatores entre si (tema × horário, tema ×
  canal-fonte): quando um fator só aparece com um valor do outro, a tela DEVE dizer "não separável".
- **FR-027**: **Distribuição travada:** quando mais de 60% dos posts medidos de uma conta no período forem
  estagnados (padrão em constante), a tela DEVE suspender as conclusões de rendimento daquela conta,
  rotular tudo como "indício" e apontar para o diagnóstico (US5).
- **FR-028**: Achados de vários fatores ao mesmo tempo DEVEM ser rotulados "exploratórios"; só achados de
  confiança moderada ou forte, fora de "não separável" e de "distribuição travada", PODEM virar
  recomendação.

**Análise da IA dos melhores (US2)**

- **FR-030**: O dono DEVE poder pedir uma análise da IA dos N melhores posts do perfil ou de uma conta
  (padrão 8, até 15) contra os piores comparáveis (mesmo período e conta, que saíram da estagnação),
  usando transcrição, gancho, legenda, hashtags, tema, duração e horário de cada um, e o resumo da
  estatística (FR-020 a FR-028) como contexto.
- **FR-031**: O dono DEVE poder incluir, por análise, quadros do vídeo por visão: até 4 quadros por vídeo
  (abertura, 2 s, meio e fim), só dos N melhores e dos piores comparáveis que têm o arquivo do corte
  guardado; o custo estimado (com e sem quadros) DEVE aparecer antes de confirmar. Vídeos sem arquivo
  entram só com texto, e a análise diz quantos.
- **FR-032**: Cada hipótese da IA DEVE ter: frase legível, os posts que a sustentam (links), o n, o
  contraste com os piores e o grau ("a conferir", nunca "comprovado"); o servidor DEVE recusar hipótese
  que cite post fora do conjunto enviado.
- **FR-033**: A análise DEVE ficar guardada (versão, data, posts usados, versão da taxonomia, chamada e
  custo) e ser reaberta sem nova chamada; o dono DEVE poder transformar uma hipótese em recomendação de
  "padrão" (FR-034), que segue o fluxo normal de aceite.

**Recomendações e preferências (US3)**

- **FR-034**: Recomendações DEVEM nascer de regras determinísticas sobre a estatística (FR-028) ou de uma
  hipótese da IA escolhida pelo dono, com os tipos: tema `ampliar` / `cortar`; hashtag `fixar` / `evitar`;
  padrão de gancho, de duração e de janela de horário. Cada uma DEVE trazer motivo, evidência no momento
  (efeito, intervalo, n, posts) e o que muda se aceita.
- **FR-035**: Padrões das regras (constantes, visíveis na tela): `ampliar` quando o efeito encolhido é
  ≥ 1,5× com confiança ao menos moderada; `cortar` quando é ≤ 0,5× com confiança ao menos moderada, n
  ≥ 8 e a conta fora de "distribuição travada"; `fixar` só para hashtag separável do tema com efeito
  ≥ 1,3×; `evitar` só para hashtag separável com efeito ≤ 0,7×.
- **FR-036**: Só o dono humano DEVE aceitar, rejeitar ou reverter recomendações e preferências; membro,
  agente ou cliente MCP recebem 403, e a tentativa fica registrada.
- **FR-037**: Aceitar DEVE gravar a preferência do perfil (ou da conta, quando a evidência é de uma conta)
  numa nova versão, com histórico, estado anterior e reversão. "Fixar hashtag" DEVE ser gravado no guia da
  017 (mesmas regras de máximo e de proibidas, histórico do guia com a origem "recomendação 023").
- **FR-038**: Rejeitar DEVE guardar o motivo (opcional) e a evidência; a recomendação só PODE reaparecer
  quando o n que a sustenta dobrar ou a confiança mudar de faixa, mostrando a rejeição anterior.
- **FR-039**: Preferências NÃO DEVEM agendar, reagendar, aprovar, publicar nem mudar nenhum dado de
  conteúdo; a janela de horário aceita aparece só como dica no agendamento (princípio I).

**Buscador (US4)**

- **FR-040**: A pontuação dos vídeos-fonte (006) e as oportunidades do Mercado (019) DEVEM ganhar um
  componente de **afinidade** com peso limitado (padrão: até 20% da pontuação), calculado de forma
  determinística: tema do vídeo-fonte por casamento das palavras-chave dos temas no título e na
  descrição (sem acento e sem caixa), efeito do tema no perfil, preferência (`ampliar` soma; `cortar`
  subtrai) e efeito dos posts derivados do mesmo canal-fonte. Vídeos de tema `cortar` DEVEM ser
  penalizados e, por padrão, escondidos de "Recomendados" e das oportunidades do Mercado, com o contador
  "N ocultos por tema cortado" e o filtro "mostrar temas cortados" (que os mostra com o selo "tema
  cortado", sem mudar a preferência); a busca por texto também respeita o filtro.
- **FR-041**: O motivo em uma linha (006) DEVE citar a afinidade quando ela for o componente principal, e
  o detalhe da pontuação DEVE mostrar a parte da afinidade separada.
- **FR-042**: A afinidade NÃO DEVE alterar o status de direito do canal nem o aviso antes do envio para
  corte (princípio II); vídeos `sem_acordo` continuam com o aviso, com ou sem afinidade.
- **FR-043**: Sem perfil escolhido, sem taxonomia, ou sem preferências e abaixo da amostra mínima, a
  afinidade DEVE ser neutra e a pontuação DEVE ficar igual à da 006. Preferências aceitas pelo dono valem
  mesmo com amostra pequena (são decisão dele); o efeito estatístico só entra acima da amostra mínima.

**Gerador (US4)**

- **FR-044**: Ao gerar textos de postagem (título, legenda, hashtags; tipos `postagem.*` da 008) e no
  `guia.testar` da 017, o pedido DEVE levar um bloco `<desempenho>` depois de `<guia_conta>` e antes de
  `<perfil>`, com: preferências aceitas do perfil e da conta (temas, padrões, hashtags a evitar) e até 3
  exemplos (legenda e gancho) de posts vencedores da mesma conta (ou do perfil, sem posts da conta),
  escolhidos por regra fixa: maior efeito encolhido, fora de "distribuição travada", sem palavra
  proibida, de conta não anonimizada, publicados nos últimos 90 dias. A versão do prompt DEVE subir.
- **FR-045**: A chamada DEVE gravar a versão das preferências e os ids dos exemplos enviados, como grava
  as versões dos guias (017); o registro do assistente DEVE mostrá-los.
- **FR-046**: As hashtags fixas continuam incluídas pelo servidor (017) e as `evitar` aceitas DEVEM ser
  retiradas pelo servidor da proposta, com aviso na tela; as proibidas continuam bloqueando o Aplicar sem
  edição. O bloco de desempenho NÃO DEVE anular as regras fixas, os guias nem as proibidas.
- **FR-047**: O dono DEVE poder desligar o bloco de desempenho por perfil; desligado, a chamada registra
  "sem bloco de desempenho".

**Diagnóstico de distribuição (US5)**

- **FR-048**: Sinais por conta e por post, calculados na leitura (não gravados), cada um com o número que o
  sustenta: conta nova (menos de 30 dias de coleta ou menos de 15 posts), posts no mesmo dia acima de um
  limite (padrão 3) ou com intervalo menor que o mínimo da conta (014), publicação fora das 6 h de maior
  audiência (mapa da 019), possível repostagem (mesmo vídeo-fonte ou mesmo trecho em outra conta, canal
  `sem_acordo`, envio avulso), duração abaixo de 10 s, legenda vazia e mais de 8 hashtags.
- **FR-049**: O diagnóstico DEVE trazer um checklist fixo do que conferir no app da rede (post restrito ou
  não elegível para recomendação, aviso de conteúdo não original, privacidade, música, diretrizes), e o
  dono DEVE poder marcar itens conferidos por post, gravados com histórico.
- **FR-050**: O diagnóstico NÃO DEVE criar tarefas, mudar destinos nem republicar; é só leitura mais as
  marcações do dono.

**Custo, cadência e controle (US6)**

- **FR-051**: Cadência: a estatística (efeitos, recomendações por regra, diagnóstico, afinidade) DEVE ser
  calculada na leitura, sem custo; o agendador DEVE classificar os posts novos de perfis com taxonomia
  salva assim que chegam ao marco da medida, com limite diário de chamadas por perfil (padrão 50,
  constante), deixando o excedente "aguardando classificação" para o dia seguinte; a análise da IA dos
  melhores DEVE ser só sob demanda do dono. O dono DEVE poder pedir "classificar pendentes" a qualquer
  momento (respeitando o mesmo limite).
- **FR-052**: Toda chamada de IA desta spec DEVE ir para o registro do assistente (008) com finalidade
  própria (`aprendizado.taxonomia`, `aprendizado.classificacao`, `aprendizado.analise`), desfecho e custo;
  o custo DEVE ser visível só para o dono, e a análise da IA DEVE mostrar o custo estimado antes de
  confirmar.
- **FR-053**: O dono DEVE poder pausar a classificação automática e o bloco de desempenho
  por perfil; pausar não apaga nada.
- **FR-054**: Nenhuma parte desta spec DEVE publicar, criar rascunho, aprovar, agendar, conectar conta ou
  falar com API de rede social (princípio I); a leitura das métricas continua sendo a da 016.
- **FR-055**: Clientes MCP (009) PODEM ler temas, classificações, análise e recomendações; NÃO DEVEM editar
  a taxonomia, corrigir classificação, aceitar, rejeitar nem mudar preferências.
- **FR-056**: Todo gráfico desta área DEVE seguir FR-005, FR-006 e FR-008 da 019 (leitura, tabela
  alternativa, CSV, paleta validada, celular) e usar o fuso America/Sao_Paulo.

### Key Entities

- **Tema:** do perfil; nome, descrição, palavras-chave, estado, versão e histórico. "Sem tema" é
  reservado.
- **Taxonomia (versão):** o conjunto de temas ativos de um perfil num momento; citado pelas classificações,
  análises e recomendações.
- **Classificação do post:** vídeo publicado (016) → tema principal, secundários, estilo do gancho,
  justificativa, origem (`ia`/`dono`), evidência parcial ou completa, versão da taxonomia, chamada do
  assistente, versão e histórico.
- **Efeito de fator** (calculado na leitura, não gravado): fator, valor, parte (entrega/rendimento), efeito
  encolhido, intervalo, n de posts e dias distintos, confiança, avisos (puxado por 1 post, não separável,
  distribuição travada, exploratório, em alta/queda).
- **Análise da IA:** perfil ou conta, posts usados (melhores e comparáveis), uso de quadros (sim/não, quantos por vídeo),
  hipóteses (frase, posts, n, contraste), chamada, custo, versão da taxonomia, data.
- **Recomendação:** tipo, alvo (tema, hashtag, padrão), escopo (perfil ou conta), motivo, evidência no
  momento, origem (regra ou hipótese), estado (aberta, aceita, rejeitada, superada), decisão do dono com
  motivo e data.
- **Preferências do perfil/conta:** temas (`ampliar`/`neutro`/`cortar`), hashtags a evitar, padrões
  (gancho, duração, janela de horário), uso do bloco de desempenho, versão e histórico com reversão.
  Hashtags a fixar vivem no guia (017).
- **Sinal de distribuição** (calculado na leitura): conta ou post, tipo, número, explicação.
- **Conferência do dono:** post, item do checklist, resultado, autor, data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com a taxonomia salva, 100% dos posts medidos do perfil têm tema (da IA ou do dono) até 24 h
  depois de chegarem ao marco da medida (classificação automática do agendador, FR-051), enquanto o
  limite diário não for atingido, e o dono corrige uma classificação em menos de 15 segundos.
- **SC-002**: Em 20 classificações revisadas pelo dono num perfil com taxonomia estável, pelo menos 80%
  ficam sem correção.
- **SC-003**: Todos os efeitos, intervalos, n e avisos batem com o cálculo de referência sobre os dados
  semeados nos testes (100% dos casos de concentração, coocorrência e distribuição travada).
- **SC-004**: Nenhuma recomendação nasce de grupo abaixo da amostra mínima, de efeito "não separável", de
  achado puxado por 1 post sem efeito restante, ou de conta em "distribuição travada" (0 casos nos testes).
- **SC-005**: O dono responde "que assunto ampliar e que assunto cortar nesta conta?" em menos de 1 minuto
  a partir da abertura da área, vendo a evidência de cada resposta.
- **SC-006**: 100% das aceitações, rejeições, correções e reversões aparecem no histórico com autor e data,
  e 100% das tentativas de membro ou MCP são recusadas e registradas.
- **SC-007**: Em 10 gerações de legenda com bloco de desempenho, 100% trazem as hashtags fixas, 0 trazem
  hashtag "evitar" e 0 trazem proibida aplicável sem edição; 100% das chamadas mostram a versão das
  preferências usada.
- **SC-008**: Com afinidade neutra (sem temas ou preferências), a ordem do Descobrir é idêntica à da 006;
  com preferências, nenhum vídeo `sem_acordo` passa sem o aviso de direito (0 casos nos testes).
- **SC-009**: O custo de IA desta spec aparece separado por finalidade no resumo do mês, e nenhum valor de
  custo chega a um membro.

## Assumptions

- **Dados:** usa o que já existe (016 métricas e vínculo; 006 cortes com transcrição, gancho e score,
  canais e vídeos-fonte; 014 destinos e hashtags; 019 medida do post, estagnação e mapa da audiência;
  020 histórico do Studio só para os totais da conta). Nenhuma coleta nova da rede.
- **Uma rede hoje:** as análises cobrem a TikTok; o modelo serve a outras redes quando elas tiverem
  métricas, sem dado falso.
- **Escopo da taxonomia:** por perfil (as contas do perfil compartilham os temas); efeitos podem ser
  vistos por conta ou para o perfil inteiro.
- **Estilos de gancho:** lista fixa em código (pergunta, revelação, número/lista, polêmica, humor,
  "você sabia", ordem direta, outro), sem edição pelo dono nesta spec.
- **Vídeos-fonte não são classificados pela IA:** o tema deles vem só do casamento das palavras-chave
  (determinístico, sem custo), porque são dezenas de milhares.
- **Estatística sem dependência pesada:** encolhimento, reamostragem e escala logarítmica cabem em código
  próprio, como a Spearman da 019; a escolha concreta (fórmula do encolhimento, número de reamostras)
  fica no plano.
- **Medida padrão:** views em 24 h (como a 019); a tela permite 1 h e 7 d.
- **Constantes ajustáveis** (amostra mínima, meia-vida, limites das regras, peso da afinidade) ficam em
  código, com o valor visível na nota de leitura; ajuste fino no `/speckit-clarify` ou depois de um ciclo
  real.
- **Hipóteses da IA não são fatos:** aparecem sempre como "a conferir"; só viram mudança quando o dono
  aceita uma recomendação.
- **Modelo de IA:** o mesmo cliente e registro da 008; a escolha do modelo por finalidade (ex.: mais
  barato na classificação) fica no plano.
- **Fora do escopo:** testes A/B controlados, previsão de views de um post antes de publicar, alteração
  automática de agenda, e classificação de posts de outras redes sem métricas.
