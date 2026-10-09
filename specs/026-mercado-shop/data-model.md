# Modelo de dados: 026-mercado-shop

Tudo fica no PostgreSQL (NVMe), na migration **`0025_mercado_shop`** (número provisório: o gate T001
confere o próximo livre; a última aplicada nesta worktree é a `0021`, e a 012 ocupa a `0022` em outra
sessão). Os arquivos ficam no MinIO do HD: as **imagens** (de produto e de avaliação) no bucket `imagens`
(o único que o imgproxy lê), com o prefixo `mercado/<sha[:2]>/<sha>.<ext>`; o **bruto** de cada coleta no
bucket novo **`sociman-mercado`**, em `bruto/<data_local>/<coleta_id>/<tarefa_id>.json.gz`. O Postgres
guarda só a referência (`bruto_ref` = object key) e a `esquema_versao` do adaptador que normalizou.

O modelo tem **três camadas**, com regras diferentes:

| Camada | Tabelas | Dono | Mutação | Histórico |
|---|---|---|---|---|
| **Lago** (global, permanente) | `mercado_categorias`, `mercado_lojas`, `mercado_loja_fotos`, `mercado_produtos`, `mercado_produto_fichas`, `mercado_imagens`, `mercado_produto_imagens`, `mercado_produto_fotos`, `mercado_ranking_fotos`, `mercado_ranking_foto_itens`, `mercado_avaliacoes`, `mercado_produto_videos` | ninguém (sem `perfil_id`, `conta_id`, `tenant_id`, `created_by`, `user_id`) | fotos, fichas, itens, avaliações, vídeos e imagens **só inserção** (trigger); identidades (`produtos`, `lojas`, `categorias`) só com UPDATE em "último visto" e estado técnico | nenhum (`entity_versions` não muda); autoria = `coleta_id` |
| **Operação da coleta** | `mercado_fila`, `mercado_coletas`, `mercado_coleta_itens`, `coleta_eventos` | ninguém | fila e rodada são estado de job (UPDATE de estado e contadores); itens e eventos só inserção | nenhum |
| **Interesse** (por perfil; onde o tenant entra depois) | `mercado_interesses`, `mercado_perfil_config` | perfil (`perfil_id`; nulo = todos, só na vitrine) | `history.py` | `entity_type` `mercado_interesse`, `mercado_perfil_config` |
| **Infra do dono** | `coleta_clientes`, `coleta_config` | dono humano | `history.py` | `entity_type` `coleta_cliente`, `coleta_config` |

Nada do lago nem da operação é apagado, por nenhuma rotina (FR-002): a limpeza de 90 dias da 021 não se
aplica, e o `storage.apagar_por_excecao` não ganha exceção nova. O `TRUNCATE` dos testes e do `reset-db`
continua valendo (trigger de linha não dispara em `TRUNCATE`).

**Neutralidade de tenant.** Toda tabela do lago e da operação tem as dimensões `rede` (`platform`,
enum existente da 002) e `mercado` (`text CHECK (mercado ~ '^[A-Z]{2}$')`, só `BR` nesta spec), direta ou
pela FK ao produto. O guarda de metadata (FR-057) proíbe `perfil_id | conta_id | tenant_id | created_by |
user_id` em toda tabela `mercado_*` e `coleta_*`, com **uma exceção nominal**: `mercado_fila.perfil_id`,
que é operacional ("para quem esta tarefa foi gerada", para o revezamento e para o detalhe da fila), não
é dono do dado e nunca entra em filtro de leitura do lago. A camada de interesse é a que receberá o
`tenant_id` na spec de multi-tenant.

**O que a 027 e a 028 vão estender** (já previsto aqui para não migrar depois): tipos reservados na fila
(`busca_assunto`, `video`); `mercado_interesses.origem = video` e `tema_id`; `mercado_produto_videos`
nasce populada (vídeos top por produto) e a 027 cria as irmãs `mercado_videos`/`mercado_video_fotos`;
a 028 lê tudo pelas tools MCP `mercado_*` e grava só anotações (009) e a notificação
`mercado_novo_em_alta` (não criada aqui).

## Tipos (enums e CHECKs)

| Tipo | Forma | Valores |
|---|---|---|
| `mercado` | `text CHECK (~ '^[A-Z]{2}$')` | `BR` (fuso `America/Sao_Paulo`, moeda `BRL`, em `mercado/mercados.py`) |
| `rede` | `platform` (002) | `tiktok` nesta spec |
| `mercado_calor` | enum | `quente`, `morna`, `parada` |
| `mercado_turno` | enum | `manha` (coletado antes de `TURNO_CORTE = "15:30"` no fuso do mercado), `noite` |
| `mercado_fonte` | enum | `pagina_publica`, `affiliate` |
| `mercado_ranking_tipo` | enum | `mais_vendidos`, `em_alta`, `novos`, `alta_comissao` |
| `mercado_ranking_janela` | `text CHECK` | `1d`, `7d`, `30d`, `total` |
| `mercado_fila_tipo` | `text CHECK` | `produto`, `ranking`, `categorias`, `vitrine`, `loja`, `avaliacoes`, `produto_videos`; **reservados para a 027:** `busca_assunto`, `video` (aceitos pelo CHECK, nunca gerados pela trilha da 026; o coletor da 026 recusa com `tipo_desconhecido`) |
| `mercado_fila_fonte` | `text CHECK` | `pagina_publica`, `affiliate`, `ambas` |
| `mercado_fila_estado` | enum | `pendente`, `reservada`, `recebida`, `falhou`, `expirada` |
| `mercado_coleta_estado` | enum | `ativa`, `pausada_captcha`, `pausada_login`, `interrompida`, `encerrada`, `abortada` |
| `mercado_coleta_item_status` | enum | `gravado`, `repetido`, `invalido`, `erro`, `captcha` |
| `coleta_evento_tipo` | enum | `captcha`, `login_perdido`, `bloqueio_suspeito`, `layout_mudou`, `parar_local`, `retomou`, `iniciado`, `parado` |
| `mercado_interesse_origem` | enum | `manual`, `vitrine`, `ranking`, `video` (027), `loja`, `categoria` |
| `mercado_interesse_situacao` | enum | `ativo`, `pausado`, `encerrado` |
| `coleta_situacao` | enum | `ativo`, `suspenso`, `revogado` (final) |
| `notificacao_tipo` (006) | `ADD VALUE` | `coleta_captcha`, `coleta_login`, `coleta_bloqueio`, `coleta_layout`, `coleta_parada`, `mercado_interesse_auto` |

Convenções: ids da rede são **texto** (podem passar de 2^53); dinheiro em **centavos** inteiros com a
`moeda`; `sha256` em hexadecimal minúsculo de 64 caracteres; `data_local` é a data no fuso do mercado
calculada **pelo servidor** a partir de `coletado_em` (nunca do relógio do coletor).

## Lago

