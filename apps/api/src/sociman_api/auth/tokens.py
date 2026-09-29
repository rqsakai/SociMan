"""Access token (JWT) e famílias de renovação no Redis (research.md R2/R3).

- access: JWT HS256 curto, só em memória no SPA. Carrega `fam` porque o cookie de renovação só vai
  para /api/auth/refresh; o logout revoga a família pela claim.
- refresh: opaco, `{fam}.{segredo}`. O Redis guarda só o sha256 do token atual da família.
  Rotação a cada uso; o token imediatamente anterior vale por `refresh_grace` segundos (duas abas
  renovando juntas ou resposta perdida). Qualquer outro token da família é reuso e revoga tudo.
- a expiração da família é absoluta: a rotação não estende os `refresh_ttl` do login.
"""

import hashlib
import hmac
import math
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import jwt
import redis

from sociman_api.config import Settings, get_settings
from sociman_api.redis import get_redis

ISSUER = "sociman-auth"
AUDIENCE = "sociman"
LEEWAY_SECONDS = 30

# Rotação atômica: dois refresh simultâneos com o mesmo token não podem se atropelar.
# KEYS[1] = rt:{fam}; ARGV = hash apresentado, hash novo, agora (ms), carência (ms).
# Devolve {"ok", userId, restante_ms} | {"invalid"} | {"reused", userId}.
_ROTATE_LUA = """
local f = redis.call('HGETALL', KEYS[1])
if #f == 0 then return {'invalid'} end
local h = {}
for i = 1, #f, 2 do h[f[i]] = f[i + 1] end
local now = tonumber(ARGV[3])
local expires = tonumber(h['expiresAt'])
local is_current = h['tokenHash'] == ARGV[1]
local prev_exp = tonumber(h['prevExpiresAt'] or '0') or 0
local is_prev = (not is_current) and h['prevTokenHash'] ~= nil and h['prevTokenHash'] ~= ''
  and h['prevTokenHash'] == ARGV[1] and now < prev_exp
if not is_current and not is_prev then
  redis.call('DEL', KEYS[1])
  return {'reused', h['userId']}
end
local remaining = expires - now
if remaining <= 0 then
  redis.call('DEL', KEYS[1])
  return {'invalid'}
end
if is_current then
  redis.call('HSET', KEYS[1], 'tokenHash', ARGV[2], 'prevTokenHash', ARGV[1],
    'prevExpiresAt', tostring(now + tonumber(ARGV[4])))
else
  -- rotação pela carência não estende a janela original
  redis.call('HSET', KEYS[1], 'tokenHash', ARGV[2])
end
redis.call('PEXPIRE', KEYS[1], remaining)
return {'ok', h['userId'], tostring(remaining)}
"""


@dataclass(frozen=True)
class RotateOk:
    user_id: str
    fam: str
    access: str
    refresh: str
    remaining_seconds: int
    ok: Literal[True] = True


@dataclass(frozen=True)
class RotateFailed:
    reason: Literal["invalid", "reused"]
    ok: Literal[False] = False


RotateResult = RotateOk | RotateFailed


def _now_ms() -> int:
    return int(time.time() * 1000)


def _family_key(fam: str) -> str:
    return f"rt:{fam}"


def _user_key(user_id: str) -> str:
    return f"uf:{user_id}"


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_refresh(fam: str) -> str:
    return f"{fam}.{secrets.token_urlsafe(32)}"


def sign_access(user_id: str, fam: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now = int(time.time())
    claims = {
        "sub": user_id,
        "fam": fam,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + settings.access_ttl,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def decode_access(
    token: str, allow_expired: bool = False, settings: Settings | None = None
) -> dict[str, Any] | None:
    """Claims do access token, ou None se inválido.

    `allow_expired` existe só para o logout: um token expirado com assinatura válida ainda
    identifica a família a revogar. Mesmo assim, não aceita mais velho que a vida da família.
    """
    settings = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            leeway=settings.refresh_ttl if allow_expired else LEEWAY_SECONDS,
            options={"require": ["sub", "fam", "iss", "aud", "iat", "exp"]},
        )
    except jwt.PyJWTError:
        return None
    if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("fam"), str):
        return None
    return claims


