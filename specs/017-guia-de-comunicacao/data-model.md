# Modelo de dados: 017-guia-de-comunicacao

Tudo fica no PostgreSQL (NVMe), na migration **`0012_guia_comunicacao`** (`down_revision =
"0011_metricas_tiktok"`, que já existe e está aplicada no dev; ver "Numeração" no fim). Uma tabela
nova (`ia_guias`), um enum novo (`guia_emojis`) e 4 colunas em `ia_chamadas`. Nenhum dado existente
muda.

## `ia_guias` (nova; `entity_type = "ia_guia"`)

Uma linha por perfil (`conta_id IS NULL`) e no máximo uma por conta. A linha nasce na primeira
edição (sem linha = sem guia; a API responde `version = 0` e os campos vazios). Sem
`archived_at` e sem DELETE: "limpar" é salvar vazio.

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid NOT NULL FK `perfis.id` | também no guia da conta (o perfil da conta) |
| `conta_id` | uuid NULL FK `contas.id` | NULL = guia do perfil |
| `tom` | text NOT NULL DEFAULT `''` | CHECK `char_length(tom) <= 500` |
| `faca` | text[] NOT NULL DEFAULT `'{}'` | CHECK `cardinality(faca) <= 10` |
| `nao_faca` | text[] NOT NULL DEFAULT `'{}'` | CHECK `cardinality(nao_faca) <= 10` |
| `vocabulario` | text[] NOT NULL DEFAULT `'{}'` | CHECK `cardinality(vocabulario) <= 30` |
| `proibidas` | text[] NOT NULL DEFAULT `'{}'` | CHECK `cardinality(proibidas) <= 30` |
| `emojis` | `guia_emojis` NULL | `nao` \| `moderado` \| `livre`; NULL = não definido (na conta, herda) |
| `emojis_preferidos` | text[] NOT NULL DEFAULT `'{}'` | CHECK `cardinality(...) <= 10` |
| `hashtags_fixas` | text[] NOT NULL DEFAULT `'{}'` | CHECK `cardinality(hashtags_fixas) <= 8 AND (conta_id IS NOT NULL OR cardinality(hashtags_fixas) <= 5)`; já normalizadas (`#…`) |
| `max_hashtags_fixas` | int NULL | CHECK `max_hashtags_fixas IS NULL OR (conta_id IS NOT NULL AND max_hashtags_fixas BETWEEN 0 AND 8)`; só no guia da conta; NULL = padrão 5 (Q3) |
| `exemplos` | jsonb NOT NULL DEFAULT `'[]'` | lista de `{"tipo": "titulo"\|"legenda"\|"bordao", "texto": str}`; CHECK `jsonb_array_length(exemplos) <= 5` |
| `version` | int NOT NULL DEFAULT 1 | controle otimista e nº da versão atual |
| `created_at`, `created_by`, `updated_at`, `updated_by` | `AuditMixin` | |

Índices e restrições:
- `uq_ia_guias_perfil` UNIQUE `(perfil_id) WHERE conta_id IS NULL`;
- `uq_ia_guias_conta` UNIQUE `(conta_id) WHERE conta_id IS NOT NULL`;
- o par (conta, perfil da conta) é garantido pelo service (a conta é carregada e o `perfil_id` vem
  dela; nunca do cliente).

Limites por item (1..200 em faça/não faça, 1..60 em vocabulário e proibidas, 1..16 em emojis,
1..500 nos exemplos, hashtags pela regra da 006) e o **total ≤ 4.000 caracteres** ficam no
Pydantic/service (R2), não em CHECK: o banco guarda o que já passou.

Modelo SQLAlchemy (`ia/models.py`):

```python
class GuiaEmojis(enum.StrEnum):
    nao = "nao"; moderado = "moderado"; livre = "livre"

class IaGuia(AuditMixin, Base):
    __tablename__ = "ia_guias"
    __versioned_fields__ = ("perfil_id", "conta_id", "tom", "faca", "nao_faca", "vocabulario",
                            "proibidas", "emojis", "emojis_preferidos", "hashtags_fixas",
                            "max_hashtags_fixas", "exemplos")
    __immutable_fields__ = ("perfil_id", "conta_id")
```

### Validação no save (service_guia)

