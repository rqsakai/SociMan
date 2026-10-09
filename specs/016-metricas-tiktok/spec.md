# Feature Specification: Métricas do TikTok para análise e machine learning (016-metricas-tiktok)

**Feature Branch**: `016-metricas-tiktok`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "Pela API do TikTok, ter acesso às análises da conta e dos posts (público, views
etc.) para fazer a coleta de dados e usar em machine learning depois."

## Clarifications

### Session 2026-09-30

- Q: Qual API nesta etapa? → A: A mesma do app atual (dados públicos da conta e dos vídeos). Alcance,
  retenção, fontes de tráfego e audiência exigem outra API com aprovação e ficam para uma spec futura.
  Base: `docs/pesquisa/metricas-tiktok.md`.
- Q: Tipo das contas? → A: @atavernanerd e @meusqueridinhos10 são **Pessoais** (dono).
- Q: Permissões? → A: As permissões de métricas já estão ativas no app (sandbox). O SociMan passa a pedi-las
  no login e o dono **reconecta** as contas; a tela avisa quando uma conexão não as tem.
- Q: E se uma conta for desconectada? → A: As métricas guardadas são **anonimizadas**, não apagadas (dono).
- Q: Na anonimização, quais características do corte ficam? → A: **Só as não textuais** (dono, Q1 = A):
  origem, modo de envio, nota da recomendação, status do canal-fonte, duração, hora e dia da
  publicação, intervalo desde o post anterior, seguidores na publicação, **tamanho** do gancho e
  **número** de hashtags. O texto do gancho, a legenda e as hashtags saem.
- Q: Vídeos com mais de 1 ano na primeira varredura? → A: Entram com **uma foto** (a da descoberta,
  que vem na própria lista) e param aí; os mais novos seguem a cadência (dono, Q2 = A).
- Q: Ligar sozinho os posts feitos pelo lembrete (sem rascunho)? → A: **Só depois de "Marcar como
  postado"** (dono, Q3 = A). A hora do clique vira a âncora: o post precisa ter sido publicado até
  24 h antes ou até 1 h depois do clique, com a mesma regra de duração (±1 s), legenda compatível
  e candidato único nos dois sentidos. Antes do clique, o destino de lembrete mostra os candidatos
  e o dono escolhe em 1 clique (o que também o marca como postado).
- Q: Onde guardar as métricas? → A: **Só no PostgreSQL** que já existe, sem banco novo (dono, Q4 =
  A). Para pausar a coleta sem desconectar (desconectar anonimiza), o dono usa
  `METRICAS_COLETA_HABILITADA=false` no `.env`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Liberar a coleta numa conta (Priority: P1)

Na aba Contas do perfil, a conta TikTok conectada mostra se já tem as permissões de métricas. Sem elas,
aparece "Reconectar para liberar métricas"; o dono reconecta (mesmo login da spec 015) e a coleta
começa sozinha para aquela conta.

**Why this priority**: sem as permissões, nada é coletado.

**Independent Test**: com @atavernanerd conectada antes desta spec, ver o aviso, reconectar e, em até
uma hora, ver a primeira foto das métricas da conta.

**Acceptance Scenarios**:

1. **Given** uma conexão sem as permissões de métricas, **When** o dono abre a conta, **Then** vê o aviso
   e o botão de reconectar; nenhuma coleta é tentada.
2. **Given** a reconexão com as permissões, **When** ela termina, **Then** a conta passa a "coletando
   métricas", com a data da última coleta.
3. **Given** um membro, **When** ele abre a conta, **Then** vê o estado da coleta, mas não reconecta.

---

### User Story 2 - Série temporal da conta e dos vídeos (Priority: P1)

O SociMan guarda, sem nunca sobrescrever, fotos periódicas:
- **da conta**: seguidores, seguindo, curtidas totais, número de vídeos;
- **de cada vídeo público**: visualizações, curtidas, comentários, compartilhamentos, além de duração,
  data de publicação, legenda e link.

A frequência depende da idade do vídeo: de hora em hora nas primeiras 48 h, uma vez por dia até 30 dias,
uma vez por semana até 90 dias e uma vez por mês até 1 ano. A conta é fotografada uma vez por dia (e
de hora em hora enquanto houver vídeo nas primeiras 48 h). Vídeos publicados fora do SociMan também são
coletados.

