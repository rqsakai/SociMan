# Contrato HTTP: 004-kit-de-marca

Este arquivo é a fonte de desenho. Na implementação, a fonte vira o OpenAPI do FastAPI (princípio
IV), com `npm run gen:contract`. Tudo fica sob `/api`, e o envelope de erro é o da 001. **Não
existe nenhuma rota DELETE** (FR-009, FR-016, SC-005). Os nomes dos campos JSON seguem o
camelCase da 003; os tokens do kit estão em [data-model.md](../data-model.md).

## Tipos
```text
Kit         { perfilId, version: int (0 = padrão ainda não salvo), persisted: bool,
              palette: Cor[], caption: Legenda, hook: Gancho, watermark: MarcaDagua,
              endCard: CardFinal, catchphrases: string[], series: string[],
              updatedAt: datetime|null, updatedBy: UserRef|null }
Fonte       { id, perfilId, name, family, style, format: "ttf"|"otf", bytes: int,
              archived: bool, version: int, createdAt, createdBy: UserRef|null }
FontePadrao { key: "anton"|"noto-serif-bold"|"liberation-sans"|"liberation-serif",
              name, family, url: string }          # url pública /api/fontes-padrao/{key}
FontOption  { ref: FonteRef, name, family, url: string }   # para os seletores e a prévia
Corte       { id, perfilId, hookText, kitVersion, status: "na_fila"|"processando"|"pronto"|"falhou",
              progress: int, queuePosition: int|null, attempts: int,
              errorMessage: string|null, originalFilename, bytes: int, durationMs, width, height,
              hasAudio: bool, resultBytes: int|null, processingMs: int|null, posterUrl: string|null,
              version: int, createdAt, createdBy: UserRef|null, finishedAt: datetime|null }
MidiaLink   { url: string, expiresAt: datetime|null }   # null = sem validade (só fonte e marca d'água, na exportação)
Armazenamento { available: bool, reason: "ok"|"sem_sentinela"|"pouco_espaco", freeBytes: int|null,
              totalBytes: int|null, minFreeBytes: int, cortesBytes: int }   # HD de dados (R5)
KitExport   ver "Exportação" abaixo
Version, UserRef   como na 003
```

## Kit (`RequireUser`, salvo onde indicado)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/perfis/{id}/kit` | – | `{kit, fontOptions: FontOption[]}` (padrão com `version: 0` se nunca salvo) | 404 |
| `PUT /api/perfis/{id}/kit` | `{version, palette, caption, hook, watermark, endCard, catchphrases, series}` | `{kit}` (o 1º salvamento, com `version: 0`, cria a v1) | 400 `invalid_kit` (`field`, mensagem); 409 `version_conflict` ("Este kit foi alterado por outra pessoa; recarregue"); 404 |
| `GET /api/perfis/{id}/kit/versions` | – | `{items: Version[]}` | 404 |
| `POST /api/perfis/{id}/kit/revert` | `{version, toVersion}` | `{kit}` | **`RequireOwner`** (403 para membro); 409 `version_conflict`; 409 `revert_conflict` ("A versão usa a fonte X, que está arquivada; restaure-a antes") |
| `GET /api/perfis/{id}/kit/export` | query `download?` (bool) | `KitExport`; com `download=1`, `Content-Disposition: attachment; filename="kit-<slug>-v<versão>.json"` | 404 |

## Fontes (`RequireUser`)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/fontes-padrao` | – | `{items: FontePadrao[]}` | |
| `GET /api/fontes-padrao/{key}` | – | o arquivo (`font/ttf`), **sem login** (fontes livres, OFL), `Cache-Control: public, max-age=31536000, immutable` | 404 |
| `GET /api/perfis/{id}/fontes` | query `archived?` (padrão false) | `{items: Fonte[]}` | 404 |
| `POST /api/perfis/{id}/fontes` | `multipart/form-data`: `file`, `name` | `{fonte}` (201) | 400 `invalid_font` ("Não é uma fonte TTF/OTF" \| "Arquivo maior que 10 MB"); 409 `font_name_in_use`; 503 `storage_unavailable`; 507 `storage_full` |
| `PATCH /api/fontes/{id}` | `{version, name}` | `{fonte}` | 409 `version_conflict` / `font_name_in_use` |
| `POST /api/fontes/{id}/archive` | `{version}` | `{fonte}` | 409 `font_in_use` (`details.fields: ["hook.fonte", …]`, "Esta fonte é usada no gancho; troque antes de arquivar"); 409 `version_conflict` |
| `POST /api/fontes/{id}/restore` | `{version}` | `{fonte}` | 409 |
| `GET /api/fontes/{id}/versions` | – | `{items: Version[]}` | 404 |

