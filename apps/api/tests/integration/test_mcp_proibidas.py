"""T039 (US3, FR-024/FR-025, SC-002; princípios I, II e VII): toda operação PROIBIDA chamada com
um token MCP (o maior escopo) é recusada com `somente_humano` e o evento, direto na API e pela
tool, sem mudar nada no banco."""

import uuid

import pytest
from mcp.shared.exceptions import MCPError
from sqlalchemy import func, select

from integration.mcp_helpers import bearer, com_mcp, criar_cliente, ligar
from integration.postagem_helpers import (  # noqa: F401
    add_destino,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
)
from sociman_api.auth.models import SecurityEvent
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.mcp import mapa

_OPS = {op["operationId"]: (m.upper(), path)
        for path, ops in app.openapi()["paths"].items() for m, op in ops.items()}
PROIBIDAS = sorted(mapa.PROIBIDAS)
# Casos nomeados dos princípios (precisam estar na lista).
PRINCIPIOS = {"destinos_aprovar", "agendamentos_create", "destinos_enviar_agora",
              "conexoes_iniciar", "canais_direito", "envios_enviar", "destinos_revert",
              "anotacoes_revert", "anotacoes_descartar"}


@pytest.fixture
def agente(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    cliente, token = criar_cliente(client, h, "Gestor", "propostas", limitePorMinuto=600)
    return cliente, token


def _contar(db, modelo, *where):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo).where(*where))


def test_principios_na_lista():
    assert PRINCIPIOS <= set(PROIBIDAS)


@pytest.mark.parametrize("op", PROIBIDAS)
def test_direto_na_api(client, agente, db, op):
    cliente, token = agente
    metodo, caminho = _OPS[op]
    url = caminho
    while "{" in url:
        ini, fim = url.index("{"), url.index("}")
        url = url[:ini] + str(uuid.uuid4()) + url[fim + 1:]
    versoes = _contar(db, EntityVersion)
    corpo = {"version": 1, "confirmarAviso": True, "habilitado": True}
    r = client.request(metodo, url, headers=bearer(token), json=corpo)
    assert r.status_code == 403, (op, r.status_code, r.text)
    assert r.json()["error"]["code"] == "somente_humano", op
    eventos = db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()
    assert [str(e.actor_mcp_client_id) for e in eventos] == [cliente["id"]], op
    assert eventos[0].details["rota"] == f"{metodo} {caminho}"
    assert _contar(db, EntityVersion) == versoes


def test_pela_tool_nao_existem(agente):
    _, token = agente

    async def todas(c):
        codigos = {}
        for op in PROIBIDAS:
            try:
                await c.call_tool(op, {})
                codigos[op] = "chamou"
            except MCPError as exc:
                codigos[op] = exc.code
        return codigos, {t.name for t in (await c.list_tools()).tools}

    codigos, listadas = com_mcp(token, todas)
    assert set(codigos.values()) == {-32602}
    assert not listadas & set(PROIBIDAS)


def test_destino_aprovar_real_nao_muda(client, dono, agente, db):  # noqa: F811
    """Com um destino de verdade: a recusa não aprova nada (I)."""
    _, h = dono
    _, token = agente
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"])
    corte = criar_corte(db, perfil["id"])
    destino = add_destino(client, h, corte.id, conta["id"])
    r = client.post(f"/api/destinos/{destino['id']}/aprovar", headers=bearer(token),
                    json={"version": destino["version"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    depois = client.get(f"/api/destinos/{destino['id']}", headers=h).json()["destino"]
    assert depois["estado"] == destino["estado"] and depois["version"] == destino["version"]
