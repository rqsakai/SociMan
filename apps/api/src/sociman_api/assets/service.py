"""Biblioteca de assets do perfil (spec 007, contracts/http-api.md, research R1–R7).

Toda mutação trava a linha do asset, confere a `version` (menos o envio de arquivo, que só
acrescenta), recusa perfil arquivado (`perfil_archived`) e asset arquivado (`asset_archived`) e
grava **uma** versão do asset em `entity_versions` na mesma transação (`history.record`), com
os arquivos no snapshot. Nada é apagado: arquivos e assets são arquivados, e a reversão (só o
dono) arquiva o que não existia na versão alvo.

O envio de arquivo confere o HD (`datadir.ensure_writable`) **antes** de ler o corpo, lê até
20 MB, valida pelo conteúdo com a classe técnica do tipo (`tipos.IMAGE_KIND`) e grava o objeto
no bucket `imagens` com a chave de sempre (`perfis/{perfil_id}/{uuid4}.{ext}`).
"""

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any, BinaryIO

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import datadir, history, imaging, midia, storage
from sociman_api.assets import schemas, tipos
from sociman_api.assets.models import Asset, AssetFile, AssetTipo, FileRole, sorted_files
from sociman_api.assets.usos import UsoImagem, usos_do_perfil
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.ia import aplicacao
from sociman_api.perfis.models import Image, ImageKind, Perfil
from sociman_api.perfis.platforms import suggest_slug
from sociman_api.perfis.schemas import ImageRef, ImageUrls, VersionsList
from sociman_api.perfis.service_imagens import read_limited
from sociman_api.perfis.service_perfis import (
    apply_archived,
    get_perfil_or_404,
    target_state,
    user_refs,
    versions_out,
)

ENTITY = "asset"
LABEL = "Este asset"
NOT_FOUND = "Asset não encontrado"
POSE_LABEL_IN_USE = "Já existe uma pose com esse rótulo neste avatar"
_TEXT_FIELDS = ("name", "description", "tags", "prompt", "voice_tone", "image_rules")
_FILE_FIELDS = ("look", "uso", "label", "quando_usar", "notes")


# ---- auxiliares ----

def get_asset_or_404(db: Session, asset_id: uuid.UUID, lock: bool = False) -> Asset:
    asset = db.get(Asset, asset_id, with_for_update=lock)
    if asset is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return asset


def _perfil_ativo(db: Session, perfil_id: uuid.UUID) -> Perfil:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    return perfil


def _editavel(db: Session, asset_id: uuid.UUID, version: int | None) -> Asset:
    """Trava o asset, confere a versão, o perfil e o arquivamento (para editar)."""
    asset = get_asset_or_404(db, asset_id, lock=True)
    if version is not None:
        history.check_version(asset, version, LABEL)
    _perfil_ativo(db, asset.perfil_id)
    if asset.archived:
        raise ApiError(409, "asset_archived", "Restaure o asset antes de editar")
    return asset


def _file_or_404(asset: Asset, file_id: uuid.UUID) -> AssetFile:
    for f in asset.arquivos:
        if f.id == file_id:
            return f
    raise ApiError(404, "not_found", "Arquivo não encontrado")


def _record(db: Session, actor: Actor, asset: Asset, action: str, before: dict[str, Any] | None,
            details: dict[str, Any] | None = None,
            ia: list[aplicacao.IaAplicacao] | None = None) -> bool:
    """Grava a versão se algo mudou (criação sempre grava). Devolve se gravou. Com `ia`, marca
    as chamadas aplicadas (spec 008) na mesma transação e leva `details.ia` na versão."""
    db.flush()
    after = history.snapshot(asset)
    if before is not None and after == before:
        return False
    marca = aplicacao.marcar(db, actor, ENTITY, asset, before, after, ia)
    if marca is not None:
        details = {**(details or {}), **marca}
    asset.updated_by = actor.user_id
    history.record(db, actor, ENTITY, asset, action, before, after, details)
    return True


def _pose_label_taken(asset: Asset, label: str, exclude: uuid.UUID | None = None) -> bool:
    wanted = label.lower()
    return any(f.label is not None and f.label.lower() == wanted and f.id != exclude
               for f in asset.active_files(FileRole.pose))


def _pose_label_in_use() -> ApiError:
    return ApiError(409, "pose_label_in_use", POSE_LABEL_IN_USE)


