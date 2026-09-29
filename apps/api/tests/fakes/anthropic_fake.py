"""Claude falso para os textos de postagem (T061): `httpx2.MockTransport` passado ao SDK por
`http_client` (o SDK 1.x usa o `httpx2`). Nenhuma chamada real e nenhuma chave de verdade.

Uso:
    from fakes.anthropic_fake import anthropic_fake  # noqa: F401  (fixture)

    anthropic_fake.responder("fora_dos_limites", "valida")  # uma resposta por chamada
    client = anthropic_fake.client()                       # IaClient com o fake
    anthropic_fake.bodies                                   # corpos JSON enviados

Cada item de `responder` é o nome de um arquivo de `tests/fixtures/anthropic/` (200), um dict
(200), `"timeout"` (o transporte levanta `ReadTimeout`) ou `(status, fixture_ou_dict)`. Sem
resposta enfileirada, devolve uma resposta válida **para o schema pedido** (spec 008: `proposta`,
`itens` ou os textos da postagem; `valida` na 006).

Spec 008: `anthropic_fake.ia_client()` devolve o `IaClient` com o fake; `mensagem(dados,
usage=..., model=...)` monta respostas com cache e `iterations` de fallback.
"""

import json
from collections import deque
from pathlib import Path
from typing import Any

import httpx2
import pytest

from sociman_api.ia.cliente import IaClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "anthropic"
CHAVE_TESTE = "chave-de-teste-do-claude"  # não casa com o padrão `sk-ant-…` do check:secrets


def fixture(nome: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{nome}.json").read_text())


def mensagem(dados: dict[str, Any], stop_reason: str = "end_turn",
             usage: dict[str, Any] | None = None, model: str | None = None) -> dict[str, Any]:
    """Resposta 200 com `dados` como o JSON da saída estruturada."""
    base = fixture("valida")
    base["content"] = [{"type": "text", "text": json.dumps(dados, ensure_ascii=False)}]
    base["stop_reason"] = stop_reason
    if usage is not None:
        base["usage"] = usage
    if model is not None:
        base["model"] = model
    return base


def texto(proposta: str, explicacao: str = "Deixei mais direto.",
          avisos: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    return mensagem({"proposta": proposta, "explicacao": explicacao, "avisos": avisos or []},
                    **kw)


def itens(*valores: str, explicacao: str = "Sugestões novas.",
          avisos: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    return mensagem({"itens": list(valores), "explicacao": explicacao, "avisos": avisos or []},
                    **kw)


def _padrao(body: dict[str, Any]) -> dict[str, Any]:
    """Uma resposta válida para o schema pedido (sem fila)."""
    props = (body.get("output_config", {}).get("format", {}).get("schema", {})
             .get("properties", {}))
    if "proposta" in props:
        return texto("Texto proposto pela IA.")
    if "itens" in props:
        return itens("#dica", "#casa", "#achadinhos")
    base = fixture("valida")
    if "explicacao" in props:
        dados = json.loads(base["content"][0]["text"])
        return mensagem(dados | {"explicacao": "Textos para o clipe.", "avisos": []})
    return base


class AnthropicFake:
    def __init__(self) -> None:
        self.fila: deque[Any] = deque()
        self.requests: list[httpx2.Request] = []
        self.transport = httpx2.MockTransport(self._handle)

    def responder(self, *itens: Any) -> None:
        self.fila.extend(itens)

    def client(self, **kwargs: Any) -> IaClient:
        """Desde a spec 008 o cliente do Claude é um só (o `TextosClient` da 006 virou este)."""
        return self.ia_client(**kwargs)

    def ia_client(self, **kwargs: Any) -> IaClient:
        kwargs.setdefault("max_retries", 0)
        return IaClient(api_key=CHAVE_TESTE, transport=self.transport, **kwargs)

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        item = self.fila.popleft() if self.fila else _padrao(json.loads(request.content))
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
