# Tasks: Revisão de UX tela a tela (024-revisao-ux)

**Input**: `specs/024-revisao-ux/` (plan.md, spec.md, research.md, data-model.md, contracts/api-024.md,
contracts/ui-024.md, quickstart.md)

**Tests**: obrigatórios pela constitution (princípio VI): testes de contrato da API (pytest), e2e ajustados e o novo
`e2e/layout-ritmo.spec.ts`.

**Format**: `- [ ] Tnnn [P?] [USn?] Descrição com caminho`. Caminhos relativos à raiz do SociMan; `web/` =
`apps/web/src/`, `api/` = `apps/api/src/sociman_api/`, `tests/` = `apps/api/tests/`.

**Regras de execução (CLAUDE.md e handoff):**
- Um passo por vez, verificando cada um.
- O dono usa o dev ao vivo: rota ou campo novo só entra no SPA depois de existir na API.
- e2e só com `flock /tmp/sociman-e2e.lock npm run test:e2e [-- arquivo]`; a suíte completa roda com o código
  congelado.
- Depois de mudar a API: `npm run gen:contract`.
- Commit só quando o dono pedir; `docs/insumos/` e `.impeccable/` ficam fora.

---

## Phase 1: Setup

- [X] T001 Confirmar com o dono que as mudanças sem commit da spec 021 já foram commitadas (`git status --short` limpo, fora de `docs/insumos/` e `.impeccable/`). Se não foram, criar a worktree `024-revisao-ux` (skill `superpowers:using-git-worktrees`) e trabalhar nela.
- [X] T002 Rodar a linha de base: `npm run check:web` e `flock /tmp/sociman-e2e.lock npm run test:e2e -- layout.spec.ts conteudos.spec.ts mcp.spec.ts`, e registrar o resultado em `specs/024-revisao-ux/checklists/linha-de-base.md` (o que já falhava antes da 024).

---

## Phase 2: Foundational (bloqueia todas as histórias)

- [X] T003 Criar `web/components/shell/Page.tsx` (`<div className="flex min-w-0 flex-col gap-6">`, com `className` extra opcional) e exportá-lo junto dos outros componentes de `components/shell/`.
- [X] T004 [P] Criar `web/components/shell/EmptyState.tsx` (props `titulo`, `descricao?`, `acao?: ReactNode`, `icone?: LucideIcon`; título com `role="status"`; `py-10 text-center`, ícone `text-muted-foreground`), conforme contracts/ui-024.md.
- [X] T005 [P] Mover o `useFiltroUrl()` de `web/components/conteudos/FiltrosConteudos.tsx` para `web/lib/filtros.ts`, com prefixo opcional de chave (ex.: `reg_`), e atualizar os imports em `lib/analytics.ts`, `lib/aprendizado.ts`, `components/metricas/RankingTable.tsx` e `components/metricas/ContaMetricas.tsx`.
- [X] T006 [P] Em `e2e/helpers.ts`: criar `nav(page, label)`, que acha o link no `navigation "Menu principal"` e, se ele estiver dentro de um grupo com `aria-expanded="false"`, clica no botão do grupo antes; criar também `preencherData(locator, iso)`, que digita `dd/mm/aaaa`. Remover as cópias locais de `nav()` em `e2e/mcp.spec.ts:35`, `e2e/cortes-openshorts.spec.ts:42`, `e2e/importacao.spec.ts:17` e `e2e/conteudos.spec.ts:199` e importar do helper.

**Checkpoint:** `npm run check:web` verde; e2e de mcp, cortes-openshorts, importacao e conteudos verdes com o helper novo.

---

## Phase 3: User Story 1 — Menu agrupado (P1) 🎯 MVP

**Goal:** menu com os grupos Cortes, Analytics e Configurações, colapsáveis e lembrados (FR-001..007).
**Independent Test:** como dono e como membro, abrir e fechar grupos, recarregar e navegar no desktop e no celular.

