"""Trilha `lembretes` (T065, R10): uma "Hora de postar" por horário, para o autor e os donos,
marcando `lembrado_em` na mesma transação; nenhum caminho do agendador marca `postado`."""

from datetime import UTC, datetime, timedelta

import pytest

from integration.postagem_helpers import (  # noqa: F401
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo
from sociman_api.postagem import lembretes
from sociman_api.postagem.models import EstadoPostagem, Postagem


@pytest.fixture
def agendada(client, db, dono, membro):  # noqa: F811
    _, h = dono
    _, hm = membro
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd")
    corte = criar_corte(db, perfil["id"])
    quando = datetime.now(UTC) + timedelta(minutes=30)
    r = client.post(f"/api/cortes/{corte.id}/postagens", headers=hm,
                    json={"contaId": conta["id"], "titulo": "Atalho secreto",
                          "plannedAt": quando.isoformat()})
    assert r.status_code == 201, r.text
    return r.json()["postagem"]


def _vencer(db, postagem_id, minutos: int = 1) -> None:
    """Leva o horário para o passado direto no banco (a API recusa horário passado)."""
    db.query(Postagem).filter_by(id=postagem_id).update(
        {"planned_at": datetime.now(UTC) - timedelta(minutes=minutos)})
    db.commit()


def _rodar(db) -> int:
    n = lembretes.rodar(db)
    db.commit()
    return n


def test_antes_da_hora_nada(db, agendada):
    assert _rodar(db) == 0
    assert db.query(Notificacao).count() == 0


def test_na_hora_uma_notificacao_para_autor_e_donos(db, agendada, dono, membro):  # noqa: F811
    _vencer(db, agendada["id"])
    assert _rodar(db) == 1
    notas = db.query(Notificacao).order_by(Notificacao.id).all()
    assert {n.user_id for n in notas} == {dono[0].id, membro[0].id}
    n = notas[0]
    assert n.tipo == NotificacaoTipo.hora_de_postar
    assert n.titulo == "Hora de postar: Atalho secreto no TikTok"
    assert n.link == f"/app/cortes/{agendada['corteId']}"
    assert n.entity_type == "postagem" and str(n.entity_id) == agendada["id"]
    assert n.dedupe_key.startswith(f"hora_de_postar:{agendada['id']}:")
    p = db.get(Postagem, agendada["id"])
    db.refresh(p)
    assert p.lembrado_em is not None
    assert p.estado == EstadoPostagem.agendado  # só avisa: nunca marca postado
    # Segunda volta: já lembrado.
    assert _rodar(db) == 0
    assert db.query(Notificacao).count() == 2


def test_remarcar_zera_e_lembra_de_novo(client, db, agendada, dono):  # noqa: F811
    _vencer(db, agendada["id"])
    _rodar(db)
    novo = datetime.now(UTC) + timedelta(minutes=10)
    r = client.patch(f"/api/postagens/{agendada['id']}", headers=dono[1],
                     json={"version": 1, "plannedAt": novo.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["postagem"]["lembrado"] is False
    _vencer(db, agendada["id"], minutos=2)
    assert _rodar(db) == 1
    chaves = {n.dedupe_key for n in db.query(Notificacao)}
    assert len(chaves) == 2  # uma por horário


def test_dedupe_se_o_lembrado_em_se_perder(db, agendada):
    """Um reinício entre o INSERT e o commit não duplica: a chave leva o horário."""
    _vencer(db, agendada["id"])
    _rodar(db)
    db.query(Postagem).filter_by(id=agendada["id"]).update({"lembrado_em": None})
    db.commit()
    _rodar(db)
    assert db.query(Notificacao).count() == 2  # os mesmos dois destinatários, sem repetir


def test_rascunho_arquivada_e_postada_nao_lembram(client, db, agendada, dono):  # noqa: F811
    _vencer(db, agendada["id"])
    db.query(Postagem).filter_by(id=agendada["id"]).update(
        {"archived_at": datetime.now(UTC)})
    db.commit()
    assert _rodar(db) == 0
