"""Erros da API no envelope {"error": {"code", "message"}} (contracts/http-api.md)."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None  # ex.: `font_in_use` → {"fields": ["hook.fonte"]}


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None,
                 details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers
        self.details = details


def error_response(status: int, code: str, message: str, headers: dict[str, str] | None = None,
                   details: dict[str, Any] | None = None):
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse({"error": body}, status_code=status, headers=headers)


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Dados inválidos"
    first = errors[0]
    field = ".".join(str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path"))
    msg = first.get("msg", "inválido")
    return f"{field}: {msg}" if field else msg


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.headers, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return error_response(400, "validation_error", _validation_message(exc))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        log.exception("erro inesperado em %s %s", request.method, request.url.path)
        return error_response(500, "internal_error", "Erro interno")


def install_openapi_error_contract(app: FastAPI) -> None:
    """Troca o 422 automático do FastAPI pelo 400 `validation_error` que a API de fato devolve.

    Sem isso o OpenAPI (fonte do contrato, princípio IV) anunciaria um HTTPValidationError que
    nunca acontece, e o cliente gerado ficaria errado.
    """
    from fastapi.openapi.utils import get_openapi

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        envelope_ref = {"$ref": "#/components/schemas/ErrorEnvelope"}
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.setdefault("ErrorBody", ErrorBody.model_json_schema())
        components.setdefault("ErrorEnvelope", {
            "type": "object", "title": "ErrorEnvelope", "required": ["error"],
            "properties": {"error": {"$ref": "#/components/schemas/ErrorBody"}},
        })
        for path in schema.get("paths", {}).values():
            for op in path.values():
                responses = op.get("responses", {})
                if responses.pop("422", None) is not None:
                    responses.setdefault("400", {
                        "description": "Dados inválidos (validation_error)",
                        "content": {"application/json": {"schema": envelope_ref}},
                    })
        components.pop("HTTPValidationError", None)
        components.pop("ValidationError", None)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
