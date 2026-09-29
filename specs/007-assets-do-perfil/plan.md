# Implementation Plan: Biblioteca de assets do perfil (007-assets-do-perfil)

**Branch**: `007-assets-do-perfil` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-assets-do-perfil/spec.md`

## Summary

Uma biblioteca de assets por perfil (aba "Assets"), fora do fluxo de cortes, com avatares
(descrição para prompts, tom de voz, regras de imagem, looks e poses), cenários, fundos,
stickers, marcas d'água e imagens genéricas. Abordagem:
- **Modelo** (R1): `assets` (o item, com tags e os campos de avatar e cenário) e `asset_files`
  (papel de cada imagem no asset: referência de look, pose ou arquivo, com ordem). Os arquivos
  continuam na tabela `images` da 003 e no bucket `sociman` do HD, então o kit e os cortes, que
  apontam para `images.id`/`object_key`, **não mudam**.
- **Migração verificável** (R2, SC-003): a migration `0005_assets` cria um asset para cada imagem
  de marca d'água e de fundo da 004, com os mesmos ids de imagem, histórico `system:migration`
  e um backfill idempotente testado; o quickstart confere as contagens antes e depois.
- **Tipos e validação** (R3): o `image_kind` vira a classe técnica (cenário = `fundo`, sticker =
  `watermark`; `avatar` e `imagem` novos), a validação pelo conteúdo da 004 é reaproveitada, com
  **20 MB** nas rotas da biblioteca e uma `location` própria de 21 MB no edge.
- **Histórico** (R4): o asset é o agregado (`entity_type = asset`), com os arquivos no snapshot;
  reversão só pelo dono, que arquiva (nunca apaga) o que não existia na versão alvo.
- **Onde é usado** (R5): registro de provedores; o kit bloqueia o arquivamento (409
  `asset_in_use` com a lista), os cortes só informam, e specs futuras (roteiros, cenas)
  registram o próprio provedor.
- **Kit** (R6): os seletores de fundo e marca d'água listam da biblioteca, com "Abrir
  biblioteca" e envio direto; o `ref_context` passa a exigir asset e arquivo ativos.
- **Links** (R7): `MidiaKind = imagem`, sem validade e estável, para "Copiar link" e "Baixar
  original".
- **UI** (R9): aba com grade, filtros por tipo e tag, busca e paginação; detalhe do avatar com
  looks e poses reordenáveis por botões e arrastar nativo, sem dependência nova.

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md). As três perguntas
de alto impacto ([open-questions.md](open-questions.md)) foram resolvidas pelo dono em 2026-09-29
com a opção recomendada (Q1 = A, Q2 = A, Q3 = A), que é a que o plano segue.

## Technical Context

**Language/Version**: Python 3.12 (API) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**:
- **nenhuma dependência nova** (Python ou npm): Pillow, minio e python-multipart já estão na API;
  shadcn/ui, TanStack Query e o HTML5 Drag and Drop nativo no SPA;
- opcional: `npx shadcn@latest add toggle-group` (código gerado no repo, sobre o Radix que já
  está no projeto) para os chips de tipo.

**Storage**: PostgreSQL (`assets`, `asset_files`, `images` com `kind` `avatar` e `imagem`,
`entity_versions` com `entity_type = asset`), no NVMe; arquivos no bucket `sociman` do MinIO no
HD (`SOCIMAN_DATA_DIR`), com sentinela e piso de espaço (`datadir.ensure_writable`) antes de ler
o corpo do upload; spool em `work/tmp` no HD.

**Testing**:
- pytest na stack efêmera (`npm run test:api`): unit (schemas, imaging, `fields_using_image`) e
  integration (assets, usos, backfill, mídia); os testes da 004 continuam verdes sem mudança de
  asserção;
- ruff; `check:web` (contrato regenerado, CSP inalterada);
- Playwright `e2e/assets.spec.ts` na stack e2e isolada (`npm run test:e2e`), mais o ajuste dos
  seletores em `e2e/fundo.spec.ts` e `e2e/marca.spec.ts`.

**Target Platform**: a mesma stack (api, edge, minio no HD, imgproxy); SPA também no modo casa
(PWA). Nenhum serviço novo.

**Project Type**: web application (SPA + API)

**Performance Goals**:
- SC-002: grade e busca numa biblioteca de 200 itens em menos de 10 s de ponta a ponta (a
  consulta em si leva milissegundos com os índices de R8);
- SC-001: avatar com 2 looks e 3 poses em menos de 5 minutos pela interface;
- upload de 20 MB limitado só pela rede de casa.

**Constraints**:
- sem DELETE e sem apagar objeto (FR-007, SC-004);
- 20 MB e 40 MP por imagem; o edge aceita 21 MB **só** nas duas rotas de upload da biblioteca;
- a CSP não muda (miniaturas por `/img`, originais por `/api/midia`, tudo `'self'`);
- HD fora: a biblioteca lista (banco), mas envios e downloads dão 503 (edge case);
- nada publica em rede social (princípio I);
- trabalho em paralelo com a 006 sem colisão (R11 e "Arquivos existentes tocados" abaixo).

**Scale/Scope**: 2 perfis hoje (até ~10); centenas de assets por perfil; 15 endpoints novos (e o kind `imagem` na mídia);
1 aba e 2 páginas novas no SPA; 3 seletores da aba Marca trocados.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Nenhum agente publica | ✅ | a biblioteca só guarda e organiza; "Copiar link" e "Baixar original" servem arquivos ao dono; nenhuma rota ou credencial de rede social; o teste-guarda da 001 passa a cobrir o pacote `assets` |
| II. Direito é responsabilidade do dono | n/a | assets são material próprio do perfil (avatar, cenários, stickers); não há canal-fonte nem envio para corte nesta spec |
| III. Marca em tokens | ✅ | o kit continua em tokens: guarda `images.id`, validado por `check_refs`; a biblioteca só muda a origem da lista e a regra de pertinência (asset ativo). Descrição e prompts são texto do usuário **para ferramentas externas** (Flow/Veo), não regra de marca aplicada por máquina |
| IV. Contrato é a fonte única | ✅ | rotas e schemas novos saem do OpenAPI (`npm run gen:contract`); `check:contract` acusa divergência; nada escrito à mão em `packages/contract` |
| V. Segurança e segredos | ✅ | imagem validada pelo conteúdo (Pillow, `verify`, limite de pixels), nunca pela extensão; bucket privado; links HMAC sem validade só para imagem (nunca vídeo), impossíveis de adivinhar; `Content-Type` da tabela e `nosniff`; limite de 21 MB só numa `location`; CSP inalterada |
| VI. Testes antes de pronto | ✅ | quickstart §0 (migração verificada, SC-003), §6 (pytest, ruff, check:web, e2e); teste automatizado de VII para asset (autor em toda mutação, reversão só dono, nenhuma rota DELETE) |
| VII. Humano no controle | ✅ | toda mutação de asset e arquivo gera versão com autor, antes e depois (`history.record` na mesma transação); arquivar e restaurar, nunca apagar; reversão só pelo dono; a migração registra `system:migration` |
| VIII. Simplicidade | ✅ | nenhuma dependência nem serviço novo; duas tabelas; `images`, `imaging`, `storage`, `midia` e `history` reaproveitados; reordenar com botões e DnD nativo em vez de `@dnd-kit`; uso calculado em vez de tabela mantida; busca com índice comum, sem `pg_trgm` |

**Reavaliação pós-design:** mantida. O design não introduziu nada que precise da tabela de
complexidade. Fora do escopo, de propósito: vídeo e áudio de avatar, geração de imagem por IA,
avatar compartilhado entre perfis, importação automática de `../shared/…` (spec de importação),
uso de stickers nos cortes (spec futura) e as tools do MCP (spec 009).

## Project Structure

### Documentation (this feature)

```text
specs/007-assets-do-perfil/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
├── open-questions.md      # 3 perguntas ao dono (resolvidas em 2026-09-29: Q1, Q2 e Q3 = A)
└── tasks.md               # /speckit-tasks
```

### Source Code (repository root)

**Arquivos novos** (nenhum conflito possível com a 006):

```text
apps/api/
├── migrations/versions/0005_assets.py        # tabelas, enums, image_kind += avatar/imagem, chama assets.backfill (R2, R11)
├── src/sociman_api/assets/
│   ├── __init__.py
│   ├── models.py                             # Asset, AssetFile, AssetTipo, FileRole; propriedade `files` do snapshot
│   ├── tipos.py                              # tabela tipo → image_kind, roles aceitos, "um arquivo só", campos por tipo
│   ├── schemas.py                            # AssetCreate/Patch, FilePatch, Ordem, AssetOut, AssetFileOut, Uso, LibraryImage
│   ├── service.py                            # criar, editar, enviar arquivo, ordem, principal, arquivar/restaurar, reverter (history.py)
│   ├── busca.py                              # filtros, busca, cursor, contagem de tags (R8)
│   ├── usos.py                               # registro de provedores; provedores "kit" (bloqueia) e "corte" (informa) (R5)
│   ├── backfill.py                           # imagens watermark/fundo da 004 → assets (idempotente, SQL sobre a conexão) (R2)
│   ├── router_perfil.py                      # /api/perfis/{id}/assets, …/assets/arquivo, …/assets/imagens
│   └── router.py                             # /api/assets/{id}/…
└── tests/
    ├── unit/test_assets_schemas.py
    ├── unit/test_imaging_assets.py
    ├── integration/test_assets.py
    ├── integration/test_assets_usos.py
    ├── integration/test_assets_backfill.py
    └── integration/test_assets_midia.py

