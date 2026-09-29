---

description: "Tarefas da feature 006-cortes-openshorts"
---

# Tasks: Fontes, seleção de vídeos e cortes com o OpenShorts (006-cortes-openshorts)

**Input**: `specs/006-cortes-openshorts/`: spec (com as Clarifications de 2026-09-29, Q1–Q4 = A),
plan, research R1–R16, data-model, contracts/http-api.md e quickstart.

**Prerequisites**:
- a migration `0005_assets` da spec 007 precisa existir antes da `0006_cortes_openshorts`
  (`down_revision = "0005_assets"`). Se a 006 for implementada antes da 007, refaça o
  encadeamento: a 006 passa a `down_revision = "0004_fundo_imagem"` e a 007 passa a vir depois
  dela (plan.md, "Migration");
- a stack da 004 validada: MinIO no HD, sentinela, worker.

**Tests**: OBRIGATÓRIOS (constitution 3.0.0, princípio VI). Toda história tem testes de API, e
fecham a entrega:
- `npm run test:api` (pytest na stack efêmera), com mocks HTTP (`httpx.MockTransport`) de
  YouTube, OpenShorts e Anthropic, e ffmpeg real nos clipes sintéticos;
- `docker compose exec api uv run ruff check .`;
- `npm run check:web` (contrato regenerado, `check:secrets` com os padrões `AIza…` e `sk-ant-…`);
- `npm run test:e2e` na stack isolada (projeto `sociman-e2e`, `docker-compose.e2e.yml`), com o
  `openshorts-fake` e o `agendador`;
- testes-guarda dos princípios I (`tests/unit/test_constitution_guards.py`), II
  (`tests/integration/test_direito.py`) e VII (`tests/integration/test_historico_006.py`).

**Nomes canônicos** (valem os documentos do plano): serviço `agendador` (`sociman agendador`),
trilhas `sync`, `openshorts`, `importacao` e `lembretes`; pacotes `canais/`, `envios/`,
`postagem/` e `notificacoes/`; bucket `sociman-videos`; `APP_TZ = America/Sao_Paulo`.

**Arquivos compartilhados com a 007** (assets do perfil, em paralelo): **só acréscimo**, sem
reescrever nem reordenar o que a 007 pôs. Marcados com ⚠️ **COMPARTILHADO (só acréscimo)**:
`docker/nginx/default.conf.template`, `docker-compose.yml`, `docker-compose.e2e.yml`,
`apps/web/src/pages/perfis/PerfilDetalhe.tsx`, `apps/web/src/components/shell/nav.ts`,
`apps/api/src/sociman_api/imaging.py` e `apps/web/src/App.tsx` (rotas).

**Contrato gerado** (princípio IV, armadilha 6 do CLAUDE.md): `packages/contract/openapi.json` e
`src/generated/` nunca são editados à mão. Só a Trilha D roda `npm run gen:contract` (veja
"Trilhas para agentes paralelos").

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US5 da spec; Setup, Foundational e Polish não têm rótulo de história
- Todos os caminhos são relativos à raiz do SociMan

---

## Phase 1: Setup (infra compartilhada)

**Purpose**: dependências, configuração, compose e edge. Nada de domínio.

- [X] T001 Em `apps/api/pyproject.toml`, mover `httpx` do grupo dev para `dependencies` e
  acrescentar `anthropic` (SDK oficial); atualizar `apps/api/uv.lock` (`uv lock`) e reconstruir a
  imagem. Não acrescentar `google-api-python-client` (o guarda `SOCIAL_SDKS` o proíbe).
- [X] T002 [P] Em `apps/api/src/sociman_api/config.py`, acrescentar: `youtube_api_key` (vazio =
  não configurada), `youtube_api_url` (padrão `https://www.googleapis.com/youtube/v3`; o e2e
  aponta para o `openshorts-fake`), `openshorts_url` (padrão `http://host.docker.internal:8000`),
  `anthropic_api_key`, `textos_model` (padrão `claude-sonnet-5-5`), `app_tz`
  (`America/Sao_Paulo`), `yt_quota_daily` (10000), `sync_novos_h` (1) e os intervalos
  `agendador_sync_s` (60), `agendador_openshorts_s` (10), `agendador_importacao_s` (5) e
  `agendador_lembretes_s` (30). As chaves nunca entram em `repr`/log (usar `SecretStr` ou
  equivalente).
- [X] T003 [P] Em `.env.example`, acrescentar `YOUTUBE_API_KEY=` e `ANTHROPIC_API_KEY=` vazios,
  com comentário em pt-BR ("fica só no `.env`, fora do git"). Conferir que
  `scripts/check-secrets.mjs` **já tem** os padrões `\bsk-ant-[A-Za-z0-9_-]{20,}` e
  `\bAIza[0-9A-Za-z_-]{35}\b` (linhas 11–12) e rodar `npm run check:secrets`. Só mexer no script
  se faltar algum.
- [X] T004 ⚠️ **COMPARTILHADO (só acréscimo)** Em `docker-compose.yml`:
  - serviço novo `agendador`: a mesma imagem da `api`, `command` `uv run sociman agendador`,
    `user: "1000:1000"`, os mesmos binds do HD do `worker` (com o sentinela), `depends_on`
    postgres e minio, sem porta publicada;
  - `api` e `agendador`: `extra_hosts: ["host.docker.internal:host-gateway"]` e
    `YOUTUBE_API_KEY: ${YOUTUBE_API_KEY:-}`, `ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}`,
    `OPENSHORTS_URL: ${OPENSHORTS_URL:-http://host.docker.internal:8000}`. O `worker` **não**
    recebe as chaves;
  - `imgproxy`: **acrescentar** a `IMGPROXY_ALLOWED_SOURCES` (lista separada por vírgula, sem
    trocar o que a 007 puser) `https://i.ytimg.com/,https://yt3.ggpht.com/,https://yt3.googleusercontent.com/`.
- [X] T005 [P] ⚠️ **COMPARTILHADO (só acréscimo)** Em `docker/nginx/default.conf.template`,
  acrescentar um bloco `location` próprio (regex) para `^/api/perfis/[^/]+/envios/arquivo$`, com
  `client_max_body_size 2100m`, `proxy_request_buffering off` e timeouts longos, como o de cortes
  da 004. Não mexer no bloco de assets da 007. Depois: `docker compose restart edge` (armadilha 13).
- [ ] T006 Passo do **dono** (manual, quickstart §0): copiar a chave do YouTube sem imprimir
  (`grep '^YOUTUBE_API_KEY=' ~/.config/openclaw/youtube.env >> .env`), colar a
  `ANTHROPIC_API_KEY` no `.env` com o editor, conferir com `grep -c` e `git check-ignore .env`.
  Se o `agendador` não alcançar `host.docker.internal:8000`, o dono decide a regra do ufw
  (`172.16.0.0/12 → 8000`).
  **Preparado pela Trilha 0 (2026-09-29):** `.env.example` e o compose já têm as variáveis; o
  `.env` da raiz ainda **não** tem as chaves (sem elas a trilha `sync` fica ociosa, com log). O
  `agendador` já alcança `http://host.docker.internal:8000/health` (200): não precisa de regra
  no ufw. Depois de pôr as chaves: `docker compose up -d api agendador`.

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Purpose**: migration, todos os modelos, esqueleto dos routers, notificações e o `agendador`
com as trilhas vazias. Feita por **um agente só** (Trilha 0), para que as trilhas A–D não
disputem `main.py`, `migrations/env.py`, `cli.py` e a migration.

**⚠️ CRITICAL**: nenhuma história começa antes do checkpoint desta fase.

