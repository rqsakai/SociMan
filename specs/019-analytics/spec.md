# Feature Specification: Analytics de decisão (019-analytics)

**Feature Branch**: `019-analytics`

**Created**: 2026-10-01

**Status**: Draft

**Input**: User description: "Transformar /app/metricas num analytics de decisão, no estilo do dashboard
'AI Reports' do llm-microservice da autodoc (KPIs com comparação ao período anterior, heatmaps, radar
contra a média = 100, rankings 'principais' com drill-down, CSV por card, tabela por gráfico, notas de
leitura, estados vazios claros). Começar largo, 'mais para depois reduzir', com 8 abas: Visão geral,
Quando postar, O que funciona, Curvas, Contas/perfis/redes, Funil, Mercado e Alertas. Período global
com comparação, filtros por conta/perfil/rede, amostra mínima com aviso, acessível e responsivo.
Biblioteca de gráficos carregada sob demanda só nessa área (substitui a decisão de não usar biblioteca
da spec 016). Só leitura."

## Clarifications

### Session 2026-10-01

- Q: Como o analytics aparece no menu e o que acontece com a tela de métricas atual? → A: "Métricas"
  no menu abre o analytics (8 abas); o ranking atual vira um card da Visão geral e o detalhe do vídeo
  da 016 continua igual, como destino dos cliques.
- Q: Em que ordem as 8 abas são entregues? → A: Tudo de uma vez, numa entrega só (as prioridades P1–P3
  ordenam o trabalho, mas a spec só fecha com as 8 abas prontas).
- Q: Qual período a tela abre por padrão? → A: Últimos 7 dias, comparando com os 7 anteriores.
- Q: Quando um vídeo é "estagnado"? → A: Relativo à conta: depois de 6 h, abaixo de 10% da mediana de
  views da conta para a mesma idade; com menos de 5 vídeos na conta, usa o limite fixo de até 1 view.
- Q: Que medida de desempenho por post as comparações usam? → A: Seletor na tela entre views em 1 h,
  24 h e 7 d (padrão 24 h, marcos da 016); posts mais novos que o marco escolhido ficam fora das
  comparações e aparecem como "aguardando".

## Contexto

A 016 coleta, de hora em hora, as métricas públicas dos vídeos da TikTok (views, curtidas, comentários,
compartilhamentos) e da conta (seguidores, curtidas totais), e liga cada vídeo ao conteúdo do SociMan
de onde ele saiu (postagem → corte → envio → canal-fonte). A tela atual mostra um ranking e curvas por
vídeo, mas não responde às perguntas que o dono faz para decidir: **o que postar, quando postar, de
onde cortar e o que está dando errado**. Os dados para responder já estão no banco; faltam as análises
e a apresentação.

O que já existe e esta spec usa (sem coletar nada novo):

- **TikTok (016):** fotos horárias por vídeo e por conta, data e hora de publicação, duração e legenda,
  vínculo com o destino do SociMan.
- **Produção (006/014):** cortes (gancho, duração, score do SociShorts, canal-fonte), envios (tempos),
  destinos (modo lembrete ou rascunho, horário planejado e postado, hashtags).
- **Assistente de IA (008):** custo aproximado por chamada, ligado ao conteúdo.
- **YouTube dos canais-fonte (006):** vídeos dos canais-fonte com views, curtidas, duração, data de
  publicação e série temporal de views.

As amostras são pequenas hoje (1 conta conectada e menos de 20 vídeos). A tela precisa ser honesta com
isso: avisar quando a amostra não basta, sem esconder o dado.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visão geral do período (Priority: P1)

O dono abre o analytics e, numa tela, vê como o período foi: views, curtidas, engajamento, seguidores
ganhos, posts publicados e mediana de views por post, cada um com a variação contra o período
anterior de mesmo tamanho. Abaixo, a evolução diária por conta, os vídeos que mais renderam e cartões
de insight em frases ("posts publicados entre 18 h e 21 h tiveram 2,3× a mediana de views").

**Why this priority**: É a porta de entrada e responde "estamos crescendo?" em segundos. Sozinha, já
supera a tela atual.

**Independent Test**: Com dados semeados em dois períodos, abrir a visão geral e conferir os números,
as variações (sinal e %), a série diária e a ordem dos principais vídeos com os valores do banco.

**Acceptance Scenarios**:

1. **Given** um período de 7 dias com vídeos e fotos, **When** o dono abre a visão geral, **Then** vê
   os 6 indicadores do período, cada um com o valor do período anterior e a variação em %, e a seta
   ▲/▼ coerente com o sinal.
