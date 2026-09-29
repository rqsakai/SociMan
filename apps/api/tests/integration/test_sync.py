"""Trilha `sync` do agendador (T033, research R2): 1ª sync, incremental, métricas, cota e erros."""

from datetime import UTC, datetime, timedelta

import pytest
from fakes.youtube_fake import CHAVE_TESTE, YoutubeFake, youtube_fake  # noqa: F401
from sqlalchemy import func, select

from sociman_api.canais import sync
from sociman_api.canais.models import (
    CanalFonte,
    CanalSync,
    VideoFonte,
    VideoMetrica,
    YoutubeCota,
)
from sociman_api.history import EntityVersion
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo

CID = "UCaaaaaaaaaaaaaaaaaaaaaa"
T0 = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _vid(i: int) -> str:
    return f"vid{i:08d}"


@pytest.fixture
def dono(make_user):
    return make_user(role="dono", name="Dono")


@pytest.fixture
def fake(youtube_fake: YoutubeFake) -> YoutubeFake:  # noqa: F811
    youtube_fake.add_canal(CID, "The IT Nerd", handle="theitnerd")
    return youtube_fake


def _videos(fake: YoutubeFake, n: int, inicio: int = 0, idade: timedelta = timedelta(days=1)):
    # Do mais antigo ao mais novo (add_video põe no topo da playlist).
    for i in range(inicio, inicio + n):
        fake.add_video(CID, _vid(i), T0 - idade - timedelta(minutes=inicio + n - i), views=1000 + i)


def _canal(db, **kw) -> CanalFonte:
    canal = CanalFonte(youtube_channel_id=CID, title="The IT Nerd",
                       uploads_playlist_id="UU" + CID[2:], next_sync_at=T0 - timedelta(minutes=1),
                       **kw)
    db.add(canal)
    db.commit()
    return canal


def _rodar(db, fake, agora=T0, quota=10000) -> int:
    n = sync.rodar(db, client=fake.client(quota_daily=quota, relogio=lambda: agora),
                   agora=agora)
    db.expire_all()
    return n


def _n_videos(db) -> int:
    return db.scalar(select(func.count()).select_from(VideoFonte))


def test_primeira_sync_pagina_e_conclui(db, fake):
    _videos(fake, 120)
    canal = _canal(db)
    assert _rodar(db, fake) > 0
    assert fake.contar("playlistItems") == 3
    assert fake.contar("videos") == 3
    assert db.get(YoutubeCota, T0.date()).unidades == 6
    db.refresh(canal)
    assert canal.sync_status == CanalSync.ok
    assert canal.full_synced_at == T0
    assert canal.last_synced_at == T0
    assert canal.next_sync_at == T0 + timedelta(hours=1)
    assert canal.sync_error is None
    assert _n_videos(db) == 120
    assert db.scalar(select(func.count()).select_from(VideoMetrica)) == 120
    v = db.scalar(select(VideoFonte).where(VideoFonte.youtube_video_id == _vid(0)))
    assert v.views == 1000 and v.duration_s == 24 * 60 + 10
    assert v.score > 0 and v.score_reason and v.recomendavel is True
    assert v.score_detail["componente"] in ("v", "e", "r", "d")
    assert db.scalar(select(EntityVersion.id)) is None  # estado de job: sem histórico


def test_primeira_sync_grava_por_pagina_e_retoma(db, fake, monkeypatch):
    monkeypatch.setattr(sync, "PAGINAS_POR_VOLTA", 1)
    _videos(fake, 120)
    canal = _canal(db)
    _rodar(db, fake)
    db.refresh(canal)
    assert canal.sync_status == CanalSync.sincronizando
    assert canal.sync_progress["lidos"] == 50
    assert canal.sync_progress["total"] == 120
    assert canal.full_synced_at is None
    assert canal.next_sync_at == T0
    assert _n_videos(db) == 50
    _rodar(db, fake)
    _rodar(db, fake)
    db.refresh(canal)
    assert canal.sync_status == CanalSync.ok
    assert _n_videos(db) == 120
    assert canal.sync_progress.get("lidos") is None


def test_incremental_para_no_primeiro_conhecido(db, fake):
    _videos(fake, 60)
    canal = _canal(db)
    _rodar(db, fake)
    _videos(fake, 2, inicio=60, idade=timedelta(minutes=30))
    fake.requests.clear()
    _rodar(db, fake, agora=T0 + timedelta(hours=1))
    assert fake.contar("playlistItems") == 1  # achou um conhecido na 1ª página
    assert fake.contar("channels") == 0  # nome e avatar: uma vez por dia
    assert _n_videos(db) == 62
    ids = db.scalars(select(VideoFonte.youtube_video_id)).all()
    assert len(ids) == len(set(ids))
    db.refresh(canal)
    assert canal.next_sync_at == T0 + timedelta(hours=2)
    # Um dia depois, relê o canal (título novo).
    fake.canais[CID]["snippet"]["title"] = "IT Nerd 2"
    fake.requests.clear()
    _rodar(db, fake, agora=T0 + timedelta(days=1, hours=1))
    assert fake.contar("channels") == 1
    db.refresh(canal)
    assert canal.title == "IT Nerd 2"


