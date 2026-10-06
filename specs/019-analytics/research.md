# Research: Analytics de decisão (019)

Decisões técnicas da 019. Cada item: **Decisão / Por quê / Alternativas**. Os números de volume são do
banco de dev em 2026-10-01.

## R1. Biblioteca de gráficos: Apache ECharts sob demanda

- **Decisão:** Apache ECharts **6.1.0** (Apache-2.0), importado de forma modular (`echarts/core`,
  `echarts/charts`, `echarts/components`, `echarts/renderers`; nunca `'echarts'`), num componente React
  próprio `Grafico` (~60 linhas: `init` no `useEffect`, `ResizeObserver` → `resize()`, `dispose()` no
  cleanup e idempotente no StrictMode, `setTheme` ao trocar claro/escuro com cores lidas das variáveis
  `--chart-*`). Configuração:
  - **renderer SVG**, para o e2e ter DOM;
  - locale **PT-br** registrado (`echarts/i18n/langPT-br-obj.js`);
  - `aria.enabled` ligado (textura `decal` desligada por padrão, opcional pela prop `textura` — ver ADR 0002), com descrição escrita por nós (a automática sai ruim, com
    "NaN" e só 10 itens);
  - `animation: false` quando `prefers-reduced-motion`.

  Carregamento por `React.lazy` só na rota de analytics.
  Charts registrados: Heatmap, Line, Bar, Scatter, Radar, Boxplot, Sankey e Funnel. Componentes: Grid,
  Tooltip, VisualMap, Calendar, Legend, Title, Dataset, MarkLine e Aria.
- **Por quê:**
  - Uma biblioteca cobre todos os tipos pedidos.
  - **CSP testada:** build servido com a política do edge e testado no Chromium (heatmap SVG, empilhado,
    calendar, sankey, aria/decal, `setTheme`, `showTip`), com 0 violações e 0 erros. O único
    `new Function` do pacote (fallback de GeoJSON) não entra no build modular.
  - O tooltip e os estilos inline são cobertos por `style-src 'unsafe-inline'` (ADR 0001), e os decals
    (`data:`) por `img-src data:`.
- **Números** (Vite 8 + rolldown, chunk lazy):

  | Variante | Minificado | gzip |
  |---|---|---|
  | modular + SVG | 698 kB | **234 kB** |
  | modular + Canvas | 691 kB | 231 kB |
  | pacote completo | 1.125 kB | 374 kB |

  A base Bar+Line+Grid+Tooltip sozinha dá 177 kB gz.
- **Cuidados obrigatórios** (viram tarefas e testes):
  1. **Escapar texto no tooltip:** o tooltip usa `innerHTML`, e os títulos e legendas vêm da rede. O
     `formatter` próprio passa tudo por `echarts.format.encodeHTML`.
  2. **PWA:** o `globPatterns` `**/*.js` poria o chunk no precache de todos. Ele sai do precache
     (`globIgnores` para o chunk de gráficos, nomeado por `manualChunks`) e entra num cache em runtime
     (`StaleWhileRevalidate`). Isso cumpre o SC-004 também na instalação do PWA.
  3. **Sem eval no dist:** o `check:bundle` ganha um teste que reprova `Function(` e `eval(` nos chunks.
  4. **Teclado:** o ECharts não tem navegação por teclado. O caminho acessível é a tabela alternativa,
     com botão "Ver tabela" focável, e o gráfico recebe `role="img"` e descrição.
- **Alternativas:**
  - **echarts-for-react 3.0.6:** não acrescenta nada além de resize e setOption, o React 19 entra só pelo
    range, e o registro do npm teve versões publicadas e retiradas em 2026-05-19.
  - **Pacote completo:** +140 kB gz e inclui o `Function()` do GeoJSON.
  - **Canvas:** 3 kB menor, mas sem DOM para teste.
  - **Recharts/visx:** sem calendar, boxplot e sankey nativos.
  - **SVG próprio** (R14 da 016): 7 tipos para manter.
