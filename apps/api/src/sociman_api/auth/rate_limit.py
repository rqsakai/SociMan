"""Limite de tentativas em janela fixa no Redis (research.md R4)."""

import math
import time
from dataclasses import dataclass
from typing import Literal

import redis

from sociman_api.errors import ApiError
from sociman_api.redis import get_redis

Action = Literal["login", "forgot", "reset", "verify", "resend", "change"]


@dataclass(frozen=True)
class Limits:
    window: int
    per_ip: int | None
    per_account: int | None = None


LIMITS: dict[str, Limits] = {
    "login": Limits(window=15 * 60, per_ip=30, per_account=10),
    "forgot": Limits(window=60 * 60, per_ip=10, per_account=5),
    "reset": Limits(window=60 * 60, per_ip=10),
    "verify": Limits(window=60 * 60, per_ip=30),
    "resend": Limits(window=60 * 60, per_ip=30, per_account=5),
    "change": Limits(window=15 * 60, per_ip=None, per_account=10),
}


def _now() -> float:
    return time.time()


def check(action: Action, ip: str, account: str | None = None, r: redis.Redis | None = None) -> None:
    """Conta uma tentativa e levanta 429 `rate_limited` se o IP ou a conta estourou o limite.

    `account` é o e-mail (normalizado aqui) ou o id do usuário, conforme a ação.
    """
    r = r or get_redis()
    limits = LIMITS[action]
    now = _now()
    bucket = int(now // limits.window)
    keys: list[tuple[str, int]] = []
    if limits.per_ip is not None:
        keys.append((f"rl:{action}:ip:{bucket}:{ip}", limits.per_ip))
    if account is not None and limits.per_account is not None:
        keys.append((f"rl:{action}:acct:{bucket}:{account.strip().lower()}", limits.per_account))
    if not keys:
        return

    # Os dois contadores sobem mesmo que um já tenha estourado: é só +1 a mais.
    pipe = r.pipeline(transaction=True)
    for key, _ in keys:
        pipe.incr(key)
        pipe.expire(key, limits.window, nx=True)
    counts = pipe.execute()[::2]

    if any(count > limit for count, (_, limit) in zip(counts, keys, strict=True)):
        retry_after = max(1, math.ceil((bucket + 1) * limits.window - now))
        minutes = math.ceil(retry_after / 60)
        unit = "minuto" if minutes == 1 else "minutos"
        raise ApiError(
            429,
            "rate_limited",
            f"Muitas tentativas. Tente de novo em {minutes} {unit}.",
            headers={"Retry-After": str(retry_after)},
        )
