"""Modelos Pydantic das notificações (contracts/http-api.md da 006, "Notificações")."""

from datetime import datetime
from typing import Annotated, Self

from pydantic import ConfigDict, Field, model_validator

from sociman_api.auth.schemas import CamelModel
from sociman_api.notificacoes.models import NotificacaoTipo

__all__ = ["MarcarLidasIn", "NaoLidasOut", "Notificacao", "NotificacoesList"]


class Notificacao(CamelModel):
    id: int
    tipo: NotificacaoTipo
    titulo: str
    corpo: str
    link: str
    created_at: datetime
    lida: bool


class NotificacoesList(CamelModel):
    items: list[Notificacao]
    nao_lidas: int


class NaoLidasOut(CamelModel):
    nao_lidas: int


class MarcarLidasIn(CamelModel):
    """`{ids: [...]}` ou `{todas: true}`, nunca os dois."""

    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=500)] | None = None
    todas: bool = False

    @model_validator(mode="after")
    def _um_dos_dois(self) -> Self:
        if self.todas == (self.ids is not None):
            raise ValueError("Informe ids ou todas: true")
        return self
