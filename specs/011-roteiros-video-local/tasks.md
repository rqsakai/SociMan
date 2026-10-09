---

description: "Tarefas da feature 011-roteiros-video-local"
---

# Tasks: Roteiros com vídeo local (011-roteiros-video-local)

**Input:** `specs/011-roteiros-video-local/`:
- a spec, com as Clarifications de 2026-10-08;
- o plan, com P1–P7;
- a research R1–R20;
- o data-model;
- `contracts/http-api.md`, `contracts/comfyui-blocos.md` e `contracts/shop-tts-pronuncias.md`;
- o quickstart.

**Pré-requisitos:**
- **021** verde (`0020_geracao_local` + `0021_geracao_interrupcoes`);
- **025** implementada (`0023_cadastro_padronizado`: `vozes`, kit, `assets.voz_id`, consentimento,
  `revogacao.py`);
- **012** implementada (`0022_produtos_shop`: `produtos`, `produto_variantes`, ponte em `cenas`).

Sem as duas últimas, **não comece** (T001).

**Nomes canônicos:**
- **Pacote e tabelas:**
  - pacote `sociman_api/roteiros/`;
  - tabelas `roteiros`, `roteiro_produtos`, `roteiro_cenas`, `roteiro_narracoes`, `roteiro_entregas`,
    `roteiro_padroes` e `pronuncias`.
- **Enums:**
  - novos: `roteiro_formato`, `roteiro_modo`, `roteiro_status`, `roteiro_etapa` e `cena_motor`;
  - valores novos em enums existentes: `tomada_origem` + `geracao_local`, `image_kind` + `keyframe`,
    `geracao_alvo` + `cena`/`roteiro`, `geracao_motor` + `ffmpeg`.
- **Passos novos:** `roteiro.plano`, `roteiro.narracao`, `cena.keyframe`, `cena.clipe`, `roteiro.montagem`,
  `roteiro.acabamento`.
- **Ator:** `system:roteiro` (exibido "sistema (automático)").
- **Entidades no histórico:** `roteiro`, `roteiro_padroes` e `pronuncia`.
- **Rotas:** `roteiros_*`, `roteiro_padroes_*` e `pronuncias_*` (contracts/http-api.md).
- **SPA:** `/app/roteiros`, `/app/roteiros/novo`, `/app/roteiros/:id`, e a aba `?aba=video-local` do
  perfil.

`packages/contract/**` é gerado. Nunca edite `.specify/feature.json` nem `../comfyui-docker/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US8 da spec

---

## Phase 1: Setup

- [ ] T001 **Gate:**
  - `docker compose exec api uv run alembic heads` mostra **`0023_cadastro_padronizado`** como único head, com
    `0022_produtos_shop` e `0021_geracao_interrupcoes` antes dele. Com outro head, pare e corrija
    `down_revision` no data-model, no plan e na T004 com o líder;
  - as tabelas `produtos`, `produto_variantes` e `vozes` existem, e `assets.voz_id` também;
  - os testes da 010, 012, 021 e 025 estão verdes: `npm run test:api -- -k "cenas or produtos or geracao
    or vozes or kit" -q`;
  - `git status` só tem o esperado.
- [ ] T002 **Emenda 4.4.0** da constitution via `/speckit-constitution`: a exceção (1) do princípio VII,
  com o texto do plan.md (Constitution Check), **aprovado pelo dono antes de gravar**. Tipo da emenda:
  MINOR. O Sync Impact Report vai no topo e é retirado antes do commit.
- [ ] T003 [P] Copiar os 5 blocos (`contracts/comfyui-blocos.md`) de `../comfyui-docker/workflows/api/` (só
  leitura) para `apps/api/src/sociman_api/geracao/workflows/`: `clipe_minimax`, `clipe_wan`,
  `clipe_wan_qualidade`, `clipe_ltx` e `upscale_video` (`.api.json` + `.params.json`). Atualizar o
  `MANIFEST.json` (origem + sha256) e conferir no `upscale_video.api.json` o tamanho de bloco de 41
  quadros (R11). Anote se for outro valor.

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** banco, modelos, fakes, funções puras e as extensões da 021 e da 010 que todas as histórias
usam.

