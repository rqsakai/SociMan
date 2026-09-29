---

description: "Tarefas da feature 007-assets-do-perfil"
---

# Tasks: Biblioteca de assets do perfil (007-assets-do-perfil)

**Input**: `specs/007-assets-do-perfil/` (spec, plan, research R1–R11, data-model, contracts/http-api.md, quickstart, open-questions resolvidas)

**Decisões do dono (2026-09-29):** Q1 = A (só o **kit** bloqueia arquivar; cortes só informam), Q2 = A (fundo: fundos + cenários; marca d'água: marcas d'água + stickers), Q3 = A (reordenar com botões ←/→ + arrastar nativo HTML5, sem dependência nova).

**Nomes canônicos** (valem os documentos do plano): pacote `sociman_api/assets/`; `entity_type = "asset"`; migration `0005_assets` (`down_revision = "0004_fundo_imagem"`; a 006 encadeia `0006_cortes_openshorts` sobre ela); erros novos `invalid_asset`, `pose_label_in_use`, `asset_in_use`, `asset_archived`; `MidiaKind` `imagem`; aba do perfil `?aba=assets` (o `PerfilDetalhe` usa o parâmetro `aba`).

**Tests**: OBRIGATÓRIOS (constitution, princípio VI):
- pytest na stack efêmera (`npm run test:api`), que pode rodar em paralelo com a 006;
- `docker compose exec api uv run ruff check .`;
- `npm run gen:contract && npm run check:web` (contrato regenerado, CSP inalterada);
- e2e na stack isolada (`npm run test:e2e`); **nunca** dois `test:e2e` ao mesmo tempo, nem com a 006 (armadilha 18);
- a migração verificada no dev (SC-003, quickstart §0).

**Arquivos compartilhados com a 006: SÓ ACRÉSCIMO** (nunca reescrever nem reordenar trechos existentes; bloco novo ao lado dos vizinhos):
`docker/nginx/default.conf.template`, `docker-compose.yml`, `apps/api/src/sociman_api/midia.py`, `apps/api/src/sociman_api/router_midia.py`, `apps/api/src/sociman_api/imaging.py`, `apps/web/src/pages/perfis/PerfilDetalhe.tsx`, `apps/web/src/components/shell/nav.ts` (a 007 **não toca**: Assets é aba, não item de menu). Também só acréscimo: `apps/api/src/sociman_api/main.py`, `apps/api/migrations/env.py`, `apps/api/tests/conftest.py`, `apps/web/src/App.tsx`, `e2e/helpers.ts`, `CLAUDE.md`, `docs/visao.md`. `packages/contract/**` é **gerado**: em conflito, rebase e `npm run gen:contract` de novo (armadilha 6).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US4 da spec

---

## Phase 1: Setup (infra e linha de base)

- [ ] T001 Linha de base no dev, **antes** de subir qualquer código novo (quickstart §0):
  - `docker compose exec api uv run alembic heads` → `0004_fundo_imagem` (se a 006 já tiver mergeado a dela, ajustar o `down_revision` da 007 conforme research R11);
  - anotar em `specs/007-assets-do-perfil/quickstart.md` (Resultado) a contagem `SELECT kind, count(*) FROM images WHERE kind IN ('watermark','fundo') GROUP BY kind;` e, por perfil, `watermark.imagem_id`, `hook.fundo_imagem_id` e `endCard.fundo_imagem_id` do kit vigente.
- [ ] T002 [P] Em `docker-compose.yml` (só acréscimo), serviço `imgproxy`: `IMGPROXY_MAX_SRC_RESOLUTION: "40"` (R3). Conferir a versão com `docker compose exec imgproxy imgproxy version`, validar com `docker compose config -q` e aplicar com `docker compose up -d imgproxy`.
- [ ] T003 [P] Em `docker/nginx/default.conf.template` (só acréscimo: bloco novo, sem mexer nas `location` existentes), a `location ~ ^/api/(perfis/[^/]+/assets/arquivo|assets/[^/]+/arquivos)$` com `client_max_body_size 21m`, buffering normal e os mesmos `proxy_*`/headers do `location /api/`. Depois `docker compose restart edge` (armadilha 13). Verificar: um POST de 15 MB nessa rota não recebe 413 do edge (chega à API), e um POST de 15 MB em outra rota de `/api/` recebe 413.

---

## Phase 2: Foundational (modelo, migração, imaging, mídia, esqueleto)

**⚠️ Bloqueia todas as histórias.**

