"""Regras por tipo de campo e registro das chamadas (data-model.md da spec 008).

- `ia_regras`: a personalização das regras de um tipo. Sem linha = usa o padrão do código (a
  linha nasce na primeira edição, como o kit com `version = 0`). Entidade versionada
  (`entity_type = "ia_regra"`), sem arquivamento: "voltar ao padrão" grava `texto = NULL`.
- `ia_chamadas` (a `sugestoes_texto` da 006 renomeada, com os mesmos ids): log de cada geração.
  Só INSERT, salvo as colunas de desfecho, que são estado sem versão (R10).
- `ia_guias` (spec 017): o guia de comunicação do perfil (`conta_id IS NULL`) e o de cada conta.
  Sem linha = sem guia (a linha nasce na primeira edição); sem arquivamento e sem DELETE
  ("limpar" é salvar vazio). Entidade versionada (`entity_type = "ia_guia"`).
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
from sociman_api.conteudos import models as _conteudos_models  # noqa: F401 — FK (spec 014)
from sociman_api.db import Base
from sociman_api.perfis.models import Platform

REGRAS_MAX = 8000

# Spec 017 (data-model): os CHECKs baratos; os limites por item e o total ficam em `ia/guia.py`.
GUIA_TOM_MAX = 500
GUIA_REGRAS_ITENS = 10
GUIA_VOCABULARIO_ITENS = 30
GUIA_PROIBIDAS_ITENS = 30
GUIA_EMOJIS_ITENS = 10
GUIA_FIXAS_PERFIL = 5
GUIA_FIXAS_TETO = 8  # = postagem.textos.HASHTAGS_MAX
GUIA_EXEMPLOS = 5


class IaDesfecho(enum.StrEnum):
    sem_acao = "sem_acao"
    aplicada = "aplicada"
    editada = "editada"
    descartada = "descartada"
    erro = "erro"


class GuiaEmojis(enum.StrEnum):
    nao = "nao"
    moderado = "moderado"
    livre = "livre"


class IaRegra(AuditMixin, Base):
    """Sem `archived_at`: a linha nunca some ("voltar ao padrão" é o equivalente)."""

    __tablename__ = "ia_regras"
    __table_args__ = (
        CheckConstraint(f"texto IS NULL OR char_length(texto) BETWEEN 1 AND {REGRAS_MAX}",
                        name="ck_ia_regras_texto"),
        UniqueConstraint("tipo_campo", name="uq_ia_regras_tipo_campo"),
    )
    __versioned_fields__ = ("tipo_campo", "texto")
    __immutable_fields__ = ("tipo_campo",)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo_campo: Mapped[str] = mapped_column(Text, nullable=False)
    texto: Mapped[str | None] = mapped_column(Text)  # NULL = usa o padrão do código
    padrao_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


def _lista() -> Mapped[list[str]]:
    return mapped_column(ARRAY(Text), nullable=False, default=list, server_default=text("'{}'"))


class IaGuia(AuditMixin, Base):
    """Guia de comunicação (spec 017). O par (conta, perfil da conta) é garantido pelo service:
    o `perfil_id` do guia da conta vem sempre da conta carregada, nunca do cliente."""

    __tablename__ = "ia_guias"
    __table_args__ = (
        CheckConstraint(f"char_length(tom) <= {GUIA_TOM_MAX}", name="ck_ia_guias_tom"),
        CheckConstraint(f"cardinality(faca) <= {GUIA_REGRAS_ITENS}", name="ck_ia_guias_faca"),
        CheckConstraint(f"cardinality(nao_faca) <= {GUIA_REGRAS_ITENS}",
                        name="ck_ia_guias_nao_faca"),
        CheckConstraint(f"cardinality(vocabulario) <= {GUIA_VOCABULARIO_ITENS}",
                        name="ck_ia_guias_vocabulario"),
        CheckConstraint(f"cardinality(proibidas) <= {GUIA_PROIBIDAS_ITENS}",
                        name="ck_ia_guias_proibidas"),
        CheckConstraint(f"cardinality(emojis_preferidos) <= {GUIA_EMOJIS_ITENS}",
                        name="ck_ia_guias_emojis_preferidos"),
        CheckConstraint(f"cardinality(hashtags_fixas) <= {GUIA_FIXAS_TETO} AND (conta_id IS NOT "
                        f"NULL OR cardinality(hashtags_fixas) <= {GUIA_FIXAS_PERFIL})",
                        name="ck_ia_guias_hashtags_fixas"),
        CheckConstraint("max_hashtags_fixas IS NULL OR (conta_id IS NOT NULL AND "
                        f"max_hashtags_fixas BETWEEN 0 AND {GUIA_FIXAS_TETO})",
                        name="ck_ia_guias_max_hashtags_fixas"),
        CheckConstraint(f"jsonb_array_length(exemplos) <= {GUIA_EXEMPLOS}",
                        name="ck_ia_guias_exemplos"),
        Index("uq_ia_guias_perfil", "perfil_id", unique=True,
              postgresql_where=text("conta_id IS NULL")),
        Index("uq_ia_guias_conta", "conta_id", unique=True,
              postgresql_where=text("conta_id IS NOT NULL")),
    )
    __versioned_fields__ = ("perfil_id", "conta_id", "tom", "faca", "nao_faca", "vocabulario",
                            "proibidas", "emojis", "emojis_preferidos", "hashtags_fixas",
                            "max_hashtags_fixas", "exemplos")
    __immutable_fields__ = ("perfil_id", "conta_id")

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    conta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contas.id"))
    tom: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    faca: Mapped[list[str]] = _lista()
    nao_faca: Mapped[list[str]] = _lista()
    vocabulario: Mapped[list[str]] = _lista()
    proibidas: Mapped[list[str]] = _lista()
    emojis: Mapped[GuiaEmojis | None] = mapped_column(Enum(GuiaEmojis, name="guia_emojis"))
    emojis_preferidos: Mapped[list[str]] = _lista()
    hashtags_fixas: Mapped[list[str]] = _lista()  # já normalizadas (`#…`)
    max_hashtags_fixas: Mapped[int | None] = mapped_column(Integer)  # só na conta; NULL = 5
    exemplos: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )  # [{"tipo": "titulo"|"legenda"|"bordao", "texto": str}]
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class IaChamada(Base):
    """Uma geração (com proposta ou erro), com o contexto enviado, o custo e o desfecho."""

    __tablename__ = "ia_chamadas"
    __table_args__ = (
        CheckConstraint("(erro_code IS NOT NULL) = (desfecho = 'erro')",
                        name="ck_ia_chamadas_erro_desfecho"),
        CheckConstraint("guia_rascunho IS NULL OR guia_rascunho IN ('perfil', 'conta')",
                        name="ck_ia_chamadas_guia_rascunho"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo_campo: Mapped[str] = mapped_column(Text, nullable=False)
    perfil_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("perfis.id"), nullable=False)
    # asset|perfil|kit|postagem|corte|conteudo|guia (017: `guia` no montar, id = linha do guia)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # null no kit nunca salvo
    corte_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("cortes.id"))
    # Spec 014: preenchida em toda chamada `postagem.*` (na origem corte, = corte_id).
    conteudo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conteudos.id"))
    conta_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contas.id"))
    plataforma: Mapped[Platform | None] = mapped_column(Enum(Platform, name="platform"))
    sessao_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    anteriores: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), nullable=False, default=list, server_default=text("'{}'")
    )
    aceitos: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    rejeitados: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    instrucao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    entrada: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    contexto_faltante: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    proposta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # null quando deu erro
    explicacao: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    avisos: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    excede: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ajustes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_servido: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)  # ia/1 (006: textos/1)
    regras_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    padrao_versao: Mapped[int | None] = mapped_column(Integer)
    erro_code: Mapped[str | None] = mapped_column(Text)  # unconfigured|timeout|refusal|invalid|api_error
    erro_status: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_creation_tokens: Mapped[int | None] = mapped_column(Integer)
    custo_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    precos_versao: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    desfecho: Mapped[IaDesfecho] = mapped_column(
        Enum(IaDesfecho, name="ia_desfecho"), nullable=False, default=IaDesfecho.sem_acao,
        server_default=IaDesfecho.sem_acao.value,
    )
    desfecho_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desfecho_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    aplicada_versao: Mapped[int | None] = mapped_column(Integer)
    itens_aplicados: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    # Spec 017 (R8): versões dos guias enviados (NULL = nada enviado); `guia_rascunho` só no
    # `guia.testar` (o nível que veio do formulário); `proibidas` encontradas na proposta final.
    guia_perfil_version: Mapped[int | None] = mapped_column(Integer)
    guia_conta_version: Mapped[int | None] = mapped_column(Integer)
    guia_rascunho: Mapped[str | None] = mapped_column(Text)
    proibidas: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


Index("ix_ia_chamadas_created", IaChamada.created_at.desc(), IaChamada.id)
Index("ix_ia_chamadas_perfil_created", IaChamada.perfil_id, IaChamada.created_at.desc())
Index("ix_ia_chamadas_tipo_created", IaChamada.tipo_campo, IaChamada.created_at.desc())
Index("ix_ia_chamadas_conteudo", IaChamada.conteudo_id, IaChamada.created_at.desc())
Index("ix_ia_chamadas_sessao", IaChamada.sessao_id,
      postgresql_where=text("sessao_id IS NOT NULL"))
