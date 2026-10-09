"""Trilha `metricas` (spec 016, US2, T030; research R3 a R7). TikTok falsa e relógio injetado
(`agora`), sem sleep. Nenhum teste chama a TikTok real."""

from datetime import UTC, datetime, timedelta

import pytest
from fakes.tiktok_fake import ESCOPOS, ESCOPOS_016
from sqlalchemy import func, select, text

from integration.conexao_helpers import app_tiktok, conectar  # noqa: F401
from integration.postagem_helpers import criar_conta, criar_perfil, dono  # noqa: F401
from sociman_api.config import get_settings
from sociman_api.metricas import agenda, coleta
from sociman_api.metricas.models import FotoConta, FotoVideo, Serie, VideoRede
from sociman_api.publicacao import conexoes, limites
from sociman_api.publicacao.executor import ConexaoPerdida
from sociman_api.publicacao.models import Conexao, ConexaoEstado

H = "atavernanerd"
ID_GRANDE = 7_400_000_000_000_000_001  # acima de 2^53
LEITURAS = ("user_info", "video_list", "video_query")


@pytest.fixture
def agora() -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0)


@pytest.fixture
def c(client, dono, app_tiktok):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], handle=H)
    conectar(client, h, conta, app_tiktok, escopos=ESCOPOS_016)
    return {"h": h, "perfil": perfil, "conta": conta, "fake": app_tiktok}


def _rodar(db, fake, agora) -> int:
    return coleta.rodar(db, client=fake.client(), agora=agora)


def _leituras(fake) -> list[str]:
    return [e for _, e, _ in fake.requests if e in LEITURAS]


def _serie(db) -> Serie:
    db.expire_all()
    return db.scalar(select(Serie).where(Serie.anonimizada_em.is_(None)))


def _video(db, rede_id) -> VideoRede:
    db.expire_all()
    return db.scalar(select(VideoRede).where(VideoRede.rede_video_id == str(rede_id)))


def _fotos(db, video_id=None) -> list[FotoVideo]:
    stmt = select(FotoVideo).order_by(FotoVideo.id)
    if video_id is not None:
        stmt = stmt.where(FotoVideo.video_id == video_id)
    return list(db.scalars(stmt))


def _n(db, modelo) -> int:
    return db.scalar(select(func.count()).select_from(modelo))


# ---- 1ª volta, varredura e descoberta ----

def test_primeira_volta_cria_a_serie_e_a_primeira_foto_da_conta(db, c, agora):
    fake = c["fake"]
    fake.seguidores(H, 1234, seguindo=10, curtidas=5000)
    fake.video(H, ID_GRANDE, agora - timedelta(minutes=30), duracao=31, legenda="oi")
    assert _rodar(db, fake, agora) == 1
    serie = _serie(db)
    assert serie is not None and serie.varredura_concluida_em == agora
    assert serie.ultima_coleta_em == agora and serie.ultimo_erro_codigo is None
    [fc] = db.scalars(select(FotoConta))
    assert (fc.seguidores, fc.seguindo, fc.curtidas, fc.videos) == (1234, 10, 5000, 1)
    assert fc.janela_em == agenda.hora_cheia(agora)  # vídeo < 48 h: horária
    assert serie.conta_proxima_em == agenda.hora_cheia(agora) + timedelta(hours=1)
    v = _video(db, ID_GRANDE)
    assert v.rede_video_id == str(ID_GRANDE) and v.duracao_s == 31 and v.legenda == "oi"
    [f] = _fotos(db, v.id)
    assert f.alvo_idade_min == 30 and f.idade_s == 30 * 60
    assert v.proxima_coleta_em == v.publicado_em + timedelta(hours=1)


def test_varredura_segue_o_cursor_ate_10_paginas_e_continua(db, c, agora):
    fake = c["fake"]
    for i in range(215):
        fake.video(H, 1000 + i, agora - timedelta(days=3, hours=i))
    _rodar(db, fake, agora)
    serie = _serie(db)
    assert len(fake.pedidos("video_list")) == 10
    assert serie.varredura_concluida_em is None and serie.varredura_cursor is not None
    assert _n(db, VideoRede) == 200
    _rodar(db, fake, agora + timedelta(minutes=1))
    serie = _serie(db)
    assert serie.varredura_concluida_em is not None and serie.varredura_cursor is None
    assert _n(db, VideoRede) == 215
    assert len(fake.pedidos("video_list")) == 11  # + 1 página; a 1ª página horária espera
    # uma foto de descoberta por vídeo, nenhuma repetida
    assert _n(db, FotoVideo) == 215


