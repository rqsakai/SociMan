"""T060 (US5): ficha mudada cria versão e a anterior continua; galeria com 6 imagens; rankings com
variação entre 2 dias; vídeos só com @ e contadores; avaliações sem autor e com as fotos de
clientes; loja com GMV estimado = soma dos produtos; categorias em árvore."""

from datetime import UTC, datetime, timedelta

import pytest
from fakes.coletor_fake import SP, png
from sqlalchemy import select

from integration.coleta_helpers import coletor, dono, ligado  # noqa: F401
from sociman_api.mercado.models import Produto

HOJE = datetime.now(UTC).astimezone(SP).date()
URL_BASE = "https://exemplo.test/shop"


@pytest.fixture
def lago(db, coletor):  # noqa: F811
    """3 produtos × 2 dias (ranking alternando as posições 1 e 2 no 2º dia), 6 imagens cada;
    depois, numa rodada à parte, o produto 0 muda de título (turno da noite), ganha 5 avaliações
    (uma com foto), 3 vídeos top, e a loja X tem uma foto."""
    semente = coletor.semear(db, produtos=3, dias=2, imagens_por_produto=6)
    pid0 = coletor.produto_id(0)
    coletor.abrir()
    t_prod = coletor.tarefa(db, "produto", f"produto:{pid0}", coletor.url_produto(0), HOJE,
                            reservar=True)
    t_av = coletor.tarefa(db, "avaliacoes", f"avaliacoes:{pid0}:1", coletor.url_produto(0), HOJE,
                          nivel=8, fonte="pagina_publica", reservar=True)
    t_vid = coletor.tarefa(db, "produto_videos", f"produto_videos:{pid0}", coletor.url_produto(0),
                           HOJE, nivel=7, fonte="affiliate", reservar=True)
    t_loja = coletor.tarefa(db, "loja", "loja:loja123", f"{URL_BASE}/shop/loja123", HOJE,
                            nivel=6, fonte="pagina_publica", reservar=True)
    foto_cliente = png(999)
    coletor.imagens([foto_cliente], t_av, origem="avaliacao")
    r = coletor.itens([
        coletor.item(t_prod, coletor.campos_produto(0, 1, titulo="Produto 0 v2",
                                                     imagens_sha=semente["imagens"][0]), HOJE, hora=20),
        coletor.item(t_av, coletor.campos_avaliacoes(0, 5, imagens=[foto_cliente]), HOJE, hora=20,
                     imagens=[foto_cliente]),
        coletor.item(t_vid, coletor.campos_videos(0, 3), HOJE, hora=20),
        coletor.item(t_loja, coletor.campos_loja(novos=2), HOJE, hora=20),
    ])
    assert all(x["status"] == "gravado" for x in r["resultados"]), r
    coletor.fechar()
    db.expire_all()
    return {str(i): db.scalar(select(Produto.id).where(Produto.rede_produto_id == coletor.produto_id(i)))
            for i in range(3)}


def test_ficha_versionada_e_galeria(client, db, ligado, lago):  # noqa: F811
    pid = lago["0"]
    r = client.get(f"/api/mercado/produtos/{pid}/fichas", headers=ligado)
    assert r.status_code == 200, r.text
    fichas = r.json()["itens"]
    assert [f["titulo"] for f in fichas] == ["Produto 0 v2", "Produto 0"]
    assert "titulo" in fichas[0]["diff"]["campos"] and fichas[1]["diff"] is None
    assert len(fichas[0]["imagens"]) == 6 and len(fichas[1]["imagens"]) == 6
    det = client.get(f"/api/mercado/produtos/{pid}", headers=ligado).json()
    assert det["ficha"]["titulo"] == "Produto 0 v2" and det["nFichas"] == 2
    assert len(det["galeria"]) == 6 and len({g["sha256"] for g in det["galeria"]}) == 6
    assert all(g["url"].startswith("/img/") for g in det["galeria"])


