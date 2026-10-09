"""Estatística do aprendizado (spec 023, R1 e R2). Funções puras, sem I/O, sem numpy.

- **medida:** y = ln(1 + views), que não explode com mediana 0 nem deixa um viral dominar;
- **peso:** 0,5^(idade/30 dias);
- **efeito encolhido:** Σw·d / (Σw + K), em que `d` é o desvio do post em relação à base da
  própria conta (entrega: e − p_c; rendimento: y − m_c). Com K = 5 e 3 posts de peso 1, o efeito
  cai a 3/8 do bruto;
- **intervalo:** reamostragem com reposição (B = 400) com semente fixa, percentis 10–90;
- **confiança:** regra fixa sobre n, dias, intervalo e tamanho do efeito.
"""

import hashlib
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from sociman_api.aprendizado import constantes as K

Parte = Literal["entrega", "rendimento"]
Confianca = Literal["forte", "moderada", "fraca", "indicio", "amostra_pequena"]


@dataclass(frozen=True)
class Item:
    """Um post num grupo: o desvio em relação à base da conta, o peso e as views (concentração)."""

    desvio: float
    peso: float
    views: float = 0.0
    chave: object = None  # o post (para "sem o maior" e para contar posts distintos)


def medida_log(views: float | None) -> float:
    return math.log1p(max(0.0, float(views or 0)))


def peso(idade_dias: float) -> float:
    return 0.5 ** (max(0.0, idade_dias) / K.MEIA_VIDA_DIAS)


def media_ponderada(valores: Sequence[tuple[float, float]]) -> float | None:
    """Σw·x / Σw de (x, w); None sem peso."""
    total = sum(w for _, w in valores)
    if total <= 0:
        return None
    return sum(x * w for x, w in valores) / total


def encolhido(itens: Sequence[Item], k: float = K.K_ENCOLHIMENTO) -> float:
    """Σw·d / (Σw + K): o grupo pequeno empresta força do típico da conta (desvio 0)."""
    soma_w = sum(i.peso for i in itens)
    if soma_w + k <= 0:
        return 0.0
    return sum(i.peso * i.desvio for i in itens) / (soma_w + k)


def efeito_entrega(itens: Sequence[Item]) -> float:
    """Diferença de chance de sair da estagnação (fração; ×100 = p.p.)."""
    return encolhido(itens)


def efeito_rendimento(itens: Sequence[Item]) -> float:
    """θ em escala log; exibido como e^θ ("≈ 2,4× o típico da conta")."""
    return encolhido(itens)


def semente(*partes: object) -> int:
    """Semente estável entre processos (o `hash()` do Python muda a cada execução)."""
    bruto = "|".join(str(p) for p in partes).encode()
    return int.from_bytes(hashlib.sha256(bruto).digest()[:8], "big")


def percentil(valores: Sequence[float], q: float) -> float:
    """Percentil com interpolação linear (q em 0..1) de valores já ordenados ou não."""
    ordenados = sorted(valores)
    if not ordenados:
        raise ValueError("sem valores")
    pos = q * (len(ordenados) - 1)
    baixo = math.floor(pos)
    alto = min(baixo + 1, len(ordenados) - 1)
    frac = pos - baixo
    return ordenados[baixo] * (1 - frac) + ordenados[alto] * frac


def reamostrar(grupos: Sequence[Sequence[Item]], estatistica: Callable[..., float],
               sem: int, b: int = K.REAMOSTRAS) -> tuple[float, float]:
    """Reamostra cada grupo com reposição (independentes) e devolve o intervalo de 80% de
    `estatistica(*grupos_reamostrados)`."""
    rng = random.Random(sem)
    valores = []
    for _ in range(b):
        amostras = [rng.choices(g, k=len(g)) if g else [] for g in grupos]
        valores.append(estatistica(*amostras))
    lo, hi = K.PERCENTIS
    return percentil(valores, lo), percentil(valores, hi)


def intervalo(grupo: Sequence[Item], sem: int, b: int = K.REAMOSTRAS) -> tuple[float, float]:
    """Intervalo de 80% do efeito encolhido do grupo (a mesma semente dá o mesmo intervalo).
    O caminho rápido de `reamostrar([grupo], encolhido)`: os mesmos sorteios, sem objetos."""
    if not grupo:
        return 0.0, 0.0
    rng = random.Random(sem)
    n = len(grupo)
    wd = [i.peso * i.desvio for i in grupo]
    w = [i.peso for i in grupo]
    indices = range(n)
    valores = []
    for _ in range(b):
        idx = rng.choices(indices, k=n)
        valores.append(sum(wd[i] for i in idx) / (sum(w[i] for i in idx) + K.K_ENCOLHIMENTO))
    lo, hi = K.PERCENTIS
    return percentil(valores, lo), percentil(valores, hi)


def cruza_zero(iv: tuple[float, float]) -> bool:
    return iv[0] <= 0 <= iv[1]


def confianca(n: int, dias: int, iv: tuple[float, float], efeito: float,
              parte: Parte) -> Confianca:
    """Regra fixa (R2): amostra mínima, depois forte, moderada, fraca e indício."""
    if n < K.MIN_GRUPO or dias < K.MIN_DIAS:
        return "amostra_pequena"
    forte = K.LIMIAR_FORTE_REND if parte == "rendimento" else K.LIMIAR_FORTE_ENTREGA
    fraca = K.LIMIAR_FRACA_REND if parte == "rendimento" else K.LIMIAR_FRACA_ENTREGA
    if not cruza_zero(iv):
        if n >= K.FORTE_N and abs(efeito) >= forte:
            return "forte"
        return "moderada"
    if abs(efeito) >= fraca:
        return "fraca"
    return "indicio"


def faltam(n: int, dias: int) -> int | None:
    """Quantos posts faltam para a amostra mínima (None se já basta). Com posts suficientes num
    dia só, falta 1 (de outro dia)."""
    if n >= K.MIN_GRUPO and dias >= K.MIN_DIAS:
        return None
    return max(K.MIN_GRUPO - n, K.MIN_DIAS - dias, 1)


def concentracao(itens: Sequence[Item]) -> bool:
    """Um post com mais da metade das views do grupo (FR-023)."""
    total = sum(i.views for i in itens)
    if total <= 0 or len(itens) < 2:
        return False
    return max(i.views for i in itens) / total > K.CONCENTRACAO


def sem_maior(itens: Sequence[Item]) -> list[Item]:
    """O grupo sem o post de mais views (o primeiro, no empate)."""
    if not itens:
        return []
    maior = max(range(len(itens)), key=lambda i: (itens[i].views, -i))
    return [it for j, it in enumerate(itens) if j != maior]


def exibir(efeito: float, parte: Parte) -> float:
    """Entrega em p.p.; rendimento como fator multiplicativo (e^θ)."""
    return round(efeito * 100, 1) if parte == "entrega" else round(math.exp(efeito), 2)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)
