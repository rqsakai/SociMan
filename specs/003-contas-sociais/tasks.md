---

description: "Tarefas da feature 003-contas-sociais"
---

# Tasks: Perfis e contas sociais (003-contas-sociais)

**Input**: Design documents from `/specs/003-contas-sociais/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-api.md, quickstart.md

**Tests**: OBRIGATÓRIOS pelo princípio VI, conforme o quickstart §5. As regras do princípio VII
(histórico, sem DELETE, reversão só pelo dono) têm teste no backend.

**Organization**: tarefas por user story. US1 = perfis (P1), US2 = contas (P1), US4 = histórico e
reversão (P1), US3 = imagens (P2). A US4 vem antes da US3 pela prioridade.

**Desvio de organização em relação ao plan.md:** para os agentes trabalharem em paralelo sem
colidir, o serviço do domínio se divide em `service_perfis.py`, `service_contas.py` e
`service_imagens.py`, e as rotas de imagem ficam em `router_imagens.py`.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Adicionar `minio`, `pillow` e `python-multipart` em `apps/api/pyproject.toml`. Rodar `uv lock` e depois `docker compose build api && docker compose up -d api`. Conferir o import no container
- [X] T002 Configuração:
  - `apps/api/src/sociman_api/config.py`: acrescentar `s3_endpoint` (`minio:9000`), `s3_access_key`, `s3_secret_key`, `s3_bucket` (`sociman`), `s3_secure` (false), `imgproxy_key`, `imgproxy_salt` (opcionais, em hex) e `img_public_path` (`/img`);
  - `.env.docker` e `.env.example`: os valores de dev do MinIO (`minioadmin`, **só dev**, como já está no compose) e `TEST_S3_BUCKET=sociman-test`;
  - `docker/nginx/default.conf.template`: `client_max_body_size 6m;` na `location /api/`. Depois, `docker compose up -d edge` e `nginx -t`;
  - se `IMGPROXY_KEY`/`IMGPROXY_SALT` estiverem no `.env` da raiz (gitignored), repassar ao `api` e ao `imgproxy` no `docker-compose.yml` (`${IMGPROXY_KEY:-}`). Vazios, o modo é `unsafe` em dev.
- [X] T003 [P] Em `apps/api/tests/conftest.py`, criar a fixture de sessão `s3_bucket`: aponta `s3_bucket` para `TEST_S3_BUCKET`, cria o bucket se não existir e esvazia os objetos **só no bucket de teste**, entre os testes que a usam. O TRUNCATE da autouse passa a incluir `entity_versions`, `images`, `contas` e `perfis` quando essas tabelas existirem

---

## Phase 2: Foundational (bloqueia todas as stories)

- [X] T004 Criar `apps/api/src/sociman_api/history.py`:
  - modelo `EntityVersion`, exatamente como em data-model.md (`entity_type`, `entity_id`, `version`, `action`, `actor_kind`, `actor_user_id`, `occurred_at`, `before` jsonb, `after` jsonb, `changed_fields` text[], `details` jsonb; `UNIQUE (entity_type, entity_id, version)`; índice `(entity_type, entity_id, version desc)`);
  - `diff(before, after) -> list[str]`;
  - `record(db, actor, entity_type, entity, action, before, after, details=None)`: incrementa `entity.version` e insere a versão na mesma sessão;
  - `list_versions(db, entity_type, entity_id)`;
  - `version_state(db, entity_type, entity_id, n) -> dict` (o `after` da versão n);
  - `check_version(entity, expected)`: levanta `ApiError(409, "version_conflict", …)`.

  A mensagem de conflito recebe o nome da entidade ("Este perfil…" / "Esta conta…"). Criar também `apps/api/tests/unit/test_history.py` para o `diff` e a ordem de versões.
- [X] T005 Criar `apps/api/src/sociman_api/perfis/{__init__,models}.py`, com `Perfil`, `Conta` e `Image` exatamente como em data-model.md:
  - enums `perfil_status`, `platform`, `conta_status` e `image_kind`;
  - `slug` UNIQUE com `CHECK` do formato;
  - os dois índices únicos de `contas`, sendo o parcial `WHERE status='ativa' AND archived_at IS NULL`;
  - `images.object_key` UNIQUE;
  - `AuditMixin`, `version`, `archived_at` e `archived_by`.

  Importar `history` e `perfis.models` em `migrations/env.py`. Gerar e revisar `apps/api/migrations/versions/0002_perfis.py`, com downgrade completo. Aplicar em `sociman` e em `sociman_test` e testar downgrade e upgrade no de teste.
- [X] T006 [P] Criar os módulos de imagem:
  - `apps/api/src/sociman_api/storage.py`: cliente `minio.Minio` com `lru_cache`; `put(key, data, content_type)`, `get(key)` e `ensure_bucket(name)`; **nenhuma** função de delete.
  - `apps/api/src/sociman_api/imaging.py`, com `validate_image(data: bytes, kind) -> ImageInfo(content_type, ext, width, height, sha256)`:
    - usa Pillow com `Image.MAX_IMAGE_PIXELS = 40_000_000`, `verify()` e depois reabre para ler as dimensões;
    - aceita só PNG, JPEG e WebP pelo formato real;
    - recusa mais de 5 MB e menos que o mínimo (logo 200×200, banner 1000×250);
    - devolve `ApiError(400, "invalid_image", "Formato não aceito" | "Arquivo maior que 5 MB" | "Imagem pequena demais")`.
  - Também em `imaging.py`: `image_urls(object_key) -> {thumb, medium}` e `banner_url(object_key)`, montando as URLs do imgproxy como o adapter do volans (`reference/volans-api/src/lib/adapters/imgproxy.ts`): `rs:fit:96:96`, `256:256` e `1200:300`, `f:webp`, fonte `s3://{bucket}/{key}` em base64url, assinadas com HMAC-SHA256 quando há key e salt, senão `unsafe`.
  - Testes unitários em `apps/api/tests/unit/test_imaging.py`: imagens geradas com Pillow; arquivo texto `.png`; 6 MB; pequeno demais; bomb (cabeçalho com dimensões enormes); URLs com e sem assinatura, comparadas com um vetor conhecido.
