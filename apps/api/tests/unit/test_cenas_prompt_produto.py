"""Prompt da cena com o produto do catálogo (spec 012, T037, research R13): função pura, byte a
byte; a referência leve da 010 continua idêntica."""

from sociman_api.cenas.models import ESTILO_PADRAO, NEGATIVE_PADRAO, CenaMovimento, CenaPlano
from sociman_api.cenas.prompt import AvatarIn, CenarioIn, Entrada, montar

AVATAR = "A cheerful woman in her early 30s with dark curly hair."
QUARTO = "Bright minimalist bedroom with white walls"
FRASE = "High-waisted ribbed knit biker shorts with a small 'LS' logo on the left leg."


def _entrada(**kw) -> Entrada:
    base = {"acao": "holds the shorts up to the camera and smiles",
            "estilo_padrao": ESTILO_PADRAO, "negative_padrao": NEGATIVE_PADRAO,
            "avatar": AvatarIn(AVATAR, None, 3), "cenario": CenarioIn(QUARTO, 1),
            "plano": CenaPlano.medio, "movimento": CenaMovimento.parada}
    return Entrada(**{**base, **kw})


def test_catalogo_com_variante_byte_a_byte():
    m = montar(_entrada(produto_prompt=FRASE, produto_cor="navy blue"))
    assert m.texto == (
        f"{AVATAR} holds the shorts up to the camera and smiles, with the product exactly as in "
        f"the reference image. {FRASE} Color: navy blue. {QUARTO}. Medium shot, static camera. "
        f"{ESTILO_PADRAO}.")
    assert [p.parte for p in m.partes] == ["avatar", "acao", "produto", "cenario", "camera",
                                           "estilo"]


def test_catalogo_sem_variante_so_a_frase_literal():
    frase = "  Ribbed knit shorts  "  # literal: nem trim
    m = montar(_entrada(produto_prompt=frase))
    produto = next(p for p in m.partes if p.parte == "produto")
    assert produto.texto == frase
    assert "Color:" not in m.texto


def test_acao_que_ja_cita_a_referencia_nao_repete():
    m = montar(_entrada(acao="holds the product from the reference image", produto_prompt=FRASE))
    assert m.texto.count("reference image") == 1


def test_referencia_leve_identica_a_010():
    """Regressão: sem catálogo, o prompt é o mesmo da 010 (nome + foto)."""
    leve = _entrada(produto_nome="Garrafa térmica", produto_com_foto=True)
    m = montar(leve)
    assert m.texto == (
        f"{AVATAR} holds the shorts up to the camera and smiles, with the Garrafa térmica exactly "
        f"as in the reference image. {QUARTO}. Medium shot, static camera. {ESTILO_PADRAO}.")
    assert "produto" not in [p.parte for p in m.partes]
    sem_produto = montar(_entrada())
    assert sem_produto.texto == (f"{AVATAR} holds the shorts up to the camera and smiles. "
                                 f"{QUARTO}. Medium shot, static camera. {ESTILO_PADRAO}.")
