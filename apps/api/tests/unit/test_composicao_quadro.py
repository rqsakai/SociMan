"""T059: a diretiva fixa de composição do quadro numera as imagens pela posição real."""
import uuid

from sociman_api.roteiros.pedidos import composicao_do_quadro

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def test_quadro_0_poe_a_pessoa_no_cenario():
    t = composicao_do_quadro(0, [A, B, C])
    assert t.startswith("Place the person from image 2 into the scene of image 1, wearing the "
                        "garment from image 3")
    assert "Keep the room, walls, furniture, floor and lighting of image 1 unchanged" in t
    assert t.endswith("New state:")


def test_quadro_0_sem_corpo_base_renumera_o_produto():
    t = composicao_do_quadro(0, [A, None, C])
    assert t.startswith("Use the scene of image 1, wearing the garment from image 2")
    assert "person in image" not in t


def test_quadro_seguinte_ancora_produto_e_rosto():
    t = composicao_do_quadro(1, [A, B, C])
    assert t.startswith("Edit image 1: keep the same person, room, background")
    assert "exactly as in image 2" in t and "like the person in image 3" in t
    assert composicao_do_quadro(2, [A, None, C]).count("image 2") == 1
