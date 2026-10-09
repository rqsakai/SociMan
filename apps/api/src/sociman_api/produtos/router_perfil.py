"""Rotas dos produtos do perfil (contracts/api.md da 012, "Produtos do perfil"). Ler: dono,
membro e cliente MCP pelo mapa (`RequireUser`); criar: só humano (`RequireHuman`). Não existe
rota DELETE.

Spec 029: as duas ficam obsoletas (`deprecated`), com o mesmo comportamento das rotas da agência
(`/api/produtos`) com `perfilId` = o perfil do caminho."""

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile

from sociman_api.auth.deps import RequireHuman, RequireUser
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope
from sociman_api.produtos import schemas
from sociman_api.produtos import service as svc
from sociman_api.produtos.models import ProdutoStatus

router = APIRouter(prefix="/api/perfis")

Db = DbSession
_URL = re.compile(r"^https://\S+$")


def _errors(*statuses: int) -> dict[int | str, dict]:
    return {status: {"model": ErrorEnvelope} for status in statuses}


@router.get("/{perfil_id}/produtos", operation_id="produtos_listar",
            response_model=schemas.ProdutosLista, responses=_errors(400, 401, 403, 404),
            deprecated=True)
def listar(
    perfil_id: UUID, actor: RequireUser, db: Db,
    status: Annotated[list[ProdutoStatus] | None, Query(description="Estados (OU)")] = None,
    arquivados: Annotated[schemas.ArquivadosFiltro, Query()] = "false",
    q: Annotated[str | None, Query(max_length=100, description="Nome interno ou comercial")]
    = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=svc.LIMITE_MAX)] = svc.LIMITE_PADRAO,
) -> schemas.ProdutosLista:
    return svc.listar(db, perfil_id, status=status or (), arquivados=arquivados, q=q,
                      cursor=cursor, limit=limit)


@router.post("/{perfil_id}/produtos", operation_id="produtos_criar", status_code=201,
             response_model=schemas.Produto,
             responses=_errors(400, 401, 403, 404, 409, 503, 507), deprecated=True)
def criar(
    perfil_id: UUID, actor: RequireHuman, db: Db,
    name: Annotated[str, Form(max_length=200)],
    obs: Annotated[str | None, Form(max_length=2000)] = None,
    url_loja: Annotated[str | None, Form(alias="urlLoja", max_length=500)] = None,
    fotos: Annotated[list[UploadFile] | None,
                     File(description="1 a 6 fotos (PNG, JPG ou WebP, ≥ 512×512, até 20 MB)")]
    = None,
) -> schemas.Produto:
    nome, url = campos_criar(name, url_loja)
    produto = svc.criar(db, actor, perfil_id, nome, (obs or "").strip(), url,
                        [f.file for f in fotos or []])
    return svc.produto_out(db, produto)


def campos_criar(name: str, url_loja: str | None) -> tuple[str, str | None]:
    """O nome (1 a 80) e o link https da loja do multipart de criação."""
    nome = name.strip()
    if not 1 <= len(nome) <= 80:
        raise schemas.invalid("name", "de 1 a 80 caracteres")
    url = (url_loja or "").strip() or None
    if url is not None and not _URL.match(url):
        raise schemas.invalid("url_loja", "use um link https://")
    return nome, url
