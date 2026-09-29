"""Limites e normalização das hashtags da postagem (spec 006, R9). Desde a spec 008, o cliente,
o prompt e a validação das sugestões são testados em `test_ia_{cliente,prompt,saida}.py`."""

import pytest

from sociman_api.postagem import textos


@pytest.mark.parametrize(("raw", "tag"), [
    (" #Dica De Hoje! ", "#dicadehoje"),
    ("tecnologia", "#tecnologia"),
    ("##Ação_2", "#ação_2"),
    ("!!!", None),
])
def test_normalizar_hashtag(raw, tag):
    assert textos.normalizar_hashtag(raw) == tag


def test_normalizar_hashtags_sem_repetir():
    assert textos.normalizar_hashtags(["#Dica", "dica", "#DICA", "#outra"]) == ["#dica", "#outra"]


def test_hashtag_longa_cortada_no_limite():
    assert textos.normalizar_hashtag("a" * 80) == "#" + "a" * textos.HASHTAG_MAX_CHARS


def test_limites():
    assert (textos.TITULO_MAX, textos.DESCRICAO_MAX) == (100, 2000)
    assert (textos.HASHTAGS_MIN, textos.HASHTAGS_MAX) == (3, 8)
