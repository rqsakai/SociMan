---

description: "Tarefas da feature 010-cenas"
---

# Tasks: Cenas para o Flow/Veo (010-cenas)

**Input**: `specs/010-cenas/` (spec com Clarifications 2026-10-06, plan, research R1–R12, data-model,
contracts/http-api.md, quickstart)

**Pré-requisito:** a 009 (MCP) está implementada na API, com `anotacoes/` e `mcp/mapa.py` estáveis e verdes.
A 010 mexe em `anotacoes/` (models, schemas, service), `mcp/mapa.py`, `ia/` (tipos, regras, contexto,
aplicação, saída), `assets/usos.py` (só o registro) e `conteudos/` (leitura). Nenhum outro agente pode
editar esses arquivos ao mesmo tempo.

**Decisões do dono (2026-10-06):**
- **Q1 = A:** a proposta de cena é uma anotação `proposta_cena` da 009, com alvo perfil ou cena. O humano
  aceita pelo formulário, e o agente não cria entidade de domínio.
- **Q2 = A:** tomadas na cena (várias, uma escolhida, cada uma com o prompt usado) e vínculo com o
  conteúdo vídeo próprio da 014, que define `usada`.
- **Q3 = A:** o prompt é ao vivo em `rascunho` e congelado em `pronta`/`usada`, com aviso "mudou" e
  "Remontar".

**Nomes canônicos:**
- **API:** pacote `sociman_api/cenas/` (`models`, `prompt`, `avisos`, `ingredientes`, `service`, `padroes`,
  `tomadas`, `usos`, `usos_assets`, `schemas`, `router_perfil`, `router`).
  - `operationId`s `cenas_*` e `conteudos_cenas_*`.
  - Tabelas `cenas`, `cena_tomadas`, `cena_usos` e `cena_padroes`.
  - `entity_type`s `cena`, `cena_tomada` e `cena_padroes`.
  - Migration **`0015_cenas`** (`down_revision = "0014_mcp"`). A 013 usará a 0016 apontando para esta.
- **SPA:**
  - `pages/perfis/tabs/CenasTab.tsx` (`?aba=cenas`);
  - `pages/cenas/CenaDetalhe.tsx` (`/app/cenas/:id`, e `/app/perfis/:id/cenas/nova` para a cena
    nova);
  - `pages/cenas/CenaHistorico.tsx`;
  - `components/cenas/*` e `lib/cenas.ts`.
- **Testes:** `tests/integration/cenas_helpers.py` (avatar Achadinhos, cenário e produto sintéticos;
  MP4 sintético via ffmpeg `testsrc`) e `e2e/cenas.spec.ts`.

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera: `npm run test:api [-- args]`;
- `docker compose exec -T api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/cenas.spec.ts]`.

Nada chama serviço real: nem Flow/Veo, nem Claude real, nem OpenClaw.

**Arquivos compartilhados, SÓ ACRÉSCIMO:**
- `apps/api/src/sociman_api/main.py`;
- `apps/web/src/App.tsx`;
- `apps/api/tests/unit/test_constitution_guards.py`;
- `docker/nginx/default.conf.template`;
- `e2e/helpers.ts`;
- `CLAUDE.md`;
- `docs/visao.md`.

`packages/contract/**` é gerado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US5 da spec

---

## Phase 1: Setup

- [X] T001 **Gate:**
  - `ls apps/api/migrations/versions/` mostra **0014_mcp** como a última e nenhum `0015_*`. Se já houver
    um `0015_*`, pare e avise o líder;
  - `docker compose exec api uv run alembic heads` mostra só `0014_mcp`;
  - os testes da 009 estão verdes: `npm run test:api -- tests/ -k "mcp or anotacoes" -q`;
  - `git status` só tem o esperado;
  - `.specify/feature.json` aponta para a 010 (o líder cuida).
- [X] T002 [P] `docker/nginx/default.conf.template` (acréscimo): `location ~ ^/api/cenas/[^/]+/tomadas$`,
  com `client_max_body_size 210m`, `proxy_request_buffering off` e os mesmos headers da location do vídeo
  próprio. Rode `docker compose restart edge` (armadilha 13). Confira com um `curl` de 9 MB, que **não**
  deve receber 413 do edge.

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** banco, modelos, montagem pura do prompt e avisos, padrões do perfil, classificação no mapa
do MCP e helpers.

