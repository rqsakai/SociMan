"""Produtos do TikTok Shop (data-model.md da spec 012, research R1, R2 e R4).

- `produtos`: o produto do perfil, com a ficha técnica (pelo Claude ou à mão) e o estado do
  cadastro (`entity_type = "produto"`). O estado `arquivado` é **efetivo** (`archived_at`), não
  está no enum: restaurar volta ao status de antes (R4);
- `produto_variantes`: uma por foto/cor, com a foto original (intocada), o recorte (do
  `produto.recorte`) e o flat (a opção escolhida do `produto.flat`, com a geração de origem).
  Sem `version` própria: toda mudança numa variante é uma versão do produto (como os
  `asset_files` da 007), pela propriedade `variantes` do snapshot.

Os campos em inglês (`material_en`, `formato_corte`, `detalhes_visiveis`, `tamanho_relativo`,
`descricao_prompt`, `cor_en`) são guardados exatamente como vieram (sem trim): vão literais para
os prompts (R2). Nada é apagado: produtos e variantes são arquivados.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sociman_api.auth.models import AuditMixin
from sociman_api.db import Base
from sociman_api.geracao import models as _geracao_models  # noqa: F401 — FK para geracoes
from sociman_api.perfis.models import _Versioned

ENTITY = "produto"
MAX_VARIANTES = 6


class ProdutoStatus(enum.StrEnum):
    rascunho = "rascunho"
    gerando = "gerando"
    revisao = "revisao"
    aprovado = "aprovado"


class ProdutoFichaPor(enum.StrEnum):
    ia = "ia"
    ia_editada = "ia_editada"
    humano = "humano"


# Os campos da ficha, na ordem do contrato (a `FichaSaida` e o `PUT …/ficha` usam os mesmos).
CAMPOS_FICHA = ("nome_comercial", "categoria", "material_en", "material_pt", "formato_corte",
                "detalhes_visiveis", "tamanho_relativo", "descricao_prompt", "cuidados",
                "descricao_venda", "precisa_flat")
CAMPOS_EN = ("material_en", "formato_corte", "detalhes_visiveis", "tamanho_relativo",
             "descricao_prompt")


class Produto(_Versioned, AuditMixin, Base):
    __tablename__ = "produtos"
    __table_args__ = (
        CheckConstraint("ficha_por IS NULL OR precisa_flat IS NOT NULL",
                        name="ck_produtos_ficha"),
    )
    __versioned_fields__ = (
        "perfil_id", "name", *CAMPOS_FICHA, "obs", "url_loja", "status", "ficha_por",
        "archived", "variantes",
    )
    __immutable_fields__ = ()  # 029: o perfil base é editável

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("perfis.id"))  # 029: opcional
    name: Mapped[str] = mapped_column(Text, nullable=False)
    nome_comercial: Mapped[str | None] = mapped_column(Text)
    categoria: Mapped[str | None] = mapped_column(Text)
    material_en: Mapped[str | None] = mapped_column(Text)
    material_pt: Mapped[str | None] = mapped_column(Text)
    formato_corte: Mapped[str | None] = mapped_column(Text)
    detalhes_visiveis: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'"))
    tamanho_relativo: Mapped[str | None] = mapped_column(Text)
    descricao_prompt: Mapped[str | None] = mapped_column(Text)
    cuidados: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'"))
    descricao_venda: Mapped[str | None] = mapped_column(Text)
    precisa_flat: Mapped[bool | None] = mapped_column(Boolean)
    obs: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    url_loja: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProdutoStatus] = mapped_column(
        Enum(ProdutoStatus, name="produto_status"), nullable=False,
        default=ProdutoStatus.rascunho, server_default="rascunho")
    ficha_por: Mapped[ProdutoFichaPor | None] = mapped_column(
        Enum(ProdutoFichaPor, name="produto_ficha_por"))

    # Classes da 012 por referência direta (lambda): a 026 tem outro `Produto` (mercado_produtos)
    # no mesmo registro, e o nome em texto ficaria ambíguo.
    variantes_rel: Mapped[list["ProdutoVariante"]] = relationship(
        primaryjoin=lambda: Produto.id == ProdutoVariante.produto_id,
        foreign_keys=lambda: [ProdutoVariante.produto_id], lazy="selectin",
    )

    @property
    def variantes(self) -> list[dict[str, Any]]:
        """As variantes do snapshot: ativas pela ordem, depois as arquivadas."""
        return [
            {"id": v.id, "position": v.position, "cor_en": v.cor_en, "cor_pt": v.cor_pt,
             "original_image_id": v.original_image_id, "recorte_image_id": v.recorte_image_id,
             "flat_image_id": v.flat_image_id, "flat_geracao_id": v.flat_geracao_id,
             "archived": v.archived}
            for v in ordenadas(self.variantes_rel)
        ]

    def ativas(self) -> list["ProdutoVariante"]:
        return [v for v in ordenadas(self.variantes_rel) if not v.archived]

    def variante(self, variante_id: uuid.UUID) -> "ProdutoVariante | None":
        return next((v for v in self.variantes_rel if v.id == variante_id), None)

    @property
    def tem_ficha(self) -> bool:
        return self.ficha_por is not None

    @property
    def estado(self) -> str:
        """O estado efetivo (R4): `arquivado` ou o status."""
        return "arquivado" if self.archived else self.status.value


Index("ix_produtos_lista_agencia", Produto.archived_at, Produto.updated_at.desc(), Produto.id)  # 029
Index("ix_produtos_perfil_lista", Produto.perfil_id, Produto.archived_at,
      Produto.updated_at.desc(), Produto.id)
Index("ix_produtos_perfil_status", Produto.perfil_id, Produto.status,
      postgresql_where=text("archived_at IS NULL"))
Index("ix_produtos_perfil_lower_name", Produto.perfil_id, func.lower(Produto.name))
Index("ix_produtos_perfil_lower_nome_comercial", Produto.perfil_id,
      func.lower(Produto.nome_comercial))


class ProdutoVariante(Base):
    """Sem `version` própria: toda mudança aqui é uma versão do produto."""

    __tablename__ = "produto_variantes"
    __table_args__ = (
        CheckConstraint("(flat_image_id IS NULL) = (flat_geracao_id IS NULL)",
                        name="ck_variantes_flat"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    produto_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("produtos.id"),
                                                  nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cor_en: Mapped[str | None] = mapped_column(Text)
    cor_pt: Mapped[str | None] = mapped_column(Text)
    original_image_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("images.id"), nullable=False, unique=True)
    recorte_image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("images.id"))
    flat_image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("images.id"))
    flat_geracao_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("geracoes.id"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))

    @property
    def archived(self) -> bool:
        return self.archived_at is not None


Index("ix_produto_variantes_produto", ProdutoVariante.produto_id, ProdutoVariante.archived_at,
      ProdutoVariante.position)


def ordenadas(variantes: list[ProdutoVariante]) -> list[ProdutoVariante]:
    """Ativas pela `position`, depois as arquivadas (pela `position` que tinham)."""
    return sorted(variantes, key=lambda v: (v.archived, v.position, str(v.id)))