### `mercado_categorias` (taxonomia observada; identidade)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `rede` | `platform` not null | |
| `mercado` | text not null | CHECK `^[A-Z]{2}$` |
| `rede_categoria_id` | text not null | id da categoria na rede |
| `nome` | text not null | como a rede exibe (pt-BR no `BR`) |
| `nivel` | smallint not null | CHECK 1..3 (FR-008) |
| `pai_id` | uuid null FK → mercado_categorias.id | nulo no nível 1; CHECK `(nivel = 1) = (pai_id IS NULL)` |
| `caminho` | text not null | "L1 > L2 > L3", recalculado quando a tarefa `categorias` muda nome ou pai |
| `ativa` | boolean not null default true | `false` quando some da taxonomia semanal (nunca apagada; continua nas fichas e rankings antigos) |
| `primeira_vez_em` | timestamptz not null | |
| `ultimo_visto_em` | timestamptz not null | UPDATE operacional |
| `coleta_id` | uuid null FK → mercado_coletas.id | a rodada que viu por último |

Restrições e índices: UQ `(rede, mercado, rede_categoria_id)`; `ix_mercado_categorias_pai (pai_id)`;
`ix_mercado_categorias_ativas (rede, mercado, nivel) WHERE ativa`. UPDATE permitido só em `nome`,
`caminho`, `pai_id`, `ativa`, `ultimo_visto_em`, `coleta_id` (regra do service; guarda em teste).

### `mercado_lojas` (identidade)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `rede`, `mercado` | | como acima |
| `rede_loja_id` | text not null | |
| `nome` | text not null | |
| `oficial` | boolean not null default false | selo "Loja oficial" (ficha) |
| `url` | text null | canônica, sem parâmetros de consulta (FR-021) |
| `primeira_vez_em`, `ultimo_visto_em` | timestamptz not null | |
| `ultima_foto_em` | date null | `data_local` da última `mercado_loja_fotos` |
| `proxima_coleta_em` | timestamptz null | estado técnico (tarefa `loja`: ficha e produtos novos) |
| `coleta_id` | uuid null FK → mercado_coletas.id | |

UQ `(rede, mercado, rede_loja_id)`; `ix_mercado_lojas_nome (rede, mercado, lower(nome))`. UPDATE só em
`nome`, `oficial`, `url`, `ultimo_visto_em`, `ultima_foto_em`, `proxima_coleta_em`, `coleta_id`.

### `mercado_loja_fotos` (**só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `loja_id` | uuid not null FK → mercado_lojas.id | |
| `data_local` | date not null | fuso do mercado, pelo servidor |
| `fonte` | `mercado_fonte` not null | |
| `nota` | numeric(3,2) null | 0..5 |
| `seguidores` | bigint null | |
| `envio_no_prazo_pct` | numeric(5,2) null | 0..100 |
| `tempo_resposta_pct` | numeric(5,2) null | quando a loja expõe |
| `n_produtos` | int null | |
| `vendidos_total`, `vendidos_total_min`, `vendidos_total_max` | bigint null | ponto médio e faixa (Edge "1,2 mil") |
| `vendidos_total_exato` | boolean null | |
| `campos` | jsonb not null default '{}' | o resto normalizado que a página expôs (sem PII) |
| `bruto_ref`, `esquema_versao` | text null / text not null | object key no `sociman-mercado`; `bruto_ref` nulo = "bruto pendente" (HD indisponível, FR-030) |
| `coleta_id` | uuid not null FK → mercado_coletas.id | |
| `coletado_em` | timestamptz not null | relógio do servidor no recebimento |

UQ `(loja_id, data_local, fonte)` (`INSERT … ON CONFLICT DO NOTHING` → "repetido"). Trigger
`mercado_so_insercao` (`BEFORE UPDATE OR DELETE`, função `metricas_recusa_mudanca()` da 0011).

### `mercado_produtos` (identidade + último visto + estado de coleta)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `rede`, `mercado` | | |
| `rede_produto_id` | text not null | |
| `url_canonica` | text not null | sem parâmetros (é a URL que a fila entrega) |
| `titulo_atual` | text null | **cópia operacional** da ficha atual, para listar e buscar (`q`) sem join |
| `loja_id` | uuid null FK → mercado_lojas.id | cópia operacional da ficha atual |
| `categoria_id` | uuid null FK → mercado_categorias.id | idem (a folha, nível mais fundo visto) |
| `ficha_atual_id` | uuid null FK → mercado_produto_fichas.id (`use_alter`) | a última versão da ficha |
| `primeira_vez_em` | timestamptz not null | quando entrou no lago (FR-003; base de "novo em alta") |
| `lancado_em` | date null | quando a página expõe |
| `ultimo_visto_em` | timestamptz not null | |
| `ultima_foto_em` | date null | `data_local` da última foto de qualquer fonte |
| `ultima_foto_affiliate_em` | date null | para `AC_FOTO_MAX_DIAS` |
| `ultimas_avaliacoes_em`, `ultimos_videos_em` | date null | cadência de avaliações (30 d) e vídeos (7 d), FR-040a |
| `indisponivel_desde` | date null | Edge "indisponível": preenchida na 1ª foto com `disponivel = false`, zerada quando volta |
| `calor` | `mercado_calor` not null default `quente` | cadência (FR-040); recalculada pela trilha |
| `fotos_por_dia` | smallint not null default 1 | CHECK 1..2; 2 = manhã e noite (novo em alta e manual) |
| `proxima_coleta_em` | timestamptz null | nulo em `parada` |
| `ultimo_erro_codigo`, `ultimo_erro_em` | text null, timestamptz null | último item `erro`/`invalido` desta chave |
| `imagens_pendentes` | boolean not null default false | teto de imagens atingido antes de baixar; entra primeiro no dia seguinte |
| `fonte_descoberta` | `mercado_interesse_origem` not null | como o produto entrou no lago (manual, vitrine, ranking, loja, categoria, video) |
| `ultimo_ranking_em` | date null | última `data_local` em que apareceu em algum ranking (base de `SAI_DO_RANKING_DIAS`) |
| `coleta_id` | uuid null FK → mercado_coletas.id | |

Restrições e índices: UQ `(rede, mercado, rede_produto_id)`; `ix_mercado_produtos_fila (calor,
proxima_coleta_em) WHERE calor <> 'parada'`; `ix_mercado_produtos_loja (loja_id)`;
`ix_mercado_produtos_categoria (categoria_id)`; `ix_mercado_produtos_primeira (rede, mercado,
primeira_vez_em desc)`; `ix_mercado_produtos_titulo` GIN `to_tsvector('portuguese', coalesce(titulo_atual,''))`
(busca `q`). UPDATE só nas colunas operacionais (tudo depois de `url_canonica`); identidade imutável.

### `mercado_produto_fichas` (**só inserção**; versão por conteúdo)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `produto_id` | uuid not null FK → mercado_produtos.id | |
| `hash_conteudo` | text not null | sha256 hex da forma canônica (JSON ordenado) de `titulo, descricao, atributos, variantes, argumentos, selos, categoria_id, loja_id, imagens_sha`; nova linha **só** quando muda (FR-004) |
| `titulo` | text not null | |
| `descricao` | text not null default '' | |
| `atributos` | jsonb not null default '[]' | `[{nome, valor}]` (especificação técnica) |
| `variantes` | jsonb not null default '[]' | `[{redeVarianteId, nome, precoCentavos?, precoOriginalCentavos?, estoqueVisivel?, imagemSha?}]` |
| `argumentos` | text[] not null default '{}' | argumentos de venda da página |
| `selos` | text[] not null default '{}' | cupons, frete grátis, "mais vendido" etc. |
| `categoria_id` | uuid null FK → mercado_categorias.id | a folha; o caminho vem da categoria |
| `loja_id` | uuid null FK → mercado_lojas.id | |
| `imagens_sha` | text[] not null default '{}' | sha256 das imagens **na ordem da página** (também materializadas em `mercado_produto_imagens`) |
| `esquema_versao` | text not null | `tiktok_shop/1` |
| `bruto_ref` | text null | nulo = bruto pendente |
| `coleta_id` | uuid not null FK → mercado_coletas.id | |
| `coletado_em` | timestamptz not null | |
| `created_at` | timestamptz not null default now() | |

