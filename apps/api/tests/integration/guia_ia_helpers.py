"""Dados de teste do guia no assistente (spec 017, trilha B): perfil com contas e corte, o
Claude falso na rota e os guias salvos pela API do dono (`PUT …/guia`)."""

import uuid

import pytest

from integration.postagem_helpers import criar_conta, criar_corte, criar_perfil
from sociman_api.ia.cliente import get_ia_client
from sociman_api.main import app

VAZIO = {"tom": "", "faca": [], "naoFaca": [], "vocabulario": [], "proibidas": [],
         "emojis": None, "emojisPreferidos": [], "hashtagsFixas": [], "maxHashtagsFixas": None,
         "exemplos": []}


@pytest.fixture
def fake(anthropic_fake):
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    return anthropic_fake


@pytest.fixture
def cena(client, db, dono):
    user, h = dono
    perfil = criar_perfil(client, h)
    tiktok = criar_conta(client, h, perfil["id"], "tiktok", "atavernanerd")
    youtube = criar_conta(client, h, perfil["id"], "youtube", "atavernanerdyt")
    corte = criar_corte(db, perfil["id"])
    return {"user": user, "h": h, "perfil": perfil, "tiktok": tiktok, "youtube": youtube,
            "corte": corte}


def campos(**kw) -> dict:
    return VAZIO | kw


def guia_perfil(client, c, versao=None, **kw) -> dict:
    url = f"/api/perfis/{c['perfil']['id']}/guia"
    if versao is None:
        versao = client.get(url, headers=c["h"]).json()["guia"]["version"]
    r = client.put(url, headers=c["h"], json={"version": versao, "campos": campos(**kw)})
    assert r.status_code == 200, r.text
    return r.json()["guia"]


def guia_conta(client, c, conta="tiktok", versao=None, **kw) -> dict:
    url = f"/api/contas/{c[conta]['id']}/guia"
    if versao is None:
        versao = client.get(url, headers=c["h"]).json()["guia"]["version"]
    r = client.put(url, headers=c["h"], json={"version": versao, "campos": campos(**kw)})
    assert r.status_code == 200, r.text
    return r.json()["guia"]


def alvo_corte(c, conta="tiktok") -> dict:
    return {"entityType": "corte", "entityId": str(c["corte"].id), "contaId": c[conta]["id"]}


def gerar(client, c, tipo, alvo, status=200, **extra):
    body = {"tipoCampo": tipo, "perfilId": c["perfil"]["id"], "alvo": alvo,
            "sessaoId": str(uuid.uuid4())} | extra
    r = client.post("/api/ia/gerar", headers=c["h"], json=body)
    assert r.status_code == status, r.text
    return r.json()["chamada"] if status == 200 else r.json()


def avatar(client, c, **body) -> dict:
    body = {"tipo": "avatar", "name": "Ana", "prompt": "A woman in her 30s."} | body
    r = client.post(f"/api/perfis/{c['perfil']['id']}/assets", headers=c["h"], json=body)
    assert r.status_code == 201, r.text
    return r.json()["asset"]