def test_metricas_por_idade(db, fake):
    fake.add_video(CID, "novo0000000", T0 - timedelta(days=1))
    fake.add_video(CID, "medio000000", T0 - timedelta(days=30))
    fake.add_video(CID, "velho000000", T0 - timedelta(days=100))
    _canal(db)
    _rodar(db, fake)
    proximas = dict(db.execute(
        select(VideoFonte.youtube_video_id, VideoFonte.next_metrics_at)).all())
    assert proximas == {"novo0000000": T0 + timedelta(hours=1),
                        "medio000000": T0 + timedelta(hours=24),
                        "velho000000": T0 + timedelta(days=7)}


def test_vph_recente_com_leituras_de_6h(db, fake):
    fake.add_video(CID, "novo0000000", T0 - timedelta(days=1), views=1000)
    _canal(db)
    _rodar(db, fake)
    fake.stats("novo0000000", 2000)
    _rodar(db, fake, agora=T0 + timedelta(hours=1))
    v = db.scalar(select(VideoFonte))
    assert v.views == 2000
    assert v.vph_recente is None  # só 1 h entre as leituras
    fake.stats("novo0000000", 8000)
    _rodar(db, fake, agora=T0 + timedelta(hours=7))
    v = db.scalar(select(VideoFonte))
    assert float(v.vph_recente) == 1000.0  # (8000 − 2000) / 6 h
    assert db.scalar(select(func.count()).select_from(VideoMetrica)) == 3


def test_video_sumido_fica_indisponivel(db, fake):
    fake.add_video(CID, "novo0000000", T0 - timedelta(days=1))
    _canal(db)
    _rodar(db, fake)
    fake.removidos.add("novo0000000")
    _rodar(db, fake, agora=T0 + timedelta(hours=1))
    v = db.scalar(select(VideoFonte))
    assert v.disponivel is False
    assert v.recomendavel is False
    assert float(v.score) == 0.0
    assert v.score_reason.startswith("Indisponível")


def test_cota_em_95_pausa_e_aviso_em_80(db, fake, dono):
    fake.page_size = 2
    _videos(fake, 30)
    canal = _canal(db)
    _rodar(db, fake, quota=20)  # teto da sync = 19
    db.refresh(canal)
    assert canal.sync_status == CanalSync.pausado_cota
    assert canal.next_sync_at == datetime(2026, 9, 30, 7, 0, tzinfo=UTC)
    assert canal.sync_progress["lidos"] == 18  # 9 páginas completas ficaram gravadas
    assert _n_videos(db) == 18
    notas = db.scalars(select(Notificacao)).all()
    assert [(n.tipo, n.user_id) for n in notas] == [(NotificacaoTipo.cota_youtube, dono.id)]
    # Enquanto pausada, a volta não chama o Google.
    fake.requests.clear()
    assert _rodar(db, fake, agora=T0 + timedelta(minutes=5), quota=20) == 0
    assert fake.requests == []


@pytest.mark.parametrize("tipo", ["keyInvalid", "accessNotConfigured"])
def test_chave_invalida_deixa_o_canal_em_erro(db, fake, dono, tipo):
    fake.add_video(CID, "novo0000000", T0 - timedelta(days=1))
    fake.falhar_sempre = tipo
    canal = _canal(db)
    _rodar(db, fake)
    db.refresh(canal)
    assert canal.sync_status == CanalSync.erro
    assert canal.sync_error.startswith("Chave do YouTube inválida")
    assert CHAVE_TESTE not in canal.sync_error
    assert canal.next_sync_at == T0 + timedelta(hours=1)
    notas = db.scalars(select(Notificacao)).all()
    assert [(n.tipo, n.user_id) for n in notas] == [(NotificacaoTipo.canal_erro, dono.id)]
    assert CHAVE_TESTE not in notas[0].corpo
    # A nova tentativa, uma hora depois, volta a funcionar.
    fake.falhar_sempre = None
    _rodar(db, fake, agora=T0 + timedelta(hours=1))
    db.refresh(canal)
    assert canal.sync_status == CanalSync.ok
    assert canal.sync_error is None


def test_canal_arquivado_nao_sincroniza(db, fake):
    _videos(fake, 3)
    _canal(db, archived_at=T0)
    assert _rodar(db, fake) == 0
    assert fake.requests == []


def test_sem_chave_fica_ociosa(db, fake):
    _canal(db)
    assert sync.rodar(db, client=fake.client(key=""), agora=T0) == 0
    assert fake.requests == []
