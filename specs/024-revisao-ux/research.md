# Research: 024-revisao-ux

Linha de base: critique do impeccable de 2026-10-06 (`.impeccable/critique/2026-10-07T02-14-59Z__apps-web-src-pages.md`,
24/40) e inventário do código em 2026-10-07. Cada decisão abaixo responde a um ponto do plano.

## R1. Menu agrupado
- **Decisão:** `nav.ts` passa a exportar `navTree: (NavItem | NavGroup)[]`, em que `NavGroup = { id, label, icon,
  itens: NavItem[] }`. A lista plana `navItems` continua derivada (achatada) para o `navItemFor()` do breadcrumb.
  O `Sidebar` renderiza o grupo com o `Collapsible` que já existe em `components/ui/collapsible.tsx` (Radix:
  `aria-expanded` e teclado já vêm prontos). O estado fica em `localStorage["sociman:menu:grupos"]` (JSON
  `{id: boolean}`), com leitura e escrita em try/catch. O grupo da rota atual abre por cima do estado lembrado.
  O padrão da primeira visita é Cortes e Analytics abertos, Configurações fechado. O grupo some quando o
  filtro de papel o deixa vazio.
- **Por quê:** é o componente Radix que já existe (princípio VIII). O `navItemFor` e o `aria-current` continuam
  como estão.
- **Alternativas:** o `sidebar` do shadcn (componente novo e grande, rejeitado); rótulos sem colapsar
  (rejeitado pelo dono).
- **e2e:** um helper `nav(page, label)` em `e2e/helpers.ts` abre o grupo do item quando ele está fechado e
  substitui as quatro cópias locais. O `layout.spec.ts` ganha os casos de grupo e de lembrança.

## R2. Ritmo e contêiner de página (FR-028, FR-029, FR-032, FR-033)
- **Decisão:**
  - `AppShell`: o `<main>` ganha um filho `mx-auto w-full max-w-[1440px]`.
  - `html { scrollbar-gutter: stable }` no `index.css`.
  - Novo `components/shell/Page.tsx` (`<div className="flex min-w-0 flex-col gap-6">`), que toda página usa como
    raiz no lugar de `space-y-*`, `flex flex-col gap-*` e `grid` de raiz (25 páginas com `space-y`, 26 com
    `gap`).
  - `Tabs` com `gap-6` por padrão em `components/ui/tabs.tsx`, e o `TabsContent` sempre `flex flex-col gap-6`.
  - As abas de Analytics com `gap-4` passam a `gap-6`. Grades de cards lado a lado continuam com `gap-6`.
- **Por quê:** a margem colapsada só existe porque o espaço mora no cartão. Com `gap` no contêiner, o espaço
  fica previsível e mensurável (SC-002).
- **Alternativas:** corrigir página a página (a causa voltaria a cada tela nova).

## R3. Cartão com faixa (FR-030)
- **Decisão:** a estrutura do `HeaderCard` muda, e o visual continua:
  - um invólucro `<section className="pt-6">`, com padding, que não colapsa;
  - o cartão;
  - a faixa com `-mt-6 mx-4` (sobe sobre a borda como hoje, mas ocupa o padding do invólucro);
  - o corpo com `px-5 pt-4 pb-5`.
  Sai o `mt-6`, sai o `relative -top-6 -mb-2` e some o vazio de 16 px. O espaço entre o bloco de cima e o topo
  da faixa passa a ser o `gap-6` da página. Os comentários de CortesTab e FontesTab sobre o `mt-6` vão embora.
- **Card do shadcn:** `components/ui/card.tsx` passa a usar o mesmo interno (`gap-4 py-5`, `px-5` no header e no
  content). Os dois "dialetos" ficam com o mesmo padding e a mesma tipografia de título (`text-lg font-semibold`
  no Card e `text-lg font-bold` na faixa).
- **Alternativas:** abolir a faixa (rejeitado pelo dono); manter o `mt-6` e proibir `space-y` (frágil).

## R4. Tons (FR-031)
- **Decisão:** o tom padrão é `primary` (já é o default). Os 15 usos de `tone="dark"` e os 3 de `info` viram
  `primary`. `destructive`, `warning` e `success` ficam reservados para estado (ex.: Interruptor desligado,
  falha). No tema escuro, o `--primary` (0.72) leva texto escuro. Para a faixa ficar igual nos dois temas, o
  `tone-primary` passa a usar tokens próprios (`--band`, `--band-light` e `--band-foreground`), com o
  primário do tema claro (0.52) e texto branco nos dois temas. `tone-dark` continua existindo para o `MetricCard`, mas com `--dark` escuro também no tema
  escuro (deixa de ser cinza-claro).
