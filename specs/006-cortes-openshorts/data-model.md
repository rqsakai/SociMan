# Modelo de dados: 006-cortes-openshorts

Tudo fica no PostgreSQL (NVMe), na migration `0006_cortes_openshorts` (down_revision `0005_assets`, da spec 007), e os arquivos ficam no
MinIO (HD), no bucket `sociman-videos`.
- As tabelas usam o `AuditMixin` da 001 e, quando versionadas, o `_Versioned` da 003
  (`version`, `archived_at`, `archived_by`).
- O histórico é o `entity_versions` da 003, com os novos `entity_type`: `canal`, `padroes_corte`,
  `envio` e `postagem`. O `corte` já existe.
- Mudanças feitas pelo sistema (sincronização, progresso, importação) são **estado de job**, sem
  versão, como na 004. A exceção é a criação do corte importado, que grava `created` com
  `actor_kind = system:agendador`.

## `canais_fonte`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `youtube_channel_id` | text not null UNIQUE | `^UC[0-9A-Za-z_-]{22}$` (conta também os arquivados; 409 `canal_exists`) |
| `handle` | text null | sem `@`, normalizado |
| `title` | text not null | do YouTube (atualizado pela sync) |
| `avatar_url` | text null | URL remota (servida via imgproxy, R13) |
| `subscribers` | bigint null | null = oculto |
| `video_count` | int null | do YouTube |
| `uploads_playlist_id` | text not null | `contentDetails.relatedPlaylists.uploads` |
| `direito` | enum `canal_direito` (`proprio`, `parceiro`, `programa_de_cortes`, `sem_acordo`) | padrão `sem_acordo`; **só o dono muda** |
| `direito_evidencia_url` | text null | http(s), até 500 |
| `direito_evidencia_nota` | text not null default '' | até 2.000 |
| `sync_status` | enum `canal_sync` (`pendente`, `sincronizando`, `ok`, `pausado_cota`, `erro`) | padrão `pendente` |
| `sync_progress` | jsonb not null default '{}' | `{lidos, total}` durante a 1ª sync |
| `sync_error` | text null | pt-BR, sem a chave |
| `full_synced_at` | timestamptz null | fim da 1ª sync completa |
| `last_synced_at` | timestamptz null | |
| `next_sync_at` | timestamptz not null default now() | agenda da trilha `sync` |
| `version`, `archived_at`, `archived_by`, AuditMixin | | como na 003 |

**Snapshot versionado:** `title`, `handle`, `direito`, `direito_evidencia_url`,
`direito_evidencia_nota`, `perfil_ids` (lista ordenada, vinda de `canal_perfis`) e `archived`.
- `title` e `handle` entram só para exibição (`__immutable_fields__`), e a reversão os ignora.
- Um canal arquivado sai da sync e da descoberta, mas os vídeos e envios ficam.
- Reverter só pelo dono, como na 003. Reverter o `direito` é, na prática, uma mudança de
  direito.

## `canal_perfis`
| Coluna | Tipo | Regras |
|---|---|---|
| `canal_id` | uuid FK → canais_fonte.id | PK composta |
| `perfil_id` | uuid FK → perfis.id | PK composta |
| `created_at`, `created_by` | | |

Ligar e desligar mudam o `perfil_ids` do snapshot do canal (versão `updated`). A reversão recria
as ligações.

