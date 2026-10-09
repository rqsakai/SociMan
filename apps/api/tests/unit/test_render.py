"""cortes.render: PNGs do gancho, da marca d'água e do card final (T023, R2 e R7)."""

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageFont

from sociman_api.cortes import render
from sociman_api.cortes.render import (
    EndCardStyle,
    HookStyle,
    InvalidHook,
    KitRender,
    WatermarkStyle,
)

W, H = 1080, 1920


@pytest.fixture(scope="module")
def font_path(tmp_path_factory) -> Path:
    """A fonte embutida no Pillow, gravada em arquivo (os testes não dependem do sistema)."""
    path = tmp_path_factory.mktemp("fonts") / "pillow.ttf"
    path.write_bytes(ImageFont.load_default(20).font_bytes)
    return path


def hook_style(font_path: Path, **kw) -> HookStyle:
    base = HookStyle(font_path=font_path, text_color="#000000", bg_color="#FFFFFF",
                     bg_opacity=0.94, stroke_color="#000000", stroke_width=0, position="topo",
                     size="M", duration_s=5)
    return replace(base, **kw)


def colors(img: Image.Image) -> set[tuple[int, ...]]:
    return {c for _, c in img.getcolors(maxcolors=img.width * img.height)}


def logo(tmp_path: Path, size=(200, 100), color=(255, 0, 0, 255)) -> Path:
    path = tmp_path / "logo.png"
    Image.new("RGBA", size, color).save(path)
    return path


# ---------- gancho ----------

