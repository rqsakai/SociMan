"""Anotações e propostas (R12, FR-018 a FR-022).

- criar: humano ou cliente MCP (o escopo `propostas` é conferido pelo portão); o alvo precisa
  existir (404) e não estar arquivado (409 `alvo_arquivado`);
- editar e arquivar: só o autor, só com a anotação `aberta` (o dono também pode arquivar);
- descartar: só humano (a rota usa `RequireHuman`);
- aplicar: no save do destino (`postagem.service.update_textos` chama `aplicar`), só humano;
- reverter: só o dono humano (`RequireHumanOwner`).

Nada é apagado; toda mudança vai para o histórico (`entity_type = "anotacao"`).
"""

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.anotacoes import schemas
from sociman_api.anotacoes.models import (
    Anotacao,
    AnotacaoAlvo,
    AnotacaoSituacao,
    AnotacaoTipo,
)
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User, UserRole
from sociman_api.canais.models import CanalFonte, CanalPerfil, VideoFonte
from sociman_api.cenas.models import Cena, CenaStatus
from sociman_api.cenas.schemas import CamposCena
from sociman_api.conteudos.models import Conteudo
from sociman_api.cortes.models import Corte
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.perfis.schemas import Autor, UserRef
from sociman_api.postagem.models import Postagem
from sociman_api.produtos.models import Produto

ENTITY = "anotacao"
LABEL = "Esta anotação"
NAO_ENCONTRADA = "Anotação não encontrada"
FECHADA = "Esta anotação não está mais aberta"
NAO_AUTOR = "Só o autor pode alterar esta anotação"

_MODELOS: dict[AnotacaoAlvo, Any] = {
    AnotacaoAlvo.perfil: Perfil, AnotacaoAlvo.conta: Conta, AnotacaoAlvo.canal: CanalFonte,
    AnotacaoAlvo.video_fonte: VideoFonte, AnotacaoAlvo.corte: Corte,
    AnotacaoAlvo.conteudo: Conteudo, AnotacaoAlvo.destino: Postagem,
    AnotacaoAlvo.cena: Cena,  # spec 010
    AnotacaoAlvo.produto: Produto,  # spec 012
}
_NOMES = {AnotacaoAlvo.perfil: "Perfil", AnotacaoAlvo.conta: "Conta",
          AnotacaoAlvo.canal: "Canal-fonte", AnotacaoAlvo.video_fonte: "Vídeo-fonte",
          AnotacaoAlvo.corte: "Corte", AnotacaoAlvo.conteudo: "Conteúdo",
          AnotacaoAlvo.destino: "Destino", AnotacaoAlvo.cena: "Cena",
          AnotacaoAlvo.produto: "Produto"}


@dataclass(frozen=True)
class _Alvo:
    perfil_id: uuid.UUID | None
    titulo: str
    link: str
    arquivado: bool


def _primeiro_perfil(db: Session, canal_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(CanalPerfil.perfil_id).where(CanalPerfil.canal_id == canal_id)
                     .order_by(CanalPerfil.created_at, CanalPerfil.perfil_id).limit(1))


def _titulo(obj: Any, padrao: str) -> str:
    for attr in ("titulo", "title", "name", "nome", "handle", "hook_text", "source_title"):
        valor = getattr(obj, attr, None)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()[:120]
    return padrao