- [ ] T004 Criar `apps/api/src/sociman_api/assets/__init__.py` e `assets/models.py` com `AssetTipo` (`avatar`, `cenario`, `fundo`, `sticker`, `marca_dagua`, `imagem`), `FileRole` (`referencia`, `pose`, `arquivo`), `Asset` (AuditMixin + `_Versioned`) e `AssetFile`, exatamente com as restrições do data-model:
  - `assets.name` "1..80, sem espaço nas pontas"; `description` "até 2.000"; `tags` "até 20; cada uma 1..30, minúsculas, sem espaço nas pontas, sem repetição"; `prompt` "só `avatar` … e `cenario` …; até 2.000; guardado **exatamente** como enviado (sem trim)"; `voice_tone` "só `avatar`; até 500"; `image_rules` "só `avatar`; até 2.000"; `primary_file_id` "arquivo **ativo** do próprio asset" (FK `use_alter`);
  - check `ck_assets_campos_por_tipo`; índices `(perfil_id, archived_at, updated_at desc, id)`, GIN em `tags`, `(perfil_id, lower(name))`; nome **não** é único;
  - `asset_files.image_id` "UNIQUE FK → images.id"; `look` "só `referencia` de avatar; 1..60"; `uso` "só `referencia`; até 200"; `label` "**obrigatório** em `pose`; 1..60"; `quando_usar` "só `pose`; até 300"; `notes` "até 500"; `position` "ordem dentro de (`asset_id`, `role`), 0..n-1, sem buracos entre os ativos";
  - UNIQUE parcial `(asset_id, lower(label)) WHERE role = 'pose' AND archived_at IS NULL`; índice `(asset_id, role, position)`;
  - `__versioned_fields__` = `tipo`, `name`, `description`, `tags`, `prompt`, `voice_tone`, `image_rules`, `primary_file_id`, `archived`, `files`; `__immutable_fields__` = `tipo`; propriedade `files` (lista ordenada por `role` e `position` com `id`, `image_id`, `role`, `look`, `uso`, `label`, `quando_usar`, `notes`, `position`, `archived`).

  Em `apps/api/src/sociman_api/perfis/models.py`, `ImageKind` += `avatar`, `imagem`. Em `apps/api/migrations/env.py`, um import dos modelos de `assets` (só acréscimo). Em `apps/api/tests/conftest.py`, `assets` e `asset_files` no `_TABLES` (só acréscimo).
- [ ] T005 [P] Criar `apps/api/src/sociman_api/assets/tipos.py`: tabela tipo → `image_kind` (`avatar`→`avatar`, `cenario`→`fundo`, `fundo`→`fundo`, `sticker`→`watermark`, `marca_dagua`→`watermark`, `imagem`→`imagem`), roles aceitos por tipo (`avatar`: `referencia`/`pose`; `cenario`: `referencia`; demais: `arquivo`), "um arquivo só" nos tipos `fundo`, `sticker`, `marca_dagua` e `imagem`, campos por tipo e a mensagem de transparência ("O sticker precisa ter fundo transparente" / "A imagem precisa ter fundo transparente").
- [ ] T006 Criar `apps/api/src/sociman_api/assets/backfill.py` (`backfill(conn)`, SQL puro sobre a conexão, idempotente, R2): para cada `images` com `kind IN ('watermark','fundo')` sem `asset_files`, em ordem de `created_at, id` por perfil e tipo, cria o asset (`marca_dagua`/`fundo`, nome "Marca d'água N"/"Fundo N", `created_at`/`created_by` da imagem, `version = 1`), o `asset_files` (`role = arquivo`, `position = 0`), o `primary_file_id` e a v1 no `entity_versions` (`created`, `actor_kind = 'system:migration'`, `details = {"migracao": "0005_assets", "image_id": …}`).
- [ ] T007 Criar `apps/api/migrations/versions/0005_assets.py` (`revision = "0005_assets"`, `down_revision = "0004_fundo_imagem"`):
  1. `ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'avatar'` e `'imagem'` (não usados na mesma transação);
  2. `CREATE TYPE asset_tipo`, `asset_file_role`; tabelas `assets`, `asset_files`; índices e checks de T004;
  3. `backfill(op.get_bind())`;
  4. **downgrade** recusa se existir asset criado depois da migração (`actor_kind <> 'system:migration'` em alguma v1) ou imagem `avatar`/`imagem`; senão remove tabelas e tipos e recria o `image_kind` sem os dois valores (como a `0004`). Nada de objeto é apagado.

  Testar `upgrade head` → `downgrade 0004_fundo_imagem` → `upgrade head` no banco de teste (stack efêmera).
