"""Conteúdos (spec 014, US1; research R1 e R10).

- `criar_para_corte`: todo corte nasce com o seu conteúdo (mesmo `id`), no mesmo flush, nos dois
  únicos pontos que criam `Corte` (`cortes/service.py::create_corte` e
  `envios/importacao.py::importar_clipe`). A migration 0009 criou os dos cortes antigos.
- Lista com filtros no servidor, atalhos, cursor opaco (base64 de `[chave, id]`) e o total do
  filtro; os destinos de cada linha vêm numa segunda consulta (sem N+1). Os campos derivados e o
  estado efetivo vêm todos de `consulta.py` (a mesma expressão no filtro e na saída).
- `destinos_out`/`resumos_por_conteudo` montam o `Destino`/`DestinoResumo` para todos (conteúdo,
  destinos, corte e calendário).
- Arquivar e restaurar: na origem corte, pelo service do corte (o arquivamento é do corte).
  Reverter volta o título e, no vídeo próprio, o arquivamento. **Exceção herdada da 006
  (princípio VII):** o conteúdo de origem corte não reverte o arquivamento (o corte não tem
  `revert`).
"""

import base64
import binascii
import json
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    func,
    literal,
    or_,
    select,
    tuple_,
)
from sqlalchemy.orm import Session

from sociman_api import history, imaging
from sociman_api.auth.deps import Actor
from sociman_api.canais.schemas import PerfilRef
from sociman_api.config import get_settings
from sociman_api.conteudos import consulta, proposta
from sociman_api.conteudos import schemas as s
from sociman_api.conteudos.consulta import EstadoEfetivo
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.cortes.models import Corte
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Conta, Perfil, Platform
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import (
    apply_archived,
    target_state,
    user_refs,
    versions_out,
)
from sociman_api.postagem import envio
from sociman_api.postagem import schemas as ps
from sociman_api.postagem.models import DestinoEstado, Postagem

ENTITY = "conteudo"
LABEL = "Este conteúdo"
NOT_FOUND = "Conteúdo não encontrado"
TITULO_MAX = 100
LIMIT_PADRAO = 50
# Sem agendamento na ordem `agenda`: vai para o fim (a chave do cursor nunca é nula).
SEM_AGENDA = datetime(9999, 12, 31, tzinfo=UTC)
# Estados que tiram o conteúdo de "prontos sem agendamento" (já tem data ou já saiu).
MARCADOS = (DestinoEstado.agendado, DestinoEstado.postado, DestinoEstado.rascunho_criado,
            DestinoEstado.publicado, DestinoEstado.falhou, DestinoEstado.enviando)


def app_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


def _invalid(message: str) -> ApiError:
    return ApiError(400, "validation_error", message)


def titulo_do_corte(corte: Corte) -> str:
    """A regra da migration: título do OpenShorts, gancho ou nome do arquivo (até 100)."""
    return (corte.openshorts_title or corte.hook_text or corte.original_filename)[:TITULO_MAX]


def criar_para_corte(db: Session, actor: history.ActorLike, corte: Corte) -> Conteudo:
    """O conteúdo do corte (origem `corte`, `id = corte_id = corte.id`), com a versão
    `created`. Quem chama faz o flush junto com o do corte."""
    conteudo = Conteudo(
        id=corte.id, perfil_id=corte.perfil_id, origem=ConteudoOrigem.corte, corte_id=corte.id,
        titulo=titulo_do_corte(corte), created_by=corte.created_by, updated_by=corte.created_by,
    )
    db.add(conteudo)
    history.record(db, actor, ENTITY, conteudo, "created", None, history.snapshot(conteudo))
    return conteudo


def get_conteudo_or_404(db: Session, conteudo_id: uuid.UUID, lock: bool = False) -> Conteudo:
    conteudo = db.get(Conteudo, conteudo_id, with_for_update=lock)
    if conteudo is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    return conteudo


