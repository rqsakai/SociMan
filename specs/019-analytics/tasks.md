---

description: "Tarefas da feature 019-analytics"
---

# Tasks: Analytics de decisão (019-analytics)

**Input**: `specs/019-analytics/` (spec com Clarifications 1–5, plan, research R1–R13, data-model,
contracts/http-api.md, quickstart)

**Pré-requisito:** a correção pontual de métricas (views da conta, ranking por views total, linhas
compactas com miniatura), feita fora desta spec pelo agente `fix-views`, precisa estar concluída e
verde, porque a 019 mexe nos mesmos arquivos (`metricas/consulta.py`, `metricas/router.py`,
`RankingTable.tsx`, `ContaMetricas.tsx`, `Metricas.tsx`).

**Decisões do dono (2026-10-01):**
- **Q1:** "Métricas" abre o analytics; o ranking vira card da Visão geral; o detalhe do vídeo continua.
- **Q2:** as 8 abas saem numa entrega só.
- **Q3:** período padrão de 7 dias, comparando com os 7 anteriores.
- **Q4:** estagnado = abaixo de 10% da mediana da conta para a mesma idade depois de 6 h (com menos de 5
  vídeos na conta, até 1 view).
- **Q5:** seletor de medida 1 h / 24 h / 7 d, padrão 24 h.
- ECharts carregado sob demanda e emenda 4.1.0 da constitution + ADR 0002 aprovados.

**Nomes canônicos:**
- **API:** pacote `sociman_api/analytics/` (`filtros`, `base`, `estatistica`, `insights`, `visao_geral`,
  `quando_postar`, `o_que_funciona`, `curvas`, `contas`, `funil`, `mercado`, `alertas`, `schemas`,
  `router`). Rotas `GET /api/analytics/{visao-geral,quando-postar,o-que-funciona,curvas,contas,funil,mercado,alertas}`,
  `operationId` `analytics_*`.
- **SPA:** `pages/analytics/Analytics.tsx` (lazy em `/app/metricas`) e `pages/analytics/abas/*.tsx`.
- **Componentes** em `components/analytics/`: `Grafico`, `echarts`, `tema`, `CardAnalytics`,
  `TabelaAlternativa`, `Indicador`, `Amostra`, `FiltrosGlobais`, `csv`.
- **Hooks:** `lib/analytics.ts`.
- **Cores:** tokens `--chart-1..8` e `--chart-seq-100..700`.
- **e2e:** `e2e/analytics.spec.ts`.
- **Docs:** `docs/adr/0002-graficos-echarts.md`.

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera (`npm run test:api [-- args]`), com **cálculo de referência** sobre dados
  semeados para cada aba (SC-002);
- `docker compose exec -T api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e sempre com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/analytics.spec.ts]`.

Nada chama serviço real.

**Arquivos compartilhados, SÓ ACRÉSCIMO:** `apps/api/src/sociman_api/main.py`, `apps/web/src/App.tsx`,
`apps/web/src/index.css`, `apps/web/vite.config.ts` (bloco PWA), `scripts/check-bundle.mjs`,
`apps/api/tests/unit/test_constitution_guards.py`, `e2e/helpers.ts`, `CLAUDE.md`, `docs/visao.md`.
`packages/contract/**` é gerado.

**Segredos:** nenhuma consulta imprime tokens, links de upload ou `rede_video_id`; só contagens e
agregados.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US8 da spec

---

## Phase 1: Setup

- [X] T001 **Gate:** confirmar que a correção pontual de métricas terminou, com pytest de métricas,
  `check:web` e `e2e/metricas.spec.ts` verdes, e que o `git status` só tem o que é esperado. Confirmar
  também que `.specify/feature.json` aponta para `specs/019-analytics`.
