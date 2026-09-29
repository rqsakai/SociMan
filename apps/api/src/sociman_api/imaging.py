"""Validação de imagens (R5) e URLs do imgproxy (R6).

Imagem de marca d'água (spec 004, data-model `images`): só PNG ou WebP com transparência de
verdade (canal alfa com algum pixel não opaco), mínimo 64×64. Imagem de fundo (FR-005b): PNG,
JPG ou WebP, mínimo 540×540, sem exigir alfa.

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
MIN_SIZE = {"logo": (200, 200), "banner": (1000, 250), "watermark": (64, 64),
            "fundo": (540, 540), "avatar": (256, 256), "imagem": (64, 64)}
_FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"),
            "WEBP": ("image/webp", "webp")}
_KIND_FORMATS = {"logo": tuple(_FORMATS), "banner": tuple(_FORMATS),
                 "watermark": ("PNG", "WEBP"), "fundo": tuple(_FORMATS),
                 "avatar": tuple(_FORMATS), "imagem": tuple(_FORMATS)}
TRANSPARENCY_MESSAGE = "A imagem precisa ter fundo transparente"
FORMAT_MESSAGE = "Formato não aceito"

ImageKind = Literal["logo", "banner", "watermark", "fundo", "avatar", "imagem"]


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


def validate_image(data: bytes, kind: ImageKind, *, max_bytes: int = MAX_BYTES,
                   transparency_message: str = TRANSPARENCY_MESSAGE,
                   too_large_message: str = FORMAT_MESSAGE,
                   opaque_format_message: str | None = None) -> ImageInfo:
    """Valida pelo conteúdo real (não pela extensão) e devolve os metadados.

    Decompression bomb (acima de MAX_IMAGE_PIXELS, inclusive o aviso do Pillow, tratado como
    erro) vira `too_large_message`: "Formato não aceito" nas rotas da 003/004 (conjunto fechado
    da T006); a biblioteca da 007 passa "Imagem grande demais (máximo 40 megapixels)". A
    biblioteca também passa `max_bytes` (20 MB), a mensagem de transparência do sticker e
    `opaque_format_message`: um JPG (que não tem alfa) enviado onde a transparência é exigida
    recebe essa mensagem em vez de "Formato não aceito".
    """
    if len(data) > max_bytes:
        raise _invalid(f"Arquivo maior que {max_bytes // (1024 * 1024)} MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=list(_FORMATS)) as im:
                im.verify()
            # verify() inutiliza o objeto; reabre para ler formato e dimensões.
            with Image.open(io.BytesIO(data), formats=list(_FORMATS)) as im:
                fmt = im.format
                width, height = im.size
                transparent = _has_transparency(im) if kind == "watermark" else True
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise _invalid(too_large_message) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise _invalid(FORMAT_MESSAGE) from exc
    if fmt not in _KIND_FORMATS[kind]:
        if opaque_format_message is not None and kind == "watermark":
            raise _invalid(opaque_format_message)
        raise _invalid("Formato não aceito")
    min_w, min_h = MIN_SIZE[kind]
    if width < min_w or height < min_h:
        raise _invalid("Imagem pequena demais")
    if not transparent:
        raise _invalid(transparency_message)
    content_type, ext = _FORMATS[fmt]
    return ImageInfo(content_type=content_type, ext=ext, width=width, height=height,
                     sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))


def _has_transparency(im: Image.Image) -> bool:
    """Canal alfa (ou cor transparente da paleta) com pelo menos um pixel não opaco."""
    if im.mode not in ("RGBA", "LA", "PA") and "transparency" not in im.info:
        return False
    alpha = im.convert("RGBA").getchannel("A")
    return alpha.getextrema()[0] < 255


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


def preview_url(object_key: str) -> str:
    """Prévia grande do asset na biblioteca (spec 007): até 1024×1024, sem cortar."""
    return _url(object_key, 1024, 1024)


def banner_url(object_key: str) -> str:
    return _url(object_key, 1200, 300)


def poster_url(object_key: str) -> str:
    """Quadro de um corte como fundo da prévia do kit (cabe em 540×960, proporção 9:16)."""
    return _url(object_key, 540, 960)


# Origens remotas que o imgproxy aceita (IMGPROXY_ALLOWED_SOURCES no compose, spec 006 R13).
REMOTE_ORIGINS = ("https://i.ytimg.com/", "https://yt3.ggpht.com/",
                  "https://yt3.googleusercontent.com/")


def remote_url(url: str | None, width: int, height: int) -> str | None:
    """Miniatura ou avatar do YouTube servido pelo imgproxy (a CSP proíbe origem externa).

    Só para as origens de `REMOTE_ORIGINS`; qualquer outra (ou None) devolve None, para a API
    nunca virar proxy aberto.
    """
    if not url or not url.startswith(REMOTE_ORIGINS):
        return None
    s = get_settings()
    path = f"/rs:fill:{width}:{height}/f:webp/{_b64url(url.encode())}"
    prefix = sign_path(path, s.imgproxy_key, s.imgproxy_salt) \
        if s.imgproxy_key and s.imgproxy_salt else "unsafe"
    return f"{s.img_public_path}/{prefix}{path}"
