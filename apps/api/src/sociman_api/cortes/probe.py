"""Validação do vídeo enviado com ffprobe (research R3).

Aceita MP4/MOV e WebM com um stream de vídeo h264, hevc, vp8, vp9, av1 ou prores, até 180 s,
500 MB e lados entre 240 e 4096 px. Qualquer outra coisa vira 400 `invalid_video` com a razão
em pt-BR. O ffprobe roda com tempo limite e só lê arquivo local (`-protocol_whitelist file`).
"""

import json
import os
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from sociman_api.errors import ApiError

MAX_DURATION_S = 180
MAX_BYTES = 500 * 1024 * 1024
MIN_SIDE = 240
MAX_SIDE = 4096
PROBE_TIMEOUT_S = 30

VIDEO_CODECS = frozenset({"h264", "hevc", "vp8", "vp9", "av1", "prores"})
# WebM só admite estes codecs; o ffprobe chama Matroska e WebM de "matroska,webm".
_WEBM_VIDEO = frozenset({"vp8", "vp9", "av1"})
_WEBM_AUDIO = frozenset({"opus", "vorbis"})

NOT_ACCEPTED = "Não é um vídeo aceito"
TOO_LONG = "Vídeo mais longo que 3 minutos"
TOO_BIG = "Arquivo maior que 500 MB"
BAD_RESOLUTION = "Resolução não suportada"


class InvalidVideo(ApiError):
    def __init__(self, message: str):
        super().__init__(400, "invalid_video", message)


@dataclass(frozen=True)
class VideoInfo:
    content_type: str  # 'video/mp4' | 'video/quicktime' | 'video/webm'
    duration_ms: int
    width: int  # já com a rotação aplicada
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None  # None = sem áudio
    rotation: int  # graus (0, 90, 180, 270), só informativo

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000


def _run_ffprobe(path: Path, timeout: float) -> dict:
    cmd = ["ffprobe", "-v", "error", "-protocol_whitelist", "file",
           "-print_format", "json", "-show_format", "-show_streams", f"file:{path}"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise InvalidVideo(NOT_ACCEPTED) from None
    if res.returncode != 0:
        raise InvalidVideo(NOT_ACCEPTED)
    try:
        return json.loads(res.stdout)
    except ValueError:
        raise InvalidVideo(NOT_ACCEPTED) from None


def _rotation(stream: dict) -> int:
    """Rotação em graus: side data (ffmpeg ≥ 5) ou a tag `rotate` (arquivos antigos)."""
    for side in stream.get("side_data_list") or ():
        if "rotation" in side:
            try:
                return round(float(side["rotation"])) % 360
            except (TypeError, ValueError):
                return 0
    try:
        return int((stream.get("tags") or {}).get("rotate", 0)) % 360
    except (TypeError, ValueError):
        return 0


def _fps(stream: dict) -> float:
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            value = Fraction(stream.get(key) or "0/0")
        except (ValueError, ZeroDivisionError):
            continue
        if value > 0:
            return round(float(value), 3)
    return 0.0


def _duration_s(fmt: dict, video: dict) -> float:
    for raw in (fmt.get("duration"), video.get("duration")):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    raise InvalidVideo(NOT_ACCEPTED)


def _content_type(fmt: dict, video_codec: str, audio_codec: str | None) -> str:
    names = set((fmt.get("format_name") or "").split(","))
    if "mp4" in names or "mov" in names:
        brand = ((fmt.get("tags") or {}).get("major_brand") or "").strip().lower()
        return "video/quicktime" if brand == "qt" else "video/mp4"
    if "webm" in names and video_codec in _WEBM_VIDEO and (
            audio_codec is None or audio_codec in _WEBM_AUDIO):
        return "video/webm"
    raise InvalidVideo(NOT_ACCEPTED)


def probe(path: str | os.PathLike[str], *, timeout: float = PROBE_TIMEOUT_S) -> VideoInfo:
    """Valida o arquivo pelo conteúdo real e devolve os metadados, ou levanta `InvalidVideo`."""
    path = Path(path).resolve()
    try:
        size = path.stat().st_size
    except OSError:
        raise InvalidVideo(NOT_ACCEPTED) from None
    if size > MAX_BYTES:
        raise InvalidVideo(TOO_BIG)

    data = _run_ffprobe(path, timeout)
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    # Capa (attached_pic) de MP4 também é "vídeo" para o ffprobe; não conta.
    videos = [s for s in streams if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")]
    if not videos:
        raise InvalidVideo(NOT_ACCEPTED)
    video = videos[0]
    video_codec = video.get("codec_name") or ""
    if video_codec not in VIDEO_CODECS:
        raise InvalidVideo(NOT_ACCEPTED)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    audio_codec = (audio.get("codec_name") or None) if audio else None
    content_type = _content_type(fmt, video_codec, audio_codec)

    duration = _duration_s(fmt, video)
    if duration > MAX_DURATION_S:
        raise InvalidVideo(TOO_LONG)

    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    rotation = _rotation(video)
    if rotation in (90, 270):
        width, height = height, width
    if min(width, height) < MIN_SIDE or max(width, height) > MAX_SIDE:
        raise InvalidVideo(BAD_RESOLUTION)

    return VideoInfo(content_type=content_type, duration_ms=round(duration * 1000),
                     width=width, height=height, fps=_fps(video), video_codec=video_codec,
                     audio_codec=audio_codec, rotation=rotation)
