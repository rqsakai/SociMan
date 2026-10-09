# Modelo de dados: 025-cadastro-padronizado

Tudo fica no PostgreSQL (NVMe), na migration **`0023_cadastro_padronizado`** (`down_revision =
"0022_produtos_shop"`, provisório: o gate da implementação confere a cadeia). Os arquivos continuam no
MinIO do HD: imagens no bucket `sociman` (`images` da 003) e áudios no bucket `sociman-audios` (`audios`
da 021). Esta feature **estende** `assets`/`asset_files` da 007 (colunas anuláveis, valores de enum) e
cria `vozes`. Nada da 007 muda de forma nem de comportamento para os dados que já existem.

Entidades da 021 usadas com os nomes de lá: `geracoes` (`passo`, `params`, `status` com `entregue`,
`escolhido_id`), `geracao_candidatos` (`image_id`, **`image_par_id`**, `audio_id`, `metricas`), `audios`,
`storage.apagar_por_excecao(..., excecao="lgpd_revogacao")`, `geracao/uso.py` e `ia_chamadas.geracao_id`.

## Tipos (enums)

| Enum | Valores | Novo? |
|---|---|---|
| `asset_origem` | `upload`, `sintetico`, `pessoa_real` | novo |
| `asset_kit_status` | `incompleto`, `completo`, `atencao` | novo |
| `asset_file_role` | `referencia`, `pose`, `arquivo`, **`kit`**, **`variacao`** | 007 + 2 valores |
| `voz_origem` | `gravacao`, `sintetica` | novo |
| `voz_status` | `rascunho`, `gerando`, `revisao`, `aprovada` | novo |

## `assets` (da 007): colunas novas

| Coluna | Tipo | Regras |
|---|---|---|
| `origem` | `asset_origem` null | só `avatar`; nula nos avatares da 007; definida no 1º passo do kit (`sintetico` ao escolher o `rosto_origem` gerado; `upload`/`pessoa_real` no upload do slot) |
| `consentimento` | jsonb null | só `avatar`; obrigatório antes do `rosto_origem` quando `origem = pessoa_real` (forma abaixo) |
| `voz_id` | uuid null FK → vozes.id | só `avatar`; voz do mesmo perfil, não arquivada, não revogada, com referência (research R15) |
| `identidade` | jsonb null | só `avatar`: `{modelo, data, geracao_id, notas: {<slot>: {nota: 0..10, observacao}}}` com as chaves `rosto_frontal`, `rosto_34_esq`, `rosto_34_dir`, `corpo_base`; **apagada** (null) quando qualquer slot muda |
| `kit_status` | `asset_kit_status` null | só `avatar`/`cenario`; null = "sem kit padrão" (007); calculado por `padrao.situacao` (research R5) e gravado na mesma transação |

`prompt` (da 007) não muda de forma: a checagem de identidade passa a escrevê-lo (exatamente como veio,
até 2.000) e ele continua editável (research R4).

**CHECKs** (substituem `ck_assets_campos_por_tipo`, que ganha as colunas novas):
- `ck_assets_campos_por_tipo`: o da 007 **e** `(tipo = 'avatar' OR (origem IS NULL AND consentimento IS
  NULL AND voz_id IS NULL AND identidade IS NULL))` **e** `(tipo IN ('avatar','cenario') OR kit_status
  IS NULL)`;
- `ck_assets_pessoa_real`: `origem IS DISTINCT FROM 'pessoa_real' OR consentimento IS NOT NULL`.

Índice: `ix_assets_voz (voz_id) WHERE voz_id IS NOT NULL` (lista "Usada por" da voz).

**Snapshot versionado** (`__versioned_fields__` da 007 + ): `origem`, `consentimento`, `voz_id`,
`identidade`, `kit_status`; e, em `files`, cada arquivo ganha `slot` e `geracao_id`. Imutável: `tipo`
(como na 007).

### `consentimento` (asset e voz; mesma forma)

```text
{ nome: str (1..120), data: date (≤ hoje), registrado_por: uuid (o ator, nunca do corpo),
  registrado_em: datetime, observacao: str (≤ 1000),
  prova: { image_id } | { audio_id } | null,      # do mesmo perfil
  revogado_em: datetime | null, revogado_por: uuid | null }   # só pela revogação (R10)
```
Validação no service (Pydantic + `history`). Depois de `revogado_em`, o consentimento não muda mais.

