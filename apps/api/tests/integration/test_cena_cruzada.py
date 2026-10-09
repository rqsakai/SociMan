"""Cena da biblioteca da agência (spec 029, T027, US3, research R6): itens de qualquer perfil base
ou sem nenhum, os padrões e as proibidas do perfil base da cena, o aviso `sem_perfil_base`, as
recusas que continuam, o vínculo com o conteúdo de outro perfil, "onde é usado" com o perfil,
o PATCH do perfil base (versionado, revert do dono), a lista da agência, as propostas pelo perfil
base atual e as rotas antigas por perfil `deprecated` (T035)."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    ACHADINHOS,
    COZINHA,
    _buckets,
    acao,
    add_file,
    base,
    corpo_cena,
    criar_perfil,
    get,
    member,
    montar_perfil,
    owner,
    patch,
)
from integration.geracao_helpers import motores  # noqa: F401 — fixture
from integration.test_cenas_usos import _hist, _put, video_proprio
from integration.test_produtos_cenas import _aprovado, _catalogo
from sociman_api.cenas.models import ESTILO_PADRAO, NEGATIVE_PADRAO
from sociman_api.produtos.models import ProdutoVariante

ESTILO_B = "B style: handheld, bright daylight"
NEGATIVE_B = "B negative: blur"


def _avatar_sem_perfil(client, h) -> tuple[dict, dict]:
    r = client.post("/api/assets", headers=h, json={
        "tipo": "avatar", "name": "Avatar da agência", "prompt": ACHADINHOS, "perfilId": None})
    assert r.status_code == 201, r.text
    avatar = r.json()["asset"]
    assert avatar["perfilId"] is None
    return avatar, add_file(client, h, avatar["id"], role="referencia", look="Corpo inteiro")


def _padroes(client, h, perfil_id) -> None:
    r = client.put(f"/api/perfis/{perfil_id}/cenas/padroes", headers=h,
                   json={"version": 0, "estilo": ESTILO_B, "negative": NEGATIVE_B})
    assert r.status_code == 200, r.text


def _criar(client, h, status=201, **body) -> dict:
    r = client.post("/api/cenas", headers=h, json=body)
    assert r.status_code == status, r.text
    return r.json()


def _lista(client, h, status=200, **params) -> dict:
    r = client.get("/api/cenas", headers=h, params=params)
    assert r.status_code == status, r.text
    return r.json()


def _codigos(cena) -> set[str]:
    return {a["codigo"] for a in cena["avisos"]}


def _cena_b(client, h, base, a, avatar, look, produto, **kw) -> dict:
    """Cena com perfil base B (`base`, proibida "milagre"), o cenário de A, o avatar sem perfil e
    o produto aprovado de A."""
    corpo = corpo_cena(base, avatarId=avatar["id"], avatarArquivoId=look["id"],
                       cenarioId=a["cenario"]["id"], acao="says milagre and vapor",
                       **_catalogo(produto))
    return _criar(client, h, perfilId=base["perfil"]["id"], **(corpo | kw))


def test_cena_com_itens_de_outros_perfis(client, base, motores):
    h, pid_b = base["h"], base["perfil"]["id"]
    a = montar_perfil(client, h, "perfila", proibida="vapor")
    _padroes(client, h, pid_b)
    avatar, look = _avatar_sem_perfil(client, h)
    produto = _aprovado(client, h, a["perfil"]["id"], motores)

    cena = _cena_b(client, h, base, a, avatar, look, produto)
    assert cena["perfilId"] == pid_b and cena["perfilNome"] == base["perfil"]["name"]
    assert cena["avatar"]["id"] == avatar["id"] and cena["cenario"]["id"] == a["cenario"]["id"]
    assert cena["produto"]["id"] == produto["id"]
    texto = cena["prompt"]["texto"]
    assert texto.startswith(ACHADINHOS) and COZINHA in texto
    assert produto["ficha"]["descricaoPrompt"] in texto
    # padrões e proibidas do perfil base B, não os de A
    assert ESTILO_B in texto and cena["prompt"]["negative"].startswith(NEGATIVE_B)
    proibidas = [x for x in cena["avisos"] if x["codigo"] == "proibida"]
    assert [x["detalhe"]["palavras"] for x in proibidas] == [["milagre"]]
    assert "sem_perfil_base" not in _codigos(cena)
    # editar continua aceitando os itens de outros perfis
    pronta = acao(client, h, patch(client, h, cena, cenarioId=a["cenario"]["id"],
                                   cenarioArquivoId=a["cenario_file"]["id"]), "pronta")
    assert pronta["status"] == "pronta"


def test_cena_sem_perfil_base(client, base):
    h = base["h"]
    cena = _criar(client, h, **corpo_cena(base, acao="says milagre"))
    assert cena["perfilId"] is None and cena["perfilNome"] is None
    aviso = next(x for x in cena["avisos"] if x["codigo"] == "sem_perfil_base")
    assert aviso["mensagem"] == "Sem perfil base: sem padrões nem guia"
    assert "proibida" not in _codigos(cena)  # sem guia, sem proibidas
    assert ESTILO_PADRAO in cena["prompt"]["texto"]
    assert cena["prompt"]["negative"].startswith(NEGATIVE_PADRAO)
    # o fluxo de status segue igual
    assert acao(client, h, cena, "pronta")["status"] == "pronta"


def test_recusas_que_continuam(client, db, base, motores):
    h = base["h"]
    a = montar_perfil(client, h, "perfila", proibida=None)
    # tipo errado
    for campo, valor in (("avatarId", a["cenario"]["id"]), ("cenarioId", a["avatar"]["id"])):
        r = _criar(client, h, status=422, **corpo_cena(base, **{campo: valor,
                                                               "avatarArquivoId": None}))
        assert r["error"]["details"]["field"] == campo
    # produto de A ainda não aprovado
    from integration.produtos_helpers import criar

    rascunho = criar(client, h, a["perfil"]["id"], n_fotos=1)
    r = _criar(client, h, status=422, **corpo_cena(base, **_catalogo(rascunho, variante=None)))
    assert r["error"]["details"]["field"] == "produtoId"
    # variante sem recorte
    produto = _aprovado(client, h, a["perfil"]["id"], motores)
    variante = db.get(ProdutoVariante, uuid.UUID(produto["variantes"][0]["id"]))
    variante.recorte_image_id = None
    db.commit()
    r = _criar(client, h, status=422, **corpo_cena(base, **_catalogo(produto)))
    assert r["error"]["details"]["field"] == "produtoVarianteId"
    # perfil base que não existe
    r = _criar(client, h, status=400, perfilId=str(uuid.uuid4()), **corpo_cena(base))
    assert r["error"]["code"] == "perfil_invalido"


def test_conteudo_de_outro_perfil_usa_a_cena(client, db, base):
    h = base["h"]
    cena = acao(client, h, _criar(client, h, perfilId=base["perfil"]["id"],
                                  **corpo_cena(base)), "pronta")
    c_perfil = criar_perfil(client, h, "perfilc")
    sem = acao(client, h, _criar(client, h, **corpo_cena(base, nome="Sem perfil")), "pronta")
    conteudo = video_proprio(db, c_perfil["id"])
    out = _put(client, h, conteudo.id, 1, [cena["id"], sem["id"]])
    assert {i["id"] for i in out["items"]} == {cena["id"], sem["id"]}
    assert get(client, h, cena["id"])["status"] == "usada"
    hist = _hist(db, conteudo.id)[-1]
    assert set(hist.details["cenas"]["depois"]) == {cena["id"], sem["id"]}
    assert _hist(db, cena["id"])[-1].details["uso"]["conteudoId"] == str(conteudo.id)


def test_onde_e_usado_lista_as_cenas_de_todos_os_perfis(client, base):
    h, pid_b = base["h"], base["perfil"]["id"]
    a = montar_perfil(client, h, "perfila", proibida=None)
    corpo = corpo_cena(base, cenarioId=a["cenario"]["id"], cenarioArquivoId=None)
    _criar(client, h, perfilId=pid_b, **corpo)
    _criar(client, h, perfilId=pid_b, **(corpo | {"nome": "Outra"}))
    _criar(client, h, **(corpo | {"nome": "Sem perfil"}))
    r = client.get(f"/api/assets/{a['cenario']['id']}", headers=h)
    assert r.status_code == 200, r.text
    usos = sorted((u for u in r.json()["usos"] if u["origem"] == "cena"),
                  key=lambda u: u["rotulo"])
    cenario = a["cenario"]["id"]
    assert [(u["rotulo"], u["href"]) for u in usos] == [
        ("1 cena", f"/app/estudio/cenas?perfil=sem&cenarioId={cenario}"),
        ("2 cenas", f"/app/estudio/cenas?perfil={pid_b}&cenarioId={cenario}")]
    assert [u.get("perfilNome") for u in usos] == [None, base["perfil"]["name"]]


def test_patch_do_perfil_base_e_revert(client, db, base, member):
    h, pid_b = base["h"], base["perfil"]["id"]
    _padroes(client, h, pid_b)
    cena = _criar(client, h, perfilId=pid_b, **corpo_cena(base))
    assert ESTILO_B in cena["prompt"]["texto"]
    # o membro também muda o perfil base; nulo = nenhum
    r = client.patch(f"/api/cenas/{cena['id']}", headers=member[1],
                     json={"version": cena["version"], "perfilId": None})
    assert r.status_code == 200, r.text
    sem = r.json()
    assert sem["perfilId"] is None and "sem_perfil_base" in _codigos(sem)
    assert ESTILO_B not in sem["prompt"]["texto"]
    ultima = _hist(db, cena["id"])[-1]
    assert "perfil_id" in ultima.changed_fields
    # inexistente → 400; arquivado é aceito
    r = client.patch(f"/api/cenas/{cena['id']}", headers=h,
                     json={"version": sem["version"], "perfilId": str(uuid.uuid4())})
    assert r.status_code == 400 and r.json()["error"]["code"] == "perfil_invalido"
    arquivado = criar_perfil(client, h, "arquivado")
    r = client.post(f"/api/perfis/{arquivado['id']}/archive", headers=h, json={"version": 1})
    assert r.status_code == 200, r.text
    no_arquivado = patch(client, h, sem, perfilId=arquivado["id"])
    assert no_arquivado["perfilId"] == arquivado["id"]
    assert patch(client, h, no_arquivado, nome="Ainda editável")["nome"] == "Ainda editável"
    # o revert é do dono e volta o perfil base
    r = client.post(f"/api/cenas/{cena['id']}/revert", headers=member[1],
                    json={"version": no_arquivado["version"] + 1, "toVersion": 1})
    assert r.status_code == 403
    r = client.post(f"/api/cenas/{cena['id']}/revert", headers=h,
                    json={"version": no_arquivado["version"] + 1, "toVersion": 1})
    assert r.status_code == 200, r.text
    assert r.json()["perfilId"] == pid_b and ESTILO_B in r.json()["prompt"]["texto"]


def test_lista_da_agencia(client, base):
    h, pid_b = base["h"], base["perfil"]["id"]
    a = montar_perfil(client, h, "perfila", proibida=None)
    de_b = _criar(client, h, perfilId=pid_b, **corpo_cena(base, nome="De B"))
    de_a = _criar(client, h, perfilId=a["perfil"]["id"], **corpo_cena(base, nome="De A"))
    sem = _criar(client, h, **corpo_cena(base, nome="Sem"))
    todas = _lista(client, h)["items"]
    assert {c["id"] for c in todas} == {de_b["id"], de_a["id"], sem["id"]}
    assert {c["id"]: c["perfilNome"] for c in todas} == {
        de_b["id"]: base["perfil"]["name"], de_a["id"]: a["perfil"]["name"], sem["id"]: None}
    assert [c["id"] for c in _lista(client, h, perfilId="sem")["items"]] == [sem["id"]]
    assert [c["id"] for c in _lista(client, h, perfilId=pid_b)["items"]] == [de_b["id"]]
    assert _lista(client, h, status=400, perfilId="x")["error"]["code"] == "invalid_query"
    erro = _lista(client, h, status=400, perfilId=str(uuid.uuid4()))["error"]
    assert erro["code"] == "perfil_invalido"
    # filtros e cursor da 010 continuam
    assert [c["id"] for c in _lista(client, h, q="de a")["items"]] == [de_a["id"]]
    p1 = _lista(client, h, limit=2)
    p2 = _lista(client, h, limit=2, cursor=p1["nextCursor"])
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1 and p2["nextCursor"] is None
    assert {c["id"] for c in p1["items"] + p2["items"]} == {de_b["id"], de_a["id"], sem["id"]}


def test_propostas_pelo_perfil_base_atual(client, base):
    h, pid_b = base["h"], base["perfil"]["id"]
    cena = _criar(client, h, perfilId=pid_b, **corpo_cena(base))
    r = client.post("/api/anotacoes", headers=h, json={
        "alvoTipo": "cena", "alvoId": cena["id"], "texto": "Trocar a luz"})
    assert r.status_code == 201, r.text
    nota = r.json()["anotacao"]

    def ids(**params):
        r = client.get("/api/anotacoes", headers=h, params=params)
        assert r.status_code == 200, r.text
        return [x["id"] for x in r.json()["anotacoes"]]

    assert ids(perfilId=pid_b) == [nota["id"]] and ids(perfilId="sem") == []
    patch(client, h, cena, perfilId=None)
    assert ids(perfilId=pid_b) == [] and ids(perfilId="sem") == [nota["id"]]
    r = client.get("/api/anotacoes/resumo", headers=h, params={"perfilId": "sem"})
    assert r.status_code == 200 and r.json()["abertas"] == 1
    lida = client.get(f"/api/anotacoes/{nota['id']}", headers=h).json()["anotacao"]
    assert lida["perfilId"] is None  # o perfil base atual do alvo
    r = client.get("/api/anotacoes", headers=h, params={"perfilId": "x"})
    assert r.status_code == 400


def test_rotas_por_perfil_deprecated_respondem_igual(client, base):
    """T035: as rotas antigas por perfil equivalem à rota nova com `perfilId = {id}`."""
    h, pid_b = base["h"], base["perfil"]["id"]
    r = client.post(f"/api/perfis/{pid_b}/cenas", headers=h, json=corpo_cena(base))
    assert r.status_code == 201, r.text
    antiga = r.json()
    assert antiga["perfilId"] == pid_b
    _criar(client, h, **corpo_cena(base, nome="Sem perfil"))
    r = client.get(f"/api/perfis/{pid_b}/cenas", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == _lista(client, h, perfilId=pid_b)
    # o mesmo comportamento de antes: perfil inexistente → 404; arquivado não cria
    r = client.get(f"/api/perfis/{uuid.uuid4()}/cenas", headers=h)
    assert r.status_code == 404
    arquivado = criar_perfil(client, h, "arquivado")
    client.post(f"/api/perfis/{arquivado['id']}/archive", headers=h, json={"version": 1})
    r = client.post(f"/api/perfis/{arquivado['id']}/cenas", headers=h, json=corpo_cena(base))
    assert r.status_code == 409 and r.json()["error"]["code"] == "perfil_archived"
    ops = {op["operationId"]: op for path in client.get("/api/openapi.json").json()["paths"]
           .values() for op in path.values() if isinstance(op, dict) and "operationId" in op}
    assert ops["cenas_list"].get("deprecated") is True
    assert ops["cenas_create"].get("deprecated") is True
    assert not ops["cenas_listar_agencia"].get("deprecated")
    assert not ops["cenas_criar_agencia"].get("deprecated")
