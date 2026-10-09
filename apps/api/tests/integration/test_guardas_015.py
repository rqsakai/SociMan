"""Guardas do princípio I na API e na execução (spec 015, T060, SC-004; research R15, R16.8 e
R16.9): nenhum ator que não seja um dono humano conecta, liga o interruptor, agenda, reagenda,
cancela, arquiva ou devolve à fila um envio automático; a trilha não envia o que não tem
decisão humana. Toda recusa a não humano deixa o evento `publicacao_recusada`."""

from datetime import UTC, datetime, timedelta

import pytest
from atores import ator_fake
from sqlalchemy import func, select

from integration.conexao_helpers import (  # noqa: F401
    HOST_WEB,
    app_tiktok,
    conectar,
    destino_auto,
)
from integration.postagem_helpers import (  # noqa: F401
    aprovado,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api import history
from sociman_api.auth.deps import Actor, current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao.models import Conexao, ConexaoCredencial, PublicacaoConfig


def _err(r) -> str:
    return r.json()["error"]["code"]


def _eventos(db) -> list[SecurityEvent]:
    db.expire_all()
    return list(db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada").order_by(SecurityEvent.id)))


def _foto(db) -> tuple:
    """Tudo o que uma recusa não pode mudar."""
    db.expire_all()
    return (
        db.scalar(select(func.count()).select_from(Conexao)),
        db.scalar(select(func.count()).select_from(ConexaoCredencial)),
        db.scalar(select(func.count()).select_from(EntityVersion)),
        db.get(PublicacaoConfig, 1).envios_habilitados,
        tuple(db.execute(select(Postagem.id, Postagem.estado, Postagem.version,
                                Postagem.archived_at).order_by(Postagem.id)).all()),
    )


@pytest.fixture
def cena(client, db, dono, app_tiktok):  # noqa: F811
    user, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], handle="atavernanerd")
    cx = conectar(client, h, conta, app_tiktok)["conexao"]
    agendado = destino_auto(db, perfil["id"], conta["id"], user)
    falhou = destino_auto(db, perfil["id"], conta["id"], user, estado="falhou",
                          planned_at=datetime.now(UTC) - timedelta(hours=3))
    vencido = destino_auto(db, perfil["id"], conta["id"], user,
                           planned_at=datetime.now(UTC) - timedelta(hours=2))
    return {"user": user, "h": h, "perfil": perfil, "conta": conta, "cx": cx,
            "agendado": agendado, "falhou": falhou, "vencido": vencido, "fake": app_tiktok}


def _rotas_h(cena) -> list[tuple[str, str, dict | None]]:
    conta = cena["conta"]["id"]
    return [
        ("POST", f"/api/contas/{conta}/conexao/iniciar", {}),
        ("POST", "/api/conexoes/retorno", {"state": "qualquer", "code": "x"}),
        ("POST", f"/api/contas/{conta}/conexao/desconectar", {"version": cena["cx"]["version"]}),
        ("GET", f"/api/contas/{conta}/conexao/criador", None),
        ("PUT", "/api/publicacao/config", {"version": 1, "enviosHabilitados": True}),
        ("POST", f"/api/destinos/{cena['falhou'].id}/tentar-de-novo",
         {"version": cena["falhou"].version}),
        ("POST", f"/api/destinos/{cena['vencido'].id}/confirmar-envio",
         {"version": cena["vencido"].version}),
    ]


@pytest.mark.parametrize("kind", ["mcp_client", "system:cli", "system:agente"])
def test_rotas_h_recusam_nao_humano(client, db, cena, kind):
    antes = _foto(db)
    user = cena["user"]
    app.dependency_overrides[current_user] = lambda: ator_fake(kind, user)
    rotas = _rotas_h(cena)
    for metodo, rota, body in rotas:
        r = client.request(metodo, rota, headers={**cena["h"], **HOST_WEB}, json=body)
        assert r.status_code == 403 and _err(r) == "somente_humano", (rota, r.text)
    app.dependency_overrides.clear()
    assert _foto(db) == antes
    eventos = _eventos(db)
    assert len(eventos) == len(rotas)
    assert {e.actor_kind for e in eventos} == {kind}
    assert all(e.outcome == "denied" and e.details["actorKind"] == kind for e in eventos)
    conta = cena["conta"]["id"]
    assert eventos[0].details == {"rota": "/api/contas/{conta_id}/conexao/iniciar",
                                  "actorKind": kind, "contaId": conta}
    assert eventos[5].details["destinoId"] == str(cena["falhou"].id)
    assert cena["fake"].inits == 0


def test_rotas_h_recusam_membro(client, db, cena, membro):  # noqa: F811
    antes = _foto(db)
    for metodo, rota, body in _rotas_h(cena):
        r = client.request(metodo, rota, headers={**membro[1], **HOST_WEB}, json=body)
        assert r.status_code == 403 and _err(r) == "somente_dono", (rota, r.text)
    assert _foto(db) == antes
    assert _eventos(db) == []


