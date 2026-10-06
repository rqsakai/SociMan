# ADR 0002: Gráficos do analytics com Apache ECharts

**Status:** Aceita (2026-10-01, decisão do dono) · **Constitution:** 4.1.0 (Restrições técnicas) ·
**Spec:** 019-analytics (research R1)

## Contexto
- A spec 016 decidiu não usar biblioteca de gráficos (R14) e desenhou um gráfico de linha próprio
  (`LinhaChart`, SVG).
- A spec 019 transforma "Métricas" num analytics de decisão. São cerca de 25 cards com:
  - mapas de calor 7 × 24;
  - calendário;
  - radar contra a média;
  - dispersões;
  - boxplot;
  - funil e sankey;
  - barras e linhas.
- Manter 7 tipos de gráfico feitos à mão, com tooltip e acessibilidade, custaria mais que a feature.
- A CSP de produção tem `script-src 'self'` estrito (ADR 0001) e não pode ganhar `unsafe-eval`.

## Decisão
- **Apache ECharts 6.1.0** (Apache-2.0), importado de forma modular (`echarts/core`, `echarts/charts`,
  `echarts/components`, `echarts/renderers`), nunca pelo pacote inteiro.
- Componente React próprio (`components/analytics/Grafico.tsx`), sem `echarts-for-react`.
- **Configuração:**
  - renderer **SVG**;
  - locale PT-br;
  - `aria` com descrição escrita por nós; textura (`decal`) desligada por padrão e opcional por gráfico (prop `textura`), porque a acessibilidade é garantida pela tabela alternativa e pelos rótulos;
  - tema lido dos tokens `--chart-*` e trocado em runtime com `setTheme`.
- **Carregamento:**
  - só na rota de analytics, via `React.lazy`;
  - o chunk `graficos` fica **fora do precache** do PWA (`globIgnores`) e entra num cache em runtime.
- Toda string vinda de fora (títulos e legendas da rede) passa por `echarts.format.encodeHTML` no tooltip,
  que é montado com `innerHTML`.

## Consequências
- **CSP intacta.** O build modular foi testado no Chromium com a política do edge: 0 violações e nenhum
  `eval` ou `Function`. O único `new Function` do pacote (fallback de GeoJSON) fica fora do build
  modular, e o `check:bundle` passa a reprovar `Function(`/`eval(` no `dist`.
- **Peso:** cerca de 234 kB gzip, baixados só ao abrir o analytics. As outras telas e a instalação do PWA
  não pagam esse custo.
- **Acessibilidade:** o ECharts não navega por teclado. A tabela alternativa ("Ver tabela"), presente em
  todo card, é o caminho acessível.
- **Escopo da revogação:** a R14 da 016 deixa de valer só para o analytics. O `LinhaChart` próprio
  continua no detalhe do vídeo e no painel do destino.
- Adicionar outra biblioteca de gráficos exige nova emenda.
