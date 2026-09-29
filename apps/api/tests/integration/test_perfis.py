"""US1: API de perfis (T009, contracts/http-api.md "Perfis")."""

import pytest
from sqlalchemy import select

from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Conta, ContaStatus, Image, ImageKind, Perfil, Platform


@pytest.fixture
def member(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, "senha-forte-123")


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, "senha-forte-123")


def _create(client, headers, **overrides):
    body = {"name": "Queridinhos", "slug": "queridinhos", "niche": "Achadinhos de beleza + casa",
            "language": "pt-BR"} | overrides
    r = client.post("/api/perfis", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _versions(db, perfil_id):
    db.expire_all()
    return db.scalars(
        select(EntityVersion).where(EntityVersion.entity_type == "perfil",
                                    EntityVersion.entity_id == perfil_id)
        .order_by(EntityVersion.version)
    ).all()


def test_sem_sessao_da_401(client):
    assert client.get("/api/perfis").status_code == 401
    assert client.post("/api/perfis", json={"name": "X", "slug": "xx"}).status_code == 401
    assert client.get("/api/perfis/slug-suggestion", params={"name": "X"}).status_code == 401


def test_criar_perfil_como_membro(client, member, db):
    user, h = member
    p = _create(client, h)
    assert p["slug"] == "queridinhos"
    assert p["status"] == "em_preparacao"
    assert p["version"] == 1
    assert p["archived"] is False and p["archivedAt"] is None
    assert p["logo"] is None and p["banner"] is None
    assert p["platforms"] == []
    assert p["createdBy"] == {"id": str(user.id), "name": "Membro"}
    assert p["updatedBy"] == {"id": str(user.id), "name": "Membro"}

    [v] = _versions(db, p["id"])
    assert v.version == 1 and v.action == "created"
    assert v.actor_kind == "user" and v.actor_user_id == user.id
    assert v.before is None
    assert v.after["name"] == "Queridinhos" and v.after["slug"] == "queridinhos"
    assert v.after["archived"] is False
    assert set(v.changed_fields) == set(v.after)


def test_criar_valida_campos(client, member):
    _, h = member
    assert client.post("/api/perfis", json={"name": "X", "slug": "Com Espaço"},
                       headers=h).status_code == 400
    assert client.post("/api/perfis", json={"name": "  ", "slug": "ok"},
                       headers=h).status_code == 400
    r = client.post("/api/perfis", json={"name": "X", "slug": "xx", "language": "portugues"},
                    headers=h)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"


def test_slug_duplicado_da_409(client, member):
    _, h = member
    _create(client, h)
    r = client.post("/api/perfis", json={"name": "Outro", "slug": "queridinhos"}, headers=h)
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "slug_in_use",
                                 "message": "Já existe um perfil com esse identificador"}


def test_slug_sugerido(client, member):
    _, h = member
    r = client.get("/api/perfis/slug-suggestion", params={"name": "A Taverna Nerd"}, headers=h)
    assert r.status_code == 200
    assert r.json() == {"slug": "a-taverna-nerd"}
    r = client.get("/api/perfis/slug-suggestion", params={"name": "Achadinhos da Lú!"},
                   headers=h)
    assert r.json() == {"slug": "achadinhos-da-lu"}
    # Já em uso: sugere o próximo livre.
    _create(client, h, name="A Taverna Nerd", slug="a-taverna-nerd")
    r = client.get("/api/perfis/slug-suggestion", params={"name": "A Taverna Nerd"}, headers=h)
    assert r.json() == {"slug": "a-taverna-nerd-2"}


def test_listar_busca_e_filtros(client, member):
    _, h = member
    _create(client, h, name="Queridinhos", slug="queridinhos")
    _create(client, h, name="A Taverna Nerd", slug="taverna", status="ativo")
    _create(client, h, name="Cortes 100%", slug="cortes")

    r = client.get("/api/perfis", headers=h)
    assert r.status_code == 200
    assert [p["name"] for p in r.json()["items"]] == ["A Taverna Nerd", "Cortes 100%",
                                                     "Queridinhos"]

    r = client.get("/api/perfis", params={"q": "taVERna"}, headers=h)
    assert [p["slug"] for p in r.json()["items"]] == ["taverna"]
    # % é literal na busca, não curinga.
    r = client.get("/api/perfis", params={"q": "100%"}, headers=h)
    assert [p["slug"] for p in r.json()["items"]] == ["cortes"]
    r = client.get("/api/perfis", params={"q": "%"}, headers=h)
    assert [p["slug"] for p in r.json()["items"]] == ["cortes"]

    r = client.get("/api/perfis", params={"status": "ativo"}, headers=h)
    assert [p["slug"] for p in r.json()["items"]] == ["taverna"]
    assert client.get("/api/perfis", params={"status": "xyz"}, headers=h).status_code == 400


