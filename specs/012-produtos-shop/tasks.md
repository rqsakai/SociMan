---

description: "Tarefas da feature 012-produtos-shop"
---

# Tasks: Produtos do TikTok Shop (012-produtos-shop)

**Input:** `specs/012-produtos-shop/`, com:
- a spec, com as Clarifications de 2026-10-06;
- o plan;
- a research R1–R19;
- o data-model;
- o `contracts/api.md`;
- o quickstart.

**Pré-requisitos:**
- a **021-geracao-local** implementada e verde, com:
  - a constitution 4.3.0 aplicada;
  - `0020_geracao_local` no head;
  - o protocolo `Aplicador` com `ao_mudar_estado`;
  - `fila.abertas_do_alvo`;
  - o registro de `uso.py`;
  - os fakes `comfyui_fake`/`dockerctl_fake` e os componentes `components/geracao/`;
- a 025 **não** é pré-requisito: no gate de 2026-10-08 o head era `0021_geracao_interrupcoes` (da 021),
  e a 012 entra antes da 025 (que passa a ser a `0023`).

A 012 mexe em:
- `cenas/models.py`, `cenas/service.py`, `cenas/prompt.py`, `cenas/ingredientes.py`, `cenas/avisos.py`
  e `cenas/schemas.py`;
- `anotacoes/models.py` e `anotacoes/service.py`;
- `ia/tipos.py`, `mcp/mapa.py`, `imaging.py` e `perfis/models.py`;
- `geracao/passos.py` e `geracao/router.py`, só nos pontos de registro.

Nenhum outro agente pode estar editando esses arquivos ao mesmo tempo.

**Decisões do dono (2026-10-06):**
- **FR-021:** aprovar é de dono e membro;
- **FR-029:** só o `url_loja`, opcional e informativo;
- **FR-025:** sem a marcação "produto deitado" na cena.

**Nomes canônicos:**
- **API:** pacote `sociman_api/produtos/`, com `models`, `estados`, `ficha`, `flat`, `aplicadores`,
  `fluxo`, `service`, `usos`, `uso`, `schemas`, `router` e `router_perfil`;
- **rotas e `operationId`:** os de `contracts/api.md` (`produtos_*`);
- **tabelas:** `produtos` e `produto_variantes`;
- **enums:** `produto_status` (`rascunho`, `gerando`, `revisao`, `aprovado`) e `produto_ficha_por`.
  Ganham o valor `produto`: `image_kind` e `anotacao_alvo`;
- **passos da 021:** `produto.ficha` (motor `claude`), `produto.recorte` (`cutout`, sem escolha) e
  `produto.flat` (`keyframe`, 2 opções, humano);
- **histórico:** `entity_type = "produto"`;
- **SPA:**
  - aba `?aba=produtos` (`pages/perfis/tabs/ProdutosTab.tsx`);
  - `/app/produtos/:id` (`pages/produtos/ProdutoPage.tsx`);
  - `lib/produtos.ts`.

`packages/contract/**` é gerado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US6 da spec

---

## Phase 1: Setup

- [X] T001 **Gate:**
  - `ls apps/api/migrations/versions/` e `docker compose exec api uv run alembic heads` mostram
    **`0021_cadastro_padronizado`** como único head, com `0020_geracao_local` antes dele;
  - se a 025 ainda não entrou (o head é `0020_geracao_local`), a migration da 012 vira `0021_produtos_shop`
    com `down_revision = "0020_geracao_local"`. Avise o líder e corrija data-model, plan e T003 antes de
    seguir. Com qualquer outro head, pare;
  - `.specify/memory/constitution.md` está na **4.3.0**, com as "Exceções de eliminação" no princípio VII;
  - os testes da 021, da 010 e da 008 estão verdes:
    `npm run test:api -- -k "geracao or cenas or ia_" -q`;
  - `geracao/aplicadores.py` tem o protocolo com `ao_mudar_estado`, e `geracao/uso.py` aceita provedores;
  - o serviço de pedido da 021 delega a validação de `referencias` ao `montar_params` do aplicador (as fotos,
    recortes e flats do produto **não** estão em `asset_files`). Se a validação de "imagem em arquivo ativo
    de asset ativo" estiver fixa no serviço, e não só na rota genérica, pare e combine com o líder;
  - `git status` só tem o esperado.
