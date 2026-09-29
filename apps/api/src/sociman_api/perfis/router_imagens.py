"""Rotas de logo e banner (T021, contracts/http-api.md "Perfis"): dono e membro (`RequireUser`).

Upload em `multipart/form-data` com `file` e `version`. Não existe rota de apagar imagem
(FR-010): `clear` só tira a referência do perfil.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile

from sociman_api.auth.deps import RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis import service_imagens as service
from sociman_api.perfis.models import ImageKind
from sociman_api.perfis.schemas import PerfilOut, VersionIn
from sociman_api.perfis.service_perfis import perfil_out

router = APIRouter(prefix="/api/perfis")

Db = DbSession
Upload = Annotated[UploadFile, File(description="PNG, JPG ou WebP até 5 MB")]
VersionField = Annotated[int, Form(ge=1)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _upload(db: Db, actor: RequireUser, perfil_id: UUID, kind: ImageKind, version: int,
            file: UploadFile) -> PerfilOut:
    perfil = service.upload_image(db, actor, perfil_id, kind, version, file.file)
    return PerfilOut(perfil=perfil_out(db, perfil))


def _clear(db: Db, actor: RequireUser, perfil_id: UUID, kind: ImageKind,
           version: int) -> PerfilOut:
    perfil = service.clear_image(db, actor, perfil_id, kind, version)
    return PerfilOut(perfil=perfil_out(db, perfil))


@router.put("/{perfil_id}/logo", operation_id="perfis_upload_logo", response_model=PerfilOut,
            responses=_errors(400, 401, 403, 404, 409))
def upload_logo(perfil_id: UUID, file: Upload, version: VersionField, actor: RequireUser,
                db: Db) -> PerfilOut:
    return _upload(db, actor, perfil_id, ImageKind.logo, version, file)


@router.put("/{perfil_id}/banner", operation_id="perfis_upload_banner",
            response_model=PerfilOut, responses=_errors(400, 401, 403, 404, 409))
def upload_banner(perfil_id: UUID, file: Upload, version: VersionField, actor: RequireUser,
                  db: Db) -> PerfilOut:
    return _upload(db, actor, perfil_id, ImageKind.banner, version, file)


@router.post("/{perfil_id}/logo/clear", operation_id="perfis_clear_logo",
             response_model=PerfilOut, responses=_errors(400, 401, 403, 404, 409))
def clear_logo(perfil_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> PerfilOut:
    return _clear(db, actor, perfil_id, ImageKind.logo, body.version)


@router.post("/{perfil_id}/banner/clear", operation_id="perfis_clear_banner",
             response_model=PerfilOut, responses=_errors(400, 401, 403, 404, 409))
def clear_banner(perfil_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> PerfilOut:
    return _clear(db, actor, perfil_id, ImageKind.banner, body.version)
