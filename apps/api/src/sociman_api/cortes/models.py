"""Modelo do corte (data-model.md da spec 004). A linha é o job de processamento (R1, R10).

Só as ações do usuário (envio e "tentar de novo") geram versão no histórico; as transições do
worker (`processando`, `pronto`, `falhou`, progresso) são estado de job, com timestamps
próprios. Nada é apagado: nem a linha nem os vídeos (FR-016).

Spec 006: o clipe importado do OpenShorts também é um corte, em `revisao` (sem kit e com o gancho
sugerido); "Aplicar marca" leva a `na_fila`, e daí o worker e a fila seguem iguais (só pegam
`na_fila`). Cortes podem ser arquivados e restaurados; sem `revert` (exceção aprovada do
princípio VII).
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
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base


class CorteStatus(enum.StrEnum):
    revisao = "revisao"  # clipe do OpenShorts esperando "Aplicar marca" (spec 006)
    na_fila = "na_fila"
    processando = "processando"
    pronto = "pronto"
    falhou = "falhou"


class CorteOrigem(enum.StrEnum):
    upload = "upload"
    openshorts = "openshorts"


class Corte(AuditMixin, Base):
    """`created_by` é o autor do envio (FR-017)."""

    __tablename__ = "cortes"
    __table_args__ = (
        CheckConstraint("status <> 'pronto' OR result_key IS NOT NULL",
                        name="ck_cortes_pronto_result"),
        CheckConstraint("status <> 'falhou' OR error_message IS NOT NULL",
                        name="ck_cortes_falhou_message"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_cortes_progress"),
        CheckConstraint(
            "status::text = 'revisao' OR (kit_version IS NOT NULL AND kit_tokens IS NOT NULL)",
            name="ck_cortes_kit",
        ),
        CheckConstraint("origem <> 'openshorts' OR envio_id IS NOT NULL",
                        name="ck_cortes_origem_envio"),
        CheckConstraint(
            "legenda IS NULL OR legenda IN ('kit', 'gerador', 'nenhuma', 'sem_fala')",
            name="ck_cortes_legenda",
        ),
        UniqueConstraint("envio_id", "clip_index", name="uq_cortes_envio_clip"),
    )
    __versioned_fields__ = ("hook_text", "kit_version", "status", "archived")
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    hook_text: Mapped[str] = mapped_column(Text, nullable=False)  # '' aceito em `revisao`
    # 0 = padrão nunca salvo; null só em `revisao` (a marca ainda não foi aplicada).
    kit_version: Mapped[int | None] = mapped_column(Integer)
    # Tokens resolvidos no envio (hex, fontes e imagem por object_key): o worker só usa estes.
    kit_tokens: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
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

    # ---- spec 006: clipe importado do OpenShorts ----
    origem: Mapped[CorteOrigem] = mapped_column(
        Enum(CorteOrigem, name="corte_origem"),
        nullable=False,
        default=CorteOrigem.upload,
        server_default=CorteOrigem.upload.value,
    )
    envio_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("envios.id"))
    clip_index: Mapped[int | None] = mapped_column(SmallInteger)  # importação idempotente
    source_start_ms: Mapped[int | None] = mapped_column(Integer)  # trecho no vídeo de origem
    source_end_ms: Mapped[int | None] = mapped_column(Integer)
    openshorts_title: Mapped[str | None] = mapped_column(Text)
    openshorts_description: Mapped[str | None] = mapped_column(Text)
    openshorts_score: Mapped[int | None] = mapped_column(SmallInteger)
    transcript: Mapped[str | None] = mapped_column(Text)  # até 4.000 caracteres (para o Claude)
    legenda: Mapped[str | None] = mapped_column(Text)  # kit|gerador|nenhuma|sem_fala
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))

    @property
    def archived(self) -> bool:
        return self.archived_at is not None


Index("ix_cortes_status_queued_at", Corte.status, Corte.queued_at)
Index("ix_cortes_perfil_created_at", Corte.perfil_id, Corte.created_at.desc())
