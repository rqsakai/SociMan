"""Migration 0012 (spec 017, T008): sobe sobre uma base da 0011 com chamadas da 008 sem mudar
nenhuma (proibidas `'{}'`, versões NULL) nem o histórico; cada CHECK e índice único de
`ia_guias` e o CHECK de `guia_rascunho` recusam com SQL direto; desce e sobe de novo."""

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
ANTERIOR = "0011_metricas_tiktok"
COLUNAS = ("guia_perfil_version", "guia_conta_version", "guia_rascunho", "proibidas")
GUIA = ("INSERT INTO ia_guias (id, perfil_id, conta_id, tom, hashtags_fixas, "
        "max_hashtags_fixas, exemplos) VALUES (gen_random_uuid(), :p, :c, :tom, :fixas, :max, "
        "CAST(:ex AS jsonb))")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _colunas(conn) -> set[str]:
    return set(conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'ia_chamadas'"
    )).scalars())


def _semear(conn, dono: uuid.UUID) -> dict:
    perfil, conta = uuid.uuid4(), uuid.uuid4()
    conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'T')"),
                 {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    conn.execute(text("INSERT INTO contas (id, perfil_id, platform, handle, url) VALUES "
                      "(:id, :p, 'tiktok', 'c0', 'https://www.tiktok.com/@c0')"),
                 {"id": conta, "p": perfil})
    for tipo, desfecho, erro in (("perfil.bio", "aplicada", None),
                                 ("postagem.textos", "sem_acao", None),
                                 ("postagem.hashtags", "erro", "timeout")):
        conn.execute(text(
            "INSERT INTO ia_chamadas (id, tipo_campo, perfil_id, entity_type, entity_id, "
            "conta_id, model, prompt_version, duration_ms, desfecho, erro_code, proposta, "
            "created_by) VALUES (gen_random_uuid(), :t, :p, 'perfil', :p, :c, 'claude', 'ia/1', "
            "100, CAST(:d AS ia_desfecho), :e, CAST(:prop AS jsonb), :u)"),
            {"t": tipo, "p": perfil, "c": conta, "d": desfecho, "e": erro, "u": dono,
             "prop": None if erro else json.dumps({"texto": "clickbait"})})
    conn.execute(text(
        "INSERT INTO entity_versions (entity_type, entity_id, version, action, actor_kind, "
        "actor_user_id, after, changed_fields) VALUES ('perfil', :id, 1, 'created', 'user', :u, "
        "CAST('{\"name\": \"T\"}' AS jsonb), ARRAY['name'])"), {"id": perfil, "u": dono})
    return {"perfil": perfil, "conta": conta}


def _chamadas(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(text(
        "SELECT id, tipo_campo, desfecho::text, erro_code, proposta, prompt_version, created_at "
        "FROM ia_chamadas ORDER BY id"))]


def _historico(conn) -> tuple:
    return tuple(conn.execute(text(
        "SELECT count(*), md5(string_agg(t::text, '|' ORDER BY t.id)) FROM entity_versions t"
    )).one())


def _recusa(sql: str, params: dict, nome: str) -> None:
    with pytest.raises(IntegrityError, match=nome), get_engine().begin() as conn:
        conn.execute(text(sql), params)


def _guia(p, c=None, tom="", fixas=(), max_=None, ex="[]") -> dict:
    return {"p": p, "c": c, "tom": tom, "fixas": list(fixas), "max": max_, "ex": ex}


def test_upgrade_preserva_a_008_checks_e_downgrade(make_user):
    dono = make_user(role="dono").id
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "ia_guias")
            assert not set(COLUNAS) & _colunas(conn)
            ids = _semear(conn, dono)
            antes, hist = _chamadas(conn), _historico(conn)
        command.upgrade(_cfg(), "head")

        with engine.begin() as conn:
            assert _chamadas(conn) == antes  # nenhuma chamada mudou
            assert _historico(conn) == hist  # nenhuma versão escrita
            novas = conn.execute(text(
                "SELECT guia_perfil_version, guia_conta_version, guia_rascunho, proibidas "
                "FROM ia_chamadas")).all()
            assert len(novas) == 3
            assert all(tuple(r) == (None, None, None, []) for r in novas)
            assert conn.execute(text("SELECT count(*) FROM ia_guias")).scalar() == 0
            assert set(conn.execute(text(
                "SELECT unnest(enum_range(NULL::guia_emojis))::text")).scalars()) == {
                "nao", "moderado", "livre"}

        perfil, conta = ids["perfil"], ids["conta"]
        with engine.begin() as conn:  # o permitido passa
            conn.execute(text(GUIA), _guia(perfil, fixas=["#a"] * 5, tom="x" * 500))
            conn.execute(text(GUIA), _guia(perfil, conta, fixas=["#b"] * 8, max_=8,
                                           ex=json.dumps([{"tipo": "titulo", "texto": "t"}] * 5)))
            linha = conn.execute(text(
                "SELECT faca, proibidas, emojis, exemplos, version FROM ia_guias "
                "WHERE conta_id IS NULL")).one()
            assert tuple(linha) == ([], [], None, [], 1)

        # ---- índices únicos parciais ----
        _recusa(GUIA, _guia(perfil), "uq_ia_guias_perfil")
        _recusa(GUIA, _guia(perfil, conta), "uq_ia_guias_conta")

        # ---- CHECKs ----
        with engine.begin() as conn:
            outro = uuid.uuid4()
            conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :s, 'U')"),
                         {"id": outro, "s": f"p-{outro.hex[:8]}"})
            outra_conta = uuid.uuid4()
            conn.execute(text("INSERT INTO contas (id, perfil_id, platform, handle, url) VALUES "
                              "(:id, :p, 'youtube', 'c1', 'https://www.youtube.com/@c1')"),
                         {"id": outra_conta, "p": outro})
        _recusa(GUIA, _guia(outro, fixas=["#a"] * 6), "ck_ia_guias_hashtags_fixas")
        _recusa(GUIA, _guia(outro, outra_conta, fixas=["#a"] * 9), "ck_ia_guias_hashtags_fixas")
        _recusa(GUIA, _guia(outro, max_=5), "ck_ia_guias_max_hashtags_fixas")  # no perfil
        _recusa(GUIA, _guia(outro, outra_conta, max_=9), "ck_ia_guias_max_hashtags_fixas")
        _recusa(GUIA, _guia(outro, outra_conta, max_=-1), "ck_ia_guias_max_hashtags_fixas")
        _recusa(GUIA, _guia(outro, tom="x" * 501), "ck_ia_guias_tom")
        _recusa(GUIA, _guia(outro, ex=json.dumps([{"tipo": "titulo", "texto": "t"}] * 6)),
                "ck_ia_guias_exemplos")
        for coluna, n, nome in (("faca", 11, "ck_ia_guias_faca"),
                                ("nao_faca", 11, "ck_ia_guias_nao_faca"),
                                ("vocabulario", 31, "ck_ia_guias_vocabulario"),
                                ("proibidas", 31, "ck_ia_guias_proibidas"),
                                ("emojis_preferidos", 11, "ck_ia_guias_emojis_preferidos")):
            _recusa(f"INSERT INTO ia_guias (id, perfil_id, {coluna}) VALUES "
                    "(gen_random_uuid(), :p, :v)", {"p": outro, "v": ["x"] * n}, nome)
        _recusa("UPDATE ia_chamadas SET guia_rascunho = 'outro'", {},
                "ck_ia_chamadas_guia_rascunho")
        with engine.begin() as conn:
            conn.execute(text("UPDATE ia_chamadas SET guia_rascunho = 'perfil', "
                              "proibidas = ARRAY['clickbait'], guia_perfil_version = 1 "
                              "WHERE tipo_campo = 'postagem.textos'"))

        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not _existe(conn, "ia_guias")
            assert not set(COLUNAS) & _colunas(conn)
            assert conn.execute(text(
                "SELECT count(*) FROM pg_type WHERE typname = 'guia_emojis'")).scalar() == 0
            assert _chamadas(conn) == antes
    finally:
        command.upgrade(_cfg(), "head")  # subir de novo funciona

    with engine.begin() as conn:
        assert _existe(conn, "ia_guias")
        assert COLUNAS and set(COLUNAS) <= _colunas(conn)
        assert _chamadas(conn) == antes
        assert _historico(conn) == hist
