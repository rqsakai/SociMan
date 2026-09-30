---

description: "Tarefas da feature 017-guia-de-comunicacao"
---

# Tasks: Guia de comunicação por perfil e conta (017-guia-de-comunicacao)

**Input**: `specs/017-guia-de-comunicacao/` (spec, plan, research R1–R13, data-model, contracts/http-api.md, quickstart, open-questions resolvidas)

**Pré-requisito:** a 008 (assistente de IA) validada e a **`0011_metricas_tiktok` (016) aplicada no dev** (`alembic current` = `0011_metricas_tiktok`). A 016 e a 018 ainda têm trabalho em andamento no mesmo branch: a 017 **não toca** `metricas/`, `publicacao/`, `components/metricas/`, `components/conteudos/DestinoPanel.tsx` nem `e2e/metricas.spec.ts`. Não rodar `setup-tasks.sh` nem mexer em `.specify/feature.json` (o líder troca quando a 016 fechar).

**Decisões do dono (2026-09-30, spec → Clarifications):**
- **Q1:** a voz do guia (tom, faça/não faça, vocabulário, emojis, exemplos, hashtags fixas) **não** entra em `avatar.descricao_prompt`, `cenario.prompt_ambiente` e `avatar.regras_imagem`; esses 3 tipos são `usa_guia = "so_proibidas"`: recebem só as **palavras proibidas** do perfil (mesma detecção, 2ª tentativa, marcação e `ia_proibida`), e a tela deles tem o link **"Ver guia de comunicação do perfil"** (`/app/perfis/<id>?aba=guia`).
- **Q2 = A:** editado por um humano, pode aplicar. O servidor recusa (400 `ia_proibida`) só o **campo salvo igual à proposta que contém a proibida**; campo editado passa (desfecho `editada`).
- **Q3:** padrão de **5** fixas, **configurável por conta** (`max_hashtags_fixas`, 0..8, `NULL` = 5; 8 = `postagem.textos.HASHTAGS_MAX`). **Regra de soma** (research R6): `M(conta) = conta.max ?? 5`; `F(conta)` = fixas do perfil, na ordem, depois as da conta, sem repetir; sempre `|F(conta)| ≤ M(conta)`. O perfil tem no máximo 5 fixas e **nenhum** máximo próprio. O save da conta confere a própria soma; o save do perfil confere todas as contas **não arquivadas, com ou sem guia**. Estado inválido herdado vira aviso e conflito, nunca erro de geração.

**Nomes canônicos** (valem os documentos do plano): tabela `ia_guias` (`entity_type = "ia_guia"`), enum `guia_emojis`; módulos novos `ia/guia.py` (domínio puro), `ia/service_guia.py`, `ia/router_guia.py`, `ia/schemas_guia.py`; rotas de montar/testar em `ia/router.py`; tipos `guia.montar` e `guia.testar`; formatos `guia` e `variacoes`; `PROMPT_VERSION = "ia/2"`; tags `guia_perfil`, `guia_conta`, `guia_em_teste`; erro `ia_proibida`; ajuste `hashtags_fixas_incluidas`; `operationId` `guias_perfil_*`, `guias_conta_*`, `ia_guia_montar`, `ia_guia_testar`; migration `0012_guia_comunicacao` (`down_revision = "0011_metricas_tiktok"`); SPA `pages/perfis/tabs/GuiaTab.tsx`, `pages/perfis/ContaGuia.tsx` (`/app/contas/:id/guia`), `components/guia/*`, `lib/guia.ts`.

**Tests**: OBRIGATÓRIOS (constitution 4.0.0, princípios I, VI e VII):
- pytest na stack efêmera (`npm run test:api [-- args]`), **sempre com o Claude falso** (`tests/fakes/anthropic_fake.py`);
- `docker compose exec api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e na stack isolada, **sempre com trava**: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/guia-comunicacao.spec.ts]` (armadilha 18: nunca dois e2e ao mesmo tempo, nem com outra spec). Nunca `npx playwright test` direto;
- **nenhum teste automatizado chama o Claude real**; o Claude real só no quickstart §4–§6, com o dono.

**Segredos (princípio V):** ninguém roda `cat .env` nem imprime a `ANTHROPIC_API_KEY`; para conferir se existe: `grep -oE '^ANTHROPIC_API_KEY=' .env`. **Nenhum texto do guia vai para log** (só ids, versões e contagens).

