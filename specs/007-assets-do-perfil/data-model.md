# Modelo de dados: 007-assets-do-perfil

Tudo fica no PostgreSQL (NVMe), na migration `0005_assets` (ver research R11 sobre a ordem com a
006). Os arquivos continuam no bucket `sociman` do MinIO no HD, registrados na tabela `images`
da 003, que **não muda de forma** (só ganha dois valores de enum). As tabelas novas usam o
`AuditMixin` da 001 e o `_Versioned` da 003 (`version`, `archived_at`, `archived_by`). O
histórico é o `entity_versions`, com o novo `entity_type` **`asset`** (R4).

## `assets`
O item da biblioteca de um perfil.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | |
| `tipo` | enum `asset_tipo` (`avatar`, `cenario`, `fundo`, `sticker`, `marca_dagua`, `imagem`) | imutável |
| `name` | text not null | 1..80, sem espaço nas pontas |
| `description` | text not null default '' | até 2.000 (nota livre, princípio III: nunca fonte de regra) |
| `tags` | text[] not null default '{}' | até 20; cada uma 1..30, minúsculas, sem espaço nas pontas, sem repetição |
| `prompt` | text null | só `avatar` (**descrição para prompts**, FR-002) e `cenario` (**prompt do ambiente**, FR-003); até 2.000; guardado **exatamente** como enviado (sem trim), porque é copiado para o Flow/Veo (FR-009) |
| `voice_tone` | text null | só `avatar`; até 500 |
| `image_rules` | text null | só `avatar`; até 2.000 |
| `primary_file_id` | uuid null FK → asset_files.id (`use_alter`) | arquivo **ativo** do próprio asset; nos tipos de um arquivo é sempre o único arquivo |
| `version`, `archived_at`, `archived_by` | | `_Versioned` da 003 |
| AuditMixin | | `created_by`/`updated_by` |

Índices:
- `(perfil_id, archived_at, updated_at desc, id)`: grade e cursor (R8);
- GIN em `tags`;
- `(perfil_id, lower(name))`: busca por nome.

Check: `prompt`, `voice_tone` e `image_rules` nulos fora dos tipos que os usam
(`ck_assets_campos_por_tipo`). Nome **não** é único (envios rápidos geram nomes parecidos; o
id identifica).

**Snapshot versionado** (`__versioned_fields__`): `tipo` (imutável, `__immutable_fields__`),
`name`, `description`, `tags`, `prompt`, `voice_tone`, `image_rules`, `primary_file_id`,
`archived` e **`files`** (propriedade: a lista dos arquivos, ordenada por `role` e `position`,
com `id`, `image_id`, `role`, `look`, `uso`, `label`, `quando_usar`, `notes`, `position`,
`archived`).

## `asset_files`
Liga um asset a uma imagem e guarda o papel dela no asset. Sem `version` própria: toda mudança
aqui é uma versão do asset (R4).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `asset_id` | uuid not null FK → assets.id | |
| `image_id` | uuid not null UNIQUE FK → images.id | a imagem pertence ao mesmo perfil; uma imagem está em no máximo um asset |
| `role` | enum `asset_file_role` (`referencia`, `pose`, `arquivo`) | `avatar`: `referencia` ou `pose`; `cenario`: `referencia`; demais tipos: `arquivo` |
| `look` | text null | só `referencia` de avatar; 1..60 (ex.: "Cozinha, corpo inteiro"); agrupa as referências |
| `uso` | text null | só `referencia`; até 200 (ex.: "cenas de cozinha") |
| `label` | text null | **obrigatório** em `pose`; 1..60 (ex.: "apontando para o produto") |
| `quando_usar` | text null | só `pose`; até 300 |
| `notes` | text not null default '' | até 500 (ex.: "HeyGen look `012eb0ab…`") |
| `position` | int not null | ordem dentro de (`asset_id`, `role`), 0..n-1, sem buracos entre os ativos |
| `archived_at`, `archived_by` | | arquivar um arquivo (nunca apagar) |
| `created_at`, `created_by` | | |

Índices e restrições:
- UNIQUE parcial `(asset_id, lower(label)) WHERE role = 'pose' AND archived_at IS NULL` →
  409 `pose_label_in_use` ("Já existe uma pose com esse rótulo neste avatar");
- `(asset_id, role, position)`;
- nos tipos `fundo`, `sticker`, `marca_dagua` e `imagem`, **um** arquivo ativo (validado no
  service: enviar um segundo dá 400 `invalid_asset`; arquivar o único dá 400, "arquive o asset").

## `images` (da 003; só enum)
- `image_kind` ganha `avatar` e `imagem` (R3). A tabela é a mesma: imutável, nunca apagada.
- **Classe técnica por tipo do asset** (a validação continua sendo `imaging.validate_image` pelo
  `kind`):