- [X] T002 [P] `docker/nginx/default.conf.template`: `location ~
  ^/api/(perfis/[^/]+/produtos|produtos/[^/]+/variantes)$` com `client_max_body_size 130m` e o mesmo bloco
  de proxy das rotas de upload da 007 (R12). Depois, `docker compose restart edge` (armadilha 13).

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** banco, modelos, enums, imagem `produto`, funções puras e fakes.

- [X] T003 Migration `apps/api/migrations/versions/0022_produtos_shop.py` (`revision =
  "0022_produtos_shop"`, `down_revision = "0021_geracao_interrupcoes"`, conferido na T001), conforme o
  data-model:
  - os valores `produto` em `image_kind` e `anotacao_alvo` (em `autocommit_block`);
  - `produto_status` e `produto_ficha_por`;
  - as tabelas `produtos` e `produto_variantes`, com CHECKs e índices;
  - as 2 colunas, os 2 CHECKs e o índice em `cenas`;
  - o downgrade com recusa quando há dados.
- [X] T004 [P] `tests/integration/test_migration_0022.py`:
  - sobe sobre o head anterior com cenas existentes, que ficam com as colunas novas NULL;
  - cada CHECK recusa com `INSERT` direto (`ck_variantes_flat`, `ck_cenas_produto_modo`,
    `ck_cenas_produto_variante`, `ck_produtos_aprovado`);
  - o downgrade vazio passa e o downgrade com produto é recusado.
- [X] T005 `produtos/models.py`:
  - `Produto` (`_Versioned` + `AuditMixin`, os `__versioned_fields__` com a propriedade `variantes`, e
    `perfil_id` imutável);
  - `ProdutoVariante`;
  - os enums.

  Também: `perfis/models.py` com `ImageKind.produto`; `history.py` com `entity_type "produto"` (se a lista
  for fechada); e o registro no metadata.
- [X] T006 [P] `imaging.py`: `"produto"` em `MIN_SIZE` (512×512), `_KIND_FORMATS` (PNG/JPG/WebP) e
  `ImageKind`. Em `tests/unit/test_imaging.py`: 511×511 recusado, 512×512 aceito e GIF recusado.
- [X] T007 [P] `produtos/estados.py` (R8, R9; puro):
  - `ficha_completa(produto, variantes)`;
  - `pendencias(produto, variantes, abertas)`;
  - `proximo(produto, variantes, abertas, evento) -> (status, pedidos)`, onde `pedidos` é a lista de
    `(passo, variante_id?)` a criar.
- [X] T008 [P] `tests/unit/test_produtos_estados.py`:
  - cada linha da tabela de transições do data-model;
  - sem variante → `rascunho`;
  - a ficha ausente pede `produto.ficha` uma vez só (com uma aberta, não pede);
  - recorte faltando pede só para as variantes sem geração aberta;
  - flat só depois do recorte;
  - uma geração falha não é repedida;
  - `aprovado` + edição → `revisao`;
  - pendências exatas (`sem_cor`, `geracao_em_andamento`…).
- [X] T009 [P] `produtos/flat.py` (R7): `instrucao(ficha, variante)` com o texto exato do pipeline, os
  `detalhes_visiveis` unidos por "; " e a `cor_en` da variante. `tests/unit/test_produtos_flat.py` confere o
  texto byte a byte para o `shorts_canelado` e a mudança quando cor ou material mudam.
