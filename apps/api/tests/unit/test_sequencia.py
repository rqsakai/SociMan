"""Conflito de horários e planejador de sequência (spec 014, R7, Q3 = C)."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from sociman_api.conteudos import sequencia

TZ = ZoneInfo("America/Sao_Paulo")


def _t(h: int, m: int = 0, dia: int = 1) -> datetime:
    return datetime(2026, 10, dia, h, m, tzinfo=TZ)


# ---- conflitos ----

@pytest.mark.parametrize(("delta_min", "intervalo", "conflita"), [
    (0, 30, True), (29, 30, True), (30, 30, False), (-10, 30, True), (45, 30, False),
    (0, 0, True), (1, 0, False), (-1, 0, False),
    (1439, 1440, True), (1440, 1440, False),
])
def test_conflitos(delta_min, intervalo, conflita):
    ocupados = [(_t(19) + timedelta(minutes=delta_min), "d1")]
    assert sequencia.conflitos(_t(19), ocupados, intervalo) == (["d1"] if conflita else [])


def test_intervalo_zero_so_o_mesmo_minuto():
    ocupados = [(_t(19), "a"), (_t(19, 1), "b")]
    assert sequencia.conflitos(_t(19), ocupados, 0) == ["a"]


def test_conflitos_devolve_todos():
    ocupados = [(_t(18, 50), "a"), (_t(19, 10), "b"), (_t(20), "c")]
    assert sequencia.conflitos(_t(19), ocupados, 30) == ["a", "b"]


# ---- planejador ----

AGORA = datetime(2026, 9, 30, 12, 0, tzinfo=TZ)


def _plan(itens, horarios, ocupados=(), inicio=date(2026, 10, 1), agora=AGORA, intervalo=30):
    return sequencia.planejar(itens, inicio, horarios, list(ocupados), agora, intervalo, TZ)


def test_um_por_dia_na_ordem():
    slots, pulados = _plan(["a", "b", "c"], [time(19)])
    assert [(s.item, s.planned_at) for s in slots] == [
        ("a", _t(19, dia=1)), ("b", _t(19, dia=2)), ("c", _t(19, dia=3))]
    assert pulados == []


def test_dois_por_dia_ordenados():
    slots, _ = _plan(["a", "b", "c"], [time(19), time(12)])
    assert [s.planned_at for s in slots] == [_t(12, dia=1), _t(19, dia=1), _t(12, dia=2)]


def test_fuso_sao_paulo_na_virada_do_dia():
    slots, _ = _plan(["a"], [time(23, 30)])
    assert slots[0].planned_at.utcoffset() == timedelta(hours=-3)
    assert slots[0].planned_at.astimezone(ZoneInfo("UTC")).day == 2


def test_passado_pulado():
    agora = datetime(2026, 10, 1, 15, 0, tzinfo=TZ)
    slots, pulados = _plan(["a", "b"], [time(12), time(19)], agora=agora)
    assert [s.planned_at for s in slots] == [_t(19, dia=1), _t(12, dia=2)]
    assert [(p.planned_at, p.motivo) for p in pulados] == [(_t(12, dia=1), "passado")]


@pytest.mark.parametrize(("ocupado", "intervalo", "pula"), [
    (_t(19, 10), 30, True), (_t(19, 10), 0, False), (_t(19), 0, True), (_t(20, 30), 120, True),
])
def test_conflito_com_ocupados(ocupado, intervalo, pula):
    slots, pulados = _plan(["a"], [time(19)], ocupados=[(ocupado, "d9")], intervalo=intervalo)
    if pula:
        assert slots[0].planned_at == _t(19, dia=2)
        assert [(p.motivo, p.ocupante) for p in pulados] == [("conflito", "d9")]
    else:
        assert slots[0].planned_at == _t(19, dia=1)
        assert pulados == []


def test_conflito_dentro_da_propria_sequencia():
    # 19:00 e 19:20 no mesmo dia, com intervalo de 30: o segundo é pulado todo dia.
    slots, pulados = _plan(["a", "b"], [time(19), time(19, 20)])
    assert [s.planned_at for s in slots] == [_t(19, dia=1), _t(19, dia=2)]
    assert [(p.planned_at, p.motivo, p.ocupante) for p in pulados] == [
        (_t(19, 20, dia=1), "conflito", None)]


def test_limites():
    with pytest.raises(ValueError):
        _plan(list(range(101)), [time(19)])
    with pytest.raises(ValueError):
        _plan(["a"], [time(h) for h in range(7)])
    with pytest.raises(ValueError):
        _plan(["a"], [])
    with pytest.raises(ValueError):
        _plan(["a"], [time(19), time(19)])


def test_horizonte_de_180_dias():
    slots, _ = _plan(list(range(100)), [time(19)])
    assert len(slots) == 100
    # tudo ocupado: nenhum slot cabe, sem laço infinito
    ocupados = [(datetime.combine(date(2026, 10, 1) + timedelta(days=d), time(19), tzinfo=TZ), d)
                for d in range(sequencia.DIAS_MAX)]
    slots, pulados = _plan(["a"], [time(19)], ocupados=ocupados)
    assert slots == [] and len(pulados) == sequencia.DIAS_MAX
