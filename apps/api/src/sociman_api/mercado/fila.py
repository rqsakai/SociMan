"""A fila do dia (FR-026, R12): calculada pela trilha e materializada em `mercado_fila` por
idempotência (`INSERT … ON CONFLICT DO NOTHING` no índice parcial das tarefas vivas).

Níveis (prioridade): 1 manual e vitrine · 2 novos de lojas seguidas · 3 rankings das categorias ·
4 quentes · 5 semanais (mornas) · 6 lojas e categorias · 7 vídeos · 8 avaliações. Dentro de cada
nível os candidatos são agrupados por perfil (as tarefas sem perfil formam o "perfil" nulo, por
último) e **intercalados um a um** (revezamento); um produto comum entra uma vez, pelo primeiro
perfil cuja vez chegar. O orçamento (`paginas_dia − páginas de hoje − tarefas vivas de hoje`)
corta a lista; o que sobra não vira linha e nasce no dia seguinte com prioridade 0.

Nenhum DELETE: tarefas vencem (`expirada`), falham (`falhou`) ou voltam (`pendente`).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sociman_api.coleta import comum
from sociman_api.mercado import cadencia, interesses, mercados
from sociman_api.mercado import constantes as k
from sociman_api.mercado.fontes.base import BasesUrl
from sociman_api.mercado.fontes.registro import fonte_para
from sociman_api.mercado.models import (
    COLETA_PAUSADAS,
    Calor,
    Categoria,
    Coleta,
    ColetaEstado,
    FilaEstado,
    FotoProduto,
    Interesse,
    InteresseOrigem,
    InteresseSituacao,
    ItemStatus,
    Loja,
    PerfilConfig,
    Produto,
    Tarefa,
    Turno,
)
from sociman_api.perfis.models import Perfil, Platform

# Rankings coletados por categoria por dia (FR-037: "uma coleta por categoria por dia" vale para
# cada tipo); o formato de referência até a sonda com o dono.
RANKING_TIPOS_FILA = ("mais_vendidos", "em_alta")
RANKING_JANELA_FILA = "7d"


@dataclass
class Candidato:
    tipo: str
    chave: str
    url: str | None  # None = sem base configurada: não nasce
    nivel: int
    fonte: str
    perfil_id: uuid.UUID | None
    produto_id: uuid.UUID | None = None
    loja_id: uuid.UUID | None = None
    categoria_id: uuid.UUID | None = None
    turno: Turno | None = None
    prioridade_zero: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def identidade(self) -> tuple[str, str, Turno | None]:
        return (self.tipo, self.chave, self.turno)


Grupos = dict[uuid.UUID | None, list[Candidato]]


def perfis_ordenados(db: Session) -> list[Perfil]:
    return interesses.perfis_ativos(db)


def revezar(grupos: Grupos, ordem: list[uuid.UUID | None]) -> list[Candidato]:
    """Um item de cada perfil por vez, na ordem fixa (nulo por último); produto comum entra uma
    vez, pelo primeiro perfil cuja vez chegar (Clarification 2)."""
    filas = [list(grupos.get(p, [])) for p in ordem if grupos.get(p)]
    vistos: set[tuple[str, str, Turno | None]] = set()
    saida: list[Candidato] = []
    while any(filas):
        for fila_perfil in filas:
            while fila_perfil:
                c = fila_perfil.pop(0)
                if c.identidade in vistos:
                    continue
                vistos.add(c.identidade)
                saida.append(c)
                break
    return saida


def _ordem(perfis: list[Perfil]) -> list[uuid.UUID | None]:
    return [*(p.id for p in perfis), None]


def _adicionar(grupos: Grupos, perfil_id: uuid.UUID | None, c: Candidato) -> None:
    grupos.setdefault(perfil_id, []).append(c)


def _fotos_hoje(db: Session, hoje: date, mercado: str) -> dict[uuid.UUID, set[Turno]]:
    linhas = db.execute(select(FotoProduto.produto_id, FotoProduto.turno)
                        .join(Produto, Produto.id == FotoProduto.produto_id)
                        .where(FotoProduto.data_local == hoje, Produto.mercado == mercado)).all()
    saida: dict[uuid.UUID, set[Turno]] = {}
    for pid, turno in linhas:
        saida.setdefault(pid, set()).add(turno)
    return saida


def _interesses_ativos(db: Session, mercado: str) -> dict[uuid.UUID, list[Interesse]]:
    linhas = db.scalars(select(Interesse).join(Produto, Produto.id == Interesse.mercado_produto_id)
                        .where(Interesse.situacao == InteresseSituacao.ativo,
                               Produto.mercado == mercado)).all()
    saida: dict[uuid.UUID, list[Interesse]] = {}
    for i in linhas:
        saida.setdefault(i.mercado_produto_id, []).append(i)
    return saida


def _turno_para(produto: Produto, fotos: set[Turno], turno_atual: Turno) -> Turno | None | bool:
    """Que tarefa de produto cabe hoje: `False` = nenhuma (já tem foto), `None` = sem turno,
    ou o turno que falta."""
    if produto.fotos_por_dia >= k.FOTOS_POR_DIA_MAX:
        return False if turno_atual in fotos else turno_atual
    return False if fotos else None


def _candidato_produto(produto: Produto, nivel: int, perfil_id: uuid.UUID | None,
                       turno: Turno | None, fonte_rede, prioridade_zero: bool,
                       bases: BasesUrl) -> Candidato:
    return Candidato(tipo="produto", chave=f"produto:{produto.rede_produto_id}",
                     url=fonte_rede.url_tarefa("produto", bases, produto_url=produto.url_canonica),
                     nivel=nivel, fonte="ambas", perfil_id=perfil_id, produto_id=produto.id,
                     turno=turno, prioridade_zero=prioridade_zero or produto.imagens_pendentes,
                     extra={"fotosPorDia": produto.fotos_por_dia})


def _configs(db: Session, perfis: list[Perfil]) -> dict[uuid.UUID, PerfilConfig]:
    ids = [p.id for p in perfis]
    if not ids:
        return {}
    return {c.perfil_id: c for c in db.scalars(select(PerfilConfig)
                                                 .where(PerfilConfig.perfil_id.in_(ids)))}


def _ultima_categorias_em(db: Session, mercado: str) -> date | None:
    return db.scalar(select(func.max(Tarefa.data_local)).where(
        Tarefa.tipo == "categorias", Tarefa.mercado == mercado,
        Tarefa.resultado_status.in_((ItemStatus.gravado, ItemStatus.repetido))))


def montar_fila_do_dia(db: Session, hoje: date, agora: datetime,
                       mercado: str = mercados.PADRAO,
                       rede: Platform = Platform.tiktok) -> int:
    """Monta (idempotente) as tarefas de hoje dentro do orçamento. Devolve quantas nasceram."""
    fonte_rede = fonte_para(rede)
    if fonte_rede is None:
        return 0
    bases = BasesUrl.das_settings()
    cfg = comum.config_atual(db)
    orc = comum.orcamento(db, cfg, mercado, hoje)
    vivas_hoje = db.scalar(select(func.count()).select_from(Tarefa).where(
        Tarefa.data_local == hoje, Tarefa.mercado == mercado,
        Tarefa.estado.in_((FilaEstado.pendente, FilaEstado.reservada)))) or 0
    restante = orc.paginas_restantes - vivas_hoje
    if restante <= 0:
        return 0
    existentes = {(t, c, tu) for t, c, tu in db.execute(
        select(Tarefa.tipo, Tarefa.chave, Tarefa.turno)
        .where(Tarefa.data_local == hoje, Tarefa.mercado == mercado)).all()}
    expiradas_ontem = set(db.scalars(select(Tarefa.chave).where(
        Tarefa.data_local == hoje - timedelta(days=1), Tarefa.mercado == mercado,
        Tarefa.estado == FilaEstado.expirada)))
    turno_atual = mercados.data_local_e_turno(agora, mercado)[1]

    perfis = perfis_ordenados(db)
    ordem = _ordem(perfis)
    configs = _configs(db, perfis)
    fotos_hoje = _fotos_hoje(db, hoje, mercado)
    ativos = _interesses_ativos(db, mercado)
    lojas_seguidas: dict[uuid.UUID, list[uuid.UUID]] = {}
    categorias_por_perfil: dict[uuid.UUID, list[uuid.UUID]] = {}
    for perfil in perfis:
        c = configs.get(perfil.id)
        if c is None:
            continue
        for lid in c.lojas_seguidas:
            lojas_seguidas.setdefault(lid, []).append(perfil.id)
        for cid in c.categoria_ids:
            categorias_por_perfil.setdefault(cid, []).append(perfil.id)

    devidos = db.scalars(select(Produto).where(
        Produto.rede == rede, Produto.mercado == mercado, Produto.calor != Calor.parada,
        (Produto.proxima_coleta_em.is_(None)) | (Produto.proxima_coleta_em <= agora))
        .order_by(Produto.primeira_vez_em.desc())).all()
    desde_novo = agora - timedelta(days=k.NOVO_DIAS)

    niveis: dict[int, Grupos] = {n: {} for n in range(1, 9)}
    ja_produto: set[uuid.UUID] = set()  # produtos já com tarefa de página em nível anterior

    def produto_em(nivel: int, produto: Produto, perfil_id: uuid.UUID | None) -> None:
        turno = _turno_para(produto, fotos_hoje.get(produto.id, set()), turno_atual)
        if turno is False:
            return
        c = _candidato_produto(produto, nivel, perfil_id, turno, fonte_rede,
                               f"produto:{produto.rede_produto_id}" in expiradas_ontem, bases)
        _adicionar(niveis[nivel], perfil_id, c)
        ja_produto.add(produto.id)

    # Nível 1: manual (por perfil) e vitrine (sem perfil), mais a tarefa `vitrine` do dia.
    for produto in devidos:
        for i in ativos.get(produto.id, []):
            if i.origem == InteresseOrigem.manual:
                produto_em(1, produto, i.perfil_id)
            elif i.origem == InteresseOrigem.vitrine:
                produto_em(1, produto, None)
    _adicionar(niveis[1], None, Candidato(tipo="vitrine", chave="vitrine",
                                          url=fonte_rede.url_tarefa("vitrine", bases), nivel=1,
                                          fonte="affiliate", perfil_id=None,
                                          prioridade_zero="vitrine" in expiradas_ontem))
    # Nível 2: novos de lojas seguidas.
    for produto in devidos:
        if produto.id in ja_produto or produto.loja_id not in lojas_seguidas:
            continue
        if produto.primeira_vez_em < desde_novo:
            continue
        for perfil_id in lojas_seguidas[produto.loja_id]:
            produto_em(2, produto, perfil_id)
    # Nível 3: rankings da união das categorias, por tipo (e janela), por dia.
    if categorias_por_perfil:
        cats = {c.id: c for c in db.scalars(select(Categoria).where(
            Categoria.id.in_(list(categorias_por_perfil))))}
        for cid, perfis_ids in categorias_por_perfil.items():
            cat = cats.get(cid)
            if cat is None:
                continue
            for tipo in RANKING_TIPOS_FILA:
                chave = f"ranking:{cat.rede_categoria_id}:{tipo}:{RANKING_JANELA_FILA}"
                for perfil_id in perfis_ids:
                    _adicionar(niveis[3], perfil_id, Candidato(
                        tipo="ranking", chave=chave, nivel=3, fonte="affiliate",
                        url=fonte_rede.url_tarefa("ranking", bases, rede_categoria_id=cat.rede_categoria_id,
                                                  ranking_tipo=tipo, janela=RANKING_JANELA_FILA),
                        perfil_id=perfil_id, categoria_id=cat.id,
                        prioridade_zero=chave in expiradas_ontem,
                        extra={"rankingTipo": tipo, "janela": RANKING_JANELA_FILA}))
    # Níveis 4 e 5: quentes e mornas devidos (pelo perfil com interesse ativo; senão sem perfil).
    for produto in devidos:
        if produto.id in ja_produto:
            continue
        nivel = 4 if produto.calor == Calor.quente else 5
        perfis_ids = [i.perfil_id for i in ativos.get(produto.id, []) if i.perfil_id] or [None]
        for perfil_id in perfis_ids:
            produto_em(nivel, produto, perfil_id)
    # Nível 6: lojas seguidas devidas e a taxonomia (`categorias`) a cada 7 dias.
    if lojas_seguidas:
        for loja in db.scalars(select(Loja).where(
                Loja.id.in_(list(lojas_seguidas)), Loja.mercado == mercado,
                (Loja.proxima_coleta_em.is_(None)) | (Loja.proxima_coleta_em <= agora),
                (Loja.ultima_foto_em.is_(None)) | (Loja.ultima_foto_em < hoje))):
            chave = f"loja:{loja.rede_loja_id}"
            for perfil_id in lojas_seguidas[loja.id]:
                _adicionar(niveis[6], perfil_id, Candidato(
                    tipo="loja", chave=chave, nivel=6, fonte="pagina_publica",
                    url=fonte_rede.url_tarefa("loja", bases, loja_url=loja.url,
                                              rede_loja_id=loja.rede_loja_id),
                    perfil_id=perfil_id, loja_id=loja.id, prioridade_zero=chave in expiradas_ontem))
    ultima_cat = _ultima_categorias_em(db, mercado)
    if ultima_cat is None or (hoje - ultima_cat).days >= k.CATEGORIAS_CADA_DIAS:
        _adicionar(niveis[6], None, Candidato(tipo="categorias", chave="categorias", nivel=6,
                                              fonte="affiliate",
                                              url=fonte_rede.url_tarefa("categorias", bases),
                                              perfil_id=None,
                                              prioridade_zero="categorias" in expiradas_ontem))
    # Níveis 7 e 8: vídeos e avaliações só em quente (FR-040a).
    for produto in devidos:
        if produto.calor != Calor.quente:
            continue
        perfis_ids = [i.perfil_id for i in ativos.get(produto.id, []) if i.perfil_id] or [None]
        if cadencia.precisa_videos(produto.calor, produto.ultimos_videos_em, hoje):
            chave = f"produto_videos:{produto.rede_produto_id}"
            for perfil_id in perfis_ids:
                _adicionar(niveis[7], perfil_id, Candidato(
                    tipo="produto_videos", chave=chave, nivel=7, fonte="affiliate",
                    url=fonte_rede.url_tarefa("produto_videos", bases,
                                              rede_produto_id=produto.rede_produto_id),
                    perfil_id=perfil_id, produto_id=produto.id))
        precisa, paginas = cadencia.precisa_avaliacoes(produto.calor, produto.ultimas_avaliacoes_em,
                                                       hoje)
        if precisa:
            for pagina in range(1, paginas + 1):
                chave = f"avaliacoes:{produto.rede_produto_id}:{pagina}"
                for perfil_id in perfis_ids:
                    _adicionar(niveis[8], perfil_id, Candidato(
                        tipo="avaliacoes", chave=chave, nivel=8, fonte="pagina_publica",
                        url=fonte_rede.url_tarefa("avaliacoes", bases, produto_url=produto.url_canonica,
                                                  pagina=pagina),
                        perfil_id=perfil_id, produto_id=produto.id, extra={"pagina": pagina}))

    escolhidos: list[Candidato] = []
    vistos: set[tuple[str, str, Turno | None]] = set(existentes)
    for nivel in range(1, 9):
        if len(escolhidos) >= restante:
            break
        for c in revezar(niveis[nivel], ordem):
            if len(escolhidos) >= restante:
                break
            if c.identidade in vistos or c.url is None:
                continue
            vistos.add(c.identidade)
            escolhidos.append(c)
    if not escolhidos:
        return 0
    linhas = []
    for idx, c in enumerate(escolhidos):
        linhas.append({
            "id": uuid.uuid4(), "tipo": c.tipo, "rede": rede, "mercado": mercado, "fonte": c.fonte,
            "chave": c.chave, "url": c.url, "nivel": c.nivel,
            "prioridade": 0 if c.prioridade_zero else idx + 1, "perfil_id": c.perfil_id,
            "produto_id": c.produto_id, "loja_id": c.loja_id, "categoria_id": c.categoria_id,
            "data_local": hoje, "turno": c.turno, "estado": FilaEstado.pendente,
            "tentativas": 0, "extra": c.extra})
    r = db.execute(insert(Tarefa).values(linhas).on_conflict_do_nothing())
    return r.rowcount or 0


# ---- manutenção (nenhum DELETE) ----

def devolver_leases_vencidos(db: Session, agora: datetime) -> int:
    """Reserva vencida volta a `pendente` (+1 tentativa); na `FILA_TENTATIVAS_MAX`ª vira `falhou`."""
    vencidas = (Tarefa.estado == FilaEstado.reservada) & (Tarefa.reservada_ate < agora)
    falhas = db.execute(update(Tarefa).where(
        vencidas, Tarefa.tentativas + 1 >= k.FILA_TENTATIVAS_MAX)
        .values(estado=FilaEstado.falhou, reservada_ate=None,
                tentativas=Tarefa.tentativas + 1, erro_codigo="reserva_vencida")).rowcount or 0
    voltas = db.execute(update(Tarefa).where(vencidas)
                        .values(estado=FilaEstado.pendente, reservada_ate=None, cliente_id=None,
                                tentativas=Tarefa.tentativas + 1)).rowcount or 0
    return falhas + voltas


def expirar_dia_anterior(db: Session, hoje: date) -> int:
    """Tarefa viva de um dia que passou vira `expirada`; a chave ganha prioridade 0 amanhã."""
    return db.execute(update(Tarefa).where(
        Tarefa.estado.in_((FilaEstado.pendente, FilaEstado.reservada)), Tarefa.data_local < hoje)
        .values(estado=FilaEstado.expirada, reservada_ate=None, cliente_id=None)).rowcount or 0


def abortar_sem_batimento(db: Session, agora: datetime) -> int:
    """Rodada `ativa` sem batimento há `COLETA_SEM_BATIMENTO_MIN` → `interrompida`; rodada pausada
    sem "Continuar" há `CAPTCHA_ESPERA_MAX_H` → `encerrada` (FR-018)."""
    limite = agora - timedelta(minutes=k.COLETA_SEM_BATIMENTO_MIN)
    n = db.execute(update(Coleta).where(Coleta.estado == ColetaEstado.ativa,
                                        Coleta.batimento_em < limite)
                   .values(estado=ColetaEstado.interrompida, terminada_em=agora)).rowcount or 0
    limite_pausa = agora - timedelta(hours=k.CAPTCHA_ESPERA_MAX_H)
    n += db.execute(update(Coleta).where(Coleta.estado.in_(COLETA_PAUSADAS),
                                         Coleta.batimento_em < limite_pausa)
                    .values(estado=ColetaEstado.encerrada, terminada_em=agora)).rowcount or 0
    if n:
        # As tarefas reservadas dessas rodadas voltam na próxima volta (lease vence).
        db.flush()
    return n
