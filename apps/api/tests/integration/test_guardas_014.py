"""Guardas da spec 014 (plan, "Guardas" 3, 4 e 8): princípio I (nenhum modo automático nem
estado da 015 passa pela API nem pelo banco) e princípio VII (uma versão por destino afetado,
com autor; reversão, aprovação e recusa só pelo dono)."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from integration.postagem_helpers import (  # noqa: F401
    acao,
    add_destino,
    agendar,
    aprovado,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion
from sociman_api.postagem.models import Postagem

SP = ZoneInfo("America/Sao_Paulo")
AUTOMATICOS = ("criar_rascunho", "publicar", "rascunho_e_publicar")


def _amanha(hora: int = 19, dias: int = 1) -> datetime:
    return (datetime.now(SP) + timedelta(days=dias)).replace(hour=hora, minute=0, second=0,
                                                            microsecond=0)


@pytest.fixture
def c(client, db, dono, membro):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    return {"h": h, "hm": membro[1], "dono": dono[0], "membro": membro[0], "perfil": perfil,
            "conta": criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd"),
            "corte": criar_corte(db, perfil["id"])}


def _snapshot(db) -> list[tuple]:
    db.expire_all()
    rows = db.execute(select(Postagem.id, Postagem.version, Postagem.estado, Postagem.modo,
                             Postagem.planned_at).order_by(Postagem.id)).all()
    return [tuple(r) for r in rows]


def _n_versoes(db) -> int:
    return db.scalar(select(func.count()).select_from(EntityVersion)
                     .where(EntityVersion.entity_type == "postagem")) or 0


# ---- guarda 3: a API recusa todo modo automático ----

@pytest.mark.parametrize("modo", AUTOMATICOS)
def test_guarda3_api_recusa_modos_automaticos(client, db, c, modo):
    d = agendar(client, c["h"], c["corte"].id, c["conta"]["id"], _amanha()).json()["destino"]
    antes, versoes = _snapshot(db), _n_versoes(db)
    outro = criar_corte(db, c["perfil"]["id"])

    r = agendar(client, c["h"], outro.id, c["conta"]["id"], _amanha(20), modo=modo)
    assert r.status_code == 409 and r.json()["error"]["code"] == "modo_indisponivel"
    r = client.patch(f"/api/destinos/{d['id']}/agendamento", headers=c["h"],
                     json={"version": d["version"], "modo": modo})
    assert r.status_code == 409 and r.json()["error"]["code"] == "modo_indisponivel"
    body = {"contaId": c["conta"]["id"], "conteudoIds": [str(outro.id)],
            "inicio": _amanha(dias=2).date().isoformat(), "horarios": ["19:00"], "modo": modo}
    r = client.post("/api/agendamentos/sequencia/previa", headers=c["h"], json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "modo_indisponivel"
    r = client.post("/api/agendamentos/sequencia", headers=c["h"],
                    json={**body, "esperado": []})
    assert r.status_code == 409 and r.json()["error"]["code"] == "modo_indisponivel"

    assert _snapshot(db) == antes and _n_versoes(db) == versoes


# ---- guarda 4: os CHECKs do banco ----

# Spec 015: `criar_rascunho` e `publicar` passam a existir no banco (em `aprovado`, sem
# agendamento); `rascunho_e_publicar` continua proibido, e os estados de execução continuam
# proibidos num destino `lembrete` (`ck_postagens_execucao`).
@pytest.mark.parametrize(("coluna", "valor"), [
    ("modo", "rascunho_e_publicar"),
    ("estado", "rascunho_criado"), ("estado", "publicado"), ("estado", "falhou"),
    ("estado", "enviando"),
])
def test_guarda4_banco_recusa(client, db, c, coluna, valor):
    d = aprovado(client, c["h"], c["corte"].id, c["conta"]["id"])
    with get_engine().connect() as conn, pytest.raises(IntegrityError) as exc:
        conn.execute(text(f"UPDATE postagens SET {coluna} = :v WHERE id = :id"),
                     {"v": valor, "id": d["id"]})
    assert "ck_postagens_" in str(exc.value)
    livre = criar_corte(db, c["perfil"]["id"])  # sem destino: o índice único não interfere
    with get_engine().connect() as conn, pytest.raises(IntegrityError) as exc:
        conn.execute(text(
            f"INSERT INTO postagens (id, conteudo_id, conta_id, {coluna}, aprovado_em) "
            "VALUES (:id, :c, :k, :v, now())"),
            {"id": str(uuid.uuid4()), "c": str(livre.id), "k": c["conta"]["id"], "v": valor})
    assert "ck_postagens_" in str(exc.value)


def test_guarda4_automatico_agendado_exige_decisao(client, db, c):
    """015 (`ck_postagens_auto_decisao`): modo automático agendado sem `agendado_por`."""
    d = aprovado(client, c["h"], c["corte"].id, c["conta"]["id"])
    with get_engine().connect() as conn, pytest.raises(IntegrityError) as exc:
        conn.execute(text("UPDATE postagens SET modo = 'criar_rascunho', estado = 'agendado', "
                          "planned_at = now() WHERE id = :id"), {"id": d["id"]})
    assert "ck_postagens_auto_decisao" in str(exc.value)


def test_guarda4_antecedencia_so_com_rascunho_e_publicar(client, db, c):
    d = aprovado(client, c["h"], c["corte"].id, c["conta"]["id"])
    with get_engine().connect() as conn, pytest.raises(IntegrityError):
        conn.execute(text("UPDATE postagens SET antecedencia_min = 10 WHERE id = :id"),
                     {"id": d["id"]})


# ---- guarda 8: uma versão por destino afetado, com autor; permissões ----

def _versoes(db, destino_id) -> list[EntityVersion]:
    db.expire_all()
    return list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "postagem",
        EntityVersion.entity_id == uuid.UUID(str(destino_id))).order_by(EntityVersion.version)))


def _uma_versao(db, destino_id, antes: int, autor, acao_esperada: str) -> None:
    vs = _versoes(db, destino_id)
    assert len(vs) == antes + 1, [v.details for v in vs]
    assert vs[-1].actor_user_id == autor.id and vs[-1].actor_kind == "user"
    assert vs[-1].details.get("acao") == acao_esperada


def test_guarda8_cada_acao_uma_versao(client, db, c):
    h, hm = c["h"], c["hm"]
    d = add_destino(client, hm, c["corte"].id, c["conta"]["id"])
    n = len(_versoes(db, d["id"]))
    d = acao(client, hm, d, "pedir-aprovacao").json()["destino"]
    _uma_versao(db, d["id"], n, c["membro"], "aprovacao_pedida")
    d = acao(client, h, d, "recusar", motivo="não").json()["destino"]
    _uma_versao(db, d["id"], n + 1, c["dono"], "recusado")
    d = acao(client, h, d, "aprovar").json()["destino"]
    _uma_versao(db, d["id"], n + 2, c["dono"], "aprovado")
    d = agendar(client, hm, c["corte"].id, c["conta"]["id"], _amanha()).json()["destino"]
    _uma_versao(db, d["id"], n + 3, c["membro"], "agendado")
    d = client.patch(f"/api/destinos/{d['id']}/agendamento", headers=hm, json={
        "version": d["version"], "plannedAt": _amanha(20).isoformat()}).json()["destino"]
    _uma_versao(db, d["id"], n + 4, c["membro"], "reagendado")
    d = acao(client, hm, d, "agendamento/cancelar").json()["destino"]
    _uma_versao(db, d["id"], n + 5, c["membro"], "agendamento_cancelado")
    d = agendar(client, hm, c["corte"].id, c["conta"]["id"], _amanha()).json()["destino"]
    corte = client.get(f"/api/cortes/{c['corte'].id}", headers=h).json()["corte"]
    r = client.post(f"/api/cortes/{c['corte'].id}/archive", headers=h,
                    json={"version": corte["version"]})
    assert r.status_code == 200, r.text
    _uma_versao(db, d["id"], n + 7, c["dono"], "cancelado_por_arquivo")


def test_guarda8_lote_uma_versao_por_destino(client, db, c):
    outro = criar_corte(db, c["perfil"]["id"])
    a = aprovado(client, c["h"], c["corte"].id, c["conta"]["id"])
    b = add_destino(client, c["h"], outro.id, c["conta"]["id"])
    na, nb = len(_versoes(db, a["id"])), len(_versoes(db, b["id"]))
    r = client.post("/api/destinos/lote/aprovar", headers=c["h"], json={
        "contaId": c["conta"]["id"], "conteudoIds": [str(c["corte"].id), str(outro.id)]})
    assert r.status_code == 200, r.text
    assert len(_versoes(db, a["id"])) == na  # já aprovado: nada muda
    _uma_versao(db, b["id"], nb, c["dono"], "lote")


def test_guarda8_membro_403(client, c):
    d = add_destino(client, c["hm"], c["corte"].id, c["conta"]["id"], titulo="a")
    assert acao(client, c["hm"], d, "aprovar").status_code == 403
    assert acao(client, c["hm"], d, "recusar", motivo="x").status_code == 403
    r = client.post("/api/destinos/lote/aprovar", headers=c["hm"], json={
        "contaId": c["conta"]["id"], "conteudoIds": [str(c["corte"].id)]})
    assert r.status_code == 403
    r = client.post(f"/api/destinos/{d['id']}/revert", headers=c["hm"],
                    json={"version": d["version"], "toVersion": 1})
    assert r.status_code == 403
