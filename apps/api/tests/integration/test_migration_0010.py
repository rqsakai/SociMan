"""Migration 0010 (spec 015, T015): sobe com destinos da 014 em todos os estados sem mudar
nenhum (e sem escrever histórico), os CHECKs novos barram o que o princípio I proíbe, o
downgrade recusa com dados da 015 e, sem eles, volta os CHECKs da 014; subir de novo funciona
(`ADD VALUE IF NOT EXISTS`)."""

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
ANTERIOR = "0009_central_conteudos"
ESTADOS_014 = ("pendente", "aprovacao_pedida", "aprovado", "agendado", "postado")


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _checks(conn) -> set[str]:
    return set(conn.execute(text(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'postagens'::regclass "
        "AND contype = 'c'")).scalars())


def _semear_014(conn, dono: uuid.UUID) -> dict:
    perfil, conta = uuid.uuid4(), uuid.uuid4()
    conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'T')"),
                 {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    conn.execute(text("INSERT INTO contas (id, perfil_id, platform, handle, url) "
                      "VALUES (:id, :p, 'tiktok', 'um', 'https://www.tiktok.com/@um')"),
                 {"id": conta, "p": perfil})
    agora = datetime.now(UTC)
    ids: dict = {"perfil": perfil, "conta": conta}
    # Um conteúdo por destino (um destino ativo por conteúdo e conta).
    for estado in (*ESTADOS_014, "arquivado"):
        conteudo, destino = uuid.uuid4(), uuid.uuid4()
        conn.execute(text(
            "INSERT INTO conteudos (id, perfil_id, origem, video_key, poster_key, duration_ms) "
            "VALUES (:id, :p, 'video_proprio', :k, 'poster.jpg', 1000)"),
            {"id": conteudo, "p": perfil, "k": f"conteudos/{conteudo}/video.mp4"})
        aprovado = estado in ("aprovado", "agendado", "postado")
        conn.execute(text(
            "INSERT INTO postagens (id, conteudo_id, conta_id, titulo, estado, planned_at, "
            "aprovado_por, aprovado_em, pedido_em, archived_at, created_by) VALUES (:id, :c, :k, "
            ":t, CAST(:e AS destino_estado), :pl, :ap, :ae, :pe, :arq, :cb)"),
            {"id": destino, "c": conteudo, "k": conta, "t": estado,
             "e": "pendente" if estado == "arquivado" else estado,
             "pl": agora + timedelta(hours=1) if estado in ("agendado", "postado") else None,
             "ap": dono if aprovado else None, "ae": agora if aprovado else None,
             "pe": agora if estado == "aprovacao_pedida" else None,
             "arq": agora if estado == "arquivado" else None, "cb": dono})
        conn.execute(text(
            "INSERT INTO entity_versions (entity_type, entity_id, version, action, actor_kind, "
            "actor_user_id, after, changed_fields) VALUES ('postagem', :id, 1, 'created', "
            "'user', :u, CAST(:a AS jsonb), ARRAY['estado'])"),
            {"id": destino, "u": dono, "a": f'{{"estado": "{estado}"}}'})
        ids[estado] = destino
    return ids


def _destinos(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(text(
        "SELECT id, conteudo_id, conta_id, titulo, estado::text, modo::text, planned_at, "
        "aprovado_por, aprovado_em, archived_at, version, updated_at FROM postagens ORDER BY id"))]


def _historico(conn) -> tuple:
    return tuple(conn.execute(text(
        "SELECT count(*), md5(string_agg((to_jsonb(t) - 'actor_mcp_client_id')::text, '|' "
        "ORDER BY t.id)) FROM entity_versions t"  # a coluna da 0014 (spec 009) fica de fora
    )).one())


def _conexao(conn, conta, dono, *, open_id: str = "open-um") -> uuid.UUID:
    cid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO conexoes (id, conta_id, rede, open_id, username, escopos, estado, "
        "conectado_por, conectado_em) VALUES (:id, :c, 'tiktok', :o, 'um', "
        "ARRAY['video.upload'], 'conectada', :u, now())"),
        {"id": cid, "c": conta, "o": open_id, "u": dono})
    return cid


