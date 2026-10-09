"""Anotação ou proposta presa a um item do domínio (data-model.md da spec 009).

`entity_type = "anotacao"`, com versão e histórico. O autor é um cliente MCP **ou** um usuário
(CHECK `ck_anotacoes_autor`); quem aplica ou descarta é sempre humano (`resolvida_por`).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base


class AnotacaoAlvo(enum.StrEnum):
    perfil = "perfil"
    conta = "conta"
    canal = "canal"
    video_fonte = "video_fonte"
    corte = "corte"
    conteudo = "conteudo"
    destino = "destino"
    cena = "cena"  # spec 010
    produto = "produto"  # spec 012: só `observacao`


class AnotacaoTipo(enum.StrEnum):
    observacao = "observacao"
    proposta_texto = "proposta_texto"  # só em destino (primeiro corte)
    proposta_cena = "proposta_cena"  # spec 010: em perfil (cena nova) ou cena (alteração)


class AnotacaoSituacao(enum.StrEnum):
    aberta = "aberta"
    aplicada = "aplicada"
    descartada = "descartada"
    arquivada = "arquivada"


class Anotacao(AuditMixin, Base):
    __tablename__ = "anotacoes"
    __table_args__ = (
        CheckConstraint("char_length(texto) BETWEEN 1 AND 4000", name="ck_anotacoes_texto"),
        CheckConstraint(
            "(autor_kind = 'mcp_client' AND autor_mcp_cliente_id IS NOT NULL "
            "AND autor_user_id IS NULL) OR (autor_kind = 'user' AND autor_user_id IS NOT NULL "
            "AND autor_mcp_cliente_id IS NULL)", name="ck_anotacoes_autor"),
        CheckConstraint(  # spec 010 (migration 0015)
            "tipo = 'observacao' OR (tipo = 'proposta_texto' AND alvo_tipo = 'destino') "
            "OR (tipo = 'proposta_cena' AND alvo_tipo IN ('perfil', 'cena'))",
            name="ck_anotacoes_proposta_alvo"),
    )
    __versioned_fields__ = ("texto", "campos", "situacao", "motivo_descarte")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    alvo_tipo: Mapped[AnotacaoAlvo] = mapped_column(Enum(AnotacaoAlvo, name="anotacao_alvo"),
                                                    nullable=False)
    alvo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Derivado do alvo, para filtrar a caixa por perfil. Canal e vídeo-fonte são N:N com perfis:
    # o primeiro perfil ligado (nulo se nenhum).
    perfil_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("perfis.id"))
    tipo: Mapped[AnotacaoTipo] = mapped_column(Enum(AnotacaoTipo, name="anotacao_tipo"),
                                               nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    campos: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    situacao: Mapped[AnotacaoSituacao] = mapped_column(
        Enum(AnotacaoSituacao, name="anotacao_situacao"), nullable=False,
        default=AnotacaoSituacao.aberta, server_default=AnotacaoSituacao.aberta.value)
    autor_kind: Mapped[str] = mapped_column(Text, nullable=False)
    autor_mcp_cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("mcp_clientes.id"))
    autor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    resolvida_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_descarte: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))
