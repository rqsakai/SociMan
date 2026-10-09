"""Adaptador `tiktok_shop/1` (contracts/coletor.md, "Adaptador `redes/tiktok_shop.py`").

Este é o **único** módulo do coletor que conhece endereços da rede (guarda `test_guardas`). Ele
não navega nem clica: recebe a página (só leitura) e as respostas que a própria página carregou
(interceptação passiva) e devolve os payloads normalizados em camelCase da seção "Payloads
normalizados" do contrato.

PLACEHOLDERS ATÉ A SONDA GUIADA COM O DONO (quickstart §2, passo 4):
- `INTERCEPTAR` está **vazia de valores reais**. A sonda (`uma-vez --limite 1`) mostra, no bruto e
  no Chrome, quais URLs da API interna a página chama; os padrões entram aqui e viram a versão
  `tiktok_shop/1`. Até lá, nenhuma resposta é guardada e o parser cai no DOM (`via_dom`).
- Os parsers leem um **formato de referência** (as listas `_CANDIDATOS` abaixo, com vários nomes
  prováveis por campo). A sonda ajusta nomes de chaves, nunca as regras nem o formato de saída.
- `IMAGENS_HOSTS`, `CAPTCHA_PADROES`, `LOGIN_PADROES` e `URL_LOGIN` são genéricos.

Os testes usam um adaptador com `interceptar=` e `imagens_hosts=` de teste (servidor sintético).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sociman_coletor import modelos
from sociman_coletor.redes.base import ImagemRef, Interceptada, Resultado

ESQUEMA = "tiktok_shop/1"
REDE = "tiktok"
TIPOS = ("produto", "ranking", "categorias", "vitrine", "loja", "avaliacoes", "produto_videos")
TIPOS_RESERVADOS = ("busca_assunto", "video")  # 027: item `erro` `tipo_desconhecido`
RANKING_ACOMPANHAR_TOP = 30

# Lista fechada de padrões de URL de resposta a guardar. VAZIA até a sonda com o dono:
# os valores reais entram aqui depois de confirmados no bruto da primeira coleta (quickstart §2).
INTERCEPTAR: tuple[re.Pattern[str], ...] = ()

# Hosts de imagem da rede (sufixos). Genéricos; a sonda confirma.
IMAGENS_HOSTS: frozenset[str] = frozenset({"tiktokcdn.com", "tiktokcdn-us.com", "ibyteimg.com"})

CAPTCHA_PADROES: tuple[re.Pattern[str], ...] = (
    re.compile(r"/verify", re.IGNORECASE),
    re.compile(r"captcha", re.IGNORECASE),
    re.compile(r"verifica[çc][ãa]o", re.IGNORECASE),
    re.compile(r"security\s*check", re.IGNORECASE),
)
LOGIN_PADROES: tuple[re.Pattern[str], ...] = (
    re.compile(r"/login(/|\?|$)", re.IGNORECASE),
    re.compile(r"/passport/", re.IGNORECASE),
)
# Mensagens de sessão inválida numa resposta interceptada (genérico; a sonda ajusta).
SESSAO_INVALIDA = re.compile(
    r"not\s*log(ged)?\s*in|logged\s*out|session\s*(expired|invalid)|"
    r"login\s*required",
    re.IGNORECASE,
)
SESSAO_CODIGOS: frozenset[int] = frozenset()  # códigos numéricos da API interna; placeholder

# Página de login da rede, só para `perfil-iniciar` (o dono loga à mão, sem CDP).
URL_LOGIN = "https://affiliate.tiktok.com/"

_FAIXA = re.compile(r"^\s*([\d.,]+)\s*(mil|k|mi|m)?\s*(\+)?\s*(vendid[oa]s?)?\s*$", re.IGNORECASE)
_DINHEIRO = re.compile(r"[-+]?\d[\d.,]*")
_ID_NA_URL = re.compile(r"/(?:product|produto|p|pdp/[^/?#]+)/(\d{6,})(?:[/?#]|$)")
_LOJA_NA_URL = re.compile(r"/(?:shop|store|loja)/(?:@)?([A-Za-z0-9_.-]{3,})(?:[/?#]|$)")

# Nomes prováveis por campo (formato de referência; o 1º é o que o teste sintético usa).
_CANDIDATOS: dict[str, tuple[str, ...]] = {
    "produto": ("product", "product_info", "productInfo", "product_detail", "productDetail"),
    "affiliate": ("affiliate", "affiliate_info", "affiliateInfo", "commission_info"),
    "produto_id": ("product_id", "productId", "id"),
    "titulo": ("title", "product_name", "productName"),
    "descricao": ("description", "desc", "product_description"),
    "atributos": ("specifications", "attributes", "properties", "specs"),
    "atributo_nome": ("attr_name", "spec_name", "key", "label"),
    "atributo_valor": ("attr_value", "spec_value", "value"),
    "variantes": ("skus", "sku_list", "skuList", "variants"),
    "variante_id": ("sku_id", "skuId", "id"),
    "variante_nome": ("sku_name", "skuName", "title", "spec"),
    "preco": ("price", "price_info", "priceInfo"),
    "preco_venda": ("sale_price", "salePrice", "current_price", "real_price", "price"),
    "preco_min": ("min_price", "minPrice", "sale_price", "salePrice"),
    "preco_max": ("max_price", "maxPrice", "sale_price", "salePrice"),
    "preco_original": ("original_price", "originalPrice", "market_price", "list_price"),
    "moeda": ("currency", "currency_code", "currencyCode"),
    "estoque": ("stock", "stock_count", "quantity", "inventory"),
    "imagens": ("images", "image_list", "imageList", "main_images", "pictures"),
    "imagem": ("image", "cover", "thumbnail", "main_image", "img"),
    "url_list": ("url_list", "urlList", "urls"),
    "url": ("url", "uri", "src"),
    "vendidos": ("sold_count", "soldCount", "sales", "sold", "sales_count"),
    "nota": ("rating", "score", "avg_rating", "product_rating"),
    "nota_valor": ("score", "rating", "value", "avg"),
    "n_avaliacoes": ("review_count", "reviewCount", "reviews", "comment_count", "count"),
    "disponivel": ("available", "is_available", "on_sale", "in_stock"),
    "selos": ("labels", "tags", "badges", "label_list"),
    "argumentos": ("selling_points", "sellingPoints", "highlights", "benefits"),
    "cupons": ("coupons", "coupon_list", "vouchers"),
    "frete_gratis": ("free_shipping", "freeShipping", "is_free_shipping"),
    "categoria": ("category", "category_info", "categoryInfo"),
    "categoria_id": ("category_id", "categoryId", "id", "cat_id"),
    "categoria_nome": ("category_name", "categoryName", "nome_categoria", "label", "title"),
    "categoria_caminho": ("path", "category_path", "breadcrumb", "parents"),
    "categoria_nivel": ("level", "depth", "nivel"),
    "categoria_pai": ("parent_id", "parentId", "parent_category_id"),
    "categorias": ("categories", "category_list", "categoryList"),
    "loja": ("shop", "seller", "store", "shop_info", "shopInfo"),
    "loja_id": ("shop_id", "shopId", "seller_id", "sellerId", "id"),
    "loja_nome": ("shop_name", "shopName", "seller_name", "store_name", "title"),
    "loja_oficial": ("official", "is_official", "isOfficial", "official_shop"),
    "loja_url": ("shop_url", "shopUrl", "url", "link"),
    "lancado_em": ("launch_time", "launchTime", "create_time", "createTime", "listed_at"),
    "comissao": ("commission_rate", "commissionRate", "commission", "rate"),
    "comissao_direcionada": (
        "targeted_commission_rate",
        "targetedCommissionRate",
        "target_commission",
    ),
    "n_criadores": ("creator_count", "creatorCount", "creators", "affiliate_count"),
    "vendas_7d": ("sales_7d", "sales7d", "sold_7d", "sales_last_7_days"),
    "vendas_30d": ("sales_30d", "sales30d", "sold_30d", "sales_last_30_days"),
    "plano_aberto": ("open_plan", "openPlan", "is_open_plan", "open_collaboration"),
    "amostra_gratis": ("free_sample", "freeSample", "sample_available"),
    "ranking_itens": ("items", "list", "products", "product_list", "data_list"),
    "posicao": ("rank", "position", "index", "ranking"),
    "valor_exibido": ("display_value", "displayValue", "sold_text", "sales_text"),
    "produto_url": ("product_url", "productUrl", "url", "link", "detail_url"),
    "adicionado_em": ("added_time", "addedTime", "add_time", "create_time", "createTime"),
    "seguidores": ("followers", "follower_count", "followerCount", "fans"),
    "envio_no_prazo": ("on_time_shipping_rate", "onTimeShippingRate", "shipping_on_time_pct"),
    "tempo_resposta": ("response_rate", "responseRate", "reply_rate"),
    "n_produtos": ("product_count", "productCount", "products_count"),
    "vendidos_total": ("sold_total", "soldTotal", "total_sold", "total_sales"),
    "novo": ("is_new", "isNew", "new"),
    "avaliacoes": ("reviews", "review_list", "reviewList", "comments", "comment_list"),
    "avaliacao_id": ("review_id", "reviewId", "comment_id", "id"),
    "autor": ("user", "author", "reviewer"),
    "autor_id": ("uid", "user_id", "userId", "id"),
    "texto": ("text", "content", "comment", "review_text"),
    "nota_avaliacao": ("rating", "score", "star", "stars"),
    "data_avaliacao": ("create_time", "createTime", "review_time", "time", "date"),
    "variante_texto": ("sku_specification", "sku_name", "skuName", "spec", "variant"),
    "curtidas": ("digg_count", "diggCount", "like_count", "likeCount", "likes"),
    "total_paginas": ("total_pages", "totalPages", "page_count"),
    "total": ("total", "total_count", "totalCount"),
    "pagina": ("page", "page_no", "pageNo", "cursor"),
    "videos": ("videos", "video_list", "videoList", "items", "list"),
    "video_id": ("video_id", "videoId", "item_id", "aweme_id", "id"),
    "handle": ("unique_id", "uniqueId", "handle"),
    "views": ("play_count", "playCount", "views", "view_count"),
    "comentarios": ("comment_count", "commentCount", "comments"),
    "compartilhamentos": ("share_count", "shareCount", "shares"),
    "legenda": ("desc", "caption", "title", "text"),
    "publicado_em": ("create_time", "createTime", "publish_time", "published_at"),
    "duracao": ("duration", "duration_s", "video_duration"),
    "produto_marcado": ("product_tagged", "productTagged", "has_product_anchor", "anchored"),
}


# ---- utilidades de parse ----


def _pegar(d: Any, chave: str, padrao: Any = None) -> Any:
    """O primeiro candidato presente (e não nulo) de `_CANDIDATOS[chave]` em `d`."""
    if not isinstance(d, dict):
        return padrao
    for nome in _CANDIDATOS[chave]:
        if nome in d and d[nome] is not None:
            return d[nome]
    return padrao


def _texto(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _inteiro(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v))
    if isinstance(v, str):
        m = _DINHEIRO.search(v)
        if not m:
            return None
        bruto = (
            m.group(0).replace(".", "").replace(",", ".")
            if "," in m.group(0)
            else m.group(0).replace(",", "")
        )
        try:
            return int(round(float(bruto)))
        except ValueError:
            return None
    if isinstance(v, dict):
        return _inteiro(_pegar(v, "total"))
    return None


def _decimal(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        m = _DINHEIRO.search(v)
        if not m:
            return None
        s = m.group(0)
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _booleano(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int | float):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "sim", "yes", "y")
    return None


def faixa(v: Any) -> dict[str, Any] | None:
    """Contador exibido → `{valor, min, max, exato}`. "1,2 mil" → 1200 (1150..1249, inexato);
    "10 mil+" → 10000 sem teto; 320 → exato. Irreconhecível → None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, dict):
        if "valor" in v:
            return v
        return faixa(_pegar(v, "total"))
    if isinstance(v, int | float):
        n = int(round(v))
        return {"valor": n, "min": n, "max": n, "exato": True}
    m = _FAIXA.match(str(v))
    if m is None:
        return None
    num, sufixo, mais, _ = m.groups()
    bruto = num.replace(".", "").replace(",", ".") if "," in num else num.replace(".", "")
    try:
        base = float(bruto)
    except ValueError:
        return None
    mult = {None: 1, "mil": 1_000, "k": 1_000, "mi": 1_000_000, "m": 1_000_000}[
        sufixo.lower() if sufixo else None
    ]
    valor = int(round(base * mult))
    if mais:
        return {"valor": valor, "min": valor, "max": None, "exato": False}
    if sufixo is None and "," not in num:
        return {"valor": valor, "min": valor, "max": valor, "exato": True}
    casas = len(bruto.split(".")[1]) if "." in bruto else 0
    passo = mult / (10**casas)
    return {
        "valor": valor,
        "min": int(valor - passo // 2),
        "max": int(valor + passo // 2 - 1),
        "exato": False,
    }


def centavos(v: Any) -> int | None:
    """Dinheiro → centavos. Strings ("R$ 49,90", "49.90") e números são **reais**; um dict com
    `amount`/`value` idem. Negativo → None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, dict):
        for k in ("amount", "value", "price", "sale_price"):
            if k in v:
                return centavos(v[k])
        return None
    d = _decimal(v)
    if d is None or d < 0:
        return None
    return int(round(d * 100))


def bp(v: Any) -> int | None:
    """Comissão → pontos-base. "12%" ou 12 → 1200; 0.12 → 1200; 1200 (≥ 100 e inteiro, sem %)
    é tratado como bp já."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        d = _decimal(v)
        if d is None:
            return None
        if "%" in v:
            return int(round(d * 100))
        v = d
    if isinstance(v, int) and not isinstance(v, bool):
        return v if v >= 100 else v * 100
    if isinstance(v, float):
        if v <= 1.0:
            return int(round(v * 10_000))
        if v < 100:
            return int(round(v * 100))
        return int(round(v))
    return None


def data_iso(v: Any) -> str | None:
    """Timestamp (s ou ms) ou texto → `AAAA-MM-DD`."""
    dt = _datetime(v)
    return dt.date().isoformat() if dt else None


def datahora_iso(v: Any) -> str | None:
    dt = _datetime(v)
    return dt.isoformat() if dt else None


def _datetime(v: Any) -> datetime | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        n = float(v)
        if n > 1e12:
            n /= 1000.0
        if n <= 0:
            return None
        try:
            return datetime.fromtimestamp(n, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            return _datetime(int(s))
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.combine(date.fromisoformat(s[:10]), datetime.min.time(), UTC)
            except ValueError:
                return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


def _url_imagem(v: Any) -> str | None:
    """Uma imagem pode vir como string, `{url}` ou `{url_list: [...]}`."""
    if isinstance(v, str):
        return v if v.startswith(("http://", "https://")) else None
    if isinstance(v, dict):
        lista = _pegar(v, "url_list")
        if isinstance(lista, list) and lista:
            return _url_imagem(lista[0])
        return _url_imagem(_pegar(v, "url"))
    return None


def _urls_imagens(v: Any) -> list[str]:
    if not isinstance(v, list):
        u = _url_imagem(v)
        return [u] if u else []
    saida: list[str] = []
    for item in v:
        u = _url_imagem(item)
        if u and u not in saida:
            saida.append(u)
    return saida


def _lista_textos(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    saida: list[str] = []
    for item in v:
        t = _texto(
            item
            if not isinstance(item, dict)
            else (item.get("text") or item.get("title") or item.get("label"))
        )
        if t:
            saida.append(t)
    return saida


def _procurar(json: Any, chave: str, profundidade: int = 6) -> Any:
    """Procura, em profundidade, um dict que tenha um dos candidatos de `chave`."""
    if profundidade < 0:
        return None
    if isinstance(json, dict):
        achado = _pegar(json, chave)
        if achado is not None:
            return achado
        for v in json.values():
            achado = _procurar(v, chave, profundidade - 1)
            if achado is not None:
                return achado
    elif isinstance(json, list):
        for v in json:
            achado = _procurar(v, chave, profundidade - 1)
            if achado is not None:
                return achado
    return None


def definir(campos: dict[str, Any], caminho: str, valor: Any) -> None:
    """Põe `valor` em `campos` pelo caminho pontuado ("ficha.variantes.0.imagemSha"). Quando o
    alvo final é uma lista, acrescenta; senão, define a chave."""
    partes = caminho.split(".")
    alvo: Any = campos
    for parte in partes[:-1]:
        alvo = alvo[int(parte)] if isinstance(alvo, list) else alvo.setdefault(parte, {})
    ultima = partes[-1]
    if isinstance(alvo, list):
        alvo[int(ultima)] = valor
        return
    atual = alvo.get(ultima)
    if isinstance(atual, list):
        atual.append(valor)
    else:
        alvo[ultima] = valor


class AdaptadorTikTokShop:
    """Implementa `redes.base.ColetorRede`. `interceptar`/`imagens_hosts` só são trocados pelos
    testes (servidor sintético); em produção valem as constantes do módulo."""

    esquema = ESQUEMA
    rede = REDE
    TIPOS = TIPOS
    CAPTCHA_PADROES = CAPTCHA_PADROES
    LOGIN_PADROES = LOGIN_PADROES
    URL_LOGIN = URL_LOGIN

    def __init__(
        self,
        interceptar: Iterable[re.Pattern[str]] | None = None,
        imagens_hosts: Iterable[str] | None = None,
    ):
        self.INTERCEPTAR = tuple(interceptar) if interceptar is not None else INTERCEPTAR
        self.IMAGENS_HOSTS = (
            frozenset(imagens_hosts) if imagens_hosts is not None else IMAGENS_HOSTS
        )

    # ---- URLs ----

    @staticmethod
    def url_canonica(url: str) -> str:
        p = urlsplit(url.strip())
        return urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))

    @staticmethod
    def url_pagina(url: str, n: int) -> str:
        """Paginação derivada da URL da tarefa: troca/define `page=n` (a sonda confirma)."""
        p = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k != "page"]
        q.append(("page", str(n)))
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))

    def e_derivada(self, url: str, base: str) -> bool:
        a, b = urlsplit(url), urlsplit(base)
        if a.netloc.lower() != b.netloc.lower():
            return False
        ca, cb = a.path.rstrip("/"), b.path.rstrip("/")
        return ca == cb or ca.startswith(cb + "/")

    def intercepta(self, url: str) -> bool:
        return any(p.search(url) for p in self.INTERCEPTAR)

    def host_de_imagem(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        host = host.lower()
        return any(host == h or host.endswith("." + h) for h in self.IMAGENS_HOSTS)

    def sessao_invalida(self, interceptadas: list[Interceptada]) -> bool:
        for i in interceptadas:
            if not isinstance(i.json, dict):
                continue
            codigo = i.json.get("status_code", i.json.get("code"))
            if isinstance(codigo, int) and codigo in SESSAO_CODIGOS:
                return True
            msg = i.json.get("status_msg") or i.json.get("message") or i.json.get("msg")
            if isinstance(msg, str) and SESSAO_INVALIDA.search(msg):
                return True
        return False

    # ---- entrada ----

    def coletar(
        self, pagina: Any, tarefa: modelos.Tarefa, interceptadas: list[Interceptada]
    ) -> Resultado:
        if tarefa.tipo not in TIPOS:
            return Resultado(erro_codigo="tipo_desconhecido")
        bruto = self.montar_bruto(interceptadas)
        try:
            resultado = self._parse(tarefa.tipo, tarefa, [i.json for i in interceptadas])
        except Exception:  # noqa: BLE001 - o motivo vai no código; a rodada segue
            return Resultado(bruto=bruto, erro_codigo="parser_falhou")
        if resultado.tem_campos:
            resultado.bruto = bruto
            resultado.fonte = tarefa.fonte
            return resultado
        if pagina is not None and tarefa.tipo == "produto":
            dom = self._parser_dom_produto(pagina, tarefa)
            if dom.tem_campos:
                dom.bruto = bruto
                dom.fonte = "pagina_publica"
                dom.via_dom = True
                return dom
        return Resultado(
            bruto=bruto,
            erro_codigo="interceptacao_vazia" if not interceptadas else "pagina_sem_campos",
        )

    def reprocessar(self, tarefa_tipo: str, bruto: Any, fonte: str | None) -> Resultado:
        """Reaplica o parser atual sobre um bruto guardado (sem página, sem DOM)."""
        if tarefa_tipo not in TIPOS:
            return Resultado(erro_codigo="tipo_desconhecido")
        jsons = (
            [i.get("json") for i in (bruto or {}).get("interceptadas", [])]
            if isinstance(bruto, dict)
            else []
        )
        tarefa = modelos.Tarefa(
            tarefa_id="", tipo=tarefa_tipo, chave="", url="", fonte=fonte or "pagina_publica"
        )
        try:
            resultado = self._parse(tarefa_tipo, tarefa, jsons)
        except Exception:  # noqa: BLE001
            return Resultado(bruto=bruto, erro_codigo="parser_falhou")
        resultado.bruto = bruto
        resultado.fonte = fonte
        if not resultado.tem_campos:
            resultado.erro_codigo = "pagina_sem_campos"
        return resultado

    @staticmethod
    def montar_bruto(interceptadas: list[Interceptada]) -> dict[str, Any]:
        """O bruto guardado: as respostas interceptadas, URL sem query. A poda vem depois."""
        return {
            "esquema": ESQUEMA,
            "interceptadas": [
                {
                    "url": urlunsplit(urlsplit(i.url)[:3] + ("", "")),
                    "status": i.status,
                    "json": i.json,
                }
                for i in interceptadas
            ],
        }

    def _parse(self, tipo: str, tarefa: modelos.Tarefa, jsons: list[Any]) -> Resultado:
        parser = getattr(self, f"parse_{tipo}")
        return parser(jsons, tarefa)

    # ---- parsers por tipo ----

    def parse_produto(self, jsons: list[Any], tarefa: modelos.Tarefa) -> Resultado:
        publico = affiliate = None
        for j in jsons:
            publico = publico or _procurar(j, "produto")
            affiliate = affiliate or _procurar(j, "affiliate")
        if publico is None and affiliate is None:
            return Resultado()
        fonte_bloco = publico if publico is not None else affiliate
        produto_id = _texto(_pegar(fonte_bloco, "produto_id")) or self.produto_id_da_url(tarefa.url)
        if not produto_id:
            return Resultado()
        campos: dict[str, Any] = {
            "redeProdutoId": produto_id,
            "urlCanonica": self.url_canonica(tarefa.url) if tarefa.url else "",
        }
        imagens: list[ImagemRef] = []
        if publico is not None:
            ficha, refs = self._ficha(publico)
            campos["ficha"] = ficha
            imagens.extend(refs)
            campos["paginaPublica"] = self._pagina_publica(publico)
        if affiliate is not None:
            campos["affiliate"] = self._affiliate(affiliate)
        return Resultado(campos=campos, imagens=imagens)

    def _ficha(self, p: dict[str, Any]) -> tuple[dict[str, Any], list[ImagemRef]]:
        refs: list[ImagemRef] = []
        atributos = []
        for a in _pegar(p, "atributos", []) or []:
            if not isinstance(a, dict):
                continue
            nome = _texto(_pegar(a, "atributo_nome") or a.get("name"))
            valor = _texto(_pegar(a, "atributo_valor"))
            if nome and valor and nome != "[podado]":
                atributos.append({"nome": nome, "valor": valor})
        variantes = []
        for i, s in enumerate(_pegar(p, "variantes", []) or []):
            if not isinstance(s, dict):
                continue
            preco = _pegar(s, "preco")
            preco_dict = preco if isinstance(preco, dict) else s
            var = {
                "redeVarianteId": _texto(_pegar(s, "variante_id")),
                "nome": _texto(_pegar(s, "variante_nome")) or f"Variante {i + 1}",
                "precoCentavos": centavos(
                    _pegar(preco_dict, "preco_venda") if isinstance(preco, dict) else preco
                ),
                "precoOriginalCentavos": centavos(_pegar(preco_dict, "preco_original")),
                "estoqueVisivel": _inteiro(_pegar(s, "estoque")),
                "imagemSha": None,
            }
            variantes.append(var)
            u = _url_imagem(_pegar(s, "imagem"))
            if u:
                refs.append(
                    ImagemRef(u, "produto", f"ficha.variantes.{len(variantes) - 1}.imagemSha")
                )
        for u in _urls_imagens(_pegar(p, "imagens", [])):
            refs.append(ImagemRef(u, "produto", "ficha.imagensSha"))
        ficha = {
            "titulo": _texto(_pegar(p, "titulo")) or "",
            "descricao": _texto(_pegar(p, "descricao")) or "",
            "atributos": atributos,
            "variantes": variantes,
            "argumentos": _lista_textos(_pegar(p, "argumentos")),
            "selos": _lista_textos(_pegar(p, "selos")),
            "categoria": self._categoria(_pegar(p, "categoria")),
            "loja": self._loja(_pegar(p, "loja")),
            "lancadoEm": data_iso(_pegar(p, "lancado_em")),
            "imagensSha": [],
        }
        return ficha, refs

    def _pagina_publica(self, p: dict[str, Any]) -> dict[str, Any]:
        preco = _pegar(p, "preco")
        preco_dict = preco if isinstance(preco, dict) else {}
        nota = _pegar(p, "nota")
        nota_valor = _decimal(_pegar(nota, "nota_valor") if isinstance(nota, dict) else nota)
        n_aval = _inteiro(_pegar(nota, "n_avaliacoes") if isinstance(nota, dict) else None)
        if n_aval is None:
            n_aval = _inteiro(_pegar(p, "n_avaliacoes"))
        disponivel = _booleano(_pegar(p, "disponivel"))
        return {
            "vendidos": faixa(_pegar(p, "vendidos")),
            "precoMinCentavos": centavos(_pegar(preco_dict, "preco_min") if preco_dict else preco),
            "precoMaxCentavos": centavos(_pegar(preco_dict, "preco_max") if preco_dict else preco),
            "precoOriginalCentavos": centavos(_pegar(preco_dict, "preco_original")),
            "moeda": _texto(_pegar(preco_dict, "moeda")) or "BRL",
            "nota": nota_valor,
            "nAvaliacoes": n_aval,
            "estoqueVisivel": _inteiro(_pegar(p, "estoque")),
            "disponivel": True if disponivel is None else disponivel,
            "campos": {
                "cupons": _lista_textos(_pegar(p, "cupons")),
                "freteGratis": _booleano(_pegar(p, "frete_gratis")),
            },
        }

    def _affiliate(self, a: dict[str, Any]) -> dict[str, Any]:
        preco = _pegar(a, "preco")
        preco_dict = preco if isinstance(preco, dict) else {}
        return {
            "comissaoBp": bp(_pegar(a, "comissao")),
            "nCriadores": _inteiro(_pegar(a, "n_criadores")),
            "vendas7d": _inteiro(_pegar(a, "vendas_7d")),
            "vendas30d": _inteiro(_pegar(a, "vendas_30d")),
            "precoMinCentavos": centavos(_pegar(preco_dict, "preco_min") if preco_dict else preco),
            "precoMaxCentavos": centavos(_pegar(preco_dict, "preco_max") if preco_dict else preco),
            "moeda": _texto(_pegar(preco_dict, "moeda")) or "BRL",
            "campos": {
                "planoAberto": _booleano(_pegar(a, "plano_aberto")),
                "amostraGratis": _booleano(_pegar(a, "amostra_gratis")),
                "comissaoDirecionadaBp": bp(_pegar(a, "comissao_direcionada")),
            },
        }

    def _categoria(self, c: Any) -> dict[str, Any] | None:
        if not isinstance(c, dict):
            return None
        caminho = []
        for no in _pegar(c, "categoria_caminho", []) or []:
            if isinstance(no, dict):
                cid = _texto(_pegar(no, "categoria_id"))
                nome = _texto(_pegar(no, "categoria_nome"))
                if cid and nome:
                    caminho.append({"redeCategoriaId": cid, "nome": nome})
        cid = _texto(_pegar(c, "categoria_id")) or (
            caminho[-1]["redeCategoriaId"] if caminho else None
        )
        if not cid:
            return None
        return {"redeCategoriaId": cid, "caminho": caminho[-3:]}

    def _loja(self, loja: Any) -> dict[str, Any] | None:
        if not isinstance(loja, dict):
            return None
        lid = _texto(_pegar(loja, "loja_id"))
        nome = _texto(_pegar(loja, "loja_nome"))
        if not lid or not nome:
            return None
        url = _texto(_pegar(loja, "loja_url"))
        return {
            "redeLojaId": lid,
            "nome": nome,
            "oficial": bool(_booleano(_pegar(loja, "loja_oficial"))),
            "url": self.url_canonica(url) if url else None,
        }

    def parse_ranking(self, jsons: list[Any], tarefa: modelos.Tarefa) -> Resultado:
        itens_brutos = None
        categoria = None
        for j in jsons:
            itens_brutos = (
                itens_brutos if itens_brutos is not None else _procurar(j, "ranking_itens")
            )
            categoria = categoria or _procurar(j, "categoria")
        if not isinstance(itens_brutos, list):
            return Resultado()
        extra = tarefa.extra or {}
        itens: list[dict[str, Any]] = []
        refs: list[ImagemRef] = []
        for i, b in enumerate(itens_brutos[:RANKING_ACOMPANHAR_TOP]):
            if not isinstance(b, dict):
                continue
            prod = _pegar(b, "produto", b)
            pid = _texto(_pegar(prod, "produto_id")) or self.produto_id_da_url(
                _texto(_pegar(b, "produto_url")) or ""
            )
            if not pid:
                continue
            url = _texto(_pegar(b, "produto_url")) or _texto(_pegar(prod, "produto_url"))
            vend = _pegar(b, "vendidos")
            fx = faixa(vend)
            preco = _pegar(prod, "preco")
            preco_dict = preco if isinstance(preco, dict) else {}
            item = {
                "posicao": _inteiro(_pegar(b, "posicao")) or (i + 1),
                "redeProdutoId": pid,
                "urlCanonica": self.url_canonica(url) if url else "",
                "titulo": _texto(_pegar(prod, "titulo")),
                "imagemSha": None,
                "valorExibido": _texto(_pegar(b, "valor_exibido"))
                or (_texto(vend) if isinstance(vend, str) else None),
                "valorNum": fx["valor"] if fx else None,
                "campos": {
                    "precoMinCentavos": centavos(
                        _pegar(preco_dict, "preco_min") if preco_dict else preco
                    ),
                    "comissaoBp": bp(_pegar(b, "comissao")),
                    "nCriadores": _inteiro(_pegar(b, "n_criadores")),
                },
                "loja": self._loja(_pegar(prod, "loja")),
            }
            itens.append(item)
            u = (
                _url_imagem(_pegar(prod, "imagem"))
                or (_urls_imagens(_pegar(prod, "imagens")) or [None])[0]
            )
            if u:
                refs.append(ImagemRef(u, "produto", f"itens.{len(itens) - 1}.imagemSha"))
        if not itens:
            return Resultado()
        cat = self._categoria(categoria)
        if cat is None and extra.get("categoriaRedeId"):
            cat = {"redeCategoriaId": str(extra["categoriaRedeId"]), "caminho": []}
        campos = {
            "rankingTipo": extra.get("rankingTipo", "mais_vendidos"),
            "janela": extra.get("janela", "7d"),
            "categoria": cat,
            "itens": itens,
        }
        return Resultado(campos=campos, imagens=refs)

    def parse_categorias(self, jsons: list[Any], tarefa: modelos.Tarefa) -> Resultado:
        lista = None
        for j in jsons:
            lista = _procurar(j, "categorias")
            if isinstance(lista, list):
                break
        if not isinstance(lista, list):
            return Resultado()
        saida: list[dict[str, Any]] = []

        def andar(nos: list[Any], nivel: int, pai: str | None) -> None:
            for no in nos:
                if not isinstance(no, dict):
                    continue
                cid = _texto(_pegar(no, "categoria_id"))
                nome = _texto(_pegar(no, "categoria_nome"))
                if not cid or not nome:
                    continue
                nv = _inteiro(_pegar(no, "categoria_nivel")) or nivel
                pai_id = _texto(_pegar(no, "categoria_pai")) or pai
                saida.append(
                    {"redeCategoriaId": cid, "nome": nome, "nivel": min(nv, 3), "paiRedeId": pai_id}
                )
                filhos = no.get("children") or no.get("sub_categories") or no.get("subCategories")
                if isinstance(filhos, list) and nv < 3:
                    andar(filhos, nv + 1, cid)

        andar(lista, 1, None)
        return Resultado(campos={"categorias": saida}) if saida else Resultado()

    def parse_vitrine(self, jsons: list[Any], tarefa: modelos.Tarefa) -> Resultado:
        lista = None
        for j in jsons:
            lista = _procurar(j, "ranking_itens")
            if isinstance(lista, list):
                break
        if not isinstance(lista, list):
            return Resultado()
        itens: list[dict[str, Any]] = []
        refs: list[ImagemRef] = []
        for b in lista:
            if not isinstance(b, dict):
                continue
            prod = _pegar(b, "produto", b)
            pid = _texto(_pegar(prod, "produto_id"))
            if not pid:
                continue
            url = _texto(_pegar(b, "produto_url")) or _texto(_pegar(prod, "produto_url"))
            itens.append(
                {
                    "redeProdutoId": pid,
                    "urlCanonica": self.url_canonica(url) if url else "",
                    "titulo": _texto(_pegar(prod, "titulo")),
                    "imagemSha": None,
                    "adicionadoEm": data_iso(_pegar(b, "adicionado_em")),
                    "campos": {"comissaoBp": bp(_pegar(b, "comissao"))},
                }
            )
            u = _url_imagem(_pegar(prod, "imagem"))
            if u:
                refs.append(ImagemRef(u, "produto", f"itens.{len(itens) - 1}.imagemSha"))
        return Resultado(campos={"itens": itens}, imagens=refs) if itens else Resultado()

    def parse_loja(self, jsons: list[Any], tarefa: modelos.Tarefa) -> Resultado:
        loja = None
        produtos = None
        for j in jsons:
            loja = loja or _procurar(j, "loja")
            produtos = produtos if produtos is not None else _procurar(j, "ranking_itens")
        if not isinstance(loja, dict):
            return Resultado()
        lid = _texto(_pegar(loja, "loja_id")) or self.loja_id_da_url(tarefa.url)
        nome = _texto(_pegar(loja, "loja_nome"))
        if not lid or not nome:
            return Resultado()
        url = _texto(_pegar(loja, "loja_url")) or tarefa.url
        itens: list[dict[str, Any]] = []
        refs: list[ImagemRef] = []
        for b in produtos if isinstance(produtos, list) else []:
            if not isinstance(b, dict):
                continue
            pid = _texto(_pegar(b, "produto_id"))
            if not pid:
                continue
            purl = _texto(_pegar(b, "produto_url"))
            preco = _pegar(b, "preco")
            preco_dict = preco if isinstance(preco, dict) else {}
            itens.append(
                {
                    "redeProdutoId": pid,
                    "urlCanonica": self.url_canonica(purl) if purl else "",
                    "titulo": _texto(_pegar(b, "titulo")),
                    "imagemSha": None,
                    "precoMinCentavos": centavos(
                        _pegar(preco_dict, "preco_min") if preco_dict else preco
                    ),
                    "moeda": _texto(_pegar(preco_dict, "moeda")) or "BRL",
                    "vendidos": faixa(_pegar(b, "vendidos")),
                    "novo": bool(_booleano(_pegar(b, "novo"))),
                }
            )
            u = _url_imagem(_pegar(b, "imagem"))
            if u:
                refs.append(ImagemRef(u, "produto", f"produtos.{len(itens) - 1}.imagemSha"))
        campos = {
            "redeLojaId": lid,
            "nome": nome,
            "oficial": bool(_booleano(_pegar(loja, "loja_oficial"))),
            "url": self.url_canonica(url) if url else None,
            "foto": {
                "nota": _decimal(_pegar(loja, "nota"))
                if not isinstance(_pegar(loja, "nota"), dict)
                else _decimal(_pegar(_pegar(loja, "nota"), "nota_valor")),
                "seguidores": _inteiro(_pegar(loja, "seguidores")),
                "envioNoPrazoPct": _decimal(_pegar(loja, "envio_no_prazo")),
                "tempoRespostaPct": _decimal(_pegar(loja, "tempo_resposta")),
                "nProdutos": _inteiro(_pegar(loja, "n_produtos")),
                "vendidosTotal": faixa(_pegar(loja, "vendidos_total")),
                "campos": {},
            },
            "produtos": itens,
        }
        return Resultado(campos=campos, imagens=refs)

    def parse_avaliacoes(self, jsons: list[Any], tarefa: modelos.Tarefa) -> Resultado:
        lista = None
        raiz = None
        for j in jsons:
            lista = _procurar(j, "avaliacoes")
            if isinstance(lista, list):
                raiz = j
                break
        if not isinstance(lista, list):
            return Resultado()
        pid = self.produto_id_da_url(tarefa.url) or _texto(_procurar(raiz, "produto_id"))
        if not pid:
            return Resultado()
        itens: list[dict[str, Any]] = []
        refs: list[ImagemRef] = []
        for r in lista:
            if not isinstance(r, dict):
                continue
            autor = _pegar(r, "autor")
            autor_ref = _texto(_pegar(autor, "autor_id")) if isinstance(autor, dict) else None
            autor_ref = autor_ref or _texto(r.get("user_id") or r.get("uid"))
            item = {
                "redeAvaliacaoId": _texto(_pegar(r, "avaliacao_id")),
                "autorRef": autor_ref,
                "texto": _texto(_pegar(r, "texto")),
                "nota": _inteiro(_pegar(r, "nota_avaliacao")),
                "dataAvaliacao": data_iso(_pegar(r, "data_avaliacao")),
                "variante": _texto(_pegar(r, "variante_texto")),
                "imagensSha": [],
                "curtidas": _inteiro(_pegar(r, "curtidas")),
                "campos": {},
            }
            if item["nota"] is not None:
                item["nota"] = max(1, min(5, item["nota"]))
            itens.append(item)
            for u in _urls_imagens(_pegar(r, "imagens", [])):
                refs.append(ImagemRef(u, "avaliacao", f"itens.{len(itens) - 1}.imagensSha"))
        pagina = _inteiro(_pegar(raiz, "pagina")) if isinstance(raiz, dict) else None
        chave_pag = tarefa.chave.rsplit(":", 1)[-1] if tarefa.chave else ""
        campos = {
            "redeProdutoId": pid,
            "pagina": pagina or (int(chave_pag) if chave_pag.isdigit() else 1),
            "totalPaginas": _inteiro(_procurar(raiz, "total_paginas")),
            "itens": itens,
        }
        return Resultado(campos=campos, imagens=refs)

    def parse_produto_videos(self, jsons: list[Any], tarefa: modelos.Tarefa) -> Resultado:
        lista = None
        raiz = None
        for j in jsons:
            lista = _procurar(j, "videos")
            if isinstance(lista, list):
                raiz = j
                break
        if not isinstance(lista, list):
            return Resultado()
        pid = self.produto_id_da_url(tarefa.url) or _texto(_procurar(raiz, "produto_id"))
        if not pid:
            return Resultado()
        itens: list[dict[str, Any]] = []
        for i, v in enumerate(lista):
            if not isinstance(v, dict):
                continue
            vid = _texto(_pegar(v, "video_id"))
            autor = _pegar(v, "autor")
            handle = _texto(_pegar(autor, "handle")) if isinstance(autor, dict) else None
            handle = handle or _texto(_pegar(v, "handle"))
            if not vid or not handle:
                continue
            stats = v.get("statistics") or v.get("stats") or v
            itens.append(
                {
                    "posicao": _inteiro(_pegar(v, "posicao")) or (i + 1),
                    "redeVideoId": vid,
                    "autorHandle": handle.lstrip("@"),
                    "views": _inteiro(_pegar(stats, "views")),
                    "likes": _inteiro(_pegar(stats, "curtidas")),
                    "comentarios": _inteiro(_pegar(stats, "comentarios")),
                    "compartilhamentos": _inteiro(_pegar(stats, "compartilhamentos")),
                    "legenda": _texto(_pegar(v, "legenda")),
                    "publicadoEm": datahora_iso(_pegar(v, "publicado_em")),
                    "campos": {
                        "duracaoS": _inteiro(_pegar(v, "duracao")),
                        "produtoMarcado": _booleano(_pegar(v, "produto_marcado")),
                    },
                }
            )
        return Resultado(campos={"redeProdutoId": pid, "itens": itens}) if itens else Resultado()

    # ---- reserva: DOM ----

    def _parser_dom_produto(self, pagina: Any, tarefa: modelos.Tarefa) -> Resultado:
        """Só leitura do DOM: título (og:title/h1), preços "R$" e "vendidos" por regex no HTML.
        Sem `evaluate`, sem clique."""
        pid = self.produto_id_da_url(pagina.url) or self.produto_id_da_url(tarefa.url)
        if not pid:
            return Resultado()
        titulo = None
        try:
            meta = pagina.locator('meta[property="og:title"]').first
            if meta.count():
                titulo = _texto(meta.get_attribute("content", timeout=2000))
            if not titulo:
                h1 = pagina.locator("h1").first
                if h1.count():
                    titulo = _texto(h1.inner_text(timeout=2000))
        except Exception:  # noqa: BLE001 - DOM é reserva; sem título não há ficha
            titulo = None
        if not titulo:
            return Resultado()
        html = ""
        try:
            html = pagina.content()
        except Exception:  # noqa: BLE001
            pass
        precos = [centavos(m) for m in re.findall(r"R\$\s?\d[\d.]*,\d{2}", html)]
        precos = [p for p in precos if p]
        vend = re.search(r"([\d.,]+\s*(?:mil|mi)?\+?)\s*vendid", html, re.IGNORECASE)
        imagens: list[ImagemRef] = []
        try:
            imgs = pagina.locator("img[src^='http']")
            for i in range(min(imgs.count(), 12)):
                src = imgs.nth(i).get_attribute("src", timeout=1000)
                if src and self.host_de_imagem(src):
                    imagens.append(ImagemRef(src, "produto", "ficha.imagensSha"))
        except Exception:  # noqa: BLE001
            imagens = []
        campos = {
            "redeProdutoId": pid,
            "urlCanonica": self.url_canonica(tarefa.url) if tarefa.url else "",
            "ficha": {
                "titulo": titulo,
                "descricao": "",
                "atributos": [],
                "variantes": [],
                "argumentos": [],
                "selos": [],
                "categoria": None,
                "loja": None,
                "lancadoEm": None,
                "imagensSha": [],
            },
            "paginaPublica": {
                "vendidos": faixa(vend.group(1)) if vend else None,
                "precoMinCentavos": min(precos) if precos else None,
                "precoMaxCentavos": max(precos) if precos else None,
                "precoOriginalCentavos": None,
                "moeda": "BRL",
                "nota": None,
                "nAvaliacoes": None,
                "estoqueVisivel": None,
                "disponivel": True,
                "campos": {"cupons": [], "freteGratis": None},
            },
        }
        return Resultado(campos=campos, imagens=imagens)

    # ---- ids ----

    @staticmethod
    def produto_id_da_url(url: str) -> str | None:
        m = _ID_NA_URL.search(url or "")
        return m.group(1) if m else None

    @staticmethod
    def loja_id_da_url(url: str) -> str | None:
        m = _LOJA_NA_URL.search(url or "")
        return m.group(1) if m else None


def adaptador_padrao() -> AdaptadorTikTokShop:
    return AdaptadorTikTokShop()
