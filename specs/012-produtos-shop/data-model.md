# Modelo de dados: 012-produtos-shop

Tudo fica no PostgreSQL (NVMe), na migration **`0022_produtos_shop`** com `down_revision =
"0021_cadastro_padronizado"` (**provisório**, research R19: depende da ordem real de merge da 021
`0020_geracao_local` e da 025 `0021_cadastro_padronizado`; o gate da 1ª tarefa confere `alembic heads`).
Os arquivos ficam no MinIO do HD, bucket `sociman`, registrados em `images` (003). As tabelas novas usam o
`AuditMixin` da 001 e o `_Versioned` da 003 (`version`, `archived_at`, `archived_by`). O histórico é o
`entity_versions`, com o novo `entity_type` **`produto`**.

Da 021 (sem mudança de forma, só uso): `geracoes` (`alvo_tipo = produto`, `alvo_id = produtos.id`),
`geracao_candidatos`, `ia_chamadas.geracao_id`, `geracao/passos.py`, `geracao/aplicadores.py`,
`geracao/uso.py`.

## Tipos (enums)

| Enum | Valores |
|---|---|
| `produto_status` | `rascunho`, `gerando`, `revisao`, `aprovado` (sem `arquivado`: é efetivo, R4) |
| `produto_ficha_por` | `ia`, `ia_editada`, `humano` |
| `image_kind` (003) | ganha `produto` |
| `anotacao_alvo` (009) | ganha `produto` |

## `produtos`

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | imutável |
| `name` | text not null | 1..80, sem espaço nas pontas (nome interno) |
| `nome_comercial` | text null | pt-BR; 1..120 quando preenchido |
| `categoria` | text null | pt-BR livre (ex.: "roupa > shorts"); ≤ 120 |
| `material_en` | text null | inglês, 2 a 5 palavras, ≤ 60; guardado exatamente (sem trim) |
| `material_pt` | text null | ≤ 60 |
| `formato_corte` | text null | **inglês** (R2), ≤ 300, exato |
| `detalhes_visiveis` | text[] not null default '{}' | **lista** em inglês (R2), ≤ 12 itens de 1..200, exatos |
| `tamanho_relativo` | text null | inglês, ≤ 300, exato |
| `descricao_prompt` | text null | 1 frase em inglês, ≤ 500, usada literalmente, exata |
| `cuidados` | text[] not null default '{}' | pt-BR, ≤ 12 itens de 1..200 |
| `descricao_venda` | text null | pt-BR, 2 a 3 frases, ≤ 600 |
| `precisa_flat` | boolean null | nulo até a ficha chegar |
| `obs` | text not null default '' | ≤ 2.000; entra no pedido da ficha |
| `url_loja` | text null | ≤ 500, `https://`; só informativo (FR-029) |
| `status` | `produto_status` not null default `rascunho` | R8 |
| `ficha_por` | `produto_ficha_por` null | nulo até a 1ª ficha (R9) |
| `version`, `archived_at`, `archived_by` | | `_Versioned` |
| AuditMixin | | `created_by`/`updated_by` |

Índices: `(perfil_id, archived_at, updated_at desc, id)` (lista e cursor);
`(perfil_id, status) WHERE archived_at IS NULL` (seletor de aprovados);
`(perfil_id, lower(name))` e `(perfil_id, lower(nome_comercial))` (busca). Nome **não** é único.

CHECKs: `ck_produtos_ficha` (`ficha_por IS NULL OR precisa_flat IS NOT NULL`);
`ck_produtos_aprovado` (`status <> 'aprovado' OR (ficha_por IS NOT NULL AND nome_comercial IS NOT NULL AND
material_en IS NOT NULL AND formato_corte IS NOT NULL AND tamanho_relativo IS NOT NULL AND
descricao_prompt IS NOT NULL AND descricao_venda IS NOT NULL AND categoria IS NOT NULL AND material_pt IS
NOT NULL)`, a rede de segurança do FR-018; as regras das variantes ficam no service).

