"""Séries, vídeos, fotos e buscas de post (data-model.md da spec 016).

As tabelas `metricas_*` são **observações da rede**, escritas pela trilha `metricas`
(`system:metricas`) e, no vínculo manual, pelas rotas **H**. Não têm `version`/`history`
próprios (exceção do princípio VII no plan): o histórico do vínculo fica no destino
(`entity_type = "postagem"`) e o da anonimização, na conexão (`entity_type = "conexao"`).

- `metricas_series`: as métricas de uma conta numa rede enquanto ela está conectada; anonimizar
  encerra a série (`conta_id` nulo, `rotulo = "Conta anônima N"`), e reconectar cria outra;
- `metricas_videos`: um post público da série (id da rede como **texto**, pode passar de 2^53);
- `metricas_video_fotos` e `metricas_conta_fotos`: **só inserção** (trigger
  `metricas_so_insercao` na migration 0011; `INSERT … ON CONFLICT DO NOTHING` por janela);
- `metricas_buscas_post`: o nível 1 do vínculo, uma linha por destino `criar_rascunho` entregue.
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
    Identity,
    Index,
    Integer,
    Sequence,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.db import Base
from sociman_api.perfis.models import Platform
from sociman_api.postagem import models as _postagem_models  # noqa: F401 — FK para postagens
from sociman_api.publicacao import models as _publicacao_models  # noqa: F401 — FK tentativas


class VinculoMetodo(enum.StrEnum):
    envio = "envio"  # post id do `status/fetch` ou do post direto da 015
    casamento = "casamento"  # lista: data, duração e legenda
    link = "link"  # link colado pelo dono
    escolha = "escolha"  # o dono escolheu um candidato


FINS_BUSCA = ("vinculado", "prazo", "falhou", "desfeito", "anonimizada", "cancelada")
FONTES_FOTO = ("display", "business")  # `business` fica reservado para a etapa 2

anonima_seq = Sequence("metricas_anonima_seq", metadata=Base.metadata)


class Serie(Base):
    __tablename__ = "metricas_series"
    __table_args__ = (
        CheckConstraint(
            "((anonimizada_em IS NULL) = (conta_id IS NOT NULL)) AND (anonimizada_em IS NULL "
            "OR (rotulo IS NOT NULL AND anonima_n IS NOT NULL))",
            name="ck_metricas_series_anonima"),
        Index("uq_metricas_series_conta_viva", "conta_id", unique=True,
              postgresql_where=text("anonimizada_em IS NULL")),
        Index("ix_metricas_series_ativas", "lista_proxima_em",
              postgresql_where=text("anonimizada_em IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rede: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    conta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contas.id"))
    rotulo: Mapped[str | None] = mapped_column(Text)
    anonima_n: Mapped[int | None] = mapped_column(Integer)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                server_default=func.now())
    varredura_cursor: Mapped[int | None] = mapped_column(BigInteger)  # ms (R5)
    varredura_concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lista_proxima_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conta_proxima_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_coleta_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_erro_codigo: Mapped[str | None] = mapped_column(Text)
    ultimo_erro_motivo: Mapped[str | None] = mapped_column(Text)  # pt-BR
    ultimo_erro_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adiar_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sem_permissao_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonimizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonimizada_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class VideoRede(Base):
    __tablename__ = "metricas_videos"
    __table_args__ = (
        CheckConstraint(
            "((destino_id IS NULL) = (vinculo_metodo IS NULL)) "
            "AND (destino_id IS NULL OR vinculado_em IS NOT NULL)",
            name="ck_metricas_videos_vinculo"),
        CheckConstraint(
            "anonimizado_em IS NULL OR (rede_video_id IS NULL AND share_url IS NULL "
            "AND legenda IS NULL AND titulo IS NULL AND destino_id IS NULL "
            "AND vinculado_por IS NULL AND proxima_coleta_em IS NULL AND features IS NOT NULL)",
            name="ck_metricas_videos_anonimo"),
        CheckConstraint("disponivel OR indisponivel_desde IS NOT NULL",
                        name="ck_metricas_videos_indisponivel"),
        Index("uq_metricas_videos_rede_id", "serie_id", "rede_video_id", unique=True,
              postgresql_where=text("rede_video_id IS NOT NULL")),
        Index("uq_metricas_videos_destino", "destino_id", unique=True,
              postgresql_where=text("destino_id IS NOT NULL")),
        Index("ix_metricas_videos_fila", "proxima_coleta_em",
              postgresql_where=text("proxima_coleta_em IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    serie_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("metricas_series.id"),
                                                nullable=False)
    rede_video_id: Mapped[str | None] = mapped_column(Text)
    share_url: Mapped[str | None] = mapped_column(Text)
    legenda: Mapped[str | None] = mapped_column(Text)
    titulo: Mapped[str | None] = mapped_column(Text)
    duracao_s: Mapped[int] = mapped_column(Integer, nullable=False)
    largura: Mapped[int | None] = mapped_column(Integer)
    altura: Mapped[int | None] = mapped_column(Integer)
    publicado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    descoberto_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                    server_default=func.now())
    disponivel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                             server_default=text("true"))
    indisponivel_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proxima_coleta_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_foto_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    destino_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("postagens.id"))
    vinculo_metodo: Mapped[VinculoMetodo | None] = mapped_column(
        Enum(VinculoMetodo, name="vinculo_metodo"))
    vinculado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    vinculado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vinculo_automatico: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                                     server_default=text("true"))
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # congeladas (R13)
    anonimizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_metricas_videos_serie_pub", VideoRede.serie_id, VideoRede.publicado_em.desc(),
      VideoRede.id.desc())


class FotoVideo(Base):
    """Só inserção (trigger `metricas_so_insercao`)."""

    __tablename__ = "metricas_video_fotos"
    __table_args__ = (
        UniqueConstraint("video_id", "alvo_idade_min", name="uq_metricas_video_fotos_janela"),
        CheckConstraint("idade_s >= 0 AND alvo_idade_min >= 0",
                        name="ck_metricas_video_fotos_idade"),
        CheckConstraint("fonte IN ('display','business')", name="ck_metricas_video_fotos_fonte"),
        Index("ix_metricas_video_fotos_idade", "video_id", "idade_s"),
        Index("ix_metricas_video_fotos_coletado", "coletado_em"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    video_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("metricas_videos.id"),
                                                nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idade_s: Mapped[int] = mapped_column(Integer, nullable=False)
    alvo_idade_min: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL quando a TikTok omite o campo; gravados como vieram, inclusive quando caem.
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    fonte: Mapped[str] = mapped_column(Text, nullable=False, default="display",
                                       server_default="display")


class FotoConta(Base):
    """Só inserção (trigger `metricas_so_insercao`)."""

    __tablename__ = "metricas_conta_fotos"
    __table_args__ = (
        UniqueConstraint("serie_id", "janela_em", name="uq_metricas_conta_fotos_janela"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    serie_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("metricas_series.id"),
                                                nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    janela_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    seguidores: Mapped[int | None] = mapped_column(BigInteger)
    seguindo: Mapped[int | None] = mapped_column(BigInteger)
    curtidas: Mapped[int | None] = mapped_column(BigInteger)
    videos: Mapped[int | None] = mapped_column(BigInteger)  # só os públicos


class BuscaPost(Base):
    __tablename__ = "metricas_buscas_post"
    __table_args__ = (
        CheckConstraint(
            "((encerrada_em IS NULL) = (fim IS NULL)) "
            "AND (encerrada_em IS NULL OR proxima_em IS NULL)",
            name="ck_metricas_buscas_fim"),
        CheckConstraint(
            "fim IS NULL OR fim IN "
            "('vinculado','prazo','falhou','desfeito','anonimizada','cancelada')",
            name="ck_metricas_buscas_fim_valor"),
        Index("ix_metricas_buscas_fila", "proxima_em",
              postgresql_where=text("encerrada_em IS NULL")),
    )

    destino_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("postagens.id"),
                                                  primary_key=True)
    # A tentativa `entregue` (o `publish_id` fica lá e não é copiado).
    tentativa_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("publicacao_tentativas.id"), nullable=False)
    entregue_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    proxima_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consultas: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                           server_default=text("0"))
    ultimo_status: Mapped[str | None] = mapped_column(Text)
    post_id: Mapped[str | None] = mapped_column(Text)  # `publicaly_available_post_id`
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fim: Mapped[str | None] = mapped_column(Text)  # ver FINS_BUSCA
