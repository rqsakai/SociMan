"""Mapeamento para o gerador de cortes (T017, R9, SC-002): legenda dentro das faixas do
`SubtitleRequest` e preset de gancho mais próximo por CIELAB."""

import random
import uuid

import pytest

from sociman_api.marca.openshorts import (
    HOOK_STYLES,
    delta_e,
    generator_font,
    nearest_hook_style,
    openshorts_section,
)
from sociman_api.marca.tokens import DEFAULT_FONTS, KitTokens, default_kit, resolve_tokens

# Faixas e opções copiadas do gerador (openshorts/app.py:3696 e subtitles.py `_clamp_number`,
# fontmap), independentes do módulo testado.
GEN_POSITIONS = {"top", "middle", "bottom"}
GEN_STYLES = {"classic", "karaoke"}
GEN_EFFECTS = {"none", "glow", "pop", "box"}
GEN_FONTS = {"Anton", "Noto Serif", "Liberation Sans", "Liberation Serif", "Verdana", "Arial",
             "Helvetica", "Georgia", "Impact"}
GEN_FIELDS = {"position", "font_size", "font_name", "font_color", "border_color",
              "border_width", "bg_color", "bg_opacity", "style", "highlight_color", "effect",
              "base_opacity", "uppercase"}
HEX = "0123456789ABCDEF"


def _fonts(kit: KitTokens) -> dict:
    out = {}
    for field in ("caption", "hook", "watermark", "end_card"):
        ref = getattr(kit, field).fonte
        if ref.startswith("padrao:"):
            f = DEFAULT_FONTS[ref.removeprefix("padrao:")]
            out[ref] = {"ref": ref, "name": f.name, "family": f.family, "style": f.style}
        else:
            out[ref] = {"ref": ref, "name": "Pergaminho", "family": "Pergaminho Serif",
                        "style": "Regular", "url": "/api/midia/x"}
    return out


def _section(kit: KitTokens) -> dict:
    return openshorts_section(resolve_tokens(kit, _fonts(kit)))


def _assert_subtitle_in_generator_ranges(sub: dict) -> None:
    assert set(sub) == GEN_FIELDS
    assert sub["position"] in GEN_POSITIONS
    assert sub["style"] in GEN_STYLES
    assert sub["effect"] in GEN_EFFECTS
    assert sub["font_name"] in GEN_FONTS
    assert isinstance(sub["font_size"], int) and 10 <= sub["font_size"] <= 200
    assert isinstance(sub["border_width"], int) and 0 <= sub["border_width"] <= 10
    assert 0.0 <= sub["bg_opacity"] <= 1.0
    assert 0.05 <= sub["base_opacity"] <= 1.0
    assert isinstance(sub["uppercase"], bool)
    for key in ("font_color", "border_color", "bg_color", "highlight_color"):
        value = sub[key]
        assert len(value) == 7 and value[0] == "#" and all(c in HEX for c in value[1:])


def _random_kit(rng: random.Random) -> KitTokens:
    def color() -> str:
        return "#" + "".join(rng.choice(HEX) for _ in range(6))

    palette = [{"chave": f"c{i}", "nome": f"C{i}", "valor": color()}
               for i in range(rng.randint(1, 12))]

    def cor_ref() -> str:
        return rng.choice([color(), f"paleta:{rng.choice(palette)['chave']}"])

    fonte = rng.choice([*(f"padrao:{k}" for k in DEFAULT_FONTS), f"perfil:{uuid.uuid4()}"])
    data = default_kit(None).model_dump(mode="json", by_alias=True)
    data["palette"] = palette
    data["caption"] = {
        "fonte": fonte, "tamanho": rng.randint(10, 200), "cor_texto": cor_ref(),
        "cor_contorno": cor_ref(), "espessura_contorno": rng.randint(0, 10),
        "cor_fundo": cor_ref(), "opacidade_fundo": rng.randint(0, 20) * 0.05,
        "estilo": rng.choice(["classico", "karaoke"]), "cor_destaque": cor_ref(),
        "efeito": rng.choice(["nenhum", "brilho", "pop", "caixa"]),
        "posicao": rng.choice(["topo", "meio", "base"]), "maiusculas": rng.random() < 0.5,
    }
    data["hook"] |= {"cor_texto": cor_ref(), "cor_fundo": cor_ref(),
                     "cor_contorno": cor_ref(), "opacidade_fundo": rng.random(),
                     "tamanho": rng.choice("PMG"), "posicao": rng.choice(["topo", "centro", "base"]),
                     "duracao_s": rng.randint(2, 20) / 2}
    for section in ("watermark", "endCard"):
        for key in ("cor_texto", "cor_fundo"):
            if key in data[section]:
                data[section][key] = cor_ref()
    return KitTokens.model_validate(data)


# ---- SC-002 ----

def test_random_kits_stay_inside_generator_ranges():
    rng = random.Random(20260929)
    for _ in range(300):
        section = _section(_random_kit(rng))
        _assert_subtitle_in_generator_ranges(section["subtitle"])
        hook = section["hook"]
        assert hook["enabled"] is False
        assert hook["style"] in HOOK_STYLES
        assert hook["size"] in {"S", "M", "L"}
        assert hook["position"] in {"top", "center", "bottom"}
        assert 1 <= hook["duration_seconds"] <= 10


