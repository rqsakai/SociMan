"""Conexão da conta TikTok (spec 015, US1, T026 e T079; research R1 a R5, R14, R15).

Sempre com a TikTok falsa (`tests/fakes/tiktok_fake.py`); nenhum teste chama a TikTok real."""

import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from integration.conexao_helpers import (  # noqa: F401
    DESKTOP,
    HOST_DESKTOP,
    HOST_WEB,
    WEB,
    app_tiktok,
    conectar,
    destino_auto,
    iniciar,
    redis_state,
    retorno,
    state_de,
)
from integration.postagem_helpers import (  # noqa: F401
    criar_conta,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.auth.models import SecurityEvent
from sociman_api.config import get_settings
from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Conta, ContaStatus
from sociman_api.postagem.models import DestinoEstado
from sociman_api.publicacao.models import Conexao, ConexaoCredencial, ConexaoEstado
from sociman_api.publicacao.tiktok import oauth

SEGREDOS = ("act.fake", "rft.fake", "access_token", "refresh_token", "upl-")


@pytest.fixture
def c(client, dono, app_tiktok):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], handle="atavernanerd")
    return {"h": h, "perfil": perfil, "conta": conta, "fake": app_tiktok}


def _err(r) -> str:
    return r.json()["error"]["code"]


def _sem_segredo(r) -> None:
    assert not any(s in r.text for s in SEGREDOS), r.text


def _conexoes(db) -> list[Conexao]:
    db.expire_all()
    return list(db.scalars(select(Conexao).order_by(Conexao.conectado_em)))


def _creds(db) -> int:
    return db.scalar(select(func.count()).select_from(ConexaoCredencial))


# ---- iniciar ----

def test_iniciar_web_sem_pkce(client, c):
    url = iniciar(client, c["h"], c["conta"]["id"], HOST_WEB)
    q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert url.startswith(oauth.AUTORIZAR_URL)
    assert q["redirect_uri"] == WEB
    assert "code_challenge" not in q
    st = redis_state(q["state"])
    assert st["plataforma"] == "web" and st["redirectUri"] == WEB
    assert st["contaId"] == c["conta"]["id"] and st["codeVerifier"] is None


def test_desktop_com_pkce_conecta(client, c):
    url = iniciar(client, c["h"], c["conta"]["id"], HOST_DESKTOP)
    q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    st = redis_state(q["state"])
    assert q["redirect_uri"] == DESKTOP and st["plataforma"] == "desktop"
    assert q["code_challenge"] == oauth.code_challenge(st["codeVerifier"])
    assert q["code_challenge_method"] == "S256"
    c["fake"].usuario("cod", "atavernanerd", verifier=st["codeVerifier"])
    r = client.post("/api/conexoes/retorno", headers=c["h"], json={"state": q["state"],
                                                                    "code": "cod"})
    assert r.status_code == 200, r.text
    [troca] = c["fake"].pedidos("token")
    assert troca == {"grant_type": "authorization_code", "pkce": True, "redirect_uri": DESKTOP}


def test_endereco_de_login_nao_configurado(client, c, monkeypatch):
    monkeypatch.setattr(get_settings(), "tiktok_redirect_web", "")
    r = client.post(f"/api/contas/{c['conta']['id']}/conexao/iniciar",
                    headers={**c["h"], **HOST_WEB})
    assert r.status_code == 409 and _err(r) == "endereco_de_login"
    assert r.json()["error"]["details"] == {"abrirEm": "http://localhost:8180"}


@pytest.mark.parametrize("campo", ["tiktok_client_key", "tiktok_client_secret",
                                   "sociman_tokens_key"])
def test_publicacao_nao_configurada(client, c, monkeypatch, campo):
    monkeypatch.setattr(get_settings(), campo, SecretStr(""))
    r = client.post(f"/api/contas/{c['conta']['id']}/conexao/iniciar",
                    headers={**c["h"], **HOST_WEB})
    assert r.status_code == 503 and _err(r) == "publicacao_nao_configurada"


