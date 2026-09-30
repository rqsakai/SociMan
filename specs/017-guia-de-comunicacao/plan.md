# Implementation Plan: Guia de comunicação por perfil e conta (017-guia-de-comunicacao)

**Branch**: `017-guia-de-comunicacao` | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/017-guia-de-comunicacao/spec.md`

## Summary

A 017 dá ao assistente de IA da 008 uma **camada de voz** por perfil e por conta: tom, regras
"faça"/"não faça", vocabulário da casa, palavras proibidas, emojis, hashtags fixas e até 5
exemplos aprovados. As regras por tipo de campo continuam globais (008); o guia se soma a elas.
Nada publica (princípio I). Quatro blocos:

- **Guia (US1):** uma tabela nova, `ia_guias`, com uma linha por perfil (`conta_id` nulo) ou por
  conta, criada na primeira edição (como `ia_regras`: sem linha = sem guia, `version = 0`).
  Entidade versionada (`entity_type = "ia_guia"`), com histórico e **reversão só do dono**; só o
  dono edita, o membro vê (R1, R2, R11). Limites por campo e total, recusados campo a campo
  (R2). Validação cruzada perfil × conta: palavras proibidas acumulam e não podem aparecer no
  vocabulário, nos exemplos nem nas hashtags fixas de nenhum dos dois; as hashtags fixas somadas
  cabem no **máximo da conta** (padrão 5, configurável por conta até 8; Q3, R5, R6).
- **Prompt (US2):** o `system` passa a ter, nesta ordem: base fixa (`ia/2`) → regras do tipo →
  `<guia_perfil>` → `<guia_conta>` (só nos campos de destino, que têm conta) → bloco `<perfil>`
  com `cache_control`; o `user` continua com o contexto e, por último, a `<instrucao>` (R3, R4).
  O guia vai **delimitado como dado de orientação**: muda a voz, nunca o formato, os limites, o
  idioma exigido nem a segurança. Em conflito, a conta vence (R5). Os 3 campos visuais
  (`usa_guia = "so_proibidas"`, Q1) recebem só as palavras proibidas do perfil, e a tela deles
  ganha o link "Ver guia de comunicação do perfil" (R3).
- **Garantias no pós-processamento (US2):** as hashtags fixas entram sempre, primeiro, e contam no
  limite de 8 (R6); palavras proibidas são detectadas (sem acento, sem maiúsculas, palavra
  inteira), provocam a segunda tentativa e, se continuarem, marcam a proposta: o "Aplicar" direto
  fica bloqueado até o usuário editar, e o servidor recusa só o campo aplicado **sem edição** que
  contém a palavra; editado, passa (Q2 = A, R7). Cada chamada
  grava as versões dos guias usadas (R8).
- **Montar e testar (US3):** dois tipos novos no registro da 008: `guia.montar` (saída
  estruturada com os campos do guia; só vira guia ao salvar, e o save marca a chamada como
  `aplicada`/`editada`) e `guia.testar` (3 variações de título, descrição e hashtags para um
  conteúdo, com o guia do formulário, sem gravar nada além da chamada) (R9, R10).

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md). As perguntas para
o dono em [open-questions.md](open-questions.md) foram **respondidas em 2026-09-30** (spec →
Clarifications): Q1 (campos visuais só com as proibidas), Q2 = A (editado pode aplicar) e Q3
(máximo de fixas por conta, padrão 5).

## Technical Context

**Language/Version**: Python 3.12 (API) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**: nada novo.
- **Python:** `anthropic` (já na 006/008); normalização com `unicodedata` e `re` da biblioteca
  padrão (sem o pacote `regex`);
- **SPA:** componentes do shadcn que já existem (`Tabs`, `Dialog`, `AlertDialog`, `Badge`,
  `Tooltip`), `Field`/`NativeSelect` da 005, `VersionHistory` (`components/VersionHistory.tsx`) e `IaSelo` da 008. Só tokens de cor do tema
  (o tema escuro da 018 já está ativo).

**Storage**: PostgreSQL (NVMe): `ia_guias` (nova, com `max_hashtags_fixas` só na conta) e 4 colunas
em `ia_chamadas`. Nada no MinIO nem no HD.

**Testing**:
- pytest com o `anthropic_fake` da 008, ampliado com os formatos `guia` e `variacoes` e uma
  resposta com palavra proibida (inclusive num tipo `so_proibidas`);
- unitários: normalização e detecção de proibidas, fusão perfil × conta, render do bloco, ordem
  dos blocos do `system`, inserção das hashtags fixas, limites e validação cruzada;
- integração: CRUD do guia (dono × membro), histórico e reversão, 409, conta arquivada, gerar com
  guia (versões gravadas, fixas presentes, proibida marcada), aplicar sem editar recusado,
  montar (e o save marcando a chamada), testar (nada gravado além da chamada), migration 0012;
- princípio I: as rotas novas passam pela guarda de caminhos e `operationId`; princípio VII:
  toda mutação do guia cria versão com autor; gerar, montar e testar não criam versão;
- ruff; `check:web` com o contrato regenerado;
- Playwright `e2e/guia-comunicacao.spec.ts` com o Claude falso do `openshorts-fake` (formatos
  novos e o gatilho "proibida" na instrução).

**Target Platform**: a mesma stack; nenhum serviço novo.

**Project Type**: web application (SPA + API)

**Performance Goals**:
- o guia soma no máximo 4.000 caracteres por nível (≈ 1,2 mil tokens; dois níveis ≈ 2,5 mil).
  O p95 < 15 s da 008 continua: a entrada cresce, a saída não (R4);
- GET do guia da conta (com o do perfil, o efetivo e os conflitos): 3 consultas por chave única;
  p95 < 100 ms.

**Constraints**:
- nada publica e nada é salvo sem ação humana (008): montar só preenche o formulário; testar não
  grava conteúdo; o guia só muda no "Salvar" do dono;
- o guia não anula a base fixa (formato, limites, idioma exigido, segurança) nem as proibidas
  (FR-005); a instrução do usuário também não;
- o campo pertence a uma conta **só quando o alvo tem conta** (destino ou conteúdo + conta; os
  tipos `postagem.*` e `guia.testar`). Bio, bordões, séries e assets são do perfil (R5);
- CSP inalterada; nenhum texto do guia vai para log.

**Scale/Scope**:
- até ~10 perfis e ~30 contas: no máximo ~40 guias; dezenas de gerações por dia;
- 10 rotas novas (8 do guia, montar e testar) e o campo `ia` no save do guia; 4 colunas no
  registro; 2 tipos novos no registro da 008;
- telas: aba "Guia" no perfil, página do guia da conta, diálogos "Montar com IA" e "Testar guia",
  avisos no painel `IaAssist` e versões dos guias no registro.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Publicação só com decisão humana | ✅ | O guia só orienta textos (FR-008). Montar e testar usam o mesmo `messages.parse` **sem tools** da 008. As rotas novas ficam em `/api/perfis/{id}/guia`, `/api/contas/{id}/guia` e `/api/ia/guia/*`, com `operationId` `guias_*` e `ia_guia_*`, e passam pela guarda de caminhos (nenhum `publish`, `tiktok`…) |
| II. Direito é responsabilidade do dono | ✅ (não se aplica) | Não toca canais, envios nem status de direito. A transcrição continua como `<dados_terceiros>` |
| III. Marca em tokens | ✅ | O guia é **dado estruturado e validado por schema** (listas com limites, enum de emojis, hashtags normalizadas, exemplos tipados), e as garantias verificáveis (fixas, proibidas) são aplicadas por código, não pela prosa. O tom é o único texto livre, e é instrução de escrita, não regra de marca visual |
| IV. Contrato é a fonte única | ✅ | Rotas e schemas no OpenAPI → `gen:contract`; os limites do guia saem da API (`limites` na resposta do GET), não são copiados no SPA; `TipoCampoId` ganha os dois tipos novos no `Literal` |
| V. Segurança e segredos | ✅ | Nada de segredo novo. O guia entra delimitado (`<guia_perfil>`, `<guia_conta>`, com as tags de fechamento removidas do conteúdo) e a base fixa diz que ele não muda formato, limites nem segurança (R4). A descrição do "montar" é `<instrucao>`; o guia em edição do "testar" é dado |
| VI. Testes antes de pronto | ✅ | pytest (unidade, integração, migration), ruff, `check:web` e o e2e do guia com o Claude falso. VII e I com teste no backend |
| VII. Humano no controle | ✅ | O guia é entidade versionada (`ia_guia`): `version`, 409, `history.record` com autor e antes/depois, reversão **só do dono**, sem DELETE (limpar = salvar vazio). Gerar, montar e testar **não criam versão**. O save a partir do "montar" marca a chamada (`details.ia`, autor humano). Cada chamada registra as versões dos guias usadas (FR-006) |
| VIII. Simplicidade | ✅ | Uma tabela (`ia_guias`) e 4 colunas; nenhum serviço, dependência ou fila. Sem tags input novo (listas "uma por linha"), sem conferência de proibidas no navegador (o servidor decide, R7), sem sugestão de exemplos por métricas (fica para depois da 016) |

**Reavaliação pós-design:** mantida. A tabela de complexidade abaixo lista o que foi além do
mínimo.

Fora do escopo, de propósito (research R13): exemplos sugeridos pelos posts que mais performaram
(016), guia por tipo de campo, conferência de proibidas em texto digitado à mão, guia no MCP (009),
proibidas com variação automática (plural, conjugação).

## Project Structure

### Documentation (this feature)

```text
specs/017-guia-de-comunicacao/
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
├── migrations/versions/0012_guia_comunicacao.py    # ia_guias + enum guia_emojis; 4 colunas em ia_chamadas
├── src/sociman_api/ia/
│   ├── guia.py                                     # NOVO: GuiaCampos, limites, normalizar/achar proibidas,
│   │                                               #   fundir perfil × conta (GuiaEfetivo), conflitos, render do bloco
│   ├── service_guia.py                             # NOVO: obter, put (com `ia`), versões, revert, validação cruzada
│   ├── router_guia.py                              # NOVO: /api/perfis/{id}/guia…, /api/contas/{id}/guia…
│   ├── router.py                                   # + /api/ia/guia/{montar,testar} (junto das rotas da 008)
│   ├── models.py                                   # + IaGuia, GuiaEmojis; IaChamada + guia_perfil_version,
│   │                                               #   guia_conta_version, guia_rascunho, proibidas
│   ├── tipos.py                                    # + usa_guia; + guia.montar e guia.testar; Entidade "guia"; formatos guia/variacoes
│   ├── regras_padrao.py                            # + padrão de guia.montar (guia.testar usa as de postagem.textos)
│   ├── prompt.py                                   # ia/2: BASE fala do guia; blocos <guia_perfil>/<guia_conta>; ordem R3
│   ├── saida.py                                    # + PropostaGuia, PropostaVariacoes; fixas e proibidas em problemas/finalizar
│   ├── cliente.py                                  # passa o GuiaEfetivo para problemas/finalizar (sem mudança de chamada)
│   ├── service.py                                  # executar carrega os guias, grava versões/proibidas; montar e testar
│   ├── aplicacao.py                                # alvo "guia"; aplicar sem editar com proibidas → 400 ia_proibida
│   ├── schemas.py                                  # Valor + guia/variacoes; IaChamada + campos do guia
│   └── schemas_guia.py                             # NOVO: Guia, GuiaIn, GuiaContaOut, Conflito, MontarIn, TestarIn
├── src/sociman_api/main.py                         # inclui router_guia
└── tests/
    ├── fakes/anthropic_fake.py                     # + formatos guia/variacoes; resposta com proibida
    ├── unit/                                       # test_guia_normalizar, test_guia_fundir, test_prompt_guia, test_saida_guia
    └── integration/                                # test_guia_crud, test_guia_revert, test_gerar_com_guia,
                                                    #   test_ia_proibida, test_guia_montar, test_guia_testar,
                                                    #   test_migration_0012

apps/web/src/
├── lib/guia.ts                                     # NOVO: queries/mutations do guia, montar, testar
├── components/guia/
│   ├── GuiaForm.tsx                                # NOVO: campos, "uma por linha", contadores por campo e total, erros por campo
│   ├── GuiaHerdado.tsx                             # NOVO: o que vem do perfil (só leitura) na página da conta
│   ├── GuiaConflitos.tsx                           # NOVO: avisos de conflito perfil × conta
│   ├── MontarGuiaDialog.tsx                        # NOVO: descrição → proposta → preenche o formulário
│   └── TestarGuiaDialog.tsx                        # NOVO: escolhe conteúdo (+ conta) → 3 variações lado a lado
├── pages/perfis/tabs/GuiaTab.tsx                   # NOVO: aba "Guia" do perfil (form + histórico)
├── pages/perfis/ContaGuia.tsx                      # NOVO: /app/contas/:id/guia
├── pages/perfis/PerfilDetalhe.tsx                  # + aba "Guia"
├── pages/perfis/ContasTab.tsx                      # + ação "Guia de comunicação" em cada conta
├── components/ia/IaAssist.tsx                      # + aviso de proibidas; "Aplicar" desabilitado; "Guia usado: perfil vN · conta vM"
├── pages/ia/RegistroTab.tsx                        # + versões dos guias e proibidas no Sheet da chamada
└── App.tsx                                         # + rota /app/contas/:id/guia

e2e/fakes/server.py        # + formatos guia/variacoes; "proibida" na instrução devolve texto com a palavra
e2e/guia-comunicacao.spec.ts
```

**Structure Decision:**
- o guia mora no pacote `ia/` (é insumo do assistente, não do perfil): `perfis/` não muda, e o
  histórico do perfil e da conta não se mistura com o do guia (R1);
- as garantias (fixas e proibidas) ficam em `saida.py`, no mesmo ponto em que a 008 já normaliza
  hashtags e decide a segunda tentativa; o cliente não muda a forma de chamar o Claude;
- montar e testar são **tipos do registro da 008**, então herdam o log, o custo, o descartar e o
  resumo do mês sem código novo de registro.

**Migration:** `0012_guia_comunicacao`, `down_revision = "0011_metricas_tiktok"`. A 0011 (016) já
existe e está aplicada no dev, então a numeração está decidida. As duas não tocam as mesmas tabelas
(a 016 não mexe em `ia_chamadas`). Backup do banco de dev antes de aplicar (tasks T003).

### Arquivos existentes que a implementação toca

| Arquivo | Mudança |
|---|---|
| `apps/api/src/sociman_api/ia/models.py` | `IaGuia`, enum `GuiaEmojis`; 4 colunas em `IaChamada` |
| `apps/api/src/sociman_api/ia/tipos.py` | `usa_guia: "completo"\|"so_proibidas"` (`"so_proibidas"` em `avatar.descricao_prompt`, `cenario.prompt_ambiente`, `avatar.regras_imagem`, Q1); `guia.montar`, `guia.testar` (`listar_regras=False`, `regras_de="postagem.textos"`); `Entidade` + `"guia"`; `Formato` + `"guia"`, `"variacoes"` |
| `apps/api/src/sociman_api/ia/regras_padrao.py` | padrão de `guia.montar` |
| `apps/api/src/sociman_api/ia/prompt.py` | `PROMPT_VERSION = "ia/2"`; BASE com o parágrafo do guia; `_TAGS` + `guia_perfil`, `guia_conta`, `guia_em_teste`; `montar_system(tipo, regras, contexto, guias)` na ordem R3; limites de hashtags descontando as fixas |
| `apps/api/src/sociman_api/ia/saida.py` | schemas `PropostaGuia`, `PropostaVariacoes`; `problemas`/`finalizar` recebem o `GuiaEfetivo` (fixas, proibidas, aviso de emoji) |
| `apps/api/src/sociman_api/ia/cliente.py` | repassa o `GuiaEfetivo` a `problemas`/`finalizar` (junto do `Excluir`) |
| `apps/api/src/sociman_api/ia/service.py` | `executar` carrega os guias (`guia.em_vigor`), grava versões e proibidas; `montar_guia`, `testar_guia`; `chamadas_out` com os campos novos |
| `apps/api/src/sociman_api/ia/service_regras.py` | `listar` pula os tipos com `listar_regras=False`; `regras_em_vigor` segue `regras_de` |
| `apps/api/src/sociman_api/ia/aplicacao.py` | alvo `guia`; pré-checagem "aplicar sem editar com proibidas" (fora do `try` que engole erros) |
| `apps/api/src/sociman_api/ia/schemas.py` | `Valor` + `guia`, `variacoes`; `IaChamada` + `guiaPerfilVersion`, `guiaContaVersion`, `guiaRascunho`, `proibidas`; `AlvoTipo` + `"guia"` |
| `apps/api/src/sociman_api/main.py` | inclui `router_guia` |
| `apps/api/tests/fakes/anthropic_fake.py`, `tests/unit/test_constitution_guards.py`, `tests/unit/test_ia_tipos.py` | formatos novos; guarda cobre as rotas novas; cruzamento ignora os tipos `guia.*` (não têm schema de entidade) |
| `apps/web/src/components/ia/IaAssist.tsx` | aviso de proibidas e "Aplicar" desabilitado ("Editar e aplicar" liberado, Q2 = A); linha "Guia usado" |
| `apps/web/src/components/assets/AvatarCampos.tsx` | link "Ver guia de comunicação do perfil" (`/app/perfis/<id>?aba=guia`) junto dos 3 campos visuais (Q1) |
| `apps/web/src/pages/ia/RegistroTab.tsx` | versões dos guias e proibidas no Sheet |
| `apps/web/src/pages/perfis/PerfilDetalhe.tsx`, `ContasTab.tsx`, `App.tsx` | aba, ação e rota |
| `e2e/fakes/server.py` | formatos novos e gatilho "proibida" |
| `CLAUDE.md`, `docs/visao.md` | seção "Guia de comunicação (desde a spec 017)" e backlog (no fim) |

**Ordem sugerida para o `/speckit-tasks`:**
0. migration `0012` + `IaGuia` + colunas + `test_migration_0012`;
1. `ia/guia.py` (limites, normalização, proibidas, fusão, conflitos, render) + unitários;
2. `service_guia.py` + `router_guia.py` (GET/PUT/versions/revert de perfil e conta, dono × membro,
   validação cruzada) + integração → **fecha a US1 na API**;
3. `prompt.py` (ia/2, ordem, blocos), `saida.py` (fixas, proibidas), `service.executar` (versões e
   proibidas gravadas), `aplicacao.py` (recusa sem edição) + testes → **fecha a US2 na API**;
4. `guia.montar` e `guia.testar` (tipos, schemas de saída, rotas) + testes → US3 na API;
5. `gen:contract`; SPA: `lib/guia.ts`, `GuiaForm`, aba do perfil, página da conta, herdado e
   conflitos;
6. `IaAssist` (proibidas, guia usado) e registro;
7. diálogos montar e testar;
8. Claude falso + `e2e/guia-comunicacao.spec.ts`; `CLAUDE.md` e `docs/visao.md`.

As fases 0 a 3, 5 e 6 fecham as duas histórias P1 e podem ir ao dono antes de montar/testar.

## Riscos

| # | Risco | Mitigação |
|---|---|---|
| R-1 | **O modelo ignora o guia** (tom, vocabulário) e o dono não percebe | o guia vai no `system` antes do contexto, com os exemplos; a base pede que a explicação diga como o guia foi usado; quickstart §4 mede 10 gerações (SC-002). O que é verificável (fixas, proibidas) é garantido por código, não pelo modelo |
| R-2 | **Proibida escapa por variação** (plural, conjugação, grafia com número) | detecção por palavra inteira, sem acento e sem maiúsculas, também dentro das hashtags (sem espaços); a tela explica "liste as variações". Variação automática fica fora (R13) |
| R-3 | **Falso positivo** de proibida (palavra curta dentro de outra, ex.: "pix" em "pixel") | só palavra inteira (`(?<!\w)…(?!\w)`); nas hashtags, só a hashtag inteira igual à proibida sem espaços |
| R-4 | **Guia vira injeção** (texto colado de fora com "ignore as regras") | é escrito só pelo dono, vai delimitado, as tags de fechamento são removidas e a base diz que o guia não muda formato, limites nem segurança; saída estruturada e nada aplicado sozinho (008 R6) |
| R-5 | **Custo e tempo sobem** com guias longos | teto de 4.000 caracteres por guia (≈ 1,2 mil tokens), contador na tela; o registro da 008 mostra tokens e custo por chamada; o bloco do perfil segue com `cache_control` |
| R-6 | **Duas cabeças no Alembic** (0012 criada sobre uma base errada) | `down_revision = "0011_metricas_tiktok"` (já aplicada no dev); `alembic heads` com uma cabeça só (quickstart §0) e `test_migration_0012` |
| R-7 | **Validação cruzada trava o dono** (salvar o perfil com uma proibida que uma conta usa) | a mensagem diz qual conta e qual campo; nada é trocado sozinho. O GET da conta mostra os conflitos que não bloqueiam |
| R-8 | **Aplicar recusado surpreende** (400 `ia_proibida` no save) | o painel já mostra o aviso e desabilita o "Aplicar"; o 400 só acontece fora do SPA (MCP, cliente antigo) ou em corrida (o guia mudou entre gerar e aplicar) |
| R-9 | **Hashtags fixas empurram as do clipe para fora** | padrão de 5 fixas por conta (sobram ≥ 3 vagas); o dono pode subir até 8 por conta sabendo que sobra menos (a tela mostra "sobram N vagas para a IA"); o prompt diz quantas vagas sobram e, com 0, não pede hashtags |
| R-10 | **Máximo de uma conta menor que as fixas do perfil** (ex.: YouTube 3, perfil 5) | o save da conta e o do perfil recusam, citando a conta; a regra de soma é uma só (research R6); estado inválido herdado vira aviso e conflito, nunca erro de geração |

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Tabela `ia_guias` (entidade versionada) | FR-001/FR-002: guia por perfil e por conta, com histórico e reversão (princípio VII) | colunas em `perfis`/`contas`: misturaria o histórico e a reversão do guia com os dados da conta (reverter a conta desfaria o guia) e incharia o snapshot (R1) |
| Validação cruzada perfil × conta | FR-004/FR-005 e os edge cases (fixas acima do limite, exemplo com proibida) precisam valer para o guia **efetivo** | validar cada guia sozinho: uma conta poderia usar no exemplo uma palavra que o perfil proíbe, e o prompt se contradiria |
| Recusa de "aplicar sem editar" com proibidas no `marcar` | FR-004: impedir o Aplicar vale também fora do SPA (MCP) | só desabilitar o botão: um cliente sem a tela aplicaria a proposta com a palavra |
| Tipos `guia.montar` e `guia.testar` no registro | FR-007 com log, custo e resumo iguais aos outros usos da IA | rotas soltas com cliente próprio: duplicaria registro, custo e erros da 008 |
