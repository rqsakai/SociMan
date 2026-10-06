"""Prompt congelado (spec 010, T021, Q3, FR-006a): pronta congela, assets mudam sem mexer no
congelado (aviso com antes/depois), remontar recongela, editar o prompt volta a rascunho."""

# ruff: noqa: F811 — fixtures importadas de `cenas_helpers`

import uuid

from sqlalchemy import select

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    ACHADINHOS,
    _buckets,
    acao,
    base,
    criar_cena,
    get,
    owner,
    patch,
)
from sociman_api.history import EntityVersion


def _editar_avatar(client, h, avatar_id, prompt):
    asset = client.get(f"/api/assets/{avatar_id}", headers=h).json()["asset"]
    r = client.patch(f"/api/assets/{avatar_id}", headers=h,
                     json={"version": asset["version"], "prompt": prompt})
    assert r.status_code == 200, r.text
    return r.json()["asset"]


def test_pronta_congela_e_avisa_mudanca(client, db, base):
    h = base["h"]
    pronta = acao(client, h, criar_cena(client, h, base), "pronta")
    p = pronta["prompt"]
    assert pronta["status"] == "pronta" and p["congelado"] is True
    assert p["texto"].startswith(ACHADINHOS) and p["avatarVersion"] is not None

    novo = ACHADINHOS + " Smiling."
    avatar = _editar_avatar(client, h, base["avatar"]["id"], novo)
    lida = get(client, h, pronta["id"])
    assert lida["prompt"]["texto"] == p["texto"]  # o congelado não muda
    mudou = [a for a in lida["avisos"] if a["codigo"] == "assets_mudaram"]
    assert len(mudou) == 1 and mudou[0]["detalhe"]["parte"] == "avatar"
    assert mudou[0]["detalhe"]["antes"].startswith(ACHADINHOS + " ")
    assert mudou[0]["detalhe"]["depois"].startswith(novo)

    remontada = acao(client, h, lida, "remontar")
    assert remontada["status"] == "pronta"
    assert remontada["prompt"]["texto"].startswith(novo)
    assert remontada["prompt"]["avatarVersion"] == avatar["version"]
    assert not [a for a in remontada["avisos"] if a["codigo"] == "assets_mudaram"]
    ultima = db.scalars(select(EntityVersion).where(
        EntityVersion.entity_id == uuid.UUID(pronta["id"])).order_by(
        EntityVersion.version.desc())).first()
    assert ultima.details == {"acao": "remontar"}


def test_editar_prompt_volta_rascunho_e_nome_nao(client, base):
    h = base["h"]
    pronta = acao(client, h, criar_cena(client, h, base), "pronta")
    so_nome = patch(client, h, pronta, nome="Novo nome", tags=["x"], notas="obs")
    assert so_nome["status"] == "pronta" and so_nome["prompt"]["congelado"] is True
    editada = patch(client, h, so_nome, acao="opens the box")
    assert editada["status"] == "rascunho" and editada["prompt"]["congelado"] is False
    assert "opens the box" in editada["prompt"]["texto"]


def test_rascunho_explicito_e_remontar_em_rascunho(client, base):
    h = base["h"]
    cena = criar_cena(client, h, base)
    assert acao(client, h, cena, "remontar", status=409)["error"]["code"] == "cena_nao_pronta"
    assert acao(client, h, cena, "rascunho", status=409)["error"]["code"] == "conflict"
    pronta = acao(client, h, cena, "pronta")
    volta = acao(client, h, pronta, "rascunho")
    assert volta["status"] == "rascunho" and volta["prompt"]["congelado"] is False


def test_pronta_incompleta(client, base):
    h = base["h"]
    cena = criar_cena(client, h, base, modo="quadros", quadroInicial="closed pot")
    erro = acao(client, h, cena, "pronta", status=422)["error"]
    assert erro["code"] == "cena_incompleta" and erro["details"]["faltando"] == ["quadroFinal"]


def test_avatar_arquivado_impede_pronta(client, base):
    h = base["h"]
    cena = criar_cena(client, h, base)
    asset = client.get(f"/api/assets/{base['avatar']['id']}", headers=h).json()["asset"]
    r = client.post(f"/api/assets/{asset['id']}/archive", headers=h,
                    json={"version": asset["version"]})
    assert r.status_code == 200, r.text
    lida = get(client, h, cena["id"])
    assert any(a["codigo"] == "asset_arquivado" for a in lida["avisos"])
    erro = acao(client, h, lida, "pronta", status=422)["error"]
    assert "avatarId" in erro["details"]["faltando"]