## `videos_fonte`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `canal_id` | uuid not null FK → canais_fonte.id | |
| `youtube_video_id` | text not null UNIQUE | 11 caracteres |
| `title` | text not null | |
| `description` | text not null default '' | cortada em 5.000 |
| `thumbnail_url` | text null | `mqdefault` (320×180), remota |
| `published_at` | timestamptz not null | |
| `duration_s` | int null | de `contentDetails.duration` (ISO 8601) |
| `live` | enum `video_live` (`nenhum`, `ao_vivo`, `agendado`) | de `liveBroadcastContent` |
| `disponivel` | bool not null default true | false quando o `videos.list` não devolve mais o id |
| `views`, `likes`, `comments` | bigint null | última leitura (likes ou comentários ocultos = null) |
| `metrics_at` | timestamptz null | |
| `next_metrics_at` | timestamptz not null | por idade: +1 h (≤ 7 d), +24 h (≤ 60 d), +7 d |
| `vph_recente` | numeric(14,2) null | views/h entre as duas últimas leituras com ≥ 6 h de distância |
| `score` | numeric(5,1) not null default 0 | 0–100 (R3), sem o fator "já cortado" (que é por perfil) |
| `score_reason` | text not null default '' | motivo em uma linha |
| `score_detail` | jsonb not null default '{}' | `{v, e, r, d, componente, valores}` para o "Por quê?" |
| `recomendavel` | bool not null default false | false se indisponível, ao vivo ou agendado, < 45 s ou > 3 h |
| `first_seen_at` | timestamptz not null default now() | |

Índices:
- `(canal_id, published_at desc)`;
- `(recomendavel, score desc)`;
- `(next_metrics_at)` (trilha `sync`);
- `lower(title)` com `text_pattern_ops` não é necessário: busca com `ILIKE` em até cerca de 10 mil
  linhas.

Não é versionada: é espelho do YouTube, escrito só pelo sistema.

## `video_metricas`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `video_id` | uuid not null FK → videos_fonte.id | |
| `observed_at` | timestamptz not null | |
| `views`, `likes`, `comments` | bigint null | |

Índice `(video_id, observed_at desc)`. Só INSERT. Guarda o histórico de métricas (key entity
"métricas com histórico") e alimenta o `vph_recente`. Volume estimado: menos de 20 mil linhas por
mês com o orçamento de R2.

## `youtube_cota`
| Coluna | Tipo | Regras |
|---|---|---|
| `dia` | date PK | no fuso `America/Los_Angeles` (a cota zera à meia-noite do Pacífico) |
| `unidades` | int not null default 0 | somadas **antes** de cada chamada |
| `aviso_enviado` | bool not null default false | notificação de 80% (uma por dia) |

