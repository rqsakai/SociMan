"""Cortes (T026, contracts/http-api.md "Cortes"; research R3, R4 e R5).

Envio em três etapas:
1. `precheck` (antes de ler o corpo): perfil existe e não está arquivado, `Content-Length` até
   500 MB + folga do multipart (413) e o HD com o sentinela e espaço para o envio (503/507);
2. `receive`: lê o multipart em streaming direto para um arquivo em
   `${SOCIMAN_DATA_DIR}/work/tmp` (nunca a RAM nem o `/tmp` do container), com o sha256 e o
   limite de 500 MB conferidos enquanto chega;
3. `create_corte`: ffprobe (R3), gancho que cabe em 3 linhas na fonte do kit, o original no
   bucket de vídeos e só então a linha, com os tokens do kit resolvidos e a `kitVersion`. Um
   envio interrompido não cria linha.

Só o envio e o "tentar de novo" são versões do histórico; o resto é estado do job (queue.py).

Spec 006 (T057): o clipe importado do OpenShorts chega em `revisao` (sem kit). Daí:
- `editar_gancho` (só em `revisao`);
- `aplicar_marca` (lote de até 30, tudo ou nada): resolve o kit atual, confere o gancho e leva a
  `na_fila`; o worker e a fila da 004 seguem iguais. A importação com a marca automática chama o
  mesmo `marcar`;
- `arquivar`/`restaurar` (menos em `processando`). Sem `revert` (exceção aprovada).
"""

import hashlib
import os
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from python_multipart.multipart import MultipartParser, parse_options_header
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect, Request

from sociman_api import datadir, history, imaging, storage
from sociman_api.auth.deps import Actor
from sociman_api.canais.models import CanalFonte
from sociman_api.config import get_settings
from sociman_api.cortes import worker
from sociman_api.cortes.models import Corte, CorteOrigem, CorteStatus
from sociman_api.cortes.probe import MAX_BYTES, probe
from sociman_api.cortes.render import HOOK_MAX_CHARS, InvalidHook, wrap_hook
from sociman_api.cortes.schemas import AplicarMarcaItem, Armazenamento, CorteCanal
from sociman_api.cortes.schemas import Corte as CorteSchema
from sociman_api.envios.models import Envio
from sociman_api.errors import ApiError
from sociman_api.marca.models import BrandFont
from sociman_api.marca.service_kit import current_tokens
from sociman_api.marca.tokens import (
    DEFAULT_FONTS,
    DEFAULT_PREFIX,
    KitTokens,
    font_refs,
    fundo_image_ids,
    perfil_font_id,
    resolve_tokens,
)
from sociman_api.perfis.models import Conta, Image, ImageKind, Perfil
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, user_refs, versions_out

ENTITY = "corte"
LABEL = "Este corte"
NOT_FOUND = "Corte não encontrado"
MULTIPART_SLACK = 1024 * 1024  # folga do envelope multipart sobre os 500 MB do arquivo
MAX_BODY = MAX_BYTES + MULTIPART_SLACK
TOO_BIG = "Arquivo maior que 500 MB"
MAX_FIELD = 4096
MAX_FILENAME = 200


def _too_big(message: str = TOO_BIG) -> ApiError:
    return ApiError(413, "payload_too_large", message)


def _bad_request(message: str) -> ApiError:
    return ApiError(400, "validation_error", message)


# ---- envio ----

def spool_dir() -> Path:
    return Path(get_settings().data_dir) / "work" / "tmp"


def precheck(db: Session, perfil_id: uuid.UUID, content_length: str | None, *,
             max_body: int = MAX_BODY, too_big: str = TOO_BIG) -> None:
    """Tudo o que dá para recusar sem ler o corpo. O envio avulso da 006 passa o próprio
    limite (2 GB, envios/upload.py)."""
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    try:
        length = int(content_length) if content_length is not None else None
    except ValueError:
        raise _bad_request("Content-Length inválido") from None
    if length is not None and length > max_body:
        raise _too_big(too_big)
    # Sem Content-Length (envio em partes), reserva o máximo.
    datadir.ensure_writable(max_body if length is None else length)
    if not spool_dir().is_dir():
        raise ApiError(503, "storage_unavailable", "O HD de dados não está disponível")