def test_conta_invalida(client, db, c):
    yt = criar_conta(client, c["h"], c["perfil"]["id"], platform="youtube")
    r = client.post(f"/api/contas/{yt['id']}/conexao/iniciar", headers={**c["h"], **HOST_WEB})
    assert r.status_code == 400 and _err(r) == "conta_invalida"
    conta = db.get(Conta, uuid.UUID(c["conta"]["id"]))
    conta.status = ContaStatus.encerrada
    db.commit()
    r = client.post(f"/api/contas/{conta.id}/conexao/iniciar", headers={**c["h"], **HOST_WEB})
    assert r.status_code == 400 and _err(r) == "conta_invalida"
    r = client.post(f"/api/contas/{uuid.uuid4()}/conexao/iniciar", headers={**c["h"],
                                                                           **HOST_WEB})
    assert r.status_code == 404


# ---- retorno ----

def test_conecta_e_mostra(client, db, c, s3):
    body = conectar(client, c["h"], c["conta"], c["fake"])
    _sem_segredo(client.get(f"/api/contas/{c['conta']['id']}/conexao", headers=c["h"]))
    cx = body["conexao"]
    assert body["contaId"] == c["conta"]["id"] and body["perfilId"] == c["perfil"]["id"]
    assert cx["estado"] == "conectada" and cx["username"] == "atavernanerd"
    assert cx["displayName"] == "Apelido de teste"
    assert "video.upload" in cx["escopos"] and cx["conectadoPor"]["name"] == "Dono"
    assert cx["avatarUrl"].startswith("/img/")
    modos = {m["modo"]: m for m in cx["modos"]}
    assert modos["criar_rascunho"]["disponivel"]
    assert modos["publicar"]["disponivel"] and modos["publicar"]["aviso"]  # US3, sandbox
    [conexao] = _conexoes(db)
    assert conexao.avatar_key.startswith(f"conexoes/{conexao.id}/avatar-")
    guardados = s3.keys()
    assert conexao.avatar_key in guardados
    assert _creds(db) == 1
    cred = db.get(ConexaoCredencial, conexao.id)
    assert b"act.fake" not in cred.access_cifrado and b"rft.fake" not in cred.refresh_cifrado


def test_state_uso_unico_e_de_outro_usuario(client, db, c, make_user, login):
    url = iniciar(client, c["h"], c["conta"]["id"])
    state = state_de(url)
    outro = make_user(role="dono", name="Outro dono")
    h2 = login(client, outro.email, "senha-forte-123")
    r = client.post("/api/conexoes/retorno", headers=h2, json={"state": state, "code": "x"})
    assert r.status_code == 400 and _err(r) == "state_invalido"
    # o GETDEL gastou o state: nem o dono certo usa de novo
    r = client.post("/api/conexoes/retorno", headers=c["h"], json={"state": state, "code": "x"})
    assert r.status_code == 400 and _err(r) == "state_invalido"
    r = client.post("/api/conexoes/retorno", headers=c["h"], json={"state": "inexistente",
                                                                    "code": "x"})
    assert r.status_code == 400 and _err(r) == "state_invalido"
    assert _conexoes(db) == []


def test_autorizacao_negada(client, db, c):
    state = state_de(iniciar(client, c["h"], c["conta"]["id"]))
    r = client.post("/api/conexoes/retorno", headers=c["h"],
                    json={"state": state, "error": "access_denied",
                          "errorDescription": "user cancelled"})
    assert r.status_code == 409 and _err(r) == "autorizacao_negada"
    assert _conexoes(db) == [] and c["fake"].pedidos("token") == []


def test_codigo_recusado(client, db, c):
    state = state_de(iniciar(client, c["h"], c["conta"]["id"]))
    r = client.post("/api/conexoes/retorno", headers=c["h"],
                    json={"state": state, "code": "nao-existe"})
    assert r.status_code == 409 and _err(r) == "autorizacao_negada"
    assert _conexoes(db) == []


