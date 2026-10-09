"""Pedir e escolher (spec 021, T025, SC-005): o ciclo do piloto `cenario.cena` com o ComfyUI
falso; a opção vira arquivo do cenário com a versão do alvo apontando a geração; recusas."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import threading
import uuid

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    acao,
    asset,
    detalhe,
    montar,
    motores,
    owner,
    pedir,
    rodar_gpu,
)


def _revisao(client, h, motores, b, **kw) -> dict:
    g = pedir(client, h, b, **kw)
    assert g["status"] == "na_fila" and g["nOpcoes"] == 2 and g["motor"] == "comfyui"
    rodar_gpu(motores)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "revisao", g
    return g


def test_ciclo_completo_escolhe_a_opcao_2(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = _revisao(client, h, motores, b)
    assert [c["numero"] for c in g["candidatos"]] == [1, 2]
    assert len({c["seed"] for c in g["candidatos"]}) == 2
    op2 = g["candidatos"][1]
    assert (op2["imagem"]["width"], op2["imagem"]["height"]) == (768, 1344)
    assert op2["imagem"]["link"]["expiresAt"] is not None  # com validade (a limpeza apaga)
    alvo = asset(client, h, b["cenario"]["id"])
    r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                    json={"candidatoId": op2["id"], "version": g["version"],
                          "alvoVersion": alvo["version"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "escolhido" and out["escolhidoId"] == op2["id"]
    assert out["alvo"]["version"] == alvo["version"] + 1
    depois = asset(client, h, b["cenario"]["id"])
    novo = [f for f in depois["files"] if f["image"]["id"] == op2["imagem"]["imageId"]]
    # Spec 025 (T041): o `cenario.cena` grava o slot `cena` do kit (o piloto da 021 gravava
    # uma `referencia`), e o cenário fica com o kit completo.
    assert novo and novo[0]["role"] == "kit" and novo[0]["slot"] == "cena"
    assert novo[0]["geracaoId"] == g["id"] and novo[0]["origemArquivo"] == "gerado"
    assert depois["kitStatus"] == "completo"
    versoes = client.get(f"/api/assets/{b['cenario']['id']}/versions", headers=h).json()
    assert versoes["items"][0]["details"]["geracao_id"] == g["id"]
    assert versoes["items"][0]["actor"]["id"] == str(owner[0].id)
    # A opção 1 continua visível na geração.
    g2 = detalhe(client, h, g["id"])
    assert len(g2["candidatos"]) == 2
    hist = client.get(f"/api/geracoes/{g['id']}/versoes", headers=h).json()["items"]
    assert [v["details"].get("acao") for v in hist] == ["escolher", None]
    # A RAM do ComfyUI subiu e voltou (US2), e o prompt saiu com o REALISMO.
    assert motores.dockerctl.memoria == motores.dockerctl.historico[-1]
    prompt = next(iter(motores.comfy.prompts.values()))
    assert "no people" in str(prompt)


def test_recusas_da_escolha(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = _revisao(client, h, motores, b)
    alvo = asset(client, h, b["cenario"]["id"])
    c1, c2 = g["candidatos"]
    corpo = {"candidatoId": c1["id"], "version": g["version"], "alvoVersion": alvo["version"]}
    # alvo mudou → version_conflict
    r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                    json=corpo | {"alvoVersion": alvo["version"] - 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    # candidato de outra geração → 400
    outra = _revisao(client, h, motores, b)
    r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                    json=corpo | {"candidatoId": outra["candidatos"][0]["id"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "candidato_invalido"
    # escolhe; de novo → geracao_decidida
    assert client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                       json=corpo).status_code == 200
    r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                    json=corpo | {"candidatoId": c2["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "geracao_decidida"


def test_duas_escolhas_simultaneas_uma_so(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = _revisao(client, h, motores, b)
    alvo = asset(client, h, b["cenario"]["id"])
    respostas: list[int] = []

    def escolher(c):
        r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                        json={"candidatoId": c["id"], "version": g["version"],
                              "alvoVersion": alvo["version"]})
        respostas.append(r.status_code)
    ts = [threading.Thread(target=escolher, args=(c,)) for c in g["candidatos"]]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(respostas) == [200, 409]
    depois = asset(client, h, b["cenario"]["id"])
    gerados = [f for f in depois["files"] if f["slot"] == "cena"]  # spec 025: o slot `cena`
    assert len(gerados) == 1


def test_alvo_arquivado_e_alvo_incompativel(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = _revisao(client, h, motores, b)
    alvo = asset(client, h, b["cenario"]["id"])
    r = client.post(f"/api/assets/{alvo["id"]}/archive", headers=h,
                    json={"version": alvo["version"]})
    assert r.status_code == 200, r.text
    arquivado = r.json()["asset"]
    r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                    json={"candidatoId": g["candidatos"][0]["id"], "version": g["version"],
                          "alvoVersion": arquivado["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "alvo_arquivado"
    erro = pedir(client, h, b, status=409)
    assert erro["error"]["code"] == "alvo_arquivado"
    # cancelar uma aberta do alvo arquivado é aceito (FR-015)
    assert acao(client, h, g, "cancelar")["status"] == "cancelada"
    # produto no POST genérico → alvo_incompativel; passo sem aplicador → passo_indisponivel
    erro = pedir(client, h, b, status=409, alvoTipo="produto", passo="produto.flat")
    assert erro["error"]["code"] == "alvo_incompativel"
    # Spec 025: todo passo tem aplicador; o passo de avatar num cenário é incompatível.
    erro = pedir(client, h, b, status=409, passo="avatar.look")
    assert erro["error"]["code"] == "alvo_incompativel"
    # foto (não cenário) como alvo do cenario.cena → alvo_incompativel
    erro = pedir(client, h, b, status=409, alvoId=b["foto"]["id"])
    assert erro["error"]["code"] == "alvo_incompativel"


def test_referencias_e_entrada(client, owner, make_user, login, motores):
    h = owner[1]
    b = montar(client, h)
    outro = montar(client, h, slug="outro")
    erro = pedir(client, h, b, status=400, referencias=[str(uuid.uuid4())])
    assert erro["error"]["code"] == "entrada_invalida"
    assert erro["error"]["details"]["field"] == "referencias"
    # Spec 029 (R8): a foto pode ser de um item de outro perfil base da biblioteca.
    cruzada = pedir(client, h, b, referencias=[outro["foto_image_id"]], nOpcoes=1)
    acao(client, h, cruzada, "cancelar")
    erro = pedir(client, h, b, status=400, nOpcoes=3)
    assert erro["error"]["details"]["field"] == "nOpcoes"
    erro = pedir(client, h, b, status=400, extras={"quandoUsar": "x"})
    assert erro["error"]["details"]["field"] == "extras.quandoUsar"
    # Spec 025: sem instrução, a cena usa o prompt do cenário.
    vazia = pedir(client, h, b, instrucao="   ")
    assert vazia["instrucao"] == "bright bedroom"
    acao(client, h, vazia, "cancelar")
    # Com a foto de referência, o bloco é o keyframe (Qwen Edit) com o MANTER.
    g = pedir(client, h, b, referencias=[b["foto_image_id"]], nOpcoes=1)
    assert len(g["referencias"]) == 1
    rodar_gpu(motores)
    assert detalhe(client, h, g["id"])["status"] == "revisao"
    prompt = next(iter(motores.comfy.prompts.values()))
    assert "Keep the same room" in str(prompt)
