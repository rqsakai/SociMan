# Modelo de dados: 020-historico-tiktok-studio

Tudo fica no PostgreSQL (NVMe), na migration **`0013_historico_studio`** (down_revision
**`0012_guia_comunicacao`**). Antes de gerar a migration, confira que nenhuma outra spec já ocupou o
número 0013. **Nada vai para o MinIO nem para o HD:** os arquivos são lidos em memória, e a
pré-visualização fica no Redis (research R2 e R4).
- Pacote novo: `apps/api/src/sociman_api/metricas/studio/` (plan, Project Structure).
- `entity_type` novo: **`studio_importacao`** (histórico, princípio VII).
- Os dias importados são **observações só de inserção**, como as fotos da 016, com trigger no banco.

## Enum novo: `studio_importacao_estado`
`ativa` · `desfeita`.

## `metricas_studio_importacoes` (nova, versionada)
Uma confirmação do dono para uma série da 016.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `serie_id` | uuid not null FK → metricas_series.id | a série **viva** da conta no momento (R5) |
| `secoes` | text[] not null | subconjunto de `{visao_geral, seguidores}`, não vazio |
| `sha_visao_geral` | text null | SHA-256 (hex) dos bytes do `Overview.csv`; `NULL` se a seção não veio |
| `sha_seguidores` | text null | SHA-256 do `FollowerHistory.csv` |
| `periodo_de`, `periodo_ate` | date not null | menor e maior dia gravado (das duas seções) |
| `ano_origem` | text not null | `nome_zip`, `deduzido` ou `misto` (uma seção de cada jeito, R3); `ck_studio_imp_ano` |
| `contagens` | jsonb not null | por seção: `{gravados, iguais, divergentes, coletados, faltando, ignorados}` |
| `nomes_arquivos` | text[] null | os nomes enviados (contêm o @); **fora do snapshot**; `NULL` depois de anonimizar (R9) |
| `estado` | `studio_importacao_estado` not null default `ativa` | |
| `criada_em` | timestamptz not null default now() | ordem de prioridade (a ativa mais antiga vale) |
| `criada_por` | uuid not null FK → users.id | sempre um dono humano |
| `desfeita_em` | timestamptz null | |
| `desfeita_por` | uuid null FK → users.id | |
| `version` | int not null | controle otimista e histórico |
| `created_at`, `updated_at` | timestamptz | `AuditMixin` |

Regras:
- `ck_studio_imp_secoes`: `cardinality(secoes) BETWEEN 1 AND 2 AND secoes <@ ARRAY['visao_geral','seguidores']`;
- `ck_studio_imp_sha`: `('visao_geral' = ANY(secoes)) = (sha_visao_geral IS NOT NULL)` e o mesmo para
  `seguidores`;
- `ck_studio_imp_desfeita`: `(estado = 'desfeita') = (desfeita_em IS NOT NULL AND desfeita_por IS NOT NULL)`;
- `ck_studio_imp_periodo`: `periodo_de <= periodo_ate`;
- `ck_studio_imp_ano`: `ano_origem IN ('nome_zip','deduzido','misto')`;
- `ix_studio_imp_serie (serie_id, estado, criada_em, id)`;
- `ix_studio_imp_sha_vg (serie_id, sha_visao_geral) WHERE estado = 'ativa'` e o mesmo para
  `sha_seguidores` (idempotência, R5). Os índices **não são únicos**: a conferência é feita no service,
  sob o lock da série, porque um envio com uma seção repetida e outra nova é válido.
- `__versioned_fields__ = ("estado", "secoes", "periodo_de", "periodo_ate", "ano_origem", "contagens",
  "sha_visao_geral", "sha_seguidores", "desfeita_em", "desfeita_por")`, `__immutable_fields__ = ()`. Não
  há rota de revert genérico para esta entidade (R8).