**Restrições do data-model (citadas literalmente; valem na migration, nos modelos e nos serviços):**
- Tabela: "Uma linha por perfil (`conta_id IS NULL`) e no máximo uma por conta. A linha nasce na primeira edição (sem linha = sem guia; a API responde `version = 0` e os campos vazios). Sem `archived_at` e sem DELETE: \"limpar\" é salvar vazio."
- Colunas: `perfil_id` "uuid NOT NULL FK `perfis.id`" ("também no guia da conta (o perfil da conta)"); `conta_id` "uuid NULL FK `contas.id`" ("NULL = guia do perfil"); `tom` "CHECK `char_length(tom) <= 500`"; `faca` "CHECK `cardinality(faca) <= 10`"; `nao_faca` "CHECK `cardinality(nao_faca) <= 10`"; `vocabulario` "CHECK `cardinality(vocabulario) <= 30`"; `proibidas` "CHECK `cardinality(proibidas) <= 30`"; `emojis` "`guia_emojis` NULL", "`nao` \| `moderado` \| `livre`; NULL = não definido (na conta, herda)"; `emojis_preferidos` "CHECK `cardinality(...) <= 10`"; `hashtags_fixas` "CHECK `cardinality(hashtags_fixas) <= 8 AND (conta_id IS NOT NULL OR cardinality(hashtags_fixas) <= 5)`; já normalizadas (`#…`)"; `max_hashtags_fixas` "CHECK `max_hashtags_fixas IS NULL OR (conta_id IS NOT NULL AND max_hashtags_fixas BETWEEN 0 AND 8)`; só no guia da conta; NULL = padrão 5 (Q3)"; `exemplos` "lista de `{\"tipo\": \"titulo\"\|\"legenda\"\|\"bordao\", \"texto\": str}`; CHECK `jsonb_array_length(exemplos) <= 5`"; `version` "controle otimista e nº da versão atual"; "`AuditMixin`".
- Índices: "`uq_ia_guias_perfil` UNIQUE `(perfil_id) WHERE conta_id IS NULL`"; "`uq_ia_guias_conta` UNIQUE `(conta_id) WHERE conta_id IS NOT NULL`"; "o par (conta, perfil da conta) é garantido pelo service (a conta é carregada e o `perfil_id` vem dela; nunca do cliente)".
- Limites fora do banco: "Limites por item (1..200 em faça/não faça, 1..60 em vocabulário e proibidas, 1..16 em emojis, 1..500 nos exemplos, hashtags pela regra da 006) e o **total ≤ 4.000 caracteres** ficam no Pydantic/service (R2), não em CHECK: o banco guarda o que já passou."
- Modelo: `__versioned_fields__ = ("perfil_id", "conta_id", "tom", "faca", "nao_faca", "vocabulario", "proibidas", "emojis", "emojis_preferidos", "hashtags_fixas", "max_hashtags_fixas", "exemplos")`; `__immutable_fields__ = ("perfil_id", "conta_id")`.
- Validação no save, "na ordem, tudo no mesmo PUT (ou revert), com erros campo a campo (`details.fields`)": 1. limites ("itens aparados, vazios descartados, repetidos (normalizados) recusados"); 2. "**hashtags fixas** normalizadas pela `normalizar_hashtag` da 006; inválidas recusadas"; 3. "**proibidas do efetivo** (este guia ∪ o outro nível): nenhuma pode aparecer (palavra inteira, R7) no `tom`, `faca`, `nao_faca`, `vocabulario`, `exemplos` nem nas `hashtags_fixas` **deste** guia"; 4. "**máximo de fixas** (Q3): `max_hashtags_fixas` só no guia da conta (no perfil, não nulo → 400 em `maxHashtagsFixas`); 0..8 (`textos.HASHTAGS_MAX`)"; 5. cruzada: "guia da **conta**: `|F(conta)| ≤ M(conta)` com os valores do formulário → 400 em `hashtagsFixas`"; "guia do **perfil**: para cada conta **não arquivada** do perfil, **com ou sem guia**: `|F(conta)| ≤ M(conta)`; e, nas contas com guia, nenhuma proibida nova do perfil aparece no conteúdo do guia da conta → 400 com `details.contas = [{contaId, rotulo, campos}]`".
- Histórico: "`created` (1ª edição), `updated`, `reverted` (`details.from_version`)"; "`details.ia = [...]` quando o save veio de uma proposta do \"montar\" (008, `aplicacao.marcar`)"; versões pedidas por `/api/perfis/{id}/guia/versions` e `/api/contas/{id}/guia/versions`, "que a API traduz para o `id` da linha".
- `ia_chamadas`: `guia_perfil_version` "int NULL"; `guia_conta_version` "int NULL"; `guia_rascunho` "text NULL", "CHECK `guia_rascunho IS NULL OR guia_rascunho IN ('perfil','conta')`; só em `guia.testar`"; `proibidas` "text[] NOT NULL DEFAULT `'{}'`", "proibidas encontradas na proposta final"; "`entity_type` passa a aceitar também `guia` (texto livre na coluna; só o service escreve); `entity_id` = id da linha do guia, ou NULL se o guia ainda não existe"; "as linhas antigas ficam com NULL/`'{}'` (sem backfill: antes da 017 não havia guia)".
- Tipos: `TipoCampo` ganha "`usa_guia: Literal[\"completo\", \"so_proibidas\"] = \"completo\"`, `regras_de: str | None = None` e `listar_regras: bool = True`"; "O teste de cruzamento tipos × schemas da 008 ignora os `guia.*` (não há entidade salva com esses campos; o `guia.montar` é cruzado com `GuiaIn`)".
- Migration: upgrade "`CREATE TYPE guia_emojis AS ENUM ('nao','moderado','livre')`", a tabela, os 2 índices únicos parciais, as 4 colunas e "`ADD CONSTRAINT ck_ia_chamadas_guia_rascunho`"; downgrade "(só dev)": "DROP das 4 colunas e da constraint; DROP TABLE ia_guias; DROP TYPE guia_emojis (as versões \"ia_guia\" em entity_versions ficam; são inofensivas)".

**Arquivos compartilhados: SÓ ACRÉSCIMO** (bloco novo ao lado dos vizinhos, sem reordenar): `apps/api/src/sociman_api/main.py`, `apps/api/tests/conftest.py`, `apps/api/src/sociman_api/errors.py` (se precisar do código `ia_proibida`), `apps/web/src/App.tsx`, `e2e/fakes/server.py`, `e2e/helpers.ts`, `CLAUDE.md`, `docs/visao.md`. `packages/contract/**` é **gerado** (armadilha 6): em conflito, rebase e `npm run gen:contract` de novo.

**Não mexer:** `specs/008-*/**`, `specs/016-*/**`, `specs/018-*/**` (só leitura); nada da 016/018 em andamento (lista no Pré-requisito).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US3 da spec
- **[DONO]**: passo manual do dono (o agente mostra o comando e espera)

---

## Phase 1: Setup (gate, linha de base e backup)

- [X] T001 **Gate:** `docker compose exec api uv run alembic current` e `alembic heads` mostram só `0011_metricas_tiktok`; `ls apps/api/migrations/versions/` não tem nenhum `0012_*`. Conferir que `git status` não mostra arquivos da 017 além de `specs/017-guia-de-comunicacao/**`. Commit/branch só quando o dono pedir.
- [X] T002 Linha de base no dev, **antes** de subir código novo (só contagens, nada de texto): `select tipo_campo, desfecho, count(*) from ia_chamadas group by 1,2;`, `select count(*) from ia_regras;`, `select count(*), md5(string_agg(id::text, ',' order by id)) from entity_versions;`. Guardar a saída no relatório da tarefa (não no repositório).
- [X] T003 **Backup do banco de dev antes da migration `0012_guia_comunicacao`** (quickstart §0): `mkdir -p /media/sakai/BACKUP/tiktok/sociman/backups` e `docker compose exec -T postgres pg_dump -U sociman -Fc sociman > /media/sakai/BACKUP/tiktok/sociman/backups/pre-0012.dump` (HD, fora do git e do MinIO; sem o sentinela `.sociman-volume`, usar o scratchpad da sessão). Conferir tamanho > 0 e `docker compose exec -T postgres pg_restore -l < /media/sakai/BACKUP/tiktok/sociman/backups/pre-0012.dump | grep -c "TABLE DATA"` > 0. **Nunca no repositório.** Apagar só no T057.
- [X] T004 [P] Linha de base de testes da 008: `npm run test:api -- tests/unit/test_ia_prompt.py tests/unit/test_ia_saida.py tests/unit/test_ia_tipos.py tests/unit/test_ia_aplicacao.py tests/integration/test_ia_gerar.py tests/integration/test_ia_aplicar.py tests/integration/test_ia_postagem.py tests/integration/test_ia_registro.py tests/integration/test_ia_regras.py` verde antes de mudar qualquer coisa (registrar no relatório).