Limite em `YT_QUOTA_DAILY` (padrão 10.000):
- em 95%, a sync para, e os canais vão para `pausado_cota`;
- em 100%, o cadastro também recebe 429 `youtube_quota` ("A cota diária do YouTube acabou; volta
  às 04:00"), com o horário convertido para `APP_TZ`.

## `padroes_corte`
Um por perfil, preguiçoso (sem linha = padrão com `version: 0`, criado no primeiro salvar).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null UNIQUE FK → perfis.id | |
| `clip_min_s` | smallint not null | 5–175 |
| `clip_max_s` | smallint not null | 10–180, ≥ `clip_min_s` + 5 |
| `quantidade` | smallint null | 1–15; null = a IA decide |
| `layout` | text not null | `auto`, `none`, `split`, `screencast` ou `speaker_cut` |
| `formato` | text not null | `vertical` ou `square` |
| `legenda` | text not null | `kit`, `gerador` ou `nenhuma` |
| `marca_automatica` | bool not null | |
| `conta_padrao_id` | uuid null FK → contas.id | conta do perfil, não arquivada |
| `version`, AuditMixin | | |

O padrão é 15, 60, null, `auto`, `vertical`, `kit`, false, null. O snapshot versionado inclui
todos os campos acima.

## `envios`
A linha é a **seleção** e depois o **job no OpenShorts** (R4, R6).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | |
| `origem` | enum `envio_origem` (`canal`, `avulso_link`, `avulso_arquivo`) | |
| `video_fonte_id` | uuid null FK → videos_fonte.id | obrigatório em `canal` |
| `canal_fonte_id` | uuid null FK → canais_fonte.id | cópia do canal do vídeo (filtros e histórico) |
| `source_url` | text null | `canal`: `https://www.youtube.com/watch?v=<id>`; `avulso_link`: a URL colada (http/https, até 2.000) |
| `source_title` | text not null | título do vídeo, ou o dado pelo usuário no avulso (1..200) |
| `upload_key` | text null UNIQUE | `avulso_arquivo`: `envios/{id}/fonte.<ext>` no bucket `sociman-videos` |
| `upload_bytes`, `upload_duration_ms`, `upload_sha256` | | só em `avulso_arquivo` |
| `status` | enum `envio_status` (ver Estados) | padrão `selecionado` |
| `config` | jsonb null | padrões resolvidos no envio + `subtitle` (seção `openshorts.subtitle` do kit, se `legenda = kit`) + `kit_version`; null enquanto `selecionado` |
| `direito_no_envio` | enum `direito_envio` (`proprio`, `parceiro`, `programa_de_cortes`, `sem_acordo`, `avulso`) null | gravado ao enviar (princípio II) |
| `aviso_confirmado` | bool not null default false | true quando o aviso foi mostrado e confirmado |
| `force_low_quality` | bool not null default false | "Enviar mesmo assim" depois de `confirmar_qualidade` |
| `openshorts_job_id` | text null | |
| `openshorts_queue_pos` | smallint null | posição na fila do gerador |
| `progress` | smallint not null default 0 | 0..100: % geral **estimado e ponderado por etapa** (tabela abaixo) |
| `etapa` | text null | etapa real (migration `0007_envio_progresso`): `fila`, `baixando`, `transcrevendo`, `escolhendo_momentos`, `processando_clipes`, `legendas`, `importando`, `concluido`, `erro` (check) |
| `etapa_pct` | smallint null | 0..100: % da etapa, quando o OpenShorts o informa |
| `clipe_atual`, `clipes_previstos` | smallint null | "clipe N de M" na geração, na legenda e na importação |
| `etapa_mensagem` | text null | detalhe curto em pt-BR (ex.: "Transcrevendo o vídeo 25%", "Cortando clipe 3 de 9 (cenas 40%)"); o SPA junta com o % geral |
| `clips_total` | smallint null | clipes em `result.clips` |
| `clips_importados` | smallint not null default 0 | |
| `attempts` | smallint not null default 0 | tentativas de submissão ou importação |
| `next_attempt_at` | timestamptz null | backoff (fila da trilha) |
| `last_polled_at` | timestamptz null | |
| `error_code` | text null | `source_invalid`, `openshorts_lost`, `clips_expired`, `no_clips`, `internal`… |
| `error_message` | text null | pt-BR |
| `sent_at`, `started_at`, `finished_at` | timestamptz null | |
| `version`, `archived_at`, `archived_by`, AuditMixin | | `created_by` = quem selecionou; o autor do envio fica no histórico |

**Progresso por etapa** (`envios/progresso.py`, puro): a trilha `openshorts` lê `status`, `logs`,
`queue` e `partial` do `GET /api/status/{job}` a cada consulta e grava as colunas acima; a trilha
`importacao` grava `legendas` (durante o `/api/subtitle` do SociMan) e `importando`. Faixas do %
geral: fila 0; baixando 0–5; transcrevendo 5–35; escolhendo os momentos 35–40; gerando os clipes
40–90 (clipes prontos ÷ previstos); legendas e importação 90–100 (clipes importados ÷ total);
concluído 100. O % geral nunca volta dentro do mesmo job (só a volta para a fila zera). Linha
desconhecida mantém a última etapa reconhecida. Na API, `pronto` → `concluido`, `falhou` e
`sem_clipes` → `erro`, `na_fila`/`aguardando_openshorts` → `fila`; "enviar", "tentar de novo"
e "enviar mesmo assim" zeram as colunas.

Índices:
- `(status, next_attempt_at)` para as trilhas;
- `(perfil_id, created_at desc)`;
- `(perfil_id, video_fonte_id) WHERE archived_at IS NULL`, **não único** (o duplicado é
  permitido com confirmação), usado no "já cortado".

Checks:
- `origem = 'canal'` exige `video_fonte_id` e `source_url`;
- `origem = 'avulso_link'` exige `source_url`;
- `origem = 'avulso_arquivo'` exige `upload_key`;
- um status além de `selecionado` exige `config` e `direito_no_envio`.

**Snapshot versionado** (só ações humanas): `status`, `config`, `direito_no_envio`,
`aviso_confirmado`, `source_title`, `source_url`, `canal_fonte_id`, `video_fonte_id`, `origem` e
`archived`.
- A versão da ação **"enviar"** é o registro do princípio II: autor, data, fonte e direito no
  momento.
- `details` guarda `{duplicado: bool, canal_direito_atual}`.

## `cortes` (da 004, ampliada)
Colunas novas:

| Coluna | Tipo | Regras |
|---|---|---|
| `origem` | enum `corte_origem` (`upload`, `openshorts`) | padrão `upload` (linhas antigas) |
| `envio_id` | uuid null FK → envios.id | obrigatório em `openshorts` |
| `clip_index` | smallint null | UNIQUE `(envio_id, clip_index)`: importação idempotente |
| `source_start_ms`, `source_end_ms` | int null | trecho no vídeo de origem |
| `openshorts_title` | text null | `video_title_for_youtube_short` |
| `openshorts_description` | text null | `video_description_for_tiktok` |
| `openshorts_score` | smallint null | `predicted_score` |
| `transcript` | text null | palavras do clipe, até 4.000 caracteres (para o Claude) |
| `legenda` | text null | `kit`, `gerador`, `nenhuma` ou `sem_fala`: o que foi aplicado |
| `archived_at`, `archived_by` | | arquivar clipes ruins (FR-013) |

Mudanças:
- o enum `corte_status` ganha **`revisao`** (antes de `na_fila`);
- `kit_version` e `kit_tokens` passam a **anuláveis**, com o check `status = 'revisao' OR
  (kit_version IS NOT NULL AND kit_tokens IS NOT NULL)`;
- `hook_text` continua `not null`, mas aceita `''` em `revisao`. Ao aplicar a marca, vale a regra
  da 004 (1..120 e até 3 linhas, com o gancho ligado no kit).

O snapshot versionado passa a ser `hook_text`, `kit_version`, `status` e `archived`.
- Novas ações: `updated` ao editar o gancho e ao aplicar a marca; `archived` e `restored`.
- O worker, a fila e o `queue.claim` não mudam: continuam pegando só `na_fila`.

Índice novo: `(envio_id, clip_index)`.

## `postagens`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `corte_id` | uuid not null FK → cortes.id | |
| `conta_id` | uuid not null FK → contas.id | conta do mesmo perfil do corte, não arquivada; dá a plataforma |
| `titulo` | text not null default '' | até 100 |
| `descricao` | text not null default '' | até 2.000 |
| `hashtags` | text[] not null default '{}' | 0..8 ao salvar (3–8 só nas sugestões); cada uma `^#[\p{L}0-9_]{1,50}$` |
| `estado` | enum `postagem_estado` (`rascunho`, `agendado`, `postado`) | padrão `rascunho` |
| `planned_at` | timestamptz null | obrigatório em `agendado` |
| `lembrado_em` | timestamptz null | "Hora de postar" já enviada; zera ao remarcar |
| `posted_at` | timestamptz null | ao marcar `postado` |
| `posted_url` | text null | link do post (opcional, colado pelo dono) |
| `sugestao_id` | uuid null FK → sugestoes_texto.id | de onde vieram os textos |
| `version`, `archived_at`, `archived_by`, AuditMixin | | |

Regras:
- índice único parcial `(corte_id, conta_id) WHERE archived_at IS NULL` → 409 `postagem_exists`;
- `agendado` exige o corte `pronto` (409 `corte_not_ready`);
- `postado` só pela rota humana.

**Snapshot versionado:** `conta_id`, `titulo`, `descricao`, `hashtags`, `estado`, `planned_at`,
`posted_url` e `archived`. Esse snapshot é o "histórico dos textos" (US5-2).

## `sugestoes_texto`
Log imutável de cada chamada ao Claude (R9).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `corte_id` | uuid not null FK → cortes.id | |
| `plataforma` | enum `platform` (da 003) | |
| `model` | text not null | ex.: `claude-sonnet-5-5` |
| `prompt_version` | text not null | ex.: `textos/1` |
| `resultado` | jsonb null | `{titulo, descricao, hashtags}` validado |
| `ajustes` | text[] not null default '{}' | o que foi cortado ou completado na validação |
| `erro_code` | text null | `timeout`, `refusal`, `invalid`, `api_error` |
| `input_tokens`, `output_tokens`, `cache_read_tokens` | int null | |
| `duration_ms` | int not null | |
| `created_at`, `created_by` | | |

Só INSERT.

## `notificacoes`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | cursor do polling (`after`) |
| `user_id` | uuid not null FK → users.id | destinatário |
| `tipo` | enum `notificacao_tipo` (`envio_pronto`, `envio_sem_clipes`, `envio_falhou`, `envio_confirmar_qualidade`, `envio_momentos` (0007: momentos escolhidos, um por rodada), `openshorts_fora`, `hora_de_postar`, `cota_youtube`, `canal_erro`) | |
| `titulo` | text not null | ex.: "Hora de postar: <título> no TikTok" |
| `corpo` | text not null default '' | |
| `link` | text not null | rota do SPA (`/app/envios/…`, `/app/cortes/…`) |
| `entity_type`, `entity_id` | text, uuid null | |
| `dedupe_key` | text not null | ex.: `hora_de_postar:<postagem>:<planned_at>`; UNIQUE `(user_id, dedupe_key)` |
| `created_at` | timestamptz not null default now() | |
| `lida_em` | timestamptz null | |

Índice `(user_id, id desc)` e parcial `(user_id) WHERE lida_em IS NULL`. As notificações nunca
são apagadas (marcar como lida só preenche `lida_em`).

## Estados
```
canal (sync): pendente ──agendador──▶ sincronizando ──▶ ok ──(next_sync_at)──▶ sincronizando …
                              │                         └──cota ≥ 95%──▶ pausado_cota ──novo dia──▶ ok
                              └──erro da API──▶ erro ──(retry 1 h / "Sincronizar agora")──▶ sincronizando

envio: selecionado ──enviar (aviso se sem_acordo/avulso)──▶ na_fila ──agendador──▶ processando
         │                                                   ▲   │  └─OpenShorts fora─▶ aguardando_openshorts ─┘ (backoff)
         └──remover──▶ descartado (arquivado)               │   ├─needs_confirmation─▶ confirmar_qualidade ─"mesmo assim"─▶ na_fila
                                                             │   └─400/403─▶ falhou
         processando ──completed──▶ importando ──▶ pronto
                     ├─failed "No clips"─▶ sem_clipes
                     ├─failed / 404─▶ falhou ──"Tentar de novo"──┘ (volta a na_fila, novo job)
         importando ──clipes expirados / 3 erros──▶ falhou (mantém os já importados; "Importar de novo" se o job ainda existe)

corte (openshorts): revisao ──"Aplicar marca" (ou marca automática)──▶ na_fila ──(worker da 004)──▶ processando ──▶ pronto | falhou
                    revisao/pronto ──arquivar──▶ arquivado ──restaurar──▶ (estado anterior)

postagem: rascunho ──data e hora (corte pronto)──▶ agendado ──"Postado"──▶ postado
          agendado ──remarcar──▶ agendado (lembrado_em = null) ;  qualquer ──arquivar──▶ cancelada
```
- `pronto`, `sem_clipes` e `descartado` são finais para o envio. Reprocessar é um envio novo, e o
  aviso de duplicado se aplica.
- Nenhum estado apaga arquivo. Os clipes e o arquivo avulso ficam no bucket `sociman-videos`.

## Relações
```
perfis 1─N canal_perfis N─1 canais_fonte 1─N videos_fonte 1─N video_metricas
perfis 1─1 padroes_corte
perfis 1─N envios N─1 videos_fonte (null no avulso)
envios 1─N cortes (origem openshorts) 1─N postagens N─1 contas
cortes 1─N sugestoes_texto
users 1─N notificacoes
```
