"""Limites de uso por cliente MCP (R7): janela fixa no Redis, no padrão do `auth/rate_limit.py`.

- `mcp:min:{cliente}:{minuto}`: até `limite_por_minuto` chamadas (TTL 60 s);
- `mcp:esc:{cliente}:{AAAA-MM-DD em America/Sao_Paulo}`: até `limite_escritas_dia` escritas
  (TTL 26 h), virando à meia-noite de Brasília.

Estourou → 429 `mcp_limite` com `Retry-After`. Redis fora do ar → 503 `mcp_indisponivel` (o
portão nega, como a sessão).
"""

import math
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import redis

from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.redis import get_redis

JANELA_MIN = 60
TTL_DIA = 26 * 60 * 60
INDISPONIVEL = "Limites de uso indisponíveis no momento; tente de novo em instantes"


def _agora() -> float:
    return time.time()


def _limite(retry_after: int, escrita_do_dia: bool) -> ApiError:
    msg = (f"Limite diário de escritas atingido, tente de novo em {retry_after} s"
           if escrita_do_dia else f"Limite de uso atingido, tente de novo em {retry_after} s")
    return ApiError(429, "mcp_limite", msg, headers={"Retry-After": str(retry_after)},
                    details={"retryAfterS": retry_after})


def verificar(cliente_id: uuid.UUID, limite_por_minuto: int, limite_escritas_dia: int,
              escrita: bool, r: redis.Redis | None = None) -> None:
    """Conta a chamada (e a escrita) e levanta 429 se passou de um dos limites."""
    agora = _agora()
    minuto = int(agora // JANELA_MIN)
    tz = ZoneInfo(get_settings().app_tz)
    local = datetime.fromtimestamp(agora, tz)
    chave_min = f"mcp:min:{cliente_id}:{minuto}"
    chave_dia = f"mcp:esc:{cliente_id}:{local.date().isoformat()}"
    try:
        r = r or get_redis()
        pipe = r.pipeline(transaction=True)
        pipe.incr(chave_min)
        pipe.expire(chave_min, JANELA_MIN, nx=True)
        if escrita:
            pipe.incr(chave_dia)
            pipe.expire(chave_dia, TTL_DIA, nx=True)
        res = pipe.execute()
    except redis.RedisError as exc:
        raise ApiError(503, "mcp_indisponivel", INDISPONIVEL) from exc
    if res[0] > limite_por_minuto:
        raise _limite(max(1, math.ceil((minuto + 1) * JANELA_MIN - agora)), False)
    if escrita and res[2] > limite_escritas_dia:
        meia_noite = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tz)
        raise _limite(max(1, math.ceil(meia_noite.timestamp() - agora)), True)
