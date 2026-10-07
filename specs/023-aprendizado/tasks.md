---

description: "Tarefas da feature 023-aprendizado"
---

# Tasks: Aprender com o desempenho (023-aprendizado)

**Input:** `specs/023-aprendizado/`, com:
- a spec, com as Clarifications de 2026-10-06;
- o plan;
- a research R1–R15;
- o data-model;
- o `contracts/http-api.md`;
- o quickstart.

**Pré-requisitos:**
- a 019 (analytics) e a 017 (guia) estáveis e verdes;
- a 022 já com a migration `0017_publico` aplicada.

A 023 mexe em `ia/prompt.py`, `ia/saida.py`, `ia/cliente.py`, `canais/service_videos.py`,
`analytics/mercado.py` e `metricas/anonimizar.py`. Nenhum outro agente pode estar editando esses arquivos
ao mesmo tempo.

**Decisões do dono (2026-10-06):**
- **Q1 (FR-031) = B:** quadros opcionais por análise, 4 por vídeo, só dos N melhores e dos comparáveis,
  com estimativa antes de confirmar.
- **Q2 (FR-040) = B:** os temas cortados ficam escondidos por padrão, com o contador "N ocultos por tema
  cortado" e o filtro "mostrar temas cortados".
- **Q3 (FR-051) = C:**
  - a estatística é calculada na leitura;
  - a trilha `aprendizado` classifica os posts novos, com limite de 50 por perfil por dia;
  - a análise da IA só sob demanda.

**Nomes canônicos:**
- **API:** pacote `sociman_api/aprendizado/`, com `constantes`, `estatistica`, `fatores`, `analise`,
  `recomendacoes`, `preferencias`, `temas`, `classificacao`, `analise_ia`, `quadros`, `afinidade`,
  `desempenho`, `diagnostico`, `conferencias`, `trilha`, `models`, `schemas` e `router`.
- **Rotas e `operationId`:** os de `contracts/http-api.md` (`aprendizado_*`).
- **Tabelas:**
  - `aprendizado_temas`;
  - `aprendizado_classificacoes`;
  - `aprendizado_preferencias`;
  - `aprendizado_analises`;
  - `aprendizado_decisoes`;
  - `aprendizado_conferencias`;
  - mais 3 colunas em `ia_chamadas`.
- **Migration:** **`0018_aprendizado`** (`down_revision = "0017_publico"`).
- **Autor automático:** `Actor(kind="system:aprendizado")`.
- **Tipos de IA:** `aprendizado.taxonomia`, `aprendizado.classificacao` e `aprendizado.analise`.
  `PROMPT_VERSION = "ia/3"`.
- **Trilha:** `aprendizado` (`AGENDADOR_APRENDIZADO_S`, padrão 300).
- **SPA:**
  - `pages/aprendizado/Aprendizado.tsx` (lazy, `/app/perfis/:id/aprendizado?aba=…`);
  - `pages/aprendizado/abas/*`, `components/aprendizado/*` e `lib/aprendizado.ts`.
