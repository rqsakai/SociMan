"""Tokens de links de mídia (R6): assinatura, validade e adulteração."""

import base64
import json
import time
import uuid

import pytest

from sociman_api import midia
from sociman_api.errors import ApiError

ID = uuid.uuid4()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _forge(payload: dict) -> str:
    """Token com assinatura válida para um payload arbitrário (simula um bug de emissão)."""
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{body}.{_b64(midia._mac(body))}"


def _rejects(token: str, **kw) -> None:
    with pytest.raises(ApiError) as exc:
        midia.verify(token, **kw)
    assert exc.value.status == 403 and exc.value.code == "invalid_link"


def test_round_trip_with_expiration():
    now = time.time()
    token = midia.sign("corte_marcado", ID, variant="download", now=now)
    claims = midia.verify(token, now=now)
    assert claims.kind == "corte_marcado" and claims.id == ID
    assert claims.variant == "download"
    assert claims.exp == int(now) + midia.LINK_TTL


def test_expired_token_is_rejected():
    now = time.time()
    token = midia.sign("fonte", ID, ttl=10, now=now)
    midia.verify(token, now=now + 9)
    _rejects(token, now=now + 11)


def test_font_and_watermark_links_without_expiration():
    for kind in ("fonte", "marca_dagua"):
        token = midia.sign(kind, ID, ttl=None)
        assert midia.verify(token, now=time.time() + 10 * 365 * 86400).exp is None
    link = midia.link("fonte", ID, ttl=None)
    assert link.url.startswith("/api/midia/") and link.expires_at is None
    assert midia.link("fonte", ID).expires_at is not None


def test_video_never_without_expiration():
    with pytest.raises(ValueError):
        midia.sign("corte_original", ID, ttl=None)
    _rejects(_forge({"k": "corte_original", "id": str(ID)}))


@pytest.mark.parametrize("payload", [
    {"k": "senha", "id": str(ID)},
    {"k": "fonte", "id": "nao-e-uuid"},
    {"k": "fonte"},
    {"k": "fonte", "id": str(ID), "exp": "amanhã"},
    {"k": "fonte", "id": str(ID), "v": 3},
])
def test_malformed_payload_is_rejected(payload):
    _rejects(_forge(payload))


def test_tampering_is_rejected():
    token = midia.sign("fonte", ID)
    body, sig = token.split(".")
    other = midia.sign("fonte", uuid.uuid4()).split(".")[0]
    _rejects(f"{other}.{sig}")
    _rejects(f"{body}.{sig[:-2]}AA")
    _rejects(body)
    _rejects(f"{body}.{sig}.x")
    _rejects("x" * 600)
    _rejects("!!!.???")


def test_domain_separates_from_other_hmacs():
    # A mesma chave sem o domínio `midia:` não gera uma assinatura aceita.
    import hashlib
    import hmac

    from sociman_api.config import get_settings

    body = midia.sign("fonte", ID).split(".")[0]
    raw = hmac.new(get_settings().jwt_secret.encode(), body.encode(), hashlib.sha256).digest()
    _rejects(f"{body}.{_b64(raw)}")


def test_imagem_link_sem_validade_e_estavel():
    # Spec 007 (R7): o token sem `exp` é determinístico, então o "Copiar link" é estável.
    a = midia.link("imagem", ID, ttl=None)
    assert a.expires_at is None and a.url == midia.link("imagem", ID, ttl=None).url
    assert midia.verify(a.url.removeprefix(midia.PATH_PREFIX),
                        now=time.time() + 10 * 365 * 86400).kind == "imagem"
    assert midia.link("imagem", ID).expires_at is not None