# ---- modo automático nas rotas da 014 (service) ----

@pytest.fixture
def pronto(client, db, cena):
    """Um conteúdo pronto com destino aprovado (ainda sem agendamento) na conta conectada."""
    corte = criar_corte(db, cena["perfil"]["id"])
    destino = aprovado(client, cena["h"], corte.id, cena["conta"]["id"])
    return {"corte": corte, "destino": destino}


def _agendar(client, h, cena, pronto, modo="criar_rascunho"):
    return client.post("/api/agendamentos", headers=h, json={
        "conteudoId": str(pronto["corte"].id), "contaId": cena["conta"]["id"],
        "plannedAt": (datetime.now(UTC) + timedelta(days=1)).isoformat(), "modo": modo,
        "destinoVersion": pronto["destino"]["version"],
        "textos": {"descricao": "Legenda"}})  # T101: legenda obrigatória na TikTok


def _como(kind, user):
    app.dependency_overrides[current_user] = lambda: ator_fake(kind, user)


def test_agendar_automatico_so_dono_humano(client, db, cena, pronto, membro):  # noqa: F811
    antes = _foto(db)
    r = _agendar(client, membro[1], cena, pronto)
    assert r.status_code == 403 and _err(r) == "somente_dono"
    _como("mcp_client", cena["user"])
    r = _agendar(client, cena["h"], cena, pronto)
    assert r.status_code == 403 and _err(r) == "somente_humano"
    app.dependency_overrides.clear()
    assert _foto(db) == antes
    assert len(_eventos(db)) == 1
    # lembrete continua aberto (014 Q1), e o dono humano agenda o automático
    r = _agendar(client, cena["h"], cena, pronto)
    assert r.status_code in (200, 201), r.text
    assert r.json()["destino"]["modo"] == "criar_rascunho"


def test_mudar_agendamento_automatico_so_dono_humano(client, db, cena):
    d = cena["agendado"]
    amanha = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    chamadas = [
        ("PATCH", f"/api/destinos/{d.id}/agendamento",
         {"version": d.version, "plannedAt": amanha}),
        ("POST", f"/api/destinos/{d.id}/agendamento/cancelar", {"version": d.version}),
        ("POST", f"/api/destinos/{d.id}/archive", {"version": d.version}),
    ]
    antes = _foto(db)
    _como("mcp_client", cena["user"])
    for metodo, rota, body in chamadas:
        r = client.request(metodo, rota, headers=cena["h"], json=body)
        assert r.status_code == 403 and _err(r) == "somente_humano", (rota, r.text)
    # em lote, a recusa vai por item em `falhas`
    r = client.post("/api/agendamentos/lote/cancelar", headers=cena["h"],
                    json={"itens": [{"destinoId": str(d.id), "version": d.version}]})
    assert r.status_code == 200 and r.json()["ok"] == []
    assert [f["code"] for f in r.json()["falhas"]] == ["somente_humano"]
    r = client.post("/api/agendamentos/lote/reagendar", headers=cena["h"], json={
        "itens": [{"destinoId": str(d.id), "version": d.version, "plannedAt": amanha}]})
    assert r.status_code == 200 and [f["code"] for f in r.json()["falhas"]] == [
        "somente_humano"]
    app.dependency_overrides.clear()
    assert _foto(db) == antes
    assert len(_eventos(db)) == len(chamadas) + 2


# ---- execução (R15, defesa redundante) ----

def test_trilha_recusa_agendamento_sem_decisao_humana(client, db, cena, publicacao_habilitada):
    from sociman_api.publicacao import trilha

    publicacao_habilitada(True)
    r = client.put("/api/publicacao/config", headers=cena["h"],
                   json={"version": 1, "enviosHabilitados": True})
    assert r.status_code == 200
    # gravado direto no banco, com a "decisão" de um ator de sistema
    d = cena["agendado"]
    before = history.snapshot(d)
    d.planned_at = datetime.now(UTC) - timedelta(minutes=1)
    history.record(db, Actor(kind="system:cli"), "postagem", d, "updated", before,
                   history.snapshot(d), {"acao": "agendado"})
    db.commit()
    trilha.rodar(db, client=cena["fake"].client())
    assert cena["fake"].inits == 0
    db.expire_all()
    assert db.get(Postagem, d.id).estado == DestinoEstado.falhou
    [ev] = _eventos(db)
    assert ev.actor_kind == "system:cli" and ev.details["destinoId"] == str(d.id)


def test_nao_ha_rota_delete_nova(client):
    for path, ops in app.openapi()["paths"].items():
        if path.startswith(("/api/conexoes", "/api/publicacao", "/api/contas/{conta_id}/conexao")):
            assert "delete" not in ops, path