- [X] T007 [US1] Em `web/components/shell/nav.ts`: criar `NavGroup = { id: "cortes"|"analytics"|"config", label, icon, itens: NavItem[] }` e `navTree`, na ordem do FR-001 (Início, Perfis, Cortes[Canais-fonte, Descobrir, Gerar cortes], Conteúdos, Calendário, Propostas dos agentes, Analytics[Métricas, Aprendizado → `/app/aprendizado`, Importar da agência], Configurações[Assistente de IA, Usuários, Segurança, Publicação automática, Agentes (MCP)], Minha conta). Manter `navItems` como o achatamento de `navTree`, para o `navItemFor()`.
- [X] T008 [US1] Em `web/components/shell/Sidebar.tsx`: renderizar o `NavGroup` com `Collapsible` (`components/ui/collapsible.tsx`), botão com o nome do grupo, `aria-expanded` e `aria-controls`. Lembrar o estado em `localStorage["sociman:menu:grupos"]` (JSON `{id: boolean}`, try/catch em leitura e escrita). Padrão: cortes e analytics abertos, config fechado. O grupo com a rota ativa abre sozinho. Filtrar `ownerOnly` antes e esconder o grupo vazio. O contador de propostas continua no item. O `MobileSidebar` usa o mesmo `SidebarContent`.
- [X] T009 [US1] Garantir que `/app/aprendizado` exista antes do item do menu: se a US3 ainda não estiver feita, o item "Aprendizado" fica atrás de uma flag local em `nav.ts` até a T030. Registrar a decisão no commit.
- [X] T010 [US1] Atualizar `e2e/layout.spec.ts`: `OWNER_ITEMS` com os itens visíveis, mais casos novos (abrir e fechar grupo; o fechado continua fechado depois de reload; abrir uma rota de Configurações abre o grupo; o membro não vê os itens só do dono e Configurações mostra só o Assistente de IA; o drawer do celular tem os grupos e fecha ao navegar). Conferir `e2e/propostas.spec.ts:122` (contador).
- [X] T011 [US1] Rodar `flock /tmp/sociman-e2e.lock npm run test:e2e -- layout.spec.ts propostas.spec.ts` e `npm run test:e2e:pwa`, ambos verdes.

---

## Phase 4: User Story 2 — Espaçamento, cartões e larguras (P1)

**Goal:** ritmo único, faixa sem vazio nem encosto, cor da marca nos dois temas, 1440 px (FR-028..033, FR-038).
**Independent Test:** `e2e/layout-ritmo.spec.ts` (SC-002..004) nas telas Agentes, Propostas, Gerar cortes, Conteúdos, Descobrir e Perfil.

- [X] T012 [US2] Escrever `e2e/layout-ritmo.spec.ts` (deve falhar antes da T013..T020). Em 1280 e 390 px, mede por `boundingBox()`:
  - os espaços entre filhos diretos do `Page` (diferença ≤ 4 px entre telas, nunca 0);
  - a largura igual dos cartões empilhados;
  - a distância faixa→corpo ≤ 16 px;
  - `scrollWidth <= clientWidth`.
  Telas: `/app/configuracoes/agentes`, `/app/propostas`, `/app/envios`, `/app/conteudos`, `/app/descobrir` e `/app/perfis/:id`, com dados semeados pelos helpers existentes.
- [X] T013 [US2] Em `web/components/shell/AppShell.tsx`: envolver o `<Outlet>` do `<main>` em `<div className="mx-auto w-full max-w-[1440px]">`; em `web/index.css`: `html { scrollbar-gutter: stable; }`.
- [X] T014 [US2] Refazer a estrutura de `web/components/shell/HeaderCard.tsx` sem mudar o visual: `<section className="min-w-0 pt-6">` → cartão `rounded-xl bg-card shadow-card` → faixa `-mt-6 mx-4 rounded-lg px-4 py-4 sm:px-5` → corpo `px-5 pt-4 pb-5` (e `footer`). Tirar `mt-6`, `relative -top-6` e `-mb-2`. Apagar os comentários sobre `mt-6` em `web/pages/perfis/tabs/CortesTab.tsx:125` e `web/pages/perfis/tabs/FontesTab.tsx:70`.
- [X] T015 [US2] Em `web/index.css`: criar os tokens `--band`, `--band-light` e `--band-foreground`, iguais nos temas claro e escuro (primário do tema claro `oklch(0.52 0.2 266)`, `oklch(0.66 0.16 258)` e branco); o `@utility tone-primary` passa a usar esses tokens; no `.dark`, `--dark`/`--dark-light` escuros (sem cinza-claro) e `--dark-foreground` claro. Conferir contraste ≥ 4.5:1 do texto da faixa nos dois temas.
- [X] T016 [US2] Trocar `tone="dark"` (15 usos) e `tone="info"` (3) por `primary` (ou omitir) nos HeaderCards de `web/pages/**` e `web/components/**` (inventário: ContaMetricas, Account, AnalisesIa, Recomendacoes, Temas, Agentes, Home, ResumoTab, VideoMetricas, FontesTab, Propostas, SecurityEvents, CortesTab, _Showcase). `destructive`, `warning` e `success` só onde já indicam estado.
- [X] T017 [P] [US2] Em `web/components/ui/card.tsx`: padding e gap iguais ao corpo do HeaderCard (`gap-4 py-5`; `px-5` no `CardHeader`, `CardContent` e `CardFooter`; `CardTitle` com `text-lg font-semibold`).
- [X] T018 [P] [US2] Em `web/components/ui/tabs.tsx`: `Tabs` com `gap-6` por padrão e `TabsContent` com `flex flex-col gap-6`; tirar os `className="gap-2"`/`"gap-4"` locais (`web/pages/envios/EnviosList.tsx:72`, `web/pages/configuracoes/Agentes.tsx:47`) e os `space-y-6` de `TabsContent` (`Agentes.tsx:52`).
- [X] T019 [US2] Migrar a raiz de toda página para `<Page>`:
  - as 17 com `space-y-6`, as 7 com `space-y-4 aria-live` (manter o `aria-live`), a Home com `space-y-8`, as 14 com `flex flex-col gap-6` e as 6 de `aprendizado/`;
  - as abas de Analytics com `gap-4` (Contas, Curvas, OQueFunciona, VisaoGeral, Alertas, Funil) passam a `gap-6`;
  - as grades de raiz (Mercado, QuandoPostar, Publico, PadroesCorteTab, MarcaTab, GuiaTab) ficam dentro de `<Page>` com `gap-6`.
  Lista completa no inventário de research.md R2.
