---

description: "Tarefas da feature 013-importacao"
---

# Tasks: Importação da agência (013-importacao)

**Input**: `specs/013-importacao/` (spec com Clarifications de 2026-10-06, plan, research R1–R12, data-model,
contracts/http-api.md, quickstart)

**Pré-requisito:** a 010 (cenas) criou a migration **`0015_cenas`** e está verde. A 013 encadeia a
`0016_importacao` nela. Nenhum outro agente pode estar editando `history.py`, `conteudos/video_proprio.py`,
`mcp/mapa.py` ou os `docker-compose*.yml` ao mesmo tempo.

**Decisões do dono (2026-10-06):**
- **Q1 (FR-014):** a prévia propõe `sem_acordo` para `autorizado`; o dono troca para `parceiro` linha a
  linha; canal existente nunca muda sem escolha explícita. `parceiro` e `sem_acordo` são aceitos como
  "igual" para `autorizado` (FR-015a); os 3 `pendente` como `parceiro` aparecem como divergência.
- **Q2 (FR-026):** cada clipe com linha no registro vira conteúdo `video_proprio` (014), sem destino, com
  dedup pelo SHA-256; ≈900 MB no HD, com o marcador e o piso.
- **Q3 (FR-027):** o SociMan é a fonte da verdade; o markdown fica como arquivo; reimportação manual, só o
  novo.

**Nomes canônicos:**
- **API:** pacote `sociman_api/agencia/` (`pastas`, `mapa`, `markdown`, `leitores`, `itens`, `conciliar`,
  `previa`, `aplicar`, `desfazer`, `models`, `schemas`, `router`).
  - Rotas: `GET /api/agencia/estado`, `POST /api/agencia/previa`, `POST /api/agencia/importacoes`,
    `GET /api/agencia/importacoes`, `GET /api/agencia/importacoes/{id}` e
    `POST /api/agencia/importacoes/{id}/desfazer`. `operationId` `agencia_*`.
  - Tabelas `agencia_importacoes` e `agencia_importacao_itens`. `entity_type` `importacao_agencia`.
  - Migration **`0016_importacao`** (`down_revision = "0015_cenas"`).
  - Config `AGENCIA_SHARED_DIR` e `AGENCIA_CLIPES_DIR`; montagens `AGENCIA_SHARED_HOST` e
    `AGENCIA_CLIPES_HOST`.
- **SPA:** `pages/configuracoes/ImportacaoAgencia.tsx` (`/app/configuracoes/importacao`),
  `pages/configuracoes/ImportacaoDetalhe.tsx` (`/app/configuracoes/importacao/:id`),
  `components/importacao/*` e `lib/importacao.ts`.
