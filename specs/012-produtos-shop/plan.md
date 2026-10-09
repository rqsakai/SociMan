# Implementation Plan: Produtos do TikTok Shop

**Branch**: `012-produtos-shop` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-produtos-shop/spec.md`

## Summary

O SociMan ganha o **catálogo de produtos do perfil**, padronizado para os modelos de imagem e vídeo:
- **2 tabelas novas** (`produtos`, `produto_variantes`), o valor `produto` em `image_kind` e em
  `anotacao_alvo`, e 2 colunas em `cenas`, na migration `0022_produtos_shop` (`down_revision =
  "0021_geracao_interrupcoes"`, conferido no gate em 2026-10-08: a 012 entra antes da 025, R19);
- o cadastro roda sobre a **021-geracao-local**, com 3 aplicadores (`produtos/aplicadores.py`):
  - `produto.ficha`: motor `claude`, 1 chamada com as fotos originais, no registro da 008, aplicada direto;
  - `produto.recorte`: bloco `cutout`, 1 resultado, aplicado direto e revisado na folha;
  - `produto.flat`: bloco `keyframe`, 2 opções, **escolha humana**;
- um **fluxo** (`produtos/fluxo.py`) encadeia os passos pelo gancho `ao_mudar_estado` da 021 e decide o
  estado (`rascunho → gerando → revisao → aprovado`). O arquivamento é efetivo, sem mudar o status (R4);
- a **folha de revisão** e a ficha editável em `/app/produtos/:id`, e a aba Produtos do perfil;
- a **ponte com a 010**, só por acréscimo (`produto_id`, `produto_variante_id`). O prompt da cena usa a
  frase da ficha e a cor da variante, e o ingrediente é o recorte;
- o **MCP** só lê os produtos aprovados, e a anotação `observacao` pode ser presa a um produto.

Nada publica, compra ou vende. A GPU, a RAM (`dockerctl`, D1), a rede (`gpu-local`, D2), a espera e a
limpeza de 90 dias são da 021.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite)

**Primary Dependencies**:
- API: FastAPI, SQLAlchemy 2, Pydantic 2, Pillow (já usada; reduz as fotos para o Claude em memória) e o
  SDK `anthropic` (pela 008/021);
- SPA: TanStack Query, TanStack Table v9 (`dataTableColumns`), shadcn/ui e os componentes
  `components/geracao/` da 021;
- **nenhuma dependência nova.**

**Storage**:
- PostgreSQL (NVMe): 2 tabelas, 2 colunas e valores de enum;
- MinIO no HD, bucket `sociman` (fotos, recortes e flats), com sentinela `.sociman-volume` e piso de espaço
  (`datadir`).

**Testing**:
- pytest na stack efêmera (`npm run test:api`):
  - fakes da 021: `comfyui_fake.py` (blocos `cutout` e `keyframe`) e `dockerctl_fake.py`;
  - `anthropic_fake.py` estendido com a ficha;
- ruff e `npm run check:web` (inclui `check:contract`);
- Playwright `e2e/produtos.spec.ts` com o `openshorts-fake` (`/comfyui`, `/geracao-e2e`, `/v1/messages`);
- nenhum teste chama serviço real.

**Target Platform**: Linux (`sakai-desktop`) com Docker. A SPA roda no desktop e no celular (modo casa).

**Project Type**: web (apps/api + apps/web), sem serviço novo (usa o `gerador` da 021).

**Performance Goals**:
- criar com 6 fotos de 20 MB: < 10 s, a maior parte é upload;
- ler o produto: < 200 ms;
- a tela vê o andamento em ≤ 2 s (polling da 021);
- a ficha chega em segundos (1 chamada).

**Constraints**:
- até 6 variantes ativas;
- fotos de 512×512 a 40 MP e ≤ 20 MB;
- 1 job de GPU por vez (021);
- RAM do ComfyUI em 12 GB fora dos jobs;
- o edge aceita 130m só nas rotas de upload de produto.

**Scale/Scope**:
- dezenas de produtos por perfil, 1 a 6 variantes cada;
- 17 rotas novas e acréscimos em 3 rotas da 010;
- 2 telas novas (aba e detalhe) e o seletor na cena.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.3.0**: o
princípio VII ganha as "Exceções de eliminação" — limpeza de opções não escolhidas aos 90 dias e
revogação LGPD — aplicada na 1ª tarefa da 021)

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | `produtos/` não importa `publicacao` nem fala com rede social; a única rede externa é a do motor da 021 (ComfyUI e Claude). `url_loja` é texto informativo, sem chamada. Sem "tiktok" em rota nem `operationId` (`produtos_*`); o guarda `test_constitution_guards` ganha `produtos/` |
| **II. Direito é responsabilidade do dono** | ✅ (não afetado) | Nenhum envio para corte. Direito de imagem das fotos do fornecedor é risco do dono, sem bloqueio (spec, Edge Cases) |
| **III. Marca em tokens** | ✅ | A ficha é dado estruturado e validado por schema (`FichaSaida`, listas em `text[]`, R2), aplicável por máquina (prompt da cena, instrução do flat). A `obs` é nota livre e nunca fonte da regra |
| **IV. Contrato é a fonte única** | ✅ | Rotas e schemas Pydantic → `npm run gen:contract`; os acréscimos da 010 e das anotações passam pelo mesmo gerado. Tools do MCP saem do mapa sobre o OpenAPI |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. Uploads validados pelo conteúdo (Pillow, 40 MP). O edge só ganha uma `location` de upload. A CSP não muda (imagens pela mesma origem, via `/img` e `/api/midia`) |
| **VI. Testes antes de pronto** | ✅ | Unitários (estados, instrução do flat, ficha, prompt da cena), integração (fluxo completo, falha de GPU sem 2ª chamada ao Claude, RAM, escolha humana, aprovar, arquivar/restaurar, reverter, limites, ponte, MCP, migration), guardas e e2e. Regra inegociável I e VII com teste no backend: escolha do flat só humana (403 para MCP; o gerador nunca chama `aplicar` do `produto.flat`) e nenhuma eliminação de produto/variante/imagem de variante |
| **VII. Humano no controle** | ✅ com a exceção 1 da 4.3.0 | `entity_type = produto` com `history.record` em toda mutação humana e versão do produto com `details.geracao_id` nas aplicações automáticas. Nada é apagado: arquivar/restaurar e reverter pelo dono. A única eliminação que toca o cadastro é a **exceção 1** (opções de flat não escolhidas aos 90 dias), feita pela limpeza da 021; o provedor `produtos/uso.py` protege toda imagem referenciada por variante. Nenhuma exceção nova |
| **VIII. Simplicidade** | ✅ | Sem serviço, dependência nem fila nova. Duas tabelas, como as do insumo. Rejeitados: jobs próprios (duplicariam a 021) e tabela de estado anterior (R4) |
| Restrições: armazenamento NVMe × HD | ✅ | Imagens no MinIO do HD; o redimensionamento para o Claude é em memória (nada gravado); sentinela e piso em todo upload |
| Restrições: banco | ✅ | `0022_produtos_shop` com upgrade/downgrade e `test_migration_0022` |
| Restrições: portas e containers | ✅ (não afetado) | Nada novo |

**Reavaliação pós-design:** mantida. O design não cria rota de geração própria para o pedido genérico
(409 `alvo_incompativel`, R1) e encadeia os passos só pelo gancho da 021, sem rede dentro dele. Toda
escolha de imagem com mais de uma opção continua humana.

## Divergências resolvidas no plano (spec → plano)

| Divergência | Resolução |
|---|---|
| `detalhes_visiveis` `text` (insumo) × lista (pipeline) | `text[]` em inglês; `cuidados` `text[]` (R2) |
| Idioma de `formato_corte` não dito | inglês (vai na instrução do flat e nos prompts); `categoria` pt-BR (R2) |
| `fotos[].flat_seed` (pipeline) × `flat_geracao_id` (insumo) | só `flat_geracao_id`; seed na opção da 021 (R3) |
| `status = arquivado` **e** `archived_*` (insumo) | só `archived_*`; `arquivado` é estado efetivo; restaurar mantém o status (R4) |
| Flat 1 (pipeline) × 2 opções (insumo) | 2 opções, escolha humana (R7) |
| Recorte "sem escolha" × "toda escolha é humana" | `sem_escolha` da 021 (FR-031), revisão na folha antes de aprovar (R6) |
| Pedido genérico da 021 × instrução vinda da ficha | pedidos só pelas ações do produto; o genérico responde 409 (R1) |
| "Refazer flat" depois de escolhido × "Gerar outras" só em `revisao` (021) | rota `refazer-flat` do produto cria geração nova; em `revisao`, "Gerar outras" (R7) |

## Project Structure

### Documentation (this feature)

```text
specs/012-produtos-shop/
├── plan.md              # este arquivo
├── research.md          # R1–R19
├── data-model.md        # 2 tabelas, acréscimos em cenas/enums, estados, migration 0022
├── quickstart.md        # automático + manual com o dono (GPU real)
├── contracts/api.md     # rotas do SociMan (OpenAPI gerado)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/produtos/
├── __init__.py
├── models.py          # Produto (versionado, snapshot com variantes), ProdutoVariante, enums
├── estados.py         # proximo(), pendencias(), ficha_completa() — puros (R8, R9)
├── ficha.py           # FichaSaida, SYSTEM, montar mensagens (fotos ≤ 1568 px em memória) (R5)
├── flat.py            # instrucao(ficha, variante) — pura (R7, R10)
├── aplicadores.py     # 3 aplicadores da 021 + ao_mudar_estado → fluxo.reavaliar (R1, R8)
├── fluxo.py           # reavaliar(): pede ficha/recortes/flats pelo serviço da 021 (R8)
├── service.py         # criar, editar, ficha, variantes, aprovar, arquivar, restaurar, reverter + history
├── usos.py            # onde é usado: cenas (R13)
├── uso.py             # provedor do midia_em_uso da 021 (R12)
├── schemas.py
├── router.py          # /api/produtos/{id}…
└── router_perfil.py   # /api/perfis/{id}/produtos
apps/api/src/sociman_api/
├── perfis/models.py   # ImageKind.produto
├── imaging.py         # MIN_SIZE/_KIND_FORMATS de "produto"
├── history.py         # entity_type "produto" (se houver lista fechada)
├── ia/tipos.py        # TipoCampoId "produto.ficha" (fora do listar_regras)
├── geracao/passos.py  # (021) passos produto.* com image_kind "produto"; aplicadores registrados
├── geracao/router.py  # (021) POST genérico com alvoTipo=produto → 409 alvo_incompativel
├── cenas/models.py, service.py, prompt.py, ingredientes.py, avisos.py, schemas.py, router_perfil.py
│                      # ponte: produto_id/produto_variante_id, parte "produto", ingrediente recorte, aviso
├── anotacoes/models.py, service.py   # alvo "produto" (só observacao)
├── mcp/mapa.py        # Listar produtos, Ver produto, versões (leitura)
└── main.py            # include_router
apps/api/migrations/versions/0022_produtos_shop.py
apps/api/tests/
├── fakes/anthropic_fake.py   # + ficha (ok, recusa, saída inválida)
├── unit/test_produtos_estados.py, test_produtos_flat.py, test_produtos_ficha.py,
│   test_cenas_prompt_produto.py, test_constitution_guards.py (+012)
└── integration/test_produtos_crud.py, test_produtos_fluxo.py, test_produtos_falhas.py,
    test_produtos_aprovar.py, test_produtos_historico.py, test_produtos_cenas.py,
    test_produtos_mcp.py, test_produtos_limpeza.py, test_migration_0022.py
