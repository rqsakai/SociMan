# Data Model: Aprender com o desempenho (023)

Migration **`0018_aprendizado`** (`revision = "0018_aprendizado"`, `down_revision = "0017_publico"`).
Ela cria 6 tabelas, 5 enums e 3 colunas em `ia_chamadas`. Todas as tabelas de domínio têm `version`,
`history.record` e soft-delete por estado. Não há DELETE (princípio VII).

## Enums

| Enum | Valores |
|---|---|
| `aprendizado_origem` | `ia`, `dono` |
| `aprendizado_estilo_gancho` | `pergunta`, `revelacao`, `numero_lista`, `polemica`, `humor`, `voce_sabia`, `ordem_direta`, `outro` |
| `aprendizado_analise_estado` | `pendente`, `processando`, `pronta`, `erro` |
| `aprendizado_decisao` | `aberta` (só de hipótese), `aceita`, `rejeitada` |
| `aprendizado_conferencia_resultado` | `ok`, `problema`, `nao_sei` |

## Tabelas

### `aprendizado_temas` (entity_type `aprendizado_tema`)

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid FK perfis, NOT NULL | imutável |
| `nome` | text NOT NULL | 1–40 caracteres. Único por perfil entre os ativos, pela forma normalizada: índice único parcial em `(perfil_id, nome_norm) WHERE archived_at IS NULL` |
| `nome_norm` | text NOT NULL | `ia.guia.normalizar(nome)` |
| `descricao` | text NOT NULL default '' | ≤ 200 |
| `palavras_chave` | text[] NOT NULL default '{}' | ≤ 20 itens, cada um com 2–30 caracteres, normalizados e sem repetir |
| `juntado_em_id` | uuid FK aprendizado_temas NULL | preenchido ao juntar, quando o tema também é arquivado |
| `archived_at`, `archived_by` | | arquivar e juntar |
| `version`, AuditMixin | | `__versioned_fields__ = ("nome", "descricao", "palavras_chave", "archived", "juntado_em_id")` |

CHECKs:
- `cardinality(palavras_chave) <= 20`;
- `juntado_em_id IS NULL OR archived_at IS NOT NULL`;
- `juntado_em_id <> id`.

No serviço: no máximo 30 ativos por perfil (409 `temas_no_maximo`).

### `aprendizado_classificacoes` (entity_type `aprendizado_classificacao`)

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `video_id` | uuid FK metricas_videos, UNIQUE, NOT NULL | o post |
| `perfil_id` | uuid FK perfis NOT NULL | o perfil da conta da série no momento |
| `tema_id` | uuid FK aprendizado_temas NULL | NULL = "Sem tema" |
| `secundarios` | uuid[] NOT NULL default '{}' | ≤ 2; não contém `tema_id` |
| `estilo_gancho` | aprendizado_estilo_gancho NULL | NULL = sem gancho (vídeo sem corte e sem texto) |
| `justificativa` | text NULL | ≤ 160. NULL depois da anonimização |
| `sugestao_tema` | text NULL | ≤ 40; tema "inventado" pela IA (FR-005) |
| `origem` | aprendizado_origem NOT NULL | `dono` nunca é sobrescrito pela IA (serviço e teste) |
| `evidencia_parcial` | bool NOT NULL | true quando o vídeo não tem corte |
| `reclassificar` | bool NOT NULL default false | true depois de arquivar o tema |
| `taxonomia_versao` | int NOT NULL | a versão da taxonomia usada (R2 da spec) |
| `chamada_id` | uuid FK ia_chamadas NULL | a última chamada da IA (NULL na correção do dono) |
| `version`, AuditMixin | | `__versioned_fields__ = ("tema_id", "secundarios", "estilo_gancho", "origem", "reclassificar")` |

Índices: `(perfil_id, tema_id)`, e `(perfil_id) WHERE reclassificar`.

**Pendente de classificação** (calculado): é um `metricas_videos`:
- de uma série viva, com conta de um perfil com ≥ 1 tema ativo e `classificacao_auto`;
- com idade ≥ 24 h;
- disponível;
- **sem** linha em `aprendizado_classificacoes`, **ou** com `reclassificar` e `origem = ia`.

### `aprendizado_preferencias` (entity_type `aprendizado_preferencias`)