- [ ] T004 Migration `apps/api/migrations/versions/0024_roteiros_video_local.py` (`down_revision =
  "0023_cadastro_padronizado"`), exatamente como o data-model §Migration: os enums (`ADD VALUE` em
  `autocommit_block`), as 7 tabelas, as FKs `use_alter`, o trigger `roteiro_entregas_so_insercao`, as
  colunas em `cenas`/`cena_tomadas`/`geracoes`/`geracao_candidatos`/`conteudos`, o `ck_geracoes_passo`
  com os 21 passos, o `ck_candidatos_midia`, o trigger `geracao_candidatos_midia` atualizado e o downgrade
  com recusa. **Backup antes de aplicar no dev:** `pg_dump` para
  `/media/sakai/BACKUP/tiktok/sociman/backups/pre-0024.dump`, sob o `flock` combinado.
- [ ] T005 [P] `apps/api/tests/integration/test_migration_0024.py` cobre:
  - upgrade sobre dados da 010, 012, 021 e 025, com as colunas novas nulas e os padrões corretos;
  - cada CHECK e trigger recusa um INSERT direto: `ck_roteiros_falhou`, `ck_tomadas_origem_local`,
    `ck_tomadas_limpa`, `ck_tomadas_limpa_local`, `ck_candidatos_midia`, o trigger de mídia (vídeo em
    `cena.clipe`, áudio em `roteiro.narracao`) e UPDATE/DELETE em `roteiro_entregas`;
  - downgrade vazio passa e downgrade com dados é recusado.
- [ ] T006 `roteiros/models.py`: as 7 entidades do data-model, com `__versioned_fields__` (incluindo as
  propriedades `produtos` e `posicoes`) e `__immutable_fields__`. Também:
  - `cenas/models.py`: as 8 colunas, `CenaMotor`, `TomadaOrigem.geracao_local`, as colunas novas da tomada
    e o conjunto `CAMPOS_LOCAIS`;
  - `geracao/models.py`: `GeracaoAlvo` + `cena`/`roteiro`, `GeracaoMotor.ffmpeg`, `desuso_em`, as colunas
    de vídeo do candidato;
  - `conteudos/models.py`: `gerado_ia`, imutável;
  - `perfis/models.py`: `ImageKind.keyframe`;
  - `history.py`: os 3 `entity_type` e o nome "sistema (automático)" para `system:roteiro`.
- [ ] T007 [P] `config.py`: `roteiro_max_cenas: int = Field(8, ge=1, le=20)` (R14). Em
  `docker-compose.yml`, `docker-compose.test.yml` e `docker-compose.e2e.yml`, a variável
  `ROTEIRO_MAX_CENAS` vai nos serviços `api` e `gerador`. `.env.example` com a chave comentada.
- [ ] T008 [P] `roteiros/tempos.py` com `limites()` puro (R6: LEAD 0,08, TAIL 0,45, mínimo 1,0, 3 casas) e
  as fórmulas de quadros por motor (R4, arredondando para cima, com 0,1 s de folga e teto do motor). Testes
  em `tests/unit/test_roteiro_tempos.py`:
  - `test_tempos_bia_vo`, com `tests/fixtures/bia_vo_timings.json` (só números de
    `runs/bia_vo/narration/timings.json`) e a velocidade 1,08: espera 3,327 / 6,722 / 5,315 / 1,826;
  - posições não contíguas → erro;
  - quadros dos 4 motores, inclusive o teto.
- [ ] T009 [P] `roteiros/pronuncia.py` com `aplicar(texto, dic)` (palavra inteira, sem diferenciar
  maiúsculas, preservando a inicial, igual a `tts_service/app.py:40-56`) e `hash_atual(frases, dic,
  voz_id, ref_audio_id, velocidade)` (R10). Testes em `tests/unit/test_roteiro_pronuncia.py`.
- [ ] T010 [P] `cenas/prompt_local.py`: `montar_clipe()` puro (R7) com `MOUTH_CLOSED`, `AMBIENTE_FIXO` e o
  sufixo de realismo; a fala, o texto na tela e o áudio nunca entram. Também `avisos_keyframe(instrucao)`
  (luz, "phone video"). Testes em `tests/unit/test_prompt_local.py`, com e sem avatar e com
  `detalhe_produto`.
- [ ] T011 [P] `roteiros/montagem.py`: construtores **puros** dos comandos ffmpeg (R2, R11):
  - corte por posição: `scale/pad` para a resolução da cena, `fps=24`, `trim=duration`, `-an`;
  - concat;
  - mistura da narração com `loudnorm=I=-14:TP=-1.5:LRA=11`;
  - `atempo`;
  - acabamento: `hqdn3d=0:0:3:3`, `lanczos`, `crop=1080:1920`, `unsharp=3:3:0.3`, `fps=24`, crf 16 e
    `+faststart`.

  Os executores (subprocess, temporário em `work/tmp/roteiros/<geracao>/` e `finally`) vão em funções
  separadas. Testes de comando em `tests/unit/test_montagem_comandos.py`. Nenhum `tpad`/clone (a tomada
  curta é recusada antes).
