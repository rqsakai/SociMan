# Modelo de dados: 015-tiktok-rascunho

Tudo no PostgreSQL (NVMe), na migration **`0010_publicacao_tiktok`** (down_revision
**`0009_central_conteudos`**). O avatar do criador vai para o MinIO (HD), bucket `imagens`.
- Tabelas de domínio com o `AuditMixin` da 001 e o `_Versioned` da 003 (`version`,
  `archived_at`, `archived_by`) quando têm histórico.
- Histórico em `entity_versions` com dois `entity_type` novos: **`conexao`** e
  **`publicacao_config`**. O destino continua `postagem`.
- `actor_kind` novo: **`system:publicacao`** (a trilha). As ações humanas continuam `user`.
- Pacote novo: `apps/api/src/sociman_api/publicacao/` (plan, Project Structure).

## `conexoes` (nova)
Uma conexão por conta TikTok. Guarda só dados **não secretos**; os tokens ficam em
`conexao_credenciais`.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `conta_id` | uuid not null FK → contas.id | conta da 003 com `platform = 'tiktok'` (conferido no service) |
| `rede` | enum `platform` (o da 003) | `tiktok` na 015 |
| `open_id` | text not null | identificador da TikTok para este app e este usuário |
| `username` | text not null | o @ que a TikTok informou (sem `@`), conferido com `contas.handle` |
| `display_name` | text not null default '' | apelido |
| `avatar_key` | text null | `conexoes/{id}/avatar-{sha8}.<ext>` no bucket `imagens` |
| `escopos` | text[] not null | os concedidos (`video.upload`, `video.publish`, …) |
| `estado` | enum **`conexao_estado`** (`conectada`, `precisa_reconectar`, `desconectada`) | |
| `motivo` | text null | por que precisa reconectar (pt-BR) |
| `conectado_por` | uuid not null FK → users.id | dono humano |
| `conectado_em` | timestamptz not null | |
| `desconectado_por` | uuid null FK → users.id | |
| `desconectado_em` | timestamptz null | |
| `refresh_expira_em` | timestamptz null | cópia não secreta para o aviso de 30 dias |
| `avisado_vencimento_em` | timestamptz null | uma vez por ciclo (R5) |
| `version`, `archived_at`, `archived_by`, AuditMixin | | nunca arquivada na 015 (desconectar é o fim) |

Regras:
- `uq_conexoes_conta_viva (conta_id) WHERE estado <> 'desconectada'`: uma conexão viva por conta;
- `uq_conexoes_open_id_vivo (rede, open_id) WHERE estado <> 'desconectada'` → 409
  `conexao_em_uso`;
- `ck_conexoes_desconectada`: `estado <> 'desconectada' OR (desconectado_em IS NOT NULL)`;
- reconectar a mesma conta cria **outra linha** (a antiga fica `desconectada`) só depois de
  desconectar; reconectar de `precisa_reconectar` **reusa** a linha (mesmo `open_id`, R3).

**Snapshot versionado:** `open_id`, `username`, `display_name`, `escopos`, `estado`, `motivo`,
`conectado_por`, `desconectado_por`. `avatar_key` e `refresh_expira_em` são informativos.
`details.acao`: `conectada`, `reconectada`, `precisa_reconectar`, `desconectada`. Sem `revert`
(reconectar é refazer o login).

## `conexao_credenciais` (nova, **fora do histórico**)
| Coluna | Tipo | Regras |
|---|---|---|
| `conexao_id` | uuid PK FK → conexoes.id | 1:1 |
| `key_id` | text not null | 8 hex do SHA-256 da chave usada (R4) |
| `access_cifrado` | bytea not null | `nonce(12) ‖ AES-GCM(access_token)`, AAD `"{conexao_id}:access"` |
| `access_expira_em` | timestamptz not null | `now + expires_in` |
| `refresh_cifrado` | bytea not null | idem, AAD `"{conexao_id}:refresh"` |
| `refresh_expira_em` | timestamptz not null | `now + refresh_expires_in` |
| `renovado_em` | timestamptz null | |
| `renovacoes` | int not null default 0 | |

- Sem `__versioned_fields__`: nunca passa por `history.snapshot`, nunca sai em schema.
- **Apagada** (DELETE da linha) ao desconectar e ao virar `precisa_reconectar`. É a única exclusão
  física da 015: segredo não é dado de domínio, e o fato fica na versão da `conexao` (Constitution
  Check VII).