- [X] T020 [US2] Remover os limites de largura de cartões e seções: `web/pages/configuracoes/Agentes.tsx:116`, `web/pages/configuracoes/Publicacao.tsx:89,174`, `web/pages/perfis/ContasTab.tsx:385,468`, `web/pages/Home.tsx:110`, `web/pages/Account.tsx:56` e `web/pages/perfis/PerfilNovo.tsx:96` (formulários longos podem limitar só os campos internos, nunca o cartão). Diálogos e sheets ficam como estão.
- [X] T021 [US2] Rodar `layout-ritmo.spec.ts` (verde) e a suíte e2e das telas tocadas; ajustar asserções de heading afetadas (`analytics.spec.ts:26`, `analytics-p23.spec.ts:159,172`).

---

## Phase 5: User Story 3 — Perfil enxuto e Aprendizado como página (P2)

**Goal:** sem a aba Cortes; upload com marca e estado do HD em Conteúdos; Aprendizado em `/app/aprendizado` com redirects; cabeçalho compacto (FR-008..014, FR-040).
**Independent Test:** quickstart §2 itens 3, 4 (upload) e 5.

- [X] T022 [US3] Criar `web/components/conteudos/AplicarMarcaDialog.tsx` a partir do `CorteUpload` e do `StorageCard` de `web/pages/perfis/tabs/CortesTab.tsx`. Título "Aplicar marca num corte". Campo Perfil (NativeSelect; pré-escolhido pelo filtro `perfil` da URL ou pelo único perfil). Estado do HD (`api.armazenamento()` só com o diálogo aberto; HD indisponível → envio bloqueado com a mesma mensagem). Arquivo e gancho, pela mesma `uploadCorte(perfilId, …)`. Ao concluir: toast e invalidação da lista de conteúdos.
- [X] T023 [US3] Em `web/pages/conteudos/Conteudos.tsx`: botão "Aplicar marca num corte" nas ações do cabeçalho, que abre o `AplicarMarcaDialog`.
- [X] T024 [US3] Em `web/pages/perfis/PerfilDetalhe.tsx`:
  - remover a aba `cortes` do array `tabs`;
  - `?aba=cortes` → `<Navigate replace to={/app/conteudos?perfil=<id>}>`;
  - remover o botão "Aprendizado" do cabeçalho;
  - mostrar o banner só se `perfil.banner` existir (sem ele, o cabeçalho é a linha de identidade, sem `h-36 sm:h-48`);
  - lista de abas com rolagem horizontal, máscara de fade nas bordas (`mask-image`) e `scrollIntoView` da aba ativa.
  Apagar `web/pages/perfis/tabs/CortesTab.tsx` (o `MarcaTab` continua com `api.cortes.list(..., limit 1)`).
- [X] T025 [US3] Atualizar os e2e que enviavam corte pela aba Cortes (`e2e/assistente-ia.spec.ts:369`, `e2e/fundo.spec.ts:148`, `e2e/marca.spec.ts:113`) para usar o diálogo de Conteúdos, e acrescentar em `e2e/conteudos.spec.ts` o caso "HD indisponível bloqueia o envio", se o fake permitir (senão, cobrir em teste de componente via e2e com interceptação de `/api/armazenamento`).
- [X] T026 [US3] Em `web/App.tsx`: rota lazy `/app/aprendizado`, que renderiza `pages/aprendizado/Aprendizado.tsx`; `/app/perfis/:id/aprendizado` vira um componente que faz `<Navigate replace>` para `/app/aprendizado?perfil=:id&<query original>`.
- [X] T027 [US3] Em `web/pages/aprendizado/Aprendizado.tsx`:
  - ler o perfil de `?perfil=` (via `lib/filtros.ts`) em vez de `useParams`;
  - seletor de perfil no topo, junto de conta e medida;
  - sem `perfil`, usar `localStorage["sociman:aprendizado:perfil"]` (try/catch) ou o único perfil;
  - sem nenhum perfil, `EmptyState` com o link "Novo perfil";
  - perfil inexistente ou arquivado → o erro de hoje;
  - gravar o perfil escolhido.
