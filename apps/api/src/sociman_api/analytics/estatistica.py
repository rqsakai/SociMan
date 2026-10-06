"""Estatística do analytics (spec 019, research R5): mediana, quartis, correlação de postos
(Spearman), lift e amostra mínima. Puro, sem numpy/scipy.

Toda conclusão (insight, correlação, lift, radar) carrega uma `Amostra`; abaixo do mínimo, a
tela mostra o dado bruto e "amostra pequena (n = X de Y)" (FR-006/SC-007).
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

MIN_GRUPO = 5  # medianas por grupo e lift
MIN_CORRELACAO = 8  # vídeos para mostrar ρ
MIN_CONTAS_RADAR = 2  # contas com post no período para o radar
MIN_CONTA_ESTAGNADO = 5  # vídeos da conta para o "estagnado" relativo (senão, ≤ 1 view)

FRACA_ATE = 0.3
MODERADA_ATE = 0.6


@dataclass(frozen=True)
class Amostra:
    n: int
    minimo: int

    @property
    def suficiente(self) -> bool:
        return self.n >= self.minimo

    @property
    def faltam(self) -> int:
        return max(0, self.minimo - self.n)


@dataclass(frozen=True)
class Quartis:
    min: float
    q1: float
    mediana: float
    q3: float
    max: float


def mediana(valores: Sequence[float]) -> float | None:
    return float(statistics.median(valores)) if valores else None


def quartis(valores: Sequence[float]) -> Quartis | None:
    """min/q1/mediana/q3/max (`statistics.quantiles`, método "inclusive"); com 1 valor, os 5
    são ele."""
    if not valores:
        return None
    if len(valores) == 1:
        v = float(valores[0])
        return Quartis(v, v, v, v, v)
    q1, med, q3 = statistics.quantiles(valores, n=4, method="inclusive")
    return Quartis(float(min(valores)), float(q1), float(med), float(q3), float(max(valores)))


def postos(valores: Sequence[float]) -> list[float]:
    """Postos 1..n; empates recebem a média dos postos que ocupariam."""
    ordem = sorted(range(len(valores)), key=lambda i: valores[i])
    out = [0.0] * len(valores)
    i = 0
    while i < len(ordem):
        j = i
        while j + 1 < len(ordem) and valores[ordem[j + 1]] == valores[ordem[i]]:
            j += 1
        medio = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[ordem[k]] = medio
        i = j + 1
    return out


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """ρ de Spearman (Pearson sobre os postos, o que trata empates). None com menos de 2 pares
    ou com um dos lados constante."""
    if len(xs) != len(ys):
        raise ValueError("xs e ys precisam ter o mesmo tamanho")
    if len(xs) < 2:
        return None
    rx, ry = postos(xs), postos(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return max(-1.0, min(1.0, cov / math.sqrt(vx * vy)))


def leitura_correlacao(rho: float | None) -> str | None:
    """|ρ| < 0,3 fraca; < 0,6 moderada; ≥ 0,6 forte; com o sinal ("forte negativa")."""
    if rho is None:
        return None
    forca = abs(rho)
    nome = "fraca" if forca < FRACA_ATE else "moderada" if forca < MODERADA_ATE else "forte"
    if rho == 0:
        return nome
    return f"{nome} {'positiva' if rho > 0 else 'negativa'}"


def lift(grupo: float | None, geral: float | None) -> float | None:
    """Mediana do grupo ÷ mediana geral; None sem base (geral nulo ou zero)."""
    if grupo is None or not geral:
        return None
    return grupo / geral
