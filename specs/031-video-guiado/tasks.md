---

description: "Tarefas da feature 031-video-guiado"
---

# Tasks: Vídeo guiado (031-video-guiado)

**Input:** `specs/031-video-guiado/`:
- a spec, com as Clarifications de 2026-10-13 (7 respostas);
- o plan, com P1–P8;
- a research R1–R12;
- o data-model;
- `contracts/http-api.md`;
- o quickstart.

**Pré-requisitos:**
- a **011** na main (`0027_roteiros_video_local`);
- o PR da **correção de memória do ComfyUI** (2026-10-13) mesclado (research R12).

**Nomes canônicos:**
- **Migration:** `0028_video_guiado`.
- **Tabelas novas:** `roteiro_conversa`, `roteiro_trechos` e `cena_quadros`.
- **Enums novos:** `roteiro_tipo_video`, `conversa_estado`, `conversa_tipo`, `posicao_reuso` e
  `quadro_papel`.
- **Passos novos:** `roteiro.perguntas` e `roteiro.ajuste`.
- **Formatos da IA:** `perguntas_roteiro`, `ajuste_roteiro` e `plano_roteiro` v2.
- **Config:** `ROTEIRO_TRECHO_BASE_S=5` e `ROTEIRO_GRADE_MAX=6`.
- **Ator da máquina:** `system:roteiro`.
- **SPA:** `/app/estudio/videos/novo` passa a ser o guiado (`VideoNovo.tsx`). O detalhe continua em
  `/app/roteiros/:id`, com o switch wizard/avançado.

**Testes:** pedidos pela constitution (princípio VI) e pela spec (SC-001 a SC-008). Cada história tem os seus
testes **antes** da implementação.

**Regras:**
- E2e só com `flock /tmp/sociman-e2e.lock npm run test:e2e`.
- Não tocar no `../comfyui-docker`.
- Sem commit nem push até o dono pedir.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Gate: conferir que `alembic heads` = `0027_roteiros_video_local` e que a correção de memória (o `devolver_ram` com `_soltar_comfy` em `apps/api/src/sociman_api/geracao/gerador.py` e o `uso_preso` em `docker/dockerctl/server.py`) está na branch. Rodar `npm run test:api -- -k "roteiro or geracao_memoria or dockerctl"` verde antes de começar
- [X] T002 [P] Config: `roteiro_trecho_base_s: int = Field(5, ge=3, le=10)` e `roteiro_grade_max: int = Field(6, ge=1, le=12)` em `apps/api/src/sociman_api/config.py`, mais as linhas comentadas no `.env.example`

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** dados, grade, quadros e trechos básicos (2 quadros = 1 trecho), montagem com duração exata e os fakes. Sem isso, nenhuma história gera vídeo.

- [X] T003 Migration `apps/api/migrations/versions/0028_video_guiado.py` (`down_revision = "0027_roteiros_video_local"`), conforme o data-model:
  - **enums:** os 5 novos;
  - **colunas em `roteiros`:** `tipo_video`, `cenario_id` (FK `assets`), `duracao_alvo_s`, `trecho_base_s`, `conversa_estado`, e o CHECK `ck_roteiros_guiado` ("todos preenchidos ou todos nulos");
  - **colunas em `roteiro_cenas`:** `trechos` (CHECK 1..3), `reuso`, `motivo` (≤ 300), `aprovado_keyframes_em/por`, `aprovado_clipe_em/por`, `orcamento_chars`;
  - **`roteiro_trechos`:** PK (`roteiro_id`, `ordem`, `trecho`) e `tomada_id` FK `cena_tomadas`;
  - **colunas em `cenas`:** `trechos` (1..3) e `origem_cena_id` (FK `cenas`);
  - **`cena_quadros`:** `ordem` 0..3, `papel`, `instrucao` ≤ 2000, `image_id`, `geracao_id`, `provisorio`, `archived_at`, e o UNIQUE parcial (`cena_id`, `ordem`) WHERE `archived_at IS NULL`;
  - **colunas em `cena_tomadas`:** `trecho` (0..2) e `keyframe_fim_image_id`;
  - **`roteiro_conversa`:** `seq` UNIQUE por roteiro e o trigger `roteiro_conversa_so_insercao`;
  - **passos:** `roteiro.perguntas` e `roteiro.ajuste` no CHECK `ck_geracoes_passo`;
  - **downgrade** completo.
