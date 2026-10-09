"""T064/T065 (US6): o cliente MCP lista e chama as tools de leitura do mercado e da coleta e é
recusado em qualquer escrita (`escopo_mcp`/`somente_humano`); o mapa (fonte do `mcp-tools.json`)
tem as leituras e nenhuma escrita; "Adotar no catálogo" sem a 012 nesta branca → 409
`passo_indisponivel`, e pelo MCP → recusado."""

from integration.coleta_helpers import coletor, dono, ligado  # noqa: F401
from integration.mcp_helpers import bearer as bearer_mcp
from integration.mcp_helpers import com_mcp, criar_cliente, ligar
from integration.postagem_helpers import criar_perfil
from sociman_api.mcp import mapa

LEITURAS = {"mercado_produtos_listar", "mercado_produtos_detalhe", "mercado_produtos_serie",
            "mercado_produtos_fichas", "mercado_produtos_rankings", "mercado_produtos_videos",
            "mercado_produtos_avaliacoes", "mercado_rankings_listar", "mercado_lojas_listar",
            "mercado_lojas_detalhe", "mercado_categorias_listar", "mercado_resumo",
            "mercado_interesses_listar", "mercado_interesses_listar_todos",
            "mercado_perfil_config_get", "coleta_estado"}
ESCRITAS = {"mercado_produtos_adotar", "mercado_interesses_criar", "mercado_interesses_editar",
            "mercado_interesses_revert", "mercado_perfil_config_put", "mercado_perfil_config_revert",
            "mercado_lojas_seguir", "mercado_lojas_deixar_de_seguir", "coleta_clientes_criar",
            "coleta_config_put", "coleta_config_aceitar_risco", "coleta_itens_enviar", "coleta_fila",
            "coleta_coletas_abrir"}


def test_mapa_tem_as_leituras_e_nenhuma_escrita():
    assert LEITURAS <= set(mapa.TOOLS)
    assert not (ESCRITAS & set(mapa.TOOLS))
    assert ESCRITAS - {"coleta_itens_enviar", "coleta_fila", "coleta_coletas_abrir"} <= set(mapa.PROIBIDAS)
    assert {"coleta_itens_enviar", "coleta_fila", "coleta_coletas_abrir"} <= set(mapa.FORA)


def test_mcp_le_o_cockpit_e_e_recusado_nas_escritas(client, db, ligado, coletor, mcp_habilitado):  # noqa: F811
    perfil = criar_perfil(client, ligado)
    coletor.semear(db, produtos=2, dias=2)
    db.commit()
    ligar(client, ligado, mcp_habilitado)
    _, token = criar_cliente(client, ligado, "Analista", "leitura")

    async def fluxo(c):
        tools = {t.name for t in (await c.list_tools()).tools}
        lista = await c.call_tool("mercado_produtos_listar", {})
        resumo = await c.call_tool("mercado_resumo", {})
        estado = await c.call_tool("coleta_estado", {})
        cats = await c.call_tool("mercado_categorias_listar", {})
        lojas = await c.call_tool("mercado_lojas_listar", {})
        rankings = await c.call_tool("mercado_rankings_listar", {})
        inter = await c.call_tool("mercado_interesses_listar", {"perfil_id": perfil["id"]})
        return tools, lista, resumo, estado, cats, lojas, rankings, inter

    tools, lista, resumo, estado, cats, lojas, rankings, inter = com_mcp(token, fluxo)
    assert LEITURAS <= tools
    assert not (ESCRITAS & tools)
    assert not lista.is_error and lista.structured_content["total"] == 2
    assert not resumo.is_error and resumo.structured_content["estadoColeta"]["habilitada"] is True
    assert not estado.is_error and estado.structured_content["situacao"]
    assert not cats.is_error and len(cats.structured_content["itens"]) >= 3
    assert not lojas.is_error and lojas.structured_content["total"] == 1
    assert not rankings.is_error and len(rankings.structured_content["fotos"]) == 2
    assert not inter.is_error and inter.structured_content["total"] == 0
    # Escritas pela API direta com a credencial MCP: proibidas (somente_humano) ou fora de escopo.
    h = bearer_mcp(token)
    r = client.post(f"/api/perfis/{perfil['id']}/mercado/interesses", headers=h,
                    json={"url": "https://exemplo.test/shop/pdp/x/7399999999999999999"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.post("/api/coleta/clientes", headers=h, json={"nome": "x", "mercado": "BR"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.get("/api/coleta/fila", headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "escopo_mcp"
    r = client.post(f"/api/mercado/produtos/{lista.structured_content['itens'][0]['id']}/adotar",
                    headers=h, json={"perfilId": perfil["id"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"


def test_adotar_sem_a_012_e_passo_indisponivel(client, db, ligado, coletor):  # noqa: F811
    perfil = criar_perfil(client, ligado)
    coletor.semear(db, produtos=1, dias=1, ranking=False)
    db.commit()
    pid = client.get("/api/mercado/produtos", headers=ligado).json()["itens"][0]["id"]
    r = client.post(f"/api/mercado/produtos/{pid}/adotar", headers=ligado,
                    json={"perfilId": perfil["id"]})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "passo_indisponivel"
    r = client.post("/api/mercado/produtos/00000000-0000-0000-0000-000000000001/adotar",
                    headers=ligado, json={"perfilId": perfil["id"]})
    assert r.status_code == 404
    det = client.get(f"/api/mercado/produtos/{pid}", headers=ligado).json()
    assert det["adotadoEm"] == []