def test_obter_perfil_com_contas_e_plataformas(client, member, db):
    user, h = member
    p = _create(client, h)
    db.add_all([
        Conta(perfil_id=p["id"], platform=Platform.tiktok, handle="queridinhos",
              url="https://www.tiktok.com/@queridinhos", status=ContaStatus.ativa,
              created_by=user.id, updated_by=user.id),
        Conta(perfil_id=p["id"], platform=Platform.youtube, handle="queridinhos",
              url="https://www.youtube.com/@queridinhos", status=ContaStatus.planejada),
    ])
    db.commit()

    r = client.get(f"/api/perfis/{p['id']}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["perfil"]["id"] == p["id"]
    assert body["perfil"]["platforms"] == ["tiktok"]  # só as contas ativas
    assert {c["platform"] for c in body["contas"]} == {"tiktok", "youtube"}
    tiktok = next(c for c in body["contas"] if c["platform"] == "tiktok")
    assert tiktok["createdBy"] == {"id": str(user.id), "name": "Membro"}
    assert tiktok["archived"] is False

    r = client.get("/api/perfis", headers=h)
    assert r.json()["items"][0]["platforms"] == ["tiktok"]


def test_saida_com_logo_e_banner(client, member, db):
    user, h = member
    p = _create(client, h)
    logo = Image(perfil_id=p["id"], kind=ImageKind.logo, object_key=f"perfis/{p['id']}/a.png",
                 content_type="image/png", bytes=10, width=400, height=400, sha256="x",
                 created_by=user.id)
    banner = Image(perfil_id=p["id"], kind=ImageKind.banner,
                   object_key=f"perfis/{p['id']}/b.jpg", content_type="image/jpeg", bytes=10,
                   width=1500, height=500, sha256="y", created_by=user.id)
    db.add_all([logo, banner])
    db.flush()
    perfil = db.get(Perfil, p["id"])
    perfil.logo_image_id, perfil.banner_image_id = logo.id, banner.id
    db.commit()

    out = client.get(f"/api/perfis/{p['id']}", headers=h).json()["perfil"]
    assert out["logo"]["id"] == str(logo.id)
    assert (out["logo"]["width"], out["logo"]["height"]) == (400, 400)
    assert out["logo"]["urls"]["thumb"].startswith("/img/")
    assert "/rs:fit:96:96/" in out["logo"]["urls"]["thumb"]
    assert "/rs:fit:256:256/" in out["logo"]["urls"]["medium"]
    assert "/rs:fit:1200:300/" in out["banner"]["urls"]["medium"]
    listed = client.get("/api/perfis", headers=h).json()["items"][0]
    assert listed["logo"]["id"] == str(logo.id)


def test_obter_inexistente_da_404(client, member):
    _, h = member
    missing = "00000000-0000-0000-0000-000000000000"
    for path in (f"/api/perfis/{missing}", f"/api/perfis/{missing}/versions"):
        r = client.get(path, headers=h)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
    r = client.patch(f"/api/perfis/{missing}", json={"version": 1, "bio": "x"}, headers=h)
    assert r.status_code == 404


def test_editar_perfil_gera_versao(client, member, owner, db):
    creator, h = member
    editor, h2 = owner
    p = _create(client, h)
    r = client.patch(f"/api/perfis/{p['id']}",
                     json={"version": 1, "bio": "Nova bio", "status": "ativo"}, headers=h2)
    assert r.status_code == 200, r.text
    out = r.json()["perfil"]
    assert out["bio"] == "Nova bio" and out["status"] == "ativo"
    assert out["niche"] == "Achadinhos de beleza + casa"  # não enviado, não muda
    assert out["version"] == 2
    assert out["createdBy"]["id"] == str(creator.id)
    assert out["updatedBy"] == {"id": str(editor.id), "name": "Dono"}

    v = _versions(db, p["id"])[-1]
    assert v.version == 2 and v.action == "updated" and v.actor_user_id == editor.id
    assert v.before["bio"] == "" and v.after["bio"] == "Nova bio"
    assert v.before["status"] == "em_preparacao" and v.after["status"] == "ativo"
    assert sorted(v.changed_fields) == ["bio", "status"]

    # A lista reflete o novo status.
    r = client.get("/api/perfis", params={"status": "ativo"}, headers=h)
    assert [x["id"] for x in r.json()["items"]] == [p["id"]]


def test_editar_sem_mudanca_nao_gera_versao(client, member, db):
    _, h = member
    p = _create(client, h)
    r = client.patch(f"/api/perfis/{p['id']}", json={"version": 1, "name": "Queridinhos"},
                     headers=h)
    assert r.status_code == 200
    assert r.json()["perfil"]["version"] == 1
    assert len(_versions(db, p["id"])) == 1


def test_slug_no_patch_da_400(client, member):
    _, h = member
    p = _create(client, h)
    r = client.patch(f"/api/perfis/{p['id']}", json={"version": 1, "slug": "outro"}, headers=h)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation_error"
    assert client.get(f"/api/perfis/{p['id']}", headers=h).json()["perfil"]["slug"] == \
        "queridinhos"


def test_patch_com_versao_velha_da_409(client, member, db):
    _, h = member
    p = _create(client, h)
    assert client.patch(f"/api/perfis/{p['id']}", json={"version": 1, "bio": "a"},
                        headers=h).status_code == 200
    r = client.patch(f"/api/perfis/{p['id']}", json={"version": 1, "bio": "b"}, headers=h)
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "version_conflict",
        "message": "Este perfil foi alterado por outra pessoa; recarregue",
    }
    assert len(_versions(db, p["id"])) == 2
    assert client.patch(f"/api/perfis/{p['id']}", json={"bio": "c"}, headers=h).status_code \
        == 400  # version é obrigatório


