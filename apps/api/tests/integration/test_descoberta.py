"""Descoberta de vídeos (T034, US2; contracts/http-api.md "Descoberta")."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fakes.youtube_fake import YoutubeFake, youtube_fake  # noqa: F401

from sociman_api.canais import youtube
from sociman_api.canais.models import (
    CanalFonte,
    CanalPerfil,
    CanalSync,
    VideoFonte,
    VideoMetrica,
    YoutubeCota,
)
from sociman_api.canais.youtube import get_youtube_client
from sociman_api.envios.models import DireitoEnvio, Envio, EnvioOrigem, EnvioStatus
from sociman_api.main import app
from sociman_api.perfis.models import Perfil

PW = "senha-forte-123"
T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def h(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return login(client, user.email, PW)


@pytest.fixture
def perfis(db):
    a = Perfil(name="A Taverna Nerd", slug="a-taverna-nerd")
    b = Perfil(name="Bits", slug="bits")
    db.add_all([a, b])
    db.commit()
    return a, b


def _canal(db, cid: str, title: str, perfis=(), **kw) -> CanalFonte:
    canal = CanalFonte(youtube_channel_id=cid, title=title, uploads_playlist_id="UU" + cid[2:],
                       direito_evidencia_nota="", **kw)
    db.add(canal)
    db.flush()
    for p in perfis:
        db.add(CanalPerfil(canal_id=canal.id, perfil_id=p.id))
    db.commit()
    return canal


_seq = iter(range(10**6))


def _video(db, canal, score=50.0, views=100, vph=None, published=T0, dur=600,
           recomendavel=True, title=None) -> VideoFonte:
    n = next(_seq)
    v = VideoFonte(canal_id=canal.id, youtube_video_id=f"v{n:010d}", title=title or f"Vídeo {n}",
                   published_at=published, duration_s=dur, views=views,
                   vph_recente=Decimal(str(vph)) if vph is not None else None,
                   score=Decimal(str(score)), score_reason="Motivo",
                   score_detail={"v": 0.5, "e": 0.1, "r": 0.2, "d": 1.0, "componente": "v"},
                   recomendavel=recomendavel, next_metrics_at=T0,
                   thumbnail_url=f"https://i.ytimg.com/vi/v{n:010d}/mqdefault.jpg")
    db.add(v)
    db.commit()
    return v


def _envio(db, perfil, video, status=EnvioStatus.pronto) -> Envio:
    kw = {}
    if status != EnvioStatus.selecionado:
        kw = {"config": {"clipMinS": 15}, "direito_no_envio": DireitoEnvio.sem_acordo}
    e = Envio(perfil_id=perfil.id, origem=EnvioOrigem.canal, video_fonte_id=video.id,
              canal_fonte_id=video.canal_id, source_url=f"https://youtu.be/{video.youtube_video_id}",
              source_title=video.title, status=status, **kw)
    db.add(e)
    db.commit()
    return e


def _list(client, h, **params):
    r = client.get("/api/videos-fonte", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _ids(body) -> list[str]:
    return [v["id"] for v in body["items"]]


def test_filtros(client, db, h, perfis):
    a, _ = perfis
    c1 = _canal(db, "UC" + "a" * 22, "Canal Um", perfis=[a])
    c2 = _canal(db, "UC" + "b" * 22, "Canal Dois")
    arq = _canal(db, "UC" + "c" * 22, "Arquivado", archived_at=T0)
    curto = _video(db, c1, score=90, dur=300, title="Review rápido")
    longo = _video(db, c1, score=80, dur=1800, published=T0 - timedelta(days=40))
    outro = _video(db, c2, score=70, dur=1200)
    nao_rec = _video(db, c2, score=0, recomendavel=False)
    _video(db, arq, score=99)

    body = _list(client, h)
    assert _ids(body) == [str(curto.id), str(longo.id), str(outro.id)]
    assert body["total"] == 3
    assert body["nextCursor"] is None
    assert str(nao_rec.id) in _ids(_list(client, h, recomendaveis="false"))
    assert _ids(_list(client, h, canalId=[str(c2.id)])) == [str(outro.id)]
    assert _ids(_list(client, h, canalId=[str(c1.id), str(c2.id)])) == \
        [str(curto.id), str(longo.id), str(outro.id)]
    assert _ids(_list(client, h, perfilId=str(a.id))) == [str(curto.id), str(longo.id)]
    assert _ids(_list(client, h, q="REVIEW")) == [str(curto.id)]
    assert _ids(_list(client, h, publicadoDesde=(T0 - timedelta(days=1)).isoformat())) == \
        [str(curto.id), str(outro.id)]
    assert _ids(_list(client, h, publicadoAte=(T0 - timedelta(days=1)).isoformat())) == \
        [str(longo.id)]
    assert _ids(_list(client, h, duracaoMax=1200)) == [str(curto.id), str(outro.id)]
    assert _ids(_list(client, h, duracaoMin=600, duracaoMax=1200)) == [str(outro.id)]

    r = client.get("/api/videos-fonte", params={"naoCortados": "true"}, headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (400, "validation_error")
    r = client.get("/api/videos-fonte", params={"ordem": "aleatoria"}, headers=h)
    assert r.status_code == 400
    r = client.get("/api/videos-fonte", params={"perfilId": str(uuid.uuid4())}, headers=h)
    assert r.status_code == 404


def test_saida_do_video(client, db, h):
    canal = _canal(db, "UC" + "a" * 22, "Canal Um")
    v = _video(db, canal, score=42.5, vph=12.34)
    [item] = _list(client, h)["items"]
    assert item["canal"] == {"id": str(canal.id), "title": "Canal Um", "direito": "sem_acordo"}
    assert item["url"] == f"https://www.youtube.com/watch?v={v.youtube_video_id}"
    assert item["thumbnailUrl"].startswith("/img/")
    assert item["score"] == 42.5
    assert item["vphRecente"] == 12.34
    assert item["scoreReason"] == "Motivo"
    assert item["scoreDetail"]["componente"] == "v"
    assert item["jaCortado"] == [] and item["selecionado"] == []


@pytest.mark.parametrize("ordem", ["score", "views", "vph", "data"])
def test_ordens_estaveis_com_cursor(client, db, h, ordem):
    canal = _canal(db, "UC" + "a" * 22, "Canal Um")
    for i in range(7):
        # Empates de propósito (i // 2): o desempate é o id.
        _video(db, canal, score=10 + i // 2, views=100 + i // 2,
               vph=None if i == 0 else 5 + i // 2, published=T0 - timedelta(hours=i // 2))
    completo = _ids(_list(client, h, ordem=ordem, limit=100))
    assert len(completo) == 7
    paginas, cursor = [], None
    while True:
        params = {"ordem": ordem, "limit": 3}
        if cursor:
            params["cursor"] = cursor
        body = _list(client, h, **params)
        assert body["total"] == 7
        paginas += _ids(body)
        cursor = body["nextCursor"]
        if not cursor:
            break
    assert paginas == completo
    itens = _list(client, h, ordem=ordem, limit=100)["items"]
    chave = {"score": "score", "views": "views", "vph": "vphRecente",
             "data": "publishedAt"}[ordem]
    valores = [(-1 if it[chave] is None else it[chave]) for it in itens]
    assert valores == sorted(valores, reverse=True)


def test_cursor_invalido(client, db, h):
    r = client.get("/api/videos-fonte", params={"cursor": "lixo"}, headers=h)
    assert r.status_code == 400


def test_ja_cortado_e_selecionado_por_perfil(client, db, h, perfis):
    a, b = perfis
    canal = _canal(db, "UC" + "a" * 22, "Canal Um", perfis=[a, b])
    cortado = _video(db, canal, score=80)
    selecionado = _video(db, canal, score=60)
    livre = _video(db, canal, score=30)
    envio = _envio(db, a, cortado, EnvioStatus.pronto)
    sel = _envio(db, a, selecionado, EnvioStatus.selecionado)
    _envio(db, b, livre, EnvioStatus.descartado)

    body = _list(client, h, perfilId=str(a.id))
    por_id = {v["id"]: v for v in body["items"]}
    assert por_id[str(cortado.id)]["score"] == 24.0  # 80 × 0,3
    assert por_id[str(cortado.id)]["jaCortado"] == [
        {"perfilId": str(a.id), "envioId": str(envio.id), "status": "pronto"}]
    assert por_id[str(selecionado.id)]["selecionado"] == [
        {"perfilId": str(a.id), "envioId": str(sel.id)}]
    assert por_id[str(selecionado.id)]["score"] == 60.0  # selecionar não é cortar
    assert por_id[str(livre.id)]["jaCortado"] == []  # descartado não conta
    # A ordem usa o score exibido.
    assert _ids(body) == [str(selecionado.id), str(livre.id), str(cortado.id)]
    # Para o perfil B, nada foi cortado: score cheio.
    body_b = _list(client, h, perfilId=str(b.id))
    assert {v["id"]: v["score"] for v in body_b["items"]}[str(cortado.id)] == 80.0
    # Sem perfil, o score é o do vídeo.
    assert _list(client, h)["items"][0]["id"] == str(cortado.id)

    nao_cortados = _list(client, h, perfilId=str(a.id), naoCortados="true")
    assert _ids(nao_cortados) == [str(selecionado.id), str(livre.id)]
    assert nao_cortados["total"] == 2


def test_detalhe_com_ultimas_50_metricas(client, db, h):
    canal = _canal(db, "UC" + "a" * 22, "Canal Um")
    v = _video(db, canal)
    for i in range(55):
        db.add(VideoMetrica(video_id=v.id, observed_at=T0 + timedelta(hours=i), views=i))
    db.commit()
    r = client.get(f"/api/videos-fonte/{v.id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["video"]["id"] == str(v.id)
    assert len(body["metricas"]) == 50
    assert body["metricas"][0]["views"] == 54
    assert body["metricas"][-1]["views"] == 5
    assert client.get(f"/api/videos-fonte/{uuid.uuid4()}", headers=h).status_code == 404


def test_sincronizar_com_cota_pausada_429(client, db, h, youtube_fake):  # noqa: F811
    app.dependency_overrides[get_youtube_client] = lambda: youtube_fake.client()
    canal = _canal(db, "UC" + "a" * 22, "Canal Um", sync_status=CanalSync.ok)
    db.add(YoutubeCota(dia=youtube.dia_cota(datetime.now(UTC)), unidades=9500))
    db.commit()
    r = client.post(f"/api/canais/{canal.id}/sincronizar", headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (429, "youtube_quota")
    app.dependency_overrides[get_youtube_client] = lambda: youtube_fake.client(key="")
    r = client.post(f"/api/canais/{canal.id}/sincronizar", headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (503, "youtube_unconfigured")