| Tipo do asset | `images.kind` | Formatos | Transparência | Mínimo |
|---|---|---|---|---|
| `avatar` | `avatar` | PNG, JPG, WebP | – | 256×256 |
| `cenario` | `fundo` | PNG, JPG, WebP | – | 540×540 |
| `fundo` | `fundo` | PNG, JPG, WebP | – | 540×540 |
| `sticker` | `watermark` | PNG, WebP | exige | 64×64 |
| `marca_dagua` | `watermark` | PNG, WebP | exige | 64×64 |
| `imagem` | `imagem` | PNG, JPG, WebP | – | 64×64 |

- Limite pelas rotas da biblioteca: **20 MB** e 40 megapixels. Logo, banner e as rotas antigas da
  004 continuam com 5 MB.
- Chave do objeto: `perfis/{perfil_id}/{uuid4}.{ext}` (a mesma da 003/004; impossível de
  adivinhar).

## Uso (sem tabela; R5)
Calculado a cada leitura pelos provedores registrados em `assets/usos.py`:

```text
Uso { origem: "kit" | "corte" | <futuro: "roteiro" | "cena" …>,
      rotulo: str        # "Card final (kit v3)", "Marca d'água (kit v3)", "12 cortes"
      campo: str | null  # "endCard.fundo_imagem_id"
      file_id: uuid      # o arquivo do asset que está em uso
      bloqueia: bool     # kit: true; corte: false
      href: str | null } # rota do SPA
```
- **kit:** `watermark.imagem_id`, `hook.fundo_imagem_id`, `endCard.fundo_imagem_id` **não nulos**
  nos tokens vigentes (`fields_using_image`), mesmo com a seção desligada;
- **corte:** cortes do perfil com a `object_key` da imagem em `kit_tokens`
  (`watermark.imagem_key`, `hook.fundo_imagem_key`, `end_card.fundo_imagem_key`); informativo.

## Estados
```
asset:   ativo ──arquivar (sem uso que bloqueia)──▶ arquivado ──restaurar──▶ ativo
arquivo: ativo ──arquivar (sem uso que bloqueia; não o único dos tipos simples)──▶ arquivado ──restaurar──▶ ativo
         (restaurar uma pose cujo rótulo já está em uso por outra ativa → 409 pose_label_in_use)
versões: criar = v1 (`created`); cada mutação = +1 (`updated`, `archived`, `restored`);
         reverter (só dono) = +1 (`reverted`), arquivando os arquivos que não existiam na versão alvo
```
Nenhum estado apaga linha nem objeto. Arquivar o asset não arquiva os arquivos (restaurar volta
tudo como estava). Imagem de asset arquivado **sai dos seletores** e o kit recusa salvá-la
(`invalid_kit`), mas os links de mídia e os cortes que já a usam continuam funcionando.

## Validação por tipo (400 `invalid_asset`, com `field`)
- campos de avatar (`prompt`, `voice_tone`, `image_rules`) só em `avatar`; `prompt` também em
  `cenario`; enviados em outro tipo → "campo não se aplica a este tipo";
- `role` compatível com o tipo; `look`/`uso` só em `referencia`; `label`/`quando_usar` só em
  `pose`; `label` obrigatório em `pose`;
- `primary_file_id` precisa ser arquivo ativo do asset;
- reordenar: a lista precisa ter **exatamente** os arquivos ativos daquele `role`.

## Migração (`0005_assets`, R2)
1. `ALTER TYPE image_kind ADD VALUE IF NOT EXISTS 'avatar'` e `'imagem'` (não usados na mesma
   transação);
2. `CREATE TYPE asset_tipo`, `asset_file_role`; `CREATE TABLE assets`, `asset_files`; índices;
3. `backfill(conn)`: para cada `images` com `kind IN ('watermark','fundo')` sem `asset_files`,
   em ordem de `created_at, id` por perfil e tipo:
   - `assets` (`tipo` = `marca_dagua` para `watermark`, `fundo` para `fundo`; `name` = "Marca
     d'água N" / "Fundo N"; `created_at`/`created_by` da imagem; `version = 1`);
   - `asset_files` (`role = arquivo`, `position = 0`) e `assets.primary_file_id`;
   - `entity_versions` v1 `created`, `actor_kind = 'system:migration'`,
     `details = {"migracao": "0005_assets", "image_id": …}`;
   - idempotente (o filtro "sem `asset_files`" não acha nada na segunda vez).
4. **Downgrade:** recusa se existir asset criado depois da migração (`actor_kind <> 'system:migration'`
   em alguma v1) ou imagem `avatar`/`imagem`; senão remove as tabelas e os tipos novos e recria o
   `image_kind` sem os dois valores (como a `0004`). Nada de objeto é apagado.

## Onde a 004 muda (só isto)
- `service_kit.ref_context`: `watermark_image_ids`/`fundo_image_ids` passam a exigir imagem em
  arquivo **ativo** de asset **ativo** do perfil (com o `kind` de hoje);
- `marca/tokens.py`: função pura nova `fields_using_image(kit, image_id) -> list[str]`;
- `marca/router_marca_dagua.upload_image` (usado também por `router_fundos`): cria o asset junto
  com a imagem (rotas antigas continuam, marcadas `deprecated`).