- **Verificação:** contraste de texto da faixa ≥ 4.5:1 nos dois temas (conferido no quickstart).

## R5. Barra de filtros única (FR-034, clarify Q1)
- **Decisão:**
  - Novo `components/data-table/FilterBar.tsx`, que entra no slot `toolbar` da `DataTable` ou no topo do cartão
    quando a tela não é tabela. Props:
    - `principais` (até 3 controles visíveis, com rótulo);
    - `mais` (os outros, num `Sheet` lateral que já existe; no celular, tela cheia);
    - `ativos: {chave, rotulo, valor, limpar}[]`.
  - Os ativos aparecem como etiquetas (`Badge` + botão "Remover filtro X"), e o botão "Mais filtros (N)"
    mostra a contagem. "Limpar filtros" aparece quando há algum ativo.
  - A aplicação é imediata. O texto tem debounce de 300 ms, como hoje em Descobrir e Conteúdos.
- **Estado no endereço:** o `useFiltroUrl()` sai de `FiltrosConteudos.tsx` para `lib/filtros.ts` e é reusado.
  As telas com estado local (Propostas, SecurityEvents, Registro da IA, Registro do MCP, Cenas, Assets,
  Canais-fonte, Perfis, Gerações, Importação, Aprendizado/Temas) passam a guardar os filtros no endereço. O
  Registro do MCP e o Registro da IA vivem dentro de abas: a chave do filtro ganha prefixo para não colidir
  (ex.: `reg_cliente`).
- **Telas (inventário de 2026-10-07):** Descobrir, Propostas, Conteúdos, Gerar cortes (seletor de perfil e
  Gerações), Canais-fonte, Calendário, Analytics (`FiltrosGlobais`, ranking, contas), Aprendizado (conta,
  medida e Temas), Segurança, Registro da IA, Registro do MCP, Cenas, Assets, Perfis, Importação (itens e
  prévia), Usuários (só busca).
- **Busca da DataTable:** a busca embutida (`search`, só nas linhas carregadas) sai das telas com dados do
  servidor e vira busca no servidor quando a rota tem `q`. Telas com tudo carregado (Usuários, Importação)
  mantêm a busca local, dentro da FilterBar.
- **Alternativas:** Popover (não existe em `ui/`, seria componente novo); filtros inline sem "Mais" (11
  controles em Conteúdos não cabem no celular, SC-008).

## R6. Propostas: busca única (FR-025)
- **Decisão:** parâmetro novo e opcional `q` (≤ 100) em `GET /api/anotacoes`, com `ILIKE` sem acento em
  `texto`, no mesmo padrão do `q` de conteúdos. A busca local da DataTable e o botão "Filtrar" saem.
- **MCP:** o `anotacoes_list` já é tool de leitura. O parâmetro novo vira entrada da tool automaticamente
  (`ferramentas.py` lê o OpenAPI); sem mudança no `mapa.py` (nenhum operationId novo, contagens do
  `test_escopos` iguais).

## R7. Paginação numerada de Conteúdos (FR-020, FR-021)
- **Decisão:** parâmetro novo e opcional `offset` (≥ 0) em `GET /api/conteudos`. `offset` e `cursor` juntos →
  400 `paginacao_invalida`. O `total` já existe e a ordem já é determinística (`chave, id`).
- **SPA:** `useConteudos` troca para `useQuery` com `offset = (pagina-1)*tamanho`. `pagina` e `tamanho` (10, 25 ou 50;
  padrão 25) ficam na URL. Mudar filtro ou ordem apaga `pagina`. Página além da última → `replace` para a
  última, quando `total` chega. O novo `components/data-table/ServerPagination.tsx` reaproveita o visual do
  `ClientPagination` ("N itens", tamanho, "Página X de Y", Anterior/Próxima). A seleção em lote é limpa a cada
  troca de página.
- **Custo:** o `count` já é feito hoje. Com offset de até ~100 páginas de 25, não é preciso nada novo.
- **Alternativas:** páginas por cursor sem total (não dá "Página X de Y").

