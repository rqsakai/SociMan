"""Seção `openshorts` da exportação do kit (research R9, FR-011, SC-002).

Traduz os tokens **resolvidos** (`tokens.resolve_tokens`, com cores em hex e cada `fonte` como
`{ref, name, family, style, …}`) para o que o gerador de cortes aceita hoje:
- `subtitle`: os campos do `SubtitleRequest` (`openshorts/app.py:3696`), já dentro das faixas
  do `_clamp_number` do gerador (`subtitles.py`);
- `hook`: o preset mais próximo entre os 6 `HOOK_STYLES` (`openshorts/hooks.py:192`), por
  distância CIELAB, **sempre com `enabled: false`**: só o SociMan queima o gancho (US4);
- `approximations`: notas legíveis de tudo o que o gerador não reproduz exatamente.
"""

from collections.abc import Mapping
from typing import Any

from sociman_api.marca.tokens import DEFAULT_FONTS, DEFAULT_PREFIX

# Nomes que o gerador resolve pelo fontconfig (Anton, Noto Serif e Liberation, via
# openshorts-fontmap.conf).
GENERATOR_FONTS = {
    "anton": "Anton",
    "noto-serif-bold": "Noto Serif",
    "liberation-sans": "Liberation Sans",
    "liberation-serif": "Liberation Serif",
}
HOOK_FONT = "padrao:noto-serif-bold"  # o gerador usa sempre Noto Serif Bold no gancho

POSITION = {"topo": "top", "meio": "middle", "base": "bottom"}
STYLE = {"classico": "classic", "karaoke": "karaoke"}
EFFECT = {"nenhum": "none", "brilho": "glow", "pop": "pop", "caixa": "box"}
HOOK_POSITION = {"topo": "top", "centro": "center", "base": "bottom"}
HOOK_SIZE = {"P": "S", "M": "M", "G": "L"}
BASE_OPACITY = 1.0  # não é token do kit: é o padrão do próprio gerador

# Cópia de HOOK_STYLES (hooks.py:192-205): caixa RGBA (alfa 0 = sem caixa) e texto RGB.
HOOK_STYLES: dict[str, dict[str, tuple[int, ...]]] = {
    "classic": {"box": (255, 255, 255, 240), "text": (0, 0, 0)},
    "dark": {"box": (18, 18, 20, 235), "text": (255, 255, 255)},
    "yellow": {"box": (255, 214, 0, 245), "text": (0, 0, 0)},
    "red": {"box": (220, 38, 38, 245), "text": (255, 255, 255)},
    "outline": {"box": (0, 0, 0, 0), "text": (255, 255, 255)},
    "outline_yellow": {"box": (0, 0, 0, 0), "text": (255, 214, 0)},
}
BOXLESS_OPACITY = 0.2  # abaixo disso o fundo do kit conta como "sem caixa"
EXACT_DISTANCE = 5.0

_CONDENSED = ("condensed", "narrow", "compressed", "display", "black", "heavy", "impact")


# ---- cor: sRGB → CIELAB (D65), feito à mão para não trazer dependência ----

def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[int, ...]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def _lab(rgb: tuple[int, ...]) -> tuple[float, float, float]:
    def linear(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb[:3])
    x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883

    def f(t: float) -> float:
        d = 6 / 29
        return t ** (1 / 3) if t > d**3 else t / (3 * d * d) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str | tuple[int, ...], b: str | tuple[int, ...]) -> float:
    """ΔE CIE76 entre duas cores (hex ou RGB)."""
    la = _lab(_rgb(a) if isinstance(a, str) else a)
    lb = _lab(_rgb(b) if isinstance(b, str) else b)
    return sum((p - q) ** 2 for p, q in zip(la, lb, strict=True)) ** 0.5


# ---- gancho: preset mais próximo ----

def nearest_hook_style(bg: str, bg_opacity: float, text: str) -> tuple[str, float]:
    """(preset, distância). Fundo com opacidade < 0,2 só compara com os presets sem caixa, e
    aí só o texto conta; senão, `0,6 × ΔE(fundo) + 0,4 × ΔE(texto)` entre os 4 com caixa."""
    boxless = bg_opacity < BOXLESS_OPACITY
    best: tuple[str, float] | None = None
    for name, preset in HOOK_STYLES.items():
        if (preset["box"][3] == 0) != boxless:
            continue
        d_text = delta_e(text, preset["text"])
        dist = d_text if boxless else 0.6 * delta_e(bg, preset["box"]) + 0.4 * d_text
        if best is None or dist < best[1]:
            best = (name, dist)
    assert best is not None
    return best