- [X] T028 [US3] Em `web/lib/aprendizado.ts`: `aprendizadoPath(perfilId, aba?, extra)` → `/app/aprendizado?perfil=<id>&aba=…`; conferir os usos em `pages/metricas/VideoMetricas.tsx:82`, `pages/analytics/abas/OQueFunciona.tsx:276`, `abas/Analise.tsx:146,164`, `abas/AnalisesIa.tsx:165` e `components/aprendizado/SinaisDistribuicao.tsx:178`.
- [X] T029 [US3] Atualizar `e2e/aprendizado.spec.ts:104,106,124` para o novo endereço e acrescentar os casos "link antigo com aba/conta/medida redireciona preservando a query" e "item Analytics › Aprendizado abre com o último perfil".
- [X] T030 [US3] Tirar a flag da T009: o item "Aprendizado" aparece no grupo Analytics. Rodar `flock … test:e2e -- aprendizado.spec.ts conteudos.spec.ts marca.spec.ts fundo.spec.ts assistente-ia.spec.ts layout.spec.ts`.

---

## Phase 6: User Story 4 — Pontuação explicada no Descobrir (P2)

**Goal:** tema e motivo na linha; diálogo com afinidade, temas e escala; a soma fecha (FR-015..017).
**Independent Test:** quickstart §2 item 6; teste de contrato da soma.

- [X] T031 [P] [US4] Teste de contrato em `tests/integration/test_024_descobrir.py` (falha antes da T032..T034):
  - vídeo com 2 temas casados → `afinidade.temas` com 2 itens, decisivo primeiro;
  - perfil sem taxonomia → `afinidadeEstado = {ativa: false, motivo: "sem_temas"}` e `temas = []`;
  - casamento desatualizado → `motivo = "desatualizada"`;
  - soma das parcelas (`100×peso×nota` das 4, ×0,3 se `jaCortado` para o perfil, mais `afinidade.pontos`, limitada a 0..100) = `score` ±1;
  - sem `perfilId` → `motivo = "sem_perfil"`.
- [X] T032 [US4] Em `api/aprendizado/afinidade.py`:
  - `TemaAfinidade` ganha `acao: Literal["ampliar","cortar"] | None` (a partir de `prefs.efetivas`);
  - nova `temas_por_video(db, valores, video_ids) -> dict[uuid, list[TemaCasado]]` (consulta a `FonteTema` por `perfil_id` + `video_fonte_id IN ids`, mapeada em `valores.temas`; `pontos = round(a×20, 1)`; `decisivo` pelo critério do `_ordem`; ordem: decisivo, |pontos| desc, nome);
  - nova `estado(db, perfil_id) -> (ativa, motivo)` com `"sem_perfil"|"sem_temas"|"desatualizada"|"neutra"|None`.
- [X] T033 [US4] Em `api/canais/schemas.py`: `TemaCasado {temaId, nome, pontos: float, acao: "ampliar"|"cortar"|None, decisivo: bool}`, `AprendizadoAfinidade.temas: list[TemaCasado] = []` e `AfinidadeEstado {ativa: bool, motivo: "sem_perfil"|"sem_temas"|"desatualizada"|"neutra"|None}` e `VideosList.afinidade_estado: AfinidadeEstado | None = None`. Em `api/canais/service_videos.py` (`list_videos`/`videos_out`): uma chamada a `temas_por_video` por página (só quando `valores` não é `None`) e o `afinidade_estado` preenchido. Só importar `aprendizado.afinidade` (guarda `tests/unit/test_constitution_guards.py:1293`).
- [X] T034 [US4] Rodar `npm run test:api -- tests/integration/test_024_descobrir.py tests/integration/test_aprendizado_descobrir.py tests/integration/test_aprendizado_desempenho_perf.py tests/integration/test_descoberta.py tests/unit/test_constitution_guards.py` e `npm run gen:contract`.
- [X] T035 [US4] Em `web/pages/descobrir/Descobrir.tsx`: na coluna "Vídeo", selo neutro com o nome do tema decisivo (o selo "tema cortado" atual continua) e o `scoreReason` em texto `text-xs text-muted-foreground` visível também no desktop.
- [X] T036 [US4] Em `web/components/canais/ScoreReason.tsx`:
  - coluna "Nota (0 a 1)";
  - linha "Já cortado para este perfil (×0,3)" quando houver;
  - linha "Afinidade (tema e canal)" com `afinidade.pontos`;
  - lista "Temas casados" (nome, pontos, ação, destaque do decisivo);
  - sem afinidade, o texto do `afinidadeEstado.motivo` ("Sem temas neste perfil", "Casamento de temas desatualizado", "Afinidade neutra");
  - total = `score`.
  Ajustar `web/lib/canais.ts` se precisar de rótulos.
- [X] T037 [US4] Em `e2e/cortes-openshorts.spec.ts` (ou `e2e/aprendizado.spec.ts`, onde já há afinidade semeada): caso que abre "Por quê?" e confere a linha de afinidade e o tema na linha.

