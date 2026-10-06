"""Insights determinísticos da visão geral (spec 019, research R6; FR-015). Regras puras sobre os
posts já medidos; nenhuma chama IA nem grava.

Cada regra compara a mediana da medida de um grupo (faixa de 3 h, dia da semana, faixa de
duração, canal-fonte, hashtag) com a mediana geral. Só vira insight quando o vencedor e o geral
têm `MIN_GRUPO` posts e a razão é ≥ 1,3×; senão, o cartão fica `pendente`, dizendo quantos posts
faltam (ou que nenhum grupo se destacou). "Destaque": o vídeo com a medida acima de 3× a mediana.
Posts aguardando o marco (ou sem dado) ficam fora de todas as regras.
"""

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

from sociman_api.analytics import schemas
from sociman_api.analytics.base import PostAnalisado, amostra
from sociman_api.analytics.estatistica import MIN_GRUPO, mediana

RAZAO_MINIMA = 1.3
DESTAQUE_ACIMA = 3.0
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
MEDIDAS = {"h1": "em 1 h", "h24": "em 24 h", "d7": "em 7 dias"}


def vezes(razao: float) -> str:
    """2.345 → "2,3×"."""
    return f"{razao:.1f}".replace(".", ",") + "×"


def faltam_posts(k: int) -> str:
    return "falta 1 post" if k == 1 else f"faltam {k} posts"


def faixa_horario(hora: int) -> str:
    ini = hora - hora % 3
    return f"{ini}h–{ini + 3}h"


def _no_dia(dia: str) -> str:
    return f"no {dia}" if dia in ("sábado", "domingo") else f"na {dia}"


def faixa_duracao(segundos: int) -> str:
    if segundos <= 30:
        return "até 30 s"
    return "31–60 s" if segundos <= 60 else "mais de 60 s"


@dataclass(frozen=True)
class _Grupo:
    rotulo: str
    n: int
    mediana: float


def _grupos(posts: Sequence[PostAnalisado],
            chaves: Callable[[PostAnalisado], Sequence[tuple[Hashable, str]]]) -> list[_Grupo]:
    valores: dict[Hashable, list[float]] = {}
    rotulos: dict[Hashable, str] = {}
    for p in posts:
        for chave, rotulo in chaves(p):
            valores.setdefault(chave, []).append(p.medida.valor)  # type: ignore[arg-type]
            rotulos[chave] = rotulo
    return [_Grupo(rotulos[k], len(v), mediana(v)) for k, v in valores.items()]  # type: ignore[arg-type]


def _melhor(regra: str, grupos: list[_Grupo], geral: float | None, n_geral: int,
            frase: Callable[[_Grupo, float], str], o_que: str) -> schemas.Insight:
    """O grupo com a maior mediana entre os que têm `MIN_GRUPO` posts, comparado ao geral."""
    validos = [g for g in grupos if g.n >= MIN_GRUPO]
    if n_geral < MIN_GRUPO or not validos:
        # o que falta: no geral, ou no grupo mais perto do mínimo
        alvo = max((g.n for g in grupos), default=0) if n_geral >= MIN_GRUPO else n_geral
        faltam = MIN_GRUPO - alvo
        return schemas.Insight(
            regra=regra, frase=f"Amostra pequena: {faltam_posts(faltam)} {o_que} para comparar.",
            valor=None, grupo=None, amostra=amostra(alvo, MIN_GRUPO), pendente=True)
    vencedor = max(validos, key=lambda g: (g.mediana, g.n))
    razao = vencedor.mediana / geral if geral else None
    if razao is None or razao < RAZAO_MINIMA:
        texto = f"Nenhum grupo se destacou: o melhor ({vencedor.rotulo}) teve " \
            f"{vezes(razao)} a mediana." if razao is not None else \
            "Sem base de comparação: a mediana geral é zero."
        return schemas.Insight(regra=regra, frase=texto, valor=razao, grupo=vencedor.rotulo,
                               amostra=amostra(vencedor.n, MIN_GRUPO), pendente=True)
    return schemas.Insight(regra=regra, frase=frase(vencedor, razao), valor=razao,
                           grupo=vencedor.rotulo, amostra=amostra(vencedor.n, MIN_GRUPO),
                           pendente=False)