@dataclass
class Spooled:
    path: Path
    filename: str
    size: int
    sha256: str
    hook_text: str | None
    fields: dict[str, str] = field(default_factory=dict)  # os campos de texto do formulário


class _Receiver:
    """Callbacks do `MultipartParser`: campos pequenos na memória e o arquivo `file` em disco
    (os pedaços ficam em `pending` até o laço assíncrono gravá-los fora do event loop)."""

    def __init__(self) -> None:
        self.fields: dict[str, str] = {}
        self.filename: str | None = None
        self.pending: list[bytes] = []
        self._header_name = b""
        self._header_value = b""
        self._disposition = b""
        self._name = ""
        self._is_file = False
        self._buf = bytearray()
        self._files = 0

    def on_part_begin(self) -> None:
        self._disposition = b""
        self._name = ""
        self._is_file = False
        self._buf = bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        if self._header_name.lower() == b"content-disposition":
            self._disposition = self._header_value
        self._header_name = b""
        self._header_value = b""

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self._disposition)
        self._name = options.get(b"name", b"").decode("utf-8", "replace")
        if b"filename" in options:
            if self._name != "file" or self._files:
                raise _bad_request("Envie um único arquivo no campo file")
            self._files += 1
            self._is_file = True
            raw = options[b"filename"].decode("utf-8", "replace")
            name = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
            self.filename = name[:MAX_FILENAME] or "video"

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._is_file:
            self.pending.append(bytes(data[start:end]))
            return
        self._buf += data[start:end]
        if len(self._buf) > MAX_FIELD:
            raise _bad_request(f"{self._name}: campo grande demais")

    def on_part_end(self) -> None:
        if not self._is_file and self._name:
            if len(self.fields) >= 10:
                raise _bad_request("Campos demais no formulário")
            self.fields[self._name] = self._buf.decode("utf-8", "replace")

    def callbacks(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in (
            "on_part_begin", "on_header_field", "on_header_value", "on_header_end",
            "on_headers_finished", "on_part_data", "on_part_end")}


def _write(fh: Any, chunks: list[bytes], hasher: Any) -> int:
    n = 0
    for chunk in chunks:
        fh.write(chunk)
        hasher.update(chunk)
        n += len(chunk)
    return n


async def receive(request: Request, *, max_bytes: int = MAX_BYTES, prefix: str = "corte-",
                  too_big: str = TOO_BIG) -> Spooled:
    """Lê o multipart (`file`, `hookText`) direto para `work/tmp`. Quem chama apaga o arquivo;
    em erro, este já apaga. O envio avulso da 006 passa o próprio limite e prefixo (e lê o
    campo `titulo` em `fields`)."""
    content_type, params = parse_options_header(request.headers.get("content-type", ""))
    boundary = params.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise _bad_request("Envie o vídeo em multipart/form-data")

    try:
        fh = tempfile.NamedTemporaryFile(  # noqa: SIM115 — fechado no `with fh` abaixo
            dir=spool_dir(), prefix=prefix, suffix=".upload", delete=False)
    except OSError:
        raise ApiError(503, "storage_unavailable", "O HD de dados não está disponível") from None
    path = Path(fh.name)
    receiver = _Receiver()
    hasher = hashlib.sha256()
    size = 0
    try:
        parser = MultipartParser(boundary, receiver.callbacks())
        with fh:
            async for chunk in request.stream():
                parser.write(chunk)
                if receiver.pending:
                    chunks, receiver.pending = receiver.pending, []
                    size += await run_in_threadpool(_write, fh, chunks, hasher)
                    if size > max_bytes:
                        raise _too_big(too_big)
            parser.finalize()
        if receiver.filename is None:
            raise _bad_request("file: obrigatório")
        return Spooled(path=path, filename=receiver.filename, size=size,
                       sha256=hasher.hexdigest(), hook_text=receiver.fields.get("hookText"),
                       fields=dict(receiver.fields))
    except (ApiError, ClientDisconnect):
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise _bad_request("Envio inválido ou interrompido") from exc