**Snapshot versionado** (`__versioned_fields__`): `name`, todos os campos da ficha, `obs`, `url_loja`,
`status`, `ficha_por`, `archived` e **`variantes`** (propriedade: lista por `position` com `id`,
`position`, `cor_en`, `cor_pt`, `original_image_id`, `recorte_image_id`, `flat_image_id`,
`flat_geracao_id`, `archived`). Imutáveis (`__immutable_fields__`): `perfil_id`.

**Estado efetivo** (calculado, nunca gravado): `arquivado` se `archived_at IS NOT NULL`, senão `status`.

## `produto_variantes` (uma por foto/cor)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `produto_id` | uuid not null FK → produtos.id | imutável |
| `position` | smallint not null | ordem entre as ativas, 0..n−1, sem buracos |
| `cor_en` | text null | inglês, ≤ 40, exata; preenchida pela ficha, editável |
| `cor_pt` | text null | ≤ 40 |
| `original_image_id` | uuid not null UNIQUE FK → images.id | foto do dono, intocada; `kind = produto` |
| `recorte_image_id` | uuid null FK → images.id | fundo branco, mesmo tamanho; vem do `produto.recorte` |
| `flat_image_id` | uuid null FK → images.id | só com `precisa_flat`; opção escolhida do `produto.flat` |
| `flat_geracao_id` | uuid null FK → geracoes.id | a geração da opção escolhida (seed e instrução lá, R3) |
| `archived_at`, `archived_by` | | arquivar (nunca apagar) |
| `created_at`, `created_by` | | |

Sem `version` própria: toda mudança é uma versão do produto (como os `asset_files` da 007).

Restrições: `ck_variantes_flat` (`(flat_image_id IS NULL) = (flat_geracao_id IS NULL)`); índice
`(produto_id, archived_at, position)`. **No máximo 6 ativas** por produto e **pelo menos 1** depois de
enviadas as fotos: validado no service com `SELECT … FOR UPDATE` no produto (409 `limite_variantes`; 400
`invalid_produto` ao arquivar a última).

## `images` (003): só enum e tamanho mínimo
- `image_kind` ganha `produto`. `imaging.MIN_SIZE["produto"] = (512, 512)`, formatos PNG/JPG/WebP,
  `max_bytes = 20 MB` pelas rotas de produto. Chave `perfis/{perfil_id}/{uuid4}.{ext}`.
- Originais: gravadas pelas rotas de produto. Recortes e flats (inclusive as opções não escolhidas):
  gravados pelo gerador da 021 com o `image_kind` do passo (`produto`).

## `cenas` (010): só acréscimos

| Coluna | Tipo | Regras |
|---|---|---|
| `produto_id` | uuid null FK → produtos.id | produto do catálogo; do mesmo perfil, `aprovado` e não arquivado **ao ligar** |
| `produto_variante_id` | uuid null FK → produto_variantes.id | variante ativa daquele produto, com recorte |

CHECKs novos: `ck_cenas_produto_variante` (`produto_variante_id IS NULL OR produto_id IS NOT NULL`) e
`ck_cenas_produto_modo` (`produto_id IS NULL OR (produto_nome IS NULL AND produto_imagem_id IS NULL)`).
Os campos leves `produto_nome` e `produto_imagem_id` e o `ck_cenas_produto` **continuam**. Índice
`(perfil_id, produto_id)`. Os dois campos entram em `__versioned_fields__` da cena e nos campos que mudam
o prompt (FR-006 da 010).

## `anotacoes` (009)
- `anotacao_alvo` ganha `produto`; só o tipo `observacao` é aceito nele (validação no service das
  anotações, como `proposta_texto` só em destino).

## `ia/tipos.py` (008, em código)
- `TipoCampoId` ganha `produto.ficha` (schema `FichaSaida`, regra padrão = `ficha.SYSTEM`, fora do
  `listar_regras`), conforme R14 da 021.

## Passos da 021 usados

| Passo | Motor | Bloco | `n_opcoes` | Sem escolha | Resultado no alvo (aplicador) |
|---|---|---|---|---|---|
| `produto.ficha` | `claude` | — | (texto) | sim | ficha + cores das variantes; `ficha_por = ia` |
| `produto.recorte` | `comfyui` | `cutout` | 1 | sim (`automatico`) | `recorte_image_id` da variante `extras.varianteId` |
| `produto.flat` | `comfyui` | `keyframe` | 2 | **não** (humano) | `flat_image_id` + `flat_geracao_id` da variante |

