"""T042 (US4, FR-018/FR-019/FR-020/FR-022): anotações e propostas."""

import uuid

import pytest

from integration.mcp_helpers import bearer, criar_cliente, ligar
from integration.postagem_helpers import (  # noqa: F401
    add_destino,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)


@pytest.fixture
def base(client, dono, membro, db, mcp_habilitado):  # noqa: F811
    _, h = dono
    ligar(client, h, mcp_habilitado)
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"])
    corte = criar_corte(db, perfil["id"])
    destino = add_destino(client, h, corte.id, conta["id"])
    _, token = criar_cliente(client, h, "Planejador", "propostas")
    _, outro = criar_cliente(client, h, "Revisor", "propostas")
    return {"h": h, "hm": membro[1], "perfil": perfil, "conta": conta, "corte": corte,
            "destino": destino, "token": token, "outro": outro}


def _criar(client, h, **corpo):
    return client.post("/api/anotacoes", headers=h, json=corpo)


def test_criar_por_agente_e_por_humano(client, base):
    r = _criar(client, bearer(base["token"]), alvoTipo="perfil", alvoId=base["perfil"]["id"],
               texto="Observação do agente")
    assert r.status_code == 201
    a = r.json()["anotacao"]
    assert a["autor"]["tipo"] == "mcp_client" and a["autor"]["nome"] == "Planejador"
    assert a["perfilId"] == base["perfil"]["id"] and a["situacao"] == "aberta"
    assert a["alvo"]["link"] == f"/app/perfis/{base['perfil']['id']}"
    r = _criar(client, base["hm"], alvoTipo="conta", alvoId=base["conta"]["id"], texto="do membro")
    assert r.status_code == 201 and r.json()["anotacao"]["autor"]["tipo"] == "usuario"


@pytest.mark.parametrize("texto,status", [("", 400), ("x" * 4001, 400), ("x" * 4000, 201)])
def test_tamanho_do_texto(client, base, texto, status):
    r = _criar(client, bearer(base["token"]), alvoTipo="perfil", alvoId=base["perfil"]["id"],
               texto=texto)
    assert r.status_code == status


def test_alvo_inexistente_e_arquivado(client, base):
    r = _criar(client, bearer(base["token"]), alvoTipo="corte", alvoId=str(uuid.uuid4()),
               texto="x")
    assert r.status_code == 404
    perfil = criar_perfil(client, base["h"], "Arquivado")
    client.post(f"/api/perfis/{perfil['id']}/archive", headers=base["h"],
                json={"version": perfil["version"]})
    r = _criar(client, bearer(base["token"]), alvoTipo="perfil", alvoId=perfil["id"], texto="x")
    assert r.status_code == 409 and r.json()["error"]["code"] == "alvo_arquivado"