def test_arquivar_e_restaurar(client, member, db):
    user, h = member
    p = _create(client, h)
    r = client.post(f"/api/perfis/{p['id']}/archive", json={"version": 1}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()["perfil"]
    assert out["archived"] is True and out["archivedAt"] is not None and out["version"] == 2

    assert client.get("/api/perfis", headers=h).json()["items"] == []
    r = client.get("/api/perfis", params={"archived": "true"}, headers=h)
    assert [x["id"] for x in r.json()["items"]] == [p["id"]]
    # Arquivado continua acessível pelo id.
    assert client.get(f"/api/perfis/{p['id']}", headers=h).json()["perfil"]["archived"] is True

    # Versão velha e arquivar de novo são recusados.
    r = client.post(f"/api/perfis/{p['id']}/restore", json={"version": 1}, headers=h)
    assert r.json()["error"]["code"] == "version_conflict"
    r = client.post(f"/api/perfis/{p['id']}/archive", json={"version": 2}, headers=h)
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "conflict", "message": "Este perfil já está arquivado"}

    r = client.post(f"/api/perfis/{p['id']}/restore", json={"version": 2}, headers=h)
    assert r.status_code == 200
    assert r.json()["perfil"]["archived"] is False and r.json()["perfil"]["version"] == 3
    assert [x["id"] for x in client.get("/api/perfis", headers=h).json()["items"]] == [p["id"]]
    assert client.get("/api/perfis", params={"archived": "true"}, headers=h).json()["items"] \
        == []
    r = client.post(f"/api/perfis/{p['id']}/restore", json={"version": 3}, headers=h)
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "conflict", "message": "Este perfil não está arquivado"}

    archived, restored = _versions(db, p["id"])[1:]
    assert archived.action == "archived" and archived.changed_fields == ["archived"]
    assert archived.before["archived"] is False and archived.after["archived"] is True
    assert archived.actor_user_id == user.id
    assert restored.action == "restored" and restored.changed_fields == ["archived"]
    assert restored.after["archived"] is False


def test_versions_da_mais_recente_para_a_mais_antiga(client, member, owner):
    creator, h = member
    editor, h2 = owner
    p = _create(client, h)
    client.patch(f"/api/perfis/{p['id']}", json={"version": 1, "bio": "x"}, headers=h2)
    client.post(f"/api/perfis/{p['id']}/archive", json={"version": 2}, headers=h)

    r = client.get(f"/api/perfis/{p['id']}/versions", headers=h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [(v["version"], v["action"]) for v in items] == [
        (3, "archived"), (2, "updated"), (1, "created")]
    assert items[1]["actor"] == {"id": str(editor.id), "name": "Dono"}
    assert items[1]["actorKind"] == "user"
    assert items[1]["changedFields"] == ["bio"]
    assert items[1]["before"]["bio"] == "" and items[1]["after"]["bio"] == "x"
    assert items[2]["before"] is None
    assert items[0]["actor"]["id"] == str(creator.id)
    assert items[0]["details"] == {}


def test_senha_provisoria_bloqueia(client, make_user, login):
    user = make_user(must_change=True)
    h = login(client, user.email, "senha-forte-123")
    r = client.get("/api/perfis", headers=h)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "password_change_required"


def test_nenhuma_rota_delete_de_perfis(client):
    spec = client.get("/api/openapi.json").json()
    for path, ops in spec["paths"].items():
        if path.startswith("/api/perfis"):
            assert "delete" not in ops, path