def test_gancho_rgba_dentro_de_90_por_cento(font_path):
    placed = render.render_hook("Olha isso aqui", hook_style(font_path), W, H)
    img = placed.image
    assert img.mode == "RGBA"
    assert int(W * 0.3) <= img.width <= int(W * 0.9)
    assert placed.x == (W - img.width) // 2
    # Canto arredondado transparente; borda interna com o fundo a 94%.
    assert img.getpixel((0, 0))[3] == 0
    assert img.getpixel((10, img.height // 2)) == (255, 255, 255, round(0.94 * 255))


def test_gancho_texto_na_cor_pedida(font_path):
    img = render.render_hook("TEXTO", hook_style(font_path, text_color="#FF0000"), W, H).image
    assert (255, 0, 0, 255) in colors(img)


def test_gancho_sem_caixa_quando_opacidade_zero(font_path):
    img = render.render_hook("Oi", hook_style(font_path, bg_opacity=0), W, H).image
    assert img.getpixel((5, img.height // 2))[3] == 0


def test_gancho_posicoes(font_path):
    topo = render.render_hook("Oi", hook_style(font_path), W, H)
    assert topo.y == int(H * 0.12)
    base = render.render_hook("Oi", hook_style(font_path, position="base"), W, H)
    assert base.y == int(H * 0.70)
    centro = render.render_hook("Oi", hook_style(font_path, position="centro"), W, H)
    assert centro.y == (H - centro.image.height) // 2


def test_gancho_tamanhos_crescem(font_path):
    heights = [render.render_hook("Oi", hook_style(font_path, size=s), W, H).image.height
               for s in ("P", "M", "G")]
    assert heights[0] < heights[1] < heights[2]


def test_gancho_relativo_ao_tamanho_do_video(font_path):
    vertical = render.render_hook("Oi", hook_style(font_path), 1080, 1920).image
    horizontal = render.render_hook("Oi", hook_style(font_path), 1920, 1080).image
    assert horizontal.height > vertical.height


def test_gancho_quebra_em_ate_3_linhas(font_path):
    text = " ".join(["palavra"] * 12)
    lines = render.wrap_hook(text, hook_style(font_path), W)
    assert 2 <= len(lines) <= 3
    assert " ".join(lines) == text


def test_gancho_respeita_quebra_do_usuario(font_path):
    assert render.wrap_hook("um\ndois", hook_style(font_path), W) == ["um", "dois"]


def test_gancho_palavra_gigante_quebra_por_caractere(font_path):
    lines = render.wrap_hook("x" * 60, hook_style(font_path), W)
    assert len(lines) >= 2
    assert "".join(lines) == "x" * 60


@pytest.mark.parametrize("text", [
    "um\ndois\ntres\nquatro",
    " ".join(["palavra"] * 19),
    "a" * 121,
    "   ",
])
def test_gancho_longo_demais_recusado(font_path, text):
    with pytest.raises(InvalidHook) as exc:
        render.render_hook(text, hook_style(font_path, size="G"), W, H)
    assert (exc.value.status, exc.value.code) == (400, "invalid_hook")
    assert exc.value.message == "Gancho longo demais"


def test_gancho_remove_emoji(font_path):
    assert render.wrap_hook("oi 🔥🔥 tudo", hook_style(font_path), W) == ["oi tudo"]


# ---------- marca d'água ----------

def wm(**kw) -> WatermarkStyle:
    base = WatermarkStyle(kind="imagem", position="inf_dir", scale_pct=20, opacity_pct=100,
                          margin_pct=4)
    return replace(base, **kw)


@pytest.mark.parametrize(("pos", "expected"), [
    ("sup_esq", lambda w, h, m: (m, m)),
    ("sup_dir", lambda w, h, m: (W - w - m, m)),
    ("inf_esq", lambda w, h, m: (m, H - h - m)),
    ("inf_dir", lambda w, h, m: (W - w - m, H - h - m)),
    ("centro_inf", lambda w, h, m: ((W - w) // 2, H - h - m)),
    ("centro_sup", lambda w, h, m: ((W - w) // 2, m)),
])
def test_marca_imagem_posicao_e_escala(tmp_path, pos, expected):
    placed = render.render_watermark(wm(image_path=logo(tmp_path), position=pos), W, H)
    w, h = placed.image.size
    assert (w, h) == (216, 108)  # 20% de 1080, proporção mantida
    assert (placed.x, placed.y) == expected(w, h, round(W * 0.04))


def test_marca_opacidade_no_alfa(tmp_path):
    img = render.render_watermark(wm(image_path=logo(tmp_path), opacity_pct=70), W, H).image
    assert img.getpixel((50, 50)) == (255, 0, 0, round(255 * 0.7))


def test_marca_texto(font_path):
    style = wm(kind="texto", text="@achadinhos", font_path=font_path, text_color="#FFFF00",
               opacity_pct=50)
    placed = render.render_watermark(style, W, H)
    img = placed.image
    assert abs(img.width - 216) <= 4
    assert img.getchannel("A").getextrema()[1] == round(255 * 0.5)
    assert placed.x + img.width == W - round(W * 0.04)


# ---------- card final ----------

def card(font_path: Path, **kw) -> EndCardStyle:
    base = EndCardStyle(cta="Segue pra mais", font_path=font_path, text_color="#FFFFFF",
                        bg_color="#000000", duration_s=2)
    return replace(base, **kw)


def test_card_quadro_inteiro_opaco(font_path):
    placed = render.render_end_card(card(font_path, bg_color="#0000FF"), W, H)
    img = placed.image
    assert (placed.x, placed.y, img.size) == (0, 0, (W, H))
    assert img.getpixel((0, 0)) == (0, 0, 255, 255)
    assert img.getchannel("A").getextrema() == (255, 255)
    center = img.crop((0, H // 2 - 200, W, H // 2 + 200))
    assert (255, 255, 255, 255) in colors(center)


def test_card_com_logo_acima_do_cta(tmp_path, font_path):
    style = card(font_path, logo_path=logo(tmp_path, color=(0, 255, 0, 255)))
    img = render.render_end_card(style, W, H).image
    green = [y for y in range(0, H, 4) if img.getpixel((W // 2, y))[:3] == (0, 255, 0)]
    white = [y for y in range(0, H, 2)
             for x in range(0, W, 8) if img.getpixel((x, y))[:3] == (255, 255, 255)]
    assert green and white
    assert max(green) < min(white)


def test_card_cta_longo_cabe(font_path):
    img = render.render_end_card(card(font_path, cta="muito texto " * 7), W, H).image
    assert img.size == (W, H)


# ---------- camadas ----------

def test_render_layers_ordem_e_tempos(tmp_path, font_path):
    kit = KitRender(hook=hook_style(font_path, duration_s=5),
                    watermark=wm(image_path=logo(tmp_path)), end_card=card(font_path))
    overlays = render.render_layers(tmp_path, hook_text="Oi", kit=kit, width=W, height=H,
                                    duration_s=10)
    assert [o.path.name for o in overlays] == ["gancho.png", "marca.png", "card.png"]
    assert [(o.start_s, o.end_s) for o in overlays] == [(0.0, 5), (None, None), (8.0, None)]
    assert all(o.path.exists() for o in overlays)
    with Image.open(overlays[2].path) as img:
        assert img.size == (W, H)


def test_render_layers_secoes_desligadas(tmp_path, font_path):
    kit = KitRender(hook=hook_style(font_path, duration_s=10), watermark=None, end_card=None)
    overlays = render.render_layers(tmp_path, hook_text="Oi", kit=kit, width=W, height=H,
                                    duration_s=3)
    assert [(o.path.name, o.end_s) for o in overlays] == [("gancho.png", 3)]
    assert render.render_layers(tmp_path, hook_text="Oi", kit=KitRender(None, None, None),
                                width=W, height=H, duration_s=3) == []


# ---------- fundo com imagem (FR-005a) ----------

STRIPE_A, STRIPE_B = (255, 0, 0), (0, 0, 255)


def stripes(tmp_path: Path, size=(1200, 1200), width: int = 60) -> Path:
    """Listras verticais vermelhas e azuis (a imagem de fundo sintética)."""
    img = Image.new("RGB", size, STRIPE_A)
    for x in range(width, size[0], 2 * width):
        img.paste(STRIPE_B, (x, 0, x + width, size[1]))
    path = tmp_path / "fundo.jpg"
    img.save(path, quality=95)
    return path


def mix(color: tuple[int, int, int], layer: tuple[int, int, int], opacity: float
        ) -> tuple[int, ...]:
    return tuple(round(c * (1 - opacity) + ly * opacity) for c, ly in zip(color, layer,
                                                                           strict=True))


def near(px: tuple[int, ...], expected: tuple[int, ...], tol: int = 12) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(px, expected, strict=True))


def test_gancho_com_imagem_sob_a_camada(tmp_path, font_path):
    style = hook_style(font_path, bg_color="#FFFFFF", bg_opacity=0.5, text_color="#00FF00",
                       bg_image_path=stripes(tmp_path))
    img = render.render_hook("Olha isso", style, W, H).image
    # Canto arredondado continua transparente; a caixa é opaca (imagem + camada).
    assert img.getpixel((0, 0))[3] == 0
    row = [img.getpixel((x, 8)) for x in range(20, img.width - 20)]
    assert all(px[3] == 255 for px in row)
    # Na faixa acima do texto aparecem as duas listras, clareadas pela camada branca a 50%.
    assert any(near(px[:3], mix(STRIPE_A, (255, 255, 255), 0.5)) for px in row)
    assert any(near(px[:3], mix(STRIPE_B, (255, 255, 255), 0.5)) for px in row)
    # O texto continua por cima, na cor pedida.
    assert (0, 255, 0, 255) in colors(img)


def test_gancho_com_imagem_e_opacidade_zero_mostra_a_imagem(tmp_path, font_path):
    style = hook_style(font_path, bg_opacity=0, bg_image_path=stripes(tmp_path))
    img = render.render_hook("Oi", style, W, H).image
    row = [img.getpixel((x, 8))[:3] for x in range(20, img.width - 20)]
    assert any(near(px, STRIPE_A) for px in row) and any(near(px, STRIPE_B) for px in row)


def test_card_com_imagem_cover_e_camada(tmp_path, font_path):
    # Imagem horizontal: o cover recorta o centro, sem distorcer (listras continuam verticais).
    style = card(font_path, bg_color="#000000", bg_opacity=0.45, text_color="#00FF00",
                 bg_image_path=stripes(tmp_path, size=(2400, 1200)))
    placed = render.render_end_card(style, W, H)
    img = placed.image
    assert (placed.x, placed.y, img.size) == (0, 0, (W, H))
    assert img.getchannel("A").getextrema() == (255, 255)
    top = [img.getpixel((x, 10))[:3] for x in range(W)]
    assert any(near(px, mix(STRIPE_A, (0, 0, 0), 0.45)) for px in top)
    assert any(near(px, mix(STRIPE_B, (0, 0, 0), 0.45)) for px in top)
    # Listra vertical: a mesma coluna tem a mesma cor em cima e embaixo.
    assert near(img.getpixel((30, 10))[:3], img.getpixel((30, H - 10))[:3])
    center = img.crop((0, H // 2 - 200, W, H // 2 + 200))
    assert (0, 255, 0, 255) in colors(center)


def test_card_com_imagem_e_logo_acima_da_camada(tmp_path, font_path):
    style = card(font_path, bg_opacity=1, bg_image_path=stripes(tmp_path),
                 logo_path=logo(tmp_path, color=(0, 255, 0, 255)))
    img = render.render_end_card(style, W, H).image
    # Camada opaca: a imagem some, mas o logo verde fica por cima.
    assert img.getpixel((10, 10))[:3] == (0, 0, 0)
    assert any(img.getpixel((W // 2, y))[:3] == (0, 255, 0) for y in range(0, H, 4))
