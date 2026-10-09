"""Trocar um slot e reverter (spec 025, T045, US6, R17): a troca do frontal avisa os derivados;
reverter para a versão anterior à troca volta o arquivo antigo do slot e a identidade daquela
versão, sem colidir no UNIQUE parcial do slot."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import avatar_com_slots, com_claude, img, perfil, ver


def _slot(a: dict, slot: str) -> dict:
    return next(f for f in a["files"] if f["slot"] == slot and not f["archived"])


def test_troca_avisa_derivados_e_reverter_volta_o_slot(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    com_claude(motores)
    a = avatar_com_slots(client, h, motores, pid)
    assert a["kitStatus"] == "completo"
    frontal_antes = _slot(a, "rosto_frontal")
    versao_antes = a["version"]
    # Enviar outro frontal no lugar: os 3/4 e o corpo foram gerados do frontal anterior.
    r = client.post(f"/api/assets/{a['id']}/arquivos", headers=h,
                    data={"role": "kit", "slot": "rosto_frontal"},
                    files={"file": ("f.jpg", img(cor=(200, 10, 10)), "image/jpeg")})
    assert r.status_code == 201, r.text
    out = r.json()
    itens = out["avisos"][0]["itens"]
    assert {i["slot"] for i in itens} >= {"rosto_34_esq", "rosto_34_dir", "corpo_base"}
    assert out["checagemGeracaoId"] is not None
    a = out["asset"]
    assert a["identidade"] is None and a["kitStatus"] == "incompleto"
    # O dono reverte para a versão anterior à troca.
    r = client.post(f"/api/assets/{a['id']}/revert", headers=h,
                    json={"version": a["version"], "toVersion": versao_antes})
    assert r.status_code == 200, r.text
    a = ver(client, h, a["id"])
    assert _slot(a, "rosto_frontal")["id"] == frontal_antes["id"]
    assert a["identidade"] is not None and a["kitStatus"] == "completo"
