"""Interesses (acompanhamentos) e configuração de mercado do perfil (FR-037..FR-039).

Tudo versionado com `history.py` (`mercado_interesse`, `mercado_perfil_config`). Quem escreve:
qualquer humano (criar por link, pausar, encerrar, seguir loja), o dono (categorias, reverts) e
o sistema (`system:mercado`: vitrine, ranking, loja, categoria). Encerrar nunca apaga.

Nada aqui fala com a rede: um link colado vira um produto do lago "pela cara" (identidade + URL
canônica); a primeira visita do coletor traz a ficha.
"""

import uuid
from datetime import UTC, datetime, time, timedelta
from datetime import date as date_
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.mercado import constantes as k
from sociman_api.mercado import mercados
from sociman_api.mercado.fontes.registro import fonte_para
from sociman_api.mercado.models import (
    Calor,
    Categoria,
    FotoRanking,
    Interesse,
    InteresseOrigem,
    InteresseSituacao,
    ItemRanking,
    Loja,
    PerfilConfig,
    Produto,
)
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo
from sociman_api.perfis.models import Perfil, Platform

ENTITY = "mercado_interesse"
ENTITY_CONFIG = "mercado_perfil_config"
LABEL = "Acompanhamento"
LABEL_CONFIG = "Configuração de mercado do perfil"
SISTEMA = Actor(kind="system:mercado")
VIVOS = (InteresseSituacao.ativo, InteresseSituacao.pausado)
AUTOMATICOS = (InteresseOrigem.ranking, InteresseOrigem.loja, InteresseOrigem.categoria)
RELACIONADOS = (InteresseOrigem.loja, InteresseOrigem.categoria)


# ---- apoio ----

def perfil_ou_404(db: Session, perfil_id: uuid.UUID) -> Perfil:
    perfil = db.get(Perfil, perfil_id)
    if perfil is None:
        raise ApiError(404, "not_found", "Perfil não encontrado")
    return perfil


def perfis_ativos(db: Session) -> list[Perfil]:
    """Em ordem fixa (`created_at`), a mesma do revezamento."""
    return list(db.scalars(select(Perfil).where(Perfil.archived_at.is_(None))
                           .order_by(Perfil.created_at, Perfil.id)))


def inicio_do_dia(dia: date_, mercado: str) -> datetime:
    return datetime.combine(dia, time.min, tzinfo=ZoneInfo(mercados.mercado(mercado).tz))


def interesse_vivo(db: Session, perfil_id: uuid.UUID | None, mercado_produto_id: uuid.UUID,
                   origem: InteresseOrigem) -> Interesse | None:
    """O interesse ativo ou pausado deste perfil (nulo = vitrine), produto e origem."""
    cond = Interesse.perfil_id.is_(None) if perfil_id is None else Interesse.perfil_id == perfil_id
    return db.scalar(select(Interesse).where(
        cond, Interesse.mercado_produto_id == mercado_produto_id, Interesse.origem == origem,
        Interesse.situacao.in_(VIVOS)))


def _algum_vivo(db: Session, perfil_id: uuid.UUID, mercado_produto_id: uuid.UUID) -> bool:
    return db.scalar(select(Interesse.id).where(
        Interesse.perfil_id == perfil_id, Interesse.mercado_produto_id == mercado_produto_id,
        Interesse.situacao.in_(VIVOS))) is not None


def aquecer(produto: Produto, agora: datetime, fotos_por_dia: int = 1) -> None:
    """Um interesse novo (ou reativado) puxa o produto para `quente` e para a fila de hoje
    (SC-005): nada é apagado, só a cadência muda."""
    produto.calor = Calor.quente
    produto.fotos_por_dia = max(produto.fotos_por_dia, fotos_por_dia)
    if produto.proxima_coleta_em is None or produto.proxima_coleta_em > agora:
        produto.proxima_coleta_em = agora