---

## Phase 2: Foundational (modelo, migration, domínio do guia, schemas, fake e guardas)

**⚠️ Bloqueia todas as histórias.**

- [X] T005 `apps/api/src/sociman_api/ia/models.py`: `GuiaEmojis` (StrEnum `nao`/`moderado`/`livre`, `name="guia_emojis"`) e `IaGuia(AuditMixin, Base)` com todas as colunas, CHECKs e os 2 índices únicos parciais citados acima, `__versioned_fields__` e `__immutable_fields__`; em `IaChamada`, as 4 colunas (`guia_perfil_version`, `guia_conta_version`, `guia_rascunho`, `proibidas`) e `ck_ia_chamadas_guia_rascunho`.
- [X] T006 Criar `apps/api/migrations/versions/0012_guia_comunicacao.py` (`revision = "0012_guia_comunicacao"`, `down_revision = "0011_metricas_tiktok"`) com o upgrade e o downgrade (docstring "só dev") do data-model, na ordem: tipo, tabela, índices, colunas + constraint; downgrade inverso. Sem backfill.
- [X] T007 Acréscimo em `apps/api/tests/conftest.py` (bloco "Spec 017"): `ia_guias` na lista do `TRUNCATE` (antes de `perfis`/`contas` pelo `CASCADE`, sem reordenar as outras).
- [X] T008 Criar `apps/api/tests/integration/test_migration_0012.py` (como `test_migration_0011.py`): descer a `0011_metricas_tiktok`, semear chamadas da 008; subir e conferir: chamadas antigas com `proibidas = '{}'` e versões `NULL`, `entity_versions` idêntica (contagem e hash); insere guia de perfil e de conta; 2º guia do mesmo perfil viola `uq_ia_guias_perfil`, 2º da mesma conta viola `uq_ia_guias_conta`; 6 fixas no perfil e 9 na conta violam o CHECK; `max_hashtags_fixas` no perfil e fora de 0..8 violam o CHECK; `tom` com 501 caracteres e 6 exemplos violam; `guia_rascunho = 'outro'` viola `ck_ia_chamadas_guia_rascunho`. Descer e **subir de novo**. Ajustar os testes de migration anteriores que sobem para `head`, sem mudar o que verificam.
- [X] T009 Criar `apps/api/src/sociman_api/ia/guia.py` (domínio puro, sem HTTP nem sessão, exceto `em_vigor`): constantes de limite do R2 (`TOM_MAX=500`, …, `TOTAL_MAX=4000`, `FIXAS_PERFIL_MAX=5`, `FIXAS_PADRAO=5`, `FIXAS_TETO=textos.HASHTAGS_MAX`); `GuiaCampos`, `GuiaBloco`, `GuiasEmVigor`, `GuiaEfetivo`, `Conflito`; `normalizar` (NFKD, sem marcas combinantes, `casefold`, espaços colapsados); `achar_proibidas(textos, termos)` (palavra inteira `(?<!\w)tok1\W+tok2(?!\w)`, e hashtag inteira igual ao termo sem espaços); `tamanho`; `fundir` (proibidas = união; fixas = perfil, depois conta, sem repetir, cortadas em `M` só no estado inválido herdado, com aviso; emojis e preferidos da conta ou do perfil; `maxHashtagsFixas = conta ?? 5`); `conflitos` (emojis, faça × não faça, `hashtagsFixas` no estado inválido); `render(bloco, so_proibidas=False)` com os rótulos fixos do R4; `em_vigor(db, perfil_id, conta_id)` (2 consultas por chave única; guia vazio = ausente).
- [X] T010 [P] Criar `apps/api/tests/unit/test_guia_normalizar.py` ("Clickbait" = "CLÍCKBAIT"; "pix" não casa "pixel"; termo de 2 palavras com pontuação no meio; `#compreja` × "compre já") e `apps/api/tests/unit/test_guia_fundir.py` (união de proibidas, ordem e dedupe das fixas, `M` padrão 5 e da conta, corte com aviso no estado inválido, emojis herdados, os 3 conflitos, `render` completo × `so_proibidas`, seções vazias omitidas, `tamanho`).
- [X] T011 [P] Criar `apps/api/src/sociman_api/ia/schemas_guia.py` em camelCase, exatamente como o contrato ("Tipos"): `Exemplo`, `GuiaCampos` (com `maxHashtagsFixas`), `GuiaLimites` (`hashtagsFixasPerfil`, `hashtagsFixasPadrao`, `hashtagsFixasTeto`), `Guia`, `GuiaEfetivo`, `Conflito`, `GuiaIn` (com `ia?`), `GuiaContaOut`, `MontarIn`, `TestarIn`. Nenhum campo com `tiktok`/`youtube`/`publish` no nome.
- [X] T012 [P] `apps/api/src/sociman_api/ia/tipos.py`: `usa_guia: Literal["completo", "so_proibidas"] = "completo"`, `regras_de` e `listar_regras`; `"so_proibidas"` em `avatar.descricao_prompt`, `cenario.prompt_ambiente` e `avatar.regras_imagem` (Q1). Ajustar `apps/api/tests/unit/test_ia_tipos.py` (os 3 tipos são `so_proibidas`; os outros 10, `completo`).
- [X] T013 [P] `apps/api/tests/fakes/anthropic_fake.py` e `apps/api/tests/fixtures/anthropic/`: formatos `guia` e `variacoes` na resposta padrão; fixtures `proibida_texto.json`, `proibida_postagem.json` (título com "clickbait") e `postagem_sem_fixas.json`; o fake registra o `system` enviado (para os testes de ordem).
- [X] T014 [P] `apps/api/tests/unit/test_constitution_guards.py`, seção "spec 017": as rotas `/api/perfis/{id}/guia*`, `/api/contas/{id}/guia*`, `/api/ia/guia/{montar,testar}` e os `operationId` `guias_*`/`ia_guia_*` passam pela guarda de caminhos do princípio I (sem `publish`, `share`, `post-to`, `upload-to`, `tiktok`, `youtube`, `instagram`); nenhuma rota DELETE com `guia` no caminho; `ia/guia.py`, `ia/service_guia.py` e `ia/router_guia.py` não importam `publicacao`. Os guardas existentes continuam verdes sem mudança.