def test_rankings_com_variacao_entre_dois_dias(client, db, ligado, lago, coletor):  # noqa: F811
    # No 2º dia o fake troca as posições 1 e 2: produto 0 caiu (1 → 2), produto 1 subiu (2 → 1).
    r = client.get(f"/api/mercado/produtos/{lago['0']}/rankings", headers=ligado,
                   params={"de": (HOJE - timedelta(days=1)).isoformat(), "ate": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["itens"]) == 2 and body["itens"][0]["dataLocal"] == HOJE.isoformat()
    res = body["resumo"][0]
    assert res["tipo"] == "mais_vendidos" and res["posicaoAtual"] == 2 and res["melhorPosicao"] == 1
    assert res["diasNoTopo"] == 2 and res["entrouEm"] == (HOJE - timedelta(days=1)).isoformat()
    cats = client.get("/api/mercado/categorias", headers=ligado).json()["itens"]
    fem = next(c for c in cats if c["redeCategoriaId"] == "cat45")
    r = client.get("/api/mercado/rankings", headers=ligado,
                   params={"categoriaId": fem["id"], "de": (HOJE - timedelta(days=1)).isoformat(),
                           "ate": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["fotos"]) == 2
    atual = body["atual"]
    assert atual["dataLocal"] == HOJE.isoformat()
    por_produto = {i["produto"]["redeProdutoId"]: i for i in atual["itens"]}
    assert por_produto[coletor.produto_id(1)]["posicao"] == 1
    assert por_produto[coletor.produto_id(1)]["variacao"] == "subiu"
    assert por_produto[coletor.produto_id(1)]["delta"] == 1
    assert por_produto[coletor.produto_id(0)]["variacao"] == "caiu"
    assert por_produto[coletor.produto_id(2)]["variacao"] == "igual"
    assert atual["sairam"] == []
    # Sem categoria: as fotos de todas (nenhum perfil configurado) e `atual` nulo.
    body = client.get("/api/mercado/rankings", headers=ligado).json()
    assert body["atual"] is None and len(body["fotos"]) >= 2


def test_videos_so_handle_e_contadores(client, db, ligado, lago):  # noqa: F811
    r = client.get(f"/api/mercado/produtos/{lago['0']}/videos", headers=ligado)
    assert r.status_code == 200, r.text
    itens = r.json()["itens"]
    assert len(itens) == 3 and itens[0]["posicao"] == 1
    assert set(itens[0]) == {"redeVideoId", "autorHandle", "views", "likes", "comentarios",
                             "compartilhamentos", "legenda", "publicadoEm", "dataLocal", "posicao",
                             "url"}
    assert itens[0]["autorHandle"] == "criadora.0" and itens[0]["views"] == 300000
    assert itens[0]["url"].startswith("https://exemplo.test/shop/@criadora.0/video/")


def test_avaliacoes_sem_autor_e_com_fotos(client, db, ligado, lago):  # noqa: F811
    r = client.get(f"/api/mercado/produtos/{lago['0']}/avaliacoes", headers=ligado)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resumo"]["total"] == 5 and body["resumo"]["comFotos"] == 1
    assert body["resumo"]["comTexto"] == 5 and body["resumo"]["porNota"]["5"] == 2
    for a in body["itens"]:
        assert "autorHash" not in a and "autor" not in a and "autorRef" not in a
        assert set(a) == {"id", "texto", "nota", "dataAvaliacao", "variante", "imagens", "curtidas",
                          "coletadoEm"}
    com_foto = [a for a in body["itens"] if a["imagens"]]
    assert len(com_foto) == 1 and com_foto[0]["imagens"][0]["url"].startswith("/img/")
    # Filtros.
    r = client.get(f"/api/mercado/produtos/{lago['0']}/avaliacoes", headers=ligado,
                   params={"nota": 5}).json()
    assert len(r["itens"]) == 2 and r["resumo"]["total"] == 5
    r = client.get(f"/api/mercado/produtos/{lago['0']}/avaliacoes", headers=ligado,
                   params={"comFotos": "true"}).json()
    assert len(r["itens"]) == 1
    # O texto nunca sai no bruto da resposta de lista com nome (não há campo de nome).
    assert "autor-" not in r"" + str(body)


def test_lojas_gmv_estimado_e_categorias_em_arvore(client, db, ligado, lago):  # noqa: F811
    r = client.get("/api/mercado/lojas", headers=ligado,
                   params={"de": (HOJE - timedelta(days=1)).isoformat(), "ate": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    lojas = r.json()
    assert lojas["total"] == 1
    lj = lojas["itens"][0]
    assert lj["nome"] == "Loja X" and lj["oficial"] is True
    assert lj["nota"]["valor"] == pytest.approx(4.7) and lj["nota"]["estimado"] is False
    assert lj["seguidores"]["valor"] == 15800 and lj["nProdutosNoLago"] == 5  # 3 + 2 novos
    assert lj["lancamentos30d"] == 5 and lj["vendidosTotal"]["valor"] == 230000
    assert lj["gmvEstimadoCentavos"]["estimado"] is True
    det = client.get(f"/api/mercado/lojas/{lj['id']}", headers=ligado,
                     params={"de": (HOJE - timedelta(days=1)).isoformat(),
                             "ate": HOJE.isoformat()}).json()
    soma = sum(p["gmvPeriodoCentavos"]["valor"] or 0 for p in det["produtos"])
    assert det["gmvEstimadoCentavos"]["valor"] == pytest.approx(round(soma))
    assert len(det["fotos"]) == 1 and len(det["novos30d"]) == 5
    gmvs = [p["gmvPeriodoCentavos"]["valor"] or 0 for p in det["produtos"]]
    assert gmvs == sorted(gmvs, reverse=True)
    assert client.get(f"/api/mercado/lojas/{lago['0']}", headers=ligado).status_code == 404
    # Ordenar por nome e filtrar oficiais.
    assert client.get("/api/mercado/lojas", headers=ligado,
                      params={"ordenarLoja": "nome", "oficial": "true"}).json()["total"] == 1
    assert client.get("/api/mercado/lojas", headers=ligado,
                      params={"ordenarLoja": "x"}).status_code == 400
    # Categorias em árvore: Moda > Feminino > Shorts, com o pai de cada uma.
    cats = client.get("/api/mercado/categorias", headers=ligado).json()["itens"]
    por_rede = {c["redeCategoriaId"]: c for c in cats}
    assert por_rede["cat1"]["paiId"] is None and por_rede["cat1"]["nivel"] == 1
    assert por_rede["cat45"]["paiId"] == por_rede["cat1"]["id"]
    assert por_rede["cat789"]["paiId"] == por_rede["cat45"]["id"]
    assert por_rede["cat789"]["caminho"] == "Moda > Feminino > Shorts"
    assert por_rede["cat789"]["nProdutos"] == 3
    assert client.get("/api/mercado/categorias", headers=ligado,
                      params={"nivel": 2}).json()["itens"][0]["nome"] == "Feminino"