- [X] T004 [P] Teste `apps/api/tests/integration/test_migration_0028.py`:
  - upgrade e downgrade;
  - CHECK do guiado;
  - UNIQUE parcial dos quadros;
  - trigger só de inserção;
  - os roteiros da 011 ficam intactos.
- [X] T005 Modelos:
  - `CenaQuadro`, mais `trechos`/`origem_cena_id` em `Cena` e `trecho`/`keyframe_fim_image_id` em `CenaTomada`, em `apps/api/src/sociman_api/cenas/models.py`;
  - as colunas novas de `Roteiro`/`RoteiroCena`, `RoteiroTrecho` e `RoteiroConversa` em `apps/api/src/sociman_api/roteiros/models.py`;
  - `tipo_video`, `cenario_id`, `duracao_alvo_s` e `trecho_base_s` em `__versioned_fields__`, com `duracao_alvo_s`/`trecho_base_s` também em `__immutable_fields__`;
  - `roteiro_trechos` no snapshot de `posicoes`.
- [X] T006 [P] Puro `apps/api/src/sociman_api/roteiros/grade.py`:
  - `opcoes(base, maximo)`;
  - `valida_duracao(d, base, maximo)`;
  - `orcamento_chars(duracao_s) = floor(0.85 × duracao_s × 14)`;
  - `soma_fecha(posicoes, base, alvo)`;
  - `papeis(n_quadros)` → `inicio`/`meio1`/`meio2`/`fim`.
- [X] T007 [P] Teste `apps/api/tests/unit/test_roteiro_grade.py`: opções 5–30, duração fora da grade, orçamento, soma, papéis para 2, 3 e 4 quadros.
- [X] T008 Módulo `apps/api/src/sociman_api/cenas/quadros.py`:
  - criar, listar e arquivar quadros;
  - `definir_imagem(quadro, image_id, provisorio, ator)`;
  - espelhar `keyframe_inicial_id`/`keyframe_final_id` (quadro 0 e último) na mesma transação;
  - versão da cena com `details.quadro`;
  - `arquivar_desde(cena, ordem)`, que arquiva a ordem e as seguintes e recria as vagas com a mesma instrução.
- [X] T009 `apps/api/src/sociman_api/roteiros/estado.py`:
  - `tomada_serve_trecho(tomada, cena, t, base)` (R8: mesma cena e mesmo trecho, `keyframe_image_id` = quadro[t], `keyframe_fim_image_id` = quadro[t+1], `duracao_ms` ≥ base × 950);
  - `assinatura` incluindo os trechos;
  - `reposicionar` com as checagens de quadro sem imagem/provisório e de trecho sem tomada.
- [X] T010 `apps/api/src/sociman_api/roteiros/pedidos.py`:
  - `pedido_quadro(roteiro, posicao, ordem, n)`: quadro 0 com `base_image` = a imagem `cena` do cenário do roteiro, `ref1` = o `corpo_base` do avatar e `ref2` = o flat ou o recorte da variante; quadros 1+ com `base_image` = o quadro anterior, `ref1` = o produto e `ref2` = o `rosto_frontal` (R3);
  - `pedido_trecho(posicao, t)` com refs `[quadro[t], quadro[t+1]]`, `extras.trecho`, e quadros pelo `tempos.quadros_para(motor, base)`.
- [X] T011 `apps/api/src/sociman_api/geracao/passos.py`: os 2 passos novos (claude, 1/1, `sem_escolha`), `cena.keyframe` com `n_max` 4 e `extras.quadro`/`extras.trecho` repassados pelos aplicadores de `apps/api/src/sociman_api/geracao/aplicadores.py`.
- [X] T012 Aplicadores em `apps/api/src/sociman_api/roteiros/aplicadores.py`:
  - o do quadro grava a imagem no `cena_quadros` certo (pelo `extras.quadro`), e não mais só no `keyframe_inicial_id`;
  - o do trecho registra a tomada com `trecho` e `keyframe_fim_image_id` e a liga em `roteiro_trechos`.
