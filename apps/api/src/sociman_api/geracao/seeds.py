"""Seeds das opções (research R7).

A 1ª geração de um alvo e passo sorteia uma base (`secrets.randbelow(2**31 - 1) + 1`) e a opção
*i* usa `base + i - 1`, como o pipeline. As seguintes ("Gerar outras", ou um novo pedido para o
mesmo alvo e passo) começam em `max(seeds já usadas) + 1`, e por isso nunca repetem. As usadas
saem do `params.seeds` de toda geração daquele alvo e passo (inclusive as que ainda estão na
fila, que ainda não têm candidato).
"""

import secrets
import uuid
from collections.abc import Callable, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from sociman_api.geracao.models import GeracaoAlvo

BASE_MAX = 2**31 - 1


def sortear_base() -> int:
    return secrets.randbelow(BASE_MAX) + 1


def proximas(usadas: Iterable[int], n: int, sortear: Callable[[], int] = sortear_base
             ) -> list[int]:
    """`n` seeds novas: a partir da maior já usada, ou de uma base sorteada se não há nenhuma."""
    usadas = list(usadas)
    base = max(usadas) + 1 if usadas else sortear()
    return [base + i for i in range(n)]


def usadas(db: Session, alvo_tipo: GeracaoAlvo, alvo_id: uuid.UUID, passo: str) -> list[int]:
    rows = db.execute(text(
        "SELECT s.value::bigint FROM geracoes g, jsonb_array_elements_text("
        "COALESCE(g.params->'seeds', '[]'::jsonb)) AS s(value) "
        "WHERE g.alvo_tipo = CAST(:t AS geracao_alvo) AND g.alvo_id = :a AND g.passo = :p"),
        {"t": alvo_tipo.value, "a": alvo_id, "p": passo})
    return [int(v) for (v,) in rows]


def novas(db: Session, alvo_tipo: GeracaoAlvo, alvo_id: uuid.UUID, passo: str, n: int
          ) -> list[int]:
    return proximas(usadas(db, alvo_tipo, alvo_id, passo), n)
