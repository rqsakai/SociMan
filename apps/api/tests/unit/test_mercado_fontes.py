"""T015 (FR-028): o adaptador `tiktok_shop/1` valida cada tipo, aponta o campo que faltou,
converte faixas ("1,2 mil") e preços por variante, e extrai o produto de um link."""

import pytest

from sociman_api.mercado.fontes import registro
from sociman_api.mercado.fontes.base import CampoInvalido
from sociman_api.mercado.fontes.tiktok_shop import ProdutoIn, parse_faixa
from sociman_api.perfis.models import Platform

FONTE = registro.fonte_para("tiktok")


def _produto(**extra) -> dict:
    base = {"redeProdutoId": "7291000000000000001",
            "urlCanonica": "https://exemplo.test/shop/product/7291000000000000001",
            "ficha": {"titulo": "Shorts de linho", "imagensSha": []},
            "paginaPublica": {"vendidos": {"valor": 320, "exato": True},
                              "precoMinCentavos": 4990, "moeda": "BRL"}}
    base.update(extra)
    return base


def test_registro_so_tiktok_e_esquema():
    assert FONTE is not None and FONTE.rede == Platform.tiktok
    assert FONTE.esquema_versao == "tiktok_shop/1"
    assert registro.fonte_para("youtube") is None and registro.fonte_para("x9") is None
    assert registro.esquemas() == {"tiktok_shop/1"}


@pytest.mark.parametrize("tipo, chave, ok", [
    ("produto", "produto:7291", True), ("produto", "produto:", False),
    ("ranking", "ranking:cat45:mais_vendidos:7d", True), ("ranking", "ranking:cat45:x:7d", False),
    ("categorias", "categorias", True), ("vitrine", "vitrine", True),
    ("loja", "loja:loja123", True), ("avaliacoes", "avaliacoes:7291:2", True),
    ("avaliacoes", "avaliacoes:7291", False), ("produto_videos", "produto_videos:7291", True),
    ("busca_assunto", "busca_assunto:x", False),
])
def test_validar_chave(tipo, chave, ok):
    assert FONTE.validar_chave(tipo, chave) is ok


def test_produto_normaliza_e_aponta_campo_faltando():
    dados = FONTE.normalizar("produto", _produto())
    assert isinstance(dados, ProdutoIn) and dados.ficha.titulo == "Shorts de linho"
    assert dados.pagina_publica.vendidos.valor == 320
    with pytest.raises(CampoInvalido) as exc:
        FONTE.normalizar("produto", _produto(ficha={"descricao": "sem título"}))
    assert exc.value.motivo == "campos_invalidos" and exc.value.campo == "ficha.titulo"
    with pytest.raises(CampoInvalido) as exc:
        FONTE.normalizar("produto", {"urlCanonica": "https://x.test/p/1"})
    assert exc.value.campo == "redeProdutoId"


def test_faixa_1_2_mil_vira_min_max_inexato():
    f = parse_faixa("1,2 mil")
    assert (f.valor, f.min, f.max, f.exato) == (1200, 1150, 1249, False)
    f = parse_faixa("10 mil+")
    assert (f.valor, f.min, f.max, f.exato) == (10000, 10000, None, False)
    f = parse_faixa("320")
    assert (f.valor, f.min, f.max, f.exato) == (320, 320, 320, True)
    f = parse_faixa("12,3 mil")
    assert (f.valor, f.min, f.max, f.exato) == (12300, 12250, 12349, False)
    with pytest.raises(CampoInvalido):
        parse_faixa("muitos")
    # Como texto dentro do payload, a faixa também é convertida.
    dados = FONTE.normalizar("produto", _produto(paginaPublica={"vendidos": "1,2 mil",
                                                                 "moeda": "BRL"}))
    assert dados.pagina_publica.vendidos.exato is False
    assert dados.pagina_publica.vendidos.min == 1150


def test_preco_por_variante_min_max():
    dados = FONTE.normalizar("produto", _produto(paginaPublica={
        "precoMinCentavos": 4990, "precoMaxCentavos": 5990, "moeda": "BRL"}))
    assert (dados.pagina_publica.preco_min_centavos, dados.pagina_publica.preco_max_centavos) \
        == (4990, 5990)
    with pytest.raises(CampoInvalido) as exc:
        FONTE.normalizar("produto", _produto(paginaPublica={"precoMinCentavos": -1, "moeda": "BRL"}))
    assert exc.value.campo == "paginaPublica.precoMinCentavos"