def _alvo(db: Session, tipo: AnotacaoAlvo, alvo_id: uuid.UUID) -> _Alvo | None:
    obj = db.get(_MODELOS[tipo], alvo_id)
    if obj is None:
        return None
    arquivado = bool(getattr(obj, "archived", False))
    titulo = _titulo(obj, _NOMES[tipo])
    match tipo:
        case AnotacaoAlvo.perfil:
            return _Alvo(obj.id, titulo, f"/app/perfis/{obj.id}", arquivado)
        case AnotacaoAlvo.conta:
            return _Alvo(obj.perfil_id, titulo, f"/app/contas/{obj.id}/historico", arquivado)
        case AnotacaoAlvo.canal:
            return _Alvo(_primeiro_perfil(db, obj.id), titulo, f"/app/fontes/{obj.id}", arquivado)
        case AnotacaoAlvo.video_fonte:
            canal = db.get(CanalFonte, obj.canal_id)
            return _Alvo(_primeiro_perfil(db, obj.canal_id), titulo,
                         f"/app/fontes/{obj.canal_id}?video={obj.id}",
                         bool(canal is not None and canal.archived))
        case AnotacaoAlvo.corte:
            return _Alvo(obj.perfil_id, titulo, f"/app/cortes/{obj.id}", arquivado)
        case AnotacaoAlvo.conteudo:
            return _Alvo(obj.perfil_id, titulo, f"/app/conteudos/{obj.id}", arquivado)
        case AnotacaoAlvo.cena:  # spec 010
            return _Alvo(obj.perfil_id, titulo, f"/app/cenas/{obj.id}", arquivado)
        case AnotacaoAlvo.produto:  # spec 012
            return _Alvo(obj.perfil_id, obj.nome_comercial or titulo,
                         f"/app/produtos/{obj.id}", arquivado)
        case AnotacaoAlvo.destino:
            conteudo = db.get(Conteudo, obj.conteudo_id)
            if titulo == _NOMES[tipo] and conteudo is not None:
                titulo = _titulo(conteudo, titulo)
            arquivado = arquivado or bool(conteudo is not None and conteudo.archived)
            return _Alvo(conteudo.perfil_id if conteudo is not None else None, titulo,
                         f"/app/conteudos/{obj.conteudo_id}?destino={obj.id}", arquivado)
    return None  # pragma: no cover


# ---- saída ----

def _autores(db: Session, anotacoes: list[Anotacao]) -> tuple[dict[uuid.UUID, str],
                                                              dict[uuid.UUID, str]]:
    from sociman_api.mcp.models import McpCliente  # só o nome do cliente (autor)

    user_ids = {a.autor_user_id for a in anotacoes} | {a.resolvida_por for a in anotacoes}
    user_ids.discard(None)
    mcp_ids = {a.autor_mcp_cliente_id for a in anotacoes if a.autor_mcp_cliente_id}
    users = dict(db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
                 ) if user_ids else {}
    clientes = dict(db.execute(select(McpCliente.id, McpCliente.nome).where(
        McpCliente.id.in_(mcp_ids))).all()) if mcp_ids else {}
    return users, clientes


def anotacoes_out(db: Session, anotacoes: list[Anotacao]) -> list[schemas.Anotacao]:
    users, clientes = _autores(db, anotacoes)
    out = []
    for a in anotacoes:
        alvo = _alvo(db, a.alvo_tipo, a.alvo_id) or _Alvo(a.perfil_id, _NOMES[a.alvo_tipo],
                                                          "/app", True)
        if a.autor_mcp_cliente_id is not None:
            autor = Autor(tipo="mcp_client", id=a.autor_mcp_cliente_id,
                          nome=clientes.get(a.autor_mcp_cliente_id, "Agente"))
        else:
            autor = Autor(tipo="usuario", id=a.autor_user_id,
                          nome=users.get(a.autor_user_id, "Usuário"))
        out.append(schemas.Anotacao(
            id=a.id,
            alvo=schemas.AlvoRef(tipo=a.alvo_tipo, id=a.alvo_id, titulo=alvo.titulo,
                                 link=alvo.link, arquivado=alvo.arquivado),
            perfil_id=a.perfil_id, tipo=a.tipo, texto=a.texto,
            campos=_campos_out(a),
            situacao=a.situacao, autor=autor,
            resolvida_por=(UserRef(id=a.resolvida_por, name=users.get(a.resolvida_por, ""))
                           if a.resolvida_por else None),
            resolvida_em=a.resolvida_em, motivo_descarte=a.motivo_descarte,
            created_at=a.created_at, version=a.version))
    return out