def _flush_labels(db: Session) -> None:
    """Corrida entre a checagem e o UPDATE/INSERT: o índice único decide, com o mesmo 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        if "uq_asset_files_pose_label" in str(exc.orig):
            raise _pose_label_in_use() from exc
        raise


def _renumber(asset: Asset, role: FileRole) -> None:
    """Ordem 0..n-1 sem buracos entre os ativos do papel."""
    for i, f in enumerate(asset.active_files(role)):
        f.position = i


def _fix_primary(asset: Asset) -> None:
    """O principal é um arquivo ativo; sem ele, o primeiro ativo (ou nenhum)."""
    active = asset.active_files()
    if asset.primary_file_id not in {f.id for f in active}:
        asset.primary_file_id = active[0].id if active else None


def image_ref(img: Image) -> ImageRef:
    return ImageRef(id=img.id, width=img.width, height=img.height,
                    urls=ImageUrls(**imaging.image_urls(img.object_key)))


def _images(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, Image]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {img.id: img for img in db.scalars(select(Image).where(Image.id.in_(wanted)))}


def _uso_out(file_id: uuid.UUID, uso: UsoImagem) -> schemas.Uso:
    return schemas.Uso(origem=uso.origem, rotulo=uso.rotulo, campo=uso.campo, file_id=file_id,
                       bloqueia=uso.bloqueia, href=uso.href)


def asset_usos(asset: Asset, usos: dict[uuid.UUID, list[UsoImagem]]) -> list[schemas.Uso]:
    return [_uso_out(f.id, u) for f in sorted_files(asset.arquivos)
            for u in usos.get(f.image_id, [])]


def _in_use_error(code: str, prefix: str, usos: list[schemas.Uso]) -> ApiError:
    rotulos = ", ".join(dict.fromkeys(u.rotulo for u in usos))
    return ApiError(409, code, f"{prefix}{rotulos}",
                    details={"usos": [u.model_dump(by_alias=True, mode="json") for u in usos]})


def _blocking(db: Session, asset: Asset, files: Sequence[AssetFile]) -> list[schemas.Uso]:
    usos = usos_do_perfil(db, asset.perfil_id)
    return [_uso_out(f.id, u) for f in files for u in usos.get(f.image_id, []) if u.bloqueia]


def _download_name(perfil: Perfil | None, asset: Asset, f: AssetFile, image: Image) -> str:
    """`<slug-do-perfil>-<nome-do-asset>-<n>.<ext>` (contracts, Mídia)."""
    stem = suggest_slug(asset.name) or "asset"
    slug = perfil.slug if perfil is not None else "perfil"
    return f"{slug}-{stem}-{f.position + 1}{PurePath(image.object_key).suffix}"


def asset_download_name(db: Session, image: Image) -> str:
    """Nome do `?download=1` do link `imagem`; imagem fora da biblioteca usa o id."""
    f = db.scalar(select(AssetFile).where(AssetFile.image_id == image.id))
    perfil = db.get(Perfil, image.perfil_id)
    if f is None:
        slug = perfil.slug if perfil is not None else "perfil"
        return f"{slug}-imagem-{image.id.hex[:8]}{PurePath(image.object_key).suffix}"
    return _download_name(perfil, db.get(Asset, f.asset_id), f, image)


def _file_out(f: AssetFile, image: Image, users: dict) -> schemas.AssetFile:
    link = midia.link("imagem", image.id, ttl=None).url
    return schemas.AssetFile(
        id=f.id, role=f.role, look=f.look, uso=f.uso, label=f.label,
        quando_usar=f.quando_usar, notes=f.notes, position=f.position, archived=f.archived,
        image=image_ref(image), preview_url=imaging.preview_url(image.object_key),
        content_type=image.content_type, bytes=image.bytes,
        has_alpha=image.kind == ImageKind.watermark, link=link,
        download_url=f"{link}?download=1", created_at=f.created_at,
        created_by=users.get(f.created_by) if f.created_by else None,
    )


def _summary_fields(asset: Asset, images: dict[uuid.UUID, Image],
                    usos: dict[uuid.UUID, list[UsoImagem]]) -> dict[str, Any]:
    cover = None
    if asset.primary_file_id is not None:
        primary = next((f for f in asset.arquivos if f.id == asset.primary_file_id), None)
        if primary is not None and primary.image_id in images:
            cover = image_ref(images[primary.image_id])
    return {
        "id": asset.id, "perfil_id": asset.perfil_id, "tipo": asset.tipo, "name": asset.name,
        "tags": list(asset.tags), "cover": cover, "file_count": len(asset.active_files()),
        "in_use": any(usos.get(f.image_id) for f in asset.arquivos),
        "archived": asset.archived, "version": asset.version, "updated_at": asset.updated_at,
    }


def summaries_out(db: Session, perfil_id: uuid.UUID,
                  assets: Sequence[Asset]) -> list[schemas.AssetSummary]:
    usos = usos_do_perfil(db, perfil_id) if assets else {}
    primaries = {f.id: f.image_id for a in assets for f in a.arquivos
                 if f.id == a.primary_file_id}
    images = _images(db, primaries.values())
    return [schemas.AssetSummary(**_summary_fields(a, images, usos)) for a in assets]


def asset_out(db: Session, asset: Asset,
              usos: dict[uuid.UUID, list[UsoImagem]] | None = None) -> schemas.Asset:
    db.flush()
    db.refresh(asset)  # updated_at vem do banco
    if usos is None:
        usos = usos_do_perfil(db, asset.perfil_id)
    files = sorted_files(asset.arquivos)
    images = _images(db, [f.image_id for f in files])
    users = user_refs(db, [asset.created_by, asset.updated_by]
                      + [f.created_by for f in files])
    return schemas.Asset(
        **_summary_fields(asset, images, usos),
        description=asset.description, prompt=asset.prompt, voice_tone=asset.voice_tone,
        image_rules=asset.image_rules, primary_file_id=asset.primary_file_id,
        files=[_file_out(f, images[f.image_id], users) for f in files],
        created_at=asset.created_at,
        created_by=users.get(asset.created_by) if asset.created_by else None,
        updated_by=users.get(asset.updated_by) if asset.updated_by else None,
    )


def file_out(out: schemas.Asset, file_id: uuid.UUID) -> schemas.AssetFile:
    return next(f for f in out.files if f.id == file_id)


# ---- consultas ----

def get_asset(db: Session, asset_id: uuid.UUID) -> schemas.AssetDetail:
    asset = get_asset_or_404(db, asset_id)
    usos = usos_do_perfil(db, asset.perfil_id)
    return schemas.AssetDetail(asset=asset_out(db, asset, usos), usos=asset_usos(asset, usos))


def asset_versions(db: Session, asset_id: uuid.UUID) -> VersionsList:
    get_asset_or_404(db, asset_id)
    return versions_out(db, ENTITY, asset_id)


def library_images(db: Session, perfil_id: uuid.UUID, tipos_: Sequence[AssetTipo],
                   q: str | None, limit: int) -> list[schemas.LibraryImage]:
    """Arquivos ativos de assets ativos dos tipos pedidos, mais recentes primeiro (R6)."""
    get_perfil_or_404(db, perfil_id)
    stmt = (
        select(AssetFile, Asset, Image)
        .join(Asset, Asset.id == AssetFile.asset_id)
        .join(Image, Image.id == AssetFile.image_id)
        .where(Asset.perfil_id == perfil_id, Asset.tipo.in_(list(tipos_)),
               Asset.archived_at.is_(None), AssetFile.archived_at.is_(None))
    )
    term = (q or "").strip().lower()
    if term:
        stmt = stmt.where(or_(
            func.lower(Asset.name).like(f"%{escape_like(term)}%", escape="\\"),
            func.lower(func.coalesce(AssetFile.label, "")).like(f"%{escape_like(term)}%",
                                                                escape="\\"),
            Asset.tags.contains([term]),
        ))
    stmt = stmt.order_by(AssetFile.created_at.desc(), AssetFile.id).limit(limit)
    return [
        schemas.LibraryImage(image=image_ref(img), asset_id=a.id, asset_name=a.name,
                             asset_tipo=a.tipo, file_id=f.id, label=f.label,
                             has_alpha=img.kind == ImageKind.watermark)
        for f, a, img in db.execute(stmt).all()
    ]


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---- criação ----

def create_asset(db: Session, actor: Actor, perfil_id: uuid.UUID,
                 data: schemas.AssetCreate) -> Asset:
    _perfil_ativo(db, perfil_id)
    values = data.model_dump(exclude={"tipo"})
    schemas.check_campos(data.tipo, values)
    asset = Asset(perfil_id=perfil_id, tipo=data.tipo, created_by=actor.user_id,
                  updated_by=actor.user_id, **values)
    db.add(asset)
    db.flush()
    _record(db, actor, asset, "created", None)
    return asset


def _store_image(db: Session, actor: Actor, perfil_id: uuid.UUID, tipo: AssetTipo,
                 stream: BinaryIO) -> Image:
    """HD conferido, corpo lido até 20 MB, validado pelo conteúdo e gravado no bucket."""
    datadir.ensure_writable()  # HD fora ou cheio: 503/507 antes de ler o corpo
    data = read_limited(stream, max_bytes=tipos.MAX_BYTES)
    kind = tipos.IMAGE_KIND[tipo]
    info = imaging.validate_image(data, kind.value, max_bytes=tipos.MAX_BYTES,
                                  transparency_message=tipos.transparency_message(tipo),
                                  too_large_message=tipos.TOO_LARGE,
                                  opaque_format_message=tipos.transparency_message(tipo))
    key = f"perfis/{perfil_id}/{uuid.uuid4()}.{info.ext}"
    # O objeto vai antes do commit; se a transação falhar, sobra um objeto sem referência
    # (nunca apagamos objetos), o que é inofensivo.
    storage.put(key, data, info.content_type)
    image = Image(perfil_id=perfil_id, kind=kind, object_key=key,
                  content_type=info.content_type, bytes=info.bytes, width=info.width,
                  height=info.height, sha256=info.sha256, created_by=actor.user_id)
    db.add(image)
    db.flush()
    return image


def _attach(db: Session, actor: Actor, asset: Asset, image: Image, role: FileRole,
            meta: dict[str, Any]) -> AssetFile:
    f = AssetFile(asset_id=asset.id, image_id=image.id, role=role,
                  position=len(asset.active_files(role)), created_by=actor.user_id,
                  notes=meta.get("notes") or "",
                  **{k: meta.get(k) for k in ("look", "uso", "label", "quando_usar")})
    db.add(f)
    asset.arquivos.append(f)
    _flush_labels(db)
    if asset.primary_file_id is None:
        asset.primary_file_id = f.id
    return f


def upload_file(db: Session, actor: Actor, asset_id: uuid.UUID, stream: BinaryIO,
                role: FileRole, meta: dict[str, Any]) -> tuple[Asset, AssetFile]:
    """Acrescenta um arquivo (sem `version`: não há atualização perdida). O primeiro vira o
    principal."""
    asset = _editavel(db, asset_id, None)
    schemas.check_file_campos(asset.tipo, role, meta)
    if role == FileRole.pose and not meta.get("label"):
        raise schemas.invalid("label", "informe o rótulo da pose")
    if asset.tipo in tipos.SINGLE_FILE and asset.active_files():
        raise schemas.invalid("file", "este tipo aceita um arquivo só")
    if role == FileRole.pose and _pose_label_taken(asset, meta["label"]):
        raise _pose_label_in_use()
    before = history.snapshot(asset)
    image = _store_image(db, actor, asset.perfil_id, asset.tipo, stream)
    f = _attach(db, actor, asset, image, role, meta)
    _record(db, actor, asset, "updated", before)
    return asset, f


def upload_asset(db: Session, actor: Actor, perfil_id: uuid.UUID, stream: BinaryIO,
                 tipo: AssetTipo, name: str, tags: list[str]) -> tuple[Asset, AssetFile]:
    """Atalho "um arquivo = um asset" (envio múltiplo e seletores do kit): uma versão só."""
    if tipo not in tipos.SHORTCUT:
        raise schemas.invalid("tipo", "use o cadastro do avatar ou do cenário")
    _perfil_ativo(db, perfil_id)
    image = _store_image(db, actor, perfil_id, tipo, stream)
    return _asset_from_image(db, actor, perfil_id, image, tipo, name, tags)


def _asset_from_image(db: Session, actor: Actor, perfil_id: uuid.UUID, image: Image,
                      tipo: AssetTipo, name: str, tags: list[str]) -> tuple[Asset, AssetFile]:
    asset = Asset(perfil_id=perfil_id, tipo=tipo, name=name, tags=tags,
                  created_by=actor.user_id, updated_by=actor.user_id)
    db.add(asset)
    db.flush()
    f = _attach(db, actor, asset, image, FileRole.arquivo, {})
    _record(db, actor, asset, "created", None)
    return asset, f


def asset_for_legacy_image(db: Session, actor: Actor, image: Image) -> Asset:
    """As rotas antigas da 004 (`/marca-dagua`, `/fundos`) também criam o asset, para nenhuma
    imagem de kit ficar fora da biblioteca (R2). Nome "Marca d'água N" / "Fundo N"."""
    tipo = AssetTipo.marca_dagua if image.kind == ImageKind.watermark else AssetTipo.fundo
    n = db.scalar(select(func.count()).select_from(Asset).where(
        Asset.perfil_id == image.perfil_id, Asset.tipo == tipo)) or 0
    asset, _ = _asset_from_image(db, actor, image.perfil_id, image, tipo,
                                 f"{tipos.LABELS[tipo]} {n + 1}", [])
    return asset


def default_name(filename: str | None) -> str:
    stem = PurePath(filename or "").stem.strip()
    return stem[:80].strip() or "Imagem"


# ---- edição ----

def update_asset(db: Session, actor: Actor, asset_id: uuid.UUID,
                 data: schemas.AssetPatch) -> Asset:
    """Só os campos enviados. Nulo em `prompt`, `voiceTone` e `imageRules` limpa o campo; nos
    demais, é ignorado. Sem mudança real, não grava versão."""
    asset = _editavel(db, asset_id, data.version)
    changes = data.model_dump(exclude_unset=True, exclude={"version", "ia"})
    schemas.check_campos(asset.tipo, changes)
    before = history.snapshot(asset)
    for field in _TEXT_FIELDS:
        if field not in changes:
            continue
        value = changes[field]
        if value is None and field in ("name", "description", "tags"):
            continue
        setattr(asset, field, value)
    if "primary_file_id" in changes:
        primary = changes["primary_file_id"]
        if primary not in {f.id for f in asset.active_files()}:
            raise schemas.invalid("primaryFileId", "escolha um arquivo ativo deste asset")
        asset.primary_file_id = primary
    _record(db, actor, asset, "updated", before, ia=data.ia)
    return asset


def update_file(db: Session, actor: Actor, asset_id: uuid.UUID, file_id: uuid.UUID,
                data: schemas.FilePatch) -> Asset:
    asset = _editavel(db, asset_id, data.version)
    f = _file_or_404(asset, file_id)
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    schemas.check_file_campos(asset.tipo, f.role, changes)
    if f.role == FileRole.pose and "label" in changes:
        if changes["label"] is None:
            raise schemas.invalid("label", "informe o rótulo da pose")
        if not f.archived and _pose_label_taken(asset, changes["label"], exclude=f.id):
            raise _pose_label_in_use()
    before = history.snapshot(asset)
    for field in _FILE_FIELDS:
        if field in changes:
            value = changes[field]
            setattr(f, field, "" if field == "notes" and value is None else value)
    _flush_labels(db)
    _record(db, actor, asset, "updated", before)
    return asset


def reorder(db: Session, actor: Actor, asset_id: uuid.UUID, data: schemas.Ordem) -> Asset:
    """Uma versão por reordenação; a lista precisa ter exatamente os ativos do papel."""
    asset = _editavel(db, asset_id, data.version)
    active = asset.active_files(data.role)
    if len(data.file_ids) != len(set(data.file_ids)) \
            or set(data.file_ids) != {f.id for f in active}:
        raise schemas.invalid("fileIds", "a lista precisa ter todos os arquivos ativos")
    before = history.snapshot(asset)
    by_id = {f.id: f for f in active}
    for i, fid in enumerate(data.file_ids):
        by_id[fid].position = i
    _record(db, actor, asset, "updated", before)
    return asset


def archive_file(db: Session, actor: Actor, asset_id: uuid.UUID, file_id: uuid.UUID,
                 version: int) -> Asset:
    asset = _editavel(db, asset_id, version)
    f = _file_or_404(asset, file_id)
    if f.archived:
        raise ApiError(409, "conflict", "Este arquivo já está arquivado")
    if asset.tipo in tipos.SINGLE_FILE:
        raise schemas.invalid("file", "este tipo tem um arquivo só; arquive o asset")
    blocking = _blocking(db, asset, [f])
    if blocking:
        raise _in_use_error("asset_in_use", "Em uso em: ", blocking)
    before = history.snapshot(asset)
    f.archived_at = datetime.now(UTC)
    f.archived_by = actor.user_id
    _renumber(asset, f.role)
    _fix_primary(asset)
    _record(db, actor, asset, "updated", before)
    return asset


def restore_file(db: Session, actor: Actor, asset_id: uuid.UUID, file_id: uuid.UUID,
                 version: int) -> Asset:
    """Volta ao fim da ordem; sem principal, vira o principal."""
    asset = _editavel(db, asset_id, version)
    f = _file_or_404(asset, file_id)
    if not f.archived:
        raise ApiError(409, "conflict", "Este arquivo não está arquivado")
    if asset.tipo in tipos.SINGLE_FILE and asset.active_files():
        raise schemas.invalid("file", "este tipo aceita um arquivo só")
    if f.role == FileRole.pose and _pose_label_taken(asset, f.label or "", exclude=f.id):
        raise _pose_label_in_use()
    before = history.snapshot(asset)
    f.position = len(asset.active_files(f.role))
    f.archived_at = None
    f.archived_by = None
    _flush_labels(db)
    if asset.primary_file_id is None:
        asset.primary_file_id = f.id
    _record(db, actor, asset, "updated", before)
    return asset


def archive_asset(db: Session, actor: Actor, asset_id: uuid.UUID, version: int) -> Asset:
    """Só o uso no kit bloqueia (Q1 = A); os arquivos ficam como estão."""
    asset = get_asset_or_404(db, asset_id, lock=True)
    history.check_version(asset, version, LABEL)
    _perfil_ativo(db, asset.perfil_id)
    if asset.archived:
        raise ApiError(409, "conflict", "Este asset já está arquivado")
    blocking = _blocking(db, asset, asset.arquivos)
    if blocking:
        raise _in_use_error("asset_in_use", "Em uso em: ", blocking)
    before = history.snapshot(asset)
    asset.archived_at = datetime.now(UTC)
    asset.archived_by = actor.user_id
    _record(db, actor, asset, "archived", before)
    return asset


def restore_asset(db: Session, actor: Actor, asset_id: uuid.UUID, version: int) -> Asset:
    asset = get_asset_or_404(db, asset_id, lock=True)
    history.check_version(asset, version, LABEL)
    _perfil_ativo(db, asset.perfil_id)
    if not asset.archived:
        raise ApiError(409, "conflict", "Este asset não está arquivado")
    before = history.snapshot(asset)
    asset.archived_at = None
    asset.archived_by = None
    _record(db, actor, asset, "restored", before)
    return asset


# ---- reversão (R4: só o dono; a rota usa `RequireOwner`) ----

def revert_asset(db: Session, actor: Actor, asset_id: uuid.UUID, version: int,
                 to_version: int) -> Asset:
    """Volta campos, metadado, ordem e arquivamento dos arquivos da versão alvo numa versão
    nova `reverted`. Arquivo que não existia na versão alvo é arquivado (nunca apagado)."""
    asset = get_asset_or_404(db, asset_id, lock=True)
    history.check_version(asset, version, LABEL)
    _perfil_ativo(db, asset.perfil_id)
    state = target_state(db, ENTITY, asset, to_version)
    before = history.snapshot(asset)
    now = datetime.now(UTC)

    for field in _TEXT_FIELDS:
        setattr(asset, field, state[field])
    target_files = {uuid.UUID(f["id"]): f for f in state["files"]}
    newly_archived: list[AssetFile] = []
    for f in asset.arquivos:
        snap = target_files.get(f.id)
        archived = True if snap is None else snap["archived"]
        if snap is not None:
            for field in _FILE_FIELDS:
                setattr(f, field, snap[field])
            f.position = snap["position"]
        if archived and not f.archived:
            f.archived_at, f.archived_by = now, actor.user_id
            newly_archived.append(f)
        elif not archived and f.archived:
            f.archived_at, f.archived_by = None, None
    for role in FileRole:
        _renumber(asset, role)
    primary = state["primary_file_id"]
    asset.primary_file_id = uuid.UUID(primary) if primary else None
    _fix_primary(asset)
    apply_archived(asset, state["archived"], actor)

    blocking_files = list(asset.arquivos) if asset.archived and not before["archived"] \
        else newly_archived
    blocking = _blocking(db, asset, blocking_files)
    if blocking:
        raise _in_use_error("revert_conflict", "A versão arquivaria a imagem usada em ",
                            blocking)
    labels = [f.label.lower() for f in asset.active_files(FileRole.pose) if f.label]
    if len(labels) != len(set(labels)):
        raise _pose_label_in_use()
    _flush_labels(db)
    if history.snapshot(asset) == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    _record(db, actor, asset, "reverted", before, {"from_version": to_version})
    return asset
