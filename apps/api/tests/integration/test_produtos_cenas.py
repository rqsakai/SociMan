"""Ponte do catálogo com as cenas da 010 (spec 012, T038, US4, R13): só produto aprovado ao
ligar, a variante com recorte, ou o catálogo ou a referência leve, "Ligar ao catálogo" numa
versão só, as regras de `pronta`/`usada`, o aviso `produto_fora_de_aprovado`, o "onde é usado" e
as cenas antigas intactas."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    base,
    cena_pronta,
    criar_cena,
    get,
    owner,
    patch,
)
from integration.geracao_helpers import motores  # noqa: F401 — fixture
from integration.produtos_helpers import com_claude, criar, rodar_tudo, ver
from integration.test_cenas_usos import _put, video_proprio


def _aprovado(client, h, perfil_id, motores, n_fotos=2) -> dict:
    com_claude(motores)
    p = criar(client, h, perfil_id, n_fotos=n_fotos, obs="sem flat")
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    r = client.post(f"/api/produtos/{p['id']}/aprovar", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 200, r.text
    return r.json()


def _catalogo(p: dict, variante: int | None = 0, **kw) -> dict:
    corpo = {"produtoNome": None, "produtoImagemId": None, "produtoId": p["id"]}
    if variante is not None:
        corpo["produtoVarianteId"] = p["variantes"][variante]["id"]
    return corpo | kw


def test_so_produto_aprovado_e_variante_valida(client, base, motores):
    h, pid = base["h"], base["perfil"]["id"]
    rascunho = criar(client, h, pid, n_fotos=1)
    r = criar_cena(client, h, base, status=422, **_catalogo(rascunho, variante=None))
    assert r["error"]["details"]["field"] == "produtoId"
    p = _aprovado(client, h, pid, motores)
    outro = _aprovado(client, h, pid, motores, n_fotos=1)
    r = criar_cena(client, h, base, status=422, **_catalogo(
        p, variante=None, produtoVarianteId=outro["variantes"][0]["id"]))
    assert r["error"]["details"]["field"] == "produtoVarianteId"
    # Catálogo e referência leve juntos: recusado.
    r = criar_cena(client, h, base, status=422, produtoId=p["id"])
    assert r["error"]["details"]["field"] == "produtoId"
    cena = criar_cena(client, h, base, **_catalogo(p))
    assert cena["produto"]["id"] == p["id"] and cena["produto"]["variante"]["corEn"] == "black"


def test_prompt_e_ingrediente_com_catalogo(client, base, motores):
    h = base["h"]
    p = _aprovado(client, h, base["perfil"]["id"], motores)
    cena = criar_cena(client, h, base, **_catalogo(p, variante=1))
    texto = cena["prompt"]["texto"]
    assert "with the product exactly as in the reference image" in texto
    assert f"{p['ficha']['descricaoPrompt']} Color: heather grey." in texto
    ing = next(i for i in cena["ingredientes"] if i["papel"] == "produto")
    assert ing["produtoId"] == p["id"] and ing["produtoVarianteId"] == p["variantes"][1]["id"]
    assert ing["assetId"] is None and ing["downloadUrl"]
    assert [i["papel"] for i in cena["ingredientes"]] == ["avatar", "produto", "cenario"]
    # Sem variante, o ingrediente é o recorte da primeira variante ativa.
    sem = criar_cena(client, h, base, **_catalogo(p, variante=None))
    ing = next(i for i in sem["ingredientes"] if i["papel"] == "produto")
    assert ing["produtoVarianteId"] == p["variantes"][0]["id"]
    assert "Color:" not in sem["prompt"]["texto"]


def test_ligar_ao_catalogo_numa_versao(client, base, motores):
    h = base["h"]
    p = _aprovado(client, h, base["perfil"]["id"], motores)
    antiga = criar_cena(client, h, base)
    prompt_antigo = antiga["prompt"]["texto"]
    assert "Panela" in prompt_antigo  # a referência leve da 010, como sempre
    hist = client.get(f"/api/cenas/{antiga['id']}/versions", headers=h).json()["items"]
    ligada = patch(client, h, antiga, **_catalogo(p))
    assert ligada["produtoNome"] is None and ligada["produtoImagemId"] is None
    assert ligada["produtoId"] == p["id"]
    hist2 = client.get(f"/api/cenas/{antiga['id']}/versions", headers=h).json()["items"]
    assert len(hist2) == len(hist) + 1


def test_pronta_volta_a_rascunho_e_usada_recusa(client, base, motores, db):
    h = base["h"]
    p = _aprovado(client, h, base["perfil"]["id"], motores)
    pronta = cena_pronta(client, h, base)
    ligada = patch(client, h, pronta, **_catalogo(p))
    assert ligada["status"] == "rascunho"
    usada = cena_pronta(client, h, base, nome="Usada")
    c = video_proprio(db, base["perfil"]["id"])
    _put(client, h, c.id, 1, [usada["id"]])
    usada = get(client, h, usada["id"])
    r = client.patch(f"/api/cenas/{usada['id']}", headers=h,
                     json={"version": usada["version"], **_catalogo(p)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cena_usada"


def test_produto_volta_a_revisao_mostra_aviso_e_usos(client, base, motores):
    h = base["h"]
    p = _aprovado(client, h, base["perfil"]["id"], motores)
    cena = criar_cena(client, h, base, nome="Com shorts", **_catalogo(p))
    assert "produto_fora_de_aprovado" not in {a["codigo"] for a in cena["avisos"]}
    # Editar a cor de uma variante devolve o produto a revisão.
    r = client.patch(f"/api/produtos/{p['id']}/variantes/{p['variantes'][0]['id']}", headers=h,
                     json={"version": p["version"], "corEn": "jet black"})
    assert r.status_code == 200 and r.json()["status"] == "revisao"
    cena = get(client, h, cena["id"])
    assert "produto_fora_de_aprovado" in {a["codigo"] for a in cena["avisos"]}
    assert "Color: jet black." in cena["prompt"]["texto"]  # rascunho: ao vivo
    p = ver(client, h, p["id"])
    assert p["usos"] == [{"origem": "cena", "rotulo": "Cena: Com shorts",
                          "href": f"/app/cenas/{cena['id']}", "bloqueia": False}]
    # Arquivar o produto não é bloqueado pelo uso.
    r = client.post(f"/api/produtos/{p['id']}/arquivar", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 200 and r.json()["estado"] == "arquivado"
    # O filtro da lista de cenas por produto.
    r = client.get(f"/api/perfis/{base['perfil']['id']}/cenas", headers=h,
                   params={"produtoId": p["id"]})
    assert [c["id"] for c in r.json()["items"]] == [cena["id"]]


def test_cena_pronta_antiga_nao_muda_o_prompt_congelado(client, base, motores):
    h = base["h"]
    pronta = cena_pronta(client, h, base)
    _aprovado(client, h, base["perfil"]["id"], motores)
    assert get(client, h, pronta["id"])["prompt"] == pronta["prompt"]
