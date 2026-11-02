"""Miniatura dos seletores com imagem (spec 031, T019, R10): o `thumbUrl` do resumo do asset é o
rosto frontal do avatar, a cena do cenário, senão a capa, senão o 1º arquivo ativo."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import (
    avatar,
    avatar_com_slots,
    cenario_com_cena,
    img,
    perfil,
    ver,
)


def _resumo(client, h, asset_id: str, tipo: str) -> dict:
    r = client.get("/api/assets", headers=h, params={"tipo": tipo})
    assert r.status_code == 200, r.text
    return next(a for a in r.json()["items"] if a["id"] == asset_id)


def _slot(a: dict, slot: str) -> dict:
    return next(f for f in a["files"] if f["slot"] == slot and not f["archived"])


def _enviar(client, h, asset_id: str, cor) -> dict:
    r = client.post(f"/api/assets/{asset_id}/arquivos", headers=h, data={"role": "referencia"},
                    files={"file": ("f.jpg", img(cor=cor), "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def test_sem_arquivo_nao_tem_miniatura(client, owner):
    h = owner[1]
    a = avatar(client, h, perfil(client, h))
    assert _resumo(client, h, a["id"], "avatar")["thumbUrl"] is None


def test_avatar_com_kit_usa_o_rosto_frontal(client, owner, motores):
    h = owner[1]
    a = avatar_com_slots(client, h, motores, perfil(client, h), n=2)
    frontal = _slot(a, "rosto_frontal")
    assert _slot(a, "rosto_origem")["image"]["id"] != frontal["image"]["id"]
    resumo = _resumo(client, h, a["id"], "avatar")
    assert resumo["thumbUrl"] == frontal["image"]["urls"]["medium"]


def test_cenario_usa_a_cena(client, owner, motores):
    h = owner[1]
    c = cenario_com_cena(client, h, motores, perfil(client, h))
    resumo = _resumo(client, h, c["id"], "cenario")
    assert resumo["thumbUrl"] == _slot(c, "cena")["image"]["urls"]["medium"]


def test_sem_kit_usa_a_capa_e_senao_o_primeiro(client, owner):
    h = owner[1]
    a = avatar(client, h, perfil(client, h))
    _enviar(client, h, a["id"], (200, 30, 30))
    a = _enviar(client, h, a["id"], (30, 200, 30))
    ativos = [f for f in a["files"] if not f["archived"]]
    capa = next((f for f in ativos if f["id"] == a["primaryFileId"]), ativos[0])
    assert _resumo(client, h, a["id"], "avatar")["thumbUrl"] == capa["image"]["urls"]["medium"]

    # trocar a capa troca a miniatura
    outro = next(f for f in ativos if f["id"] != capa["id"])
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "primaryFileId": outro["id"]})
    assert r.status_code == 200, r.text
    assert _resumo(client, h, a["id"], "avatar")["thumbUrl"] == outro["image"]["urls"]["medium"]
    assert ver(client, h, a["id"])["thumbUrl"] == outro["image"]["urls"]["medium"]
