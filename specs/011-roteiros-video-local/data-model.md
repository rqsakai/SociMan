> **Achado de escopo da 029 (2026-10-09):** os FKs para avatar, voz, produto, cena e keyframes deixam de exigir "do perfil" (itens da agência com perfil base opcional). Revisar no analyze da 011.

# Modelo de dados: 011-roteiros-video-local

Tudo fica no PostgreSQL (NVMe), na migration **`0027_roteiros_video_local`**, com `down_revision =
"0023_cadastro_padronizado"`. O número é **provisório** (research R19): a 012 entrou primeiro como
`0022_produtos_shop` (2026-10-08), e a 025 vira `0023_cadastro_padronizado`. O gate T001 confere com
`alembic heads`.

Os arquivos ficam no MinIO do HD:
- vídeos no bucket `sociman-videos`;
- miniaturas e keyframes no bucket `sociman`, na tabela `images`;
- narrações no bucket `sociman-audios`, na tabela `audios` da 021.

As tabelas novas usam o `AuditMixin` e o `_Versioned`. Os `entity_type` novos são **`roteiro`**,
**`roteiro_padroes`** e **`pronuncia`**.

O que muda por conta do gerador (status de máquina, `desuso_em`, `limpa_em`) é **estado de job**, sem
versão. Só as ações humanas versionam, como na 021.

## Tipos (enums)

| Enum | Valores | Novo? |
|---|---|---|
| `roteiro_formato` | `voice_over` | novo |
| `roteiro_modo` | `revisar`, `automatico` | novo |
| `roteiro_status` | `rascunho`, `planejando`, `aguardando_texto`, `narrando`, `aguardando_narracao`, `gerando_keyframes`, `aguardando_keyframes`, `gerando_clipes`, `aguardando_clipes`, `montando`, `aguardando_final`, `finalizando`, `pronto`, `falhou` | novo |
| `roteiro_etapa` | `plano`, `narracao`, `keyframes`, `clipes`, `montagem`, `acabamento` | novo (etapa do `falhou`) |
| `cena_motor` | `minimax`, `wan`, `wan_qualidade`, `ltx` | novo |
| `tomada_origem` (010) | `flow_manual` + **`geracao_local`** | `ADD VALUE` |
| `image_kind` (003) | + **`keyframe`** | `ADD VALUE` |
| `geracao_alvo` (021) | `asset`, `voz`, `produto` + **`cena`**, **`roteiro`** | `ADD VALUE` |
| `geracao_motor` (021) | `comfyui`, `tts`, `claude` + **`ffmpeg`** | `ADD VALUE` |

## `roteiros` (nova)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | imutável |
| `nome` | text not null | 1..120, sem espaço nas pontas |
| `brief` | text not null default '' | ≤ 4.000 |
| `avatar_id` | uuid null FK → assets.id | asset `avatar` do perfil, não arquivado ao ligar |
| `voz_id` | uuid null FK → vozes.id | do perfil, `aprovada`, não arquivada, consentimento não revogado (FR-003); obrigatória para narrar; padrão = `assets.voz_id` do avatar na criação |
| `formato` | `roteiro_formato` not null default `voice_over` | |
| `frases` | text[] not null default '{}' | 0..60 itens de 1..300, pt-BR, uma linha cada |
| `velocidade` | numeric(3,2) not null default 1.08 | CHECK 0.90..1.20 |
| `modo` | `roteiro_modo` not null default `revisar` | |
| `portoes` | jsonb not null | `{texto, narracao, keyframes, clipes, final}`, todos bool; validado por Pydantic; padrão do perfil ou do código |
| `status` | `roteiro_status` not null default `rascunho` | máquina abaixo |
| `etapa_falhou` | `roteiro_etapa` null | só em `falhou` |
| `erro_code`, `erro_message` | text null | só em `falhou` (códigos da 021 + `consentimento_revogado`, `tomada_curta`, `limite_cenas`) |
| `avisos` | jsonb not null default '[]' | técnica: avisos da máquina (plano cortado, prompt com "phone video"…); reescrita a cada `avancar` |
| `comandado_por` | uuid null FK → users.id | técnica: o último humano que deu um comando (R9); vira `created_by` das gerações que a máquina cria |
| `narracao_id` | uuid null FK → roteiro_narracoes.id (`use_alter`) | a ativa |
| `montagem_geracao_id` | uuid null FK → geracoes.id | a prévia atual |
| `acabamento_geracao_id` | uuid null FK → geracoes.id | o acabamento atual |
| `conteudo_id` | uuid null FK → conteudos.id | o da última entrega |
| `version`, `archived_at`, `archived_by`, AuditMixin | | |