- [X] T003 Migration `apps/api/migrations/versions/0015_cenas.py` (`revision = "0015_cenas"`,
  `down_revision = "0014_mcp"`), na ordem do data-model:
  - os 5 enums (incluindo `tomada_origem` = `flow_manual`, ponto de extensão da 021);
  - as tabelas `cena_padroes`, `cenas`, `cena_tomadas` (com FK deferível de
    `cenas.tomada_escolhida_id`) e `cena_usos`;
  - os CHECKs `ck_cenas_duracao`, `ck_cenas_congelado` e `ck_cenas_produto`;
  - os índices, incluindo o único parcial de `cena_usos`;
  - os `ALTER TYPE anotacao_alvo/anotacao_tipo ADD VALUE` em `autocommit_block`;
  - a troca de `ck_anotacoes_proposta_em_destino` por `ck_anotacoes_proposta_alvo`;
  - o downgrade, que recusa se houver dados novos nas anotações.
- [X] T004 `apps/api/src/sociman_api/cenas/models.py`: `Cena`, `CenaTomada`, `CenaUso` e `CenaPadroes`,
  com enums, `__versioned_fields__`/`__immutable_fields__` e a constante `CAMPOS_PROMPT`. Também
  `apps/api/src/sociman_api/anotacoes/models.py` (`AnotacaoAlvo.cena`, `AnotacaoTipo.proposta_cena` e o
  CHECK novo). Depende de T003.
- [X] T005 [P] `apps/api/tests/integration/test_migration_0015.py`:
  - upgrade e downgrade num banco limpo;
  - os CHECKs recusam duração 5, congelado em rascunho e foto sem nome de produto;
  - o único parcial de `cena_usos`;
  - o CHECK das anotações aceita `proposta_cena` em perfil/cena e recusa em destino;
  - o downgrade recusa quando existe `proposta_cena`.
- [X] T006 [P] `apps/api/src/sociman_api/cenas/prompt.py`:
  - `montar(entrada) -> PromptMontado`, pura (research R2);
  - as tabelas fixas de plano e movimento em inglês;
  - a fala em pt-BR entre aspas com verbo de fala;
  - "exactly as in the reference image" com foto de produto;
  - `Start frame`/`End frame` no modo `quadros`;
  - o negative da cena ou o padrão.
