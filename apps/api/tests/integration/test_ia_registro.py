"""Registro e custo das chamadas (spec 008, T039; US3, R7, R8): filtros em APP_TZ, cursor,
resumo do mês, só o dono, e cada erro gravado com a mensagem certa (sem vazar a chave)."""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fakes.anthropic_fake import CHAVE_TESTE, anthropic_fake, mensagem  # noqa: F401
from sqlalchemy import select

from sociman_api.ia.cliente import get_ia_client
from sociman_api.ia.models import IaChamada, IaDesfecho
from sociman_api.main import app

PW = "senha-forte-123"


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


def _perfil(client, h, slug):
    r = client.post("/api/perfis", headers=h, json={"name": slug.title(), "slug": slug})
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _linha(db, perfil_id, quando: datetime, tipo="perfil.bio", desfecho=IaDesfecho.sem_acao,
           custo="0.010000", **extra) -> IaChamada:
    row = IaChamada(
        tipo_campo=tipo, perfil_id=uuid.UUID(perfil_id), entity_type="perfil",
        entity_id=uuid.UUID(perfil_id), model="claude-sonnet-5-5", prompt_version="ia/1",
        duration_ms=100, desfecho=desfecho, custo_usd=Decimal(custo) if custo else None,
        proposta={"texto": "x"}, created_at=quando,
        erro_code="timeout" if desfecho == IaDesfecho.erro else None, **extra)
    db.add(row)
    db.commit()
    return row


def _ids(r) -> list[str]:
    assert r.status_code == 200, r.text
    return [c["id"] for c in r.json()["items"]]


def test_filtros_cursor_e_linhas_da_006(client, db, dono):
    h = dono[1]
    a = _perfil(client, h, "perfil-a")
    b = _perfil(client, h, "perfil-b")
    # 02:30 UTC de 1/set = 23:30 de 31/ago em São Paulo (a virada do dia é em APP_TZ).
    velha = _linha(db, a["id"], datetime(2026, 9, 1, 2, 30, tzinfo=UTC))
    dia1 = _linha(db, a["id"], datetime(2026, 9, 1, 12, 0, tzinfo=UTC), tipo="asset.nome",
                  desfecho=IaDesfecho.aplicada)
    sessao = uuid.uuid4()
    dia2 = _linha(db, b["id"], datetime(2026, 9, 2, 12, 0, tzinfo=UTC), sessao_id=sessao)
    da006 = _linha(db, b["id"], datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
                   tipo="postagem.textos")  # como as linhas migradas da 006
    url = "/api/ia/chamadas"
    todos = [str(r.id) for r in (da006, dia2, dia1, velha)]
    assert _ids(client.get(url, headers=h)) == todos
    assert _ids(client.get(url, headers=h, params={"perfilId": a["id"]})) == \
        [str(dia1.id), str(velha.id)]
    assert _ids(client.get(url, headers=h, params={"tipoCampo": "postagem.textos"})) == \
        [str(da006.id)]
    assert _ids(client.get(url, headers=h, params={"desfecho": "aplicada"})) == [str(dia1.id)]
    assert _ids(client.get(url, headers=h, params={"de": "2026-09-01", "ate": "2026-09-01"})) \
        == [str(dia1.id)]
    assert _ids(client.get(url, headers=h, params={"ate": "2026-08-31"})) == [str(velha.id)]
    assert _ids(client.get(url, headers=h, params={"sessaoId": str(sessao)})) == [str(dia2.id)]

    p1 = client.get(url, headers=h, params={"limit": 3}).json()
    assert [c["id"] for c in p1["items"]] == todos[:3] and p1["nextCursor"]
    p2 = client.get(url, headers=h, params={"limit": 3, "cursor": p1["nextCursor"]}).json()
    assert [c["id"] for c in p2["items"]] == todos[3:] and p2["nextCursor"] is None
    assert client.get(url, headers=h, params={"limit": 101}).status_code == 400
    assert client.get(url, headers=h, params={"cursor": "lixo"}).status_code == 400

    r = client.get(f"{url}/{dia1.id}", headers=h)
    assert r.status_code == 200
    ch = r.json()["chamada"]
    assert ch["perfil"]["slug"] == "perfil-a" and ch["custoUsd"] == 0.01
    assert client.get(f"{url}/{uuid.uuid4()}", headers=h).status_code == 404