**Checkpoint:** `npm run test:api -- tests/integration/test_migration_0012.py tests/unit/test_guia_normalizar.py tests/unit/test_guia_fundir.py tests/unit/test_ia_tipos.py tests/unit/test_constitution_guards.py` verde; T003 feito antes de subir no dev.

---

## Phase 3: User Story 1 - Escrever o guia do perfil e da conta (Priority: P1) 🎯 MVP

**Goal**: o dono escreve, salva, vê o histórico e reverte o guia do perfil e o de cada conta; o membro só vê.

**Independent Test**: quickstart §1–§3 (Taverna + @atavernanerd; limites, soma das fixas, validação cruzada, conflitos, membro, reversão, conta arquivada).

### API

- [X] T015 [US1] Criar `apps/api/src/sociman_api/ia/service_guia.py`: `obter_perfil`, `obter_conta` (guia, perfil, efetivo e conflitos), `put_perfil`, `put_conta` (lock `with_for_update`, `check_version` → 409 "Este guia foi alterado por outra pessoa; recarregue", validação 1–5 do data-model com `details.fields` e `details.contas`, `history.record` `created`/`updated` com autor, igual ao atual não cria versão, conta/perfil arquivado → 409 "Esta conta está arquivada", `perfil_id` sempre tirado da conta carregada), `validar_campos(db, perfil, conta, campos)` (a validação 1–5, reusada pelo `testar_guia` da trilha B), `versions_*` (traduz para o `id` da linha; vazio se nunca editado), `revert_*` (snapshot revalidado com as regras de hoje, `reverted` com `details.from_version`; só dono). O `ia` do `GuiaIn` é repassado a `aplicacao.marcar` (alvo `guia`, T043); até lá, ignorado. Nenhum texto do guia em log.
- [X] T016 [US1] Criar `apps/api/src/sociman_api/ia/router_guia.py` com as 8 rotas do contrato ("Guia do perfil" e "Guia da conta"): GET e `versions` com `RequireUser`; PUT e `revert` com `RequireOwner` (403 `forbidden`); `operationId` exatos (`guias_perfil_get`, `guias_perfil_update`, `guias_perfil_versions`, `guias_perfil_revert`, `guias_conta_*`); `DbSession` (armadilha 7). Acréscimo em `apps/api/src/sociman_api/main.py` (`include_router`).
- [X] T017 [P] [US1] Criar `apps/api/tests/integration/test_guia_crud.py`: GET sem guia (`version 0`, campos vazios, `limites`); dono cria (v1 `created`) e membro recebe 403 no PUT e 200 no GET; 404; cada limite do R2 recusado no campo (`faca.3`, `exemplos.5`, `tom`, total > 4.000); repetido recusado; hashtag inválida; proibida do perfil no exemplo da conta (`exemplos.2.texto`); `maxHashtagsFixas` no perfil → 400; 9 → 400; **regra de soma**: perfil 1 + conta 5 com máximo padrão → 400 "perfil e conta somam 6 hashtags fixas; o máximo desta conta é 5"; com `maxHashtagsFixas = 6` → 200; conta sem guia e perfil com 6 fixas → 400 (perfil ≤ 5); conta YouTube com máximo 1 e o perfil tentando a 2ª fixa → 400 com `details.contas` citando a conta; conta arquivada não conta na validação cruzada; proibida nova do perfil usada no vocabulário da conta → `details.contas` com `campos: ["vocabulario"]`; GET da conta com `efetivo` (`maxHashtagsFixas`) e conflitos de emojis e faça × não faça; 409 `version_conflict`; salvar igual não cria versão.
- [X] T018 [P] [US1] Criar `apps/api/tests/integration/test_guia_revert.py`: `versions` do perfil e da conta com autor; revert do dono cria `reverted` com `from_version`; membro → 403; revert para uma versão que hoje viola a validação cruzada → 400; conta arquivada → 409; o histórico da conta (spec 003) não ganha versão e o do guia não muda ao reverter a conta.
- [X] T019 [US1] `npm run gen:contract` (trilha A) e conferir no `packages/contract` os `operationId` `guias_*` e os schemas do T011.

### SPA

- [X] T020 [P] [US1] Criar `apps/web/src/lib/guia.ts`: queries e mutations do guia do perfil e da conta (GET, PUT, versions, revert) com o client gerado; invalida a query do guia e da conta após salvar.
- [X] T021 [US1] Criar `apps/web/src/components/guia/GuiaForm.tsx`: tom, faça, não faça, vocabulário, proibidas, emojis (`NativeSelect`), preferidos, hashtags fixas e exemplos (tipo + texto, até `limites.exemplos`); listas "uma por linha"; contadores por campo e total vindos de `limites` (não copiar números no SPA, princípio IV); no modo conta, o campo **"Máximo de hashtags fixas"** (vazio = `limites.hashtagsFixasPadrao`, até `hashtagsFixasTeto`) e a linha "sobram N vagas para a IA" (`8 − fixas efetivas`); erros por campo de `details.fields` e a lista de `details.contas` (com link para o guia de cada conta); membro: tudo desabilitado, sem Salvar/Montar/Testar. Só tokens de cor do tema (tema escuro da 018 ativo; nada de cor fixa).
- [X] T022 [US1] Criar `apps/web/src/pages/perfis/tabs/GuiaTab.tsx` (formulário + `components/VersionHistory.tsx` com reverter só para o dono) e acrescentar a aba **"Guia"** (`id: "guia"`, `?aba=guia`) em `apps/web/src/pages/perfis/PerfilDetalhe.tsx`.
- [X] T023 [US1] Criar `apps/web/src/components/guia/GuiaHerdado.tsx` ("Vem do perfil", só leitura) e `apps/web/src/components/guia/GuiaConflitos.tsx` (avisos, inclusive `hashtagsFixas`); criar `apps/web/src/pages/perfis/ContaGuia.tsx` (`/app/contas/:id/guia`: herdado + formulário da conta + conflitos + histórico); acréscimo da rota em `apps/web/src/App.tsx`; ação **"Guia de comunicação"** em cada conta de `apps/web/src/pages/perfis/ContasTab.tsx`.

