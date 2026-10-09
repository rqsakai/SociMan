# Modelo de dados: 014-central-de-conteudos

Tudo fica no PostgreSQL (NVMe), na migration **`0009_central_conteudos`** (down_revision
`0008_assistente_ia`). Os arquivos do vídeo próprio ficam no MinIO (HD): o vídeo no bucket
`sociman-videos` e a miniatura no bucket `sociman`.
- As tabelas usam o `AuditMixin` da 001 e o `_Versioned` da 003 (`version`, `archived_at`,
  `archived_by`).
- Histórico em `entity_versions`, com um `entity_type` novo: **`conteudo`**. O destino continua com
  `entity_type = "postagem"` (research R2).
- Nomes: **conteúdo** = `conteudos`; **destino** = uma linha de `postagens`; **agendamento** = os
  campos de agenda do destino.

## `conteudos` (nova)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | na origem `corte`, **igual a `cortes.id`** |
| `perfil_id` | uuid not null FK → perfis.id | na origem corte, o perfil do corte |
| `origem` | enum `conteudo_origem` (`corte`, `video_proprio`) | avatar e afiliado entram depois com `ADD VALUE` |
| `corte_id` | uuid null UNIQUE FK → cortes.id | origem `corte` ⇔ preenchido e `= id` |
| `titulo` | text not null default '' | até 100; na origem corte, nasce do título do OpenShorts, do gancho ou do nome do arquivo |
| `video_key` | text null UNIQUE | só `video_proprio`: `conteudos/{id}/video.<ext>` no bucket de vídeos |
| `video_content_type` | text null | `video/mp4`, `video/quicktime`, `video/webm` |
| `video_bytes` | bigint null | até 2 GB |
| `video_sha256` | text null | calculado no recebimento |
| `original_filename` | text null | |
| `duration_ms`, `width`, `height` | int null | do ffprobe |
| `poster_key` | text null | bucket `sociman` (imgproxy) |
| `version`, `archived_at`, `archived_by`, AuditMixin | | na origem corte, `archived_at` fica null (vale o do corte) |

Regras:
- `ck_conteudos_origem`:
  `(origem = 'corte' AND corte_id = id AND video_key IS NULL AND archived_at IS NULL)` **ou**
  `(origem = 'video_proprio' AND corte_id IS NULL AND video_key IS NOT NULL AND poster_key IS NOT
  NULL AND duration_ms IS NOT NULL)`;
- `ck_conteudos_titulo`: `char_length(titulo) <= 100`;
- índices `ix_conteudos_perfil_created (perfil_id, created_at DESC, id DESC)` e
  `ix_conteudos_created (created_at DESC, id DESC)`;
- invariante (teste): todo `cortes.id` tem uma linha `conteudos` com o mesmo id.

**Snapshot versionado:** `titulo` e `archived`. `origem`, `corte_id` e as colunas do arquivo são
`__immutable_fields__` (informativas; a reversão as ignora).

**Campos derivados** (em `conteudos/consulta.py`, nunca gravados):

| Campo | Origem `corte` | Origem `video_proprio` |
|---|---|---|
| `situacao` | `revisao` → `em_revisao`; `na_fila`/`processando` → `processando`; `pronto` → `pronto`; `falhou` → `erro_marca` | `pronto` |
| `arquivado` | `cortes.archived_at IS NOT NULL` | `conteudos.archived_at IS NOT NULL` |
| `poster_key`, `duration_ms` | do corte | do conteúdo |
| vídeo final (`video_ref`) | `cortes.result_key` | `conteudos.video_key` |

