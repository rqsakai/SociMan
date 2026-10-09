# Implementation Plan: Assistente de IA para textos (008-assistente-ia)

**Branch**: `008-assistente-ia` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-assistente-ia/spec.md`

## Summary

A 008 transforma a sugestão de textos de postagem da 006 num **assistente geral**: um botão
"Melhorar com IA" em 13 tipos de campo, com regras (system prompt) por tipo que o dono vê e
ajusta, e um registro único de chamadas com custo. Nada é salvo sem ação humana, e nada publica
(princípio I). Quatro blocos:

- **Motor (US1, US4):**
  - o cliente da 006 (`postagem/textos.py`: SDK `anthropic`, `beta.messages.parse` com Pydantic,
    `claude-sonnet-5-5`, esforço `low`, `fallbacks: "default"`) vira o pacote `ia/`, com um
    schema de saída por formato (`texto`, `lista`, `sugestoes`, `textos_postagem`), sempre com
    `explicacao` e `avisos` (R4);
  - o registro dos tipos de campo é **código** (`ia/tipos.py`), cruzado por teste com os schemas
    reais dos campos (R1);
  - o contexto (perfil, kit com a paleta nomeada, até 2 avatares como persona, a entidade) é
    montado no servidor; o valor atual e a instrução vêm do formulário (R5). Dados de terceiros
    entram delimitados (R6);
  - "Outra versão" manda ao modelo as propostas da sessão do painel, carregadas pelo id (R9);
  - bordões e séries são **sugestões com seleção** (Q3): o usuário marca as que quer, e "Gerar
    mais" leva os já aceitos e os rejeitados na sessão para não repetir (R4, R9).
- **Regras (US2):** o padrão fica no código; a personalização, em `ia_regras`, uma entidade
  versionada com histórico, "voltar ao padrão" e reversão pelo dono (R2). A base fixa do prompt
  (formato, limites, segurança) não é editável.
- **Registro e custo (US3):** `sugestoes_texto` é **renomeada** para `ia_chamadas` e ampliada,
  sem perder as linhas da 006 (R3). O custo aproximado sai do `usage` do SDK com uma tabela de
  preços em código (R7). Registro e resumo do mês para o dono.
- **Aplicar (FR-006, Q1 = B):** "Aplicar" **salva na hora só aquele campo** (1 clique). O
  `<IaAssist>` recebe da tela um `onSave`, que chama o save que já existe com só aquele campo
  (`PATCH` parcial; no kit, os tokens salvos com o campo trocado) e o campo opcional `ia:
  [{tipoCampo, chamadaId, itens?}]`. O helper `ia.aplicacao.marcar` grava `details.ia` na versão
  (autor humano, "com ajuda da IA") e o desfecho da chamada (`aplicada` ou `editada`) na mesma
  transação. As outras alterações não salvas do formulário continuam lá, e o formulário passa a
  usar a versão nova (R10, R11).

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md). As perguntas para
o dono estão em [open-questions.md](open-questions.md), todas respondidas em 2026-09-29 (Q1 = B,
Q2 = B, Q3 = sugestões com seleção); o plano segue as respostas.

## Technical Context

**Language/Version**: Python 3.12 (API) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**:
- **Python:** nada novo. O `anthropic` (1.x, sobre `httpx2`) já entrou na 006;
- **SPA:** nada novo. `Collapsible`, `Tabs`, `Sheet`, `Tooltip` e `AlertDialog` do shadcn (os que
  faltarem entram com `npx shadcn@latest add`, que copia código, sem dependência nova além do
  Radix que já está no projeto), `DataTable` e `MetricCard` da 005.

**Storage**: PostgreSQL (NVMe): `ia_regras` (nova) e `ia_chamadas` (a `sugestoes_texto`
renomeada e ampliada). Nada no MinIO nem no HD.

**Testing**:
- pytest com o `anthropic_fake` da 006 (`httpx2.MockTransport`), ampliado com os três formatos,
  `usage` com cache e `iterations` de fallback (R14);
- teste de cruzamento registro × schemas; teste da migration (linhas da 006 preservadas);
- testes dos princípios I (guarda de rotas `ia_*`) e VII (gerar não cria versão; aplicar cria
  versão com autor humano e `details.ia`; regras com histórico e reversão só do dono);
- ruff; `check:web` com o contrato regenerado;
- Playwright `e2e/assistente-ia.spec.ts` com um **Claude falso** no `openshorts-fake`
  (`POST /v1/messages`) e `ANTHROPIC_BASE_URL` na stack e2e (config nova).

**Target Platform**: a mesma stack; nenhum serviço novo. `ANTHROPIC_BASE_URL` (vazio = padrão do
SDK) só é usado no e2e.

**Project Type**: web application (SPA + API)

**Performance Goals**:
- SC-001: proposta em < 15 s no p95: Sonnet 5.5 com esforço `low`, ~2,5 mil tokens de entrada e
  ~400 de saída (a 006 já fica bem abaixo disso); timeout de 20 s, sem retentativa do SDK, e a
  segunda tentativa de validação só se a primeira levou < 10 s (R8);
- registro: p95 < 300 ms com índices por data, perfil e tipo (dezenas de milhares de linhas em
  anos de uso);
- resumo do mês: um `SUM`/`GROUP BY` sobre o índice de data.

**Constraints**:
- nada publica (princípio I); a chamada ao Claude não tem tools e só devolve texto;
- nada é salvo sem ação humana (FR-005, SC-003): gerar nunca salva; o componente só chama o
  `onSave` da tela no clique de Aplicar (ou no "Salvar" do Editar e aplicar);
- aplicar não pode perder o que o usuário digitou nos outros campos (US1-7): o `PerfilDetalhe` e o
  `MarcaTab` hoje remontam o formulário quando a versão muda (`key` com a versão), então a
  integração reaplica os campos sujos sobre os dados novos;
- CSP inalterada: o SPA só fala com `/api`; a chave nunca chega ao navegador;
- o prompt do avatar e do cenário é guardado **sem trim** (FR-009 da 007): a proposta aplicada
  vai como veio;
- fuso `America/Sao_Paulo` no filtro do registro e no mês do resumo.

**Scale/Scope**:
- 2 perfis hoje (até cerca de 10), 2 usuários; dezenas de gerações por dia (≈ US$ 0,01 cada);
- 13 tipos de campo em 5 telas; 11 rotas novas e o campo `ia` em 5 rotas existentes;
- telas: o painel `IaAssist` (5 telas) e "Assistente de IA" (regras, registro e resumo).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Nenhum agente publica | ✅ | O assistente só devolve texto para a tela (FR-011). A chamada ao Claude é `messages.parse` **sem tools**. Nenhuma rota nova publica ou envia a rede social; os caminhos `/api/ia/*` e os `operationId` `ia_*` passam pelo guarda da 001 (ampliado para as rotas novas). "Aplicar" grava pelo save que já existe em cada tela (rota da entidade, sem nada de rede social), no clique humano |
| II. Direito é responsabilidade do dono | ✅ (não se aplica) | A 008 não toca canais, envios nem status de direito. A transcrição de terceiros continua entrando só como dado (R6) |
| III. Marca em tokens | ✅ | Os bordões e séries continuam listas validadas pelo `KitTokens`; a IA só propõe valores, que passam pelo mesmo schema no save. A paleta vai ao modelo como dado estruturado (nome + hex), só como contexto. As regras são texto livre, mas **não são fonte de regra da marca**: são instruções de escrita do assistente (a marca continua nos tokens) |
| IV. Contrato é a fonte única | ✅ | Rotas e schemas novos (e o campo `ia` nos saves) entram no OpenAPI → `gen:contract`; o `check:contract` acusa divergência. O `TipoCampoId` é um `Literal` no Python, então o SPA recebe a união tipada. Os limites de cada tipo saem do registro pela API (`GET /api/ia/tipos`), não são copiados no SPA |
| V. Segurança e segredos | ✅ | `ANTHROPIC_API_KEY` continua só no `.env` da raiz → `api` (e `agendador`, que não usa). A chave nunca vai para log, erro, registro nem navegador (`SecretStr` e o `__repr__` do cliente). Dados de terceiros delimitados e a base fixa não editável contra injection (R6). `ANTHROPIC_BASE_URL` é só para o e2e e aponta para a rede interna. `check:secrets` já cobre `sk-ant-…`; a chave de mentira do e2e não casa com o padrão |
| VI. Testes antes de pronto | ✅ | pytest (unidade, integração, migration), ruff, `check:web` e o e2e do painel com o Claude falso (R14). Os princípios I e VII têm teste no backend |
| VII. Humano no controle | ✅ | Gerar **não muda** nenhuma entidade (teste). Aplicar = save humano (1 clique, só aquele campo), com `version`, 409, `history.record`, autor humano e `details.ia` (R10). As regras são entidade versionada (`entity_type = "ia_regra"`), com autor, antes/depois, "voltar ao padrão" como versão e **reversão só do dono**. `ia_chamadas` é log (só INSERT); as colunas de desfecho são estado sem versão, como o progresso dos envios da 006, e nunca apagam o que foi proposto. Nada é apagado (o `downgrade` só roda em dev) |
| VIII. Simplicidade | ✅ | Nenhuma dependência, serviço ou tabela além de `ia_regras`. O registro dos tipos fica em código; a tabela de chamadas é a da 006 renomeada. Sem SSE, sem fila, sem Redis, sem conversa persistida, sem regras por perfil, sem teto de gasto. A única config nova (`ANTHROPIC_BASE_URL`) existe para o e2e testar o fluxo crítico |

**Reavaliação pós-design:** mantida. O design não acrescentou nada à tabela de complexidade além
do que está abaixo.

Fora do escopo, de propósito (research R15): conversa persistida, regras por perfil, teto de gasto,
geração de imagem, imagem como contexto, campos de arquivo do asset, formulários de criação,
nicho e CTA, assistente pelo MCP (009).

## Project Structure

### Documentation (this feature)

```text
specs/008-assistente-ia/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── open-questions.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── migrations/versions/0008_assistente_ia.py      # ia_regras; sugestoes_texto → ia_chamadas + backfill
├── src/sociman_api/
│   ├── config.py                                  # + anthropic_base_url (vazio = padrão; só e2e); textos_model continua
│   ├── ia/                                        # NOVO
│   │   ├── tipos.py                               # TipoCampo e os 13 tipos (R1)
│   │   ├── regras_padrao.py                       # texto padrão de cada tipo + padrao_versao (R2)
│   │   ├── prompt.py                              # base fixa (formato, limites, idioma, segurança) e montagem das mensagens (R5, R6)
│   │   ├── contexto.py                            # perfil + kit (paleta nomeada) + persona + entidade + faltantes (R5)
│   │   ├── saida.py                               # PropostaTexto/Lista/TextosPostagem, validação e ajustes (R4)
│   │   ├── cliente.py                             # IaClient (o TextosClient generalizado): parse, 2ª tentativa, usage, fallback (R8)
│   │   ├── custo.py                               # tabela de preços e cálculo pelo usage (R7)
│   │   ├── models.py                              # IaRegra, IaChamada (+ enum IaDesfecho)
│   │   ├── service_regras.py                      # listar, put, voltar ao padrão, versões, revert
│   │   ├── service.py                             # gerar (grava sempre), descartar, registro, resumo
│   │   ├── aplicacao.py                           # IaAplicacao (schema) + marcar() para os saves (R10)
│   │   ├── schemas.py
│   │   └── router.py                              # /api/ia/*
│   ├── postagem/
│   │   ├── textos.py                              # fica só com a normalização de hashtags e os limites (o resto vai para ia/)
│   │   ├── models.py                              # SugestaoTexto sai (IaChamada em ia/models.py); sugestao_id aponta para ia_chamadas
│   │   ├── schemas.py                             # + ia: list[IaAplicacao] | None em Create/UpdatePostagemIn; sugestaoId deprecated
│   │   ├── service.py                             # sugerir → ia.service.gerar("postagem.textos"); create/update chamam marcar()
│   │   └── router.py                              # rotas de sugestões: deprecated=True
│   ├── assets/schemas.py, assets/service.py       # + ia no AssetPatch; update chama marcar()
│   ├── perfis/schemas.py, perfis/service_perfis.py # + ia no UpdatePerfilIn; update chama marcar()
│   ├── marca/schemas.py, marca/service_kit.py     # + ia no KitIn (fora de sections()); put_kit chama marcar()
│   └── main.py                                    # inclui ia.router
└── tests/
    ├── fakes/anthropic_fake.py                    # + formatos, usage com cache e iterations
    ├── fixtures/anthropic/                        # respostas por formato, injection, fora do limite
    ├── unit/                                      # tipos × schemas, prompt/delimitação, saída, custo, marcar
    └── integration/                               # gerar (13 tipos), erros gravados, regras (dono/membro, histórico),
                                                   #   registro/resumo, aplicar nos 5 saves, migration 0008, guardas I e VII

apps/web/src/
├── components/ia/
│   ├── IaAssist.tsx                               # botão + painel inline (antes/depois, versões, ações, onSave) (R11)
│   ├── IaDiff.tsx                                 # antes × depois (texto e lista), contador e limite
│   ├── IaSugestoes.tsx                            # sugestões com seleção, "Gerar mais", "N de 20" (Q3)
│   └── IaSelo.tsx                                 # selo "com ajuda da IA" (histórico e registro)
├── lib/ia.ts                                      # queries/mutations, tipo do onSave, tiposQuery, useFormRebase()
├── pages/ia/
│   ├── AssistenteIa.tsx                           # abas Regras | Registro | Resumo
│   ├── RegraDetalhe.tsx                           # texto, padrão, editar, voltar ao padrão, histórico
│   ├── RegistroTab.tsx                            # DataTable + Sheet da chamada
│   └── ResumoTab.tsx                              # MetricCards + tabelas por tipo e perfil
├── components/assets/AvatarCampos.tsx             # 3 IaAssist (prompt/voiceTone/imageRules; cenário: prompt)
├── pages/assets/AssetDetalhe.tsx                  # IaAssist em nome e notas; onSave = PATCH parcial com `ia`
├── pages/perfis/PerfilDetalhe.tsx                 # IaAssist na bio; onSave = PATCH parcial; campos sujos preservados
├── pages/perfis/tabs/MarcaTab.tsx                 # IaAssist (sugestões) em bordões e séries; onSave = PUT com os tokens salvos + o campo
├── components/postagem/PostagemSection.tsx        # IaAssist nos 3 campos + "Sugerir textos"; onSave = PATCH parcial (ou POST, sem postagem)
├── components/VersionHistory.tsx                  # selo quando details.ia existe
├── components/shell/nav.ts                        # + "Assistente de IA"
└── App.tsx                                        # + rotas /app/assistente-ia…

docker-compose.e2e.yml   # + ANTHROPIC_API_KEY de mentira e ANTHROPIC_BASE_URL=http://openshorts-fake:8000 na api
e2e/fakes/server.py      # + POST /v1/messages determinístico (formatos, "lento", "fora do limite")
e2e/assistente-ia.spec.ts
```

**Structure Decision:**
- um pacote de domínio novo, `ia/`, que **absorve** o cliente da 006 em vez de duplicá-lo; o
  `postagem/` passa a ser um usuário do assistente;
- os saves das telas existentes ganham **só** o campo `ia` e uma chamada a `marcar()` antes do
  `history.record`; validação, versão, conflito e resposta não mudam;
- o SPA ganha um componente reutilizável; cada tela só fornece o `onSave` (a mutation que já
  existe, com só aquele campo e `ia`) e mantém as outras alterações não salvas do formulário.

**Migration:** `0008_assistente_ia`, `down_revision = "0007_envio_progresso"`.

### Arquivos existentes que a implementação toca

| Arquivo | Mudança |
|---|---|
| `apps/api/src/sociman_api/postagem/textos.py` | o cliente, o prompt e o `_somar_uso` vão para `ia/`; fica a normalização de hashtags e os limites da postagem |
| `apps/api/src/sociman_api/postagem/models.py` | `SugestaoTexto` sai; `postagens.sugestao_id` passa a apontar para `ia_chamadas` (mesma coluna) |
| `apps/api/src/sociman_api/postagem/{service,schemas,router}.py` | `sugerir` delega a `ia.service.gerar`; `list_sugestoes` lê `ia_chamadas`; `ia` em create/update; rotas antigas `deprecated` |
| `apps/api/src/sociman_api/assets/{schemas,service}.py` | `ia` no `AssetPatch`; `marcar()` no update |
| `apps/api/src/sociman_api/perfis/{schemas,service_perfis}.py` | `ia` no `UpdatePerfilIn`; `marcar()` no update |
| `apps/api/src/sociman_api/marca/{schemas,service_kit}.py` | `ia` no `KitIn` (excluído de `sections()`); `marcar()` no `put_kit` |
| `apps/api/src/sociman_api/{config,main}.py` | `anthropic_base_url`; router `ia` |
| `apps/api/tests/fakes/anthropic_fake.py`, `tests/unit/test_constitution_guards.py` | formatos novos; guarda cobre `ia_*` |
| `apps/web/src/components/assets/AvatarCampos.tsx`, `pages/assets/AssetDetalhe.tsx` | botões e `ia` no save |
| `apps/web/src/pages/perfis/PerfilDetalhe.tsx`, `pages/perfis/tabs/MarcaTab.tsx` | botões e `ia` no save |
| `apps/web/src/components/postagem/PostagemSection.tsx`, `lib/postagem.ts` | troca o "Sugerir" da 006 pelo `IaAssist`; `onSave` parcial (ou cria a postagem) |
| `apps/web/src/components/VersionHistory.tsx`, `components/shell/nav.ts`, `App.tsx` | selo, menu e rotas |
| `docker-compose.e2e.yml`, `e2e/fakes/server.py` | Claude falso no e2e |
| `CLAUDE.md`, `docs/visao.md` | seção "Assistente de IA (desde a spec 008)" e backlog (no fim da implementação) |

**Ordem sugerida para o `/speckit-tasks`:**
0. migration `0008` + modelos + teste da migration (linhas da 006 preservadas);
1. `ia/tipos.py` + `regras_padrao.py` + teste de cruzamento com os schemas;
2. `ia/prompt.py`, `contexto.py`, `saida.py`, `custo.py`, `cliente.py` (o cliente da 006
   generalizado) + unitários;
3. `ia/service.py` + `router.py` (gerar, descartar) + integração; rotas da 006 delegando (US4);
4. `ia/aplicacao.py` + `ia` nos 5 saves + testes do princípio VII;
5. regras: `service_regras.py` + rotas + testes (dono/membro, padrão, revert);
6. registro e resumo + testes;
7. `gen:contract`; SPA: `lib/ia.ts`, `IaAssist`, `IaDiff`, `IaSelo`;
8. integração nas 5 telas com o `onSave` parcial e os campos sujos preservados (avatar primeiro:
   é o teste independente da US1; kit com as sugestões);
9. tela "Assistente de IA" (regras, registro, resumo);
10. Claude falso no e2e + `e2e/assistente-ia.spec.ts`; `CLAUDE.md` e `docs/visao.md`.

As fases 0 a 4 e 7 e 8 fecham as US1 e US4 (P1/P2 do dia a dia) e podem ir ao dono antes da tela
de regras e do registro.

## Riscos

| # | Risco | Mitigação |
|---|---|---|
| R-1 | **Idioma errado** num campo `en` (SC-004: 100% em inglês na descrição do avatar). O código não valida idioma | regra padrão e base fixa dizem o idioma exigido; a instrução em pt-BR ("mais detalhes do rosto") é traduzida, não copiada. O quickstart §3 mede as 10 gerações da SC-004. Se falhar, uma checagem barata (proporção de palavras ASCII/stopwords pt) vira aviso, sem bloquear |
| R-2 | **Custo aproximado diverge** da fatura (preço muda, fallback para outro modelo, cache) | `precos_versao` gravado, `model_servido` e tokens de cache registrados; a tela diz "≈". Mudou o preço: atualiza a tabela, e as chamadas antigas ficam com o preço da época |
| R-3 | **Regra editada pelo dono piora tudo** (ou pede formato impossível) | a base fixa não é editável (formato, limites e segurança sempre valem); histórico com reversão e "voltar ao padrão"; cada chamada registra a `regras_version` usada |
| R-4 | **Gasto sem teto** (clique repetido, loop de "Outra versão") | botão desabilitado durante a geração; resumo do mês visível; ≈ US$ 0,01 por chamada. Teto/limite no Redis fica para depois (Assumptions), se o registro mostrar abuso |
| R-5 | **Conflito com edições não salvas** (aplicar e outra pessoa salvou antes) | aplicar salva só aquele campo com a `version` do formulário; o 409 continua com "Recarregar", o painel guarda a proposta e o formulário não muda (edge case). O `marcar` ignora a aplicação se o campo não mudou na versão salva |
| R-9 | **Aplicar apaga o que foi digitado** nos outros campos (Q1 = B): o `PerfilDetalhe` e o `MarcaTab` remontam o formulário pela `key` com a versão | `useFormRebase` guarda os campos sujos antes do `onSave` e os reaplica sobre os dados novos; e2e ("edita o tom, aplica a descrição, o tom continua e salva sem 409") |
| R-10 | **Kit salvo com o `draft`** em vez dos tokens salvos (gravaria as outras seções não salvas) | o `onSave` do kit monta o corpo a partir da query do kit (`kit.data`), não do `draft`; e2e (paleta mudada sem salvar continua fora da versão) |
| R-6 | **Migration renomeando tabela** com FKs e índices da 006 | teste de migration com dados reais da 006 (upgrade → conferência → downgrade → upgrade); backup do banco antes do `alembic upgrade` no quickstart §0 |
| R-7 | **Prompt injection** por transcrição ou texto de vídeo | dados delimitados, sem tools, saída estruturada e nada aplicado sozinho (R6); fixtures de ataque nos testes |
| R-8 | **Espalhar a mudança por 5 telas** (formulários com padrões diferentes: `useState`, react-hook-form, `draft` do kit) | `IaAssist` recebe `value` e `onSave` e não conhece o formulário nem as rotas; cada tela escreve só o `onSave`. A integração por tela é pequena e coberta pelo e2e em ao menos avatar, kit e postagem |

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Tabela `ia_regras` (entidade versionada) | FR-007 pede regras editáveis pelo dono com histórico e reversão (princípio VII) | regras em arquivo ou em env: sem autor, sem histórico, fora da UI; semear as 13 linhas: congela o padrão no banco |
| Campo `ia` nos corpos de 5 saves | a marca "com ajuda da IA" precisa nascer na mesma transação da versão (FR-006, SC-003) | rota separada depois do save: `entity_versions` é imutável e haveria corrida; heurística comparando textos: frágil |
| Formato `sugestoes` (seleção, "Gerar mais", aceitos e rejeitados) | decisão do dono (Q3): bordões e séries crescem aos poucos, escolhendo item a item, sem repetir | a lista inteira substituída: o dono preferiu escolher item a item |
| `ANTHROPIC_BASE_URL` (config) + rota no `openshorts-fake` | o e2e do fluxo crítico (painel, aplicar, salvar, histórico) precisa de um Claude falso (princípio VI) | e2e só com `claude_unconfigured`: não testa o painel; `page.route` no navegador: não passa pela API nem pelo registro |