**Checkpoint:** US1 completa pela API e pela tela (quickstart §1–§3); `npm run check:web` verde.

---

## Phase 4: User Story 2 - O guia entra em todo pedido do assistente (Priority: P1)

**Goal**: cada geração leva os guias na ordem da spec (voz completa ou só proibidas, conforme o tipo), garante fixas e proibidas por código, grava as versões e recusa aplicar sem editar.

**Independent Test**: quickstart §4–§5 (Sugerir textos no corte da Taverna; bio; avatar; proibida; "ignore o guia"; `ia_proibida` pela API).

### API

- [X] T024 [US2] `apps/api/src/sociman_api/ia/prompt.py`: `PROMPT_VERSION = "ia/2"`; o parágrafo do guia na BASE, literal do research R4, acima das outras regras; `_TAGS` + `guia_perfil`, `guia_conta`, `guia_em_teste`; `montar_system(tipo, regras, contexto, guias)` na ordem base → regras do tipo → `<guia_perfil versao="N">` → `<guia_conta versao="M">` (só se o alvo tem conta) → `<perfil>` com `cache_control` no último bloco; nos tipos `so_proibidas`, só `<guia_perfil versao="N" parte="proibidas">` com a linha "Palavras proibidas:" e só se houver proibidas; limites de hashtags com `F` fixas e `V = 8 − F` vagas ("de max(3 − F, 1) a V além das fixas"; com `V = 0`, "não gere hashtags: o sistema inclui as fixas").
- [X] T025 [P] [US2] Criar `apps/api/tests/unit/test_prompt_guia.py` e ajustar `apps/api/tests/unit/test_ia_prompt.py` (`ia/1` → `ia/2`, sem mudar o resto): ordem dos blocos; `cache_control` só no último; tags de fechamento removidas do conteúdo do guia; bio sem `<guia_conta>`; perfil sem guia e conta com guia → só `<guia_conta>`; `so_proibidas` sem tom/vocabulário/exemplos; texto dos limites com F = 0, 3 e 8.
- [X] T026 [US2] `apps/api/src/sociman_api/ia/saida.py`: `problemas`/`finalizar` recebem o `GuiaEfetivo`; fixas nos formatos `lista`, `textos_postagem` (e `variacoes`, T041): normaliza as do modelo, tira as que repetem uma fixa, **fixas primeiro**, corta em 8 (as do modelo saem, as fixas nunca), ajuste `hashtags_fixas_incluidas`; `problemas` conta o total depois das fixas (com `V = 0`, não pede mínimo ao modelo); proibidas (`achar_proibidas` em todo texto da proposta, também nos tipos `so_proibidas`) → "usou a palavra proibida X" em `problemas` (2ª tentativa da 008) e, se continuar, `proibidas` + o aviso "A proposta usa uma palavra proibida pelo guia (X); edite antes de aplicar."; emoji com `emojis = nao` → só aviso; aviso do estado inválido herdado das fixas. `apps/api/src/sociman_api/ia/cliente.py`: repassa o `GuiaEfetivo` junto do `Excluir` (sem mudar a chamada ao Claude).
- [X] T027 [P] [US2] Criar `apps/api/tests/unit/test_saida_guia.py`: fixas entram e ficam primeiro; corte em 8 preserva as fixas; `V = 0`; proibida em título, descrição, hashtag e item de lista; proibida num tipo `so_proibidas`; aviso de emoji; nada muda sem guia (regressão da 008 em `test_ia_saida.py` sem alteração).
- [X] T028 [US2] `apps/api/src/sociman_api/ia/service.py::executar`: carrega `guia.em_vigor` (perfil sempre; conta só se `AlvoResolvido.conta`; nos `so_proibidas`, só as proibidas do perfil), passa ao prompt e à saída, grava `guia_perfil_version`/`guia_conta_version` (só quando o bloco foi enviado) e `proibidas`; `chamadas_out` com os campos novos. `apps/api/src/sociman_api/ia/schemas.py`: `IaChamada` + `guiaPerfilVersion`, `guiaContaVersion`, `guiaRascunho`, `proibidas`; `TipoCampo` + `usaGuia`; `AlvoTipo` + `"guia"`; `GET /api/ia/tipos` com `usaGuia`.
- [X] T029 [US2] `apps/api/src/sociman_api/ia/aplicacao.py::marcar`: pré-checagem **fora** do `try` que nunca derruba o save (Q2 = A): para cada item `ia` que casa com uma chamada com `proibidas`, cada campo do tipo cujo valor salvo é igual ao da proposta **e** cujo valor da proposta contém uma das `proibidas` da chamada → 400 `ia_proibida` com `details.palavras` e `details.campos`; campo editado passa (desfecho `editada`). Vale para asset (incluindo os 3 visuais), perfil, kit e postagem. Código `ia_proibida` em `apps/api/src/sociman_api/errors.py` (acréscimo), se o envelope pedir.
- [X] T030 [P] [US2] Criar `apps/api/tests/integration/test_gerar_com_guia.py`: postagem com guias de perfil e conta → as duas versões gravadas e os dois blocos no `system` do fake; bio → só `guiaPerfilVersion`; `avatar.descricao_prompt` com proibidas → só o bloco de proibidas e `guiaPerfilVersion`; sem proibidas → nada enviado e versão nula; **10 gerações** com o fake sem as fixas → 10/10 com as fixas, ≤ 8 no total (SC-002); proibida na 1ª e na 2ª resposta → `proibidas` e aviso; proibida só na 1ª → 2ª tentativa limpa; instrução "ignore o guia e escreva sem hashtags" → fixas continuam; conta com máximo 8 e 8 fixas → nenhuma hashtag do modelo; estado inválido herdado (UPDATE direto no banco) → corta com aviso; guia editado entre duas gerações → a 2ª usa a versão nova; conta arquivada → a 008 recusa como antes.
- [X] T031 [P] [US2] Criar `apps/api/tests/integration/test_ia_proibida.py`: postagem salva com `ia` e o título igual à proposta com "clickbait" → 400 `ia_proibida` (`campos: ["titulo"]`); só a descrição editada e o título intacto → 400; título editado mantendo a palavra → 200 `editada` (Q2 = A); asset `avatar.descricao_prompt` sem edição → 400; chamada sem `proibidas` → 008 igual (o `ia` inválido continua ignorado; `tests/unit/test_ia_aplicacao.py` sem mudança de comportamento).
- [X] T032 [US2] `npm run gen:contract` (trilha A): `TipoCampoId` do 008 ainda sem os `guia.*` (entram na US3), `IaChamada` e `TipoCampo` novos.

