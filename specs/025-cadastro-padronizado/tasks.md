---

description: "Tarefas da feature 025-cadastro-padronizado"
---

# Tasks: Cadastro padronizado de avatar, voz e cenário (025-cadastro-padronizado)

**Input:** `specs/025-cadastro-padronizado/`, com:
- a spec, com as Clarifications de 2026-10-06;
- o plan, com as decisões do dono de 2026-10-07;
- a research R1–R22;
- o data-model;
- os contratos `contracts/http-api.md`, `contracts/passos.md` e `contracts/shop-tts-025.md`;
- o quickstart.

**Pré-requisitos:**
- a **021-geracao-local implementada e verde**, com:
  - `geracoes`, `geracao_candidatos` (com `image_par_id`) e `audios`;
  - o estado `entregue` e o passo `voz.teste`;
  - o protocolo `Aplicador` com `ao_mudar_estado`, `extras` e `geracao.fila.abertas_do_alvo`;
  - `storage.apagar_por_excecao` e `geracao/uso.py`;
  - o `gerador`, o `dockerctl` e a rede `gpu-local`.
- a **constitution 4.3.0** aplicada, com o texto da exceção 2 ajustado (D1 do dono: arquivos **e** textos
  que descrevem a pessoa, inclusive em versões antigas do histórico).
- o **shop-tts `v2`** com o `DELETE /v2/voices/{nome}` no ar (021 D3). É dependência externa em
  `../comfyui-docker/tts_service/` e não é editado aqui. Sem ele, só a §1 do quickstart roda.

A 025 mexe em `assets/models.py`, `assets/service.py`, `ia/tipos.py`, `geracao/passos.py`,
`geracao/uso.py`, `geracao/shoptts.py` e `geracao/gerador.py`. Nenhum outro agente pode estar editando
esses arquivos ao mesmo tempo (a 012 também pluga em `geracao/passos.py` e `geracao/uso.py`: serializar).

**Decisões do dono:**
- **2026-10-06 (spec):**
  - voz do perfil, com voz padrão no avatar;
  - escolha sempre humana, exceto a checagem de identidade;
  - limpeza de 90 dias;
  - gravação original guardada completa;
  - consentimento registrado só por humano (dono ou membro);
  - toda gravação pede consentimento;
  - revogação só do dono, apagando a mídia.
- **2026-10-07 (plan):**
  - D1 = limpar o texto que descreve a pessoa também nos snapshots antigos;
  - D2 = cenas (010) só listadas na revogação;
  - 021 D1 = `dockerctl`; 021 D2 = `gpu-local`; 021 D3 = shop-tts `v2` + `DELETE` antes da 025.

**Nomes canônicos:**
- **API:**
  - `assets/padrao.py` (domínio puro), `assets/service_padrao.py`, `assets/schemas_padrao.py`,
    `assets/router_padrao.py`;
  - pacote `vozes/` (`models`, `service`, `schemas`, `router`, `tts_id`);
  - `sociman_api/revogacao.py`;
  - `geracao/aplicadores_avatar.py`, `geracao/aplicadores_cenario.py`, `geracao/aplicadores_voz.py`,
    `geracao/vozes_sync.py`.
- **Rotas e `operationId`:** os de `contracts/http-api.md`: `assets_consentimento_*`, `vozes_*`, e o
  `assets_update`/`assets_file_upload`/`assets_revert`/`assets_restore`/`assets_get` estendidos.
- **Tabelas e colunas:**
  - `vozes`;
  - em `assets`: `origem`, `consentimento`, `voz_id`, `identidade`, `kit_status`;
  - em `asset_files`: `slot`, `geracao_id`, e os papéis `kit`/`variacao`;
  - enums `asset_origem`, `asset_kit_status`, `voz_origem`, `voz_status`.
- **Migration:** **`0021_cadastro_padronizado`** (`down_revision = "0020_geracao_local"`, provisório:
  confere no T001).
- **Histórico:** `entity_type = "voz"`; ações do asset `kit_escolhido`, `identidade`, `consentimento`,
  `revoked`.