UQ `(produto_id, hash_conteudo)`; `ix_mercado_fichas_produto (produto_id, created_at desc)`. Trigger
`mercado_so_insercao`. O reprocessamento do bruto (FR-012) só pode **inserir** uma ficha nova se o
conteúdo renormalizado for diferente; nunca altera uma existente.

### `mercado_imagens` (arquivo original, deduplicado por conteúdo; **só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `sha256` | text not null UNIQUE | hex 64; conferido no coletor **e** no servidor |
| `object_key` | text not null UNIQUE | `mercado/<sha[:2]>/<sha>.<ext>` no bucket `imagens` (o imgproxy serve por `/img`) |
| `content_type` | text not null | CHECK em `image/jpeg`, `image/png`, `image/webp`, `image/avif`, `image/gif`; validado pelo **conteúdo** (Pillow, `imaging.py`), não pelo cabeçalho |
| `bytes` | bigint not null | ≤ 5 MB por arquivo (FR-032) |
| `width`, `height` | int not null | |
| `origem` | text not null | CHECK `produto | avaliacao` (onde apareceu pela primeira vez; informativo) |
| `coleta_id` | uuid not null FK → mercado_coletas.id | |
| `created_at` | timestamptz not null default now() | |

Imutável e **global**: a mesma foto em anúncios diferentes é uma linha, referenciada por várias fichas
(Edge). Sem redimensionar (FR-005). `bytes` entra na contagem do teto diário de imagens e no piso do HD.

### `mercado_produto_imagens` (ordem das imagens numa ficha; **só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `produto_id` | uuid not null FK → mercado_produtos.id | |
| `ficha_id` | uuid not null FK → mercado_produto_fichas.id | a versão a que a ordem pertence |
| `imagem_id` | uuid not null FK → mercado_imagens.id | |
| `posicao` | smallint not null | 0..`IMAGENS_POR_PRODUTO_MAX − 1` |

UQ `(ficha_id, posicao)`; `ix_mercado_produto_imagens_imagem (imagem_id)` ("onde esta imagem aparece").
Quando o teto de imagens interrompe o download, as posições faltantes **não** existem e o produto fica
`imagens_pendentes`; na visita seguinte, as linhas que faltam são inseridas na **mesma** ficha (o
`imagens_sha` da ficha já tinha a lista completa, vinda da página).

### `mercado_produto_fotos` (medição por dia, turno e fonte; **só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `produto_id` | uuid not null FK → mercado_produtos.id | |
| `data_local` | date not null | pelo servidor, fuso do mercado |
| `turno` | `mercado_turno` not null | `manha` se `coletado_em` < `TURNO_CORTE` local, senão `noite` |
| `fonte` | `mercado_fonte` not null | |
| `vendidos` | bigint null | ponto médio quando faixa |
| `vendidos_min`, `vendidos_max` | bigint null | faixa ("1,2 mil" → 1150..1249; "10 mil+" → 10000..null) |
| `vendidos_exato` | boolean null | `false` marca incerteza nos cálculos |
| `preco_min_centavos`, `preco_max_centavos` | int null | por variante (Edge); iguais quando preço único |
| `preco_original_centavos` | int null | preço de lista antes do desconto |
| `moeda` | text not null | CHECK `^[A-Z]{3}$`; `BRL` |
| `nota` | numeric(3,2) null | 0..5 |
| `n_avaliacoes` | int null | |
| `comissao_bp` | int null | pontos-base (500 = 5%); só `affiliate` |
| `n_criadores` | int null | criadores promovendo; só `affiliate` |
| `vendas_7d`, `vendas_30d` | bigint null | quando o Affiliate Center expõe (precedência, FR-044) |
| `estoque_visivel` | int null | soma do que a página mostra |
| `disponivel` | boolean not null default true | |
| `campos` | jsonb not null default '{}' | plano aberto/direcionado, amostra grátis, cupons etc. (sem PII) |
| `esquema_versao` | text not null | |
| `bruto_ref` | text null | nulo = bruto pendente |
| `coleta_id` | uuid not null FK → mercado_coletas.id | |
| `coletado_em` | timestamptz not null | |

Restrições e índices: UQ `(produto_id, data_local, turno, fonte)` (FR-006, FR-027; a 2ª foto do mesmo
dia, turno e fonte é "repetida"); CHECK `vendidos_min IS NULL OR vendidos_max IS NULL OR vendidos_min <=
vendidos_max`; CHECK `preco_min_centavos IS NULL OR preco_max_centavos IS NULL OR preco_min_centavos <=
preco_max_centavos`; CHECK `(fonte = 'affiliate') OR (comissao_bp IS NULL AND n_criadores IS NULL AND
vendas_7d IS NULL AND vendas_30d IS NULL)`; `ix_mercado_fotos_serie (produto_id, data_local desc, turno
desc, fonte)`; `ix_mercado_fotos_dia (data_local, fonte)` (orçamento e "estado da coleta");
`ix_mercado_fotos_affiliate (produto_id, data_local desc) WHERE fonte = 'affiliate'`. Trigger
`mercado_so_insercao`.

### `mercado_ranking_fotos` (a lista de um ranking num dia; **só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `rede`, `mercado` | | |
| `fonte` | `mercado_fonte` not null | `affiliate` nesta spec |
| `categoria_id` | uuid null FK → mercado_categorias.id | nulo = ranking geral |
| `tipo` | `mercado_ranking_tipo` not null | |
| `janela` | text not null | CHECK em `1d, 7d, 30d, total` |
| `data_local` | date not null | |
| `n_itens` | smallint not null | |
| `esquema_versao`, `bruto_ref` | | |
| `coleta_id` | uuid not null FK | |
| `coletado_em` | timestamptz not null | |

UQ `(rede, mercado, fonte, coalesce(categoria_id, '00000000-0000-0000-0000-000000000000'::uuid), tipo, janela, data_local)` (índice único
em expressão); `ix_mercado_ranking_fotos_cat (categoria_id, tipo, janela, data_local desc)`. Trigger
`mercado_so_insercao`.

### `mercado_ranking_foto_itens` (**só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `ranking_foto_id` | uuid not null FK → mercado_ranking_fotos.id | |
| `posicao` | smallint not null | 1..n |
| `produto_id` | uuid not null FK → mercado_produtos.id | criado "pela cara" (identidade + `titulo_atual`) se ainda não existia; a ficha vem na visita de produto |
| `valor_exibido` | text null | como o ranking mostrou ("12,3 mil vendidos", "+320%") |
| `valor_num` | numeric null | o número normalizado, quando dá |
| `campos` | jsonb not null default '{}' | preço, comissão, criadores que o cartão do ranking já traz |

