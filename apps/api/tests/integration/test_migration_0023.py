"""Migration 0023 (spec 025, T004): sobe sobre a 0022 com assets da 007 (as colunas novas ficam
nulas); cada CHECK e índice único recusa por INSERT direto; desce vazia e sobe; com dado novo,
o downgrade recusa."""

import json
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0022_produtos_shop"


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _perfil(conn) -> uuid.UUID:
    return conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:i, :s, 'P') "
                             "RETURNING id"),
                        {"i": uuid.uuid4(), "s": f"p{uuid.uuid4().hex[:8]}"}).scalar()


def _asset(conn, perfil, tipo="avatar", **extra) -> uuid.UUID:
    aid = uuid.uuid4()
    cols = {"id": aid, "perfil_id": perfil, "tipo": tipo, "name": "A", **extra}
    vals = ", ".join(f"CAST(:{c} AS jsonb)" if c in ("consentimento", "identidade") else
                     f"CAST(:{c} AS asset_origem)" if c == "origem" else
                     f"CAST(:{c} AS asset_tipo)" if c == "tipo" else f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO assets ({', '.join(cols)}) VALUES ({vals})"), cols)
    return aid


def _imagem(conn, perfil) -> uuid.UUID:
    iid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO images (id, perfil_id, kind, object_key, content_type, bytes, width, height, "
        "sha256) VALUES (:i, :p, 'avatar', :k, 'image/png', 1, 600, 600, 'x')"),
        {"i": iid, "p": perfil, "k": f"perfis/{perfil}/{iid}.png"})
    return iid


def _arquivo(conn, asset, imagem, role="kit", **extra) -> None:
    cols = {"id": uuid.uuid4(), "asset_id": asset, "image_id": imagem, "role": role,
            "position": 0, **extra}
    vals = ", ".join(f"CAST(:{c} AS asset_file_role)" if c == "role" else f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO asset_files ({', '.join(cols)}) VALUES ({vals})"), cols)


def _voz(conn, perfil, **extra) -> None:
    cols = {"id": uuid.uuid4(), "perfil_id": perfil, "name": f"v{uuid.uuid4().hex[:6]}",
            "origem": "gravacao", "tom": "vendas", **extra}
    vals = ", ".join(f"CAST(:{c} AS voz_origem)" if c == "origem" else
                     f"CAST(:{c} AS voz_status)" if c == "status" else f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO vozes ({', '.join(cols)}) VALUES ({vals})"), cols)


def _recusa(sql_fn) -> None:
    with pytest.raises(IntegrityError), get_engine().begin() as conn:
        sql_fn(conn)


def test_sobe_com_assets_da_007_e_desce_vazia():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "vozes")
            p = _perfil(conn)
            a = conn.execute(text("INSERT INTO assets (id, perfil_id, tipo, name, prompt) VALUES "
                                  "(:i, :p, 'avatar', 'Ana', 'woman') RETURNING id"),
                             {"i": uuid.uuid4(), "p": p}).scalar()
            conn.execute(text(
                "INSERT INTO asset_files (id, asset_id, image_id, role, position, label) VALUES "
                "(:i, :a, :img, 'pose', 0, 'apontando')"),
                {"i": uuid.uuid4(), "a": a, "img": _imagem(conn, p)})
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            assert _existe(conn, "vozes")
            linha = conn.execute(text("SELECT origem, kit_status, voz_id, identidade FROM assets"
                                      )).one()
            assert linha == (None, None, None, None)
            assert conn.execute(text("SELECT slot, geracao_id FROM asset_files")).one() == \
                (None, None)
        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not _existe(conn, "vozes")
            assert conn.execute(text("SELECT count(*) FROM asset_files")).scalar() == 1
    finally:
        command.upgrade(_cfg(), "head")


def test_checks_e_indices_recusam():
    with get_engine().begin() as conn:
        p = _perfil(conn)
        avatar = _asset(conn, p)
        cenario = _asset(conn, p, tipo="cenario")
        _arquivo(conn, avatar, _imagem(conn, p), slot="rosto_origem")
        _arquivo(conn, cenario, _imagem(conn, p), role="variacao", label="Noite")
    # Slot duplicado ativo; kit sem slot; slot desconhecido; variação sem rótulo ou repetida.
    _recusa(lambda c: _arquivo(c, avatar, _imagem(c, p), slot="rosto_origem"))
    _recusa(lambda c: _arquivo(c, avatar, _imagem(c, p)))
    _recusa(lambda c: _arquivo(c, avatar, _imagem(c, p), slot="outro"))
    _recusa(lambda c: _arquivo(c, cenario, _imagem(c, p), role="variacao"))
    _recusa(lambda c: _arquivo(c, cenario, _imagem(c, p), role="variacao", label="noite"))
    _recusa(lambda c: _arquivo(c, avatar, _imagem(c, p), role="referencia", slot="corpo_base"))
    # Pessoa real sem consentimento; campos de avatar em outro tipo; kit_status em fundo.
    _recusa(lambda c: _asset(c, p, origem="pessoa_real"))
    _recusa(lambda c: _asset(c, p, tipo="cenario", origem="upload"))
    _recusa(lambda c: _asset(c, p, tipo="fundo", kit_status="completo"))
    # Voz sintética sem descrição; gravação com descrição; aprovada sem referência.
    _recusa(lambda c: _voz(c, p, origem="sintetica"))
    _recusa(lambda c: _voz(c, p, descricao="young woman"))
    _recusa(lambda c: _voz(c, p, status="aprovada"))
    with get_engine().begin() as conn:  # os válidos passam
        _asset(conn, p, origem="pessoa_real",
               consentimento=json.dumps({"nome": "Ana", "data": "2026-10-01"}))
        _voz(conn, p, origem="sintetica", descricao="warm adult female voice")
        nome = f"Única{uuid.uuid4().hex[:4]}"
        _voz(conn, p, name=nome)
    _recusa(lambda c: _voz(c, p, name=nome.lower()))  # nome único entre as ativas


def test_downgrade_recusa_com_dados():
    with get_engine().begin() as conn:
        _voz(conn, _perfil(conn))
    with pytest.raises(RuntimeError, match="recusado"):
        command.downgrade(_cfg(), ANTERIOR)
    with get_engine().begin() as conn:
        assert _existe(conn, "vozes")
