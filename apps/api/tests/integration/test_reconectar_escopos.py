"""Reconectar para liberar as métricas (spec 016, US1, T021; research R1; contrato, "Rotas da
015 que mudam"). Sempre com a TikTok falsa; nenhum teste chama a TikTok real."""

import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from fakes.tiktok_fake import ESCOPOS, ESCOPOS_016
from sqlalchemy import func, select

from integration.conexao_helpers import (  # noqa: F401
    HOST_WEB,
    app_tiktok,
    conectar,
    destino_auto,
    iniciar,
    retorno,
)
from integration.postagem_helpers import criar_conta, criar_perfil, dono, membro  # noqa: F401
from sociman_api.auth.deps import Actor, current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.metricas.models import Serie
from sociman_api.perfis.models import Platform
from sociman_api.publicacao.models import Conexao, ConexaoCredencial, ConexaoEstado


@pytest.fixture
def c(client, dono, app_tiktok):  # noqa: F811
    user, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], handle="atavernanerd")
    return {"user": user, "h": h, "perfil": perfil, "conta": conta, "fake": app_tiktok}


def _err(r) -> str:
    return r.json()["error"]["code"]


def _iniciar(client, c):
    return client.post(f"/api/contas/{c['conta']['id']}/conexao/iniciar",
                       headers={**c["h"], **HOST_WEB})


def _acoes(db, conexao_id) -> list[str]:
    return [v.details["acao"] for v in db.scalars(
        select(EntityVersion).where(EntityVersion.entity_id == conexao_id)
        .order_by(EntityVersion.version))]


def test_iniciar_pede_os_seis_escopos_na_conexao_sem_metricas(client, db, c):
    cx = conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS)["conexao"]
    assert cx["metricas"]["permissao"] == "faltando"
    assert cx["metricas"]["escoposFaltando"] == ["user.info.stats", "video.list"]
    assert not cx["metricas"]["coletando"]
    r = _iniciar(client, c)
    assert r.status_code == 200, r.text
    escopos = parse_qs(urlsplit(r.json()["autorizarUrl"]).query)["scope"][0].split(",")
    assert set(escopos) == set(ESCOPOS_016.split(",")) and len(escopos) == 6


def test_com_todos_os_escopos_continua_ja_conectada(client, c):
    conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS_016)
    r = _iniciar(client, c)
    assert r.status_code == 409 and _err(r) == "ja_conectada"


def test_envio_em_andamento_bloqueia_a_ampliacao(client, db, c):
    conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS)
    destino_auto(db, c["perfil"]["id"], c["conta"]["id"], c["user"], estado="enviando")
    r = _iniciar(client, c)
    assert r.status_code == 409 and _err(r) == "envio_em_andamento"


def test_retorno_com_o_mesmo_open_id_amplia_a_mesma_linha(client, db, c):
    cx = conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS)["conexao"]
    [antiga] = db.scalars(select(Conexao))
    cred_antiga = db.get(ConexaoCredencial, antiga.id).access_cifrado
    # a série existia e tinha perdido a permissão em uso
    serie = Serie(rede=Platform.tiktok, conta_id=antiga.conta_id,
                  sem_permissao_desde=datetime.now(UTC),
                  ultimo_erro_codigo="scope_not_authorized", ultimo_erro_motivo="x",
                  ultimo_erro_em=datetime.now(UTC))
    db.add(serie)
    db.commit()

    r = conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS_016)
    db.expire_all()
    [mesma] = db.scalars(select(Conexao))
    assert mesma.id == antiga.id and mesma.estado == ConexaoEstado.conectada
    assert set(mesma.escopos) == set(ESCOPOS_016.split(","))
    assert db.get(ConexaoCredencial, mesma.id).access_cifrado != cred_antiga
    assert db.scalar(select(func.count()).select_from(ConexaoCredencial)) == 1
    assert mesma.version == cx["version"] + 1
    assert _acoes(db, mesma.id) == ["conectada", "ampliada"]
    serie = db.get(Serie, serie.id)
    assert serie.sem_permissao_desde is None and serie.ultimo_erro_codigo is None
    m = r["conexao"]["metricas"]
    assert m["permissao"] == "ok" and m["escoposFaltando"] == [] and m["coletando"]


def test_open_id_diferente_continua_conta_diferente(client, db, c):
    conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS)
    r = retorno(client, c["h"], c["conta"]["id"], c["fake"], "atavernanerd",
                open_id="open-impostor", escopos=ESCOPOS_016)
    assert r.status_code == 409 and _err(r) == "conta_diferente"
    [cx] = db.scalars(select(Conexao))
    assert set(cx.escopos) == set(ESCOPOS.split(","))


def test_dono_desmarca_video_list_na_tiktok(client, db, c):
    conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS)
    sem_lista = ESCOPOS + ",user.info.stats"
    r = conectar(client, c["h"], c["conta"], c["fake"], escopos=sem_lista)
    assert set(r["conexao"]["escopos"]) == set(sem_lista.split(","))
    assert r["conexao"]["metricas"]["escoposFaltando"] == ["video.list"]
    r = client.get(f"/api/contas/{c['conta']['id']}/conexao", headers=c["h"])
    assert r.json()["conexao"]["metricas"]["permissao"] == "faltando"


def test_get_sem_conexao_traz_metricas_sem_conexao(client, c):
    r = client.get(f"/api/contas/{c['conta']['id']}/conexao", headers=c["h"])
    m = r.json()["conexao"]["metricas"]
    assert m["permissao"] == "sem_conexao" and not m["coletando"] and m["videos"] == 0
    assert m["habilitada"] is True


def test_conta_de_rede_sem_leitor_tem_metricas_null(client, c):
    yt = criar_conta(client, c["h"], c["perfil"]["id"], platform="youtube")
    r = client.get(f"/api/contas/{yt['id']}/conexao", headers=c["h"])
    assert r.status_code == 200 and r.json()["conexao"]["metricas"] is None


def test_membro_nao_amplia(client, db, c, membro):  # noqa: F811
    conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS)
    _, hm = membro
    r = client.post(f"/api/contas/{c['conta']['id']}/conexao/iniciar",
                    headers={**hm, **HOST_WEB})
    assert r.status_code == 403 and _err(r) == "somente_dono"
    r = client.get(f"/api/contas/{c['conta']['id']}/conexao", headers=hm)
    assert r.json()["conexao"]["metricas"]["permissao"] == "faltando"  # vê o estado


@pytest.mark.parametrize("kind", ["mcp_client"])
def test_cliente_mcp_nao_amplia(client, db, c, kind):
    conectar(client, c["h"], c["conta"], c["fake"], escopos=ESCOPOS)
    user = c["user"]
    app.dependency_overrides[current_user] = lambda: Actor(kind=kind, user_id=user.id,
                                                           user=user)
    r = _iniciar(client, c)
    assert r.status_code == 403 and _err(r) == "somente_humano"
    r = client.post("/api/conexoes/retorno", headers=c["h"], json={"state": "x", "code": "y"})
    assert r.status_code == 403 and _err(r) == "somente_humano"
    app.dependency_overrides.clear()
    eventos = list(db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")))
    assert len(eventos) == 2 and {e.actor_kind for e in eventos} == {kind}
    [cx] = db.scalars(select(Conexao))
    assert set(cx.escopos) == set(ESCOPOS.split(","))
    assert uuid.UUID(c["conta"]["id"]) == cx.conta_id
