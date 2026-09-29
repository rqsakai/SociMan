# Contrato HTTP: 003-contas-sociais

Este arquivo é a fonte de desenho. Na implementação, a fonte vira o OpenAPI do FastAPI (princípio
IV), com `npm run gen:contract`. Tudo fica sob `/api`, e o envelope de erro é o da 001. **Não
existe nenhuma rota DELETE** (FR-014).

## Tipos
```text
ImageRef   { id: uuid, width: int, height: int, urls: { thumb: string, medium: string } }   # URLs /img/... (imgproxy)
Perfil     { id, slug, name, niche, bio, language, status: "em_preparacao"|"ativo"|"pausado",
             logo: ImageRef|null, banner: ImageRef|null, platforms: Platform[] (contas ativas),
             archived: bool, archivedAt: datetime|null, version: int,
             createdAt, updatedAt, createdBy: UserRef|null, updatedBy: UserRef|null }
Conta      { id, perfilId, platform: Platform, platformName: string, handle: string, url: string,
             status: "planejada"|"ativa"|"pausada"|"encerrada", notes, archived: bool, version: int,
             createdAt, updatedAt, createdBy, updatedBy }
Platform   "tiktok"|"youtube"|"instagram"|"kwai"|"facebook"|"x"|"outra"
Version    { version: int, action: "created"|"updated"|"archived"|"restored"|"reverted",
             actor: UserRef|null, actorKind: string, occurredAt: datetime,
             changedFields: string[], before: object|null, after: object, details: object }
UserRef    { id: uuid, name: string }
```

## Perfis (qualquer usuário logado: `RequireUser`)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/perfis` | query `q?`, `status?`, `archived?` (padrão false) | `{items: Perfil[]}` ordenado por nome | |
| `GET /api/perfis/slug-suggestion` | query `name` | `{slug}` | |
| `POST /api/perfis` | `{name, slug, niche?, bio?, language?, status?}` | `{perfil}` (201) | 409 `slug_in_use`; 400 |
| `GET /api/perfis/{id}` | – | `{perfil, contas: Conta[]}` (inclui contas arquivadas com a flag) | 404 |
| `PATCH /api/perfis/{id}` | `{version, name?, niche?, bio?, language?, status?}` (sem slug) | `{perfil}` | 409 `version_conflict`; 404; 400 |
| `POST /api/perfis/{id}/archive` | `{version}` | `{perfil}` | 409 `version_conflict` |
| `POST /api/perfis/{id}/restore` | `{version}` | `{perfil}` | 409 |
| `PUT /api/perfis/{id}/logo` | `multipart/form-data` `file` + campo `version` | `{perfil}` | 400 `invalid_image` ("Formato não aceito" \| "Arquivo maior que 5 MB" \| "Imagem pequena demais"); 409 |
| `PUT /api/perfis/{id}/banner` | idem | `{perfil}` | idem |
| `POST /api/perfis/{id}/logo/clear`, `…/banner/clear` | `{version}` | `{perfil}` sem a imagem (a imagem continua guardada e reversível) | 409 |
| `GET /api/perfis/{id}/versions` | – | `{items: Version[]}` da mais recente para a mais antiga | 404 |

## Contas (`RequireUser`)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/perfis/{id}/contas` | `{platform, platformName?, handle?, url?, status?, notes?}` (handle ou url; extrai um do outro) | `{conta}` (201) | 409 `handle_in_use` ("Esse @ já pertence ao perfil X"); 409 `active_platform_exists`; 400 |
| `PATCH /api/contas/{id}` | `{version, handle?, url?, status?, notes?, platformName?}` | `{conta}` | 409 `version_conflict` / `handle_in_use` / `active_platform_exists` |
| `POST /api/contas/{id}/archive` / `restore` | `{version}` | `{conta}` | 409 |
| `GET /api/contas/{id}/versions` | – | `{items: Version[]}` | 404 |

## Reversão (`RequireOwner`: 403 `forbidden` para membro)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/perfis/{id}/revert` | `{version, toVersion}` | `{perfil}` | 409 `version_conflict`; 409 `revert_conflict` (ex.: imagem ou @ em conflito); 404 |
| `POST /api/contas/{id}/revert` | `{version, toVersion}` | `{conta}` | 409 `handle_in_use` / `active_platform_exists` / `version_conflict` |

**Códigos de erro novos:** `slug_in_use`, `handle_in_use`, `active_platform_exists`,
`version_conflict`, `revert_conflict`, `invalid_image` e `conflict` (arquivar o que já está arquivado ou restaurar o que não está).

## Rotas do SPA
| Rota | Conteúdo |
|---|---|
| `/app/perfis` | lista (miniatura, nome, nicho, status, ícones das plataformas), busca, filtro de status e "Arquivados", botão "Novo perfil" |
| `/app/perfis/novo` | formulário: Nome, Identificador (slug sugerido, editável só aqui), Nicho, Descrição, Idioma, Status |
| `/app/perfis/:id` | abas **Dados** (editar, logo, banner), **Contas** (lista, adicionar, editar, arquivar), **Histórico** (versões com antes/depois; "Reverter para esta versão" só para dono); ações Arquivar/Restaurar |
| `/app/contas/:id/historico` | histórico da conta (também acessível pela aba Contas) |

Na navegação do `AppLayout` entra o link "Perfis", visível para dono e membro.
