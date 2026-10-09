"""Cenário padrão e variações (spec 025, T042, US5): a cena 768×1344 vira o slot `cena` e o kit
`completo`; a variação exige a cena, nasce da cena e recusa rótulo repetido sem diferença de
caixa; o cenário da 007 sem kit continua igual."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import (
    cenario,
    cenario_com_cena,
    escolher_opcao,
    geracao,
    pedir,
    perfil,
    rodar_gpu,
    ver,
)


def test_cena_e_variacoes(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    c = cenario(client, h, pid)
    assert c["kitStatus"] is None  # a 007 sem kit
    erro = pedir(client, h, pid, c["id"], "cenario.variacao", status=409, rotulo="noite",
                 instrucao="at night")
    assert erro["error"]["code"] == "passo_fechado"
    c = cenario_com_cena(client, h, motores, pid)
    cena = next(f for f in c["files"] if f["slot"] == "cena")
    assert (cena["image"]["width"], cena["image"]["height"]) == (768, 1344)
    assert c["kitStatus"] == "completo" and c["primaryFileId"] == cena["id"]
    v = pedir(client, h, pid, c["id"], "cenario.variacao", rotulo="noite",
              instrucao="same kitchen at night, warm lamps")
    assert v["referencias"][0]["id"] == cena["image"]["id"]
    rodar_gpu(motores)
    assert len(geracao(client, h, v["id"])["candidatos"]) == 2
    escolher_opcao(client, h, v["id"], 1, ver(client, h, c["id"])["version"])
    c = ver(client, h, c["id"])
    var = next(f for f in c["files"] if f["role"] == "variacao")
    assert var["label"] == "noite" and var["geracaoId"] == v["id"]
    erro = pedir(client, h, pid, c["id"], "cenario.variacao", status=409, rotulo="Noite",
                 instrucao="x")
    assert erro["error"]["code"] == "variacao_label_in_use"