- [ ] T008 [P] Criar `apps/api/tests/integration/test_assets_backfill.py` (**SC-003**): criar imagens `watermark` e `fundo` sem asset (como a 004 deixava) em dois perfis e um kit que as usa; contar por `kind` **antes**; rodar `backfill`; conferir que a contagem com `JOIN asset_files` é **igual** à de antes, que o `LEFT JOIN … WHERE f.id IS NULL` dá **0**, que os `images.id` e os tokens do kit não mudaram, os nomes "Fundo 1"/"Marca d'água 1" por ordem de envio, a v1 com `system:migration`; rodar de novo não cria nada (idempotente). Testar também a recusa do downgrade com um asset criado pela API.
- [ ] T009 [P] Em `apps/api/src/sociman_api/imaging.py` (só acréscimo, sem mudar o comportamento dos kinds existentes): `MIN_SIZE`/`_KIND_FORMATS` de `avatar` (PNG/JPG/WebP, 256×256) e `imagem` (PNG/JPG/WebP, 64×64); parâmetros `max_bytes` (padrão 5 MB) e `transparency_message` no `validate_image`; "Imagem grande demais (máximo 40 megapixels)" em vez de "Formato não aceito" acima de 40 MP; `preview_url` (1024×1024, fit). Em `perfis/service_imagens.py`, `read_limited(stream, max_bytes=…)`. Criar `apps/api/tests/unit/test_imaging_assets.py`: kinds novos, 20 MB aceito no limite e 20 MB + 1 byte recusado com "Arquivo maior que 20 MB" (ruído com `os.urandom`, sem fixture no git), sticker sem alfa e PNG todo opaco recusados com "O sticker precisa ter fundo transparente", mensagem de megapixels; os testes de `test_imaging.py` e `test_imaging_watermark.py` continuam verdes sem mudança.
- [ ] T010 [P] Criar `apps/api/src/sociman_api/assets/schemas.py` (`AssetCreate`, `AssetPatch`, `FilePatch`, `Ordem`, `AssetSummary`, `AssetOut`, `AssetFileOut`, `Uso`, `LibraryImage`, `TagCount`, camelCase como o contrato) e `apps/api/tests/unit/test_assets_schemas.py`: campos de avatar só em `avatar` ("campo não se aplica a este tipo"), `prompt` também em `cenario`, limites de tamanho, normalização de tags, `prompt` sem trim, `label` obrigatório em `pose`.
- [ ] T011 [P] Mídia (só acréscimo): em `apps/api/src/sociman_api/midia.py`, `MidiaKind` += `imagem` (id = `images.id`, qualquer `kind`, pode ser assinado sem validade; nunca vídeo); em `apps/api/src/sociman_api/router_midia.py`, o ramo `imagem` no `resolve` (original do bucket `sociman`, `Content-Type` da tabela, `Range`, `?download=1` com `content_disposition`); `POST /api/midia/links` aceita `{kind: "imagem", id}` (1 h). Acrescentar casos em `apps/api/tests/unit/test_midia.py` (token sem `exp` determinístico).
- [ ] T012 Criar `apps/api/src/sociman_api/assets/service.py` (núcleo): carregar asset do perfil (404), checar `version` (409 `version_conflict`, "Este asset foi alterado por outra pessoa; recarregue"), `asset_archived` ("Restaure o asset antes de editar"), `perfil_archived`, `history.record` na **mesma transação** em toda mutação (`entity_type = "asset"`), e o envio de arquivo comum: `datadir.ensure_writable()` **antes** de ler o corpo (503/507), `read_limited(max_bytes=20 MB)`, `validate_image(kind, max_bytes, transparency_message)`, `storage.put` em `perfis/{perfil_id}/{uuid4}.{ext}`, linha em `images` e em `asset_files`. Criar `assets/router_perfil.py` e `assets/router.py` vazios e registrá-los em `apps/api/src/sociman_api/main.py` (2 `include_router`, só acréscimo). Usar `DbSession`, nunca `Depends(get_db)` (armadilha 7).
- [ ] T013 [P] Em `apps/api/src/sociman_api/marca/tokens.py`, a função pura `fields_using_image(kit, image_id) -> list[str]` (`watermark.imagem_id`, `hook.fundo_imagem_id`, `endCard.fundo_imagem_id` **não nulos**, mesmo com a seção desligada ou `fundo_tipo = cor`), com casos novos em `apps/api/tests/unit/test_kit_tokens.py`. Criar `apps/api/src/sociman_api/assets/usos.py` com o registro (`register(origem, fn)`, `usos_do_perfil(db, perfil_id) -> {image_id: [Uso]}`) e o provedor **kit** (`bloqueia = true`, rótulos "Card final (kit vN)", "Gancho (kit vN)", "Marca d'água (kit vN)", `href` `/app/perfis/{id}?aba=marca`).

**Checkpoint:** `npm run test:api` e ruff verdes; `alembic upgrade head` sobe a `0005_assets`.

---

## Phase 3: User Story 1 - Avatares e poses (Priority: P1) 🎯 MVP

**Goal**: criar o avatar com descrição para prompts, tom de voz, regras de imagem, looks e poses reordenáveis, com "Copiar descrição para prompt" e histórico com reversão.

