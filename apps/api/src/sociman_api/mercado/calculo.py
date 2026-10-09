"""Cálculo na leitura (FR-042..FR-049): funções **puras**, sem banco e sem relógio.

Todo número derivado sai como `Numero {valor, estimado, motivos, amostraPequena, nFotos, min, max}`.
As constantes vêm de `mercado/constantes.py`. Quem chama (`consulta.py`) traz as fotos de um
produto como `Foto` (uma por dia, turno e fonte) e as datas do filtro; nada aqui escreve.

Regras (data-model, "Regras derivadas"):
- `v(d)` = `vendidos` da última foto com `data_local ≤ d`; o Affiliate Center com `vendas_7d/30d`
  tem precedência quando a janela coincide (motivo `fonte_affiliate`), a página pública é reserva;
- vendas no período = `max(0, v(ate) − v(de − 1))`, negativo → 0 + `inconsistente`;
- vendas/dia exige `MIN_FOTOS_VENDAS` fotos com `MIN_DIAS_ENTRE_FOTOS` dia de distância; menos de
  `AMOSTRA_PEQUENA_DIAS` dias de fotos → `amostraPequena`;
- GMV = Σ Δvendidos × preço mínimo vigente no início do par (`{min, max}` com faixa de preço);
- crescimento = vendas/dia dos últimos 7 d ÷ 7 d anteriores − 1 (base < `MIN_VENDAS_DIA_BASE` → nulo);
- comissão por venda, retorno/dia, retorno por afiliado (÷ criadores + K), saturação, "novo em
  alta", "alto retorno com poucos afiliados" (quartis por categoria ou os limiares globais).
"""

import itertools
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from sociman_api.mercado import constantes as k

Estado = Literal["coletando", "amostra_pequena", "ok"]
Variacao = Literal["subiu", "caiu", "igual", "novo", "entrou", "saiu"]


@dataclass(frozen=True)
class Foto:
    """Uma medição (linha de `mercado_produto_fotos`), já como valores simples."""

    data_local: date
    turno: str
    fonte: str  # pagina_publica | affiliate
    vendidos: int | None = None
    vendidos_min: int | None = None
    vendidos_max: int | None = None
    vendidos_exato: bool | None = None
    preco_min_centavos: int | None = None
    preco_max_centavos: int | None = None
    preco_original_centavos: int | None = None
    comissao_bp: int | None = None
    n_criadores: int | None = None
    vendas_7d: int | None = None
    vendas_30d: int | None = None
    disponivel: bool = True


@dataclass
class Numero:
    valor: float | None
    estimado: bool = True
    motivos: list[str] = field(default_factory=list)
    amostra_pequena: bool = False
    n_fotos: int = 0
    min: float | None = None
    max: float | None = None

    @classmethod
    def nulo(cls, *motivos: str, n_fotos: int = 0) -> "Numero":
        return cls(None, True, list(motivos), False, n_fotos)


# ---- séries ----

def com_vendidos(fotos: list[Foto]) -> list[Foto]:
    """As fotos com `vendidos`, uma por dia (a última do dia; página pública primeiro, porque é a
    série do acumulado), em ordem de data."""
    por_dia: dict[date, Foto] = {}
    for f in sorted(fotos, key=lambda f: (f.data_local, f.turno, f.fonte == "pagina_publica")):
        if f.vendidos is not None:
            por_dia[f.data_local] = f
    return [por_dia[d] for d in sorted(por_dia)]


def v_de(fotos: list[Foto], d: date) -> Foto | None:
    """A última foto com `vendidos` em `data_local ≤ d`."""
    ate = [f for f in com_vendidos(fotos) if f.data_local <= d]
    return ate[-1] if ate else None


def ultima(fotos: list[Foto], ate: date, fonte: str | None = None) -> Foto | None:
    cand = [f for f in fotos if f.data_local <= ate and (fonte is None or f.fonte == fonte)]
    if not cand:
        return None
    return max(cand, key=lambda f: (f.data_local, f.turno))


def preco_de(fotos: list[Foto], d: date) -> Foto | None:
    cand = [f for f in fotos if f.data_local <= d and f.preco_min_centavos is not None]
    return max(cand, key=lambda f: (f.data_local, f.turno)) if cand else None