docker/nginx/default.conf.template            # location de upload de produto (130m)
e2e/fakes/server.py                           # /v1/messages: resposta da ficha
e2e/produtos.spec.ts
apps/web/src/
├── pages/perfis/tabs/ProdutosTab.tsx         # lista (DataTable), filtros, criar
├── pages/produtos/ProdutoPage.tsx            # folha, ficha, passos, usos, histórico
├── pages/produtos/FolhaRevisao.tsx, FichaForm.tsx, VarianteCard.tsx
├── pages/cenas/…                             # seletor de produto/variante, "Ligar ao catálogo"
├── lib/produtos.ts                           # hooks TanStack Query
└── routes                                    # /app/produtos/:id e ?aba=produtos
```

**Structure Decision**: o web app que já existe, com o pacote novo `produtos/`. Setas:
- `produtos → geracao` (serviço de pedido, `fila.abertas_do_alvo`, registro de aplicadores e de uso);
- `cenas → produtos` (leitura do produto e da variante);
- `geracao` não importa `produtos`, porque o registro é feito no import de `produtos/aplicadores.py`
  pelo `main.py` e pelo `cli.py` do gerador;
- `produtos` não importa `publicacao` nem `mcp`.

**Ordem sugerida para as tasks:**
1. gate: 021 verde, com a 4.3.0 aplicada e `0020_geracao_local` no head; conferir a cadeia
   (head real `0021_geracao_interrupcoes`, a 025 vem depois);
2. migration, modelos, enums e imagem `produto`;
3. funções puras (estados, flat, ficha);
4. aplicadores, fluxo e service;
5. rotas e `gen:contract`;
6. telas;
7. ponte com as cenas;
8. MCP e anotações;
9. e2e e polish.

## Complexity Tracking

Nenhuma violação a justificar. O acréscimo de colunas em `cenas` (em vez de substituir os campos leves) é
pedido do dono, para não forçar migração de cenas antigas.
