"""Pontuação de recomendação dos vídeos (research R3). Funções puras, sem banco.

`100 × (0,45·V + 0,20·E + 0,15·R + 0,20·D)`, com uma casa decimal, relativa ao próprio canal:
- V (velocidade): `r = vph / mediana do canal`, `V = min(1, ln(1 + r) / ln(9))` (1 com 8×);
- E (engajamento): `(likes + 3 × comentários) / views` contra a mediana do canal (1 com 4×);
- R (recência): `exp(−dias / 30)`;
- D (duração): tabela `_duracao`.
Zeram e saem da recomendação: indisponível, ao vivo ou agendado, mais de 3 h, menos de 45 s.
O direito do canal **não** entra na conta (princípio II é informativo), e o fator "já cortado"
(× 0,3) é por perfil, aplicado na consulta da descoberta.
"""

import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sociman_api.canais.models import VideoLive

# Pesos num só lugar (fáceis de ajustar depois com dados).
PESOS = {"v": 0.45, "e": 0.20, "r": 0.15, "d": 0.20}
V_TETO = 8.0  # V = 1 com 8× a mediana
E_TETO = 4.0  # E = 1 com 4× a mediana
RECENCIA_DIAS = 30.0
MIN_S = 45  # o OpenShorts recusa menos que isso
MAX_S = 3 * 3600
FATOR_JA_CORTADO = Decimal("0.3")
AMOSTRA_CANAL = 50  # mediana dos 50 vídeos mais recentes do canal


@dataclass(frozen=True)
class Entrada:
    views: int | None
    likes: int | None
    comments: int | None
    published_at: datetime
    duration_s: int | None
    live: VideoLive
    disponivel: bool
    vph_recente: float | None


@dataclass(frozen=True)
class Resultado:
    score: Decimal
    reason: str
    detail: dict[str, Any]
    recomendavel: bool


def _horas(entrada: Entrada, agora: datetime) -> float:
    return max((agora - entrada.published_at).total_seconds() / 3600, 1 / 60)


def vph(entrada: Entrada, agora: datetime) -> float | None:
    """`vph_recente` ou, sem duas leituras com 6 h de distância, views / horas publicadas."""
    if entrada.vph_recente is not None:
        return max(entrada.vph_recente, 0.0)
    if entrada.views is None:
        return None
    return entrada.views / _horas(entrada, agora)


def engajamento(entrada: Entrada) -> float | None:
    """Likes ocultos contam 0; sem views conhecidas não há engajamento."""
    if entrada.views is None:
        return None
    return ((entrada.likes or 0) + 3 * (entrada.comments or 0)) / max(entrada.views, 1)


def mediana(valores: list[float | None]) -> float | None:
    vals = [v for v in valores if v is not None]
    return statistics.median(vals) if vals else None


def _relativo(valor: float | None, med: float | None) -> float:
    if valor is None or valor <= 0:
        return 0.0
    if not med or med <= 0:
        return 1.0  # sem referência no canal: conta como "na média"
    return valor / med


def _componente_log(r: float, teto: float) -> float:
    return min(1.0, math.log1p(r) / math.log1p(teto))


def _duracao(segundos: int | None) -> float:
    if segundos is None or segundos < 180 or segundos > MAX_S:
        return 0.0
    if segundos < 480:
        return 0.6
    if segundos <= 3600:
        return 1.0
    return 0.7


# ---- textos em pt-BR ----

def _num(valor: float, casas: int = 1) -> str:
    texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".") if casas else f"{valor:.0f}"
    return texto.replace(".", ",")


def formatar_contagem(valor: float) -> str:
    """12 → "12"; 12.345 → "12 mil"; 1.234 → "1,2 mil"; 3.100.000 → "3,1 mi"."""
    if valor >= 1_000_000:
        return f"{_num(valor / 1_000_000, 1)} mi"
    if valor >= 10_000:
        return f"{_num(valor / 1000, 0)} mil"
    if valor >= 1000:
        return f"{_num(valor / 1000, 1)} mil"
    return _num(valor, 0 if valor >= 10 else 1)