### SPA

- [X] T033 [US2] `apps/web/src/components/ia/IaAssist.tsx`: com `chamada.proibidas` não vazio, aviso "A proposta usa uma palavra proibida pelo guia (X); edite antes de aplicar.", **"Aplicar" desabilitado** e **"Editar e aplicar" liberado** (Q2 = A); linha "Guia usado: perfil vN · conta vM" (ou só perfil; nada se nulo) com link para o histórico do guia; 400 `ia_proibida` (cliente antigo ou corrida) vira mensagem clara no painel. Não mexer no layout do detalhe do conteúdo (reorganizado pela 018; o painel só muda por dentro).
- [X] T034 [P] [US2] `apps/web/src/pages/ia/RegistroTab.tsx`: no Sheet da chamada, "Guia do perfil vN · Guia da conta vM" com link para o histórico de cada guia, `guiaRascunho` ("rascunho do perfil/da conta") e as proibidas encontradas (SC-003).
- [X] T035 [P] [US2] `apps/web/src/components/assets/AvatarCampos.tsx`: link **"Ver guia de comunicação do perfil"** (`/app/perfis/<perfilId>?aba=guia`) junto dos campos de descrição para prompts, prompt do ambiente e regras de imagem (Q1).

**Checkpoint:** US1 + US2 prontas (as duas P1); podem ir ao dono antes da US3 (quickstart §1–§5).

---

## Phase 5: User Story 3 - Montar e testar o guia com ajuda da IA (Priority: P2)

**Goal**: o dono pede um guia inicial a partir de uma descrição e testa o guia do formulário com 3 variações, sem salvar nada além da chamada.

**Independent Test**: quickstart §6 (Queridinhos: montar, ajustar, testar, salvar; `guia.montar` `editada`, `guia.testar` com `guiaRascunho = perfil`).

### API

- [X] T036 [US3] `apps/api/src/sociman_api/ia/tipos.py`: `Entidade` + `"guia"`; `Formato` + `"guia"`, `"variacoes"`; `TipoCampoId` + `"guia.montar"`, `"guia.testar"`; `guia.montar` (`entidade="guia"`, `formato="guia"`, idioma do perfil) e `guia.testar` (`entidade="postagem"`, `formato="variacoes"`, `regras_de="postagem.textos"`, `listar_regras=False`). `apps/api/src/sociman_api/ia/regras_padrao.py`: padrão de `guia.montar` (no guia da conta, só o que a conta acrescenta ao perfil). `apps/api/src/sociman_api/ia/service_regras.py`: `listar` pula `listar_regras=False`; `regras_em_vigor` segue `regras_de`. `apps/api/tests/unit/test_ia_tipos.py`: o cruzamento tipos × schemas ignora os `guia.*`, e o `guia.montar` é cruzado com `GuiaIn`.
- [X] T037 [US3] `apps/api/src/sociman_api/ia/saida.py`: `PropostaGuia` (`tom`, `faca`, `naoFaca`, `vocabulario`, `proibidas`, `emojis`, `emojisPreferidos`, `explicacao`, `avisos`; **sem** fixas, máximo e exemplos) com os limites do R2 (`problemas` → 2ª tentativa; `finalizar` corta listas longas com aviso); `PropostaVariacoes` (exatamente 3 × `{titulo, descricao, hashtags}`), cada variação pelo `_ajustar_postagem` da 006, pelas fixas e pelas proibidas do guia **em teste**.
- [X] T038 [US3] `apps/api/src/sociman_api/ia/service.py`: `montar_guia` (dono; `descricao` → `<instrucao>`, `guiaAtual` → `<valor_atual>`, no guia da conta o do perfil salvo vai como `<guia_perfil>`; arquivado → 409; sessão/anteriores/descartar da 008) e `testar_guia` (dono; valida o formulário com as regras do PUT **antes** de chamar o Claude — 400 campo a campo, sem gastar; `contaId` obrigatório; nível em teste do formulário em `<guia_em_teste>`, o outro nível salvo; grava só a chamada com `tipo_campo = "guia.testar"`, `guia_rascunho = nivel`, a versão base (0 se não havia), `entrada = {"guia": …}`, desfecho `sem_acao`; nenhuma versão, nenhum conteúdo).
- [X] T039 [US3] `apps/api/src/sociman_api/ia/router.py`: `POST /api/ia/guia/montar` (`ia_guia_montar`) e `POST /api/ia/guia/testar` (`ia_guia_testar`), ambos `RequireOwner`, com os erros do contrato (400 `invalid_ia`/`validation_error`, 403, 404, 409, 502, 503, 504).
- [X] T040 [US3] `apps/api/src/sociman_api/ia/aplicacao.py`: alvo `guia` no `marcar` (o `put_*` do T015 repassa `ia: [{tipoCampo: "guia.montar", chamadaId}]`): `aplicada` se os campos da proposta ficaram iguais, `editada` se não; `details.ia` na versão do guia.
- [X] T041 [P] [US3] Criar `apps/api/tests/integration/test_guia_montar.py`: proposta dentro dos limites, sem fixas/máximo/exemplos; nada salvo (`version` continua 0); save com `ia` → chamada `editada` e `details.ia` na versão; membro → 403; conta: o guia do perfil vai no `system` do fake; e `apps/api/tests/integration/test_guia_testar.py`: 3 variações com as fixas do guia **em teste** e proibidas marcadas; formulário inválido → 400 sem chamada ao fake; sem `contaId` → 400; chamada com `guiaRascunho`, `entrada.guia` e `sem_acao`; nenhuma versão criada e nenhum destino mudou; `GET /api/ia/tipos` lista `guia.montar` e não lista `guia.testar`.
- [X] T042 [US3] `npm run gen:contract` (trilha A): `TipoCampoId` com os `guia.*`, `Valor` com `guia`/`variacoes`, `MontarIn`/`TestarIn`.

