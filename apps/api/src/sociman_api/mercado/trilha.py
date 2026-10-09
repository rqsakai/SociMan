"""Trilha `mercado` do agendador (FR-041): a cada volta recalcula a cadência, cria os interesses
automáticos, monta a fila do dia, devolve reservas vencidas, expira o dia anterior, marca rodadas
sem batimento e avisa "coleta parada". **Nenhum DELETE e nenhuma chamada à rede.**

Com `COLETA_HABILITADA=false` a trilha fica ociosa: só devolve reservas e marca rodadas.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.coleta import comum
from sociman_api.mercado import cadencia, fila, interesses, mercados
from sociman_api.mercado import constantes as k
from sociman_api.mercado.models import (
    Calor,
    ColetaItem,
    FotoProduto,
    FotoRanking,
    Interesse,
    InteresseOrigem,
    InteresseSituacao,
    ItemRanking,
    ItemStatus,
    Produto,
    RankingTipo,
)
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo

log = logging.getLogger(__name__)


def ociosa() -> str | None:
    if comum.servidor_habilitado():
        return None
    return "COLETA_HABILITADA=false: a trilha mercado só devolve reservas e marca rodadas"


def rodar(db: Session, agora: datetime | None = None) -> None:
    agora = agora or datetime.now(UTC)
    for mercado in sorted(mercados.MERCADOS):
        _rodar_mercado(db, mercado, agora)
    db.flush()


def _rodar_mercado(db: Session, mercado: str, agora: datetime) -> None:
    hoje = mercados.hoje(mercado, agora)
    devolvidas = fila.devolver_leases_vencidos(db, agora)
    expiradas = fila.expirar_dia_anterior(db, hoje)
    abortadas = fila.abortar_sem_batimento(db, agora)
    if not comum.servidor_habilitado():
        if devolvidas or expiradas or abortadas:
            log.info("trilha mercado (ociosa) %s: %d reservas, %d expiradas, %d rodadas",
                     mercado, devolvidas, expiradas, abortadas)
        return
    recalculados = recalcular_cadencia(db, mercado, hoje, agora)
    por_ranking = interesses.interesses_de_ranking(db, hoje, mercado)
    relacionados = 0
    for perfil in interesses.perfis_ativos(db):
        relacionados += interesses.relacionados_automaticos(db, perfil, hoje, agora)
    novas = 0
    if comum.ligada(db):
        novas = fila.montar_fila_do_dia(db, hoje, agora, mercado)
        avisar_parada(db, mercado, hoje, agora)
    log.info("trilha mercado %s: %d produtos recalculados, %d interesses de ranking, %d "
             "relacionados, %d tarefas novas, %d reservas devolvidas, %d expiradas, %d rodadas",
             mercado, recalculados, por_ranking, relacionados, novas, devolvidas, expiradas,
             abortadas)


# ---- cadência (FR-040) ----

def _em_alta_recentes(db: Session, mercado: str, hoje: date) -> set[uuid.UUID]:
    """Produtos em ranking `em_alta`/`novos` nos últimos 7 dias (entrada de "novo em alta")."""
    desde = hoje - timedelta(days=k.JANELA_CRESCIMENTO_DIAS)
    return set(db.scalars(select(ItemRanking.produto_id).join(
        FotoRanking, FotoRanking.id == ItemRanking.ranking_foto_id).where(
        FotoRanking.mercado == mercado, FotoRanking.data_local >= desde,
        FotoRanking.tipo.in_((RankingTipo.em_alta, RankingTipo.novos)))))


def _vendas_dia_leve(db: Session, produto_id: uuid.UUID) -> float | None:
    """Vendas/dia pelas duas últimas fotos de página com ao menos um dia de distância."""
    fotos = db.execute(select(FotoProduto.data_local, FotoProduto.vendidos)
                       .where(FotoProduto.produto_id == produto_id, FotoProduto.vendidos.is_not(None))
                       .order_by(FotoProduto.data_local.desc(), FotoProduto.coletado_em.desc())
                       .limit(12)).all()
    if len(fotos) < 2:
        return None
    ultima = fotos[0]
    for dia, vendidos in fotos[1:]:
        dias = (ultima[0] - dia).days
        if dias >= k.MIN_DIAS_ENTRE_FOTOS:
            return max(0, (ultima[1] or 0) - (vendidos or 0)) / dias
    return None


def recalcular_cadencia(db: Session, mercado: str, hoje: date, agora: datetime) -> int:
    """Todos os produtos não parados, mais os parados que reapareceram (ranking ou interesse)."""
    ativos_ids = select(Interesse.mercado_produto_id).where(
        Interesse.situacao == InteresseSituacao.ativo)
    produtos = db.scalars(select(Produto).where(
        Produto.mercado == mercado,
        (Produto.calor != Calor.parada)
        | (Produto.ultimo_ranking_em >= hoje - timedelta(days=1))
        | (Produto.id.in_(ativos_ids)))).all()
    if not produtos:
        return 0
    ids = [p.id for p in produtos]
    fotos_hoje: dict[uuid.UUID, int] = dict(db.execute(
        select(FotoProduto.produto_id, func.count(func.distinct(FotoProduto.turno)))
        .where(FotoProduto.produto_id.in_(ids), FotoProduto.data_local == hoje)
        .group_by(FotoProduto.produto_id)).all())
    vivos = db.scalars(select(Interesse).where(Interesse.mercado_produto_id.in_(ids))).all()
    por_produto: dict[uuid.UUID, list[Interesse]] = {}
    for i in vivos:
        por_produto.setdefault(i.mercado_produto_id, []).append(i)
    em_alta = _em_alta_recentes(db, mercado, hoje)
    desde_novo = agora - timedelta(days=k.NOVO_DIAS)
    n = 0
    for p in produtos:
        meus = por_produto.get(p.id, [])
        ativos = [i for i in meus if i.situacao == InteresseSituacao.ativo]
        novo_em_alta = False
        if p.primeira_vez_em >= desde_novo:
            if p.id in em_alta:
                novo_em_alta = True
            else:
                vd = _vendas_dia_leve(db, p.id)
                novo_em_alta = vd is not None and vd >= k.NOVO_VENDAS_DIA_MIN
        entrada = cadencia.Entrada(
            primeira_vez_em=p.primeira_vez_em.date(), ultima_foto_em=p.ultima_foto_em,
            fotos_hoje=fotos_hoje.get(p.id, 0), ultimo_ranking_em=p.ultimo_ranking_em,
            ultimo_interesse_em=max((i.updated_at.date() for i in meus), default=None),
            manual_ativo=any(i.origem == InteresseOrigem.manual for i in ativos),
            vitrine_ativa=any(i.origem == InteresseOrigem.vitrine for i in ativos),
            outro_interesse_ativo=any(i.origem not in (InteresseOrigem.manual,
                                                       InteresseOrigem.vitrine) for i in ativos),
            novo_em_alta=novo_em_alta, ultimas_avaliacoes_em=p.ultimas_avaliacoes_em,
            ultimos_videos_em=p.ultimos_videos_em)
        saida = cadencia.calcular(entrada, hoje)
        p.calor = saida.calor
        p.fotos_por_dia = saida.fotos_por_dia
        if saida.proxima_coleta is None:
            p.proxima_coleta_em = None
        elif saida.proxima_coleta <= hoje:
            p.proxima_coleta_em = min(p.proxima_coleta_em or agora, agora)
        else:
            p.proxima_coleta_em = interesses.inicio_do_dia(saida.proxima_coleta, mercado)
        n += 1
    db.flush()
    return n


# ---- aviso "coleta parada" (FR-041) ----

def avisar_parada(db: Session, mercado: str, hoje: date, agora: datetime) -> bool:
    cfg = comum.config_atual(db)
    ultimo = db.scalar(select(func.max(ColetaItem.recebido_em)).where(
        ColetaItem.status == ItemStatus.gravado))
    referencia = ultimo or cfg.updated_at or cfg.risco_aceito_em
    if referencia is None or agora - referencia < timedelta(hours=k.COLETA_PARADA_H):
        return False
    n = notificacoes.criar(
        db, NotificacaoTipo.coleta_parada, "Coleta parada",
        (f"A coleta está ligada e nada foi gravado há mais de {k.COLETA_PARADA_H} h. Confira o "
         "coletor no desktop (serviço, Chrome e token)."),
        comum.LINK_CONFIG, None, f"coleta:parada:{hoje.isoformat()}", notificacoes.donos_ativos(db))
    return n > 0
