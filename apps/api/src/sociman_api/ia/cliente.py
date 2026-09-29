"""Cliente do Claude do assistente (research R8): o `TextosClient` da 006 generalizado.

Uma chamada `beta.messages.parse` com o schema do formato do tipo (`saida.SCHEMAS`):
- **sem tools** (princípio I: a IA só devolve texto), `max_tokens = 2000`, esforço `low`, sem
  `temperature` e sem desligar o `thinking` (o Sonnet 5.5 recusa os dois);
- `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`), como na 006;
- `timeout = 20 s` e `max_retries = 0` (as retentativas do SDK multiplicariam o tempo). Uma
  segunda tentativa só quando a validação recusa **e** a primeira levou menos de 10 s;
- `base_url` da config (`ANTHROPIC_BASE_URL`) quando não vazio: só o e2e aponta para o fake.

Nunca levanta: o erro vai em `erro_code` (`timeout`, `refusal`, `invalid`, `api_error`), para o
service gravar a chamada e traduzir. A chave nunca aparece em log, erro nem `repr`.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx2
import pydantic
from pydantic import BaseModel

from sociman_api.config import get_settings
from sociman_api.ia import saida
from sociman_api.ia.custo import Uso, somar
from sociman_api.ia.tipos import TipoCampo

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
TIMEOUT_S = 20.0
MAX_RETRIES = 0
MAX_TOKENS = 2000
SEGUNDA_TENTATIVA_ATE_S = 10.0


@dataclass
class Resultado:
    """O que vai para `ia_chamadas` (uma linha por geração, com proposta ou erro)."""

    model: str
    validada: saida.Validada | None = None
    erro_code: str | None = None  # timeout | refusal | invalid | api_error
    erro_status: int | None = None  # status HTTP do Claude, se houve
    uso: Uso = field(default_factory=Uso)
    duration_ms: int = 0


class IaClient:
    """`transport` só nos testes (httpx2.MockTransport)."""

    def __init__(self, api_key: str, model: str | None = None,
                 transport: httpx2.BaseTransport | None = None, timeout_s: float = TIMEOUT_S,
                 max_retries: int = MAX_RETRIES, base_url: str | None = None):
        self.model = model or get_settings().textos_model
        http_client = httpx2.Client(transport=transport) if transport is not None else None
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s,
                                           max_retries=max_retries, http_client=http_client,
                                           base_url=base_url or None)

    def __repr__(self) -> str:  # nunca mostra a chave
        return f"IaClient(model={self.model!r})"

    def _chamar(self, schema: type[BaseModel], system: list[dict[str, Any]], user: str) -> Any:
        return self._client.beta.messages.parse(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": "low"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )

    def gerar(self, tipo: TipoCampo, system: list[dict[str, Any]],
              user: Callable[[str | None], str],
              excluir: saida.Excluir = saida.NADA) -> Resultado:
        """`user(erro_anterior)` monta a mensagem do usuário (com o erro na 2ª tentativa)."""
        res = Resultado(model=self.model)
        schema = saida.SCHEMAS[tipo.formato]
        inicio = time.monotonic()
        erro_anterior: str | None = None
        melhor: BaseModel | None = None  # a última resposta que passou pelo parse
        try:
            for tentativa in (1, 2):
                t0 = time.monotonic()
                try:
                    resposta = self._chamar(schema, system, user(erro_anterior))
                except (pydantic.ValidationError, ValueError):
                    resposta = None  # o parse do SDK recusou o JSON: resposta inválida
                somar(res.uso, resposta, self.model)
                if getattr(resposta, "stop_reason", None) == "refusal":
                    res.erro_code = "refusal"
                    break
                parsed = getattr(resposta, "parsed_output", None)
                melhor = parsed or melhor
                problemas = (["a resposta não veio no formato JSON pedido"] if parsed is None
                             else saida.problemas(tipo, parsed, excluir))
                pode_repetir = (tentativa == 1
                                and time.monotonic() - t0 < SEGUNDA_TENTATIVA_ATE_S)
                if problemas and pode_repetir:
                    erro_anterior = "; ".join(problemas)
                    continue
                if melhor is None:
                    res.erro_code = "invalid"
                    break
                try:
                    res.validada = saida.finalizar(tipo, melhor, excluir)
                except saida.Invalida:
                    res.erro_code = "invalid"
                break
        except anthropic.APITimeoutError:
            res.erro_code = "timeout"
        except anthropic.APIStatusError as exc:
            res.erro_code, res.erro_status = "api_error", exc.status_code
            log.warning("Claude respondeu %s ao assistente", exc.status_code)
        except anthropic.APIConnectionError:
            res.erro_code = "api_error"
            log.warning("Claude fora do alcance para o assistente")
        res.duration_ms = int((time.monotonic() - inicio) * 1000)
        return res


def get_ia_client() -> IaClient | None:
    """Dependência das rotas. None = `ANTHROPIC_API_KEY` ausente (503 `claude_unconfigured`)."""
    settings = get_settings()
    key = settings.anthropic_api_key.get_secret_value()
    if not key:
        return None
    return IaClient(api_key=key, base_url=settings.anthropic_base_url)
