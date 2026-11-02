"""Grade de duração do vídeo guiado (spec 031, research R1 e R4): funções puras, sem banco.

- a duração do vídeo é um múltiplo do trecho-base (`base`), de 1× a `maximo`×;
- cada posição ocupa de 1 a `MAX_TRECHOS` trechos (com `trechos + 1` quadros: 2 a 4);
- a fala de uma posição tem um orçamento de caracteres: `floor(0,85 × duração × 14)`, com
  ~14 caracteres por segundo em pt-BR a 1,08× (medido nas narrações da 011, `bia_vo`).

O roteiro guarda a base com que nasceu (`trecho_base_s`): estas funções recebem a base e o
máximo como argumentos, e não leem o `.env`.
"""

import math
from collections.abc import Iterable

MAX_TRECHOS = 3
CHARS_POR_S = 14
FRACAO_FALA = 0.85
PAPEIS = {2: ("inicio", "fim"), 3: ("inicio", "meio1", "fim"),
          4: ("inicio", "meio1", "meio2", "fim")}


class GradeInvalida(ValueError):
    """Base, máximo ou número de quadros fora do que a grade aceita."""


def _conferir(base: int, maximo: int) -> None:
    if base <= 0 or maximo <= 0:
        raise GradeInvalida("a base e o máximo da grade devem ser positivos")


def opcoes(base: int, maximo: int) -> list[int]:
    """As durações oferecidas, em segundos, do menor ao maior (base 5, máximo 6 → 5 a 30)."""
    _conferir(base, maximo)
    return [base * k for k in range(1, maximo + 1)]


def valida_duracao(duracao_s: int, base: int, maximo: int) -> bool:
    """`duracao_s` é uma das opções da grade (múltiplo da base, de 1× a `maximo`×)."""
    return duracao_s in opcoes(base, maximo)


def orcamento_chars(duracao_s: float) -> int:
    """Os caracteres de fala que cabem numa posição de `duracao_s` (5 s → 59; 15 s → 178)."""
    if duracao_s <= 0:
        return 0
    # round(…, 6) tira o ruído do float antes do piso (0,85 × 10 × 14 não pode virar 118,99…).
    return math.floor(round(FRACAO_FALA * duracao_s * CHARS_POR_S, 6))


def duracao_posicao(trechos: int, base: int) -> int:
    """A duração fixa de uma posição de `trechos` trechos (1 a `MAX_TRECHOS`)."""
    if not 1 <= trechos <= MAX_TRECHOS:
        raise GradeInvalida(f"uma posição tem de 1 a {MAX_TRECHOS} trechos")
    return trechos * base


def soma_fecha(duracoes: Iterable[float], alvo: float) -> bool:
    """A soma das durações das posições é exatamente a duração-alvo do vídeo."""
    return round(sum(duracoes), 3) == round(alvo, 3)


def papeis(n_quadros: int) -> list[str]:
    """O papel de cada quadro de uma posição: 2 → início e fim; 3 e 4 ganham os meios."""
    if n_quadros not in PAPEIS:
        raise GradeInvalida(f"uma posição tem de 2 a {MAX_TRECHOS + 1} quadros")
    return list(PAPEIS[n_quadros])
