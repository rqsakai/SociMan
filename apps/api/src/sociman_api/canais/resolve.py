"""O que o usuário cola para cadastrar um canal → consulta ao YouTube e custo (research R2).

Função pura, sem rede:

| Entrada                                            | Consulta              | Custo |
|----------------------------------------------------|-----------------------|-------|
| `UC` + 22 caracteres, ou `/channel/UC…`            | `channels?id=`        | 1     |
| `@handle` ou `youtube.com/@handle`                 | `channels?forHandle=` | 1     |
| `/user/nome`                                       | `channels?forUsername=` | 1   |
| `/c/nome`, `youtube.com/nome` ou nome solto        | `search?type=channel` | 100   |
| link de vídeo (`watch?v=`, `youtu.be/`, `shorts/`) | `videos` → `channels` | 2     |
"""

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from sociman_api.errors import ApiError

TipoConsulta = Literal["id", "handle", "username", "busca", "video"]

CUSTOS: dict[TipoConsulta, int] = {"id": 1, "handle": 1, "username": 1, "busca": 100, "video": 2}

_CHANNEL_ID = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
_VIDEO_ID = re.compile(r"^[0-9A-Za-z_-]{11}$")
_HANDLE = re.compile(r"^[0-9A-Za-z._-]{3,30}$")
_USERNAME = re.compile(r"^[0-9A-Za-z._-]{1,100}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
# Primeiro trecho do caminho que não é um canal (`youtube.com/<nome>` legado vira busca).
_RESERVADOS = {"watch", "shorts", "live", "embed", "playlist", "results", "feed", "channel",
               "user", "c", "hashtag", "post", "v"}
INVALIDA = "Cole o link do canal, o @ ou o ID (UC…)"
MAX_ENTRADA = 500


@dataclass(frozen=True)
class Consulta:
    tipo: TipoConsulta
    valor: str

    @property
    def custo(self) -> int:
        return CUSTOS[self.tipo]


def _invalida() -> ApiError:
    return ApiError(400, "invalid_channel_input", INVALIDA)


def _handle(raw: str) -> Consulta:
    handle = raw.removeprefix("@")
    if not _HANDLE.match(handle):
        raise _invalida()
    return Consulta("handle", handle.lower())


def _video(video_id: str) -> Consulta:
    if not _VIDEO_ID.match(video_id):
        raise _invalida()
    return Consulta("video", video_id)


def _from_url(entrada: str) -> Consulta:
    url = entrada if re.match(r"^https?://", entrada, re.IGNORECASE) else f"https://{entrada}"
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    segs = [s for s in parts.path.split("/") if s]
    if host in _SHORT_HOSTS:
        if not segs:
            raise _invalida()
        return _video(segs[0])
    if host not in _HOSTS or not segs:
        raise _invalida()
    first = segs[0]
    if first == "watch":
        ids = parse_qs(parts.query).get("v", [])
        if not ids:
            raise _invalida()
        return _video(ids[0])
    if first in ("shorts", "live", "embed", "v") and len(segs) > 1:
        return _video(segs[1])
    if first.startswith("@"):
        return _handle(first)
    if first == "channel" and len(segs) > 1 and _CHANNEL_ID.match(segs[1]):
        return Consulta("id", segs[1])
    if first == "user" and len(segs) > 1 and _USERNAME.match(segs[1]):
        return Consulta("username", segs[1])
    if first == "c" and len(segs) > 1:
        return Consulta("busca", segs[1])
    if first not in _RESERVADOS and _USERNAME.match(first):
        return Consulta("busca", first)
    raise _invalida()


def _parece_url(entrada: str) -> bool:
    return bool(re.match(r"^(https?://|(www\.|m\.|music\.)?youtube\.com/|(www\.)?youtu\.be/)",
                         entrada, re.IGNORECASE))


def resolver_entrada(entrada: str) -> Consulta:
    """Converte a entrada; recusa com 400 `invalid_channel_input` o que não reconhece."""
    entrada = entrada.strip()
    if not entrada or len(entrada) > MAX_ENTRADA:
        raise _invalida()
    if _CHANNEL_ID.match(entrada):
        return Consulta("id", entrada)
    if entrada.startswith("@"):
        return _handle(entrada)
    if _parece_url(entrada):
        return _from_url(entrada)
    if "/" in entrada or "://" in entrada or len(entrada) > 100:
        raise _invalida()
    return Consulta("busca", entrada)
