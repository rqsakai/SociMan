"""Paridade do casamento da afinidade (spec 023, T045; R9): o `translate` do PG dá o mesmo texto
que `ia.guia.normalizar` em todas as letras acentuadas do pt-BR e do espanhol, o regex escapa
as palavras e casa palavra inteira (inclusive de 2 letras)."""

import pytest
from sqlalchemy import func, literal, select, text

from sociman_api.aprendizado import afinidade
from sociman_api.db import get_engine
from sociman_api.ia.guia import normalizar

LETRAS = "áàâãäåéèêëíìîïóòôõöúùûüçñýÿ"


def _sql(expr):
    with get_engine().connect() as conn:
        return conn.execute(select(expr)).scalar()


@pytest.mark.parametrize("letra", list(LETRAS + LETRAS.upper()))
def test_translate_igual_a_normalizar(letra):
    palavra = f"a{letra}b"
    sql = _sql(afinidade.texto_sem_acento(literal(palavra), literal("")))
    assert sql.strip() == normalizar(palavra), letra


def test_frase_completa():
    frase = "AÇÃO Épica: Pokémon, São João e Ñandú"
    sql = _sql(afinidade.texto_sem_acento(literal(frase), literal("Descrição")))
    assert sql == normalizar(frase) + " " + normalizar("Descrição")


@pytest.mark.parametrize(("texto", "palavras", "casa"), [
    ("o c.a hoje", ["c.a"], True),
    ("o cxa hoje", ["c.a"], False),  # o ponto escapado não vira "qualquer letra"
    ("ti e redes", ["ti"], True),
    ("tilápia frita", ["ti"], False),
    ("homem aranha volta", ["homem aranha"], True),
    ("homem-aranha volta", ["homem aranha"], False),
    ("um.ponto", ["u.p"], False),
])
def test_regex_escapado_e_palavra_inteira(texto, palavras, casa):
    with get_engine().connect() as conn:
        r = conn.execute(text("SELECT :t ~ :r"), {"t": texto, "r": afinidade.regex(palavras)})
        assert r.scalar() is casa, (texto, palavras)


def test_caso_quente_e_frio_no_sql():
    expr = func.translate(func.lower(literal("Os VINGADORES voltaram")), afinidade.ACENTOS,
                          afinidade.SEM_ACENTO).op("~")(afinidade.regex(["vingadores"]))
    assert _sql(expr) is True
