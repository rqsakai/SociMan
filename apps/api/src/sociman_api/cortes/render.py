"""Camadas do kit renderizadas como PNG com Pillow (research R2 e R7).

O texto do usuário (gancho, CTA, @ da marca d'água) só existe aqui, dentro dos PNGs: nunca vai
para a linha de comando do ffmpeg. Todas as medidas são relativas ao tamanho do vídeo; as
constantes em px valem para 1080 de largura e escalam com `largura / 1080`.

Geometria (a mesma da prévia no navegador, R7):
- **gancho:** caixa de até 90% da largura (mínimo 30% dela), fonte = 5% da caixa × 0,8 | 1 |
  1,3 (P, M, G), padding 30/25, entrelinha 20, raio 20; até 3 linhas (o `\\n` do usuário é
  respeitado); topo da caixa em 12% da altura (topo), centralizada (centro) ou em 70% (base);
  com imagem de fundo (FR-005a), a imagem preenche a caixa em cover (recorte central, sem
  distorção, cantos arredondados) e a cor de fundo × opacidade vai por cima como camada;
- **marca d'água:** largura = `escala_pct`% da largura do vídeo, `opacidade_pct` aplicada no
  alfa do PNG, margem = `margem_pct`% da largura, nos cantos ou centralizada em cima/embaixo;
- **card final:** quadro inteiro opaco na cor de fundo, com o logo opcional (35% da largura)
  acima do CTA (fonte de 8% da largura, reduzida até caber em 4 linhas), tudo centralizado;
  com imagem de fundo, a imagem cobre o quadro (cover) e a cor de fundo entra como camada com
  `opacidade_fundo`. Texto e logo ficam sempre acima da camada.

Mapeamento dos tokens resolvidos do kit (`cortes.kit_tokens`) para os estilos abaixo, feito
pelo worker depois de baixar os arquivos: `fonte` → `font_path` (arquivo local), `cor_*` →
hex `#RRGGBB`, `opacidade_fundo` (0..1), `espessura_contorno` (px a 1080), `posicao`,
`tamanho` e `duracao_s` iguais; `fundo_tipo = imagem` → `bg_image_path` (arquivo local
de `fundo_imagem_key`) e, no card final, `opacidade_fundo` → `bg_opacity`; marca d'água `tipo` logo/imagem → `kind="imagem"` com o
arquivo em `image_path`, `tipo` texto → `kind="texto"` com o `@handle` em `text`. Seção com
`ligado = false` vira `None` no `KitRender`.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont, ImageOps

from sociman_api.errors import ApiError

BASE_WIDTH = 1080
HOOK_MAX_CHARS = 120
HOOK_MAX_LINES = 3
HOOK_SIZE_SCALE = {"P": 0.8, "M": 1.0, "G": 1.3}
HOOK_Y = {"topo": 0.12, "base": 0.70}

HookPosition = Literal["topo", "centro", "base"]
HookSize = Literal["P", "M", "G"]
WatermarkPosition = Literal["sup_esq", "sup_dir", "inf_esq", "inf_dir", "centro_inf",
                            "centro_sup"]

# Nenhuma fonte do kit tem emoji; sem isto, viram caixinhas (mesmo corte do OpenShorts).
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF"
    "\U0000FE0E\U0000FE0F\U0000200D\U000020E3]+"
)


class InvalidHook(ApiError):
    def __init__(self, message: str = "Gancho longo demais"):
        super().__init__(400, "invalid_hook", message)


@dataclass(frozen=True)
class HookStyle:
    font_path: Path
    text_color: str  # "#RRGGBB"
    bg_color: str
    bg_opacity: float  # 0..1; 0 = sem caixa
    stroke_color: str
    stroke_width: float  # 0..10, em px a 1080 de largura
    position: HookPosition
    size: HookSize
    duration_s: float
    bg_image_path: Path | None = None  # com imagem: fica sob a camada `bg_color` × opacidade


@dataclass(frozen=True)
class WatermarkStyle:
    kind: Literal["imagem", "texto"]  # o logo do perfil entra como "imagem"
    position: WatermarkPosition
    scale_pct: float  # 5..40
    opacity_pct: float  # 10..100
    margin_pct: float  # 0..10
    image_path: Path | None = None
    text: str | None = None  # "@handle"
    font_path: Path | None = None
    text_color: str = "#FFFFFF"


@dataclass(frozen=True)
class EndCardStyle:
    cta: str
    font_path: Path
    text_color: str
    bg_color: str
    duration_s: float
    logo_path: Path | None = None
    bg_image_path: Path | None = None
    bg_opacity: float = 0.45  # a camada sobre a imagem; sem imagem o fundo é opaco


@dataclass(frozen=True)
class KitRender:
    """O que o worker queima no corte; `None` = seção desligada."""

    hook: HookStyle | None
    watermark: WatermarkStyle | None
    end_card: EndCardStyle | None


@dataclass(frozen=True)
class Placed:
    image: Image.Image  # RGBA
    x: int
    y: int


@dataclass(frozen=True)
class Overlay:
    """PNG já no disco e quando aparece; `None` = desde o início / até o fim."""

    path: Path
    x: int
    y: int
    start_s: float | None = None
    end_s: float | None = None


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _alpha(opacity: float) -> int:
    return round(max(0.0, min(1.0, opacity)) * 255)


def _cover(path: Path, width: int, height: int) -> Image.Image:
    """A imagem recortada no centro para preencher `width`×`height` sem distorcer (RGBA)."""
    with Image.open(path) as src:
        img = ImageOps.exif_transpose(src).convert("RGBA")
    return ImageOps.fit(img, (width, height), Image.Resampling.LANCZOS)


def _scale(width: int) -> float:
    return width / BASE_WIDTH


def _clean(text: str) -> str:
    text = _EMOJI_RE.sub("", text.replace("\r\n", "\n"))
    return "\n".join(re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.split("\n"))


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Quebra por largura em pixels; palavra maior que a linha é quebrada por caractere."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}" if current else word
            if font.getlength(candidate) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if font.getlength(word) <= max_width:
                current = word
                continue
            for ch in word:
                if current and font.getlength(current + ch) > max_width:
                    lines.append(current)
                    current = ch
                else:
                    current += ch
        lines.append(current)
    return lines


@dataclass(frozen=True)
class _HookGeometry:
    font: ImageFont.FreeTypeFont
    lines: list[str]
    target_width: int
    pad_x: int
    pad_y: int
    spacing: int
    radius: int
    stroke: int


def _hook_geometry(text: str, style: HookStyle, width: int) -> _HookGeometry:
    text = _clean(text).strip("\n")
    if not text.strip() or len(text) > HOOK_MAX_CHARS:
        raise InvalidHook()
    k = _scale(width)
    target = int(width * 0.9)
    font_size = max(1, int(target * 0.05 * HOOK_SIZE_SCALE[style.size]))
    font = ImageFont.truetype(str(style.font_path), font_size)
    pad_x, stroke = round(30 * k), round(style.stroke_width * k)
    lines = _wrap(text, font, target - 2 * pad_x - 2 * stroke)
    if len(lines) > HOOK_MAX_LINES:
        raise InvalidHook()
    return _HookGeometry(font=font, lines=lines, target_width=target, pad_x=pad_x,
                         pad_y=round(25 * k), spacing=round(20 * k), radius=round(20 * k),
                         stroke=stroke)


def wrap_hook(text: str, style: HookStyle, width: int) -> list[str]:
    """As linhas do gancho na fonte e no tamanho do kit, ou `InvalidHook` (> 120 ou > 3 linhas).

    Serve para recusar o envio (400 `invalid_hook`) antes de enfileirar o corte.
    """
    return _hook_geometry(text, style, width).lines


def render_hook(text: str, style: HookStyle, width: int, height: int) -> Placed:
    g = _hook_geometry(text, style, width)
    ascent, descent = g.font.getmetrics()
    line_h = ascent + descent
    text_w = max((g.font.getlength(line) for line in g.lines), default=0)
    box_w = min(g.target_width,
                max(int(text_w) + 2 * g.pad_x + 2 * g.stroke, int(g.target_width * 0.3)))
    n = len(g.lines)
    box_h = n * line_h + (n - 1) * g.spacing + 2 * g.pad_y + 2 * g.stroke

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    box = (0, 0, box_w - 1, box_h - 1)
    if style.bg_image_path is not None:
        mask = Image.new("L", (box_w, box_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=g.radius, fill=255)
        img.paste(_cover(style.bg_image_path, box_w, box_h), (0, 0), mask)
    alpha = _alpha(style.bg_opacity)
    if alpha:
        layer = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(box, radius=g.radius,
                                                fill=(*_rgb(style.bg_color), alpha))
        img.alpha_composite(layer)
    draw = ImageDraw.Draw(img)
    y = g.pad_y + g.stroke
    for line in g.lines:
        x = (box_w - g.font.getlength(line)) / 2
        draw.text((x, y), line, font=g.font, fill=(*_rgb(style.text_color), 255),
                  stroke_width=g.stroke, stroke_fill=(*_rgb(style.stroke_color), 255))
        y += line_h + g.spacing

    x = (width - box_w) // 2
    if style.position == "centro":
        top = (height - box_h) // 2
    else:
        top = min(int(height * HOOK_Y[style.position]), height - box_h)
    return Placed(img, x, max(0, top))


def _with_opacity(img: Image.Image, opacity_pct: float) -> Image.Image:
    factor = max(0.0, min(1.0, opacity_pct / 100))
    if factor < 1:
        img.putalpha(img.getchannel("A").point(lambda v: round(v * factor)))
    return img


def _text_image(text: str, font_path: Path, color: str, target_width: int) -> Image.Image:
    """Texto numa linha com a largura pedida (o tamanho da fonte sai da medida a 100 px)."""
    probe = ImageFont.truetype(str(font_path), 100)
    size = max(1, int(100 * target_width / max(1.0, probe.getlength(text))))
    font = ImageFont.truetype(str(font_path), size)
    left, top, right, bottom = font.getbbox(text)
    img = Image.new("RGBA", (max(1, right - left), max(1, bottom - top)), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((-left, -top), text, font=font, fill=(*_rgb(color), 255))
    return img


def _fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Redimensiona para a largura `max_w`, sem passar de `max_h` de altura."""
    ratio = min(max_w / img.width, max_h / img.height)
    size = (max(1, round(img.width * ratio)), max(1, round(img.height * ratio)))
    return img.resize(size, Image.Resampling.LANCZOS)


