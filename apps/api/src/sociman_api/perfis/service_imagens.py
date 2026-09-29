"""Logo e banner dos perfis (T021, contracts/http-api.md "Perfis", research R4–R7).

Upload: lê no máximo 5 MB + 1 byte, valida pelo conteúdo (`imaging.validate_image`) e só então
grava o objeto no MinIO (`perfis/{perfil_id}/{uuid4}.{ext}`, impossível de adivinhar:
FR-009a), a linha em `images` e a referência no perfil, com a versão no histórico na mesma
transação. Nada é apagado (FR-010): trocar ou remover só muda a referência, e a imagem antiga
continua no bucket e na tabela, pronta para a reversão.
"""

import uuid
from typing import BinaryIO

from sqlalchemy.orm import Session

from sociman_api import history, imaging, storage
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Image, ImageKind, Perfil
from sociman_api.perfis.service_perfis import ENTITY, LABEL, get_perfil_or_404

_CHUNK = 64 * 1024
_FIELD = {ImageKind.logo: "logo_image_id", ImageKind.banner: "banner_image_id"}


def read_limited(stream: BinaryIO) -> bytes:
    """Lê em blocos e para ao passar de MAX_BYTES, sem carregar o resto do arquivo."""
    data = bytearray()
    while chunk := stream.read(_CHUNK):
        data += chunk
        if len(data) > imaging.MAX_BYTES:
            raise ApiError(400, "invalid_image", "Arquivo maior que 5 MB")
    return bytes(data)


def _set_image(
    db: Session, actor: Actor, perfil: Perfil, kind: ImageKind, image_id: uuid.UUID | None
) -> None:
    before = history.snapshot(perfil)
    setattr(perfil, _FIELD[kind], image_id)
    perfil.updated_by = actor.user_id
    history.record(db, actor, ENTITY, perfil, "updated", before, history.snapshot(perfil))


def upload_image(
    db: Session, actor: Actor, perfil_id: uuid.UUID, kind: ImageKind, version: int,
    stream: BinaryIO,
) -> Perfil:
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    history.check_version(perfil, version, LABEL)
    data = read_limited(stream)
    info = imaging.validate_image(data, kind.value)
    key = f"perfis/{perfil.id}/{uuid.uuid4()}.{info.ext}"
    # O objeto vai antes do commit; se a transação falhar, sobra um objeto sem referência
    # (nunca apagamos objetos), o que é inofensivo.
    storage.put(key, data, info.content_type)
    image = Image(
        perfil_id=perfil.id, kind=kind, object_key=key, content_type=info.content_type,
        bytes=info.bytes, width=info.width, height=info.height, sha256=info.sha256,
        created_by=actor.user_id,
    )
    db.add(image)
    db.flush()
    _set_image(db, actor, perfil, kind, image.id)
    return perfil


def clear_image(
    db: Session, actor: Actor, perfil_id: uuid.UUID, kind: ImageKind, version: int
) -> Perfil:
    """Tira a referência do perfil. Sem imagem, não grava versão."""
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    history.check_version(perfil, version, LABEL)
    if getattr(perfil, _FIELD[kind]) is not None:
        _set_image(db, actor, perfil, kind, None)
    return perfil