def create_family(
    user_id: str, r: redis.Redis | None = None, settings: Settings | None = None
) -> tuple[str, str, str]:
    """Abre uma sessão: devolve `(access, refresh, fam)`."""
    r = r or get_redis()
    settings = settings or get_settings()
    fam = str(uuid.uuid4())
    refresh = _new_refresh(fam)
    ttl = settings.refresh_ttl
    pipe = r.pipeline(transaction=True)
    pipe.hset(_family_key(fam), mapping={
        "userId": user_id,
        "tokenHash": _sha256(refresh),
        "prevTokenHash": "",
        "prevExpiresAt": "0",
        "expiresAt": str(_now_ms() + ttl * 1000),
    })
    pipe.expire(_family_key(fam), ttl)
    pipe.sadd(_user_key(user_id), fam)
    pipe.expire(_user_key(user_id), ttl)
    pipe.execute()
    return sign_access(user_id, fam, settings), refresh, fam


def rotate(
    refresh: str, r: redis.Redis | None = None, settings: Settings | None = None
) -> RotateResult:
    r = r or get_redis()
    settings = settings or get_settings()
    fam, sep, secret = refresh.partition(".")
    if not fam or not sep or not secret:
        return RotateFailed("invalid")

    # Pré-checagem em tempo constante: um token que não é nem o atual nem o anterior conta como
    # reuso (o Lua repete a comparação de forma atômica, por igualdade de hash).
    presented = _sha256(refresh)
    stored = r.hmget(_family_key(fam), ["tokenHash", "prevTokenHash"])
    if stored[0] is None:
        return RotateFailed("invalid")
    known = [h for h in stored if h]
    matches = [hmac.compare_digest(presented, h) for h in known]
    if not any(matches):
        presented = ""  # força o reuso no script

    new_refresh = _new_refresh(fam)
    script = r.register_script(_ROTATE_LUA)
    res = script(
        keys=[_family_key(fam)],
        args=[presented, _sha256(new_refresh), _now_ms(), settings.refresh_grace * 1000],
    )
    status = res[0]
    if status == "reused":
        r.srem(_user_key(res[1]), fam)
        return RotateFailed("reused")
    if status != "ok":
        return RotateFailed("invalid")
    user_id = res[1]
    remaining = math.ceil(int(res[2]) / 1000)
    return RotateOk(
        user_id=user_id,
        fam=fam,
        access=sign_access(user_id, fam, settings),
        refresh=new_refresh,
        remaining_seconds=remaining,
    )


def family_alive(fam: str, r: redis.Redis | None = None) -> bool:
    r = r or get_redis()
    return bool(r.exists(_family_key(fam)))


def remaining_ttl(fam: str, r: redis.Redis | None = None) -> int:
    """Segundos até a expiração absoluta da família (0 se ela não existe mais)."""
    r = r or get_redis()
    expires = r.hget(_family_key(fam), "expiresAt")
    if expires is None:
        return 0
    return max(0, math.ceil((int(expires) - _now_ms()) / 1000))


def revoke_family(fam: str, r: redis.Redis | None = None) -> None:
    r = r or get_redis()
    user_id = r.hget(_family_key(fam), "userId")
    r.delete(_family_key(fam))
    if user_id:
        r.srem(_user_key(user_id), fam)


def revoke_all_for_user(
    user_id: str, except_fam: str | None = None, r: redis.Redis | None = None
) -> None:
    """Encerra todas as sessões do usuário, exceto `except_fam` (a sessão atual, FR-015)."""
    r = r or get_redis()
    fams = [f for f in r.smembers(_user_key(user_id)) if f != except_fam]
    pipe = r.pipeline(transaction=True)
    for fam in fams:
        pipe.delete(_family_key(fam))
    if except_fam is None:
        pipe.delete(_user_key(user_id))
    elif fams:
        pipe.srem(_user_key(user_id), *fams)
    pipe.execute()
