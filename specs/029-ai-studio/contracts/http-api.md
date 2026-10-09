# Contrato HTTP: 029 AI Studio

O OpenAPI do FastAPI é a fonte única (princípio IV). Este arquivo descreve o que muda; o `npm run gen:contract` gera o resto. Todas as rotas exigem sessão (`RequireUser`). As escritas usam o mesmo ator de hoje em cada tipo, e as de geração continuam `RequireHuman`.

## Filtro comum `perfilId` (listas da agência)

| Valor | Lista |
|---|---|
| ausente | todos os itens (qualquer perfil base e sem perfil) |
| `sem` | só os itens sem perfil base |
| `<uuid>` | os itens com aquele perfil base (o perfil precisa existir; arquivado é aceito no filtro) |

O valor fica no parâmetro de query `perfilId`. Qualquer outro valor → 400 `invalid_query`, com `field: "perfilId"`.

## Rotas novas

| Método e caminho | operationId | Corpo / query | Resposta |
|---|---|---|---|
| `GET /api/assets` | `assets_listar_agencia` | `tipo[]`, `perfilId`, `q`, `tag[]`, `archived`, `limit`, `cursor` | `{ items: AssetSummary[], nextCursor }` (como a lista por perfil) |
| `POST /api/assets` | `assets_criar_agencia` | `AssetCreate` + `perfilId: uuid \| null` | 201 `{ asset }` |
| `POST /api/assets/arquivo` | `assets_criar_arquivo_agencia` | multipart da 007 + `perfilId` opcional | 201 `{ asset }` |
| `GET /api/cenas` | `cenas_listar_agencia` | `perfilId`, `status`, `q`, `archived`, `limit`, `cursor` | lista da 010 |
| `POST /api/cenas` | `cenas_criar_agencia` | `CenaCreate` + `perfilId` anulável | 201 cena |
| `GET /api/produtos` | `produtos_listar_agencia` | `perfilId`, `status`, `q`, `archived`, `limit`, `cursor` | lista da 012 |
| `POST /api/produtos` | `produtos_criar_agencia` | multipart da 012 + `perfilId` opcional | 201 produto |
| `GET /api/vozes` | `vozes_listar_agencia` | `perfilId`, `status`, `q`, `archived`, `limit`, `cursor` | `{ itens, proximo }` |
| `POST /api/vozes` | `vozes_criar_agencia` | `VozCreate` + `perfilId` anulável | 201 voz |
| `POST /api/geracoes` | `geracoes_pedir_agencia` | `GeracaoIn` + `perfilBaseId` (ausente, `null` ou uuid) | 201 geração |
| `GET /api/geracoes` | `geracoes_listar_agencia` | `alvoTipo`, `alvoId`, `status`, `limit`, `cursor` | lista da 021 |
| `POST /api/audios` | `audios_enviar_agencia` | multipart `arquivo` + `perfilId` opcional | 201 `Audio` |
| `GET /api/estudio/resumo` | `estudio_resumo` | `perfilId` | `{ avatares, cenarios, assets, cenas, produtos, vozes }` (contagens dos ativos), usado no card "Ver no AI Studio" do perfil |

## Rotas que mudam

| Rota | Mudança |
|---|---|
| `PATCH /api/assets/{id}`, `PATCH /api/cenas/{id}`, `PATCH /api/produtos/{id}`, `PATCH /api/vozes/{id}` | aceitam `perfilId: uuid \| null` (muda o perfil base, versionado). Perfil inexistente → 400 `perfil_invalido`. |
| `POST /api/ia/gerar` (008) | ganha `perfilBaseId` (os mesmos 3 estados). O alvo (asset, cena, produto) não precisa mais ser do `perfilId` do pedido. Para os alvos com conta (`postagem.*`), nada muda. |
| As saídas `Asset`, `AssetSummary`, `Cena`, `Produto`, `Voz`, `Geracao` e `IaChamada` | `perfilId` passa a `uuid \| null`, e entra `perfilNome: string \| null` (para as listas). `Cena` ganha o aviso `sem_perfil_base` em `avisos`. |
| `POST /api/perfis/{id}/geracoes` | continua: o `perfil_id` do caminho vira o `perfilBaseId` padrão (ausente = o do caminho). |

## Rotas `deprecated` (mantidas, mesmo comportamento)
- `GET/POST /api/perfis/{id}/assets` e `…/assets/arquivo`
- `GET/POST /api/perfis/{id}/cenas`
- `GET/POST /api/perfis/{id}/produtos`
- `GET/POST /api/perfis/{id}/vozes`
- `GET/POST /api/perfis/{id}/geracoes`
- `POST /api/perfis/{id}/audios`

Equivalem à rota nova com `perfilId = {id}`.

## Erros novos

| Código | Status | Quando |
|---|---|---|
| `perfil_base_arquivado` | 409 | o pedido de geração ou de IA resolve para um perfil arquivado |
| `perfil_invalido` | 400 | `perfilId`/`perfilBaseId` de um perfil que não existe (`field` indicado) |

Os erros que deixam de existir só para "item de outro perfil": o 422 `cena_invalida` com `field` `avatarId`/`cenarioId`/`produtoId` quando o motivo era o perfil (os outros motivos continuam).

## MCP (`mcp/mapa.py`)
- **`TOOLS` (leitura):** `assets_listar_agencia`, `cenas_listar_agencia`, `produtos_listar_agencia` (padrão `status=aprovado`, como a 012), `vozes_listar_agencia` e `estudio_resumo`.
- **`FORA`:** `assets_criar_agencia`, `assets_criar_arquivo_agencia`, `cenas_criar_agencia`, `produtos_criar_agencia`, `vozes_criar_agencia`, `audios_enviar_agencia` e `geracoes_listar_agencia` (como as leituras de geração da 021).
- **`PROIBIDAS`:** `geracoes_pedir_agencia` (`RequireHuman`, como a da 021).
