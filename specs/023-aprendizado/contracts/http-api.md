# Contrato HTTP: Aprender com o desempenho (023)

Prefixos `/api/perfis/{perfilId}/aprendizado/*` e `/api/aprendizado/*`. Os `operationId` são
`aprendizado_*`, e as respostas vêm em camelCase (aliases Pydantic). Não há "tiktok" nem "youtube" em
rotas nem em `operationId`. O contrato tipado sai do OpenAPI (`npm run gen:contract`); este arquivo
descreve a forma e as regras.

**Quem pode:**
- **Rotas H** (só dono humano, `RequireHumanOwner`):
  - membro → 403 `somente_dono`;
  - `system:*` ou token MCP → 403 `somente_humano`, com o evento de recusa e `details.rota`.
- **Rotas U** (`RequireUser`): dono e membro. Para membro, os campos de custo vêm `null`.

Toda escrita em entidade versionada recebe `version` e devolve 409 `version_conflict` quando diverge.

## Temas e taxonomia

| operationId | Método e rota | Quem | Corpo / resposta |
|---|---|---|---|
| `aprendizado_temas_list` | `GET /api/perfis/{perfilId}/aprendizado/temas?arquivados=bool` | U | → `{ items: Tema[], taxonomiaVersao }` |
| `aprendizado_temas_create` | `POST /api/perfis/{perfilId}/aprendizado/temas` | H | `{ nome, descricao?, palavrasChave? }` → 201 `Tema` · 409 `temas_no_maximo` · 409 `tema_repetido` |
| `aprendizado_temas_lote` | `POST /api/perfis/{perfilId}/aprendizado/temas/lote` | H | `{ temas: TemaIn[], chamadaId? }` (salvar a proposta da IA, tudo ou nada; `details.ia` como na 008) → 201 `{ items }` |
| `aprendizado_temas_update` | `PATCH /api/aprendizado/temas/{id}` | H | `{ version, nome?, descricao?, palavrasChave? }` → `Tema` |
| `aprendizado_temas_archive` / `_restore` | `POST /api/aprendizado/temas/{id}/archive` · `/restore` | H | `{ version }` → `Tema` (arquivar manda as classificações para "Sem tema") |
| `aprendizado_temas_juntar` | `POST /api/aprendizado/temas/{id}/juntar` | H | `{ version, destinoId }` → `{ origem: Tema, destino: Tema, movidas: int }` |
| `aprendizado_temas_versions` / `_revert` | `GET …/temas/{id}/versions` · `POST …/temas/{id}/revert` | U · H | `{ version: alvo }` |
| `aprendizado_taxonomia_propor` | `POST /api/perfis/{perfilId}/aprendizado/taxonomia/propor` | H | `{ instrucao? }` → `{ chamadaId, temas: TemaIn[], custoUsd }` (nada salvo; 503 `claude_unconfigured`, 504, 502 como na 008) |

`Tema`: `id, perfilId, nome, descricao, palavrasChave[], archived, juntadoEmId, nPosts, version`.

## Classificações

| operationId | Método e rota | Quem | Corpo / resposta |
|---|---|---|---|
| `aprendizado_classificacoes_list` | `GET /api/perfis/{perfilId}/aprendizado/classificacoes?contaId&temaId&origem&pendentes=bool&cursor&limit` | U | → `{ items: Classificacao[], nextCursor, pendentes: int, limiteHoje: { usadas, limite } }` |
| `aprendizado_classificacoes_put` | `PUT /api/aprendizado/classificacoes/{videoId}` | H | `{ version (0 se nova), temaId \| null, secundarios[], estiloGancho \| null }` → `Classificacao` (`origem = dono`) · 400 `tema_invalido` (de outro perfil ou arquivado) |
| `aprendizado_classificacoes_versions` / `_revert` | `GET …/classificacoes/{videoId}/versions` · `POST …/revert` | U · H | |
| `aprendizado_classificar_pendentes` | `POST /api/perfis/{perfilId}/aprendizado/classificar-pendentes` | H | `{}` → 202 `{ pendentes, restantesHoje }` (marca `pedido_classificacao_em`; a trilha atende na próxima volta) · 409 `sem_taxonomia` |

`Classificacao`: `videoId, post: PostResumo (019), temaId, temaNome, secundarios[], estiloGancho,
justificativa, sugestaoTema, origem, evidenciaParcial, reclassificar, taxonomiaVersao, chamadaId, version`.

## Análise estatística e recomendações (só leitura, salvo o decidir)

| operationId | Método e rota | Quem | Corpo / resposta |
|---|---|---|---|
| `aprendizado_analise` | `GET /api/perfis/{perfilId}/aprendizado/analise?contaId&medida=h1\|h24\|d7&de&ate` | U | → `Analise` (data-model). Sem `de`/`ate`, usa a janela de 180 dias com peso |
| `aprendizado_recomendacoes` | `GET /api/perfis/{perfilId}/aprendizado/recomendacoes?contaId&medida` | U | → `{ abertas: Recomendacao[], decididas: Decisao[] }` |
| `aprendizado_recomendacoes_decidir` | `POST /api/perfis/{perfilId}/aprendizado/recomendacoes/decidir` | H | `{ chave, decisao: "aceita" \| "rejeitada", motivo?, substituir?, medida }` → `{ decisao: Decisao, preferencias?: Preferencias, guia?: { nivel, version } }` · 409 `recomendacao_mudou` (com a atual, se houver) · 409 `fixas_no_maximo` (com `fixas[]`) · 400 `ia_proibida` |
| `aprendizado_decisoes_revert` | `POST /api/aprendizado/decisoes/{id}/revert` | H | `{ version }` → `Decisao` (reverter um aceite reverte as preferências criadas por ele; a hashtag fixada é avisada com o link do guia) |