def test_ranking_categorias_vitrine_loja_avaliacoes_videos():
    r = FONTE.normalizar("ranking", {"rankingTipo": "em_alta", "janela": "7d", "itens": [
        {"posicao": 1, "redeProdutoId": "1", "urlCanonica": "https://x.test/product/1"}]})
    assert r.itens[0].posicao == 1
    with pytest.raises(CampoInvalido) as exc:
        FONTE.normalizar("ranking", {"rankingTipo": "x", "janela": "7d", "itens": []})
    assert exc.value.campo == "rankingTipo"
    c = FONTE.normalizar("categorias", {"categorias": [
        {"redeCategoriaId": "c1", "nome": "Moda", "nivel": 1}]})
    assert c.categorias[0].pai_rede_id is None
    v = FONTE.normalizar("vitrine", {"itens": []})
    assert v.itens == []
    loja = FONTE.normalizar("loja", {"redeLojaId": "l1", "nome": "Loja", "foto": {
        "vendidosTotal": "230 mil"}})
    assert loja.foto.vendidos_total.exato is False
    av = FONTE.normalizar("avaliacoes", {"redeProdutoId": "1", "itens": [
        {"autorRef": "u1", "texto": None, "nota": None}]})
    assert av.itens[0].autor_ref == "u1"  # vira hash no servidor; nunca é gravado
    with pytest.raises(CampoInvalido) as exc:
        FONTE.normalizar("avaliacoes", {"redeProdutoId": "1", "itens": [{"nota": 6}]})
    assert exc.value.campo == "itens[0].nota"
    vid = FONTE.normalizar("produto_videos", {"redeProdutoId": "1", "itens": [
        {"redeVideoId": "7", "autorHandle": "fulana.achados", "views": 10}]})
    assert vid.itens[0].autor_handle == "fulana.achados"


def test_tipo_desconhecido_e_reservados():
    for tipo in ("busca_assunto", "video", "outro"):
        with pytest.raises(CampoInvalido) as exc:
            FONTE.normalizar(tipo, {})
        assert exc.value.motivo == "tipo_desconhecido"


def test_produto_de_url_e_url_canonica():
    ref = FONTE.produto_de_url("https://exemplo.test/shop/product/7291000000000000001?a=1#x", "BR")
    assert ref is not None and ref.rede_produto_id == "7291000000000000001"
    assert ref.url_canonica == "https://exemplo.test/shop/product/7291000000000000001"
    assert ref.mercado == "BR"
    assert FONTE.produto_de_url("https://exemplo.test/nada", "BR") is None
    assert FONTE.produto_de_url("texto solto", "BR") is None
    # Só https num host do domínio de MERCADO_URL_PUBLICA (o coletor abre a URL logado).
    assert FONTE.produto_de_url("http://exemplo.test/shop/product/7291000000000000001", "BR") is None
    assert FONTE.produto_de_url("https://outro.test/shop/product/7291000000000000001", "BR") is None
    assert FONTE.produto_de_url("https://m.exemplo.test/product/7291000000000000001", "BR") is not None
    # Userinfo, porta estranha e host com caracteres fora do simples: recusados; a URL devolvida é
    # reconstruída (host em minúsculas, sem porta).
    assert FONTE.produto_de_url("https://exemplo.test@evil.test/product/7291000000000000001", "BR") is None
    assert FONTE.produto_de_url("https://exemplo.test:8443/product/7291000000000000001", "BR") is None
    assert FONTE.produto_de_url("https://exem plo.test/product/7291000000000000001", "BR") is None
    ref = FONTE.produto_de_url("https://WWW.Exemplo.test:443/shop/product/7291000000000000002", "BR")
    assert ref is not None and ref.url_canonica == "https://www.exemplo.test/shop/product/7291000000000000002"
    assert FONTE.url_canonica("https://x.test/p/1/?q=2") == "https://x.test/p/1"