def estado(fotos: list[Foto], ate: date) -> Estado:
    """`coletando` com menos de duas fotos; `amostra_pequena` com menos de 7 dias de fotos."""
    serie = [f for f in com_vendidos(fotos) if f.data_local <= ate]
    if len(serie) < k.MIN_FOTOS_VENDAS:
        return "coletando"
    if (serie[-1].data_local - serie[0].data_local).days + 1 < k.AMOSTRA_PEQUENA_DIAS:
        return "amostra_pequena"
    return "ok"


def _incerteza(f: Foto | None) -> bool:
    return f is not None and f.vendidos_exato is False


# ---- vendas e GMV ----

def vendas_periodo(fotos: list[Foto], de: date, ate: date) -> Numero:
    """FR-044. Com `vendas_7d`/`vendas_30d` do Affiliate Center na última foto do período e a
    janela coincidindo, esse valor tem precedência."""
    dias = (ate - de).days + 1
    af = ultima(fotos, ate, "affiliate")
    if af is not None and (ate - af.data_local).days <= k.AC_FOTO_MAX_DIAS:
        if dias == 7 and af.vendas_7d is not None:
            return Numero(af.vendas_7d, True, ["fonte_affiliate"], False, 1)
        if dias == 30 and af.vendas_30d is not None:
            return Numero(af.vendas_30d, True, ["fonte_affiliate"], False, 1)
    fim = v_de(fotos, ate)
    ini = v_de(fotos, de - timedelta(days=1))
    serie = [f for f in com_vendidos(fotos) if de <= f.data_local <= ate]
    if fim is None or (ini is None and len(serie) < k.MIN_FOTOS_VENDAS):
        return Numero.nulo("coletando", n_fotos=len(serie))
    base = ini if ini is not None else serie[0]
    motivos = ["fonte_pagina_publica"]
    if ini is None:
        motivos.append("interpolado")  # a base é a 1ª foto do período, não a véspera
    delta = fim.vendidos - base.vendidos
    if delta < 0:
        return Numero(0, True, [*motivos, "inconsistente"], False, len(serie) or 2)
    n = Numero(delta, True, motivos, False, len(serie) or 2)
    if _incerteza(fim) or _incerteza(base):
        n.motivos.append("incerteza")
        n.min = max(0, (fim.vendidos_min or fim.vendidos) - (base.vendidos_max or base.vendidos))
        n.max = ((fim.vendidos_max or fim.vendidos) - (base.vendidos_min or base.vendidos)) \
            if fim.vendidos_max is not None else None
    return n


def vendas_dia(fotos: list[Foto], ate: date, janela: int = k.JANELA_CRESCIMENTO_DIAS) -> Numero:
    """FR-045: a média diária nos `janela` dias que terminam em `ate`. Exige duas fotos com ao
    menos um dia de distância; o Affiliate Center com `vendas_7d` recente tem precedência."""
    af = ultima(fotos, ate, "affiliate")
    if janela == 7 and af is not None and af.vendas_7d is not None \
            and (ate - af.data_local).days <= k.AC_FOTO_MAX_DIAS:
        return Numero(af.vendas_7d / 7, True, ["fonte_affiliate"], False, 1)
    serie = [f for f in com_vendidos(fotos) if ate - timedelta(days=janela) <= f.data_local <= ate]
    if len(serie) < k.MIN_FOTOS_VENDAS:
        return Numero.nulo("coletando", n_fotos=len(serie))
    ini, fim = serie[0], serie[-1]
    dias = (fim.data_local - ini.data_local).days
    if dias < k.MIN_DIAS_ENTRE_FOTOS:
        return Numero.nulo("coletando", n_fotos=len(serie))
    delta = fim.vendidos - ini.vendidos
    motivos = ["fonte_pagina_publica"]
    if delta < 0:
        delta, motivos = 0, [*motivos, "inconsistente"]
    n = Numero(delta / dias, True, motivos, dias + 1 < k.AMOSTRA_PEQUENA_DIAS, len(serie))
    if _incerteza(fim) or _incerteza(ini):
        n.motivos.append("incerteza")
    return n