@pytest.mark.parametrize("extreme", [
    {"tamanho": 10, "espessura_contorno": 0, "opacidade_fundo": 0.0},
    {"tamanho": 200, "espessura_contorno": 10, "opacidade_fundo": 1.0},
])
def test_extreme_kits_stay_inside_generator_ranges(extreme):
    data = default_kit(None).model_dump(mode="json", by_alias=True)
    data["caption"] |= extreme
    section = _section(KitTokens.model_validate(data))
    _assert_subtitle_in_generator_ranges(section["subtitle"])
    assert section["subtitle"]["font_size"] == extreme["tamanho"]


def test_default_kit_maps_to_auto_caption_style():
    section = _section(default_kit(None))
    assert section["subtitle"] == {
        "position": "bottom", "font_size": 44, "font_name": "Anton", "font_color": "#FFFFFF",
        "border_color": "#000000", "border_width": 4, "bg_color": "#000000", "bg_opacity": 0.0,
        "style": "karaoke", "highlight_color": "#FFE500", "effect": "pop", "base_opacity": 1.0,
        "uppercase": True,
    }
    assert section["hook"] == {"enabled": False, "style": "classic", "size": "M",
                               "position": "top", "duration_seconds": 5, "exact": True,
                               "distance": 0.0}
    assert section["approximations"] == []


# ---- preset de gancho ----

def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


@pytest.mark.parametrize("name", list(HOOK_STYLES))
def test_each_preset_is_its_own_nearest(name):
    preset = HOOK_STYLES[name]
    opacity = preset["box"][3] / 255
    style, dist = nearest_hook_style(_hex(preset["box"]), opacity, _hex(preset["text"]))
    assert style == name
    assert dist == pytest.approx(0, abs=1e-9)


def test_pink_background_goes_to_red_with_note():
    data = default_kit(None).model_dump(mode="json", by_alias=True)
    data["palette"].append({"chave": "rosa", "nome": "Rosa Queridinhos", "valor": "#FF5FA2"})
    data["hook"] |= {"cor_fundo": "paleta:rosa", "cor_texto": "#FFFFFF", "fonte": "padrao:anton"}
    section = _section(KitTokens.model_validate(data))
    hook = section["hook"]
    assert hook["style"] == "red" and hook["exact"] is False and hook["distance"] >= 5
    assert "hook: fundo #FF5FA2 aproximado para o preset red (#DC2626); texto exato" in \
        section["approximations"]
    assert "hook: o gerador usa sempre Noto Serif Bold (o kit usa Anton)" in \
        section["approximations"]


def test_boxless_yellow_text_goes_to_outline_yellow():
    style, _ = nearest_hook_style("#000000", 0.1, "#FFE500")
    assert style == "outline_yellow"
    style, _ = nearest_hook_style("#FFD600", 0.9, "#FFE500")  # com caixa, nunca sem caixa
    assert style in {"classic", "dark", "yellow", "red"}


def test_delta_e_basics():
    assert delta_e("#FFFFFF", "#FFFFFF") == 0
    assert delta_e("#000000", "#FFFFFF") == pytest.approx(100, abs=0.01)


# ---- fonte da legenda ----

@pytest.mark.parametrize(("family", "style", "expected"), [
    ("Pergaminho Serif", "Regular", "Noto Serif"),
    ("Merriweather Serif", "Bold", "Noto Serif"),
    ("Bebas Neue Condensed", "Regular", "Anton"),
    ("Oswald", "Black", "Anton"),
    ("Open Sans", "Regular", "Liberation Sans"),
    ("PT Sans Serif", "Regular", "Liberation Sans"),
])
def test_own_font_falls_back_to_similar_default(family, style, expected):
    name, exact = generator_font({"ref": f"perfil:{uuid.uuid4()}", "family": family,
                                  "style": style})
    assert (name, exact) == (expected, False)


@pytest.mark.parametrize(("key", "expected"), [
    ("anton", "Anton"), ("noto-serif-bold", "Noto Serif"),
    ("liberation-sans", "Liberation Sans"), ("liberation-serif", "Liberation Serif"),
])
def test_default_fonts_are_exact(key, expected):
    assert generator_font({"ref": f"padrao:{key}"}) == (expected, True)


def test_own_caption_font_is_noted_with_link():
    data = default_kit(None).model_dump(mode="json", by_alias=True)
    data["caption"]["fonte"] = f"perfil:{uuid.uuid4()}"
    section = _section(KitTokens.model_validate(data))
    assert section["subtitle"]["font_name"] == "Noto Serif"
    note = section["approximations"][0]
    assert note.startswith("legenda: a fonte Pergaminho (do perfil) não existe no gerador")
    assert note.endswith("original em /api/midia/x")


def test_effect_in_classic_style_is_noted():
    data = default_kit(None).model_dump(mode="json", by_alias=True)
    data["caption"]["estilo"] = "classico"
    section = _section(KitTokens.model_validate(data))
    assert "legenda: o gerador só aplica o efeito no estilo karaokê" in section["approximations"]
