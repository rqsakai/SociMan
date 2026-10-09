"""Envio de vídeo próprio (contracts/http-api.md da 014, "Conteúdos"; research R9).

Arquivo à parte do `router.py` para as trilhas paralelas não colidirem. Como o envio de corte e o
avulso, o corpo não é `UploadFile`: o HD e o `Content-Length` são conferidos antes, e o
multipart (`file` e `titulo`, os mesmos campos do envio avulso) é lido em streaming. O schema
do multipart vai para o OpenAPI por `openapi_extra`. Nada aqui publica (princípio I).
"""

from uuid import UUID

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from sociman_api.auth.deps import RequireUser
from sociman_api.conteudos import service, video_proprio
from sociman_api.conteudos.schemas import ConteudoOut
from sociman_api.cortes import service as cortes_service
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope

router = APIRouter(prefix="/api")

_ARQUIVO_BODY = {
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object",
            "required": ["file"],
            "properties": {
                "file": {"type": "string", "format": "binary",
                         "description": "MP4, MOV ou WebM, de 1 s a 10 min, até 2 GB, "
                                        "qualquer proporção"},
                "titulo": {"type": "string", "maxLength": video_proprio.TITULO_MAX,
                           "description": "Título do conteúdo (padrão: o nome do arquivo)"},
            },
        }}},
    },
}


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.post("/perfis/{perfil_id}/conteudos/arquivo", operation_id="conteudos_video_proprio",
             response_model=ConteudoOut, status_code=201, openapi_extra=_ARQUIVO_BODY,
             responses=_errors(400, 401, 403, 404, 409, 413, 503, 507))
async def enviar_video_proprio(perfil_id: UUID, request: Request, actor: RequireUser,
                               db: DbSession) -> ConteudoOut:
    await run_in_threadpool(video_proprio.precheck, db, perfil_id,
                            request.headers.get("content-length"))
    up = await video_proprio.receive(request)
    try:
        conteudo = await run_in_threadpool(video_proprio.create, db, actor, perfil_id, up)
        return ConteudoOut(conteudo=await run_in_threadpool(service.conteudo_out, db,
                                                             conteudo.id))
    finally:
        cortes_service.cleanup_spool(up)