- **Testes:**
  - `tests/integration/aprendizado_helpers.py` (semeadura);
  - `e2e/aprendizado.spec.ts`;
  - os fakes do Claude em `tests/fakes/anthropic_fake.py` e `e2e/fakes/server.py`.

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec -T api uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/aprendizado.spec.ts]`.

Nada chama serviço real.

**Arquivos compartilhados, SÓ ACRÉSCIMO:**
- `apps/api/src/sociman_api/main.py`, `agendador.py` e `config.py`;
- `mcp/mapa.py`;
- `apps/web/src/App.tsx`;
- `apps/api/tests/unit/test_constitution_guards.py`;
- `e2e/helpers.ts` e `e2e/fakes/server.py`;
- `CLAUDE.md` e `docs/visao.md`.

`packages/contract/**` é gerado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US6 da spec

---

## Phase 1: Setup

- [X] T001 **Gate:**
  - `ls apps/api/migrations/versions/` mostra **`0017_publico`** como a última e nenhum `0018_*`. Se a 0017
    não existir ou já houver uma 0018, pare e avise o líder;
  - `docker compose exec api uv run alembic heads` mostra só `0017_publico`;
  - os testes da 019, da 017 e da 008 estão verdes:
    `npm run test:api -- tests/ -k "analytics or guia or ia_" -q`;
  - `git status` só tem o esperado;
  - `.specify/feature.json` aponta para a 023 (o líder cuida).
- [X] T002 [P] `apps/api/src/sociman_api/config.py` (acréscimo): `agendador_aprendizado_s: float = 300`.
  No `docker-compose.yml`, só no `agendador`: `AGENDADOR_APRENDIZADO_S: ${AGENDADOR_APRENDIZADO_S:-300}`.
  No `docker-compose.e2e.yml`: `AGENDADOR_APRENDIZADO_S=2`, para o e2e ver a trilha rodar.

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** banco, modelos, estatística pura, tipos de IA e fakes.

- [X] T003 Migration `apps/api/migrations/versions/0018_aprendizado.py` (`revision = "0018_aprendizado"`,
  `down_revision = "0017_publico"`), conforme o data-model:
  - os 5 enums e as 6 tabelas, com todos os CHECKs, os índices únicos parciais e os índices;
  - as 3 colunas de `ia_chamadas`;
  - o downgrade na ordem inversa.
- [X] T004 [P] `apps/api/tests/integration/test_migration_0018.py`:
  - sobe sobre a 0017 com chamadas da 008 existentes, que ficam com as colunas novas NULL / `'{}'`;
  - cada CHECK e índice único recusa com `INSERT` direto;
  - down e up.
- [X] T005 `aprendizado/models.py`:
  - `Tema`, `Classificacao`, `Preferencias`, `Decisao` e `Conferencia` (`_Versioned` e `AuditMixin`,
    com os `__versioned_fields__` do data-model);
  - `Analise` (com `version`, sem edição).

  Registrar no metadata e no `env.py`, se necessário. Em `ia/models.py` (acréscimo): as 3 colunas novas.
- [X] T006 [P] `aprendizado/constantes.py`: `MIN_GRUPO = 5`, `MIN_DIAS = 2`, `MIN_CONTA = 15`,
  `K_ENCOLHIMENTO = 5`, `MEIA_VIDA_DIAS = 30`, `JANELA_DIAS = 180`, `REAMOSTRAS = 400`,
  `CONCENTRACAO = 0.5`, `MIN_SEPARAVEL = 3`, `CONFUSAO = 0.8`, `TRAVADA = 0.6`, os limites das regras de
  FR-035, `PESO_AFINIDADE = 20`, `LIMITE_DIARIO = 50`, `IDADE_CLASSIFICAR = 24 h`, `MAX_TEMAS = 30` e as
  faixas de gancho e de duração. Cada uma com comentário de origem (FR/R).
- [X] T007 [P] `aprendizado/estatistica.py` (R1, R2; funções puras, sem I/O):
  - `medida_log`, `peso(idade_dias)`;
  - `efeito_entrega` e `efeito_rendimento` (encolhidos);
  - `intervalo(grupo, semente)` (reamostragem, percentis 10–90);
  - `confianca(...)`, `concentracao(...)` e `sem_maior(...)`.
- [X] T008 [P] `tests/unit/test_aprendizado_estatistica.py`, com casos de referência calculados à mão:
  - 3 posts com 1 viral (o encolhimento cai a 3/8 e aparece "puxado por 1");
  - grupo 0/1 com mediana geral 0 (sem infinito);
  - o peso de 30 dias = 0,5;
  - a mesma semente dá o mesmo intervalo;
  - as faixas de confiança nas bordas (n = 4, 5, 9, 10).
- [X] T009 `aprendizado/fatores.py` (R1): de `analytics.base.PostAnalisado` (019) e da `Classificacao` para
  a lista de `(fator, valor, rotulo)` por post. Também identifica o estagnado por
  `analytics.alertas.desempenho`. Reaproveita `analytics.base.hashtags` e `ia.guia.normalizar`.
- [X] T010 [P] `ia/tipos.py` e `ia/regras_padrao.py` (acréscimo, R5): os 3 `TipoCampo`
  (`aprendizado.taxonomia`, `.classificacao` e `.analise`), com regra padrão e limites. Em
  `tests/unit/test_ia_tipos.py`: os 3 aparecem, com a regra padrão editável.
- [X] T011 [P] `ia/saida.py` (acréscimo): os schemas Pydantic das 3 saídas (taxonomia, classificação e
  análise) e as funções de ajuste com os limites de R5. A recusa de id fora da lista fica no serviço
  (T018, T031).
- [X] T012 [P] `ia/cliente.py`: `_chamar` aceita `user: str | list[dict]` (blocos `text` e `image` base64
  `image/jpeg`), sem mudar o resto. Em `tests/unit/test_ia_cliente.py`: o corpo com imagem e a guarda de
  `tools` continua.
- [X] T013 [P] Fakes do Claude:
  - `tests/fakes/anthropic_fake.py` e `e2e/fakes/server.py` respondem os 3 schemas de forma
    determinística (R15);
  - a instrução "id inválido" devolve um id fora do conjunto;
  - o fake registra se houve blocos `image`.
- [X] T014 [P] `tests/integration/aprendizado_helpers.py`: `semear_aprendizado(...)`, que reaproveita
  `metricas_helpers.semear` e gera:
  - 2 contas e 30 posts com temas e ganchos;
  - hashtags que coocorrem com um tema;
  - 1 viral, 1 conta travada e 1 repostagem (o mesmo `video_fonte_id` em 2 contas);
  - vídeos-fonte com palavras-chave.
- [X] T015 `aprendizado/schemas.py` (camelCase): Tema, Classificacao, Efeito, Analise, Recomendacao,
  Decisao, Preferencias, AnaliseIa, Sinal, Conferencia e Afinidade, conforme o contrato.

**Checkpoint:** migração verde, estatística pura testada e fakes prontos.

---

## Phase 3: User Story 1 - Temas e classificação (Priority: P1) 🎯 MVP

**Goal:** taxonomia editável pelo dono, proposta pela IA, classificação automática com limite e correção
que prevalece.

**Independent Test:** spec US1 (quickstart §2).

- [X] T016 [US1] `aprendizado/temas.py`:
  - criar, lote, editar, arquivar, restaurar, juntar e revert, com `history`;
  - incremento de `preferencias.taxonomia_versao` na mesma transação;
  - máximo de 30 temas e nome único normalizado;
  - juntar e arquivar movem as classificações (data-model, "Regras de transição").
- [X] T017 [US1] `aprendizado/classificacao.py` (parte dono):
  - `pendentes(db, perfil)` (data-model);
  - `corrigir` (PUT, `origem = dono`) e `revert`;
  - a regra "`origem = dono` nunca é sobrescrita pela IA" (função única, usada pela trilha).
- [X] T018 [US1] `aprendizado/classificacao.py` (parte IA):
  - `montar_entrada(post)`: legenda, hashtags, gancho e transcrição ≤ 4.000, com `evidencia_parcial` sem
    corte;
  - `classificar_um(db, client, video)` grava a `ia_chamadas` pelo mesmo caminho do `ia.service`
    (`_preencher`, custo e desfecho `sem_acao`; uma função irmã de `executar` se o alvo não couber em
    `AlvoResolvido`);
  - recusa de tema fora da taxonomia → `tema_id NULL` mais `sugestao_tema`;
  - autor `system:aprendizado`.
- [X] T019 [US1] `aprendizado/trilha.py` (classificação):
  - `rodar(db)` percorre os perfis com taxonomia e `classificacao_auto` (ou com `pedido_classificacao_em`);
  - classifica os pendentes até `LIMITE_DIARIO` por perfil por dia local (conta as `ia_chamadas` de
    `aprendizado.classificacao` do dia, inclusive erros);
  - para no 1º erro 503/504 da IA na volta.

  Em `agendador.py` (acréscimo): `Trilha("aprendizado", s.agendador_aprendizado_s, trilha.rodar,
  _sem_ia)`, ociosa sem `ANTHROPIC_API_KEY`. A guarda `test_agendador_sem_trilha_nova` é **atualizada**
  para incluir `aprendizado` (acréscimo justificado no plan, Complexity Tracking).
- [X] T020 [US1] A proposta de taxonomia: `aprendizado_taxonomia_propor`, síncrona como o `guia.montar`.
  Usa até 40 posts recentes e não salva nada.
- [X] T021 [US1] `aprendizado/router.py` (temas, taxonomia e classificações) mais o `include_router` em
  `main.py`. As escritas usam `RequireHumanOwner` e as leituras `RequireUser`. Depois, `npm run
  gen:contract`.
- [X] T022 [P] [US1] `tests/integration/test_aprendizado_temas.py`:
  - CRUD, nome repetido sem acento, 31º tema;
  - juntar e reverter (as classificações vão e voltam), arquivar (`reclassificar`);
  - `taxonomia_versao` sobe;
  - membro só lê.
- [X] T023 [P] [US1] `tests/integration/test_aprendizado_classificacao.py` e `test_aprendizado_trilha.py`:
  - pendentes (idade < 24 h fica fora);
  - limite de 50 por dia, contando erros;
  - a correção do dono prevalece sobre a IA;
  - id inválido do fake → "Sem tema" mais sugestão;
  - vídeo sem corte com evidência parcial;
  - `classificacao_auto = false` → nada roda;
  - trilha ociosa sem chave;
  - autor `system:aprendizado` no histórico.
- [X] T024 [US1] SPA:
  - `pages/aprendizado/Aprendizado.tsx` (rota lazy em `App.tsx`, abas na URL);
  - `abas/Temas.tsx` (lista, proposta da IA com "Salvar", juntar e arquivar com AlertDialog, histórico);
  - lista de classificações com `ClassificacaoEditor` (`NativeSelect`), filtro por tema e pendentes, e o
    contador "usadas hoje";
  - `lib/aprendizado.ts`;
  - links na página do perfil e no detalhe do vídeo (016).
- [X] T025 [US1] `e2e/aprendizado.spec.ts` (US1): propor → salvar → classificar pendentes (a trilha roda na
  stack e2e com intervalo curto) → corrigir → juntar e reverter. O membro não vê botões.

**Checkpoint:** US1 entregue (MVP).

---

## Phase 4: User Story 2 - Por que deu certo (Priority: P1)

**Goal:** análise estatística robusta na leitura e análise da IA dos melhores, assíncrona, com quadros
opcionais.

**Independent Test:** spec US2 (quickstart §3 e §4).

- [X] T026 [US2] `aprendizado/analise.py` (R1–R4):
  - `calcular(db, filtro, medida)` monta os posts pela 019 (`analytics.base.posts`), aplica pesos e janela,
    e calcula os efeitos das 2 partes por fator;
  - amostra mínima, concentração, blocos de hashtags e matriz hashtag × tema;
  - separabilidade dentro do tema, "quase só com", travada, em alta e em queda;
  - o contador de comparações.

  Só leitura.
- [X] T027 [P] [US2] `tests/unit/test_aprendizado_analise.py` (SC-003), sobre posts semeados em memória:
  - o bloco #a + #b + #c sempre juntas;
  - a hashtag só no tema → `nao_separavel`;
  - tema × horário → `quase_so_com`;
  - conta com 70% estagnados → `travada`;
  - em alta e em queda;
  - post sem vínculo fora dos fatores de corte.
- [X] T028 [US2] Rotas `aprendizado_analise` (U) e `npm run gen:contract`. Em
  `tests/integration/test_aprendizado_analise_api.py`:
  - o GET não grava (conta `entity_versions` e linhas antes e depois);
  - os filtros conta, medida e período;
  - "aguardando".
- [X] T029 [US2] `aprendizado/quadros.py` (R5):
  - `datadir.ensure_writable()` e a pasta `work/tmp/aprendizado/<analise>/`;
  - `storage.get_to_file` do arquivo do corte ou do vídeo próprio;
  - `cortes.compose.extract_frame` em 4 tempos, reduzidos a 512 px JPEG q = 80 com Pillow;
  - limpeza no `finally`;
  - erro `hd_indisponivel` sem o marcador.
- [X] T030 [US2] `aprendizado/analise_ia.py`:
  - `escolher(db, perfil, conta, n, medida)`: melhores e comparáveis (R5), sem anônimas;
  - `estimar(...)`: com e sem quadros, por `ia/custo.py`;
  - `pedir(...)`: 409 `confirmar_custo` sem confirmação e 409 `analise_em_andamento`; grava `pendente`.
- [X] T031 [US2] `aprendizado/analise_ia.py` (execução) mais `trilha.py`:
  - a trilha pega 1 pedido com `SKIP LOCKED` **antes** da classificação;
  - monta a entrada (posts em `<post id>` como dados e resumo estatístico), com os quadros se pedidos;
  - chama o `ia.service` (registro e custo);
  - valida as hipóteses (ids no conjunto, limites) e grava `pronta` ou `erro`;
  - um `processando` com mais de 15 min volta a `pendente` 1 vez.
- [X] T032 [US2] Rotas de análises da IA (estimativa, create, list, get e `hipotese_recomendar`, este só a
  rota aqui; a regra fica na T039) e `npm run gen:contract`.
- [X] T033 [P] [US2] `tests/integration/test_aprendizado_analise_ia.py`:
  - estimativa sem chamada;
  - `confirmar_custo`;
  - execução sem quadros e com quadros (MP4 sintético `ffmpeg -f lavfi`; o fake recebeu 4 × vídeos blocos
    `image`);
  - vídeo sem arquivo contado;
  - HD fora → `hd_indisponivel`;
  - hipótese com id inválido recusada;
  - a pasta temporária vazia no fim;
  - membro vê `custo = null` e não pode pedir.
- [X] T034 [US2] SPA:
  - `abas/Analise.tsx`: `GraficoEfeitos` (Bar transparente com Scatter), `EfeitoLinha` com avisos e n,
    `MatrizHashtagTema` (Heatmap), aviso de travada com link para o Diagnóstico, nota "exploratório"; a
    tabela alternativa, o CSV e a leitura (FR-005 e FR-006 da 019);
  - `abas/AnalisesIa.tsx`: `PedidoAnalise` com estimativa, "Confirmar custo" e polling de 5 s, e as
    hipóteses com links e "a conferir".
- [X] T035 [US2] `e2e/aprendizado.spec.ts` (US2): a análise com o bloco e o "não separável" sobre dados
  semeados; o pedido de análise sem quadros até `pronta`, e as hipóteses visíveis.

---

## Phase 5: User Story 3 - Recomendações com decisão do dono (Priority: P1)

**Goal:** regras na leitura, decisão gravada, preferências versionadas, "fixar" no guia.

**Independent Test:** spec US3 (quickstart §5.1).

- [X] T036 [US3] `aprendizado/recomendacoes.py` (R6):
  - as regras de FR-035 sobre os efeitos;
  - chave estável;
  - filtro das decididas (aceita vigente some; rejeitada só volta com n ≥ 2× ou mudança de faixa);
  - "superada" calculada;
  - bloqueios (`fixas_no_maximo`, conta travada e não separável não geram).
- [X] T037 [P] [US3] `tests/unit/test_aprendizado_recomendacoes.py` (SC-004): nenhuma recomendação com
  amostra pequena, com não separável, puxada por 1 sem efeito restante, ou com conta travada; e a regra de
  reaparecer.
- [X] T038 [US3] `aprendizado/preferencias.py` (R7):
  - `efetivas(perfil, conta)`;
  - PATCH, versions e revert;
  - `aceitar(chave)`:
    - recalcula, e responde 409 `recomendacao_mudou`;
    - grava a decisão e a nova versão das preferências;
    - `hashtag_fixar` → `ia.service_guia` com `details.origem = "recomendacao_023"`, 409
      `fixas_no_maximo` com `substituir` e 400 `ia_proibida`;
  - `rejeitar(chave, motivo)`;
  - revert da decisão.
- [X] T039 [US3] As decisões de hipótese: `hipotese_recomendar` cria uma `Decisao` `aberta` com
  `origem = hipotese` (só `padrao_*`), que entra no `decidir`.
- [X] T040 [US3] Rotas `aprendizado_recomendacoes`, `_decidir`, `aprendizado_decisoes_revert` e
  `aprendizado_preferencias_*`, e `npm run gen:contract`.
- [X] T041 [P] [US3] `tests/integration/test_aprendizado_recomendacoes_api.py` e
  `test_aprendizado_preferencias.py`:
  - aceitar ampliar, cortar e fixar (a hashtag aparece no guia da conta, com o histórico do guia);
  - fixar no máximo, com e sem `substituir`;
  - fixar uma proibida;
  - rejeitar com motivo, e o reaparecer;
  - revert;
  - `recomendacao_mudou`;
  - a janela de horário não toca em nenhum destino (contagem de `postagens` e de versões antes e depois).
- [X] T042 [US3] SPA:
  - `abas/Recomendacoes.tsx`: `CartaoRecomendacao` (motivo, evidência, "o que muda", aceitar e rejeitar
    com AlertDialog e motivo, escolher a fixa a substituir), a lista das decididas com revert;
  - a dica "Janela preferida" no agendamento do destino (só leitura).
- [X] T043 [US3] `e2e/aprendizado.spec.ts` (US3): aceitar fixar → o guia da conta mostra a hashtag; rejeitar
  → some; revert.

---

## Phase 6: User Story 4 - Buscador e gerador (Priority: P2)

**Goal:** afinidade no Descobrir e no Mercado, temas cortados ocultos, bloco `<desempenho>` no assistente.

**Independent Test:** spec US4 (quickstart §5.2–§5.4).

- [X] T044 [US4] `aprendizado/afinidade.py` (R9):
  - `valores(db, perfil)`: a_t e a_c a partir da análise e das preferências;
  - `expressao_sql(valores, coluna_titulo, coluna_descricao)`, com `translate` + regex `\m…\M` e
    palavras-chave escapadas;
  - `filtro_cortados(...)`.
- [X] T045 [P] [US4] `tests/integration/test_aprendizado_afinidade_norm.py`: a paridade `translate` (SQL) ×
  `ia.guia.normalizar` em todas as letras acentuadas pt-BR e es (roda contra o PG da stack de teste), o
  escape de regex e palavras de 2 letras.
- [X] T046 [US4] `canais/service_videos.py` e `canais/schemas.py` (acréscimo):
  - com `perfilId`, a ordem e o cursor usam `score_exibido + afinidade`;
  - `mostrarCortados`, `ocultosPorTema` e `afinidade` por item;
  - o motivo com tema quando é o principal;
  - sem `perfilId`, nada muda.

  `analytics/mercado.py`: o mesmo nas oportunidades, com import tardio de `aprendizado.afinidade` (sem
  ciclo com `analytics.base`). Depois, `npm run gen:contract`.
- [X] T047 [P] [US4] `tests/integration/test_aprendizado_descobrir.py` (SC-008):
  - afinidade neutra → ordem idêntica à da 006 (fotografia da ordem antes);
  - tema ampliado sobe;
  - cortado oculto, com o contador e o filtro;
  - a paginação por cursor estável;
  - **o `enviar` de vídeo `sem_acordo` com afinidade alta continua 409 `aviso_direito`**, e `direito` não
    muda;
  - as oportunidades do Mercado.
- [X] T048 [US4] `aprendizado/desempenho.py` (R8): `bloco(db, perfil, conta)` → preferências efetivas, até
  3 exemplos por regra fixa (sem anônimas nem travadas, sem proibidas, 90 dias) e versões. Em
  `ia/prompt.py`:
  - `PROMPT_VERSION = "ia/3"`;
  - `<desempenho>` depois de `<guia_conta>` e antes de `<perfil>`, só nos `postagem.*` e no `guia.testar`
    com `usar_desempenho`;
  - a linha nova na base.

  Em `ia/service.py`: grava `desempenho_*_version` e `desempenho_exemplos`. Em `ia/saida.py`:
  `_sem_evitadas` depois de `_com_fixas`, com o aviso em `ajustes`.
- [X] T049 [P] [US4] `tests/unit/test_ia_prompt.py` (acréscimo) e `test_aprendizado_desempenho.py`:
  - a ordem dos blocos e o `cache_control` só no último;
  - a escolha dos exemplos (desempate, exclusões);
  - sem preferências e sem exemplos → sem bloco.
- [X] T050 [P] [US4] `tests/integration/test_aprendizado_gerador.py` (SC-007): 10 gerações com bloco →
  100% com as fixas, 0 "evitar", 0 proibida aplicável sem edição, as versões no registro, e
  `usar_desempenho = false` → NULL. Os testes da 017 continuam verdes (`-k guia`).
- [X] T051 [US4] SPA:
  - Descobrir: o selo "tema cortado", o contador, o interruptor "mostrar temas cortados" (na URL) e o
    motivo;
  - Mercado: o mesmo nas oportunidades;
  - registro do assistente: "Desempenho: perfil vN, conta vM, K exemplos" ou "sem bloco".
- [X] T052 [US4] e2e: em `e2e/cortes-openshorts.spec.ts` (Descobrir), o tema cortado oculto e o filtro; em
  `e2e/assistente-ia.spec.ts`, a versão do desempenho no registro.

---

## Phase 7: User Story 5 - Diagnóstico de distribuição (Priority: P2)

**Goal:** sinais com número, checklist e conferências do dono.

**Independent Test:** spec US5 (quickstart §3.2).

- [X] T053 [US5] `aprendizado/diagnostico.py` (R10): os sinais por conta e por post e o `CHECKLIST` fixo;
  reaproveita o mapa da audiência da 019 (`analytics.quando_postar`) e `contas.intervalo_min_minutos`.
  `aprendizado/conferencias.py`: PUT com `history`.
- [X] T054 [US5] As rotas `aprendizado_diagnostico`, `_post_diagnostico` e `_conferencias_put`, e `npm run
  gen:contract`.
- [X] T055 [P] [US5] `tests/integration/test_aprendizado_diagnostico.py`:
  - uma conta nova com 8 posts num dia;
  - a repostagem entre contas;
  - um sinal que some quando a condição deixa de valer;
  - conferência com histórico;
  - nada criado em `postagens` nem em `notificacoes`.
- [X] T056 [US5] SPA: `abas/Diagnostico.tsx` (`SinaisDistribuicao`, checklist com marcação pelo dono) e o
  bloco no detalhe do vídeo estagnado.

---

## Phase 8: User Story 6 - Custo, cadência e controle (Priority: P3)

- [X] T057 [US6] `ia/service.py` e `ia_resumo`: o detalhamento por tipo inclui os 3 `aprendizado.*` (só
  dono). Preferências: a SPA tem os interruptores "classificação automática" e "usar desempenho no
  assistente" (`PATCH`).
- [X] T058 [P] [US6] `tests/integration/test_aprendizado_custo.py` (SC-009): o resumo separa as
  finalidades; membro recebe `null` em todo campo de custo da 023; com `classificacao_auto` pausada, um
  post novo fica pendente e "Sem tema" na análise.

---

## Phase 9: Polish & Cross-Cutting

- [X] T059 [P] `tests/integration/test_aprendizado_permissoes.py` (SC-006): todas as rotas H, com membro →
  403 `somente_dono`, e `system:*` e token MCP → 403 `somente_humano` mais o evento de recusa. As leituras
  aceitam membro.
- [X] T060 [P] `tests/unit/test_constitution_guards.py` (acréscimo, R13):
  - os imports proibidos em `aprendizado/`;
  - sem DELETE e sem "tiktok"/"youtube" em `aprendizado_*`;
  - as escritas com `require_human_owner`;
  - nenhuma atribuição a `direito` em `aprendizado/` e `canais/service_videos.py`;
  - os GETs de `aprendizado/` sem `db.add`, `history.record` nem `commit`;
  - `analytics/` continua só leitura (importa só `aprendizado.afinidade`).
- [X] T061 [P] `mcp/mapa.py` (acréscimo) e `tests/unit/test_mcp_mapa.py`: as leituras como tools
  `leitura`, as análises da IA em `FORA` e as escritas em `PROIBIDAS`. O teste "todo operationId
  classificado" continua verde.
- [X] T062 [P] `metricas/anonimizar.py` (acréscimo, R11) e `tests/integration/test_aprendizado_anonimizar.py`:
  - a justificativa, a sugestão e a nota ficam NULL;
  - as hipóteses que usaram a série são trocadas;
  - o tema e o estilo ficam;
  - a série anônima nunca vira exemplo (R8) nem entra na análise da IA.
- [X] T063 [P] `tests/integration/test_aprendizado_desempenho_perf.py` (R14): a análise e as recomendações
  < 2 s com 10× o volume; o Descobrir com afinidade ≤ +300 ms com 50 mil vídeos-fonte e 30 temas × 20
  palavras. Se falhar, aplicar o plano B do R9 ou do R14 e registrar no plan.
  - **Feito (2026-10-06):** o teste de 50 mil passava de +2,6 s; com o plano B do R9 (a migration 0019
    `aprendizado_fonte_temas`, aprovada pelo líder), voltou a ficar dentro de +300 ms. A análise com 10× o
    volume ficou abaixo de 2 s.
- [X] T064 `CLAUDE.md` (acréscimo): a seção "Aprendizado (desde a spec 023)", com:
  - o pacote e as tabelas;
  - a trilha `aprendizado` (limite diário, análise assíncrona, quadros no HD tmp);
  - o `ia/3` e o `<desempenho>`;
  - a afinidade só com perfil e os cortados ocultos;
  - "dono nunca sobrescrito";
  - as recomendações calculadas e as decisões gravadas.

  `docs/visao.md`: o item 023 no backlog.
- [X] T065 Verificação final:
  - `npm run test:api` inteiro, ruff, `npm run gen:contract && npm run check:web`;
  - a suíte e2e inteira (com trava);
  - percorrer o quickstart §1–§6 no dev.

  O §7 é **com o dono**, à mão; registrar o resultado. **Commit só quando o dono pedir.**

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate) → T002.
- **Phase 2** bloqueia tudo:
  - T003 → T004 e T005;
  - T006, T007, T010, T011, T012, T013 e T014 em paralelo; T007 → T008;
  - T005 + T009 → T015.
- **US1 (Phase 3):** T016 → T017 → T018 → T019. T020 depois de T010 e T011. T021 → T022 e T023. T024 →
  T025.
- **US2 (Phase 4):** depende das classificações da US1 (T017) para os fatores de tema.
  - T026 → T027 e T028;
  - T029 e T030 → T031 → T032 → T033;
  - T034 → T035.
- **US3 (Phase 5):** depende da T026. T036 → T037. T038 depende do `ia.service_guia` (017). T039 depende da
  T032.
- **US4 (Phase 6):** depende de T026 e T038. T044 → T045 e T046 → T047. T048 → T049 e T050.
- **US5 (Phase 7):** depende só da Phase 2 e da T009, e pode começar junto com a US2.
- **US6 (Phase 8):** depois da US1 e da US2.
- **Serialização:**
  - o `gen:contract` (T021, T028, T032, T040, T046, T054);
  - os arquivos compartilhados (`ia/prompt.py`, `ia/saida.py`, `ia/service.py`: T011, T048, T057);
  - os e2e, pela trava.
- **Phase 9** no fim. A T060 e a T061 podem começar assim que as rotas de cada história existirem.

### Paralelismo sugerido (agentes)

- **Frente A (API, núcleo):** T003, T005, T009, T015 → T016–T021 → T026, T028 → T036, T038–T040.
- **Frente B (IA e trilha):** T010–T013 → T018–T020 → T029–T032 → T048 → T057.
- **Frente C (testes):** T004, T008, T014, T022, T023, T027, T033, T037, T041, T045, T047, T049, T050, T055,
  T058–T063.
- **Frente D (SPA e e2e):** T024–T025, T034–T035, T042–T043, T051–T052, T056.
- **Frente E (buscador):** T044–T047, depois da T026.

## Implementation Strategy

- **MVP:** a US1 (temas e classificação) mais a US2 sem IA (T026–T028). Com isso, o dono já vê "que tema
  rende" com a honestidade estatística, e o "distribuição travada" das contas de hoje.
- **Depois:** a análise da IA (T029–T035), a US3 (decidir) e a US4 (fechar o ciclo); a US5 pode correr em
  paralelo.
- **Checkpoints:** depois da Phase 2, da US1, da US2 sem IA, da US3, da US4 (com o SC-008 verde) e no fim.
