"""Gestão da coleta (FR-033..FR-036) e leitura do estado: só o dono humano escreve (as rotas
usam `RequireHumanOwner`); dono e membro leem o estado.

Toda mudança passa por `history.record` (`coleta_cliente`, `coleta_config`); o aceite de risco
grava também o evento de segurança `coleta_aceite_risco`. Nada guarda nem devolve o token, só
o `token_id`; o token sai uma vez na resposta de criar e rotacionar (molde `mcp/service.py`).
"""

import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.auth.events import record_event
from sociman_api.auth.models import User
from sociman_api.auth.router_events import decode_cursor, encode_cursor
from sociman_api.coleta import comum, credenciais, ingestao, schemas
from sociman_api.coleta.models import (
    CONFIG_ID,
    ColetaCliente,
    ColetaConfig,
    ColetaSituacao,
    Evento,
    EventoTipo,
)
from sociman_api.errors import ApiError
from sociman_api.mercado import mercados
from sociman_api.mercado.constantes import COLETA_PARADA_H
from sociman_api.mercado.models import (
    COLETA_ABERTAS,
    Coleta,
    ColetaEstado,
    ColetaItem,
    FilaEstado,
    ItemStatus,
    Tarefa,
)
from sociman_api.perfis.schemas import Autor, UserRef, Version, VersionsList

ENTITY = "coleta_cliente"
LABEL = "Este cliente"
LABEL_CONFIG = "Esta configuração"
NAO_ENCONTRADO = "Cliente de coleta não encontrado"
REVOGADO = "Este token foi revogado (definitivo)"
RISCO = "Aceite de risco pendente: leia o aviso e confirme antes de ligar"
TEXTO_RISCO = (
    "A coleta usa a conta de afiliado do dono, logada no Chrome do desktop. Os Termos da rede "
    "proíbem coleta automatizada: a rede pode exigir verificação, limitar ou suspender essa conta, "
    "e com ela a comissão. O robô só lê, em ritmo humano, e para em captcha, login perdido ou "
    "bloqueio. As fotos que clientes anexam às avaliações são guardadas como vêm (dado pessoal de "
    "terceiros, decisão do dono). Registro legível: docs/decisoes/coleta-mercado.md.")
TEXTO_RISCO_VERSAO = "2026-10-08"


def normalizar_nome(nome: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", nome)
                         if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


# ---- leitura comum ----

def _user_refs(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, UserRef]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.name).where(User.id.in_(wanted)))
    return {uid: UserRef(id=uid, name=name) for uid, name in rows}


def _versoes(db: Session, entity_type: str, entity_id: uuid.UUID) -> VersionsList:
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


# ---- clientes ----

def _cliente(db: Session, cliente_id: uuid.UUID, lock: bool = False) -> ColetaCliente:
    cliente = db.get(ColetaCliente, cliente_id, with_for_update=lock)
    if cliente is None:
        raise ApiError(404, "not_found", NAO_ENCONTRADO)
    return cliente


def cliente_out(db: Session, c: ColetaCliente) -> schemas.ColetaCliente:
    users = _user_refs(db, {c.created_by, c.revogado_por})
    return schemas.ColetaCliente(
        id=c.id, nome=c.nome, descricao=c.descricao, rede=c.rede, mercado=c.mercado,
        situacao=c.situacao, token_id=c.token_id, token_emitido_em=c.token_emitido_em,
        expira_em=c.expira_em, limite_por_minuto=c.limite_por_minuto,
        ultimo_contato_em=c.ultimo_contato_em, versao_coletor=c.versao_coletor,
        chrome_versao=c.chrome_versao, revogado_em=c.revogado_em,
        revogado_por=users.get(c.revogado_por) if c.revogado_por else None,
        created_at=c.created_at, created_by=users.get(c.created_by) if c.created_by else None,
        version=c.version)


def listar_clientes(db: Session) -> list[schemas.ColetaCliente]:
    ordem = case({ColetaSituacao.ativo: 0, ColetaSituacao.suspenso: 1, ColetaSituacao.revogado: 2},
                 value=ColetaCliente.situacao)
    rows = db.scalars(select(ColetaCliente).order_by(ordem, ColetaCliente.nome_normalizado))
    return [cliente_out(db, c) for c in rows]


