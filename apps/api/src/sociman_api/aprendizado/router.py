"""Rotas do aprendizado (spec 023, contracts/http-api.md): `/api/perfis/{id}/aprendizado/*` e
`/api/aprendizado/*`, `operationId` `aprendizado_*`.

- **H** (`RequireHumanOwner`): toda escrita, a proposta de taxonomia e o pedido e a estimativa
  da análise da IA. Membro → 403 `somente_dono`; `system:*` ou token MCP → 403
  `somente_humano` com o evento de recusa;
- **U** (`RequireUser`): as leituras, para dono e membro; o custo vem `null` para membro.

Os GETs não gravam nada (guarda da 023). Nenhuma rota é DELETE, agenda, aprova ou publica.
"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from sociman_api.analytics.router import eh_dono
from sociman_api.aprendizado import analise as an
from sociman_api.aprendizado import (
    analise_ia,
    classificacao,
    conferencias,
    diagnostico,
    preferencias,
    recomendacoes,
    schemas,
    temas,
)
from sociman_api.aprendizado import constantes as K
from sociman_api.auth.deps import RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.ia.cliente import IaClient, get_ia_client
from sociman_api.perfis.schemas import RevertIn, VersionsList

router = APIRouter()
P = "/api/perfis/{perfil_id}/aprendizado"
A = "/api/aprendizado"
Medida = Literal["h1", "h24", "d7"]
ContaQ = Annotated[UUID | None, Query(alias="contaId")]
IaDep = Annotated[IaClient | None, Depends(get_ia_client)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {s: {"model": ErrorEnvelope} for s in statuses}


LER = _errors(400, 401, 403, 404)
ESCREVER = _errors(400, 401, 403, 404, 409)


# ---- temas e taxonomia ----

@router.get(f"{P}/temas", operation_id="aprendizado_temas_list",
            response_model=schemas.AprendizadoTemasList, responses=LER)
def temas_list(perfil_id: UUID, actor: RequireUser, db: DbSession,
               arquivados: bool = False) -> schemas.AprendizadoTemasList:
    return temas.listar(db, perfil_id, arquivados)


@router.post(f"{P}/temas", operation_id="aprendizado_temas_create",
             status_code=status.HTTP_201_CREATED, response_model=schemas.AprendizadoTema,
             responses=ESCREVER)
def temas_create(perfil_id: UUID, body: schemas.AprendizadoTemaIn, actor: RequireHumanOwner,
                 db: DbSession) -> schemas.AprendizadoTema:
    return temas.criar(db, actor, perfil_id, body)


@router.post(f"{P}/temas/lote", operation_id="aprendizado_temas_lote",
             status_code=status.HTTP_201_CREATED,
             response_model=schemas.AprendizadoTemasLoteOut, responses=ESCREVER)
def temas_lote(perfil_id: UUID, body: schemas.AprendizadoTemasLoteIn, actor: RequireHumanOwner,
               db: DbSession) -> schemas.AprendizadoTemasLoteOut:
    return temas.lote(db, actor, perfil_id, body)


@router.patch(f"{A}/temas/{{tema_id}}", operation_id="aprendizado_temas_update",
              response_model=schemas.AprendizadoTema, responses=ESCREVER)
def temas_update(tema_id: UUID, body: schemas.AprendizadoTemaPatch, actor: RequireHumanOwner,
                 db: DbSession) -> schemas.AprendizadoTema:
    return temas.editar(db, actor, tema_id, body)


@router.post(f"{A}/temas/{{tema_id}}/archive", operation_id="aprendizado_temas_archive",
             response_model=schemas.AprendizadoTema, responses=ESCREVER)
def temas_archive(tema_id: UUID, body: schemas.AprendizadoVersionIn, actor: RequireHumanOwner,
                  db: DbSession) -> schemas.AprendizadoTema:
    return temas.arquivar(db, actor, tema_id, body)


@router.post(f"{A}/temas/{{tema_id}}/restore", operation_id="aprendizado_temas_restore",
             response_model=schemas.AprendizadoTema, responses=ESCREVER)
def temas_restore(tema_id: UUID, body: schemas.AprendizadoVersionIn, actor: RequireHumanOwner,
                  db: DbSession) -> schemas.AprendizadoTema:
    return temas.restaurar(db, actor, tema_id, body)


@router.post(f"{A}/temas/{{tema_id}}/juntar", operation_id="aprendizado_temas_juntar",
             response_model=schemas.AprendizadoJuntarOut, responses=ESCREVER)
def temas_juntar(tema_id: UUID, body: schemas.AprendizadoJuntarIn, actor: RequireHumanOwner,
                 db: DbSession) -> schemas.AprendizadoJuntarOut:
    return temas.juntar(db, actor, tema_id, body)


@router.get(f"{A}/temas/{{tema_id}}/versions", operation_id="aprendizado_temas_versions",
            response_model=VersionsList, responses=LER)
def temas_versions(tema_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return temas.versions(db, tema_id)


@router.post(f"{A}/temas/{{tema_id}}/revert", operation_id="aprendizado_temas_revert",
             response_model=schemas.AprendizadoTema, responses=ESCREVER)
def temas_revert(tema_id: UUID, body: RevertIn, actor: RequireHumanOwner,
                 db: DbSession) -> schemas.AprendizadoTema:
    return temas.reverter(db, actor, tema_id, body)


@router.post(f"{P}/taxonomia/propor", operation_id="aprendizado_taxonomia_propor",
             response_model=schemas.AprendizadoProporOut,
             responses=_errors(400, 401, 403, 404, 409, 502, 503, 504))
def taxonomia_propor(perfil_id: UUID, body: schemas.AprendizadoProporIn,
                     actor: RequireHumanOwner, db: DbSession,
                     client: IaDep) -> schemas.AprendizadoProporOut:
    return temas.propor(db, actor, perfil_id, body, client)


# ---- classificações ----

@router.get(f"{P}/classificacoes", operation_id="aprendizado_classificacoes_list",
            response_model=schemas.AprendizadoClassificacoesList, responses=LER)
def classificacoes_list(
    perfil_id: UUID, actor: RequireUser, db: DbSession, conta_id: ContaQ = None,
    tema_id: Annotated[UUID | None, Query(alias="temaId")] = None,
    origem: Literal["ia", "dono", "sem_tema"] | None = None, pendentes: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=classificacao.LIMIT_MAX)] = classificacao.LIMIT_PADRAO,
) -> schemas.AprendizadoClassificacoesList:
    return classificacao.listar(db, perfil_id, conta_id=conta_id, tema_id=tema_id,
                                origem=origem, pendentes=pendentes, cursor=cursor, limit=limit)


@router.put(f"{A}/classificacoes/{{video_id}}", operation_id="aprendizado_classificacoes_put",
            response_model=schemas.AprendizadoClassificacao, responses=ESCREVER)
def classificacoes_put(video_id: UUID, body: schemas.AprendizadoClassificacaoPut,
                       actor: RequireHumanOwner,
                       db: DbSession) -> schemas.AprendizadoClassificacao:
    return classificacao.corrigir(db, actor, video_id, body)


@router.get(f"{A}/classificacoes/{{video_id}}/versions",
            operation_id="aprendizado_classificacoes_versions", response_model=VersionsList,
            responses=LER)
def classificacoes_versions(video_id: UUID, actor: RequireUser, db: DbSession) -> VersionsList:
    return classificacao.versions(db, video_id)


@router.post(f"{A}/classificacoes/{{video_id}}/revert",
             operation_id="aprendizado_classificacoes_revert",
             response_model=schemas.AprendizadoClassificacao, responses=ESCREVER)
def classificacoes_revert(video_id: UUID, body: RevertIn, actor: RequireHumanOwner,
                          db: DbSession) -> schemas.AprendizadoClassificacao:
    return classificacao.reverter(db, actor, video_id, body)


@router.post(f"{P}/classificar-pendentes", operation_id="aprendizado_classificar_pendentes",
             status_code=status.HTTP_202_ACCEPTED,
             response_model=schemas.AprendizadoClassificarOut, responses=ESCREVER)
def classificar_pendentes(perfil_id: UUID, actor: RequireHumanOwner,
                          db: DbSession) -> schemas.AprendizadoClassificarOut:
    return classificacao.pedir_pendentes(db, actor, perfil_id)


# ---- análise e recomendações ----

def _analise_out(res: an.Resultado) -> schemas.AprendizadoAnalise:
    k = schemas.AprendizadoConstantes(
        min_grupo=K.MIN_GRUPO, min_dias=K.MIN_DIAS, min_conta=K.MIN_CONTA,
        k_encolhimento=K.K_ENCOLHIMENTO, meia_vida_dias=K.MEIA_VIDA_DIAS,
        janela_dias=K.JANELA_DIAS, reamostras=K.REAMOSTRAS, concentracao=K.CONCENTRACAO,
        travada=K.TRAVADA, ampliar_min=K.AMPLIAR_MIN, cortar_max=K.CORTAR_MAX,
        cortar_min_n=K.CORTAR_MIN_N, fixar_min=K.FIXAR_MIN, evitar_max=K.EVITAR_MAX,
        limite_diario=K.LIMITE_DIARIO, peso_afinidade=K.PESO_AFINIDADE)
    ctx = res.contexto
    return schemas.AprendizadoAnalise(
        contexto=schemas.AprendizadoAnaliseContexto(
            de=res.de, ate=res.ate, medida=res.medida, fuso=ctx.fuso, aguardando=ctx.aguardando,
            posts_no_periodo=ctx.posts_no_periodo, comparacoes=res.comparacoes,
            falsos_esperados=round(res.comparacoes * K.FALSOS_ESPERADOS),
            contas=[schemas.AprendizadoContaContexto(
                conta_id=c.chave, rotulo=c.rotulo, medidos=c.medidos, estagnados=c.estagnados,
                travada=c.travada, suficiente=c.suficiente) for c in res.contas],
            travadas=res.travadas, constantes=k),
        efeitos=[recomendacoes.efeito_out(e) for e in res.efeitos],
        blocos=[schemas.AprendizadoBloco(valor=b.valor, hashtags=list(b.hashtags),
                                         n_posts=len(b.posts), quase_sempre_com=list(b.quase_com))
                for b in res.blocos],
        matriz=[schemas.AprendizadoCelulaMatriz(bloco=bv, tema_id=t, tema_nome=res.temas[t], n=n)
                for bv, t, n in res.matriz],
        sem_tema=res.sem_tema, pendentes_classificacao=res.pendentes)


@router.get(f"{P}/analise", operation_id="aprendizado_analise",
            response_model=schemas.AprendizadoAnalise, responses=LER)
def analise(perfil_id: UUID, actor: RequireUser, db: DbSession, conta_id: ContaQ = None,
            medida: Medida = "h24", de: date | None = None,
            ate: date | None = None) -> schemas.AprendizadoAnalise:
    return _analise_out(an.calcular(db, perfil_id, conta_id, medida, de, ate))


@router.get(f"{P}/recomendacoes", operation_id="aprendizado_recomendacoes",
            response_model=schemas.AprendizadoRecomendacoesOut, responses=LER)
def recomendacoes_list(perfil_id: UUID, actor: RequireUser, db: DbSession,
                       conta_id: ContaQ = None,
                       medida: Medida = "h24") -> schemas.AprendizadoRecomendacoesOut:
    return recomendacoes.out(recomendacoes.calcular(db, perfil_id, conta_id, medida))


@router.post(f"{P}/recomendacoes/decidir", operation_id="aprendizado_recomendacoes_decidir",
             response_model=schemas.AprendizadoDecidirOut, responses=ESCREVER)
def recomendacoes_decidir(perfil_id: UUID, body: schemas.AprendizadoDecidirIn,
                          actor: RequireHumanOwner,
                          db: DbSession) -> schemas.AprendizadoDecidirOut:
    return preferencias.decidir(db, actor, perfil_id, body)


@router.post(f"{A}/decisoes/{{decisao_id}}/revert", operation_id="aprendizado_decisoes_revert",
             response_model=schemas.AprendizadoRevertOut, responses=ESCREVER)
def decisoes_revert(decisao_id: UUID, body: schemas.AprendizadoVersionIn,
                    actor: RequireHumanOwner, db: DbSession) -> schemas.AprendizadoRevertOut:
    return preferencias.reverter_decisao(db, actor, decisao_id, body)


# ---- preferências ----

@router.get(f"{P}/preferencias", operation_id="aprendizado_preferencias_get",
            response_model=schemas.AprendizadoPreferenciasOut, responses=LER)
def preferencias_get(perfil_id: UUID, actor: RequireUser, db: DbSession,
                     conta_id: ContaQ = None) -> schemas.AprendizadoPreferenciasOut:
    return preferencias.obter(db, perfil_id, conta_id)


@router.patch(f"{P}/preferencias", operation_id="aprendizado_preferencias_patch",
              response_model=schemas.AprendizadoPreferencias, responses=ESCREVER)
def preferencias_patch(perfil_id: UUID, body: schemas.AprendizadoPreferenciasPatch,
                       actor: RequireHumanOwner, db: DbSession,
                       conta_id: ContaQ = None) -> schemas.AprendizadoPreferencias:
    return preferencias.patch(db, actor, perfil_id, conta_id, body)


@router.get(f"{P}/preferencias/versions", operation_id="aprendizado_preferencias_versions",
            response_model=VersionsList, responses=LER)
def preferencias_versions(perfil_id: UUID, actor: RequireUser, db: DbSession,
                          conta_id: ContaQ = None) -> VersionsList:
    return preferencias.versions(db, perfil_id, conta_id)


@router.post(f"{P}/preferencias/revert", operation_id="aprendizado_preferencias_revert",
             response_model=schemas.AprendizadoPreferencias, responses=ESCREVER)
def preferencias_revert(perfil_id: UUID, body: RevertIn, actor: RequireHumanOwner,
                        db: DbSession,
                        conta_id: ContaQ = None) -> schemas.AprendizadoPreferencias:
    return preferencias.reverter(db, actor, perfil_id, conta_id, body)


# ---- análises da IA ----

@router.post(f"{P}/analises/estimativa", operation_id="aprendizado_analises_estimativa",
             response_model=schemas.AprendizadoEstimativa, responses=ESCREVER)
def analises_estimativa(perfil_id: UUID, body: schemas.AprendizadoEstimativaIn,
                        actor: RequireHumanOwner,
                        db: DbSession) -> schemas.AprendizadoEstimativa:
    return analise_ia.estimativa(db, perfil_id, body)


@router.post(f"{P}/analises", operation_id="aprendizado_analises_create",
             status_code=status.HTTP_202_ACCEPTED, response_model=schemas.AprendizadoAnaliseIa,
             responses=_errors(400, 401, 403, 404, 409, 503))
def analises_create(perfil_id: UUID, body: schemas.AprendizadoAnaliseIaIn,
                    actor: RequireHumanOwner, db: DbSession,
                    client: IaDep) -> schemas.AprendizadoAnaliseIa:
    return analise_ia.pedir(db, actor, perfil_id, body, client)


@router.get(f"{P}/analises", operation_id="aprendizado_analises_list",
            response_model=schemas.AprendizadoAnalisesList, responses=LER)
def analises_list(perfil_id: UUID, actor: RequireUser, db: DbSession,
                  cursor: str | None = None) -> schemas.AprendizadoAnalisesList:
    return analise_ia.listar(db, perfil_id, eh_dono(actor), cursor)


@router.get(f"{A}/analises/{{analise_id}}", operation_id="aprendizado_analises_get",
            response_model=schemas.AprendizadoAnaliseIa, responses=LER)
def analises_get(analise_id: UUID, actor: RequireUser,
                 db: DbSession) -> schemas.AprendizadoAnaliseIa:
    return analise_ia.obter(db, analise_id, eh_dono(actor))


@router.post(f"{A}/analises/{{analise_id}}/hipoteses/{{indice}}/recomendar",
             operation_id="aprendizado_hipotese_recomendar",
             status_code=status.HTTP_201_CREATED, response_model=schemas.AprendizadoDecisao,
             responses=ESCREVER)
def hipotese_recomendar(analise_id: UUID, indice: int,
                        body: schemas.AprendizadoHipoteseRecomendarIn,
                        actor: RequireHumanOwner, db: DbSession) -> schemas.AprendizadoDecisao:
    return analise_ia.recomendar(db, actor, analise_id, indice, body)


# ---- diagnóstico ----

@router.get(f"{P}/diagnostico", operation_id="aprendizado_diagnostico",
            response_model=schemas.AprendizadoDiagnostico, responses=LER)
def diagnostico_get(perfil_id: UUID, actor: RequireUser, db: DbSession,
                    conta_id: ContaQ = None, de: date | None = None,
                    ate: date | None = None) -> schemas.AprendizadoDiagnostico:
    return diagnostico.calcular(db, perfil_id, conta_id, de, ate)


@router.get(f"{A}/posts/{{video_id}}/diagnostico", operation_id="aprendizado_post_diagnostico",
            response_model=schemas.AprendizadoPostDiagnostico, responses=LER)
def post_diagnostico(video_id: UUID, actor: RequireUser,
                     db: DbSession) -> schemas.AprendizadoPostDiagnostico:
    return diagnostico.do_post(db, video_id)


@router.put(f"{A}/posts/{{video_id}}/conferencias/{{item}}",
            operation_id="aprendizado_conferencias_put",
            response_model=schemas.AprendizadoConferencia, responses=ESCREVER)
def conferencias_put(video_id: UUID, item: str, body: schemas.AprendizadoConferenciaPut,
                     actor: RequireHumanOwner, db: DbSession) -> schemas.AprendizadoConferencia:
    return conferencias.put(db, actor, video_id, item, body)