- [X] T010 [P] `produtos/ficha.py` (R5):
  - `FichaSaida` (pydantic, espelha o `Ficha` do pipeline, com `detalhes_visiveis: list[str]` e
    `cores: [{foto, en, pt}]`);
  - `SYSTEM` (o texto do pipeline, adaptado ao SociMan);
  - `montar_mensagem(fotos, nome, obs)`: blocos "PRODUCT PHOTO N" + imagem reduzida em memória a ≤ 1568 px
    no lado maior, em JPEG 90;
  - `validar_limites(ficha)` (R2).

  `tests/unit/test_produtos_ficha.py`:
  - foto de 4000 px vira 1568 no lado maior, sem gravar nada;
  - os limites de cada campo;
  - `material_en` com 6 palavras é recusado;
  - os campos em inglês são guardados sem trim.
- [X] T011 [P] `ia/tipos.py` (acréscimo, R14 da 021): `produto.ficha` em `TipoCampoId`, com o schema
  `FichaSaida`, a regra padrão e `PROMPT_VERSION` `produto/1` em `details`, **fora** do `listar_regras`. Em
  `tests/unit/test_ia_tipos.py`: o tipo existe e não aparece na lista de regras editáveis.
- [X] T012 [P] Fakes do Claude:
  - `tests/fakes/anthropic_fake.py` e `e2e/fakes/server.py` respondem a ficha quando o `system` é o da
    ficha: `shorts_canelado` determinístico, uma cor por foto e `precisa_flat` conforme a instrução;
  - modos "recusa" e "ficha inválida";
  - o fake conta as chamadas de ficha (para o SC-002).
- [X] T013 `produtos/schemas.py` (camelCase): `ProdutoResumo`, `Produto`, `Ficha`, `Variante`,
  `ImagemRef`, `Pendencia`, `UsoProduto` e os corpos de entrada, conforme `contracts/api.md`.

**Checkpoint:** migração verde, funções puras testadas e fakes prontos.

---

## Phase 3: User Story 1 - Cadastrar e receber a ficha (Priority: P1) 🎯 MVP

**Goal:** criar o produto com 1 a 6 fotos e receber a ficha do Claude numa chamada só, gravada antes da GPU
e registrada na 008.

**Independent Test:** com o Claude falso, criar com 3 fotos e conferir a ficha, as cores, o Registro (com
`geracao_id`) e o histórico; com a GPU fora, a ficha continua e não é pedida de novo.

- [X] T014 [US1] `produtos/service.py`, parte 1:
  - `criar(db, actor, perfil, name, obs, url_loja, fotos)`:
    - valida **todas** as fotos (`imaging.validate_image` com kind `produto` e 20 MB) antes de gravar
      qualquer uma;
    - passa pelo `datadir` (503/507) e grava em `storage` (`bucket="imagens"`);
    - cria as `images` e as variantes em ordem e chama `history.record` (`created`);
    - chama `fluxo.reavaliar`;
  - `listar` (filtros por estado, `arquivados`, `q` sem acento e sem caixa, cursor `(updated_at desc, id)`,
    miniatura do recorte da 1ª variante ativa);
  - `editar` (`name`, `obs`, `url_loja` com `https://`);
  - `ver` com estado efetivo, pendências, passos (`fila.abertas_do_alvo` + a última de cada passo ×
    variante) e links (sem validade nas imagens da variante).
- [X] T015 [US1] `produtos/fluxo.py` (R8): `reavaliar(db, actor, produto)`:
  - aplica `estados.proximo`;
  - cria as gerações pedidas pelo serviço de pedido da 021, com o `params` do data-model e o ator humano
    (no gancho, o `created_by` da geração que terminou);
  - grava o status com versão;
  - é idempotente, porque confere as gerações abertas antes de criar.
- [X] T016 [US1] `produtos/aplicadores.py`, parte 1:
  - o aplicador de `produto.ficha`:
    - `validar_alvo` (produto do perfil, não arquivado);
    - `montar_params`;
    - `aplicar`: copia a `FichaSaida` para o produto e as cores para as variantes por `position`, define
      `ficha_por = ia` e grava versão com `details.geracao_id` e `automatico`;
  - o `ao_mudar_estado` dos três passos, que chama `fluxo.reavaliar`;
  - o registro dos três passos em `geracao/passos.py` com `image_kind = "produto"`;
  - o import no `main.py` e no `cli.py` do gerador.
