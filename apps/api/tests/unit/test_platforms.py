"""platforms.py: normalização de @, links (R8) e sugestão de slug (R9)."""

import pytest

from sociman_api.perfis.models import Platform
from sociman_api.perfis.platforms import (
    PLATFORMS,
    SLUG_RE,
    handle_from_url,
    normalize_handle,
    suggest_slug,
    url_for,
)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Achadinhos da Lú!", "achadinhos-da-lu"),
        ("  Café & Pão  ", "cafe-pao"),
        ("Ação---Já", "acao-ja"),
        ("X" * 80, "x" * 60),
        ("a" * 59 + " b", "a" * 59),  # corte não termina em hífen
    ],
)
def test_suggest_slug(name, slug):
    assert suggest_slug(name) == slug
    assert SLUG_RE.match(slug)


def test_suggest_slug_may_be_too_short():
    assert suggest_slug("!!!") == ""


@pytest.mark.parametrize(
    ("raw", "handle"),
    [
        ("@ Meus.Queridinhos ", "meus.queridinhos"),
        ("achadinhos_da_lu", "achadinhos_da_lu"),
        ("@@Lu-Shop", "lu-shop"),
    ],
)
def test_normalize_handle(raw, handle):
    assert normalize_handle(raw) == handle


@pytest.mark.parametrize("raw", ["", "@", "lú", "a/b", "x" * 61])
def test_normalize_handle_rejects(raw):
    with pytest.raises(ValueError):
        normalize_handle(raw)


@pytest.mark.parametrize(
    ("platform", "url", "handle"),
    [
        (Platform.tiktok, "https://www.tiktok.com/@Achadinhos.Lu?lang=pt-BR", "achadinhos.lu"),
        (Platform.tiktok, "tiktok.com/@lu_shop/", "lu_shop"),
        (Platform.youtube, "https://www.youtube.com/@AchadinhosDaLu", "achadinhosdalu"),
        (Platform.youtube, "https://m.youtube.com/@lu/shorts", None),  # subpágina não bate
        (Platform.instagram, "https://instagram.com/lu.shop/", "lu.shop"),
        (Platform.kwai, "https://www.kwai.com/@lushop", "lushop"),
        (Platform.facebook, "https://web.facebook.com/LuShop", "lushop"),
        (Platform.x, "https://twitter.com/lushop", "lushop"),
        (Platform.x, "https://x.com/@lushop#top", "lushop"),
        (Platform.tiktok, "https://www.youtube.com/@lu", None),  # link de outra plataforma
        (Platform.outra, "https://exemplo.com/lu", None),
    ],
)
def test_handle_from_url(platform, url, handle):
    assert handle_from_url(platform, url) == handle


def test_url_for_roundtrip():
    for platform, info in PLATFORMS.items():
        url = url_for(platform, "lu.shop")
        if info.url_template is None:
            assert url is None
            continue
        assert handle_from_url(platform, url) == "lu.shop"
    assert url_for(Platform.tiktok, "lu") == "https://www.tiktok.com/@lu"
    assert url_for(Platform.x, "lu") == "https://x.com/lu"


def test_every_platform_has_info():
    assert set(PLATFORMS) == set(Platform)
