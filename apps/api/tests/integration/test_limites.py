"""Limites por conta (spec 015, T022, R10 e Clarifications Q1 = A): 5 rascunhos em 24 h
contados localmente e a taxa por minuto no Redis."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from sociman_api.db import get_engine
from sociman_api.publicacao import limites

AGORA = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


@pytest.fixture
def cenario(make_user):
    """Conta TikTok conectada; `tentativa(fase, init_ha, modo)` cria um destino com uma tentativa."""
    dono = make_user(role="dono").id
    perfil, conta, conexao = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with get_engine().begin() as conn:
        conn.execute(text("INSERT INTO perfis (id, slug, name) VALUES (:id, 'p-lim', 'T')"),
                     {"id": perfil})
        conn.execute(text("INSERT INTO contas (id, perfil_id, platform, handle, url) VALUES "
                          "(:id, :p, 'tiktok', 'um', 'https://www.tiktok.com/@um')"),
                     {"id": conta, "p": perfil})
        conn.execute(text(
            "INSERT INTO conexoes (id, conta_id, rede, open_id, username, escopos, estado, "
            "conectado_por, conectado_em) VALUES (:id, :c, 'tiktok', 'open-um', 'um', "
            "ARRAY['video.upload'], 'conectada', :u, now())"),
            {"id": conexao, "c": conta, "u": dono})

    def tentativa(fase: str, init_ha: timedelta | None, modo: str = "criar_rascunho") -> None:
        conteudo, destino = uuid.uuid4(), uuid.uuid4()
        aberta = fase in ("iniciando", "enviando_partes", "processando")
        with get_engine().begin() as conn:
            conn.execute(text(
                "INSERT INTO conteudos (id, perfil_id, origem, video_key, poster_key, "
                "duration_ms) VALUES (:id, :p, 'video_proprio', :k, 'poster.jpg', 1000)"),
                {"id": conteudo, "p": perfil, "k": f"conteudos/{conteudo}/video.mp4"})
            conn.execute(text("INSERT INTO postagens (id, conteudo_id, conta_id) "
                              "VALUES (:id, :c, :k)"), {"id": destino, "c": conteudo, "k": conta})
            conn.execute(text(
                "INSERT INTO publicacao_tentativas (id, destino_id, numero, conexao_id, rede, "
                "modo, fase, disparo, video_ref, video_etag, video_bytes, chunk_size, "
                "total_partes, init_enviado_em, publish_id, concluida_em) VALUES (:id, :d, 1, "
                ":c, 'tiktok', CAST(:m AS agendamento_modo), CAST(:f AS tentativa_fase), "
                "'agendador', 'k', 'e', 10, 10, 1, :init, :pid, :fim)"),
                {"id": uuid.uuid4(), "d": destino, "c": conexao, "m": modo, "f": fase,
                 "init": AGORA - init_ha if init_ha is not None else None,
                 "pid": f"p-{uuid.uuid4()}", "fim": None if aberta else AGORA})

    return conexao, tentativa


def test_cinco_em_24h_sem_vaga_e_proxima_em(db, cenario):
    conexao, tentativa = cenario
    assert limites.vagas_rascunho(db, conexao, AGORA) == (0, None)
    for horas in (23, 20, 10, 5):
        tentativa("entregue", timedelta(hours=horas))
    ocupadas, proxima = limites.vagas_rascunho(db, conexao, AGORA)
    assert ocupadas == 4 < limites.RASCUNHOS_24H
    tentativa("incerta", timedelta(hours=1))
    ocupadas, proxima = limites.vagas_rascunho(db, conexao, AGORA)
    assert ocupadas == limites.RASCUNHOS_24H
    assert proxima == AGORA - timedelta(hours=23) + timedelta(hours=24)


def test_abertas_e_incertas_contam_recusadas_nao(db, cenario):
    conexao, tentativa = cenario
    for fase in ("iniciando", "enviando_partes", "processando", "entregue", "incerta"):
        tentativa(fase, timedelta(hours=2))
    for fase in ("recusada", "sem_vaga"):
        tentativa(fase, timedelta(hours=1))
    tentativa("entregue", timedelta(hours=25))  # fora da janela
    tentativa("iniciando", None)  # o init ainda não saiu
    tentativa("publicada", timedelta(hours=1), modo="publicar")  # Direct Post não conta
    assert limites.vagas_rascunho(db, conexao, AGORA)[0] == 5


def test_taxa_estoura_e_volta_no_minuto_seguinte():
    conexao = uuid.uuid4()
    minuto = 1_000_000 * 60.0
    assert all(limites.consumir(conexao, "init", minuto) for _ in range(limites.TAXAS["init"]))
    assert not limites.consumir(conexao, "init", minuto + 30)
    assert limites.consumir(conexao, "status", minuto)  # outro endpoint, outro contador
    assert limites.consumir(uuid.uuid4(), "init", minuto)  # outra conexão
    assert limites.consumir(conexao, "init", minuto + 60)  # minuto seguinte
    assert limites.TAXAS == {"init": 5, "status": 29, "creator_info": 19}