**Independent Test**: avatar "Achadinhos" no Queridinhos com a descrição do `persona.md`, 2 looks (cozinha e diner), a pose "apontando para o produto", tudo na aba Assets, e o texto copiado idêntico.

### Tests for User Story 1

- [ ] T014 [P] [US1] Criar `apps/api/tests/integration/test_assets.py` (parte avatar):
  - criar avatar (201, v1), campos de avatar, `prompt` guardado sem trim;
  - enviar `referencia` com `look`/`uso` e `pose` com `label`/`quandoUsar`; o primeiro arquivo vira o principal; trocar o principal por `PATCH primaryFileId`;
  - pose com rótulo repetido (sem diferenciar maiúsculas) → 409 `pose_label_in_use` ("Já existe uma pose com esse rótulo neste avatar"); restaurar pose com rótulo já em uso → 409;
  - `PUT /ordem` com a lista exata dos ativos (lista incompleta → 400 `invalid_asset`); a ordem persiste;
  - `role` incompatível e `look` em `pose` → 400 `invalid_asset` com `field`;
  - **princípio VII:** cada mutação gera uma versão com autor e `changed_fields`; 409 `version_conflict` em edição concorrente; reversão só dono (403 membro); reversão que arquiva o arquivo que não existia na versão alvo; "Essa versão é igual à atual" → 400;
  - HD fora (sem sentinela): criar avatar sem arquivo funciona; enviar arquivo → 503 `storage_unavailable`; piso → 507.

### Implementation for User Story 1