def criar(db: Session, actor: Actor, perfil_id: uuid.UUID | None, mercado_produto_id: uuid.UUID,
          origem: InteresseOrigem, motivo: dict[str, Any] | None = None,
          nota: str = "") -> Interesse:
    """Cria o interesse com histórico (`created`). Quem chama já conferiu a duplicidade."""
    agora = datetime.now(UTC)
    interesse = Interesse(id=uuid.uuid4(), perfil_id=perfil_id,
                          mercado_produto_id=mercado_produto_id, origem=origem,
                          situacao=InteresseSituacao.ativo, motivo=motivo or {}, nota=nota,
                          created_at=agora, updated_at=agora,
                          created_by=actor.user_id, updated_by=actor.user_id)
    db.add(interesse)
    db.flush()
    history.record(db, actor, ENTITY, interesse, "created", None, history.snapshot(interesse),
                   {"origem": origem.value, "perfilId": str(perfil_id) if perfil_id else None})
    return interesse


def vitrine_para_todos(db: Session, produto_ids: list[uuid.UUID],
                       motivo: dict[str, Any] | None = None) -> int:
    """FR-038: cada produto da vitrine do dono vira um interesse `vitrine` com `perfil_id` nulo
    (vale para todos os perfis), sem duplicar. Devolve quantos nasceram."""
    novos = 0
    for pid in dict.fromkeys(produto_ids):
        if interesse_vivo(db, None, pid, InteresseOrigem.vitrine) is None:
            criar(db, SISTEMA, None, pid, InteresseOrigem.vitrine, motivo)
            novos += 1
    return novos


# ---- ações humanas (FR-039) ----

def _produto_por_ref(db: Session, ref, agora: datetime) -> Produto:
    produto = db.scalar(select(Produto).where(
        Produto.rede == ref.rede, Produto.mercado == ref.mercado,
        Produto.rede_produto_id == ref.rede_produto_id))
    if produto is None:
        produto = Produto(id=uuid.uuid4(), rede=ref.rede, mercado=ref.mercado,
                          rede_produto_id=ref.rede_produto_id, url_canonica=ref.url_canonica,
                          primeira_vez_em=agora, ultimo_visto_em=agora, calor=Calor.quente,
                          fotos_por_dia=k.FOTOS_POR_DIA_MAX, proxima_coleta_em=agora,
                          fonte_descoberta=InteresseOrigem.manual)
        db.add(produto)
        db.flush()
    return produto


def _duplicado(interesse: Interesse) -> ApiError:
    return ApiError(409, "interesse_duplicado", "Este perfil já acompanha este produto",
                    details={"interesseId": str(interesse.id), "situacao": interesse.situacao.value})


def acompanhar_por_link(db: Session, actor: Actor, perfil_id: uuid.UUID, url: str, nota: str = "",
                        rede: Platform = Platform.tiktok) -> Interesse:
    """Um link colado vira interesse `manual` (produto do lago criado "pela cara" se for novo)."""
    perfil_ou_404(db, perfil_id)
    cfg = config_perfil(db, perfil_id)
    fonte = fonte_para(rede)
    ref = fonte.produto_de_url(url, cfg.mercado) if fonte else None
    if ref is None:
        raise ApiError(400, "link_invalido", "Não reconheci um produto neste link",
                       details={"field": "url"})
    agora = datetime.now(UTC)
    produto = _produto_por_ref(db, ref, agora)
    vivo = interesse_vivo(db, perfil_id, produto.id, InteresseOrigem.manual)
    if vivo is not None:
        raise _duplicado(vivo)
    interesse = criar(db, actor, perfil_id, produto.id, InteresseOrigem.manual,
                      {"url": ref.url_canonica}, nota)
    aquecer(produto, agora, k.FOTOS_POR_DIA_MAX)
    return interesse


def acompanhar_produto(db: Session, actor: Actor, perfil_id: uuid.UUID,
                       mercado_produto_id: uuid.UUID, nota: str = "") -> Interesse:
    """"Acompanhar neste perfil" a partir do detalhe: interesse `manual` num produto do lago."""
    perfil_ou_404(db, perfil_id)
    produto = db.get(Produto, mercado_produto_id)
    if produto is None:
        raise ApiError(404, "produto_nao_encontrado", "Produto de mercado não encontrado")
    vivo = interesse_vivo(db, perfil_id, produto.id, InteresseOrigem.manual)
    if vivo is not None:
        raise _duplicado(vivo)
    agora = datetime.now(UTC)
    interesse = criar(db, actor, perfil_id, produto.id, InteresseOrigem.manual,
                      {"url": produto.url_canonica}, nota)
    aquecer(produto, agora, k.FOTOS_POR_DIA_MAX)
    return interesse


