"""Migration 0024 (spec 029, T004): sobe sobre a 0023 sem mudar o perfil dos itens; desduplica as
vozes ativas com o mesmo nome em perfis diferentes (sufixo " (2)" + versão `system:migration`); o
nome passa a ser único na agência; o downgrade recusa com item sem perfil."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0023_cadastro_padronizado"


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _perfil(conn) -> uuid.UUID:
    return conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:i, :s, 'P') "
                             "RETURNING id"),
                        {"i": uuid.uuid4(), "s": f"p{uuid.uuid4().hex[:8]}"}).scalar()


def _voz(conn, perfil, nome, criada="2026-10-01T10:00:00+00:00") -> uuid.UUID:
    return conn.execute(text(
        "INSERT INTO vozes (id, perfil_id, name, origem, tom, status, version, created_at) VALUES "
        "(:i, :p, :n, 'gravacao', 't', 'rascunho', 1, :c) RETURNING id"),
        {"i": uuid.uuid4(), "p": perfil, "n": nome, "c": criada}).scalar()


def test_sobe_desduplica_vozes_e_desce():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            a, b = _perfil(conn), _perfil(conn)
            v1 = _voz(conn, a, "Ana vendas")
            v2 = _voz(conn, b, "ana VENDAS", criada="2026-10-02T10:00:00+00:00")  # a mais nova
            asset = conn.execute(text("INSERT INTO assets (id, perfil_id, tipo, name) VALUES "
                                      "(:i, :p, 'avatar', 'Ana') RETURNING id"),
                                 {"i": uuid.uuid4(), "p": a}).scalar()
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            nomes = dict(conn.execute(text("SELECT id, name FROM vozes")).all())
            assert nomes[v1] == "Ana vendas" and nomes[v2] == "ana VENDAS (2)"
            ver = conn.execute(text(
                "SELECT version, actor_kind, after->>'name', details->>'motivo' FROM entity_versions "
                "WHERE entity_id = :v"), {"v": v2}).one()
            assert ver == (2, "system:migration", "ana VENDAS (2)", "nome_unico_029")
            assert conn.execute(text("SELECT perfil_id FROM assets WHERE id = :i"),
                                {"i": asset}).scalar() == a
            with pytest.raises(IntegrityError), conn.begin_nested():
                _voz(conn, b, "ANA VENDAS")
            conn.execute(text("INSERT INTO assets (id, perfil_id, tipo, name) VALUES "
                              "(:i, NULL, 'cenario', 'Sem perfil')"), {"i": uuid.uuid4()})
        with pytest.raises(RuntimeError, match="sem perfil"):
            command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM assets WHERE perfil_id IS NULL"))
        command.downgrade(_cfg(), ANTERIOR)
    finally:
        command.upgrade(_cfg(), "head")
