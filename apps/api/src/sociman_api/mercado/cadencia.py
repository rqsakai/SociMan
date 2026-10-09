"""Cadência de coleta de um produto (FR-040, FR-040a; data-model "Produto (calor)"). **Puro**: sem
banco e sem relógio; a trilha monta a `Entrada` a partir do ORM e grava a `Saida`.

```text
novo no lago ──▶ quente (fotos_por_dia = 2 se manual ou "novo em alta"; senão 1)
quente ──sem ranking há SAI_DO_RANKING_DIAS e sem interesse manual|vitrine ativo──▶ morna (1/semana)
morna ──sem ranking e sem interesse ativo há ESFRIAR_DIAS──▶ parada (próxima coleta nula)
morna | parada ──reaparece em ranking, ou ganha interesse ativo──▶ quente (no mesmo dia, SC-005)
manual e vitrine ativos: sempre quente
```
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sociman_api.mercado import constantes as k
from sociman_api.mercado.models import Calor


@dataclass(frozen=True)
class Entrada:
    primeira_vez_em: date
    ultima_foto_em: date | None
    fotos_hoje: int  # fotos de página já gravadas hoje (qualquer fonte/turno)
    ultimo_ranking_em: date | None
    ultimo_interesse_em: date | None  # última mudança de qualquer interesse do produto
    manual_ativo: bool
    vitrine_ativa: bool
    outro_interesse_ativo: bool  # ranking, loja, categoria ou vídeo em `ativo`
    novo_em_alta: bool
    ultimas_avaliacoes_em: date | None = None
    ultimos_videos_em: date | None = None


@dataclass(frozen=True)
class Saida:
    calor: Calor
    fotos_por_dia: int
    proxima_coleta: date | None  # dia local da próxima foto de página (nulo = parada)
    coletar_avaliacoes: bool
    coletar_videos: bool
    avaliacoes_paginas: int


def _ultimo_sinal(e: Entrada) -> date:
    candidatos = [e.primeira_vez_em]
    if e.ultimo_ranking_em:
        candidatos.append(e.ultimo_ranking_em)
    if e.ultimo_interesse_em:
        candidatos.append(e.ultimo_interesse_em)
    return max(candidatos)


def calor_de(e: Entrada, hoje: date) -> Calor:
    """FR-040: manual/vitrine sempre quente; interesse ativo ou ranking recente mantém quente;
    7 dias sem sinal → morna; 30 → parada."""
    if e.manual_ativo or e.vitrine_ativa or e.outro_interesse_ativo:
        return Calor.quente
    if e.ultimo_ranking_em and (hoje - e.ultimo_ranking_em).days < k.SAI_DO_RANKING_DIAS:
        return Calor.quente
    dias = (hoje - _ultimo_sinal(e)).days
    if dias >= k.ESFRIAR_DIAS:
        return Calor.parada
    if dias >= k.SAI_DO_RANKING_DIAS:
        return Calor.morna
    return Calor.quente


def fotos_por_dia_de(e: Entrada, calor: Calor) -> int:
    if calor != Calor.quente:
        return 1
    return k.FOTOS_POR_DIA_MAX if (e.manual_ativo or e.novo_em_alta) else 1


def proxima_coleta_de(e: Entrada, calor: Calor, fotos_por_dia: int, hoje: date) -> date | None:
    if calor == Calor.parada:
        return None
    if e.ultima_foto_em is None or e.ultima_foto_em < hoje:
        if calor == Calor.morna and e.ultima_foto_em is not None:
            alvo = e.ultima_foto_em + timedelta(days=k.MORNA_CADA_DIAS)
            return max(alvo, hoje)
        return hoje
    # Já há foto hoje.
    if calor == Calor.quente and fotos_por_dia == k.FOTOS_POR_DIA_MAX and e.fotos_hoje < fotos_por_dia:
        return hoje  # o 2º turno
    passo = k.QUENTE_DIAS if calor == Calor.quente else k.MORNA_CADA_DIAS
    return hoje + timedelta(days=passo)


def precisa_avaliacoes(calor: Calor, ultimas_em: date | None, hoje: date) -> tuple[bool, int]:
    """FR-040a: só em quente; 1ª visita com 2 páginas, depois 1 página a cada 30 dias."""
    if calor != Calor.quente:
        return False, 0
    if ultimas_em is None:
        return True, k.AVALIACOES_PAGINAS_1A_VISITA
    return (hoje - ultimas_em).days >= k.AVALIACOES_CADA_DIAS, 1


def precisa_videos(calor: Calor, ultimos_em: date | None, hoje: date) -> bool:
    if calor != Calor.quente:
        return False
    return ultimos_em is None or (hoje - ultimos_em).days >= k.VIDEOS_CADA_DIAS


def calcular(e: Entrada, hoje: date) -> Saida:
    calor = calor_de(e, hoje)
    fpd = fotos_por_dia_de(e, calor)
    aval, paginas = precisa_avaliacoes(calor, e.ultimas_avaliacoes_em, hoje)
    return Saida(calor=calor, fotos_por_dia=fpd,
                 proxima_coleta=proxima_coleta_de(e, calor, fpd, hoje),
                 coletar_avaliacoes=aval, coletar_videos=precisa_videos(calor, e.ultimos_videos_em, hoje),
                 avaliacoes_paginas=paginas)
