# Modelo de dados: 016-metricas-tiktok

Tudo fica no PostgreSQL (NVMe), na migration **`0011_metricas_tiktok`** (down_revision
**`0010_publicacao_tiktok`**). Nada vai para o MinIO: a exportação só usa temporário no HD
(research R16).
- **As tabelas `metricas_*` são observações da rede**, escritas pela trilha `metricas`
  (`system:metricas`) e, no vínculo manual, pelas rotas **H**. Não têm `version`/`history`
  próprios (exceção justificada no plan, princípio VII). O histórico do vínculo fica no
  **destino** (`entity_type = "postagem"`), e o da anonimização fica na **conexão**
  (`entity_type = "conexao"`).
- As fotos são **só de inserção**, com trigger no banco (research R7).
- `actor_kind` novo: **`system:metricas`**.
- Pacote novo: `apps/api/src/sociman_api/metricas/` (plan, Project Structure).

## Enum novo: `vinculo_metodo`
`envio` (post id do `status/fetch` ou do post direto da 015) · `casamento` (lista: data,
duração e legenda) · `link` (link colado pelo dono) · `escolha` (o dono escolheu um candidato).

## `metricas_series` (nova)
As métricas de uma conta do SociMan numa rede, enquanto ela está conectada. Anonimizar encerra a
série, e reconectar depois cria outra.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `rede` | enum `platform` (da 003) | `tiktok` na 016 |
| `conta_id` | uuid null FK → contas.id | `NULL` só depois de anonimizada |
| `rotulo` | text null | `"Conta anônima N"` depois de anonimizada |
| `anonima_n` | int null | o N do rótulo (sequência `metricas_anonima_seq`) |
| `criada_em` | timestamptz not null default now() | |
| `varredura_cursor` | bigint null | o `cursor` (ms) da varredura completa em andamento (R5) |
| `varredura_concluida_em` | timestamptz null | |
| `lista_proxima_em` | timestamptz null | a próxima 1ª página do `video/list` (a cada hora) |
| `conta_proxima_em` | timestamptz null | a próxima janela da foto da conta (R6) |
| `ultima_coleta_em` | timestamptz null | o último pedido com sucesso |
| `ultimo_erro_codigo` | text null | o código cru (`scope_not_authorized`, `rate_limit_exceeded`, `rede_indisponivel`, …) |
| `ultimo_erro_motivo` | text null | pt-BR |
| `ultimo_erro_em` | timestamptz null | |
| `adiar_ate` | timestamptz null | recuo depois de erro ou taxa (R3) |
| `sem_permissao_desde` | timestamptz null | `scope_not_authorized` em uso (R1); é limpo ao ampliar os escopos |
| `anonimizada_em` | timestamptz null | |
| `anonimizada_por` | uuid null FK → users.id | o dono humano que desconectou |

Regras:
- `ck_metricas_series_anonima`: `(anonimizada_em IS NULL) = (conta_id IS NOT NULL)`, e
  `anonimizada_em IS NULL OR (rotulo IS NOT NULL AND anonima_n IS NOT NULL)`;
- `uq_metricas_series_conta_viva (conta_id) WHERE anonimizada_em IS NULL`: uma série viva por
  conta;
- `ix_metricas_series_ativas (lista_proxima_em) WHERE anonimizada_em IS NULL`;
- sequência `metricas_anonima_seq`.

**Série ativa** (derivado): `anonimizada_em IS NULL`, a conta com conexão `conectada`,
`metricas_liberadas(conexao)`, `sem_permissao_desde IS NULL` e `METRICAS_COLETA_HABILITADA`.

