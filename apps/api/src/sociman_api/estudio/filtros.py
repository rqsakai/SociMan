"""O perfil base nas rotas da biblioteca da agência (spec 029, contracts/http-api.md): o filtro
`perfilId` das listas e o campo `perfilId` dos cadastros em multipart."""

from typing import Annotated
from uuid import UUID

from fastapi import Query
from sqlalchemy.orm import Session

from sociman_api.perfis import base as perfil_base

PerfilFiltro = Annotated[str | None, Query(
    alias="perfilId", max_length=40,
    description="Perfil base: ausente = todos; `sem` = sem perfil; ou o id de um perfil")]


def filtro(db: Session, valor: str | None) -> perfil_base.Filtro:
    """O `perfilId` das listas; um perfil que não existe → 400 `perfil_invalido` (arquivado
    passa)."""
    f = perfil_base.filtro_perfil(valor)
    if f is not None and f != perfil_base.SEM:
        perfil_base.perfil_existente(db, f)
    return f


def form_perfil(valor: str | None) -> UUID | None:
    """O `perfilId` de um multipart: vazio = sem perfil base; fora do formato → 400."""
    if valor is None or not valor.strip():
        return None
    try:
        return UUID(valor.strip())
    except ValueError:
        raise perfil_base.perfil_invalido("perfilId") from None
