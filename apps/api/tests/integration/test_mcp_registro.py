"""T054 (US5, R8, FR-028/FR-029, SC-007): o registro só de inserção de toda chamada MCP."""

import pytest
from mcp.shared.exceptions import MCPError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from integration.mcp_helpers import INIT, bearer, com_mcp, criar_cliente, ligar, post_mcp
from integration.postagem_helpers import criar_perfil, dono, membro  # noqa: F401
from sociman_api.mcp import registro
from sociman_api.mcp.models import McpChamada


@pytest.fixture
def base(client, dono, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    perfil = criar_perfil(client, h)
    cliente, token = criar_cliente(client, h, "Caçador", "propostas")
    return h, perfil, cliente, token


def _linhas(db):
    db.expire_all()
    return db.scalars(select(McpChamada).order_by(McpChamada.id)).all()


def test_cada_resultado_vira_uma_linha(client, base, db):
    _, perfil, cliente, token = base
    t = bearer(token)
    client.get("/api/perfis", headers=t)  # ok
    client.get("/api/perfis/00000000-0000-0000-0000-000000000000", headers=t)  # erro 404
    client.get("/api/users", headers=t)  # recusada (somente_humano)
    r = client.post("/api/anotacoes", headers=t, json={
        "alvoTipo": "perfil", "alvoId": perfil["id"], "texto": "nota"})  # escrita ok
    linhas = _linhas(db)
    assert [(c.tool, c.resultado, c.status_http, c.codigo_erro) for c in linhas] == [
        ("perfis_list", "ok", 200, None),
        ("perfis_get", "erro", 404, "not_found"),
        ("users_list", "recusada", 403, "somente_humano"),
        ("anotacoes_create", "ok", 201, None),
    ]
    assert all(str(c.cliente_id) == cliente["id"] and c.via == "api" for c in linhas)
    escrita = linhas[-1]
    assert escrita.escrita and escrita.entidade_tipo == "anotacao"
    assert str(escrita.entidade_id) == r.json()["anotacao"]["id"]
    assert escrita.rota == "POST /api/anotacoes" and escrita.duracao_ms >= 0
    assert linhas[0].rota == "GET /api/perfis" and not linhas[0].escrita


def test_limite_e_via_mcp(client, base, db):
    h, _, cliente, token = base
    r = client.patch(f"/api/mcp/clientes/{cliente['id']}", headers=h,
                     json={"version": cliente["version"], "limitePorMinuto": 1})
    assert r.status_code == 200

    async def duas(c):
        return [await c.call_tool("perfis_list", {}), await c.call_tool("perfis_list", {})]

    _, segunda = com_mcp(token, duas)
    assert segunda.is_error and segunda.structured_content["detalhes"]["retryAfterS"] > 0
    linhas = _linhas(db)
    assert [(c.via, c.resultado) for c in linhas] == [("mcp", "ok"), ("mcp", "limite")]


def test_nao_autenticado_com_e_sem_cliente(client, base, db):
    _, _, cliente, token = base
    errado = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert client.get("/api/perfis", headers=bearer(errado)).status_code == 401
    assert client.get("/api/perfis",
                      headers=bearer("smcp_zzzzzzzz_" + "x" * 43)).status_code == 401
    assert post_mcp(client, errado, INIT).status_code == 401
    linhas = _linhas(db)
    assert [(str(c.cliente_id) if c.cliente_id else None, c.resultado) for c in linhas] == [
        (cliente["id"], "nao_autenticado"), (None, "nao_autenticado"),
        (cliente["id"], "nao_autenticado")]
    eventos = client.get("/api/security-events?type=mcp_auth_falhou", headers=base[0]).json()
    assert len(eventos["items"]) == 2


def test_resumo_mascarado_e_cortado():
    args = {"token": "abc", "senha": "x", "Authorization": "y", "texto": "z" * 500,
            "nota": "use smcp_abcdefgh_" + "A" * 43, "lista": ["a" * 300]}
    r = registro.resumo_args(args)
    assert r["token"] == r["senha"] == r["Authorization"] == "***"
    assert len(r["texto"]) == 201 and r["lista"][0].endswith("…")
    assert "smcp_abcdefgh" not in str(r)
    grande = registro.resumo_args({f"k{i}": "v" * 190 for i in range(40)})
    assert len(str(grande).encode()) <= 2400 and grande["_truncado"] is True


def test_args_sem_token_no_registro(client, base, db):
    _, perfil, _, token = base
    client.post("/api/anotacoes", headers=bearer(token), json={
        "alvoTipo": "perfil", "alvoId": perfil["id"], "texto": f"vazou {token}?"})
    assert token not in str(_linhas(db)[0].args_resumo)
    assert "smcp_***" in _linhas(db)[0].args_resumo["texto"]


def test_so_insercao(client, base, db):
    client.get("/api/perfis", headers=bearer(base[3]))
    for sql in ("UPDATE mcp_chamadas SET tool = 'x'", "DELETE FROM mcp_chamadas"):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
        db.rollback()


def test_recusa_gravada_mesmo_com_rollback(client, base, db):
    """A recusa do portão faz a requisição falhar (rollback), mas a linha fica."""
    _, _, _, token = base
    client.post("/api/destinos/00000000-0000-0000-0000-000000000000/aprovar",
                headers=bearer(token), json={"version": 1})
    assert [c.resultado for c in _linhas(db)] == ["recusada"]


def test_interruptor_e_tool_desconhecida_no_registro(client, base, db, mcp_habilitado):
    _, _, _, token = base

    async def chamar(c):
        with pytest.raises(MCPError):  # erro de protocolo esperado
            await c.call_tool("destinos_aprovar", {})

    com_mcp(token, chamar)
    mcp_habilitado(False)
    assert post_mcp(client, token, INIT).status_code == 503
    linhas = _linhas(db)
    assert [(c.tool, c.resultado, c.codigo_erro) for c in linhas] == [
        ("destinos_aprovar", "recusada", "tool_desconhecida"),
        ("(protocolo)", "recusada", "mcp_desligado")]


def test_lista_do_registro(client, base, db, membro):  # noqa: F811
    h, _, cliente, token = base
    _, outro = criar_cliente(client, h, "Analista", "leitura")
    for _ in range(3):
        client.get("/api/perfis", headers=bearer(token))
    client.get("/api/users", headers=bearer(outro))
    r = client.get(f"/api/mcp/chamadas?clienteId={cliente['id']}&limit=2", headers=h).json()
    assert len(r["chamadas"]) == 2 and r["nextCursor"]
    assert r["chamadas"][0]["cliente"] == {"id": cliente["id"], "nome": "Caçador"}
    r2 = client.get(f"/api/mcp/chamadas?clienteId={cliente['id']}&cursor={r['nextCursor']}",
                    headers=h).json()
    assert len(r2["chamadas"]) == 1
    r = client.get("/api/mcp/chamadas?resultado=recusada", headers=h).json()
    assert [c["tool"] for c in r["chamadas"]] == ["users_list"]
    lista = {c["nome"]: c for c in client.get("/api/mcp/clientes", headers=h).json()["clientes"]}
    assert lista["Caçador"]["uso24h"] == {"chamadas": 3, "recusas": 0, "escritas": 0}
    assert lista["Analista"]["uso24h"]["recusas"] == 1
    assert client.get("/api/mcp/chamadas", headers=membro[1]).status_code == 403
