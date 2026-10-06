---

description: "Tarefas da feature 020-historico-tiktok-studio"
---

# Tasks: Histórico do TikTok Studio (020-historico-tiktok-studio)

**Input**: `specs/020-historico-tiktok-studio/` (spec com Clarifications e "Ajustes depois do arquivo real",
plan, research R1–R15, data-model, contracts/http-api.md, quickstart, notas-pesquisa)

**Pré-requisito:** a 019 (analytics) tem de estar estável e verde, porque a 020 mexe em `analytics/base.py`,
`visao_geral.py`, `contas.py`, `quando_postar.py`, `schemas.py` e nas abas da SPA. Nenhum outro agente
pode estar editando esses arquivos ao mesmo tempo.

**Decisões do dono (2026-10-02):**
- **Q1:** formato com cabeçalho em inglês e pt-BR reconhecido sozinho. **Ajuste confirmado:** só ZIP e
  CSV, **sem XLSX**.
- **Q2:** vale a API; o Studio vale nos dias anteriores à 1ª coleta **e no dia da 1ª coleta**, e aparece
  como comparação no tooltip nos dias cobertos.
- **Q3:** o arquivo por vídeo (Conteúdo) fica fora.
- **Ajuste confirmado:** a pré-visualização fica no Redis por 30 min, é de uso único, e os arquivos
  **nunca** vão para disco nem para o MinIO.

**Nomes canônicos:**
- **API:** pacote `sociman_api/metricas/studio/` (`formato`, `arquivos`, `datas`, `models`, `efetivo`,
  `previa`, `service`, `schemas`, `router`).
  - Rotas: `POST /api/contas/{id}/studio/previa`, `POST /api/contas/{id}/studio/importacoes`,
    `GET /api/contas/{id}/studio/importacoes`, `GET /api/contas/{id}/studio/cobertura` e
    `POST /api/studio/importacoes/{id}/desfazer`. `operationId` `studio_*`.
  - Tabelas `metricas_studio_importacoes` e `metricas_studio_dias`. `entity_type` `studio_importacao`.
  - Migration **`0013_historico_studio`** (`down_revision = "0012_guia_comunicacao"`). A 009 usará a 0014
    apontando para esta.
- **SPA:** `pages/perfis/ContaStudio.tsx` (`/app/contas/:id/studio`), `components/studio/*` e
  `lib/studio.ts`.