def test_escopo_faltando_revoga(client, db, c):
    r = retorno(client, c["h"], c["conta"]["id"], c["fake"], "atavernanerd",
                escopos="user.info.basic,user.info.profile")
    assert r.status_code == 409 and _err(r) == "escopo_faltando"
    assert r.json()["error"]["details"] == {"faltando": ["video.upload"]}
    assert c["fake"].revogados == ["open-atavernanerd"]
    assert _conexoes(db) == [] and _creds(db) == 0


def test_conta_diferente_nada_gravado_e_revoga(client, db, c):
    r = retorno(client, c["h"], c["conta"]["id"], c["fake"], "Outra.Conta")
    assert r.status_code == 409 and _err(r) == "conta_diferente"
    assert r.json()["error"]["details"] == {"autorizado": "outra.conta",
                                            "esperado": "atavernanerd"}
    assert "@outra.conta" in r.json()["error"]["message"]
    assert c["fake"].revogados == ["open-Outra.Conta"]
    assert _conexoes(db) == [] and _creds(db) == 0
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(EntityVersion).where(
        EntityVersion.entity_type == "conexao")) == 0


def test_username_com_maiusculas_e_arroba(client, c):
    body = conectar(client, c["h"], c["conta"], c["fake"], username="@AtavernaNerd",
                    open_id="open-x")
    assert body["conexao"]["username"] == "atavernanerd"


def test_conexao_em_uso(client, db, c):
    conectar(client, c["h"], c["conta"], c["fake"], open_id="open-mesmo")
    perfil2 = criar_perfil(client, c["h"], "Outro perfil")
    outra = criar_conta(client, c["h"], perfil2["id"], handle="outra")
    # a mesma conta da TikTok (open_id) respondendo com o @ da outra conta do SociMan
    r = retorno(client, c["h"], outra["id"], c["fake"], "outra", open_id="open-mesmo")
    assert r.status_code == 409 and _err(r) == "conexao_em_uso"
    assert len(_conexoes(db)) == 1


def test_sem_username_cai_para_creator_info(client, db, c, monkeypatch):
    fake = c["fake"]
    original = fake._creator_info

    def _criador(request, form, corpo):
        resp = original(request, form, corpo)
        dados = resp.json()
        dados["data"]["creator_username"] = "atavernanerd"
        return fake._json(dados)

    monkeypatch.setattr(fake, "_creator_info", _criador)
    r = retorno(client, c["h"], c["conta"]["id"], fake, None, open_id="open-sem")
    assert r.status_code == 200, r.text
    assert r.json()["conexao"]["username"] == "atavernanerd"
    assert fake.pedidos("creator_info")


def test_sem_identidade(client, db, c):
    r = retorno(client, c["h"], c["conta"]["id"], c["fake"], None, open_id="open-sem")
    assert r.status_code == 409 and _err(r) == "identidade_indisponivel"
    assert c["fake"].revogados == ["open-sem"] and _conexoes(db) == []


def test_ja_conectada(client, c):
    conectar(client, c["h"], c["conta"], c["fake"])
    r = client.post(f"/api/contas/{c['conta']['id']}/conexao/iniciar",
                    headers={**c["h"], **HOST_WEB})
    assert r.status_code == 409 and _err(r) == "ja_conectada"


# ---- desconectar e reconectar ----