- [X] T002 **Emenda da constitution 4.0.0 → 4.1.0 (MINOR)** em `.specify/memory/constitution.md`, aprovada
  pelo dono em 2026-10-01. Na seção "Restrições técnicas", acrescentar:
  "Gráficos do SPA: **Apache ECharts** (modular, `echarts/core`), só em rotas carregadas sob demanda;
  nenhuma outra biblioteca de gráficos". Atualizar a linha de versão e a data de emenda. Incluir o Sync
  Impact Report como comentário, para ser removido antes do commit.
- [X] T003 [P] `docs/adr/0002-graficos-echarts.md` (Contexto / Decisão / Consequências / Status: Aceita)
  com R1:
  - 6.1.0, modular, SVG, lazy, fora do precache;
  - CSP testada sem violações;
  - tooltip escapado;
  - revoga a R14 da 016 só para o analytics.

  Adicionar a linha no `docs/adr/README.md`.
- [X] T004 `apps/web`: `npm install echarts@6.1.0 --save-exact` (sem `echarts-for-react`). Conferir que
  o `package-lock.json` mudou só por ele e por `zrender`.
- [X] T005 [P] `apps/web/src/index.css` (acréscimo): tokens `--chart-1..8` com os hex de R11.
  - **Claro** em `:root`: `#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4 #008300 #4a3aa7 #e34948`.
  - **Escuro** em `.dark`: `#3987e5 #d95926 #199e70 #c98500 #d55181 #008300 #9085e9 #e66767`.
  - **Sequencial** `--chart-seq-100..700` (azul da skill dataviz).
  - Registrar em `@theme` como `--color-chart-*`.

---

## Phase 2: Foundational (bloqueia todas as histórias)

### API

- [X] T006 [P] `apps/api/src/sociman_api/analytics/estatistica.py`:
  - `mediana`, `quartis` (min/q1/med/q3/max, `statistics` "inclusive");
  - `spearman(xs, ys) -> float | None` (postos com empates pela média);
  - `leitura_correlacao(rho)` (|ρ| < 0,3 fraca; < 0,6 moderada; ≥ 0,6 forte, com sinal);
  - `lift(grupo, geral)` (None se geral = 0);
  - `Amostra(n, minimo)` com `suficiente`/`faltam`;
  - constantes `MIN_GRUPO = 5`, `MIN_CORRELACAO = 8`, `MIN_CONTAS_RADAR = 2`, `MIN_CONTA_ESTAGNADO = 5`.

  Testes em `tests/unit/test_analytics_estatistica.py`: valores conhecidos, empates, listas vazias,
  ρ de ±1 e de 0.
- [X] T007 `analytics/filtros.py`: `Filtro`, que lê os parâmetros comuns do contrato.
  - **Período:**
    - padrão hoje − 6 … hoje no `app_tz`;
    - `validar_periodo` da 016 (≤ 400 dias, 400 `periodo_invalido`);
    - intervalo `[de 00:00, ate+1 00:00)` via `metricas.consulta._periodo`;
    - período anterior de mesma duração.
  - **Filtros de escopo:**
    - `contaId` precisa pertencer ao `perfilId`, senão 400 `conta_fora_do_perfil`;
    - `perfilId` inexistente → 404;
    - `medida` ∈ {h1, h24, d7}, padrão h24;
    - `rede` opcional.

  Testes unitários de bordas: virada de dia em SP, período de 1 dia e período inválido.
- [X] T008 `analytics/base.py`: `posts(db, filtro, *, periodo) -> list[PostAnalisado]` (data-model),
  com SQL dos `metricas_videos` publicados no período e filtrados por série, conta, perfil e rede.
  - Reusa:
    - `metricas.consulta.marcos` para a medida, com `estimado` e "aguardando";
    - `metricas.anonimizar.caracteristicas` para hora local, dia, score, gancho, modo, canal e direito;
    - `ia.guia.normalizar` + `#(\w+)` para hashtags do destino ∪ legenda.
  - Cada post leva `titulo_curto` (40), link, `thumb_url` (a mesma da correção do ranking) e `padrao`
    vindo de `envios.config`.
  - Também `ganhos(db, filtro, periodo)`: Δviews/Δlikes/Δcomments/Δshares por vídeo, com a última foto
    ≤ fim menos a última ≤ início (0 se negativo).