## `asset_files` (da 007): colunas e valores novos

| Coluna | Tipo | Regras |
|---|---|---|
| `role` | `asset_file_role` | + `kit` (avatar e cenário) e `variacao` (só cenário) |
| `slot` | text null | **obrigatório** em `kit`, nulo fora dele. Avatar: `rosto_origem`, `rosto_frontal`, `rosto_34_esq`, `rosto_34_dir`, `corpo_base`; cenário: `cena` |
| `geracao_id` | uuid null FK → geracoes.id | de onde veio (null = enviado à mão); em `referencia` (look), `pose`, `kit` e `variacao` |

`label` (da 007) passa a ser obrigatório também em `variacao`.

**CHECKs e índices:**
- `ck_asset_files_campos_por_papel` (substitui o da 007):
  - o da 007 com `label` permitido e obrigatório em `pose` **e** `variacao`, e `quando_usar` só em `pose`;
  - `(role = 'kit') = (slot IS NOT NULL)`;
  - `slot IS NULL OR slot IN ('rosto_origem','rosto_frontal','rosto_34_esq','rosto_34_dir','corpo_base','cena')`;
- `uq_asset_files_slot`: UNIQUE `(asset_id, slot) WHERE role = 'kit' AND archived_at IS NULL` (trocar =
  arquivar o antigo; research R6);
