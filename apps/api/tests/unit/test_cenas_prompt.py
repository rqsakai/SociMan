"""Montagem do prompt da cena (spec 010, T007, SC-002/SC-003): função pura."""

from sociman_api.cenas.models import (
    ESTILO_PADRAO,
    NEGATIVE_PADRAO,
    CenaModo,
    CenaMovimento,
    CenaPlano,
)
from sociman_api.cenas.prompt import AvatarIn, CenarioIn, Entrada, montar

ACHADINHOS = ("A cheerful 1950s pin-up style woman in her early 30s, with dark brown voluminous "
              "curled hair in a vintage updo, fair skin, red lipstick, pearl earrings and a pearl "
              "necklace, wearing a red dress with small white polka dots and white cotton gloves.")
COZINHA = ("1950s kitchen with mint-green countertops, wooden cabinets, copper pots hanging, "
           "pastel bowls on shelves, a stainless steel gas stove")


def _entrada(**kw) -> Entrada:
    base = {"acao": "lifts the lid and steam comes out", "estilo_padrao": ESTILO_PADRAO,
            "negative_padrao": NEGATIVE_PADRAO}
    return Entrada(**{**base, **kw})


def test_exemplo_do_shop_diretor():
    """SC-003: Achadinhos na Cozinha retrô, com a foto da panela e a fala em pt-BR."""
    m = montar(_entrada(
        avatar=AvatarIn(ACHADINHOS, "Mãos longe do rosto nas cenas com fala", 4),
        cenario=CenarioIn(COZINHA, 2), plano=CenaPlano.medio, movimento=CenaMovimento.parada,
        fala="Gente, olha essa panela!", audio="soft kitchen ambience",
        produto_nome="Panela de pressão elétrica", produto_com_foto=True))
    assert m.texto == (
        f"{ACHADINHOS} Mãos longe do rosto nas cenas com fala. lifts the lid and steam comes "
        "out, with the Panela de pressão elétrica exactly as in the reference image. "
        f"{COZINHA}. Medium shot, static camera. {ESTILO_PADRAO}. She looks at the camera and "
        'says: "Gente, olha essa panela!" Ambient sound: soft kitchen ambience.')
    assert m.negative == NEGATIVE_PADRAO
    assert [p.parte for p in m.partes] == ["avatar", "regras", "acao", "cenario", "camera",
                                           "estilo", "fala", "audio"]
    assert (m.avatar_version, m.cenario_version) == (4, 2)


def test_descricao_do_avatar_byte_a_byte():
    descricao = "  A woman\twith  odd   spacing\n\n"
    m = montar(_entrada(avatar=AvatarIn(descricao, None, 1)))
    assert m.texto.startswith(descricao)
    assert m.partes[0].texto == descricao
    # a separação não altera a descrição: termina em espaço, então nada é inserido
    assert m.texto[len(descricao):].startswith("lifts the lid")


def test_sem_avatar_cenario_nem_produto():
    m = montar(_entrada(fala="Oi"))
    assert m.texto == f"lifts the lid and steam comes out. {ESTILO_PADRAO}. The person looks " \
                      'at the camera and says: "Oi"'
    assert m.avatar_version is None and m.cenario_version is None


def test_modo_quadros_traz_os_quadros_antes():
    m = montar(_entrada(modo=CenaModo.quadros, quadro_inicial="closed pot",
                        quadro_final="open pot with steam", avatar=AvatarIn(ACHADINHOS, None, 1)))
    assert m.texto.startswith("Start frame: closed pot. End frame: open pot with steam. "
                              + ACHADINHOS)


def test_estilo_e_negative_da_cena_ou_do_perfil():
    m = montar(_entrada(estilo="cinematic", negative="blur"))
    assert "cinematic." in m.texto and ESTILO_PADRAO not in m.texto
    assert m.negative == "blur"
    m = montar(_entrada(estilo="   ", negative=""))
    assert ESTILO_PADRAO in m.texto and m.negative == NEGATIVE_PADRAO


def test_referencia_nao_duplica_e_exige_foto():
    m = montar(_entrada(acao="holds the pot exactly as in the reference image",
                        produto_nome="Panela", produto_com_foto=True))
    assert m.texto.count("reference image") == 1
    m = montar(_entrada(produto_nome="Panela", produto_com_foto=False))
    assert "reference image" not in m.texto


def test_camera_com_detalhe_livre():
    m = montar(_entrada(plano=CenaPlano.close, camera="eye level"))
    assert "Close-up shot, eye level." in m.texto


def test_pronome_masculino():
    m = montar(_entrada(avatar=AvatarIn("A tall man in a suit.", None, 1), fala="Olá"))
    assert 'He looks at the camera and says: "Olá"' in m.texto