---

## Phase 7: User Story 5 — Contagens por geração (P2)

**Goal:** aceitos, pendentes, arquivados e com falha por geração (FR-018, FR-019; clarify Q4).
**Independent Test:** quickstart §2 item 7.

- [X] T038 [P] [US5] Teste de contrato em `tests/integration/test_024_envios.py`: geração com cortes em `revisao` (2), `pronto` (2), `na_fila` (1), `falhou` (1) e 1 arquivado → `cortesResumo = {aceitos: 3, pendentes: 2, falhou: 1, arquivados: 1}`; geração sem cortes → `null`; arquivar um corte muda a contagem no `GET /api/envios` seguinte; o `GET /api/envios/{id}` traz o mesmo resumo.
- [X] T039 [US5] Em `api/envios/schemas.py`: `CortesResumo {aceitos, pendentes, falhou, arquivados: int}` e `Envio.cortes_resumo: CortesResumo | None = None`. Em `api/envios/service_envios.py` (`envios_out`): um `select(Corte.envio_id, count().filter(...)…).where(Corte.envio_id.in_(ids)).group_by(Corte.envio_id)` com as regras do data-model (aceitos = não arquivado e status `na_fila|processando|pronto`; pendentes = `revisao` não arquivado; falhou = `falhou` não arquivado; arquivados = `archived_at IS NOT NULL`).
- [X] T040 [US5] Rodar `npm run test:api -- tests/integration/test_024_envios.py tests/integration/test_selecao.py tests/integration/test_enviar.py tests/integration/test_importacao.py` e `npm run gen:contract`.
- [X] T041 [US5] Em `web/components/envios/EnvioStatus.tsx` e `web/lib/envios.ts`: abaixo do estado, "3 aceitos · 2 pendentes · 1 arquivado · 1 com falha" (só os não zero; pendentes em destaque de atenção). Em `web/pages/envios/EnvioDetalhe.tsx`: o mesmo resumo no `dl`, substituindo o "N em revisão" duplicado.
- [X] T042 [US5] Em `e2e/cortes-openshorts.spec.ts`: depois de importar os clipes do fake, conferir "N pendentes" na lista de Gerações; aplicar a marca num clipe e conferir "1 aceito".

---

## Phase 8: User Story 6 — Paginação numerada em Conteúdos (P2)

**Goal:** páginas numeradas com página e tamanho na URL (FR-020..022).
**Independent Test:** quickstart §2 item 4 (paginação).

- [X] T043 [P] [US6] Teste de contrato em `tests/integration/test_024_conteudos.py`:
  - com 60 conteúdos, `offset` 0/25/50 e `limit=25` cobrem os 60 sem repetir, nas duas ordens (`recentes`, `agenda`);
  - `offset` + `cursor` → 400 `paginacao_invalida`;
  - `offset` além do total → `items=[]` e `total=60`.
- [X] T044 [US6] Em `api/conteudos/router.py`: query `offset: Annotated[int | None, Query(ge=0)] = None`; em `api/conteudos/service.py` (`list_conteudos`): sem cursor, aplicar `.offset(offset)`; com os dois → `ApiError(400, "paginacao_invalida", "Use offset ou cursor, não os dois.")`. Atualizar a `descricao` da tool em `api/mcp/mapa.py`, se ela citar a paginação. Rodar `npm run test:api -- tests/integration/test_024_conteudos.py tests/integration/test_conteudos.py tests/integration/test_escala_conteudos.py tests/unit/test_mcp_mapa.py` e `npm run gen:contract`.
- [X] T045 [US6] Criar `web/components/data-table/ServerPagination.tsx` (props `total`, `pagina`, `tamanho`, `onPagina`, `onTamanho`), no visual do `ClientPagination` de `DataTablePagination.tsx`: "N itens", select "Itens por página" (10, 25, 50), "Página X de Y", botões "Página anterior" e "Próxima página". A `DataTable` aceita `pagination={{ modo: "servidor", ... }}`.
- [X] T046 [US6] Em `web/lib/conteudos.ts`: `useConteudos` com `useQuery` e `offset = (pagina-1)*tamanho`, `limit = tamanho` (padrão 25). Em `web/pages/conteudos/Conteudos.tsx`:
  - `pagina` e `tamanho` na URL;
  - mudar filtro ou ordem apaga `pagina`;
  - `pagina > ceil(total/tamanho)` → `replace` para a última;
  - a seleção em lote é limpa a cada troca de página;
  - trocar o `CursorPagination` pelo `ServerPagination`.
- [X] T047 [US6] Atualizar `e2e/conteudos.spec.ts:341,345` ("Carregar mais" → "Próxima página") e acrescentar os casos: voltar do detalhe mantém a página e os filtros; mudar filtro volta à página 1; página fora do intervalo cai na última.

---

