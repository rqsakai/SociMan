"""Modelos dos canais-fonte, vídeos, métricas e cota (data-model.md da spec 006).

O canal é versionado (direito, evidência, perfis ligados e arquivamento); o direito é
informativo e só o dono o muda (princípio II). Vídeos, métricas e cota são espelho do YouTube,
escritos só pelo sistema (estado de job, sem versão). Nada é apagado: canal arquivado sai da
sync e da descoberta, mas os vídeos e envios ficam.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.perfis.models import _Versioned

CHANNEL_ID_PATTERN = r"^UC[0-9A-Za-z_-]{22}$"


class CanalDireito(enum.StrEnum):
    proprio = "proprio"
    parceiro = "parceiro"
    programa_de_cortes = "programa_de_cortes"
    sem_acordo = "sem_acordo"


class CanalSync(enum.StrEnum):
    pendente = "pendente"
    sincronizando = "sincronizando"
    ok = "ok"
    pausado_cota = "pausado_cota"
    erro = "erro"


class VideoLive(enum.StrEnum):
    nenhum = "nenhum"
    ao_vivo = "ao_vivo"
    agendado = "agendado"


class CanalPerfil(Base):
    """Ligação N:N canal ↔ perfil. Ligar e desligar mudam o `perfil_ids` do snapshot do canal."""

    __tablename__ = "canal_perfis"

    canal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("canais_fonte.id"), primary_key=True
    )
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class CanalFonte(_Versioned, AuditMixin, Base):
    __tablename__ = "canais_fonte"
    __table_args__ = (
        CheckConstraint(f"youtube_channel_id ~ '{CHANNEL_ID_PATTERN}'",
                        name="ck_canais_fonte_channel_id"),
        CheckConstraint(
            "direito_evidencia_url IS NULL OR (direito_evidencia_url ~ '^https?://' "
            "AND char_length(direito_evidencia_url) <= 500)",
            name="ck_canais_fonte_evidencia_url",
        ),
        CheckConstraint("char_length(direito_evidencia_nota) <= 2000",
                        name="ck_canais_fonte_evidencia_nota"),
    )
    # `title` e `handle` entram só para exibição (vêm do YouTube): a reversão os ignora.
    __versioned_fields__ = (
        "title", "handle", "direito", "direito_evidencia_url", "direito_evidencia_nota",
        "perfil_ids", "archived",
    )
    __immutable_fields__ = ("title", "handle")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # UNIQUE conta também os arquivados (409 canal_exists).
    youtube_channel_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    handle: Mapped[str | None] = mapped_column(Text)  # sem @, normalizado
    title: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)  # remota, servida via imgproxy
    subscribers: Mapped[int | None] = mapped_column(BigInteger)  # null = oculto
    video_count: Mapped[int | None] = mapped_column(Integer)
    uploads_playlist_id: Mapped[str] = mapped_column(Text, nullable=False)
    direito: Mapped[CanalDireito] = mapped_column(
        Enum(CanalDireito, name="canal_direito"),
        nullable=False,
        default=CanalDireito.sem_acordo,
        server_default=CanalDireito.sem_acordo.value,
    )
    direito_evidencia_url: Mapped[str | None] = mapped_column(Text)
    direito_evidencia_nota: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    sync_status: Mapped[CanalSync] = mapped_column(
        Enum(CanalSync, name="canal_sync"),
        nullable=False,
        default=CanalSync.pendente,
        server_default=CanalSync.pendente.value,
    )
    sync_progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )  # {lidos, total} durante a 1ª sync
    sync_error: Mapped[str | None] = mapped_column(Text)  # pt-BR, sem a chave
    full_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sync_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    perfil_links: Mapped[list[CanalPerfil]] = relationship(
        CanalPerfil, lazy="selectin", cascade="all, delete-orphan",
        order_by=CanalPerfil.perfil_id,
    )

    @property
    def perfil_ids(self) -> list[str]:
        """Lista ordenada (snapshot do histórico)."""
        return sorted(str(link.perfil_id) for link in self.perfil_links)


Index("ix_canais_fonte_next_sync_at", CanalFonte.next_sync_at)


class VideoFonte(Base):
    """Espelho do YouTube, escrito só pelo sistema (sem versão)."""

    __tablename__ = "videos_fonte"
    __table_args__ = (
        CheckConstraint("char_length(youtube_video_id) = 11", name="ck_videos_fonte_video_id"),
        CheckConstraint("char_length(description) <= 5000",
                        name="ck_videos_fonte_description"),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_videos_fonte_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    canal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("canais_fonte.id"), nullable=False
    )
    youtube_video_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    thumbnail_url: Mapped[str | None] = mapped_column(Text)  # mqdefault, remota
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    live: Mapped[VideoLive] = mapped_column(
        Enum(VideoLive, name="video_live"),
        nullable=False,
        default=VideoLive.nenhum,
        server_default=VideoLive.nenhum.value,
    )
    disponivel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    metrics_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_metrics_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vph_recente: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    score: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), nullable=False, default=Decimal(0), server_default=text("0")
    )
    score_reason: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    score_detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    recomendavel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


Index("ix_videos_fonte_canal_published", VideoFonte.canal_id, VideoFonte.published_at.desc())
Index("ix_videos_fonte_recomendavel_score", VideoFonte.recomendavel, VideoFonte.score.desc())
Index("ix_videos_fonte_next_metrics_at", VideoFonte.next_metrics_at)


class VideoMetrica(Base):
    """Histórico de métricas; só INSERT."""

    __tablename__ = "video_metricas"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    video_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("videos_fonte.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)


Index("ix_video_metricas_video_observed", VideoMetrica.video_id, VideoMetrica.observed_at.desc())


class YoutubeCota(Base):
    """Uma linha por dia do Pacífico (a cota zera à meia-noite de America/Los_Angeles)."""

    __tablename__ = "youtube_cota"

    dia: Mapped[date] = mapped_column(Date, primary_key=True)
    unidades: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    aviso_enviado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