def _interesse_ou_404(db: Session, interesse_id: uuid.UUID) -> Interesse:
    interesse = db.get(Interesse, interesse_id)
    if interesse is None:
        raise ApiError(404, "not_found", "Acompanhamento não encontrado")
    return interesse


def atualizar(db: Session, actor: Actor, interesse_id: uuid.UUID, version: int,
              situacao: InteresseSituacao | None = None, nota: str | None = None) -> Interesse:
    """Pausar, reativar, encerrar e editar a nota (qualquer humano). Encerrado é final para a
    UQ: um novo interesse pode nascer depois."""
    interesse = _interesse_ou_404(db, interesse_id)
    history.check_version(interesse, version, LABEL)
    if interesse.situacao == InteresseSituacao.encerrado:
        raise ApiError(409, "interesse_encerrado",
                       "Este acompanhamento foi encerrado; acompanhe de novo para reabrir")
    before = history.snapshot(interesse)
    agora = datetime.now(UTC)
    acao = "nota"
    if situacao is not None and situacao != interesse.situacao:
        if situacao == InteresseSituacao.pausado:
            interesse.pausado_em = agora
            acao = "pausado"
        elif situacao == InteresseSituacao.encerrado:
            interesse.encerrado_em = agora
            acao = "encerrado"
        else:
            interesse.pausado_em = None
            acao = "reativado"
            produto = db.get(Produto, interesse.mercado_produto_id)
            if produto is not None:
                aquecer(produto, agora,
                        k.FOTOS_POR_DIA_MAX if interesse.origem == InteresseOrigem.manual else 1)
        interesse.situacao = situacao
    if nota is not None:
        interesse.nota = nota
    interesse.updated_at = agora
    interesse.updated_by = actor.user_id
    history.record(db, actor, ENTITY, interesse, "updated", before, history.snapshot(interesse),
                   {"acao": acao})
    return interesse


def versoes(db: Session, interesse_id: uuid.UUID):
    _interesse_ou_404(db, interesse_id)
    return history.list_versions(db, ENTITY, interesse_id)


def reverter(db: Session, actor: Actor, interesse_id: uuid.UUID, version: int,
             to_version: int) -> Interesse:
    """Só o dono humano (princípio VII)."""
    interesse = _interesse_ou_404(db, interesse_id)
    history.check_version(interesse, version, LABEL)
    alvo = history.version_state(db, ENTITY, interesse_id, to_version)
    if alvo is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    nova = InteresseSituacao(alvo["situacao"]) if alvo.get("situacao") else interesse.situacao
    if nova in VIVOS and interesse.situacao == InteresseSituacao.encerrado:
        outro = interesse_vivo(db, interesse.perfil_id, interesse.mercado_produto_id,
                               interesse.origem)
        if outro is not None and outro.id != interesse.id:
            raise _duplicado(outro)
    before = history.snapshot(interesse)
    for campo in Interesse.__versioned_fields__:
        if campo not in alvo:
            continue
        valor = alvo[campo]
        if campo == "situacao" and valor is not None:
            valor = InteresseSituacao(valor)
        elif campo in ("produto_id", "tema_id") and valor:
            valor = uuid.UUID(valor)
        setattr(interesse, campo, valor)
    agora = datetime.now(UTC)
    interesse.updated_at = agora
    interesse.updated_by = actor.user_id
    if interesse.situacao == InteresseSituacao.ativo:
        produto = db.get(Produto, interesse.mercado_produto_id)
        if produto is not None:
            aquecer(produto, agora)
    history.record(db, actor, ENTITY, interesse, "reverted", before, history.snapshot(interesse),
                   {"toVersion": to_version})
    return interesse


def listar(db: Session, perfil_id: uuid.UUID | None = None,
           origem: InteresseOrigem | None = None,
           situacao: InteresseSituacao | None = None, incluir_vitrine: bool = True,
           limite: int = 500) -> list[Interesse]:
    """Os interesses de um perfil (com os de vitrine, que valem para todos) ou de todos."""
    stmt = select(Interesse)
    if perfil_id is not None:
        cond = Interesse.perfil_id == perfil_id
        if incluir_vitrine:
            cond = cond | Interesse.perfil_id.is_(None)
        stmt = stmt.where(cond)
    if origem is not None:
        stmt = stmt.where(Interesse.origem == origem)
    if situacao is not None:
        stmt = stmt.where(Interesse.situacao == situacao)
    return list(db.scalars(stmt.order_by(Interesse.created_at.desc(), Interesse.id).limit(limite)))


