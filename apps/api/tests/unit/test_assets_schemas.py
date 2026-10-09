"""Schemas e regras por tipo da biblioteca de assets (T010)."""

import pytest
from pydantic import ValidationError

from sociman_api.assets import schemas
from sociman_api.assets.models import AssetTipo, FileRole
from sociman_api.errors import ApiError


def _invalid(fn, *args) -> tuple[str, str]:
    with pytest.raises(ApiError) as exc:
        fn(*args)
    assert (exc.value.status, exc.value.code) == (400, "invalid_asset")
    return exc.value.details["field"], exc.value.message


def test_campos_de_avatar_so_no_avatar():
    schemas.check_campos(AssetTipo.avatar, {"prompt": "x", "voice_tone": "y",
                                            "image_rules": "z"})
    schemas.check_campos(AssetTipo.cenario, {"prompt": "x"})
    assert _invalid(schemas.check_campos, AssetTipo.cenario, {"voice_tone": "y"}) == \
        ("voiceTone", "voiceTone: campo não se aplica a este tipo")
    assert _invalid(schemas.check_campos, AssetTipo.sticker, {"prompt": "x"})[0] == "prompt"
    assert _invalid(schemas.check_campos, AssetTipo.fundo, {"image_rules": "x"})[0] == \
        "imageRules"
    schemas.check_campos(AssetTipo.fundo, {"prompt": None})  # nulo sempre passa


def test_campos_do_arquivo_por_papel():
    schemas.check_file_campos(AssetTipo.avatar, FileRole.referencia, {"look": "Cozinha"})
    schemas.check_file_campos(AssetTipo.avatar, FileRole.pose,
                              {"label": "piscando", "quando_usar": "fim"})
    assert _invalid(schemas.check_file_campos, AssetTipo.avatar, FileRole.pose,
                    {"look": "x"})[0] == "look"
    assert _invalid(schemas.check_file_campos, AssetTipo.avatar, FileRole.referencia,
                    {"label": "x"})[0] == "label"
    assert _invalid(schemas.check_file_campos, AssetTipo.cenario, FileRole.pose, {})[0] == \
        "role"
    assert _invalid(schemas.check_file_campos, AssetTipo.cenario, FileRole.referencia,
                    {"look": "x"})[0] == "look"
    assert _invalid(schemas.check_file_campos, AssetTipo.sticker, FileRole.referencia,
                    {})[0] == "role"


def test_tags_normalizadas():
    data = schemas.AssetCreate(tipo="sticker", name="  Oi ", tags=[" Promo", "promo", "REAÇÃO"])
    assert data.name == "Oi"
    assert data.tags == ["promo", "reação"]
    for bad in (["x" * 31], [" "], [f"t{i}" for i in range(21)]):
        with pytest.raises(ValidationError):
            schemas.AssetCreate(tipo="sticker", name="a", tags=bad)


def test_prompt_sem_trim_e_limites():
    texto = "  A cheerful 1950s pin-up style woman…\n"
    assert schemas.AssetCreate(tipo="avatar", name="a", prompt=texto).prompt == texto
    with pytest.raises(ValidationError):
        schemas.AssetCreate(tipo="avatar", name="a", prompt="x" * 2001)
    with pytest.raises(ValidationError):
        schemas.AssetCreate(tipo="avatar", name="x" * 81)
    with pytest.raises(ValidationError):
        schemas.AssetCreate(tipo="avatar", name="   ")
    with pytest.raises(ValidationError):
        schemas.AssetCreate(tipo="avatar", name="a", voice_tone="x" * 501)


def test_patch_nao_aceita_tipo():
    with pytest.raises(ValidationError):
        schemas.AssetPatch(version=1, tipo="fundo")


def test_pose_label_obrigatorio_no_patch_do_arquivo():
    with pytest.raises(ValidationError):
        schemas.FilePatch(version=1, label="")
    with pytest.raises(ValidationError):
        schemas.FilePatch(version=1, label="x" * 61)