def formatar_duracao(segundos: int) -> str:
    minutos = round(segundos / 60)
    if minutos < 60:
        return f"{max(minutos, 1)} min"
    h, m = divmod(minutos, 60)
    return f"{h} h {m} min" if m else f"{h} h"


def _idade(horas: float) -> str:
    if horas < 1:
        return "há menos de 1 h"
    if horas < 48:
        return f"há {int(horas)} h"
    return f"há {int(horas // 24)} dias"


def _aviso(entrada: Entrada) -> str | None:
    if not entrada.disponivel:
        return "Indisponível no YouTube (removido ou privado)"
    if entrada.live == VideoLive.ao_vivo:
        return "Ao vivo agora: não recomendado"
    if entrada.live == VideoLive.agendado:
        return "Transmissão agendada: não recomendado"
    if entrada.duration_s is not None and entrada.duration_s > MAX_S:
        return "Longo demais (> 3 h)"
    if entrada.duration_s is not None and entrada.duration_s < MIN_S:
        return "Curto demais (Shorts)"
    return None


def _arredonda(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def calcular(entrada: Entrada, mediana_vph: float | None, mediana_eng: float | None,
             agora: datetime) -> Resultado:
    horas = _horas(entrada, agora)
    velocidade = vph(entrada, agora)
    eng = engajamento(entrada)
    r_v = _relativo(velocidade, mediana_vph)
    r_e = _relativo(eng, mediana_eng)
    comp = {
        "v": _componente_log(r_v, V_TETO),
        "e": _componente_log(r_e, E_TETO),
        "r": math.exp(-(horas / 24) / RECENCIA_DIAS),
        "d": _duracao(entrada.duration_s),
    }
    valores = {
        "vph": round(velocidade, 2) if velocidade is not None else None,
        "medianaVph": round(mediana_vph, 2) if mediana_vph is not None else None,
        "rV": round(r_v, 2),
        "engajamento": round(eng, 5) if eng is not None else None,
        "medianaEngajamento": round(mediana_eng, 5) if mediana_eng is not None else None,
        "rE": round(r_e, 2),
        "horas": round(horas, 1),
        "duracaoS": entrada.duration_s,
    }
    detail: dict[str, Any] = {k: round(v, 3) for k, v in comp.items()}
    detail["valores"] = valores

    aviso = _aviso(entrada)
    if aviso is not None:
        detail["componente"] = "aviso"
        return Resultado(score=Decimal("0.0"), reason=aviso, detail=detail, recomendavel=False)

    contrib = {k: PESOS[k] * v for k, v in comp.items()}
    total = 100 * sum(contrib.values())
    principal = max(contrib, key=lambda k: (contrib[k], -list(PESOS).index(k)))
    detail["componente"] = principal
    return Resultado(score=min(_arredonda(total), Decimal("100.0")),
                     reason=_motivo(principal, velocidade, r_v, r_e, horas, entrada),
                     detail=detail, recomendavel=True)


def _motivo(principal: str, velocidade: float | None, r_v: float, r_e: float, horas: float,
            entrada: Entrada) -> str:
    if principal == "v" and velocidade is not None:
        return (f"{formatar_contagem(velocidade)} views/h recentes "
                f"({_num(r_v)}× a média do canal)")
    if principal == "e":
        return f"Engajamento alto: {_num(r_e)}× o do canal"
    if principal == "r":
        return f"Novo: publicado {_idade(horas)}"
    if entrada.duration_s is not None:
        return f"Duração boa para cortes ({formatar_duracao(entrada.duration_s)})"
    return f"Publicado {_idade(horas)}"


def score_exibido(score: Decimal, ja_cortado: bool) -> Decimal:
    """O score da descoberta para um perfil: × 0,3 quando o vídeo já foi cortado para ele."""
    if not ja_cortado:
        return score
    return (score * FATOR_JA_CORTADO).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