apps/web/src/
├── pages/perfis/tabs/AssetsTab.tsx
├── pages/assets/{AssetDetalhe,AssetHistorico}.tsx
├── components/assets/
│   ├── AssetGrid.tsx  AssetCard.tsx  AssetFilters.tsx  NovoAssetMenu.tsx  AssetUpload.tsx
│   ├── AvatarCampos.tsx  LooksSection.tsx  PosesGrid.tsx  ReorderButtons.tsx
│   ├── UsosList.tsx  CopyButton.tsx  AssetFileCard.tsx
│   └── LibraryImageDialog.tsx                # "Abrir biblioteca" dos seletores do kit
└── lib/assets.ts                             # rótulos pt-BR, query keys, upload com limite de 20 MB, clipboard com fallback

e2e/assets.spec.ts
```

**Arquivos existentes tocados** (lista fechada; trechos pequenos, para evitar colisão com a 006):

| Arquivo | Mudança | Risco com a 006 |
|---|---|---|
| `apps/api/src/sociman_api/main.py` | 2 `include_router` | trivial (linhas vizinhas) |
| `apps/api/src/sociman_api/perfis/models.py` | `ImageKind` += `avatar`, `imagem` | baixo |
| `apps/api/src/sociman_api/imaging.py` | `MIN_SIZE`/`_KIND_FORMATS` dos kinds novos; parâmetros `max_bytes` e `transparency_message` no `validate_image`; mensagem de megapixels; `preview_url` (1024) | baixo |
| `apps/api/src/sociman_api/perfis/service_imagens.py` | `read_limited(stream, max_bytes=…)` | baixo |
| `apps/api/src/sociman_api/midia.py` | `MidiaKind` += `imagem` | **médio** (a 006 pode acrescentar kinds de vídeo na mesma linha) |
| `apps/api/src/sociman_api/router_midia.py` | ramo `imagem` no `resolve` | **médio** (idem) |
| `apps/api/src/sociman_api/marca/tokens.py` | função pura `fields_using_image` | baixo |
| `apps/api/src/sociman_api/marca/service_kit.py` | `ref_context` filtra por asset/arquivo ativo | baixo |
| `apps/api/src/sociman_api/marca/router_marca_dagua.py` | `upload_image` cria o asset; `deprecated=True` nas rotas (e em `router_fundos.py`) | baixo |
| `apps/api/src/sociman_api/marca/router_fundos.py` | `deprecated=True` nas rotas | baixo |
| `apps/api/migrations/env.py` | 1 import dos modelos de `assets` | trivial (linhas vizinhas) |
| `apps/api/tests/conftest.py` | `assets` e `asset_files` no `_TABLES` do TRUNCATE | trivial (mesma tupla) |
| `apps/api/tests/unit/test_kit_tokens.py` | testes de `fields_using_image` (acréscimo) | nenhum |
| `apps/api/src/sociman_api/cortes/**` | **nenhuma** (R3) | – |
| `docker/nginx/default.conf.template` | 1 `location` (21m) | baixo (a 006 pode acrescentar outra; blocos distintos) |
| `docker-compose.yml` | `IMGPROXY_MAX_SRC_RESOLUTION: "40"` no `imgproxy` | baixo |
| `apps/web/src/App.tsx` | rotas `/app/assets/:id` e `…/historico` | trivial |
| `apps/web/src/pages/perfis/PerfilDetalhe.tsx` | aba "Assets" | **médio** (a 006 pode acrescentar abas na mesma lista) |
| `apps/web/src/components/marca/{ProfileImagePicker,FundoImagePicker,WatermarkImagePicker}.tsx` | lista e envio da biblioteca, "Abrir biblioteca", 20 MB | nenhum (004) |
| `e2e/fundo.spec.ts`, `e2e/marca.spec.ts` | textos do seletor | baixo |
| `packages/contract/**` | **gerado** (`npm run gen:contract`); em conflito, rebase e gerar de novo | **alto se editado à mão** (não editar) |
| `e2e/helpers.ts` | helpers de imagem sintética e de seed de assets (acréscimo, se preciso) | baixo |
| `CLAUDE.md` | seção curta "Biblioteca de assets" (ao final da implementação) | baixo |
| `docs/visao.md` | backlog: 007 implementada | baixo (a 006 edita a linha dela) |
| `apps/web/src/components/shell/nav.ts` | **nenhuma** (Assets é aba do perfil, não item do menu) | – |

**Structure Decision**: um pacote de domínio novo, `assets/`, como `marca/` e `cortes/` na 004.
A 004 só é tocada nos seletores de imagem do kit (SPA), na regra de pertinência do
`ref_context`, no `upload_image` das rotas antigas e na migração de dados das imagens de fundo e
marca d'água. `imaging.py`, `midia.py` e `router_midia.py` ficam na raiz do pacote e recebem só
acréscimos. O SPA segue a 005 (abas no detalhe do perfil, páginas de detalhe próprias,
`components/ui` do shadcn).

**Ordem sugerida para o `/speckit-tasks`:**
1. migration + modelos + `backfill` com teste (SC-003) e verificação no dev (quickstart §0);
2. `imaging` (kinds, 20 MB, mensagens) + edge 21m + imgproxy;
3. service e rotas de asset (US1 e US2 no backend), histórico e reversão;
4. usos e arquivamento (US4), `ref_context` e `fields_using_image`;
5. mídia `imagem` (links e download);
6. SPA: aba Assets e grade (filtros, busca, paginação), detalhe do avatar (looks, poses,
   reordenar, copiar), detalhe do cenário;
7. seletores do kit pela biblioteca (US2-2, US3);
8. e2e e medições (SC-001, SC-002).

As etapas 1, 3 e 6 (avatar) fecham a US1 e podem ir ao dono antes do resto.

## Complexity Tracking

Nenhuma violação dos princípios. Itens que parecem complexidade e por que ficam:

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Segunda tabela (`asset_files`) | pose e referência têm metadado editável e ordem; `images` é imutável (FR-010 da 003) | JSONB de arquivos no asset: sem índice do rótulo da pose nem FK para "onde é usado" |
| `location` de 21 MB no edge | FR-004 pede 20 MB por imagem | subir todo `/api/` para 21 MB aumenta a superfície de todas as rotas |
| Registro de provedores de uso | FR-005 pede "cortes e, no futuro, roteiros e cenas" sem editar a 007 a cada spec | consulta fixa só do kit: cada spec nova editaria `assets/` |
