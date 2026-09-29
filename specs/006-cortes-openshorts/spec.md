# Feature Specification: Fontes, seleção de vídeos e cortes com o OpenShorts (006-cortes-openshorts)

**Feature Branch**: `006-cortes-openshorts`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Canais e fontes de vídeo, busca de vídeos da fonte, cadastro de vídeos da fonte (API do YouTube), envio para cortes no OpenShorts e integração com o OpenShorts. Estrutura completa de cortes: cadastro das fontes, seleção de vídeos (de uma lista ou upload manual), configuração e envio ao OpenShorts, aviso de processamento, e já propor título, descrição e hashtags para integrar depois com o TikTok (criar draft e postar na data e hora indicada). UX é o mais importante: facilitar que o usuário escolha de quais vídeos fazer corte e agende os cortes para serem postados."

## Clarifications

### Session 2026-09-29

- Q: Quem gera a proposta de título, descrição e hashtags? → A: O SociMan, com o Claude, usando o contexto do perfil (nicho, tom, bordões e séries do kit) e o conteúdo do clipe. O usuário edita antes de usar.
- Q: Como avisar que o processamento terminou? → A: No próprio app: status ao vivo, sino de notificações no painel e notificação do navegador quando o app está aberto ou instalado.
- Q: Upload manual e direito autoral? → A: Envio manual livre, por link ou arquivo. Os canais-fonte incluem canais parceiros, não só os próprios. O direito autoral é responsabilidade do dono, não do sistema (constitution 3.0.0, princípio II: status informativo, aviso e histórico, sem bloqueio). O sistema busca **todos** os vídeos dos canais cadastrados e **recomenda** quais usar, e o usuário escolhe quais cadastrar para corte.
- Q: Postar no TikTok (criar draft e postar na data e hora)? → A: **Fora desta spec.** Aqui ficam só a data e hora planejadas e os textos prontos. Publicar ou mandar rascunho para o TikTok exige outra spec e, para publicação automática, uma emenda do princípio I da constitution, que continua proibindo o SociMan de publicar.
- Q: "Hora de postar" com o app fechado (open-questions Q1)? → A: **Só com o app aberto** (aba ou app instalado): sino e Notification API do navegador (`registration.showNotification` com o service worker, senão `new Notification`). **Sem Web Push** nesta spec. Com o app fechado, os avisos ficam guardados no sino.
- Q: Um corte em várias redes (open-questions Q2)? → A: **Uma postagem por conta de destino.** Cada postagem tem textos, data e hora e "Postado" próprios, e a tela do corte tem uma aba por conta.
- Q: Membro pode enviar vídeo "Sem acordo" ou avulso (open-questions Q3)? → A: **Sim.** Dono e membro enviam depois de ver e confirmar o aviso, e o histórico registra quem confirmou. Só o dono muda o status de direito do canal.
- Q: Estilo da legenda dos clipes (open-questions Q4)? → A: **Legenda do kit do perfil**, refeita pelo `/api/subtitle` do OpenShorts antes da importação (+30 a 60 s de CPU por clipe). O padrão de corte do perfil ainda permite "gerador" ou "nenhuma". O tempo da legenda conta como parte do processamento do envio (SC-003).
- Q: Evidência de direito por print? → A: **Link ou nota nesta spec**; upload de imagem (print) entra depois da 007, usando a biblioteca de assets.
- Q: Envio e corte sem reversão por snapshot? → A: **Sim, exceção aceita do princípio VII**: voltar atrás é arquivar/restaurar o corte ou fazer um envio novo; o histórico continua visível.
- Q: Nome do menu dos canais? → A: **"Canais-fonte"** (evita colisão com a aba "Fontes" de tipografia do perfil).
- Q: Como mostrar o progresso do processamento? → A: Etapa real do OpenShorts em pt-BR (na fila,
  baixando, transcrevendo, escolhendo os momentos, gerando os clipes, legendando, importando), com o
  % da etapa quando o OpenShorts o informa e "clipe N de M" na geração, na legenda e na
  importação. O % geral é uma **estimativa ponderada por etapa**. O sino só avisa as transições
  importantes: momentos escolhidos, pronto, sem clipes e falhou.
- Q: Formato do texto de progresso? → A: Sempre o % geral junto da etapa, numa linha só:
  "Processando 10% · Transcrevendo o vídeo 25%", "Processando 55% · Cortando clipe 3 de 9 (cenas
  40%)", "Processando 85% · Aplicando legendas do kit 2 de 9", "Processando 95% · Importando 4 de
  9"; na fila, "Na fila do OpenShorts (2º)". Rótulos: Baixando o vídeo, Transcrevendo o vídeo,
  Escolhendo os momentos, Cortando os clipes, Aplicando legendas do kit, Importando. O detalhe do
  envio lista as etapas, com check nas concluídas e a atual destacada.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cadastrar canais-fonte (Priority: P1)

