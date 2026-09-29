"""Postagens preparadas e sugestões de texto (data-model.md da spec 006, R9 e R10).

O SociMan nunca publica (princípio I): `postado` só é marcado pela rota humana. Uma postagem
por corte e conta de destino (a conta dá a plataforma). O snapshot versionado é o histórico dos
textos (US5-2). As chamadas ao Claude ficam em `ia_chamadas` (spec 008, `ia/models.py`), a
`sugestoes_texto` da 006 renomeada: `sugestao_id` continua apontando para os mesmos ids.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.ia import models as _ia_models  # noqa: F401 — FK para ia_chamadas
from sociman_api.perfis.models import _Versioned


class EstadoPostagem(enum.StrEnum):
    rascunho = "rascunho"
    agendado = "agendado"
    postado = "postado"


class Postagem(_Versioned, AuditMixin, Base):
    __tablename__ = "postagens"
    __table_args__ = (
        CheckConstraint("char_length(titulo) <= 100", name="ck_postagens_titulo"),
        CheckConstraint("char_length(descricao) <= 2000", name="ck_postagens_descricao"),
        CheckConstraint("estado <> 'agendado' OR planned_at IS NOT NULL",
                        name="ck_postagens_agendado_planned"),
        # Uma postagem ativa por corte e conta (409 postagem_exists).
        Index("uq_postagens_corte_conta_ativa", "corte_id", "conta_id", unique=True,
              postgresql_where=text("archived_at IS NULL")),
    )
    __versioned_fields__ = (
        "conta_id", "titulo", "descricao", "hashtags", "estado", "planned_at", "posted_url",
        "archived",
    )
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    corte_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cortes.id"), nullable=False)
    conta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contas.id"), nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    hashtags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    estado: Mapped[EstadoPostagem] = mapped_column(
        Enum(EstadoPostagem, name="postagem_estado"),
        nullable=False,
        default=EstadoPostagem.rascunho,
        server_default=EstadoPostagem.rascunho.value,
    )
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lembrado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_url: Mapped[str | None] = mapped_column(Text)
    sugestao_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ia_chamadas.id")
    )


Index("ix_postagens_estado_planned", Postagem.estado, Postagem.planned_at)