- [X] T007 [P] Criar `apps/api/src/sociman_api/perfis/platforms.py`:
  - tabela de plataformas com templates de link e regex de extração (R8);
  - `normalize_handle`;
  - `handle_from_url`;
  - `url_for`;
  - `suggest_slug(name)` (R9).

  Criar `apps/api/tests/unit/test_platforms.py`, com os casos do spec: "Achadinhos da Lú!" → `achadinhos-da-lu`, links colados do TikTok e do YouTube, e `@ Meus.Queridinhos ` → `meus.queridinhos`.
- [X] T008 [P] Criar `apps/api/src/sociman_api/perfis/schemas.py` com os tipos de contracts/http-api.md:
  - saídas: `ImageRef`, `Perfil`, `Conta`, `Version`, `UserRef`;
  - entradas: `CreatePerfilIn`, `UpdatePerfilIn` (sem slug, com `version` obrigatório), `VersionIn`, `CreateContaIn`, `UpdateContaIn`, `RevertIn {version, toVersion}`.

  Usar `CamelModel` de `auth/schemas.py`, com os limites de tamanho do data-model.

**Checkpoint**: migration aplicada; testes unitários de history, imaging e platforms verdes.

---

## Phase 3: User Story 1 - Perfis (Priority: P1) 🎯 MVP

**Independent Test**: quickstart §1.

- [X] T009 [P] [US1] Criar `apps/api/tests/integration/test_perfis.py`:
  - criar, listar (busca `q`, filtro `status`, `archived`), obter e editar;
  - slug sugerido, slug duplicado dá 409 `slug_in_use`, e slug no PATCH é ignorado ou recusado (400);
  - PATCH com `version` velha dá 409 `version_conflict`;
  - arquivar e restaurar (a lista padrão não mostra arquivado);
  - cada mutação gera uma `entity_version` com autor, antes e depois e `changed_fields` corretos;
  - `GET /versions` vem ordenado do mais recente;
  - sem sessão dá 401;
  - membro pode tudo, exceto reverter (reversão testada na US4).
