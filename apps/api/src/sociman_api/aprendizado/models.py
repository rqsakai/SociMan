"""Tabelas do aprendizado (data-model.md da spec 023, migration `0018_aprendizado`).

- `aprendizado_temas` (`entity_type = "aprendizado_tema"`): a taxonomia do perfil; arquivar e
  juntar em vez de apagar;
- `aprendizado_classificacoes` (`aprendizado_classificacao`): tema, secundários e gancho de um
  post (016). `origem = dono` nunca é sobrescrita pela IA;
- `aprendizado_preferencias` (`aprendizado_preferencias`): uma linha do perfil (`conta_id IS
  NULL`) e no máximo uma por conta; sem linha = `version 0`;
- `aprendizado_analises` (`aprendizado_analise`): o pedido de análise da IA, imutável depois de
  `pronta`/`erro` (exceção do princípio VII no plan);
- `aprendizado_decisoes` (`aprendizado_decisao`): o aceite ou a rejeição de uma recomendação (as
  recomendações por regra são calculadas na leitura) e as abertas nascidas de hipótese;
- `aprendizado_conferencias` (`aprendizado_conferencia`): o checklist do diagnóstico marcado pelo
  dono.

Nada é apagado.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.ia import models as _ia_models  # noqa: F401 — FK ia_chamadas
from sociman_api.metricas import models as _metricas_models  # noqa: F401 — FK metricas_videos
from sociman_api.perfis.models import _Versioned

CHECKLIST_ITENS = ("restrito", "nao_elegivel_para_voce", "nao_original", "privacidade", "musica",
                   "diretrizes")


class Origem(enum.StrEnum):
    ia = "ia"
    dono = "dono"


class EstiloGancho(enum.StrEnum):
    pergunta = "pergunta"
    revelacao = "revelacao"
    numero_lista = "numero_lista"
    polemica = "polemica"
    humor = "humor"
    voce_sabia = "voce_sabia"
    ordem_direta = "ordem_direta"
    outro = "outro"


class AnaliseEstado(enum.StrEnum):
    pendente = "pendente"
    processando = "processando"
    pronta = "pronta"
    erro = "erro"


class DecisaoEstado(enum.StrEnum):
    aberta = "aberta"  # só de hipótese
    aceita = "aceita"
    rejeitada = "rejeitada"


class ConferenciaResultado(enum.StrEnum):
    ok = "ok"
    problema = "problema"
    nao_sei = "nao_sei"


def _lista() -> Mapped[list[str]]:
    return mapped_column(ARRAY(Text), nullable=False, default=list, server_default=text("'{}'"))


def _version() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, default=1, server_default=text("1"))


class Tema(_Versioned, AuditMixin, Base):
    __tablename__ = "aprendizado_temas"
    __table_args__ = (
        CheckConstraint("char_length(nome) BETWEEN 1 AND 40", name="ck_aprendizado_temas_nome"),
        CheckConstraint("char_length(descricao) <= 200", name="ck_aprendizado_temas_descricao"),
        CheckConstraint("cardinality(palavras_chave) <= 20",
                        name="ck_aprendizado_temas_palavras"),
        CheckConstraint("juntado_em_id IS NULL OR archived_at IS NOT NULL",
                        name="ck_aprendizado_temas_juntado"),
        CheckConstraint("juntado_em_id IS NULL OR juntado_em_id <> id",
                        name="ck_aprendizado_temas_juntado_outro"),
        Index("uq_aprendizado_temas_nome", "perfil_id", "nome_norm", unique=True,
              postgresql_where=text("archived_at IS NULL")),
    )
    __versioned_fields__ = ("nome", "descricao", "palavras_chave", "archived", "juntado_em_id")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    nome_norm: Mapped[str] = mapped_column(Text, nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    palavras_chave: Mapped[list[str]] = _lista()
    juntado_em_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("aprendizado_temas.id"))


class Classificacao(AuditMixin, Base):
    __tablename__ = "aprendizado_classificacoes"
    __table_args__ = (
        CheckConstraint("cardinality(secundarios) <= 2",
                        name="ck_aprendizado_classificacoes_secundarios"),
        CheckConstraint("tema_id IS NULL OR NOT (tema_id = ANY(secundarios))",
                        name="ck_aprendizado_classificacoes_secundario_principal"),
        CheckConstraint("justificativa IS NULL OR char_length(justificativa) <= 160",
                        name="ck_aprendizado_classificacoes_justificativa"),
        CheckConstraint("sugestao_tema IS NULL OR char_length(sugestao_tema) <= 40",
                        name="ck_aprendizado_classificacoes_sugestao"),
        UniqueConstraint("video_id", name="uq_aprendizado_classificacoes_video"),
        Index("ix_aprendizado_classificacoes_tema", "perfil_id", "tema_id"),
        Index("ix_aprendizado_classificacoes_reclassificar", "perfil_id",
              postgresql_where=text("reclassificar")),
    )
    __versioned_fields__ = ("tema_id", "secundarios", "estilo_gancho", "origem", "reclassificar")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("metricas_videos.id"),
                                                nullable=False)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    tema_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("aprendizado_temas.id"))
    secundarios: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), nullable=False, default=list, server_default=text("'{}'"))
    estilo_gancho: Mapped[EstiloGancho | None] = mapped_column(
        Enum(EstiloGancho, name="aprendizado_estilo_gancho"))
    justificativa: Mapped[str | None] = mapped_column(Text)
    sugestao_tema: Mapped[str | None] = mapped_column(Text)
    origem: Mapped[Origem] = mapped_column(Enum(Origem, name="aprendizado_origem"),
                                           nullable=False)
    evidencia_parcial: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reclassificar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                server_default=text("false"))
    taxonomia_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    chamada_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("ia_chamadas.id"))
    version: Mapped[int] = _version()


class Preferencias(AuditMixin, Base):
    __tablename__ = "aprendizado_preferencias"
    __table_args__ = (
        CheckConstraint("cardinality(hashtags_evitar) <= 30",
                        name="ck_aprendizado_preferencias_evitar"),
        CheckConstraint("jsonb_array_length(padroes) <= 10",
                        name="ck_aprendizado_preferencias_padroes"),
        Index("uq_aprendizado_preferencias_perfil", "perfil_id", unique=True,
              postgresql_where=text("conta_id IS NULL")),
        Index("uq_aprendizado_preferencias_conta", "conta_id", unique=True,
              postgresql_where=text("conta_id IS NOT NULL")),
    )
    # `taxonomia_versao`, `pedido_classificacao_em` e `fonte_temas_*` são contadores técnicos
    # (fora do snapshot).
    __versioned_fields__ = ("temas", "hashtags_evitar", "padroes", "classificacao_auto",
                            "usar_desempenho")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    conta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contas.id"))
    temas: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict,
                                                  server_default=text("'{}'::jsonb"))
    hashtags_evitar: Mapped[list[str]] = _lista()
    padroes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    taxonomia_versao: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                                  server_default=text("0"))
    classificacao_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                                     server_default=text("true"))
    usar_desempenho: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                                  server_default=text("true"))
    pedido_classificacao_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Plano B do R9 (migration 0019): a taxonomia já casada com os vídeos-fonte e até quando.
    fonte_temas_versao: Mapped[int | None] = mapped_column(Integer)
    fonte_temas_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = _version()


class Analise(Base):
    __tablename__ = "aprendizado_analises"
    __table_args__ = (
        CheckConstraint("n BETWEEN 1 AND 15", name="ck_aprendizado_analises_n"),
        CheckConstraint("medida IN ('h1', 'h24', 'd7')", name="ck_aprendizado_analises_medida"),
        CheckConstraint("quadros_por_video IN (0, 4) AND (com_quadros = (quadros_por_video = 4))",
                        name="ck_aprendizado_analises_quadros"),
        CheckConstraint("(estado = 'erro') = (erro_code IS NOT NULL)",
                        name="ck_aprendizado_analises_erro"),
        Index("ix_aprendizado_analises_perfil", "perfil_id", text("created_at DESC")),
        Index("ix_aprendizado_analises_fila", "estado", "created_at",
              postgresql_where=text("estado IN ('pendente', 'processando')")),
    )
    __versioned_fields__ = ("estado", "hipoteses", "erro_code", "chamada_id",
                            "videos_sem_arquivo")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    conta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contas.id"))
    estado: Mapped[AnaliseEstado] = mapped_column(
        Enum(AnaliseEstado, name="aprendizado_analise_estado"), nullable=False)
    medida: Mapped[str] = mapped_column(Text, nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    com_quadros: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quadros_por_video: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                                   server_default=text("0"))
    videos_sem_arquivo: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                                    server_default=text("0"))
    melhores: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    comparaveis: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    resumo_estatistico: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    hipoteses: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    custo_estimado_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    chamada_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("ia_chamadas.id"))
    erro_code: Mapped[str | None] = mapped_column(Text)
    taxonomia_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    pedido_por: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=func.now())
    iniciada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = _version()


class Decisao(AuditMixin, Base):
    __tablename__ = "aprendizado_decisoes"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('tema_ampliar', 'tema_cortar', 'hashtag_fixar', 'hashtag_evitar', "
            "'padrao_gancho', 'padrao_duracao', 'padrao_horario')",
            name="ck_aprendizado_decisoes_tipo"),
        CheckConstraint("origem IN ('regra', 'hipotese')", name="ck_aprendizado_decisoes_origem"),
        CheckConstraint("(origem = 'hipotese') = (analise_id IS NOT NULL)",
                        name="ck_aprendizado_decisoes_hipotese"),
        CheckConstraint("estado <> 'aberta' OR origem = 'hipotese'",
                        name="ck_aprendizado_decisoes_aberta"),
        CheckConstraint("texto IS NULL OR char_length(texto) <= 120",
                        name="ck_aprendizado_decisoes_texto"),
        CheckConstraint("motivo IS NULL OR char_length(motivo) <= 300",
                        name="ck_aprendizado_decisoes_motivo"),
        Index("ix_aprendizado_decisoes_chave", "perfil_id", "chave", text("decidido_em DESC")),
    )
    __versioned_fields__ = ("estado", "motivo", "texto", "preferencias_version", "revertida")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    conta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contas.id"))
    chave: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    origem: Mapped[str] = mapped_column(Text, nullable=False)
    analise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("aprendizado_analises.id"))
    estado: Mapped[DecisaoEstado] = mapped_column(
        Enum(DecisaoEstado, name="aprendizado_decisao"), nullable=False)
    evidencia: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    n_decisao: Mapped[int] = mapped_column(Integer, nullable=False)
    faixa_decisao: Mapped[str] = mapped_column(Text, nullable=False)
    texto: Mapped[str | None] = mapped_column(Text)
    motivo: Mapped[str | None] = mapped_column(Text)
    preferencias_version: Mapped[int | None] = mapped_column(Integer)
    decidido_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Reverter um aceite desfaz a preferência criada por ele; a linha fica, marcada.
    revertida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revertida_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    version: Mapped[int] = _version()

    @property
    def revertida(self) -> bool:
        return self.revertida_em is not None


class Conferencia(AuditMixin, Base):
    __tablename__ = "aprendizado_conferencias"
    __table_args__ = (
        CheckConstraint("item IN (" + ", ".join(f"'{i}'" for i in CHECKLIST_ITENS) + ")",
                        name="ck_aprendizado_conferencias_item"),
        CheckConstraint("nota IS NULL OR char_length(nota) <= 300",
                        name="ck_aprendizado_conferencias_nota"),
        UniqueConstraint("video_id", "item", name="uq_aprendizado_conferencias_video_item"),
    )
    __versioned_fields__ = ("resultado", "nota")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("metricas_videos.id"),
                                                nullable=False)
    item: Mapped[str] = mapped_column(Text, nullable=False)
    resultado: Mapped[ConferenciaResultado] = mapped_column(
        Enum(ConferenciaResultado, name="aprendizado_conferencia_resultado"), nullable=False)
    nota: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = _version()
