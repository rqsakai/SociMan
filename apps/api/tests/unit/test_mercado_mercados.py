"""T010 (FR-001, FR-027): a dimensão `mercado` em código e o dia/turno decididos pelo servidor."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from sociman_api.errors import ApiError
from sociman_api.mercado import constantes, mercados
from sociman_api.mercado.mercados import Turno

SP = ZoneInfo("America/Sao_Paulo")


def test_so_br_e_fuso_e_moeda():
    assert set(mercados.MERCADOS) == {"BR"}
    assert mercados.mercado("BR").tz == "America/Sao_Paulo"
    assert mercados.mercado("BR").moeda == "BRL"


def test_mercado_desconhecido_e_erro_400():
    with pytest.raises(ApiError) as exc:
        mercados.mercado("US")
    assert exc.value.status == 400 and exc.value.code == "mercado_desconhecido"


def test_meia_noite_e_do_fuso_do_mercado_nao_do_utc():
    # 01:30 UTC de 10/10 ainda é 22:30 de 09/10 em São Paulo: a foto é do dia 9, turno noite.
    d, t = mercados.data_local_e_turno(datetime(2026, 10, 10, 1, 30, tzinfo=UTC), "BR")
    assert (d, t) == (date(2026, 10, 9), Turno.noite)


def test_corte_do_turno():
    assert constantes.TURNO_CORTE == "15:30"
    manha = datetime(2026, 10, 9, 15, 29, tzinfo=SP)
    noite = datetime(2026, 10, 9, 15, 31, tzinfo=SP)
    assert mercados.data_local_e_turno(manha, "BR") == (date(2026, 10, 9), Turno.manha)
    assert mercados.data_local_e_turno(noite, "BR") == (date(2026, 10, 9), Turno.noite)
    assert mercados.data_local_e_turno(datetime(2026, 10, 9, 15, 30, tzinfo=SP), "BR")[1] \
        == Turno.noite


def test_sem_fuso_vale_utc():
    ingenuo = datetime(2026, 10, 10, 1, 0, tzinfo=UTC).replace(tzinfo=None)
    d, _ = mercados.data_local_e_turno(ingenuo, "BR")
    assert d == date(2026, 10, 9)


def test_constantes_sao_nomeadas_uma_por_linha():
    """FR-050: cada limiar tem nome; os números do data-model ficam aqui, e só aqui."""
    assert constantes.MIN_FOTOS_VENDAS == 2
    assert constantes.K_AFILIADOS == 5
    assert constantes.POUCOS_AFILIADOS == 50
    assert constantes.NOVO_DIAS == 30
    assert constantes.RANKING_ACOMPANHAR_TOP == 30
    assert constantes.CATEGORIAS_MAX == 5
    assert constantes.CAPTCHA_ESFRIAR_MIN == 60
    assert constantes.PERIODO_MAX_DIAS == 400
    assert constantes.CATEGORIAS_CADA_DIAS == 7
