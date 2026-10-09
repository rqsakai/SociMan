"""Biblioteca de assets (T014, T023, T030, T039; contracts/http-api.md da 007): avatar com
looks e poses, cenários, atalho de envio, stickers, busca e paginação, histórico e reversão."""

import io
import uuid

import pytest
from PIL import Image as PILImage
from sqlalchemy import select

from sociman_api.config import get_settings
from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Image, ImageKind

PW = "senha-forte-123"
PROMPT = "  A cheerful 1950s pin-up style woman, red polka-dot dress…\n"


@pytest.fixture
def owner(client, make_user, login):
    user = make_user(role="dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def member(client, make_user, login):
    user = make_user(role="membro")
    return user, login(client, user.email, PW)


@pytest.fixture
def h(member):
    return member[1]


def _perfil(client, h, slug: str = "queridinhos") -> dict:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


@pytest.fixture
def perfil(client, h) -> dict:
    return _perfil(client, h)


def img(size=(300, 300), fmt: str = "JPEG", alpha: int | None = None,
        color=(30, 120, 200)) -> bytes:
    mode = "RGB" if alpha is None else "RGBA"
    buf = io.BytesIO()
    PILImage.new(mode, size, color if alpha is None else (*color, alpha)).save(buf, format=fmt)
    return buf.getvalue()


def create(client, h, perfil, **body) -> dict:
    r = client.post(f"/api/perfis/{perfil['id']}/assets", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["asset"]


def post_file(client, h, asset, data: bytes | None = None, **form):
    return client.post(f"/api/assets/{asset['id']}/arquivos", headers=h, data=form,
                       files={"file": ("f.jpg", data or img(), "application/octet-stream")})


def add_file(client, h, asset, data: bytes | None = None, **form) -> tuple[dict, dict]:
    r = post_file(client, h, asset, data, **form)
    assert r.status_code == 201, r.text
    return r.json()["asset"], r.json()["file"]


def shortcut(client, h, perfil, tipo: str, data: bytes | None = None, filename="foto.png",
             **form):
    return client.post(f"/api/perfis/{perfil['id']}/assets/arquivo", headers=h,
                       data={"tipo": tipo, **form},
                       files={"file": (filename, data or img(), "application/octet-stream")})


def get(client, h, asset) -> dict:
    r = client.get(f"/api/assets/{asset['id']}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def patch(client, h, asset, **body):
    return client.patch(f"/api/assets/{asset['id']}", headers=h,
                        json={"version": asset["version"], **body})


def versions(client, h, asset) -> list[dict]:
    r = client.get(f"/api/assets/{asset['id']}/versions", headers=h)
    assert r.status_code == 200
    return r.json()["items"]


def error(r) -> tuple[int, str, str]:
    e = r.json()["error"]
    return r.status_code, e["code"], e["message"]


# ---- US1: avatar, looks e poses ----

def test_criar_avatar(client, h, perfil, member):
    user, _ = member
    a = create(client, h, perfil, tipo="avatar", name="Achadinhos", prompt=PROMPT,
               voiceTone="Animado", imageRules="Sem texto em inglês", tags=["Persona"])
    assert a["version"] == 1 and a["tipo"] == "avatar"
    assert a["prompt"] == PROMPT  # exatamente como enviado (FR-009)
    assert (a["voiceTone"], a["imageRules"], a["tags"]) == ("Animado", "Sem texto em inglês",
                                                            ["persona"])
    assert a["cover"] is None and a["files"] == [] and a["fileCount"] == 0
    assert a["createdBy"]["id"] == str(user.id)
    [v] = versions(client, h, a)
    assert v["action"] == "created" and v["actor"]["id"] == str(user.id)
    assert v["after"]["prompt"] == PROMPT


@pytest.mark.parametrize(("tipo", "body", "field"), [
    ("cenario", {"voiceTone": "x"}, "voiceTone"),
    ("sticker", {"prompt": "x"}, "prompt"),
    ("fundo", {"imageRules": "x"}, "imageRules"),
])
def test_campos_por_tipo(client, h, perfil, tipo, body, field):
    r = client.post(f"/api/perfis/{perfil['id']}/assets", headers=h,
                    json={"tipo": tipo, "name": "x", **body})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_asset"
    assert r.json()["error"]["details"] == {"field": field}


def test_looks_poses_principal_e_ordem(client, h, perfil):
    a = create(client, h, perfil, tipo="avatar", name="Achadinhos", prompt=PROMPT)
    a, cozinha = add_file(client, h, a, img((512, 512)), role="referencia",
                          look="Cozinha, corpo inteiro", uso="cenas de cozinha",
                          notes="HeyGen look 012eb0ab")
    assert a["primaryFileId"] == cozinha["id"]  # o primeiro vira o principal
    assert a["cover"]["id"] == cozinha["image"]["id"]
    assert (cozinha["look"], cozinha["uso"], cozinha["position"]) == \
        ("Cozinha, corpo inteiro", "cenas de cozinha", 0)
    assert cozinha["link"].startswith("/api/midia/")
    assert cozinha["downloadUrl"] == cozinha["link"] + "?download=1"
    assert cozinha["previewUrl"].startswith("/img/") and cozinha["hasAlpha"] is False
    a, diner = add_file(client, h, a, img((300, 300)), role="referencia", look="Diner, busto")
    assert a["primaryFileId"] == cozinha["id"] and diner["position"] == 1

    poses = []
    for label in ("apontando para o produto", "surpresa", "piscando"):
        a, p = add_file(client, h, a, role="pose", label=label, quandoUsar="mostrar o item")
        poses.append(p)
    assert [p["position"] for p in poses] == [0, 1, 2]
    assert a["fileCount"] == 5

    # Rótulo repetido, sem diferenciar maiúsculas.
    r = post_file(client, h, a, role="pose", label="Surpresa")
    assert error(r) == (409, "pose_label_in_use", "Já existe uma pose com esse rótulo neste avatar")

    # Trocar o principal.
    r = patch(client, h, a, primaryFileId=diner["id"])
    assert r.status_code == 200, r.text
    a = r.json()["asset"]
    assert a["cover"]["id"] == diner["image"]["id"]
    r = patch(client, h, a, primaryFileId=str(uuid.uuid4()))
    assert error(r)[:2] == (400, "invalid_asset")

    # Reordenar: "piscando" para o início.
    order = [poses[2]["id"], poses[0]["id"], poses[1]["id"]]
    r = client.put(f"/api/assets/{a['id']}/ordem", headers=h,
                   json={"version": a["version"], "role": "pose", "fileIds": order})
    assert r.status_code == 200, r.text
    a = r.json()["asset"]
    got = [f["id"] for f in sorted((f for f in a["files"] if f["role"] == "pose"),
                                   key=lambda f: f["position"])]
    assert got == order
    assert get(client, h, a)["asset"]["version"] == a["version"]
    # Lista incompleta.
    r = client.put(f"/api/assets/{a['id']}/ordem", headers=h,
                   json={"version": a["version"], "role": "pose", "fileIds": order[:2]})
    assert error(r) == (400, "invalid_asset",
                        "fileIds: a lista precisa ter todos os arquivos ativos")


@pytest.mark.parametrize(("form", "field"), [
    ({"role": "arquivo"}, "role"),
    ({"role": "pose", "label": "x", "look": "Cozinha"}, "look"),
    ({"role": "referencia", "label": "x"}, "label"),
    ({"role": "pose"}, "label"),
])
def test_arquivo_invalido(client, h, perfil, form, field):
    a = create(client, h, perfil, tipo="avatar", name="A")
    r = post_file(client, h, a, **form)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_asset"
    assert r.json()["error"]["details"] == {"field": field}


def test_editar_pose_e_restaurar_com_rotulo_em_uso(client, h, perfil):
    a = create(client, h, perfil, tipo="avatar", name="A")
    a, p1 = add_file(client, h, a, role="pose", label="piscando")
    a, p2 = add_file(client, h, a, role="pose", label="surpresa")
    r = client.patch(f"/api/assets/{a['id']}/arquivos/{p2['id']}", headers=h,
                     json={"version": a["version"], "label": "PISCANDO"})
    assert error(r)[:2] == (409, "pose_label_in_use")
    r = client.patch(f"/api/assets/{a['id']}/arquivos/{p2['id']}", headers=h,
                     json={"version": a["version"], "quandoUsar": "reação"})
    assert r.status_code == 200, r.text
    a = r.json()["asset"]

    r = client.post(f"/api/assets/{a['id']}/arquivos/{p1['id']}/archive", headers=h,
                    json={"version": a["version"]})
    assert r.status_code == 200, r.text
    a = r.json()["asset"]
    # O principal passou para o primeiro ativo; a ordem ficou sem buracos.
    assert a["primaryFileId"] == p2["id"]
    assert next(f for f in a["files"] if f["id"] == p2["id"])["position"] == 0
    a, _ = add_file(client, h, a, role="pose", label="Piscando")
    r = client.post(f"/api/assets/{a['id']}/arquivos/{p1['id']}/restore", headers=h,
                    json={"version": a["version"]})
    assert error(r)[:2] == (409, "pose_label_in_use")


def test_restaurar_arquivo_volta_ao_fim(client, h, perfil):
    a = create(client, h, perfil, tipo="cenario", name="Cozinha retrô", prompt="1950s kitchen")
    a, r1 = add_file(client, h, a, img((600, 600)), role="referencia")
    a, r2 = add_file(client, h, a, img((600, 600)), role="referencia")
    a = client.post(f"/api/assets/{a['id']}/arquivos/{r1['id']}/archive", headers=h,
                    json={"version": a["version"]}).json()["asset"]
    a = client.post(f"/api/assets/{a['id']}/arquivos/{r1['id']}/restore", headers=h,
                    json={"version": a["version"]}).json()["asset"]
    pos = {f["id"]: f["position"] for f in a["files"]}
    assert (pos[r2["id"]], pos[r1["id"]]) == (0, 1)
    assert a["primaryFileId"] == r2["id"]


def test_version_conflict_e_asset_arquivado(client, h, perfil):
    a = create(client, h, perfil, tipo="avatar", name="A")
    r = patch(client, h, a, name="B")
    assert r.status_code == 200
    r = patch(client, h, a, name="C")  # versão velha
    assert error(r) == (409, "version_conflict",
                        "Este asset foi alterado por outra pessoa; recarregue")
    a = r2 = client.post(f"/api/assets/{a['id']}/archive", headers=h,
                         json={"version": 2}).json()["asset"]
    assert r2["archived"] is True
    r = patch(client, h, a, name="D")
    assert error(r) == (409, "asset_archived", "Restaure o asset antes de editar")
    assert error(post_file(client, h, a, role="pose", label="x"))[:2] == (409, "asset_archived")
    a = client.post(f"/api/assets/{a['id']}/restore", headers=h,
                    json={"version": a["version"]}).json()["asset"]
    assert a["archived"] is False and a["version"] == 4
    assert [v["action"] for v in versions(client, h, a)] == \
        ["restored", "archived", "updated", "created"]


def test_patch_sem_mudanca_nao_grava_versao(client, h, perfil):
    a = create(client, h, perfil, tipo="avatar", name="A", prompt="p")
    r = patch(client, h, a, name="A", prompt="p")
    assert r.json()["asset"]["version"] == 1
    r = patch(client, h, a, prompt=None)  # nulo limpa o campo
    assert r.json()["asset"]["prompt"] is None and r.json()["asset"]["version"] == 2
    r = client.patch(f"/api/assets/{a['id']}", headers=h, json={"version": 2, "tipo": "fundo"})
    assert r.status_code == 400


def test_perfil_arquivado(client, h, perfil):
    a = create(client, h, perfil, tipo="avatar", name="A")
    r = client.post(f"/api/perfis/{perfil['id']}/archive", headers=h,
                    json={"version": perfil["version"]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/perfis/{perfil['id']}/assets", headers=h,
                    json={"tipo": "avatar", "name": "B"})
    assert error(r)[:2] == (409, "perfil_archived")
    # Spec 029 (FR-010): o item de um perfil base arquivado continua editável.
    r = patch(client, h, a, name="B")
    assert r.status_code == 200 and r.json()["asset"]["name"] == "B"


def test_hd_fora(client, h, perfil, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    a = create(client, h, perfil, tipo="avatar", name="Sem HD")  # só banco: funciona
    assert error(post_file(client, h, a, role="pose", label="x"))[:2] == \
        (503, "storage_unavailable")
    assert error(shortcut(client, h, perfil, "imagem"))[:2] == (503, "storage_unavailable")


def test_hd_sem_espaco(client, h, perfil, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**9)
    a = create(client, h, perfil, tipo="avatar", name="A")
    assert error(post_file(client, h, a, role="pose", label="x"))[:2] == (507, "storage_full")


# ---- histórico e reversão (princípio VII) ----

def test_reversao_so_dono_e_arquiva_arquivo_novo(client, owner, member, perfil, db):
    _, ho = owner
    _, hm = member
    a = create(client, hm, perfil, tipo="avatar", name="Achadinhos")
    a, p1 = add_file(client, hm, a, role="pose", label="piscando")
    a, p2 = add_file(client, hm, a, role="pose", label="surpresa")
    v3 = a["version"]
    a = client.put(f"/api/assets/{a['id']}/ordem", headers=hm,
                   json={"version": a["version"], "role": "pose",
                         "fileIds": [p2["id"], p1["id"]]}).json()["asset"]
    a, p3 = add_file(client, hm, a, role="pose", label="apontando")

    r = client.post(f"/api/assets/{a['id']}/revert", headers=hm,
                    json={"version": a["version"], "toVersion": v3})
    assert r.status_code == 403
    r = client.post(f"/api/assets/{a['id']}/revert", headers=ho,
                    json={"version": a["version"], "toVersion": v3})
    assert r.status_code == 200, r.text
    a = r.json()["asset"]
    files = {f["id"]: f for f in a["files"]}
    assert files[p1["id"]]["position"] == 0 and files[p2["id"]]["position"] == 1
    assert files[p3["id"]]["archived"] is True  # não existia na v3: arquivado, nunca apagado
    assert db.get(Image, uuid.UUID(p3["image"]["id"])) is not None
    [last, *_] = versions(client, ho, a)
    assert last["action"] == "reverted" and last["details"] == {"from_version": v3}

    r = client.post(f"/api/assets/{a['id']}/revert", headers=ho,
                    json={"version": a["version"], "toVersion": a["version"] - 1})
    assert r.status_code == 200  # volta a ordem nova e restaura a pose
    a = r.json()["asset"]
    r = client.post(f"/api/assets/{a['id']}/revert", headers=ho,
                    json={"version": a["version"], "toVersion": a["version"] - 2})
    assert error(r) == (400, "validation_error", "Essa versão é igual à atual")


def _mutations(client, h, perfil) -> tuple[list, dict]:
    """Cada mutação de asset, na ordem, com a ação esperada no histórico."""
    state: dict = {}

    def cur():
        return state["a"]

    def run(fn, action):
        def _step():
            r = fn()
            assert r.status_code in (200, 201), r.text
            state["a"] = r.json()["asset"]
            return action
        return _step

    def created():
        return client.post(f"/api/perfis/{perfil['id']}/assets", headers=h,
                           json={"tipo": "avatar", "name": "A"})

    return [
        run(created, "created"),
        run(lambda: patch(client, h, cur(), name="B"), "updated"),
        run(lambda: post_file(client, h, cur(), role="pose", label="x"), "updated"),
        run(lambda: post_file(client, h, cur(), role="pose", label="y"), "updated"),
        run(lambda: client.patch(
            f"/api/assets/{cur()['id']}/arquivos/{cur()['files'][0]['id']}", headers=h,
            json={"version": cur()["version"], "notes": "n"}), "updated"),
        run(lambda: client.put(f"/api/assets/{cur()['id']}/ordem", headers=h, json={
            "version": cur()["version"], "role": "pose",
            "fileIds": [f["id"] for f in reversed(cur()["files"])]}), "updated"),
        run(lambda: client.post(
            f"/api/assets/{cur()['id']}/arquivos/{cur()['files'][0]['id']}/archive",
            headers=h, json={"version": cur()["version"]}), "updated"),
        run(lambda: client.post(
            f"/api/assets/{cur()['id']}/arquivos/{cur()['files'][-1]['id']}/restore",
            headers=h, json={"version": cur()["version"]}), "updated"),
        run(lambda: client.post(f"/api/assets/{cur()['id']}/archive", headers=h,
                                json={"version": cur()["version"]}), "archived"),
        run(lambda: client.post(f"/api/assets/{cur()['id']}/restore", headers=h,
                                json={"version": cur()["version"]}), "restored"),
    ], state


def test_toda_mutacao_gera_versao_com_autor(client, member, perfil, db):
    user, h = member
    steps, state = _mutations(client, h, perfil)
    for i, step in enumerate(steps, start=1):
        action = step()
        a = state["a"]
        assert a["version"] == i
        row = db.scalar(select(EntityVersion).where(
            EntityVersion.entity_type == "asset", EntityVersion.entity_id == uuid.UUID(a["id"]),
            EntityVersion.version == i))
        assert row is not None and row.action == action
        assert row.actor_user_id == user.id and row.actor_kind == "user"
        assert row.changed_fields
        if action != "created":
            assert row.before is not None and row.before != row.after
        db.expire_all()


# ---- US2: cenários e atalho de envio ----

def test_cenario(client, h, perfil):
    a = create(client, h, perfil, tipo="cenario", name="Cozinha retrô",
               prompt="1950s kitchen with mint-green countertops", tags=["cozinha"])
    a, ref = add_file(client, h, a, img((600, 600)), role="referencia", uso="cenas")
    assert a["cover"]["id"] == ref["image"]["id"]
    r = post_file(client, h, a, img((600, 600)), role="pose", label="x")
    assert error(r)[:2] == (400, "invalid_asset")
    r = post_file(client, h, a, img((600, 600)), role="referencia", look="x")
    assert error(r)[:2] == (400, "invalid_asset")
    r = post_file(client, h, a, img((500, 500)), role="referencia")
    assert error(r) == (400, "invalid_image", "Imagem pequena demais")


def test_atalho_um_arquivo_um_asset(client, h, perfil, db):
    r = shortcut(client, h, perfil, "fundo", img((600, 800)), filename="Pôr do sol.jpg",
                 tags="Praia, verão ,praia")
    assert r.status_code == 201, r.text
    a, f = r.json()["asset"], r.json()["file"]
    assert (a["tipo"], a["name"], a["tags"], a["version"]) == \
        ("fundo", "Pôr do sol", ["praia", "verão"], 1)
    assert a["primaryFileId"] == f["id"] and f["role"] == "arquivo"
    assert db.get(Image, uuid.UUID(f["image"]["id"])).kind == ImageKind.fundo

    r = shortcut(client, h, perfil, "imagem", img((64, 64)), name="Selo")
    assert r.json()["asset"]["name"] == "Selo"
    for tipo in ("avatar", "cenario"):
        assert error(shortcut(client, h, perfil, tipo))[:2] == (400, "invalid_asset")
    # Tipo de um arquivo só.
    r = post_file(client, h, a, img((600, 600)), role="arquivo")
    assert error(r) == (400, "invalid_asset", "file: este tipo aceita um arquivo só")
    r = client.post(f"/api/assets/{a['id']}/arquivos/{f['id']}/archive", headers=h,
                    json={"version": a["version"]})
    assert error(r) == (400, "invalid_asset", "file: este tipo tem um arquivo só; arquive o asset")


def test_imagens_da_biblioteca_para_os_seletores(client, h, perfil):
    fundo = shortcut(client, h, perfil, "fundo", img((600, 600))).json()["asset"]
    cen = create(client, h, perfil, tipo="cenario", name="Cozinha retrô", tags=["cozinha"])
    cen, ref = add_file(client, h, cen, img((600, 600)), role="referencia")
    shortcut(client, h, perfil, "sticker", img((100, 100), "PNG", alpha=0))
    arquivado = shortcut(client, h, perfil, "fundo", img((600, 600))).json()["asset"]
    client.post(f"/api/assets/{arquivado['id']}/archive", headers=h,
                json={"version": arquivado["version"]})

    r = client.get(f"/api/perfis/{perfil['id']}/assets/imagens?tipo=fundo&tipo=cenario",
                   headers=h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["assetId"] for i in items] == [cen["id"], fundo["id"]]  # mais recentes primeiro
    assert items[0]["fileId"] == ref["id"] and items[0]["assetTipo"] == "cenario"
    r = client.get(f"/api/perfis/{perfil['id']}/assets/imagens?tipo=fundo&tipo=cenario"
                   "&q=cozinha", headers=h)
    assert [i["assetId"] for i in r.json()["items"]] == [cen["id"]]
    r = client.get(f"/api/perfis/{perfil['id']}/assets/imagens?tipo=marca_dagua&tipo=sticker",
                   headers=h)
    [st] = r.json()["items"]
    assert st["assetTipo"] == "sticker" and st["hasAlpha"] is True
    assert client.get(f"/api/perfis/{perfil['id']}/assets/imagens",
                      headers=h).status_code == 400  # tipo obrigatório


# ---- US3: stickers, filtros, busca e paginação ----

@pytest.mark.parametrize(("tipo", "data", "message"), [
    ("sticker", img((128, 128)), "O sticker precisa ter fundo transparente"),
    ("sticker", img((128, 128), "PNG", alpha=255), "O sticker precisa ter fundo transparente"),
    ("marca_dagua", img((128, 128), "PNG"), "A imagem precisa ter fundo transparente"),
    ("imagem", b"texto renomeado para png", "Formato não aceito"),
])
def test_transparencia_e_formato(client, h, perfil, tipo, data, message):
    assert error(shortcut(client, h, perfil, tipo, data)) == (400, "invalid_image", message)


def test_filtros_busca_e_tags(client, h, perfil):
    def st(name, tags):
        r = shortcut(client, h, perfil, "sticker", img((100, 100), "PNG", alpha=0), name=name,
                     tags=tags)
        assert r.status_code == 201, r.text
        return r.json()["asset"]

    a1 = st("Uau", "reação")
    a2 = st("Oferta", "promo")
    a3 = st("Uau promo", "reação,promo")
    fundo = shortcut(client, h, perfil, "fundo", img((600, 600)), name="Praia").json()["asset"]
    outro = _perfil(client, h, "outro")
    shortcut(client, h, outro, "sticker", img((100, 100), "PNG", alpha=0), tags="promo")

    def ids(query: str) -> list[str]:
        r = client.get(f"/api/perfis/{perfil['id']}/assets{query}", headers=h)
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["items"]]

    assert ids("") == [fundo["id"], a3["id"], a2["id"], a1["id"]]
    assert ids("?tag=promo") == [a3["id"], a2["id"]]
    assert ids("?tag=promo&tag=reação") == [a3["id"]]  # E lógico
    assert ids("?tipo=fundo&tipo=imagem") == [fundo["id"]]  # OU
    assert ids("?q=uau") == [a3["id"], a1["id"]]  # nome contém
    assert ids("?q=PROMO") == [a3["id"], a2["id"]]  # nome contém ou tag igual
    r = client.get(f"/api/perfis/{perfil['id']}/assets", headers=h).json()
    assert r["tags"] == [{"tag": "promo", "count": 2}, {"tag": "reação", "count": 2}]
    assert r["nextCursor"] is None

    client.post(f"/api/assets/{a1['id']}/archive", headers=h, json={"version": 1})
    assert ids("") == [fundo["id"], a3["id"], a2["id"]]
    assert ids("?archived=true") == [a1["id"]]
    assert set(ids("?archived=all")) == {fundo["id"], a1["id"], a2["id"], a3["id"]}
    summary = client.get(f"/api/perfis/{perfil['id']}/assets?archived=true",
                         headers=h).json()["items"][0]
    assert summary["archived"] is True and summary["fileCount"] == 1
    assert summary["cover"] is not None and summary["inUse"] is False


def test_paginacao_por_cursor(client, h, perfil):
    created = [create(client, h, perfil, tipo="avatar", name=f"A{i}")["id"] for i in range(7)]
    seen, cursor = [], None
    while True:
        q = "?limit=3" + (f"&cursor={cursor}" if cursor else "")
        r = client.get(f"/api/perfis/{perfil['id']}/assets{q}", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        seen += [i["id"] for i in body["items"]]
        cursor = body["nextCursor"]
        if cursor is None:
            break
    assert seen == list(reversed(created))  # sem repetir nem pular
    r = client.get(f"/api/perfis/{perfil['id']}/assets?cursor=lixo", headers=h)
    assert r.status_code == 400
    assert client.get(f"/api/perfis/{perfil['id']}/assets?limit=101", headers=h
                      ).status_code == 400


def test_sem_login_e_inexistentes(client, h, perfil):
    assert client.get(f"/api/perfis/{perfil['id']}/assets").status_code == 401
    assert client.get(f"/api/perfis/{uuid.uuid4()}/assets", headers=h).status_code == 404
    assert client.get(f"/api/assets/{uuid.uuid4()}", headers=h).status_code == 404
    assert client.get(f"/api/assets/{uuid.uuid4()}/versions", headers=h).status_code == 404
