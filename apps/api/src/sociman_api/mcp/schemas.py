"""Modelos Pydantic da gestão do MCP (contracts/http-api.md da 009). JSON em camelCase.

Nenhuma saída tem o hash; o `token` só aparece em `ClienteComToken` (criar e rotacionar).
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.mcp.models import McpEscopo, McpResultado, McpSituacao, McpVia
from sociman_api.perfis.schemas import UserRef

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Descricao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
LimiteMinuto = Annotated[int, Field(ge=1, le=600)]
LimiteDia = Annotated[int, Field(ge=0, le=5000)]
VersionNumber = Annotated[int, Field(ge=1)]


class Uso24h(CamelModel):
    chamadas: int
    recusas: int
    escritas: int


class ClienteMcp(CamelModel):
    id: UUID
    nome: str
    descricao: str
    escopo: McpEscopo
    situacao: McpSituacao
    token_id: str  # o `<id>` público da credencial (nunca o segredo)
    token_emitido_em: datetime
    expira_em: datetime | None
    vence_em_breve: bool  # vence em até 7 dias (FR-005)
    limite_por_minuto: int
    limite_escritas_dia: int
    ultimo_uso_em: datetime | None
    uso24h: Uso24h = Field(alias="uso24h")  # o gerador daria "uso24H"
    no_limite: bool  # houve 429 nos últimos 5 minutos
    revogado_em: datetime | None
    revogado_por: UserRef | None
    created_at: datetime
    created_by: UserRef | None
    version: int


class ClientesList(CamelModel):
    clientes: list[ClienteMcp]


class ClienteOut(CamelModel):
    cliente: ClienteMcp


class ClienteComToken(CamelModel):
    cliente: ClienteMcp
    token: str  # mostrado uma única vez (resposta com `Cache-Control: no-store`)


class CreateClienteIn(CamelModel):
    nome: Nome
    descricao: Descricao = ""
    escopo: McpEscopo
    expira_em: datetime | None = None
    limite_por_minuto: LimiteMinuto = 60
    limite_escritas_dia: LimiteDia = 200


class UpdateClienteIn(CamelModel):
    """Só os campos mandados mudam; `expiraEm: null` tira o vencimento."""

    version: VersionNumber
    nome: Nome | None = None
    descricao: Descricao | None = None
    escopo: McpEscopo | None = None
    expira_em: datetime | None = None
    limite_por_minuto: LimiteMinuto | None = None
    limite_escritas_dia: LimiteDia | None = None


class VersionIn(CamelModel):
    version: VersionNumber


class McpConfig(CamelModel):
    habilitado: bool  # o botão da tela
    servidor_habilitado: bool  # `MCP_HABILITADO` no `.env` (só leitura)
    version: int


class McpConfigIn(CamelModel):
    habilitado: bool
    version: VersionNumber


class ClienteRef(CamelModel):
    id: UUID
    nome: str


class EntidadeRef(CamelModel):
    tipo: str
    id: UUID
    link: str  # rota do SPA do item


class ChamadaMcp(CamelModel):
    id: int
    ocorreu_em: datetime
    cliente: ClienteRef | None
    via: McpVia
    tool: str
    metodo: str
    rota: str
    args_resumo: dict[str, Any]
    resultado: McpResultado
    status_http: int | None
    codigo_erro: str | None
    duracao_ms: int
    escrita: bool
    entidade: EntidadeRef | None


class ChamadasPage(CamelModel):
    chamadas: list[ChamadaMcp]
    next_cursor: str | None
