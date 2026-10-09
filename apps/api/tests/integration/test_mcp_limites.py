"""T053 (US5, R7, FR-027): limites por minuto e de escritas por dia, por cliente."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import redis

from integration.mcp_helpers import bearer, criar_cliente, ligar
from integration.postagem_helpers import criar_perfil, dono  # noqa: F401
from sociman_api.mcp import limites


@pytest.fixture
def base(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    return h, criar_perfil(client, h)


def _nota(client, token, perfil):
    return client.post("/api/anotacoes", headers=bearer(token),
                       json={"alvoTipo": "perfil", "alvoId": perfil["id"], "texto": "x"})


def test_61a_chamada_no_minuto(client, base, monkeypatch):
    h, _ = base
    monkeypatch.setattr(limites, "_agora", lambda: 1_800_000_010.0)  # 10 s dentro do minuto
    _, token = criar_cliente(client, h, "A", "leitura")
    for _ in range(60):
        assert client.get("/api/perfis", headers=bearer(token)).status_code == 200
    r = client.get("/api/perfis", headers=bearer(token))
    assert r.status_code == 429 and r.json()["error"]["code"] == "mcp_limite"
    assert r.headers["retry-after"] == "50" and r.json()["error"]["details"] == {
        "retryAfterS": 50}
    assert "tente de novo em 50 s" in r.json()["error"]["message"]
    # outro cliente não é afetado
    _, outro = criar_cliente(client, h, "B", "leitura")
    assert client.get("/api/perfis", headers=bearer(outro)).status_code == 200


def test_escritas_do_dia_viram_a_meia_noite_de_brasilia(client, base, monkeypatch):
    h, perfil = base
    tz = ZoneInfo("America/Sao_Paulo")
    agora = datetime(2026, 10, 5, 23, 59, 0, tzinfo=tz).timestamp()
    monkeypatch.setattr(limites, "_agora", lambda: agora)
    _, token = criar_cliente(client, h, "A", "propostas", limiteEscritasDia=2)
    assert _nota(client, token, perfil).status_code == 201
    assert _nota(client, token, perfil).status_code == 201
    r = _nota(client, token, perfil)
    assert r.status_code == 429 and r.json()["error"]["details"]["retryAfterS"] == 60
    assert client.get("/api/perfis", headers=bearer(token)).status_code == 200  # leitura segue
    monkeypatch.setattr(limites, "_agora", lambda: agora + 120)  # 00:01 do dia seguinte
    assert _nota(client, token, perfil).status_code == 201


def test_zero_escritas_bloqueia_mesmo_com_propostas(client, base):
    h, perfil = base
    _, token = criar_cliente(client, h, "A", "propostas", limiteEscritasDia=0)
    assert _nota(client, token, perfil).status_code == 429


def test_limite_ajustado_vale_na_seguinte(client, base, monkeypatch):
    h, _ = base
    monkeypatch.setattr(limites, "_agora", lambda: 1_800_000_010.0)
    cliente, token = criar_cliente(client, h, "A", "leitura")
    for _ in range(3):
        client.get("/api/perfis", headers=bearer(token))
    r = client.patch(f"/api/mcp/clientes/{cliente['id']}", headers=h,
                     json={"version": cliente["version"], "limitePorMinuto": 3})
    assert r.status_code == 200
    assert client.get("/api/perfis", headers=bearer(token)).status_code == 429
    lista = client.get("/api/mcp/clientes", headers=h).json()["clientes"]
    assert lista[0]["noLimite"] is True


def test_redis_fora_do_ar_nega(client, base, monkeypatch):
    h, _ = base
    _, token = criar_cliente(client, h, "A", "leitura")

    class _Quebrado:
        def pipeline(self, **_):
            raise redis.ConnectionError("fora")

    monkeypatch.setattr(limites, "get_redis", lambda: _Quebrado())
    r = client.get("/api/perfis", headers=bearer(token))
    assert r.status_code == 503 and r.json()["error"]["code"] == "mcp_indisponivel"
