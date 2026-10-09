"""Parsers do adaptador `tiktok_shop/1`: JSON sintético por tipo → payload do contrato; faixas."""

from sociman_coletor import modelos
from sociman_coletor.redes.base import Interceptada
from sociman_coletor.redes.tiktok_shop import (
    ESQUEMA,
    TIPOS,
    AdaptadorTikTokShop,
    bp,
    centavos,
    data_iso,
    definir,
    faixa,
)

from .fakes import (
    HOST_REDE,
    json_affiliate,
    json_avaliacoes,
    json_categorias,
    json_loja,
    json_produto,
    json_ranking,
    json_videos,
    json_vitrine,
    rede_teste,
)


def _tarefa(
    tipo: str, url: str, fonte: str = "pagina_publica", chave: str = "x", extra: dict | None = None
) -> modelos.Tarefa:
    return modelos.Tarefa(
        tarefa_id="t1", tipo=tipo, chave=chave, url=url, fonte=fonte, extra=extra or {}
    )


def _inter(url: str, j) -> Interceptada:
    return Interceptada(url, 200, j)


def test_faixas():
    assert faixa("1,2 mil") == {"valor": 1200, "min": 1150, "max": 1249, "exato": False}
    assert faixa("10 mil+") == {"valor": 10000, "min": 10000, "max": None, "exato": False}
    assert faixa("320") == {"valor": 320, "min": 320, "max": 320, "exato": True}
    assert faixa(120) == {"valor": 120, "min": 120, "max": 120, "exato": True}
    assert faixa("12,3 mil vendidos")["valor"] == 12300
    assert faixa("230 mil") == {"valor": 230000, "min": 229500, "max": 230499, "exato": False}
    assert faixa("1.5k")["valor"] == 15000  # em pt-BR o ponto separa milhar
    assert faixa("abc") is None and faixa(None) is None


def test_dinheiro_comissao_e_datas():
    assert centavos("49.90") == 4990 and centavos("R$ 49,90") == 4990 and centavos(49.9) == 4990
    assert centavos("R$ 1.299,00") == 129900 and centavos(None) is None and centavos(-1) is None
    assert centavos({"amount": "5.00"}) == 500
    assert bp("12%") == 1200 and bp(12) == 1200 and bp(0.12) == 1200 and bp(1200) == 1200
    assert bp(None) is None
    assert data_iso(1789862400) == "2026-09-20"
    assert data_iso(1789862400000) == "2026-09-20"
    assert data_iso("2026-09-20T10:00:00-03:00") == "2026-09-20"
    assert data_iso("x") is None


def test_definir_caminhos():
    campos = {"ficha": {"imagensSha": [], "variantes": [{"imagemSha": None}]}, "itens": [{}]}
    definir(campos, "ficha.imagensSha", "a")
    definir(campos, "ficha.imagensSha", "b")
    definir(campos, "ficha.variantes.0.imagemSha", "c")
    definir(campos, "itens.0.imagemSha", "d")
    assert campos["ficha"]["imagensSha"] == ["a", "b"]
    assert campos["ficha"]["variantes"][0]["imagemSha"] == "c"
    assert campos["itens"][0]["imagemSha"] == "d"


def test_produto_ambas_fontes():
    rede = rede_teste()
    url = f"{HOST_REDE}/product/7291001?src=x"
    r = rede.coletar(
        None,
        _tarefa("produto", url, "ambas"),
        [
            _inter(f"{HOST_REDE}/api-sintetica/product/7291001", json_produto()),
            _inter(f"{HOST_REDE}/api-sintetica/affiliate/7291001", json_affiliate()),
        ],
    )
    assert r.erro_codigo is None and r.fonte == "ambas"
    c = r.campos
    assert c["redeProdutoId"] == "7291001"
    assert c["urlCanonica"] == f"{HOST_REDE}/product/7291001"
    f = c["ficha"]
    assert f["titulo"].startswith("Shorts") and f["descricao"] == "Tecido fresco."
    assert f["atributos"] == [{"nome": "Material", "valor": "Linho"}]
    v = f["variantes"][0]
    assert v == {
        "redeVarianteId": "17001",
        "nome": "Bege / M",
        "precoCentavos": 4990,
        "precoOriginalCentavos": 7990,
        "estoqueVisivel": 12,
        "imagemSha": None,
    }
    assert f["argumentos"] == ["Frete grátis"] and f["selos"] == ["Mais vendido", "Cupom R$ 5"]
    assert f["categoria"]["redeCategoriaId"] == "cat789"
    assert [n["nome"] for n in f["categoria"]["caminho"]] == ["Moda", "Feminino", "Shorts"]
    assert f["loja"] == {
        "redeLojaId": "loja123",
        "nome": "Loja X",
        "oficial": True,
        "url": f"{HOST_REDE}/shop/loja123",
    }
    assert f["lancadoEm"] == "2026-09-20" and f["imagensSha"] == []
    p = c["paginaPublica"]
    assert p["vendidos"] == {"valor": 1200, "min": 1150, "max": 1249, "exato": False}
    assert (p["precoMinCentavos"], p["precoMaxCentavos"], p["precoOriginalCentavos"]) == (
        4990,
        5990,
        7990,
    )
    assert p["moeda"] == "BRL" and p["nota"] == 4.8 and p["nAvaliacoes"] == 311
    assert p["estoqueVisivel"] == 230 and p["disponivel"] is True
    assert p["campos"] == {"cupons": ["R$ 5"], "freteGratis": True}
    a = c["affiliate"]
    assert a["comissaoBp"] == 1200 and a["nCriadores"] == 37
    assert a["vendas7d"] == 410 and a["vendas30d"] == 1620
    assert a["precoMinCentavos"] == 4990 and a["precoMaxCentavos"] == 5990
    assert a["campos"] == {
        "planoAberto": True,
        "amostraGratis": True,
        "comissaoDirecionadaBp": None,
    }
    # imagens a baixar: 2 principais + 1 do SKU, com destino
    destinos = sorted(i.destino for i in r.imagens)
    assert destinos == ["ficha.imagensSha", "ficha.imagensSha", "ficha.variantes.0.imagemSha"]
    # bruto guardado: URLs sem query, esquema
    assert r.bruto["esquema"] == ESQUEMA
    assert all("?" not in i["url"] for i in r.bruto["interceptadas"])


