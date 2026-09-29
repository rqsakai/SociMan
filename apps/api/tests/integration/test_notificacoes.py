"""Notificações (spec 006, R11, T016): dedupe, destinatários, cursor, não lidas e isolamento."""

import pytest

from sociman_api.notificacoes import service
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo

PW = "senha-forte-123"


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


def _criar(db, user_ids, dedupe: str, titulo: str = "Envio pronto") -> int:
    n = service.criar(db, NotificacaoTipo.envio_pronto, titulo, "6 clipes", "/app/envios/x",
                      ("envio", None), dedupe, user_ids)
    db.commit()
    return n


def test_dedupe_uma_linha_por_usuario(db, dono):
    user, _ = dono
    assert _criar(db, [user.id], "envio_pronto:1") == 1
    assert _criar(db, [user.id], "envio_pronto:1") == 0
    assert db.query(Notificacao).count() == 1
    # Destinatário repetido na mesma chamada também vira uma linha só.
    assert _criar(db, [user.id, user.id], "envio_pronto:2") == 1


def test_destinatarios_autor_e_donos_sem_repetir(db, make_user):
    dono1 = make_user(role="dono")
    dono2 = make_user(role="dono")
    make_user(role="dono", active=False)
    membro = make_user(role="membro")
    assert service.destinatarios_padrao(db, membro.id) == [membro.id, dono1.id, dono2.id]
    assert service.destinatarios_padrao(db, dono2.id) == [dono2.id, dono1.id]
    assert service.destinatarios_padrao(db, None) == [dono1.id, dono2.id]


def test_listar_com_cursor_e_nao_lidas(client, db, dono):
    user, h = dono
    for i in range(3):
        _criar(db, [user.id], f"k{i}", titulo=f"n{i}")

    r = client.get("/api/notificacoes", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [n["titulo"] for n in body["items"]] == ["n2", "n1", "n0"]
    assert body["naoLidas"] == 3
    primeiro = body["items"][0]
    assert set(primeiro) == {"id", "tipo", "titulo", "corpo", "link", "createdAt", "lida"}
    assert primeiro["tipo"] == "envio_pronto" and primeiro["lida"] is False

    ids = sorted(n["id"] for n in body["items"])
    r = client.get("/api/notificacoes", params={"after": ids[0]}, headers=h)
    assert [n["titulo"] for n in r.json()["items"]] == ["n2", "n1"]

    r = client.get("/api/notificacoes", params={"limit": 1}, headers=h)
    assert [n["titulo"] for n in r.json()["items"]] == ["n2"]

    client.post("/api/notificacoes/lidas", json={"ids": [ids[2]]}, headers=h)
    r = client.get("/api/notificacoes", params={"naoLidas": "true"}, headers=h)
    assert [n["titulo"] for n in r.json()["items"]] == ["n1", "n0"]
    assert r.json()["naoLidas"] == 2


def test_marcar_lidas_por_ids_e_todas(client, db, dono):
    user, h = dono
    for i in range(3):
        _criar(db, [user.id], f"k{i}")
    ids = [n.id for n in db.query(Notificacao).order_by(Notificacao.id)]

    r = client.post("/api/notificacoes/lidas", json={"ids": ids[:2]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"naoLidas": 1}

    r = client.post("/api/notificacoes/lidas", json={"todas": True}, headers=h)
    assert r.json() == {"naoLidas": 0}
    db.expire_all()
    linhas = db.query(Notificacao).all()
    assert len(linhas) == 3, "marcar como lida nunca apaga"
    assert all(n.lida_em is not None for n in linhas)


@pytest.mark.parametrize("body", [{}, {"ids": [1], "todas": True}, {"todas": False},
                                  {"ids": [0]}, {"outra": 1}])
def test_marcar_lidas_corpo_invalido(client, dono, body):
    _, h = dono
    r = client.post("/api/notificacoes/lidas", json=body, headers=h)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


def test_isolamento_entre_usuarios(client, db, dono, membro):
    user_d, _ = dono
    user_m, h_m = membro
    _criar(db, [user_d.id], "so-do-dono", titulo="do dono")
    _criar(db, [user_m.id], "so-do-membro", titulo="do membro")
    id_do_dono = db.query(Notificacao).filter_by(user_id=user_d.id).one().id

    r = client.get("/api/notificacoes", headers=h_m)
    assert [n["titulo"] for n in r.json()["items"]] == ["do membro"]

    # O membro não marca a do dono como lida.
    r = client.post("/api/notificacoes/lidas", json={"ids": [id_do_dono]}, headers=h_m)
    assert r.json() == {"naoLidas": 1}
    db.expire_all()
    assert db.get(Notificacao, id_do_dono).lida_em is None


def test_exige_login(client):
    assert client.get("/api/notificacoes").status_code == 401
    assert client.post("/api/notificacoes/lidas", json={"todas": True}).status_code == 401
