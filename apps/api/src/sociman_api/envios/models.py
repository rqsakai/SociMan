"""Padrões de corte do perfil e envios ao OpenShorts (data-model.md da spec 006, R4, R6, R8).

O envio é a **seleção** (`selecionado`) e depois o **job no OpenShorts**. Só as ações humanas
(selecionar, enviar, descartar, tentar de novo) geram versão; submissão, polling, progresso e
importação são estado de job, como na 004. A versão da ação "enviar" é o registro do princípio
II: autor, data, fonte e `direito_no_envio`. Envio não tem `revert` (exceção aprovada do
princípio VII): refazer é um envio novo.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.perfis.models import _Versioned

LAYOUTS = ("auto", "none", "split", "screencast", "speaker_cut")
FORMATOS = ("vertical", "square")
LEGENDAS = ("kit", "gerador", "nenhuma")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class EnvioOrigem(enum.StrEnum):
    canal = "canal"
    avulso_link = "avulso_link"
    avulso_arquivo = "avulso_arquivo"


class EnvioStatus(enum.StrEnum):
    selecionado = "selecionado"
    na_fila = "na_fila"
    aguardando_openshorts = "aguardando_openshorts"
    confirmar_qualidade = "confirmar_qualidade"
    processando = "processando"
    importando = "importando"
    pronto = "pronto"
    sem_clipes = "sem_clipes"
    falhou = "falhou"
    descartado = "descartado"


class DireitoEnvio(enum.StrEnum):
    """O direito do canal no momento do envio, ou `avulso` (princípio II)."""

    proprio = "proprio"
    parceiro = "parceiro"
    programa_de_cortes = "programa_de_cortes"
    sem_acordo = "sem_acordo"
    avulso = "avulso"


class PadroesCorte(AuditMixin, Base):
    """Um por perfil, preguiçoso: sem linha, a API devolve o padrão com `version: 0`."""

    __tablename__ = "padroes_corte"
    __table_args__ = (
        CheckConstraint("clip_min_s BETWEEN 5 AND 175", name="ck_padroes_corte_clip_min"),
        CheckConstraint("clip_max_s BETWEEN 10 AND 180 AND clip_max_s >= clip_min_s + 5",
                        name="ck_padroes_corte_clip_max"),
        CheckConstraint("quantidade IS NULL OR quantidade BETWEEN 1 AND 15",
                        name="ck_padroes_corte_quantidade"),
        CheckConstraint(_in("layout", LAYOUTS), name="ck_padroes_corte_layout"),
        CheckConstraint(_in("formato", FORMATOS), name="ck_padroes_corte_formato"),
        CheckConstraint(_in("legenda", LEGENDAS), name="ck_padroes_corte_legenda"),
    )
    __versioned_fields__ = (
        "clip_min_s", "clip_max_s", "quantidade", "layout", "formato", "legenda",
        "marca_automatica", "conta_padrao_id",
    )
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("perfis.id"), nullable=False, unique=True
    )
    clip_min_s: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    clip_max_s: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    quantidade: Mapped[int | None] = mapped_column(SmallInteger)  # null = a IA decide
    layout: Mapped[str] = mapped_column(Text, nullable=False)
    formato: Mapped[str] = mapped_column(Text, nullable=False)
    legenda: Mapped[str] = mapped_column(Text, nullable=False)
    marca_automatica: Mapped[bool] = mapped_column(Boolean, nullable=False)
    conta_padrao_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contas.id"))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class Envio(_Versioned, AuditMixin, Base):
    """`created_by` = quem selecionou; o autor do envio fica no histórico."""

    __tablename__ = "envios"
    __table_args__ = (
        CheckConstraint(
            "origem <> 'canal' OR (video_fonte_id IS NOT NULL AND source_url IS NOT NULL)",
            name="ck_envios_origem_canal",
        ),
        CheckConstraint("origem <> 'avulso_link' OR source_url IS NOT NULL",
                        name="ck_envios_origem_link"),
        CheckConstraint("origem <> 'avulso_arquivo' OR upload_key IS NOT NULL",
                        name="ck_envios_origem_arquivo"),
        CheckConstraint(
            "status IN ('selecionado', 'descartado') "
            "OR (config IS NOT NULL AND direito_no_envio IS NOT NULL)",
            name="ck_envios_enviado_config",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_envios_progress"),
        CheckConstraint("char_length(source_title) BETWEEN 1 AND 200",
                        name="ck_envios_source_title"),
    )
    __versioned_fields__ = (
        "status", "config", "direito_no_envio", "aviso_confirmado", "source_title", "source_url",
        "canal_fonte_id", "video_fonte_id", "origem", "archived",
    )
    __immutable_fields__ = ()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    origem: Mapped[EnvioOrigem] = mapped_column(
        Enum(EnvioOrigem, name="envio_origem"), nullable=False
    )
    video_fonte_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("videos_fonte.id")
    )
    canal_fonte_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("canais_fonte.id")
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(Text, nullable=False)
    upload_key: Mapped[str | None] = mapped_column(Text, unique=True)  # bucket sociman-videos
    upload_bytes: Mapped[int | None] = mapped_column(BigInteger)
    upload_duration_ms: Mapped[int | None] = mapped_column(Integer)
    upload_sha256: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EnvioStatus] = mapped_column(
        Enum(EnvioStatus, name="envio_status"),
        nullable=False,
        default=EnvioStatus.selecionado,
        server_default=EnvioStatus.selecionado.value,
    )
    # Padrões resolvidos no envio + `subtitle` do kit (se legenda = kit) + `kit_version`.
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    direito_no_envio: Mapped[DireitoEnvio | None] = mapped_column(
        Enum(DireitoEnvio, name="direito_envio")
    )
    aviso_confirmado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    force_low_quality: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    openshorts_job_id: Mapped[str | None] = mapped_column(Text)
    openshorts_queue_pos: Mapped[int | None] = mapped_column(SmallInteger)
    progress: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    clips_total: Mapped[int | None] = mapped_column(SmallInteger)
    clips_importados: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)  # source_invalid|openshorts_lost|…
    error_message: Mapped[str | None] = mapped_column(Text)  # pt-BR
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_envios_status_next_attempt", Envio.status, Envio.next_attempt_at)
Index("ix_envios_perfil_created", Envio.perfil_id, Envio.created_at.desc())
# Não único: o duplicado é permitido com confirmação; serve ao "já cortado".
Index("ix_envios_perfil_video_ativo", Envio.perfil_id, Envio.video_fonte_id,
      postgresql_where=text("archived_at IS NULL"))
