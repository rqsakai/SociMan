"""Direito proposto e aceito (spec 013, T030, Q1, FR-014 a FR-017) e identificação do canal."""

import pytest

from sociman_api.agencia import conciliar as c
from sociman_api.agencia.leitores import FonteLida
from sociman_api.canais.models import CanalDireito as D

UC = "UC" + "a" * 22


@pytest.mark.parametrize(("status", "propria", "proposto", "aceitos"), [
    ("programa-de-cortes", False, D.programa_de_cortes, [D.programa_de_cortes]),
    ("autorizado", False, D.sem_acordo, [D.sem_acordo, D.parceiro]),
    ("pendente", False, D.sem_acordo, [D.sem_acordo]),
    ("negado", False, D.sem_acordo, [D.sem_acordo]),
    ("desconhecido", False, D.sem_acordo, [D.sem_acordo]),
    ("autorizado", True, D.proprio, [D.proprio]),
])
def test_proposta_e_aceitos(status, propria, proposto, aceitos):
    assert c.direito_proposto(status, propria) == proposto
    assert c.direitos_aceitos(status, propria) == aceitos


@pytest.mark.parametrize(("celula", "esperado"), [
    (f"youtube.com/channel/{UC}", (f"youtube.com/channel/{UC}", None)),
    ("youtube.com/@JovemNerd · tiktok.com/@jovemnerd", ("youtube.com/@JovemNerd", None)),
    ("twitch.tv/cellbit · youtube.com/@cellbit", ("youtube.com/@cellbit", None)),
    ("https://www.youtube.com/c/D20Culturebr", ("https://www.youtube.com/c/D20Culturebr", None)),
    ("youtube.com/user/fulano", ("youtube.com/user/fulano", None)),
    (f"Channel ID confirmado 2026-09-26: {UC}", (UC, None)),
    ("@VACACAST", ("@VACACAST", None)),
    ("handle exato não confirmado nesta pesquisa", (None, "sem_canal_youtube")),
    ("canal(is) de cortes a confirmar", (None, "sem_canal_youtube")),
    ("rpgnext.com.br", (None, "sem_canal_youtube")),
    ("tiktok.com/@x", (None, "sem_canal_youtube")),
    ("arquivos entregues em media/originais/x/", (None, "conteudo_proprio")),
])
def test_identificar_canal(celula, esperado):
    assert c.identificar_canal(celula) == esperado


def _f(**kw) -> FonteLida:
    base = {"linha": 12, "criador": "C", "canal": "youtube.com/@c", "status_md": "autorizado",
            "evidencia": "", "regras": "", "confirmado_por": "", "data": "", "propria": False}
    return FonteLida(**(base | kw))


def test_nota_e_url_de_evidencia():
    f = _f(evidencia="Print em https://exemplo.com/p e https://outro.com", regras="48h",
           confirmado_por="dono", data="2026-09-24")
    assert c.nota_evidencia("x", f) == (
        "fontes.md de x, linha 12: status autorizado. Print em https://exemplo.com/p e "
        "https://outro.com. Regras: 48h. Confirmado por dono em 2026-09-24.")
    assert c.evidencia_url(f) == "https://exemplo.com/p"
    negado = c.nota_evidencia("x", _f(status_md="negado", data="2026-09-20"))
    assert "Negado no markdown em 2026-09-20." in negado
    longa = c.nota_evidencia("x", _f(evidencia="a" * 3000))
    assert len(longa) == c.NOTA_MAX and longa.endswith("…")