def _normalize_hook(raw: str | None) -> str:
    text = (raw or "").replace("\r\n", "\n").strip()
    if not text:
        raise ApiError(400, "invalid_hook", "O texto do gancho é obrigatório")
    if len(text) > HOOK_MAX_CHARS:
        raise InvalidHook()
    return text


def resolve_corte_tokens(db: Session, perfil: Perfil, tokens: KitTokens) -> dict[str, Any]:
    """Os tokens que o worker usa: cores em hex, fontes (`padrao` ou `object_key`), o `@` da
    conta, a imagem da marca d'água, as de fundo (`fundo_imagem_key`) e o logo por
    `object_key` (data-model `kit_tokens`)."""
    fonts: dict[str, dict[str, Any]] = {}
    for ref in font_refs(tokens):
        font_id = perfil_font_id(ref)
        if font_id is None:
            key = ref[len(DEFAULT_PREFIX):]
            fonts[ref] = {"ref": ref, "family": DEFAULT_FONTS[key].family, "padrao": key}
            continue
        font = db.get(BrandFont, font_id)
        if font is None or font.perfil_id != perfil.id:
            raise ApiError(409, "conflict", f"A fonte {ref} do kit não existe")
        fonts[ref] = {"ref": ref, "family": font.family, "object_key": font.object_key}
    fundos: dict[uuid.UUID, dict[str, Any]] = {}
    for image_id in fundo_image_ids(tokens):
        image = db.get(Image, image_id)
        if image is None or image.perfil_id != perfil.id or image.kind != ImageKind.fundo:
            raise ApiError(409, "conflict", "A imagem de fundo do kit não existe")
        fundos[image_id] = {"fundo_imagem_key": image.object_key}
    out = resolve_tokens(tokens, fonts, fundos)

    logo_key = None
    if perfil.logo_image_id is not None:
        logo = db.get(Image, perfil.logo_image_id)
        logo_key = logo.object_key if logo is not None else None
    wm, wm_in = out["watermark"], tokens.watermark
    if wm_in.conta_id is not None:
        conta = db.get(Conta, wm_in.conta_id)
        wm["texto"] = f"@{conta.handle}" if conta is not None else None
    if wm_in.imagem_id is not None:
        image = db.get(Image, wm_in.imagem_id)
        wm["imagem_key"] = image.object_key if image is not None else None
    wm["logo_key"] = logo_key
    out["end_card"]["logo_key"] = logo_key
    return out


def _check_hook(hook_text: str, tokens: dict[str, Any], width: int, workdir: Path) -> None:
    """Recusa (400 `invalid_hook`) o gancho que passa de 3 linhas na fonte e no tamanho do kit."""
    hook = tokens["hook"]
    if not hook["ligado"]:
        return
    style = worker.hook_style(hook, worker.font_file(hook["fonte"], workdir))
    wrap_hook(hook_text, style, width)


def create_corte(db: Session, actor: Actor, perfil_id: uuid.UUID, up: Spooled) -> Corte:
    hook_text = _normalize_hook(up.hook_text)
    info = probe(up.path)
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    tokens, kit_row = current_tokens(db, perfil_id)
    resolved = resolve_corte_tokens(db, perfil, tokens)
    with tempfile.TemporaryDirectory(dir=spool_dir(), prefix="gancho-") as tmp:
        _check_hook(hook_text, resolved, info.width, Path(tmp))

    corte_id = uuid.uuid4()
    key = worker.original_key(perfil_id, corte_id, info.content_type)
    storage.put_file(key, up.path, info.content_type, bucket="videos")

    corte = Corte(
        id=corte_id, perfil_id=perfil_id, hook_text=hook_text,
        kit_version=kit_row.version if kit_row is not None else 0, kit_tokens=resolved,
        status=CorteStatus.na_fila, original_filename=up.filename, original_key=key,
        original_content_type=info.content_type, original_bytes=up.size,
        duration_ms=info.duration_ms, width=info.width, height=info.height, fps=info.fps,
        video_codec=info.video_codec, audio_codec=info.audio_codec, original_sha256=up.sha256,
        created_by=actor.user_id, updated_by=actor.user_id,
    )
    db.add(corte)
    db.flush()
    history.record(db, actor, ENTITY, corte, "created", None, history.snapshot(corte))
    db.flush()
    db.refresh(corte)
    return corte