`Decisao`: `id, chave, tipo, escopo, estado, origem, analiseId, evidencia, texto, motivo, decididoPor,
decididoEm, superada (calculado), version`.

## Preferências

| operationId | Método e rota | Quem | Corpo / resposta |
|---|---|---|---|
| `aprendizado_preferencias_get` | `GET /api/perfis/{perfilId}/aprendizado/preferencias?contaId` | U | → `{ perfil: Preferencias, conta?: Preferencias, efetivas: PreferenciasEfetivas }` |
| `aprendizado_preferencias_patch` | `PATCH /api/perfis/{perfilId}/aprendizado/preferencias?contaId` | H | `{ version, temas?, hashtagsEvitar?, padroes?, classificacaoAuto?, usarDesempenho? }` (os dois últimos só sem `contaId`) → `Preferencias` |
| `aprendizado_preferencias_versions` / `_revert` | `GET …/preferencias/versions?contaId` · `POST …/preferencias/revert?contaId` | U · H | |

## Análises da IA

| operationId | Método e rota | Quem | Corpo / resposta |
|---|---|---|---|
| `aprendizado_analises_estimativa` | `POST /api/perfis/{perfilId}/aprendizado/analises/estimativa` | H | `{ contaId?, n (1–15), medida }` → `{ melhores: PostResumo[], comparaveis: PostResumo[], semArquivo: int, custoSemQuadrosUsd, custoComQuadrosUsd }` (nenhuma chamada) · 409 `sem_posts` |
| `aprendizado_analises_create` | `POST /api/perfis/{perfilId}/aprendizado/analises` | H | `{ contaId?, n, medida, comQuadros, confirmoCusto }` → 202 `AnaliseIa` (`pendente`) · 409 `confirmar_custo` (com as estimativas) · 409 `analise_em_andamento` (uma por perfil) · 503 `claude_unconfigured` |
| `aprendizado_analises_list` | `GET /api/perfis/{perfilId}/aprendizado/analises?cursor` | U | → `{ items: AnaliseIa[] }` |
| `aprendizado_analises_get` | `GET /api/aprendizado/analises/{id}` | U | → `AnaliseIa` |
| `aprendizado_hipotese_recomendar` | `POST /api/aprendizado/analises/{id}/hipoteses/{indice}/recomendar` | H | `{ tipo: "padrao_gancho" \| "padrao_duracao" \| "padrao_horario", texto }` → 201 `Decisao` (`estado = aberta`, `origem = hipotese`) |

`AnaliseIa`: `id, estado, contaId, n, medida, comQuadros, videosSemArquivo, melhores[], comparaveis[],
hipoteses[] (texto, postsIds, contraste, n, grau), custoEstimadoUsd*, custoUsd*, erroCode, pedidoPor,
createdAt, concluidaEm` (* `null` para membro).

## Diagnóstico de distribuição

| operationId | Método e rota | Quem | Corpo / resposta |
|---|---|---|---|
| `aprendizado_diagnostico` | `GET /api/perfis/{perfilId}/aprendizado/diagnostico?contaId&de&ate` | U | → `{ contas: [{ conta, travada, estagnados, medidos, sinais: Sinal[] }], checklist: ItemChecklist[] }` |
| `aprendizado_post_diagnostico` | `GET /api/aprendizado/posts/{videoId}/diagnostico` | U | → `{ post, estagnado, sinais: Sinal[], conferencias: Conferencia[] }` |
| `aprendizado_conferencias_put` | `PUT /api/aprendizado/posts/{videoId}/conferencias/{item}` | H | `{ version (0 se nova), resultado, nota? }` → `Conferencia` · 400 `item_invalido` |

## Rotas existentes que mudam (campos aditivos)

| operationId | Mudança |
|---|---|
| `videos_fonte_list` (Descobrir, 006) | Novo parâmetro `mostrarCortados` (padrão `false`, só com `perfilId`). Cada item ganha `afinidade: Afinidade \| null`, e a resposta ganha `ocultosPorTema: int`. O `score` exibido inclui os pontos da afinidade quando há `perfilId` |
| `analytics_mercado` (019) | `oportunidades[].afinidade`, `ocultosPorTema` e o mesmo parâmetro `mostrarCortados` |
| `ia_chamadas_list` / `ia_chamadas_get` (008) | `desempenhoPerfilVersion`, `desempenhoContaVersion` e `desempenhoExemplos[]` |
| `ia_resumo` (008) | Os tipos `aprendizado.*` entram no detalhamento por tipo (só dono) |
| `ia_gerar` (008), `ia_guia_testar` (017) | Sem mudança no corpo. A resposta pode trazer, em `ajustes`, "removida #x: marcada para evitar" |

## MCP (009)

- **Tools `leitura`:** `aprendizado_temas_list`, `aprendizado_classificacoes_list`, `aprendizado_analise`,
  `aprendizado_recomendacoes`, `aprendizado_preferencias_get`, `aprendizado_diagnostico` e
  `aprendizado_post_diagnostico`.
- **`FORA`** ("IA paga ou dado de dono"): `aprendizado_analises_list`, `aprendizado_analises_get`, e os
  `*_versions`.
- **`PROIBIDAS`:** todas as rotas H.
