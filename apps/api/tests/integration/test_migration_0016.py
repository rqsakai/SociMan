"""Migration 0016 (spec 013, T005): desce para a 0015 e sobe; os CHECKs de
`agencia_importacoes` e `agencia_importacao_itens` recusam com SQL direto; o índice único parcial
recusa duas `processando`; o trigger recusa UPDATE de outra coluna, a 2ª marca do desfazer e o
DELETE (o TRUNCATE passa); desce e sobe de novo."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0015_cenas"
TABELAS = ("agencia_importacoes", "agencia_importacao_itens")
IMP = ("INSERT INTO agencia_importacoes (id, estado, raiz_shared, raiz_clipes, arquivos, "
       "criada_por, erro, desfeita_em, desfeita_por) VALUES (:id, "
       "CAST(:estado AS importacao_agencia_estado), '/a', '/b', '{}'::jsonb, :u, :erro, :d_em, "
       ":d_por)")
ITEM = ("INSERT INTO agencia_importacao_itens (importacao_id, ordem, tipo, arquivo, chave, "
        "impressao, situacao, resultado, entity_type, entity_id, entity_version) VALUES (:i, 1, "
        ":tipo, 'shared:perfis/x/perfil.md', 'perfil:x', 'abc', 'novo', "
        "CAST(:res AS importacao_item_resultado), :et, :eid, :ev)")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _imp(user, **kw) -> dict:
    return {"id": uuid.uuid4(), "estado": "concluida", "u": user, "erro": None, "d_em": None,
            "d_por": None} | kw


def _item(imp, **kw) -> dict:
    return {"i": imp, "tipo": "perfil", "res": "criado", "et": "perfil", "eid": uuid.uuid4(),
            "ev": 1} | kw


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
        command.upgrade(_cfg(), "head")

        with engine.begin() as conn:
            assert all(_existe(conn, t) for t in TABELAS)
            ok = _imp(dono)
            conn.execute(text(IMP), ok)
            conn.execute(text(IMP), _imp(dono, estado="processando"))
            conn.execute(text(IMP), _imp(dono, estado="falhou", erro="interrompida"))
            conn.execute(text(IMP), _imp(dono, estado="desfeita", d_em="2026-10-06T10:00:00-03",
                                         d_por=dono))
            conn.execute(text(ITEM), _item(ok["id"]))
            conn.execute(text(ITEM), _item(ok["id"], res="fora", et=None, eid=None, ev=None))
            linha = conn.execute(text("SELECT version, contagens, progresso FROM "
                                      "agencia_importacoes WHERE id = :i"), {"i": ok["id"]}).one()
            assert tuple(linha) == (1, {}, {})

        # ---- CHECKs e índice parcial ----
        for kw, nome in (({"estado": "processando"}, "ux_agencia_imp_processando"),
                         ({"estado": "falhou"}, "ck_agencia_imp_erro"),
                         ({"erro": "x"}, "ck_agencia_imp_erro"),
                         ({"estado": "desfeita"}, "ck_agencia_imp_desfeita"),
                         ({"d_em": "2026-10-06T10:00:00-03", "d_por": dono},
                          "ck_agencia_imp_desfeita")):
            _recusa(IMP, _imp(dono, **kw), nome)
        for kw, nome in (({"tipo": "produto"}, "ck_agencia_item_tipo"),
                         ({"eid": None}, "ck_agencia_item_entidade"),
                         ({"res": "atualizado", "ev": None}, "ck_agencia_item_entidade")):
            _recusa(ITEM, _item(ok["id"], **kw), nome)

        # ---- só inserção, salvo as marcas do desfazer (uma vez) ----
        with engine.begin() as conn:
            conn.execute(text("UPDATE agencia_importacao_itens SET desfeito_em = now() "
                              "WHERE resultado = 'criado'"))
            conn.execute(text("UPDATE agencia_importacao_itens SET desfazer_motivo = "
                              "'editado_depois' WHERE resultado = 'fora'"))
        for sql in ("UPDATE agencia_importacao_itens SET resultado = 'mantido'",
                    ("UPDATE agencia_importacao_itens SET desfazer_motivo = 'em_uso' "
                     "WHERE resultado = 'criado'"),
                    ("UPDATE agencia_importacao_itens SET desfeito_em = now(), trecho = 'x' "
                     "WHERE resultado = 'fora'"),
                    "DELETE FROM agencia_importacao_itens"):
            with pytest.raises(DBAPIError, match="agencia_importacao_itens"), \
                    engine.begin() as conn:
                conn.execute(text(sql))
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE agencia_importacao_itens"))
            assert conn.execute(text("SELECT count(*) FROM agencia_importacao_itens")
                                ).scalar() == 0

        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
            assert conn.execute(text(
                "SELECT count(*) FROM pg_type WHERE typname IN ('importacao_agencia_estado', "
                "'importacao_item_resultado')")).scalar() == 0
            assert conn.execute(text(
                "SELECT count(*) FROM pg_proc WHERE proname = 'agencia_itens_so_insercao'")
            ).scalar() == 0
    finally:
        command.upgrade(_cfg(), "head")  # subir de novo funciona

    with engine.begin() as conn:
        assert all(_existe(conn, t) for t in TABELAS)