- [X] T017 [US1] `geracao/router.py` (acréscimo, R1): o `POST /api/perfis/{id}/geracoes` com `alvoTipo =
  produto` responde 409 `alvo_incompativel` ("use as ações do produto").
- [X] T018 [US1] `produtos/router_perfil.py` (`produtos_listar`, `produtos_criar` multipart) e
  `produtos/router.py` (`produtos_ver`, `produtos_editar`, `produtos_pedir_ficha`), com `RequireHuman` nas
  escritas e `RequireUser` nas leituras, incluídos no `main.py`. Depois, `npm run gen:contract`.
- [X] T019 [P] [US1] `tests/integration/test_produtos_crud.py`:
  - criar com 3 fotos → 3 variantes em ordem, `gerando`, 1 geração `produto.ficha`;
  - criar sem fotos → `rascunho`;
  - foto 511 px, foto de 21 MB ou GIF → 400 `invalid_image` com `field = fotos[N]`, sem nenhuma linha
    criada;
  - 7 fotos → 409 `limite_variantes`;
  - membro cria; token MCP → 403 `somente_humano`;
  - HD sem sentinela → 503.
- [X] T020 [P] [US1] `tests/integration/test_produtos_fluxo.py`, parte 1 (fake do Claude e o gerador da 021
  rodando em teste):
  - a ficha aplicada preenche todos os campos e as cores, com `ficha_por = ia`;
  - `ia_chamadas` tem 1 linha `produto.ficha` com `geracao_id`, custo e desfecho `aplicada`;
  - a versão do produto tem `details.geracao_id`;
  - a observação "jeans" com a resposta "ribbed knit" mantém o que o fake devolveu em `cuidados`.
- [X] T021 [P] [US1] `tests/integration/test_produtos_falhas.py`, parte 1:
  - sem chave → a geração `falhou` com o código da 008/021 e o produto fica `gerando`, com
    `produtos_pedir_ficha` disponível depois de cancelar;
  - recusa e saída inválida → nada na ficha e o Registro com `erro`;
  - **SC-002:** com a ficha aplicada e o ComfyUI fora, "Tentar de novo" no recorte **não** gera nova
    chamada de ficha (contador do fake = 1).
- [X] T022 [US1] SPA:
  - `lib/produtos.ts` (hooks; polling enquanto houver passo aberto);
  - `pages/perfis/tabs/ProdutosTab.tsx`: `DataTable` com miniatura, nome comercial ou interno, categoria,
    variantes, estado e data; filtro por estado, busca e "Ver arquivados"; diálogo "Novo produto" com nome,
    até 6 fotos com prévia e ordem, e observação; erros por foto;
  - a aba no perfil (`?aba=produtos`) e a rota `/app/produtos/:id`.

**Checkpoint:** o produto nasce e recebe a ficha; o MVP já serve para copiar as palavras certas.

---

## Phase 4: User Story 2 - Recorte e flat, com escolha humana (Priority: P1)

**Goal:** recorte direto por variante; flat com 2 opções e escolha humana; "Refazer flat".

**Independent Test:** com o ComfyUI falso, produto de roupa com 2 variantes → 2 recortes, 2 × 2 opções,
escolhas, "Gerar outras" e "Refazer flat"; produto que não é roupa → sem flat.

- [X] T023 [US2] `produtos/aplicadores.py`, parte 2:
  - o aplicador de `produto.recorte`: a variante de `extras.varianteId` é do produto e está ativa; `aplicar`
    grava `recorte_image_id` com versão `automatico`;
  - o aplicador de `produto.flat`:
    - `montar_params` com a `flat.instrucao` e o recorte vigente;
    - `aplicar` só pela escolha humana: confere que o recorte de `params` ainda é o da variante (senão,
      `entrada_invalida`) e grava `flat_image_id` + `flat_geracao_id` com versão `details.geracao_id`.
