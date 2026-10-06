# Contrato HTTP: Analytics (019)

Todas as rotas: `GET`, prefixo `/api/analytics`, `RequireUser` (dono ou membro), `operationId`
`analytics_*`, respostas JSON em camelCase (aliases Pydantic, como na 016). Nenhuma rota escreve.
O contrato tipado sai do OpenAPI (`npm run gen:contract`); este arquivo descreve a forma e as regras.

## Parâmetros comuns (query)

| Nome | Tipo | Padrão | Erro |
|---|---|---|---|
| `de`, `ate` | `AAAA-MM-DD` | últimos 7 dias (hoje − 6 … hoje, fuso da casa) | 400 `periodo_invalido` (ate < de, > 400 dias) |
| `perfilId` | uuid | — | 404 `not_found` se não existir |
| `contaId` | uuid | — | 400 `conta_fora_do_perfil` se não for do perfil informado |
| `rede` | `tiktok` \| `youtube` \| `instagram` \| … | todas | — (rede sem dados → listas vazias) |
| `medida` | `h1` \| `h24` \| `d7` | `h24` | 422 (validação) |

Todo corpo de resposta começa com o bloco `contexto`:

```json
{
  "contexto": {
    "de": "2026-09-25", "ate": "2026-10-01",
    "anteriorDe": "2026-09-18", "anteriorAte": "2026-09-24",
    "medida": "h24", "fuso": "America/Sao_Paulo",
    "postsNoPeriodo": 18, "aguardando": 3, "foraDoSociman": 10,
    "minimos": { "grupo": 5, "correlacao": 8, "contasRadar": 2 }
  }
}
```

`Amostra` = `{ "n": 4, "minimo": 5, "suficiente": false, "faltam": 1 }`.

## Rotas

| operationId | Rota | Corpo (além de `contexto`) |
|---|---|---|
| `analytics_visao_geral` | `/api/analytics/visao-geral` | `indicadores[]` (Indicador), `serieDiaria[]` {`dia`, `porConta[]` {`contaId`, `rotulo`, `views`}}, `principais[]` (top 10 PostAnalisado resumido), `insights[]` (Insight), `ranking` (o ranking da 016 compacto, 1ª página) |
| `analytics_quando_postar` | `/api/analytics/quando-postar` | `porPublicacao` {`celulas[]` CelulaMapa}, `audiencia` {`celulas[]`, `semHora`}, `calendario[]` {`dia`, `posts`, `views`} |
| `analytics_o_que_funciona` | `/api/analytics/o-que-funciona` | `dispersoes` {`duracao`, `gancho`, `score`} cada um {`pontos[]`, `correlacao` {`rho`, `leitura`, `amostra`}}, `canais[]`, `hashtags[]`, `modos[]`, `padroes[]` (LinhaRanking), `excluidosSemVinculo` |
| `analytics_curvas` | `/api/analytics/curvas` | `curvas[]` (Curva, máx. 50 vídeos mais recentes do período), `distribuicao[]` {`contaId`, `rotulo`, `min`, `q1`, `mediana`, `q3`, `max`, `amostra`} |
| `analytics_contas` | `/api/analytics/contas` | `contas[]` {`contaId`, `rotulo`, `perfil`, `rede`, `indicadores[]`}, `perfis[]` {idem por perfil}, `radar[]` (RadarConta) ou `null` + `radarMotivo` |
| `analytics_funil` | `/api/analytics/funil` | `etapas[]` (EtapaFunil), `patamar`, `custoIaUsd`*, `custoPorMilViewsUsd`* |
| `analytics_mercado` | `/api/analytics/mercado` | `publicacao` {`celulas[]`}, `velocidadePorHorario` {`celulas[]`}, `oportunidades[]` (Oportunidade, top 25), `canais[]` {`canalId`, `titulo`, `direito`, `videos`, `medianaVelocidade`} |
| `analytics_alertas` | `/api/analytics/alertas` | `alertas[]` (Alerta), `contagem` {`atencao`, `info`, `positivo`} |

\* `null` para membro (o servidor não calcula). Parâmetro extra do funil: `patamar` (inteiro ≥ 1,
padrão 100).

## Regras de resposta

- Listas sempre presentes (vazias quando não há dado); nunca 404 por "sem dados".
- Números monetários em USD com 4 casas; percentuais como fração (0–1) — a SPA formata.
- Datas e horas em ISO 8601 com o deslocamento de America/Sao_Paulo.
- `estimado: true` acompanha todo valor vindo de marco interpolado.
- Nenhum token, link de upload ou identificador de conta anônima aparece nas respostas.

## Erros

`ErrorEnvelope` padrão (`code`, `message`, `details`): 400 `periodo_invalido`, 400
`conta_fora_do_perfil`, 401, 403 (senha provisória), 404 `not_found`, 422 validação.

## SPA

- Rota: `/app/metricas` (lazy) com `?aba=visao-geral|quando-postar|o-que-funciona|curvas|contas|funil|mercado|alertas`
  (padrão some da URL), `?de&ate&perfil&conta&rede&medida`. `/app/metricas/videos/:id` continua igual.
- CSV de cada card gerado no cliente a partir da tabela alternativa (R10).