- **Revoga:** R14 da 016 ("sem biblioteca") só para o analytics. O `LinhaChart` próprio continua no
  detalhe do vídeo.

## R2. Sem tabela nova: tudo calculado na leitura

- **Decisão:** a 019 não cria tabela, coluna nem migração. Cada aba é um endpoint GET que agrega em SQL
  (filtros, junções, `AT TIME ZONE`) e termina em Python (medianas, Spearman, regras de insight).
  Reaproveita a 016: `metricas.consulta.marcos` (marcos 1 h/24 h/7 d com interpolação e
  "estimado"), `consulta.views_conta`, `consulta._periodo`, `consulta.origem_sql`,
  `anonimizar.caracteristicas` (hora local, dia da semana, score, gancho, modo, canal, direito,
  intervalo desde o post anterior) e `ia.guia.normalizar` (sem acento e sem caixa).
- **Por quê:** os volumes são pequenos (22 vídeos, 301 fotos, 39 destinos, 397 cortes, 62 envios,
  42 mil vídeos-fonte) e o ranking da 016 já mede < 300 ms. Cache ou tabela agregada seria
  complexidade sem necessidade (princípio VIII). O SC-003 (2 s com 10× o volume) é verificado por
  teste de desempenho com dados semeados.
- **Alternativas:** visão materializada atualizada pela trilha `metricas` (rejeitada agora: mais uma
  peça para manter; fica como plano B se o teste de 10× passar de 2 s); cache no Redis por filtro
  (rejeitado: Redis não é banco de registro e o ganho é pequeno).

## R3. Medida do post (1 h, 24 h, 7 d)

- **Decisão:** a medida vem de `marcos()` da 016, com o marco pedido (`h1`, `h24`, `d7`). Vídeos cuja
  idade ainda não alcançou o marco ficam fora das comparações e entram no contador "aguardando". Marco
  estimado (interpolado com folga > 25%) entra na conta e é marcado no tooltip e na tabela.
- **Por quê:** comparação justa entre vídeos de idades diferentes (Clarification 5). O seletor fica no
  cabeçalho e vale para todas as abas que comparam posts.
- **Alternativas:** views totais (favorece os antigos); média em vez de mediana (sensível a um viral).

## R4. Mapa de calor da audiência (views por hora)

- **Decisão:** para cada par de fotos consecutivas de um vídeo, ganho = max(0, views₂ − views₁). Se o
  intervalo tem até 3 h, o ganho é dividido igualmente pelas horas-relógio cobertas (proporcional aos
  minutos de cada hora) no fuso America/Sao_Paulo; acima de 3 h, o ganho vai para o total "sem hora
  atribuída". Feito em SQL com `lag()` sobre `metricas_video_fotos` ordenado por `coletado_em`
  e `generate_series` das horas do intervalo.
- **Primeiro intervalo:** da publicação (0 view, como nos marcos da 016) até a primeira foto, com a
  mesma regra de até 3 h. É o que mostra as primeiras horas de cada vídeo no mapa.
- **Por quê:** a agenda da 016 fotografa de hora em hora só até 48 h de idade; depois, diariamente.
  Espalhar 24 h de ganho por 24 células apagaria o sinal (spec ajustada em FR-017).
- **Alternativas:** distribuir tudo (rejeitado: achata o mapa); só intervalos de exatamente 1 h
  (rejeitado: perde as fotos atrasadas da trilha).

## R5. Estatística

- **Decisão:** mediana e quartis com `statistics` (método "inclusive"); correlação de Spearman (postos
  com empates pela média) implementada em ~15 linhas em `analytics/estatistica.py`, sem numpy/scipy.
  Leitura em palavras: |ρ| < 0,3 fraca, < 0,6 moderada, ≥ 0,6 forte, com sinal. Lift = mediana do
  grupo ÷ mediana geral (geral ≠ 0; se 0, "sem base"). Amostras mínimas em constantes:
  `MIN_GRUPO = 5`, `MIN_CORRELACAO = 8`, `MIN_CONTAS_RADAR = 2`, `MIN_CONTA_ESTAGNADO = 5`.