def _campos_out(a: Anotacao) -> schemas.CamposProposta | CamposCena | None:
    if a.campos is None:
        return None
    if a.tipo == AnotacaoTipo.proposta_cena:
        return CamposCena.model_validate(a.campos)
    return schemas.CamposProposta(**a.campos)


def anotacao_out(db: Session, anotacao: Anotacao) -> schemas.Anotacao:
    return anotacoes_out(db, [anotacao])[0]


# ---- leitura ----

def get_or_404(db: Session, anotacao_id: uuid.UUID, lock: bool = False) -> Anotacao:
    anotacao = db.get(Anotacao, anotacao_id, with_for_update=lock)
    if anotacao is None:
        raise ApiError(404, "not_found", NAO_ENCONTRADA)
    return anotacao


def _encode(created_at: datetime, anotacao_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{anotacao_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        at, _, aid = raw.partition("|")
        created_at = datetime.fromisoformat(at)
        if created_at.tzinfo is None:
            raise ValueError("cursor sem fuso")
        return created_at, uuid.UUID(aid)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ApiError(400, "validation_error", "cursor: inválido") from exc


# Busca sem acento e sem caixa (spec 024, R6): mesma tabela do `translate` das cenas (010), no
# banco e no termo, para os dois lados serem dobrados igual.
_ACENTOS = ("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
_DOBRA = str.maketrans(*_ACENTOS)


def _sem_acento(col):
    return func.translate(func.lower(col), *_ACENTOS)


def _termo(q: str) -> str:
    termo = q.strip().lower().translate(_DOBRA)
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar(db: Session, alvo_tipo: AnotacaoAlvo | None, alvo_id: uuid.UUID | None,
           perfil_id: uuid.UUID | None, situacao: AnotacaoSituacao | None,
           tipo: AnotacaoTipo | None, autor_cliente_id: uuid.UUID | None, cursor: str | None,
           limit: int, q: str | None = None) -> schemas.AnotacoesPage:
    stmt = select(Anotacao)
    if alvo_tipo is not None:
        stmt = stmt.where(Anotacao.alvo_tipo == alvo_tipo)
    if alvo_id is not None:
        stmt = stmt.where(Anotacao.alvo_id == alvo_id)
    if perfil_id is not None:
        stmt = stmt.where(Anotacao.perfil_id == perfil_id)
    if situacao is not None:
        stmt = stmt.where(Anotacao.situacao == situacao)
    if tipo is not None:
        stmt = stmt.where(Anotacao.tipo == tipo)
    if autor_cliente_id is not None:
        stmt = stmt.where(Anotacao.autor_mcp_cliente_id == autor_cliente_id)
    if q and q.strip():
        stmt = stmt.where(_sem_acento(Anotacao.texto).like(f"%{_termo(q)}%", escape="\\"))
    if cursor is not None:
        stmt = stmt.where(tuple_(Anotacao.created_at, Anotacao.id) < _decode(cursor))
    rows = list(db.scalars(stmt.order_by(Anotacao.created_at.desc(), Anotacao.id.desc())
                           .limit(limit + 1)))
    page = rows[:limit]
    next_cursor = _encode(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    return schemas.AnotacoesPage(anotacoes=anotacoes_out(db, page), next_cursor=next_cursor)


def resumo(db: Session, perfil_id: uuid.UUID | None) -> schemas.AnotacoesResumo:
    stmt = select(func.count()).select_from(Anotacao).where(
        Anotacao.situacao == AnotacaoSituacao.aberta)
    if perfil_id is not None:
        stmt = stmt.where(Anotacao.perfil_id == perfil_id)
    return schemas.AnotacoesResumo(abertas=db.scalar(stmt) or 0)


def versoes(db: Session, anotacao_id: uuid.UUID):
    from sociman_api.perfis.service_perfis import versions_out

    get_or_404(db, anotacao_id)
    return versions_out(db, ENTITY, anotacao_id)


# ---- mutações ----

def _campos(tipo: AnotacaoTipo, campos: Any | None) -> dict[str, Any] | None:
    if tipo == AnotacaoTipo.observacao:
        if campos is not None:
            raise ApiError(400, "validation_error", "campos: só numa proposta de texto")
        return None
    if tipo == AnotacaoTipo.proposta_cena:  # spec 010: chaves em camelCase
        dados = campos.model_dump(exclude_none=True) if campos is not None else {}
        try:
            cena = CamposCena.model_validate(dados)
        except ValueError:
            raise ApiError(400, "validation_error",
                           "campos: use os campos da cena (nome, ação, fala…)") from None
        out = cena.model_dump(exclude_none=True, by_alias=True, mode="json")
        if not out:
            raise ApiError(400, "campos_vazios", "A proposta de cena precisa de algum campo")
        return out
    if not isinstance(campos, schemas.CamposProposta) and campos is not None:
        raise ApiError(400, "validation_error",
                       "campos: título, descrição ou hashtags da proposta de texto")
    if campos is None or not campos.model_dump(exclude_none=True):
        raise ApiError(400, "campos_vazios",
                       "A proposta de texto precisa de título, descrição ou hashtags")
    return campos.model_dump(exclude_none=True)


def _e_autor(actor: Actor, anotacao: Anotacao) -> bool:
    if anotacao.autor_kind == "mcp_client":
        return actor.kind == "mcp_client" and actor.mcp_client_id == anotacao.autor_mcp_cliente_id
    return actor.kind == "user" and actor.user_id == anotacao.autor_user_id


def _e_dono_humano(actor: Actor) -> bool:
    return actor.kind == "user" and actor.user is not None and actor.user.role == UserRole.dono


def _aberta(anotacao: Anotacao) -> None:
    if anotacao.situacao != AnotacaoSituacao.aberta:
        raise ApiError(409, "anotacao_fechada", FECHADA)


def _record(db: Session, actor: Actor, anotacao: Anotacao, action: str,
            before: dict[str, Any] | None, details: dict[str, Any] | None = None) -> None:
    anotacao.updated_by = actor.user_id
    history.record(db, actor, ENTITY, anotacao, action, before, history.snapshot(anotacao),
                   details)


def criar(db: Session, actor: Actor, body: schemas.CreateAnotacaoIn) -> Anotacao:
    if body.tipo == AnotacaoTipo.proposta_texto and body.alvo_tipo != AnotacaoAlvo.destino:
        raise ApiError(400, "proposta_so_em_destino",
                       "A proposta de texto só vale para um destino; use uma observação")
    if body.tipo == AnotacaoTipo.proposta_cena \
            and body.alvo_tipo not in (AnotacaoAlvo.perfil, AnotacaoAlvo.cena):
        raise ApiError(422, "proposta_alvo_invalido",
                       "A proposta de cena vale num perfil (cena nova) ou numa cena")
    campos = _campos(body.tipo, body.campos)
    alvo = _alvo(db, body.alvo_tipo, body.alvo_id)
    if alvo is None:
        raise ApiError(404, "not_found", f"{_NOMES[body.alvo_tipo]} não encontrado")
    if alvo.arquivado:
        raise ApiError(409, "alvo_arquivado", "Este item está arquivado")
    if body.tipo == AnotacaoTipo.proposta_cena:
        _validar_cena(db, body.alvo_tipo, body.alvo_id, alvo, campos or {})
    mcp = actor.kind == "mcp_client"
    if not mcp and actor.kind != "user":
        raise ApiError(403, "forbidden", "Sem permissão")
    anotacao = Anotacao(
        id=uuid.uuid4(), alvo_tipo=body.alvo_tipo, alvo_id=body.alvo_id,
        perfil_id=alvo.perfil_id, tipo=body.tipo, texto=body.texto, campos=campos,
        situacao=AnotacaoSituacao.aberta, autor_kind="mcp_client" if mcp else "user",
        autor_mcp_cliente_id=actor.mcp_client_id if mcp else None,
        autor_user_id=None if mcp else actor.user_id,
        created_by=actor.user_id, updated_by=actor.user_id)
    db.add(anotacao)
    db.flush()
    history.record(db, actor, ENTITY, anotacao, "created", None, history.snapshot(anotacao))
    db.flush()
    return anotacao


def _validar_cena(db: Session, alvo_tipo: AnotacaoAlvo, alvo_id: uuid.UUID, alvo: _Alvo,
                  campos: dict[str, Any]) -> None:
    """Spec 010: a cena alvo não pode estar `usada`; os assets propostos são do perfil e não
    estão arquivados (422 `proposta_invalida`)."""
    from sociman_api.cenas import service as cenas  # import tardio (ciclo)
    from sociman_api.cenas.models import CAMPOS_EDITAVEIS

    base: dict[str, Any] = {}
    if alvo_tipo == AnotacaoAlvo.cena:
        cena = db.get(Cena, alvo_id)
        if cena.status == CenaStatus.usada:
            raise ApiError(409, "cena_usada", cenas.CENA_USADA)
        base = {f: getattr(cena, f) for f in CAMPOS_EDITAVEIS}
    proposta = CamposCena.model_validate(campos).model_dump(exclude_unset=True)
    novos = {k for k in proposta if k.endswith("_id")}
    if "avatar_id" in proposta and "avatar_arquivo_id" not in proposta:
        base["avatar_arquivo_id"] = None
    if "cenario_id" in proposta and "cenario_arquivo_id" not in proposta:
        base["cenario_arquivo_id"] = None

    def erro(campo: str, mensagem: str) -> ApiError:
        return ApiError(422, "proposta_invalida", f"{cenas.camel(campo)}: {mensagem}",
                        details={"field": cenas.camel(campo)})

    cenas.validar_refs(db, alvo.perfil_id, base | proposta, novos=novos, erro=erro)


def editar(db: Session, actor: Actor, anotacao_id: uuid.UUID, body: schemas.UpdateAnotacaoIn
           ) -> Anotacao:
    anotacao = get_or_404(db, anotacao_id, lock=True)
    history.check_version(anotacao, body.version, LABEL)
    if not _e_autor(actor, anotacao):
        raise ApiError(403, "nao_e_o_autor", NAO_AUTOR)
    _aberta(anotacao)
    before = history.snapshot(anotacao)
    if body.texto is not None:
        anotacao.texto = body.texto
    if "campos" in body.model_fields_set:
        anotacao.campos = _campos(anotacao.tipo, body.campos)
        if anotacao.tipo == AnotacaoTipo.proposta_cena:
            alvo = _alvo(db, anotacao.alvo_tipo, anotacao.alvo_id)
            if alvo is not None:
                _validar_cena(db, anotacao.alvo_tipo, anotacao.alvo_id, alvo,
                              anotacao.campos or {})
    if history.diff(before, history.snapshot(anotacao)):
        _record(db, actor, anotacao, "updated", before, {"acao": "editada"})
        db.flush()
    return anotacao


def arquivar(db: Session, actor: Actor, anotacao_id: uuid.UUID, version: int) -> Anotacao:
    anotacao = get_or_404(db, anotacao_id, lock=True)
    history.check_version(anotacao, version, LABEL)
    if not (_e_autor(actor, anotacao) or _e_dono_humano(actor)):
        raise ApiError(403, "nao_e_o_autor", NAO_AUTOR)
    _aberta(anotacao)
    before = history.snapshot(anotacao)
    anotacao.situacao = AnotacaoSituacao.arquivada
    _record(db, actor, anotacao, "archived", before, {"acao": "arquivada"})
    db.flush()
    return anotacao


def descartar(db: Session, actor: Actor, anotacao_id: uuid.UUID, version: int,
              motivo: str | None) -> Anotacao:
    """Ato humano (a rota é **Hu**)."""
    anotacao = get_or_404(db, anotacao_id, lock=True)
    history.check_version(anotacao, version, LABEL)
    _aberta(anotacao)
    before = history.snapshot(anotacao)
    anotacao.situacao = AnotacaoSituacao.descartada
    anotacao.motivo_descarte = (motivo or "").strip() or None
    anotacao.resolvida_por = actor.user_id
    anotacao.resolvida_em = datetime.now(UTC)
    _record(db, actor, anotacao, "updated", before, {"acao": "descartada"})
    db.flush()
    return anotacao


def aplicar(db: Session, actor: Actor, proposta_id: uuid.UUID, destino_id: uuid.UUID
            ) -> Anotacao:
    """Chamado pelo save do destino com `propostaId` (só humano; o chamador confere o ator).

    A proposta precisa ser `proposta_texto` do **mesmo** destino e estar `aberta`.
    """
    anotacao = db.get(Anotacao, proposta_id, with_for_update=True)
    if anotacao is None or anotacao.tipo != AnotacaoTipo.proposta_texto \
            or anotacao.alvo_tipo != AnotacaoAlvo.destino or anotacao.alvo_id != destino_id:
        raise ApiError(409, "proposta_invalida", "Essa proposta não é deste destino")
    _aberta(anotacao)
    before = history.snapshot(anotacao)
    anotacao.situacao = AnotacaoSituacao.aplicada
    anotacao.resolvida_por = actor.user_id
    anotacao.resolvida_em = datetime.now(UTC)
    _record(db, actor, anotacao, "updated", before,
            {"acao": "aplicada", "destinoId": str(destino_id)})
    return anotacao


def aplicar_cena(db: Session, actor: Actor, proposta_id: uuid.UUID, *, perfil_id: uuid.UUID,
                 cena_id: uuid.UUID | None, aplicada_em: uuid.UUID) -> Anotacao:
    """Spec 010: chamado pelo save humano da cena com `propostaId` (cena nova: `cena_id` None e
    a proposta precisa estar no perfil; alteração: a proposta precisa ser desta cena)."""
    anotacao = db.get(Anotacao, proposta_id, with_for_update=True)
    if cena_id is None:
        casa = anotacao is not None and anotacao.alvo_tipo == AnotacaoAlvo.perfil \
            and anotacao.alvo_id == perfil_id
    else:
        casa = anotacao is not None and anotacao.alvo_tipo == AnotacaoAlvo.cena \
            and anotacao.alvo_id == cena_id
    if not casa or anotacao.tipo != AnotacaoTipo.proposta_cena:
        raise ApiError(409, "proposta_invalida", "Essa proposta não é desta cena")
    _aberta(anotacao)
    before = history.snapshot(anotacao)
    anotacao.situacao = AnotacaoSituacao.aplicada
    anotacao.resolvida_por = actor.user_id
    anotacao.resolvida_em = datetime.now(UTC)
    _record(db, actor, anotacao, "updated", before,
            {"acao": "aplicada", "cenaId": str(aplicada_em)})
    return anotacao


def reverter(db: Session, actor: Actor, anotacao_id: uuid.UUID, version: int, to_version: int
             ) -> Anotacao:
    """Só o dono humano (a rota é **H**): volta texto, campos, situação e motivo."""
    anotacao = get_or_404(db, anotacao_id, lock=True)
    history.check_version(anotacao, version, LABEL)
    if to_version == anotacao.version:
        raise ApiError(400, "validation_error", "Já é a versão atual")
    state = history.version_state(db, ENTITY, anotacao.id, to_version)
    if state is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    before = history.snapshot(anotacao)
    anotacao.texto = state["texto"]
    anotacao.campos = state["campos"]
    anotacao.situacao = AnotacaoSituacao(state["situacao"])
    anotacao.motivo_descarte = state["motivo_descarte"]
    if anotacao.situacao == AnotacaoSituacao.aberta:
        anotacao.resolvida_por = None
        anotacao.resolvida_em = None
    if history.snapshot(anotacao) == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    _record(db, actor, anotacao, "reverted", before, {"from_version": to_version})
    db.flush()
    return anotacao