## R8. Contagem por geração (FR-018, FR-019, clarify Q4)
- **Decisão:** o `Envio` ganha `cortesResumo: { aceitos, pendentes, arquivados, falhou } | null`, preenchido por
  um `GROUP BY envio_id` com `count(*) FILTER (...)` dentro de `envios_out` (que já busca outras coisas em lote).
  - aceitos = `archived_at IS NULL AND status IN (na_fila, processando, pronto)`;
  - pendentes = `status = revisao AND archived_at IS NULL`;
  - falhou = `status = falhou AND archived_at IS NULL`;
  - arquivados = `archived_at IS NOT NULL`.
  Quando não há nenhum corte, o campo é `null`. O `EnvioStatus` da lista mostra o estado e, abaixo, "3 aceitos ·
  2 pendentes · 1 arquivado" (só os não zero). O detalhe repete o resumo no `dl`.
- **Alternativas:** calcular no SPA pelo detalhe (N chamadas, rejeitado).

## R9. Tema e motivo no Descobrir (FR-015..017)
- **Decisão:**
  - `AprendizadoAfinidade` ganha `temas: list[TemaCasado] = []` (`temaId`, `nome`, `pontos` (a×20, arredondado),
    `acao` (`ampliar`, `cortar` ou `null`), `decisivo: bool`). A busca vem de uma consulta extra por página,
    `afinidade.temas_por_video(db, valores, video_ids)`, que mora em `aprendizado/afinidade.py` por causa da
    guarda de import (`test_constitution_guards.py:1293`). O `TemaAfinidade` ganha `acao`.
  - O `VideosList` ganha `afinidadeEstado: { ativa: bool, motivo: "sem_temas" | "desatualizada" | "neutra" | null }`,
    para o diálogo explicar a afinidade neutra.
  - O `ScoreDetail` não muda.
  - A composição exibida no diálogo é: 4 linhas (v, e, r, d) com `100×peso×nota`; a linha "Já cortado para este
    perfil (×0,3)", quando houver `jaCortado`; a linha "Afinidade (tema/canal)" com `pontos`; e o total, limitado a
    0..100. A soma confere com o `score` dentro de ±1.
  - A coluna "Nota" vira "Nota (0 a 1)".
- **Linha:** um selo com o nome do tema decisivo (cor neutra; o tema cortado continua com o selo de alerta atual)
  e o `scoreReason` (o motivo resumido, que já existe) visível também no desktop, numa linha de texto pequeno
  abaixo do título.
- **Desempenho:** a consulta extra é uma busca por chave primária (`perfil_id`, `video_fonte_id`) para ≤ 50 ids.
  O `test_aprendizado_desempenho_perf.py` continua valendo como guarda.

## R10. Aprendizado como página (FR-010..012)
- **Decisão:**
  - Rota `/app/aprendizado`, com o perfil em `?perfil=`. O componente atual é reaproveitado, lendo o perfil da
    query em vez de `:id`.
  - Sem `perfil`: usa o último lembrado (`localStorage["sociman:aprendizado:perfil"]`, com try/catch) ou o único
    perfil; se não houver nenhum, mostra o vazio com o link "Novo perfil".
  - O seletor de perfil fica no topo, junto dos filtros de conta e medida (na FilterBar).
  - `/app/perfis/:id/aprendizado` vira um `<Navigate replace>` que preserva a query
    (`?perfil=id&aba&conta&medida`).
  - O `aprendizadoPath(perfilId, aba, extra)` passa a gerar o novo endereço, então todos os links internos
    mudam juntos.
  - O botão "Aprendizado" sai do cabeçalho do perfil.

## R11. Perfil sem a aba Cortes (FR-008, FR-009, FR-013, FR-014)
- **Decisão:**
  - A aba `cortes` sai do `PerfilDetalhe`. `?aba=cortes` vira `Navigate replace` para
    `/app/conteudos?perfil=<id>`.
  - O `CorteUpload` e o `StorageCard` passam para `components/conteudos/AplicarMarcaDialog.tsx`: o botão
    "Aplicar marca num corte" no cabeçalho de Conteúdos abre um diálogo com a escolha de perfil (pré-escolhido
    pelo filtro, se houver um), o estado do HD (`api.armazenamento()`, só enquanto o diálogo está aberto),
    o arquivo e o gancho. A rota `cortes_upload` não muda.
  - A tabela de cortes do perfil sai.
  - O banner do perfil só aparece quando `perfil.banner` existe. Sem ele, o cabeçalho é a linha de identidade.
  - As abas do perfil no celular ganham rolagem com máscara de fade nas bordas (CSS `mask-image`) e rolam até a
    aba ativa.
