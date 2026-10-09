# Implementation Plan: Analytics de decisão

**Branch**: `019-analytics` | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/019-analytics/spec.md`

## Summary

A entrada "Métricas" vira um analytics de decisão com 8 abas (Visão geral, Quando postar, O que funciona,
Curvas, Contas, Funil, Mercado, Alertas), período global com comparação ao período anterior, filtros por
perfil/conta/rede e o seletor de medida do post (1 h / 24 h / 7 d). **Sem tabela nova:** um pacote
`analytics/` na API agrega, na leitura, os dados da 016 (métricas da TikTok), 006/014 (envios, cortes,
destinos), 008 (custo de IA) e o YouTube dos canais-fonte, reaproveitando os marcos, características e
normalização já existentes. A SPA ganha uma rota carregada sob demanda com **Apache ECharts** (decisão do
dono), paleta validada para daltonismo em claro e escuro, tabela alternativa, "Como ler" e CSV por card.
Tudo é só leitura (princípio I).

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite 8)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic 2 (API, sem dependência nova) · TanStack Query,
shadcn/ui, Tailwind 4 e **`echarts` 6.1.0 (novo; modular, renderer SVG, carregado sob demanda e fora do precache do PWA)** na SPA

**Storage**: PostgreSQL existente; **nenhuma migração**

**Testing**: pytest na stack efêmera (`npm run test:api`), ruff, `npm run check:web`, Playwright na stack
e2e efêmera (`flock /tmp/sociman-e2e.lock npm run test:e2e`)

**Target Platform**: SPA (desktop e celular via PWA, modo casa) + API no Docker

**Project Type**: web (apps/api + apps/web)

**Performance Goals**: cada aba responde em < 2 s com 10× o volume atual (SC-003); o resto do app não baixa
o código de gráficos (SC-004)

**Constraints**: CSP `script-src 'self'` estrita (sem eval/inline); fuso America/Sao_Paulo; só leitura;
amostra mínima antes de qualquer conclusão; responsivo em 390 px

**Scale/Scope**: hoje 1 conta conectada, 22 vídeos, 301 fotos, 397 cortes, 62 envios, 42 mil vídeos-fonte;
8 endpoints GET, 8 abas, ~25 cards

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | Só leitura: 8 rotas **GET** em `/api/analytics/*`; `analytics/` não importa `publicacao`, `httpx`, nem serviços que mudam estado (guardas em `test_constitution_guards.py`, R12). Os atalhos (detalhe do vídeo, "Gerar cortes") levam às telas existentes, onde valem as regras de sempre |
| **II. Direito é responsabilidade do dono** | ✅ | O status de direito do canal aparece no ranking de canais e nas oportunidades; o atalho do Mercado leva ao fluxo da 006, com o mesmo aviso e confirmação. Nada é bloqueado nem liberado pelo analytics |
| III. Marca em tokens | ✅ (não afetado) | Nenhum token de marca muda. As cores dos gráficos são tokens do tema (`--chart-*`), não da marca do perfil |
| **IV. Contrato é a fonte única** | ✅ | Rotas e schemas Pydantic → `npm run gen:contract`; a SPA usa o cliente gerado; nada editado à mão em `packages/contract` |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. CSP inalterada: ECharts verificado sem `eval`/`new Function`/script inline (R1); estilos inline do tooltip já são permitidos (ADR 0001). Custo de IA só para dono, calculado no servidor (membro recebe `null`). Nenhum token ou link de upload nas respostas |
| **VI. Testes antes de pronto** | ✅ | pytest com cálculo de referência por aba (SC-002), teste de desempenho 10× (SC-003), guardas de só leitura; ruff; `check:web` (inclui CSP e bundle); e2e `analytics.spec.ts` (abas, filtros na URL, permissões, celular, CSV) |
| **VII. Humano no controle** | ✅ (não afetado) | Nenhuma mutação, logo nada para historiar; alertas e insights são calculados na hora, não gravados |
| **VIII. Simplicidade** | ⚠️ justificado | 1 dependência nova no front (`echarts`), 0 tabela, 0 serviço, 0 dependência no backend. A constitution lista a stack: **adicionar a biblioteca é emenda** (4.0.0 → 4.1.0, MINOR) + ADR 0002 — ver Complexity Tracking |

**Reavaliação pós-design:** mantida. A emenda da constitution e o ADR 0002 entram como primeiras
tarefas (com aprovação do dono do texto) antes do código da SPA.

## Project Structure

### Documentation (this feature)

```text
specs/019-analytics/
├── plan.md              # este arquivo
├── research.md          # R1–R13
├── data-model.md        # fontes e entidades calculadas
├── quickstart.md        # roteiro de validação
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/analytics/
├── __init__.py
├── filtros.py        # Filtro (período, anterior, perfil/conta/rede, medida), validação
├── base.py           # posts do período → PostAnalisado (usa metricas.consulta.marcos e anonimizar.caracteristicas)
├── estatistica.py    # mediana, quartis, spearman, lift, Amostra
├── visao_geral.py    # indicadores, série diária, principais, ranking compacto
├── insights.py       # regras determinísticas
├── quando_postar.py  # mapas por publicação e audiência (R4), calendário
├── o_que_funciona.py # dispersões, canais, hashtags, modos, padrões
├── curvas.py         # curvas por idade, meia-vida, distribuição
├── contas.py         # comparação e radar
├── funil.py          # etapas, perdas, tempos, custo (dono)
├── mercado.py        # canais-fonte, oportunidades
├── alertas.py        # estagnado, destaque, sem coleta, vínculo a confirmar
├── schemas.py
└── router.py         # /api/analytics/* (GET), operationId analytics_*
apps/api/tests/
├── unit/test_analytics_estatistica.py, test_analytics_insights.py, test_constitution_guards.py (+019)
└── integration/test_analytics_*.py, analytics_helpers.py (reusa metricas_helpers.semear), test_analytics_desempenho.py

apps/web/src/
├── pages/metricas/Metricas.tsx          # vira casca lazy → pages/analytics/Analytics.tsx
├── pages/analytics/Analytics.tsx        # abas, filtros globais na URL
├── pages/analytics/abas/*.tsx           # uma por aba
├── components/analytics/
│   ├── Grafico.tsx                       # wrapper ECharts (echarts/core, init/dispose, ResizeObserver, tema)
│   ├── echarts.ts                        # registro tree-shaken dos charts/componentes usados
│   ├── tema.ts                           # tema ECharts lido das variáveis --chart-* (claro/escuro)
│   ├── CardAnalytics.tsx                 # título, Como ler, amostra, Ver tabela, CSV
│   ├── Indicador.tsx, Amostra.tsx, FiltrosGlobais.tsx, TabelaAlternativa.tsx
│   └── csv.ts                            # CSV no cliente (R10)
├── lib/analytics.ts                      # hooks TanStack Query + formatadores
└── index.css                             # tokens --chart-1..8 e --chart-seq-* (claro e escuro)

e2e/analytics.spec.ts                      # + ajustes em e2e/metricas.spec.ts
docs/adr/0002-graficos-echarts.md          # nova ADR
.specify/memory/constitution.md            # emenda 4.1.0 (Restrições técnicas: echarts no SPA)
```

**Structure Decision**: web app existente (apps/api + apps/web). O pacote `analytics/` fica separado de
`metricas/` porque agrega várias specs e é só leitura; ele **importa** funções de `metricas/` (que segue
sendo dona da coleta e do vínculo), nunca o contrário.

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Dependência nova `echarts` (emenda da constitution 4.1.0 + ADR 0002) | Heatmap, calendário, radar, sankey, boxplot, dispersão com zoom e tooltips acessíveis em ~25 cards; decisão explícita do dono | SVG próprio (R14 da 016) exigiria escrever e manter 7 tipos de gráfico, acessibilidade e tooltips; Recharts não tem heatmap/calendário |
| Revogar a decisão R14 da 016 ("sem biblioteca") | O `LinhaChart` próprio continua onde está (detalhe do vídeo); o analytics usa ECharts só na rota lazy | Migrar o detalhe do vídeo também (fora do escopo) |