2. **Given** um período sem dado no período anterior, **When** a tela abre, **Then** a variação mostra
   "sem base de comparação" em vez de um percentual infinito ou zero.
3. **Given** dados suficientes para uma regra de insight, **When** a tela abre, **Then** aparece o
   cartão com a frase, o número que a sustenta e o tamanho da amostra (ex.: "n = 12 posts").
4. **Given** amostra abaixo do mínimo para uma regra, **When** a tela abre, **Then** o cartão não
   afirma nada e diz quantos posts faltam para a conclusão valer.

---

### User Story 2 - Quando postar (Priority: P1)

O dono quer saber em que dia e horário postar. A tela mostra um mapa de calor dia da semana × hora
(no fuso de Brasília) com o desempenho dos posts por horário de publicação (mediana de views em 24 h),
outro mapa com **quando a audiência de fato assiste** (views ganhas em cada hora, a partir das fotos
horárias) e um calendário do período com posts e views por dia.

**Why this priority**: Decisão diária de agenda; os dados horários da 016 permitem uma resposta que a
própria TikTok não dá na API pública.

**Independent Test**: Semear posts em horários conhecidos e fotos horárias com ganhos conhecidos;
conferir cada célula dos dois mapas e cada dia do calendário com o cálculo esperado.

**Acceptance Scenarios**:

1. **Given** posts publicados às terças 19 h com mediana de 24 h igual a 300, **When** abro o mapa por
   horário de publicação, **Then** a célula terça × 19 h mostra 300 e o número de posts dela.
2. **Given** fotos de um vídeo às 10 h (100 views) e às 11 h (160 views), **When** abro o mapa da
   audiência, **Then** 60 views são somadas na hora das 10 h às 11 h do dia correspondente.
3. **Given** um intervalo entre fotos de até 3 horas, **When** o mapa da audiência é calculado,
   **Then** o ganho é distribuído igualmente pelas horas do intervalo; ganhos de intervalos maiores
   (fotos diárias depois de 48 h) não entram no mapa e a nota de leitura mostra quantas views ficaram
   "sem hora atribuída".
4. **Given** uma célula com menos posts que o mínimo, **When** o mapa aparece, **Then** a célula fica
   marcada como amostra pequena (sem cor de intensidade cheia) e o tooltip diz o n.

---

### User Story 3 - O que funciona (Priority: P1)

O dono quer saber que tipo de conteúdo performa: a relação das views com a duração do clipe, o tamanho
do gancho e o score do SociShorts (a nota prevê alguma coisa?); o ranking dos canais-fonte de origem;
as hashtags que elevam ou derrubam a mediana; e o modo de envio (lembrete × rascunho).

**Why this priority**: Orienta o que cortar e como montar o post; usa a ligação exclusiva do SociMan
entre o vídeo publicado e o corte que o gerou.

**Independent Test**: Com vídeos vinculados a cortes de durações, ganchos, scores e canais conhecidos,
conferir os pontos das dispersões, a correlação mostrada, o ranking de canais e o "lift" de cada
hashtag.

**Acceptance Scenarios**:

1. **Given** vídeos vinculados com duração e views em 24 h, **When** abro a dispersão duração × views,
   **Then** cada ponto é um vídeo, o tooltip mostra título curto, duração e views, e clicar abre o
   vídeo.
2. **Given** pelo menos o mínimo de vídeos vinculados, **When** a dispersão aparece, **Then** mostra a
   correlação (de −1 a 1) com uma leitura em palavras (fraca, moderada, forte); abaixo do mínimo, só os
   pontos e o aviso de amostra pequena.
3. **Given** hashtags nas postagens e na legenda publicada, **When** abro o lift de hashtags, **Then**
   cada hashtag usada em pelo menos o mínimo de posts mostra a razão entre a mediana dos posts com ela e
   a mediana geral, ordenada do maior para o menor.
4. **Given** vídeos publicados fora do SociMan (sem vínculo), **When** abro as análises de corte,
   **Then** eles ficam fora delas e a tela diz quantos foram excluídos.

---

### User Story 4 - Curvas de crescimento (Priority: P2)

O dono compara como os vídeos crescem: views por idade do vídeo (horas desde a publicação), sobrepostas
ou em pequenos múltiplos por conta, a meia-vida de cada vídeo (tempo até alcançar 50% das views de 7
dias) e a distribuição de views por conta.