# ---- destinos (saída) ----

def conta_ref(conta: Conta, conexao: str = "nao_conectada") -> ps.ContaRef:
    return ps.ContaRef(id=conta.id, platform=conta.platform, platform_name=conta.platform_name,
                       handle=conta.handle, status=conta.status, conexao=conexao)


def _local(dt: datetime | None, tz: ZoneInfo) -> datetime | None:
    return dt.astimezone(tz) if dt is not None else None


def _destinos_rows(db: Session, *where: ColumnElement[bool], agora: datetime | None = None):
    return db.execute(
        consulta.destinos_do_conteudo()
        .add_columns(Conta, consulta.estado_efetivo(agora).label("ee"),
                     consulta.motivo_atencao_efetivo(agora).label("motivo"),
                     consulta.video_mudou().label("vm"))
        .where(*where)
        .order_by(Postagem.created_at, Postagem.id)
    ).all()


def destinos_out(db: Session, destino_ids: Iterable[uuid.UUID],
                 agora: datetime | None = None) -> list[ps.Destino]:
    """Os destinos pedidos, completos, na ordem de criação."""
    ids = list(set(destino_ids))
    if not ids:
        return []
    return _destinos(db, _destinos_rows(db, Postagem.id.in_(ids), agora=agora))


def destino_out(db: Session, destino: Postagem) -> ps.Destino:
    db.flush()
    db.refresh(destino)
    return destinos_out(db, [destino.id])[0]


def _destinos(db: Session, rows: Sequence) -> list[ps.Destino]:
    postagens = [r[0] for r in rows]
    users = user_refs(db, [u for p in postagens for u in
                           (p.updated_by, p.aprovado_por, p.pedido_por, p.recusado_por)])
    conexoes = envio.conexoes_por_conta(db, {p.conta_id for p in postagens})
    extras = envio.campos_envio(db, postagens)
    tz = app_tz()
    out = []
    for p, conta, ee, motivo, vm in rows:
        aprovacao = ps.Aprovacao(por=users[p.aprovado_por], em=p.aprovado_em.astimezone(tz)) \
            if p.aprovado_em is not None and p.aprovado_por in users else None
        pedido = ps.Pedido(por=users[p.pedido_por], em=p.pedido_em.astimezone(tz),
                           nota=p.pedido_nota) \
            if p.pedido_em is not None and p.pedido_por in users else None
        recusa = ps.Recusa(por=users[p.recusado_por], em=p.recusado_em.astimezone(tz),
                           motivo=p.recusa_motivo or "") \
            if p.recusado_em is not None and p.recusado_por in users else None
        out.append(ps.Destino(
            id=p.id, conteudo_id=p.conteudo_id,
            conta=conta_ref(conta, envio.estado_conexao(conexoes.get(conta.id))), titulo=p.titulo,
            descricao=p.descricao, hashtags=list(p.hashtags), estado=p.estado,
            estado_efetivo=ee, motivo_atencao=motivo, modo=p.modo,
            antecedencia_min=p.antecedencia_min, planned_at=_local(p.planned_at, tz),
            lembrado=p.lembrado_em is not None, posted_at=_local(p.posted_at, tz),
            posted_url=p.posted_url, falha_motivo=p.falha_motivo, aprovacao=aprovacao,
            pedido=pedido, recusa=recusa, video_mudou=bool(vm), archived=p.archived,
            version=p.version, created_at=p.created_at, updated_at=p.updated_at,
            updated_by=users.get(p.updated_by) if p.updated_by else None,
            **extras[p.id],
        ))
    return out


