"""Desempenho do cadastro padronizado (spec 025, T049, plan): pedir um passo < 300 ms, escolher
< 500 ms, detalhe do avatar < 200 ms e revogar 50 arquivos < 5 s, com o volume semeado."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import time

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import (
    avatar,
    com_claude,
    consentimento,
    geracao,
    img,
    passo_e_escolha,
    pedir,
    perfil,
    rodar_gpu,
    ver,
)


def _medir(fn):
    inicio = time.monotonic()
    out = fn()
    return out, time.monotonic() - inicio


def test_tempos_do_kit_e_da_revogacao(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    com_claude(motores)
    a = avatar(client, h, pid)  # pessoa real: consentimento, foto enviada e o kit gerado
    a = consentimento(client, h, a["id"], a["version"])["asset"]
    r = client.post(f"/api/assets/{a['id']}/arquivos", headers=h,
                    data={"role": "kit", "slot": "rosto_origem", "origem": "pessoa_real"},
                    files={"file": ("ana.jpg", img(), "image/jpeg")})
    assert r.status_code == 201, r.text
    for passo in ("avatar.rosto_frontal", "avatar.rostos_34", "avatar.corpo_base"):
        passo_e_escolha(client, h, motores, pid, a["id"], passo)
    motores.linha_claude().volta()
    for i in range(45):  # 5 slots + 45 looks = 50 arquivos
        r = client.post(f"/api/assets/{a['id']}/arquivos", headers=h,
                        data={"role": "referencia", "look": f"Look {i}"},
                        files={"file": (f"l{i}.jpg", img(size=(320, 400)), "image/jpeg")})
        assert r.status_code == 201, r.text
    ver(client, h, a["id"])  # aquece
    _, t_detalhe = _medir(lambda: ver(client, h, a["id"]))
    assert t_detalhe < 0.2, f"detalhe: {t_detalhe:.3f} s"

    g, t_pedir = _medir(lambda: pedir(client, h, pid, a["id"], "avatar.look", rotulo="Rua",
                                      instrucao="jeans jacket"))
    assert t_pedir < 0.3, f"pedir: {t_pedir:.3f} s"
    rodar_gpu(motores)
    g = geracao(client, h, g["id"])
    cand = g["candidatos"][0]
    versao = ver(client, h, a["id"])["version"]
    r, t_escolher = _medir(lambda: client.post(
        f"/api/geracoes/{g['id']}/escolher", headers=h,
        json={"candidatoId": cand["id"], "version": g["version"], "alvoVersion": versao}))
    assert r.status_code == 200, r.text
    assert t_escolher < 0.5, f"escolher: {t_escolher:.3f} s"

    a = ver(client, h, a["id"])
    assert len(a["files"]) >= 50
    r, t_revogar = _medir(lambda: client.post(
        f"/api/assets/{a['id']}/consentimento/revogar", headers=h,
        json={"version": a["version"], "confirmo": True}))
    assert r.status_code == 200, r.text
    assert t_revogar < 5.0, f"revogar: {t_revogar:.3f} s"