**Why this priority**: a série temporal é a base de todo o resto (telas, ranking, dataset para ML).

**Independent Test**: com uma conta liberada e um vídeo publicado, ver após algumas horas várias fotos
do vídeo com os números crescendo e uma foto diária da conta.

**Acceptance Scenarios**:

1. **Given** uma conta liberada, **When** passa o tempo, **Then** cada vídeo público ganha fotos na
   frequência da sua idade, e cada foto guarda o momento da coleta.
2. **Given** um vídeo com mais de 1 ano, **When** a coleta roda, **Then** ele não é mais fotografado (as
   fotos antigas continuam). Na primeira varredura, ele entra com uma única foto, a da descoberta.
3. **Given** a TikTok fora do ar ou limitando as consultas, **When** a coleta falha, **Then** tenta de novo
   depois, sem perder a cadência dos outros vídeos, e o erro fica visível no estado da conta.
4. **Given** um vídeo que deixou de ser público ou foi apagado, **When** a coleta não o encontra, **Then**
   ele é marcado como "indisponível desde…" e as fotos anteriores são mantidas.

---

### User Story 3 - Ligar o vídeo da TikTok ao conteúdo do SociMan (Priority: P1)

Cada vídeo coletado é ligado, quando possível, ao conteúdo e ao destino do SociMan que o originou:
1. pelo identificador que a TikTok devolve quando o rascunho enviado pelo SociMan é publicado (o
   SociMan continua consultando o envio por até 14 dias depois de entregar o rascunho);
2. se não vier, pela lista de vídeos da conta: publicado depois da entrega do rascunho, com duração igual
   (±1 s) e legenda compatível;
3. por último, o dono cola o link do post no destino, ou escolhe o post entre os candidatos.

Nos destinos de **lembrete** (o dono posta à mão), o nível 2 só vale depois de "Marcar como postado",
com a hora do clique como âncora (Clarifications, Q3). Antes disso, o destino mostra os candidatos e
o dono escolhe em 1 clique.

Quando o vínculo é feito, o link do post aparece no destino. Um rascunho entregue passa a
"publicado"; um lembrete escolhido ou com link colado passa a "postado"; um destino já "publicado"
ou "postado" não muda de estado. Vídeos sem vínculo aparecem como "fora do SociMan".

**Why this priority**: sem o vínculo, as métricas não se juntam às características do corte (gancho,
canal-fonte, nota), que é o que interessa para ML.

**Independent Test**: publicar pelo app o rascunho enviado pelo SociMan e ver, em até um dia, o destino
virar "publicado" com o link e as métricas aparecerem no conteúdo.

**Acceptance Scenarios**:

1. **Given** um rascunho entregue, **When** o dono o publica no app, **Then** o SociMan detecta o post e
   liga o vídeo ao destino, sem ação humana.
2. **Given** dois candidatos possíveis na lista de vídeos, **When** o casamento é ambíguo, **Then** nada é
   ligado sozinho e o destino mostra "escolha o post" com os candidatos.
3. **Given** um link colado pelo dono, **When** ele é de outra conta, **Then** é recusado com o motivo.
4. **Given** um vínculo errado, **When** o dono desfaz, **Then** o vídeo volta a "sem vínculo" e o histórico
   registra a troca.
5. **Given** um destino de lembrete que o dono marcou como postado (sem link), **When** a coleta acha um
   único post da conta publicado até 24 h antes ou 1 h depois do clique, com a duração e a legenda
   compatíveis, **Then** o vínculo é feito sozinho; com 2 ou mais candidatos, o destino mostra "escolha
   o post".
6. **Given** um destino de lembrete ainda não marcado como postado, **When** o dono o abre, **Then** vê os
   posts candidatos da conta e, ao escolher um, o destino vira "postado" ligado a ele.

---

### User Story 4 - Ver o desempenho (Priority: P2)

- **Conta**: gráfico de seguidores e curtidas ao longo do tempo, com os vídeos publicados marcados.
- **Conteúdo/destino**: curva de visualizações, curtidas, comentários e compartilhamentos desde a
  publicação, com os números de 1 h, 24 h, 7 dias e 30 dias.
