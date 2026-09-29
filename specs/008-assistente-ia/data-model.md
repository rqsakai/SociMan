# Modelo de dados: 008-assistente-ia

Migration: **`0008_assistente_ia`**, com `down_revision = "0007_envio_progresso"`. Tudo no
PostgreSQL (NVMe); nada no MinIO nem no HD.

Resumo:
- **nova** `ia_regras` (entidade de domínio versionada, `entity_type = "ia_regra"`);
- `sugestoes_texto` **renomeada** para `ia_chamadas` e ampliada (log das chamadas; R3);
- `entity_versions.details` ganha o uso `{"ia": [...]}` (sem mudança de schema; R10);
- os **tipos de campo** não são tabela: ficam em `ia/tipos.py` (R1). Idioma: `en` só em
  `avatar.descricao_prompt` e `cenario.prompt_ambiente`; todos os outros, inclusive
  `avatar.regras_imagem`, usam o idioma do perfil (Q2 = B).

## Tipo de campo (código, `ia/tipos.py`)

```text
TipoCampo {
  id: str                     # "avatar.descricao_prompt" … (13, tabela no research R1)
  rotulo: str                 # "Descrição para prompts do avatar"
  entidade: "asset"|"perfil"|"kit"|"postagem"
  campos: tuple[str, ...]     # ("prompt",) · ("titulo","descricao","hashtags") no postagem.textos
  tipos_asset: frozenset|None # {"avatar"}, {"cenario"} ou None (todos)
  onde: str                   # "Assets › Avatar › Descrição para prompts"
  idioma: "en"|"perfil"
  formato: "texto"|"lista"|"sugestoes"|"textos_postagem"
                              # lista = substitui (hashtags); sugestoes = seleção e acréscimo (kit, Q3)
  limites: { max_chars, min_chars, uma_linha, trim, max_itens, min_itens, max_chars_item,
             unicos, normalizar: None|"hashtag", max_sugestoes }   # max_sugestoes = 10 (só sugestoes)
  padrao: str                 # regras padrão (ia/regras_padrao.py)
  padrao_versao: int          # sobe quando o padrão muda no código
}
```

Teste de cruzamento: para cada tipo, os limites batem com o schema Pydantic do campo
(`AssetPatch`, `UpdatePerfilIn`, `KitTokens`, `UpdatePostagemIn`/`CreatePostagemIn`).

## `ia_regras`
Personalização das regras de um tipo de campo. **Sem linha = usa o padrão do código** (a linha
nasce na primeira edição, como o kit com `version = 0`).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | `entity_id` do histórico |
| `tipo_campo` | text not null **unique** | um id de `TIPOS`; validado no serviço (404 `ia_tipo_not_found`) |
| `texto` | text null | `NULL` = usa o padrão; senão 1..8.000 caracteres (check) |
| `padrao_versao` | int not null | `padrao_versao` do tipo no momento da última edição |
| `version` | int not null | controle otimista (409 `version_conflict`) |
| AuditMixin | | `created_at/by`, `updated_at/by` |

- `__versioned_fields__ = ("tipo_campo", "texto")`, `__immutable_fields__ = ("tipo_campo",)`.
- Mutações: `put_regras` (texto novo), `voltar_ao_padrao` (texto `NULL`, `details = {"padrao":
  true}`), `revert` (dono). Todas com `history.record` na mesma transação. Não há arquivamento
  (a linha nunca some; "voltar ao padrão" é o equivalente).
- Na API, a versão de um tipo sem linha é `0` (como o kit).

