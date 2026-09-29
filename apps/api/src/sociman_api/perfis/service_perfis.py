"""Perfis da agência (T010, contracts/http-api.md "Perfis").

Toda mutação trava a linha (`SELECT … FOR UPDATE`), faz `check_version` e grava a versão em
`entity_versions` na mesma transação (`history.record`), com `updated_by` vindo do ator. Nada é
apagado (FR-014): arquivar e restaurar também são versões.

Os helpers públicos (`get_perfil_or_404`, `perfil_out`, `conta_out`, `user_refs`,
`versions_out`, `target_state`, `apply_archived`) são reusados pelas rotas de contas, imagens e
reversão. Este módulo não importa `service_contas` (evita import circular).
"""

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history, imaging
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User
from sociman_api.errors import ApiError
from sociman_api.perfis import schemas
from sociman_api.perfis.models import (
    Conta,
    ContaStatus,
    Image,
    ImageKind,
    Perfil,
    PerfilStatus,
    Platform,
)
from sociman_api.perfis.platforms import SLUG_MAX, suggest_slug

ENTITY = "perfil"
LABEL = "Este perfil"
NOT_FOUND = "Perfil não encontrado"
SLUG_IN_USE = "Já existe um perfil com esse identificador"
_PLATFORM_ORDER = {p: i for i, p in enumerate(Platform)}


# ---- auxiliares ----

def get_perfil_or_404(db: Session, perfil_id: uuid.UUID, lock: bool = False) -> Perfil:
    perfil = db.get(Perfil, perfil_id, with_for_update=lock)
    if perfil is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return perfil


def _slug_in_use() -> ApiError:
    return ApiError(409, "slug_in_use", SLUG_IN_USE)


def _slug_taken(db: Session, slug: str) -> bool:
    return db.scalar(select(Perfil.id).where(Perfil.slug == slug)) is not None


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def user_refs(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, schemas.UserRef]:
    """Nomes dos autores numa consulta só."""
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.name).where(User.id.in_(wanted)))
    return {uid: schemas.UserRef(id=uid, name=name) for uid, name in rows}


def _active_platforms(db: Session, perfil_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[Platform]]:
    """Plataformas das contas ativas (não arquivadas) de cada perfil, na ordem do enum."""
    result: dict[uuid.UUID, set[Platform]] = {pid: set() for pid in perfil_ids}
    if perfil_ids:
        rows = db.execute(
            select(Conta.perfil_id, Conta.platform).where(
                Conta.perfil_id.in_(perfil_ids),
                Conta.status == ContaStatus.ativa,
                Conta.archived_at.is_(None),
            )
        )
        for pid, platform in rows:
            result[pid].add(platform)
    return {pid: sorted(ps, key=_PLATFORM_ORDER.__getitem__) for pid, ps in result.items()}


def _images(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, Image]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {img.id: img for img in db.scalars(select(Image).where(Image.id.in_(wanted)))}


def _logo_ref(img: Image | None) -> schemas.ImageRef | None:
    if img is None:
        return None
    return schemas.ImageRef(id=img.id, width=img.width, height=img.height,
                            urls=schemas.ImageUrls(**imaging.image_urls(img.object_key)))


def _banner_ref(img: Image | None) -> schemas.ImageRef | None:
    # Banner: `medium` é o recorte largo (1200×300); `thumb` segue o quadrado da lista.
    if img is None:
        return None
    urls = imaging.image_urls(img.object_key)
    return schemas.ImageRef(
        id=img.id, width=img.width, height=img.height,
        urls=schemas.ImageUrls(thumb=urls["thumb"], medium=imaging.banner_url(img.object_key)),
    )


def _perfis_out(db: Session, perfis: Sequence[Perfil]) -> list[schemas.Perfil]:
    ids = [p.id for p in perfis]
    platforms = _active_platforms(db, ids)
    images = _images(db, [i for p in perfis for i in (p.logo_image_id, p.banner_image_id)])
    users = user_refs(db, [u for p in perfis for u in (p.created_by, p.updated_by)])
    return [
        schemas.Perfil(
            id=p.id, slug=p.slug, name=p.name, niche=p.niche, bio=p.bio, language=p.language,
            status=p.status,
            logo=_logo_ref(images.get(p.logo_image_id)) if p.logo_image_id else None,
            banner=_banner_ref(images.get(p.banner_image_id)) if p.banner_image_id else None,
            platforms=platforms[p.id], archived=p.archived, archived_at=p.archived_at,
            version=p.version, created_at=p.created_at, updated_at=p.updated_at,
            created_by=users.get(p.created_by) if p.created_by else None,
            updated_by=users.get(p.updated_by) if p.updated_by else None,
        )
        for p in perfis
    ]


