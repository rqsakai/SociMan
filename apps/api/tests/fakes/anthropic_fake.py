"""Claude falso para os textos de postagem (T061): `httpx2.MockTransport` passado ao SDK por
`http_client` (o SDK 1.x usa o `httpx2`). Nenhuma chamada real e nenhuma chave de verdade.

Uso:
    from fakes.anthropic_fake import anthropic_fake  # noqa: F401  (fixture)

    anthropic_fake.responder("fora_dos_limites", "valida")  # uma resposta por chamada
    client = anthropic_fake.client()                       # TextosClient com o fake
    anthropic_fake.bodies                                   # corpos JSON enviados

Cada item de `responder` é o nome de um arquivo de `tests/fixtures/anthropic/` (200), um dict
(200), `"timeout"` (o transporte levanta `ReadTimeout`) ou `(status, fixture_ou_dict)`. Sem
resposta enfileirada, devolve `valida`.
"""

import json
from collections import deque
from pathlib import Path
from typing import Any

import httpx2
import pytest

from sociman_api.postagem.textos import TextosClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "anthropic"
CHAVE_TESTE = "chave-de-teste-do-claude"  # não casa com o padrão `sk-ant-…` do check:secrets


def fixture(nome: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{nome}.json").read_text())


def mensagem(dados: dict[str, Any], stop_reason: str = "end_turn") -> dict[str, Any]:
    """Resposta 200 com `dados` como o JSON da saída estruturada."""
    base = fixture("valida")
    base["content"] = [{"type": "text", "text": json.dumps(dados, ensure_ascii=False)}]
    base["stop_reason"] = stop_reason
    return base


class AnthropicFake:
    def __init__(self) -> None:
        self.fila: deque[Any] = deque()
        self.requests: list[httpx2.Request] = []
        self.transport = httpx2.MockTransport(self._handle)

    def responder(self, *itens: Any) -> None:
        self.fila.extend(itens)

    def client(self, **kwargs: Any) -> TextosClient:
        kwargs.setdefault("max_retries", 0)  # sem backoff nos testes
        return TextosClient(api_key=CHAVE_TESTE, transport=self.transport, **kwargs)

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        item = self.fila.popleft() if self.fila else "valida"
        if item == "timeout":
            raise httpx2.ReadTimeout("timeout do fake", request=request)
        status = 200
        if isinstance(item, tuple):
            status, item = item
        body = fixture(item) if isinstance(item, str) else item
        return httpx2.Response(status, json=body, headers={"request-id": "req_fake"})


@pytest.fixture
def anthropic_fake() -> AnthropicFake:
    return AnthropicFake()
