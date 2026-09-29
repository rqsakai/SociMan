"""Modelo do corte (data-model.md da spec 004). A linha é o job de processamento (R1, R10).

Só as ações do usuário (envio e "tentar de novo") geram versão no histórico; as transições do
worker (`processando`, `pronto`, `falhou`, progresso) são estado de job, com timestamps
próprios. Nada é apagado: nem a linha nem os vídeos (FR-016).
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base


class CorteStatus(enum.StrEnum):
    na_fila = "na_fila"
    processando = "processando"
    pronto = "pronto"
    falhou = "falhou"


class Corte(AuditMixin, Base):
    """`created_by` é o autor do envio (FR-017)."""

    __tablename__ = "cortes"
    __table_args__ = (
        CheckConstraint("status <> 'pronto' OR result_key IS NOT NULL",
                        name="ck_cortes_pronto_result"),
        CheckConstraint("status <> 'falhou' OR error_message IS NOT NULL",
                        name="ck_cortes_falhou_message"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_cortes_progress"),
    )
    __versioned_fields__ = ("hook_text", "kit_version", "status")
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    hook_text: Mapped[str] = mapped_column(Text, nullable=False)
    kit_version: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 = padrão nunca salvo
    # Tokens resolvidos no envio (hex, fontes e imagem por object_key): o worker só usa estes.
    kit_tokens: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[CorteStatus] = mapped_column(
        Enum(CorteStatus, name="corte_status"),
        nullable=False,
        default=CorteStatus.na_fila,
        server_default=CorteStatus.na_fila.value,
    )
    progress: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    error_code: Mapped[str | None] = mapped_column(Text)  # corrupted|timeout|interrupted|…
    error_message: Mapped[str | None] = mapped_column(Text)  # pt-BR, exibida ao usuário
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    original_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_content_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    video_codec: Mapped[str] = mapped_column(Text, nullable=False)
    audio_codec: Mapped[str | None] = mapped_column(Text)  # null = sem áudio
    original_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    result_key: Mapped[str | None] = mapped_column(Text, unique=True)
    result_bytes: Mapped[int | None] = mapped_column(BigInteger)
    poster_key: Mapped[str | None] = mapped_column(Text)  # bucket `sociman` (imgproxy)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


Index("ix_cortes_status_queued_at", Corte.status, Corte.queued_at)
Index("ix_cortes_perfil_created_at", Corte.perfil_id, Corte.created_at.desc())