- Leitura só por `publicacao/conexoes.py::token_valido`, com `SELECT … FOR UPDATE` (R5).

## `publicacao_config` (nova, singleton)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | smallint PK | `ck_publicacao_config_unica`: `id = 1` (a migration insere a linha) |
| `envios_habilitados` | boolean not null default false | o interruptor da tela (R11) |
| `version`, AuditMixin | | |

**Snapshot versionado:** `envios_habilitados`. `details.acao`: `ligado`, `desligado`. O nível do
servidor (`PUBLICACAO_HABILITADA`) não fica no banco; a API o expõe só como leitura.

## `publicacao_tentativas` (nova)
Uma linha por execução de envio de um destino. Escrita **só** pela trilha e por
`publicacao/service.py` (tentar de novo); linhas em fase final não mudam mais (teste).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `destino_id` | uuid not null FK → postagens.id | |
| `numero` | int not null | 1, 2, … por destino; `uq_tentativas_destino_numero` |
| `conexao_id` | uuid not null FK → conexoes.id | a conexão usada |
| `rede` | enum `platform` | |
| `modo` | enum `agendamento_modo` | `criar_rascunho` ou `publicar` |
| `fase` | enum **`tentativa_fase`** | `iniciando`, `enviando_partes`, `processando`, `entregue`, `publicada`, `recusada`, `incerta`, `sem_vaga` |
| `disparo` | text not null | `agendador` \| `tentar_de_novo` \| `confirmado` |
| `disparado_por` | uuid null FK → users.id | nas ações humanas |
| `video_ref` | text not null | chave do objeto no bucket `sociman-videos` no início |
| `video_etag` | text not null | `stat_object` no início (R9) |
| `video_bytes` | bigint not null | |
| `video_sha256` | text null | calculado durante o envio |
| `chunk_size`, `total_partes` | bigint / int not null | R9 |
| `partes_enviadas` | int not null default 0 | |
| `init_enviado_em` | timestamptz null | gravado **antes** do init (R8) |
| `publish_id` | text null UNIQUE | gravado **antes** do primeiro PUT |
| `upload_url_cifrado` | bytea null | o `upload_url` leva `upload_token`: cifrado como os tokens (AAD `"{id}:upload"`), apagado (null) ao sair de `enviando_partes` |
| `upload_url_expira_em` | timestamptz null | `init + 55 min` |
| `status_rede` | text null | último status bruto (`PROCESSING_UPLOAD`, `SEND_TO_USER_INBOX`, …) |
| `codigo_rede` | text null | `error.code` ou `fail_reason` cru |
| `motivo` | text null | pt-BR (R19) |
| `rede_post_id` | text null | `publicaly_available_post_id` (grafia da API), quando vier |
| `proxima_em` | timestamptz null | próxima consulta de status, ou a vaga (fase `sem_vaga`) |
| `iniciada_em` | timestamptz not null default now() | |
| `concluida_em` | timestamptz null | preenchida nas fases finais |
| `details` | jsonb not null default '{}' | tempos por parte, número de consultas; nunca tokens |

Regras:
- `uq_tentativas_destino_aberta (destino_id) WHERE fase IN ('iniciando','enviando_partes',
  'processando')` (R8);
- `ck_tentativas_publish_id`: `fase NOT IN ('enviando_partes','processando','entregue',
  'publicada') OR publish_id IS NOT NULL`;
- `ck_tentativas_final`: `fase IN ('iniciando','enviando_partes','processando') OR concluida_em
  IS NOT NULL`;
- `ck_tentativas_partes`: `partes_enviadas BETWEEN 0 AND total_partes`;
- índices `ix_tentativas_abertas (proxima_em) WHERE fase IN ('iniciando','enviando_partes',
  'processando')`, `ix_tentativas_conexao_init (conexao_id, init_enviado_em) WHERE modo =
  'criar_rascunho' AND init_enviado_em IS NOT NULL` (contagem das 24 h: fases `iniciando`,
  `enviando_partes`, `processando`, `entregue` e `incerta`, R10 e Clarifications Q1) e
  `ix_tentativas_destino (destino_id, numero DESC)`.