UQ `(ranking_foto_id, posicao)`; `ix_mercado_ranking_itens_produto (produto_id, ranking_foto_id)` (posições
de um produto; `ultimo_ranking_em`). Trigger `mercado_so_insercao`.

### `mercado_avaliacoes` (**só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `produto_id` | uuid not null FK → mercado_produtos.id | |
| `rede_avaliacao_id` | text null | quando a rede expõe |
| `autor_hash` | text not null | `sha256(rede_autor_id + MERCADO_HASH_PEPPER)` hex; **nunca** nome, @ ou foto de perfil (FR-010); sem id de autor → `sha256("anon:" + texto_hash + pepper)` |
| `texto` | text null | como veio (sem o nome do autor; a poda é no coletor e conferida no servidor, FR-029) |
| `texto_hash` | text not null | sha256 do texto normalizado (minúsculas, espaços colapsados; vazio → hash de "") para dedup |
| `nota` | smallint null | CHECK 1..5 |
| `data_avaliacao` | date null | |
| `variante` | text null | nome da variante comprada |
| `imagens_sha` | text[] not null default '{}' | fotos do cliente, em `mercado_imagens` (**guardadas como vêm**, Clarification 1; risco em `docs/decisoes/coleta-mercado.md`) |
| `curtidas` | int null | |
| `campos` | jsonb not null default '{}' | sem PII (o servidor recusa as chaves da lista de poda) |
| `esquema_versao`, `bruto_ref` | | |
| `coleta_id` | uuid not null FK | |
| `coletado_em` | timestamptz not null | |

Dedup: UQ parcial `(produto_id, rede_avaliacao_id) WHERE rede_avaliacao_id IS NOT NULL`; UQ parcial
`(produto_id, autor_hash, texto_hash, coalesce(data_avaliacao, '0001-01-01')) WHERE rede_avaliacao_id IS
NULL`. `ix_mercado_avaliacoes_produto (produto_id, data_avaliacao desc)`. Trigger `mercado_so_insercao`.
Avaliação sem texto ou sem nota é aceita (Edge).

### `mercado_produto_videos` (vídeos top que promovem o produto; **só inserção**, uma linha por dia visto)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `produto_id` | uuid not null FK → mercado_produtos.id | |
| `rede`, `mercado` | | |
| `rede_video_id` | text not null | |
| `autor_handle` | text not null | o @ público do criador (FR-011); **nunca** nome de exibição, foto ou bio |
| `views`, `likes` | bigint null | contadores no dia |
| `comentarios`, `compartilhamentos` | bigint null | quando a página expõe |
| `legenda` | text null | |
| `publicado_em` | timestamptz null | |
| `data_local` | date not null | dia da observação (série de contadores; a 027 estende) |
| `posicao` | smallint null | posição na lista "vídeos top" |
| `campos` | jsonb not null default '{}' | duração, produto marcado etc. (sem PII) |
| `esquema_versao`, `bruto_ref` | | |
| `coleta_id` | uuid not null FK | |
| `coletado_em` | timestamptz not null | |

UQ `(produto_id, rede_video_id, data_local)`; `ix_mercado_videos_produto (produto_id, data_local desc,
views desc)`; `ix_mercado_videos_rede (rede, mercado, rede_video_id)` (a 027 liga `mercado_videos` por
aqui). Trigger `mercado_so_insercao`.

## Operação da coleta

### `mercado_fila` (tarefa; nunca apagada)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | o `tarefaId` do protocolo |
| `tipo` | text not null | CHECK `mercado_fila_tipo` (inclui os reservados da 027) |
| `rede`, `mercado` | | |
| `fonte` | text not null | CHECK `pagina_publica | affiliate | ambas` |
| `chave` | text not null | idempotência: `produto:<rede_produto_id>`, `ranking:<categoria|geral>:<tipo>:<janela>`, `categorias`, `vitrine`, `loja:<rede_loja_id>`, `avaliacoes:<rede_produto_id>:<pagina>`, `produto_videos:<rede_produto_id>` |
| `url` | text not null | a única URL que o coletor pode abrir para esta tarefa (FR-023); canônica, sem parâmetros pessoais |
| `nivel` | smallint not null | CHECK 1..8, a prioridade de FR-026: 1 manual e vitrine · 2 novos de lojas seguidas · 3 rankings das categorias · 4 quentes · 5 semanais (mornas) · 6 lojas e categorias · 7 vídeos · 8 avaliações |
| `prioridade` | int not null | ordem dentro do nível depois do revezamento (menor = primeiro); itens que sobraram do dia anterior e `imagens_pendentes` ganham prioridade 0 |
| `perfil_id` | uuid null FK → perfis.id | **operacional**: o perfil cuja vez trouxe a tarefa (revezamento); nulo nas tarefas sem perfil (vitrine, categorias, lojas globais). **Não é dono do dado** e não filtra leitura; exceção nominal do guarda de neutralidade |
| `produto_id`, `loja_id`, `categoria_id` | uuid null FK | o alvo, conforme o tipo |
| `data_local` | date not null | o dia da fila (fuso do mercado) |
| `turno` | `mercado_turno` null | só nas tarefas de produto com `fotos_por_dia = 2` |
| `estado` | `mercado_fila_estado` not null default `pendente` | ver Estados |
| `reservada_ate` | timestamptz null | lease (`FILA_LEASE_MIN = 30`); vencido → volta a `pendente` (trilha) |
| `cliente_id` | uuid null FK → coleta_clientes.id | quem reservou |
| `coleta_id` | uuid null FK → mercado_coletas.id | a rodada que entregou o resultado |
| `tentativas` | smallint not null default 0 | reservas vencidas + itens `erro`; `FILA_TENTATIVAS_MAX = 3` → `falhou` |
| `resultado_status` | `mercado_coleta_item_status` null | do item que fechou a tarefa |
| `erro_codigo` | text null | |
| `criada_em`, `recebida_em` | timestamptz | |
| `extra` | jsonb not null default '{}' | parâmetros da tarefa: `paginas` (avaliações), `baixarImagens` (bool), `imagensMax`, `rankingTipo`, `janela` |

Restrições e índices: UQ parcial `(tipo, chave, data_local, turno) NULLS NOT DISTINCT WHERE estado IN
('pendente', 'reservada')` (a trilha é idempotente); `ix_mercado_fila_entrega (estado, data_local, nivel,
prioridade) WHERE estado = 'pendente'`; `ix_mercado_fila_lease (reservada_ate) WHERE estado =
'reservada'`; `ix_mercado_fila_produto (produto_id, data_local desc)`. Estado de job: UPDATE só em
`estado`, `reservada_ate`, `cliente_id`, `coleta_id`, `tentativas`, `resultado_status`, `erro_codigo`,
`recebida_em`. Linhas de dias passados ficam para sempre (`expirada`, `recebida`, `falhou`).

