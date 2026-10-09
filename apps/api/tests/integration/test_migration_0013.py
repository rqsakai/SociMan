"""Migration 0013 (spec 020, T004): sobe sobre uma base da 0012 com uma série viva e uma anônima
sem mudar as fotos; cada CHECK de `metricas_studio_importacoes` e `metricas_studio_dias` recusa
com SQL direto; o trigger recusa UPDATE e DELETE nos dias, e o TRUNCATE passa; desce e sobe."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0012_guia_comunicacao"
TABELAS = ("metricas_studio_importacoes", "metricas_studio_dias")
IMP = ("INSERT INTO metricas_studio_importacoes (id, serie_id, secoes, sha_visao_geral, "
       "sha_seguidores, periodo_de, periodo_ate, ano_origem, contagens, estado, criada_por, "
       "desfeita_em, desfeita_por) VALUES (:id, :s, :secoes, :vg, :seg, :de, :ate, :ano, "
       "'{}'::jsonb, CAST(:estado AS studio_importacao_estado), :u, :d_em, :d_por)")
DIA = ("INSERT INTO metricas_studio_dias (importacao_id, serie_id, dia, tem_visao_geral, views, "
       "likes, tem_seguidores, seguidores, seguidores_dif) VALUES (:i, :s, :dia, :tvg, :views, "
       ":likes, :tseg, :seg, :dif)")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _semear(conn) -> dict:
    perfil, conta, viva, anonima = (uuid.uuid4() for _ in range(4))
    conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'T')"),
                 {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    conn.execute(text("INSERT INTO contas (id, perfil_id, platform, handle, url) VALUES "
                      "(:id, :p, 'tiktok', 'c0', 'https://www.tiktok.com/@c0')"),
                 {"id": conta, "p": perfil})
    conn.execute(text("INSERT INTO metricas_series (id, rede, conta_id) VALUES "
                      "(:id, 'tiktok', :c)"), {"id": viva, "c": conta})
    conn.execute(text("INSERT INTO metricas_series (id, rede, rotulo, anonima_n, anonimizada_em) "
                      "VALUES (:id, 'tiktok', 'Conta anônima 1', 1, now())"), {"id": anonima})
    conn.execute(text("INSERT INTO metricas_conta_fotos (serie_id, coletado_em, janela_em, "
                      "seguidores) VALUES (:s, now(), date_trunc('hour', now()), 10)"),
                 {"s": viva})
    return {"viva": viva, "anonima": anonima}


def _fotos(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(text(
        "SELECT id, serie_id, coletado_em, seguidores FROM metricas_conta_fotos ORDER BY id"))]


def _imp(serie, user, **kw) -> dict:
    base = {"id": uuid.uuid4(), "s": serie, "secoes": ["visao_geral"], "vg": "a" * 64,
            "seg": None, "de": "2026-09-25", "ate": "2026-10-01", "ano": "nome_zip",
            "estado": "ativa", "u": user, "d_em": None, "d_por": None}
    return base | kw


def _dia(imp, serie, **kw) -> dict:
    base = {"i": imp, "s": serie, "dia": "2026-09-25", "tvg": True, "views": 10, "likes": 1,
            "tseg": False, "seg": None, "dif": None}
    return base | kw


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
            ids = _semear(conn)
            fotos = _fotos(conn)
        command.upgrade(_cfg(), "head")

        viva = ids["viva"]
        with engine.begin() as conn:
            assert all(_existe(conn, t) for t in TABELAS)
            assert _fotos(conn) == fotos
            assert conn.execute(text("SELECT count(*) FROM metricas_studio_importacoes")
                                ).scalar() == 0
            ok = _imp(viva, dono, secoes=["visao_geral", "seguidores"], seg="b" * 64)
            conn.execute(text(IMP), ok)
            conn.execute(text(IMP), _imp(ids["anonima"], dono, estado="desfeita",
                                         d_em="2026-10-02T10:00:00-03:00", d_por=dono))
            conn.execute(text(DIA), _dia(ok["id"], viva))
            conn.execute(text(DIA), _dia(ok["id"], viva, dia="2026-09-26", tvg=False,
                                         views=None, likes=None, tseg=True, seg=3, dif=-1))
            linha = conn.execute(text("SELECT estado::text, version FROM "
                                      "metricas_studio_importacoes WHERE id = :i"),
                                 {"i": ok["id"]}).one()
            assert tuple(linha) == ("ativa", 1)

        # ---- CHECKs das importações ----
        for kw, nome in (({"secoes": []}, "ck_studio_imp_secoes"),
                         ({"secoes": ["visao_geral", "outra"]}, "ck_studio_imp_secoes"),
                         ({"vg": None}, "ck_studio_imp_sha"),
                         ({"seg": "c" * 64}, "ck_studio_imp_sha"),
                         ({"estado": "desfeita"}, "ck_studio_imp_desfeita"),
                         ({"d_em": "2026-10-02T10:00:00-03:00", "d_por": dono},
                          "ck_studio_imp_desfeita"),
                         ({"de": "2026-10-02"}, "ck_studio_imp_periodo"),
                         ({"ano": "chute"}, "ck_studio_imp_ano")):
            _recusa(IMP, _imp(viva, dono, **kw), nome)

        # ---- CHECKs e unicidade dos dias ----
        imp = ok["id"]
        for kw, nome in (({"tvg": False, "tseg": False, "views": None}, "ck_studio_dias_secao"),
                         ({"views": None}, "ck_studio_dias_secao"),
                         ({"tseg": True}, "ck_studio_dias_secao"),
                         ({"views": -1}, "ck_studio_dias_naoneg"),
                         ({"likes": -1}, "ck_studio_dias_naoneg"),
                         ({"dia": "2026-09-27", "tseg": True, "seg": -2},
                          "ck_studio_dias_naoneg"),
                         ({}, "uq_studio_dias_imp_dia")):
            params = _dia(imp, viva, **kw)
            if nome != "uq_studio_dias_imp_dia" and "dia" not in kw:
                params["dia"] = "2026-09-28"
            _recusa(DIA, params, nome)

        # ---- só inserção ----
        for sql in ("UPDATE metricas_studio_dias SET views = 1",
                    "DELETE FROM metricas_studio_dias"):
            with pytest.raises(DBAPIError, match="só de inserção"), engine.begin() as conn:
                conn.execute(text(sql))
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE metricas_studio_dias"))
            assert conn.execute(text("SELECT count(*) FROM metricas_studio_dias")).scalar() == 0

        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
            assert conn.execute(text(
                "SELECT count(*) FROM pg_type WHERE typname = 'studio_importacao_estado'")
            ).scalar() == 0
            assert conn.execute(text(  # a função da 0011 continua
                "SELECT count(*) FROM pg_proc WHERE proname = 'metricas_recusa_mudanca'")
            ).scalar() == 1
            assert _fotos(conn) == fotos
    finally:
        command.upgrade(_cfg(), "head")  # subir de novo funciona

    with engine.begin() as conn:
        assert all(_existe(conn, t) for t in TABELAS)
        assert _fotos(conn) == fotos
