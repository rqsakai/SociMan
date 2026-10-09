"""Conteúdo: um vídeo publicável de um perfil (data-model.md da spec 014, research R1).

- Origem `corte`: o `id` **é o do corte** (`corte_id = id`). O corte continua sendo a fonte do
  arquivo, da situação, da miniatura e do arquivamento; aqui fica só o que é da central
  (`titulo` editável e o histórico `conteudo`). Nada do corte é copiado: os campos derivados
  saem de `conteudos/consulta.py`.
- Origem `video_proprio`: o conteúdo é dono do arquivo (vídeo no bucket de vídeos, miniatura no
  `sociman`) e do próprio arquivamento.

`Modo` é o modo do agendamento de um destino (`postagem/models.py`). Na 014 só `lembrete`
existe de fato (princípio I; CHECK `ck_postagens_modo_014`); os outros são só modelados.
"""

import enum
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.cortes import models as _cortes_models  # noqa: F401 — FK para cortes
from sociman_api.db import Base
from sociman_api.perfis.models import _Versioned


class ConteudoOrigem(enum.StrEnum):
    corte = "corte"
    video_proprio = "video_proprio"


class Modo(enum.StrEnum):
    """`agendamento_modo`. Só `lembrete` executa na 014 (o resto é da 015)."""

    lembrete = "lembrete"
    criar_rascunho = "criar_rascunho"
    publicar = "publicar"
    rascunho_e_publicar = "rascunho_e_publicar"


class Conteudo(_Versioned, AuditMixin, Base):
    __tablename__ = "conteudos"
    __table_args__ = (
        CheckConstraint(
            "(origem = 'corte' AND corte_id IS NOT DISTINCT FROM id AND video_key IS NULL"
            " AND archived_at IS NULL)"
            " OR (origem = 'video_proprio' AND corte_id IS NULL AND video_key IS NOT NULL"
            " AND poster_key IS NOT NULL AND duration_ms IS NOT NULL)",
            name="ck_conteudos_origem",
        ),
        CheckConstraint("char_length(titulo) <= 100", name="ck_conteudos_titulo"),
    )
    __versioned_fields__ = ("titulo", "archived")
    # Informativos: a reversão os ignora.
    __immutable_fields__ = (
        "origem", "corte_id", "video_key", "video_content_type", "video_bytes", "video_sha256",
        "original_filename", "duration_ms", "width", "height", "poster_key",
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    origem: Mapped[ConteudoOrigem] = mapped_column(
        Enum(ConteudoOrigem, name="conteudo_origem"), nullable=False
    )
    corte_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cortes.id"), unique=True
    )
    titulo: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # ---- só `video_proprio` ----
    video_key: Mapped[str | None] = mapped_column(Text, unique=True)
    video_content_type: Mapped[str | None] = mapped_column(Text)
    video_bytes: Mapped[int | None] = mapped_column(BigInteger)
    video_sha256: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    poster_key: Mapped[str | None] = mapped_column(Text)  # bucket `sociman` (imgproxy)


Index("ix_conteudos_perfil_created", Conteudo.perfil_id, Conteudo.created_at.desc(),
      Conteudo.id.desc())
Index("ix_conteudos_created", Conteudo.created_at.desc(), Conteudo.id.desc())