def test_proposta_so_em_destino_e_campos(client, base):
    t = bearer(base["token"])
    r = _criar(client, t, alvoTipo="perfil", alvoId=base["perfil"]["id"], tipo="proposta_texto",
               texto="x", campos={"titulo": "T"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "proposta_so_em_destino"
    r = _criar(client, t, alvoTipo="destino", alvoId=base["destino"]["id"],
               tipo="proposta_texto", texto="x", campos={})
    assert r.status_code == 400 and r.json()["error"]["code"] == "campos_vazios"
    r = _criar(client, t, alvoTipo="destino", alvoId=base["destino"]["id"],
               tipo="proposta_texto", texto="x", campos={"titulo": "y" * 101})
    assert r.status_code == 400
    r = _criar(client, t, alvoTipo="destino", alvoId=base["destino"]["id"],
               tipo="proposta_texto", texto="Legenda mais curta",
               campos={"descricao": "Nova legenda", "hashtags": ["receita"]})
    assert r.status_code == 201
    assert r.json()["anotacao"]["campos"] == {"titulo": None, "descricao": "Nova legenda",
                                              "hashtags": ["receita"]}


def test_editar_e_arquivar_so_o_autor(client, base):
    a = _criar(client, bearer(base["token"]), alvoTipo="perfil", alvoId=base["perfil"]["id"],
               texto="um").json()["anotacao"]
    url = f"/api/anotacoes/{a['id']}"
    r = client.patch(url, headers=bearer(base["outro"]), json={"version": 1, "texto": "dois"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "nao_e_o_autor"
    r = client.patch(url, headers=base["hm"], json={"version": 1, "texto": "dois"})
    assert r.status_code == 403
    r = client.patch(url, headers=bearer(base["token"]), json={"version": 1, "texto": "dois"})
    assert r.status_code == 200 and r.json()["anotacao"]["version"] == 2
    r = client.post(f"{url}/archive", headers=bearer(base["outro"]), json={"version": 2})
    assert r.status_code == 403
    r = client.post(f"{url}/archive", headers=base["h"], json={"version": 2})  # o dono pode
    assert r.status_code == 200 and r.json()["anotacao"]["situacao"] == "arquivada"
    r = client.patch(url, headers=bearer(base["token"]), json={"version": 3, "texto": "três"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "anotacao_fechada"


def test_descartar_so_humano_e_revert_so_dono(client, base):
    a = _criar(client, bearer(base["token"]), alvoTipo="destino", alvoId=base["destino"]["id"],
               tipo="proposta_texto", texto="p", campos={"titulo": "Novo"}).json()["anotacao"]
    url = f"/api/anotacoes/{a['id']}"
    r = client.post(f"{url}/descartar", headers=bearer(base["token"]), json={"version": 1})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.post(f"{url}/descartar", headers=base["hm"],
                    json={"version": 1, "motivo": "fora do tom"})
    assert r.status_code == 200
    d = r.json()["anotacao"]
    assert d["situacao"] == "descartada" and d["motivoDescarte"] == "fora do tom"
    assert d["resolvidaPor"]["name"] == "Membro"
    r = client.post(f"{url}/revert", headers=base["hm"], json={"version": 2, "toVersion": 1})
    assert r.status_code == 403
    r = client.post(f"{url}/revert", headers=bearer(base["token"]),
                    json={"version": 2, "toVersion": 1})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.post(f"{url}/revert", headers=base["h"], json={"version": 2, "toVersion": 1})
    assert r.status_code == 200 and r.json()["anotacao"]["situacao"] == "aberta"
    versoes = client.get(f"{url}/versions", headers=base["h"]).json()["items"]
    assert [v["autor"]["tipo"] for v in versoes] == ["usuario", "usuario", "mcp_client"]


def test_alvo_arquivado_depois_e_calculado(client, base):
    a = _criar(client, bearer(base["token"]), alvoTipo="destino", alvoId=base["destino"]["id"],
               texto="obs").json()["anotacao"]
    assert a["alvo"]["arquivado"] is False
    d = base["destino"]
    client.post(f"/api/destinos/{d['id']}/archive", headers=base["h"],
                json={"version": d["version"]})
    a = client.get(f"/api/anotacoes/{a['id']}", headers=base["h"]).json()["anotacao"]
    assert a["alvo"]["arquivado"] is True


def test_lista_filtros_paginacao_e_resumo(client, base):
    t = bearer(base["token"])
    for i in range(3):
        _criar(client, t, alvoTipo="perfil", alvoId=base["perfil"]["id"], texto=f"n{i}")
    _criar(client, bearer(base["outro"]), alvoTipo="conta", alvoId=base["conta"]["id"], texto="o")
    r = client.get("/api/anotacoes?limit=2", headers=base["h"]).json()
    assert len(r["anotacoes"]) == 2 and r["nextCursor"]
    r2 = client.get(f"/api/anotacoes?limit=2&cursor={r['nextCursor']}", headers=base["h"]).json()
    assert len(r2["anotacoes"]) == 2 and r2["nextCursor"] is None
    assert {a["texto"] for a in r["anotacoes"] + r2["anotacoes"]} == {"n0", "n1", "n2", "o"}
    r = client.get(f"/api/anotacoes?alvoTipo=conta&alvoId={base['conta']['id']}",
                   headers=base["h"]).json()
    assert [a["texto"] for a in r["anotacoes"]] == ["o"]
    assert client.get("/api/anotacoes/resumo", headers=base["h"]).json() == {"abertas": 4}
    r = client.get(f"/api/anotacoes/resumo?perfilId={base['perfil']['id']}", headers=base["h"])
    assert r.json() == {"abertas": 4}