def resumos_por_conteudo(db: Session, conteudo_ids: Iterable[uuid.UUID],
                         agora: datetime | None = None
                         ) -> dict[uuid.UUID, list[ps.DestinoResumo]]:
    """Os destinos ativos (não arquivados) de cada conteúdo, numa consulta só."""
    ids = list(set(conteudo_ids))
    out: dict[uuid.UUID, list[ps.DestinoResumo]] = {i: [] for i in ids}
    if not ids:
        return out
    tz = app_tz()
    rows = _destinos_rows(db, Postagem.conteudo_id.in_(ids), Postagem.archived_at.is_(None),
                          agora=agora)
    conexoes = envio.conexoes_por_conta(db, {r[0].conta_id for r in rows})
    fases = envio.ultimas_fases(db, [r[0].id for r in rows])
    for p, conta, ee, motivo, vm in rows:
        out[p.conteudo_id].append(ps.DestinoResumo(
            id=p.id, conta=conta_ref(conta, envio.estado_conexao(conexoes.get(conta.id))),
            estado=p.estado, estado_efetivo=ee, motivo_atencao=motivo, modo=p.modo,
            planned_at=_local(p.planned_at, tz), sem_textos=p.titulo == "",
            video_mudou=bool(vm), version=p.version, ultima_fase=fases.get(p.id),
        ))
    return out


# ---- conteúdos (saída) ----

def _linhas() -> Select:
    """Conteúdo + corte (se houver) + perfil + os derivados de `consulta.py`."""
    return consulta.join_corte(
        select(Conteudo, Corte, Perfil, consulta.situacao().label("situacao"),
               consulta.arquivado().label("arquivado"),
               consulta.poster_key().label("poster_key"),
               consulta.duration_ms().label("duration_ms"))
        .join(Perfil, Perfil.id == Conteudo.perfil_id)
    )


def _item_campos(row, destinos: list, sem_conta: bool) -> dict:
    conteudo, corte, perfil = row.Conteudo, row.Corte, row.Perfil
    return {
        "id": conteudo.id,
        "perfil": PerfilRef(id=perfil.id, name=perfil.name, slug=perfil.slug),
        "origem": conteudo.origem, "titulo": conteudo.titulo, "situacao": row.situacao,
        "poster_url": imaging.poster_url(row.poster_key) if row.poster_key else None,
        "duration_ms": row.duration_ms, "created_at": conteudo.created_at,
        "archived": bool(row.arquivado), "corte_id": conteudo.corte_id,
        "envio_id": corte.envio_id if corte is not None else None, "destinos": destinos,
        "sem_conta": sem_conta,
    }


def _itens(db: Session, rows: Sequence, agora: datetime) -> list[s.ConteudoItem]:
    resumos = resumos_por_conteudo(db, [r.Conteudo.id for r in rows], agora)
    return [s.ConteudoItem(**_item_campos(r, resumos[r.Conteudo.id],
                                          not resumos[r.Conteudo.id]))
            for r in rows]


def conteudo_out(db: Session, conteudo_id: uuid.UUID) -> s.Conteudo:
    db.flush()
    row = db.execute(_linhas().where(Conteudo.id == conteudo_id)).one_or_none()
    if row is None:
        raise ApiError(404, "not_found", NOT_FOUND)
    db.refresh(row.Conteudo)
    conteudo, corte = row.Conteudo, row.Corte
    destinos = _destinos(db, _destinos_rows(db, Postagem.conteudo_id == conteudo.id))
    width = corte.width if corte is not None else conteudo.width
    height = corte.height if corte is not None else conteudo.height
    users = user_refs(db, [conteudo.updated_by])
    prop = proposta.do_corte(corte)
    from sociman_api.cenas.usos import conteudo_tem_cenas  # spec 010 (import tardio: ciclo)

    return s.Conteudo(
        **_item_campos(row, destinos, not any(not d.archived for d in destinos)),
        width=width, height=height,
        nao_vertical=width is not None and height is not None and width >= height,
        video_bytes=corte.result_bytes if corte is not None else conteudo.video_bytes,
        original_filename=corte.original_filename if corte is not None
        else conteudo.original_filename,
        version=conteudo.version, updated_at=conteudo.updated_at,
        updated_by=users.get(conteudo.updated_by) if conteudo.updated_by else None,
        proposta_openshorts=s.PropostaOpenshorts(titulo=prop.titulo, descricao=prop.descricao,
                                                 gancho=prop.gancho, score=prop.score)
        if prop is not None else None,
        cenas=conteudo_tem_cenas(db, conteudo),
    )


