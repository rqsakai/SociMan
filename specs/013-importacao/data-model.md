# Modelo de dados: 013-importacao

Tudo fica no PostgreSQL (NVMe), na migration **`0016_importacao`** (`down_revision = "0015_cenas"`, criada
pela 010). Antes de gerar a migration, confira com `alembic heads` que a cabeça é a `0015_cenas`; se a 010
ainda não tiver entrado, pare e avise o líder (não aponte para a `0014_mcp` sem combinar).
- Pacote novo: `apps/api/src/sociman_api/agencia/`.
- `entity_type` novo: **`importacao_agencia`** (histórico, princípio VII).
- **Nenhuma coluna nova em tabela de domínio:** perfis, contas, canais, assets, guias, anotações e
  conteúdos são gravados pelos services que já existem. A origem fica em `entity_versions.details.importacao`
  e nos itens da importação.
- A pré-visualização fica no Redis (R7). Os arquivos novos vão para o MinIO no HD (R8, R9).

## Enums novos

- `importacao_agencia_estado`: `processando` · `concluida` · `falhou` · `desfeita`.
- `importacao_item_resultado`: `criado` · `atualizado` · `mantido` · `igual` · `fora` · `nao_gravado` ·
  `sugestao`.

## `agencia_importacoes` (nova, versionada)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `estado` | `importacao_agencia_estado` not null default `processando` | |
| `raiz_shared`, `raiz_clipes` | text not null | os caminhos lidos (no container) |
| `arquivos` | jsonb not null | `{caminho_relativo: sha256}` dos arquivos **usados** (sem os de "fora") |
| `contagens` | jsonb not null default `{}` | por situação e por tipo: `{novo, igual, diverge, fora, aguardando_cota, criado, atualizado, mantido, nao_gravado}` |
| `progresso` | jsonb not null default `{}` | `{etapa: "arquivos"\|"gravando"\|"fim", feitos, total, bytes}` |
| `progresso_em` | timestamptz not null default now() | o último avanço (R8: interrompida depois de 10 min) |
| `erro` | text null | pt-BR, quando `falhou` |
| `criada_em` | timestamptz not null default now() | |
| `criada_por` | uuid not null FK → users.id | sempre um dono humano |
| `concluida_em` | timestamptz null | |
| `desfeita_em`, `desfeita_por` | timestamptz null, uuid null FK → users.id | |
| `version` | int not null | controle otimista e histórico |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | `AuditMixin` |

Regras:
- `ck_agencia_imp_desfeita`: `(estado = 'desfeita') = (desfeita_em IS NOT NULL AND desfeita_por IS NOT NULL)`;
- `ck_agencia_imp_erro`: `(estado = 'falhou') = (erro IS NOT NULL)`;
- `ux_agencia_imp_processando`: índice **único parcial** em `(estado) WHERE estado = 'processando'` (uma por
  vez, R8);
- `ix_agencia_imp_criada (criada_em DESC, id DESC)`;
- `__versioned_fields__ = ("estado", "contagens", "erro", "concluida_em", "desfeita_em", "desfeita_por")`;
  `progresso` e `progresso_em` ficam fora do snapshot (mudam a cada arquivo). Não há revert genérico (R10).
- Transições: `processando → concluida | falhou`; `concluida → desfeita`. Cada uma com `history.record`
  (`created`, `updated`).

## `agencia_importacao_itens` (nova, só inserção, exceto o desfazer)