- [X] T024 [US2] `produtos/service.py`, parte 2: `refazer_flat(db, actor, produto, variante)`:
  - com a última aberta em `revisao` → 409 `estado_invalido` ("use Gerar outras");
  - ficha incompleta ou variante sem recorte → 409 `produto_incompleto`;
  - nos outros casos, cria a geração pelo serviço da 021 (seeds depois da maior) e `reavaliar`;
  - num produto `aprovado`, volta a `revisao`.

  Rota `produtos_refazer_flat`; depois, `gen:contract`.
- [X] T025 [US2] `produtos/uso.py` (R12): o provedor do `midia_em_uso` da 021 com toda imagem de
  `produto_variantes` (original, recorte e flat, de variante ou produto arquivados).
- [X] T026 [P] [US2] `tests/integration/test_produtos_fluxo.py`, parte 2:
  - ficha com `precisa_flat` → recortes (1 por variante, `escolhido` sem revisão) → flats (2 opções cada,
    `revisao`), com os nós do `cutout`/`keyframe` preenchidos no fake (instrução e recorte);
  - "Usar opção 2" → `flat_image_id` e `flat_geracao_id`, versão com a geração, e o produto `revisao` só
    quando todas as variantes escolheram;
  - "Gerar outras" → seeds novas e a antiga `descartada`, com o flat vigente intacto até a nova escolha;
  - `refazer-flat` depois de escolhido;
  - `precisa_flat = false` → sem passo de flat, direto para `revisao`.
- [X] T027 [P] [US2] `tests/integration/test_produtos_falhas.py`, parte 2:
  - GPU ocupada → "Aguardando a GPU ficar livre", e o passo começa sozinho quando ela libera;
  - `OutOfMemoryError` no flat → `falhou` `sem_memoria`, e o `dockerctl_fake` mostra 28 → 12 GB;
  - cancelar um flat → 12 GB, e o produto fica `gerando` com o passo pendente (sem recriar sozinho);
  - o gerador **nunca** chama `aplicar` do `produto.flat` (guarda da 021, estendida);
  - escolher por token MCP → 403.
- [X] T028 [P] [US2] `tests/integration/test_produtos_limpeza.py`:
  - limpeza de 90 dias (CLI `sociman geracoes limpar`) apaga as opções não escolhidas de flat;
  - mantém o flat escolhido, os recortes e as originais, e também uma imagem de variante arquivada
    (provedor `uso.py`);
  - grava o evento `eliminacao_candidatos`;
  - a folha continua com o flat escolhido.
- [X] T029 [US2] SPA, `pages/produtos/ProdutoPage.tsx`, parte 1:
  - os passos com `AndamentoGeracao` (progresso, "Aguardando a GPU ficar livre", erro, "Tentar de novo" e
    "Cancelar");
  - por variante, `OpcoesGeracao` com o flat lado a lado, "Usar opção N" (AlertDialog) e "Gerar outras";
  - "Refazer flat" na variante com flat escolhido.

**Checkpoint:** o cadastro completo roda até `revisao` com o ComfyUI falso.

---

## Phase 5: User Story 3 - Revisar, editar e aprovar (Priority: P1)

**Goal:** folha de revisão, ficha editável com origem, aprovar com pendências, voltar a `revisao` ao editar.

**Independent Test:** levar um produto a `revisao`, editar uma cor, aprovar e conferir a origem, o estado, o
histórico e o seletor; editar de novo → `revisao`.

- [X] T030 [US3] `produtos/service.py`, parte 3:
  - `salvar_ficha(db, actor, produto, version, ficha, cores)`:
    - aplica as regras de `ficha_por` do R9 (`null → humano`, `ia → ia_editada`);
    - cancela a `produto.ficha` aberta;
    - valida os limites;
    - `aprovado → revisao`;
    - ligar `precisa_flat` → `reavaliar` pede os flats que faltam;
  - variantes: criar (multipart, ≤ 6 ativas), editar cor, arquivar (recusa a última), restaurar (respeita o
    limite) e ordenar (exatamente as ativas);
  - `aprovar(db, actor, produto, version)`: 409 `produto_incompleto` com as pendências, ou 409
    `estado_invalido` fora de `revisao`.

  Cada mutação passa por `history.record` e `version`. As rotas `produtos_salvar_ficha`,
  `produtos_aprovar` e `produtos_variante_*` ficam com `RequireHuman`; depois, `gen:contract`.