- **Testes:** `tests/integration/studio_helpers.py` (gerador **sintético**, conta `contateste`) e
  `e2e/studio.spec.ts`.

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec -T api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/studio.spec.ts]`.

Nada chama serviço real. **Os ZIPs reais do dono nunca entram no repositório nem nos testes.**

**Arquivos compartilhados, SÓ ACRÉSCIMO:** `apps/api/src/sociman_api/main.py`, `apps/web/src/App.tsx`,
`apps/api/tests/unit/test_constitution_guards.py`, `e2e/helpers.ts`, `.gitignore`, `CLAUDE.md`,
`docs/visao.md`. `packages/contract/**` é gerado.

**Segredos e privacidade:** nenhuma consulta ou log imprime nome de arquivo com @, handle ou conteúdo
de CSV real; só contagens.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US5 da spec

---

## Phase 1: Setup

- [X] T001 **Gate:**
  - `ls apps/api/migrations/versions/` mostra **0012_guia_comunicacao** como a última e nenhum arquivo
    `0013_*` (se já houver, pare e avise o líder);
  - `docker compose exec api uv run alembic heads` mostra só `0012_guia_comunicacao`;
  - os testes da 019 estão verdes: `npm run test:api -- tests/ -k "analytics" -q`;
  - `git status` só tem o esperado;
  - `.specify/feature.json` aponta para a 020 (o líder cuida).
- [X] T002 [P] `.gitignore` (acréscimo): `Overview_*.zip`, `Followers_*.zip`, `Content_*.zip`,
  `Viewers_*.zip`, `Overview.csv`, `FollowerHistory.csv` e `Content.csv` na raiz do repositório e em
  `apps/`. Conferir com `git check-ignore -v` (os fixtures sintéticos são gerados em memória, não em
  arquivo).

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** banco, leitura pura dos arquivos, valor efetivo e gerador sintético.

- [X] T003 Migration `apps/api/migrations/versions/0013_historico_studio.py` (`revision =
  "0013_historico_studio"`, `down_revision = "0012_guia_comunicacao"`), conforme o data-model:
  - o enum `studio_importacao_estado`;
  - `metricas_studio_importacoes` e `metricas_studio_dias`, com todos os CHECKs e índices;
  - o trigger `metricas_studio_so_insercao`, que reaproveita `metricas_recusa_mudanca()`.

  No downgrade, a função da 0011 fica.
- [X] T004 [P] `apps/api/tests/integration/test_migration_0013.py`:
  - sobe sobre a 0012 com séries vivas e anônimas;
  - cada CHECK recusa com `INSERT` direto;
  - o trigger recusa `UPDATE` e `DELETE`, e o `TRUNCATE` passa;
  - down e up.
- [X] T005 `metricas/studio/models.py`:
  - `Importacao` (`_Versioned`, `AuditMixin`; `__versioned_fields__` do data-model; `__immutable_fields__
    = ()`; `nomes_arquivos` fora do snapshot);
  - `DiaStudio` (sem `version`).

  Registrar no `env.py` e no metadata, se necessário.
- [X] T006 [P] `metricas/studio/formato.py` (R1): `SINONIMOS` (en confirmado, pt-BR com
  `provisorio=True`), a detecção de seção pelo cabeçalho (com as seções não importadas: Conteúdo,
  Atividade, Gênero, Territórios, Espectadores), a leitura `utf-8-sig`, os números (milhar, recusa de
  decimal, K/M e negativo, exceto `seguidores_dif`), as linhas vazias e a contagem de campos. Funções
  puras, devolvendo as linhas mais uma lista de `Problema(arquivo, linha, coluna, valor, motivo)`.
- [X] T007 [P] `metricas/studio/datas.py` (R3, R14):
  - meses en e pt;
  - formatos "September 25", "Sep 25", "25 de setembro", "setembro 25", `AAAA-MM-DD` e `DD/MM/AAAA`;
  - regex dos nomes de ZIP (com " (1)"), handle normalizado, epoch → dia em `APP_TZ`;
  - ano pelo nome do ZIP (o início bate com a 1ª linha, o fim bate com a última) e dedução para trás;
  - virada de ano, ordem estritamente crescente, salto ≥ 366 dias, hoje (ignorado) e futuro (erro).
- [X] T008 [P] `metricas/studio/arquivos.py` (R2):
  - teto de 5 MB por requisição (`read(limite + 1)`) e detecção por assinatura (`PK\x03\x04`);
  - o ZIP em memória, com ≤ 20 entradas, Σ `file_size` ≤ 20 MB, razão ≤ 100:1, sem caminho absoluto,
    `\`, `..`, unidade, pasta, link (S_IFLNK), `.zip` interno, cifrado ou método fora de stored/deflate;
  - só abre `Overview.csv` e `FollowerHistory.csv` (`read(teto + 1)`), lista os outros como ignorados
    **sem abrir** e calcula o SHA-256 dos bytes de cada CSV;
  - recusa XLSX ou "Baixar seus dados" com orientação. **Proibido** `extract`/`extractall`.
- [X] T009 [P] Testes unitários das funções puras:
  - `tests/unit/test_studio_formato.py`: cabeçalhos en e pt, ordem diferente das colunas, coluna
    opcional ausente, desconhecida ignorada, números válidos e inválidos, dia repetido igual e
    diferente, seção errada;
  - `tests/unit/test_studio_datas.py`: o caso real (25/09–01/10 com epoch 1790891174), **virada de ano**
    (Dec 30 → Jan 2) pelo nome do ZIP e pela dedução, nome do ZIP que não bate, fora de ordem, hoje
    ignorado, futuro, sufixo " (1)", handle com `.` e `_`;
  - `tests/unit/test_studio_zip.py` (**ZIP malicioso**): bomb (razão e tamanho), slip (`../x`,
    `/etc/x`, `C:\x`), link simbólico, cifrado, aninhado, 21 entradas, método bzip2, `Content.csv`
    nunca aberto (espião em `ZipFile.open`), CSV renomeado de ZIP, envio de 5 MB + 1 byte.
- [X] T010 [P] `tests/integration/studio_helpers.py`: o gerador **sintético** no formato real (BOM,
  aspas, sem `\n` final, "September 25", `Overview_<início>_<epoch>_<handle>.zip`, `Followers_<handle>.zip`
  com Activity, Gender e Territories só com cabeçalho, e o `Content_<handle>.zip` com título falso). Tem
  variantes pt-BR, virada de ano e defeitos, mais a função `semear_coleta(serie, primeira_em)` (reusa
  `metricas_helpers.semear`). Também é uma CLI `python -m tests.integration.studio_helpers --handle H
  --saida DIR` para o quickstart.
- [X] T011 `metricas/studio/efetivo.py` (R6; só leitura):
  - `primeiro_dia_coberto(db, serie_ids)`: `min(coletado_em)` das fotos de conta e de vídeo → dia em
    `APP_TZ` + 1;
  - `dias(db, serie_ids, de, ate)`: `DISTINCT ON` por seção, a ativa mais antiga;
  - `fonte_do_dia(...)`, conforme a tabela "Fonte do dia" do data-model.
- [X] T012 [P] `tests/integration/test_studio_efetivo.py`: o 1º dia coberto (o dia da 1ª coleta **não**
  é coberto); a ativa mais antiga vale; uma desfeita não vale e a próxima ativa assume; seções
  independentes (visão geral de uma importação e seguidores de outra); série sem coleta.
- [X] T013 `metricas/studio/schemas.py`: `Previa`, `Importacao` e `Cobertura` (camelCase, como no
  contrato), mais os códigos de erro novos em `errors.py`, se houver catálogo.

**Checkpoint:** a migration aplica, as funções puras e o valor efetivo estão testados, e o gerador
sintético está pronto.

---

## Phase 3: User Story 1 - Importar com pré-visualização (Priority: P1) 🎯 MVP

**Goal:** o dono envia os ZIPs, vê a prévia e confirma; os dias são gravados com a fonte `studio`.

**Independent Test:** enviar os ZIPs sintéticos de 7 dias, conferir as contagens e os totais, confirmar
e ver os 7 dias gravados com o autor.

### Testes da US1

- [X] T014 [P] [US1] `tests/integration/test_studio_previa.py`:
  - prévia com os 2 ZIPs (período, `anoOrigem`, seções, ignorados, totais, amostra de 5 + 5);
  - **nada gravado** (0 linhas nas 2 tabelas);
  - chave no Redis com TTL ≤ 1800;
  - só a Visão geral; só Seguidores;
  - contagens `coletados`/`iguais`/`divergentes`/`faltando`/`ignorados` (data-model).
- [X] T015 [P] [US1] `tests/integration/test_studio_importacao.py`:
  - confirmar grava tudo ou nada (falha forçada no meio → 0 linhas);
  - `history` versão 1 **sem nome de arquivo nem handle** no snapshot;
  - `nomes_arquivos` gravado;
  - **2 cliques** → o 2º recebe 410 `previa_indisponivel`;
  - **base mudou** (outra importação entre a prévia e o confirmar) → 409 `previa_desatualizada`;
  - prévia de outro usuário ou conta → 410;
  - **SC-004:** contar e somar com hash as fotos de conta e de vídeo antes e depois → idênticas.
- [X] T016 [P] [US1] **Idempotência** (no mesmo arquivo de teste):
  - reenviar os mesmos ZIPs → a prévia traz `jaImportada` e `podeConfirmar = false`, e confirmar dá 200
    com `gravados = 0`, sem versão nova;
  - re-zipar o mesmo CSV (outro ZIP, mesmos bytes do CSV) → idempotente;
  - envio com uma seção repetida e outra nova → só a nova é gravada;
  - um arquivo sobreposto e diferente → grava todos os dias, mas o valor efetivo continua o da
    importação anterior ("divergentes").

### Implementação da US1

- [X] T017 [US1] `metricas/studio/previa.py`:
  - monta a prévia (arquivos → formato → datas → validação por conta e @ → contagens contra
    `efetivo` → avisos `diverge_da_coleta` 30%, `dia_incompleto`, `dias_faltando`, `periodo_longo`,
    `ano_deduzido`, `colunas_ausentes` e `cabecalho_provisorio`);
  - grava no Redis `studio:previa:<uuid>` (TTL 1800) com a `base`;
  - `consumir(previa_id, user, conta)` com `GETDEL`.
- [X] T018 [US1] `metricas/studio/service.py::confirmar`:
  - `pg_advisory_xact_lock(hashtext('studio:'||serie_id))` e conferência da base;
  - descarta as seções com SHA igual a uma ativa;
  - `INSERT` da importação e dos dias em lote, mais `history.record("created", details={secoes,
    gravados})`;
  - sem nenhuma seção nova → devolve a importação existente com `gravados = 0`;
  - exige `confirmoConta` quando `exigeConfirmacaoConta`.
- [X] T019 [US1] `metricas/studio/router.py`: `studio_previa` (multipart `arquivos`, `RequireHumanOwner`),
  `studio_confirmar` (`RequireHumanOwner`) e `studio_importacoes` (GET, `RequireUser`). `serie_indisponivel`
  quando a conta não é TikTok ou não tem série viva. `include_router` em `main.py` (acréscimo).
- [X] T020 [US1] `npm run gen:contract` e `lib/studio.ts` (hooks: `usePreviaStudio` em mutation
  multipart, `useConfirmarStudio` e `useImportacoesStudio`).
- [X] T021 [US1] SPA `pages/perfis/ContaStudio.tsx` + `components/studio/EnvioArquivos.tsx` e
  `PreviaStudio.tsx`:
  - input `multiple accept=".zip,.csv"` com instrução curta de onde baixar no Studio;
  - prévia com período e origem do ano, contagens por seção, totais, colunas, avisos e amostra
    (tabela com `situacao`);
  - "Confirmar importação" e "Cancelar";
  - estado "já importado".

  Rota `/app/contas/:id/studio` em `App.tsx` (acréscimo). Link "Histórico do Studio" no cartão da conta
  TikTok em `pages/perfis/ContasTab.tsx`.
- [X] T022 [US1] `e2e/helpers.ts` (acréscimo): `zipStudio(entradas)`, um gerador de ZIP **stored** em
  memória (cabeçalhos local e central, CRC com `zlib.crc32` do Node 22), sem dependência nova, mais
  `csvOverview(dias)` e `csvSeguidores(dias)` no formato real. A conta de teste é a do e2e. Os arquivos
  vão por `setInputFiles({ name, mimeType, buffer })`, como em `assets.spec.ts`.
  `e2e/studio.spec.ts`, parte 1: o dono envia, vê a prévia, confirma e vê a importação na lista;
  reenviar mostra "já importado".

**Checkpoint:** a US1 funciona sozinha (sem analytics).

---

## Phase 4: User Story 2 - Arquivo íntegro e conta certa (Priority: P1)

**Goal:** recusas claras para cada defeito; o @ do ZIP é conferido; o CSV solto pede confirmação.

**Independent Test:** cada arquivo defeituoso sintético recusado com o código, a linha e a coluna
certos, e 0 linhas gravadas.

- [X] T023 [P] [US2] `tests/integration/test_studio_validacao.py` (pela rota, SC-003), um caso por
  defeito:
  - `studio_formato` (sem `Date`, sem `Video Views`, vazio, codificação inválida);
  - `studio_invalido` (futuro, negativo, "1.2K", "12.5", dia repetido diferente; lista ≤ 50 com
    `total`);
  - `studio_datas` (fora de ordem, nome do ZIP que não bate);
  - `studio_secao_nao_importada` (Content, Viewers.xlsx, um XLSX qualquer, um JSON do "Baixar seus
    dados");
  - `studio_zip_inseguro` (amostra de R2);
  - `arquivo_grande` (413);
  - `studio_arquivos` (0 ou 3 arquivos, a mesma seção 2×).

  Em todos, 0 linhas no banco e nenhuma chave no Redis.
- [X] T024 [P] [US2] Conta e @ no mesmo arquivo de teste:
  - ZIP `…_outraconta.zip` → `studio_conta_diferente`;
  - dois ZIPs com @ diferentes → `studio_conta_diferente`;
  - handle com caixa diferente passa;
  - CSV solto → `exigeConfirmacaoConta = true`, confirmar sem `confirmoConta` → 400 `confirmar_conta`,
    e com ele → 201;
  - série anonimizada ou conta não TikTok → 409 `serie_indisponivel`.
- [X] T025 [P] [US2] Avisos: `diverge_da_coleta` com a coleta semeada (dias cobertos, diferença > 30%) sem
  bloquear; `dia_incompleto` (linha de hoje ignorada); `ano_deduzido` (CSV solto); `cabecalho_provisorio`
  (variante pt-BR).
- [X] T026 [US2] Mensagens em pt-BR de cada código no `ErrorEnvelope` (com orientação do que enviar) e
  exibição na SPA: lista de problemas (arquivo, linha, coluna, valor), "e mais N", e a caixa "confirmo
  que este arquivo é de @conta" que libera o botão.
- [X] T027 [US2] `e2e/studio.spec.ts`, parte 2: ZIP de outra conta recusado com a mensagem; CSV solto exige
  a caixa; arquivo com data futura mostra a linha do problema.

---

## Phase 5: User Story 3 - O analytics usa o histórico (Priority: P1)

**Goal:** os indicadores, a série diária, o calendário e as contas da 019 usam o Studio nos dias que a
coleta não cobre inteiros, mostrando a fonte.

**Independent Test:** 7 dias importados que terminam no dia da 1ª coleta, mais 3 dias de coleta; a visão
geral de 14 dias bate com a referência.

### Testes da US3 (escrever ANTES de mexer em `analytics/`)

- [X] T028 [US3] **Regressão "sem Studio = números de hoje"** em
  `tests/integration/test_studio_analytics.py`:
  - antes de qualquer mudança em `analytics/`, gravar como referência a saída atual de
    `/api/analytics/visao-geral`, `/quando-postar` (calendário) e `/contas` sobre os dados de
    `analytics_helpers` em 3 períodos;
  - o teste exige que, **sem importação**, os números e as séries continuem idênticos depois da
    mudança (os campos novos são aditivos e ignorados na comparação).
- [X] T029 [P] [US3] Referência com Studio (mesmo arquivo de teste):
  - views, likes, engajamento e seguidores = Σ por dia com a regra da fonte;
  - o **dia da 1ª coleta** usa o Studio (e não o salto das views acumuladas);
  - os dias cobertos usam a API, com `comparacao` = Studio;
  - `diasStudio` e `contexto.studio`;
  - o período anterior só com Studio dá variação %;
  - `visitasPerfil` na série;
  - calendário com `fonte` `studio`/`misto` e `contasStudio`;
  - uma conta com Studio e sem vídeo coletado aparece;
  - só a Visão geral importada → os seguidores dos dias do Studio ficam "sem dado" (nada estimado,
    FR-016);
  - abas por vídeo ou hora sem mudança (FR-020).
- [X] T030 [US3] SC-006 no mesmo arquivo: importar → desfazer (pelo service da US4) → os números voltam
  exatamente à referência da T028. **Roda depois da T037.** Até lá, fica marcado `xfail` com o motivo.

### Implementação da US3

- [X] T031 [US3] `analytics/base.py`:
  - `ganhos_por_dia` com os 4 contadores (views, likes, comments, shares) por vídeo e por dia;
  - `totais_diarios(db, filtro, periodo) → {serie: {dia: TotalDia}}`, com o ganho diário de seguidores
    da API e a regra de `metricas.studio.efetivo.fonte_do_dia`;
  - as séries do escopo vêm do filtro.
- [X] T032 [US3] `analytics/visao_geral.py`:
  - `valores` sobre os totais diários (o período e o anterior);
  - `serie_diaria` com `fonte`, `comparacao` e `visitas_perfil`;
  - `Indicador.dias_studio` e `contexto.studio`.

  `analytics/contas.py`: a tabela por conta e perfil e o eixo `crescimento` do radar usam
  `totais_diarios`. `analytics/quando_postar.py::calendario`: `fonte` e `contas_studio`.
  `analytics/schemas.py`: os campos aditivos do contrato.
- [X] T033 [US3] `npm run gen:contract`. A T028 e a T029 ficam verdes.
- [X] T034 [US3] SPA (rota lazy do analytics):
  - `VisaoGeral.tsx`: a série diária com duas séries por conta (coletado sólido; Studio tracejado,
    opacidade 0,6, mesma cor de entidade) e a legenda "importado do Studio";
  - o tooltip com a fonte e a comparação, escapado (ADR 0002);
  - o `Indicador` com "inclui N dias importados do Studio";
  - "Visitas ao perfil" como série opcional;
  - `QuandoPostar.tsx`: o calendário com contorno tracejado nos dias `studio`/`misto`;
  - tabela alternativa e CSV com a coluna `fonte`;
  - nota de leitura do fuso do Studio;
  - abas por vídeo ou hora: a nota de FR-020 quando `contexto.studio.dias > 0` e não há post coletado;
  - `Contas.tsx`: o link "Histórico do Studio" por conta;
  - Visão geral: o atalho "Importar histórico do Studio" (só dono) quando o período começa antes da 1ª
    coleta.
- [X] T035 [US3] `e2e/studio.spec.ts`, parte 3: depois de importar, `/app/metricas` mostra os dias do
  Studio (legenda e linha na tabela alternativa com `fonte = studio`) e a nota no indicador.
  `e2e/analytics.spec.ts` continua verde.

---

## Phase 6: User Story 4 - Desfazer (Priority: P2)

**Goal:** o dono desfaz uma importação, com histórico; os dias ficam guardados, mas deixam de valer.

**Independent Test:** importar → desfazer → o analytics volta; a lista e o histórico mostram "desfeita
por… em…"; reimportar o mesmo arquivo cria uma importação nova.

- [X] T036 [P] [US4] `tests/integration/test_studio_desfazer.py`:
  - desfazer → `estado = desfeita`, `desfeita_em`/`desfeita_por` e a versão 2 com `{acao: "desfeita"}`;
  - as linhas dos dias continuam (contagem igual);
  - `version` errada → 409 `version_conflict`; desfazer de novo → 409 `ja_desfeita`;
  - **reimportar o mesmo arquivo** depois de desfazer → a prévia trata como novo, e confirmar cria outra
    importação;
  - duas ativas sobrepostas: desfazer a mais antiga → a outra passa a valer (US4.3);
  - uma prévia feita antes do desfazer → 409 `previa_desatualizada`.
- [X] T037 [US4] `service.desfazer` (lock da série, `check_version`, `history.record("updated")`) e a
  rota `studio_desfazer` (`RequireHumanOwner`); `gen:contract`.
- [X] T038 [US4] SPA `components/studio/ListaImportacoes.tsx`: tabela (data, autor, seções, período,
  dias, estado) e "Desfazer" (só dono), com AlertDialog explicando que os dias saem do analytics e
  continuam guardados.
- [X] T039 [US4] `e2e/studio.spec.ts`, parte 4: desfazer → a importação fica "desfeita" e os dias do
  Studio somem do analytics.

---

## Phase 7: User Story 5 - Cobertura, exportação e anonimização (Priority: P3)

**Goal:** faixas por fonte e seção com buracos; o dataset da 016 traz os dias importados; a anonimização
apaga os nomes dos arquivos.

- [X] T040 [P] [US5] `tests/integration/test_studio_cobertura.py`: faixas contínuas por seção, a
  sobreposição com a coleta, os buracos (dia faltando no arquivo), uma série sem coleta (buracos até
  ontem) e as desfeitas fora.
- [X] T041 [P] [US5] `tests/integration/test_studio_export.py`: `studio_dias.csv` e `.jsonl` só de
  ativas, as colunas da R10, `efetivo_*` corretos, o `dicionario.csv` com `versao = 2`, e uma série
  anônima como "Conta anônima N".
- [X] T042 [P] [US5] `tests/integration/test_studio_anonimizar.py`: anonimizar a série →
  `nomes_arquivos = NULL`, os dias intactos (o trigger não dispara, porque não há UPDATE neles), nenhum
  handle nas versões `studio_importacao`, e `details.importacoes` na anonimização.
- [X] T043 [US5] `efetivo.cobertura` mais a rota `studio_cobertura` (`RequireUser`) e o `gen:contract`.
- [X] T044 [US5] `metricas/export.py` + `dicionario.py` (R10) e `metricas/anonimizar.py` (R9).
- [X] T045 [US5] SPA `components/studio/CoberturaBarras.tsx`: barras em CSS por seção (Studio, coleta,
  buracos), legenda e tabela acessível. Visível para dono e membro, no topo de `ContaStudio.tsx`.
- [X] T046 [US5] `e2e/studio.spec.ts`, parte 5: o membro abre `/app/contas/:id/studio`, vê a cobertura e a
  lista, e **não** vê "Importar" nem "Desfazer".

---

## Phase 8: Polish & Cross-Cutting

- [X] T047 [P] `tests/integration/test_studio_permissoes.py` (SC-007): membro → 403 `somente_dono`;
  `system:*` e token de agente → 403 `somente_humano` mais o evento `publicacao_recusada` com
  `details.rota`, nas 3 rotas de escrita; as 2 de leitura aceitam membro.
- [X] T048 [P] `tests/unit/test_constitution_guards.py` (acréscimo):
  - `metricas/studio/` não importa `publicacao`, `httpx` nem `minio`;
  - não há `extract`/`extractall` nem `open(` de escrita em disco no pacote;
  - as rotas `POST` de `studio` dependem de `require_human_owner`;
  - não há "tiktok" nas rotas nem nos `operationId` `studio_*`;
  - `analytics/` continua sem escrita;
  - nenhum arquivo rastreado casa com `Overview_*_*.zip`/`Followers_*.zip`/`Content_*.zip`.
- [X] T049 [P] Teste de desempenho: a prévia e o confirmar de 366 dias em < 1 s; as abas da 019 com
  Studio (366 dias em 2 séries) mais 10× o volume continuam < 2 s (SC-003 da 019).
- [X] T050 `CLAUDE.md` (acréscimo): a seção "Histórico do Studio (desde a spec 020)", com o pacote, as
  rotas, a prévia no Redis, os arquivos nunca guardados, a regra do dia coberto, o `.gitignore` dos ZIPs e
  os sinônimos pt-BR provisórios. `docs/visao.md`: o item 020 no backlog.
- [X] T051 Verificação final:
  - `npm run test:api` inteiro, ruff, `npm run gen:contract && npm run check:web`;
  - a suíte e2e inteira (com trava);
  - percorrer o quickstart §1–§4 no dev.

  O §5 (arquivos reais) é **com o dono**, à mão; registrar o resultado. O §6 (exportação em pt-BR) fica
  como pendência anotada. **Commit só quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate) → T002.
- **Phase 2** bloqueia tudo:
  - T003 → T004/T005;
  - T006, T007, T008 e T010 em paralelo → T009;
  - T005 → T011 → T012;
  - T013 depois de T005.
- **US1 (Phase 3)** → **US2 (Phase 4):** as validações já existem nas funções puras; a US2 cobre a rota,
  as mensagens e a SPA. A US2 pode começar os testes junto com a US1.
- **US3 (Phase 5):** a T028 (referência sem Studio) **antes** de qualquer edição em `analytics/`. Depende
  da T011 e da gravação da US1 (T018) para semear. A T030 só fecha depois da T037 (US4).
- **US4 (Phase 6)** depois da US1. **US5 (Phase 7)** depois da US1; a T044 mexe em arquivos da 016
  (só acréscimo).
- O `gen:contract` é serializado (T020, T033, T037, T043). Os e2e são serializados pela trava.
- **Phase 8** no fim.

### Paralelismo sugerido (agentes)

- **Frente A (API, núcleo):** T003–T013 → T017–T019 → T037 → T043–T044.
- **Frente B (testes):** T009, T014–T016, T023–T025, T036, T040–T042, T047–T049.
- **Frente C (analytics):** T028 primeiro, depois T029–T034.
- **Frente D (SPA e e2e):** T021, T026, T038, T045 e e2e por história.

## Implementation Strategy

O MVP é a US1 mais a US2 (importar com segurança). Com a US3, o histórico aparece no analytics, que é o
valor para o dono. A US4 e a US5 completam. Checkpoints: depois da Phase 2, da US1+US2, da US3 (com a
regressão verde) e no fim.