def _expira_no_futuro(expira_em: datetime | None) -> None:
    if expira_em is None:
        return
    if expira_em.tzinfo is None:
        raise ApiError(400, "entrada_invalida", "expiraEm: informe o fuso horário",
                       details={"field": "expiraEm"})
    if expira_em <= datetime.now(UTC):
        raise ApiError(400, "entrada_invalida", "O vencimento precisa ficar no futuro",
                       details={"field": "expiraEm"})


def _nome_livre(db: Session, nome: str, exceto: uuid.UUID | None = None) -> str:
    normal = normalizar_nome(nome)
    stmt = select(ColetaCliente.id).where(ColetaCliente.nome_normalizado == normal)
    if exceto is not None:
        stmt = stmt.where(ColetaCliente.id != exceto)
    if db.scalar(stmt) is not None:
        raise ApiError(409, "nome_em_uso", "Já existe um cliente com este nome")
    return normal


def _token_livre(db: Session) -> tuple[str, str, bytes]:
    for _ in range(5):
        token, token_id, hash_ = credenciais.gerar()
        if db.scalar(select(ColetaCliente.id).where(ColetaCliente.token_id == token_id)) is None:
            return token, token_id, hash_
    raise ApiError(500, "internal_error", "Não foi possível gerar a credencial")


def _evento(db: Session, actor: Actor, tipo: str, cliente: ColetaCliente,
            extra: dict[str, Any] | None = None) -> None:
    record_event(db, tipo, "ok", actor, details={
        "clienteId": str(cliente.id), "nome": cliente.nome, "credencial": cliente.token_id,
        **(extra or {})})


def _nao_revogado(cliente: ColetaCliente) -> None:
    if cliente.situacao == ColetaSituacao.revogado:
        raise ApiError(409, "cliente_revogado", REVOGADO)


def _interromper_rodadas(db: Session, cliente_id: uuid.UUID, motivo: str) -> None:
    for coleta in db.scalars(select(Coleta).where(Coleta.cliente_id == cliente_id,
                                                  Coleta.estado.in_(COLETA_ABERTAS))):
        ingestao._terminar(coleta, ColetaEstado.interrompida, motivo)
        ingestao.devolver_reservas(db, coleta)


def criar_cliente(db: Session, actor: Actor, body: schemas.CriarClienteIn
                  ) -> tuple[ColetaCliente, str]:
    mercados.mercado(body.mercado)  # 400 se desconhecido
    _expira_no_futuro(body.expira_em)
    normal = _nome_livre(db, body.nome)
    token, token_id, hash_ = _token_livre(db)
    cliente = ColetaCliente(
        id=uuid.uuid4(), nome=body.nome, nome_normalizado=normal, descricao=body.descricao,
        rede=body.rede, mercado=body.mercado, situacao=ColetaSituacao.ativo, token_id=token_id,
        token_hash=hash_, token_emitido_em=datetime.now(UTC), expira_em=body.expira_em,
        limite_por_minuto=body.limite_por_minuto, created_by=actor.user_id,
        updated_by=actor.user_id)
    db.add(cliente)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ApiError(409, "nome_em_uso", "Já existe um cliente com este nome") from exc
    history.record(db, actor, ENTITY, cliente, "created", None, history.snapshot(cliente))
    _evento(db, actor, "coleta_cliente_criado", cliente)
    db.flush()
    return cliente, token


def _mudar(db: Session, actor: Actor, cliente: ColetaCliente, before: dict[str, Any],
           acao: str, evento: str | None = None) -> ColetaCliente:
    after = history.snapshot(cliente)
    if not history.diff(before, after):
        return cliente
    cliente.updated_by = actor.user_id
    history.record(db, actor, ENTITY, cliente, "updated", before, after, {"acao": acao})
    if evento is not None:
        _evento(db, actor, evento, cliente)
    db.flush()
    return cliente