- **Ranking**: lista dos vídeos da conta ou do perfil ordenável por visualizações em 24 h, 7 dias,
  engajamento (curtidas + comentários + compartilhamentos ÷ visualizações) e velocidade, filtrável por
  período, perfil e origem (corte, vídeo próprio, fora do SociMan).

**Why this priority**: o dono quer entender o que funciona antes mesmo do modelo.

**Independent Test**: com uma semana de coleta, abrir o ranking da Taverna e ver os vídeos ordenados por
visualizações em 7 dias, e abrir o melhor para ver a curva.

**Acceptance Scenarios**:

1. **Given** fotos de um vídeo, **When** o usuário abre o destino, **Then** vê a curva e os marcos 1 h, 24 h,
   7 d e 30 d (ou "ainda não" quando o vídeo é mais novo).
2. **Given** o ranking, **When** o usuário troca a ordenação ou os filtros, **Then** a lista reflete a
   escolha e o link leva ao conteúdo no SociMan (ou ao post, se for de fora).

---

### User Story 5 - Exportar o dataset (Priority: P2)

O dono exporta o dataset em CSV ou JSON, escolhendo período, perfil e conta:
- uma linha por foto de vídeo (métricas + momento + idade do vídeo na coleta);
- as características do SociMan de cada vídeo ligado: perfil, conta, origem, canal-fonte, nota da
  recomendação, gancho, legenda, hashtags, duração, horário e dia da semana da publicação, modo de envio;
- e um arquivo das fotos da conta.

**Why this priority**: é a entrada do machine learning; pode vir depois das telas.

**Independent Test**: exportar a Taverna do último mês em CSV e abrir numa planilha com uma linha por
foto e as colunas de características preenchidas nos vídeos ligados.

**Acceptance Scenarios**:

1. **Given** o filtro escolhido, **When** o dono exporta, **Then** recebe o arquivo com cabeçalho estável e
   documentado (nome e significado de cada coluna).
2. **Given** vídeos sem vínculo, **When** exporta, **Then** eles vêm com as colunas do SociMan vazias e a
   origem "fora do SociMan".
3. **Given** uma conta anonimizada, **When** exporta, **Then** os dados dela vêm sem nada que a identifique.

---

### Edge Cases

- Conta sem vídeos públicos: só as fotos da conta.
- Vídeo privado ou "só amigos": não aparece na lista da TikTok; não é coletado (aviso na ajuda).
- Números que diminuem (a TikTok corrige contagens): gravar como vieram; a curva mostra a queda.
- Conta desconectada: a coleta para; as fotos já guardadas são anonimizadas (sem @, nome, foto, legenda
  e link), mantendo os números e as características **não textuais** do corte (Clarifications, Q1).
- Pausar a coleta sem desconectar: `METRICAS_COLETA_HABILITADA=false`; nada é apagado nem anonimizado.
- Conta reconectada depois de anonimizada: a coleta recomeça como conta nova (a série antiga continua
  anônima).
- Limite de consultas atingido: a coleta espera e retoma; nenhuma foto é duplicada no mesmo horário.
- Relógio: tudo em horário de São Paulo nas telas; as fotos guardam o momento exato.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O login das contas TikTok DEVE pedir as permissões de métricas; conexões antigas sem elas
  DEVEM mostrar o aviso de reconectar, e só o dono reconecta.
- **FR-002**: O SociMan DEVE guardar fotos periódicas da conta (seguidores, seguindo, curtidas, nº de
  vídeos) e de cada vídeo público (visualizações, curtidas, comentários, compartilhamentos, duração,
  data, legenda, link), sem nunca sobrescrever uma foto.
- **FR-003**: A cadência por vídeo DEVE ser: de hora em hora até 48 h de idade, diária até 30 dias, semanal
  até 90 dias, mensal até 365 dias; depois, parar. Um vídeo que já tem mais de 365 dias quando é
  descoberto entra só com a foto da descoberta. A conta: diária, e de hora em hora enquanto houver
  vídeo com menos de 48 h.
