"""O shop-tts antigo, sem as rotas /v2, dá uma mensagem clara (e não "Erro interno"); a voz
desconhecida (404 da regra do serviço) continua `internal` com a mensagem padrão."""

import httpx
import pytest

from sociman_api.geracao.erros import MENSAGENS, MotorErro
from sociman_api.geracao.shoptts import SEM_V2, ShopTtsClient


def _cliente(detail: str) -> ShopTtsClient:
    return ShopTtsClient("http://shop-tts:8200", transport=httpx.MockTransport(
        lambda r: httpx.Response(404, json={"detail": detail})))


def test_rota_v2_inexistente_tem_mensagem_propria():
    with pytest.raises(MotorErro) as exc:
        _cliente("Not Found").register(b"x", "a.wav", nome="v_abc", tom="t", n=3)
    assert exc.value.codigo == "internal" and exc.value.mensagem == SEM_V2


def test_voz_desconhecida_continua_padrao():
    with pytest.raises(MotorErro) as exc:
        _cliente("voz desconhecida: x").tts({"voice": "x", "sentences": ["oi"]})
    assert exc.value.mensagem == MENSAGENS["internal"]