### `mercado_coletas` (rodada do coletor)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `cliente_id` | uuid not null FK → coleta_clientes.id | |
| `rede`, `mercado` | | copiados do cliente |
| `iniciada_em` | timestamptz not null | |
| `batimento_em` | timestamptz not null | último `POST …/batimento` ou `…/itens`; sem batimento há `COLETA_SEM_BATIMENTO_MIN = 10` → `interrompida` (trilha) |
| `terminada_em` | timestamptz null | em todo estado final |
| `estado` | `mercado_coleta_estado` not null default `ativa` | |
| `tarefa_atual_id` | uuid null FK → mercado_fila.id | do batimento |
| `paginas`, `imagens` | int not null default 0 | contagem da rodada |
| `itens_ok`, `itens_erro`, `itens_repetidos` | int not null default 0 | |
| `versao_coletor` | text not null | semver do `sociman_coletor` |
| `chrome_versao` | text null | |
| `protocolo` | smallint not null | `1` |
| `resumo` | jsonb not null default '{}' | no fim: `{motivo, duracaoS, porTipo: {produto: n…}}` |

UQ parcial `(cliente_id) WHERE estado IN ('ativa', 'pausada_captcha', 'pausada_login')` (uma rodada aberta
por cliente: o 2º coletor com o mesmo token recebe 409 `coleta_em_andamento`); `ix_mercado_coletas_cliente
(cliente_id, iniciada_em desc)`. Estado de job (UPDATE de estado e contadores). CHECK `estado IN
('ativa','pausada_captcha','pausada_login') OR terminada_em IS NOT NULL`.

### `mercado_coleta_itens` (**só inserção**: um por item recebido, inclusive repetidos e inválidos)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `coleta_id` | uuid not null FK → mercado_coletas.id | |
| `tarefa_id` | uuid null FK → mercado_fila.id | nulo quando o `tarefaId` não existe (item `invalido`) |
| `tipo` | text not null | CHECK `mercado_fila_tipo` |
| `fonte` | `mercado_fonte` null | |
| `status` | `mercado_coleta_item_status` not null | |
| `erro_codigo` | text null | `tarefa_desconhecida`, `tarefa_de_outro_cliente`, `campos_invalidos`, `bruto_pessoal`, `bruto_grande`, `esquema_desconhecido`, `url_divergente`, `imagem_invalida`, `hd_indisponivel` |
| `erro_campo` | text null | o campo do erro de validação |
| `duracao_ms` | int null | medida pelo coletor (navegação) |
| `recebido_em` | timestamptz not null default now() | |
| `coletado_em` | timestamptz not null | do item |
| `data_local`, `turno` | date not null, `mercado_turno` null | o que o servidor decidiu |
| `esquema_versao` | text null | |
| `bruto_ref` | text null | |
| `bruto_bytes` | int null | gzip |
| `reprocessado_de` | bigint null FK → mercado_coleta_itens.id | item original, no `reprocessar --desde` |

`ix_mercado_coleta_itens_coleta (coleta_id, recebido_em)`; `ix_mercado_coleta_itens_tarefa (tarefa_id)`.
Trigger `mercado_so_insercao`.

### `coleta_eventos` (**só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `tipo` | `coleta_evento_tipo` not null | |
| `cliente_id` | uuid not null FK → coleta_clientes.id | |
| `coleta_id` | uuid null FK → mercado_coletas.id | |
| `tarefa_id` | uuid null FK → mercado_fila.id | |
| `detalhe` | jsonb not null default '{}' | **sem PII**: `{codigoHttp, contagem, urlSemParametros, tipoTarefa, versaoColetor}`; o servidor recusa as chaves da lista de poda |
| `ocorreu_em` | timestamptz not null | do coletor |
| `recebido_em` | timestamptz not null default now() | |
| `notificacao_dedupe` | text null | a `dedupe_key` usada no sino (`coleta:<tipo>:<data_local>`), para auditoria |

`ix_coleta_eventos_recentes (recebido_em desc)`; `ix_coleta_eventos_coleta (coleta_id)`. Trigger
`mercado_so_insercao`. Efeito colateral no recebimento (no mesmo commit): a rodada muda de estado
(`captcha` → `pausada_captcha`, `login_perdido` → `pausada_login`, `parar_local`/`parado` →
`interrompida`, `bloqueio_suspeito`/`layout_mudou` → `abortada` + `coleta_config.pausada_ate = agora +
RECUO_BLOQUEIO_H`), e nasce a notificação para os donos ativos, **uma por tipo por dia local**
(`dedupe_key = coleta:<tipo>:<data_local>`; `retomou`, `iniciado` e `parado` não notificam).

## Interesse (por perfil; versionado)

### `mercado_interesses`

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid null FK → perfis.id | **nulo = todos os perfis** (só `origem = vitrine`); CHECK `(perfil_id IS NULL) = (origem = 'vitrine')`; imutável |
| `mercado_produto_id` | uuid not null FK → mercado_produtos.id | imutável |
| `origem` | `mercado_interesse_origem` not null | imutável |
| `situacao` | `mercado_interesse_situacao` not null default `ativo` | encerrar nunca apaga (FR-038) |
| `motivo` | jsonb not null default '{}' | por origem: `manual {url}`; `vitrine {rankingFotoId?}`; `ranking {rankingFotoId, posicao, categoriaId}`; `loja {lojaId, vistoEm}`; `categoria {categoriaId, vistoEm}`; `video {redeVideoId}` (027) |
| `nota` | text not null default '' | ≤ 2.000; livre, do humano |
| `produto_id` | uuid null FK → produtos.id (012) | preenchido pelo "Adotar no catálogo"; a FK só existe se a tabela `produtos` existir na hora da migration (ver Dependência 012) |
| `tema_id` | uuid null FK → aprendizado_temas.id (023) | gancho da 027/028; nulo aqui |
| `encerrado_em`, `pausado_em` | timestamptz null | informativos; a verdade é `situacao` |
| `version` | int not null | `history.py`, controle otimista |
| AuditMixin | | `created_by` nulo nos automáticos (autor `system:mercado`); `updated_by` = último humano |

Restrições e índices: UQ parcial `(coalesce(perfil_id, '00000000-0000-0000-0000-000000000000'::uuid), mercado_produto_id, origem) WHERE
situacao IN ('ativo', 'pausado')` (um acompanhamento vivo por perfil, produto e origem; um pausado ainda
ocupa a vaga, para ser retomado em vez de duplicado; 409 `interesse_duplicado`);
`ix_mercado_interesses_perfil (perfil_id, situacao, created_at desc)`; `ix_mercado_interesses_produto
(mercado_produto_id, situacao)`; `ix_mercado_interesses_auto_dia (perfil_id, created_at) WHERE origem IN
('ranking','loja','categoria')` (limite diário). `__versioned_fields__`: `situacao`, `nota`, `produto_id`,
`tema_id`. `__immutable_fields__`: `perfil_id`, `mercado_produto_id`, `origem`, `motivo`. `entity_type =
"mercado_interesse"`. Revert só dono humano; o revert não pode violar a UQ (409 `interesse_duplicado`).

### `mercado_perfil_config` (uma por perfil)

