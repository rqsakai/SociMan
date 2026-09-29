# Modelo de dados: 003-contas-sociais

Tudo fica no PostgreSQL, na migration `0002_perfis`, com os arquivos no MinIO (bucket `sociman`).
Todas as tabelas de domínio usam o `AuditMixin` da 001 (`created_at`, `created_by`, `updated_at`,
`updated_by`).

## `perfis`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `slug` | text not null UNIQUE | `^[a-z0-9]+(-[a-z0-9]+)*$`, 2..60, **imutável** depois de criado (FR-002a) |
| `name` | text not null | 1..80, sem espaço nas pontas |
| `niche` | text not null default '' | até 200 |
| `bio` | text not null default '' | até 2000 |
| `language` | text not null default 'pt-BR' | tag BCP 47 simples (`pt-BR`, `en`, `es`…) |
| `status` | enum `perfil_status` (`em_preparacao`, `ativo`, `pausado`) | padrão `em_preparacao` |
| `logo_image_id` | uuid null FK → images.id | kind = `logo` |
| `banner_image_id` | uuid null FK → images.id | kind = `banner` |
| `version` | int not null default 1 | controle otimista e número da versão atual |
| `archived_at` / `archived_by` | timestamptz null / uuid null FK users | null = não arquivado |
| AuditMixin | | |

Índices: `(archived_at, status)` e `lower(name)` para a busca.

## `contas`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | |
| `platform` | enum `platform` (`tiktok`, `youtube`, `instagram`, `kwai`, `facebook`, `x`, `outra`) | |
| `platform_name` | text not null default '' | obrigatório (1..40) quando `platform = outra`; vazio nas demais |
| `handle` | text not null | normalizado `^[a-z0-9._-]{1,60}$` (sem `@`) |
| `url` | text not null | http(s); sugerido pelo template da plataforma; obrigatório em `outra` |
| `status` | enum `conta_status` (`planejada`, `ativa`, `pausada`, `encerrada`) | padrão `planejada` |
| `notes` | text not null default '' | até 500 |
| `version`, `archived_at`, `archived_by`, AuditMixin | | como em `perfis` |

Restrições (FR-005):
- `UNIQUE (platform, platform_name, handle)`: o mesmo @ não se repete na plataforma, contando
  também as arquivadas;
- `UNIQUE (perfil_id, platform, platform_name) WHERE status = 'ativa' AND archived_at IS NULL`: no
  máximo uma conta ativa por plataforma em cada perfil.

## `images`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | |
| `kind` | enum `image_kind` (`logo`, `banner`) | |
| `object_key` | text not null UNIQUE | `perfis/{perfil_id}/{uuid4}.{png\|jpg\|webp}` |
| `content_type` | text not null | `image/png`, `image/jpeg` ou `image/webp` (detectado pelo conteúdo) |
| `bytes` | int not null | até 5 MB |
| `width`, `height` | int not null | logo ≥ 200×200; banner ≥ 1000×250 |
| `sha256` | text not null | |
| `created_at`, `created_by` | | |

Imutável e nunca apagada (FR-010). O objeto no MinIO também nunca é apagado.

## `entity_versions` (histórico genérico, R1)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `entity_type` | text not null | `perfil`, `conta` (as próximas specs acrescentam) |
| `entity_id` | uuid not null | |
| `version` | int not null | `UNIQUE (entity_type, entity_id, version)` |
| `action` | text not null | `created`, `updated`, `archived`, `restored`, `reverted` |
| `actor_kind` | text not null | `user`, `system:cli` (`mcp_client` fica reservado para a 009) |
| `actor_user_id` | uuid null FK users | |
| `occurred_at` | timestamptz not null default now() | |
| `before` | jsonb null | snapshot antes (null em `created`) |
| `after` | jsonb not null | snapshot depois |
| `changed_fields` | text[] not null | campos que mudaram |
| `details` | jsonb not null default '{}' | ex.: `{"from_version": 3}` numa reversão |

Imutável: só recebe INSERT. Índice: `(entity_type, entity_id, version desc)`.

**Snapshot versionado:**
- **perfil:** `name`, `niche`, `bio`, `language`, `status`, `logo_image_id`, `banner_image_id`,
  `archived`. O `slug` aparece só para exibição e nunca é revertido.
- **conta:** `platform`, `platform_name`, `handle`, `url`, `status`, `notes`, `archived`.

## Estados
```
perfil:  em_preparacao ⇄ ativo ⇄ pausado      (qualquer transição permitida)
conta:   planejada ⇄ ativa ⇄ pausada ⇄ encerrada (qualquer transição; encerrada pode voltar)
qualquer registro:  ativo ──arquivar──▶ arquivado ──restaurar──▶ ativo   (cada passo = 1 versão)
reversão (só dono): estado atual ──reverter para vN──▶ estado de vN (nova versão, action=reverted)
```
