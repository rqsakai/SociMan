"""Kit padrão do avatar (spec 025, T017, US1): os passos em ordem, o par 3/4 numa versão só,
passo fechado, geração em andamento, menoridade, o `prompt` fora das edições e a troca de slot
(US6: arquiva, apaga a identidade, avisa os derivados e pede a checagem)."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import (
    PESSOA,
    avatar,
    avatar_com_slots,
    com_claude,
    escolher_opcao,
    geracao,
    passo_e_escolha,
    pedir,
    perfil,
    rodar_gpu,
    ver,
)


def _slot(a: dict, slot: str) -> dict | None:
    return next((f for f in a["files"] if f["slot"] == slot and not f["archived"]), None)


def test_avatar_novo_so_abre_o_rosto_de_origem(client, owner):
    h = owner[1]
    a = avatar(client, h, perfil(client, h))
    kit = a["kit"]
    assert [s["slot"] for s in kit["slots"]] == ["rosto_origem", "rosto_frontal",
                                                 "rosto_34_esq", "rosto_34_dir", "corpo_base"]
    abertos = {p["passo"]: p for p in kit["passos"]}
    assert abertos["avatar.rosto_origem"]["aberto"]
    assert not abertos["avatar.rosto_frontal"]["aberto"]
    assert abertos["avatar.rosto_frontal"]["motivo"] == "Escolha o rosto de origem antes"
    assert a["kitStatus"] is None  # a 007 sem kit: "sem kit padrão"


def test_kit_completo_passo_a_passo(client, owner, motores, db):
    h = owner[1]
    pid = perfil(client, h)
    a = avatar(client, h, pid)
    g = pedir(client, h, pid, a["id"], "avatar.rosto_origem", instrucao=PESSOA)
    assert g["nOpcoes"] == 4
    rodar_gpu(motores)
    assert len(geracao(client, h, g["id"])["candidatos"]) == 4
    escolher_opcao(client, h, g["id"], 2, a["version"])
    a = ver(client, h, a["id"])
    assert a["origem"] == "sintetico" and _slot(a, "rosto_origem")["geracaoId"] == g["id"]
    assert a["kitStatus"] == "incompleto"
    hist = client.get(f"/api/assets/{a['id']}/versions", headers=h).json()["items"]
    assert hist[0]["action"] == "kit_escolhido" and hist[0]["details"]["geracao_id"] == g["id"]
    # Frontal (2 opções), depois o par 3/4 numa versão só.
    passo_e_escolha(client, h, motores, pid, a["id"], "avatar.rosto_frontal")
    antes = ver(client, h, a["id"])["version"]
    par = passo_e_escolha(client, h, motores, pid, a["id"], "avatar.rostos_34")
    a = ver(client, h, a["id"])
    assert a["version"] == antes + 1
    esq, dir_ = _slot(a, "rosto_34_esq"), _slot(a, "rosto_34_dir")
    assert esq and dir_ and esq["image"]["id"] != dir_["image"]["id"]
    assert esq["geracaoId"] == dir_["geracaoId"] == par["id"]
    # Corpo-base: com os 5 slots, a checagem de identidade é pedida pelo servidor.
    com_claude(motores)
    passo_e_escolha(client, h, motores, pid, a["id"], "avatar.corpo_base")
    a = ver(client, h, a["id"])
    ident = next(p for p in a["kit"]["passos"] if p["passo"] == "avatar.identidade")
    assert ident["geracaoAberta"]["status"] == "na_fila"
    assert motores.linha_claude().volta() == "ok"
    a = ver(client, h, a["id"])
    assert a["kitStatus"] == "completo" and a["prompt"]
    assert {s["slot"]: s["nota"] for s in a["kit"]["slots"]}["corpo_base"] == 8


def test_passo_fechado_em_andamento_e_menoridade(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    a = avatar(client, h, pid)
    erro = pedir(client, h, pid, a["id"], "avatar.rosto_frontal", status=409)
    assert erro["error"]["code"] == "passo_fechado"
    erro = pedir(client, h, pid, a["id"], "avatar.rosto_origem", status=400,
                 instrucao="a teen girl smiling")
    assert erro["error"]["code"] == "menor_proibido"
    assert client.get(f"/api/perfis/{pid}/geracoes", headers=h).json()["itens"] == []
    erro = pedir(client, h, pid, a["id"], "avatar.rosto_origem", status=400,
                 instrucao=PESSOA, extras={"outra": 1})
    assert erro["error"]["details"]["field"] == "extras.outra"
    pedir(client, h, pid, a["id"], "avatar.rosto_origem", instrucao=PESSOA)
    erro = pedir(client, h, pid, a["id"], "avatar.rosto_origem", status=409, instrucao=PESSOA)
    assert erro["error"]["code"] == "geracao_em_andamento"


def test_prompt_do_avatar_fora_das_edicoes(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    a = avatar_com_slots(client, h, motores, pid, n=2)
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "prompt": "UNIQUE-AVATAR-PROMPT"})
    assert r.status_code == 200
    g = pedir(client, h, pid, a["id"], "avatar.rostos_34")
    assert "UNIQUE-AVATAR-PROMPT" not in str(geracao(client, h, g["id"]))
    rodar_gpu(motores)
    assert "UNIQUE-AVATAR-PROMPT" not in str([p.params for p in motores.comfy.prompts.values()])


def test_trocar_slot_arquiva_apaga_identidade_e_avisa(client, owner, motores):
    """US6: refazer o frontal com o kit completo."""
    h = owner[1]
    pid = perfil(client, h)
    com_claude(motores)
    a = avatar_com_slots(client, h, motores, pid)
    assert a["kitStatus"] == "completo" and a["identidade"]
    antigo = _slot(a, "rosto_frontal")
    g = pedir(client, h, pid, a["id"], "avatar.rosto_frontal")
    rodar_gpu(motores)
    out = escolher_opcao(client, h, g["id"], 2, a["version"])
    assert out["status"] == "escolhido"
    a = ver(client, h, a["id"])
    assert _slot(a, "rosto_frontal")["id"] != antigo["id"]
    assert next(f for f in a["files"] if f["id"] == antigo["id"])["archived"]
    assert a["identidade"] is None and a["kitStatus"] == "incompleto"
    ident = next(p for p in a["kit"]["passos"] if p["passo"] == "avatar.identidade")
    assert ident["geracaoAberta"] is not None  # a nova checagem foi pedida


def test_upload_no_slot_segue_a_ordem(client, owner, motores):
    from integration.padrao_helpers import img

    h = owner[1]
    pid = perfil(client, h)
    a = avatar(client, h, pid)
    r = client.post(f"/api/assets/{a['id']}/arquivos", headers=h,
                    data={"role": "kit", "slot": "rosto_frontal"},
                    files={"file": ("f.jpg", img(), "image/jpeg")})
    assert r.status_code == 400 and r.json()["error"]["details"]["field"] == "slot"
    r = client.post(f"/api/assets/{a['id']}/arquivos", headers=h,
                    data={"role": "kit", "slot": "rosto_origem", "origem": "upload"},
                    files={"file": ("f.jpg", img(), "image/jpeg")})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["file"]["slot"] == "rosto_origem" and out["file"]["origemArquivo"] == "enviado"
    assert out["asset"]["origem"] == "upload"
    abertos = {p["passo"]: p["aberto"] for p in out["asset"]["kit"]["passos"]}
    assert abertos["avatar.rosto_frontal"] and not abertos["avatar.rosto_origem"]
