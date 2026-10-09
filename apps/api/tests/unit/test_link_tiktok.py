"""Link colado pelo dono (spec 016, R11): formatos aceitos e recusados, com o motivo."""

import pytest

from sociman_api.errors import ApiError
from sociman_api.metricas.vinculos import LINK_CURTO, LINK_INVALIDO, ler_link

GRANDE = "7412345678901234567"  # acima de 2^53: não pode passar por float


@pytest.mark.parametrize("link", [
    f"https://www.tiktok.com/@atavernanerd/video/{GRANDE}",
    f"https://www.tiktok.com/@atavernanerd/video/{GRANDE}?is_from_webapp=1&sender_device=pc",
    f"https://www.tiktok.com/@atavernanerd/video/{GRANDE}/",
    f"https://www.tiktok.com/@AtavernaNerd/video/{GRANDE}",
    f"  https://tiktok.com/@atavernanerd/video/{GRANDE}  ",
    f"https://m.tiktok.com/@atavernanerd/video/{GRANDE}#x",
])
def test_aceita_o_link_completo_e_preserva_o_id(link):
    assert ler_link(link, "atavernanerd") == GRANDE
    assert ler_link(link, "@atavernanerd") == GRANDE


@pytest.mark.parametrize("link", [
    "https://vm.tiktok.com/ZMabc123/",
    "https://vt.tiktok.com/ZSabc123",
    "vm.tiktok.com/ZMabc123",
])
def test_recusa_encurtado_com_o_motivo(link):
    with pytest.raises(ApiError) as exc:
        ler_link(link, "atavernanerd")
    assert (exc.value.status, exc.value.code, exc.value.message) == \
        (400, "link_invalido", LINK_CURTO)


@pytest.mark.parametrize("link", [
    "https://www.tiktok.com/@atavernanerd",
    "https://www.tiktok.com/@atavernanerd/photo/123",
    "https://www.youtube.com/watch?v=abc",
    "https://www.tiktok.com.evil.com/@atavernanerd/video/123",
    "",
])
def test_recusa_link_sem_video(link):
    with pytest.raises(ApiError) as exc:
        ler_link(link, "atavernanerd")
    assert (exc.value.status, exc.value.code, exc.value.message) == \
        (400, "link_invalido", LINK_INVALIDO)


def test_outra_conta_mostra_os_dois_arrobas():
    with pytest.raises(ApiError) as exc:
        ler_link(f"https://www.tiktok.com/@meusqueridinhos10/video/{GRANDE}", "atavernanerd")
    assert exc.value.status == 409
    assert exc.value.code == "link_outra_conta"
    assert exc.value.message == "O link é de @meusqueridinhos10; este destino é de @atavernanerd"
