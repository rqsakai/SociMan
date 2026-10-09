"""Looks e poses gerados (spec 025, T039, US4): bloqueados sem corpo-base e frontal; a opção
escolhida vira `referencia` com o `look` ou `pose` com o rótulo e o "quando usar", com a geração
de origem; rótulo de pose repetido recusado antes de gerar; pose como base; o `prompt` fora."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import (
    avatar,
    avatar_com_slots,
    escolher_opcao,
    pedir,
    perfil,
    rodar_gpu,
    ver,
)


def test_bloqueado_sem_o_kit(client, owner):
    h = owner[1]
    pid = perfil(client, h)
    a = avatar(client, h, pid)
    erro = pedir(client, h, pid, a["id"], "avatar.look", status=409, rotulo="Cozinha",
                 instrucao="red dress")
    assert erro["error"]["code"] == "passo_fechado"


def test_look_e_pose_a_partir_do_kit(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    a = avatar_com_slots(client, h, motores, pid, n=4)
    corpo = next(f for f in a["files"] if f["slot"] == "corpo_base")
    look = pedir(client, h, pid, a["id"], "avatar.look", rotulo="Cozinha",
                 instrucao="red polka-dot dress and white sneakers")
    assert look["referencias"][0]["id"] == corpo["image"]["id"]
    rodar_gpu(motores)
    escolher_opcao(client, h, look["id"], 1, ver(client, h, a["id"])["version"])
    a = ver(client, h, a["id"])
    gerado = next(f for f in a["files"] if f["look"] == "Cozinha")
    assert gerado["role"] == "referencia" and gerado["geracaoId"] == look["id"]
    assert gerado["origemArquivo"] == "gerado"
    pose = pedir(client, h, pid, a["id"], "avatar.pose", rotulo="apontando",
                 instrucao="pointing to the product, same outfit",
                 extras={"quandoUsar": "quando mostra o produto"})
    rodar_gpu(motores)
    escolher_opcao(client, h, pose["id"], 2, ver(client, h, a["id"])["version"])
    a = ver(client, h, a["id"])
    p = next(f for f in a["files"] if f["role"] == "pose")
    assert p["label"] == "apontando" and p["quandoUsar"] == "quando mostra o produto"
    # Rótulo repetido recusado antes de gerar; "quando usar" grande demais e chave estranha.
    erro = pedir(client, h, pid, a["id"], "avatar.pose", status=409, rotulo="Apontando",
                 instrucao="x")
    assert erro["error"]["code"] == "pose_label_in_use"
    erro = pedir(client, h, pid, a["id"], "avatar.pose", status=400, rotulo="sentada",
                 instrucao="x", extras={"outra": "y"})
    assert erro["error"]["details"]["field"] == "extras.outra"
    # A pose como base do look (e o frontal como referência do rosto).
    base = pedir(client, h, pid, a["id"], "avatar.look", rotulo="Rua",
                 instrucao="jeans jacket", referencias=[p["image"]["id"]])
    assert base["referencias"][0]["id"] == p["image"]["id"]
    rodar_gpu(motores)
    ultimo = max(motores.comfy.prompts.values(), key=lambda x: x.numero)
    assert "Same person" in str(ultimo.params)


def test_uma_geracao_por_rotulo(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    a = avatar_com_slots(client, h, motores, pid, n=4)
    pedir(client, h, pid, a["id"], "avatar.look", rotulo="Cozinha", instrucao="red dress")
    erro = pedir(client, h, pid, a["id"], "avatar.look", status=409, rotulo="cozinha",
                 instrucao="blue dress")
    assert erro["error"]["code"] == "geracao_em_andamento"
    pedir(client, h, pid, a["id"], "avatar.look", rotulo="Rua", instrucao="jeans")
