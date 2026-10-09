"""Schemas do AI Studio (spec 029, contracts/http-api.md). JSON em camelCase."""

from sociman_api.auth.schemas import CamelModel


class EstudioResumo(CamelModel):
    """Os itens ativos (não arquivados) da biblioteca por tipo, no filtro de perfil base."""

    avatares: int
    cenarios: int
    assets: int  # imagem, sticker, marca d'água e fundo (Clarification 2)
    cenas: int
    produtos: int
    vozes: int
