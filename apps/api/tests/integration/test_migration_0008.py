"""Migration 0008 (spec 008, T006): `sugestoes_texto` vira `ia_chamadas` sem perder as linhas
da 006 (mesmos ids, FK de `postagens.sugestao_id` intacta), e o downgrade volta tudo."""

import uuid
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0007_envio_progresso"

COLUNAS_006 = ["id", "corte_id", "plataforma", "model", "prompt_version", "resultado",
               "ajustes", "erro_code", "input_tokens", "output_tokens", "cache_read_tokens",
               "duration_ms", "created_at", "created_by"]


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _colunas(conn, tabela: str) -> list[str]:
    return list(conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t "
        "ORDER BY ordinal_position"), {"t": tabela}).scalars())


def _constraints(conn, tabela: str) -> set[str]:
    return set(conn.execute(text(
        "SELECT conname FROM pg_constraint WHERE conrelid = CAST(:t AS regclass)"),
        {"t": tabela}).scalars())


def _semear_006(conn) -> dict[str, uuid.UUID]:
    """Perfil, conta, corte, três sugestões da 006 (erro, usada por uma postagem, sem uso)."""
    perfil, conta, corte = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'Teste')"),
                 {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    conn.execute(text(
        "INSERT INTO contas (id, perfil_id, platform, handle, url) "
        "VALUES (:id, :p, 'tiktok', 'teste', 'https://www.tiktok.com/@teste')"),
        {"id": conta, "p": perfil})
    conn.execute(text(
        "INSERT INTO cortes (id, perfil_id, hook_text, status, kit_version, kit_tokens, "
        "original_filename, original_key, original_content_type, original_bytes, duration_ms, "
        "width, height, fps, video_codec, original_sha256) VALUES (:id, :p, '', 'na_fila', 1, "
        "CAST('{}' AS jsonb), 'a.mp4', :k, 'video/mp4', 1, 1000, 1080, 1920, 30, 'h264', 'x')"),
        {"id": corte, "p": perfil, "k": f"k/{corte}"})
    ids = {"erro": uuid.uuid4(), "usada": uuid.uuid4(), "livre": uuid.uuid4()}
    sql = text(
        "INSERT INTO sugestoes_texto (id, corte_id, plataforma, model, prompt_version, "
        "resultado, erro_code, input_tokens, output_tokens, cache_read_tokens, duration_ms) "
        "VALUES (:id, :c, 'tiktok', 'claude-sonnet-5-5', 'textos/1', CAST(:r AS jsonb), :e, "
        ":i, :o, :cr, 900)")
    resultado = '{"titulo": "T", "descricao": "D", "hashtags": ["#a", "#b", "#c"]}'
    conn.execute(sql, {"id": ids["erro"], "c": corte, "r": None, "e": "timeout", "i": None,
                       "o": None, "cr": None})
    conn.execute(sql, {"id": ids["usada"], "c": corte, "r": resultado, "e": None, "i": 1800,
                       "o": 220, "cr": 1200})
    conn.execute(sql, {"id": ids["livre"], "c": corte, "r": resultado, "e": None, "i": 1000,
                       "o": 100, "cr": 0})
    ids["postagem"] = uuid.uuid4()
    conn.execute(text("INSERT INTO postagens (id, corte_id, conta_id, sugestao_id) "
                      "VALUES (:id, :c, :k, :s)"),
                 {"id": ids["postagem"], "c": corte, "k": conta, "s": ids["usada"]})
    ids.update(perfil=perfil, corte=corte, conta=conta)
    return ids


def _estado_upgrade(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(text(
        "SELECT id, tipo_campo, perfil_id, entity_type, entity_id, corte_id, plataforma::text, "
        "desfecho::text, custo_usd, precos_versao, prompt_version, regras_version, proposta, "
        "erro_code FROM ia_chamadas ORDER BY id"))]


def _estado_006(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(text(
        "SELECT id, corte_id, plataforma::text, model, prompt_version, resultado, ajustes, "
        "erro_code, input_tokens, output_tokens, cache_read_tokens, duration_ms "
        "FROM sugestoes_texto ORDER BY id"))]


def test_upgrade_preserva_a_006_downgrade_volta_e_upgrade_de_novo_e_identico():
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "ia_chamadas") and not _existe(conn, "ia_regras")
            ids = _semear_006(conn)
            antes = _estado_006(conn)
        command.upgrade(_cfg(), "head")

        with engine.begin() as conn:
            assert not _existe(conn, "sugestoes_texto") and _existe(conn, "ia_regras")
            linhas = {r[0]: r for r in _estado_upgrade(conn)}
            assert set(linhas) == {ids["erro"], ids["usada"], ids["livre"]}
            for row in linhas.values():
                assert row[1] == "postagem.textos" and row[2] == ids["perfil"]
                assert row[3] == "corte" and row[4] == ids["corte"] == row[5]
                assert row[6] == "tiktok" and row[10] == "textos/1" and row[11] == 0
            assert linhas[ids["erro"]][7] == "erro" and linhas[ids["erro"]][8] is None
            assert linhas[ids["erro"]][9] is None and linhas[ids["erro"]][12] is None
            assert linhas[ids["usada"]][7] == "aplicada"
            assert linhas[ids["livre"]][7] == "sem_acao"
            # 1800 × 2 + 220 × 10 + 1200 × 0,20 = 6.040 por milhão.
            assert linhas[ids["usada"]][8] == Decimal("0.006040")
            assert linhas[ids["usada"]][9] == "2026-09"
            assert linhas[ids["livre"]][8] == Decimal("0.003000")
            assert linhas[ids["usada"]][12]["titulo"] == "T"
            # A FK de postagens segue a tabela renomeada.
            fk = conn.execute(text(
                "SELECT confrelid::regclass::text FROM pg_constraint "
                "WHERE conname = 'postagens_sugestao_id_fkey'")).scalar()
            assert fk == "ia_chamadas"
            assert conn.execute(text("SELECT sugestao_id FROM postagens WHERE id = :id"),
                                {"id": ids["postagem"]}).scalar() == ids["usada"]
            assert {"ia_chamadas_pkey", "ia_chamadas_corte_id_fkey",
                    "ia_chamadas_created_by_fkey", "ia_chamadas_perfil_id_fkey",
                    "ck_ia_chamadas_erro_desfecho"} <= _constraints(conn, "ia_chamadas")
            primeiro = _estado_upgrade(conn)
            # Uma chamada de outro tipo, feita depois: some no downgrade (só dev).
            outra = uuid.uuid4()
            conn.execute(text(
                "INSERT INTO ia_chamadas (id, tipo_campo, perfil_id, entity_type, model, "
                "prompt_version, duration_ms) VALUES (:id, 'perfil.bio', :p, 'perfil', "
                "'claude-sonnet-5-5', 'ia/1', 10)"), {"id": outra, "p": ids["perfil"]})
            conn.execute(text("UPDATE postagens SET sugestao_id = :s WHERE id = :id"),
                         {"s": outra, "id": ids["postagem"]})

        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not _existe(conn, "ia_chamadas") and not _existe(conn, "ia_regras")
            assert _colunas(conn, "sugestoes_texto") == COLUNAS_006
            assert _estado_006(conn) == antes
            assert {"sugestoes_texto_pkey", "sugestoes_texto_corte_id_fkey",
                    "sugestoes_texto_created_by_fkey"} == _constraints(conn, "sugestoes_texto")
            assert conn.execute(text(
                "SELECT count(*) FROM pg_type WHERE typname = 'ia_desfecho'")).scalar() == 0
            # A postagem que apontava para a chamada apagada fica sem sugestão.
            assert conn.execute(text("SELECT sugestao_id FROM postagens WHERE id = :id"),
                                {"id": ids["postagem"]}).scalar() is None
            conn.execute(text("UPDATE postagens SET sugestao_id = :s WHERE id = :id"),
                         {"s": ids["usada"], "id": ids["postagem"]})
    finally:
        command.upgrade(_cfg(), "head")

    with engine.begin() as conn:
        assert _estado_upgrade(conn) == primeiro


def test_check_erro_code_e_desfecho():
    engine = get_engine()
    with engine.begin() as conn:
        perfil = uuid.uuid4()
        conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'T')"),
                     {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    sql = text("INSERT INTO ia_chamadas (id, tipo_campo, perfil_id, entity_type, model, "
               "prompt_version, duration_ms, erro_code, desfecho) VALUES (:id, 'perfil.bio', "
               ":p, 'perfil', 'm', 'ia/1', 1, :e, CAST(:d AS ia_desfecho))")
    for erro, desfecho in (("timeout", "sem_acao"), (None, "erro")):
        try:
            with engine.begin() as conn:
                conn.execute(sql, {"id": uuid.uuid4(), "p": perfil, "e": erro, "d": desfecho})
        except Exception as exc:  # noqa: BLE001
            assert "ck_ia_chamadas_erro_desfecho" in str(exc)
        else:
            raise AssertionError("o check deveria recusar")
    with engine.begin() as conn:
        conn.execute(sql, {"id": uuid.uuid4(), "p": perfil, "e": "timeout", "d": "erro"})
        conn.execute(sql, {"id": uuid.uuid4(), "p": perfil, "e": None, "d": "sem_acao"})
