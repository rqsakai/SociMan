---

description: "Tarefas da feature 022-publico"
---

# Tasks: Público (022-publico)

**Input**: `specs/022-publico/`: a spec (com Clarifications), o plan, o research R1–R14, o data-model, o
contracts/http-api.md e o quickstart. A base é a 020 (`specs/020-historico-tiktok-studio/`).

**Pré-requisito:** a 020 (importação do Studio) e a 019 (analytics) estáveis e verdes. A 022 mexe em
`metricas/studio/*`, `analytics/quando_postar.py`, `analytics/schemas.py`, `analytics/router.py`,
`mcp/mapa.py`, `metricas/export.py` e `dicionario.py`, e nas telas do Studio e do analytics. Nenhum outro
agente pode estar editando esses arquivos ao mesmo tempo.

**Decisões do dono (2026-10-06):**
- **FR-012 = A:** a data da foto é o dia seguinte ao último dia do `FollowerHistory.csv` do mesmo ZIP,
  limitado a hoje; sem ele, vale o dia da importação, com aviso.
- **FR-016 = A:** vale a foto mais recente até o fim do período, mesmo que seja anterior ao início (com a
  data em destaque); a comparação é com a foto válida no fim do período anterior.
- **FR-017 = A:** o mapa de atividade faz a média sobre os dias com dado no período, com n por célula;
  sem nenhum dia, fica vazio com o atalho "ver os últimos dias com dado".

**Nomes canônicos:**
- **API:** pacote `sociman_api/metricas/studio/`, **só por acréscimo**:
  - módulos novos `planilha.py` e `publico.py`;
  - acréscimos em `formato`, `arquivos`, `datas`, `models`, `efetivo`, `previa`, `service`, `schemas` e
    `router` (só a descrição).
  - Tabelas novas: `metricas_studio_distribuicoes`, `metricas_studio_atividade` e
    `metricas_studio_espectadores`; colunas novas em `metricas_studio_importacoes`.
  - Migration **`0017_publico`** (`down_revision = "0016_importacao"`). A 023 vai usar a 0018 em cima
    desta.
  - Rota nova `GET /api/analytics/publico` (`analytics_publico`), em `analytics/publico.py`.
- **SPA:**
  - `pages/analytics/abas/Publico.tsx` e `components/analytics/Distribuicao.tsx`;
  - acréscimos em `lib/analytics.ts`, `Analytics.tsx`, `abas/QuandoPostar.tsx`, `components/studio/*` e
    `lib/studio.ts`.
