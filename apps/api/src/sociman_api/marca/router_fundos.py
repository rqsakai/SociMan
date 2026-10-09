"""Imagens de fundo do gancho e do card final (T031, FR-005b, contracts/http-api.md "Imagens
de fundo"): dono e membro (`RequireUser`).

Como a marca d'água: o envio só guarda a imagem (`images.kind = fundo`, bucket `imagens`) e
não altera o kit; o usuário escolhe a imagem na seção Gancho ou Card final e salva o kit. PNG,
JPG ou WebP, até 5 MB, mínimo 540×540. Nada é apagado.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile

from sociman_api.auth.deps import RequireUser
from sociman_api.auth.schemas import CamelModel
from sociman_api.db import DbSession
from sociman_api.marca.router_marca_dagua import _errors, image_ref, list_images, upload_image
from sociman_api.perfis.models import ImageKind
from sociman_api.perfis.schemas import ImageRef

router = APIRouter(prefix="/api/perfis")

Db = DbSession
Upload = Annotated[UploadFile, File(description="PNG, JPG ou WebP, até 5 MB, mínimo 540×540")]


class FundoImageOut(CamelModel):
    image: ImageRef


class FundoImagesList(CamelModel):
    items: list[ImageRef]  # mais recentes primeiro


@router.post("/{perfil_id}/fundos", operation_id="fundos_upload", status_code=201,
             deprecated=True,
             response_model=FundoImageOut, responses=_errors(400, 401, 403, 404, 503, 507))
def upload(perfil_id: UUID, file: Upload, actor: RequireUser, db: Db) -> FundoImageOut:
    return FundoImageOut(image=image_ref(upload_image(db, actor, perfil_id, file.file,
                                                      ImageKind.fundo)))


@router.get("/{perfil_id}/fundos", operation_id="fundos_list", deprecated=True,
            response_model=FundoImagesList, responses=_errors(401, 403, 404))
def list_(perfil_id: UUID, actor: RequireUser, db: Db) -> FundoImagesList:
    return FundoImagesList(items=list_images(db, perfil_id, ImageKind.fundo))
