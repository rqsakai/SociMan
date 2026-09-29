"""validate_image e URLs do imgproxy (T006)."""

import base64
import hashlib
import hmac
import io
import struct
import zlib

import pytest
from PIL import Image

from sociman_api import imaging
from sociman_api.config import Settings
from sociman_api.errors import ApiError


def _img(fmt: str, size: tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 90)).save(buf, format=fmt)
    return buf.getvalue()


def _png_header(width: int, height: int) -> bytes:
    """PNG só com assinatura + IHDR (CRC válido): o Pillow lê as dimensões sem decodificar."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    return b"\x89PNG\r\n\x1a\n" + chunk + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))


def _message(data: bytes, kind: str = "logo") -> str:
    with pytest.raises(ApiError) as exc:
        imaging.validate_image(data, kind)
    assert exc.value.status == 400
    assert exc.value.code == "invalid_image"
    return exc.value.message


@pytest.mark.parametrize(("fmt", "ctype", "ext"), [
    ("PNG", "image/png", "png"), ("JPEG", "image/jpeg", "jpg"), ("WEBP", "image/webp", "webp"),
])
def test_aceita_png_jpeg_webp(fmt, ctype, ext):
    data = _img(fmt, (300, 220))
    info = imaging.validate_image(data, "logo")
    assert (info.content_type, info.ext, info.width, info.height) == (ctype, ext, 300, 220)
    assert info.sha256 == hashlib.sha256(data).hexdigest()
    assert info.bytes == len(data)


def test_banner_no_minimo():
    info = imaging.validate_image(_img("PNG", (1000, 250)), "banner")
    assert (info.width, info.height) == (1000, 250)


def test_texto_com_extensao_png():
    assert _message(b"isto nao e uma imagem, so texto\n" * 10) == "Formato não aceito"


def test_formato_real_nao_aceito():
    assert _message(_img("GIF", (300, 300))) == "Formato não aceito"


def test_maior_que_5mb():
    assert _message(b"\x89PNG" + b"\0" * (6 * 1024 * 1024)) == "Arquivo maior que 5 MB"


@pytest.mark.parametrize(("kind", "size"), [
    ("logo", (199, 300)), ("logo", (300, 199)), ("banner", (999, 400)), ("banner", (1200, 249)),
])
def test_pequena_demais(kind, size):
    assert _message(_img("PNG", size), kind) == "Imagem pequena demais"


@pytest.mark.parametrize("size", [(10_000, 10_000), (7_000, 7_000)])
def test_decompression_bomb(size):
    # 100 Mpx dispara DecompressionBombError; 49 Mpx, só o aviso (tratado como erro).
    assert _message(_png_header(*size)) == "Formato não aceito"


# Vetor conferido contra um imgproxy real (darthsim/imgproxy) com esta key/salt: a URL
# assinada respondeu 200 image/webp, e a mesma URL com assinatura adulterada, 403.
KEY = "943b421c9eb07c830af81030552c86009268de4e532ba2ee2eab8247c6da0881"
SALT = "520f986b998545b4785e0defbc4f3c1203f22de2374a3d53cb7a7fe9fea309c5"


def test_assinatura_vetor_conhecido():
    path = "/rs:fit:96:96/f:webp/bG9jYWw6Ly8vYS5wbmc"  # local:///a.png
    assert imaging.sign_path(path, KEY, SALT) == "PYJbztJltCESKDKH_jVJIvOIz069r6Xb8_CA6urA67o"


def _settings(monkeypatch, **kw):
    s = Settings(jwt_secret="x" * 32, s3_bucket="sociman", img_public_path="/img", **kw)
    monkeypatch.setattr(imaging, "get_settings", lambda: s)


SOURCE = base64.urlsafe_b64encode(b"s3://sociman/perfis/p1/a.png").rstrip(b"=").decode()


@pytest.mark.parametrize(("key", "salt"), [(None, None), ("", ""), (KEY, "")])
def test_urls_unsafe_sem_key_e_salt(monkeypatch, key, salt):
    _settings(monkeypatch, imgproxy_key=key, imgproxy_salt=salt)
    assert imaging.image_urls("perfis/p1/a.png") == {
        "thumb": f"/img/unsafe/rs:fit:96:96/f:webp/{SOURCE}",
        "medium": f"/img/unsafe/rs:fit:256:256/f:webp/{SOURCE}",
    }
    assert imaging.banner_url("perfis/p1/a.png") == f"/img/unsafe/rs:fit:1200:300/f:webp/{SOURCE}"


def test_urls_assinadas(monkeypatch):
    _settings(monkeypatch, imgproxy_key=KEY, imgproxy_salt=SALT)

    def expected(w: int, h: int) -> str:
        path = f"/rs:fit:{w}:{h}/f:webp/{SOURCE}"
        mac = hmac.new(bytes.fromhex(KEY), bytes.fromhex(SALT) + path.encode(), hashlib.sha256)
        sig = base64.urlsafe_b64encode(mac.digest()).rstrip(b"=").decode()
        return f"/img/{sig}{path}"

    urls = imaging.image_urls("perfis/p1/a.png")
    assert urls == {"thumb": expected(96, 96), "medium": expected(256, 256)}
    assert imaging.banner_url("perfis/p1/a.png") == expected(1200, 300)
