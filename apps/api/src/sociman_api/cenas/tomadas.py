"""Tomadas da cena (research R6, FR-011): os vídeos gerados no Flow.

O envio reusa o recebimento em streaming da 004/006 (`cortes.service.precheck` e `receive`, com
o prefixo `tomada-` e o limite de 200 MB): HD e `Content-Length` conferidos antes de ler o corpo,
arquivo em `work/tmp` (HD). Depois:
1. ffprobe pelo conteúdo real: MP4, MOV ou WebM, de 1 a 30 s, qualquer proporção (fora de 9:16
   sai com `naoVertical`);
2. o vídeo vai para o bucket de vídeos em `cenas/<cena>/tomadas/<tomada>.<ext>` e a miniatura
   para o `sociman`, como no vídeo próprio da 014;
3. nasce a linha com o prompt congelado da cena **naquele momento** (não muda com um
   "Remontar" depois). A primeira tomada vira a escolhida.

Só cenas `pronta`/`usada` recebem tomadas (409 `cena_nao_pronta`). Nada é apagado: arquivar e
restaurar; a reversão é só do dono humano.
"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from sociman_api import history, storage
from sociman_api.auth.deps import Actor
from sociman_api.cenas import schemas
from sociman_api.cenas import service as cenas
from sociman_api.cenas.models import Cena, CenaStatus, CenaTomada, TomadaOrigem
from sociman_api.cortes import compose
from sociman_api.cortes import service as cortes_service
from sociman_api.cortes.probe import InvalidVideo, probe
from sociman_api.cortes.service import Spooled
from sociman_api.cortes.worker import EXT
from sociman_api.errors import ApiError
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import target_state, versions_out

ENTITY = "cena_tomada"
LABEL = "Esta tomada"
MB = 1024 * 1024
MAX_BYTES = 200 * MB
TOO_BIG = "Arquivo maior que 200 MB"
MIN_DURATION_S = 1
MAX_DURATION_S = 30
TOO_SHORT = "A tomada precisa ter de 1 a 30 s"
TOO_LONG = "A tomada precisa ter de 1 a 30 s"
SPOOL_PREFIX = "tomada-"
NAO_PRONTA = "Marque a cena como pronta antes de enviar tomadas"


def max_bytes() -> int:
    """Lido na hora (os testes reduzem o limite)."""
    return MAX_BYTES


def video_key(cena_id: uuid.UUID, tomada_id: uuid.UUID, content_type: str) -> str:
    return f"cenas/{cena_id}/tomadas/{tomada_id}.{EXT[content_type]}"


def miniatura_key(perfil_id: uuid.UUID, cena_id: uuid.UUID, tomada_id: uuid.UUID) -> str:
    return f"perfis/{perfil_id}/cenas/{cena_id}/tomadas/{tomada_id}.jpg"


def _recebe(cena: Cena) -> None:
    if cena.archived:
        raise ApiError(409, "arquivada", "Restaure a cena antes de enviar tomadas")
    if cena.status == CenaStatus.rascunho:
        raise ApiError(409, "cena_nao_pronta", NAO_PRONTA)


def precheck(db: Session, cena_id: uuid.UUID, content_length: str | None) -> None:
    cena = cenas.get_cena_or_404(db, cena_id)
    _recebe(cena)
    cortes_service.precheck(db, cena.perfil_id, content_length,
                            max_body=max_bytes() + cortes_service.MULTIPART_SLACK,
                            too_big=TOO_BIG)


async def receive(request: Request) -> Spooled:
    return await cortes_service.receive(request, max_bytes=max_bytes(), prefix=SPOOL_PREFIX,
                                        too_big=TOO_BIG)


def get_tomada_or_404(db: Session, tomada_id: uuid.UUID, lock: bool = False) -> CenaTomada:
    tomada = db.get(CenaTomada, tomada_id, with_for_update=lock)
    if tomada is None:
        raise ApiError(404, "nao_encontrada", "Tomada não encontrada")
    return tomada


def _record_cena(db: Session, actor: Actor, cena: Cena, before: dict, acao: str,
                 tomada_id: uuid.UUID) -> None:
    cenas._record(db, actor, cena, "updated", before,
                  {"tomada": {"id": str(tomada_id), "acao": acao}}, sempre=True)


def criar(db: Session, actor: Actor, cena_id: uuid.UUID, up: Spooled) -> CenaTomada:
    """O envio HTTP: o arquivo gerado à mão no Flow."""
    cena = cenas.get_cena_or_404(db, cena_id, lock=True)
    return registrar_tomada(db, actor, cena, up, TomadaOrigem.flow_manual)


def registrar_tomada(db: Session, actor: Actor, cena: Cena, arquivo: Spooled,
                     origem: TomadaOrigem) -> CenaTomada:
    """Valida o arquivo (já em `work/tmp`) e cria a tomada com o prompt congelado do momento,
    sem saber de HTTP: a 021 (geração local) vai reaproveitar com outra `origem`."""
    up = arquivo
    cenas.perfil_ativo(db, cena.perfil_id)
    _recebe(cena)
    info = probe(up.path, max_duration_s=MAX_DURATION_S, min_duration_s=MIN_DURATION_S,
                 max_bytes=max_bytes(), too_long=TOO_LONG, too_short=TOO_SHORT,
                 too_big=TOO_BIG)
    tomada_id = uuid.uuid4()
    with tempfile.TemporaryDirectory(dir=cortes_service.spool_dir(), prefix="tomada-") as tmp:
        poster = Path(tmp) / "poster.jpg"
        try:
            compose.extract_frame(up.path, min(1.0, info.duration_s / 2), poster)
        except compose.ComposeError:
            raise InvalidVideo("Não deu para ler um quadro do vídeo") from None
        m_key = miniatura_key(cena.perfil_id, cena.id, tomada_id)
        storage.put(m_key, poster.read_bytes(), "image/jpeg", bucket="imagens")
    v_key = video_key(cena.id, tomada_id, info.content_type)
    storage.put_file(v_key, up.path, info.content_type, bucket="videos")

    tomada = CenaTomada(
        id=tomada_id, cena_id=cena.id, origem=origem, video_key=v_key, content_type=info.content_type,
        bytes=up.size, sha256=up.sha256, original_filename=up.filename,
        duracao_ms=info.duration_ms, largura=info.width, altura=info.height,
        miniatura_key=m_key, prompt_usado=cena.prompt_congelado or "",
        negative_usado=cena.negative_congelado or "", nota="",
        created_by=actor.user_id, updated_by=actor.user_id)
    db.add(tomada)
    db.flush()
    history.record(db, actor, ENTITY, tomada, "created", None, history.snapshot(tomada),
                   {"cenaId": str(cena.id),
                    "arquivo": {"nome": up.filename, "bytes": up.size, "sha256": up.sha256}})
    if cena.tomada_escolhida_id is None:
        before = history.snapshot(cena)
        cena.tomada_escolhida_id = tomada.id
        _record_cena(db, actor, cena, before, "escolhida", tomada.id)
    db.flush()
    db.refresh(tomada)
    return tomada


def tomada_out(db: Session, tomada: CenaTomada, actor: Actor | None = None) -> schemas.Tomada:
    db.flush()
    db.refresh(tomada)
    cena = db.get(Cena, tomada.cena_id)
    autor = cenas.autores_de(db, ENTITY, [tomada.id]).get(tomada.id)
    return cenas.tomada_out(tomada, cena is not None and cena.tomada_escolhida_id == tomada.id,
                            autor, com_video=actor is None or actor.kind != "mcp_client")


def listar(db: Session, cena_id: uuid.UUID, arquivadas: bool,
           actor: Actor | None = None) -> schemas.TomadasList:
    cena = cenas.get_cena_or_404(db, cena_id)
    stmt = select(CenaTomada).where(CenaTomada.cena_id == cena_id)
    if not arquivadas:
        stmt = stmt.where(CenaTomada.archived_at.is_(None))
    rows = list(db.scalars(stmt.order_by(CenaTomada.created_at.desc(), CenaTomada.id)))
    autores = cenas.autores_de(db, ENTITY, [t.id for t in rows])
    com_video = actor is None or actor.kind != "mcp_client"
    return schemas.TomadasList(items=[
        cenas.tomada_out(t, cena.tomada_escolhida_id == t.id, autores.get(t.id), com_video)
        for t in rows])


def escolher(db: Session, actor: Actor, cena_id: uuid.UUID, tomada_id: uuid.UUID,
             version: int) -> Cena:
    cena = cenas._editavel(db, cena_id, version)
    tomada = get_tomada_or_404(db, tomada_id)
    if tomada.cena_id != cena.id:
        raise ApiError(404, "nao_encontrada", "Tomada não encontrada nesta cena")
    if tomada.archived:
        raise ApiError(409, "arquivada", "Restaure a tomada antes de escolher")
    if cena.tomada_escolhida_id == tomada.id:
        return cena
    before = history.snapshot(cena)
    cena.tomada_escolhida_id = tomada.id
    _record_cena(db, actor, cena, before, "escolhida", tomada.id)
    return cena


def _editavel(db: Session, tomada_id: uuid.UUID, version: int) -> tuple[CenaTomada, Cena]:
    tomada = get_tomada_or_404(db, tomada_id, lock=True)
    history.check_version(tomada, version, LABEL)
    cena = cenas.get_cena_or_404(db, tomada.cena_id, lock=True)
    cenas.perfil_ativo(db, cena.perfil_id)
    return tomada, cena


def _record(db: Session, actor: Actor, tomada: CenaTomada, action: str, before: dict,
            details: dict | None = None) -> None:
    tomada.updated_by = actor.user_id
    history.record(db, actor, ENTITY, tomada, action, before, history.snapshot(tomada), details)


def _solta_escolha(db: Session, actor: Actor, cena: Cena, tomada: CenaTomada) -> None:
    if cena.tomada_escolhida_id == tomada.id:
        before = history.snapshot(cena)
        cena.tomada_escolhida_id = None
        _record_cena(db, actor, cena, before, "escolha_desfeita", tomada.id)


def editar_nota(db: Session, actor: Actor, tomada_id: uuid.UUID, version: int,
                nota: str) -> CenaTomada:
    tomada, _ = _editavel(db, tomada_id, version)
    before = history.snapshot(tomada)
    tomada.nota = nota
    if history.snapshot(tomada) != before:
        _record(db, actor, tomada, "updated", before)
    return tomada


def arquivar(db: Session, actor: Actor, tomada_id: uuid.UUID, version: int) -> CenaTomada:
    tomada, cena = _editavel(db, tomada_id, version)
    if tomada.archived:
        raise ApiError(409, "arquivada", "Esta tomada já está arquivada")
    before = history.snapshot(tomada)
    tomada.archived_at = datetime.now(UTC)
    tomada.archived_by = actor.user_id
    _record(db, actor, tomada, "archived", before)
    _solta_escolha(db, actor, cena, tomada)
    return tomada


def restaurar(db: Session, actor: Actor, tomada_id: uuid.UUID, version: int) -> CenaTomada:
    tomada, _ = _editavel(db, tomada_id, version)
    if not tomada.archived:
        raise ApiError(409, "conflict", "Esta tomada não está arquivada")
    before = history.snapshot(tomada)
    tomada.archived_at = None
    tomada.archived_by = None
    _record(db, actor, tomada, "restored", before)
    return tomada


def versoes(db: Session, tomada_id: uuid.UUID) -> VersionsList:
    get_tomada_or_404(db, tomada_id)
    return versions_out(db, ENTITY, tomada_id)


def reverter(db: Session, actor: Actor, tomada_id: uuid.UUID, version: int,
             to_version: int) -> CenaTomada:
    """Só o dono humano (rota): volta a nota e o arquivamento."""
    tomada, cena = _editavel(db, tomada_id, version)
    state = target_state(db, ENTITY, tomada, to_version)
    before = history.snapshot(tomada)
    tomada.nota = state["nota"]
    if state["archived"] and not tomada.archived:
        tomada.archived_at, tomada.archived_by = datetime.now(UTC), actor.user_id
    elif not state["archived"] and tomada.archived:
        tomada.archived_at, tomada.archived_by = None, None
    if history.snapshot(tomada) == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    _record(db, actor, tomada, "reverted", before, {"from_version": to_version})
    if tomada.archived:
        _solta_escolha(db, actor, cena, tomada)
    return tomada
