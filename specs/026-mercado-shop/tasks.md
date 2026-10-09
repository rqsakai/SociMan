---

description: "Tarefas da feature 026-mercado-shop"
---

# Tasks: Cockpit do TikTok Shop coletado pelo SociMan (026-mercado-shop)

**Input:** `specs/026-mercado-shop/`, com:
- a spec, com as Clarifications de 2026-10-08 (fotos de clientes como vêm; revezamento entre perfis;
  avaliações e vídeos só para quentes; qualquer humano acompanha, pausa, encerra e segue loja);
- o plan (Constitution Check com o princípio IX; a 012 como dependência condicionada);
- a research R1–R24;
- o data-model (20 tabelas em três camadas, estados, regras derivadas, migração `0025_mercado_shop`);
- os contratos `contracts/http-api.md` (32 rotas) e `contracts/coletor.md` (serviço do host);
- o quickstart (§1 automático; §2 sonda com o dono; §3 ligar; §4 parar; §5 ponte com a 012).

**Pré-requisitos:**
- constitution **4.4.0** (princípio IX) já aplicada em `.specify/memory/constitution.md` (conferida na T001);
- a 016 (fotos só de inserção e a função `metricas_recusa_mudanca()`), a 009 (token e portão do MCP), a
  006 (notificações e trilhas) e a 004 (HD e `storage.py`) estáveis e verdes;
- a **012 (produtos)** é implementada em **outra sessão** a partir do mesmo HEAD: esta worktree não tem o
  pacote `produtos/` nem a migration `0022`. A Phase 8 (US6, "Adotar") e a coluna `produtos.mercado_produto_id`
  só rodam **depois do merge da 012**; até lá a migration pula a coluna (`has_table`).

A 026 mexe em `main.py`, `agendador.py`, `config.py`, `auth/deps.py`, `storage.py`, `notificacoes/models.py`,
`integracoes.py`, `mcp/mapa.py`, `docker/nginx/default.conf.template`, `scripts/check-secrets.mjs`,
`apps/web/src/nav.ts`, `e2e/fakes/server.py` e `docker-compose.e2e.yml`. Nenhum outro agente pode estar
editando esses arquivos ao mesmo tempo.

**Decisões do dono (2026-10-08):** coleta própria com a conta de afiliado do dono (risco aceito e registrado
em `docs/decisoes/coleta-mercado.md`); um perfil de Chrome logado sempre; ~300 páginas/dia das 08h às 23h,
pausas de 5 a 40 s; lago global e permanente, nada apagado, sem perfil; 2 fotos/dia para quentes e manuais;
vitrine para todos os perfis; vídeos top já na 026; vínculo com a 012 agora (condicionado); fotos de
clientes guardadas como vêm; revezamento entre perfis; qualquer humano acompanha e segue loja.

**Nomes canônicos:**
- **API:** pacotes `sociman_api/coleta/` (`models`, `credenciais`, `portao`, `ingestao`, `fila_api`,
  `service`, `schemas`, `router`) e `sociman_api/mercado/` (`models`, `mercados`, `constantes`,
  `fontes/{base,tiktok_shop,registro}`, `cadencia`, `fila`, `interesses`, `calculo`, `consulta`,
  `filtros`, `adotar`, `trilha`, `schemas`, `router`, `router_perfil`).
- **Rotas e `operationId`:** os de `contracts/http-api.md` (`coleta_*`, `mercado_*`).
- **Tabelas:** as 20 do data-model (12 do lago, 4 de operação, 2 de interesse, 2 de infra) e a coluna
  `produtos.mercado_produto_id` (012). Enums e CHECKs da seção "Tipos" do data-model.
- **Migration:** **`0025_mercado_shop`** (`down_revision = "0021_geracao_interrupcoes"`; provisória,
  conferida na T001).
- **Ator:** `Actor(kind="coletor", coleta_cliente_id=…)`, sem `user`; `RequireColetor`. Autor automático
  da trilha: `system:mercado`.
- **Token:** `scol_<8 base32>_<43 b64url>` (`coleta/credenciais.py`); cabeçalho
  `X-Sociman-Coleta-Protocolo: 1`.
- **Trilha:** `mercado` (`AGENDADOR_MERCADO_S`, padrão 300). **Config:** `COLETA_HABILITADA` (padrão
  `false`), `MERCADO_HASH_PEPPER` (segredo), `S3_MERCADO_BUCKET` (`sociman-mercado`).
- **Bucket:** `sociman-mercado` (bruto gzip); imagens no bucket `imagens` com prefixo `mercado/<sha[:2]>/`.
- **Notificações:** `coleta_captcha`, `coleta_login`, `coleta_bloqueio`, `coleta_layout`, `coleta_parada`,
  `mercado_interesse_auto`. **Eventos de segurança:** `coleta_recusada`, `coleta_aceite_risco`.
- **Coletor:** `apps/coletor/` (pacote `sociman_coletor`, CLI `sociman-coletor`, unidade
  `systemd/sociman-coletor.service`, esquema `tiktok_shop/1`).
- **SPA:** `pages/mercado/{Mercado,ProdutoMercado}.tsx` e `pages/mercado/abas/*`,
  `pages/perfis/tabs/MercadoTab.tsx`, `pages/configuracoes/Coleta.tsx`, `components/mercado/*`,
  `lib/mercado.ts`; rotas `/app/mercado`, `/app/mercado/produtos/:id`, `/app/configuracoes/coleta`.
- **Testes:** fake `tests/fakes/coletor_fake.py`; `e2e/fakes/coletor_fake.py` (no `openshorts-fake`);
  `e2e/mercado.spec.ts`; `apps/coletor/tests/` (servidor HTML sintético em `tests/sintetico/`).