## `postagens` (o destino da 014), ampliada
| Coluna | Tipo | Regras |
|---|---|---|
| `estado` | enum `destino_estado` + **`enviando`** | `ALTER TYPE … ADD VALUE 'enviando'` |
| `agendado_por` | uuid null FK → users.id | **novo**: quem agendou (ou reagendou) por último |
| `agendado_em` | timestamptz null | **novo** |
| `envio_confirmado_por` | uuid null FK → users.id | **novo**: "Confirmar envio" de um vencido (R11) |
| `envio_confirmado_em` | timestamptz null | **novo** |
| `opcoes_rede` | jsonb null | **novo**: `OpcoesTikTok` (R13), validado por schema; só modo `publicar` |
| `envio_snapshot` | jsonb null | **novo**: `{legenda, opcoes, consentimento: {texto, aceitoEm}, videoRef}` gravado ao agendar em modo automático |
| `falha_motivo` | text null | da 014; agora preenchido pela trilha |
| `falha_incerta` | boolean not null default false | **novo**: a última falha pode ter criado algo na TikTok |
| `rede_post_id` | text null | **novo**: id do post público, quando a TikTok informar |

CHECKs (R17), trocados na 0010:
- **removidos:** `ck_postagens_modo_014`, `ck_postagens_estados_015`;
- `ck_postagens_modo_015`: `modo IN ('lembrete','criar_rascunho','publicar') AND
  antecedencia_min IS NULL`;
- `ck_postagens_execucao`: `estado NOT IN ('enviando','rascunho_criado','publicado','falhou') OR
  modo <> 'lembrete'`;
- `ck_postagens_auto_decisao`: `modo = 'lembrete' OR estado NOT IN ('agendado','enviando') OR
  (aprovado_por IS NOT NULL AND agendado_por IS NOT NULL)`;
- `ck_postagens_publicar_snapshot`: `modo <> 'publicar' OR estado NOT IN ('agendado','enviando')
  OR (opcoes_rede IS NOT NULL AND envio_snapshot IS NOT NULL)`;
- o `ck_postagens_aprovado` da 014 já cobre `rascunho_criado`/`publicado`/`falhou`; ganha
  `enviando` na lista.
- índice novo `ix_postagens_auto_vencidos (planned_at) WHERE estado = 'agendado' AND modo <>
  'lembrete' AND archived_at IS NULL` (reivindicação da trilha).

**Snapshot versionado:** os da 014 + `agendado_por`, `opcoes_rede`, `envio_snapshot`,
`envio_confirmado_por`, `falha_motivo`, `rede_post_id`. `agendado_em`, `envio_confirmado_em` e
`falha_incerta` são informativos. A **reversão** (014) nunca restaura `enviando`,
`rascunho_criado`, `publicado` nem `falhou`, nunca restaura um snapshot de envio (reagendar é o
caminho) e é recusada (409 `conflict`) com o destino em `enviando`.

`details.acao` novos: `envio_iniciado`, `rascunho_criado`, `publicado`, `envio_falhou`,
`envio_devolvido` (sem vaga ou conta desconectada antes do init), `tentar_de_novo`,
`envio_confirmado`, `snapshot_atualizado`. As da trilha levam `details.tentativaId`.

### Transições do destino (acréscimos à 014)
```
agendado ──(trilha: reivindica; modo automático, conectada, interruptor ligado,
            planned_at > now-1h ou confirmado)──▶ enviando
enviando ──entregue──▶ rascunho_criado ──"Postado" (humano)──▶ postado
enviando ──publicada─▶ publicado
enviando ──recusada | incerta──▶ falhou ──"Tentar de novo" (dono humano)──▶ agendado (planned_at = agora)
enviando ──sem_vaga | conexão perdida antes do init──▶ agendado (volta; derivado aguardando_vaga/atencao)
agendado (vencido > 1 h) ──"Confirmar envio" (dono humano)──▶ agendado + envio_confirmado_em
```
Regras que valem sempre:
- de `enviando` nada sai por ação humana (cancelar, reagendar, arquivar, reverter, editar textos
  → 409 `envio_em_andamento`);
- `falhou` aceita também **Cancelar** (vira `aprovado`, sem data) e **Reagendar** (vira
  `agendado`, com nova data): ações de dono humano;
- `rascunho_criado` e `publicado` são finais para a trilha; `rascunho_criado → postado` é
  humano; `publicado` é final.

### Estado efetivo (derivado; a ordem da 014 com os acréscimos em negrito)
`arquivado` → `em_revisao` → `atencao` (+ "Conta não conectada", "Conta precisa reconectar" em
modo automático) → **`pausado`** → **`vencido`** → **`aguardando_vaga`** → `atrasado` →
`a_postar` (só lembrete) → estado gravado (inclui **`enviando`**) → `pronto`.

