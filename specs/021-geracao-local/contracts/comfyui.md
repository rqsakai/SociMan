# Contrato: ComfyUI (serviço externo, sem mudança de código)

O ComfyUI roda no projeto vizinho `../comfyui-docker` (container `comfyui`). O SociMan usa só a **API HTTP
padrão do ComfyUI**, igual ao `run_block` do pipeline (`pipeline/run_storyboard.py`). O código do ComfyUI
**não muda**. A única mudança externa é de **rede** (abaixo), e quem a aplica é o dono.

## Endpoints usados (cliente `geracao/comfyui.py`, lista fechada)

| Método e caminho | Uso | Observação |
|---|---|---|
| `GET /system_stats` | VRAM livre (`devices[0].vram_free`, `torch_vram_total`) e "está de pé" | R3 |
| `POST /upload/image` (multipart `image`, `subfolder=sociman`, `type=input`, `overwrite=true`) | sobe as referências | nome `<geracao_id>_<n>_<param>.png` |
| `POST /prompt` `{prompt, client_id}` | enfileira o bloco preenchido | devolve `prompt_id` |
| `GET /history/{prompt_id}` | polling a cada 2 s | `status.status_str`, `outputs` |
| `GET /view?filename&subfolder&type` | baixa a saída | em memória (≤ 40 MP) |
| `GET /queue` | sabe se o prompt está em execução (cancelar) | |
| `POST /interrupt` | cancela o prompt em execução | só se for o da geração |
| `POST /queue {"delete": [prompt_id]}` | tira da fila do ComfyUI | |
| `POST /free {"unload_models": bool, "free_memory": true}` | libera VRAM (fim de bloco: `false`; antes do TTS: `true`) | R3, FR-022 |

Qualquer outro caminho é bloqueado no cliente (`ALLOWED`, como o cliente da TikTok da 015). Timeouts: 10 s
por chamada; o job inteiro tem teto de 20 min por opção (`GERACAO_COMFYUI_TETO_S`), depois `servico_fora`.

## Blocos (cópia versionada, research R6)

`apps/api/src/sociman_api/geracao/workflows/` com `cena`, `keyframe`, `retrato` e `cutout` (`*.api.json` +
`*.params.json`) e `MANIFEST.json` (origem e sha256). Parâmetros preenchidos pelo contrato (`kind` `image`,
`image_optional`, `value`); saída pelo `outputs` do contrato.

## Mudança externa de rede (DEPENDÊNCIA, aplicada pelo dono; research R5, recomendação A)

Em `../comfyui-docker/docker-compose.yml` (não editar daqui):
```yaml
services:
  comfyui:
    networks: [default, gpu-local]
  tts:
    networks: [default, gpu-local]
networks:
  gpu-local:
    external: true
```
E uma vez no host: `docker network create gpu-local` (o `scripts/data-setup.sh init` do SociMan passa a
criar a rede se faltar). As portas `127.0.0.1:8188` e `127.0.0.1:8200` continuam (o pipeline do host usa).
No SociMan, só o serviço `gerador` entra na `gpu-local`; `COMFYUI_URL=http://comfyui:8188`.

## Fake
- pytest: `apps/api/tests/fakes/comfyui_fake.py`;
- e2e: `openshorts-fake` em `/comfyui/*` (`COMFYUI_URL=http://openshorts-fake:8000/comfyui`).