Há uma linha do perfil (`conta_id IS NULL`) e no máximo uma por conta. A linha nasce na 1ª escrita (sem
linha = `version 0`).

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid FK NOT NULL | |
| `conta_id` | uuid FK contas NULL | a conta precisa ser do perfil |
| `temas` | jsonb NOT NULL default '{}' | `{temaId: "ampliar" \| "cortar"}` |
| `hashtags_evitar` | text[] NOT NULL default '{}' | normalizadas `#…`, ≤ 30 |
| `padroes` | jsonb NOT NULL default '[]' | ≤ 10 itens `{tipo: "gancho"\|"duracao"\|"horario", texto (≤ 120), valor?}` |
| `taxonomia_versao` | int NOT NULL default 0 | só na linha do perfil. É incrementada a cada criação, edição, junção, arquivamento ou restauração de tema, na mesma transação. Se a linha do perfil não existe, a 1ª mudança de tema a cria (`history created`, autor do tema) |
| `classificacao_auto` | bool NOT NULL default true | só na linha do perfil |
| `usar_desempenho` | bool NOT NULL default true | só na linha do perfil |
| `pedido_classificacao_em` | timestamptz NULL | "classificar pendentes" |
| `version`, AuditMixin | | `__versioned_fields__ = ("temas", "hashtags_evitar", "padroes", "classificacao_auto", "usar_desempenho")`. `taxonomia_versao` e `pedido_classificacao_em` ficam fora do snapshot (são contadores técnicos) |

Índices únicos: `(perfil_id) WHERE conta_id IS NULL` e `(conta_id) WHERE conta_id IS NOT NULL`.

### `aprendizado_analises` (entity_type `aprendizado_analise`; registro imutável depois de `pronta`/`erro`)

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid FK NOT NULL | |
| `conta_id` | uuid FK NULL | escopo de conta |
| `estado` | aprendizado_analise_estado NOT NULL | `pendente → processando → pronta \| erro` (só a trilha avança) |
| `medida` | text NOT NULL | `h1`/`h24`/`d7` |
| `n` | int NOT NULL | 1–15 |
| `com_quadros` | bool NOT NULL | |
| `quadros_por_video` | int NOT NULL default 0 | 0 ou 4 |
| `videos_sem_arquivo` | int NOT NULL default 0 | entraram só com texto |
| `melhores`, `comparaveis` | uuid[] NOT NULL | ids de `metricas_videos` escolhidos no pedido |
| `resumo_estatistico` | jsonb NOT NULL | os efeitos com confiança ≥ fraca enviados à IA |
| `hipoteses` | jsonb NULL | lista `{texto, postsIds, contraste, n, grau}`. Os textos são trocados na anonimização |
| `custo_estimado_usd` | numeric(10,6) NOT NULL | o mostrado ao confirmar |
| `chamada_id` | uuid FK ia_chamadas NULL | |
| `erro_code` | text NULL | `ia_*` da 008, `hd_indisponivel`, `sem_posts` |
| `taxonomia_versao` | int NOT NULL | |
| `pedido_por` | uuid FK users NOT NULL | dono humano |
| `created_at`, `iniciada_em`, `concluida_em` | timestamptz | |
| `version` | int | `created` (pedido) e `updated` (conclusão pela trilha, `system:aprendizado`) |

Índices: `(perfil_id, created_at DESC)`, e `(estado, created_at) WHERE estado IN ('pendente','processando')`.

A trilha pega o pedido com `FOR UPDATE SKIP LOCKED`. Se a trilha morrer, um `processando` com mais de
15 min volta a `pendente` uma vez; na 2ª vez, vira `erro`.

### `aprendizado_decisoes` (entity_type `aprendizado_decisao`)

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid FK NOT NULL | |
| `conta_id` | uuid FK NULL | escopo |
| `chave` | text NOT NULL | `"<tipo>:<escopo>:<alvo>"` (R6) |
| `tipo` | text NOT NULL | `tema_ampliar`, `tema_cortar`, `hashtag_fixar`, `hashtag_evitar`, `padrao_gancho`, `padrao_duracao`, `padrao_horario` |
| `origem` | text NOT NULL | `regra` \| `hipotese` |
| `analise_id` | uuid FK NULL | quando `origem = hipotese` |
| `estado` | aprendizado_decisao NOT NULL | |
| `evidencia` | jsonb NOT NULL | o efeito, o intervalo, n, dias, confiança, posts (ids) e a taxonomia_versao no momento |
| `n_decisao`, `faixa_decisao` | int, text NOT NULL | para a regra de reaparecer (FR-038) |
| `texto` | text NULL | só nos padrões (≤ 120) |
| `motivo` | text NULL | ≤ 300, na rejeição |
| `preferencias_version` | int NULL | a versão das preferências criada pelo aceite |
| `decidido_por`, `decidido_em` | | dono humano |
| `version`, AuditMixin | | |

Índice: `(perfil_id, chave, decidido_em DESC)`. Uma chave pode ter várias decisões ao longo do tempo
(rejeitou e depois aceitou), e vale a mais recente.

### `aprendizado_conferencias` (entity_type `aprendizado_conferencia`)

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `video_id` | uuid FK metricas_videos NOT NULL | |
| `item` | text NOT NULL | chave de `diagnostico.CHECKLIST` (CHECK com a lista) |
| `resultado` | aprendizado_conferencia_resultado NOT NULL | |
| `nota` | text NULL | ≤ 300. NULL depois da anonimização |
| `version`, AuditMixin | | UNIQUE `(video_id, item)` |

