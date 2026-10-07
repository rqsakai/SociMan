# Contrato HTTP: 012-produtos-shop

Rotas do FastAPI (fonte única: o OpenAPI gerado; `npm run gen:contract` gera `packages/contract`). Corpo
e resposta em camelCase, como o resto da API. Erros no formato `{code, message, field?}` da `errors.py`.
`operationId` com prefixo `produtos_` (e `cenas_` nas rotas da 010 que mudam). Sem "tiktok" em rota nem
`operationId` (guarda do princípio I): o link da loja é só o campo `urlLoja`.

Auth: leituras com `RequireUser` (dono, membro e cliente MCP pelo mapa); escritas com `RequireHuman`
(dono ou membro humano; outro ator → 403 `somente_humano`); `revert` com `RequireOwner`. Escolher,
cancelar, tentar de novo e gerar outras são as rotas da **021** (`/api/geracoes/{id}/…`), sem mudança.
Os **pedidos** de geração `produto.*` saem das ações do produto (criar, variante nova, salvar ficha,
`pedir-ficha`, `refazer-flat`); o `POST /api/perfis/{id}/geracoes` da 021 com `alvoTipo = produto`
responde 409 `alvo_incompativel` ("use as ações do produto").

## Produtos do perfil

### `GET /api/perfis/{perfilId}/produtos` — `produtos_listar`
Query: `status` (`rascunho|gerando|revisao|aprovado`, repetível), `arquivados` (`false` padrão | `true` |
`so`), `q` (nome interno ou comercial, sem acento e sem caixa), `cursor`, `limit` (≤ 100).
200: `{ itens: ProdutoResumo[], proximoCursor }`.

`ProdutoResumo`: `id`, `name`, `nomeComercial?`, `categoria?`, `status`, `estado` (`status` ou
`arquivado`), `variantesAtivas`, `thumbUrl?` (recorte da primeira variante ativa, senão a original),
`updatedAt`, `version`.

### `POST /api/perfis/{perfilId}/produtos` — `produtos_criar` (multipart)
Campos: `name` (1..80), `obs?` (≤ 2.000), `urlLoja?`, `fotos[]` (1..6 arquivos, PNG/JPG/WebP, ≥ 512×512,
≤ 20 MB cada; ordem = `position`). Sem `fotos`, cria em `rascunho`.
201: `Produto`. Erros: 400 `invalid_image` (com o índice da foto em `field`, ex.: `fotos[2]`), 400
`invalid_produto`, 409 `limite_variantes`, 503 `datadir_indisponivel`, 507 `datadir_cheio`. Validação
de **todas** as fotos antes de gravar qualquer uma (nada fica pela metade).

## Produto

### `GET /api/produtos/{id}` — `produtos_ver`
200: `Produto`:
- `id`, `perfilId`, `name`, `obs`, `urlLoja?`, `status`, `estado`, `fichaPor?` (`ia|ia_editada|humano`),
  `version`, `archivedAt?`, `createdAt/By`, `updatedAt/By`;
- `ficha?`: `nomeComercial`, `categoria`, `materialEn`, `materialPt`, `formatoCorte`,
  `detalhesVisiveis[]`, `tamanhoRelativo`, `descricaoPrompt`, `cuidados[]`, `descricaoVenda`,
  `precisaFlat` (nulo antes da ficha);
- `variantes[]` (ativas e arquivadas, por `position`): `id`, `position`, `corEn?`, `corPt?`, `original`,
  `recorte?`, `flat?` (cada um `ImagemRef {imageId, largura, altura, thumbUrl, url, downloadUrl}`),
  `flatGeracaoId?`, `avisos[]` (`flat_desatualizado`, `sem_cor`), `archivedAt?`;
- `passos[]`: as gerações `produto.*` não finais e a última de cada passo × variante (`GeracaoResumo` da
  021: `id`, `passo`, `varianteId?`, `status`, `progress`, `etapaMensagem`, `errorCode?`,
  `errorMessage?`, `nOpcoes`);
- `pendencias[]` para aprovar: `{varianteId?, motivo}` (`ficha_incompleta`, `sem_variante`,
  `sem_recorte`, `sem_flat`, `sem_cor`, `geracao_em_andamento`);
- `usos[]`: `{origem: "cena", rotulo, href, bloqueia: false}`.

