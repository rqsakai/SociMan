---

description: "Tarefas da feature 014-central-de-conteudos"
---

# Tasks: Central de conteúdos, aprovação e agendamento (014-central-de-conteudos)

**Input**: `specs/014-central-de-conteudos/` (spec, plan, research R1–R14, data-model, contracts/http-api.md, quickstart, open-questions resolvidas)

**Decisões do dono (2026-09-29):** Q1 = A (dono e membro agendam, reagendam e cancelam o que **já está aprovado**; aprovar e recusar só dono; membro diante de item não aprovado vê "Pedir aprovação"; na 015 os modos automáticos ficam restritos a donos, constitution 4.0.0), Q2 = A (editar textos depois da aprovação **não** desfaz a aprovação; tudo no histórico), Q3 = C com padrão de 30 min (`contas.intervalo_min_minutos`, 0..1.440, só dono edita, com histórico da conta; a **sequência pula** o conflito, o **individual avisa** com 409 `intervalo_conflito` e deixa manter com `ignorarIntervalo: true`), Q4 = A (vídeo próprio de 1 s a 10 min, até 2 GB, qualquer proporção, aviso "não é vertical").

**Nomes canônicos** (valem os documentos do plano): pacote novo `sociman_api/conteudos/` (`models`, `consulta`, `capacidades`, `sequencia`, `video_proprio`, `service`, `schemas`, `router`, `router_video`); `postagem/` evolui para destino e agendamento (tabela `postagens`, classe `Postagem`, `entity_type = "postagem"` mantidos); `entity_type` novo `conteudo`; enums `conteudo_origem`, `destino_estado`, `agendamento_modo`; migration `0009_central_conteudos` (`down_revision = "0008_assistente_ia"`); recursos da API `conteudos`, `destinos`, `agendamentos`, `contas_modos`; erros novos `conteudo_nao_pronto`, `nao_aprovado`, `aprovacao_necessaria`, `modo_indisponivel`, `conta_em_atencao`, `conta_invalida`, `destino_exists`, `intervalo_conflito`, `previa_desatualizada`; `MidiaKind` novo `conteudo_video`; notificações novas `aprovacao_pedida`, `aprovacao_respondida`; SPA `/app/conteudos` e `/app/conteudos/:id`, componentes em `components/conteudos/`, `DestinoPanel` no lugar do `PostagemSection`.