| Coluna | Tipo | Regras |
|---|---|---|
| `perfil_id` | uuid PK FK → perfis.id | |
| `mercado` | text not null default 'BR' | CHECK `^[A-Z]{2}$` |
| `categoria_ids` | uuid[] not null default '{}' | CHECK `cardinality(categoria_ids) <= 5` (`CATEGORIAS_MAX = 5`, FR-037); cada id precisa existir em `mercado_categorias` (service; 400 `categoria_desconhecida`) |
| `lojas_seguidas` | uuid[] not null default '{}' | ids de `mercado_lojas` (seguir/deixar de seguir, FR-039) |
| `max_relacionados_dia` | int not null default 10 | CHECK 0..50 (`MAX_RELACIONADOS_DIA`) |
| `avisar_novo_em_alta` | boolean not null default true | gancho da 028 (a notificação não existe nesta spec) |
| `version` | int not null | |
| AuditMixin | | |

Nasce na 1ª edição (sem linha = padrão: sem categorias, sem lojas, 10, true; `version 0` na resposta,
como o guia da 017). `__versioned_fields__`: `mercado`, `categoria_ids`, `lojas_seguidas`,
`max_relacionados_dia`, `avisar_novo_em_alta`. `entity_type = "mercado_perfil_config"`. Só o dono edita
(PUT e revert); seguir e deixar de seguir loja é de qualquer humano e grava versão com `details.loja`.

## Infra do dono (versionado)

### `coleta_clientes` (= `mcp_clientes` com prefixo `scol_`)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `nome`, `nome_normalizado` | text not null / UNIQUE | 1..60 (ex.: "desktop do dono") |
| `descricao` | text not null default '' | ≤ 300 |
| `rede` | `platform` not null default `tiktok` | |
| `mercado` | text not null | CHECK `^[A-Z]{2}$`; o mercado acompanha o cliente (outro país = outra conta e outro cliente) |
| `situacao` | `coleta_situacao` not null default `ativo` | `revogado` é final |
| `token_id` | text not null UNIQUE | os 8 caracteres base32 do `scol_<id8>_<seg43>` |
| `token_hash` | bytea not null | SHA-256 do token inteiro; **nunca** sai do banco nem entra no histórico |
| `token_emitido_em` | timestamptz not null | |
| `expira_em` | timestamptz null | |
| `limite_por_minuto` | int not null default 120 | CHECK 1..600 (portão, Redis) |
| `ultimo_contato_em` | timestamptz null | qualquer rota do coletor (estado da tela) |
| `versao_coletor` | text null | do último contato |
| `chrome_versao` | text null | |
| `revogado_em`, `revogado_por` | timestamptz null, uuid null FK → users.id | |
| `version` | int not null | |
| AuditMixin | | |

`__versioned_fields__`: `nome`, `descricao`, `rede`, `mercado`, `situacao`, `expira_em`,
`limite_por_minuto`, `token_id` (a rotação aparece no diff pelo `token_id`, nunca pelo hash).
`entity_type = "coleta_cliente"`. `__repr__` sem o hash. `check:secrets` ganha o padrão
`scol_[a-z2-7]{8}_[A-Za-z0-9_-]{43}`.

### `coleta_config` (linha única)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | smallint PK | CHECK `id = 1` |
| `habilitada` | boolean not null default false | o botão da tela; o outro nível é `COLETA_HABILITADA` do `.env` |
| `risco_aceito_em` | timestamptz null | o aceite (FR-034) |
| `risco_aceito_por` | uuid null FK → users.id | |
| `risco_texto_versao` | text null | a versão do texto de `docs/decisoes/coleta-mercado.md` que foi aceita (ex.: `2026-10-08`) |
| `janela_inicio`, `janela_fim` | smallint not null default 8 / 23 | horas locais do mercado; CHECK 0..23 e `janela_inicio < janela_fim` |
| `paginas_dia` | int not null default 300 | CHECK 1..2000 |
| `imagens_dia` | int not null default 1500 | CHECK 0..20000 |
| `imagens_por_produto` | smallint not null default 9 | CHECK 0..20 |
| `itens_por_coleta` | smallint not null default 40 | CHECK 1..50 (teto da fila entregue por pedido) |
| `pausa_min_s`, `pausa_max_s` | smallint not null default 5 / 40 | CHECK `1 <= pausa_min_s <= pausa_max_s <= 600` |
| `pausada_ate` | timestamptz null | "Pausar N horas" e o recuo de 24 h de bloqueio/layout |
| `continuar_em` | timestamptz null | o clique "Continuar" (FR-018); o coletor retoma em `continuar_em + CAPTCHA_ESFRIAR_MIN` |
| `version` | int not null | |
| AuditMixin | | |

CHECK `ck_coleta_config_risco`: `NOT habilitada OR risco_aceito_em IS NOT NULL` (409 `risco_nao_aceito`
antes de chegar ao banco). `__versioned_fields__`: tudo menos `id`, `version`, auditoria (o aceite e o
"Continuar" entram no histórico). `entity_type = "coleta_config"`. Só dono humano escreve
(`RequireHumanOwner`); a linha nasce no primeiro PUT ou aceite (sem linha = padrões, `version 0`).

## Fora dos pacotes

### `produtos` (012): uma coluna, **dependência**
| Coluna | Tipo | Regras |
|---|---|---|
| `mercado_produto_id` | uuid null FK → mercado_produtos.id | o produto de mercado de origem ("Adotar no catálogo", FR-055); entra em `__versioned_fields__` da 012 |

A 012 é implementada em outra sessão (migration `0022`). A `0025` **só adiciona a coluna e a FK se a
tabela `produtos` existir** (`inspector.has_table`); senão registra no log "012 ausente: a coluna
`produtos.mercado_produto_id` fica para a migration de ligação" e a tarefa correspondente fica para
depois do merge da 012 (a FK `mercado_interesses.produto_id` segue a mesma regra). O "Adotar" responde 409
`passo_indisponivel` enquanto a 012 não existir no banco.

### `notificacoes` (006): valores novos de `notificacao_tipo`
| Tipo | Quando | `dedupe_key` | Link |
|---|---|---|---|
| `coleta_captcha` | evento `captcha` | `coleta:captcha:<data_local>` | `/app/configuracoes/coleta` |
| `coleta_login` | evento `login_perdido` | `coleta:login_perdido:<data_local>` | idem |
| `coleta_bloqueio` | evento `bloqueio_suspeito` | `coleta:bloqueio_suspeito:<data_local>` | idem |
| `coleta_layout` | evento `layout_mudou` | `coleta:layout_mudou:<data_local>` | idem |
| `coleta_parada` | trilha: coleta ligada e sem item `gravado` há `COLETA_PARADA_H = 48` | `coleta:parada:<data_local>` | idem |
| `mercado_interesse_auto` | trilha: criou interesses automáticos para um perfil hoje | `mercado:auto:<perfil_id>:<data_local>` | `/app/perfis/<id>?aba=mercado` |

Todas para os donos ativos; uma por tipo por dia local (FR-031, FR-039).

### `entity_versions` e `security_events`
- `entity_type` novos: `mercado_interesse`, `mercado_perfil_config`, `coleta_cliente`, `coleta_config`.
  A versão do `produtos` (012) criada pelo "Adotar" leva `details.origem = "mercado_026"` e
  `details.mercadoProdutoId`.
- O ator **`coletor`** (`Actor(kind="coletor", coleta_cliente_id=…)`, sem `user`) **não versiona nada**:
  grava só fotos, fichas, imagens, itens, eventos e estado de job. `entity_versions` não ganha coluna.
