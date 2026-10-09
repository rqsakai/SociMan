"""Rotas do AI Studio (spec 029, contracts/http-api.md): o resumo da biblioteca da agência, para o
card "Ver no AI Studio" do perfil. Só leitura, dono e membro (`RequireUser`)."""

from fastapi import APIRouter
from sqlalchemy import func, select

from sociman_api.assets.models import Asset, AssetTipo
from sociman_api.auth.deps import RequireUser
from sociman_api.cenas.models import Cena
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.estudio import schemas
from sociman_api.estudio.filtros import PerfilFiltro, filtro
from sociman_api.perfis import base as perfil_base
from sociman_api.produtos.models import Produto
from sociman_api.vozes.models import Voz

router = APIRouter(prefix="/api/estudio")

# Os tipos do item "Assets" do menu; avatares e cenários têm item próprio (Clarification 2).
TIPOS_ASSETS = (AssetTipo.imagem, AssetTipo.sticker, AssetTipo.marca_dagua, AssetTipo.fundo)


def _contar(db, modelo, f: perfil_base.Filtro, *where) -> int:
    stmt = select(func.count()).select_from(modelo).where(modelo.archived_at.is_(None), *where)
    return db.scalar(perfil_base.aplicar_filtro(stmt, modelo.perfil_id, f)) or 0


@router.get("/resumo", operation_id="estudio_resumo", response_model=schemas.EstudioResumo,
            responses={s: {"model": ErrorEnvelope} for s in (400, 401, 403)})
def resumo(actor: RequireUser, db: DbSession,
           perfil_id: PerfilFiltro = None) -> schemas.EstudioResumo:
    f = filtro(db, perfil_id)
    por_tipo = dict(db.execute(perfil_base.aplicar_filtro(
        select(Asset.tipo, func.count()).where(Asset.archived_at.is_(None))
        .group_by(Asset.tipo), Asset.perfil_id, f)).all())
    return schemas.EstudioResumo(
        avatares=por_tipo.get(AssetTipo.avatar, 0),
        cenarios=por_tipo.get(AssetTipo.cenario, 0),
        assets=sum(por_tipo.get(t, 0) for t in TIPOS_ASSETS),
        cenas=_contar(db, Cena, f),
        produtos=_contar(db, Produto, f),
        vozes=_contar(db, Voz, f),
    )