- **e2e:** `assistente-ia.spec.ts:369`, `fundo.spec.ts:148` e `marca.spec.ts:113` usam a aba Cortes para enviar
  um corte. Passam a usar o diálogo de Conteúdos.

## R12. Datas e arquivos em pt-BR (FR-036)
- **Contexto:** o `<html lang="pt-BR">` já existe, mas o Chromium desenha o `input type=date` na língua do
  sistema operacional (mm/dd/yyyy na máquina do dono). Não dá para forçar isso por atributo.
- **Decisão:**
  - Novo `components/ui/date-field.tsx`: um `<input type="text" inputMode="numeric">` com máscara `dd/mm/aaaa`,
    validação e valor ISO para fora. Um botão de calendário abre um `input type=date` oculto com
    `showPicker()`, com queda para digitar quando o navegador não suportar.
  - Variante `DateTimeField` para os 2 `datetime-local`.
  - Novo `components/ui/file-field.tsx`: input oculto, botão "Escolher arquivo" e o nome escolhido ou "Nenhum
    arquivo escolhido". Também aceita arrastar e soltar.
  - Os 18 campos de data e os 10 de arquivo migram. Os rótulos acessíveis continuam (os e2e usam
    `getByLabel`).
  - As datas exibidas com `Intl` ad hoc (37 arquivos) passam pelos helpers de `lib/tz.ts`.
- **Por quê:** nenhuma dependência nova (o `react-day-picker` do Calendar do shadcn seria uma).

## R13. Estados vazios (FR-024, FR-037)
- **Decisão:**
  - Novo `components/shell/EmptyState.tsx` com título, descrição opcional, ação opcional e ícone. A
    `DataTable.emptyMessage` passa a aceitar `ReactNode`, e há uma prop `empty` para o `EmptyState`.
  - Propostas:
    - sem nenhuma proposta e sem filtro → "Ainda não chegou nenhuma proposta", explicação dos agentes do
      OpenClaw e, para o dono, o link "Configurar agentes (MCP)";
    - com filtro → "Nenhuma proposta com estes filtros" e o botão "Limpar filtros".
  - Os ~51 textos ad hoc de vazio passam a usar o componente.

## R14. Agentes (MCP) (FR-026, FR-027)
- **Decisão:**
  - O cartão do Interruptor vira uma faixa compacta em largura total: switch, selo "Servidor ligado/desligado"
    e "Histórico". O `Alert` aparece só quando está desligado (tom `warning`).
  - "Novo cliente" vai para as `actions` do `HeaderCard`.
  - O título "Clientes" vira "Agentes conectados", e a tabela fica "Agentes conectados (MCP)". O e2e
    `mcp.spec.ts:40` (`table "Clientes MCP"`) muda junto.
  - Também saem os `max-w-*` de Publicação, ContasTab, Home e Account (lista no inventário).

## R15. Atalhos de Conteúdos (FR-023, clarify Q3)
- **Decisão:** o `AtalhosConteudos` filtra os itens com `contagem > 0` ou que estão ativos na URL. O botão "Ver
  todos os atalhos" expande a grade completa (estado local). Sem nenhum item, mostra "Nada pedindo ação agora".
  A grade usa `grid-cols-[repeat(auto-fill,minmax(10rem,1fr))]`.

## R16. Barra fixa do Descobrir (FR-035)
- **Decisão:** a barra fica `sticky bottom-4` dentro do contêiner da página (no lugar de `fixed`), e assim herda
  a largura e o alinhamento do conteúdo, inclusive o limite de 1440 px. O `pb-24` da raiz continua para não
  cobrir a última linha.

## R17. Verificação de layout (SC-002..004, SC-008)
- **Decisão:** um e2e novo, `e2e/layout-ritmo.spec.ts`, com dados semeados, em 1280 e 390 px, mede por
  `boundingBox()`:
  - o espaço entre os filhos diretos do `Page` (tolerância de 4 px);
  - nenhum encosto (0 px);
  - a largura dos cartões empilhados;
  - a distância da faixa até o corpo do cartão;
  - a ausência de rolagem horizontal;
  - o primeiro item de Conteúdos visível em até 1,5 altura de tela no celular.
  Telas: Agentes, Propostas, Gerar cortes, Conteúdos, Descobrir e Perfil.
- **Depois:** as capturas do Playwright MCP e o agente `impeccable-finish-reviewer` (SC-009 ≥ 30/40).
