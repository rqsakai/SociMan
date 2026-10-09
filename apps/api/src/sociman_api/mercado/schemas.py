"""Modelos Pydantic da leitura do mercado (contracts/http-api.md, "Leitura do mercado"). JSON em
camelCase. Todo número derivado é um `Numero` (valor, estimado, motivos, amostra, n de fotos)."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from sociman_api.auth.schemas import CamelModel
from sociman_api.coleta.schemas import EstadoColetaMercado
from sociman_api.mercado.models import Calor, InteresseOrigem, InteresseSituacao, RankingTipo
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import UserRef

Estado = Literal["coletando", "amostra_pequena", "ok"]


class Numero(CamelModel):
    valor: float | None
    estimado: bool = True
    motivos: list[str] = Field(default_factory=list)
    amostra_pequena: bool = False
    n_fotos: int = 0
    min: float | None = None
    max: float | None = None


class LojaRef(CamelModel):
    id: uuid.UUID
    nome: str
    oficial: bool


class CategoriaRef(CamelModel):
    id: uuid.UUID
    nome: str
    caminho: str


class PrecoOut(CamelModel):
    min_centavos: int | None
    max_centavos: int | None
    original_centavos: int | None
    moeda: str
    data_local: date


class PosicaoRanking(CamelModel):
    categoria_id: uuid.UUID | None
    tipo: RankingTipo
    janela: str
    posicao: int
    variacao7d: int | None = Field(default=None, alias="variacao7d")
    data_local: date


class InteresseResumo(CamelModel):
    id: uuid.UUID
    perfil_id: uuid.UUID | None
    origem: InteresseOrigem
    situacao: InteresseSituacao


class CartaoProdutoOut(CamelModel):
    id: uuid.UUID
    rede: Platform
    mercado: str
    rede_produto_id: str
    titulo: str | None
    url_canonica: str
    imagem_url: str | None
    loja: LojaRef | None
    categoria: CategoriaRef | None
    estado: Estado
    calor: Calor
    fotos_por_dia: int
    primeira_vez_em: datetime
    lancado_em: date | None
    ultima_foto_em: date | None
    ultima_foto_affiliate_em: date | None
    indisponivel_desde: date | None
    preco: PrecoOut | None
    comissao_bp: Numero
    comissao_por_venda_centavos: Numero
    n_criadores: Numero
    retorno_afiliado_centavos_dia: Numero
    saturacao: Numero
    vendas_periodo: Numero
    gmv_periodo_centavos: Numero
    crescimento: Numero
    vendas_dia: Numero
    vendas_totais: Numero
    gmv_total_centavos: Numero
    novo_em_alta: bool
    alto_retorno_poucos_afiliados: bool
    poucos_afiliados: bool
    rankings: list[PosicaoRanking] = Field(default_factory=list)
    interesses: list[InteresseResumo] = Field(default_factory=list)


class ContextoMercado(CamelModel):
    de: date
    ate: date
    anterior_de: date
    anterior_ate: date
    fuso: str
    mercado: str
    perfil_id: uuid.UUID | None
    gerado_em: datetime
    constantes: dict[str, Any]


class ListaProdutosOut(CamelModel):
    itens: list[CartaoProdutoOut]
    proximo: str | None
    total: int
    contexto: ContextoMercado


class MercadoLinkOut(CamelModel):
    url: str
    expires_at: datetime | None


class ImagemOut(CamelModel):
    id: uuid.UUID
    sha256: str
    url: str
    original: MercadoLinkOut
    width: int
    height: int
    bytes: int
    content_type: str
    posicao: int


class FichaOut(CamelModel):
    id: uuid.UUID
    hash_conteudo: str
    titulo: str
    descricao: str
    atributos: list[dict[str, Any]]
    variantes: list[dict[str, Any]]
    argumentos: list[str]
    selos: list[str]
    categoria: CategoriaRef | None
    loja: LojaRef | None
    imagens: list[ImagemOut]
    esquema_versao: str
    coletado_em: datetime
    created_at: datetime
    diff: dict[str, Any] | None = None


class InteresseDoUsuario(CamelModel):
    perfil_id: uuid.UUID
    perfil_nome: str
    interesse_id: uuid.UUID | None


class AdotadoEm(CamelModel):
    perfil_id: uuid.UUID
    produto_id: uuid.UUID


class ProdutoMercadoOut(CartaoProdutoOut):
    ficha: FichaOut | None
    galeria: list[ImagemOut]
    n_fichas: int
    interesses_do_usuario: list[InteresseDoUsuario]
    adotado_em: list[AdotadoEm]
    contexto: ContextoMercado


class FotoOut(CamelModel):
    data_local: date
    turno: str
    fonte: str
    vendidos: int | None
    vendidos_min: int | None
    vendidos_max: int | None
    vendidos_exato: bool | None
    preco_min_centavos: int | None
    preco_max_centavos: int | None
    preco_original_centavos: int | None
    moeda: str
    nota: float | None
    n_avaliacoes: int | None
    comissao_bp: int | None
    n_criadores: int | None
    vendas7d: int | None = Field(default=None, alias="vendas7d")
    vendas30d: int | None = Field(default=None, alias="vendas30d")
    estoque_visivel: int | None
    disponivel: bool
    bruto_pendente: bool


class DiariaOut(CamelModel):
    data_local: date
    vendidos: Numero
    vendas_dia: Numero
    preco_min_centavos: int | None
    n_criadores: Numero
    comissao_bp: Numero


class ResumoSerie(CamelModel):
    vendas_periodo: Numero
    gmv_periodo_centavos: Numero
    crescimento: Numero


class SerieOut(CamelModel):
    produto_id: uuid.UUID
    de: date
    ate: date
    fotos: list[FotoOut]
    diaria: list[DiariaOut]
    resumo: ResumoSerie


class CardOut(CamelModel):
    itens: list[CartaoProdutoOut]
    total: int
    criterio: dict[str, Any] | None = None


class TotaisOut(CamelModel):
    produtos: int
    acompanhados: int
    coletando: int
    amostra_pequena: int
    ok: int
    vendas_periodo: Numero
    gmv_periodo_centavos: Numero


class ResumoOut(CamelModel):
    contexto: ContextoMercado
    mais_vendidos: CardOut
    novos_em_alta: CardOut
    alto_retorno_poucos_afiliados: CardOut
    estado_coleta: EstadoColetaMercado
    totais: TotaisOut


# ---- US4/US5 (reservados aqui para o contrato nascer inteiro) ----

class InteresseOut(CamelModel):
    id: uuid.UUID
    perfil_id: uuid.UUID | None
    todos_os_perfis: bool
    mercado_produto_id: uuid.UUID
    produto: CartaoProdutoOut | None
    origem: InteresseOrigem
    situacao: InteresseSituacao
    motivo: dict[str, Any]
    nota: str
    produto_id: uuid.UUID | None
    tema_id: uuid.UUID | None
    pausado_em: datetime | None
    encerrado_em: datetime | None
    version: int
    created_at: datetime
    created_by: UserRef | None
    updated_at: datetime


class InteresseCriarIn(CamelModel):
    """Um link colado (`url`) ou um produto do lago (`mercadoProdutoId`); um dos dois."""

    url: str | None = Field(default=None, max_length=2000)
    mercado_produto_id: uuid.UUID | None = None
    nota: str = Field(default="", max_length=2000)


class InteresseAtualizarIn(CamelModel):
    version: int = Field(ge=1)
    situacao: InteresseSituacao | None = None
    nota: str | None = Field(default=None, max_length=2000)


class InteresseRevertIn(CamelModel):
    version: int = Field(ge=1)
    to_version: int = Field(ge=1)


class InteressesList(CamelModel):
    itens: list[InteresseOut]
    total: int


class CategoriaOut(CamelModel):
    id: uuid.UUID
    rede_categoria_id: str
    nome: str
    nivel: int
    pai_id: uuid.UUID | None
    caminho: str
    ativa: bool
    n_produtos: int


class CategoriasList(CamelModel):
    itens: list[CategoriaOut]


class PerfilConfigOut(CamelModel):
    perfil_id: uuid.UUID
    mercado: str
    categoria_ids: list[uuid.UUID]
    categorias: list[CategoriaRef]
    lojas_seguidas: list[LojaRef]
    max_relacionados_dia: int
    avisar_novo_em_alta: bool
    relacionados_hoje: int
    maximo_categorias: int
    version: int
    updated_at: datetime | None
    updated_by: UserRef | None


class PerfilConfigIn(CamelModel):
    version: int = Field(ge=0)
    mercado: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    categoria_ids: list[uuid.UUID] = Field(default_factory=list)
    max_relacionados_dia: int = Field(default=10, ge=0, le=50)
    avisar_novo_em_alta: bool = True


class SeguirLojaIn(CamelModel):
    version: int = Field(ge=0)


# ---- US5: ficha versionada, rankings, vídeos, avaliações, lojas ----

class FichasList(CamelModel):
    itens: list[FichaOut]


class PosicaoRankingItem(CamelModel):
    ranking_foto_id: uuid.UUID
    data_local: date
    fonte: str
    categoria: CategoriaRef | None
    tipo: RankingTipo
    janela: str
    posicao: int
    valor_exibido: str | None
    valor_num: float | None


class ResumoRankingOut(CamelModel):
    categoria_id: uuid.UUID | None
    categoria: CategoriaRef | None
    tipo: RankingTipo
    janela: str
    posicao_atual: int | None
    melhor_posicao: int | None
    dias_no_topo: int
    variacao7d: int | None = Field(default=None, alias="variacao7d")
    entrou_em: date | None
    saiu_em: date | None


class RankingsProdutoOut(CamelModel):
    itens: list[PosicaoRankingItem]
    resumo: list[ResumoRankingOut]


class VideoOut(CamelModel):
    """Só o @ público e contadores (FR-011): nada mais sobre a pessoa."""

    rede_video_id: str
    autor_handle: str
    views: int | None
    likes: int | None
    comentarios: int | None
    compartilhamentos: int | None
    legenda: str | None
    publicado_em: datetime | None
    data_local: date
    posicao: int | None
    url: str | None


class VideosList(CamelModel):
    itens: list[VideoOut]
    proximo: str | None


class AvaliacaoOut(CamelModel):
    """Nunca `autor_hash`, nome, @ ou foto de perfil (FR-010)."""

    id: uuid.UUID
    texto: str | None
    nota: int | None
    data_avaliacao: date | None
    variante: str | None
    imagens: list[ImagemOut]
    curtidas: int | None
    coletado_em: datetime


class AvaliacoesResumo(CamelModel):
    total: int
    por_nota: dict[str, int]
    com_texto: int
    com_fotos: int


class AvaliacoesList(CamelModel):
    itens: list[AvaliacaoOut]
    proximo: str | None
    resumo: AvaliacoesResumo


class FotoRankingOut(CamelModel):
    id: uuid.UUID
    data_local: date
    fonte: str
    categoria: CategoriaRef | None
    tipo: RankingTipo
    janela: str
    n_itens: int


class RankingItemOut(CamelModel):
    posicao: int
    produto: CartaoProdutoOut
    valor_exibido: str | None
    valor_num: float | None
    variacao: Literal["subiu", "caiu", "igual", "novo"]
    delta: int | None


class RankingSaiuOut(CamelModel):
    produto: CartaoProdutoOut
    ultima_posicao: int


class RankingAtualOut(CamelModel):
    ranking_foto_id: uuid.UUID
    data_local: date
    anterior_data_local: date | None
    itens: list[RankingItemOut]
    sairam: list[RankingSaiuOut]


class RankingsListarOut(CamelModel):
    fotos: list[FotoRankingOut]
    atual: RankingAtualOut | None
    contexto: ContextoMercado


class CartaoLojaOut(CamelModel):
    id: uuid.UUID
    rede: Platform
    mercado: str
    rede_loja_id: str
    nome: str
    oficial: bool
    url: str | None
    primeira_vez_em: datetime
    ultimo_visto_em: datetime
    ultima_foto_em: date | None
    nota: Numero
    seguidores: Numero
    envio_no_prazo_pct: Numero
    n_produtos: Numero
    vendidos_total: Numero
    n_produtos_no_lago: int
    n_produtos_acompanhados: int
    gmv_estimado_centavos: Numero
    concentracao_top1: Numero
    lancamentos30d: int = Field(alias="lancamentos30d")
    comissao_media_bp: Numero
    seguida_por: list[uuid.UUID]


class LojasList(CamelModel):
    itens: list[CartaoLojaOut]
    total: int
    proximo: str | None
    contexto: ContextoMercado


class FotoLojaOut(CamelModel):
    data_local: date
    fonte: str
    nota: float | None
    seguidores: int | None
    envio_no_prazo_pct: float | None
    tempo_resposta_pct: float | None
    n_produtos: int | None
    vendidos_total: int | None
    vendidos_total_min: int | None
    vendidos_total_max: int | None
    vendidos_total_exato: bool | None


class LojaDetalheOut(CartaoLojaOut):
    fotos: list[FotoLojaOut]
    produtos: list[CartaoProdutoOut]
    novos30d: list[CartaoProdutoOut] = Field(alias="novos30d")
    contexto: ContextoMercado


# ---- US6: adotar no catálogo ----

class AdotarIn(CamelModel):
    perfil_id: uuid.UUID


class AdotadoOut(CamelModel):
    produto_id: uuid.UUID
    interesse_id: uuid.UUID
    perfil_id: uuid.UUID
    mercado_produto_id: uuid.UUID
