"""US4: reversão pelo dono (T017, FR-013; contracts/http-api.md "Reversão")."""

import uuid

import pytest
from sqlalchemy import select

from sociman_api import history
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.perfis.models import Conta, Image, ImageKind, Perfil

PW = "senha-forte-123"


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def member(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


def _perfil(client, h, **overrides) -> dict:
    body = {"name": "Queridinhos", "slug": "queridinhos", "bio": "bio original"} | overrides
    r = client.post("/api/perfis", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _patch_perfil(client, h, p: dict, **body) -> dict:
    r = client.patch(f"/api/perfis/{p['id']}", json={"version": p["version"], **body}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["perfil"]


def _conta(client, h, perfil: dict, **body) -> dict:
    r = client.post(f"/api/perfis/{perfil['id']}/contas", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["conta"]


def _patch_conta(client, h, c: dict, **body) -> dict:
    r = client.patch(f"/api/contas/{c['id']}", json={"version": c["version"], **body}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["conta"]


def _revert(client, h, kind: str, obj: dict, to_version: int, version: int | None = None):
    body = {"version": obj["version"] if version is None else version, "toVersion": to_version}
    return client.post(f"/api/{kind}/{obj['id']}/revert", json=body, headers=h)


def _versions(db, entity_type: str, entity_id: str) -> list[EntityVersion]:
    db.expire_all()
    return list(db.scalars(
        select(EntityVersion).where(EntityVersion.entity_type == entity_type,
                                    EntityVersion.entity_id == uuid.UUID(entity_id))
        .order_by(EntityVersion.version)
    ))


def _tamper_v1(db, entity_id: str, **fields) -> None:
    """Adultera o snapshot da v1 (só teste: a aplicação nunca altera uma versão)."""
    row = db.scalar(select(EntityVersion).where(EntityVersion.entity_id == uuid.UUID(entity_id),
                                                EntityVersion.version == 1))
    row.after = {**row.after, **fields}
    db.commit()


# ---- perfil ----

def test_dono_reverte_perfil_para_v1(client, owner, member, db):
    _, h = member
    p = _perfil(client, h)
    p = _patch_perfil(client, h, p, bio="bio nova", niche="casa")
    p = _patch_perfil(client, h, p, name="Queridinhos 2", status="ativo")

    r = _revert(client, owner[1], "perfis", p, 1)
    assert r.status_code == 200, r.text
    out = r.json()["perfil"]
    assert (out["name"], out["bio"], out["niche"], out["status"]) == (
        "Queridinhos", "bio original", "", "em_preparacao")
    assert out["version"] == 4
    assert out["updatedBy"] == {"id": str(owner[0].id), "name": "Dono"}

    rows = _versions(db, "perfil", p["id"])
    assert [v.action for v in rows] == ["created", "updated", "updated", "reverted"]
    reverted = rows[-1]
    assert reverted.details == {"from_version": 1}
    assert reverted.actor_user_id == owner[0].id
    assert reverted.after == rows[0].after
    assert set(reverted.changed_fields) == {"name", "niche", "bio", "status"}

    # O histórico da API mostra a reversão, e as versões intermediárias continuam lá.
    items = client.get(f"/api/perfis/{p['id']}/versions", headers=h).json()["items"]
    assert [(v["version"], v["action"]) for v in items] == [
        (4, "reverted"), (3, "updated"), (2, "updated"), (1, "created")]
    assert items[0]["details"] == {"from_version": 1}


def test_reversao_nunca_muda_o_slug(client, owner, db):
    _, h = owner
    p = _perfil(client, h)
    p = _patch_perfil(client, h, p, bio="outra")
    # Mesmo que o snapshot traga outro slug (só informativo), a reversão o ignora.
    _tamper_v1(db, p["id"], slug="slug-antigo")

    r = _revert(client, h, "perfis", p, 1)
    assert r.status_code == 200, r.text
    assert r.json()["perfil"]["slug"] == "queridinhos"
    assert r.json()["perfil"]["bio"] == "bio original"
    db.expire_all()
    assert db.get(Perfil, uuid.UUID(p["id"])).slug == "queridinhos"


def test_reverter_perfil_arquivado_para_versao_nao_arquivada_restaura(client, owner, db):
    _, h = owner
    p = _perfil(client, h)
    p = _patch_perfil(client, h, p, bio="v2")
    r = client.post(f"/api/perfis/{p['id']}/archive", json={"version": 2}, headers=h)
    p = r.json()["perfil"]
    assert p["archived"] is True

    r = _revert(client, h, "perfis", p, 2)
    assert r.status_code == 200, r.text
    out = r.json()["perfil"]
    assert out["archived"] is False and out["archivedAt"] is None and out["bio"] == "v2"
    db.expire_all()
    row = db.get(Perfil, uuid.UUID(p["id"]))
    assert row.archived_at is None and row.archived_by is None
    assert [x["id"] for x in client.get("/api/perfis", headers=h).json()["items"]] == [p["id"]]

    # E o caminho inverso: voltar para a versão arquivada arquiva de novo.
    r = _revert(client, h, "perfis", out, 3)
    assert r.status_code == 200, r.text
    assert r.json()["perfil"]["archived"] is True


def _image(db, perfil_id: str, kind: ImageKind = ImageKind.logo) -> Image:
    img = Image(perfil_id=uuid.UUID(perfil_id), kind=kind, object_key=f"teste/{uuid.uuid4()}",
                content_type="image/png", bytes=10, width=512, height=512, sha256="0" * 64)
    db.add(img)
    db.flush()
    return img


class _System:
    kind = "system:cli"
    user_id = None


def _set_logo(db, perfil_id: str, image_id: uuid.UUID | None) -> None:
    """Troca o logo direto no banco, com versão (as rotas de imagem são de outra tarefa)."""
    perfil = db.get(Perfil, uuid.UUID(perfil_id))
    before = history.snapshot(perfil)
    perfil.logo_image_id = image_id
    history.record(db, _System(), "perfil", perfil, "updated", before, history.snapshot(perfil))
    db.commit()


def test_reversao_traz_o_logo_de_volta(client, owner, db):
    _, h = owner
    p = _perfil(client, h)
    primeiro = _image(db, p["id"])
    _set_logo(db, p["id"], primeiro.id)  # v2
    segundo = _image(db, p["id"])
    _set_logo(db, p["id"], segundo.id)  # v3

    r = _revert(client, h, "perfis", {"id": p["id"], "version": 3}, 2)
    assert r.status_code == 200, r.text
    assert r.json()["perfil"]["logo"]["id"] == str(primeiro.id)

    r = _revert(client, h, "perfis", {"id": p["id"], "version": 4}, 1)
    assert r.status_code == 200, r.text
    assert r.json()["perfil"]["logo"] is None


def test_reversao_com_imagem_de_outro_perfil_da_409(client, owner, db):
    _, h = owner
    p = _perfil(client, h)
    outro = _perfil(client, h, name="Outro", slug="outro")
    alheia = _image(db, outro["id"])
    db.commit()
    # Snapshot adulterado: a v1 apontaria para a imagem de outro perfil.
    _patch_perfil(client, h, p, bio="v2")
    _tamper_v1(db, p["id"], logo_image_id=str(alheia.id))

    r = _revert(client, h, "perfis", {"id": p["id"], "version": 2}, 1)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "revert_conflict"
    assert len(_versions(db, "perfil", p["id"])) == 2


# ---- recusas comuns ----

def test_membro_nao_reverte(client, owner, member):
    _, h = member
    p = _perfil(client, h)
    p = _patch_perfil(client, h, p, bio="x")
    c = _conta(client, h, p, platform="tiktok", handle="a")
    c = _patch_conta(client, h, c, notes="x")

    for kind, obj in (("perfis", p), ("contas", c)):
        r = _revert(client, h, kind, obj, 1)
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "forbidden"
    # Sem sessão: 401.
    assert _revert(client, {}, "perfis", p, 1).status_code == 401


def test_to_version_inexistente_ou_atual(client, owner):
    _, h = owner
    p = _perfil(client, h)
    p = _patch_perfil(client, h, p, bio="x")

    r = _revert(client, h, "perfis", p, 9)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

    r = _revert(client, h, "perfis", p, 2)
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "validation_error", "message": "Já é a versão atual"}

    r = client.post(f"/api/perfis/{p['id']}/revert", json={"version": 2, "toVersion": 0},
                    headers=h)
    assert r.status_code == 400

    fantasma = {"id": str(uuid.uuid4()), "version": 1}
    assert _revert(client, h, "perfis", fantasma, 1).status_code == 404
    assert _revert(client, h, "contas", fantasma, 1).status_code == 404


def test_versao_atual_velha_da_409(client, owner, db):
    _, h = owner
    p = _perfil(client, h)
    p = _patch_perfil(client, h, p, bio="x")
    r = _revert(client, h, "perfis", p, 1, version=1)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "version_conflict"

    c = _conta(client, h, p, platform="tiktok", handle="a")
    c = _patch_conta(client, h, c, notes="x")
    r = _revert(client, h, "contas", c, 1, version=1)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "version_conflict"
    assert len(_versions(db, "perfil", p["id"])) == 2


# ---- conta ----

def test_dono_reverte_conta(client, owner, member, db):
    _, h = member
    p = _perfil(client, h)
    c = _conta(client, h, p, platform="tiktok", handle="antigo", notes="n1")
    c = _patch_conta(client, h, c, handle="novo", status="ativa", notes="n2")

    r = _revert(client, owner[1], "contas", c, 1)
    assert r.status_code == 200, r.text
    out = r.json()["conta"]
    assert (out["handle"], out["url"], out["status"], out["notes"]) == (
        "antigo", "https://www.tiktok.com/@antigo", "planejada", "n1")
    assert out["version"] == 3
    assert out["updatedBy"]["name"] == "Dono"

    rows = _versions(db, "conta", c["id"])
    assert [v.action for v in rows] == ["created", "updated", "reverted"]
    assert rows[-1].details == {"from_version": 1}
    assert rows[-1].after == rows[0].after


def test_reverter_conta_para_arroba_de_outra_da_409(client, owner, db):
    _, h = owner
    p = _perfil(client, h)
    c = _conta(client, h, p, platform="tiktok", handle="disputado")
    c = _patch_conta(client, h, c, handle="provisorio")
    outro = _perfil(client, h, name="Achadinhos", slug="achadinhos")
    _conta(client, h, outro, platform="tiktok", handle="disputado")

    r = _revert(client, h, "contas", c, 1)
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "handle_in_use",
                                 "message": "Esse @ já pertence ao perfil Achadinhos"}
    db.expire_all()
    assert db.get(Conta, uuid.UUID(c["id"])).handle == "provisorio"
    assert len(_versions(db, "conta", c["id"])) == 2


def test_reverter_conta_para_segunda_ativa_da_409(client, owner, db):
    _, h = owner
    p = _perfil(client, h)
    c = _conta(client, h, p, platform="tiktok", handle="principal", status="ativa")
    c = _patch_conta(client, h, c, status="pausada")
    _conta(client, h, p, platform="tiktok", handle="reserva", status="ativa")

    r = _revert(client, h, "contas", c, 1)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "active_platform_exists"
    assert len(_versions(db, "conta", c["id"])) == 2


def test_reverter_conta_arquivada_restaura(client, owner):
    _, h = owner
    p = _perfil(client, h)
    c = _conta(client, h, p, platform="youtube", handle="canal")
    r = client.post(f"/api/contas/{c['id']}/archive", json={"version": 1}, headers=h)
    c = r.json()["conta"]
    assert c["archived"] is True

    r = _revert(client, h, "contas", c, 1)
    assert r.status_code == 200, r.text
    assert r.json()["conta"]["archived"] is False


# ---- nada é apagado (SC-006) ----

def test_no_delete_routes():
    for path, ops in app.openapi()["paths"].items():
        assert "delete" not in ops, path
