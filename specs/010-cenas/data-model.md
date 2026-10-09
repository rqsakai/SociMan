# Modelo de dados: 010-cenas

Tudo no PostgreSQL (NVMe), migration **`0015_cenas`** (`down_revision = "0014_mcp"`). Antes de gerar,
confira que nenhuma outra spec ocupou a 0015 (a 013 usará a 0016 apontando para esta). Vídeos e miniaturas
das tomadas ficam no MinIO (HD); o banco guarda só as chaves.
- Pacote novo: `apps/api/src/sociman_api/cenas/`.
- `entity_type` novos: **`cena`**, **`cena_tomada`**, **`cena_padroes`** (histórico, princípio VII).

## Enums novos
- `cena_status`: `rascunho` · `pronta` · `usada`
- `cena_modo`: `ingredientes` · `quadros` · `estender`
- `cena_plano`: `close` · `busto` · `medio` · `americano` · `aberto` · `detalhe_produto`
- `cena_movimento`: `parada` · `aproximacao` · `afastamento` · `panoramica` · `camera_na_mao`
- `tomada_origem`: `flow_manual` (único valor nesta spec). **Ponto de extensão:** a 021 (geração local pelo
  ComfyUI) poderá acrescentar `geracao_local` com `ALTER TYPE … ADD VALUE` e uma coluna nullable
  `geracao_id`, sem refazer a 010

## `cenas` (nova, versionada)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | a cena nunca muda de perfil (`__immutable_fields__`) |
| `nome` | text not null | 1–120, uma linha |
| `avatar_id` | uuid null FK → assets.id | asset tipo `avatar` do mesmo perfil (serviço confere) |
| `avatar_arquivo_id` | uuid null FK → asset_files.id | arquivo `referencia` ou `pose` **desse** avatar; null = principal |
| `cenario_id` | uuid null FK → assets.id | asset tipo `cenario` do mesmo perfil |
| `cenario_arquivo_id` | uuid null FK → asset_files.id | imagem do cenário para ingrediente; null = principal |
| `plano` | `cena_plano` null | |
| `movimento` | `cena_movimento` null | |
| `camera` | text null | detalhe livre, ≤ 500, en |
| `acao` | text not null | 1–1.000, en (é o que vai ao prompt) |
| `fala` | text null | ≤ 300, pt-BR, uma linha |
| `texto_tela` | text null | ≤ 300, pt-BR (guia de edição; fora do prompt) |
| `estilo` | text null | ≤ 500, en; null = padrão do perfil |
| `audio` | text null | ≤ 300, en (ambiente; a fala é separada) |
| `duracao_s` | smallint not null default 8 | CHECK `IN (4, 6, 8)` |
| `modo` | `cena_modo` not null default `ingredientes` | |
| `quadro_inicial`, `quadro_final` | text null | ≤ 500 cada; obrigatórios para `pronta` no modo `quadros` |
| `produto_nome` | text null | ≤ 120 (referência leve; a 012 troca por FK do catálogo) |
| `produto_imagem_id` | uuid null FK → assets.id | asset tipo `imagem` do mesmo perfil; exige `produto_nome` (CHECK) |
| `negative` | text null | ≤ 500; null = padrão do perfil |
| `tags` | text[] not null default '{}' | ≤ 20, sem repetir |
| `notas` | text not null default '' | ≤ 2.000 |
| `status` | `cena_status` not null default `rascunho` | |
| `prompt_congelado` | text null | preenchido em `pronta`/`usada` (CHECK `ck_cenas_congelado`: `status = 'rascunho'` ⇔ `prompt_congelado IS NULL`) |
| `negative_congelado` | text null | idem |
| `avatar_version_congelada`, `cenario_version_congelada` | int null | versões dos assets no congelamento |
| `tomada_escolhida_id` | uuid null FK → cena_tomadas.id (DEFERRABLE) | tomada da própria cena |
| `duplicada_de` | uuid null FK → cenas.id | origem do "Duplicar" (informativo) |
| `archived_at`, `archived_by` | | soft-delete |
| `version` | int not null default 1 | controle otimista |
| `created_*`, `updated_*` | | `AuditMixin` |

- `__versioned_fields__`: todas as colunas editáveis, mais `status`, os congelados,
  `tomada_escolhida_id` e `archived_at`.
- `__immutable_fields__`: `perfil_id`, `duplicada_de`.
- **Índices:**
  - `(perfil_id, archived_at, status)`;
  - `(perfil_id, avatar_id)`, `(perfil_id, cenario_id)`, `(perfil_id, produto_imagem_id)`;
  - GIN em `tags`;
  - busca por texto: índice trigram não, `ILIKE` sem acento sobre `nome`, `acao`, `fala` e
    `produto_nome` (até centenas de linhas por perfil, SC-006).