## `postagens` (da 006, agora o **destino**)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `conteudo_id` | uuid not null FK → conteudos.id | **novo**; substitui `corte_id` (removida) |
| `conta_id` | uuid not null FK → contas.id | conta do perfil do conteúdo; **não muda depois de criado** (aprovação é por conta) |
| `titulo`, `descricao`, `hashtags` | como na 006 | 100 / 2.000 / 0..8 |
| `estado` | enum **`destino_estado`** | `pendente` (padrão), `aprovacao_pedida`, `aprovado`, `agendado`, `postado`, `rascunho_criado`, `publicado`, `falhou` |
| `modo` | enum `agendamento_modo` (`lembrete`, `criar_rascunho`, `publicar`, `rascunho_e_publicar`) not null default `lembrete` | só `lembrete` na 014 (CHECK) |
| `antecedencia_min` | smallint null | só com `rascunho_e_publicar` (0..10.080) |
| `planned_at` | timestamptz null | obrigatório em `agendado` |
| `lembrado_em` | timestamptz null | como na 006; zera ao mudar `planned_at` |
| `posted_at`, `posted_url` | como na 006 | preenchidos por "Postado" |
| `falha_motivo` | text null | reservado ao executor da 015 (sempre null na 014) |
| `sugestao_id` | uuid null FK → ia_chamadas.id | como na 008 |
| `aprovado_por` | uuid null FK → users.id | **novo** |
| `aprovado_em` | timestamptz null | **novo** |
| `aprovado_video_ref` | text null | **novo**: o vídeo final no momento da aprovação (`videoMudou`) |
| `pedido_por` | uuid null FK → users.id | **novo** |
| `pedido_em` | timestamptz null | **novo** |
| `pedido_nota` | text null | **novo**, até 500 |
| `recusado_por` | uuid null FK → users.id | **novo** |
| `recusado_em` | timestamptz null | **novo** |
| `recusa_motivo` | text null | **novo**, 1..500; visível até a próxima aprovação |
| `version`, `archived_at`, `archived_by`, AuditMixin | | |

Regras:
- `uq_postagens_conteudo_conta_ativa (conteudo_id, conta_id) WHERE archived_at IS NULL` → 409
  `destino_exists` (substitui `uq_postagens_corte_conta_ativa`);
- `ck_postagens_agendado_planned` (da 006): `estado <> 'agendado' OR planned_at IS NOT NULL`;
- `ck_postagens_aprovado`: `estado NOT IN ('aprovado','agendado','postado','rascunho_criado',
  'publicado','falhou') OR aprovado_em IS NOT NULL`;
- `ck_postagens_pedido`: `estado <> 'aprovacao_pedida' OR pedido_em IS NOT NULL`;
- `ck_postagens_antecedencia`: `antecedencia_min IS NULL OR (modo = 'rascunho_e_publicar' AND
  antecedencia_min BETWEEN 0 AND 10080)`;
- `ck_postagens_textos_nota`: `char_length(pedido_nota) <= 500` e `char_length(recusa_motivo)
  BETWEEN 1 AND 500` (quando não null); os de título e descrição da 006 continuam;
- **guardas do princípio I no banco (só na 014; a 015 os remove depois da emenda):**
  - `ck_postagens_modo_014`: `modo = 'lembrete' AND antecedencia_min IS NULL`;
  - `ck_postagens_estados_015`: `estado NOT IN ('rascunho_criado','publicado','falhou')`;
- índices: `ix_postagens_estado_planned` (da 006), `ix_postagens_conteudo (conteudo_id)` e
  `ix_postagens_conta_agenda (conta_id, planned_at) WHERE archived_at IS NULL AND estado =
  'agendado'`.

**Snapshot versionado:** `conta_id`, `titulo`, `descricao`, `hashtags`, `estado`, `modo`,
`antecedencia_min`, `planned_at`, `posted_url`, `aprovado_por`, `aprovado_em`, `pedido_nota`,
`recusa_motivo` e `archived`. `aprovado_video_ref`, `pedido_por`, `pedido_em`, `recusado_por` e
`recusado_em` são informativos. As versões antigas (da 006) não têm os campos novos: a reversão usa
os padrões (`modo = lembrete`, aprovação vazia) e **nunca** restaura uma aprovação num destino que
não está aprovado hoje (a reversão de aprovação é recusar ou aprovar de novo).

`details.acao` das versões: `aprovado`, `aprovacao_pedida`, `recusado`, `agendado`, `reagendado`,
`agendamento_cancelado`, `cancelado_por_arquivo`, `postado` (da 006), e `lote` quando a ação veio de
uma rota em lote (com `details.loteId`, um uuid por chamada). Um agendamento ou reagendamento mantido
a menos do intervalo mínimo da conta leva `details.intervaloIgnorado = true`.

## `contas` (da 002, ampliada)
| Coluna | Tipo | Regras |
|---|---|---|
| `intervalo_min_minutos` | smallint not null default 30 | **nova**; intervalo mínimo entre posts da conta (Clarifications Q3); só dono muda |

Regras:
- `ck_contas_intervalo_min`: `intervalo_min_minutos BETWEEN 0 AND 1440`;
- conflito entre dois horários da mesma conta: `abs(a - b) < greatest(intervalo_min_minutos, 1)`
  minutos (com 0, só o mesmo minuto conflita). Consideram-se os destinos ativos da conta com
  `estado = 'agendado'` (índice `ix_postagens_conta_agenda`), menos o próprio destino;