- [X] T007 Criar `apps/api/migrations/versions/0006_cortes_openshorts.py`
  (`revision = "0006_cortes_openshorts"`, `down_revision = "0005_assets"`), com `downgrade`
  completo. Restrições do data-model, literalmente:
  - enums: `canal_direito` (`proprio`, `parceiro`, `programa_de_cortes`, `sem_acordo`),
    `canal_sync` (`pendente`, `sincronizando`, `ok`, `pausado_cota`, `erro`), `video_live`
    (`nenhum`, `ao_vivo`, `agendado`), `envio_origem` (`canal`, `avulso_link`,
    `avulso_arquivo`), `envio_status` (`selecionado`, `na_fila`, `aguardando_openshorts`,
    `confirmar_qualidade`, `processando`, `importando`, `pronto`, `sem_clipes`, `falhou`,
    `descartado`), `direito_envio` (`proprio`, `parceiro`, `programa_de_cortes`, `sem_acordo`,
    `avulso`), `corte_origem` (`upload`, `openshorts`), `postagem_estado` (`rascunho`,
    `agendado`, `postado`), `notificacao_tipo` (`envio_pronto`, `envio_sem_clipes`,
    `envio_falhou`, `envio_confirmar_qualidade`, `openshorts_fora`, `hora_de_postar`,
    `cota_youtube`, `canal_erro`); `corte_status` ganha **`revisao`** (antes de `na_fila`);
  - `canais_fonte`: `youtube_channel_id` text not null UNIQUE, `^UC[0-9A-Za-z_-]{22}$` (conta
    também os arquivados; 409 `canal_exists`); `direito` padrão `sem_acordo`;
    `direito_evidencia_url` http(s), até 500; `direito_evidencia_nota` not null default '', até
    2.000; `sync_status` padrão `pendente`; `sync_progress` jsonb not null default '{}';
    `next_sync_at` timestamptz not null default now(); `uploads_playlist_id` not null;
    `version`, `archived_at`, `archived_by` e AuditMixin;
  - `canal_perfis`: PK composta (`canal_id`, `perfil_id`), `created_at`, `created_by`;
  - `videos_fonte`: `youtube_video_id` text not null UNIQUE (11 caracteres); `description` not
    null default '' (cortada em 5.000); `disponivel` bool not null default true; `next_metrics_at`
    not null; `vph_recente` numeric(14,2) null; `score` numeric(5,1) not null default 0 (0–100);
    `score_reason` not null default ''; `score_detail` jsonb not null default '{}';
    `recomendavel` bool not null default false; `first_seen_at` not null default now(); índices
    `(canal_id, published_at desc)`, `(recomendavel, score desc)` e `(next_metrics_at)`;
  - `video_metricas`: `id` bigint identity PK, índice `(video_id, observed_at desc)`;
  - `youtube_cota`: `dia` date PK (fuso `America/Los_Angeles`), `unidades` int not null default
    0, `aviso_enviado` bool not null default false;
  - `padroes_corte`: `perfil_id` uuid not null UNIQUE; `clip_min_s` smallint not null 5–175;
    `clip_max_s` smallint not null 10–180, ≥ `clip_min_s` + 5; `quantidade` smallint null 1–15;
    `layout` in (`auto`, `none`, `split`, `screencast`, `speaker_cut`); `formato` in
    (`vertical`, `square`); `legenda` in (`kit`, `gerador`, `nenhuma`); `marca_automatica` bool
    not null; `conta_padrao_id` uuid null FK → contas.id; `version` e AuditMixin;
  - `envios`: colunas do data-model; `upload_key` UNIQUE; `status` padrão `selecionado`;
    `progress` smallint not null default 0 (0..100); `clips_importados` e `attempts` not null
    default 0; `aviso_confirmado` e `force_low_quality` bool not null default false; índices
    `(status, next_attempt_at)`, `(perfil_id, created_at desc)` e `(perfil_id, video_fonte_id)
    WHERE archived_at IS NULL` **não único**; checks: `origem = 'canal'` exige `video_fonte_id` e
    `source_url`; `origem = 'avulso_link'` exige `source_url`; `origem = 'avulso_arquivo'` exige
    `upload_key`; status além de `selecionado` exige `config` e `direito_no_envio`;
  - `cortes` (da 004): colunas `origem` (padrão `upload`), `envio_id` FK → envios.id,
    `clip_index`, `source_start_ms`, `source_end_ms`, `openshorts_title`,
    `openshorts_description`, `openshorts_score`, `transcript`, `legenda`, `archived_at`,
    `archived_by`; UNIQUE `(envio_id, clip_index)`; `kit_version` e `kit_tokens` anuláveis com o
    check `status = 'revisao' OR (kit_version IS NOT NULL AND kit_tokens IS NOT NULL)`;
  - `postagens`: `titulo` not null default '' (até 100); `descricao` not null default '' (até
    2.000); `hashtags` text[] not null default '{}'; `estado` padrão `rascunho`; índice único
    parcial `(corte_id, conta_id) WHERE archived_at IS NULL`; check `estado <> 'agendado' OR
    planned_at IS NOT NULL`;
  - `sugestoes_texto`: `ajustes` text[] not null default '{}'; `duration_ms` not null; só
    INSERT;
  - `notificacoes`: `id` bigint identity PK; `dedupe_key` not null com UNIQUE `(user_id,
    dedupe_key)`; `corpo` not null default ''; índice `(user_id, id desc)` e parcial `(user_id)
    WHERE lida_em IS NULL`.
- [X] T008 [P] Criar `apps/api/src/sociman_api/canais/__init__.py` e `canais/models.py`:
  `CanalFonte` (versionado, `__versioned_fields__` = `title`, `handle`, `direito`,
  `direito_evidencia_url`, `direito_evidencia_nota`, `perfil_ids`, `archived`;
  `__immutable_fields__` = `title`, `handle`, só exibição), `CanalPerfil`, `VideoFonte`,
  `VideoMetrica`, `YoutubeCota`, com os enums.
- [X] T009 [P] Criar `apps/api/src/sociman_api/envios/__init__.py` e `envios/models.py`:
  `PadroesCorte` (snapshot com todos os campos) e `Envio` (snapshot só de ações humanas:
  `status`, `config`, `direito_no_envio`, `aviso_confirmado`, `source_title`, `source_url`,
  `canal_fonte_id`, `video_fonte_id`, `origem`, `archived`), com os enums `EnvioOrigem`,
  `EnvioStatus`, `DireitoEnvio`.
- [X] T010 [P] Ampliar `apps/api/src/sociman_api/cortes/models.py`: status `revisao`, colunas
  novas, `kit_version`/`kit_tokens` anuláveis; snapshot versionado passa a `hook_text`,
  `kit_version`, `status`, `archived`. `hook_text` continua not null e aceita `''` em `revisao`.
  O `queue.claim` e o `worker.py` **não mudam** (continuam pegando só `na_fila`).
- [X] T011 [P] Criar `apps/api/src/sociman_api/postagem/__init__.py` e `postagem/models.py`:
  `Postagem` (snapshot `conta_id`, `titulo`, `descricao`, `hashtags`, `estado`, `planned_at`,
  `posted_url`, `archived`) e `SugestaoTexto` (só INSERT), com `EstadoPostagem`.
- [X] T012 [P] Criar `apps/api/src/sociman_api/notificacoes/__init__.py` e
  `notificacoes/models.py`: `Notificacao` e o enum `NotificacaoTipo`.
- [X] T013 Registrar os modelos novos em `apps/api/migrations/env.py` (imports `# noqa: F401`) e
  criar `apps/api/tests/integration/test_migration_0006.py`: `alembic upgrade head` e
  `downgrade -1` limpos; os checks de `envios` (canal sem `video_fonte_id` → IntegrityError), de
  `cortes` (`na_fila` sem kit → erro; `revisao` sem kit → ok) e o único parcial de `postagens`;
  cortes antigos ficam com `origem = 'upload'`.
- [X] T014 Criar os routers vazios (`APIRouter` com prefixo e tags) em `canais/router.py`,
  `envios/router.py`, `postagem/router.py`, `notificacoes/router.py` e
  `apps/api/src/sociman_api/integracoes.py`, e incluí-los em `apps/api/src/sociman_api/main.py`.
  Depois desta tarefa, **só a Trilha 0 mexe em `main.py`**.
