"""Infra do dono e eventos da coleta (data-model.md da spec 026).

- `coleta_clientes`: o token do coletor (= `mcp_clientes` com prefixo `scol_`), só o SHA-256 no
  banco, versionado (`entity_type = "coleta_cliente"`); revogar é final;
- `coleta_config`: linha única com o botão da tela, o aceite de risco (quem, quando), janela,
  tetos e pausas (`entity_type = "coleta_config"`). O CHECK `ck_coleta_config_risco` impede
  `habilitada` sem aceite no próprio banco;
- `coleta_eventos`: **só inserção** (trigger `mercado_so_insercao`): captcha, login perdido,
  bloqueio, layout, parada local, retomada, início e fim de rodada. `detalhe` nunca leva PII.
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
    LargeBinary,
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
from sociman_api.mercado import models as _mercado  # noqa: F401 — FKs para a fila e as rodadas
from sociman_api.mercado.models import MERCADO_CHECK
from sociman_api.perfis.models import Platform

CONFIG_ID = 1


class ColetaSituacao(enum.StrEnum):
    ativo = "ativo"
    suspenso = "suspenso"
    revogado = "revogado"  # final


class EventoTipo(enum.StrEnum):
    captcha = "captcha"
    login_perdido = "login_perdido"
    bloqueio_suspeito = "bloqueio_suspeito"
    layout_mudou = "layout_mudou"
    parar_local = "parar_local"
    retomou = "retomou"
    iniciado = "iniciado"
    parado = "parado"


EVENTOS_QUE_NOTIFICAM = (EventoTipo.captcha, EventoTipo.login_perdido,
                         EventoTipo.bloqueio_suspeito, EventoTipo.layout_mudou)


class ColetaCliente(AuditMixin, Base):
    __tablename__ = "coleta_clientes"
    __table_args__ = (
        CheckConstraint("char_length(nome) BETWEEN 1 AND 60", name="ck_coleta_clientes_nome"),
        CheckConstraint("char_length(descricao) <= 300", name="ck_coleta_clientes_descricao"),
        CheckConstraint(MERCADO_CHECK, name="ck_coleta_clientes_mercado"),
        CheckConstraint("limite_por_minuto BETWEEN 1 AND 600",
                        name="ck_coleta_clientes_limite_min"),
    )
    # O hash nunca entra no histórico; o `token_id` entra para a rotação aparecer no diff.
    __versioned_fields__ = ("nome", "descricao", "rede", "mercado", "situacao", "expira_em",
                            "limite_por_minuto", "token_id")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    nome_normalizado: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    rede: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False,
                                           default=Platform.tiktok,
                                           server_default=Platform.tiktok.value)
    mercado: Mapped[str] = mapped_column(Text, nullable=False)
    situacao: Mapped[ColetaSituacao] = mapped_column(
        Enum(ColetaSituacao, name="coleta_situacao"), nullable=False,
        default=ColetaSituacao.ativo, server_default=ColetaSituacao.ativo.value)
    token_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_emitido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    limite_por_minuto: Mapped[int] = mapped_column(Integer, nullable=False, default=120,
                                                   server_default=text("120"))
    ultimo_contato_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    versao_coletor: Mapped[str | None] = mapped_column(Text)
    chrome_versao: Mapped[str | None] = mapped_column(Text)
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))

    def __repr__(self) -> str:  # nunca expõe o hash
        return f"ColetaCliente(id={self.id}, nome={self.nome!r}, token_id={self.token_id!r})"

    __str__ = __repr__


class ColetaConfig(AuditMixin, Base):
    __tablename__ = "coleta_config"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_coleta_config_unica"),
        CheckConstraint("NOT habilitada OR risco_aceito_em IS NOT NULL",
                        name="ck_coleta_config_risco"),
        CheckConstraint("janela_inicio BETWEEN 0 AND 23 AND janela_fim BETWEEN 0 AND 23 "
                        "AND janela_inicio < janela_fim", name="ck_coleta_config_janela"),
        CheckConstraint("paginas_dia BETWEEN 1 AND 2000", name="ck_coleta_config_paginas"),
        CheckConstraint("imagens_dia BETWEEN 0 AND 20000", name="ck_coleta_config_imagens"),
        CheckConstraint("imagens_por_produto BETWEEN 0 AND 20",
                        name="ck_coleta_config_imagens_produto"),
        CheckConstraint("itens_por_coleta BETWEEN 1 AND 50", name="ck_coleta_config_itens"),
        CheckConstraint("1 <= pausa_min_s AND pausa_min_s <= pausa_max_s AND pausa_max_s <= 600",
                        name="ck_coleta_config_pausas"),
    )
    __versioned_fields__ = ("habilitada", "risco_aceito_em", "risco_aceito_por",
                            "risco_texto_versao", "janela_inicio", "janela_fim", "paginas_dia",
                            "imagens_dia", "imagens_por_produto", "itens_por_coleta",
                            "pausa_min_s", "pausa_max_s", "pausada_ate", "continuar_em")

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=CONFIG_ID)
    habilitada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                             server_default=text("false"))
    risco_aceito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risco_aceito_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    risco_texto_versao: Mapped[str | None] = mapped_column(Text)
    janela_inicio: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=8,
                                               server_default=text("8"))
    janela_fim: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=23,
                                            server_default=text("23"))
    paginas_dia: Mapped[int] = mapped_column(Integer, nullable=False, default=300,
                                             server_default=text("300"))
    imagens_dia: Mapped[int] = mapped_column(Integer, nullable=False, default=1500,
                                             server_default=text("1500"))
    imagens_por_produto: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=9,
                                                     server_default=text("9"))
    itens_por_coleta: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=40,
                                                  server_default=text("40"))
    pausa_min_s: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5,
                                             server_default=text("5"))
    pausa_max_s: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=40,
                                             server_default=text("40"))
    pausada_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    continuar_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))


class Evento(Base):
    """`coleta_eventos`: só inserção (trigger)."""

    __tablename__ = "coleta_eventos"
    __table_args__ = (
        Index("ix_coleta_eventos_recentes", text("recebido_em DESC")),
        Index("ix_coleta_eventos_coleta", "coleta_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    tipo: Mapped[EventoTipo] = mapped_column(Enum(EventoTipo, name="coleta_evento_tipo"),
                                             nullable=False)
    cliente_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("coleta_clientes.id"),
                                                  nullable=False)
    coleta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_coletas.id"))
    tarefa_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("mercado_fila.id"))
    detalhe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict,
                                                    server_default=text("'{}'::jsonb"))
    ocorreu_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recebido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=func.now())
    notificacao_dedupe: Mapped[str | None] = mapped_column(Text)
