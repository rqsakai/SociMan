"""Guarda do princípio VII na spec 006 (T076): toda rota humana de mutação (canal, padrões de
corte, envio, corte e postagem) grava uma versão com autor e antes/depois; não existe DELETE;
`revert` do canal, dos padrões e da postagem só pelo dono; mudanças do sistema não versionam."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from integration.postagem_helpers import (  # noqa: F401
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.canais.models import CanalFonte, CanalPerfil
from sociman_api.cortes.models import CorteStatus
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.postagem import lembretes
from sociman_api.postagem.models import Postagem


def _versoes(db, tipo: str, entity_id) -> list[EntityVersion]:
    db.expire_all()
    return (db.query(EntityVersion)
            .filter_by(entity_type=tipo, entity_id=uuid.UUID(str(entity_id)))
            .order_by(EntityVersion.version).all())


def _ultima_por(db, tipo, entity_id, user, acao: str) -> EntityVersion:
    v = _versoes(db, tipo, entity_id)[-1]
    assert v.action == acao, (tipo, v.action)
    assert v.actor_kind == "user" and v.actor_user_id == user.id
    assert v.after
    if acao != "created":
        assert v.before is not None and v.changed_fields
    return v


def _ok(r, status: int = 200):
    assert r.status_code == status, r.text
    return r.json()


@pytest.fixture
def base(client, db, dono, membro):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    return {"h": h, "hm": membro[1], "perfil": perfil, "dono": dono[0], "membro": membro[0]}


def test_nenhuma_rota_delete():
    deletes = [f"{p}" for p, ops in app.openapi()["paths"].items() if "delete" in ops]
    assert not deletes, f"DELETE viola o princípio VII: {deletes}"


def test_canal_patch_archive_restore_versionam(client, db, base):
    suf = uuid.uuid4().hex[:22]
    canal = CanalFonte(youtube_channel_id=f"UC{suf}", title="Canal", uploads_playlist_id=f"UU{suf}")
    db.add(canal)
    db.flush()
    db.add(CanalPerfil(canal_id=canal.id, perfil_id=uuid.UUID(base["perfil"]["id"])))
    db.commit()
    outro = criar_perfil(client, base["h"], "Outro")
    hm, user = base["hm"], base["membro"]
    c = _ok(client.patch(f"/api/canais/{canal.id}", headers=hm,
                         json={"version": 1,
                               "perfilIds": [base["perfil"]["id"], outro["id"]]}))["canal"]
    v = _ultima_por(db, "canal", canal.id, user, "updated")
    assert "perfil_ids" in v.changed_fields
    c = _ok(client.post(f"/api/canais/{canal.id}/archive", headers=hm,
                        json={"version": c["version"]}))["canal"]
    _ultima_por(db, "canal", canal.id, user, "archived")
    _ok(client.post(f"/api/canais/{canal.id}/restore", headers=hm,
                    json={"version": c["version"]}))
    _ultima_por(db, "canal", canal.id, user, "restored")


PADROES = {"clipMinS": 15, "clipMaxS": 60, "quantidade": None, "layout": "auto",
           "formato": "vertical", "legenda": "kit", "marcaAutomatica": False,
           "contaPadraoId": None}


def test_padroes_de_corte_versionam(client, db, base):
    pid = base["perfil"]["id"]
    url = f"/api/perfis/{pid}/padroes-corte"
    p = _ok(client.put(url, headers=base["hm"], json={"version": 0, **PADROES}))["padroes"]
    rows = db.query(EntityVersion).filter_by(entity_type="padroes_corte").all()
    assert len(rows) == 1 and rows[0].action == "created"
    assert rows[0].actor_user_id == base["membro"].id
    _ok(client.put(url, headers=base["hm"],
                   json={"version": p["version"], **PADROES, "clipMaxS": 90}))
    ultima = (db.query(EntityVersion).filter_by(entity_type="padroes_corte")
              .order_by(EntityVersion.version.desc()).first())
    assert ultima.action == "updated" and ultima.actor_user_id == base["membro"].id
    assert ultima.before["clip_max_s"] == 60 and ultima.after["clip_max_s"] == 90


def test_envio_selecionar_e_descartar_versionam(client, db, base):
    hm, user = base["hm"], base["membro"]
    e = _ok(client.post(f"/api/perfis/{base['perfil']['id']}/envios", headers=hm,
                        json={"url": "https://vimeo.com/1", "titulo": "Palestra"}), 201)["envio"]
    _ultima_por(db, "envio", e["id"], user, "created")
    _ok(client.post(f"/api/envios/{e['id']}/archive", headers=hm,
                    json={"version": e["version"]}))
    v = _ultima_por(db, "envio", e["id"], user, "archived")
    assert v.after["status"] == "descartado"


def test_corte_gancho_archive_restore_versionam(client, db, base):
    hm, user = base["hm"], base["membro"]
    corte = criar_corte(db, base["perfil"]["id"], CorteStatus.revisao, hook_text="")
    c = _ok(client.patch(f"/api/cortes/{corte.id}", headers=hm,
                         json={"version": corte.version, "hookText": "Você usa isso?"}))["corte"]
    v = _ultima_por(db, "corte", corte.id, user, "updated")
    assert v.after["hook_text"] == "Você usa isso?"
    c = _ok(client.post(f"/api/cortes/{corte.id}/archive", headers=hm,
                        json={"version": c["version"]}))["corte"]
    _ultima_por(db, "corte", corte.id, user, "archived")
    _ok(client.post(f"/api/cortes/{corte.id}/restore", headers=hm,
                    json={"version": c["version"]}))
    _ultima_por(db, "corte", corte.id, user, "restored")


def test_postagem_create_patch_postado_archive_versionam(client, db, base):
    hm, user = base["hm"], base["membro"]
    conta = criar_conta(client, base["h"], base["perfil"]["id"])
    corte = criar_corte(db, base["perfil"]["id"])
    p = _ok(client.post(f"/api/cortes/{corte.id}/postagens", headers=hm,
                        json={"contaId": conta["id"]}), 201)["postagem"]
    _ultima_por(db, "postagem", p["id"], user, "created")
    p = _ok(client.patch(f"/api/postagens/{p['id']}", headers=hm,
                         json={"version": p["version"], "titulo": "Novo"}))["postagem"]
    _ultima_por(db, "postagem", p["id"], user, "updated")
    p = _ok(client.post(f"/api/postagens/{p['id']}/postado", headers=hm,
                        json={"version": p["version"]}))["postagem"]
    v = _ultima_por(db, "postagem", p["id"], user, "updated")
    assert v.before["estado"] == "rascunho" and v.after["estado"] == "postado"
    _ok(client.post(f"/api/postagens/{p['id']}/archive", headers=hm,
                    json={"version": p["version"]}))
    _ultima_por(db, "postagem", p["id"], user, "archived")


def test_revert_so_pelo_dono(client, db, base):
    """Membro recebe 403 em todas as reversões da 006 (canal, padrões e postagem)."""
    reverts = {op.get("operationId") for ops in app.openapi()["paths"].values()
               for op in ops.values()}
    assert {"canais_revert", "envios_padroes_revert", "postagens_revert"} <= reverts
    alvo = uuid.uuid4()
    corpo = {"version": 2, "toVersion": 1}
    for url in (f"/api/canais/{alvo}/revert",
                f"/api/perfis/{base['perfil']['id']}/padroes-corte/revert",
                f"/api/postagens/{alvo}/revert"):
        r = client.post(url, headers=base["hm"], json=corpo)
        assert r.status_code == 403, (url, r.text)


def test_mudanca_do_sistema_nao_versiona(client, db, base):
    """A trilha `lembretes` (estado de job) não grava versão; só as ações humanas."""
    conta = criar_conta(client, base["h"], base["perfil"]["id"])
    corte = criar_corte(db, base["perfil"]["id"])
    p = _ok(client.post(f"/api/cortes/{corte.id}/postagens", headers=base["h"],
                        json={"contaId": conta["id"],
                              "plannedAt": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}),
            201)["postagem"]
    db.query(Postagem).filter_by(id=p["id"]).update(
        {"planned_at": datetime.now(UTC) - timedelta(minutes=1)})
    db.commit()
    antes = db.query(EntityVersion).count()
    assert lembretes.rodar(db) == 1
    db.commit()
    assert db.query(EntityVersion).count() == antes
