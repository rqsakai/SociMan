"""Período do filtro do analytics (spec 019, T007): padrão de 7 dias, anterior de mesma duração,
virada de dia em São Paulo, período de 1 dia e período inválido. Puro (o perfil e a conta são
conferidos nos testes de integração das rotas)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from sociman_api.analytics import base
from sociman_api.analytics.filtros import Filtro, periodos
from sociman_api.errors import ApiError

HOJE = date(2026, 10, 1)


def test_padrao_ultimos_7_dias_e_anterior():
    atual, anterior = periodos(None, None, HOJE)
    assert (atual.de, atual.ate, atual.dias) == (date(2026, 9, 25), HOJE, 7)
    assert (anterior.de, anterior.ate) == (date(2026, 9, 18), date(2026, 9, 24))
    assert anterior.fim == atual.ini  # sem buraco nem sobreposição


def test_virada_de_dia_em_sao_paulo():
    atual, _ = periodos(HOJE, HOJE, HOJE)
    # 00:00 em SP (UTC−3) = 03:00 UTC; o fim é o 00:00 do dia seguinte (exclusivo)
    assert atual.ini.astimezone(UTC) == datetime(2026, 10, 1, 3, tzinfo=UTC)
    assert atual.fim.astimezone(UTC) == datetime(2026, 10, 2, 3, tzinfo=UTC)
    # 23:30 de 30/09 em SP (02:30 UTC de 01/10) ainda é o dia anterior
    assert not atual.ini <= datetime(2026, 10, 1, 2, 30, tzinfo=UTC) < atual.fim


def test_periodo_de_um_dia():
    atual, anterior = periodos(date(2026, 9, 10), date(2026, 9, 10), HOJE)
    assert atual.dias == 1 and anterior.dias == 1
    assert (anterior.de, anterior.ate) == (date(2026, 9, 9), date(2026, 9, 9))


def test_so_uma_das_datas():
    atual, _ = periodos(date(2026, 9, 1), None, HOJE)
    assert (atual.de, atual.ate) == (date(2026, 9, 1), HOJE)
    atual, _ = periodos(None, date(2026, 9, 10), HOJE)
    assert (atual.de, atual.ate) == (date(2026, 9, 4), date(2026, 9, 10))


def test_anterior_de_periodo_longo():
    atual, anterior = periodos(date(2026, 9, 1), date(2026, 9, 30), HOJE)
    assert atual.dias == anterior.dias == 30
    assert (anterior.de, anterior.ate) == (date(2026, 8, 2), date(2026, 8, 31))


@pytest.mark.parametrize(("de", "ate"), [
    (date(2026, 9, 10), date(2026, 9, 9)),  # ate < de
    (HOJE - timedelta(days=400), HOJE),  # 401 dias
    (date(2026, 10, 5), None),  # de depois de hoje (ate = hoje)
])
def test_periodo_invalido(de, ate):
    with pytest.raises(ApiError) as e:
        periodos(de, ate, HOJE)
    assert (e.value.status, e.value.code) == (400, "periodo_invalido")


def test_400_dias_ainda_vale():
    atual, _ = periodos(HOJE - timedelta(days=399), HOJE, HOJE)
    assert atual.dias == 400


def test_medida_em_segundos():
    atual, anterior = periodos(None, None, HOJE)
    f = Filtro(atual=atual, anterior=anterior, perfil_id=None, conta_id=None, rede=None,
               medida="h1")
    assert f.medida_s == 3600
    assert Filtro(**{**f.__dict__, "medida": "d7"}).medida_s == 7 * 24 * 3600


def test_titulo_curto_e_hashtags():
    assert base.titulo_curto(None) == "Sem legenda"
    assert base.titulo_curto(None, anonima=True) == "Vídeo anônimo"
    assert base.titulo_curto("  curta  ") == "curta"
    longa = "a" * 39 + " bcdef"
    assert base.titulo_curto(longa) == "a" * 39 + "…"
    assert base.hashtags(["#Marvel", "Ação", "marvel"], "Vídeo #AÇÃO #fyp e #Marvel") == (
        "marvel", "acao", "fyp")
    assert base.hashtags(None, None) == ()


def test_delta_do_ganho():
    assert base._delta(10, 4) == 6
    assert base._delta(7, None) == 7  # sem foto antes do início
    assert base._delta(5, 10) == 0  # caiu: 0
    assert base._delta(None, 3) == 0
