"""Kit de marca do perfil (T012, contracts/http-api.md "Kit"; R10).

O kit é preguiçoso: sem linha em `brand_kits`, o GET devolve `default_kit()` com `version: 0`,
e o primeiro PUT (com `version: 0`) cria a v1 (`created`). O PUT troca o kit inteiro, porque os
tokens dependem uns dos outros (paleta e fontes). Toda mutação trava a linha do perfil, faz
`check_version` e grava a versão em `entity_versions` na mesma transação, com um snapshot por
seção (o histórico diz "hook" ou "caption"). Só o dono reverte (a rota usa `RequireOwner`).

Spec 029 (FR-013): o fundo e a marca d'água vêm da biblioteca da agência, de qualquer perfil
base ou sem perfil; o uso no kit continua bloqueando o arquivar do asset.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sociman_api import history, imaging, midia
from sociman_api.assets.models import Asset, AssetFile
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.ia import aplicacao
from sociman_api.marca import schemas
from sociman_api.marca.models import KIT_SECTIONS, BrandFont, BrandKit
from sociman_api.marca.openshorts import openshorts_section
from sociman_api.marca.tokens import (
    DEFAULT_FONTS,
    DEFAULT_PREFIX,
    KitInvalid,
    KitTokens,
    RefContext,
    check_refs,
    default_kit,
    font_refs,
    fundo_image_ids,
    image_fields,
    perfil_font_id,
    resolve_tokens,
)
from sociman_api.perfis.models import Conta, ContaStatus, Image, ImageKind, Perfil
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import (
    get_perfil_or_404,
    target_state,
    user_refs,
    versions_out,
)

ENTITY = "kit"
LABEL = "Este kit"
EXPORT_SCHEMA = "sociman.kit/1"


# ---- auxiliares ----

def _row(db: Session, perfil_id: uuid.UUID, lock: bool = False) -> BrandKit | None:
    stmt = select(BrandKit).where(BrandKit.perfil_id == perfil_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _first_active_conta(db: Session, perfil_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(Conta.id).where(
            Conta.perfil_id == perfil_id, Conta.status == ContaStatus.ativa,
            Conta.archived_at.is_(None),
        ).order_by(Conta.created_at, Conta.id).limit(1)
    )


def current_tokens(db: Session, perfil_id: uuid.UUID) -> tuple[KitTokens, BrandKit | None]:
    """Os tokens vigentes do perfil (os salvos ou o padrão) e a linha, se existir.

    Público: o envio de corte usa isto para registrar `kit_version` e `kit_tokens`.
    """
    row = _row(db, perfil_id)
    if row is None:
        return default_kit(_first_active_conta(db, perfil_id)), None
    return KitTokens.from_sections({s: getattr(row, s) for s in KIT_SECTIONS}), row


def _imagens_kit(kit: KitTokens | None) -> list[uuid.UUID]:
    if kit is None:
        return []
    return [image_id for _, image_id in image_fields(kit)]


def ref_context(db: Session, perfil: Perfil, kit: KitTokens | None = None) -> RefContext:
    """O que `check_refs` precisa do banco: fontes ativas, logo e contas do perfil e as imagens
    que o kit cita (da biblioteca da agência, spec 029)."""
    fonts = db.scalars(select(BrandFont.id).where(
        BrandFont.perfil_id == perfil.id, BrandFont.archived_at.is_(None)))
    contas = db.scalars(select(Conta.id).where(
        Conta.perfil_id == perfil.id, Conta.archived_at.is_(None)))
    citadas = _imagens_kit(kit)
    images = db.execute(select(Image.id, Image.kind).where(
        Image.id.in_(citadas), Image.kind.in_((ImageKind.watermark, ImageKind.fundo))
    )).all() if citadas else []
    # Spec 007: a imagem precisa estar em arquivo ativo de asset ativo da biblioteca. Imagem sem
    # asset (só por inserção direta; a migração 0005 pôs todas na biblioteca) segue valendo.
    arquivadas = db.scalars(
        select(AssetFile.image_id).join(Asset, Asset.id == AssetFile.asset_id).where(
            AssetFile.image_id.in_(citadas),
            or_(AssetFile.archived_at.is_not(None), Asset.archived_at.is_not(None)))
    ) if citadas else []
    return RefContext(
        archived_image_ids=frozenset(arquivadas),
        active_font_ids=frozenset(fonts), has_logo=perfil.logo_image_id is not None,
        conta_ids=frozenset(contas),
        watermark_image_ids=frozenset(i for i, k in images if k == ImageKind.watermark),
        fundo_image_ids=frozenset(i for i, k in images if k == ImageKind.fundo),
    )


def _invalid(exc: KitInvalid) -> ApiError:
    return ApiError(400, "invalid_kit", f"{exc.field}: {exc.message}",
                    details={"field": exc.field})


def _kit_out(db: Session, perfil_id: uuid.UUID, tokens: KitTokens,
             row: BrandKit | None) -> schemas.Kit:
    updated_by = None
    if row is not None and row.updated_by is not None:
        updated_by = user_refs(db, [row.updated_by]).get(row.updated_by)
    return schemas.Kit(
        **tokens.model_dump(), perfil_id=perfil_id,
        version=row.version if row else 0, persisted=row is not None,
        updated_at=row.updated_at if row else None, updated_by=updated_by,
    )


def _saved_out(db: Session, row: BrandKit) -> schemas.Kit:
    db.flush()
    db.refresh(row)  # updated_at vem do banco
    tokens = KitTokens.from_sections({s: getattr(row, s) for s in KIT_SECTIONS})
    return _kit_out(db, row.perfil_id, tokens, row)


def font_options(db: Session, perfil_id: uuid.UUID) -> list[schemas.FontOption]:
    """Fontes padrão mais as ativas do perfil, por nome (FR-010, US2-4)."""
    options = [
        schemas.FontOption(ref=f.ref, name=f.name, family=f.family,
                           url=f"/api/fontes-padrao/{f.key}")
        for f in DEFAULT_FONTS.values()
    ]
    fonts = db.scalars(
        select(BrandFont).where(BrandFont.perfil_id == perfil_id,
                                BrandFont.archived_at.is_(None))
        .order_by(BrandFont.name)
    )
    options += [
        schemas.FontOption(ref=f"perfil:{f.id}", name=f.name, family=f.family,
                           url=midia.link("fonte", f.id).url)
        for f in fonts
    ]
    return options


# ---- consultas ----

def get_kit(db: Session, perfil_id: uuid.UUID) -> schemas.KitGet:
    get_perfil_or_404(db, perfil_id)
    tokens, row = current_tokens(db, perfil_id)
    return schemas.KitGet(kit=_kit_out(db, perfil_id, tokens, row),
                          font_options=font_options(db, perfil_id))


def kit_versions(db: Session, perfil_id: uuid.UUID) -> VersionsList:
    get_perfil_or_404(db, perfil_id)
    row = _row(db, perfil_id)
    if row is None:
        return VersionsList(items=[])
    return versions_out(db, ENTITY, row.id)


# ---- mutações ----

def put_kit(db: Session, actor: Actor, perfil_id: uuid.UUID, data: schemas.KitIn) -> schemas.Kit:
    """Cria (versão 0 → 1) ou troca o kit inteiro. Sem mudança real, não grava versão."""
    # A trava do perfil serializa o primeiro salvamento (sem linha para travar ainda).
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    tokens = KitTokens.model_validate(data.model_dump(exclude={"version", "ia"}))
    row = _row(db, perfil_id, lock=True)
    if row is None:
        if data.version != 0:
            raise ApiError(409, "version_conflict", f"{LABEL} foi alterado por outra pessoa; recarregue")
    else:
        history.check_version(row, data.version, LABEL)
    try:
        check_refs(tokens, ref_context(db, perfil, tokens))
    except KitInvalid as exc:
        raise _invalid(exc) from exc

    sections = tokens.sections()
    if row is None:
        row = BrandKit(perfil_id=perfil_id, created_by=actor.user_id,
                       updated_by=actor.user_id, **sections)
        db.add(row)
        db.flush()
        after = history.snapshot(row)
        details = aplicacao.marcar(db, actor, ENTITY, row, None, after, data.ia)
        history.record(db, actor, ENTITY, row, "created", None, after, details)
        return _saved_out(db, row)

    before = history.snapshot(row)
    for section, value in sections.items():
        setattr(row, section, value)
    after = history.snapshot(row)
    if after == before:
        return _saved_out(db, row)
    row.updated_by = actor.user_id
    details = aplicacao.marcar(db, actor, ENTITY, row, before, after, data.ia)
    history.record(db, actor, ENTITY, row, "updated", before, after, details)
    return _saved_out(db, row)


def revert_kit(db: Session, actor: Actor, perfil_id: uuid.UUID, version: int,
               to_version: int) -> schemas.Kit:
    """Volta as seções da versão alvo numa versão nova `reverted` (só o dono, FR-007)."""
    perfil = get_perfil_or_404(db, perfil_id, lock=True)
    row = _row(db, perfil_id, lock=True)
    if row is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    history.check_version(row, version, LABEL)
    state = target_state(db, ENTITY, row, to_version)
    tokens = KitTokens.from_sections({s: state[s] for s in KIT_SECTIONS})

    ctx = ref_context(db, perfil, tokens)
    for ref in font_refs(tokens):
        font_id = perfil_font_id(ref)
        if font_id is not None and font_id not in ctx.active_font_ids:
            font = db.get(BrandFont, font_id)
            name = font.name if font is not None else ref
            raise ApiError(409, "revert_conflict",
                           f"A versão usa a fonte {name}, que está arquivada; restaure-a antes")
    try:
        check_refs(tokens, ctx)
    except KitInvalid as exc:
        raise ApiError(409, "revert_conflict",
                       f"Essa versão não vale mais ({exc.field}: {exc.message})") from exc

    before = history.snapshot(row)
    for section, value in tokens.sections().items():
        setattr(row, section, value)
    after = history.snapshot(row)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    row.updated_by = actor.user_id
    history.record(db, actor, ENTITY, row, "reverted", before, after,
                   {"from_version": to_version})
    return _saved_out(db, row)


# ---- exportação (US3, FR-011, R9) ----

def _export_fonts(db: Session, tokens: KitTokens) -> tuple[dict[str, dict[str, Any]],
                                                           list[schemas.ExportAsset]]:
    """Cada fonte do kit como `{ref, name, family, style, url}`, e os assets das do perfil
    (links assinados sem validade: valem enquanto o arquivo existir)."""
    fonts: dict[str, dict[str, Any]] = {}
    assets: list[schemas.ExportAsset] = []
    for ref in font_refs(tokens):
        font_id = perfil_font_id(ref)
        if font_id is None:
            f = DEFAULT_FONTS[ref[len(DEFAULT_PREFIX):]]
            fonts[ref] = {"ref": ref, "name": f.name, "family": f.family, "style": f.style,
                          "url": f"/api/fontes-padrao/{f.key}"}
            continue
        font = db.get(BrandFont, font_id)  # nunca apagada; arquivada ainda exporta
        if font is None:
            raise ApiError(409, "conflict", f"A fonte {ref} do kit não existe")
        url = midia.link("fonte", font.id, ttl=None).url
        fonts[ref] = {"ref": ref, "name": font.name, "family": font.family,
                      "style": font.style, "url": url}
        assets.append(schemas.ExportAsset(ref=ref, name=font.name, url=url, expires_at=None))
    return fonts, assets


def export_kit(db: Session, perfil_id: uuid.UUID) -> tuple[schemas.KitExport, str]:
    """O documento `sociman.kit/1` e o nome do arquivo `kit-<slug>-v<versão>.json`."""
    perfil = get_perfil_or_404(db, perfil_id)
    tokens, row = current_tokens(db, perfil_id)
    version = row.version if row else 0
    fonts, font_assets = _export_fonts(db, tokens)
    # Imagens de fundo (FR-005a): link sem validade, como as fontes e a marca d'água.
    fundo_urls = {i: midia.link("fundo", i, ttl=None).url for i in fundo_image_ids(tokens)}
    resolved = resolve_tokens(tokens, fonts,
                              {i: {"fundo_imagem_url": url} for i, url in fundo_urls.items()})

    watermark = resolved["watermark"]
    wm = tokens.watermark
    watermark_image = None
    if wm.conta_id is not None:
        conta = db.get(Conta, wm.conta_id)
        watermark["texto"] = f"@{conta.handle}" if conta is not None else None
    if wm.imagem_id is not None:
        url = midia.link("marca_dagua", wm.imagem_id, ttl=None).url
        watermark["imagem_url"] = url
        watermark_image = schemas.ExportAsset(id=wm.imagem_id, url=url, expires_at=None)
    if perfil.logo_image_id is not None:
        logo = db.get(Image, perfil.logo_image_id)
        if logo is not None:
            watermark["logo_url"] = imaging.image_urls(logo.object_key)["medium"]

    doc = schemas.KitExport(
        schema=EXPORT_SCHEMA,
        generated_at=datetime.now(UTC),
        perfil=schemas.ExportPerfil(id=perfil.id, slug=perfil.slug, name=perfil.name),
        kit=schemas.ExportKitMeta(version=version, updated_at=row.updated_at if row else None),
        tokens={
            "palette": resolved["palette"], "caption": resolved["caption"],
            "hook": resolved["hook"], "watermark": watermark, "endCard": resolved["end_card"],
            "catchphrases": resolved["catchphrases"], "series": resolved["series"],
        },
        openshorts=schemas.OpenShorts.model_validate(openshorts_section(resolved)),
        assets=schemas.ExportAssets(
            fonts=font_assets, watermark_image=watermark_image,
            background_images=[schemas.ExportAsset(id=i, url=url, expires_at=None)
                               for i, url in fundo_urls.items()],
        ),
    )
    return doc, f"kit-{perfil.slug}-v{version}.json"