- [X] T007 [P] `apps/api/tests/unit/test_cenas_prompt.py` (SC-002):
  - a descrição do avatar sai idêntica, byte a byte, inclusive com espaços e quebras finais;
  - a ordem das partes;
  - funciona sem avatar, sem cenário e sem produto;
  - o modo quadros;
  - o padrão do perfil é usado quando o estilo está vazio;
  - o texto na tela nunca entra;
  - o exemplo de referência do shop-diretor (Achadinhos, Cozinha retrô e a fala "Gente, olha essa
    panela!") bate com o texto esperado (SC-003).
- [X] T008 [P] `apps/api/src/sociman_api/cenas/avisos.py`, função pura (research R4), com os avisos
  `fala_longa` (proporcional à duração), `duracao_modo`, `produto_sem_foto`, `proibida` (usa
  `ia.guia.achar_proibidas`), `assets_mudaram` (com antes/depois da parte) e `asset_arquivado`.
- [X] T009 [P] `apps/api/tests/unit/test_cenas_avisos.py`: cada aviso com borda, como 15 palavras em 8 s,
  8 palavras em 4 s, proibida com acento e caixa, e as versões iguais e diferentes.
- [X] T010 `apps/api/src/sociman_api/cenas/schemas.py`:
  - `CenaIn`, `CenaPatch`, `Cena`, `CenaResumo`, `PromptOut`, `Ingrediente`, `Aviso`, `Tomada`,
    `CenaPadroes` e `CamposCena` (subconjunto de `CenaIn` para a proposta), todos com
    `extra="forbid"` na entrada;
  - os limites do data-model.

  Depende de T004.
- [X] T011 `apps/api/src/sociman_api/cenas/padroes.py` e as rotas `cenas_padroes_get`/`_put`/`_revert` em
  `cenas/router_perfil.py`:
  - sem linha, devolve `version 0` com o padrão do código;
  - o `PUT` cria ou atualiza com histórico (`cena_padroes`);
  - o revert é **H**.

  Também o `include_router` em `main.py` (acréscimo). Depende de T010.
- [X] T012 `apps/api/src/sociman_api/mcp/mapa.py`: classificar **todas** as operações novas (research
  R11), deixando o `test_mcp_mapa.py` verde:
  - leituras em `TOOLS` com descrições em pt-BR (`ocultar` o `videoUrl` das tomadas);
  - escritas em `FORA`;
  - os reverts em `PROIBIDAS`.

  Repita a cada fase que criar rota (T017, T019, T024, T032, T036).
- [X] T013 [P] `apps/api/tests/integration/cenas_helpers.py`:
  - o perfil com o avatar "Achadinhos" (descrição de `persona.md`, um look e uma pose), o cenário
    "Cozinha retrô", a imagem de produto e o guia com a proibida "milagre";
  - `mp4_sintetico(segundos, largura, altura)` via ffmpeg `testsrc`, em `tmp_path`;
  - `cena_pronta(...)`.

**Checkpoint:** a migration aplica e reverte, e prompt e avisos estão cobertos por testes unitários.

---

## Phase 3: User Story 1 - Montar a cena e copiar o prompt (Priority: P1) 🎯 MVP

**Objetivo:** criar e editar a cena, com o prompt ao vivo e os ingredientes.
**Teste independente:** o quickstart §2.

### Testes (US1)

- [X] T014 [P] [US1] `apps/api/tests/integration/test_cenas.py` (criar e ler):
  - criar com todos os campos → 201, `rascunho`, prompt ao vivo com as partes;
  - avatar, cenário ou foto de **outro perfil** → 422;
  - arquivo de look que não é do avatar → 422;
  - ingredientes na ordem avatar → produto → cenário, com `downloadUrl`;
  - avisos presentes no `GET`;
  - histórico `created`;
  - conflito de versão no `PATCH`.

### Implementação (US1)

- [X] T015 [US1] `apps/api/src/sociman_api/cenas/ingredientes.py` (research R3): resolve o arquivo do
  avatar (o escolhido ou o principal), a foto do produto e a imagem do cenário, com os links de mídia
  `imagem` da 007.
- [X] T016 [US1] `apps/api/src/sociman_api/cenas/service.py`:
  - `criar`: valida a posse dos assets no perfil e grava o histórico;
  - `obter`: monta o prompt ao vivo ou devolve o congelado, mais os ingredientes, os avisos (com as
    proibidas do guia efetivo do perfil) e os resumos de avatar, cenário e produto;
  - um "Padrões" ausente usa o padrão do código (T011);
  - `editar`: `check_version`, snapshot e `record`.
- [X] T017 [US1] Em `cenas/router_perfil.py` e `cenas/router.py`: `cenas_create`, `cenas_get` e
  `cenas_update`.
- [X] T018 [US1] `npm run gen:contract`; `apps/web/src/lib/cenas.ts` (hooks TanStack Query) e
  `apps/web/src/components/cenas/`:
  - `CenaForm`, com `NativeSelect` para avatar, look/pose, cenário, plano, movimento, modo e duração,
    usando os seletores da biblioteca (`LibraryImageDialog`) para a foto do produto;
  - `PromptPainel`, com as partes destacadas, o selo "ao vivo"/"congelado" e os `CopyButton`
    "Copiar prompt" e "Copiar negative prompt";
  - `Ingredientes`, com miniatura e "Baixar";
  - `Avisos`.
- [X] T019 [US1] `apps/web/src/pages/cenas/CenaDetalhe.tsx` e as rotas em `App.tsx` (acréscimo):
  `/app/cenas/:id` e `/app/perfis/:id/cenas/nova`. Use `usePageMeta` e `HeaderCard`, e repita a
  classificação do T012 para as rotas novas.
- [X] T020 [US1] `e2e/cenas.spec.ts` (US1):
  - semear o avatar, o cenário e o produto pela API;
  - criar a cena pela tela;
  - conferir que o texto do prompt começa com a descrição do avatar;
  - "Copiar prompt" (leitura do clipboard com permissão do Playwright);
  - 3 ingredientes;
  - aviso de fala longa.

**Checkpoint:** o MVP permite montar e copiar o prompt.

---

## Phase 4: User Story 2 - Biblioteca, status e reaproveitamento (Priority: P1)

**Objetivo:** lista com filtros, status com congelamento (Q3), duplicar, arquivar e reverter.
**Teste independente:** o quickstart §3.

### Testes (US2)

- [X] T021 [P] [US2] `apps/api/tests/integration/test_cenas_prompt_congelado.py` (Q3, FR-006a):
  - `pronta` congela o texto e as versões;
  - mudar o avatar mantém o congelado e mostra `assets_mudaram` com antes/depois;
  - `remontar` regrava o congelado sem mudar o status, com `details.acao = "remontar"`;
  - editar um campo de `CAMPOS_PROMPT` em `pronta` volta a `rascunho` e limpa o congelado;
  - editar nome, tags ou notas mantém `pronta`;
  - `pronta` incompleta → 422 `cena_incompleta` com `faltando`;
  - avatar arquivado impede `pronta`;
  - `rascunho` explícito.
- [X] T022 [P] [US2] Em `apps/api/tests/integration/test_cenas.py` (lista e ciclo):
  - os filtros (status, avatar, cenário, foto do produto, tag e busca sem acento em nome, ação, fala e
    produto);
  - a paginação por cursor;
  - `duplicar`: rascunho, "(cópia)", sem tomadas e usos, com `duplicada_de` no histórico;
  - arquivar e restaurar;
  - revert pelo dono volta o prompt congelado;
  - revert por membro → 403 `somente_dono`;
  - revert em cena `usada` → 409 `cena_usada`;
  - SC-006: 200 cenas, lista filtrada < 500 ms.

### Implementação (US2)

- [X] T023 [US2] `apps/api/src/sociman_api/cenas/service.py`:
  - `listar` (filtros e cursor);
  - `marcar_pronta`, `voltar_rascunho` e `remontar` (research R5);
  - a regra de `CAMPOS_PROMPT` no `editar`;
  - `duplicar`, `arquivar`, `restaurar` e `reverter` (só o dono; recusado em `usada`; um snapshot
    `usada` sem vínculo ativo volta como `pronta`, research R5).
- [X] T024 [US2] Rotas `cenas_list`, `cenas_duplicar`, `cenas_pronta`, `cenas_rascunho`,
  `cenas_remontar`, `cenas_archive`, `cenas_restore`, `cenas_versions` e `cenas_revert` (**H**; recusa
  em `usada`, research R5).
  Classifique-as no mapa (T012).
- [X] T025 [US2] `apps/api/src/sociman_api/cenas/usos_assets.py`: provedor `cena` em
  `assets.usos.register` (`bloqueia = False`, "N cenas", link para a aba filtrada). Teste em
  `test_cenas.py`: o avatar mostra o uso e arquivar o avatar continua permitido (FR-009).
- [X] T026 [US2] `npm run gen:contract`. Na SPA:
  - `apps/web/src/pages/perfis/tabs/CenasTab.tsx`, com `DataTable` (`dataTableColumns`), filtros,
    busca, "Nova cena", "Duplicar" e "Arquivadas";
  - a aba "Cenas" em `PerfilDetalhe.tsx` (`?aba=cenas`);
  - no `CenaDetalhe`, os botões de status, o aviso "mudou" com a diferença (`AvisoMudou`) e
    "Remontar prompt";
  - `CenaHistorico.tsx` (`VersionHistory`), com a rota `/app/cenas/:id/historico`;
  - o painel "Padrões das cenas" (estilo e negative) na aba.
- [X] T027 [US2] `e2e/cenas.spec.ts` (US2):
  - filtrar, duplicar e arquivar;
  - pronta → editar o avatar pela API → aviso → Remontar;
  - editar a ação → rascunho;
  - o membro não vê "Reverter".

**Checkpoint:** US1 e US2 completam a biblioteca de cenas utilizável.

---

## Phase 5: User Story 3 - Tomadas e vínculo com o vídeo final (Priority: P2)

**Objetivo:** enviar e escolher tomadas, e ligar as cenas ao vídeo próprio (Q2).
**Teste independente:** o quickstart §4.

### Testes (US3)

- [X] T028 [P] [US3] `apps/api/tests/integration/test_cenas_tomadas.py`:
  - enviar 8 s em 9:16 → 201, com miniatura, `origem = flow_manual`, `promptUsado` igual ao
    congelado e a 1ª tomada como escolhida;
  - 16:9 → `naoVertical`;
  - 0,5 s, 31 s e um arquivo que não é vídeo → recusa sem gravar nada;
  - cena em `rascunho` → 409 `cena_nao_pronta`;
  - escolher outra tomada;
  - arquivar a escolhida limpa a escolha;
  - remontar depois do envio não muda o `promptUsado`;
  - HD sem sentinela → 503;
  - abaixo do piso → 507;
  - o link de vídeo tem validade e aceita Range.
- [X] T029 [P] [US3] `apps/api/tests/integration/test_cenas_usos.py`:
  - `PUT /api/conteudos/{id}/cenas` com duas cenas `pronta` → as duas viram `usada`, com histórico nas
    cenas e no conteúdo;
  - tirar uma → ela volta a `pronta`;
  - conteúdo de origem `corte` → 422 `origem_invalida`;
  - cena em rascunho, de outro perfil ou arquivada → 422;
  - conflito de versão do conteúdo;
  - editar um campo de `CAMPOS_PROMPT` numa cena `usada` → 409 `cena_usada`;
  - o revert do conteúdo não mexe nos usos;
  - o `conteudos_get` traz `cenas`.

### Implementação (US3)

- [X] T030 [US3] `apps/api/src/sociman_api/cenas/tomadas.py` (research R6):
  - reaproveita `cortes.service.precheck`/`receive` (prefixo `tomada-`, 200 MB), `probe` e a miniatura
    de `conteudos/video_proprio.py`;
  - separa `registrar_tomada(cena, arquivo, origem)` do transporte HTTP, com `origem = flow_manual` na
    rota de envio (a 021 vai reaproveitar essa função; nada da 021 é implementado aqui);
  - grava o vídeo em `cenas/<id>/tomadas/<tomada>.<ext>`;
  - `escolher`, `editar_nota`, `arquivar`, `restaurar` e `reverter` (**H**).
- [X] T031 [US3] `apps/api/src/sociman_api/cenas/usos.py` (research R7): define o conjunto, recalcula
  `usada`/`pronta` e grava o histórico nos dois lados. Em `conteudos/consulta.py` e
  `conteudos/schemas.py`, acrescente `cenas` ao detalhe (só leitura).
- [X] T032 [US3] Rotas `cenas_tomadas_*` e `conteudos_cenas_get`/`_put`, com a classificação no mapa
  (T012).
- [X] T033 [US3] `npm run gen:contract`. Na SPA:
  - `components/cenas/Tomadas.tsx`: envio com progresso (o mesmo componente de envio do vídeo próprio),
    player, "prompt usado" num colapsável, "Escolher", nota e arquivar;
  - no `CenaDetalhe`, o bloco "Usada em";
  - `components/cenas/SeletorCenas.tsx` no `ConteudoDetalhe.tsx`, só para vídeo próprio: as cenas
    `pronta`/`usada` do perfil, com busca.
- [X] T034 [US3] `e2e/cenas.spec.ts` (US3):
  - enviar uma tomada sintética e escolher;
  - enviar um vídeo próprio sintético;
  - ligar a cena → `usada`;
  - editar a ação → a mensagem "duplique";
  - desligar → `pronta`.

---

## Phase 6: User Story 4 - IA na cena (Priority: P2)

**Objetivo:** "Melhorar com IA" nos 4 campos e "Ajustar cena com IA" (research R10).
**Teste independente:** o quickstart §5.1–5.2, com o Claude falso.

- [X] T035 [P] [US4] `apps/api/tests/unit/test_ia_tipos.py` (acréscimo): os 5 tipos `cena.*` com os limites
  iguais aos de `CenaPatch`, `usa_guia = "so_proibidas"` e formato `campos_cena` só em `cena.ajustar`.
- [X] T036 [US4] `apps/api/src/sociman_api/ia/`:
  - `tipos.py`: entidade `cena`, os 5 tipos e o formato `campos_cena`;
  - `regras_padrao.py`: as regras do shop-diretor;
  - `contexto.py`: avatar, regras de imagem, cenário, produto, duração, modo e fala, vindos da cena
    salva ou de `cenaContexto` com a posse conferida;
  - `schemas.py`: `AlvoTipo` mais `cena`, `Valor.cena` e `GerarIn.cenaContexto`;
  - `saida.py`: valida `campos_cena` e descarta chaves fora das 4;
  - `aplicacao.py`: marca `details.ia` no `PATCH`/`POST` da cena.

  Rode `npm run gen:contract`. As rotas da IA já estão classificadas no mapa: confira com o T012.
- [X] T037 [P] [US4] `apps/api/tests/integration/test_cenas_ia.py` (Claude falso):
  - gerar `cena.acao` → proposta e explicação;
  - aplicar pelo `PATCH` com `ia` → histórico com `details.ia` e autor humano;
  - `cena.ajustar` → só as 4 chaves, e o prompt montado mantém a descrição do avatar idêntica;
  - o pedido leva só `<guia_perfil parte="proibidas">`;
  - uma proposta com proibida sai marcada, e salvar o valor igual à proposta → 400 `ia_proibida`;
  - cena nova (`entityId` nulo) com `cenaContexto` de outro perfil → 422.
- [X] T038 [US4] Na SPA: `IaBotao`/`IaAssist` nos campos ação, câmera, estilo e áudio do `CenaForm`, e o
  botão "Ajustar cena com IA", com prévia por campo (`IaDiff`) e "Aplicar".
- [X] T039 [US4] `e2e/cenas.spec.ts` (US4) com o Claude falso:
  - melhorar a ação e aplicar → o selo "com ajuda da IA" no histórico;
  - ajustar a cena → o prompt ainda começa com a descrição do avatar.

---

## Phase 7: User Story 5 - O shop-diretor propõe cenas pelo MCP (Priority: P3)

**Objetivo:** a anotação `proposta_cena` (Q1), com o aceitar humano.
**Teste independente:** o quickstart §5.3–5.5.

- [X] T040 [US5] `apps/api/src/sociman_api/anotacoes/`:
  - `schemas.py`: `CamposCena` e `campos` como união discriminada pelo `tipo`;
  - `service.py`:
    - alvo `cena` em `_MODELOS`/`_NOMES`, com link `/app/cenas/{id}`;
    - validação de `proposta_cena` (alvo perfil ou cena; cena não arquivada nem `usada`; assets do
      perfil);
    - `aplicar_cena(db, actor, proposta_id, cena_id | perfil_id)`.

  Em `cenas/service.py`, `criar`/`editar` aceitam `propostaId`, chamam `aplicar_cena` na mesma transação
  e gravam a referência no histórico da cena.
- [X] T041 [P] [US5] `apps/api/tests/integration/test_cenas_mcp.py` (SC-004):
  - um cliente "leitura e propostas" grava `proposta_cena` no perfil → aparece na caixa com o autor
    `mcp_client`;
  - o dono cria a cena com `propostaId` → cena em rascunho, autor humano, proposta `aplicada`;
  - uma proposta numa cena existente, ao ser aplicada pelo `PATCH`, altera só os campos propostos;
  - alvo destino → 422;
  - asset de outro perfil → 422;
  - cena `usada` → 409;
  - o cliente MCP chama **cada** operação `cenas_*` e `conteudos_cenas_put` de escrita pelo nome →
    recusa `escopo_mcp`; os reverts → `somente_humano` mais o evento;
  - o cliente "só leitura" lê `cenas_list`/`cenas_get` sem `videoUrl`;
  - a proposta conta no limite diário de escritas.
- [X] T042 [US5] Na SPA:
  - `components/anotacoes/PropostaCard.tsx` e `pages/propostas/Propostas.tsx` (acréscimo): o tipo
    `proposta_cena` mostra os campos, e "Aceitar" navega para `/app/perfis/:id/cenas/nova?proposta=<id>`
    ou para `/app/cenas/:id?proposta=<id>`;
  - o `CenaForm` preenche a partir da proposta, sem salvar, com a faixa "Proposta de <agente>";
  - `AnotacoesDoItem` no `CenaDetalhe`.
- [X] T043 [US5] Em `mcp/mapa.py`, a descrição de `anotacoes_create` explica o formato de `proposta_cena`.
  Em `docs/guia-mcp-openclaw.md` (acréscimo), uma seção "Propor cenas (shop-diretor)" com um exemplo
  de chamada.
- [X] T044 [US5] `e2e/cenas.spec.ts` (US5): a proposta é gravada pelo cliente MCP de teste (helper da
  009) → aparece na caixa → Aceitar → Salvar → a cena aparece na aba, e a proposta fica `aplicada`.

---

## Phase 8: Polish & Cross-Cutting

- [X] T045 [P] `apps/api/tests/integration/test_cenas_permissoes.py`:
  - o membro cria, edita, marca pronta, envia tomada e liga ao conteúdo;
  - o membro tenta os 3 reverts → 403 `somente_dono`;
  - `system:*` e o token de agente → 403 `somente_humano` mais o evento `publicacao_recusada` nos 3
    reverts.
- [X] T046 [P] `apps/api/tests/unit/test_constitution_guards.py` (acréscimo):
  - `cenas/` não importa `publicacao`, `httpx` nem cliente de rede;
  - não há "tiktok"/"youtube" nas rotas nem nos `operationId` `cenas_*`;
  - os reverts de cena dependem de `require_human_owner`;
  - toda mutação em `cenas/service.py`, `tomadas.py`, `usos.py` e `padroes.py` chama `history.record`
    (varredura como nas specs anteriores).
- [X] T047 [P] Teste de desempenho:
  - `cenas_list` com 200 cenas e filtros < 500 ms;
  - `cenas_get` com prompt, ingredientes e avisos < 200 ms.
- [X] T048 Documentação (acréscimo):
  - `CLAUDE.md`: a seção "Cenas (desde a spec 010)", com o pacote, as rotas, o congelamento, as
    tomadas no HD com a location do edge, o vínculo com o vídeo próprio, os tipos de IA `cena.*` e a
    `proposta_cena` do MCP;
  - `docs/visao.md`: o item 010 no backlog, com a nota "cena = tomada; ambiente = cenário da 007";
  - `../shared/shop/README.md` **não** é alterado (é do gestor/dono). Anote a sugestão no relatório.
- [X] T049 Verificação final:
  - `npm run test:api` inteiro, ruff e `npm run gen:contract && npm run check:web`;
  - a suíte e2e inteira (com trava);
  - o quickstart §1–§3 e §5.1–5.2 no dev.

  O §4.1 (Flow real) e o §5.3 (OpenClaw real) são **com o dono**, à mão; registre o resultado. **Commit
  só quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate) → T002.