- [X] T009 [P] `apps/api/tests/integration/analytics_helpers.py`: fixtures que reusam
  `metricas_helpers.semear` e acrescentam:
  - `vincular(video, corte=…, canal=…, modo=…, hashtags=…, aprovado_em=…, posted_at=…)`, que cria
    perfil → conta → envio → corte → conteúdo → destino e liga o vídeo;
  - `segunda_conta()`;
  - `custo_ia(conteudo, usd)`;
  - `videos_fonte(n, …)`.

  Datas sempre relativas a "agora" no fuso de SP.
- [X] T010 `analytics/schemas.py`: modelos Pydantic com aliases camelCase para `Contexto`, `Amostra`,
  `Indicador`, `Insight`, `CelulaMapa`, `PontoDispersao`, `LinhaRanking`, `Curva`, `RadarConta`,
  `EtapaFunil`, `Oportunidade` e `Alerta`, e uma resposta por aba (contracts/http-api.md).
  Monetários em `Decimal` com 4 casas.
- [X] T011 `analytics/router.py`: `APIRouter(prefix="/api/analytics")`, só `@router.get`,
  `RequireUser`, `DbSession`, `ErrorEnvelope`. Registrar em `main.py` (acréscimo). Função `eh_dono(actor)`
  para os campos de custo.
- [X] T012 **Guardas** em `tests/unit/test_constitution_guards.py` (seção "spec 019", acréscimo):
  1. em `app.openapi()`, todo path `/api/analytics` só tem `get`;
  2. todo operationId de analytics começa com `analytics_`;
  3. a AST de `analytics/*.py` não importa `publicacao`, `httpx`, `postagem.service`,
     `envios.service_envios`, `cortes.service` nem `history`, e não chama `.add(`, `.flush(`,
     `.commit(`, `.delete(` nem `.execute(update/insert/delete…)`.

  O guarda existente de nomes neutros continua cobrindo "tiktok" e "youtube".

### SPA

- [X] T013 [P] `components/analytics/echarts.ts`: `echarts.use([...])` com HeatmapChart, LineChart,
  BarChart, ScatterChart, RadarChart, BoxplotChart, SankeyChart, FunnelChart, GridComponent,
  TooltipComponent, VisualMapComponent, CalendarComponent, LegendComponent, TitleComponent,
  DatasetComponent, MarkLineComponent, AriaComponent e SVGRenderer.
  - Registro do locale `PT-br` (`echarts/i18n/langPT-br-obj.js`).
  - Tipo `OpcoesGrafico = ComposeOption<…>`.
  - Import **só** de `echarts/core|charts|components|renderers`.
- [X] T014 [P] `components/analytics/tema.ts`: monta o tema do ECharts lendo `--chart-*`, `--foreground`,
  `--muted-foreground`, `--border` e `--card` via `getComputedStyle`. Grade, eixos e textos ficam
  recessivos, com linhas de 2 px e marcadores ≥ 8 px. `useTemaGraficos()` observa a classe `dark` no
  `<html>` (MutationObserver) e devolve o objeto do tema.
- [X] T015 `components/analytics/Grafico.tsx`:
  - **Ciclo de vida:**
    - `init(el, tema, {renderer: 'svg', locale: 'PT-br'})` no `useEffect`;
    - `setOption`;
    - `ResizeObserver` → `resize()`;
    - `dispose()` no cleanup, idempotente no StrictMode;
    - `setTheme` quando o tema muda.
  - **Acessibilidade e movimento:**
    - `aria: {enabled: true, decal: {show: true}, label: {description}}`, com descrição recebida por prop;
    - `role="img"` + `aria-label`;
    - `animation: false` com `prefers-reduced-motion`.
  - **Tooltip:** `formatter` padrão que passa **todo texto** por `echarts.format.encodeHTML` (R1,
    cuidado 1).
  - Props: `opcoes`, `descricao`, `altura`, `onClickItem`.
