# Research: 029 AI Studio

Fase 0 do plan. Cada decisão traz o porquê e as alternativas descartadas. Achados do código conferidos em 2026-10-09.

## R1. "Perfil base" = a coluna `perfil_id` que passa a aceitar nulo (sem renomear)
- **Decisão:** `assets`, `cenas`, `produtos` e `vozes` mantêm a coluna `perfil_id`, agora `NULL`-ável. O significado muda de "dono" para "perfil base". Na API, o campo continua `perfilId` (anulável).
- **Por quê:** a coluna aparece em dezenas de consultas (assets, cenas, produtos, vozes, ia, anotações, mídia, agência). Renomear dobraria o diff sem mudar comportamento. Os índices `(perfil_id, archived_at, updated_at)` continuam servindo ao filtro de perfil base.
- **Alternativas:** renomear para `perfil_base_id` (churn sem ganho); tabela de ligação item × perfis (fora do que o dono pediu: o perfil base é um só).

## R2. `perfil_id` imutável vira editável e versionado
- **Decisão:**
  - `cenas` e `produtos` tiram `perfil_id` de `__immutable_fields__` e o põem em `__versioned_fields__`;
  - `assets` e `vozes` ganham `perfil_id` em `__versioned_fields__`;
  - a mudança passa pelo PATCH normal (dono e membro, Clarification 3) e o revert do dono a desfaz (princípio VII).
- **Cuidados:**
  - o revert de uma versão com um perfil base hoje arquivado é aceito (o item pode ter perfil arquivado, FR-010 só recusa na geração);
  - a anotação (009) do item segue o perfil do item: a lista "por perfil" das propostas usa o perfil base atual.

## R3. Tabelas de apoio com `perfil_id` obrigatório

| Tabela | Hoje | 029 |
|---|---|---|
| `images` (perfis/models) | `perfil_id` NOT NULL, prefixo da chave no MinIO | anulável. Imagem enviada a um item sem perfil vai para `agencia/imagens/<id>`. As chaves antigas não mudam (só leitura pela chave). |
| `audios` (021) | NOT NULL | anulável, mesma regra (`agencia/audios/<id>`) |
| `geracoes` (021) | NOT NULL: "perfil da geração" | anulável: passa a ser o **perfil base usado** (FR-008). `listar` por perfil continua; lista nova por alvo e por agência. |
| `ia_chamadas` (008) | NOT NULL | anulável: o perfil base usado. O resumo de custo agrupa "Sem perfil". |
| `cena_padroes`, `ia_guias`, `brand_kits`, `contas`, `conteudos`, `cortes`, `envios`, aprendizado | NOT NULL | **não mudam**: são do perfil |

- **Por quê:** sem anular `images`/`audios`, um item sem perfil não teria onde guardar o arquivo. Sem anular `geracoes`/`ia_chamadas`, a geração "sem perfil" (FR-009) não teria registro.
- **Alternativa descartada:** um "perfil da agência" oculto, que criaria um perfil falso com guia e kit, apareceria nas listas de perfis e confundiria analytics.

## R4. Resolver o perfil base da geração (FR-008/FR-009/FR-010)
- **Decisão:**
  - o corpo do pedido ganha `perfilBaseId` com três estados: ausente = o do item; `null` = nenhum; um id = aquele perfil;
  - uma função única, `perfis.base.resolver(db, item_perfil_id, pedido)`, devolve o `Perfil | None`;
  - perfil arquivado → 409 `perfil_base_arquivado`.
- **Onde usa:** `geracao/service.pedir` e `criar_para_alvo` (021/012/025), `ia/service.gerar` (008: o `<guia_perfil>` e o `<perfil>` só entram com perfil base; sem ele, só base + regras do tipo), `cenas/service` (padrões e proibidas do perfil base da cena, R7) e `produtos/fluxo` (a ficha pelo Claude usa o guia do perfil base).
- **Registro:** `geracoes.perfil_id` e `ia_chamadas.perfil_id` = o perfil usado, e `guia_perfil_version` já existente. Assim o SC-004 se confere no registro.
- **Alternativa:** guardar só no `params` da geração (não serve para filtrar nem para o resumo de custo).