def editar_cliente(db: Session, actor: Actor, cliente_id: uuid.UUID,
                   body: schemas.EditarClienteIn) -> ColetaCliente:
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, body.version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    if body.nome is not None and body.nome != cliente.nome:
        cliente.nome_normalizado = _nome_livre(db, body.nome, exceto=cliente.id)
        cliente.nome = body.nome
    if body.descricao is not None:
        cliente.descricao = body.descricao
    if "expira_em" in body.model_fields_set:
        if body.expira_em != cliente.expira_em:
            _expira_no_futuro(body.expira_em)
        cliente.expira_em = body.expira_em
    if body.limite_por_minuto is not None:
        cliente.limite_por_minuto = body.limite_por_minuto
    return _mudar(db, actor, cliente, before, "editado")


def rotacionar(db: Session, actor: Actor, cliente_id: uuid.UUID, version: int
               ) -> tuple[ColetaCliente, str]:
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    token, token_id, hash_ = _token_livre(db)
    cliente.token_id, cliente.token_hash = token_id, hash_
    cliente.token_emitido_em = datetime.now(UTC)
    _interromper_rodadas(db, cliente.id, "token_rotacionado")
    _mudar(db, actor, cliente, before, "rotacionado", "coleta_cliente_rotacionado")
    return cliente, token


def suspender(db: Session, actor: Actor, cliente_id: uuid.UUID, version: int) -> ColetaCliente:
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    cliente.situacao = ColetaSituacao.suspenso
    _interromper_rodadas(db, cliente.id, "token_suspenso")
    return _mudar(db, actor, cliente, before, "suspenso", "coleta_cliente_suspenso")


def reativar(db: Session, actor: Actor, cliente_id: uuid.UUID, version: int) -> ColetaCliente:
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    cliente.situacao = ColetaSituacao.ativo
    return _mudar(db, actor, cliente, before, "reativado", "coleta_cliente_reativado")


def revogar(db: Session, actor: Actor, cliente_id: uuid.UUID, version: int) -> ColetaCliente:
    cliente = _cliente(db, cliente_id, lock=True)
    history.check_version(cliente, version, LABEL)
    _nao_revogado(cliente)
    before = history.snapshot(cliente)
    cliente.situacao = ColetaSituacao.revogado
    cliente.revogado_em = datetime.now(UTC)
    cliente.revogado_por = actor.user_id
    _interromper_rodadas(db, cliente.id, "token_revogado")
    return _mudar(db, actor, cliente, before, "revogado", "coleta_cliente_revogado")


def versoes_cliente(db: Session, cliente_id: uuid.UUID) -> VersionsList:
    _cliente(db, cliente_id)
    return _versoes(db, ENTITY, cliente_id)


# ---- configuração ----

def config_out(db: Session, cfg: ColetaConfig) -> schemas.ColetaConfig:
    users = _user_refs(db, {cfg.risco_aceito_por, cfg.updated_by})
    return schemas.ColetaConfig(
        habilitada=cfg.habilitada, servidor_habilitado=comum.servidor_habilitado(),
        risco_aceito=cfg.risco_aceito_em is not None, risco_aceito_em=cfg.risco_aceito_em,
        risco_aceito_por=users.get(cfg.risco_aceito_por) if cfg.risco_aceito_por else None,
        risco_texto_versao=cfg.risco_texto_versao, texto_risco=TEXTO_RISCO,
        texto_risco_versao=TEXTO_RISCO_VERSAO,
        janela_inicio=cfg.janela_inicio, janela_fim=cfg.janela_fim, paginas_dia=cfg.paginas_dia,
        imagens_dia=cfg.imagens_dia, imagens_por_produto=cfg.imagens_por_produto,
        itens_por_coleta=cfg.itens_por_coleta, pausa_min_s=cfg.pausa_min_s,
        pausa_max_s=cfg.pausa_max_s, pausada_ate=cfg.pausada_ate, continuar_em=cfg.continuar_em,
        version=cfg.version, updated_at=cfg.updated_at if cfg.version else None,
        updated_by=users.get(cfg.updated_by) if cfg.version and cfg.updated_by else None)


