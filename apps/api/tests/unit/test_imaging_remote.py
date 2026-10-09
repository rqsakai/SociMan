"""Miniaturas e avatares do YouTube pelo imgproxy (T026, research R13)."""

import base64

import pytest

from sociman_api import imaging
from sociman_api.config import get_settings

THUMB = "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"


def _fonte(url: str) -> str:
    raw = url.rsplit("/", 1)[-1]
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()


@pytest.fixture
def sem_assinatura(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "imgproxy_key", None)
    monkeypatch.setattr(s, "imgproxy_salt", None)
    return s


@pytest.mark.parametrize("url", [
    THUMB,
    "https://yt3.ggpht.com/abc=s240-c-k",
    "https://yt3.googleusercontent.com/abc=s240",
])
def test_origens_do_youtube_viram_url_do_imgproxy(sem_assinatura, url):
    out = imaging.remote_url(url, 320, 180)
    assert out.startswith(f"{sem_assinatura.img_public_path}/unsafe/rs:fill:320:180/f:webp/")
    assert _fonte(out) == url


@pytest.mark.parametrize("url", [
    None, "", "http://i.ytimg.com/vi/x/mqdefault.jpg", "https://i.ytimg.com.evil.com/x.jpg",
    "https://example.com/x.jpg", "s3://sociman/perfis/x.png",
])
def test_outra_origem_nao_vira_proxy(sem_assinatura, url):
    assert imaging.remote_url(url, 320, 180) is None


def test_assinada_com_chave_e_salt(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "imgproxy_key", "aa" * 32)
    monkeypatch.setattr(s, "imgproxy_salt", "bb" * 16)
    out = imaging.remote_url(THUMB, 160, 160)
    path = out.removeprefix(f"{s.img_public_path}/").split("/", 1)
    assert path[0] != "unsafe"
    assert path[0] == imaging.sign_path("/" + path[1], "aa" * 32, "bb" * 16)