- [X] T013 Montagem por trecho em `apps/api/src/sociman_api/roteiros/montagem.py` e `tempos.py`:
  - `cmd_trecho(video, base, primeiro)`: `setpts` para exatamente `base` s e remoção do 1º quadro quando não é o primeiro trecho (R2);
  - parâmetro `crossfade_quadros=0`;
  - concat por posição e concat do vídeo;
  - os roteiros da 011 continuam pelo caminho atual.
- [X] T014 [P] Teste `apps/api/tests/unit/test_montagem_trechos.py`, com mp4s sintéticos (`testsrc2`):
  - 124 quadros → exatamente 5,0 s;
  - 3 trechos → 15,0 s ± 1 quadro;
  - o último quadro do trecho = o quadro final, comparando o frame;
  - o 011 fica sem mudança (regressão do `test_tempos_bia_vo`).
- [X] T015 [P] Fakes:
  - `apps/api/tests/fakes/comfyui_fake.py`: grava o `end_image`/`base_image` de cada prompt e devolve mp4 de 124 quadros a 24 fps no clipe;
  - `apps/api/tests/fakes/anthropic_fake.py`: responde `perguntas_roteiro`, `ajuste_roteiro` (modo "ambíguo" → `pergunta`) e `plano_roteiro` v2 (modo "não cabe" → estoura o orçamento na 1ª tentativa);
  - helpers `criar_guiado` e `levar_ate` em `apps/api/tests/integration/roteiro_helpers.py`.

**Checkpoint:** migration, modelos, grade, quadros, trechos e montagem prontos, com os unitários verdes.

---

## Phase 3: User Story 1 - Começar um vídeo em blocos simples (P1) 🎯 MVP

**Objetivo:** o "Novo vídeo" em 6 blocos cria um roteiro guiado.

**Teste independente:** escolher os 6 blocos e ver o roteiro criado: voz padrão pré-escolhida, só itens utilizáveis, e voltar a um bloco mantém o que vale.

- [X] T016 [P] [US1] Teste `apps/api/tests/integration/test_video_guiado.py::test_criar_*`:
  - cria com a grade copiada;
  - a voz vazia vira a voz padrão do avatar;
  - sem voz padrão, 400 `voz_invalida`;
  - 422 `duracao_fora_da_grade`;
  - produto não aprovado → 422 `cena_invalida`;
  - perfil arquivado → 409 `perfil_base_arquivado`;
  - avatar revogado → 409 `consentimento_revogado`;
  - `GET /api/roteiros/grade`.
- [X] T017 [US1] `apps/api/src/sociman_api/roteiros/guiado.py` `criar_guiado(...)`:
  - valida pela 029 (itens de qualquer perfil base, não arquivados), pela 025 (consentimento e voz aprovada) e pela 012 (produto aprovado e variante com recorte);
  - nome padrão "<nome comercial do produto> – <dd/mm>";
  - grava os portões e o modo dos padrões do perfil;
  - `history.record`;
  - pede o `roteiro.perguntas` (`criar_para_alvo`).
- [X] T018 [US1] Schemas e rotas em `apps/api/src/sociman_api/roteiros/schemas.py` e `router.py`:
  - `POST /api/roteiros` (`roteiros_criar_guiado`) e `GET /api/roteiros/grade` (`roteiros_grade`);
  - campos aditivos no `Roteiro`;
  - `POST /api/perfis/{id}/roteiros` marcado `deprecated`;
  - classificar no `apps/api/src/sociman_api/mcp/mapa.py` (escrita em `PROIBIDAS`, leitura em `FORA`);
  - `npm run gen:contract`.
- [X] T019 [P] [US1] Miniaturas: conferir os resumos de asset (avatar, cenário) em `apps/api/src/sociman_api/assets/schemas.py`. Se faltar, somar `thumbUrl` (aditivo, imgproxy) à opção usada pelos seletores e atualizar o `gen:contract`.
- [X] T020 [P] [US1] Componente `apps/web/src/components/video-guiado/BlocoEscolha.tsx`:
  - cartões com imagem em `role="radiogroup"`/`role="radio"` + `aria-checked` (padrão do `components/marca/ProfileImagePicker.tsx`);
  - estado vazio com o link para o cadastro;
  - contador "N fora (motivo)";
  - variante de voz com o `components/geracao/PlayerAudio.tsx`.
