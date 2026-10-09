"""Listas da biblioteca da agência (spec 029, T010, T024 e T035): `GET /api/assets`,
`/api/produtos` e `/api/vozes` com o filtro de perfil base (ausente, `sem` e um perfil), a busca,
as tags, os arquivados, o cursor e o `perfilNome`; o cadastro com perfil base opcional; o PATCH do
perfil base, versionado e revertido só pelo dono; e as rotas por perfil, obsoletas, iguais à rota
nova filtrada."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

from sqlalchemy import select

from integration.estudio_helpers import ids, item, itens, listar, perfil, png
from integration.geracao_helpers import _buckets, member, owner  # noqa: F401 (fixtures)
from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Image


def _tres(client, h, tipo: str, **kw) -> tuple[str, str, dict, dict, dict]:
    a, b = perfil(client, h, "perfil-a"), perfil(client, h, "perfil-b")
    xa = item(client, h, tipo, a, name=f"{tipo} A", **kw)
    xb = item(client, h, tipo, b, name=f"{tipo} B", **kw)
    xs = item(client, h, tipo, None, name=f"{tipo} sem", **kw)
    return a, b, xa, xb, xs


def test_assets_filtro_por_perfil_base(client, owner):
    h = owner[1]
    a, _b, xa, xb, xs = _tres(client, h, "avatar")
    todos = listar(client, h, "assets", tipo="avatar")
    assert ids(todos) == {xa["id"], xb["id"], xs["id"]}
    nomes = {i["id"]: i["perfilNome"] for i in itens(todos)}
    assert nomes == {xa["id"]: "Perfil-A", xb["id"]: "Perfil-B", xs["id"]: None}
    assert ids(listar(client, h, "assets", tipo="avatar", perfilId=a)) == {xa["id"]}
    assert ids(listar(client, h, "assets", tipo="avatar", perfilId="sem")) == {xs["id"]}
    assert xs["perfilId"] is None and xa["perfilId"] == a


def test_filtro_invalido(client, owner):
    h = owner[1]
    for rota in ("assets", "produtos", "vozes"):
        r = listar(client, h, rota, status=400, perfilId="xpto")
        assert r["error"]["code"] == "invalid_query"
        assert r["error"]["details"]["field"] == "perfilId"
        r = listar(client, h, rota, status=400, perfilId=str(uuid.uuid4()))
        assert r["error"]["code"] == "perfil_invalido"


def test_assets_so_os_tipos_pedidos_busca_tags_e_arquivados(client, owner):
    h = owner[1]
    a = perfil(client, h, "perfil-a")
    av = item(client, h, "avatar", a, name="Ana")
    item(client, h, "cenario", None, name="Cozinha", prompt="retro kitchen")
    im = item(client, h, "imagem", None, name="Selo verde", tags="promo,verde")
    st = item(client, h, "sticker", a, name="Estrela")
    fu = item(client, h, "fundo", None, name="Fundo rosa")
    # O item "Assets" do AI Studio pede só imagem, sticker, marca d'água e fundo.
    lista = listar(client, h, "assets", tipo=["imagem", "sticker", "marca_dagua", "fundo"])
    assert ids(lista) == {im["id"], st["id"], fu["id"]}
    assert {t["tag"] for t in lista["tags"]} == {"promo", "verde"}
    assert ids(listar(client, h, "assets", q="selo")) == {im["id"]}
    assert ids(listar(client, h, "assets", tag="promo")) == {im["id"]}
    r = client.post(f"/api/assets/{av['id']}/archive", headers=h, json={"version": av["version"]})
    assert r.status_code == 200, r.text
    assert av["id"] not in ids(listar(client, h, "assets", tipo="avatar"))
    assert ids(listar(client, h, "assets", tipo="avatar", archived="true")) == {av["id"]}


def test_assets_cursor_estavel(client, owner):
    h = owner[1]
    a = perfil(client, h, "perfil-a")
    criados = {item(client, h, "avatar", a if i % 2 else None, name=f"A{i}")["id"]
               for i in range(5)}
    vistos, cursor = [], None
    while True:
        params = {"tipo": "avatar", "limit": 2} | ({"cursor": cursor} if cursor else {})
        pagina = listar(client, h, "assets", **params)
        vistos += [i["id"] for i in pagina["items"]]
        cursor = pagina["nextCursor"]
        if not cursor:
            break
    assert len(vistos) == len(set(vistos)) == 5 and set(vistos) == criados


def test_imagem_sem_perfil_vai_para_agencia(client, owner, db):
    h = owner[1]
    a = perfil(client, h, "perfil-a")
    sem = item(client, h, "imagem", None)
    com = item(client, h, "imagem", a)
    chave = {x["id"]: db.scalar(select(Image.object_key).where(
        Image.id == uuid.UUID(x["files"][0]["image"]["id"]))) for x in (sem, com)}
    assert chave[sem["id"]].startswith("agencia/imagens/")
    assert chave[com["id"]].startswith(f"perfis/{a}/")
    # O avatar sem perfil também guarda o arquivo na agência.
    av = item(client, h, "avatar", None)
    r = client.post(f"/api/assets/{av['id']}/arquivos", headers=h,
                    data={"role": "pose", "label": "frente"},
                    files={"file": ("f.png", png(), "application/octet-stream")})
    assert r.status_code == 201, r.text
    image_id = uuid.UUID(r.json()["file"]["image"]["id"])
    assert db.scalar(select(Image.object_key).where(Image.id == image_id)).startswith(
        "agencia/imagens/")


def test_criar_com_perfil_invalido_ou_arquivado(client, owner):
    h = owner[1]
    falso = str(uuid.uuid4())
    for tipo in ("avatar", "voz"):
        r = item(client, h, tipo, falso, status=400)
        assert r["error"]["code"] == "perfil_invalido"
    r = client.post("/api/produtos", headers=h, data={"name": "x", "perfilId": falso})
    assert r.status_code == 400 and r.json()["error"]["code"] == "perfil_invalido"
    a = perfil(client, h, "perfil-a")
    p = client.get(f"/api/perfis/{a}", headers=h).json()["perfil"]
    assert client.post(f"/api/perfis/{a}/archive", headers=h,
                       json={"version": p["version"]}).status_code == 200
    r = item(client, h, "avatar", a, status=409)
    assert r["error"]["code"] == "perfil_archived"


def test_produtos_e_vozes_filtro(client, owner):
    h = owner[1]
    a, b, pa, pb, ps = _tres(client, h, "produto")
    todos = listar(client, h, "produtos")
    assert ids(todos) == {pa["id"], pb["id"], ps["id"]}
    assert {i["id"]: i["perfilNome"] for i in itens(todos)}[ps["id"]] is None
    assert ids(listar(client, h, "produtos", perfilId=b)) == {pb["id"]}
    assert ids(listar(client, h, "produtos", perfilId="sem")) == {ps["id"]}
    assert ids(listar(client, h, "produtos", q="produto a")) == {pa["id"]}

    va = item(client, h, "voz", a, name="Voz A")
    vs = item(client, h, "voz", None, name="Voz sem")
    assert ids(listar(client, h, "vozes")) == {va["id"], vs["id"]}
    assert ids(listar(client, h, "vozes", perfilId="sem")) == {vs["id"]}
    assert itens(listar(client, h, "vozes", perfilId=a))[0]["perfilNome"] == "Perfil-A"


def test_nome_de_voz_unico_na_agencia(client, owner):
    h = owner[1]
    a, b = perfil(client, h, "perfil-a"), perfil(client, h, "perfil-b")
    item(client, h, "voz", a, name="Ana vendas")
    for pid in (b, None):
        r = item(client, h, "voz", pid, name="ana VENDAS", status=409)
        assert r["error"]["code"] == "voz_nome_em_uso"
    r = client.post(f"/api/perfis/{b}/vozes", headers=h,
                    json={"name": "Ana vendas", "origem": "gravacao", "tom": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "voz_nome_em_uso"


# ---- PATCH do perfil base (T024) ----

def _versao(db, entity_type: str, entity_id: str, n: int) -> EntityVersion:
    return db.scalar(select(EntityVersion).where(
        EntityVersion.entity_type == entity_type,
        EntityVersion.entity_id == uuid.UUID(entity_id), EntityVersion.version == n))


def test_patch_perfil_base_versionado_e_revert_so_do_dono(client, owner, member, db):
    h, hm = owner[1], member[1]
    a, b = perfil(client, h, "perfil-a"), perfil(client, h, "perfil-b")
    av = item(client, h, "avatar", a)
    # O membro muda o perfil base.
    r = client.patch(f"/api/assets/{av['id']}", headers=hm,
                     json={"version": av["version"], "perfilId": b})
    assert r.status_code == 200, r.text
    novo = r.json()["asset"]
    assert novo["perfilId"] == b and novo["perfilNome"] == "Perfil-B"
    v = _versao(db, "asset", av["id"], novo["version"])
    assert v.before["perfil_id"] == a and v.after["perfil_id"] == b
    # Sem perfil base.
    r = client.patch(f"/api/assets/{av['id']}", headers=hm,
                     json={"version": novo["version"], "perfilId": None})
    assert r.status_code == 200 and r.json()["asset"]["perfilId"] is None
    atual = r.json()["asset"]
    # Perfil inexistente → 400.
    r = client.patch(f"/api/assets/{av['id']}", headers=hm,
                     json={"version": atual["version"], "perfilId": str(uuid.uuid4())})
    assert r.status_code == 400 and r.json()["error"]["code"] == "perfil_invalido"
    # O membro não reverte; o dono reverte e o perfil base volta.
    corpo = {"version": atual["version"], "toVersion": 1}
    assert client.post(f"/api/assets/{av['id']}/revert", headers=hm,
                       json=corpo).status_code == 403
    r = client.post(f"/api/assets/{av['id']}/revert", headers=h, json=corpo)
    assert r.status_code == 200, r.text
    assert r.json()["asset"]["perfilId"] == a


def test_patch_perfil_base_produto_e_voz(client, owner, member):
    h, hm = owner[1], member[1]
    a, b = perfil(client, h, "perfil-a"), perfil(client, h, "perfil-b")
    p = item(client, h, "produto", a)
    r = client.patch(f"/api/produtos/{p['id']}", headers=hm,
                     json={"version": p["version"], "perfilId": None})
    assert r.status_code == 200, r.text
    assert r.json()["perfilId"] is None and r.json()["perfilNome"] is None
    r = client.post(f"/api/produtos/{p['id']}/revert", headers=h,
                    json={"version": r.json()["version"], "toVersion": p["version"]})
    assert r.status_code == 200, r.text
    assert r.json()["perfilId"] == a

    v = item(client, h, "voz", None)
    r = client.patch(f"/api/vozes/{v['id']}", headers=hm,
                     json={"version": v["version"], "perfilId": b})
    assert r.status_code == 200, r.text
    assert r.json()["perfilId"] == b and r.json()["perfilNome"] == "Perfil-B"
    r = client.post(f"/api/vozes/{v['id']}/revert", headers=h,
                    json={"version": r.json()["version"], "toVersion": v["version"]})
    assert r.status_code == 200, r.text
    assert r.json()["perfilId"] is None


def test_item_de_perfil_arquivado_continua_editavel(client, owner):
    h = owner[1]
    a = perfil(client, h, "perfil-a")
    av, v = item(client, h, "avatar", a), item(client, h, "voz", a)
    p = client.get(f"/api/perfis/{a}", headers=h).json()["perfil"]
    assert client.post(f"/api/perfis/{a}/archive", headers=h,
                       json={"version": p["version"]}).status_code == 200
    r = client.patch(f"/api/assets/{av['id']}", headers=h,
                     json={"version": av["version"], "name": "Outra"})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/vozes/{v['id']}", headers=h,
                     json={"version": v["version"], "tom": "calma"})
    assert r.status_code == 200, r.text
    assert listar(client, h, "assets", tipo="avatar", perfilId=a)["items"][0]["name"] == "Outra"


# ---- rotas por perfil obsoletas (T035) ----

def test_rotas_por_perfil_obsoletas_e_iguais(client, owner):
    h = owner[1]
    a, b, *_ = _tres(client, h, "avatar")
    for i, pid in enumerate((a, b, None)):
        item(client, h, "produto", pid, name=f"produto {i}")
    item(client, h, "voz", a, name="Voz A")
    item(client, h, "voz", None, name="Voz sem")
    pares = (("assets", {"tipo": "avatar"}), ("produtos", {}), ("vozes", {}))
    for rota, extra in pares:
        antiga = client.get(f"/api/perfis/{a}/{rota}", headers=h, params=extra).json()
        nova = listar(client, h, rota, perfilId=a, **extra)
        assert antiga == nova, rota
        assert ids(antiga)
    spec = client.app.openapi()["paths"]
    base = "/api/perfis/{perfil_id}"
    obsoletas = {(f"{base}/assets", "get"), (f"{base}/assets", "post"),
                 (f"{base}/assets/arquivo", "post"), (f"{base}/produtos", "get"),
                 (f"{base}/produtos", "post"), (f"{base}/vozes", "get"),
                 (f"{base}/vozes", "post")}
    for caminho, metodo in obsoletas:
        assert spec[caminho][metodo].get("deprecated") is True, (caminho, metodo)
    novas = {("/api/assets", "get"): "assets_listar_agencia",
             ("/api/assets", "post"): "assets_criar_agencia",
             ("/api/assets/arquivo", "post"): "assets_criar_arquivo_agencia",
             ("/api/produtos", "get"): "produtos_listar_agencia",
             ("/api/produtos", "post"): "produtos_criar_agencia",
             ("/api/vozes", "get"): "vozes_listar_agencia",
             ("/api/vozes", "post"): "vozes_criar_agencia",
             ("/api/estudio/resumo", "get"): "estudio_resumo"}
    for (caminho, metodo), op in novas.items():
        assert spec[caminho][metodo]["operationId"] == op
        assert not spec[caminho][metodo].get("deprecated")


def test_imagens_da_agencia(client, owner):
    h = owner[1]
    a, b = perfil(client, h, "perfil-a"), perfil(client, h, "perfil-b")
    fa = item(client, h, "fundo", a, name="Fundo A")
    fs = item(client, h, "fundo", None, name="Fundo sem")
    mb = item(client, h, "marca_dagua", b, name="Selo B")
    arq = item(client, h, "fundo", None, name="Arquivado")
    assert client.post(f"/api/assets/{arq['id']}/archive", headers=h,
                       json={"version": arq["version"]}).status_code == 200

    def assets_de(lista):
        return {i["assetId"] for i in lista["items"]}

    todos = listar(client, h, "assets/imagens", tipo=["fundo", "marca_dagua"])
    assert assets_de(todos) == {fa["id"], fs["id"], mb["id"]}
    nomes = {i["assetId"]: (i["perfilId"], i["perfilNome"]) for i in todos["items"]}
    assert nomes[fs["id"]] == (None, None) and nomes[mb["id"]] == (b, "Perfil-B")
    assert assets_de(listar(client, h, "assets/imagens", tipo="fundo")) == {fa["id"], fs["id"]}
    assert assets_de(listar(client, h, "assets/imagens", tipo="fundo",
                            perfilId="sem")) == {fs["id"]}
    assert assets_de(listar(client, h, "assets/imagens", tipo="fundo", q="fundo a")) \
        == {fa["id"]}
    # A rota por perfil (obsoleta) dá o mesmo que a nova filtrada.
    antiga = client.get(f"/api/perfis/{a}/assets/imagens", headers=h,
                        params={"tipo": "fundo"}).json()
    assert antiga == listar(client, h, "assets/imagens", tipo="fundo", perfilId=a)
    spec = client.app.openapi()["paths"]
    assert spec["/api/perfis/{perfil_id}/assets/imagens"]["get"]["deprecated"] is True
    assert spec["/api/assets/imagens"]["get"]["operationId"] == "assets_imagens_agencia"
    assert listar(client, h, "assets/imagens", status=400)["error"]["code"] == \
        "validation_error"  # tipo é obrigatório