- [X] T015 Implementar `notificacoes/service.py` (`criar(db, tipo, titulo, corpo, link, entidade,
  dedupe_key, destinatarios)` com `INSERT … ON CONFLICT (user_id, dedupe_key) DO NOTHING`;
  `destinatarios_padrao(autor)` = autor + donos ativos, sem repetir; `listar(after, limit=30,
  nao_lidas)`; `marcar_lidas(ids | todas)` só preenche `lida_em`, nunca apaga),
  `notificacoes/schemas.py` e as rotas `GET /api/notificacoes` e `POST /api/notificacoes/lidas`
  (`operationId` `notificacoes_*`, `RequireUser`, só as do usuário logado).
- [X] T016 [P] Criar `apps/api/tests/integration/test_notificacoes.py`: dedupe (duas chamadas, uma
  linha), destinatários (autor + donos, sem repetir), cursor `after`, `naoLidas`, marcar lidas
  (ids e todas), isolamento entre usuários.
- [X] T017 Criar `apps/api/src/sociman_api/agendador.py` e o comando `sociman agendador` em
  `cli.py` (R1): `pg_try_advisory_lock(0x50C1)` (a segunda instância espera, sem trabalhar);
  uma thread por trilha, cada uma com sessão própria, laço `try/except` por volta (a exceção vai
  para o log e não derruba o processo) e intervalo da config; SIGTERM encerra limpo; log "agendador
  pronto (lock ok): trilhas sync, openshorts, importacao, lembretes". As trilhas chamam
  `canais.sync.rodar`, `envios.acompanhamento.rodar`, `envios.importacao.rodar` e
  `postagem.lembretes.rodar`: criar esses quatro módulos **como stubs sem efeito**, que as
  trilhas A, B e C preenchem depois. A trilha `importacao` não pega nada sem o sentinela do HD.
- [X] T018 [P] Criar `apps/api/tests/integration/test_agendador.py`: o lock impede a segunda
  instância; uma exceção numa trilha não para as outras; o encerramento limpo solta o lock.
- [X] T019 Padrão de testes das integrações: criar `apps/api/tests/fakes/__init__.py` e
  documentar nele que cada cliente HTTP (`canais/youtube.py`, `envios/openshorts.py`,
  `postagem/textos.py`) recebe o transporte por injeção (fábrica `get_*_client()` +
  `app.dependency_overrides` nas rotas e parâmetro no agendador). As fixtures dos fakes ficam em
  `tests/fakes/<nome>_fake.py` e são importadas pelos testes; **nenhuma trilha mexe em
  `tests/integration/conftest.py` depois desta tarefa**.

**Checkpoint**: `npm run test:api -- tests/integration/test_migration_0006.py
tests/integration/test_notificacoes.py tests/integration/test_agendador.py` verde, ruff limpo e
`docker compose up -d agendador` mostrando o log de pronto. As trilhas A, B, C e D começam.

---

## Phase 3: User Story 1 - Cadastrar canais-fonte (Priority: P1) 🎯 MVP

**Goal**: cadastrar canais do YouTube por link, `@` ou ID, com status de direito que só o dono
muda, ligação a perfis, histórico, arquivamento e reversão.

**Independent Test**: colar `https://www.youtube.com/@theitnerd`, ver nome e avatar (via `/img`),
marcar "Próprio" como dono e ligar ao perfil A Taverna Nerd; como membro, o direito fica só
leitura e o `PUT …/direito` responde 403.

### Tests for User Story 1

- [X] T020 [P] [US1] Criar `apps/api/tests/fixtures/youtube/*.json` (respostas gravadas **sem a
  chave**: `channels` por id/forHandle/forUsername, `search`, `playlistItems` paginado, `videos`,
  erros `keyInvalid`, `accessNotConfigured`, `quotaExceeded`) e
  `apps/api/tests/fakes/youtube_fake.py` (MockTransport com estado, que registra os pedidos).
- [X] T021 [P] [US1] Criar `apps/api/tests/unit/test_resolve.py`: cada entrada da tabela de R2
  (`UC…` de 24, `/channel/UC…`, `@handle`, `youtube.com/@handle`, `/user/`, `/c/` e nome solto,
  links de vídeo `watch?v=`, `youtu.be/`, `shorts/`) vira a consulta certa com o custo certo
  (1, 1, 1, 100, 2); entrada inválida → `invalid_channel_input`.
- [X] T022 [P] [US1] Criar `apps/api/tests/unit/test_youtube_client.py`: só `GET` em `channels`,
  `playlistItems`, `videos` e `search` (lista fechada, princípio I); a cota é somada **antes** da
  chamada (`UPDATE … RETURNING`); 80% → uma notificação `cota_youtube` por dia (`aviso_enviado`);
  95% → sinaliza pausa da sync; 100% → 429 `youtube_quota` com o horário de renovação em
  `APP_TZ`; `403 quotaExceeded` encerra o dia; `key=…` vira `key=***` em qualquer texto de erro e
  a chave nunca aparece em log.
- [X] T023 [P] [US1] Criar `apps/api/tests/integration/test_canais.py`: `resolver` sem gravar
  (com `existente` quando já cadastrado); `POST /api/canais` 201 com sync `pendente` e
  `next_sync_at = now`; 409 `canal_exists` com `details.id`, **contando os arquivados** (US1-2);
  `PATCH` perfis (versão `updated` com `perfil_ids`; perfil arquivado → 400); `PUT …/direito`:
  membro → 403, dono → 200 com versão (autor, antes e depois) (US1-3); archive/restore; `revert`
  só pelo dono, recriando as ligações e ignorando `title`/`handle`; 503 `youtube_unconfigured`
  sem chave; 429 `youtube_quota`; 502 `youtube_error` sem a chave na mensagem; `avatarUrl` via
  `/img`.

### Implementation for User Story 1

- [X] T024 [P] [US1] Criar `apps/api/src/sociman_api/canais/resolve.py` (puro): link/`@`/`UC` →
  consulta e custo, conforme a tabela de R2.
- [X] T025 [US1] Criar `apps/api/src/sociman_api/canais/youtube.py`: cliente `httpx` só `GET`,
  base `settings.youtube_api_url`, `params` com a chave, constante `ALLOWED` (método + recurso),
  controle de cota em `youtube_cota` (dia no fuso `America/Los_Angeles`, limites 80/95/100% de
  `YT_QUOTA_DAILY`), hook de redação `key=***`, erros tipados (`youtube_unconfigured`,
  `youtube_quota`, `youtube_error`, `canal_not_found`). Log só `endpoint + custo + status`.
- [X] T026 [P] [US1] ⚠️ **COMPARTILHADO (só acréscimo)** Em
  `apps/api/src/sociman_api/imaging.py`, acrescentar `remote_url(url, w, h)` →
  `/img/<assinatura|unsafe>/rs:fill:w:h/f:webp/<base64url(url)>`, só para URLs das origens
  `https://i.ytimg.com/`, `https://yt3.ggpht.com/` e `https://yt3.googleusercontent.com/` (outra
  origem → `None`). Não alterar as funções existentes. Teste novo em
  `apps/api/tests/unit/test_imaging_remote.py` (não mexer em `test_imaging.py`).
- [X] T027 [US1] Criar `apps/api/src/sociman_api/canais/schemas.py` (`CanalFonte`, `Direito`,
  entradas de `resolver`, `criar`, `PATCH`, `direito`, `revert`; camelCase; evidência URL
  http(s) até 500, nota até 2.000).
- [X] T028 [US1] Criar `apps/api/src/sociman_api/canais/service_canais.py`: resolver, criar
  (sync `pendente`, `next_sync_at = now()`), listar (`archived?`, `perfilId?`, `q?`), obter,
  ligar/desligar perfis, `mudar_direito` (só dono), arquivar/restaurar, versões e reverter (só
  dono), tudo com `history.record` na mesma transação e `version` (409 `version_conflict`).
  Canal arquivado sai da sync e da descoberta; vídeos e envios ficam.
