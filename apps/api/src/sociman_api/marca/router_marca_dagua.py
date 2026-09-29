"""Imagem própria de marca d'água (T020, contracts/http-api.md "Imagem de marca d'água"):
dono e membro (`RequireUser`).

O envio só guarda a imagem (`images.kind = watermark`, bucket `imagens`, que o imgproxy lê);
não altera o kit: o usuário escolhe a imagem na seção Marca d'água e salva o kit. Nada é
apagado (FR-016). `upload_image` e `list_images` servem também às imagens de fundo
(`router_fundos.py`), que só mudam o `kind`.
"""

import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import datadir, imaging, storage
from sociman_api.auth.deps import Actor, RequireUser
from sociman_api.auth.schemas import CamelModel
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.models import Image, ImageKind
from sociman_api.perfis.schemas import ImageRef, ImageUrls
from sociman_api.perfis.service_imagens import read_limited
from sociman_api.perfis.service_perfis import get_perfil_or_404

router = APIRouter(prefix="/api/perfis")

Db = DbSession
Upload = Annotated[UploadFile, File(description="PNG ou WebP com transparência, até 5 MB")]


class WatermarkImageOut(CamelModel):
    image: ImageRef


class WatermarkImagesList(CamelModel):
    items: list[ImageRef]  # mais recentes primeiro


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def image_ref(img: Image) -> ImageRef:
    return ImageRef(id=img.id, width=img.width, height=img.height,
                    urls=ImageUrls(**imaging.image_urls(img.object_key)))


def upload_image(db: Session, actor: Actor, perfil_id: uuid.UUID, stream,
                 kind: ImageKind) -> Image:
    perfil = get_perfil_or_404(db, perfil_id)
    datadir.ensure_writable()  # HD fora ou cheio: 503/507 antes de ler o corpo
    data = read_limited(stream)
    info = imaging.validate_image(data, kind.value)
    key = f"perfis/{perfil.id}/{uuid.uuid4()}.{info.ext}"
    storage.put(key, data, info.content_type)
    image = Image(
        perfil_id=perfil.id, kind=kind, object_key=key,
        content_type=info.content_type, bytes=info.bytes, width=info.width,
        height=info.height, sha256=info.sha256, created_by=actor.user_id,
    )
    db.add(image)
    db.flush()
    return image


def list_images(db: Session, perfil_id: uuid.UUID, kind: ImageKind) -> list[ImageRef]:
    get_perfil_or_404(db, perfil_id)
    rows = db.scalars(
        select(Image).where(Image.perfil_id == perfil_id, Image.kind == kind)
        .order_by(Image.created_at.desc(), Image.id)
    )
    return [image_ref(img) for img in rows]


@router.post("/{perfil_id}/marca-dagua", operation_id="marca_dagua_upload", status_code=201,
             response_model=WatermarkImageOut, responses=_errors(400, 401, 403, 404, 503, 507))
def upload(perfil_id: UUID, file: Upload, actor: RequireUser, db: Db) -> WatermarkImageOut:
    image = upload_image(db, actor, perfil_id, file.file, ImageKind.watermark)
    return WatermarkImageOut(image=image_ref(image))


@router.get("/{perfil_id}/marca-dagua", operation_id="marca_dagua_list",
            response_model=WatermarkImagesList, responses=_errors(401, 403, 404))
def list_(perfil_id: UUID, actor: RequireUser, db: Db) -> WatermarkImagesList:
    return WatermarkImagesList(items=list_images(db, perfil_id, ImageKind.watermark))