def test_video_com_mais_de_um_ano_entra_com_uma_foto_e_para(db, c, agora):
    fake = c["fake"]
    fake.video(H, 42, agora - timedelta(days=400), duracao=20)
    fake.contadores(42, views=9000)
    _rodar(db, fake, agora)
    v = _video(db, 42)
    [f] = _fotos(db, v.id)
    assert f.views == 9000 and v.proxima_coleta_em is None
    _rodar(db, fake, agora + timedelta(days=40))
    assert len(_fotos(db, v.id)) == 1 and fake.pedidos("video_query") == []


def test_primeira_pagina_de_hora_em_hora(db, c, agora):
    fake = c["fake"]
    _rodar(db, fake, agora)
    fake.video(H, 77, agora + timedelta(minutes=20))
    _rodar(db, fake, agora + timedelta(minutes=30))
    assert _video(db, 77) is None  # a lista só é lida de novo depois de 1 h
    _rodar(db, fake, agora + timedelta(minutes=61))
    assert _video(db, 77) is not None


# ---- fila (R4) ----

def test_fila_tira_as_fotos_na_cadencia_e_grava_contagem_que_cai(db, c, agora):
    fake = c["fake"]
    pub = agora - timedelta(minutes=30)
    fake.video(H, 5, pub)
    fake.contadores(5, views=10, likes=1)
    _rodar(db, fake, agora)
    v = _video(db, 5)
    fake.contadores(5, views=150, likes=9)
    _rodar(db, fake, v.publicado_em + timedelta(minutes=62))
    fake.contadores(5, views=140, likes=None)  # a TikTok corrigiu e omitiu likes
    _rodar(db, fake, v.publicado_em + timedelta(minutes=121))
    fotos = _fotos(db, v.id)
    assert [f.alvo_idade_min for f in fotos] == [30, 60, 120]
    assert [f.views for f in fotos] == [10, 150, 140]
    assert [f.likes for f in fotos] == [1, 9, None]
    assert _video(db, 5).proxima_coleta_em == v.publicado_em + timedelta(hours=3)


def test_atraso_tira_so_a_janela_mais_recente(db, c, agora):
    fake = c["fake"]
    fake.video(H, 6, agora - timedelta(minutes=10))
    _rodar(db, fake, agora)
    v = _video(db, 6)
    _rodar(db, fake, v.publicado_em + timedelta(hours=5, minutes=40))  # agendador parado
    assert [f.alvo_idade_min for f in _fotos(db, v.id)] == [10, 300]


def test_fila_em_lotes_de_20(db, c, agora):
    fake = c["fake"]
    for i in range(25):
        fake.video(H, 300 + i, agora - timedelta(minutes=50, seconds=i))
    _rodar(db, fake, agora)
    _rodar(db, fake, agora + timedelta(minutes=11))
    lotes = fake.pedidos("video_query")
    assert len(lotes) == 2
    assert _n(db, FotoVideo) == 50


def test_video_que_some_fica_indisponivel_e_volta(db, c, agora):
    fake = c["fake"]
    fake.video(H, 8, agora - timedelta(minutes=50))
    _rodar(db, fake, agora)
    v = _video(db, 8)
    fake.tornar_privado(8)
    t1 = v.publicado_em + timedelta(minutes=61)
    _rodar(db, fake, t1)
    v = _video(db, 8)
    assert not v.disponivel and v.indisponivel_desde == t1
    assert len(_fotos(db, v.id)) == 1  # a foto antiga ficou
    assert v.proxima_coleta_em == v.publicado_em + timedelta(hours=2)  # segue na fila
    fake.tornar_publico(8)
    _rodar(db, fake, v.publicado_em + timedelta(minutes=121))
    v = _video(db, 8)
    assert v.disponivel and v.indisponivel_desde is None
    assert len(_fotos(db, v.id)) == 2


def test_foto_da_conta_diaria_sem_video_novo(db, c, agora):
    fake = c["fake"]
    fake.video(H, 9, agora - timedelta(days=5))
    _rodar(db, fake, agora)
    [fc] = db.scalars(select(FotoConta))
    tz = get_settings().app_tz
    assert fc.janela_em == agenda.janela_conta(agora, False, tz)
    _rodar(db, fake, agenda.proxima_janela_conta(agora, False, tz) - timedelta(minutes=1))
    assert _n(db, FotoConta) == 1
    _rodar(db, fake, agenda.proxima_janela_conta(agora, False, tz) + timedelta(minutes=1))
    assert _n(db, FotoConta) == 2