def perfil_out(db: Session, perfil: Perfil) -> schemas.Perfil:
    """Saída do perfil com logo/banner (imgproxy), plataformas ativas e autores."""
    db.flush()
    db.refresh(perfil)  # created_at/updated_at vêm do banco
    return _perfis_out(db, [perfil])[0]


def conta_out(
    db: Session, conta: Conta, users: dict[uuid.UUID, schemas.UserRef] | None = None
) -> schemas.Conta:
    """Saída da conta com os autores. `users` evita uma consulta por conta numa lista."""
    if users is None:
        users = user_refs(db, [conta.created_by, conta.updated_by])
    return schemas.Conta(
        id=conta.id, perfil_id=conta.perfil_id, platform=conta.platform,
        platform_name=conta.platform_name, handle=conta.handle, url=conta.url,
        status=conta.status, notes=conta.notes, archived=conta.archived, version=conta.version,
        created_at=conta.created_at, updated_at=conta.updated_at,
        created_by=users.get(conta.created_by) if conta.created_by else None,
        updated_by=users.get(conta.updated_by) if conta.updated_by else None,
    )


def versions_out(db: Session, entity_type: str, entity_id: uuid.UUID) -> schemas.VersionsList:
    """Histórico da entidade, da versão mais recente para a mais antiga."""
    rows = history.list_versions(db, entity_type, entity_id)
    users = user_refs(db, [r.actor_user_id for r in rows])
    return schemas.VersionsList(items=[
        schemas.Version(
            version=r.version, action=r.action,
            actor=users.get(r.actor_user_id) if r.actor_user_id else None,
            actor_kind=r.actor_kind, occurred_at=r.occurred_at,
            changed_fields=list(r.changed_fields), before=r.before, after=r.after,
            details=r.details,
        )
        for r in rows
    ])


# ---- consultas ----

def list_perfis(
    db: Session, q: str | None = None, status: PerfilStatus | None = None,
    archived: bool = False,
) -> list[schemas.Perfil]:
    """Ordenado por nome. `archived=True` lista só os arquivados; o padrão, só os ativos."""
    query = select(Perfil)
    query = query.where(Perfil.archived_at.is_not(None) if archived
                        else Perfil.archived_at.is_(None))
    if status is not None:
        query = query.where(Perfil.status == status)
    term = (q or "").strip()
    if term:
        query = query.where(
            func.lower(Perfil.name).like(f"%{_escape_like(term.lower())}%", escape="\\")
        )
    perfis = db.scalars(query.order_by(func.lower(Perfil.name), Perfil.slug)).all()
    return _perfis_out(db, perfis)


def slug_suggestion(db: Session, name: str) -> str:
    """Slug derivado do nome; se já estiver em uso, acrescenta `-2`, `-3`…"""
    base = suggest_slug(name)
    if len(base) < 2 or not _slug_taken(db, base):
        return base
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = base[: SLUG_MAX - len(suffix)].rstrip("-") + suffix
        if not _slug_taken(db, candidate):
            return candidate
        n += 1


def get_perfil(db: Session, perfil_id: uuid.UUID) -> schemas.PerfilDetail:
    """O perfil e todas as contas dele, inclusive as arquivadas (com a flag)."""
    perfil = get_perfil_or_404(db, perfil_id)
    contas = db.scalars(
        select(Conta).where(Conta.perfil_id == perfil.id)
        .order_by(Conta.archived_at.is_not(None), Conta.platform, Conta.handle)
    ).all()
    users = user_refs(db, [u for c in contas for u in (c.created_by, c.updated_by)])
    return schemas.PerfilDetail(perfil=_perfis_out(db, [perfil])[0],
                                contas=[conta_out(db, c, users) for c in contas])


def perfil_versions(db: Session, perfil_id: uuid.UUID) -> schemas.VersionsList:
    get_perfil_or_404(db, perfil_id)
    return versions_out(db, ENTITY, perfil_id)


# ---- mutações ----

