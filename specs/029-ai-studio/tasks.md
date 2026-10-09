---

description: "Tarefas da feature 029-ai-studio"
---

# Tasks: AI Studio, biblioteca da agência (029-ai-studio)

**Input:** `specs/029-ai-studio/`, com estes documentos:
- `spec.md`, com as Clarifications de 2026-10-09;
- `plan.md`;
- `research.md` (R1 a R13);
- `data-model.md`;
- `contracts/http-api.md`;
- `quickstart.md`.

**Pré-requisitos:**
- 007, 010, 012, 017, 021 e 025 implementadas, com o head em `0023_cadastro_padronizado`.
- A 011 **não** foi implementada. Ela passa para a migration `0027`, depois da `0026_uniao_mercado` da 026 (R11).

**Nomes canônicos:**

| O quê | Nome |
|---|---|
| Migration | `0024_ai_studio` (`down_revision = "0023_cadastro_padronizado"`) |
| Módulo do resolver | `perfis/base.py`, com `resolver(db, item_perfil_id, pedido) -> Perfil \| None` |
| Pacote novo | `estudio/` (`router`, `schemas`), com `GET /api/estudio/resumo` |
| `operationId` novos | os de `contracts/http-api.md`: `*_listar_agencia`, `*_criar_agencia`, `geracoes_pedir_agencia`, `audios_enviar_agencia` e `estudio_resumo` |
| Erros novos | `perfil_base_arquivado` (409) e `perfil_invalido` (400) |
| Campo de pedido | `perfilBaseId`: ausente = o perfil do item; `null` = nenhum; um uuid = aquele perfil |
| Filtro das listas | `perfilId`: ausente = todos; `sem` = sem perfil; um uuid = aquele perfil |
| Aviso da cena | `sem_perfil_base` |
| Rotas da SPA | `/app/estudio/{avatares,cenarios,vozes,produtos,cenas,assets,movimentos}`; nova cena em `/app/estudio/cenas/nova` |

**Testes:** fazem parte desta spec (princípio VI). Rodam com `npm run test:api` e `flock /tmp/sociman-e2e.lock npm run test:e2e`.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Gate e numeração:
  - conferir que `alembic heads` = `0023_cadastro_padronizado`;
  - em `specs/011-roteiros-video-local/` (spec, plan, research, data-model, tasks, quickstart), trocar `0024_roteiros_video_local` por `0027_roteiros_video_local`, com `down_revision = "0026_uniao_mercado"` e o gate T001 da 011 esperando `0024_ai_studio`;
  - em `docs/visao.md`, anotar a ordem 029 → 011;
  - **inventário das regras de "mesmo perfil"** (C3 da análise): `grep -rn "perfil_id !=\|deste perfil\|do perfil\""` em `assets/`, `cenas/`, `produtos/`, `vozes/`, `geracao/`, `ia/`, `marca/` e `anotacoes/`; registrar a lista em `research.md` (R14), com o destino de cada uma (sai, fica ou vira perfil base) e a tarefa que a cobre;
  - **achado de escopo na 011** (C4): anotar no topo de `specs/011-roteiros-video-local/spec.md` e `data-model.md` que, depois da 029, avatar, voz, produto, cena e keyframes do roteiro podem ser de qualquer perfil base; o roteiro continua do perfil do vídeo; rodar o `/speckit-analyze` da 011 antes do implement dela;
  - rodar a base `npm run test:api -- -k "assets or cenas or produtos or vozes or geracao or ia_"` e confirmar que passa.
- [X] T002 [P] `apps/api/tests/integration/estudio_helpers.py` com:
  - `perfil(client, h, slug)`;
  - `item(client, h, tipo, perfil_id|None, **kw)`, que cria pela rota nova da agência;
  - `listar(client, h, rota, **filtros)`;
  - `semear_biblioteca(db, n, perfis)`, que insere em lote por SQL para o teste de desempenho.

---

## Phase 2: Foundational (bloqueia todas as histórias)

