"""Janela de horário, avaliada no fuso do servidor (contracts/coletor.md, "Relógio"). Puro.

`Janela(8, 23)` = das 08:00 às 22:59. `inicio > fim` cruza a meia-noite (`Janela(22, 6)`).
`inicio == fim` = o dia inteiro. A janela efetiva é a interseção da local com a do servidor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Janela:
    inicio: int
    fim: int

    def __post_init__(self) -> None:
        for h in (self.inicio, self.fim):
            if not 0 <= h <= 23:
                raise ValueError("hora da janela fora de 0..23")

    def horas(self) -> frozenset[int]:
        """As horas inteiras em que a janela está aberta."""
        if self.inicio == self.fim:
            return frozenset(range(24))
        if self.inicio < self.fim:
            return frozenset(range(self.inicio, self.fim))
        return frozenset(range(self.inicio, 24)) | frozenset(range(0, self.fim))

    def contem_hora(self, hora: int) -> bool:
        return hora in self.horas()

    def dentro(self, agora: datetime, fuso: str) -> bool:
        """`agora` (com fuso) convertido para o fuso do servidor; a hora inteira decide."""
        return self.contem_hora(_local(agora, fuso).hour)

    def proxima_abertura(self, agora: datetime, fuso: str) -> datetime:
        """O próximo instante (no fuso) em que a janela abre; `agora` se já está aberta."""
        local = _local(agora, fuso)
        if self.contem_hora(local.hour):
            return local
        candidato = local.replace(minute=0, second=0, microsecond=0)
        for _ in range(48):
            candidato += timedelta(hours=1)
            if self.contem_hora(candidato.hour):
                return candidato
        return candidato  # inalcançável: a janela sempre tem ao menos uma hora

    def segundos_ate_abertura(self, agora: datetime, fuso: str) -> float:
        return max(0.0, (self.proxima_abertura(agora, fuso) - _local(agora, fuso)).total_seconds())


def _local(agora: datetime, fuso: str) -> datetime:
    if agora.tzinfo is None:
        raise ValueError("o instante precisa ter fuso")
    return agora.astimezone(ZoneInfo(fuso))


def intersecao(a: Janela, b: Janela) -> Janela | None:
    """A maior faixa contígua de horas comum às duas; None quando não se tocam."""
    comuns = a.horas() & b.horas()
    if not comuns:
        return None
    if len(comuns) == 24:
        return Janela(0, 0)
    # Procura o início de uma faixa: uma hora presente cuja anterior (circular) não está.
    inicios = [h for h in comuns if (h - 1) % 24 not in comuns]
    melhor: tuple[int, int] | None = None
    for ini in inicios:
        tamanho = 0
        h = ini
        while h in comuns and tamanho < 24:
            tamanho += 1
            h = (h + 1) % 24
        if melhor is None or tamanho > melhor[1]:
            melhor = (ini, tamanho)
    assert melhor is not None
    ini, tamanho = melhor
    return Janela(ini, (ini + tamanho) % 24)


def agora_com_fuso(fuso: str) -> datetime:
    return datetime.now(ZoneInfo(fuso))


def proximo_dia_local(agora: datetime, fuso: str) -> datetime:
    """Meia-noite seguinte no fuso do servidor (para dormir até o próximo dia local)."""
    local = _local(agora, fuso)
    return (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