- [ ] T015 [US1] Em `assets/service.py`: `criar_asset`, `editar_asset` (inclui `primaryFileId`), `enviar_arquivo` (roles de avatar e cenário; sem `version`: só acrescenta), `editar_arquivo`, `reordenar` (uma versão por reordenação), `arquivar_arquivo`/`restaurar_arquivo` (principal passa ao primeiro ativo, ou null; restaurado volta ao fim da ordem; consulta `usos` para bloquear), `listar_versoes`, `reverter` (campos + metadado, ordem e arquivamento dos arquivos da versão alvo; arquivo inexistente na versão alvo é **arquivado**, nunca apagado; 409 `revert_conflict` se arquivaria algo em uso no kit).
- [ ] T016 [US1] Rotas: em `assets/router_perfil.py`, `POST /api/perfis/{id}/assets` e um `GET /api/perfis/{id}/assets` básico (mais recentes primeiro, `archived=false`); em `assets/router.py`, `GET/PATCH /api/assets/{id}`, `POST /api/assets/{id}/arquivos`, `PATCH /api/assets/{id}/arquivos/{fileId}`, `PUT /api/assets/{id}/ordem`, `POST …/arquivos/{fileId}/archive|restore`, `GET /api/assets/{id}/versions` e `POST /api/assets/{id}/revert` (**`RequireOwner`**); todas as demais `RequireUser`. **Nenhuma rota DELETE.** `AssetFileOut` com `image`, `previewUrl`, `hasAlpha`, `link` e `downloadUrl` (T011).
- [ ] T017 [US1] `npm run gen:contract` (host), `docker compose exec api uv run ruff check .` e `npm run test:api` verdes. **Libera a trilha SPA para a US1.**
- [X] T018 [P] [US1] SPA, peças sem contrato: `apps/web/src/components/assets/CopyButton.tsx` (`navigator.clipboard.writeText` com fallback: `Textarea` somente leitura selecionada e "Copie com Ctrl+C"; copia o texto exato) e `components/assets/ReorderButtons.tsx` ("Mover para a esquerda/direita", acessíveis por teclado e toque).
- [ ] T019 [US1] SPA base: `apps/web/src/lib/assets.ts` (rótulos pt-BR dos tipos e papéis, query keys, upload por XHR com checagem de 20 MB e tipo no navegador), `pages/perfis/tabs/AssetsTab.tsx`, `components/assets/{AssetGrid,AssetCard,NovoAssetMenu}.tsx` (card com miniatura `medium` ou as iniciais em cor neutra via `Avatar` do shadcn; menu Avatar, Cenário, Fundo, Sticker, Marca d'água, Imagem). Em `pages/perfis/PerfilDetalhe.tsx` (só acréscimo): um item `{ id: "assets", label: "Assets" }` em `tabs` e um `TabsContent value="assets"`.
- [ ] T020 [US1] SPA detalhe: `pages/assets/AssetDetalhe.tsx` e as rotas `/app/assets/:id` e `/app/assets/:id/historico` em `apps/web/src/App.tsx` (só acréscimo); `components/assets/{AvatarCampos,LooksSection,PosesGrid,AssetFileCard,AssetUpload}.tsx`: descrição para prompts (contador de 2.000) + "Copiar descrição para prompt", tom de voz, regras de imagem, tags; **Looks** agrupados por `look` com uso e "Marcar como principal"; **Poses** em grade com rótulo e "quando usar", `ReorderButtons` e arrastar nativo HTML5 (`draggable`, `onDragOver`, `onDrop`) no desktop, uma chamada `PUT /ordem` por reordenação; `version` em toda mutação e 409 com "recarregue". `usePageMeta` com a trilha Perfis › perfil › asset.
- [ ] T021 [US1] SPA histórico: `pages/assets/AssetHistorico.tsx` com o `components/VersionHistory.tsx` da 003 (antes/depois, inclusive `files`); "Reverter" só para dono. `npm run check:web` verde.
- [ ] T022 [US1] Criar `e2e/assets.spec.ts` (US1): avatar "Achadinhos" com descrição, 2 looks (imagens 1080×1080 geradas no teste; helper em `e2e/helpers.ts`, só acréscimo) e 3 poses; 4ª pose "Surpresa" recusada; mover "piscando" para o início com os botões e recarregar; "Copiar descrição para prompt" com permissões `clipboard-read`/`clipboard-write` e `navigator.clipboard.readText` igual ao texto; avatar sem imagem mostra "TE". Rodar `npm run test:e2e -- e2e/assets.spec.ts`.

**Checkpoint:** US1 pronta e demonstrável ao dono (plan: "As etapas 1, 3 e 6 (avatar) fecham a US1").

---

## Phase 4: User Story 2 - Cenários e fundos (Priority: P1)

**Goal**: cenários com prompt e referências; os seletores de fundo do kit escolhem **fundos e cenários** da biblioteca; as imagens da 004 aparecem como fundos.

**Independent Test**: cenário "Cozinha retrô" com prompt e imagem, escolhido como fundo do card final na aba Marca pelo seletor da biblioteca.

### Tests for User Story 2

- [ ] T023 [P] [US2] Em `apps/api/tests/integration/test_assets.py` (acréscimo): cenário com `prompt`, só `referencia` (outro role → 400); `POST /api/perfis/{id}/assets/arquivo` com `tipo=fundo` (nome padrão = nome do arquivo sem extensão, tags por vírgula; `tipo` `avatar`/`cenario` → 400); segundo arquivo em tipo simples → 400 "este tipo aceita um arquivo só"; `GET …/assets/imagens?tipo=fundo&tipo=cenario` só com arquivos ativos de assets ativos, mais recentes primeiro. Criar `apps/api/tests/integration/test_assets_usos.py` (parte kit): `PUT /kit` aceita imagem de `cenario` no fundo; imagem de asset ou arquivo arquivado → `invalid_kit` ("imagem arquivada; restaure-a na biblioteca"); reverter o kit para versão com imagem arquivada → 409 `revert_conflict`; o upload pelas rotas antigas (`/fundos`, `/marca-dagua`) cria o asset e a lista antiga omite imagens de assets arquivados. `test_fundos.py`, `test_marca_dagua.py`, `test_kit.py`, `test_export.py` e `test_cortes.py` verdes **sem mudança de asserção**; um corte enviado com fundo de cenário sai com a imagem.

### Implementation for User Story 2

- [ ] T024 [US2] Em `assets/router_perfil.py` e `assets/service.py`: `POST /api/perfis/{id}/assets/arquivo` (atalho "um arquivo = um asset"; HD conferido antes de ler o corpo) e `GET /api/perfis/{id}/assets/imagens` (`tipo` repetível e obrigatório, `q?`, `limit?` 60) devolvendo `LibraryImage`.
- [ ] T025 [US2] Em `apps/api/src/sociman_api/marca/service_kit.py`, `ref_context`: `watermark_image_ids`/`fundo_image_ids` passam a exigir imagem em arquivo **ativo** de asset **ativo** do perfil (com o `kind` de hoje), com a mensagem de `invalid_kit` acima. Nada muda em `cortes/**`.
- [ ] T026 [US2] Em `apps/api/src/sociman_api/marca/router_marca_dagua.py`, `upload_image` cria também o asset (`marca_dagua` ou `fundo`, mesma transação, `history.record`); `deprecated=True` nas rotas de `router_marca_dagua.py` e `router_fundos.py`; as listas antigas omitem imagens de assets arquivados.
- [ ] T027 [US2] `npm run gen:contract`, ruff e `npm run test:api` verdes. **Libera a trilha SPA para a US2.**
- [ ] T028 [US2] SPA: `components/assets/LibraryImageDialog.tsx` ("Abrir biblioteca": `Dialog` com busca e filtro de tipo); `components/marca/ProfileImagePicker.tsx` lista de `GET …/assets/imagens` (as 12 mais recentes), envia por `POST …/assets/arquivo` com limite de 20 MB e escolhe a imagem no rascunho (enviar não altera o kit); `components/marca/FundoImagePicker.tsx` pede `tipo=fundo&tipo=cenario` e troca os textos. No `AssetDetalhe`, o cenário mostra prompt do ambiente + "Copiar prompt" e as referências. `npm run check:web` verde.
- [ ] T029 [US2] e2e: em `e2e/assets.spec.ts` (acréscimo), cenário "Cozinha retrô" com imagem 1080×1080, escolhido como fundo do card final pelo seletor ("Abrir biblioteca", busca "cozinha"), kit salvo e prévia com a imagem; "Enviar imagem" no seletor cria um "Fundo" na biblioteca. Ajustar `e2e/fundo.spec.ts` **só no seletor** (texto do botão de envio e lista da biblioteca).

**Checkpoint:** US1 e US2 funcionam de forma independente.

---

## Phase 5: User Story 3 - Stickers e imagens de marca (Priority: P2)

**Goal**: stickers e marcas d'água com transparência real, tags, filtros e busca; a marca d'água do kit escolhe **marcas d'água e stickers**.

**Independent Test**: 3 stickers com tags "reação"/"promo", filtro "promo" mostra só os certos; um sticker escolhido como marca d'água no kit.

### Tests for User Story 3

- [ ] T030 [P] [US3] Em `apps/api/tests/integration/test_assets.py` (acréscimo): sticker JPG e PNG opaco → 400 `invalid_image` "O sticker precisa ter fundo transparente"; marca d'água sem alfa → "A imagem precisa ter fundo transparente"; filtros `tipo` (OR), `tag` (E lógico, `tags @> ARRAY[…]`), `q` (nome contém ou tag igual), `archived` (`false`/`true`/`all`), cursor opaco com `limit` (48, máx. 100) sem repetir nem pular itens, `tags: TagCount[]`; `GET …/assets/imagens?tipo=marca_dagua&tipo=sticker`. Em `test_assets_usos.py`: `PUT /kit` aceita imagem de sticker em `watermark.imagem_id`. Em `apps/api/tests/integration/test_assets_midia.py`: link `marca_dagua` para imagem de sticker funciona.

### Implementation for User Story 3

- [ ] T031 [US3] Criar `apps/api/src/sociman_api/assets/busca.py` (R8: filtros, busca `lower(name) LIKE '%q%'` ou tag igual a `lower(q)`, ordenação `updated_at desc, id`, cursor `updated_at|id` em base64url, contagem de tags do perfil) e ligá-lo ao `GET /api/perfis/{id}/assets` em `assets/router_perfil.py`, com `inUse` por item (uma consulta ao kit por página). `npm run gen:contract`, ruff e `npm run test:api` verdes.
- [ ] T032 [US3] SPA: `components/assets/AssetFilters.tsx` (chips de tipo, chips de tag com contagem, busca com debounce de 250 ms, "Mostrar arquivados"); `AssetsTab` com `useInfiniteQuery` e "Carregar mais"; envio múltiplo (um asset por arquivo) para Fundo, Sticker, Marca d'água e Imagem; miniatura sobre xadrez quando `hasAlpha`; `components/marca/WatermarkImagePicker.tsx` pede `tipo=marca_dagua&tipo=sticker` e troca os textos. `npm run check:web` verde.
- [ ] T033 [US3] e2e: em `e2e/assets.spec.ts` (acréscimo), 3 stickers PNG com alfa gerados no teste e tags `reação`/`promo`; filtro por `promo` e busca por nome; JPG como sticker recusado com a mensagem da spec; sticker escolhido como marca d'água no kit. Ajustar `e2e/marca.spec.ts` **só no seletor**.

**Checkpoint:** US1–US3 funcionam de forma independente.

---

## Phase 6: User Story 4 - Onde é usado, arquivar e baixar (Priority: P2)

**Goal**: "Onde é usado" (kit bloqueia; cortes só informam, Q1 = A), arquivar/restaurar sem apagar, "Baixar original" e "Copiar link" estável sem login.

**Independent Test**: arquivar o fundo usado no kit é recusado com "Em uso em: Card final (kit v3)"; trocar no kit e arquivar; baixar o original.

### Tests for User Story 4

- [ ] T034 [P] [US4] Em `apps/api/tests/integration/test_assets_usos.py` (acréscimo): arquivar asset (e arquivo) usado no kit → 409 `asset_in_use` com `details.usos` e "Em uso em: Card final (kit vN)", inclusive com a seção desligada ou `fundo_tipo = cor`; trocar no kit e arquivar passa; **asset usado só em cortes arquiva normalmente** e o `GET /api/assets/{id}` continua listando o uso por cortes com `bloqueia = false` (Q1 = A); arquivar o único arquivo de tipo simples → 400 "arquive o asset"; `inUse` no resumo; reversão do asset que arquivaria arquivo em uso → 409 `revert_conflict`.
- [ ] T035 [P] [US4] Em `apps/api/tests/integration/test_assets_midia.py` (acréscimo): `AssetFile.link` sem validade e **estável** (duas leituras, mesmo token); abre sem login; `downloadUrl` com `Content-Disposition` `<slug-do-perfil>-<nome-do-asset>-<n>.<ext>`; `sha256` do download igual ao enviado; `Range`; link continua valendo com o asset arquivado; HD fora → 503; token adulterado → 403 `invalid_link`.

### Implementation for User Story 4

- [ ] T036 [US4] Em `apps/api/src/sociman_api/assets/usos.py`, o provedor **corte** (`bloqueia = false`: conta os cortes do perfil cujo `kit_tokens` tem a `object_key` em `watermark.imagem_key`, `hook.fundo_imagem_key` ou `end_card.fundo_imagem_key`, e lista os 5 mais recentes; só leitura da tabela `cortes`). Em `assets/service.py` e `assets/router.py`: `POST /api/assets/{id}/archive|restore` com 409 `asset_in_use` (só usos com `bloqueia = true`); `GET /api/assets/{id}` devolve `{asset, usos}`. `npm run gen:contract`, ruff e `npm run test:api` verdes.
- [ ] T037 [US4] SPA: `components/assets/UsosList.tsx` ("Onde é usado", com link para a aba Marca), "Arquivar"/"Restaurar" em `AlertDialog` (409 mostra a lista de usos), selos "Em uso" e "Arquivado" no card, "Baixar original" e "Copiar link" (via `CopyButton`) em `AssetFileCard`, arquivar/restaurar arquivo. `npm run check:web` verde.
- [ ] T038 [US4] e2e: em `e2e/assets.spec.ts` (acréscimo), arquivar a referência usada no card final → "Em uso em: Card final (kit v…)"; trocar o fundo para cor, salvar e arquivar; "Mostrar arquivados" e "Restaurar"; "Copiar link" aberto num contexto sem sessão carrega a imagem.

**Checkpoint:** todas as histórias funcionam de forma independente.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T039 [P] Em `apps/api/tests/integration/test_assets.py` (acréscimo), o teste parametrizado do **princípio VII** sobre todas as rotas de mutação de asset (autor, antes/depois, `version` +1) e a confirmação de que `test_revert.py::test_no_delete_routes` e `unit/test_constitution_guards.py` cobrem as rotas novas (SC-004, princípio I).
- [ ] T040 [P] **SC-002:** criar `e2e/assets-escala.spec.ts`: seed de 200 assets pela API (tipos e tags variados; helper em `e2e/helpers.ts`, só acréscimo) e cronômetro da abertura da aba Assets até achar um asset por tag e por nome (< 10 s cada).
- [ ] T041 **SC-003 no dev** (quickstart §0): `docker compose up -d --build api` (o `start.sh` roda `alembic upgrade head`); rodar as três consultas do §0 e comparar com a linha de base de T001 (contagens iguais, 0 sem asset, versões `system:migration`); kit de cada perfil com os mesmos ids, prévia e "Exportar JSON" iguais; `alembic upgrade head` de novo não cria nada. Registrar a saída no Resultado do `quickstart.md`.
- [ ] T042 Quickstart §1–§5 no dev, à mão: **SC-001** (avatar com 2 looks e 3 poses < 5 min, cronometrado), **SC-005** (todo o `../shared/shop/persona.md` coube sem campo faltando), limites de 19/21 MB (a resposta de 21 MB vem da API, não um 413 do edge), HD fora (sentinela renomeado e restaurado). Registrar no Resultado.
- [ ] T043 [P] `CLAUDE.md` (só acréscimo): seção curta "Biblioteca de assets (desde a spec 007)": pacote `assets/`, tipos × `image_kind`, `entity_type = asset`, 20 MB com `location` de 21m no edge, `MidiaKind imagem` sem validade, só o kit bloqueia arquivar, seletores do kit pela biblioteca, rotas antigas `deprecated`.
- [ ] T044 [P] `docs/visao.md`: corrigir o backlog (005 = UI shadcn, 006 = cortes-openshorts, 007 = assets do perfil) e marcar a 007 como implementada com as decisões (Q1–Q3). Arquivo compartilhado com a 006: editar só as linhas da 007 e avisar a trilha da 006 sobre a renumeração.
- [ ] T045 Verificação final: `npm run test:api`, `docker compose exec api uv run ruff check .`, `npm run gen:contract && npm run check:web` e `npm run test:e2e` (sem outro e2e rodando, inclusive da 006), todos verdes; `curl -s http://localhost:8180/api/openapi.json | grep -c '"delete"'` → 0; CSP inalterada (`check:csp`). Commit só quando o dono pedir.

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (T001–T003):** T001 **antes** de qualquer rebuild da API no dev (a linha de base some depois da migração). T002 e T003 em paralelo.
- **Foundational (T004–T013):** T004 → T005/T006 → T007 → T008. T009, T010, T011 e T013 em paralelo depois de T004. T012 depende de T004, T005, T009 e T011. **Bloqueia todas as histórias.**
- **US1 (T014–T022):** T015 → T016 → T017 → T019 → T020 → T021 → T022. T014 e T018 em paralelo.
- **US2 (T023–T029):** depois da fundação; T024 → T025 → T026 → T027 → T028 → T029. Reusa o `enviar_arquivo` de T015 (cenário); se a US2 andar antes da US1, T015 entra junto.
- **US3 (T030–T033):** T031 → T032 → T033. A busca (T031) pode andar em paralelo com a US2 na API.
- **US4 (T034–T038):** T036 → T037 → T038. O provedor do kit (T013) já bloqueia desde a fundação; T036 acrescenta cortes e as rotas de arquivar o asset.
- **Polish (T039–T045):** depois das histórias desejadas; T041 exige a API nova no dev.

### Parallel Opportunities
- Testes marcados [P] de cada história andam juntos com a implementação da API de outra trilha.
- API de US2, US3 e US4 pode andar em sequência rápida enquanto o SPA fecha a US1.
- `npm run test:api` pode rodar em paralelo (stacks efêmeras); `npm run test:e2e` **não**.

---

## Trilhas para agentes paralelos

Três agentes, sem arquivo em comum entre eles. Cada trilha só edita os arquivos listados; qualquer outro arquivo pede coordenação pelo líder.

| Trilha | Agente sugerido | Tarefas | Arquivos (exclusivos) |
|---|---|---|---|
| **A: API** | `api-007` | T004–T017, T023–T027, T030–T031, T034–T036, T039 | `apps/api/**` (inclui `migrations/`, `tests/`, `main.py`, `env.py`, `conftest.py`, e os acréscimos em `imaging.py`, `midia.py`, `router_midia.py`, `marca/*`); **única trilha que roda `npm run gen:contract`** e toca `packages/contract/**` (gerado) |
| **B: SPA** | `spa-007` | T018–T021, T028, T032, T037 | `apps/web/**` (novos em `components/assets/`, `pages/assets/`, `pages/perfis/tabs/AssetsTab.tsx`, `lib/assets.ts`; acréscimos em `App.tsx`, `PerfilDetalhe.tsx`, `components/marca/*Picker.tsx`) |
| **C: infra, e2e e docs** | `e2e-007` | T001–T003, T022, T029, T033, T038, T040–T044 | `docker/nginx/default.conf.template`, `docker-compose.yml`, `e2e/**`, `specs/007-assets-do-perfil/quickstart.md`, `CLAUDE.md`, `docs/visao.md` |

Sincronização:
1. A começa pela fundação; C faz T001–T003 ao mesmo tempo (T001 antes do primeiro rebuild da API no dev).
2. B começa T018 (sem contrato) logo; T019 em diante espera o T017 (contrato da US1). Depois, cada história do SPA espera o `gen:contract` da história na trilha A (T027 para a US2, T031 para a US3, T036 para a US4).
3. C escreve cada e2e depois que A e B fecham a história; roda `npm run test:e2e` **sozinho** (combinar com a trilha e2e da 006, armadilha 18).
4. T045 (verificação final) fica com o líder, depois das três trilhas.
5. Com a 006: `PerfilDetalhe.tsx`, `default.conf.template`, `docker-compose.yml`, `midia.py`, `router_midia.py` e `imaging.py` recebem **só acréscimos** (blocos novos, sem reordenar); a migration `0006_cortes_openshorts` da 006 encadeia sobre a `0005_assets` (research R11).

---

## Implementation Strategy

### MVP (US1)
1. Setup + Foundational (inclui a migração com o teste de SC-003).
2. US1 (avatar, looks, poses, copiar, histórico).
3. **Parar e validar** com o dono (quickstart §1).

### Incremental
US2 (cenários + seletor de fundo) → US3 (stickers, filtros, seletor de marca d'água) → US4 (usos, arquivar, links) → Polish (SC-001/002/003/005, docs, verificação final).

## Notes
- Nenhum DELETE, nenhum `storage` delete, nenhuma dependência nova (Python ou npm); `toggle-group` do shadcn só se preciso (código gerado no repo).
- `cortes/**` não é tocado (R3); o provedor de usos só lê a tabela `cortes`.
- Commit só quando o dono pedir, em pt-BR, no imperativo.
