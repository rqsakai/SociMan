"""T049 (spec 024, US7, FR-025): busca única nas propostas (`q` em `GET /api/anotacoes`)."""

import pytest

from integration.postagem_helpers import criar_perfil, dono  # noqa: F401


@pytest.fixture
def base(client, dono):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    for texto in ("Trocar a Legenda do vídeo", "Gancho mais curto", "Revisar ÁUDIO e legenda"):
        r = client.post("/api/anotacoes", headers=h,
                        json={"alvoTipo": "perfil", "alvoId": perfil["id"], "texto": texto})
        assert r.status_code == 201
    return h


def _textos(client, h, **params):
    r = client.get("/api/anotacoes", headers=h, params=params)
    assert r.status_code == 200, r.text
    return {a["texto"] for a in r.json()["anotacoes"]}


def test_q_acha_por_trecho_sem_acento_e_sem_caixa(client, base):
    assert _textos(client, base, q="LEGENDA") == {"Trocar a Legenda do vídeo",
                                                  "Revisar ÁUDIO e legenda"}
    assert _textos(client, base, q="audio") == {"Revisar ÁUDIO e legenda"}
    assert _textos(client, base, q="vídeo") == {"Trocar a Legenda do vídeo"}
    assert _textos(client, base, q="VIDEO") == {"Trocar a Legenda do vídeo"}
    assert _textos(client, base, q="nada disso") == set()


def test_q_escapa_curingas(client, base):
    assert _textos(client, base, q="%") == set()
    assert _textos(client, base, q="_") == set()


@pytest.mark.parametrize("q", ["", "   "])
def test_q_vazio_igual_a_hoje(client, base, q):
    todos = _textos(client, base)
    assert len(todos) == 3
    assert _textos(client, base, q=q) == todos


def test_q_longo_recusado(client, base):
    # o handler do app converte o 422 do FastAPI em 400 `validation_error`
    assert client.get("/api/anotacoes", headers=base, params={"q": "x" * 100}).status_code == 200
    r = client.get("/api/anotacoes", headers=base, params={"q": "x" * 101})
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"