def test_produto_sem_interceptacao_nem_dom_e_erros():
    rede = rede_teste()
    url = f"{HOST_REDE}/product/7291001"
    r = rede.coletar(None, _tarefa("produto", url), [])
    assert r.erro_codigo == "interceptacao_vazia" and not r.tem_campos
    r = rede.coletar(None, _tarefa("produto", url), [_inter("u", {"data": {"foo": 1}})])
    assert r.erro_codigo == "pagina_sem_campos"
    r = rede.coletar(None, _tarefa("busca_assunto", url), [])
    assert r.erro_codigo == "tipo_desconhecido"
    r = rede.coletar(None, _tarefa("video", url), [])
    assert r.erro_codigo == "tipo_desconhecido"


def test_ranking():
    rede = rede_teste()
    r = rede.coletar(
        None,
        _tarefa(
            "ranking",
            f"{HOST_REDE}/rank/cat45",
            "affiliate",
            "ranking:cat45:mais_vendidos:7d",
            {"rankingTipo": "mais_vendidos", "janela": "7d", "categoriaRedeId": "cat45"},
        ),
        [_inter("u", json_ranking(3))],
    )
    c = r.campos
    assert c["rankingTipo"] == "mais_vendidos" and c["janela"] == "7d"
    assert c["categoria"]["redeCategoriaId"] == "cat45"
    assert len(c["itens"]) == 3
    i0 = c["itens"][0]
    assert i0["posicao"] == 1 and i0["redeProdutoId"] == "7291000"
    assert i0["urlCanonica"] == f"{HOST_REDE}/product/7291000"
    assert i0["valorExibido"] == "12,3 mil" and i0["valorNum"] == 12300
    assert i0["campos"] == {"precoMinCentavos": 4990, "comissaoBp": 1200, "nCriadores": 10}
    assert i0["loja"]["redeLojaId"] == "loja123" and i0["loja"]["oficial"] is False
    assert [i.destino for i in r.imagens] == [
        "itens.0.imagemSha",
        "itens.1.imagemSha",
        "itens.2.imagemSha",
    ]


def test_ranking_para_no_top_30():
    rede = rede_teste()
    r = rede.coletar(
        None,
        _tarefa("ranking", f"{HOST_REDE}/rank/c", "affiliate"),
        [_inter("u", json_ranking(45))],
    )
    assert len(r.campos["itens"]) == 30


def test_categorias():
    rede = rede_teste()
    r = rede.coletar(
        None,
        _tarefa("categorias", f"{HOST_REDE}/cats", "affiliate", "categorias"),
        [_inter("u", json_categorias())],
    )
    cats = r.campos["categorias"]
    assert {"redeCategoriaId": "cat1", "nome": "Moda", "nivel": 1, "paiRedeId": None} in cats
    assert {"redeCategoriaId": "cat45", "nome": "Feminino", "nivel": 2, "paiRedeId": "cat1"} in cats
    assert {"redeCategoriaId": "cat789", "nome": "Shorts", "nivel": 3, "paiRedeId": "cat45"} in cats
    assert {"redeCategoriaId": "cat2", "nome": "Casa", "nivel": 1, "paiRedeId": None} in cats


def test_vitrine():
    rede = rede_teste()
    r = rede.coletar(
        None,
        _tarefa("vitrine", f"{HOST_REDE}/vitrine", "affiliate", "vitrine"),
        [_inter("u", json_vitrine())],
    )
    i = r.campos["itens"][0]
    assert i["redeProdutoId"] == "7291001" and i["adicionadoEm"] == "2026-09-30"
    assert i["campos"] == {"comissaoBp": 1200}
    assert r.imagens[0].destino == "itens.0.imagemSha"