# ---- erros por série (R3) ----

def test_rate_limit_adia_sem_erro_visivel(db, c, agora):
    fake = c["fake"]
    fake.falhar_proximo("video_list", "rate_limit_exceeded")
    _rodar(db, fake, agora)
    serie = _serie(db)
    assert serie.adiar_ate == agora + timedelta(seconds=60) and serie.ultimo_erro_codigo is None
    antes = len(_leituras(fake))
    _rodar(db, fake, agora + timedelta(seconds=30))
    assert len(_leituras(fake)) == antes  # adiada: nenhum pedido
    _rodar(db, fake, agora + timedelta(seconds=61))
    serie = _serie(db)
    assert serie.varredura_concluida_em is not None and serie.adiar_ate is None


def test_taxa_local_adia(db, c, agora, monkeypatch):
    monkeypatch.setitem(limites.TAXAS, "leitura", 0)
    _rodar(db, c["fake"], agora)
    assert _serie(db).adiar_ate == agora + timedelta(seconds=60)
    assert c["fake"].pedidos("video_list") == []


def test_tiktok_fora_adia_5_minutos_com_erro(db, c, agora):
    c["fake"].falhar_proximo("video_list", "5xx")
    _rodar(db, c["fake"], agora)
    serie = _serie(db)
    assert serie.adiar_ate == agora + timedelta(minutes=5)
    assert serie.ultimo_erro_codigo == "rede_indisponivel"
    assert serie.ultimo_erro_motivo.startswith("A TikTok não respondeu")
    _rodar(db, c["fake"], agora + timedelta(minutes=6))
    serie = _serie(db)
    assert serie.ultimo_erro_codigo is None and serie.adiar_ate is None


def test_scope_not_authorized_para_a_serie_e_nao_muda_a_conexao(db, c, agora):
    [cx] = db.scalars(select(Conexao))
    versao = cx.version
    c["fake"].falhar_proximo("video_list", "scope_not_authorized")
    _rodar(db, c["fake"], agora)
    serie = _serie(db)
    assert serie.sem_permissao_desde == agora
    db.expire_all()
    cx = db.get(Conexao, cx.id)
    assert cx.estado == ConexaoEstado.conectada and cx.version == versao
    antes = len(_leituras(c["fake"]))
    _rodar(db, c["fake"], agora + timedelta(hours=2))
    assert len(_leituras(c["fake"])) == antes  # parada até reconectar


def test_outra_recusa_grava_o_codigo_e_tenta_na_proxima(db, c, agora):
    c["fake"].falhar_proximo("video_list", "invalid_params")
    _rodar(db, c["fake"], agora)
    serie = _serie(db)
    assert serie.ultimo_erro_codigo == "invalid_params" and serie.adiar_ate is None
    assert "invalid_params" in serie.ultimo_erro_motivo


def test_conexao_perdida_nao_mexe_na_serie(db, c, agora, monkeypatch):
    def _perdida(*_a, **_k):
        raise ConexaoPerdida("refresh revogado")

    monkeypatch.setattr(conexoes, "token_valido", _perdida)
    _rodar(db, c["fake"], agora)
    serie = _serie(db)
    assert serie.ultimo_erro_codigo is None and serie.adiar_ate is None
    assert serie.sem_permissao_desde is None


def test_erro_numa_conta_nao_atrasa_a_outra(client, db, c, agora):
    fake = c["fake"]
    perfil2 = criar_perfil(client, c["h"], "Meus Queridinhos")
    conta2 = criar_conta(client, c["h"], perfil2["id"], handle="meusqueridinhos10")
    conectar(client, c["h"], conta2, fake, escopos=ESCOPOS_016)
    fake.video("meusqueridinhos10", 11, agora - timedelta(minutes=5))
    fake.falhar_proximo("video_list", "5xx")  # o 1º pedido é da 1ª série
    assert _rodar(db, fake, agora) == 2
    db.expire_all()
    series = list(db.scalars(select(Serie)))
    adiadas = [s for s in series if s.adiar_ate is not None]
    boas = [s for s in series if s.adiar_ate is None]
    assert len(adiadas) == 1 and len(boas) == 1
    assert boas[0].varredura_concluida_em is not None
    assert db.scalar(select(func.count()).select_from(FotoConta)
                     .where(FotoConta.serie_id == boas[0].id)) == 1


