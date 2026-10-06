# Contrato HTTP: Cenas (010)

As rotas usam os prefixos `/api/perfis/{perfilId}/cenas*`, `/api/cenas/*` e `/api/conteudos/{id}/cenas`.
Os `operationId` seguem o padrão `cenas_*` e as respostas vêm em camelCase (aliases Pydantic). Nenhuma rota
nem `operationId` contém "tiktok" ou "youtube". O contrato tipado sai do OpenAPI (`npm run gen:contract`);
este arquivo descreve a forma e as regras.

**Quem pode chamar:**
- **U**: dono ou membro (`RequireUser`). Um cliente MCP é barrado antes, pelo mapa: a rota fica em `FORA`.
- **H**: só dono humano (`RequireHumanOwner`). Um membro recebe 403 `somente_dono`; um não humano recebe
  403 `somente_humano` mais o evento.

**Erros comuns:**
- 404 `nao_encontrada`;
- 409 `version_conflict`;
- 409 `arquivada`;
- 422 de validação, com a lista de campos.

## Rotas

| operationId | Método e rota | Quem | Corpo → resposta | MCP |
|---|---|---|---|---|
| `cenas_list` | `GET /api/perfis/{perfilId}/cenas` | U | query `q, status, avatarId, cenarioId, produtoImagemId, tag, arquivadas, cursor, limit` → `{ items: CenaResumo[], nextCursor }` | leitura |
| `cenas_create` | `POST /api/perfis/{perfilId}/cenas` | U | `CenaIn` (+ `propostaId?`, `ia?`) → **201** `Cena` | FORA |
| `cenas_get` | `GET /api/cenas/{id}` | U | → `Cena` (com `prompt`, `ingredientes`, `avisos`, `tomadas`, `usos`) | leitura |
| `cenas_update` | `PATCH /api/cenas/{id}` | U | `CenaPatch` (`version`, campos, `propostaId?`, `ia?`) → `Cena`; em `usada` com campo de prompt → 409 `cena_usada` | FORA |
| `cenas_duplicar` | `POST /api/cenas/{id}/duplicar` | U | → **201** `Cena` (rascunho, "(cópia)") | FORA |
| `cenas_pronta` | `POST /api/cenas/{id}/pronta` | U | `{ version }` → `Cena`; 422 `cena_incompleta` com `faltando[]` | FORA |
| `cenas_rascunho` | `POST /api/cenas/{id}/rascunho` | U | `{ version }` → `Cena` (só de `pronta`; `usada` → 409 `cena_usada`) | FORA |
| `cenas_remontar` | `POST /api/cenas/{id}/remontar` | U | `{ version }` → `Cena` (só `pronta`/`usada`) | FORA |
| `cenas_archive` / `cenas_restore` | `POST /api/cenas/{id}/arquivar` · `/restaurar` | U | `{ version }` → `Cena` | FORA |
| `cenas_versions` | `GET /api/cenas/{id}/versions` | U | → histórico (padrão da 003) | leitura |
| `cenas_revert` | `POST /api/cenas/{id}/revert` | **H** | `{ version, toVersion }` → `Cena`; em `usada` → 409 `cena_usada` | PROIBIDA |
| `cenas_tomadas_list` | `GET /api/cenas/{id}/tomadas` | U | query `arquivadas` → `{ items: Tomada[] }` | leitura (sem `videoUrl`) |
| `cenas_tomadas_upload` | `POST /api/cenas/{id}/tomadas` | U | multipart `arquivo` (≤ 200 MB, 1–30 s) → **201** `Tomada`; 409 `cena_nao_pronta`; 415/422 `video_invalido`; 503/507 do HD | FORA |
| `cenas_tomadas_escolher` | `POST /api/cenas/{id}/tomadas/{tomadaId}/escolher` | U | `{ version }` (da cena) → `Cena` | FORA |
| `cenas_tomadas_update` | `PATCH /api/cenas/tomadas/{tomadaId}` | U | `{ version, nota }` → `Tomada` | FORA |
| `cenas_tomadas_archive` / `_restore` | `POST /api/cenas/tomadas/{tomadaId}/arquivar` · `/restaurar` | U | `{ version }` → `Tomada` | FORA |
| `cenas_tomadas_revert` | `POST /api/cenas/tomadas/{tomadaId}/revert` | **H** | `{ version, toVersion }` → `Tomada` | PROIBIDA |
| `cenas_padroes_get` | `GET /api/perfis/{perfilId}/cenas/padroes` | U | → `CenaPadroes` (`version 0` = padrão do código) | leitura |
| `cenas_padroes_put` | `PUT /api/perfis/{perfilId}/cenas/padroes` | U | `{ version, estilo, negative }` → `CenaPadroes` | FORA |
| `cenas_padroes_revert` | `POST /api/perfis/{perfilId}/cenas/padroes/revert` | **H** | `{ version, toVersion }` | PROIBIDA |
| `conteudos_cenas_get` | `GET /api/conteudos/{id}/cenas` | U | → `{ items: CenaResumo[] }` | leitura |
| `conteudos_cenas_put` | `PUT /api/conteudos/{id}/cenas` | U | `{ version, cenaIds: uuid[] }` (version do conteúdo) → `{ items: CenaResumo[], version }`; 422 `origem_invalida` (não é vídeo próprio), `cena_rascunho`, `cena_outro_perfil`, `cena_arquivada` | FORA |

O edge ganha uma `location ~ ^/api/cenas/[^/]+/tomadas$` com `client_max_body_size 210m` e
`proxy_request_buffering off`. Todas as outras rotas seguem o limite padrão de 8m.

## Schemas

