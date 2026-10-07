# Modelo de dados: 022-publico

Tudo fica no PostgreSQL (NVMe), na migration **`0017_publico`** (`down_revision = "0016_importacao"`).
Antes de gerar a migration, confira que nenhuma outra spec ocupou o número 0017 (a 023 vai usar a 0018 em
cima desta). **Nada vai para o MinIO nem para o HD:** os arquivos são lidos em memória, e a prévia fica no
Redis (020, R2 e R4).
- **Pacote:** `apps/api/src/sociman_api/metricas/studio/`, só por acréscimo (plan, Project Structure).
- **`entity_type`:** continua `studio_importacao`. Não há entidade nova versionada.
- **Observações novas:** são **só de inserção**, como os dias da 020, com trigger no banco.

## `metricas_studio_importacoes` (da 020, **colunas aditivas**)

| Coluna nova | Tipo | Regras |
|---|---|---|
| `sha_genero` | text null | SHA-256 dos bytes do `FollowerGender.csv` |
| `sha_territorios` | text null | SHA-256 do `FollowerTopTerritories.csv` |
| `sha_atividade` | text null | SHA-256 do `FollowerActivity.csv` |
| `sha_espectadores` | text null | SHA-256 dos bytes do **`Viewers.xlsx`** (o arquivo da planilha, não o ZIP) |
| `data_foto` | date null | a data das fotos de gênero e territórios desta importação (FR-012) |
| `data_foto_origem` | text null | `historico` (dia seguinte ao último do `FollowerHistory.csv` do mesmo ZIP, limitado a hoje) ou `importacao` (dia da importação) |
| `secoes_vazias` | text[] not null default `'{}'` | as seções de público que vieram só com o cabeçalho neste envio (R5) |

**`secoes`** passa a aceitar `{visao_geral, seguidores, genero, territorios, atividade, espectadores}`.

Regras:
- **`ck_studio_imp_secoes` (trocado):** `cardinality(secoes) BETWEEN 1 AND 6 AND secoes <@
  ARRAY['visao_geral','seguidores','genero','territorios','atividade','espectadores']`.
- **`ck_studio_imp_sha` (da 020, mantido)** e o novo `ck_studio_imp_sha_publico`: `('genero' = ANY(secoes))
  = (sha_genero IS NOT NULL)`, e o mesmo para `territorios`, `atividade` e `espectadores`.
- **`ck_studio_imp_foto`:** `(('genero' = ANY(secoes)) OR ('territorios' = ANY(secoes))) = (data_foto IS NOT
  NULL)` e `(data_foto IS NULL) = (data_foto_origem IS NULL)` e `data_foto_origem IN
  ('historico','importacao')`.
- **`ck_studio_imp_vazias`:** `secoes_vazias <@ ARRAY['genero','territorios','atividade','espectadores']
  AND NOT (secoes && secoes_vazias)`.
- **Índices parciais (não únicos):** `ix_studio_imp_sha_gen`, `ix_studio_imp_sha_ter`, `ix_studio_imp_sha_atv`
  e `ix_studio_imp_sha_esp`, cada um em `(serie_id, sha_<secao>) WHERE estado = 'ativa'`, como os da 020.
- **`periodo_de`/`periodo_ate`:** o mínimo e o máximo de todos os dias **e da data da foto** gravados.
- **`ano_origem`:** a regra da 020 nas seções diárias gravadas. Uma importação só com fotos usa o
  `anoOrigem` do `FollowerHistory.csv` lido (origem `historico`) ou `deduzido` (origem `importacao`).
- **`contagens`:** ganha as chaves das seções novas:
  - fotos: `{gravados, iguais, divergentes, semDado}`, onde `gravados` são os rótulos;
  - atividade: `{gravados, iguais, divergentes, ignorados, semDado}`, por (dia, hora);
  - espectadores: `{gravados, iguais, divergentes, faltando, ignorados, semDado}`.
- **`__versioned_fields__`:** os da 020, mais `sha_genero`, `sha_territorios`, `sha_atividade`,
  `sha_espectadores`, `data_foto`, `data_foto_origem` e `secoes_vazias`. O `nomes_arquivos` continua fora.

## `metricas_studio_distribuicoes` (nova, **só inserção**)

Uma linha por rótulo de uma foto (gênero ou territórios) de uma importação.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `importacao_id` | uuid not null FK → metricas_studio_importacoes.id | |
| `serie_id` | uuid not null FK → metricas_series.id | copiado da importação |
| `tipo` | text not null | `genero` ou `territorio` |
| `data_foto` | date not null | igual à `data_foto` da importação |
| `rotulo` | text not null | gênero normalizado (`masculino`, `feminino`, `outro`) ou território como veio (sem espaço nas pontas, até 64 caracteres) |
| `pct` | numeric(6,3) null | de 0 a 100 (a fração vira %); `NULL` = "sem dado" (`undefined`) |

