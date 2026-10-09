"""T007 (spec 026): a `0025_mercado_shop` sobe, desce vazia e sobe de novo; recusa o downgrade
com dados; cria (ou não) a coluna da 012 conforme a tabela `produtos` exista; as 11 tabelas só
de inserção recusam UPDATE e DELETE e aceitam TRUNCATE; os CHECKs do `mercado` e da
`coleta_config` recusam por INSERT direto."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sociman_api.db import get_engine
from sociman_api.mercado.models import LAGO, SO_INSERCAO

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0021_geracao_interrupcoes"
NEUTRAS = {"perfil_id", "conta_id", "tenant_id", "created_by", "user_id"}


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _cliente(conn) -> uuid.UUID:
    cid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO coleta_clientes (id, nome, nome_normalizado, mercado, token_id, token_hash, "
        "token_emitido_em) VALUES (:i, 'desktop', :n, 'BR', :t, :h, now())"),
        {"i": cid, "n": f"desktop {cid.hex[:6]}", "t": cid.hex[:8], "h": b"\x00" * 32})
    return cid


def _coleta(conn, cliente: uuid.UUID) -> uuid.UUID:
    cid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO mercado_coletas (id, cliente_id, rede, mercado, iniciada_em, batimento_em, "
        "versao_coletor, protocolo) VALUES (:i, :c, 'tiktok', 'BR', now(), now(), '0.1.0', 1)"),
        {"i": cid, "c": cliente})
    return cid


def _produto(conn, mercado: str = "BR") -> uuid.UUID:
    pid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO mercado_produtos (id, rede, mercado, rede_produto_id, url_canonica, "
        "primeira_vez_em, ultimo_visto_em, fonte_descoberta) VALUES (:i, 'tiktok', :m, :r, "
        "'https://exemplo.test/p/1', now(), now(), 'manual')"),
        {"i": pid, "m": mercado, "r": pid.hex[:12]})
    return pid


def _foto(conn, produto: uuid.UUID, coleta: uuid.UUID, **extra) -> int:
    cols = {"produto_id": produto, "data_local": "2026-10-09", "turno": "manha",
            "fonte": "pagina_publica", "moeda": "BRL", "esquema_versao": "tiktok_shop/1",
            "coleta_id": coleta, "coletado_em": datetime.now(UTC), **extra}
    casts = {"turno": "mercado_turno", "fonte": "mercado_fonte"}
    valores = ", ".join(f"CAST(:{c} AS {casts[c]})" if c in casts else f":{c}" for c in cols)
    return conn.execute(text(
        f"INSERT INTO mercado_produto_fotos ({', '.join(cols)}) VALUES ({valores}) RETURNING id"),
        cols).scalar()


def test_sobe_desce_vazia_e_sobe():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "mercado_produtos")
            assert not _existe(conn, "coleta_clientes")
            tipos = conn.execute(text(
                "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'notificacao_tipo'")).scalars().all()
            assert "coleta_captcha" not in tipos
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            for t in LAGO + ("mercado_fila", "mercado_coletas", "mercado_coleta_itens",
                             "coleta_eventos", "mercado_interesses", "mercado_perfil_config",
                             "coleta_clientes", "coleta_config"):
                assert _existe(conn, t), t
            tipos = conn.execute(text(
                "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'notificacao_tipo'")).scalars().all()
            assert {"coleta_captcha", "coleta_login", "coleta_bloqueio", "coleta_layout",
                    "coleta_parada", "mercado_interesse_auto"} <= set(tipos)
    finally:
        command.upgrade(_cfg(), "head")


def test_downgrade_recusa_com_dados():
    with get_engine().begin() as conn:
        c = _cliente(conn)
    try:
        with pytest.raises(RuntimeError, match="recusado"):
            command.downgrade(_cfg(), ANTERIOR)
    finally:
        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM coleta_clientes WHERE id = :i"), {"i": c})
        command.upgrade(_cfg(), "head")


def test_coluna_da_012_segue_a_tabela_produtos():
    """Sem `produtos` no banco (esta worktree), a coluna e a FK não existem; com a tabela (a
    012 mesclada), existem. O teste cobre o caminho que o banco atual tem."""
    with get_engine().begin() as conn:
        tem_produtos = _existe(conn, "produtos")
        coluna = conn.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'produtos' "
            "AND column_name = 'mercado_produto_id'")).scalar() is not None
        fk = conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'fk_mercado_interesses_produto'")
        ).scalar() is not None
    assert coluna == tem_produtos
    assert fk == tem_produtos


def test_lago_sem_coluna_de_perfil_conta_ou_tenant():
    """FR-001/FR-057: nenhuma tabela do lago nem da operação tem dono, salvo a exceção
    nominal `mercado_fila.perfil_id` (operacional)."""
    with get_engine().begin() as conn:
        rows = conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_name LIKE 'mercado\\_%' OR table_name LIKE 'coleta\\_%'")).all()
    ruins = sorted(f"{t}.{c}" for t, c in rows if c in NEUTRAS
                   and t not in ("mercado_interesses", "mercado_perfil_config",
                                 "coleta_clientes", "coleta_config")
                   and (t, c) != ("mercado_fila", "perfil_id"))
    assert not ruins, ruins


def test_so_insercao_recusa_update_e_delete_e_aceita_truncate():
    engine = get_engine()
    with engine.begin() as conn:
        cli = _cliente(conn)
        col = _coleta(conn, cli)
        prod = _produto(conn)
        foto = _foto(conn, prod, col)
    assert len(SO_INSERCAO) == 11
    with pytest.raises(DBAPIError, match="só de inserção"), engine.begin() as conn:
        conn.execute(text("UPDATE mercado_produto_fotos SET vendidos = 1 WHERE id = :i"),
                     {"i": foto})
    with pytest.raises(DBAPIError, match="só de inserção"), engine.begin() as conn:
        conn.execute(text("DELETE FROM mercado_produto_fotos WHERE id = :i"), {"i": foto})
    with engine.begin() as conn:
        for tabela in SO_INSERCAO:
            trig = conn.execute(text(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'mercado_so_insercao' "
                "AND tgrelid = CAST(:t AS regclass)"), {"t": tabela}).scalar()
            assert trig == 1, tabela
        # A 2ª foto do mesmo dia, turno e fonte é "repetida" (UQ); a do turno da noite passa.
        with pytest.raises(IntegrityError), conn.begin_nested():
            _foto(conn, prod, col)
        _foto(conn, prod, col, turno="noite")
        conn.execute(text("TRUNCATE mercado_produto_fotos"))  # trigger de linha não dispara
        assert conn.execute(text("SELECT count(*) FROM mercado_produto_fotos")).scalar() == 0


def test_checks_do_mercado_e_da_config():
    engine = get_engine()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _produto(conn, mercado="br")
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _produto(conn, mercado="BRA")
    # Ligar sem aceite é recusado no próprio banco (FR-034).
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("INSERT INTO coleta_config (id, habilitada) VALUES (1, true)"))
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO coleta_config (id, habilitada, risco_aceito_em) VALUES (1, true, now())"))
        conn.execute(text("DELETE FROM coleta_config WHERE id = 1"))
    # Interesse de vitrine sem perfil, qualquer outro com perfil.
    with pytest.raises(IntegrityError), engine.begin() as conn:
        prod = _produto(conn)
        conn.execute(text(
            "INSERT INTO mercado_interesses (id, perfil_id, mercado_produto_id, origem) "
            "VALUES (:i, NULL, :p, 'manual')"), {"i": uuid.uuid4(), "p": prod})
