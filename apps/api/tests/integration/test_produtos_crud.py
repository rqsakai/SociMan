"""Cadastro do produto (spec 012, T019, US1): criar com fotos, sem fotos, validação de todas as
fotos antes de gravar qualquer uma, limite de variantes, permissões e HD fora."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from sqlalchemy import func, select

from integration.geracao_helpers import _buckets, member, owner  # noqa: F401 (fixtures)
from integration.produtos_helpers import criar, foto, passos, perfil, ver, versoes
from sociman_api.perfis.models import Image
from sociman_api.produtos.models import Produto, ProdutoVariante


def _contagens(db) -> tuple[int, int, int]:
    db.expire_all()
    return (db.scalar(select(func.count()).select_from(Produto)),
            db.scalar(select(func.count()).select_from(ProdutoVariante)),
            db.scalar(select(func.count()).select_from(Image)))


def test_criar_com_3_fotos_pede_a_ficha(client, owner):
    h = owner[1]
    pid = perfil(client, h)
    p = criar(client, h, pid, n_fotos=3, obs="3 cores, logo LS", urlLoja="https://loja.x/p/1")
    assert p["status"] == "gerando" and p["estado"] == "gerando"
    assert [v["position"] for v in p["variantes"]] == [0, 1, 2]
    assert all(v["original"]["imageId"] and v["recorte"] is None for v in p["variantes"])
    fichas = passos(p, "produto.ficha")
    assert len(fichas) == 1 and fichas[0]["status"] == "na_fila"
    assert p["urlLoja"] == "https://loja.x/p/1" and p["fichaPor"] is None
    assert p["ficha"] is None
    assert {x["motivo"] for x in p["pendencias"]} >= {"ficha_incompleta", "sem_recorte"}
    hist = versoes(client, h, p["id"])
    assert [v["action"] for v in hist] == ["created"]
    assert hist[0]["actor"]["id"] == str(owner[0].id)
    # A geração leva as 3 originais, na ordem, e a observação.
    g = client.get(f"/api/geracoes/{fichas[0]['id']}", headers=h).json()
    assert [r["id"] for r in g["referencias"]] == [v["original"]["imageId"]
                                                   for v in p["variantes"]]
    assert g["instrucao"] == "3 cores, logo LS"


def test_criar_sem_fotos_fica_em_rascunho(client, owner):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=0)
    assert p["status"] == "rascunho" and p["variantes"] == [] and p["passos"] == []
    assert {"motivo": "sem_variante", "varianteId": None} in p["pendencias"]


def test_foto_invalida_recusa_tudo(client, owner, db):
    h = owner[1]
    pid = perfil(client, h)
    antes = _contagens(db)
    casos = [
        ([foto(), foto(size=(511, 511))], "fotos[1]"),
        ([foto(), foto(), foto(fmt="GIF")], "fotos[2]"),
        ([b"x" * (21 * 1024 * 1024)], "fotos[0]"),
    ]
    for fotos, campo in casos:
        r = criar(client, h, pid, fotos=fotos, status=400)
        assert r["error"]["code"] == "invalid_image"
        assert r["error"]["details"]["field"] == campo
        assert _contagens(db) == antes  # nenhuma linha (nem imagem) criada


def test_sete_fotos_passa_do_limite(client, owner, db):
    h = owner[1]
    r = criar(client, h, perfil(client, h), n_fotos=7, status=409)
    assert r["error"]["code"] == "limite_variantes"
    assert _contagens(db)[0] == 0


def test_nome_e_link_validados(client, owner):
    h = owner[1]
    pid = perfil(client, h)
    r = criar(client, h, pid, name="   ", status=400)
    assert r["error"]["details"]["field"] == "name"
    r = criar(client, h, pid, urlLoja="http://loja.x", status=400)
    assert r["error"]["details"]["field"] == "urlLoja"


def test_editar_nao_muda_o_estado(client, owner):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    r = client.patch(f"/api/produtos/{p['id']}", headers=h,
                     json={"version": p["version"], "name": "shorts LS", "urlLoja": None})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "shorts LS" and r.json()["status"] == "gerando"
    r = client.patch(f"/api/produtos/{p['id']}", headers=h,
                     json={"version": p["version"], "name": "outro"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


def test_membro_cria_e_le(client, owner, member):
    pid = perfil(client, owner[1])
    p = criar(client, member[1], pid, n_fotos=1)
    assert ver(client, member[1], p["id"])["id"] == p["id"]
    r = client.get(f"/api/perfis/{pid}/produtos", headers=member[1])
    assert r.status_code == 200 and len(r.json()["itens"]) == 1


def test_token_mcp_nao_cria(client, owner, mcp_habilitado):
    from integration.mcp_helpers import bearer, criar_cliente, ligar

    pid = perfil(client, owner[1])
    ligar(client, owner[1], mcp_habilitado)
    _, token = criar_cliente(client, owner[1], escopo="propostas")
    r = client.post(f"/api/perfis/{pid}/produtos", headers=bearer(token),
                    data={"name": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"


def test_hd_sem_sentinela_503(client, owner, tmp_path, monkeypatch):
    from sociman_api.config import get_settings

    h = owner[1]
    pid = perfil(client, h)
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    r = criar(client, h, pid, n_fotos=1, status=503)
    assert r["error"]["code"] == "storage_unavailable"
    assert criar(client, h, pid, n_fotos=0)["status"] == "rascunho"  # só banco: funciona


def test_pedido_generico_com_alvo_produto_e_recusado(client, owner):
    h = owner[1]
    pid = perfil(client, h)
    p = criar(client, h, pid, n_fotos=1)
    r = client.post(f"/api/perfis/{pid}/geracoes", headers=h,
                    json={"alvoTipo": "produto", "alvoId": p["id"], "passo": "produto.flat",
                          "instrucao": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "alvo_incompativel"
