"""Envio avulso por arquivo (research R16): `POST /api/perfis/{id}/envios/arquivo`.

Reusa o recebimento em streaming da 004 (`cortes.service.precheck` e `receive`, com o limite e o
prefixo deste envio): o HD e o `Content-Length` são conferidos antes de ler o corpo; o arquivo
vai para `work/tmp` (HD), passa pelo ffprobe (vídeo aceito, de 45 s a 3 h, até 2 GB) e é
guardado no bucket de vídeos em `envios/{id}/fonte.<ext>`. Só então a linha é criada, como
`selecionado` (o aviso de direito vem na hora de enviar). O arquivo fica no HD e pode ser
reenviado depois que o OpenShorts apagar o job.
"""

import uuid

from sqlalchemy.orm import Session
from starlette.requests import Request

from sociman_api import storage
from sociman_api.auth.deps import Actor
from sociman_api.cortes import service as cortes_service
from sociman_api.cortes.probe import probe
from sociman_api.cortes.service import Spooled
from sociman_api.cortes.worker import EXT
from sociman_api.envios import service_envios
from sociman_api.envios.models import Envio

GB = 1024**3
MAX_BYTES = 2 * GB  # o limite do OpenShorts (MAX_FILE_SIZE_MB)
MAX_BODY = MAX_BYTES + cortes_service.MULTIPART_SLACK
TOO_BIG = "Arquivo maior que 2 GB"
MIN_DURATION_S = 45  # MIN_SOURCE_SECONDS do OpenShorts
MAX_DURATION_S = 3 * 3600
TOO_SHORT = "Vídeo com menos de 45 segundos"
TOO_LONG = "Vídeo com mais de 3 horas"
SPOOL_PREFIX = "envio-"


def upload_key(envio_id: uuid.UUID, content_type: str) -> str:
    return f"envios/{envio_id}/fonte.{EXT[content_type]}"


def precheck(db: Session, perfil_id: uuid.UUID, content_length: str | None) -> None:
    cortes_service.precheck(db, perfil_id, content_length, max_body=MAX_BODY, too_big=TOO_BIG)


async def receive(request: Request) -> Spooled:
    return await cortes_service.receive(request, max_bytes=MAX_BYTES, prefix=SPOOL_PREFIX,
                                        too_big=TOO_BIG)


def create(db: Session, actor: Actor, perfil_id: uuid.UUID, up: Spooled) -> Envio:
    info = probe(up.path, max_duration_s=MAX_DURATION_S, min_duration_s=MIN_DURATION_S,
                 max_bytes=MAX_BYTES, too_long=TOO_LONG, too_short=TOO_SHORT, too_big=TOO_BIG)
    envio_id = uuid.uuid4()
    key = upload_key(envio_id, info.content_type)
    storage.put_file(key, up.path, info.content_type, bucket="videos")
    titulo = up.fields.get("titulo") or up.filename.rsplit(".", 1)[0]
    return service_envios.criar_avulso_arquivo(
        db, actor, perfil_id, envio_id, titulo, key, up.size, info.duration_ms, up.sha256)