def _tentativa(conn, destino, conexao, *, numero: int = 1, fase: str = "iniciando",
               publish_id: str | None = None, partes: int = 0, concluida: bool = False) -> None:
    conn.execute(text(
        "INSERT INTO publicacao_tentativas (id, destino_id, numero, conexao_id, rede, modo, "
        "fase, disparo, video_ref, video_etag, video_bytes, chunk_size, total_partes, "
        "partes_enviadas, publish_id, concluida_em) VALUES (:id, :d, :n, :c, 'tiktok', "
        "'criar_rascunho', CAST(:f AS tentativa_fase), 'agendador', 'k', 'e', 10, 10, 1, :p, "
        ":pid, :fim)"),
        {"id": uuid.uuid4(), "d": destino, "n": numero, "c": conexao, "f": fase, "p": partes,
         "pid": publish_id, "fim": datetime.now(UTC) if concluida else None})


def _recusa(sql: str, params: dict, nome: str) -> None:
    with pytest.raises(IntegrityError, match=nome), get_engine().begin() as conn:
        conn.execute(text(sql), params)


def test_upgrade_preserva_a_014_checks_e_downgrade(make_user):
    dono = make_user(role="dono").id
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "conexoes")
            ids = _semear_014(conn, dono)
            antes, hist = _destinos(conn), _historico(conn)
        command.upgrade(_cfg(), "head")

        with engine.begin() as conn:
            assert _destinos(conn) == antes  # nenhum destino mudou
            assert _historico(conn) == hist  # nenhuma versão escrita
            assert [tuple(r) for r in conn.execute(text(
                "SELECT id, envios_habilitados, version FROM publicacao_config"))] == [
                (1, False, 1)]
            assert set(conn.execute(text(
                "SELECT falha_incerta FROM postagens")).scalars()) == {False}
            checks = _checks(conn)
            assert {"ck_postagens_modo_015", "ck_postagens_execucao",
                    "ck_postagens_auto_decisao", "ck_postagens_publicar_snapshot"} <= checks
            assert not {"ck_postagens_modo_014", "ck_postagens_estados_015"} & checks
            tipos = set(conn.execute(text(
                "SELECT unnest(enum_range(NULL::notificacao_tipo))::text")).scalars())
            assert {"rascunho_criado", "envio_publicado", "envio_rede_falhou",
                    "envio_aguardando_vaga", "conexao_precisa_reconectar"} <= tipos

        # CHECKs novos com INSERT/UPDATE direto.
        agendado = {"id": ids["agendado"], "u": dono}
        _recusa("UPDATE postagens SET modo = 'rascunho_e_publicar' WHERE id = :id",
                {"id": ids["pendente"]}, "ck_postagens_modo_015")
        _recusa("UPDATE postagens SET estado = 'enviando' WHERE id = :id", agendado,
                "ck_postagens_execucao")
        _recusa("UPDATE postagens SET estado = 'falhou' WHERE id = :id", agendado,
                "ck_postagens_execucao")
        _recusa("UPDATE postagens SET modo = 'criar_rascunho' WHERE id = :id", agendado,
                "ck_postagens_auto_decisao")
        _recusa("UPDATE postagens SET modo = 'publicar', agendado_por = :u WHERE id = :id",
                agendado, "ck_postagens_publicar_snapshot")
        _recusa("UPDATE postagens SET modo = 'criar_rascunho', estado = 'enviando', "
                "agendado_por = :u, aprovado_em = NULL WHERE id = :id", agendado,
                "ck_postagens_aprovado")
        with engine.begin() as conn:  # o permitido passa
            conn.execute(text("UPDATE postagens SET modo = 'criar_rascunho', agendado_por = :u "
                              "WHERE id = :id"), agendado)
            conexao = _conexao(conn, ids["conta"], dono)
            _tentativa(conn, ids["agendado"], conexao)
        _recusa("INSERT INTO conexoes (id, conta_id, rede, open_id, username, escopos, estado, "
                "conectado_por, conectado_em) VALUES (gen_random_uuid(), :c, 'tiktok', 'outro', "
                "'um', ARRAY['video.upload'], 'conectada', :u, now())",
                {"c": ids["conta"], "u": dono}, "uq_conexoes_conta_viva")
        _recusa("UPDATE conexoes SET estado = 'desconectada' WHERE id = :id", {"id": conexao},
                "ck_conexoes_desconectada")
        for kwargs, nome in (
            ({"numero": 2}, "uq_tentativas_destino_aberta"),
            ({"numero": 3, "fase": "enviando_partes"}, "ck_tentativas_publish_id"),
            ({"numero": 4, "fase": "recusada"}, "ck_tentativas_final"),
            ({"numero": 5, "fase": "sem_vaga", "partes": 2, "concluida": True},
             "ck_tentativas_partes"),
            ({"numero": 1, "fase": "recusada", "concluida": True},
             "uq_tentativas_destino_numero"),
        ):
            with pytest.raises(IntegrityError, match=nome), engine.begin() as conn:
                _tentativa(conn, ids["agendado"], conexao, **kwargs)
        _recusa("INSERT INTO publicacao_config (id) VALUES (2)", {}, "ck_publicacao_config_unica")

        # Downgrade recusa com conexão, tentativa ou destino automático.
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO notificacoes (user_id, tipo, titulo, link, dedupe_key) VALUES "
                "(:u, 'rascunho_criado', 'T', '/app', 'rascunho_criado:x')"), {"u": dono})
        for limpar, motivo in (
            ("DELETE FROM publicacao_tentativas", "tentativa"),
            ("DELETE FROM conexoes", "conexão"),
            ("UPDATE postagens SET modo = 'lembrete', agendado_por = NULL", "modo automático"),
        ):
            with pytest.raises(RuntimeError, match=motivo):
                command.downgrade(_cfg(), ANTERIOR)
            with engine.begin() as conn:
                assert _existe(conn, "conexoes")  # nada mudou
                conn.execute(text(limpar))
        command.downgrade(_cfg(), ANTERIOR)

        with engine.begin() as conn:
            for tabela in ("conexoes", "conexao_credenciais", "publicacao_config",
                           "publicacao_tentativas"):
                assert not _existe(conn, tabela)
            checks = _checks(conn)
            assert {"ck_postagens_modo_014", "ck_postagens_estados_015"} <= checks
            assert "ck_postagens_execucao" not in checks
            assert _destinos(conn) == antes
            assert conn.execute(text("SELECT count(*) FROM notificacoes")).scalar() == 0
            tipos = set(conn.execute(text(
                "SELECT unnest(enum_range(NULL::notificacao_tipo))::text")).scalars())
            assert "rascunho_criado" not in tipos and "aprovacao_pedida" in tipos
            estados = set(conn.execute(text(
                "SELECT unnest(enum_range(NULL::destino_estado))::text")).scalars())
            assert "enviando" in estados  # o PostgreSQL não remove valor de enum
            for tipo in ("conexao_estado", "tentativa_fase"):
                assert conn.execute(text("SELECT count(*) FROM pg_type WHERE typname = :t"),
                                    {"t": tipo}).scalar() == 0
            _recusa("UPDATE postagens SET modo = 'publicar' WHERE id = :id",
                    {"id": ids["pendente"]}, "ck_postagens_modo_014")
    finally:
        command.upgrade(_cfg(), "head")  # subir de novo funciona (IF NOT EXISTS)

    with engine.begin() as conn:
        assert _destinos(conn) == antes
        assert _existe(conn, "publicacao_tentativas")
        assert conn.execute(text("SELECT count(*) FROM publicacao_config")).scalar() == 1