- **Evento:** `eliminacao_lgpd` em `security_events`.
- **Tipo de IA:** `avatar.identidade` (`en`, `usa_guia = "so_proibidas"`).
- **Linha do gerador:** `vozes_sync` (`GERADOR_VOZES_SYNC_S`, padrão 60).
- **Identificador no shop-tts:** `tts_id(id) = "v_" + id.hex[:32]`.
- **SPA:**
  - `pages/assets/kit/*` (`KitAvatar`, `SlotCard`, `ConsentimentoCard`, `RevogarDialog`, `CenaVariacoes`);
  - `pages/perfis/tabs/VozesTab.tsx`, `pages/vozes/VozDetalhe.tsx`;
  - `lib/vozes.ts`, `lib/padrao.ts`.
- **Testes:**
  - `tests/integration/padrao_helpers.py` (semeadura de kit, vozes e consentimento);
  - `e2e/cadastro-padronizado.spec.ts`;
  - os fakes da 021 (`comfyui_fake`, `shoptts_fake`, `dockerctl_fake`) e o `anthropic_fake`.

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec -T api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/cadastro-padronizado.spec.ts]`.

Nada chama serviço real.

**Arquivos compartilhados, SÓ ACRÉSCIMO:**
- `apps/api/src/sociman_api/main.py`, `config.py` e `history.py`;
- `mcp/mapa.py`;
- `geracao/passos.py`, `geracao/uso.py` e `geracao/gerador.py`;
- `apps/web/src/App.tsx`;
- `apps/api/tests/unit/test_constitution_guards.py`;
- `e2e/helpers.ts` e `e2e/fakes/server.py`;
- `apps/api/tests/fakes/shoptts_fake.py` e `anthropic_fake.py`;
- `CLAUDE.md` e `docs/visao.md`.

`packages/contract/**` é gerado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US6 da spec

---

## Phase 1: Setup

- [ ] T001 **Gate:**
  - `ls apps/api/migrations/versions/` mostra a `0020_geracao_local` (ou o número que a 021 ocupou) como a
    última e nenhuma `0021_*`. Se a 021 não estiver aplicada ou o número estiver ocupado, pare e avise o
    líder; ajuste o `down_revision` com o líder;
  - `docker compose exec api uv run alembic heads` mostra uma head só;
  - `grep -n "4.3.0" .specify/memory/constitution.md` mostra a versão, com o texto da exceção 2
    citando "textos que descrevem a pessoa (inclusive em versões antigas do histórico)";
  - os testes da 021, da 007, da 008 e da 017 estão verdes:
    `npm run test:api -- tests/ -k "geracao or assets or ia_ or guia" -q`;
  - o protocolo da 021 existe: `grep -n "ao_mudar_estado\|abertas_do_alvo\|apagar_por_excecao\|image_par_id" -r apps/api/src/sociman_api/geracao apps/api/src/sociman_api/storage.py`;
  - `git status` só tem o esperado. O `.specify/feature.json` fica com o líder.
- [ ] T002 [P] `config.py` (acréscimo): `gerador_vozes_sync_s: float = 60`.
  - No `docker-compose.yml`, só no `gerador`: `GERADOR_VOZES_SYNC_S: ${GERADOR_VOZES_SYNC_S:-60}`.
  - No `docker-compose.e2e.yml`: `GERADOR_VOZES_SYNC_S=1`.

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** banco, modelos, domínio puro, tipo de IA e fakes.

- [ ] T003 Migration `apps/api/migrations/versions/0021_cadastro_padronizado.py`
  (`revision = "0021_cadastro_padronizado"`, `down_revision = "0020_geracao_local"`), conforme o
  data-model:
  - os 4 enums novos;
  - `ALTER TYPE asset_file_role ADD VALUE` `kit` e `variacao` em `autocommit_block`, antes dos CHECKs;
  - a tabela `vozes`, com os CHECKs (`ck_vozes_por_origem`, `ck_vozes_ref` com a exceção de revogada) e
    os índices (`uq_vozes_nome`, `ix_vozes_perfil`, `ix_vozes_sync`, `ix_vozes_remover`);
  - as colunas de `assets` (com a FK `voz_id`), a recriação de `ck_assets_campos_por_tipo`,
    `ck_assets_pessoa_real` e `ix_assets_voz`;
  - as colunas de `asset_files` (com a FK `geracao_id`), a recriação de `ck_asset_files_campos_por_papel`,
    `uq_asset_files_slot`, `uq_asset_files_variacao_label` e `ix_asset_files_geracao`;
  - o downgrade com recusa quando há dado novo (inclusive evento `eliminacao_lgpd`), recriando os CHECKs
    da 007 e o enum sem os 2 valores.
- [ ] T004 [P] `tests/integration/test_migration_0021.py`:
  - sobe sobre a 0020 com assets da 007 (avatar com looks e poses, cenário, fundo); as colunas novas
    ficam NULL e as telas da 007 seguem iguais (SC-007);
  - cada CHECK e índice único recusa com `INSERT` direto (slot duplicado ativo, `kit` sem `slot`,
    `variacao` sem `label`, `pessoa_real` sem consentimento, voz sintética sem descrição);
  - down vazio e recusa com dados.
- [ ] T005 `assets/models.py` (acréscimo):
  - `AssetOrigem`, `KitStatus`, `FileRole.kit`/`variacao` e o `_ROLE_ORDER` (kit primeiro);
  - as colunas novas;
  - os `__versioned_fields__` com `origem`, `consentimento`, `voz_id`, `identidade`, `kit_status`;
  - em `files`, `slot` e `geracao_id`;
  - `sorted_files` com o `kit` na ordem de `padrao.SLOTS`.
- [ ] T006 [P] `vozes/models.py`: `Voz` (`_Versioned`, `AuditMixin`), `VozOrigem`, `VozStatus`, com os
  `__versioned_fields__`/`__immutable_fields__` do data-model. `vozes/tts_id.py`: a função pura
  `tts_id`. Registrar no metadata.
- [ ] T007 [P] `assets/padrao.py` (domínio puro, sem I/O; R5–R8):
  - `SLOTS_AVATAR`, `SLOTS_CENARIO`, `PASSOS` (ordem e pré-requisitos), `NOTA_MINIMA = 7`;
  - `situacao(tipo, slots_ativos, identidade)`, `passo_aberto(...)` (com o motivo em pt-BR);
  - `PROIBIDO` (porte da regex do `pipeline/avatares.py`) e `checar_menoridade(*textos)`;
  - as instruções fixas KIT_FRONTAL, KIT_34_ESQ/DIR, KIT_CORPO, LOOK, POSE, CENA e VARIACAO (porte de
    `avatares.py`/`cenarios.py`), **sem** o `prompt` do avatar.
- [ ] T008 [P] `tests/unit/test_padrao.py`:
  - a tabela de `situacao` (incompleto/completo/atencao; nota 7 = completo, 6 = atencao; cenário);
  - `passo_aberto` em cada passo;
  - a regex nos termos do pipeline e em falsos positivos ("kitchen", "teenage-style" não; "teen" sim);
  - instruções sem o `prompt`. Em `tests/unit/test_tts_id.py`: formato `[a-z0-9_]{2,40}`, estável e
    único.
- [ ] T009 [P] `ia/tipos.py` e `ia/regras_padrao.py` (acréscimo, R4): o `TipoCampo` `avatar.identidade`
  (`en`, `usa_guia = "so_proibidas"`, `_PROMPT`), a regra padrão e o schema de saída:
  `notas` por slot `{nota 0..10, observacao}` e `descricao_prompt` (40–80 palavras, sem roupa/pose/fundo).
- [ ] T010 [P] Fakes (acréscimo):
  - `tests/fakes/anthropic_fake.py` responde o formato `identidade`, com notas configuráveis e o gatilho
    "proibida" (como na 017);
  - `tests/fakes/shoptts_fake.py` ganha o `DELETE /v2/voices/{nome}` e a inspeção das vozes importadas e
    removidas;
  - `e2e/fakes/server.py` ganha o mesmo, mais `/geracao-e2e/vozes-tts`.
- [ ] T011 [P] `tests/integration/padrao_helpers.py`: `avatar_com_slots(n)`, `cenario_com_cena()`,
  `voz(origem, status, com_ref)`, `consentimento(...)` e `escolher_opcao(geracao, n)` (pela rota da 021,
  com o worker falso).
- [ ] T012 `history.py` (acréscimo): `entity_type "voz"` e as ações `kit_escolhido`, `identidade`,
  `consentimento` e `revoked` nos rótulos do histórico.

---

## Phase 3: US1 — Kit padrão de um avatar sintético (P1) 🎯 MVP

**Objetivo:** do rosto de origem à checagem de identidade, com escolha humana em cada passo.
**Teste independente:** spec US1, com os fakes.

- [ ] T013 [US1] `assets/service_padrao.py`:
  - `aplicar_slot(db, actor, asset, slot(s), image(s), geracao)`: arquiva o ativo do slot, cria o
    `asset_files` `kit` com `geracao_id`, apaga `identidade`, recalcula `kit_status` e grava a versão
    `kit_escolhido`;
  - com os 5 slots, pede o `avatar.identidade` pelo `geracao.service` (autor = quem escolheu);
  - devolve os avisos `derivados_desatualizados` (R6).
- [ ] T014 [US1] `geracao/aplicadores_avatar.py`: aplicadores de `avatar.rosto_origem`, `rosto_frontal`,
  `rostos_34` (`image_id` → `rosto_34_esq`, `image_par_id` → `rosto_34_dir`, uma versão) e `corpo_base`,
  conforme `contracts/passos.md`:
  - `validar_alvo`: avatar, não revogado, `passo_aberto`, `geracao_em_andamento` por
    `abertas_do_alvo`;
  - `montar_params`: instrução fixa e referências; `checar_menoridade`; `extras` desconhecido → 400.
  Registrar em `geracao/passos.py`.
- [ ] T015 [US1] Aplicador de `avatar.identidade` (R4):
  - `montar_params` com as 5 imagens;
  - `aplicar` grava `identidade` (`modelo`, `data`, `geracao_id`, `notas`), o `prompt` sem trim (se a
    descrição não tiver proibida do perfil, por `ia.guia.achar_proibidas`) e `kit_status`, numa versão
    `identidade` com `details.automatico`, `details.ia` e as `proibidas`;
  - com proibida (sem 2ª tentativa, R4): as notas entram, o `prompt` fica e o aplicador ajusta o desfecho
    da chamada para `sem_acao`;
  - `ao_mudar_estado(→ falhou)`: deixa a "Checagem pendente" visível (`kit.checagemPendente`).
- [ ] T016 [US1] `assets/schemas_padrao.py` + `assets/service.py` (ganchos):
  - o `AssetDetail` com `origem`, `identidade`, `kitStatus` e `kit` (slots, passos, `geracaoAberta`,
    `checagemPendente`, `descricaoNaoAplicada`), e o `AssetCard` com `kitStatus`;
  - `AssetFile` com `slot`, `geracaoId` e `origemArquivo`;
  - o upload em slot (`role=kit`, `slot`, `origem` no `rosto_origem`) na rota existente, com a ordem
    de abertura.
- [ ] T017 [P] [US1] `tests/integration/test_kit_avatar.py`:
  - os cenários 1–4 e 7–8 da US1 com os fakes;
  - par 3/4 numa versão só;
  - passo fechado → 409 `passo_fechado`;
  - em andamento → 409 `geracao_em_andamento`;
  - menoridade → 400 sem geração;
  - o `prompt` ausente dos `params` de edição (FR-016).
- [ ] T018 [P] [US1] `tests/integration/test_identidade.py`:
  - completo (notas ≥ 7), atenção (< 7), "Refazer este passo";
  - proibida do guia não aplicada (sem 2ª tentativa, desfecho `sem_acao`, aviso; editar à mão passa);
  - Claude fora (`falhou`, checagem pendente, "Checar de novo");
  - a chamada em `ia_chamadas` com `geracao_id` e custo;
  - `prompt` gravado exatamente como veio.
- [ ] T019 [US1] `npm run gen:contract`; `lib/padrao.ts`; `pages/assets/kit/KitAvatar.tsx` e
  `SlotCard.tsx`:
  - 5 slots em ordem, bloqueados com o motivo;
  - os componentes da 021 (`PedirGeracao`, `AndamentoGeracao`, `OpcoesGeracao`) por passo, com o par
    lado a lado;
  - notas e observações, situação, "Refazer este passo", aviso de derivados;
  - descrição para prompts editável com `IaSelo`.
  Seção "Kit padrão" no `AssetDetalhe.tsx`.
- [ ] T020 [US1] e2e `e2e/cadastro-padronizado.spec.ts` (kit): pedir origem (4) → escolher → … →
  identidade com notas → `completo`; semear nota 6 → `atencao`; termo "teen" recusado.

---

## Phase 4: US2 — Voz do perfil e voz padrão (P1)

**Objetivo:** gravação ou sintética → candidatos → aprovada → sincronizada; testar; voz padrão.
**Teste independente:** spec US2, com o shop-tts falso.

- [ ] T021 [US2] `vozes/service.py`, `schemas.py`, `router.py` (`contracts/http-api.md`):
  - criar, listar (cursor), detalhe (`usadaPor`, `trocandoReferencia`, `sincronizacao`, `geracaoAberta`,
    `ultimoTeste`), update (`gravacaoAudioId` do perfil), arquivar, restaurar, versões e revert (só dono;
    `revert_midia_apagada`);
  - nome único → 409 `voz_nome_em_uso`; menoridade na `descricao` → 400.
  Rotas `RequireHuman` nas escritas. `include_router` no `main.py`.
- [ ] T022 [US2] `geracao/aplicadores_voz.py`:
  - `voz.gravacao` (exige `gravacao_audio_id` e consentimento → 400 `consentimento_ausente`) e
    `voz.design`: `montar_params` lê a voz (`tts_id`, `tom`, `descricao`, áudio);
  - `aplicar` grava `ref_audio_id`, `ref_texto`, `status = aprovada`, `sincronizada_em = null`;
  - `ao_mudar_estado`: `gerando` / `revisao` (+ `analise`) / volta ao anterior, usando
    `abertas_do_alvo(exceto=)`;
  - validação do `voz.teste` (referência e `sincronizada_em`, senão 409 `voz_nao_sincronizada`).
  Registrar em `geracao/passos.py`.
- [ ] T023 [US2] `geracao/vozes_sync.py` + linha no `geracao/gerador.py`:
  - importa (`/v2/voices/import` + conferência do `sha256` em `/voices`), grava `sincronizada_em`;
  - remove revogadas (`DELETE /v2/voices/{nome}`, 404 = ok) e zera `sincronizada_em`;
  - espera crescente em falha, só log. O `ALLOWED` do `geracao/shoptts.py` já traz o `DELETE` (T052 da 021): só conferir.
- [ ] T024 [US2] Voz padrão (R15): `PATCH` do asset com `vozId` (mesmo perfil, não arquivada, não
  revogada, com referência; senão 400 `voz_invalida`); `AssetDetail.vozPadrao` (com `arquivada` e
  `revogada`).
- [ ] T025 [US2] Provedor `vozes_e_consentimento` no `geracao/uso.py` (R22): gravação, referência e prova
  (de voz e de asset) nunca entram na limpeza de 90 dias.
- [ ] T026 [P] [US2] `tests/integration/test_vozes.py`:
  - os cenários 1–8 da US2;
  - estados pelo gancho (inclusive "Gerar outras" mantendo `gerando` e a falha voltando a `aprovada`
    com referência);
  - troca de referência mantendo a anterior até a escolha;
  - voz padrão (de outro perfil → 400; arquivada → aviso);
  - nome único entre ativas;
  - `voz.teste` termina em `entregue`, sem versão da voz;
  - a referência aprovada com `metricas.segundos` entre 8 e 13 (ou 6–15 com o aviso), mono 24 kHz
    (SC-005, com o fake devolvendo os casos).
- [ ] T027 [P] [US2] `tests/integration/test_vozes_sync.py`:
  - import com `tts_id`, `sha256` conferido e `sincronizada_em`;
  - shop-tts fora: "Não sincronizada" e nova tentativa;
  - a referência nova reimporta;
  - remoção de revogada idempotente.
  Mais o teste da limpeza da 021 com a gravação e a referência intactas aos 90 dias.
- [ ] T028 [US2] `npm run gen:contract`; `lib/vozes.ts`; `pages/perfis/tabs/VozesTab.tsx` (`?aba=vozes`,
  DataTable); `pages/vozes/VozDetalhe.tsx` (`/app/vozes/:id`, rota no `App.tsx`):
  - análise com avisos;
  - candidatos com `PlayerAudio`, duração, transcrição e similaridade;
  - "Testar" com o texto;
  - "Usada por", sincronização e histórico.
  Seção "Voz padrão" (`NativeSelect`) no avatar.
- [ ] T029 [US2] e2e (voz): criar voz de gravação → consentimento → enviar áudio → 3 candidatos →
  escolher → "Sincronizada" → testar → voz padrão do avatar → "Usada por".

---

## Phase 5: US3 — Pessoa real com consentimento (P1)

**Objetivo:** consentimento antes de foto ou gravação; revogação só do dono, com eliminação.
**Teste independente:** spec US3 e FR-033a.

- [ ] T030 [US3] `assets/service_padrao.py` + `assets/router_padrao.py`:
  - `assets_consentimento_registrar` (`RequireHuman`; `registrado_por` = ator; prova do perfil;
    `origem = pessoa_real` se vazia; versão `consentimento`);
  - o upload do `rosto_origem` com `origem = pessoa_real` sem consentimento → 400
    `consentimento_ausente`;
  - na leitura pelo MCP, a prova omitida (`temProva`).
  Em `vozes/router.py`: `vozes_consentimento_registrar` (só `gravacao`).
- [ ] T030a [US3] `history.py` (acréscimo, R10b): `redigir_versoes(db, entity_type, entity_id, campos, *,
  motivo="lgpd_revogacao", actor) -> int` (UPDATE em `before`/`after` de todas as versões, campos →
  `null`, `details.redigida`); `target_state` recusa versão redigida com 409 `versao_redigida`; o
  `VersionHistory` da SPA mostra "Redigido (LGPD)". Campos: asset `prompt`, `identidade`, `image_rules`,
  `consentimento.prova`; voz `ref_texto`, `analise`, `consentimento.prova`.
- [ ] T031 [US3] `sociman_api/revogacao.py` (R10, data-model "Escritas da revogação"):
  - `revogar_asset` e `revogar_voz` (`RequireHumanOwner`, `confirmo`, `version`), na ordem:
    1. cancelar as gerações abertas;
    2. mídia nula nos candidatos e `params` sem texto (`limpa_em`);
    3. apagar `asset_files`, `images`/`audios`;
    4. esvaziar o texto das `ia_chamadas`;
    5. limpar os snapshots por `history.redigir_versoes` (T030a);
    6. zerar os campos atuais;
    7. `revogado_em`/`revogado_por`; arquivar; versão `revoked`; evento `eliminacao_lgpd` (sem nome nem
       texto);
    8. depois do commit, `storage.apagar_por_excecao(..., excecao="lgpd_revogacao")` nos objetos;
  - `assets_consentimento_previa`: contagens e `cenasAfetadas` (D2: só lista).
  Rotas `assets_consentimento_revogar`, `assets_consentimento_previa` e `vozes_consentimento_revogar`.
- [ ] T032 [US3] Bloqueios pós-revogação: pedir geração (aplicadores), escolher (021), restaurar,
  reverter, `PATCH`, upload e voz padrão → 409 `consentimento_revogado`.
- [ ] T033 [P] [US3] `tests/integration/test_revogacao.py`:
  - membro → 403 e MCP → 403 `somente_humano`;
  - sem `confirmo` → 400;
  - avatar: todas as imagens (slots, looks, poses, candidatos, prova) e as linhas apagadas, e os objetos
    fora do bucket do fake;
  - voz: gravação, referência, candidatos, testes e prova apagados, e a remoção no shop-tts falso;
  - `geracao_candidatos` com mídia nula e o `escolhido_id` íntegro; `params` sem texto;
  - `ia_chamadas` sem texto e com custo mantido;
  - **nenhuma** versão antiga (em `before` nem `after`) com `prompt`/`identidade`/`image_rules`/prova,
    nem com `ref_texto`/`analise` na voz; `name`, consentimento (nome, data, quem) e `changed_fields`
    intactos; `details.redigida` em todas;
  - revert para uma versão redigida → 409 `versao_redigida` (inclusive testando o `target_state` direto
    numa entidade não revogada com versão redigida semeada);
  - o evento com as contagens;
  - restaurar e reverter recusados;
  - cenas da 010 intactas e listadas.
- [ ] T034 [P] [US3] `tests/unit/test_constitution_guards.py` (acréscimo):
  - só `revogacao.py` (e o `geracao/limpeza.py` da 021) importa `apagar_por_excecao`;
  - só `revogacao.py` faz UPDATE em `geracao_candidatos`, em `geracoes.params` ou em `entity_versions`, e
    só ele importa `history.redigir_versoes`;
  - nenhum módulo de `mcp/` ou `ia/` alcança a revogação;
  - os aplicadores de imagem e áudio da 025 só rodam pela escolha humana ("nunca auto").
- [ ] T035 [P] [US3] `tests/integration/test_padrao_permissoes.py`:
  - todas as rotas novas com cliente MCP (leitura ok; escritas 403 com o evento);
  - membro × dono (revogar e reverter só dono);
  - consentimento registrado por membro passa, com o autor gravado.
- [ ] T036 [US3] SPA: `ConsentimentoCard.tsx` (formulário com o aviso de menores e famosos, prova por
  imagem ou áudio) e `RevogarDialog.tsx` (só dono; `AlertDialog` com a prévia: contagens e cenas
  afetadas); estados "Revogado" no avatar e na voz.
- [ ] T037 [US3] e2e (pessoa real): foto sem consentimento recusada → registrar → foto vira origem →
  frontal abre; dono revoga → arquivado, restaurar indisponível, voz some do `/geracao-e2e/vozes-tts`.

---

## Phase 6: US4 — Looks e poses gerados (P2)

- [ ] T038 [US4] Aplicadores `avatar.look` e `avatar.pose` em `geracao/aplicadores_avatar.py`:
  - abrem com `rosto_frontal` e `corpo_base`;
  - base = `corpo_base` ou a pose em `referencias[0]`;
  - `rotulo` obrigatório; pose com rótulo conferido antes (409 `pose_label_in_use`) e de novo no
    `aplicar`;
  - `extras.quandoUsar` (≤ 300; outra chave → 400);
  - `aplicar` cria `referencia` com `look` ou `pose` com `label`/`quando_usar`, os dois com `geracao_id`.
- [ ] T039 [P] [US4] `tests/integration/test_looks_poses.py`: os cenários 1–5 da US4; o `prompt` fora
  dos `params`; uma geração por rótulo.
- [ ] T040 [US4] SPA: "Gerar look" e "Gerar pose" no avatar (rótulo, roupa, "quando usar", base); o
  selo "gerado"/"enviado" nos arquivos.

---

## Phase 7: US5 — Cenário padrão e variações (P2)

- [ ] T041 [US5] `geracao/aplicadores_cenario.py`:
  - `cenario.cena` **substitui** o aplicador piloto da 021: slot `cena`, `kit_status = completo`, o 1º
    vira `primary_file_id`;
  - `cenario.variacao` exige `cena`, `rotulo` único entre as variações ativas (409
    `variacao_label_in_use`) e `referencias = [cena]`;
  - `aplicar` cria a `variacao`.
  Atualizar o teste da 021 do piloto (`referencia` → slot `cena`), avisando o líder.
- [ ] T042 [P] [US5] `tests/integration/test_cenario_padrao.py`: os cenários 1–4 da US5; 768×1344;
  o kind `fundo`; o cenário da 007 sem kit continuando igual.
- [ ] T043 [US5] SPA: `CenaVariacoes.tsx` (cena, variações com rótulo, "Gerar variação" bloqueado sem
  cena).

---

## Phase 8: US6 — Trocar um slot e manter o kit coerente (P3)

- [ ] T044 [US6] `assets/service.py` `revert_asset` (R17):
  - arquivar antes e restaurar depois os arquivos `kit`/`variacao` (UNIQUE parcial, como o
    `_flush_labels`);
  - conferir os rótulos de variação;
  - recusar com consentimento revogado;
  - recalcular `kit_status` com a `identidade` da versão alvo.
  O upload num slot com os 5 preenchidos dispara a nova checagem.
- [ ] T045 [P] [US6] `tests/integration/test_assets_revert_slot.py`: os cenários 1–3 da US6; troca de
  `rosto_frontal` com o aviso `derivados_desatualizados`; revert para a versão anterior à troca (slot e
  identidade de volta).

---

## Phase 9: Polish & Cross-Cutting

- [ ] T046 `mcp/mapa.py` (acréscimo, R18):
  - leitura `vozes_listar`, `vozes_detalhe`, `vozes_versoes`;
  - proibidas do princípio VII: `vozes_revert`, `assets_consentimento_revogar`,
    `vozes_consentimento_revogar`, `assets_consentimento_previa`;
  - proibidas "cadastro é ato humano (009 FR-023)": `vozes_criar`, `vozes_update`, `vozes_archive`,
    `vozes_restore`, `assets_consentimento_registrar`, `vozes_consentimento_registrar`.
  O teste do mapa (todo `operationId` classificado) verde.
- [ ] T047 Guarda do princípio I (acréscimo): as rotas e os `operationId` novos sem "youtube"/"tiktok";
  `vozes/`, `revogacao.py` e os aplicadores sem `publicacao`.
- [ ] T048 `npm run gen:contract && npm run check:web` (contrato, typecheck, build, bundle, CSP, segredos).
- [ ] T049 [P] Desempenho (plan): pedir passo < 300 ms, escolher < 500 ms, detalhe do avatar < 200 ms,
  revogação de 50 arquivos < 5 s, medidos no teste com o volume semeado.
- [ ] T050 `CLAUDE.md` (acréscimo): a seção "Cadastro padronizado (desde a spec 025)", com:
  - slots e passos;
  - a escolha humana e a identidade direta com as proibidas;
  - `vozes` e o `tts_id`;
  - a `vozes_sync` no `gerador`;
  - o consentimento e a revogação (exceção 2, `revogacao.py`, snapshots limpos, cenas só listadas);
  - a dependência do shop-tts `v2` + `DELETE`.
  `docs/visao.md`: o item 025 no backlog.
- [ ] T051 Verificação final:
  - `npm run test:api` inteiro, ruff e `npm run gen:contract && npm run check:web`;
  - a suíte e2e inteira (com trava);
  - o quickstart §1 no dev.
  As §2–§5 são **com o dono**, à mão, com a GPU e o shop-tts reais; registre o resultado. **Commit só
  quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate) → T002.
- **Phase 2** bloqueia tudo:
  - T003 → T004, T005 e T006;
  - T007, T009, T010 e T011 em paralelo; T007 → T008;
  - T005 + T006 → T012.
- **US1 (Phase 3):** T013 → T014 → T015 → T016 → T017, T018 → T019 → T020.
- **US2 (Phase 4):** depende da Phase 2 e do consentimento de voz (T030, parte de voz), que pode vir
  antes:
  - T021 → T022 → T023;
  - T024 depois de T021 e T016;
  - T025 → T026, T027 → T028 → T029.
- **US3 (Phase 5):**
  - T030 depois de T016 e T021;
  - T031 depois de T013, T022 e T023;
  - T030a antes da T031 (`history.py` é compartilhado: só acréscimo);
  - T032 → T033, T034, T035 → T036 → T037.
- **US4 (Phase 6):** depois da T014. **US5 (Phase 7):** depois da Phase 2; só a T041 toca o piloto da 021.
  **US6 (Phase 8):** depois da T013 e da T016.
- **Serialização:**
  - o `gen:contract` (T019, T028, T048);
  - os arquivos compartilhados (`geracao/passos.py`: T014, T015, T022, T038, T041; `assets/service.py`:
    T016, T044);
  - os e2e, pela trava;
  - a 012 também pluga em `geracao/passos.py`/`uso.py`.
- **Phase 9** no fim; a T046 pode começar assim que as rotas existirem.

### Paralelismo sugerido (agentes)

- **Frente A (API, avatar e cenário):** T005, T007, T013–T016 → T038, T041, T044.
- **Frente B (API, vozes e revogação):** T006, T021–T025 → T030–T032.
- **Frente C (testes):** T004, T008, T010, T011, T017, T018, T026, T027, T033–T035, T039, T042, T045, T049.
- **Frente D (SPA e e2e):** T019, T020, T028, T029, T036, T037, T040, T043.

## Implementation Strategy

- **MVP:** a US1 (kit + identidade) com o cenário da US5. É o que destrava looks, poses e storyboards
  com a identidade estável.
- **Depois:** a US2 (vozes) junto com a US3 (consentimento é pré-requisito da gravação; a revogação fecha a
  US3); depois a US4 e a US6.
- **Checkpoints:** depois da Phase 2, da US1, da US2 + US3 (com o SC-003 e os guardas da exceção 2 verdes)
  e no fim. O uso real da voz só depois do shop-tts `v2` + `DELETE` no ar (021 D3).
