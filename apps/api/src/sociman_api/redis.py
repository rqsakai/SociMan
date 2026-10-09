"""Cliente Redis (sessões de login e limites de tentativa; constitution 1.1.0)."""

from functools import lru_cache

import redis

from sociman_api.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
