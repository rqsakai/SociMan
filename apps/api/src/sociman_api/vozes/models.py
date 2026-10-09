"""Vozes do perfil (data-model.md da spec 025, research R11): uma voz de gravação (pessoa real,
com consentimento) ou sintética (VoiceDesign), com a referência aprovada que o shop-tts usa
para narrar (`entity_type = "voz"`).

A gravação original é guardada completa e nunca entra na limpeza de 90 dias; só a revogação do
consentimento (exceção 2 da 4.3.0) a apaga. `analise` e `sincronizada_em` são estado técnico,
fora do snapshot.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.geracao import models as _geracao_models  # noqa: F401 — FK para audios
from sociman_api.perfis.models import _Versioned

ENTITY = "voz"


class VozOrigem(enum.StrEnum):
    gravacao = "gravacao"
    sintetica = "sintetica"


class VozStatus(enum.StrEnum):
    rascunho = "rascunho"
    gerando = "gerando"
    revisao = "revisao"
    aprovada = "aprovada"


class Voz(_Versioned, AuditMixin, Base):
    __tablename__ = "vozes"
    __versioned_fields__ = ("name", "origem", "descricao", "tom", "gravacao_audio_id",
                            "ref_audio_id", "ref_texto", "consentimento", "status", "archived",
                            "perfil_id")  # 029: o perfil base
    __immutable_fields__ = ("origem",)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("perfis.id"))  # 029: opcional
    name: Mapped[str] = mapped_column(Text, nullable=False)
    origem: Mapped[VozOrigem] = mapped_column(Enum(VozOrigem, name="voz_origem"),
                                              nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    tom: Mapped[str] = mapped_column(Text, nullable=False)
    gravacao_audio_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("audios.id"))
    ref_audio_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("audios.id"))
    ref_texto: Mapped[str | None] = mapped_column(Text)
    analise: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    consentimento: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[VozStatus] = mapped_column(Enum(VozStatus, name="voz_status"), nullable=False,
                                              default=VozStatus.rascunho,
                                              server_default="rascunho")
    sincronizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def revogada(self) -> bool:
        return bool((self.consentimento or {}).get("revogado_em"))


# 029: o nome é único na agência inteira (entre as ativas)
Index("uq_vozes_nome", func.lower(Voz.name), unique=True, postgresql_where=text("archived_at IS NULL"))
Index("ix_vozes_lista_agencia", Voz.archived_at, Voz.updated_at.desc(), Voz.id)
Index("ix_vozes_perfil", Voz.perfil_id, Voz.archived_at, Voz.updated_at.desc(), Voz.id)