- [X] T029 [US1] Preencher `apps/api/src/sociman_api/canais/router.py` com as rotas de
  `contracts/http-api.md` → Canais (menos `sincronizar`, que é da US2), `operationId`
  `canais_*`, `RequireOwner` em `direito` e `revert`, sem `youtube` no caminho nem no
  `operationId`.
- [X] T030 [P] [US1] (SPA) Criar `apps/web/src/lib/canais.ts` (hooks TanStack Query sobre o
  contrato gerado) e `apps/web/src/components/canais/{DireitoBadge,CanalForm}.tsx` (colar →
  prévia com custo em unidades → perfis → salvar; "Este canal já está cadastrado" com link para o
  existente; selo de aviso em `sem_acordo`).
- [X] T031 [US1] (SPA) Criar `apps/web/src/pages/canais/{CanaisList,CanalDetalhe}.tsx` (`/app/fontes`
  e `/app/fontes/:id`: avatar, nome, inscritos, vídeos, selo de direito, perfis, estado da sync,
  direito editável só pelo dono com evidência, histórico); acrescentar as rotas em
  ⚠️ **COMPARTILHADO (só acréscimo)** `apps/web/src/App.tsx` e o item "Canais-fonte" em
  ⚠️ **COMPARTILHADO (só acréscimo)** `apps/web/src/components/shell/nav.ts`.

**Checkpoint**: US1 testável sozinha (pytest da US1 verde; tela Fontes funcionando com o YouTube
real no dev).

---

## Phase 4: User Story 2 - Descobrir e escolher os vídeos (Priority: P1)

**Goal**: o `agendador` busca todos os vídeos dos canais, calcula a pontuação explicável e a tela
Descobrir filtra, ordena e seleciona (inclusive avulso por link ou arquivo).

**Independent Test**: com dois canais, abrir Descobrir, ver os vídeos ordenados com o motivo,
filtrar "até 20 min" e "não cortados" e selecionar três vídeos; colar um link avulso e ver o
aviso de direito.

### Tests for User Story 2

- [X] T032 [P] [US2] Criar `apps/api/tests/unit/test_score.py` (R3): pesos 0,45/0,20/0,15/0,20;
  `V = min(1, ln(1 + r) / ln(9))` com `r` relativo à mediana dos 50 mais recentes do canal;
  `E` com `likes + 3 × comentários` (likes ocultos = 0); `R = exp(−dias/30)`; tabela de `D`;
  zeram e saem da recomendação: indisponível, ao vivo ou agendado, > 3 h, < 45 s; motivo em uma
  linha pelo componente de maior contribuição (templates de R3); o direito **não** entra na
  conta.
- [X] T033 [P] [US2] Criar `apps/api/tests/integration/test_sync.py`: 1ª sync pagina a playlist
  de uploads (2 unidades a cada 50 vídeos) com commit por página e `sync_progress`; incremental
  para no primeiro vídeo conhecido e não duplica; métricas por idade (+1 h ≤ 7 d, +24 h ≤ 60 d,
  +7 d) gravando `video_metricas` e `vph_recente` (leituras com ≥ 6 h); id sumido →
  `disponivel = false`; cota em 95% → `pausado_cota` (com `YT_QUOTA_DAILY=40`) e notificação em
  80%; `keyInvalid` → canal `erro` com mensagem sem a chave e notificação `canal_erro`; canal
  arquivado não sincroniza.
- [X] T034 [P] [US2] Criar `apps/api/tests/integration/test_descoberta.py`: filtros de
  `GET /api/videos-fonte` (canal repetível, perfil, `q`, período, duração, `recomendaveis`
  padrão true, `naoCortados` exige `perfilId` → 400 sem ele); ordens `score|views|vph|data`
  estáveis por `(ordem, id)` com cursor opaco; `jaCortado` e `selecionado` por perfil; score
  exibido × 0,3 quando já cortado para o perfil do filtro; `GET /api/videos-fonte/{id}` com as
  últimas 50 métricas; `POST /api/canais/{id}/sincronizar` (409 `sync_running`, 429).
- [X] T035 [P] [US2] Criar `apps/api/tests/integration/test_selecao.py` (Trilha B; insere
  `videos_fonte` direto pelo modelo, sem depender da Trilha A): `POST /api/perfis/{id}/envios`
  com `videoFonteId` → 201 `selecionado`; 409 `already_selected` / `already_sent` com
  `details.envioId` sem `confirmarDuplicado`, e com ele cria outro (histórico
  `details.duplicado = true`); 409 `video_unavailable`; avulso por link (400 `invalid_url`); 409
  `perfil_archived`; `POST …/envios/arquivo`: 413 acima de 2 GB, 400 `invalid_video` (não é vídeo,
  < 45 s, > 3 h), 503/507 sem HD, objeto em `sociman-videos` `envios/{id}/fonte.<ext>`;
  `POST /api/envios/{id}/archive` em `selecionado` → `descartado` (sem apagar).

### Implementation for User Story 2

- [X] T036 [P] [US2] Criar `apps/api/src/sociman_api/canais/score.py` (puro, pesos como
  constantes num só lugar), com `score`, `score_reason` e `score_detail` (`{v, e, r, d,
  componente, valores}`).
- [X] T037 [US2] Implementar `apps/api/src/sociman_api/canais/sync.py` e a função `rodar` da
  trilha `sync` (substitui o stub da T017): 1ª sync, incremental a cada `SYNC_NOVOS_H`, métricas
  por faixa de idade, disponibilidade, recálculo da pontuação, estados de `canal_sync`, pausa da
  cota e retry de 1 h em `erro`.
- [X] T038 [US2] Criar `apps/api/src/sociman_api/canais/service_videos.py` e as rotas
  `GET /api/videos-fonte`, `GET /api/videos-fonte/{id}` (`operationId` `videos_fonte_*`) e
  `POST /api/canais/{id}/sincronizar` em `canais/router.py`; miniaturas via `imaging.remote_url`.
- [X] T039 [US2] Criar `apps/api/src/sociman_api/envios/schemas.py`,
  `envios/service_envios.py` (selecionar, avulso por link, descartar, listar, obter, versões) e
  `envios/upload.py` (R16): generalizar o recebimento em streaming de
  `apps/api/src/sociman_api/cortes/service.py` para aceitar limite e prefixo, **sem mudar o
  comportamento da 004** (os testes de `test_cortes.py` continuam verdes); até 2 GB; ffprobe de
  45 s a 3 h; HD conferido antes de ler o corpo.
- [X] T040 [US2] Preencher `apps/api/src/sociman_api/envios/router.py`:
  `POST /api/perfis/{id}/envios`, `POST /api/perfis/{id}/envios/arquivo`, `GET /api/envios`,
  `GET /api/envios/{id}`, `POST /api/envios/{id}/archive` e `GET /api/envios/{id}/versions`
  (`operationId` `envios_*`).
- [X] T041 [P] [US2] (SPA) Criar `apps/web/src/components/canais/{VideoCard,ScoreReason}.tsx`
  (miniatura, título, canal, duração, publicação, views, views/h, pontuação, motivo e "Por quê?"
  com `scoreDetail`) e `apps/web/src/lib/envios.ts` (seleção e avulso).
- [X] T042 [US2] (SPA) Criar `apps/web/src/pages/descobrir/Descobrir.tsx` (`/app/descobrir`):
  seletor de perfil, filtros (canal, período, duração, "não cortados", texto), `DataTable` com
  paginação no servidor (`dataTableColumns<T>()`, TanStack Table v9), "Selecionar para corte" em
  um clique e desfazível, seleção em lote, selo "Já cortado para <perfil>", "mostrar não
  recomendados", "Colar link" e "Enviar arquivo", barra fixa "N selecionados → Enviar para
  corte"; mensagem clara quando o YouTube não está configurado; rota em ⚠️ `App.tsx` e item
  "Descobrir" em ⚠️ `nav.ts` (**só acréscimo**).

**Checkpoint**: US1 + US2 funcionando; a lista de Selecionados existe no banco.

---

## Phase 5: User Story 3 - Configurar e enviar ao OpenShorts (Priority: P1)

