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

Spec 011 (FR-023, R3): a tomada `geracao_local` nasce do candidato do `cena.clipe` e **aponta o
mesmo objeto** (`video_key` e miniatura do candidato, sem cópia), com a geração, o keyframe
inicial usado, o motor, o fps e o prompt do clipe (`prompt_usado`, não o congelado do Flow).
"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from sociman_api import datadir, history, storage
from sociman_api.auth.deps import Actor
from sociman_api.cenas import schemas
from sociman_api.cenas import service as cenas
from sociman_api.cenas.models import Cena, CenaMotor, CenaStatus, CenaTomada, TomadaOrigem
from sociman_api.cortes import compose
from sociman_api.cortes import service as cortes_service
from sociman_api.cortes.probe import InvalidVideo, probe
from sociman_api.cortes.service import Spooled
from sociman_api.cortes.worker import EXT
from sociman_api.errors import ApiError
from sociman_api.geracao.models import GeracaoCandidato
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


def miniatura_key(perfil_id: uuid.UUID | None, cena_id: uuid.UUID, tomada_id: uuid.UUID) -> str:
    """029: a cena sem perfil base guarda a miniatura em `agencia/` (as chaves antigas ficam)."""
    raiz = f"perfis/{perfil_id}" if perfil_id is not None else "agencia"
    return f"{raiz}/cenas/{cena_id}/tomadas/{tomada_id}.jpg"


def _recebe(cena: Cena) -> None:
    if cena.archived:
        raise ApiError(409, "arquivada", "Restaure a cena antes de enviar tomadas")
    if cena.status == CenaStatus.rascunho:
        raise ApiError(409, "cena_nao_pronta", NAO_PRONTA)


def precheck(db: Session, cena_id: uuid.UUID, content_length: str | None) -> None:
    """O que dá para recusar sem ler o corpo. 029: a cena é da agência, então o perfil base
    (opcional, e pode estar arquivado) não entra; o resto é o `precheck` dos cortes."""
    cena = cenas.get_cena_or_404(db, cena_id)
    _recebe(cena)
    max_body = max_bytes() + cortes_service.MULTIPART_SLACK
    try:
        length = int(content_length) if content_length is not None else None
    except ValueError:
        raise ApiError(400, "validation_error", "Content-Length inválido") from None
    if length is not None and length > max_body:
        raise ApiError(413, "payload_too_large", TOO_BIG)
    # Sem Content-Length (envio em partes), reserva o máximo.
    datadir.ensure_writable(max_body if length is None else length)
    if not cortes_service.spool_dir().is_dir():
        raise ApiError(503, "storage_unavailable", "O HD de dados não está disponível")


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


def _de_candidato(db: Session, actor: Actor, cena: Cena, cand: GeracaoCandidato,
                  prompt_usado: str, geracao_id: uuid.UUID, keyframe_image_id: uuid.UUID,
                  motor: CenaMotor) -> CenaTomada:
    """Spec 011 (R3): a tomada local aponta o vídeo e a miniatura do candidato."""
    if not cand.video_key or not cand.video_miniatura_key or cand.video_duracao_ms is None:
        raise ApiError(400, "candidato_invalido", "Esta opção não tem mais o arquivo")
    tomada = CenaTomada(
        id=uuid.uuid4(), cena_id=cena.id, origem=TomadaOrigem.geracao_local,
        video_key=cand.video_key, content_type="video/mp4", bytes=cand.video_bytes,
        sha256=(cand.metricas or {}).get("sha256") or "", original_filename=(
            f"geracao-{geracao_id.hex[:8]}-{cand.numero}.mp4"),
        duracao_ms=cand.video_duracao_ms, largura=cand.video_largura or cena.largura,
        altura=cand.video_altura or cena.altura, miniatura_key=cand.video_miniatura_key,
        prompt_usado=prompt_usado, negative_usado="", nota="", geracao_id=geracao_id,
        keyframe_image_id=keyframe_image_id, motor=motor,
        fps=cand.video_fps if cand.video_fps in (16, 24) else None,
        created_by=actor.user_id, updated_by=actor.user_id)
    db.add(tomada)
    db.flush()
    history.record(db, actor, ENTITY, tomada, "created", None, history.snapshot(tomada),
                   {"cenaId": str(cena.id), "geracaoId": str(geracao_id),
                    "candidato": {"id": str(cand.id), "numero": cand.numero},
                    "motor": motor.value})
    return tomada


def registrar_tomada(db: Session, actor: Actor, cena: Cena, arquivo: Spooled | None,
                     origem: TomadaOrigem, prompt_usado: str | None = None,
                     geracao_id: uuid.UUID | None = None,
                     keyframe_image_id: uuid.UUID | None = None, motor: CenaMotor | None = None,
                     objeto_existente: GeracaoCandidato | None = None) -> CenaTomada:
    """Cria a tomada sem saber de HTTP. `flow_manual`: valida o arquivo (já em `work/tmp`), sobe
    vídeo e miniatura e grava o prompt congelado do momento. `geracao_local` (011): a geração, o
    keyframe e o motor são obrigatórios, e o `objeto_existente` (o candidato do `cena.clipe`) é
    apontado sem cópia; `prompt_usado` é o prompt do clipe. A 1ª tomada vira a escolhida."""
    _recebe(cena)
    local = origem == TomadaOrigem.geracao_local
    if local and (geracao_id is None or keyframe_image_id is None or motor is None):
        raise ValueError("a tomada local precisa da geração, do keyframe e do motor")
    if local and objeto_existente is not None:
        tomada = _de_candidato(db, actor, cena, objeto_existente, prompt_usado or "",
                               geracao_id, keyframe_image_id, motor)
        return _escolher_primeira(db, actor, cena, tomada)
    if arquivo is None:
        raise ValueError("sem arquivo nem objeto existente")
    up = arquivo
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
        miniatura_key=m_key,
        prompt_usado=prompt_usado if prompt_usado is not None else cena.prompt_congelado or "",
        negative_usado="" if local else cena.negative_congelado or "", nota="",
        geracao_id=geracao_id, keyframe_image_id=keyframe_image_id, motor=motor,
        created_by=actor.user_id, updated_by=actor.user_id)
    db.add(tomada)
    db.flush()
    history.record(db, actor, ENTITY, tomada, "created", None, history.snapshot(tomada),
                   {"cenaId": str(cena.id),
                    "arquivo": {"nome": up.filename, "bytes": up.size, "sha256": up.sha256}})
    return _escolher_primeira(db, actor, cena, tomada)


def _escolher_primeira(db: Session, actor: Actor, cena: Cena, tomada: CenaTomada) -> CenaTomada:
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
                            autor, com_video=actor is None or actor.kind != "mcp_client",
                            cena=cena)


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
        cenas.tomada_out(t, cena.tomada_escolhida_id == t.id, autores.get(t.id), com_video, cena)
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
