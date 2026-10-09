"""Perfil base na geração e no assistente (spec 029, T020; US2, research R4 e R14): o
`perfilBaseId` com 3 estados (ausente = o do item, `null` = nenhum, um id = aquele) é gravado em
`geracoes.perfil_id` e `ia_chamadas.perfil_id`, o item não muda, perfil arquivado → 409, e as
rotas antigas por perfil continuam (o perfil do caminho é o padrão)."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

import pytest
from fakes.anthropic_fake import anthropic_fake, texto  # noqa: F401
from fakes.shoptts_fake import wav_sintetico
from sqlalchemy import select

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    acao,
    asset,
    detalhe,
    member,
    montar,
    motores,
    owner,
)
from integration.padrao_helpers import avatar_com_slots, com_claude, geracao
from sociman_api.geracao.models import Audio, Geracao
from sociman_api.ia.cliente import get_ia_client
from sociman_api.ia.models import IaChamada, IaDesfecho
from sociman_api.main import app


@pytest.fixture
def fake(anthropic_fake):
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    return anthropic_fake


def _perfil(client, h, slug: str) -> dict:
    r = client.post("/api/perfis", headers=h, json={"name": slug.title(), "slug": slug})
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _arquivar(client, h, perfil: dict) -> None:
    r = client.post(f"/api/perfis/{perfil['id']}/archive", headers=h,
                    json={"version": perfil["version"]})
    assert r.status_code == 200, r.text


def _guia(client, h, perfil_id: str, **campos) -> None:
    r = client.put(f"/api/perfis/{perfil_id}/guia", headers=h,
                   json={"version": 0, "campos": campos})
    assert r.status_code == 200, r.text


def _pedir(client, h, b: dict, status: int = 201, **kw) -> dict:
    corpo = {"alvoTipo": "asset", "alvoId": b["cenario"]["id"], "passo": "cenario.cena",
             "instrucao": "cozy bright bedroom, morning sun", "nOpcoes": 1} | kw
    r = client.post("/api/geracoes", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def _db_geracao(db, gid: str) -> Geracao:
    g = db.get(Geracao, uuid.UUID(gid))
    db.refresh(g)
    return g


# ---- geração (021/025) ----

def test_perfil_base_ausente_null_e_outro(client, owner, motores, db):
    h = owner[1]
    b = montar(client, h, slug="aaa")
    outro = _perfil(client, h, "bbb")
    ausente = _pedir(client, h, b)
    assert ausente["perfilId"] == b["perfil_id"] and ausente["perfilNome"] == "Aaa"
    acao(client, h, ausente, "cancelar")
    nenhum = _pedir(client, h, b, perfilBaseId=None)
    assert nenhum["perfilId"] is None and nenhum["perfilNome"] is None
    acao(client, h, nenhum, "cancelar")
    com_b = _pedir(client, h, b, perfilBaseId=outro["id"])
    assert com_b["perfilId"] == outro["id"] and com_b["perfilNome"] == "Bbb"
    assert _db_geracao(db, com_b["id"]).perfil_id == uuid.UUID(outro["id"])
    assert asset(client, h, b["cenario"]["id"])["perfilId"] == b["perfil_id"]  # o item não muda

    # A lista do item traz as três, de qualquer perfil base; a antiga, só as do perfil.
    r = client.get("/api/geracoes", headers=h,
                   params={"alvoTipo": "asset", "alvoId": b["cenario"]["id"]})
    assert r.status_code == 200, r.text
    assert {g["id"] for g in r.json()["itens"]} == {ausente["id"], nenhum["id"], com_b["id"]}
    r = client.get(f"/api/perfis/{outro['id']}/geracoes", headers=h)
    assert [g["id"] for g in r.json()["itens"]] == [com_b["id"]]
    assert client.get("/api/geracoes", headers=h).status_code == 400  # o alvo é obrigatório


def test_perfil_base_arquivado_ou_inexistente(client, owner, motores):
    h = owner[1]
    b = montar(client, h, slug="aaa")
    outro = _perfil(client, h, "bbb")
    _arquivar(client, h, outro)
    erro = _pedir(client, h, b, status=409, perfilBaseId=outro["id"])
    assert erro["error"]["code"] == "perfil_base_arquivado"
    erro = _pedir(client, h, b, status=400, perfilBaseId=str(uuid.uuid4()))
    assert erro["error"]["code"] == "perfil_invalido"
    assert erro["error"]["details"]["field"] == "perfilBaseId"


def test_item_sem_perfil_gera_sem_perfil_e_imagem_da_agencia(client, owner, motores, db):
    from integration.geracao_helpers import rodar_gpu
    from sociman_api.perfis.models import Image

    h = owner[1]
    r = client.post("/api/assets", headers=h,
                    json={"tipo": "cenario", "name": "Sala", "prompt": "living room",
                          "perfilId": None})
    assert r.status_code == 201, r.text
    cenario = r.json()["asset"]
    g = _pedir(client, h, {"cenario": cenario})
    assert g["perfilId"] is None
    rodar_gpu(motores)
    d = detalhe(client, h, g["id"])
    assert d["status"] == "revisao", d
    img = db.get(Image, uuid.UUID(d["candidatos"][0]["imagem"]["imageId"]))
    assert img.perfil_id is None and img.object_key.startswith("agencia/imagens/")


def test_rota_antiga_usa_o_perfil_do_caminho(client, owner, motores):
    h = owner[1]
    b = montar(client, h, slug="aaa")
    outro = _perfil(client, h, "bbb")
    corpo = {"alvoTipo": "asset", "alvoId": b["cenario"]["id"], "passo": "cenario.cena",
             "instrucao": "cozy bedroom", "nOpcoes": 1}
    r = client.post(f"/api/perfis/{outro['id']}/geracoes", headers=h, json=corpo)
    assert r.status_code == 201, r.text
    assert r.json()["perfilId"] == outro["id"]
    acao(client, h, r.json(), "cancelar")
    r = client.post(f"/api/perfis/{outro['id']}/geracoes", headers=h,
                    json=corpo | {"perfilBaseId": None})
    assert r.status_code == 201 and r.json()["perfilId"] is None
    acao(client, h, r.json(), "cancelar")
    _arquivar(client, h, outro)
    r = client.post(f"/api/perfis/{outro['id']}/geracoes", headers=h, json=corpo)
    assert r.status_code == 409 and r.json()["error"]["code"] == "perfil_archived"


def test_identidade_usa_as_proibidas_do_perfil_base(client, owner, motores, db):
    h = owner[1]
    a_id = _perfil(client, h, "aaa")["id"]
    b_id = _perfil(client, h, "bbb")["id"]
    _guia(client, h, b_id, proibidas=["beauty"])
    com_claude(motores)
    a = avatar_com_slots(client, h, motores, a_id)  # perfil A, sem proibidas: aplica
    assert a["kitStatus"] == "completo" and a["prompt"]
    antes = a["prompt"]
    r = client.post("/api/geracoes", headers=h,
                    json={"alvoTipo": "asset", "alvoId": a["id"], "passo": "avatar.identidade",
                          "instrucao": "", "perfilBaseId": b_id})
    assert r.status_code == 201, r.text
    motores.linha_claude().volta()
    assert geracao(client, h, r.json()["id"])["perfilId"] == b_id
    depois = asset(client, h, a["id"])
    assert depois["prompt"] == antes  # a nova descrição (com "beauty mark") não entrou
    assert depois["kit"]["descricaoNaoAplicada"] == {"proibidas": ["beauty"]}
    row = db.scalar(select(IaChamada).where(IaChamada.geracao_id == uuid.UUID(r.json()["id"])))
    assert row.perfil_id == uuid.UUID(b_id) and row.proibidas == ["beauty"]


def test_criar_para_alvo_com_perfil_base(db, owner, client):
    from sociman_api.auth.deps import Actor
    from sociman_api.errors import ApiError
    from sociman_api.geracao import service
    from sociman_api.geracao.models import GeracaoAlvo
    from sociman_api.perfis.models import Perfil

    user, h = owner
    b = montar(client, h, slug="aaa")
    outro = _perfil(client, h, "bbb")
    actor = Actor(kind="user", user_id=user.id)
    params = {"instrucao": "x", "referencias": [], "rotulo": None, "texto": None,
              "extras": None, "bloco": "cena", "prompt": "x"}
    pid, cid = uuid.UUID(b["perfil_id"]), uuid.UUID(b["cenario"]["id"])
    g = service.criar_para_alvo(db, actor, pid, "cenario.cena", GeracaoAlvo.asset, cid, params)
    assert g.perfil_id == pid
    g = service.criar_para_alvo(db, actor, pid, "cenario.cena", GeracaoAlvo.asset, cid, params,
                                perfil_base=None)
    assert g.perfil_id is None
    db.get(Perfil, uuid.UUID(outro["id"])).archived_at = db.get(Perfil, pid).created_at
    with pytest.raises(ApiError) as exc:
        service.criar_para_alvo(db, actor, pid, "cenario.cena", GeracaoAlvo.asset, cid, params,
                                perfil_base=uuid.UUID(outro["id"]))
    assert exc.value.code == "perfil_base_arquivado"
    db.rollback()


# ---- áudio sem perfil (T008) ----

def test_audio_da_agencia(client, owner, db):
    h = owner[1]
    wav = wav_sintetico(segundos=1.0)
    r = client.post("/api/audios", headers=h,
                    files={"arquivo": ("voz.wav", wav, "application/octet-stream")})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["perfilId"] is None
    assert db.get(Audio, uuid.UUID(a["id"])).object_key.startswith("agencia/audios/")
    p = _perfil(client, h, "aaa")
    r = client.post("/api/audios", headers=h, data={"perfilId": p["id"]},
                    files={"arquivo": ("voz.wav", wav, "application/octet-stream")})
    assert r.status_code == 201 and r.json()["perfilId"] == p["id"]
    r = client.post("/api/audios", headers=h, data={"perfilId": str(uuid.uuid4())},
                    files={"arquivo": ("voz.wav", wav, "application/octet-stream")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "perfil_invalido"


# ---- assistente (008/017) ----

def _avatar(client, h, perfil_id: str | None, name: str = "Ana") -> dict:
    r = client.post("/api/assets", headers=h,
                    json={"tipo": "avatar", "name": name, "prompt": "A woman, 30s",
                          "perfilId": perfil_id})
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def _gerar(client, h, avatar: dict, **extra):
    body = {"tipoCampo": "avatar.tom_de_voz",
            "alvo": {"entityType": "asset", "entityId": avatar["id"]},
            "valorAtual": {"texto": "Animada"}, "instrucao": "", "sessaoId": str(uuid.uuid4()),
            **extra}
    return client.post("/api/ia/gerar", headers=h, json=body)


def test_ia_com_perfil_base_b_e_sem_perfil(client, owner, fake, db):
    h = owner[1]
    a_id = _perfil(client, h, "aaa")["id"]
    b_id = _perfil(client, h, "bbb")["id"]
    _guia(client, h, b_id, tom="Divertido e leve", proibidas=["barato"])
    avatar = _avatar(client, h, a_id)
    r = _gerar(client, h, avatar, perfilBaseId=b_id)
    assert r.status_code == 200, r.text
    ch = r.json()["chamada"]
    assert ch["perfilId"] == b_id and ch["perfilNome"] == "Bbb" and ch["guiaPerfilVersion"] == 1
    system = fake.systems[-1]
    assert '<guia_perfil versao="1">' in system and "Perfil: Bbb" in system

    r = _gerar(client, h, avatar, perfilBaseId=None)
    assert r.status_code == 200, r.text
    ch = r.json()["chamada"]
    assert ch["perfilId"] is None and ch["perfil"] is None and ch["guiaPerfilVersion"] is None
    system = fake.systems[-1]
    assert "<guia_perfil versao" not in system and "Perfil: " not in system
    assert fake.system_blocos[-1][-1]["cache_control"] == {"type": "ephemeral"}

    sem = _avatar(client, h, None, name="Bia")
    r = _gerar(client, h, sem)  # ausente num item sem perfil = nenhum
    assert r.status_code == 200 and r.json()["chamada"]["perfilId"] is None
    row = db.get(IaChamada, uuid.UUID(r.json()["chamada"]["id"]))
    assert row.perfil_id is None


def test_ia_perfil_base_arquivado(client, owner, fake):
    h = owner[1]
    a = _perfil(client, h, "aaa")
    avatar = _avatar(client, h, a["id"])
    _arquivar(client, h, a)
    r = _gerar(client, h, avatar)
    assert r.status_code == 409 and r.json()["error"]["code"] == "perfil_base_arquivado"
    r = _gerar(client, h, avatar, perfilBaseId=None)
    assert r.status_code == 200, r.text


def test_aplicar_sugestao_gerada_com_outro_perfil_base(client, owner, fake, db):
    """C1: gerar com B num item de A e aplicar no save → 200 e desfecho `aplicada`."""
    h = owner[1]
    a_id = _perfil(client, h, "aaa")["id"]
    b_id = _perfil(client, h, "bbb")["id"]
    avatar = _avatar(client, h, a_id)
    fake.responder(texto("Leve e direta"))
    r = _gerar(client, h, avatar, perfilBaseId=b_id)
    assert r.status_code == 200, r.text
    ch = r.json()["chamada"]
    r = client.patch(f"/api/assets/{avatar['id']}", headers=h,
                     json={"version": avatar["version"], "voiceTone": "Leve e direta",
                           "ia": [{"tipoCampo": "avatar.tom_de_voz", "chamadaId": ch["id"]}]})
    assert r.status_code == 200, r.text
    assert db.get(IaChamada, uuid.UUID(ch["id"])).desfecho == IaDesfecho.aplicada


def test_campos_do_perfil_continuam_exigindo_o_perfil(client, owner, fake):
    h = owner[1]
    p = _perfil(client, h, "aaa")
    body = {"tipoCampo": "perfil.bio", "alvo": {"entityType": "perfil", "entityId": p["id"]},
            "valorAtual": {"texto": ""}, "instrucao": "", "sessaoId": str(uuid.uuid4())}
    r = client.post("/api/ia/gerar", headers=h, json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_ia"
    r = client.post("/api/ia/gerar", headers=h, json=body | {"perfilId": p["id"]})
    assert r.status_code == 200, r.text


def test_resumo_de_custo_tem_sem_perfil(client, owner, fake):
    h = owner[1]
    a_id = _perfil(client, h, "aaa")["id"]
    assert _gerar(client, h, _avatar(client, h, a_id)).status_code == 200
    assert _gerar(client, h, _avatar(client, h, None, name="Bia")).status_code == 200
    r = client.get("/api/ia/resumo", headers=h)
    assert r.status_code == 200, r.text
    linhas = {(p["perfil"] or {}).get("name"): p["chamadas"] for p in r.json()["porPerfil"]}
    assert linhas == {"Aaa": 1, None: 1}
    r = client.get("/api/ia/chamadas", headers=h)
    assert r.status_code == 200, r.text
    assert {c["perfilNome"] for c in r.json()["items"]} == {"Aaa", None}