# ---- configuração do perfil (FR-037) ----

def config_perfil(db: Session, perfil_id: uuid.UUID) -> PerfilConfig:
    """A configuração do perfil; sem linha = os padrões, `version 0` (nada gravado até editar)."""
    cfg = db.get(PerfilConfig, perfil_id)
    if cfg is None:
        cfg = PerfilConfig(perfil_id=perfil_id, mercado=mercados.PADRAO, categoria_ids=[],
                           lojas_seguidas=[], max_relacionados_dia=k.MAX_RELACIONADOS_DIA,
                           avisar_novo_em_alta=True)
        cfg.version = 0
    return cfg


def _config_para_escrever(db: Session, actor: Actor, perfil_id: uuid.UUID,
                          version: int) -> tuple[PerfilConfig, dict]:
    perfil_ou_404(db, perfil_id)
    cfg = db.get(PerfilConfig, perfil_id)
    agora = datetime.now(UTC)
    if cfg is None:
        if version != 0:
            raise ApiError(409, "version_conflict", "A configuração mudou; recarregue",
                           details={"versaoAtual": 0})
        cfg = PerfilConfig(perfil_id=perfil_id, mercado=mercados.PADRAO, categoria_ids=[],
                           lojas_seguidas=[], max_relacionados_dia=k.MAX_RELACIONADOS_DIA,
                           avisar_novo_em_alta=True, created_at=agora, updated_at=agora,
                           created_by=actor.user_id, updated_by=actor.user_id)
        db.add(cfg)
        db.flush()
        cfg.version = 0
        return cfg, {}
    history.check_version(cfg, version, LABEL_CONFIG)
    return cfg, history.snapshot(cfg)


class _ConfigEntidade:
    """`history.record` precisa de `id` e `version`; a chave da config é o `perfil_id`."""

    def __init__(self, cfg: PerfilConfig):
        self._cfg = cfg

    @property
    def id(self) -> uuid.UUID:
        return self._cfg.perfil_id

    @property
    def version(self) -> int:
        return self._cfg.version

    @version.setter
    def version(self, v: int) -> None:
        self._cfg.version = v


def _gravar_config(db: Session, actor: Actor, cfg: PerfilConfig, before: dict,
                   detalhes: dict[str, Any]) -> PerfilConfig:
    cfg.updated_at = datetime.now(UTC)
    cfg.updated_by = actor.user_id
    action = "created" if not before else "updated"
    history.record(db, actor, ENTITY_CONFIG, _ConfigEntidade(cfg), action, before or None,
                   history.snapshot(cfg), detalhes)
    db.flush()
    return cfg


def _categorias_existentes(db: Session, ids: list[uuid.UUID], mercado: str) -> None:
    if not ids:
        return
    achadas = set(db.scalars(select(Categoria.id).where(Categoria.id.in_(ids),
                                                         Categoria.mercado == mercado)))
    faltam = [str(i) for i in ids if i not in achadas]
    if faltam:
        raise ApiError(400, "categoria_desconhecida", "Categoria fora da taxonomia deste mercado",
                       details={"field": "categoriaIds", "ids": faltam})


def atualizar_config(db: Session, actor: Actor, perfil_id: uuid.UUID, version: int, *,
                     categoria_ids: list[uuid.UUID], max_relacionados_dia: int,
                     avisar_novo_em_alta: bool, mercado: str | None = None) -> PerfilConfig:
    """Só o dono humano: categorias do nicho (≤ 5), teto de relacionados e o aviso."""
    ids = list(dict.fromkeys(categoria_ids))
    if len(ids) > k.CATEGORIAS_MAX:
        raise ApiError(400, "categorias_maximo",
                       f"No máximo {k.CATEGORIAS_MAX} categorias por perfil",
                       details={"field": "categoriaIds", "maximo": k.CATEGORIAS_MAX})
    cfg, before = _config_para_escrever(db, actor, perfil_id, version)
    alvo_mercado = mercado or cfg.mercado
    if alvo_mercado not in mercados.MERCADOS:
        raise ApiError(400, "mercado_desconhecido", "Mercado não disponível",
                       details={"field": "mercado"})
    _categorias_existentes(db, ids, alvo_mercado)
    cfg.mercado = alvo_mercado
    cfg.categoria_ids = ids
    cfg.max_relacionados_dia = max_relacionados_dia
    cfg.avisar_novo_em_alta = avisar_novo_em_alta
    return _gravar_config(db, actor, cfg, before, {"acao": "editada"})


