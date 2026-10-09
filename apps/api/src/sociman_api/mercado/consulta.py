"""Leitura do lago (FR-042..FR-050): só `SELECT`, nenhuma tabela agregada, nada gravado.

A lista de produtos ordena **no SQL** por uma chave aproximada (a última foto no período, a última
antes dele e a última do Affiliate Center, por subconsultas correlacionadas) e pagina; só a página
recebe o cálculo completo em Python (`calculo.py`) a partir das fotos de uma janela que cobre o
período, os 7 dias anteriores (crescimento) e o período anterior.

`perfilId` só restringe: produtos com interesse do perfil (ativo ou pausado), ou da vitrine
(perfil nulo), ou com `categoria_id` nas categorias do perfil (e nas filhas, pelo `caminho`).
"""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from sociman_api import imaging, midia
from sociman_api.errors import ApiError
from sociman_api.mercado import adotar as adotar_mod
from sociman_api.mercado import calculo as calc
from sociman_api.mercado import constantes as k
from sociman_api.mercado import schemas
from sociman_api.mercado.filtros import Filtro, cursor_para
from sociman_api.mercado.models import (
    Categoria,
    Ficha,
    Fonte,
    FotoProduto,
    FotoRanking,
    Imagem,
    Interesse,
    InteresseSituacao,
    ItemRanking,
    Loja,
    PerfilConfig,
    Produto,
    ProdutoImagem,
    RankingTipo,
)
from sociman_api.perfis.models import Perfil

JANELA_FOTOS_DIAS = 2 * k.JANELA_CRESCIMENTO_DIAS + 1  # para o crescimento (7 d + 7 d anteriores)
VIVOS = (InteresseSituacao.ativo, InteresseSituacao.pausado)
CONSTANTES_PUBLICAS = {
    "minFotosVendas": k.MIN_FOTOS_VENDAS, "amostraPequenaDias": k.AMOSTRA_PEQUENA_DIAS,
    "kAfiliados": k.K_AFILIADOS, "comissaoMinBp": k.COMISSAO_MIN_BP,
    "acFotoMaxDias": k.AC_FOTO_MAX_DIAS, "minProdutosCategoria": k.MIN_PRODUTOS_CATEGORIA,
    "poucosAfiliados": k.POUCOS_AFILIADOS, "novoDias": k.NOVO_DIAS,
    "novoVendasDiaMin": k.NOVO_VENDAS_DIA_MIN, "novoCrescimentoMin": k.NOVO_CRESCIMENTO_MIN,
    "altaPosicoes": k.ALTA_POSICOES, "minVendasDiaBase": k.MIN_VENDAS_DIA_BASE,
}


# ---- helpers de filtro ----

