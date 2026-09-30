"""Destinos (conteúdo × conta), aprovação, agendamento, sugestões de texto e calendário
(spec 006, US5; spec 014, US2 a US4, research R3 a R8).

Spec 014: a `Postagem` é o **destino**. Aprovar e recusar são do dono; pedir aprovação é de
todos; agendar exige destino aprovado (ou um dono, que aprova e agenda no mesmo passo). Só o
modo `lembrete` existe (princípio I: `capacidades.modos_da_conta`, os CHECKs do banco e os
guardas). As rotas de postagem da 006 saíram (T045); as de sugestão (deprecated) ficam.

- Um destino ativo por conteúdo e conta, com histórico (`entity_type = "postagem"`); editar
  os textos não desfaz a aprovação (Q2 = A).
- **`postado` só por ação humana**, em `marcar_postado` (princípio I; o guarda da T074 confere por
  AST que nenhum outro lugar atribui `DestinoEstado.postado`). Nada aqui publica.
- A sugestão do Claude é gravada em `ia_chamadas` (spec 008; `tipo_campo = "postagem.textos"`,
  sucesso ou erro) e **não altera** o destino: a tela preenche os campos, e o usuário salva.
"""

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history, imaging
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import UserRole
from sociman_api.config import get_settings
from sociman_api.conteudos import capacidades, consulta, proposta, sequencia
from sociman_api.conteudos.models import Conteudo, Modo
from sociman_api.cortes.models import Corte
from sociman_api.errors import ApiError
from sociman_api.ia import aplicacao
from sociman_api.ia import service as ia_service
from sociman_api.ia.cliente import IaClient
from sociman_api.ia.models import IaChamada
from sociman_api.ia.tipos import TIPOS
from sociman_api.marca.models import BrandKit
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo
from sociman_api.perfis.models import Conta, Perfil, Platform
from sociman_api.perfis.platforms import PLATFORMS
from sociman_api.perfis.schemas import VersionsList
from sociman_api.perfis.service_perfis import (
    apply_archived,
    target_state,
    user_refs,
    versions_out,
)
from sociman_api.postagem import envio, schemas, textos
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao import legenda
from sociman_api.publicacao.schemas import OpcoesTikTok

ENTITY = "postagem"
CORTE_NOT_FOUND = "Corte não encontrado"
UQ_ATIVA = "uq_postagens_conteudo_conta_ativa"
TOLERANCIA_PASSADO = timedelta(minutes=1)
CALENDARIO_MAX_DIAS = 62
SEM_DATA_MAX = 200
ANTERIORES_MAX = 3
TIPO_TEXTOS = "postagem.textos"  # tipo de campo das sugestões da 006 em `ia_chamadas`
HASHTAG_RE = re.compile(r"^#\w{1,50}$", re.UNICODE)  # \w = [\p{L}\p{N}_]


def app_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


# ---- auxiliares ----

def _invalid(message: str) -> ApiError:
    return ApiError(400, "validation_error", message)


def _corte_or_404(db: Session, corte_id: uuid.UUID) -> Corte:
    corte = db.get(Corte, corte_id)
    if corte is None:
        raise ApiError(404, "not_found", CORTE_NOT_FOUND)
    return corte


def _conta_do_perfil(db: Session, corte: Corte, conta_id: uuid.UUID) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None or conta.perfil_id != corte.perfil_id:
        raise _invalid("A conta de destino precisa ser do perfil do corte")
    if conta.archived:
        raise _invalid("Esta conta está arquivada")
    return conta


def normalizar_hashtags(items: Iterable[str]) -> list[str]:
    """`"Dica"` → `"#dica"`: # na frente, sem repetir (sem diferenciar maiúsculas); 400 se
    alguma não casa com `^#[\\p{L}0-9_]{1,50}$`."""
    vistas: dict[str, str] = {}
    for raw in items:
        tag = raw.strip()
        tag = tag if tag.startswith("#") else f"#{tag}"
        if not HASHTAG_RE.match(tag):
            raise _invalid(f"Hashtag inválida: {raw.strip()} (uma palavra, sem espaço nem "
                           "pontuação, até 50 caracteres)")
        vistas.setdefault(tag.casefold(), tag)
    tags = list(vistas.values())
    if len(tags) > textos.HASHTAGS_MAX:
        raise _invalid(f"No máximo {textos.HASHTAGS_MAX} hashtags")
    return tags


def _aware(dt: datetime) -> datetime:
    """Sem offset, a data é local (APP_TZ); guardada sempre com fuso."""
    return dt.replace(tzinfo=app_tz()) if dt.tzinfo is None else dt


def _planned(dt: datetime) -> datetime:
    dt = _aware(dt)
    if dt < datetime.now(UTC) - TOLERANCIA_PASSADO:
        raise ApiError(400, "planned_in_past", "Esse horário já passou; escolha outro")
    return dt


# ---- saídas ----

# ---- mutações ----

def marcar_postado(db: Session, actor: Actor, destino_id: uuid.UUID, version: int,
                   posted_url: str | None) -> Postagem:
    """O ÚNICO lugar que atribui `postado` (princípio I): alguém postou à mão e registra. Só
    a partir de `aprovado`, `agendado` (spec 014) ou `rascunho_criado` (015: o dono finalizou
    o rascunho no app). Um agendamento automático ainda pendente só por dono humano (cancela o
    envio)."""
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, DESTINO_LABEL)
    _check_textos_editaveis(destino)
    if destino.estado not in POSTAVEIS:
        raise ApiError(409, "conflict", "Só dá para marcar como postado um destino aprovado")
    if destino.estado == DestinoEstado.agendado and automatico(destino.modo):
        exigir_humano(actor, "POST /api/destinos/{id}/postado", destino)
    before = history.snapshot(destino)
    destino.estado = DestinoEstado.postado
    destino.posted_at = datetime.now(UTC)
    destino.posted_url = posted_url
    _record(db, actor, destino, "updated", before, {"acao": "postado"})
    db.flush()
    return destino


# ---- sugestões (Claude) ----

def _sugestao_out(s: IaChamada) -> schemas.Sugestao:
    r = s.proposta or {}
    return schemas.Sugestao(id=s.id, plataforma=s.plataforma, titulo=r.get("titulo", ""),
                            descricao=r.get("descricao", ""), hashtags=r.get("hashtags", []),
                            ajustes=list(s.ajustes), model=s.model, created_at=s.created_at)


def list_sugestoes(db: Session, corte_id: uuid.UUID) -> list[schemas.Sugestao]:
    _corte_or_404(db, corte_id)
    rows = db.scalars(
        select(IaChamada)
        .where(IaChamada.corte_id == corte_id, IaChamada.tipo_campo == TIPO_TEXTOS,
               IaChamada.proposta.is_not(None))
        .order_by(IaChamada.created_at.desc(), IaChamada.id)
    )
    return [_sugestao_out(s) for s in rows]


def _anteriores(db: Session, corte_id: uuid.UUID, plataforma: Platform) -> list[IaChamada]:
    """"Outra versão" da 006: as últimas propostas deste corte na plataforma."""
    return list(db.scalars(
        select(IaChamada)
        .where(IaChamada.corte_id == corte_id, IaChamada.tipo_campo == TIPO_TEXTOS,
               IaChamada.plataforma == plataforma, IaChamada.proposta.is_not(None))
        .order_by(IaChamada.created_at.desc()).limit(ANTERIORES_MAX)
    ))


def sugerir(db: Session, actor: Actor, corte_id: uuid.UUID, body: schemas.SugestaoIn,
            client: IaClient | None) -> IaChamada:
    """Rota da 006 (deprecated): delega ao assistente (`postagem.textos`, alvo corte + conta,
    sem sessão). O `ia.service.executar` grava a chamada sempre (commit antes do erro)."""
    corte = _corte_or_404(db, corte_id)
    conta = _conta_do_perfil(db, corte, body.conta_id)
    perfil = db.get(Perfil, corte.perfil_id)
    assert perfil is not None
    alvo = ia_service.AlvoResolvido("corte", corte.id, corte=corte, conta=conta,
                                    conteudo=db.get(Conteudo, corte.id))
    anteriores = _anteriores(db, corte.id, conta.platform) if body.outra_versao else []
    return ia_service.executar(db, actor, TIPOS[TIPO_TEXTOS], perfil, alvo, {}, "", client,
                               anteriores=anteriores)


def sugestao_out(s: IaChamada) -> schemas.Sugestao:
    return _sugestao_out(s)


# ---- calendário (R11) ----

