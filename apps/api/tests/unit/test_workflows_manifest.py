"""Os 4 blocos copiados do pipeline (spec 021, T011, R6): os sha256 do MANIFEST batem e cada
`params.json` aponta para nós que existem no `api.json`."""

import hashlib
import json

from sociman_api.geracao.comfyui import BLOCOS, WORKFLOWS


def test_hashes_batem():
    man = json.loads((WORKFLOWS / "MANIFEST.json").read_text())["blocos"]
    assert set(man) == set(BLOCOS)
    for bloco, ent in man.items():
        for ext in ("api", "params"):
            dados = (WORKFLOWS / f"{bloco}.{ext}.json").read_bytes()
            assert hashlib.sha256(dados).hexdigest() == ent[f"{ext}_sha256"], (bloco, ext)


def test_contrato_aponta_para_nos_do_workflow():
    for bloco in BLOCOS:
        api = json.loads((WORKFLOWS / f"{bloco}.api.json").read_text())
        contrato = json.loads((WORKFLOWS / f"{bloco}.params.json").read_text())
        for nome, spec in contrato["params"].items():
            assert spec["node"] in api, (bloco, nome)
            assert spec["input"] in api[spec["node"]]["inputs"], (bloco, nome)
            for nid, inp in spec.get("consumers", []):
                assert inp in api[nid]["inputs"], (bloco, nome, nid)
        for saida in contrato["outputs"].values():
            assert saida["node"] in api, bloco