- **`CAMPOS_PROMPT`** (editar volta `pronta` → `rascunho`; em `usada` dá 409): `avatar_id`,
  `avatar_arquivo_id`, `cenario_id`, `cenario_arquivo_id`, `plano`, `movimento`, `camera`, `acao`,
  `fala`, `estilo`, `audio`, `duracao_s`, `modo`, `quadro_inicial`, `quadro_final`, `produto_nome`,
  `produto_imagem_id`, `negative`.

## `cena_tomadas` (nova, versionada)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `cena_id` | uuid not null FK → cenas.id | imutável |
| `origem` | `tomada_origem` not null default `flow_manual` | imutável; como a tomada nasceu (hoje: envio manual do arquivo gerado no Flow) |
| `video_key` | text not null unique | `cenas/<cena_id>/tomadas/<id>.<ext>` (bucket de vídeos) |
| `content_type` | text not null | `video/mp4`, `video/quicktime`, `video/webm` |
| `bytes` | bigint not null | ≤ 200 MB |
| `duracao_ms` | int not null | 1.000–30.000 |
| `largura`, `altura` | int not null | |
| `miniatura_key` | text not null | bucket `sociman` |
| `prompt_usado` | text not null | cópia do `prompt_congelado` no envio (não muda) |
| `negative_usado` | text not null | idem |
| `nota` | text not null default '' | ≤ 300 (ex.: "2ª tentativa, mão melhor") |
| `archived_at`, `archived_by`, `version`, auditoria | | |

- `__versioned_fields__`: `nota`, `archived_at`. Arquivar a escolhida limpa
  `cenas.tomada_escolhida_id` (histórico na cena).

## `cena_usos` (nova)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `cena_id` | uuid not null FK → cenas.id | |
| `conteudo_id` | uuid not null FK → conteudos.id | origem `video_proprio`, mesmo perfil (serviço confere) |
| `criado_em`, `criado_por` | timestamptz, uuid FK users | humano |
| `desfeito_em`, `desfeito_por` | null | |

- Índice único parcial `(cena_id, conteudo_id) WHERE desfeito_em IS NULL`. Sem `version` própria: o
  vínculo é registrado no histórico da cena e do conteúdo (research R7).

## `cena_padroes` (nova, versionada; uma por perfil)

| Coluna | Tipo | Regras |
|---|---|---|
| `perfil_id` | uuid PK FK → perfis.id | |
| `estilo` | text not null | ≤ 500; padrão do código: "vertical 9:16, natural soft light, realistic, warm retro color grading" |
| `negative` | text not null | ≤ 500; padrão: `text, subtitles, watermark, logo changes, extra fingers, distorted product` |
| `version`, auditoria | | sem linha = padrão do código, `version 0` (como `ia_guias`) |

## `anotacoes` (alterada, spec 009)
- `anotacao_alvo` + `cena`; `anotacao_tipo` + `proposta_cena` (`ADD VALUE` num `autocommit_block`).
- CHECK `ck_anotacoes_proposta_em_destino` → **`ck_anotacoes_proposta_alvo`**:
  `tipo = 'observacao' OR (tipo = 'proposta_texto' AND alvo_tipo = 'destino') OR (tipo = 'proposta_cena' AND alvo_tipo IN ('perfil','cena'))`.
- `campos` (jsonb) da `proposta_cena`: as chaves de `CamposCena` em camelCase (os editáveis da cena).

## Máquina de status

```text
rascunho ──pronta (valida + congela)──▶ pronta ──1º uso ativo──▶ usada
   ▲                                      │  ▲                     │
   └──── editar CAMPOS_PROMPT / rascunho ─┘  └──último uso desfeito┘
pronta/usada ──remontar──▶ (mesmo status, congelado novo)
usada ──editar CAMPOS_PROMPT──✗ 409 cena_usada (duplicar)
arquivar: qualquer status (uma cena usada continua ligada; arquivada não aceita uso novo nem tomada)
```

## Regras derivadas (não gravadas)
- **Prompt exibido:** `montar(...)` ao vivo em `rascunho`; `prompt_congelado` em `pronta`/`usada`.
- **Avisos:** research R4, calculados em cada leitura do detalhe.
- **Miniatura da cena:** tomada escolhida → imagem do arquivo do avatar → iniciais.

## Migration `0015_cenas`
1. enums `cena_status`, `cena_modo`, `cena_plano`, `cena_movimento`, `tomada_origem`;
2. `cena_padroes`; `cenas` (sem a FK de `tomada_escolhida_id`); `cena_tomadas`; FK deferível
   `cenas.tomada_escolhida_id`; `cena_usos` e índices;
3. `ALTER TYPE … ADD VALUE` (autocommit) e troca do CHECK das anotações;
4. downgrade: recusa se houver anotação `proposta_cena`/alvo `cena`; recria o CHECK antigo; derruba as
   4 tabelas e os 5 enums (os valores de enum das anotações ficam).
