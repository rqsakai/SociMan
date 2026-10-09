"""Notificações in-app (data-model.md da spec 006, R11).

Uma linha por destinatário. `dedupe_key` é única por usuário: um reinício no meio de uma
trilha não duplica o aviso. Nunca são apagadas: marcar como lida só preenche `lida_em`.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.db import Base


class NotificacaoTipo(enum.StrEnum):
    envio_pronto = "envio_pronto"
    envio_sem_clipes = "envio_sem_clipes"
    envio_falhou = "envio_falhou"
    envio_confirmar_qualidade = "envio_confirmar_qualidade"
    envio_momentos = "envio_momentos"  # 0007: momentos escolhidos, um por rodada
    openshorts_fora = "openshorts_fora"
    hora_de_postar = "hora_de_postar"
    cota_youtube = "cota_youtube"
    canal_erro = "canal_erro"
    aprovacao_pedida = "aprovacao_pedida"  # 0009: para os donos ativos (spec 014)
    aprovacao_respondida = "aprovacao_respondida"  # 0009: para quem pediu
    # 0010 (spec 015): execução na rede, para os donos ativos.
    rascunho_criado = "rascunho_criado"
    envio_publicado = "envio_publicado"
    envio_rede_falhou = "envio_rede_falhou"
    envio_aguardando_vaga = "envio_aguardando_vaga"
    conexao_precisa_reconectar = "conexao_precisa_reconectar"
    # 0011 (spec 016): vínculo do post, para os donos ativos (dedupe por destino).
    post_detectado = "post_detectado"
    vinculo_a_confirmar = "vinculo_a_confirmar"
    # 0025 (spec 026): coleta de mercado, para os donos ativos (dedupe por tipo e dia local).
    coleta_captcha = "coleta_captcha"
    coleta_login = "coleta_login"
    coleta_bloqueio = "coleta_bloqueio"
    coleta_layout = "coleta_layout"
    coleta_parada = "coleta_parada"
    mercado_interesse_auto = "mercado_interesse_auto"


class Notificacao(Base):
    __tablename__ = "notificacoes"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notificacoes_user_dedupe"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    tipo: Mapped[NotificacaoTipo] = mapped_column(
        Enum(NotificacaoTipo, name="notificacao_tipo"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    corpo: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    link: Mapped[str] = mapped_column(Text, nullable=False)  # rota do SPA
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_notificacoes_user_id_desc", Notificacao.user_id, Notificacao.id.desc())
Index("ix_notificacoes_user_nao_lidas", Notificacao.user_id,
      postgresql_where=text("lida_em IS NULL"))