- [ ] T012 Extensões da 021 em `geracao/`:
  - `passos.py`: os 6 passos (motor, alvo, resultado `texto|audio|imagem|video`, `n`, `sem_escolha`,
    `bloco`, `image_kind`);
  - `comfyui.py`: `BLOCOS` + os 5 blocos, `run_bloco` com saída `kind = "video"` (o arquivo vem em
    `outputs[node].images`), teto por bloco (comfyui-blocos.md) e o upload de vídeo pelo `/upload/image`;
  - `fila.py`: claim por `motor = 'ffmpeg'` fora do `uq_geracoes_gpu_rodando`;
  - `gerador.py`:
    - a `LinhaMontagem` (thread, como a `LinhaClaude`);
    - `_gravar_video` (ffprobe, miniatura pelo `compose.extract_frame`, `put` no bucket `videos` e na
      miniatura de `imagens`, candidato com as colunas de vídeo);
    - a narração pelo `shoptts.tts_paragraph` + `atempo` + tempos divididos (R5);
  - `storage.py`: `Excecao` + `intermediarios_90d`;
  - `midia.py`: `MidiaKind "geracao_video"`.

  Atualize os testes da 021 que fixam listas: `test_geracao_passos`, `test_workflows_manifest`,
  `test_clientes_da_geracao_com_lista_fechada`.
- [ ] T013 [P] Fakes de vídeo e narração:
  - `tests/fakes/comfyui_fake.py`: reconhece os 5 blocos novos e devolve um mp4 `ffmpeg -f lavfi
    testsrc2` na largura, altura, fps e quadros pedidos, com cache por parâmetros; o `upscale_video`
    devolve a entrada no tamanho pedido; falhas como as da 021;
  - `tests/fakes/shoptts_fake.py`: `/v2/tts_paragraph` com wav senoidal e tempos proporcionais, guarda o
    último `pronuncias`, modos `ok=false` e 503 (shop-tts-pronuncias.md);
  - `tests/integration/roteiro_helpers.py`: semear perfil + produto aprovado + avatar com kit e voz
    aprovada + cenas, `rodar_ate(roteiro, status)` usando o `rodar_gpu` da 021.
- [ ] T014 [P] Extensões da 010:
  - `cenas/service.py`: validação de `CAMPOS_LOCAIS` (409 `cena_usada` em `usada`), `marcar_pronta(db,
    ator, cena)` reutilizável (R8) e `duplicar` copiando os campos locais **sem** keyframe (FR-025);
  - `cenas/tomadas.py`: `registrar_tomada(..., origem, prompt_usado=None, geracao_id=None,
    keyframe_image_id=None, motor=None, objeto_existente=None)`, em que o `geracao_local` aponta o objeto
    do candidato sem copiar (R3);
  - schemas e detalhe da cena com os campos novos, `keyframeAntigo` e `limpa`.

  Teste em `tests/integration/test_cena_local.py`.
- [ ] T015 `auth/deps.py`: `ROTEIRO = Actor(kind="system:roteiro")`. Em `geracao/service.py`,
  `escolher_automatico(db, geracao)` (R9), com as 3 conferências na mesma transação e recusa de qualquer
  passo que não seja `cena.keyframe`. Teste em `tests/integration/test_roteiro_automatico.py` (parte 1:
  recusas fora do roteiro).
- [ ] T016 Guardas em `tests/unit/test_constitution_guards.py`, seção 011:
  - só `roteiros/automatico.py` chama `escolher_automatico`;
  - `roteiros/` não importa `publicacao`, `mcp` nem `httpx`;
  - nenhuma rota do `roteiros/` sem `RequireUser`/`RequireHuman`/`RequireHumanOwner`, nem com
    "youtube"/"tiktok";
  - o UPDATE em `geracao_candidatos` só existe em `revogacao.py` e `geracao/limpeza.py`;
  - o `DELETE_PERMITIDO` não muda;
  - o `revogacao.py` não referencia `cena_tomadas`, `roteiro_*` nem os passos novos (R16).

**Checkpoint:** a migration está aplicada, as funções puras estão testadas e os fakes devolvem vídeo e
narração.

---

## Phase 3: User Story 1 — Criar o roteiro e planejar com a IA (P1) 🎯 MVP

