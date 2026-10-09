"""Vínculo cena × conteúdo vídeo próprio (spec 010, T029, Q2, FR-012): `usada`/`pronta`,
histórico nos dois lados, recusas, conflito de versão e o `conteudos_get` com as cenas."""

# ruff: noqa: F811 — fixtures importadas de `cenas_helpers`

import uuid

from sqlalchemy import select

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    base,
    cena_pronta,
    criar_cena,
    get,
    montar_perfil,
    owner,
    patch,
)
from integration.postagem_helpers import criar_corte
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.history import EntityVersion


def video_proprio(db, perfil_id, titulo="Panela final") -> Conteudo:
    cid = uuid.uuid4()
    c = Conteudo(id=cid, perfil_id=uuid.UUID(perfil_id), origem=ConteudoOrigem.video_proprio,
                 titulo=titulo, video_key=f"conteudos/{cid}/video.mp4", poster_key="p.jpg",
                 duration_ms=16000, width=1080, height=1920)
    db.add(c)
    db.commit()
    return c


def _put(client, h, conteudo_id, version, ids, status=200):
    r = client.put(f"/api/conteudos/{conteudo_id}/cenas", headers=h,
                   json={"version": version, "cenaIds": ids})
    assert r.status_code == status, r.text
    return r.json()


def _hist(db, entity_id):
    return list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_id == uuid.UUID(str(entity_id))).order_by(EntityVersion.version)))


def test_ligar_e_desligar(client, db, base):
    h = base["h"]
    a = cena_pronta(client, h, base)
    b = cena_pronta(client, h, base, nome="Fecho")
    c = video_proprio(db, base["perfil"]["id"])
    out = _put(client, h, c.id, 1, [a["id"], b["id"]])
    assert {i["id"] for i in out["items"]} == {a["id"], b["id"]}
    assert {i["status"] for i in out["items"]} == {"usada"} and out["version"] == 2
    lida = get(client, h, a["id"])
    assert lida["status"] == "usada" and lida["usos"][0]["conteudoId"] == str(c.id)
    assert _hist(db, a["id"])[-1].details == {"uso": {"conteudoId": str(c.id),
                                                      "acao": "ligado"}}
    hc = _hist(db, c.id)[-1]
    assert hc.details["cenas"]["antes"] == [] and len(hc.details["cenas"]["depois"]) == 2

    detalhe = client.get(f"/api/conteudos/{c.id}", headers=h).json()["conteudo"]
    assert {x["id"] for x in detalhe["cenas"]} == {a["id"], b["id"]}
    r = client.get(f"/api/conteudos/{c.id}/cenas", headers=h)
    assert len(r.json()["items"]) == 2

    # numa cena usada, o prompt não muda (duplique); nome muda
    r = client.patch(f"/api/cenas/{a['id']}", headers=h,
                     json={"version": lida["version"], "acao": "waves"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cena_usada"
    assert patch(client, h, lida, nome="Novo")["status"] == "usada"
    r = client.post(f"/api/cenas/{a['id']}/rascunho", headers=h,
                    json={"version": lida["version"] + 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cena_usada"

    out = _put(client, h, c.id, 2, [b["id"]])
    assert [i["id"] for i in out["items"]] == [b["id"]]
    assert get(client, h, a["id"])["status"] == "pronta"
    assert _hist(db, a["id"])[-1].details["uso"]["acao"] == "desfeito"


def test_recusas(client, db, base):
    h = base["h"]
    pronta = cena_pronta(client, h, base)
    rascunho = criar_cena(client, h, base, nome="Rascunho")
    arquivada = acao(client, h, cena_pronta(client, h, base, nome="Arq"), "arquivar")
    c = video_proprio(db, base["perfil"]["id"])
    # 029 (FR-014): a cena de outro perfil base é aceita (test_cena_cruzada.py).
    for cena, codigo in ((rascunho, "cena_rascunho"), (arquivada, "cena_arquivada")):
        erro = _put(client, h, c.id, 1, [pronta["id"], cena["id"]], status=422)["error"]
        assert erro["code"] == codigo
    assert get(client, h, pronta["id"])["status"] == "pronta"  # nada mudou
    erro = _put(client, h, c.id, 9, [pronta["id"]], status=409)["error"]
    assert erro["code"] == "version_conflict"
    corte = db.get(Conteudo, criar_corte(db, base["perfil"]["id"]).id)
    erro = _put(client, h, corte.id, corte.version, [pronta["id"]], status=422)["error"]
    assert erro["code"] == "origem_invalida"


def test_revert_do_conteudo_nao_mexe_nos_usos(client, db, base):
    h = base["h"]
    a = cena_pronta(client, h, base)
    c = video_proprio(db, base["perfil"]["id"])
    r = client.patch(f"/api/conteudos/{c.id}", headers=h, json={"version": 1, "titulo": "T2"})
    assert r.status_code == 200, r.text
    _put(client, h, c.id, 2, [a["id"]])
    r = client.patch(f"/api/conteudos/{c.id}", headers=h, json={"version": 3, "titulo": "T3"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/conteudos/{c.id}/revert", headers=h,
                    json={"version": 4, "toVersion": 2})
    assert r.status_code == 200, r.text
    assert get(client, h, a["id"])["status"] == "usada"


def test_revert_da_cena_usada_recusado(client, base, db):
    h = base["h"]
    a = cena_pronta(client, h, base)
    c = video_proprio(db, base["perfil"]["id"])
    _put(client, h, c.id, 1, [a["id"]])
    lida = get(client, h, a["id"])
    r = client.post(f"/api/cenas/{a['id']}/revert", headers=h,
                    json={"version": lida["version"], "toVersion": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cena_usada"