# ---- consultas ----

def get_corte_or_404(db: Session, corte_id: uuid.UUID, lock: bool = False) -> Corte:
    corte = db.get(Corte, corte_id, with_for_update=lock)
    if corte is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return corte


def _queue_positions(db: Session) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(Corte.id, func.row_number().over(order_by=(Corte.queued_at, Corte.id)))
        .where(Corte.status == CorteStatus.na_fila)
    )
    return {cid: pos for cid, pos in rows}


def _envios_e_canais(db: Session, cortes: list[Corte]
                     ) -> tuple[dict[uuid.UUID, Envio], dict[uuid.UUID, CanalFonte]]:
    envio_ids = {c.envio_id for c in cortes if c.envio_id is not None}
    envios = {e.id: e for e in db.scalars(select(Envio).where(Envio.id.in_(envio_ids)))} \
        if envio_ids else {}
    canal_ids = {e.canal_fonte_id for e in envios.values() if e.canal_fonte_id is not None}
    canais = {c.id: c for c in db.scalars(select(CanalFonte).where(CanalFonte.id.in_(canal_ids)))} \
        if canal_ids else {}
    return envios, canais


def cortes_out(db: Session, cortes: list[Corte]) -> list[CorteSchema]:
    users = user_refs(db, [c.created_by for c in cortes])
    positions = _queue_positions(db) if any(
        c.status == CorteStatus.na_fila for c in cortes) else {}
    envios, canais = _envios_e_canais(db, cortes)
    # Import tardio: postagem/service importa cortes.models.
    from sociman_api.postagem.service import resumos_por_corte

    postagens = resumos_por_corte(db, [c.id for c in cortes]) if cortes else {}

    def extra(c: Corte) -> dict[str, Any]:
        envio = envios.get(c.envio_id) if c.envio_id else None
        canal = canais.get(envio.canal_fonte_id) if envio and envio.canal_fonte_id else None
        return {
            "origem": c.origem, "envio_id": c.envio_id, "clip_index": c.clip_index,
            "source_start_ms": c.source_start_ms, "source_end_ms": c.source_end_ms,
            "openshorts_title": c.openshorts_title,
            "openshorts_description": c.openshorts_description,
            "openshorts_score": c.openshorts_score, "legenda": c.legenda,
            "canal": CorteCanal(id=canal.id, title=canal.title) if canal else None,
            "direito_no_envio": envio.direito_no_envio if envio else None,
            "archived": c.archived,
            "postagens": postagens.get(c.id, []),
        }

    return [
        CorteSchema(
            id=c.id, perfil_id=c.perfil_id, hook_text=c.hook_text, kit_version=c.kit_version,
            status=c.status, progress=c.progress, queue_position=positions.get(c.id),
            attempts=c.attempts, error_message=c.error_message,
            original_filename=c.original_filename, bytes=c.original_bytes,
            duration_ms=c.duration_ms, width=c.width, height=c.height,
            has_audio=c.audio_codec is not None, result_bytes=c.result_bytes,
            processing_ms=c.processing_ms,
            poster_url=imaging.poster_url(c.poster_key) if c.poster_key else None,
            version=c.version, created_at=c.created_at,
            created_by=users.get(c.created_by) if c.created_by else None,
            finished_at=c.finished_at, **extra(c),
        )
        for c in cortes
    ]


def corte_out(db: Session, corte: Corte) -> CorteSchema:
    return cortes_out(db, [corte])[0]


