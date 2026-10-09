"""Normalização e detecção de palavras proibidas do guia (spec 017, R7)."""

import pytest

from sociman_api.ia import guia


def test_normalizar_tira_acento_maiuscula_e_espacos():
    assert guia.normalizar("  CLÍCKBAIT \t  Já ") == "clickbait ja"
    assert guia.normalizar("Clickbait") == guia.normalizar("CLÍCKBAIT")
    assert guia.normalizar("Ação") == "acao"


@pytest.mark.parametrize(("texto", "termo", "casa"), [
    ("Nada de CLÍCKBAIT aqui", "clickbait", True),
    ("isso é clickbait.", "Clickbait", True),
    ("paga no pix", "pix", True),
    ("um pixel a mais", "pix", False),
    ("o pixinguinha", "pix", False),
    ("compre, já!", "compre já", True),
    ("compre -- JÁ", "compre já", True),
    ("comprejá", "compre já", False),
    ("#compreja hoje", "compre já", True),
    ("#comprejaagora", "compre já", False),
    ("#clickbait", "clickbait", True),
    ("sem nada", "clickbait", False),
])
def test_achar_proibidas_palavra_inteira(texto, termo, casa):
    assert guia.achar_proibidas([texto], [termo]) == ([termo] if casa else [])


def test_achar_proibidas_na_ordem_dos_termos_sem_repetir():
    textos = ["Promo imperdível", "compre já", "#clickbait"]
    termos = ["clickbait", "Clickbait", "pix", "imperdível", "compre já"]
    assert guia.achar_proibidas(textos, termos) == ["clickbait", "imperdível", "compre já"]


def test_achar_proibidas_ignora_termo_sem_palavra_e_texto_vazio():
    assert guia.achar_proibidas(["", "!!!"], ["!!!", "x"]) == []