## R5. Rotas da agência (FR-020) e as rotas por perfil `deprecated`
- **Decisão:**

  | Rota nova | O que faz |
  |---|---|
  | `GET /api/assets` | `tipo`, `perfilId` (uuid ou `sem`), `q`, `tag`, `arquivados`, cursor |
  | `POST /api/assets` e `POST /api/assets/arquivo` | corpo com `perfilId` anulável |
  | `GET/POST /api/cenas` | idem |
  | `GET/POST /api/produtos` | idem, com o multipart da 012 |
  | `GET/POST /api/vozes` | idem |
  | `POST /api/geracoes` | o alvo dá o item, `perfilBaseId` opcional |
  | `GET /api/geracoes?alvoTipo&alvoId` | gerações do item |
  | `POST /api/audios` | envio de áudio sem perfil |

  - As rotas `/api/perfis/{id}/…` continuam com o mesmo comportamento (filtro = aquele perfil; criar = perfil base aquele) e ficam `deprecated` no OpenAPI.
- **operationIds:** `assets_listar_agencia`, `assets_criar_agencia`, `cenas_listar_agencia` etc. Os antigos são mantidos.
- **MCP (`mcp/mapa.py`):** as leituras novas em `TOOLS` (leitura), as escritas em `FORA`. As escritas humanas (`RequireHuman`) de geração continuam em `PROIBIDAS`. O `test_mcp_mapa.py` obriga a classificação.
- **Alternativa:** trocar as rotas por perfil por um redirect 308 (quebraria o MCP e o SPA antigos de uma vez).

## R6. Usos cruzados na cena (FR-011/FR-012)
- **Decisão:**
  - sai a checagem `asset.perfil_id != perfil_id` (`cenas/service.py:136`) e `produto.perfil_id != perfil_id` (`:170`);
  - continuam valendo tipo, arquivado (aviso), produto aprovado com recorte (012) e variante do produto;
  - os padrões (`padroes.efetivos`) e as proibidas (`proibidas_do_perfil`) usam `cena.perfil_id` quando há; sem perfil, `None` (sem padrões nem proibidas) e o aviso `sem_perfil_base` na resposta da cena;
  - o `ia/service` (`:93`, `:138`) deixa de exigir que a cena ou o asset seja do perfil do pedido: o perfil do pedido vira o perfil base resolvido (R4).
- **Conteúdo (014):** `PUT /api/conteudos/{id}/cenas` aceita cena de outro perfil base (FR-014); o histórico do conteúdo continua registrando.

## R7. Unicidade de voz na agência (FR-022, Clarification 1)
- **Decisão:**
  - `uq_vozes_nome` vira `(lower(name)) WHERE archived_at IS NULL`, sem o perfil;
  - a migration resolve os repetidos antes de criar o índice: entre as vozes ativas com o mesmo `lower(name)`, a mais antiga fica e as outras ganham " (2)", " (3)"…;
  - cada ajuste grava uma versão (`action = "updated"`, autor `system:migration`, `details.motivo = "nome_unico_029"`);
  - o `tts_id` não muda (é do id, 025).
- O nome dos assets continua sem unicidade (Assumptions).

## R8. "Onde é usado" e o kit de marca (FR-013/FR-015)
- **Decisão:**
  - `assets/usos.py`, `cenas/usos_assets.py` e os provedores de `geracao/uso.py` passam a listar os usos de todos os perfis, com o nome do perfil de cada uso;
  - o kit de marca (`marca/service_kit.py`) escolhe da biblioteca da agência (`GET /api/assets?tipo=fundo|marca_dagua`); o bloqueio de arquivar em uso no kit continua;
  - a checagem de "imagem do mesmo perfil" no kit sai, e a do `geracao/service.py:147` (referência do mesmo perfil) também: a referência pode ser imagem de qualquer item da biblioteca.