## Imagem de marca d'água (`RequireUser`)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/perfis/{id}/marca-dagua` | `multipart/form-data` `file` | `{image: ImageRef}` (201); não altera o kit (o usuário escolhe a imagem no kit e salva) | 400 `invalid_image` ("Formato não aceito" \| "Arquivo maior que 5 MB" \| "Imagem pequena demais" \| "A imagem precisa ter fundo transparente"); 503 `storage_unavailable`; 507 `storage_full` |
| `GET /api/perfis/{id}/marca-dagua` | – | `{items: ImageRef[]}` (as enviadas, mais recentes primeiro) | 404 |

## Cortes (`RequireUser`)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/perfis/{id}/cortes` | `multipart/form-data`: `file`, `hookText` | `{corte}` (201, status `na_fila`) | 413 `payload_too_large` ("Arquivo maior que 500 MB"); 400 `invalid_video` ("Não é um vídeo aceito" \| "Vídeo mais longo que 3 minutos" \| "Resolução não suportada"); 400 `invalid_hook` ("Gancho longo demais", mais de 120 caracteres ou mais de 3 linhas na fonte e no tamanho do kit); 503 `storage_unavailable` ("O HD de dados não está disponível", sem o sentinela); 507 `storage_full` ("Pouco espaço no HD de dados", livre − envio < `HD_MIN_FREE_GB`); 409 `perfil_archived`. O volume e o tamanho são conferidos **antes** de ler o corpo |
| `GET /api/perfis/{id}/cortes` | query `status?`, `limit?` (50), `before?` (cursor por `createdAt`) | `{items: Corte[]}` | 404 |
| `GET /api/armazenamento` | – | `Armazenamento` (a aba Cortes mostra uso e espaço livre, e desabilita o envio quando `available` é false) | |
| `GET /api/cortes/{id}` | – | `{corte}` (o SPA faz polling a cada 2 s enquanto `na_fila` ou `processando`) | 404 |
| `POST /api/cortes/{id}/retry` | `{version}` | `{corte}` (volta para `na_fila`, com a mesma `kitVersion` e os mesmos `kit_tokens`) | 409 `conflict` (status diferente de `falhou`); 409 `version_conflict` |
| `GET /api/cortes/{id}/versions` | – | `{items: Version[]}` | 404 |

## Mídia (links assinados, R6)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/midia/links` (`RequireUser`) | `{items: [{kind: "corte_original"\|"corte_marcado"\|"fonte"\|"marca_dagua", id}]}` (até 20) | `{items: MidiaLink[]}` (validade de 1 h) | 404 (item de outro tipo ou inexistente); 409 `not_ready` (marcado antes de `pronto`) |
| `GET /api/midia/{token}` (**sem login**) | header `Range?`; query `download?` | o arquivo, 200 ou 206 (`Accept-Ranges: bytes`, `Content-Range`), `Content-Type` da tabela, `nosniff`, `Cache-Control: private, max-age=3600` | 403 `invalid_link` ("Link inválido ou vencido"); 503 `storage_unavailable` (HD fora); 416 |