def list_cortes(db: Session, perfil_id: uuid.UUID, status: CorteStatus | None, limit: int,
                before: Any | None, origem: CorteOrigem | None = None,
                envio_id: uuid.UUID | None = None, archived: bool = False
                ) -> list[CorteSchema]:
    """Mais recentes primeiro; `before` (cursor) é o `createdAt` do último item já visto.
    `archived=True` lista só os arquivados; o padrão, só os ativos."""
    get_perfil_or_404(db, perfil_id)
    query = select(Corte).where(Corte.perfil_id == perfil_id)
    query = query.where(Corte.archived_at.is_not(None) if archived
                        else Corte.archived_at.is_(None))
    if origem is not None:
        query = query.where(Corte.origem == origem)
    if envio_id is not None:
        query = query.where(Corte.envio_id == envio_id)
    if status is not None:
        query = query.where(Corte.status == status)
    if before is not None:
        query = query.where(Corte.created_at < before)
    query = query.order_by(Corte.created_at.desc(), Corte.id.desc()).limit(limit)
    return cortes_out(db, list(db.scalars(query)))


def corte_versions(db: Session, corte_id: uuid.UUID) -> VersionsList:
    get_corte_or_404(db, corte_id)
    return versions_out(db, ENTITY, corte_id)


def armazenamento(db: Session) -> Armazenamento:
    s = datadir.status()
    used = db.scalar(select(func.coalesce(
        func.sum(Corte.original_bytes + func.coalesce(Corte.result_bytes, 0)), 0)))
    return Armazenamento(available=s.available, reason=s.reason, free_bytes=s.free_bytes,
                         total_bytes=s.total_bytes, min_free_bytes=s.min_free_bytes,
                         cortes_bytes=int(used or 0))


# ---- mutações ----

def retry(db: Session, actor: Actor, corte_id: uuid.UUID, version: int) -> Corte:
    """"Tentar de novo" (US4-5): `falhou` → `na_fila`, com os mesmos `kit_tokens`."""
    corte = get_corte_or_404(db, corte_id, lock=True)
    history.check_version(corte, version, LABEL)
    if corte.status != CorteStatus.falhou:
        raise ApiError(409, "conflict", "Só um corte que falhou pode ser tentado de novo")
    before = history.snapshot(corte)
    corte.status = CorteStatus.na_fila
    corte.attempts = 0
    corte.progress = 0
    corte.error_code = None
    corte.error_message = None
    corte.queued_at = func.now()
    corte.started_at = None
    corte.heartbeat_at = None
    corte.finished_at = None
    corte.updated_by = actor.user_id
    history.record(db, actor, ENTITY, corte, "updated", before, history.snapshot(corte))
    db.flush()
    db.refresh(corte)
    return corte


def cleanup_spool(up: Spooled | None) -> None:
    if up is not None:
        try:
            os.unlink(up.path)
        except FileNotFoundError:
            pass


# ---- revisão dos clipes do OpenShorts (spec 006, T057) ----

def _conflict(message: str) -> ApiError:
    return ApiError(409, "conflict", message)


class KitCache:
    """O kit atual resolvido uma vez por perfil (um lote pode ter clipes de vários perfis)."""

    def __init__(self, db: Session):
        self.db = db
        self._kits: dict[uuid.UUID, tuple[int, dict[str, Any]]] = {}

    def get(self, perfil_id: uuid.UUID) -> tuple[int, dict[str, Any]]:
        if perfil_id not in self._kits:
            perfil = get_perfil_or_404(self.db, perfil_id)
            tokens, row = current_tokens(self.db, perfil_id)
            self._kits[perfil_id] = (row.version if row is not None else 0,
                                     resolve_corte_tokens(self.db, perfil, tokens))
        return self._kits[perfil_id]


def _check_hook_revisao(hook_text: str, tokens: dict[str, Any], width: int) -> None:
    with tempfile.TemporaryDirectory(dir=spool_dir(), prefix="gancho-") as tmp:
        _check_hook(hook_text, tokens, width, Path(tmp))