- **Snapshot versionado:** `intervalo_min_minutos` entra em `Conta.__versioned_fields__`. As versões
  anteriores (da 002) não têm o campo: a reversão para uma delas **mantém o valor atual**;
- mudar o valor não altera nenhum agendamento existente.

## `ia_chamadas` (da 008, ampliada)
| Coluna | Tipo | Regras |
|---|---|---|
| `conteudo_id` | uuid null FK → conteudos.id | **nova**; preenchida em toda chamada `postagem.*`; na migração, `= corte_id` |

Índice `ix_ia_chamadas_conteudo (conteudo_id, created_at DESC)`.

## `notificacoes` (da 006)
`notificacao_tipo` ganha:
- `aprovacao_pedida`: para os donos ativos. Título "Aprovação pedida: <título> no <rede>", link
  `/app/conteudos/{conteudoId}?conta={contaId}`, `dedupe_key = aprovacao_pedida:<destino>:<version>`;
- `aprovacao_respondida`: para quem pediu, na aprovação ou na recusa (com o motivo no corpo),
  `dedupe_key = aprovacao_respondida:<destino>:<version>`.

`hora_de_postar` muda só o link (`/app/conteudos/{conteudoId}?conta={contaId}`).

## Estados

### Conteúdo (derivado, R1)
```
origem corte:   em_revisao ──Aplicar marca──▶ processando ──worker──▶ pronto | erro_marca
video_proprio:  pronto (ao terminar o envio)
qualquer:       ──arquivar──▶ arquivado (cancela os agendamentos) ──restaurar──▶ situação anterior
```

### Destino (gravado, R3)
```
                ┌───────── recusar (dono, motivo) ◀──────────┐
                ▼                                            │
 (conta escolhida) pendente ──pedir aprovação──▶ aprovacao_pedida
        │                                            │
        └──────── aprovar (dono; conteúdo pronto) ◀──┘
                              │
                              ▼
                          aprovado ◀──cancelar agendamento── agendado ◀──reagendar──┐
                           │  │                               ▲   │                 │
                           │  └──agendar (dono/membro)────────┘   └─────────────────┘
                           │                                      │
                           └──"Postado" (humano)──▶ postado ◀─────┘ "Postado" (humano)

 dono agenda direto: pendente|aprovacao_pedida ──(aprova + agenda, 2 versões)──▶ agendado
 recusar também sai de aprovado (sem agendamento) ─▶ pendente
 015 (não existe na 014): agendado ──executor──▶ rascunho_criado | publicado | falhou
```

### Estado efetivo (derivado, R3), na ordem de avaliação
`arquivado` → `em_revisao` → `atencao` → `atrasado` → `a_postar` → estado gravado (`pendente`
aparece como `pronto`). `sem_conta` é do conteúdo sem destino.

## Relações
```
perfis 1─N conteudos 1─N postagens (destinos) N─1 contas
cortes 1─1 conteudos (origem corte, mesmo id)
conteudos 1─N ia_chamadas (postagem.*)
users 1─N notificacoes (aprovacao_pedida, aprovacao_respondida, hora_de_postar)
```

## Migração dos dados da 006 (`0009_central_conteudos`, R2)
1. `INSERT INTO conteudos` uma linha por corte (arquivados inclusive), com `id = corte_id =
   cortes.id`.
2. `postagens.conteudo_id = corte_id`; `NOT NULL`; troca o índice único; remove `corte_id`.
3. `estado`: `rascunho → pendente`, `agendado → agendado`, `postado → postado`; em `agendado` e
   `postado`, `aprovado_em = updated_at` e `aprovado_por = COALESCE(updated_by, created_by)`.
4. `modo = 'lembrete'` em todas; demais colunas novas null.
5. `ia_chamadas.conteudo_id = corte_id`.
5a. `contas.intervalo_min_minutos` com padrão 30 em todas as contas e o CHECK
    `ck_contas_intervalo_min`.
6. `ALTER TYPE notificacao_tipo ADD VALUE` (dois valores; não usados na mesma transação).
7. Nenhuma linha de `entity_versions` é escrita nem alterada. A primeira mutação depois da migração
   grava o snapshot novo com todos os campos.

Downgrade: recusa com `video_proprio` presente; senão desfaz na ordem inversa (inclusive remove
`contas.intervalo_min_minutos`) (`pendente`,
`aprovacao_pedida` e `aprovado` → `rascunho`). Para os valores novos de `notificacao_tipo`, segue o
padrão da 0007 (`envio_momentos`): apaga as notificações desses dois tipos e recria o enum sem eles
(o Postgres não remove valor de enum).
