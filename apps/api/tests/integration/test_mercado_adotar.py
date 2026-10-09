"""T064 (US6, SC-009): "Adotar no catálogo" cria o produto da 012 com 100% das imagens válidas
copiadas, a categoria, a loja e o vínculo `mercado_produto_id`; a 2ª adoção responde 409 com o id;
o MCP é recusado; o detalhe do mercado mostra `adotadoEm`; imagem pequena demais para a 012 é
ignorada e contada, não derruba a adoção."""

from datetime import UTC, datetime

from fakes.coletor_fake import SP, png
from sqlalchemy import select, text

from integration.coleta_helpers import coletor, dono, ligado, membro  # noqa: F401
from integration.mcp_helpers import bearer as bearer_mcp
from integration.mcp_helpers import criar_cliente, ligar
from integration.postagem_helpers import criar_perfil
from sociman_api.mercado.models import Interesse, Produto

HOJE = datetime.now(UTC).astimezone(SP).date()


def _lago(db, coletor, i: int, imagens: list[bytes]):  # noqa: F811
    coletor.abrir()
    tid = coletor.tarefa(db, "produto", f"produto:{coletor.produto_id(i)}", coletor.url_produto(i),
                         HOJE, reservar=True)
    coletor.imagens(imagens, tid)
    r = coletor.itens([coletor.item(tid, coletor.campos_produto(i, 0, imagens=imagens), HOJE,
                                    imagens=imagens)])
    assert r["resultados"][0]["status"] == "gravado", r
    coletor.fechar()
    db.expire_all()
    return db.scalar(select(Produto.id).where(Produto.rede_produto_id == coletor.produto_id(i)))


def test_adotar_copia_ficha_e_imagens_e_liga(client, db, ligado, membro, coletor, mcp_habilitado):  # noqa: F811
    _, hm = membro
    perfil = criar_perfil(client, ligado)
    # Duas imagens válidas para a 012 (≥ 512) e uma pequena (ignorada e contada).
    pid = _lago(db, coletor, 0, [png(1, 512), png(2, 600), png(3)])
    # Qualquer humano adota (aqui o membro).
    r = client.post(f"/api/mercado/produtos/{pid}/adotar", headers=hm, json={"perfilId": perfil["id"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mercadoProdutoId"] == str(pid) and body["perfilId"] == perfil["id"]
    produto_012 = client.get(f"/api/produtos/{body['produtoId']}", headers=hm)
    assert produto_012.status_code == 200, produto_012.text
    p = produto_012.json()
    assert p["name"] == "Produto 0"
    assert p["urlLoja"] == coletor.url_produto(0)  # a loja da semente não tem URL: fica a do produto
    assert "Frete grátis" in p["obs"]
    assert len(p["variantes"]) == 2  # 100% das imagens válidas; a pequena foi ignorada
    assert p["mercadoProdutoId"] == str(pid)
    cat, mpid = db.execute(text("SELECT categoria, mercado_produto_id FROM produtos WHERE id = :id"),
                           {"id": body["produtoId"]}).one()
    assert cat == "Moda > Feminino > Shorts" and str(mpid) == str(pid)
    # Histórico da 012: a versão da ligação diz de onde veio.
    vs = client.get(f"/api/produtos/{body['produtoId']}/versoes", headers=hm).json()["items"]
    ligacao = next(v for v in vs if v["details"].get("origem") == "mercado_026")
    assert ligacao["details"]["imagensCopiadas"] == 2 and ligacao["details"]["imagensIgnoradas"] == 1
    # Interesse manual nasceu para o perfil, e o detalhe do mercado mostra a adoção.
    inter = db.scalars(select(Interesse).where(Interesse.perfil_id == perfil["id"])).all()
    assert len(inter) == 1 and inter[0].origem.value == "manual"
    assert inter[0].motivo["adotadoEm"] == body["produtoId"]
    det = client.get(f"/api/mercado/produtos/{pid}", headers=hm).json()
    assert det["adotadoEm"] == [{"perfilId": perfil["id"], "produtoId": body["produtoId"]}]
    # 2ª adoção no mesmo perfil → 409 com o id do existente (um novo interesse não nasce).
    r = client.post(f"/api/mercado/produtos/{pid}/adotar", headers=ligado, json={"perfilId": perfil["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ja_adotado"
    assert r.json()["error"]["details"]["produtoId"] == body["produtoId"]
    # Outro perfil pode adotar o mesmo produto do lago.
    perfil2 = criar_perfil(client, ligado, "Outro")
    r = client.post(f"/api/mercado/produtos/{pid}/adotar", headers=ligado, json={"perfilId": perfil2["id"]})
    assert r.status_code == 201
    assert db.execute(text("SELECT count(*) FROM produtos WHERE mercado_produto_id = :m"),
                      {"m": pid}).scalar() == 2
    # MCP: recusado (somente_humano); produto inexistente: 404.
    ligar(client, ligado, mcp_habilitado)
    _, tok = criar_cliente(client, ligado, "Analista", "propostas")
    r = client.post(f"/api/mercado/produtos/{pid}/adotar", headers=bearer_mcp(tok),
                    json={"perfilId": perfil["id"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.post("/api/mercado/produtos/00000000-0000-0000-0000-000000000001/adotar",
                    headers=ligado, json={"perfilId": perfil["id"]})
    assert r.status_code == 404


def test_adotar_sem_ficha_e_ficha_ausente(client, db, ligado):  # noqa: F811
    perfil = criar_perfil(client, ligado)
    # Produto do lago criado por link (sem ficha ainda).
    r = client.post(f"/api/perfis/{perfil['id']}/mercado/interesses", headers=ligado,
                    json={"url": "https://exemplo.test/shop/pdp/x/7399999999999999997"})
    assert r.status_code == 201, r.text
    pid = r.json()["mercadoProdutoId"]
    r = client.post(f"/api/mercado/produtos/{pid}/adotar", headers=ligado, json={"perfilId": perfil["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ficha_ausente"
