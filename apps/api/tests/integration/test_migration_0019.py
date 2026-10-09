"""Migration 0019 (spec 023, plano B do R9): o cache de casamento vídeo-fonte × tema e os dois
marcadores nas preferências; a chave primária recusa a repetição; desce e sobe."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn) -> bool:
    return conn.execute(text("SELECT to_regclass('aprendizado_fonte_temas')")).scalar() is not None


def test_upgrade_pk_e_downgrade():
    engine = get_engine()
    command.downgrade(_cfg(), "0018_aprendizado")
    try:
        with engine.begin() as conn:
            assert not _existe(conn)
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            assert _existe(conn)
            cols = set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'aprendizado_preferencias'")).scalars())
            assert {"fonte_temas_versao", "fonte_temas_em"} <= cols
            p = conn.execute(text("INSERT INTO perfis (id, slug, name, language) VALUES "
                                  "(:i, :s, 'P', 'pt-BR') RETURNING id"),
                             {"i": uuid.uuid4(), "s": f"p{uuid.uuid4().hex[:8]}"}).scalar()
            c = conn.execute(text("INSERT INTO canais_fonte (id, youtube_channel_id, title, "
                                  "uploads_playlist_id) VALUES (:i, :y, 'C', :u) RETURNING id"),
                             {"i": uuid.uuid4(), "y": f"UC{uuid.uuid4().hex[:22]}",
                              "u": f"UU{uuid.uuid4().hex[:22]}"}).scalar()
            v = conn.execute(text("INSERT INTO videos_fonte (id, canal_id, youtube_video_id, "
                                  "title, published_at, next_metrics_at) VALUES (:i, :c, :y, "
                                  "'V', now(), now()) RETURNING id"),
                             {"i": uuid.uuid4(), "c": c, "y": uuid.uuid4().hex[:11]}).scalar()
            t = conn.execute(text("INSERT INTO aprendizado_temas (id, perfil_id, nome, nome_norm) "
                                  "VALUES (:i, :p, 'T', 't') RETURNING id"),
                             {"i": uuid.uuid4(), "p": p}).scalar()
            linha = {"p": p, "v": v, "t": t}
            sql = ("INSERT INTO aprendizado_fonte_temas (perfil_id, video_fonte_id, tema_id) "
                   "VALUES (:p, :v, :t)")
            conn.execute(text(sql), linha)
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(sql), linha)
        command.downgrade(_cfg(), "0018_aprendizado")
        with engine.begin() as conn:
            assert not _existe(conn)
    finally:
        command.upgrade(_cfg(), "head")