# ---- lista, atalhos e resumo ----

@dataclass
class Filtros:
    perfil_ids: list[uuid.UUID] = field(default_factory=list)
    conta_id: uuid.UUID | None = None
    plataforma: Platform | None = None
    estados: list[s.EstadoFiltro] = field(default_factory=list)
    origem: ConteudoOrigem | None = None
    agendado_de: date | None = None
    agendado_ate: date | None = None
    criado_de: date | None = None
    criado_ate: date | None = None
    q: str | None = None
    atalho: s.Atalho | None = None
    ordem: s.OrdemConteudos = s.OrdemConteudos.recentes
    archived: bool = False


def _dia(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time.min, tzinfo=tz)


def _periodo(de: date | None, ate: date | None, tz: ZoneInfo, nome: str
             ) -> tuple[datetime | None, datetime | None]:
    if de is not None and ate is not None and ate < de:
        raise _invalid(f"No período {nome}, a data final vem antes da inicial")
    return (_dia(de, tz) if de else None,
            _dia(ate + timedelta(days=1), tz) if ate else None)


def _destino_base(f: Filtros) -> list[ColumnElement[bool]]:
    """As condições de "um destino ativo desta conta/rede" (o filtro de conta e rede)."""
    conds: list[ColumnElement[bool]] = [Postagem.archived_at.is_(None)]
    if f.conta_id is not None:
        conds.append(Postagem.conta_id == f.conta_id)
    if f.plataforma is not None:
        conds.append(Conta.platform == f.plataforma)
    return conds


def _hoje_e_semana(agora: datetime, tz: ZoneInfo) -> tuple[datetime, datetime, datetime]:
    hoje = agora.astimezone(tz).date()
    inicio_semana = _dia(hoje - timedelta(days=hoje.weekday()), tz)  # segunda-feira
    return _dia(hoje, tz), _dia(hoje + timedelta(days=1), tz), inicio_semana


def _atalho(nome: s.Atalho, dest: list[ColumnElement[bool]], agora: datetime,
            tz: ZoneInfo) -> ColumnElement[bool]:
    ee = consulta.estado_efetivo(agora)
    agendado = Postagem.estado == DestinoEstado.agendado
    hoje, amanha, semana = _hoje_e_semana(agora, tz)
    match nome:
        case s.Atalho.prontos_sem_agendamento:
            return and_(consulta.pronto(),
                        ~consulta.algum_destino(*dest, Postagem.estado.in_(MARCADOS)))
        case s.Atalho.aprovados_sem_data:
            return consulta.algum_destino(*dest, ee == EstadoEfetivo.aprovado.value)
        case s.Atalho.aprovacao_pedida:
            return consulta.algum_destino(*dest, ee == EstadoEfetivo.aprovacao_pedida.value)
        case s.Atalho.agendados_hoje:
            return consulta.algum_destino(*dest, agendado, Postagem.planned_at >= hoje,
                                          Postagem.planned_at < amanha)
        case s.Atalho.esta_semana:
            return consulta.algum_destino(*dest, agendado, Postagem.planned_at >= semana,
                                          Postagem.planned_at < semana + timedelta(days=7))
        case s.Atalho.a_postar:
            return consulta.algum_destino(*dest, ee == EstadoEfetivo.a_postar.value)
        case s.Atalho.atrasados:
            return consulta.algum_destino(*dest, ee == EstadoEfetivo.atrasado.value)
        case s.Atalho.falharam:
            return consulta.algum_destino(*dest, Postagem.estado == DestinoEstado.falhou)
        case s.Atalho.vencidos:
            return consulta.algum_destino(*dest, ee == EstadoEfetivo.vencido.value)
        case s.Atalho.enviando:
            return consulta.algum_destino(*dest, Postagem.estado == DestinoEstado.enviando)
        case s.Atalho.rascunhos_criados:
            return consulta.algum_destino(*dest,
                                          Postagem.estado == DestinoEstado.rascunho_criado)
    raise AssertionError(nome)  # pragma: no cover