def test_desconectar_revoga_apaga_e_historico(client, db, c, dono):  # noqa: F811
    user, h = dono
    cx = conectar(client, h, c["conta"], c["fake"])["conexao"]
    auto = destino_auto(db, c["perfil"]["id"], c["conta"]["id"], user)
    destino_auto(db, c["perfil"]["id"], c["conta"]["id"], user, modo="lembrete")
    r = client.post(f"/api/contas/{c['conta']['id']}/conexao/desconectar", headers=h,
                    json={"version": cx["version"]})
    assert r.status_code == 200, r.text
    _sem_segredo(r)
    assert r.json()["conexao"]["estado"] == "nao_conectada"
    assert r.json()["agendamentosEmAtencao"] == 1
    assert c["fake"].revogados == ["open-atavernanerd"]
    assert _creds(db) == 0
    [conexao] = _conexoes(db)
    assert conexao.estado == ConexaoEstado.desconectada and conexao.desconectado_por == user.id
    db.expire_all()
    assert db.get(type(auto), auto.id).estado == DestinoEstado.agendado  # derivado: atenção
    modos = {m["modo"]: m for m in r.json()["conexao"]["modos"]}
    assert not modos["criar_rascunho"]["disponivel"]

    # reconectar depois de desconectar: outra linha, e o histórico mostra a sequência
    conectar(client, h, c["conta"], c["fake"])
    antiga, nova = _conexoes(db)
    assert antiga.id != nova.id and nova.estado == ConexaoEstado.conectada
    r = client.get(f"/api/contas/{c['conta']['id']}/conexao/versions", headers=h)
    assert r.status_code == 200
    itens = r.json()["items"]
    assert [i["details"]["acao"] for i in itens] == ["conectada", "desconectada", "conectada"]
    assert all(i["actor"]["name"] == "Dono" and i["actorKind"] == "user" for i in itens)
    _sem_segredo(r)


def test_desconectar_com_rede_fora_do_ar(client, db, c):
    cx = conectar(client, c["h"], c["conta"], c["fake"])["conexao"]
    c["fake"].falhar_proximo("revoke", "conexao")
    r = client.post(f"/api/contas/{c['conta']['id']}/conexao/desconectar", headers=c["h"],
                    json={"version": cx["version"]})
    assert r.status_code == 200, r.text
    assert _creds(db) == 0


def test_desconectar_conflitos(client, db, c, dono):  # noqa: F811
    user, h = dono
    url = f"/api/contas/{c['conta']['id']}/conexao/desconectar"
    r = client.post(url, headers=h, json={"version": 1})
    assert r.status_code == 409 and _err(r) == "conta_nao_conectada"
    cx = conectar(client, h, c["conta"], c["fake"])["conexao"]
    r = client.post(url, headers=h, json={"version": cx["version"] + 1})
    assert r.status_code == 409 and _err(r) == "version_conflict"
    destino_auto(db, c["perfil"]["id"], c["conta"]["id"], user, estado="enviando")
    r = client.post(url, headers=h, json={"version": cx["version"]})
    assert r.status_code == 409 and _err(r) == "envio_em_andamento"
    assert _creds(db) == 1


def test_reconectar_de_precisa_reconectar_reusa_a_linha(client, db, c):
    conectar(client, c["h"], c["conta"], c["fake"])
    [conexao] = _conexoes(db)
    conexao.estado = ConexaoEstado.precisa_reconectar
    db.delete(db.get(ConexaoCredencial, conexao.id))
    db.commit()
    # outra conta da TikTok (open_id diferente) com o mesmo @: recusada
    r = retorno(client, c["h"], c["conta"]["id"], c["fake"], "atavernanerd",
                open_id="open-impostor")
    assert r.status_code == 409 and _err(r) == "conta_diferente"
    conectar(client, c["h"], c["conta"], c["fake"])
    [mesma] = _conexoes(db)
    assert mesma.id == conexao.id and mesma.estado == ConexaoEstado.conectada
    assert _creds(db) == 1
    acoes = [v.details["acao"] for v in db.scalars(
        select(EntityVersion).where(EntityVersion.entity_id == conexao.id)
        .order_by(EntityVersion.version))]
    assert acoes == ["conectada", "reconectada"]


# ---- permissões ----

