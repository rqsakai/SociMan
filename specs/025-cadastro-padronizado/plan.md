# Implementation Plan: Cadastro padronizado de avatar, voz e cenário (025-cadastro-padronizado)

**Branch**: `025-cadastro-padronizado` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/025-cadastro-padronizado/spec.md`

## Summary

A 025 pluga o cadastro padronizado no motor de geração da **021** (`geracoes`, `geracao_candidatos`,
`audios`, `sociman gerador`, fila da GPU, limpeza de 90 dias) e **estende** a biblioteca da 007 sem
reescrevê-la. Nada publica (princípio I). Quatro blocos:

- **Kit do avatar e cenário (US1, US5, US6):** colunas novas em `assets` (`origem`, `consentimento`,
  `voz_id`, `identidade`, `kit_status`) e em `asset_files` (papéis `kit`/`variacao`, `slot`, `geracao_id`),
  com um ativo por slot. Os passos são pedidos pela rota genérica da 021; a 025 registra os **aplicadores**
  (validar, montar a entrada, aplicar a escolha, gancho de estado) no `geracao/passos.py`. O par 3/4 usa o
  `image_par_id` da 021 (uma opção = um par). A checagem de identidade é o passo de texto
  `avatar.identidade`, disparado pelo servidor ao completar ou trocar um slot, com o Claude da 008
  (`ia_chamadas.geracao_id`) e as **proibidas do guia** (017) aplicadas no caminho que grava direto: com
  proibida, as notas entram e a descrição não, sem 2ª tentativa automática (R4).
- **Looks e poses gerados (US4):** passos `avatar.look`/`avatar.pose` com o rosto frontal de referência e
  a base no corpo-base ou numa pose; o `prompt` nunca entra nas edições (FR-016).
- **Vozes do perfil (US2):** pacote novo `vozes/` (`entity_type = "voz"`), estados movidos pelo gancho
  `ao_mudar_estado` da 021, gravação original guardada completa, identificador no shop-tts derivado e
  estável (`"v_" + id.hex[:32]`, `[a-z0-9_]{2,40}`), sincronização pela linha `vozes_sync` do `gerador`
  (`/v2/voices/import`), "Testar" pelo passo `voz.teste` (estado `entregue` da 021) e voz padrão no avatar.
- **Pessoa real e revogação (US3):** consentimento registrado só por humano (dono ou membro); revogação
  só pelo dono, que arquiva, tira a voz do shop-tts (pedido aditivo `DELETE /v2/voices/{nome}`), bloqueia
  geração/restauração/reversão e **apaga** os arquivos da pessoa pelo delete restrito da 021
  (`excecao="lgpd_revogacao"`), com o evento `eliminacao_lgpd`: exceção 2 do princípio VII (4.3.0).

Detalhes em [research.md](research.md) (R1–R22), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md), [contracts/passos.md](contracts/passos.md),
[contracts/shop-tts-025.md](contracts/shop-tts-025.md) e [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite)

**Primary Dependencies**: nada novo. FastAPI, SQLAlchemy 2, Pydantic 2, o SDK `anthropic` (cliente da 008,
com blocos de imagem desde a 023), os clientes da 021 (`geracao/comfyui.py`, `geracao/shoptts.py`).
Na SPA: shadcn/ui, TanStack Query/Table, `Field`/`NativeSelect`, `VersionHistory`, `IaSelo` e os
componentes da 021 (`PedirGeracao`, `AndamentoGeracao`, `OpcoesGeracao`, `PlayerAudio`).

**Storage**: PostgreSQL (NVMe): 1 tabela nova (`vozes`), 5 colunas em `assets`, 2 em `asset_files`, 2
valores de enum. MinIO no HD: as imagens no bucket `sociman` e os áudios no `sociman-audios` (da 021),
com sentinela e piso (`datadir`). Nada novo no HD além disso.

**Testing**:
- pytest na stack efêmera (`npm run test:api`) com os fakes **da 021** (`comfyui_fake`, `shoptts_fake`,
  `dockerctl_fake`), o `shoptts_fake` ampliado com `DELETE /v2/voices/{nome}` e a inspeção das vozes, e o
  `anthropic_fake` com a saída de identidade (notas configuráveis; resposta com proibida);
- unitários: `assets/padrao.py` (situação, ordem dos passos, regex de menoridade, instruções sem o
  `prompt`), `vozes/tts_id.py`, forma do consentimento;
- integração: kit de ponta a ponta, par 3/4, identidade (completo, atenção, proibida não aplicada, Claude
  fora), troca de slot, revert com slot, consentimento, revogação (arquivos e linhas apagados, evento,
  bloqueios), vozes (estados pelo gancho, sincronização, troca de referência, teste, voz padrão, nome),
  provedor "em uso", permissões (MCP 403), migration `0023`;
- guardas: princípio I (rotas novas sem nome de rede), VII (versão com autor em toda mutação; o guarda
  `test_delete_so_nas_excecoes` da 021 passa a aceitar `sociman_api/revogacao.py`), "nunca auto" (os
  aplicadores de imagem e áudio só rodam pela escolha humana);
- ruff; `npm run check:web` com o contrato regenerado;
- Playwright `e2e/cadastro-padronizado.spec.ts` com o `openshorts-fake` (`/comfyui`, `/shop-tts`,
  Claude falso). Nenhum teste chama serviço real.

**Target Platform**: Linux (host `sakai-desktop`), Docker; SPA no desktop e no celular (modo casa).

**Project Type**: web (apps/api + apps/web); sem serviço novo (usa o `gerador` e o `agendador`
existentes).

**Performance Goals**: pedir passo < 300 ms (inclui a validação do aplicador); escolher < 500 ms (copia
até 2 arquivos e grava a versão); detalhe do avatar com o kit < 200 ms; revogação < 5 s para um avatar
com ~50 arquivos (as linhas na transação, os objetos depois do commit).

**Constraints**:
- 1 job de GPU por vez (021);
- `prompt` do avatar fora das edições de imagem;
- consentimento antes de qualquer mídia de pessoa real;
- MCP só lê;
- CSP inalterada;
- shop-tts só pela rede `gpu-local` (021 D2), por isso a sincronização roda no `gerador`.

**Scale/Scope**:
- dezenas de avatares, vozes e cenários por perfil;
- 13 rotas novas e 5 estendidas;
- 3 seções novas no detalhe do asset, 1 aba e 1 página novas.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.3.0**, emenda
aprovada pelo dono e aplicada na 1ª tarefa da 021: o princípio VII ganha 2 exceções de eliminação
nomeadas e auditadas, (1) candidatos não escolhidos aos 90 dias e (2) revogação LGPD só pelo dono)

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | Nada fala com rede social. Os aplicadores e o pacote `vozes/` não importam `publicacao/`; o único serviço externo novo é o shop-tts, pelo cliente da 021 com lista fechada (`ALLOWED` ganha só `DELETE /v2/voices/{nome}`). Rotas `assets_consentimento_*`, `vozes_*`, sem nome de rede |
| **II. Direito é responsabilidade do dono** | ✅ | Consentimento de pessoa real **registrado** antes de usar foto ou gravação (FR-009/FR-024), por humano, com autor no histórico; o SociMan não julga o mérito (pessoa famosa e menor em foto ficam com quem registra; termos de menoridade recusados) |
| **III. Marca em tokens** | ✅ (não afetado) | O kit de marca não muda; slots e notas são dado estruturado (enums, jsonb com schema), não prosa |
| **IV. Contrato é a fonte única** | ✅ | Schemas Pydantic → `npm run gen:contract`; os contratos externos (shop-tts) ficam em `contracts/*.md` e nos fakes, fora do OpenAPI |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. A prova do consentimento não sai para o MCP. Nenhuma porta nova. O acesso ao Docker é o da 021 (D1), sem nada a mais |
| **VI. Testes antes de pronto** | ✅ | Ver Testing. As inegociáveis têm teste no backend: escolha só humana (aplicadores), consentimento obrigatório (SC-003), revogação só do dono e só pela exceção 2 (guarda do delete), toda mutação com versão |
| **VII. Humano no controle** | ✅ com a exceção 2 da 4.3.0 | `history.record` em toda mutação de asset e voz (inclusive a checagem automática, com `details.automatico` e o autor do pedido); soft-delete (arquivar) em tudo; reversão do dono para asset e voz. **Exceção 2 (revogação LGPD):** só `RequireHumanOwner`, com confirmação, apaga a mídia da pessoa pelo `storage.apagar_por_excecao(excecao="lgpd_revogacao")`, usado só por `sociman_api/revogacao.py`, e grava o evento `eliminacao_lgpd` (quem, quando, contagem, motivo); o registro do consentimento e da revogação fica, sem mídia. A gravação original e a referência ficam fora da exceção 1 (provedor "em uso", R22). a limpeza do texto que descreve a pessoa nos snapshots antigos está coberta pelo texto da exceção 2 (D1 = sim) |
| **VIII. Simplicidade** | ✅ | Sem serviço, dependência ou fila nova. Uma tabela (`vozes`), colunas anuláveis e módulos dentro de `assets/`, `geracao/` e um pacote `vozes/` |
| Restrições: armazenamento NVMe × HD | ✅ | Mídia só no MinIO do HD (021); o PG guarda metadados |
| Restrições: banco | ✅ | `0023_cadastro_padronizado` (`down_revision = "0022_produtos_shop"`, provisório), com upgrade/downgrade e `test_migration_0023` |
| Restrições: portas | ✅ | Nenhuma porta nova |
| Restrições: containers UID 1000 | ✅ | Sem container novo |

**Reavaliação pós-design:** mantida. O design não criou serviço: a sincronização com o shop-tts foi para
uma linha do `gerador` da 021 (o único na rede `gpu-local`) em vez de uma trilha do agendador.

## Decisões do dono (2026-10-07)

| # | Decisão | Escolha |
|---|---|---|
| **D1** | Na revogação, limpar também o texto que descreve a pessoa nos **snapshots antigos** do histórico | **Sim.** `prompt`, `identidade` e a prova viram `null` em todas as versões do alvo; a linha da versão fica. A emenda 4.3.0 foi ajustada **antes** de ser aplicada: "revogação de consentimento de pessoa real (LGPD), só pelo dono: os arquivos e os textos que descrevem a pessoa (inclusive em versões antigas do histórico) são apagados; o registro de que houve consentimento e revogação fica, sem a mídia nem a descrição." |
| **D2** | Cenas (010) que usam o avatar revogado | **Só listar** na confirmação (`cenasAfetadas`), sem mexer nelas |
| 021 D1 | Acesso ao Docker | container `dockerctl` (da 021; a 025 não acrescenta nada) |
| 021 D2 | Rede para o ComfyUI e o shop-tts | rede `gpu-local` (por isso a `vozes_sync` roda no `gerador`) |
| 021 D3 | Quando mudar o shop-tts | o contrato `v2`, **inclusive o `DELETE /v2/voices/{nome}` da 025**, é feito **antes** da implementação da 025 (dependência externa, fora deste repo) |

## Contradições resolvidas no plano

| Contradição (spec, Notas para o plano) | Resolução |
|---|---|
| 1. Rostos 3/4 em par × 1 imagem por candidato | Coordenado com a 021: `geracao_candidatos.image_par_id` (direita) + `image_id` (esquerda), resultado `par_imagem`; uma escolha preenche os dois slots (R3) |
| 2. `vozes.name` livre × shop-tts `[a-z0-9_]{2,40}` | `tts_id = "v_" + id.hex[:32]`, derivado e estável, sem coluna; o `name` é só exibição (R11, `contracts/shop-tts-025.md`) |
| 3. "Testar" sem passo | Coordenado com a 021: passo `voz.teste`, estado final `entregue`, `aplica_alvo = False`, entra na limpeza (R13) |
| 4. `images`/`audios` nunca apagados × limpeza e revogação | Constitution 4.3.0 (2 exceções); o único delete é o `storage.apagar_por_excecao` da 021; a 025 usa só `lgpd_revogacao`, por `revogacao.py` (R10) |
| 5. Checagem grava o `prompt` direto × "Aplicar" por clique da 008 + proibidas da 017 | `tipo_campo = "avatar.identidade"` (`usa_guia = so_proibidas`), `achar_proibidas` no `aplicar`; com proibida, a descrição não é gravada e a chamada fica `sem_acao`; sem 2ª tentativa (o `aplicar` não chama rede) (R4) |
| 6. `prompt` "exatamente como enviado" | A checagem grava sem trim, até 2.000 (R4) |
| 7. `images.kind` do cenário | `cena`/`variacao` → `fundo`; kit/look/pose → `avatar`; prova → `imagem` (R16) |
| Uso da voz × provedores por `image_id` | `usadaPor` calculado no detalhe da voz, fora do `assets/usos.py` (R14); e o provedor "em uso" para a limpeza no `geracao/uso.py` (R22) |
| Voz com status próprio × estados da 021 | Gancho `ao_mudar_estado` do Aplicador, confirmado pela 021 (R2, `contracts/passos.md`) |
| "Quando usar" da pose no pedido × corpo da 021 | Campo `extras` (≤ 2 KB), confirmado pela 021 (R2) |
| Cenário piloto da 021 grava `referencia` | O aplicador da 025 troca para o slot `cena` (R2) |

## Project Structure

### Documentation (this feature)

```text
specs/025-cadastro-padronizado/
├── plan.md              # este arquivo
├── research.md          # R1–R22
├── data-model.md        # colunas novas da 007, `vozes`, estados, migration 0023
├── quickstart.md        # automático + manual com o dono (GPU e shop-tts reais)
├── contracts/
│   ├── http-api.md      # rotas do SociMan (OpenAPI gerado)
│   ├── passos.md        # passos da 025 no motor da 021 (aplicadores, gancho)
│   └── shop-tts-025.md  # DEPENDÊNCIA EXTERNA: tts_id e DELETE /v2/voices/{nome} (não editado aqui)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (não criado aqui)
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/
├── assets/
│   ├── models.py            # + colunas novas, FileRole kit/variacao, slot, geracao_id, snapshot
│   ├── service.py           # ganchos: snapshot, um ativo por slot, role × tipo, upload em slot, revert (R17)
│   ├── padrao.py            # NOVO, domínio puro: SLOTS, PASSOS, situacao, passo_aberto, PROIBIDO, instruções (R5–R8)
│   ├── service_padrao.py    # NOVO: aplicar escolha no slot/look/pose/variação, identidade, consentimento (R4, R9)
│   ├── schemas_padrao.py    # NOVO
│   └── router_padrao.py     # NOVO: /api/assets/{id}/consentimento… (R9, R10)
├── vozes/                   # NOVO: models, service, schemas, router, tts_id (R11–R15)
├── revogacao.py             # NOVO: revogação de avatar e voz; único usuário de lgpd_revogacao (R10)
├── geracao/
│   ├── aplicadores_avatar.py   # NOVO: 7 passos avatar.* (R2, R3, R4)
│   ├── aplicadores_cenario.py  # NOVO: cenario.cena (troca o piloto) e cenario.variacao
│   ├── aplicadores_voz.py      # NOVO: voz.gravacao, voz.design, validação do voz.teste, gancho de estado
│   ├── vozes_sync.py           # NOVO: linha do `gerador` (import/remover no shop-tts) (R12)
│   ├── passos.py               # registra os aplicadores da 025
│   ├── uso.py                  # registra o provedor vozes_e_consentimento (R22)
│   └── shoptts.py              # ALLOWED + DELETE /v2/voices/{nome}
├── ia/tipos.py              # + TipoCampo "avatar.identidade" (en, so_proibidas) e schema de saída
├── mcp/mapa.py              # tools de leitura de vozes; escritas na lista proibida
├── history.py               # entity_type "voz"
└── main.py                  # include_router (vozes, padrão)
apps/api/migrations/versions/0023_cadastro_padronizado.py
apps/api/tests/
├── fakes/shoptts_fake.py (+DELETE, inspeção), anthropic_fake.py (+identidade)
├── integration/padrao_helpers.py
├── unit/test_padrao.py, test_tts_id.py, test_constitution_guards.py (+025)
└── integration/test_kit_avatar.py, test_identidade.py, test_cenario_padrao.py, test_looks_poses.py,
    test_vozes.py, test_vozes_sync.py, test_revogacao.py, test_padrao_permissoes.py,
    test_assets_revert_slot.py, test_migration_0023.py
e2e/fakes/server.py           # /shop-tts DELETE, /geracao-e2e/vozes-tts, Claude: formato identidade
e2e/cadastro-padronizado.spec.ts

apps/web/src/
├── pages/assets/AssetDetalhe.tsx        # seções Kit padrão, Origem e consentimento, Voz padrão; Cena e Variações
├── pages/assets/kit/KitAvatar.tsx, SlotCard.tsx, ConsentimentoCard.tsx, RevogarDialog.tsx, CenaVariacoes.tsx
├── pages/perfis/tabs/VozesTab.tsx       # ?aba=vozes (DataTable)
├── pages/vozes/VozDetalhe.tsx           # /app/vozes/:id
├── lib/vozes.ts, lib/padrao.ts          # hooks TanStack Query
└── App.tsx                              # rota /app/vozes/:id
```

**Structure Decision**: o web app que já existe. A seta de dependência segue a da 021: `geracao/` →
`assets/`, `vozes/`; `assets/` e `vozes/` não importam o motor. A revogação fica num módulo próprio na raiz
do pacote para o guarda do delete apontar um arquivo só.

**Ordem sugerida para as tasks** (o `/speckit-tasks` detalha):
1. **Gate:** a 021 implementada (motor, `image_par_id`, `voz.teste`/`entregue`, `extras`, gancho
   `ao_mudar_estado`, delete restrito) e a constitution 4.3.0 aplicada (com o texto ajustado de D1); shop-tts `v2` + `DELETE /v2/voices/{nome}` no ar (021 D3);
   conferir o número da migration.
2. Migration `0023` + models + `padrao.py` (unitários).
3. Aplicadores do kit do avatar + identidade (008/017) + troca de slot (US1, US6).
4. Consentimento + origem pessoa real (US3).
5. Vozes: pacote, aplicadores, gancho, sync no `gerador`, teste, voz padrão (US2).
6. Looks e poses (US4); cenário: cena e variações (US5).
7. Revogação + evento + guarda (US3, FR-033a).
8. MCP (mapa), contrato gerado, SPA, e2e.
9. Quickstart com o dono (GPU real e shop-tts com o contrato `v2` + `DELETE`).

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Apagar mídia na revogação (VII, exceção 2 da 4.3.0) | A LGPD dá à pessoa o direito de eliminação, e a emenda 4.3.0 nomeou esta exceção | Só arquivar: a mídia da pessoa continuaria no HD e no shop-tts |
| Limpar texto nos snapshots antigos (VII) — D1 = sim | A descrição física é dado pessoal; manter no histórico frustra a eliminação (coberto pela exceção 2 da 4.3.0) | Manter: não atenderia ao pedido de eliminação |
| Gancho `ao_mudar_estado` no protocolo da 021 | O status da voz (insumo) acompanha a geração na mesma transação | Calcular o status na leitura: o insumo pede a coluna e a lista/MCP precisariam consultar as gerações |