- **Por quê:** Spearman é robusto a outliers (um viral) e não supõe linearidade; nenhuma dependência
  nova no backend.
- **Alternativas:** Pearson (sensível a viral); scipy (dependência pesada para uma fórmula).

## R6. Insights determinísticos

- **Decisão:** `analytics/insights.py` com uma lista de regras puras: cada regra recebe os posts já
  medidos e devolve `Insight | Pendente`. Regras iniciais: melhor faixa de 3 h de publicação, melhor
  dia da semana, faixa de duração (≤ 30 s, 31–60 s, > 60 s), canal-fonte, hashtag com maior lift e
  vídeos acima de 3× a mediana. Só vira insight se o grupo vencedor e o geral tiverem `MIN_GRUPO` e a
  razão for ≥ 1,3×; senão, `Pendente` com "faltam N posts".
- **Por quê:** reprodutível, testável e sem custo de IA (spec, Assumptions).
- **Alternativas:** texto gerado pela IA (custo, não determinístico; pode vir numa spec futura usando
  os mesmos números).

## R7. Funil

- **Decisão:** etapas no período (pelo `created_at` de cada elemento, filtradas por perfil):
  1. envios enviados (`sent_at` no período, status ≠ `selecionado`/`descartado` antes do envio);
  2. cortes gerados (cortes com `envio_id` desses envios);
  3. aprovados = conteúdos desses cortes com ao menos um destino com `aprovado_em` (decisão humana);
  4. publicados = destinos em `postado`/`publicado`;
  5. acima do patamar = vídeos vinculados com a medida do post ≥ patamar (padrão 100).
  Perdas mostradas no fluxo: envio `sem_clipes`/`falhou`, corte `falhou` ou arquivado, corte parado em
  `revisao`, destino recusado/arquivado/`falhou`. Tempos medianos: `envios.finished_at − started_at`,
  `cortes.created_at → destino.aprovado_em`, `aprovado_em → posted_at`.
- **Por quê:** o corte não tem estado "aprovado"; o sinal humano real é o destino aprovado (014). O
  "Aplicar marca" pode ser automático (`marca_automatica`), então não serve como aprovação.
- **Custo de IA:** soma de `ia_chamadas.custo_usd` dos conteúdos do período; custo por mil views =
  soma ÷ views dos vídeos vinculados × 1000. Só aparece para dono (o servidor nem calcula para membro).

## R8. Mercado (YouTube de origem)

- **Decisão:** usa `videos_fonte` (42 mil) e não a série `video_metricas` (rasa: ~1,2 observação por
  vídeo desde 29/09). Mapa de publicação: contagem por dia × hora de `published_at`. Velocidade por
  horário: mediana de `views ÷ idade_h` para vídeos com idade entre 24 h e 7 d. Oportunidades: vídeos
  com `vph_recente` (1.063 preenchidos) ou, sem ele, `views ÷ idade_h` nas últimas 72 h, sem envio ativo
  (`ix_envios_perfil_video_ativo`), não `live`, `disponivel`, ordenados por velocidade; top 25.
- **Atalho:** leva a "Gerar cortes" com o vídeo pré-selecionado; o fluxo e o aviso de direito da 006
  continuam iguais (princípio II, FR-031).

## R9. Alertas

- **Decisão:** calculados na leitura, nunca gravados (FR-032):
  - **estagnado:** idade ≥ 6 h e views < 10% da mediana da conta para a mesma idade (mediana dos
    outros vídeos da conta interpolada na idade do vídeo); se a conta tem < 5 vídeos, views ≤ 1;
  - **destaque:** views > 3× essa mediana;
  - **sem coleta:** `metricas_series.ultima_coleta_em` há mais de 3 h (série ativa);
  - **vínculo a confirmar:** `metricas.vinculos.vinculo()` com `estado = "a_confirmar"`.
