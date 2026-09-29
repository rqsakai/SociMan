"""Entrada do usuário → consulta ao YouTube e custo (T021, research R2)."""

import pytest

from sociman_api.canais.resolve import resolver_entrada
from sociman_api.errors import ApiError

CID = "UC" + "a1B2c3D4e5F6g7H8i9J0_-"  # 24 caracteres


@pytest.mark.parametrize(("entrada", "tipo", "valor", "custo"), [
    (CID, "id", CID, 1),
    (f"  {CID}  ", "id", CID, 1),
    (f"https://www.youtube.com/channel/{CID}", "id", CID, 1),
    (f"youtube.com/channel/{CID}/videos", "id", CID, 1),
    ("@TheITNerd", "handle", "theitnerd", 1),
    ("https://www.youtube.com/@theitnerd", "handle", "theitnerd", 1),
    ("youtube.com/@theitnerd/videos", "handle", "theitnerd", 1),
    ("https://m.youtube.com/@The.IT-Nerd_", "handle", "the.it-nerd_", 1),
    ("https://www.youtube.com/user/techguy", "username", "techguy", 1),
    ("https://www.youtube.com/c/TheITNerd", "busca", "TheITNerd", 100),
    ("https://www.youtube.com/TheITNerd", "busca", "TheITNerd", 100),
    ("The IT Nerd", "busca", "The IT Nerd", 100),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "video", "dQw4w9WgXcQ", 2),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", "video", "dQw4w9WgXcQ", 2),
    ("youtu.be/dQw4w9WgXcQ", "video", "dQw4w9WgXcQ", 2),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "video", "dQw4w9WgXcQ", 2),
    ("https://www.youtube.com/live/dQw4w9WgXcQ", "video", "dQw4w9WgXcQ", 2),
])
def test_entrada_vira_consulta_com_custo(entrada, tipo, valor, custo):
    consulta = resolver_entrada(entrada)
    assert (consulta.tipo, consulta.valor, consulta.custo) == (tipo, valor, custo)


@pytest.mark.parametrize("entrada", [
    "", "   ", "@", "@ab",
    "https://vimeo.com/123456",
    "https://www.youtube.com/watch?x=1",
    "https://www.youtube.com/watch?v=curto",
    "https://youtu.be/",
    "https://www.youtube.com/",
    "https://www.youtube.com/playlist?list=PL123",
    "https://www.youtube.com.evil.com/@x",
    "algo/com/barras",
    "x" * 101,
])
def test_entrada_invalida(entrada):
    with pytest.raises(ApiError) as exc:
        resolver_entrada(entrada)
    assert exc.value.status == 400
    assert exc.value.code == "invalid_channel_input"
