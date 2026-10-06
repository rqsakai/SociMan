"""Quando postar (spec 019, US2, T028; research R4): o mapa por horário de publicação (mediana e
n por célula, no fuso de SP), o mapa da audiência (ganho entre fotos consecutivas dividido pelas
horas cobertas quando o intervalo tem até 3 h; acima disso, `semHora`; queda conta 0) e o
calendário, com cálculo de referência."""

from datetime import timedelta

import pytest

from integration.analytics_helpers import cena, hoje_sp, local  # noqa: F401
from sociman_api.metricas.models import FotoVideo


def _dias_atras(dia_semana: int, minimo: int = 2) -> int:
    """Quantos dias atrás (≥ `minimo`) caiu o último `dia_semana` (0 = segunda)."""
    return next(k for k in range(minimo, minimo + 7)
                if (hoje_sp() - timedelta(days=k)).weekday() == dia_semana)


def _celula(mapa, dia, hora):
    [c] = [c for c in mapa["celulas"] if (c["dia"], c["hora"]) == (dia, hora)]
    return c


def test_mapa_por_horario_de_publicacao(cena):  # noqa: F811
    terca = _dias_atras(1)
    domingo = _dias_atras(6)
    # 3 posts na terça às 19:00, 19:15 e 19:30, com 1 h = 150, 300 e 450 (mediana 300)
    s = cena.semear(videos=3, fotos=2, inicio=local(terca, 19), intervalo_h=0.25,
                    views_por_h=150)
    # 23:30 de domingo em SP (02:30 UTC de segunda) conta no domingo às 23 h
    cena.semear(videos=1, fotos=2, inicio=local(domingo, 23, 30), serie_id=s.serie_id)
    de, ate = local(max(terca, domingo)).date(), local(min(terca, domingo)).date()
    corpo = cena.ok("quando-postar", de=str(de), ate=str(ate), medida="h1")
    mapa = corpo["porPublicacao"]
    assert len(mapa["celulas"]) == 7 * 24
    assert _celula(mapa, 1, 19) == {"dia": 1, "hora": 19, "valor": 300, "n": 3,
                                    "amostraPequena": True}
    dom = _celula(mapa, 6, 23)
    assert (dom["n"], dom["valor"]) == (1, 100)
    assert _celula(mapa, 0, 2) == {"dia": 0, "hora": 2, "valor": None, "n": 0,
                                   "amostraPequena": False}
    assert sum(c["n"] for c in mapa["celulas"]) == 4
    # com 24 h, as 2 fotos horárias não alcançam o marco: sem dado, células vazias
    h24 = cena.ok("quando-postar", de=str(de), ate=str(ate))["porPublicacao"]
    assert all(c["valor"] is None for c in h24["celulas"])


def _foto(c, video_id, pub, quando, views):
    idade = int((quando - pub).total_seconds())
    c.db.add(FotoVideo(video_id=video_id, coletado_em=quando, idade_s=idade,
                       alvo_idade_min=idade // 60, views=views, likes=0, comments=0,
                       shares=0))


def _audiencia(c):
    """Publicado em D−3 às 06:00; fotos às 10:00 (100), 11:00 (160), 13:30 (310), D−2 13:30
    (1310) e D−2 14:30 (1200, queda)."""
    pub = local(3, 6)
    s = c.semear(videos=1, fotos=0, inicio=pub)
    [vid] = s.videos
    for quando, views in ((local(3, 10), 100), (local(3, 11), 160), (local(3, 13, 30), 310),
                          (local(2, 13, 30), 1310), (local(2, 14, 30), 1200)):
        _foto(c, vid, pub, quando, views)
    c.db.commit()
    return pub


def test_mapa_da_audiencia(cena):  # noqa: F811
    pub = _audiencia(cena)
    dia, seguinte = pub.weekday(), (pub.weekday() + 1) % 7
    aud = cena.ok("quando-postar")["audiencia"]
    assert len(aud["celulas"]) == 7 * 24
    # 10 h → 11 h: 60 na célula das 10 h
    assert (_celula(aud, dia, 10)["valor"], _celula(aud, dia, 10)["n"]) == (60, 1)
    # 11:00 → 13:30 (2 h 30, ganho 150): proporcional aos minutos de cada hora
    assert _celula(aud, dia, 11)["valor"] == pytest.approx(60)
    assert _celula(aud, dia, 12)["valor"] == pytest.approx(60)
    assert _celula(aud, dia, 13)["valor"] == pytest.approx(30)
    # a queda conta 0 (a célula existe, com n = 1)
    assert (_celula(aud, seguinte, 14)["valor"], _celula(aud, seguinte, 14)["n"]) == (0, 1)
    # publicação → 10:00 (4 h, 100) e D−3 13:30 → D−2 13:30 (24 h, 1000): sem hora
    assert aud["semHora"] == 1100
    total = sum(c["valor"] or 0 for c in aud["celulas"])
    assert total + aud["semHora"] == pytest.approx(1310)  # nada some nem duplica
    assert _celula(aud, dia, 6)["valor"] is None


def test_audiencia_so_conta_o_periodo(cena):  # noqa: F811
    pub = _audiencia(cena)
    dia = str(local(2).date())
    aud = cena.ok("quando-postar", de=dia, ate=dia)["audiencia"]
    assert aud["semHora"] == 1000  # só o intervalo que termina em D−2
    assert _celula(aud, pub.weekday(), 10)["valor"] is None
    # a queda (13:30 → 14:30) toca as 13 h e as 14 h, com 0 em cada
    seguinte = (pub.weekday() + 1) % 7
    assert [(c["dia"], c["hora"], c["valor"], c["n"]) for c in aud["celulas"] if c["n"]] == [
        (seguinte, 13, 0, 1), (seguinte, 14, 0, 1)]


def test_calendario(cena):  # noqa: F811
    _audiencia(cena)
    corpo = cena.ok("quando-postar")
    cal = {d["dia"]: (d["posts"], d["views"]) for d in corpo["calendario"]}
    assert list(cal) == [str(hoje_sp() - timedelta(days=k)) for k in range(6, -1, -1)]
    assert cal[str(local(3).date())] == (1, 310)
    assert cal[str(local(2).date())] == (0, 1200 - 310)
    assert cal[str(local(1).date())] == (0, 0)
    assert corpo["contexto"]["postsNoPeriodo"] == 1