- [X] T016 [P] `components/analytics/csv.ts`: `baixarCsv(nome, colunas, linhas)`, com UTF-8 + BOM,
  separador `,`, aspas duplas escapadas e `\r\n`, igual ao `_Escritor` da 016. Faz `Blob` + `<a download>`
  temporário e revoga a URL. Teste com Vitest se houver; senão, coberto pelo e2e.
- [X] T017 `components/analytics/CardAnalytics.tsx`:
  - cabeçalho com título, chip de `Amostra` ("amostra pequena (n = X de Y)") e botões
    "Ver tabela"/"Ver gráfico" e "CSV";
  - "Como ler" (texto curto) e estado vazio com motivo e atalho "Ampliar período";
  - `TabelaAlternativa.tsx` (tabela semântica com cabeçalhos; a mesma fonte do CSV).

  Mais `Indicador.tsx` (valor, anterior, ▲/▼, "sem base de comparação") e `Amostra.tsx`.
- [X] T018 `lib/analytics.ts`: hooks TanStack Query `useAnalytics(aba, filtro)` com o cliente gerado e
  chaves `['analytics', aba, filtro]`; `useFiltroAnalytics()` sobre `useSearchParams` (padrões somem da
  URL: `aba=visao-geral`, últimos 7 dias, `medida=h24`); formatadores reusados de `lib/metricas.ts`.
- [X] T019 `components/analytics/FiltrosGlobais.tsx`: período com atalhos (24 h, 7 d, 14 d, 30 d, 90 d,
  tudo, personalizado), perfil, conta, rede e "Medida do post" (1 h / 24 h / 7 d), numa linha acima das
  abas e quebrando em coluna no celular. Mais a trilha "Contas → @conta" quando há conta filtrada.
- [X] T020 `pages/analytics/Analytics.tsx` + rota: `/app/metricas` passa a ser
  `lazy(() => import('./pages/analytics/Analytics'))` com `Suspense` em `App.tsx`, no modelo do
  Showcase. Abas com o `Tabs` do shadcn e `?aba=` com os 8 valores. A antiga `pages/metricas/Metricas.tsx` é removida, e **nada da 016 se perde** (FR-001):
  o ranking vai para a Visão geral (T026); `ColetaStatus` e `ExportarDialog` (só dono) ficam no
  cabeçalho do analytics; `ContaMetricas` (série da conta) vai para a aba Contas (T042). `/app/metricas/videos/:id` não muda.
- [X] T021 `apps/web/vite.config.ts` (bloco PWA e build, acréscimo):
  - `manualChunks` dá nome fixo ao chunk do ECharts (`graficos`);
  - `workbox.globIgnores` o tira do precache;
  - `runtimeCaching` `StaleWhileRevalidate` para `/assets/graficos-*.js` (R1, cuidado 2).

  `scripts/check-bundle.mjs` (acréscimo): reprova `Function(` e `eval(` em qualquer chunk de `dist`
  (cuidado 3).
- [X] T022 `npm run gen:contract && npm run check:web` (rotas vazias já tipadas). Smoke e2e mínimo em
  `e2e/analytics.spec.ts`: abrir `/app/metricas`, ver as 8 abas e trocar a aba pela URL.

**Checkpoint:** base pronta: filtros na URL, card com tabela/CSV/amostra, gráfico que troca de tema e
guardas verdes.

---

## Phase 3: US1 — Visão geral (P1)

- [X] T023 [P] [US1] Testes `tests/integration/test_analytics_visao_geral.py`, com cálculo de
  referência sobre a semeadura:
  - os 6 indicadores (views e likes ganhos, engajamento, seguidores, posts, mediana da medida) com o
    anterior e a variação;
  - "sem base de comparação";
  - a série diária por conta em SP;
  - top 10 por views ganhas;
  - anônima rotulada "Conta anônima N";
  - medida h1/h24/d7 com "aguardando".
