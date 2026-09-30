"""`EstadoColeta` (contracts/http-api.md da 016, "Tipos") num módulo à parte, sem importar
`postagem`: o `publicacao/schemas.py` o usa no `Conexao.metricas`, e o `postagem/schemas.py`
importa o `publicacao/schemas.py` (um import de `metricas/schemas.py` ali faria ciclo).
`metricas/schemas.py` reexporta os dois.
"""

from datetime import datetime
from typing import Literal

from sociman_api.auth.schemas import CamelModel

PermissaoColeta = Literal["ok", "faltando", "sem_conexao"]


class ErroColeta(CamelModel):
    codigo: str
    motivo: str  # pt-BR
    em: datetime


class EstadoColeta(CamelModel):
    permissao: PermissaoColeta
    escopos_faltando: list[str]
    coletando: bool  # série ativa agora
    habilitada: bool  # METRICAS_COLETA_HABILITADA
    ultima_coleta_em: datetime | None
    proxima_coleta_em: datetime | None
    erro: ErroColeta | None
    varredura_concluida: bool
    videos: int
    fotos: int
