# Data Model: Analytics de decisão (019)

**Nenhuma tabela, coluna ou migração nova** (research R2). Tudo é calculado na leitura a partir das
tabelas existentes. Este documento descreve as fontes, as entidades calculadas (que existem só nas
respostas da API) e as regras de cálculo.

## Fontes (existentes)

| Tabela | Uso na 019 | Colunas-chave |
|---|---|---|
| `metricas_series` | conta da rede, anônimas, alerta "sem coleta" | `conta_id`, `rede`, `rotulo`, `anonima_n`, `ultima_coleta_em` |
| `metricas_videos` | post analisado | `serie_id`, `publicado_em`, `duracao_s`, `legenda`, `destino_id`, `disponivel` |
| `metricas_video_fotos` | marcos, ganhos por hora, curvas | `video_id`, `coletado_em`, `idade_s`, `views`, `likes`, `comments`, `shares` |
| `metricas_conta_fotos` | seguidores ganhos | `serie_id`, `janela_em`, `seguidores` |
| `postagens` (destino) | modo, hashtags, aprovação, publicação, perdas | `conteudo_id`, `conta_id`, `estado`, `modo`, `hashtags`, `aprovado_em`, `posted_at`, `recusado_em`, `archived_at` |
| `conteudos` / `cortes` | duração, gancho, score, processamento | `corte_id`, `hook_text`, `openshorts_score`, `duration_ms`, `status`, `archived_at`, `envio_id` |
| `envios` | funil, tempos, padrão usado | `sent_at`, `started_at`, `finished_at`, `status`, `config`, `canal_fonte_id`, `video_fonte_id` |
| `canais_fonte` / `videos_fonte` | canal de origem, Mercado | `title`, `handle`, `direito`; `published_at`, `views`, `vph_recente`, `live`, `disponivel` |
| `ia_chamadas` | custo de IA (só dono) | `conteudo_id`, `custo_usd`, `created_at` |
| `contas` / `perfis` | filtros e nomes | `perfil_id`, `platform`, `handle`; `name`, `slug` |

Cadeia de vínculo (016): `metricas_videos.destino_id → postagens.conteudo_id → conteudos.corte_id →
cortes.envio_id → envios.{video_fonte_id, canal_fonte_id}`.

## Entidades calculadas

### Filtro (entrada de toda aba)

| Campo | Tipo | Regra |
|---|---|---|
| `de`, `ate` | data (AAAA-MM-DD) | dias em America/Sao_Paulo, `[de 00:00, ate+1 00:00)`; padrão: últimos 7 dias; máx. 400 dias (`validar_periodo` da 016) |
| `perfilId`, `contaId` | uuid opcional | conta tem precedência; conta precisa ser do perfil, senão 400 |
| `rede` | enum opcional | `tiktok` hoje; demais redes devolvem vazio, sem erro |
| `medida` | `h1` \| `h24` \| `d7` | padrão `h24` (Clarification 5) |
| Período anterior | derivado | mesma duração, terminando em `de` |

### PostAnalisado (interno)

`video_id`, `serie_id`, `conta_id` (nulo se anônima), `rotulo_conta`, `publicado_em`, `hora_local`
(0–23), `dia_semana` (0 = segunda), `duracao_s`, `titulo_curto` (40 caracteres), `link`,
`thumb_url` (a mesma do ranking corrigido), `medida` (valor + `estimado` + `aguardando`),
`views_atual`, `engajamento`, `hashtags` (normalizadas, do destino ∪ legenda), `vinculado` (bool) e,
se vinculado: `modo`, `score`, `gancho_caracteres`, `canal_fonte` (id, título, direito), `padrao`
(`clip_min_s`/`clip_max_s`/`layout` de `envios.config`), `conteudo_id`.

### Indicador

