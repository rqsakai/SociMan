# Contrato HTTP: 007-assets-do-perfil

Este arquivo é a fonte de desenho. Na implementação, a fonte vira o OpenAPI do FastAPI (princípio
IV), com `npm run gen:contract`. Tudo fica sob `/api`, com o envelope de erro da 001 e os nomes
JSON em camelCase. **Não existe nenhuma rota DELETE** (FR-007, SC-004). Todas as rotas são
`RequireUser` (dono e membro), menos a reversão (`RequireOwner`). Tipos e regras em
[data-model.md](../data-model.md).

## Tipos
```text
AssetTipo   "avatar" | "cenario" | "fundo" | "sticker" | "marca_dagua" | "imagem"
FileRole    "referencia" | "pose" | "arquivo"

AssetFile   { id, role: FileRole, look: str|null, uso: str|null, label: str|null,
              quandoUsar: str|null, notes: str, position: int, archived: bool,
              image: ImageRef,                     # da 003: {id, width, height, urls: {thumb, medium}}
              previewUrl: str,                     # imgproxy 1024×1024 (fit)
              contentType: str, bytes: int,
              hasAlpha: bool,                      # images.kind = watermark (miniatura sobre xadrez)
              link: str,                           # /api/midia/{token}, sem validade e estável (R7)
              downloadUrl: str,                    # o mesmo com ?download=1
              createdAt, createdBy: UserRef|null }

AssetSummary { id, perfilId, tipo: AssetTipo, name, tags: str[], cover: ImageRef|null,
               fileCount: int, inUse: bool, archived: bool, version: int, updatedAt }

Asset       AssetSummary + { description, prompt: str|null, voiceTone: str|null,
              imageRules: str|null, primaryFileId: uuid|null,
              files: AssetFile[],                  # ativos e arquivados, por role e position
              createdAt, createdBy: UserRef|null, updatedBy: UserRef|null }

Uso         { origem: "kit" | "corte", rotulo: str, campo: str|null, fileId: uuid,
              bloqueia: bool, href: str|null }

LibraryImage { image: ImageRef, assetId, assetName, assetTipo: AssetTipo, fileId,
               label: str|null, hasAlpha: bool }

TagCount    { tag: str, count: int }
Version, UserRef, ImageRef   como na 003
```

## Biblioteca do perfil
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/perfis/{id}/assets` | query `tipo?` (repetível), `tag?` (repetível, E lógico), `q?` (nome contém ou tag igual), `archived?` (false \| true \| `all`), `limit?` (48, máx. 100), `cursor?` | `{items: AssetSummary[], nextCursor: str\|null, tags: TagCount[]}` (mais recentes primeiro por `updatedAt`) | 404 |
| `POST /api/perfis/{id}/assets` | `{tipo, name, description?, tags?, prompt?, voiceTone?, imageRules?}` | `{asset}` (201, v1) | 400 `invalid_asset` (`field`); 404; 409 `perfil_archived` |
| `POST /api/perfis/{id}/assets/arquivo` | `multipart/form-data`: `file`, `tipo` (não `avatar` nem `cenario`), `name?` (padrão: nome do arquivo sem extensão), `tags?` (separadas por vírgula) | `{asset, file: AssetFile}` (201); atalho de "um arquivo = um asset", usado pelo envio múltiplo e pelos seletores do kit | 400 `invalid_image` ("Formato não aceito" \| "Arquivo maior que 20 MB" \| "Imagem grande demais (máximo 40 megapixels)" \| "Imagem pequena demais" \| "O sticker precisa ter fundo transparente" \| "A imagem precisa ter fundo transparente"); 400 `invalid_asset`; 503 `storage_unavailable`; 507 `storage_full`. O HD é conferido **antes** de ler o corpo |
| `GET /api/perfis/{id}/assets/imagens` | query `tipo` (repetível, obrigatório), `q?`, `limit?` (60) | `{items: LibraryImage[]}`: arquivos ativos de assets ativos, mais recentes primeiro (seletores do kit, R6) | 404 |

## Asset
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/assets/{id}` | – | `{asset, usos: Uso[]}` | 404 |
| `PATCH /api/assets/{id}` | `{version, name?, description?, tags?, prompt?, voiceTone?, imageRules?, primaryFileId?}` | `{asset}` | 400 `invalid_asset`; 409 `version_conflict` ("Este asset foi alterado por outra pessoa; recarregue"); 409 `asset_archived` ("Restaure o asset antes de editar") |
| `POST /api/assets/{id}/arquivos` | `multipart/form-data`: `file`, `role`, `look?`, `uso?`, `label?`, `quandoUsar?`, `notes?` (sem `version`: só acrescenta) | `{asset, file: AssetFile}` (201); o primeiro arquivo vira o principal | 400 `invalid_image` (como acima); 400 `invalid_asset` ("este tipo aceita um arquivo só", `role` incompatível, `label` faltando); 409 `pose_label_in_use`; 409 `asset_archived`; 503; 507 |
| `PATCH /api/assets/{id}/arquivos/{fileId}` | `{version, look?, uso?, label?, quandoUsar?, notes?}` | `{asset}` | 400 `invalid_asset`; 409 `pose_label_in_use`; 409 `version_conflict` |
| `PUT /api/assets/{id}/ordem` | `{version, role, fileIds: uuid[]}` (todos os ativos daquele `role`, na nova ordem) | `{asset}` (uma versão) | 400 `invalid_asset` ("a lista precisa ter todos os arquivos ativos"); 409 `version_conflict` |
| `POST /api/assets/{id}/arquivos/{fileId}/archive` | `{version}` | `{asset}` (se era o principal, o principal passa para o primeiro ativo, ou null) | 409 `asset_in_use` (`details.usos: Uso[]`, "Em uso em: Card final (kit v3)"); 400 `invalid_asset` (único arquivo de tipo simples: "arquive o asset"); 409 `version_conflict` |
| `POST /api/assets/{id}/arquivos/{fileId}/restore` | `{version}` | `{asset}` (volta ao fim da ordem) | 409 `pose_label_in_use`; 409 `version_conflict` |
| `POST /api/assets/{id}/archive` | `{version}` | `{asset}` | 409 `asset_in_use` (`details.usos`); 409 `version_conflict` |
| `POST /api/assets/{id}/restore` | `{version}` | `{asset}` | 409 `version_conflict` |
| `GET /api/assets/{id}/versions` | – | `{items: Version[]}` (autor, ação, `changedFields`, antes/depois) | 404 |
| `POST /api/assets/{id}/revert` | `{version, toVersion}` | `{asset}` (versão nova `reverted`) | **`RequireOwner`** (403 para membro); 409 `version_conflict`; 409 `revert_conflict` ("A versão arquivaria a imagem usada em Card final (kit v3)"; `details.usos`); 409 `pose_label_in_use`; 400 `validation_error` ("Essa versão é igual à atual") |

