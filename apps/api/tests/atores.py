"""Atores de teste não humanos (spec 009): desde a 0014, um `mcp_client` precisa apontar para um
cliente MCP de verdade (CHECK `ck_*_ator`). `ator_fake("mcp_client", user)` cria (uma vez por
teste, idempotente) o "Cliente MCP de teste" e devolve o ator com o `mcp_client_id` dele."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from sociman_api.auth.deps import Actor
from sociman_api.db import get_engine

MCP_TESTE_ID = uuid.UUID("00000000-0000-4000-8000-000000000009")


def garantir_cliente_mcp() -> uuid.UUID:
    with get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO mcp_clientes (id, nome, nome_normalizado, escopo, token_id, token_hash, "
            "token_emitido_em) VALUES (:id, 'Cliente MCP de teste', 'cliente mcp de teste', "
            "'propostas', 'testeaaa', decode(repeat('00', 32), 'hex'), :agora) "
            "ON CONFLICT (id) DO NOTHING"), {"id": MCP_TESTE_ID, "agora": datetime.now(UTC)})
    return MCP_TESTE_ID


def ator_fake(kind: str, user=None) -> Actor:
    if kind == "mcp_client":
        return Actor(kind=kind, user_id=getattr(user, "id", None), user=user,
                     mcp_client_id=garantir_cliente_mcp(), mcp_escopo="propostas")
    return Actor(kind=kind, user_id=getattr(user, "id", None), user=user)