### `ia_chamadas` (colunas novas)

| Coluna | Tipo | Regra |
|---|---|---|
| `desempenho_perfil_version` | int NULL | NULL = bloco não enviado |
| `desempenho_conta_version` | int NULL | |
| `desempenho_exemplos` | uuid[] NOT NULL default '{}' | ids de `metricas_videos` |

`entity_type` das chamadas novas:
- `perfil`, para `aprendizado.taxonomia`;
- `aprendizado_classificacao`, com `entity_id = video_id`, para `aprendizado.classificacao`;
- `aprendizado_analise`, para `aprendizado.analise`.

## Migration `0019_aprendizado_fonte_temas` (plano B do R9)

### `aprendizado_fonte_temas` (cache derivado; sem `version`/`history`)

| Coluna | Tipo | Regra |
|---|---|---|
| `perfil_id` | uuid FK perfis | PK (perfil_id, video_fonte_id, tema_id) |
| `video_fonte_id` | uuid FK videos_fonte | |
| `tema_id` | uuid FK aprendizado_temas | apagadas ao arquivar ou juntar o tema |

Índice: `(perfil_id, tema_id)`. A trilha reconstrói o perfil quando a taxonomia muda e casa, de forma
incremental, os vídeos-fonte novos. Em `aprendizado_preferencias` (linha do perfil, fora do snapshot):
`fonte_temas_versao` (a taxonomia casada) e `fonte_temas_em` (até quando). Sem casamento em dia, a afinidade
fica neutra.

## Entidades calculadas (só nas respostas)

### Efeito

`fator`, `valor` (id ou rótulo), `rotulo`, `parte` (`entrega` | `rendimento`), `efeito` (p.p. ou fator ×),
`intervalo` ([baixo, alto]), `nPosts`, `nDias`, `confianca` (`forte`/`moderada`/`fraca`/`indicio`/
`amostra_pequena`), `faltam` (int|null), e `avisos[]`:
- `puxado_por_1` (com `semMaior`);
- `nao_separavel` (com `tema`);
- `quase_so_com` (com `fator`, `valor`);
- `travada`;
- `em_alta`;
- `em_queda`.

### Analise (GET)

`contexto` (período, medida, contas, `aguardando`, `comparacoes`, `travadas[]`), `efeitos[]`, `blocos[]`
(as hashtags juntas), `matriz` (hashtags × temas → n), `semTema` (n), `pendentesClassificacao` (n).

### Recomendacao (GET)

`chave`, `tipo`, `escopo` (`perfil` | `conta` + `contaId`), `alvo` (`temaId`/`hashtag`/`padrao`), `motivo`,
`evidencia` (o Efeito), `oQueMuda`, `origem`, `jaRejeitadaEm` (data|null) e `bloqueio` (por exemplo
`fixas_no_maximo`, com a lista).

### Afinidade (no `VideoFonte` do Descobrir e nas oportunidades do Mercado)

`pontos` (−20..20), `temaId`, `temaNome`, `cortado` (bool) e `motivo` (null se não for o principal). A
resposta da lista ganha `ocultosPorTema`.

### Sinal de distribuição

`tipo` (os do R10), `alvo` (conta ou post), `numero` (o valor que o sustenta) e `texto`.

## Regras de transição

- **Tema:** ativo → arquivado (`archived`) ↔ restaurado. Juntar (A → B): A é arquivado com
  `juntado_em_id = B`, as classificações com `tema_id = A` passam a B e os secundários A viram B (sem
  repetir). Tudo numa transação, com `history` em cada linha e `details.juntar`. Reverter a junção (no tema
  A) restaura A e devolve as classificações movidas (lista em `details`).
- **Arquivar:** as classificações com `tema_id = A` vão a NULL, com `reclassificar = true`; as de
  `origem = dono` também vão a NULL, mas continuam `dono` e não são reclassificadas pela IA (aparecem
  "Sem tema" para o dono corrigir).
- **Classificação pela IA:** só cria ou atualiza linhas com `origem = ia`. A correção do dono grava
  `origem = dono`. O revert do dono pode voltar a `ia`.
- **Análise:** `pendente → processando → pronta | erro`. Não há outra transição, nem DELETE.

## Migration `0018_aprendizado`

- **upgrade:** cria os enums, as 6 tabelas (com CHECKs e índices) e as 3 colunas em `ia_chamadas`, com
  default (as linhas antigas ficam NULL / '{}').
- **downgrade:** remove as colunas, as tabelas e os enums, na ordem inversa.
- `test_migration_0018`: sobe sobre a 0017; cada CHECK e índice único recusa com `INSERT` direto; faz down
  e up com dados nas tabelas da 008.