## Phase 9: User Story 7 — Barra de filtros única (P3)

**Goal:** a mesma `FilterBar` em toda lista com filtro, com estado na URL e aplicação imediata (FR-034, FR-025; clarify Q1).
**Independent Test:** quickstart §2 item 9, em cada tela do inventário.

- [X] T048 [US7] Criar `web/components/data-table/FilterBar.tsx` (contracts/ui-024.md):
  - `principais` (até 3 controles com `Field`/`NativeSelect` rotulados, mais a busca "Buscar" com debounce de 300 ms);
  - `mais` (aberto por "Mais filtros (N)" num `Sheet` lateral; `side="bottom"` em < sm);
  - `ativos: {chave, rotulo, valor, limpar}[]` como etiquetas `Badge` com o botão "Remover filtro: <rótulo>";
  - "Limpar filtros" quando houver algum ativo.
  Ela entra no slot `toolbar` da `DataTable` (`web/components/data-table/DataTable.tsx`), que deixa de desenhar a própria busca quando recebe `FilterBar`.
- [X] T049 [P] [US7] Teste de contrato em `tests/integration/test_024_anotacoes.py`: `q` acha por trecho sem acento e sem caixa; `q` vazio → igual a hoje; `q` > 100 caracteres → 400 `validation_error` (o handler do app converte 422).
- [X] T050 [US7] Em `api/anotacoes/router.py` e `api/anotacoes/service.py` (`listar`): query `q: str | None` (1..100) com `ILIKE` sem acento em `texto` (mesmo helper do `q` de conteúdos). Rodar `npm run test:api -- tests/integration/test_024_anotacoes.py tests/unit/test_mcp_mapa.py` e `npm run gen:contract`.
- [X] T051 [P] [US7] Migrar Propostas (`web/pages/propostas/Propostas.tsx`): `FilterBar` (principais: Buscar, Perfil, Situação; mais: Autor, Tipo), estado na URL, sem botão "Filtrar" e sem a busca local da DataTable (busca no servidor por `q`).
- [X] T052 [P] [US7] Migrar Conteúdos (`web/components/conteudos/FiltrosConteudos.tsx`, `web/pages/conteudos/Conteudos.tsx`): a `FilterBar` dentro do cartão da tabela (principais: Buscar, Perfil, Estado; mais: Conta, Plataforma, Origem, Ordem, Arquivados, Agendado de/até, Criado de/até).
- [X] T053 [P] [US7] Migrar Descobrir (`web/pages/descobrir/Descobrir.tsx`): o seletor de perfil continua no cartão "Cortar para o perfil"; a `FilterBar` no cartão "Vídeos recomendados" (principais: Buscar, Canal, Ordenar; mais: Período, Duração e os 3 checkboxes).
- [X] T054 [P] [US7] Migrar Gerar cortes (`web/pages/envios/EnviosList.tsx`): o Perfil vai para a linha das abas, à direita; Gerações com `FilterBar` (Buscar, Status) e o status na URL.
- [X] T055 [P] [US7] Migrar Canais-fonte (`web/pages/canais/CanaisList.tsx`), Perfis (`web/pages/perfis/PerfisList.tsx`) e Usuários (`web/pages/Users.tsx`, só a busca local): estado na URL.
- [X] T056 [P] [US7] Migrar Calendário (`web/pages/calendario/Calendario.tsx`) e Analytics (`web/components/analytics/FiltrosGlobais.tsx`, `web/components/metricas/RankingTable.tsx`, `web/components/metricas/FiltroContas.tsx`, `web/components/metricas/ContaMetricas.tsx`): `FilterBar` com os atalhos de período como principal. Manter os nomes de parâmetro de hoje (os e2e de analytics dependem deles).
- [X] T057 [P] [US7] Migrar Aprendizado (conta e medida em `web/pages/aprendizado/Aprendizado.tsx`; arquivados e tema em `web/pages/aprendizado/abas/Temas.tsx`).
- [X] T058 [P] [US7] Migrar Segurança (`web/pages/SecurityEvents.tsx`), Registro da IA (`web/pages/ia/RegistroTab.tsx`, prefixo `reg_`) e Registro do MCP (`web/components/mcp/RegistroChamadasTable.tsx`, prefixo `reg_`): sem "Filtrar", estado na URL.
- [X] T059 [P] [US7] Migrar Cenas (`web/pages/perfis/tabs/CenasTab.tsx`), Assets (`web/components/assets/AssetFilters.tsx`, `web/pages/perfis/tabs/AssetsTab.tsx`; os chips de tipo e tag viram etiquetas da FilterBar com o mesmo rótulo de grupo "Filtrar por tipo"/"Filtrar por tag") e Importação (`web/components/importacao/ItensImportacao.tsx`, `web/components/importacao/PreviaTabela.tsx`; manter o rótulo "Filtrar por situação").
- [X] T060 [US7] Atualizar os e2e da tabela do contracts/ui-024.md: `cenas.spec.ts:211-219,395`, `mcp.spec.ts:265,272`, `security-events.spec.ts:17` (sem "Filtrar"), `layout.spec.ts:107` (searchbox "Buscar") e conferir `assets.spec.ts:333`, `assets-escala.spec.ts:36`, `importacao.spec.ts:39`, `analytics*.spec.ts` e `conteudos.spec.ts:288-300`. Acrescentar em `e2e/propostas.spec.ts`: filtro em "Mais filtros" vira etiqueta; remover pela etiqueta; recarregar mantém o filtro.