def marcar(db: Session, actor: history.ActorLike, corte: Corte, kits: KitCache) -> Corte:
    """`revisao` → `na_fila` com o kit atual resolvido (`kit_version`/`kit_tokens`), sem
    conferir a versão: quem chama já conferiu (rota) ou é a importação (marca automática).
    Levanta 400 `invalid_hook` se o gancho não cabe."""
    if corte.status != CorteStatus.revisao or corte.archived:
        raise _conflict("Só um clipe em revisão (não arquivado) recebe a marca")
    hook_text = _normalize_hook(corte.hook_text)
    kit_version, resolved = kits.get(corte.perfil_id)
    _check_hook_revisao(hook_text, resolved, corte.width)
    before = history.snapshot(corte)
    corte.hook_text = hook_text
    corte.kit_version = kit_version
    corte.kit_tokens = resolved
    corte.status = CorteStatus.na_fila
    corte.progress = 0
    corte.attempts = 0
    corte.error_code = None
    corte.error_message = None
    corte.queued_at = func.now()
    corte.updated_by = actor.user_id
    history.record(db, actor, ENTITY, corte, "updated", before, history.snapshot(corte),
                   {"acao": "aplicar_marca"})
    return corte


def aplicar_marca(db: Session, actor: Actor, items: Sequence[AplicarMarcaItem]) -> list[Corte]:
    """"Aplicar marca" em um lote (até 30), tudo ou nada: o HD é conferido antes (503/507)."""
    datadir.ensure_writable()
    kits = KitCache(db)
    cortes: list[Corte] = []
    for item in sorted(items, key=lambda i: i.corte_id):  # trava sempre na mesma ordem
        corte = get_corte_or_404(db, item.corte_id, lock=True)
        history.check_version(corte, item.version, LABEL)
        if corte.status != CorteStatus.revisao or corte.archived:
            raise _conflict("Só um clipe em revisão (não arquivado) recebe a marca")
        try:
            marcar(db, actor, corte, kits)
        except ApiError as exc:
            if exc.code == "invalid_hook":
                raise ApiError(400, "invalid_hook", exc.message,
                               details={"corteId": str(corte.id)}) from exc
            raise
        cortes.append(corte)
    db.flush()
    order = {i.corte_id: n for n, i in enumerate(items)}
    for corte in cortes:
        db.refresh(corte)
    return sorted(cortes, key=lambda c: order[c.id])


def editar_gancho(db: Session, actor: Actor, corte_id: uuid.UUID, version: int,
                  hook_text: str) -> Corte:
    """Só em `revisao`: 1..120 caracteres e, com o gancho ligado no kit, até 3 linhas."""
    corte = get_corte_or_404(db, corte_id, lock=True)
    history.check_version(corte, version, LABEL)
    if corte.status != CorteStatus.revisao or corte.archived:
        raise _conflict("Só dá para editar o gancho de um clipe em revisão")
    text = _normalize_hook(hook_text)
    datadir.ensure_writable()
    _, resolved = KitCache(db).get(corte.perfil_id)
    _check_hook_revisao(text, resolved, corte.width)
    before = history.snapshot(corte)
    corte.hook_text = text
    after = history.snapshot(corte)
    if after != before:
        corte.updated_by = actor.user_id
        history.record(db, actor, ENTITY, corte, "updated", before, after)
    db.flush()
    db.refresh(corte)
    return corte


def arquivar(db: Session, actor: Actor, corte_id: uuid.UUID, version: int) -> Corte:
    corte = get_corte_or_404(db, corte_id, lock=True)
    history.check_version(corte, version, LABEL)
    if corte.archived:
        raise _conflict("Este corte já está arquivado")
    if corte.status == CorteStatus.processando:
        raise _conflict("O corte está sendo processado; espere terminar para arquivar")
    before = history.snapshot(corte)
    corte.archived_at = datetime.now(UTC)
    corte.archived_by = actor.user_id
    corte.updated_by = actor.user_id
    history.record(db, actor, ENTITY, corte, "archived", before, history.snapshot(corte))
    db.flush()
    db.refresh(corte)
    return corte


def restaurar(db: Session, actor: Actor, corte_id: uuid.UUID, version: int) -> Corte:
    corte = get_corte_or_404(db, corte_id, lock=True)
    history.check_version(corte, version, LABEL)
    if not corte.archived:
        raise _conflict("Este corte não está arquivado")
    before = history.snapshot(corte)
    corte.archived_at = None
    corte.archived_by = None
    corte.updated_by = actor.user_id
    history.record(db, actor, ENTITY, corte, "restored", before, history.snapshot(corte))
    db.flush()
    db.refresh(corte)
    return corte
