"""Rotas de um asset (contracts/http-api.md da 007, "Asset"): dono e membro (`RequireUser`),
menos a reversão (`RequireOwner`). Não existe rota DELETE (FR-007, SC-004).

Spec 029: a lista, o cadastro e o atalho da biblioteca da agência (`/api/assets`), com o perfil
base opcional; o PATCH muda o perfil base (`perfilId`)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile

from sociman_api.assets import busca, schemas
from sociman_api.assets import service as svc
from sociman_api.assets.models import AssetTipo, FileRole
from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.estudio.filtros import PerfilFiltro, filtro, form_perfil
from sociman_api.perfis.schemas import RevertIn, VersionIn, VersionsList

router = APIRouter(prefix="/api/assets")

Db = DbSession
Upload = Annotated[UploadFile, File(description="PNG, JPG ou WebP até 20 MB")]
OptText = Annotated[str | None, Form(max_length=600)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _out(db, asset) -> schemas.AssetOut:
    return schemas.AssetOut(asset=svc.asset_out(db, asset))


def _blank(value: str | None) -> str | None:
    value = value.strip() if value is not None else None
    return value or None


# ---- biblioteca da agência (spec 029) ----

@router.get("", operation_id="assets_listar_agencia", response_model=schemas.AssetsList,
            responses=_errors(400, 401, 403))
def listar_agencia(
    actor: RequireUser, db: Db, perfil_id: PerfilFiltro = None,
    tipo: Annotated[list[AssetTipo] | None, Query(description="Tipos (OU)")] = None,
    tag: Annotated[list[str] | None, Query(description="Tags (E)")] = None,
    q: Annotated[str | None, Query(max_length=100, description="Nome contém ou tag igual")]
    = None,
    archived: Annotated[schemas.ArchivedFilter, Query()] = "false",
    limit: Annotated[int, Query(ge=1, le=busca.MAX_LIMIT)] = busca.DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> schemas.AssetsList:
    return busca.listar(db, filtro(db, perfil_id), tipos=tipo or (), tags=tag or (), q=q,
                        archived=archived, limit=limit, cursor=cursor, tags_por_tipo=True)


@router.post("", operation_id="assets_criar_agencia", status_code=201,
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 409))
def criar_agencia(body: schemas.AssetCreateAgencia, actor: RequireUser,
                  db: Db) -> schemas.AssetOut:
    svc.perfil_base_novo(db, body.perfil_id)
    return _out(db, svc.create_asset(db, actor, body.perfil_id, body))


@router.post("/arquivo", operation_id="assets_criar_arquivo_agencia", status_code=201,
             response_model=schemas.AssetFileOut,
             responses=_errors(400, 401, 403, 409, 503, 507))
def criar_arquivo_agencia(
    file: Upload, actor: RequireUser, db: Db,
    tipo: Annotated[AssetTipo, Form(description="fundo, sticker, marca_dagua ou imagem")],
    name: Annotated[str | None, Form(max_length=200)] = None,
    tags: Annotated[str | None, Form(max_length=1000, description="Separadas por vírgula")]
    = None,
    perfil_id: Annotated[str | None, Form(alias="perfilId", max_length=40,
                                          description="Perfil base; vazio = sem perfil")]
    = None,
) -> schemas.AssetFileOut:
    pid = form_perfil(perfil_id)
    svc.perfil_base_novo(db, pid)
    name_, tag_list = schemas.nome_e_tags(name, tags, file.filename, svc.default_name)
    asset, f = svc.upload_asset(db, actor, pid, file.file, tipo, name_, tag_list)
    out = svc.asset_out(db, asset)
    return schemas.AssetFileOut(asset=out, file=svc.file_out(out, f.id))


@router.get("/imagens", operation_id="assets_imagens_agencia",
            response_model=schemas.LibraryImagesList, responses=_errors(400, 401, 403))
def imagens_agencia(
    actor: RequireUser, db: Db,
    tipo: Annotated[list[AssetTipo], Query(description="Tipos (OU), obrigatório")],
    perfil_id: PerfilFiltro = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=busca.MAX_LIMIT)] = 60,
) -> schemas.LibraryImagesList:
    """Os seletores de imagem (kit, foto leve do produto, prova): a biblioteca da agência."""
    return schemas.LibraryImagesList(items=svc.library_images_agencia(
        db, filtro(db, perfil_id), tipo, q, limit))


# ---- um asset ----


@router.get("/{asset_id}", operation_id="assets_get", response_model=schemas.AssetDetail,
            responses=_errors(401, 403, 404))
def get(asset_id: UUID, actor: RequireUser, db: Db) -> schemas.AssetDetail:
    return svc.get_asset(db, asset_id, actor)


@router.patch("/{asset_id}", operation_id="assets_update", response_model=schemas.AssetOut,
              responses=_errors(400, 401, 403, 404, 409))
def update(asset_id: UUID, body: schemas.AssetPatch, actor: RequireUser,
           db: Db) -> schemas.AssetOut:
    return _out(db, svc.update_asset(db, actor, asset_id, body))


@router.post("/{asset_id}/arquivos", operation_id="assets_file_upload", status_code=201,
             response_model=schemas.AssetFileOut,
             responses=_errors(400, 401, 403, 404, 409, 503, 507))
def upload_file(
    asset_id: UUID, file: Upload, actor: RequireUser, db: Db,
    role: Annotated[FileRole, Form()],
    look: OptText = None, uso: OptText = None, label: OptText = None,
    quando_usar: Annotated[str | None, Form(alias="quandoUsar", max_length=600)] = None,
    notes: OptText = None,
    slot: Annotated[str | None, Form(max_length=40, description="Spec 025: slot do kit")] = None,
    origem: Annotated[str | None, Form(max_length=20,
                                       description="Spec 025: upload ou pessoa_real")] = None,
) -> schemas.AssetFileOut:
    if role == FileRole.kit:  # spec 025: um slot do kit padrão
        asset = svc._editavel(db, asset_id, None)
        asset, f, avisos, checagem = svc.upload_slot(db, actor, asset, file.file, slot, origem)
        out = svc.asset_out(db, asset)
        return schemas.AssetFileOut(
            asset=out, file=svc.file_out(out, f.id),
            avisos=[{"itens": avisos}] if avisos else [], checagem_geracao_id=checagem)
    raw = {"look": look, "uso": uso, "label": label, "quando_usar": quando_usar,
           "notes": notes}
    limits = {"look": 60, "uso": 200, "label": 60, "quando_usar": 300, "notes": 500}
    meta = {k: _blank(v) for k, v in raw.items()}
    for field, value in meta.items():
        if value is not None and len(value) > limits[field]:
            camel = "quandoUsar" if field == "quando_usar" else field
            raise schemas.invalid(camel, f"até {limits[field]} caracteres")
    asset, f = svc.upload_file(db, actor, asset_id, file.file, role, meta)
    out = svc.asset_out(db, asset)
    return schemas.AssetFileOut(asset=out, file=svc.file_out(out, f.id))


@router.patch("/{asset_id}/arquivos/{file_id}", operation_id="assets_file_update",
              response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def update_file(asset_id: UUID, file_id: UUID, body: schemas.FilePatch, actor: RequireUser,
                db: Db) -> schemas.AssetOut:
    return _out(db, svc.update_file(db, actor, asset_id, file_id, body))


@router.put("/{asset_id}/ordem", operation_id="assets_reorder",
            response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def reorder(asset_id: UUID, body: schemas.Ordem, actor: RequireUser,
            db: Db) -> schemas.AssetOut:
    return _out(db, svc.reorder(db, actor, asset_id, body))


@router.post("/{asset_id}/arquivos/{file_id}/archive", operation_id="assets_file_archive",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def archive_file(asset_id: UUID, file_id: UUID, body: VersionIn, actor: RequireUser,
                 db: Db) -> schemas.AssetOut:
    return _out(db, svc.archive_file(db, actor, asset_id, file_id, body.version))


@router.post("/{asset_id}/arquivos/{file_id}/restore", operation_id="assets_file_restore",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def restore_file(asset_id: UUID, file_id: UUID, body: VersionIn, actor: RequireUser,
                 db: Db) -> schemas.AssetOut:
    return _out(db, svc.restore_file(db, actor, asset_id, file_id, body.version))


@router.post("/{asset_id}/archive", operation_id="assets_archive",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def archive(asset_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> schemas.AssetOut:
    return _out(db, svc.archive_asset(db, actor, asset_id, body.version))


@router.post("/{asset_id}/restore", operation_id="assets_restore",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def restore(asset_id: UUID, body: VersionIn, actor: RequireUser, db: Db) -> schemas.AssetOut:
    return _out(db, svc.restore_asset(db, actor, asset_id, body.version))


@router.get("/{asset_id}/versions", operation_id="assets_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def versions(asset_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return svc.asset_versions(db, asset_id)


@router.post("/{asset_id}/revert", operation_id="assets_revert",
             response_model=schemas.AssetOut, responses=_errors(400, 401, 403, 404, 409))
def revert(asset_id: UUID, body: RevertIn, actor: RequireOwner, db: Db) -> schemas.AssetOut:
    return _out(db, svc.revert_asset(db, actor, asset_id, body.version, body.to_version))
