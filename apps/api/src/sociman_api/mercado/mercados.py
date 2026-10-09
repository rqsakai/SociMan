"""A dimensão `mercado` (país) em código (FR-001): só `BR` nesta spec.

O servidor decide `data_local` e `turno` de toda foto a partir do `coletado_em` convertido ao
fuso do mercado (FR-027; Edge "meia-noite" e "relógio errado"): o relógio do coletor nunca
manda. Outro país é outra conta, outro cliente de coleta e outra linha aqui.
"""

import enum
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sociman_api.errors import ApiError
from sociman_api.mercado.constantes import TURNO_CORTE

MERCADO_RE = re.compile(r"^[A-Z]{2}$")


class Turno(enum.StrEnum):
    manha = "manha"
    noite = "noite"


@dataclass(frozen=True)
class Mercado:
    codigo: str
    tz: str
    moeda: str

    @property
    def zona(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


MERCADOS: dict[str, Mercado] = {"BR": Mercado("BR", "America/Sao_Paulo", "BRL")}
PADRAO = "BR"


def mercado(codigo: str) -> Mercado:
    m = MERCADOS.get(codigo)
    if m is None:
        raise ApiError(400, "mercado_desconhecido", f"Mercado desconhecido: {codigo}")
    return m


def _corte() -> time:
    h, m = TURNO_CORTE.split(":")
    return time(int(h), int(m))


def hora_local(coletado_em: datetime, codigo: str = PADRAO) -> datetime:
    if coletado_em.tzinfo is None:
        coletado_em = coletado_em.replace(tzinfo=UTC)
    return coletado_em.astimezone(mercado(codigo).zona)


def data_local(coletado_em: datetime, codigo: str = PADRAO) -> date:
    return hora_local(coletado_em, codigo).date()


def data_local_e_turno(coletado_em: datetime, codigo: str = PADRAO) -> tuple[date, Turno]:
    """O dia e o turno da foto no fuso do mercado: `manha` antes de `TURNO_CORTE`, senão `noite`."""
    local = hora_local(coletado_em, codigo)
    turno = Turno.manha if local.time() < _corte() else Turno.noite
    return local.date(), turno


def hoje(codigo: str = PADRAO, agora: datetime | None = None) -> date:
    return data_local(agora or datetime.now(UTC), codigo)


def agora_local(codigo: str = PADRAO, agora: datetime | None = None) -> datetime:
    return hora_local(agora or datetime.now(UTC), codigo)
