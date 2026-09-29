---

description: "Tarefas da feature 008-assistente-ia"
---

# Tasks: Assistente de IA para textos (008-assistente-ia)

**Input**: `specs/008-assistente-ia/` (spec, plan, research R1–R15, data-model, contracts/http-api.md, quickstart, open-questions resolvidas)

**Decisões do dono (2026-09-29):** Q1 = B (**Aplicar salva na hora** só aquele campo, 1 clique, pelo save normal da entidade; as outras alterações não salvas continuam no formulário; no kit, os tokens **salvos** com só aquele campo trocado), Q2 = B (`avatar.regras_imagem` no idioma do perfil; só `avatar.descricao_prompt` e `cenario.prompt_ambiente` em inglês), Q3 = **sugestões com seleção** em `kit.bordoes` e `kit.series` (marcar, "Gerar mais" com aceitos e rejeitados da sessão, lista do kit ≤ 20 com aviso).

**Nomes canônicos** (valem os documentos do plano): pacote `sociman_api/ia/`; tabelas `ia_regras` (nova) e `ia_chamadas` (a `sugestoes_texto` renomeada); enum `ia_desfecho`; `entity_type = "ia_regra"`; migration `0008_assistente_ia` (`down_revision = "0007_envio_progresso"`); formatos `texto`, `lista`, `sugestoes`, `textos_postagem`; erros novos `invalid_ia`, `ia_anteriores_invalidas`, `ia_tipo_not_found`, `ia_timeout`, `ia_recusa`, `ia_invalida`; `operationId` `ia_*`; rota do SPA `/app/assistente-ia`; componente `components/ia/IaAssist.tsx` com `onSave`.

