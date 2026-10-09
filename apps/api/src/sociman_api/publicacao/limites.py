"""Limites da rede por conta (research R10 da spec 015, FR-007).

- **Taxa por token**, compartilhada pela API e pelo agendador (processos diferentes): um contador
  no Redis por minuto, `publicacao:taxa:{conexao}:{endpoint}:{minuto}` (`INCR` + `EXPIRE 70`),
  com limites 1 abaixo dos da TikTok. Estourou → a trilha adia o passo; a rota do `creator_info`
  responde 429 `tente_em_instantes`. Perder o Redis só zera contadores de um minuto.
- **Rascunhos pendentes** (5 em 24 h, Clarifications Q1 = A): contam as tentativas da conexão em
  `criar_rascunho` com `init_enviado_em` nas últimas 24 h e fase aberta, `entregue` ou `incerta`
  (a TikTok pode já ter o rascunho). A contagem é local e conservadora.
"""

import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.conteudos.models import Modo
from sociman_api.publicacao.executor import SemResposta  # noqa: F401 — reexportado à trilha
from sociman_api.publicacao.models import FASES_OCUPAM_VAGA, Tentativa
from sociman_api.redis import get_redis

# Um abaixo dos limites da TikTok (6 init, 30 status e 20 creator_info por minuto e token).
TAXAS = {"init": 5, "status": 29, "creator_info": 19}
# Spec 016 (R18): leitura das métricas, 120 por minuto, por token e **por endpoint** (a TikTok
# permite 600). O `status/fetch` do vínculo usa a chave "status", compartilhada com a trilha.
TAXAS["leitura"] = 120
LEITURA = ("user_info", "video_list", "video_query")
RASCUNHOS_24H = 5
JANELA = timedelta(hours=24)


def _chave(conexao_id: uuid.UUID, endpoint: str, minuto: int) -> str:
    return f"publicacao:taxa:{conexao_id}:{endpoint}:{minuto}"


def consumir(conexao_id: uuid.UUID, endpoint: str, agora: float | None = None) -> bool:
    """Reserva um pedido no minuto atual. False = a taxa estourou (não chamar a rede). Os
    endpoints de `LEITURA` têm contador próprio, com o limite `TAXAS["leitura"]`."""
    limite = TAXAS["leitura"] if endpoint in LEITURA else TAXAS[endpoint]
    minuto = int((time.time() if agora is None else agora) // 60)
    chave = _chave(conexao_id, endpoint, minuto)
    r = get_redis()
    pipe = r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, 70)
    usados, _ = pipe.execute()
    return int(usados) <= limite


def vagas_rascunho(db: Session, conexao_id: uuid.UUID, agora: datetime
                   ) -> tuple[int, datetime | None]:
    """`(ocupadas, proxima_em)`: quantos rascunhos contam nas últimas 24 h e quando a vaga mais
    antiga se libera (menor `init_enviado_em` + 24 h; None sem nenhum)."""
    ocupadas, mais_antigo = db.execute(
        select(func.count(), func.min(Tentativa.init_enviado_em)).where(
            Tentativa.conexao_id == conexao_id,
            Tentativa.modo == Modo.criar_rascunho,
            Tentativa.init_enviado_em.is_not(None),
            Tentativa.init_enviado_em >= agora - JANELA,
            Tentativa.fase.in_(FASES_OCUPAM_VAGA),
        )
    ).one()
    return int(ocupadas), (mais_antigo + JANELA if mais_antigo is not None else None)