- **FR-004**: A coleta DEVE respeitar os limites da TikTok, tentar de novo em falhas temporárias e mostrar
  o último erro e a última coleta por conta. O dono DEVE poder pausar a coleta sem desconectar
  (`METRICAS_COLETA_HABILITADA=false`), sem apagar nem anonimizar nada.
- **FR-005**: Cada vídeo DEVE ser ligado ao destino do SociMan pelo identificador devolvido após a
  publicação (consultando o envio por até 14 dias), senão pelo casamento na lista de vídeos (data, duração
  ±1 s, legenda) quando houver um único candidato nos dois sentidos, senão pelo link colado ou pela
  escolha do dono; ambiguidade nunca é resolvida sozinha. No casamento, a âncora de data é a entrega do
  rascunho; num destino de **lembrete**, é a hora em que o dono marcou "postado" (post até 24 h antes ou
  1 h depois), e antes disso só o dono liga (escolha ou link). Ligar DEVE mostrar o link no destino e
  mover um rascunho entregue para "publicado" (um lembrete escolhido ou com link vai para "postado").
- **FR-006**: O dono DEVE poder desfazer e refazer um vínculo, com histórico.
- **FR-007**: As telas DEVEM mostrar a evolução da conta, a curva de cada vídeo com os marcos 1 h/24 h/7 d/30 d
  e um ranking ordenável e filtrável.
- **FR-008**: O dono DEVE poder exportar o dataset (CSV e JSON) por período, perfil e conta, com as
  características do SociMan nos vídeos ligados e um dicionário das colunas.
- **FR-009**: Ao desconectar uma conta, as métricas guardadas DEVEM ser anonimizadas (sem identificação da
  conta nem dos posts), mantendo os números e só as características **não textuais** do corte (origem,
  modo de envio, nota, status do canal, duração, hora e dia, intervalo desde o post anterior, seguidores
  na publicação, tamanho do gancho e número de hashtags).
- **FR-010**: A coleta é só leitura: nada publica nem altera posts (princípio I). IA, agentes e MCP podem,
  numa spec futura, ler métricas; nunca escrever nas redes.

### Key Entities

- **Vídeo da rede**: identificador na TikTok, conta, link, legenda, duração, data de publicação, situação
  (disponível, indisponível desde…), vínculo com destino/conteúdo (e como foi feito).
- **Foto de vídeo**: vídeo, momento da coleta, idade na coleta, visualizações, curtidas, comentários,
  compartilhamentos.
- **Foto de conta**: conta, momento, seguidores, seguindo, curtidas, nº de vídeos.
- **Estado da coleta por conta**: permissões presentes, última coleta, último erro, próxima coleta.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Depois de reconectar, a primeira foto da conta aparece em até 1 hora.
- **SC-002**: 95% das fotos previstas pela cadência são coletadas no horário (com até 15 min de atraso).
- **SC-003**: 90% dos rascunhos publicados pelo dono no app são ligados ao destino sem ação humana em até
  24 h.
- **SC-004**: O dono encontra o top 5 da semana de um perfil em menos de 30 segundos.
- **SC-005**: A exportação de um mês de uma conta sai em menos de 1 minuto e abre numa planilha sem ajuste.
- **SC-006**: 0 fotos sobrescritas ou apagadas; 0 chamadas que publiquem ou alterem posts (verificado por
  teste).

## Assumptions

- Usa o app TikTok e as conexões da spec 015; nada de app ou login novos nesta etapa.
- As métricas ficam no PostgreSQL que já existe; nenhum banco novo (Clarifications, Q4).
- A API desta etapa só expõe vídeos **públicos** e números acumulados; alcance, tempo assistido, retenção,
  fontes de tráfego e audiência ficam para a etapa 2 (outra API, com aprovação e conta possivelmente
  Business).
- Não se sabe ainda com que atraso a TikTok atualiza as visualizações; a coleta de hora em hora será
  conferida nos primeiros dias e pode ser ajustada.
- Com 2 contas, o volume de consultas fica muito abaixo dos limites; o volume de dados para ML é pequeno
  no começo, por isso vale começar a coletar cedo.
- Uso dos dados só interno (SociMan e a agência), como pedem os termos da TikTok.
- Métricas do TikTok Shop (vendas de afiliado) ficam fora (outro programa da TikTok).
