"""Identificador da voz no shop-tts (spec 025, T008, R11): formato do serviço, estável e único."""

import re
import uuid

from sociman_api.vozes.tts_id import tts_id


def test_formato_estavel_e_unico():
    ids = [uuid.uuid4() for _ in range(200)]
    nomes = [tts_id(i) for i in ids]
    assert all(re.fullmatch(r"[a-z0-9_]{2,40}", n) for n in nomes)
    assert len(set(nomes)) == len(nomes)
    assert tts_id(ids[0]) == tts_id(ids[0]) and nomes[0].startswith("v_")
    assert len(nomes[0]) == 34
