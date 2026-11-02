"""Durações das posições a partir da narração e quadros por motor (research R4, R5 e R6): funções
puras, sem banco.

`limites` é o porte do `continuous_bounds` do pipeline (`run_storyboard.py`): cada posição vai do
início da sua 1ª frase (menos `LEAD`) até o início da próxima; a 1ª começa em 0 e a última termina
`TAIL` depois do fim da fala. Os tempos já chegam divididos pela velocidade (`na_velocidade`).

`quadros` arredonda **para cima**, com `FOLGA` de 0,1 s e o teto do motor (o `frames_for` do
`run_storyboard.py` arredonda o Wan e o LTX para baixo: esse erro não foi portado).

Vídeo guiado (spec 031, R4): as posições têm duração fixa (trechos × base) e a fala é que se
ajusta. `fala_por_slot` corta a narração contínua em um bloco por posição, pelos tempos das
frases, e põe cada bloco no início do seu slot (+ `ATRASO_FALA`), com `atempo` próprio quando
passa do slot (até a velocidade total `VELOCIDADE_MAX`); acima disso, o aviso `fala_nao_cabe`.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

LEAD = 0.08
TAIL = 0.45
MINIMO_S = 1.0
FOLGA = 0.1

# fps, passo e resto da regra de quadros (passo·k + resto) e duração máxima do clipe (provisória,
# calibrada no quickstart §3; `cenas.duracao_max_s` nulo usa esta).
FPS = {"minimax": 24, "wan": 16, "wan_qualidade": 16, "ltx": 24}
_REGRA = {"minimax": (17, 5), "wan": (4, 1), "wan_qualidade": (4, 1), "ltx": (8, 1)}
DURACAO_MAX_S = {"minimax": 8.0, "wan": 5.0, "wan_qualidade": 7.0, "ltx": 5.0}


class TemposInvalidos(ValueError):
    """As posições não cobrem as frases da narração em ordem e sem buracos."""


@dataclass(frozen=True)
class Limite:
    inicio_s: float
    duracao_s: float


def na_velocidade(sentencas: Iterable[dict[str, Any]], segundos: float, velocidade: float
                  ) -> tuple[list[dict[str, Any]], float]:
    """Os tempos do `/v2/tts_paragraph` (`sentences: [{index, start, end}]` e `seconds`) depois
    do `atempo`: `[{frase, inicio_s, fim_s}]` e o total, divididos pela velocidade (R5)."""
    if velocidade <= 0:
        raise ValueError("velocidade deve ser positiva")
    # 6 casas, e não 3: arredondar aqui muda a 3ª casa das durações (6,722 viraria 6,723).
    tempos = [{"frase": int(s["index"]), "inicio_s": round(float(s["start"]) / velocidade, 6),
               "fim_s": round(float(s["end"]) / velocidade, 6)} for s in sentencas]
    return tempos, round(float(segundos) / velocidade, 6)


def validar_posicoes(posicoes: Sequence[Sequence[int]], frases: Sequence[int]) -> None:
    """Cada posição cobre frases contíguas, toda frase está em exatamente uma posição e a ordem
    das posições segue a das frases (R6)."""
    if not posicoes:
        raise TemposInvalidos("o roteiro não tem posições")
    for i, pos in enumerate(posicoes):
        if not pos:
            raise TemposInvalidos(f"a posição {i} não tem frases")
    if [f for pos in posicoes for f in pos] != list(frases):
        raise TemposInvalidos("as posições precisam cobrir todas as frases, em ordem e sem "
                              "repetir")


def limites(tempos: Sequence[dict[str, Any]], posicoes: Sequence[Sequence[int]],
            total_s: float) -> list[Limite]:
    """Início e duração (3 casas) de cada posição. `tempos` são os da narração na velocidade
    final (`[{frase, inicio_s, fim_s}]`, em ordem); `posicoes` lista, por posição, os ids de
    `frase` que ela cobre."""
    ordem = [int(t["frase"]) for t in tempos]
    validar_posicoes(posicoes, ordem)
    inicio_frase = {int(t["frase"]): float(t["inicio_s"]) for t in tempos}
    inicios = [0.0] + [inicio_frase[pos[0]] - LEAD for pos in posicoes[1:]]
    fins = inicios[1:] + [float(total_s) + TAIL]
    return [Limite(round(a, 3), round(max(MINIMO_S, b - a), 3)) for a, b in zip(inicios, fins,
                                                                                 strict=True)]


def _quadros_brutos(motor: str, duracao_s: float) -> int:
    passo, resto = _REGRA[motor]
    # round(…, 6) tira o ruído do float antes do teto (3,0·24 − 5 não pode virar 67,0000001).
    k = math.ceil(round((duracao_s * FPS[motor] - resto) / passo, 6))
    return passo * max(k, 0) + resto


def teto_quadros(motor: str) -> int:
    """Os quadros da duração máxima do motor (minimax 192, wan 81, wan_qualidade 113, ltx 121)."""
    return _quadros_brutos(motor, DURACAO_MAX_S[motor])


def quadros(motor: str, duracao_s: float) -> int:
    """Quadros do clipe para cobrir `duracao_s` (+ `FOLGA`), na regra do motor e sem passar do
    teto: MiniMax 17k+5 e LTX 8k+1 a 24 fps, Wan 4k+1 a 16 fps."""
    if motor not in _REGRA:
        raise ValueError(f"motor desconhecido: {motor}")
    return min(_quadros_brutos(motor, duracao_s + FOLGA), teto_quadros(motor))


def duracao_clipe_s(motor: str, n_quadros: int) -> float:
    """Duração (3 casas) de um clipe de `n_quadros` no fps do motor."""
    return round(n_quadros / FPS[motor], 3)


# ---- vídeo guiado: fala por slot (spec 031, R4) ----

ATRASO_FALA = 0.15  # a fala entra 0,15 s depois do início do slot
MARGEM_FIM = 0.3  # e termina pelo menos 0,3 s antes do fim
VELOCIDADE_MAX = 1.20  # o teto da 011 (`ck_roteiros_velocidade`)
PAD_CORTE = 0.05  # respiro em volta da fala no corte (sem invadir o bloco vizinho)


@dataclass(frozen=True)
class BlocoFala:
    """O bloco de fala de uma posição. `inicio_s`/`fim_s` são o corte na narração (já na
    velocidade do roteiro); `atempo` é o ajuste a mais deste bloco (1 = nenhum); `atraso_s` é o
    `adelay` (início do slot + `ATRASO_FALA`); `max_s` é o que cabe até o fim do slot (só corta
    algo quando o bloco tem o aviso `fala_nao_cabe`); `indice` é a posição na lista (o slot).
    """
    indice: int
    ordem: int
    inicio_s: float
    fim_s: float
    atempo: float
    atraso_s: float
    max_s: float


def fala_por_slot(tempos: Sequence[dict[str, Any]], posicoes: Sequence[Sequence[int]],
                  duracoes_s: Sequence[float], velocidade: float, *,
                  ordens: Sequence[int] | None = None
                  ) -> tuple[list[BlocoFala], list[dict[str, Any]]]:
    """Os blocos de fala e os avisos de um roteiro guiado.

    - `tempos`: os da narração na velocidade do roteiro (`na_velocidade`), em ordem;
    - `posicoes`: por posição, os ids de `frase` (contíguos; uma posição pode ficar sem fala);
    - `duracoes_s`: a duração fixa de cada posição (trechos × base);
    - `velocidade`: a do roteiro (a narração já está nela): o `atempo` do bloco vai até
      `VELOCIDADE_MAX / velocidade`;
    - `ordens`: a `ordem` de cada posição para o aviso (padrão: 0, 1, 2…).

    Os avisos saem no formato de `roteiros.avisos` (`{code, message, ordem}`), para o chamador
    gravar (`maquina.avisar`)."""
    if velocidade <= 0:
        raise ValueError("velocidade deve ser positiva")
    if len(duracoes_s) != len(posicoes):
        raise TemposInvalidos("uma duração por posição")
    ordens = list(range(len(posicoes))) if ordens is None else list(ordens)
    if len(ordens) != len(posicoes):
        raise TemposInvalidos("uma ordem por posição")
    if [f for pos in posicoes for f in pos] != [int(t["frase"]) for t in tempos]:
        raise TemposInvalidos("as posições precisam cobrir todas as frases, em ordem e sem "
                              "repetir")
    por_frase = {int(t["frase"]): t for t in tempos}
    falas = [(i, float(por_frase[pos[0]]["inicio_s"]), float(por_frase[pos[-1]]["fim_s"]))
             for i, pos in enumerate(posicoes) if pos]
    extra_max = VELOCIDADE_MAX / velocidade
    blocos: list[BlocoFala] = []
    avisos: list[dict[str, Any]] = []
    for k, (i, ini, fim) in enumerate(falas):
        # O corte não invade o vizinho: no máximo até o meio do silêncio entre as duas falas.
        antes = (falas[k - 1][2] + ini) / 2 if k else 0.0
        depois = (fim + falas[k + 1][1]) / 2 if k + 1 < len(falas) else math.inf
        corte_ini, corte_fim = max(antes, ini - PAD_CORTE, 0.0), min(depois, fim + PAD_CORTE)
        inicio_slot = sum(duracoes_s[:i])
        cabe_s = duracoes_s[i] - ATRASO_FALA - MARGEM_FIM
        fala_s = corte_fim - corte_ini
        precisa = fala_s / cabe_s if cabe_s > 0 else math.inf
        if precisa <= 1:
            atempo = 1.0
        elif precisa <= extra_max:
            # Para cima, na 3ª casa: arredondar para baixo deixaria a fala 1 ms além da margem.
            atempo = min(math.ceil(round(precisa, 6) * 1000) / 1000, extra_max)
        else:
            atempo = math.floor(extra_max * 1000) / 1000
            avisos.append({"code": "fala_nao_cabe",
                           "message": (f"A fala da cena {ordens[i] + 1} não cabe em "
                                       f"{duracoes_s[i]:g} s nem a {VELOCIDADE_MAX:.2f}×"
                                       ).replace(".", ","),
                           "ordem": ordens[i]})
        blocos.append(BlocoFala(indice=i, ordem=ordens[i], inicio_s=round(corte_ini, 3),
                                fim_s=round(corte_fim, 3), atempo=atempo,
                                atraso_s=round(inicio_slot + ATRASO_FALA, 3),
                                max_s=round(max(duracoes_s[i] - ATRASO_FALA, 0.0), 3)))
    return blocos, avisos
