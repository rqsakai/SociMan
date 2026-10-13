"""Fluxo do roteiro com os serviços falsos (spec 011): US1 (plano e portão TEXTO, T021), US2
(narração, T025), US3 (keyframes, T031) e US6 (três configurações, T047). Nada chama serviço
real."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from sqlalchemy import select

from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    aprovar,
    controle,
    criar_roteiro,
    editar,
    escolher_keyframes,
    levar_ate,
    montar,
    motores,
    owner,
    produto_aprovado,
    rodar_ate,
    roteiro_planejado,
    ver_roteiro,
    voz_aprovada,
)
from sociman_api import history
from sociman_api.geracao.models import Audio, Geracao, GeracaoCandidato, GeracaoStatus
from sociman_api.ia.models import IaChamada
from sociman_api.roteiros import tempos


def _err(r) -> str:
    return r.json()["error"]["code"]


def test_plano_e_portao_texto(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=2)
    outro = produto_aprovado(client, h, motores, b["perfil_id"], name="bolsa_palha")
    rot = criar_roteiro(client, h, b, produtos=[{"produtoId": b["produto"]["id"]},
                                                {"produtoId": outro["id"]}])
    assert rot["status"] == "rascunho" and rot["voz"]["id"] == b["voz"]["id"]
    assert rot["portoes"] == {"texto": True, "narracao": True, "keyframes": True,
                              "clipes": True, "final": True} and rot["modo"] == "revisar"
    assert [p["produtoId"] for p in rot["produtos"]] == [b["produto"]["id"], outro["id"]]

    rot = acao(client, h, rot, "planejar")
    assert rot["status"] == "planejando"
    assert [g["passo"] for g in rot["geracoesAbertas"]] == ["roteiro.plano"]
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_texto")
    assert len(rot["frases"]) == 4 and len(rot["posicoes"]) == 4
    reaproveitadas = [p for p in rot["posicoes"] if p["reaproveitada"]]
    assert len(reaproveitadas) == 1
    assert reaproveitadas[0]["cena"]["id"] in {c["id"] for c in b["cenas"]}
    assert [p["frases"] for p in rot["posicoes"]] == [[0], [1], [2], [3]]
    novas = [p["cena"] for p in rot["posicoes"] if not p["reaproveitada"]]
    assert all(c["status"] == "rascunho" and c["perfilId"] == b["perfil_id"] for c in novas)
    v_cena = history.list_versions(db, "cena", uuid.UUID(novas[0]["id"]))[0]
    assert v_cena.actor_user_id == owner[0].id and v_cena.details["ia"]["passo"] == \
        "roteiro.plano"
    # A chamada ficou no registro da 008, ligada à geração, com custo.
    g = db.scalar(select(Geracao).where(Geracao.passo == "roteiro.plano"))
    chamada = db.scalar(select(IaChamada).where(IaChamada.geracao_id == g.id))
    assert chamada is not None and chamada.custo_usd is not None
    assert chamada.desfecho.value == "aplicada"

    # Edição de frase e reordenação de cenas, com histórico; a regra das frases vale.
    pos = rot["posicoes"]
    trocadas = [{"cenaId": pos[1]["cena"]["id"], "frases": [0]},
                {"cenaId": pos[0]["cena"]["id"], "frases": [1]},
                {"cenaId": pos[2]["cena"]["id"], "frases": [2, 3]}]
    frases = ["Achei o vestido perfeito!", *rot["frases"][1:]]
    rot = editar(client, h, rot, frases=frases, posicoes=trocadas)
    assert rot["frases"][0] == "Achei o vestido perfeito!" and len(rot["posicoes"]) == 3
    assert rot["status"] == "aguardando_texto"
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h, json={
        "version": rot["version"], "posicoes": [{"cenaId": pos[0]["cena"]["id"],
                                                 "frases": [0, 2]},
                                                {"cenaId": pos[1]["cena"]["id"],
                                                 "frases": [1, 3]}]})
    assert r.status_code == 400 and _err(r) == "invalid_roteiro"
    assert r.json()["error"]["details"]["field"] == "posicoes"
    versoes = client.get(f"/api/roteiros/{rot['id']}/versoes", headers=h).json()["items"]
    acoes = [v["details"].get("acao") for v in versoes]
    assert acoes[:3] == ["updated", "plano", "planejar"]

    # Aprovar o TEXTO registra quem aprovou e leva à narração.
    r = client.post(f"/api/roteiros/{rot['id']}/aprovar", headers=h,
                    json={"version": rot["version"], "portao": "narracao"})
    assert r.status_code == 409 and _err(r) == "portao_fora_de_hora"
    rot = aprovar(client, h, rot, "texto")
    assert rot["status"] == "narrando"
    assert [g["passo"] for g in rot["geracoesAbertas"]] == ["roteiro.narracao"]
    v = client.get(f"/api/roteiros/{rot['id']}/versoes", headers=h).json()["items"][0]
    assert v["details"] == {"acao": "aprovar", "portao": "texto"}
    assert v["autor"]["id"] == str(owner[0].id)
    # A cena do detalhe traz a versão (o `alvoVersion` da escolha do keyframe) e as referências.
    c = rot["posicoes"][0]["cena"]
    detalhe_cena = client.get(f"/api/cenas/{c['id']}", headers=h).json()
    assert c["version"] == detalhe_cena["version"]
    recorte = b["produto"]["variantes"][0]["recorte"]["imageId"]
    if recorte:
        r = client.patch(f"/api/cenas/{c['id']}", headers=h, json={
            "version": detalhe_cena["version"], "keyframeRefs": [recorte]})
        assert r.status_code == 200, r.text
        c = ver_roteiro(client, h, rot["id"])["posicoes"][0]["cena"]
        assert c["version"] == r.json()["version"]
        assert c["keyframeRefs"] == r.json()["keyframeRefs"]
        [ref] = c["keyframeRefs"]
        assert ref["imageId"] == recorte and ref["removida"] is False and ref["thumbUrl"]

    # A lista da agência (AI Studio › Vídeos): todos, por perfil e "sem perfil".
    r = client.get("/api/roteiros", headers=h, params={"perfilId": b["perfil_id"]})
    assert r.status_code == 200, r.text
    [item] = r.json()["itens"]
    assert item["id"] == rot["id"] and item["perfilNome"] == "Bia"
    assert client.get("/api/roteiros", headers=h, params={"perfilId": "sem"}).json()[
        "itens"] == []
    assert len(client.get("/api/roteiros", headers=h, params={"limit": 5}).json()["itens"]) == 1
    assert client.get("/api/roteiros", headers=h, params={"archived": True}).json()[
        "itens"] == []


def test_produto_desaprovado_limite_e_tentar_de_novo(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    # Produto que deixou de estar aprovado: o plano é recusado com o nome (US1-7).
    rot = criar_roteiro(client, h, b)
    p = client.get(f"/api/produtos/{b['produto']['id']}", headers=h).json()
    r = client.post(f"/api/produtos/{p['id']}/arquivar", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/roteiros/{rot['id']}/planejar", headers=h,
                    json={"version": rot["version"]})
    assert r.status_code == 409 and _err(r) == "produto_fora_de_aprovado"
    assert "Short canelado" in r.json()["error"]["message"]
    p = client.get(f"/api/produtos/{p['id']}", headers=h).json()
    client.post(f"/api/produtos/{p['id']}/restaurar", headers=h, json={"version": p["version"]})

    # O limite de cenas (FR-047): a IA propôs 10, ficam 8, com aviso.
    rot = criar_roteiro(client, h, b, brief="muitas cenas")
    rot = acao(client, h, rot, "planejar")
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_texto")
    assert len(rot["posicoes"]) == 8 and len(rot["frases"]) == 10
    assert rot["posicoes"][-1]["frases"] == [7, 8, 9]
    assert rot["avisos"][0]["code"] == "limite_cenas"
    extra = {"cenaId": rot["posicoes"][0]["cena"]["id"], "frases": [9]}
    posicoes = [{"cenaId": p["cena"]["id"], "frases": p["frases"]} for p in rot["posicoes"]]
    posicoes[-1]["frases"] = [7, 8]
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h,
                     json={"version": rot["version"], "posicoes": [*posicoes, extra]})
    assert r.status_code == 409 and _err(r) == "limite_cenas"

    # Uma falha no plano: o roteiro vai a `falhou(plano)` e o "Tentar de novo" retoma dele.
    rot = criar_roteiro(client, h, b, brief="cena inexistente")
    rot = acao(client, h, rot, "planejar")
    rot = rodar_ate(client, h, motores, rot["id"], "falhou")
    assert rot["etapaFalhou"] == "plano" and rot["erro"]["code"] == "entrada_invalida"
    rot = editar(client, h, rot, brief="Mostrar o vestido")
    rot = acao(client, h, rot, "tentar-de-novo")
    assert rot["status"] == "planejando" and rot["erro"] is None
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_texto")
    planos = db.scalars(select(Geracao).where(Geracao.alvo_id == uuid.UUID(rot["id"]))).all()
    assert len(planos) == 2


def _paragrafos(m) -> list:
    return [p for p in m.tts.requests if p.caminho == "/v2/tts_paragraph"]


def test_narracao(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    r = client.post(f"/api/perfis/{b['perfil_id']}/pronuncias", headers=h,
                    json={"escrita": "levinho", "falada": "lévinho"})
    assert r.status_code == 201, r.text
    rot = roteiro_planejado(client, h, motores, b)
    rot = aprovar(client, h, rot, "texto")
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_narracao")
    pedido = _paragrafos(motores)[-1].corpo
    assert pedido["sentences"] == rot["frases"]
    assert pedido["pronuncias"] == {"levinho": "lévinho"} and "velocidade" not in pedido
    n = rot["narracao"]
    assert n["velocidade"] == 1.08 and not n["desatualizada"] and n["audioUrl"]
    # O áudio já está na velocidade final e os tempos divididos por ela.
    esperados = motores.tts.tempos_esperados(rot["frases"])
    assert [round(t["inicioS"], 3) for t in n["tempos"]] == [round(a / 1.08, 3)
                                                              for a, _ in esperados]
    audio = db.scalar(select(Audio).join(Geracao, Geracao.alvo_id == uuid.UUID(rot["id"]))
                      .where(Audio.id == uuid.UUID(_audio_id(db, n["id"]))))
    assert abs(audio.duracao_ms / 1000 - n["totalS"]) < 0.1
    # As durações batem com `limites`.
    limites = tempos.limites([{"frase": t["frase"], "inicio_s": t["inicioS"],
                               "fim_s": t["fimS"]} for t in n["tempos"]],
                             [p["frases"] for p in rot["posicoes"]], n["totalS"])
    assert [p["duracaoS"] for p in rot["posicoes"]] == [lim.duracao_s for lim in limites]
    assert rot["posicoes"][0]["inicioS"] == 0

    # Editar uma frase deixa a narração desatualizada, pede outra e guarda a antiga.
    frases = [*rot["frases"][:-1], "Corre no link, é levinho!"]
    rot = editar(client, h, rot, frases=frases)
    assert rot["status"] == "narrando" and rot["narracao"]["desatualizada"]
    assert [g["passo"] for g in rot["geracoesAbertas"]] == ["roteiro.narracao"]
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_narracao")
    assert rot["narracaoAnteriores"] if "narracaoAnteriores" in rot else \
        rot["narracoesAnteriores"] == 1
    assert _paragrafos(motores)[-1].corpo["sentences"][-1] == "Corre no link, é levinho!"
    # Trocar a velocidade também; e a voz.
    rot = editar(client, h, rot, velocidade="1.00")
    assert rot["status"] == "narrando" and rot["narracao"]["desatualizada"]
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_narracao")
    assert rot["narracao"]["velocidade"] == 1.0
    outra = voz_aprovada(client, h, motores, b["perfil_id"], name="Outra voz")
    rot = editar(client, h, rot, vozId=outra["id"])
    assert rot["status"] == "narrando"
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_narracao")
    assert rot["narracao"]["vozId"] == outra["id"] and rot["narracoesAnteriores"] == 3

    # Voz sem consentimento (revogada) é recusada com o motivo.
    v = client.get(f"/api/vozes/{outra['id']}", headers=h).json()
    r = client.post(f"/api/vozes/{outra['id']}/consentimento/revogar", headers=h,
                    json={"version": v["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h,
                     json={"version": rot["version"], "vozId": outra["id"]})
    assert r.status_code == 409 and _err(r) == "consentimento_revogado"
    rot = ver_roteiro(client, h, rot["id"])
    assert rot["voz"]["revogada"] is True and rot["narracao"]["audioUrl"]  # o feito fica
    r = client.post(f"/api/roteiros/{rot['id']}/aprovar", headers=h,
                    json={"version": rot["version"], "portao": "narracao"})
    assert r.status_code == 200, r.text  # aprovar o que já existe continua


def _audio_id(db, narracao_id: str) -> str:
    from sociman_api.roteiros.models import RoteiroNarracao

    return str(db.get(RoteiroNarracao, uuid.UUID(narracao_id)).audio_id)


def _keyframes(db, rot: dict) -> list[Geracao]:
    return list(db.scalars(select(Geracao).where(Geracao.passo == "cena.keyframe")
                           .where(Geracao.params["extras"]["roteiroId"].astext == rot["id"])
                           .order_by(Geracao.created_at)))


def test_keyframes(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    rot = roteiro_planejado(client, h, motores, b)
    # A cena reaproveitada já tem keyframe (o upload pela cena, como uma cena antiga).
    reusada = next(p for p in rot["posicoes"] if p["reaproveitada"])
    rot = levar_ate(client, h, motores, rot, "aguardando_keyframes")
    gs = _keyframes(db, rot)
    assert len(gs) == 4 and all(g.n_opcoes == 2 for g in gs)
    assert all(g.status == GeracaoStatus.revisao for g in gs)
    # "Usar opção 2" grava na cena, com a geração de origem e o autor humano.
    p0 = rot["posicoes"][0]
    g0 = next(g for g in gs if str(g.alvo_id) == p0["cena"]["id"])
    det = client.get(f"/api/geracoes/{g0.id}", headers=h).json()
    cena = client.get(f"/api/cenas/{p0['cena']['id']}", headers=h).json()
    r = client.post(f"/api/geracoes/{g0.id}/escolher", headers=h, json={
        "version": det["version"], "candidatoId": det["candidatos"][1]["id"],
        "alvoVersion": cena["version"]})
    assert r.status_code == 200, r.text
    rot = ver_roteiro(client, h, rot["id"])
    p0 = rot["posicoes"][0]
    assert p0["cena"]["keyframeGeracaoId"] == str(g0.id)
    assert p0["cena"]["keyframeImageId"] == det["candidatos"][1]["imagem"]["imageId"]
    v = history.list_versions(db, "cena", uuid.UUID(p0["cena"]["id"]))[0]
    assert v.actor_user_id == owner[0].id and v.details["acao"] == "keyframe"
    # Regerar só aquela cena: geração nova com seeds novas, a anterior sai.
    p1 = rot["posicoes"][1]
    antes = next(g for g in gs if str(g.alvo_id) == p1["cena"]["id"])
    r = client.post(f"/api/roteiros/{rot['id']}/posicoes/1/keyframe/regerar", headers=h,
                    json={"version": rot["version"], "instrucao": "She smiles holding the dress"})
    assert r.status_code == 200, r.text
    db.expire_all()
    novas = [g for g in _keyframes(db, rot) if str(g.alvo_id) == p1["cena"]["id"]]
    assert len(novas) == 2 and novas[0].status == GeracaoStatus.cancelada
    assert set(novas[1].params["seeds"]).isdisjoint(antes.params["seeds"])
    assert novas[1].params["instrucao"] == "She smiles holding the dress"
    assert len(_keyframes(db, rot)) == 5  # só aquela cena gerou
    # O upload vira o keyframe sem geração (aspecto da cena; fora dele, recusado).
    rot = ver_roteiro(client, h, rot["id"])
    r = client.post(f"/api/roteiros/{rot['id']}/posicoes/2/keyframe", headers=h,
                    data={"version": str(rot["version"])},
                    files={"arquivo": ("k.png", _png(800, 800), "image/png")})
    assert r.status_code == 400 and _err(r) == "invalid_image"
    r = client.post(f"/api/roteiros/{rot['id']}/posicoes/2/keyframe", headers=h,
                    data={"version": str(rot["version"])},
                    files={"arquivo": ("k.png", _png(1104, 1920), "image/png")})
    assert r.status_code == 200, r.text
    rot = r.json()
    assert rot["posicoes"][2]["cena"]["keyframeImageId"] and \
        rot["posicoes"][2]["cena"]["keyframeGeracaoId"] is None
    # A cena regerada voltou a gerar; aprovar exige todas as posições com keyframe.
    assert rot["status"] == "gerando_keyframes"
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")
    r = client.post(f"/api/roteiros/{rot['id']}/aprovar", headers=h,
                    json={"version": rot["version"], "portao": "keyframes"})
    assert r.status_code == 409 and _err(r) == "keyframes_pendentes"
    rot = escolher_keyframes(client, h, rot)
    rot = aprovar(client, h, rot, "keyframes")
    assert rot["status"] in ("gerando_clipes", "aguardando_clipes")
    assert all(p["cena"]["status"] == "pronta" for p in rot["posicoes"])
    v = history.list_versions(db, "cena", uuid.UUID(rot["posicoes"][3]["cena"]["id"]))[0]
    assert v.details["acao"] == "pronta_pelo_roteiro" and v.actor_user_id == owner[0].id
    assert reusada  # a reaproveitada também passou a pronta


def _png(w: int, h: int) -> bytes:
    import io

    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", (w, h), (90, 160, 90)).save(buf, format="PNG")
    return buf.getvalue()


def test_tres_configuracoes(client, db, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    # Só KEYFRAMES ligado: passa direto pelo texto e pela narração e para nos keyframes.
    so_kf = criar_roteiro(client, h, b, nome="So keyframes")
    so_kf = controle(client, h, so_kf, texto=False, narracao=False, clipes=False, final=False)
    so_kf = acao(client, h, so_kf, "planejar")
    so_kf = rodar_ate(client, h, motores, so_kf["id"], "aguardando_keyframes")
    assert so_kf["narracao"] is not None
    # Automático: a opção 1 de cada cena pelo "sistema (automático)", sem parar nos keyframes.
    auto = criar_roteiro(client, h, b, nome="Automatico")
    auto = controle(client, h, auto, modo="automatico")
    auto = acao(client, h, auto, "planejar")
    auto = rodar_ate(client, h, motores, auto["id"], ("gerando_clipes", "montando",
                                                      "finalizando", "pronto"))
    for g in _keyframes(db, auto):
        assert g.status == GeracaoStatus.escolhido
        v = history.list_versions(db, "geracao", g.id)[0]
        assert v.actor_kind == "system:roteiro" and v.details["automatico"] is True
        cand = db.get(GeracaoCandidato, g.escolhido_id)
        assert cand.numero == 1
    # Ligar um portão no meio para nele (o de clipes, no automático → revisar).
    auto = ver_roteiro(client, h, auto["id"])
    if auto["status"] == "gerando_clipes":
        auto = controle(client, h, auto, modo="revisar", texto=False, narracao=False,
                        keyframes=False, final=False)
        auto = rodar_ate(client, h, motores, auto["id"], "aguardando_clipes")
        assert auto["status"] == "aguardando_clipes"
    # Desligar o portão em que está parado = aprovar no nome de quem desligou.
    so_kf = escolher_keyframes(client, h, ver_roteiro(client, h, so_kf["id"]))
    so_kf = controle(client, h, so_kf, texto=False, narracao=False, keyframes=False,
                     clipes=False, final=False)
    assert so_kf["status"] in ("gerando_clipes", "montando")
    v = client.get(f"/api/roteiros/{so_kf['id']}/versoes", headers=h).json()["items"][0]
    assert v["details"]["aprovou"] == "keyframes" and v["autor"]["id"] == str(owner[0].id)
