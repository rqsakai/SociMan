"""Interruptor "Envios automáticos" e ações humanas da execução (spec 015, T062 e T045;
research R11 e R15; Clarifications Q3 e Q4)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from integration.conexao_helpers import app_tiktok, conectar, destino_auto  # noqa: F401
from integration.postagem_helpers import criar_conta, criar_perfil, dono, membro  # noqa: F401
from sociman_api.auth.deps import Actor, current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.conteudos.models import Modo
from sociman_api.main import app
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao.models import Tentativa, TentativaFase
from sociman_api.publicacao.service import CONFIG_ENTITY_ID

URL = "/api/publicacao/config"


def _err(r) -> str:
    return r.json()["error"]["code"]


def _cfg(client, h) -> dict:
    r = client.get(URL, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["config"]


def _eventos(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada"))


def _como_mcp(user) -> None:
    app.dependency_overrides[current_user] = lambda: Actor(kind="mcp_client", user_id=user.id,
                                                           user=user)


# ---- GET / PUT ----

def test_get_dono_e_membro(client, dono, membro):  # noqa: F811
    for _, h in (dono, membro):
        cfg = _cfg(client, h)
        assert cfg["servidorHabilitado"] is False  # PUBLICACAO_HABILITADA=false no teste
        assert cfg["enviosHabilitados"] is False
        assert cfg["tokensConfigurados"] is True  # chave fixa de teste do compose
        assert cfg["situacaoApp"] == "sandbox"
        assert cfg["vencidos"] == 0 and cfg["emAndamento"] == 0 and cfg["version"] == 1
        assert set(cfg["enderecosLogin"]) == {"web", "desktop"}
        # nada de segredo, só booleanos
        assert not any(k.lower().endswith(("key", "secret", "token")) for k in cfg)


def test_app_configurado_e_enderecos(client, dono, app_tiktok):  # noqa: F811
    cfg = _cfg(client, dono[1])
    assert cfg["appConfigurado"] is True
    assert cfg["enderecosLogin"]["web"].startswith("https://192.168.86.47:8543/")
    assert cfg["enderecosLogin"]["desktop"].startswith("http://localhost:8180/")


def test_ligar_e_desligar_com_historico(client, db, dono, publicacao_habilitada):  # noqa: F811
    user, h = dono
    r = client.put(URL, headers=h, json={"version": 1, "enviosHabilitados": True})
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert cfg["enviosHabilitados"] is True and cfg["version"] == 2
    assert cfg["servidorHabilitado"] is False  # o PUT não mexe no nível do servidor
    r = client.put(URL, headers=h, json={"version": 1, "enviosHabilitados": False})
    assert r.status_code == 409 and _err(r) == "version_conflict"
    r = client.put(URL, headers=h, json={"version": 2, "enviosHabilitados": False})
    assert r.status_code == 200 and r.json()["config"]["version"] == 3
    # mesmo valor: sem versão nova
    r = client.put(URL, headers=h, json={"version": 3, "enviosHabilitados": False})
    assert r.status_code == 200 and r.json()["config"]["version"] == 3
    itens = client.get(f"{URL}/versions", headers=h).json()["items"]
    assert [i["details"]["acao"] for i in itens] == ["desligado", "ligado"]
    assert all(i["actor"]["id"] == str(user.id) and i["actorKind"] == "user" for i in itens)
    assert itens[0]["after"] == {"envios_habilitados": False}
    publicacao_habilitada(True)
    assert _cfg(client, h)["servidorHabilitado"] is True


def test_put_so_dono_humano(client, db, dono, membro):  # noqa: F811
    r = client.put(URL, headers=membro[1], json={"version": 1, "enviosHabilitados": True})
    assert r.status_code == 403 and _err(r) == "somente_dono"
    _como_mcp(dono[0])
    r = client.put(URL, headers=dono[1], json={"version": 1, "enviosHabilitados": True})
    assert r.status_code == 403 and _err(r) == "somente_humano"
    assert _eventos(db) == 1
    app.dependency_overrides.clear()
    assert _cfg(client, dono[1])["enviosHabilitados"] is False


def test_vencidos_e_em_andamento(client, db, dono):  # noqa: F811
    user, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"])
    agora = datetime.now(UTC)
    destino_auto(db, perfil["id"], conta["id"], user, planned_at=agora - timedelta(hours=2))
    destino_auto(db, perfil["id"], conta["id"], user, planned_at=agora - timedelta(minutes=10))
    destino_auto(db, perfil["id"], conta["id"], user, planned_at=agora - timedelta(hours=3),
                 envio_confirmado_por=user.id, envio_confirmado_em=agora)
    destino_auto(db, perfil["id"], conta["id"], user, modo="lembrete",
                 planned_at=agora - timedelta(hours=5))
    destino_auto(db, perfil["id"], conta["id"], user, estado="enviando")
    r = client.put(URL, headers=h, json={"version": 1, "enviosHabilitados": True})
    cfg = r.json()["config"]
    assert cfg["vencidos"] == 1 and cfg["emAndamento"] == 1


def test_versions_do_singleton(client, db, dono):  # noqa: F811
    client.put(URL, headers=dono[1], json={"version": 1, "enviosHabilitados": True})
    from sociman_api.history import EntityVersion

    [v] = db.scalars(select(EntityVersion).where(EntityVersion.entity_type ==
                                                 "publicacao_config"))
    assert v.entity_id == CONFIG_ENTITY_ID and v.version == 2


# ---- tentar de novo (T045) e confirmar envio ----

@pytest.fixture
def cenario(client, db, dono, app_tiktok):  # noqa: F811
    user, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], handle="atavernanerd")
    return {"user": user, "h": h, "perfil": perfil, "conta": conta, "fake": app_tiktok}


def _falhou(db, cn, incerta=False) -> Postagem:
    return destino_auto(db, cn["perfil"]["id"], cn["conta"]["id"], cn["user"], estado="falhou",
                        planned_at=datetime.now(UTC) - timedelta(hours=3),
                        falha_motivo="A TikTok recusou", falha_incerta=incerta)


def _post(client, h, destino, acao, **body):
    return client.post(f"/api/destinos/{destino.id}/{acao}", headers=h,
                       json={"version": destino.version, **body})


def test_tentar_de_novo(client, db, cenario):
    cn = cenario
    destino = _falhou(db, cn)
    r = _post(client, cn["h"], destino, "tentar-de-novo")
    assert r.status_code == 409 and _err(r) == "conta_nao_conectada"
    conectar(client, cn["h"], cn["conta"], cn["fake"])
    versao = destino.version
    r = _post(client, cn["h"], destino, "tentar-de-novo")
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "agendado"
    db.expire_all()
    d = db.get(Postagem, destino.id)
    assert d.estado == DestinoEstado.agendado and d.agendado_por == cn["user"].id
    assert abs((d.planned_at - datetime.now(UTC)).total_seconds()) < 60
    assert d.falha_motivo is None and d.version == versao + 1
    # já não está `falhou`
    r = client.post(f"/api/destinos/{destino.id}/tentar-de-novo", headers=cn["h"],
                    json={"version": d.version})
    assert r.status_code == 409 and _err(r) == "conflict"
    assert cn["fake"].inits == 0  # nada foi enviado: a trilha é quem envia


def test_tentar_de_novo_incerta_pede_confirmacao(client, db, cenario):
    cn = cenario
    conectar(client, cn["h"], cn["conta"], cn["fake"])
    destino = _falhou(db, cn, incerta=True)
    r = _post(client, cn["h"], destino, "tentar-de-novo")
    assert r.status_code == 409 and _err(r) == "confirmacao_necessaria"
    r = _post(client, cn["h"], destino, "tentar-de-novo", confirmoQueNaoChegou=True)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Postagem, destino.id).falha_incerta is False
    versoes = client.get(f"/api/destinos/{destino.id}/versions", headers=cn["h"]).json()
    assert versoes["items"][0]["details"] == {"acao": "tentar_de_novo", "conferidoNoApp": True}


def test_confirmar_envio_de_vencido(client, db, cenario):
    cn = cenario
    agora = datetime.now(UTC)
    futuro = destino_auto(db, cn["perfil"]["id"], cn["conta"]["id"], cn["user"])
    r = _post(client, cn["h"], futuro, "confirmar-envio")
    assert r.status_code == 409 and _err(r) == "conflict"
    vencido = destino_auto(db, cn["perfil"]["id"], cn["conta"]["id"], cn["user"],
                           planned_at=agora - timedelta(hours=2))
    r = _post(client, cn["h"], vencido, "confirmar-envio")
    assert r.status_code == 200, r.text
    db.expire_all()
    d = db.get(Postagem, vencido.id)
    assert d.envio_confirmado_por == cn["user"].id and d.envio_confirmado_em >= d.planned_at
    assert d.estado == DestinoEstado.agendado
    r = client.post(f"/api/destinos/{vencido.id}/confirmar-envio", headers=cn["h"],
                    json={"version": d.version})
    assert r.status_code == 409  # já confirmado: não está mais vencido
    versoes = client.get(f"/api/destinos/{vencido.id}/versions", headers=cn["h"]).json()
    assert versoes["items"][0]["details"]["acao"] == "envio_confirmado"


def test_acoes_humanas_recusam_membro_e_mcp(client, db, cenario, membro):  # noqa: F811
    cn = cenario
    destino = _falhou(db, cn)
    for acao in ("tentar-de-novo", "confirmar-envio"):
        r = _post(client, membro[1], destino, acao)
        assert r.status_code == 403 and _err(r) == "somente_dono"
    _como_mcp(cn["user"])
    for acao in ("tentar-de-novo", "confirmar-envio"):
        r = _post(client, cn["h"], destino, acao)
        assert r.status_code == 403 and _err(r) == "somente_humano"
    assert _eventos(db) == 2
    db.expire_all()
    assert db.get(Postagem, destino.id).estado == DestinoEstado.falhou


def test_tentativas_mais_nova_primeiro(client, db, cenario, membro):  # noqa: F811
    cn = cenario
    conectar(client, cn["h"], cn["conta"], cn["fake"])
    from sociman_api.publicacao.models import Conexao

    conexao = db.scalar(select(Conexao))
    destino = _falhou(db, cn)
    agora = datetime.now(UTC)
    for numero, fase, codigo in ((1, TentativaFase.incerta, None),
                                 (2, TentativaFase.recusada, "spam_risk_too_many_posts")):
        db.add(Tentativa(
            id=uuid.uuid4(), destino_id=destino.id, numero=numero, conexao_id=conexao.id,
            rede=conexao.rede, modo=Modo.criar_rascunho, fase=fase, disparo="agendador",
            video_ref="cortes/x/marcado.mp4", video_etag="e", video_bytes=10, chunk_size=10,
            total_partes=1, concluida_em=agora, codigo_rede=codigo, motivo="m"))
    db.commit()
    r = client.get(f"/api/destinos/{destino.id}/tentativas", headers=membro[1])
    assert r.status_code == 200, r.text
    itens = r.json()["items"]
    assert [i["numero"] for i in itens] == [2, 1]
    assert itens[0]["fase"] == "recusada" and itens[0]["acao"] == "reagendar"
    assert itens[1]["acao"] == "tentar_de_novo_conferido"
    assert itens[0]["video"] == {"ref": "cortes/x/marcado.mp4", "bytes": 10, "sha256": None}
    r = client.get(f"/api/destinos/{uuid.uuid4()}/tentativas", headers=membro[1])
    assert r.status_code == 404
