"""Portão da API para tokens do coletor (spec 026, FR-025): vale para **qualquer** requisição
com `Bearer scol_…`, em qualquer rota, antes da validação dos parâmetros (molde `mcp/portao.py`).

Ordem das recusas (contracts/http-api.md, "Permissões e atores"):

1. credencial que não confere → 401 `unauthorized` (mensagem neutra);
2. interruptor desligado (`COLETA_HABILITADA` **ou** o botão `coleta_config.habilitada`): o
   `GET /api/coleta/fila` passa e responde vazio (o coletor precisa saber que está desligado); as
   demais rotas C respondem 503 `coleta_desligada`;
3. revogado ou vencido → 401; suspenso → 403 `coleta_suspensa`;
4. `Origin` presente (navegador) → 403 `escopo_coleta`;
5. rota fora das rotas **C** da ingestão → 403 `escopo_coleta`;
6. `X-Sociman-Coleta-Protocolo` ausente ou diferente → 426 `protocolo_coleta`;
7. limite por minuto no Redis → 429 `coleta_limite` (Redis fora → 503 `coleta_indisponivel`).

Toda recusa grava `security_events` (`coleta_recusada`, `actor_kind = "coletor"`, com
`{motivo, tokenId, rota}` e nunca o token), numa sessão própria (armadilha 8). Toda passagem
atualiza `ultimo_contato_em`, `versao_coletor` e `chrome_versao` do cliente.
"""

import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import redis
from fastapi import Request
from sqlalchemy import select, update

from sociman_api.auth.deps import Actor, _unauthorized, bearer_token
from sociman_api.auth.events import record_event
from sociman_api.coleta import credenciais
from sociman_api.coleta.models import CONFIG_ID, ColetaCliente, ColetaConfig, ColetaSituacao
from sociman_api.config import get_settings
from sociman_api.db import get_sessionmaker
from sociman_api.errors import ApiError
from sociman_api.redis import get_redis

log = logging.getLogger(__name__)

_ATOR = "sociman.coleta.ator"
PROTOCOLO_HEADER = "x-sociman-coleta-protocolo"
VERSAO_HEADER = "x-sociman-coletor-versao"
CHROME_HEADER = "x-sociman-chrome-versao"
EVENTO_RECUSA = "coleta_recusada"
# As rotas C (operationIds) em que o token vale. O `GET /api/coleta/fila` passa mesmo com a
# coleta desligada (responde vazio); as outras recebem 503.
ROTAS_C = frozenset({"coleta_fila", "coleta_coletas_abrir", "coleta_itens_enviar",
                     "coleta_imagens_enviar", "coleta_batimento", "coleta_coletas_fechar",
                     "coleta_eventos_enviar", "coleta_bruto_link",
                     # leituras do `reprocessar --desde` (só as próprias rodadas; FR-012)
                     "coleta_coletas_listar", "coleta_coletas_detalhe"})
ROTAS_SEM_INTERRUPTOR = frozenset({"coleta_fila"})

DESLIGADA = "A coleta está desligada no servidor"
SUSPENSA = "Este token está suspenso"
ESCOPO = "Este token só vale para o serviço do coletor"
PROTOCOLO = "Atualize o sociman-coletor: o servidor fala o protocolo {esperado}"
LIMITE = "Muitas requisições do coletor; tente de novo em {s} s"
INDISPONIVEL = "Serviço da coleta indisponível (Redis)"
JANELA_S = 60


@dataclass(frozen=True)
class Cliente:
    id: uuid.UUID
    token_id: str
    mercado: str
    rede: str
    situacao: ColetaSituacao
    expira_em: datetime | None
    limite_por_minuto: int

    @classmethod
    def de(cls, c: ColetaCliente) -> "Cliente":
        return cls(c.id, c.token_id, c.mercado, c.rede.value, c.situacao, c.expira_em,
                   c.limite_por_minuto)

    def ator(self) -> Actor:
        return Actor(kind="coletor", coleta_cliente_id=self.id)


def interruptor_ligado(db) -> bool:
    """Os dois níveis (FR-033): `COLETA_HABILITADA` e o botão da tela."""
    if not get_settings().coleta_habilitada:
        return False
    cfg = db.get(ColetaConfig, CONFIG_ID)
    return bool(cfg is not None and cfg.habilitada)


def _registrar(motivo: str, token_id: str | None, rota: str, request: Request,
               cliente_id: uuid.UUID | None = None) -> None:
    session = get_sessionmaker()()
    try:
        details = {"motivo": motivo, "credencial": token_id, "rota": rota}
        if cliente_id is not None:
            details["clienteId"] = str(cliente_id)
        record_event(session, EVENTO_RECUSA, "denied", Actor(kind="coletor"), request=request,
                     details=details)
        session.commit()
    except Exception:  # a recusa sai de qualquer jeito
        session.rollback()
        log.exception("falha ao registrar %s", EVENTO_RECUSA)
    finally:
        session.close()


def _identificar(token: str) -> Cliente | None:
    session = get_sessionmaker()()
    try:
        cliente = credenciais.verificar(session, token)
        return Cliente.de(cliente) if cliente is not None else None
    finally:
        session.close()


