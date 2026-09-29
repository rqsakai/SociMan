"""Regras por tipo de campo e registro das chamadas (data-model.md da spec 008).

- `ia_regras`: a personalização das regras de um tipo. Sem linha = usa o padrão do código (a
  linha nasce na primeira edição, como o kit com `version = 0`). Entidade versionada
  (`entity_type = "ia_regra"`), sem arquivamento: "voltar ao padrão" grava `texto = NULL`.
- `ia_chamadas` (a `sugestoes_texto` da 006 renomeada, com os mesmos ids): log de cada geração.
  Só INSERT, salvo as colunas de desfecho, que são estado sem versão (R10).
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.perfis.models import Platform

REGRAS_MAX = 8000


class IaDesfecho(enum.StrEnum):
    sem_acao = "sem_acao"
    aplicada = "aplicada"
    editada = "editada"
    descartada = "descartada"
    erro = "erro"


class IaRegra(AuditMixin, Base):
    """Sem `archived_at`: a linha nunca some ("voltar ao padrão" é o equivalente)."""

    __tablename__ = "ia_regras"
    __table_args__ = (
        CheckConstraint(f"texto IS NULL OR char_length(texto) BETWEEN 1 AND {REGRAS_MAX}",
                        name="ck_ia_regras_texto"),
        UniqueConstraint("tipo_campo", name="uq_ia_regras_tipo_campo"),
    )
    __versioned_fields__ = ("tipo_campo", "texto")
    __immutable_fields__ = ("tipo_campo",)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo_campo: Mapped[str] = mapped_column(Text, nullable=False)
    texto: Mapped[str | None] = mapped_column(Text)  # NULL = usa o padrão do código
    padrao_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class IaChamada(Base):
    """Uma geração (com proposta ou erro), com o contexto enviado, o custo e o desfecho."""

    __tablename__ = "ia_chamadas"
    __table_args__ = (
        CheckConstraint("(erro_code IS NOT NULL) = (desfecho = 'erro')",
                        name="ck_ia_chamadas_erro_desfecho"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo_campo: Mapped[str] = mapped_column(Text, nullable=False)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)  # asset|perfil|kit|postagem|corte
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # null no kit nunca salvo
    corte_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cortes.id"))
    conta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contas.id"))
    plataforma: Mapped[Platform | None] = mapped_column(Enum(Platform, name="platform"))
    sessao_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    anteriores: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), nullable=False, default=list, server_default=text("'{}'")
    )
    aceitos: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    rejeitados: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    instrucao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    entrada: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    contexto_faltante: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    proposta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # null quando deu erro
    explicacao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    avisos: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    excede: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ajustes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_servido: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)  # ia/1 (006: textos/1)
    regras_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    padrao_versao: Mapped[int | None] = mapped_column(Integer)
    erro_code: Mapped[str | None] = mapped_column(Text)  # unconfigured|timeout|refusal|invalid|api_error
    erro_status: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_creation_tokens: Mapped[int | None] = mapped_column(Integer)
    custo_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    precos_versao: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    desfecho: Mapped[IaDesfecho] = mapped_column(
        Enum(IaDesfecho, name="ia_desfecho"), nullable=False, default=IaDesfecho.sem_acao,
        server_default=IaDesfecho.sem_acao.value,
    )
    desfecho_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desfecho_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    aplicada_versao: Mapped[int | None] = mapped_column(Integer)
    itens_aplicados: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


Index("ix_ia_chamadas_created", IaChamada.created_at.desc(), IaChamada.id)
Index("ix_ia_chamadas_perfil_created", IaChamada.perfil_id, IaChamada.created_at.desc())
Index("ix_ia_chamadas_tipo_created", IaChamada.tipo_campo, IaChamada.created_at.desc())
Index("ix_ia_chamadas_sessao", IaChamada.sessao_id,
      postgresql_where=text("sessao_id IS NOT NULL"))
