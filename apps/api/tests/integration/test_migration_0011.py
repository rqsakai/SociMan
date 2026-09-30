"""Migration 0011 (spec 016, T011): sobe sobre uma base da 0010 com conexões e destinos em
todos os estados sem mudar nenhum (e sem escrever histórico); cada CHECK e índice único recusa
com SQL direto; o trigger `metricas_so_insercao` recusa UPDATE e DELETE nas duas tabelas de
fotos, e o TRUNCATE continua funcionando; desce (os avisos dos 2 tipos novos saem, o resto
fica) e sobe de novo (`IF NOT EXISTS`)."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sociman_api.db import get_engine

API_DIR = Path(__file__).resolve().parents[2]
ANTERIOR = "0010_publicacao_tiktok"
TABELAS = ("metricas_series", "metricas_videos", "metricas_video_fotos",
           "metricas_conta_fotos", "metricas_buscas_post")
# Estados da 015 (com o modo que o CHECK da 0010 aceita).
ESTADOS = (("lembrete", "pendente"), ("lembrete", "aprovacao_pedida"),
           ("lembrete", "aprovado"), ("lembrete", "agendado"), ("lembrete", "postado"),
           ("criar_rascunho", "agendado"), ("criar_rascunho", "enviando"),
           ("criar_rascunho", "rascunho_criado"), ("criar_rascunho", "falhou"),
           ("publicar", "publicado"))
MSG_TRIGGER = "metricas: fotos são só de inserção"


def _cfg() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


def _existe(conn, tabela: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:t)"), {"t": tabela}).scalar() is not None


def _semear_015(conn, dono: uuid.UUID) -> dict:
    perfil = uuid.uuid4()
    conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, :slug, 'T')"),
                 {"id": perfil, "slug": f"p-{perfil.hex[:8]}"})
    ids: dict = {"perfil": perfil, "contas": []}
    agora = datetime.now(UTC)
    for n, estado_conexao in enumerate(("conectada", "precisa_reconectar", "desconectada")):
        conta = uuid.uuid4()
        conn.execute(text("INSERT INTO contas (id, perfil_id, platform, handle, url) VALUES "
                          "(:id, :p, 'tiktok', :h, :u)"),
                     {"id": conta, "p": perfil, "h": f"c{n}", "u": f"https://www.tiktok.com/@c{n}"})
        conn.execute(text(
            "INSERT INTO conexoes (id, conta_id, rede, open_id, username, escopos, estado, "
            "conectado_por, conectado_em, desconectado_em) VALUES (gen_random_uuid(), :c, "
            "'tiktok', :o, :h, ARRAY['video.upload'], CAST(:e AS conexao_estado), :u, now(), "
            ":d)"),
            {"c": conta, "o": f"open-{n}", "h": f"c{n}", "e": estado_conexao, "u": dono,
             "d": agora if estado_conexao == "desconectada" else None})
        ids["contas"].append(conta)
    conta = ids["contas"][0]
    for modo, estado in ESTADOS:
        conteudo, destino = uuid.uuid4(), uuid.uuid4()
        conn.execute(text(
            "INSERT INTO conteudos (id, perfil_id, origem, video_key, poster_key, duration_ms) "
            "VALUES (:id, :p, 'video_proprio', :k, 'poster.jpg', 1000)"),
            {"id": conteudo, "p": perfil, "k": f"conteudos/{conteudo}/video.mp4"})
        aprovado = estado not in ("pendente", "aprovacao_pedida")
        auto = modo != "lembrete" and estado in ("agendado", "enviando")
        conn.execute(text(
            "INSERT INTO postagens (id, conteudo_id, conta_id, titulo, estado, modo, planned_at, "
            "aprovado_por, aprovado_em, pedido_em, agendado_por, opcoes_rede, envio_snapshot, "
            "posted_at, created_by) VALUES (:id, :c, :k, :t, CAST(:e AS destino_estado), "
            "CAST(:m AS agendamento_modo), :pl, :ap, :ae, :pe, :ag, NULL, NULL, :pa, :cb)"),
            {"id": destino, "c": conteudo, "k": conta, "t": f"{modo}-{estado}", "e": estado,
             "m": modo, "pl": agora + timedelta(hours=1),
             "ap": dono if aprovado else None, "ae": agora if aprovado else None,
             "pe": agora if estado == "aprovacao_pedida" else None,
             "ag": dono if auto else None,
             "pa": agora if estado == "postado" else None, "cb": dono})
        conn.execute(text(
            "INSERT INTO entity_versions (entity_type, entity_id, version, action, actor_kind, "
            "actor_user_id, after, changed_fields) VALUES ('postagem', :id, 1, 'created', "
            "'user', :u, CAST(:a AS jsonb), ARRAY['estado'])"),
            {"id": destino, "u": dono, "a": f'{{"estado": "{estado}"}}'})
        ids[(modo, estado)] = destino
    return ids


def _destinos(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(text(
        "SELECT id, estado::text, modo::text, planned_at, aprovado_por, posted_at, version, "
        "updated_at FROM postagens ORDER BY id"))]


def _conexoes(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(text(
        "SELECT id, conta_id, open_id, escopos, estado::text, version, updated_at "
        "FROM conexoes ORDER BY id"))]


def _historico(conn) -> tuple:
    return tuple(conn.execute(text(
        "SELECT count(*), md5(string_agg(t::text, '|' ORDER BY t.id)) FROM entity_versions t"
    )).one())


def _recusa(sql: str, params: dict, nome: str) -> None:
    with pytest.raises(IntegrityError, match=nome), get_engine().begin() as conn:
        conn.execute(text(sql), params)


def _trigger_recusa(sql: str, params: dict) -> None:
    with pytest.raises(DBAPIError, match=MSG_TRIGGER), get_engine().begin() as conn:
        conn.execute(text(sql), params)


def _serie(conn, conta) -> uuid.UUID:
    sid = uuid.uuid4()
    conn.execute(text("INSERT INTO metricas_series (id, rede, conta_id) VALUES "
                      "(:id, 'tiktok', :c)"), {"id": sid, "c": conta})
    return sid


def _video(conn, serie, **extra) -> uuid.UUID:
    vid = uuid.uuid4()
    campos = {"id": vid, "serie_id": serie, "rede_video_id": str(2**60 + vid.int % 1000),
              "duracao_s": 30, "publicado_em": datetime.now(UTC), **extra}
    colunas = ", ".join(campos)
    valores = ", ".join(f"CAST(:{c} AS vinculo_metodo)" if c == "vinculo_metodo"
                        else f"CAST(:{c} AS jsonb)" if c == "features" else f":{c}"
                        for c in campos)
    conn.execute(text(f"INSERT INTO metricas_videos ({colunas}) VALUES ({valores})"), campos)
    return vid


def test_upgrade_preserva_a_015_checks_trigger_e_downgrade(make_user):
    dono = make_user(role="dono").id
    engine = get_engine()
    command.downgrade(_cfg(), ANTERIOR)
    try:
        with engine.begin() as conn:
            assert not _existe(conn, "metricas_series")
            ids = _semear_015(conn, dono)
            antes, conexoes, hist = _destinos(conn), _conexoes(conn), _historico(conn)
        command.upgrade(_cfg(), "head")

        with engine.begin() as conn:
            assert _destinos(conn) == antes  # nenhum destino mudou
            assert _conexoes(conn) == conexoes  # nenhuma conexão mudou
            assert _historico(conn) == hist  # nenhuma versão escrita
            for tabela in TABELAS:
                assert conn.execute(text(f"SELECT count(*) FROM {tabela}")).scalar() == 0
            tipos = set(conn.execute(text(
                "SELECT unnest(enum_range(NULL::notificacao_tipo))::text")).scalars())
            assert {"post_detectado", "vinculo_a_confirmar", "rascunho_criado"} <= tipos
            assert set(conn.execute(text(
                "SELECT unnest(enum_range(NULL::vinculo_metodo))::text")).scalars()) == {
                "envio", "casamento", "link", "escolha"}
            assert conn.execute(text("SELECT nextval('metricas_anonima_seq')")).scalar() == 1

        conta, conta2 = ids["contas"][0], ids["contas"][1]
        destino = ids[("criar_rascunho", "rascunho_criado")]
        with engine.begin() as conn:
            serie = _serie(conn, conta)
            video = _video(conn, serie)
            tentativa = uuid.uuid4()
            conexao = conn.execute(text("SELECT id FROM conexoes WHERE conta_id = :c"),
                                   {"c": conta}).scalar()
            conn.execute(text(
                "INSERT INTO publicacao_tentativas (id, destino_id, numero, conexao_id, rede, "
                "modo, fase, disparo, video_ref, video_etag, video_bytes, chunk_size, "
                "total_partes, publish_id, concluida_em) VALUES (:id, :d, 1, :c, 'tiktok', "
                "'criar_rascunho', 'entregue', 'agendador', 'k', 'e', 10, 10, 1, 'p-1', now())"),
                {"id": tentativa, "d": destino, "c": conexao})

        # ---- CHECKs e índices únicos, com SQL direto ----
        _recusa("INSERT INTO metricas_series (id, rede, conta_id) VALUES "
                "(gen_random_uuid(), 'tiktok', :c)", {"c": conta},
                "uq_metricas_series_conta_viva")
        _recusa("INSERT INTO metricas_series (id, rede) VALUES (gen_random_uuid(), 'tiktok')",
                {}, "ck_metricas_series_anonima")  # sem conta e sem anonimizar
        _recusa("UPDATE metricas_series SET anonimizada_em = now() WHERE id = :s",
                {"s": serie}, "ck_metricas_series_anonima")  # anônima com conta
        _recusa("UPDATE metricas_series SET anonimizada_em = now(), conta_id = NULL "
                "WHERE id = :s", {"s": serie}, "ck_metricas_series_anonima")  # sem rótulo
        _recusa("UPDATE metricas_videos SET destino_id = :d WHERE id = :v",
                {"d": destino, "v": video}, "ck_metricas_videos_vinculo")  # sem método
        _recusa("UPDATE metricas_videos SET destino_id = :d, vinculo_metodo = 'link' "
                "WHERE id = :v", {"d": destino, "v": video}, "ck_metricas_videos_vinculo")
        _recusa("UPDATE metricas_videos SET anonimizado_em = now() WHERE id = :v",
                {"v": video}, "ck_metricas_videos_anonimo")
        _recusa("UPDATE metricas_videos SET disponivel = false WHERE id = :v", {"v": video},
                "ck_metricas_videos_indisponivel")
        with engine.begin() as conn:  # o permitido passa
            conn.execute(text(
                "UPDATE metricas_videos SET destino_id = :d, vinculo_metodo = 'envio', "
                "vinculado_em = now(), disponivel = false, indisponivel_desde = now() "
                "WHERE id = :v"), {"d": destino, "v": video})
            outro = _video(conn, serie)
        _recusa("UPDATE metricas_videos SET destino_id = :d, vinculo_metodo = 'casamento', "
                "vinculado_em = now() WHERE id = :v", {"d": destino, "v": outro},
                "uq_metricas_videos_destino")
        _recusa("UPDATE metricas_videos SET rede_video_id = (SELECT rede_video_id FROM "
                "metricas_videos WHERE id = :v) WHERE id = :o", {"v": video, "o": outro},
                "uq_metricas_videos_rede_id")
        foto = ("INSERT INTO metricas_video_fotos (video_id, coletado_em, idade_s, "
                "alvo_idade_min, views, fonte) VALUES (:v, now(), :i, :a, 10, :f)")
        _recusa(foto, {"v": video, "i": -1, "a": 60, "f": "display"},
                "ck_metricas_video_fotos_idade")
        _recusa(foto, {"v": video, "i": 60, "a": -1, "f": "display"},
                "ck_metricas_video_fotos_idade")
        _recusa(foto, {"v": video, "i": 3600, "a": 60, "f": "outra"},
                "ck_metricas_video_fotos_fonte")
        conta_foto = ("INSERT INTO metricas_conta_fotos (serie_id, coletado_em, janela_em, "
                      "seguidores) VALUES (:s, now(), :j, 10)")
        janela = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
        with engine.begin() as conn:
            conn.execute(text(foto), {"v": video, "i": 3600, "a": 60, "f": "display"})
            conn.execute(text(conta_foto), {"s": serie, "j": janela})
            # ON CONFLICT DO NOTHING: a mesma janela não duplica (R7).
            conn.execute(text(foto + " ON CONFLICT DO NOTHING"),
                         {"v": video, "i": 3700, "a": 60, "f": "display"})
            assert conn.execute(text("SELECT count(*) FROM metricas_video_fotos")).scalar() == 1
        _recusa(foto, {"v": video, "i": 3700, "a": 60, "f": "display"},
                "uq_metricas_video_fotos_janela")
        _recusa(conta_foto, {"s": serie, "j": janela}, "uq_metricas_conta_fotos_janela")
        busca = ("INSERT INTO metricas_buscas_post (destino_id, tentativa_id, entregue_em, "
                 "proxima_em, encerrada_em, fim) VALUES (:d, :t, now(), :p, :e, :f)")
        agora = datetime.now(UTC)
        _recusa(busca, {"d": destino, "t": tentativa, "p": agora, "e": None, "f": "prazo"},
                "ck_metricas_buscas_fim")  # fim sem encerrada_em
        _recusa(busca, {"d": destino, "t": tentativa, "p": agora, "e": agora, "f": "prazo"},
                "ck_metricas_buscas_fim")  # encerrada com próxima
        _recusa(busca, {"d": destino, "t": tentativa, "p": None, "e": agora, "f": "outro"},
                "ck_metricas_buscas_fim_valor")
        with engine.begin() as conn:
            conn.execute(text(busca), {"d": destino, "t": tentativa, "p": agora, "e": None,
                                       "f": None})
            # A anonimização completa passa (sem nenhum identificador).
            n = conn.execute(text("SELECT nextval('metricas_anonima_seq')")).scalar()
            conn.execute(text(
                "UPDATE metricas_videos SET rede_video_id = NULL, share_url = NULL, "
                "legenda = NULL, titulo = NULL, destino_id = NULL, vinculo_metodo = NULL, "
                "vinculado_por = NULL, vinculado_em = NULL, proxima_coleta_em = NULL, "
                "features = '{}'::jsonb, anonimizado_em = now() WHERE serie_id = :s"),
                {"s": serie})
            conn.execute(text(
                "UPDATE metricas_series SET conta_id = NULL, rotulo = :r, anonima_n = :n, "
                "anonimizada_em = now(), anonimizada_por = :u WHERE id = :s"),
                {"s": serie, "r": f"Conta anônima {n}", "n": n, "u": dono})
            _serie(conn, conta)  # reconectar cria outra série viva para a mesma conta
            _serie(conn, conta2)

        # ---- trigger: fotos só de inserção ----
        _trigger_recusa("UPDATE metricas_video_fotos SET views = 0", {})
        _trigger_recusa("DELETE FROM metricas_video_fotos", {})
        _trigger_recusa("UPDATE metricas_conta_fotos SET seguidores = 0", {})
        _trigger_recusa("DELETE FROM metricas_conta_fotos", {})
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM metricas_video_fotos")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM metricas_conta_fotos")).scalar() == 1
            conn.execute(text("TRUNCATE metricas_video_fotos, metricas_conta_fotos"))
            assert conn.execute(text("SELECT count(*) FROM metricas_video_fotos")).scalar() == 0
            for tabela in ("metricas_video_fotos", "metricas_conta_fotos"):
                assert conn.execute(text(
                    "SELECT count(*) FROM pg_trigger WHERE tgname = 'metricas_so_insercao' "
                    "AND tgrelid = CAST(:t AS regclass)"), {"t": tabela}).scalar() == 1

        # ---- downgrade: os avisos dos 2 tipos saem, os outros ficam ----
        with engine.begin() as conn:
            for tipo in ("post_detectado", "vinculo_a_confirmar", "rascunho_criado"):
                conn.execute(text(
                    "INSERT INTO notificacoes (user_id, tipo, titulo, link, dedupe_key) VALUES "
                    "(:u, CAST(:t AS notificacao_tipo), 'T', '/app', :k)"),
                    {"u": dono, "t": tipo, "k": f"{tipo}:x"})
        command.downgrade(_cfg(), ANTERIOR)

        with engine.begin() as conn:
            for tabela in TABELAS:
                assert not _existe(conn, tabela)
            assert _destinos(conn) == antes
            assert _conexoes(conn) == conexoes
            assert set(conn.execute(text("SELECT tipo::text FROM notificacoes")).scalars()) == {
                "rascunho_criado"}
            tipos = set(conn.execute(text(
                "SELECT unnest(enum_range(NULL::notificacao_tipo))::text")).scalars())
            assert "post_detectado" not in tipos and "rascunho_criado" in tipos
            for nome, tabela in (("vinculo_metodo", "pg_type"),
                                 ("metricas_recusa_mudanca", "pg_proc")):
                coluna = "typname" if tabela == "pg_type" else "proname"
                assert conn.execute(text(f"SELECT count(*) FROM {tabela} WHERE {coluna} = :n"),
                                    {"n": nome}).scalar() == 0
            assert conn.execute(text("SELECT to_regclass('metricas_anonima_seq')")).scalar() \
                is None
    finally:
        command.upgrade(_cfg(), "head")  # subir de novo funciona (IF NOT EXISTS)

    with engine.begin() as conn:
        assert _destinos(conn) == antes
        for tabela in TABELAS:
            assert _existe(conn, tabela)
        assert set(conn.execute(text("SELECT tipo::text FROM notificacoes")).scalars()) == {
            "rascunho_criado"}