- [X] T003 Migration `apps/api/migrations/versions/0024_ai_studio.py`, conforme o data-model:
  - `DROP NOT NULL` em `perfil_id` de `assets`, `cenas`, `produtos`, `vozes`, `images`, `audios`, `geracoes` e `ia_chamadas`;
  - desduplicar os nomes de voz ativos (sufixo " (2)", " (3)"…), com a versão em `entity_versions` (`system:migration`, `details.motivo = "nome_unico_029"`);
  - trocar `uq_vozes_nome` por `UNIQUE (lower(name)) WHERE archived_at IS NULL`;
  - criar `ix_{assets,cenas,produtos,vozes}_lista_agencia (archived_at, updated_at DESC, id)` e `ix_geracoes_alvo`, se ainda não existir;
  - no downgrade, recusar se houver `perfil_id` nulo.
- [X] T004 [P] `apps/api/tests/integration/test_migration_0024.py`:
  - upgrade e downgrade sobre a 0023 com dados;
  - duas vozes "Ana vendas" em perfis diferentes → a mais nova vira "Ana vendas (2)", com a versão gravada;
  - o downgrade recusa com nulo;
  - os itens existentes mantêm o `perfil_id`.
- [X] T005 Modelos:
  - `perfil_id` vira `Mapped[uuid.UUID | None]` em `assets/models.py`, `cenas/models.py`, `produtos/models.py`, `vozes/models.py`, `perfis/models.py` (Image), `geracao/models.py` (Geracao, Audio) e `ia/models.py` (IaChamada);
  - `perfil_id` entra em `__versioned_fields__` de Asset, Cena, Produto e Voz, e sai de `__immutable_fields__` de Cena e Produto (R2);
  - os índices novos ficam declarados nos modelos.
- [X] T006 `perfis/base.py`:
  - `resolver(db, item_perfil_id, pedido)` com os 3 estados (`AUSENTE` sentinela, `None`, uuid);
  - perfil inexistente → 400 `perfil_invalido` (`field`); arquivado → 409 `perfil_base_arquivado`;
  - helper `perfil_ou_none(db, perfil_id)` para o filtro das listas.
- [X] T007 [P] `apps/api/tests/unit/test_perfil_base_resolver.py`: os 3 estados, o perfil arquivado e o inexistente.
- [X] T008 Arquivos sem perfil:
  - `imaging`/upload de imagem e `geracao/audios._gravar` aceitam `perfil_id=None`, com a chave `agencia/imagens/<id>.<ext>` e `agencia/audios/<id>.<ext>`;
  - as chaves existentes não mudam;
  - os links de mídia (`router_midia.py`) não dependem do perfil.
- [X] T009 Schemas de saída:
  - `perfilId: uuid | null` e `perfilNome: str | null` em `Asset`, `AssetSummary`, `Cena`, `Produto`, `Voz`, `Geracao` e `IaChamada`;
  - o `perfilNome` vem de um join único por página, sem N+1.

**Checkpoint:** a migration aplica e os modelos aceitam nulo; o resto do sistema continua igual, com a suíte verde.

---

## Phase 3: User Story 1 — Biblioteca da agência no menu AI Studio (P1) 🎯 MVP

**Goal:** listas da agência por tipo, com filtro de perfil base, e o grupo AI Studio no menu.

**Independent test:** com itens de 2 perfis e um sem perfil, cada lista traz os 3, e o filtro separa cada um.