def _escape_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _condicoes(f: Filtros, agora: datetime, tz: ZoneInfo) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [consulta.arquivado() == f.archived]
    dest = _destino_base(f)
    if f.perfil_ids:
        conds.append(Conteudo.perfil_id.in_(f.perfil_ids))
    if f.origem is not None:
        conds.append(Conteudo.origem == f.origem)
    if f.estados:
        valores = [e.value for e in f.estados if e != s.EstadoFiltro.sem_conta]
        alternativas = []
        if valores:
            alternativas.append(consulta.algum_destino(
                *dest, consulta.estado_efetivo(agora).in_(valores)))
        if s.EstadoFiltro.sem_conta in f.estados:
            alternativas.append(~consulta.algum_destino(*dest))
        conds.append(or_(*alternativas))
    if f.atalho is not None:
        conds.append(_atalho(f.atalho, dest, agora, tz))
    if (f.conta_id is not None or f.plataforma is not None) and not f.estados \
            and f.atalho is None:
        conds.append(consulta.algum_destino(*dest))  # só conta/rede: os que têm destino nela
    de, ate = _periodo(f.agendado_de, f.agendado_ate, tz, "agendado")
    if de is not None or ate is not None:
        periodo = [c for c in (Postagem.planned_at >= de if de else None,
                               Postagem.planned_at < ate if ate else None) if c is not None]
        conds.append(consulta.algum_destino(*dest, *periodo))
    de, ate = _periodo(f.criado_de, f.criado_ate, tz, "de criação")
    if de is not None:
        conds.append(Conteudo.created_at >= de)
    if ate is not None:
        conds.append(Conteudo.created_at < ate)
    if f.q:
        padrao = f"%{_escape_like(f.q.strip())}%"
        conds.append(or_(
            Conteudo.titulo.ilike(padrao, escape="\\"),
            Corte.hook_text.ilike(padrao, escape="\\"),
            Corte.openshorts_title.ilike(padrao, escape="\\"),
            consulta.algum_destino(Postagem.archived_at.is_(None),
                                   Postagem.titulo.ilike(padrao, escape="\\")),
        ))
    return conds


def _proximo_agendamento(f: Filtros) -> ColumnElement[datetime]:
    """Chave da ordem `agenda`: o próximo `planned_at` agendado (na conta/rede do filtro)."""
    sub = (
        select(func.min(Postagem.planned_at))
        .join(Conta, Conta.id == Postagem.conta_id)
        .where(Postagem.conteudo_id == Conteudo.id, Postagem.estado == DestinoEstado.agendado,
               *_destino_base(f))
        .correlate(Conteudo)
        .scalar_subquery()
    )
    return func.coalesce(sub, literal(SEM_AGENDA))


