"""Kit de marca com a biblioteca da agência (spec 029, T032, FR-013): o fundo e a marca d'água
vêm de qualquer perfil base ou de um asset sem perfil, e o uso no kit continua bloqueando o
arquivar do asset."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from integration.estudio_helpers import item, perfil
from integration.geracao_helpers import _buckets, owner  # noqa: F401 (fixtures)

KIT_KEYS = ("palette", "caption", "hook", "watermark", "endCard", "catchphrases", "series")


def _kit(client, h, perfil_id: str) -> dict:
    return client.get(f"/api/perfis/{perfil_id}/kit", headers=h).json()["kit"]


def _put(client, h, perfil_id: str, kit: dict, **sections):
    body = {k: kit[k] for k in KIT_KEYS} | sections
    return client.put(f"/api/perfis/{perfil_id}/kit", headers=h,
                      json={"version": kit["version"], **body})


def _imagem(asset: dict) -> str:
    return asset["files"][0]["image"]["id"]


def test_kit_usa_imagens_de_outro_perfil_e_sem_perfil(client, owner):
    h = owner[1]
    a, b = perfil(client, h, "perfil-a"), perfil(client, h, "perfil-b")
    fundo_b = item(client, h, "fundo", b, name="Fundo de B")
    marca_sem = item(client, h, "marca_dagua", None, name="Selo da agência")
    kit = _kit(client, h, a)
    r = _put(client, h, a, kit,
             endCard=kit["endCard"] | {"ligado": True, "fundo_tipo": "imagem",
                                       "fundo_imagem_id": _imagem(fundo_b)},
             watermark=kit["watermark"] | {"ligado": True, "tipo": "imagem",
                                           "imagem_id": _imagem(marca_sem)})
    assert r.status_code == 200, r.text
    # O tipo continua valendo: uma marca d'água não serve de fundo.
    kit = r.json()["kit"]
    r = _put(client, h, a, kit, hook=kit["hook"] | {"fundo_tipo": "imagem",
                                                    "fundo_imagem_id": _imagem(marca_sem)})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_kit"


def test_asset_arquivado_recusado_no_kit(client, owner):
    h = owner[1]
    a = perfil(client, h, "perfil-a")
    fundo = item(client, h, "fundo", None)
    r = client.post(f"/api/assets/{fundo['id']}/archive", headers=h,
                    json={"version": fundo["version"]})
    assert r.status_code == 200, r.text
    kit = _kit(client, h, a)
    r = _put(client, h, a, kit, endCard=kit["endCard"] | {
        "ligado": True, "fundo_tipo": "imagem", "fundo_imagem_id": _imagem(fundo)})
    assert r.status_code == 400 and "arquivada" in r.json()["error"]["message"]


def test_uso_no_kit_bloqueia_arquivar(client, owner):
    h = owner[1]
    a, b = perfil(client, h, "perfil-a"), perfil(client, h, "perfil-b")
    fundo = item(client, h, "fundo", b)
    kit = _kit(client, h, a)
    r = _put(client, h, a, kit, endCard=kit["endCard"] | {
        "ligado": True, "fundo_tipo": "imagem", "fundo_imagem_id": _imagem(fundo)})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/assets/{fundo['id']}/archive", headers=h,
                    json={"version": fundo["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "asset_in_use"