**Why this priority**: Mostra se um vídeo "pegou" cedo e ajuda a decidir quando parar de esperar por
ele; é complementar à visão geral.

**Independent Test**: Com séries semeadas, conferir os pontos da curva por idade, a meia-vida calculada
e os quartis da distribuição.

**Acceptance Scenarios**:

1. **Given** vídeos com fotos em idades diferentes, **When** abro as curvas, **Then** todas ficam
   alinhadas pela idade (eixo em horas desde a publicação), com destaque para um vídeo escolhido e os
   outros em cinza.
2. **Given** um vídeo com menos de 7 dias, **When** a meia-vida é mostrada, **Then** aparece "ainda não
   calculável" em vez de um número.

---

### User Story 5 - Contas, perfis e redes (Priority: P2)

O dono compara contas e perfis lado a lado e vê, num radar, o perfil de cada conta contra a média das
demais (média = 100), em 6 eixos: views por post, engajamento, frequência de posts, crescimento de
seguidores, velocidade na primeira hora e % de posts acima da mediana. Clicar numa conta abre o detalhe
dela com as mesmas análises filtradas.

**Why this priority**: Fica forte com mais contas conectadas; hoje há uma só, então vem depois das
análises que já rendem com uma conta.

**Independent Test**: Com duas ou mais contas semeadas, conferir os índices do radar (valor da conta ÷
média × 100) e a navegação de detalhe.

**Acceptance Scenarios**:

1. **Given** duas ou mais contas com dados, **When** abro o radar de uma conta, **Then** cada eixo mostra
   o índice contra a média, a linha da média em 100 e uma tabela eixo / conta / média / índice.
2. **Given** uma única conta com dados, **When** abro o radar, **Then** a tela explica que o radar
   precisa de pelo menos duas contas e mostra só a tabela de valores.
3. **Given** a lista de contas, **When** clico numa conta, **Then** abre o detalhe com trilha
   ("Contas → @conta") e todas as abas filtradas por ela.

---

### User Story 6 - Funil de produção (Priority: P2)

O dono vê o caminho do material: vídeos-fonte enviados → cortes gerados → cortes aprovados → posts
publicados → posts acima de um patamar de views, com a conversão em cada etapa, o tempo típico de cada
etapa (processamento no SociShorts, tempo até a postagem) e o custo de IA por mil views.

**Why this priority**: Mostra onde o processo perde material e quanto custa cada resultado; depende de
dados de várias specs, por isso vem depois.

**Independent Test**: Com envios, cortes, destinos e vídeos semeados, conferir as contagens e conversões
de cada etapa, as medianas de tempo e o custo por mil views.

**Acceptance Scenarios**:

1. **Given** envios e cortes do período, **When** abro o funil, **Then** cada etapa mostra a contagem e
   a % sobre a etapa anterior, e o tooltip lista o que caiu (ex.: cortes arquivados, sem clipes).
2. **Given** um usuário que não é dono, **When** abre o funil, **Then** não vê o custo de IA (como no
   resumo do assistente da 008).

---

### User Story 7 - Mercado: o YouTube de origem (Priority: P3)

O dono olha os canais-fonte: em que dias e horários publicam, quanto os vídeos ganham por hora nas
primeiras horas e quais vídeos-fonte estão "quentes" e ainda não foram cortados (oportunidade), com
atalho para selecioná-los em "Gerar cortes".

**Why this priority**: Usa a base mais rica que temos (dezenas de milhares de vídeos), mas o efeito é
indireto (escolher a matéria-prima); vem depois das análises do próprio desempenho.

**Independent Test**: Com vídeos-fonte e séries semeados, conferir o mapa de publicação dos canais, a
velocidade calculada e a lista de oportunidades (quentes e sem envio).

**Acceptance Scenarios**:

1. **Given** vídeos-fonte com séries de views, **When** abro "oportunidades", **Then** vejo os vídeos de
   maior velocidade recente que ainda não têm envio, com o status de direito do canal à vista.
2. **Given** um vídeo de canal `sem_acordo`, **When** uso o atalho para gerar cortes, **Then** o aviso de
   direito da 006 aparece como sempre (o analytics não pula o aviso).

---

### User Story 8 - Alertas (Priority: P3)

O dono recebe na própria tela a lista do que precisa de atenção: posts estagnados (views muito abaixo
do esperado para a idade, como 0 view após várias horas), quedas ou picos fora do padrão, conta sem
coleta recente e vídeos com vínculo ambíguo.

**Why this priority**: É o "o que está dando errado" — útil, mas depende das bases das outras abas.

