"""Fila das gerações na própria tabela `geracoes` (research R2), no padrão da fila de cortes.

- `proxima(motores)`: espia (sem travar) o próximo `na_fila` vencido, por `created_at, id`;
- `claim(geracao_id)`: pega aquela geração com `FOR UPDATE SKIP LOCKED`, marca `rodando`,
  `started_at`, `heartbeat_at` e `attempts + 1`, e faz commit antes do motor. O índice único
  `uq_geracoes_gpu_rodando` recusa um 2º job de GPU rodando, mesmo com dois processos;
- `aguardar_gpu`: a GPU não está livre → toda a fila de GPU fica "Aguardando a GPU ficar livre"
  com a mesma próxima tentativa (+30 s), **sem** contar tentativa (a ordem de pedido se mantém);
- `heartbeat`: grava andamento e `heartbeat_at`; False = a linha não é mais deste processamento
  (cancelada, ou devolvida e pega de novo);
- `requeue_stale`: devolve à fila todo `rodando` sem heartbeat há mais de 120 s, **sem** gastar
  a tentativa (`attempts` é o orçamento das esperas por memória e por serviço fora, R8) e somando
  em `interrupcoes`; na 3ª interrupção, vai para `falhou` (`internal`);
- os fins "é meu" (`para_revisao`, `para_falhou`, `para_espera`, `para_escolhido_auto`,
  `para_entregue`, `devolver`) só tocam a linha se ela ainda for deste processamento (`status =
  rodando` e o mesmo `attempts`): uma geração cancelada nunca é sobrescrita pelo resultado que
  chega depois (FR-011).

**Toda transição chama `Aplicador.ao_mudar_estado` na mesma transação** (uma exceção no gancho
desfaz a transição). Os horários vêm do relógio do banco. Cada função abre e fecha a própria
transação, porque o gerador fica minutos entre uma e outra. Tudo aqui é estado de job (sem
versão, R10).
"""

import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api.db import get_sessionmaker
from sociman_api.geracao import aplicadores
from sociman_api.geracao.models import (
    TERMINADOS,
    Geracao,
    GeracaoAlvo,
    GeracaoCandidato,
    GeracaoMotor,
    GeracaoStatus,
)

log = logging.getLogger("sociman.gerador")

STALE_S = 120
MAX_INTERRUPCOES = 3
INTERROMPIDA = "O processamento foi interrompido 3 vezes"
AGUARDANDO_GPU = "Aguardando a GPU ficar livre"


@dataclass(frozen=True)
class Job:
    """O que o gerador precisa da geração pega (uma cópia; a sessão já foi fechada)."""

    id: uuid.UUID
    perfil_id: uuid.UUID | None  # o perfil base usado (spec 029)
    alvo_tipo: GeracaoAlvo
    alvo_id: uuid.UUID
    passo: str
    motor: GeracaoMotor
    params: dict[str, Any]
    n_opcoes: int
    attempts: int
    created_by: uuid.UUID | None


def _job(g: Geracao) -> Job:
    return Job(id=g.id, perfil_id=g.perfil_id, alvo_tipo=g.alvo_tipo, alvo_id=g.alvo_id,
               passo=g.passo, motor=g.motor, params=dict(g.params), n_opcoes=g.n_opcoes,
               attempts=g.attempts, created_by=g.created_by)


def _session() -> Session:
    return get_sessionmaker()()


def _vencida():
    return or_(Geracao.next_attempt_at.is_(None), Geracao.next_attempt_at <= func.now())


def transicao(db: Session, g: Geracao, para: GeracaoStatus) -> None:
    """Muda o status e chama o gancho do aplicador na mesma transação."""
    de = g.status
    g.status = para
    if para in TERMINADOS:
        g.finished_at = func.now()
    db.flush()
    aplicadores.chamar_gancho(db, g, de, para)


def abertas_do_alvo(db: Session, alvo_tipo: GeracaoAlvo, alvo_id: uuid.UUID,
                    exceto: uuid.UUID | None = None) -> list[Geracao]:
    """As gerações não terminadas do alvo (helper para os aplicadores, R15)."""
    stmt = select(Geracao).where(Geracao.alvo_tipo == alvo_tipo, Geracao.alvo_id == alvo_id,
                                 Geracao.status.not_in(TERMINADOS))
    if exceto is not None:
        stmt = stmt.where(Geracao.id != exceto)
    return list(db.scalars(stmt.order_by(Geracao.created_at, Geracao.id)))


