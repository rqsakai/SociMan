"""Destinos: Postagem = destino, conteúdo × conta (data-model.md da spec 014, R2 e R3; a
origem é a postagem da 006).

A tabela, a classe e o `entity_type = "postagem"` ficam (histórico, IA e notificações já os
carregam); na API e na tela o recurso se chama **destino**. O agendamento são campos do destino
(`planned_at`, `modo`, `antecedencia_min`).

Princípio I (constitution 4.0.0): `postado` só é marcado pela rota humana; `enviando`,
`rascunho_criado`, `publicado` e `falhou` só pela trilha `publicacao` (spec 015), e só em modo
automático (`ck_postagens_execucao`). Modo automático em `agendado`/`enviando` exige a decisão
humana gravada (`ck_postagens_auto_decisao`), e `publicar` exige o snapshot do que o dono
confirmou (`ck_postagens_publicar_snapshot`). `rascunho_e_publicar` continua barrado no banco
(`ck_postagens_modo_015`). As chamadas ao Claude ficam em `ia_chamadas` (spec 008,
`ia/models.py`): `sugestao_id` continua apontando para os mesmos ids.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.conteudos.models import Modo
from sociman_api.db import Base
from sociman_api.ia import models as _ia_models  # noqa: F401 — FK para ia_chamadas
from sociman_api.perfis.models import _Versioned


class DestinoEstado(enum.StrEnum):
    """Estado gravado (R3). Os quatro últimos são da execução (spec 015, só modo automático)."""

    pendente = "pendente"
    aprovacao_pedida = "aprovacao_pedida"
    aprovado = "aprovado"
    agendado = "agendado"
    postado = "postado"
    rascunho_criado = "rascunho_criado"
    publicado = "publicado"
    falhou = "falhou"
    enviando = "enviando"  # 0010 (spec 015)


# Estados em que a aprovação precisa existir (`ck_postagens_aprovado`).
APROVADOS = (DestinoEstado.aprovado, DestinoEstado.agendado, DestinoEstado.postado,
             DestinoEstado.rascunho_criado, DestinoEstado.publicado, DestinoEstado.falhou,
             DestinoEstado.enviando)


class Postagem(_Versioned, AuditMixin, Base):
    __tablename__ = "postagens"
    __table_args__ = (
        CheckConstraint("char_length(titulo) <= 100", name="ck_postagens_titulo"),
        CheckConstraint("char_length(descricao) <= 2000", name="ck_postagens_descricao"),
        CheckConstraint("estado <> 'agendado' OR planned_at IS NOT NULL",
                        name="ck_postagens_agendado_planned"),
        CheckConstraint(
            "estado NOT IN ('aprovado','agendado','enviando','postado','rascunho_criado',"
            "'publicado','falhou') OR aprovado_em IS NOT NULL",
            name="ck_postagens_aprovado",
        ),
        CheckConstraint("estado <> 'aprovacao_pedida' OR pedido_em IS NOT NULL",
                        name="ck_postagens_pedido"),
        CheckConstraint(
            "antecedencia_min IS NULL OR (modo = 'rascunho_e_publicar' "
            "AND antecedencia_min BETWEEN 0 AND 10080)",
            name="ck_postagens_antecedencia",
        ),
        CheckConstraint(
            "(pedido_nota IS NULL OR char_length(pedido_nota) <= 500) AND "
            "(recusa_motivo IS NULL OR char_length(recusa_motivo) BETWEEN 1 AND 500)",
            name="ck_postagens_textos_nota",
        ),
        # Guardas do princípio I no banco (spec 015, R17; trocaram os da 014).
        CheckConstraint(
            "modo IN ('lembrete','criar_rascunho','publicar') AND antecedencia_min IS NULL",
            name="ck_postagens_modo_015",
        ),
        CheckConstraint(
            "estado NOT IN ('enviando','rascunho_criado','publicado','falhou') "
            "OR modo <> 'lembrete'",
            name="ck_postagens_execucao",
        ),
        CheckConstraint(
            "modo = 'lembrete' OR estado NOT IN ('agendado','enviando') "
            "OR (aprovado_por IS NOT NULL AND agendado_por IS NOT NULL)",
            name="ck_postagens_auto_decisao",
        ),
        CheckConstraint(
            "modo <> 'publicar' OR estado NOT IN ('agendado','enviando') "
            "OR (opcoes_rede IS NOT NULL AND envio_snapshot IS NOT NULL)",
            name="ck_postagens_publicar_snapshot",
        ),
        # Um destino ativo por conteúdo e conta (409 destino_exists).
        Index("uq_postagens_conteudo_conta_ativa", "conteudo_id", "conta_id", unique=True,
              postgresql_where=text("archived_at IS NULL")),
    )
    __versioned_fields__ = (
        "conta_id", "titulo", "descricao", "hashtags", "estado", "modo", "antecedencia_min",
        "planned_at", "posted_url", "aprovado_por", "aprovado_em", "pedido_nota",
        "recusa_motivo", "archived",
        # spec 015
        "agendado_por", "opcoes_rede", "envio_snapshot", "envio_confirmado_por", "falha_motivo",
        "rede_post_id",
    )
    # Informativos: a reversão os ignora.
    __immutable_fields__ = (
        "aprovado_video_ref", "pedido_por", "pedido_em", "recusado_por", "recusado_em",
        # spec 015
        "agendado_em", "envio_confirmado_em", "falha_incerta",
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conteudo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conteudos.id"), nullable=False
    )
    # Não muda depois de criado (a aprovação é por conta).
    conta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contas.id"), nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    hashtags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    estado: Mapped[DestinoEstado] = mapped_column(
        Enum(DestinoEstado, name="destino_estado"),
        nullable=False,
        default=DestinoEstado.pendente,
        server_default=DestinoEstado.pendente.value,
    )
    modo: Mapped[Modo] = mapped_column(
        Enum(Modo, name="agendamento_modo"),
        nullable=False,
        default=Modo.lembrete,
        server_default=Modo.lembrete.value,
    )
    antecedencia_min: Mapped[int | None] = mapped_column(SmallInteger)
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lembrado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_url: Mapped[str | None] = mapped_column(Text)
    falha_motivo: Mapped[str | None] = mapped_column(Text)  # preenchido pela trilha (015)
    sugestao_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ia_chamadas.id")
    )
    # ---- aprovação, pedido e recusa (R5) ----
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprovado_video_ref: Mapped[str | None] = mapped_column(Text)  # `videoMudou`
    pedido_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    pedido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pedido_nota: Mapped[str | None] = mapped_column(Text)
    recusado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    recusado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recusa_motivo: Mapped[str | None] = mapped_column(Text)
    # ---- execução na rede (spec 015) ----
    agendado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    agendado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    envio_confirmado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    envio_confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opcoes_rede: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # OpcoesTikTok (R13)
    # {legenda, opcoes, consentimento: {texto, aceitoEm}, videoRef}: o que o dono confirmou.
    envio_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    falha_incerta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                server_default=text("false"))
    rede_post_id: Mapped[str | None] = mapped_column(Text)


Index("ix_postagens_estado_planned", Postagem.estado, Postagem.planned_at)
Index("ix_postagens_conteudo", Postagem.conteudo_id)
Index("ix_postagens_conta_agenda", Postagem.conta_id, Postagem.planned_at,
      postgresql_where=text("archived_at IS NULL AND estado = 'agendado'"))
# Reivindicação da trilha `publicacao` (spec 015).
Index("ix_postagens_auto_vencidos", Postagem.planned_at,
      postgresql_where=text(
          "estado = 'agendado' AND modo <> 'lembrete' AND archived_at IS NULL"))