- [X] T021 [US1] Página `apps/web/src/pages/roteiros/VideoNovo.tsx`:
  - os 6 blocos em sequência (tipo, perfil, avatar e voz, cenário, produto, duração);
  - voltar mantém as escolhas válidas e avisa as desmarcadas (FR-006);
  - resumo das 6 escolhas;
  - criar e ir para `/app/roteiros/:id`;
  - rota `/app/estudio/videos/novo` em `apps/web/src/App.tsx`;
  - remover `RoteiroNovo.tsx`;
  - hooks em `apps/web/src/lib/videoGuiado.ts`.
- [X] T022 [US1] E2e `e2e/video-guiado.spec.ts`, teste "blocos": criar pela tela com avatar com voz padrão, conferir a voz pré-escolhida e o produto em revisão fora, e trocar o perfil no bloco 5.

**Checkpoint:** US1 funciona sozinha (o roteiro guiado nasce e o chat é pedido).

---

## Phase 4: User Story 2 - Chat com perguntas fechadas, e a IA monta tudo (P1)

**Objetivo:** até 5 perguntas de múltipla escolha geradas numa chamada, as respostas gravadas e o plano v2 montado dentro da grade.

**Teste independente:** responder só com cliques e receber um plano cuja soma é a duração escolhida.

- [X] T023 [P] [US2] Teste `apps/api/tests/unit/test_plano_v2.py` (`problemas()` v2):
  - soma diferente da duração;
  - posição acima do orçamento;
  - `trechos` fora de 1..3;
  - `quadros` com tamanho diferente de `trechos + 1`;
  - reuso `total` com cena não candidata;
  - cena de outro produto.
- [X] T024 [P] [US2] Teste `apps/api/tests/integration/test_conversa.py`:
  - as perguntas são gravadas (≤ 5, de 2 a 6 opções);
  - responder só por cliques;
  - 409 `pergunta_respondida`;
  - 422 `opcao_invalida`;
  - retomar a conversa depois de reabrir;
  - a proibida do guia na resposta não entra no plano e gera um `aviso`;
  - `planejar` antes de responder → 409 `conversa_incompleta`;
  - a IA fora → "tentar de novo" sem perder as respostas;
  - histórico: cada resposta registra autor e data (FR-037).
- [X] T025 [US2] Formatos em `apps/api/src/sociman_api/ia/tipos.py` e `ia/saida.py`: `perguntas_roteiro` (1..5 perguntas, 2..6 opções, rótulo ≤ 60, texto ≤ 200) e `plano_roteiro` v2, com `usa_guia="completo"` e as regras de `contracts/http-api.md`.
- [X] T026 [US2] `apps/api/src/sociman_api/roteiros/conversa.py`:
  - montar a mensagem das perguntas (produto com a ficha da 012, avatar, cenário, duração, cenas candidatas);
  - aplicador do `roteiro.perguntas` (grava em `roteiro_conversa` e `conversa_estado = perguntando`);
  - `responder` (valida as opções, grava e, na última, `respondida`);
  - `refazer_perguntas`.
- [X] T027 [US2] `apps/api/src/sociman_api/roteiros/plano.py` v2:
  - blocos `<respostas>`, `<grade base=… alvo=…>` e `<cenas nivel=…>`;
  - `orcamento` por posição;
  - regras novas (trechos de 1 a 3, quadros = trechos + 1, estado final por quadro, nunca mudança de luz, close de lado);
  - o `RoteiroPlano.aplicar` do guiado cria as posições com `trechos`, `reuso`, `motivo` e `orcamento_chars`, as cenas novas com `cena_quadros` vazios e as instruções, e as derivadas no reuso `plano` (US4).
