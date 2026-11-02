"""Roteiros com vídeo local (data-model.md da spec 011, research R1, R6, R10, R12 e R15).

- `roteiros`: brief, produtos, avatar e voz que viram um vídeo voice over (`entity_type =
  "roteiro"`). O status é a máquina de `roteiros/maquina.py`; só as ações humanas (e a escolha
  automática do `system:roteiro`) versionam. Os campos que a máquina muda sozinha (`etapa_falhou`,
  `erro_*`, `avisos`, `comandado_por`, os ponteiros de etapa e o `conteudo_id`) são estado de job,
  fora do snapshot;
- `roteiro_produtos` e `roteiro_cenas` (as posições): sem versão própria, são as propriedades
  `produtos` e `posicoes` do snapshot do roteiro. `inicio_s`, `duracao_s` e `aviso` da posição
  são técnicos (derivados da narração ativa);
- `roteiro_narracoes`: cada take contínuo, imutável salvo `desuso_em`/`limpa_em` (R12); a ativa é
  `roteiros.narracao_id`, e "desatualizada" é derivada do `texto_hash` (R10);
- `roteiro_entregas`: só inserção (trigger), o registro do "usado num vídeo final" (R12, R13);
- `roteiro_padroes`: modo e portões padrão do perfil (`entity_type = "roteiro_padroes"`); sem
  linha = padrão do código, `version 0`;
- `pronuncias`: o dicionário de pronúncia do perfil (`entity_type = "pronuncia"`), arquivável.

Spec 031 (vídeo guiado, data-model): o roteiro guiado tem `tipo_video`, `cenario_id` e a grade
com que nasceu (`duracao_alvo_s`, `trecho_base_s`; as 4 juntas ou nenhuma, `ck_roteiros_guiado`).
Nulas = roteiro da 011, que segue igual. A posição do guiado ganha `trechos` (1 a 3), o `reuso`,
o `motivo`, as aprovações por posição e o orçamento de fala; a tomada de cada trecho fica em
`roteiro_trechos` (no snapshot de `posicoes`, só nas posições do guiado). A `roteiro_conversa` é o
chat (só inserção, trigger).

Nada é apagado nas invalidações: só se marca `desuso_em`. A limpeza de 90 dias (exceção 1 da
4.5.0) é a única que remove mídia, e a linha fica com `limpa_em`.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    and_,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sociman_api.auth.models import AuditMixin
from sociman_api.cenas import models as _cenas_models  # noqa: F401 — FKs cenas e tomadas
from sociman_api.conteudos import models as _conteudos_models  # noqa: F401 — FK conteudos
from sociman_api.db import Base
from sociman_api.geracao import models as _geracao_models  # noqa: F401 — FKs geracoes/audios
from sociman_api.ia import models as _ia_models  # noqa: F401 — FK ia_chamadas (031)
from sociman_api.perfis.models import _Versioned
from sociman_api.produtos import models as _produtos_models  # noqa: F401 — FKs produtos
from sociman_api.vozes import models as _vozes_models  # noqa: F401 — FK vozes

ENTITY = "roteiro"
ENTITY_PADROES = "roteiro_padroes"
ENTITY_PRONUNCIA = "pronuncia"
ENTITY_TYPES = (ENTITY, ENTITY_PADROES, ENTITY_PRONUNCIA)

VELOCIDADE_PADRAO = Decimal("1.08")
MAX_FRASES = 60
MAX_PRODUTOS = 6
PORTOES = ("texto", "narracao", "keyframes", "clipes", "final")
PORTOES_PADRAO: dict[str, bool] = dict.fromkeys(PORTOES, True)


class RoteiroFormato(enum.StrEnum):
    voice_over = "voice_over"


class RoteiroModo(enum.StrEnum):
    revisar = "revisar"
    automatico = "automatico"


class RoteiroAcabamento(enum.StrEnum):
    """Decisão do dono (T059, 2026-10-15): o acabamento padrão é `leve` (lanczos para 1080×1920,
    24 fps e −14 LUFS, segundos, na linha ffmpeg); `hd` é o SeedVR2 por cena (~20 min por 15 s,
    na GPU), opcional e, no futuro, cobrado à parte."""

    leve = "leve"
    hd = "hd"


class RoteiroStatus(enum.StrEnum):
    rascunho = "rascunho"
    planejando = "planejando"
    aguardando_texto = "aguardando_texto"
    narrando = "narrando"
    aguardando_narracao = "aguardando_narracao"
    gerando_keyframes = "gerando_keyframes"
    aguardando_keyframes = "aguardando_keyframes"
    gerando_clipes = "gerando_clipes"
    aguardando_clipes = "aguardando_clipes"
    montando = "montando"
    aguardando_final = "aguardando_final"
    finalizando = "finalizando"
    pronto = "pronto"
    falhou = "falhou"


class RoteiroEtapa(enum.StrEnum):
    """A etapa em que o roteiro falhou (o "Tentar de novo" retoma dela, FR-011)."""

    plano = "plano"
    narracao = "narracao"
    keyframes = "keyframes"
    clipes = "clipes"
    montagem = "montagem"
    acabamento = "acabamento"


class RoteiroTipoVideo(enum.StrEnum):
    """Spec 031: o tipo do vídeo guiado (nulo = roteiro da 011)."""

    avatar_pov = "avatar_pov"


class ConversaEstado(enum.StrEnum):
    sem_perguntas = "sem_perguntas"
    perguntando = "perguntando"
    respondida = "respondida"


class ConversaTipo(enum.StrEnum):
    pergunta = "pergunta"
    resposta = "resposta"
    pedido_troca = "pedido_troca"
    esclarecimento = "esclarecimento"
    aviso = "aviso"


class PosicaoReuso(enum.StrEnum):
    """A decisão do modal de cenas (FR-019): a cena como está, só o plano dela ou uma nova."""

    total = "total"
    plano = "plano"
    nova = "nova"


class PosicaoAviso(enum.StrEnum):
    tomada_curta = "tomada_curta"
    cena_arquivada = "cena_arquivada"
    keyframe_pendente = "keyframe_pendente"
    consentimento_revogado = "consentimento_revogado"


class Roteiro(_Versioned, AuditMixin, Base):
    __tablename__ = "roteiros"
    __table_args__ = (
        CheckConstraint("velocidade BETWEEN 0.90 AND 1.20", name="ck_roteiros_velocidade"),
        CheckConstraint("(status = 'falhou') = (etapa_falhou IS NOT NULL)",
                        name="ck_roteiros_falhou"),
        CheckConstraint("status <> 'pronto' OR conteudo_id IS NOT NULL",
                        name="ck_roteiros_pronto"),
    )
    __versioned_fields__ = ("nome", "brief", "avatar_id", "voz_id", "formato", "frases",
                            "velocidade", "modo", "portoes", "status", "archived", "produtos",
                            "posicoes", "perfil_id",
                            # spec 031 (nulos na 011)
                            "tipo_video", "cenario_id", "duracao_alvo_s", "trecho_base_s",
                            "acabamento_modo")
    # A `duracao_alvo_s` muda dentro da grade guardada (FR-033): só a base é fixa. Imutável aqui =
    # o revert não volta o campo (o `PATCH` da duração confere a grade).
    __immutable_fields__ = ("perfil_id", "trecho_base_s")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    avatar_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id"))
    voz_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vozes.id"))
    formato: Mapped[RoteiroFormato] = mapped_column(
        Enum(RoteiroFormato, name="roteiro_formato"), nullable=False,
        default=RoteiroFormato.voice_over, server_default=RoteiroFormato.voice_over.value)
    frases: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list,
                                              server_default=text("'{}'"))
    velocidade: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False,
                                                default=VELOCIDADE_PADRAO,
                                                server_default=text("1.08"))
    modo: Mapped[RoteiroModo] = mapped_column(
        Enum(RoteiroModo, name="roteiro_modo"), nullable=False, default=RoteiroModo.revisar,
        server_default=RoteiroModo.revisar.value)
    portoes: Mapped[dict[str, bool]] = mapped_column(
        JSONB, nullable=False, default=lambda: dict(PORTOES_PADRAO))
    acabamento_modo: Mapped[RoteiroAcabamento] = mapped_column(
        Enum(RoteiroAcabamento, name="roteiro_acabamento"), nullable=False,
        default=RoteiroAcabamento.leve, server_default=RoteiroAcabamento.leve.value)
    status: Mapped[RoteiroStatus] = mapped_column(
        Enum(RoteiroStatus, name="roteiro_status"), nullable=False,
        default=RoteiroStatus.rascunho, server_default=RoteiroStatus.rascunho.value)
    # ---- técnicos (estado de job, fora do snapshot) ----
    etapa_falhou: Mapped[RoteiroEtapa | None] = mapped_column(
        Enum(RoteiroEtapa, name="roteiro_etapa"))
    erro_code: Mapped[str | None] = mapped_column(Text)
    erro_message: Mapped[str | None] = mapped_column(Text)
    avisos: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    # O último humano que deu um comando (R9): vira o `created_by` das gerações da máquina.
    comandado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    narracao_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("roteiro_narracoes.id", use_alter=True, name="fk_roteiros_narracao"))
    montagem_geracao_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                                  ForeignKey("geracoes.id"))
    acabamento_geracao_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                                    ForeignKey("geracoes.id"))
    conteudo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conteudos.id"))
    # ---- spec 031: o vídeo guiado (nulos = roteiro da 011) ----
    tipo_video: Mapped[RoteiroTipoVideo | None] = mapped_column(
        Enum(RoteiroTipoVideo, name="roteiro_tipo_video"))
    cenario_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id"))
    duracao_alvo_s: Mapped[int | None] = mapped_column(SmallInteger)
    trecho_base_s: Mapped[int | None] = mapped_column(SmallInteger)
    conversa_estado: Mapped[ConversaEstado | None] = mapped_column(  # técnico, fora do snapshot
        Enum(ConversaEstado, name="conversa_estado"))

    produtos_rel: Mapped[list["RoteiroProduto"]] = relationship(
        primaryjoin=lambda: Roteiro.id == RoteiroProduto.roteiro_id,
        foreign_keys=lambda: [RoteiroProduto.roteiro_id],
        order_by=lambda: RoteiroProduto.ordem, lazy="selectin",
        cascade="all, delete-orphan")
    posicoes_rel: Mapped[list["RoteiroCena"]] = relationship(
        primaryjoin=lambda: Roteiro.id == RoteiroCena.roteiro_id,
        foreign_keys=lambda: [RoteiroCena.roteiro_id],
        order_by=lambda: RoteiroCena.ordem, lazy="selectin",
        cascade="all, delete-orphan")

    @property
    def produtos(self) -> list[dict[str, Any]]:
        """Os produtos do snapshot, na ordem."""
        return [{"produto_id": p.produto_id, "produto_variante_id": p.produto_variante_id}
                for p in sorted(self.produtos_rel, key=lambda p: p.ordem)]

    @property
    def guiado(self) -> bool:
        """Spec 031: o roteiro nasceu no "Novo vídeo" guiado (tem a grade)."""
        return self.tipo_video is not None

    @property
    def posicoes(self) -> list[dict[str, Any]]:
        """As posições do snapshot (sem os campos técnicos derivados da narração). As do guiado
        levam também os trechos, o reuso, o motivo e a tomada de cada trecho; as da 011 ficam
        iguais (byte a byte)."""
        out = []
        for c in sorted(self.posicoes_rel, key=lambda c: c.ordem):
            item: dict[str, Any] = {"ordem": c.ordem, "cena_id": c.cena_id,
                                    "frases": list(c.frases), "tomada_id": c.tomada_id}
            if c.trechos is not None:
                item["trechos"] = c.trechos
                item["reuso"] = c.reuso.value if c.reuso else None
                item["motivo"] = c.motivo
                item["tomadas_trechos"] = [t.tomada_id for t in c.trechos_ordenados()]
                # As aprovações humanas por posição (R9, FR-037: antes e depois no histórico).
                item["aprovado_keyframes"] = c.aprovado_keyframes_em is not None
                item["aprovado_clipe"] = c.aprovado_clipe_em is not None
            out.append(item)
        return out


Index("ix_roteiros_perfil_lista", Roteiro.perfil_id, Roteiro.archived_at,
      Roteiro.updated_at.desc(), Roteiro.id)
Index("ix_roteiros_perfil_status", Roteiro.perfil_id, Roteiro.status,
      postgresql_where=text("archived_at IS NULL"))


class RoteiroProduto(Base):
    """Sem versão própria: é a propriedade `produtos` do roteiro."""

    __tablename__ = "roteiro_produtos"

    roteiro_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roteiros.id"),
                                                  primary_key=True)
    ordem: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("produtos.id"),
                                                  nullable=False)
    produto_variante_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("produto_variantes.id"))


class RoteiroCena(Base):
    """Uma posição: a cena (pode repetir), as frases contíguas que ela cobre e a tomada."""

    __tablename__ = "roteiro_cenas"

    roteiro_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roteiros.id"),
                                                  primary_key=True)
    ordem: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    cena_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cenas.id"), nullable=False)
    frases: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    # Técnicos: derivados da narração ativa (`tempos.limites`), nulos sem narração.
    inicio_s: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    duracao_s: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    tomada_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cena_tomadas.id"))
    aviso: Mapped[str | None] = mapped_column(Text)  # técnico: um `PosicaoAviso`
    # ---- spec 031: a posição do guiado (nulos na 011) ----
    trechos: Mapped[int | None] = mapped_column(SmallInteger)  # 1 a 3; duração = trechos × base
    reuso: Mapped[PosicaoReuso | None] = mapped_column(Enum(PosicaoReuso, name="posicao_reuso"))
    motivo: Mapped[str | None] = mapped_column(Text)
    # Técnicos (R9): zerados quando um quadro ou trecho da posição muda.
    aprovado_keyframes_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprovado_keyframes_por: Mapped[uuid.UUID | None] = mapped_column(Uuid,
                                                                     ForeignKey("users.id"))
    aprovado_clipe_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprovado_clipe_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    orcamento_chars: Mapped[int | None] = mapped_column(SmallInteger)

    trechos_rel: Mapped[list["RoteiroTrecho"]] = relationship(
        primaryjoin=lambda: and_(RoteiroCena.roteiro_id == RoteiroTrecho.roteiro_id,
                                 RoteiroCena.ordem == RoteiroTrecho.ordem),
        foreign_keys=lambda: [RoteiroTrecho.roteiro_id, RoteiroTrecho.ordem],
        order_by=lambda: RoteiroTrecho.trecho, lazy="selectin",
        cascade="all, delete-orphan")

    def trechos_ordenados(self) -> list["RoteiroTrecho"]:
        return sorted(self.trechos_rel, key=lambda t: t.trecho)

    def trecho(self, t: int) -> "RoteiroTrecho | None":
        return next((x for x in self.trechos_rel if x.trecho == t), None)


class RoteiroTrecho(Base):
    """Spec 031 (R8): a tomada escolhida de cada trecho de uma posição do guiado (nula = a gerar).
    Sem versão própria: entra no snapshot de `posicoes` do roteiro."""

    __tablename__ = "roteiro_trechos"
    __table_args__ = (
        ForeignKeyConstraint(["roteiro_id", "ordem"],
                             ["roteiro_cenas.roteiro_id", "roteiro_cenas.ordem"],
                             name="fk_roteiro_trechos_posicao"),
        CheckConstraint("trecho BETWEEN 0 AND 2", name="ck_roteiro_trechos_trecho"),
    )

    roteiro_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    ordem: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    trecho: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    tomada_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cena_tomadas.id"))


class RoteiroConversa(Base):
    """Spec 031: uma mensagem do chat do roteiro guiado. Só inserção (trigger
    `roteiro_conversa_so_insercao`); fica fora da revogação da 025 (data-model)."""

    __tablename__ = "roteiro_conversa"
    __table_args__ = (
        UniqueConstraint("roteiro_id", "seq", name="uq_roteiro_conversa_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    roteiro_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roteiros.id"),
                                                  nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[ConversaTipo] = mapped_column(Enum(ConversaTipo, name="conversa_tipo"),
                                               nullable=False)
    pergunta_id: Mapped[str | None] = mapped_column(Text)
    conteudo: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    alvo: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ia_chamada_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("ia_chamadas.id"))
    autor_tipo: Mapped[str] = mapped_column(Text, nullable=False)  # "user" | "system:roteiro"
    autor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class RoteiroNarracao(Base):
    """Imutável depois de criada, salvo `desuso_em`/`limpa_em` (técnicos, R12)."""

    __tablename__ = "roteiro_narracoes"
    __table_args__ = (
        CheckConstraint("audio_id IS NOT NULL OR limpa_em IS NOT NULL",
                        name="ck_narracoes_limpa"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    roteiro_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roteiros.id"),
                                                  nullable=False)
    geracao_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("geracoes.id"),
                                                  nullable=False)
    audio_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("audios.id"))
    voz_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vozes.id"), nullable=False)
    texto_hash: Mapped[str] = mapped_column(Text, nullable=False)
    frases: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    tempos: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    total_s: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    similaridade: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    velocidade: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    desuso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    limpa_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class RoteiroEntrega(Base):
    """Só inserção (trigger `roteiro_entregas_so_insercao`)."""

    __tablename__ = "roteiro_entregas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    roteiro_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roteiros.id"),
                                                  nullable=False)
    conteudo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conteudos.id"),
                                                   nullable=False, unique=True)
    narracao_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roteiro_narracoes.id"),
                                                   nullable=False)
    montagem_geracao_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("geracoes.id"),
                                                           nullable=False)
    acabamento_geracao_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("geracoes.id"),
                                                             nullable=False)
    # [{ordem, cenaId, tomadaId, keyframeImageId, motor, duracaoS}]
    posicoes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    motores: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class RoteiroPadroes(AuditMixin, Base):
    __tablename__ = "roteiro_padroes"
    __versioned_fields__ = ("modo", "portoes")

    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"),
                                                 primary_key=True)
    modo: Mapped[RoteiroModo] = mapped_column(Enum(RoteiroModo, name="roteiro_modo"),
                                              nullable=False)
    portoes: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                         server_default=text("1"))

    @property
    def id(self) -> uuid.UUID:  # o `history.record` usa `entity.id`
        return self.perfil_id


class Pronuncia(_Versioned, AuditMixin, Base):
    __tablename__ = "pronuncias"
    __versioned_fields__ = ("escrita", "falada", "archived", "perfil_id")
    __immutable_fields__ = ("perfil_id",)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    escrita: Mapped[str] = mapped_column(Text, nullable=False)
    falada: Mapped[str] = mapped_column(Text, nullable=False)


Index("uq_pronuncias_escrita", Pronuncia.perfil_id, func.lower(Pronuncia.escrita), unique=True,
      postgresql_where=text("archived_at IS NULL"))
Index("ix_pronuncias_perfil", Pronuncia.perfil_id, Pronuncia.archived_at, Pronuncia.escrita)
