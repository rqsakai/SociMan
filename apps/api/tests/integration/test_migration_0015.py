"""Migration 0015 (spec 010, T005): sobe sobre a 0014, cria as 4 tabelas e os CHECKs da cena,
amplia as anotações (proposta de cena em perfil ou cena), desce (recusando quando já existe
proposta de cena) e sobe de novo."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0014_mcp"
TABELAS = ("cenas", "cena_tomadas", "cena_usos", "cena_padroes")
PERFIL = ("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'Perfil')")
CENA = ("INSERT INTO cenas (id, perfil_id, nome, acao, duracao_s, status, prompt_congelado, "
        "negative_congelado, produto_nome, produto_imagem_id) VALUES (:id, :p, 'Cena', 'acts', "
        ":d, :s, :pc, :nc, :pn, :pi)")
ANOTACAO = ("INSERT INTO anotacoes (id, alvo_tipo, alvo_id, tipo, texto, campos, autor_kind, "
            "autor_user_id) VALUES (gen_random_uuid(), :alvo, gen_random_uuid(), :tipo, 'x', "
            "CAST(:campos AS jsonb), 'user', :u)")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _recusa(sql: str, params: dict, nome: str) -> None:
    with pytest.raises(IntegrityError, match=nome), get_engine().begin() as conn:
        conn.execute(text(sql), params)


def _cena(perfil_id, **kw) -> dict:
    return {"id": uuid.uuid4(), "p": perfil_id, "d": 8, "s": "rascunho", "pc": None, "nc": None,
            "pn": None, "pi": None, **kw}


def test_upgrade_checks_e_downgrade(make_user):
    dono = make_user(role="dono").id
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
        command.upgrade(_cfg(), "head")
        perfil = uuid.uuid4()
        with engine.begin() as conn:
            assert all(_existe(conn, t) for t in TABELAS)
            conn.execute(text(PERFIL), {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
            conn.execute(text(CENA), _cena(perfil))
            conn.execute(text(CENA), _cena(perfil, s="pronta", pc="prompt", nc="neg"))

        # CHECKs da cena
        _recusa(CENA, _cena(perfil, d=5), "ck_cenas_duracao")
        _recusa(CENA, _cena(perfil, pc="prompt", nc="neg"), "ck_cenas_congelado")
        _recusa(CENA, _cena(perfil, s="pronta"), "ck_cenas_congelado")
        with engine.begin() as conn:
            asset = uuid.uuid4()
            conn.execute(text("INSERT INTO assets (id, perfil_id, tipo, name) VALUES "
                              "(:id, :p, 'imagem', 'Foto')"), {"id": asset, "p": perfil})
        _recusa(CENA, _cena(perfil, pi=asset), "ck_cenas_produto")

        # a tomada nasce `flow_manual` (ponto de extensão da 021)
        with engine.begin() as conn:
            assert conn.execute(text(
                "SELECT enum_range(NULL::tomada_origem)::text")).scalar() == "{flow_manual}"
            assert conn.execute(text(
                "SELECT column_default FROM information_schema.columns WHERE table_name = "
                "'cena_tomadas' AND column_name = 'origem'")).scalar().startswith(
                "'flow_manual'")

        # um uso ativo por par (desfeito libera)
        with engine.begin() as conn:
            cena = conn.execute(text("SELECT id FROM cenas WHERE status = 'pronta'")).scalar()
            conteudo = uuid.uuid4()
            conn.execute(text(
                "INSERT INTO conteudos (id, perfil_id, origem, titulo, video_key, poster_key, "
                "duration_ms) VALUES (:id, :p, 'video_proprio', 't', :k, 'p.jpg', 8000)"),
                {"id": conteudo, "p": perfil, "k": f"conteudos/{conteudo}/video.mp4"})
            uso = ("INSERT INTO cena_usos (id, cena_id, conteudo_id) VALUES "
                   "(gen_random_uuid(), :c, :t)")
            conn.execute(text(uso), {"c": cena, "t": conteudo})
        _recusa(uso, {"c": cena, "t": conteudo}, "uq_cena_usos_ativo")
        with engine.begin() as conn:
            conn.execute(text("UPDATE cena_usos SET desfeito_em = now()"))
            conn.execute(text(uso), {"c": cena, "t": conteudo})

        # anotações: proposta de cena em perfil/cena, nunca em destino; texto só em destino
        with engine.begin() as conn:
            for alvo in ("perfil", "cena"):
                conn.execute(text(ANOTACAO), {"alvo": alvo, "tipo": "proposta_cena",
                                              "campos": '{"acao": "x"}', "u": dono})
        _recusa(ANOTACAO, {"alvo": "destino", "tipo": "proposta_cena", "campos": "{}",
                           "u": dono}, "ck_anotacoes_proposta_alvo")
        _recusa(ANOTACAO, {"alvo": "perfil", "tipo": "proposta_texto", "campos": "{}",
                           "u": dono}, "ck_anotacoes_proposta_alvo")
        _recusa(ANOTACAO, {"alvo": "perfil", "tipo": "proposta_cena", "campos": None,
                           "u": dono}, "ck_anotacoes_campos")

        # o downgrade recusa com proposta de cena; sem ela, desce e volta o CHECK antigo
        with pytest.raises(RuntimeError, match="recusado"):
            command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM anotacoes"))
        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not any(_existe(conn, t) for t in TABELAS)
        _recusa(ANOTACAO, {"alvo": "perfil", "tipo": "proposta_texto", "campos": "{}",
                           "u": dono}, "ck_anotacoes_proposta_em_destino")
    finally:
        command.upgrade(_cfg(), "head")