---

## Phase 10: User Story 8 — Vazios e ajustes pontuais (P3)

**Goal:** Propostas, Agentes, atalhos, barra fixa, datas, arquivos e vazios (FR-023, FR-024, FR-026, FR-027, FR-035..037; clarify Q3).
**Independent Test:** quickstart §2 itens 1 (parte), 4 (atalhos), 8 e 10.

- [X] T061 [US8] Em `web/components/data-table/DataTable.tsx`: `emptyMessage: ReactNode` e prop `empty?: ReactNode` (renderizada no lugar da célula de texto, com `EmptyState`).
- [X] T062 [US8] Em `web/pages/propostas/Propostas.tsx`, dois vazios:
  - sem filtro ativo e lista vazia → `EmptyState` "Ainda não chegou nenhuma proposta", com o texto "Propostas são sugestões dos agentes da agência (OpenClaw). Elas só chegam depois que os agentes forem ligados ao SociMan pelo MCP, e nada muda até alguém aplicar." e, só para o dono, a ação "Configurar agentes (MCP)" → `/app/configuracoes/agentes`;
  - com filtro → "Nenhuma proposta com estes filtros" e o botão "Limpar filtros".
  Acrescentar os dois casos em `e2e/propostas.spec.ts` (dono e membro).
- [X] T063 [US8] Em `web/pages/configuracoes/Agentes.tsx`:
  - o Interruptor vira uma faixa compacta em largura total (switch, selo do servidor ligado/desligado, link "Histórico"); o `Alert` só quando desligado (tom `warning`);
  - "Novo cliente" vai para as `actions` do HeaderCard;
  - o título "Clientes" vira "Agentes conectados", e a tabela `aria-label` vira "Agentes conectados (MCP)".
  Atualizar `e2e/mcp.spec.ts:40`.
- [X] T064 [US8] Em `web/components/conteudos/AtalhosConteudos.tsx`:
  - mostrar só os atalhos com contagem > 0 ou ativos na URL;
  - botão "Ver todos os atalhos" (estado local) que mostra os 11;
  - sem nenhum, a linha "Nada pedindo ação agora";
  - grade `grid-cols-[repeat(auto-fill,minmax(10rem,1fr))]`.
  Conferir `e2e/conteudos.spec.ts:288-300` (`atalho=` na URL).
- [X] T065 [US8] Em `web/pages/descobrir/Descobrir.tsx:553`: a barra de selecionados passa de `fixed inset-x-4 … lg:left-80` para `sticky bottom-4` dentro do `Page` (mantendo o `pb-24` da raiz), alinhada às bordas do conteúdo.
- [X] T066 [US8] Criar `web/components/ui/date-field.tsx`:
  - `DateField`: `input type="text" inputMode="numeric"` com máscara `dd/mm/aaaa`, validação de data real, `value`/`onChange` em ISO `YYYY-MM-DD`, botão "Abrir calendário" que chama `showPicker()` de um `input type=date` oculto (sem suporte, o botão some);
  - `DateTimeField` (`dd/mm/aaaa hh:mm` ↔ `YYYY-MM-DDTHH:mm`).
  Mesmo `id`/rótulo do `Field` para o `getByLabel`.
- [X] T067 [US8] Migrar os 18 `type="date"` (RegistroTab, SecurityEvents, NovoClienteDialog, RegistroChamadasTable, FiltrosConteudos, SequenciaDialog, ExportarDialog, ContaMetricas, RankingTable, FiltrosGlobais) e os 2 `datetime-local` (`web/pages/calendario/Calendario.tsx:610`, `web/components/.../AgendarDialog.tsx:371`) para `DateField`/`DateTimeField`; ajustar os e2e que fazem `fill("YYYY-MM-DD")` para usar `preencherData` (`e2e/helpers.ts`).
- [X] T068 [P] [US8] Criar `web/components/ui/file-field.tsx` (input oculto; botão "Escolher arquivo"; texto "Nenhum arquivo escolhido" ou o nome; aceita soltar; repassa `accept`, `multiple` e `ref`) e migrar os 10 `type="file"` (FontesTab, ProfileImagePicker, EnvioArquivos, AvulsoDialogs, Tomadas, VideoProprioDialog, NovoAssetMenu, AssetUpload, ImageUpload, AplicarMarcaDialog). Os e2e com `setInputFiles` continuam funcionando no input oculto (conferir).
- [X] T069 [P] [US8] Trocar as datas formatadas com `Intl.DateTimeFormat`/`toLocale*` ad hoc (37 arquivos, `grep -rn "toLocale\|Intl.DateTimeFormat" web/pages web/components`) pelos helpers de `web/lib/tz.ts` (`formatDateTime`, `formatLongDate`, `formatTime`, `formatAgo`), salvo os gráficos do ECharts (locale próprio).
- [X] T070 [US8] Trocar os ~51 vazios ad hoc (`>Nenhum…`, `>Sem …`, `>Nada …` em `web/pages` e `web/components`) por `EmptyState` ou `DataTable.empty`, mantendo o texto (os e2e procuram por ele), incluindo `web/pages/envios/EnviosList.tsx:111`.