- [X] T010 [P] [US1] Testes `apps/api/tests/integration/test_agencia_listas.py`:
  - `GET /api/assets` (só `tipo` imagem, sticker, marca d'água e fundo, como a SPA pede, e também por tipo avatar e cenário), `/api/cenas`, `/api/produtos` e `/api/vozes`;
  - o filtro `perfilId` ausente, `sem` e uuid, e um valor inválido → 400;
  - a busca, as tags e os arquivados;
  - o cursor estável;
  - o `perfilNome`.
- [X] T011 [US1] Rotas de lista e de criação da agência em `assets/router.py`, `cenas/router.py`, `produtos/router.py` e `vozes/router.py`:
  - `assets_listar_agencia`, `assets_criar_agencia`, `assets_criar_arquivo_agencia`, `cenas_listar_agencia`, `cenas_criar_agencia`, `produtos_listar_agencia`, `produtos_criar_agencia`, `vozes_listar_agencia` e `vozes_criar_agencia`;
  - o service de cada tipo ganha `listar(db, filtros)` sem perfil obrigatório (o `assets/busca.py` aceita `perfil_id: UUID | Literal["sem"] | None`);
  - a criação recebe `perfil_id: UUID | None`.
- [X] T012 [US1] `estudio/` com `GET /api/estudio/resumo?perfilId=`, que devolve as contagens de ativos por tipo (avatares, cenários, assets, cenas, produtos e vozes). Incluir em `main.py`.
- [X] T013 [P] [US1] `apps/api/tests/integration/test_estudio_resumo.py`: as contagens com e sem perfil, e os arquivados fora.
- [X] T014 [US1] `mcp/mapa.py`: classificar as rotas novas conforme `contracts/http-api.md` §MCP. Atualizar as contagens em `tests/unit/test_mcp_mapa.py` e `tests/integration/test_mcp_leitura.py`.
- [X] T015 [US1] `npm run gen:contract` e os tipos e métodos em `packages/contract/src/client.ts`: `assets.listarAgencia`, `assets.criarAgencia`, `cenas.listarAgencia`, `produtos.listarAgencia`, `vozes.listarAgencia`, `estudio.resumo` etc.
- [X] T016 [US1] SPA, menu e listas:
  - `components/shell/nav.ts`: grupo `{ id: "estudio", label: "AI Studio" }` logo depois de "Perfis", com Avatares, Cenários, Vozes, Produtos, Cenas, Assets e Movimentos;
  - o `navItems`/breadcrumb casa `/app/assets/:id` (pelo tipo), `/app/vozes/:id`, `/app/produtos/:id` e `/app/cenas/:id` com o item do tipo.
- [X] T017 [US1] SPA, componentes das listas:
  - `components/estudio/PerfilBaseFiltro.tsx`: `NativeSelect` com "Todos", "Sem perfil" e os perfis; estado em `useFiltroUrl` (`perfil`); vai na `FilterBar`;
  - refatorar `pages/perfis/tabs/{AssetsTab,CenasTab,ProdutosTab,VozesTab}.tsx` em listas que recebem `perfilFiltro` e, no caso dos assets, `tipos` fixos: `AssetsLista`, `CenasLista`, `ProdutosLista` e `VozesLista`;
  - cada card ou linha mostra o perfil base ("Sem perfil").
- [X] T018 [US1] SPA, páginas:
  - `pages/estudio/{Avatares,Cenarios,Vozes,Produtos,Cenas,Assets}.tsx`: Page, PageHeading, a lista e o "Novo …"; Assets fixa os tipos imagem, sticker, marca d'água e fundo (Clarification 2);
  - `pages/estudio/Movimentos.tsx`: "em breve" (clonagem de movimento, spec 030), sem ação;
  - as rotas em `App.tsx`, lazy por página;
  - remover `pages/estudio/Estudio.tsx`.
- [X] T019 [US1] e2e `e2e/ai-studio.spec.ts` (US1):
  - o grupo AI Studio com os 7 itens;
  - a lista de avatares com 2 perfis e um sem perfil;
  - o filtro "Sem perfil" na URL, que sobrevive ao reload;
  - Movimentos "em breve";
  - o membro vê as listas.
  - Atualizar `e2e/layout.spec.ts`: o grupo "AI Studio" em `GROUPS` e os itens no `OWNER_ITEMS`; sai o "AI Studio" provisório.

**Checkpoint:** o AI Studio lista a biblioteca inteira.

---

## Phase 4: User Story 2 — Criar e gerar com perfil base escolhido (P1)

**Goal:** perfil base opcional na criação, no PATCH e no pedido de geração ou de IA, com o perfil usado gravado.

**Independent test:** um avatar sem perfil gera sem guia; com o perfil base A (proibida "x"), o registro mostra o guia de A e a proibida é tratada.

- [X] T020 [P] [US2] Testes `apps/api/tests/integration/test_perfil_base.py`:
  - criar sem perfil;
  - PATCH do perfil base, versionado e com revert só do dono (o membro muda, mas não reverte);
  - `POST /api/geracoes` com `perfilBaseId` ausente, `null` e B → `geracoes.perfil_id` gravado, e o item continua com A;
  - perfil arquivado → 409;
  - `POST /api/ia/gerar` sobre um asset com perfil base B → `ia_chamadas.perfil_id = B` e `guia_perfil_version`; sem perfil → sem `<guia_perfil>` nem `<perfil>` no `system`;
  - a ficha do produto (012) usa o guia do perfil base;
  - a checagem de identidade (025) usa as proibidas do perfil base;
  - as rotas antigas `POST /api/perfis/{id}/geracoes` continuam: o perfil do caminho é o padrão.
- [X] T021 [US2] `geracao/service.py`:
  - `pedir` e `criar_para_alvo` passam pelo `perfis.base.resolver`;
  - `Geracao.perfil_id` = o perfil usado;
  - a validação de referência (`img.perfil_id != perfil_id`, R8) sai;
  - os aplicadores validam o alvo sem exigir o perfil (`validar_alvo(db, perfil_id|None, alvo_id)` aceita qualquer perfil base);
  - a rota nova `geracoes_pedir_agencia` e a `geracoes_listar_agencia` (por alvo), em `geracao/router.py`;
  - `POST /api/audios` (`audios_enviar_agencia`), em `geracao/router_audios.py`.
- [X] T022 [US2] `ia/service.py` e `ia/prompt` (008/017/023):
  - `perfilBaseId` no `IaGerarIn`;
  - o alvo de asset, cena ou produto não precisa ser do perfil do pedido;
  - o guia, as proibidas e o `<perfil>` vêm do perfil resolvido; sem ele, só a base e as regras do tipo;
  - o `ia_chamadas.perfil_id` anulável;
  - `ia/aplicacao.py:90`: aplicar a sugestão confere só o alvo (tipo e entidade), sem exigir `chamada.perfil_id == alvo.perfil_id`, porque o perfil base pode ter sido trocado só na geração (C1); com teste em T020 (gerar com B num item de A e aplicar → 200);
  - o resumo de custo (`ia/service.py` ~719) usa outer join, com "Sem perfil";
  - os `postagem.*` não mudam.
- [X] T023 [US2] Os aplicadores e motores que leem o guia do perfil (`geracao/aplicadores_avatar.py` Identidade, `produtos/fluxo.py`, `geracao/motor_claude.py`) usam o `perfil_id` da geração, e não o do item.
- [X] T024 [US2] O PATCH de Asset, Cena, Produto e Voz aceita `perfilId` (uuid ou null; inexistente → 400 `perfil_invalido`), versionado. O revert do dono volta o perfil base.
- [X] T025 [US2] SPA:
  - `components/estudio/PerfilBaseField.tsx`, com o texto "Sem perfil base: só as regras do tipo, sem guia" quando vazio;
  - nos formulários de criação dos tipos (`NovoAssetMenu`, nova voz, novo produto, nova cena), o padrão é o filtro da lista;
  - no cabeçalho de detalhe, o perfil base é editável;
  - em `components/geracao/PedirGeracao.tsx`, `pages/assets/kit/PedirPasso.tsx` e nas ações de geração do produto e da voz, o "Perfil base desta geração" vem com o padrão do item e é enviado como `perfilBaseId`;
  - `lib/geracoes.ts` passa a usar `geracoes_pedir_agencia`;
  - `components/ia/IaAssist` envia o `perfilBaseId` do item.
- [X] T026 [US2] e2e (`e2e/ai-studio.spec.ts`, US2):
  - criar um cenário sem perfil e gerar a cena (o aviso aparece);
  - gerar com o perfil B a partir de um cenário de A: o cenário continua A, e a geração mostra B no histórico;
  - mudar o perfil base pelo cabeçalho e reverter.

**Checkpoint:** toda geração grava o perfil base usado (SC-004).

---

## Phase 5: User Story 3 — Usar itens de qualquer perfil e criar no lugar (P1)

**Goal:** a cena aceita itens de qualquer perfil, e o "+ Novo …" em diálogo devolve o item escolhido.

**Independent test:** uma cena com perfil base B usa um cenário de A e um avatar sem perfil; um produto criado pelo diálogo já vem escolhido.

- [X] T027 [P] [US3] Testes `apps/api/tests/integration/test_cena_cruzada.py`:
  - a cena B com cenário A, avatar sem perfil e produto aprovado de A → 201, e o prompt com os três;
  - os padrões e as proibidas vêm de B; sem perfil base, o aviso `sem_perfil_base`, sem padrões e sem proibidas;
  - as recusas que continuam (tipo errado, produto não aprovado, variante sem recorte);
  - o `PUT /api/conteudos/{id}/cenas` do perfil C com a cena B → ok, com o histórico;
  - "onde é usado" do cenário A lista a cena B com o perfil.
- [X] T028 [US3] Mudanças nas cenas:
  - `cenas/service.py`: tirar as checagens de perfil (`:136` asset, `:170` produto);
  - `padroes.efetivos` e `proibidas_do_perfil` com `cena.perfil_id` anulável;
  - o aviso `sem_perfil_base` em `cenas/avisos.py`;
  - em `cenas/tomadas.py`, `cenas/usos.py` e `cenas/usos_assets.py`, o perfil anulável e os usos de todos os perfis;
  - em `assets/usos.py` e nos provedores de `geracao/uso.py`, listar com o nome do perfil de cada uso (FR-015).
- [X] T028a [US3] Regras de "mesmo perfil" da 025 (C2):
  - `assets/service_padrao.py`: a voz padrão do avatar aceita voz de qualquer perfil base (continua exigindo aprovada, não arquivada, não revogada e com referência; a mensagem deixa de dizer "deste perfil");
  - a prova do consentimento (imagem ou áudio) pode ser de qualquer perfil base;
  - `vozes/service.py`: a gravação da voz pode ser um áudio de qualquer perfil base;
  - testes em `tests/integration/test_vozes.py` e `test_revogacao.py` (voz de B como padrão de avatar de A; prova de outro perfil; a revogação continua apagando tudo).
- [X] T029 [US3] SPA, criação no lugar:
  - `components/estudio/NovoItemDialog.tsx` para avatar, cenário e produto, que reaproveita os formulários de criação de cada tipo, nasce com o perfil base da cena e chama `onCriado(id)`;
  - nos seletores da nova cena e da edição (`pages/cenas/*`), o "+ Novo avatar", o "+ Novo cenário" e o "+ Novo produto";
  - o diálogo fora do `<form>` da cena: o estado preenchido não muda;
  - os seletores listam a biblioteca da agência com o perfil base ao lado do nome;
  - a nova cena vive em `/app/estudio/cenas/nova`;
  - a cena mostra o aviso `sem_perfil_base` ("Sem perfil base: sem padrões nem guia") quando não tem perfil (FR-012).
- [X] T030 [US3] e2e (`e2e/ai-studio.spec.ts`, US3):
  - a cena B com o cenário A;
  - "+ Novo cenário" cria e volta escolhido, com o título da cena preservado;
  - cancelar o diálogo não cria nada.

**Checkpoint:** a queixa do dono está resolvida (SC-001, SC-003).

---

## Phase 6: User Story 4 — A página do perfil sem as abas de criação (P2)

**Goal:** a página do perfil perde as 4 abas e ganha o card "Ver no AI Studio"; os links antigos redirecionam.

**Independent test:** `?aba=vozes` leva à lista de vozes filtrada pelo perfil.

- [X] T031 [US4] SPA:
  - `pages/perfis/PerfilDetalhe.tsx`: remover as abas Assets, Cenas, Produtos e Vozes; o card "Ver no AI Studio" com as contagens do `estudio.resumo`;
  - `?aba=assets|cenas|produtos|vozes` → `<Navigate>` para `/app/estudio/<tipo>?perfil=<id>` (`assets` → `/app/estudio/assets`);
  - `/app/estudio` → `/app/estudio/avatares`, com o perfil lembrado;
  - `/app/perfis/:id/cenas/nova` → `/app/estudio/cenas/nova?perfil=<id>`;
  - trocar os links internos que apontam para as abas antigas: `VozDetalhe`, `ProdutoPage`, `CenaDetalhe`, `CenaHistorico`, `AssetDetalhe`, `AssetHistorico`, `lib/anotacoes.ts` e `App.tsx`.
- [X] T032 [US4] `marca/service_kit.py` e o seletor do kit (`pages/perfis/tabs/MarcaTab.tsx`):
  - a imagem de fundo e a marca d'água vêm da biblioteca da agência (`assets.listarAgencia` com tipo);
  - a checagem de "mesmo perfil" sai;
  - o uso no kit continua bloqueando o arquivar (com teste em `tests/integration/test_kit_biblioteca.py`).
- [X] T033 [US4] e2e:
  - `e2e/ai-studio.spec.ts` US4: os redirecionamentos e o card do perfil;
  - ajustar `e2e/assets.spec.ts`, `assets-escala.spec.ts`, `cenas.spec.ts`, `produtos.spec.ts`, `cadastro-padronizado.spec.ts` e `geracao.spec.ts` para entrar pelo AI Studio, em vez de `?aba=…`.

---

## Phase 7: User Story 5 — Agentes e leitura continuam funcionando (P3)

**Goal:** o MCP lê a biblioteca pelas duas rotas; as escritas continuam fora.

- [X] T034 [P] [US5] `apps/api/tests/integration/test_mcp_leitura.py` (acréscimo):
  - `assets_listar_agencia` com `perfilId=A` dá os mesmos itens que a leitura antiga por perfil;
  - as escritas novas → 403 (`escopo_mcp`/`somente_humano`);
  - a lista de propostas (`anotacoes/service.py`) aceita o filtro "Sem perfil" e usa o perfil base **atual** do alvo, com teste, e a SPA de Propostas ganha a opção (C8);
  - `docs/guia-mcp-openclaw.md`: orientar os agentes (ex.: shop-roteirista) a usar as listas da agência (`produtos_listar_agencia` etc.), porque a rota antiga por perfil só traz o perfil base (C5).
- [X] T035 [US5] Marcar as rotas por perfil como `deprecated=True` (`contracts/http-api.md`), com o mesmo comportamento, e com um teste de regressão de que elas respondem igual à rota nova filtrada.
- [X] T036 [P] [US5] `tests/unit/test_constitution_guards.py` (seção spec 029):
  - nenhum módulo novo (`estudio/`, `perfis/base.py`) importa `publicacao` nem `httpx`;
  - as rotas novas sem "tiktok" ou "youtube".

---

## Phase 8: Polish & Cross-Cutting

- [X] T037 [P] Desempenho: `apps/api/tests/integration/test_estudio_desempenho.py` semeia 5 mil assets em 3 perfis e mais os sem perfil, e exige < 1 s na lista sem filtro, com `perfilId=sem` e com perfil (SC-006).
- [X] T038 [P] Agência (013): conferir que `agencia/aplicar.py` e `conciliar.py` continuam criando com o perfil da importação (sem mudança de comportamento), com teste existente verde.
- [X] T039 Docs:
  - `CLAUDE.md`: a seção "AI Studio (desde a spec 029)", com o perfil base anulável, o `perfis/base.resolver`, as rotas da agência, as obsoletas, o prefixo `agencia/` no MinIO, a voz única na agência, o menu, os redirecionamentos e a ordem 029 → 011 (0024, 0026 da 026, 0027); tirar a menção do `/app/estudio` provisório;
  - `docs/visao.md`: a 029 implementada.
- [X] T040 Verificação final:
  - `npm run test:api` inteiro, o ruff, `npm run gen:contract && npm run check:web`, com a regressão obrigatória das regras que não mudam (FR-023): `test_revogacao`, `test_geracao_escolher`, `test_produtos*`, `test_geracao_limpeza` e `test_constitution_guards`;
  - o e2e inteiro com trava;
  - no dev: backup `pre-0024.dump`, `alembic upgrade head` e o restart de api, gerador e agendador;
  - o quickstart §2 com o dono.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2** bloqueia tudo. A T003 vem antes da T005; a T006 vem antes de T021, T022 e T024.
- **US1** (T010–T019) primeiro, porque as listas são a base da SPA das outras histórias.
- **US2** depende de T006 e T009. **US3** depende da US1, por causa dos seletores da agência. US2 e US3 podem andar em paralelo na API, porque mexem em arquivos diferentes: `geracao/` e `ia/` na US2, `cenas/` na US3.
- **US4** depende da US1, por causa das rotas do AI Studio, e da US3, por causa da nova cena em `/app/estudio`.
- **US5** pode rodar logo depois da T014.
- Os arquivos compartilhados (`assets/service.py`, `mcp/mapa.py` e `client.ts`) são editados em série: nunca dois agentes ao mesmo tempo.

### Parallel Opportunities
- Os testes [P] de cada fase (T004, T007, T010, T013, T020, T027, T034, T036 e T037) podem ser escritos juntos.
- A SPA (T016–T018, T025, T029 e T031) pode ir para um subagente de frontend depois do T015, como na 012 e na 025.

## Implementation Strategy
1. **MVP:** Phases 1, 2 e 3 (US1): a biblioteca no menu, só listando. Validar com o dono.
2. Depois a US2 (o perfil base na geração) e a US3 (a cena cruzada e a criação no lugar), que fecham a queixa do dono.
3. Depois a US4 (limpar a página do perfil) e a US5 (as garantias dos agentes).
4. Por fim, o polimento e a migration no dev.