def _config_para_escrever(db: Session, actor: Actor, version: int) -> tuple[ColetaConfig, dict]:
    """A linha travada (ou criada com os padrões na primeira escrita) e o snapshot `before`."""
    cfg = db.get(ColetaConfig, CONFIG_ID, with_for_update=True)
    if cfg is None:
        if version != 0:
            raise ApiError(409, "version_conflict", "Recarregue e tente de novo",
                           details={"versaoAtual": 0})
        cfg = ColetaConfig(id=CONFIG_ID, habilitada=False, created_by=actor.user_id,
                           updated_by=actor.user_id, version=0)
        db.add(cfg)
        db.flush()
        db.refresh(cfg)
        cfg.version = 0
        return cfg, {}
    history.check_version(cfg, version, LABEL_CONFIG)
    return cfg, history.snapshot(cfg)


def _gravar_config(db: Session, actor: Actor, cfg: ColetaConfig, before: dict,
                   acao: str, extra: dict[str, Any] | None = None) -> ColetaConfig:
    if cfg.habilitada and cfg.risco_aceito_em is None:
        raise ApiError(409, "risco_nao_aceito", RISCO)
    cfg.updated_by = actor.user_id
    action = "created" if not before else "updated"
    history.record(db, actor, comum.ENTITY_CONFIG, comum.ConfigEntidade(cfg), action,
                   before or None, history.snapshot(cfg), {"acao": acao, **(extra or {})})
    db.flush()
    return cfg


def atualizar_config(db: Session, actor: Actor, body: schemas.ColetaConfigIn) -> ColetaConfig:
    if body.janela_inicio >= body.janela_fim:
        raise ApiError(400, "entrada_invalida", "A janela precisa começar antes de terminar",
                       details={"field": "janelaInicio"})
    if body.pausa_min_s > body.pausa_max_s:
        raise ApiError(400, "entrada_invalida", "A pausa mínima não pode passar da máxima",
                       details={"field": "pausaMinS"})
    cfg, before = _config_para_escrever(db, actor, body.version)
    if body.habilitada and cfg.risco_aceito_em is None:
        raise ApiError(409, "risco_nao_aceito", RISCO)
    for campo in ("habilitada", "janela_inicio", "janela_fim", "paginas_dia", "imagens_dia",
                  "imagens_por_produto", "itens_por_coleta", "pausa_min_s", "pausa_max_s"):
        setattr(cfg, campo, getattr(body, campo))
    return _gravar_config(db, actor, cfg, before, "ligada" if cfg.habilitada else "editada")


def aceitar_risco(db: Session, actor: Actor, body: schemas.AceitarRiscoIn) -> ColetaConfig:
    if not body.confirmo:
        raise ApiError(400, "entrada_invalida", "Marque a confirmação para aceitar o risco",
                       details={"field": "confirmo"})
    cfg, before = _config_para_escrever(db, actor, body.version)
    cfg.risco_aceito_em = datetime.now(UTC)
    cfg.risco_aceito_por = actor.user_id
    cfg.risco_texto_versao = body.texto_versao
    record_event(db, "coleta_aceite_risco", "ok", actor,
                 details={"textoVersao": body.texto_versao})
    return _gravar_config(db, actor, cfg, before, "aceite_risco")


def pausar(db: Session, actor: Actor, body: schemas.PausarIn) -> ColetaConfig:
    cfg, before = _config_para_escrever(db, actor, body.version)
    cfg.pausada_ate = datetime.now(UTC) + timedelta(hours=body.horas)
    return _gravar_config(db, actor, cfg, before, "pausada", {"horas": body.horas})


def continuar(db: Session, actor: Actor, body: schemas.ContinuarIn) -> ColetaConfig:
    pausadas = db.scalars(select(Coleta).where(Coleta.estado.in_(
        (ColetaEstado.pausada_captcha, ColetaEstado.pausada_login)))).all()
    if not pausadas:
        raise ApiError(409, "nada_a_continuar", "Nenhuma rodada está pausada")
    cfg, before = _config_para_escrever(db, actor, body.version)
    cfg.continuar_em = datetime.now(UTC)
    return _gravar_config(db, actor, cfg, before, "continuar",
                          {"rodadas": [str(c.id) for c in pausadas]})


def versoes_config(db: Session) -> VersionsList:
    return _versoes(db, comum.ENTITY_CONFIG, comum.CONFIG_ENTITY_ID)


