"""Fontes do kit (T009/T015, research R3 e R8, contracts/http-api.md "Fontes").

- **padrão:** Anton, Noto Serif Bold e Liberation Sans/Serif Bold, empacotadas em
  `marca/fonts/` (com as licenças OFL) e servidas sem login por `/api/fontes-padrao/{key}`;
- **do perfil:** TTF ou OTF até 10 MB, validada pela assinatura do arquivo (nunca pela
  extensão) e pelo FreeType do Pillow, que também dá a família e o estilo. O arquivo vai para o
  bucket `fontes` e é imutável; a linha em `brand_fonts` só muda de nome ou é arquivada, com
  histórico (`entity_type = "fonte"`). Nada é apagado (FR-009).
"""

import hashlib
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, BinaryIO, Literal

from PIL import ImageFont
from pydantic import StringConstraints
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import datadir, history, storage
from sociman_api.auth.deps import Actor
from sociman_api.auth.schemas import CamelModel
from sociman_api.errors import ApiError
from sociman_api.marca.models import BrandFont, FontFormat
from sociman_api.marca.tokens import DEFAULT_FONTS, PERFIL_PREFIX, DefaultFont, fields_using_font
from sociman_api.perfis.schemas import UserRef, VersionNumber
from sociman_api.perfis.service_perfis import get_perfil_or_404, user_refs

FONTS_DIR = Path(__file__).resolve().parent / "fonts"
ENTITY = "fonte"
LABEL = "Esta fonte"
MAX_BYTES = 10 * 1024 * 1024
SAMPLE = "Os achadinhos que você queria"
CONTENT_TYPES = {FontFormat.ttf: "font/ttf", FontFormat.otf: "font/otf"}
_CHUNK = 64 * 1024
_SIGNATURES = {b"\x00\x01\x00\x00": FontFormat.ttf, b"true": FontFormat.ttf,
               b"OTTO": FontFormat.otf}
# Nome dos campos do kit nas mensagens do `font_in_use`.
_FIELD_LABELS = {"caption": "na legenda", "hook": "no gancho", "watermark": "na marca d'água",
                 "endCard": "no card final"}

FontName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


# ---- schemas ----

class FontePadrao(CamelModel):
    key: Literal["anton", "noto-serif-bold", "liberation-sans", "liberation-serif"]
    name: str
    family: str
    url: str  # pública


class FontesPadraoList(CamelModel):
    items: list[FontePadrao]


class Fonte(CamelModel):
    id: uuid.UUID
    perfil_id: uuid.UUID
    name: str
    family: str
    style: str
    format: Literal["ttf", "otf"]
    bytes: int
    archived: bool
    version: int
    created_at: datetime
    created_by: UserRef | None


class FonteOut(CamelModel):
    fonte: Fonte


class FontesList(CamelModel):
    items: list[Fonte]


class RenameFonteIn(CamelModel):
    version: VersionNumber
    name: FontName


# ---- fontes padrão ----

def default_font_url(font: DefaultFont) -> str:
    return f"/api/fontes-padrao/{font.key}"


def default_font_path(key: str) -> Path:
    font = DEFAULT_FONTS.get(key)
    if font is None:
        raise ApiError(404, "not_found", "Fonte não encontrada")
    return FONTS_DIR / font.filename


def list_default_fonts() -> FontesPadraoList:
    return FontesPadraoList(items=[
        FontePadrao(key=f.key, name=f.name, family=f.family, url=default_font_url(f))
        for f in DEFAULT_FONTS.values()
    ])


# ---- validação (R3) ----

@dataclass(frozen=True)
class FontInfo:
    format: FontFormat
    family: str
    style: str
    bytes: int
    sha256: str


def _invalid(message: str = "Não é uma fonte TTF/OTF") -> ApiError:
    return ApiError(400, "invalid_font", message)


def read_limited(stream: BinaryIO) -> bytes:
    """Lê em blocos e para ao passar de 10 MB, sem carregar o resto do arquivo."""
    data = bytearray()
    while chunk := stream.read(_CHUNK):
        data += chunk
        if len(data) > MAX_BYTES:
            raise _invalid("Arquivo maior que 10 MB")
    return bytes(data)


def validate_font(data: bytes) -> FontInfo:
    """Assinatura TTF/OTF (coleção, WOFF e WOFF2 ficam de fora) e carga pelo FreeType, com a
    amostra renderizando com largura > 0."""
    if len(data) > MAX_BYTES:
        raise _invalid("Arquivo maior que 10 MB")
    fmt = _SIGNATURES.get(data[:4])
    if fmt is None:
        raise _invalid()
    try:
        font = ImageFont.truetype(io.BytesIO(data), 48)
        family, style = font.getname()
        left, _, right, _ = font.getbbox(SAMPLE)
    except (OSError, ValueError, TypeError) as exc:
        raise _invalid() from exc
    if not family or right - left <= 0:
        raise _invalid()
    return FontInfo(format=fmt, family=family, style=style or "Regular", bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest())


# ---- saída ----

def fonte_out(db: Session, font: BrandFont) -> Fonte:
    users = user_refs(db, [font.created_by])
    return _out(font, users)


def _out(font: BrandFont, users: dict[uuid.UUID, UserRef]) -> Fonte:
    return Fonte(
        id=font.id, perfil_id=font.perfil_id, name=font.name, family=font.family,
        style=font.style, format=font.format.value, bytes=font.bytes, archived=font.archived,
        version=font.version, created_at=font.created_at,
        created_by=users.get(font.created_by) if font.created_by else None,
    )