**Goal**: padrões de corte por perfil, envio com o aviso de direito exigido pela API,
acompanhamento que sobrevive a reinícios e notificações no app.

**Independent Test**: selecionar um vídeo, conferir a configuração pré-preenchida, enviar, ver
"Na fila → Processando → Pronto" e receber a notificação no sino.

### Tests for User Story 3

- [X] T043 [P] [US3] Criar `apps/api/tests/integration/test_padroes_corte.py`: `GET` sem linha →
  padrão (15, 60, null, `auto`, `vertical`, `kit`, false, null) com `version: 0`; `PUT` cria a v1;
  400 `invalid_padroes` com `field` para cada faixa (`clip_min_s` 5–175, `clip_max_s` 10–180 e ≥
  mín + 5, `quantidade` 1–15 ou null, valores de `layout`, `formato`, `legenda`,
  `conta_padrao_id` de outro perfil ou arquivada); 409 `version_conflict`; versões; `revert` só
  pelo dono (403 para membro).
- [X] T044 [P] [US3] Criar `apps/api/tests/integration/test_enviar.py`: `POST /api/envios/enviar`
  tudo ou nada (até 20 itens); 409 `aviso_direito` com `details.envioIds` quando há `sem_acordo`
  ou avulso sem `confirmarAviso`, **sem enviar nenhum**; **membro** com `confirmarAviso: true` →
  200 (Q3 = A) e a versão registra o membro como autor; `proprio` sem aviso; `config` = padrões do
  perfil + override + `subtitle` do kit (se `legenda = kit`) + `kit_version`; versão "enviar" com
  `direito_no_envio`, `aviso_confirmado`, fonte e `details {duplicado, canal_direito_atual}`; 409
  `already_sent`, `invalid_config`, `version_conflict`, `conflict`; `confirmar-qualidade`
  (`enviar: true` → `na_fila` com `force_low_quality`; false → `descartado`); `retry` de
  `falhou`.
- [X] T045 [P] [US3] Criar `apps/api/tests/unit/test_openshorts_client.py` (o arquivo
  `test_openshorts.py` é da exportação da 004 e não muda): o cliente só chama `/health`,
  `/api/process`, `/api/uploads`, `/api/status`, `/api/subtitle`, `/api/clip/*/transcript` e
  `/videos/*`; `download()` recusa caminho fora de `/videos/`; corpo do `/api/process` com
  `acknowledged: true`, `auto_hook: false`, `captions` (false com legenda do kit ou nenhuma, true
  com "gerador"), `layouts`, `output_format`, `clip_min_seconds`, `clip_max_seconds` e
  `target_clips` omitido quando null.
- [X] T046 [P] [US3] Criar `apps/api/tests/fakes/openshorts_fake.py`: OpenShorts falso com
  estado (fila, `queued → processing → completed`, `needs_confirmation`, 429, 5xx e conexão
  recusada ligáveis, 404 depois da "retenção", `failed` com "No clips could be rendered",
  `/api/subtitle`, transcript e `/videos/*` servindo MP4 sintéticos gerados com ffmpeg).