# ---- pegar ----

def proxima(motores: Iterable[GeracaoMotor]) -> Job | None:
    with _session() as db:
        g = db.scalar(select(Geracao)
                      .where(Geracao.status == GeracaoStatus.na_fila,
                             Geracao.motor.in_(list(motores)), _vencida())
                      .order_by(Geracao.created_at, Geracao.id).limit(1))
        return _job(g) if g is not None else None


def claim(geracao_id: uuid.UUID) -> Job | None:
    """A geração já marcada `rodando` (commit feito), ou None (pega por outro, cancelada, ainda
    em espera, ou outro job de GPU rodando)."""
    db = _session()
    try:
        with db.begin():
            g = db.scalar(select(Geracao)
                          .where(Geracao.id == geracao_id,
                                 Geracao.status == GeracaoStatus.na_fila, _vencida())
                          .with_for_update(skip_locked=True))
            if g is None:
                return None
            g.attempts += 1
            g.progress = 0
            g.started_at = func.now()
            g.heartbeat_at = func.now()
            g.next_attempt_at = None
            g.error_code = None
            g.error_message = None
            g.etapa_mensagem = "Começando"
            transicao(db, g, GeracaoStatus.rodando)
            job = _job(g)
        return job
    except IntegrityError as exc:
        if "uq_geracoes_gpu_rodando" in str(exc.orig):
            log.warning("já há um job de GPU rodando; %s fica na fila", geracao_id)
            return None
        raise
    finally:
        db.close()


def aguardar_gpu(motores: Iterable[GeracaoMotor], mensagem: str = AGUARDANDO_GPU,
                 depois_s: float = 30) -> int:
    """Adia toda a fila vencida desses motores, sem contar tentativa (FR-018, FR-020)."""
    with _session() as db, db.begin():
        res = db.execute(update(Geracao).where(
            Geracao.status == GeracaoStatus.na_fila, Geracao.motor.in_(list(motores)),
            _vencida()).values(
            etapa_mensagem=mensagem,
            next_attempt_at=func.now() + text(f"interval '{int(depois_s)} seconds'")))
        return res.rowcount


def marcar_mensagem(motores: Iterable[GeracaoMotor], mensagem: str) -> int:
    """Só a mensagem (ex.: o ajuste de memória do ComfyUI não está configurado)."""
    with _session() as db, db.begin():
        res = db.execute(update(Geracao).where(
            Geracao.status == GeracaoStatus.na_fila, Geracao.motor.in_(list(motores)),
            or_(Geracao.etapa_mensagem.is_(None), Geracao.etapa_mensagem != mensagem))
            .values(etapa_mensagem=mensagem))
        return res.rowcount


def requeue_stale(stale_s: int = STALE_S) -> int:
    """Devolve à fila (ou dá como falhas) as `rodando` abandonadas (FR-023). Devolve quantas."""
    with _session() as db, db.begin():
        rows = db.scalars(
            select(Geracao)
            .where(Geracao.status == GeracaoStatus.rodando,
                   Geracao.heartbeat_at < func.now() - text(f"interval '{int(stale_s)} seconds'"))
            .with_for_update(skip_locked=True)).all()
        for g in rows:
            g.heartbeat_at = None
            g.progress = 0
            g.attempts -= 1  # a interrupção não gasta o orçamento das esperas (FR-018)
            g.interrupcoes += 1
            if g.interrupcoes >= MAX_INTERRUPCOES:
                g.error_code, g.error_message = "internal", INTERROMPIDA
                g.etapa_mensagem = None
                transicao(db, g, GeracaoStatus.falhou)
            else:
                g.etapa_mensagem = "Retomando depois de uma interrupção"
                transicao(db, g, GeracaoStatus.na_fila)
        return len(rows)


# ---- durante o job ----

def _mine(job: Job):
    return and_(Geracao.id == job.id, Geracao.status == GeracaoStatus.rodando,
                Geracao.attempts == job.attempts)