- [X] T028 [US2] Rotas `GET …/conversa`, `POST …/conversa/respostas` e `POST …/conversa/refazer-perguntas` em `apps/api/src/sociman_api/roteiros/router.py`, mais o `planejar` exigindo `respondida` no guiado; mapa do MCP e `gen:contract`.
- [X] T029 [US2] SPA `apps/web/src/pages/roteiros/wizard/Conversa.tsx` e `apps/web/src/components/video-guiado/Chat.tsx`:
  - uma pergunta por vez, com opções clicáveis (única/múltipla);
  - texto curto opcional (≤ 500);
  - os exemplos de pedidos prontos;
  - "Montar o vídeo" quando a conversa estiver respondida;
  - estado de "IA pensando" e "tentar de novo".
- [X] T030 [US2] E2e "chat" em `e2e/video-guiado.spec.ts`, mais os formatos novos no `e2e/fakes/server.py`: responder só por cliques e ver o resumo com a soma = duração.

**Checkpoint:** US1 + US2 levam do zero ao plano montado (SC-001).

---

## Phase 5: User Story 3 - Modo wizard: ouvir, ver e aprovar ou pedir troca (P1)

**Objetivo:** aprovar pelo áudio e pelas imagens, sem texto, e o "não aprovo" virando ajuste pela IA.

**Teste independente:** recusar 1 quadro com um pedido e ver só ele (e os seguintes) refeito, sem prompt na tela.

- [X] T031 [P] [US3] Teste `apps/api/tests/integration/test_recusar_ajuste.py`:
  - recusar a narração com "mais animada" muda só a velocidade ou o texto e refaz a narração, sem refazer os quadros;
  - recusar o quadro 1 refaz o 1 e os seguintes;
  - um pedido "ambíguo" vira esclarecimento sem geração;
  - o autor da mudança é o humano, com `details.ia`;
  - 409 `etapa_errada`;
  - `recusar`, `aprovar_posicao` e `definir_cena` gravam versão com autor, antes e depois (FR-037).
- [X] T032 [P] [US3] Teste da cadeia em `apps/api/tests/integration/test_quadros_cadeia.py`:
  - com n = 1, cada quadro vira provisório e o seguinte nasce dele (o `base_image` gravado no fake);
  - o portão keyframes só passa com todas as posições aprovadas;
  - `aprovar_posicao` com quadro faltando → 409 `nada_a_aprovar`;
  - com n = 2 (avançado), a cadeia espera a escolha humana.
- [X] T033 [US3] `apps/api/src/sociman_api/roteiros/automatico.py`: a regra "opção única de quadro de roteiro guiado", aplicada como `provisorio` com o ator `system:roteiro`. Ampliar a guarda AST em `apps/api/tests/unit/test_constitution_guards.py`: só o `automatico.py` chama `escolher_automatico`, e o provisório nunca aprova portão.
- [X] T034 [US3] Máquina em `apps/api/src/sociman_api/roteiros/maquina.py`:
  - `gerando_keyframes` encadeia por posição (pede o quadro i+1 quando o i fica pronto);
  - os portões `keyframes` e `clipes` passam por todas as posições aprovadas;
  - mudar um quadro zera o `aprovado_keyframes_*` da posição e o `aprovado_clipe_*` dos trechos afetados.
- [X] T035 [US3] `ajuste_roteiro` em `ia/tipos.py`/`ia/saida.py`, e o aplicador do `roteiro.ajuste` em `apps/api/src/sociman_api/roteiros/aplicadores.py`:
  - `pergunta` → `roteiro_conversa` `esclarecimento` (no máximo 3 por pedido);
  - `mudanca` → confere que só os campos do alvo mudam e aplica pelo `service.editar`, com o autor = quem recusou e `details.ia`.
- [X] T036 [US3] `apps/api/src/sociman_api/roteiros/guiado.py` `recusar(...)` e `aprovar_posicao(...)`; rotas `POST …/recusar`, `POST …/posicoes/{ordem}/aprovar` e `GET …/posicoes/{ordem}/quadros`; mapa do MCP e `gen:contract`.
- [X] T037 [US3] SPA `apps/web/src/pages/roteiros/wizard/`:
  - `NarracaoWizard.tsx`: só o áudio, "Aprovar" e "Não aprovo";
  - `QuadrosWizard.tsx`: a sequência da cena lado a lado, com o papel de cada quadro, aprovar a sequência e recusar um quadro;
  - `ClipesWizard.tsx`: um player por posição, aprovar e recusar um trecho;
  - `FinalWizard.tsx`;
  - `NaoAprovo.tsx`: abre o chat com o alvo, mostra opções de troca prontas (por exemplo "mais de lado", "manter o rosto", "mais animada") e o texto curto.

  Nada disso mostra texto de prompt ou de fala (FR-015).