O usuário cadastra os canais de onde saem os cortes, sejam próprios ou de parceiros, colando o
link ou o @ do canal no YouTube. O sistema preenche nome, avatar e número de vídeos. O dono marca
o status de direito do canal (próprio, parceiro, programa de cortes, sem acordo), com evidência
opcional, e liga o canal a um ou mais perfis da agência.

**Why this priority**: tudo começa pela fonte. Sem canal cadastrado não há vídeos para escolher.

**Independent Test**: colar `https://www.youtube.com/@theitnerd`, ver o canal aparecer com nome e
avatar, marcar "Próprio" e ligar ao perfil A Taverna Nerd.

**Acceptance Scenarios**:

1. **Given** um link, @ ou ID de canal do YouTube, **When** o usuário cadastra, **Then** o sistema
   identifica o canal e mostra nome, avatar, inscritos e total de vídeos.
2. **Given** um canal já cadastrado, **When** alguém tenta cadastrá-lo de novo, **Then** o sistema
   avisa e abre o existente.
3. **Given** um canal, **When** o **dono** muda o status de direito, **Then** a mudança entra no
   histórico com autor e data; um `membro` não consegue mudar.
4. **Given** um canal com status "Sem acordo", **When** ele aparece em listas, **Then** mostra um
   selo de aviso.

---

### User Story 2 - Descobrir e escolher os vídeos (Priority: P1)

O sistema busca **todos** os vídeos dos canais cadastrados e mostra uma lista de **recomendações**
ordenada pelo potencial de corte: desempenho recente (views por hora e por dia), duração
adequada, idade do vídeo e ainda não usado. O usuário filtra (canal, perfil, período, duração,
"ainda não cortado"), vê miniatura, título, duração, views e o motivo da recomendação, e com um
clique **seleciona** os vídeos que quer cortar.

**Why this priority**: a escolha rápida dos vídeos é a parte mais importante da UX (pedido do
dono).

**Independent Test**: com dois canais cadastrados, abrir "Descobrir", ver os vídeos ordenados com o
motivo ("12 mil views/h nas últimas 24 h"), filtrar "até 20 min" e "não cortados", e selecionar
três vídeos.

**Acceptance Scenarios**:

1. **Given** canais cadastrados, **When** o usuário abre "Descobrir", **Then** vê os vídeos de todos
   os canais, com miniatura, título, canal, duração, publicação, views e views por hora, ordenados
   pela pontuação de recomendação e com o motivo em uma linha.
2. **Given** a lista, **When** o usuário aplica filtros ou busca por texto, **Then** a lista reflete
   os filtros instantaneamente.
3. **Given** um vídeo, **When** o usuário clica em "Selecionar para corte", **Then** o vídeo entra na
   lista de "Selecionados" do perfil escolhido; vídeos já cortados aparecem marcados.
4. **Given** um canal novo, **When** ele é cadastrado, **Then** a busca dos vídeos começa sozinha, e
   a lista é atualizada periodicamente (vídeos novos aparecem sem ação do usuário).
5. **Given** um vídeo de outro lugar, **When** o usuário cola um link avulso (YouTube ou outro) ou
   envia um arquivo, **Then** o vídeo entra nos "Selecionados" como envio avulso, com o aviso de
   direito (princípio II).

---

### User Story 3 - Configurar e enviar ao OpenShorts (Priority: P1)

Para os vídeos selecionados, o usuário escolhe o perfil e a configuração do corte e envia ao
OpenShorts. A configuração vem pré-preenchida pelos **padrões de corte do perfil**: duração mínima
e máxima, quantidade de clipes, layout, estilo de legenda vindo do kit (004) e sem o gancho
automático. Antes de enviar, o sistema mostra o aviso de direito quando o vídeo é de canal "Sem
acordo" ou avulso. Depois do envio, acompanha o processamento e **avisa** quando termina.

**Why this priority**: é o coração do fluxo de cortes.

**Independent Test**: selecionar um vídeo, conferir a configuração pré-preenchida do perfil,
enviar, ver o status "Na fila → Processando 10% · Transcrevendo o vídeo 25% → … · Cortando clipe
3 de 9 → … · Aplicando legendas do kit → Pronto" com a barra do % geral, e receber a notificação no sino do
painel.

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o usuário define os padrões de corte (duração 15–60 s, até N
   clipes, layout automático, legenda do kit), **Then** esses padrões preenchem todo envio daquele
   perfil, e podem ser ajustados envio a envio.