## R9. Contexto de persona do assistente (`ia/contexto._personas`)
- **Decisão:** a lista de avatares do perfil usada nos textos de postagem (008) continua sendo "avatares com perfil base = o perfil da postagem". Avatar sem perfil não entra no contexto automático. Comportamento igual ao de hoje para os dados existentes.

## R10. SPA
- **Decisão:**
  - **Menu:** `nav.ts` ganha o grupo `{ id: "estudio", label: "AI Studio" }` logo depois de "Perfis", com os itens Avatares (`/app/estudio/avatares`), Cenários, Vozes, Produtos, Cenas, Assets e Movimentos (`/app/estudio/movimentos`, página "em breve"). O grupo segue a 024: aberto/fechado lembrado e o grupo da rota abre sozinho.
  - **Listas:** as listas da agência reaproveitam os componentes das abas, que deixam de receber `perfil` obrigatório: `AssetsTab` vira `AssetsLista({ tipos, perfilFiltro })`, e o mesmo vale para `CenasLista`, `ProdutosLista` e `VozesLista`. O filtro "Perfil base" (`NativeSelect` com "Todos", "Sem perfil" e os perfis) fica na `FilterBar`, com o estado em `useFiltroUrl` (`perfil=<id>|sem`).
  - **Formulários e cabeçalhos:**
    - `PerfilBaseField` é usado no criar, no editar e no pedir geração; nesses dois últimos, vem com o texto "Sem perfil base: só as regras do tipo, sem guia";
    - os cabeçalhos de detalhe mostram o perfil base, e o menu marca o item do AI Studio pela rota (o `navItems` ganha os prefixos `/app/assets`, `/app/vozes`, `/app/produtos` e `/app/cenas` → item do tipo).
  - **Criação no lugar (FR-016):** `NovoItemDialog` (avatar, cenário, produto), aberto pelo botão "+ Novo …" ao lado do seletor na nova cena e na edição. Ao salvar, chama o `onCriado(id)`, e o seletor recarrega e escolhe. O estado do formulário da cena não é tocado (o diálogo fica fora do `<form>`).
  - **Perfil e redirecionamentos (FR-018/FR-019):**
    - a página do perfil remove as 4 abas e ganha o card "Ver no AI Studio", com as contagens das listas da agência (`limit=1` + total);
    - `?aba=assets|cenas|produtos|vozes` → `<Navigate>` para a lista com `?perfil=<id>`;
    - `/app/estudio` → `/app/estudio/avatares` (com o perfil lembrado da página provisória, se houver);
    - as rotas `/app/perfis/:id/cenas/nova` e as afins redirecionam para `/app/estudio/cenas/nova?perfil=<id>`.
  - **A página provisória** `pages/estudio/Estudio.tsx` sai.
- **e2e:** `nav(page, rótulo)` já abre o grupo. O `layout.spec.ts` ganha o grupo AI Studio na lista de grupos, e os e2e que usam `?aba=assets|cenas|produtos|vozes` passam a abrir o AI Studio. São eles `assets`, `cenas`, `produtos`, `cadastro-padronizado` e `geracao`.

## R11. Migration e ordem
- **Decisão:**
  - a 029 vem antes da 011 e fica com a **`0024_ai_studio`** (`down_revision = 0023_cadastro_padronizado`);
  - a 011 passa a `0027_roteiros_video_local`, e a correção dos documentos da 011 (gate T001 e `down_revision`) entra na T001 desta spec;
  - o downgrade recusa se houver linha com `perfil_id` nulo (mesmo padrão da 0023).
- **Passos da migration:**
  1. `DROP NOT NULL` nas 8 colunas da R3 e da R1;
  2. desduplicar as vozes (R7) e trocar o índice;
  3. criar `ix_assets_lista_agencia (archived_at, updated_at DESC, id)` e os índices equivalentes em `cenas`, `produtos` e `vozes` para a lista sem perfil (SC-006).

