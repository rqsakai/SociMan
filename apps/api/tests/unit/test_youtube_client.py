"""Cliente do YouTube (T022): lista fechada, cota antes da chamada, limites e sigilo da chave.

Usa o Postgres de teste (tabela `youtube_cota`) pelo conftest da raiz.
"""

import logging
from datetime import UTC, datetime

import httpx
import pytest
from fakes.youtube_fake import BASE_URL, CHAVE_TESTE, YoutubeFake, youtube_fake  # noqa: F401
from sqlalchemy import select

from sociman_api.canais import youtube
from sociman_api.canais.models import VideoLive, YoutubeCota
from sociman_api.canais.resolve import Consulta
from sociman_api.errors import ApiError
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo

CID = "UCaaaaaaaaaaaaaaaaaaaaaa"
AGORA = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)  # 05:00 no Pacífico (PDT)


def _relogio() -> datetime:
    return AGORA


def _usadas(db) -> int:
    db.expire_all()
    row = db.get(YoutubeCota, AGORA.date())
    return row.unidades if row else 0


@pytest.fixture
def fake(youtube_fake: YoutubeFake) -> YoutubeFake:  # noqa: F811
    youtube_fake.add_canal(CID, "The IT Nerd", handle="theitnerd", username="itnerd")
    youtube_fake.add_video(CID, "dQw4w9WgXcQ", AGORA)
    return youtube_fake


def test_so_get_em_recursos_permitidos(fake):
    assert youtube.ALLOWED == {("GET", "channels"), ("GET", "playlistItems"),
                               ("GET", "videos"), ("GET", "search")}
    client = fake.client(relogio=_relogio)
    for consulta in (Consulta("id", CID), Consulta("handle", "theitnerd"),
                     Consulta("username", "itnerd"), Consulta("busca", "IT Nerd"),
                     Consulta("video", "dQw4w9WgXcQ")):
        assert client.canal(consulta).youtube_channel_id == CID
    client.playlist("UU" + CID[2:])
    client.videos(["dQw4w9WgXcQ"])
    assert fake.requests
    for method, recurso, _ in fake.requests:
        assert (method, recurso) in youtube.ALLOWED
    # A chave vai em params (nunca no caminho).
    assert all(f"key={CHAVE_TESTE}" in u for u in fake.urls)


def test_recurso_fora_da_lista_e_recusado(fake):
    client = fake.client(relogio=_relogio)
    with pytest.raises(ValueError):
        client._get("subscriptions", {}, 1, False)
    assert fake.requests == []


def test_custos_da_resolucao(db, fake):
    client = fake.client(relogio=_relogio)
    esperado = 0
    for consulta, custo in ((Consulta("id", CID), 1), (Consulta("handle", "theitnerd"), 1),
                            (Consulta("username", "itnerd"), 1),
                            (Consulta("video", "dQw4w9WgXcQ"), 2),
                            (Consulta("busca", "IT Nerd"), 101)):  # busca 100 + channels 1
        client.canal(consulta)
        esperado += custo
        assert _usadas(db) == esperado


def test_cota_somada_antes_da_chamada(db, fake):
    fake.erro_proximo("keyInvalid")
    client = fake.client(relogio=_relogio)
    with pytest.raises(youtube.YoutubeErro):
        client.canais([CID])
    assert _usadas(db) == 1  # a unidade gasta fica, mesmo com o erro


def test_aviso_de_80_por_cento_uma_vez_por_dia(db, fake, make_user):
    dono = make_user(role="dono")
    client = fake.client(quota_daily=10, relogio=_relogio)
    for _ in range(7):
        client.canais([CID])
    assert db.query(Notificacao).count() == 0
    client.canais([CID])  # 8 de 10
    client.canais([CID])
    notas = db.scalars(select(Notificacao)).all()
    assert [(n.user_id, n.tipo) for n in notas] == [(dono.id, NotificacaoTipo.cota_youtube)]
    assert db.get(YoutubeCota, AGORA.date()).aviso_enviado is True


def test_95_por_cento_pausa_a_sync_e_100_recusa_o_resto(db, fake):
    client = fake.client(quota_daily=20, relogio=_relogio)
    for _ in range(19):
        client.videos(["dQw4w9WgXcQ"], sync=True)
    with pytest.raises(youtube.CotaPausada) as pausa:
        client.videos(["dQw4w9WgXcQ"], sync=True)
    assert pausa.value.renova_em == datetime(2026, 9, 30, 7, 0, tzinfo=UTC)
    assert _usadas(db) == 19
    client.canais([CID])  # o cadastro manual segue até 100%
    antes = len(fake.requests)
    with pytest.raises(ApiError) as exc:
        client.canais([CID])
    assert exc.value.status == 429
    assert exc.value.code == "youtube_quota"
    # Meia-noite do Pacífico = 04:00 em São Paulo (APP_TZ).
    assert exc.value.message == "A cota diária do YouTube acabou; volta às 04:00"
    assert len(fake.requests) == antes  # recusado antes de ir ao Google
    assert _usadas(db) == 20


