"""Trilha `importacao` do agendador (research R7): clipes do OpenShorts → cortes em `revisao`.

Um envio `importando` por volta (`FOR UPDATE SKIP LOCKED`). Para cada clipe de `result.clips`,
em ordem e de forma idempotente (`UNIQUE (envio_id, clip_index)`: o já importado é pulado):
1. legenda do kit (`config.legenda = "kit"`): `POST /api/subtitle` com a seção
   `openshorts.subtitle` resolvida no envio (`config.subtitle`); clipe sem fala segue sem legenda
   (`legenda = sem_fala`);
2. download em streaming para `work/envios/{id}/clip-{i}.mp4` (HD, com o piso de espaço);
3. ffprobe (`cortes/probe.py`, clipe de até 180 s);
4. MinIO: `perfis/{p}/cortes/{corte}/original.mp4` no bucket de vídeos;
5. transcrição (até 4.000 caracteres; uma falha aqui não impede a importação);
6. a linha `cortes` em `revisao` (`origem = openshorts`, trecho, gancho sugerido, textos e score
   do OpenShorts), com versão `created` do `system:agendador` e `created_by` = autor do envio;
7. com a marca automática, o mesmo `marcar` do botão "Aplicar marca" (→ `na_fila`).

O progresso real (FR-010a) é commitado antes de cada passo lento: `legendas` (clipe N de M,
durante o `/api/subtitle`) e `importando` (download e MinIO), com o % geral de 90 a 100.
Cada clipe é commitado ao terminar (um reinício no meio retoma do próximo). A deduplicação é
pelo **trecho** no vídeo de origem (início e fim, com tolerância de 1 s), não pela ordem: um
"tentar de novo" com job novo depois de uma importação parcial pode devolver os clipes em outra
ordem. Clipe com trecho já importado é pulado; os demais entram com o próximo `clip_index`
livre. Só um clipe sem trecho cai na regra antiga (a posição na lista). No fim, `pronto` e o
aviso `envio_pronto`. Falhas: HD fora → continua `importando` e tenta depois; 404 (retenção de
24 h vencida) → `falhou` ("Os clipes expiraram no OpenShorts"), mantendo os já importados;
outros erros → 3 tentativas com backoff e depois `falhou` ("Importar de novo" pelo `retry`).
Sem o sentinela do HD o agendador nem chama esta trilha (e ela confere de novo).
"""

import hashlib
import logging
import re
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from sociman_api import datadir, history, storage
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.conteudos import service as conteudos_service
from sociman_api.cortes import service as cortes_service
from sociman_api.cortes import worker
from sociman_api.cortes.models import Corte, CorteOrigem, CorteStatus
from sociman_api.cortes.probe import InvalidVideo, probe
from sociman_api.cortes.render import HOOK_MAX_CHARS
from sociman_api.envios import avisos, progresso
from sociman_api.envios.models import Envio, EnvioStatus
from sociman_api.envios.openshorts import (
    OpenShortsClient,
    OpenShortsError,
    OpenShortsFora,
    OpenShortsNaoEncontrado,
    OpenShortsRecusou,
    get_openshorts_client,
)
from sociman_api.errors import ApiError

log = logging.getLogger("sociman.agendador.importacao")

SISTEMA = Actor(kind="system:agendador")
MAX_TENTATIVAS = 3
BACKOFF_S = 30  # × tentativas
HD_ESPERA_S = 60
FORA_ESPERA_S = 30
TRANSCRICAO_MAX = 4000
EXPIRADOS = "Os clipes expiraram no OpenShorts"
FALHOU = "Não foi possível importar os clipes ({motivo}); use \"Importar de novo\""
TOLERANCIA_TRECHO_MS = 1000
_CLIP_N = re.compile(r"_clip_(\d+)\.\w+$")


def work_dir(envio_id: uuid.UUID) -> Path:
    return Path(get_settings().data_dir) / "work" / "envios" / str(envio_id)


