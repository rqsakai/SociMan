""""GPU livre" antes de um job `comfyui` ou `tts` (research R3, FR-020).

Em ordem: (1) nenhum envio da 006 em `processando` (o OpenShorts está cortando; um envio em
`aguardando_openshorts` ainda não começou e não conta); (2) a VRAM do dispositivo, medida pelo
próprio ComfyUI (`/system_stats`: `vram_free + torch_vram_total`, porque o cache do ComfyUI é
dele), contra o piso do motor (`GERACAO_VRAM_MIN_GB_COMFYUI` e `_TTS`). O gerador não precisa de
GPU nem de `nvidia-smi`. O estado é calculado na hora, nunca gravado.
"""

from typing import Literal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from sociman_api.config import get_settings
from sociman_api.envios.models import Envio, EnvioStatus
from sociman_api.geracao.comfyui import ComfyClient
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.models import GeracaoMotor

Estado = Literal["livre", "openshorts", "pouca_vram", "fora"]


def piso_gb(motor: GeracaoMotor) -> float:
    s = get_settings()
    return s.geracao_vram_min_gb_tts if motor == GeracaoMotor.tts \
        else s.geracao_vram_min_gb_comfyui


def openshorts_processando(db: Session) -> bool:
    return bool(db.scalar(select(exists().where(Envio.status == EnvioStatus.processando))))


def gpu_livre(db: Session, motor: GeracaoMotor, comfy: ComfyClient) -> Estado:
    if openshorts_processando(db):
        return "openshorts"
    try:
        vram = comfy.vram_disponivel_gb()
    except MotorErro:
        return "fora"
    return "livre" if vram >= piso_gb(motor) else "pouca_vram"
