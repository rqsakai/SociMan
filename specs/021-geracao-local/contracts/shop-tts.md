# Contrato: shop-tts — DEPENDÊNCIA EXTERNA

> **Dependência externa.** O serviço fica em `../comfyui-docker/tts_service/app.py` (container `shop-tts`,
> FastAPI). **Esta spec não edita esse serviço**: só descreve a mudança de contrato de que o SociMan
> precisa. A mudança é feita no projeto `comfyui-docker` (pelo dono ou numa sessão dedicada), **antes** do
> primeiro uso real do motor `tts` (que chega com a voz da 025). Na 021, o motor `tts` é implementado e
> testado só contra o fake deste contrato.

## Por que mudar

Hoje os endpoints recebem e gravam **caminhos de arquivo** dentro do container (`"arquivo": "/in/..."`,
`out_dir` em `/out/...`, vozes aprovadas em `/vozes/ref_<nome>.wav` + `ref_texts.json`). O SociMan roda em
outro container, sem acesso a essas pastas, e passa a ser a **fonte da verdade** da voz (a referência
aprovada fica no MinIO do SociMan). Por isso:
1. a entrada tem de chegar **como arquivo** no pedido (multipart);
2. a saída tem de sair **como arquivo** para download (e ser apagada do serviço depois);
3. uma voz aprovada no SociMan tem de ser **importada** no serviço (wav + transcrição).

Os campos e rotas atuais continuam valendo para o CLI do pipeline (`pipeline/voz.py`): a mudança é
**aditiva** e compatível.

## Endpoints

### Sem mudança
- `GET /health` → `{status, loaded, voices}`. **Aditivo pedido:** `vram_free_mb` (opcional; o SociMan usa a
  VRAM do ComfyUI quando faltar).
- `GET /voices` → mapa `nome → {file, text}`. **Aditivo pedido:** `sha256` da referência por voz (o SociMan
  compara para saber se precisa importar de novo).
- `POST /unload` → libera a VRAM agora.
- 503 com "GPU sem memória livre" quando der `OutOfMemoryError` (o SociMan trata como `sem_memoria`).

### Novos (o SociMan usa só estes)

| Método e caminho | Entrada | Saída |
|---|---|---|
| `POST /v2/voices/register` | multipart: `arquivo` (wav/m4a/ogg/mp3), `nome`, `tom`, `n` (≤ 3) | `Lote` (análise, avisos, candidatos com teste) |
| `POST /v2/voices/design` | JSON: `nome`, `descricao` (inglês), `texto` (opcional), `n` (≤ 3), `seed` | `Lote` |
| `POST /v2/voices/import` | multipart: `nome`, `ref` (wav mono 24 kHz), `ref_texto`, `meta` (JSON: origem, tom, sociman_voz_id, sha256) | `{nome, sha256, importada_em}`; grava `/vozes/ref_<nome>.wav` + `ref_texts.json` + `ref_meta.json` (substitui sem `--substituir`, porque o SociMan decide) |
| `POST /v2/tts` | JSON: o `TTSRequest` atual **sem** `out_dir` | `Lote` com `frases[]` (`arquivo`, `similarity`, `seconds`, `seed`, `transcript`, `ok`) |
| `POST /v2/tts_paragraph` | JSON: idem | `Lote` com 1 arquivo e os tempos das frases |
| `GET /v2/lotes/{lote_id}/{arquivo}` | — | o WAV (`audio/wav`) |
| `DELETE /v2/lotes/{lote_id}` | — | 204; apaga a pasta temporária do lote |

```text
Lote {
  lote_id: str,                       # pasta temporária no serviço (ex.: /out/v2/<uuid>/)
  analise?: {codec, bitrate, sample_rate, piso_ruido_dbfs, snr_db, clipping_pct, duracao_s, avisos: [pt-BR]},
  transcricao?: str,
  candidatos?: [{n, arquivo: "candidato_N.wav", teste: "teste_N.wav",
                 segundos, similaridade, transcricao, janela: {inicio_s, fim_s}}],
  frases?: [...], arquivo?: str
}
```

Regras pedidas ao serviço:
- `lote_id` e `arquivo` só com `[A-Za-z0-9_.-]`, sem `..` (o serviço confere o caminho, como já faz com
  `out_dir`);
- o lote expira sozinho em 24 h se o SociMan não chamar o `DELETE`;
- upload até 25 MB (o mesmo limite do SociMan);
- nada de caminho absoluto no pedido nem na resposta.

## Fluxo do SociMan (motor `tts`, `geracao/shoptts.py`)
1. antes do job: `POST /free` do ComfyUI (`unload_models: true`) e a conferência de GPU (research R3);
2. `register`/`design`/`tts` com o arquivo baixado do MinIO;
3. baixa cada arquivo do `Lote`, valida (ffprobe), grava como `audios` e cria os candidatos com as
   `metricas` (`segundos`, `similaridade`, `transcricao`, `teste_audio_id`);
4. `DELETE` do lote;
5. ao aprovar uma voz (025): `import` com a referência e a transcrição, e confere o `sha256` em `GET /voices`.

Lista fechada no cliente (`ALLOWED`): só os caminhos `/health`, `/voices`, `/unload`, os `/v2/*` acima e o
`DELETE /v2/voices/{nome}` da 025 (`specs/025-cadastro-padronizado/contracts/shop-tts-025.md`, parte da
mesma dependência externa X2). A 021 já fecha o `ALLOWED` com essa rota; quem a usa é a 025.

## Rede
O mesmo da `contracts/comfyui.md`: `shop-tts` na rede `gpu-local` (mudança externa no
`../comfyui-docker/docker-compose.yml`); `SHOP_TTS_URL=http://shop-tts:8200`.

## Fake
- pytest: `apps/api/tests/fakes/shoptts_fake.py` (implementa exatamente este contrato `v2`);
- e2e: `openshorts-fake` em `/shop-tts/*` (`SHOP_TTS_URL=http://openshorts-fake:8000/shop-tts`).