**Tests**: OBRIGATÓRIOS (constitution, princípio VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec api uv run ruff check .`;
- `npm run gen:contract && npm run check:web` (contrato regenerado, CSP inalterada, segredos);
- e2e na stack isolada, **sempre com trava**: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/conteudos.spec.ts]` (armadilha 18: nunca dois e2e ao mesmo tempo);
- nenhum teste fala com rede social nem com a Anthropic de verdade (Claude falso da 008).

**Restrições do data-model (citadas literalmente; valem na migration, nos modelos e nos serviços):**
- `conteudos.id`: "na origem `corte`, **igual a `cortes.id`**"; `origem`: "enum `conteudo_origem` (`corte`, `video_proprio`)"; `corte_id`: "uuid null UNIQUE FK → cortes.id", "origem `corte` ⇔ preenchido e `= id`"; `titulo`: "text not null default ''", "até 100"; `video_key`: "text null UNIQUE", "só `video_proprio`: `conteudos/{id}/video.<ext>` no bucket de vídeos"; `video_bytes`: "até 2 GB"; `archived_at`: "na origem corte, `archived_at` fica null (vale o do corte)".
- `ck_conteudos_origem`: "`(origem = 'corte' AND corte_id = id AND video_key IS NULL AND archived_at IS NULL)` **ou** `(origem = 'video_proprio' AND corte_id IS NULL AND video_key IS NOT NULL AND poster_key IS NOT NULL AND duration_ms IS NOT NULL)`"; `ck_conteudos_titulo`: "`char_length(titulo) <= 100`"; índices "`ix_conteudos_perfil_created (perfil_id, created_at DESC, id DESC)` e `ix_conteudos_created (created_at DESC, id DESC)`"; "invariante (teste): todo `cortes.id` tem uma linha `conteudos` com o mesmo id".
- Snapshot de `conteudos`: "`titulo` e `archived`. `origem`, `corte_id` e as colunas do arquivo são `__immutable_fields__` (informativas; a reversão as ignora)". Campos derivados "em `conteudos/consulta.py`, nunca gravados".
- `postagens.conteudo_id`: "**novo**; substitui `corte_id` (removida)"; `conta_id`: "**não muda depois de criado** (aprovação é por conta)"; `estado`: "enum **`destino_estado`**", "`pendente` (padrão), `aprovacao_pedida`, `aprovado`, `agendado`, `postado`, `rascunho_criado`, `publicado`, `falhou`"; `modo`: "enum `agendamento_modo` (`lembrete`, `criar_rascunho`, `publicar`, `rascunho_e_publicar`) not null default `lembrete`", "só `lembrete` na 014 (CHECK)"; `antecedencia_min`: "só com `rascunho_e_publicar` (0..10.080)"; `planned_at`: "obrigatório em `agendado`"; `lembrado_em`: "zera ao mudar `planned_at`"; `falha_motivo`: "reservado ao executor da 015 (sempre null na 014)"; `aprovado_video_ref`: "o vídeo final no momento da aprovação (`videoMudou`)"; `pedido_nota`: "até 500"; `recusa_motivo`: "1..500; visível até a próxima aprovação".
- Regras de `postagens`: "`uq_postagens_conteudo_conta_ativa (conteudo_id, conta_id) WHERE archived_at IS NULL` → 409 `destino_exists` (substitui `uq_postagens_corte_conta_ativa`)"; "`ck_postagens_agendado_planned` (da 006): `estado <> 'agendado' OR planned_at IS NOT NULL`"; "`ck_postagens_aprovado`: `estado NOT IN ('aprovado','agendado','postado','rascunho_criado', 'publicado','falhou') OR aprovado_em IS NOT NULL`"; "`ck_postagens_pedido`: `estado <> 'aprovacao_pedida' OR pedido_em IS NOT NULL`"; "`ck_postagens_antecedencia`: `antecedencia_min IS NULL OR (modo = 'rascunho_e_publicar' AND antecedencia_min BETWEEN 0 AND 10080)`"; "`ck_postagens_textos_nota`: `char_length(pedido_nota) <= 500` e `char_length(recusa_motivo) BETWEEN 1 AND 500` (quando não null)"; **guardas do princípio I** "`ck_postagens_modo_014`: `modo = 'lembrete' AND antecedencia_min IS NULL`" e "`ck_postagens_estados_015`: `estado NOT IN ('rascunho_criado','publicado','falhou')`"; índices "`ix_postagens_estado_planned` (da 006), `ix_postagens_conteudo (conteudo_id)` e `ix_postagens_conta_agenda (conta_id, planned_at) WHERE archived_at IS NULL AND estado = 'agendado'`".
- Snapshot do destino: "`conta_id`, `titulo`, `descricao`, `hashtags`, `estado`, `modo`, `antecedencia_min`, `planned_at`, `posted_url`, `aprovado_por`, `aprovado_em`, `pedido_nota`, `recusa_motivo` e `archived`"; a reversão "usa os padrões (`modo = lembrete`, aprovação vazia) e **nunca** restaura uma aprovação num destino que não está aprovado hoje". `details.acao`: "`aprovado`, `aprovacao_pedida`, `recusado`, `agendado`, `reagendado`, `agendamento_cancelado`, `cancelado_por_arquivo`, `postado` (da 006), e `lote` quando a ação veio de uma rota em lote (com `details.loteId`, um uuid por chamada)"; "Um agendamento ou reagendamento mantido a menos do intervalo mínimo da conta leva `details.intervaloIgnorado = true`".
- `contas.intervalo_min_minutos`: "smallint not null default 30"; "`ck_contas_intervalo_min`: `intervalo_min_minutos BETWEEN 0 AND 1440`"; conflito "`abs(a - b) < greatest(intervalo_min_minutos, 1)` minutos (com 0, só o mesmo minuto conflita)", considerando "os destinos ativos da conta com `estado = 'agendado'` (índice `ix_postagens_conta_agenda`), menos o próprio destino"; versões antigas: "a reversão para uma delas **mantém o valor atual**"; "mudar o valor não altera nenhum agendamento existente".
- `ia_chamadas.conteudo_id`: "uuid null FK → conteudos.id", "preenchida em toda chamada `postagem.*`; na migração, `= corte_id`"; "Índice `ix_ia_chamadas_conteudo (conteudo_id, created_at DESC)`".
- Notificações: `aprovacao_pedida` "para os donos ativos", "`dedupe_key = aprovacao_pedida:<destino>:<version>`"; `aprovacao_respondida` "para quem pediu, na aprovação ou na recusa (com o motivo no corpo)", "`dedupe_key = aprovacao_respondida:<destino>:<version>`"; "`hora_de_postar` muda só o link (`/app/conteudos/{conteudoId}?conta={contaId}`)".
- Migração: "Nenhuma linha de `entity_versions` é escrita nem alterada"; downgrade "recusa com `video_proprio` presente"; os valores novos de `notificacao_tipo` seguem "o padrão da 0007 (`envio_momentos`): apaga as notificações desses dois tipos e recria o enum sem eles".

**Arquivos compartilhados: SÓ ACRÉSCIMO** (bloco novo ao lado dos vizinhos, sem reordenar): `apps/api/src/sociman_api/main.py`, `apps/api/migrations/env.py`, `apps/api/tests/conftest.py`, `apps/api/src/sociman_api/agendador.py` (só `_registrar_modelos`), `apps/web/src/App.tsx`, `apps/web/src/components/shell/nav.ts`, `e2e/helpers.ts`, `CLAUDE.md`, `docs/visao.md`. `packages/contract/**` é **gerado** (armadilha 6): em conflito, rebase e `npm run gen:contract` de novo.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US5 da spec

---

## Phase 1: Setup (linha de base e backup)

- [X] T001 Linha de base no dev, **antes** de subir código novo (quickstart §0): `docker compose exec api uv run alembic heads` → `0008_assistente_ia`; anotar `select estado, archived_at is null, count(*) from postagens group by 1,2;`, `select count(*) from cortes;`, `select count(*) from contas;`, `select count(*) from ia_chamadas where corte_id is not null;` e `select count(*), md5(string_agg(id::text, ',' order by id)) from entity_versions;`.
- [X] T002 **Backup do banco de dev** antes da migration: `mkdir -p /media/sakai/BACKUP/tiktok/sociman/backups` e `docker compose exec -T postgres pg_dump -U sociman -Fc sociman > /media/sakai/BACKUP/tiktok/sociman/backups/pre-0009.dump` (HD, fora do git e do MinIO; se o HD estiver sem o sentinela `.sociman-volume`, usar o scratchpad da sessão). Conferir tamanho > 0 e `docker compose exec -T postgres pg_restore -l < …/pre-0009.dump | grep -c "TABLE DATA"` > 0. **Nunca no repositório.** Apagar só no T071.

---

## Phase 2: Foundational (modelo, migration, consulta, capacidades, guardas)

**⚠️ Bloqueia todas as histórias.**

- [X] T003 Criar `apps/api/src/sociman_api/conteudos/__init__.py` (docstring: "central de conteúdos; nada aqui fala com rede social") e `conteudos/models.py` com `ConteudoOrigem` (`corte`, `video_proprio`), `Modo` (`agendamento_modo`: `lembrete`, `criar_rascunho`, `publicar`, `rascunho_e_publicar`) e `Conteudo` (AuditMixin + `_Versioned`, `__versioned_fields__ = ("titulo", "archived")`, `__immutable_fields__` com `origem`, `corte_id` e as colunas do arquivo), com as colunas, o `ck_conteudos_origem`, o `ck_conteudos_titulo` e os índices citados acima.
- [X] T004 Em `apps/api/src/sociman_api/postagem/models.py`, a `Postagem` vira o destino (docstring registra "Postagem = destino, conteúdo × conta"): `DestinoEstado` (`destino_estado`, sai `postagem_estado`), `conteudo_id` no lugar de `corte_id`, `modo`, `antecedencia_min`, `falha_motivo`, aprovação, pedido e recusa; todos os CHECKs e índices citados acima (inclusive `ck_postagens_modo_014` e `ck_postagens_estados_015`); `__versioned_fields__` com o snapshot citado. Ajustar `postagem/service.py`, `postagem/lembretes.py`, `postagem/router.py` e `cortes/service.py` **só o mínimo** para o código continuar compilando e as rotas da 006 continuarem respondendo (o `conteudo_id` do destino é o `corte_id`, R1; `rascunho` → `pendente`); a remoção das rotas é o T052.
- [X] T005 [P] Em `apps/api/src/sociman_api/perfis/models.py`, `Conta.intervalo_min_minutos` (smallint, not null, default e server_default 30) com o `ck_contas_intervalo_min`, e o campo em `Conta.__versioned_fields__` (acréscimo no fim da tupla).
- [X] T006 [P] Em `apps/api/src/sociman_api/ia/models.py`, `IaChamada.conteudo_id` (FK `conteudos.id`, null) e `ix_ia_chamadas_conteudo`; em `apps/api/src/sociman_api/notificacoes/models.py`, os tipos `aprovacao_pedida` e `aprovacao_respondida`.
- [X] T007 Criar `apps/api/migrations/versions/0009_central_conteudos.py` (`revision = "0009_central_conteudos"`, `down_revision = "0008_assistente_ia"`), numa transação, na ordem do data-model ("Migração dos dados da 006", passos 1 a 7 e 5a) e de R2: `conteudo_origem` + `conteudos` (uma linha por corte, arquivados inclusive, `titulo = COALESCE(NULLIF(openshorts_title,''), NULLIF(hook_text,''), original_filename)` cortado em 100, `created_at`/`created_by` do corte); `postagens.conteudo_id` = `corte_id`, `NOT NULL`, FK, troca do índice único, `DROP corte_id`; `ALTER COLUMN estado TYPE destino_estado USING CASE` (`rascunho → pendente`; em `agendado`/`postado`, `aprovado_em = updated_at`, `aprovado_por = COALESCE(updated_by, created_by)`); colunas novas, `agendamento_modo` com `modo = 'lembrete'`, CHECKs e índices; `ia_chamadas.conteudo_id = corte_id` + índice; `contas.intervalo_min_minutos` default 30 + CHECK; `ALTER TYPE notificacao_tipo ADD VALUE` (dois valores, não usados na mesma transação). `downgrade` (docstring "só dev"): recusa com `video_proprio` presente; senão volta `corte_id`, mapeia `pendente`/`aprovacao_pedida`/`aprovado` → `rascunho`, remove colunas, CHECKs, índices, `conteudos`, os enums novos e `contas.intervalo_min_minutos`, e recria `notificacao_tipo` sem os dois valores (padrão da 0007).
- [X] T008 Acréscimos: `apps/api/migrations/env.py` (import de `conteudos.models`); `apps/api/tests/conftest.py` (`_TABLES += ("conteudos",)` num bloco "Spec 014"); `apps/api/src/sociman_api/agendador.py::_registrar_modelos` (import de `conteudos.models`; **nenhuma trilha nova**).
- [X] T009 Criar `apps/api/tests/integration/test_migration_0009.py` (como `test_migration_0008.py`): descer a `0008_assistente_ia`, semear dados da 006 (cortes em `revisao` e `pronto`, um arquivado; postagens `rascunho`, `agendado`, `postado` e uma arquivada; uma `ia_chamadas` com `corte_id`; versões em `entity_versions`), subir e conferir: uma linha `conteudos` por corte com `id = corte_id`; o mapa de estados e `aprovado_em/por`; `modo = lembrete`; `conteudo_id` nas postagens e em `ia_chamadas`; `intervalo_min_minutos = 30` nas contas; **`entity_versions` idêntica** (contagem e hash); os CHECKs recusam `modo <> 'lembrete'` e `estado = 'publicado'`. Descer de novo: `rascunho` volta, contagens iguais às de antes, e com um `video_proprio` o downgrade recusa. Rodar também `test_migration_0006.py` e `test_migration_0008.py` e ajustar os que sobem para `head` (agora `0009`), sem mudar o que verificam.
- [X] T010 Em `apps/api/src/sociman_api/conteudos/service.py`, `criar_para_corte(db, corte)` (mesmo `id`, título pela regra da migration, versão `created`), chamado **no mesmo flush** em `apps/api/src/sociman_api/cortes/service.py::create_corte` e em `apps/api/src/sociman_api/envios/importacao.py`. Testes de invariante (todo corte tem conteúdo com o mesmo id) em `apps/api/tests/integration/test_cortes.py` e `test_importacao.py` (o `c0["postagens"]` do `test_importacao` passa a `destinos` no T045).
- [X] T011 Criar `apps/api/src/sociman_api/conteudos/consulta.py` com a **única** definição das expressões derivadas (data-model, "Campos derivados" e "Estado efetivo"): `situacao`, `arquivado`, `poster_key`, `duration_ms`, `video_ref` por `LEFT JOIN cortes`; o estado efetivo do destino na ordem "`arquivado` → `em_revisao` → `atencao` → `atrasado` → `a_postar` → estado gravado (`pendente` aparece como `pronto`)", com `motivoAtencao`, usado no `WHERE` e no `SELECT`; `sem_conta`.
- [X] T012 [P] Criar `apps/api/src/sociman_api/conteudos/capacidades.py` (R4): `CAPACIDADES` por `Platform` com os motivos em pt-BR da tabela de R4 e `modos_da_conta(conta) -> list[ModoInfo]` com as três camadas; na 014 só `lembrete` disponível, e nenhum modo (nem lembrete) para conta arquivada, `pausada` ou `encerrada`. Teste `apps/api/tests/unit/test_capacidades.py` (**guarda 2**: para cada `Platform` e cada `ContaStatus`, no máximo `lembrete` disponível e todo indisponível com motivo).
- [X] T013 [P] Criar `apps/api/src/sociman_api/conteudos/sequencia.py` só com `conflitos(horario, ocupados, intervalo_min) -> list` (regra `abs(a - b) < max(intervalo, 1 min)`), pura, e `apps/api/tests/unit/test_sequencia.py` com os casos de intervalo 30, 0 (só o mesmo minuto) e 1.440. O planejador entra no T055.
- [X] T014 Guardas do princípio I e do VII em `apps/api/tests/unit/test_constitution_guards.py`, seção "spec 014" (plan, "Guardas"): (1) toda rota de `/api/conteudos`, `/api/destinos` e `/api/agendamentos` tem `operationId` com o prefixo do recurso e nenhuma é DELETE; (5) **AST**: nenhum arquivo de `src/` atribui `rascunho_criado`, `publicado` ou `falhou` a um estado (lista de lugares permitidos **vazia**), e o guarda de `postado` continua só com `postagem/service.py::marcar_postado`; (6) `trilhas_padrao()` tem exatamente `{sync, openshorts, importacao, lembretes}`; (7) `test_listas_do_guarda_nao_encolheram` inalterado. Os guardas 3, 4 e 8 ficam no T044.
- [X] T015 Schemas base: `apps/api/src/sociman_api/conteudos/schemas.py` (`Origem`, `Situacao`, `ConteudoItem`, `Conteudo`, `Atalhos`) e `apps/api/src/sociman_api/postagem/schemas.py` (`DestinoEstado`, `EstadoEfetivo`, `Modo`, `ModoInfo`, `ContaRef` com `status`, `DestinoResumo`, `Destino`, `Textos`, `LoteResultado`, `SlotSequencia`, `Previa` com `intervaloMin`, `ConflitoIntervalo`), exatamente como `contracts/http-api.md` → Tipos (camelCase).

**Checkpoint:** `npm run test:api` verde (a 006 e a 008 continuam passando com as rotas antigas), `alembic upgrade head` e `downgrade 0008_assistente_ia` limpos na stack efêmera.

---

## Phase 3: User Story 1 - Ver tudo o que pode ser publicado, num lugar só (Priority: P1) 🎯 MVP

**Goal**: tela Conteúdos com todos os vídeos publicáveis, estado por conta, filtros na URL, atalhos com contagem e cursor.

**Independent Test**: com os cortes do dev em 2 perfis, filtrar "A Taverna Nerd · prontos sem agendamento" e ver exatamente os prontos sem postagem agendada (quickstart §1).

### Tests for User Story 1

- [X] T016 [P] [US1] `apps/api/tests/integration/test_conteudos.py`: lista paginada dos mais recentes; cada filtro (`perfilId` repetível, `contaId`, `plataforma`, `estado` repetível e `sem_conta`, `origem`, `agendadoDe/Ate`, `criadoDe/Ate`, `q` nos títulos do conteúdo, do destino, do gancho e do OpenShorts); cada `atalho` e `ordem=agenda`; cursor sem repetir nem pular linhas quando entram cortes novos no meio; 400 `validation_error` com cursor inválido e período invertido; `GET /resumo` igual à contagem de cada atalho; estado efetivo igual no filtro e na saída (`a_postar`, `atrasado` e `atencao` com `planned_at` manipulado); detalhe, `PATCH` do título (409 `version_conflict`; 409 `conflict` arquivado), `archive`/`restore` pela regra do corte na origem corte, `versions`, `revert` (membro 403).
- [X] T017 [P] [US1] `apps/api/tests/integration/test_escala_conteudos.py` (como o `assets-escala` da 007): semear 500 conteúdos e 1.000 destinos, medir 30 chamadas de `GET /api/conteudos` com filtros combinados e conferir **p95 < 200 ms** no servidor e nenhuma consulta N+1 (contador de statements) (SC-006).

### Implementation for User Story 1

- [X] T018 [US1] Em `apps/api/src/sociman_api/conteudos/service.py`: `list_conteudos` (filtros, atalhos com as regras de `consulta.py`, cursor opaco base64 de `[chave, id]`, `limit` 1..100, `total` pelo `COUNT` sem o cursor, destinos resumidos numa segunda consulta `WHERE conteudo_id IN (…)`), `resumo`, `get`, `update_titulo`, `archive`/`restore` (origem corte delega ao service do corte), `versions`, `revert` (título e arquivamento; a exceção herdada da 006 fica no docstring).
- [X] T019 [US1] Criar `apps/api/src/sociman_api/conteudos/router.py` com `conteudos_list`, `conteudos_resumo`, `conteudos_get`, `conteudos_update`, `conteudos_archive`, `conteudos_restore`, `conteudos_versions`, `conteudos_revert` (`RequireOwner`), como o contrato; incluir no `apps/api/src/sociman_api/main.py` (acréscimo).
- [X] T020 [US1] `npm run gen:contract` (OpenAPI → `packages/contract`) e `npm run check:contract` sem divergência.
- [X] T021 [P] [US1] `apps/web/src/lib/conteudos.ts`: queries e chaves do TanStack (`useConteudos` com os `searchParams` como chave, `useResumo`, `useConteudo`), rótulos em pt-BR de `Situacao`, `EstadoEfetivo`, `Origem` e `Modo`.
- [X] T022 [P] [US1] `apps/web/src/components/data-table/DataTable.tsx`: prop `manual` (desliga ordenação, filtro e paginação do cliente, sem mudar o comportamento atual quando ausente) e `components/data-table/CursorPagination.tsx` ("Carregar mais"); exportar em `components/data-table/index.ts`.
- [X] T023 [P] [US1] `apps/web/src/components/conteudos/{EstadoBadge,DestinoChips,FiltrosConteudos,AtalhosConteudos}.tsx`: chip por conta com estado efetivo e data (APP_TZ, `lib/tz.ts`); filtros com `NativeSelect` e `Field` (os e2e dependem do `<select>` nativo) lidos e gravados em `useSearchParams`; atalhos com a contagem do `resumo`.
- [X] T024 [US1] `apps/web/src/pages/conteudos/Conteudos.tsx` (atalhos, filtros, `DataTable manual` com miniatura, título, perfil, origem, duração, chips e "Carregar mais"; seleção em lote com a barra, cujas ações entram em US2–US4) e `pages/conteudos/ConteudoDetalhe.tsx` (player por `/api/midia/links`, título editável, origem com link para o corte, uma aba por conta com `?conta=`, "Adicionar conta", histórico com `VersionHistory`; o painel de cada aba entra no T039). Rotas `/app/conteudos` e `/app/conteudos/:id` em `apps/web/src/App.tsx` e o item "Conteúdos" entre "Envios" e "Calendário" em `components/shell/nav.ts` (acréscimos).
- [X] T025 [US1] `e2e/conteudos.spec.ts` (novo), bloco US1: lista com os cortes semeados, filtro de perfil + atalho "Prontos sem agendamento", URL com os filtros (recarregar e voltar mantêm), busca, "Carregar mais" sem repetir, clique abre o detalhe. Rodar com `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/conteudos.spec.ts`.

**Checkpoint:** US1 funciona sozinha (lista e detalhe só de leitura, com os destinos migrados da 006).

---

## Phase 4: User Story 2 - Aprovar para uma conta (Priority: P1)

**Goal**: donos aprovam e recusam (com motivo); membros pedem aprovação; lote; tudo no histórico e no sino.

**Independent Test**: membro pede aprovação de 3 cortes; dono aprova 2 e recusa 1 com motivo; estados e histórico corretos (quickstart §2).

### Tests for User Story 2

- [X] T026 [P] [US2] `apps/api/tests/integration/test_destinos.py`: `POST /api/conteudos/{id}/destinos` (201 `pendente`; 400 `conta_invalida` para conta de outro perfil ou arquivada; 409 `destino_exists`; 409 `conflict` com conteúdo arquivado); `PATCH` dos textos em `aprovado` e `agendado` **não** muda o estado (Q2) e grava versão; pedir aprovação (só de `pendente`; notifica cada dono ativo, `dedupe_key` certo); aprovar (dono; 409 `conteudo_nao_pronto` com corte em revisão; limpa pedido e recusa; `aprovado_video_ref`); recusar (dono; 400 sem motivo; 409 em `agendado`; volta a `pendente` com o motivo visível; notifica quem pediu); `postado` só de `aprovado`/`agendado`; `videoMudou` quando o `result_key` do corte muda depois da aprovação; lote aprovar e pedir (cria o destino que falta, `SAVEPOINT` por item, inelegíveis em `falhas`, `details.loteId`, limite 100); membro 403 em aprovar, recusar, lote aprovar e reverter; `revert` nunca restaura aprovação nem `postado`, inclusive a partir de uma versão da 006 sem os campos novos.

### Implementation for User Story 2

- [X] T027 [US2] Em `apps/api/src/sociman_api/postagem/service.py`: `add_destino`, `update_textos` (com o campo `ia` da 008), `pedir_aprovacao`, `aprovar`, `recusar`, `archive`/`restore`, `versions`, `revert` (regras de R3 e R5; `check_version` e `history.record` com `details.acao` em cada uma) e `marcar_postado` evoluído **no mesmo lugar** (guarda de `postado`).
- [X] T028 [US2] Em `postagem/service.py`, `lote_aprovar` e `lote_pedir_aprovacao`: trava `FOR UPDATE` em ordem de id, `db.begin_nested()` por item, uma versão por destino com `details.acao = "lote"` e `details.loteId`.
- [X] T029 [US2] Notificações `aprovacao_pedida` (donos ativos) e `aprovacao_respondida` (quem pediu) com os títulos, links e `dedupe_key` do data-model, pelo módulo `apps/api/src/sociman_api/notificacoes/`.
- [X] T030 [US2] Em `apps/api/src/sociman_api/postagem/router.py`: `conteudos_add_destino`, `destinos_get`, `destinos_update`, `destinos_pedir_aprovacao`, `destinos_aprovar` (`RequireOwner`), `destinos_recusar` (`RequireOwner`), `destinos_marcar_postado`, `destinos_archive`, `destinos_restore`, `destinos_versions`, `destinos_revert` (`RequireOwner`), `destinos_lote_aprovar` (`RequireOwner`), `destinos_lote_pedir_aprovacao`. Depois, `npm run gen:contract` (trilha A).
- [X] T031 [P] [US2] `apps/web/src/components/conteudos/RecusarDialog.tsx` (motivo obrigatório 1..500, botão desabilitado sem motivo) e a primeira versão de `components/conteudos/DestinoPanel.tsx`: textos com `IaAssist`, estado, bloco de aprovação ("Pedir aprovação" com nota; "Aprovar"/"Recusar" só para dono via `RequireOwner`/papel), recusa visível, "Copiar", "Baixar vídeo", "Postado" com link opcional, aviso "o vídeo mudou desde a aprovação".
- [X] T032 [US2] Integrar o `DestinoPanel` nas abas por conta do `ConteudoDetalhe.tsx` e as ações "Aprovar" (só dono) e "Pedir aprovação" na barra de lote do `Conteudos.tsx`, com o resumo do `LoteResultado` (ok e falhas com motivo).
- [X] T033 [US2] `e2e/conteudos.spec.ts`, bloco US2 (membro e dono; helpers de membro em `e2e/helpers.ts`, só acréscimo): membro pede aprovação (1 individual, 2 em lote), não vê "Aprovar" e recebe 403 pela API; dono vê 3 no sino e no atalho, aprova 2 (um em lote) e recusa 1 com motivo; membro recebe "Aprovação respondida"; conteúdo em revisão dá "Aplique a marca antes de aprovar"; histórico com os autores.

**Checkpoint:** US1 + US2 funcionam (fila de aprovados pronta para agendar).

---

## Phase 5: User Story 3 - Agendar com o modo certo (Priority: P1)

**Goal**: "Agendar" direto no clipe e no conteúdo, com modo (só lembrete executa), intervalo mínimo da conta com aviso, reagendar, cancelar, calendário, e troca das rotas e da tela de postagem da 006.

**Independent Test**: num corte pronto, Agendar → TikTok, amanhã 19h, textos com IA, Lembrete manual; item em Agendados na lista e no calendário; modos 2–4 desabilitados com o motivo (quickstart §3).

### Tests for User Story 3

- [X] T034 [P] [US3] `apps/api/tests/integration/test_agendamentos.py`: agendar direto por dono num `pendente` (aprova e agenda, **duas versões** `aprovado` e `agendado`); membro com destino aprovado agenda, reagenda e cancela; membro com não aprovado → 403 `aprovacao_necessaria`; 400 `planned_in_past` (tolerância de 1 min); 409 `conteudo_nao_pronto`, `modo_indisponivel` (`details.motivo`), `conta_em_atencao`, `version_conflict` (com `destinoVersion`), `conflict` (já `postado`); `PATCH …/agendamento` 409 `nao_aprovado` fora de `agendado` e zera `lembrado_em` ao mudar a data; cancelar volta a `aprovado` sem data; lote reagendar e cancelar com falhas por item; **intervalo mínimo** (Q3): outro agendamento da conta a menos de `intervalo_min_minutos` → 409 `intervalo_conflito` com `details.intervaloMin` e `details.conflitos`, **nada gravado**; com `ignorarIntervalo: true` grava e a versão tem `details.intervaloIgnorado = true`; intervalo 0 só conflita no mesmo minuto; o próprio destino não conflita consigo; `lote/reagendar` confere contra o estado final (trocar os horários de dois itens da mesma conta não conflita); arquivar o conteúdo (e o corte pela rota da 006) cancela os agendamentos com `cancelado_por_arquivo`, e restaurar não reagenda; conta pausada deixa o destino em `atencao`; `GET /api/contas/{id}/modos` devolve os quatro na ordem da spec.
- [X] T035 [P] [US3] `apps/api/tests/integration/test_contas.py` (ampliar): `intervaloMinMinutos` = 30 na criação e no `ContaOut`; `PATCH` do dono com 0, 45 e 1.440 grava com versão no histórico; −1 e 1.441 → 400; membro que muda o campo → 403 `forbidden` e nada gravado (membro que muda só `notes` continua 200); reversão para uma versão anterior à 0009 mantém o valor atual; mudar o intervalo não altera nenhum destino.
- [X] T036 [P] [US3] Ampliar `apps/api/tests/integration/test_lembretes.py`: só `modo = lembrete`, conta sem atenção, `JOIN conteudos`, título do destino e depois do conteúdo, link `/app/conteudos/{conteudoId}?conta={contaId}`; uma volta com destinos vencidos **não muda `estado` nem `version`** (guarda 6, parte 2).
- [X] T037 [P] [US3] Ampliar `apps/api/tests/integration/test_ia_postagem.py` e `test_sugestoes.py`: alvo `{entityType: "conteudo", entityId, contaId}` antes de o destino existir; alvo `corte` com o mesmo id; `ia_chamadas.conteudo_id` gravado em toda chamada `postagem.*`; vídeo próprio sem transcrição no contexto; o campo `ia` em `POST /api/agendamentos` e `PATCH /api/destinos/{id}`.

### Implementation for User Story 3

- [X] T038 [US3] Intervalo da conta na API: `apps/api/src/sociman_api/perfis/schemas.py` (`intervaloMinMinutos` 0..1440 em `UpdateContaIn` e no schema `Conta`), `perfis/service_contas.py` (só dono muda o campo: 403 `forbidden`; reversão mantém o valor atual quando a versão alvo não tem o campo).
- [X] T039 [US3] Em `apps/api/src/sociman_api/postagem/service.py`: `agendar` (cria o destino se faltar; dono aprova no mesmo passo; membro 403 `aprovacao_necessaria`; textos e `ia`), `reagendar`, `cancelar_agendamento`, `lote_reagendar`, `lote_cancelar`, `cancelar_por_arquivo`; validações de R6 com `modos_da_conta` (409 `modo_indisponivel`) e o aviso do intervalo com `conteudos.sequencia.conflitos` sobre `ix_postagens_conta_agenda` (409 `intervalo_conflito`, `ignorarIntervalo`, `details.intervaloIgnorado`). Nenhum modo automático é gravado.
- [X] T040 [US3] Em `postagem/router.py`: `agendamentos_create`, `agendamentos_update`, `agendamentos_cancelar`, `agendamentos_lote_reagendar`, `agendamentos_lote_cancelar` e `contas_modos`; `GET /api/calendario` (`postagens_calendario`, mantido) com `contaId`, itens de `postagens` + `conteudos`, `modo`, `estadoEfetivo`, `conteudo` no lugar de `corte` e `semData` com os aprovados primeiro (R11).
- [X] T041 [US3] Arquivar cancela: `apps/api/src/sociman_api/conteudos/service.py::archive` e `apps/api/src/sociman_api/cortes/service.py` (archive do corte) chamam `postagem.service.cancelar_por_arquivo` na mesma transação (trilha A, depois do T039). `cortes/schemas.py`: `Corte.postagens` → `Corte.destinos: DestinoResumo[]`.
- [X] T042 [US3] `apps/api/src/sociman_api/postagem/lembretes.py` (R8): filtro `modo = 'lembrete'` e conta sem atenção, `JOIN conteudos`, título e link novos; continua sem mudar estado.
- [X] T043 [US3] IA com alvo `conteudo` (R12): `apps/api/src/sociman_api/ia/schemas.py` (`AlvoTipo` + `"conteudo"`), `ia/service.py::_resolver_postagem` pelo conteúdo (e o corte, na origem corte), `ia/contexto.py::montar(..., conteudo=...)`, `ia/aplicacao.py::_Alvo.conteudo_id`, gravação de `ia_chamadas.conteudo_id`.
- [X] T044 [US3] Criar `apps/api/tests/integration/test_guardas_014.py` com os guardas 3, 4 e 8 do plan: (3) `POST /api/agendamentos`, `PATCH …/agendamento`, `sequencia/previa` e `sequencia` com cada modo automático → 409 `modo_indisponivel` e nenhuma linha muda; (4) `INSERT`/`UPDATE` direto com `modo <> 'lembrete'` ou estado `rascunho_criado`, `publicado`, `falhou` → `IntegrityError`; (8) cada ação (aprovar, pedir, recusar, agendar, reagendar, cancelar, cancelar por arquivo, lote) grava exatamente uma versão por destino afetado com autor, e membro recebe 403 em aprovar, recusar, lote aprovar e reverter. (A parte da sequência passa depois do T056.)
- [X] T045 [US3] **Remoção das rotas de postagem da 006** em `postagem/router.py` e `postagem/service.py`: `GET/POST /api/cortes/{id}/postagens`, `GET/PATCH /api/postagens/{id}`, `POST /api/postagens/{id}/{postado,archive,restore,revert}`, `GET /api/postagens/{id}/versions` (as de sugestão `deprecated` da 006 ficam). Reescrever os testes que as usavam: o que `test_postagens.py` cobria vai para `test_destinos.py`, `test_agendamentos.py` e um `test_calendario.py` novo (e `test_postagens.py` sai quando nada mais depender dele); adaptar `test_historico_006.py`, `test_sugestoes.py`, `test_importacao.py` (`destinos`). Depois, `npm run gen:contract`: o `check:contract` e o `typecheck` apontam cada uso no SPA (T050).
- [X] T046 [P] [US3] `apps/web/src/lib/postagem.ts` (vira destino e agendamento: mutations de destino, agendamento, lote e `useModos(contaId)`), `apps/web/src/lib/ia.ts` e `components/ia/IaAssist.tsx` (alvo `conteudo`, a sessão sobrevive à criação do destino).
- [X] T047 [P] [US3] `apps/web/src/components/conteudos/{ModoSelect,AgendarDialog}.tsx`: conta (só as do perfil), data e hora (APP_TZ), os quatro modos com os indisponíveis desabilitados e o motivo, textos com "Gerar com IA"; dono vê "Aprovar e agendar", membro diante de não aprovado vê "Pedir aprovação"; em `intervalo_conflito`, mostra os posts próximos e o intervalo, com "Manter mesmo assim" (reenvia com `ignorarIntervalo: true`) e "Escolher outro horário".
- [X] T048 [US3] `DestinoPanel.tsx`: bloco de agendamento (Agendar, Reagendar, Cancelar, modo com motivo, chips `a_postar`/`atrasado`/`atencao`). Botão "Agendar" nas linhas de `Conteudos.tsx` e no `ConteudoDetalhe.tsx`; "Cancelar agendamento" na barra de lote.
- [X] T049 [P] [US3] `apps/web/src/pages/perfis/ContasTab.tsx`: campo "Intervalo mínimo entre posts (min)" (0..1.440, padrão 30) no formulário da conta; editável só por dono, leitura para membro.
- [X] T050 [US3] Trocar a tela de postagem da 006: `apps/web/src/pages/cortes/CorteDetalhe.tsx` usa o `DestinoPanel` com o botão **Agendar** no corte pronto; `pages/perfis/tabs/CortesTab.tsx` ganha "Agendar" nas linhas prontas e "Ver em Conteúdos"; `pages/calendario/Calendario.tsx` com modo e estado efetivo nos cartões, filtro de conta, coluna "Sem data" com aprovados primeiro, arrastar por `lote/reagendar` (com o aviso do intervalo) e soltar "sem data" abrindo o `AgendarDialog`; remover `components/postagem/PostagemSection.tsx`. `npm run check:web` verde.
- [X] T051 [US3] Ajustar os e2e da 006 e da 008 ao painel de destinos e às rotas novas: `e2e/cortes-openshorts.spec.ts` (grupo "Postagem em TikTok" → painel do destino; agendar pelo `AgendarDialog`) e `e2e/assistente-ia.spec.ts` (`/api/cortes/{id}/postagens` e `/api/postagens/{id}/versions` → rotas de destino; grupo do painel). Rodar os dois com `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/cortes-openshorts.spec.ts e2e/assistente-ia.spec.ts`.
- [X] T052 [US3] `e2e/conteudos.spec.ts`, bloco US3: agendar direto num corte pronto (dono, IA falsa, lembrete), modos 2–4 desabilitados com o motivo, chip e calendário, histórico com `aprovado` e `agendado`; segundo agendamento a 10 min na mesma conta mostra o aviso do intervalo e "Manter mesmo assim" grava; membro diante de não aprovado vê "Pedir aprovação"; reagendar arrastando e cancelar; dono muda o intervalo na aba Contas e o membro só vê.

**Checkpoint:** US1–US3 (P1) completas: podem ir ao dono antes de US4 e US5 (plan).

---

## Phase 6: User Story 4 - Agendar em lote e em sequência (Priority: P2)

**Goal**: sequência com cadência, prévia que respeita o intervalo da conta, confirmação com `esperado`, textos pela IA para os que não têm, trocar horários.

**Independent Test**: 7 aprovados da Taverna, "1 por dia às 19h a partir de amanhã", prévia com 7 dias, confirmar e ver os 7 no calendário (quickstart §4).

### Tests for User Story 4

- [X] T053 [P] [US4] Ampliar `apps/api/tests/unit/test_sequencia.py` (planejador puro): fuso `America/Sao_Paulo` (inclusive virada de dia), horários no passado pulados, conflito com ocupados e com os já atribuídos na própria sequência usando o `intervalo_min` recebido (30, 0, 120), horários do mesmo dia mais próximos que o intervalo, ordem dos itens preservada, limites de 100 itens, 6 horários e 180 dias.
- [X] T054 [P] [US4] Em `apps/api/tests/integration/test_agendamentos.py`, seção "sequência" (depois do T034, mesmo arquivo): prévia não grava e devolve `intervaloMin` da conta, `slots`, `pulados` (`conflito` com `destinoId`, `passado`) e `inelegiveis` (não pronto, arquivado, não aprovado para membro); mudar o intervalo da conta muda a prévia; confirmação igual aplica com `SAVEPOINT` e devolve `{ok, falhas}`; alguém agendando no meio → 409 `previa_desatualizada` com `details.previa`; dono aprova e agenda no mesmo passo, membro só com aprovados; 400 `validation_error` (horário repetido, mais de 180 dias); 409 `modo_indisponivel`.

### Implementation for User Story 4

- [X] T055 [US4] Em `apps/api/src/sociman_api/conteudos/sequencia.py`, `planejar(itens, inicio, horarios, ocupados, agora, intervalo_min) -> (slots, pulados)` (R7), sobre o `conflitos` do T013.
- [X] T056 [US4] Em `postagem/service.py` e `postagem/router.py`: `agendamentos_sequencia_previa` e `agendamentos_sequencia` (ocupados pela `ix_postagens_conta_agenda` com as linhas travadas; recalcula e compara com `esperado`; aplica item a item). Depois, `npm run gen:contract`.
- [X] T057 [P] [US4] `apps/web/src/components/conteudos/SequenciaDialog.tsx`: conta, primeira data, chips `HH:MM` (1..6), modo, "Gerar textos com IA para os que não têm"; prévia (tabela dia × item, intervalo mínimo da conta, pulados e inelegíveis) antes de "Confirmar"; em `previa_desatualizada`, mostra a prévia nova; depois, barra de progresso gerando os textos no SPA (até 3 chamadas ao mesmo tempo, `PATCH /api/destinos/{id}` com `ia`), com o selo "sem textos" nos que falharem.
- [X] T058 [US4] Barra de lote do `Conteudos.tsx`: "Agendar em sequência" e "Trocar horários" (dois agendados, `lote/reagendar`, só os dois mudam).
- [X] T059 [US4] `e2e/conteudos.spec.ts`, bloco US4: sequência de 7 com um conflito pulado, `previa_desatualizada` ao agendar em outra aba antes de confirmar, 7 no calendário, textos gerados pela IA falsa, "Trocar horários".

**Checkpoint:** US4 funciona sobre US1–US3.

---

## Phase 7: User Story 5 - Conteúdos de outras origens (Priority: P3)

**Goal**: enviar vídeo próprio (1 s a 10 min, até 2 GB, qualquer proporção, aviso "não é vertical") e filtrar por origem.

**Independent Test**: enviar um MP4 vertical como vídeo próprio da Queridinhos, vê-lo com a origem "Vídeo próprio", aprovar e agendar em lembrete (quickstart §5).

### Tests for User Story 5

- [X] T060 [P] [US5] `apps/api/tests/integration/test_video_proprio.py` (ffmpeg real, vídeos gerados com `lavfi`): vertical curto → 201 `situacao: pronto`, miniatura no bucket `sociman`, vídeo em `sociman-videos/conteudos/{id}/video.<ext>`, `duration_ms`, `width`, `height`, `video_sha256`, versão `created` com autor; horizontal e quadrado aceitos com `naoVertical = true`; menos de 1 s e mais de 10 min → 400 `invalid_video`; arquivo que não é vídeo → 400 `invalid_video`; acima de 2 GB → 413 (limite reduzido por config no teste); HD sem sentinela → 503, abaixo do piso → 507; perfil arquivado → 409; envio interrompido não cria linha; filtro `origem=video_proprio`; `POST /api/midia/links` com `conteudo_video` (validade, `download=1`, `Range`); aprovar e agendar como um corte; arquivar e restaurar pelo próprio conteúdo (com `revert`).

### Implementation for User Story 5

- [X] T061 [US5] Criar `apps/api/src/sociman_api/conteudos/video_proprio.py` (R9): `cortes.service.precheck`/`receive` com `max_bytes = 2 GB` e prefixo `proprio-`; `cortes.probe.probe` com 1 s a 10 min e formatos da 004; upload para `sociman-videos`; miniatura com `cortes.compose.extract_frame` em `min(1 s, duração/2)` no bucket `sociman`; só então a linha `conteudos` e a versão `created`.
- [X] T062 [US5] Criar `apps/api/src/sociman_api/conteudos/router_video.py` com `conteudos_video_proprio` (`POST /api/perfis/{id}/conteudos/arquivo`, multipart `arquivo` e `titulo?`) e incluir no `main.py` (acréscimo); `MidiaKind` `conteudo_video` em `apps/api/src/sociman_api/midia.py` e `router_midia.py`. Depois, `npm run gen:contract`.
- [X] T063 [P] [US5] `docker/nginx/default.conf.template`: `location ~ ^/api/perfis/[^/]+/conteudos/arquivo$` com `client_max_body_size 2100m`, `proxy_request_buffering off` e timeouts longos, igual à do envio avulso; `docker compose restart edge` (armadilha 13); `npm run check:web` confere que a CSP não mudou.
- [X] T064 [P] [US5] `apps/web/src/components/conteudos/VideoProprioDialog.tsx` (perfil, arquivo, título; progresso de upload; aviso "não é vertical" na resposta) com o botão "Enviar vídeo próprio" no topo de `Conteudos.tsx` e na aba do perfil; filtro "Origem" com "Vídeo próprio"; no detalhe, player e "Baixar vídeo" por `conteudo_video`.
- [X] T065 [US5] `e2e/conteudos.spec.ts`, bloco US5: enviar um MP4 vertical pequeno, ver origem "Vídeo próprio" e "Pronto", filtrar por origem, aprovar e agendar em lembrete; um horizontal mostra "não é vertical"; um `.txt` renomeado dá erro.

**Checkpoint:** todas as histórias funcionam de forma independente.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T066 [P] Conferir no `/api/openapi.json` que nenhum caminho nem `operationId` novo contém termos do guarda do princípio I (`publish`, `share`, `post-to`, `upload-to`, `tiktok`, `youtube`, `instagram`), que não há `DELETE`, e que `grep -rn "httpx" apps/api/src/sociman_api/conteudos apps/api/src/sociman_api/postagem` não acha nada (a 014 não tem cliente HTTP novo).
- [X] T067 [P] Rodar o `test_escala_conteudos.py` (T017) com o código final e anotar o p95 medido.
- [X] T068 Verificação completa: `npm run test:api`, `docker compose exec api uv run ruff check .`, `npm run gen:contract && npm run check:web` (sem divergência), `flock /tmp/sociman-e2e.lock npm run test:e2e` (regressão inteira, com `conteudos.spec.ts`, `cortes-openshorts.spec.ts` e `assistente-ia.spec.ts`).
- [X] T069 Migration no dev (quickstart §0): `docker compose up -d --build api worker agendador`, `alembic current` = `0009_central_conteudos`; contagens do T001 conferidas (conteúdos = cortes; estados mapeados; `entity_versions` com a mesma contagem e hash; contas com intervalo 30); `/api/health` ok. Resultado numa seção "Resultado" nova no fim de `specs/014-central-de-conteudos/quickstart.md`.
- [ ] T070 Validação manual pelo dono (quickstart §1 a §7), com dono e membro, cronometrando SC-001 (< 30 s cada pergunta), SC-002 (< 1 min) e SC-003 (< 2 min para 10); anotar no quickstart. **Só com o dono presente.**
- [ ] T071 Apagar o backup do T002 (`rm /media/sakai/BACKUP/tiktok/sociman/backups/pre-0009.dump`, ou o arquivo no scratchpad) **só depois** do T069 e do T070 aprovados; conferir com `ls`.
- [X] T072 [P] `CLAUDE.md` (SociMan): seção curta "Central de conteúdos (desde a spec 014)": `conteudos` com `id = cortes.id` na origem corte; `postagens` = destino (`entity_type` "postagem"); estado efetivo só em `conteudos/consulta.py`; só `lembrete` executa (CHECKs `ck_postagens_modo_014`/`ck_postagens_estados_015`, que a 015 remove); aprovar/recusar só dono, agendar dono e membro com aprovação; intervalo mínimo por conta (sequência pula, individual avisa com `ignorarIntervalo`); rotas de postagem da 006 removidas; `location` do vídeo próprio (2100m).
- [X] T073 `docs/visao.md`: marcar a 014 como ✅ **implementada** no backlog de specs, com as decisões Q1–Q4 em uma linha cada. **Só no fim**, depois do T068 verde e do T070 aprovado pelo dono.

---

## Dependencies & Execution Order

### Phase Dependencies
- Setup (T001–T002) → Foundational (T003–T015) → histórias.
- T003 → T004 → T007; T005 e T006 em paralelo com T004; T007 → T008 → T009. T010 e T011 dependem do T003/T004; T012 e T013 são independentes; T014 depois do T004; T015 depois do T003/T004.
- US1: T016/T017 depois da Foundational; T018 → T019 → T020; SPA (T021–T024) depois do T020; T025 depois do T024.
- US2: T027 → T028, T029 → T030 (+ `gen:contract`) → T031, T032 → T033.
- US3: T038 e T039 depois da US2 (usam o mesmo `postagem/service.py`); T040 depois do T039; T041 depois do T039; T042, T043 independentes entre si; T044 depois do T040; T045 depois do T040 (as rotas novas substituem as antigas) e antes do T050; SPA (T046–T050) depois do `gen:contract` do T045; T051 depois do T050; T052 depois do T048–T050.
- US4: T055 depois do T013; T056 depois do T039 e do T055; T057, T058 depois do `gen:contract` do T056; T059 no fim.
- US5: T061 depois da Foundational; T062 depois do T061; T063 independente; T064 depois do `gen:contract` do T062; T065 no fim. US5 **não** depende de US4.
- Polish depois das histórias; T071 e T073 por último.

### Parallel Opportunities
- T005, T006, T012 e T013 em paralelo na Foundational.
- Testes de cada história marcados [P] entre si (arquivos diferentes).
- Depois da US3, US4 e US5 andam juntas (US5 só toca `conteudos/video_proprio.py`, `router_video.py`, `midia.py`, `router_midia.py` e o edge).
- No SPA, T021–T023, T031, T046, T047, T049, T057 e T064 são arquivos diferentes.

---

## Trilhas para agentes paralelos

Quatro agentes, sem arquivo em comum. Cada trilha só edita os arquivos listados; qualquer outro arquivo pede coordenação pelo líder. Os arquivos "só acréscimo" do topo podem receber blocos de qualquer trilha.

| Trilha | Agente sugerido | Tarefas | Arquivos (exclusivos) |
|---|---|---|---|
| **A: API base, migração e consulta** | `api-014-base` | T001–T004, T007–T011, T014–T020, T041, T066, T067, T069 | `apps/api/migrations/**`; `conteudos/{__init__,models,consulta,schemas,service,router}.py`; `cortes/{service,schemas}.py`; `envios/importacao.py`; no T004, também `postagem/{models,service,lembretes,router}.py` (só o mínimo; depois do checkpoint da Foundational eles são da trilha B); `tests/unit/test_constitution_guards.py`; `tests/integration/test_migration_{0006,0008,0009}.py`, `test_conteudos.py`, `test_escala_conteudos.py`, `test_cortes.py`. **Única trilha que roda `npm run gen:contract`** e toca `packages/contract/**` (inclusive quando B pede, nos T030, T045, T056 e T062) |
| **B: API aprovação, agendamento, sequência e vídeo próprio** | `api-014-fluxo` | T005, T006, T012, T013, T026–T030, T034–T040, T042–T045, T053–T056, T060–T062 | `postagem/**` (depois da Foundational); `conteudos/{capacidades,sequencia,video_proprio,router_video}.py`; `perfis/{models,schemas,service_contas}.py`; `ia/{models,schemas,service,contexto,aplicacao}.py`; `notificacoes/**`; `midia.py`, `router_midia.py`; `tests/unit/test_{capacidades,sequencia}.py`; `tests/integration/test_{destinos,agendamentos,contas,lembretes,ia_postagem,sugestoes,historico_006,importacao,postagens,calendario,guardas_014,video_proprio}.py` (o `test_importacao.py` só no T045; o invariante do T010 é da A e entra antes) |
| **C: SPA** | `spa-014` | T021–T024, T031, T032, T046–T050, T057, T058, T064 | `apps/web/**` (novos em `pages/conteudos/`, `components/conteudos/`, `lib/conteudos.ts`, `components/data-table/CursorPagination.tsx`; alterações em `DataTable.tsx`, `lib/postagem.ts`, `lib/ia.ts`, `components/ia/IaAssist.tsx`, `CorteDetalhe.tsx`, `CortesTab.tsx`, `ContasTab.tsx`, `Calendario.tsx`; remoção de `components/postagem/PostagemSection.tsx`; acréscimos em `App.tsx` e `nav.ts`) |
| **D: e2e, edge e docs** | `e2e-014` | T025, T033, T051, T052, T059, T063, T065, T068, T070 (com o líder), T071–T073 | `e2e/**` (`conteudos.spec.ts` novo, `cortes-openshorts.spec.ts`, `assistente-ia.spec.ts`, acréscimos em `helpers.ts`), `docker/nginx/default.conf.template`, `specs/014-central-de-conteudos/quickstart.md` (Resultado), `CLAUDE.md`, `docs/visao.md` |

Sincronização:
1. A faz Setup e a Foundational do modelo (T001–T004, T007–T011, T014, T015); B faz em paralelo T005, T006, T012 e T013 (arquivos dela). C e D esperam o checkpoint da Foundational, mas D já pode fazer o T063.
2. Depois do checkpoint, A segue com US1 (T016–T020) e B com US2 (T026–T030). B avisa A para cada `gen:contract`.
3. B entrega o `cancelar_por_arquivo` (T039) e avisa A para o T041. A remoção das rotas da 006 (T045, B) só entra quando C estiver pronto para o T050 **na mesma rodada**, para o `main` nunca ficar com o SPA quebrado; D faz o T051 logo em seguida.
4. C começa cada tela depois do `gen:contract` correspondente (T020, T030, T045, T056, T062).
5. D escreve cada bloco do `conteudos.spec.ts` quando A, B e C fecham a história, e roda **sempre** com `flock /tmp/sociman-e2e.lock` (nunca dois e2e ao mesmo tempo, nem com outra spec).
6. T070 fica com o líder e o dono; T071 e T073 só depois do T068 verde e do T070 aprovado.

---

## Implementation Strategy

### MVP (US1–US3, todas P1)
1. Setup (com backup) + Foundational (migration com o teste de preservação da 006 e os guardas).
2. US1 (lista e detalhe) → US2 (aprovação) → US3 (agendar, intervalo da conta, troca da tela e das rotas da 006).
3. **Parar e validar** com o dono (quickstart §0 a §3 e §6).

### Incremental
US4 (sequência) e US5 (vídeo próprio), em paralelo → Polish (verificação completa, validação do dono, backup apagado, docs).

## Notes
- Nenhum DELETE, nenhuma dependência nova (Python ou npm), nenhum serviço nem trilha de agendador nova; uma tabela nova (`conteudos`) e uma coluna nova em `contas`.
- Nenhum modo automático executa na 014: capacidades, CHECKs e guardas (três camadas). Membro agenda só `lembrete`, que não envia nada.
- Commit só quando o dono pedir, em pt-BR, no imperativo.

## Emenda do dono (2026-09-29): proposta do OpenShorts como texto padrão

- [X] T074 [US3] API: expor `propostaOpenshorts {titulo, descricao, gancho, score}` no conteúdo de origem corte (`conteudos/schemas.py`, `conteudos/service.py`), e pré-preencher `titulo`/`descricao` do destino na criação (inclusive "agendar direto", lote e sequência) quando vierem vazios (`postagem/service.py`), respeitando os limites do destino; teste em `apps/api/tests/integration/test_proposta_openshorts.py`
- [X] T075 [US3] SPA: bloco "Proposta do OpenShorts" no `ConteudoDetalhe` (título, descrição, gancho, nota, com "Copiar"), campos do destino já preenchidos com a proposta e botão "Usar proposta do OpenShorts" quando vazios (`apps/web/src/pages/conteudos/ConteudoDetalhe.tsx`, `components/conteudos/DestinoPanel.tsx`, `AgendarDialog.tsx`)
