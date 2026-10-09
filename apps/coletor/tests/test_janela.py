"""Janela de horário no fuso do servidor: 08:00/22:59/23:00, fuso, meia-noite, interseção."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from sociman_coletor.janela import Janela, intersecao, proximo_dia_local

SP = "America/Sao_Paulo"


def _sp(h: int, m: int = 0) -> datetime:
    return datetime(2026, 10, 9, h, m, tzinfo=ZoneInfo(SP))


def test_limites_da_janela_padrao():
    j = Janela(8, 23)
    assert not j.dentro(_sp(7, 59), SP)
    assert j.dentro(_sp(8, 0), SP)
    assert j.dentro(_sp(22, 59), SP)
    assert not j.dentro(_sp(23, 0), SP)


def test_avaliada_no_fuso_do_servidor_nao_no_local():
    j = Janela(8, 23)
    # 01:30Z = 22:30 em São Paulo (UTC-3): dentro; em UTC estaria fora.
    assert j.dentro(datetime(2026, 10, 10, 1, 30, tzinfo=UTC), SP)
    # 02:30Z = 23:30 em São Paulo: fora.
    assert not j.dentro(datetime(2026, 10, 10, 2, 30, tzinfo=UTC), SP)
    with pytest.raises(ValueError):
        j.dentro(datetime(2026, 10, 10, 1, 30), SP)


def test_cruzando_a_meia_noite():
    j = Janela(22, 6)
    assert j.dentro(_sp(23), SP) and j.dentro(_sp(2), SP) and j.dentro(_sp(5, 59), SP)
    assert not j.dentro(_sp(6), SP) and not j.dentro(_sp(12), SP)
    assert j.proxima_abertura(_sp(12), SP).hour == 22
    assert Janela(0, 0).horas() == frozenset(range(24))


def test_proxima_abertura_e_segundos():
    j = Janela(8, 23)
    prox = j.proxima_abertura(_sp(23, 30), SP)
    assert (prox.day, prox.hour, prox.minute) == (10, 8, 0)
    assert j.segundos_ate_abertura(_sp(23, 30), SP) == 8.5 * 3600
    assert j.segundos_ate_abertura(_sp(10), SP) == 0
    assert proximo_dia_local(_sp(10), SP) == _sp(0).replace(day=10)


def test_intersecao():
    assert intersecao(Janela(8, 23), Janela(10, 18)) == Janela(10, 18)
    assert intersecao(Janela(8, 23), Janela(20, 2)) == Janela(20, 23)
    assert intersecao(Janela(8, 12), Janela(14, 18)) is None
    assert intersecao(Janela(0, 0), Janela(9, 21)) == Janela(9, 21)
    assert intersecao(Janela(22, 6), Janela(23, 3)) == Janela(23, 3)


def test_hora_invalida():
    with pytest.raises(ValueError):
        Janela(24, 1)
