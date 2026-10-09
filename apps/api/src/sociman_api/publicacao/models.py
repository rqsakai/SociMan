"""Conexões, credenciais, interruptor e tentativas de envio (data-model.md da spec 015).

- `conexoes`: uma conexão viva por conta TikTok, só dados **não secretos**, com histórico
  (`entity_type = "conexao"`). Desconectar é o fim (nunca arquivada na 015); reconectar de
  `precisa_reconectar` reusa a linha, e depois de desconectar cria outra.
- `conexao_credenciais`: os tokens cifrados (R4), **fora do histórico** e de qualquer schema de
  saída. A linha é apagada ao desconectar e ao virar `precisa_reconectar` (a única exclusão
  física da 015). Leitura só por `publicacao/conexoes.py::token_valido`, com `FOR UPDATE`.
- `publicacao_config`: o botão "Envios automáticos" (singleton `id = 1`, histórico
  `entity_type = "publicacao_config"`). O nível do servidor (`PUBLICACAO_HABILITADA`) não fica no
  banco.
- `publicacao_tentativas`: uma linha por execução de envio de um destino, escrita só pela trilha
  e por `publicacao/service.py` (tentar de novo). Cada passo é gravado **antes** da chamada à
  rede (R8); linhas em fase final não mudam mais.
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
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.conteudos.models import Modo
from sociman_api.db import Base
from sociman_api.perfis.models import Platform, _Versioned
from sociman_api.postagem import models as _postagem_models  # noqa: F401 — FK para postagens


class ConexaoEstado(enum.StrEnum):
    conectada = "conectada"
    precisa_reconectar = "precisa_reconectar"
    desconectada = "desconectada"


class TentativaFase(enum.StrEnum):
    """Fases de uma tentativa (R7). As três primeiras são abertas; as demais, finais."""

    iniciando = "iniciando"
    enviando_partes = "enviando_partes"
    processando = "processando"
    entregue = "entregue"
    publicada = "publicada"
    recusada = "recusada"
    incerta = "incerta"
    sem_vaga = "sem_vaga"


FASES_ABERTAS = (TentativaFase.iniciando, TentativaFase.enviando_partes,
                 TentativaFase.processando)
# Contam no limite de 5 rascunhos em 24 h (R10, Clarifications Q1 = A).
FASES_OCUPAM_VAGA = FASES_ABERTAS + (TentativaFase.entregue, TentativaFase.incerta)
DISPAROS = ("agendador", "tentar_de_novo", "confirmado")

_SQL_ABERTAS = "fase IN ('iniciando','enviando_partes','processando')"


class Conexao(_Versioned, AuditMixin, Base):
    __tablename__ = "conexoes"
    __table_args__ = (
        CheckConstraint("estado <> 'desconectada' OR (desconectado_em IS NOT NULL)",
                        name="ck_conexoes_desconectada"),
        Index("uq_conexoes_conta_viva", "conta_id", unique=True,
              postgresql_where=text("estado <> 'desconectada'")),
        Index("uq_conexoes_open_id_vivo", "rede", "open_id", unique=True,
              postgresql_where=text("estado <> 'desconectada'")),
    )
    __versioned_fields__ = (
        "open_id", "username", "display_name", "escopos", "estado", "motivo", "conectado_por",
        "desconectado_por",
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conta_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contas.id"), nullable=False)
    rede: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    open_id: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)  # sem `@`
    display_name: Mapped[str] = mapped_column(Text, nullable=False, default="",
                                              server_default="")
    avatar_key: Mapped[str | None] = mapped_column(Text)  # bucket `imagens`
    escopos: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    estado: Mapped[ConexaoEstado] = mapped_column(
        Enum(ConexaoEstado, name="conexao_estado"), nullable=False
    )
    motivo: Mapped[str | None] = mapped_column(Text)
    conectado_por: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"),
                                                     nullable=False)
    conectado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    desconectado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    desconectado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avisado_vencimento_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConexaoCredencial(Base):
    """Segredo, não dado de domínio: sem `__versioned_fields__` e sem schema de saída."""

    __tablename__ = "conexao_credenciais"

    conexao_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conexoes.id"),
                                                  primary_key=True)
    key_id: Mapped[str] = mapped_column(Text, nullable=False)
    access_cifrado: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    access_expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_cifrado: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    renovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    renovacoes: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                            server_default=text("0"))


class PublicacaoConfig(AuditMixin, Base):
    __tablename__ = "publicacao_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_publicacao_config_unica"),)
    __versioned_fields__ = ("envios_habilitados",)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    envios_habilitados: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                     server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))


class Tentativa(Base):
    __tablename__ = "publicacao_tentativas"
    __table_args__ = (
        UniqueConstraint("destino_id", "numero", name="uq_tentativas_destino_numero"),
        UniqueConstraint("publish_id", name="uq_tentativas_publish_id"),
        CheckConstraint(
            "fase NOT IN ('enviando_partes','processando','entregue','publicada') "
            "OR publish_id IS NOT NULL",
            name="ck_tentativas_publish_id",
        ),
        CheckConstraint(f"{_SQL_ABERTAS} OR concluida_em IS NOT NULL",
                        name="ck_tentativas_final"),
        CheckConstraint("partes_enviadas BETWEEN 0 AND total_partes",
                        name="ck_tentativas_partes"),
        CheckConstraint("disparo IN ('agendador','tentar_de_novo','confirmado')",
                        name="ck_tentativas_disparo"),
        Index("uq_tentativas_destino_aberta", "destino_id", unique=True,
              postgresql_where=text(_SQL_ABERTAS)),
        Index("ix_tentativas_abertas", "proxima_em", postgresql_where=text(_SQL_ABERTAS)),
        Index("ix_tentativas_conexao_init", "conexao_id", "init_enviado_em",
              postgresql_where=text("modo = 'criar_rascunho' AND init_enviado_em IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    destino_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("postagens.id"),
                                                  nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    conexao_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conexoes.id"),
                                                  nullable=False)
    rede: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    modo: Mapped[Modo] = mapped_column(Enum(Modo, name="agendamento_modo"), nullable=False)
    fase: Mapped[TentativaFase] = mapped_column(
        Enum(TentativaFase, name="tentativa_fase"), nullable=False
    )
    disparo: Mapped[str] = mapped_column(Text, nullable=False)  # ver DISPAROS
    disparado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    video_ref: Mapped[str] = mapped_column(Text, nullable=False)
    video_etag: Mapped[str] = mapped_column(Text, nullable=False)
    video_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    video_sha256: Mapped[str | None] = mapped_column(Text)
    chunk_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_partes: Mapped[int] = mapped_column(Integer, nullable=False)
    partes_enviadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                                 server_default=text("0"))
    init_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_id: Mapped[str | None] = mapped_column(Text)
    # Leva o `upload_token`: cifrado (AAD "{id}:upload") e apagado ao sair de `enviando_partes`.
    upload_url_cifrado: Mapped[bytes | None] = mapped_column(LargeBinary)
    upload_url_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_rede: Mapped[str | None] = mapped_column(Text)
    codigo_rede: Mapped[str | None] = mapped_column(Text)
    motivo: Mapped[str | None] = mapped_column(Text)  # pt-BR (R19)
    rede_post_id: Mapped[str | None] = mapped_column(Text)
    proxima_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    iniciada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=func.now())
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )  # nunca tokens


Index("ix_tentativas_destino", Tentativa.destino_id, Tentativa.numero.desc())
