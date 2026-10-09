"""Cadência por idade e janela da conta (spec 016, T029; research R4 a R6). Funções puras."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from sociman_api.metricas import agenda

H, D = 60, 24 * 60
PUB = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
SP = "America/Sao_Paulo"


def test_alvos_por_faixa():
    a = agenda.alvos()
    assert len(a) == 48 + 28 + 9 + 10 == 95
    assert a[:48] == tuple(range(H, 48 * H + 1, H))
    assert a[48:76] == tuple(d * D for d in range(3, 31))
    assert a[76:85] == tuple(d * D for d in (37, 44, 51, 58, 65, 72, 79, 86, 90))
    assert a[85:] == tuple(d * D for d in (120, 150, 180, 210, 240, 270, 300, 330, 360, 365))
    assert list(a) == sorted(set(a))


@pytest.mark.parametrize("alvo, tol", [(H, 15), (2 * H, 15), (3 * D, 15), (90 * D, 15),
                                       (365 * D, 15)])
def test_tolerancia(alvo, tol):
    assert agenda.tolerancia(alvo) == tol


def test_proxima_coleta_menor_alvo_maior_que_a_idade():
    assert agenda.proxima_coleta(PUB, 0) == PUB + timedelta(hours=1)
    assert agenda.proxima_coleta(PUB, 30) == PUB + timedelta(hours=1)
    assert agenda.proxima_coleta(PUB, 60) == PUB + timedelta(hours=2)
    assert agenda.proxima_coleta(PUB, 65) == PUB + timedelta(hours=2)
    assert agenda.proxima_coleta(PUB, 48 * H) == PUB + timedelta(days=3)
    assert agenda.proxima_coleta(PUB, 30 * D) == PUB + timedelta(days=37)
    assert agenda.proxima_coleta(PUB, 86 * D + 1) == PUB + timedelta(days=90)
    assert agenda.proxima_coleta(PUB, 360 * D) == PUB + timedelta(days=365)


def test_depois_de_365_dias_para():
    assert agenda.proxima_coleta(PUB, 365 * D) is None
    assert agenda.proxima_coleta(PUB, 400 * D) is None


def test_atraso_pula_para_o_alvo_mais_recente_ja_vencido():
    assert agenda.alvo_vencido(59) is None
    assert agenda.alvo_vencido(60) == 60
    assert agenda.alvo_vencido(74) == 60
    # agendador parado 5 h: a foto vai para as 6 h, e 2 h … 5 h ficam sem foto (nada inventado)
    assert agenda.alvo_vencido(6 * H + 40) == 6 * H
    assert agenda.proxima_coleta(PUB, 6 * H + 40) == PUB + timedelta(hours=7)
    assert agenda.alvo_vencido(10 * D) == 10 * D
    assert agenda.alvo_vencido(500 * D) == 365 * D


def test_foto_de_descoberta():
    assert agenda.alvo_descoberta(30.5) == 30  # antes do 1º alvo: floor da idade
    assert agenda.alvo_descoberta(60) == 60
    assert agenda.alvo_descoberta(75) == 60  # dentro da tolerância do alvo de 1 h
    assert agenda.alvo_descoberta(75.5) == 75  # fora dela: floor
    assert agenda.alvo_descoberta(3 * H + 10) == 3 * H
    assert agenda.alvo_descoberta(400 * D + 7) == 400 * D + 7  # mais de 1 ano (Q2 = A)
    assert agenda.proxima_coleta(PUB, 400 * D + 7) is None


def test_idade_nunca_negativa():
    assert agenda.idade_min(PUB, PUB - timedelta(minutes=3)) == 0


def test_janela_da_conta_horaria_e_diaria():
    agora = datetime(2026, 9, 30, 14, 37, 12, tzinfo=UTC)  # 11:37 em SP
    assert agenda.janela_conta(agora, True, SP) == datetime(2026, 9, 30, 14, tzinfo=UTC)
    assert agenda.proxima_janela_conta(agora, True, SP) == datetime(2026, 9, 30, 15, tzinfo=UTC)
    assert agenda.janela_conta(agora, False, SP) == datetime(2026, 9, 30, 3, tzinfo=UTC)
    assert agenda.proxima_janela_conta(agora, False, SP) == datetime(2026, 10, 1, 3, tzinfo=UTC)
    # 01:30 UTC ainda é o dia anterior em SP
    madrugada = datetime(2026, 10, 1, 1, 30, tzinfo=UTC)
    assert agenda.janela_conta(madrugada, False, SP) == datetime(2026, 9, 30, 3, tzinfo=UTC)


def test_janela_diaria_na_virada_do_horario_de_verao():
    """Fuso com horário de verão: a meia-noite local muda de offset e continua certa."""
    ny = "America/New_York"
    antes = datetime(2026, 3, 8, 12, tzinfo=UTC)  # dia da virada nos EUA
    meia_noite = agenda.janela_conta(antes, False, ny)
    assert meia_noite.astimezone(ZoneInfo(ny)).hour == 0
    proxima = agenda.proxima_janela_conta(antes, False, ny)
    assert proxima.astimezone(ZoneInfo(ny)).hour == 0
    assert proxima - meia_noite == timedelta(hours=23)


def test_conta_vencida():
    agora = datetime(2026, 9, 30, 14, 37, tzinfo=UTC)
    assert agenda.conta_vencida(None, agora, False)  # série nova: 1ª foto já (SC-001)
    assert agenda.conta_vencida(agora, agora, False)
    assert not agenda.conta_vencida(agora + timedelta(minutes=23), agora, True)
    assert not agenda.conta_vencida(agora + timedelta(hours=12), agora, False)
    # agenda diária gravada, mas apareceu um vídeo novo: vira horária na hora
    assert agenda.conta_vencida(agora + timedelta(hours=12), agora, True)