CHECKs:
- `ck_roteiros_falhou`: `(status = 'falhou') = (etapa_falhou IS NOT NULL)`;
- `ck_roteiros_pronto`: `status <> 'pronto' OR conteudo_id IS NOT NULL`;
- `ck_roteiros_velocidade`: entre 0.90 e 1.20.

Índices:
- `(perfil_id, archived_at, updated_at desc, id)` (lista e cursor);
- `(perfil_id, status) WHERE archived_at IS NULL`.

**Snapshot versionado:** `nome`, `brief`, `avatar_id`, `voz_id`, `formato`, `frases`, `velocidade`,
`modo`, `portoes`, `status` e `archived`, além das propriedades `produtos` (lista) e `posicoes` (lista por
`ordem` com `cena_id`, `frases` e `tomada_id`). Imutável: `perfil_id`.

Ficam **fora** do snapshot (técnicos): `etapa_falhou`, `erro_*`, `avisos`, `comandado_por`, os ponteiros
`*_id` de etapa e `conteudo_id`. O `conteudo_id` vai para `details` na versão da entrega.

Ações humanas, cada uma com `history.record` e `details.acao`:
- `created`, `updated`;
- `planejar`;
- `aprovar` (`details = {portao}`);
- `portoes` e `modo` (`details = {de, para}`);
- `tentar_de_novo`;
- `archived`, `restored`, `reverted` (só dono).

## `roteiro_produtos` (nova)

| Coluna | Tipo | Regras |
|---|---|---|
| `roteiro_id` | uuid not null FK → roteiros.id | PK (`roteiro_id`, `ordem`) |
| `ordem` | smallint not null | 0..n-1 sem buracos |
| `produto_id` | uuid not null FK → produtos.id | do perfil; `aprovado` e não arquivado **ao entrar** |
| `produto_variante_id` | uuid null FK → produto_variantes.id | variante ativa daquele produto |

UNIQUE `(roteiro_id, produto_id, produto_variante_id)`; 1..6 produtos. Sem versão própria: é a
propriedade `produtos` do roteiro.

## `roteiro_cenas` (nova; as posições)

| Coluna | Tipo | Regras |
|---|---|---|
| `roteiro_id` | uuid not null FK → roteiros.id | PK (`roteiro_id`, `ordem`) |
| `ordem` | smallint not null | 0..n-1 sem buracos; n ≤ `ROTEIRO_MAX_CENAS` (R14) |
| `cena_id` | uuid not null FK → cenas.id | do mesmo perfil; a mesma cena pode repetir |
| `frases` | smallint[] not null | índices de `roteiros.frases`, **contíguos** e em ordem crescente (R6) |
| `inicio_s`, `duracao_s` | numeric(7,3) null | **derivados** da narração ativa; gravados pela máquina (técnicos), nulos sem narração |
| `tomada_id` | uuid null FK → cena_tomadas.id | da mesma cena |
| `aviso` | text null | técnica: `tomada_curta`, `cena_arquivada`, `keyframe_pendente`, `consentimento_revogado` |

Validação no service (400 `invalid_roteiro`, com `field`):
- toda frase está em exatamente uma posição;
- a ordem das posições segue a das frases;
- `tomada_id` é da `cena_id`.

## `roteiro_narracoes` (nova)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `roteiro_id` | uuid not null FK → roteiros.id | |
| `geracao_id` | uuid not null FK → geracoes.id | o `roteiro.narracao` que a produziu |
| `audio_id` | uuid null FK → audios.id | take contínuo **já na velocidade final**; null só depois da limpeza |
| `voz_id` | uuid not null FK → vozes.id | |
| `texto_hash` | text not null | sha256 de (frases com as pronúncias aplicadas, `voz_id`, `ref_audio_id` da voz, velocidade) (R10) |
| `frases` | text[] not null | o texto narrado (grafia original), para mostrar a antiga |
| `tempos` | jsonb not null | `[{frase, inicio_s, fim_s}]`, já divididos pela velocidade |
| `total_s` | numeric(7,3) not null | |
| `similaridade` | numeric(4,3) not null | |
| `seed` | bigint not null | |
| `velocidade` | numeric(3,2) not null | |
| `desuso_em` | timestamptz null | técnica (R12) |
| `limpa_em` | timestamptz null | técnica: quando o áudio foi removido |
| `created_at`, `created_by` | | |

CHECK `ck_narracoes_limpa`: `audio_id IS NOT NULL OR limpa_em IS NOT NULL`. Imutável depois de criada,
salvo os campos técnicos.

