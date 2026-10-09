"""Trilha `lembretes` (T065 da 006, R10; spec 014, R8): uma "Hora de postar" por horário, para
o autor e os donos, marcando `lembrado_em` na mesma transação. Só destinos no modo `lembrete`
e com a conta em condição; nenhum caminho do agendador muda `estado` nem `version`."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from integration.postagem_helpers import (  # noqa: F401
    agendar,
    aprovado,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo
from sociman_api.postagem import lembretes
from sociman_api.postagem.models import DestinoEstado, Postagem


@pytest.fixture
def cenario(client, db, dono, membro):  # noqa: F811
    _, h = dono
    _, hm = membro
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd")
    corte = criar_corte(db, perfil["id"])
    return {"h": h, "hm": hm, "conta": conta, "corte": corte}


@pytest.fixture
def agendada(client, cenario):
    """Aprovado pelo dono e agendado pelo membro (o autor do agendamento)."""
    c = cenario
    aprovado(client, c["h"], c["corte"].id, c["conta"]["id"])
    quando = datetime.now(UTC) + timedelta(minutes=30)
    r = agendar(client, c["hm"], c["corte"].id, c["conta"]["id"], quando,
                textos={"titulo": "Atalho secreto"})
    assert r.status_code == 200, r.text
    return r.json()["destino"]


def _vencer(db, destino_id, minutos: int = 1) -> None:
    """Leva o horário para o passado direto no banco (a API recusa horário passado)."""
    db.query(Postagem).filter_by(id=destino_id).update(
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
    antes = db.scalar(select(Postagem.version).where(Postagem.id == agendada["id"]))
    assert _rodar(db) == 1
    notas = db.query(Notificacao).order_by(Notificacao.id).all()
    assert {n.user_id for n in notas} == {dono[0].id, membro[0].id}
    n = notas[0]
    assert n.tipo == NotificacaoTipo.hora_de_postar
    assert n.titulo == "Hora de postar: Atalho secreto no TikTok"
    assert n.link == (f"/app/conteudos/{agendada['conteudoId']}"
                      f"?conta={agendada['conta']['id']}")
    assert n.entity_type == "postagem" and str(n.entity_id) == agendada["id"]
    assert n.dedupe_key.startswith(f"hora_de_postar:{agendada['id']}:")
    db.expire_all()
    p = db.get(Postagem, agendada["id"])
    assert p.lembrado_em is not None
    # Guarda 6 (parte 2): só avisa, nunca muda estado nem versão.
    assert p.estado == DestinoEstado.agendado and p.version == antes
    assert _rodar(db) == 0
    assert db.query(Notificacao).count() == 2


def test_titulo_do_conteudo_quando_o_destino_nao_tem(client, db, cenario):
    c = cenario
    aprovado(client, c["h"], c["corte"].id, c["conta"]["id"])
    d = agendar(client, c["h"], c["corte"].id, c["conta"]["id"],
                datetime.now(UTC) + timedelta(minutes=30)).json()["destino"]
    _vencer(db, d["id"])
    assert _rodar(db) == 1
    n = db.query(Notificacao).first()
    assert n.titulo == "Hora de postar: Você usa isso? no TikTok"  # o gancho vira o título


def test_remarcar_zera_e_lembra_de_novo(client, db, agendada, dono):  # noqa: F811
    _vencer(db, agendada["id"])
    _rodar(db)
    d = client.get(f"/api/destinos/{agendada['id']}", headers=dono[1]).json()["destino"]
    novo = datetime.now(UTC) + timedelta(minutes=10)
    r = client.patch(f"/api/destinos/{agendada['id']}/agendamento", headers=dono[1],
                     json={"version": d["version"], "plannedAt": novo.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["lembrado"] is False
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


def test_arquivado_nao_lembra(db, agendada):
    _vencer(db, agendada["id"])
    db.query(Postagem).filter_by(id=agendada["id"]).update(
        {"archived_at": datetime.now(UTC)})
    db.commit()
    assert _rodar(db) == 0


@pytest.mark.parametrize("status", ["pausada", "encerrada"])
def test_conta_em_atencao_nao_lembra(client, db, agendada, cenario, status):
    c = cenario
    r = client.patch(f"/api/contas/{c['conta']['id']}", headers=c["h"],
                     json={"version": c["conta"]["version"], "status": status})
    assert r.status_code == 200, r.text
    _vencer(db, agendada["id"])
    assert _rodar(db) == 0


def test_conta_arquivada_nao_lembra(client, db, agendada, cenario):
    c = cenario
    r = client.post(f"/api/contas/{c['conta']['id']}/archive", headers=c["h"],
                    json={"version": c["conta"]["version"]})
    assert r.status_code == 200, r.text
    _vencer(db, agendada["id"])
    assert _rodar(db) == 0
