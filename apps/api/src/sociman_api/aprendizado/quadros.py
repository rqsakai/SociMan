"""Quadros dos vídeos para a análise da IA (spec 023, Clarification 1, R5).

Por vídeo, 4 quadros (0,3 s, 2 s, metade e duração − 0,5 s), do arquivo do corte
(`cortes.result_key`) ou do vídeo próprio (`conteudos.video_key`), no bucket `videos`:
1. confere o HD (`datadir.ensure_writable`: marcador e piso; sem eles, `hd_indisponivel`);
2. baixa o vídeo para `work/tmp/aprendizado/<analise>/` no HD (nunca no NVMe) e lê a duração
   real (`cortes.probe`);
3. `cortes.compose.extract_frame` (o ffmpeg que já existe) em cada tempo;
4. reduz com Pillow a 512 px de largura, JPEG q = 80;
5. apaga a pasta no `finally`, com sucesso ou erro.

Vídeo sem arquivo (ou que falha) entra só com texto, e a análise conta quantos.
"""

import io
import logging
import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api import datadir, storage
from sociman_api.aprendizado import constantes as K
from sociman_api.config import get_settings
from sociman_api.conteudos.models import Conteudo
from sociman_api.cortes import compose, probe
from sociman_api.cortes.models import Corte
from sociman_api.errors import ApiError
from sociman_api.metricas.models import VideoRede
from sociman_api.postagem.models import Postagem

log = logging.getLogger(__name__)
PROBE_MAX_S = 4 * 3600  # a duração real do arquivo (os tempos nunca passam do fim)
PROBE_MAX_BYTES = 4 * 1024**3


class HdIndisponivel(Exception):
    """O HD de dados sem o marcador ou sem espaço: a análise com quadros não roda."""


def pasta(analise_id: uuid.UUID) -> Path:
    return Path(get_settings().data_dir) / "work" / "tmp" / "aprendizado" / str(analise_id)


def chaves(db: Session, video_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    """O arquivo final de cada post vinculado (corte pronto ou vídeo próprio)."""
    if not video_ids:
        return {}
    chave = func.coalesce(Corte.result_key, Conteudo.video_key)
    rows = db.execute(
        select(VideoRede.id, chave).join(Postagem, Postagem.id == VideoRede.destino_id)
        .join(Conteudo, Conteudo.id == Postagem.conteudo_id)
        .outerjoin(Corte, Corte.id == Conteudo.corte_id)
        .where(VideoRede.id.in_(list(video_ids)), chave.is_not(None))).all()
    return {vid: key for vid, key in rows}


def tempos(duracao_s: float) -> list[float]:
    d = max(duracao_s, 0.0)
    return [min(0.3, d), min(2.0, d), d * 0.5, max(0.0, d - 0.5)]


def reduzir(caminho: Path) -> bytes:
    with Image.open(caminho) as img:
        img = img.convert("RGB")
        if img.width > K.QUADRO_LARGURA:
            altura = round(img.height * K.QUADRO_LARGURA / img.width)
            img = img.resize((K.QUADRO_LARGURA, altura), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=K.QUADRO_QUALIDADE)
        return buf.getvalue()


def extrair(analise_id: uuid.UUID, videos: Sequence[tuple[uuid.UUID, str, float]]
            ) -> dict[uuid.UUID, list[bytes]]:
    """`videos` = (post, chave no bucket `videos`, duração em s). Devolve os quadros de cada
    post que deu certo; os outros ficam de fora (entram só com texto)."""
    try:
        datadir.ensure_writable()
    except ApiError as exc:
        raise HdIndisponivel(exc.code) from exc
    dir_ = pasta(analise_id)
    out: dict[uuid.UUID, list[bytes]] = {}
    try:
        dir_.mkdir(parents=True, exist_ok=True)
        for vid, key, duracao in videos:
            arquivo = dir_ / f"{vid}.mp4"
            try:
                storage.get_to_file(key, arquivo, bucket="videos")
                real = probe.probe(arquivo, max_duration_s=PROBE_MAX_S,
                                   max_bytes=PROBE_MAX_BYTES).duration_s
                quadros = []
                for i, t in enumerate(tempos(min(duracao, real) if duracao else real)):
                    destino = dir_ / f"{vid}-{i}.png"
                    compose.extract_frame(arquivo, t, destino)
                    quadros.append(reduzir(destino))
                out[vid] = quadros
            except Exception:  # um vídeo ruim não derruba a análise: entra só com texto
                log.warning("quadros do post %s indisponíveis; segue só com texto", vid,
                            exc_info=True)
            finally:
                arquivo.unlink(missing_ok=True)
    finally:
        shutil.rmtree(dir_, ignore_errors=True)
    return out
