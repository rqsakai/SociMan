"""T055 (US4): interesses e configuração de mercado do perfil pela API: criar por link (produto
novo no lago), duplicado → 409, membro pausa/encerra/segue loja, MCP → `somente_humano`, revert
só dono, `categorias_maximo`, config só dono, histórico e `version_conflict`."""

import uuid

from sqlalchemy import select, text

from integration.coleta_helpers import (  # noqa: F401
    coletor,
    dono,
    ligado,
    membro,
)
from integration.mcp_helpers import bearer as bearer_mcp
from integration.mcp_helpers import criar_cliente, ligar
from integration.postagem_helpers import criar_perfil
from sociman_api.mercado.models import Calor, Loja, Produto

LINK = "https://www.exemplo.test/shop/pdp/legging-x/7399999999999999999?region=BR&utm=x"


def _url(perfil_id: str) -> str:
    return f"/api/perfis/{perfil_id}/mercado"


def test_acompanhar_por_link_cria_produto_do_lago_e_duplicado_409(client, db, ligado):  # noqa: F811
    perfil = criar_perfil(client, ligado)
    r = client.post(f"{_url(perfil['id'])}/interesses", headers=ligado,
                    json={"url": LINK, "nota": "visto no vídeo da Bia"})
    assert r.status_code == 201, r.text
    i = r.json()
    assert i["origem"] == "manual" and i["situacao"] == "ativo" and i["todosOsPerfis"] is False
    assert i["motivo"]["url"].endswith("/7399999999999999999") and "utm" not in i["motivo"]["url"]
    assert i["produto"]["redeProdutoId"] == "7399999999999999999"
    assert i["produto"]["estado"] == "coletando"  # sem foto ainda
    produto = db.scalar(select(Produto).where(Produto.rede_produto_id == "7399999999999999999"))
    assert produto is not None and produto.calor == Calor.quente and produto.fotos_por_dia == 2
    assert produto.proxima_coleta_em is not None and produto.fonte_descoberta.value == "manual"
    # De novo → 409 com o id do interesse vivo.
    r = client.post(f"{_url(perfil['id'])}/interesses", headers=ligado, json={"url": LINK})
    assert r.status_code == 409 and r.json()["error"]["code"] == "interesse_duplicado"
    assert r.json()["error"]["details"]["interesseId"] == i["id"]
    # Link sem produto → 400.
    r = client.post(f"{_url(perfil['id'])}/interesses", headers=ligado,
                    json={"url": "https://www.exemplo.test/@alguem"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "link_invalido"
    # Host fora do domínio configurado (MERCADO_URL_PUBLICA) ou sem https: o coletor nunca abre
    # URL que não seja da rede → 400 (revisão de segurança 2026-10-09).
    for url in ("https://malicioso.test/shop/pdp/x/7399999999999999998",
                "http://exemplo.test/shop/pdp/x/7399999999999999998",
                "https://exemplo.test.evil.com/shop/pdp/x/7399999999999999998"):
        r = client.post(f"{_url(perfil['id'])}/interesses", headers=ligado, json={"url": url})
        assert r.status_code == 400 and r.json()["error"]["code"] == "link_invalido", url
    # Nem link nem produto → 400.
    r = client.post(f"{_url(perfil['id'])}/interesses", headers=ligado, json={"nota": "x"})
    assert r.status_code == 400
    # A lista do perfil traz o interesse com o cartão.
    lista = client.get(f"{_url(perfil['id'])}/interesses", headers=ligado).json()
    assert lista["total"] == 1 and lista["itens"][0]["id"] == i["id"]
    # Histórico: `created` pelo dono.
    vs = client.get(f"/api/mercado/interesses/{i['id']}/versions", headers=ligado).json()["items"]
    assert [v["action"] for v in vs] == ["created"] and vs[0]["autor"]["tipo"] == "usuario"


def test_membro_pausa_reativa_encerra_e_segue_loja(client, db, ligado, membro, coletor):  # noqa: F811
    _, hm = membro
    perfil = criar_perfil(client, ligado)
    coletor.semear(db, produtos=1, dias=1, ranking=False)
    pid = db.scalar(select(Produto.id).where(Produto.rede_produto_id == coletor.produto_id(0)))
    # "Acompanhar neste perfil" pelo membro.
    r = client.post(f"{_url(perfil['id'])}/interesses", headers=hm,
                    json={"mercadoProdutoId": str(pid)})
    assert r.status_code == 201, r.text
    i = r.json()
    # Pausar → reativar → encerrar, com versão.
    r = client.patch(f"/api/mercado/interesses/{i['id']}", headers=hm,
                     json={"version": i["version"], "situacao": "pausado"})
    assert r.status_code == 200 and r.json()["situacao"] == "pausado" and r.json()["pausadoEm"]
    v = r.json()["version"]
    # Versão velha → 409.
    r = client.patch(f"/api/mercado/interesses/{i['id']}", headers=hm,
                     json={"version": i["version"], "situacao": "ativo"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    r = client.patch(f"/api/mercado/interesses/{i['id']}", headers=hm,
                     json={"version": v, "situacao": "ativo", "nota": "voltou"})
    assert r.status_code == 200 and r.json()["situacao"] == "ativo" and r.json()["nota"] == "voltou"
    v = r.json()["version"]
    r = client.patch(f"/api/mercado/interesses/{i['id']}", headers=hm,
                     json={"version": v, "situacao": "encerrado"})
    assert r.status_code == 200 and r.json()["encerradoEm"]
    v = r.json()["version"]
    # Encerrado é final: 409; e nada foi apagado (a linha continua, com histórico).
    r = client.patch(f"/api/mercado/interesses/{i['id']}", headers=hm,
                     json={"version": v, "situacao": "ativo"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "interesse_encerrado"
    vs = client.get(f"/api/mercado/interesses/{i['id']}/versions", headers=hm).json()["items"]
    assert [x["details"].get("acao") for x in vs][:3] == ["encerrado", "reativado", "pausado"]
    # Revert só do dono: membro → 403; dono volta ao estado "pausado" (versão 2).
    r = client.post(f"/api/mercado/interesses/{i['id']}/revert", headers=hm,
                    json={"version": vs[0]["version"], "toVersion": 2})
    assert r.status_code == 403
    r = client.post(f"/api/mercado/interesses/{i['id']}/revert", headers=ligado,
                    json={"version": vs[0]["version"], "toVersion": 2})
    assert r.status_code == 200 and r.json()["situacao"] == "pausado"
    v = r.json()["version"]
    r = client.patch(f"/api/mercado/interesses/{i['id']}", headers=hm,
                     json={"version": v, "situacao": "encerrado"})
    assert r.status_code == 200
    v = r.json()["version"]
    # Um novo interesse pode nascer depois do encerrado; e reverter o velho para "vivo" com o
    # novo de pé → 409 (a unicidade dos vivos).
    r = client.post(f"{_url(perfil['id'])}/interesses", headers=hm,
                    json={"mercadoProdutoId": str(pid)})
    assert r.status_code == 201
    r = client.post(f"/api/mercado/interesses/{i['id']}/revert", headers=ligado,
                    json={"version": v, "toVersion": 2})
    assert r.status_code == 409 and r.json()["error"]["code"] == "interesse_duplicado"
    # Seguir loja (membro) e deixar de seguir, com a versão da config.
    loja_id = db.scalar(select(Loja.id).where(Loja.rede_loja_id == "loja123"))
    cfg = client.get(f"{_url(perfil['id'])}/config", headers=hm).json()
    assert cfg["version"] == 0 and cfg["categoriaIds"] == [] and cfg["maximoCategorias"] == 5
    r = client.post(f"{_url(perfil['id'])}/lojas/{loja_id}/seguir", headers=hm,
                    json={"version": cfg["version"]})
    assert r.status_code == 200, r.text
    assert [lj["nome"] for lj in r.json()["lojasSeguidas"]] == ["Loja X"]
    v = r.json()["version"]
    r = client.post(f"{_url(perfil['id'])}/lojas/{loja_id}/deixar-de-seguir", headers=hm,
                    json={"version": v})
    assert r.status_code == 200 and r.json()["lojasSeguidas"] == []
    r = client.post(f"{_url(perfil['id'])}/lojas/{loja_id}/deixar-de-seguir", headers=hm,
                    json={"version": r.json()["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "loja_nao_seguida"


def test_config_do_nicho_so_dono_e_categorias_maximo(client, db, ligado, membro, coletor):  # noqa: F811
    _, hm = membro
    perfil = criar_perfil(client, ligado)
    coletor.semear(db, produtos=2, dias=1)  # traz as categorias Moda > Feminino (> Shorts)
    cats = client.get("/api/mercado/categorias", headers=hm).json()["itens"]
    assert len(cats) >= 2 and cats[0]["nivel"] == 1 and "Moda" in cats[0]["caminho"]
    folha = next(c for c in cats if c["nome"] == "Shorts")
    assert folha["nProdutos"] == 2
    # Membro não edita a config.
    r = client.put(f"{_url(perfil['id'])}/config", headers=hm,
                   json={"version": 0, "categoriaIds": [folha["id"]], "maxRelacionadosDia": 10,
                         "avisarNovoEmAlta": True})
    assert r.status_code == 403
    # Mais de 5 → 400.
    r = client.put(f"{_url(perfil['id'])}/config", headers=ligado,
                   json={"version": 0, "categoriaIds": [str(uuid.uuid4()) for _ in range(6)],
                         "maxRelacionadosDia": 10, "avisarNovoEmAlta": True})
    assert r.status_code == 400 and r.json()["error"]["code"] == "categorias_maximo"
    # Categoria fora da taxonomia → 400.
    r = client.put(f"{_url(perfil['id'])}/config", headers=ligado,
                   json={"version": 0, "categoriaIds": [str(uuid.uuid4())],
                         "maxRelacionadosDia": 10, "avisarNovoEmAlta": True})
    assert r.status_code == 400 and r.json()["error"]["code"] == "categoria_desconhecida"
    # Dono grava (version 0 → 1) e o histórico nasce.
    r = client.put(f"{_url(perfil['id'])}/config", headers=ligado,
                   json={"version": 0, "categoriaIds": [folha["id"]], "maxRelacionadosDia": 3,
                         "avisarNovoEmAlta": False})
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["version"] == 1 and cfg["categorias"][0]["nome"] == "Shorts"
    assert cfg["maxRelacionadosDia"] == 3 and cfg["updatedBy"] is not None
    r = client.put(f"{_url(perfil['id'])}/config", headers=ligado,
                   json={"version": 0, "categoriaIds": [], "maxRelacionadosDia": 3,
                         "avisarNovoEmAlta": False})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    vs = client.get(f"{_url(perfil['id'])}/config/versions", headers=hm).json()["items"]
    assert [v["action"] for v in vs] == ["created"]
    # Perfil inexistente → 404.
    assert client.get(f"{_url(uuid.uuid4())}/config", headers=hm).status_code == 404


def test_mcp_le_e_nao_escreve(client, db, ligado, coletor, mcp_habilitado):  # noqa: F811
    perfil = criar_perfil(client, ligado)
    coletor.semear(db, produtos=1, dias=1, ranking=False)
    pid = db.scalar(select(Produto.id).where(Produto.rede_produto_id == coletor.produto_id(0)))
    ligar(client, ligado, mcp_habilitado)
    _, tok = criar_cliente(client, ligado, "Analista", "propostas")
    h = bearer_mcp(tok)
    assert client.get(f"{_url(perfil['id'])}/interesses", headers=h).status_code == 200
    assert client.get(f"{_url(perfil['id'])}/config", headers=h).status_code == 200
    assert client.get("/api/mercado/categorias", headers=h).status_code == 200
    assert client.get("/api/mercado/interesses", headers=h).status_code == 200
    antes = db.execute(text("SELECT count(*) FROM security_events WHERE type = 'publicacao_recusada'")).scalar()
    r = client.post(f"{_url(perfil['id'])}/interesses", headers=h,
                    json={"mercadoProdutoId": str(pid)})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.put(f"{_url(perfil['id'])}/config", headers=h,
                   json={"version": 0, "categoriaIds": [], "maxRelacionadosDia": 10,
                         "avisarNovoEmAlta": True})
    assert r.status_code == 403
    depois = db.execute(text("SELECT count(*) FROM security_events WHERE type = 'publicacao_recusada'")).scalar()
    assert depois == antes + 2
    assert client.get(f"{_url(perfil['id'])}/interesses", headers=ligado).json()["total"] == 0