def categorias_com_filhas(db: Session, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """As categorias e todas as descendentes (pelo prefixo do `caminho`)."""
    if not ids:
        return set()
    bases = db.scalars(select(Categoria).where(Categoria.id.in_(ids))).all()
    out = {c.id for c in bases}
    for c in bases:
        out |= set(db.scalars(select(Categoria.id).where(
            Categoria.rede == c.rede, Categoria.mercado == c.mercado,
            Categoria.caminho.like(c.caminho.replace("%", r"\%") + " > %"))).all())
    return out


def _interesses_vivos_do_perfil(perfil_id: uuid.UUID | None):
    cond = [Interesse.situacao.in_(VIVOS)]
    if perfil_id is not None:
        cond.append(or_(Interesse.perfil_id == perfil_id, Interesse.perfil_id.is_(None)))
    return select(Interesse.mercado_produto_id).where(*cond)


def base_produtos(db: Session, f: Filtro) -> Select:
    stmt = select(Produto).where(Produto.mercado == f.mercado)
    if f.rede is not None:
        stmt = stmt.where(Produto.rede == f.rede)
    if f.loja_id is not None:
        stmt = stmt.where(Produto.loja_id == f.loja_id)
    if f.categoria_id is not None:
        stmt = stmt.where(Produto.categoria_id.in_(categorias_com_filhas(db, [f.categoria_id])))
    if f.q:
        stmt = stmt.where(or_(
            Produto.rede_produto_id == f.q,
            func.to_tsvector("portuguese", func.coalesce(Produto.titulo_atual, "")).op("@@")(
                func.plainto_tsquery("portuguese", f.q)),
            Produto.titulo_atual.ilike(f"%{f.q}%")))
    if f.perfil_id is not None:
        cfg = db.get(PerfilConfig, f.perfil_id)
        cats = categorias_com_filhas(db, list(cfg.categoria_ids)) if cfg else set()
        cond = [Produto.id.in_(_interesses_vivos_do_perfil(f.perfil_id))]
        if cats:
            cond.append(Produto.categoria_id.in_(cats))
        stmt = stmt.where(or_(*cond))
    if f.so_acompanhados:
        stmt = stmt.where(Produto.id.in_(
            select(Interesse.mercado_produto_id).where(Interesse.situacao == InteresseSituacao.ativo,
                                                       *([or_(Interesse.perfil_id == f.perfil_id,
                                                              Interesse.perfil_id.is_(None))]
                                                         if f.perfil_id else []))))
    if f.origens:
        sub = select(Interesse.mercado_produto_id).where(Interesse.situacao.in_(VIVOS),
                                                        Interesse.origem.in_(f.origens))
        if f.perfil_id is not None:
            sub = sub.where(or_(Interesse.perfil_id == f.perfil_id, Interesse.perfil_id.is_(None)))
        stmt = stmt.where(Produto.id.in_(sub))
    return stmt


# ---- ordenação no SQL (aproximada; o cálculo exato é da página) ----

def _ultima(coluna, ate: date, fonte: Fonte | None = None, com_vendidos: bool = True):
    cond = [FotoProduto.produto_id == Produto.id, FotoProduto.data_local <= ate]
    if com_vendidos:
        cond.append(FotoProduto.vendidos.is_not(None))
    if fonte is not None:
        cond.append(FotoProduto.fonte == fonte)
    return (select(coluna).where(*cond)
            .order_by(FotoProduto.data_local.desc(), FotoProduto.turno.desc())
            .limit(1).scalar_subquery())


def _primeira_no_periodo(coluna, de: date, ate: date):
    return (select(coluna).where(FotoProduto.produto_id == Produto.id,
                                 FotoProduto.data_local >= de, FotoProduto.data_local <= ate,
                                 FotoProduto.vendidos.is_not(None))
            .order_by(FotoProduto.data_local, FotoProduto.turno).limit(1).scalar_subquery())


def chave_de_ordem(f: Filtro):
    p = f.atual
    v_fim = _ultima(FotoProduto.vendidos, p.ate)
    v_ini = func.coalesce(_ultima(FotoProduto.vendidos, p.de - timedelta(days=1)),
                          _primeira_no_periodo(FotoProduto.vendidos, p.de, p.ate))
    vendas = func.greatest(v_fim - v_ini, 0)
    preco = _ultima(FotoProduto.preco_min_centavos, p.ate, com_vendidos=False)
    comissao = _ultima(FotoProduto.comissao_bp, p.ate, Fonte.affiliate, com_vendidos=False)
    criadores = _ultima(FotoProduto.n_criadores, p.ate, Fonte.affiliate, com_vendidos=False)
    v7 = _ultima(FotoProduto.vendidos, p.ate - timedelta(days=7))
    v14 = _ultima(FotoProduto.vendidos, p.ate - timedelta(days=14))
    chaves = {
        "vendasPeriodo": vendas,
        "gmvPeriodo": vendas * func.coalesce(preco, 0),
        "crescimento": case((v7 - v14 > 0, (v_fim - v7) / func.nullif(v7 - v14, 0)), else_=None),
        "vendasTotais": v_fim,
        "gmvTotal": v_fim * func.coalesce(preco, 0),
        "preco": preco,
        "comissaoBp": comissao,
        "comissaoPorVenda": func.coalesce(preco, 0) * func.coalesce(comissao, 0),
        "retornoAfiliado": (vendas * func.coalesce(preco, 0) * func.coalesce(comissao, 0)
                            / (func.coalesce(criadores, 0) + k.K_AFILIADOS)),
        "nCriadores": criadores,
        "primeiraVezEm": Produto.primeira_vez_em,
        "ultimaFotoEm": Produto.ultima_foto_em,
        "titulo": func.lower(func.coalesce(Produto.titulo_atual, "")),
    }
    return chaves[f.ordenar]


# ---- cálculo da página ----

def _fotos_de(db: Session, ids: list[uuid.UUID], de: date, ate: date
              ) -> dict[uuid.UUID, list[calc.Foto]]:
    out: dict[uuid.UUID, list[calc.Foto]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.scalars(select(FotoProduto).where(FotoProduto.produto_id.in_(ids),
                                                FotoProduto.data_local >= de,
                                                FotoProduto.data_local <= ate)).all()
    for r in rows:
        out[r.produto_id].append(calc.Foto(
            r.data_local, r.turno.value, r.fonte.value, r.vendidos, r.vendidos_min,
            r.vendidos_max, r.vendidos_exato, r.preco_min_centavos, r.preco_max_centavos,
            r.preco_original_centavos, r.comissao_bp, r.n_criadores, r.vendas_7d, r.vendas_30d,
            r.disponivel))
    return out


def _posicoes_de(db: Session, ids: list[uuid.UUID], ate: date
                 ) -> dict[uuid.UUID, list[schemas.PosicaoRanking]]:
    """As posições atuais (último dia ≤ ate de cada ranking) com a variação em 7 dias."""
    out: dict[uuid.UUID, list[schemas.PosicaoRanking]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.execute(
        select(ItemRanking.produto_id, ItemRanking.posicao, FotoRanking.categoria_id,
               FotoRanking.tipo, FotoRanking.janela, FotoRanking.data_local)
        .join(FotoRanking, FotoRanking.id == ItemRanking.ranking_foto_id)
        .where(ItemRanking.produto_id.in_(ids), FotoRanking.data_local <= ate,
               FotoRanking.data_local >= ate - timedelta(days=8))).all()
    por: dict[tuple, dict[date, int]] = {}
    for pid, pos, cat, tipo, jan, d in rows:
        por.setdefault((pid, cat, tipo, jan), {})[d] = pos
    for (pid, cat, tipo, jan), posicoes in por.items():
        dia = max(posicoes)
        atual = posicoes[dia]
        antes = [d for d in posicoes if d <= dia - timedelta(days=7)]
        var = (posicoes[max(antes)] - atual) if antes else None
        out[pid].append(schemas.PosicaoRanking(categoria_id=cat, tipo=tipo, janela=jan,
                                               posicao=atual, variacao7d=var, data_local=dia))
    return out


def _interesses_de(db: Session, ids: list[uuid.UUID], perfil_id: uuid.UUID | None
                   ) -> dict[uuid.UUID, list[schemas.InteresseResumo]]:
    out: dict[uuid.UUID, list[schemas.InteresseResumo]] = {i: [] for i in ids}
    if not ids:
        return out
    stmt = select(Interesse).where(Interesse.mercado_produto_id.in_(ids),
                                   Interesse.situacao.in_(VIVOS))
    if perfil_id is not None:
        stmt = stmt.where(or_(Interesse.perfil_id == perfil_id, Interesse.perfil_id.is_(None)))
    for i in db.scalars(stmt):
        out[i.mercado_produto_id].append(schemas.InteresseResumo(
            id=i.id, perfil_id=i.perfil_id, origem=i.origem, situacao=i.situacao))
    return out


def _imagem_url_de(db: Session, produtos: list[Produto]) -> dict[uuid.UUID, str | None]:
    fichas = [p.ficha_atual_id for p in produtos if p.ficha_atual_id]
    out: dict[uuid.UUID, str | None] = {p.id: None for p in produtos}
    if not fichas:
        return out
    rows = db.execute(select(ProdutoImagem.produto_id, Imagem.object_key)
                      .join(Imagem, Imagem.id == ProdutoImagem.imagem_id)
                      .where(ProdutoImagem.ficha_id.in_(fichas), ProdutoImagem.posicao == 0)).all()
    for pid, key in rows:
        out[pid] = imaging.image_urls(key)["medium"]
    return out


def _refs(db: Session, produtos: list[Produto]) -> tuple[dict, dict]:
    lojas = {l.id: l for l in db.scalars(select(Loja).where(
        Loja.id.in_({p.loja_id for p in produtos if p.loja_id})))} if produtos else {}
    cats = {c.id: c for c in db.scalars(select(Categoria).where(
        Categoria.id.in_({p.categoria_id for p in produtos if p.categoria_id})))} \
        if produtos else {}
    return lojas, cats


def loja_ref(l: Loja | None) -> schemas.LojaRef | None:
    return schemas.LojaRef(id=l.id, nome=l.nome, oficial=l.oficial) if l else None


def categoria_ref(c: Categoria | None) -> schemas.CategoriaRef | None:
    return schemas.CategoriaRef(id=c.id, nome=c.nome, caminho=c.caminho) if c else None


def _numero(n: calc.Numero) -> schemas.Numero:
    return schemas.Numero(valor=n.valor, estimado=n.estimado, motivos=n.motivos,
                          amostra_pequena=n.amostra_pequena, n_fotos=n.n_fotos, min=n.min,
                          max=n.max)


def comparaveis_da_categoria(db: Session, categoria_id: uuid.UUID | None, ate: date
                             ) -> calc.Comparaveis | None:
    """FR-047: P25 de criadores e P75 do retorno por afiliado entre os produtos da categoria com
    foto recente do Affiliate Center (aproximação por `vendas_7d`); None sem categoria."""
    if categoria_id is None:
        return None
    ult = (select(FotoProduto.produto_id, FotoProduto.n_criadores, FotoProduto.comissao_bp,
                  FotoProduto.vendas_7d, FotoProduto.preco_min_centavos)
           .distinct(FotoProduto.produto_id)
           .join(Produto, Produto.id == FotoProduto.produto_id)
           .where(Produto.categoria_id == categoria_id, FotoProduto.fonte == Fonte.affiliate,
                  FotoProduto.data_local <= ate,
                  FotoProduto.data_local >= ate - timedelta(days=k.AC_FOTO_MAX_DIAS))
           .order_by(FotoProduto.produto_id, FotoProduto.data_local.desc(),
                     FotoProduto.turno.desc()))
    rows = db.execute(ult).all()
    criadores = [float(r.n_criadores) for r in rows if r.n_criadores is not None]
    retornos = [r.vendas_7d / 7 * (r.preco_min_centavos or 0) * (r.comissao_bp or 0) / 10000
                / ((r.n_criadores or 0) + k.K_AFILIADOS)
                for r in rows if r.vendas_7d is not None and r.n_criadores is not None]
    return calc.Comparaveis(calc.percentil(criadores, k.P_CRIADORES),
                            calc.percentil(retornos, k.P_RETORNO), None, len(rows))


def cartao(p: Produto, fotos: list[calc.Foto], f: Filtro, hoje: date, lojas: dict, cats: dict,
           posicoes: list[schemas.PosicaoRanking], interesses: list[schemas.InteresseResumo],
           imagem_url: str | None, comparaveis: calc.Comparaveis | None
           ) -> schemas.CartaoProdutoOut:
    de, ate = f.atual.de, f.atual.ate
    est = calc.estado(fotos, ate)
    vd = calc.vendas_dia(fotos, ate)
    cresc = calc.crescimento(fotos, ate)
    af = calc.ultima(fotos, ate, "affiliate")
    preco = calc.preco_de(fotos, ate)
    comissao_bp = af.comissao_bp if af else None
    n_criadores = af.n_criadores if af else None
    cv = calc.comissao_por_venda(preco.preco_min_centavos if preco else None, comissao_bp)
    rd = calc.retorno_dia(vd, cv)
    ra = calc.retorno_por_afiliado(rd, n_criadores)
    dias_af = (ate - af.data_local).days if af else None
    em_alta = any(r.tipo in (RankingTipo.em_alta, RankingTipo.novos) for r in posicoes)
    subiu = max((r.variacao7d for r in posicoes if r.variacao7d is not None), default=None)
    alto, poucos = calc.alto_retorno_poucos_afiliados(comissao_bp, dias_af, n_criadores, ra,
                                                      comparaveis)
    return schemas.CartaoProdutoOut(
        id=p.id, rede=p.rede, mercado=p.mercado, rede_produto_id=p.rede_produto_id,
        titulo=p.titulo_atual, url_canonica=p.url_canonica, imagem_url=imagem_url,
        loja=loja_ref(lojas.get(p.loja_id)), categoria=categoria_ref(cats.get(p.categoria_id)),
        estado=est, calor=p.calor, fotos_por_dia=p.fotos_por_dia,
        primeira_vez_em=p.primeira_vez_em, lancado_em=p.lancado_em,
        ultima_foto_em=p.ultima_foto_em, ultima_foto_affiliate_em=p.ultima_foto_affiliate_em,
        indisponivel_desde=p.indisponivel_desde,
        preco=schemas.PrecoOut(min_centavos=preco.preco_min_centavos,
                               max_centavos=preco.preco_max_centavos,
                               original_centavos=preco.preco_original_centavos,
                               moeda="BRL", data_local=preco.data_local) if preco else None,
        comissao_bp=_numero(calc.Numero(comissao_bp, True, ["fonte_affiliate"], False, 1)
                            if comissao_bp is not None else calc.Numero.nulo("sem_dado_afiliado")),
        comissao_por_venda_centavos=_numero(cv),
        n_criadores=_numero(calc.Numero(n_criadores, True, ["fonte_affiliate"], False, 1)
                            if n_criadores is not None else calc.Numero.nulo("sem_dado_afiliado")),
        retorno_afiliado_centavos_dia=_numero(ra), saturacao=_numero(calc.saturacao(n_criadores, vd)),
        vendas_periodo=_numero(calc.vendas_periodo(fotos, de, ate)),
        gmv_periodo_centavos=_numero(calc.gmv_periodo(fotos, de, ate)),
        crescimento=_numero(cresc), vendas_dia=_numero(vd),
        vendas_totais=_numero(calc.vendas_totais(fotos, ate)),
        gmv_total_centavos=_numero(calc.gmv_total(fotos, ate)),
        novo_em_alta=calc.novo_em_alta(p.primeira_vez_em.date(), hoje, vd, cresc, em_alta, subiu,
                                       est),
        alto_retorno_poucos_afiliados=alto, poucos_afiliados=poucos,
        rankings=posicoes, interesses=interesses)


def cartoes(db: Session, produtos: list[Produto], f: Filtro, hoje: date
            ) -> list[schemas.CartaoProdutoOut]:
    ids = [p.id for p in produtos]
    de_fotos = min(f.anterior.de, f.atual.ate - timedelta(days=JANELA_FOTOS_DIAS))
    fotos = _fotos_de(db, ids, de_fotos, f.atual.ate)
    posicoes = _posicoes_de(db, ids, f.atual.ate)
    interesses = _interesses_de(db, ids, f.perfil_id)
    imagens = _imagem_url_de(db, produtos)
    lojas, cats = _refs(db, produtos)
    comparaveis = {cid: comparaveis_da_categoria(db, cid, f.atual.ate)
                   for cid in {p.categoria_id for p in produtos}}
    return [cartao(p, fotos[p.id], f, hoje, lojas, cats, posicoes[p.id], interesses[p.id],
                   imagens[p.id], comparaveis.get(p.categoria_id)) for p in produtos]


def contexto(f: Filtro) -> schemas.ContextoMercado:
    return schemas.ContextoMercado(de=f.atual.de, ate=f.atual.ate, anterior_de=f.anterior.de,
                                   anterior_ate=f.anterior.ate, fuso=f.fuso, mercado=f.mercado,
                                   perfil_id=f.perfil_id, gerado_em=datetime.now(UTC),
                                   constantes=CONSTANTES_PUBLICAS)


def listar_produtos(db: Session, f: Filtro, hoje: date) -> schemas.ListaProdutosOut:
    base = base_produtos(db, f)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    chave = chave_de_ordem(f)
    ordem = chave.desc().nulls_last() if f.desc else chave.asc().nulls_last()
    produtos = db.scalars(base.order_by(ordem, Produto.id).offset(f.offset).limit(f.limite)).all()
    proximo = cursor_para(f.offset + f.limite) if f.offset + f.limite < total else None
    return schemas.ListaProdutosOut(itens=cartoes(db, list(produtos), f, hoje), proximo=proximo,
                                    total=total, contexto=contexto(f))


def produto_ou_404(db: Session, produto_id: uuid.UUID) -> Produto:
    p = db.get(Produto, produto_id)
    if p is None:
        raise ApiError(404, "produto_nao_encontrado", "Produto de mercado não encontrado")
    return p


def imagens_out(db: Session, ficha: Ficha | None) -> list[schemas.ImagemOut]:
    if ficha is None:
        return []
    rows = db.execute(select(ProdutoImagem.posicao, Imagem)
                      .join(Imagem, Imagem.id == ProdutoImagem.imagem_id)
                      .where(ProdutoImagem.ficha_id == ficha.id).order_by(ProdutoImagem.posicao)).all()
    out = []
    for pos, img in rows:
        link = midia.link("mercado_imagem", img.id, ttl=None)
        out.append(schemas.ImagemOut(id=img.id, sha256=img.sha256,
                                     url=imaging.preview_url(img.object_key),
                                     original=schemas.MercadoLinkOut(url=link.url, expires_at=None),
                                     width=img.width, height=img.height, bytes=img.bytes,
                                     content_type=img.content_type, posicao=pos))
    return out


def ficha_out(db: Session, ficha: Ficha, lojas: dict, cats: dict,
              anterior: Ficha | None = None) -> schemas.FichaOut:
    diff = None
    if anterior is not None:
        campos = [c for c in ("titulo", "descricao", "atributos", "variantes", "argumentos", "selos",
                              "categoria_id", "loja_id", "imagens_sha")
                  if getattr(ficha, c) != getattr(anterior, c)]
        diff = {"campos": campos}
    return schemas.FichaOut(
        id=ficha.id, hash_conteudo=ficha.hash_conteudo, titulo=ficha.titulo,
        descricao=ficha.descricao, atributos=ficha.atributos, variantes=ficha.variantes,
        argumentos=list(ficha.argumentos), selos=list(ficha.selos),
        categoria=categoria_ref(cats.get(ficha.categoria_id)), loja=loja_ref(lojas.get(ficha.loja_id)),
        imagens=imagens_out(db, ficha), esquema_versao=ficha.esquema_versao,
        coletado_em=ficha.coletado_em, created_at=ficha.created_at, diff=diff)


def detalhe_produto(db: Session, produto_id: uuid.UUID, f: Filtro, hoje: date
                    ) -> schemas.ProdutoMercadoOut:
    p = produto_ou_404(db, produto_id)
    base = cartoes(db, [p], f, hoje)[0]
    ficha = db.get(Ficha, p.ficha_atual_id) if p.ficha_atual_id else None
    n_fichas = db.scalar(select(func.count()).select_from(Ficha).where(Ficha.produto_id == p.id)) or 0
    lojas, cats = _refs(db, [p])
    if ficha is not None:
        lojas.update({l.id: l for l in db.scalars(select(Loja).where(Loja.id == ficha.loja_id))}
                     if ficha.loja_id else {})
        cats.update({c.id: c for c in db.scalars(select(Categoria).where(
            Categoria.id == ficha.categoria_id))} if ficha.categoria_id else {})
    perfis = db.scalars(select(Perfil).where(Perfil.archived_at.is_(None))
                        .order_by(Perfil.created_at)).all()
    vivos = {i.perfil_id: i.id for i in db.scalars(select(Interesse).where(
        Interesse.mercado_produto_id == p.id, Interesse.situacao.in_(VIVOS),
        Interesse.perfil_id.is_not(None)))}
    return schemas.ProdutoMercadoOut(
        **base.model_dump(), ficha=ficha_out(db, ficha, lojas, cats) if ficha else None,
        galeria=imagens_out(db, ficha), n_fichas=n_fichas,
        interesses_do_usuario=[schemas.InteresseDoUsuario(perfil_id=pf.id, perfil_nome=pf.name,
                                                          interesse_id=vivos.get(pf.id))
                               for pf in perfis],
        adotado_em=[schemas.AdotadoEm(perfil_id=pf, produto_id=pr)
                    for pf, pr in adotar_mod.adotados_em(db, p.id)],
        contexto=contexto(f))


def serie_produto(db: Session, produto_id: uuid.UUID, f: Filtro, fonte: Fonte | None
                  ) -> schemas.SerieOut:
    p = produto_ou_404(db, produto_id)
    de, ate = f.atual.de, f.atual.ate
    rows = db.scalars(select(FotoProduto).where(FotoProduto.produto_id == p.id,
                                                FotoProduto.data_local >= de - timedelta(days=15),
                                                FotoProduto.data_local <= ate)
                      .order_by(FotoProduto.data_local, FotoProduto.turno, FotoProduto.fonte)).all()
    todas = [calc.Foto(r.data_local, r.turno.value, r.fonte.value, r.vendidos, r.vendidos_min,
                       r.vendidos_max, r.vendidos_exato, r.preco_min_centavos, r.preco_max_centavos,
                       r.preco_original_centavos, r.comissao_bp, r.n_criadores, r.vendas_7d,
                       r.vendas_30d, r.disponivel) for r in rows]
    fotos_out = [schemas.FotoOut(
        data_local=r.data_local, turno=r.turno.value, fonte=r.fonte.value, vendidos=r.vendidos,
        vendidos_min=r.vendidos_min, vendidos_max=r.vendidos_max, vendidos_exato=r.vendidos_exato,
        preco_min_centavos=r.preco_min_centavos, preco_max_centavos=r.preco_max_centavos,
        preco_original_centavos=r.preco_original_centavos, moeda=r.moeda,
        nota=float(r.nota) if r.nota is not None else None, n_avaliacoes=r.n_avaliacoes,
        comissao_bp=r.comissao_bp, n_criadores=r.n_criadores, vendas7d=r.vendas_7d,
        vendas30d=r.vendas_30d, estoque_visivel=r.estoque_visivel, disponivel=r.disponivel,
        bruto_pendente=r.bruto_ref is None)
        for r in rows if r.data_local >= de and (fonte is None or r.fonte == fonte)]
    diaria = []
    dias = sorted({x.data_local for x in todas if de <= x.data_local <= ate})
    for d in dias:
        vt = calc.vendas_totais(todas, d)
        af = calc.ultima(todas, d, "affiliate")
        pr = calc.preco_de(todas, d)
        diaria.append(schemas.DiariaOut(
            data_local=d, vendidos=_numero(vt), vendas_dia=_numero(calc.vendas_dia(todas, d)),
            preco_min_centavos=pr.preco_min_centavos if pr else None,
            n_criadores=_numero(calc.Numero(af.n_criadores, True, ["fonte_affiliate"], False, 1)
                                if af and af.n_criadores is not None
                                else calc.Numero.nulo("sem_dado_afiliado")),
            comissao_bp=_numero(calc.Numero(af.comissao_bp, True, ["fonte_affiliate"], False, 1)
                                if af and af.comissao_bp is not None
                                else calc.Numero.nulo("sem_dado_afiliado"))))
    return schemas.SerieOut(
        produto_id=p.id, de=de, ate=ate, fotos=fotos_out, diaria=diaria,
        resumo=schemas.ResumoSerie(vendas_periodo=_numero(calc.vendas_periodo(todas, de, ate)),
                                   gmv_periodo_centavos=_numero(calc.gmv_periodo(todas, de, ate)),
                                   crescimento=_numero(calc.crescimento(todas, ate))))


def resumo(db: Session, f: Filtro, hoje: date, estado_coleta) -> schemas.ResumoOut:
    """Os cards do Cockpit (FR-051): mais vendidos, novos em alta, alto retorno e os totais, todos
    dos mesmos dados que a tabela e o CSV."""
    base = base_produtos(db, f)
    sub = base.subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    acompanhados = db.scalar(select(func.count(func.distinct(Interesse.mercado_produto_id)))
                             .where(Interesse.mercado_produto_id.in_(select(sub.c.id)),
                                    Interesse.situacao == InteresseSituacao.ativo)) or 0
    # Os candidatos: os 200 mais vendidos do período (os cards saem deles).
    f_cards = replace(f, ordenar="vendasPeriodo", desc=True, offset=0, limite=200)
    chave = chave_de_ordem(f_cards)
    produtos = list(db.scalars(base.order_by(chave.desc().nulls_last(), Produto.id)
                               .limit(200)).all())
    todos = cartoes(db, produtos, f, hoje)
    mais = sorted(todos, key=lambda c: c.vendas_periodo.valor or 0, reverse=True)
    novos = [c for c in todos if c.novo_em_alta]
    alto = [c for c in todos if c.alto_retorno_poucos_afiliados]
    alto.sort(key=lambda c: c.retorno_afiliado_centavos_dia.valor or 0, reverse=True)
    estados = {"coletando": 0, "amostra_pequena": 0, "ok": 0}
    for c in todos:
        estados[c.estado] += 1
    soma_v = sum(c.vendas_periodo.valor or 0 for c in todos)
    soma_g = sum(c.gmv_periodo_centavos.valor or 0 for c in todos)
    criterio = None
    cats = {p.categoria_id for p in produtos if p.categoria_id}
    if cats:
        comps = [comparaveis_da_categoria(db, cid, f.atual.ate) for cid in cats]
        por_cat = [c for c in comps if c is not None and c.por_categoria]
        criterio = {"porCategoria": bool(por_cat),
                    "p25Criadores": por_cat[0].p25_criadores if por_cat else None,
                    "p75Retorno": por_cat[0].p75_retorno if por_cat else None}
    n = k.CARDS_COCKPIT
    return schemas.ResumoOut(
        contexto=contexto(f),
        mais_vendidos=schemas.CardOut(itens=mais[:n], total=len(mais)),
        novos_em_alta=schemas.CardOut(itens=novos[:n], total=len(novos)),
        alto_retorno_poucos_afiliados=schemas.CardOut(itens=alto[:n], total=len(alto),
                                                      criterio=criterio),
        estado_coleta=estado_coleta,
        totais=schemas.TotaisOut(
            produtos=total, acompanhados=acompanhados, coletando=estados["coletando"],
            amostra_pequena=estados["amostra_pequena"], ok=estados["ok"],
            vendas_periodo=_numero(calc.Numero(soma_v, True, ["estimado"], False, len(todos))),
            gmv_periodo_centavos=_numero(calc.Numero(soma_g, True, ["estimado"], False,
                                                     len(todos)))))