def test_quota_exceeded_do_google_encerra_o_dia(db, fake):
    fake.erro_proximo("quotaExceeded")
    client = fake.client(quota_daily=100, relogio=_relogio)
    with pytest.raises(ApiError) as exc:
        client.canais([CID])
    assert (exc.value.status, exc.value.code) == (429, "youtube_quota")
    assert _usadas(db) == 100
    status = youtube.cota_atual(db, AGORA, limite=100)
    assert status.esgotada and status.pausada
    antes = len(fake.requests)
    with pytest.raises(ApiError):
        client.canais([CID])
    assert len(fake.requests) == antes


@pytest.mark.parametrize("tipo", ["keyInvalid", "accessNotConfigured"])
def test_chave_invalida_vira_youtube_error(fake, tipo):
    fake.erro_proximo(tipo)
    client = fake.client(relogio=_relogio)
    with pytest.raises(youtube.YoutubeErro) as exc:
        client.canais([CID])
    assert exc.value.status == 502
    assert exc.value.code == "youtube_error"
    assert exc.value.chave_invalida is True
    assert exc.value.message.startswith(youtube.PREFIXO_CHAVE_INVALIDA)


def test_chave_nunca_aparece_em_erro_nem_em_log(caplog):
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {
            "code": 500, "message": f"falhou em {request.url} com key={CHAVE_TESTE}",
            "errors": [{"reason": "backendError"}]}})

    client = youtube.YoutubeClient(CHAVE_TESTE, BASE_URL, 10000,
                                   transport=httpx.MockTransport(handler), relogio=_relogio)
    with pytest.raises(youtube.YoutubeErro) as exc:
        client.canais([CID])
    assert exc.value.status == 502
    assert CHAVE_TESTE not in exc.value.message
    assert "key=***" in exc.value.message

    def queda(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"sem rede para {request.url}")

    client = youtube.YoutubeClient(CHAVE_TESTE, BASE_URL, 10000,
                                   transport=httpx.MockTransport(queda), relogio=_relogio)
    with pytest.raises(youtube.YoutubeErro) as exc:
        client.canais([CID])
    assert CHAVE_TESTE not in exc.value.message
    assert CHAVE_TESTE not in caplog.text
    assert "youtube channels custo=1 status=500" in caplog.text


def test_redact():
    assert youtube.redact("https://x/v3/videos?id=1&key=AIzaXYZ&part=a") == \
        "https://x/v3/videos?id=1&key=***&part=a"
    assert youtube.redact("segredo solto", "segredo") == "*** solto"


def test_sem_chave_503_sem_chamar(fake):
    client = fake.client(key="", relogio=_relogio)
    assert client.configurado is False
    with pytest.raises(youtube.YoutubeErro) as exc:
        client.canais([CID])
    assert (exc.value.status, exc.value.code) == (503, "youtube_unconfigured")
    assert fake.requests == []


def test_canal_nao_encontrado(fake):
    client = fake.client(relogio=_relogio)
    with pytest.raises(youtube.YoutubeErro) as exc:
        client.canal(Consulta("handle", "naoexiste"))
    assert (exc.value.status, exc.value.code) == (404, "canal_not_found")


def test_parse_de_canal_e_video(fake):
    fake.add_canal("UCbbbbbbbbbbbbbbbbbbbbbb", "Oculto", subscribers=None)
    fake.add_video(CID, "liveliveliv", AGORA, duration="P0D", live="live", likes=None)
    client = fake.client(relogio=_relogio)
    oculto = client.canais(["UCbbbbbbbbbbbbbbbbbbbbbb"])[0]
    assert oculto.subscribers is None and oculto.handle is None
    assert oculto.uploads_playlist_id == "UUbbbbbbbbbbbbbbbbbbbbbb"
    canal = client.canais([CID])[0]
    assert (canal.handle, canal.subscribers) == ("theitnerd", 45600)
    videos = {v.youtube_video_id: v for v in client.videos(["dQw4w9WgXcQ", "liveliveliv"])}
    assert videos["dQw4w9WgXcQ"].duration_s == 24 * 60 + 10
    assert videos["dQw4w9WgXcQ"].thumbnail_url == \
        "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"
    assert videos["liveliveliv"].live == VideoLive.ao_vivo
    assert videos["liveliveliv"].likes is None
    assert youtube.duracao_s("P1DT2H3M4S") == 93784
    assert youtube.duracao_s("xyz") is None