## `metricas_videos` (nova)
Um post público de uma série. A linha é criada pela descoberta (`video/list`), pelo nível 1 do
vínculo (`video/query` do post id) ou pelo link colado.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | é o `video_ref` do dataset |
| `serie_id` | uuid not null FK → metricas_series.id | |
| `rede_video_id` | text null | o `id` da TikTok como texto (pode passar de 2^53); `NULL` depois de anonimizado |
| `share_url` | text null | o link do post; `NULL` depois de anonimizado |
| `legenda` | text null | `video_description` (a última vista); `NULL` depois de anonimizado |
| `titulo` | text null | `title`; `NULL` depois de anonimizado |
| `duracao_s` | int not null | `duration` (s, inteiro) |
| `largura`, `altura` | int null | |
| `publicado_em` | timestamptz not null | `create_time`; truncado para a hora ao anonimizar |
| `descoberto_em` | timestamptz not null default now() | |
| `disponivel` | boolean not null default true | false quando o `video/query` não o devolve (R5) |
| `indisponivel_desde` | timestamptz null | |
| `proxima_coleta_em` | timestamptz null | a fila (R4); `NULL` = parou (mais de 365 d ou anonimizado) |
| `ultima_foto_em` | timestamptz null | |
| `destino_id` | uuid null FK → postagens.id | o vínculo vivo |
| `vinculo_metodo` | enum `vinculo_metodo` null | |
| `vinculado_por` | uuid null FK → users.id | `NULL` quando foi automático (`system:metricas`) |
| `vinculado_em` | timestamptz null | |
| `vinculo_automatico` | boolean not null default true | false depois que o dono desfaz (R11): não se liga mais sozinho |
| `features` | jsonb null | características **congeladas** na anonimização (R13); `NULL` antes dela |
| `anonimizado_em` | timestamptz null | igual ao da série (facilita os filtros) |

Regras:
- `uq_metricas_videos_rede_id (serie_id, rede_video_id) WHERE rede_video_id IS NOT NULL`;
- `uq_metricas_videos_destino (destino_id) WHERE destino_id IS NOT NULL`: um vídeo por
  destino;
- `ck_metricas_videos_vinculo`: `(destino_id IS NULL) = (vinculo_metodo IS NULL)` e
  `destino_id IS NULL OR vinculado_em IS NOT NULL`;
- `ck_metricas_videos_anonimo`: `anonimizado_em IS NULL OR (rede_video_id IS NULL AND share_url
  IS NULL AND legenda IS NULL AND titulo IS NULL AND destino_id IS NULL AND vinculado_por IS
  NULL AND proxima_coleta_em IS NULL AND features IS NOT NULL)`;
- `ck_metricas_videos_indisponivel`: `disponivel OR indisponivel_desde IS NOT NULL`;
- `ix_metricas_videos_fila (proxima_coleta_em) WHERE proxima_coleta_em IS NOT NULL`;
- `ix_metricas_videos_serie_pub (serie_id, publicado_em DESC, id DESC)` (ranking e casamento);
- o vínculo só pode ligar a um destino **da mesma conta** da série. Um CHECK não cruza tabelas,
  então isso é conferido no service, com teste.

**`features`** (congeladas, sem texto identificador; decisão do dono, Q1 = A), com as chaves:
- `origem` (`corte`, `video_proprio` ou `fora`) e `modo_envio` (`lembrete`, `criar_rascunho`,
  `publicar` ou null);
- `vinculo_metodo` e `score` (int ou null);
- `canal_status_direito` (`proprio`, `parceiro`, `programa_de_cortes`, `sem_acordo` ou null);
- `duracao_s`, `hora_local` e `dia_semana` (0 = segunda);
- `intervalo_post_anterior_h` e `seguidores_na_publicacao`;
- `gancho_caracteres` e `hashtags_n`.

## `metricas_video_fotos` (nova, **só inserção**)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `video_id` | uuid not null FK → metricas_videos.id | |
| `coletado_em` | timestamptz not null | o momento exato da resposta |
| `idade_s` | int not null | `coletado_em − publicado_em` real (≥ 0) |
| `alvo_idade_min` | int not null | a janela da agenda (R4); na foto de descoberta, `floor(idade_min)` ou o alvo cuja tolerância contém a idade (R5). Um vídeo com mais de 365 d na descoberta fica só com essa foto (Q2 = A) |
| `views` | bigint null | `view_count` |
| `likes` | bigint null | `like_count` |
| `comments` | bigint null | `comment_count` |
| `shares` | bigint null | `share_count` |
| `fonte` | text not null default `'display'` | `display` (a 016); `business` fica reservado para a etapa 2 |

Regras:
- `uq_metricas_video_fotos_janela (video_id, alvo_idade_min)`: uma foto por vídeo por janela
  (`ON CONFLICT DO NOTHING`);
- `ix_metricas_video_fotos_idade (video_id, idade_s)`: curvas e `LATERAL` dos marcos (R15);
- `ix_metricas_video_fotos_coletado (coletado_em)`: exportação por período;
- `ck_metricas_video_fotos_idade`: `idade_s >= 0 AND alvo_idade_min >= 0`;
- `ck_metricas_video_fotos_fonte`: `fonte IN ('display','business')`;
- os contadores ficam `NULL` quando a TikTok omite o campo, e são gravados como vieram,
  inclusive quando caem;