---

## Phase 11: Polish e verificação final

- [X] T071 Atualizar o `CLAUDE.md` do SociMan (seção Frontend): `Page`, `FilterBar`, `ServerPagination`, `EmptyState`, `DateField`/`FileField`, tons da faixa (`--band`), limite de 1440 px, menu em `navTree` e o helper `nav()` dos e2e. Atualizar o `docs/design/layout-referencia.md` com o ritmo (`gap-6` entre blocos, `px-5`/`gap-4` dentro do cartão).
- [X] T072 Rodar `npm run gen:contract`, `npm run check:web` e `docker compose exec api uv run ruff check .`.
- [X] T073 Com o código congelado: `npm run test:api` e `flock /tmp/sociman-e2e.lock npm run test:e2e`, depois `npm run test:e2e:pwa`. Tudo verde (SC-010), comparado com a linha de base da T002.
- [X] T074 Capturas com o Playwright MCP em 1280 e 390 px, temas claro e escuro, de Agentes, Propostas, Gerar cortes, Conteúdos, Descobrir, Perfil, Aprendizado e o menu (aberto e fechado).
- [X] T075 Rodar `/impeccable critique` nas mesmas telas (dual-agent) e o agente `impeccable:impeccable-finish-reviewer`: nota ≥ 30/40 e nenhum P0 (SC-009). Corrigir os achados P0/P1 numa só rodada e confirmar com, no máximo, mais uma.
- [ ] T076 Roteiro manual do quickstart §2 com o dono no app de dev; registrar o resultado em `specs/024-revisao-ux/checklists/quickstart-dono.md`.

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → **Foundational (T003–T006)** → histórias.
- **US1 (menu)** e **US2 (layout)** são P1 e independentes entre si; o item "Aprendizado" do menu espera a US3 (T009/T030).
- **US2** antes das telas que mudam layout (US3, US7, US8), para não refazer a raiz duas vezes.
- **API antes do SPA** em cada história: T031–T034 → T035–T037; T038–T040 → T041–T042; T043–T044 → T045–T047; T049–T050 → T051.
- **US7 (FilterBar)** depende da US6 (Conteúdos paginado), porque os dois mexem em `Conteudos.tsx`. Para a T052, fazer a T046 antes.
- **US8**: a T061 vem antes das T062 e T070; a T066 antes da T067; a T068 depois da T022 (o `AplicarMarcaDialog` usa o `FileField`).
- **Polish** só com tudo pronto; a T073 roda com o código congelado.

### Parallel Opportunities

- Foundational: T004, T005 e T006 juntos.
- US2: T017 e T018 juntos, depois da T014.
- Testes de contrato da API (T031, T038, T043, T049) podem ser escritos juntos, e as fatias de API (US4, US5, US6, US7-API) não tocam os mesmos arquivos.
- US7: T051–T059 em paralelo (arquivos diferentes), todas depois da T048.
- US8: T068 e T069 em paralelo com a T066/T067.

```text
# Exemplo: API das quatro histórias em paralelo (agentes separados, arquivos disjuntos)
T031+T032+T033 (canais/, aprendizado/afinidade.py)
T038+T039     (envios/)
T043+T044     (conteudos/)
T049+T050     (anotacoes/)
→ um único npm run gen:contract no fim (evita corrida nos arquivos gerados)
```

## Implementation Strategy

- **MVP = US2 + US1** (P1): resolve a queixa central (ritmo, faixa, larguras) e o menu. Já dá para validar com o
  `layout-ritmo.spec.ts` e mostrar ao dono.
- **Incremento 2:** US3 (Perfil e Aprendizado) e US6 (paginação), que mudam rotas e o uso diário.
- **Incremento 3:** US4 e US5 (explicações e contagens).
- **Incremento 4:** US7 (FilterBar em todas as telas), a maior em arquivos, feita em lote paralelo.
- **Incremento 5:** US8 e o polish, com o critique final.
- Ao fim de cada incremento: suítes das telas tocadas verdes e uma parada para o dono olhar no dev.
