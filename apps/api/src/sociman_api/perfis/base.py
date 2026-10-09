"""Perfil base (spec 029, research R4): o perfil cujo guia, proibidas e padrões valem numa geração
ou chamada de IA sobre um item da biblioteca da agência.

O pedido traz `perfilBaseId` com 3 estados:
- ausente (`AUSENTE`): o perfil base do item;
- `None`: nenhum (só as regras do tipo, sem guia);
- um uuid: aquele perfil, só para este pedido (o item não muda).

O perfil precisa existir (400 `perfil_invalido`) e, para gerar, estar ativo (409
`perfil_base_arquivado`). O filtro das listas usa `filtro_perfil` (`sem` = sem perfil base)."""

import uuid
from typing import Final, Literal

from sqlalchemy.orm import Session

from sociman_api.errors import ApiError
from sociman_api.perfis.models import Perfil


class _Ausente:
    def __repr__(self) -> str:
        return "AUSENTE"


AUSENTE: Final = _Ausente()
SEM: Final = "sem"
Pedido = uuid.UUID | None | _Ausente
Filtro = uuid.UUID | Literal["sem"] | None


def perfil_invalido(field: str) -> ApiError:
    return ApiError(400, "perfil_invalido", "Perfil não encontrado", details={"field": field})


def perfil_existente(db: Session, perfil_id: uuid.UUID | None, field: str = "perfilId"
                     ) -> Perfil | None:
    """O perfil base de um item (criar ou editar): pode ser arquivado; nulo = sem perfil."""
    if perfil_id is None:
        return None
    perfil = db.get(Perfil, perfil_id)
    if perfil is None:
        raise perfil_invalido(field)
    return perfil


def resolver(db: Session, item_perfil_id: uuid.UUID | None, pedido: Pedido = AUSENTE,
             field: str = "perfilBaseId") -> Perfil | None:
    """O perfil base de um pedido de geração ou de IA (FR-008 a FR-010)."""
    perfil_id = item_perfil_id if isinstance(pedido, _Ausente) else pedido
    if perfil_id is None:
        return None
    perfil = db.get(Perfil, perfil_id)
    if perfil is None:
        raise perfil_invalido(field)
    if perfil.archived:
        raise ApiError(409, "perfil_base_arquivado",
                       "O perfil base está arquivado: escolha outro ou nenhum",
                       details={"field": field})
    return perfil


def filtro_perfil(valor: str | None) -> Filtro:
    """O parâmetro `perfilId` das listas da agência: ausente = todos; `sem`; ou um uuid."""
    if valor is None or valor == "":
        return None
    if valor == SEM:
        return SEM
    try:
        return uuid.UUID(valor)
    except ValueError:
        raise ApiError(400, "invalid_query", "perfilId: use um id de perfil ou 'sem'",
                       details={"field": "perfilId"}) from None


def aplicar_filtro(stmt, coluna, filtro: Filtro):
    """Aplica o filtro de perfil base num select (coluna = `Modelo.perfil_id`)."""
    if filtro is None:
        return stmt
    if filtro == SEM:
        return stmt.where(coluna.is_(None))
    return stmt.where(coluna == filtro)