## `metricas_studio_dias` (nova, **só inserção**)
Uma linha por dia de uma importação. As colunas de uma seção ficam `NULL` quando ela não veio.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `importacao_id` | uuid not null FK → metricas_studio_importacoes.id | |
| `serie_id` | uuid not null FK → metricas_series.id | copiado da importação (consultas por série) |
| `dia` | date not null | dia de calendário do arquivo (R14) |
| `tem_visao_geral` | boolean not null | a linha veio do `Overview.csv` |
| `views` | bigint null | `Video Views` do dia; not null quando `tem_visao_geral` |
| `visitas_perfil` | bigint null | `Profile Views` (opcional) |
| `likes`, `comments`, `shares` | bigint null | opcionais |
| `tem_seguidores` | boolean not null | a linha veio do `FollowerHistory.csv` |
| `seguidores` | bigint null | total no dia; not null quando `tem_seguidores` |
| `seguidores_dif` | bigint null | a diferença para o dia anterior (pode ser negativa) |

Regras:
- `uq_studio_dias_imp_dia (importacao_id, dia)`;
- `ck_studio_dias_secao`: `tem_visao_geral OR tem_seguidores`, `tem_visao_geral = (views IS NOT NULL)` e
  `tem_seguidores = (seguidores IS NOT NULL)`;
- `ck_studio_dias_naoneg`: `views`, `visitas_perfil`, `likes`, `comments`, `shares` e `seguidores` são
  `>= 0` quando não nulos;
- `ix_studio_dias_serie_dia (serie_id, dia)`: leitura efetiva (R6) e cobertura;
- trigger **`metricas_studio_so_insercao`** (`BEFORE UPDATE OR DELETE … FOR EACH ROW EXECUTE FUNCTION
  metricas_recusa_mudanca()`). A função vem da 0011, e o `TRUNCATE` dos testes e do `reset-db` continua.

## Estado efêmero: pré-visualização (Redis, **não** é tabela)
A chave `studio:previa:<uuid>`, com TTL de 1800 s, guarda este JSON:
```json
{
  "userId": "…", "contaId": "…", "serieId": "…", "criadaEm": "…",
  "exigeConfirmacaoConta": false, "anoOrigem": "nome_zip",
  "secoes": {
    "visao_geral": {"sha": "…", "linhas": [{"dia": "2026-09-25", "views": 118, "visitasPerfil": 0, "likes": 5, "comments": 0, "shares": 0}]},
    "seguidores":  {"sha": "…", "linhas": [{"dia": "2026-09-25", "seguidores": 0, "seguidoresDif": 0}]}
  },
  "nomesArquivos": ["Overview_2026-09-25_1790891174_contateste.zip", "Followers_contateste.zip"],
  "base": {"ativas": [["<id>", 1]], "primeiroDiaCoberto": "2026-10-01"}
}
```
O confirmar lê e apaga a chave de uma vez (`GETDEL`). Se a chave não existe, a resposta é 410
`previa_indisponivel`. Se a `base` mudou, é 409 `previa_desatualizada`.

## Regras derivadas (sem coluna)

### Dia coberto pela coleta (R6)
`primeiro_dia_coberto(serie) = dia_APP_TZ(min(coletado_em das fotos de conta e de vídeo da série)) + 1`.
Um dia `d` está coberto quando `primeiro_dia_coberto` não é nulo e `d >= primeiro_dia_coberto`.

### Valor efetivo do Studio
Por (série, dia, seção), vale a linha da importação **ativa** mais antiga (`criada_em`, `id`) com
`tem_<secao>`.
```sql
SELECT DISTINCT ON (d.serie_id, d.dia) d.*
FROM metricas_studio_dias d JOIN metricas_studio_importacoes i ON i.id = d.importacao_id
WHERE i.estado = 'ativa' AND d.tem_visao_geral AND d.serie_id = ANY(:series) AND d.dia BETWEEN :de AND :ate
ORDER BY d.serie_id, d.dia, i.criada_em, i.id;
```
(e o mesmo com `tem_seguidores`).