def _cursor_encode(chave: datetime, item_id: uuid.UUID) -> str:
    raw = json.dumps([chave.isoformat(), str(item_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _cursor_decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        chave, item_id = json.loads(raw)
        valor = datetime.fromisoformat(chave)
        if valor.tzinfo is None:
            raise ValueError("sem fuso")
        return valor, uuid.UUID(item_id)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise _invalid("Cursor inválido; recarregue a lista") from exc


def list_conteudos(db: Session, f: Filtros, cursor: str | None, limit: int = LIMIT_PADRAO,
                   offset: int | None = None) -> s.ConteudosList:
    if cursor and offset is not None:
        raise ApiError(400, "paginacao_invalida", "Use offset ou cursor, não os dois.")
    tz = app_tz()
    agora = datetime.now(UTC)
    conds = _condicoes(f, agora, tz)
    total = db.scalar(consulta.join_corte(select(func.count(Conteudo.id))).where(*conds)) or 0

    if f.ordem == s.OrdemConteudos.agenda:
        chave = _proximo_agendamento(f)
        ordem = (chave.asc(), Conteudo.id.asc())
    else:
        chave = Conteudo.created_at
        ordem = (Conteudo.created_at.desc(), Conteudo.id.desc())
    query = _linhas().add_columns(chave.label("chave")).where(*conds)
    if cursor:
        valor, item_id = _cursor_decode(cursor)
        pos = tuple_(chave, Conteudo.id)
        query = query.where(pos > tuple_(literal(valor), literal(item_id))
                            if f.ordem == s.OrdemConteudos.agenda
                            else pos < tuple_(literal(valor), literal(item_id)))
    elif offset:
        query = query.offset(offset)
    rows = db.execute(query.order_by(*ordem).limit(limit + 1)).all()
    proximo = None
    if len(rows) > limit:
        rows = rows[:limit]
        proximo = _cursor_encode(rows[-1].chave, rows[-1].Conteudo.id)
    return s.ConteudosList(items=_itens(db, rows, agora), total=total, next_cursor=proximo)


def resumo(db: Session, perfil_ids: list[uuid.UUID], conta_id: uuid.UUID | None
           ) -> s.Atalhos:
    """As contagens dos atalhos (conteúdos não arquivados), numa consulta só."""
    tz = app_tz()
    agora = datetime.now(UTC)
    f = Filtros(perfil_ids=perfil_ids, conta_id=conta_id)
    dest = _destino_base(f)
    colunas = [func.count(Conteudo.id).filter(_atalho(a, dest, agora, tz)).label(a.value)
               for a in s.Atalho]
    query = consulta.join_corte(select(*colunas)).where(consulta.arquivado().is_(False))
    if perfil_ids:
        query = query.where(Conteudo.perfil_id.in_(perfil_ids))
    row = db.execute(query).one()
    return s.Atalhos(**{a.value: getattr(row, a.value) for a in s.Atalho})


# ---- mutações ----

def _corte_do(db: Session, conteudo: Conteudo) -> Corte | None:
    return db.get(Corte, conteudo.corte_id) if conteudo.corte_id is not None else None


def _arquivado(db: Session, conteudo: Conteudo) -> bool:
    corte = _corte_do(db, conteudo)
    return corte.archived if corte is not None else conteudo.archived


def update_titulo(db: Session, actor: Actor, conteudo_id: uuid.UUID, version: int,
                  titulo: str) -> Conteudo:
    conteudo = get_conteudo_or_404(db, conteudo_id, lock=True)
    history.check_version(conteudo, version, LABEL)
    if _arquivado(db, conteudo):
        raise ApiError(409, "conflict", "Este conteúdo está arquivado")
    before = history.snapshot(conteudo)
    conteudo.titulo = titulo
    after = history.snapshot(conteudo)
    if after != before:
        conteudo.updated_by = actor.user_id
        history.record(db, actor, ENTITY, conteudo, "updated", before, after)
    db.flush()
    return conteudo


def _cancelar_agendamentos(db: Session, actor: Actor, conteudo: Conteudo) -> None:
    """Arquivar cancela os agendamentos ativos, na mesma transação (research R6)."""
    from sociman_api.postagem import service as postagem_service  # import tardio (ciclo)

    postagem_service.cancelar_por_arquivo(db, actor, conteudo.id)


def _checar_arquivo(db: Session, actor: Actor, conteudo: Conteudo, rota: str) -> None:
    """Spec 015: sem envio em andamento; automático agendado só por dono humano."""
    from sociman_api.postagem import service as postagem_service  # import tardio (ciclo)

    postagem_service.checar_arquivo(db, actor, conteudo.id, rota)


def archive(db: Session, actor: Actor, conteudo_id: uuid.UUID, version: int) -> Conteudo:
    conteudo = get_conteudo_or_404(db, conteudo_id, lock=True)
    history.check_version(conteudo, version, LABEL)
    if conteudo.origem == ConteudoOrigem.corte:
        from sociman_api.cortes import service as cortes_service  # import tardio (ciclo)

        corte = cortes_service.get_corte_or_404(db, conteudo.id, lock=True)
        cortes_service.arquivar(db, actor, corte.id, corte.version)  # cancela também (T041)
        return conteudo
    if conteudo.archived:
        raise ApiError(409, "conflict", "Este conteúdo já está arquivado")
    _checar_arquivo(db, actor, conteudo, "POST /api/conteudos/{id}/archive")
    before = history.snapshot(conteudo)
    conteudo.archived_at = datetime.now(UTC)
    conteudo.archived_by = actor.user_id
    conteudo.updated_by = actor.user_id
    history.record(db, actor, ENTITY, conteudo, "archived", before, history.snapshot(conteudo))
    _cancelar_agendamentos(db, actor, conteudo)
    db.flush()
    return conteudo


def restore(db: Session, actor: Actor, conteudo_id: uuid.UUID, version: int) -> Conteudo:
    """Restaurar não reagenda nada."""
    conteudo = get_conteudo_or_404(db, conteudo_id, lock=True)
    history.check_version(conteudo, version, LABEL)
    if conteudo.origem == ConteudoOrigem.corte:
        from sociman_api.cortes import service as cortes_service  # import tardio (ciclo)

        corte = cortes_service.get_corte_or_404(db, conteudo.id, lock=True)
        cortes_service.restaurar(db, actor, corte.id, corte.version)
        return conteudo
    if not conteudo.archived:
        raise ApiError(409, "conflict", "Este conteúdo não está arquivado")
    before = history.snapshot(conteudo)
    conteudo.archived_at = None
    conteudo.archived_by = None
    conteudo.updated_by = actor.user_id
    history.record(db, actor, ENTITY, conteudo, "restored", before, history.snapshot(conteudo))
    db.flush()
    return conteudo


def list_versions(db: Session, conteudo_id: uuid.UUID) -> VersionsList:
    get_conteudo_or_404(db, conteudo_id)
    return versions_out(db, ENTITY, conteudo_id)


def revert(db: Session, actor: Actor, conteudo_id: uuid.UUID, version: int,
           to_version: int) -> Conteudo:
    """Só o dono (rota). Volta o título e, no vídeo próprio, o arquivamento (arquivar pela
    reversão também cancela os agendamentos). Na origem corte o arquivamento é do corte e não
    volta por aqui (exceção herdada da 006)."""
    conteudo = get_conteudo_or_404(db, conteudo_id, lock=True)
    history.check_version(conteudo, version, LABEL)
    state = target_state(db, ENTITY, conteudo, to_version)
    before = history.snapshot(conteudo)
    conteudo.titulo = state["titulo"]
    arquivou = False
    if conteudo.origem != ConteudoOrigem.corte:
        arquivou = state["archived"] and not conteudo.archived
        if arquivou:
            _checar_arquivo(db, actor, conteudo, "POST /api/conteudos/{id}/revert")
        apply_archived(conteudo, state["archived"], actor)
    after = history.snapshot(conteudo)
    if after == before:
        raise _invalid("Essa versão é igual à atual")
    conteudo.updated_by = actor.user_id
    history.record(db, actor, ENTITY, conteudo, "reverted", before, after,
                   {"from_version": to_version})
    if arquivou:
        _cancelar_agendamentos(db, actor, conteudo)
    db.flush()
    return conteudo