## Mídia (acréscimo à 004)
- `MidiaKind` ganha **`imagem`** (id = `images.id`, de qualquer `kind`), que pode ser assinado
  **sem validade** (não é vídeo). O `AssetFile.link` e o `downloadUrl` já vêm prontos no
  detalhe; o SPA não precisa chamar `POST /api/midia/links` para eles.
- `GET /api/midia/{token}` com kind `imagem`: o original do bucket `sociman`, `Content-Type` da
  tabela, `Range`, e com `?download=1` o nome `<slug-do-perfil>-<nome-do-asset>-<n>.<ext>`
  (`content_disposition` da 004). 503 com o HD fora; 403 `invalid_link`.
- `POST /api/midia/links` aceita `{kind: "imagem", id}` (validade de 1 h, como os demais).

## Rotas da 004 afetadas
| Rota | Mudança |
|---|---|
| `PUT /api/perfis/{id}/kit` | `invalid_kit` também quando `watermark.imagem_id` / `*.fundo_imagem_id` é de asset ou arquivo **arquivado** ("imagem arquivada; restaure-a na biblioteca"); aceita imagens de `sticker` na marca d'água e de `cenario` no fundo (mesmas classes `watermark`/`fundo`) |
| `POST /api/perfis/{id}/kit/revert` | 409 `revert_conflict` quando a versão usa imagem arquivada (já existia para fonte) |
| `POST/GET /api/perfis/{id}/marca-dagua`, `POST/GET /api/perfis/{id}/fundos` | continuam iguais no contrato, `deprecated: true` no OpenAPI; o envio também cria o asset (`marca_dagua` ou `fundo`); a lista continua devolvendo as imagens do `kind`, agora **sem** as de assets arquivados |

**Códigos de erro novos:** `invalid_asset`, `pose_label_in_use`, `asset_in_use`,
`asset_archived`. Reusados: `invalid_image` (mensagens novas), `version_conflict`,
`revert_conflict`, `storage_unavailable`, `storage_full`, `perfil_archived`, `invalid_link`.

## Edge
`location ~ ^/api/(perfis/[^/]+/assets/arquivo|assets/[^/]+/arquivos)$` com
`client_max_body_size 21m` (a API recusa > 20 MB com `invalid_image`); o resto de `/api/`
continua com 8 MB.

## Rotas do SPA
| Rota | Conteúdo |
|---|---|
| `/app/perfis/:id?aba=assets` aba **Assets** | chips de tipo, chips de tag (com contagem), busca, "Mostrar arquivados"; grade de cards (miniatura, nome, tipo, selos "Em uso" e "Arquivado"); "Novo asset" (Avatar, Cenário, Fundo, Sticker, Marca d'água, Imagem); envio múltiplo para Fundo, Sticker, Marca d'água e Imagem; "Carregar mais" |
| `/app/assets/:id` | cabeçalho com miniatura (ou iniciais), nome, tipo, tags, "Onde é usado", "Arquivar"/"Restaurar", link para o histórico. **Avatar:** descrição para prompts + "Copiar descrição para prompt", tom de voz, regras de imagem, **Looks** (referências agrupadas por look, com uso, "Principal"), **Poses** (grade com rótulo e "quando usar", mover ←/→ e arrastar no desktop). **Cenário:** prompt + "Copiar prompt", referências. **Demais:** o arquivo. Em cada arquivo: "Baixar original", "Copiar link", editar, arquivar |
| `/app/assets/:id/historico` | `VersionHistory` da 003 com antes/depois (inclusive `files`); "Reverter" só para dono |
| aba **Marca** (004) | os seletores de fundo (gancho e card final) e de marca d'água listam da biblioteca, com "Abrir biblioteca" (busca e filtro) e "Enviar imagem" (entra na biblioteca) |
