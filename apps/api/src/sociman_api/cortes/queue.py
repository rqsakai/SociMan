"""Fila de cortes na própria tabela `cortes` (research R1).

- `claim`: pega o próximo `na_fila` por `queued_at` com `FOR UPDATE SKIP LOCKED`, marca
  `processando`, `started_at`, `heartbeat_at` e `attempts + 1`, e faz commit antes do ffmpeg;
- `requeue_stale`: devolve para `na_fila` todo `processando` sem heartbeat há mais de 120 s;
  na 3ª tentativa interrompida, o corte vai para `falhou` ("O processamento foi interrompido 3
  vezes");
- `heartbeat`, `finish_ok`, `finish_failed` e `release` só tocam a linha se ela ainda for do
  mesmo processamento (`status = processando` e o mesmo `attempts`): um corte devolvido à fila
  e pego de novo nunca é sobrescrito pelo processamento antigo.

Os horários vêm sempre do relógio do banco (`now()`). Cada função abre e fecha a própria
transação, porque o worker fica minutos entre uma e outra.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.orm import Session

from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.db import get_sessionmaker

STALE_S = 120
MAX_ATTEMPTS = 3
INTERRUPTED = "O processamento foi interrompido 3 vezes"


@dataclass(frozen=True)
class Job:
    """O que o worker precisa do corte pego (uma cópia; a sessão já foi fechada)."""

    id: uuid.UUID
    perfil_id: uuid.UUID
    attempts: int
    hook_text: str
    kit_tokens: dict[str, Any]
    original_key: str
    original_content_type: str
    original_bytes: int
    duration_ms: int
    width: int
    height: int
    fps: Decimal
    audio_codec: str | None


def _job(c: Corte) -> Job:
    return Job(id=c.id, perfil_id=c.perfil_id, attempts=c.attempts, hook_text=c.hook_text,
               kit_tokens=c.kit_tokens, original_key=c.original_key,
               original_content_type=c.original_content_type, original_bytes=c.original_bytes,
               duration_ms=c.duration_ms, width=c.width, height=c.height, fps=c.fps,
               audio_codec=c.audio_codec)


def _session() -> Session:
    return get_sessionmaker()()


def _mine(job: Job):
    """A linha ainda é deste processamento."""
    return and_(Corte.id == job.id, Corte.status == CorteStatus.processando,
                Corte.attempts == job.attempts)


def requeue_stale(stale_s: int = STALE_S) -> int:
    """Devolve à fila (ou dá como falho) os `processando` abandonados. Devolve quantos."""
    with _session() as db, db.begin():
        rows = db.scalars(
            select(Corte)
            .where(Corte.status == CorteStatus.processando,
                   Corte.heartbeat_at < func.now() - text(f"interval '{int(stale_s)} seconds'"))
            .with_for_update(skip_locked=True)
        ).all()
        for c in rows:
            c.heartbeat_at = None
            c.progress = 0
            if c.attempts >= MAX_ATTEMPTS:
                c.status = CorteStatus.falhou
                c.error_code = "interrupted"
                c.error_message = INTERRUPTED
                c.finished_at = func.now()
            else:
                c.status = CorteStatus.na_fila
        return len(rows)


def claim() -> Job | None:
    """O próximo corte da fila, já marcado `processando` (commit feito), ou None."""
    with _session() as db, db.begin():
        c = db.scalar(
            select(Corte)
            .where(Corte.status == CorteStatus.na_fila)
            .order_by(Corte.queued_at, Corte.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if c is None:
            return None
        c.status = CorteStatus.processando
        c.attempts += 1
        c.progress = 0
        c.started_at = func.now()
        c.heartbeat_at = func.now()
        c.error_code = None
        c.error_message = None
        db.flush()
        return _job(c)


def heartbeat(job: Job, progress: int) -> bool:
    """Grava o progresso e o `heartbeat_at`. False = a linha não é mais deste processamento."""
    with _session() as db, db.begin():
        res = db.execute(update(Corte).where(_mine(job)).values(
            progress=max(0, min(100, progress)), heartbeat_at=func.now()))
        return res.rowcount == 1


def finish_ok(job: Job, *, result_key: str, result_bytes: int, poster_key: str | None,
              processing_ms: int) -> bool:
    with _session() as db, db.begin():
        res = db.execute(update(Corte).where(_mine(job)).values(
            status=CorteStatus.pronto, progress=100, result_key=result_key,
            result_bytes=result_bytes, poster_key=poster_key, processing_ms=processing_ms,
            finished_at=func.now(), heartbeat_at=None, error_code=None, error_message=None))
        return res.rowcount == 1


def finish_failed(job: Job, *, code: str, message: str, processing_ms: int | None) -> bool:
    with _session() as db, db.begin():
        res = db.execute(update(Corte).where(_mine(job)).values(
            status=CorteStatus.falhou, error_code=code, error_message=message,
            processing_ms=processing_ms, finished_at=func.now(), heartbeat_at=None))
        return res.rowcount == 1


def release(job: Job) -> bool:
    """Devolve à fila sem contar a tentativa (HD sumiu no meio, ou o worker foi parado)."""
    with _session() as db, db.begin():
        res = db.execute(update(Corte).where(_mine(job)).values(
            status=CorteStatus.na_fila, attempts=Corte.attempts - 1, progress=0,
            heartbeat_at=None))
        return res.rowcount == 1
