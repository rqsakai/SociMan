"""Recomendações, decisões e preferências (spec 023, T041; FR-034 a FR-039): aceitar ampliar e
fixar (a hashtag no guia da conta, com a origem no histórico), fixas no máximo com e sem
`substituir`, fixar uma proibida, rejeitar com motivo, reverter, `recomendacao_mudou`, e nada
de destino ou agenda tocado."""

import uuid

from sqlalchemy import func, select

from integration.analytics_helpers import cena  # noqa: F401
from integration.aprendizado_helpers import ap, err, estagnados, membro  # noqa: F401
from integration.guia_ia_helpers import campos
from sociman_api.history import EntityVersion
from sociman_api.postagem.models import Postagem


def _cenario(ap):  # noqa: F811
    ap.tema("Marvel", ["marvel"])
    ap.tema("Games", ["games"])
    for d in range(2, 12):
        tag = d % 3 == 0
        vid = ap.post(dias=d, hora=9 + 3 * (d % 4), views=6000 if tag else 2000,
                      legenda="Marvel #matchcut" if tag else "Marvel")
        ap.classificar(vid, "Marvel")
    for d in range(12, 22):
        tag = d % 3 == 0
        vid = ap.post(dias=d, hora=9 + 3 * (d % 4), views=300 if tag else 100,
                      legenda="Games #matchcut" if tag else "Games")
        ap.classificar(vid, "Games")


def _abertas(ap, **params) -> dict[str, dict]:  # noqa: F811
    return {r["tipo"]: r for r in ap.get("recomendacoes", **params)["abertas"]}


def _decidir(ap, chave, decisao="aceita", status=200, h=None, **extra):  # noqa: F811
    r = ap.client.post(f"{ap.url}/recomendacoes/decidir", headers=h or ap.h,
                       json={"chave": chave, "decisao": decisao, "medida": "h24", **extra})
    assert r.status_code == status, r.text
    return r.json()


def _contar_destinos(db) -> tuple[int, int]:
    db.expire_all()
    return (db.scalar(select(func.count()).select_from(Postagem)),
            db.scalar(select(func.count()).select_from(EntityVersion).where(
                EntityVersion.entity_type == "postagem")))


def test_aceitar_ampliar_rejeitar_e_reverter(ap, estagnados):  # noqa: F811
    _cenario(ap)
    destinos = _contar_destinos(ap.db)
    abertas = _abertas(ap)
    amp = abertas["tema_ampliar"]
    marvel = ap.temas["Marvel"]["id"]
    assert amp["chave"] == f"tema_ampliar:perfil:{marvel}" and amp["evidencia"]["nPosts"] == 10
    assert amp["motivo"].startswith("O tema Marvel rende") and amp["oQueMuda"]
    out = _decidir(ap, amp["chave"])
    assert out["preferencias"]["temas"] == {marvel: "ampliar"}
    assert out["decisao"]["estado"] == "aceita" and out["decisao"]["evidencia"]["efeito"]
    assert "tema_ampliar" not in _abertas(ap)
    assert ap.get("preferencias")["efetivas"]["temas"] == {marvel: "ampliar"}

    rec = ap.get("recomendacoes")
    [decidida] = [d for d in rec["decididas"] if d["chave"] == amp["chave"]]
    r = ap.client.post(f"/api/aprendizado/decisoes/{decidida['id']}/revert", headers=ap.h,
                       json={"version": decidida["version"]})
    assert r.status_code == 200, r.text
    assert r.json()["preferencias"]["temas"] == {} and r.json()["decisao"]["revertidaEm"]
    assert "tema_ampliar" in _abertas(ap)  # voltou

    _decidir(ap, amp["chave"], "rejeitada", motivo="Ainda é cedo")
    assert "tema_ampliar" not in _abertas(ap)
    [rej] = [d for d in ap.get("recomendacoes")["decididas"] if d["estado"] == "rejeitada"]
    assert rej["motivo"] == "Ainda é cedo" and rej["decididoPor"]["name"] == "Dono"
    assert ap.get("preferencias")["perfil"]["temas"] == {}
    assert _contar_destinos(ap.db) == destinos  # FR-039: nada de destino ou agenda

    err_ = _decidir(ap, "tema_ampliar:perfil:" + str(uuid.uuid4()), status=409)
    assert err_["error"]["code"] == "recomendacao_mudou"


