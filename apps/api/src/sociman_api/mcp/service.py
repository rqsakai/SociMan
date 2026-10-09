"""Gestão dos clientes MCP, do interruptor e do registro (R11, R13). Só o dono humano chega aqui
(as rotas usam `RequireHumanOwner`).

Toda mudança passa por `history.record` (`mcp_cliente`, `mcp_config`) e por um evento de
segurança. Nada guarda nem devolve o token, só o `token_id`; o token sai uma vez na resposta
de criar e rotacionar.
"""

import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.auth.events import record_event
from sociman_api.auth.models import User
from sociman_api.auth.router_events import decode_cursor, encode_cursor
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.mcp import credenciais, schemas
from sociman_api.mcp.models import (
    McpChamada,
    McpCliente,
    McpConfig,
    McpResultado,
    McpSituacao,
    McpVia,
)
from sociman_api.perfis.schemas import Autor, UserRef, Version, VersionsList

ENTITY = "mcp_cliente"
ENTITY_CONFIG = "mcp_config"
CONFIG_ENTITY_ID = uuid.UUID(int=9)  # o `entity_id` do histórico do singleton
LABEL = "Este cliente"
NAO_ENCONTRADO = "Cliente MCP não encontrado"
REVOGADO = "Este cliente foi revogado; crie outro"
VENCE_EM_BREVE = timedelta(days=7)
NO_LIMITE = timedelta(minutes=5)
_LINKS = {"anotacao": "/app/propostas?anotacao={id}", "envio": "/app/envios/{id}",
          "destino": "/app/conteudos?destino={id}"}


