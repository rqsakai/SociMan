"""T043 e T044 (US4, FR-020/FR-021/FR-022): textos do destino pelo agente, a proposta aplicada
pelo humano e o envio selecionado pela tool."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from integration.envios_helpers import criar_canal, criar_video
from integration.mcp_helpers import bearer, com_mcp, criar_cliente, ligar
from integration.postagem_helpers import (  # noqa: F401
    acao,
    add_destino,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import SecurityEvent
from sociman_api.envios.models import Envio
from sociman_api.errors import ApiError
from sociman_api.postagem import service
from sociman_api.postagem.models import DestinoEstado
from sociman_api.postagem.schemas import UpdateDestinoIn


@pytest.fixture
def base(client, dono, membro, db, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"])
    corte = criar_corte(db, perfil["id"])
    destino = add_destino(client, h, corte.id, conta["id"])
    cliente, token = criar_cliente(client, h, "Planejador", "propostas")
    return {"h": h, "hm": membro[1], "perfil": perfil, "destino": destino, "token": token,
            "cliente": cliente}


def _patch(client, h, destino, **campos):
    return client.patch(f"/api/destinos/{destino['id']}", headers=h,
                        json={"version": destino["version"], **campos})


def test_agente_edita_pendente_e_pedido(client, base):
    d = base["destino"]
    r = _patch(client, bearer(base["token"]), d, titulo="Título do agente")
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    r = acao(client, base["h"], d, "pedir-aprovacao")
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    r = _patch(client, bearer(base["token"]), d, descricao="Legenda do agente")
    assert r.status_code == 200
    versoes = client.get(f"/api/destinos/{d['id']}/versions", headers=base["h"]).json()["items"]
    assert versoes[0]["autor"] == {"tipo": "mcp_client", "id": base["cliente"]["id"],
                                   "nome": "Planejador"}


@pytest.mark.parametrize("estado", list(DestinoEstado))
def test_trava_por_estado(estado):
    """FR-021 em todos os estados (a trava olha só o estado e o arquivamento)."""
    ator = Actor(kind="mcp_client", mcp_client_id=uuid.uuid4(), mcp_escopo="propostas")
    destino = SimpleNamespace(id=uuid.uuid4(), estado=estado, archived=False)
    corpo = UpdateDestinoIn(version=1, titulo="x")
    if estado in (DestinoEstado.pendente, DestinoEstado.aprovacao_pedida):
        service._trava_mcp(ator, destino, corpo)
    else:
        with pytest.raises(ApiError) as exc:
            service._trava_mcp(ator, destino, corpo)
        assert exc.value.status == 409 and exc.value.code == "destino_aprovado"


def test_aprovado_e_agendado_recusados(client, base):
    d = acao(client, base["h"], base["destino"], "aprovar").json()["destino"]
    r = _patch(client, bearer(base["token"]), d, titulo="tentativa")
    assert r.status_code == 409 and r.json()["error"]["code"] == "destino_aprovado"
    assert "proposta" in r.json()["error"]["message"]
    atual = client.get(f"/api/destinos/{d['id']}", headers=base["h"]).json()["destino"]
    assert atual["version"] == d["version"] and atual["titulo"] == d["titulo"]


def test_arquivado_recusado(client, base):
    d = base["destino"]
    d = acao(client, base["h"], d, "archive").json()["destino"]
    r = _patch(client, bearer(base["token"]), d, titulo="x")
    assert r.status_code == 409  # arquivado: a regra geral do destino recusa antes (conflict)


def test_agente_nao_aplica_proposta(client, base, db):
    d = base["destino"]
    p = client.post("/api/anotacoes", headers=bearer(base["token"]), json={
        "alvoTipo": "destino", "alvoId": d["id"], "tipo": "proposta_texto", "texto": "p",
        "campos": {"titulo": "T"}}).json()["anotacao"]
    r = _patch(client, bearer(base["token"]), d, titulo="T", propostaId=p["id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    assert db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()
    p = client.get(f"/api/anotacoes/{p['id']}", headers=base["h"]).json()["anotacao"]
    assert p["situacao"] == "aberta"


def test_humano_aplica_proposta(client, base):
    d = base["destino"]
    p = client.post("/api/anotacoes", headers=bearer(base["token"]), json={
        "alvoTipo": "destino", "alvoId": d["id"], "tipo": "proposta_texto", "texto": "p",
        "campos": {"descricao": "Legenda proposta"}}).json()["anotacao"]
    r = _patch(client, base["hm"], d, descricao="Legenda proposta", propostaId=p["id"])
    assert r.status_code == 200, r.text
    versoes = client.get(f"/api/destinos/{d['id']}/versions", headers=base["h"]).json()["items"]
    assert versoes[0]["autor"]["tipo"] == "usuario"
    assert versoes[0]["details"]["proposta"] == {"id": p["id"], "clienteId": base["cliente"]["id"],
                                                 "clienteNome": "Planejador"}
    p = client.get(f"/api/anotacoes/{p['id']}", headers=base["h"]).json()["anotacao"]
    assert p["situacao"] == "aplicada" and p["resolvidaPor"]["name"] == "Membro"
    # fechada: não aplica de novo
    d = client.get(f"/api/destinos/{d['id']}", headers=base["h"]).json()["destino"]
    r = _patch(client, base["h"], d, descricao="outra", propostaId=p["id"])
    assert r.status_code == 409


def test_proposta_de_outro_destino_recusada(client, base, db):
    conta = criar_conta(client, base["h"], base["perfil"]["id"], platform="youtube")
    corte = criar_corte(db, base["perfil"]["id"])
    outro = add_destino(client, base["h"], corte.id, conta["id"])
    p = client.post("/api/anotacoes", headers=bearer(base["token"]), json={
        "alvoTipo": "destino", "alvoId": outro["id"], "tipo": "proposta_texto", "texto": "p",
        "campos": {"titulo": "T"}}).json()["anotacao"]
    r = _patch(client, base["h"], base["destino"], titulo="T", propostaId=p["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "proposta_invalida"


def test_conflito_e_reverter_edicao_do_agente(client, base):
    d = base["destino"]
    r = _patch(client, base["h"], d, titulo="do dono")
    assert r.status_code == 200
    r = _patch(client, bearer(base["token"]), d, titulo="do agente")  # versão velha
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    d = client.get(f"/api/destinos/{d['id']}", headers=base["h"]).json()["destino"]
    d = _patch(client, bearer(base["token"]), d, titulo="do agente").json()["destino"]
    r = client.post(f"/api/destinos/{d['id']}/revert", headers=base["h"],
                    json={"version": d["version"], "toVersion": d["version"] - 1})
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["titulo"] == "do dono"
    versoes = client.get(f"/api/destinos/{d['id']}/versions", headers=base["h"]).json()["items"]
    assert versoes[0]["action"] == "reverted" and versoes[0]["autor"]["tipo"] == "usuario"


# ---- T044: envio selecionado pela tool ----

def test_envio_selecionado_pela_tool(client, base, db):
    canal = criar_canal()
    video = criar_video(canal)

    async def chamar(c):
        primeiro = await c.call_tool("envios_selecionar", {
            "perfil_id": base["perfil"]["id"], "videoFonteId": str(video.id)})
        segundo = await c.call_tool("envios_selecionar", {
            "perfil_id": base["perfil"]["id"], "videoFonteId": str(video.id)})
        return primeiro, segundo

    primeiro, segundo = com_mcp(base["token"], chamar)
    assert not primeiro.is_error, primeiro.content[0].text
    envio = primeiro.structured_content["envio"]
    assert envio["status"] == "selecionado"
    assert segundo.is_error and segundo.structured_content["status"] == 409
    versoes = client.get(f"/api/envios/{envio['id']}/versions", headers=base["h"]).json()["items"]
    assert versoes[-1]["autor"]["tipo"] == "mcp_client"
    assert db.scalar(select(Envio).where(Envio.id == envio["id"])).status == "selecionado"
    r = client.post(f"/api/envios/{envio['id']}/archive", headers=base["h"],
                    json={"version": envio["version"]})
    assert r.status_code == 200, r.text  # o desfazer (humano) da exceção do VII
    assert not db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()