- **Testes:**
  - `tests/integration/studio_helpers.py`, com o gerador de público e do XLSX **sintéticos**, conta
    `contateste`;
  - `e2e/publico.spec.ts`.

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec -T api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/publico.spec.ts]`.

Nada chama serviço real. **Os ZIPs e XLSX reais do dono nunca entram no repositório nem nos testes.**

**Arquivos compartilhados, SÓ ACRÉSCIMO:**
- `apps/api/src/sociman_api/main.py` (se precisar), `apps/api/src/sociman_api/mcp/mapa.py`,
  `apps/api/tests/unit/test_constitution_guards.py`;
- `e2e/helpers.ts`, `.gitignore`, `CLAUDE.md`, `docs/visao.md`.

O `packages/contract/**` é gerado.

**Segredos e privacidade:** nenhuma consulta ou log imprime nome de arquivo com @, handle, rótulo de
território ou conteúdo de arquivo real; só contagens.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US5 da spec

---

## Phase 1: Setup

- [X] T001 **Gate:**
  - `ls apps/api/migrations/versions/` mostra **0016_importacao** como a última e nenhum `0017_*` (se já
    houver, pare e avise o líder);
  - `docker compose exec api uv run alembic heads` mostra só `0016_importacao`;
  - os testes da 020 e da 019 estão verdes: `npm run test:api -- tests/ -k "studio or analytics" -q`;
  - `git status` só tem o esperado;
  - o `.specify/feature.json` aponta para a 022 (cuidado do líder; **não** mexer).
- [X] T002 [P] `.gitignore` (acréscimo): `Viewers.xlsx`, `FollowerGender.csv`, `FollowerTopTerritories.csv`
  e `FollowerActivity.csv`, na raiz e em `apps/`. Conferir com `git check-ignore -v` (os `Followers_*.zip`
  e `Viewers_*.zip` já estão lá desde a 020).

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** o banco, a leitura pura das seções novas (CSV e XLSX), o valor efetivo e o gerador
sintético.

- [X] T003 Migration `apps/api/migrations/versions/0017_publico.py` (`revision = "0017_publico"`,
  `down_revision = "0016_importacao"`), conforme o data-model:
  - as 7 colunas novas em `metricas_studio_importacoes` (`secoes_vazias` com default `'{}'`);
  - a troca de `ck_studio_imp_secoes` e os CHECKs novos (`_sha_publico`, `_foto`, `_vazias`);
  - os 4 índices parciais;
  - as 3 tabelas, com CHECKs, índices e triggers `metricas_studio_{dist,atv,esp}_so_insercao` (função
    `metricas_recusa_mudanca()` da 0011).

  O downgrade **recusa** se houver importação com seção de público; senão, desfaz na ordem inversa.
- [X] T004 [P] `apps/api/tests/integration/test_migration_0017.py`:
  - sobe sobre a 0016 com importações da 020 (ativas e desfeitas), que continuam válidas;
  - cada CHECK novo recusa com `INSERT` direto;
  - os 3 triggers recusam `UPDATE`/`DELETE`, e o `TRUNCATE` passa;
  - down/up sem público; downgrade com público recusado.
- [X] T005 `metricas/studio/models.py` (acréscimo):
  - `SECOES` ampliado, `SECOES_PUBLICO` e `DATA_FOTO_ORIGENS`;
  - as colunas novas da `Importacao`, com `__versioned_fields__` ampliado;
  - os modelos `FotoDistribuicao`, `AtividadeStudio` e `EspectadoresStudio` (sem `version`).
- [X] T006 [P] `metricas/studio/formato.py` (R1, acréscimo):
  - os sinônimos novos (pt-BR com `provisorio=True`);
  - as seções `genero`, `territorios`, `atividade` e `espectadores` pelo cabeçalho; elas saem de
    `OUTRAS_SECOES` (fica só o Conteúdo); `ORIENTACAO` com os 3 ZIPs;
  - `ler_linhas(arquivo, cabecalho, linhas)` extraída de `ler` (mesma assinatura e mesmo comportamento
    para a 020);
  - `undefined`/vazio → `None` só nas colunas numéricas de público; `Leitura.vazia` para o arquivo só com
    o cabeçalho (só nas seções de público);
  - `Problema.celula` opcional.
- [X] T007 [P] `metricas/studio/publico.py` (novo; R1, R4, R14), com funções puras:
  - o formato da % por arquivo (`%`, inteiro ou decimal com `.`/`,`, fração), sem mistura;
  - os rótulos de gênero (`Male`/`Female`/`Other` e sinônimos) → `masculino`/`feminino`/`outro`, com
    recusa do desconhecido; o território como veio (1–64 caracteres, sem repetir);
  - as somas: gênero a 100 ± `TOLERANCIA_GENERO`, territórios ≤ 100 + tolerância;
  - a hora (`5`, `05`, `5:00`, `05:00` → 0–23);
  - a chave (dia, hora) repetida, igual ou diferente;
  - a `data_foto(historico_dias, hoje)` (FR-012 A);
  - as constantes `TOLERANCIA_GENERO` e `FUSO_ATIVIDADE = None`;
  - `provisorios()` com os itens de R14.
- [X] T008 [P] `metricas/studio/planilha.py` (novo; R2): o XLSX → (cabeçalho, linhas, células), em
  memória:
  - os limites da 020, com subpastas relativas aceitas;
  - a recusa de `..`, absoluto, `\`, link, cifrado, `.zip`/`.xlsx` interno, `vbaProject.bin`/macro,
    `externalLinks`/`connections.xml`, `<!DOCTYPE`/`<!ENTITY`, `workbookProtection`/`sheetProtection` e
    `<f>`;
  - a aba `Viewers` (ou a única); as partes abertas só as do R2, cada uma com teto;
  - as células `str`, `s`, `inlineStr`, `n` e `b`, com a posição `r`;
  - o número de série do Excel na coluna de data.

  **Proibido** `extract`/`extractall`, `openpyxl` e `defusedxml`. Erros em `studio_planilha` e
  `studio_zip_inseguro`.
- [X] T009 [P] `metricas/studio/arquivos.py` (R3, acréscimo):
  - envio de 1 a 3 arquivos;
  - `ENTRADAS` com os 3 CSVs e o `Viewers.xlsx` (este via `planilha`, como único aninhado aceito);
  - o XLSX solto (assinatura ZIP com `[Content_Types].xml`) vai para a `planilha`; um `.xlsx` sem
    assinatura ZIP, ou OLE, vai para `studio_planilha`;
  - o SHA dos bytes de cada CSV e do XLSX.

  O `Content.csv` continua nunca aberto.
- [X] T010 [P] `metricas/studio/datas.py` (R4, acréscimo):
  - `nome_zip` reconhece `Viewers_<handle>.zip` como `espectadores` (sai de `_OUTRAS`);
  - `dias_distintos(datas)` na ordem da 1ª aparição, para a atividade;
  - a ordem de âncora do ano entre as seções (função usada pela prévia).
- [X] T011 [P] Testes unitários das funções puras (novos e acréscimos):
  - `tests/unit/test_studio_publico.py`:
    - % em cada formato e misturado;
    - gênero com soma 80/100/101,5 e territórios 100,1/99;
    - rótulo desconhecido e repetido;
    - hora 0/23/24/"05:00"/"x";
    - (dia, hora) repetido igual e diferente;
    - `data_foto` (último dia + 1, limitado a hoje, e o caso real 01/10 → 02/10);
    - `undefined` → `None`;
    - arquivo só com o cabeçalho → `vazia`.
  - `tests/unit/test_studio_formato.py` (acréscimo): os cabeçalhos reais das 4 seções; a 020 sem
    regressão (`undefined` em Visão geral continua erro).
  - `tests/unit/test_studio_datas.py` (acréscimo): a atividade ordenada por dia e por hora, com virada de
    ano; `Viewers_<handle>.zip` com " (1)".
- [X] T012 [P] `tests/unit/test_studio_planilha.py` (**XLSX malicioso**, R2):
  - o real sintético (`t="str"`, sem `sharedStrings`, `undefined`);
  - com `sharedStrings`, `inlineStr`, número e data por número de série;
  - abas `Viewers` + outra (a outra nunca aberta, com espião em `ZipFile.open`); duas abas sem `Viewers`;
  - recusas: fórmula (célula citada), `vbaProject.bin`, `externalLinks`, `sheetProtection`, `DOCTYPE`
    (*billion laughs*), `ENTITY`, razão > 100, 21 entradas, `../x`, link, cifrado, `.xls` OLE, XLSX
    dentro do XLSX;
  - `Viewers_x.zip` com o `Viewers.xlsx` dentro (aceito) e com um `Viewers.xlsx` que contém outro ZIP
    (recusado).
- [X] T013 **Ajustar os testes da 020 que codificam a recusa antiga** (o comportamento muda de propósito):
  - `tests/unit/test_studio_zip.py`: `ignorados` do ZIP de Seguidores sem os 3 CSVs; os casos
    `Viewers.xlsx` e `Viewers_conta.zip` saem de `test_secoes_nao_importadas` e viram casos de
    `test_studio_planilha.py`; o `planilha.xlsx` vai para `studio_planilha`;
  - `tests/unit/test_studio_formato.py`: o parâmetro `("Gender", "Distribution")` sai de
    `test_secao_nao_importada`;
  - `tests/integration/test_studio_validacao.py` (casos `Viewers*` e `planilha.xlsx`) e
    `test_studio_previa.py` (o `ignorados` de Seguidores e as seções vazias em `publico[]`);
  - `e2e/studio.spec.ts:99` (a prévia mostra "ainda sem dados de público" em vez de listar o
    `FollowerActivity.csv`).

  Anote no relatório da tarefa o motivo de cada ajuste (FR-003, FR-004); commit só quando o dono pedir.
- [X] T014 [P] `tests/integration/studio_helpers.py` (acréscimo):
  - o gerador **sintético** dos 3 CSVs de público preenchidos, no formato real (BOM, aspas, sem `\n`
    final);
  - um `Viewers.xlsx` montado em memória com `zipfile` (as mesmas partes do real, `t="str"`, `undefined`
    no 1º dia) e o `Viewers_<handle>.zip`;
  - as variantes: vazio (só o cabeçalho), pt-BR, fração, fórmula, macro, DOCTYPE, protegido, abas a mais e
    total ≠ novos + recorrentes;
  - na CLI, as opções `--publico`, `--publico-vazio` e `--defeito <nome>` (quickstart §2).
- [X] T015 `metricas/studio/efetivo.py` (R7, acréscimo; só leitura):
  - `fotos`, `foto_valida` (e a comparação), `atividade`, `ultimo_dia_atividade`, `espectadores` e
    `vazias`;
  - todas pelo `DISTINCT ON … criada_em, id` das importações ativas.
- [X] T016 [P] `tests/integration/test_studio_publico_efetivo.py`:
  - a ativa mais antiga vale por foto, por (dia, hora) e por dia;
  - uma desfeita não vale, e a próxima assume;
  - a foto inteira não mistura rótulos de importações diferentes;
  - a `foto_valida` dentro, antes e sem foto;
  - a comparação só com outra data;
  - a regra "veio vazia" (vazia mais nova que a última com dado).
- [X] T017 `metricas/studio/schemas.py` (acréscimo):
  - `SecaoPublicoPrevia` e `PreviaStudio.publico`;
  - `Secao` ampliado; `Importacao.dataFoto`, `dataFotoOrigem` e `secoesVazias`; `ContagensImportacao` com
    `semDado` e os padrões 0 (contrato);
  - `Cobertura.publico`;
  - os códigos de aviso novos;
  - os erros `studio_sem_dados` e `studio_planilha` (no catálogo de `errors.py`, se houver).

**Checkpoint:** a migration aplica, as funções puras (CSV, XLSX, %, datas) e o efetivo estão testados, os
testes da 020 estão ajustados e verdes, e o gerador sintético está pronto.

---

## Phase 3: User Story 1 - Importar o público junto com o histórico (Priority: P1) 🎯 MVP

**Goal:** o dono envia os ZIPs de Seguidores e de Espectadores, vê o público na prévia e confirma; tudo
é gravado numa importação só.

**Independent Test:** enviar os ZIPs sintéticos com público, conferir a distribuição, o pico e os totais
na prévia, confirmar e ver cada seção gravada com a fonte "Studio", a importação e o autor.

### Testes da US1

- [X] T018 [P] [US1] `tests/integration/test_studio_publico_previa.py`:
  - prévia com Seguidores (4 CSVs) e Espectadores: `publico[]` com a data da foto e a origem `historico`,
    a distribuição, o pico, as contagens, os totais (novos somados, médias) e `semDado`;
  - **nada gravado** (0 linhas nas 3 tabelas e na importação);
  - o estado no Redis com `publico` e `vazias`, TTL ≤ 1800;
  - **as vazias** (o real): `vazia: true` com a mensagem; um envio só de vazias → 400 `studio_sem_dados`;
  - um CSV de gênero solto: a origem `importacao` e o aviso `data_foto_importacao`;
  - o `periodo` raiz cobre os dias de público;
  - `podeConfirmar` com só uma seção de público nova.
- [X] T019 [P] [US1] `tests/integration/test_studio_publico_importacao.py`:
  - confirmar grava tudo ou nada (falha forçada no meio → 0 linhas em todas as tabelas);
  - `secoes`, SHAs, `data_foto`/`data_foto_origem`, `secoes_vazias`, `periodo`, `ano_origem` (incluindo o
    caso só com fotos) e `gravados` = total de linhas;
  - `history` versão 1 com `details.publico` **sem rótulo, nome de arquivo ou handle**;
  - **idempotência por seção** (mesmo SHA → 0 linhas e `gravados = 0`; re-zipar o mesmo XLSX →
    idempotente; uma seção repetida e outra nova → só a nova);
  - sobreposição diferente → `divergentes`, e o efetivo continua o anterior (foto da mesma data; atividade
    no mesmo dia e hora; espectadores no mesmo dia);
  - **as observações da 016 e os dias da 020 intactos** (hash antes e depois).
- [X] T020 [P] [US1] `tests/integration/test_studio_desfazer.py` (acréscimo): desfazer tira de uso
  **todas** as seções (020 e público) e as linhas continuam no banco; reimportar depois do desfazer grava
  de novo.

### Implementação da US1

- [X] T021 [US1] `metricas/studio/previa.py` (R5, R8, acréscimo):
  - a leitura das seções de público na ordem de âncora do R4;
  - `data_foto`;
  - as contagens contra o efetivo e a `situacao` das fotos;
  - os avisos novos (`data_foto_importacao`, `espectadores_soma`, `sem_dado`, `secao_vazia`) e os da 020
    nas seções diárias, sem o `diverge_da_coleta`;
  - `studio_sem_dados`;
  - o estado do Redis com `publico` e `vazias`;
  - `PreviaStudio.publico`.
- [X] T022 [US1] `metricas/studio/service.py::confirmar` (R8, acréscimo):
  - o `SHA` ampliado;
  - os INSERTs em lote nas 3 tabelas;
  - as colunas novas da importação, com o `ano_origem` das importações só com fotos;
  - `gravados` = linhas;
  - `history.record("created", details={secoes, gravados, vazias, publico})`.

  O lock e a `base` não mudam.
- [X] T023 [US1] `metricas/studio/router.py`: só a descrição do upload (de 1 a 3 arquivos `.zip`, `.csv`
  ou `.xlsx`). Nenhuma rota nova de escrita.
- [X] T024 [US1] `npm run gen:contract` e `lib/studio.ts` (os tipos novos).
- [X] T025 [US1] SPA:
  - `components/studio/EnvioArquivos.tsx`: até 3 arquivos, `accept` com `.xlsx`, o texto citando os 3 ZIPs;
  - `PreviaStudio.tsx`: os blocos de público (distribuição em tabela, pico, totais, "sem dado") e as vazias
    com a explicação de FR-006;
  - `ListaImportacoes.tsx`: as seções novas e as vazias.
- [X] T026 [US1] `e2e/publico.spec.ts` (US1): enviar os ZIPs sintéticos (com público e vazios), conferir
  a prévia, confirmar e ver a lista; reenviar → "já importado".

**Checkpoint:** a US1 funciona sozinha: o público entra no banco com segurança.

---

## Phase 4: User Story 2 - Conferir que os arquivos de público estão íntegros (Priority: P1)

**Goal:** cada defeito é recusado com a mensagem, o arquivo e a linha (ou célula) certos.

**Independent Test:** um arquivo sintético por defeito, cada um recusado e com nada gravado.

- [X] T027 [P] [US2] `tests/integration/test_studio_publico_validacao.py` (SC-004), na rota:
  - cada defeito de FR-008 (gênero com soma 80%, territórios 101%, % negativa, % mista, rótulo
    desconhecido, hora 24, (dia, hora) repetido diferente, "abc" em B4 do XLSX, data futura) → 400 com
    `problemas[]` e `celula` quando é planilha;
  - o XLSX com macro, fórmula, link, protegido, DOCTYPE ou sem a aba → `studio_planilha`;
  - o *bomb* e o `..` → `studio_zip_inseguro`;
  - `Viewers_outraconta.zip` → `studio_conta_diferente`;
  - `Viewers.xlsx` solto → `exigeConfirmacaoConta` e 400 `confirmar_conta` sem a marcação;
  - total ≠ novos + recorrentes → só o aviso `espectadores_soma`;
  - 4 arquivos → `studio_arquivos`;
  - em todos, 0 linhas gravadas.
- [X] T028 [US2] SPA `PreviaStudio.tsx`/`EnvioArquivos.tsx`: a lista de problemas mostra a célula
  ("B4") quando houver, e as mensagens de `studio_planilha` e `studio_sem_dados` em pt-BR.
- [X] T029 [US2] `e2e/publico.spec.ts` (US2): o XLSX com fórmula e o gênero com soma 80% mostram a recusa
  com a posição; nada aparece na lista.

---

## Phase 5: User Story 3 - Aba Público no analytics (Priority: P1)

**Goal:** a aba Público mostra gênero, territórios, atividade e espectadores com fonte, data da foto ou
dias cobertos, e amostra.

**Independent Test:** com fotos em duas datas, 14 dias de atividade e 14 de espectadores semeados,
conferir cada número da aba contra o cálculo de referência.

### Testes da US3 (escrever ANTES de mexer em `analytics/`)

- [X] T030 [P] [US3] `tests/integration/test_analytics_publico.py` (SC-006):
  - **a foto válida (FR-016 A):** dentro do período; anterior ao início com `anteriorAoPeriodo`; sem
    foto → `null` e o motivo; a comparação em p.p. com a foto válida no fim do período anterior; os
    rótulos `novo`/`saiu`; `outrosPct`; `seguidoresNaData`;
  - **o mapa (FR-017 A):** a média por célula com o n; `amostraPequena` com n = 1; os dias fora do período
    não entram; um período sem dado → células vazias, `ultimoDiaComDado` e o motivo
    `sem_dado_no_periodo`;
  - **os espectadores:** a série com `null`; os novos somados; as médias sobre os dias com valor; a
    variação contra o período anterior (e `null` sem base); `diasSemDado`;
  - **os motivos:** `sem_importacao`, `veio_vazia` e `sem_dado_no_periodo`;
  - **várias contas:** uma entrada por conta, na ordem de contas, sem misturar;
  - **a conta anonimizada:** "Conta anônima N" e `contaId = null`;
  - **o desfazer:** a resposta volta à de antes (SC-005);
  - membro pode ler.
- [X] T031 [P] [US3] A regressão das rotas da 019 e da 020: o snapshot das respostas de `visao_geral`,
  `quando_postar` (sem o campo novo), `contas` e `alertas` **antes** de editar `analytics/`, comparado
  depois, com e sem dados de público (a 022 não muda nenhum número que já existia).

### Implementação da US3

- [X] T032 [US3] `analytics/publico.py` (novo; R9): monta o `PublicoOut` a partir de `studio.efetivo`
  (só leitura), com:
  - `MIN_DIAS_CELULA = 2`;
  - o dia da semana pelo dia do arquivo, e a hora como veio (R13);
  - as contas pelo `Filtro` e pela `ordem_contas` da 019.
- [X] T033 [US3] `analytics/schemas.py` (`PublicoOut` e as partes) e `analytics/router.py` (`GET
  /analytics/publico`, `operation_id="analytics_publico"`, `RequireUser`, `FiltroDep`). A referência de
  conta reaproveita a da 019 (`ordem_contas` e o rótulo de conta anônima), sem tipo paralelo. Em `mcp/mapa.py`
  (acréscimo), `analytics_publico` como `Tool` de leitura, "Analytics: público", com a descrição em pt-BR.
  O `test_mcp_mapa.py` tem de passar sem mudança.
- [X] T034 [US3] `npm run gen:contract`. Em `lib/analytics.ts`: `"publico"` em `ABAS_ANALYTICS` depois de
  `"quando-postar"`, o `abaLabel` "Público" e o hook `usePublico`.
- [X] T035 [P] [US3] `components/analytics/Distribuicao.tsx`:
  - barras horizontais de um tom (a cor de magnitude da paleta da 019), com o rótulo e a % em texto, e a
    mudança em p.p. com ▲/▼ e texto;
  - a data da foto (com "anterior ao período" em destaque);
  - a tabela alternativa e o CSV (`fonte`, `data_foto`, `rotulo`, `pct`, `pct_comparacao`, `dif_pp`);
  - pequenos múltiplos por conta (com a cor da conta só no título);
  - o tooltip escapando o rótulo (ADR 0002).
- [X] T036 [US3] `pages/analytics/abas/Publico.tsx` + `Analytics.tsx`:
  - os 4 cards no `CardAnalytics` (título, como ler, tabela, CSV e amostra);
  - o mapa com o `MapaSemana` e a nota "horas conforme a TikTok · fonte: TikTok Studio", com o seletor
    local de conta quando há mais de uma;
  - espectadores: linhas por conta com cores fixas e buraco no "sem dado", barras empilhadas novos ×
    recorrentes, e os 3 indicadores;
  - os estados vazios por motivo, com o atalho para "Histórico do Studio" (só dono) e o atalho "ver os
    últimos dias com dado" (`setPeriodo`);
  - no celular, uma coluna, e o mapa rola só dentro do card.
- [X] T037 [US3] `e2e/publico.spec.ts` (US3):
  - a aba na URL (`?aba=publico`);
  - os 4 cards com a fonte e a data;
  - "Ver tabela" e o CSV;
  - o atalho de período;
  - os estados vazios do real (vazias);
  - a 390 px sem rolagem horizontal da página (SC-007);
  - a regra de paleta: o validador da 019 nos tokens usados, em claro e escuro.

---

## Phase 6: User Story 4 - Atividade dos seguidores em "Quando postar" (Priority: P2)

- [X] T038 [P] [US4] `tests/integration/test_analytics_quando_postar.py` (acréscimo):
  `atividadeSeguidores` igual ao mapa de `analytics_publico` no mesmo filtro e período; sem dado → o
  motivo; os outros dois mapas idênticos ao snapshot da T031.
- [X] T039 [US4] `analytics/quando_postar.py` + `schemas.py`: o `QuandoPostarOut.atividadeSeguidores`
  (aditivo), reaproveitando a função do mapa da T032. Depois, `npm run gen:contract`.
- [X] T040 [US4] `pages/analytics/abas/QuandoPostar.tsx`: o 3º `MapaSemana`, "Seguidores on-line (TikTok
  Studio)", com a nota de fonte, fuso e amostra, o seletor local de conta e o estado vazio com os atalhos.
- [X] T041 [US4] `e2e/publico.spec.ts` (US4): o 3º mapa com dado e vazio; os dois mapas da 019 sem
  mudança.

---

## Phase 7: User Story 5 - Cobertura e exportação (Priority: P3)

- [X] T042 [P] [US5] `tests/integration/test_studio_cobertura.py` (acréscimo): as fotos (datas), as faixas
  e os buracos de atividade e espectadores, e as `vazias`; o desfeito sai.
- [X] T043 [US5] `metricas/studio/service.py::cobertura` (acréscimo): `Cobertura.publico` (R10).
- [X] T044 [P] [US5] `tests/integration/test_studio_publico_export.py`: os 3 CSVs (e `.jsonl`), só das
  ativas, com `importacao_id` e `efetivo`; o filtro de período por `dia`/`data_foto`; o `dicionario.csv`
  na versão 3, com as colunas novas no fim; o `studio_dias.csv` da 020 idêntico.
- [X] T045 [US5] `metricas/export.py` + `dicionario.py` (acréscimo): os 3 arquivos e
  `DICIONARIO_VERSAO = 3`.
- [X] T046 [P] [US5] `tests/integration/test_studio_publico_anonimizar.py` (FR-019, R11): depois de
  `anonimizar.serie`, as 3 tabelas ficam intactas, sem nenhum texto com o @ (busca pelo handle em todas as
  colunas de texto), `nomes_arquivos = NULL`, e a aba Público mostra "Conta anônima N".
- [X] T047 [US5] SPA `components/studio/CoberturaBarras.tsx`: as fotos como marcos (data), as faixas de
  atividade e de espectadores, os buracos e "veio sem dados em <data>".

---

## Phase 8: Polish & Cross-Cutting

- [X] T048 [P] `tests/integration/test_studio_permissoes.py` (acréscimo; SC-008):
  - membro → 403 `somente_dono`, e `system:*`/token de agente → 403 `somente_humano` mais o evento
    `publicacao_recusada`, com envios de XLSX e de público nas 3 rotas H;
  - `analytics_publico` e a cobertura aceitam membro.
- [X] T049 [P] `tests/unit/test_constitution_guards.py` (acréscimo):
  - `planilha.py` e `publico.py` não importam `publicacao`, `httpx`, `minio`, `openpyxl` nem `defusedxml`;
  - não há `extract`/`extractall` nem `open(` de escrita no pacote;
  - a `planilha.py` recusa `<!DOCTYPE`/`<!ENTITY` antes de chamar o parser (teste com o payload);
  - a rota `analytics_publico` não tem "tiktok" no caminho nem no `operationId`, e `analytics/` continua
    sem escrita;
  - nenhum arquivo rastreado casa com `Viewers*.xlsx` nem com os 3 CSVs de público.
- [X] T050 [P] Teste de desempenho (no `test_studio_desempenho.py`, acréscimo):
  - a prévia e o confirmar de 366 dias de espectadores + 366 × 24 de atividade em < 1 s;
  - `analytics_publico` e `quando_postar` com 2 séries de 1 ano, mais 10× o volume, em < 2 s.
- [X] T051 `CLAUDE.md` (acréscimo): a seção "Público (desde a spec 022)", com:
  - as seções novas e o XLSX lido pela stdlib, com as recusas;
  - as vazias (~100 seguidores) e o "sem dado";
  - a data da foto, e as fotos datadas (não diárias);
  - a aba Público e o 3º mapa;
  - a hora da atividade "como veio";
  - os provisórios.

  Em `docs/visao.md`, o item 022 no backlog.
- [X] T052 Verificação final:
  - `npm run test:api` inteiro, ruff, `npm run gen:contract && npm run check:web`;
  - a suíte e2e inteira (com trava);
  - percorrer o quickstart §1–§4 no dev.

  O §5 (arquivos reais) é **com o dono**, à mão: registre o resultado e o tempo do envio à confirmação
  (SC-001, < 2 min). O §6 fica como pendência anotada.
  **Commit só quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate) → T002.
- **Phase 2** bloqueia tudo:
  - T003 → T004 e T005;
  - T006, T007, T008, T009, T010 e T014 em paralelo → T011, T012 e T013;
  - T005 → T015 → T016;
  - T017 depois de T005.
- **US1 (Phase 3)** depois da Phase 2; os testes T018–T020 podem ser escritos junto com a T021.
- **US2 (Phase 4):** as validações estão nas funções puras; a US2 cobre a rota, as mensagens e a SPA, e
  pode começar junto com a US1.
- **US3 (Phase 5):** a T031 (snapshot) vem **antes** de qualquer edição em `analytics/`. Depende da T015 e
  da gravação da US1 (T022) para semear.
- **US4 (Phase 6)** depois da T032. **US5 (Phase 7)** depois da US1.
- O `gen:contract` é serializado (T024, T034, T039). Os e2e são serializados pela trava.
- **Phase 8** no fim.

### Paralelismo sugerido (agentes)

- **Frente A (API, leitura):** T006–T010 → T021–T023.
- **Frente B (banco e núcleo):** T003, T005, T015, T017 → T022 → T043, T045.
- **Frente C (testes):** T004, T011–T014, T016, T018–T020, T027, T030–T031, T038, T042, T044, T046, T048–T050.
- **Frente D (analytics):** T031 primeiro, depois T032–T033 e T039.
- **Frente E (SPA e e2e):** T025, T028, T034–T037, T040, T047 e os e2e por história.

## Implementation Strategy

O MVP é a US1 mais a US2 (importar o público com segurança). Com a US3, o público aparece no analytics,
que é o valor para o dono. A US4 e a US5 completam. Checkpoints: depois da Phase 2 (com os testes da 020
ajustados e verdes), da US1+US2, da US3 (com a regressão verde) e no fim.