- [X] T047 [US3] Criar `apps/api/tests/integration/test_agendador_openshorts.py` (depende da
  T046): `na_fila` → `processando` com `openshorts_job_id`; upload do avulso por arquivo
  (`POST /api/uploads` + `PUT` em streaming do MinIO, sem usar o `upload_url` devolvido); fila
  (`queue_pos`), progresso estimado com teto de 90%; `needs_confirmation` →
  `confirmar_qualidade` + notificação, **sem reenviar sozinho**; 429 → `na_fila` +60 s; 400/403 →
  `falhou` com `detail` traduzido; fora do ar → `aguardando_openshorts` com backoff 30 s → 1 → 2 →
  5 min e volta sozinho (US3-5); 30 min fora → uma `openshorts_fora`; 404 → `falhou` ("O
  OpenShorts não tem mais este job; envie de novo"); "No clips" → `sem_clipes` + notificação;
  reinício do agendador continua o polling; `envio_falhou` notifica em < 1 min (SC-003).

### Implementation for User Story 3

- [X] T048 [US3] Criar `apps/api/src/sociman_api/envios/service_padroes.py` (padrão preguiçoso
  como o kit: get/put/versões/reverter) e as rotas `GET|PUT /api/perfis/{id}/padroes-corte`,
  `GET …/padroes-corte/versions` e `POST …/padroes-corte/revert` (`RequireOwner`) em
  `envios/router.py`. O gancho automático **não é campo** (sempre desligado).
- [X] T049 [US3] Criar `apps/api/src/sociman_api/envios/openshorts.py`: cliente `httpx` com
  `ALLOWED` (lista fechada) e só `health()`, `process()`, `reserve_upload()`, `put_upload()`,
  `status()`, `subtitle()`, `transcript()` e `download(video_url)` (prefixo `/videos/`), **sem
  `/api/social/*`, `/api/thumbnail/publish` nem `/api/saasshorts/post`**.
- [X] T050 [US3] Em `envios/service_envios.py` e `envios/router.py`: `enviar` (aviso 409
  `aviso_direito`, duplicado, resolução da `config` com a seção `openshorts.subtitle` do kit via
  `marca/openshorts.py`, `direito_no_envio`, versão "enviar"), `confirmar-qualidade` e `retry`
  (`falhou` → `na_fila` com job novo). Dono e membro enviam (Q3 = A).
- [X] T051 [US3] Implementar `apps/api/src/sociman_api/envios/acompanhamento.py` e a função
  `rodar` da trilha `openshorts` (substitui o stub da T017): submissão, polling a cada 10 s,
  backoff em `next_attempt_at`, tabela de respostas de R6 e as notificações `envio_falhou`,
  `envio_sem_clipes`, `envio_confirmar_qualidade` e `openshorts_fora`, com `dedupe_key`.
- [X] T052 [P] [US3] (SPA) Criar `apps/web/src/lib/notificacoes.ts` e
  `apps/web/src/components/notificacoes/{Sino,useNotificacoes}.tsx`: polling de
  `GET /api/notificacoes?after=` a cada 20 s com a aba visível e 60 s em segundo plano, refetch ao
  focar, contagem, lista, "Marcar todas como lidas", clique navega para o `link`; "Avisar também
  pelo navegador" pede a permissão por gesto e usa `registration.showNotification` com o service
  worker ou `new Notification`, **só com o app aberto** (Q1 = A, sem Web Push); último id no
  `localStorage` (com try/catch) e trava por `BroadcastChannel`. Pôr o sino em
  `apps/web/src/components/shell/Topbar.tsx`.
- [X] T053 [P] [US3] (SPA) Criar `apps/web/src/pages/perfis/tabs/PadroesCorteTab.tsx` (formulário
  com `Field`/`NativeSelect`, histórico e "Reverter" só para o dono) e acrescentar **uma linha**
  no array de abas de ⚠️ **COMPARTILHADO (só acréscimo)**
  `apps/web/src/pages/perfis/PerfilDetalhe.tsx`.
- [X] T054 [US3] (SPA) Criar `apps/web/src/pages/envios/EnviosList.tsx` (`/app/envios`: abas
  Selecionados, por perfil, e Envios com status ao vivo e polling de 5 s enquanto houver envio em
  andamento) e `apps/web/src/components/envios/{EnviarDialog,AvisoDireito,EnvioStatus}.tsx`
  (padrões do perfil editáveis; aviso "O direito autoral deste vídeo é de sua responsabilidade"
  com confirmação, em AlertDialog `role="alertdialog"`; confirmação de duplicado; "Enviar mesmo
  assim"/"Descartar" em `confirmar_qualidade`; "Tentar de novo"); rota em ⚠️ `App.tsx` e item
  "Envios" em ⚠️ `nav.ts` (**só acréscimo**).

**Checkpoint**: US3 testável com o OpenShorts falso (pytest) e com o real no dev (quickstart §3
e §4).

---

## Phase 6: User Story 4 - Clipes gerados viram cortes do perfil (Priority: P1)

**Goal**: importar os clipes com a legenda do kit como cortes em `revisao`, revisar lado a lado,
arquivar e aplicar a marca (manual ou automática) pela fila da 004 sem mudanças no worker.

**Independent Test**: com um envio pronto, abrir o envio, ver os N clipes com player, arquivar um,
aplicar a marca nos outros e vê-los na aba Cortes do perfil.

### Tests for User Story 4

- [X] T055 [P] [US4] Criar `apps/api/tests/integration/test_importacao.py` (ffmpeg real, OpenShorts
  falso da T046): todos os clipes de `result.clips` viram cortes `revisao` com `origem =
  openshorts`, `envio_id`, `clip_index`, trecho, `hook_text` do `viral_hook_text` (cortado em
  120), textos e score do OpenShorts, transcrição (até 4.000) e `legenda`; com `legenda = kit`, o
  `/api/subtitle` recebe o `config.subtitle` do envio; clipe sem fala → `legenda = sem_fala`;
  idempotência (reinício no meio não duplica: UNIQUE `(envio_id, clip_index)`); sem o sentinela o
  envio fica em `importando`; 404 do clipe → `falhou` ("Os clipes expiraram no OpenShorts"),
  mantendo os já importados; 3 erros → `falhou` e "Importar de novo" pelo `retry`; versão
  `created` com `actor_kind = system:agendador`; `envio_pronto` para autor e donos; marca
  automática → `na_fila` com `kit_version`/`kit_tokens`; arquivos em `sociman-videos`
  `perfis/{p}/cortes/{corte_id}/original.mp4` (SC-004).
- [X] T056 [P] [US4] Criar `apps/api/tests/integration/test_cortes_revisao.py`: `PATCH
  /api/cortes/{id}` só em `revisao` (400 `invalid_hook`: 1..120 e até 3 linhas com o gancho
  ligado no kit); `POST /api/cortes/aplicar-marca` (até 30; 409 `conflict` fora de `revisao`;
  `invalid_hook` com `details.corteId`; 503/507 sem HD); archive/restore (409 em `processando`);
  `GET /api/perfis/{id}/cortes` com `origem?`, `envioId?`, `archived?` (padrão false); o worker da
  004 continua pegando só `na_fila` (`test_queue.py` e `test_worker.py` seguem verdes).

### Implementation for User Story 4

- [X] T057 [US4] Ampliar `apps/api/src/sociman_api/cortes/{schemas,service,router}.py`:
  `aplicar_marca` (resolve o kit atual, `revisao → na_fila`, lote até 30), editar gancho,
  arquivar/restaurar e os filtros novos; campos novos no `Corte` (origem, envio, trecho, textos do
  OpenShorts, `legenda`, `canal`, `direitoNoEnvio`, `archived`, `postagens` como lista vazia até a
  US5). Sem mudar `worker.py`, `queue.py` nem `compose.py`.
- [X] T058 [US4] Implementar `apps/api/src/sociman_api/envios/importacao.py` e a função `rodar`
  da trilha `importacao` (substitui o stub da T017): `FOR UPDATE SKIP LOCKED`, um envio por vez,
  os passos 1–7 de R7 (legenda do kit, download em streaming para `work/envios/{id}/clip-{i}.mp4`
  com o piso de espaço, ffprobe, MinIO, transcrição, linha `cortes`, marca automática pelo mesmo
  serviço da T057), `pronto` com `clips_total`/`clips_importados` e a notificação `envio_pronto`;
  `retry` de `falhou` volta a `importando` quando o job ainda existe e faltam clipes.
- [X] T059 [US4] (SPA) Criar `apps/web/src/pages/envios/EnvioDetalhe.tsx` (`/app/envios/:id`) e
  `apps/web/src/components/envios/ClipReview.tsx`: clipes lado a lado (player com o link assinado
  da 004, trecho, gancho editável, título e score do OpenShorts), "Arquivar", "mostrar
  arquivados", "Aplicar marca" em um, vários ou todos, status da marca por clipe; rota em
  ⚠️ `App.tsx` (**só acréscimo**).
- [X] T060 [P] [US4] (SPA) Em `apps/web/src/pages/perfis/tabs/CortesTab.tsx` e
  `apps/web/src/pages/cortes/CorteDetalhe.tsx`: origem "OpenShorts", canal, trecho, estado
  `revisao`, filtro de arquivados.

**Checkpoint**: as quatro histórias P1 fecham o fluxo canal → vídeo → OpenShorts → corte com a
marca. Pode ir ao dono antes da US5 (plan.md).

---

## Phase 7: User Story 5 - Preparar a postagem e agendar (Priority: P2)

**Goal**: sugestão de textos com o Claude, uma postagem por conta de destino (Q2 = A), calendário
com arrastar e o aviso "Hora de postar". Nada é publicado.

**Independent Test**: num corte pronto, "Sugerir textos", editar o título, escolher a conta TikTok
e amanhã às 19:00; ver no calendário; na hora, receber "Hora de postar" com copiar e baixar.

### Tests for User Story 5

- [X] T061 [P] [US5] Criar `apps/api/tests/fixtures/anthropic/*.json` e
  `apps/api/tests/fakes/anthropic_fake.py` (MockTransport passado ao SDK por `http_client`), com
  resposta válida, fora dos limites, recusa (`stop_reason == "refusal"`), timeout e erro de API.
- [X] T062 [P] [US5] Criar `apps/api/tests/unit/test_textos.py`: `messages.parse` com
  `output_format` Pydantic, `output_config={"effort": "low"}`, **sem `temperature`** e sem
  desligar `thinking`; prompt em três partes (system fixo; bloco do perfil com `cache_control`
  `ephemeral`; user com a transcrição dentro de `<transcricao>…</transcricao>` e o aviso de não
  seguir instruções dela); "Outra versão" leva as sugestões anteriores; validação: título ≤ 100,
  descrição ≤ 2.000, hashtags normalizadas (`#`, sem espaço nem pontuação, minúsculas, sem
  repetir) entre 3 e 8; uma nova tentativa com o erro; depois corta e completa, e com menos de 3
  hashtags → `textos_invalidos`.
- [X] T063 [P] [US5] Criar `apps/api/tests/integration/test_sugestoes.py`:
  `POST /api/cortes/{id}/sugestoes` (plataforma da conta), 503 `claude_unconfigured`, 504
  `textos_timeout`, 502 `textos_invalidos`/`claude_error` com mensagem em pt-BR; cada chamada
  grava `sugestoes_texto` (modelo, `prompt_version`, tokens, duração, resultado ou erro); a
  sugestão **não altera** a postagem; `GET …/sugestoes` mais recentes primeiro.
- [X] T064 [P] [US5] Criar `apps/api/tests/integration/test_postagens.py`: criar por conta (a
  conta precisa ser do perfil do corte e não arquivada); 409 `postagem_exists` (único parcial);
  duas contas → duas postagens independentes (Q2 = A); `plannedAt` → `agendado`, `null` →
  `rascunho`; 409 `corte_not_ready` (agendar fora de `pronto`; rascunho em `revisao` ok); 400
  `planned_in_past` (tolerância de 1 min); hashtags `^#[\p{L}0-9_]{1,50}$`, 0..8 ao salvar;
  `POST …/postado` (qualquer usuário logado, `posted_at`, link opcional) e 409 ao editar depois
  de `postado`; archive/restore; versões (histórico dos textos, US5-2); `revert` só pelo dono (não desfaz `postado`);
  `GET /api/calendario` (`de`/`ate` locais até 62 dias, `perfilId`, `plataforma`, `semData`) com
  fuso `APP_TZ` via `zoneinfo`.
- [X] T065 [P] [US5] Criar `apps/api/tests/integration/test_lembretes.py`: a trilha `lembretes`
  cria **uma** `hora_de_postar` (autor + donos) para `agendado AND planned_at <= now() AND
  lembrado_em IS NULL` e marca `lembrado_em` na mesma transação; remarcar zera `lembrado_em`;
  dedupe `hora_de_postar:<postagem>:<planned_at>`; nenhum caminho do agendador muda o estado
  para `postado`.

### Implementation for User Story 5

- [X] T066 [US5] Criar `apps/api/src/sociman_api/postagem/textos.py` (R9): cliente `anthropic`
  com `timeout=20 s` e `max_retries=1`, modelo `settings.textos_model`, `fallbacks: "default"`
  com a beta `server-side-fallback-2026-07-01`, `prompt_version = "textos/1"`, validação e
  normalização; recusa final → "O Claude não sugeriu textos para este clipe; escreva à mão".
- [X] T067 [US5] Criar `apps/api/src/sociman_api/postagem/{schemas,service}.py` e preencher
  `postagem/router.py` com as rotas de `contracts/http-api.md` → Postagens (sugestões, CRUD,
  `postado`, archive/restore, versões, `revert` do dono e `GET /api/calendario`), `operationId`
  `postagens_*`. `EstadoPostagem.postado` só é atribuído em `service.marcar_postado`. O
  `Corte.postagens` (T057) passa a vir preenchido.
- [X] T068 [US5] Implementar `apps/api/src/sociman_api/postagem/lembretes.py` e a função `rodar`
  da trilha `lembretes` (substitui o stub da T017).
- [X] T069 [P] [US5] (SPA) Criar `apps/web/src/lib/postagem.ts` e `apps/web/src/lib/tz.ts`
  (exibição e entrada em `America/Sao_Paulo`, ISO com offset).
- [X] T070 [US5] (SPA) Em `apps/web/src/pages/cortes/CorteDetalhe.tsx`, seção **Postagem**: uma
  aba por conta de destino; "Sugerir textos"/"Outra versão"; título (contador 100), descrição
  (2.000), hashtags em chips (3–8 recomendadas); data e hora; "Salvar"; "Copiar título /
  descrição / hashtags / tudo"; "Baixar vídeo" (`POST /api/midia/links`, kind `corte_marcado`,
  `download=1`); "Marcar como postado" (link opcional); histórico.
- [X] T071 [US5] (SPA) Criar `apps/web/src/pages/calendario/Calendario.tsx` (`/app/calendario`):
  semana (padrão) e mês em CSS grid, sem biblioteca; filtros de perfil e plataforma; cor do perfil
  e `PlatformIcon`; coluna "Prontos sem data"; arrastar nativo HTML5 com encaixe de 15 min,
  `PATCH` otimista com desfazer no 409; toque → diálogo "Remarcar"; rota em ⚠️ `App.tsx` e item
  "Calendário" em ⚠️ `nav.ts` (**só acréscimo**).

**Checkpoint**: as cinco histórias funcionam; nada publica.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: integrações, guardas dos princípios, e2e na stack isolada, contrato e docs.

- [X] T072 Criar a rota `GET /api/integracoes` em `apps/api/src/sociman_api/integracoes.py`
  (`RequireUser`): `youtube` (`ok`/`ausente`/`invalida`, esta derivada do último erro de chave
  registrado em `canais_fonte.sync_error`), `openshorts` (`/health` pelo cliente da T049, timeout
  de 2 s e cache de 30 s), `claude` (`ok`/`ausente`) e `cotaYoutube {usadas, limite, renovaEm}`,
  **sem nenhum valor de chave**; teste em `apps/api/tests/integration/test_integracoes.py`.
- [X] T073 (SPA) Ligar a UI a `GET /api/integracoes`: aviso na Descobrir e no "Adicionar canal"
  quando o YouTube está `ausente`/`invalida`; botão "Sugerir textos" desabilitado com a explicação
  quando o Claude está `ausente` (os campos seguem editáveis); cota na tela Fontes. Arquivos:
  `apps/web/src/lib/integracoes.ts`, `Descobrir.tsx`, `CanalForm.tsx`, `CorteDetalhe.tsx`,
  `CanaisList.tsx`.
- [X] T074 Ampliar `apps/api/tests/unit/test_constitution_guards.py` (princípio I; as listas só
  crescem): corrigir a docstring ("O princípio II ganha teste próprio na spec 006", que absorveu a
  008); varredura de `src/` sem `/api/social`, `upload-post`, `open.tiktokapis.com`,
  `upload/youtube`, `graph.facebook.com` nem `videos.insert`; `canais.youtube.ALLOWED` só `GET` em
  `channels`, `playlistItems`, `videos`, `search`; `envios.openshorts.ALLOWED` sem `/api/social`,
  `/api/thumbnail/publish`, `/api/saasshorts/post`; por AST, `EstadoPostagem.postado` só é
  atribuído em `postagem/service.py` (`marcar_postado`); `PUBLISH_TERMS` e `SOCIAL_SDKS` iguais
  (SC-007).
- [X] T075 [P] Criar `apps/api/tests/integration/test_direito.py` (princípio II, R12): membro →
  403 ao mudar o direito, dono → 200 com versão (autor, antes e depois); `sem_acordo` ou avulso
  sem `confirmarAviso` → 409 `aviso_direito` e nada enviado; com a confirmação (dono **ou
  membro**) → 200, e a versão do envio tem `direito_no_envio`, fonte, autor e data; `proprio` sem
  aviso; o direito não altera a pontuação nem bloqueia o envio.
- [X] T076 [P] Criar `apps/api/tests/integration/test_historico_006.py` (princípio VII): cada rota
  humana de mutação da 006 (canal, padrões de corte, envio, corte, postagem) grava uma versão com
  autor e antes/depois; não existe rota DELETE; `revert` do canal, dos padrões e da postagem só
  pelo dono; mudanças do sistema (sync, progresso) não geram versão.
- [X] T077 ⚠️ **COMPARTILHADO (só acréscimo)** Em `docker-compose.e2e.yml`: serviço
  `openshorts-fake` (imagem `sociman-api-e2e`, que já tem ffmpeg, rodando
  `python /fake/server.py` com `./e2e/fakes:/fake:ro`), que atende a API do OpenShorts usada pelo
  cliente **e** `/youtube/v3/*` (o e2e nunca chama o Google); serviço `agendador` (mesma imagem,
  `sociman agendador`, mesmo `x-api-env`, HD tmpfs com o sentinela, intervalos curtos:
  `AGENDADOR_SYNC_S=2`, `AGENDADOR_OPENSHORTS_S=1`, `AGENDADOR_IMPORTACAO_S=1`,
  `AGENDADOR_LEMBRETES_S=2`); `api` e `agendador` com `OPENSHORTS_URL=http://openshorts-fake:8000`,
  `YOUTUBE_API_URL=http://openshorts-fake:8000/youtube/v3` e `YOUTUBE_API_KEY` fixa de teste que
  **não** casa com `AIza…`; sem `ANTHROPIC_API_KEY` (a sugestão é coberta pelo pytest). Conferir
  que `scripts/test-e2e.sh` sobe os serviços novos e os derruba com `down -v`.
- [X] T078 [P] Criar `e2e/fakes/server.py` (stdlib `http.server`, sem dependência nova): canal e
  vídeos de mentira (sem miniaturas externas: `thumbnails` ausentes, a API devolve `null`), job
  que passa por `queued → processing → completed` em poucos segundos, clipes MP4 sintéticos
  gerados com ffmpeg na subida, `/api/subtitle` e transcript.
- [X] T079 Criar `e2e/cortes-openshorts.spec.ts` (fluxos críticos, na stack isolada, usando
  `e2e/helpers.ts` sem tocar no dev): US1 cadastrar canal pelo fake, dono muda o direito, membro
  vê só leitura; US2 Descobrir mostra o motivo e seleciona 2 vídeos; US3 enviar com o aviso de
  `sem_acordo` (confirmado pelo **membro**), status até "Pronto" e notificação no sino; US4
  revisão: arquivar um clipe e aplicar a marca nos outros (worker real); US5 textos à mão,
  agendar para daqui a 1 min, "Hora de postar" no sino, "Marcar como postado", e nenhuma
  requisição sai para rede social.
- [X] T080 Rodar `npm run gen:contract` depois da última mudança de rota e conferir
  `npm run check:contract` (Trilha D; nunca editar `packages/contract` à mão).
- [X] T081 [P] Atualizar `docs/visao.md`: item 8 do backlog (`008-canais-fonte-e-videos`) passa a
  "absorvido pela spec `006-cortes-openshorts`", com as decisões principais (agendador, pontuação
  explicável, aviso de direito pela API, legenda do kit, uma postagem por conta, avisos só com o
  app aberto) e o status real da 006.
- [X] T082 [P] Atualizar `CLAUDE.md` com uma seção curta "Cortes com o OpenShorts (desde a spec
  006)": serviço `agendador` e trilhas; comandos `docker compose logs -f agendador` e
  `docker compose restart agendador`; `YOUTUBE_API_KEY`/`ANTHROPIC_API_KEY` só no `.env` da raiz
  (rotação: trocar e `docker compose up -d api agendador`); `OPENSHORTS_URL` e a regra do ufw;
  `auto_hook` sempre desligado; o `openshorts-fake` do e2e.
