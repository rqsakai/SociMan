"""T028 (US1, SC-001): com o coletor falso (3 produtos × 10 dias), a lista traz os cartões com os
números calculados à mão, tudo `estimado`; `coletando` no produto de 1 foto; `semDadoAfiliado` no
sem Affiliate; filtros, ordenação, cursor; membro vê os mesmos números; tool MCP lê; nada grava."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fakes.coletor_fake import SP, ColetorFake
from sqlalchemy import func, select

from integration.coleta_helpers import coletor, dono, ligado, membro  # noqa: F401
from integration.mcp_helpers import bearer as bearer_mcp
from integration.mcp_helpers import criar_cliente, ligar
from integration.postagem_helpers import criar_perfil
from sociman_api.history import EntityVersion
from sociman_api.mercado.models import FotoProduto, Produto

HOJE = datetime.now(UTC).astimezone(SP).date()


@pytest.fixture
def semente(db, coletor):  # noqa: F811
    return coletor.semear(db, produtos=3, dias=10, imagens_por_produto=1)


def _lista(client, h, **q):
    r = client.get("/api/mercado/produtos", headers=h, params=q)
    assert r.status_code == 200, r.text
    return r.json()


def _por_rede_id(body: dict) -> dict[str, dict]:
    return {c["redeProdutoId"]: c for c in body["itens"]}


def test_cartoes_com_os_numeros_do_sc_001(client, db, ligado, coletor, semente):  # noqa: F811
    body = _lista(client, ligado, de=(HOJE - timedelta(days=6)).isoformat(), ate=HOJE.isoformat())
    assert body["total"] == 3 and body["proximo"] is None
    por = _por_rede_id(body)
    p0 = por[coletor.produto_id(0)]  # passo 20/dia: 1000 … 1180
    # vendas no período de 7 dias: v(hoje) − v(hoje − 7) = 1180 − 1040 = 140
    assert p0["vendasPeriodo"]["valor"] == 140 and p0["vendasPeriodo"]["estimado"] is True
    assert p0["vendasDia"]["valor"] == 20
    # GMV: 7 pares × 20 × preço mínimo (4990) = 698.600 centavos
    assert p0["gmvPeriodoCentavos"]["valor"] == 7 * 20 * 4990
    assert p0["vendasTotais"]["valor"] == 1180
    assert p0["gmvTotalCentavos"]["valor"] == 1180 * 4990
    assert "grosseiro" in p0["gmvTotalCentavos"]["motivos"]
    # Comissão por venda = 4990 × 12% = 598,8; criadores 37; retorno/dia = 20 × 598,8
    assert p0["comissaoBp"]["valor"] == 1200
    assert p0["comissaoPorVendaCentavos"]["valor"] == pytest.approx(598.8)
    assert p0["nCriadores"]["valor"] == 37
    assert p0["retornoAfiliadoCentavosDia"]["valor"] == pytest.approx(20 * 598.8 / (37 + 5))
    # Crescimento: 7 d a +20 contra 7 d a +20 → 0 (estável; base 20 ≥ 3)
    assert p0["crescimento"]["valor"] == pytest.approx(0)
    assert p0["estado"] == "ok" and p0["calor"] == "quente"
    assert p0["loja"]["nome"] == "Loja X" and p0["loja"]["oficial"] is True
    assert p0["categoria"]["caminho"] == "Moda > Feminino > Shorts"
    assert p0["preco"]["minCentavos"] == 4990 and p0["preco"]["maxCentavos"] == 5990
    assert p0["imagemUrl"] and p0["imagemUrl"].startswith("/img/")
    assert p0["rankings"] and p0["rankings"][0]["tipo"] == "mais_vendidos"
    # Todo derivado é estimado.
    for chave in ("vendasPeriodo", "gmvPeriodoCentavos", "crescimento", "vendasDia",
                  "vendasTotais", "gmvTotalCentavos", "comissaoPorVendaCentavos",
                  "retornoAfiliadoCentavosDia"):
        assert p0[chave]["estimado"] is True, chave
    # Produto 2: sem Affiliate → "sem dado de afiliado", sem erro.
    p2 = por[coletor.produto_id(2)]
    assert p2["comissaoBp"]["valor"] is None
    assert p2["comissaoBp"]["motivos"] == ["sem_dado_afiliado"]
    assert p2["retornoAfiliadoCentavosDia"]["motivos"] == ["sem_dado_afiliado"]
    assert p2["vendasPeriodo"]["valor"] == 7 * 12
    # Contexto: período, anterior, fuso e constantes nomeadas.
    ctx = body["contexto"]
    assert ctx["fuso"] == "America/Sao_Paulo" and ctx["constantes"]["kAfiliados"] == 5
    assert ctx["anteriorAte"] == (HOJE - timedelta(days=7)).isoformat()


def test_coletando_com_uma_foto_e_amostra_pequena(client, db, ligado, coletor):  # noqa: F811
    coletor.semear(db, produtos=2, dias=1, ranking=False)  # o último fica sem Affiliate
    body = _lista(client, ligado)
    c = _por_rede_id(body)[coletor.produto_id(0)]
    assert c["estado"] == "coletando" and c["vendasDia"]["valor"] is None
    assert "coletando" in c["vendasDia"]["motivos"]
    # Preço, loja e comissão continuam visíveis.
    assert c["preco"]["minCentavos"] == 4990 and c["loja"]["nome"] == "Loja X"
    assert c["comissaoBp"]["valor"] == 1200
    coletor2 = ColetorFake(client, coletor.h["Authorization"].split(" ", 1)[1])
    coletor2.semear(db, produtos=2, dias=5, ranking=False)  # repete a foto de hoje; +4 dias
    c = _por_rede_id(_lista(client, ligado))[coletor.produto_id(0)]
    assert c["estado"] == "amostra_pequena"
    assert c["vendasDia"]["amostraPequena"] is True


def test_filtros_ordem_cursor_e_periodo_invalido(client, db, ligado, coletor, semente):  # noqa: F811
    body = _lista(client, ligado, ordenar="vendasPeriodo", limite=2)
    assert body["total"] == 3 and len(body["itens"]) == 2 and body["proximo"]
    ids = [c["redeProdutoId"] for c in body["itens"]]
    assert ids == [coletor.produto_id(0), coletor.produto_id(2)]  # 20/dia, 12/dia, 5/dia
    resto = _lista(client, ligado, ordenar="vendasPeriodo", limite=2, cursor=body["proximo"])
    assert [c["redeProdutoId"] for c in resto["itens"]] == [coletor.produto_id(1)]
    assert resto["proximo"] is None
    for ordem in ("gmvPeriodo", "crescimento", "vendasTotais", "gmvTotal", "preco", "comissaoBp",
                  "comissaoPorVenda", "retornoAfiliado", "nCriadores", "primeiraVezEm",
                  "ultimaFotoEm", "titulo", "titulo:desc", "preco:asc"):
        assert _lista(client, ligado, ordenar=ordem)["total"] == 3, ordem
    asc = _lista(client, ligado, ordenar="preco:asc")
    assert next(c["redeProdutoId"] for c in asc["itens"]) == coletor.produto_id(0)
    assert _lista(client, ligado, q="Produto 1")["total"] == 1
    assert _lista(client, ligado, q=coletor.produto_id(2))["total"] == 1
    r = client.get("/api/mercado/produtos", headers=ligado,
                   params={"de": (HOJE - timedelta(days=401)).isoformat(), "ate": HOJE.isoformat()})
    assert r.status_code == 400 and r.json()["error"]["code"] == "periodo_invalido"
    r = client.get("/api/mercado/produtos", headers=ligado, params={"ordenar": "x"})
    assert r.status_code == 400
    r = client.get("/api/mercado/produtos", headers=ligado, params={"cursor": "!!"})
    assert r.status_code == 400
    r = client.get("/api/mercado/produtos", headers=ligado, params={"perfilId": str(uuid.uuid4())})
    assert r.status_code == 404


def test_perfil_so_restringe(client, db, ligado, coletor, semente):  # noqa: F811
    perfil = criar_perfil(client, ligado)
    assert _lista(client, ligado, perfilId=perfil["id"])["total"] == 0
    assert _lista(client, ligado, soAcompanhados="true")["total"] == 0
    # Um interesse manual do perfil no produto 0 (direto no banco, a US4 traz a rota).
    from sqlalchemy import text
    pid = db.scalar(select(Produto.id).where(Produto.rede_produto_id == coletor.produto_id(0)))
    db.execute(text("INSERT INTO mercado_interesses (id, perfil_id, mercado_produto_id, origem) "
                    "VALUES (:i, :p, :m, 'manual')"),
               {"i": uuid.uuid4(), "p": perfil["id"], "m": pid})
    db.commit()
    body = _lista(client, ligado, perfilId=perfil["id"])
    assert body["total"] == 1 and body["itens"][0]["interesses"][0]["origem"] == "manual"
    assert _lista(client, ligado, soAcompanhados="true")["total"] == 1
    assert _lista(client, ligado, origem="manual")["total"] == 1
    assert _lista(client, ligado, origem="vitrine")["total"] == 0


def test_membro_ve_os_mesmos_numeros(client, db, ligado, coletor, semente, membro):  # noqa: F811
    _, hm = membro
    dono_body = _lista(client, ligado)
    membro_body = _lista(client, hm)
    a = {c["redeProdutoId"]: (c["comissaoBp"], c["retornoAfiliadoCentavosDia"], c["vendasPeriodo"])
         for c in dono_body["itens"]}
    b = {c["redeProdutoId"]: (c["comissaoBp"], c["retornoAfiliadoCentavosDia"], c["vendasPeriodo"])
         for c in membro_body["itens"]}
    assert a == b


def test_detalhe_serie_e_resumo(client, db, ligado, coletor, semente):  # noqa: F811
    pid = db.scalar(select(Produto.id).where(Produto.rede_produto_id == coletor.produto_id(0)))
    r = client.get(f"/api/mercado/produtos/{pid}", headers=ligado)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ficha"]["titulo"] == "Produto 0" and d["nFichas"] == 1
    assert len(d["galeria"]) == 1 and d["galeria"][0]["url"].startswith("/img/")
    assert d["galeria"][0]["original"]["url"].startswith("/api/midia/")
    assert d["interessesDoUsuario"] == [] and d["adotadoEm"] == []
    r = client.get(f"/api/mercado/produtos/{pid}/serie", headers=ligado,
                   params={"de": (HOJE - timedelta(days=6)).isoformat(), "ate": HOJE.isoformat()})
    s = r.json()
    assert len(s["diaria"]) == 7 and s["diaria"][-1]["vendidos"]["valor"] == 1180
    assert s["diaria"][-1]["vendasDia"]["valor"] == 20
    assert len(s["fotos"]) == 14  # 7 dias × 2 fontes
    assert s["resumo"]["vendasPeriodo"]["valor"] == 140
    r = client.get(f"/api/mercado/produtos/{pid}/serie", headers=ligado,
                   params={"fonte": "affiliate"})
    assert all(f["fonte"] == "affiliate" for f in r.json()["fotos"])
    r = client.get(f"/api/mercado/produtos/{uuid.uuid4()}", headers=ligado)
    assert r.status_code == 404 and r.json()["error"]["code"] == "produto_nao_encontrado"
    r = client.get("/api/mercado/resumo", headers=ligado,
                   params={"de": (HOJE - timedelta(days=6)).isoformat(), "ate": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    res = r.json()
    assert next(c["redeProdutoId"] for c in res["maisVendidos"]["itens"]) == coletor.produto_id(0)
    assert res["totais"]["produtos"] == 3 and res["totais"]["ok"] == 3
    assert res["totais"]["vendasPeriodo"]["valor"] == 140 + 84 + 35
    assert res["estadoColeta"]["habilitada"] is True
    # Só "mais vendidos" e crescimento estável (0): ninguém é "novo em alta" (FR-048).
    assert res["novosEmAlta"]["total"] == 0
    # Uma foto do ranking "em alta" de hoje muda isso para os dois com ≥ 10 vendas/dia.
    tid = coletor.tarefa(db, "ranking", "ranking:cat45:em_alta:7d", "https://exemplo.test/shop/ranking/alta",
                         HOJE, nivel=3, fonte="affiliate", reservar=True)
    coletor.abrir()
    r2 = coletor.itens([coletor.item(tid, coletor.campos_ranking(3, 0, tipo="em_alta"), HOJE, hora=12)])
    assert r2["resultados"][0]["status"] == "gravado", r2
    coletor.fechar()
    res = client.get("/api/mercado/resumo", headers=ligado,
                     params={"de": (HOJE - timedelta(days=6)).isoformat(), "ate": HOJE.isoformat()}).json()
    assert res["novosEmAlta"]["total"] == 2
    assert all(c["novoEmAlta"] for c in res["novosEmAlta"]["itens"])
    # "Produto 1" cresce 5/dia: fica fora de "novo em alta" (< 10 vendas/dia).
    assert coletor.produto_id(1) not in {c["redeProdutoId"] for c in res["novosEmAlta"]["itens"]}


def test_leituras_nao_gravam_e_mcp_le(client, db, ligado, coletor, semente, mcp_habilitado):  # noqa: F811
    versoes = db.scalar(select(func.count()).select_from(EntityVersion))
    fotos = db.scalar(select(func.count()).select_from(FotoProduto))
    _lista(client, ligado)
    client.get("/api/mercado/resumo", headers=ligado)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(EntityVersion)) == versoes
    assert db.scalar(select(func.count()).select_from(FotoProduto)) == fotos
    ligar(client, ligado, mcp_habilitado)
    _, token = criar_cliente(client, ligado, "Analista", "leitura")
    r = client.get("/api/mercado/produtos", headers=bearer_mcp(token))
    assert r.status_code == 200 and r.json()["total"] == 3
    r = client.get("/api/mercado/resumo", headers=bearer_mcp(token))
    assert r.status_code == 200
    # O token do coletor não lê o mercado (escopo).
    r = client.get("/api/mercado/produtos", headers=coletor.h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "escopo_coleta"