**Independent Test**: Semear um vídeo com 0 view após o limite, uma conta sem coleta e um pico; conferir
que cada alerta aparece com a explicação e some quando a condição deixa de valer.

**Acceptance Scenarios**:

1. **Given** um vídeo com 6 h ou mais e views abaixo de 10% da mediana da conta para a mesma idade (ou
   até 1 view numa conta com menos de 5 vídeos), **When** abro os alertas, **Then** ele
   aparece como "estagnado", com a idade, as views e um lembrete do que conferir no app (ex.: se o post
   ficou restrito).
2. **Given** a condição que gerou o alerta deixa de valer, **When** a tela recarrega, **Then** o alerta
   some sozinho (nada é gravado como tarefa).

---

### Edge Cases

- **Período sem dado nenhum:** cada card mostra estado vazio com o motivo (ex.: "nenhum vídeo publicado
  no período") e um atalho para ampliar o período.
- **Conta desconectada e anonimizada (016):** entra nos totais como "Conta anônima N", sem rótulo; não
  aparece no filtro por conta pelo nome antigo.
- **Fotos atrasadas ou faltando:** os marcos usam a interpolação da 016 e mostram "estimado"; o mapa da
  audiência distribui só ganhos de intervalos de até 3 h e não inventa ganho onde não há foto posterior.
- **Views que diminuem entre fotos** (correção da rede): o ganho negativo conta como 0 no mapa da
  audiência e não derruba os totais.
- **Vídeo publicado fora do SociMan:** entra nas análises da TikTok (horário, curvas, totais) e fica
  fora das análises que dependem do corte (duração do clipe, gancho, score, canal-fonte, funil).
- **Hashtags com caixa ou acento diferentes:** são a mesma hashtag (comparação sem acento e sem caixa).
- **Fuso:** todos os dias e horas são de America/Sao_Paulo; um post às 23:30 de domingo em Brasília conta
  no domingo, mesmo que em UTC seja segunda.
- **Celular:** cada gráfico vira uma coluna; os mapas de calor podem rolar na horizontal dentro do
  próprio card, nunca a página inteira.
- **Muitos itens numa série categórica:** acima do limite de cores, o excedente vira "Outros".

## Requirements *(mandatory)*

### Functional Requirements

**Transversais**

- **FR-001**: O analytics DEVE ser aberto pela entrada "Métricas" do menu (no lugar da tela atual; o
  ranking da 016 vira um card da Visão geral e o detalhe do vídeo continua como está), com 8 abas: Visão geral, Quando postar, O que funciona, Curvas, Contas,
  Funil, Mercado e Alertas. A aba ativa e os filtros DEVEM ficar na URL (compartilhável e com voltar).
- **FR-002**: Um seletor global de período DEVE oferecer atalhos (24 h, 7 d, 14 d, 30 d, 90 d, tudo) e
  intervalo personalizado, abrindo por padrão nos últimos 7 dias (sem período na URL); toda comparação
  DEVE usar o período anterior de mesma duração.
- **FR-003**: Filtros globais por perfil, conta e rede DEVEM valer para todas as abas; filtros locais
  de um card valem só para ele.
- **FR-004**: Toda análise estatística DEVE respeitar uma amostra mínima configurada no código (padrão:
  5 posts por grupo para medianas e lift; 8 vídeos para correlação; 2 contas para o radar). Abaixo
  dela, a tela DEVE mostrar o dado bruto disponível e o aviso "amostra pequena (n = X de Y)", sem
  conclusão.
- **FR-004a**: Um seletor global "medida do post" DEVE oferecer views em 1 h, 24 h e 7 d (marcos da
  016, com "estimado" quando interpolado), padrão 24 h; ele vale para mapas por horário de publicação,
  insights, dispersões, lift, ranking de canais-fonte, comparações por modo/padrão e radar. Posts mais
  novos que o marco escolhido ficam fora dessas comparações e a tela mostra quantos estão "aguardando".
- **FR-005**: Todo gráfico DEVE ter: título, uma frase de leitura ("como ler"), tooltip com os valores,
  uma alternativa em tabela acessível, e exportação CSV dos dados daquele card.
- **FR-006**: As cores DEVEM seguir uma paleta validada para daltonismo (contraste e separação entre
  cores vizinhas) em tema claro e escuro, com sequencial de um só tom para magnitudes (mapas de calor),
  cores de entidade fixas (a mesma conta sempre com a mesma cor, mesmo quando um filtro muda o
  conjunto) e cores de status reservadas para alertas, sempre com ícone e texto.
- **FR-007**: Toda hora e dia DEVEM estar no fuso America/Sao_Paulo, com a nota de fuso visível nos
  mapas de calor.
- **FR-008**: A área DEVE funcionar no celular: cards em uma coluna, tabelas com as colunas principais
  (miniatura, título curto e views) sempre visíveis, títulos truncados (cerca de 40 caracteres, texto
  completo no tooltip).
- **FR-009**: O analytics é **só leitura**: nenhuma ação dele publica, aprova, agenda, conecta conta ou
  altera dado; atalhos levam às telas existentes, onde valem as regras de sempre (princípio I e avisos
  de direito da 006).
- **FR-010**: Membros e donos veem o analytics; custo de IA e exportação do dataset completo ficam só
  com o dono (como na 008 e na 016). O CSV de cada card fica disponível a quem vê o card.
- **FR-011**: A área DEVE carregar a biblioteca de gráficos só quando for aberta, sem aumentar o peso do
  restante do aplicativo, e funcionar com a política de segurança de conteúdo atual (sem script inline
  nem execução dinâmica de código).

**Visão geral (US1)**

- **FR-012**: 6 indicadores do período: views ganhas, curtidas ganhas, engajamento (curtidas +
  comentários + compartilhamentos sobre views, no período), seguidores ganhos, posts publicados e
  mediana da medida do post (padrão views em 24 h); cada um com valor anterior, variação % e seta.
- **FR-013**: Série diária de views ganhas por conta (uma cor por conta, legenda, "Outros" acima do
  limite).
- **FR-014**: Principais vídeos do período (top 10 por views ganhas), com miniatura, título curto,
  conta, views, engajamento e link para o detalhe do vídeo.
- **FR-015**: Cartões de insight gerados por regras determinísticas (sem chamar IA), cada um com frase,
  número de apoio, n e período; pelo menos: melhor faixa de horário, melhor dia da semana, faixa de
  duração com melhor mediana, canal-fonte com melhor mediana, hashtag com maior lift e vídeo acima de
  3× a mediana.

**Quando postar (US2)**

- **FR-016**: Mapa de calor 7 × 24 do desempenho por horário de publicação (mediana da medida do post, padrão 24 h;
  alternativa: média e contagem de posts), com o n em cada célula.
- **FR-017**: Mapa de calor 7 × 24 da audiência: views ganhas por hora, calculadas pela diferença entre
  fotos consecutivas e distribuídas igualmente pelas horas do intervalo quando ele tem até 3 h; ganhos
  de intervalos maiores ficam fora do mapa e aparecem como "sem hora atribuída"; ganhos negativos
  contam 0.
- **FR-018**: Calendário diário do período com posts publicados e views ganhas por dia.

**O que funciona (US3)**

- **FR-019**: Dispersões da medida do post (padrão views em 24 h) contra: duração do clipe, tamanho do gancho (caracteres) e
  score do SociShorts, cada uma com correlação de postos (−1 a 1) e leitura em palavras quando a
  amostra permite.
- **FR-020**: Ranking de canais-fonte de origem por mediana da medida do post dos posts derivados, com
  n, status de direito do canal e link para o canal.
- **FR-021**: Lift de hashtags (mediana com a hashtag ÷ mediana geral), usando as hashtags da postagem
  e as extraídas da legenda publicada, sem acento e sem caixa.
- **FR-022**: Comparação por modo de envio (lembrete × rascunho) e por padrão de corte, em mediana da
  medida do post e engajamento.

**Curvas (US4)**

- **FR-023**: Curvas de views por idade do vídeo (horas desde a publicação), sobrepostas com destaque de
  um vídeo e o resto em cinza, e em pequenos múltiplos por conta.
- **FR-024**: Meia-vida por vídeo (horas até alcançar 50% das views de 7 dias), só para vídeos com 7
  dias completos; distribuição da medida do post por conta (mínimo, quartis, máximo).

**Contas, perfis e redes (US5)**

- **FR-025**: Tabela comparativa por conta e por perfil com os indicadores da visão geral.
- **FR-026**: Radar de 6 eixos por conta contra a média simples das contas com dados no período
  (índice = valor ÷ média × 100, eixo limitado a 200 com marca de "acima"), com tabela eixo / conta /
  média / índice.
- **FR-027**: Drill-down: clicar numa conta ou perfil aplica o filtro global e mostra a trilha.

**Funil (US6)**

- **FR-028**: Funil do período: envios → cortes gerados → cortes aprovados → posts publicados → posts
  acima de um patamar de views em 24 h (padrão 100, ajustável na tela), com contagem e conversão por
  etapa, e diagrama de fluxo das perdas (ex.: sem clipes, arquivados, recusados).
- **FR-029**: Tempos medianos por etapa (processamento do envio, revisão até aprovação, aprovação até
  publicação) e, só para o dono, custo de IA total e por mil views.

**Mercado (US7)**

- **FR-030**: Mapa de calor 7 × 24 de quando os canais-fonte publicam e da velocidade média nas
  primeiras 24 h por horário de publicação.
- **FR-031**: Lista de oportunidades: vídeos-fonte com maior velocidade recente que ainda não têm envio,
  com canal, status de direito, idade, views e atalho para selecionar em "Gerar cortes" (passando pelo
  fluxo e pelos avisos normais).

**Alertas (US8)**

- **FR-032**: Alertas calculados na hora (não gravados): post estagnado (depois de 6 h, views abaixo
  de 10% da mediana da conta para a mesma idade; se a conta tem menos de 5 vídeos, até 1 view), vídeo
  acima de 3× a mediana da conta para a mesma idade (destaque positivo), conta sem coleta há mais de 3 h, e vínculo ambíguo pendente.
- **FR-033**: Cada alerta DEVE dizer o motivo, os números e o que conferir, e levar ao item.

### Key Entities

- **Período e comparação:** intervalo escolhido e o anterior de mesma duração; base de todas as
  variações.
- **Post analisado:** vídeo da rede (016) com publicação, duração e legenda, opcionalmente ligado ao
  destino, conteúdo, corte, envio e canal-fonte; carrega views/curtidas/comentários/compartilhamentos
  por idade (marcos) e ganhos por hora.
- **Indicador:** valor do período, valor anterior, variação e amostra.
- **Insight:** regra, frase, número de apoio, n, período (calculado, não gravado).
- **Alerta:** tipo, item, motivo, números, link (calculado, não gravado).
- **Oportunidade:** vídeo-fonte sem envio com velocidade recente, canal e status de direito.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com o filtro de 7 dias, o dono responde "qual foi o melhor horário de postagem e o melhor
  vídeo da semana" em menos de 30 segundos a partir da abertura da área.
- **SC-002**: Todos os números exibidos batem com o cálculo de referência sobre os dados semeados nos
  testes (100% dos indicadores, células dos mapas e etapas do funil).
- **SC-003**: Cada aba abre com os dados em até 2 segundos com o volume atual e com 10× o volume atual
  de vídeos e fotos.
- **SC-004**: Abrir qualquer outra tela do SociMan não fica mais pesado: a parte de gráficos só é
  baixada ao entrar no analytics.
- **SC-005**: 100% dos gráficos têm tabela alternativa, frase de leitura e CSV; a paleta passa na
  validação de daltonismo em claro e escuro.
- **SC-006**: No celular (largura de 390 px), nenhuma tela de analytics rola a página na horizontal e
  as views de cada vídeo ficam visíveis sem abrir detalhe.
- **SC-007**: Nenhuma conclusão (insight, correlação, lift, radar) aparece com amostra abaixo do mínimo.

## Assumptions

- **Fonte dos dados:** só o que já está no banco (016, 006, 008, 014). Não há coleta nova nesta spec;
  alcance, retenção, audiência e tráfego seguem na "etapa 2" (API comercial da TikTok).
- **Uma rede hoje:** as análises de desempenho cobrem a TikTok; "por rede" fica pronto para quando
  YouTube/Instagram próprios tiverem métricas, sem dado falso para elas.
- **Views da conta:** a TikTok não informa o total de views da conta; os totais são a soma das views dos
  vídeos da série (correção já feita fora desta spec, junto com o ranking compacto).
- **Insights determinísticos:** regras fixas em código, sem IA; custo zero e resultado reproduzível.
- **Biblioteca de gráficos:** decisão do dono de usar uma biblioteca de gráficos carregada sob demanda
  (registrada em ADR, revogando a decisão de "sem biblioteca" da 016); a escolha concreta fica no plano.
- **Tela atual:** o ranking da 016 vira um card da Visão geral; o detalhe por vídeo continua igual e é
  o destino dos cliques do analytics.
- **Entrega única:** as 8 abas saem juntas; as prioridades P1–P3 só ordenam a implementação.
- **Patamares padrão** (amostra mínima, estagnação, faixa do funil) ficam em constantes no código, com o
  valor visível na nota de leitura de cada card.
