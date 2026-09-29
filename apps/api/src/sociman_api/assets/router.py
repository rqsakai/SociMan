"""Rotas de um asset (contracts/http-api.md da 007, "Asset"): dono e membro (`RequireUser`),
menos a reversão (`RequireOwner`). Não existe rota DELETE (FR-007, SC-004)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile

from sociman_api.assets import schemas
from sociman_api.assets import service as svc
from sociman_api.assets.models import FileRole
from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList

router = APIRouter(prefix="/api/assets")

Db = DbSession
Upload = Annotated[UploadFile, File(description="PNG, JPG ou WebP até 20 MB")]
OptText = Annotated[str | None, Form(max_length=600)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _out(db, asset) -> schemas.AssetOut:
    return schemas.AssetOut(asset=svc.asset_out(db, asset))


def _blank(value: str | None) -> str | None:
    value = value.strip() if value is not None else None
    return value or None


@router.get("/{asset_id}", operation_id="assets_get", response_model=schemas.AssetDetail,
            responses=_errors(401, 403, 404))
def get(asset_id: UUID, actor: RequireUser, db: Db) -> schemas.AssetDetail:
    return svc.get_asset(db, asset_id)


@router.patch("/{asset_id}", operation_id="assets_update", response_model=schemas.AssetOut,
              responses=_errors(400, 401, 403, 404, 409))
def update(asset_id: UUID, body: schemas.AssetPatch, actor: RequireUser,
           db: Db) -> schemas.AssetOut:
    return _out(db, svc.update_asset(db, actor, asset_id, body))


@router.post("/{asset_id}/arquivos", operation_id="assets_file_upload", status_code=201,
             response_model=schemas.AssetFileOut,
             responses=_errors(400, 401, 403, 404, 409, 503, 507))
def upload_file(
    asset_id: UUID, file: Upload, actor: RequireUser, db: Db,
    role: Annotated[FileRole, Form()],
    look: OptText = None, uso: OptText = None, label: OptText = None,
    quando_usar: Annotated[str | None, Form(alias="quandoUsar", max_length=600)] = None,
    notes: OptText = None,
) -> schemas.AssetFileOut:
    raw = {"look": look, "uso": uso, "label": label, "quando_usar": quando_usar,
           "notes": notes}
    limits = {"look": 60, "uso": 200, "label": 60, "quando_usar": 300, "notes": 500}
    meta = {k: _blank(v) for k, v in raw.items()}
    for field, value in meta.items():
        if value is not None and len(value) > limits[field]:
            camel = "quandoUsar" if field == "quando_usar" else field
            raise schemas.invalid(camel, f"até {limits[field]} caracteres")
    asset, f = svc.upload_file(db, actor, asset_id, file.file, role, meta)
    out = svc.asset_out(db, asset)
    return schemas.AssetFileOut(asset=out, file=svc.file_out(out, f.id))


@router.patch("/{asset_id}/arquivos/{file_id}", operation_id="assets_file_update",
              response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def update_file(asset_id: UUID, file_id: UUID, body: schemas.FilePatch, actor: RequireUser,
                db: Db) -> schemas.AssetOut:
    return _out(db, svc.update_file(db, actor, asset_id, file_id, body))


@router.put("/{asset_id}/ordem", operation_id="assets_reorder",
            response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def reorder(asset_id: UUID, body: schemas.Ordem, actor: RequireUser,
            db: Db) -> schemas.AssetOut:
    return _out(db, svc.reorder(db, actor, asset_id, body))


@router.post("/{asset_id}/arquivos/{file_id}/archive", operation_id="assets_file_archive",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def archive_file(asset_id: UUID, file_id: UUID, body: VersionIn, actor: RequireUser,
                 db: Db) -> schemas.AssetOut:
    return _out(db, svc.archive_file(db, actor, asset_id, file_id, body.version))


@router.post("/{asset_id}/arquivos/{file_id}/restore", operation_id="assets_file_restore",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def restore_file(asset_id: UUID, file_id: UUID, body: VersionIn, actor: RequireUser,
                 db: Db) -> schemas.AssetOut:
    return _out(db, svc.restore_file(db, actor, asset_id, file_id, body.version))


@router.post("/{asset_id}/archive", operation_id="assets_archive",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def archive(asset_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> schemas.AssetOut:
    return _out(db, svc.archive_asset(db, actor, asset_id, body.version))


@router.post("/{asset_id}/restore", operation_id="assets_restore",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def restore(asset_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> schemas.AssetOut:
    return _out(db, svc.restore_asset(db, actor, asset_id, body.version))


@router.get("/{asset_id}/versions", operation_id="assets_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def versions(asset_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return svc.asset_versions(db, asset_id)


@router.post("/{asset_id}/revert", operation_id="assets_revert",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def revert(asset_id: UUID, body: RevertIn, actor: RequireOwner, db: Db) -> schemas.AssetOut:
    return _out(db, svc.revert_asset(db, actor, asset_id, body.version, body.to_version))