def indice_openshorts(clip: dict[str, Any], pos: int) -> int:
    """O índice do clipe no metadata do OpenShorts (`<base>_clip_<n>.mp4` → n − 1). Um clipe
    que falhou no render some de `result.clips`, então a posição pode não bater."""
    m = _CLIP_N.search(str(clip.get("video_url") or ""))
    return int(m.group(1)) - 1 if m else pos


def _ms(value: Any) -> int | None:
    try:
        return max(0, round(float(value) * 1000))
    except (TypeError, ValueError):
        return None


def _score(value: Any) -> int | None:
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError):
        return None


def _texto(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None


def _gancho(value: Any) -> str:
    return (str(value or "")).replace("\r\n", "\n").strip()[:HOOK_MAX_CHARS]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _transcricao(client: OpenShortsClient, job_id: str, idx: int) -> str | None:
    try:
        data = client.transcript(job_id, idx)
    except OpenShortsError as exc:
        log.info("transcrição do clipe %s/%s indisponível: %s", job_id, idx, exc)
        return None
    words = [str(c.get("text", "")).strip() for c in data.get("captions") or []
             if isinstance(c, dict)]
    text = " ".join(w for w in words if w)
    return text[:TRANSCRICAO_MAX] or None


def _legendar(client: OpenShortsClient, envio: Envio, idx: int, video_url: str
              ) -> tuple[str, str]:
    """(video_url a baixar, legenda aplicada)."""
    config = envio.config or {}
    legenda = config.get("legenda", "kit")
    if legenda != "kit":
        return video_url, legenda
    assert envio.openshorts_job_id is not None
    try:
        url = client.subtitle(envio.openshorts_job_id, idx, config.get("subtitle") or {},
                              input_filename=video_url.rsplit("/", 1)[-1])
    except OpenShortsRecusou:  # 400: sem transcrição ou sem palavras no trecho
        return video_url, "sem_fala"
    except OpenShortsFora as exc:
        # O gerador embrulha o 400 "No words found" num 500.
        if "no words found" in exc.detail.lower():
            return video_url, "sem_fala"
        raise
    return url, "kit"


def importar_clipe(db: Session, client: OpenShortsClient, envio: Envio, pos: int,
                   clip: dict[str, Any], clip_index: int) -> Corte:
    """`pos` é a posição em `result.clips` deste job; `clip_index`, o índice livre no envio."""
    assert envio.openshorts_job_id is not None
    video_url = str(clip.get("video_url") or "")
    idx = indice_openshorts(clip, pos)
    video_url, legenda = _legendar(client, envio, idx, video_url)
    if legenda == "kit":
        _etapa(db, envio, progresso.Etapa.importando, pos)

    datadir.ensure_writable()
    pasta = work_dir(envio.id)
    pasta.mkdir(parents=True, exist_ok=True)
    dest = pasta / f"clip-{pos}.mp4"
    try:
        client.download(video_url, dest)
        info = probe(dest)
        corte_id = uuid.uuid4()
        key = worker.original_key(envio.perfil_id, corte_id, info.content_type)
        size = storage.put_file(key, dest, info.content_type, bucket="videos")
        sha = _sha256(dest)
    finally:
        dest.unlink(missing_ok=True)

    autor = avisos.autor(envio)
    corte = Corte(
        id=corte_id, perfil_id=envio.perfil_id, hook_text=_gancho(clip.get("viral_hook_text")),
        kit_version=None, kit_tokens=None, status=CorteStatus.revisao,
        origem=CorteOrigem.openshorts, envio_id=envio.id, clip_index=clip_index,
        source_start_ms=_ms(clip.get("start")), source_end_ms=_ms(clip.get("end")),
        openshorts_title=_texto(clip.get("video_title_for_youtube_short")),
        openshorts_description=_texto(clip.get("video_description_for_tiktok")),
        openshorts_score=_score(clip.get("predicted_score")),
        transcript=_transcricao(client, envio.openshorts_job_id, idx), legenda=legenda,
        original_filename=f"clipe-{pos + 1}.mp4", original_key=key,
        original_content_type=info.content_type, original_bytes=size,
        duration_ms=info.duration_ms, width=info.width, height=info.height, fps=info.fps,
        video_codec=info.video_codec, audio_codec=info.audio_codec, original_sha256=sha,
        created_by=autor, updated_by=autor,
    )
    db.add(corte)
    db.flush()
    history.record(db, SISTEMA, cortes_service.ENTITY, corte, "created", None,
                   history.snapshot(corte), {"envio_id": envio.id, "clip_index": clip_index})
    conteudos_service.criar_para_corte(db, SISTEMA, corte)  # spec 014: mesmo id, mesmo flush
    db.flush()
    return corte


def _etapa(db: Session, envio: Envio, etapa: progresso.Etapa, pos: int) -> None:
    """Clipe `pos + 1` de `clipes_previstos` (o total do job), visível já: commit."""
    progresso.gravar(envio, progresso.clipes(etapa, pos, envio.clipes_previstos or pos + 1))
    db.commit()


def _marca_automatica(db: Session, envio: Envio, corte: Corte,
                      kits: cortes_service.KitCache) -> None:
    """O mesmo serviço do botão "Aplicar marca". Se não der (gancho que não cabe, kit com
    referência quebrada), o clipe fica em `revisao` para o usuário ajustar."""
    try:
        with db.begin_nested():
            cortes_service.marcar(db, SISTEMA, corte, kits)
            corte.updated_by = avisos.autor(envio)
    except ApiError as exc:
        log.warning("marca automática do corte %s não aplicada: %s", corte.id, exc.message)


def _importados(db: Session, envio: Envio) -> set[int]:
    return set(db.scalars(select(Corte.clip_index).where(Corte.envio_id == envio.id)))


class Feitos:
    """Os clipes já importados do envio: índices usados e trechos (início, fim) em ms."""

    def __init__(self, db: Session, envio: Envio):
        rows = db.execute(select(Corte.clip_index, Corte.source_start_ms, Corte.source_end_ms)
                          .where(Corte.envio_id == envio.id)).all()
        self.indices: set[int] = {r[0] for r in rows}
        self.trechos: list[tuple[int, int]] = [(r[1], r[2]) for r in rows
                                               if r[1] is not None and r[2] is not None]

    def __len__(self) -> int:
        return len(self.indices)

    def ja_importado(self, clip: dict[str, Any], pos: int) -> bool:
        inicio, fim = _ms(clip.get("start")), _ms(clip.get("end"))
        if inicio is None or fim is None:
            return pos in self.indices  # sem trecho: a regra antiga, pela posição
        return any(abs(inicio - a) <= TOLERANCIA_TRECHO_MS and abs(fim - b) <= TOLERANCIA_TRECHO_MS
                   for a, b in self.trechos)

    def proximo_indice(self, clip: dict[str, Any], pos: int) -> int:
        sem_trecho = _ms(clip.get("start")) is None or _ms(clip.get("end")) is None
        if sem_trecho and pos not in self.indices:
            return pos
        return max(self.indices, default=-1) + 1

    def marcar(self, corte: Corte) -> None:
        assert corte.clip_index is not None
        self.indices.add(corte.clip_index)
        if corte.source_start_ms is not None and corte.source_end_ms is not None:
            self.trechos.append((corte.source_start_ms, corte.source_end_ms))


def _encerrar(envio: Envio) -> None:
    envio.next_attempt_at = None
    envio.finished_at = func.now()
    shutil.rmtree(work_dir(envio.id), ignore_errors=True)


def _falhar(db: Session, envio: Envio, code: str, message: str) -> None:
    envio.status = EnvioStatus.falhou
    envio.error_code = code
    envio.error_message = message
    envio.clips_importados = len(_importados(db, envio))
    _encerrar(envio)
    db.flush()
    avisos.falhou(db, envio)


def _erro(db: Session, envio: Envio, motivo: str, agora: datetime) -> None:
    envio.attempts += 1
    if envio.attempts >= MAX_TENTATIVAS:
        _falhar(db, envio, "import_failed", FALHOU.format(motivo=motivo))
        return
    envio.next_attempt_at = agora + timedelta(seconds=BACKOFF_S * envio.attempts)


def importar(db: Session, client: OpenShortsClient, envio: Envio) -> None:
    agora = datetime.now(UTC)
    if not envio.openshorts_job_id:
        _falhar(db, envio, "openshorts_lost", EXPIRADOS)
        return
    try:
        st = client.status(envio.openshorts_job_id)
    except OpenShortsNaoEncontrado:
        _falhar(db, envio, "clips_expired", EXPIRADOS)
        return
    except OpenShortsError as exc:
        log.warning("envio %s: %s", envio.id, exc)
        envio.next_attempt_at = agora + timedelta(seconds=FORA_ESPERA_S)
        return
    result = st.get("result") or {}
    clips = [c for c in (result.get("clips") or []) if isinstance(c, dict)] \
        if isinstance(result, dict) else []
    if not clips:
        _erro(db, envio, "o OpenShorts não devolveu os clipes", agora)
        return
    envio.clips_total = len(clips)
    envio.clipes_previstos = len(clips)

    feitos = Feitos(db, envio)
    kits = cortes_service.KitCache(db)
    marca = bool((envio.config or {}).get("marca_automatica"))
    kit = (envio.config or {}).get("legenda", "kit") == "kit"
    for pos, clip in enumerate(clips):
        if feitos.ja_importado(clip, pos):
            continue
        _etapa(db, envio, progresso.Etapa.legendas if kit else progresso.Etapa.importando, pos)
        try:
            corte = importar_clipe(db, client, envio, pos, clip, feitos.proximo_indice(clip, pos))
        except OpenShortsNaoEncontrado:
            _falhar(db, envio, "clips_expired", EXPIRADOS)
            return
        except InvalidVideo as exc:
            _erro(db, envio, f"clipe {pos + 1}: {exc.message}", agora)
            return
        except ApiError as exc:  # HD fora ou cheio (503/507): espera, sem contar tentativa
            if exc.status in (503, 507):
                log.warning("envio %s: %s; tento depois", envio.id, exc.message)
                envio.next_attempt_at = agora + timedelta(seconds=HD_ESPERA_S)
                return
            _erro(db, envio, exc.message, agora)
            return
        except (OpenShortsError, ValueError) as exc:  # ValueError: video_url fora de /videos/
            _erro(db, envio, str(exc), agora)
            return
        if marca:
            _marca_automatica(db, envio, corte, kits)
        feitos.marcar(corte)
        envio.clips_importados = len(feitos)
        db.commit()  # cada clipe fica salvo: um reinício retoma do próximo

    envio.status = EnvioStatus.pronto
    envio.clips_importados = len(feitos)
    # Com um job novo depois de uma importação parcial, o envio pode ter mais clipes que o job.
    envio.clips_total = max(len(clips), len(feitos))
    envio.progress = 100
    envio.attempts = 0
    progresso.gravar(envio, progresso.Progresso(progresso.Etapa.concluido, 100, None,
                                                envio.clips_total, None, "Pronto", 100))
    envio.error_code = None
    envio.error_message = None
    _encerrar(envio)
    db.flush()
    avisos.pronto(db, envio)


def rodar(db: Session, client: OpenShortsClient | None = None) -> int:
    """Uma volta da trilha; devolve quantos envios importou (0 = nada a fazer)."""
    if datadir.status().reason == "sem_sentinela":
        return 0
    agora = datetime.now(UTC)
    envio = db.scalar(
        select(Envio)
        .where(Envio.status == EnvioStatus.importando,
               or_(Envio.next_attempt_at.is_(None), Envio.next_attempt_at <= agora))
        .order_by(Envio.sent_at, Envio.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if envio is None:
        return 0
    own = client is None
    client = client or get_openshorts_client()
    try:
        importar(db, client, envio)
    finally:
        if own:
            client.close()
    return 1