Regras:
- `uq_studio_dist_imp (importacao_id, tipo, rotulo)`;
- `ck_studio_dist_tipo`: `tipo IN ('genero','territorio')`;
- `ck_studio_dist_genero`: `tipo <> 'genero' OR rotulo IN ('masculino','feminino','outro')`;
- `ck_studio_dist_pct`: `pct IS NULL OR pct BETWEEN 0 AND 100`;
- `ck_studio_dist_rotulo`: `length(rotulo) BETWEEN 1 AND 64`;
- `ix_studio_dist_serie (serie_id, tipo, data_foto)`;
- trigger **`metricas_studio_dist_so_insercao`** (`metricas_recusa_mudanca()`).

## `metricas_studio_atividade` (nova, **só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `importacao_id` | uuid not null FK | |
| `serie_id` | uuid not null FK | |
| `dia` | date not null | dia de calendário do arquivo |
| `hora` | smallint not null | 0–23, **como veio** no arquivo (R13) |
| `ativos` | bigint null | `>= 0`; `NULL` = "sem dado" |

Regras: `uq_studio_atv_imp (importacao_id, dia, hora)`; `ck_studio_atv_hora` (`hora BETWEEN 0 AND 23`);
`ck_studio_atv_naoneg`; `ix_studio_atv_serie (serie_id, dia, hora)`; trigger
**`metricas_studio_atv_so_insercao`**.

## `metricas_studio_espectadores` (nova, **só inserção**)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | bigint identity PK | |
| `importacao_id` | uuid not null FK | |
| `serie_id` | uuid not null FK | |
| `dia` | date not null | |
| `total` | bigint null | `Total Viewers`; `NULL` = "sem dado" |
| `novos` | bigint null | `New Viewers` |
| `recorrentes` | bigint null | `Returning Viewers` |

Regras: `uq_studio_esp_imp (importacao_id, dia)`; `ck_studio_esp_naoneg` (os 3 `>= 0` quando não nulos);
`ix_studio_esp_serie (serie_id, dia)`; trigger **`metricas_studio_esp_so_insercao`**.

Uma linha com os 3 nulos é válida: o dia existe no arquivo, mas a TikTok não informou (FR-007).

## Estado efêmero: prévia (Redis, a chave da 020)

`studio:previa:<uuid>` (TTL de 1800 s) ganha `publico` e `vazias`. Os campos que já existiam não mudam.

```json
{
  "…": "campos da 020 (userId, contaId, serieId, secoes, nomesArquivos, base…)",
  "publico": {
    "genero":      {"sha": "…", "dataFoto": "2026-10-02", "dataFotoOrigem": "historico",
                    "anoOrigem": "deduzido", "itens": [{"rotulo": "feminino", "pct": 61.0}]},
    "territorios": {"sha": "…", "dataFoto": "2026-10-02", "dataFotoOrigem": "historico",
                    "anoOrigem": "deduzido", "itens": [{"rotulo": "BR", "pct": 92.5}]},
    "atividade":   {"sha": "…", "anoOrigem": "deduzido",
                    "linhas": [{"dia": "2026-09-25", "hora": 0, "ativos": 3}]},
    "espectadores":{"sha": "…", "anoOrigem": "deduzido",
                    "linhas": [{"dia": "2026-09-25", "total": null, "novos": 0, "recorrentes": 0}]}
  },
  "vazias": ["genero", "territorios", "atividade"]
}
```

Cada seção traz também `contagens`, como na 020. O confirmar continua `GETDEL` + `base`.

## Regras derivadas (sem coluna)

### Valor efetivo (a importação ativa mais antiga vale)
| Seção | Chave do efetivo |
|---|---|
| gênero e territórios | (série, tipo, data da foto): **a foto inteira** da importação ativa mais antiga daquela data (os rótulos não se misturam entre importações) |
| atividade | (série, dia, hora) |
| espectadores | (série, dia) |

```sql
-- foto efetiva por data
SELECT DISTINCT ON (d.serie_id, d.tipo, d.data_foto) d.importacao_id, d.serie_id, d.tipo, d.data_foto
FROM metricas_studio_distribuicoes d JOIN metricas_studio_importacoes i ON i.id = d.importacao_id
WHERE i.estado = 'ativa' AND d.serie_id = ANY(:series) AND d.tipo = :tipo
ORDER BY d.serie_id, d.tipo, d.data_foto, i.criada_em, i.id;
-- e depois os rótulos dessa importação
```

### Foto válida para o período (FR-016, resposta A)
- `valida = a foto efetiva de maior data_foto ≤ ate`, com `anteriorAoPeriodo = data_foto < de`;
- `comparacao = a foto efetiva de maior data_foto ≤ (de − 1 dia)`, só quando a data é **diferente** da
  `valida`;
