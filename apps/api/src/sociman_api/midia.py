"""Links assinados de mídia (research R6): `/api/midia/{token}`.

O token é `base64url(payload).base64url(HMAC-SHA256)`, com o `JWT_SECRET` e o domínio
separado `midia:` (um token de mídia nunca vale como outro segredo da API, e vice-versa). O
payload é `{k: tipo, id, v?: variante, exp?: epoch}`:
- vídeo (`corte_original`, `corte_marcado`, `conteudo_video` da spec 014) sempre tem `exp`
  (1 h na interface);
- fonte, imagem de marca d'água e imagem de fundo podem sair **sem `exp`** na exportação do kit (FR-011,
  decisão do dono em 2026-09-29): valem enquanto o arquivo existir, e arquivos nunca são
  apagados.
- `imagem` (spec 007, R7): o original de qualquer imagem da biblioteca, sem `exp` no
  "Copiar link" e no "Baixar original" do asset (token determinístico, portanto estável).

Streaming (T010): `stream_object` serve o objeto do MinIO com `Range` (206/416) e 503 com o HD
fora. As rotas (`GET /api/midia/{token}`, sem login, e `POST /api/midia/links`) ficam em
`router_midia.py`, que escolhe o bucket e o `Content-Type` pela tabela do `kind`.
"""

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, get_args
from urllib.parse import quote

import urllib3
from fastapi.responses import Response, StreamingResponse
from minio.error import S3Error

from sociman_api import datadir, storage
from sociman_api.config import get_settings
from sociman_api.errors import ApiError

MidiaKind = Literal["corte_original", "corte_marcado", "fonte", "marca_dagua", "fundo",
                    "imagem",  # imagem: qualquer `images.id` (biblioteca da 007)
                    "conteudo_video"]  # vídeo próprio (spec 014)
KINDS: frozenset[str] = frozenset(get_args(MidiaKind))
VIDEO_KINDS: frozenset[str] = frozenset({"corte_original", "corte_marcado", "conteudo_video"})
LINK_TTL = 60 * 60  # 1 h (interface)
PATH_PREFIX = "/api/midia/"
_DOMAIN = b"midia:"
_MAX_TOKEN = 512
INVALID_LINK = "Link inválido ou vencido"


@dataclass(frozen=True)
class MidiaClaims:
    kind: str
    id: uuid.UUID
    variant: str | None
    exp: int | None  # epoch em segundos; None = sem validade


@dataclass(frozen=True)
class Link:
    url: str  # relativa ao edge
    expires_at: datetime | None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(body: str) -> bytes:
    secret = get_settings().jwt_secret
    assert secret, "jwt_secret é preenchido pelo Settings"
    return hmac.new(secret.encode(), _DOMAIN + body.encode("ascii"), hashlib.sha256).digest()


def sign(kind: MidiaKind, entity_id: uuid.UUID, *, ttl: int | None = LINK_TTL,
         variant: str | None = None, now: float | None = None) -> str:
    """Token para `/api/midia/{token}`. `ttl=None` (sem validade) só para o que não é vídeo."""
    if kind not in KINDS:
        raise ValueError(f"tipo de mídia desconhecido: {kind}")
    if ttl is None and kind in VIDEO_KINDS:
        raise ValueError("link de vídeo sempre tem validade")
    if ttl is not None and ttl <= 0:
        raise ValueError("ttl precisa ser positivo")
    payload: dict[str, object] = {"k": kind, "id": str(entity_id)}
    if variant is not None:
        payload["v"] = variant
    if ttl is not None:
        payload["exp"] = int(time.time() if now is None else now) + ttl
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{body}.{_b64(_mac(body))}"


def link(kind: MidiaKind, entity_id: uuid.UUID, *, ttl: int | None = LINK_TTL,
         variant: str | None = None, now: float | None = None) -> Link:
    token = sign(kind, entity_id, ttl=ttl, variant=variant, now=now)
    exp = verify(token, now=now).exp
    expires_at = datetime.fromtimestamp(exp, UTC) if exp is not None else None
    return Link(url=f"{PATH_PREFIX}{token}", expires_at=expires_at)


def _invalid() -> ApiError:
    return ApiError(403, "invalid_link", INVALID_LINK)