def list_fontes(db: Session, perfil_id: uuid.UUID, archived: bool) -> FontesList:
    get_perfil_or_404(db, perfil_id)
    cond = BrandFont.archived_at.is_not(None) if archived else BrandFont.archived_at.is_(None)
    fonts = list(db.scalars(
        select(BrandFont).where(BrandFont.perfil_id == perfil_id, cond)
        .order_by(func.lower(BrandFont.name), BrandFont.created_at)
    ))
    users = user_refs(db, [f.created_by for f in fonts])
    return FontesList(items=[_out(f, users) for f in fonts])


# ---- mutações ----

def get_font_or_404(db: Session, font_id: uuid.UUID, lock: bool = False) -> BrandFont:
    font = db.get(BrandFont, font_id, with_for_update=lock)
    if font is None:
        raise ApiError(404, "not_found", "Fonte não encontrada")
    return font


def _check_name_free(db: Session, perfil_id: uuid.UUID, name: str,
                     exclude: uuid.UUID | None = None) -> None:
    stmt = select(BrandFont.id).where(
        BrandFont.perfil_id == perfil_id, BrandFont.archived_at.is_(None),
        func.lower(BrandFont.name) == name.lower(),
    )
    if exclude is not None:
        stmt = stmt.where(BrandFont.id != exclude)
    if db.scalar(stmt) is not None:
        raise _name_in_use()


def _name_in_use() -> ApiError:
    return ApiError(409, "font_name_in_use", "Já existe uma fonte ativa com esse nome")


def _flush(db: Session) -> None:
    """Flush que traduz a corrida no índice único parcial (nome entre as ativas) em 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        if "uq_brand_fonts_perfil_lower_name" in str(exc.orig):
            raise _name_in_use() from exc
        raise


def upload_fonte(db: Session, actor: Actor, perfil_id: uuid.UUID, name: str,
                 stream: BinaryIO) -> BrandFont:
    perfil = get_perfil_or_404(db, perfil_id)
    datadir.ensure_writable()  # HD fora ou cheio: 503/507 antes de ler o corpo
    _check_name_free(db, perfil.id, name)
    data = read_limited(stream)
    info = validate_font(data)
    key = f"perfis/{perfil.id}/{uuid.uuid4()}.{info.format.value}"
    # O objeto vai antes do commit; se a transação falhar, sobra um objeto sem referência
    # (nunca apagamos objetos), o que é inofensivo.
    storage.put(key, data, CONTENT_TYPES[info.format], bucket="fontes")
    font = BrandFont(
        perfil_id=perfil.id, name=name, family=info.family, style=info.style,
        format=info.format, object_key=key, bytes=info.bytes, sha256=info.sha256,
        created_by=actor.user_id, updated_by=actor.user_id,
    )
    db.add(font)
    _flush(db)
    history.record(db, actor, ENTITY, font, "created", None, history.snapshot(font))
    db.flush()
    db.refresh(font)  # created_at vem do banco
    return font


def rename_fonte(db: Session, actor: Actor, font_id: uuid.UUID, version: int,
                 name: str) -> BrandFont:
    font = get_font_or_404(db, font_id, lock=True)
    history.check_version(font, version, LABEL)
    if name == font.name:
        return font
    if not font.archived:
        _check_name_free(db, font.perfil_id, name, exclude=font.id)
    before = history.snapshot(font)
    font.name = name
    font.updated_by = actor.user_id
    history.record(db, actor, ENTITY, font, "updated", before, history.snapshot(font))
    _flush(db)
    return font


def _in_use_message(fields: list[str]) -> str:
    places = list(dict.fromkeys(_FIELD_LABELS.get(f.split(".")[0], f) for f in fields))
    joined = places[0] if len(places) == 1 else ", ".join(places[:-1]) + " e " + places[-1]
    return f"Esta fonte é usada {joined}; troque antes de arquivar"


def archive_fonte(db: Session, actor: Actor, font_id: uuid.UUID, version: int) -> BrandFont:
    # Import tardio: service_kit importa o módulo de mídia e o de tokens; evita ciclo.
    from sociman_api.marca.service_kit import current_tokens

    font = get_font_or_404(db, font_id, lock=True)
    history.check_version(font, version, LABEL)
    if font.archived:
        raise ApiError(409, "conflict", "Esta fonte já está arquivada")
    tokens, _ = current_tokens(db, font.perfil_id)
    fields = fields_using_font(tokens, f"{PERFIL_PREFIX}{font.id}")
    if fields:
        raise ApiError(409, "font_in_use", _in_use_message(fields), details={"fields": fields})
    before = history.snapshot(font)
    font.archived_at = datetime.now(UTC)
    font.archived_by = actor.user_id
    font.updated_by = actor.user_id
    history.record(db, actor, ENTITY, font, "archived", before, history.snapshot(font))
    return font


def restore_fonte(db: Session, actor: Actor, font_id: uuid.UUID, version: int) -> BrandFont:
    font = get_font_or_404(db, font_id, lock=True)
    history.check_version(font, version, LABEL)
    if not font.archived:
        raise ApiError(409, "conflict", "Esta fonte não está arquivada")
    _check_name_free(db, font.perfil_id, font.name, exclude=font.id)
    before = history.snapshot(font)
    font.archived_at = None
    font.archived_by = None
    font.updated_by = actor.user_id
    history.record(db, actor, ENTITY, font, "restored", before, history.snapshot(font))
    _flush(db)
    return font
