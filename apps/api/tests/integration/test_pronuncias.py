"""O dicionário de pronúncia do perfil (spec 011, US8, T052; FR-045, FR-019): o par fica com
histórico, a duplicata é recusada sem diferenciar maiúsculas, o pedido de narração leva o
dicionário, o texto mostrado não muda e a edição deixa a narração desatualizada."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    aprovar,
    montar,
    motores,
    owner,
    rodar_ate,
    roteiro_planejado,
    ver_roteiro,
)


def _criar(client, h, pid, escrita, falada, status=201):
    r = client.post(f"/api/perfis/{pid}/pronuncias", headers=h,
                    json={"escrita": escrita, "falada": falada})
    assert r.status_code == status, r.text
    return r.json()


def test_pronuncias_no_pedido_e_no_hash(client, owner, motores):
    h = owner[1]
    b = montar(client, h, motores, n_cenas=1)
    pid = b["perfil_id"]
    p = _criar(client, h, pid, "levinho", "lévinho")
    _criar(client, h, pid, "leve", "lévi")
    r = client.post(f"/api/perfis/{pid}/pronuncias", headers=h,
                    json={"escrita": "LEVINHO", "falada": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "pronuncia_existe"
    lista = client.get(f"/api/perfis/{pid}/pronuncias", headers=h).json()["items"]
    assert [x["escrita"] for x in lista] == ["leve", "levinho"]
    versoes = client.get(f"/api/pronuncias/{p['id']}/versoes", headers=h).json()["items"]
    assert versoes[0]["action"] == "created"

    rot = roteiro_planejado(client, h, motores, b)
    frases = rot["frases"]
    rot = aprovar(client, h, rot, "texto")
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_narracao")
    pedido = [x for x in motores.tts.requests if x.caminho == "/v2/tts_paragraph"][-1].corpo
    assert pedido["pronuncias"] == {"levinho": "lévinho", "leve": "lévi"}
    assert rot["frases"] == frases and pedido["sentences"] == frases  # a grafia não muda
    assert not rot["narracao"]["desatualizada"]

    # Uma pronúncia de palavra que está nas frases ("levinho"): a narração fica desatualizada.
    assert any("levinho" in f.lower() for f in frases)
    r = client.patch(f"/api/pronuncias/{p['id']}", headers=h,
                     json={"version": p["version"], "falada": "lévinhu"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert ver_roteiro(client, h, rot["id"])["narracao"]["desatualizada"] is True
    versoes = client.get(f"/api/pronuncias/{p['id']}/versoes", headers=h).json()["items"]
    assert [v["action"] for v in versoes] == ["updated", "created"]
    # Arquivar e restaurar, com histórico; arquivada sai do pedido.
    r = client.post(f"/api/pronuncias/{p['id']}/arquivar", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 200 and r.json()["archived"] is True
    assert [x["escrita"] for x in client.get(f"/api/perfis/{pid}/pronuncias",
                                             headers=h).json()["items"]] == ["leve"]
    r = client.post(f"/api/pronuncias/{p['id']}/restaurar", headers=h,
                    json={"version": r.json()["version"]})
    assert r.status_code == 200 and r.json()["archived"] is False
