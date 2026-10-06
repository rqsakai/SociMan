# ADRs do SociMan

Decisões de arquitetura do SociMan, no formato Contexto / Decisão / Consequências / Status.
As ADRs do volans (`docs/reference/volans/decisions/`) são só referência; quando uma decisão do
SociMan contradiz alguma delas, a ADR daqui prevalece e o trecho do volans ganha uma nota
apontando para cá.

| # | Decisão | Status |
|---|---|---|
| [0001](0001-ui-shadcn-tanstack-csp-styles.md) | UI com shadcn/ui + TanStack; CSP com `style-src 'unsafe-inline'` e `script-src` estrito | Aceita |
| [0002](0002-graficos-echarts.md) | Gráficos do analytics com Apache ECharts modular, sob demanda (revoga a R14 da 016 só no analytics) | Aceita |