- **Phase 2** bloqueia tudo:
  - T003 → T004 → T005/T010;
  - T006, T008 e T013 em paralelo com T003; T007 depois de T006 e T009 depois de T008;
  - T010 → T011;
  - T012 depois de T011 e de novo a cada fase com rotas.
- **US1 (Phase 3)** → **US2 (Phase 4)**: o T023 estende o `service.py` do T016.
- **US3 (Phase 5)** depois da US2, porque precisa de `pronta` e do congelamento.
- **US4 (Phase 6)** depois da US1 e pode correr em paralelo com a US2 e a US3, mas é dona de `ia/`.
- **US5 (Phase 7)** depois da US1 (`criar` e `editar`). O caso "cena `usada` → 409" do T041 depende da
  US3; se ela ainda não estiver pronta, esse caso fica para o fim.
- O `gen:contract` é serializado (T018, T026, T033, T036 e T042). Os e2e são serializados pela trava.
- **Phase 8** fica no fim.

### Paralelismo sugerido (agentes)

- **Frente A (API, núcleo):** T003–T004, T010–T012, T015–T017, T023–T025, T030–T032, T040.
- **Frente B (testes):** T005, T007, T009, T013, T014, T021, T022, T028, T029, T037, T041, T045–T047.
- **Frente C (IA):** T035–T036 (dona de `ia/`).
- **Frente D (SPA e e2e):** T018–T020, T026–T027, T033–T034, T038–T039, T042, T044.

## Implementation Strategy

O MVP é a US1 (montar e copiar o prompt), que já substitui o pacote em markdown do shop-diretor para uma
cena. A US2 torna a biblioteca reaproveitável e fecha a Q3. A US3 fecha o ciclo com as tomadas e o vídeo
final (Q2). A US4 e a US5 aceleram o trabalho com a IA e com o agente.

Checkpoints: depois da Phase 2, da US1, da US2, da US3 e no fim.