**Tests**: OBRIGATÓRIOS (constitution, princípio VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec api uv run ruff check .`;
- `npm run gen:contract && npm run check:web` (contrato regenerado, CSP inalterada, segredos);
- e2e na stack isolada, **sempre com trava**: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/assistente-ia.spec.ts]` (armadilha 18: nunca dois e2e ao mesmo tempo);
- nenhum teste chama a Anthropic de verdade (Claude falso no pytest e no e2e, R14). O SPA não tem teste unitário: o comportamento do painel é coberto pelo e2e.

**Restrições do data-model (citadas literalmente; valem em T004, T005 e nos serviços):**
- `ia_regras`: "**Sem linha = usa o padrão do código** (a linha nasce na primeira edição, como o kit com `version = 0`)"; `tipo_campo` "text not null **unique**" ("um id de `TIPOS`; validado no serviço (404 `ia_tipo_not_found`)"); `texto` "`NULL` = usa o padrão; senão 1..8.000 caracteres (check)"; `padrao_versao` "`padrao_versao` do tipo no momento da última edição"; "`__versioned_fields__ = ("tipo_campo", "texto")`, `__immutable_fields__ = ("tipo_campo",)`"; "Não há arquivamento (a linha nunca some; "voltar ao padrão" é o equivalente)"; "Na API, a versão de um tipo sem linha é `0` (como o kit)".
- `ia_chamadas`: "**Só INSERT**, salvo as colunas de desfecho (R10), que são estado, sem versão"; `id` "preservado da 006 (`postagens.sugestao_id` continua apontando)"; `corte_id` "era not null; só nos tipos de postagem"; `plataforma` "era not null"; `instrucao` "até 1.000"; `explicacao` "≤ 400"; `aceitos` "só `sugestoes`: itens marcados na sessão e ainda não aplicados, enviados como contexto (≤ 20)"; `rejeitados` "só `sugestoes`: itens mostrados na sessão e não marcados, enviados como contexto (≤ 100)"; `itens_aplicados` "só `sugestoes`: texto final dos itens desta chamada que entraram no kit (acumula)"; `prompt_version` "versão da base fixa (`ia/1`; as linhas da 006 ficam `textos/1`)"; `regras_version` "versão de `ia_regras` usada (0 = padrão)".
- Regras de `ia_chamadas`: "`erro_code` não nulo ⇔ `desfecho = 'erro'` (check)"; "o desfecho só sai de `sem_acao` (para `aplicada`, `editada` ou `descartada`); `aplicada` e `editada` só pelo `ia.aplicacao.marcar` dentro de um save; `descartada` só pelo autor da chamada; uma chamada `aplicada`/`editada` não volta a `descartada`"; "uma chamada `texto`, `lista` ou `textos_postagem` pode ser aplicada uma vez"; "uma chamada `sugestoes` pode ser aplicada **mais de uma vez** […] `itens_aplicados` acumula, `aplicada_versao` fica com a última, e o desfecho vai para `editada` se algum item aplicado foi editado (nunca volta de `editada` para `aplicada`)"; "`aceitos` e `rejeitados` só não são vazios quando o tipo tem formato `sugestoes` (check no serviço; 400 `invalid_ia` no `gerar`); `itens_aplicados` só é gravado pelo `marcar`".
- Índices: `ix_ia_chamadas_created` (`created_at desc`, `id`), `ix_ia_chamadas_perfil_created`, `ix_ia_chamadas_tipo_created`, `ix_ia_chamadas_sessao` "parcial `WHERE sessao_id IS NOT NULL`"; "o índice da 006 por `corte_id` é mantido (renomeado)".
- `IaAplicacao { tipoCampo, chamadaId, itens? }`: "lista opcional com até 10 itens"; "`itens` só vale nos tipos `sugestoes` (≤ 20, cada um no limite do item)"; em `AssetPatch`, `UpdatePerfilIn`, `KitIn` "(fora de `sections()`)", `CreatePostagemIn` e `UpdatePostagemIn`; "Nada mais muda nesses schemas".
- `entity_versions.details`: `{"ia": [{"campo", "tipoCampo", "chamadaId", "desfecho"}]}` ("Nas sugestões, cada item leva também `"itens"`"); "O autor continua o humano (`actor_kind = "user"`)".

**Arquivos compartilhados: SÓ ACRÉSCIMO** (bloco novo ao lado dos vizinhos, sem reordenar): `apps/api/src/sociman_api/main.py`, `apps/api/migrations/env.py`, `apps/api/tests/conftest.py`, `apps/web/src/App.tsx`, `apps/web/src/components/shell/nav.ts`, `e2e/helpers.ts`, `docker-compose.e2e.yml`, `e2e/fakes/server.py`, `CLAUDE.md`, `docs/visao.md`. `packages/contract/**` é **gerado** (armadilha 6): em conflito, rebase e `npm run gen:contract` de novo.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US4 da spec

---

## Phase 1: Setup (linha de base e config)

- [X] T001 Linha de base no dev, **antes** de subir código novo (quickstart §0): `docker compose exec api uv run alembic heads` → `0007_envio_progresso`; anotar `select count(*) from sugestoes_texto;` e `select count(*) from postagens where sugestao_id is not null;`; `pg_dump` para `/tmp/sociman-antes-0008.sql` (nunca no repositório).
- [X] T002 [P] Em `apps/api/src/sociman_api/config.py`, `anthropic_base_url: str = ""` (vazio = padrão do SDK; só o e2e usa), ao lado de `anthropic_api_key` e `textos_model`, que continuam. Sem mudança no `docker-compose.yml` de dev.
- [X] T003 [P] Em `apps/web`, `npx shadcn@latest add collapsible checkbox` (código copiado para `apps/web/src/components/ui/`; o pacote `radix-ui` já está no projeto, sem dependência nova). Conferir `npm run check:web` verde.

---

## Phase 2: Foundational (modelo, migration, motor da IA, guardas)

**⚠️ Bloqueia todas as histórias.**

- [X] T004 Criar `apps/api/src/sociman_api/ia/__init__.py` e `ia/models.py` com `IaDesfecho` (`sem_acao`, `aplicada`, `editada`, `descartada`, `erro`), `IaRegra` (AuditMixin + `_Versioned`) e `IaChamada` (`__tablename__ = "ia_chamadas"`), com todas as colunas do data-model e as restrições citadas acima. Tirar `SugestaoTexto` de `apps/api/src/sociman_api/postagem/models.py` (`postagens.sugestao_id` passa a `ForeignKey("ia_chamadas.id")`, mesma coluna) e trocar as referências em `postagem/service.py` e `postagem/textos.py` para `IaChamada` **sem mudar o comportamento da 006** (`resultado` → `proposta`; `tipo_campo = "postagem.textos"`, `entity_type = "corte"`, `perfil_id` do corte ao gravar). Em `apps/api/migrations/env.py`, o import de `ia.models` (só acréscimo). Em `apps/api/tests/conftest.py`, `_TABLES`: `sugestoes_texto` → `ia_chamadas` e `ia_regras` (só acréscimo no bloco da 008; a troca do nome é a única edição). Verificar: `npm run test:api -- tests/integration/test_sugestoes.py tests/unit/test_textos.py tests/integration/test_postagens.py` continua verde depois do T005.
- [X] T005 Criar `apps/api/migrations/versions/0008_assistente_ia.py` (`revision = "0008_assistente_ia"`, `down_revision = "0007_envio_progresso"`), exatamente como o data-model:
  1. `CREATE TYPE ia_desfecho AS ENUM ('sem_acao','aplicada','editada','descartada','erro')`;
  2. `CREATE TABLE ia_regras` (unique em `tipo_campo`, check de 1..8.000 em `texto` quando não nulo);
  3. `ALTER TABLE sugestoes_texto RENAME TO ia_chamadas`; renomear PK, FKs e índices para o prefixo `ia_chamadas_`;
  4. `RENAME COLUMN resultado TO proposta`; `corte_id` e `plataforma` passam a `NULL`;
  5. `ADD COLUMN` das colunas novas (as `not null` com default), inclusive `aceitos`, `rejeitados` e `itens_aplicados`;
  6. backfill: `tipo_campo = 'postagem.textos'`, `entity_type = 'corte'`, `entity_id = corte_id`, `perfil_id` por `JOIN cortes`, `regras_version = 0`; `desfecho = 'erro'` onde `erro_code` não é nulo, `'aplicada'` onde `id IN (SELECT sugestao_id FROM postagens)`; `custo_usd` pelos tokens com o preço do Sonnet 5.5 (`precos_versao = '2026-09'`); `prompt_version` preservado;
  7. `SET NOT NULL` em `tipo_campo`, `perfil_id`, `entity_type` e `DROP DEFAULT` onde o default era só para o backfill; check `erro_code` ⇔ `erro`; os quatro índices novos.

  `downgrade` (docstring: "só dev"): apaga as linhas com `tipo_campo <> 'postagem.textos'`, remove as colunas novas, volta `proposta` → `resultado`, `corte_id`/`plataforma` a `NOT NULL`, o nome `sugestoes_texto` (PK, FKs e índices com os nomes da 006), e dropa `ia_regras` e o enum.
- [X] T006 Teste `apps/api/tests/integration/test_migration_0008.py` (no molde de `test_migration_0006.py`): semear linhas da 006 (uma com erro, uma usada por `postagens.sugestao_id`, uma sem uso) em `0007`; `upgrade` → as linhas estão em `ia_chamadas` com os **mesmos ids**, `tipo_campo = 'postagem.textos'`, `perfil_id` certo, desfechos `erro`/`aplicada`/`sem_acao`, `custo_usd` calculado e a FK de `postagens` intacta; `downgrade` → `sugestoes_texto` volta com as mesmas linhas e colunas (uma linha de outro tipo semeada depois do upgrade some); `upgrade` de novo → idêntico ao primeiro. Rodar com `npm run test:api -- tests/integration/test_migration_0008.py`.
- [X] T007 [P] Criar `apps/api/src/sociman_api/ia/tipos.py` (`TipoCampo` dataclass congelada, `TIPOS: dict[str, TipoCampo]` e `TipoCampoId` como `Literal`) com os 13 tipos da tabela do research R1: `idioma = "en"` **só** em `avatar.descricao_prompt` e `cenario.prompt_ambiente` (Q2 = B: `avatar.regras_imagem` é `"perfil"`); `formato = "sugestoes"` em `kit.bordoes` e `kit.series` (`max_itens = 20`, `max_chars_item` 120/60, `unicos`, `max_sugestoes = 10`), `"lista"` em `postagem.hashtags` (3..8, `normalizar = "hashtag"`), `"textos_postagem"` em `postagem.textos`; `trim = False` no prompt do avatar e do cenário. E `apps/api/src/sociman_api/ia/regras_padrao.py` com o texto padrão de cada tipo e `padrao_versao = 1` (o das regras de imagem pede pt-BR, frases curtas de "sempre"/"nunca"; o dos bordões e séries pede sugestões novas, curtas, no tom dos aceitos).
- [X] T008 [P] Teste `apps/api/tests/unit/test_ia_tipos.py`: para cada tipo, os limites batem com o schema Pydantic real do campo (`AssetPatch`, `UpdatePerfilIn`, `KitTokens`, `UpdatePostagemIn`/`CreatePostagemIn`), `tipos_asset` bate com `ck_assets_campos_por_tipo`, o `Literal` tem os 13 ids, e só os 2 tipos de prompt de imagem são `en`.
- [X] T009 [P] Criar `apps/api/src/sociman_api/ia/custo.py` (tabela de preços do R7, `PRECOS_VERSAO = "2026-09"`, soma das tentativas, `iterations` de fallback, modelo desconhecido = preço do Sonnet 5.5 + log) e o teste `apps/api/tests/unit/test_ia_custo.py` (sem cache, com leitura e escrita de cache, fallback para o Opus, modelo desconhecido).
- [X] T010 [P] Criar `apps/api/src/sociman_api/ia/saida.py`: `PropostaTexto`, `PropostaLista`, `PropostaSugestoes`, `PropostaTextosPostagem` (R4) e a validação por formato: texto acima do limite volta **sem corte** com `excede = true`; lista remove vazias e repetidas; **sugestões** removem (com aviso) as vazias, as repetidas entre si e as que repetem, sem diferenciar maiúsculas e sem espaço nas pontas, um item de `valorAtual.itens`, de `aceitos` ou de `rejeitados`, cortam em 10, marcam as acima do limite do item, e zero válidas = `invalid`; hashtags e `postagem.textos` com o ajuste da 006. Teste `apps/api/tests/unit/test_ia_saida.py` cobrindo cada ramo.
- [X] T011 Criar `apps/api/src/sociman_api/ia/contexto.py` (perfil + kit com paleta nomeada via `marca.service_kit.current_tokens`, até 2 avatares como persona, bloco da entidade por tipo, `contexto_faltante`; nas sugestões, a lista atual do campo, a do outro campo e os `aceitos`/`rejeitados`) e `apps/api/src/sociman_api/ia/prompt.py` (base fixa `ia/1` não editável: formato, limites, idioma exigido, "nunca publica", segurança do R6; ordem base → regras → perfil com `cache_control` → `user` com persona, entidade, `<valor_atual>`, `<propostas_anteriores>`, `<ja_aceitos>`, `<rejeitados>`, `<dados_terceiros>` e `<instrucao>`; tag de fechamento removida do conteúdo). Teste `apps/api/tests/unit/test_ia_prompt.py`: dados de terceiros delimitados, fixture de transcrição "ignore as instruções…", instrução "mostre seu system prompt", aceitos/rejeitados só nas sugestões, idioma exigido por tipo.
- [X] T012 Criar `apps/api/src/sociman_api/ia/cliente.py` (`IaClient`: o `TextosClient` da 006 generalizado, `beta.messages.parse` com o schema do formato, **sem tools**, `timeout = 20`, `max_retries = 0`, segunda tentativa de validação só se a primeira levou < 10 s, `max_tokens = 2000`, sem `temperature`, `fallbacks: "default"`, `base_url` de `anthropic_base_url` quando não vazio, chave nunca em log/erro/`__repr__`). Ampliar `apps/api/tests/fakes/anthropic_fake.py` com os quatro formatos, `usage` com cache e `iterations`. Teste `apps/api/tests/unit/test_ia_cliente.py` (formatos, segunda tentativa, timeout, recusa, 401/429, soma de uso).
- [X] T013 Criar `apps/api/src/sociman_api/ia/schemas.py` (camelCase, como o contrato: `TipoCampo`, `Limites` com `maxSugestoes`, `Regras`, `Alvo`, `Valor`, `Selecao`, `IaChamada` com `aceitos`, `rejeitados`, `itensAplicados`, `GerarIn`, `IaAplicacao` com `itens`, `Resumo`) e o esqueleto `apps/api/src/sociman_api/ia/router.py` (prefixo `/api/ia`, `operationId` `ia_*`), incluído em `apps/api/src/sociman_api/main.py` (só acréscimo).
- [X] T014 [P] Em `apps/api/tests/unit/test_constitution_guards.py`, o guarda do princípio I cobre `/api/ia/*` e `ia_*` (nenhum termo proibido no caminho nem no `operationId`) e confere que o `IaClient` não envia `tools`; e um teste de que não existe rota `DELETE` em `/api/ia/*`.
- [X] T015 [P] Claude falso do e2e: em `e2e/fakes/server.py` (só acréscimo), `POST /v1/messages` determinístico que lê o schema pedido e devolve JSON válido por formato; palavra "lento" na instrução → dorme além do timeout; "fora do limite" → texto acima do limite; nas sugestões, itens que dependem do número de aceitos e rejeitados recebidos (para "Gerar mais" nunca repetir). Em `docker-compose.e2e.yml` (só acréscimo), na `api`: `ANTHROPIC_API_KEY` de mentira que **não** casa com `sk-ant-…` e `ANTHROPIC_BASE_URL=http://openshorts-fake:8000`. Verificar `docker compose -f docker-compose.e2e.yml config -q` e `npm run check:web` (check:secrets).

**Checkpoint:** migration testada, motor da IA com unitários verdes, `npm run test:api` verde (006 e 007 sem regressão).

---

## Phase 3: User Story 1 - Melhorar ou criar um texto com IA (Priority: P1) 🎯 MVP

**Goal:** botão "Melhorar com IA" nos campos do asset, do perfil e do kit; gerar, outra versão, sugestões com seleção nos bordões e séries, e **Aplicar em 1 clique** que salva só aquele campo, com o selo "com ajuda da IA", sem perder o resto do formulário.

**Independent Test:** quickstart §1 (avatar Achadinhos: gerar, editar o tom sem salvar, Aplicar, versão com o selo e só a descrição, salvar o tom depois sem 409).

### Tests for User Story 1

- [X] T016 [P] [US1] `apps/api/tests/integration/test_ia_gerar.py`: `POST /api/ia/gerar` para cada um dos 9 tipos de asset, perfil e kit (o corpo enviado ao fake tem as regras, o perfil, a persona, a entidade, o `valorAtual` e a instrução certos; campo vazio pede criação do zero); **gerar não cria versão em nenhuma entidade** (princípio VII); "Outra versão" com `anteriores` da mesma sessão (enviadas em `<propostas_anteriores>`) e 400 `ia_anteriores_invalidas` com anterior de outra sessão, autor, tipo ou alvo; `selecao` num tipo que não é `sugestoes` → 400 `invalid_ia`; sugestões: as repetidas com a lista, os aceitos e os rejeitados saem com aviso, e a chamada guarda `aceitos`/`rejeitados`; alvo de outro perfil, tipo incompatível com o alvo (`avatar.tom_de_voz` num cenário) e `valorAtual` acima de 1,5 × o limite → 400; entidade arquivada → 409; perfil sem kit salvo e sem avatar → `contextoFaltante` com `kit` e `persona` e o aviso na chamada (edge case); `POST /api/ia/chamadas/{id}/descartar` (só o autor, 403 para outro; idempotente; não muda `aplicada`/`editada`/`erro`).
- [X] T017 [P] [US1] `apps/api/tests/unit/test_ia_aplicacao.py` (`marcar`): `aplicada` (igual à proposta, depois da mesma normalização), `editada`, ignorada (outro perfil, outro alvo, tipo que não casa com a entidade, campo que não mudou, chamada `texto` já aplicada), e nas sugestões: `itens` que entraram na lista nesta versão, item que já estava na lista (ignorado), item editado (`editada`), segunda aplicação da mesma chamada acumulando `itens_aplicados` e nunca voltando de `editada` para `aplicada`.
- [X] T018 [P] [US1] `apps/api/tests/integration/test_ia_aplicar.py`: `PATCH /api/assets/{id}` e `PATCH /api/perfis/{id}` **só com o campo** + `ia` → versão nova com autor humano (`actor_kind = "user"`), `details.ia` e só aquele campo no diff; a chamada fica `aplicada` com `aplicada_versao` e `desfecho_por`; `PUT /api/perfis/{id}/kit` com os tokens salvos + `catchphrases` acrescidos + `ia` com `itens` → só os bordões mudam; kit nunca salvo (`version: 0`) cria a v1 com o selo; 409 `version_conflict` → nada gravado e a chamada continua `sem_acao`; itens de `ia` que não casam não quebram o save; um segundo save com a versão nova funciona (US1-7); reverter pelo dono uma versão "com ajuda da IA" funciona como qualquer outra.

### Implementation for User Story 1

- [X] T019 [US1] Criar `apps/api/src/sociman_api/ia/service.py`: `gerar` (valida tipo × alvo × perfil, `valorAtual` e `selecao` pelo formato; carrega as anteriores pelo id; monta contexto e prompt; chama o `IaClient`; valida a saída; calcula o custo; **grava sempre**, inclusive com erro, com commit antes de levantar, como o `_deny`: 503 `claude_unconfigured`, 504 `ia_timeout`, 502 `ia_recusa`/`ia_invalida`/`claude_error`) e `descartar`. Usa as regras em vigor (`ia_regras` ou o padrão) e grava `regras_version`/`padrao_versao`.
- [X] T020 [US1] Em `apps/api/src/sociman_api/ia/router.py`: `GET /api/ia/tipos` (`ia_tipos_list`), `GET /api/ia/tipos/{tipo}` (`ia_tipos_get`), `POST /api/ia/gerar` (`ia_gerar`, `RequireUser`), `POST /api/ia/chamadas/{id}/descartar` (`ia_chamadas_descartar`, 204). Sessão do banco com `DbSession` (armadilha 7).
- [X] T021 [US1] Criar `apps/api/src/sociman_api/ia/aplicacao.py`: `IaAplicacao` (≤ 10, `itens` ≤ 20) e `marcar(db, actor, entity_type, entidade, antes, depois, ia) -> dict | None`, chamado **antes** do `history.record` na mesma transação, com as regras do data-model (inclusive sugestões acumulando).
- [X] T022 [P] [US1] `ia: list[IaAplicacao] | None` em `AssetPatch` (`apps/api/src/sociman_api/assets/schemas.py`) e `marcar()` no update de `apps/api/src/sociman_api/assets/service.py` (tipos `avatar.*`, `cenario.prompt_ambiente`, `asset.nome`, `asset.descricao`); o prompt continua sem trim.
- [X] T023 [P] [US1] `ia` em `UpdatePerfilIn` (`apps/api/src/sociman_api/perfis/schemas.py`) e `marcar()` no update de `apps/api/src/sociman_api/perfis/service_perfis.py` (`perfil.bio`).
- [X] T024 [P] [US1] `ia` em `KitIn` (`apps/api/src/sociman_api/marca/schemas.py`), **fora de `sections()`** e fora dos tokens gravados, e `marcar()` no `put_kit` de `apps/api/src/sociman_api/marca/service_kit.py` (`kit.bordoes`, `kit.series`, com `itens`).
- [X] T025 [US1] `npm run gen:contract` (contrato das rotas da US1 e do campo `ia`) e `docker compose exec api uv run ruff check .`; `npm run test:api -- -k "ia_ or migration_0008 or kit or assets or perfis"` verde.
- [X] T026 [US1] Criar `apps/web/src/lib/ia.ts`: queries (`tiposQuery`, integrações), mutations (`gerar`, `descartar`), o tipo `IaOnSave = (valor, ia: IaAplicacao[]) => Promise<void>` e o hook `useFormRebase()` (guarda os campos sujos antes do `onSave` e os reaplica sobre os dados novos depois do sucesso, para formulários que remontam pela `key` com a versão).
- [X] T027 [US1] Criar `apps/web/src/components/ia/IaAssist.tsx` e `IaDiff.tsx` (R11): botão "Melhorar com IA" (`Sparkles`, desabilitado com tooltip "IA não configurada"), painel inline (`Collapsible`), instrução com contador de 1.000, "Gerar" desabilitado durante a geração, antes × depois, explicação, avisos, contador do limite em vermelho quando `excede` (Aplicar desabilitado até editar), abas "Versão N", **Aplicar** (1 clique: `onSave(proposta, [{ tipoCampo, chamadaId }])`, "Salvando…", toast "Salvo com ajuda da IA", fecha o painel), **Editar e aplicar** (textarea no painel + "Salvar" do painel), **Outra versão**, **Descartar**; ao fechar, `descartar` das chamadas sem aplicação (melhor esforço); erro no `onSave` (409 com "Recarregar", 400 com a mensagem) mantém a proposta e não mexe no formulário. `sessaoId` gerado ao abrir.
- [X] T028 [US1] Criar `apps/web/src/components/ia/IaSugestoes.tsx` (formato `sugestoes`, Q3): uma `Checkbox` por sugestão, item marcado editável no lugar, sugestões marcadas acima do limite do item só depois de editadas, "Gerar mais" (manda `anteriores` e `selecao { aceitos, rejeitados }`, e as novas aparecem abaixo com as marcações preservadas), contador "N de 20", bloqueio de marcar além do que cabe com o aviso "A lista está cheia (máximo de 20)", "Gerar" desabilitado com a lista em 20; **Aplicar** chama `onSave(lista + marcados no fim sem repetir, ia)` com um `IaAplicacao` por chamada de origem (`itens` com o texto final); depois do sucesso o painel continua aberto e os aplicados passam a contar como lista.
- [X] T029 [P] [US1] Criar `apps/web/src/components/ia/IaSelo.tsx` e mostrar o selo "com ajuda da IA" em `apps/web/src/components/VersionHistory.tsx` quando `details.ia` existir (autor humano continua o destaque).
- [X] T030 [US1] Integrar em `apps/web/src/components/assets/AvatarCampos.tsx` (3 `IaAssist` no avatar: `avatar.descricao_prompt`, `avatar.tom_de_voz`, `avatar.regras_imagem`; 1 no cenário: `cenario.prompt_ambiente`) e no `DadosCard` de `apps/web/src/pages/assets/AssetDetalhe.tsx` (`asset.nome`, `asset.descricao`), com `onSave` = `PATCH` parcial `{ version, <campo>, ia }` pela mutation que já existe; depois do sucesso, o valor salvo e a `version` entram no formulário sem descartar os outros campos sujos.
- [X] T031 [US1] Integrar em `apps/web/src/pages/perfis/PerfilDetalhe.tsx` (`perfil.bio` no formulário de edição, react-hook-form): `onSave` = `PATCH` parcial; como o formulário remonta pela `key` com a versão, usar `useFormRebase` (ou tirar a versão da `key` e fazer `resetField` só da bio) para o nicho/nome editados continuarem no formulário.
- [X] T032 [US1] Integrar em `apps/web/src/pages/perfis/tabs/MarcaTab.tsx` (`LinesField` "Bordões" e "Séries" com `IaSugestoes`): `onSave` = `PUT` com os **tokens salvos** (`kit.data.kit`, nunca o `draft`) e só `catchphrases`/`series` trocado; o `draft` (remontado pela `key` com a versão e `dataUpdatedAt`) é reaplicado com `useFormRebase`, e a lista aplicada entra no `draft`.
- [X] T033 [US1] `e2e/assistente-ia.spec.ts` (US1, com o Claude falso): no avatar, gerar a descrição, editar o tom sem salvar, **Aplicar** (1 clique) → versão com o selo e só a descrição; o tom continua no campo e "Salvar" grava sem 409; "Editar e aplicar" → `editada`; "Outra versão" com as abas; "Descartar"/fechar não muda nada; "fora do limite" deixa Aplicar desabilitado; conflito (versão alterada por API no meio) → aviso e nada salvo; no kit, marcar 2 sugestões, "Gerar mais" sem repetir, Aplicar → só os bordões mudam e a paleta alterada sem salvar não entra na versão; lista em 20 → aviso e "Gerar" desabilitado. Rodar `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/assistente-ia.spec.ts`.

**Checkpoint:** US1 funcional e testada; pode ir ao dono (quickstart §1, §2 e §4).

---

## Phase 4: User Story 2 - Regras (system prompts) por tipo de campo (Priority: P1)

**Goal:** tela "Assistente de IA" com as regras dos 13 tipos, edição pelo dono com histórico, "Voltar ao padrão" e reversão; membro só lê.

**Independent Test:** quickstart §7 (regra do título com emoji, voltar ao padrão, reverter; membro sem edição e 403 nas rotas).

### Tests for User Story 2

- [X] T034 [P] [US2] `apps/api/tests/integration/test_ia_regras.py`: `GET /api/ia/tipos` sem linhas → 13 tipos com `personalizada = false`, `version = 0`; `PUT …/regras` com `version: 0` cria a linha (v1, `history.record` com autor), `version` errada → 409, texto vazio ou > 8.000 → 400, membro → 403; `POST …/padrao` grava `texto = NULL` com `details = {"padrao": true}`; `GET …/versions`; `POST …/revert` só dono; tipo inexistente → 404 `ia_tipo_not_found`; `padraoAtualizado = true` quando o `padrao_versao` do código é maior que o da linha; a geração seguinte usa a regra nova (corpo enviado ao fake) e grava `regras_version`.

### Implementation for User Story 2

- [X] T035 [US2] Criar `apps/api/src/sociman_api/ia/service_regras.py` (listar, obter, `put_regras`, `voltar_ao_padrao`, versões, `revert`), com `history.record` (`entity_type = "ia_regra"`) na mesma transação e as restrições de `ia_regras` citadas acima.
- [X] T036 [US2] Em `apps/api/src/sociman_api/ia/router.py`, as rotas `ia_regras_update`, `ia_regras_padrao`, `ia_regras_versions`, `ia_regras_revert` (`RequireOwner` nas mutações); `GET /api/ia/tipos*` passa a trazer `Regras` em vigor. `npm run gen:contract` e ruff.
- [X] T037 [US2] Criar `apps/web/src/pages/ia/AssistenteIa.tsx` (abas `?aba=regras|registro|resumo`; registro e resumo só aparecem para o dono) e `apps/web/src/pages/ia/RegraDetalhe.tsx` (texto em vigor, padrão para comparar, aviso "O padrão mudou desde a sua edição", editar com contador ≤ 8.000, "Voltar ao padrão" em `AlertDialog`, histórico com reversão via `VersionHistory`; membro só leitura). Rotas `/app/assistente-ia` e `/app/assistente-ia/regras/:tipo` em `apps/web/src/App.tsx` e o item "Assistente de IA" (`WandSparkles`) em `apps/web/src/components/shell/nav.ts` (só acréscimo).
- [X] T038 [US2] `e2e/assistente-ia.spec.ts` (US2): dono edita a regra do título, gera e vê o efeito no corpo que o fake recebeu (ou no texto de volta), volta ao padrão, reverte; membro vê as regras sem botões de edição.

**Checkpoint:** US2 funcional (quickstart §7).

---

## Phase 5: User Story 3 - Registro e custo das chamadas (Priority: P2)

**Goal:** registro filtrável de todas as chamadas (inclusive as da 006) e resumo do gasto do mês, só para o dono; falhas registradas com mensagem clara.

**Independent Test:** quickstart §8 (3 propostas → 4 chamadas com os desfechos certos; resumo do mês em < 1 min).

### Tests for User Story 3

- [X] T039 [P] [US3] `apps/api/tests/integration/test_ia_registro.py`: `GET /api/ia/chamadas` com filtros `perfilId`, `tipoCampo`, `desfecho`, `de`/`ate` em `APP_TZ` (virada do dia em São Paulo), `sessaoId`, cursor e `limit ≤ 100`; inclui as linhas `postagem.textos` da 006; `GET /api/ia/chamadas/{id}`; `GET /api/ia/resumo` (totais, por tipo, por perfil, `precosVersao`, mês padrão em `APP_TZ`); membro → 403 nas três; erros gravados: sem chave → 503 e linha `erro_code = unconfigured`; timeout do fake → 504 `ia_timeout` e linha `erro`; 401/429 do fake → 502 `claude_error`; resposta inválida duas vezes → 502 `ia_invalida`; nenhuma resposta ou linha contém a chave.

### Implementation for User Story 3

- [X] T040 [US3] Em `apps/api/src/sociman_api/ia/service.py`, `listar_chamadas` (paginação por cursor sobre `ix_ia_chamadas_created`) e `resumo` (`SUM`/`GROUP BY`, mês em `APP_TZ`); em `ia/router.py`, `ia_chamadas_list`, `ia_chamadas_get` e `ia_resumo` com `RequireOwner`. `npm run gen:contract` e ruff.
- [X] T041 [US3] Criar `apps/web/src/pages/ia/RegistroTab.tsx` (`DataTable` com paginação no servidor: quando, autor, perfil, campo, desfecho, duração, custo "≈ US$"; filtros; a linha abre um `Sheet` com instrução, entrada, proposta, explicação, avisos, `aceitos`/`rejeitados`/`itensAplicados` nas sugestões, erro, modelo servido e tokens) e `apps/web/src/pages/ia/ResumoTab.tsx` (`MetricCard`s do mês e tabelas por tipo e por perfil, seletor de mês em `APP_TZ`). O `IaSelo` do histórico leva à chamada no registro (dono).
- [X] T042 [US3] `e2e/assistente-ia.spec.ts` (US3): 3 gerações (aplicar 1, descartar 1, outra versão em 1) → 4 linhas com os desfechos certos e a mesma sessão na "Outra versão"; resumo com a soma; modo "lento" → mensagem "A IA demorou demais" com "Tentar de novo" e o campo editável; membro sem as abas e 403 por `request`.

**Checkpoint:** US3 funcional (quickstart §6 e §8).

---

## Phase 6: User Story 4 - Os textos de postagem usam o mesmo assistente (Priority: P2)

**Goal:** título, descrição, hashtags e "Sugerir textos" da postagem pelo `IaAssist`, com Aplicar salvando na hora (ou criando a postagem em rascunho); rotas da 006 `deprecated` delegando ao serviço novo, sem perder o histórico.

**Independent Test:** quickstart §5 (título "mais polêmico" aplicado em 1 clique, versão com o selo, chamada no registro; corte sem postagem cria o rascunho).

### Tests for User Story 4

- [X] T043 [P] [US4] `apps/api/tests/integration/test_ia_postagem.py`: gerar `postagem.titulo`/`descricao`/`hashtags`/`textos` com o contexto da 006 (plataforma e limites da conta, transcrição em `<dados_terceiros>`, os outros campos da postagem); `POST /api/cortes/{id}/postagens` com `contaId`, **só** o campo e `ia` → rascunho v1 com `details.ia` e `sugestao_id` gravado a partir do item; `PATCH /api/postagens/{id}` parcial com `ia` → `aplicada`/`editada`; item com alvo de outra conta ignorado. Atualizar `apps/api/tests/integration/test_sugestoes.py` e `apps/api/tests/unit/test_textos.py`: as rotas da 006 continuam respondendo `{ sugestao }` (agora lendo e gravando `ia_chamadas` com `tipo_campo = 'postagem.textos'`), com os códigos novos (`ia_timeout`…) no lugar de `textos_timeout`/`textos_invalidos`, e o `GET` lista também as linhas migradas.

### Implementation for User Story 4

- [X] T044 [US4] Em `apps/api/src/sociman_api/postagem/textos.py`, deixar só a normalização de hashtags e os limites (cliente, prompt e `_somar_uso` já estão em `ia/`); em `postagem/service.py`, `sugerir` delega a `ia.service.gerar("postagem.textos", alvo corte + conta, sem sessão; `outraVersao` manda as últimas do corte e da plataforma como anteriores)`, `list_sugestoes` lê `ia_chamadas`, e create/update chamam `marcar()` (e gravam `sugestao_id` a partir do item `postagem.textos` ou do primeiro item); em `postagem/schemas.py`, `ia` em `CreatePostagemIn`/`UpdatePostagemIn` e `sugestaoId` `deprecated`; em `postagem/router.py`, as rotas de sugestões com `deprecated=True`. `npm run gen:contract` e ruff.
- [X] T045 [US4] Em `apps/web/src/components/postagem/PostagemSection.tsx` e `apps/web/src/lib/postagem.ts`: `IaAssist` no título, na descrição e nas hashtags, e o "Sugerir textos" da 006 vira um `IaAssist` com `tipo="postagem.textos"` que salva os três campos juntos; `onSave` = `PATCH` parcial com `ia` ou, sem postagem, `POST` de criação com `contaId`, o campo e `ia` (a seção passa a mostrar a postagem criada); os outros campos sujos continuam; o SPA deixa de chamar as rotas `deprecated`.
- [X] T046 [US4] `e2e/assistente-ia.spec.ts` (US4) e ajuste de `e2e/cortes-openshorts.spec.ts` se ele usar o "Sugerir" antigo: título "mais polêmico" aplicado em 1 clique com o selo; "Sugerir textos" salva os três; corte sem postagem cria o rascunho com o selo.

**Checkpoint:** as quatro histórias funcionais.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T047 [P] Conferir no `/api/openapi.json` que nenhum caminho `/api/ia/*` nem `operationId` `ia_*` contém termos do guarda do princípio I, que não há `DELETE` novo, e `git grep -n "sk-ant-" -- ':!scripts/check-secrets.mjs'` vazio.
- [X] T048 Verificação completa: `npm run test:api`, `docker compose exec api uv run ruff check .`, `npm run gen:contract && npm run check:web` (sem divergência), `flock /tmp/sociman-e2e.lock npm run test:e2e` (regressão inteira, 006 e 007 incluídas).
- [X] T049 Migration no dev (quickstart §0): `docker compose restart api`, `alembic current` = `0008_assistente_ia`, contagem de `ia_chamadas` = N anotado no T001, FK de `postagens` intacta; resultado anotado numa seção "Resultado" nova no fim de `specs/008-assistente-ia/quickstart.md`.
- [ ] T050 Validação com o Claude real pelo dono (quickstart §1 a §8), incluindo a SC-001 (proposta em < 15 s), a SC-004 (10 gerações da descrição do avatar: 10/10 em inglês com os traços fixos) e a SC-005 (resumo em < 1 min); anotar no quickstart. **Só com o dono presente** (custo real, alguns centavos).
- [X] T051 [P] `CLAUDE.md`: seção curta "Assistente de IA (desde a spec 008)" (pacote `ia/`, tipos em código e regras em `ia_regras`, `ia_chamadas` = `sugestoes_texto` renomeada, Aplicar salva só o campo pelo save da tela com `ia: [...]` e `details.ia`, formato `sugestoes` nos bordões e séries, `ANTHROPIC_BASE_URL` só no e2e, rotas da 006 `deprecated`).
- [X] T052 `docs/visao.md`: marcar a 008 como implementada no backlog de specs. **Só no fim**, depois do T048 verde e do T050 aprovado pelo dono.

---

## Dependencies & Execution Order

### Phase Dependencies
- Setup (T001–T003) → Foundational (T004–T015) → histórias.
- T004 → T005 → T006; T007 → T008, T010, T011; T009, T010, T011 → T012 → T013. T014 depende do T013; T015 é independente.
- US1: T019 depende de T011–T013; T021 → T022–T024; T025 depois de T020–T024; SPA (T026–T032) depois do T025 (contrato); T033 depois de T030–T032 e do T015.
- US2 (T034–T038): depende só da Foundational e do T020 (rotas `tipos`); SPA depois do `gen:contract` do T036.
- US3 (T039–T042): depende do T019 (chamadas gravadas); SPA depois do T040.
- US4 (T043–T046): depende do T019 e do T021; T045 depois do `gen:contract` do T044 e do T027.
- Polish depois das histórias; T052 por último.

### Parallel Opportunities
- T002, T003 e T015 em paralelo com o resto da Setup/Foundational.
- T007, T009 e T010 em paralelo; T014 em paralelo com T016–T018.
- Testes de cada história marcados [P] entre si; T022, T023 e T024 em paralelo (arquivos diferentes).
- Depois da US1, US2 e US3 podem andar juntas (arquivos diferentes em `ia/`, exceto `router.py` e `service.py`: uma trilha só, ver abaixo).

---

## Trilhas para agentes paralelos

Quatro agentes, sem arquivo em comum. Cada trilha só edita os arquivos listados; qualquer outro arquivo pede coordenação pelo líder.

| Trilha | Agente sugerido | Tarefas | Arquivos (exclusivos) |
|---|---|---|---|
| **A: API base, regras e registro** | `api-008-base` | T001, T002, T004–T014, T016, T019, T020, T025, T034–T036, T039, T040, T047 | `apps/api/src/sociman_api/ia/**` **exceto** `ia/aplicacao.py`; `config.py`, `main.py`; `apps/api/migrations/**`; `apps/api/tests/conftest.py`, `tests/fakes/anthropic_fake.py`, `tests/unit/test_constitution_guards.py`, `tests/unit/test_ia_{tipos,custo,saida,prompt,cliente}.py`, `tests/integration/test_migration_0008.py`, `test_ia_{gerar,regras,registro}.py`; no T004, também `postagem/models.py`, `postagem/service.py` e `postagem/textos.py` (só a troca para `IaChamada`; depois disso eles são da trilha B). **Única trilha que roda `npm run gen:contract`** e toca `packages/contract/**` |
| **B: API integração com os 5 saves** | `api-008-saves` | T017, T018, T021–T024, T043, T044 | `apps/api/src/sociman_api/ia/aplicacao.py`; `assets/{schemas,service}.py`; `perfis/{schemas,service_perfis}.py`; `marca/{schemas,service_kit}.py`; `postagem/{textos,service,schemas,router}.py` (depois do T004); `tests/unit/test_ia_aplicacao.py`, `tests/unit/test_textos.py`, `tests/integration/test_ia_{aplicar,postagem}.py`, `test_sugestoes.py` |
| **C: SPA** | `spa-008` | T003, T026–T032, T037, T041, T045 | `apps/web/**` (novos em `components/ia/`, `pages/ia/`, `lib/ia.ts`; `components/ui/{collapsible,checkbox}.tsx`; integrações em `AvatarCampos.tsx`, `AssetDetalhe.tsx`, `PerfilDetalhe.tsx`, `MarcaTab.tsx`, `PostagemSection.tsx`, `lib/postagem.ts`, `VersionHistory.tsx`; acréscimos em `App.tsx` e `nav.ts`) |
| **D: e2e, fake e docs** | `e2e-008` | T015, T033, T038, T042, T046, T048, T049, T051, T052 | `e2e/**` (`assistente-ia.spec.ts`, `fakes/server.py`, `helpers.ts`, ajuste em `cortes-openshorts.spec.ts`), `docker-compose.e2e.yml`, `specs/008-assistente-ia/quickstart.md` (Resultado), `CLAUDE.md`, `docs/visao.md` |

Sincronização:
1. A faz a fundação (T004–T014) sozinha no backend; B, C e D esperam o checkpoint da Foundational para mexer em `apps/api/**`, mas C já pode fazer o T003 e D o T015.
2. B começa o T021 depois do T013 (schemas do `IaAplicacao`) e avisa A ao terminar T022–T024 e T044, para A rodar o `gen:contract` (T025, e o do T044).
3. C começa o T026 depois do T025; o T037 depois do `gen:contract` do T036; o T041 depois do do T040; o T045 depois do do T044.
4. D escreve cada parte do e2e depois que A, B e C fecham a história, e roda **sempre** com `flock /tmp/sociman-e2e.lock` (nunca dois e2e ao mesmo tempo, nem com outra spec).
5. T050 (Claude real) fica com o líder e o dono; T052 só depois do T048 verde e do T050 aprovado.

---

## Implementation Strategy

### MVP (US1)
1. Setup + Foundational (inclui a migration com o teste de preservação da 006).
2. US1 (asset, perfil e kit; Aplicar em 1 clique; sugestões com seleção).
3. **Parar e validar** com o dono (quickstart §1, §2 e §4).

### Incremental
US2 (regras) → US3 (registro e custo) → US4 (postagem pelo assistente, rotas da 006 `deprecated`) → Polish (verificação completa, Claude real, docs).

## Notes
- Nenhum DELETE, nenhuma tabela além de `ia_regras`, nenhuma dependência nova (Python ou npm; `collapsible` e `checkbox` do shadcn são código copiado sobre o `radix-ui` que já existe).
- Gerar nunca salva; só o clique humano em Aplicar (ou no "Salvar" do Editar e aplicar) chama o save da tela.
- Commit só quando o dono pedir, em pt-BR, no imperativo.