- [X] T010 [US1] Criar `apps/api/src/sociman_api/perfis/service_perfis.py`: `list_perfis`, `create_perfil`, `get_perfil`, `update_perfil`, `archive_perfil` e `restore_perfil`. Cada mutação faz `check_version`, calcula o snapshot antes e depois e chama `history.record` na mesma transação, com `updated_by` vindo do ator. A saída monta `platforms` a partir das contas ativas e `logo`/`banner` via `imaging`
- [X] T011 [US1] Criar `apps/api/src/sociman_api/perfis/router_perfis.py` com as rotas de perfis do contrato, **exceto** imagens e reversão:
  - list, `slug-suggestion`, create (201), get (com contas), PATCH, archive, restore e versions;
  - `RequireUser` em todas;
  - operationIds `perfis_*`;
  - erros documentados com `ErrorEnvelope`.

  Incluir o router em `main.py`, antes de `install_openapi_error_contract`. Rodar `uv run --directory apps/api python scripts/export_openapi.py`.
- [X] T012 [US1] SPA:
  - regenerar o contrato e acrescentar os métodos `perfis.*` ao `packages/contract/src/client.ts`;
  - criar `apps/web/src/pages/perfis/PerfisList.tsx` (`/app/perfis`): tabela com avatar (iniciais), Nome, Nicho, Status e Plataformas, busca, filtro de status e "Arquivados", e botão "Novo perfil";
  - criar `PerfilNovo.tsx` (`/app/perfis/novo`): Nome, Identificador (sugerido pela API enquanto se digita o nome, editável só aqui), Nicho, Descrição, Idioma e Status;
  - criar `PerfilDetalhe.tsx` (`/app/perfis/:id`), com a aba **Dados** (edita Nome, Nicho, Descrição, Idioma e Status; o slug aparece como somente leitura; trata 409 com "Este perfil foi alterado por outra pessoa; recarregue") e as ações Arquivar e Restaurar;
  - link "Perfis" no `AppLayout` para todos;
  - rotas em `App.tsx`;
  - rótulos pt-BR em `apps/web/src/lib/perfis.ts`: Em preparação, Ativo, Pausado.

  `npm run check:web` verde.

---

## Phase 4: User Story 2 - Contas (Priority: P1)

**Independent Test**: quickstart §2.

- [X] T013 [P] [US2] Criar `apps/api/tests/integration/test_contas.py`:
  - adicionar por @ e por link colado;
  - normalização;
  - "outra" exige nome e link;
  - @ repetido na mesma plataforma em outro perfil, inclusive arquivado, dá 409 `handle_in_use` com o nome do perfil na mensagem;
  - segunda conta **ativa** na mesma plataforma do perfil dá 409 `active_platform_exists`, enquanto uma planejada é aceita;
  - mudar status para ativa com outra ativa dá 409;
  - PATCH com versão velha dá 409;
  - arquivar e restaurar;
  - versões gravadas;
  - as `platforms` do perfil refletem as contas ativas.
- [X] T014 [US2] Criar `apps/api/src/sociman_api/perfis/service_contas.py`: `create_conta`, `update_conta`, `archive_conta` e `restore_conta`, com histórico. Converter `IntegrityError` dos dois índices únicos nos 409 corretos: consultar o dono do @ para montar a mensagem, e tratar também a corrida entre a checagem e a inserção
- [X] T015 [US2] Criar `apps/api/src/sociman_api/perfis/router_contas.py`: `POST /api/perfis/{id}/contas`, `PATCH /api/contas/{id}`, archive, restore e versions, com operationIds `contas_*`. Incluir em `main.py` e exportar o OpenAPI
- [X] T016 [US2] SPA: aba **Contas** no `PerfilDetalhe.tsx`, com:
  - lista com ícone da plataforma (`components/PlatformIcon.tsx`, SVG inline em componente, sem CDN), `@handle`, link, status e ações Editar, Arquivar e Restaurar;
  - formulário "Adicionar conta" com Plataforma (`<select>`: TikTok, YouTube, Instagram, Kwai, Facebook, X, Outra), "Nome da plataforma" (só quando é Outra), "@ ou link", Status e Observação;
  - mensagens de 409.

  Regenerar o contrato e os métodos `contas.*`. `npm run check:web` verde.