def create_perfil(db: Session, actor: Actor, data: schemas.CreatePerfilIn) -> Perfil:
    if _slug_taken(db, data.slug):
        raise _slug_in_use()
    perfil = Perfil(
        slug=data.slug, name=data.name, niche=data.niche, bio=data.bio, language=data.language,
        status=data.status, created_by=actor.user_id, updated_by=actor.user_id,
    )
    db.add(perfil)
    try:  # corrida entre a checagem e o INSERT: o UNIQUE do banco decide, com o mesmo 409
        db.flush()
    except IntegrityError as exc:
        raise _slug_in_use() from exc
    history.record(db, actor, ENTITY, perfil, "created", None, history.snapshot(perfil))
    return perfil


def update_perfil(
    db: Session, actor: Actor, perfil_id: uuid.UUID, data: schemas.UpdatePerfilIn
) -> Perfil:
    """Só os campos enviados. Sem mudança real, não grava versão nem toca em `updated_*`."""
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    history.check_version(perfil, data.version, LABEL)
    before = history.snapshot(perfil)
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    for field, value in changes.items():
        if value is not None:
            setattr(perfil, field, value)
    after = history.snapshot(perfil)
    if after == before:
        return perfil
    perfil.updated_by = actor.user_id
    history.record(db, actor, ENTITY, perfil, "updated", before, after)
    return perfil


def archive_perfil(db: Session, actor: Actor, perfil_id: uuid.UUID, version: int) -> Perfil:
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    history.check_version(perfil, version, LABEL)
    if perfil.archived:
        raise ApiError(409, "conflict", "Este perfil já está arquivado")
    before = history.snapshot(perfil)
    perfil.archived_at = datetime.now(UTC)
    perfil.archived_by = actor.user_id
    perfil.updated_by = actor.user_id
    history.record(db, actor, ENTITY, perfil, "archived", before, history.snapshot(perfil))
    return perfil


def restore_perfil(db: Session, actor: Actor, perfil_id: uuid.UUID, version: int) -> Perfil:
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    history.check_version(perfil, version, LABEL)
    if not perfil.archived:
        raise ApiError(409, "conflict", "Este perfil não está arquivado")
    before = history.snapshot(perfil)
    perfil.archived_at = None
    perfil.archived_by = None
    perfil.updated_by = actor.user_id
    history.record(db, actor, ENTITY, perfil, "restored", before, history.snapshot(perfil))
    return perfil


# ---- reversão (US4, FR-013: só o dono; a rota usa `RequireOwner`) ----

def target_state(db: Session, entity_type: str, entity: Perfil | Conta,
                 to_version: int) -> dict:
    """O snapshot da versão `to_version`, pronto para reverter; recusa a versão atual (400)."""
    if to_version == entity.version:
        raise ApiError(400, "validation_error", "Já é a versão atual")
    state = history.version_state(db, entity_type, entity.id, to_version)
    if state is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    return state


def apply_archived(entity: Perfil | Conta, archived: bool, actor: Actor) -> None:
    """Arquiva ou restaura conforme o snapshot; quem já está no estado certo fica como está."""
    if archived and not entity.archived:
        entity.archived_at = datetime.now(UTC)
        entity.archived_by = actor.user_id
    elif not archived and entity.archived:
        entity.archived_at = None
        entity.archived_by = None


def _revert_image(
    db: Session, perfil: Perfil, raw: str | None, kind: ImageKind
) -> uuid.UUID | None:
    """A imagem da versão alvo volta se existir, for deste perfil e do mesmo tipo."""
    if raw is None:
        return None
    image = db.get(Image, uuid.UUID(raw))
    if image is None or image.perfil_id != perfil.id or image.kind != kind:
        raise ApiError(409, "revert_conflict", "A imagem dessa versão não está disponível")
    return image.id


def revert_perfil(
    db: Session, actor: Actor, perfil_id: uuid.UUID, version: int, to_version: int
) -> Perfil:
    """Volta os campos da versão alvo, menos os imutáveis (slug), numa versão nova `reverted`."""
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    history.check_version(perfil, version, LABEL)
    state = target_state(db, ENTITY, perfil, to_version)
    before = history.snapshot(perfil)

    perfil.name = state["name"]
    perfil.niche = state["niche"]
    perfil.bio = state["bio"]
    perfil.language = state["language"]
    perfil.status = PerfilStatus(state["status"])
    perfil.logo_image_id = _revert_image(db, perfil, state["logo_image_id"], ImageKind.logo)
    perfil.banner_image_id = _revert_image(db, perfil, state["banner_image_id"],
                                           ImageKind.banner)
    apply_archived(perfil, state["archived"], actor)

    after = history.snapshot(perfil)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    perfil.updated_by = actor.user_id
    history.record(db, actor, ENTITY, perfil, "reverted", before, after,
                   {"from_version": to_version})
    return perfil