- [X] T038 [US3] E2e "wizard" em `e2e/video-guiado.spec.ts`:
  - aprovar a narração;
  - recusar 1 quadro com uma opção pronta;
  - ver só aquele e os seguintes voltarem;
  - concluir o vídeo e ver o conteúdo sem destino;
  - varrer as telas do wizard confirmando que não aparece prompt nem texto de fala (SC-002).

**Checkpoint:** fluxo mínimo útil (com a US6 e o T045 já feitos): blocos → chat → wizard → vídeo.

---

## Phase 6: User Story 4 - Reuso de cenas transparente (P1)

**Objetivo:** modal com reuso `total`, reuso `plano` ou `nova` por posição, e a cena nova ou derivada indo para a biblioteca.

**Teste independente:** com 2 cenas que servem (1 total e 1 plano) e 1 posição sem cena, ver o modal certo. O total não gera nada, e o derivado aparece na biblioteca.

- [X] T039 [P] [US4] Teste `apps/api/tests/integration/test_reuso_niveis.py`:
  - classificação total e plano (avatar, cenário e variante iguais versus diferentes);
  - cena de outro produto fora da proposta, mas escolhível à mão com aviso;
  - reuso total = 0 gerações (SC-003);
  - reuso plano cria a derivada com `origem_cena_id` copiando ação, câmera, movimento, motor, trechos e instruções;
  - a cena reaproveitada não muda;
  - "quero cenas novas" no chat faz o plano propor `nova` em todas;
  - a cena nova fica na biblioteca depois da entrega (SC-008).
- [X] T040 [US4] `cenas_para_reuso` com nível em `apps/api/src/sociman_api/roteiros/aplicadores.py` (R7), e `derivar_cena(origem, avatar, cenario, variante, perfil_base)` em `apps/api/src/sociman_api/cenas/service.py`, com histórico nas duas cenas.
- [X] T041 [US4] `apps/api/src/sociman_api/roteiros/guiado.py` `definir_cena(...)`:
  - `total` confere a candidatura (senão 422 `reuso_invalido`);
  - `plano` cria a derivada;
  - `nova` pede o `roteiro.ajuste` com alvo `posicao`;
  - depois do texto, só no avançado (409 `etapa_errada`).

  Rota `PUT …/posicoes/{ordem}/cena`, mapa do MCP e `gen:contract`.
- [X] T042 [US4] SPA `apps/web/src/pages/roteiros/wizard/ModalCenas.tsx`:
  - por posição: miniatura, nome, onde já foi usada, o nível ("sem custo" ou "refaz as imagens") ou "criar nova", e o motivo;
  - trocar a decisão e escolher outra cena da biblioteca (`useCenasOpcoes`);
  - conversar sobre uma posição (`NaoAprovo` com alvo `posicao`);
  - "Confirmar cenas" aprova o portão texto.
- [X] T043 [US4] E2e "modal de cenas" em `e2e/video-guiado.spec.ts`: semear 1 cena total e 1 de outro avatar, conferir as propostas e trocar uma por "criar nova".

---

## Phase 7: User Story 5 - De 2 a 4 keyframes por cena (P2)

**Objetivo:** cenas de 2 e 3 trechos-base (3 e 4 quadros), com refação parcial.

**Teste independente:** uma cena de 4 quadros gera 3 trechos encadeados. Refazer o meio 1 refaz só os trechos 0→1 e 1→2.