- `uq_asset_files_variacao_label`: UNIQUE `(asset_id, lower(label)) WHERE role = 'variacao' AND
  archived_at IS NULL` → 409 `variacao_label_in_use` ("Já existe uma variação com esse rótulo neste
  cenário");
- `ix_asset_files_geracao (geracao_id) WHERE geracao_id IS NOT NULL`.

Validação no service (400 `invalid_asset`, com `field`):
- `kit` só em `avatar`/`cenario`; os slots do avatar só em avatar e `cena` só em cenário; `variacao` só
  em cenário;
- a ordem de abertura (`padrao.PASSOS`) vale para o upload no slot e para a escolha;
- `position` de `kit` é 0 (a ordem de exibição é a de `padrao.SLOTS`); `variacao` tem `position` como
  as poses (reordenar igual).

`images.kind` por arquivo novo: slots, looks e poses do avatar → `avatar`; `cena` e `variacao` → `fundo`;
prova de consentimento → `imagem`.

## `vozes` (nova)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | o `tts_id` do shop-tts deriva dele: `"v_" + id.hex[:32]` (research R11) |
| `perfil_id` | uuid not null FK → perfis.id | |
| `name` | text not null | 1..60, sem espaço nas pontas; único por perfil entre as ativas |
| `origem` | `voz_origem` not null | imutável |
| `descricao` | text null | só `sintetica` (obrigatória nela): a descrição em inglês do VoiceDesign, até 1.000 |
| `tom` | text not null | 1..60 (ex.: "vendas animada") |
| `gravacao_audio_id` | uuid null FK → audios.id | só `gravacao`: o original enviado, **guardado completo** (FR-024); fora da limpeza de 90 dias (R22) |
| `ref_audio_id` | uuid null FK → audios.id | a referência aprovada (8–13 s, ou 6–15 s com aviso; mono 24 kHz; -18 LUFS) |
| `ref_texto` | text null | transcrição exata da referência; obrigatória com `ref_audio_id` |
| `analise` | jsonb null | `{codec, bitrate, sample_rate, piso_ruido_dbfs, snr_db, clipping_pct, duracao_s, avisos: [pt-BR]}` (do `Lote` do shop-tts) |
| `consentimento` | jsonb null | obrigatório antes do `voz.gravacao` (toda gravação é de pessoa real) |
| `status` | `voz_status` not null default `rascunho` | ver Estados |
| `sincronizada_em` | timestamptz null | última importação no shop-tts; null = pendente (com referência) ou removida (revogada) |
| `version`, `archived_at`, `archived_by` | | `_Versioned` da 003 |
| AuditMixin | | |

**CHECKs e índices:**
- `ck_vozes_por_origem`: `(origem = 'sintetica') = (descricao IS NOT NULL)` **e** `(origem = 'gravacao' OR
  (gravacao_audio_id IS NULL AND consentimento IS NULL))`;
- `ck_vozes_ref`: `(ref_audio_id IS NULL) = (ref_texto IS NULL)` **e** `(status <> 'aprovada' OR
  ref_audio_id IS NOT NULL)`, exceto revogada (o CHECK aceita `consentimento->>'revogado_em' IS NOT
  NULL`, quando a referência foi apagada e a voz está arquivada);
- `uq_vozes_nome`: UNIQUE `(perfil_id, lower(name)) WHERE archived_at IS NULL` → 409 `voz_nome_em_uso`;
- `ix_vozes_perfil (perfil_id, archived_at, updated_at desc, id)` (lista e cursor);
- `ix_vozes_sync (id) WHERE sincronizada_em IS NULL AND ref_audio_id IS NOT NULL` e `ix_vozes_remover (id)
  WHERE sincronizada_em IS NOT NULL AND consentimento->>'revogado_em' IS NOT NULL` (linha `vozes_sync` do `gerador`).

**Snapshot versionado** (`entity_type = "voz"`): `name`, `origem`, `descricao`, `tom`,
`gravacao_audio_id`, `ref_audio_id`, `ref_texto`, `consentimento`, `status`, `archived`. Imutável:
`origem`. Fora do snapshot (estado técnico): `analise` (vem do job) e `sincronizada_em` (trilha).

## Ligações com a 021

| 021 | 025 |
|---|---|
| `geracoes.alvo_tipo = 'asset'`, `alvo_id` = avatar/cenário | passos `avatar.*`, `cenario.*` |
| `geracoes.alvo_tipo = 'voz'`, `alvo_id` = voz | `voz.gravacao`, `voz.design`, `voz.teste` |
| `params` | `instrucao` (descrição da pessoa, da roupa, da cena, da voz), `referencias` (montadas pelo aplicador: origem, frontal, corpo-base, pose, cena), `rotulo` (look, pose, variação), `texto` (`voz.teste`), `extras.quandoUsar` (pose) |
| `geracao_candidatos.image_id` / `image_par_id` | `rosto_34_esq` / `rosto_34_dir` |
| `geracao_candidatos.audio_id` + `metricas` | candidato de referência (`segundos`, `similaridade`, `transcricao`, `teste_audio_id`); `voz.teste` (`segundos`, `texto`) |
| `geracao_candidatos.metricas` (identidade) | a 025 grava o resultado completo da checagem em `assets.identidade` e, no candidato, `{notas, descricao_prompt, proibidas}` |
| `ia_chamadas` (`tipo_campo = "avatar.identidade"`, `geracao_id`) | tipo novo em `ia/tipos.py` (research R4) |
| `geracao/uso.py` | provedor `vozes_e_consentimento` (research R22) |
| `storage.apagar_por_excecao(excecao="lgpd_revogacao")` | só `sociman_api/revogacao.py` (research R10) |

## `security_events`: valor novo
- `eliminacao_lgpd` (humano dono, `outcome = "ok"`, `details = {excecao: "lgpd_revogacao", alvoTipo,
  alvoId, perfilId, imagens, audios, candidatos, geracoes, chamadasIa, versoesLimpas, bytes}`), um por
  revogação; sem nome nem texto da pessoa.

## Escritas da revogação fora do padrão (exceção 2 da 4.3.0; só `sociman_api/revogacao.py`)
- `geracao_candidatos` do alvo: `image_id`, `image_par_id`, `audio_id` → `null`, `metricas` → `{}` (a
  linha fica por causa do `escolhido_id`);
- `geracoes.params` do alvo: `instrucao`, `prompt`, `texto`, `extras` → `null`; `limpa_em = now()`;
- `ia_chamadas` do alvo: `instrucao` → `''`, `entrada`, `proposta` → `null`, `explicacao` → `''`;
- `entity_versions` do alvo, em `before` e `after` de todas as versões, por `history.redigir_versoes`
  (research R10b): asset → `prompt`, `identidade`, `image_rules`, `consentimento.prova`; voz →
  `ref_texto`, `analise`, `consentimento.prova`; `details.redigida = {em, por, motivo:
  "lgpd_revogacao"}`. Revert para versão com `details.redigida` → 409 `versao_redigida`;
- DELETE de `asset_files` (todos os do avatar), `images`, `audios` e objetos do MinIO
  (`storage.apagar_por_excecao(excecao="lgpd_revogacao")`).
Teste-guarda: nenhum outro módulo faz UPDATE em `geracao_candidatos`, em `geracoes.params` ou em
`entity_versions` (AST/grep, junto do `test_delete_so_nas_excecoes` da 021).

## `entity_versions`: valores novos
- `entity_type = "voz"` (created, updated, archived, restored, reverted, `consentimento`, `revoked`);
- no asset, as ações novas: `kit_escolhido` (details `{geracaoId, passo, slots}`), `identidade`
  (details `{geracaoId, ia: {chamadaId}, automatico: true, proibidas: [...]?}`), `consentimento`,
  `revoked`. Upload em slot continua `updated`.

## Estados

```text
asset.kit_status (avatar):
  null (007) ──1º passo──▶ incompleto ──5 slots + checagem, notas ≥ 7──▶ completo
                                      └─5 slots + checagem, alguma < 7──▶ atencao
  completo | atencao ──trocar/refazer slot (identidade apagada)──▶ incompleto ──nova checagem──▶ …
asset.kit_status (cenário):
  null (007) | incompleto ──cena escolhida──▶ completo ──trocar a cena──▶ completo (sem checagem)

voz.status:
  rascunho ──pedir voz.gravacao / voz.design──▶ gerando ──geração em revisao──▶ revisao ──escolher──▶ aprovada
  aprovada ──"Trocar referência" (pedido novo)──▶ gerando ──▶ revisao ──escolher──▶ aprovada
  gerando | revisao ──geração falhou / cancelada / descartada sem outra aberta──▶ estado anterior
                      (rascunho sem referência; aprovada com referência)
  qualquer ──arquivar──▶ (arquivada) ──restaurar──▶ (mesmo status)   [restaurar recusado se revogada]
  gravacao com consentimento ──revogar (dono)──▶ arquivada, sem mídia, sincronizada_em → null após remover
```
O `status` muda pelo gancho `ao_mudar_estado` do aplicador, na transação da geração (research R2). Em
`gerando`/`revisao` com referência, a referência anterior continua valendo (FR-026).

## Regras derivadas (sem coluna)
- **Passo aberto:** `padrao.passo_aberto(asset, passo)` a partir dos slots ativos (research R6).
- **Usada por:** `SELECT id, name FROM assets WHERE voz_id = :voz AND archived_at IS NULL`.
- **Derivados desatualizados:** arquivos com `geracao_id` cujas `params.referencias` contêm a imagem do
  slot trocado (aviso na resposta da troca).
- **`tts_id`:** função pura de `vozes.id`.

## Migração `0023_cadastro_padronizado`
1. `CREATE TYPE asset_origem`, `asset_kit_status`, `voz_origem`, `voz_status`;
2. `ALTER TYPE asset_file_role ADD VALUE IF NOT EXISTS 'kit'` e `'variacao'` (num bloco
   `autocommit_block`, porque o valor novo não pode ser usado na mesma transação; os CHECKs e índices que
   citam `'kit'`/`'variacao'` vêm depois);
3. `CREATE TABLE vozes` (+ CHECKs e índices);
4. `ALTER TABLE assets ADD COLUMN origem, consentimento, voz_id (FK vozes), identidade, kit_status`;
   recria `ck_assets_campos_por_tipo`; cria `ck_assets_pessoa_real`, `ix_assets_voz`;
5. `ALTER TABLE asset_files ADD COLUMN slot, geracao_id (FK geracoes)`; recria
   `ck_asset_files_campos_por_papel`; cria `uq_asset_files_slot`, `uq_asset_files_variacao_label`,
   `ix_asset_files_geracao`;
6. sem backfill (os dados da 007 ficam com as colunas novas nulas);
7. **Downgrade:** recusa se existir linha em `vozes`, arquivo `kit`/`variacao`, asset com `origem`,
   `consentimento`, `voz_id`, `identidade` ou `kit_status`, ou evento `eliminacao_lgpd`; senão remove
   índices, CHECKs, colunas e a tabela e recria os CHECKs da 007. Os valores `kit`/`variacao` do
   `asset_file_role` ficam (como na `0015` e na `0022`; decisão da implementação, 2026-10-08). Nada do MinIO
   é tocado.

`test_migration_0023` cobre upgrade, downgrade vazio e a recusa com dados.
