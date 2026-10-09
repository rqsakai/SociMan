"""Imagem de marca d'água (T020, data-model `images`): PNG ou WebP com transparência, ≥ 64×64."""

import io

import pytest
from PIL import Image

from sociman_api import imaging
from sociman_api.errors import ApiError


def _img(fmt: str, mode: str = "RGBA", size=(64, 64), alpha: int = 0) -> bytes:
    color = {"RGBA": (255, 0, 0, alpha), "LA": (10, alpha), "RGB": (255, 0, 0), "P": 1}[mode]
    im = Image.new(mode, size, color)
    buf = io.BytesIO()
    kw = {"lossless": True} if fmt == "WEBP" else {}
    if mode == "P":
        im.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
        kw["transparency"] = 1
    im.save(buf, format=fmt, **kw)
    return buf.getvalue()


def _rejects(data: bytes, message: str) -> None:
    with pytest.raises(ApiError) as exc:
        imaging.validate_image(data, "watermark")
    assert (exc.value.status, exc.value.code, exc.value.message) == (400, "invalid_image", message)


@pytest.mark.parametrize(("data", "content_type"), [
    (_img("PNG"), "image/png"),
    (_img("PNG", alpha=128), "image/png"),
    (_img("PNG", mode="LA"), "image/png"),
    (_img("PNG", mode="P"), "image/png"),
    (_img("WEBP"), "image/webp"),
])
def test_aceita_png_e_webp_com_alfa(data, content_type):
    info = imaging.validate_image(data, "watermark")
    assert info.content_type == content_type and (info.width, info.height) == (64, 64)


def test_recusa_jpeg():
    _rejects(_img("JPEG", mode="RGB"), "Formato não aceito")


@pytest.mark.parametrize("data", [_img("PNG", mode="RGB"), _img("PNG", alpha=255),
                                  _img("WEBP", mode="RGB")])
def test_recusa_sem_transparencia(data):
    _rejects(data, "A imagem precisa ter fundo transparente")


def test_recusa_pequena():
    _rejects(_img("PNG", size=(63, 200)), "Imagem pequena demais")


def test_logo_continua_aceitando_jpeg_opaco():
    assert imaging.validate_image(_img("JPEG", mode="RGB", size=(200, 200)), "logo").ext == "jpg"