- `security_events` ganha o `actor_kind = "coletor"` nos eventos `coleta_recusada` (portão: 401/403/426/
  429, com `details = {motivo, tokenId, rota}`) e `publicacao_recusada` (ator não humano em rota
  `RequireHuman*` das novas rotas, como na 015). Um evento `coleta_aceite_risco` registra o aceite.

### `storage.py`
`Bucket` ganha `"mercado"` (`s3_mercado_bucket`, padrão `sociman-mercado`), criado por
`ensure_buckets`. Nenhum delete novo. As imagens vão no bucket `imagens` com prefixo `mercado/`, para o
imgproxy servir por `/img` com as mesmas URLs assinadas das outras imagens.

## Estados

### Tarefa da fila
```text
(trilha) ──▶ pendente ──GET /fila (lease)──▶ reservada ──item gravado|repetido──▶ recebida
                ▲                               │  └──item erro|invalido (tentativas < 3)──▶ pendente (tentativas+1)
                │                               │  └──item erro|invalido (3ª)──────────────▶ falhou
                └──lease vencido (trilha)───────┘
pendente | reservada ──virou o dia sem resultado (trilha)──▶ expirada  (o que sobrou entra primeiro no dia seguinte, prioridade 0)
finais: recebida, falhou, expirada
```

### Rodada
```text
POST /coletas ──▶ ativa ──evento captcha──▶ pausada_captcha ──"Continuar" + esfriar──▶ ativa
                    │  ──evento login_perdido──▶ pausada_login ──"Continuar" + esfriar──▶ ativa
                    │  pausada_* sem "Continuar" em CAPTCHA_ESPERA_MAX_H ──▶ encerrada (resumo.motivo = "pausa_vencida")
                    │  ──POST /fim──▶ encerrada
                    │  ──evento parar_local | parado──▶ interrompida
                    │  ──sem batimento há 10 min (trilha)──▶ interrompida
                    └──evento bloqueio_suspeito | layout_mudou──▶ abortada (+ coleta_config.pausada_ate = +24 h)
finais: encerrada, interrompida, abortada
```
Ao fechar uma rodada em qualquer estado final, as tarefas `reservada` dela voltam a `pendente` na hora
(sem esperar o lease).

### Produto (calor)
```text
novo no lago ──▶ quente (fotos_por_dia = 2 se manual ou "novo em alta"; senão 1)
quente ──sem ranking há SAI_DO_RANKING_DIAS = 7 e sem interesse manual|vitrine ativo──▶ morna (1 foto por semana)
morna ──sem ranking e sem interesse ativo há ESFRIAR_DIAS = 30──▶ parada (proxima_coleta_em nulo)
morna | parada ──reaparece em ranking, ou ganha interesse ativo──▶ quente (no mesmo dia, SC-005)
manual e vitrine ativos: sempre quente (FR-040)
```

### Interesse
| De | Para | Quem | Histórico |
|---|---|---|---|
| — | `ativo` | humano (manual, por link ou "Acompanhar neste perfil"), `system:mercado` (vitrine, ranking, loja, categoria), "Adotar" (manual se não existia) | `created` |
| `ativo` | `pausado` | humano (dono ou membro) | `updated` |
| `pausado` | `ativo` | humano | `updated` |
| `ativo` / `pausado` | `encerrado` | humano | `updated` (final para a UQ; um novo interesse pode nascer depois) |
| qualquer | versão anterior | dono humano (revert) | `reverted` |

## Regras derivadas (sem coluna)

- **Dia e turno da foto:** `data_local = coletado_em` convertido ao fuso do mercado (`mercados.py`);
  `turno = manha` se a hora local < `TURNO_CORTE = "15:30"`, senão `noite`. Decididos pelo servidor
  (Edge "meia-noite" e "relógio errado").
- **Interesse efetivo de um produto:** ativo se existe `mercado_interesses` em `ativo` para o produto
  (qualquer perfil, ou `perfil_id` nulo). "Manual ou vitrine ativo" é o que impede esfriar.
- **Cadência** (`mercado/cadencia.py`, puro): entradas = calor, `fotos_por_dia`, `ultima_foto_em`,
  `ultimo_ranking_em`, interesses, "novo em alta" (do `calculo.py`); saída = `calor`, `fotos_por_dia`,
  `proxima_coleta_em`. Avaliações: 1ª visita com `AVALIACOES_PAGINAS_1A_VISITA = 2` páginas, depois a cada
  `AVALIACOES_CADA_DIAS = 30`; vídeos a cada `VIDEOS_CADA_DIAS = 7` (1 página); só em `quente` (FR-040a).
- **Fila do dia** (`mercado/fila.py`, calculada na trilha e materializada em `mercado_fila` por
  idempotência): para cada nível de FR-026, as tarefas candidatas são agrupadas por perfil (as sem perfil
  formam o "perfil" nulo) em ordem fixa (`perfis.created_at`, nulo por último) e intercaladas um a um
  (**revezamento**, Clarification 2); um produto de interesse de vários perfis entra uma vez, pelo
  primeiro perfil cuja vez chegar. O orçamento (`paginas_dia − páginas já gravadas hoje`) corta a lista;
  o que sobra não vira linha (nasce no dia seguinte com prioridade 0). Rankings: uma tarefa por
  categoria da união das categorias dos perfis ativos, por tipo e janela, por dia (FR-037;
  `RANKING_ACOMPANHAR_TOP = 30` itens viram interesses `ranking`).
- **Relacionados automáticos** (trilha, autor `system:mercado`): produtos com `primeira_vez_em` há até
  `NOVO_DIAS = 30` de lojas em `lojas_seguidas` ou de categorias em `categoria_ids`, até
  `max_relacionados_dia` por perfil por dia local; uma notificação `mercado_interesse_auto` por perfil por
  dia.
- **Orçamento de hoje:** `paginas_hoje = count(mercado_coleta_itens WHERE data_local = hoje AND status IN
  ('gravado','repetido','erro'))`; `imagens_hoje = count(mercado_imagens … created_at hoje local)`; nunca
  gravados como totais.
- **Estado do cliente/rodada para a tela e para `GET /api/integracoes`:** calculado na hora (último
  contato, rodada aberta, páginas e imagens de hoje, `desligada_no_servidor` quando `COLETA_HABILITADA`
  é falso), nunca gravado.
