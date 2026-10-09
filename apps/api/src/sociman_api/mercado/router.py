"""Rotas de leitura do mercado (contracts/http-api.md, "Leitura do mercado"): todas **GET**, para
dono e membro (`RequireUser`) e para as tools MCP de leitura. Nada aqui escreve (FR-042; guarda
`test_mercado_leitura_so_get_e_sem_escrita`). As escritas de interesse e a ponte com a 012 ficam
em `router_perfil.py` e nas rotas da US4/US6.

Nenhuma rota tem "tiktok" no caminho nem no `operationId` (FR-057); a rede é um valor.
"""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from sociman_api.auth.deps import RequireHuman, RequireHumanOwner, RequireUser
from sociman_api.coleta import service as coleta_service
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.mercado import adotar as adotar_mod
from sociman_api.mercado import apresentacao as ap
from sociman_api.mercado import consulta, consulta_detalhe, filtros, interesses, mercados, schemas
from sociman_api.mercado.filtros import Filtro
from sociman_api.mercado.models import Fonte, InteresseOrigem, InteresseSituacao, RankingTipo
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import VersionsList

router = APIRouter(prefix="/api/mercado")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


ERROS = _errors(400, 401, 403, 404)


def filtro(
    db: DbSession,
    de: date | None = None, ate: date | None = None,
    perfil_id: Annotated[uuid.UUID | None, Query(alias="perfilId")] = None,
    mercado: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
    rede: Platform | None = None,
    categoria_id: Annotated[uuid.UUID | None, Query(alias="categoriaId")] = None,
    loja_id: Annotated[uuid.UUID | None, Query(alias="lojaId")] = None,
    origem: Annotated[list[InteresseOrigem] | None, Query()] = None,
    so_acompanhados: Annotated[bool, Query(alias="soAcompanhados")] = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    ordenar: Annotated[str | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Filtro:
    """O filtro comum (FR-043)."""
    return filtros.montar(db, de=de, ate=ate, perfil_id=perfil_id, mercado=mercado, rede=rede,
                          categoria_id=categoria_id, loja_id=loja_id, origem=origem,
                          so_acompanhados=so_acompanhados, q=q, ordenar=ordenar, limite=limite,
                          cursor=cursor)


FiltroDep = Annotated[Filtro, Depends(filtro)]


@router.get("/produtos", operation_id="mercado_produtos_listar",
            response_model=schemas.ListaProdutosOut, responses=ERROS)
def produtos_listar(actor: RequireUser, db: DbSession, f: FiltroDep) -> schemas.ListaProdutosOut:
    """O cartão mínimo de cada produto (vendas, GMV, crescimento, comissão, retorno), calculado na
    leitura e marcado como estimado. Paginação no servidor (`cursor`)."""
    return consulta.listar_produtos(db, f, mercados.hoje(f.mercado))


@router.get("/produtos/{produto_id}", operation_id="mercado_produtos_detalhe",
            response_model=schemas.ProdutoMercadoOut, responses=ERROS)
def produtos_detalhe(produto_id: uuid.UUID, actor: RequireUser, db: DbSession, f: FiltroDep
                     ) -> schemas.ProdutoMercadoOut:
    """O cartão, a ficha atual, a galeria e os perfis do usuário para "Acompanhar neste perfil"."""
    return consulta.detalhe_produto(db, produto_id, f, mercados.hoje(f.mercado))


@router.get("/produtos/{produto_id}/serie", operation_id="mercado_produtos_serie",
            response_model=schemas.SerieOut, responses=ERROS)
def produtos_serie(produto_id: uuid.UUID, actor: RequireUser, db: DbSession, f: FiltroDep,
                   fonte: Literal["pagina_publica", "affiliate"] | None = None) -> schemas.SerieOut:
    """As fotos do período e a série diária (vendidos, vendas/dia, preço, criadores)."""
    return consulta.serie_produto(db, produto_id, f, Fonte(fonte) if fonte else None)


@router.get("/resumo", operation_id="mercado_resumo", response_model=schemas.ResumoOut,
            responses=ERROS)
def resumo(actor: RequireUser, db: DbSession, f: FiltroDep) -> schemas.ResumoOut:
    """Os cards do Cockpit: mais vendidos, novos em alta, alto retorno com poucos afiliados,
    estado da coleta e totais."""
    return consulta.resumo(db, f, mercados.hoje(f.mercado), coleta_service.estado(db, f.mercado))


# ---- US4: interesses (todos os perfis) e categorias ----

@router.get("/interesses", operation_id="mercado_interesses_listar_todos",
            response_model=schemas.InteressesList, responses=ERROS)
def interesses_listar_todos(actor: RequireUser, db: DbSession,
                            perfil_id: Annotated[uuid.UUID | None, Query(alias="perfilId")] = None,
                            origem: Annotated[InteresseOrigem | None, Query()] = None,
                            situacao: Annotated[InteresseSituacao | None, Query()] = None,
                            limite: Annotated[int, Query(ge=1, le=500)] = 200
                            ) -> schemas.InteressesList:
    """Os acompanhamentos de todos os perfis (aba Acompanhamentos), com filtros."""
    itens = interesses.listar(db, perfil_id, origem, situacao, incluir_vitrine=perfil_id is None,
                              limite=limite)
    return ap.interesses_out(db, itens)


@router.patch("/interesses/{interesse_id}", operation_id="mercado_interesses_editar",
              response_model=schemas.InteresseOut, responses=_errors(400, 401, 403, 404, 409))
def interesses_atualizar(interesse_id: uuid.UUID, body: schemas.InteresseAtualizarIn,
                         actor: RequireHuman, db: DbSession) -> schemas.InteresseOut:
    """Pausar, reativar, encerrar ou anotar (qualquer humano; MCP → `somente_humano`)."""
    i = interesses.atualizar(db, actor, interesse_id, body.version, body.situacao, body.nota)
    return ap.interesses_out(db, [i]).itens[0]


@router.get("/interesses/{interesse_id}/versions", operation_id="mercado_interesses_versions",
            response_model=VersionsList, responses=ERROS)
def interesses_versions(interesse_id: uuid.UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return ap.versions_list(db, interesses.versoes(db, interesse_id))


@router.post("/interesses/{interesse_id}/revert", operation_id="mercado_interesses_revert",
             response_model=schemas.InteresseOut, responses=_errors(400, 401, 403, 404, 409))
def interesses_revert(interesse_id: uuid.UUID, body: schemas.InteresseRevertIn,
                      actor: RequireHumanOwner, db: DbSession) -> schemas.InteresseOut:
    """Só o dono humano (princípio VII)."""
    i = interesses.reverter(db, actor, interesse_id, body.version, body.to_version)
    return ap.interesses_out(db, [i]).itens[0]


@router.get("/categorias", operation_id="mercado_categorias_listar",
            response_model=schemas.CategoriasList, responses=ERROS)
def categorias_listar(actor: RequireUser, db: DbSession,
                      mercado: Annotated[str, Query(pattern=r"^[A-Z]{2}$")] = "BR",
                      nivel: Annotated[int | None, Query(ge=1, le=3)] = None,
                      q: Annotated[str | None, Query(max_length=100)] = None,
                      so_ativas: Annotated[bool, Query(alias="soAtivas")] = True
                      ) -> schemas.CategoriasList:
    """A taxonomia observada na rede (FR-008), com o nº de produtos no lago por categoria."""
    return ap.categorias_out(db, mercado, nivel, q, so_ativas)


# ---- US5: ficha versionada, rankings, vídeos, avaliações, lojas ----

@router.get("/produtos/{produto_id}/fichas", operation_id="mercado_produtos_fichas",
            response_model=schemas.FichasList, responses=ERROS)
def produtos_fichas(produto_id: uuid.UUID, actor: RequireUser, db: DbSession) -> schemas.FichasList:
    """As versões da ficha (uma por mudança de conteúdo), com o `diff` em relação à anterior."""
    return consulta_detalhe.fichas_produto(db, produto_id)


@router.get("/produtos/{produto_id}/rankings", operation_id="mercado_produtos_rankings",
            response_model=schemas.RankingsProdutoOut, responses=ERROS)
def produtos_rankings(produto_id: uuid.UUID, actor: RequireUser, db: DbSession, f: FiltroDep
                      ) -> schemas.RankingsProdutoOut:
    """As posições do produto nos rankings do período e o resumo por ranking (FR-049)."""
    return consulta_detalhe.rankings_produto(db, produto_id, f)


@router.get("/produtos/{produto_id}/videos", operation_id="mercado_produtos_videos",
            response_model=schemas.VideosList, responses=ERROS)
def produtos_videos(produto_id: uuid.UUID, actor: RequireUser, db: DbSession, f: FiltroDep,
                    todas_observacoes: Annotated[bool, Query(alias="todasObservacoes")] = False
                    ) -> schemas.VideosList:
    """Os vídeos top do produto: só o @ público e contadores (FR-011)."""
    return consulta_detalhe.videos_produto(db, produto_id, f, todas_observacoes)


@router.get("/produtos/{produto_id}/avaliacoes", operation_id="mercado_produtos_avaliacoes",
            response_model=schemas.AvaliacoesList, responses=ERROS)
def produtos_avaliacoes(produto_id: uuid.UUID, actor: RequireUser, db: DbSession, f: FiltroDep,
                        nota: Annotated[int | None, Query(ge=1, le=5)] = None,
                        com_fotos: Annotated[bool | None, Query(alias="comFotos")] = None
                        ) -> schemas.AvaliacoesList:
    """As avaliações públicas, sem autor (FR-010), com as fotos de clientes."""
    return consulta_detalhe.avaliacoes_produto(db, produto_id, f, nota, com_fotos)


@router.get("/rankings", operation_id="mercado_rankings_listar",
            response_model=schemas.RankingsListarOut, responses=ERROS)
def rankings_listar(actor: RequireUser, db: DbSession, f: FiltroDep,
                    tipo: Annotated[RankingTipo | None, Query()] = None,
                    janela: Annotated[str | None, Query(max_length=10)] = None,
                    fonte: Literal["pagina_publica", "affiliate"] | None = None
                    ) -> schemas.RankingsListarOut:
    """As fotos de ranking do período e, com `categoriaId`, a foto atual com a variação de
    posição contra a anterior."""
    return consulta_detalhe.listar_rankings(db, f, mercados.hoje(f.mercado), f.categoria_id, tipo,
                                            janela, fonte)


@router.get("/lojas", operation_id="mercado_lojas_listar", response_model=schemas.LojasList,
            responses=ERROS)
def lojas_listar(actor: RequireUser, db: DbSession, f: FiltroDep,
                 oficial: Annotated[bool | None, Query()] = None,
                 seguida_por: Annotated[uuid.UUID | None, Query(alias="seguidaPor")] = None,
                 ordenar_loja: Annotated[str, Query(alias="ordenarLoja")] = "gmv"
                 ) -> schemas.LojasList:
    """O cartão de cada loja: nota, seguidores, envio no prazo, produtos, GMV estimado,
    concentração, lançamentos e comissão média (FR-049)."""
    return consulta_detalhe.listar_lojas(db, f, mercados.hoje(f.mercado), f.q, oficial, seguida_por,
                                         ordenar_loja)


@router.get("/lojas/{loja_id}", operation_id="mercado_lojas_detalhe",
            response_model=schemas.LojaDetalheOut, responses=ERROS)
def lojas_detalhe(loja_id: uuid.UUID, actor: RequireUser, db: DbSession,
                  de: date | None = None, ate: date | None = None,
                  perfil_id: Annotated[uuid.UUID | None, Query(alias="perfilId")] = None,
                  mercado: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
                  ) -> schemas.LojaDetalheOut:
    """O cartão da loja, as fotos, os produtos do lago e os novos em 30 dias. (O filtro comum
    não serve aqui: o `lojaId` dele colidiria com o parâmetro de caminho.)"""
    f = filtros.montar(db, de=de, ate=ate, perfil_id=perfil_id, mercado=mercado)
    return consulta_detalhe.detalhe_loja(db, loja_id, f, mercados.hoje(f.mercado))


# ---- US6: adotar no catálogo (só humano; depende da 012) ----

@router.post("/produtos/{produto_id}/adotar", operation_id="mercado_produtos_adotar",
             status_code=201, response_model=schemas.AdotadoOut,
             responses=_errors(400, 401, 403, 404, 409))
def produtos_adotar(produto_id: uuid.UUID, body: schemas.AdotarIn, actor: RequireHuman,
                    db: DbSession) -> schemas.AdotadoOut:
    """Copia a ficha e as imagens para um produto do catálogo do perfil (spec 012) e cria o
    vínculo; 409 `passo_indisponivel` sem a 012, 409 `ja_adotado` com o id existente."""
    r = adotar_mod.adotar(db, actor, produto_id, body.perfil_id)
    return schemas.AdotadoOut(produto_id=r["produtoId"], interesse_id=r["interesseId"],
                              perfil_id=body.perfil_id, mercado_produto_id=produto_id)