def normalizar_nome(nome: str) -> str:
    """Sem caixa nem acento, espaços colapsados (unicidade, `nome_em_uso`)."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", nome)
                         if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


# ---- leitura ----

def _cliente(db: Session, cliente_id: uuid.UUID, lock: bool = False) -> McpCliente:
    cliente = db.get(McpCliente, cliente_id, with_for_update=lock)
    if cliente is None:
        raise ApiError(404, "not_found", NAO_ENCONTRADO)
    return cliente


def _user_refs(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, UserRef]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.name).where(User.id.in_(wanted)))
    return {uid: UserRef(id=uid, name=name) for uid, name in rows}


def _uso(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[schemas.Uso24h, bool]]:
    """Chamadas, recusas e escritas em 24 h e "no limite" (429 nos últimos 5 min), por cliente."""
    if not ids:
        return {}
    agora = datetime.now(UTC)
    c = McpChamada
    recusa = c.resultado.in_((McpResultado.recusada, McpResultado.limite,
                              McpResultado.nao_autenticado))
    rows = db.execute(
        select(c.cliente_id, func.count(),
               func.count().filter(recusa),
               func.count().filter(c.escrita & (c.resultado == McpResultado.ok)),
               func.count().filter((c.resultado == McpResultado.limite)
                                   & (c.ocorreu_em >= agora - NO_LIMITE)))
        .where(c.cliente_id.in_(ids), c.ocorreu_em >= agora - timedelta(hours=24))
        .group_by(c.cliente_id))
    out = {cid: (schemas.Uso24h(chamadas=total, recusas=recusas, escritas=escritas), limite > 0)
           for cid, total, recusas, escritas, limite in rows}
    vazio = (schemas.Uso24h(chamadas=0, recusas=0, escritas=0), False)
    return {cid: out.get(cid, vazio) for cid in ids}


def _out(cliente: McpCliente, users: dict[uuid.UUID, UserRef],
         uso: tuple[schemas.Uso24h, bool]) -> schemas.ClienteMcp:
    agora = datetime.now(UTC)
    vence = (cliente.expira_em is not None and cliente.situacao != McpSituacao.revogado
             and cliente.expira_em - agora <= VENCE_EM_BREVE)
    return schemas.ClienteMcp(
        id=cliente.id, nome=cliente.nome, descricao=cliente.descricao, escopo=cliente.escopo,
        situacao=cliente.situacao, token_id=cliente.token_id,
        token_emitido_em=cliente.token_emitido_em, expira_em=cliente.expira_em,
        vence_em_breve=vence, limite_por_minuto=cliente.limite_por_minuto,
        limite_escritas_dia=cliente.limite_escritas_dia, ultimo_uso_em=cliente.ultimo_uso_em,
        uso24h=uso[0], no_limite=uso[1], revogado_em=cliente.revogado_em,
        revogado_por=users.get(cliente.revogado_por) if cliente.revogado_por else None,
        created_at=cliente.created_at,
        created_by=users.get(cliente.created_by) if cliente.created_by else None,
        version=cliente.version)


def clientes_out(db: Session, clientes: list[McpCliente]) -> list[schemas.ClienteMcp]:
    users = _user_refs(db, {c.created_by for c in clientes} | {c.revogado_por for c in clientes})
    uso = _uso(db, [c.id for c in clientes])
    return [_out(c, users, uso[c.id]) for c in clientes]


def cliente_out(db: Session, cliente: McpCliente) -> schemas.ClienteMcp:
    return clientes_out(db, [cliente])[0]


def listar(db: Session, situacao: McpSituacao | None = None) -> list[schemas.ClienteMcp]:
    ordem = case({McpSituacao.ativo: 0, McpSituacao.suspenso: 1, McpSituacao.revogado: 2},
                 value=McpCliente.situacao)
    stmt = select(McpCliente).order_by(ordem, McpCliente.nome_normalizado)
    if situacao is not None:
        stmt = stmt.where(McpCliente.situacao == situacao)
    return clientes_out(db, list(db.scalars(stmt)))


def obter(db: Session, cliente_id: uuid.UUID) -> schemas.ClienteMcp:
    return cliente_out(db, _cliente(db, cliente_id))


def versoes(db: Session, entity_type: str, entity_id: uuid.UUID) -> VersionsList:
    rows = history.list_versions(db, entity_type, entity_id)
    autores = history.autores(db, rows)
    users = _user_refs(db, {r.actor_user_id for r in rows})
    return VersionsList(items=[
        Version(version=r.version, action=r.action,
                actor=users.get(r.actor_user_id) if r.actor_user_id else None,
                actor_kind=r.actor_kind, autor=Autor(**autores[r.id]),
                occurred_at=r.occurred_at, changed_fields=list(r.changed_fields),
                before=r.before, after=r.after, details=r.details)
        for r in rows])


def versoes_cliente(db: Session, cliente_id: uuid.UUID) -> VersionsList:
    _cliente(db, cliente_id)
    return versoes(db, ENTITY, cliente_id)


# ---- mutações ----

def _expira_no_futuro(expira_em: datetime | None) -> None:
    if expira_em is None:
        return
    if expira_em.tzinfo is None:
        raise ApiError(400, "validation_error", "expiraEm: informe o fuso horário")
    if expira_em <= datetime.now(UTC):
        raise ApiError(400, "expira_no_passado", "O vencimento precisa ficar no futuro")


def _nome_livre(db: Session, nome: str, exceto: uuid.UUID | None = None) -> str:
    normal = normalizar_nome(nome)
    stmt = select(McpCliente.id).where(McpCliente.nome_normalizado == normal)
    if exceto is not None:
        stmt = stmt.where(McpCliente.id != exceto)
    if db.scalar(stmt) is not None:
        raise ApiError(409, "nome_em_uso", "Já existe um cliente com esse nome")
    return normal


def _token_id_livre(db: Session) -> tuple[str, str, bytes]:
    for _ in range(5):  # 40 bits: colisão é rara, mas o `<id>` precisa ser único
        token, token_id, hash_ = credenciais.gerar()
        if db.scalar(select(McpCliente.id).where(McpCliente.token_id == token_id)) is None:
            return token, token_id, hash_
    raise ApiError(500, "internal_error", "Não foi possível gerar a credencial")


def _evento(db: Session, actor: Actor, tipo: str, cliente: McpCliente,
            extra: dict[str, Any] | None = None) -> None:
    # Sem "token" no nome das chaves: o `record_event` apaga chaves com "token"/"hash".
    record_event(db, tipo, "ok", actor, details={
        "clienteId": str(cliente.id), "nome": cliente.nome, "credencial": cliente.token_id,
        **(extra or {})})


def _nao_revogado(cliente: McpCliente) -> None:
    if cliente.situacao == McpSituacao.revogado:
        raise ApiError(409, "mcp_cliente_revogado", REVOGADO)


def criar(db: Session, actor: Actor, body: schemas.CreateClienteIn
          ) -> tuple[McpCliente, str]:
    _expira_no_futuro(body.expira_em)
    normal = _nome_livre(db, body.nome)
    token, token_id, hash_ = _token_id_livre(db)
    cliente = McpCliente(
        id=uuid.uuid4(), nome=body.nome, nome_normalizado=normal, descricao=body.descricao,
        escopo=body.escopo, situacao=McpSituacao.ativo, token_id=token_id, token_hash=hash_,
        token_emitido_em=datetime.now(UTC), expira_em=body.expira_em,
        limite_por_minuto=body.limite_por_minuto, limite_escritas_dia=body.limite_escritas_dia,
        created_by=actor.user_id, updated_by=actor.user_id)
    db.add(cliente)
    try:
        db.flush()
    except IntegrityError as exc:  # corrida no nome único
        raise ApiError(409, "nome_em_uso", "Já existe um cliente com esse nome") from exc
    history.record(db, actor, ENTITY, cliente, "created", None, history.snapshot(cliente))
    _evento(db, actor, "mcp_cliente_criado", cliente, {"escopo": cliente.escopo.value})
    db.flush()
    return cliente, token


def _mudar(db: Session, actor: Actor, cliente: McpCliente, before: dict[str, Any],
           acao: str, action: str = "updated", evento: str | None = None) -> McpCliente:
    after = history.snapshot(cliente)
    if not history.diff(before, after):
        return cliente
    cliente.updated_by = actor.user_id
    history.record(db, actor, ENTITY, cliente, action, before, after, {"acao": acao})
    if evento is not None:
        _evento(db, actor, evento, cliente)
    db.flush()
    return cliente


def editar(db: Session, actor: Actor, cliente_id: uuid.UUID, body: schemas.UpdateClienteIn
           ) -> McpCliente:
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, body.version, LABEL)
    _nao_revogado(cliente)
    campos = body.model_fields_set
    before = history.snapshot(cliente)
    if body.nome is not None and body.nome != cliente.nome:
        cliente.nome_normalizado = _nome_livre(db, body.nome, exceto=cliente.id)
        cliente.nome = body.nome
    if body.descricao is not None:
        cliente.descricao = body.descricao
    if body.escopo is not None:
        cliente.escopo = body.escopo
    if "expira_em" in campos:
        if body.expira_em != cliente.expira_em:
            _expira_no_futuro(body.expira_em)
        cliente.expira_em = body.expira_em
    if body.limite_por_minuto is not None:
        cliente.limite_por_minuto = body.limite_por_minuto
    if body.limite_escritas_dia is not None:
        cliente.limite_escritas_dia = body.limite_escritas_dia
    return _mudar(db, actor, cliente, before, "editado")


def suspender(db: Session, actor: Actor, cliente_id: uuid.UUID, version: int) -> McpCliente:
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    cliente.situacao = McpSituacao.suspenso
    return _mudar(db, actor, cliente, before, "suspenso", evento="mcp_cliente_suspenso")


def reativar(db: Session, actor: Actor, cliente_id: uuid.UUID, version: int) -> McpCliente:
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    cliente.situacao = McpSituacao.ativo
    return _mudar(db, actor, cliente, before, "reativado", evento="mcp_cliente_reativado")


def rotacionar(db: Session, actor: Actor, cliente_id: uuid.UUID, version: int
               ) -> tuple[McpCliente, str]:
    """Token novo com `<id>` novo (o log distingue as gerações); o antigo cai na hora."""
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    token, token_id, hash_ = _token_id_livre(db)
    cliente.token_id = token_id
    cliente.token_hash = hash_
    cliente.token_emitido_em = datetime.now(UTC)
    cliente.updated_by = actor.user_id
    history.record(db, actor, ENTITY, cliente, "updated", before, history.snapshot(cliente),
                   {"acao": "rotacionado", "rotacao": True})
    _evento(db, actor, "mcp_cliente_rotacionado", cliente)
    db.flush()
    return cliente, token


def revogar(db: Session, actor: Actor, cliente_id: uuid.UUID, version: int) -> McpCliente:
    """Final (exceção do VII aprovada pelo dono): nunca volta, cria-se outro cliente."""
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    cliente.situacao = McpSituacao.revogado
    cliente.revogado_em = datetime.now(UTC)
    cliente.revogado_por = actor.user_id
    cliente.updated_by = actor.user_id
    history.record(db, actor, ENTITY, cliente, "archived", before, history.snapshot(cliente),
                   {"acao": "revogado"})
    _evento(db, actor, "mcp_cliente_revogado", cliente)
    db.flush()
    return cliente


# ---- interruptor ----

class _ConfigVersao:
    """Adaptador do singleton para o `history` (o `entity_id` do histórico é uuid)."""

    __versioned_fields__ = McpConfig.__versioned_fields__

    def __init__(self, cfg: McpConfig):
        self.id = CONFIG_ENTITY_ID
        self.version = cfg.version
        self.habilitado = cfg.habilitado


def config(db: Session, lock: bool = False) -> McpConfig:
    cfg = db.get(McpConfig, 1, with_for_update=lock)
    if cfg is None:  # a migration insere a linha; só por segurança
        cfg = McpConfig(id=1, habilitado=False, version=1)
        db.add(cfg)
        db.flush()
    return cfg


def config_out(cfg: McpConfig) -> schemas.McpConfig:
    return schemas.McpConfig(habilitado=cfg.habilitado,
                             servidor_habilitado=get_settings().mcp_habilitado,
                             version=cfg.version)


def config_update(db: Session, actor: Actor, body: schemas.McpConfigIn) -> schemas.McpConfig:
    cfg = config(db, lock=True)
    history.check_version(cfg, body.version, "Esta configuração")
    if cfg.habilitado != body.habilitado:
        alvo = _ConfigVersao(cfg)
        before = history.snapshot(alvo)
        cfg.habilitado = alvo.habilitado = body.habilitado
        cfg.updated_by = actor.user_id
        acao = "ligado" if body.habilitado else "desligado"
        history.record(db, actor, ENTITY_CONFIG, alvo, "updated", before,
                       history.snapshot(alvo), {"acao": acao})
        cfg.version = alvo.version
        record_event(db, "mcp_config_alterada", "ok", actor, details={"acao": acao})
        db.flush()
    return config_out(cfg)


def config_versoes(db: Session) -> VersionsList:
    return versoes(db, ENTITY_CONFIG, CONFIG_ENTITY_ID)


# ---- registro ----

def chamadas(db: Session, cliente_id: uuid.UUID | None, tool: str | None,
             resultado: McpResultado | None, via: McpVia | None, de: datetime | None,
             ate: datetime | None, cursor: str | None, limit: int) -> schemas.ChamadasPage:
    c = McpChamada
    stmt = select(c, McpCliente.nome).outerjoin(McpCliente, McpCliente.id == c.cliente_id)
    if cliente_id is not None:
        stmt = stmt.where(c.cliente_id == cliente_id)
    if tool:
        stmt = stmt.where(c.tool == tool)
    if resultado is not None:
        stmt = stmt.where(c.resultado == resultado)
    if via is not None:
        stmt = stmt.where(c.via == via)
    if de is not None:
        stmt = stmt.where(c.ocorreu_em >= de)
    if ate is not None:
        stmt = stmt.where(c.ocorreu_em <= ate)
    if cursor is not None:
        stmt = stmt.where(tuple_(c.ocorreu_em, c.id) < decode_cursor(cursor))
    rows = db.execute(stmt.order_by(c.ocorreu_em.desc(), c.id.desc()).limit(limit + 1)).all()
    page = rows[:limit]
    itens = []
    for ch, nome in page:
        entidade = None
        if ch.entidade_tipo and ch.entidade_id:
            link = _LINKS.get(ch.entidade_tipo, "/app").format(id=ch.entidade_id)
            entidade = schemas.EntidadeRef(tipo=ch.entidade_tipo, id=ch.entidade_id, link=link)
        itens.append(schemas.ChamadaMcp(
            id=ch.id, ocorreu_em=ch.ocorreu_em,
            cliente=schemas.ClienteRef(id=ch.cliente_id, nome=nome) if ch.cliente_id else None,
            via=ch.via, tool=ch.tool, metodo=ch.metodo, rota=ch.rota, args_resumo=ch.args_resumo,
            resultado=ch.resultado, status_http=ch.status_http, codigo_erro=ch.codigo_erro,
            duracao_ms=ch.duracao_ms, escrita=ch.escrita, entidade=entidade))
    last = page[-1][0] if page else None
    next_cursor = (encode_cursor(last.ocorreu_em, last.id)
                   if len(rows) > limit and last is not None else None)
    return schemas.ChamadasPage(chamadas=itens, next_cursor=next_cursor)