`params` (imutável depois do pedido): ficha `{referencias: originais, instrucao: obs, extras: {nome}}`;
recorte `{referencias: [original], extras: {varianteId}, bloco: "cutout"}`; flat `{instrucao:
flat.instrucao(ficha, variante), referencias: [recorte], seeds, n: 2, extras: {varianteId}, bloco:
"keyframe"}`. Os aplicadores conferem que a variante é do produto, está ativa e (no flat) que o recorte
de `params` ainda é o da variante; se não for, `aplicar` recusa (`entrada_invalida`) e a geração não
aplica.

## Estados do produto

```text
rascunho ──fotos enviadas──▶ gerando ──ficha + recortes (+ flats escolhidos)──▶ revisao ──Aprovar──▶ aprovado
aprovado ──editar ficha / cor / precisa_flat · refazer flat · nova variante · reverter──▶ revisao (ou gerando, se faltar passo)
qualquer ──arquivar──▶ (efetivo) arquivado ──restaurar──▶ o mesmo status de antes (R4)
```

| De | Para | Quem | Gatilho |
|---|---|---|---|
| — | `rascunho` | humano | criar sem fotos |
| — / `rascunho` | `gerando` | humano | criar com fotos / enviar a 1ª variante (pede `produto.ficha`) |
| `gerando` | `gerando` | gancho da 021 | ficha aplicada → pede recortes; recortes → pede flats |
| `gerando` | `revisao` | gancho da 021 / humano | último recorte aplicado ou último flat escolhido (`reavaliar`) |
| `revisao` | `aprovado` | humano (dono ou membro) | Aprovar (sem pendências) |
| `aprovado` | `revisao`/`gerando` | humano | edição (FR-019), `reavaliar` |
| qualquer | `rascunho` | `reavaliar` | sem variante ativa (só se alguém arquivar todas; o service já recusa a última) |

Toda transição humana é `history.record` (`updated`); as do gancho gravam versão do produto com
`details.geracao_id` (e `details.automatico = true` no recorte e na ficha), autor = quem pediu.

## Regras derivadas (sem coluna)
- **Ficha completa** (R9): todos os campos de texto preenchidos, `detalhes_visiveis` e `cuidados` com
  ≥ 1 item, `precisa_flat` definido, `cor_en`/`cor_pt` em toda variante ativa.
- **Pendências** (FR-018): `ficha_incompleta`, `sem_variante`, `sem_recorte`, `sem_flat`, `sem_cor`,
  `geracao_em_andamento` (geração `produto.*` não final do produto, por `fila.abertas_do_alvo`).
- **Aviso `flat_desatualizado`** (R10): `flat.instrucao(ficha, variante) <> geracoes.params.instrucao` da
  `flat_geracao_id`.
- **Uso** (`produtos/usos.py`): cenas com `produto_id` (origem `cena`, `bloqueia = false`).
- **Em uso para a limpeza** (`produtos/uso.py`, provedor do `midia_em_uso` da 021): `original_image_id`,
  `recorte_image_id` e `flat_image_id` de toda variante, ativa ou arquivada.

## Migração `0022_produtos_shop`
1. `ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'produto'` e `ALTER TYPE anotacao_alvo ADD VALUE IF NOT
   EXISTS 'produto'` (em `autocommit_block`, sem uso na mesma transação);
2. `CREATE TYPE produto_status`, `produto_ficha_por`; `CREATE TABLE produtos`, `produto_variantes`;
   índices e CHECKs;
3. `ALTER TABLE cenas ADD COLUMN produto_id …, ADD COLUMN produto_variante_id …`, CHECKs e índice;
4. **Downgrade:** recusa se existir linha em `produtos`, cena com `produto_id`, imagem `kind = produto` ou
   anotação com `alvo_tipo = produto`; senão remove colunas, CHECKs, tabelas e tipos e recria os dois
   enums sem o valor `produto` (como a `0004`). Nada de objeto do MinIO é tocado.

`test_migration_0022` cobre upgrade, downgrade vazio e recusa do downgrade com dados.
