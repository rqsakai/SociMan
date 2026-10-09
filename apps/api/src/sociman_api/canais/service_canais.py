"""Canais-fonte (US1, contracts/http-api.md "Canais").

Toda mutação humana checa a versão, grava o histórico (`canal`) na mesma transação e nunca
apaga: arquivar tira o canal da sync e da descoberta, mas vídeos e envios ficam. O direito é
informativo e só o dono o muda (princípio II; o `RequireOwner` fica na rota), como a reversão.
A sync (estado de job: `sync_*`, `next_sync_at`) não gera versão.
"""

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history, imaging
from sociman_api.auth.deps import Actor
from sociman_api.canais import schemas, youtube
from sociman_api.canais.models import CanalDireito, CanalFonte, CanalPerfil, CanalSync, VideoFonte
from sociman_api.canais.resolve import Consulta, resolver_entrada
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Perfil
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import (
    apply_archived,
    target_state,
    user_refs,
    versions_out,
)

ENTITY = "canal"
LABEL = "Este canal"
NOT_FOUND = "Canal não encontrado"
AVATAR_PX = 176


# ---- saída ----

def _perfis_ref(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, schemas.PerfilRef]:
    wanted = set(ids)
    if not wanted:
        return {}
    rows = db.execute(select(Perfil.id, Perfil.name, Perfil.slug).where(Perfil.id.in_(wanted)))
    return {pid: schemas.PerfilRef(id=pid, name=name, slug=slug) for pid, name, slug in rows}