- [X] T031 [US3] Aviso `flat_desatualizado` (R10) e `sem_cor` na leitura da variante (`service.ver`).
- [X] T032 [P] [US3] `tests/integration/test_produtos_aprovar.py`:
  - aprovar sem flat → 409 com `sem_flat` na variante certa;
  - com `produto.flat` em `revisao` → `geracao_em_andamento`;
  - variante sem cor → `sem_cor`;
  - aprovar com tudo → `aprovado`; o membro também aprova (FR-021);
  - editar ficha, cor, `precisa_flat`, refazer flat ou adicionar variante num aprovado → `revisao` (ou
    `gerando`);
  - origem `ia → ia_editada`; a ficha à mão sem IA → `humano`, que libera os recortes;
  - `flat_desatualizado` aparece só quando cor, material, corte ou detalhes mudam;
  - `version_conflict` em edição concorrente;
  - 7ª variante → 409; arquivar a última → 400.
- [X] T033 [US3] SPA, `ProdutoPage.tsx`, parte 2:
  - `FolhaRevisao.tsx`: linhas originais | recortes | flats numeradas; no celular, uma coluna por variante
    (SC-007);
  - `FichaForm.tsx`: `Field`, listas editáveis item a item, selo "vai literal para os prompts" nos campos
    em inglês, "Copiar descrição para prompts" e o switch `precisa_flat`;
  - "Preencher à mão" quando a `produto.ficha` falhou ou foi cancelada (ao salvar, a origem é `humano`);
  - `VarianteCard.tsx`: cores, avisos, arquivar e ordenar;
  - o botão **Aprovar** com a lista de pendências.

**Checkpoint:** um produto pode ser aprovado e volta a `revisao` quando muda.

---

## Phase 6: User Story 4 - Usar nas cenas (Priority: P2)

**Goal:** a cena aponta para produto e variante do catálogo (só aprovados), com a frase da ficha no prompt e
o recorte como ingrediente; as cenas antigas continuam.

**Independent Test:** ligar uma cena a um produto aprovado e conferir o seletor, o prompt, o ingrediente, o
"onde é usado" e uma cena antiga.

- [X] T034 [US4] `cenas/models.py` e `cenas/service.py` (acréscimo, R13):
  - `produto_id` e `produto_variante_id` em `__versioned_fields__` e nos campos que mudam o prompt;
  - validação ao ligar: produto do perfil, aprovado e não arquivado; variante ativa e com recorte;
    exclusão com `produto_nome`/`produto_imagem_id` (400 `invalid_cena`, field `produtoId`);
  - "Ligar ao catálogo" = PATCH que limpa os campos leves numa versão só;
  - o filtro `produtoId` na lista.
- [X] T035 [US4] `cenas/prompt.py`: `Entrada` ganha `produto_prompt` e `produto_cor`. Com catálogo, a ação
  recebe ", with the product exactly as in the reference image", e entra a parte `produto` logo depois:
  a `descricao_prompt` literal + "Color: {cor_en}." quando há variante. A referência leve fica igual.
  `cenas/ingredientes.py`: com catálogo, o ingrediente `produto` é o recorte da variante (ou da 1ª ativa),
  com `produtoId`/`produtoVarianteId`. `cenas/avisos.py`: `produto_fora_de_aprovado`. `cenas/schemas.py`:
  `produto?` e os campos do `Ingrediente`. Depois, `gen:contract`.
- [X] T036 [US4] `produtos/usos.py`: as cenas por `produto_id` (origem `cena`, `bloqueia = false`, href),
  no `service.ver`.
