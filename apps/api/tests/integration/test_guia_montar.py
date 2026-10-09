"""Montar o guia com a IA (spec 017, T041; US3, research R9): a proposta cabe nos limites, não
salva nada, e o save do dono com `ia` marca a chamada (`aplicada`/`editada`, `details.ia`)."""

import uuid
from datetime import UTC, datetime

from fakes.anthropic_fake import anthropic_fake, guia  # noqa: F401
from sqlalchemy import select, update

from integration.guia_ia_helpers import cena, fake, guia_perfil  # noqa: F401
from integration.postagem_helpers import dono, membro  # noqa: F401
from sociman_api.history import EntityVersion
from sociman_api.ia.models import IaChamada, IaDesfecho
from sociman_api.perfis.models import Conta


def _montar(client, c, h=None, status=200, **extra):
    body = {"perfilId": c["perfil"]["id"], "descricao": "perfil nerd de RPG, fala como amigo",
            "sessaoId": str(uuid.uuid4())} | extra
    r = client.post("/api/ia/guia/montar", headers=h or c["h"], json=body)
    assert r.status_code == status, r.text
    return r.json()["chamada"] if status == 200 else r.json()


def _desfecho(db, cid) -> IaDesfecho:
    db.expire_all()
    return db.get(IaChamada, uuid.UUID(cid)).desfecho


def _versao(db, entity_id) -> EntityVersion:
    db.expire_all()
    return db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "ia_guia", EntityVersion.entity_id == uuid.UUID(entity_id))
        .order_by(EntityVersion.version.desc()).limit(1)).one()


def test_proposta_dentro_dos_limites_sem_salvar(client, cena, fake):  # noqa: F811
    c = cena
    fake.responder(guia(faca=[f"Regra {i}" for i in range(12)]),
                   guia(faca=[f"Regra {i}" for i in range(12)]))
    ch = _montar(client, c)
    g = ch["proposta"]["guia"]
    assert ch["tipoCampo"] == "guia.montar" and ch["alvo"]["entityType"] == "guia"
    assert len(g["faca"]) == 10 and g["proibidas"] == ["clickbait"] and g["emojis"] == "moderado"
    assert g["hashtagsFixas"] == [] and g["exemplos"] == [] and g["maxHashtagsFixas"] is None
    assert ch["instrucao"] == "perfil nerd de RPG, fala como amigo"
    assert "<instrucao>\nperfil nerd de RPG" in fake.bodies[0]["messages"][0]["content"]
    r = client.get(f"/api/perfis/{c['perfil']['id']}/guia", headers=c["h"])
    assert r.json()["guia"]["version"] == 0


def test_salvar_com_ia_editado_marca_a_chamada(client, db, cena, fake):  # noqa: F811
    c = cena
    ch = _montar(client, c)
    campos = dict(ch["proposta"]["guia"]) | {"tom": "Ajustado pelo dono.",
                                             "hashtagsFixas": ["#taverna"]}
    r = client.put(f"/api/perfis/{c['perfil']['id']}/guia", headers=c["h"],
                   json={"version": 0, "campos": campos,
                         "ia": [{"tipoCampo": "guia.montar", "chamadaId": ch["id"]}]})
    assert r.status_code == 200, r.text
    g = r.json()["guia"]
    assert _desfecho(db, ch["id"]) == IaDesfecho.editada
    assert _versao(db, g["id"]).details == {"ia": [{
        "campo": "tom,faca,nao_faca,vocabulario,proibidas,emojis,emojis_preferidos",
        "tipoCampo": "guia.montar", "chamadaId": ch["id"], "desfecho": "editada"}]}


def test_salvar_igual_a_proposta_fica_aplicada(client, db, cena, fake):  # noqa: F811
    c = cena
    ch = _montar(client, c)
    r = client.put(f"/api/perfis/{c['perfil']['id']}/guia", headers=c["h"],
                   json={"version": 0, "campos": ch["proposta"]["guia"],
                         "ia": [{"tipoCampo": "guia.montar", "chamadaId": ch["id"]}]})
    assert r.status_code == 200, r.text
    assert _desfecho(db, ch["id"]) == IaDesfecho.aplicada


def test_membro_nao_monta(client, cena, membro, fake):  # noqa: F811
    body = _montar(client, cena, h=membro[1], status=403)
    assert body["error"]["code"] == "forbidden" and not fake.requests


def test_guia_da_conta_leva_o_do_perfil_como_referencia(client, db, cena, fake):  # noqa: F811
    c = cena
    guia_perfil(client, c, tom="Nerd e acolhedor")
    ch = _montar(client, c, contaId=c["tiktok"]["id"])
    assert ch["guiaPerfilVersion"] == 1 and ch["alvo"]["entityType"] == "guia"
    system = fake.systems[0]
    assert '<guia_perfil versao="1">' in system and "Nerd e acolhedor" in system
    assert "a conta TikTok @atavernanerd" in fake.bodies[0]["messages"][0]["content"]

    campos = dict(ch["proposta"]["guia"])
    r = client.put(f"/api/contas/{c['tiktok']['id']}/guia", headers=c["h"],
                   json={"version": 0, "campos": campos,
                         "ia": [{"tipoCampo": "guia.montar", "chamadaId": ch["id"]}]})
    assert r.status_code == 200, r.text
    assert _desfecho(db, ch["id"]) == IaDesfecho.aplicada


def test_chamada_do_perfil_nao_marca_o_guia_da_conta(client, db, cena, fake):  # noqa: F811
    c = cena
    ch = _montar(client, c)  # guia do perfil
    r = client.put(f"/api/contas/{c['tiktok']['id']}/guia", headers=c["h"],
                   json={"version": 0, "campos": ch["proposta"]["guia"],
                         "ia": [{"tipoCampo": "guia.montar", "chamadaId": ch["id"]}]})
    assert r.status_code == 200, r.text
    assert _desfecho(db, ch["id"]) == IaDesfecho.sem_acao


def test_conta_arquivada(client, db, cena, fake):  # noqa: F811
    c = cena
    db.execute(update(Conta).where(Conta.id == uuid.UUID(c["tiktok"]["id"]))
               .values(archived_at=datetime.now(UTC)))
    db.commit()
    body = _montar(client, c, status=409, contaId=c["tiktok"]["id"])
    assert body["error"]["code"] == "conflict" and not fake.requests


def test_tipos_listam_o_montar_e_nao_o_testar(client, cena):  # noqa: F811
    ids = [t["id"] for t in client.get("/api/ia/tipos", headers=cena["h"]).json()["items"]]
    assert "guia.montar" in ids and "guia.testar" not in ids
    r = client.put("/api/ia/tipos/guia.testar/regras", headers=cena["h"],
                   json={"version": 0, "texto": "outra regra"})
    assert r.status_code == 404