def test_fixar_vai_para_o_guia_da_conta(ap, estagnados):  # noqa: F811
    _cenario(ap)
    conta = ap.c.conta["id"]
    fixar = _abertas(ap, contaId=conta)["hashtag_fixar"]
    assert fixar["alvo"]["hashtag"] == "#matchcut" and fixar["escopo"]["contaId"] == conta
    out = _decidir(ap, fixar["chave"], contaId=conta)
    assert out["guia"] == {"nivel": "conta", "version": 1}
    guia = ap.client.get(f"/api/contas/{conta}/guia", headers=ap.h).json()["guia"]
    assert guia["campos"]["hashtagsFixas"] == ["#matchcut"]
    v = ap.db.scalars(select(EntityVersion).where(EntityVersion.entity_type == "ia_guia")).one()
    assert v.details["origem"] == "recomendacao_023" and v.details["chave"] == fixar["chave"]
    assert "hashtag_fixar" not in _abertas(ap, contaId=conta)
    # reverter a decisão não tira a fixa: avisa e leva ao guia
    [d] = [x for x in ap.get("recomendacoes", contaId=conta)["decididas"]
           if x["tipo"] == "hashtag_fixar"]
    r = ap.client.post(f"/api/aprendizado/decisoes/{d['id']}/revert", headers=ap.h,
                       json={"version": d["version"]}).json()
    assert r["aviso"] and r["linkGuia"] == f"/app/contas/{conta}/guia"
    guia = ap.client.get(f"/api/contas/{conta}/guia", headers=ap.h).json()["guia"]
    assert guia["campos"]["hashtagsFixas"] == ["#matchcut"]


def test_fixas_no_maximo_e_substituir(ap, estagnados):  # noqa: F811
    _cenario(ap)
    conta = ap.c.conta["id"]
    r = ap.client.put(f"/api/contas/{conta}/guia", headers=ap.h, json={
        "version": 0, "campos": campos(hashtagsFixas=["#taverna"], maxHashtagsFixas=1)})
    assert r.status_code == 200, r.text
    fixar = _abertas(ap, contaId=conta)["hashtag_fixar"]
    assert fixar["bloqueio"] == {"code": "fixas_no_maximo", "fixas": ["#taverna"], "maximo": 1}
    e = _decidir(ap, fixar["chave"], status=409, contaId=conta)
    assert e["error"]["code"] == "fixas_no_maximo" and e["error"]["details"]["fixas"] == [
        "#taverna"]
    _decidir(ap, fixar["chave"], contaId=conta, substituir="#taverna")
    guia = ap.client.get(f"/api/contas/{conta}/guia", headers=ap.h).json()["guia"]
    assert guia["campos"]["hashtagsFixas"] == ["#matchcut"]


def test_fixar_proibida_recusa(ap, estagnados):  # noqa: F811
    _cenario(ap)
    r = ap.client.put(f"/api/perfis/{ap.perfil_id}/guia", headers=ap.h,
                      json={"version": 0, "campos": campos(proibidas=["matchcut"])})
    assert r.status_code == 200, r.text
    conta = ap.c.conta["id"]
    fixar = _abertas(ap, contaId=conta)["hashtag_fixar"]
    e = _decidir(ap, fixar["chave"], status=400, contaId=conta)
    assert e["error"]["code"] == "ia_proibida"


def test_preferencias_patch_versoes_e_revert(ap, membro):  # noqa: F811
    marvel = ap.tema("Marvel")["id"]
    r = ap.client.patch(f"{ap.url}/preferencias", headers=ap.h, json={
        "version": 1, "temas": {marvel: "cortar"}, "hashtagsEvitar": ["#FYP", "fyp"],
        "padroes": [{"tipo": "horario", "texto": "ter–qua, 18 h–21 h"}]})
    assert r.status_code == 200, r.text
    assert r.json()["hashtagsEvitar"] == ["#fyp"] and r.json()["version"] == 2
    prefs = ap.get("preferencias")
    assert prefs["efetivas"]["janelaPreferida"] == "ter–qua, 18 h–21 h"
    conta = ap.c.conta["id"]
    r = ap.client.patch(f"{ap.url}/preferencias", headers=ap.h, params={"contaId": conta},
                        json={"version": 0, "usarDesempenho": False})
    assert r.status_code == 400
    r = ap.client.patch(f"{ap.url}/preferencias", headers=ap.h, params={"contaId": conta},
                        json={"version": 0, "hashtagsEvitar": ["#xyz"]})
    assert r.status_code == 200
    ef = ap.get("preferencias", contaId=conta)["efetivas"]
    assert ef["hashtagsEvitar"] == ["#fyp", "#xyz"] and ef["temas"] == {marvel: "cortar"}
    r = ap.client.post(f"{ap.url}/preferencias/revert", headers=ap.h,
                       json={"version": 2, "toVersion": 1})
    assert r.status_code == 200 and r.json()["temas"] == {}
    vs = ap.get("preferencias/versions")["items"]
    assert [v["action"] for v in vs] == ["reverted", "updated", "created"]
    _, hm = membro
    r = ap.client.patch(f"{ap.url}/preferencias", headers=hm, json={"version": 3})
    assert r.status_code == 403 and err(r) == "somente_dono"
    r = ap.client.patch(f"{ap.url}/preferencias", headers=ap.h,
                        json={"version": 3, "temas": {str(uuid.uuid4()): "ampliar"}})
    assert r.status_code == 400 and err(r) == "tema_invalido"