- [X] T037 [P] [US4] `tests/unit/test_cenas_prompt_produto.py`:
  - prompt com catálogo (com e sem variante), byte a byte;
  - prompt com referência leve **idêntico** ao da 010 (regressão);
  - a parte `produto` na ordem certa.
- [X] T038 [P] [US4] `tests/integration/test_produtos_cenas.py`:
  - ligar a produto em `revisao` → 400; aprovado → ok;
  - variante de outro produto → 400; produto + `produtoNome` → 400;
  - "Ligar ao catálogo" numa cena antiga → uma versão, campos leves nulos;
  - cena `pronta` volta a `rascunho`; cena `usada` recusa (409, regra da 010);
  - o produto volta a `revisao` → a cena mostra `produto_fora_de_aprovado` e continua;
  - "onde é usado" do produto lista a cena; arquivar o produto não é bloqueado;
  - cenas antigas sem mudança de prompt congelado.
- [X] T039 [US4] SPA, cenas:
  - no formulário da cena, o seletor de produto (só aprovados, `NativeSelect`) e de variante (com
    miniatura);
  - nas cenas com referência leve, "Ligar ao catálogo";
  - o produto e a variante no detalhe e na lista (filtro por produto);
  - o aviso `produto_fora_de_aprovado`.

---

## Phase 7: User Story 5 - Lista, arquivo e histórico (Priority: P2)

**Goal:** filtros, busca, arquivar e restaurar mantendo o estado, histórico e reversão pelo dono.

- [X] T040 [US5] `produtos/service.py`, parte 4:
  - `arquivar` (com `cancelarGeracoes?`, que cancela as abertas pela 021) e `restaurar` (só limpa
    `archived_at`; o status fica como estava, R4);
  - `versoes` e `reverter` (só dono, `RequireOwner`): restaura ficha, cores e referências de imagem **sem
    gerar nada**, seguido de `reavaliar`. Uma versão alvo `aprovado` volta a `revisao`.

  As rotas e `gen:contract`.
- [X] T041 [P] [US5] `tests/integration/test_produtos_historico.py`:
  - arquivar e restaurar um aprovado → continua `aprovado`, sem geração nova;
  - o produto arquivado sai do seletor;
  - geração aberta num produto arquivado aplica no produto arquivado (R4);
  - reverter a ficha → a versão anterior volta e o histórico tem `reverted`;
  - o membro tenta reverter → 403;
  - filtros por estado, busca sem acento e "arquivados=so".
- [X] T042 [US5] SPA: na `ProdutoPage`, arquivar/restaurar (AlertDialog, com a opção de cancelar as
  gerações), a seção "Onde é usado" e o histórico (o componente de versões das outras entidades, com
  "Reverter" só para o dono).

---

## Phase 8: User Story 6 - MCP só leitura (Priority: P3)

- [X] T043 [US6] `mcp/mapa.py` (acréscimo, R14):
  - `produtos_listar` ("Listar produtos", padrão `status=aprovado`), `produtos_ver` e `produtos_versoes`
    como `leitura`;
  - todas as outras rotas `produtos_*` em `PROIBIDAS`.

  `anotacoes/models.py` e `anotacoes/service.py`: o alvo `produto`, só com `observacao`.
- [X] T044 [P] [US6] `tests/integration/test_produtos_mcp.py` e `tests/unit/test_mcp_mapa.py`:
  - o cliente "só leitura" lista os aprovados e lê a ficha, com a chamada registrada;
  - o cliente "propostas" grava `observacao` num produto, que aparece na caixa "Propostas dos agentes",
    sem mudar a ficha;
  - `proposta_texto` num produto → recusado;
  - nenhuma tool de escrita de produto existe;
  - o teste "todo operationId classificado" continua verde.

---

## Phase 9: Polish & Cross-Cutting

- [X] T045 [P] `tests/unit/test_constitution_guards.py` (acréscimo):
  - `produtos/` não importa `publicacao` nem `mcp`, e não chama `storage.apagar_por_excecao`;
  - sem "tiktok"/"youtube" em `produtos_*`;
  - sem DELETE em `produtos`/`produto_variantes`;
  - as escritas de `produtos/` com `RequireHuman` (ou `RequireOwner` no revert).
