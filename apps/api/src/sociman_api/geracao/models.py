"""Modelos da geração local (data-model.md da spec 021, research R2, R10 e R15).

`geracoes` é o pedido (o job), versionado (`entity_type = "geracao"`): só as ações humanas
(pedir, cancelar, tentar de novo, gerar outras, escolher) gravam versão; o andamento, a espera,
o erro e os candidatos são estado de job, como no envio da 006. `geracao_candidatos` são as
opções (só INSERT pelo gerador; DELETE só pela limpeza de 90 dias, exceção 1 da 4.3.0) e
`audios` é a irmã de `images` da 003 (imutável).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
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

ENTITY = "geracao"


class GeracaoAlvo(enum.StrEnum):
    asset = "asset"
    voz = "voz"  # 025
    produto = "produto"  # 012


class GeracaoMotor(enum.StrEnum):
    comfyui = "comfyui"
    tts = "tts"
    claude = "claude"


class GeracaoStatus(enum.StrEnum):
    na_fila = "na_fila"
    rodando = "rodando"
    revisao = "revisao"
    escolhido = "escolhido"
    descartada = "descartada"
    cancelada = "cancelada"
    entregue = "entregue"  # só o `voz.teste` (025)
    falhou = "falhou"


# Estados de que nenhuma ação humana sai (o `falhou` ainda aceita "Tentar de novo").
FINAIS = frozenset({GeracaoStatus.escolhido, GeracaoStatus.descartada, GeracaoStatus.cancelada,
                    GeracaoStatus.entregue})
# Os que têm `finished_at` (e entram na limpeza de 90 dias).
TERMINADOS = FINAIS | {GeracaoStatus.falhou}
MOTORES_GPU = frozenset({GeracaoMotor.comfyui, GeracaoMotor.tts})


class Geracao(AuditMixin, Base):
    __tablename__ = "geracoes"
    __versioned_fields__ = ("status", "escolhido_id", "error_code", "error_message")
    __immutable_fields__ = ("alvo_tipo", "alvo_id", "passo", "motor")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    alvo_tipo: Mapped[GeracaoAlvo] = mapped_column(Enum(GeracaoAlvo, name="geracao_alvo"),
                                                   nullable=False)
    alvo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)  # polimórfico, sem FK
    passo: Mapped[str] = mapped_column(Text, nullable=False)
    motor: Mapped[GeracaoMotor] = mapped_column(Enum(GeracaoMotor, name="geracao_motor"),
                                                nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    n_opcoes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[GeracaoStatus] = mapped_column(
        Enum(GeracaoStatus, name="geracao_status"), nullable=False,
        default=GeracaoStatus.na_fila, server_default=GeracaoStatus.na_fila.value)
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0,
                                          server_default=text("0"))
    etapa_mensagem: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0,
                                          server_default=text("0"))
    # Migration 0021: as paradas do gerador no meio (FR-023), fora do orçamento de `attempts`.
    interrupcoes: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0,
                                              server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    # use_alter: geracao_candidatos.geracao_id aponta de volta (ciclo de FKs).
    escolhido_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("geracao_candidatos.id", use_alter=True, name="fk_geracoes_escolhido"))
    de_geracao_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("geracoes.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    limpa_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))


class GeracaoCandidato(Base):
    __tablename__ = "geracao_candidatos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    geracao_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("geracoes.id"),
                                                  nullable=False)
    numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("images.id"))
    image_par_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("images.id"))
    audio_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("audios.id"))
    seed: Mapped[int | None] = mapped_column(BigInteger)
    metricas: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class Audio(Base):
    """Imutável. DELETE só pelas duas exceções da 4.3.0 (limpeza de 90 dias; LGPD na 025)."""

    __tablename__ = "audios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    formato: Mapped[str] = mapped_column(Text, nullable=False)  # wav | m4a | ogg | mp3
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    duracao_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