def reverter_config(db: Session, actor: Actor, body: schemas.ColetaRevertIn) -> ColetaConfig:
    cfg, before = _config_para_escrever(db, actor, body.version)
    alvo = history.version_state(db, comum.ENTITY_CONFIG, comum.CONFIG_ENTITY_ID, body.to_version)
    if alvo is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    for campo in ColetaConfig.__versioned_fields__:
        if campo not in alvo:
            continue
        valor = alvo[campo]
        if campo in ("risco_aceito_em", "pausada_ate", "continuar_em") and valor:
            valor = datetime.fromisoformat(valor)
        if campo == "risco_aceito_por" and valor:
            valor = uuid.UUID(valor)
        setattr(cfg, campo, valor)
    cfg.updated_by = actor.user_id
    if cfg.habilitada and cfg.risco_aceito_em is None:
        raise ApiError(409, "risco_nao_aceito", RISCO)
    history.record(db, actor, comum.ENTITY_CONFIG, comum.ConfigEntidade(cfg), "reverted", before,
                   history.snapshot(cfg), {"toVersion": body.to_version})
    db.flush()
    return cfg


# ---- leitura: estado, rodadas, eventos, fila ----

def _coleta_resumo(c: Coleta) -> schemas.ColetaResumo:
    return schemas.ColetaResumo.model_validate(c)


def _evento_out(e: Evento) -> schemas.ColetaEventoOut:
    return schemas.ColetaEventoOut(id=e.id, tipo=e.tipo, cliente_id=e.cliente_id,
                                   coleta_id=e.coleta_id, tarefa_id=e.tarefa_id,
                                   detalhe=e.detalhe, ocorreu_em=e.ocorreu_em,
                                   recebido_em=e.recebido_em,
                                   notificado=e.notificacao_dedupe is not None)


def _hoje_resumo(db: Session, hoje) -> schemas.HojeResumo:
    estados = dict(db.execute(select(Tarefa.estado, func.count()).where(Tarefa.data_local == hoje)
                              .group_by(Tarefa.estado)).all())
    itens = dict(db.execute(select(ColetaItem.status, func.count())
                            .where(ColetaItem.data_local == hoje)
                            .group_by(ColetaItem.status)).all())
    return schemas.HojeResumo(
        tarefas=sum(estados.values()),
        pendentes=estados.get(FilaEstado.pendente, 0) + estados.get(FilaEstado.reservada, 0),
        recebidas=estados.get(FilaEstado.recebida, 0),
        falhadas=estados.get(FilaEstado.falhou, 0), expiradas=estados.get(FilaEstado.expirada, 0),
        gravados=itens.get(ItemStatus.gravado, 0), repetidos=itens.get(ItemStatus.repetido, 0),
        invalidos=itens.get(ItemStatus.invalido, 0) + itens.get(ItemStatus.erro, 0))


def ultimo_resultado_em(db: Session) -> datetime | None:
    return db.scalar(select(func.max(ColetaItem.recebido_em))
                     .where(ColetaItem.status == ItemStatus.gravado))