Um item lido e o que aconteceu com ele. Os itens `fora` e `igual` também são gravados (o relatório completo
fica no banco).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `importacao_id` | uuid not null FK → agencia_importacoes.id | |
| `ordem` | int not null | ordem de aplicação (desfazer na inversa) |
| `tipo` | text not null | `perfil`, `conta`, `guia`, `anotacao`, `canal`, `vinculo_canal`, `imagem_logo`, `asset`, `arquivo_asset`, `clipe`, `sugestao_bordao` (`ck_agencia_item_tipo`) |
| `perfil_slug` | text null | |
| `arquivo` | text not null | caminho relativo à raiz (`shared:` ou `clipes:` no começo) |
| `trecho` | text not null default `''` | seção, linha da tabela ou nome da imagem, legível |
| `linha` | int null | |
| `chave` | text not null | chave de conciliação (research R4) |
| `impressao` | text not null | SHA-256 do conteúdo normalizado do item |
| `situacao` | text not null | `novo`, `igual`, `diverge`, `fora`, `aguardando_cota`, `sugestao` |
| `motivo` | text null | código do motivo (`sem_canal_youtube`, `direito`, `editado`, `arquivado`, `molde`, `nao_usar_ainda`…) |
| `escolha` | jsonb not null default `{}` | `{marcado}`, `{usar: "sociman"\|"markdown"}`, `{direito}` |
| `resultado` | `importacao_item_resultado` not null | |
| `resultado_motivo` | text null | ex.: `mudou_desde_a_leitura`, `editado_desde_a_leitura`, erro de validação em pt-BR |
| `entity_type` | text null | da entidade criada ou alterada (`perfil`, `conta`, `canal`, `asset`, `ia_guia`, `anotacao`, `conteudo`…) |
| `entity_id` | uuid null | |
| `entity_version` | int null | a versão que a importação gravou (desfazer confere) |
| `desfeito_em` | timestamptz null | |
| `desfazer_motivo` | text null | `em_uso`, `editado_depois` |

Regras:
- `ix_agencia_item_imp (importacao_id, ordem)`;
- `ix_agencia_item_chave (chave, importacao_id)` (idempotência das anotações, R4);
- `ck_agencia_item_entidade`: `resultado IN ('criado','atualizado')` ⇒ `entity_type`, `entity_id` e
  `entity_version` não nulos;
- trigger `agencia_itens_so_insercao`: `UPDATE` só pode mudar `desfeito_em` e `desfazer_motivo` (e só de
  `NULL` para valor); `DELETE` levanta erro. O `TRUNCATE` do `reset-db` e dos testes continua valendo.

## Redis: pré-visualização

Chave `agencia:previa:<uuid>`, `EX` 1800 s, JSON:
```text
{ autor_id, criada_em, raizes: {shared, clipes}, arquivos: {caminho: sha256},
  itens: [ {n, tipo, perfil_slug, arquivo, trecho, linha, chave, impressao, situacao, motivo,
            dados, atual?, proposto_direito?, bytes?} ],
  base: { "<entity_type>:<id>": version }, resolver: {entrada: channel_id | "cota" | "erro"} }
```
Lida com `GETDEL` na confirmação (uso único).

## Situação × escolha × resultado

| Situação | Escolha | Resultado na confirmação |
|---|---|---|
| `novo` | `marcado = true` (padrão) | `criado` (ou `nao_gravado` com motivo) |
| `novo` | `marcado = false` | `mantido` |
| `diverge` | `usar = sociman` (padrão) | `mantido` |
| `diverge` | `usar = markdown` | `atualizado` (ou `nao_gravado` se a versão mudou) |
| `igual` | — | `igual` |
| `fora`, `aguardando_cota` | — | `fora` |
| `sugestao` | — | `sugestao` |

## Migration `0016_importacao`

- `upgrade`: cria os 2 enums, as 2 tabelas, os índices e a função/trigger `agencia_itens_so_insercao`.
- `downgrade`: remove trigger, função, tabelas e enums. As versões em `entity_versions` com
  `entity_type = 'importacao_agencia'` ficam (histórico não é apagado; o downgrade só existe para dev).
- `test_migration_0016`: upgrade/downgrade/upgrade; o trigger recusa `UPDATE` de outra coluna e `DELETE`;
  o índice parcial recusa duas `processando`.
