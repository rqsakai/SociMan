"""Migração das imagens da 004 para a biblioteca (T008, research R2, SC-003) e o downgrade da
`0005_assets`."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sociman_api.assets.backfill import backfill
from sociman_api.db import get_engine
from sociman_api.perfis.models import Image, ImageKind, Perfil

API_DIR = Path(__file__).resolve().parents[2]
PW = "senha-forte-123"
KIT_KEYS = ("palette", "caption", "hook", "watermark", "endCard", "catchphrases", "series")

COUNT_BEFORE = "SELECT kind::text, count(*) FROM images WHERE kind IN ('watermark','fundo') " \
    "GROUP BY 1 ORDER BY 1"
COUNT_AFTER = "SELECT i.kind::text, count(*) FROM images i JOIN asset_files f " \
    "ON f.image_id = i.id WHERE i.kind IN ('watermark','fundo') GROUP BY 1 ORDER BY 1"
MISSING = "SELECT count(*) FROM images i LEFT JOIN asset_files f ON f.image_id = i.id " \
    "WHERE i.kind IN ('watermark','fundo') AND f.id IS NULL"


def _image(db, perfil: Perfil, kind: ImageKind, minutes: int, user_id=None) -> Image:
    """Como a 004 deixava: só a linha em `images`, sem asset."""
    img = Image(perfil_id=perfil.id, kind=kind, object_key=f"perfis/{perfil.id}/{uuid.uuid4()}.png",
                content_type="image/png", bytes=10, width=600, height=600, sha256="0" * 64,
                created_at=datetime(2026, 9, 1, tzinfo=UTC) + timedelta(minutes=minutes),
                created_by=user_id)
    db.add(img)
    return img


def _rows(sql: str) -> list[tuple]:
    with get_engine().connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def test_backfill_leva_todas_as_imagens_para_a_biblioteca(client, db, make_user, login):
    user = make_user(role="membro")
    h = login(client, user.email, PW)
    pa = Perfil(slug="queridinhos", name="Queridinhos")
    pb = Perfil(slug="taverna", name="Taverna")
    db.add_all([pa, pb])
    db.flush()
    # Fora de ordem de propósito: o nome segue a ordem de envio (created_at).
    f2 = _image(db, pa, ImageKind.fundo, 20, user.id)
    f1 = _image(db, pa, ImageKind.fundo, 10, user.id)
    w1 = _image(db, pa, ImageKind.watermark, 5)
    wb = _image(db, pb, ImageKind.watermark, 1)
    logo = _image(db, pa, ImageKind.logo, 0)  # logo e banner ficam fora (R2)
    db.commit()

    # Um kit que usa as imagens (salvo pela API, como na 004).
    kit = client.get(f"/api/perfis/{pa.id}/kit", headers=h).json()["kit"]
    body = {k: kit[k] for k in KIT_KEYS}
    body["watermark"] |= {"tipo": "imagem", "imagem_id": str(w1.id)}
    body["endCard"] |= {"ligado": True, "fundo_tipo": "imagem", "fundo_imagem_id": str(f2.id)}
    r = client.put(f"/api/perfis/{pa.id}/kit", headers=h, json={"version": 0, **body})
    assert r.status_code == 200, r.text
    kit_antes = r.json()["kit"]
    # A 004 não criava asset: remove os que o PUT não cria (nenhum) e confere a linha de base.
    assert _rows("SELECT count(*) FROM assets") == [(0,)]
    antes = _rows(COUNT_BEFORE)
    assert antes == [("fundo", 2), ("watermark", 2)]

    with get_engine().begin() as conn:
        assert backfill(conn) == 4

    assert _rows(COUNT_AFTER) == antes  # 100% na biblioteca (SC-003)
    assert _rows(MISSING) == [(0,)]
    names = _rows(
        "SELECT a.perfil_id, a.tipo::text, a.name, f.image_id, a.version, "
        "a.primary_file_id = f.id, a.created_by FROM assets a "
        "JOIN asset_files f ON f.asset_id = a.id ORDER BY a.perfil_id, a.tipo, a.name")
    by_image = {row[3]: row for row in names}
    assert by_image[f1.id][1:3] == ("fundo", "Fundo 1")
    assert by_image[f2.id][1:3] == ("fundo", "Fundo 2")
    assert by_image[w1.id][1:3] == ("marca_dagua", "Marca d'água 1")
    assert by_image[wb.id][1:3] == ("marca_dagua", "Marca d'água 1")
    assert all(row[4] == 1 and row[5] for row in names)
    assert by_image[f1.id][6] == user.id and by_image[w1.id][6] is None
    assert logo.id not in by_image

    versions = _rows("SELECT action, actor_kind, details->>'migracao', details->>'image_id', "
                     "version FROM entity_versions WHERE entity_type = 'asset'")
    assert len(versions) == 4
    assert {v[3] for v in versions} == {str(i.id) for i in (f1, f2, w1, wb)}
    assert all(v[:3] == ("created", "system:migration", "0005_assets") and v[4] == 1
               for v in versions)

    # O kit não mudou (os ids das imagens são os mesmos) e continua salvando.
    kit_depois = client.get(f"/api/perfis/{pa.id}/kit", headers=h).json()["kit"]
    for key in KIT_KEYS:
        assert kit_depois[key] == kit_antes[key]
    assert kit_depois["version"] == kit_antes["version"]
    r = client.put(f"/api/perfis/{pa.id}/kit", headers=h,
                   json={"version": kit_depois["version"],
                         **{k: kit_depois[k] for k in KIT_KEYS}})
    assert r.status_code == 200, r.text

    # A biblioteca mostra as imagens da 004, com "Em uso" nas do kit.
    items = client.get(f"/api/perfis/{pa.id}/assets", headers=h).json()["items"]
    assert sorted((a["tipo"], a["name"], a["inUse"]) for a in items) == [
        ("fundo", "Fundo 1", False), ("fundo", "Fundo 2", True),
        ("marca_dagua", "Marca d'água 1", True)]

    # Idempotente.
    with get_engine().begin() as conn:
        assert backfill(conn) == 0
    assert _rows("SELECT count(*) FROM assets") == [(4,)]


def test_backfill_continua_a_numeracao(db):
    perfil = Perfil(slug="p1", name="P1")
    db.add(perfil)
    db.flush()
    _image(db, perfil, ImageKind.fundo, 1)
    db.commit()
    with get_engine().begin() as conn:
        backfill(conn)
    _image(db, perfil, ImageKind.fundo, 2)
    db.commit()
    with get_engine().begin() as conn:
        assert backfill(conn) == 1
    assert sorted(r[0] for r in _rows("SELECT name FROM assets")) == ["Fundo 1", "Fundo 2"]


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def test_downgrade_e_upgrade(db, client, make_user, login):
    """upgrade head → downgrade 0004 → upgrade head, e a recusa com asset criado pela API."""
    db.close()
    cfg = _cfg()
    get_engine().dispose()  # nenhuma conexão ociosa segura o ALTER TYPE
    command.downgrade(cfg, "0004_fundo_imagem")
    try:
        assert _rows("SELECT to_regclass('assets')") == [(None,)]
        kinds = _rows("SELECT unnest(enum_range(NULL::image_kind))::text")
        assert [k[0] for k in kinds] == ["logo", "banner", "watermark", "fundo"]
    finally:
        get_engine().dispose()
        command.upgrade(cfg, "head")
    get_engine().dispose()

    user = make_user(role="membro")
    h = login(client, user.email, PW)
    pid = client.post("/api/perfis", json={"name": "Queridinhos", "slug": "queridinhos"},
                      headers=h).json()["perfil"]["id"]
    r = client.post(f"/api/perfis/{pid}/assets", headers=h,
                    json={"tipo": "avatar", "name": "Achadinhos"})
    assert r.status_code == 201, r.text
    get_engine().dispose()
    with pytest.raises(RuntimeError, match="o downgrade perderia dados"):
        command.downgrade(cfg, "0004_fundo_imagem")
    get_engine().dispose()
    # Nada mudou: a transação do downgrade voltou atrás.
    assert _rows("SELECT name FROM assets") == [("Achadinhos",)]
    assert client.get(f"/api/assets/{r.json()['asset']['id']}", headers=h).status_code == 200