# ---- idempotência e só inserção (R7) ----

def test_volta_repetida_nao_duplica(db, c, agora):
    fake = c["fake"]
    fake.video(H, 12, agora - timedelta(minutes=40))
    _rodar(db, fake, agora)
    _rodar(db, fake, agora)
    assert _n(db, FotoVideo) == 1 and _n(db, FotoConta) == 1
    # duas instâncias por engano: a mesma janela de novo pela fila
    v = _video(db, 12)
    t = v.publicado_em + timedelta(minutes=61)
    _rodar(db, fake, t)
    db.execute(text("UPDATE metricas_videos SET proxima_coleta_em = :t WHERE id = :id"),
               {"t": t, "id": v.id})
    db.commit()
    _rodar(db, fake, t + timedelta(minutes=1))
    assert [f.alvo_idade_min for f in _fotos(db, v.id)] == [40, 60]


def test_queda_depois_do_pedido_e_antes_do_commit(db, c, agora, monkeypatch):
    fake = c["fake"]
    fake.video(H, 13, agora - timedelta(minutes=40))
    _rodar(db, fake, agora)
    v = _video(db, 13)
    t = v.publicado_em + timedelta(minutes=61)
    original = db.commit
    estado = {"caiu": False}

    def commit_que_cai():
        if not estado["caiu"] and fake.pedidos("video_query"):
            estado["caiu"] = True
            raise RuntimeError("queda injetada")
        original()

    monkeypatch.setattr(db, "commit", commit_que_cai)
    with pytest.raises(RuntimeError):
        _rodar(db, fake, t)
    db.rollback()  # o agendador faz o rollback da volta
    monkeypatch.setattr(db, "commit", original)
    assert len(_fotos(db, v.id)) == 1
    _rodar(db, fake, t + timedelta(minutes=1))
    assert [f.alvo_idade_min for f in _fotos(db, v.id)] == [40, 60]
    assert len(fake.pedidos("video_query")) == 2  # o pedido foi refeito


# ---- quem não é coletado ----

def test_conta_sem_escopos_nao_e_coletada(client, db, dono, app_tiktok, agora):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], handle=H)
    conectar(client, h, conta, app_tiktok, escopos=ESCOPOS)
    antes = len(_leituras(app_tiktok))  # o login leu o user/info
    assert _rodar(db, app_tiktok, agora) == 0
    assert _n(db, Serie) == 0 and len(_leituras(app_tiktok)) == antes


def test_serie_anonimizada_nao_e_coletada(db, c, agora):
    fake = c["fake"]
    fake.video(H, 14, agora - timedelta(minutes=40))
    _rodar(db, fake, agora)
    v = _video(db, 14)
    db.execute(text(
        "UPDATE metricas_videos SET rede_video_id = NULL, share_url = NULL, legenda = NULL, "
        "titulo = NULL, proxima_coleta_em = NULL, features = '{}'::jsonb, anonimizado_em = now()"))
    db.execute(text(
        "UPDATE metricas_series SET conta_id = NULL, rotulo = 'Conta anônima 1', anonima_n = 1, "
        "anonimizada_em = now()"))
    db.commit()
    _rodar(db, fake, agora + timedelta(hours=3))
    assert len(_fotos(db, v.id)) == 1  # a anônima não ganha foto
    assert _n(db, Serie) == 2  # a conta, ainda conectada, começa outra série


def test_coleta_desligada_nao_faz_pedido(db, c, agora, monkeypatch):
    monkeypatch.setattr(get_settings(), "metricas_coleta_habilitada", False)
    antes = len(c["fake"].requests)
    assert _rodar(db, c["fake"], agora) == 0
    assert len(c["fake"].requests) == antes and _n(db, Serie) == 0


def test_so_le_e_nao_depende_da_publicacao(db, c, agora, publicacao_habilitada):
    publicacao_habilitada(False)
    c["fake"].video(H, 15, agora - timedelta(minutes=5))
    antes = len(c["fake"].requests)
    _rodar(db, c["fake"], agora)
    endpoints = {e for _, e, _ in c["fake"].requests[antes:]}
    assert endpoints <= {"token", *LEITURAS}
    assert c["fake"].inits == 0 and _n(db, FotoConta) == 1