def test_loja():
    rede = rede_teste()
    r = rede.coletar(
        None,
        _tarefa("loja", f"{HOST_REDE}/shop/loja123", "pagina_publica", "loja:loja123"),
        [_inter("u", json_loja())],
    )
    c = r.campos
    assert c["redeLojaId"] == "loja123" and c["nome"] == "Loja X" and c["oficial"] is True
    assert c["url"] == f"{HOST_REDE}/shop/loja123"
    foto = c["foto"]
    assert foto["nota"] == 4.7 and foto["seguidores"] == 15800
    assert foto["envioNoPrazoPct"] == 97.5 and foto["tempoRespostaPct"] == 92.0
    assert foto["nProdutos"] == 84
    assert foto["vendidosTotal"] == {"valor": 230000, "min": 229500, "max": 230499, "exato": False}
    p = c["produtos"][0]
    assert p["redeProdutoId"] == "7300001" and p["precoMinCentavos"] == 3990
    assert p["vendidos"] == {"valor": 120, "min": 120, "max": 120, "exato": True}
    assert p["novo"] is True
    assert r.imagens[0].destino == "produtos.0.imagemSha"


def test_avaliacoes_so_autor_ref_sai():
    rede = rede_teste()
    r = rede.coletar(
        None,
        _tarefa(
            "avaliacoes",
            f"{HOST_REDE}/product/7291001/reviews",
            "pagina_publica",
            "avaliacoes:7291001:1",
            {"paginas": 2},
        ),
        [_inter("u", json_avaliacoes())],
    )
    c = r.campos
    assert c["redeProdutoId"] == "7291001" and c["pagina"] == 1 and c["totalPaginas"] == 14
    a = c["itens"][0]
    assert a == {
        "redeAvaliacaoId": "av1",
        "autorRef": "6812001",
        "texto": "Tecido ótimo, veio no prazo.",
        "nota": 5,
        "dataAvaliacao": "2026-10-02",
        "variante": "Bege / M",
        "imagensSha": [],
        "curtidas": 3,
        "campos": {},
    }
    assert "nickname" not in str(c) and "Fulana" not in str(c)
    assert r.imagens[0].origem == "avaliacao" and r.imagens[0].destino == "itens.0.imagensSha"


def test_produto_videos_so_handle_sai():
    rede = rede_teste()
    r = rede.coletar(
        None,
        _tarefa(
            "produto_videos",
            f"{HOST_REDE}/product/7291001/videos",
            "affiliate",
            "produto_videos:7291001",
        ),
        [_inter("u", json_videos())],
    )
    c = r.campos
    assert c["redeProdutoId"] == "7291001"
    v = c["itens"][0]
    assert v["posicao"] == 1 and v["redeVideoId"] == "7320001"
    assert v["autorHandle"] == "fulana.achados"
    assert (v["views"], v["likes"], v["comentarios"], v["compartilhamentos"]) == (
        1250000,
        84000,
        1200,
        3100,
    )
    assert v["legenda"] == "Olha esse shorts"
    assert v["publicadoEm"].startswith("2026-09-28")
    assert v["campos"] == {"duracaoS": 34, "produtoMarcado": True}
    assert "Fulana" not in str(c) and "nickname" not in str(c)


def test_reprocessar_a_partir_do_bruto_guardado():
    rede = rede_teste()
    url = f"{HOST_REDE}/product/7291001"
    r = rede.coletar(
        None,
        _tarefa("produto", url, "ambas"),
        [
            _inter(f"{HOST_REDE}/api-sintetica/product/7291001", json_produto()),
            _inter(f"{HOST_REDE}/api-sintetica/affiliate/7291001", json_affiliate()),
        ],
    )
    novo = rede.reprocessar("produto", r.bruto, "ambas")
    assert novo.tem_campos and novo.campos["affiliate"]["comissaoBp"] == 1200
    assert novo.campos["ficha"]["titulo"] == r.campos["ficha"]["titulo"]
    assert (
        rede.reprocessar("produto", {"interceptadas": []}, None).erro_codigo == "pagina_sem_campos"
    )


def test_urls_e_hosts():
    rede = AdaptadorTikTokShop()
    assert rede.url_canonica("https://h/product/1/?a=1#x") == "https://h/product/1"
    assert rede.url_pagina("https://h/p?a=1&page=1", 3) == "https://h/p?a=1&page=3"
    assert rede.e_derivada("https://h/p/reviews?page=2", "https://h/p")
    assert not rede.e_derivada("https://outro/p", "https://h/p")
    assert rede.host_de_imagem("https://p16.tiktokcdn.com/x.png")
    assert not rede.host_de_imagem("https://evil.test/x.png")
    assert rede.produto_id_da_url("https://h/product/7291001?x") == "7291001"
    assert rede.produto_id_da_url("https://h/product/12") is None
    assert rede.INTERCEPTAR == () and not rede.intercepta("https://h/api/x")
    assert rede.esquema == "tiktok_shop/1" and rede.TIPOS == TIPOS
