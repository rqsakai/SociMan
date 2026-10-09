"""Adaptador da fonte `tiktok_shop/1` (contracts/coletor.md, "Payloads normalizados").

Valida os `campos` de cada tipo de tarefa com Pydantic (camelCase, como o coletor manda) e
converte faixas ("1,2 mil", "10 mil+") em `{valor, min, max, exato}` quando vierem como texto.
Nada aqui chama a rede nem conhece endereços dela (guarda FR-057): a única URL que este módulo
entende é a `urlCanonica` que o coletor devolveu, para extrair o identificador do produto.
"""

import re
from datetime import date, datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic.alias_generators import to_camel

from sociman_api.mercado.fontes.base import BasesUrl, CampoInvalido, ProdutoRef, campo_do_erro
from sociman_api.perfis.models import Platform

ESQUEMA = "tiktok_shop/1"
TIPOS = ("produto", "ranking", "categorias", "vitrine", "loja", "avaliacoes", "produto_videos")
_CHAVES = {
    "produto": re.compile(r"^produto:[A-Za-z0-9_-]+$"),
    "ranking": re.compile(r"^ranking:[A-Za-z0-9_-]+:(mais_vendidos|em_alta|novos|alta_comissao)"
                          r":(1d|7d|30d|total)$"),
    "categorias": re.compile(r"^categorias$"),
    "vitrine": re.compile(r"^vitrine$"),
    "loja": re.compile(r"^loja:[A-Za-z0-9_-]+$"),
    "avaliacoes": re.compile(r"^avaliacoes:[A-Za-z0-9_-]+:\d+$"),
    "produto_videos": re.compile(r"^produto_videos:[A-Za-z0-9_-]+$"),
}
# O id do produto na URL canônica: o último segmento numérico do caminho (`/product/7291…`).
_ID_NA_URL = re.compile(r"/(?:product|produto|p|pdp/[^/?#]+)/(\d{6,})(?:[/?#]|$)")
_FAIXA = re.compile(r"^\s*([\d.,]+)\s*(mil|k|mi|m)?\s*(\+)?\s*$", re.IGNORECASE)


class _Modelo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")


