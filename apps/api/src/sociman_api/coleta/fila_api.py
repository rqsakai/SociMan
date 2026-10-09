"""`GET /api/coleta/fila` (FR-026): entrega e **reserva** as tarefas do dia ao coletor.

Quem decide o que coletar é o servidor: a fila já está em `mercado_fila` (montada pela trilha
`mercado`); aqui só se escolhe, em ordem `(nivel, prioridade)`, até `min(limite,
itens_por_coleta)` tarefas `pendente` do dia local e do mercado do cliente, marcando o lease
(`reservada`, `reservada_ate`, `cliente_id`). Com a coleta desligada, pausada, fora da janela,
sem orçamento ou sem nada a coletar, a resposta vem com `tarefas: []` e o `motivoVazia`.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sociman_api.coleta import comum, schemas
from sociman_api.coleta.models import ColetaCliente
from sociman_api.mercado import mercados
from sociman_api.mercado.constantes import FILA_LEASE_MIN
from sociman_api.mercado.models import COLETA_PAUSADAS, Coleta, FilaEstado, Tarefa


def _tarefa_out(t: Tarefa) -> schemas.TarefaOut:
    return schemas.TarefaOut(tarefa_id=t.id, tipo=t.tipo, rede=t.rede, mercado=t.mercado,
                             fonte=t.fonte, chave=t.chave, url=t.url, nivel=t.nivel,
                             prioridade=t.prioridade, turno=t.turno.value if t.turno else None,
                             reservada_ate=t.reservada_ate, extra=t.extra)


def _aguardando_continuar(db: Session, cliente_id: uuid.UUID) -> bool:
    return db.scalar(select(Coleta.id).where(Coleta.cliente_id == cliente_id,
                                             Coleta.estado.in_(COLETA_PAUSADAS))) is not None


def reservar(db: Session, cliente: ColetaCliente, limite: int, hoje, agora,
             simular: bool = False) -> list[Tarefa]:
    stmt = (select(Tarefa)
            .where(Tarefa.estado == FilaEstado.pendente, Tarefa.data_local == hoje,
                   Tarefa.mercado == cliente.mercado, Tarefa.rede == cliente.rede)
            .order_by(Tarefa.nivel, Tarefa.prioridade, Tarefa.criada_em)
            .limit(limite))
    if not simular:
        stmt = stmt.with_for_update(skip_locked=True)
    tarefas = list(db.scalars(stmt))
    if tarefas and not simular:
        ids = [t.id for t in tarefas]
        ate = agora + timedelta(minutes=FILA_LEASE_MIN)
        db.execute(update(Tarefa).where(Tarefa.id.in_(ids))
                   .values(estado=FilaEstado.reservada, reservada_ate=ate,
                           cliente_id=cliente.id))
        for t in tarefas:
            t.estado, t.reservada_ate, t.cliente_id = FilaEstado.reservada, ate, cliente.id
    return tarefas


def fila(db: Session, cliente: ColetaCliente, limite: int, ligada: bool,
         simular: bool = False) -> schemas.FilaOut:
    cfg = comum.config_atual(db)
    agora = comum.agora()
    mercado = cliente.mercado
    hoje = mercados.hoje(mercado, agora)
    janela = comum.janela(cfg, mercado, agora)
    orc = comum.orcamento(db, cfg, mercado, hoje)
    motivo: schemas.MotivoVazia | None = None
    tarefas: list[Tarefa] = []
    if not ligada:
        motivo = "desligada"
    elif comum.pausada(cfg, agora):
        motivo = "pausada"
    elif not janela.dentro:
        motivo = "fora_da_janela"
    elif _aguardando_continuar(db, cliente.id):
        motivo = "aguardando_continuar"
    elif orc.paginas_restantes <= 0:
        motivo = "orcamento"
    else:
        n = max(0, min(limite, cfg.itens_por_coleta, orc.paginas_restantes))
        tarefas = reservar(db, cliente, n, hoje, agora, simular=simular)
        if not tarefas:
            motivo = "nada_a_coletar"
    return schemas.FilaOut(
        habilitada=ligada, desligada_no_servidor=not comum.servidor_habilitado(),
        pausada_ate=cfg.pausada_ate, continuar_em=cfg.continuar_em,
        agora_servidor=mercados.agora_local(mercado, agora), data_local=hoje,
        fuso=mercados.mercado(mercado).tz, janela=janela, limites=comum.limites(cfg),
        orcamento=orc, tarefas=[_tarefa_out(t) for t in tarefas], motivo_vazia=motivo)