Na ordem, tudo no mesmo PUT (ou revert), com erros campo a campo (`details.fields`):
1. **limites** do R2 (por item, por lista, total); itens aparados, vazios descartados, repetidos
   (normalizados) recusados;
2. **hashtags fixas** normalizadas pela `normalizar_hashtag` da 006; inválidas recusadas;
3. **proibidas do efetivo** (este guia ∪ o outro nível): nenhuma pode aparecer (palavra inteira,
   R7) no `tom`, `faca`, `nao_faca`, `vocabulario`, `exemplos` nem nas `hashtags_fixas` **deste**
   guia → `"exemplos.2.texto": "usa a palavra proibida 'clickbait'"`;
4. **máximo de fixas** (Q3): `max_hashtags_fixas` só no guia da conta (no perfil, não nulo → 400
   em `maxHashtagsFixas`); 0..8 (`textos.HASHTAGS_MAX`);
5. **cruzada**, conforme o nível, com `M(conta) = conta.max_hashtags_fixas ?? 5` e `F(conta)` =
   fixas do perfil, na ordem, depois as da conta, sem repetir:
   - guia da **conta**: `|F(conta)| ≤ M(conta)` com os valores do formulário → 400 em
     `hashtagsFixas` ("perfil e conta somam 6 hashtags fixas; o máximo desta conta é 5");
   - guia do **perfil**: para cada conta **não arquivada** do perfil, **com ou sem guia**:
     `|F(conta)| ≤ M(conta)`; e, nas contas com guia, nenhuma proibida nova do perfil aparece no
     conteúdo do guia da conta → 400 com `details.contas = [{contaId, rotulo, campos}]` e a
     mensagem "A conta TikTok @x usa 'clickbait' no vocabulário; tire de lá antes" ou "A conta
     YouTube @x aceita no máximo 3 hashtags fixas; perfil e conta somariam 4".

### Histórico

`entity_versions` com `entity_type = "ia_guia"`, `entity_id = ia_guias.id`:
- `created` (1ª edição), `updated`, `reverted` (`details.from_version`);
- `details.ia = [...]` quando o save veio de uma proposta do "montar" (008, `aplicacao.marcar`);
- a lista de versões é pedida pelo dono do guia (`/api/perfis/{id}/guia/versions`,
  `/api/contas/{id}/guia/versions`), que a API traduz para o `id` da linha.

## Estruturas de domínio (sem tabela; `ia/guia.py`)

```text
GuiaCampos     tom, faca[], naoFaca[], vocabulario[], proibidas[], emojis|None,
               emojisPreferidos[], hashtagsFixas[], maxHashtagsFixas|None (só conta),
               exemplos[{tipo, texto}]
GuiaBloco      campos: GuiaCampos, version: int, nivel: "perfil"|"conta", rascunho: bool
GuiasEmVigor   perfil: GuiaBloco|None, conta: GuiaBloco|None
GuiaEfetivo    proibidas[] (união, na forma do guia, com a forma normalizada ao lado)
               hashtagsFixas[] (perfil, depois conta, sem repetir; cortadas em maxHashtagsFixas
                              só no estado inválido herdado, com aviso)
               maxHashtagsFixas: int (conta ?? 5; 5 quando não há conta)
               emojis (conta ?? perfil), emojisPreferidos (conta se houver, senão perfil)
Conflito       campo, perfil, conta, mensagem          # só avisos (R5; + "hashtagsFixas" no
                                                       #   estado inválido herdado, R6)
```

Funções:
- `em_vigor(db, perfil_id, conta_id | None) → GuiasEmVigor` (2 consultas por chave única; um guia
  vazio conta como ausente);
- `fundir(perfil, conta) → GuiaEfetivo`;
- `conflitos(perfil, conta) → list[Conflito]`;
- `render(bloco, so_proibidas=False) → str` (os rótulos fixos do R4; seções vazias omitidas;
  `so_proibidas=True` rende só "Palavras proibidas:" para os tipos `so_proibidas`, Q1);
- `normalizar(texto) → str` e `achar_proibidas(textos, efetivo) → list[str]`;
- `tamanho(campos) → int` (a soma do R2).

## `ia_chamadas` (4 colunas novas)

