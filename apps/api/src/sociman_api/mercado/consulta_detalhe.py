"""Leituras do detalhe e das abas Rankings e Lojas (US5, FR-049): fichas versionadas, posições
nos rankings, vídeos top, avaliações (sem autor) e os cartões de loja. **Só SELECT**, como
`consulta.py` (guarda FR-042): nada aqui grava, e todo derivado sai marcado como estimado.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api import imaging, midia
from sociman_api.errors import ApiError
from sociman_api.mercado import calculo as calc
from sociman_api.mercado import constantes as k
from sociman_api.mercado import consulta, interesses, schemas
from sociman_api.mercado.filtros import Filtro, cursor_para
from sociman_api.mercado.fontes.base import BasesUrl
from sociman_api.mercado.models import (
    Avaliacao,
    Categoria,
    Ficha,
    FotoLoja,
    FotoRanking,
    Imagem,
    Interesse,
    InteresseSituacao,
    ItemRanking,
    Loja,
    PerfilConfig,
    Produto,
    RankingTipo,
    VideoProduto,
)

VIVOS = (InteresseSituacao.ativo, InteresseSituacao.pausado)
LOJAS_PRODUTOS_MAX = 200  # produtos por loja considerados nos indicadores (os mais recentes)


def _refs_de_fichas(db: Session, fichas: list[Ficha]) -> tuple[dict, dict]:
    lojas = {lj.id: lj for lj in db.scalars(select(Loja).where(
        Loja.id.in_({f.loja_id for f in fichas if f.loja_id})))} if fichas else {}
    cats = {c.id: c for c in db.scalars(select(Categoria).where(
        Categoria.id.in_({f.categoria_id for f in fichas if f.categoria_id})))} if fichas else {}
    return lojas, cats


def fichas_produto(db: Session, produto_id: uuid.UUID) -> schemas.FichasList:
    """As versões da ficha, da mais nova para a mais antiga, com o `diff` em relação à anterior."""
    p = consulta.produto_ou_404(db, produto_id)
    fichas = db.scalars(select(Ficha).where(Ficha.produto_id == p.id)
                        .order_by(Ficha.created_at.desc())).all()
    lojas, cats = _refs_de_fichas(db, fichas)
    return schemas.FichasList(itens=[
        consulta.ficha_out(db, f, lojas, cats, fichas[i + 1] if i + 1 < len(fichas) else None)
        for i, f in enumerate(fichas)])


def _cats(db: Session, ids: set[uuid.UUID | None]) -> dict:
    ids_ok = {i for i in ids if i}
    return {c.id: c for c in db.scalars(select(Categoria).where(Categoria.id.in_(ids_ok)))} \
        if ids_ok else {}


def rankings_produto(db: Session, produto_id: uuid.UUID, f: Filtro) -> schemas.RankingsProdutoOut:
    """As posições no período e, por ranking (categoria × tipo × janela), o resumo de FR-049."""
    p = consulta.produto_ou_404(db, produto_id)
    de, ate = f.atual.de, f.atual.ate
    rows = db.execute(select(ItemRanking, FotoRanking)
                      .join(FotoRanking, FotoRanking.id == ItemRanking.ranking_foto_id)
                      .where(ItemRanking.produto_id == p.id, FotoRanking.data_local <= ate,
                             FotoRanking.data_local >= de - timedelta(days=60))
                      .order_by(FotoRanking.data_local.desc(), FotoRanking.tipo,
                                FotoRanking.janela)).all()
    cats = _cats(db, {fo.categoria_id for _, fo in rows})
    itens = [schemas.PosicaoRankingItem(
        ranking_foto_id=fo.id, data_local=fo.data_local, fonte=fo.fonte.value,
        categoria=consulta.categoria_ref(cats.get(fo.categoria_id)), tipo=fo.tipo, janela=fo.janela,
        posicao=it.posicao, valor_exibido=it.valor_exibido,
        valor_num=float(it.valor_num) if it.valor_num is not None else None)
        for it, fo in rows if fo.data_local >= de]
    por: dict[tuple, dict[date, int]] = {}
    for it, fo in rows:
        por.setdefault((fo.categoria_id, fo.tipo, fo.janela), {})[fo.data_local] = it.posicao
    resumo = []
    for (cat, tipo, jan), posicoes in por.items():
        r = calc.resumo_ranking(posicoes, ate)
        resumo.append(schemas.ResumoRankingOut(
            categoria_id=cat, categoria=consulta.categoria_ref(cats.get(cat)), tipo=tipo, janela=jan,
            posicao_atual=r.posicao_atual, melhor_posicao=r.melhor_posicao,
            dias_no_topo=r.dias_no_topo, variacao7d=r.variacao_7d, entrou_em=r.entrou_em,
            saiu_em=r.saiu_em))
    return schemas.RankingsProdutoOut(itens=itens, resumo=resumo)


def videos_produto(db: Session, produto_id: uuid.UUID, f: Filtro,
                   todas_observacoes: bool = False) -> schemas.VideosList:
    """Só o @ público e contadores (FR-011). A última observação de cada vídeo no período, ou a
    série inteira com `todasObservacoes`. A URL é montada pelo servidor, sem parâmetros, a partir
    da base pública configurada pelo dono (sem base, vem nula)."""
    p = consulta.produto_ou_404(db, produto_id)
    de, ate = f.atual.de, f.atual.ate
    rows = db.scalars(select(VideoProduto).where(
        VideoProduto.produto_id == p.id, VideoProduto.data_local >= de,
        VideoProduto.data_local <= ate)
        .order_by(VideoProduto.data_local.desc(), VideoProduto.posicao.nulls_last(),
                  VideoProduto.views.desc().nulls_last())).all()
    if not todas_observacoes:
        vistos: set[str] = set()
        unicos = []
        for v in rows:
            if v.rede_video_id in vistos:
                continue
            vistos.add(v.rede_video_id)
            unicos.append(v)
        rows = unicos
    bases = BasesUrl.das_settings()
    pagina = rows[f.offset:f.offset + f.limite]
    proximo = cursor_para(f.offset + f.limite) if f.offset + f.limite < len(rows) else None
    return schemas.VideosList(itens=[schemas.VideoOut(
        rede_video_id=v.rede_video_id, autor_handle=v.autor_handle, views=v.views, likes=v.likes,
        comentarios=v.comentarios, compartilhamentos=v.compartilhamentos, legenda=v.legenda,
        publicado_em=v.publicado_em, data_local=v.data_local, posicao=v.posicao,
        url=(f"{bases.publica}/@{v.autor_handle}/video/{v.rede_video_id}"
             if bases.publica else None)) for v in pagina], proximo=proximo)


def _imagens_por_sha(db: Session, shas: set[str]) -> dict[str, schemas.ImagemOut]:
    if not shas:
        return {}
    out = {}
    for img in db.scalars(select(Imagem).where(Imagem.sha256.in_(shas))):
        link = midia.link("mercado_imagem", img.id, ttl=None)
        out[img.sha256] = schemas.ImagemOut(
            id=img.id, sha256=img.sha256, url=imaging.preview_url(img.object_key),
            original=schemas.MercadoLinkOut(url=link.url, expires_at=None), width=img.width,
            height=img.height, bytes=img.bytes, content_type=img.content_type, posicao=0)
    return out


def avaliacoes_produto(db: Session, produto_id: uuid.UUID, f: Filtro, nota: int | None = None,
                       com_fotos: bool | None = None) -> schemas.AvaliacoesList:
    """Texto, nota, data, variante e as fotos de clientes; **nunca** o autor (FR-010)."""
    p = consulta.produto_ou_404(db, produto_id)
    base = select(Avaliacao).where(Avaliacao.produto_id == p.id)
    stmt = base
    if nota is not None:
        stmt = stmt.where(Avaliacao.nota == nota)
    if com_fotos is True:
        stmt = stmt.where(func.cardinality(Avaliacao.imagens_sha) > 0)
    elif com_fotos is False:
        stmt = stmt.where(func.cardinality(Avaliacao.imagens_sha) == 0)
    total_filtrado = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Avaliacao.data_avaliacao.desc().nulls_last(),
                                    Avaliacao.coletado_em.desc(), Avaliacao.id)
                      .offset(f.offset).limit(f.limite)).all()
    shas = {s for a in rows for s in a.imagens_sha}
    imagens = _imagens_por_sha(db, shas)
    por_nota = {str(n): 0 for n in range(1, 6)}
    for n, c in db.execute(select(Avaliacao.nota, func.count()).where(Avaliacao.produto_id == p.id)
                           .group_by(Avaliacao.nota)).all():
        if n is not None:
            por_nota[str(n)] = c
    total = db.scalar(select(func.count()).select_from(Avaliacao)
                      .where(Avaliacao.produto_id == p.id)) or 0
    com_texto = db.scalar(select(func.count()).select_from(Avaliacao).where(
        Avaliacao.produto_id == p.id, Avaliacao.texto.is_not(None), Avaliacao.texto != "")) or 0
    n_fotos = db.scalar(select(func.count()).select_from(Avaliacao).where(
        Avaliacao.produto_id == p.id, func.cardinality(Avaliacao.imagens_sha) > 0)) or 0
    proximo = cursor_para(f.offset + f.limite) if f.offset + f.limite < total_filtrado else None
    return schemas.AvaliacoesList(
        itens=[schemas.AvaliacaoOut(
            id=a.id, texto=a.texto, nota=a.nota, data_avaliacao=a.data_avaliacao,
            variante=a.variante, imagens=[imagens[s] for s in a.imagens_sha if s in imagens],
            curtidas=a.curtidas, coletado_em=a.coletado_em) for a in rows],
        proximo=proximo,
        resumo=schemas.AvaliacoesResumo(total=total, por_nota=por_nota, com_texto=com_texto,
                                        com_fotos=n_fotos))


# ---- rankings (aba) ----

def _categorias_dos_perfis(db: Session, perfil_id: uuid.UUID | None) -> set[uuid.UUID] | None:
    """As categorias do perfil (ou a união dos perfis ativos), com descendentes; None = sem
    configuração (não restringe)."""
    if perfil_id is not None:
        cfg = db.get(PerfilConfig, perfil_id)
        ids = list(cfg.categoria_ids) if cfg else []
    else:
        ids = [c for cfg in db.scalars(select(PerfilConfig)) for c in cfg.categoria_ids]
    if not ids:
        return None
    return interesses.categorias_com_descendentes(db, list(dict.fromkeys(ids)))


def listar_rankings(db: Session, f: Filtro, hoje: date, categoria_id: uuid.UUID | None = None,
                    tipo: RankingTipo | None = None, janela: str | None = None,
                    fonte: str | None = None) -> schemas.RankingsListarOut:
    """As fotos de ranking do período (das categorias dos perfis, sem `categoriaId`) e, com a
    categoria, a foto atual com a variação de posição contra a anterior."""
    de, ate = f.atual.de, f.atual.ate
    stmt = select(FotoRanking).where(FotoRanking.mercado == f.mercado,
                                     FotoRanking.data_local >= de - timedelta(days=30),
                                     FotoRanking.data_local <= ate)
    if categoria_id is not None:
        stmt = stmt.where(FotoRanking.categoria_id == categoria_id)
    else:
        cats_perfis = _categorias_dos_perfis(db, f.perfil_id)
        if cats_perfis:
            stmt = stmt.where(FotoRanking.categoria_id.in_(cats_perfis))
    if tipo is not None:
        stmt = stmt.where(FotoRanking.tipo == tipo)
    if janela is not None:
        stmt = stmt.where(FotoRanking.janela == janela)
    if fonte is not None:
        stmt = stmt.where(FotoRanking.fonte == fonte)
    fotos = db.scalars(stmt.order_by(FotoRanking.data_local.desc(), FotoRanking.categoria_id,
                                     FotoRanking.tipo, FotoRanking.janela).limit(1000)).all()
    cats = _cats(db, {fo.categoria_id for fo in fotos})
    fotos_out = [schemas.FotoRankingOut(
        id=fo.id, data_local=fo.data_local, fonte=fo.fonte.value,
        categoria=consulta.categoria_ref(cats.get(fo.categoria_id)), tipo=fo.tipo, janela=fo.janela,
        n_itens=fo.n_itens) for fo in fotos if fo.data_local >= de]
    atual = None
    if categoria_id is not None:
        t = tipo or RankingTipo.mais_vendidos
        j = janela or "7d"
        serie = [fo for fo in fotos if fo.tipo == t and fo.janela == j]
        if serie:
            foto_atual, foto_ant = serie[0], (serie[1] if len(serie) > 1 else None)
            itens = db.scalars(select(ItemRanking).where(ItemRanking.ranking_foto_id == foto_atual.id)
                               .order_by(ItemRanking.posicao)).all()
            ant = {it.produto_id: it.posicao for it in db.scalars(select(ItemRanking).where(
                ItemRanking.ranking_foto_id == foto_ant.id))} if foto_ant else {}
            ids = list(dict.fromkeys([it.produto_id for it in itens] + list(ant)))
            produtos = {p.id: p for p in db.scalars(select(Produto).where(Produto.id.in_(ids)))}
            cards = {c.id: c for c in consulta.cartoes(db, [produtos[i] for i in ids if i in produtos],
                                                        f, hoje)}
            itens_out = []
            for it in itens:
                if foto_ant is None:
                    var, delta = "igual", None
                else:
                    var, delta = calc.variacao_posicao(it.posicao, ant.get(it.produto_id))
                    if var in ("entrou", "saiu"):
                        var = "novo"
                if it.produto_id in cards:
                    itens_out.append(schemas.RankingItemOut(
                        posicao=it.posicao, produto=cards[it.produto_id],
                        valor_exibido=it.valor_exibido,
                        valor_num=float(it.valor_num) if it.valor_num is not None else None,
                        variacao=var, delta=delta))
            presentes = {it.produto_id for it in itens}
            sairam = [schemas.RankingSaiuOut(produto=cards[pid], ultima_posicao=pos)
                      for pid, pos in sorted(ant.items(), key=lambda x: x[1])
                      if pid not in presentes and pid in cards]
            atual = schemas.RankingAtualOut(
                ranking_foto_id=foto_atual.id, data_local=foto_atual.data_local,
                anterior_data_local=foto_ant.data_local if foto_ant else None,
                itens=itens_out, sairam=sairam)
    return schemas.RankingsListarOut(fotos=fotos_out, atual=atual, contexto=consulta.contexto(f))


# ---- lojas ----

def _observado(valor, n_fotos: int = 1) -> schemas.Numero:
    if valor is None:
        return schemas.Numero(valor=None, estimado=False, motivos=["coletando"], n_fotos=0)
    return schemas.Numero(valor=float(valor), estimado=False, motivos=["fonte_pagina_publica"],
                          n_fotos=n_fotos)


def _seguidores_por_loja(db: Session) -> dict[uuid.UUID, list[uuid.UUID]]:
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for cfg in db.scalars(select(PerfilConfig)):
        for lid in cfg.lojas_seguidas:
            out.setdefault(lid, []).append(cfg.perfil_id)
    return out


def _cartao_loja(db: Session, loja: Loja, f: Filtro, hoje: date,
                 seguidores: dict[uuid.UUID, list[uuid.UUID]]
                 ) -> tuple[schemas.CartaoLojaOut, list[schemas.CartaoProdutoOut], list[Produto]]:
    ate = f.atual.ate
    foto = db.scalar(select(FotoLoja).where(FotoLoja.loja_id == loja.id, FotoLoja.data_local <= ate)
                     .order_by(FotoLoja.data_local.desc(), FotoLoja.id.desc()))
    produtos = db.scalars(select(Produto).where(Produto.loja_id == loja.id)
                          .order_by(Produto.primeira_vez_em.desc())
                          .limit(LOJAS_PRODUTOS_MAX)).all()
    n_no_lago = db.scalar(select(func.count()).select_from(Produto)
                          .where(Produto.loja_id == loja.id)) or 0
    cards = consulta.cartoes(db, list(produtos), f, hoje) if produtos else []
    acompanhados = db.scalar(select(func.count(func.distinct(Interesse.mercado_produto_id)))
                             .where(Interesse.mercado_produto_id.in_([p.id for p in produtos]),
                                    Interesse.situacao.in_(VIVOS))) or 0 if produtos else 0
    gmvs = [calc.Numero(c.gmv_periodo_centavos.valor, True, list(c.gmv_periodo_centavos.motivos),
                        c.gmv_periodo_centavos.amostra_pequena, c.gmv_periodo_centavos.n_fotos)
            for c in cards]
    comissoes = [int(c.comissao_bp.valor) for c in cards if c.comissao_bp.valor is not None]
    ind = calc.indicadores_loja(gmvs, [p.primeira_vez_em.date() for p in produtos], hoje, comissoes)
    vt = None
    if foto is not None and foto.vendidos_total is not None:
        vt = schemas.Numero(valor=float(foto.vendidos_total), estimado=not bool(foto.vendidos_total_exato),
                            motivos=["fonte_pagina_publica"] + ([] if foto.vendidos_total_exato else ["incerteza"]),
                            n_fotos=1, min=foto.vendidos_total_min, max=foto.vendidos_total_max)
    cartao = schemas.CartaoLojaOut(
        id=loja.id, rede=loja.rede, mercado=loja.mercado, rede_loja_id=loja.rede_loja_id,
        nome=loja.nome, oficial=loja.oficial, url=loja.url, primeira_vez_em=loja.primeira_vez_em,
        ultimo_visto_em=loja.ultimo_visto_em, ultima_foto_em=loja.ultima_foto_em,
        nota=_observado(foto.nota if foto else None),
        seguidores=_observado(foto.seguidores if foto else None),
        envio_no_prazo_pct=_observado(foto.envio_no_prazo_pct if foto else None),
        n_produtos=_observado(foto.n_produtos if foto else None),
        vendidos_total=vt or _observado(None),
        n_produtos_no_lago=n_no_lago, n_produtos_acompanhados=acompanhados,
        gmv_estimado_centavos=consulta._numero(ind.gmv_estimado_centavos),
        concentracao_top1=consulta._numero(ind.concentracao_top1),
        lancamentos30d=ind.lancamentos_30d,
        comissao_media_bp=consulta._numero(ind.comissao_media_bp),
        seguida_por=list(seguidores.get(loja.id, [])))
    return cartao, cards, list(produtos)


ORDENS_LOJA = ("gmv", "nome", "seguidores", "nProdutos", "lancamentos", "comissao")


def listar_lojas(db: Session, f: Filtro, hoje: date, q: str | None = None,
                 oficial: bool | None = None, seguida_por: uuid.UUID | None = None,
                 ordenar: str = "gmv") -> schemas.LojasList:
    stmt = select(Loja).where(Loja.mercado == f.mercado)
    if q:
        stmt = stmt.where(Loja.nome.ilike(f"%{q}%"))
    if oficial is not None:
        stmt = stmt.where(Loja.oficial.is_(oficial))
    seguidores = _seguidores_por_loja(db)
    if seguida_por is not None:
        ids = [lid for lid, ps in seguidores.items() if seguida_por in ps]
        stmt = stmt.where(Loja.id.in_(ids)) if ids else stmt.where(False)
    if ordenar not in ORDENS_LOJA:
        raise ApiError(400, "entrada_invalida", "ordenar: valor fora da lista",
                       details={"field": "ordenar", "aceitos": list(ORDENS_LOJA)})
    lojas = db.scalars(stmt.order_by(Loja.nome).limit(500)).all()
    cartoes = [_cartao_loja(db, lj, f, hoje, seguidores)[0] for lj in lojas]

    def chave(c: schemas.CartaoLojaOut):
        if ordenar == "nome":
            return (c.nome.lower(),)
        if ordenar == "seguidores":
            return (-(c.seguidores.valor or 0),)
        if ordenar == "nProdutos":
            return (-c.n_produtos_no_lago,)
        if ordenar == "lancamentos":
            return (-c.lancamentos30d,)
        if ordenar == "comissao":
            return (-(c.comissao_media_bp.valor or 0),)
        return (-(c.gmv_estimado_centavos.valor or 0),)

    cartoes.sort(key=chave)
    total = len(cartoes)
    pagina = cartoes[f.offset:f.offset + f.limite]
    proximo = cursor_para(f.offset + f.limite) if f.offset + f.limite < total else None
    return schemas.LojasList(itens=pagina, total=total, proximo=proximo, contexto=consulta.contexto(f))


def detalhe_loja(db: Session, loja_id: uuid.UUID, f: Filtro, hoje: date) -> schemas.LojaDetalheOut:
    loja = db.get(Loja, loja_id)
    if loja is None:
        raise ApiError(404, "loja_nao_encontrada", "Loja não encontrada")
    cartao, cards, produtos = _cartao_loja(db, loja, f, hoje, _seguidores_por_loja(db))
    fotos = db.scalars(select(FotoLoja).where(FotoLoja.loja_id == loja.id,
                                              FotoLoja.data_local <= f.atual.ate)
                       .order_by(FotoLoja.data_local.desc()).limit(400)).all()
    novos_ids = {p.id for p in produtos if (hoje - p.primeira_vez_em.date()).days <= k.NOVO_DIAS}
    ordenados = sorted(cards, key=lambda c: -(c.gmv_periodo_centavos.valor or 0))
    return schemas.LojaDetalheOut(
        **cartao.model_dump(by_alias=False),
        fotos=[schemas.FotoLojaOut(
            data_local=fo.data_local, fonte=fo.fonte.value,
            nota=float(fo.nota) if fo.nota is not None else None, seguidores=fo.seguidores,
            envio_no_prazo_pct=float(fo.envio_no_prazo_pct) if fo.envio_no_prazo_pct is not None else None,
            tempo_resposta_pct=float(fo.tempo_resposta_pct) if fo.tempo_resposta_pct is not None else None,
            n_produtos=fo.n_produtos, vendidos_total=fo.vendidos_total,
            vendidos_total_min=fo.vendidos_total_min, vendidos_total_max=fo.vendidos_total_max,
            vendidos_total_exato=fo.vendidos_total_exato) for fo in fotos],
        produtos=ordenados, novos30d=[c for c in ordenados if c.id in novos_ids],
        contexto=consulta.contexto(f))
