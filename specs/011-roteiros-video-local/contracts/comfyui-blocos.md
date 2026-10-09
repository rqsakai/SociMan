# Contrato: blocos de vídeo do ComfyUI (uso, sem mudança externa)

O SociMan usa a API padrão do ComfyUI que a 021 já usa (`/upload/image`, `/prompt`, `/history/{id}`,
`/view`, `/free`, `/system_stats`), pela rede `gpu-local`. **Nada muda no `../comfyui-docker`**: os blocos
são **copiados** de `workflows/api/` para `apps/api/src/sociman_api/geracao/workflows/`, com sha256 no
`MANIFEST.json`. A cópia é refeita (e o manifesto atualizado) se o dono regerar os blocos lá.

## Blocos novos

Formato do contrato, o mesmo da 021: `params.{nome: {node, input, kind, default}}` e `outputs.{nome: {node,
kind}}`.

| Bloco | Origem | Params usados | Saída |
|---|---|---|---|
| `clipe_minimax` | `V2 - Clip MiniMax-H3 (início + fim opcional, com áudio)` | `start_image`, `end_image?`, `prompt`, `width`, `height`, `frames` (17k+5, 24 fps), `seed`, `prefix` | `video` (SaveVideo, h264 com áudio; o áudio é descartado) |
| `clipe_wan` | `V2 - Clip Wan 2.2 14B (início + fim opcional)` | idem, `frames` 4k+1 a 16 fps | `video` (sem áudio) |
| `clipe_wan_qualidade` | `V2 - Clip Wan 2.2 14B qualidade (20 passos, sem LightX2V)` | idem | `video` |
| `clipe_ltx` | `V2 - Clip LTX-2.5 22B (início + fim opcional, com áudio)` | idem, `frames` 8k+1 a 24 fps; o `end_image` opcional usa `drop`/`rewire` | `video` |
| `upscale_video` | `V3 - Upscale vídeo SeedVR2 3B` | `video` (enviado pelo `/upload/image`), `width`, `height`, `seed`, `prefix` | `video` (herda fps e áudio da entrada) |

O `keyframe` (Qwen Edit: `base_image`, `ref1?`, `ref2?`, `instruction`, `seed`) já foi copiado pela 021.
Na 011, a `base_image` é a principal das `keyframe_refs` (rosto, corpo-base ou look do avatar, ou o
recorte/flat do produto no plano sem avatar), e `ref1`/`ref2` são as seguintes. Com mais de 3
referências, só as 3 primeiras entram e a tela avisa.

## O que o SociMan muda do lado dele
- `comfyui.BLOCOS` ganha os 5 blocos;
- `run_bloco` aceita saída `kind = "video"`: o `/history` devolve o arquivo do SaveVideo em
  `outputs[node].images[0]`, e o `/view` devolve o mp4;
- o `last_frame` (SaveImage) existe nos clipes e é ignorado;
- o upload do vídeo para o `upscale_video` usa o mesmo `/upload/image` (multipart `image`).
- O `/free` com `unload_models: true` roda depois de cada job (como o `comfy_free` do pipeline) e o
  `unload` do shop-tts roda antes (regra da 021).

## Teto de duração por job
`GERACAO_COMFYUI_TETO_S` (1.200 s na 021) é pouco para o `clipe_wan_qualidade` (~40 min por 6,7 s) e para o
acabamento (~20 min). O teto passa a ser por bloco, em `geracao/comfyui.py`:
- `keyframe`: 600 s;
- `clipe_minimax`, `clipe_wan` e `clipe_ltx`: 1.200 s;
- `clipe_wan_qualidade`: 3.600 s;
- `upscale_video`: 900 s por posição.