2. **Given** vídeos selecionados, **When** o usuário clica em "Enviar para corte", **Then** cada vídeo
   vira um job no OpenShorts com a configuração, e o status aparece na lista de envios.
3. **Given** um vídeo de canal "Sem acordo" ou avulso, **When** o usuário vai enviar, **Then** vê o
   aviso "O direito autoral deste vídeo é de sua responsabilidade" e confirma; o envio registra o
   status de direito no histórico.
4. **Given** um job em andamento, **When** ele termina (ou falha), **Then** o usuário recebe a
   notificação no app (sino + notificação do navegador se permitida e o app estiver aberto) com
   link para o resultado.
5. **Given** o OpenShorts fora do ar, **When** o usuário envia, **Then** o envio fica "Aguardando o
   OpenShorts" e é retomado sozinho quando ele volta.
6. **Given** um job em processamento, **When** o usuário abre a lista ou o detalhe do envio,
   **Then** vê numa linha o % geral e a etapa real em pt-BR, com ícone (ex.: "Processando 10% ·
   Transcrevendo o vídeo 25%", "Processando 55% · Cortando clipe 3 de 9 (cenas 40%)", "Na fila do
   OpenShorts (2º)"), a barra do % geral estimado; no detalhe, a lista das etapas com check nas
   concluídas e a atual destacada. O sino avisa uma vez quando os momentos são escolhidos (sem um
   aviso por etapa).

---

### User Story 4 - Clipes gerados viram cortes do perfil (Priority: P1)

Os clipes gerados pelo OpenShorts entram automaticamente como cortes do perfil, ligados ao vídeo
e ao canal de origem, e já podem receber a marca do kit (004). O usuário revisa os clipes de cada
envio lado a lado, descarta os ruins (arquivar) e manda aplicar a marca nos bons (ou em todos
automaticamente, se configurado no perfil).

**Why this priority**: sem trazer os clipes de volta, o fluxo termina fora do SociMan.

**Independent Test**: com um envio pronto, abrir o envio, ver os N clipes com player, arquivar um,
aplicar a marca nos outros e vê-los na aba Cortes do perfil.

**Acceptance Scenarios**:

1. **Given** um job pronto, **When** o SociMan importa os clipes, **Then** cada clipe vira um corte
   com origem (vídeo, canal, trecho), título e descrição sugeridos pelo OpenShorts e o status de
   direito no momento.
2. **Given** os clipes, **When** o usuário os revisa, **Then** pode assistir, arquivar os que não
   servem e aplicar a marca em um ou vários de uma vez.
3. **Given** o perfil com "aplicar marca automaticamente", **When** os clipes chegam, **Then** a marca
   é aplicada sem ação do usuário.

---

### User Story 5 - Preparar a postagem e agendar (Priority: P2)

Para cada corte pronto, o SociMan propõe **título, descrição e hashtags** no tom do perfil
(Claude, usando nicho, bordões e séries do kit e o conteúdo do clipe). O usuário escolhe as
**contas de destino** (uma postagem por conta, cada uma com seus textos), edita e define a **data e
hora planejadas** de cada uma. Um **calendário** mostra os cortes
agendados por perfil e dia. Nada é publicado. Quando chegar a hora, o SociMan avisa no app que
aquele corte está programado para agora, com os textos e o vídeo prontos para o dono postar.

**Why this priority**: prepara a integração futura com o TikTok e já organiza a rotina de postagem.

**Independent Test**: num corte pronto, clicar em "Sugerir textos", editar o título, escolher
TikTok e amanhã às 19:00; ver o corte no calendário; quando chegar a hora, receber o aviso "Hora
de postar", com botões para copiar os textos e baixar o vídeo.

**Acceptance Scenarios**:

1. **Given** um corte pronto, **When** o usuário pede sugestão, **Then** recebe título (até 100
   caracteres), descrição (até 2.000) e 3 a 8 hashtags, coerentes com o perfil e o clipe, em pt-BR;
   pode pedir outra versão.
2. **Given** os textos, **When** o usuário edita e salva, **Then** as versões ficam no histórico da
   postagem.
3. **Given** um corte com data e hora planejadas, **When** o usuário abre o calendário, **Then** vê o
   corte no dia e hora, por perfil e plataforma (uma entrada por postagem), e pode arrastar para
   remarcar.
4. **Given** a hora planejada, **When** ela chega, **Then** o app notifica "Hora de postar: <título>
   no <plataforma>" com atalhos para copiar título, descrição e hashtags e baixar o vídeo; o dono
   marca "Postado" manualmente.
5. **Given** um corte, **When** o usuário prepara a postagem para duas contas (ex.: TikTok e YouTube
   Shorts), **Then** cada conta tem a própria postagem, com textos, data e hora e "Postado"
   independentes.

---

### Edge Cases

- Canal com milhares de vídeos: a primeira busca pode levar alguns minutos, e a lista vai
  aparecendo aos poucos; o limite diário da API do YouTube é respeitado, com aviso quando estiver
  perto do fim.
- Vídeo removido ou privado depois de cadastrado: marcado como "Indisponível" e não pode ser
  enviado.
- Vídeo muito longo (> 3 h) ou transmissão ao vivo em andamento: aparece com aviso e não é
  recomendado.
- OpenShorts devolve 0 clipes: o envio fica "Sem clipes" com a razão.
- O mesmo vídeo enviado duas vezes para o mesmo perfil: o sistema avisa e pede confirmação.
- Chave da API do YouTube ausente ou inválida: a descoberta mostra uma mensagem clara e o cadastro
  manual por link continua funcionando.
- Falha do Claude na sugestão de textos: mensagem clara, e os campos continuam editáveis à mão.
- O usuário fecha o app com jobs em andamento: o acompanhamento continua no servidor, e as
  notificações ficam no sino.

## Requirements *(mandatory)*

### Functional Requirements

**Canais-fonte**
- **FR-001**: Usuários logados DEVEM poder cadastrar canais do YouTube por link, @ ou ID; o sistema
  DEVE preencher nome, avatar, inscritos e total de vídeos.
- **FR-002**: Cada canal DEVE ter um status de direito informativo (`proprio`, `parceiro`,
  `programa_de_cortes` ou `sem_acordo`) e uma evidência opcional; **só o dono** muda o status
  (princípio II).
- **FR-003**: Um canal DEVE poder ser ligado a um ou mais perfis; canais seguem as regras de
  histórico, arquivamento e reversão da spec 003 (princípio VII).

**Descoberta e seleção**
- **FR-004**: O sistema DEVE buscar todos os vídeos de cada canal cadastrado, com título, miniatura,
  duração, data de publicação e métricas (views, likes, comentários), e atualizar periodicamente
  (vídeos novos e métricas).
- **FR-005**: O sistema DEVE calcular uma pontuação de recomendação por vídeo e um motivo em uma
  linha, a partir de views por hora recentes, idade, duração adequada ao corte, engajamento e se já
  foi usado.
- **FR-006**: A tela de descoberta DEVE permitir filtrar por canal, perfil, período, duração, "não
  cortados" e texto, ordenar por pontuação, views ou data, e selecionar vários vídeos para um
  perfil.
- **FR-007**: O usuário DEVE poder adicionar vídeo avulso por link (YouTube ou outro) ou por upload
  de arquivo, que entra nos selecionados como envio avulso.

**Envio ao OpenShorts**
- **FR-008**: Cada perfil DEVE ter padrões de corte (duração mínima e máxima, quantidade de clipes,
  layout, estilo de legenda derivado do kit e gancho automático desligado), usados como padrão em
  cada envio e ajustáveis por envio.
- **FR-009**: O envio DEVE mostrar o aviso de direito quando o vídeo é de canal `sem_acordo` ou
  avulso, pedir confirmação e registrar no histórico o autor, a data, a fonte e o status de direito
  (princípio II). Dono e membro podem enviar depois de confirmar o aviso; nada bloqueia.
- **FR-010**: O sistema DEVE enviar cada vídeo ao OpenShorts, acompanhar o status até o fim e
  sobreviver a reinício (do SociMan ou do OpenShorts), retomando o acompanhamento.
- **FR-010a**: Durante o processamento, o sistema DEVE mostrar a **etapa real** (fila, baixando,
  transcrevendo, escolhendo os momentos, gerando os clipes, legendas, importando, concluído ou
  erro), lida do `status`, dos `logs`, da `queue` e do `partial` do OpenShorts, com o % da etapa
  quando houver, "clipe N de M" e um % geral estimado e ponderado por etapa. Linha de log
  desconhecida nunca quebra o acompanhamento: a etapa continua a última reconhecida.
- **FR-011**: O usuário DEVE ser avisado no app quando um envio termina ou falha: sino de
  notificações com lista e marcação de lidas, e notificação do navegador quando permitida e o app
  estiver aberto (aba ou app instalado). Web Push com o app fechado fica fora desta spec.

**Clipes → cortes**
- **FR-012**: Os clipes gerados DEVEM ser importados como cortes do perfil (spec 004), com origem
  (vídeo, canal, trecho), textos sugeridos pelo OpenShorts e o status de direito no momento.
- **FR-013**: O usuário DEVE poder revisar os clipes de um envio, arquivar clipes e aplicar a marca
  do kit em um ou vários; o perfil pode ligar "aplicar marca automaticamente".

**Preparação da postagem**
- **FR-014**: Para cada corte, o sistema DEVE propor título (até 100 caracteres), descrição (até
  2.000) e 3 a 8 hashtags em pt-BR, no tom do perfil, usando o kit e o conteúdo do clipe; o usuário
  pode pedir outra versão e editar.
- **FR-015**: Cada corte DEVE poder ter uma **postagem por conta de destino** (a conta dá a
  plataforma), cada uma com textos, data e hora planejadas e estado (`rascunho`, `agendado`,
  `postado` marcado à mão), com histórico.
- **FR-016**: DEVE existir um calendário com os cortes agendados por dia, perfil e plataforma, com
  remarcação por arrastar.
- **FR-017**: Na hora planejada, o app DEVE notificar "Hora de postar" (sino e, com o app aberto,
  notificação do navegador), com atalhos para copiar os textos e baixar o vídeo. O SociMan **NÃO
  publica** (princípio I).

### Key Entities

- **Canal-fonte**: canal do YouTube (ID, nome, avatar, inscritos), status de direito, evidência,
  perfis ligados e a última atualização dos vídeos.
- **Vídeo-fonte**: vídeo de um canal (ID do YouTube, título, miniatura, duração, publicação,
  métricas com histórico), pontuação e motivo da recomendação, disponibilidade e "já usado".
- **Seleção**: vídeo escolhido para um perfil, aguardando envio (inclui avulsos por link ou
  arquivo).
- **Padrões de corte**: por perfil (duração, quantidade, layout, legenda e marca automática).
- **Envio (job)**: um vídeo enviado ao OpenShorts, com configuração, status, progresso, erro,
  status de direito no momento, autor e datas.
- **Corte** (da 004, ampliado): origem (envio, vídeo, trecho), textos sugeridos pelo OpenShorts e
  o estilo de legenda aplicado.
- **Postagem**: um corte numa conta de destino, com título, descrição e hashtags (com versões),
  data e hora planejadas e estado de postagem.
- **Notificação**: aviso ao usuário (envio concluído ou falhou, hora de postar), lida ou não.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Do cadastro de um canal à lista de vídeos recomendados, menos de 2 minutos para
  canais de até 500 vídeos.
- **SC-002**: Escolher 5 vídeos e enviar todos para corte leva menos de 1 minuto na tela.
- **SC-003**: 100% dos envios terminados (ou com falha) geram notificação no app em menos de 1
  minuto depois do fim do processamento. Com a legenda do kit, o processamento inclui refazer a
  legenda de cada clipe (+30 a 60 s de CPU por clipe) e a importação; uma falha no OpenShorts
  notifica em menos de 1 minuto.
- **SC-004**: 100% dos clipes de um envio pronto aparecem como cortes do perfil, sem ação manual.
- **SC-005**: A sugestão de textos chega em menos de 15 segundos, e os textos respeitam os limites
  (título ≤ 100, 3–8 hashtags).
- **SC-006**: O dono agenda a semana de cortes de um perfil (7 cortes) em menos de 5 minutos pelo
  calendário.
- **SC-007**: Nenhum caminho do sistema publica em rede social (verificado por teste).

## Assumptions

- A chave da API do YouTube Data v3 já existe (em `~/.config/openclaw/youtube.env`) e passa a ser
  configurada também no SociMan; o limite diário de cota é o padrão (10.000 unidades).
- O OpenShorts local (`../openshorts`, API em `localhost:8000`) é o gerador de clipes; o SociMan o
  chama pela API (sem mudar o código dele), com `auto_hook` desligado, porque o gancho vem do kit.
- A chave da Anthropic (Claude) passa a ser configurada no SociMan (fora do git) para a sugestão de
  textos.
- Só YouTube como plataforma de canais-fonte nesta spec (TikTok e Instagram como fonte ficam para
  depois); links avulsos de outras plataformas entram só como envio avulso.
- Postar no TikTok ou em outra rede (rascunho ou publicação agendada) fica numa spec futura; a
  publicação automática exige emendar o princípio I.
- Downloads de vídeos do YouTube, quando necessários, usam as ferramentas já instaladas (yt-dlp) e
  ficam no HD (constitution 2.1.0).