`chave`, `valor`, `anterior`, `variacao_pct` (nulo = "sem base de comparação"), `n`.
Chaves: `views`, `likes`, `engajamento`, `seguidores`, `posts`, `mediana_post`.
- `views`/`likes`: soma dos ganhos no período (última foto ≤ fim − última foto ≤ início, por vídeo; 0
  se negativo).
- `engajamento`: (Δlikes + Δcomments + Δshares) ÷ Δviews no período.
- `seguidores`: última `FotoConta` ≤ fim − última ≤ início, por série.
- `posts`: vídeos com `publicado_em` no período.
- `mediana_post`: mediana da medida dos posts do período que não estão "aguardando".

### Amostra

`n`, `minimo`, `suficiente` (bool), `faltam` (= max(0, minimo − n)). Toda conclusão carrega uma.

### Insight

`regra` (`horario`, `dia`, `duracao`, `canal`, `hashtag`, `destaque`), `frase`, `valor` (razão ou
número), `grupo` (ex.: "18h–21h"), `amostra`, `pendente` (bool; se verdadeiro, `frase` diz o que falta).

### CelulaMapa

`dia` (0–6), `hora` (0–23), `valor` (nulo se vazio), `n`, `amostra_pequena` (n < `MIN_GRUPO` no mapa
por publicação). O mapa da audiência traz também `sem_hora` (views não atribuídas, R4).

### PontoDispersao

`video_id`, `x`, `y` (medida), `titulo_curto`, `conta` — com `correlacao` (ρ, leitura, amostra) no
nível do gráfico.

### LinhaRanking (canais, hashtags, modos, padrões)

`chave`, `rotulo`, `n`, `mediana`, `lift` (nulo sem base), `extra` (ex.: direito do canal).

### Curva

`video_id`, `pontos` [(`idade_h`, `views`)], `meia_vida_h` (nulo = "ainda não calculável" se idade
< 7 d), `conta`.

### RadarConta

`conta_id`, `eixos` [{`chave`, `valor`, `media`, `indice` (0–200, `acima` se cortado)}].
Eixos: `views_por_post` (mediana da medida), `engajamento`, `frequencia` (posts/dia no período),
`crescimento` (% de seguidores ganhos), `velocidade_1h` (mediana do marco h1), `acima_mediana` (% de
posts acima da mediana geral). Média = média simples das contas com ≥ 1 post no período; com < 2
contas, `radar = null` e só a tabela.

### EtapaFunil

`chave` (`enviados`, `cortes`, `aprovados`, `publicados`, `acima_patamar`), `n`, `conversao_pct`,
`perdas` [{`motivo`, `n`}], `tempo_mediano_h` (quando houver). `custo_ia_usd` e
`custo_por_mil_views_usd` só para dono (nulos para membro).

### Oportunidade

`video_fonte_id`, `titulo_curto`, `canal` (título, `direito`), `idade_h`, `views`, `velocidade`
(views/h), `link_gerar_cortes`.

### Alerta

`tipo` (`estagnado`, `destaque`, `sem_coleta`, `vinculo_a_confirmar`), `severidade`
(`atencao`/`info`/`positivo`), `alvo` (vídeo, série ou destino), `motivo`, `numeros` (ex.: idade,
views, mediana de referência), `link`.

## Regras transversais

- **Fuso:** toda hora/dia em `settings.app_tz` (America/Sao_Paulo), via `AT TIME ZONE` no SQL ou
  `astimezone` no Python; nunca UTC na resposta para o usuário.
- **Anônimas:** séries anonimizadas entram em totais com o `rotulo` "Conta anônima N" e não aparecem
  no filtro por conta.
- **Hashtags:** `ia.guia.normalizar` (NFKD, sem acento, casefold) e `#(\w+)`; união das do destino e
  da legenda, sem repetição.
- **Sem escrita:** nenhuma função do pacote `analytics/` chama `db.add`, `flush`, `commit`,
  `history.record` nem serviços que mudam estado (guarda R12).