**Goal:** criar o roteiro, pedir o plano (Claude) e editar e aprovar o TEXTO.
**Independent Test:** spec US1.

- [ ] T017 [US1] `roteiros/schemas.py` e `roteiros/service.py`:
  - `criar`: voz padrão do avatar, portões do padrão do perfil, produtos aprovados (FR-003/004), 409
    `limite_cenas`;
  - `editar`: frases, posições, produtos, avatar e voz, com a validação do data-model (frases contíguas,
    toda frase numa posição, `invalid_roteiro` com `field`);
  - `arquivar` e `restaurar`, com o histórico (FR-006).
- [ ] T018 [US1] `roteiros/maquina.py`, parte 1: `avancar()` com o roteiro em `FOR UPDATE`, as etapas
  `rascunho → planejando → aguardando_texto | narrando`, os portões e o modo (FR-007/008), o `falhou`
  com a etapa e o `comandado_por`.
- [ ] T019 [US1] `ia/tipos.py`: `roteiro.plano` (entidade `roteiro`, schema de saída `PlanoSaida`, com
  frases, posições e cenas novas). Em `roteiros/aplicadores.py`, o aplicador `roteiro.plano`:
  - `montar_params` com o brief, as fichas da 012, a descrição fixa do avatar da 025 e a lista de cenas do
    perfil daquele avatar e produto (FR-013);
  - `aplicar` grava as frases e as posições, cria as cenas novas pela 010 em `rascunho`, com o autor = quem
    pediu e `details.ia` (FR-014), e corta no `ROTEIRO_MAX_CENAS`, com aviso;
  - o gancho chama `avancar`.
- [ ] T020 [US1] `roteiros/router.py` e `router_perfil.py`: `roteiros_listar`, `roteiros_criar`,
  `roteiros_detalhe`, `roteiros_editar`, `roteiros_planejar`, `roteiros_aprovar` (só `texto` nesta
  fase; as outras histórias somam os seus portões), `roteiros_tentar_de_novo` (de `falhou`, retoma da
  etapa gravada, sem refazer as anteriores, FR-011), `roteiros_arquivar`, `roteiros_restaurar`, `roteiros_versoes` e `roteiros_reverter` (só o dono).
  Também `main.py`, `mcp/mapa.py` (escritas em `PROIBIDAS`, leituras em `FORA`) e o `errors.ts` via
  `npm run gen:contract`.
- [ ] T021 [P] [US1] `tests/integration/test_roteiro_fluxo.py::test_plano_e_portao_texto`, com o Claude
  falso respondendo `PlanoSaida`: reaproveita 1 cena, cria 2, fica em `aguardando_texto`, salva a edição e
  a reordenação com histórico, registra a aprovação com o autor, e a chamada fica no registro da 008 com
  `geracao_id`. Mais os casos de produto desaprovado (US1-7), de limite de cenas (FR-047) e do "Tentar de novo"
  (um `falhou` no plano retoma em `planejando` e não refaz nada antes, FR-011).
- [ ] T022 [US1] SPA:
  - `lib/roteiros.ts` (hooks, polling de 2 s com geração aberta);
  - `pages/roteiros/RoteirosList.tsx` (`FilterBar`, `ServerPagination`, `EmptyState`);
  - `RoteiroNovo.tsx` (perfil, nome, brief, produtos aprovados, avatar, voz);
  - `RoteiroDetalhe.tsx` com a etapa `etapas/Texto.tsx` (editar frases, trocar, reordenar, reaproveitar
    ou duplicar cena, atribuir frase → cena, aprovar);
  - item "Roteiros" no `nav.ts`, rotas lazy e `Page` como raiz.

**Checkpoint:** US1 funciona sozinha com o Claude falso.

---

## Phase 4: User Story 2 — Narração contínua (P1)

**Goal:** narração com a voz, a velocidade e as pronúncias, e as durações derivadas.
**Independent Test:** spec US2.

- [ ] T023 [US2] Aplicador `roteiro.narracao`:
  - `montar_params` com as frases, a voz (`tts_id` da 025), a seed e as pronúncias do perfil, e recusa de
    voz revogada ou arquivada (R16);
  - `aplicar` cria a `roteiro_narracoes` com o `texto_hash`, aponta `roteiros.narracao_id`, grava
    `inicio_s`/`duracao_s` nas posições por `tempos.limites` e põe `desuso_em` na narração anterior;
  - `ok=false` vira `entrada_invalida` com "a narração não bateu com o texto" (FR-020).
