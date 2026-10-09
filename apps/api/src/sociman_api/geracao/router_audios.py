"""Rotas dos áudios (contracts/http-api.md da spec 021, R11): enviar (`RequireHuman`,
multipart com `arquivo`, até 25 MB; o edge tem `location` própria de 26m) e ler (`RequireUser`).
Sem rota de alteração: o áudio é imutável. No `mcp/mapa.py`, `audios_enviar` fica em
`PROIBIDAS` e `audios_detalhe` em `FORA`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile

from sociman_api.auth.deps import RequireHuman, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope
from sociman_api.geracao import audios, schemas
from sociman_api.geracao.models import Audio
from sociman_api.perfis.service_perfis import get_perfil_or_404, user_refs

router = APIRouter(prefix="/api")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.post("/perfis/{perfil_id}/audios", operation_id="audios_enviar", status_code=201,
             response_model=schemas.Audio,
             responses=_errors(400, 401, 403, 404, 409, 413, 503, 507))
def enviar(perfil_id: UUID, arquivo: Annotated[UploadFile, File()], actor: RequireHuman,
           db: DbSession) -> schemas.Audio:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    audio = audios.enviar(db, perfil_id, arquivo.file, actor.user_id)
    return audios.audio_out(audio, user_refs(db, [audio.created_by]))


@router.get("/audios/{audio_id}", operation_id="audios_detalhe", response_model=schemas.Audio,
            responses=_errors(401, 403, 404))
def detalhe(audio_id: UUID, actor: RequireUser, db: DbSession) -> schemas.Audio:
    audio = db.get(Audio, audio_id)
    if audio is None:
        raise ApiError(404, "not_found", "Áudio não encontrado")
    return audios.audio_out(audio, user_refs(db, [audio.created_by]))