def calendario(db: Session, de: date, ate: date, perfil_id: uuid.UUID | None,
               plataforma: Platform | None, conta_id: uuid.UUID | None = None
               ) -> schemas.CalendarioOut:
    """Destinos com `planned_at` entre `de` e `ate` (dias locais em APP_TZ, inclusive), com o
    modo e o estado efetivo, e a coluna "sem data": primeiro os destinos aprovados sem data,
    depois os conteúdos prontos sem destino agendado (nem postado)."""
    if ate < de:
        raise _invalid("A data final vem antes da inicial")
    if (ate - de).days + 1 > CALENDARIO_MAX_DIAS:
        raise _invalid(f"O calendário mostra até {CALENDARIO_MAX_DIAS} dias por vez")
    tz = app_tz()
    inicio = datetime.combine(de, time.min, tzinfo=tz)
    fim = datetime.combine(ate + timedelta(days=1), time.min, tzinfo=tz)

    def _filtros(query):
        if perfil_id is not None:
            query = query.where(Conteudo.perfil_id == perfil_id)
        if plataforma is not None:
            query = query.where(Conta.platform == plataforma)
        if conta_id is not None:
            query = query.where(Conta.id == conta_id)
        return query

    colunas = (Conteudo, Perfil, consulta.situacao(), consulta.poster_key(),
               consulta.duration_ms())
    query = _filtros(
        consulta.destinos_do_conteudo().add_columns(*colunas)
        .join(Perfil, Perfil.id == Conteudo.perfil_id)
        .where(Postagem.archived_at.is_(None), Postagem.planned_at >= inicio,
               Postagem.planned_at < fim)
        .order_by(Postagem.planned_at, Postagem.id)
    )
    rows = db.execute(query).all()
    base = destinos_out(db, [r[0] for r in rows])
    cores = _cores_perfis(db, {r[2].id for r in rows})
    items = [
        schemas.CalendarioItem(
            **b.model_dump(),
            conteudo=schemas.ConteudoCalendario(
                id=k.id, origem=k.origem, titulo=k.titulo, situacao=sit, duration_ms=dur,
                poster_url=imaging.poster_url(poster) if poster else None),
            perfil=schemas.PerfilCalendario(id=pf.id, name=pf.name, slug=pf.slug,
                                            cor=cores.get(pf.id)),
        )
        for b, (_, k, pf, sit, poster, dur) in zip(base, rows, strict=True)
    ]

    # 1) destinos aprovados sem data (conteúdo pronto, não arquivado)
    aprovados = db.execute(_filtros(
        consulta.destinos_do_conteudo().add_columns(Conteudo, consulta.poster_key())
        .where(Postagem.archived_at.is_(None), Postagem.estado == DestinoEstado.aprovado,
               consulta.pronto(), ~consulta.arquivado())
        .order_by(Postagem.aprovado_em.desc().nulls_last(), Postagem.id)
        .limit(SEM_DATA_MAX)
    )).all()
    sem_data = [
        schemas.SemData(
            conteudo_id=k.id, destino_id=d.id, conta_id=d.conta_id, perfil_id=k.perfil_id,
            poster_url=imaging.poster_url(poster) if poster else None,
            titulo=d.titulo or k.titulo, aprovado=True)
        for d, k, poster in aprovados
    ]
    # 2) conteúdos prontos sem destino agendado nem postado (na conta, se filtrada)
    marcado = [Postagem.conteudo_id == Conteudo.id, Postagem.archived_at.is_(None),
               Postagem.estado.in_([DestinoEstado.agendado, DestinoEstado.postado])]
    if conta_id is not None:
        marcado.append(Postagem.conta_id == conta_id)
    ja = {k.id for _, k, _ in aprovados}
    sem = consulta.join_corte(
        select(Conteudo, consulta.poster_key())
        .where(consulta.pronto(), ~consulta.arquivado(), ~exists().where(*marcado))
        .order_by(Conteudo.created_at.desc(), Conteudo.id)
        .limit(SEM_DATA_MAX)
    )
    if perfil_id is not None:
        sem = sem.where(Conteudo.perfil_id == perfil_id)
    if conta_id is not None or plataforma is not None:
        contas = select(Conta.perfil_id).where(Conta.archived_at.is_(None))
        if conta_id is not None:
            contas = contas.where(Conta.id == conta_id)
        if plataforma is not None:
            contas = contas.where(Conta.platform == plataforma)
        sem = sem.where(Conteudo.perfil_id.in_(contas))
    for k, poster in db.execute(sem):
        if k.id in ja or len(sem_data) >= SEM_DATA_MAX:
            continue
        sem_data.append(schemas.SemData(
            conteudo_id=k.id, destino_id=None, conta_id=None, perfil_id=k.perfil_id,
            poster_url=imaging.poster_url(poster) if poster else None, titulo=k.titulo,
            aprovado=False))
    cores.update(_cores_perfis(db, {s.perfil_id for s in sem_data} - cores.keys()))
    for item in sem_data:
        item.perfil_cor = cores.get(item.perfil_id)
    return schemas.CalendarioOut(items=items, sem_data=sem_data)


