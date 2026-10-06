"""Migration 0014 (spec 009, T012): sobe sobre a 0013 sem mudar o histórico, cria as tabelas, o
singleton desligado e os CHECKs do ator; desce (o histórico do agente vira `system:mcp`, nada é
apagado) e sobe de novo."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0013_historico_studio"
TABELAS = ("mcp_clientes", "mcp_config", "mcp_chamadas", "anotacoes")
CLIENTE = ("INSERT INTO mcp_clientes (id, nome, nome_normalizado, escopo, token_id, token_hash, "
           "token_emitido_em) VALUES (:id, :n, :n, 'leitura', :tid, decode(repeat('ab', 32), "
           "'hex'), now())")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _historico(conn) -> tuple:
    return tuple(conn.execute(text(
        "SELECT count(*), md5(string_agg(t.id::text || t.actor_kind, '|' ORDER BY t.id)) "
        "FROM entity_versions t")).one())


def _recusa(sql: str, params: dict, nome: str) -> None:
    with pytest.raises(IntegrityError, match=nome), get_engine().begin() as conn:
        conn.execute(text(sql), params)


def test_upgrade_checks_trigger_e_downgrade(make_user):
    dono = make_user(role="dono").id
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
            conn.execute(text(
                "INSERT INTO entity_versions (entity_type, entity_id, version, action, "
                "actor_kind, actor_user_id, after, changed_fields) VALUES ('perfil', "
                "gen_random_uuid(), 1, 'created', 'user', :u, '{}', '{}')"), {"u": dono})
            hist = _historico(conn)
        command.upgrade(_cfg(), "head")

        with engine.begin() as conn:
            assert all(_existe(conn, t) for t in TABELAS)
            assert _historico(conn) == hist
            assert tuple(conn.execute(text(
                "SELECT id, habilitado, version FROM mcp_config")).one()) == (1, False, 1)
            cid = uuid.uuid4()
            conn.execute(text(CLIENTE), {"id": cid, "n": "caçador", "tid": "abcdefgh"})
            conn.execute(text(
                "INSERT INTO mcp_chamadas (cliente_id, via, tool, metodo, rota, resultado) "
                "VALUES (:c, 'api', 'perfis_list', 'GET', 'GET /api/perfis', 'ok')"), {"c": cid})

        # CHECKs e únicos
        _recusa(CLIENTE, {"id": uuid.uuid4(), "n": "caçador", "tid": "bbbbbbbb"},
                "uq_mcp_clientes_nome")
        _recusa(CLIENTE, {"id": uuid.uuid4(), "n": "outro", "tid": "abcdefgh"},
                "uq_mcp_clientes_token_id")
        _recusa(CLIENTE, {"id": uuid.uuid4(), "n": "x", "tid": "ABC"}, "ck_mcp_clientes_token_id")
        _recusa("INSERT INTO mcp_config (id) VALUES (2)", {}, "ck_mcp_config_unica")
        _recusa("INSERT INTO entity_versions (entity_type, entity_id, version, action, actor_kind, "
                "after, changed_fields) VALUES ('t', gen_random_uuid(), 1, 'created', "
                "'mcp_client', '{}', '{}')", {}, "ck_entity_versions_ator")
        _recusa("INSERT INTO security_events (type, outcome, actor_kind, actor_mcp_client_id) "
                "VALUES ('t', 'ok', 'user', :c)", {"c": cid}, "ck_security_events_ator")
        _recusa("INSERT INTO anotacoes (id, alvo_tipo, alvo_id, tipo, texto, campos, autor_kind, "
                "autor_user_id) VALUES (gen_random_uuid(), 'perfil', gen_random_uuid(), "
                "'proposta_texto', 'x', '{}', 'user', :u)", {"u": dono},
                "ck_anotacoes_proposta_em_destino")
        _recusa("INSERT INTO anotacoes (id, alvo_tipo, alvo_id, tipo, texto, autor_kind, "
                "autor_user_id, autor_mcp_cliente_id) VALUES (gen_random_uuid(), 'perfil', "
                "gen_random_uuid(), 'observacao', 'x', 'user', :u, :c)", {"u": dono, "c": cid},
                "ck_anotacoes_autor")

        # só inserção
        for sql in ("UPDATE mcp_chamadas SET tool = 'x'", "DELETE FROM mcp_chamadas"):
            with pytest.raises(DBAPIError, match="só de inserção"), engine.begin() as conn:
                conn.execute(text(sql))

        # uma versão do agente sobrevive ao downgrade como `system:mcp`
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO entity_versions (entity_type, entity_id, version, action, "
                "actor_kind, actor_mcp_client_id, after, changed_fields) VALUES ('anotacao', "
                "gen_random_uuid(), 1, 'created', 'mcp_client', :c, '{}', '{}')"), {"c": cid})
            total = _historico(conn)[0]
        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
            assert _historico(conn)[0] == total
            assert conn.execute(text(
                "SELECT count(*) FROM entity_versions WHERE actor_kind = 'system:mcp'")
            ).scalar() == 1
    finally:
        command.upgrade(_cfg(), "head")
