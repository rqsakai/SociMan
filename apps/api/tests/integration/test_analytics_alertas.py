"""Alertas (spec 019, US8, T052): estagnado relativo (< 10% da mediana da conta na mesma idade,
≥ 6 h) e fixo (≤ 1 view) com poucas referências, destaque > 3×, sem coleta > 3 h, vínculo a
confirmar (via `metricas.vinculos.vinculo`), alertas que somem quando a condição deixa de valer
e nada gravado (contagem das tabelas antes = depois)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from integration.analytics_helpers import agora, cena, local  # noqa: F401
from integration.conexao_helpers import app_tiktok  # noqa: F401
from integration.metricas_helpers import m  # noqa: F401
from sociman_api.history import EntityVersion
from sociman_api.metricas.models import BuscaPost, FotoVideo, Serie, VideoRede
from sociman_api.notificacoes.models import Notificacao
from sociman_api.postagem.models import Postagem


def _por_tipo(corpo) -> dict:
    out: dict = {}
    for a in corpo["alertas"]:
        out.setdefault(a["tipo"], []).append(a)
    return out


def _foto(db, video_id, horas: float, views: int) -> None:
    v = db.get(VideoRede, video_id)
    s = int(horas * 3600)
    db.add(FotoVideo(video_id=video_id, coletado_em=v.publicado_em + timedelta(seconds=s),
                     idade_s=s, alvo_idade_min=s // 60, views=views, likes=0, comments=0,
                     shares=0))
    db.commit()


def test_estagnado_fixo_com_poucos_videos(cena):  # noqa: F811
    # 1 vídeo com 0 view nas 8 fotos horárias (publicado ontem às 8:00) e um com 2 h de vida,
    # que ainda não serve de referência para 8 h
    s = cena.semear(videos=1, fotos=8, views_por_h=0, inicio=local(1, 8))
    cena.semear(videos=1, fotos=1, views_por_h=0, inicio=agora() - timedelta(hours=2),
                serie_id=s.serie_id)
    corpo = cena.ok("alertas")
    [a] = corpo["alertas"]
    assert (a["tipo"], a["severidade"]) == ("estagnado", "atencao")
    assert a["alvo"] == {"tipo": "video", "id": str(s.videos[0]), "rotulo": "Post de teste #fyp"}
    assert a["numeros"] == {"idadeH": 8.0, "views": 0, "referencias": 0}
    assert "restrito" in a["motivo"] and a["link"] == f"/app/metricas/videos/{s.videos[0]}"
    assert corpo["contagem"] == {"atencao": 1, "info": 0, "positivo": 0}
    # a condição deixa de valer (uma foto com views): o alerta some
    _foto(cena.db, s.videos[0], 9, 50)
    assert cena.ok("alertas")["alertas"] == []


def test_estagnado_relativo_e_destaque(cena):  # noqa: F811
    # 6 vídeos a cada 12 h desde 6 dias atrás: na idade de 10 h, 1000·(i+1) views
    s = cena.semear(videos=6, fotos=10, intervalo_h=12, inicio=local(6, 10))
    baixo = cena.semear(videos=1, fotos=10, views_por_h=5, inicio=local(1, 10),
                        serie_id=s.serie_id).videos[0]  # 50 com 10 h
    alto = cena.semear(videos=1, fotos=10, views_por_h=2000, inicio=local(1, 11),
                       serie_id=s.serie_id).videos[0]  # 20000 com 10 h
    tipos = _por_tipo(cena.ok("alertas"))
    assert set(tipos) == {"estagnado", "destaque"}
    [e] = tipos["estagnado"]
    # referências do baixo: 1000…6000 e 20000 → mediana 4000; 50 < 400
    assert e["alvo"]["id"] == str(baixo)
    assert e["numeros"] == {"idadeH": 10.0, "views": 50, "referencias": 7,
                            "medianaReferencia": 4000}
    [d] = tipos["destaque"]
    # referências do alto: 50, 1000…6000 → mediana 3000; 20000 > 9000
    assert (d["alvo"]["id"], d["severidade"]) == (str(alto), "positivo")
    assert d["numeros"]["medianaReferencia"] == 3000
    corpo = cena.ok("alertas")
    assert [a["severidade"] for a in corpo["alertas"]] == ["atencao", "positivo"]
    assert corpo["contagem"] == {"atencao": 1, "info": 0, "positivo": 1}
    # fora do período, nada
    assert cena.ok("alertas", de=str(local(40).date()), ate=str(local(30).date()))["alertas"] == []


def test_sem_coleta(m):  # noqa: F811
    serie = m.db.scalar(select(Serie).where(Serie.conta_id == uuid.UUID(m.conta["id"])))

    def ultima(horas: float) -> list:
        m.db.execute(text("UPDATE metricas_series SET ultima_coleta_em = now() - "
                          "make_interval(secs => :s) WHERE id = :i"),
                     {"s": horas * 3600, "i": serie.id})
        m.db.commit()
        r = m.client.get("/api/analytics/alertas", headers=m.h)
        assert r.status_code == 200, r.text
        return _por_tipo(r.json()).get("sem_coleta", [])

    [a] = ultima(4)
    assert a["alvo"] == {"tipo": "serie", "id": m.conta["id"], "rotulo": "@atavernanerd"}
    assert a["numeros"]["horasSemColeta"] == pytest.approx(4, abs=0.1)
    assert a["severidade"] == "atencao"
    assert ultima(1) == []


def test_vinculo_a_confirmar_e_nada_gravado(m):  # noqa: F811
    d = m.rascunho()
    p1 = m.post(minutos=0)
    p2 = m.post(minutos=1)
    m.coletar(agora() + timedelta(hours=2))
    assert m.vinculo(d["id"])["estado"] == "a_confirmar"
    tabelas = (VideoRede, FotoVideo, Postagem, BuscaPost, Notificacao, EntityVersion)

    def contar():
        m.db.expire_all()
        return [m.db.scalar(select(func.count()).select_from(t)) for t in tabelas]

    antes = contar()
    r = m.client.get("/api/analytics/alertas", headers=m.h)
    assert r.status_code == 200, r.text
    assert contar() == antes
    [a] = _por_tipo(r.json())["vinculo_a_confirmar"]
    assert a["alvo"]["tipo"] == "destino" and a["alvo"]["id"] == d["id"]
    assert (a["severidade"], a["numeros"]) == ("info", {"candidatos": 2})
    assert a["link"] == f"/app/conteudos/{d['conteudoId']}"
    # o dono escolhe: o alerta some
    assert m.ligar(d, videoId=str(m.video_de(p2).id)).status_code == 200
    r = m.client.get("/api/analytics/alertas", headers=m.h)
    assert "vinculo_a_confirmar" not in _por_tipo(r.json())
    assert m.video_de(p1).destino_id is None
