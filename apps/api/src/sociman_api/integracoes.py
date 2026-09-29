"""Estado das integrações: YouTube, OpenShorts e Claude (contracts/http-api.md da 006, R15).

`GET /api/integracoes` (dono e membro) diz só `ok | ausente | invalida | fora`, **sem nenhum valor
de chave**:
- `youtube`: `ausente` sem `YOUTUBE_API_KEY`; `invalida` quando o último erro de sync de algum
  canal ativo é de chave recusada (`canais.youtube.chave_invalida`);
- `openshorts`: `/health` pelo cliente da trilha B, com timeout de 2 s e cache de 30 s;
- `claude`: `ok` ou `ausente` (a chave só é validada de fato na primeira sugestão);
- `cotaYoutube`: unidades do dia (fuso do Pacífico, quando o Google zera; `cota_atual` da
  trilha A) e a renovação em `APP_TZ`.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy.orm import Session

from sociman_api.auth.deps import RequireUser
from sociman_api.auth.schemas import CamelModel
from sociman_api.canais import youtube
from sociman_api.config import get_settings
from sociman_api.db import DbSession
from sociman_api.errors import ErrorEnvelope

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

OPENSHORTS_TIMEOUT_S = 2.0
OPENSHORTS_CACHE_S = 30.0


class CotaYoutube(CamelModel):
    usadas: int
    limite: int
    renova_em: datetime  # meia-noite do Pacífico, em APP_TZ


class Integracoes(CamelModel):
    youtube: Literal["ok", "ausente", "invalida"]
    openshorts: Literal["ok", "fora"]
    claude: Literal["ok", "ausente"]
    cota_youtube: CotaYoutube


# ---- OpenShorts (/health com cache) ----

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, bool]] = {}


def _openshorts_ok() -> bool:
    """Chama o `/health` pelo cliente da trilha B; qualquer falha = fora."""
    try:
        from sociman_api.envios.openshorts import get_openshorts_client

        client = get_openshorts_client()
        try:
            resultado = client.health(timeout=OPENSHORTS_TIMEOUT_S)
        except TypeError:  # cliente sem o parâmetro `timeout`
            resultado = client.health()
        return resultado is not False
    except Exception:  # fora do ar, recusado, timeout ou cliente ausente
        log.info("OpenShorts sem resposta no /health", exc_info=True)
        return False


def openshorts_status(agora: float | None = None) -> Literal["ok", "fora"]:
    agora = time.monotonic() if agora is None else agora
    with _cache_lock:
        hit = _cache.get("openshorts")
        if hit is not None and agora - hit[0] < OPENSHORTS_CACHE_S:
            return "ok" if hit[1] else "fora"
    ok = _openshorts_ok()
    with _cache_lock:
        _cache["openshorts"] = (agora, ok)
    return "ok" if ok else "fora"


def limpar_cache() -> None:
    with _cache_lock:
        _cache.clear()


# ---- YouTube ----

def youtube_status(db: Session) -> Literal["ok", "ausente", "invalida"]:
    if not youtube.configurado():
        return "ausente"
    return "invalida" if youtube.chave_invalida(db) else "ok"


def cota_youtube(db: Session, agora: datetime | None = None) -> CotaYoutube:
    cota = youtube.cota_atual(db, agora)
    return CotaYoutube(usadas=cota.usadas, limite=cota.limite,
                       renova_em=cota.renova_em.astimezone(ZoneInfo(get_settings().app_tz)))


@router.get("/integracoes", operation_id="integracoes_get", response_model=Integracoes,
            responses={s: {"model": ErrorEnvelope} for s in (401, 403)})
def get_integracoes(actor: RequireUser, db: DbSession) -> Integracoes:
    s = get_settings()
    return Integracoes(
        youtube=youtube_status(db),
        openshorts=openshorts_status(),
        claude="ok" if s.anthropic_api_key.get_secret_value() else "ausente",
        cota_youtube=cota_youtube(db),
    )