---

## Phase 5: User Story 4 - Histórico e reversão (Priority: P1)

**Independent Test**: quickstart §4.

- [X] T017 [P] [US4] Criar `apps/api/tests/integration/test_revert.py`:
  - o dono reverte o perfil para v1: os campos voltam, surge uma versão nova com `action=reverted` e `details.from_version`, e as intermediárias continuam lá;
  - o slug nunca muda na reversão;
  - membro dá 403;
  - `toVersion` inexistente dá 404 ou 400;
  - versão atual velha dá 409;
  - reverter conta que traria de volta um @ usado por outra dá 409 `handle_in_use`;
  - reverter para um estado com duas ativas dá 409 `active_platform_exists`;
  - reverter perfil arquivado para versão não arquivada restaura;
  - `test_no_delete_routes`: nenhum método DELETE em `app.openapi()` (SC-006).
- [X] T018 [US4] Implementar `revert_perfil` em `service_perfis.py` e `revert_conta` em `service_contas.py`, usando `history.version_state`, aplicando só os campos do snapshot e ignorando o slug. Criar as rotas `POST /api/perfis/{id}/revert` (em `router_perfis.py`) e `POST /api/contas/{id}/revert` (em `router_contas.py`) com `RequireOwner`. Exportar o OpenAPI
- [X] T019 [US4] SPA:
  - componente genérico `apps/web/src/components/VersionHistory.tsx`: recebe `versions`, `labels` de campos e `onRevert?`; mostra, para cada versão, número, ação ("Criado", "Alterado", "Arquivado", "Restaurado", "Revertido"), autor, data e uma tabela Campo | Antes | Depois só dos `changedFields`; o botão "Reverter para esta versão" aparece só quando `onRevert` existe e o usuário é dono, com confirmação;
  - aba **Histórico** no `PerfilDetalhe.tsx`;
  - "Histórico" por conta, num painel na aba Contas.

  `npm run check:web` verde.

---

## Phase 6: User Story 3 - Logo e banner (Priority: P2)

**Independent Test**: quickstart §3.

- [X] T020 [P] [US3] Criar `apps/api/tests/integration/test_imagens.py` (fixture `s3_bucket`, MinIO real):
  - PNG, JPG e WebP válidos sobem, o objeto existe no bucket de teste com o content-type certo, e o perfil passa a ter `logo.urls.thumb` começando com `/img/`;
  - texto com extensão `.png`, 6 MB, logo 100×100 e banner 800×200 dão 400 `invalid_image` com a mensagem certa, e nada é gravado;
  - trocar o logo cria uma imagem nova e o objeto antigo continua no bucket;
  - `clear` remove a referência sem apagar o objeto;
  - reverter para a versão com o logo antigo o traz de volta (SC-005);
  - versão com `changed_fields` igual a `["logo_image_id"]`;
  - membro pode enviar.
- [X] T021 [US3] Criar `apps/api/src/sociman_api/perfis/service_imagens.py` e `router_imagens.py`:
  - `PUT /api/perfis/{id}/logo|banner`: multipart com `file` e `version`; lê no máximo 5 MB + 1 byte e recusa acima disso; `validate_image`; `put` no MinIO com a chave `perfis/{id}/{uuid}.{ext}`; linha em `images`; referência no perfil; histórico;
  - `POST …/logo/clear` e `…/banner/clear`;
  - operationIds `perfis_upload_logo` e afins.

  Incluir em `main.py`. Verificar pelo edge (`curl -F`) que 5 MB passa, que 6 MB é barrado pela API com 400 e não pelo nginx com 413, e que a URL `/img/...` devolvida responde 200 sem login. Confirmar também a FR-009a: a porta S3 do MinIO (9000) não está publicada no host (`docker compose port minio 9000` vazio) e a chave do objeto contém um uuid4.