- [ ] T083 Verificação final (princípio VI): `npm run test:api`,
  `docker compose exec api uv run ruff check .`, `npm run check:web` (inclui `check:secrets` e
  `check:csp`, que não pode mudar) e `npm run test:e2e`; tudo verde antes de declarar pronto.
- [ ] T084 Roteiro do quickstart §0–§6 com o dono (manual, um passo por vez) e, se ele quiser,
  §7 com o OpenShorts real; anotar qualquer desvio em `plan.md`/`quickstart.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependência. T006 é passo do dono e só bloqueia o teste com o YouTube
  e o Claude reais.
- **Foundational (Phase 2)**: depende do Setup e da migration `0005_assets` da 007. **Bloqueia
  todas as histórias.**
- **US1 (Phase 3)** e **US3/US4 do lado da API**: começam logo depois da fundação (os testes da
  Trilha B inserem canais e vídeos direto pelo modelo).
- **US2**: a API da descoberta depende da US1 (canais); a seleção (T035, T039, T040) não depende.
- **US4**: depende da US3 (envio, cliente e fake do OpenShorts).
- **US5**: a API só depende da fundação (os testes inserem cortes `pronto`); a UI da seção
  Postagem depende da T060.
- **Polish**: T072 depende da T049; T074 depende de T025, T049 e T067; T077–T079 dependem de
  todas as histórias; T080 depois da última rota; T083 por último.

### Within Each User Story

- Fixtures e fakes antes dos testes que os usam (T020 → T022/T023; T046 → T047/T055; T061 →
  T062/T063).
- Modelos (fundação) → serviços → rotas → `gen:contract` → SPA.
- O stub de cada trilha do agendador só é substituído pela trilha dona dele.

### Parallel Opportunities

- Setup: T002, T003 e T005 em paralelo.
- Fundação: T008–T012 em paralelo; T016 e T018 em paralelo.
- Depois do checkpoint: as trilhas A, B e C trabalham ao mesmo tempo, e a D segue cada
  checkpoint de API.
- Testes marcados [P] de uma história em paralelo (`npm run test:api` pode rodar em paralelo;
  `docker compose exec api uv run pytest` **não**).

---

## Trilhas para agentes paralelos

Quatro agentes, mais a Trilha 0 (um deles, ou o líder) para Setup e fundação. Cada trilha é dona
dos seus arquivos; um arquivo de outra trilha só muda por pedido ao dono dele.

| Trilha | Tarefas | Arquivos de que é dona |
|---|---|---|
| **0: Setup, fundação e fechamento** (um agente, antes e depois das outras) | T001–T019; no fim, T081–T084 (docs, verificação final e quickstart com o dono) | `pyproject.toml`, `uv.lock`, `config.py`, `.env.example`, `docker-compose.yml`, `default.conf.template`, a migration `0006`, todos os `models.py` novos, `cortes/models.py`, `migrations/env.py`, `main.py`, `cli.py`, `agendador.py`, `notificacoes/*`, `integracoes.py` (esqueleto), `tests/fakes/__init__.py`, `tests/integration/conftest.py`, `docs/visao.md`, `CLAUDE.md` |
| **A: canais e YouTube** | T020–T029, T032–T034, T036–T038 | `canais/{resolve,youtube,sync,score,service_canais,service_videos,schemas,router}.py`, `imaging.py` (só acréscimo), `tests/fixtures/youtube/`, `tests/fakes/youtube_fake.py`, testes `test_resolve`, `test_youtube_client`, `test_imaging_remote`, `test_canais`, `test_sync`, `test_score`, `test_descoberta` |
| **B: envios, OpenShorts, agendador e importação** | T035, T039, T040, T043–T051, T055–T058 | `envios/*` (menos `models.py`), `cortes/{schemas,service,router}.py`, `tests/fakes/openshorts_fake.py`, testes `test_selecao`, `test_padroes_corte`, `test_enviar`, `test_openshorts_client`, `test_agendador_openshorts`, `test_importacao`, `test_cortes_revisao` |
| **C: textos, postagens, lembretes e transversais** | T061–T068, T072, T074–T078 | `postagem/*` (menos `models.py`), `integracoes.py` (rota), `tests/fixtures/anthropic/`, `tests/fakes/anthropic_fake.py`, testes `test_textos`, `test_sugestoes`, `test_postagens`, `test_lembretes`, `test_integracoes`, `test_constitution_guards`, `test_direito`, `test_historico_006`, `docker-compose.e2e.yml` (só acréscimo), `e2e/fakes/` |
| **D: SPA, contrato e e2e** | T030, T031, T041, T042, T052–T054, T059, T060, T069–T071, T073, T079, T080 | `apps/web/**` (inclui `App.tsx`, `nav.ts`, `Topbar.tsx` e `PerfilDetalhe.tsx`, estes só acréscimo), `packages/contract/**` (gerado), `e2e/cortes-openshorts.spec.ts` |

Regras de convivência:
- **Contrato:** só a Trilha D roda `npm run gen:contract`, a cada checkpoint de API (US1, US2,
  US3, US4, US5, Polish). As trilhas A, B e C não fazem commit de `packages/contract`.
- **Testes em paralelo:** cada trilha roda só os seus arquivos com
  `npm run test:api -- tests/<caminho>` (stack efêmera, paralelo seguro). O e2e (`npm run
  test:e2e`) roda um de cada vez, e só a Trilha D o dispara.
- **Sem colisão com o `agendador.py`:** as trilhas preenchem `canais/sync.py` (A),
  `envios/acompanhamento.py` e `envios/importacao.py` (B) e `postagem/lembretes.py` (C), que a
  T017 criou como stubs.
- **`cortes/service.py`:** é da Trilha B (T039 generaliza o upload, T057 amplia). A 004 tem
  testes nesse arquivo: `test_cortes.py`, `test_worker.py` e `test_queue.py` precisam continuar
  verdes.
- **Pontos de sincronização:** fim da fundação (todos); T049 pronta (C precisa para T072); T057
  pronta (D precisa para T060/T070); todas as histórias (C faz T077/T078, depois D faz T079).
- **Com a 007:** nos arquivos ⚠️ COMPARTILHADOS, só acrescentar blocos e linhas; quem fizer merge
  por último resolve. `docker compose restart edge` depois de mudar o template.

---

## Implementation Strategy

### MVP (P1)
1. Setup + fundação (Trilha 0).
2. US1 → US2 → US3 → US4 (trilhas A, B e D em paralelo onde der).
3. **Parar e validar** com o dono (quickstart §1–§5): o fluxo canal → corte com a marca funciona
   sem a US5.

### Incremento
4. US5 (Trilha C, que pode começar junto com as P1, porque a API não depende delas).
5. Polish: guardas, e2e, contrato, docs e verificação final.

---

## Notes

- Nenhuma rota DELETE; nenhum caminho nem `operationId` com `publish`, `share`, `post-to`,
  `upload-to`, `tiktok`, `youtube` ou `instagram`.
- As chaves nunca são impressas (nem em log, erro, teste ou commit).
- Commit só quando o dono pedir, em pt-BR no imperativo.