def verify(token: str, *, now: float | None = None) -> MidiaClaims:
    """Confere assinatura, formato e validade. Qualquer falha é 403 `invalid_link`."""
    if len(token) > _MAX_TOKEN or token.count(".") != 1:
        raise _invalid()
    body, sig = token.split(".")
    try:
        given = _unb64(sig)
    except (binascii.Error, ValueError):
        raise _invalid() from None
    if not hmac.compare_digest(given, _mac(body)):
        raise _invalid()
    try:
        payload = json.loads(_unb64(body))
        kind = payload["k"]
        entity_id = uuid.UUID(payload["id"])
        variant = payload.get("v")
        exp = payload.get("exp")
    except (binascii.Error, ValueError, KeyError, TypeError):
        raise _invalid() from None
    if kind not in KINDS or (variant is not None and not isinstance(variant, str)):
        raise _invalid()
    if exp is None:
        if kind in VIDEO_KINDS:  # vídeo nunca sai sem validade (R6)
            raise _invalid()
    elif not isinstance(exp, int) or exp <= (time.time() if now is None else now):
        raise _invalid()
    return MidiaClaims(kind=kind, id=entity_id, variant=variant, exp=exp)


# ---- streaming com Range (T010, R6) ----

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CACHE_CONTROL = "private, max-age=3600"


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int  # inclusivo

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def _unsatisfiable(size: int) -> ApiError:
    return ApiError(416, "range_not_satisfiable", "Faixa fora do arquivo",
                    headers={"Content-Range": f"bytes */{size}"})


def parse_range(header: str | None, size: int) -> ByteRange | None:
    """A faixa pedida em `Range`, ou None para o arquivo inteiro.

    Como o RFC 9110 permite, ignora (serve 200) o que não entende: outra unidade, sintaxe
    inválida ou várias faixas (o `<video>` pede sempre uma só). Faixa que começa depois do fim,
    sufixo zero ou arquivo vazio dão 416 com `Content-Range: bytes */size`.
    """
    if not header:
        return None
    m = _RANGE_RE.match(header.strip().replace(" ", ""))
    if m is None:
        return None
    first, last = m.groups()
    if first == "" and last == "":
        return None
    if first == "":  # sufixo: os últimos N bytes
        n = int(last)
        if n == 0 or size == 0:
            raise _unsatisfiable(size)
        return ByteRange(max(0, size - n), size - 1)
    start = int(first)
    end = int(last) if last else size - 1
    if last and end < start:
        return None  # sintaticamente inválida: ignora
    if start >= size:
        raise _unsatisfiable(size)
    return ByteRange(start, min(end, size - 1))


def content_disposition(filename: str) -> str:
    """`attachment` com nome ASCII (fallback) e `filename*` em UTF-8 (RFC 6266)."""
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r'[^A-Za-z0-9._ -]', "_", ascii_name).strip() or "arquivo"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


def stream_object(bucket: storage.Bucket, key: str, content_type: str, *,
                  range_header: str | None, download_name: str | None = None) -> Response:
    """Serve o objeto do MinIO com suporte a `Range` (206/416) sem carregá-lo na memória.

    503 `storage_unavailable` com o HD fora (sem o sentinela, o MinIO pode estar lendo uma
    pasta vazia no NVMe) ou com o MinIO sem responder; 404 se o objeto não existe.
    """
    if datadir.status().reason == "sem_sentinela":
        raise _storage_unavailable()
    try:
        size = storage.stat(key, bucket=bucket).size or 0
    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchBucket", "NoSuchObject"):
            raise ApiError(404, "not_found", "Arquivo não encontrado") from exc
        raise _storage_unavailable() from exc
    except (urllib3.exceptions.HTTPError, OSError) as exc:
        raise _storage_unavailable() from exc
    byte_range = parse_range(range_header, size)
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": CACHE_CONTROL,
        "X-Content-Type-Options": "nosniff",
    }
    if download_name:
        headers["Content-Disposition"] = content_disposition(download_name)
    if size == 0:
        return Response(b"", media_type=content_type, headers=headers)
    start, length, status = 0, size, 200
    if byte_range is not None:
        start, length, status = byte_range.start, byte_range.length, 206
        headers["Content-Range"] = f"bytes {byte_range.start}-{byte_range.end}/{size}"
    headers["Content-Length"] = str(length)
    try:
        chunks = storage.get_range(key, start, length, bucket=bucket)
    except S3Error as exc:
        raise _storage_unavailable() from exc
    except (urllib3.exceptions.HTTPError, OSError) as exc:
        raise _storage_unavailable() from exc
    return StreamingResponse(chunks, status_code=status, media_type=content_type,
                             headers=headers)


def _storage_unavailable() -> ApiError:
    return ApiError(503, "storage_unavailable", "O HD de dados não está disponível")