"Ativa" = `roteiros.narracao_id`. "Desatualizada" = `texto_hash <> hash_atual(roteiro)` (derivado).

## `roteiro_entregas` (nova; só inserção)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `roteiro_id` | uuid not null FK → roteiros.id | |
| `conteudo_id` | uuid not null UNIQUE FK → conteudos.id | |
| `narracao_id` | uuid not null FK → roteiro_narracoes.id | |
| `montagem_geracao_id`, `acabamento_geracao_id` | uuid not null FK → geracoes.id | |
| `posicoes` | jsonb not null | `[{ordem, cenaId, tomadaId, keyframeImageId, motor, duracaoS}]` |
| `motores` | text[] not null | os motores das tomadas usadas (atribuição do MiniMax) |
| `created_at`, `created_by` | | `created_by` = `comandado_por` |

Trigger `roteiro_entregas_so_insercao`: UPDATE e DELETE levantam erro. É o registro do "usado num vídeo
final" que protege da limpeza (R12).

## `roteiro_padroes` (nova; uma por perfil)

| Coluna | Tipo | Regras |
|---|---|---|
| `perfil_id` | uuid PK FK → perfis.id | |
| `modo` | `roteiro_modo` not null | |
| `portoes` | jsonb not null | mesma forma de `roteiros.portoes` |
| `version`, auditoria | | sem linha = padrão do código (`revisar`, todos `true`), `version 0` |

## `pronuncias` (nova)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | imutável |
| `escrita` | text not null | 1..60, sem quebra de linha, sem espaço nas pontas |
| `falada` | text not null | 1..60, idem |
| `version`, `archived_at`, `archived_by`, AuditMixin | | |

UNIQUE `uq_pronuncias_escrita (perfil_id, lower(escrita)) WHERE archived_at IS NULL` → 409
`pronuncia_existe`. Snapshot: `escrita`, `falada`, `archived`.

## `cenas` (010): só acréscimos

| Coluna | Tipo | Regras |
|---|---|---|
| `motor` | `cena_motor` not null default `minimax` | |
| `largura`, `altura` | smallint not null default 736 / 1280 | múltiplos de 16; 256..1920 |
| `keyframe_inicial_id` | uuid null FK → images.id | `kind = keyframe`, do perfil; obrigatório para gerar clipe |
| `keyframe_final_id` | uuid null FK → images.id | opcional; idem |
| `keyframe_instrucao` | text null | ≤ 2.000, inglês |
| `keyframe_refs` | uuid[] not null default '{}' | ids de `images` do perfil, ≤ 6, **sem FK** (uma imagem apagada pela revogação vira "referência removida") |
| `keyframe_geracao_id` | uuid null FK → geracoes.id | a geração da opção escolhida; null em upload manual |
| `duracao_max_s` | numeric(4,1) null | null = teto do motor (R4) |

- `__versioned_fields__` ganha as 8 colunas.
- `CAMPOS_PROMPT` **não** muda (o prompt do Flow não depende delas).
- Conjunto novo `CAMPOS_LOCAIS` (`motor`, `largura`, `altura`, `keyframe_*`, `duracao_max_s`): editar
  uma delas em cena `usada` → 409 `cena_usada`, sem mexer no status, **exceto o primeiro
  preenchimento**: campo `NULL` numa cena usada pode receber valor (o primeiro keyframe de uma cena do
  Flow, com a resolução e o motor), porque não há tomada local a invalidar; trocar um valor já definido
  continua recusado (FR-024). O `duplicar` (010) copia
  `motor`, `largura`, `altura`, `keyframe_instrucao`, `keyframe_refs` e `duracao_max_s`, mas **não**
  `keyframe_inicial_id`, `keyframe_final_id` nem `keyframe_geracao_id` (FR-025).
- O CHECK `ck_cenas_duracao IN (4, 6, 8)` continua só para o Flow (Divergência 1).

## `cena_tomadas` (010): acréscimos

| Coluna | Tipo | Regras |
|---|---|---|
| `geracao_id` | uuid null FK → geracoes.id | obrigatório em `geracao_local`, nulo em `flow_manual` |
| `keyframe_image_id` | uuid null FK → images.id | keyframe inicial usado no clipe (só `geracao_local`) |
| `motor` | `cena_motor` null | motor usado (só `geracao_local`) |
| `fps` | smallint null | 16 ou 24 |
| `desuso_em` | timestamptz null | técnica (R12) |
| `limpa_em` | timestamptz null | técnica |

As colunas da 010 `video_key`, `miniatura_key` e `bytes` passam a **anuláveis**.