def _contagem_videos(db: Session, canal_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not canal_ids:
        return {}
    rows = db.execute(select(VideoFonte.canal_id, func.count()).where(
        VideoFonte.canal_id.in_(canal_ids)).group_by(VideoFonte.canal_id))
    return {canal_id: n for canal_id, n in rows}


def canais_out(db: Session, canais: Sequence[CanalFonte]) -> list[schemas.CanalFonte]:
    perfis = _perfis_ref(db, (link.perfil_id for c in canais for link in c.perfil_links))
    users = user_refs(db, (c.created_by for c in canais))
    videos = _contagem_videos(db, [c.id for c in canais])
    out = []
    for c in canais:
        progress = c.sync_progress or {}
        refs = [perfis[link.perfil_id] for link in c.perfil_links if link.perfil_id in perfis]
        out.append(schemas.CanalFonte(
            id=c.id, youtube_channel_id=c.youtube_channel_id, handle=c.handle, title=c.title,
            avatar_url=imaging.remote_url(c.avatar_url, AVATAR_PX, AVATAR_PX),
            subscribers=c.subscribers, video_count=c.video_count, direito=c.direito,
            direito_evidencia_url=c.direito_evidencia_url,
            direito_evidencia_nota=c.direito_evidencia_nota,
            perfis=sorted(refs, key=lambda p: p.name.lower()),
            sync=schemas.SyncInfo(
                status=c.sync_status, lidos=progress.get("lidos"), total=progress.get("total"),
                erro=c.sync_error, last_synced_at=c.last_synced_at, next_sync_at=c.next_sync_at,
            ),
            videos_conhecidos=videos.get(c.id, 0), archived=c.archived, version=c.version,
            created_at=c.created_at,
            created_by=users.get(c.created_by) if c.created_by else None,
        ))
    return out


def canal_out(db: Session, canal: CanalFonte) -> schemas.CanalFonte:
    return canais_out(db, [canal])[0]


# ---- consultas ----

def get_canal(db: Session, canal_id: uuid.UUID, lock: bool = False) -> CanalFonte:
    canal = db.get(CanalFonte, canal_id, with_for_update=lock)
    if canal is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return canal


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_canais(db: Session, archived: bool = False, perfil_id: uuid.UUID | None = None,
                q: str | None = None) -> list[schemas.CanalFonte]:
    """Por nome. `archived=True` lista só os arquivados; o padrão, só os ativos."""
    stmt = select(CanalFonte).where(CanalFonte.archived_at.is_not(None) if archived
                                    else CanalFonte.archived_at.is_(None))
    if perfil_id is not None:
        stmt = stmt.where(CanalFonte.id.in_(
            select(CanalPerfil.canal_id).where(CanalPerfil.perfil_id == perfil_id)))
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(or_(CanalFonte.title.ilike(like, escape="\\"),
                              CanalFonte.handle.ilike(like, escape="\\")))
    stmt = stmt.order_by(func.lower(CanalFonte.title), CanalFonte.id)
    return canais_out(db, list(db.scalars(stmt)))


def list_versions(db: Session, canal_id: uuid.UUID) -> VersionsList:
    get_canal(db, canal_id)
    return versions_out(db, ENTITY, canal_id)


def _existente(db: Session, channel_id: str) -> uuid.UUID | None:
    return db.scalar(select(CanalFonte.id).where(CanalFonte.youtube_channel_id == channel_id))


def resolver(db: Session, client: youtube.YoutubeClient, entrada: str) -> schemas.ResolverOut:
    """Prévia do canal, sem gravar. Já cadastrado (inclusive arquivado) vem em `existente`."""
    consulta: Consulta = resolver_entrada(entrada)
    if consulta.tipo == "id" and (existing := _existente(db, consulta.valor)) is not None:
        # Não gasta cota para mostrar o que já temos.
        canal = get_canal(db, existing)
        return schemas.ResolverOut(candidato=_candidato_do_canal(canal), custo=0,
                                   existente=schemas.Existente(id=existing))
    info = client.canal(consulta)
    existing = _existente(db, info.youtube_channel_id)
    return schemas.ResolverOut(
        candidato=schemas.CanalCandidato(
            youtube_channel_id=info.youtube_channel_id, title=info.title, handle=info.handle,
            avatar_url=imaging.remote_url(info.avatar_url, AVATAR_PX, AVATAR_PX),
            subscribers=info.subscribers, video_count=info.video_count,
        ),
        custo=consulta.custo,
        existente=schemas.Existente(id=existing) if existing else None,
    )


def _candidato_do_canal(canal: CanalFonte) -> schemas.CanalCandidato:
    return schemas.CanalCandidato(
        youtube_channel_id=canal.youtube_channel_id, title=canal.title, handle=canal.handle,
        avatar_url=imaging.remote_url(canal.avatar_url, AVATAR_PX, AVATAR_PX),
        subscribers=canal.subscribers, video_count=canal.video_count,
    )


# ---- auxiliares ----

def _canal_exists(canal_id: uuid.UUID) -> ApiError:
    return ApiError(409, "canal_exists", "Este canal já está cadastrado",
                    details={"id": str(canal_id)})


def _perfis_validos(db: Session, perfil_ids: Iterable[uuid.UUID]) -> list[uuid.UUID]:
    """Sem repetir; perfil inexistente ou arquivado → 400."""
    ids = list(dict.fromkeys(perfil_ids))
    if not ids:
        return []
    perfis = {p.id: p for p in db.scalars(select(Perfil).where(Perfil.id.in_(ids)))}
    for pid in ids:
        perfil = perfis.get(pid)
        if perfil is None:
            raise ApiError(400, "validation_error", "Perfil não encontrado")
        if perfil.archived:
            raise ApiError(400, "validation_error",
                           f"O perfil {perfil.name} está arquivado; restaure antes de ligar")
    return ids


def _ligar(canal: CanalFonte, perfil_ids: Sequence[uuid.UUID], actor: Actor) -> None:
    """Deixa as ligações iguais a `perfil_ids`, preservando as que já existiam."""
    wanted = set(perfil_ids)
    canal.perfil_links = [link for link in canal.perfil_links if link.perfil_id in wanted]
    have = {link.perfil_id for link in canal.perfil_links}
    for pid in perfil_ids:
        if pid not in have:
            canal.perfil_links.append(CanalPerfil(perfil_id=pid, created_by=actor.user_id))


def _touch(canal: CanalFonte, actor: Actor) -> None:
    canal.updated_by = actor.user_id


# ---- mutações ----

def create_canal(db: Session, actor: Actor, client: youtube.YoutubeClient,
                 body: schemas.CreateCanalIn) -> CanalFonte:
    existing = _existente(db, body.youtube_channel_id)
    if existing is not None:  # antes de gastar cota
        raise _canal_exists(existing)
    perfil_ids = _perfis_validos(db, body.perfil_ids)
    info = client.canal(Consulta("id", body.youtube_channel_id))
    canal = CanalFonte(
        id=uuid.uuid4(), youtube_channel_id=info.youtube_channel_id, handle=info.handle,
        title=info.title, avatar_url=info.avatar_url, subscribers=info.subscribers,
        video_count=info.video_count, uploads_playlist_id=info.uploads_playlist_id,
        direito=CanalDireito.sem_acordo, direito_evidencia_nota="",
        sync_status=CanalSync.pendente,
        next_sync_at=datetime.now(UTC),  # a sync começa sozinha (US2-4)
        created_by=actor.user_id, updated_by=actor.user_id,
    )
    _ligar(canal, perfil_ids, actor)
    db.add(canal)
    history.record(db, actor, ENTITY, canal, "created", None, history.snapshot(canal))
    try:
        db.flush()
    except IntegrityError as exc:  # corrida com outro cadastro do mesmo canal
        db.rollback()
        existing = _existente(db, body.youtube_channel_id)
        if existing is not None:
            raise _canal_exists(existing) from exc
        raise
    return canal


def update_canal(db: Session, actor: Actor, canal_id: uuid.UUID,
                 body: schemas.UpdateCanalIn) -> CanalFonte:
    canal = get_canal(db, canal_id, lock=True)
    history.check_version(canal, body.version, LABEL)
    before = history.snapshot(canal)
    if body.perfil_ids is not None:
        _ligar(canal, _perfis_validos(db, body.perfil_ids), actor)
    after = history.snapshot(canal)
    if not history.diff(before, after):
        return canal
    _touch(canal, actor)
    history.record(db, actor, ENTITY, canal, "updated", before, after)
    db.flush()
    return canal


def mudar_direito(db: Session, actor: Actor, canal_id: uuid.UUID,
                  body: schemas.DireitoIn) -> CanalFonte:
    """Só o dono (a rota exige `RequireOwner`). A versão guarda autor, antes e depois."""
    canal = get_canal(db, canal_id, lock=True)
    history.check_version(canal, body.version, LABEL)
    before = history.snapshot(canal)
    canal.direito = body.direito
    canal.direito_evidencia_url = body.evidencia_url or None
    canal.direito_evidencia_nota = body.evidencia_nota
    after = history.snapshot(canal)
    if not history.diff(before, after):
        return canal
    _touch(canal, actor)
    history.record(db, actor, ENTITY, canal, "updated", before, after)
    db.flush()
    return canal


def archive_canal(db: Session, actor: Actor, canal_id: uuid.UUID, version: int) -> CanalFonte:
    canal = get_canal(db, canal_id, lock=True)
    history.check_version(canal, version, LABEL)
    if canal.archived:
        raise ApiError(409, "conflict", "Este canal já está arquivado")
    before = history.snapshot(canal)
    canal.archived_at = datetime.now(UTC)
    canal.archived_by = actor.user_id
    _touch(canal, actor)
    history.record(db, actor, ENTITY, canal, "archived", before, history.snapshot(canal))
    db.flush()
    return canal


def restore_canal(db: Session, actor: Actor, canal_id: uuid.UUID, version: int) -> CanalFonte:
    canal = get_canal(db, canal_id, lock=True)
    history.check_version(canal, version, LABEL)
    if not canal.archived:
        raise ApiError(409, "conflict", "Este canal não está arquivado")
    before = history.snapshot(canal)
    canal.archived_at = None
    canal.archived_by = None
    canal.next_sync_at = datetime.now(UTC)  # volta para a sync
    _touch(canal, actor)
    history.record(db, actor, ENTITY, canal, "restored", before, history.snapshot(canal))
    db.flush()
    return canal


def revert_canal(db: Session, actor: Actor, canal_id: uuid.UUID, version: int,
                 to_version: int) -> CanalFonte:
    """Volta direito, evidência, perfis e arquivamento da versão alvo; ignora title/handle."""
    canal = get_canal(db, canal_id, lock=True)
    history.check_version(canal, version, LABEL)
    state = target_state(db, ENTITY, canal, to_version)
    before = history.snapshot(canal)

    canal.direito = CanalDireito(state["direito"])
    canal.direito_evidencia_url = state["direito_evidencia_url"]
    canal.direito_evidencia_nota = state["direito_evidencia_nota"] or ""
    perfil_ids = [uuid.UUID(p) for p in state["perfil_ids"]]
    perfis = {p.id: p for p in db.scalars(select(Perfil).where(Perfil.id.in_(perfil_ids)))}
    if any(pid not in perfis or perfis[pid].archived for pid in perfil_ids):
        raise ApiError(409, "revert_conflict",
                       "Um perfil dessa versão não está mais disponível (arquivado)")
    _ligar(canal, perfil_ids, actor)
    was_archived = canal.archived
    apply_archived(canal, state["archived"], actor)
    if was_archived and not canal.archived:
        canal.next_sync_at = datetime.now(UTC)

    after = history.snapshot(canal)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    _touch(canal, actor)
    history.record(db, actor, ENTITY, canal, "reverted", before, after,
                   {"from_version": to_version})
    db.flush()
    return canal


def sincronizar(db: Session, client: youtube.YoutubeClient, canal_id: uuid.UUID) -> CanalFonte:
    """"Sincronizar agora": antecipa a próxima volta (estado de job, sem versão)."""
    canal = get_canal(db, canal_id, lock=True)
    if canal.archived:
        raise ApiError(409, "conflict", "Este canal está arquivado")
    if canal.sync_status == CanalSync.sincronizando:
        raise ApiError(409, "sync_running", "A sincronização deste canal já está em andamento")
    if not client.configurado:
        raise ApiError(503, "youtube_unconfigured", youtube.SEM_CHAVE)
    cota = youtube.cota_atual(db, limite=client.quota_daily)
    if cota.pausada:
        raise youtube.erro_cota(cota.renova_em)
    canal.next_sync_at = datetime.now(UTC)
    db.flush()
    return canal