- **Testes:** `tests/integration/agencia_helpers.py` (gera a pasta sintética em `tmp_path`, perfis
  `taverna-teste` e `achados-teste`) e `e2e/importacao.spec.ts` com `e2e/fixtures/agencia/`.

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec -T api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/importacao.spec.ts]`.

Nada chama serviço real: o YouTube é o fake da 006 (`tests/fakes/`, `openshorts-fake` no e2e). **A pasta
real da agência nunca entra nos testes nem no repositório**; só o quickstart §5 a lê, com o dono.

**Arquivos compartilhados, SÓ ACRÉSCIMO:** `apps/api/src/sociman_api/main.py`, `config.py`, `history.py`
(só o contexto de origem), `mcp/mapa.py`, `apps/web/src/App.tsx`, `components/shell/Sidebar.tsx`,
`apps/api/tests/unit/test_constitution_guards.py`, `docker-compose.yml`, `docker-compose.e2e.yml`,
`.env.example`, `CLAUDE.md`, `docs/visao.md`. `packages/contract/**` é gerado.

**Privacidade:** nenhum log imprime texto de markdown, só caminhos relativos e contagens.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US7 da spec

---

## Phase 1: Setup

- [X] T001 **Gate:**
  - `ls apps/api/migrations/versions/` mostra a **`0015_cenas`** e nenhum `0016_*`;
    `docker compose exec api uv run alembic heads` mostra só `0015_cenas` (senão, pare e avise o líder);
  - `git status` só tem o esperado; `.specify/feature.json` aponta para a 013 (o líder cuida);
  - `ls ../shared/perfis ../media/clipes` existem no host (a montagem não pode criar pasta como root,
    armadilha 1).
- [X] T002 [P] `docker-compose.yml` (acréscimo, serviço `api`): volumes
  `${AGENCIA_SHARED_HOST:-../shared}:/agencia/shared:ro` e `${AGENCIA_CLIPES_HOST:-../media/clipes}:/agencia/clipes:ro`;
  `docker-compose.e2e.yml`: `./e2e/fixtures/agencia/shared` e `./e2e/fixtures/agencia/clipes` nos mesmos
  destinos, `:ro`; `.env.example`: as 2 variáveis comentadas. Conferir `docker compose config` e, com a
  stack no ar, que `touch /agencia/shared/x` falha no container.
- [X] T003 [P] `e2e/fixtures/agencia/`: pasta sintética mínima (2 perfis de teste com `perfil.md`,
  `fontes.md` com uma linha de cada status e uma sem YouTube, `pesquisa.md`, `registro-clipes.md` com 2
  linhas, 2 imagens PNG pequenas (uma com transparência), `shop/persona.md` + 1 imagem, um arquivo
  `nao-usar-ainda`, um `candidatos/…md`) e `clipes/<slug>/<data>/` com 2 MP4 de 2 s gerados por ffmpeg
  (testsrc, < 200 KB). Nada copiado da pasta real.

---

## Phase 2: Foundational (bloqueia todas as histórias)

- [X] T004 `agencia/models.py` + `migrations/versions/0016_importacao.py` (data-model): enums, as 2 tabelas,
  CHECKs, índice parcial único de `processando`, trigger `agencia_itens_so_insercao`.
- [X] T005 [P] `tests/integration/test_migration_0016.py`: upgrade/downgrade/upgrade; trigger recusa UPDATE
  de outra coluna e DELETE; o índice recusa duas `processando`.
- [X] T006 [P] `config.py` (acréscimo): `agencia_shared_dir` e `agencia_clipes_dir`.
- [X] T007 [P] `agencia/pastas.py` (R2): `varrer(raiz)` com `followlinks=False`, link só dentro da raiz,
  limites (2.000 entradas, 2 MB markdown, 20 MB imagem), `sha256_arquivo` em blocos, erros
  `agencia_pasta_indisponivel` e `agencia_pasta_grande`. Teste unitário `test_agencia_pastas.py` com
  `tmp_path` (link para fora, limite, pasta vazia).
- [X] T008 [P] `agencia/markdown.py` (R3): `normalizar`, `frontmatter`, `secoes`, `campos`, `tabelas`,
  `links`. `tests/unit/test_agencia_markdown.py` com variações reais de agente (negrito, crases, nota antes
  da tabela, `|` escapado, valor em várias linhas, "A DEFINIR").
- [X] T009 [P] `agencia/mapa.py` (R1): `MAPA` e `classificar(caminho)`. `tests/unit/test_agencia_mapa.py`:
  **cada um dos 71 caminhos do levantamento** (lista literal no teste, sem ler a pasta real) cai no leitor
  ou no motivo esperado; caminho desconhecido → "fora do mapeamento".
- [X] T010 [P] `agencia/itens.py` (R4): `Item`, situações, motivos e `chave_*` por tipo.
- [X] T011 `history.py` (acréscimo, R8): `origem_importacao` (contextvar) e `record` soma
  `{"importacao": …}` aos `details` quando ativo. Teste unitário: fora do contexto, nada muda.
- [X] T012 `conteudos/video_proprio.py`: extrair `create_de_arquivo(db, actor, perfil_id, path, filename,
  titulo, size, sha256)` do `create` atual, que passa a chamá-la. Rodar os testes da 014 de vídeo próprio
  (sem mudança de comportamento).
- [X] T013 `agencia/schemas.py` e `agencia/router.py` com as 6 rotas (H e `RequireUser`), por enquanto
  `previa` e `confirmar` devolvendo só o esqueleto; `main.py` (acréscimo). `npm run gen:contract`.
- [X] T014 [P] `tests/integration/agencia_helpers.py`: gerador da pasta sintética (perfil, fontes,
  pesquisa, ideias, registro, imagens com/sem transparência, persona, clipes por ffmpeg) com parâmetros
  para cada caso; `configurar_raizes(monkeypatch, tmp_path)`.
- [X] T015 [P] `tests/integration/test_agencia_permissoes.py`: membro → 403 `somente_dono`; cliente MCP e
  `system:*` → 403 `somente_humano` + evento; lista, detalhe e estado abertos ao membro (SC-005).

**Checkpoint:** migration, leitura segura, parser e rotas protegidas prontos.

---

## Phase 3: User Story 1 - Pré-visualizar sem gravar (Priority: P1) 🎯 MVP

**Goal**: a leitura classifica perfis, contas e todos os arquivos em novo/igual/diverge/fora, sem gravar.

### Testes da US1

- [X] T016 [P] [US1] `tests/unit/test_agencia_leitores.py`: `ler_index` e `ler_perfil` (frontmatter, §1 e
  §2; status mapeado; contas do §1 com URL; "Nenhum" não cria; nicho > 200 com aviso); arquivo sem seção
  obrigatória → `nao_reconhecido` com o que faltou.
- [X] T017 [P] [US1] `tests/integration/test_agencia_previa.py`: pasta com 1 perfil novo, 1 igual, 1 com
  nicho diferente (diverge) e 1 arquivo fora do mapa → situações, contagens e origem; **nenhuma linha do
  banco muda** (contagem de `entity_versions` e das tabelas antes e depois); prévia expira (TTL reduzido no
  teste) e é de uso único; pasta inacessível → 503; perfil arquivado → `diverge(arquivado)`; slug que colide
  → `fora`; pasta de perfil sem `perfil.md` → `fora`.

### Implementação da US1

- [X] T018 [US1] `agencia/leitores.py`: `ler_index`, `ler_perfil` (perfil e contas).
- [X] T019 [US1] `agencia/conciliar.py`: perfil e conta (R5).
- [X] T020 [US1] `agencia/previa.py`: varrer as 2 raízes, aplicar o mapa (itens `fora` com motivo), chamar
  os leitores e a conciliação, montar contagens, `base` de versões, gravar no Redis (`SET EX`), resposta
  `Previa`. Rota `agencia_previa` completa; 409 `importacao_em_andamento`. `npm run gen:contract`.
- [X] T021 [US1] `agencia_estado` (FR-028): raízes disponíveis, última importação, por perfil "arquivos
  mudaram" pelas impressões digitais.
- [X] T022 [P] [US1] SPA: `lib/importacao.ts`, `pages/configuracoes/ImportacaoAgencia.tsx` (estado, "Ler a
  pasta", cartões de contagem, `DataTable` com filtros por perfil/tipo/situação, motivo, tempo restante),
  `components/importacao/PreviaTabela.tsx` e `ItemDiverge.tsx` (lado a lado); rota no `App.tsx` e link na
  Sidebar (acréscimos); botões só para dono.
- [X] T023 [US1] e2e `e2e/importacao.spec.ts` (US1): ler a pasta do fixture e conferir contagens, um
  `diverge` lado a lado e um `fora` com motivo; membro não vê "Ler".

**Checkpoint:** o dono vê o relatório completo de perfis e contas, e todo arquivo com destino ou motivo.

---

## Phase 4: User Story 2 - Confirmar, histórico, sem duplicar (Priority: P1)

**Goal**: gravar o que o dono marcou, de uma vez, com histórico e idempotência.

### Testes da US2

- [X] T024 [P] [US2] `tests/integration/test_agencia_confirmar.py`: 3 novos + 1 diverge "manter" → 3
  criados, 1 mantido; diverge "usar o markdown" → versão nova com `details.importacao` e o dono como autor
  (SC-004), revertível pelo histórico da entidade; escolhas inválidas → 422; segunda confirmação → 409
  `previa_expirada`; entidade editada entre prévia e confirmação → item `nao_gravado(editado_desde_a_leitura)`
  e o resto gravado; dono desativado antes da tarefa de fundo → `falhou(dono_inativo)`; arquivo alterado → `nao_gravado(mudou_desde_a_leitura)`; erro no meio → `falhou`, 0
  mutações de domínio; importação `processando` parada há 10 min → `falhou(interrompida)` ao ler.
- [X] T025 [P] [US2] `tests/integration/test_agencia_idempotencia.py`: importar a pasta completa duas vezes
  → na 2ª, 0 entidades, 0 versões e 0 objetos novos no MinIO (SC-002); linha nova num `fontes.md` → só ela
  `novo`.

### Implementação da US2

- [X] T026 [US2] `agencia/aplicar.py` (R8): validar escolhas contra a prévia (`GETDEL`), criar a importação
  `processando` (history `created`), 202; tarefa de fundo: reconferir impressões, `datadir.ensure_writable`
  do total, gravar arquivos com progresso, transação única aplicando os itens pelos services sob
  `history.origem_importacao`, gravar `ImportacaoItem`s, fechar `concluida` ou `falhou` (history `updated`).
  Aplicadores de perfil e conta.
- [X] T027 [US2] Rotas `agencia_confirmar`, `agencia_importacoes_list`, `agencia_importacoes_get` (com
  filtros e a regra da importação interrompida). `npm run gen:contract`.
- [X] T028 [P] [US2] SPA: escolhas na tabela (checkbox de `novo`, `NativeSelect` "Manter o SociMan / Usar o
  markdown"), AlertDialog de confirmação com o resumo (criar, trocar, MB no HD), `Andamento.tsx` (polling 2 s),
  lista de importações e `ImportacaoDetalhe.tsx` (itens e resultado).
- [X] T029 [US2] e2e (US2): confirmar com uma troca, ver "concluída", ler de novo → 0 novos.

**Checkpoint:** MVP (US1 + US2) — perfis e contas importáveis com segurança.

---

## Phase 5: User Story 3 - Fontes e status de direito (Priority: P1)

**Goal**: canais-fonte do `fontes.md` com o direito proposto e decidido pelo dono.

### Testes da US3

- [X] T030 [P] [US3] `tests/unit/test_agencia_direito.py`: tabela de proposta e de aceitos (Q1, FR-015a)
  para os 5 status do markdown e a linha própria; identificação de link (`/channel/`, `/@`, `/c/`,
  `/user/`, sem esquema, com TikTok/Twitch junto, "não confirmado", "a confirmar"); texto da nota de
  evidência e corte no limite.
- [X] T031 [P] [US3] `tests/integration/test_agencia_direito.py` (fake do YouTube): canal novo com o direito
  proposto e a troca para `parceiro`; existente `parceiro` para `autorizado` → `igual`; existente
  `parceiro` para `pendente` → `diverge(direito)`, mantido por padrão, trocado só com "usar o markdown" via
  `mudar_direito` (histórico do canal com o dono); canal ligado a outro perfil → só o vínculo; duas linhas
  do mesmo canal com status diferentes → um item `diverge`; sem YouTube → `fora`; cota esgotada →
  `aguardando_cota` e o resto segue; **nenhum direito existente muda sem escolha** (SC-003).

### Implementação da US3

- [X] T032 [US3] `leitores.ler_fontes` (colunas obrigatórias/opcionais, células com vários links).
- [X] T033 [US3] `conciliar` de canal e vínculo (R6), com cache do `resolver` na prévia e
  `aguardando_cota`; aplicadores `create_canal` (+ `mudar_direito` para o status escolhido e a evidência),
  `update_canal` (vínculo) e `mudar_direito` (diverge).
- [X] T034 [P] [US3] SPA: `components/importacao/EscolhaDireito.tsx` (`NativeSelect` dos 4 status, com o
  status do markdown e a explicação "autorizado = risco aceito pelo dono, sem acordo"), lista "fontes para
  cadastrar à mão" com o texto original.
- [X] T035 [US3] e2e (US3): canal novo `autorizado` trocado para `parceiro`; um `pendente` existente como
  `parceiro` aparece como divergência de direito.

---

## Phase 6: User Story 4 - Imagens na biblioteca (Priority: P2)

### Testes da US4

- [X] T036 [P] [US4] `tests/integration/test_agencia_imagens.py`: imagem com SHA-256 existente → `igual` e
  0 objetos; poses no mesmo asset avatar; sticker com transparência → `sticker`, sem → `imagem`; logo só se
  o perfil não tiver; `nao-usar-ainda` → `fora`; imagem inválida → `fora` com o motivo; HD sem marcador ou
  abaixo do piso → importação `falhou` antes de gravar; imagem citada no `perfil.md` que não existe →
  `fora` ("arquivo citado não encontrado").

### Implementação da US4

- [X] T037 [US4] Leitor e conciliação de imagens do perfil (R9) e aplicadores (`create_asset`,
  `upload_file` com `role`/`label`, logo pelo `service_imagens`).

---

## Phase 7: User Story 5 - Guia, persona e anotações (Priority: P2)

### Testes da US5

- [X] T038 [P] [US5] `tests/integration/test_agencia_guia_anotacoes.py`: guia vazio → versão 1 com tom,
  vocabulário e "não faça" (sem proibidas); guia editado → `diverge(editado)`; §3/§6/§7 → 1 anotação cada;
  §8 com N linhas → N anotações; seção da pesquisa alterada → `diverge`, "usar o markdown" edita a
  anotação; texto > 4.000 dividido em partes; reimportar → `igual`; sugestões de bordão sem mudar o kit.
- [X] T039 [P] [US5] `tests/integration/test_agencia_persona.py`: persona no perfil que já tem a imagem
  (padrão); sem imagem igual → exige escolha (422 sem perfil); campos diferentes → `diverge` campo a campo;
  cenários como assets `cenario`.

### Implementação da US5

- [X] T040 [US5] Leitores `pesquisa`, `ideias`, partes §3/§4/§6/§7/§8 do `perfil.md` e `persona.md`;
  conciliação e aplicadores de guia (`service_guia.put_perfil`), anotações (`anotacoes.criar`/`editar`) e
  persona (`create_asset`, `upload_file`, `update`).
- [X] T041 [P] [US5] SPA: escolha do perfil da persona na prévia; sugestões de bordão como informação.

---

## Phase 8: User Story 6 - Clipes prontos (Priority: P3)

### Testes da US6

- [X] T042 [P] [US6] `tests/integration/test_agencia_clipes.py`: linha + vídeo → conteúdo `video_proprio`
  sem destino, título do registro (≤ 100), anotação no conteúdo com a origem; vídeo já importado (SHA-256)
  → `igual`; linha sem vídeo, vídeo sem linha e vídeo inválido → `fora`; o total de bytes entra na
  conferência do HD; status e métricas do registro não entram.

### Implementação da US6

- [X] T043 [US6] `leitores.ler_registro` e conciliação de clipes; aplicador com
  `video_proprio.create_de_arquivo` (vídeo e miniatura gravados na etapa de arquivos) + `anotacoes.criar`
  no alvo `conteudo`.
- [X] T044 [US6] e2e (US6): os 2 clipes do fixture viram conteúdos na Central, sem destino.

---

## Phase 9: User Story 7 - Ver e desfazer (Priority: P3)

### Testes da US7

- [X] T045 [P] [US7] `tests/integration/test_agencia_desfazer.py`: criado e intocado → arquivado; atualizado
  e intocado → revertido; editado depois → `nao_desfeito(editado_depois)`; canal com envio, conteúdo com
  destino ou asset no kit → `nao_desfeito(em_uso)`; nada apagado; importação `desfeita` com autor;
  guia criado pela importação → salvo vazio;
  desfazer de novo → 409; o banco volta ao estado anterior entidade por entidade (SC-007).

### Implementação da US7

- [X] T046 [US7] `agencia/desfazer.py` (R10) e rota `agencia_desfazer`.
- [X] T047 [P] [US7] SPA: "Desfazer" no detalhe (AlertDialog com o que será arquivado ou revertido) e os
  itens "não desfeito" com o motivo.
- [X] T048 [US7] e2e (US7): desfazer e conferir o perfil de teste arquivado.

---

## Phase 10: Polish & Cross-Cutting

- [X] T049 `mcp/mapa.py` (acréscimo): `agencia_previa`, `agencia_confirmar`, `agencia_desfazer` em
  `_PROIBIDAS_DONO`; `agencia_estado` em `_FORA_INFRA`; `agencia_importacoes_list` e
  `agencia_importacoes_get` como leitura. Rodar o teste de cobertura do mapa da 009.
- [X] T050 [P] `tests/unit/test_constitution_guards.py` (+013): `agencia/` sem `publicacao`, `httpx` e
  `canais.youtube` direto; sem escrita de arquivo (`open` em modo de escrita, `write_text`, `write_bytes`,
  `unlink`, `rename`, `mkdir`, `shutil`); sem "youtube"/"tiktok" nos `operationId` `agencia_*`.
- [X] T051 [P] Docs: `CLAUDE.md` (seção "Importação da agência (desde a spec 013)": montagens `:ro`, pacote,
  regras de direito, fonte da verdade, armadilha da pasta inexistente); `docs/visao.md` (item 013);
  nota para a agência (fora do SociMan): trocar os AGENTS.md para ler pelo MCP (FR-027).
- [X] T052 Verificação final:
  - `npm run test:api` inteiro, ruff, `npm run gen:contract && npm run check:web`;
  - a suíte e2e inteira (com trava);
  - quickstart §1–§4 no dev.

  O §5 (pasta real) é **com o dono**, depois de um backup do banco; registrar o resultado.
  **Commit só quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate) → T002, T003.
- **Phase 2** bloqueia tudo: T004 → T005; T006–T010 em paralelo; T011 e T012 independentes; T013 depois de
  T004 e T010; T014 e T015 depois de T013.
- **US1 → US2** (a US2 aplica o que a US1 lê). **US3, US4, US5 e US6** dependem da US2 (aplicar) e podem
  andar em paralelo entre si, cada uma com seu leitor e aplicador; elas mexem em `leitores.py`,
  `conciliar.py` e `aplicar.py`, então **um agente por vez** nesses arquivos (ou funções em módulos
  separados por tipo). **US7** depois da US2 (e cobre os tipos das outras histórias que já entraram).
- O `gen:contract` é serializado (T013, T020, T027, T046). Os e2e são serializados pela trava.
- **Phase 10** no fim (T049 depois de todas as rotas).

### Paralelismo sugerido (agentes)

- **Frente A (API, núcleo):** T004, T006–T013 → T018–T021 → T026–T027 → T046.
- **Frente B (tipos):** T032–T033, T037, T040, T043 (em sequência, por causa dos arquivos comuns).
- **Frente C (testes):** T005, T014–T017, T024–T025, T030–T031, T036, T038–T039, T042, T045, T050.
- **Frente D (SPA e e2e):** T022–T023, T028–T029, T034–T035, T041, T044, T047–T048.

## Implementation Strategy

O MVP é a US1 + US2 (ler, conferir e gravar com histórico e sem duplicar). A US3 (direito) vem logo em
seguida, por ser princípio inegociável e trazer a divergência dos 3 `pendente`. A US5 é o maior ganho para
os agentes (guia e notas pelo MCP). US4, US6 e US7 completam. Checkpoints: depois da Phase 2, da US1+US2,
da US3, e no fim com o quickstart §5 junto do dono.
