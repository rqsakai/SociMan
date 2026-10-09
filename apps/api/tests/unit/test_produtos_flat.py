"""Instrução do flat lay (spec 012, T009; research R7): o texto do pipeline byte a byte."""

from types import SimpleNamespace as NS

from sociman_api.produtos import flat

SHORTS = NS(material_en="ribbed knit",
            formato_corte="high-waisted biker-style shorts, mid-thigh length",
            detalhes_visiveis=["small white 'LS' logo on the left leg hem",
                               "wide elastic waistband"])

ESPERADO = (
    "Turn this product photo into a realistic flat-lay photo: the same item lying completely flat "
    "and relaxed on a plain white surface, seen from directly above, with soft natural fabric "
    "folds and no volume at all, as if simply laid down on a table; nobody is wearing it, no "
    "invisible body or mannequin shape. Keep exactly the same item: black ribbed knit, "
    "high-waisted biker-style shorts, mid-thigh length; small white 'LS' logo on the left leg "
    "hem; wide elastic waistband. Same color, texture, cut and logo. Plain white background, "
    "soft even light.")


def test_shorts_canelado_byte_a_byte():
    assert flat.instrucao(SHORTS, NS(cor_en="black")) == ESPERADO


def test_muda_com_a_cor_e_o_material():
    base = flat.instrucao(SHORTS, NS(cor_en="black"))
    assert flat.instrucao(SHORTS, NS(cor_en="navy blue")) != base
    outro = NS(**{**vars(SHORTS), "material_en": "smooth satin"})
    assert "smooth satin" in flat.instrucao(outro, NS(cor_en="black"))
    assert flat.instrucao(outro, NS(cor_en="black")) != base


def test_campos_exatos_sem_trim():
    estranho = NS(**{**vars(SHORTS), "material_en": " ribbed knit "})
    assert ":  black  ribbed knit ," not in flat.instrucao(estranho, NS(cor_en="black"))
    assert "black  ribbed knit , high" in flat.instrucao(estranho, NS(cor_en="black"))