- [X] T044 [P] [US5] Teste em `apps/api/tests/integration/test_quadros_cadeia.py`:
  - a cena de 3 trechos pede 4 quadros e 3 trechos com os pares certos (`start_image`/`end_image` no fake);
  - refazer o quadro 1 invalida os quadros 1 a 3 e os trechos 0, 1 e 2, mas o reaproveitamento por `tomada_serve_trecho` mantém os que não tocam quadro refeito;
  - um movimento que pede mais de 3 trechos é dividido em 2 posições pelo plano (`problemas()`).
- [X] T045 [US5] (**fazer junto com a Fase 2**, achado I4 do analyze) Máquina e pedidos (`roteiros/maquina.py`, `roteiros/pedidos.py`): `gerando_clipes` pede um clipe por trecho que não tem tomada que sirva, e a invalidação por quadro segue o FR-028.
- [X] T046 [US5] SPA: o `QuadrosWizard.tsx` mostra 2 a 4 quadros com os papéis (início, meio 1, meio 2, fim), e o `ClipesWizard.tsx` deixa recusar um trecho específico.

---

## Phase 8: User Story 6 - Grade de duração (P2)

**Objetivo:** duração exata, com a fala posta no slot de cada posição e o aviso quando não cabe.

**Teste independente:** escolher 20 s e receber exatamente 20 s ± 0,5 s, com cada bloco de fala dentro da sua cena.

- [X] T047 [P] [US6] Teste `apps/api/tests/unit/test_fala_no_slot.py` (puro, `roteiros/tempos.py`):
  - cortar a narração contínua pelos tempos das frases em blocos por posição;
  - o `adelay` = início do slot + 0,15;
  - `atempo` por bloco até a velocidade total 1,20;
  - acima disso, o aviso `fala_nao_cabe` com a ordem.
- [X] T048 [US6] `apps/api/src/sociman_api/roteiros/tempos.py` e `montagem.py`:
  - fala por slot no guiado (R4);
  - o vídeo exatamente `duracao_alvo_s`;
  - o −14 LUFS mantido;
  - o aviso gravado em `roteiros.avisos`.
- [X] T049 [US6] Teste de integração em `apps/api/tests/integration/test_video_guiado.py::test_duracao_exata`: o fluxo completo com fakes e `ffprobe` do resultado = alvo ± 0,5 s (SC-004); mudar `ROTEIRO_TRECHO_BASE_S` não mexe num roteiro existente (FR-033).
- [X] T050 [US6] SPA: o bloco de duração mostra as opções de `GET /api/roteiros/grade`. No wizard, o aviso `fala_nao_cabe` oferece "texto mais curto" (`recusar` com alvo `narracao`) ou "duração maior" (`PATCH` com `duracaoS`, que refaz o plano; FR-033).

---

## Phase 9: User Story 7 - Modo avançado (P3)

**Objetivo:** o switch preserva tudo, os roteiros da 011 abrem no avançado, e o avançado pede 2 ou mais versões.

**Teste independente:** trocar de modo no meio, editar um quadro no avançado e ver o efeito no wizard.

- [X] T051 [P] [US7] Teste `apps/api/tests/integration/test_video_guiado.py::test_avancado_*`: `regerar` de quadro com `nOpcoes = 2` (cadeia espera a escolha); `regerar` de clipe com `nOpcoes = 2` (2 tomadas, com a escolha pelo `PUT …/tomada` com `trecho`).
- [X] T052 [US7] Rotas aditivas (`keyframe/regerar` com `quadro`/`nOpcoes`, `clipe/regerar` com `trecho`/`nOpcoes`, `tomada` com `trecho`) em `apps/api/src/sociman_api/roteiros/router.py` e `service.py`, mais o `gen:contract`.
- [X] T053 [US7] SPA `apps/web/src/pages/roteiros/RoteiroDetalhe.tsx`:
  - switch "Wizard / Avançado" no topo, com `localStorage["sociman:roteiro:modo:<id>"]` (try/catch);
  - padrão wizard no guiado e avançado na 011, com o motivo explicado;
  - as etapas da 011 (`pages/roteiros/etapas/*`) ganham os quadros e os trechos;
  - no wizard, todos os portões ficam ligados, e o de texto é o modal de cenas (FR-035).
