"""Migration 0017 (spec 022, T004): sobe sobre uma base da 0016 com importações da 020 (ativas e
desfeitas), que continuam válidas; cada CHECK novo recusa com SQL direto; os 3 triggers recusam
UPDATE e DELETE, e o TRUNCATE passa; desce sem público e sobe de novo; com público, o downgrade
é recusado."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0016_importacao"
TABELAS = ("metricas_studio_distribuicoes", "metricas_studio_atividade",
           "metricas_studio_espectadores")
COLUNAS = ("sha_genero", "sha_territorios", "sha_atividade", "sha_espectadores", "data_foto",
           "data_foto_origem", "secoes_vazias")
IMP_020 = ("INSERT INTO metricas_studio_importacoes (id, serie_id, secoes, sha_visao_geral, "
           "sha_seguidores, periodo_de, periodo_ate, ano_origem, contagens, estado, criada_por, "
           "desfeita_em, desfeita_por) VALUES (:id, :s, :secoes, :vg, :seg, '2026-09-25', "
           "'2026-10-01', 'deduzido', '{}'::jsonb, CAST(:estado AS studio_importacao_estado), "
           ":u, :d_em, :d_por)")
IMP = ("INSERT INTO metricas_studio_importacoes (id, serie_id, secoes, sha_seguidores, "
       "sha_genero, sha_territorios, sha_atividade, sha_espectadores, data_foto, "
       "data_foto_origem, secoes_vazias, periodo_de, periodo_ate, ano_origem, contagens, "
       "criada_por) VALUES (:id, :s, :secoes, :seg, :gen, :ter, :atv, :esp, :foto, :origem, "
       ":vazias, '2026-09-25', '2026-10-02', 'deduzido', '{}'::jsonb, :u)")
DIST = ("INSERT INTO metricas_studio_distribuicoes (importacao_id, serie_id, tipo, data_foto, "
        "rotulo, pct) VALUES (:i, :s, :tipo, '2026-10-02', :rotulo, :pct)")
ATV = ("INSERT INTO metricas_studio_atividade (importacao_id, serie_id, dia, hora, ativos) "
       "VALUES (:i, :s, :dia, :hora, :ativos)")
ESP = ("INSERT INTO metricas_studio_espectadores (importacao_id, serie_id, dia, total, novos, "
       "recorrentes) VALUES (:i, :s, :dia, :total, :novos, :rec)")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _colunas(conn) -> set[str]:
    return {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'metricas_studio_importacoes'"))}


def _semear(conn, dono) -> dict:
    perfil, conta, serie = (uuid.uuid4() for _ in range(3))
    conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'T')"),
                 {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    conn.execute(text("INSERT INTO contas (id, perfil_id, platform, handle, url) VALUES "
                      "(:id, :p, 'tiktok', 'c0', 'https://www.tiktok.com/@c0')"),
                 {"id": conta, "p": perfil})
    conn.execute(text("INSERT INTO metricas_series (id, rede, conta_id) VALUES "
                      "(:id, 'tiktok', :c)"), {"id": serie, "c": conta})
    ativa, desfeita = uuid.uuid4(), uuid.uuid4()
    conn.execute(text(IMP_020), {"id": ativa, "s": serie, "secoes": ["visao_geral", "seguidores"],
                                 "vg": "a" * 64, "seg": "b" * 64, "estado": "ativa", "u": dono,
                                 "d_em": None, "d_por": None})
    conn.execute(text(IMP_020), {"id": desfeita, "s": serie, "secoes": ["seguidores"],
                                 "vg": None, "seg": "c" * 64, "estado": "desfeita", "u": dono,
                                 "d_em": "2026-10-02T10:00:00-03:00", "d_por": dono})
    return {"serie": serie, "ativa": ativa, "desfeita": desfeita}


def _imp(serie, user, **kw) -> dict:
    base = {"id": uuid.uuid4(), "s": serie,
            "secoes": ["seguidores", "genero", "atividade", "espectadores"], "seg": "s" * 64,
            "gen": "g" * 64, "ter": None, "atv": "t" * 64, "esp": "e" * 64,
            "foto": "2026-10-02", "origem": "historico", "vazias": ["territorios"], "u": user}
    return base | kw


def _recusa(sql: str, params: dict, nome: str) -> None:
    with pytest.raises(IntegrityError, match=nome), get_engine().begin() as conn:
        conn.execute(text(sql), params)


def test_upgrade_checks_triggers_e_downgrade(make_user):
    dono = make_user(role="dono").id
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
            assert not _colunas(conn) & set(COLUNAS)
            ids = _semear(conn, dono)
        command.upgrade(_cfg(), "head")

        serie = ids["serie"]
        with engine.begin() as conn:
            assert all(_existe(conn, t) for t in TABELAS)
            assert set(COLUNAS) <= _colunas(conn)
            # as da 020 continuam válidas, com as colunas novas nulas e sem vazias
            linhas = conn.execute(text(
                "SELECT estado::text, sha_genero, data_foto, secoes_vazias FROM "
                "metricas_studio_importacoes ORDER BY estado")).all()
            assert [tuple(r) for r in linhas] == [("ativa", None, None, []),
                                                  ("desfeita", None, None, [])]
            ok = _imp(serie, dono)
            conn.execute(text(IMP), ok)
            so_atividade = _imp(serie, dono, secoes=["atividade"], seg=None, gen=None,
                                atv="u" * 64, esp=None, foto=None, origem=None, vazias=[])
            conn.execute(text(IMP), so_atividade)
            conn.execute(text(DIST), {"i": ok["id"], "s": serie, "tipo": "genero",
                                      "rotulo": "feminino", "pct": 61.5})
            conn.execute(text(DIST), {"i": ok["id"], "s": serie, "tipo": "territorio",
                                      "rotulo": "BR", "pct": None})
            conn.execute(text(ATV), {"i": ok["id"], "s": serie, "dia": "2026-09-25", "hora": 0,
                                     "ativos": None})
            conn.execute(text(ATV), {"i": ok["id"], "s": serie, "dia": "2026-09-25", "hora": 23,
                                     "ativos": 4})
            conn.execute(text(ESP), {"i": ok["id"], "s": serie, "dia": "2026-09-25",
                                     "total": None, "novos": None, "rec": None})

        # ---- CHECKs das importações ----
        so_seg = {"gen": None, "atv": None, "esp": None, "foto": None, "origem": None,
                  "vazias": []}
        for kw, nome in (({"secoes": ["seguidores", "outra"]} | so_seg, "ck_studio_imp_secoes"),
                         ({"secoes": [], "seg": None} | so_seg, "ck_studio_imp_secoes"),
                         ({"gen": None}, "ck_studio_imp_sha_publico"),
                         ({"ter": "x" * 64}, "ck_studio_imp_sha_publico"),
                         ({"esp": None}, "ck_studio_imp_sha_publico"),
                         ({"foto": None, "origem": None}, "ck_studio_imp_foto"),
                         ({"origem": None}, "ck_studio_imp_foto"),
                         ({"origem": "chute"}, "ck_studio_imp_foto"),
                         ({"secoes": ["atividade"], "seg": None, "gen": None, "esp": None,
                           "vazias": []}, "ck_studio_imp_foto"),
                         ({"vazias": ["seguidores"]}, "ck_studio_imp_vazias"),
                         ({"vazias": ["genero"]}, "ck_studio_imp_vazias")):
            _recusa(IMP, _imp(serie, dono, **kw), nome)

        # ---- CHECKs e unicidade das tabelas novas ----
        imp = ok["id"]
        for params, nome in (
                ({"tipo": "idade", "rotulo": "x", "pct": 1}, "ck_studio_dist_tipo"),
                ({"tipo": "genero", "rotulo": "Male", "pct": 1}, "ck_studio_dist_genero"),
                ({"tipo": "territorio", "rotulo": "AR", "pct": 100.5}, "ck_studio_dist_pct"),
                ({"tipo": "territorio", "rotulo": "AR", "pct": -1}, "ck_studio_dist_pct"),
                ({"tipo": "territorio", "rotulo": "", "pct": 1}, "ck_studio_dist_rotulo"),
                ({"tipo": "territorio", "rotulo": "x" * 65, "pct": 1}, "ck_studio_dist_rotulo"),
                ({"tipo": "genero", "rotulo": "feminino", "pct": 2}, "uq_studio_dist_imp")):
            _recusa(DIST, {"i": imp, "s": serie, **params}, nome)
        for params, nome in (({"hora": 24, "ativos": 1}, "ck_studio_atv_hora"),
                             ({"hora": -1, "ativos": 1}, "ck_studio_atv_hora"),
                             ({"hora": 5, "ativos": -1}, "ck_studio_atv_naoneg"),
                             ({"hora": 0, "ativos": 9}, "uq_studio_atv_imp")):
            _recusa(ATV, {"i": imp, "s": serie, "dia": "2026-09-25", **params}, nome)
        for params, nome in (({"dia": "2026-09-26", "total": -1, "novos": 0, "rec": 0},
                              "ck_studio_esp_naoneg"),
                             ({"dia": "2026-09-26", "total": 1, "novos": 0, "rec": -1},
                              "ck_studio_esp_naoneg"),
                             ({"dia": "2026-09-25", "total": 1, "novos": 1, "rec": 0},
                              "uq_studio_esp_imp")):
            _recusa(ESP, {"i": imp, "s": serie, **params}, nome)

        # ---- só inserção ----
        for tabela, coluna in (("metricas_studio_distribuicoes", "pct = 1"),
                               ("metricas_studio_atividade", "ativos = 1"),
                               ("metricas_studio_espectadores", "total = 1")):
            for sql in (f"UPDATE {tabela} SET {coluna}", f"DELETE FROM {tabela}"):
                with pytest.raises(DBAPIError, match="só de inserção"), engine.begin() as conn:
                    conn.execute(text(sql))

        # ---- com público, o downgrade é recusado (nada muda) ----
        with pytest.raises(RuntimeError, match="seções de público"):
            command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert all(_existe(conn, t) for t in TABELAS)
            conn.execute(text(f"TRUNCATE {', '.join(TABELAS)}"))
            assert all(conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0
                       for t in TABELAS)
            conn.execute(text("DELETE FROM metricas_studio_importacoes WHERE id IN (:a, :b)"),
                         {"a": ok["id"], "b": so_atividade["id"]})

        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
            assert not _colunas(conn) & set(COLUNAS)
            assert conn.execute(text("SELECT count(*) FROM metricas_studio_importacoes")
                                ).scalar() == 2  # as da 020 ficaram
            _recusa(IMP_020, {"id": uuid.uuid4(), "s": serie, "secoes": ["genero"], "vg": None,
                              "seg": None, "estado": "ativa", "u": dono, "d_em": None,
                              "d_por": None}, "ck_studio_imp_secoes")
    finally:
        command.upgrade(_cfg(), "head")  # subir de novo funciona

    with engine.begin() as conn:
        assert all(_existe(conn, t) for t in TABELAS)
        assert conn.execute(text("SELECT count(*) FROM metricas_studio_importacoes")
                            ).scalar() == 2