## `ia_chamadas` (antes `sugestoes_texto`)
Log de cada geração. **Só INSERT**, salvo as colunas de desfecho (R10), que são estado, sem
versão (como o progresso dos envios da 006).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | preservado da 006 (`postagens.sugestao_id` continua apontando) |
| `tipo_campo` | text not null | backfill `postagem.textos` |
| `perfil_id` | uuid not null FK → perfis.id | backfill pelo corte |
| `entity_type` | text not null | `asset`, `perfil`, `kit`, `postagem` ou `corte` (postagem ainda não criada e as linhas da 006) |
| `entity_id` | uuid null | id do alvo (null no `kit` nunca salvo) |
| `corte_id` | uuid **null** FK → cortes.id | era not null; só nos tipos de postagem |
| `conta_id` | uuid null FK → contas.id | nova; conta de destino nos tipos de postagem |
| `plataforma` | enum `platform` **null** | era not null; só nos tipos de postagem |
| `sessao_id` | uuid null | painel que gerou (R9); null nas linhas da 006 |
| `anteriores` | uuid[] not null default '{}' | chamadas enviadas como "Outra versão" ou "Gerar mais" |
| `aceitos` | text[] not null default '{}' | só `sugestoes`: itens marcados na sessão e ainda não aplicados, enviados como contexto (≤ 20) |
| `rejeitados` | text[] not null default '{}' | só `sugestoes`: itens mostrados na sessão e não marcados, enviados como contexto (≤ 100) |
| `instrucao` | text not null default '' | até 1.000 |
| `entrada` | jsonb null | o valor atual enviado (`{"texto"}`, `{"itens"}` ou `{"titulo",…}`) |
| `contexto_faltante` | text[] not null default '{}' | `kit`, `persona`, `transcricao`, `bio`, `nicho` |
| `proposta` | jsonb null | era `resultado`; formato do tipo (R4); null quando deu erro |
| `explicacao` | text not null default '' | ≤ 400 |
| `avisos` | text[] not null default '{}' | do modelo + do servidor |
| `excede` | bool not null default false | proposta acima do limite do campo (R4) |
| `ajustes` | text[] not null default '{}' | da 006 (cortes e normalizações do servidor) |
| `model` | text not null | pedido (`claude-sonnet-5-5`) |
| `model_servido` | text null | quem respondeu (fallback, R7) |
| `prompt_version` | text not null | versão da base fixa (`ia/1`; as linhas da 006 ficam `textos/1`) |
| `regras_version` | int not null default 0 | versão de `ia_regras` usada (0 = padrão) |
| `padrao_versao` | int null | `padrao_versao` do tipo quando usou o padrão |
| `erro_code` | text null | `unconfigured`, `timeout`, `refusal`, `invalid`, `api_error` |
| `erro_status` | int null | status HTTP do Claude, quando houve |
| `input_tokens`, `output_tokens`, `cache_read_tokens` | int null | da 006 |
| `cache_creation_tokens` | int null | novo |
| `custo_usd` | numeric(10,6) null | calculado na gravação (R7) |
| `precos_versao` | text null | ex.: `2026-09` |
| `duration_ms` | int not null | |
| `desfecho` | enum `ia_desfecho` not null default `sem_acao` | `sem_acao`, `aplicada`, `editada`, `descartada`, `erro` |
| `desfecho_em` | timestamptz null | |
| `desfecho_por` | uuid null FK → users.id | quem aplicou ou descartou |
| `aplicada_versao` | int null | versão da entidade em que foi aplicada (link com `entity_versions`); nas sugestões, a da última aplicação |
| `itens_aplicados` | text[] null | só `sugestoes`: texto final dos itens desta chamada que entraram no kit (acumula) |
| `created_at`, `created_by` | | da 006 |

Índices:
- `ix_ia_chamadas_created` (`created_at desc`, `id`): registro e resumo do mês;
- `ix_ia_chamadas_perfil_created` (`perfil_id`, `created_at desc`);
- `ix_ia_chamadas_tipo_created` (`tipo_campo`, `created_at desc`);
- `ix_ia_chamadas_sessao` (`sessao_id`) parcial `WHERE sessao_id IS NOT NULL`;
- o índice da 006 por `corte_id` é mantido (renomeado).

Regras:
- `erro_code` não nulo ⇔ `desfecho = 'erro'` (check);
- o desfecho só sai de `sem_acao` (para `aplicada`, `editada` ou `descartada`); `aplicada` e
  `editada` só pelo `ia.aplicacao.marcar` dentro de um save; `descartada` só pelo autor da chamada;
  uma chamada `aplicada`/`editada` não volta a `descartada`;
- uma chamada `texto`, `lista` ou `textos_postagem` pode ser aplicada uma vez (a segunda aplicação
  da mesma proposta, num save posterior, é ignorada pelo `marcar`);
- uma chamada `sugestoes` pode ser aplicada **mais de uma vez** (itens diferentes em saves
  diferentes): `itens_aplicados` acumula, `aplicada_versao` fica com a última, e o desfecho vai
  para `editada` se algum item aplicado foi editado (nunca volta de `editada` para `aplicada`);
- `aceitos` e `rejeitados` só não são vazios quando o tipo tem formato `sugestoes` (check no
  serviço; 400 `invalid_ia` no `gerar`); `itens_aplicados` só é gravado pelo `marcar`.