def gmv_periodo(fotos: list[Foto], de: date, ate: date) -> Numero:
    """FR-045: Σ (Δvendidos entre fotos consecutivas × preço mínimo vigente no início do par), em
    centavos; `{min, max}` quando há faixa de preço por variante."""
    serie = [f for f in com_vendidos(fotos) if de - timedelta(days=1) <= f.data_local <= ate]
    if len(serie) < k.MIN_FOTOS_VENDAS:
        return Numero.nulo("coletando", n_fotos=len(serie))
    total = total_max = 0.0
    faixa = False
    inconsistente = False
    for a, b in itertools.pairwise(serie):
        delta = b.vendidos - a.vendidos
        if delta < 0:
            inconsistente = True
            continue
        preco = preco_de(fotos, a.data_local)
        if preco is None or preco.preco_min_centavos is None:
            continue
        total += delta * preco.preco_min_centavos
        pmax = preco.preco_max_centavos or preco.preco_min_centavos
        if pmax != preco.preco_min_centavos:
            faixa = True
        total_max += delta * pmax
    motivos = ["estimado"]
    if inconsistente:
        motivos.append("inconsistente")
    n = Numero(round(total), True, motivos, False, len(serie))
    if faixa:
        n.motivos.append("incerteza")
        n.min, n.max = round(total), round(total_max)
    return n


def crescimento(fotos: list[Foto], ate: date) -> Numero:
    """FR-046: vendas/dia dos últimos 7 d ÷ 7 d anteriores − 1; base < MIN_VENDAS_DIA_BASE → nulo."""
    atual = vendas_dia(fotos, ate)
    anterior = vendas_dia(fotos, ate - timedelta(days=k.JANELA_CRESCIMENTO_DIAS))
    if atual.valor is None or anterior.valor is None:
        return Numero.nulo("coletando", n_fotos=atual.n_fotos + anterior.n_fotos)
    if anterior.valor < k.MIN_VENDAS_DIA_BASE:
        return Numero.nulo("base_pequena", n_fotos=atual.n_fotos + anterior.n_fotos)
    return Numero(atual.valor / anterior.valor - 1, True, ["estimado"],
                  atual.amostra_pequena or anterior.amostra_pequena,
                  atual.n_fotos + anterior.n_fotos)


def vendas_totais(fotos: list[Foto], ate: date) -> Numero:
    f = v_de(fotos, ate)
    if f is None:
        return Numero.nulo("coletando")
    n = Numero(f.vendidos, True, ["fonte_pagina_publica" if f.fonte == "pagina_publica"
                                  else "fonte_affiliate"], False, 1)
    if _incerteza(f):
        n.motivos.append("incerteza")
        n.min, n.max = f.vendidos_min, f.vendidos_max
    return n


def gmv_total(fotos: list[Foto], ate: date) -> Numero:
    """FR-046: vendas totais × preço atual, marcado `grosseiro`."""
    vt = vendas_totais(fotos, ate)
    preco = preco_de(fotos, ate)
    if vt.valor is None or preco is None or preco.preco_min_centavos is None:
        return Numero.nulo("coletando", n_fotos=vt.n_fotos)
    n = Numero(vt.valor * preco.preco_min_centavos, True, ["grosseiro", *vt.motivos], False,
               vt.n_fotos)
    if vt.min is not None:
        n.min = vt.min * preco.preco_min_centavos
        n.max = vt.max * preco.preco_min_centavos if vt.max is not None else None
    return n


# ---- afiliado ----

def comissao_por_venda(preco_centavos: int | None, comissao_bp: int | None) -> Numero:
    """FR-047: preço × comissão (a rede desconta cupons: `cupons_nao_descontados`)."""
    if comissao_bp is None:
        return Numero.nulo("sem_dado_afiliado")
    if preco_centavos is None:
        return Numero.nulo("coletando")
    return Numero(preco_centavos * comissao_bp / 10000, True, ["cupons_nao_descontados"], False, 1)


def retorno_dia(vendas_por_dia: Numero, comissao_venda: Numero) -> Numero:
    if comissao_venda.valor is None:
        return Numero.nulo(*comissao_venda.motivos)
    if vendas_por_dia.valor is None:
        return Numero.nulo(*vendas_por_dia.motivos)
    return Numero(vendas_por_dia.valor * comissao_venda.valor, True,
                  sorted(set(vendas_por_dia.motivos) | {"cupons_nao_descontados"}),
                  vendas_por_dia.amostra_pequena, vendas_por_dia.n_fotos)


