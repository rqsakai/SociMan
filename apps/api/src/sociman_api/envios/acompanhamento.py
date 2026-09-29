"""Trilha `openshorts` do agendador (research R6): submissão, polling e backoff dos envios.

Cada volta (a cada `AGENDADOR_OPENSHORTS_S`, 10 s):
1. **submete** os envios `na_fila` e `aguardando_openshorts` vencidos (`next_attempt_at`), na
   ordem de envio. O SociMan não segura a fila: submete todos e deixa o OpenShorts enfileirar
   (`MAX_CONCURRENT_JOBS=1` lá). O avulso por arquivo reserva o upload e faz o `PUT` em
   streaming a partir do MinIO;
2. faz o **polling** dos `processando` (`GET /api/status/{job}`).

Tabela de respostas de R6:
- `{job_id}` → `processando`; `needs_confirmation` → `confirmar_qualidade` + aviso, **sem
  reenviar sozinho**; 429 → `na_fila` com +60 s; 400/403 → `falhou` com o motivo traduzido;
- fora do ar (conexão, timeout, 5xx) → `aguardando_openshorts` com backoff de 30 s → 1 → 2 →
  5 min, e volta sozinho. Depois de 30 min sem resposta, um aviso `openshorts_fora` por período;
- polling: `queued` guarda a posição; `processing` estima o progresso (teto de 90%);
  `completed` → `importando`; `failed` → `sem_clipes` ("No clips could be rendered") ou
  `falhou`; 404 → `falhou` ("O OpenShorts não tem mais este job; envie de novo").

Tudo é estado de job (sem versão). O estado fica no banco: reiniciar o agendador continua o
polling. O cliente entra por parâmetro (os testes passam o fake).
"""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from sociman_api import storage
from sociman_api.envios import avisos
from sociman_api.envios.models import Envio, EnvioOrigem, EnvioStatus
from sociman_api.envios.openshorts import (
    OpenShortsClient,
    OpenShortsError,
    OpenShortsFora,
    OpenShortsNaoEncontrado,
    OpenShortsOcupado,
    OpenShortsRecusou,
    corpo_process,
    get_openshorts_client,
)

log = logging.getLogger("sociman.agendador.openshorts")

LOTE = 20
BACKOFF_FORA_S = (30, 60, 120, 300)
OCUPADO_S = 60
FORA_AVISO = timedelta(minutes=30)
PROGRESSO_TETO = 90
CLIPES_PADRAO = 5  # sem quantidade (a IA decide), a estimativa usa 5 clipes

JOB_PERDIDO = "O OpenShorts não tem mais este job; envie de novo"
SEM_CLIPES = "O OpenShorts não encontrou clipes neste vídeo"
BAIXA_QUALIDADE = ("O vídeo só está disponível em baixa resolução ({altura}p); "
                   "envie mesmo assim ou descarte")

# Trechos conhecidos do `detail` do OpenShorts → mensagem em pt-BR.
MOTIVOS: tuple[tuple[str, str], ...] = (
    ("clip generation needs at least",
     "Vídeo curto demais: o OpenShorts precisa de pelo menos 45 segundos"),
    ("Paste the link of one video", "O link não é de um vídeo (playlist, canal ou busca)"),
    ("can't be processed", "O OpenShorts não aceita este link"),
    ("URL ingest is disabled", "O OpenShorts está configurado para não baixar links do YouTube"),
    ("File too large", "Arquivo grande demais para o OpenShorts"),
    ("private", "O vídeo é privado ou exige login"),
    ("Unknown or expired upload_id", "O upload expirou no OpenShorts; tente de novo"),
)


def traduzir(detail: str) -> str:
    for trecho, mensagem in MOTIVOS:
        if trecho.lower() in detail.lower():
            return mensagem
    return f"O OpenShorts recusou o vídeo: {detail}" if detail else "O OpenShorts recusou o vídeo"


def _agora() -> datetime:
    return datetime.now(UTC)