| Coluna | Tipo | Regra |
|---|---|---|
| `guia_perfil_version` | int NULL | versão do guia do perfil usada; NULL = sem guia, ou tipo `so_proibidas` com o perfil sem proibidas (nada enviado) |
| `guia_conta_version` | int NULL | versão do guia da conta usada; NULL = sem conta (inclui todos os `so_proibidas`) ou sem guia |
| `guia_rascunho` | text NULL | CHECK `guia_rascunho IS NULL OR guia_rascunho IN ('perfil','conta')`; só em `guia.testar` |
| `proibidas` | text[] NOT NULL DEFAULT `'{}'` | proibidas encontradas na proposta final |

- `entity_type` passa a aceitar também `guia` (texto livre na coluna; só o service escreve);
  `entity_id` = id da linha do guia, ou NULL se o guia ainda não existe;
- no `guia.testar`, o nível em `guia_rascunho` grava a **versão base** do rascunho (0 se não havia
  guia salvo) e `entrada = {"guia": {...}}`;
- as linhas antigas ficam com NULL/`'{}'` (sem backfill: antes da 017 não havia guia).

## Tipos de campo (código, `ia/tipos.py`)

| id | entidade | formato | usa guia | regras |
|---|---|---|---|---|
| (10 dos 13 da 008) | — | — | `"completo"` | as próprias |
| `avatar.descricao_prompt`, `cenario.prompt_ambiente`, `avatar.regras_imagem` | `asset` | `texto` | `"so_proibidas"` (Q1: só as proibidas do perfil; a voz não entra) | as próprias |
| `guia.montar` | `guia` | `guia` | `"completo"`; o do perfil entra como referência no guia da conta | própria (padrão em `regras_padrao.py`, editável) |
| `guia.testar` | `postagem` | `variacoes` | `"completo"` (o do formulário + o salvo do outro nível) | as de `postagem.textos` (`regras_de`), fora da lista de regras |

`TipoCampo` ganha `usa_guia: Literal["completo", "so_proibidas"] = "completo"`, `regras_de: str |
None = None` e `listar_regras: bool = True`. O teste de cruzamento tipos × schemas da 008 ignora os `guia.*` (não há entidade salva com
esses campos; o `guia.montar` é cruzado com `GuiaIn`).

## Migration `0012_guia_comunicacao`

```text
upgrade:
  CREATE TYPE guia_emojis AS ENUM ('nao','moderado','livre')
  CREATE TABLE ia_guias (... como acima, inclusive max_hashtags_fixas e os CHECKs de fixas ...)
  CREATE UNIQUE INDEX uq_ia_guias_perfil ON ia_guias (perfil_id) WHERE conta_id IS NULL
  CREATE UNIQUE INDEX uq_ia_guias_conta  ON ia_guias (conta_id)  WHERE conta_id IS NOT NULL
  ALTER TABLE ia_chamadas ADD guia_perfil_version int, ADD guia_conta_version int,
        ADD guia_rascunho text, ADD proibidas text[] NOT NULL DEFAULT '{}',
        ADD CONSTRAINT ck_ia_chamadas_guia_rascunho CHECK (...)
downgrade (só dev):
  DROP das 4 colunas e da constraint; DROP TABLE ia_guias; DROP TYPE guia_emojis
  (as versões "ia_guia" em entity_versions ficam; são inofensivas)
```

**`test_migration_0012`:** upgrade → insere guia de perfil e de conta → o segundo guia de perfil
viola `uq_ia_guias_perfil` e o segundo da mesma conta viola `uq_ia_guias_conta` → `cardinality`
acima do limite viola o CHECK (6 fixas no perfil; 9 na conta) → `max_hashtags_fixas` no perfil ou
fora de 0..8 viola o CHECK → `guia_rascunho = 'outro'` viola `ck_ia_chamadas_guia_rascunho` →
chamadas antigas com `proibidas = '{}'` e versões NULL → downgrade → upgrade.

### Numeração (decidida)

- A `0011_metricas_tiktok` (016) **já existe e está aplicada no dev** (2026-09-30); a 017 fica com
  `0012_guia_comunicacao`, `down_revision = "0011_metricas_tiktok"`. Não há mais renumeração.
- As duas não tocam as mesmas tabelas. `alembic heads` com uma cabeça só antes de subir (quickstart
  §0).
