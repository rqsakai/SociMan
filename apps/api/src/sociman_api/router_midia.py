"""Rotas de mídia (T010, research R6, contracts/http-api.md "Mídia").

- `POST /api/midia/links` (`RequireUser`): links assinados de 1 h (configurável em
  `MIDIA_LINK_TTL_S`) para até 20 itens;
- `GET /api/midia/{token}` (**sem login**: o token é a autorização, porque `<video src>`,
  `<a download>` e `@font-face` não mandam `Authorization`): streaming do MinIO com `Range`.

O bucket, a chave e o `Content-Type` vêm da tabela do `kind` e do banco, nunca do pedido.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response
from pydantic import Field
from sqlalchemy.orm import Session

from sociman_api import midia, storage
from sociman_api.assets.service import asset_download_name
from sociman_api.auth.deps import RequireUser
from sociman_api.auth.schemas import CamelModel
from sociman_api.config import get_settings
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope
from sociman_api.marca.fontes import CONTENT_TYPES as FONT_CONTENT_TYPES
from sociman_api.marca.models import BrandFont
from sociman_api.perfis.models import Image, ImageKind, Perfil

router = APIRouter(prefix="/api/midia")

Db = DbSession
MAX_ITEMS = 20
_IMAGE_KINDS = {"marca_dagua": (ImageKind.watermark, "marca-dagua"),
                "fundo": (ImageKind.fundo, "fundo")}
_VIDEO_EXT = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm",
              "video/x-matroska": "mkv"}


class MidiaItem(CamelModel):
    kind: midia.MidiaKind
    id: uuid.UUID


class MidiaLinksIn(CamelModel):
    items: list[MidiaItem] = Field(min_length=1, max_length=MAX_ITEMS)


class MidiaLink(CamelModel):
    url: str  # relativa ao edge
    expires_at: datetime | None  # null = sem validade (só fonte e imagens, na exportação)


class MidiaLinksOut(CamelModel):
    items: list[MidiaLink]  # na ordem do pedido


@dataclass(frozen=True)
class Target:
    bucket: storage.Bucket
    key: str
    content_type: str
    filename: str  # para `?download=1`


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


def _not_found() -> ApiError:
    return ApiError(404, "not_found", "Arquivo não encontrado")


def _slug(db: Session, perfil_id: uuid.UUID) -> str:
    perfil = db.get(Perfil, perfil_id)
    return perfil.slug if perfil is not None else "corte"


def _corte_target(db: Session, corte: Corte, marked: bool) -> Target:
    stem = f"{_slug(db, corte.perfil_id)}-{corte.created_at:%Y-%m-%d}"
    if marked:
        if corte.status != CorteStatus.pronto or not corte.result_key:
            raise ApiError(409, "not_ready", "O corte ainda não está pronto")
        return Target("videos", corte.result_key, "video/mp4", f"{stem}-marcado.mp4")
    ext = _VIDEO_EXT.get(corte.original_content_type) \
        or PurePath(corte.original_filename).suffix.lstrip(".").lower() or "mp4"
    return Target("videos", corte.original_key, corte.original_content_type,
                  f"{stem}-original.{ext}")


def resolve(db: Session, kind: str, entity_id: uuid.UUID) -> Target:
    """O objeto de um item de mídia. 404 se não existe ou é de outro tipo; 409 `not_ready` para
    o marcado de um corte que ainda não está `pronto`."""
    if kind == "fonte":
        font = db.get(BrandFont, entity_id)
        if font is None:
            raise _not_found()
        return Target("fontes", font.object_key, FONT_CONTENT_TYPES[font.format],
                      f"{font.name}.{font.format.value}")
    if kind in _IMAGE_KINDS:
        image_kind, prefix = _IMAGE_KINDS[kind]
        image = db.get(Image, entity_id)
        if image is None or image.kind != image_kind:
            raise _not_found()
        ext = PurePath(image.object_key).suffix
        return Target("imagens", image.object_key, image.content_type,
                      f"{prefix}-{image.id.hex[:8]}{ext}")
    if kind == "imagem":
        image = db.get(Image, entity_id)
        if image is None:
            raise _not_found()
        return Target("imagens", image.object_key, image.content_type,
                      asset_download_name(db, image))
    if kind == "conteudo_video":  # vídeo próprio (spec 014); o corte usa `corte_marcado`
        conteudo = db.get(Conteudo, entity_id)
        if conteudo is None or conteudo.origem != ConteudoOrigem.video_proprio \
                or not conteudo.video_key or not conteudo.video_content_type:
            raise _not_found()
        ext = _VIDEO_EXT.get(conteudo.video_content_type, "mp4")
        stem = f"{_slug(db, conteudo.perfil_id)}-{conteudo.created_at:%Y-%m-%d}"
        return Target("videos", conteudo.video_key, conteudo.video_content_type,
                      f"{stem}-video.{ext}")
    if kind == "cena_tomada":  # spec 010
        from sociman_api.cenas.models import Cena, CenaTomada

        tomada = db.get(CenaTomada, entity_id)
        if tomada is None:
            raise _not_found()
        cena = db.get(Cena, tomada.cena_id)
        ext = _VIDEO_EXT.get(tomada.content_type, "mp4")
        stem = f"{_slug(db, cena.perfil_id) if cena else 'cena'}-tomada-{tomada.id.hex[:8]}"
        return Target("videos", tomada.video_key, tomada.content_type, f"{stem}.{ext}")
    if kind == "audio":  # spec 021 (R11)
        from sociman_api.geracao.audios import CONTENT_TYPES as AUDIO_CONTENT_TYPES
        from sociman_api.geracao.models import Audio

        audio = db.get(Audio, entity_id)
        if audio is None:
            raise _not_found()
        return Target("audios", audio.object_key, AUDIO_CONTENT_TYPES[audio.formato],
                      f"{_slug(db, audio.perfil_id)}-audio-{audio.id.hex[:8]}.{audio.formato}")
    if kind in midia.VIDEO_KINDS:
        corte = db.get(Corte, entity_id)
        if corte is None:
            raise _not_found()
        return _corte_target(db, corte, marked=kind == "corte_marcado")
    raise _not_found()


@router.post("/links", operation_id="midia_links", response_model=MidiaLinksOut,
             responses=_errors(400, 401, 403, 404, 409))
def create_links(body: MidiaLinksIn, actor: RequireUser, db: Db) -> MidiaLinksOut:
    ttl = get_settings().midia_link_ttl_s
    items = []
    for item in body.items:
        resolve(db, item.kind, item.id)  # existe e está pronto
        link = midia.link(item.kind, item.id, ttl=ttl)
        items.append(MidiaLink(url=link.url, expires_at=link.expires_at))
    return MidiaLinksOut(items=items)


@router.get("/{token}", operation_id="midia_get", response_class=Response, responses={
    200: {"description": "O arquivo inteiro", "content": {"application/octet-stream": {}}},
    206: {"description": "A faixa pedida em `Range`",
          "content": {"application/octet-stream": {}}},
    **_errors(403, 404, 409, 416, 503),
})
def get_media(
    token: str, db: Db,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
    download: Annotated[bool, Query(description="Baixar como anexo")] = False,
) -> Response:
    claims = midia.verify(token)
    target = resolve(db, claims.kind, claims.id)
    return midia.stream_object(target.bucket, target.key, target.content_type,
                               range_header=range_header,
                               download_name=target.filename if download else None)
