"""Conflito de horários e planejador de sequência (research R7, FR-009, FR-009a).

Funções puras, sem banco. Dois horários da mesma conta conflitam quando
`abs(a - b) < max(intervalo_min, 1 min)`: com intervalo 0, só o mesmo minuto conflita.
A sequência **pula** o horário em conflito; o agendamento individual **avisa** (service).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ITENS_MAX = 100
HORARIOS_MAX = 6
DIAS_MAX = 180


def janela(intervalo_min: int) -> timedelta:
    return timedelta(minutes=max(intervalo_min, 1))


def em_conflito(a: datetime, b: datetime, intervalo_min: int) -> bool:
    return abs(a - b) < janela(intervalo_min)


def conflitos[T](horario: datetime, ocupados: Sequence[tuple[datetime, T]],
              intervalo_min: int) -> list[T]:
    """Os itens de `ocupados` (`(planned_at, item)`) que conflitam com `horario`."""
    return [item for quando, item in ocupados if em_conflito(horario, quando, intervalo_min)]


@dataclass(frozen=True)
class Slot:
    item: object  # o conteúdo (id) na ordem recebida
    planned_at: datetime


@dataclass(frozen=True)
class Pulado:
    planned_at: datetime
    motivo: str  # "passado" | "conflito"
    ocupante: object | None  # o destino (id) que ocupa o horário, ou None


def planejar[T](itens: Sequence[T], inicio: date, horarios: Sequence[time],
             ocupados: Sequence[tuple[datetime, object]], agora: datetime,
             intervalo_min: int, tz: ZoneInfo) -> tuple[list[Slot], list[Pulado]]:
    """Atribui os `itens`, na ordem, aos horários de cada dia a partir de `inicio` (APP_TZ).

    Pula os horários que já passaram e os que conflitam com `ocupados` (outros agendamentos
    ativos da conta) ou com um horário já atribuído nesta sequência. Para no horizonte de
    `DIAS_MAX` dias; os itens que não couberem ficam sem slot (quem chama os trata).
    """
    if len(itens) > ITENS_MAX:
        raise ValueError(f"No máximo {ITENS_MAX} conteúdos por sequência")
    if not 1 <= len(horarios) <= HORARIOS_MAX:
        raise ValueError(f"De 1 a {HORARIOS_MAX} horários por dia")
    if len(set(horarios)) != len(horarios):
        raise ValueError("Horário repetido")
    ordenados = sorted(horarios)
    slots: list[Slot] = []
    pulados: list[Pulado] = []
    atribuidos: list[tuple[datetime, object]] = []
    pendentes = list(itens)
    for dia in range(DIAS_MAX):
        if not pendentes:
            break
        data = inicio + timedelta(days=dia)
        for hora in ordenados:
            if not pendentes:
                break
            quando = datetime.combine(data, hora, tzinfo=tz)
            if quando <= agora:
                pulados.append(Pulado(quando, "passado", None))
                continue
            ocupante = conflitos(quando, ocupados, intervalo_min)
            if ocupante:
                pulados.append(Pulado(quando, "conflito", ocupante[0]))
                continue
            if conflitos(quando, atribuidos, intervalo_min):
                pulados.append(Pulado(quando, "conflito", None))
                continue
            item = pendentes.pop(0)
            slots.append(Slot(item, quando))
            atribuidos.append((quando, item))
    return slots, pulados
