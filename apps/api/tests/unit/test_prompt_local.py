"""Prompt do clipe local e avisos do keyframe (spec 011, T010, research R7, FR-028 e FR-030)."""

import pytest

from sociman_api.cenas.models import CenaMovimento, CenaPlano
from sociman_api.cenas.prompt_local import (
    AMBIENTE_FIXO,
    MOUTH_CLOSED,
    REALISMO,
    EntradaClipe,
    avisos_keyframe,
    montar_clipe,
)

BIA = ("A plus-size Brazilian woman in her early 30s with long wavy dark brown hair, warm "
       "medium-brown skin and a bright friendly smile.")


def test_com_avatar_tem_boca_fechada_e_ambiente_fixo():
    cena = EntradaClipe(acao="She slowly turns her body to the side and back toward the camera",
                        plano=CenaPlano.aberto, movimento=CenaMovimento.parada)
    m = montar_clipe(cena, BIA)
    assert m.texto == (
        "She slowly turns her body to the side and back toward the camera. Wide shot, static "
        f"camera. {BIA} {MOUTH_CLOSED} {AMBIENTE_FIXO} {REALISMO}")
    assert [p.parte for p in m.partes] == ["acao", "avatar", "boca", "ambiente", "realismo"]
    # A descrição do avatar entra byte a byte.
    assert next(p.texto for p in m.partes if p.parte == "avatar") == BIA


def test_sem_avatar_nao_fala_de_boca():
    m = montar_clipe(EntradaClipe(acao="The dress hangs on a rack, the fabric moves gently",
                                  camera="slow orbit."), None)
    assert m.texto == ("The dress hangs on a rack, the fabric moves gently. Slow orbit. "
                       f"{AMBIENTE_FIXO} {REALISMO}")
    assert "mouth" not in m.texto.lower()
    assert montar_clipe(EntradaClipe(acao="x"), "   ").partes[1].parte == "ambiente"


def test_detalhe_produto_sem_boca_mas_com_avatar():
    cena = EntradaClipe(acao="Her hand glides along the wide flutter sleeve",
                        plano=CenaPlano.detalhe_produto, movimento=CenaMovimento.aproximacao)
    m = montar_clipe(cena, BIA)
    assert "Extreme close-up of the product, slow push-in." in m.texto
    assert MOUTH_CLOSED not in m.texto
    assert AMBIENTE_FIXO in m.texto
    # Quem chama pode forçar (ex.: rosto visível num close de produto).
    assert MOUTH_CLOSED in montar_clipe(cena, BIA, tem_rosto=True).texto


def test_pronome_da_boca_segue_o_avatar():
    homem = "A Brazilian man in his 40s with short grey hair."
    assert "His mouth stays closed" in montar_clipe(EntradaClipe(acao="He waves"), homem).texto
    assert "The person's mouth" in montar_clipe(EntradaClipe(acao="Waves"),
                                                "A cartoon mascot.").texto


def test_fala_texto_e_audio_nunca_entram():
    """A cena da 010 pode ter fala, texto na tela e áudio: o clipe local ignora os três."""

    class CenaDaDez:
        acao = "She points down toward the bottom of the screen"
        plano = CenaPlano.medio
        movimento = None
        camera = None
        fala = "Corre no link aqui embaixo!"
        texto_tela = "LINK AQUI"
        audio = "upbeat music"

    texto = montar_clipe(CenaDaDez(), BIA).texto
    for proibido in ("Corre no link", "LINK AQUI", "upbeat", "says", "Ambient sound"):
        assert proibido not in texto


@pytest.mark.parametrize("instrucao, codigos", [
    ("Close-up of the same woman touching the sleeve. Keep the dress exactly as in image 1.", []),
    ("Make the lighting warmer and golden", ["keyframe_luz"]),
    ("Change the light to sunset", ["keyframe_luz"]),
    ("deixe a luz mais quente", ["keyframe_luz"]),
    ("A phone video of her smiling", ["keyframe_phone_video"]),
    ("Smartphone footage, change the lights", ["keyframe_luz", "keyframe_phone_video"]),
    ("Her hand lightly touches the light crepe skirt", []),  # "light" = leve não avisa
    ("", []),
    (None, []),
])
def test_avisos_keyframe(instrucao, codigos):
    avisos = avisos_keyframe(instrucao)
    assert [a.codigo for a in avisos] == codigos
    assert all(a.campo == "keyframeInstrucao" for a in avisos)
