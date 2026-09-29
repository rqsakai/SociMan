"""Rotas de fontes (T009/T015, contracts/http-api.md "Fontes").

As fontes padrão são públicas (arquivos livres, OFL): o `@font-face` da prévia e o worker não
mandam `Authorization`. As fontes do perfil pedem `RequireUser`; o arquivo delas sai só por
link assinado (`/api/midia/{token}`, kind `fonte`). Não existe rota DELETE (FR-009).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from sociman_api.auth.deps import RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope
from sociman_api.marca import fontes as service
from sociman_api.marca.fontes import FonteOut, FontesList, FontesPadraoList, RenameFonteIn
from sociman_api.perfis.schemas import VersionIn, VersionsList
from sociman_api.perfis.service_perfis import versions_out

router = APIRouter(prefix="/api")

Db = DbSession
Upload = Annotated[UploadFile, File(description="TTF ou OTF até 10 MB")]
NameField = Annotated[str, Form(min_length=1, max_length=60)]
IMMUTABLE = "public, max-age=31536000, immutable"


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/fontes-padrao", operation_id="fontes_padrao_list",
            response_model=FontesPadraoList)
def list_default() -> FontesPadraoList:
    return service.list_default_fonts()


@router.get("/fontes-padrao/{key}", operation_id="fontes_padrao_file",
            response_class=FileResponse, responses={
                200: {"content": {"font/ttf": {}}, "description": "O arquivo da fonte"},
                **_errors(404),
            })
def default_file(key: str) -> FileResponse:
    return FileResponse(service.default_font_path(key), media_type="font/ttf", headers={
        "Cache-Control": IMMUTABLE, "X-Content-Type-Options": "nosniff",
    })


@router.get("/perfis/{perfil_id}/fontes", operation_id="fontes_list",
            response_model=FontesList, responses=_errors(401, 403, 404))
def list_fontes(
    perfil_id: UUID, actor: RequireUser, db: Db,
    archived: Annotated[bool, Query(description="Listar as arquivadas")] = False,
) -> FontesList:
    return service.list_fontes(db, perfil_id, archived)


@router.post("/perfis/{perfil_id}/fontes", operation_id="fontes_upload", status_code=201,
             response_model=FonteOut, responses=_errors(400, 401, 403, 404, 409, 503, 507))
def upload(perfil_id: UUID, file: Upload, name: NameField, actor: RequireUser,
           db: Db) -> FonteOut:
    name = name.strip()
    if not name:
        raise ApiError(400, "validation_error", "name: informe o nome da fonte")
    font = service.upload_fonte(db, actor, perfil_id, name, file.file)
    return FonteOut(fonte=service.fonte_out(db, font))


@router.patch("/fontes/{font_id}", operation_id="fontes_rename", response_model=FonteOut,
              responses=_errors(400, 401, 403, 404, 409))
def rename(font_id: UUID, body: RenameFonteIn, actor: RequireUser, db: Db) -> FonteOut:
    font = service.rename_fonte(db, actor, font_id, body.version, body.name)
    return FonteOut(fonte=service.fonte_out(db, font))


@router.post("/fontes/{font_id}/archive", operation_id="fontes_archive",
             response_model=FonteOut, responses=_errors(400, 401, 403, 404, 409))
def archive(font_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> FonteOut:
    font = service.archive_fonte(db, actor, font_id, body.version)
    return FonteOut(fonte=service.fonte_out(db, font))


@router.post("/fontes/{font_id}/restore", operation_id="fontes_restore",
             response_model=FonteOut, responses=_errors(400, 401, 403, 404, 409))
def restore(font_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> FonteOut:
    font = service.restore_fonte(db, actor, font_id, body.version)
    return FonteOut(fonte=service.fonte_out(db, font))


@router.get("/fontes/{font_id}/versions", operation_id="fontes_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def versions(font_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    service.get_font_or_404(db, font_id)
    return versions_out(db, service.ENTITY, font_id)