### `PATCH /api/produtos/{id}` — `produtos_editar`
Corpo: `version`, `name?`, `obs?`, `urlLoja?` (null limpa). Não muda estado.
200: `Produto`. 409 `version_conflict`.

### `PUT /api/produtos/{id}/ficha` — `produtos_salvar_ficha`
Corpo: `version`, a `ficha` inteira (campos acima) e `cores: [{varianteId, corEn, corPt}]`.
Regras de `fichaPor` e de estado: research R9. Com uma `produto.ficha` não final, ela é cancelada.
200: `Produto`. 400 `invalid_produto` (com `field`), 409 `version_conflict`.

### `POST /api/produtos/{id}/aprovar` — `produtos_aprovar`
Corpo: `version`. 200: `Produto` (`aprovado`). 409 `produto_incompleto` com `pendencias[]`; 409
`estado_invalido` fora de `revisao`.

### `POST /api/produtos/{id}/arquivar` e `/restaurar` — `produtos_arquivar`, `produtos_restaurar`
Corpo: `version`, `cancelarGeracoes?` (arquivar). 200: `Produto`.

### `GET /api/produtos/{id}/versoes`, `POST /api/produtos/{id}/versoes/{n}/reverter`
`produtos_versoes`, `produtos_reverter` (só dono; 403 para membro). Padrão do `history.py`.

## Variantes

### `POST /api/produtos/{id}/variantes` — `produtos_variante_criar` (multipart)
Campos: `version`, `foto`. 201: `Produto` (volta a `gerando`). 409 `limite_variantes` (6 ativas).

### `PATCH /api/produtos/{id}/variantes/{varianteId}` — `produtos_variante_editar`
Corpo: `version`, `corEn?`, `corPt?`. Num produto `aprovado`, volta a `revisao`.

### `POST /api/produtos/{id}/variantes/{varianteId}/arquivar` | `/restaurar`
Recusa arquivar a última ativa (400 `invalid_produto`); restaurar respeita o limite (409
`limite_variantes`).

### `PUT /api/produtos/{id}/variantes/ordem` — `produtos_variantes_ordenar`
Corpo: `version`, `ids[]` (exatamente as ativas).

### `POST /api/produtos/{id}/variantes/{varianteId}/refazer-flat` — `produtos_refazer_flat`
Cria uma geração `produto.flat` nova para a variante quando a última é final (escolhida, cancelada ou
falhou) ou não existe (o produto passou a `precisa_flat`). Seeds depois da maior já usada (R7 da 021).
Com a última em `revisao`, responde 409 `estado_invalido` ("use Gerar outras", a rota da 021). Num
produto `aprovado`, volta a `revisao`. 201: `GeracaoResumo`. 409 `produto_incompleto` se a ficha está
incompleta ou a variante não tem recorte.

### `POST /api/produtos/{id}/ficha/pedir` — `produtos_pedir_ficha`
Pede (de novo) a ficha ao Claude quando não há ficha nem `produto.ficha` não final (ex.: depois de
"Preencher à mão" desistido, ou de uma falha cancelada). 201: `GeracaoResumo`. 409 se já há ficha.

## Cenas (010) — só acréscimos

- `CenaIn`/`CenaPatch` ganham `produtoId?` e `produtoVarianteId?` (null limpa). Com `produtoId`,
  `produtoNome` e `produtoImagemId` precisam ser null (400 `invalid_cena`, field `produtoId`). Produto
  do mesmo perfil, `aprovado` e não arquivado; variante ativa, com recorte.
- `Cena` (resposta) ganha `produto?: {id, nomeComercial, status, estado, variante?: {id, corPt, corEn,
  thumbUrl}}`.
- `Ingrediente` ganha `produtoId?` e `produtoVarianteId?`; `assetId` e `arquivoId` passam a opcionais.
- `GET /api/perfis/{id}/cenas` ganha o filtro `produtoId`.
- Aviso novo na cena: `produto_fora_de_aprovado`.
- Seletor: `GET /api/perfis/{id}/produtos?status=aprovado` (sem rota nova).

## Anotações (009)

- `alvoTipo` ganha `produto` (só o tipo `observacao`).

## MCP (009) — mapa

Leitura: `produtos_listar` ("Listar produtos", padrão `status=aprovado`), `produtos_ver` ("Ver
produto"), `produtos_versoes`. Nenhuma outra rota de produto entra no mapa.