**Tests**: OBRIGATÓRIOS (constitution VI):
- pytest na stack efêmera (`npm run test:api [-- args]`);
- `docker compose exec -T api uv run ruff check .`;
- `cd apps/coletor && uv run pytest && uv run ruff check .`;
- `npm run gen:contract && npm run check:web`;
- e2e com trava: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/mercado.spec.ts]`.

Nada chama a rede real: nem o TikTok Shop, nem o Affiliate Center. A validação real é a sonda do
quickstart §2, **com o dono**.

**Arquivos compartilhados, SÓ ACRÉSCIMO:** `main.py`, `agendador.py`, `config.py`, `auth/deps.py`,
`storage.py`, `notificacoes/models.py`, `integracoes.py`, `mcp/mapa.py`,
`tests/unit/test_constitution_guards.py`, `e2e/fakes/server.py`, `e2e/helpers.ts`, `nav.ts`, `CLAUDE.md`
e `docs/visao.md`. `packages/contract/**` é gerado.

**Dependências externas (NÃO executar neste repo; o dono aplica):**
- **X1:** perfil de Chrome dedicado logado na conta de afiliado (`sociman-coletor perfil-iniciar`).
- **X2:** categorias do nicho por perfil, depois da 1ª tarefa `categorias`.
- **X3:** token `scol_` em `~/.config/sociman-coletor/token` (600), `api_url` e `ca_cert` no `config.toml`.
- **X4:** aceite de risco na tela e `MERCADO_HASH_PEPPER` + `COLETA_HABILITADA=true` no `.env` da raiz.
- **X5:** unidade systemd de usuário instalada com a sessão gráfica ativa.
- **X6:** sonda `uma-vez --limite 1` e `--limite 3` acompanhada (quickstart §2), antes do `rodar`.
- **X7:** lista inicial de links e a vitrine.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US6 da spec

---

## Phase 1: Setup

- [x] T001 **Gate:**
  - `grep -n "^### IX" .specify/memory/constitution.md` encontra o princípio IX e a versão é **4.4.0**;
  - `ls apps/api/migrations/versions/` mostra **`0021_geracao_interrupcoes`** como a última nesta worktree.
    Se a 012 (`0022`) já foi mesclada, ou outra spec ocupou `0025`, renomeie para o próximo livre **em
    todos os documentos da 026** e ajuste o `down_revision`; registre a decisão no `plan.md`
    ("Dependências e ordem");
  - `docker compose exec api uv run alembic heads` mostra só a última;
  - os testes da 016, 009 e 006 estão verdes: `npm run test:api -- tests/ -k "metricas or mcp or notific" -q`;
  - `/usr/bin/git status --short` só tem o esperado; `.specify/feature.json` aponta para a 026.
- [x] T002 [P] `apps/api/src/sociman_api/config.py` (acréscimo): `coleta_habilitada: bool = False`,
  `agendador_mercado_s: float = Field(300, gt=0)`, `mercado_hash_pepper: SecretStr = SecretStr("")`,
  `s3_mercado_bucket: str = "sociman-mercado"`, `coleta_protocolo: int = 1`. Nenhum segredo com valor
  padrão; `.env.example` ganha `COLETA_HABILITADA=false` e `MERCADO_HASH_PEPPER=` vazio com o comentário
  "gerado pelo dono, nunca impresso".
- [x] T003 [P] `apps/api/src/sociman_api/storage.py` (acréscimo): `Bucket` ganha `"mercado"` →
  `s.s3_mercado_bucket`, criado por `ensure_buckets`. **Nenhum delete novo.**
  `scripts/data-setup.sh check` lista o bucket.
- [x] T004 [P] `scripts/check-secrets.mjs` (acréscimo): padrão `scol_[a-z2-7]{8}_[A-Za-z0-9_-]{43}` com
  um caso de teste positivo e um negativo no próprio script (como o `smcp_`).
- [x] T005 [P] `docker/nginx/default.conf.template` (acréscimo, antes de `location /api/`):
  `location ~ ^/api/coleta/coletas/[^/]+/imagens$ { client_max_body_size 60m; proxy_request_buffering off; … }`
  e `location ~ ^/api/coleta/coletas/[^/]+/itens$ { client_max_body_size 10m; … }`, copiando os headers
  da location de áudios. Depois: `docker compose restart edge`.

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Objetivo:** tabelas, token, portão, ingestão e fakes. Sem isto nenhuma história é testável, porque até
o cockpit (US1) é alimentado pelo coletor falso **pela API de ingestão**.

- [x] T006 `apps/api/migrations/versions/0025_mercado_shop.py` exatamente como a seção "Migração
  `0025_mercado_shop`" do data-model: os 11 tipos novos + `ALTER TYPE notificacao_tipo ADD VALUE IF NOT
  EXISTS` ×6 em `autocommit_block`; `coleta_clientes`, `coleta_config`; o lago na ordem das FKs (com
  `use_alter` em `mercado_produtos.ficha_atual_id` e `mercado_coletas.tarefa_atual_id`); `mercado_fila`,
  `mercado_coleta_itens`, `coleta_eventos`; `mercado_interesses` (FK `produto_id` → `produtos` **só se
  `inspector.has_table("produtos")`**; `tema_id` → `aprendizado_temas`) e `mercado_perfil_config`;
  índices e CHECKs (`mercado ~ '^[A-Z]{2}$'`, `NOT habilitada OR risco_aceito_em IS NOT NULL`,
  `categoria_ids` ≤ 5); trigger `mercado_so_insercao` (`metricas_recusa_mudanca()`) nas **11** tabelas
  só de inserção listadas; `produtos.mercado_produto_id` **só se a tabela existir**; downgrade recusa com
  dados em `mercado_produtos`, `mercado_coletas` ou `coleta_clientes`.
- [x] T007 [P] `apps/api/tests/integration/test_migration_0025.py`: upgrade, downgrade vazio, recusa do
  downgrade com dados, os dois caminhos da coluna da 012 (com e sem `produtos`), `UPDATE`/`DELETE` nas 11
  tabelas só de inserção levantam erro, `TRUNCATE` passa, CHECK do `mercado` e da `coleta_config`.
- [x] T008 `apps/api/src/sociman_api/mercado/models.py`: as 17 tabelas do lago (12), operação (`mercado_fila`,
  `mercado_coletas`, `mercado_coleta_itens`; `coleta_eventos` fica na T009) e interesse (2) com
  as colunas, tipos, UQs e índices do data-model (`mercado_produto_fotos` UQ `(produto_id, data_local,
  turno, fonte)`; `mercado_interesses` UQ parcial em ativos com `coalesce(perfil_id, uuid_nil)`;
  `mercado_fila` UQ parcial `(tipo, chave, data_local, turno)` em `pendente|reservada`; `mercado_coletas`
  UQ parcial 1 ativa por cliente); `__versioned_fields__`/`__immutable_fields__` só nas duas de interesse.
  Nenhuma tabela do lago com `perfil_id` (exceção nominal `mercado_fila.perfil_id`, documentada no
  docstring).
- [x] T009 [P] `apps/api/src/sociman_api/coleta/models.py`: `coleta_clientes` (cópia de `McpCliente` com
  `token_id` UNIQUE, `token_hash`, `situacao coleta_situacao`, `expira_em`, `mercado char(2)`,
  `ultimo_contato_em`, `versao_coletor`, `version`, AuditMixin, `entity_type = "coleta_cliente"`),
  `coleta_config` (id=1; campos e CHECK do data-model; `entity_type = "coleta_config"`) e
  `coleta_eventos` (só inserção). `main.py`/`alembic env` registram os modelos.
- [x] T010 [P] `apps/api/src/sociman_api/mercado/mercados.py` (`MERCADOS = {"BR": Mercado(tz=
  "America/Sao_Paulo", moeda="BRL")}`, `data_local_e_turno(coletado_em, mercado)` com `TURNO_CORTE`) e
  `mercado/constantes.py` com **todas** as constantes nomeadas da seção "Regras derivadas" do data-model
  (uma por linha, com comentário do FR). `tests/unit/test_mercado_mercados.py`: meia-noite, 15:29 vs 15:31,
  mercado desconhecido → erro.
- [x] T011 [P] `apps/api/src/sociman_api/coleta/credenciais.py`: cópia de `mcp/credenciais.py` com
  `PREFIXO = "scol_"`, `FORMATO`, `gerar()`, `hash()`, `conferir()` com `compare_digest`, `Segredo` com
  `repr` mascarado. `tests/unit/test_coleta_credenciais.py`: formato, hash estável, repr nunca mostra o
  segredo, `check:secrets` acusa um token de exemplo (teste do script via `node`).
- [x] T012 `apps/api/src/sociman_api/auth/deps.py` (acréscimo): `Actor.coleta_cliente_id`, `kind ==
  "coletor"`, `require_coletor` (401 sem token; 403 `somente_coletor` para outro ator) e
  `RequireColetor`. `require_human*` já recusam o coletor ("somente humano" + `publicacao_recusada`).
- [x] T013 `apps/api/src/sociman_api/coleta/portao.py` (molde `mcp/portao.py`): dependência global em
  `main.py`; para Bearer `scol_`: credencial (401 `coleta_nao_autorizada`) → `COLETA_HABILITADA` **e**
  `coleta_config.habilitada` (fila vazia no `GET /fila`; 503 `coleta_desligada` nas outras) → revogado ou
  vencido (401) / suspenso (403) → `Origin` presente (403 `coleta_origem`) → rota fora de `/api/coleta/*`
  ou gestão (403 `escopo_coleta`) → cabeçalho `X-Sociman-Coleta-Protocolo` ≠ `coleta_protocolo` (426
  `protocolo_coleta`) → limite no Redis `coleta:limite:<id>` 120/min (429 `coleta_limite`; Redis fora →
  503). Toda recusa grava `security_events` `coleta_recusada` (`actor_kind = "coletor"`, `details = {motivo,
  tokenId, rota}`). Atualiza `ultimo_contato_em` e `versao_coletor` (cabeçalho `X-Sociman-Coletor-Versao`).
- [x] T014 [P] `apps/api/tests/integration/test_coleta_portao.py`: cada degrau da ordem acima, token em
  rota `/api/mercado/*` → 403 `escopo_coleta`, token em `/api/perfis` → 403, com `COLETA_HABILITADA=false`
  fila vazia + 503, protocolo errado → 426, `Origin` → 403, 121ª chamada → 429, evento `coleta_recusada`
  gravado e mascarado.
- [x] T015 `apps/api/src/sociman_api/mercado/fontes/base.py` (Protocol `FonteMercado`: `rede`,
  `esquema_versao`, `tipos`, `validar_chave(tipo, chave)`, `normalizar(tipo, campos, bruto) ->
  Normalizado`), `fontes/tiktok_shop.py` (esquema `tiktok_shop/1`, os 7 tipos e os payloads de
  `contracts/coletor.md` § "Payloads normalizados", em Pydantic) e `fontes/registro.py` (`FONTES =
  {Platform.tiktok: FonteTikTokShop()}`, `fonte_para(rede)`, único importador). `tests/unit/
  test_mercado_fontes.py`: cada tipo com JSON sintético de `tests/fixtures/mercado/`, campo faltando →
  `invalido` com `field`, faixa "1,2 mil" → `vendidos_min/max/exato=false`, preço por variante →
  `preco_min/max`.
- [x] T016 `apps/api/src/sociman_api/coleta/ingestao.py`: `abrir_rodada` (409 `coleta_em_andamento` pela
  UQ parcial; 503 se desligada), `receber_itens` (lote ≤ 50 e ≤ 6 MB → 413 `lote_grande`; por item:
  tarefa reservada deste cliente → senão `invalido` `tarefa_desconhecida`; `data_local`/`turno` **do
  servidor** por `coletado_em` no fuso do mercado; normaliza pela fonte; poda `CHAVES_PESSOAIS` do bruto e
  recusa `bruto_pessoal`; `INSERT … ON CONFLICT DO NOTHING` nas fotos/rankings/avaliações/vídeos →
  `gravado|repetido`; ficha nova só se `hash_conteudo` mudou (atualiza `ficha_atual_id`); identidade de
  produto/loja/categoria por `(rede, mercado, id)` com UPDATE só em "último visto"; bruto gzip no bucket
  `mercado` com `datadir.ensure_writable` (sem HD → grava a foto, item `bruto_pendente`); grava
  `mercado_coleta_itens` sempre; tarefa → `recebida|pendente(tentativas+1)|falhou`), `receber_imagens`
  (multipart ≤ 10 × 5 MB; `validate_image` pelo conteúdo; sha256 no servidor **e** conferido com o do
  cliente; dedup em `mercado_imagens`; bucket `imagens` prefixo `mercado/`; teto `imagens_por_produto` e
  `imagens_dia`), `batimento`, `fechar_rodada` (tarefas reservadas voltam a `pendente`), `evento` (→
  `coleta_eventos` + notificação por tipo com `dedupe_key` do data-model; `bloqueio_suspeito|layout_mudou`
  → rodada `abortada` + `pausada_ate = +RECUO_BLOQUEIO_H`), `link_bruto` (`midia.py` com validade).
- [x] T017 `apps/api/src/sociman_api/coleta/fila_api.py`: `GET /fila` devolve `habilitada`, `pausadaAte`,
  `continuarEm`, `janelas`, `limites {paginasDia, imagensDia, imagensPorProduto, itensPorColeta,
  intervaloMinS, intervaloMaxS}`, `orcamentoRestanteHoje {paginas, imagens}` (calculado de
  `mercado_coleta_itens`/`mercado_imagens` de hoje) e até `limite` tarefas `pendente` do dia por
  `(prioridade, nivel, posicao)` marcadas `reservada` com `reservada_ate = now() + FILA_LEASE_MIN`; fila
  vazia fora da janela, pausada, antes de `continuarEm` ou desligada.
- [x] T018 `apps/api/src/sociman_api/coleta/schemas.py` + `coleta/router.py` (rotas **C** de
  `contracts/http-api.md`: `coleta_fila`, `coleta_coletas_abrir`, `coleta_itens_enviar`,
  `coleta_imagens_enviar`, `coleta_batimento`, `coleta_coletas_fechar`, `coleta_eventos_enviar`,
  `coleta_bruto_link`), montado em `main.py`. Erros em pt-BR com os códigos do contrato.
- [x] T019 [P] `apps/api/tests/fakes/coletor_fake.py`: gera rodadas sintéticas (N produtos × D dias ×
  turnos, com `vendidos` crescente, preço, comissão, criadores, uma loja, 1 ranking/dia, 6 imagens PNG
  geradas por Pillow, 5 avaliações, 3 vídeos) e posta pela API de ingestão com um token real criado no
  teste (`criar_cliente_coleta`, `com_coletor`). Reusa o padrão de `tests/integration/mcp_helpers.py`.
- [x] T020 [P] `apps/api/tests/integration/test_coleta_ingestao.py`: abrir rodada (2ª → 409), lote
  gravado, reenvio → `repetido` (SC-004), item com campo faltando → `invalido` sem derrubar o lote, ficha
  igual não cria versão / ficha mudada cria, imagem repetida entre produtos → 1 objeto, imagem que não é
  imagem → recusada, sha divergente → recusada, bruto com `nome` → `bruto_pessoal`, HD ausente → foto
  gravada + `bruto_pendente`, data_local/turno do servidor (relógio do cliente ignorado), eventos → rodada
  `abortada`/`pausada_*` + notificação dedupe, fechar rodada devolve reservas.
- [x] T021 `apps/api/tests/unit/test_constitution_guards.py` (acréscimo, seção "spec 026", R20):
  `test_api_sem_automacao_de_navegador` (`pyproject` sem `playwright|selenium|pyppeteer`);
  `test_mercado_e_coleta_sem_rede` (`IMPORTS_PROIBIDOS_026 = ("httpx", "playwright",
  "sociman_api.publicacao")`; hosts `tiktok|affiliate` em literais só em `apps/coletor/`);
  `test_mercado_lago_sem_perfil` (metadata: nenhuma `mercado_*`/`coleta_*` com `perfil_id|conta_id|
  tenant_id|created_by|user_id`, exceto `mercado_fila.perfil_id` e as duas de interesse);
  `test_mercado_sem_delete` (AST sem `delete(`/`DELETE`/`TRUNCATE`/`apagar_por_excecao` em `mercado/` e
  `coleta/`); `test_coleta_portao_global` (dependência no `app`; `scol_` em rota não-coleta → 403);
  `test_coleta_token_so_hash`; `test_agendador_sem_trilha_nova` += `"mercado"` (ativado na T052);
  `test_mercado_rotas_de_leitura_so_get` (reuso de `ESCRITAS_ORM/_SQL` da 019 sobre `mercado/consulta.py`,
  `calculo.py`, `router.py` GETs); o teste existente de nomes cobre `coleta_*`/`mercado_*` sem "tiktok".
- [x] T022 [P] `apps/api/src/sociman_api/notificacoes/models.py` (acréscimo dos 6 tipos) e
  `integracoes.py` (bloco `coleta`: `habilitadaNoServidor`, `habilitada`, `riscoAceito`, `ultimoContatoEm`,
  `paginasHoje`, `imagensHoje`, `rodadaAtual`, `pausadaAte`; calculado na hora).

**Checkpoint:** `npm run test:api -- tests/integration/test_migration_0025.py tests/integration/
test_coleta_ingestao.py tests/integration/test_coleta_portao.py tests/unit/test_constitution_guards.py -q`
verde; `ruff` verde.

---

## Phase 3: User Story 1 - Ver o cartão do produto no cockpit (Priority: P1) 🎯 MVP

**Objetivo:** com fotos no lago, o cockpit mostra o cartão mínimo com os números calculados na leitura,
marcados "estimado", e exporta CSV.

**Independent Test:** spec US1 (coletor falso, 3 produtos × 10 dias, cartões e CSV).

- [x] T023 [US1] `apps/api/src/sociman_api/mercado/calculo.py` (puro): `v_de(fotos, d)`, `vendas_periodo`
  (negativo → 0 + `inconsistente`), `vendas_dia` (`MIN_FOTOS_VENDAS`, `MIN_DIAS_ENTRE_FOTOS`, estado
  `coletando|amostra_pequena|ok`), `gmv_periodo` (pares consecutivos × `preco_min` do início; `{min,max}`
  com faixa), `crescimento` (7 d vs 7 d, `MIN_VENDAS_DIA_BASE`), `vendas_totais`, `gmv_total` (`grosseiro`),
  `comissao_por_venda` (`cupons_nao_descontados`), `retorno_dia`, `retorno_por_afiliado` (`K_AFILIADOS`),
  `saturacao`, `novo_em_alta`, `alto_retorno_poucos_afiliados` (percentis por categoria com
  `MIN_PRODUTOS_CATEGORIA`, fallback `POUCOS_AFILIADOS`), indicadores de loja e categoria, variação de
  ranking. Toda saída `Numero {valor, estimado, motivos, amostraPequena, nFotos}`.
- [x] T024 [P] [US1] `apps/api/tests/unit/test_mercado_calculo.py`: cada fórmula com séries sintéticas
  (os números do SC-001 calculados à mão no teste), 1 foto → `coletando`, 5 dias → `amostra_pequena`, delta
  negativo, faixa "1,2 mil", AC com `vendas_7d` tem precedência, sem AC → `semDadoAfiliado`, percentis com
  9 produtos → fallback.
- [x] T025 [US1] `apps/api/src/sociman_api/mercado/filtros.py` (filtro comum FR-043: `de/ate` padrão
  `PERIODO_PADRAO_DIAS` no fuso do mercado, ≤ `PERIODO_MAX_DIAS` → 400 `periodo_invalido`; `perfilId` só
  restringe por interesse/categorias; `mercado`, `rede`, `categoriaId`, `lojaId`, `origem`,
  `soAcompanhados`, `q`, `ordenar`, `cursor/limite`) e `mercado/consulta.py` (R16): `listar_produtos`
  (`DISTINCT ON` da última foto ≤ `ate` e ≤ `de − 1` por produto, `LAG` para o GMV; só SELECT),
  `detalhe_produto`, `serie_produto`, `resumo` (cards Mais vendidos, Novos em alta, Alto retorno, Estado
  da coleta). Nenhuma escrita; nenhuma tabela agregada.
- [x] T026 [US1] `apps/api/src/sociman_api/mercado/schemas.py` (`Numero`, `CartaoProdutoOut` com os campos
  do cartão mínimo + `estado`, `interesse|null`, `ultimaFotoEm`; `ResumoOut`; `SerieOut`) e
  `mercado/router.py` (rotas **U**: `mercado_produtos_listar`, `mercado_produtos_detalhe`,
  `mercado_produtos_serie`, `mercado_resumo`), montado em `main.py`.
- [x] T027 [US1] `apps/api/src/sociman_api/mcp/mapa.py` (acréscimo): `coleta_fila`, `coleta_coletas_abrir`,
  `coleta_itens_enviar`, `coleta_imagens_enviar`, `coleta_batimento`, `coleta_coletas_fechar`,
  `coleta_eventos_enviar`, `coleta_bruto_link` → `FORA` ("serviço do coletor"); `mercado_produtos_listar`,
  `mercado_produtos_detalhe`, `mercado_produtos_serie`, `mercado_resumo` → `TOOLS` escopo `leitura`
  ("Mercado: produtos", "…detalhe", "…série", "Mercado: resumo"). Depois: `npm run gen:contract`
  (`packages/contract/**` e `mcp-tools.json`) e `test_mcp_mapa` verde.
- [x] T028 [P] [US1] `apps/api/tests/integration/test_mercado_leitura.py`: com o `coletor_fake` (3 produtos
  × 10 dias), a lista traz os 3 cartões com os valores do SC-001, `estimado = true` em todo derivado,
  `coletando` no produto de 1 foto, `semDadoAfiliado` no sem comissão, filtro `perfilId` restringe,
  `periodo_invalido` em 401 dias, `ordenar` por cada campo, cursor estável; membro vê comissão e retorno;
  tool MCP `mercado_produtos_listar` lê; nenhuma escrita (guarda).
- [x] T029 [US1] SPA: `apps/web/src/lib/mercado.ts` (hooks TanStack Query do cliente gerado),
  `components/mercado/Estimado.tsx` (selo + tooltip com os motivos, texto escapado),
  `components/mercado/CartaoProduto.tsx` (cartão mínimo + projeção 10/100/1000 calculada no cliente),
  `pages/mercado/Mercado.tsx` (`Page` + `HeaderCard`, abas na URL `?aba=cockpit|produtos|rankings|lojas|
  acompanhamentos`, `FilterBar` + `useFiltroUrl("mercado")`), `pages/mercado/abas/Cockpit.tsx` (4 cards
  com "Ver tabela" e CSV via `components/analytics/csv.ts`) e `abas/Produtos.tsx` (`DataTable` com
  `ServerPagination`, colunas do cartão, `EmptyState` "nada coletado ainda"). Rota lazy `/app/mercado` no
  mesmo arranjo do chunk `graficos`; `nav.ts`: grupo Analytics ganha "Mercado de produtos"; a aba
  "Mercado" de `/app/metricas` passa a "Fontes" (texto só).
- [x] T030 [US1] SPA: `pages/mercado/ProdutoMercado.tsx` (`/app/mercado/produtos/:id`): cabeçalho com o
  cartão, série (`components/mercado/SerieProduto.tsx` com ECharts modular: vendidos acumulado, vendas/dia,
  preço, criadores; tooltip texto), seções vazias "Ficha", "Galeria", "Rankings", "Vídeos", "Avaliações"
  (preenchidas na US5) e botões desabilitados "Acompanhar neste perfil" / "Adotar no catálogo" (US4/US6).
- [x] T031 [P] [US1] (feito em TypeScript: `e2e/coletor.ts` semeia pela ingestão real com um token `scol_`, sem fake Python) `e2e/fakes/coletor_fake.py` dentro do `openshorts-fake` (`e2e/fakes/server.py`,
  acréscimo): rota `/coleta-e2e/semear {produtos, dias}` que posta pela ingestão do SociMan de e2e com um
  token criado por `/coleta-e2e/token`: o fake gera o segredo com o mesmo formato de `coleta/credenciais.py`,
  **insere só o hash** em `coleta_clientes` via `sqlE2e` (o banco nunca tem o token, FR-024) e guarda o
  segredo em memória do processo do fake; `docker-compose.e2e.yml`
  com `COLETA_HABILITADA=true` e `MERCADO_HASH_PEPPER` de teste; `e2e/helpers.ts` ganha
  `semearMercado(page, {produtos, dias})`.
- [x] T032 [US1] `e2e/mercado.spec.ts` (US1): semear 3 produtos × 10 dias; `/app/mercado` mostra os 3
  cartões com selo "estimado", 1 "coletando"; filtro de período na URL; "Ver tabela" e CSV do card Mais
  vendidos com as mesmas linhas; detalhe abre com a série; membro vê os mesmos números e não vê ações de
  dono. `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/mercado.spec.ts`.

**Checkpoint:** US1 verde (pytest + e2e), `gen:contract` sem divergência, `check:web` verde.

---

## Phase 4: User Story 2 - O coletor navega como pessoa e devolve o que viu (Priority: P1)

**Objetivo:** o serviço `apps/coletor/` pega a fila, navega no Chrome real com ritmo humano, só lê, devolve
campos, bruto e imagens, e para em captcha/login/bloqueio.

**Independent Test:** spec US2 (servidor HTML sintético + SociMan de teste; `uma-vez --limite 3`; captcha
sintético para e registra; AST sem ação proibida).

- [x] T033 [US2] `apps/coletor/pyproject.toml` (Python 3.12, uv; deps `playwright`, `httpx`, `pydantic`,
  `tomli`/stdlib; `[project.scripts] sociman-coletor = "sociman_coletor.main:main"`; ruff e pytest),
  `apps/coletor/README.md` (instalação pelo dono = quickstart §2) e `apps/coletor/systemd/
  sociman-coletor.service` (`[Unit] After=graphical-session.target`, `[Service] ExecStart=%h/.local/bin/
  sociman-coletor rodar`, `Restart=on-failure`, `EnvironmentFile=-%h/.config/sociman-coletor/env`,
  `[Install] WantedBy=default.target`). O `pyproject` da API **não** muda (guarda T021).
- [x] T034 [P] [US2] `apps/coletor/sociman_coletor/config.py` (`~/.config/sociman-coletor/config.toml`:
  `api_url`, `ca_cert`, `chrome_bin`, `perfil_dir`, `coletor_versao`; token de `~/.config/sociman-coletor/
  token` (600, recusa se mais permissivo) ou `SOCIMAN_COLETA_TOKEN`; `Segredo` com repr mascarado),
  `log.py` (journald/stderr; só `tarefaId`, tipo, ids de produto, contagens, durações, códigos; filtro que
  recusa chaves `cookie|authorization|nome|@|url?`), `janela.py` (puro: dentro da janela no fuso do
  mercado) e `ritmo.py` (puro, RNG semeado, **constantes e valores de `contracts/coletor.md` § Ritmo
  humano**: `PAUSA_MIN_S = 5`/`PAUSA_MAX_S = 40` entre páginas e antes de clicar (soma de dois uniformes, ou
  os limites do servidor se forem maiores), `PAUSA_CURTA_MS` 300..1500 entre passos de rolagem,
  `BLOCO_PAGINAS = 10` com `PAUSA_LONGA_S` 60..180, `ROLAGEM_PASSOS` 3..8 × `ROLAGEM_PX` 300..900,
  `JITTER_JANELA_MIN` 0..20, `DORMIR_FILA_VAZIA_MIN = 15`, `menor_dos_dois(limites locais, limites do
  servidor)`).
- [x] T035 [P] [US2] `apps/coletor/tests/test_ritmo.py` (pausas dentro dos limites, bloco, menor dos dois),
  `test_janela.py` (08:00/22:59/23:00, fuso), `test_config.py` (token 644 → recusa; repr mascarado) e
  `test_log.py` (nenhuma chave proibida passa).
- [x] T036 [US2] `apps/coletor/sociman_coletor/api.py`: cliente httpx da ingestão (base `api_url`, `verify
  = ca_cert`, cabeçalhos `Authorization: Bearer scol_…`, `X-Sociman-Coleta-Protocolo: 1`,
  `X-Sociman-Coletor-Versao`), métodos `fila`, `abrir`, `enviar_itens`, `enviar_imagens`, `batimento`,
  `fechar`, `evento`, `link_bruto`; 426 → mensagem "atualize o coletor"; 401/403 → para e loga o código;
  503 `coleta_desligada` → dorme 5 min. `tests/test_api.py` com `httpx.MockTransport`.
- [x] T037 [US2] `apps/coletor/sociman_coletor/navegador.py` (R2): acha o binário (`chrome_bin` →
  `google-chrome` → `google-chrome-stable` → `chromium`), `flock` em `<perfil>/.sociman-lock`, lança
  `--user-data-dir=<perfil> --remote-debugging-port=0 --no-first-run --no-default-browser-check
  --lang=pt-BR --window-size=1280,900` (visível), espera `<perfil>/DevToolsActivePort`, `chromium.
  connect_over_cdp("http://127.0.0.1:<porta>")`, `browser.contexts[0]`, 1 aba; `fechar()` com SIGTERM;
  `perfil-iniciar` abre sem conectar e espera o dono fechar. Erros: Chrome ausente, sem display, perfil
  travado.
- [x] T038 [US2] `apps/coletor/sociman_coletor/navegacao.py` (**única fonte de cliques**:
  `CLIQUES_PERMITIDOS` = fechar aviso/tour, aba de categoria, paginação, "ver mais"; `rolar_em_passos`,
  `mover_mouse`, `esperar`; recusa clique em elemento cujo texto case `ACOES_PROIBIDAS = r"Adicionar|
  Promover|Seguir|Comprar|Enviar|Comentar|Curtir|Salvar|Solicitar|Amostra"`), `sinais.py` (captcha por
  URL/seletores de verificação, redirecionamento para login, 429/403 em série `BLOQUEIO_SEQ = 3`,
  `PARSES_VAZIOS_MAX = 5`) e `privacidade.py` (`CHAVES_PESSOAIS` podadas do bruto antes de enviar;
  `autor_hash` **não** é feito aqui: o servidor faz com o pepper; o coletor manda o `redeAutorId` só no
  campo próprio, que o servidor hasheia e descarta).
- [x] T039 [US2] `apps/coletor/sociman_coletor/redes/base.py` (Protocol `ColetorRede`: `rede`, `tipos`,
  `pode(url)`, `executar(tarefa, page, ctx) -> Resultado`) e `redes/tiktok_shop.py`: `INTERCEPTAR` (lista
  fechada de fragmentos de URL da API interna, **vazia de valores reais até a sonda**, preenchida no
  quickstart §2 e versionada como `tiktok_shop/1`), `page.on("response")` → captura JSON; parsers por tipo
  (`produto`, `ranking`, `categorias`, `vitrine`, `loja`, `avaliacoes`, `produto_videos`) → `campos`
  conforme `contracts/coletor.md`; DOM como reserva para `vendidos`/preço; `imagens.py` (download no
  contexto do navegador por `context.request.get`, sha256, até `imagensPorProduto`, teto diário; imagens de
  avaliação idem). Tipos reservados (`busca_assunto`, `video`) → `tipo_desconhecido`.
- [x] T040 [US2] `apps/coletor/sociman_coletor/main.py`: laço `rodar` (janela → fila → abrir rodada → por
  tarefa: executar, enviar itens, enviar imagens, batimento a cada 60 s, pausas do `ritmo` → fechar);
  `uma-vez --limite N`; `dry-run` (fila sem navegar); `autoteste [--sem-token]`; `perfil-iniciar`; `parar`
  (cria `PARAR`); `reprocessar --desde DATA` (baixa bruto por `link_bruto`, reaplica parsers, reenvia com
  `reprocessadoDe`); kill switch: arquivo `~/.config/sociman-coletor/PARAR`, SIGTERM e fila vazia; captcha
  → evento + espera `continuarEm` do servidor + `CAPTCHA_ESFRIAR_MIN`; `CAPTCHA_ESPERA_MAX_H` → encerra.
  Nunca abre URL fora da fila.
- [x] T041 [P] [US2] `apps/coletor/tests/sintetico/` (servidor HTTP local em thread: páginas HTML que
  carregam JSON pelos mesmos fragmentos de `INTERCEPTAR` de teste, uma página de captcha, uma de login, uma
  "layout mudou") e `apps/coletor/tests/test_fluxo.py`: com Chromium do Playwright **só no teste** (marcador
  `@pytest.mark.navegador`, pulado sem navegador) `uma-vez --limite 3` contra o sintético e um SociMan
  falso (`MockTransport`): 3 resultados aceitos, imagens com sha, pausas (relógio simulado), captcha →
  evento + parada, login → evento, 5 vazios → `layout_mudou`.
- [x] T042 [P] [US2] `apps/coletor/tests/test_guardas.py` (AST): `.click(` só em `navegacao.py` dentro de
  `CLIQUES_PERMITIDOS`; nenhum `.fill(|.type(|.press(|set_input_files|route(` fora de `imagens.py`;
  `evaluate(` sem `fetch|XMLHttpRequest`; nenhum `httpx|requests` para host ≠ `api_url` (só `api.py`);
  nenhum `print(` de `cookie|Authorization`; `INTERCEPTAR` e `CLIQUES_PERMITIDOS` são tuplas/frozensets
  constantes.
- [x] T043 [US2] `apps/api/tests/integration/test_coleta_protocolo.py`: o contrato do coletor contra a API
  real de teste (fixtures de `contracts/coletor.md`): fila com limites e orçamento, orçamento zerado → fila
  vazia, lease vencido devolve, item de tarefa não reservada → `invalido`, batimento atualiza
  `ultimo_contato_em`, 426 com protocolo 2.

**Checkpoint:** `cd apps/coletor && uv run pytest && uv run ruff check .` verde; T043 verde. A sonda real
(quickstart §2) só com o dono, **depois** da US3.

---

## Phase 5: User Story 3 - Ligar a coleta com aceite de risco, token e interruptor (Priority: P1)

**Objetivo:** a tela de configuração só de dono: aceite, interruptor, tokens, janelas e tetos, pausar,
continuar, estado e rodadas.

**Independent Test:** spec US3 (sem aceite → 409; token 1 vez; `.env` desligado esvazia a fila; revogar →
não autorizado; membro só vê o estado; MCP recusado).

- [x] T044 [US3] `apps/api/src/sociman_api/coleta/service.py`: `criar_cliente` (token mostrado 1 vez,
  `no-store`), `rotacionar` (novo `token_id`), `suspender`, `reativar`, `revogar` (final; `coleta_situacao`
  = `revogado`), `aceitar_risco` (grava `risco_aceito_em/por` + `security_events` `coleta_aceite_risco`),
  `atualizar_config` (409 `risco_nao_aceito` ao ligar sem aceite; janelas/tetos/pausas validados;
  `pausar {horas}` → `pausada_ate`; `continuar` → `continuar_em = now() + CAPTCHA_ESFRIAR_MIN` e rodadas
  `pausada_*` → `ativa`), tudo com `history.record` e `version` (409 `version_conflict`); `estado()`
  calculado na hora; `listar_coletas` com itens e eventos.
- [x] T045 [US3] `coleta/router.py` (acréscimo das rotas de gestão **Ho** e leitura **U** do contrato:
  `coleta_clientes_*`, `coleta_config_*` (`ler`, `atualizar`, `aceitar_risco`, `pausar`, `continuar`,
  `versions`), `coleta_estado`, `coleta_coletas_listar`, `coleta_coletas_detalhe`, `coleta_eventos_listar`);
  `mcp/mapa.py`: gestão → `PROIBIDAS`; `coleta_estado` → `TOOLS` leitura; `coleta_coletas_listar/detalhe`,
  `coleta_eventos_listar` → `FORA` (dado de dono). `npm run gen:contract`.
- [x] T046 [P] [US3] `apps/api/tests/integration/test_coleta_config.py`: ligar sem aceite → 409; aceite
  grava quem/quando + evento; token exibido 1 vez e lista só com prefixo; rotação invalida o antigo;
  revogar → 401 no coletor; `COLETA_HABILITADA=false` → fila vazia e tela "desligada no servidor"; pausar N
  h → fila vazia até lá; continuar → `continuarEm` e rodada `pausada_captcha` volta a `ativa`; membro →
  403 nas escritas e 200 no estado; MCP → `somente_humano` + `publicacao_recusada`; `version_conflict`;
  revert de config só dono.
- [x] T047 [US3] SPA: `pages/configuracoes/Coleta.tsx` (`/app/configuracoes/coleta`, `ownerOnly` no
  `nav.ts` grupo Configurações "Coleta de mercado"): bloco de risco com o texto de `docs/decisoes/
  coleta-mercado.md` resumido e o botão "Aceito o risco" (AlertDialog; grava); interruptor desabilitado até
  o aceite; janelas (`DateTimeField`/hora), tetos e pausas; "Pausar por N horas"; "Continuar" (visível em
  `pausada_*`); clientes (criar → token em modal `no-store` com "copiei"; rotacionar/suspender/revogar com
  AlertDialog); estado (último contato, páginas e imagens de hoje, rodada atual, "desligada no servidor");
  rodadas e eventos recentes (DataTable); guia de instalação (link para o README do coletor). Membro: só o
  bloco de estado (reusa o bloco `coleta` de `/api/integracoes`).
- [x] T048 [US3] `e2e/mercado.spec.ts` (US3): dono vê o aviso, ligar sem aceite é recusado, aceita, cria
  token (modal mostra uma vez), liga; `/coleta-e2e/semear` funciona; desliga → `GET /api/coleta/fila` com
  o token de e2e vem vazia; membro não vê os controles. Sino recebe `coleta_captcha` quando o fake envia o
  evento.

**Checkpoint:** US1–US3 verdes. **Sonda com o dono (X1–X4, X6; quickstart §2)** pode acontecer aqui:
preencher `INTERCEPTAR` e ajustar os parsers de `tiktok_shop/1` com os campos reais do Affiliate Center;
registrar no `research.md` R4 o que foi observado (sem URL com parâmetros, sem dado pessoal).

---

## Phase 6: User Story 4 - Acompanhar produtos por perfil, com categorias do nicho (Priority: P2)

**Objetivo:** interesses com origem, categorias do nicho, vitrine para todos, relacionados automáticos,
cadência e a trilha que monta a fila com revezamento.

**Independent Test:** spec US4 (2 perfis, rankings da união, vitrine para ambos, link manual, produto fora
do ranking há 8 dias vira semanal sem perder foto).

- [x] T049 [US4] `apps/api/src/sociman_api/mercado/cadencia.py` (puro): `calcular(produto, interesses,
  ultimo_ranking_em, novo_em_alta, hoje) -> (calor, fotos_por_dia, proxima_coleta_em)` com `QUENTE_DIAS`,
  `SAI_DO_RANKING_DIAS`, `ESFRIAR_DIAS`; manual/vitrine sempre quente; 2/dia para manual e novo em alta;
  avaliações (1ª visita `AVALIACOES_PAGINAS_1A_VISITA`, depois `AVALIACOES_CADA_DIAS`) e vídeos
  (`VIDEOS_CADA_DIAS`) só em quente. `tests/unit/test_mercado_cadencia.py`: transições do estado
  "Produto (calor)" do data-model, SC-005 (volta a quente no mesmo dia).
- [x] T050 [US4] `apps/api/src/sociman_api/mercado/interesses.py`: `acompanhar_por_link` (resolve/cria o
  produto do lago pela fonte; interesse `manual` ativo; 409 `interesse_duplicado`), `acompanhar_produto`,
  `pausar`, `reativar`, `encerrar` (qualquer humano; MCP → `somente_humano`), `revert` (só dono),
  `config_perfil` (`categoria_ids` ≤ `CATEGORIAS_MAX` → 400 `categorias_maximo`; `lojas_seguidas`;
  `max_relacionados_dia`; só dono), `seguir_loja`/`deixar_de_seguir` (qualquer humano), `vitrine_para_todos`
  (interesses `vitrine` com `perfil_id NULL`, sem duplicar), `relacionados_automaticos(perfil, hoje)`
  (produtos com `primeira_vez_em` ≤ `NOVO_DIAS` de `lojas_seguidas`/`categoria_ids`, até
  `max_relacionados_dia`, autor `system:mercado`, notificação `mercado_interesse_auto` 1/dia). Tudo com
  `history.record`.
- [x] T051 [US4] `apps/api/src/sociman_api/mercado/fila.py` (R12): `montar_fila_do_dia(db, hoje)`: para
  cada nível de FR-026 (1 manual/vitrine; 2 novos de lojas seguidas; 3 rankings da união das categorias
  por tipo e janela; 4 quentes; 5 semanais (`morna`); 6 lojas e categorias; 7 vídeos; 8 avaliações),
  **mais as tarefas de página sem perfil** (`perfil_id NULL`, entram no revezamento como um perfil a mais):
  `vitrine` todo dia no nível 1 e `categorias` a cada `CATEGORIAS_CADA_DIAS = 7` no nível 6 (FR-008; chave
  e URL do data-model); candidatos agrupados por perfil em ordem fixa
  (`perfis.created_at`, nulo por último) e **intercalados um a um** (revezamento), produto comum entra uma
  vez; corta no orçamento (`paginas_dia − páginas de hoje`); `INSERT … ON CONFLICT DO NOTHING` em
  `mercado_fila` (idempotente); sobras não viram linha; `devolver_leases_vencidos`, `expirar_dia_anterior`
  (→ `expirada`; prioridade 0 no dia seguinte), `abortar_sem_batimento` (`COLETA_SEM_BATIMENTO_MIN`).
  `tests/unit/test_mercado_fila_revezamento.py`: SC-010 (3 perfis, fila 3×, cada um ≥ ⌊n/3⌋−1 por nível,
  nenhum produto comum duas vezes; perfil nulo entra como um a mais).
- [x] T052 [US4] `apps/api/src/sociman_api/mercado/trilha.py` (`rodar(db)`: recalcula cadência de todos
  os produtos não parados + reativa os que reapareceram; `vitrine_para_todos`; `relacionados_automaticos`
  por perfil; `montar_fila_do_dia`; `devolver_leases_vencidos`; `expirar_dia_anterior`;
  `abortar_sem_batimento`; `coleta_parada` quando ligada e sem `gravado` há `COLETA_PARADA_H`; **nenhum
  DELETE**; `ociosa()` com motivo quando `COLETA_HABILITADA=false`), `agendador.py` (`Trilha("mercado",
  s.agendador_mercado_s, mercado.trilha.rodar, ociosa)`), `test_agendador_sem_trilha_nova` += `"mercado"`
  (ativar o acréscimo da T021). `docker compose restart agendador` depois.
- [x] T053 [P] [US4] `apps/api/tests/integration/test_mercado_trilha.py`: US4 inteira com o `coletor_fake`
  (2 perfis; rankings da união; vitrine `perfil_id NULL` para ambos; link manual; produto fora do ranking
  há 8 d → `morna` com fotos intactas; 31 d → `parada`; reaparece → `quente`); relacionados até o limite +
  1 notificação por dia; leases vencidos voltam; expirados; rodada sem batimento → `interrompida`;
  `coleta_parada` após 48 h; trilha ociosa com `COLETA_HABILITADA=false`; nada apagado (contagens antes e
  depois).
- [x] T054 [US4] `mercado/router_perfil.py` (`mercado_interesses_listar`, `mercado_interesses_criar`,
  `mercado_perfil_config_ler`, `mercado_perfil_config_atualizar`, `mercado_lojas_seguir`,
  `mercado_lojas_deixar_de_seguir`) e `mercado/router.py` (acréscimo: `mercado_interesses_atualizar`,
  `mercado_interesses_revert`, `mercado_interesses_versions`, `mercado_categorias_listar`); `mcp/mapa.py`:
  leituras (`mercado_interesses_listar`, `mercado_perfil_config_ler`, `mercado_categorias_listar`) →
  `TOOLS` leitura; escritas → `PROIBIDAS`. `npm run gen:contract`.
- [x] T055 [P] [US4] `apps/api/tests/integration/test_mercado_interesses.py`: criar por link (produto novo
  no lago), duplicado → 409, membro pausa/encerra/segue loja, MCP → `somente_humano`, revert só dono,
  `categorias_maximo`, config só dono, histórico e `version_conflict`.
- [x] T056 [US4] SPA: `pages/perfis/tabs/MercadoTab.tsx` (`?aba=mercado`: categorias do nicho com seletor
  da taxonomia (`mercado_categorias_listar`, até 5, só dono edita), lojas seguidas, lista de
  acompanhamentos com origem/situação/ações pausar-reativar-encerrar (AlertDialog), "Acompanhar por link"
  (`Field` URL), aviso de relacionados do dia); `pages/mercado/abas/Acompanhamentos.tsx` (todos os perfis,
  filtro por perfil/origem); botão "Acompanhar neste perfil" no `ProdutoMercado.tsx` (seletor de perfil).
- [x] T057 [US4] `e2e/mercado.spec.ts` (US4): dono escolhe 2 categorias; cola um link → interesse manual
  aparece; membro pausa e reativa; `/coleta-e2e/semear` com vitrine → interesse "vitrine" em ambos os
  perfis; MCP (via `openshorts-fake`) não cria interesse.

**Checkpoint:** US4 verde; a fila real do dia é gerada pela trilha no dev (`docker compose logs agendador`).

---

## Phase 7: User Story 5 - Ficha completa, lojas, rankings, avaliações e vídeos no detalhe (Priority: P2)

**Objetivo:** o detalhe mostra ficha versionada, galeria, rankings com variação, vídeos top e avaliações
(sem nome); abas Lojas e Rankings; seguir loja.

**Independent Test:** spec US5 (ficha + 6 imagens + 2 rankings + 3 vídeos + 5 avaliações; título mudou →
nova versão; avaliação sem nome).

- [x] T058 [US5] `mercado/consulta.py` (acréscimo, só SELECT): `fichas_produto` (versões por
  `hash_conteudo`), `galeria` (imagens da ficha atual + anteriores, URLs `/img` do imgproxy pelo
  `object_key` `mercado/…`), `rankings_produto` e `listar_rankings` (variação `entrou|saiu|subiu|caiu|novo`,
  melhor posição, dias no topo), `videos_produto`, `avaliacoes_produto` (filtros `nota`, `comFotos`; nunca
  expõe `autor_hash`), `listar_lojas` e `detalhe_loja` (indicadores de loja do `calculo.py`),
  `listar_categorias`.
- [x] T059 [US5] `mercado/router.py` (acréscimo: `mercado_produtos_fichas`, `mercado_produtos_rankings`,
  `mercado_produtos_videos`, `mercado_produtos_avaliacoes`, `mercado_rankings_listar`,
  `mercado_lojas_listar`, `mercado_lojas_detalhe`) + schemas; `mcp/mapa.py`: todas → `TOOLS` leitura.
  `npm run gen:contract`.
- [x] T060 [P] [US5] `apps/api/tests/integration/test_mercado_detalhe.py`: ficha mudada cria versão e a
  anterior continua; galeria com 6 imagens deduplicadas; rankings com variação entre 2 dias; vídeos com
  `autorHandle` e contadores, sem outros campos; avaliações sem `autor_hash`/nome e com `imagens` (fotos de
  clientes) presentes; loja com GMV estimado = soma dos produtos; categorias em árvore.
- [x] T061 [US5] SPA: `ProdutoMercado.tsx` ganha as seções Ficha (atributos em tabela, argumentos,
  variantes, selos; "Ver versões anteriores"), Galeria (`/img` com `AssetFile.link` estável; lightbox
  simples), Rankings (tabela com setas de variação), Vídeos (lista com @ e contadores; link externo
  `rel=noopener`), Avaliações (nota, data, texto escapado, miniaturas; sem autor); `pages/mercado/abas/
  Rankings.tsx` (seletor categoria × tipo × janela × dia; Δ posição) e `abas/Lojas.tsx` (cartão da loja,
  "Seguir loja neste perfil").
- [x] T062 [US5] `e2e/mercado.spec.ts` (US5): detalhe com ficha, galeria (6 miniaturas carregadas pelo
  `/img`), rankings com variação, vídeos e avaliações sem nome; aba Lojas → seguir loja para o perfil 1 →
  aparece em `MercadoTab`.

---

## Phase 8: User Story 6 - Adotar um produto do mercado no catálogo e ler pelo MCP (Priority: P3)

**Objetivo:** "Adotar no catálogo" cria o produto da 012 com ficha e imagens copiadas e o vínculo; o MCP
lê o cockpit e é recusado em qualquer escrita.

**Independent Test:** spec US6. **Pré-condição:** a 012 mesclada nesta branch (`produtos/` e migration
`0022` presentes) e a coluna `produtos.mercado_produto_id` criada (T006 a cria quando a tabela existe;
se a 0025 já rodou sem ela, criar `0026_mercado_produto_vinculo` só com a coluna, a FK e o índice).

- [x] T063 [US6] (completa em 2026-10-09 depois do merge da 012; migration `0026_uniao_mercado`) `apps/api/src/sociman_api/mercado/adotar.py`: `adotar(db, actor, mercado_produto_id,
  perfil_id)` (RequireHuman): lê a ficha atual e a galeria; copia os bytes das imagens para `images`
  do perfil (kind `produto`, via `imaging.validate_image` + `storage.put` no bucket `imagens`, prefixo do
  perfil); chama `produtos.service.create` da 012 com `nome` = título, `categoria` = caminho,
  `url_loja`, `obs` = argumentos, até 6 variantes, e `mercado_produto_id`; `history.record` da 012 com
  `details.origem = "mercado_026"` e `details.mercadoProdutoId`; cria interesse `manual` se não existir;
  409 `ja_adotado {produtoId}` se já há produto do perfil com o vínculo; 409 `passo_indisponivel` se a 012
  não existe no banco.
- [x] T064 [US6] `mercado/router.py` (acréscimo `mercado_produtos_adotar`, **Hu**); `mcp/mapa.py` →
  `PROIBIDAS`; `npm run gen:contract`. `apps/api/tests/integration/test_mercado_adotar.py`: cria o produto
  da 012 com 100% das imagens copiadas e o vínculo (SC-009), 2ª adoção → 409 com o id, MCP → recusado, sem
  012 → `passo_indisponivel`.
- [x] T065 [P] [US6] `apps/api/tests/integration/test_mercado_mcp.py` (com `mcp_helpers.com_mcp`): o
  cliente MCP lista `mercado_produtos_listar`, `mercado_resumo`, `mercado_rankings_listar`,
  `mercado_lojas_listar`, `mercado_categorias_listar`, `mercado_interesses_listar`, `coleta_estado`; é
  recusado em adotar, interesses, config, clientes e ingestão (`escopo_mcp`/`somente_humano`);
  `mcp-tools.json` gerado contém as tools de leitura e nenhuma de escrita.
- [x] T066 [US6] (e2e cobre adotar, link para o catálogo e o aviso de já adotado) SPA: botão "Adotar no catálogo" no `ProdutoMercado.tsx` (seletor de perfil, AlertDialog,
  sucesso → link para o produto da 012; `ja_adotado` → link para o existente); `e2e/mercado.spec.ts`
  (US6): adotar e ver o produto no catálogo do perfil; adotar de novo → aviso.

---

## Phase 9: Polish & Cross-Cutting

- [x] T067 [P] `apps/api/tests/integration/test_mercado_desempenho.py` (FR-050, SC-007): semeia por SQL em
  lote 10× um ano (≈ 1,1 M fotos, 20 k produtos, rankings e interesses) e exige < 2 s em
  `mercado_produtos_listar`, `mercado_resumo`, `mercado_produtos_serie`, `mercado_rankings_listar`,
  `mercado_lojas_listar`; medir isolado (sem e2e em paralelo).
- [x] T068 [P] Revisão de privacidade e logs: `grep` nos logs de um `uma-vez` de teste e no bruto gravado
  por `nome|@|cookie|Authorization` (SC-006, teste automatizado em `apps/coletor/tests/test_log.py` já
  cobre o coletor; adicionar `test_coleta_bruto_sem_pii.py` no servidor sobre o bruto gravado pelo fake).
- [x] T069 [P] Documentação: `CLAUDE.md` do SociMan ganha a seção "Mercado e coleta (desde a spec 026)"
  (pacotes, token, trilha, buckets, kill switch, guardas, armadilhas: HD obrigatório, sessão gráfica,
  `restart agendador`, `restart edge`); `docs/visao.md` item 26 passa a "🚧 implementada na API/SPA"
  com o que falta com o dono (X1–X7); `docs/decisoes/coleta-mercado.md` recebe a data da confirmação do
  dono quando o aceite for clicado.
- [x] T070 [P] `README.md` do coletor revisado com o passo a passo do quickstart §2–§4 e a tabela de códigos
  de erro; `apps/coletor/CHANGELOG.md` com `tiktok_shop/1`.
- [x] T071 (2026-10-09: API 3.311 passaram, só o teste de tempo pré-existente do Descobrir oscilou sob carga; `ruff` limpo na API e no coletor; coletor 90 testes; `gen:contract` + `check:web` ok; e2e `mercado.spec.ts` verde isolado, suíte inteira 99/103 com 2 falhas pré-existentes de carga reexecutadas à parte) Verificação final: `npm run test:api -q` (3171 + os novos; a única falha tolerada é o teste de
  tempo pré-existente do Descobrir, se oscilar), `uv run ruff check .` na API e no coletor, `cd apps/coletor
  && uv run pytest`, `npm run gen:contract && npm run check:web` (contract, typecheck, build, bundle, csp,
  secrets), `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/mercado.spec.ts` e a suíte e2e inteira.
  Conferir o checklist `checklists/requirements.md` e os SC-001..SC-010 contra os testes que os cobrem.
- [ ] T072 Quickstart §2 **com o dono** (X1–X4, X6): instalar, perfil, aceite, token, `uma-vez --limite 1`,
  conferir o bruto e os campos reais, ajustar `INTERCEPTAR`/parsers se preciso (commit separado
  "fix: parsers tiktok_shop/1 com os campos reais"), `--limite 3` com 1 ranking; depois §3 (X5) e a
  observação do 1º e do 2º dia.

---

## Dependencies & Execution Order

- **Phase 1:** T001 (gate) → T002, T003, T004, T005 em paralelo.
- **Phase 2** bloqueia tudo: T006 → T007; T008 e T009 depois de T006; T010, T011 em paralelo; T012 →
  T013 → T014; T015 (depende de T010) → T016 (depende de T008, T009, T013, T015) → T017 → T018; T019
  depois de T018; T020 depois de T019; T021 depois de T013 e T015; T022 em paralelo.
- **US1 (Phase 3):** T023 → T024 (paralelo com T025); T025 depois de T010 e T008; T026 depois de T023 e
  T025 → T027 (gen:contract) → T028 e T029 → T030; T031 depois de T018 → T032 depois de T029, T030, T031.
- **US2 (Phase 4):** independente da US1 (só da Phase 2): T033 → T034, T035 → T036 → T037 e T038 → T039 →
  T040 → T041 e T042; T043 depois de T017 e T018.
- **US3 (Phase 5):** depende da Phase 2 (T009, T013): T044 → T045 (gen:contract) → T046, T047 → T048
  (depende de T031).
- **US4 (Phase 6):** depende da US1 (cálculo para "novo em alta") e da Phase 2: T049 → T050 → T051 → T052
  → T053; T054 depois de T050 (gen:contract) → T055 e T056 → T057.
- **US5 (Phase 7):** depende da US1: T058 → T059 (gen:contract) → T060 e T061 → T062.
- **US6 (Phase 8):** depende da US5 e **da 012 mesclada**: T063 → T064 → T065 e T066.
- **Serialização:** `gen:contract` (T027, T045, T054, T059, T064); arquivos compartilhados (`mcp/mapa.py`:
  T027, T045, T054, T059, T064; `main.py`: T013, T018, T026; `router.py` do mercado: T026, T054, T059,
  T064; `e2e/mercado.spec.ts`: T032, T048, T057, T062, T066; `nav.ts`: T029, T047); e2e pela trava.
- **Phase 9** no fim; T072 só com o dono e depois de T071.

### Paralelismo sugerido (agentes)

- **Frente A (API, lago e leitura):** T006, T008, T010, T015, T023, T025, T026, T049–T052, T054, T058,
  T059, T063, T064.
- **Frente B (coleta: token, portão, ingestão, gestão):** T009, T011–T013, T016–T018, T022, T044, T045.
- **Frente C (coletor no host):** T033–T042 (pacote isolado; só o contrato o liga ao resto).
- **Frente D (testes e guardas):** T007, T014, T019–T021, T024, T028, T043, T046, T053, T055, T060, T065,
  T067, T068.
- **Frente E (SPA e e2e):** T029–T032, T047, T048, T056, T057, T061, T062, T066.
- **Frente F (infra e docs):** T002–T005, T069, T070.

## Implementation Strategy

- **MVP:** Phase 2 + US1 + US2 + US3. É o que permite a **sonda real com o dono** (quickstart §2): a
  ingestão recebe, o coletor navega e devolve, a tela liga com aceite e token, e o cockpit mostra o cartão.
  Sem a sonda, os parsers de `tiktok_shop/1` ficam com o `INTERCEPTAR` vazio: a US1 e a US3 são validadas
  com o coletor falso, e a US2 com o servidor sintético.
- **Depois:** US4 (interesse, cadência e fila real pela trilha) e US5 (detalhe completo) em paralelo; US6
  por último, **só depois do merge da 012**.
- **Checkpoints:** depois da Phase 2, da US1, da US3 (com a sonda, se o dono estiver disponível), da US4,
  da US5 e no fim (T071). Commit só quando o dono pedir, em pt-BR no imperativo.
