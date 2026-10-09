"""T064 (SC-006): leitura comum pelo `/mcp` em até 1 s e o portão em menos de 5 ms em média."""

import time

from integration.mcp_helpers import bearer, com_mcp, criar_cliente, ligar
from integration.postagem_helpers import criar_perfil, dono  # noqa: F401
from sociman_api.mcp import portao


def test_leitura_e_portao(client, dono, mcp_habilitado, monkeypatch):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    perfis = [criar_perfil(client, h, f"Perfil {i}") for i in range(20)]
    _, token = criar_cliente(client, h, "Analista", "leitura", limitePorMinuto=600)

    async def leituras(c):
        await c.list_tools()  # aquece o catálogo (gerado do OpenAPI uma vez por processo)
        await c.call_tool("perfis_list", {})
        tempos = []
        for nome, args in (("perfis_get", {"perfil_id": perfis[0]["id"]}),
                           ("conteudos_list", {}), ("perfis_list", {})):
            inicio = time.monotonic()
            r = await c.call_tool(nome, args)
            tempos.append(time.monotonic() - inicio)
            assert not r.is_error, nome
        return tempos

    tempos = com_mcp(token, leituras)
    assert max(tempos) <= 1.0, tempos

    gasto: list[float] = []
    original = portao._decidir

    def cronometrado(request, tok):
        inicio = time.perf_counter()
        try:
            return original(request, tok)
        finally:
            gasto.append(time.perf_counter() - inicio)

    monkeypatch.setattr(portao, "_decidir", cronometrado)
    for _ in range(100):
        assert client.get(f"/api/perfis/{perfis[0]['id']}", headers=bearer(token)).status_code == 200
    assert len(gasto) == 100
    assert sum(gasto) / len(gasto) < 0.005, f"portão: {1000 * sum(gasto) / len(gasto):.2f} ms"
