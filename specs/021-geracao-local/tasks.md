---

description: "Tarefas da feature 021-geracao-local"
---

# Tasks: Geração local com candidatos (021-geracao-local)

**Input:** `specs/021-geracao-local/`, com:
- a spec, com as Clarifications de 2026-10-06 e 2026-10-07;
- o plan, com as decisões D1–D3 do dono;
- a research R1–R16;
- o data-model;
- os contratos `contracts/http-api.md`, `comfyui.md`, `shop-tts.md` (dependência externa) e `dockerctl.md`;
- o quickstart.

**Pré-requisitos:**
- a 007 (assets), a 008 (registro de chamadas), a 006 (envios) e a 004 (worker e HD) estáveis e verdes;
- a emenda **4.3.0** da constitution, aplicada na T001.

A 021 mexe em `storage.py`, `midia.py`, `router_midia.py`, `ia/models.py`, `integracoes.py`, `agendador.py`,
`cli.py`, `docker-compose.yml`, `docker-compose.e2e.yml`, `docker/nginx/default.conf.template` e
`scripts/data-setup.sh`. Nenhum outro agente pode estar editando esses arquivos ao mesmo tempo.

**Decisões do dono:**
- **2026-10-06 (spec):**
  - Q1 (FR-030) = A: o piloto de ponta a ponta é o `cenario.cena`;
  - Q2 (FR-031) = A: o `produto.recorte` vai direto para o alvo;
  - a emenda 4.2.0 → 4.3.0 é aprovada;
  - com a 025 (2026-10-07): o par `image_par_id` no `avatar.rostos_34`; o passo `voz.teste` com o estado
    `entregue`; e, no aplicador, o gancho `ao_mudar_estado` e o campo `extras`.
- **2026-10-07 (plan):**
  - **D1 = A:** o container `dockerctl` mínimo, o único com o socket do Docker;
  - **D2 = A:** a rede Docker externa `gpu-local`;
  - **D3:** o shop-tts muda para o contrato `v2` **antes da 025**, feito pelo dono ou noutra sessão, no
    `../comfyui-docker`.

**Nomes canônicos:**
- **API:** pacote `sociman_api/geracao/`, com `models`, `passos`, `aplicadores`, `seeds`, `erros`, `fila`,
  `gpu`, `memoria`, `comfyui`, `shoptts`, `motor_claude`, `gerador`, `audios`, `uso`, `limpeza`,
  `service`, `schemas`, `router`, `router_audios` e `workflows/`.
- **Rotas e `operationId`:** os de `contracts/http-api.md` (`geracoes_*`, `audios_*`).
- **Tabelas e colunas:**
  - `geracoes`, `geracao_candidatos` (com `image_par_id`) e `audios`;
  - `ia_chamadas.geracao_id`;
  - enums `geracao_alvo`, `geracao_motor` e `geracao_status` (com `entregue`).
- **Migration:** **`0020_geracao_local`** (`down_revision = "0019_aprendizado_fonte_temas"`; provisória,
  conferida na T001).
- **Autores automáticos:** `Actor(kind="system:gerador")` (estado de job) e `system:agendador` (limpeza).
- **Serviços:** `gerador` (`sociman gerador`) e `dockerctl` (`docker/dockerctl/`).
- **Redes:** `gpu-local` (externa) e `dockerctl` (`internal`).
- **Trilha:** `geracao_limpeza` (`AGENDADOR_GERACAO_LIMPEZA_S`, padrão 3600).
- **Bucket:** `sociman-audios` (`S3_AUDIOS_BUCKET`). **MidiaKind:** `audio`.
- **Evento:** `eliminacao_candidatos`. **Delete:** `storage.apagar_por_excecao(key, *, bucket, excecao)`.
- **SPA:** `components/geracao/*`, `lib/geracoes.ts` e a seção "Gerar cena" em
  `pages/assets/AssetDetalhe.tsx`.