- **trigger `metricas_so_insercao`** (`BEFORE UPDATE OR DELETE ... FOR EACH ROW EXECUTE FUNCTION
  metricas_recusa_mudanca()`), que levanta `'metricas: fotos são só de inserção'`.

## `metricas_conta_fotos` (nova, **só inserção**)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `serie_id` | uuid not null FK → metricas_series.id | |
| `coletado_em` | timestamptz not null | |
| `janela_em` | timestamptz not null | a hora cheia (modo horário) ou 00:00 de SP (diário), R6 |
| `seguidores` | bigint null | `follower_count` |
| `seguindo` | bigint null | `following_count` |
| `curtidas` | bigint null | `likes_count` |
| `videos` | bigint null | `video_count` (só os públicos) |

Regras:
- `uq_metricas_conta_fotos_janela (serie_id, janela_em)`;
- o mesmo trigger `metricas_so_insercao`.

## `metricas_buscas_post` (nova)
O nível 1 do vínculo (research R9): uma linha por destino `criar_rascunho` entregue.

| Coluna | Tipo | Regras |
|---|---|---|
| `destino_id` | uuid PK FK → postagens.id | |
| `tentativa_id` | uuid not null FK → publicacao_tentativas.id | a tentativa `entregue` (o `publish_id` fica lá e não é copiado) |
| `entregue_em` | timestamptz not null | `tentativa.concluida_em` |
| `proxima_em` | timestamptz null | `NULL` quando encerrada |
| `consultas` | int not null default 0 | |
| `ultimo_status` | text null | `SEND_TO_USER_INBOX`, `PUBLISH_COMPLETE`, `FAILED`, … |
| `post_id` | text null | `publicaly_available_post_id`; `NULL` depois de anonimizada |
| `encerrada_em` | timestamptz null | |
| `fim` | text null | `vinculado`, `prazo`, `falhou`, `desfeito`, `anonimizada` ou `cancelada` (o destino foi arquivado) |

Regras:
- `ck_metricas_buscas_fim`: `(encerrada_em IS NULL) = (fim IS NULL)` e `encerrada_em IS NULL
  OR proxima_em IS NULL`;
- `ck_metricas_buscas_fim_valor`: `fim IS NULL OR fim IN
  ('vinculado','prazo','falhou','desfeito','anonimizada','cancelada')`;
- `ix_metricas_buscas_fila (proxima_em) WHERE encerrada_em IS NULL`.

## Mudanças em tabelas existentes
| Tabela ou tipo | Mudança |
|---|---|
| `notificacao_tipo` | + `post_detectado` (rascunho virou post e foi vinculado) e `vinculo_a_confirmar` (casamento ambíguo), para os donos ativos, com `dedupe_key` por destino |
| `postagens` | **nenhuma coluna**. O vínculo mora em `metricas_videos.destino_id`. Estados novos: nenhum; as transições `rascunho_criado ↔ publicado` e `falhou → publicado` pelo vínculo ficam em `postagem/service.py::publicacao_pelo_vinculo` (R12) e respeitam os CHECKs da 0010 (`ck_postagens_execucao` já permite `publicado` fora do lembrete). Um lembrete ligado pelo dono antes do clique vai a `postado` pelo `marcar_postado` da 014 (R12); ligado depois do clique, não muda de estado. A âncora do lembrete é o `posted_at` que já existe (Q3 = A) |
| `conexoes` | nenhuma coluna; `details.acao` ganha `ampliada` e `metricas_anonimizadas` |

## Histórico (princípio VII)
| Evento | Onde | `details` |
|---|---|---|
| vínculo feito (auto ou dono) | `postagem`, `action = "updated"` (before/after com o estado) | `{acao: "vinculo_feito", metodo, automatico}`, **sem** id nem link da TikTok |
| vínculo desfeito | `postagem`, `"updated"` | `{acao: "vinculo_desfeito", metodo_anterior}` |
| escopos ampliados | `conexao`, `"updated"` | `{acao: "ampliada"}` (escopos no snapshot, como na 015) |
| métricas anonimizadas | `conexao`, `"updated"` | `{acao: "metricas_anonimizadas", videos, fotos}` |