def _color_note(what: str, kit_color: str, preset_rgb: tuple[int, ...], style: str) -> str:
    if delta_e(kit_color, preset_rgb) < EXACT_DISTANCE:
        return f"{what} exato"
    return f"{what} {kit_color} aproximado para o preset {style} ({_hex(preset_rgb)})"


def _font_label(font: Mapping[str, Any]) -> str:
    return str(font.get("name") or font.get("family") or font.get("ref"))


def hook_section(hook: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    style, dist = nearest_hook_style(hook["cor_fundo"], hook["opacidade_fundo"],
                                     hook["cor_texto"])
    preset = HOOK_STYLES[style]
    exact = dist < EXACT_DISTANCE
    notes: list[str] = []
    if not exact:
        text_note = _color_note("texto", hook["cor_texto"], preset["text"], style)
        if preset["box"][3] == 0:
            notes.append(f"hook: sem fundo; {text_note}")
        else:
            bg_note = _color_note("fundo", hook["cor_fundo"], preset["box"], style)
            notes.append(f"hook: {bg_note}; {text_note}")
    if hook.get("fundo_tipo") == "imagem":
        notes.append("hook: o gerador não tem fundo com imagem; vale só a cor do fundo")
    font = hook["fonte"]
    if font.get("ref") != HOOK_FONT:
        notes.append(f"hook: o gerador usa sempre Noto Serif Bold (o kit usa {_font_label(font)})")
    duration = hook["duracao_s"]
    section = {
        "enabled": False,
        "style": style,
        "size": HOOK_SIZE[hook["tamanho"]],
        "position": HOOK_POSITION[hook["posicao"]],
        "duration_seconds": int(duration) if float(duration).is_integer() else duration,
        "exact": exact,
        "distance": round(dist, 1),
    }
    return section, notes


# ---- legenda ----

def generator_font(font: Mapping[str, Any]) -> tuple[str, bool]:
    """(`font_name` do gerador, exato?). Fonte própria cai para a padrão mais parecida:
    serifada → Noto Serif; condensada/display → Anton; senão Liberation Sans."""
    ref = str(font.get("ref", ""))
    if ref.startswith(DEFAULT_PREFIX) and ref[len(DEFAULT_PREFIX):] in DEFAULT_FONTS:
        return GENERATOR_FONTS[ref[len(DEFAULT_PREFIX):]], True
    desc = f"{font.get('family', '')} {font.get('style', '')}".lower()
    if "serif" in desc and "sans" not in desc:
        return "Noto Serif", False
    if any(word in desc for word in _CONDENSED):
        return "Anton", False
    return "Liberation Sans", False


def subtitle_section(caption: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    font = caption["fonte"]
    font_name, exact = generator_font(font)
    notes: list[str] = []
    if not exact:
        note = (f"legenda: a fonte {_font_label(font)} (do perfil) não existe no gerador; "
                f"usada {font_name}")
        if font.get("url"):
            note += f"; original em {font['url']}"
        notes.append(note)
    if caption["estilo"] == "classico" and caption["efeito"] != "nenhum":
        notes.append("legenda: o gerador só aplica o efeito no estilo karaokê")
    section = {
        "position": POSITION[caption["posicao"]],
        "font_size": int(caption["tamanho"]),
        "font_name": font_name,
        "font_color": caption["cor_texto"],
        "border_color": caption["cor_contorno"],
        "border_width": int(caption["espessura_contorno"]),
        "bg_color": caption["cor_fundo"],
        "bg_opacity": float(caption["opacidade_fundo"]),
        "style": STYLE[caption["estilo"]],
        "highlight_color": caption["cor_destaque"],
        "effect": EFFECT[caption["efeito"]],
        "base_opacity": BASE_OPACITY,
        "uppercase": bool(caption["maiusculas"]),
    }
    return section, notes


def openshorts_section(resolved: Mapping[str, Any]) -> dict[str, Any]:
    """`{subtitle, hook, approximations}` a partir dos tokens resolvidos."""
    subtitle, sub_notes = subtitle_section(resolved["caption"])
    hook, hook_notes = hook_section(resolved["hook"])
    return {"subtitle": subtitle, "hook": hook, "approximations": sub_notes + hook_notes}
