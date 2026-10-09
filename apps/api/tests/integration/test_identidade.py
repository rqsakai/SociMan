"""Checagem de identidade (spec 025, T018, R4): completo e atenção, "Refazer este passo",
proibida do guia não aplicada (sem 2ª tentativa, desfecho `sem_acao`), Claude fora com checagem
pendente, a chamada no registro e o `prompt` gravado exatamente como veio."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

from sqlalchemy import select

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import (
    avatar_com_slots,
    com_claude,
    geracao,
    pedir,
    perfil,
    ver,
)
from sociman_api.ia.models import IaChamada, IaDesfecho


def _identidade(a: dict) -> dict:
    return next(p for p in a["kit"]["passos"] if p["passo"] == "avatar.identidade")


def test_completo_com_registro_e_prompt_exato(client, owner, motores, db):
    h = owner[1]
    fake = com_claude(motores)
    fake.descricao_identidade = "  " + fake.descricao_identidade + "  "
    a = avatar_com_slots(client, h, motores, perfil(client, h))
    assert a["kitStatus"] == "completo"
    assert a["prompt"] == fake.descricao_identidade  # sem trim
    assert set(a["identidade"]["notas"]) == {"rosto_frontal", "rosto_34_esq", "rosto_34_dir",
                                             "corpo_base"}
    gid = a["identidade"]["geracaoId"]
    row = db.scalar(select(IaChamada).where(IaChamada.geracao_id == uuid.UUID(gid)))
    assert row.tipo_campo == "avatar.identidade" and row.custo_usd is not None
    assert row.desfecho == IaDesfecho.aplicada
    assert fake.imagens == [5]
    hist = client.get(f"/api/assets/{a['id']}/versions", headers=h).json()["items"]
    assert hist[0]["action"] == "identidade" and hist[0]["details"]["automatico"] is True


def test_nota_baixa_fica_em_atencao_e_pede_refazer(client, owner, motores):
    h = owner[1]
    fake = com_claude(motores)
    fake.notas_identidade = {"rosto_34_dir": 6}
    a = avatar_com_slots(client, h, motores, perfil(client, h))
    assert a["kitStatus"] == "atencao"
    refazer = {s["slot"]: s["refazer"] for s in a["kit"]["slots"]}
    assert refazer["rosto_34_dir"] and not refazer["rosto_frontal"]


def test_proibida_do_guia_nao_aplica_a_descricao(client, owner, motores, db):
    h = owner[1]
    pid = perfil(client, h)
    r = client.put(f"/api/perfis/{pid}/guia", headers=h,
                   json={"version": 0, "campos": {"proibidas": ["beauty"]}})
    assert r.status_code == 200, r.text
    fake = com_claude(motores)
    a = avatar_com_slots(client, h, motores, pid)
    assert a["prompt"] is None  # a descrição com "beauty mark" não entrou
    assert a["identidade"]["notas"] and a["kitStatus"] == "completo"
    assert a["kit"]["descricaoNaoAplicada"] == {"proibidas": ["beauty"]}
    row = db.scalar(select(IaChamada).where(
        IaChamada.geracao_id == uuid.UUID(a["identidade"]["geracaoId"])))
    assert row.desfecho == IaDesfecho.sem_acao and row.proibidas == ["beauty"]
    assert len(fake.bodies) == 1  # sem 2ª tentativa


def test_claude_fora_deixa_checagem_pendente(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    a = avatar_com_slots(client, h, motores, pid)  # sem cliente do Claude: falha
    assert a["kitStatus"] == "incompleto" and a["identidade"] is None
    assert a["kit"]["checagemPendente"] is True
    g = _identidade(a)["geracaoAberta"]
    assert g["status"] == "falhou"
    # "Checar de novo" = tentar de novo a da 021 (ou cancelar e pedir).
    com_claude(motores)
    r = client.post(f"/api/geracoes/{g['id']}/tentar-de-novo", headers=h,
                    json={"version": geracao(client, h, g["id"])["version"]})
    assert r.status_code == 200, r.text
    motores.linha_claude().volta()
    assert ver(client, h, a["id"])["kitStatus"] == "completo"


def test_checar_de_novo_pela_tela(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    com_claude(motores)
    a = avatar_com_slots(client, h, motores, pid)
    g = pedir(client, h, pid, a["id"], "avatar.identidade")
    assert g["semEscolha"] is True
    erro = pedir(client, h, pid, a["id"], "avatar.identidade", status=409)
    assert erro["error"]["code"] == "geracao_em_andamento"