### SPA

- [X] T043 [P] [US3] Criar `apps/web/src/components/guia/MontarGuiaDialog.tsx` (descrição → proposta → preenche o formulário, sem salvar; "Outra versão" e descartar da 008; guarda o `chamadaId` para o `ia` do Salvar) e `apps/web/src/components/guia/TestarGuiaDialog.tsx` (escolhe corte/conteúdo e conta — sugere a 1ª conta ativa —, mostra as 3 variações lado a lado, erros do formulário por campo); botões "Montar com IA" e "Testar guia" no `GuiaForm` (só dono) e o selo "com ajuda da IA" (`IaSelo`) na versão com `details.ia`; `apps/web/src/lib/guia.ts` com as duas mutations.

**Checkpoint:** as 3 histórias completas pela API e pela tela.

---

## Phase 6: e2e (Claude falso na stack efêmera)

- [X] T044 [P] `e2e/fakes/server.py` (acréscimo no bloco do Claude): formatos `guia` e `variacoes` (3 variações); resposta de postagem **sem** as fixas (o servidor é quem inclui); gatilho "proibida" na `<instrucao>` devolve texto com a 1ª palavra de "Palavras proibidas:" do `system` nas duas tentativas; tipo `so_proibidas` reconhecido pelo `parte="proibidas"`.
- [X] T045 Criar `e2e/guia-comunicacao.spec.ts` (plan, "Testing"): dono escreve o guia do perfil e o da conta (herdado visível), 6º exemplo e soma de fixas recusados no campo, máximo da conta 6 → salva e "sobram 2 vagas" [US1]; conflito de emojis na conta [US1]; membro vê tudo desabilitado [US1]; reverter [US1]; "Sugerir textos" num corte com a fixa presente e "Guia usado: perfil v… · conta v…" [US2]; instrução "proibida" → aviso, "Aplicar" desabilitado, "Editar e aplicar" salva [US2]; registro mostra as versões [US2]; avatar: link "Ver guia de comunicação do perfil" abre a aba Guia [US2]; montar → formulário preenchido e versão 0 até salvar; testar → 3 variações [US3]. Usar `NativeSelect` e `role="alertdialog"` como nos outros e2e; acréscimos em `e2e/helpers.ts` só se precisar.
- [ ] T046 Rodar `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/guia-comunicacao.spec.ts` e depois `flock /tmp/sociman-e2e.lock npm run test:e2e` inteiro (`assistente-ia.spec.ts`, `assets.spec.ts` e `conteudos.spec.ts` continuam verdes). Nunca `npx playwright test` direto.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T047 `npm run test:api` inteiro verde (inclui `test_migration_0012`, `test_guia_*`, `test_prompt_guia`, `test_saida_guia`, `test_gerar_com_guia`, `test_ia_proibida`, `test_constitution_guards` e os da 008 sem regressão) e `docker compose exec api uv run ruff check .` sem erros.
- [ ] T048 `npm run gen:contract && npm run check:web` (contrato igual, typecheck, build, bundle sem segredo, CSP igual — nenhuma origem nova).
- [X] T049 Subir no dev (depois do T003): quickstart §0 (`alembic current` = `0012_guia_comunicacao`, `\d ia_guias`, a contagem da linha de base do T002 igual e as chamadas antigas com `proibidas = '{}'`).
- [X] T050 [P] Revisão de logs: `docker compose logs api | grep -iE "guia_perfil|guia_conta|clickbait|taverneiro"` não acha texto de guia (só ids, versões e contagens).
- [ ] T051 [DONO] Quickstart §1–§6 com o **Claude real** (alguns centavos): SC-001 (< 5 min com a IA), SC-002 (10 gerações: 10/10 fixas, 0 proibidas aplicáveis sem edição), SC-003 (versões no registro), SC-004 (histórico e reversão). **Registrar** em `quickstart.md` (seção "Resultado", acréscimo).
- [X] T052 `CLAUDE.md` (acréscimo, **só no fim**): seção "Guia de comunicação (desde a spec 017)": `ia_guias` por perfil e conta, só o dono edita; ordem do `system` (`ia/2`); `usa_guia` completo × `so_proibidas` (os 3 campos visuais); regra de soma das fixas (perfil ≤ 5, máximo por conta 0..8, padrão 5); proibidas por palavra inteira e `ia_proibida` só para campo sem edição; `guia.montar`/`guia.testar` no registro.
- [X] T053 `docs/visao.md` (acréscimo, **só no fim**): marcar a 017 e registrar o resultado do T051; no backlog, os itens de R13 (exemplos pelas métricas da 016, guia pelo MCP, variações automáticas das proibidas, 2º ponto de cache).
- [ ] T054 Marcar `specs/017-guia-de-comunicacao/checklists/requirements.md` e este `tasks.md`; conferir que `open-questions.md` segue resolvido.
- [ ] T055 [DONO] Validação final do dono na tela (guia da Taverna e da Queridinhos em uso); ajustes pedidos viram tarefas novas aqui.
- [ ] T056 Commit e push **só quando o dono pedir**, em pt-BR, no imperativo.
- [ ] T057 [DONO] Apagar o backup `pre-0012.dump` do T003, **só** com a confirmação do dono e depois do T055.

---

## Dependencies & Execution Order