- [ ] T024 [US2] `maquina.py`, parte 2: `narrando → aguardando_narracao | gerando_keyframes`. A narração
  ativa desatualizada (hash) volta para `narrando` e pede outra (FR-019). O `roteiros_aprovar` passa a
  aceitar o portão `narracao`.
- [ ] T025 [P] [US2] `tests/integration/test_roteiro_fluxo.py::test_narracao`:
  - o pedido ao fake levou as frases em ordem e as pronúncias;
  - o áudio está na velocidade;
  - as durações batem com `limites`;
  - editar uma frase, trocar a voz ou mudar a velocidade deixa a narração desatualizada, pede outra e
    guarda a antiga;
  - voz sem consentimento leva 409.
- [ ] T026 [US2] SPA `etapas/Narracao.tsx`: player do take inteiro, frases com início e fim (clicar toca
  do ponto), velocidade, trocar voz e aprovar. `components/roteiro/LinhaTempos.tsx`.

---

## Phase 5: User Story 3 — Keyframe por cena (P1)

**Goal:** 2 opções por cena sem keyframe atual, escolher, regerar, editar a instrução e as referências, e
subir uma imagem pronta.
**Independent Test:** spec US3.

- [ ] T027 [US3] Aplicador `cena.keyframe` (alvo `cena`):
  - `montar_params`: `base_image` = 1ª referência, `ref1` e `ref2`, a instrução, seeds, `n = 2`,
    `extras.roteiroId/ordem`, conferência de consentimento do avatar (R16) e avisos da instrução (FR-028);
  - `aplicar`: `keyframe_inicial_id`, `keyframe_geracao_id`, versão da cena com `details.geracao_id`
    (numa cena `usada`, aceita o primeiro keyframe e recusa a troca com 409 `cena_usada`, FR-024);
  - gancho `rodando → revisao` chama `roteiros/automatico.py`, depois `avancar`.
- [ ] T028 [US3] `roteiros/automatico.py`: em modo `automatico` ou com `portoes.keyframes = false`,
  `escolher_automatico(geracao)` (R9).
- [ ] T029 [US3] `maquina.py`, parte 3:
  - `gerando_keyframes` pede `cena.keyframe` só para as posições sem keyframe atual (cenas repetidas
    pedem uma vez só);
  - `→ aguardando_keyframes` quando todas estão em `revisao` ou escolhidas;
  - ao passar o portão, `marcar_pronta` nas cenas em `rascunho` (R8), parando com o motivo se a validação
    falhar;
  - o `roteiros_aprovar` passa a aceitar o portão `keyframes`.
- [ ] T030 [US3] Rotas `roteiros_regerar_keyframe` (grava a instrução e as referências e descarta a
  aberta) e `roteiros_enviar_keyframe` (multipart ≤ 20 MB, `imaging` com `kind = keyframe`, aspecto da
  cena ±1%, normalizado). `docker/nginx/default.conf.template` com a `location` de 21m e `docker compose
  restart edge` (armadilha 13).
- [ ] T031 [P] [US3] `tests/integration/test_roteiro_fluxo.py::test_keyframes`:
  - só as cenas sem keyframe geram;
  - "Usar opção 2" grava na cena;
  - regerar cria a geração só daquela cena, com seeds novas;
  - o upload vira keyframe sem geração;
  - cena `usada` leva 409;
  - aprovar marca `pronta`.
- [ ] T032 [P] [US3] `tests/integration/test_roteiro_automatico.py`, parte 2:
  - automático e portão desligado escolhem a opção 1 com o ator `system:roteiro` e a versão da cena com
    `details.automatico`;
  - o portão ligado não escolhe;
  - a geração de `cena.keyframe` pedida fora de roteiro nunca é escolhida sozinha;
  - o roteiro arquivado no meio não escolhe.
- [ ] T033 [US3] SPA `etapas/Keyframes.tsx`: por posição, as opções (componentes `OpcoesGeracao` da 021),
  regerar com a instrução e as referências (seletor de imagens do kit, do look, do produto e do cenário),
  `FileField` para subir, os avisos e aprovar.

---

## Phase 6: User Story 4 — Clipe por cena, com reuso (P1)

**Goal:** clipe no motor da cena, tomada `geracao_local`, reuso sem GPU, regerar, trocar o motor e
escolher tomada.
**Independent Test:** spec US4.

