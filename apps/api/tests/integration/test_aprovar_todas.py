"""Aprovar e desaprovar todas as contas do conteúdo (spec 018, US2):
`POST /api/conteudos/{id}/aprovar-todas` e `…/desaprovar-todas`. Só dono humano; cada destino
ganha a sua versão no histórico; nada é apagado nem publicado."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from integration import publicacao_helpers as ph
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
from sociman_api.auth.deps import Actor, current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.cortes.models import CorteStatus
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.postagem.models import DestinoEstado, Postagem

# Fixtures do apoio da 015 (o pytest as acha pelo nome no módulo).
app_tiktok = ph.app_tiktok
cena = ph.cena


@pytest.fixture
def c(client, db, dono, membro):  # noqa: F811
    _, h = dono
    _, hm = membro
    perfil = criar_perfil(client, h)
    return {
        "h": h, "hm": hm, "dono": dono[0], "perfil": perfil,
        "tiktok": criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd"),
        "youtube": criar_conta(client, h, perfil["id"], "youtube", "tavernanerdyt"),
        "instagram": criar_conta(client, h, perfil["id"], "instagram", "tavernanerdig"),
        "corte": criar_corte(db, perfil["id"]),
    }


def _err(r) -> str:
    return r.json()["error"]["code"]


def _todas(client, h, conteudo_id, acao_: str, **body):
    return client.post(f"/api/conteudos/{conteudo_id}/{acao_}", headers=h, json=body)


def _versoes(db, destino_id) -> list[EntityVersion]:
    db.expire_all()
    return list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "postagem",
        EntityVersion.entity_id == uuid.UUID(str(destino_id)),
    ).order_by(EntityVersion.version)))


def _estado(db, destino_id) -> DestinoEstado:
    db.expire_all()
    return db.get(Postagem, uuid.UUID(str(destino_id))).estado


def _postado(client, c, conta) -> dict:
    d = aprovado(client, c["h"], c["corte"].id, conta["id"])
    r = acao(client, c["h"], d, "postado", postedUrl="https://www.tiktok.com/@x/video/1")
    assert r.status_code == 200, r.text
    return r.json()["destino"]


# ---- aprovar todas ----

def test_dono_aprova_pendentes_e_pedidos_e_lista_os_outros(client, db, c):
    corte = c["corte"]
    pendente = add_destino(client, c["h"], corte.id, c["tiktok"]["id"])
    pedido = add_destino(client, c["h"], corte.id, c["youtube"]["id"])
    r = acao(client, c["hm"], pedido, "pedir-aprovacao")
    assert r.status_code == 200, r.text
    postado = _postado(client, c, c["instagram"])

    r = _todas(client, c["h"], corte.id, "aprovar-todas")
    assert r.status_code == 200, r.text
    out = r.json()
    assert {d["id"] for d in out["ok"]} == {pendente["id"], pedido["id"]}
    assert all(d["estado"] == "aprovado" and d["aprovacao"]["por"]["id"] == str(c["dono"].id)
               for d in out["ok"])
    assert [(i["destinoId"], i["code"]) for i in out["ignorados"]] == \
        [(postado["id"], "nao_elegivel")]
    assert out["ignorados"][0]["message"] == "Já foi marcado como postado"
    for d in (pendente, pedido):
        ultima = _versoes(db, d["id"])[-1]
        assert ultima.details == {"acao": "aprovado", "loteAcao": "aprovar_todas"}
        assert ultima.actor_kind == "user"
    assert len(_versoes(db, postado["id"])) == 3  # criado, aprovado, postado: sem versão nova

    # De novo: nada muda, todos voltam como ignorados.
    r = _todas(client, c["h"], corte.id, "aprovar-todas")
    assert r.status_code == 200 and r.json()["ok"] == []
    assert len(r.json()["ignorados"]) == 3


def test_aprovar_todas_conteudo_nao_pronto(client, db, c):
    corte = criar_corte(db, c["perfil"]["id"], status=CorteStatus.revisao)
    d = add_destino(client, c["h"], corte.id, c["tiktok"]["id"])
    r = _todas(client, c["h"], corte.id, "aprovar-todas")
    assert r.status_code == 409 and _err(r) == "conteudo_nao_pronto"
    assert _estado(db, d["id"]) == DestinoEstado.pendente


def test_conteudo_inexistente_404(client, c):
    for rota in ("aprovar-todas", "desaprovar-todas"):
        assert _todas(client, c["h"], uuid.uuid4(), rota).status_code == 404


def test_membro_e_mcp_recebem_403(client, db, c):
    corte = c["corte"]
    d = add_destino(client, c["h"], corte.id, c["tiktok"]["id"])
    for rota in ("aprovar-todas", "desaprovar-todas"):
        r = _todas(client, c["hm"], corte.id, rota)
        assert r.status_code == 403 and _err(r) == "somente_dono"
    app.dependency_overrides[current_user] = lambda: Actor(
        kind="mcp_client", user_id=c["dono"].id, user=c["dono"])
    try:
        for rota in ("aprovar-todas", "desaprovar-todas"):
            r = _todas(client, {"Authorization": "Bearer qualquer"}, corte.id, rota)
            assert r.status_code == 403 and _err(r) == "somente_humano"
    finally:
        app.dependency_overrides.pop(current_user, None)
    db.expire_all()
    assert db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).first().actor_kind == "mcp_client"
    assert _estado(db, d["id"]) == DestinoEstado.pendente
    assert len(_versoes(db, d["id"])) == 1


# ---- desaprovar todas ----

def test_desaprovar_exige_confirmacao_com_agendados_e_cancela(client, db, c):
    corte = c["corte"]
    ok = aprovado(client, c["h"], corte.id, c["tiktok"]["id"])
    r = agendar(client, c["h"], corte.id, c["youtube"]["id"],
                datetime.now(UTC) + timedelta(days=1))
    assert r.status_code == 201, r.text
    agendado = r.json()["destino"]
    assert agendado["estado"] == "agendado"
    postado = _postado(client, c, c["instagram"])

    r = _todas(client, c["h"], corte.id, "desaprovar-todas")
    assert r.status_code == 409 and _err(r) == "confirmacao_necessaria"
    assert r.json()["error"]["details"]["destinoIds"] == [agendado["id"]]
    assert _estado(db, ok["id"]) == DestinoEstado.aprovado
    assert _estado(db, agendado["id"]) == DestinoEstado.agendado

    r = _todas(client, c["h"], corte.id, "desaprovar-todas", confirmo=True)
    assert r.status_code == 200, r.text
    out = r.json()
    por_id = {d["id"]: d for d in out["ok"]}
    assert set(por_id) == {ok["id"], agendado["id"]}
    for d in por_id.values():
        assert d["estado"] == "pendente" and d["aprovacao"] is None and d["plannedAt"] is None
        assert d["modo"] == "lembrete"
    assert [i["destinoId"] for i in out["ignorados"]] == [postado["id"]]
    assert _estado(db, postado["id"]) == DestinoEstado.postado

    v_ok = _versoes(db, ok["id"])[-1]
    assert v_ok.details == {"acao": "desaprovado", "agendamentoCancelado": False}
    v_ag = _versoes(db, agendado["id"])[-1]
    assert v_ag.details == {"acao": "desaprovado", "agendamentoCancelado": True}
    assert v_ag.before["estado"] == "agendado" and v_ag.after["estado"] == "pendente"
    assert v_ag.before["planned_at"] is not None and v_ag.after["planned_at"] is None

    # Nada foi apagado: os destinos seguem ativos e podem ser aprovados de novo.
    r = _todas(client, c["h"], corte.id, "aprovar-todas")
    assert r.status_code == 200 and len(r.json()["ok"]) == 2


def test_desaprovar_sem_agendados_nao_pede_confirmacao(client, db, c):
    corte = c["corte"]
    d = aprovado(client, c["h"], corte.id, c["tiktok"]["id"])
    pendente = add_destino(client, c["h"], corte.id, c["youtube"]["id"])
    r = _todas(client, c["h"], corte.id, "desaprovar-todas")
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["ok"]] == [d["id"]]
    assert [(i["destinoId"], i["message"]) for i in r.json()["ignorados"]] == \
        [(pendente["id"], "Ainda não está aprovado")]


def test_desaprovar_cancela_agendamento_automatico(cena):
    d = cena.agendado()
    assert d["modo"] == "criar_rascunho"
    r = _todas(cena.client, cena.h, d["conteudoId"], "desaprovar-todas", confirmo=True)
    assert r.status_code == 200, r.text
    destino = cena.destino(d["id"])
    assert destino.estado == DestinoEstado.pendente and destino.planned_at is None
    assert destino.envio_snapshot is None and destino.aprovado_por is None
    cena.rodar(2)
    assert cena.destino(d["id"]).estado == DestinoEstado.pendente
    assert cena.fake.inits == 0


def test_desaprovar_com_envio_em_andamento_409(cena):
    d = cena.agendado()
    # Outro conteúdo: não entra.
    outro = cena.agendar(cena.corte(), datetime.now(UTC) + timedelta(days=3)).json()
    outro = outro["destino"]
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE postagens SET estado = 'enviando' WHERE id = :id"),
                     {"id": d["id"]})
    r = _todas(cena.client, cena.h, d["conteudoId"], "desaprovar-todas", confirmo=True)
    assert r.status_code == 409 and r.json()["error"]["code"] == "envio_em_andamento"
    assert cena.destino(d["id"]).estado == DestinoEstado.enviando
    assert cena.destino(outro["id"]).estado == DestinoEstado.agendado
