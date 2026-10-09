"""Rotas do analytics (spec 019, contracts/http-api.md): 8 abas, todas **GET** em
`/api/analytics/*`, `operationId` `analytics_*`, para dono e membro (`RequireUser`), mais
`ordem-contas` (a ordem estável das contas para a cor fixa da SPA). Nenhuma
rota escreve (princípio I; guardas da seção "spec 019" em `test_constitution_guards.py`).

Os campos de custo do funil só são calculados para o dono (`eh_dono`); o membro recebe `null`.
Cada aba tem o seu módulo (`visao_geral`, `quando_postar`, `o_que_funciona`, `curvas`, `contas`,
`funil`, `mercado`, `alertas`) com `calcular()`.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from sociman_api.analytics import alertas as alertas_mod  # US8
from sociman_api.analytics import base, filtros, schemas
from sociman_api.analytics import contas as contas_mod  # US5
from sociman_api.analytics import curvas as curvas_mod  # US4
from sociman_api.analytics import funil as funil_mod  # US6
from sociman_api.analytics import mercado as mercado_mod  # US7
from sociman_api.analytics import o_que_funciona as o_que_funciona_mod  # US3
from sociman_api.analytics import ordem_contas as ordem_contas_mod  # cor fixa por conta
from sociman_api.analytics import publico as publico_mod  # spec 022
from sociman_api.analytics import quando_postar as quando_postar_mod  # US2
from sociman_api.analytics import visao_geral as visao_geral_mod  # US1
from sociman_api.analytics.filtros import Filtro, Medida
from sociman_api.auth.deps import Actor, RequireUser
from sociman_api.auth.models import UserRole
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.perfis.models import Platform

router = APIRouter(prefix="/api/analytics")

PATAMAR_PADRAO = 100


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


ERROS = _errors(400, 401, 403, 404)


def eh_dono(actor: Actor) -> bool:
    return actor.user is not None and actor.user.role == UserRole.dono


def filtro(
    db: DbSession,
    de: date | None = None, ate: date | None = None,
    perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
    conta_id: Annotated[UUID | None, Query(alias="contaId")] = None,
    rede: Platform | None = None, medida: Medida = filtros.MEDIDA_PADRAO,
) -> Filtro:
    """Os parâmetros comuns de todas as abas (período, perfil, conta, rede e medida)."""
    return filtros.montar(db, de=de, ate=ate, perfil_id=perfil_id, conta_id=conta_id,
                          rede=rede, medida=medida)


FiltroDep = Annotated[Filtro, Depends(filtro)]


def _studio(db: DbSession, f: Filtro, out):
    """Spec 020: `contexto.studio` (dias do período vindos do Studio) em todas as abas, para a
    nota de leitura e a de FR-020 nas abas por vídeo ou hora."""
    out.contexto.studio = base.uso_studio(db, f)
    return out


@router.get("/ordem-contas", operation_id="analytics_ordem_contas",
            response_model=schemas.OrdemContasOut, responses=_errors(401, 403))
def ordem_contas(actor: RequireUser, db: DbSession) -> schemas.OrdemContasOut:
    """Todas as contas na ordem estável da cor fixa (FR-006), sem filtro."""
    return ordem_contas_mod.calcular(db)


@router.get("/visao-geral", operation_id="analytics_visao_geral",
            response_model=schemas.VisaoGeralOut, responses=ERROS)
def visao_geral(actor: RequireUser, db: DbSession, f: FiltroDep) -> schemas.VisaoGeralOut:
    return _studio(db, f, visao_geral_mod.calcular(db, f))


@router.get("/quando-postar", operation_id="analytics_quando_postar",
            response_model=schemas.QuandoPostarOut, responses=ERROS)
def quando_postar(actor: RequireUser, db: DbSession, f: FiltroDep) -> schemas.QuandoPostarOut:
    return _studio(db, f, quando_postar_mod.calcular(db, f))


@router.get("/o-que-funciona", operation_id="analytics_o_que_funciona",
            response_model=schemas.OQueFuncionaOut, responses=ERROS)
def o_que_funciona(actor: RequireUser, db: DbSession,
                   f: FiltroDep) -> schemas.OQueFuncionaOut:
    return _studio(db, f, o_que_funciona_mod.calcular(db, f))


@router.get("/curvas", operation_id="analytics_curvas",
            response_model=schemas.CurvasOut, responses=ERROS)
def curvas(actor: RequireUser, db: DbSession, f: FiltroDep) -> schemas.CurvasOut:
    return _studio(db, f, curvas_mod.calcular(db, f))


@router.get("/contas", operation_id="analytics_contas",
            response_model=schemas.ContasOut, responses=ERROS)
def contas(actor: RequireUser, db: DbSession, f: FiltroDep) -> schemas.ContasOut:
    return _studio(db, f, contas_mod.calcular(db, f))


@router.get("/funil", operation_id="analytics_funil",
            response_model=schemas.FunilOut, responses=ERROS)
def funil(actor: RequireUser, db: DbSession, f: FiltroDep,
          patamar: Annotated[int, Query(ge=1)] = PATAMAR_PADRAO) -> schemas.FunilOut:
    return _studio(db, f, funil_mod.calcular(db, f, patamar, com_custo=eh_dono(actor)))


@router.get("/mercado", operation_id="analytics_mercado",
            response_model=schemas.MercadoOut, responses=ERROS)
def mercado(actor: RequireUser, db: DbSession, f: FiltroDep,
            mostrar_cortados: Annotated[bool, Query(alias="mostrarCortados")] = False
            ) -> schemas.MercadoOut:
    return _studio(db, f, mercado_mod.calcular(db, f, mostrar_cortados=mostrar_cortados))


@router.get("/alertas", operation_id="analytics_alertas",
            response_model=schemas.AlertasOut, responses=ERROS)
def alertas(actor: RequireUser, db: DbSession, f: FiltroDep) -> schemas.AlertasOut:
    return _studio(db, f, alertas_mod.calcular(db, f))


@router.get("/publico", operation_id="analytics_publico",
            response_model=schemas.PublicoOut, responses=ERROS)
def publico(actor: RequireUser, db: DbSession, f: FiltroDep) -> schemas.PublicoOut:
    """Spec 022: gênero, territórios, atividade e espectadores importados do TikTok Studio, por
    conta (só leitura)."""
    return _studio(db, f, publico_mod.calcular(db, f))