def test_resumo_do_mes(client, db, dono):
    h = dono[1]
    a = _perfil(client, h, "perfil-a")
    b = _perfil(client, h, "perfil-b")
    _linha(db, a["id"], datetime(2026, 9, 1, 2, 30, tzinfo=UTC))  # agosto em São Paulo
    _linha(db, a["id"], datetime(2026, 9, 5, tzinfo=UTC), desfecho=IaDesfecho.aplicada)
    _linha(db, a["id"], datetime(2026, 9, 6, tzinfo=UTC), tipo="asset.nome",
           desfecho=IaDesfecho.editada, custo="0.020000")
    _linha(db, b["id"], datetime(2026, 9, 7, tzinfo=UTC), desfecho=IaDesfecho.descartada)
    _linha(db, b["id"], datetime(2026, 9, 8, tzinfo=UTC), desfecho=IaDesfecho.erro, custo=None)
    r = client.get("/api/ia/resumo", headers=h, params={"mes": "2026-09"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["mes"], s["de"], s["ate"]) == ("2026-09", "2026-09-01", "2026-09-30")
    assert (s["chamadas"], s["erros"], s["aplicadas"], s["editadas"], s["descartadas"]) == \
        (4, 1, 1, 1, 1)
    assert s["custoUsd"] == pytest.approx(0.04) and s["precosVersao"] == "2026-09"
    assert s["porTipo"][0] == {"tipoCampo": "asset.nome", "chamadas": 1, "custoUsd": 0.02}
    por_perfil = {p["perfil"]["slug"]: (p["chamadas"], p["custoUsd"]) for p in s["porPerfil"]}
    assert por_perfil == {"perfil-a": (2, pytest.approx(0.03)),
                          "perfil-b": (2, pytest.approx(0.01))}
    ago = client.get("/api/ia/resumo", headers=h, params={"mes": "2026-08"}).json()
    assert ago["chamadas"] == 1
    assert client.get("/api/ia/resumo", headers=h).status_code == 200  # mês corrente
    assert client.get("/api/ia/resumo", headers=h, params={"mes": "2026-13"}).status_code == 400


def test_membro_403_no_registro_e_no_resumo(client, db, dono, membro):
    a = _perfil(client, dono[1], "perfil-a")
    row = _linha(db, a["id"], datetime(2026, 9, 5, tzinfo=UTC))
    h = membro[1]
    for url in ("/api/ia/chamadas", f"/api/ia/chamadas/{row.id}", "/api/ia/resumo"):
        assert client.get(url, headers=h).status_code == 403


def _gerar(client, h, perfil):
    return client.post("/api/ia/gerar", headers=h, json={
        "tipoCampo": "perfil.bio", "perfilId": perfil["id"],
        "alvo": {"entityType": "perfil", "entityId": perfil["id"]},
        "sessaoId": str(uuid.uuid4())})


@pytest.mark.parametrize(("itens", "status", "code", "erro", "trecho"), [
    (["timeout"], 504, "ia_timeout", "timeout", "demorou demais"),
    (["recusa"], 502, "ia_recusa", "refusal", "escreva à mão"),
    ([mensagem({"x": 1}), mensagem({"y": 1})], 502, "ia_invalida", "invalid", "fora do formato"),
    ([(500, "erro_api")], 502, "claude_error", "api_error", "não respondeu"),
    ([(401, {"type": "error", "error": {"type": "authentication_error", "message": "x"}})],
     502, "claude_error", "api_error", "ANTHROPIC_API_KEY"),
    ([(429, {"type": "error", "error": {"type": "rate_limit_error", "message": "x"}})],
     502, "claude_error", "api_error", "muitas chamadas"),
])
def test_erros_gravados(client, db, dono, anthropic_fake,  # noqa: F811
                        itens, status, code, erro, trecho):
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    h = dono[1]
    perfil = _perfil(client, h, "perfil-e")
    anthropic_fake.responder(*itens)
    r = _gerar(client, h, perfil)
    assert r.status_code == status, r.text
    body = r.json()["error"]
    assert body["code"] == code and trecho in body["message"]
    assert CHAVE_TESTE not in r.text
    [row] = db.scalars(select(IaChamada)).all()  # commitado antes do erro
    assert row.erro_code == erro and row.desfecho == IaDesfecho.erro and row.proposta is None
    lista = client.get("/api/ia/chamadas", headers=h)
    assert lista.json()["items"][0]["erroCode"] == erro
    assert CHAVE_TESTE not in lista.text
    assert CHAVE_TESTE not in json.dumps({c.name: str(getattr(row, c.name))
                                          for c in IaChamada.__table__.columns})


def test_sem_chave_grava_unconfigured(client, db, dono):
    app.dependency_overrides[get_ia_client] = lambda: None
    h = dono[1]
    perfil = _perfil(client, h, "perfil-s")
    r = _gerar(client, h, perfil)
    assert r.status_code == 503 and r.json()["error"]["code"] == "claude_unconfigured"
    [row] = db.scalars(select(IaChamada)).all()
    assert row.erro_code == "unconfigured" and row.desfecho == IaDesfecho.erro
