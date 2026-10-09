"""Migration 0009 (spec 014, T009): sobe com dados da 006 sem perder postagens nem histórico
(`entity_versions` idêntica), os CHECKs do princípio I barram modos automáticos, e o downgrade
volta tudo (e recusa com vídeo próprio)."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0008_assistente_ia"


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _corte(conn, perfil, status: str, *, arquivado: bool = False, titulo: str | None = None,
           hook: str = "", autor=None) -> uuid.UUID:
    cid = uuid.uuid4()
    revisao = status == "revisao"
    conn.execute(text(
        "INSERT INTO cortes (id, perfil_id, hook_text, status, kit_version, kit_tokens, "
        "original_filename, original_key, original_content_type, original_bytes, duration_ms, "
        "width, height, fps, video_codec, original_sha256, result_key, openshorts_title, "
        "archived_at, created_by) VALUES (:id, :p, :hook, CAST(:s AS corte_status), :kv, "
        "CAST(:kt AS jsonb), 'clipe-1.mp4', :k, 'video/mp4', 1, 1000, 1080, 1920, 30, 'h264', "
        "'x', :rk, :t, :arq, :autor)"),
        {"id": cid, "p": perfil, "hook": hook, "s": status, "kv": None if revisao else 1,
         "kt": None if revisao else "{}", "k": f"k/{cid}",
         "rk": f"r/{cid}" if status == "pronto" else None, "t": titulo,
         "arq": datetime.now(UTC) if arquivado else None, "autor": autor})
    return cid


def _semear_006(conn, dono: uuid.UUID, membro: uuid.UUID) -> dict:
    perfil, conta, conta2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'Teste')"),
                 {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    for cid, handle in ((conta, "um"), (conta2, "dois")):
        conn.execute(text(
            "INSERT INTO contas (id, perfil_id, platform, handle, url) "
            "VALUES (:id, :p, 'tiktok', :h, :u)"),
            {"id": cid, "p": perfil, "h": handle, "u": f"https://www.tiktok.com/@{handle}"})
    ids = {
        "revisao": _corte(conn, perfil, "revisao", hook="Olha só", autor=membro),
        "pronto": _corte(conn, perfil, "pronto", titulo="Título do OpenShorts", autor=dono),
        "arquivado": _corte(conn, perfil, "pronto", arquivado=True, titulo="",
                            hook="", autor=dono),
    }
    agora = datetime.now(UTC)
    sql = text(
        "INSERT INTO postagens (id, corte_id, conta_id, titulo, estado, planned_at, posted_at, "
        "archived_at, created_by, updated_by, updated_at) VALUES (:id, :c, :k, :t, "
        "CAST(:e AS postagem_estado), :pl, :po, :arq, :cb, :ub, :ua)")
    postagens = {
        "rascunho": (ids["revisao"], conta, "rascunho", None, None, None, membro, None),
        "agendado": (ids["pronto"], conta, "agendado", agora + timedelta(days=1), None, None,
                     membro, dono),
        "postado": (ids["pronto"], conta2, "postado", agora - timedelta(days=1), agora, None,
                    dono, None),
        "arquivada": (ids["pronto"], conta, "rascunho", None, None, agora, dono, dono),
    }
    for nome, (c, k, e, pl, po, arq, cb, ub) in postagens.items():
        ids[f"p_{nome}"] = uuid.uuid4()
        conn.execute(sql, {"id": ids[f"p_{nome}"], "c": c, "k": k, "t": nome, "e": e, "pl": pl,
                           "po": po, "arq": arq, "cb": cb, "ub": ub,
                           "ua": agora - timedelta(hours=2)})
    ids["ia"] = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO ia_chamadas (id, tipo_campo, perfil_id, entity_type, entity_id, corte_id, "
        "model, prompt_version, duration_ms) VALUES (:id, 'postagem.textos', :p, 'corte', :c, "
        ":c, 'claude-sonnet-5-5', 'ia/1', 10)"), {"id": ids["ia"], "p": perfil,
                                                   "c": ids["pronto"]})
    ev = text(
        "INSERT INTO entity_versions (entity_type, entity_id, version, action, actor_kind, "
        "actor_user_id, after, changed_fields, details) VALUES (:t, :id, 1, 'created', 'user', "
        ":u, CAST(:a AS jsonb), ARRAY['estado'], CAST('{}' AS jsonb))")
    for nome in ("rascunho", "agendado", "postado"):
        conn.execute(ev, {"t": "postagem", "id": ids[f"p_{nome}"], "u": dono,
                          "a": f'{{"estado": "{postagens[nome][2]}"}}'})
    conn.execute(ev, {"t": "corte", "id": ids["pronto"], "u": dono, "a": '{"status": "pronto"}'})
    ids.update(perfil=perfil, conta=conta, conta2=conta2)
    return ids


def _historico(conn) -> tuple:
    return tuple(conn.execute(text(
        "SELECT count(*), md5(string_agg((to_jsonb(t) - 'actor_mcp_client_id')::text, '|' "
        "ORDER BY t.id)) FROM entity_versions t"  # a coluna da 0014 (spec 009) fica de fora
    )).one())


def _postagens_006(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(text(
        "SELECT id, corte_id, conta_id, titulo, estado::text, planned_at, posted_at, "
        "archived_at, created_by, updated_by, version FROM postagens ORDER BY id"))]


def _contagens(conn) -> tuple:
    return tuple(conn.execute(text(
        "SELECT (SELECT count(*) FROM cortes), (SELECT count(*) FROM postagens), "
        "(SELECT count(*) FROM contas), (SELECT count(*) FROM ia_chamadas), "
        "(SELECT count(*) FROM notificacoes)")).one())


def test_upgrade_preserva_a_006_e_o_historico_downgrade_volta(make_user):
    dono = make_user(role="dono").id
    membro = make_user(role="membro").id
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "conteudos")
            ids = _semear_006(conn, dono, membro)
            hist = _historico(conn)
            antes = _postagens_006(conn)
            contagens = _contagens(conn)
        # Só até a 0009: os CHECKs da 014 conferidos abaixo a 0010 troca (spec 015).
        command.upgrade(_cfg(), "0009_central_conteudos")

        with engine.begin() as conn:
            # Uma linha por corte (arquivados inclusive), com o mesmo id.
            conteudos = {r[0]: r[1:] for r in conn.execute(text(
                "SELECT id, corte_id, origem::text, titulo, perfil_id, archived_at, version, "
                "created_by FROM conteudos"))}
            assert set(conteudos) == {ids["revisao"], ids["pronto"], ids["arquivado"]}
            for cid, (corte_id, origem, _, perfil, arq, version, _) in conteudos.items():
                assert corte_id == cid and origem == "corte" and perfil == ids["perfil"]
                assert arq is None and version == 1
            assert conteudos[ids["pronto"]][2] == "Título do OpenShorts"
            assert conteudos[ids["revisao"]][2] == "Olha só"
            assert conteudos[ids["arquivado"]][2] == "clipe-1.mp4"
            assert conteudos[ids["revisao"]][6] == membro
            assert conn.execute(text(
                "SELECT count(*) FROM cortes c WHERE NOT EXISTS "
                "(SELECT 1 FROM conteudos t WHERE t.id = c.id)")).scalar() == 0

            # Estados mapeados, aprovação em agendado/postado, modo lembrete, conteudo_id.
            rows = {r[0]: r[1:] for r in conn.execute(text(
                "SELECT id, conteudo_id, estado::text, modo::text, aprovado_em, aprovado_por, "
                "updated_at, antecedencia_min, pedido_em, recusa_motivo FROM postagens"))}
            assert rows[ids["p_rascunho"]][:2] == (ids["revisao"], "pendente")
            assert rows[ids["p_arquivada"]][1] == "pendente"
            assert rows[ids["p_agendado"]][:2] == (ids["pronto"], "agendado")
            assert rows[ids["p_postado"]][1] == "postado"
            for nome in ("rascunho", "arquivada"):
                assert rows[ids[f"p_{nome}"]][3:5] == (None, None)
            # aprovado_por = COALESCE(updated_by, created_by); aprovado_em = updated_at.
            assert rows[ids["p_agendado"]][4] == dono
            assert rows[ids["p_postado"]][4] == dono
            for nome in ("agendado", "postado"):
                assert rows[ids[f"p_{nome}"]][3] == rows[ids[f"p_{nome}"]][5]
            assert {r[2] for r in rows.values()} == {"lembrete"}
            assert all(r[6:] == (None, None, None) for r in rows.values())
            cols = set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'postagens'")).scalars())
            assert "corte_id" not in cols and "conteudo_id" in cols

            assert conn.execute(text("SELECT conteudo_id FROM ia_chamadas WHERE id = :id"),
                                {"id": ids["ia"]}).scalar() == ids["pronto"]
            assert set(conn.execute(text(
                "SELECT intervalo_min_minutos FROM contas")).scalars()) == {30}
            tipos = set(conn.execute(text(
                "SELECT unnest(enum_range(NULL::notificacao_tipo))::text")).scalars())
            assert {"aprovacao_pedida", "aprovacao_respondida"} <= tipos
            # Nenhuma linha de entity_versions escrita nem alterada.
            assert _historico(conn) == hist
            depois = _contagens(conn)
            assert depois == contagens

        # Guardas do princípio I no banco.
        for sql, check in (
            ("UPDATE postagens SET modo = 'publicar' WHERE id = :id", "ck_postagens_modo_014"),
            ("UPDATE postagens SET estado = 'publicado' WHERE id = :id",
             "ck_postagens_estados_015"),
        ):
            with pytest.raises(IntegrityError, match=check), engine.begin() as conn:
                conn.execute(text(sql), {"id": ids["p_agendado"]})
        with pytest.raises(IntegrityError, match="uq_postagens_conteudo_conta_ativa"), \
                engine.begin() as conn:
            conn.execute(text("INSERT INTO postagens (id, conteudo_id, conta_id) "
                              "VALUES (:id, :c, :k)"),
                         {"id": uuid.uuid4(), "c": ids["pronto"], "k": ids["conta"]})

        command.downgrade(_cfg(), ANTERIOR)
        with engine.begin() as conn:
            assert not _existe(conn, "conteudos")
            assert _postagens_006(conn) == antes  # rascunho volta; nada mais muda
            assert _contagens(conn) == contagens
            assert _historico(conn) == hist
            for tipo in ("destino_estado", "agendamento_modo", "conteudo_origem"):
                assert conn.execute(text("SELECT count(*) FROM pg_type WHERE typname = :t"),
                                    {"t": tipo}).scalar() == 0
            cols = set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'contas'")).scalars())
            assert "intervalo_min_minutos" not in cols
    finally:
        command.upgrade(_cfg(), "head")

    with engine.begin() as conn:
        assert _historico(conn) == hist


def test_downgrade_recusa_com_video_proprio():
    engine = get_engine()
    with engine.begin() as conn:
        perfil = uuid.uuid4()
        conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'T')"),
                     {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
        cid = uuid.uuid4()
        conn.execute(text(
            "INSERT INTO conteudos (id, perfil_id, origem, video_key, poster_key, duration_ms) "
            "VALUES (:id, :p, 'video_proprio', :k, 'poster.jpg', 1000)"),
            {"id": cid, "p": perfil, "k": f"conteudos/{cid}/video.mp4"})
    with pytest.raises(RuntimeError, match="vídeo próprio"):
        command.downgrade(_cfg(), ANTERIOR)
    with engine.begin() as conn:  # nada mudou
        assert _existe(conn, "conteudos")
        assert conn.execute(text("SELECT count(*) FROM conteudos")).scalar() == 1


def test_check_da_origem_do_conteudo():
    engine = get_engine()
    with engine.begin() as conn:
        perfil = uuid.uuid4()
        conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'T')"),
                     {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    # Vídeo próprio sem arquivo; origem corte com corte_id diferente do id.
    for sql in (
        "INSERT INTO conteudos (id, perfil_id, origem) VALUES (:id, :p, 'video_proprio')",
        "INSERT INTO conteudos (id, perfil_id, origem) VALUES (:id, :p, 'corte')",
    ):
        with pytest.raises(IntegrityError, match="ck_conteudos_origem"), engine.begin() as conn:
            conn.execute(text(sql), {"id": uuid.uuid4(), "p": perfil})