def _loja_ou_404(db: Session, loja_id: uuid.UUID) -> Loja:
    loja = db.get(Loja, loja_id)
    if loja is None:
        raise ApiError(404, "not_found", "Loja não encontrada")
    return loja


def seguir_loja(db: Session, actor: Actor, perfil_id: uuid.UUID, loja_id: uuid.UUID,
                version: int) -> PerfilConfig:
    """Qualquer humano. Idempotente: seguir de novo não muda nada (e não grava versão)."""
    loja = _loja_ou_404(db, loja_id)
    cfg, before = _config_para_escrever(db, actor, perfil_id, version)
    if loja.id in cfg.lojas_seguidas:
        if not before:
            return _gravar_config(db, actor, cfg, before, {"acao": "seguir_loja", "lojaId": str(loja.id)})
        return cfg
    cfg.lojas_seguidas = [*cfg.lojas_seguidas, loja.id]
    if loja.proxima_coleta_em is None:
        loja.proxima_coleta_em = datetime.now(UTC)
    return _gravar_config(db, actor, cfg, before, {"acao": "seguir_loja", "lojaId": str(loja.id)})


def deixar_de_seguir(db: Session, actor: Actor, perfil_id: uuid.UUID, loja_id: uuid.UUID,
                     version: int) -> PerfilConfig:
    _loja_ou_404(db, loja_id)
    cfg, before = _config_para_escrever(db, actor, perfil_id, version)
    if loja_id not in cfg.lojas_seguidas:
        raise ApiError(409, "loja_nao_seguida", "Este perfil não segue esta loja")
    cfg.lojas_seguidas = [i for i in cfg.lojas_seguidas if i != loja_id]
    return _gravar_config(db, actor, cfg, before, {"acao": "deixar_de_seguir", "lojaId": str(loja_id)})


def versoes_config(db: Session, perfil_id: uuid.UUID):
    perfil_ou_404(db, perfil_id)
    return history.list_versions(db, ENTITY_CONFIG, perfil_id)


def reverter_config(db: Session, actor: Actor, perfil_id: uuid.UUID, version: int,
                    to_version: int) -> PerfilConfig:
    """Só o dono humano (princípio VII)."""
    cfg, before = _config_para_escrever(db, actor, perfil_id, version)
    if not before:
        raise ApiError(404, "not_found", "Versão não encontrada")
    alvo = history.version_state(db, ENTITY_CONFIG, perfil_id, to_version)
    if alvo is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    for campo in PerfilConfig.__versioned_fields__:
        if campo not in alvo:
            continue
        valor = alvo[campo]
        if campo in ("categoria_ids", "lojas_seguidas") and valor is not None:
            valor = [uuid.UUID(v) for v in valor]
        setattr(cfg, campo, valor)
    cfg.updated_at = datetime.now(UTC)
    cfg.updated_by = actor.user_id
    history.record(db, actor, ENTITY_CONFIG, _ConfigEntidade(cfg), "reverted", before,
                   history.snapshot(cfg), {"toVersion": to_version})
    db.flush()
    return cfg


# ---- automáticos (FR-039; autor `system:mercado`) ----