def render_watermark(style: WatermarkStyle, width: int, height: int) -> Placed:
    target_w = max(1, round(width * style.scale_pct / 100))
    margin = round(width * style.margin_pct / 100)
    max_h = max(1, height - 2 * margin)
    if style.kind == "texto":
        if not style.text or style.font_path is None:
            raise ValueError("marca d'água de texto precisa de text e font_path")
        img = _text_image(_clean(style.text).replace("\n", " "), style.font_path,
                          style.text_color, target_w)
        if img.height > max_h:
            img = _fit(img, target_w, max_h)
    else:
        if style.image_path is None:
            raise ValueError("marca d'água de imagem precisa de image_path")
        with Image.open(style.image_path) as src:
            img = _fit(ImageOps.exif_transpose(src).convert("RGBA"), target_w, max_h)
    img = _with_opacity(img, style.opacity_pct)

    w, h = img.size
    pos = style.position
    x = {"esq": margin, "dir": width - w - margin}.get(pos.split("_")[1], (width - w) // 2)
    y = margin if pos.startswith("sup") or pos == "centro_sup" else height - h - margin
    return Placed(img, max(0, x), max(0, y))


def render_end_card(style: EndCardStyle, width: int, height: int) -> Placed:
    if style.bg_image_path is None:
        img = Image.new("RGBA", (width, height), (*_rgb(style.bg_color), 255))
    else:
        img = _cover(style.bg_image_path, width, height)
        img.putalpha(255)
        img.alpha_composite(Image.new("RGBA", (width, height),
                                      (*_rgb(style.bg_color), _alpha(style.bg_opacity))))
    draw = ImageDraw.Draw(img)
    gap = round(height * 0.04)
    max_text_w = width * 0.85

    logo = None
    if style.logo_path is not None:
        with Image.open(style.logo_path) as src:
            logo = _fit(ImageOps.exif_transpose(src).convert("RGBA"), round(width * 0.35),
                        round(height * 0.25))

    cta = _clean(style.cta)
    size = max(1, round(width * 0.08))
    while True:
        font = ImageFont.truetype(str(style.font_path), size)
        lines = _wrap(cta, font, max_text_w)
        ascent, descent = font.getmetrics()
        line_h = ascent + descent
        spacing = round(line_h * 0.2)
        text_h = len(lines) * line_h + (len(lines) - 1) * spacing
        if (len(lines) <= 4 and text_h <= height * 0.5) or size <= 8:
            break
        size = round(size * 0.9)

    block_h = text_h + (logo.height + gap if logo else 0)
    y = (height - block_h) // 2
    if logo:
        img.alpha_composite(logo, ((width - logo.width) // 2, y))
        y += logo.height + gap
    for line in lines:
        draw.text(((width - font.getlength(line)) / 2, y), line, font=font,
                  fill=(*_rgb(style.text_color), 255))
        y += line_h + spacing
    return Placed(img, 0, 0)


def render_layers(workdir: str | Path, *, hook_text: str, kit: KitRender, width: int,
                  height: int, duration_s: float) -> list[Overlay]:
    """Grava os PNGs das camadas ligadas em `workdir` e devolve os overlays na ordem de cima.

    Ordem: gancho (0..duração do kit), marca d'água (o vídeo todo) e card final (os últimos
    N s, por último para cobrir a marca d'água).
    """
    workdir = Path(workdir)
    overlays: list[Overlay] = []

    def save(name: str, placed: Placed, start: float | None, end: float | None) -> None:
        path = workdir / f"{name}.png"
        placed.image.save(path, format="PNG")
        overlays.append(Overlay(path, placed.x, placed.y, start, end))

    if kit.hook is not None and hook_text.strip():
        save("gancho", render_hook(hook_text, kit.hook, width, height), 0.0,
             min(kit.hook.duration_s, duration_s))
    if kit.watermark is not None:
        save("marca", render_watermark(kit.watermark, width, height), None, None)
    if kit.end_card is not None:
        save("card", render_end_card(kit.end_card, width, height),
             max(0.0, duration_s - kit.end_card.duration_s), None)
    return overlays