- [X] T046 [P] `tests/integration/test_produtos_permissoes.py`:
  - todas as escritas com membro → ok (menos `reverter` → 403);
  - `system:*` e token MCP → 403 `somente_humano` mais o evento de recusa;
  - as leituras aceitam membro e MCP.
- [X] T047 `e2e/produtos.spec.ts` (Claude e ComfyUI falsos):
  - criar com 2 fotos e ver a ficha;
  - esperar os recortes e escolher os 2 flats (um com "Gerar outras");
  - editar uma cor e aprovar;
  - ligar uma cena ao produto e conferir o prompt e o ingrediente;
  - editar a ficha → `revisao`, e o seletor da cena não oferece mais o produto;
  - no celular (390 px), a folha sem rolagem horizontal.

  Com a trava dos e2e; nunca `npx playwright test` direto.
- [X] T048 `CLAUDE.md` (acréscimo): a seção "Produtos do Shop (desde a spec 012)", com:
  - o pacote e as tabelas;
  - os 3 passos e os aplicadores da 021;
  - o recorte automático e o flat humano;
  - o arquivamento efetivo (status mantido);
  - o `produto.ficha` no registro da 008;
  - a ponte com a 010 (campos leves continuam);
  - a `location` de 130m.

  `docs/visao.md`: o item 12 no backlog.
- [X] T049 Verificação final:
  - `npm run test:api` inteiro, ruff, `npm run gen:contract && npm run check:web`;
  - a suíte e2e inteira (com trava);
  - o quickstart §1 no dev.

  As §2 e §3 são **com o dono**, na GPU real; registre o resultado. **Commit só quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate) → T002.
- **Phase 2** bloqueia tudo:
  - T003 → T004 e T005;
  - T006, T007, T009, T010, T011 e T012 em paralelo;
  - T007 → T008; T005 → T013.
- **US1 (Phase 3):**
  - T014 → T015 → T016 → T018;
  - T017 em paralelo com T014;
  - T019, T020 e T021 depois de T018;
  - T022 depois de T018.
- **US2 (Phase 4):** depende de T016. T023 → T024 → T026 e T027. T025 → T028. T029 depois de T024.
- **US3 (Phase 5):** depende de T023. T030 → T031 → T032. T033 depois de T030.
- **US4 (Phase 6):** precisa de produtos aprovados (T030). T034 → T035 → T036 → T037 e T038. T039 depois de
  T035.
- **US5 (Phase 7):** depende de T030. T040 → T041 e T042.
- **US6 (Phase 8):** depende de T018. T043 → T044.
- **Serialização:**
  - o `gen:contract` (T018, T024, T030, T035, T040);
  - os arquivos compartilhados (`produtos/service.py`: T014, T024, T030, T040; `cenas/*`: T034, T035);
  - os e2e, pela trava.
- **Phase 9** no fim. A T045 e a T046 podem começar assim que as rotas existirem.

### Paralelismo sugerido (agentes)

- **Frente A (API, núcleo):** T003, T005, T013 → T014–T018 → T023–T025 → T030–T031 → T040.
- **Frente B (puros e fakes):** T006–T012.
- **Frente C (testes):** T004, T008, T019–T021, T026–T028, T032, T037, T038, T041, T044–T046.
- **Frente D (SPA e e2e):** T022, T029, T033, T039, T042, T047.
- **Frente E (cenas e MCP):** T034–T036, T043, depois da T030.

## Implementation Strategy

- **MVP:** a US1 (cadastro e ficha), que já entrega as palavras exatas para os prompts sem GPU.
- **Depois:**
  - a US2 e a US3, que fecham o cadastro aprovado;
  - a US4 (cenas);
  - a US5 e a US6.
- **Checkpoints:**
  - depois da Phase 2, da US1 e da US2 (com o SC-002 verde);
  - depois da US3 (aprovar);
  - depois da US4 (regressão do prompt da 010);
  - no fim.
