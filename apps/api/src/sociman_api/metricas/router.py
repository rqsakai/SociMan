"""Rotas das métricas (contracts/http-api.md da 016).

Nomes neutros de rede: nenhum caminho nem `operationId` contém `tiktok`, `publish` ou `share`
(o guarda `test_nenhuma_rota_de_publicacao` continua sem exceção); a rede aparece só no corpo.
Prefixos: `metricas_*` para `/api/metricas/*` e `/api/contas/{id}/metricas`; `destinos_*` para
`/api/destinos/{id}/…`. Ligar, escolher, colar e desfazer vínculo são **H**
(`RequireHumanOwner`: dono e sessão humana). Não existe rota DELETE.
"""

from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from sociman_api.auth.deps import RequireHumanOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope
from sociman_api.metricas import consulta, export, schemas, vinculos
from sociman_api.metricas.models import VideoRede
from sociman_api.perfis.models import Conta
from sociman_api.perfis.schemas import VersionIn
from sociman_api.postagem import service as postagem
from sociman_api.publicacao import registro

router = APIRouter(prefix="/api")


def cliente_rede() -> Iterator[Any]:
    """Cliente HTTP da rede para validar o link colado (só leitura). Os testes trocam por um
    com a TikTok falsa."""
    client = registro.get_cliente()
    try:
        yield client
    finally:
        client.close()


Cliente = Annotated[Any, Depends(cliente_rede)]


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


# ---- vínculo do destino (US3) ----

@router.get("/destinos/{destino_id}/vinculo", operation_id="destinos_vinculo_get",
            response_model=schemas.Vinculo, responses=_errors(401, 403, 404))
def vinculo_get(destino_id: UUID, actor: RequireUser, db: DbSession) -> schemas.Vinculo:
    return vinculos.vinculo(db, postagem.get_destino_or_404(db, destino_id))


@router.post("/destinos/{destino_id}/vinculo", operation_id="destinos_vinculo_criar",
             response_model=schemas.VinculoOut,
             responses=_errors(400, 401, 403, 404, 409, 502))
def vinculo_criar(destino_id: UUID, body: schemas.VinculoIn, actor: RequireHumanOwner,
                  db: DbSession, client: Cliente) -> schemas.VinculoOut:
    destino = vinculos.ligar(db, actor, destino_id, body, client)
    return schemas.VinculoOut(destino=postagem.destino_out(db, destino),
                              vinculo=vinculos.vinculo(db, destino))


@router.post("/destinos/{destino_id}/vinculo/desfazer", operation_id="destinos_vinculo_desfazer",
             response_model=schemas.VinculoOut, responses=_errors(400, 401, 403, 404, 409))
def vinculo_desfazer(destino_id: UUID, body: VersionIn, actor: RequireHumanOwner,
                     db: DbSession) -> schemas.VinculoOut:
    destino = vinculos.desfazer(db, actor, destino_id, body.version)
    return schemas.VinculoOut(destino=postagem.destino_out(db, destino),
                              vinculo=vinculos.vinculo(db, destino))


# ---- métricas de conta e vídeos (US4) ----

ORIGENS = ("corte", "video_proprio", "fora", "anonima")
Ordem = Literal["views", "views24h", "views7d", "engajamento", "velocidade", "publicadoEm"]
Direcao = Literal["desc", "asc"]
Resolucao = Literal["auto", "hora", "dia"]


def _origens(valor: str | None) -> list[str] | None:
    if not valor:
        return None
    origens = [o.strip() for o in valor.split(",") if o.strip()]
    invalidas = [o for o in origens if o not in ORIGENS]
    if invalidas:
        raise ApiError(400, "validation_error",
                       f"origem: use {', '.join(ORIGENS)} (recebido: {', '.join(invalidas)})")
    return origens


def _video_or_404(db: DbSession, video_id: UUID) -> VideoRede:
    video = db.get(VideoRede, video_id)
    if video is None:
        raise ApiError(404, "not_found", "Vídeo não encontrado")
    return video


@router.get("/contas/{conta_id}/metricas", operation_id="metricas_conta",
            response_model=schemas.ContaMetricasOut, responses=_errors(400, 401, 403, 404))
def metricas_conta(conta_id: UUID, actor: RequireUser, db: DbSession,
                   de: date | None = None, ate: date | None = None,
                   resolucao: Resolucao = "auto") -> schemas.ContaMetricasOut:
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    return consulta.conta_metricas(db, conta, de, ate, resolucao)


@router.get("/metricas/videos", operation_id="metricas_videos_list",
            response_model=schemas.VideosList, responses=_errors(400, 401, 403))
def metricas_videos_list(
    actor: RequireUser, db: DbSession,
    perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
    conta_id: Annotated[UUID | None, Query(alias="contaId")] = None,
    origem: str | None = None, de: date | None = None, ate: date | None = None,
    ordem: Ordem = "views", direcao: Direcao = "desc", cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
) -> schemas.VideosList:
    return consulta.ranking(db, perfil_id=perfil_id, conta_id=conta_id, origens=_origens(origem),
                            de=de, ate=ate, ordem=ordem, direcao=direcao, cursor=cursor,
                            limite=limite)


@router.get("/metricas/videos/{video_id}", operation_id="metricas_videos_get",
            response_model=schemas.VideoDetalhe, responses=_errors(401, 403, 404))
def metricas_videos_get(video_id: UUID, actor: RequireUser,
                        db: DbSession) -> schemas.VideoDetalhe:
    return consulta.detalhe(db, _video_or_404(db, video_id))


@router.get("/destinos/{destino_id}/metricas", operation_id="destinos_metricas",
            response_model=schemas.DestinoMetricasOut, responses=_errors(401, 403, 404))
def destinos_metricas(destino_id: UUID, actor: RequireUser,
                      db: DbSession) -> schemas.DestinoMetricasOut:
    destino = postagem.get_destino_or_404(db, destino_id)
    video = vinculos.video_do_destino(db, destino.id)
    return schemas.DestinoMetricasOut(
        vinculo=vinculos.vinculo(db, destino),
        video=consulta.detalhe(db, video) if video is not None else None)


# ---- exportação (US5) ----
# Só o dono, pela interface (sessão humana): o dataset sai inteiro, e nenhum agente o baixa.

@router.get("/metricas/export", operation_id="metricas_export",
            response_class=StreamingResponse,
            responses={200: {"content": {"application/zip": {}},
                             "description": "ZIP com o dataset"},
                       **_errors(400, 401, 403, 503, 507)})
def metricas_export(
    actor: RequireHumanOwner, db: DbSession,
    formato: Literal["csv", "jsonl"] = "csv", de: date | None = None, ate: date | None = None,
    perfil_id: Annotated[UUID | None, Query(alias="perfilId")] = None,
    conta_id: Annotated[UUID | None, Query(alias="contaId")] = None,
    incluir_anonimas: Annotated[bool, Query(alias="incluirAnonimas")] = False,
) -> StreamingResponse:
    de, ate = export.validar_periodo(de, ate)
    filtro = export.Filtro(formato=formato, de=de, ate=ate, perfil_id=perfil_id,
                           conta_id=conta_id, incluir_anonimas=incluir_anonimas)
    arquivo = export.exportar(db, filtro)
    nome = export.nome_arquivo(de, ate)
    return StreamingResponse(export.pedacos(arquivo), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{nome}"'})