- [X] T054 [US7] Ajustar `e2e/roteiros.spec.ts` (cria pela API da 011, que está `deprecated`, e abre no avançado) e somar ao `e2e/video-guiado.spec.ts` o teste "avançado": trocar no meio sem perder aprovações (SC-007).

---

## Phase 10: Polish & Cross-Cutting

- [X] T055 [P] Limpeza e revogação:
  - os quadros arquivados e as tomadas de trecho sem uso entram na fase 2 da limpeza (`apps/api/src/sociman_api/geracao/limpeza.py` / `roteiros/retencao.py`), e o que está num vídeo entregue fica protegido;
  - revogação da 025 com quadro ou trecho novo → 409 `consentimento_revogado`;
  - a conversa fica fora da revogação (data-model). Testar que revogar não toca `roteiro_conversa`.

  Testes em `apps/api/tests/integration/test_video_guiado.py::test_limpeza_*`.
- [X] T056 [P] Guardas em `apps/api/tests/unit/test_constitution_guards.py`: `roteiros/` sem `publicacao`, todas as rotas novas no `mcp/mapa.py` (o `test_mcp_mapa.py` passa), e nenhum endereço de rede no código novo.
- [X] T057 [P] Docs:
  - seção "Vídeo guiado (desde a spec 031)" no `CLAUDE.md` do SociMan;
  - `docs/visao.md` com a 031 ✅;
  - `docs/insumos/031-video-guiado.md` apontando para a spec.
- [X] T058 Verificação final:
  - `npm run test:api` (inteiro), `docker compose exec api uv run ruff check .`, `npm run gen:contract && npm run check:web` e `flock /tmp/sociman-e2e.lock npm run test:e2e` (inteiro);
  - backup `pre-0028.dump`, `alembic upgrade head` no dev e `docker compose restart api gerador agendador`.
- [ ] T059 Com o dono: quickstart §2 (primeiro vídeo real de 20 s) e §3 (medições de 5 s × 8 s, emenda, deriva de identidade, SC-006), mais o tempo do "Novo vídeo" até o plano montado (SC-001, ≤ 5 min). Registrar os resultados no `research.md`.
  - 2026-10-15: §2 feito (15 s, 3 cenas; research R13, com as 5 decisões do dono já no código). Falta o §3 (5 s × 8 s, emenda de 3 trechos, SC-006).

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → **Foundational (T003–T015)** → histórias.
- **US1 → US2 → US3** em sequência:
  - US2 precisa do roteiro guiado da US1;
  - US3 precisa do plano da US2.
- **US4** depende da US2 (o plano v2 propõe o reuso) e pode correr em paralelo com a US3 (arquivos diferentes, salvo `aplicadores.py`: coordenar).
- **US5** depende da US3 (cadeia e aprovação por posição).
- **US6** depende só do Foundational e da US2 (tempos e montagem). Faz parte do MVP e roda em paralelo com a US3.
- **US7** depende da US3.
- **Polish** por último.

## Parallel Example

```text
Frente A (API núcleo): T003 → T005 → T008 → T009 → T010 → T012 → T013
Frente B (puros e fakes): T006, T007, T014, T015
Depois do Foundational:
  Frente C (US1 API): T016–T019   |   Frente D (US1 SPA): T020–T021 (depois do T018 por causa do contrato)
  Frente E (US6): T047–T048      |   Frente F (US4 API): T039–T041 (depois do T027)
```

Arquivos compartilhados que **não** podem ter dois agentes ao mesmo tempo:
- `roteiros/aplicadores.py`, `roteiros/maquina.py`, `roteiros/router.py` e `schemas.py`;
- `ia/tipos.py`;
- o `gen:contract` (serializado).

## Implementation Strategy

1. **MVP = Foundational (com o T045) + US1 + US2 + US6 + US3**. Já entrega blocos → chat → wizard → vídeo de duração exata, com a fala no tempo de cada cena. Validar com o dono (quickstart §2) antes de seguir.
2. **+ US4** (reuso transparente, menos GPU).
3. **+ US6** (fala no slot, aviso) e **US5** (3 e 4 quadros). Medir 5 s × 8 s e a emenda (quickstart §3).
4. **+ US7** (avançado com várias versões) e o Polish.