def estado(db: Session, mercado: str = mercados.PADRAO) -> schemas.EstadoColetaMercado:
    """Calculado na hora, nunca gravado (FR-036)."""
    cfg = comum.config_atual(db)
    agora = comum.agora()
    hoje = mercados.hoje(mercado, agora)
    janela = comum.janela(cfg, mercado, agora)
    clientes = db.scalars(select(ColetaCliente).order_by(ColetaCliente.created_at)).all()
    rodada = db.scalar(select(Coleta).where(Coleta.estado.in_(COLETA_ABERTAS))
                       .order_by(Coleta.iniciada_em.desc()))
    ultimo = ultimo_resultado_em(db)
    if not comum.servidor_habilitado():
        situacao = "desligada_no_servidor"
    elif cfg.risco_aceito_em is None:
        situacao = "aceite_pendente"
    elif not cfg.habilitada:
        situacao = "desligada"
    elif not [c for c in clientes if c.situacao == ColetaSituacao.ativo]:
        situacao = "sem_cliente"
    elif comum.pausada(cfg, agora):
        situacao = "pausada"
    elif rodada is not None and rodada.estado == ColetaEstado.pausada_captcha:
        situacao = "aguardando_continuar" if cfg.continuar_em is None else "pausada_captcha"
    elif rodada is not None and rodada.estado == ColetaEstado.pausada_login:
        situacao = "aguardando_continuar" if cfg.continuar_em is None else "pausada_login"
    elif rodada is not None:
        situacao = "coletando"
    elif ultimo is not None and agora - ultimo >= timedelta(hours=COLETA_PARADA_H):
        situacao = "parada"
    elif not janela.dentro:
        situacao = "fora_da_janela"
    else:
        situacao = "ociosa"
    eventos = db.scalars(select(Evento).order_by(Evento.recebido_em.desc()).limit(10)).all()
    return schemas.EstadoColetaMercado(
        servidor_habilitado=comum.servidor_habilitado(), habilitada=cfg.habilitada,
        risco_aceito=cfg.risco_aceito_em is not None, situacao=situacao,
        pausada_ate=cfg.pausada_ate, continuar_em=cfg.continuar_em, janela=janela,
        data_local=hoje, fuso=mercados.mercado(mercado).tz,
        orcamento=comum.orcamento(db, cfg, mercado, hoje), hoje=_hoje_resumo(db, hoje),
        clientes=[schemas.ClienteResumo(id=c.id, nome=c.nome, token_id=c.token_id,
                                        situacao=c.situacao, mercado=c.mercado,
                                        ultimo_contato_em=c.ultimo_contato_em,
                                        versao_coletor=c.versao_coletor,
                                        chrome_versao=c.chrome_versao) for c in clientes],
        rodada_atual=_coleta_resumo(rodada) if rodada else None, ultimo_resultado_em=ultimo,
        eventos_recentes=[_evento_out(e) for e in eventos])


def bloco_integracoes(db: Session) -> dict[str, Any]:
    """O bloco `coleta` de `GET /api/integracoes` (FR-036), sem valor de segredo."""
    e = estado(db)
    from sociman_api import datadir

    return {"servidorHabilitado": e.servidor_habilitado, "habilitada": e.habilitada,
            "riscoAceito": e.risco_aceito, "situacao": e.situacao, "clientes": len(e.clientes),
            "ultimoContatoEm": max((c.ultimo_contato_em for c in e.clientes
                                    if c.ultimo_contato_em), default=None),
            "paginasHoje": e.orcamento.paginas_hoje, "imagensHoje": e.orcamento.imagens_hoje,
            "rodadaAtual": e.rodada_atual.estado.value if e.rodada_atual else None,
            "hd": "ok" if datadir.status().available else "indisponivel"}


def listar_coletas(db: Session, estado_f: ColetaEstado | None, de, ate, limite: int,
                   cursor: str | None, cliente_id: uuid.UUID | None = None) -> schemas.ColetasList:
    stmt = select(Coleta).order_by(Coleta.iniciada_em.desc(), Coleta.id.desc()).limit(limite + 1)
    if cliente_id is not None:  # o coletor só vê as próprias rodadas
        stmt = stmt.where(Coleta.cliente_id == cliente_id)
    if estado_f is not None:
        stmt = stmt.where(Coleta.estado == estado_f)
    if de is not None:
        stmt = stmt.where(Coleta.iniciada_em >= de)
    if ate is not None:
        stmt = stmt.where(Coleta.iniciada_em < ate)
    if cursor:
        at, _ = decode_cursor(cursor)
        stmt = stmt.where(Coleta.iniciada_em < at)
    rows = db.scalars(stmt).all()
    proximo = None
    if len(rows) > limite:
        rows = rows[:limite]
        proximo = encode_cursor(rows[-1].iniciada_em, 0)
    return schemas.ColetasList(itens=[_coleta_resumo(c) for c in rows], proximo=proximo)


