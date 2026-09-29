"""Limites dos textos de postagem e a normalização das hashtags (spec 006, R9).

Desde a spec 008, o cliente do Claude, o prompt e a validação das sugestões ficam no assistente
(`sociman_api.ia`: `cliente.py`, `prompt.py`, `contexto.py`, `saida.py`), que usa daqui só os
limites e a normalização.
"""

import re

TITULO_MAX = 100
DESCRICAO_MAX = 2000
HASHTAGS_MIN = 3
HASHTAGS_MAX = 8
HASHTAG_MAX_CHARS = 50

_NAO_PALAVRA = re.compile(r"[\W]+", re.UNICODE)


def normalizar_hashtag(raw: str) -> str | None:
    """`" #Dica De Hoje! "` → `"#dicadehoje"`; None se não sobrar nada."""
    corpo = _NAO_PALAVRA.sub("", raw.strip().lstrip("#").lower())[:HASHTAG_MAX_CHARS]
    return f"#{corpo}" if corpo else None


def normalizar_hashtags(items: list[str]) -> list[str]:
    vistas: dict[str, None] = {}
    for item in items:
        tag = normalizar_hashtag(item)
        if tag is not None:
            vistas.setdefault(tag, None)
    return list(vistas)