def _vencidos(status: tuple[EnvioStatus, ...], agora: datetime):
    return (
        select(Envio)
        .where(Envio.status.in_(status),
               or_(Envio.next_attempt_at.is_(None), Envio.next_attempt_at <= agora))
        .order_by(Envio.sent_at, Envio.id)
        .limit(LOTE)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


def _falhar(db: Session, envio: Envio, code: str, message: str) -> None:
    envio.status = EnvioStatus.falhou
    envio.error_code = code
    envio.error_message = message
    envio.next_attempt_at = None
    envio.openshorts_queue_pos = None
    envio.finished_at = func.now()
    db.flush()
    avisos.falhou(db, envio)


def _fora(envio: Envio, agora: datetime, aguardar: bool) -> None:
    """Backoff 30 s → 1 → 2 → 5 min (teto); na submissão, o envio vai para
    `aguardando_openshorts`."""
    envio.attempts = min(envio.attempts + 1, 32767)
    espera = BACKOFF_FORA_S[min(envio.attempts, len(BACKOFF_FORA_S)) - 1]
    envio.next_attempt_at = agora + timedelta(seconds=espera)
    if aguardar:
        envio.status = EnvioStatus.aguardando_openshorts


def _chunks(key: str) -> Iterator[bytes]:
    resp = storage.get_client().get_object(storage.bucket_name("videos"), key)
    try:
        yield from resp.stream(storage.CHUNK * 16)
    finally:
        resp.close()
        resp.release_conn()


def _corpo(client: OpenShortsClient, envio: Envio) -> dict[str, Any]:
    if envio.origem == EnvioOrigem.avulso_arquivo:
        assert envio.upload_key is not None
        size = storage.stat(envio.upload_key, bucket="videos").size
        nome = envio.upload_key.rsplit("/", 1)[-1]
        upload_id = client.reserve_upload(nome)
        client.put_upload(upload_id, _chunks(envio.upload_key), size)
        return corpo_process(envio.config or {}, upload_id=upload_id,
                             force_low_quality=envio.force_low_quality)
    return corpo_process(envio.config or {}, url=envio.source_url,
                         force_low_quality=envio.force_low_quality)


def submeter(db: Session, client: OpenShortsClient, envio: Envio, agora: datetime) -> None:
    try:
        resp = client.process(_corpo(client, envio))
    except OpenShortsFora as exc:
        log.warning("envio %s: %s", envio.id, exc)
        _fora(envio, agora, aguardar=True)
        return
    except OpenShortsOcupado:
        envio.status = EnvioStatus.na_fila
        envio.next_attempt_at = agora + timedelta(seconds=OCUPADO_S)
        envio.last_polled_at = agora
        return
    except (OpenShortsRecusou, OpenShortsNaoEncontrado) as exc:
        envio.last_polled_at = agora
        _falhar(db, envio, "source_invalid", traduzir(exc.detail))
        return

    envio.last_polled_at = agora
    envio.attempts = 0
    if resp.get("needs_confirmation"):
        altura = (resp.get("quality_check") or {}).get("max_height") or "?"
        envio.status = EnvioStatus.confirmar_qualidade
        envio.error_message = BAIXA_QUALIDADE.format(altura=altura)
        envio.next_attempt_at = None
        db.flush()
        avisos.confirmar_qualidade(db, envio)
        return
    job_id = resp.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        log.warning("envio %s: resposta do /api/process sem job_id", envio.id)
        _fora(envio, agora, aguardar=True)
        return
    envio.status = EnvioStatus.processando
    envio.openshorts_job_id = job_id
    envio.openshorts_queue_pos = None
    envio.error_code = None
    envio.error_message = None
    envio.next_attempt_at = None


def _ultima_linha(logs: Any) -> str:
    if not isinstance(logs, list):
        return ""
    for line in reversed(logs):
        text = str(line).strip()
        if text:
            return text[:300]
    return ""


def _clipes(status: dict[str, Any]) -> list[Any]:
    result = status.get("result") or {}
    clips = result.get("clips") if isinstance(result, dict) else None
    return clips if isinstance(clips, list) else []


def acompanhar(db: Session, client: OpenShortsClient, envio: Envio, agora: datetime) -> None:
    assert envio.openshorts_job_id is not None
    try:
        st = client.status(envio.openshorts_job_id)
    except OpenShortsNaoEncontrado:
        envio.last_polled_at = agora
        _falhar(db, envio, "openshorts_lost", JOB_PERDIDO)
        return
    except (OpenShortsFora, OpenShortsOcupado, OpenShortsRecusou) as exc:
        log.warning("envio %s: %s", envio.id, exc)
        _fora(envio, agora, aguardar=False)
        return

    envio.last_polled_at = agora
    envio.attempts = 0
    envio.next_attempt_at = None
    estado = st.get("status")
    if estado == "queued":
        pos = (st.get("queue") or {}).get("position")
        envio.openshorts_queue_pos = pos if isinstance(pos, int) and pos > 0 else None
        envio.progress = 0
    elif estado == "processing":
        envio.openshorts_queue_pos = None
        if envio.started_at is None:
            envio.started_at = func.now()
        prontos = len(_clipes(st))
        alvo = (envio.config or {}).get("quantidade") or CLIPES_PADRAO
        envio.progress = min(PROGRESSO_TETO, int(prontos * PROGRESSO_TETO / alvo))
    elif estado == "completed":
        clips = _clipes(st)
        envio.openshorts_queue_pos = None
        if not clips:
            _sem_clipes(db, envio)
            return
        envio.status = EnvioStatus.importando
        envio.clips_total = len(clips)
        envio.progress = PROGRESSO_TETO
        if envio.started_at is None:
            envio.started_at = func.now()
    elif estado == "failed":
        linha = _ultima_linha(st.get("logs"))
        logs = " ".join(str(x) for x in (st.get("logs") or []))
        if "No clips could be rendered" in logs:
            _sem_clipes(db, envio)
        else:
            _falhar(db, envio, "openshorts_failed",
                    f"O OpenShorts falhou: {linha}" if linha else "O OpenShorts falhou")


def _sem_clipes(db: Session, envio: Envio) -> None:
    envio.status = EnvioStatus.sem_clipes
    envio.error_code = "no_clips"
    envio.error_message = SEM_CLIPES
    envio.openshorts_queue_pos = None
    envio.finished_at = func.now()
    db.flush()
    avisos.sem_clipes(db, envio)


def _aviso_fora(db: Session, agora: datetime) -> None:
    """Um aviso por período fora do ar: os envios esperando (ou em polling) sem resposta do
    OpenShorts há 30 min ou mais."""
    ultimo_contato = func.coalesce(Envio.last_polled_at, Envio.sent_at)
    envios = list(db.scalars(
        select(Envio).where(
            Envio.status.in_((EnvioStatus.aguardando_openshorts, EnvioStatus.processando)),
            Envio.attempts > 0,
            ultimo_contato <= agora - FORA_AVISO,
        )
    ))
    if not envios:
        return
    desde = min((e.last_polled_at or e.sent_at) for e in envios)
    avisos.openshorts_fora(db, desde, envios)


def rodar(db: Session, client: OpenShortsClient | None = None) -> int:
    """Uma volta da trilha; devolve quantos envios tratou (0 = nada a fazer)."""
    own = client is None
    client = client or get_openshorts_client()
    try:
        agora = _agora()
        tratados = 0
        fora = False
        submetidos: set = set()
        for envio in list(db.scalars(_vencidos(
                (EnvioStatus.na_fila, EnvioStatus.aguardando_openshorts), agora))):
            submetidos.add(envio.id)
            try:
                submeter(db, client, envio, agora)
            except Exception:  # ex.: MinIO fora no upload do avulso; o envio espera e tenta
                log.exception("envio %s: falha na submissão", envio.id)
                _fora(envio, agora, aguardar=False)
            fora = fora or envio.status == EnvioStatus.aguardando_openshorts
            db.flush()
            tratados += 1
        for envio in list(db.scalars(_vencidos((EnvioStatus.processando,), agora))):
            if envio.id in submetidos:  # acabou de ser submetido: o polling fica para a próxima
                continue
            try:
                acompanhar(db, client, envio, agora)
            except OpenShortsError as exc:  # defensivo: nada escapa por envio
                log.warning("envio %s: %s", envio.id, exc)
            fora = fora or (envio.status == EnvioStatus.processando and envio.attempts > 0)
            db.flush()
            tratados += 1
        if fora:
            _aviso_fora(db, agora)
        return tratados
    finally:
        if own:
            client.close()
