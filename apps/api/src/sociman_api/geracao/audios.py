"""Áudios do perfil (research R11, FR-028 e FR-029): a irmã das imagens da 003.

O envio (até 25 MB) vai para `work/tmp` no HD, passa pelo `ffprobe` (wav, m4a com aac/alac, ogg
ou mp3; exatamente 1 fluxo de áudio, sem vídeo; de 1 ms a 10 min) e é guardado como veio (a
gravação original, sem conversão) no bucket `audios`, em `perfis/{id}/audios/{uuid}.{ext}`. Os
candidatos do shop-tts (wav) passam pelo mesmo caminho. Imutável: não há rota de alteração.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from sociman_api import datadir, midia, storage
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.geracao import schemas
from sociman_api.geracao.models import Audio
from sociman_api.perfis.schemas import UserRef

MAX_BYTES = 25 * 1024 * 1024
MAX_DURACAO_MS = 10 * 60 * 1000
PROBE_TIMEOUT_S = 30
CHUNK = 1024 * 1024
CONTENT_TYPES = {"wav": "audio/wav", "m4a": "audio/mp4", "ogg": "audio/ogg", "mp3": "audio/mpeg"}
_M4A_CODECS = frozenset({"aac", "alac"})

FORMATO = "Formato não aceito: envie wav, m4a, ogg ou mp3"
SEM_AUDIO = "O arquivo não tem áudio"
LONGO = "Áudio longo demais (máximo 10 min)"
GRANDE = "Arquivo grande demais (máximo 25 MB)"


def _invalido(message: str) -> ApiError:
    return ApiError(400, "audio_invalido", message)


@dataclass(frozen=True)
class AudioInfo:
    formato: str
    sample_rate: int
    duracao_ms: int


def _ffprobe(path: Path) -> dict:
    cmd = ["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-print_format", "json",
           "-show_format", "-show_streams", f"file:{path}"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=PROBE_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise _invalido(FORMATO) from None
    if res.returncode != 0:
        raise _invalido(FORMATO)
    try:
        return json.loads(res.stdout)
    except ValueError:
        raise _invalido(FORMATO) from None


def probe(path: Path) -> AudioInfo:
    """Valida pelo conteúdo (nunca pela extensão) e devolve formato, taxa e duração."""
    data = _ffprobe(path)
    streams = data.get("streams") or []
    # Capa de mp3 (`attached_pic`) não é vídeo de verdade.
    videos = [s for s in streams if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    nomes = set(str((data.get("format") or {}).get("format_name") or "").split(","))
    if videos:
        raise _invalido(FORMATO)
    if not audios:
        raise _invalido(SEM_AUDIO)
    if len(audios) != 1:
        raise _invalido(FORMATO)
    codec = audios[0].get("codec_name") or ""
    if "wav" in nomes:
        formato = "wav"
    elif "mp3" in nomes:
        formato = "mp3"
    elif "ogg" in nomes:
        formato = "ogg"
    elif "m4a" in nomes or "mp4" in nomes or "mov" in nomes:
        if codec not in _M4A_CODECS:
            raise _invalido(FORMATO)
        formato = "m4a"
    else:
        raise _invalido(FORMATO)
    try:
        dur = float(audios[0].get("duration") or (data.get("format") or {}).get("duration"))
        sample_rate = int(audios[0].get("sample_rate") or 0)
    except (TypeError, ValueError):
        raise _invalido(FORMATO) from None
    duracao_ms = round(dur * 1000)
    if duracao_ms <= 0 or sample_rate <= 0:
        raise _invalido(SEM_AUDIO)
    if duracao_ms > MAX_DURACAO_MS:
        raise _invalido(LONGO)
    return AudioInfo(formato=formato, sample_rate=sample_rate, duracao_ms=duracao_ms)


def spool_dir() -> Path:
    return Path(get_settings().data_dir) / "work" / "tmp"


def _spool(stream: BinaryIO) -> tuple[Path, int, str]:
    """Copia o envio para `work/tmp` (HD), com teto de 25 MB (413) e o sha256."""
    try:
        fh = tempfile.NamedTemporaryFile(  # noqa: SIM115 — fechado no `with fh` abaixo
            dir=spool_dir(), prefix="audio-", suffix=".upload", delete=False)
    except OSError:
        raise ApiError(503, "storage_unavailable", "O HD de dados não está disponível") from None
    path, size, hasher = Path(fh.name), 0, hashlib.sha256()
    try:
        with fh:
            while chunk := stream.read(CHUNK):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ApiError(413, "arquivo_grande", GRANDE)
                fh.write(chunk)
                hasher.update(chunk)
        return path, size, hasher.hexdigest()
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _gravar(db: Session, perfil_id: uuid.UUID, path: Path, size: int, sha256: str,
            created_by: uuid.UUID | None) -> Audio:
    if size == 0:
        raise _invalido(SEM_AUDIO)
    info = probe(path)
    audio_id = uuid.uuid4()
    key = f"perfis/{perfil_id}/audios/{audio_id}.{info.formato}"
    # O objeto vai antes do commit; se a transação falhar, sobra um objeto sem referência.
    storage.put_file(key, path, CONTENT_TYPES[info.formato], bucket="audios")
    audio = Audio(id=audio_id, perfil_id=perfil_id, object_key=key, formato=info.formato,
                  sample_rate=info.sample_rate, duracao_ms=info.duracao_ms, sha256=sha256,
                  bytes=size, created_by=created_by)
    db.add(audio)
    db.flush()
    return audio


def enviar(db: Session, perfil_id: uuid.UUID, stream: BinaryIO,
           created_by: uuid.UUID | None) -> Audio:
    """`POST /api/perfis/{id}/audios`: HD conferido antes de ler, teto, ffprobe e bucket."""
    datadir.ensure_writable(MAX_BYTES)
    path, size, sha256 = _spool(stream)
    try:
        return _gravar(db, perfil_id, path, size, sha256, created_by)
    finally:
        path.unlink(missing_ok=True)


def gravar_bytes(db: Session, perfil_id: uuid.UUID, data: bytes,
                 created_by: uuid.UUID | None) -> Audio:
    """Um áudio que o motor devolveu (candidato ou teste do shop-tts), pelo mesmo caminho."""
    datadir.ensure_writable(len(data))
    if len(data) > MAX_BYTES:
        raise _invalido(GRANDE)
    fd, nome = tempfile.mkstemp(dir=spool_dir(), prefix="audio-", suffix=".wav")
    path = Path(nome)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return _gravar(db, perfil_id, path, len(data), hashlib.sha256(data).hexdigest(),
                       created_by)
    finally:
        path.unlink(missing_ok=True)


def audio_out(audio: Audio, users: dict[uuid.UUID, UserRef]) -> schemas.Audio:
    lk = midia.link("audio", audio.id, ttl=get_settings().midia_link_ttl_s)
    return schemas.Audio(
        id=audio.id, perfil_id=audio.perfil_id, formato=audio.formato,
        sample_rate=audio.sample_rate, duracao_ms=audio.duracao_ms, sha256=audio.sha256,
        bytes=audio.bytes, link=schemas.Link(url=lk.url, expires_at=lk.expires_at),
        created_at=audio.created_at,
        created_by=users.get(audio.created_by) if audio.created_by else None)