- [X] T024 [P] [US1] Testes `tests/unit/test_analytics_insights.py`: cada regra (faixa de 3 h, dia,
  duração ≤ 30/31–60/> 60 s, canal, hashtag, destaque > 3×) com o vencedor ≥ 1,3× e
  `MIN_GRUPO`. Abaixo do mínimo, `pendente` com "faltam N posts".
- [X] T025 [US1] `analytics/visao_geral.py` e `analytics/insights.py` (regras puras sobre
  `PostAnalisado`). O ranking compacto da 016 (1ª página, já corrigido) entra no payload. Rota
  `analytics_visao_geral`.
- [X] T026 [US1] SPA `pages/analytics/abas/VisaoGeral.tsx`:
  - KPIs (6 `Indicador`, 2–3 por linha no celular);
  - linha das views diárias por conta, com cor fixa por conta pela ordem estável de `contaId` e
    "Outros" acima de 8;
  - cards de insight, principais vídeos e ranking compacto (miniatura, título de 40 caracteres, views
    sempre visíveis), com clique → `/app/metricas/videos/:id`.
- [X] T027 [US1] e2e em `e2e/analytics.spec.ts`:
  - indicadores semeados por `sqlE2e` batem com a tela;
  - período 30 d na URL e "voltar" restaura;
  - período vazio mostra o estado vazio.

---

## Phase 4: US2 — Quando postar (P1)

- [X] T028 [P] [US2] Testes `test_analytics_quando_postar.py`:
  - mapa por publicação (mediana e n por célula; terça 19 h = 300; 23:30 de domingo em SP conta no
    domingo);
  - audiência: 100 → 160 entre 10 h e 11 h dá 60 na célula; intervalo de 2 h30 é dividido proporcional
    aos minutos; intervalo de 24 h vai para `semHora`; queda conta 0;
  - calendário por dia.
- [X] T029 [US2] `analytics/quando_postar.py`: SQL com `lag()` sobre `metricas_video_fotos` por vídeo e
  `generate_series` das horas do intervalo (≤ 3 h), tudo `AT TIME ZONE` do `app_tz` (R4). Rota
  `analytics_quando_postar`.
- [X] T030 [US2] SPA `abas/QuandoPostar.tsx`:
  - dois heatmaps 7 × 24 (sequencial `--chart-seq-*`, células com n < 5 marcadas e tooltip com n), com
    rolagem horizontal **dentro** do card no celular e a nota "horário de Brasília";
  - calendário (CalendarComponent) com posts e views;
  - total "sem hora atribuída" na nota de leitura.
- [X] T031 [US2] e2e: célula semeada com o valor e o n certos na tabela alternativa; a medida 1 h muda
  os valores e o contador "aguardando".

---

## Phase 5: US3 — O que funciona (P1)

- [X] T032 [P] [US3] Testes `test_analytics_o_que_funciona.py`:
  - dispersões duração/gancho/score com ρ de referência; abaixo de 8, sem ρ;
  - ranking de canais com direito;
  - lift de hashtags com normalização ("#Marvel" = "#marvel", acento) e n ≥ 5;
  - modos lembrete × rascunho e padrões vindos de `envios.config`;
  - `excluidosSemVinculo`.
- [X] T033 [US3] `analytics/o_que_funciona.py` + rota `analytics_o_que_funciona`.
- [X] T034 [US3] SPA `abas/OQueFunciona.tsx`:
  - 3 dispersões, com até 3 séries por gráfico (o resto em "Outros"), tooltip escapado e clique → detalhe
    do vídeo;
  - frase da correlação;
  - barras horizontais de canais (com selo de direito e link para o canal, FR-020) e de hashtags (lift, linha em 1,0×);
  - comparação de modos e padrões.
- [X] T035 [US3] e2e: clicar num ponto abre o detalhe; uma hashtag com n < 5 não aparece no lift.

---

## Phase 6: US4 — Curvas (P2)

- [X] T036 [P] [US4] Testes `test_analytics_curvas.py`: pontos (idade_h, views) por vídeo, meia-vida
  (interpolada entre fotos; vídeo < 7 d → null) e quartis por conta.