def retorno_por_afiliado(retorno: Numero, n_criadores: int | None) -> Numero:
    """FR-047: retorno/dia ÷ (criadores + K_AFILIADOS)."""
    if n_criadores is None:
        return Numero.nulo("sem_dado_afiliado")
    if retorno.valor is None:
        return Numero.nulo(*retorno.motivos)
    return Numero(retorno.valor / (n_criadores + k.K_AFILIADOS), True, list(retorno.motivos),
                  retorno.amostra_pequena, retorno.n_fotos)


def saturacao(n_criadores: int | None, vendas_por_dia: Numero) -> Numero:
    """FR-047: criadores por venda/dia."""
    if n_criadores is None:
        return Numero.nulo("sem_dado_afiliado")
    if vendas_por_dia.valor is None:
        return Numero.nulo(*vendas_por_dia.motivos)
    if vendas_por_dia.valor <= 0:
        return Numero.nulo("sem_vendas")
    return Numero(n_criadores / vendas_por_dia.valor, True, list(vendas_por_dia.motivos),
                  vendas_por_dia.amostra_pequena, vendas_por_dia.n_fotos)


def percentil(valores: list[float], p: int) -> float | None:
    """Percentil por interpolação linear (p em 0..100); None sem valores."""
    if not valores:
        return None
    v = sorted(valores)
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * p / 100
    i = math.floor(pos)
    frac = pos - i
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * frac


@dataclass(frozen=True)
class Comparaveis:
    """Os quartis da categoria (FR-047): None quando a amostra é menor que MIN_PRODUTOS_CATEGORIA."""

    p25_criadores: float | None
    p75_retorno: float | None
    mediana_retorno_global: float | None
    n: int

    @property
    def por_categoria(self) -> bool:
        return self.n >= k.MIN_PRODUTOS_CATEGORIA and self.p25_criadores is not None \
            and self.p75_retorno is not None


def alto_retorno_poucos_afiliados(comissao_bp: int | None, dias_foto_affiliate: int | None,
                                  n_criadores: int | None, retorno_afiliado: Numero,
                                  comparaveis: Comparaveis | None) -> tuple[bool, bool]:
    """FR-047 → `(alto_retorno_poucos_afiliados, poucos_afiliados)`. Com categoria comparável
    (≥ MIN_PRODUTOS_CATEGORIA), criadores ≤ P25 e retorno ≥ P75; sem amostra, criadores ≤
    POUCOS_AFILIADOS e retorno ≥ mediana global (ou > 0 sem mediana)."""
    poucos = n_criadores is not None and n_criadores <= k.POUCOS_AFILIADOS
    if comissao_bp is None or comissao_bp < k.COMISSAO_MIN_BP or n_criadores is None:
        return False, poucos
    if dias_foto_affiliate is None or dias_foto_affiliate > k.AC_FOTO_MAX_DIAS:
        return False, poucos
    if retorno_afiliado.valor is None or retorno_afiliado.valor <= 0:
        return False, poucos
    if comparaveis is not None and comparaveis.por_categoria:
        return (n_criadores <= comparaveis.p25_criadores
                and retorno_afiliado.valor >= comparaveis.p75_retorno), poucos
    mediana = comparaveis.mediana_retorno_global if comparaveis else None
    return poucos and (mediana is None or retorno_afiliado.valor >= mediana), poucos


def novo_em_alta(primeira_vez_em: date, hoje: date, vendas_por_dia: Numero, cresc: Numero,
                 em_ranking_alta_7d: bool, subiu_posicoes_7d: int | None, est: Estado) -> bool:
    """FR-048."""
    if est != "ok" or vendas_por_dia.valor is None:
        return False
    if (hoje - primeira_vez_em).days > k.NOVO_DIAS:
        return False
    if vendas_por_dia.valor < k.NOVO_VENDAS_DIA_MIN:
        return False
    subiu = subiu_posicoes_7d is not None and subiu_posicoes_7d >= k.ALTA_POSICOES
    cresceu = cresc.valor is not None and cresc.valor >= k.NOVO_CRESCIMENTO_MIN
    return cresceu or em_ranking_alta_7d or subiu


# ---- ranking, loja e categoria ----