## R12. Desempenho (SC-006)
- **Decisão:** a lista da agência pagina pelo cursor `(updated_at, id)` com o índice novo. O teste semeia 5 mil assets em 3 perfis e exige menos de 1 s na lista sem filtro e com `perfilId=sem`.

## R13. O que não muda (FR-023)
Consentimento e revogação (025: `revogacao.py` não olha perfil), a escolha só humana (`RequireHuman` nas rotas de geração novas), a aprovação de produto (012), a limpeza de 90 dias (021: o `midia_em_uso` não olha perfil) e o princípio I (nenhuma rota nova fala com rede social; há guarda no `test_constitution_guards`).

## R14. Inventário das regras de "mesmo perfil" (T001, 2026-10-09)
Varredura: `grep "perfil_id != | deste perfil | do perfil\" | .perfil_id == perfil_id"` em assets, cenas, produtos, vozes, geracao, ia, marca e anotacoes (73 linhas). O que importa:

| Onde | Regra hoje | Destino | Tarefa |
|---|---|---|---|
| `cenas/service.py:136`, `:170` | avatar/cenário/produto do perfil da cena | **sai** | T028 |
| `cenas/usos.py:85` | cena do mesmo perfil do conteúdo | **sai** (FR-014) | T028 |
| `cenas/usos_assets.py:25`, `assets/usos.py:57/95/101` | usos só no perfil | **vira** todos os perfis, com o nome do perfil | T028 |
| `assets/service_padrao.py:201/207` | prova do consentimento do mesmo perfil | **sai** | T028a |
| `assets/service_padrao.py:284/289` | voz padrão do mesmo perfil | **sai** | T028a |
| `vozes/service.py:258` | gravação (áudio) do mesmo perfil | **sai** | T028a |
| `geracao/service.py:147`, `geracao/aplicadores.py:160-169/186`, `aplicadores_avatar.py:80`, `aplicadores_voz.py:56`, `produtos/aplicadores.py:67` | alvo e referência do perfil do pedido (`validar_alvo(perfil_id, …)`) | **sai**: o alvo vale por si; a referência pode ser qualquer imagem ativa da biblioteca | T021 |
| `ia/service.py:93/138` | cena/asset do perfil do pedido | **sai**: o perfil do pedido vira o perfil base resolvido | T022 |
| `ia/aplicacao.py:90` | chamada do mesmo perfil do alvo | **sai** (C1) | T022 |
| `ia/service.py:182/201/273/479` | conteúdo, conta e postagem do perfil | **fica**: é do perfil do conteúdo | — |
| `ia/contexto.py:113` | personas = avatares do perfil | **fica**: perfil base = perfil da postagem (R9) | — |
| `marca/service_kit.py` (fundo/marca d'água do perfil), `marca/router_marca_dagua.py:80` (rota antiga da 004) | imagem do kit do mesmo perfil | **vira** qualquer imagem da biblioteca (kit); a rota antiga deprecated fica | T032 |
| `anotacoes/service.py:227/249` | filtro de propostas por perfil | **vira** com "Sem perfil" e o perfil base atual | T034 |
| listas (`assets/busca.py:44`, `assets/service.py:299`, `cenas/service.py:440`, `produtos/service.py:271`, `vozes/service.py:85/196`, `geracao/service.py:368`) | filtro obrigatório por perfil | **vira** filtro opcional (`perfilId` ausente/`sem`/uuid) | T011, T021 |
| `vozes/service.py:85` | nome único por perfil | **vira** único na agência | T003, T011 |
| criação (`Asset(...)`, `Image(...)`, `Produto(...)`, `Voz(...)`, `Cena(...)`, `Audio(...)`, `Geracao(...)`) | `perfil_id` obrigatório | aceita `None` | T005, T008, T011 |