- [X] T037 [US4] `analytics/curvas.py` (no máximo 50 vídeos mais recentes) + rota `analytics_curvas`.
- [X] T038 [US4] SPA `abas/Curvas.tsx`:
  - linhas sobrepostas, com o vídeo escolhido em destaque e o resto em cinza;
  - pequenos múltiplos por conta (grade responsiva);
  - boxplot por conta;
  - "ainda não calculável" na tabela.
- [X] T039 [US4] e2e: destacar um vídeo pela lista muda a série em destaque (verificado na tabela
  alternativa e no `aria-label`).

---

## Phase 7: US5 — Contas, perfis e redes (P2)

- [X] T040 [P] [US5] Testes `test_analytics_contas.py`:
  - tabela por conta e por perfil;
  - radar com 2 contas (índice = valor ÷ média × 100, corte em 200 com `acima`);
  - com 1 conta, `radar = null` e o motivo;
  - anônimas fora do radar.
- [X] T041 [US5] `analytics/contas.py` + rota `analytics_contas`.
- [X] T042 [US5] SPA `abas/Contas.tsx`: série da conta (`ContaMetricas` da 016: views, seguidores e
  curtidas) quando há conta filtrada, tabela comparativa, radar com a linha da média = 100 tracejada e
  a tabela eixo / conta / média / índice, e clique na conta → filtro global + trilha.
- [X] T043 [US5] e2e: com uma segunda conta semeada, o radar aparece; clicar aplica `?conta=` e mostra a
  trilha.

---

## Phase 8: US6 — Funil (P2)

- [X] T044 [P] [US6] Testes `test_analytics_funil.py`:
  - etapas enviados → cortes → aprovados (destino com `aprovado_em`) → publicados → acima do patamar
    (padrão 100; `patamar=50` muda);
  - perdas: `sem_clipes`, `falhou`, corte arquivado, parado em revisão, destino recusado ou arquivado;
  - tempos medianos;
  - custo de IA e custo por mil views só para dono (membro → `null`).
- [X] T045 [US6] `analytics/funil.py` + rota `analytics_funil` (o parâmetro `patamar` ≥ 1).
- [X] T046 [US6] SPA `abas/Funil.tsx`: funil com contagem e %, sankey das perdas, cards de tempos e
  custo (só dono, via `useEhDono`), e controle do patamar.
- [X] T047 [US6] e2e: o membro não vê custo, e a resposta tem `custoIaUsd: null`.

---

## Phase 9: US7 — Mercado (P3)

- [X] T048 [P] [US7] Testes `test_analytics_mercado.py`:
  - mapa de publicação dos canais-fonte em SP;
  - velocidade por horário (mediana de views ÷ idade_h, para 24 h–7 d);
  - oportunidades: com `vph_recente` ou com views ÷ idade nas 72 h; sem envio ativo, não `live`,
    `disponivel`; top 25; com direito.
- [X] T049 [US7] `analytics/mercado.py` + rota `analytics_mercado`.
- [X] T050 [US7] SPA `abas/Mercado.tsx`: 2 heatmaps, lista de oportunidades com selo de direito e
  "Gerar cortes" levando à seleção existente (a mesma rota e o mesmo fluxo da 006, com o vídeo
  pré-selecionado).
- [X] T051 [US7] e2e: "Gerar cortes" de um canal `sem_acordo` passa pelo aviso de direito como sempre.

---

## Phase 10: US8 — Alertas (P3)

- [X] T052 [P] [US8] Testes `test_analytics_alertas.py`:
  - estagnado: relativo (< 10% da mediana da conta na mesma idade, ≥ 6 h), e fixo (≤ 1 view) quando a
    conta tem < 5 vídeos;
  - destaque > 3×;
  - sem coleta > 3 h;
  - vínculo a confirmar via `metricas.vinculos.vinculo`;
  - o alerta some quando a condição deixa de valer;
  - nada é gravado (contagem das tabelas antes = depois).
