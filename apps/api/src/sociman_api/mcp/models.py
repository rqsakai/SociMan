"""Clientes MCP, interruptor e registro de chamadas (data-model.md da spec 009).

- `mcp_clientes`: um cliente por agente, com credencial guardada só como SHA-256 (R4) e histórico
  (`entity_type = "mcp_cliente"`). Revogar é final (exceção do VII aprovada pelo dono);
- `mcp_config`: o botão da tela do interruptor (linha única, `entity_type = "mcp_config"`); o
  outro nível é `MCP_HABILITADO` (R11);
- `mcp_chamadas`: **só inserção** (trigger `mcp_chamadas_so_insercao` na migration 0014), uma
  linha por chamada de um token MCP (R8).
"""

import enum
import uuid
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base


class McpEscopo(enum.StrEnum):
    leitura = "leitura"
    propostas = "propostas"  # inclui leitura


class McpSituacao(enum.StrEnum):
    ativo = "ativo"
    suspenso = "suspenso"
    revogado = "revogado"  # final


class McpResultado(enum.StrEnum):
    ok = "ok"
    erro = "erro"
    recusada = "recusada"
    limite = "limite"
    nao_autenticado = "nao_autenticado"


class McpVia(enum.StrEnum):
    mcp = "mcp"  # pela ponte do servidor MCP
    api = "api"  # token MCP usado direto na API


class McpCliente(AuditMixin, Base):
    __tablename__ = "mcp_clientes"
    __table_args__ = (
        CheckConstraint("char_length(nome) BETWEEN 1 AND 60", name="ck_mcp_clientes_nome"),
        CheckConstraint("char_length(descricao) <= 300", name="ck_mcp_clientes_descricao"),
        CheckConstraint("limite_por_minuto BETWEEN 1 AND 600", name="ck_mcp_clientes_limite_min"),
        CheckConstraint("limite_escritas_dia BETWEEN 0 AND 5000",
                        name="ck_mcp_clientes_limite_dia"),
    )
    # O hash nunca entra no histórico; o `token_id` entra para a rotação aparecer no diff.
    __versioned_fields__ = ("nome", "descricao", "escopo", "situacao", "expira_em",
                            "limite_por_minuto", "limite_escritas_dia", "token_id")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    nome_normalizado: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    escopo: Mapped[McpEscopo] = mapped_column(Enum(McpEscopo, name="mcp_escopo"), nullable=False)
    situacao: Mapped[McpSituacao] = mapped_column(
        Enum(McpSituacao, name="mcp_situacao"), nullable=False, default=McpSituacao.ativo,
        server_default=McpSituacao.ativo.value)
    token_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_emitido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    limite_por_minuto: Mapped[int] = mapped_column(Integer, nullable=False, default=60,
                                                   server_default=text("60"))
    limite_escritas_dia: Mapped[int] = mapped_column(Integer, nullable=False, default=200,
                                                     server_default=text("200"))
    ultimo_uso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))

    def __repr__(self) -> str:  # nunca expõe o hash
        return f"McpCliente(id={self.id}, nome={self.nome!r}, token_id={self.token_id!r})"

    __str__ = __repr__


class McpConfig(AuditMixin, Base):
    __tablename__ = "mcp_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_mcp_config_unica"),)
    __versioned_fields__ = ("habilitado",)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                             server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))


class McpChamada(Base):
    """Imutável: a aplicação só faz INSERT (o trigger recusa UPDATE e DELETE)."""

    __tablename__ = "mcp_chamadas"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    ocorreu_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=func.now())
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mcp_clientes.id"))
    via: Mapped[McpVia] = mapped_column(Enum(McpVia, name="mcp_via"), nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    metodo: Mapped[str] = mapped_column(Text, nullable=False)
    rota: Mapped[str] = mapped_column(Text, nullable=False)
    args_resumo: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    resultado: Mapped[McpResultado] = mapped_column(Enum(McpResultado, name="mcp_resultado"),
                                                    nullable=False)
    status_http: Mapped[int | None] = mapped_column(SmallInteger)
    codigo_erro: Mapped[str | None] = mapped_column(Text)
    duracao_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escrita: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entidade_tipo: Mapped[str | None] = mapped_column(Text)
    entidade_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    ip: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET)