CHECKs novos:
- `ck_tomadas_origem_local`: `(origem = 'geracao_local') = (geracao_id IS NOT NULL AND keyframe_image_id
  IS NOT NULL AND motor IS NOT NULL)`;
- `ck_tomadas_limpa`: `(video_key IS NOT NULL AND miniatura_key IS NOT NULL) OR limpa_em IS NOT NULL`;
- `ck_tomadas_limpa_local`: `limpa_em IS NULL OR origem = 'geracao_local'` (a do Flow nunca é limpa).

"Keyframe antigo" é derivado (R10). Uma tomada local tem o `video_key` do candidato (R3), e o UNIQUE
continua.

## `geracoes` (021): acréscimos
- `geracao_alvo` + `cena`, `roteiro`; `geracao_motor` + `ffmpeg`.
- `ck_geracoes_passo` com os **21** passos (os 15 + `roteiro.plano`, `roteiro.narracao`, `cena.keyframe`,
  `cena.clipe`, `roteiro.montagem`, `roteiro.acabamento`).
- `uq_geracoes_gpu_rodando` **não muda** (`motor IN ('comfyui','tts')`): o `ffmpeg` fica fora.
- Coluna técnica `desuso_em timestamptz null` (só as gerações `roteiro.montagem`/`roteiro.acabamento`
  usam; R12). Índice `ix_geracoes_desuso (desuso_em) WHERE desuso_em IS NOT NULL AND limpa_em IS NULL`.
- `params.extras` dos passos novos: `{roteiroId}` (todos), `{ordem}` (`cena.keyframe`, `cena.clipe`),
  `{motor, quadros, fps, duracaoS}` (`cena.clipe`).

| Passo | Motor | Alvo | Resultado | `n_opcoes` | Sem escolha | Bloco | Aplicador (resultado) |
|---|---|---|---|---|---|---|---|
| `roteiro.plano` | `claude` | `roteiro` | texto | (texto) | sim | — | frases, posições, cenas novas (010, `rascunho`) |
| `roteiro.narracao` | `tts` | `roteiro` | áudio | 1 | sim | — (`/v2/tts_paragraph`) | `roteiro_narracoes` nova, `roteiros.narracao_id`, durações |
| `cena.keyframe` | `comfyui` | `cena` | imagem (`kind = keyframe`) | 2 | **não** (humano, ou automático só no roteiro, R9) | `keyframe` | `keyframe_inicial_id`, `keyframe_geracao_id` |
| `cena.clipe` | `comfyui` | `cena` | vídeo | 1 | sim | `clipe_<motor>` | `cena_tomadas` (`geracao_local`) + `roteiro_cenas.tomada_id` |
| `roteiro.montagem` | `ffmpeg` | `roteiro` | vídeo | 1 | sim | — | `roteiros.montagem_geracao_id` |
| `roteiro.acabamento` | `comfyui` | `roteiro` | vídeo | 1 | sim | `upscale_video` | conteúdo (014) + `roteiro_entregas` + vínculo das cenas |

## `geracao_candidatos` (021): colunas de vídeo

| Coluna | Tipo | Regras |
|---|---|---|
| `video_key` | text null UNIQUE | bucket `videos`, `geracoes/{geracao_id}/{numero}.mp4` |
| `video_miniatura_key` | text null | bucket `imagens` |
| `video_duracao_ms`, `video_largura`, `video_altura`, `video_fps` | int null | do `ffprobe` |
| `video_bytes` | bigint null | |

- `ck_candidatos_midia`: `num_nonnulls(image_id, audio_id, video_key) <= 1`;
- `ck_candidatos_video`: `(video_key IS NULL) = (video_miniatura_key IS NULL)`, salvo depois da limpeza;
- trigger `geracao_candidatos_midia` atualizado:
  - `roteiro.plano` sem mídia;
  - `cena.clipe`, `roteiro.montagem` e `roteiro.acabamento` exatamente `video_key`;
  - `roteiro.narracao` exatamente `audio_id`;
  - `cena.keyframe` exatamente `image_id`.
- UPDATE só pela revogação (025) e pela limpeza (R12).

## `conteudos` (014): uma coluna
| Coluna | Tipo | Regras |
|---|---|---|
| `gerado_ia` | boolean not null default false | `true` nos conteúdos entregues por roteiro; imutável (`__immutable_fields__`) |

A origem continua `video_proprio`. "De que roteiro veio" = `roteiro_entregas.conteudo_id`.

## `images` (003)
- `image_kind` ganha `keyframe`;
- `imaging.MIN_SIZE["keyframe"] = (512, 512)`;
- o upload manual exige o aspecto da cena (±1%) e normaliza para `largura×altura` com o mesmo recorte do
  `cenario.cena` da 021.