- [X] T053 [US8] `analytics/alertas.py` + rota `analytics_alertas`.
- [X] T054 [US8] SPA `abas/Alertas.tsx`: lista por severidade, com ícone + texto (cores de status
  reservadas), motivo, números, o que conferir e link. Contador na aba ("Alertas (3)").
- [X] T055 [US8] e2e: o vídeo semeado com 0 view depois de 6 h aparece como estagnado, e some ao semear
  uma foto com views.

---

## Phase 11: Polish e verificação final

- [X] T056 [P] `tests/integration/test_analytics_desempenho.py` (R13): 10× o volume (220 vídeos, 3.000
  fotos, 400 destinos, 4.000 cortes, 50 mil vídeos-fonte) e cada rota < 2 s. Se alguma passar do
  limite, aplicar o plano B do R2 só a ela e registrar no research.
- [X] T057 [P] e2e transversais em `e2e/analytics.spec.ts`:
  - 390 px sem rolagem horizontal da página (`scrollWidth ≤ clientWidth`), e views visíveis nas tabelas;
  - troca de tema muda as cores sem recarregar;
  - "CSV" baixa o mesmo conteúdo da tabela (cabeçalho e 1ª linha);
  - "Ver tabela" acessível por teclado;
  - só `GET /api/analytics/*` (interceptar e reprovar POST/PATCH/PUT/DELETE);
  - nenhum erro de CSP no console.
- [X] T058 [P] Ajustar `e2e/metricas.spec.ts` ao novo layout (ranking dentro da Visão geral; detalhe do
  vídeo igual).
- [X] T059 Checar o carregamento sob demanda (SC-004) com `npm run test:e2e:pwa` ou build + preview: o
  chunk `graficos` não está no precache e não é baixado em `/app/conteudos`.
- [X] T060 `CLAUDE.md` (acréscimo): seção "Analytics (desde a spec 019)" com o pacote, as rotas, o
  ECharts modular/SVG/lazy, o tooltip escapado, os tokens `--chart-*`, as amostras mínimas e "só
  leitura". `docs/visao.md`: item 019 no backlog.
- [X] T061 Verificação final completa: `npm run test:api` inteiro, ruff, `npm run gen:contract && npm run
  check:web`, a suíte e2e inteira 2× (com trava) e `npm run test:e2e:pwa`. Remover o Sync Impact Report da
  constitution. Percorrer o quickstart §2–§8 no dev com dados reais e registrar o resultado. **Commit só
  quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1** (T001 gate → T002–T005). T004 antes de T013. T002 e T003 antes de qualquer código da SPA
  (a emenda vem antes da dependência entrar no build).
- **Phase 2** bloqueia tudo: T006/T009 em paralelo; T007 → T008 → T010 → T011 → T012; SPA T013/T014/T016
  em paralelo → T015 → T017 → T018 → T019 → T020 → T021 → T022.
- **Histórias (Phases 3–10):** depois da Phase 2, independentes entre si na API (um arquivo por aba), e
  cada uma segue testes → módulo → rota → `gen:contract` → aba → e2e. O `gen:contract` é serializado (um
  por vez). Os e2e são serializados pela trava.
- **Phase 11** depois das 8 histórias (entrega única, Clarification 2).

### Paralelismo sugerido (agentes)

- **Frente A (API P1):** T023–T025, T028–T029, T032–T033.
- **Frente B (API P2/P3):** T036–T037, T040–T041, T044–T045, T048–T049, T052–T053.
- **Frente C (SPA):** abas na ordem P1 → P3, consumindo as rotas conforme ficam prontas.
- **Frente D (e2e e polish):** e2e por história + T056–T059.

Arquivos compartilhados só por acréscimo; o `gen:contract` e os e2e são serializados.

## Implementation Strategy

Entrega única (Clarification 2): a ordem P1 → P3 define a sequência de trabalho, e a spec só fecha com as
8 abas, a Phase 11 verde e o quickstart percorrido. Checkpoints internos: depois da Phase 2 (base), das
P1 (Phases 3–5), das P2 (6–8) e das P3 (9–10).