## Exportação (`KitExport`, `schema: "sociman.kit/1"`)
```json
{
  "schema": "sociman.kit/1",
  "generatedAt": "2026-09-29T12:00:00Z",
  "perfil": { "id": "…", "slug": "queridinhos", "name": "Queridinhos" },
  "kit": { "version": 4, "updatedAt": "…" },
  "tokens": {
    "palette": [{ "chave": "rosa", "nome": "Rosa Queridinhos", "valor": "#FF5FA2" }],
    "caption": { "fonte": { "ref": "padrao:anton", "family": "Anton" }, "tamanho": 44, "cor_texto": "#FFFFFF", "…": "…" },
    "hook": { "…": "cores já resolvidas em hex" },
    "watermark": { "…": "…", "texto": "@meusqueridinhos10" },
    "endCard": { "…": "…" },
    "catchphrases": ["Olha esse achadinho..."],
    "series": []
  },
  "openshorts": {
    "subtitle": {
      "position": "bottom", "font_size": 44, "font_name": "Anton",
      "font_color": "#FFFFFF", "border_color": "#000000", "border_width": 4,
      "bg_color": "#000000", "bg_opacity": 0.0, "style": "karaoke",
      "highlight_color": "#FF5FA2", "effect": "pop", "base_opacity": 1.0, "uppercase": true
    },
    "hook": {
      "enabled": false, "style": "red", "size": "M", "position": "top", "duration_seconds": 3,
      "exact": false, "distance": 18.4
    },
    "approximations": [
      "hook: fundo #FF5FA2 aproximado para o preset red (#DC2626); texto exato",
      "hook: o gerador usa sempre Noto Serif Bold (o kit usa Anton)"
    ]
  },
  "assets": {
    "fonts": [{ "ref": "perfil:…", "name": "Pergaminho", "url": "/api/midia/…", "expiresAt": null }],
    "watermarkImage": null
  }
}
```
- `openshorts.subtitle` é aceito como está pelo `POST /api/subtitle` do gerador (mais `job_id` e
  `clip_index`, que são do gerador). SC-002 é verificado por teste.
- `openshorts.hook.enabled` é **sempre `false`**: só o SociMan queima o gancho (US4). O produtor
  gera os cortes no OpenShorts **sem o gancho automático**; `style`, `size`, `position`,
  `duration_seconds`, `exact` e `distance` ficam só como referência.
- As URLs de `assets` são relativas ao edge (`http://<host>:8180`), assinadas e **sem validade**
  (`expiresAt: null`): valem enquanto o arquivo existir. Vídeos nunca recebem link sem validade.

**Rotas da 003 afetadas:** `PUT /api/perfis/{id}/logo` e `…/banner` passam a responder também
503 `storage_unavailable` e 507 `storage_full` (toda gravação no MinIO confere o HD, R5). O
`GET /api/health` ganha `storage: "ok"|"unavailable"|"low_space"`, sem mudar o `status`.

**Códigos de erro novos:** `invalid_kit`, `invalid_font`, `font_name_in_use`, `font_in_use`,
`invalid_video`, `invalid_hook`, `payload_too_large`, `storage_unavailable`, `storage_full`,
`perfil_archived`,
`not_ready` e `invalid_link`.

## Rotas do SPA
| Rota | Conteúdo |
|---|---|
| `/app/perfis/:id` aba **Marca** | formulário por seção (Paleta, Legenda, Gancho, Marca d'água, Card final, Bordões e séries) com a prévia 9:16 ao lado (embaixo no celular); "Salvar"; "Exportar JSON"; link para o histórico do kit |
| `/app/perfis/:id` aba **Fontes** | lista com amostra "Os achadinhos que você queria" em cada fonte, enviar, renomear, arquivar/restaurar |
| `/app/perfis/:id` aba **Cortes** | enviar (arquivo + gancho, com barra de upload), lista (data, autor, gancho, versão do kit, status com progresso e posição na fila), abrir; no topo, uso e espaço livre do HD de dados, com aviso e envio desabilitado quando o HD não está disponível ou está abaixo do mínimo |
| `/app/cortes/:id` | player com o resultado (ou o original enquanto processa), "Baixar", "Baixar original", "Tentar de novo" quando `falhou`, detalhes (FR-017) |
| `/app/perfis/:id/kit/historico` | histórico do kit com antes/depois por seção; "Reverter" só para dono (o `VersionHistory` da 003) |
