# Insumo: 012-produtos-shop (cadastro de produtos com padronização)

Entrada para o `/speckit-specify`. Depende da **021-geracao-local**. Padrão testado:
`../comfyui-docker/pipeline/PADROES.md` (seção Produto) e `pipeline/produtos.py` (produto `shorts_canelado`).

## Problema
O produto é o centro do vídeo. Sem um padrão, os modelos erram: foto de "manequim invisível" deitada na
cama parece vestida por alguém; o planejador escreveu "jeans" para malha canelada; peças da mesma linha
saíram de tamanhos diferentes. O cadastro precisa entregar **recorte**, **versão deitada (flat lay)** e uma
**ficha técnica** com as palavras exatas para os prompts.

## Entidades

### `produtos`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid FK | |
| `name` | text | 1..80 (nome interno) |
| `nome_comercial` | text | pt-BR |
| `categoria` | text | ex.: "roupa > shorts" |
| `material_en` | text | 2–5 palavras exatas para prompts ("ribbed knit") |
| `material_pt` | text | |
| `formato_corte` | text | |
| `detalhes_visiveis` | text | logo (texto, cor, posição), cós, costuras |
| `tamanho_relativo` | text | ex.: "all variants identical in size and cut" |
| `descricao_prompt` | text | 1 frase em inglês, usada literalmente |
| `cuidados` | text[] | pt-BR: o que os modelos de vídeo erram neste produto |
| `descricao_venda` | text | pt-BR, 2–3 frases, só o que se vê nas fotos |
| `precisa_flat` | bool | roupa/tecido fotografado em forma 3D |
| `obs` | text | nota livre do usuário (entra no pedido da ficha) |
| `url_loja` | text null | link do produto no TikTok Shop (ver decisão aberta) |
| `status` | enum `produto_status` (ver Estados) | |
| `ficha_por` | enum (`ia`, `humano`, `ia_editada`) | origem da ficha |
| `version`, `archived_*`, AuditMixin | | histórico em `entity_versions` (`entity_type = produto`) |

### `produto_variantes` (uma por foto/cor)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `produto_id` | uuid FK | |
| `position` | smallint | ordem |
| `cor_en`, `cor_pt` | text | preenchidas pela ficha, editáveis |
| `original_image_id` | uuid FK → images | foto do usuário, intocada |
| `recorte_image_id` | uuid null FK → images | fundo branco (BiRefNet), mesmo tamanho |
| `flat_image_id` | uuid null FK → images | só se `precisa_flat`; gerada a partir da ficha (cor, material, corte, logo) |
| `flat_geracao_id` | uuid null FK → geracoes | seed e instrução usadas |
| `archived_*` | | |

`images.kind` ganha `produto`. Formatos PNG/JPG/WebP, mínimo 512×512, 20 MB. Máximo 6 variantes ativas por
produto (limite do planejador).

## Fluxo
1. Usuário cria o produto: nome, 1–6 fotos (uma por cor/variante), observação.
2. `geracao` **produto.ficha** (Claude, 1 chamada com as fotos originais) → preenche a ficha e as cores das
   variantes. Fica gravada antes de qualquer passo de GPU (se a GPU falhar, não se paga a ficha de novo).
3. `geracao` **produto.recorte** por variante (sem escolha: 1 resultado direto).
4. Se `precisa_flat`: `geracao` **produto.flat** por variante, 2 opções → usuário escolhe. "Refazer flat" de
   uma variante gera outras opções.
5. Revisão: folha com originais | recortes | flats + ficha editável → **Aprovar**.

## Estados
```
rascunho ──fotos enviadas──▶ gerando ──ficha + recortes (+ flats escolhidos)──▶ revisao ──aprovar──▶ aprovado
aprovado ──editar ficha / refazer flat / nova variante──▶ revisao
qualquer ──arquivar──▶ arquivado ──restaurar──▶ (estado anterior)
```
- Só produto `aprovado` aparece nos seletores de vídeo/roteiro.
- Editar a ficha à mão muda `ficha_por` para `ia_editada`/`humano` e volta para `revisao`.

## Uso (para specs futuras)
O planejador de vídeo recebe, por produto: as fotos originais, `descricao_prompt`, `material_en`, cores,
`detalhes_visiveis`, `tamanho_relativo` e `cuidados`. O render usa `recorte_image_id` (produto segurado) e
`flat_image_id` (produto deitado), sem gerar de novo. "Onde é usado" (padrão da 007) ganha `origem:
"video"`. A ficha também é exposta no MCP (009), como a visão prevê ("a IA escreve via MCP").

## Fora do escopo
Importar catálogo do TikTok Shop; preço/estoque; flat lay para não-roupa (fica `precisa_flat = false`).

## Decisões abertas para o dono
1. Guardar `url_loja`, preço e comissão já nesta spec, ou só o necessário para o vídeo?
- ~~Do perfil ou compartilhado?~~ **Decidido (2026-10-06):** o produto é **do perfil** (`perfil_id`).