### Phase Dependencies
- Setup (T001–T004): T001 primeiro; T002 → T003 antes de subir a migration no dev (T049); T004 em paralelo.
- Foundational (T005–T014): T005 → T006 → T007 → T008; T009 depois do T005 (usa `IaGuia` só no `em_vigor`); T010 depois do T009; T011, T012, T013, T014 em paralelo depois do T005. **Bloqueia todas as histórias.**
- US1 (T015–T023): T015 → T016 → T017, T018 (paralelos) → T019; SPA: T020 depois do T019; T021 → T022, T023.
- US2 (T024–T035): depende da Foundational (T009, T012, T013) e do T015 (`em_vigor` testado com guias reais). T024 → T025; T026 → T027; T028 depois do T024 e do T026; T029 → T031; T030 depois do T028; T032 depois do T028/T029; SPA T033–T035 depois do T032.
- US3 (T036–T043): depende da US2 (prompt `ia/2`, saída com fixas/proibidas). T036 → T037 → T038 → T039; T040 depois do T015 e do T036; T041 depois do T039 e do T040; T042 → T043.
- e2e (T044–T046): T044 a qualquer momento depois da Foundational; T045 cresce por história; T046 no fim de cada história e no fim de tudo.
- Polish por último; T052 e T053 só no fim; T057 por último.

### Parallel Opportunities
- Foundational: T011, T012, T013, T014 (arquivos diferentes); T010 com eles depois do T009.
- US1: T017 × T018; SPA T020 × a API da US2 (trilhas diferentes).
- US2: T025 × T027 × T030 × T031 (arquivos de teste diferentes); T034 × T035.
- US3: T041 × T043 (depois do T042).

---

## Trilhas para agentes paralelos

Quatro agentes, sem arquivo em comum. Cada trilha só edita os arquivos listados; qualquer outro pede coordenação pelo líder. Os arquivos "só acréscimo" do topo podem receber blocos de qualquer trilha. As tarefas **[DONO]** ficam com o líder e o dono.

| Trilha | Agente sugerido | Tarefas | Arquivos (exclusivos) |
|---|---|---|---|
| **A: API base e guia** (modelo, migration, domínio, CRUD, contrato) | `api-017-guia` | T001–T011, T014–T019, T032, T042, T047–T050 | `apps/api/migrations/versions/0012_guia_comunicacao.py`; `ia/models.py`; `ia/guia.py`; `ia/schemas_guia.py`; `ia/service_guia.py`; `ia/router_guia.py`; acréscimos em `main.py` e `tests/conftest.py`; `tests/unit/{test_guia_normalizar,test_guia_fundir,test_constitution_guards}.py`; `tests/integration/{test_migration_0012,test_guia_crud,test_guia_revert}.py` e os de migration anteriores. **Única trilha que roda `npm run gen:contract`** e toca `packages/contract/**` (a pedido de B) |
| **B: API do assistente** (tipos, prompt, saída, registro, aplicação, montar/testar) | `api-017-prompt` | T012, T013, T024–T031, T036–T041 | `ia/{tipos,regras_padrao,service_regras,prompt,saida,cliente,service,aplicacao,schemas,router}.py`; acréscimo em `errors.py`; `tests/fakes/anthropic_fake.py`, `tests/fixtures/anthropic/**`; `tests/unit/{test_ia_tipos,test_ia_prompt,test_prompt_guia,test_saida_guia}.py`; `tests/integration/{test_gerar_com_guia,test_ia_proibida,test_guia_montar,test_guia_testar}.py` |
| **C: SPA** | `spa-017` | T020–T023, T033–T035, T043 | `apps/web/**` (novos em `components/guia/`, `pages/perfis/tabs/GuiaTab.tsx`, `pages/perfis/ContaGuia.tsx`, `lib/guia.ts`; alterações em `pages/perfis/{PerfilDetalhe,ContasTab}.tsx`, `components/ia/IaAssist.tsx`, `pages/ia/RegistroTab.tsx`, `components/assets/AvatarCampos.tsx`; acréscimo em `App.tsx`) |
| **D: e2e, verificação e docs** | `e2e-017` | T044–T046, T051 (com o líder), T052–T054, T057 (com o líder) | `e2e/guia-comunicacao.spec.ts`, acréscimos em `e2e/fakes/server.py` e `e2e/helpers.ts`, `specs/017-guia-de-comunicacao/{quickstart,tasks}.md` e `checklists/`, `CLAUDE.md`, `docs/visao.md` |

Interfaces entre trilhas (combinar a assinatura antes de começar):
- A entrega `ia/guia.py` (T009) antes de B começar o T024/T026; B só **lê** `guia.py` (mudança pedida a A).
- A chama `aplicacao.marcar(..., "guia", ...)` no `service_guia.put_*`; B implementa o alvo `guia` (T040). Até o T040, o `ia` do `GuiaIn` é ignorado.
- B chama `service_guia.validar_campos(...)` (A, T015) no `testar_guia` (T038), para a mesma validação do PUT.
- Colisões externas: `IaAssist.tsx` e `AvatarCampos.tsx` podem estar sendo mexidos pela 018; C confere `git diff` desses arquivos com o líder antes de editar. `e2e/fakes/server.py` e `helpers.ts` também são da 016: só acréscimo.

Sincronização:
1. O líder faz o T001; A faz T002–T003 e a Foundational (T005–T011, T014); B faz T012 e T013 em paralelo.
2. Depois do checkpoint da Foundational: A faz a US1 na API (T015–T019); B começa a US2 (T024–T027). C começa o T020 assim que o T019 sair; D faz o T044.
3. B termina a US2 (T028–T031); A roda o T032; C faz T033–T035.
4. B faz a US3 (T036–T041); A roda o T042; C faz o T043.
5. D escreve o T045 por história e roda o T046 **sempre** com `flock /tmp/sociman-e2e.lock`.
6. A roda T047–T050; o líder conduz o T051 com o dono; D faz T052–T054 no fim; T057 por último.

---

## Implementation Strategy

### MVP (US1 + US2, as duas P1)
1. T001 → Setup (linha de base, backup) → Foundational (migration testada nos dois sentidos, domínio do guia, schemas, fake, guardas).
2. US1 (guia com histórico e reversão, regra de soma das fixas) → US2 (prompt `ia/2`, fixas e proibidas por código, versões no registro, `ia_proibida`).
3. **Parar e validar com o dono** (quickstart §1–§5).

### Incremental
US3 (montar e testar) → e2e completo → Polish (Claude real com o dono, docs, backup apagado).

## Notes
- Nenhuma dependência nova, nenhum serviço novo, nenhuma `location` nova no edge, CSP igual.
- Nenhuma rota DELETE; "limpar" o guia é salvar vazio (nova versão).
- Gerar, montar e testar **não criam versão**; só o Salvar e o reverter do dono criam.
- Commit só quando o dono pedir, em pt-BR, no imperativo.