- **Cálculo na leitura** (`mercado/calculo.py`, puro; constantes em `mercado/constantes.py`; nenhuma
  tabela agregada, GETs não gravam): todo número sai como `{valor, estimado, motivos[],
  amostraPequena, nFotos}`.
  - `v(d)` = `vendidos` da última foto com `data_local ≤ d` (fonte `affiliate` com `vendas_7d/30d` tem
    precedência quando a janela coincide; `pagina_publica` é reserva). **Vendas no período** =
    `max(0, v(ate) − v(de − 1))`; negativo → 0 com `inconsistente` (FR-044). Faixa (`vendidos_exato =
    false`) usa o ponto médio e carrega `incerteza` com `{min, max}`.
  - **Vendas/dia** exige `MIN_FOTOS_VENDAS = 2` fotos com `MIN_DIAS_ENTRE_FOTOS = 1` dia de distância;
    senão nulo e estado `coletando`. Menos de 7 dias de fotos → `amostraPequena` (estado
    `amostra_pequena`); senão `ok`.
  - **GMV no período** = Σ (Δvendidos entre fotos consecutivas × `preco_min_centavos` vigente no início
    do par), com `{min, max}` quando há faixa de preço (FR-045).
  - **Crescimento** = vendas/dia dos últimos 7 d ÷ vendas/dia dos 7 d anteriores − 1; base <
    `MIN_VENDAS_DIA_BASE = 3` → nulo (FR-046). **Vendas totais** = `v(ate)`; **GMV total** = vendas
    totais × preço atual, motivo `grosseiro`.
  - **Comissão por venda** = preço × `comissao_bp / 10000` (motivo `cupons_nao_descontados`);
    **retorno/dia** = vendas/dia × comissão por venda; **retorno por afiliado** = retorno/dia ÷
    (`n_criadores` + `K_AFILIADOS = 5`); **saturação** = `n_criadores` ÷ vendas/dia. Sem foto
    `affiliate` → `semDadoAfiliado` (FR-047).
  - **Alto retorno com poucos afiliados:** `comissao_bp ≥ COMISSAO_MIN_BP = 500`, foto `affiliate` com até
    `AC_FOTO_MAX_DIAS = 3` dias, e, na categoria com ≥ `MIN_PRODUTOS_CATEGORIA = 10` produtos
    comparáveis, `n_criadores` ≤ P25 e retorno por afiliado ≥ P75; sem amostra, `n_criadores ≤
    POUCOS_AFILIADOS = 50` e retorno ≥ mediana global.
  - **Novo em alta:** `primeira_vez_em` há ≤ `NOVO_DIAS = 30` **e** vendas/dia ≥ `NOVO_VENDAS_DIA_MIN =
    10` **e** (crescimento ≥ `NOVO_CRESCIMENTO_MIN = 0.5` **ou** item de ranking `em_alta | novos` nos
    últimos 7 d **ou** subiu ≥ `ALTA_POSICOES = 10` posições em 7 d), com estado `ok` (FR-048).
  - **Loja:** GMV estimado = Σ GMV dos produtos acompanhados; concentração = GMV do nº 1 ÷ total; ritmo
    de lançamentos = produtos com `primeira_vez_em` nos últimos 30 d; comissão média (FR-049).
    **Categoria:** medianas de comissão e preço, nº de "novos em alta", espaço em branco = subcategoria
    com vendas crescendo e mediana de criadores ≤ P25. **Ranking:** posição atual, melhor posição, dias no
    topo (≤ 10), variação em 7 d, `entrou`/`saiu`/`subiu`/`caiu`/`novo`.
  - Constantes operacionais, no mesmo arquivo: `QUENTE_DIAS = 1`, `SAI_DO_RANKING_DIAS = 7`,
    `ESFRIAR_DIAS = 30`, `RANKING_ACOMPANHAR_TOP = 30`, `MAX_RELACIONADOS_DIA = 10`,
    `AVALIACOES_CADA_DIAS = 30`, `AVALIACOES_PAGINAS_1A_VISITA = 2`, `VIDEOS_CADA_DIAS = 7`,
    `CAPTCHA_ESFRIAR_MIN = 60`, `CAPTCHA_ESPERA_MAX_H = 2`, `PARSES_VAZIOS_MAX = 5`, `RECUO_BLOQUEIO_H =
    24`, `TURNO_CORTE = "15:30"`, `CATEGORIAS_MAX = 5`, `FILA_LEASE_MIN = 30`, `FILA_TENTATIVAS_MAX = 3`,
    `COLETA_SEM_BATIMENTO_MIN = 10`, `COLETA_PARADA_H = 48`, `PERIODO_PADRAO_DIAS = 30`,
    `PERIODO_MAX_DIAS = 400`, `CATEGORIAS_CADA_DIAS = 7` (tarefa de página `categorias`, FR-008).
- **Desempenho** (FR-050, SC-007): `test_mercado_desempenho.py` semeia 10× (300 fotos/dia × 365 × 10 ≈ 1,1
  M de fotos) por SQL em lote e exige < 2 s por rota; a série por produto lê pelo índice
  `ix_mercado_fotos_serie`, e as listas agregam só a última foto por produto no período (`DISTINCT ON`).

## Migração `0025_mercado_shop`
1. `CREATE TYPE` `mercado_calor`, `mercado_turno`, `mercado_fonte`, `mercado_ranking_tipo`,
   `mercado_fila_estado`, `mercado_coleta_estado`, `mercado_coleta_item_status`, `coleta_evento_tipo`,
   `mercado_interesse_origem`, `mercado_interesse_situacao`, `coleta_situacao`; `ALTER TYPE
   notificacao_tipo ADD VALUE IF NOT EXISTS` para os 6 tipos (em `autocommit_block`, como a 0011);
2. infra do dono: `coleta_clientes`, `coleta_config`;
3. lago, na ordem das FKs: `mercado_categorias`, `mercado_lojas`, `mercado_coletas` (precisa de
   `coleta_clientes`), `mercado_produtos` (sem a FK `ficha_atual_id`), `mercado_produto_fichas`,
   `ALTER TABLE mercado_produtos ADD CONSTRAINT fk_mercado_produtos_ficha_atual …` (`use_alter`),
   `mercado_imagens`, `mercado_produto_imagens`, `mercado_produto_fotos`, `mercado_loja_fotos`,
   `mercado_ranking_fotos`, `mercado_ranking_foto_itens`, `mercado_avaliacoes`, `mercado_produto_videos`;
4. operação: `mercado_fila`, `mercado_coleta_itens`, `coleta_eventos`; e `ALTER TABLE mercado_coletas
   ADD CONSTRAINT fk_mercado_coletas_tarefa_atual …` (ciclo fila ↔ coletas, `use_alter`);
5. interesse: `mercado_interesses` (a FK `produto_id` → `produtos` **só se `has_table("produtos")`**;
   `tema_id` → `aprendizado_temas`), `mercado_perfil_config`;
6. índices e CHECKs; trigger `mercado_so_insercao` (`BEFORE UPDATE OR DELETE … FOR EACH ROW EXECUTE
   FUNCTION metricas_recusa_mudanca()`, função já criada pela 0011) nas 11 tabelas só de inserção:
   `mercado_loja_fotos`, `mercado_produto_fichas`, `mercado_imagens`, `mercado_produto_imagens`,
   `mercado_produto_fotos`, `mercado_ranking_fotos`, `mercado_ranking_foto_itens`, `mercado_avaliacoes`,
   `mercado_produto_videos`, `mercado_coleta_itens`, `coleta_eventos`;
7. `produtos.mercado_produto_id` + FK + índice parcial, **só se `has_table("produtos")`**;
8. **Downgrade** (só dev): recusa se existir linha em `mercado_produtos`, `mercado_coletas` ou
   `coleta_clientes`; senão remove na ordem inversa (coluna da 012 se existir, triggers, tabelas, tipos;
   os 6 avisos novos saem de `notificacoes` e o `notificacao_tipo` é recriado sem eles, padrão da 0011).
   Nenhum objeto do MinIO é tocado.

`test_migration_0025` cobre upgrade, downgrade vazio, recusa do downgrade com dados e os dois caminhos
da coluna da 012 (com e sem a tabela `produtos`).