### Fonte do dia no analytics (FR-013)
| Situação (série, dia) | Fonte | Valor | `comparacao` |
|---|---|---|---|
| coberto | `coletado` | ganhos da API do dia | o Studio efetivo, se houver |
| não coberto + Studio efetivo | `studio` | o Studio | ganhos da API do dia, se houver foto |
| não coberto, sem Studio | `coletado` | ganhos da API (como na 019) | — |

Seguidores ganhos no dia `studio` = `seguidores_dif` (ou `seguidores(d) − seguidores(d−1)` quando a
diferença falta). Visitas ao perfil só existem no Studio.

### Contagens da pré-visualização (por seção, para cada dia válido do arquivo)
- `ignorados`: dia = hoje.
- `iguais`: já existe um valor efetivo daquela seção com os mesmos números.
- `divergentes`: já existe um valor efetivo com números diferentes (continua valendo o anterior).
- `coletados`: o dia está coberto pela coleta (o dia é gravado, mas vale a API).
- `gravados`: todos os dias válidos (inclui os acima, exceto `ignorados`).
- `faltando`: os dias ausentes entre o primeiro e o último dia do arquivo.

A ordem de classificação é `ignorados` → `coletados` → `iguais`/`divergentes` → novos. A divergência
com a coleta (FR-009) é avisada à parte: |Σ Studio − Σ API| ÷ Σ API > 0,30 nos dias cobertos.

## Mudanças em tabelas e código existentes
| Onde | Mudança |
|---|---|
| `metricas_series`, fotos | **nenhuma** |
| `metricas/anonimizar.serie` | `nomes_arquivos = NULL` nas importações da série; `details.importacoes` (R9) |
| `metricas/export.py`, `dicionario.py` | `studio_dias.csv` e `DICIONARIO_VERSAO = 2` (R10) |
| `analytics/base.py`, `visao_geral.py`, `quando_postar.py` (calendário), `contas.py`, `schemas.py` | `totais_diarios`, fontes e campos novos (R7) |
| `.gitignore` | `Overview_*.zip`, `Followers_*.zip`, `Content_*.zip`, `Viewers_*.zip` |

## Histórico (princípio VII)
| Evento | `entity_type` | `action` | `details` |
|---|---|---|---|
| importação confirmada | `studio_importacao` | `created` | `{secoes, gravados}` (sem nome de arquivo) |
| importação desfeita | `studio_importacao` | `updated` | `{acao: "desfeita"}` |
| recusa a quem não é humano | evento de segurança `publicacao_recusada` | `denied` | `{rota, actorKind, contaId}` (guarda da 015) |

Não há revert genérico: desfazer **é** a reversão (R8).

## Estados
```text
(prévia no Redis) ──confirmar──► ativa ──desfazer (dono)──► desfeita (final; reimportar cria outra)
prévia ──TTL 30 min / cancelar──► (some)
```

## Migration `0013_historico_studio`
**Upgrade:**
1. `CREATE TYPE studio_importacao_estado AS ENUM ('ativa','desfeita')`;
2. as 2 tabelas, com os CHECKs e índices;
3. o trigger `metricas_studio_so_insercao` em `metricas_studio_dias` (a função da 0011 é reaproveitada).

Não há backfill.

**Downgrade:** `DROP TRIGGER`; `DROP TABLE metricas_studio_dias`, depois `metricas_studio_importacoes`;
`DROP TYPE`. A função `metricas_recusa_mudanca` continua (é da 0011). As versões
`entity_versions` com `entity_type = 'studio_importacao'` ficam (histórico imutável, sem FK).

**`test_migration_0013`:**
- sobe sobre uma base da 0012 com séries vivas e anônimas;
- confere cada CHECK com `INSERT` direto;
- confere que o trigger recusa `UPDATE`/`DELETE` em `metricas_studio_dias` e que o `TRUNCATE` funciona;
- desce e sobe de novo.
