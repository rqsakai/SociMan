"""O dicionário de pronúncia do perfil (FR-045, R15; US8): pares "escrita → falada" só para a
voz. Uma linha por par, versionada (`entity_type = "pronuncia"`), arquivável; duas ativas com a
mesma grafia escrita (sem diferenciar maiúsculas) → 409 `pronuncia_existe` (índice
`uq_pronuncias_escrita`). Dono e membro editam.

O dicionário entra no `texto_hash` da narração (R10): mudar uma pronúncia de palavra presente
nas frases deixa a narração desatualizada (FR-019), sem mexer no texto mostrado.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, versions_out
from sociman_api.roteiros import schemas
from sociman_api.roteiros.models import ENTITY_PRONUNCIA, Pronuncia

LABEL = "Esta pronúncia"


def get_or_404(db: Session, pronuncia_id: uuid.UUID, lock: bool = False) -> Pronuncia:
    p = db.get(Pronuncia, pronuncia_id, with_for_update=lock)
    if p is None:
        raise ApiError(404, "not_found", "Pronúncia não encontrada")
    return p


def pronuncia_out(p: Pronuncia) -> schemas.Pronuncia:
    return schemas.Pronuncia(id=p.id, perfil_id=p.perfil_id, escrita=p.escrita, falada=p.falada,
                             archived=p.archived, version=p.version, updated_at=p.updated_at)


def _existe(db: Session, perfil_id: uuid.UUID, escrita: str, exceto: uuid.UUID | None) -> None:
    stmt = select(Pronuncia.id).where(Pronuncia.perfil_id == perfil_id,
                                      Pronuncia.archived_at.is_(None),
                                      func.lower(Pronuncia.escrita) == escrita.lower())
    if exceto is not None:
        stmt = stmt.where(Pronuncia.id != exceto)
    if db.scalar(stmt) is not None:
        raise ApiError(409, "pronuncia_existe", f"Já existe uma pronúncia para \"{escrita}\"",
                       details={"field": "escrita"})


def _record(db: Session, actor: Actor, p: Pronuncia, action: str, before: dict | None) -> None:
    db.flush()
    p.updated_by = actor.user_id
    history.record(db, actor, ENTITY_PRONUNCIA, p, action, before, history.snapshot(p))


def listar(db: Session, perfil_id: uuid.UUID, arquivadas: bool = False
           ) -> schemas.PronunciasList:
    get_perfil_or_404(db, perfil_id)
    stmt = select(Pronuncia).where(Pronuncia.perfil_id == perfil_id)
    if not arquivadas:
        stmt = stmt.where(Pronuncia.archived_at.is_(None))
    rows = db.scalars(stmt.order_by(func.lower(Pronuncia.escrita), Pronuncia.id))
    return schemas.PronunciasList(items=[pronuncia_out(p) for p in rows])


def criar(db: Session, actor: Actor, perfil_id: uuid.UUID, body: schemas.PronunciaIn
          ) -> Pronuncia:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    _existe(db, perfil_id, body.escrita, None)
    p = Pronuncia(id=uuid.uuid4(), perfil_id=perfil_id, escrita=body.escrita,
                  falada=body.falada, created_by=actor.user_id, updated_by=actor.user_id)
    db.add(p)
    _record(db, actor, p, "created", None)
    return p


def editar(db: Session, actor: Actor, pronuncia_id: uuid.UUID, body: schemas.PronunciaPatch
           ) -> Pronuncia:
    p = get_or_404(db, pronuncia_id, lock=True)
    history.check_version(p, body.version, LABEL)
    if p.archived:
        raise ApiError(409, "arquivada", "Restaure a pronúncia antes de editar")
    before = history.snapshot(p)
    if body.escrita is not None and body.escrita != p.escrita:
        _existe(db, p.perfil_id, body.escrita, p.id)
        p.escrita = body.escrita
    if body.falada is not None:
        p.falada = body.falada
    if history.snapshot(p) != before:
        _record(db, actor, p, "updated", before)
    return p


def arquivar(db: Session, actor: Actor, pronuncia_id: uuid.UUID, version: int) -> Pronuncia:
    p = get_or_404(db, pronuncia_id, lock=True)
    history.check_version(p, version, LABEL)
    if p.archived:
        raise ApiError(409, "arquivada", "Esta pronúncia já está arquivada")
    before = history.snapshot(p)
    p.archived_at, p.archived_by = datetime.now(UTC), actor.user_id
    _record(db, actor, p, "archived", before)
    return p


def restaurar(db: Session, actor: Actor, pronuncia_id: uuid.UUID, version: int) -> Pronuncia:
    p = get_or_404(db, pronuncia_id, lock=True)
    history.check_version(p, version, LABEL)
    if not p.archived:
        raise ApiError(409, "conflict", "Esta pronúncia não está arquivada")
    _existe(db, p.perfil_id, p.escrita, p.id)
    before = history.snapshot(p)
    p.archived_at, p.archived_by = None, None
    _record(db, actor, p, "restored", before)
    return p


def versoes(db: Session, pronuncia_id: uuid.UUID) -> VersionsList:
    get_or_404(db, pronuncia_id)
    return versions_out(db, ENTITY_PRONUNCIA, pronuncia_id)