def test_membro_ve_estado_mas_nao_age(client, db, c, membro):  # noqa: F811
    _, hm = membro
    conectar(client, c["h"], c["conta"], c["fake"])
    conta_id = c["conta"]["id"]
    r = client.get(f"/api/contas/{conta_id}/conexao", headers=hm)
    assert r.status_code == 200 and r.json()["conexao"]["estado"] == "conectada"
    assert client.get(f"/api/contas/{conta_id}/conexao/versions", headers=hm).status_code == 200
    for metodo, rota, body in (
        ("POST", f"/api/contas/{conta_id}/conexao/iniciar", {}),
        ("POST", "/api/conexoes/retorno", {"state": "x", "code": "y"}),
        ("POST", f"/api/contas/{conta_id}/conexao/desconectar", {"version": 1}),
        ("GET", f"/api/contas/{conta_id}/conexao/criador", None),
    ):
        r = client.request(metodo, rota, headers={**hm, **HOST_WEB}, json=body)
        assert r.status_code == 403 and _err(r) == "somente_dono", (rota, r.text)
    assert db.scalar(select(func.count()).select_from(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")) == 0


def test_get_sem_conexao(client, c):
    r = client.get(f"/api/contas/{c['conta']['id']}/conexao", headers=c["h"])
    assert r.status_code == 200
    cx = r.json()["conexao"]
    assert cx["estado"] == "nao_conectada" and cx["version"] is None and cx["escopos"] == []
    modos = {m["modo"]: m for m in cx["modos"]}
    assert modos["criar_rascunho"]["motivo"] == "Conecte a conta"


# ---- criador (US3, T079) ----

def _criador(client, c):
    return client.get(f"/api/contas/{c['conta']['id']}/conexao/criador", headers=c["h"])


def test_criador_na_hora(client, db, c):
    conectar(client, c["h"], c["conta"], c["fake"])
    antes = len(c["fake"].pedidos("creator_info"))
    for _ in range(2):  # sem cache: cada abertura consulta
        r = _criador(client, c)
        assert r.status_code == 200, r.text
    assert len(c["fake"].pedidos("creator_info")) == antes + 2
    cr = r.json()["criador"]
    assert cr["username"] == "atavernanerd" and cr["privacyLevelOptions"] == ["SELF_ONLY"]
    assert cr["costuraDesligada"] is True and cr["duracaoMaximaS"] == 600
    assert cr["situacaoApp"] == "sandbox" and cr["podePostar"] is True
    assert cr["avatarUrl"].startswith("/img/")
    _sem_segredo(r)


def test_criador_erros(client, db, c, monkeypatch):
    r = _criador(client, c)
    assert r.status_code == 409 and _err(r) == "conta_nao_conectada"
    conectar(client, c["h"], c["conta"], c["fake"], escopos="user.info.basic,video.upload")
    r = _criador(client, c)
    assert r.status_code == 409 and _err(r) == "escopo_faltando"


def test_criador_taxa(client, c, monkeypatch):
    conectar(client, c["h"], c["conta"], c["fake"])
    from sociman_api.publicacao import limites

    monkeypatch.setitem(limites.TAXAS, "creator_info", 1)
    assert _criador(client, c).status_code == 200
    r = _criador(client, c)
    assert r.status_code == 429 and _err(r) == "tente_em_instantes"
    # a TikTok também pode recusar pela taxa
    monkeypatch.setitem(limites.TAXAS, "creator_info", 100)
    c["fake"].falhar_proximo("creator_info", "rate_limit_exceeded")
    r = _criador(client, c)
    assert r.status_code == 429 and _err(r) == "tente_em_instantes"


def test_criador_precisa_reconectar(client, db, c):
    conectar(client, c["h"], c["conta"], c["fake"])
    [conexao] = _conexoes(db)
    conexao.estado = ConexaoEstado.precisa_reconectar
    db.commit()
    r = _criador(client, c)
    assert r.status_code == 409 and _err(r) == "precisa_reconectar"
