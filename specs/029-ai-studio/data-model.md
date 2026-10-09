# Data model: 029 AI Studio

Migration **`0024_ai_studio`** (`down_revision = "0023_cadastro_padronizado"`). A 011 passa a `0027`, depois da `0026_uniao_mercado` da 026 (research R11).

## Colunas que passam a aceitar nulo

| Tabela | Coluna | Significado na 029 | Versionado |
|---|---|---|---|
| `assets` | `perfil_id` | perfil base do item (avatar, cenário, imagem, sticker, marca d'água, fundo) | sim (entra em `__versioned_fields__`) |
| `cenas` | `perfil_id` | perfil base da cena: padrões e proibidas | sim (sai de `__immutable_fields__`) |
| `produtos` | `perfil_id` | perfil base do produto: guia da ficha | sim (sai de `__immutable_fields__`) |
| `vozes` | `perfil_id` | perfil base da voz | sim |
| `images` | `perfil_id` | perfil de quem enviou; nulo = imagem da agência | não (imutável) |
| `audios` | `perfil_id` | idem para áudio | não (imutável) |
| `geracoes` | `perfil_id` | **perfil base usado** na geração (nulo = nenhum) | sim (já é versionada) |
| `ia_chamadas` | `perfil_id` | perfil base usado na chamada (nulo = nenhum) | não (registro) |

Não mudam: `brand_kits`, `fonts`, `ia_guias`, `cena_padroes`, `contas`, `conteudos`, `cortes`, `envios`, `canal_perfis` e as tabelas do aprendizado.

## Regras
- **Itens existentes:** ficam com o perfil atual como perfil base. Nenhum UPDATE de perfil na migration.
- **Mudar o perfil base:** é feito pelo PATCH do item (dono e membro). A mudança vira uma versão com `changed_fields` contendo `perfil_id`, e o revert é só do dono. É aceito com perfil arquivado; só a **geração** recusa perfil arquivado (409 `perfil_base_arquivado`).
- **Perfil base da geração** (o `perfilBaseId` do pedido):

  | Valor | Perfil usado |
  |---|---|
  | ausente | o `perfil_id` do item |
  | `null` | nenhum |
  | um id | aquele perfil (precisa existir e estar ativo) |

  O resultado é gravado em `geracoes.perfil_id` e, nas chamadas de IA, em `ia_chamadas.perfil_id`, com o `guia_perfil_version` já existente.
- **Cena:** os padrões (`cena_padroes`) e as proibidas vêm de `cenas.perfil_id`. Com ele nulo, a resposta da cena traz o aviso `sem_perfil_base`. Avatar, cenário e produto podem ter qualquer perfil base.
- **Chave no MinIO** dos arquivos novos sem perfil: `agencia/imagens/<id>.<ext>` e `agencia/audios/<id>.<ext>`. Os com perfil continuam em `perfis/<id>/…`. As chaves existentes nunca mudam.

## Vozes: nome único na agência (FR-022)
- O índice `uq_vozes_nome` passa a ser `UNIQUE (lower(name)) WHERE archived_at IS NULL`, sem o `perfil_id`.
- **Antes de criar o índice, a migration desduplica:**
  1. Agrupa as vozes ativas por `lower(name)` e as ordena por `created_at, id`.
  2. A primeira fica com o nome; as demais recebem " (2)", " (3)"…
  3. Se o nome com sufixo também já existe, o número sobe até ficar livre.
  4. Cada renomeação incrementa `version` e insere em `entity_versions`: `entity_type = "voz"`, `action = "updated"`, `actor_kind = "system:migration"`, `before`/`after` com o nome, `changed_fields = {name}` e `details = {"motivo": "nome_unico_029"}`.
- Erro no app: 409 `voz_nome_em_uso` (o mesmo código da 025).

## Índices novos (lista da agência, SC-006)
- `ix_assets_lista_agencia` em `assets (archived_at, updated_at DESC, id)`
- `ix_cenas_lista_agencia` em `cenas (archived_at, updated_at DESC, id)`
- `ix_produtos_lista_agencia` em `produtos (archived_at, updated_at DESC, id)`
- `ix_vozes_lista_agencia` em `vozes (archived_at, updated_at DESC, id)`
- `ix_geracoes_alvo` já existe desde a 0020 (a lista por alvo usa esse índice).

## Downgrade
Recusa (`RuntimeError` com a contagem) se houver linha com `perfil_id` nulo em qualquer das 8 tabelas. Sem nulos, volta o `NOT NULL` e o índice de voz por perfil. Os nomes com sufixo não são revertidos (está documentado).