def regras(posts: Sequence[PostAnalisado], medida: str = "h24") -> list[schemas.Insight]:
    """As 6 regras, na ordem: horário, dia, duração, canal, hashtag, destaque."""
    medidos = [p for p in posts if p.medido]
    geral = mediana([p.medida.valor for p in medidos])  # type: ignore[misc]
    n = len(medidos)
    views = f"a mediana de views {MEDIDAS.get(medida, '')}".rstrip()
    canais = [p for p in medidos if p.canal_fonte is not None]
    return [
        _melhor("horario", _grupos(medidos, lambda p: [(p.hora_local // 3,
                                                         faixa_horario(p.hora_local))]),
                geral, n, lambda g, r: f"Posts publicados entre {g.rotulo.replace('–', ' e ')} "
                f"tiveram {vezes(r)} {views}.", "num mesmo horário"),
        _melhor("dia", _grupos(medidos, lambda p: [(p.dia_semana, DIAS[p.dia_semana])]),
                geral, n, lambda g, r: f"Posts publicados {_no_dia(g.rotulo)} tiveram "
                f"{vezes(r)} {views}.",
                "num mesmo dia da semana"),
        _melhor("duracao", _grupos(medidos, lambda p: [(faixa_duracao(p.duracao_s),
                                                         faixa_duracao(p.duracao_s))]),
                geral, n, lambda g, r: f"Vídeos de {g.rotulo} tiveram {vezes(r)} {views}.",
                "numa mesma faixa de duração"),
        _melhor("canal", _grupos(canais, lambda p: [(p.canal_fonte.id,  # type: ignore[union-attr]
                                                      p.canal_fonte.titulo)]),  # type: ignore[union-attr]
                geral, n, lambda g, r: f"Cortes do canal {g.rotulo} tiveram {vezes(r)} {views}.",
                "de um mesmo canal-fonte"),
        _melhor("hashtag", _grupos(medidos, lambda p: [(h, f"#{h}") for h in p.hashtags]),
                geral, n, lambda g, r: f"Posts com {g.rotulo} tiveram {vezes(r)} {views}.",
                "com uma mesma hashtag"),
        destaque(medidos, geral, views),
    ]


def destaque(medidos: Sequence[PostAnalisado], geral: float | None,
             views: str) -> schemas.Insight:
    n = len(medidos)
    if n < MIN_GRUPO:
        return schemas.Insight(
            regra="destaque", frase=f"Amostra pequena: {faltam_posts(MIN_GRUPO - n)} medidos "
            "para apontar destaques.", valor=None, grupo=None, amostra=amostra(n, MIN_GRUPO),
            pendente=True)
    acima = [p for p in medidos if geral and p.medida.valor > DESTAQUE_ACIMA * geral]  # type: ignore[operator]
    if not acima:
        return schemas.Insight(
            regra="destaque", frase=f"Nenhum vídeo passou de {vezes(DESTAQUE_ACIMA)} {views}.",
            valor=None, grupo=None, amostra=amostra(n, MIN_GRUPO), pendente=True)
    top = max(acima, key=lambda p: (p.medida.valor, p.publicado_em))
    razao = top.medida.valor / geral  # type: ignore[operator]
    outros = len(acima) - 1
    mais = f" (e mais {outros})" if outros else ""
    return schemas.Insight(
        regra="destaque", frase=f"“{top.titulo_curto}” teve {vezes(razao)} {views}{mais}.",
        valor=razao, grupo=top.titulo_curto, amostra=amostra(n, MIN_GRUPO), pendente=False)
