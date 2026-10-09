# Insumo: 007 estendida, cadastro padronizado de avatar, voz e cenário

Entrada para o `/speckit-specify` (feature nova que estende a `007-assets-do-perfil`; não reescreve o que
existe). Depende da **021-geracao-local** (`geracoes`, `geracao_candidatos`, `audios`). Padrões testados:
`../comfyui-docker/pipeline/PADROES.md`.

## Problema
A 007 guarda o que o usuário envia, como enviou. Os modelos locais rendem bem só com entradas num padrão
fixo (rosto frontal limpo, corpo-base neutro, referência de voz de 8–13 s cortada em fim de frase, cena
9:16 sem pessoas). E o avatar ainda não tem voz.

## O que muda no modelo de dados

### `assets` (da 007): colunas novas
| Coluna | Tipo | Regras |
|---|---|---|
| `origem` | enum `asset_origem` (`upload`, `sintetico`, `pessoa_real`) null | só `avatar`; `pessoa_real` exige consentimento |
| `consentimento` | jsonb null | `pessoa_real`: `{nome, data, registrado_por, observacao, audio_id/image_id da prova opcional}` |
| `voz_id` | uuid null FK → vozes | só `avatar`; a voz padrão do avatar |
| `identidade` | jsonb null | só `avatar`: `{modelo, data, notas: {<slot>: {nota 0..10, observacao}}}`; apagada quando um slot do kit muda |
| `kit_status` | enum (`incompleto`, `completo`, `atencao`) null | só `avatar`/`cenario`; `atencao` = alguma nota < 7 |

O `prompt` que já existe passa a ser preenchido pela IA no kit (a **descrição fixa** em inglês, 40–80
palavras, sem roupa/pose/fundo), continuando editável.

### `asset_files` (da 007): valores e colunas novas
- `role` ganha **`kit`** e **`variacao`**.
- coluna `slot` (text null), obrigatória em `kit`:
  - avatar: `rosto_origem`, `rosto_frontal`, `rosto_34_esq`, `rosto_34_dir`, `corpo_base`;
  - cenário: `cena`.
  UNIQUE parcial `(asset_id, slot) WHERE role='kit' AND archived_at IS NULL` (trocar = arquivar o antigo).
- `variacao` (cenário): `label` obrigatório (ex.: "noite"), com o mesmo UNIQUE de rótulo das poses.
- coluna `geracao_id` (uuid null FK → geracoes): de onde o arquivo veio (null = upload).
- looks continuam `referencia` com `look`; poses continuam `pose`. A diferença: agora são gerados a partir do
  `corpo_base` (ou de uma pose), com o `rosto_frontal` de referência.

### `vozes` (nova)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid FK | |
| `name` | text | 1..60, único por perfil entre as ativas (é o nome que o shop-tts usa) |
| `origem` | enum (`gravacao`, `sintetica`) | |
| `descricao` | text null | `sintetica`: a descrição em inglês usada no VoiceDesign |
| `tom` | text | ex.: "vendas animada" |
| `gravacao_audio_id` | uuid null FK → audios | `gravacao`: o original enviado |
| `ref_audio_id` | uuid null FK → audios | a referência aprovada (8–13 s, mono 24 kHz, -18 LUFS) |
| `ref_texto` | text null | transcrição exata da referência |
| `analise` | jsonb null | codec, bitrate, sample rate, piso de ruído, SNR, clipping, duração, `avisos[]` (pt-BR) |
| `consentimento` | jsonb null | obrigatório em `gravacao` de pessoa real (mesma forma do avatar) |
| `status` | enum (`rascunho`, `gerando`, `revisao`, `aprovada`) | |
| `sincronizada_em` | timestamptz null | quando a referência foi importada no shop-tts |
| `version`, `archived_*`, AuditMixin | | histórico em `entity_versions` (`entity_type = voz`) |

A voz é **do perfil** (decisão do dono): serve a vários avatares ou a nenhum (narração neutra). O avatar
aponta a sua **voz padrão** em `assets.voz_id`.

## Fluxos (cada passo é uma `geracao`)
**Avatar (kit):** `rosto_origem` (4 opções, ou upload/foto real com consentimento) → `rosto_frontal` (2) →
`rostos_34` (2 pares) → `corpo_base` (2) → `identidade` (Claude: notas por slot + `prompt`). Cada passo só
abre depois do anterior escolhido. Nota < 7 em algum slot → `kit_status = atencao` e botão "refazer este
passo". Looks e poses: pedido com rótulo e descrição da roupa → 2 opções → escolher.

**Voz:** enviar gravação (análise mostra avisos, sem bloquear) **ou** descrever voz sintética → até 3
candidatos, cada um com um áudio de teste de 2 frases → ouvir e escolher → `aprovada` → importar no
shop-tts. "Testar" narra um texto livre com a voz aprovada.

**Cenário:** foto enviada ou prompt → `cena` 768×1344 sem pessoas (2 opções) → variações por rótulo
("noite", "outro ângulo").

## Regras
- Menores de idade e pessoas famosas: recusados (como no pipeline). Pessoa real e gravação de pessoa real
  exigem consentimento registrado.
- O `prompt` do avatar **não** entra nas edições de imagem (faz o modelo dar zoom e cortar o corpo); serve
  para geração do zero, vídeo e cópia.
- Trocar qualquer slot do kit apaga `identidade` e pede nova checagem.
- Uso (seção "Onde é usado" da 007) ganha `origem: "voz"` (avatares que usam a voz).

## Estados
```
avatar.kit_status: incompleto ──último slot escolhido──▶ completo | atencao ──refazer──▶ incompleto
voz: rascunho ──enviar/descrever──▶ gerando ──▶ revisao ──escolher──▶ aprovada ──trocar referência──▶ revisao
```

## Fora do escopo
LoRA por avatar; vídeo do avatar (motor de cenas); edição manual de áudio.

## Decisões abertas para o dono
- ~~Voz do perfil ou do avatar?~~ **Decidido (2026-10-06):** a voz é **do perfil**; o avatar pode ter
  uma **voz padrão** (`assets.voz_id`), trocável por vídeo.
1. Guardar a gravação original completa da pessoa real ou só a referência cortada?
