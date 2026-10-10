"""Vídeo próprio (research R9, FR-011, US5): `POST /api/perfis/{id}/conteudos/arquivo`.

Reusa o recebimento em streaming da 004/006 (`cortes.service.precheck` e `receive`, com o
limite e o prefixo deste envio): o HD e o `Content-Length` são conferidos antes de ler o corpo,
e o arquivo vai para `work/tmp` (HD). Depois:
1. ffprobe pelo conteúdo real: MP4, MOV ou WebM, de 1 s a 10 min (o teto da API do TikTok),
   até 2 GB, qualquer proporção (vídeo não vertical entra com o aviso `naoVertical`);
2. o vídeo vai para o bucket de vídeos em `conteudos/{id}/video.<ext>`, sem transcodificar;
3. a miniatura (1 quadro em `min(1 s, duração/2)`) é extraída na própria requisição e vai para
   o bucket `sociman`, como a do worker (imgproxy);
4. só então nasce a linha `conteudos` (`origem = video_proprio`) e a versão `created`. Um envio
   interrompido não cria linha.

O princípio II não se aplica (não é envio para corte, não há canal-fonte). Nada aqui publica.
"""

import hashlib
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session
from starlette.requests import Request

from sociman_api import history, storage
from sociman_api.auth.deps import Actor
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.cortes import compose
from sociman_api.cortes import service as cortes_service
from sociman_api.cortes.probe import InvalidVideo, probe
from sociman_api.cortes.service import Spooled
from sociman_api.cortes.worker import EXT
from sociman_api.errors import ApiError
from sociman_api.perfis.service_perfis import get_perfil_or_404

ENTITY = "conteudo"
GB = 1024**3
MAX_BYTES = 2 * GB
TOO_BIG = "Arquivo maior que 2 GB"
MIN_DURATION_S = 1
MAX_DURATION_S = 10 * 60
TOO_SHORT = "Vídeo com menos de 1 segundo"
TOO_LONG = "Vídeo com mais de 10 minutos"
SPOOL_PREFIX = "proprio-"
TITULO_MAX = 100


def max_bytes() -> int:
    """Lido na hora (os testes reduzem o limite)."""
    return MAX_BYTES


def video_key(conteudo_id: uuid.UUID, content_type: str) -> str:
    return f"conteudos/{conteudo_id}/video.{EXT[content_type]}"


def poster_key(perfil_id: uuid.UUID, conteudo_id: uuid.UUID) -> str:
    return f"perfis/{perfil_id}/conteudos/{conteudo_id}/poster.jpg"


def precheck(db: Session, perfil_id: uuid.UUID, content_length: str | None) -> None:
    cortes_service.precheck(db, perfil_id, content_length,
                            max_body=max_bytes() + cortes_service.MULTIPART_SLACK,
                            too_big=TOO_BIG)


async def receive(request: Request) -> Spooled:
    return await cortes_service.receive(request, max_bytes=max_bytes(), prefix=SPOOL_PREFIX,
                                        too_big=TOO_BIG)


def _titulo(up: Spooled) -> str:
    raw = (up.fields.get("titulo") or "").strip() or up.filename.rsplit(".", 1)[0].strip()
    return raw[:TITULO_MAX]


def create(db: Session, actor: Actor, perfil_id: uuid.UUID, up: Spooled) -> Conteudo:
    return create_de_arquivo(db, actor, perfil_id, up.path, up.filename, _titulo(up), up.size,
                             up.sha256)


def create_de_arquivo(db: Session, actor: Actor, perfil_id: uuid.UUID, path: Path,
                      filename: str, titulo: str, size: int, sha256: str) -> Conteudo:
    """O miolo do envio com o vídeo já no disco (o spool da rota ou, na importação da agência
    da spec 013, o arquivo na montagem só leitura). O `path` só é lido."""
    def enviar(v_key: str, content_type: str) -> None:
        storage.put_file(v_key, path, content_type, bucket="videos")

    return _criar(db, actor, perfil_id, path, filename, titulo, size, sha256, enviar)


def create_de_objeto(db: Session, actor: Actor, perfil_id: uuid.UUID, origem_key: str, *,
                     filename: str, titulo: str, gerado_ia: bool = False) -> Conteudo:
    """Spec 011 (R13): o conteúdo a partir de um vídeo que já está no bucket de vídeos (o
    acabamento do roteiro). O objeto é copiado no MinIO para `conteudos/{id}/video.<ext>` (o
    candidato da geração pode ser limpo depois sem levar o conteúdo junto); o ffprobe e o
    pôster leem uma cópia em `work/tmp` (HD), apagada no fim."""
    with tempfile.TemporaryDirectory(dir=cortes_service.spool_dir(), prefix="objeto-") as tmp:
        path = Path(tmp) / Path(filename).name
        storage.get_to_file(origem_key, path, bucket="videos")
        sha = hashlib.sha256()
        with path.open("rb") as fh:
            for bloco in iter(lambda: fh.read(1024 * 1024), b""):
                sha.update(bloco)

        def enviar(v_key: str, content_type: str) -> None:
            storage.copiar(origem_key, v_key, bucket="videos")

        return _criar(db, actor, perfil_id, path, filename, titulo, path.stat().st_size,
                      sha.hexdigest(), enviar, gerado_ia=gerado_ia)


def _criar(db: Session, actor: Actor, perfil_id: uuid.UUID, path: Path, filename: str,
           titulo: str, size: int, sha256: str, enviar: Callable[[str, str], None], *,
           gerado_ia: bool = False) -> Conteudo:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "perfil_archived", "O perfil está arquivado")
    info = probe(path, max_duration_s=MAX_DURATION_S, min_duration_s=MIN_DURATION_S,
                 max_bytes=max_bytes(), too_long=TOO_LONG, too_short=TOO_SHORT,
                 too_big=TOO_BIG)
    conteudo_id = uuid.uuid4()
    with tempfile.TemporaryDirectory(dir=cortes_service.spool_dir(), prefix="proprio-") as tmp:
        poster = Path(tmp) / "poster.jpg"
        try:
            compose.extract_frame(path, min(1.0, info.duration_s / 2), poster)
        except compose.ComposeError:
            raise InvalidVideo("Não deu para ler um quadro do vídeo") from None
        p_key = poster_key(perfil_id, conteudo_id)
        storage.put(p_key, poster.read_bytes(), "image/jpeg", bucket="imagens")
    v_key = video_key(conteudo_id, info.content_type)
    enviar(v_key, info.content_type)

    conteudo = Conteudo(
        id=conteudo_id, perfil_id=perfil_id, origem=ConteudoOrigem.video_proprio,
        titulo=titulo[:TITULO_MAX], video_key=v_key, video_content_type=info.content_type,
        video_bytes=size, video_sha256=sha256, original_filename=filename,
        duration_ms=info.duration_ms, width=info.width, height=info.height, poster_key=p_key,
        gerado_ia=gerado_ia, created_by=actor.user_id, updated_by=actor.user_id,
    )
    db.add(conteudo)
    db.flush()
    details = {"arquivo": {"nome": filename, "bytes": size, "sha256": sha256}}
    if gerado_ia:
        details["geradoIa"] = True
    history.record(db, actor, ENTITY, conteudo, "created", None, history.snapshot(conteudo),
                   details)
    db.flush()
    db.refresh(conteudo)
    return conteudo