- **Referência na implementação:** a mediana vem dos outros vídeos da mesma série na mesma idade
  (interpolada). A regra fixa (até 1 view) vale quando menos de 5 vídeos de referência chegaram
  àquela idade. É mais rigoroso que "conta com menos de 5 vídeos" e evita alerta por mediana de 2.
- **Por quê:** "estagnado" relativo à conta (Clarification 4) acompanha o crescimento.

## R10. CSV por card no cliente

- **Decisão:** o CSV de cada card é gerado no navegador a partir da mesma tabela alternativa do
  gráfico (UTF-8 com BOM, separador `,` e aspas, igual ao `_Escritor` da 016), baixado por um
  `Blob` + link temporário. O payload de membro não contém custo de IA, então o CSV não vaza nada.
- **Por quê:** um único caminho de dados (o que se vê é o que se baixa) e zero rota a mais. Com a CSP
  atual, download de `blob:` por âncora não exige mudança de política.
- **Injeção de fórmula:** títulos e legendas vêm da rede, e o dono abre o CSV em planilha. Toda célula
  de texto que começa com `=`, `+`, `-`, `@`, tab ou CR sai com um apóstrofo na frente, no `csv.ts` e
  no `_csv` da exportação da 016 (`metricas/export.py`); números, mesmo negativos, continuam números
  e o JSON Lines não muda. Exceção: o handle simples (`^@[A-Za-z0-9._]+$`, ex.: `@atavernanerd`) sai
  limpo, porque não forma fórmula; qualquer outro texto com `@` (`@SUM(A1)`, `@x y`) leva o apóstrofo.
- **Alternativas:** `?format=csv` no servidor, como na autodoc (dobra as rotas e os testes).

## R11. Paleta validada

- **Decisão:** paleta categórica de 8 posições da skill dataviz, em ordem fixa, com valores próprios
  para claro e escuro, e sequencial azul (100→700) para mapas de calor. Validada com
  `validate_palette.js` contra os fundos reais dos cards (`--card`: `#ffffff` claro e `#1a2334`
  escuro):
  - claro: todas as checagens passam; contraste < 3:1 em 3 cores (`#1baf7a`, `#eda100`, `#e87ba4`) →
    alívio obrigatório: rótulos diretos e tabela (já exigidos por FR-005);
  - escuro: todas passam, inclusive contraste ≥ 3:1;
  - dispersões (todos os pares): máximo 3 séries por gráfico, o resto vira "Outros" ou pequenos
    múltiplos.
  Cores de status (alertas) são separadas e sempre com ícone e texto. Tokens `--chart-1..8` e
  `--chart-seq-*` entram no `index.css` (claro em `:root`, escuro em `.dark`), e o tema do ECharts é
  montado lendo essas variáveis.
- **Por quê:** FR-006 e SC-005; cor fixa por entidade (a conta não muda de cor quando o filtro muda).

## R12. Rotas, permissões e guardas

- **Decisão:** pacote `analytics/` com router `/api/analytics/*`, só GET, `operationId`
  `analytics_*`, `RequireUser`. Campos de custo só para `role == dono` (o membro recebe `null`, e a
  SPA esconde). Guardas novos em `test_constitution_guards.py`: (1) todas as rotas `/api/analytics`
  são GET; (2) `analytics/` não importa `publicacao`, `httpx` nem serviços que mudam estado
  (`postagem.service`, `envios.service_envios`, `cortes.service`); (3) nomes neutros (o guarda
  existente cobre "tiktok"/"youtube"; a aba "Mercado" usa `mercado`).
- **Por quê:** princípio I (só leitura) e FR-009/FR-010.

## R13. Desempenho

- **Decisão:** teste de desempenho no pytest com 10× o volume atual de métricas (220 vídeos, 3.000
  fotos, 400 destinos, 4.000 cortes) e 50 mil vídeos-fonte, com limite de 2 s por aba. O Mercado usa
  os índices existentes (`ix_videos_fonte_canal_published`, `ix_videos_fonte_recomendavel_score`).
  Se alguma aba passar do limite, aplica-se o plano B do R2 só a ela.