def variacao_posicao(atual: int | None, anterior: int | None) -> tuple[Variacao, int | None]:
    """FR-049: a variação entre duas fotos do mesmo ranking."""
    if atual is None and anterior is None:
        return "igual", None
    if anterior is None:
        return "novo", None
    if atual is None:
        return "saiu", None
    if atual < anterior:
        return "subiu", anterior - atual
    if atual > anterior:
        return "caiu", anterior - atual
    return "igual", 0


@dataclass(frozen=True)
class ResumoRanking:
    posicao_atual: int | None
    melhor_posicao: int | None
    dias_no_topo: int
    variacao_7d: int | None
    entrou_em: date | None
    saiu_em: date | None


def resumo_ranking(posicoes: dict[date, int], ate: date) -> ResumoRanking:
    """`posicoes` = dia → posição do produto num ranking; dias sem o produto não aparecem."""
    if not posicoes:
        return ResumoRanking(None, None, 0, None, None, None)
    dias = sorted(d for d in posicoes if d <= ate)
    if not dias:
        return ResumoRanking(None, None, 0, None, None, None)
    atual = posicoes[dias[-1]] if dias[-1] == ate else None
    ha7 = [d for d in dias if d <= ate - timedelta(days=7)]
    var = (posicoes[ha7[-1]] - atual) if (atual is not None and ha7) else None
    saiu = None if atual is not None else dias[-1] + timedelta(days=1)
    return ResumoRanking(atual, min(posicoes[d] for d in dias),
                         sum(1 for d in dias if posicoes[d] <= k.RANKING_DIAS_NO_TOPO), var,
                         dias[0], saiu)


@dataclass(frozen=True)
class IndicadoresLoja:
    gmv_estimado_centavos: Numero
    concentracao_top1: Numero
    lancamentos_30d: int
    comissao_media_bp: Numero


def indicadores_loja(gmvs: list[Numero], primeiras_vezes: list[date], hoje: date,
                     comissoes_bp: list[int]) -> IndicadoresLoja:
    """FR-049 por loja, a partir dos GMVs dos produtos acompanhados."""
    valores = [g.valor for g in gmvs if g.valor is not None]
    total = sum(valores)
    gmv = Numero(round(total), True, ["estimado"], len(valores) < k.MIN_FOTOS_VENDAS, len(valores)) \
        if valores else Numero.nulo("coletando")
    conc = Numero(max(valores) / total, True, ["estimado"], False, len(valores)) \
        if valores and total > 0 else Numero.nulo("sem_vendas")
    lanc = sum(1 for d in primeiras_vezes if (hoje - d).days <= k.LANCAMENTOS_DIAS)
    com = Numero(sum(comissoes_bp) / len(comissoes_bp), True, ["estimado"], False,
                 len(comissoes_bp)) if comissoes_bp else Numero.nulo("sem_dado_afiliado")
    return IndicadoresLoja(gmv, conc, lanc, com)


@dataclass(frozen=True)
class IndicadoresCategoria:
    mediana_comissao_bp: Numero
    mediana_preco_centavos: Numero
    n_novos_em_alta: int
    espaco_em_branco: bool


def indicadores_categoria(comissoes_bp: list[int], precos: list[int], n_novos_em_alta: int,
                          vendas_crescendo: bool, criadores: list[int],
                          p25_criadores_global: float | None) -> IndicadoresCategoria | None:
    """FR-049 por categoria; None com menos de MIN_PRODUTOS_CATEGORIA produtos."""
    n = max(len(precos), len(comissoes_bp))
    if n < k.MIN_PRODUTOS_CATEGORIA:
        return None
    med_c = percentil([float(c) for c in comissoes_bp], 50)
    med_p = percentil([float(p) for p in precos], 50)
    med_cr = percentil([float(c) for c in criadores], 50)
    branco = (vendas_crescendo and med_cr is not None and p25_criadores_global is not None
              and med_cr <= p25_criadores_global)
    return IndicadoresCategoria(
        Numero(med_c, True, ["estimado"], False, len(comissoes_bp)) if med_c is not None
        else Numero.nulo("sem_dado_afiliado"),
        Numero(med_p, True, ["estimado"], False, len(precos)) if med_p is not None
        else Numero.nulo("coletando"),
        n_novos_em_alta, branco)