_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _cores_perfis(db: Session, perfil_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Cor de cada perfil no calendário (R14): a 1ª cor da paleta do kit salvo. Perfil sem kit
    fica fora do dicionário (o SPA usa uma cor derivada do id)."""
    if not perfil_ids:
        return {}
    cores: dict[uuid.UUID, str] = {}
    for perfil_id, palette in db.execute(
        select(BrandKit.perfil_id, BrandKit.palette).where(BrandKit.perfil_id.in_(perfil_ids))
    ):
        valor = palette[0].get("valor") if palette and isinstance(palette[0], dict) else None
        if isinstance(valor, str) and _HEX.match(valor):
            cores[perfil_id] = valor.upper()
    return cores


# ======================================================================================
# Spec 014: destino (conteúdo × conta), aprovação, agendamento, lote e sequência
# (research R3 a R8; contracts/http-api.md da 014, "Destinos" e "Agendamentos").
# ======================================================================================

DESTINO_LABEL = "Este destino"
DESTINO_NOT_FOUND = "Destino não encontrado"
CONTEUDO_NOT_FOUND = "Conteúdo não encontrado"
NAO_PRONTO = "Aplique a marca antes de aprovar"
LOTE_MAX = 100
EDITAVEIS_POSTADO = (DestinoEstado.aprovado, DestinoEstado.agendado)
# Spec 015 (data-model, "Transições do destino").
POSTAVEIS = (DestinoEstado.aprovado, DestinoEstado.agendado, DestinoEstado.rascunho_criado)
AGENDAVEIS = (DestinoEstado.aprovado, DestinoEstado.agendado, DestinoEstado.falhou)
REAGENDAVEIS = (DestinoEstado.agendado, DestinoEstado.falhou)
DEPOIS_DA_APROVACAO = (DestinoEstado.aprovado, DestinoEstado.agendado, DestinoEstado.postado,
                       DestinoEstado.enviando, DestinoEstado.rascunho_criado,
                       DestinoEstado.publicado, DestinoEstado.falhou)
JA_SAIU = (DestinoEstado.postado, DestinoEstado.rascunho_criado, DestinoEstado.publicado)
EM_ANDAMENTO = "Este destino está sendo enviado à rede; espere terminar"
PUBLICAR_SEM_TELA = "Publicar exige a tela da TikTok (privacidade, interações e consentimento)"
PUBLICAR_EM_LOTE = "Publicar exige a tela da TikTok para cada vídeo"


@dataclass(frozen=True)
class _ConteudoInfo:
    """O que as regras do destino precisam do conteúdo, pelas expressões de `consulta.py`."""

    conteudo: Conteudo
    pronto: bool
    arquivado: bool
    video_ref: str | None


def _conteudo_info(db: Session, conteudo_id: uuid.UUID) -> _ConteudoInfo:
    row = db.execute(
        consulta.join_corte(select(Conteudo, consulta.pronto(), consulta.arquivado(),
                                   consulta.video_ref()))
        .where(Conteudo.id == conteudo_id)
    ).first()
    if row is None:
        raise ApiError(404, "not_found", CONTEUDO_NOT_FOUND)
    conteudo, pronto, arquivado, video_ref = row
    return _ConteudoInfo(conteudo, bool(pronto), bool(arquivado), video_ref)


def _is_dono(actor: Actor) -> bool:
    return actor.user is not None and actor.user.role == UserRole.dono


def automatico(*modos: Modo | None) -> bool:
    """Algum dos modos (o pedido ou o atual do destino) é executado pelo SociMan (015)."""
    return any(m is not None and m != Modo.lembrete for m in modos)


def exigir_humano(actor: Actor, rota: str, destino: Postagem | None = None,
                  conta_id: uuid.UUID | None = None) -> None:
    """Modo automático: só dono humano (princípio I, R15). Membro → 403 `somente_dono`; IA,
    agente ou MCP → 403 `somente_humano` + evento `publicacao_recusada`."""
    from sociman_api.publicacao.service import exigir_humano_dono  # import tardio (ciclo)

    exigir_humano_dono(actor, rota, conta_id=conta_id or (destino.conta_id if destino else None),
                       destino_id=destino.id if destino is not None else None)


def check_sem_envio(destino: Postagem) -> None:
    """De `enviando` nada sai por ação humana (data-model, "Transições")."""
    if destino.estado == DestinoEstado.enviando:
        raise ApiError(409, "envio_em_andamento", EM_ANDAMENTO)


def _confirmar_incerta(destino: Postagem, confirmo: bool | None) -> None:
    """Q4: devolver à fila um `falhou` incerto exige "Conferi no app e o rascunho não
    chegou" (a mesma função para tentar de novo, reagendar e agendar de novo)."""
    from sociman_api.publicacao.service import exigir_confirmacao_incerta  # import tardio

    exigir_confirmacao_incerta(destino, confirmo)


def resolver_opcoes(conta: Conta, modo: Modo, pedido: OpcoesTikTok | None,
                    destino: Postagem | None) -> OpcoesTikTok | None:
    """US3 (R13): no modo `publicar`, as opções da tela obrigatória (as do pedido ou, ao
    reagendar sem mudá-las, as já confirmadas), validadas pelas regras da rede. Sem elas ou com
    alguma combinação proibida: 400 `opcoes_invalidas` com `details.problemas`."""
    if modo != Modo.publicar:
        return None
    cru: Any = pedido
    if cru is None and destino is not None and destino.modo == Modo.publicar:
        cru = destino.opcoes_rede
    if cru is None:
        raise ApiError(400, "opcoes_invalidas", PUBLICAR_SEM_TELA, details={"problemas": [
            {"campo": "opcoes", "motivo": PUBLICAR_SEM_TELA}]})
    opcoes = cru if isinstance(cru, OpcoesTikTok) else OpcoesTikTok.model_validate(cru)
    from sociman_api.publicacao import registro  # import tardio (ciclo)

    executor = registro.executor_para(conta.platform)
    problemas = list(executor.validar_opcoes(opcoes, None)) if executor is not None else []
    if problemas:
        raise ApiError(400, "opcoes_invalidas", problemas[0].mensagem,
                       details={"problemas": [{"campo": p.campo, "motivo": p.mensagem}
                                              for p in problemas]})
    return opcoes


@dataclass(frozen=True)
class _TextosEfetivos:
    descricao: str
    hashtags: list[str]


def _exigir_legenda(conta: Conta, destino: Postagem | None,
                    textos: schemas.Textos | None) -> None:
    """T101: os textos que o destino terá depois de agendar (os do pedido ou os atuais)."""
    descricao = destino.descricao if destino is not None else ""
    hashtags = list(destino.hashtags or []) if destino is not None else []
    if textos is not None and textos.descricao is not None:
        descricao = textos.descricao
    if textos is not None and textos.hashtags is not None:
        hashtags = normalizar_hashtags(textos.hashtags)
    legenda.exigir(conta.platform, _TextosEfetivos(descricao or "", hashtags))


def snapshot_publicar(destino: Postagem, opcoes: dict[str, Any], video_ref: str | None
                      ) -> dict[str, Any]:
    """O que vai para a rede no `publicar` (R13): a legenda dos textos de agora, as opções e o
    consentimento que o dono confirmou e o vídeo. A trilha envia isto, nunca os textos vivos."""
    return {"legenda": legenda.legenda_tiktok(destino),
            "opcoes": opcoes, "consentimento": opcoes["consentimento"], "videoRef": video_ref}


def _marcar_decisao(destino: Postagem, actor: Actor, video_ref: str | None,
                    opcoes: OpcoesTikTok | None = None) -> None:
    """Quem agendou (ou reagendou) por último e o snapshot do envio (015). No rascunho, o
    snapshot guarda só o vídeo (a API do inbox não recebe textos, R13); no publicar, a legenda,
    as opções da tela obrigatória e o consentimento."""
    destino.agendado_por = actor.user_id
    destino.agendado_em = datetime.now(UTC)
    destino.falha_motivo = None
    destino.falha_incerta = False
    if destino.modo == Modo.publicar:
        assert opcoes is not None  # `resolver_opcoes` já recusou antes de gravar
        dados = opcoes.model_dump(mode="json", by_alias=True)
        destino.opcoes_rede = dados
        destino.envio_snapshot = snapshot_publicar(destino, dados, video_ref)
    elif destino.modo == Modo.criar_rascunho:
        destino.envio_snapshot = {"videoRef": video_ref}
        destino.opcoes_rede = None
    elif destino.modo == Modo.lembrete:
        destino.envio_snapshot = None
        destino.opcoes_rede = None


def get_destino_or_404(db: Session, destino_id: uuid.UUID, lock: bool = False) -> Postagem:
    destino = db.get(Postagem, destino_id, with_for_update=lock)
    if destino is None:
        raise ApiError(404, "not_found", DESTINO_NOT_FOUND)
    return destino


def _conta_invalida(message: str) -> ApiError:
    return ApiError(400, "conta_invalida", message)


def _conta_do_conteudo(db: Session, conteudo: Conteudo, conta_id: uuid.UUID) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None or conta.perfil_id != conteudo.perfil_id:
        raise _conta_invalida("A conta de destino precisa ser do perfil do conteúdo")
    if conta.archived:
        raise _conta_invalida("Esta conta está arquivada")
    return conta


def _destino_exists() -> ApiError:
    return ApiError(409, "destino_exists", "Este conteúdo já tem um destino para essa conta")


def _flush_destino(db: Session) -> None:
    """Corrida entre a checagem e a escrita: o índice único parcial decide (409)."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == UQ_ATIVA:
            raise _destino_exists() from exc
        raise


def _destino_ativo(db: Session, conteudo_id: uuid.UUID, conta_id: uuid.UUID,
                   lock: bool = False) -> Postagem | None:
    query = select(Postagem).where(Postagem.conteudo_id == conteudo_id,
                                   Postagem.conta_id == conta_id,
                                   Postagem.archived_at.is_(None))
    if lock:
        query = query.with_for_update()
    with db.no_autoflush:
        return db.scalar(query)


def _check_textos_editaveis(destino: Postagem) -> None:
    check_sem_envio(destino)
    if destino.estado == DestinoEstado.postado:
        raise ApiError(409, "conflict", "Este destino já foi marcado como postado")
    if destino.archived:
        raise ApiError(409, "conflict", "Este destino está arquivado")


def _preencher_proposta(db: Session, destino: Postagem) -> None:
    """T074: o destino novo nasce com o título e a descrição da proposta do OpenShorts nos
    campos que vierem vazios (cortados nos limites do destino)."""
    if destino.titulo and destino.descricao:
        return
    conteudo = db.get(Conteudo, destino.conteudo_id)
    corte = db.get(Corte, conteudo.corte_id) if conteudo and conteudo.corte_id else None
    titulo, descricao = proposta.textos_iniciais(corte)
    destino.titulo = destino.titulo or titulo
    destino.descricao = destino.descricao or descricao


def _aplicar_textos(destino: Postagem, titulo: str | None, descricao: str | None,
                    hashtags: list[str] | None) -> None:
    if titulo is not None:
        destino.titulo = titulo
    if descricao is not None:
        destino.descricao = descricao
    if hashtags is not None:
        destino.hashtags = normalizar_hashtags(hashtags)


def _marcar_ia_destino(db: Session, actor: Actor, destino: Postagem, conteudo: Conteudo,
                       conta: Conta, before: dict | None, after: dict,
                       ia: list[aplicacao.IaAplicacao] | None) -> dict | None:
    """Spec 008 (R10): marca as chamadas aplicadas e grava o `sugestao_id` a partir do item
    `postagem.textos` (ou do primeiro)."""
    details = aplicacao.marcar(db, actor, ENTITY, destino, before, after, ia,
                               perfil_id=conteudo.perfil_id, plataforma=conta.platform.value)
    if details is not None:
        itens = details["ia"]
        item = next((i for i in itens if i["tipoCampo"] == TIPO_TEXTOS), itens[0])
        destino.sugestao_id = uuid.UUID(item["chamadaId"])
    return details


def _record(db: Session, actor: Actor, destino: Postagem, action: str, before: dict | None,
            details: dict | None = None) -> None:
    destino.updated_by = actor.user_id
    history.record(db, actor, ENTITY, destino, action, before, history.snapshot(destino),
                   details)


# ---- saída ----

def _conta_ref_014(conta: Conta, conexao: str = "nao_conectada") -> schemas.ContaRef:
    return schemas.ContaRef(id=conta.id, platform=conta.platform,
                            platform_name=conta.platform_name, handle=conta.handle,
                            status=conta.status, conexao=conexao)


def _derivados(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple]:
    """(estado efetivo, motivo de atenção, vídeo mudou) de cada destino, por `consulta.py`."""
    if not ids:
        return {}
    rows = db.execute(
        consulta.destinos_do_conteudo()
        .with_only_columns(Postagem.id, consulta.estado_efetivo(),
                           consulta.motivo_atencao_efetivo(), consulta.video_mudou())
        .where(Postagem.id.in_(list(ids)))
    )
    return {i: (e, m, bool(v)) for i, e, m, v in rows}


def destinos_out(db: Session, destinos: Sequence[Postagem]) -> list[schemas.Destino]:
    if not destinos:
        return []
    derivados = _derivados(db, [d.id for d in destinos])
    contas = {c.id: c for c in db.scalars(
        select(Conta).where(Conta.id.in_({d.conta_id for d in destinos})))}
    users = user_refs(db, [u for d in destinos for u in (
        d.updated_by, d.aprovado_por, d.pedido_por, d.recusado_por)])
    conexoes = envio.conexoes_por_conta(db, contas)
    extras = envio.campos_envio(db, destinos)
    tz = app_tz()

    def _dt(v: datetime | None) -> datetime | None:
        return v.astimezone(tz) if v is not None else None

    out = []
    for d in destinos:
        efetivo, motivo, mudou = derivados[d.id]
        aprovacao = schemas.Aprovacao(por=users[d.aprovado_por], em=_dt(d.aprovado_em)) \
            if d.aprovado_por is not None and d.aprovado_em is not None \
            and d.aprovado_por in users else None
        pedido = schemas.Pedido(por=users[d.pedido_por], em=_dt(d.pedido_em), nota=d.pedido_nota) \
            if d.estado == DestinoEstado.aprovacao_pedida and d.pedido_por in users \
            and d.pedido_em is not None else None
        recusa = schemas.Recusa(por=users[d.recusado_por], em=_dt(d.recusado_em),
                                motivo=d.recusa_motivo) \
            if d.recusa_motivo and d.recusado_por in users and d.recusado_em is not None \
            else None
        out.append(schemas.Destino(
            id=d.id, conteudo_id=d.conteudo_id,
            conta=_conta_ref_014(contas[d.conta_id],
                                 envio.estado_conexao(conexoes.get(d.conta_id))),
            titulo=d.titulo, descricao=d.descricao, hashtags=list(d.hashtags),
            estado=d.estado, estado_efetivo=efetivo, motivo_atencao=motivo, modo=d.modo,
            antecedencia_min=d.antecedencia_min, planned_at=_dt(d.planned_at),
            lembrado=d.lembrado_em is not None, posted_at=_dt(d.posted_at),
            posted_url=d.posted_url, falha_motivo=d.falha_motivo, aprovacao=aprovacao,
            pedido=pedido, recusa=recusa, video_mudou=mudou, archived=d.archived,
            version=d.version, created_at=d.created_at, updated_at=d.updated_at,
            updated_by=users.get(d.updated_by) if d.updated_by else None,
            **extras[d.id],
        ))
    return out


def destino_out(db: Session, destino: Postagem) -> schemas.Destino:
    db.flush()
    db.refresh(destino)
    return destinos_out(db, [destino])[0]


def resumos_por_conteudo(db: Session, conteudo_ids: Iterable[uuid.UUID]
                         ) -> dict[uuid.UUID, list[schemas.DestinoResumo]]:
    """Os destinos ativos (não arquivados) de cada conteúdo, numa consulta só (sem N+1): a
    linha da lista de Conteúdos e o `Corte.destinos`."""
    ids = list(set(conteudo_ids))
    out: dict[uuid.UUID, list[schemas.DestinoResumo]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.execute(
        consulta.destinos_do_conteudo()
        .add_columns(Conta, consulta.estado_efetivo(), consulta.motivo_atencao_efetivo(),
                     consulta.video_mudou())
        .where(Postagem.conteudo_id.in_(ids), Postagem.archived_at.is_(None))
        .order_by(Postagem.created_at, Postagem.id)
    )
    tz = app_tz()
    rows = rows.all()
    conexoes = envio.conexoes_por_conta(db, {r[0].conta_id for r in rows})
    fases = envio.ultimas_fases(db, [r[0].id for r in rows])
    for d, conta, efetivo, motivo, mudou in rows:
        out[d.conteudo_id].append(schemas.DestinoResumo(
            id=d.id, conta=_conta_ref_014(conta, envio.estado_conexao(conexoes.get(conta.id))),
            estado=d.estado, estado_efetivo=efetivo, motivo_atencao=motivo, modo=d.modo,
            planned_at=d.planned_at.astimezone(tz) if d.planned_at else None,
            sem_textos=not d.titulo.strip(), video_mudou=bool(mudou), version=d.version,
            ultima_fase=fases.get(d.id),
        ))
    return out


def list_destino_versions(db: Session, destino_id: uuid.UUID) -> VersionsList:
    get_destino_or_404(db, destino_id)
    return versions_out(db, ENTITY, destino_id)


def modos(db: Session, conta_id: uuid.UUID) -> list[capacidades.ModoInfo]:
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    return capacidades.modos_da_conta(conta, _conexao(db, conta))


# ---- notificações (R5) ----

def _plataforma_label(conta: Conta) -> str:
    if conta.platform == Platform.outra and conta.platform_name:
        return conta.platform_name
    return PLATFORMS[conta.platform].label


def _nome(destino: Postagem, conteudo: Conteudo) -> str:
    return destino.titulo or conteudo.titulo or "seu conteúdo"


def _link(destino: Postagem) -> str:
    return f"/app/conteudos/{destino.conteudo_id}?conta={destino.conta_id}"


def _avisar_pedido(db: Session, actor: Actor, destino: Postagem, conteudo: Conteudo,
                   conta: Conta) -> None:
    corpo = f"@{conta.handle}"
    if destino.pedido_nota:
        corpo += f": {destino.pedido_nota}"
    notificacoes.criar(
        db, NotificacaoTipo.aprovacao_pedida,
        titulo=f"Aprovação pedida: {_nome(destino, conteudo)} no {_plataforma_label(conta)}",
        corpo=corpo, link=_link(destino), entidade=(ENTITY, destino.id),
        dedupe_key=f"aprovacao_pedida:{destino.id}:{destino.version}",
        destinatarios=[u for u in notificacoes.donos_ativos(db) if u != actor.user_id],
    )


def _avisar_resposta(db: Session, actor: Actor, destino: Postagem, conteudo: Conteudo,
                     conta: Conta, pedido_por: uuid.UUID | None, aprovou: bool) -> None:
    if pedido_por is None or pedido_por == actor.user_id:
        return
    verbo = "aprovada" if aprovou else "recusada"
    corpo = f"@{conta.handle}" if aprovou else f"@{conta.handle}: {destino.recusa_motivo}"
    notificacoes.criar(
        db, NotificacaoTipo.aprovacao_respondida,
        titulo=f"Aprovação {verbo}: {_nome(destino, conteudo)} no {_plataforma_label(conta)}",
        corpo=corpo, link=_link(destino), entidade=(ENTITY, destino.id),
        dedupe_key=f"aprovacao_respondida:{destino.id}:{destino.version}",
        destinatarios=[pedido_por],
    )


# ---- destino: criar, textos, aprovação ----

def add_destino(db: Session, actor: Actor, conteudo_id: uuid.UUID,
                body: schemas.CreateDestinoIn) -> Postagem:
    info = _conteudo_info(db, conteudo_id)
    if info.arquivado:
        raise ApiError(409, "conflict", "Este conteúdo está arquivado")
    conta = _conta_do_conteudo(db, info.conteudo, body.conta_id)
    if _destino_ativo(db, conteudo_id, conta.id) is not None:
        raise _destino_exists()
    destino = Postagem(id=uuid.uuid4(), conteudo_id=conteudo_id, conta_id=conta.id,
                       estado=DestinoEstado.pendente, modo=Modo.lembrete,
                       created_by=actor.user_id, updated_by=actor.user_id)
    _aplicar_textos(destino, body.titulo, body.descricao, body.hashtags)
    _preencher_proposta(db, destino)
    db.add(destino)
    after = history.snapshot(destino)
    details = _marcar_ia_destino(db, actor, destino, info.conteudo, conta, None, after, body.ia)
    history.record(db, actor, ENTITY, destino, "created", None, after, details)
    _flush_destino(db)
    return destino


def update_textos(db: Session, actor: Actor, destino_id: uuid.UUID,
                  body: schemas.UpdateDestinoIn) -> Postagem:
    """Textos editáveis em qualquer estado, menos `postado` e arquivado; não desfaz a
    aprovação (Clarifications Q2 = A)."""
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, body.version, DESTINO_LABEL)
    _check_textos_editaveis(destino)
    if destino.estado == DestinoEstado.agendado and destino.modo == Modo.publicar:
        exigir_humano(actor, "PATCH /api/destinos/{id}", destino)  # Q2: só dono edita
    before = history.snapshot(destino)
    _aplicar_textos(destino, body.titulo, body.descricao, body.hashtags)
    conteudo = db.get(Conteudo, destino.conteudo_id)
    conta = db.get(Conta, destino.conta_id)
    assert conteudo is not None and conta is not None
    if destino.estado == DestinoEstado.agendado:
        legenda.exigir(conta.platform, destino)  # T101: um agendado não perde a legenda
    regravou = False
    if destino.estado == DestinoEstado.agendado and destino.modo == Modo.publicar \
            and destino.envio_snapshot:
        # Q2 = A: salvar os textos (mesmo iguais, o "Salvar de novo" de um snapshot
        # desatualizado) é uma nova confirmação do dono; regrava o que será publicado.
        snap = dict(destino.envio_snapshot)
        novo = snapshot_publicar(destino, snap["opcoes"], snap.get("videoRef"))
        if novo != snap:
            destino.envio_snapshot = novo
            destino.agendado_por = actor.user_id
            destino.agendado_em = datetime.now(UTC)
            regravou = True
    after = history.snapshot(destino)
    if not history.diff(before, after):
        return destino
    details = _marcar_ia_destino(db, actor, destino, conteudo, conta, before, after, body.ia)
    if regravou:
        details = {**(details or {}), "acao": "snapshot_atualizado"}
    _record(db, actor, destino, "updated", before, details)
    db.flush()
    return destino


def _check_pronto(info: _ConteudoInfo) -> None:
    if info.arquivado:
        raise ApiError(409, "conflict", "Este conteúdo está arquivado")
    if not info.pronto:
        raise ApiError(409, "conteudo_nao_pronto", NAO_PRONTO)


def _pedir(db: Session, actor: Actor, destino: Postagem, nota: str | None,
           details: dict[str, Any]) -> None:
    if destino.archived:
        raise ApiError(409, "conflict", "Este destino está arquivado")
    if destino.estado != DestinoEstado.pendente:
        raise ApiError(409, "conflict", "Só dá para pedir aprovação de um destino pendente")
    info = _conteudo_info(db, destino.conteudo_id)
    _check_pronto(info)
    conta = db.get(Conta, destino.conta_id)
    assert conta is not None
    before = history.snapshot(destino)
    destino.estado = DestinoEstado.aprovacao_pedida
    destino.pedido_por = actor.user_id
    destino.pedido_em = datetime.now(UTC)
    destino.pedido_nota = (nota or "").strip() or None
    _record(db, actor, destino, "updated", before, details)
    _avisar_pedido(db, actor, destino, info.conteudo, conta)


def pedir_aprovacao(db: Session, actor: Actor, destino_id: uuid.UUID, version: int,
                    nota: str | None) -> Postagem:
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, DESTINO_LABEL)
    _pedir(db, actor, destino, nota, {"acao": "aprovacao_pedida"})
    db.flush()
    return destino


def _aprovar(db: Session, actor: Actor, destino: Postagem, info: _ConteudoInfo,
             details: dict[str, Any]) -> None:
    """`pendente|aprovacao_pedida → aprovado` (só dono: a rota ou o `agendar` conferem)."""
    if destino.archived:
        raise ApiError(409, "conflict", "Este destino está arquivado")
    if destino.estado not in (DestinoEstado.pendente, DestinoEstado.aprovacao_pedida):
        raise ApiError(409, "conflict", "Este destino já está aprovado")
    _check_pronto(info)
    conta = db.get(Conta, destino.conta_id)
    assert conta is not None
    pedido_por = destino.pedido_por if destino.estado == DestinoEstado.aprovacao_pedida \
        else None
    before = history.snapshot(destino)
    destino.estado = DestinoEstado.aprovado
    destino.aprovado_por = actor.user_id
    destino.aprovado_em = datetime.now(UTC)
    destino.aprovado_video_ref = info.video_ref
    destino.pedido_por = destino.pedido_em = destino.pedido_nota = None
    destino.recusado_por = destino.recusado_em = destino.recusa_motivo = None
    _record(db, actor, destino, "updated", before, details)
    _avisar_resposta(db, actor, destino, info.conteudo, conta, pedido_por, aprovou=True)


def aprovar(db: Session, actor: Actor, destino_id: uuid.UUID, version: int) -> Postagem:
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, DESTINO_LABEL)
    _aprovar(db, actor, destino, _conteudo_info(db, destino.conteudo_id), {"acao": "aprovado"})
    db.flush()
    return destino


def recusar(db: Session, actor: Actor, destino_id: uuid.UUID, version: int,
            motivo: str) -> Postagem:
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, DESTINO_LABEL)
    if destino.archived:
        raise ApiError(409, "conflict", "Este destino está arquivado")
    if destino.estado == DestinoEstado.agendado:
        raise ApiError(409, "conflict", "Cancele o agendamento antes de recusar")
    if destino.estado not in (DestinoEstado.aprovacao_pedida, DestinoEstado.aprovado):
        raise ApiError(409, "conflict", "Só dá para recusar um pedido ou uma aprovação")
    motivo = motivo.strip()
    if not motivo:
        raise _invalid("Informe o motivo da recusa")
    conteudo = db.get(Conteudo, destino.conteudo_id)
    conta = db.get(Conta, destino.conta_id)
    assert conteudo is not None and conta is not None
    pedido_por = destino.pedido_por
    before = history.snapshot(destino)
    destino.estado = DestinoEstado.pendente
    destino.aprovado_por = destino.aprovado_em = destino.aprovado_video_ref = None
    destino.pedido_por = destino.pedido_em = destino.pedido_nota = None
    destino.recusado_por = actor.user_id
    destino.recusado_em = datetime.now(UTC)
    destino.recusa_motivo = motivo
    _record(db, actor, destino, "updated", before, {"acao": "recusado"})
    _avisar_resposta(db, actor, destino, conteudo, conta, pedido_por, aprovou=False)
    db.flush()
    return destino


def archive_destino(db: Session, actor: Actor, destino_id: uuid.UUID, version: int) -> Postagem:
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, DESTINO_LABEL)
    if destino.archived:
        raise ApiError(409, "conflict", "Este destino já está arquivado")
    check_sem_envio(destino)
    if destino.estado == DestinoEstado.agendado and automatico(destino.modo):
        exigir_humano(actor, "POST /api/destinos/{id}/archive", destino)  # arquivar cancela
    before = history.snapshot(destino)
    destino.archived_at = datetime.now(UTC)
    destino.archived_by = actor.user_id
    _record(db, actor, destino, "archived", before)
    db.flush()
    return destino


def restore_destino(db: Session, actor: Actor, destino_id: uuid.UUID, version: int) -> Postagem:
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, DESTINO_LABEL)
    if not destino.archived:
        raise ApiError(409, "conflict", "Este destino não está arquivado")
    outro = _destino_ativo(db, destino.conteudo_id, destino.conta_id)
    if outro is not None:
        raise _destino_exists()
    before = history.snapshot(destino)
    destino.archived_at = None
    destino.archived_by = None
    _record(db, actor, destino, "restored", before)
    _flush_destino(db)
    return destino


def revert_destino(db: Session, actor: Actor, destino_id: uuid.UUID, version: int,
                   to_version: int) -> Postagem:
    """Só o dono (rota). Volta textos, modo, data e arquivamento. Nunca desfaz nem refaz
    `postado` e **nunca restaura uma aprovação**: a data da versão alvo só volta se o destino
    está aprovado hoje (a reversão de aprovação é recusar ou aprovar de novo). Versões da 006
    não têm os campos novos: valem os padrões (`modo = lembrete`)."""
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, DESTINO_LABEL)
    check_sem_envio(destino)
    if destino.estado == DestinoEstado.postado:
        raise ApiError(409, "conflict", "Este destino já foi marcado como postado")
    if automatico(destino.modo):
        exigir_humano(actor, "POST /api/destinos/{id}/revert", destino)
    state = target_state(db, ENTITY, destino, to_version)
    before = history.snapshot(destino)

    # Uma versão `created` gravada antes do flush tem os textos nulos (os padrões do banco):
    # nulo vale como "sem mudança".
    if state.get("titulo") is not None:
        destino.titulo = state["titulo"]
    if state.get("descricao") is not None:
        destino.descricao = state["descricao"]
    if state.get("hashtags") is not None:
        destino.hashtags = list(state["hashtags"])
    planned = state.get("planned_at")
    alvo_modo = Modo(state.get("modo") or Modo.lembrete.value)
    # 015: a reversão nunca restaura estados de execução nem um agendamento automático (com o
    # snapshot do envio): reagendar é o caminho. Um automático agendado mantém a agenda.
    agendar_alvo = state.get("estado") == DestinoEstado.agendado.value and planned is not None \
        and not automatico(alvo_modo)
    mantem_agenda = destino.estado == DestinoEstado.agendado and automatico(destino.modo)
    if destino.estado in EDITAVEIS_POSTADO and not mantem_agenda:
        destino.modo = alvo_modo if not automatico(alvo_modo) else Modo.lembrete
        destino.antecedencia_min = state.get("antecedencia_min") \
            if destino.modo == Modo.rascunho_e_publicar else None
        destino.envio_snapshot = None
        destino.opcoes_rede = None
        if agendar_alvo:
            novo = _planned(datetime.fromisoformat(planned))
            if destino.planned_at != novo:
                destino.lembrado_em = None
            destino.estado = DestinoEstado.agendado
            destino.planned_at = novo
        else:
            destino.estado = DestinoEstado.aprovado
            destino.planned_at = None
            destino.lembrado_em = None
    apply_archived(destino, state.get("archived", destino.archived), actor)

    after = history.snapshot(destino)
    if after == before:
        raise _invalid("Essa versão é igual à atual")
    if not destino.archived and _destino_ativo(db, destino.conteudo_id, destino.conta_id) \
            not in (None, destino):
        raise _destino_exists()
    _record(db, actor, destino, "reverted", before, {"from_version": to_version})
    _flush_destino(db)
    return destino


# ---- agendamento (R6) ----

def _conexao(db: Session, conta: Conta):
    """A conexão viva da conta (camada 3 das capacidades, 015)."""
    from sociman_api.publicacao import conexoes  # import tardio (ciclo)

    return conexoes.conexao_viva(db, conta.id)


def _check_modo(db: Session, conta: Conta, modo: Modo, antecedencia_min: int | None) -> None:
    """Conta em atenção (409 `conta_em_atencao`), modo indisponível (409 `modo_indisponivel`,
    com o motivo). Na 014 só `lembrete` passa (princípio I)."""
    motivo = capacidades.motivo_atencao(conta)
    if motivo is not None:
        raise ApiError(409, "conta_em_atencao", f"{motivo}: nada é agendado para ela",
                       details={"motivo": motivo})
    info = capacidades.modo_info(conta, modo, _conexao(db, conta))
    if not info.disponivel:
        raise ApiError(409, "modo_indisponivel", info.motivo or "Modo indisponível",
                       details={"motivo": info.motivo})
    if antecedencia_min is not None and modo != Modo.rascunho_e_publicar:
        raise _invalid("A antecedência só vale para \"rascunho antes, publicar no horário\"")


def _ocupados(db: Session, conta: Conta, excluir: Iterable[uuid.UUID] = (),
              de: datetime | None = None, ate: datetime | None = None
              ) -> list[tuple[datetime, schemas.ConflitoIntervalo]]:
    """Os agendamentos ativos da conta (`ix_postagens_conta_agenda`), menos `excluir`."""
    query = (
        select(Postagem.id, Postagem.conteudo_id, Postagem.planned_at, Postagem.titulo,
               Conteudo.titulo)
        .join(Conteudo, Conteudo.id == Postagem.conteudo_id)
        .where(Postagem.conta_id == conta.id, Postagem.archived_at.is_(None),
               Postagem.estado == DestinoEstado.agendado)
        .order_by(Postagem.planned_at, Postagem.id)
    )
    excluir = list(excluir)
    if excluir:
        query = query.where(Postagem.id.notin_(excluir))
    if de is not None:
        query = query.where(Postagem.planned_at > de)
    if ate is not None:
        query = query.where(Postagem.planned_at < ate)
    tz = app_tz()
    with db.no_autoflush:
        rows = db.execute(query).all()
    return [(planned, schemas.ConflitoIntervalo(
        destino_id=i, conteudo_id=cid, titulo=t or tc or "",
        planned_at=planned.astimezone(tz))) for i, cid, planned, t, tc in rows]


def _intervalo_conflito(conta: Conta, conflitos: list[schemas.ConflitoIntervalo]) -> ApiError:
    primeiro = conflitos[0]
    hora = primeiro.planned_at.strftime("%d/%m %H:%M")
    return ApiError(
        409, "intervalo_conflito",
        f"Há outro post em @{conta.handle} às {hora}; o intervalo mínimo é "
        f"{conta.intervalo_min_minutos} min",
        details={"intervaloMin": conta.intervalo_min_minutos,
                 "conflitos": [c.model_dump(mode="json", by_alias=True) for c in conflitos]},
    )


def _conflitos(db: Session, conta: Conta, destino_id: uuid.UUID | None,
               planned_at: datetime) -> list[schemas.ConflitoIntervalo]:
    janela = sequencia.janela(conta.intervalo_min_minutos)
    ocupados = _ocupados(db, conta, [destino_id] if destino_id else [],
                         planned_at - janela, planned_at + janela)
    return sequencia.conflitos(planned_at, ocupados, conta.intervalo_min_minutos)


def _agendar_destino(destino: Postagem, planned_at: datetime, modo: Modo,
                     antecedencia_min: int | None) -> None:
    if destino.planned_at != planned_at:
        destino.lembrado_em = None  # a "Hora de postar" vale para o horário novo
    destino.estado = DestinoEstado.agendado
    destino.planned_at = planned_at
    destino.modo = modo
    destino.antecedencia_min = antecedencia_min


def agendar(db: Session, actor: Actor, body: schemas.AgendarIn,
            extra: dict[str, Any] | None = None) -> tuple[Postagem, bool]:
    """Agendar direto (FR-005, FR-010). Cria o destino se faltar; num destino não aprovado, um
    dono aprova no mesmo passo (duas versões: `aprovado` e `agendado`) e um membro recebe 403
    `aprovacao_necessaria`. Tudo é conferido antes de gravar. Devolve (destino, criou)."""
    info = _conteudo_info(db, body.conteudo_id)
    conta = _conta_do_conteudo(db, info.conteudo, body.conta_id)
    destino = _destino_ativo(db, info.conteudo.id, conta.id, lock=True)
    if automatico(body.modo, destino.modo if destino is not None else None):
        exigir_humano(actor, "POST /api/agendamentos", destino, conta_id=conta.id)
    _check_modo(db, conta, body.modo, body.antecedencia_min)
    opcoes = resolver_opcoes(conta, body.modo, body.opcoes, destino)
    _exigir_legenda(conta, destino, body.textos)
    if info.arquivado:
        raise ApiError(409, "conflict", "Este conteúdo está arquivado")
    if destino is not None:
        if body.destino_version is not None:
            history.check_version(destino, body.destino_version, DESTINO_LABEL)
        check_sem_envio(destino)
        if destino.estado == DestinoEstado.postado:
            raise ApiError(409, "conflict", "Este destino já foi marcado como postado")
        if destino.estado in JA_SAIU:
            raise ApiError(409, "conflict", "Este destino já foi enviado à rede")
        if destino.estado == DestinoEstado.falhou:
            _confirmar_incerta(destino, body.confirmo_que_nao_chegou)
    aprovado = destino is not None and destino.estado in AGENDAVEIS
    if not aprovado and not _is_dono(actor):
        raise ApiError(403, "aprovacao_necessaria", "Peça aprovação a um dono")
    if not aprovado:
        _check_pronto(info)
    planned_at = _planned(body.planned_at)
    conflitos = _conflitos(db, conta, destino.id if destino else None, planned_at)
    if conflitos and not body.ignorar_intervalo:
        raise _intervalo_conflito(conta, conflitos)

    criou = destino is None
    if destino is None:
        destino = Postagem(id=uuid.uuid4(), conteudo_id=info.conteudo.id, conta_id=conta.id,
                           estado=DestinoEstado.pendente, modo=Modo.lembrete,
                           created_by=actor.user_id, updated_by=actor.user_id)
        _preencher_proposta(db, destino)
        db.add(destino)
        history.record(db, actor, ENTITY, destino, "created", None, history.snapshot(destino))
        _flush_destino(db)
    if not aprovado:
        _aprovar(db, actor, destino, info, {"acao": "aprovado"})

    before = history.snapshot(destino)
    textos = body.textos
    if textos is not None:
        _aplicar_textos(destino, textos.titulo, textos.descricao, textos.hashtags)
        if criou:  # texto vazio no destino novo fica com a proposta (T074)
            _preencher_proposta(db, destino)
    _agendar_destino(destino, planned_at, body.modo, body.antecedencia_min)
    _marcar_decisao(destino, actor, info.video_ref, opcoes)
    after = history.snapshot(destino)
    details: dict[str, Any] = {"acao": "agendado", **(extra or {})}
    if conflitos:
        details["intervaloIgnorado"] = True
    ia = _marcar_ia_destino(db, actor, destino, info.conteudo, conta, before, after, body.ia)
    if ia is not None:
        details.update(ia)
    _record(db, actor, destino, "updated", before, details)
    _flush_destino(db)
    return destino, criou


SEM_CONEXAO = "Conecte (ou reconecte) a conta antes de enviar"
PAUSADO = ("Envios automáticos desligados: o envio fica pausado até ligar o interruptor "
           "(e, depois de 1 hora, pede confirmação)")


def enviar_agora(db: Session, actor: Actor, destino_id: uuid.UUID,
                 body: schemas.EnviarAgoraIn) -> tuple[Postagem, str | None]:
    """"Enviar agora" (emenda do dono, T099): aprova se preciso e agenda com `planned_at =
    agora` no modo automático, com as mesmas validações do agendar (dono humano, capacidade,
    conexão, `incerta` exige "conferi no app", `enviando` → 409). A trilha reivindica na volta
    seguinte (dentro da janela de 1 h). O interruptor desligado não bloqueia: o destino fica
    `pausado` e a resposta traz o aviso. Devolve (destino, aviso)."""
    from sociman_api.publicacao import conexoes, trilha  # import tardio (ciclo)

    if not automatico(body.modo):
        raise _invalid("Enviar agora é só para os modos automáticos")
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, body.version, DESTINO_LABEL)
    exigir_humano(actor, "POST /api/destinos/{id}/enviar-agora", destino)
    check_sem_envio(destino)
    if destino.archived:
        raise ApiError(409, "conflict", "Este destino está arquivado")
    conexao = conexoes.conexao_viva(db, destino.conta_id)
    if conexao is None or conexao.estado.value != "conectada":
        raise ApiError(409, "conta_nao_conectada", SEM_CONEXAO)
    pedido = schemas.AgendarIn(
        conteudo_id=destino.conteudo_id, conta_id=destino.conta_id,
        planned_at=datetime.now(UTC), modo=body.modo, destino_version=body.version,
        confirmo_que_nao_chegou=body.conferi_no_app, ignorar_intervalo=True,
        opcoes=body.opcoes)
    destino, _ = agendar(db, actor, pedido, extra={"disparo": "agora"})
    aviso = None if trilha.pode_enviar(db) else PAUSADO
    return destino, aviso


def reagendar(db: Session, actor: Actor, destino_id: uuid.UUID,
              body: schemas.ReagendarIn) -> Postagem:
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, body.version, DESTINO_LABEL)
    _reagendar(db, actor, destino, body.planned_at, body.modo, body.antecedencia_min,
               "antecedencia_min" in body.model_fields_set, body.ignorar_intervalo,
               {"acao": "reagendado"}, ocupados=None, confirmo=body.confirmo_que_nao_chegou,
               opcoes_in=body.opcoes)
    db.flush()
    return destino


def _reagendar(db: Session, actor: Actor, destino: Postagem, planned_at: datetime | None,
               modo: Modo | None, antecedencia_min: int | None, muda_antecedencia: bool,
               ignorar: bool, details: dict[str, Any],
               ocupados: list[tuple[datetime, schemas.ConflitoIntervalo]] | None,
               confirmo: bool | None = None, opcoes_in: OpcoesTikTok | None = None) -> None:
    """`ocupados` (lote): os horários contra os quais conferir, já no estado final do lote.
    015: aceita `falhou` (volta a `agendado`, com nova data e, se incerto, a confirmação)."""
    check_sem_envio(destino)
    if destino.archived or destino.estado not in REAGENDAVEIS:
        raise ApiError(409, "nao_aprovado", "Este destino não está agendado")
    conta = db.get(Conta, destino.conta_id)
    assert conta is not None
    novo_modo = modo or destino.modo
    if automatico(novo_modo, destino.modo):
        exigir_humano(actor, "PATCH /api/destinos/{id}/agendamento", destino)
    nova_antecedencia = antecedencia_min if muda_antecedencia else destino.antecedencia_min
    _check_modo(db, conta, novo_modo, nova_antecedencia)
    opcoes = resolver_opcoes(conta, novo_modo, opcoes_in, destino)
    legenda.exigir(conta.platform, destino)
    falhou = destino.estado == DestinoEstado.falhou
    if falhou:
        if planned_at is None:
            raise _invalid("Escolha o novo horário")
        _confirmar_incerta(destino, confirmo)
    novo = _planned(planned_at) if planned_at is not None else destino.planned_at
    assert novo is not None
    if novo != destino.planned_at:
        if ocupados is None:
            conflitos = _conflitos(db, conta, destino.id, novo)
        else:
            conflitos = sequencia.conflitos(novo, ocupados, conta.intervalo_min_minutos)
        if conflitos and not ignorar:
            raise _intervalo_conflito(conta, conflitos)
        if conflitos:
            details = {**details, "intervaloIgnorado": True}
    before = history.snapshot(destino)
    _agendar_destino(destino, novo, novo_modo, nova_antecedencia)
    if not falhou and opcoes_in is None and not history.diff(before, history.snapshot(destino)):
        return
    _marcar_decisao(destino, actor, _conteudo_info(db, destino.conteudo_id).video_ref, opcoes)
    _record(db, actor, destino, "updated", before, details)


def _cancelar(db: Session, actor: Actor, destino: Postagem, details: dict[str, Any],
              rota: str = "POST /api/destinos/{id}/agendamento/cancelar") -> None:
    """`agendado` (ou `falhou`, 015) → `aprovado`, sem data. Modo automático: só dono
    humano."""
    check_sem_envio(destino)
    if destino.archived or destino.estado not in REAGENDAVEIS:
        raise ApiError(409, "conflict", "Este destino não está agendado")
    if automatico(destino.modo):
        exigir_humano(actor, rota, destino)
    before = history.snapshot(destino)
    destino.estado = DestinoEstado.aprovado
    destino.planned_at = None
    destino.lembrado_em = None
    destino.modo = Modo.lembrete
    destino.antecedencia_min = None
    destino.envio_snapshot = None
    destino.opcoes_rede = None
    destino.falha_incerta = False
    _record(db, actor, destino, "updated", before, details)


def cancelar_agendamento(db: Session, actor: Actor, destino_id: uuid.UUID,
                         version: int) -> Postagem:
    destino = get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, DESTINO_LABEL)
    _cancelar(db, actor, destino, {"acao": "agendamento_cancelado"})
    db.flush()
    return destino


def checar_arquivo(db: Session, actor: Actor, conteudo_id: uuid.UUID, rota: str) -> None:
    """Antes de arquivar um conteúdo ou corte (015): com um destino `enviando`, 409
    `envio_em_andamento`; com um automático `agendado` (arquivar cancela), só dono humano."""
    rows = db.execute(
        select(Postagem.id, Postagem.estado, Postagem.modo, Postagem.conta_id)
        .where(Postagem.conteudo_id == conteudo_id, Postagem.archived_at.is_(None),
               Postagem.estado.in_([DestinoEstado.agendado, DestinoEstado.enviando]))
        .order_by(Postagem.id)
    ).all()
    if any(r.estado == DestinoEstado.enviando for r in rows):
        raise ApiError(409, "envio_em_andamento", EM_ANDAMENTO)
    auto = [r for r in rows if automatico(r.modo)]
    if auto:
        from sociman_api.publicacao.service import exigir_humano_dono  # import tardio (ciclo)

        exigir_humano_dono(actor, rota, conta_id=auto[0].conta_id, destino_id=auto[0].id)


def cancelar_por_arquivo(db: Session, actor: Actor, conteudo_id: uuid.UUID) -> int:
    """Arquivar o conteúdo (ou o corte) cancela os agendamentos ativos dele, na mesma
    transação, com uma versão `cancelado_por_arquivo` por destino (edge case). Restaurar não
    reagenda. Devolve quantos cancelou."""
    destinos = list(db.scalars(
        select(Postagem).where(Postagem.conteudo_id == conteudo_id,
                               Postagem.archived_at.is_(None),
                               Postagem.estado == DestinoEstado.agendado)
        .order_by(Postagem.id).with_for_update()
    ))
    for destino in destinos:
        _cancelar(db, actor, destino, {"acao": "cancelado_por_arquivo"},
                  rota="arquivar (cancela o agendamento)")
    db.flush()
    return len(destinos)


# ---- lote (R5, R6) ----

def _falha(exc: ApiError, conteudo_id: uuid.UUID | None = None,
           destino_id: uuid.UUID | None = None) -> schemas.LoteFalha:
    return schemas.LoteFalha(conteudo_id=conteudo_id, destino_id=destino_id, code=exc.code,
                             message=exc.message)


def _lote_details(lote_id: uuid.UUID, acao: str) -> dict[str, Any]:
    return {"acao": "lote", "loteId": str(lote_id), "loteAcao": acao}


def _conta_lote(db: Session, conta_id: uuid.UUID) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise _conta_invalida("Conta não encontrada")
    if conta.archived:
        raise _conta_invalida("Esta conta está arquivada")
    return conta


def _lote_destinos(db: Session, actor: Actor, conta: Conta, conteudo_ids: Sequence[uuid.UUID],
                   acao: str, aplicar) -> schemas.LoteResultado:
    """Aprovar/pedir em lote: cria o destino que faltar, trava em ordem de id e processa cada
    item num SAVEPOINT (um item ruim não desfaz os outros)."""
    lote_id = uuid.uuid4()
    ok: list[Postagem] = []
    falhas: list[schemas.LoteFalha] = []
    vistos: set[uuid.UUID] = set()
    for conteudo_id in sorted(dict.fromkeys(conteudo_ids)):
        if conteudo_id in vistos:
            continue
        vistos.add(conteudo_id)
        try:
            with db.begin_nested():
                info = _conteudo_info(db, conteudo_id)
                if info.conteudo.perfil_id != conta.perfil_id:
                    raise _conta_invalida("A conta de destino precisa ser do perfil do conteúdo")
                if info.arquivado:
                    raise ApiError(409, "conflict", "Este conteúdo está arquivado")
                destino = _destino_ativo(db, conteudo_id, conta.id, lock=True)
                if destino is None:
                    destino = Postagem(id=uuid.uuid4(), conteudo_id=conteudo_id,
                                       conta_id=conta.id, estado=DestinoEstado.pendente,
                                       modo=Modo.lembrete, created_by=actor.user_id,
                                       updated_by=actor.user_id)
                    _preencher_proposta(db, destino)
                    db.add(destino)
                    history.record(db, actor, ENTITY, destino, "created", None,
                                   history.snapshot(destino), {"loteId": str(lote_id)})
                    db.flush()
                aplicar(destino, info, _lote_details(lote_id, acao))
                db.flush()
            ok.append(destino)
        except ApiError as exc:
            falhas.append(_falha(exc, conteudo_id=conteudo_id))
        except IntegrityError:
            falhas.append(_falha(_destino_exists(), conteudo_id=conteudo_id))
    ordem = {cid: n for n, cid in enumerate(dict.fromkeys(conteudo_ids))}
    ok.sort(key=lambda d: ordem[d.conteudo_id])
    return schemas.LoteResultado(ok=destinos_out(db, ok), falhas=falhas)


def lote_aprovar(db: Session, actor: Actor, body: schemas.LoteAprovarIn) -> schemas.LoteResultado:
    conta = _conta_lote(db, body.conta_id)

    def aplicar(destino: Postagem, info: _ConteudoInfo, details: dict[str, Any]) -> None:
        if destino.estado in DEPOIS_DA_APROVACAO:
            return  # já aprovado: entra em `ok` sem versão nova
        _aprovar(db, actor, destino, info, details)

    return _lote_destinos(db, actor, conta, body.conteudo_ids, "aprovado", aplicar)


def lote_pedir_aprovacao(db: Session, actor: Actor,
                         body: schemas.LotePedirIn) -> schemas.LoteResultado:
    conta = _conta_lote(db, body.conta_id)

    def aplicar(destino: Postagem, info: _ConteudoInfo, details: dict[str, Any]) -> None:
        _pedir(db, actor, destino, body.nota, details)

    return _lote_destinos(db, actor, conta, body.conteudo_ids, "aprovacao_pedida", aplicar)


def _travar(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Postagem]:
    rows = db.scalars(select(Postagem).where(Postagem.id.in_(list(set(ids))))
                      .order_by(Postagem.id).with_for_update())
    return {d.id: d for d in rows}


def lote_reagendar(db: Session, actor: Actor,
                   body: schemas.LoteReagendarIn) -> schemas.LoteResultado:
    """Arrastar no calendário e "Trocar horários". O intervalo é conferido contra o estado
    final do lote: os itens que passam das pré-condições já contam no horário novo (trocar os
    horários de dois itens da mesma conta não conflita entre eles)."""
    lote_id = uuid.uuid4()
    destinos = _travar(db, [i.destino_id for i in body.itens])
    falhas: list[schemas.LoteFalha] = []
    validos: list[tuple[schemas.LoteReagendarItem, Postagem, datetime]] = []
    for item in body.itens:
        destino = destinos.get(item.destino_id)
        try:
            if destino is None:
                raise ApiError(404, "not_found", DESTINO_NOT_FOUND)
            history.check_version(destino, item.version, DESTINO_LABEL)
            check_sem_envio(destino)
            if destino.archived or destino.estado not in REAGENDAVEIS:
                raise ApiError(409, "nao_aprovado", "Este destino não está agendado")
            validos.append((item, destino, _planned(item.planned_at)))
        except ApiError as exc:
            falhas.append(_falha(exc, destino_id=item.destino_id))

    movidos = {d.id for _, d, _ in validos}
    contas = {c.id: c for c in db.scalars(
        select(Conta).where(Conta.id.in_({d.conta_id for _, d, _ in validos})))}
    base = {cid: _ocupados(db, conta, movidos) for cid, conta in contas.items()}
    ok: list[Postagem] = []
    for item, destino, novo in validos:
        conta = contas[destino.conta_id]
        outros = [(n, schemas.ConflitoIntervalo(
            destino_id=d.id, conteudo_id=d.conteudo_id, titulo=d.titulo,
            planned_at=n.astimezone(app_tz())))
            for _, d, n in validos if d.id != destino.id and d.conta_id == conta.id]
        try:
            with db.begin_nested():
                _reagendar(db, actor, destino, novo, None, None, False, body.ignorar_intervalo,
                           _lote_details(lote_id, "reagendado"),
                           ocupados=base[conta.id] + outros,
                           confirmo=item.confirmo_que_nao_chegou)
                db.flush()
            ok.append(destino)
        except ApiError as exc:
            falhas.append(_falha(exc, destino_id=destino.id))
    return schemas.LoteResultado(ok=destinos_out(db, ok), falhas=falhas)


def lote_cancelar(db: Session, actor: Actor,
                  body: schemas.LoteCancelarIn) -> schemas.LoteResultado:
    lote_id = uuid.uuid4()
    destinos = _travar(db, [i.destino_id for i in body.itens])
    ok: list[Postagem] = []
    falhas: list[schemas.LoteFalha] = []
    for item in body.itens:
        destino = destinos.get(item.destino_id)
        try:
            if destino is None:
                raise ApiError(404, "not_found", DESTINO_NOT_FOUND)
            with db.begin_nested():
                history.check_version(destino, item.version, DESTINO_LABEL)
                _cancelar(db, actor, destino, _lote_details(lote_id, "agendamento_cancelado"),
                          rota="POST /api/agendamentos/lote/cancelar")
                db.flush()
            ok.append(destino)
        except ApiError as exc:
            falhas.append(_falha(exc, destino_id=item.destino_id))
    return schemas.LoteResultado(ok=destinos_out(db, ok), falhas=falhas)


# ---- sequência (R7, US4) ----

@dataclass
class _Plano:
    conta: Conta
    previa: schemas.Previa
    elegiveis: dict[uuid.UUID, tuple[_ConteudoInfo, Postagem | None]]


def _planejar(db: Session, actor: Actor, body: schemas.SequenciaIn, lock: bool) -> _Plano:
    conta = _conta_lote(db, body.conta_id)
    if automatico(body.modo):
        exigir_humano(actor, "POST /api/agendamentos/sequencia", conta_id=conta.id)
    if body.modo == Modo.publicar:
        raise ApiError(409, "modo_indisponivel", PUBLICAR_EM_LOTE,
                       details={"motivo": PUBLICAR_EM_LOTE})
    _check_modo(db, conta, body.modo, None)
    tz = app_tz()
    hoje = datetime.now(tz).date()
    if body.inicio < hoje:
        raise _invalid("A primeira data já passou")
    if (body.inicio - hoje).days > sequencia.DIAS_MAX:
        raise _invalid(f"A sequência começa em até {sequencia.DIAS_MAX} dias")
    horarios = [time.fromisoformat(h) for h in body.horarios]
    if len(set(horarios)) != len(horarios):
        raise _invalid("Horário repetido")

    inelegiveis: list[schemas.Inelegivel] = []
    elegiveis: dict[uuid.UUID, tuple[_ConteudoInfo, Postagem | None]] = {}
    for conteudo_id in dict.fromkeys(body.conteudo_ids):
        try:
            info = _conteudo_info(db, conteudo_id)
            if info.conteudo.perfil_id != conta.perfil_id:
                raise _conta_invalida("A conta de destino precisa ser do perfil do conteúdo")
            if info.arquivado:
                raise ApiError(409, "conflict", "Este conteúdo está arquivado")
            destino = _destino_ativo(db, conteudo_id, conta.id, lock=lock)
            if destino is not None and destino.estado == DestinoEstado.postado:
                raise ApiError(409, "conflict", "Este destino já foi marcado como postado")
            if destino is not None and destino.estado == DestinoEstado.agendado:
                raise ApiError(409, "conflict", "Este conteúdo já está agendado nesta conta")
            if destino is not None and destino.estado not in (DestinoEstado.pendente,
                                                              DestinoEstado.aprovacao_pedida,
                                                              DestinoEstado.aprovado):
                raise ApiError(409, "conflict", "Este destino já foi enviado ou está em envio")
            if not body.gerar_textos:  # T101: sem legenda, pula (a IA escreve depois, se marcada)
                legenda.exigir(conta.platform, destino or _TextosEfetivos("", []))
            aprovado = destino is not None and destino.estado == DestinoEstado.aprovado
            if not aprovado:
                if not _is_dono(actor):
                    raise ApiError(403, "aprovacao_necessaria", "Peça aprovação a um dono")
                _check_pronto(info)
            elegiveis[conteudo_id] = (info, destino)
        except ApiError as exc:
            inelegiveis.append(schemas.Inelegivel(conteudo_id=conteudo_id, code=exc.code,
                                                  message=exc.message))

    if lock:  # as linhas da agenda da conta ficam travadas até o fim da transação
        db.execute(select(Postagem.id).where(
            Postagem.conta_id == conta.id, Postagem.archived_at.is_(None),
            Postagem.estado == DestinoEstado.agendado).with_for_update())
    ocupados = [(quando, c.destino_id) for quando, c in _ocupados(db, conta)]
    slots, pulados = sequencia.planejar(list(elegiveis), body.inicio, horarios, ocupados,
                                        datetime.now(tz), conta.intervalo_min_minutos, tz)
    for conteudo_id in list(elegiveis)[len(slots):]:  # não couberam no horizonte
        inelegiveis.append(schemas.Inelegivel(
            conteudo_id=conteudo_id, code="sem_horario",
            message=f"Sem horário livre em {sequencia.DIAS_MAX} dias"))
        elegiveis.pop(conteudo_id)
    previa = schemas.Previa(
        intervalo_min=conta.intervalo_min_minutos,
        slots=[schemas.SlotSequencia(conteudo_id=s.item, planned_at=s.planned_at)
               for s in slots],
        pulados=[schemas.Pulado(planned_at=p.planned_at, motivo=p.motivo, destino_id=p.ocupante)
                 for p in pulados],
        inelegiveis=inelegiveis,
    )
    return _Plano(conta, previa, elegiveis)


def sequencia_previa(db: Session, actor: Actor, body: schemas.SequenciaIn) -> schemas.Previa:
    """Não grava nada."""
    return _planejar(db, actor, body, lock=False).previa


def _mesmos_slots(a: Sequence[schemas.SlotSequencia],
                  b: Sequence[schemas.SlotSequencia]) -> bool:
    return [(s.conteudo_id, s.planned_at) for s in a] == \
        [(s.conteudo_id, s.planned_at) for s in b]


def aplicar_sequencia(db: Session, actor: Actor,
                      body: schemas.SequenciaConfirmarIn) -> schemas.LoteResultado:
    """Recalcula com as linhas travadas; se a prévia mudou, 409 `previa_desatualizada` com a
    nova. Senão aplica item a item (SAVEPOINT): o dono aprova e agenda no mesmo passo."""
    plano = _planejar(db, actor, body, lock=True)
    if not _mesmos_slots(plano.previa.slots, body.esperado):
        raise ApiError(409, "previa_desatualizada", "A prévia mudou; confira de novo",
                       details={"previa": plano.previa.model_dump(mode="json", by_alias=True)})
    lote_id = uuid.uuid4()
    ok: list[Postagem] = []
    falhas: list[schemas.LoteFalha] = []
    for slot in plano.previa.slots:
        info, destino = plano.elegiveis[slot.conteudo_id]
        try:
            with db.begin_nested():
                if destino is None:
                    destino = Postagem(id=uuid.uuid4(), conteudo_id=slot.conteudo_id,
                                       conta_id=plano.conta.id, estado=DestinoEstado.pendente,
                                       modo=Modo.lembrete, created_by=actor.user_id,
                                       updated_by=actor.user_id)
                    _preencher_proposta(db, destino)
                    db.add(destino)
                    history.record(db, actor, ENTITY, destino, "created", None,
                                   history.snapshot(destino), {"loteId": str(lote_id)})
                    db.flush()
                if destino.estado != DestinoEstado.aprovado:
                    _aprovar(db, actor, destino, info, _lote_details(lote_id, "aprovado"))
                before = history.snapshot(destino)
                _agendar_destino(destino, slot.planned_at, body.modo, None)
                _marcar_decisao(destino, actor, info.video_ref)
                _record(db, actor, destino, "updated", before,
                        _lote_details(lote_id, "agendado"))
                db.flush()
            ok.append(destino)
        except ApiError as exc:
            falhas.append(_falha(exc, conteudo_id=slot.conteudo_id))
        except IntegrityError:
            falhas.append(_falha(_destino_exists(), conteudo_id=slot.conteudo_id))
    return schemas.LoteResultado(ok=destinos_out(db, ok), falhas=falhas)
