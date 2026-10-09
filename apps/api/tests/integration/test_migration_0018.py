"""Migration 0018 (spec 023, T004): sobe sobre a 0017 com chamadas da 008 existentes (as colunas
novas ficam NULL / '{}'); cada CHECK e índice único recusa com SQL direto; desce e sobe."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0017_publico"
TABELAS = ("aprendizado_temas", "aprendizado_classificacoes", "aprendizado_preferencias",
           "aprendizado_analises", "aprendizado_decisoes", "aprendizado_conferencias")
COLUNAS = ("desempenho_perfil_version", "desempenho_conta_version", "desempenho_exemplos")


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


def _recusa(sql: str, params: dict, nome: str) -> None:
    with pytest.raises(IntegrityError, match=nome), get_engine().begin() as conn:
        conn.execute(text(sql), params)


TEMA = ("INSERT INTO aprendizado_temas (id, perfil_id, nome, nome_norm, palavras_chave, "
        "juntado_em_id, archived_at) VALUES (:id, :p, :nome, :norm, :pal, :junt, :arq)")


def _tema(p, **kw) -> dict:
    return {"id": uuid.uuid4(), "p": p, "nome": "Marvel", "norm": "marvel", "pal": [],
            "junt": None, "arq": None} | kw


def test_upgrade_checks_e_downgrade(make_user):
    dono = make_user(role="dono").id
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
            assert not set(COLUNAS) & _colunas(conn)
            perfil = conn.execute(text(
                "INSERT INTO perfis (id, slug, name, language) VALUES (:id, :s, 'P', 'pt-BR') "
                "RETURNING id"), {"id": uuid.uuid4(), "s": f"p{uuid.uuid4().hex[:8]}"}).scalar()
            chamada = conn.execute(text(
                "INSERT INTO ia_chamadas (id, tipo_campo, perfil_id, entity_type, model, "
                "prompt_version, duration_ms) VALUES (:id, 'perfil.bio', :p, 'perfil', 'm', "
                "'ia/2', 1) RETURNING id"), {"id": uuid.uuid4(), "p": perfil}).scalar()
        command.upgrade(_cfg(), "head")

        with engine.begin() as conn:
            assert all(_existe(conn, t) for t in TABELAS)
            assert set(COLUNAS) <= _colunas(conn)
            antiga = conn.execute(text(
                "SELECT desempenho_perfil_version, desempenho_conta_version, desempenho_exemplos "
                "FROM ia_chamadas WHERE id = :i"), {"i": chamada}).one()
            assert tuple(antiga) == (None, None, [])
            ok = _tema(perfil)
            conn.execute(text(TEMA), ok)

        # ---- CHECKs e índices únicos ----
        _recusa(TEMA, _tema(perfil, id=uuid.uuid4()), "uq_aprendizado_temas_nome")
        _recusa(TEMA, _tema(perfil, nome="", norm="x"), "ck_aprendizado_temas_nome")
        _recusa(TEMA, _tema(perfil, nome="A", norm="a", pal=[f"p{i}" for i in range(21)]),
                "ck_aprendizado_temas_palavras")
        _recusa(TEMA, _tema(perfil, nome="B", norm="b", junt=ok["id"]),
                "ck_aprendizado_temas_juntado")
        auto = uuid.uuid4()
        _recusa(TEMA, _tema(perfil, id=auto, nome="C", norm="c", junt=auto,
                            arq="2026-10-06T10:00:00-03"), "ck_aprendizado_temas_juntado_outro")
        with engine.begin() as conn:  # arquivado com o mesmo nome passa
            conn.execute(text(TEMA), _tema(perfil, arq="2026-10-06T10:00:00-03"))

        pref = ("INSERT INTO aprendizado_preferencias (id, perfil_id, conta_id, hashtags_evitar, "
                "padroes) VALUES (:id, :p, NULL, :ev, CAST(:pad AS jsonb))")
        with engine.begin() as conn:
            conn.execute(text(pref), {"id": uuid.uuid4(), "p": perfil, "ev": [], "pad": "[]"})
        _recusa(pref, {"id": uuid.uuid4(), "p": perfil, "ev": [], "pad": "[]"},
                "uq_aprendizado_preferencias_perfil")

        analise = ("INSERT INTO aprendizado_analises (id, perfil_id, estado, medida, n, "
                   "com_quadros, quadros_por_video, melhores, comparaveis, resumo_estatistico, "
                   "custo_estimado_usd, erro_code, taxonomia_versao, pedido_por) VALUES (:id, :p, "
                   "CAST(:e AS aprendizado_analise_estado), 'h24', :n, :cq, :qpv, '{}', '{}', "
                   "'[]'::jsonb, 0.01, :erro, 1, :u)")

        def _a(**kw):
            return {"id": uuid.uuid4(), "p": perfil, "e": "pendente", "n": 8, "cq": False,
                    "qpv": 0, "erro": None, "u": dono} | kw

        with engine.begin() as conn:
            conn.execute(text(analise), _a())
            conn.execute(text(analise), _a(cq=True, qpv=4))
        _recusa(analise, _a(n=16), "ck_aprendizado_analises_n")
        _recusa(analise, _a(cq=True, qpv=0), "ck_aprendizado_analises_quadros")
        _recusa(analise, _a(e="erro"), "ck_aprendizado_analises_erro")

        decisao = ("INSERT INTO aprendizado_decisoes (id, perfil_id, chave, tipo, origem, "
                   "analise_id, estado, evidencia, n_decisao, faixa_decisao) VALUES (:id, :p, "
                   "'k', :t, :o, NULL, CAST(:e AS aprendizado_decisao), '{}'::jsonb, 1, 'forte')")

        def _d(**kw):
            return {"id": uuid.uuid4(), "p": perfil, "t": "tema_ampliar", "o": "regra",
                    "e": "aceita"} | kw

        with engine.begin() as conn:
            conn.execute(text(decisao), _d())
        _recusa(decisao, _d(t="outro"), "ck_aprendizado_decisoes_tipo")
        _recusa(decisao, _d(o="hipotese"), "ck_aprendizado_decisoes_hipotese")
        _recusa(decisao, _d(e="aberta"), "ck_aprendizado_decisoes_aberta")

        # ---- desce e sobe com dados nas tabelas da 008 ----
        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
            assert conn.execute(text("SELECT count(*) FROM ia_chamadas WHERE id = :i"),
                                {"i": chamada}).scalar() == 1
        command.upgrade(_cfg(), "head")
    finally:
        command.upgrade(_cfg(), "head")
