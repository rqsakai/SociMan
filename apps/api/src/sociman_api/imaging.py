"""Validação de imagens (R5) e URLs do imgproxy (R6).

As URLs seguem o adapter do volans (reference/volans-api/src/lib/adapters/imgproxy.ts):
  {img_public_path}/{assinatura|unsafe}/rs:fit:{w}:{h}/f:webp/{base64url("s3://bucket/key")}
Com IMGPROXY_KEY/IMGPROXY_SALT (hex) a URL é assinada com HMAC-SHA256; sem eles é "unsafe"
(aceitável só em dev, porque o imgproxy só aceita s3://sociman/).
"""

import base64
import hashlib
import hmac
import io
import warnings
from dataclasses import dataclass
from typing import Literal

from PIL import Image, UnidentifiedImageError

from sociman_api.config import get_settings
from sociman_api.errors import ApiError

Image.MAX_IMAGE_PIXELS = 40_000_000

MAX_BYTES = 5 * 1024 * 1024
MIN_SIZE = {"logo": (200, 200), "banner": (1000, 250)}
_FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"),
            "WEBP": ("image/webp", "webp")}

ImageKind = Literal["logo", "banner"]


@dataclass(frozen=True)
class ImageInfo:
    content_type: str
    ext: str  # 'png' | 'jpg' | 'webp'
    width: int
    height: int
    sha256: str
    bytes: int


def _invalid(message: str) -> ApiError:
    return ApiError(400, "invalid_image", message)


def validate_image(data: bytes, kind: ImageKind) -> ImageInfo:
    """Valida pelo conteúdo real (não pela extensão) e devolve os metadados.

    Decompression bomb (acima de MAX_IMAGE_PIXELS, inclusive o aviso do Pillow, tratado como
    erro) vira "Formato não aceito": o arquivo não é uma imagem que aceitamos processar, e a
    mensagem fica dentro do conjunto fechado da T006.
    """
    if len(data) > MAX_BYTES:
        raise _invalid("Arquivo maior que 5 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=list(_FORMATS)) as im:
                im.verify()
            # verify() inutiliza o objeto; reabre para ler formato e dimensões.
            with Image.open(io.BytesIO(data), formats=list(_FORMATS)) as im:
                fmt = im.format
                width, height = im.size
    except (UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, OSError, SyntaxError, ValueError) as exc:
        raise _invalid("Formato não aceito") from exc
    if fmt not in _FORMATS:
        raise _invalid("Formato não aceito")
    min_w, min_h = MIN_SIZE[kind]
    if width < min_w or height < min_h:
        raise _invalid("Imagem pequena demais")
    content_type, ext = _FORMATS[fmt]
    return ImageInfo(content_type=content_type, ext=ext, width=width, height=height,
                     sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def sign_path(path: str, key_hex: str, salt_hex: str) -> str:
    """Assinatura do imgproxy: base64url(HMAC-SHA256(key, salt + path)), sem padding."""
    mac = hmac.new(bytes.fromhex(key_hex), bytes.fromhex(salt_hex) + path.encode(),
                   hashlib.sha256)
    return _b64url(mac.digest())


def _url(object_key: str, width: int, height: int) -> str:
    s = get_settings()
    source = _b64url(f"s3://{s.s3_bucket}/{object_key}".encode())
    path = f"/rs:fit:{width}:{height}/f:webp/{source}"
    # No container, IMGPROXY_KEY/SALT não definidos chegam como "": trata como ausente.
    prefix = sign_path(path, s.imgproxy_key, s.imgproxy_salt) \
        if s.imgproxy_key and s.imgproxy_salt else "unsafe"
    return f"{s.img_public_path}/{prefix}{path}"


def image_urls(object_key: str) -> dict[str, str]:
    return {"thumb": _url(object_key, 96, 96), "medium": _url(object_key, 256, 256)}


def banner_url(object_key: str) -> str:
    return _url(object_key, 1200, 300)