- **Testes:**
  - fakes `tests/fakes/comfyui_fake.py`, `shoptts_fake.py` e `dockerctl_fake.py`;
  - `e2e/fakes/server.py` (`/comfyui`, `/shop-tts`, `/dockerctl`, `/geracao-e2e`);
  - `e2e/geracao.spec.ts`.

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec -T api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/geracao.spec.ts]`.

Nada chama serviço real: nem o ComfyUI, nem o shop-tts, nem o Docker, nem o Claude.

**Arquivos compartilhados, SÓ ACRÉSCIMO:**
- `main.py`, `agendador.py`, `config.py`, `cli.py` e `integracoes.py`;
- `mcp/mapa.py`;
- `tests/unit/test_constitution_guards.py`;
- `e2e/fakes/server.py` e `e2e/helpers.ts`;
- `CLAUDE.md` e `docs/visao.md`.

`packages/contract/**` é gerado.

**Dependências externas (NÃO executar neste repo; o dono aplica):**
- **X1 (D2):** `docker network create gpu-local`. No `../comfyui-docker/docker-compose.yml`, `comfyui` e
  `tts` entram na `gpu-local` (`contracts/comfyui.md`). Precisa estar pronta antes do quickstart §2.
- **X2 (D3):** o contrato `v2` do shop-tts (`contracts/shop-tts.md`), mais o `DELETE /v2/voices/{nome}` da
  025 (`specs/025-cadastro-padronizado/contracts/shop-tts-025.md`), em `../comfyui-docker/tts_service/`.
  Precisa estar pronto **antes da 025**; não bloqueia a 021.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US6 da spec

---

## Phase 1: Setup

- [X] T001 **Gate:**
  - **aplicar a emenda 4.2.0 → 4.3.0** com o `/speckit-constitution`, com o texto aprovado pelo dono. No
    fim do princípio VII de `.specify/memory/constitution.md`, acrescentar:
    > **Exceções de eliminação (4.3.0):** dois casos podem apagar dados de fato, sempre registrados como
    > evento (quem, quando, contagem e motivo) e nunca disparados por IA, agente ou MCP: (1) candidatos de
    > geração não escolhidos, 90 dias depois da geração (o escolhido nunca); (2) revogação de
    > consentimento de pessoa real (LGPD), só pelo dono: os arquivos e os textos que descrevem a pessoa
    > (inclusive em versões antigas do histórico) são apagados; o registro de que houve consentimento e
    > revogação fica, sem a mídia nem a descrição. Fora desses dois casos, continua valendo: nada é
    > apagado de fato.

    Versão **4.3.0** (MINOR: exceção nova e nomeada), `Last Amended: 2026-10-07`, com o Sync Impact Report.
    Conferir que o `CLAUDE.md` não contradiz a emenda;
  - `ls apps/api/migrations/versions/` mostra **`0019_aprendizado_fonte_temas`** como a última e nenhum
    `0020_*`. Se a 024 já ocupou o número, renomeie para o próximo livre **em todos os documentos da 021**
    e avise o líder;
  - `docker compose exec api uv run alembic heads` mostra só a última;
  - os testes da 007, da 008 e da 004 estão verdes:
    `npm run test:api -- tests/ -k "asset or ia_ or corte" -q`;
  - `git status` só tem o esperado;
  - `.specify/feature.json` aponta para a 021 (o líder cuida).
- [X] T002 [P] `config.py` (acréscimo):
  - `comfyui_url` (padrão `http://comfyui:8188`) e `shop_tts_url` (`http://shop-tts:8200`);
  - `dockerctl_url` (`http://dockerctl:8080`) e `dockerctl_token` (padrão vazio);
  - `s3_audios_bucket` (`sociman-audios`);
  - `geracao_vram_min_gb_comfyui = 12`, `geracao_vram_min_gb_tts = 6` e `geracao_comfyui_teto_s = 1200`;
  - `agendador_geracao_limpeza_s = 3600`.

  Nenhum segredo com valor padrão. O `.env.example`, se existir, ganha as chaves vazias.
- [X] T003 [P] `scripts/data-setup.sh` (acréscimo):
  - `check` mostra o bucket `sociman-audios`, a rede `gpu-local` e o `DOCKER_GID` (gid do grupo `docker`);
  - `init` cria a rede `gpu-local` se faltar (`docker network create gpu-local`) e o bucket.

  Nada é apagado.

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** banco, modelos, registro de passos, delete restrito, guardas e fakes.

- [X] T004 Migration `apps/api/migrations/versions/0020_geracao_local.py`, conforme o data-model:
  - os 3 enums e as tabelas `audios`, `geracoes` e `geracao_candidatos` (com `image_par_id`);
  - a FK `fk_geracoes_escolhido` adicionada depois (`use_alter`);
  - os CHECKs (`ck_geracoes_passo` com os 15 passos, `_escolhido`, `_erro`, `_final`, `_entregue`,
    `_progress`, `_n`, `ck_candidatos_par`, `ck_candidatos_midia`);
  - o trigger `geracao_candidatos_midia` (por passo);
  - os índices, inclusive o **`uq_geracoes_gpu_rodando`**;
  - `ia_chamadas.geracao_id` com índice;
  - o downgrade recusa se houver linha em `geracoes` ou em `audios`.
- [X] T005 [P] `tests/integration/test_migration_0020.py`:
  - sobe sobre a 0019 com `ia_chamadas` existentes, que ficam com `geracao_id` NULL;
  - cada CHECK e o trigger recusam com `INSERT` direto: par fora do `rostos_34`, mídia num passo de texto,
    `entregue` fora do `voz.teste`;
  - dois `rodando` de GPU → violação do índice único;
  - down vazio e up; down com dados → recusa.
- [X] T006 `geracao/models.py`:
  - `Geracao` (`version`, `AuditMixin`, `__versioned_fields__ = (status, escolhido_id, error_code,
    error_message)`, `__immutable_fields__ = (alvo_tipo, alvo_id, passo, motor)`);
  - `GeracaoCandidato` e `Audio`;
  - os enums `GeracaoAlvo`, `GeracaoMotor` e `GeracaoStatus` (`FINAIS = {escolhido, descartada,
    cancelada, entregue}`).

  Em `ia/models.py` (acréscimo): `geracao_id`. Registrar no metadata e no `env.py`, se necessário.
- [X] T007 [P] `geracao/passos.py` (R15): o registro `Passo(id, motor, alvo_tipo, resultado, n_padrao,
  n_max, sem_escolha, aplica_alvo, bloco, image_kind)` dos 15 passos, mais os sufixos `REALISMO` e
  `MANTER` (R6) e a sobrescrita do registro **só em teste**. Em `tests/unit/test_geracao_passos.py`:
  - a lista bate com o `ck_geracoes_passo` (lê a migration);
  - `sem_escolha` só em `produto.ficha`, `avatar.identidade`, `produto.recorte` e `voz.teste`;
  - `aplica_alvo = False` só em `voz.teste`;
  - `n_padrao` 2, `rosto_origem` 4, voz ≤ 3, `voz.teste` 1.
- [X] T008 [P] `geracao/seeds.py` (R7) e `geracao/erros.py` (R8: códigos, `MENSAGENS` em pt-BR, espera
  crescente de 30 s a 15 min e 6 tentativas). Em `tests/unit/test_geracao_seeds.py` e `test_geracao_erros.py`:
  - "Gerar outras" nunca repete uma seed;
  - a GPU ocupada não conta tentativa;
  - na 7ª tentativa de `sem_memoria` ou `servico_fora`, a geração vai para `falhou`;
  - nenhuma mensagem vaza texto do serviço.
- [X] T009 [P] `storage.py` (acréscimo, R11 e R12):
  - `Bucket` ganha `"audios"`, e o `ensure_buckets` o cria;
  - **`apagar_por_excecao(key, *, bucket, excecao: Literal["candidatos_90d", "lgpd_revogacao"])`**, o
    único delete do módulo, com a docstring da emenda 4.3.0. A docstring do módulo passa a citar as 2
    exceções.
- [X] T010 [P] `tests/unit/test_constitution_guards.py` (acréscimo):
  - `geracao/` não importa `publicacao`, `mcp` nem hosts de rede social;
  - sem "tiktok" nem "youtube" em `geracoes_*` e `audios_*`;
  - **delete restrito:** por AST, só `geracao/limpeza.py` (e, na 025, o módulo da revogação LGPD,
    listado aqui quando existir) chamam `apagar_por_excecao`; nenhum módulo de `mcp/` nem de `ia/` o
    alcança; nenhuma rota HTTP o chama;
  - **nunca auto:** o `gerador` só chama `Aplicador.aplicar` para passos com `sem_escolha = True`;
  - os clientes `comfyui`, `shoptts` e `memoria` têm `ALLOWED` fechado;
  - o `docker.sock` não aparece em nenhum serviço do `docker-compose.yml` além do `dockerctl`.
- [X] T011 [P] `geracao/workflows/` (R6): copiar de `../comfyui-docker/workflows/api/` os pares `cena`
  (`V3 - Imagem FLUX schnell (txt2img)`), `keyframe`, `retrato` (`V3 - Retrato Juggernaut XL (txt2img)`)
  e `cutout`, com `MANIFEST.json` (origem e sha256). Em `tests/unit/test_workflows_manifest.py`: os
  hashes batem, e cada `params.json` tem os nós que o `api.json` declara.
- [X] T012 [P] `tests/fakes/comfyui_fake.py` (R13): `/system_stats` com VRAM programável, `/upload/image`,
  `/prompt` (confere os nós preenchidos), `/history` (N voltas "rodando"), `/view` (PNG sintético com a
  seed), `/free`, `/interrupt` e `/queue`. Falhas: fora do ar, `OutOfMemoryError` e saída vazia. Registra
  `.requests`.
- [X] T013 [P] `tests/fakes/shoptts_fake.py`: exatamente o contrato `v2` (`contracts/shop-tts.md`),
  inclusive `GET /v2/lotes/...` (WAV sintético), `DELETE`, `/unload`, `/health` e 503 programável.
- [X] T014 [P] `tests/fakes/dockerctl_fake.py`: o limite atual. Falhas: "não volta para 12 GB", "fora do
  ar", "não coube" e token errado → 401.
- [X] T015 `geracao/schemas.py` (camelCase): `GeracaoIn` (com `texto` e `extras` ≤ 2 KB), `Geracao`,
  `GeracaoResumo`, `Candidato` (com `imagemPar` e `testeAudio`), `Audio`, `Link` e os corpos de ação com
  `version`, conforme `contracts/http-api.md`.
- [X] T016 `geracao/aplicadores.py` (R15): o protocolo `Aplicador` (`validar_alvo`, `montar_params`,
  `aplicar` e `ao_mudar_estado`, que por padrão não faz nada) e o registro `APLICADORES` por passo. Em
  `geracao/fila.py`, o helper `abertas_do_alvo(db, alvo_tipo, alvo_id, exceto=None)`.

**Checkpoint:** migração verde, passos e erros testados, guardas verdes e fakes prontos.

---

## Phase 3: User Story 1 - Pedir uma geração e escolher uma opção (Priority: P1) 🎯 MVP

**Objetivo:** pedir a cena de um cenário, ver o andamento, escolher a opção e ela virar arquivo do
cenário, com histórico.

**Independent Test:** spec US1 (ComfyUI falso, 2 opções, escolher a 2).

- [X] T017 [US1] `geracao/fila.py` (R2): `claim(motor_grupo)` com `SKIP LOCKED` e a espera
  (`next_attempt_at`), `heartbeat`, `requeue_stale` (120 s; 3ª vez → `falhou`), e os fins "é meu"
  (`para_revisao`, `para_falhou`, `para_espera`, `para_escolhido_auto` e `para_entregue`).
  **Toda transição chama `Aplicador.ao_mudar_estado` na mesma transação.** Cada candidato é gravado
  quando a opção dele fica pronta.
- [X] T018 [P] [US1] `tests/integration/test_geracao_fila.py`:
  - a ordem de pedido;
  - dois claims de GPU ao mesmo tempo → um só (índice);
  - `requeue_stale` (devolve e, na 3ª vez, falha);
  - um fim "é meu" não sobrescreve uma geração cancelada;
  - o gancho é chamado em cada transição, e uma exceção no gancho desfaz a transição.
- [X] T019 [US1] `geracao/comfyui.py` (R6): o cliente com `ALLOWED` e o `run_bloco(bloco, params,
  heartbeat)` (porte do `run_block`: `upload`, `drop`, `consumers`, `rewire`, `prompt`, `history`,
  `view` e `free(unload_models=False)`), mais `normalizar_9x16` (Pillow, 768×1344) e `validate_image`.
  Em `tests/unit/test_geracao_comfyui.py` (com o fake): o preenchimento do contrato, a referência
  opcional ausente, o erro de execução → `sem_memoria`/`internal` e o 768×1344.
- [X] T020 [US1] Aplicador do **`cenario.cena`** em `geracao/aplicadores.py`:
  - `validar_alvo`: asset `cenario` do perfil, ativo;
  - `montar_params`: prompt + `REALISMO` (bloco `cena`) ou foto + `MANTER` (bloco `keyframe`), e as seeds;
  - `aplicar`: `assets.service._attach` `referencia` (`notes = "Gerado (opção N)"`) e
    `history.record(asset, "updated", details={geracao_id, candidato})`.

  Os outros 14 passos ficam sem aplicador → 409 `passo_indisponivel`.
- [X] T021 [US1] `geracao/service.py`:
  - `pedir`: valida o passo, o alvo, `nOpcoes`, `rotulo`, `texto` e `extras` pelo aplicador. As
    `referencias` também são validadas pelo `Aplicador.montar_params`: o service só confere que são imagens
    do mesmo perfil, e o padrão "arquivo ativo de asset ativo" é o helper `aplicadores.referencia_de_asset_ativo`
    dos passos de asset. `alvoTipo = produto` → 409 `alvo_incompativel` (a 012 tem rotas próprias); `history.record(geracao, "created")`; chama o gancho com `de = None`);
  - `escolher` (`FOR UPDATE`, `revisao`, `version` e `alvoVersion`; o aplicador; `history.record`;
    gancho);
  - `listar` e `detalhe` (com os links: `imagem` com validade).
- [X] T022 [US1] `geracao/router.py`: `geracoes_criar` e `geracoes_escolher` (**`RequireHuman`**);
  `geracoes_listar`, `geracoes_detalhe` e `geracoes_versoes` (`RequireUser`). `include_router` no
  `main.py`.
- [X] T023 [US1] `mcp/mapa.py` (acréscimo): `geracoes_criar` e `geracoes_escolher` em `PROIBIDAS`;
  `geracoes_listar`, `geracoes_detalhe` e `geracoes_versoes` em `FORA` ("geração local só pela interface
  no primeiro corte"). O `test_mcp_mapa` continua verde. Depois, `npm run gen:contract`.
- [X] T024 [US1] `geracao/gerador.py` + `cli.py` (`sociman gerador`):
  - advisory lock;
  - a linha GPU, ainda **sem** as conferências de GPU e de RAM (que entram na US2), com o heartbeat de 5 s;
  - SIGTERM devolve a geração à fila sem contar tentativa;
  - os clientes por parâmetro (padrão das fábricas).
- [X] T025 [P] [US1] `tests/integration/test_geracao_escolher.py` (SC-005):
  - o ciclo completo com o fake (pedir → rodar → revisão → escolher a 2): o arquivo no cenário, a versão
    do cenário com `geracao_id` e a geração `escolhido`;
  - a opção 1 continua visível;
  - escolher de novo → 409 `geracao_decidida`;
  - duas escolhas simultâneas → uma só;
  - o alvo mudou → 409 `version_conflict`;
  - o alvo arquivado → 409 `alvo_arquivado`;
  - referência de outro perfil → 400;
  - `alvoTipo = produto` no POST genérico → 409 `alvo_incompativel`.
- [X] T026 [P] [US1] `tests/integration/test_geracao_permissoes.py` (SC-004):
  - pedir e escolher com membro humano → ok;
  - com token MCP ou `system:*` → 403 `somente_humano` mais o evento `publicacao_recusada`;
  - as leituras aceitam membro;
  - nenhum caminho escolhe sem humano (passo com escolha nunca vai a `escolhido` pelo gerador).
- [X] T027 [P] [US1] SPA:
  - `lib/geracoes.ts` (hooks com o cliente gerado, `refetchInterval` de 2 s enquanto não for final);
  - `components/geracao/PedirGeracao.tsx` (instrução, foto de referência opcional pela biblioteca,
    número de opções);
  - `AndamentoGeracao.tsx` (porcentagem + mensagem);
  - `OpcoesGeracao.tsx` (grade numerada, comparação lado a lado, "Usar opção N" com AlertDialog; mostra o
    par quando houver `imagemPar`).
- [X] T028 [US1] `pages/assets/AssetDetalhe.tsx` (acréscimo): no **cenário**, a seção "Gerar cena" e as
  gerações abertas e recentes. Escolher atualiza o detalhe do asset.
- [X] T029 [P] [US1] `e2e/fakes/server.py` (acréscimo): `/comfyui/*` com o comportamento do fake do pytest
  (PNG sintético com `zlib`/`struct`) e `GET /geracao-e2e/pedidos`. Em `docker-compose.e2e.yml`, o serviço
  `gerador` com `COMFYUI_URL=http://openshorts-fake:8000/comfyui`,
  `SHOP_TTS_URL=http://openshorts-fake:8000/shop-tts` e `DOCKERCTL_URL=http://openshorts-fake:8000/dockerctl`
  (com um token de teste fixo, liberado por valor no `check:secrets`).
- [X] T030 [US1] `e2e/geracao.spec.ts`, cenário US1: no cenário de teste, pedir uma cena, ver o andamento,
  ver as 2 opções e usar a 2. O arquivo aparece no cenário, e o histórico mostra a geração.

**Checkpoint:** o ciclo do piloto funciona de ponta a ponta com fakes.

---

## Phase 4: User Story 2 - A fila respeita a GPU e a memória (Priority: P1)

**Objetivo:** um job de GPU por vez, só com a GPU livre, e RAM de 28 GB só durante o job `comfyui`.

**Independent Test:** spec US2.

- [X] T031 [P] [US2] `geracao/gpu.py` (R3): `gpu_livre(db, motor, comfy)` (envios da 006 em
  `processando`; `vram_free + torch_vram_total` contra o piso) → `livre | openshorts | pouca_vram | fora`.
- [X] T032 [P] [US2] `geracao/memoria.py` (R4): o cliente do `dockerctl` (`ALLOWED`, Bearer), com
  `ler`, `subir` e `devolver`, que conferem o valor lido depois.
- [X] T033 [US2] `geracao/gerador.py` (acréscimo):
  - **ao subir:** conferir 12 GB (senão, logar, devolver e só liberar a linha GPU depois de ler 12 GB);
  - **antes do claim de GPU:** soltar o outro motor (`/unload` ou `/free(unload_models=True)`, FR-022) e
    `gpu_livre`. Se a GPU não estiver livre, "Aguardando a GPU ficar livre" com +30 s, sem tentativa
    (FR-020);
  - **job `comfyui`:** `subir` → bloco → `finally: devolver` + conferir. Se não voltar, a linha fica
    "travada" e tenta de novo a cada 30 s, sem pegar outro job de GPU (FR-021);
  - **sem `DOCKERCTL_TOKEN`:** não pega job `comfyui` (fica na fila com "Ajuste de memória do ComfyUI não
    configurado").
- [X] T034 [P] [US2] `tests/integration/test_geracao_gpu.py` (SC-002):
  - o cenário do Independent Test (3 `comfyui`, 1 `tts`, 1 `claude`; a GPU ocupada pelo OpenShorts e
    depois livre; um por vez, em ordem);
  - a `claude` roda com a GPU ocupada;
  - pouca VRAM → espera sem contar tentativa;
  - a ordem `/unload` → `comfyui` e `/free` → `tts`.
- [X] T035 [P] [US2] `tests/integration/test_geracao_memoria.py` (SC-003): 28 → 12 em sucesso, falha,
  cancelamento e SIGTERM; o worker reiniciado com 28 GB devolve antes do próximo job; "não volta" trava a
  linha; "não coube" chama `/free` e tenta de novo.
- [X] T036 [P] [US2] `docker/dockerctl/server.py` + `Dockerfile` (`python:3.12-alpine`, só a stdlib;
  `contracts/dockerctl.md`):
  - as 3 rotas;
  - o token com `hmac.compare_digest`;
  - o corpo do pedido ignorado;
  - o container, a API e os valores vêm do ambiente;
  - 404 com log para o resto;
  - sem token, não sobe.

  Em `apps/api/tests/unit/test_dockerctl_server.py` (importa o arquivo por caminho, com um socket Unix
  falso): a allowlist, o token, o corpo fixo de `update` e o 404.
- [X] T037 [US2] `docker-compose.yml` (acréscimo):
  - o serviço **`gerador`**: a mesma imagem, `sociman gerador`, as envs do HD, `ANTHROPIC_API_KEY`, as
    URLs e o token; as redes `default`, `gpu-local` e `dockerctl`; os binds do HD; `stop_grace_period`;
  - o serviço **`dockerctl`**: `read_only`, `cap_drop: [ALL]`, `no-new-privileges`,
    `user: "1000:${DOCKER_GID}"`, o socket do Docker **só aqui**, a rede `dockerctl` e nenhuma porta;
  - as redes `gpu-local: external: true` e `dockerctl: internal: true`.

  O `check:secrets` cobre o `DOCKERCTL_TOKEN`.
- [X] T038 [P] [US2] `integracoes.py` (acréscimo): o bloco `geracao` (`comfyui`, `shopTts`,
  `memoriaComfyui`, `gpu`, `gerador`; sem valores) e o teste. Depois, `npm run gen:contract`.
- [X] T039 [US2] e2e: `/dockerctl/*` e `POST /geracao-e2e/gpu` no fake; em `e2e/geracao.spec.ts`, com a
  GPU ocupada, a tela mostra "Aguardando a GPU ficar livre". Ao liberar, a geração roda, e
  `GET /geracao-e2e/memoria` mostra 28 → 12.

---

## Phase 5: User Story 3 - Acompanhar, cancelar, tentar de novo e gerar outras (Priority: P2)

**Independent Test:** spec US3.

- [X] T040 [US3] `geracao/service.py` (acréscimo): `cancelar`, `tentar_de_novo` e `gerar_outras` (a nova é
  criada, com o gancho chamado, **antes** de a antiga virar `descartada`; seeds novas), cada um com
  `version`, `history.record` (os `details` do R10) e o gancho.
- [X] T041 [US3] `geracao/gerador.py` (acréscimo, R9): o heartbeat lê o status. Se estiver `cancelada`:
  `/interrupt` (se for o prompt em execução) e `/queue delete`, e o resultado que chegar é descartado. O
  `finally` devolve a RAM.
- [X] T042 [US3] Rotas `geracoes_cancelar`, `geracoes_tentar_de_novo` e `geracoes_gerar_outras`
  (`RequireHuman`). No `mcp/mapa.py`, em `PROIBIDAS`. Depois, `npm run gen:contract`.
- [X] T043 [P] [US3] `tests/integration/test_geracao_estados.py`:
  - cancelar em cada estado não final (na rodando, o fake recebe `/interrupt`);
  - recusas nos finais;
  - "tentar de novo" só em `falhou` (zera a espera; o erro anterior fica no histórico);
  - "gerar outras" só em `revisao` (antiga `descartada`, seeds diferentes, o gancho vê a nova aberta);
  - as mensagens por código;
  - menos opções que o pedido ("veio 1 de 2") e nenhuma (→ `internal`);
  - referência arquivada ou sumida antes do job → `falhou` com `entrada_invalida`, dizendo qual;
  - o HD sem sentinela no meio do job → `falhou`, sem gravar fora do HD;
  - o alvo arquivado com geração aberta: cancelar é aceito.
- [X] T044 [P] [US3] SPA: em `OpcoesGeracao.tsx`, os botões "Gerar outras", "Cancelar" e "Tentar de
  novo" (com AlertDialog); `ListaGeracoes.tsx` (estado, erro em pt-BR, "veio 1 de 2"); e o acesso ao
  histórico da geração.
- [X] T045 [US3] `e2e/geracao.spec.ts`, cenários US3: cancelar na fila, e "gerar outras", com a antiga
  descartada e a nova em revisão.

---

## Phase 6: User Story 4 - Passos só de texto vão direto para o alvo (Priority: P2)

**Independent Test:** spec US4, com o Claude falso e um tipo e um aplicador **injetados no teste** (os
tipos reais `produto.ficha` e `avatar.identidade` chegam com a 012 e a 025, R14).

- [X] T046 [US4] `geracao/motor_claude.py` (R14): usa `ia/cliente.py` e `ia/custo.py`; grava
  `ia_chamadas` com `tipo_campo = passo`, `entity_type = alvo_tipo`, `entity_id` e `geracao_id`. No
  sucesso, `desfecho = aplicada` (`desfecho_por = created_by`); no erro, `erro`. Sem chave → `falhou` com
  `servico_fora` e a mensagem "O Claude não está configurado" (sem ficar presa na fila).
- [X] T047 [US4] `geracao/gerador.py` (acréscimo): a **linha Claude** (thread própria, uma de cada vez,
  sem conferir GPU). O caminho `sem_escolha`: `rodando → escolhido` com `aplicar` e uma versão do alvo
  com autor = quem pediu e `details.automatico = true`. O caminho do `produto.recorte` (FR-031), na linha
  GPU, segue a mesma regra.
- [X] T048 [P] [US4] `tests/integration/test_geracao_claude.py` (SC-007):
  - passo de texto injetado → `escolhido` sem `revisao`, o alvo com o resultado e a versão com
    `geracao_id`;
  - a chamada em `ia_chamadas` com custo e `geracao_id`, inclusive no erro;
  - não espera a GPU;
  - a edição manual depois salva como mudança humana;
  - resposta fora do formato → `falhou`, nada no alvo;
  - `produto.recorte` injetado vai direto, e nenhum outro passo de imagem vai.

---

## Phase 7: User Story 5 - Áudios guardados e ouvidos (Priority: P2)

**Independent Test:** spec US5.

- [X] T049 [US5] `geracao/audios.py` (R11):
  - o upload com teto de 25 MB, em `work/tmp` no HD;
  - o `ffprobe` (formatos, 1 fluxo de áudio, sem vídeo, ≤ 10 min) e o `sha256`;
  - `storage.put_file(bucket="audios")` com `perfis/{id}/audios/{uuid}.{ext}`;
  - `datadir.ensure_writable`.
- [X] T050 [US5] `geracao/router_audios.py`: `audios_enviar` (`RequireHuman`, multipart) e
  `audios_detalhe` (`RequireUser`). `midia.py` + `router_midia.py`: `MidiaKind "audio"` (sempre com
  `exp`, `Range`, `Content-Type` por formato, bucket `audios`). No `mcp/mapa.py`, `audios_enviar` em
  `PROIBIDAS` e `audios_detalhe` em `FORA`. Depois, `npm run gen:contract`.
- [X] T051 [P] [US5] `docker/nginx/default.conf.template`: `location ~ ^/api/perfis/[^/]+/audios$`
  (`client_max_body_size 26m`, `proxy_request_buffering off`), no padrão das outras rotas de upload
  grande. Depois, `docker compose restart edge` (armadilha 13).
- [X] T052 [US5] `geracao/shoptts.py` (contrato `v2`; o `ALLOWED` inclui o `DELETE /v2/voices/{nome}` da 025) e o motor `tts` no gerador:
  - `register`/`design`/`tts`/`voz.teste`;
  - baixar o lote, validar, gravar `audios` e os candidatos (`metricas`, `teste_audio_id`);
  - `DELETE` do lote;
  - `voz.teste` → `entregue`.

  Uso real só depois da X2 (antes da 025).
- [X] T053 [P] [US5] `tests/integration/test_audios.py`:
  - wav e m4a válidos (duração, formato, taxa, `sha256`);
  - > 25 MB → 413;
  - um vídeo ou um texto renomeado → 400;
  - o HD sem sentinela → 503;
  - o link com `Range` → 206;
  - sem rota de alteração.

  E `tests/integration/test_geracao_tts.py` (com o fake e um aplicador injetado de `voz.design` e
  `voz.teste`): os candidatos com áudio e teste, `entregue` e o `DELETE` do lote.
- [X] T054 [P] [US5] SPA: `components/geracao/PlayerAudio.tsx` (`<audio controls>` nativo, link com
  validade renovado ao vencer). Em `OpcoesGeracao.tsx`, o candidato de áudio com o teste e as métricas.

---

## Phase 8: User Story 6 - Limpeza das opções não escolhidas (Priority: P3)

**Independent Test:** spec US6.

- [X] T055 [US6] `geracao/uso.py` (R12): `midia_em_uso(db, image_id | audio_id)`, com os provedores
  `asset_files`, escolhido de outra geração, `params` vivo, tokens de kit e ingredientes de cena (010).
  O registro fica aberto para a 025 e a 012.
- [X] T056 [US6] `geracao/limpeza.py` (R12):
  - gerações finais (inclusive `entregue` e `falhou`) com mais de 90 dias e `limpa_em` nulo, em lotes;
  - candidatos não escolhidos, inclusive `image_par_id` e `teste_audio_id`;
  - pular o que estiver em uso e os candidatos com a mídia já nula (revogação LGPD da 025);
  - apagar as linhas numa transação por geração, e os objetos **depois do commit**
    (`apagar_por_excecao("candidatos_90d")`);
  - `limpa_em`;
  - o evento `eliminacao_candidatos` (contagens e bytes).

  A trilha `geracao_limpeza` no `agendador.py` e o CLI `sociman geracoes limpar [--dry-run]`
  (`system:cli`).
- [X] T057 [P] [US6] `tests/integration/test_geracao_limpeza.py` (SC-006):
  - 89 × 91 dias em cada estado final;
  - o escolhido intacto (os dois lados do par);
  - `revisao` antiga intocada;
  - um arquivo em uso mantido (com `mantidos` no evento);
  - idempotente;
  - o `--dry-run` não apaga nada;
  - os objetos do MinIO só depois do commit;
  - o evento com quem, quando, contagem e motivo;
  - nenhuma rota HTTP dispara a limpeza;
  - candidato com a mídia nula (como deixa a revogação da 025) é pulado, sem erro.

---

## Phase 9: Polish & Cross-Cutting

- [X] T058 [P] `tests/unit/test_constitution_guards.py`: rodar de novo com todo o código (T010). O teste
  "toda rota `RequireHuman` está em `PROIBIDAS`" continua verde.
- [X] T059 [P] `CLAUDE.md` (acréscimo), seção "Geração local (desde a spec 021)":
  - o pacote, as tabelas e os estados (com `entregue`);
  - o serviço `gerador` e os logs (`docker compose logs -f gerador`);
  - **o `dockerctl` é o único com o socket do Docker** (risco; nunca montar em outro serviço);
  - a rede `gpu-local` (dependência externa);
  - os pisos de VRAM e o "Aguardando a GPU ficar livre";
  - o delete só por `apagar_por_excecao` (4.3.0);
  - os fakes.

  Em "Armadilhas": a rede `gpu-local` tem de existir antes do `up`; depois de mudar o `gerador`, rodar
  `docker compose restart gerador`. Em `docs/visao.md`: o item 021 no backlog.
- [X] T060 Verificação final (2026-10-07: pytest 3146+ verdes, e2e 86/87 com o `assets-escala` intermitente, verde sozinho; §2–§4 pendentes com o dono):
  - `npm run test:api` inteiro, ruff, `npm run gen:contract && npm run check:web`;
  - a suíte e2e inteira (com trava);
  - o quickstart §1 no dev.

  O quickstart §0 (X1, `dockerctl`, token), o §2 (piloto na GPU real, com o `docker inspect` 28 → 12), o
  §3 (GPU compartilhada e calibração dos pisos) e o §4 (`--dry-run`) são **com o dono**, à mão; registrar
  o resultado e ajustar os pisos no `config.py` se a calibração pedir. **Commit só quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate, com a emenda) → T002 e T003.
- **Phase 2** bloqueia tudo:
  - T004 → T005 e T006;
  - T007, T008, T009, T011, T012, T013 e T014 em paralelo;
  - T006 + T007 → T015 e T016;
  - T010 depois de T009.
- **US1 (Phase 3):** T016 → T017 → T018. T019 depois de T011 e T012. T020 depois de T017 e T019. T021 →
  T022 → T023 → T024. T025 e T026 depois de T024. T027 depois de T023 (cliente gerado) → T028. T029 →
  T030.
- **US2 (Phase 4):** depende da T024. T031 e T032 em paralelo → T033 → T034 e T035. T036 é independente →
  T037. T038 depois de T031. T039 depois de T029 e T033.
- **US3 (Phase 5):** depende da T021 e da T024. T040 → T042 → T044 → T045. T041 depois de T033. T043
  depois de T040 e T041.
- **US4 (Phase 6):** depende da Phase 2 e da T024; pode correr em paralelo com a US2. T046 → T047 → T048.
- **US5 (Phase 7):** T049 → T050 → T053; T051 é independente; T052 depois de T013 e T033; T054 depois de
  T050.
- **US6 (Phase 8):** depende da US1 (gerações escolhidas existem) e da T009. T055 → T056 → T057.
- **Serialização:**
  - o `gen:contract` (T023, T038, T042, T050);
  - os arquivos compartilhados (`gerador.py`: T024, T033, T041, T047, T052; `mcp/mapa.py`: T023, T042,
    T050; `docker-compose*.yml`: T029, T037);
  - os e2e, pela trava.
- **Phase 9** no fim.

### Paralelismo sugerido (agentes)

- **Frente A (API, núcleo):** T004, T006, T015–T017, T020–T024, T040, T042, T055–T056.
- **Frente B (motores e gerador):** T019, T031–T033, T041, T046–T047, T049, T052.
- **Frente C (testes e guardas):** T005, T007–T010, T012–T014, T018, T025–T026, T034–T035, T043, T048,
  T053, T057–T058.
- **Frente D (SPA e e2e):** T027–T030, T039, T044–T045, T054.
- **Frente E (infra):** T002–T003, T011, T036–T038, T051.

## Implementation Strategy

- **MVP:** US1 + US2. É o piloto `cenario.cena` com a GPU respeitada e a RAM devolvida, que é o que dá para
  validar com o dono na GPU real (quickstart §2–§3).
- **Depois:** a US3 (controle); a US4 e a US5 em paralelo (motores Claude e TTS, prontos para a 012 e a
  025); a US6 por último (nada é apagado antes de 90 dias).
- **Checkpoints:** depois da Phase 2, da US1, da US2 (com SC-002 e SC-003 verdes e, se possível, o §2 com o
  dono), da US5 e no fim.