- [X] T022 [US3] SPA:
  - `components/ImageUpload.tsx`: escolher o arquivo, prévia local, mostrar os limites ("PNG, JPG ou WebP até 5 MB; mínimo …") e enviar via `FormData` com `version`;
  - `components/ProfileAvatar.tsx`: logo em miniatura ou iniciais sobre cor neutra;
  - usar os dois na lista, no cabeçalho do perfil e na aba Dados, com botões "Trocar logo", "Trocar banner" e "Remover".

  Não adicionar nada à CSP (`/img` é `'self'`). `npm run check:web` verde.

---

## Phase 7: e2e e Polish

- [X] T023 Criar `e2e/perfis.spec.ts`, cobrindo quickstart §1–4:
  - criar o perfil (slug sugerido);
  - adicionar a conta TikTok por link colado e ver o `@`;
  - recusa da segunda ativa;
  - enviar o logo (fixture PNG gerada no teste) e ver a miniatura `<img src^="/img/">`;
  - editar a bio duas vezes;
  - histórico com antes e depois;
  - o dono reverte;
  - arquivar e restaurar.

  Rodar `npm run test:e2e`, que zera o banco de dev e é autorizado pelo dono nesta fase.
- [X] T024 [P] Atualizar `CLAUDE.md` com o módulo `history.py` (como toda spec de domínio deve usá-lo), `storage.py` e `imaging.py`, o limite de upload de 6 MB no edge, o `IMGPROXY_KEY`/`SALT` opcionais e "sem DELETE no domínio". Atualizar também `docs/visao.md`, marcando a 003 como implementada, com as decisões
- [X] T025 Verificação final:
  - `docker compose exec api uv run pytest`, duas vezes, sem ninguém rodando junto;
  - `ruff`;
  - `npm run check:web`;
  - `npm run test:e2e`;
  - cadastrar à mão os 2 perfis reais (Queridinhos e A Taverna Nerd, com as contas de `../shared/perfis/`) para validar o SC-002;
  - medir SC-001, SC-003 e SC-005 e registrar no fim do `quickstart.md`.

---

## Dependencies & Execution Order

- **Setup (T001–T003) → Foundational (T004–T008) → stories.**
- **US1 (API T009–T011)** é pré-requisito do SPA (T012). **US2 (T013–T015)** pode andar junto
  com a US1 na API, porque os arquivos são separados. Os dois `include_router` em `main.py` são
  uma linha cada.
- **US4 (T017–T018)** depende dos services de perfis e contas. **US3 (T020–T021)** depende do
  `service_perfis` (para o histórico) e dos módulos da T006.
- **O SPA (T012, T016, T019, T022)** vem depois das rotas correspondentes. Os arquivos
  `PerfilDetalhe.tsx` e `client.ts` são compartilhados, então fica um agente só para o SPA.
- **T023** vem depois de tudo; **T024 e T025** por último.

### Parallel Opportunities
- **Fase 2:** T006, T007 e T008 em paralelo com T004 → T005.
- **API:** US1 (T009–T011) ∥ US2 (T013–T015) ∥ US3 (T020–T021, depois do T010).
- **Depois das APIs:** o agente de SPA (T012, T016, T019, T022) ∥ o agente de e2e (T023, escrito
  antes e rodado no fim).

## Implementation Strategy

- **MVP:** Setup, Foundational e US1 (perfis com histórico gravado). Depois vêm a US2 e a US4
  (P1) e, por fim, a US3 (P2).
- **pytest em paralelo:** um agente por vez roda a suíte inteira; os outros rodam só os próprios
  arquivos. Duas suítes simultâneas no mesmo banco de teste travam (visto na 001).