class Faixa(_Modelo):
    """Um contador que a página pode mostrar arredondado ("1,2 mil") ou com teto ("10 mil+")."""

    valor: int | None = None
    min: int | None = None
    max: int | None = None
    exato: bool = True

    @field_validator("valor", "min", "max")
    @classmethod
    def _nao_negativo(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("contador negativo")
        return v


def parse_faixa(texto: str) -> Faixa:
    """"1,2 mil" → 1150..1249 (ponto médio 1200, inexato); "10 mil+" → 10000.. (sem teto);
    "320" → exato. Texto irreconhecível → `CampoInvalido`."""
    m = _FAIXA.match(texto)
    if m is None:
        raise CampoInvalido("vendidos", "campos_invalidos")
    num, sufixo, mais = m.groups()
    bruto = num.replace(".", "").replace(",", ".") if "," in num else num.replace(".", "")
    try:
        base = float(bruto)
    except ValueError as exc:
        raise CampoInvalido("vendidos", "campos_invalidos") from exc
    mult = {None: 1, "mil": 1_000, "k": 1_000, "mi": 1_000_000, "m": 1_000_000}[
        sufixo.lower() if sufixo else None]
    valor = round(base * mult)
    if mais:
        return Faixa(valor=valor, min=valor, max=None, exato=False)
    if sufixo is None and "," not in num:
        return Faixa(valor=valor, min=valor, max=valor, exato=True)
    # A precisão exibida: "1,2 mil" tem 1 casa → metade do passo (50) para cada lado.
    casas = len(bruto.split(".")[1]) if "." in bruto else 0
    passo = mult / (10 ** casas)
    return Faixa(valor=valor, min=int(valor - passo // 2), max=int(valor + passo // 2 - 1),
                 exato=False)


def _faixa(valor: Any) -> Faixa | None:
    if valor is None:
        return None
    if isinstance(valor, Faixa):
        return valor
    if isinstance(valor, int | float):
        return Faixa(valor=int(valor), min=int(valor), max=int(valor), exato=True)
    if isinstance(valor, str):
        return parse_faixa(valor)
    if isinstance(valor, dict):
        f = Faixa.model_validate(valor)
        if f.valor is None and f.min is not None and f.max is not None:
            f.valor = (f.min + f.max) // 2
        return f
    raise CampoInvalido("vendidos", "campos_invalidos")


class Atributo(_Modelo):
    nome: str = Field(min_length=1, max_length=200)
    valor: str = Field(max_length=2000)


class Variante(_Modelo):
    rede_variante_id: str | None = None
    nome: str = Field(min_length=1, max_length=300)
    preco_centavos: int | None = Field(default=None, ge=0)
    preco_original_centavos: int | None = Field(default=None, ge=0)
    estoque_visivel: int | None = Field(default=None, ge=0)
    imagem_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CategoriaNo(_Modelo):
    rede_categoria_id: str = Field(min_length=1)
    nome: str = Field(min_length=1, max_length=200)


class CategoriaRef(_Modelo):
    rede_categoria_id: str = Field(min_length=1)
    caminho: list[CategoriaNo] = Field(default_factory=list, max_length=3)


class LojaRef(_Modelo):
    rede_loja_id: str = Field(min_length=1)
    nome: str = Field(min_length=1, max_length=300)
    oficial: bool = False
    url: str | None = None


class FichaIn(_Modelo):
    titulo: str = Field(min_length=1, max_length=1000)
    descricao: str = Field(default="", max_length=20000)
    atributos: list[Atributo] = Field(default_factory=list, max_length=200)
    variantes: list[Variante] = Field(default_factory=list, max_length=200)
    argumentos: list[str] = Field(default_factory=list, max_length=50)
    selos: list[str] = Field(default_factory=list, max_length=50)
    categoria: CategoriaRef | None = None
    loja: LojaRef | None = None
    lancado_em: date | None = None
    imagens_sha: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("imagens_sha")
    @classmethod
    def _shas(cls, v: list[str]) -> list[str]:
        for s in v:
            if not re.fullmatch(r"[0-9a-f]{64}", s):
                raise ValueError("sha256 inválido")
        return v


class PaginaPublicaIn(_Modelo):
    vendidos: Any = None
    preco_min_centavos: int | None = Field(default=None, ge=0)
    preco_max_centavos: int | None = Field(default=None, ge=0)
    preco_original_centavos: int | None = Field(default=None, ge=0)
    moeda: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    nota: float | None = Field(default=None, ge=0, le=5)
    n_avaliacoes: int | None = Field(default=None, ge=0)
    estoque_visivel: int | None = Field(default=None, ge=0)
    disponivel: bool = True
    campos: dict[str, Any] = Field(default_factory=dict)

    @field_validator("vendidos", mode="after")
    @classmethod
    def _vendidos(cls, v: Any) -> Faixa | None:
        return _faixa(v)


class AffiliateIn(_Modelo):
    comissao_bp: int | None = Field(default=None, ge=0, le=10000)
    n_criadores: int | None = Field(default=None, ge=0)
    vendas_7d: int | None = Field(default=None, ge=0)
    vendas_30d: int | None = Field(default=None, ge=0)
    preco_min_centavos: int | None = Field(default=None, ge=0)
    preco_max_centavos: int | None = Field(default=None, ge=0)
    moeda: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    campos: dict[str, Any] = Field(default_factory=dict)


class ProdutoIn(_Modelo):
    rede_produto_id: str = Field(min_length=1)
    url_canonica: str = Field(min_length=8)
    ficha: FichaIn | None = None
    pagina_publica: PaginaPublicaIn | None = None
    affiliate: AffiliateIn | None = None


class ItemRankingIn(_Modelo):
    posicao: int = Field(ge=1)
    rede_produto_id: str = Field(min_length=1)
    url_canonica: str = Field(min_length=8)
    titulo: str | None = None
    imagem_sha: str | None = None
    valor_exibido: str | None = None
    valor_num: float | None = None
    campos: dict[str, Any] = Field(default_factory=dict)
    loja: LojaRef | None = None


class RankingIn(_Modelo):
    ranking_tipo: Literal["mais_vendidos", "em_alta", "novos", "alta_comissao"]
    janela: Literal["1d", "7d", "30d", "total"]
    categoria: CategoriaRef | None = None
    itens: list[ItemRankingIn] = Field(max_length=100)


class CategoriaIn(_Modelo):
    rede_categoria_id: str = Field(min_length=1)
    nome: str = Field(min_length=1, max_length=200)
    nivel: int = Field(ge=1, le=3)
    pai_rede_id: str | None = None


class CategoriasIn(_Modelo):
    categorias: list[CategoriaIn] = Field(max_length=5000)


class ItemVitrineIn(_Modelo):
    rede_produto_id: str = Field(min_length=1)
    url_canonica: str = Field(min_length=8)
    titulo: str | None = None
    imagem_sha: str | None = None
    adicionado_em: date | None = None
    campos: dict[str, Any] = Field(default_factory=dict)


class VitrineIn(_Modelo):
    itens: list[ItemVitrineIn] = Field(max_length=500)


class FotoLojaIn(_Modelo):
    nota: float | None = Field(default=None, ge=0, le=5)
    seguidores: int | None = Field(default=None, ge=0)
    envio_no_prazo_pct: float | None = Field(default=None, ge=0, le=100)
    tempo_resposta_pct: float | None = Field(default=None, ge=0, le=100)
    n_produtos: int | None = Field(default=None, ge=0)
    vendidos_total: Any = None
    campos: dict[str, Any] = Field(default_factory=dict)

    @field_validator("vendidos_total", mode="after")
    @classmethod
    def _vendidos(cls, v: Any) -> Faixa | None:
        return _faixa(v)


class ProdutoLojaIn(_Modelo):
    rede_produto_id: str = Field(min_length=1)
    url_canonica: str = Field(min_length=8)
    titulo: str | None = None
    imagem_sha: str | None = None
    preco_min_centavos: int | None = Field(default=None, ge=0)
    moeda: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    vendidos: Any = None
    novo: bool = False

    @field_validator("vendidos", mode="after")
    @classmethod
    def _vendidos(cls, v: Any) -> Faixa | None:
        return _faixa(v)


class LojaIn(_Modelo):
    rede_loja_id: str = Field(min_length=1)
    nome: str = Field(min_length=1, max_length=300)
    oficial: bool = False
    url: str | None = None
    foto: FotoLojaIn | None = None
    produtos: list[ProdutoLojaIn] = Field(default_factory=list, max_length=500)


class AvaliacaoIn(_Modelo):
    rede_avaliacao_id: str | None = None
    autor_ref: str | None = None  # só vira hash no servidor; nunca é gravado
    texto: str | None = Field(default=None, max_length=10000)
    nota: int | None = Field(default=None, ge=1, le=5)
    data_avaliacao: date | None = None
    variante: str | None = None
    imagens_sha: list[str] = Field(default_factory=list, max_length=20)
    curtidas: int | None = Field(default=None, ge=0)
    campos: dict[str, Any] = Field(default_factory=dict)


class AvaliacoesIn(_Modelo):
    rede_produto_id: str = Field(min_length=1)
    pagina: int = Field(default=1, ge=1)
    total_paginas: int | None = Field(default=None, ge=0)
    itens: list[AvaliacaoIn] = Field(max_length=200)


class VideoIn(_Modelo):
    posicao: int | None = Field(default=None, ge=1)
    rede_video_id: str = Field(min_length=1)
    autor_handle: str = Field(min_length=1, max_length=100)
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comentarios: int | None = Field(default=None, ge=0)
    compartilhamentos: int | None = Field(default=None, ge=0)
    legenda: str | None = Field(default=None, max_length=5000)
    publicado_em: datetime | None = None
    campos: dict[str, Any] = Field(default_factory=dict)


class ProdutoVideosIn(_Modelo):
    rede_produto_id: str = Field(min_length=1)
    itens: list[VideoIn] = Field(max_length=100)


_MODELOS: dict[str, type[BaseModel]] = {
    "produto": ProdutoIn, "ranking": RankingIn, "categorias": CategoriasIn,
    "vitrine": VitrineIn, "loja": LojaIn, "avaliacoes": AvaliacoesIn,
    "produto_videos": ProdutoVideosIn,
}


class FonteTikTokShop:
    rede = Platform.tiktok
    esquema_versao = ESQUEMA
    tipos = TIPOS

    def validar_chave(self, tipo: str, chave: str) -> bool:
        padrao = _CHAVES.get(tipo)
        return padrao is not None and padrao.match(chave) is not None

    def normalizar(self, tipo: str, campos: dict[str, Any]) -> BaseModel:
        modelo = _MODELOS.get(tipo)
        if modelo is None:
            raise CampoInvalido("tipo", "tipo_desconhecido")
        try:
            return modelo.model_validate(campos)
        except ValidationError as exc:
            raise CampoInvalido(campo_do_erro(exc)) from exc

    def url_canonica(self, url: str) -> str:
        """Sem query nem fragmento (FR-021); o caminho como veio."""
        partes = urlsplit(url.strip())
        return urlunsplit((partes.scheme, partes.netloc, partes.path.rstrip("/"), "", ""))

    def url_tarefa(self, tipo: str, bases: BasesUrl, *, produto_url: str | None = None,
                   rede_produto_id: str | None = None, rede_categoria_id: str | None = None,
                   ranking_tipo: str | None = None, janela: str | None = None,
                   loja_url: str | None = None, rede_loja_id: str | None = None,
                   pagina: int | None = None) -> str | None:
        """As URLs das tarefas que o servidor entrega (FR-023). O servidor não conhece os
        endereços da rede em código (princípio IX): as bases vêm da configuração do dono
        (`MERCADO_URL_PUBLICA`, `MERCADO_URL_AFFILIATE`, preenchidas depois da sonda). Sem a base,
        a tarefa não nasce (None). Os caminhos são o formato de referência até a sonda."""
        if tipo == "produto":
            return produto_url or None
        if tipo == "avaliacoes":
            return f"{produto_url}/reviews/{pagina or 1}" if produto_url else None
        if tipo == "loja" and loja_url:
            return loja_url
        if tipo == "loja":
            return f"{bases.publica}/shop/{rede_loja_id}" if bases.publica and rede_loja_id else None
        if not bases.affiliate:
            return None
        if tipo == "ranking":
            cat = rede_categoria_id or "geral"
            return f"{bases.affiliate}/product/rank/{cat}/{ranking_tipo}/{janela}"
        if tipo == "categorias":
            return f"{bases.affiliate}/product/category"
        if tipo == "vitrine":
            return f"{bases.affiliate}/showcase"
        if tipo == "produto_videos":
            return f"{bases.affiliate}/product/{rede_produto_id}/videos"
        raise ValueError(f"tipo de tarefa sem URL: {tipo}")

    def produto_de_url(self, url: str, mercado: str) -> ProdutoRef | None:
        """O id do produto no link colado pelo humano (FR-039). Não reconheceu → None."""
        canonica = self.url_canonica(url)
        if not canonica.startswith(("https://", "http://")):
            return None
        m = _ID_NA_URL.search(canonica)
        if m is None:
            return None
        return ProdutoRef(self.rede, mercado, m.group(1), canonica)