def categorias_com_descendentes(db: Session, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Os produtos ficam na folha; a escolha do dono pode ser um nível acima."""
    todas = set(ids)
    fronteira = list(ids)
    while fronteira:
        filhos = list(db.scalars(select(Categoria.id).where(Categoria.pai_id.in_(fronteira))))
        novos = [f for f in filhos if f not in todas]
        todas.update(novos)
        fronteira = novos
    return todas


def relacionados_hoje(db: Session, perfil_id: uuid.UUID, hoje: date_, mercado: str) -> int:
    return db.scalar(select(func.count()).select_from(Interesse).where(
        Interesse.perfil_id == perfil_id, Interesse.origem.in_(RELACIONADOS),
        Interesse.created_at >= inicio_do_dia(hoje, mercado))) or 0


def relacionados_automaticos(db: Session, perfil: Perfil, hoje: date_, agora: datetime) -> int:
    """Produtos novos (vistos há até 30 dias) de lojas seguidas ou das categorias do perfil viram
    interesses `loja`/`categoria`, até `max_relacionados_dia` por dia local, com um aviso por dia."""
    cfg = config_perfil(db, perfil.id)
    if cfg.version == 0 or cfg.max_relacionados_dia <= 0:
        return 0
    if not cfg.lojas_seguidas and not cfg.categoria_ids:
        return 0
    limite = cfg.max_relacionados_dia - relacionados_hoje(db, perfil.id, hoje, cfg.mercado)
    if limite <= 0:
        return 0
    cats = categorias_com_descendentes(db, cfg.categoria_ids) if cfg.categoria_ids else set()
    desde = agora - timedelta(days=k.NOVO_DIAS)
    cond = []
    if cfg.lojas_seguidas:
        cond.append(Produto.loja_id.in_(cfg.lojas_seguidas))
    if cats:
        cond.append(Produto.categoria_id.in_(cats))
    from sqlalchemy import or_
    candidatos = db.scalars(select(Produto).where(
        Produto.mercado == cfg.mercado, Produto.primeira_vez_em >= desde, or_(*cond))
        .order_by(Produto.primeira_vez_em.desc(), Produto.id).limit(limite * 5)).all()
    novos = 0
    for produto in candidatos:
        if novos >= limite:
            break
        if _algum_vivo(db, perfil.id, produto.id):
            continue
        visto = produto.primeira_vez_em.date().isoformat()
        if cfg.lojas_seguidas and produto.loja_id in cfg.lojas_seguidas:
            origem, motivo = InteresseOrigem.loja, {"lojaId": str(produto.loja_id), "vistoEm": visto}
        else:
            origem, motivo = InteresseOrigem.categoria, {"categoriaId": str(produto.categoria_id),
                                                         "vistoEm": visto}
        criar(db, SISTEMA, perfil.id, produto.id, origem, motivo)
        aquecer(produto, agora)
        novos += 1
    if novos:
        total = relacionados_hoje(db, perfil.id, hoje, cfg.mercado)
        notificacoes.criar(
            db, NotificacaoTipo.mercado_interesse_auto,
            f"{perfil.name}: produtos novos acompanhados",
            (f"O SociMan passou a acompanhar {total} produto(s) novo(s) de lojas seguidas e das "
             f"categorias do nicho hoje. Pause ou encerre os que não interessam."),
            f"/app/perfis/{perfil.id}?aba=mercado", ("perfil", perfil.id),
            f"mercado:interesse_auto:{perfil.id}:{hoje.isoformat()}", notificacoes.donos_ativos(db))
    return novos


def interesses_de_ranking(db: Session, hoje: date_, mercado: str) -> int:
    """Os primeiros `RANKING_ACOMPANHAR_TOP` de cada ranking de hoje viram interesses `ranking`
    nos perfis cujas categorias (com descendentes) incluem a do ranking."""
    fotos = db.scalars(select(FotoRanking).where(FotoRanking.data_local == hoje,
                                                 FotoRanking.mercado == mercado,
                                                 FotoRanking.categoria_id.is_not(None))).all()
    if not fotos:
        return 0
    perfis = perfis_ativos(db)
    alvo: list[tuple[Perfil, set[uuid.UUID]]] = []
    for perfil in perfis:
        cfg = config_perfil(db, perfil.id)
        if cfg.categoria_ids:
            alvo.append((perfil, categorias_com_descendentes(db, cfg.categoria_ids)))
    if not alvo:
        return 0
    agora = datetime.now(UTC)
    novos = 0
    for foto in fotos:
        itens = db.scalars(select(ItemRanking).where(
            ItemRanking.ranking_foto_id == foto.id,
            ItemRanking.posicao <= k.RANKING_ACOMPANHAR_TOP).order_by(ItemRanking.posicao)).all()
        for perfil, cats in alvo:
            if foto.categoria_id not in cats:
                continue
            for item in itens:
                if interesse_vivo(db, perfil.id, item.produto_id, InteresseOrigem.ranking):
                    continue
                criar(db, SISTEMA, perfil.id, item.produto_id, InteresseOrigem.ranking,
                      {"rankingFotoId": str(foto.id), "posicao": item.posicao,
                       "categoriaId": str(foto.categoria_id)})
                produto = db.get(Produto, item.produto_id)
                if produto is not None:
                    aquecer(produto, agora)
                novos += 1
    return novos