- [ ] T034 [US4] Aplicador `cena.clipe` (alvo `cena`):
  - `montar_params`: o bloco `clipe_<motor>`, `start_image` (e `end_image`), o prompt de
    `prompt_local.montar_clipe`, a resolução da cena, os quadros de `tempos` e o fps, conferência de
    consentimento (R16);
  - `aplicar`: `registrar_tomada(origem=geracao_local, objeto_existente=candidato)` com
    `keyframe_image_id`, `motor`, `fps` e `prompt_usado`; `roteiro_cenas.tomada_id`; `desuso_em` na
    tomada anterior da posição.
- [ ] T035 [US4] `maquina.py`, parte 4:
  - `gerando_clipes` usa a tomada útil quando há (R10, sem job) e pede `cena.clipe` só para as outras;
  - tomada mais curta que a posição pede clipe novo;
  - `→ aguardando_clipes | montando`;
  - o `roteiros_aprovar` passa a aceitar o portão `clipes`.
- [ ] T036 [US4] Rotas `roteiros_regerar_clipe` (motor opcional; grava `cenas.motor` se a cena não estiver
  usada) e `roteiros_escolher_tomada` (tomada da cena com duração suficiente, inclusive do Flow; 400
  `tomada_curta`).
- [ ] T037 [P] [US4] `tests/integration/test_roteiro_reuso.py`:
  - a cena reaproveitada com tomada útil não gera job de GPU (SC-003);
  - os 2 clipes saem com o motor certo e os quadros da fórmula;
  - a tomada aponta o objeto do candidato (sem cópia);
  - regerar com `wan` cria só aquela geração;
  - escolher outra tomada não gera nada;
  - a tomada do Flow só entra pela escolha manual.
