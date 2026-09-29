# Modelo de dados: 004-kit-de-marca

Tudo fica no PostgreSQL (NVMe), na migration `0003_kit_de_marca`. Os arquivos ficam no MinIO
único, cujos dados passam para o HD (R5, R12), em três buckets: `sociman` (logos, banners, marca
d'água e pôsteres; o único que o imgproxy lê), `sociman-fonts` e `sociman-videos`. As tabelas de domínio usam o `AuditMixin` da 001 e, quando versionadas, o
`_Versioned` da 003 (`version`, `archived_at`, `archived_by`). O histórico é o
`entity_versions` da 003, com os novos `entity_type` `kit`, `fonte` e `corte`.

## `brand_kits`
Um por perfil, criado no primeiro salvamento (R10). Sem linha, a API devolve o kit padrão com
`version: 0`.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null UNIQUE FK → perfis.id | |
| `palette` | jsonb not null | `Cor[]`, 1..12 |
| `caption` | jsonb not null | `Legenda` |
| `hook` | jsonb not null | `Gancho` |
| `watermark` | jsonb not null | `MarcaDagua` |
| `end_card` | jsonb not null | `CardFinal` |
| `catchphrases` | jsonb not null default '[]' | `string[]`, até 20, cada um 1..120, sem repetição |
| `series` | jsonb not null default '[]' | `string[]`, até 20, cada um 1..60, sem repetição |
| `version` | int not null | controle otimista |
| AuditMixin | | |

Sem `archived_at`: o kit não é arquivado (o perfil é). **Snapshot versionado:** `palette`,
`caption`, `hook`, `watermark`, `end_card`, `catchphrases`, `series`.

### Tokens (validados pelo schema Pydantic `KitTokens`; o JSONB nunca recebe nada fora dele)
```text
CorRef      "#RRGGBB" (maiúsculas, normalizado) | "paleta:<chave>"
FonteRef    "padrao:anton" | "padrao:noto-serif-bold" | "padrao:liberation-sans"
            | "padrao:liberation-serif" | "perfil:<uuid da brand_fonts>" (ativa, do mesmo perfil)

Cor         { chave: ^[a-z0-9]+(-[a-z0-9]+)*$ 1..40 (única no kit, estável ao renomear),
              nome: 1..40, valor: "#RRGGBB" }

Legenda     { fonte: FonteRef, tamanho: 10..200, cor_texto: CorRef,
              cor_contorno: CorRef, espessura_contorno: 0..10,
              cor_fundo: CorRef, opacidade_fundo: 0..1 (passo 0,05),
              estilo: "classico"|"karaoke", cor_destaque: CorRef,
              efeito: "nenhum"|"brilho"|"pop"|"caixa",
              posicao: "topo"|"meio"|"base", maiusculas: bool }

Gancho      { ligado: bool, fonte: FonteRef, cor_texto: CorRef,
              cor_fundo: CorRef, opacidade_fundo: 0..1,
              cor_contorno: CorRef, espessura_contorno: 0..10,
              posicao: "topo"|"centro"|"base", tamanho: "P"|"M"|"G", duracao_s: 1..10 (passo 0,5) }

MarcaDagua  { ligado: bool, tipo: "logo"|"imagem"|"texto",
              imagem_id: uuid|null  (obrigatório se tipo = imagem; images.kind = watermark do perfil),
              conta_id: uuid|null   (obrigatório se tipo = texto; conta do perfil, não arquivada),
              posicao: "sup_esq"|"sup_dir"|"inf_esq"|"inf_dir"|"centro_inf"|"centro_sup",
              escala_pct: 5..40, opacidade_pct: 10..100, margem_pct: 0..10 (da largura),
              fonte: FonteRef, cor_texto: CorRef   (usados só no tipo texto) }

CardFinal   { ligado: bool, cta: 1..80, fonte: FonteRef, cor_texto: CorRef,
              cor_fundo: CorRef, mostrar_logo: bool, duracao_s: 1..5 (passo 0,5) }
```

Regras cruzadas (400 `invalid_kit`, com `field` no formato `hook.cor_fundo`):
- toda `paleta:<chave>` precisa existir na paleta;
- `perfil:<uuid>` precisa ser fonte **ativa** do mesmo perfil;
- tipo `logo` exige logo no perfil (spec 003); `tipo = texto` exige a conta;
- com `ligado = false`, os demais campos da seção continuam validados (o dono pode religar sem
  redigitar);
- tirar da paleta uma cor ainda referenciada é recusado, apontando o primeiro campo que a usa.

### Kit padrão (US1-1: "as cores do padrão atual dos cortes")
- **Paleta:** Branco `#FFFFFF`, Preto `#000000`, Amarelo destaque `#FFE500`.
- **Legenda:** o `AUTO_CAPTION_STYLE` do OpenShorts (`subtitles.py:239`): Anton, 44, branco,
  contorno preto 4, karaokê com destaque `#FFE500`, efeito pop, base, maiúsculas, sem fundo.
- **Gancho:** o preset `classic` com o `AUTO_HOOK_SECONDS` (`main.py:1168`): Noto Serif Bold,
  texto preto, fundo branco a 94%, sem contorno, topo, M, 5 s, ligado.
- **Marca d'água:** texto com o @ da primeira conta ativa (desligada se não houver conta),
  `inf_dir`, 20%, 70%, margem 4%, Anton branco.
- **Card final:** desligado, CTA "Segue pra mais", Anton branco sobre preto, sem logo, 2 s.
- Bordões e séries vazios.

## `brand_fonts`
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | |
| `name` | text not null | 1..60, sem espaço nas pontas |
| `family` | text not null | lida da fonte (`getname()[0]`) |
| `style` | text not null | lida da fonte (`getname()[1]`, ex.: "Bold") |
| `format` | enum `font_format` (`ttf`, `otf`) | pela assinatura do arquivo, não pela extensão |
| `object_key` | text not null UNIQUE | `perfis/{perfil_id}/{uuid4}.{ttf\|otf}` no bucket `sociman-fonts` |
| `bytes` | int not null | até 10 MB |
| `sha256` | text not null | |
| `version`, `archived_at`, `archived_by`, AuditMixin | | como na 003 |

Índice único parcial: `(perfil_id, lower(name)) WHERE archived_at IS NULL` (409
`font_name_in_use`). **Snapshot:** `name`, `archived`. O arquivo é imutável: trocar o arquivo é
enviar outra fonte.

## `images` (da 003)
O enum `image_kind` ganha `watermark`. A validação (`imaging.validate_image`) aceita PNG ou WebP
**com canal alfa**, mínimo 64×64, até 5 MB. A imagem é referenciada por
`brand_kits.watermark.imagem_id` e nunca é apagada.

## `cortes`
A linha é o job de processamento (R1, R10).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | |
| `hook_text` | text not null | 1..120, até 3 linhas no render (R2); `\n` do usuário é respeitado |
| `kit_version` | int not null | versão do kit no envio (0 = padrão nunca salvo) |
| `kit_tokens` | jsonb not null | tokens **resolvidos** no envio (hex, arquivos de fonte e imagem por `object_key`) |
| `status` | enum `corte_status` (`na_fila`, `processando`, `pronto`, `falhou`) | padrão `na_fila` |
| `progress` | smallint not null default 0 | 0..100 |
| `attempts` | smallint not null default 0 | incrementado a cada início |
| `error_code` | text null | `corrupted`, `timeout`, `interrupted`, `low_space`, `internal` |
| `error_message` | text null | pt-BR, exibida ao usuário |
| `queued_at` | timestamptz not null | ordem da fila |
| `started_at`, `heartbeat_at`, `finished_at` | timestamptz null | |
| `processing_ms` | int null | duração do último processamento que terminou (FR-017) |
| `original_filename` | text not null | nome enviado (só exibição; até 200) |
| `original_key` | text not null UNIQUE | `perfis/{perfil_id}/cortes/{id}/original.{ext}` no bucket `sociman-videos` |
| `original_content_type` | text not null | `video/mp4`, `video/quicktime` ou `video/webm` (pelo ffprobe) |
| `original_bytes` | bigint not null | ≤ 500 MB |
| `duration_ms`, `width`, `height` | int not null | do ffprobe, já com a rotação aplicada |
| `fps` | numeric(6,3) not null | |
| `video_codec` | text not null | |
| `audio_codec` | text null | null = sem áudio |
| `original_sha256` | text not null | |
| `result_key` | text null UNIQUE | `…/marcado.mp4` no bucket `sociman-videos` |
| `result_bytes` | bigint null | |
| `poster_key` | text null | `…/poster.jpg` no bucket `sociman` (quadro do meio, para a prévia do kit, servido pelo imgproxy, R7) |
| `version` | int not null | controle otimista do "tentar de novo" |
| AuditMixin | | `created_by` é o autor do envio (FR-017) |

Índices: `(status, queued_at)` (fila) e `(perfil_id, created_at desc)` (lista).
Check: `status = 'pronto'` exige `result_key`; `status = 'falhou'` exige `error_message`.
**Snapshot versionado** (só ações do usuário): `hook_text`, `kit_version`, `status`
(`created` no envio, `updated` no "tentar de novo"). Sem arquivamento nem reversão.

## Estados
```
kit:    (sem linha, version 0) ──1º salvar──▶ v1 ──salvar──▶ v2 … ; reverter (só dono) = nova versão
fonte:  ativa ──arquivar (se não estiver em uso)──▶ arquivada ──restaurar──▶ ativa
corte:  na_fila ──worker pega──▶ processando ──ok──▶ pronto
                                   │  └──erro──▶ falhou ──"tentar de novo"──▶ na_fila
                                   └──heartbeat > 120 s──▶ na_fila (attempts < 3) | falhou (attempts = 3)
```
Nenhum estado apaga arquivo. `pronto` é final (reprocessar com outro gancho é um envio novo).
Com o HD de dados sem o sentinela, o worker não pega nada da fila (os cortes ficam `na_fila`, sem
contar tentativa); com pouco espaço, o corte vai para `falhou` com `low_space` e pode ser tentado de
novo.

## HD de dados (sem tabela)
Não há cota nem tabela de uso. O estado vem do sistema de arquivos, lido pela API e pelo worker no
bind mount de `/media/sakai` com `rslave` (R5):
- `SOCIMAN_DATA_DIR` (padrão `/media/sakai/BACKUP/tiktok/sociman`): `.sociman-volume` (sentinela,
  criado por `scripts/data-setup.sh`), `minio/` (dados do MinIO) e `work/` (`tmp/` para o spool de
  upload da API e `cortes/{id}/` para o worker);
- `DATA_MIN_FREE_GB` (padrão 20): espaço livre mínimo para qualquer gravação (MinIO e `work/`);
- `cortesBytes` na tela = `sum(original_bytes + coalesce(result_bytes, 0))` da tabela `cortes`;
  livre e total = `os.statvfs(SOCIMAN_DATA_DIR)`.

## Fundo com imagem (FR-005a e FR-005b, adicionado depois da POC)
- `image_kind` ganha o valor `fundo`: imagens de fundo do perfil, em PNG, JPG ou WebP, com mínimo
  de 540×540, no bucket `sociman` (HD).
- `hook` e `end_card` ganham `fundo_tipo` (`cor` | `imagem`, padrão `cor`) e `fundo_imagem_id`
  (uuid | null, obrigatório com `imagem` e a seção ligada; precisa ser do kind `fundo` e do
  próprio perfil).
- `end_card` ganha também `opacidade_fundo` (0–1, padrão 0.45), usado só com imagem: é a camada da
  cor de fundo sobre a imagem.
- Com imagem, a imagem é recortada em cover para a área (a caixa do gancho ou o quadro inteiro do
  card), e a camada de cor com opacidade vai por cima. O texto e o logo ficam acima da camada.