## `entity_versions` e `security_events`: valores novos
- `entity_type`: `roteiro`, `roteiro_padroes`, `pronuncia`;
- na `cena`: ações `keyframe` (details `{geracaoId?, automatico?, upload?}`) e `pronta_pelo_roteiro`
  (details `{roteiroId}`);
- ator `system:roteiro` (exibido "sistema (automático)") nas versões da escolha automática;
- evento `eliminacao_intermediarios` (R12).

## Máquina de estados do roteiro

```text
rascunho ─planejar (humano)─▶ planejando ─plano aplicado─▶ [portão TEXTO? aguardando_texto ─aprovar─▶] narrando
narrando ─narração aplicada─▶ [portão NARRAÇÃO? aguardando_narracao ─aprovar─▶] gerando_keyframes
gerando_keyframes ─todas as posições com keyframe atual─▶ [portão KEYFRAMES? aguardando_keyframes ─aprovar─▶]
   (marca as cenas `pronta`, R8) gerando_clipes
gerando_clipes ─todas com tomada útil─▶ [portão CLIPES? aguardando_clipes ─aprovar─▶] montando
montando ─prévia aplicada─▶ [portão FINAL? aguardando_final ─aprovar─▶] finalizando
finalizando ─acabamento aplicado (conteúdo criado)─▶ pronto
qualquer etapa de trabalho ─erro final de geração / regra violada─▶ falhou(etapa) ─tentar de novo─▶ a etapa
qualquer ─arquivar─▶ (arquivado; gerações abertas canceladas) ─restaurar─▶ status de antes, depois avancar
editar etapa anterior ─▶ status da etapa editada (invalidações, FR-035/036)
```

- Os colchetes só existem com o portão ligado e o modo `revisar`.
- Keyframes: com o portão KEYFRAMES desligado (ou no automático), a opção 1 é escolhida sozinha (R9).
  Com o portão ligado, o roteiro vai para `aguardando_keyframes` assim que toda geração de keyframe
  estiver em `revisao` ou escolhida; aprovar exige todas as posições com keyframe atual.
- **Invalidação por etapa** (a "etapa da mudança" é a mais cedo atingida):
  - frases, voz, velocidade ou pronúncia → `narrando`;
  - keyframe → `gerando_clipes` (só as posições daquela cena);
  - posições ou tomada → `montando`;
  - duração maior que a tomada → `gerando_clipes` (aquela posição).

  As gerações abertas das etapas seguintes são canceladas com o ator da mudança. O `desuso_em` é gravado
  nos artefatos substituídos.

## Migration `0027_roteiros_video_local`
1. Em `autocommit_block`, `ALTER TYPE … ADD VALUE IF NOT EXISTS`:
   - `tomada_origem` + `geracao_local`;
   - `image_kind` + `keyframe`;
   - `geracao_alvo` + `cena`, `roteiro`;
   - `geracao_motor` + `ffmpeg`.
2. `CREATE TYPE roteiro_formato`, `roteiro_modo`, `roteiro_status`, `roteiro_etapa`, `cena_motor`.
3. `CREATE TABLE`:
   - `roteiros` (sem as FKs `narracao_id`, `montagem_geracao_id`, `acabamento_geracao_id`);
   - `roteiro_produtos`, `roteiro_cenas`, `roteiro_narracoes`, `roteiro_entregas` (com o trigger),
     `roteiro_padroes`, `pronuncias`;
   - depois, as FKs `use_alter`.
4. `ALTER TABLE`:
   - `cenas`: 8 colunas;
   - `cena_tomadas`: 6 colunas, `video_key`/`miniatura_key`/`bytes` anuláveis, 3 CHECKs;
   - `geracoes`: `desuso_em` e o índice; `geracao_candidatos`: 7 colunas e CHECKs;
   - `conteudos`: `gerado_ia`.
5. Recria `ck_geracoes_passo` (21 passos), `ck_candidatos_midia` e a função do trigger
   `geracao_candidatos_midia`.
6. **Downgrade:** recusa se existir:
   - linha em `roteiros` ou em `pronuncias`;
   - tomada `geracao_local` ou com `limpa_em`;
   - cena com keyframe;
   - geração dos 6 passos novos;
   - candidato com vídeo;
   - imagem `kind = keyframe`;
   - conteúdo `gerado_ia`.

   Senão remove tudo na ordem inversa, recria os CHECKs e o trigger da 021 e recria os 4 enums sem os
   valores novos (como a `0004`). Nada do MinIO é tocado.

O `test_migration_0027` cobre o upgrade, o downgrade vazio e a recusa com dados.