- [ ] T038 [US4] SPA `etapas/Clipes.tsx`: `components/roteiro/PlayerVideo.tsx` (`<video>` com o link de
  mídia), motor por posição, regerar, a lista das tomadas da cena (com "keyframe antigo" e "arquivo
  removido") e aprovar.

---

## Phase 7: User Story 5 — Prévia, acabamento e conteúdo (P2)

**Goal:** montagem fora da GPU, portão FINAL, acabamento HD e entrega na 014.
**Independent Test:** spec US5.

- [ ] T039 [US5] Aplicador `roteiro.montagem` (motor `ffmpeg`): o executor da `LinhaMontagem` baixa as
  tomadas e a narração, roda `montagem.py` (corte, concat, mistura a −14 LUFS) e grava o candidato de
  vídeo. Tomada curta recusa antes, com o aviso `tomada_curta` na posição e a volta para os clipes
  (FR-032). O `aplicar` aponta `roteiros.montagem_geracao_id` e põe `desuso_em` na anterior.
- [ ] T040 [US5] Aplicador `roteiro.acabamento` (motor `comfyui`, linha GPU, RAM 28 GB): por posição, corta,
  roda o `upscale_video` na resolução da cena e aplica o `hqdn3d`; depois concat, lanczos para 1080×1920
  a 24 fps e a narração (R11); grava o candidato de vídeo e roda o `comfy_free` no fim.
- [ ] T041 [US5] `roteiros/entrega.py` + `conteudos/video_proprio.create_de_objeto` (miolo extraído do
  `create_de_arquivo`: cópia do objeto no MinIO para `conteudos/{id}/video.mp4`, ffprobe e pôster). No
  `aplicar` do acabamento, numa transação só:
  - conteúdo com `gerado_ia = true` e título = nome do roteiro;
  - `roteiro_entregas` (posições, motores);
  - `cenas.usos.definir` com o ator `comandado_por`;
  - `roteiros.status = pronto` e `conteudo_id`;
  - `desuso_em` no candidato do acabamento (R12, R13).
- [ ] T042 [US5] `maquina.py`, parte 5: `montando → aguardando_final | finalizando → pronto`. Roteiro
  `pronto` editado reabre a etapa, e a nova entrega cria um conteúdo novo. O `roteiros_aprovar` passa a
  aceitar o portão `final`.
- [ ] T043 [US5] Padrão `conteudoIa = true` nos destinos de conteúdo `gerado_ia`: no servidor, quando o
  campo vier ausente (onde se montam as `opcoes_rede`), e na SPA (`TikTokPostForm.tsx`, valor inicial).
  `GET /api/conteudos/{id}` com `geradoIa` e `roteiro {id, nome, motores, avisoAtribuicao}` (R13). No
  detalhe do conteúdo, o selo "Gerado por IA" e o aviso do MiniMax.
- [ ] T044 [P] [US5] `tests/integration/test_roteiro_entrega.py`:
  - a montagem não pega a trava de GPU (com um job de GPU rodando, ela termina) (FR-043);
  - a prévia dura a soma e tem o áudio;
  - o acabamento sai em 1080×1920 a 24 fps e −14 LUFS ±1 (medido com `ffprobe` e `ebur128`, SC-007);
  - o conteúdo nasce `gerado_ia`, sem nenhum destino (SC-005);
  - as cenas viram `usada`;
  - a entrega fica registrada;
  - tomada curta não monta.
- [ ] T045 [US5] SPA `etapas/Final.tsx`: player da prévia, aprovar e, depois de `pronto`, o link para o
  conteúdo.

---

## Phase 8: User Story 6 — Portões e modo automático (P2)

**Goal:** portões configuráveis por roteiro e o padrão do perfil.
**Independent Test:** spec US6.

- [ ] T046 [US6] Rota `roteiros_controle` (FR-009: ligar para numa etapa futura; desligar onde está parado
  = aprovar no nome de quem desligou; `details {de, para}`). `roteiros/service_padroes.py` + rotas
  `roteiro_padroes_ler` e `roteiro_padroes_salvar` (sem linha = padrão do código, `version 0`).
- [ ] T047 [P] [US6] `tests/integration/test_roteiro_permissoes.py` e
  `test_roteiro_fluxo.py::test_tres_configuracoes`:
  - três roteiros (todos os portões, só KEYFRAMES, automático) param onde devem;
  - ligar um portão no meio para nele;
  - cliente MCP, `system:*` e agente levam 403 `somente_humano` + `publicacao_recusada` em criar,
    planejar, aprovar, controle, regerar, enviar keyframe e escolher tomada (SC-008);
  - o `test_mcp_mapa` classifica todas as rotas.
- [ ] T048 [US6] SPA `components/roteiro/Portoes.tsx` (5 chaves + modo, no topo do detalhe) e
  `pages/perfis/tabs/VideoLocalTab.tsx` (o padrão do perfil).

---

## Phase 9: User Story 7 — Voltar uma etapa e invalidações (P2)

**Goal:** cascata sem apagar e cancelamento das gerações abertas.
**Independent Test:** spec US7.

- [ ] T049 [US7] `maquina.py`, parte 6: a etapa da mudança, conforme o data-model §Máquina:
  - frases, voz, velocidade ou pronúncia → `narrando`;
  - keyframe → `gerando_clipes` (só a cena);
  - posições ou tomada → `montando`;
  - duração maior que a tomada → `gerando_clipes`.

  Cancela as gerações abertas das etapas seguintes com o ator da mudança e põe `desuso_em` nos
  artefatos substituídos. Restaurar e voltar a ser atual limpa o `desuso_em`. A troca de keyframe chama
  `avancar` em **todos** os roteiros não arquivados que usam aquela cena, não só no que mudou.
- [ ] T050 [P] [US7] `tests/integration/test_roteiro_invalidacoes.py`:
  - editar uma frase em `aguardando_final` volta para `narrando`, muda as durações, só a posição que
    cresceu pede clipe e a montagem é refeita;
  - trocar o keyframe regera só aquela cena, e um 2º roteiro com a mesma cena também volta a
    `gerando_clipes` naquela posição;
  - uma cena `usada` do Flow sem keyframe ganha o primeiro; a troca seguinte leva 409 `cena_usada`;
  - depois de cada edição, a duração da prévia (`ffprobe`) bate com a soma das posições com diferença de
    no máximo 1 quadro por cena (SC-006);
  - uma duração que cabe reaproveita a tomada;
  - as gerações abertas são canceladas com o autor;
  - nada é apagado (SC-006).

---

## Phase 10: User Story 8 — Dicionário de pronúncia (P3)

**Goal:** pronúncias por perfil, no pedido e no hash.
**Independent Test:** spec US8.

- [ ] T051 [US8] `roteiros/service_pronuncias.py` + rotas `pronuncias_listar`, `criar`, `editar`,
  `arquivar` e `restaurar` (`entity_type pronuncia`, 409 `pronuncia_existe`). A mudança em pronúncia de
  palavra presente nas frases deixa a narração desatualizada pelo hash (FR-019).
- [ ] T052 [P] [US8] `tests/integration/test_pronuncias.py`: o par salvo com histórico, a duplicata
  recusada (sem diferenciar maiúsculas), o pedido leva o dicionário, o texto mostrado não muda e a edição
  deixa a narração desatualizada.
- [ ] T053 [US8] SPA: as pronúncias na `VideoLocalTab.tsx` (tabela, incluir, editar, arquivar).

---

## Phase 11: Limpeza, revogação e acabamento final

- [ ] T054 `roteiros/retencao.py` (seleção pura dos protegidos e dos elegíveis, R12). `geracao/limpeza.py`,
  fase 2, na mesma trilha `geracao_limpeza` e no CLI `sociman geracoes limpar [--dry-run]`:
  - apaga os objetos com `apagar_por_excecao(excecao="intermediarios_90d")`;
  - zera a mídia nas linhas e preenche `limpa_em`;
  - DELETE de `audios`;
  - grava o evento `eliminacao_intermediarios`.
- [ ] T055 [P] `tests/integration/test_roteiro_limpeza.py` (SC-009):
  - `desuso_em` de 91 dias é limpo e o de 89 não;
  - ficam protegidos a entrega, a tomada escolhida, a tomada atual da posição, a narração ativa, o
    keyframe atual, a tomada do Flow e a mídia em uso;
  - a segunda rodada não faz nada;
  - o evento tem as contagens;
  - a tela mostra "arquivo removido".
- [ ] T056 [P] `tests/integration/test_roteiro_revogacao.py` (FR-048):
  - revogar a voz e o avatar (pela `revogacao.py` da 025) não toca tomadas, narrações, entregas nem
    conteúdos;
  - narração, keyframe e clipe novos levam 409 `consentimento_revogado` (ação humana) ou `falhou` (máquina);
  - montar e finalizar com o que existe continuam;
  - as referências apagadas aparecem como "referência removida".
- [ ] T057 [P] e2e:
  - `e2e/fakes/geracao_fake.py`: blocos de vídeo devolvendo `e2e/fixtures/geracao/clipe_8s.mp4` (736×1280,
    cor sólida, ~60 KB) e `/shop-tts/v2/tts_paragraph` com `narracao.wav` fixo e tempos;
  - `e2e/roteiros.spec.ts`: criar, planejar, aprovar o texto e a narração, escolher um keyframe e subir
    outro, aprovar os clipes e o final, e o conteúdo aparece em Conteúdos com "Gerado por IA". Mais um
    roteiro automático que termina sem parar, contando as ações humanas (criar, planejar, ligar o
  automático): no máximo 3 (SC-001). Use `nav(page, "Roteiros")` e `preencherData` quando
    precisar;
  - rodar com `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/roteiros.spec.ts`.
- [ ] T058 Docs:
  - `CLAUDE.md` do SociMan: seção "Roteiros (desde a spec 011)", com pacote, máquina, automático,
    limpeza 4.4.0, `ROTEIRO_MAX_CENAS` e X3;
  - `docs/visao.md`: 011 ✅;
  - os `[X]` nesta lista.
- [ ] T059 Verificação final, com o código congelado:
  - `npm run test:api`, `docker compose exec api uv run ruff check .`, `npm run gen:contract && npm run
    check:web`;
  - a suíte e2e completa sob `flock`;
  - o quickstart §1.

  Os testes de tempo só valem sem e2e rodando (`flock -n /tmp/sociman-e2e.lock true`). O §2 em diante é
  com o dono.

---

## Dependencies & Execution Order

- **Setup (T001–T003)** antes de tudo; T002 (emenda) antes de T054.
- **Foundational (T004–T016)** bloqueia as histórias. T004 vem antes de T005–T006. T008–T011 e T013 rodam
  em paralelo. T012 depende de T006. T014 e T015 dependem de T006.
- **Ordem das histórias:**
  - **US1 → US2 → US3 → US4 → US5** (cada etapa precisa da anterior para testar o fluxo de ponta a ponta);
  - **US6** depende de US1 e US3 (portões e escolha automática);
  - **US7** depende de US2–US5;
  - **US8** depende de US2.
- **Limpeza e revogação (T054–T056)** depois de US5. **e2e (T057)** depois de US6. T058 e T059 no fim.

## Parallel Opportunities

- T003, T007, T008, T009, T010, T011 e T013 (arquivos diferentes).
- Dentro de cada história, os testes [P] rodam em paralelo com a SPA da mesma história, depois do
  service e do aplicador.
- T055, T056 e T057.

## Implementation Strategy

- **MVP = US1 + US2 + US3 + US4 + US5** (o vídeo sai, com todos os portões ligados, que é o padrão).
- Depois, **US6** (automático), **US7** (invalidações), **US8** (pronúncias) e a limpeza.
- Pare a cada checkpoint para o dono ver na tela de dev.
