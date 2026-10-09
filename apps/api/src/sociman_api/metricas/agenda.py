"""Cadência das fotos (research R4 e R6 da spec 016): funções puras, sem banco e sem relógio.

- **Vídeo:** a agenda é ancorada na idade (`publicado_em`). Os alvos saem de `alvos()`: de hora
  em hora até 48 h, diária até 30 d, semanal até 90 d e mensal até 365 d. Uma foto vale para o
  alvo `A` se sair entre `A` e `A + min(15 min, passo/4)`; com atraso, a foto vai **só** para o
  alvo mais recente já vencido (nada é inventado). Depois de 365 d, a coleta para.
- **Conta:** janela horária (hora cheia) quando a série tem vídeo com menos de 48 h; senão
  diária (00:00 de `APP_TZ`).

As constantes ficam uma por linha: o ajuste depois da medição do `view_count` (R19) é uma linha,
com o teste de `tests/unit/test_agenda_metricas.py`.
"""

import math
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

HORA = 60  # minutos
DIA = 24 * HORA

HORARIA_ATE = 48 * HORA  # faixa de 1 h
DIARIA_ATE = 30 * DIA  # faixa de 1 d (começa em 3 d)
SEMANAL_ATE = 90 * DIA  # faixa de 7 d (começa em 37 d; fecha em 90 d)
MENSAL_ATE = 365 * DIA  # faixa de 30 d (começa em 120 d; fecha em 365 d)
TOLERANCIA_MAX = 15  # minutos
CONTA_HORARIA = timedelta(hours=48)  # vídeo mais novo que isso → foto da conta de hora em hora


@lru_cache
def alvos() -> tuple[int, ...]:
    """As idades-alvo em minutos, em ordem: 48 + 28 + 9 + 10 = 95."""
    a = list(range(HORA, HORARIA_ATE + 1, HORA))
    a += range(3 * DIA, DIARIA_ATE + 1, DIA)
    a += range(DIARIA_ATE + 7 * DIA, SEMANAL_ATE, 7 * DIA)
    a.append(SEMANAL_ATE)
    a += range(SEMANAL_ATE + 30 * DIA, MENSAL_ATE, 30 * DIA)
    a.append(MENSAL_ATE)
    return tuple(a)


def tolerancia(alvo: int) -> int:
    """`min(15 min, passo/4)`, com o passo = distância ao alvo anterior."""
    todos = alvos()
    i = todos.index(alvo)
    passo = alvo - (todos[i - 1] if i else 0)
    return min(TOLERANCIA_MAX, passo // 4)


def idade_min(publicado_em: datetime, agora: datetime) -> float:
    return max(0.0, (agora - publicado_em).total_seconds() / 60)


def alvo_vencido(idade: float) -> int | None:
    """O alvo mais recente já vencido (`≤ idade`), ou None antes de 1 h."""
    vencidos = [a for a in alvos() if a <= idade]
    return vencidos[-1] if vencidos else None


def alvo_descoberta(idade: float) -> int:
    """Alvo da foto de descoberta (R5): o alvo cuja tolerância contém a idade, para não gastar
    outra foto na mesma janela; senão `floor(idade)`."""
    a = alvo_vencido(idade)
    if a is not None and idade <= a + tolerancia(a):
        return a
    return math.floor(idade)


def proxima_coleta(publicado_em: datetime, idade_ultima: float) -> datetime | None:
    """`publicado_em + menor alvo > idade da última foto`; None depois de 365 d."""
    for a in alvos():
        if a > idade_ultima:
            return publicado_em + timedelta(minutes=a)
    return None


# ---- conta (R6) ----

@lru_cache
def _tz(nome: str) -> ZoneInfo:
    return ZoneInfo(nome)


def hora_cheia(agora: datetime) -> datetime:
    return agora.replace(minute=0, second=0, microsecond=0)


def janela_conta(agora: datetime, horaria: bool, tz: str) -> datetime:
    """A hora cheia (horária) ou 00:00 do dia em `tz` (diária), em UTC se `agora` for UTC."""
    if horaria:
        return hora_cheia(agora)
    local = agora.astimezone(_tz(tz))
    return datetime(local.year, local.month, local.day, tzinfo=_tz(tz)).astimezone(agora.tzinfo)


def proxima_janela_conta(agora: datetime, horaria: bool, tz: str) -> datetime:
    if horaria:
        return hora_cheia(agora) + timedelta(hours=1)
    local = agora.astimezone(_tz(tz)).date() + timedelta(days=1)
    return datetime(local.year, local.month, local.day, tzinfo=_tz(tz)).astimezone(agora.tzinfo)


def conta_vencida(conta_proxima_em: datetime | None, agora: datetime, horaria: bool) -> bool:
    """A foto da conta sai agora? Sem agenda (série nova, SC-001), com a janela vencida, ou no
    modo horário quando a agenda gravada é a diária (um vídeo novo apareceu)."""
    if conta_proxima_em is None or conta_proxima_em <= agora:
        return True
    return horaria and conta_proxima_em > hora_cheia(agora) + timedelta(hours=1)