def detalhe_coleta(db: Session, coleta_id: uuid.UUID, itens_limite: int,
                   cliente_id: uuid.UUID | None = None) -> schemas.ColetaDetalhe:
    coleta = db.get(Coleta, coleta_id)
    if coleta is None or (cliente_id is not None and coleta.cliente_id != cliente_id):
        raise ApiError(404, "coleta_nao_encontrada", "Rodada não encontrada")
    itens = db.scalars(select(ColetaItem).where(ColetaItem.coleta_id == coleta_id)
                       .order_by(ColetaItem.id).limit(itens_limite)).all()
    eventos = db.scalars(select(Evento).where(Evento.coleta_id == coleta_id)
                         .order_by(Evento.id)).all()
    base = ingestao.coleta_out(coleta).model_dump()
    return schemas.ColetaDetalhe(
        **base,
        itens=[schemas.ColetaItemOut(
            id=i.id, tarefa_id=i.tarefa_id, tipo=i.tipo, fonte=i.fonte.value if i.fonte else None,
            status=i.status, erro_codigo=i.erro_codigo, erro_campo=i.erro_campo,
            duracao_ms=i.duracao_ms, recebido_em=i.recebido_em, coletado_em=i.coletado_em,
            data_local=i.data_local, turno=i.turno.value if i.turno else None,
            bruto_pendente=i.bruto_ref is None and i.status == ItemStatus.gravado,
            bruto_bytes=i.bruto_bytes) for i in itens],
        eventos=[_evento_out(e) for e in eventos])


def listar_eventos(db: Session, tipo: EventoTipo | None, de, ate, limite: int,
                   cursor: str | None) -> schemas.EventosList:
    stmt = select(Evento).order_by(Evento.recebido_em.desc(), Evento.id.desc()).limit(limite + 1)
    if tipo is not None:
        stmt = stmt.where(Evento.tipo == tipo)
    if de is not None:
        stmt = stmt.where(Evento.recebido_em >= de)
    if ate is not None:
        stmt = stmt.where(Evento.recebido_em < ate)
    if cursor:
        at, eid = decode_cursor(cursor)
        stmt = stmt.where((Evento.recebido_em < at) | ((Evento.recebido_em == at) & (Evento.id < eid)))
    rows = db.scalars(stmt).all()
    proximo = None
    if len(rows) > limite:
        rows = rows[:limite]
        proximo = encode_cursor(rows[-1].recebido_em, rows[-1].id)
    return schemas.EventosList(itens=[_evento_out(e) for e in rows], proximo=proximo)


def fila_hoje(db: Session, estado_f: FilaEstado | None, tipo: str | None,
              perfil_id: uuid.UUID | None, mercado: str = mercados.PADRAO) -> schemas.FilaHojeOut:
    hoje = mercados.hoje(mercado)
    stmt = select(Tarefa).where(Tarefa.data_local == hoje).order_by(Tarefa.nivel, Tarefa.prioridade,
                                                                   Tarefa.criada_em)
    if estado_f is not None:
        stmt = stmt.where(Tarefa.estado == estado_f)
    if tipo is not None:
        stmt = stmt.where(Tarefa.tipo == tipo)
    if perfil_id is not None:
        stmt = stmt.where(Tarefa.perfil_id == perfil_id)
    rows = db.scalars(stmt.limit(2000)).all()
    por_nivel: dict[str, int] = {}
    por_estado: dict[str, int] = {}
    for t in rows:
        por_nivel[str(t.nivel)] = por_nivel.get(str(t.nivel), 0) + 1
        por_estado[t.estado.value] = por_estado.get(t.estado.value, 0) + 1
    return schemas.FilaHojeOut(
        itens=[schemas.TarefaFila(
            tarefa_id=t.id, tipo=t.tipo, rede=t.rede, mercado=t.mercado, fonte=t.fonte,
            chave=t.chave, url=t.url, nivel=t.nivel, prioridade=t.prioridade,
            turno=t.turno.value if t.turno else None, reservada_ate=t.reservada_ate,
            extra=t.extra, estado=t.estado, perfil_id=t.perfil_id, produto_id=t.produto_id,
            tentativas=t.tentativas, resultado_status=t.resultado_status,
            erro_codigo=t.erro_codigo, criada_em=t.criada_em, recebida_em=t.recebida_em)
            for t in rows],
        por_nivel=por_nivel, por_estado=por_estado)


def devolver_leases_vencidos(db: Session) -> int:
    """Reservas vencidas voltam a `pendente` (a trilha chama; a fila também pode)."""
    r = db.execute(update(Tarefa).where(Tarefa.estado == FilaEstado.reservada,
                                        Tarefa.reservada_ate < comum.agora())
                   .values(estado=FilaEstado.pendente, reservada_ate=None, cliente_id=None,
                           tentativas=Tarefa.tentativas + 1))
    return r.rowcount or 0
