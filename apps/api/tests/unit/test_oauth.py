"""URL de autorização, PKCE e `state` do Login Kit (spec 015, T025, research R1 a R3)."""

import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from sociman_api.config import Settings
from sociman_api.publicacao.tiktok import oauth


def _settings(**over) -> Settings:
    base = {"tiktok_client_key": "chave-de-teste", "jwt_secret": "x" * 40}
    return Settings(**{**base, **over})


def test_url_web_sem_pkce():
    s = _settings()
    url = oauth.url_autorizacao("st", "https://casa/app/conexoes/retorno", s=s)
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == oauth.AUTORIZAR_URL
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert q == {
        "client_key": "chave-de-teste", "response_type": "code",
        "scope": ("user.info.basic,user.info.profile,video.upload,video.publish,"
                  "user.info.stats,video.list"),  # spec 016 (R1)
        "redirect_uri": "https://casa/app/conexoes/retorno", "state": "st",
    }


def test_url_desktop_com_pkce():
    s = _settings(tiktok_scopes="user.info.basic,video.upload")
    url = oauth.url_autorizacao("st", "http://localhost:8180/r", "v" * 64, s=s)
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["scope"] == "user.info.basic,video.upload"
    assert q["redirect_uri"] == "http://localhost:8180/r"
    assert q["code_challenge"] == oauth.code_challenge("v" * 64)
    assert q["code_challenge_method"] == "S256"


def test_code_challenge_funcao_unica():
    verifier = "abc"
    assert oauth.code_challenge(verifier) == hashlib.sha256(b"abc").hexdigest()


def test_verifier_e_state():
    v = oauth.novo_code_verifier()
    assert 43 <= len(v) <= 128
    assert v != oauth.novo_code_verifier()
    st = oauth.novo_state()
    assert len(st) >= 43  # 32 bytes em base64url
    assert st != oauth.novo_state()


@pytest.mark.parametrize(("scopes", "esperado"), [
    ("user.info.basic,video.upload", ["user.info.basic", "video.upload"]),
    ("user.info.basic video.upload", ["user.info.basic", "video.upload"]),
    (" video.upload, ", ["video.upload"]),
    ("", []),
    (None, []),
])
def test_escopos(scopes, esperado):
    assert oauth.escopos(scopes) == esperado