def _situacao(cliente: Cliente) -> tuple[ApiError, str] | None:
    if cliente.situacao == ColetaSituacao.revogado or (
            cliente.expira_em is not None and cliente.expira_em <= datetime.now(UTC)):
        return _unauthorized(), "revogado_ou_vencido"
    if cliente.situacao == ColetaSituacao.suspenso:
        return ApiError(403, "coleta_suspensa", SUSPENSA), "suspenso"
    return None


def _limite(cliente: Cliente) -> None:
    agora = time.time()
    minuto = int(agora // JANELA_S)
    chave = f"coleta:limite:{cliente.id}:{minuto}"
    try:
        r = get_redis()
        pipe = r.pipeline(transaction=True)
        pipe.incr(chave)
        pipe.expire(chave, JANELA_S, nx=True)
        n = pipe.execute()[0]
    except redis.RedisError as exc:
        raise ApiError(503, "coleta_indisponivel", INDISPONIVEL) from exc
    if n > cliente.limite_por_minuto:
        espera = max(1, math.ceil((minuto + 1) * JANELA_S - agora))
        raise ApiError(429, "coleta_limite", LIMITE.format(s=espera),
                       headers={"Retry-After": str(espera)}, details={"retryAfterS": espera})


def _marcar_contato(cliente: Cliente, request: Request) -> None:
    session = get_sessionmaker()()
    try:
        valores = {"ultimo_contato_em": datetime.now(UTC),
                   "updated_at": ColetaCliente.updated_at}
        versao = request.headers.get(VERSAO_HEADER)
        chrome = request.headers.get(CHROME_HEADER)
        if versao:
            valores["versao_coletor"] = versao[:40]
        if chrome:
            valores["chrome_versao"] = chrome[:40]
        session.execute(update(ColetaCliente).where(ColetaCliente.id == cliente.id)
                        .values(**valores))
        session.commit()
    except Exception:  # informativo: a chamada segue
        session.rollback()
        log.exception("falha ao marcar o último contato do coletor")
    finally:
        session.close()


def _operacao(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "unique_id", None) or getattr(route, "name", None) or request.url.path


def _rota(request: Request) -> str:
    route = request.scope.get("route")
    return f"{request.method} {getattr(route, 'path', None) or request.url.path}"


def _decidir(request: Request, token: str) -> Actor:
    rota = _rota(request)
    cliente = _identificar(token)
    if cliente is None:
        _registrar("credencial", credenciais.token_id_de(token), rota, request)
        raise _unauthorized()

    def recusar(erro: ApiError, motivo: str) -> ApiError:
        _registrar(motivo, cliente.token_id, rota, request, cliente.id)
        return erro

    op = _operacao(request)
    session = get_sessionmaker()()
    try:
        ligada = interruptor_ligado(session)
    finally:
        session.close()
    # A fila responde vazia (o coletor dorme); o resto não roda com a coleta desligada.
    if not ligada and op in ROTAS_C and op not in ROTAS_SEM_INTERRUPTOR:
        raise recusar(ApiError(503, "coleta_desligada", DESLIGADA), "desligada")
    if (sit := _situacao(cliente)) is not None:
        raise recusar(*sit)
    if request.headers.get("origin"):
        raise recusar(ApiError(403, "escopo_coleta", ESCOPO), "origem")
    if op not in ROTAS_C:
        raise recusar(ApiError(403, "escopo_coleta", ESCOPO), "escopo")
    esperado = get_settings().coleta_protocolo
    if request.headers.get(PROTOCOLO_HEADER) != str(esperado):
        raise recusar(ApiError(426, "protocolo_coleta", PROTOCOLO.format(esperado=esperado),
                               details={"esperado": esperado}), "protocolo")
    try:
        _limite(cliente)
    except ApiError as exc:
        raise recusar(exc, "limite" if exc.status == 429 else "redis") from None
    _marcar_contato(cliente, request)
    request.scope["sociman.coleta.ligada"] = ligada
    return cliente.ator()


def ligada(request: Request) -> bool:
    """O que o portão viu do interruptor nesta requisição (para o `GET /fila` responder vazio)."""
    return bool(request.scope.get("sociman.coleta.ligada", False))


def ator(request: Request) -> Actor:
    """O ator `coletor` da requisição (decidido uma vez só: o limite conta uma vez)."""
    cached = request.scope.get(_ATOR)
    if cached is not None:
        return cached
    actor = _decidir(request, bearer_token(request) or "")
    request.scope[_ATOR] = actor
    return actor


def dependencia(request: Request) -> None:
    """Dependência global do app: passa todo token `scol_` pelo portão, mesmo em rota sem ator
    (login, health, mídia por link), antes da validação dos parâmetros."""
    if credenciais.e_token(bearer_token(request)):
        ator(request)


def cliente_de(actor: Actor, db) -> ColetaCliente:
    """O `ColetaCliente` do ator `coletor` (as rotas C precisam do mercado e da rede)."""
    cliente = db.scalar(select(ColetaCliente).where(ColetaCliente.id == actor.coleta_cliente_id))
    if cliente is None:
        raise _unauthorized()
    return cliente
