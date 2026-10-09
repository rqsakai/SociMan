"""Rotas da biblioteca do perfil (contracts/http-api.md da 007, "Biblioteca do perfil"): dono e
membro (`RequireUser`). Não existe rota DELETE (FR-007, SC-004)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile

from sociman_api.assets import busca, schemas
from sociman_api.assets import service as svc
from sociman_api.assets.models import AssetTipo
from sociman_api.auth.deps import RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope

router = APIRouter(prefix="/api/perfis")

Db = DbSession
Upload = Annotated[UploadFile, File(description="PNG, JPG ou WebP até 20 MB")]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/{perfil_id}/assets", operation_id="assets_list", response_model=schemas.AssetsList,
            responses=_errors(400, 401, 403, 404))
def list_(
    perfil_id: UUID, actor: RequireUser, db: Db,
    tipo: Annotated[list[AssetTipo] | None, Query(description="Tipos (OU)")] = None,
    tag: Annotated[list[str] | None, Query(description="Tags (E)")] = None,
    q: Annotated[str | None, Query(max_length=100, description="Nome contém ou tag igual")]
    = None,
    archived: Annotated[schemas.ArchivedFilter, Query()] = "false",
    limit: Annotated[int, Query(ge=1, le=busca.MAX_LIMIT)] = busca.DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> schemas.AssetsList:
    return busca.list_assets(db, perfil_id, tipos=tipo or (), tags=tag or (), q=q,
                             archived=archived, limit=limit, cursor=cursor)


@router.post("/{perfil_id}/assets", operation_id="assets_create", status_code=201,
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def create(perfil_id: UUID, body: schemas.AssetCreate, actor: RequireUser,
           db: Db) -> schemas.AssetOut:
    asset = svc.create_asset(db, actor, perfil_id, body)
    return schemas.AssetOut(asset=svc.asset_out(db, asset))


@router.post("/{perfil_id}/assets/arquivo", operation_id="assets_upload", status_code=201,
             response_model=schemas.AssetFileOut,
             responses=_errors(400, 401, 403, 404, 409, 503, 507))
def upload(
    perfil_id: UUID, file: Upload, actor: RequireUser, db: Db,
    tipo: Annotated[AssetTipo, Form(description="fundo, sticker, marca_dagua ou imagem")],
    name: Annotated[str | None, Form(max_length=200)] = None,
    tags: Annotated[str | None, Form(max_length=1000, description="Separadas por vírgula")]
    = None,
) -> schemas.AssetFileOut:
    name_ = (name or "").strip() or svc.default_name(file.filename)
    if len(name_) > 80:
        raise schemas.invalid("name", "até 80 caracteres")
    try:
        tag_list = schemas.normalize_tags([t for t in (tags or "").split(",") if t.strip()])
    except ValueError as exc:
        raise schemas.invalid("tags", str(exc)) from exc
    asset, f = svc.upload_asset(db, actor, perfil_id, file.file, tipo, name_, tag_list)
    out = svc.asset_out(db, asset)
    return schemas.AssetFileOut(asset=out, file=svc.file_out(out, f.id))


@router.get("/{perfil_id}/assets/imagens", operation_id="assets_images",
            response_model=schemas.LibraryImagesList, responses=_errors(400, 401, 403, 404))
def images(
    perfil_id: UUID, actor: RequireUser, db: Db,
    tipo: Annotated[list[AssetTipo], Query(description="Tipos (OU), obrigatório")],
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=busca.MAX_LIMIT)] = 60,
) -> schemas.LibraryImagesList:
    return schemas.LibraryImagesList(items=svc.library_images(db, perfil_id, tipo, q, limit))
