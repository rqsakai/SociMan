"""Montagem das respostas de interesses, configuração do perfil e categorias (US4), fora dos
routers para os dois (`router.py` e `router_perfil.py`) partilharem."""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.models import User
from sociman_api.history import EntityVersion
from sociman_api.mercado import constantes as k
from sociman_api.mercado import consulta, filtros, interesses, mercados, schemas
from sociman_api.mercado.models import Categoria, Interesse, Loja, PerfilConfig, Produto
from sociman_api.perfis.schemas import Autor, UserRef, Version, VersionsList


def user_ref(db: Session, user_id: uuid.UUID | None) -> UserRef | None:
    if user_id is None:
        return None
    u = db.get(User, user_id)
    return UserRef(id=u.id, name=u.name) if u is not None else None


def versions_list(db: Session, rows: list[EntityVersion]) -> VersionsList:
    """Como `coleta.service._versoes`: autor humano, de sistema ou MCP, sem segredo."""
    autores = history.autores(db, rows)
    ids = {r.actor_user_id for r in rows if r.actor_user_id}
    users = {u.id: UserRef(id=u.id, name=u.name)
             for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    return VersionsList(items=[
        Version(version=r.version, action=r.action,
                actor=users.get(r.actor_user_id) if r.actor_user_id else None,
                actor_kind=r.actor_kind, autor=Autor(**autores[r.id]),
                occurred_at=r.occurred_at, changed_fields=list(r.changed_fields),
                before=r.before, after=r.after, details=r.details)
        for r in rows])


def interesses_out(db: Session, itens: list[Interesse]) -> schemas.InteressesList:
    ids = list(dict.fromkeys(i.mercado_produto_id for i in itens))
    cartoes: dict[uuid.UUID, schemas.CartaoProdutoOut] = {}
    if ids:
        produtos = {p.id: p for p in db.scalars(select(Produto).where(Produto.id.in_(ids)))}
        ordenados = [produtos[i] for i in ids if i in produtos]
        if ordenados:
            f = filtros.montar(db)
            for c in consulta.cartoes(db, ordenados, f, mercados.hoje(f.mercado)):
                cartoes[c.id] = c
    saida = [schemas.InteresseOut(
        id=i.id, perfil_id=i.perfil_id, todos_os_perfis=i.perfil_id is None,
        mercado_produto_id=i.mercado_produto_id, produto=cartoes.get(i.mercado_produto_id),
        origem=i.origem, situacao=i.situacao, motivo=i.motivo, nota=i.nota,
        produto_id=i.produto_id, tema_id=i.tema_id, pausado_em=i.pausado_em,
        encerrado_em=i.encerrado_em, version=i.version, created_at=i.created_at,
        created_by=user_ref(db, i.created_by), updated_at=i.updated_at) for i in itens]
    return schemas.InteressesList(itens=saida, total=len(saida))


def config_out(db: Session, cfg: PerfilConfig) -> schemas.PerfilConfigOut:
    cats = {c.id: c for c in db.scalars(select(Categoria).where(
        Categoria.id.in_(cfg.categoria_ids)))} if cfg.categoria_ids else {}
    lojas = {lj.id: lj for lj in db.scalars(select(Loja).where(
        Loja.id.in_(cfg.lojas_seguidas)))} if cfg.lojas_seguidas else {}
    hoje: date = mercados.hoje(cfg.mercado)
    return schemas.PerfilConfigOut(
        perfil_id=cfg.perfil_id, mercado=cfg.mercado, categoria_ids=list(cfg.categoria_ids),
        categorias=[schemas.CategoriaRef(id=c.id, nome=c.nome, caminho=c.caminho)
                    for i in cfg.categoria_ids if (c := cats.get(i)) is not None],
        lojas_seguidas=[schemas.LojaRef(id=lj.id, nome=lj.nome, oficial=lj.oficial)
                        for i in cfg.lojas_seguidas if (lj := lojas.get(i)) is not None],
        max_relacionados_dia=cfg.max_relacionados_dia, avisar_novo_em_alta=cfg.avisar_novo_em_alta,
        relacionados_hoje=(interesses.relacionados_hoje(db, cfg.perfil_id, hoje, cfg.mercado)
                           if cfg.version else 0),
        maximo_categorias=k.CATEGORIAS_MAX, version=cfg.version,
        updated_at=cfg.updated_at if cfg.version else None,
        updated_by=user_ref(db, cfg.updated_by) if cfg.version else None)


def categorias_out(db: Session, mercado: str, nivel: int | None, q: str | None,
                   so_ativas: bool) -> schemas.CategoriasList:
    stmt = select(Categoria, func.count(Produto.id)).outerjoin(
        Produto, Produto.categoria_id == Categoria.id).where(Categoria.mercado == mercado)
    if nivel is not None:
        stmt = stmt.where(Categoria.nivel == nivel)
    if q:
        stmt = stmt.where(Categoria.caminho.ilike(f"%{q}%"))
    if so_ativas:
        stmt = stmt.where(Categoria.ativa.is_(True))
    linhas = db.execute(stmt.group_by(Categoria.id).order_by(Categoria.nivel, Categoria.caminho)
                        .limit(500)).all()
    return schemas.CategoriasList(itens=[schemas.CategoriaOut(
        id=c.id, rede_categoria_id=c.rede_categoria_id, nome=c.nome, nivel=c.nivel,
        pai_id=c.pai_id, caminho=c.caminho, ativa=c.ativa, n_produtos=n) for c, n in linhas])
