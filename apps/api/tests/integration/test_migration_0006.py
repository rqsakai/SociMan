"""Migration 0006 (spec 006, T013): upgrade/downgrade limpos e as restrições do data-model."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]

ANTERIOR = "0005_assets"
TABELAS_006 = ("canais_fonte", "canal_perfis", "videos_fonte", "video_metricas", "youtube_cota",
               "padroes_corte", "envios", "postagens", "ia_chamadas", "notificacoes")  # 0008 renomeou


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _perfil(conn) -> uuid.UUID:
    pid = uuid.uuid4()
    conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'Teste')"),
                 {"id": pid, "slug": f"p-{pid.hex[:8]}"})
    return pid


def _corte(conn, perfil_id, status: str = "na_fila", kit: bool = True, **extra) -> uuid.UUID:
    cid = uuid.uuid4()
    cols = {
        "id": cid, "perfil_id": perfil_id, "hook_text": "", "status": status,
        "kit_version": 1 if kit else None,
        "kit_tokens": "{}" if kit else None,
        "original_filename": "a.mp4", "original_key": f"k/{cid}", "original_content_type":
        "video/mp4", "original_bytes": 1, "duration_ms": 1000, "width": 1080, "height": 1920,
        "fps": 30, "video_codec": "h264", "original_sha256": "x", **extra,
    }
    names = ", ".join(cols)
    values = ", ".join(
        f"CAST(:{k} AS jsonb)" if k == "kit_tokens" else
        f"CAST(:{k} AS corte_status)" if k == "status" else f":{k}" for k in cols
    )
    conn.execute(text(f"INSERT INTO cortes ({names}) VALUES ({values})"), cols)
    return cid


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _corte_status(conn) -> list[str]:
    return list(conn.execute(text(
        "SELECT unnest(enum_range(NULL::corte_status))::text"
    )).scalars())


def test_downgrade_e_upgrade_limpos_e_cortes_antigos_viram_upload():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS_006)
            assert _corte_status(conn) == ["na_fila", "processando", "pronto", "falhou"]
            cols = set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'cortes'"
            )).scalars())
            assert "origem" not in cols and "archived_at" not in cols
            antigo = _corte(conn, _perfil(conn))  # um corte da 004, antes da 0006
    finally:
        command.upgrade(_cfg(), "head")

    with engine.begin() as conn:
        assert all(_existe(conn, t) for t in TABELAS_006)
        assert _corte_status(conn) == ["revisao", "na_fila", "processando", "pronto", "falhou"]
        origem = conn.execute(text("SELECT origem::text FROM cortes WHERE id = :id"),
                              {"id": antigo}).scalar()
        assert origem == "upload"


def test_check_de_envios_por_origem_e_status():
    engine = get_engine()
    with engine.begin() as conn:
        pid = _perfil(conn)
    with pytest.raises(IntegrityError, match="ck_envios_origem_canal"), engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO envios (id, perfil_id, origem, source_title, source_url) "
            "VALUES (:id, :p, 'canal', 'Vídeo', 'https://www.youtube.com/watch?v=abc')"
        ), {"id": uuid.uuid4(), "p": pid})
    with pytest.raises(IntegrityError, match="ck_envios_origem_arquivo"), engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO envios (id, perfil_id, origem, source_title) "
            "VALUES (:id, :p, 'avulso_arquivo', 'Arquivo')"
        ), {"id": uuid.uuid4(), "p": pid})
    with pytest.raises(IntegrityError, match="ck_envios_enviado_config"), engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO envios (id, perfil_id, origem, source_title, source_url, status) "
            "VALUES (:id, :p, 'avulso_link', 'Link', 'https://exemplo.com/v', 'na_fila')"
        ), {"id": uuid.uuid4(), "p": pid})
    with engine.begin() as conn:  # avulso por link selecionado, e descartado sem enviar: válidos
        for status in ("selecionado", "descartado"):
            conn.execute(text(
                "INSERT INTO envios (id, perfil_id, origem, source_title, source_url, status) "
                "VALUES (:id, :p, 'avulso_link', 'Link', 'https://exemplo.com/v', "
                "CAST(:s AS envio_status))"
            ), {"id": uuid.uuid4(), "p": pid, "s": status})


def test_check_do_kit_nos_cortes():
    engine = get_engine()
    with engine.begin() as conn:
        pid = _perfil(conn)
    with pytest.raises(IntegrityError, match="ck_cortes_kit"), engine.begin() as conn:
        _corte(conn, pid, status="na_fila", kit=False)
    with engine.begin() as conn:  # em revisão, sem kit e sem gancho: válido
        _corte(conn, pid, status="revisao", kit=False)


def test_postagem_ativa_unica_por_corte_e_conta():
    engine = get_engine()
    with engine.begin() as conn:
        pid = _perfil(conn)
        corte = _corte(conn, pid)
        conta = uuid.uuid4()
        conn.execute(text(
            "INSERT INTO contas (id, perfil_id, platform, handle, url) "
            "VALUES (:id, :p, 'tiktok', 'teste', 'https://www.tiktok.com/@teste')"
        ), {"id": conta, "p": pid})
        sql = text("INSERT INTO postagens (id, corte_id, conta_id, archived_at) "
                   "VALUES (:id, :c, :k, :arq)")
        conn.execute(sql, {"id": uuid.uuid4(), "c": corte, "k": conta, "arq": None})
        # Uma arquivada (cancelada) não conta.
        conn.execute(sql, {"id": uuid.uuid4(), "c": corte, "k": conta, "arq": "2026-09-29"})
    with pytest.raises(IntegrityError, match="uq_postagens_corte_conta_ativa"), \
            engine.begin() as conn:
        conn.execute(sql, {"id": uuid.uuid4(), "c": corte, "k": conta, "arq": None})
