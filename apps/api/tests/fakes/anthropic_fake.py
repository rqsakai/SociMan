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

Spec 017: a resposta padrão cobre os formatos `guia` (`guia(...)`) e `variacoes`
(`variacoes(...)`, 3 textos de postagem **sem** hashtags fixas: quem inclui é o servidor);
`anthropic_fake.systems` devolve o `system` enviado em cada chamada (texto dos blocos) e
`anthropic_fake.system_blocos` os blocos crus (para conferir a ordem e o `cache_control`).
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


def guia(explicacao: str = "Montei o guia a partir da descrição.",
         avisos: list[str] | None = None, **campos: Any) -> dict[str, Any]:
    dados = {"tom": "Descontraído e direto, como quem conversa com um amigo.",
             "faca": ["Fale com o público de você"], "nao_faca": ["Não use gírias ofensivas"],
             "vocabulario": ["achadinho"], "proibidas": ["clickbait"], "emojis": "moderado",
             "emojis_preferidos": ["✨"]} | campos
    return mensagem(dados | {"explicacao": explicacao, "avisos": avisos or []})


def variacoes(*titulos: str, hashtags: list[str] | None = None,
              explicacao: str = "Três versões com o guia.",
              avisos: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    titulos = titulos or ("Primeira versão do título", "Segunda versão do título",
                          "Terceira versão do título")
    tags = hashtags or ["#tecnologia", "#dicas", "#produtividade"]
    return mensagem({"variacoes": [{"titulo": t, "descricao": f"Descrição de {t.lower()}.",
                                    "hashtags": list(tags)} for t in titulos],
                     "explicacao": explicacao, "avisos": avisos or []}, **kw)


def campos_cena(explicacao: str = "Ajustei a cena.", avisos: list[str] | None = None,
                **campos: str) -> dict[str, Any]:
    """Spec 010 (`cena.ajustar`): os 4 campos da cena."""
    dados = {"acao": "lifts the lid slowly and smiles at the product",
             "camera": "eye level, shallow depth of field", "estilo": "warm soft light",
             "audio": "gentle kitchen ambience"} | campos
    return mensagem(dados | {"explicacao": explicacao, "avisos": avisos or []})


def _padrao(body: dict[str, Any]) -> dict[str, Any]:
    """Uma resposta válida para o schema pedido (sem fila)."""
    props = (body.get("output_config", {}).get("format", {}).get("schema", {})
             .get("properties", {}))
    if "proposta" in props:
        return texto("Texto proposto pela IA.")
    if "variacoes" in props:
        return variacoes()
    if "tom" in props:
        return guia()
    if "acao" in props:  # spec 010
        return campos_cena()
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

    @property
    def system_blocos(self) -> list[list[dict[str, Any]]]:
        return [b.get("system") or [] for b in self.bodies]

    @property
    def systems(self) -> list[str]:
        """O `system` de cada chamada, com os blocos juntos por linha em branco."""
        return ["\n\n".join(bl.get("text", "") for bl in blocos)
                for blocos in self.system_blocos]

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