A reversão genérica do destino **não** restaura o vínculo nem os estados de execução (regra da
015). Para refazer, o dono usa `POST /api/destinos/{id}/vinculo`.

## Estados e transições

### Série
```text
(conta com conexão conectada + escopos) ──1ª volta──► viva/coletando
viva ── scope_not_authorized ──► viva/sem_permissao ── reconectar (ampliada) ──► viva/coletando
viva ── conexão precisa_reconectar / METRICAS_COLETA_HABILITADA=false ──► viva/parada (derivado)
viva ── desconectar (dono, confirmoAnonimizar) ──► anonimizada   (final; reconectar cria outra)
```

### Vídeo
```text
descoberto ──► disponivel ──(não volta no query)──► indisponivel ──(volta)──► disponivel
qualquer ──(idade > 365 d)──► proxima_coleta_em = NULL (fotos ficam)
sem_vinculo ──nível 1/2/3──► vinculado ──desfazer (dono)──► sem_vinculo (vinculo_automatico=false)
qualquer ──anonimizar──► anonimo (final)
```

### Vínculo visto pelo destino (derivado, `GET /api/destinos/{id}/vinculo`)
| Estado | Quando |
|---|---|
| `vinculado` | existe `metricas_videos.destino_id = destino` |
| `buscando` | busca aberta (nível 1), ou lembrete `postado` há menos de 1 h sem vínculo (Q3 = A), e nenhum candidato ambíguo |
| `a_confirmar` | destino **com âncora** (R10) e 2 ou mais candidatos, ou candidato com legenda incompatível |
| `sem_vinculo` | nenhum dos anteriores (inclui busca encerrada por `prazo`/`desfeito`, destino bloqueado e vídeo de fora). Um lembrete em `aprovado`/`agendado` fica aqui, com `candidatos` preenchidos para o dono escolher (R11), sem aviso |
| `indisponivel` | a conta não tem série ativa (sem conexão, sem escopos ou coleta desligada) |

### Âncora do casamento e bloqueio (derivados, sem coluna nova; research R10, Q3 = A)
| Destino | Âncora | Janela de `publicado_em` do vídeo |
|---|---|---|
| `criar_rascunho` com busca (`rascunho_criado` ou `postado`) | `metricas_buscas_post.entregue_em` | `−5 min` a `+14 d` |
| `lembrete` em `postado` | `postagens.posted_at` (o clique "Marcar como postado") | `−24 h` a `+1 h` |
| `lembrete` em `aprovado`/`agendado` | nenhuma (só candidatos para o dono) | — |

- **Bloqueio do destino:** existe versão do destino com `details.acao = "vinculo_desfeito"`. O
  destino bloqueado só se liga pela ação do dono.
- O `posted_url` digitado no `marcar_postado` não é lido pela trilha.

## Migration `0011_metricas_tiktok`
**Upgrade:**
1. `CREATE TYPE vinculo_metodo`; `ALTER TYPE notificacao_tipo ADD VALUE IF NOT EXISTS`
   `'post_detectado'` e `'vinculo_a_confirmar'`;
2. `CREATE SEQUENCE metricas_anonima_seq`;
3. as 5 tabelas, com CHECKs e índices;
4. `CREATE FUNCTION metricas_recusa_mudanca() RETURNS trigger` (`RAISE EXCEPTION`) e os 2
   triggers.

Não há backfill: as séries nascem na 1ª volta da trilha depois da reconexão.

**Downgrade:**
1. `DROP TRIGGER`/`DROP FUNCTION`;
2. `DROP TABLE` das 5 tabelas, na ordem das FKs;
3. `DROP SEQUENCE` e `DROP TYPE vinculo_metodo`;
4. `notificacao_tipo` recriado sem os 2 valores, no padrão da 0007 e da 0010: os avisos
   desses tipos saem (`DELETE FROM notificacoes WHERE tipo::text IN (…)`, que é aviso
   efêmero, não domínio) e o tipo é recriado.

**`test_migration_0011`:**
- sobe sobre uma base da 0010 com conexões e destinos em todos os estados;
- confere cada CHECK com `INSERT`/`UPDATE` direto;
- o trigger recusa `UPDATE` e `DELETE` nas duas tabelas de fotos, e o `TRUNCATE` continua
  funcionando;
- desce e sobe de novo.