### `CenaIn` / `CenaPatch` (campos editáveis; `extra="forbid"`)
```json
{
  "nome": "Achadinhos abre a panela",
  "avatarId": "uuid|null", "avatarArquivoId": "uuid|null",
  "cenarioId": "uuid|null", "cenarioArquivoId": "uuid|null",
  "plano": "medio", "movimento": "parada", "camera": "eye level",
  "acao": "lifts the lid and steam comes out",
  "fala": "Gente, olha essa panela!", "textoTela": "R$ 49,90 (se estiver nos dados)",
  "estilo": null, "audio": "soft kitchen ambience",
  "duracaoS": 8, "modo": "ingredientes", "quadroInicial": null, "quadroFinal": null,
  "produtoNome": "Panela de pressão elétrica", "produtoImagemId": "uuid|null",
  "negative": null, "tags": ["abertura"], "notas": ""
}
```
O `PATCH` exige `version` e aceita qualquer subconjunto dos campos. `ia: [{ tipoCampo, chamadaId }]` marca
a aplicação da IA (008); `propostaId` marca a proposta de cena aplicada (009).

### `Cena`
```json
{
  "id": "uuid", "perfilId": "uuid", "...campos de CenaIn": "...",
  "status": "rascunho|pronta|usada", "version": 3, "arquivada": false,
  "avatar": { "id": "uuid", "nome": "Achadinhos", "arquivada": false } ,
  "cenario": { "id": "uuid", "nome": "Cozinha retrô", "arquivada": false },
  "produtoImagem": { "id": "uuid", "nome": "Foto panela", "arquivada": false },
  "prompt": {
    "texto": "A cheerful 1950s pin-up style woman … She looks at the camera and says: \"Gente, olha essa panela!\"",
    "negative": "text, subtitles, watermark, logo changes, extra fingers, distorted product",
    "partes": [{ "parte": "avatar", "texto": "…" }, { "parte": "acao", "texto": "…" }],
    "congelado": true, "avatarVersion": 4, "cenarioVersion": 2
  },
  "ingredientes": [
    { "papel": "avatar|produto|cenario", "assetId": "uuid", "arquivoId": "uuid", "nome": "Cozinha, corpo inteiro",
      "largura": 2048, "altura": 2048, "downloadUrl": "/api/midia/…", "thumbUrl": "/img/…" }
  ],
  "avisos": [{ "codigo": "fala_longa|duracao_modo|produto_sem_foto|proibida|assets_mudaram|asset_arquivado",
               "mensagem": "…", "campo": "fala|null", "detalhe": { "antes": "…", "depois": "…" } }],
  "tomadaEscolhida": "Tomada|null", "tomadas": 2,
  "usos": [{ "conteudoId": "uuid", "titulo": "…", "link": "/app/conteudos/…" }],
  "duplicadaDe": "uuid|null", "createdAt": "…", "updatedAt": "…", "autor": "Autor"
}
```

### `CenaResumo`
Contém `id`, `nome`, `status`, `duracaoS`, `modo`, `avatar{id,nome}`, `cenario{id,nome}`, `produtoNome`,
`thumbUrl`, `tags`, `arquivada`, `tomadas` (quantidade), `usos` (quantidade) e `updatedAt`.

### `Tomada`
```json
{ "id": "uuid", "cenaId": "uuid", "duracaoMs": 8000, "largura": 1080, "altura": 1920,
  "naoVertical": false, "bytes": 12345678, "contentType": "video/mp4",
  "thumbUrl": "/img/…", "videoUrl": "/api/midia/… (com validade; omitido no MCP)",
  "promptUsado": "…", "negativeUsado": "…", "nota": "", "escolhida": true,
  "arquivada": false, "version": 1, "createdAt": "…", "autor": "Autor" }
```

### `CenaPadroes`
Contém `perfilId`, `estilo`, `negative`, `version` (0 = padrão do código) e `padraoCodigo { estilo, negative }`.

## Acréscimos em rotas existentes

- **Anotações (009):**
  - `anotacoes_create` aceita `alvo.tipo = "cena"` e `tipo = "proposta_cena"`, com `campos:
    CamposCena`, um subconjunto não vazio de `CenaIn` sem `tags` nem `notas`.
  - Alvo permitido para `proposta_cena`: `perfil` (cena nova) ou `cena` (alteração). Qualquer outro
    alvo → 422 `proposta_alvo_invalido`.
  - A `cena` alvo não pode estar arquivada (409 `alvo_arquivado`) nem `usada` (409 `cena_usada`).
  - Ids de assets fora do perfil ou arquivados → 422 `proposta_invalida`.
- **Assistente de IA (008):**
  - `ia_gerar` aceita os `tipoCampo` `cena.acao`, `cena.camera`, `cena.estilo`, `cena.audio` e
    `cena.ajustar`, com `alvo = { entityType: "cena", entityId }` (`entityId` nulo numa cena ainda não
    salva).
  - O corpo ganha `cenaContexto?: { avatarId, avatarArquivoId, cenarioId, produtoNome, fala, duracaoS,
    modo }`, com o formulário atual (obrigatório quando `entityId` é nulo). O servidor confere que os
    ids são do `perfilId`.
  - `Valor` ganha `cena?: { acao?, camera?, estilo?, audio? }`, que é a entrada e a proposta de
    `cena.ajustar`. Os 4 tipos simples usam `texto`.
- **Assets (007):** a resposta de "onde é usado" ganha a origem `cena` (`bloqueia = false`).
- **Conteúdos (014):** `conteudos_get` ganha `cenas: CenaResumo[]`, só para a origem `video_proprio`.