- `difPp(rotulo) = pct_valida − pct_comparacao`, quando os dois existem. Um rótulo presente numa foto e
  ausente na outra fica com `difPp = null` e a marca "novo" ou "saiu";
- `outrosPct = 100 − Σ pct` (só territórios; `null` se algum pct é nulo).
- `seguidoresNaData` = o `seguidores` efetivo da 020 (`metricas_studio_dias`) no dia anterior à
  `data_foto` (o último dia do `FollowerHistory.csv`), ou `null` (FR-025).

### Mapa de atividade (FR-017, resposta A)
- `celula(d_semana, h) = média(ativos)` sobre os dias `dia ∈ [de, ate]` com `weekday(dia) = d_semana`,
  `hora = h` e `ativos` não nulo; `n` = número desses dias;
- `amostraPequena = 0 < n < MIN_DIAS_CELULA` (2);
- `ultimoDiaComDado` = o maior `dia` efetivo da série com `ativos` não nulo (qualquer período), para o
  atalho.

### Espectadores
- **Série:** um ponto por dia efetivo, com os 3 valores (nulos ficam nulos).
- **Indicadores:**
  - `novos` = Σ `novos` não nulos, com `n` = dias com valor;
  - `mediaTotal` = média dos `total` não nulos;
  - `mediaRecorrentes` = média dos `recorrentes` não nulos.

  Cada um traz o mesmo cálculo no período anterior (019) e a `variacaoPct` (`null` sem base).
- **Aviso da prévia** (FR-010): `total ≠ novos + recorrentes` quando os 3 não são nulos.

### Motivo do card vazio (FR-026)
| Situação (série, seção) | Motivo |
|---|---|
| nenhuma importação ativa com a seção, nem vazia | `sem_importacao` |
| a importação ativa mais recente que cita a seção a tem em `secoes_vazias` | `veio_vazia` |
| há dado, mas nada no período (só atividade e espectadores; as fotos usam a regra da foto válida) | `sem_dado_no_periodo` |

## Mudanças em tabelas e código existentes
| Onde | Mudança |
|---|---|
| `metricas_studio_importacoes` | colunas e CHECKs acima (aditivos; os da 020 continuam válidos para as linhas existentes) |
| `metricas_studio_dias`, `metricas_series`, fotos da 016 | **nenhuma** |
| `metricas/anonimizar.py` | nenhuma (o `nomes_arquivos = NULL` da 020 já cobre); teste novo |
| `metricas/export.py`, `dicionario.py` | 3 CSVs novos e `DICIONARIO_VERSAO = 3` |
| `analytics/schemas.py` | `PublicoOut` (novo) e `QuandoPostarOut.atividadeSeguidores` (aditivo) |
| `mcp/mapa.py` | `analytics_publico` como tool de leitura |
| `.gitignore` | `Viewers.xlsx`, `FollowerGender.csv`, `FollowerTopTerritories.csv` e `FollowerActivity.csv` (o `Viewers_*.zip` e o `Followers_*.zip` já estão lá) |

## Histórico (princípio VII)
| Evento | `entity_type` | `action` | `details` |
|---|---|---|---|
| importação confirmada | `studio_importacao` | `created` | `{secoes, gravados, vazias}` (sem rótulo, sem nome de arquivo) |
| importação desfeita | `studio_importacao` | `updated` | `{acao: "desfeita"}` (todas as seções juntas) |

## Migration `0017_publico`
**Upgrade:**
1. `ALTER TABLE metricas_studio_importacoes ADD COLUMN …` (as 7 colunas; `secoes_vazias` com default
   `'{}'`);
2. `DROP CONSTRAINT ck_studio_imp_secoes` e `ADD` com o conjunto ampliado; `ADD` dos CHECKs
   `ck_studio_imp_sha_publico`, `ck_studio_imp_foto` e `ck_studio_imp_vazias`; os 4 índices parciais;
3. as 3 tabelas, com os CHECKs, os índices e os triggers (a função `metricas_recusa_mudanca` vem da 0011).

Não há backfill: as importações da 020 ficam válidas com as colunas nulas e `secoes_vazias = '{}'`.

**Downgrade:**
1. `DROP TRIGGER` e `DROP TABLE` das 3 tabelas;
2. `DROP` dos índices e CHECKs novos;
3. recria o `ck_studio_imp_secoes` da 020. **Antes disso, recusa com erro claro** se existir importação com
   seção de público (o downgrade não pode apagar o histórico);
4. `DROP COLUMN` das 7 colunas.

**`test_migration_0017`:**
- sobe sobre uma base da 0016 com importações da 020 (ativas e desfeitas), que continuam válidas;
- confere cada CHECK novo com `INSERT` direto;
- os 3 triggers recusam `UPDATE`/`DELETE`, e o `TRUNCATE` passa;
- desce (sem público) e sobe de novo;
- o downgrade com público é recusado.