| Derivado | Regra |
|---|---|
| `pausado` | interruptor desligado (`PUBLICACAO_HABILITADA` ou `envios_habilitados`) e: `agendado`, modo automático, `planned_at <= now()`; **ou** `enviando` com a tentativa aberta em `iniciando` ou `enviando_partes` (R11: parada até religar) |
| `vencido` | `agendado`, modo automático, `planned_at <= now() - 1 h`, `envio_confirmado_em` null ou `< planned_at`, sem tentativa aberta |
| `aguardando_vaga` | `agendado`, última tentativa `sem_vaga` com `proxima_em > now()` |

`PUBLICACAO_HABILITADA` entra na expressão SQL como parâmetro (lido do `Settings`). Atalhos novos
em `Atalhos` (014): `vencidos`, `enviando`, `rascunhosCriados`; `falharam` passa a contar.

## `notificacoes`: tipos novos
`ALTER TYPE notificacao_tipo ADD VALUE` (fora da transação que os usa, como na 0009):

| Tipo | Para | Título | `dedupe_key` |
|---|---|---|---|
| `rascunho_criado` | donos ativos | "Rascunho na TikTok: <título> (@conta)", corpo "Abra o app da TikTok para finalizar" + link com **Copiar textos** | `rascunho_criado:<tentativa>` |
| `envio_publicado` | donos | "Publicado na TikTok: <título>" | `envio_publicado:<tentativa>` |
| `envio_rede_falhou` | donos | "Falhou na TikTok: <título>", corpo com o motivo | `envio_rede_falhou:<tentativa>` |
| `envio_aguardando_vaga` | donos | "Aguardando vaga na TikTok: <título>" | `envio_aguardando_vaga:<destino>:<proxima_em>` |
| `conexao_precisa_reconectar` | donos | "Reconecte @conta na TikTok", corpo com o motivo (ou "vence em 30 dias") | `conexao:<id>:<estado>:<dia>` |

Link de todas: `/app/conteudos/{conteudoId}?conta={contaId}` (as de conexão: `/app/perfis/{id}`
na aba Contas).

## `security_events` (da 001)
Tipo novo **`publicacao_recusada`** (texto; sem enum): `{rota, actorKind, contaId?, destinoId?}`
quando `RequireHumanOwner` recusa (R15) ou a trilha encontra um agendamento sem decisão humana.

## Relações
```
contas 1─N conexoes (1 viva) 1─1 conexao_credenciais
postagens (destinos) 1─N publicacao_tentativas N─1 conexoes
users 1─N conexoes (conectado_por, desconectado_por), postagens (agendado_por, envio_confirmado_por)
publicacao_config (1 linha)
```

## Migration `0010_publicacao_tiktok`
Upgrade, na ordem:
1. `CREATE TYPE conexao_estado`, `tentativa_fase`;
2. `ALTER TYPE destino_estado ADD VALUE IF NOT EXISTS 'enviando'`; `ALTER TYPE notificacao_tipo
   ADD VALUE IF NOT EXISTS` (os cinco) — em blocos `autocommit` do Alembic, antes de qualquer uso
   (os CHECKs do passo 4 citam `'enviando'`). O `IF NOT EXISTS` é obrigatório: o downgrade deixa
   `enviando` no enum, e subir de novo não pode falhar (padrão da 0007 e da 0009);
3. `CREATE TABLE conexoes`, `conexao_credenciais`, `publicacao_config` (+ `INSERT id = 1,
   envios_habilitados = false`), `publicacao_tentativas`, com índices e CHECKs;
4. `ALTER TABLE postagens`: colunas novas; `DROP CONSTRAINT ck_postagens_modo_014`,
   `ck_postagens_estados_015`; `ADD CONSTRAINT` os quatro novos; troca o `ck_postagens_aprovado`
   (inclui `enviando`); índice `ix_postagens_auto_vencidos`;
5. dados: nenhum destino muda (todos são `lembrete` na 014). Nenhuma linha de
   `entity_versions` é escrita.

Downgrade: recusa (erro claro) se houver linha em `conexoes` ou `publicacao_tentativas`, ou
destino com `modo <> 'lembrete'`; senão desfaz na ordem inversa, recria os CHECKs da 014, apaga
as notificações dos tipos novos e recria o enum sem eles (padrão da 0007). O valor `enviando`
fica no `destino_estado` (o Postgres não remove valor de enum; nenhuma linha o usa).

Teste: `test_migration_0010.py` sobe com dados da 014 (destinos em todos os estados da 014),
confere os CHECKs novos e desce.
