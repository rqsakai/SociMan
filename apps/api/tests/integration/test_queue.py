"""Fila de cortes no Postgres (T025, R1): ordem, SKIP LOCKED, heartbeat e requeue."""

import uuid
from decimal import Decimal

from sqlalchemy import select, text

from sociman_api.cortes import queue
from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.db import get_sessionmaker
from sociman_api.perfis.models import Perfil


def _perfil(db) -> Perfil:
    perfil = Perfil(slug=f"p-{uuid.uuid4().hex[:8]}", name="Perfil")
    db.add(perfil)
    db.commit()
    return perfil


def _corte(db, perfil: Perfil, *, queued_offset_s: int = 0, **overrides) -> Corte:
    cid = uuid.uuid4()
    corte = Corte(
        id=cid, perfil_id=perfil.id, hook_text="Olha isso", kit_version=0, kit_tokens={},
        original_filename="v.mp4", original_key=f"perfis/{perfil.id}/cortes/{cid}/original.mp4",
        original_content_type="video/mp4", original_bytes=1000, duration_ms=10_000,
        width=1080, height=1920, fps=Decimal(30), video_codec="h264", audio_codec="aac",
        original_sha256="0" * 64, **overrides,
    )
    db.add(corte)
    db.commit()
    db.execute(text("UPDATE cortes SET queued_at = now() + make_interval(secs => :s) "
                    "WHERE id = :id"), {"s": queued_offset_s, "id": cid})
    db.commit()
    return corte


def _age_heartbeat(db, corte_id, seconds: int) -> None:
    db.execute(text("UPDATE cortes SET heartbeat_at = now() - make_interval(secs => :s) "
                    "WHERE id = :id"), {"s": seconds, "id": corte_id})
    db.commit()


def _get(corte_id) -> Corte:
    with get_sessionmaker()() as s:
        return s.get(Corte, corte_id)


def test_claim_em_ordem_de_chegada(db):
    perfil = _perfil(db)
    segundo = _corte(db, perfil, queued_offset_s=5)
    primeiro = _corte(db, perfil, queued_offset_s=0)

    job = queue.claim()
    assert job is not None and job.id == primeiro.id and job.attempts == 1
    row = _get(primeiro.id)
    assert row.status == CorteStatus.processando
    assert row.started_at is not None and row.heartbeat_at is not None

    assert queue.claim().id == segundo.id
    assert queue.claim() is None


def test_claim_pula_linha_travada(db):
    """SKIP LOCKED: com o primeiro travado por outra transação, o claim pega o segundo."""
    perfil = _perfil(db)
    primeiro = _corte(db, perfil, queued_offset_s=0)
    segundo = _corte(db, perfil, queued_offset_s=5)
    with get_sessionmaker()() as other, other.begin():
        other.scalar(select(Corte).where(Corte.id == primeiro.id).with_for_update())
        job = queue.claim()
        assert job is not None and job.id == segundo.id
    assert _get(primeiro.id).status == CorteStatus.na_fila


def test_heartbeat_e_fim_so_do_mesmo_processamento(db):
    perfil = _perfil(db)
    corte = _corte(db, perfil)
    job = queue.claim()
    assert queue.heartbeat(job, 42)
    assert _get(corte.id).progress == 42

    # Abandonado e pego de novo: o processamento antigo não toca mais na linha.
    _age_heartbeat(db, corte.id, 300)
    assert queue.requeue_stale() == 1
    novo = queue.claim()
    assert novo.attempts == 2
    assert not queue.heartbeat(job, 90)
    assert not queue.finish_failed(job, code="internal", message="x", processing_ms=1)
    assert queue.finish_ok(novo, result_key="k", result_bytes=10, poster_key=None,
                           processing_ms=5)
    row = _get(corte.id)
    assert row.status == CorteStatus.pronto and row.progress == 100 and row.result_key == "k"


def test_requeue_so_de_heartbeat_antigo(db):
    perfil = _perfil(db)
    corte = _corte(db, perfil)
    queue.claim()
    _age_heartbeat(db, corte.id, 60)
    assert queue.requeue_stale() == 0
    _age_heartbeat(db, corte.id, 121)
    assert queue.requeue_stale() == 1
    row = _get(corte.id)
    assert row.status == CorteStatus.na_fila and row.attempts == 1 and row.heartbeat_at is None


def test_terceiro_abandono_vira_falhou(db):
    perfil = _perfil(db)
    corte = _corte(db, perfil)
    for attempt in (1, 2, 3):
        job = queue.claim()
        assert job.attempts == attempt
        _age_heartbeat(db, corte.id, 300)
        assert queue.requeue_stale() == 1
    row = _get(corte.id)
    assert row.status == CorteStatus.falhou
    assert row.error_code == "interrupted"
    assert row.error_message == "O processamento foi interrompido 3 vezes"
    assert queue.claim() is None


def test_release_nao_conta_tentativa(db):
    perfil = _perfil(db)
    corte = _corte(db, perfil)
    job = queue.claim()
    assert queue.release(job)
    row = _get(corte.id)
    assert row.status == CorteStatus.na_fila and row.attempts == 0
    assert queue.claim().attempts == 1
