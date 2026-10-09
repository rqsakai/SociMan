"""T032 (US2, FR-014/FR-015/FR-017): cada tool de leitura do mapa devolve o mesmo que a rota da
API para um membro, sem gravar nada no domínio e sem segredo."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from integration.envios_helpers import criar_canal, criar_video, selecionado
from integration.mcp_helpers import com_mcp, criar_cliente, ligar
from integration.postagem_helpers import (  # noqa: F401
    add_destino,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.canais.models import CanalPerfil
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.mcp import ferramentas, mapa

LEITURA = sorted(n for n, t in mapa.TOOLS.items() if t.escopo == "leitura")
# Mudam entre duas chamadas iguais: links assinados com validade e o `generatedAt` do kit
# exportado (comparados sem esses campos).
VOLATEIS = {"midia_links": ("items",), "kit_export": ("generatedAt",),
            # spec 026: o `contexto` traz `geradoEm` (relógio da leitura)
            "mercado_produtos_listar": ("contexto",), "mercado_resumo": ("contexto",),
            "mercado_rankings_listar": ("contexto",), "mercado_lojas_listar": ("contexto",),
            "mercado_produtos_detalhe": ("contexto",), "mercado_lojas_detalhe": ("contexto",)}


@pytest.fixture
def cenario(client, dono, membro, db, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"])
    corte = criar_corte(db, perfil["id"])
    destino = add_destino(client, h, corte.id, conta["id"])
    canal = criar_canal()
    db.add(CanalPerfil(canal_id=canal.id, perfil_id=uuid.UUID(perfil["id"])))
    db.commit()
    video = criar_video(canal)
    envio = selecionado(client, h, perfil["id"], video)
    anotacao = client.post("/api/anotacoes", headers=h, json={
        "alvoTipo": "perfil", "alvoId": perfil["id"], "texto": "nota do dono"}).json()["anotacao"]
    _, token = criar_cliente(client, h, "Analista", "leitura", limitePorMinuto=600)
    ids = {"perfil_id": perfil["id"], "conta_id": conta["id"], "corte_id": str(corte.id),
           "conteudo_id": str(corte.id), "destino_id": destino["id"], "canal_id": str(canal.id),
           "video_id": str(video.id), "envio_id": envio["id"], "anotacao_id": anotacao["id"],
           "tipo": "postagem.descricao"}
    return token, ids, membro[1]


def _args(op: ferramentas.Operacao, ids: dict[str, str]) -> dict:
    args = {p: ids.get(p, str(uuid.uuid4())) for p in op.path_params}
    if op.nome == "assets_images":
        args["tipo"] = ["fundo"]
    if op.nome == "postagens_calendario":
        hoje = datetime.now(UTC).date()
        args |= {"de": hoje.isoformat(), "ate": (hoje + timedelta(days=7)).isoformat()}
    if op.nome == "midia_links":
        args["items"] = [{"kind": "corte", "id": ids["corte_id"]}]
    return args


def _direto(client, h, op: ferramentas.Operacao, args: dict):
    caminho = op.caminho
    for p in op.path_params:
        caminho = caminho.replace("{" + p + "}", args[p])
    query = {k: args[k] for k in op.query_params if k in args}
    if op.limite_param:
        query.setdefault(op.limite_param,
                         op.definicao["inputSchema"]["properties"][op.limite_param]["default"])
    corpo = {k: args[k] for k in op.corpo if k in args} if op.corpo else None
    return client.request(op.metodo, caminho, params=query, json=corpo, headers=h)


def test_cada_leitura_igual_a_do_membro(client, cenario, db):
    token, ids, hm = cenario
    cat = ferramentas.catalogo(app)
    # spec 010: +8 leituras de cena; spec 013: +2 da agência; spec 022: +1 (público);
    # spec 023: +7 do aprendizado; spec 026: +16 (coleta_estado e as leituras do mercado)
    assert len(LEITURA) == 62 + 8 + 2 + 1 + 7 + 16
    chamadas = {nome: _args(cat[nome], ids) for nome in LEITURA}

    async def todas(c):
        return {nome: await c.call_tool(nome, args) for nome, args in chamadas.items()}

    versoes_antes = db.scalar(select(func.count()).select_from(EntityVersion))
    via_tool = com_mcp(token, todas)
    assert db.scalar(select(func.count()).select_from(EntityVersion)) == versoes_antes
    falhas, ok = [], 0
    for nome in LEITURA:
        api = _direto(client, hm, cat[nome], chamadas[nome])
        r = via_tool[nome]
        if api.status_code < 400:
            ok += 1
            if r.is_error:
                falhas.append(f"{nome}: tool deu erro {r.content[0].text}")
            else:
                ignorar = VOLATEIS.get(nome, ())
                limpo = {k: v for k, v in r.structured_content.items() if k not in ignorar}
                if limpo != {k: v for k, v in api.json().items() if k not in ignorar}:
                    falhas.append(f"{nome}: diverge do membro")
        elif not r.is_error or r.structured_content["code"] != api.json()["error"]["code"]:
            falhas.append(f"{nome}: API {api.status_code}, tool {r.structured_content}")
        texto = json.dumps(r.structured_content, default=str)
        assert "smcp_" not in texto and "@teste.local" not in texto, nome
    assert not falhas, falhas
    assert ok >= 40  # o cenário cobre a maioria das leituras com sucesso


def test_funil_sem_custo_e_midia_por_link(cenario):
    token, ids, _ = cenario

    async def chamar(c):
        return (await c.call_tool("analytics_funil", {}),
                await c.call_tool("midia_links",
                                  {"items": [{"kind": "corte", "id": ids["corte_id"]}]}),
                await c.call_tool("kit_export", {"perfil_id": ids["perfil_id"]}))

    funil, midia, kit = com_mcp(token, chamar)
    texto = json.dumps(funil.structured_content)
    assert '"custo' not in texto or all(v is None for k, v in _pares(funil.structured_content)
                                        if k.lower().startswith("custo"))
    if not midia.is_error:
        for item in midia.structured_content["items"]:
            assert item["url"].startswith("/api/midia/") and item["expiresAt"]
    assert not kit.is_error


def _pares(valor, chave=""):
    if isinstance(valor, dict):
        for k, v in valor.items():
            yield k, v
            yield from _pares(v, k)
    elif isinstance(valor, list):
        for v in valor:
            yield from _pares(v, chave)


def test_integracoes_sem_valores(cenario):
    token, _, _ = cenario

    async def chamar(c):
        return await c.call_tool("integracoes_get", {})

    r = com_mcp(token, chamar)
    assert set(r.structured_content) == {"youtube", "openshorts", "claude", "cotaYoutube", "coleta",
                                         "geracao"}  # spec 021: só estados, sem valores
