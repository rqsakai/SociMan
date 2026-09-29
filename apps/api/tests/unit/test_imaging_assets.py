"""Imagens da biblioteca de assets (T009, research R3): kinds `avatar` e `imagem`, 20 MB,
transparência do sticker e a mensagem de megapixels."""

import io
import os

import pytest
from PIL import Image

from sociman_api import imaging
from sociman_api.assets import tipos
from sociman_api.assets.models import AssetTipo
from sociman_api.errors import ApiError

MB20 = 20 * 1024 * 1024


def _img(fmt: str, size: tuple[int, int], mode: str = "RGB", alpha: int = 255) -> bytes:
    color = (200, 30, 90) if mode == "RGB" else (200, 30, 90, alpha)
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format=fmt)
    return buf.getvalue()


def _library(data: bytes, tipo: AssetTipo) -> imaging.ImageInfo:
    return imaging.validate_image(
        data, tipos.IMAGE_KIND[tipo].value, max_bytes=tipos.MAX_BYTES,
        transparency_message=tipos.transparency_message(tipo),
        too_large_message=tipos.TOO_LARGE,
        opaque_format_message=tipos.transparency_message(tipo))


def _message(data: bytes, tipo: AssetTipo) -> str:
    with pytest.raises(ApiError) as exc:
        _library(data, tipo)
    assert (exc.value.status, exc.value.code) == (400, "invalid_image")
    return exc.value.message


def _noise_png(target: int) -> bytes:
    """PNG de ruído (sem compressão útil) com exatamente `target` bytes: o que sobra vai depois
    do IEND, que o Pillow ignora."""
    side = int(((target - 4096) / 3) ** 0.5)
    im = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=0)
    data = buf.getvalue()
    assert len(data) <= target
    return data + b"\0" * (target - len(data))


@pytest.mark.parametrize(("tipo", "size", "ok"), [
    (AssetTipo.avatar, (256, 256), True), (AssetTipo.avatar, (255, 400), False),
    (AssetTipo.imagem, (64, 64), True), (AssetTipo.imagem, (63, 64), False),
    (AssetTipo.cenario, (540, 540), True), (AssetTipo.cenario, (539, 900), False),
])
def test_minimos_por_tipo(tipo, size, ok):
    data = _img("JPEG", size)
    if ok:
        assert _library(data, tipo).content_type == "image/jpeg"
    else:
        assert _message(data, tipo) == "Imagem pequena demais"


def test_20_mb_no_limite_e_um_byte_a_mais():
    data = _noise_png(MB20)
    assert len(data) == MB20
    assert _library(data, AssetTipo.imagem).bytes == MB20
    assert _message(data + b"\0", AssetTipo.imagem) == "Arquivo maior que 20 MB"


@pytest.mark.parametrize("data", [
    _img("JPEG", (128, 128)),  # sem canal alfa
    _img("PNG", (128, 128), mode="RGBA", alpha=255),  # alfa todo opaco
])
def test_sticker_sem_transparencia(data):
    assert _message(data, AssetTipo.sticker) == "O sticker precisa ter fundo transparente"
    assert _message(data, AssetTipo.marca_dagua) == "A imagem precisa ter fundo transparente"


def test_sticker_com_transparencia():
    info = _library(_img("PNG", (128, 128), mode="RGBA", alpha=0), AssetTipo.sticker)
    assert info.content_type == "image/png"


def _big_png(side: int) -> bytes:
    """PNG de verdade acima de 40 Mpx (1 bit por pixel: poucos KB comprimido)."""
    buf = io.BytesIO()
    Image.new("1", (side, side)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("side", [10_000, 7_000])
def test_megapixels(side):
    # 100 Mpx dispara DecompressionBombError; 49 Mpx, só o aviso (tratado como erro).
    data = _big_png(side)
    assert _message(data, AssetTipo.imagem) == "Imagem grande demais (máximo 40 megapixels)"
    # As rotas da 003/004 continuam com "Formato não aceito".
    with pytest.raises(ApiError) as exc:
        imaging.validate_image(data, "logo")
    assert exc.value.message == "Formato não aceito"


def test_preview_url():
    assert "/rs:fit:1024:1024/" in imaging.preview_url("perfis/x/a.png")