## `entity_versions.details` (sem mudança de schema)
Uma versão salva "com ajuda da IA" leva:

```json
{ "ia": [ { "campo": "prompt", "tipoCampo": "avatar.descricao_prompt",
            "chamadaId": "0b9e…", "desfecho": "editada" } ] }
```

Nas sugestões, cada item leva também `"itens": ["…", "…"]` (os itens daquela chamada que entraram
nesta versão).

O autor continua o humano (`actor_kind = "user"`). O `Version.details` já sai na API
(`perfis/schemas.py`), então o SPA só lê.

## Campo `ia` nos corpos de salvar (aditivo)
`IaAplicacao { tipoCampo: str, chamadaId: uuid, itens: list[str] | None }`, lista opcional com
até 10 itens (uma sessão de sugestões pode juntar itens de várias chamadas), em:
`AssetPatch`, `UpdatePerfilIn`, `KitIn` (fora de `sections()`), `CreatePostagemIn` e
`UpdatePostagemIn`. `itens` só vale nos tipos `sugestoes` (≤ 20, cada um no limite do item);
nos outros, é ignorado. Nada mais muda nesses schemas. `sugestaoId` (postagem) fica `deprecated`.

Com Q1 = B, o SPA manda esses saves **a partir do painel**, com só aquele campo: `PATCH` parcial
(`{ version, <campo>, ia }`) no asset, no perfil e na postagem; `POST` de criação com `contaId`, o
campo e `ia` quando a postagem ainda não existe; `PUT` do kit com os **tokens salvos** e só aquele
campo trocado (nas sugestões: a lista do formulário + os marcados no fim, sem repetir, ≤ 20).

## Migration `0008_assistente_ia`
`upgrade`:
1. `CREATE TYPE ia_desfecho AS ENUM ('sem_acao','aplicada','editada','descartada','erro')`;
2. `CREATE TABLE ia_regras` (acima);
3. `ALTER TABLE sugestoes_texto RENAME TO ia_chamadas`; renomear PK, FKs e índices para o
   prefixo `ia_chamadas_`;
4. `RENAME COLUMN resultado TO proposta`; `corte_id` e `plataforma` passam a `NULL`;
5. `ADD COLUMN` das colunas novas (as `not null` com default), inclusive `aceitos`, `rejeitados`
   e `itens_aplicados`;
6. backfill: `tipo_campo = 'postagem.textos'`, `entity_type = 'corte'`, `entity_id = corte_id`,
   `perfil_id` por `JOIN cortes`, `regras_version = 0`; `desfecho = 'erro'` onde `erro_code` não
   é nulo, `'aplicada'` onde `id IN (SELECT sugestao_id FROM postagens)`; `custo_usd` pelos
   tokens com o preço do Sonnet 5.5 (`precos_versao = '2026-09'`);
7. `SET NOT NULL` em `tipo_campo`, `perfil_id`, `entity_type` e `DROP DEFAULT` onde o default era
   só para o backfill; checks e índices.

`downgrade`: apaga as linhas com `tipo_campo <> 'postagem.textos'` (só dev), remove as colunas
novas, volta `proposta` → `resultado`, `corte_id`/`plataforma` a `NOT NULL`, o nome
`sugestoes_texto`, e dropa `ia_regras` e o enum.

## Estados

```text
ia_chamadas.desfecho
  (geração ok) sem_acao ──Aplicar: save com ia[] (igual à proposta)──▶ aplicada
                        ──Editar e aplicar: save com ia[] (diferente)──▶ editada
                        ──descartar / fechar o painel────────────────▶ descartada
  (sugestoes) aplicada ──novo save com outros itens (iguais)──▶ aplicada (itens_aplicados acumula)
              aplicada ──novo save com item editado──────────▶ editada
  (geração com erro) erro   (final)

ia_regras (por tipo)
  sem linha (padrão, v0) ──editar──▶ personalizada (v1) ──editar──▶ … ──voltar ao padrão──▶ texto NULL (vN)
                                                    ◀──revert (dono)──
```

## Relações

```text
perfis 1─N ia_chamadas
cortes 1─N ia_chamadas (tipos de postagem)      contas 1─N ia_chamadas
ia_chamadas 1─N postagens.sugestao_id (compatibilidade da 006)
ia_chamadas N─1 entity_versions (lógica: entity_type + entity_id + aplicada_versao; details.ia)
ia_regras 1─N entity_versions (entity_type = "ia_regra")
users 1─N ia_chamadas (created_by, desfecho_por)
```
