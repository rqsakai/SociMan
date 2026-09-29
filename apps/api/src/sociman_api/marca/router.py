"""Rotas do kit de marca (T012/T018, contracts/http-api.md "Kit"): dono e membro
(`RequireUser`); a reversão é só do dono (`RequireOwner`). Não existe rota DELETE.
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from sociman_api.auth.deps import RequireOwner, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ApiError, ErrorEnvelope
from sociman_api.marca import service_kit as service
from sociman_api.marca.schemas import KitExport, KitGet, KitIn, KitOut
from sociman_api.marca.tokens import error_message
from sociman_api.perfis.schemas import RevertIn, VersionsList

router = APIRouter(prefix="/api/perfis")

Db = DbSession


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


class _InvalidKitRoute(APIRoute):
    """Erro de forma no corpo do kit vira 400 `invalid_kit` com o campo (`hook.cor_fundo: …`),
    em vez do `validation_error` genérico; o OpenAPI continua com o schema tipado."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                body = [e for e in exc.errors() if tuple(e.get("loc", ()))[:1] == ("body",)]
                if not body:
                    raise
                message = error_message(body[0])
                field = message.split(": ", 1)[0] if ": " in message else ""
                raise ApiError(400, "invalid_kit", message,
                               details={"field": field} if field else None) from exc

        return route


@router.get("/{perfil_id}/kit", operation_id="kit_get", response_model=KitGet,
            responses=_errors(401, 403, 404))
def get_kit(perfil_id: UUID, actor: RequireUser, db: Db) -> KitGet:
    return service.get_kit(db, perfil_id)


def put_kit(perfil_id: UUID, body: KitIn, actor: RequireUser, db: Db) -> KitOut:
    return KitOut(kit=service.put_kit(db, actor, perfil_id, body))


# add_api_route: o decorator `put` não aceita `route_class_override`.
router.add_api_route(
    "/{perfil_id}/kit", put_kit, methods=["PUT"], operation_id="kit_update",
    response_model=KitOut, responses=_errors(400, 401, 403, 404, 409),
    route_class_override=_InvalidKitRoute,
)


@router.get("/{perfil_id}/kit/versions", operation_id="kit_versions",
            response_model=VersionsList, responses=_errors(401, 403, 404))
def kit_versions(perfil_id: UUID, actor: RequireUser, db: Db) -> VersionsList:
    return service.kit_versions(db, perfil_id)


@router.post("/{perfil_id}/kit/revert", operation_id="kit_revert", response_model=KitOut,
             responses=_errors(400, 401, 403, 404, 409))
def revert_kit(perfil_id: UUID, body: RevertIn, actor: RequireOwner, db: Db) -> KitOut:
    return KitOut(kit=service.revert_kit(db, actor, perfil_id, body.version, body.to_version))


@router.get("/{perfil_id}/kit/export", operation_id="kit_export", response_model=KitExport,
            responses=_errors(401, 403, 404))
def export_kit(
    perfil_id: UUID, actor: RequireUser, db: Db,
    download: Annotated[bool, Query(description="Baixar como arquivo .json")] = False,
) -> Any:
    doc, filename = service.export_kit(db, perfil_id)
    if not download:
        return doc
    return JSONResponse(
        doc.model_dump(mode="json", by_alias=True),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