def heartbeat(job: Job, progress: int | None = None, mensagem: str | None = None) -> bool:
    values: dict[str, Any] = {"heartbeat_at": func.now()}
    if progress is not None:
        values["progress"] = max(0, min(100, progress))
    if mensagem is not None:
        values["etapa_mensagem"] = mensagem
    with _session() as db, db.begin():
        return db.execute(update(Geracao).where(_mine(job)).values(**values)).rowcount == 1


def status_atual(geracao_id: uuid.UUID) -> GeracaoStatus | None:
    with _session() as db:
        return db.scalar(select(Geracao.status).where(Geracao.id == geracao_id))


def _travar_meu(db: Session, job: Job) -> Geracao | None:
    return db.scalar(select(Geracao).where(_mine(job)).with_for_update())


def gravar_candidato(job: Job, gravar: Callable[[Session], GeracaoCandidato]) -> bool:
    """Grava uma opção assim que fica pronta (R7). `gravar(db)` cria as linhas (imagem ou áudio
    e o candidato) na mesma transação; se a geração não é mais deste processamento, nada fica."""
    with _session() as db, db.begin():
        if _travar_meu(db, job) is None:
            return False
        gravar(db)
        db.flush()
        return True


def _fim(job: Job, fazer: Callable[[Session, Geracao], None]) -> bool:
    with _session() as db, db.begin():
        g = _travar_meu(db, job)
        if g is None:
            return False
        g.heartbeat_at = None
        fazer(db, g)
        return True


def para_revisao(job: Job, mensagem: str | None = None) -> bool:
    def fazer(db: Session, g: Geracao) -> None:
        g.progress, g.etapa_mensagem = 100, mensagem
        transicao(db, g, GeracaoStatus.revisao)
    return _fim(job, fazer)


def para_falhou(job: Job, code: str, message: str) -> bool:
    def fazer(db: Session, g: Geracao) -> None:
        g.error_code, g.error_message, g.etapa_mensagem = code, message, None
        transicao(db, g, GeracaoStatus.falhou)
    return _fim(job, fazer)


def para_espera(job: Job, code: str, message: str, depois: timedelta, *,
                conta_tentativa: bool = True) -> bool:
    """De volta à fila com espera (`gpu_ocupada` sem contar tentativa; os outros contam)."""
    def fazer(db: Session, g: Geracao) -> None:
        if not conta_tentativa:
            g.attempts -= 1
        g.progress = 0
        g.error_code = None if code == "gpu_ocupada" else code
        g.error_message = None if code == "gpu_ocupada" else message
        g.etapa_mensagem = message
        g.next_attempt_at = func.now() + text(f"interval '{int(depois.total_seconds())} seconds'")
        transicao(db, g, GeracaoStatus.na_fila)
    return _fim(job, fazer)


def devolver(job: Job) -> bool:
    """Devolve à fila sem contar a tentativa (o gerador foi parado, ou o HD sumiu)."""
    def fazer(db: Session, g: Geracao) -> None:
        g.attempts -= 1
        g.progress = 0
        g.etapa_mensagem = None
        transicao(db, g, GeracaoStatus.na_fila)
    return _fim(job, fazer)


def para_escolhido_auto(job: Job, candidato_id: uuid.UUID,
                        aplicar: Callable[[Session, Geracao, GeracaoCandidato], None]) -> bool:
    """Passo sem escolha (FR-010, FR-031): `aplicar` leva o resultado ao alvo na mesma transação
    (com autor = quem pediu) e a geração vai a `escolhido` como estado de job."""
    def fazer(db: Session, g: Geracao) -> None:
        cand = db.get(GeracaoCandidato, candidato_id)
        aplicar(db, g, cand)
        g.escolhido_id = cand.id
        g.progress, g.etapa_mensagem = 100, None
        transicao(db, g, GeracaoStatus.escolhido)
    return _fim(job, fazer)


def para_entregue(job: Job) -> bool:
    """`voz.teste`: o áudio fica pronto para ouvir, sem escolha e sem mudar o alvo."""
    def fazer(db: Session, g: Geracao) -> None:
        g.progress, g.etapa_mensagem = 100, None
        transicao(db, g, GeracaoStatus.entregue)
    return _fim(job, fazer)
