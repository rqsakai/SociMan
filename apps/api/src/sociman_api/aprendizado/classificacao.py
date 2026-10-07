"""Classificação dos posts (spec 023, US1; FR-003 a FR-007; research R5).

- **Pendente** (data-model): vídeo de série viva de uma conta do perfil, com ≥ 24 h, disponível,
  sem classificação ou marcado para reclassificar com `origem = ia`;
- **Dono:** `corrigir` grava `origem = dono` (PUT com `version`, 0 se nova) e `reverter` volta a
  uma versão (pode voltar a `ia`). A IA nunca sobrescreve uma linha do dono (`pode_a_ia`);
- **IA:** `classificar_um` monta a entrada (legenda, hashtags, gancho e transcrição até 4.000
  caracteres; sem corte, "evidência parcial"), chama o Claude pelo registro da 008 e grava como
  `system:aprendizado`. Tema fora da taxonomia vira "Sem tema" com a sugestão guardada.
"""

import base64
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from sociman_api import history
from sociman_api.analytics import base, filtros
from sociman_api.aprendizado import chamada as chamada_mod
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import preferencias as prefs
from sociman_api.aprendizado import schemas
from sociman_api.aprendizado.models import Classificacao, EstiloGancho, Origem, Tema
from sociman_api.auth.deps import Actor
from sociman_api.conteudos.models import Conteudo
from sociman_api.cortes.models import Corte
from sociman_api.errors import ApiError
from sociman_api.ia.cliente import IaClient
from sociman_api.ia.models import IaChamada
from sociman_api.metricas.models import Serie, VideoRede
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.perfis.schemas import RevertIn, VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, target_state, versions_out
from sociman_api.postagem.models import Postagem

ENTITY = "aprendizado_classificacao"
LABEL = "Esta classificação"
TIPO = "aprendizado.classificacao"
LIMIT_PADRAO = 50
LIMIT_MAX = 100
PARAR = ("timeout", "unconfigured")  # a trilha para na volta (R4); e os 5xx/429 da IA


def indisponivel(row: IaChamada | None) -> bool:
    """A IA fora do ar (timeout, sem chave, 5xx, 429 ou sem resposta): a trilha para."""
    if row is None or row.erro_code is None:
        return False
    if row.erro_code in PARAR:
        return True
    return row.erro_code == "api_error" and (row.erro_status is None or row.erro_status >= 500
                                             or row.erro_status == 429)


# ---- consultas ----

def _videos_do_perfil(perfil_id: uuid.UUID) -> Select:
    return (select(VideoRede.id).join(Serie, Serie.id == VideoRede.serie_id)
            .join(Conta, Conta.id == Serie.conta_id)
            .where(Conta.perfil_id == perfil_id, Serie.anonimizada_em.is_(None),
                   VideoRede.anonimizado_em.is_(None)))


def _pendente_expr():
    c = aliased(Classificacao)  # a lista também junta `Classificacao`: sem auto-correlação
    sem_linha = ~select(c.id).where(c.video_id == VideoRede.id).correlate(VideoRede).exists()
    reclass = select(c.id).where(c.video_id == VideoRede.id, c.reclassificar,
                                 c.origem == Origem.ia).correlate(VideoRede).exists()
    return or_(sem_linha, reclass)


def pendentes_stmt(perfil_id: uuid.UUID, agora: datetime) -> Select:
    """Os vídeos pendentes do perfil, do mais antigo para o mais novo (a ordem da trilha)."""
    return (_videos_do_perfil(perfil_id)
            .where(VideoRede.publicado_em <= agora - K.IDADE_CLASSIFICAR, VideoRede.disponivel,
                   _pendente_expr())
            .order_by(VideoRede.publicado_em, VideoRede.id))


def n_pendentes(db: Session, perfil_id: uuid.UUID, agora: datetime | None = None) -> int:
    agora = agora or datetime.now(UTC)
    return db.scalar(select(func.count()).select_from(
        pendentes_stmt(perfil_id, agora).order_by(None).subquery())) or 0


def inicio_do_dia(agora: datetime) -> datetime:
    tz = ZoneInfo(filtros.fuso())
    return datetime.combine(agora.astimezone(tz).date(), time.min, tzinfo=tz)


def usadas_hoje(db: Session, perfil_id: uuid.UUID, agora: datetime | None = None) -> int:
    """As chamadas `aprendizado.classificacao` do dia local, inclusive as com erro (FR-051)."""
    agora = agora or datetime.now(UTC)
    return db.scalar(select(func.count()).select_from(IaChamada).where(
        IaChamada.perfil_id == perfil_id, IaChamada.tipo_campo == TIPO,
        IaChamada.created_at >= inicio_do_dia(agora))) or 0


def tem_taxonomia(db: Session, perfil_id: uuid.UUID) -> bool:
    return db.scalar(select(Tema.id).where(Tema.perfil_id == perfil_id,
                                           Tema.archived_at.is_(None)).limit(1)) is not None


# ---- saída ----

def _cursor(publicado: datetime, vid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{publicado.isoformat()}|{vid}".encode()).decode()


def _ler_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        quando, vid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(quando), uuid.UUID(vid)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(400, "validation_error", "Cursor inválido") from exc


def out(c: Classificacao | None, video_id: uuid.UUID, temas: dict[uuid.UUID, str],
        post: Any = None) -> schemas.AprendizadoClassificacao:
    if c is None:
        return schemas.AprendizadoClassificacao(
            video_id=video_id, post=post, tema_id=None, tema_nome=None, secundarios=[],
            estilo_gancho=None, justificativa=None, sugestao_tema=None, origem=None,
            evidencia_parcial=False, reclassificar=False, taxonomia_versao=None,
            chamada_id=None, version=0)
    return schemas.AprendizadoClassificacao(
        video_id=video_id, post=post, tema_id=c.tema_id,
        tema_nome=temas.get(c.tema_id) if c.tema_id else None, secundarios=list(c.secundarios),
        estilo_gancho=c.estilo_gancho.value if c.estilo_gancho else None,  # type: ignore[arg-type]
        justificativa=c.justificativa, sugestao_tema=c.sugestao_tema,
        origem=c.origem.value, evidencia_parcial=c.evidencia_parcial,  # type: ignore[arg-type]
        reclassificar=c.reclassificar, taxonomia_versao=c.taxonomia_versao,
        chamada_id=c.chamada_id, version=c.version)


def _todos_temas(db: Session, perfil_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict(db.execute(select(Tema.id, Tema.nome).where(Tema.perfil_id == perfil_id)).all())


def _resumos(db: Session, perfil_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> dict:
    filtro = filtros.montar(db, perfil_id=perfil_id)
    return {p.video_id: base.resumo(p) for p in base.posts_por_id(db, filtro, list(ids))}


def listar(db: Session, perfil_id: uuid.UUID, *, conta_id: uuid.UUID | None = None,
           tema_id: uuid.UUID | None = None, origem: str | None = None,
           pendentes: bool = False, cursor: str | None = None,
           limit: int = LIMIT_PADRAO) -> schemas.AprendizadoClassificacoesList:
    get_perfil_or_404(db, perfil_id)
    agora = datetime.now(UTC)
    stmt = (_videos_do_perfil(perfil_id).add_columns(VideoRede.publicado_em)
            .outerjoin(Classificacao, Classificacao.video_id == VideoRede.id))
    if conta_id is not None:
        stmt = stmt.where(Serie.conta_id == conta_id)
    if tema_id is not None:
        stmt = stmt.where(or_(Classificacao.tema_id == tema_id,
                              Classificacao.secundarios.contains([tema_id])))
    if origem in ("ia", "dono"):
        stmt = stmt.where(Classificacao.origem == Origem(origem))
    elif origem == "sem_tema":
        stmt = stmt.where(Classificacao.id.is_not(None), Classificacao.tema_id.is_(None))
    if pendentes:
        stmt = stmt.where(VideoRede.publicado_em <= agora - K.IDADE_CLASSIFICAR,
                          VideoRede.disponivel, _pendente_expr())
    if cursor:
        quando, vid = _ler_cursor(cursor)
        stmt = stmt.where(or_(VideoRede.publicado_em < quando,
                              and_(VideoRede.publicado_em == quando, VideoRede.id < vid)))
    limit = min(max(limit, 1), LIMIT_MAX)
    rows = db.execute(stmt.order_by(VideoRede.publicado_em.desc(), VideoRede.id.desc())
                      .limit(limit + 1)).all()
    pagina = rows[:limit]
    ids = [r[0] for r in pagina]
    linhas = {c.video_id: c for c in db.scalars(
        select(Classificacao).where(Classificacao.video_id.in_(ids)))} if ids else {}
    temas = _todos_temas(db, perfil_id)
    resumos = _resumos(db, perfil_id, ids)
    proximo = _cursor(pagina[-1][1], pagina[-1][0]) if len(rows) > limit else None
    return schemas.AprendizadoClassificacoesList(
        items=[out(linhas.get(vid), vid, temas, resumos.get(vid)) for vid in ids],
        next_cursor=proximo, pendentes=n_pendentes(db, perfil_id, agora),
        limite_hoje=schemas.AprendizadoLimiteHoje(usadas=usadas_hoje(db, perfil_id, agora),
                                                  limite=K.LIMITE_DIARIO))


# ---- dono ----

def _video_e_perfil(db: Session, video_id: uuid.UUID) -> tuple[VideoRede, uuid.UUID]:
    """O post e o perfil da conta da série (posts de séries anônimas não se classificam)."""
    row = db.execute(select(VideoRede, Conta.perfil_id).join(Serie, Serie.id == VideoRede.serie_id)
                     .join(Conta, Conta.id == Serie.conta_id)
                     .where(VideoRede.id == video_id, Serie.anonimizada_em.is_(None))).first()
    if row is None:
        raise ApiError(404, "not_found", "Post não encontrado")
    return row[0], row[1]


def _tema_ok(db: Session, perfil_id: uuid.UUID, tema_id: uuid.UUID | None) -> None:
    if tema_id is None:
        return
    tema = db.get(Tema, tema_id)
    if tema is None or tema.perfil_id != perfil_id or tema.archived:
        raise ApiError(400, "tema_invalido", "O tema não é um tema ativo deste perfil")


def linha(db: Session, video_id: uuid.UUID, lock: bool = False) -> Classificacao | None:
    stmt = select(Classificacao).where(Classificacao.video_id == video_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _tem_corte(db: Session, video: VideoRede) -> Corte | None:
    if video.destino_id is None:
        return None
    return db.scalar(select(Corte).join(Conteudo, Conteudo.corte_id == Corte.id)
                     .join(Postagem, Postagem.conteudo_id == Conteudo.id)
                     .where(Postagem.id == video.destino_id))


def corrigir(db: Session, actor: Actor, video_id: uuid.UUID,
             body: schemas.AprendizadoClassificacaoPut) -> schemas.AprendizadoClassificacao:
    video, perfil_id = _video_e_perfil(db, video_id)
    _tema_ok(db, perfil_id, body.tema_id)
    secundarios: list[uuid.UUID] = []
    for s in body.secundarios:
        _tema_ok(db, perfil_id, s)
        if s != body.tema_id and s not in secundarios:
            secundarios.append(s)
    c = linha(db, video_id, lock=True)
    versao = prefs.taxonomia_versao(db, perfil_id)
    estilo = EstiloGancho(body.estilo_gancho) if body.estilo_gancho else None
    if c is None:
        if body.version != 0:
            raise ApiError(409, "version_conflict", f"{LABEL} foi alterada; recarregue",
                           details={"versaoAtual": 0})
        c = Classificacao(video_id=video.id, perfil_id=perfil_id, tema_id=body.tema_id,
                          secundarios=secundarios, estilo_gancho=estilo, origem=Origem.dono,
                          evidencia_parcial=_tem_corte(db, video) is None,
                          taxonomia_versao=versao, created_by=actor.user_id,
                          updated_by=actor.user_id)
        db.add(c)
        db.flush()
        history.record(db, actor, ENTITY, c, "created", None, history.snapshot(c))
    else:
        history.check_version(c, body.version, LABEL)
        before = history.snapshot(c)
        c.tema_id, c.secundarios, c.estilo_gancho = body.tema_id, secundarios, estilo
        c.origem, c.reclassificar, c.taxonomia_versao = Origem.dono, False, versao
        c.chamada_id = None
        after = history.snapshot(c)
        if after != before:
            c.updated_by = actor.user_id
            history.record(db, actor, ENTITY, c, "updated", before, after)
    db.flush()
    return out(c, video.id, _todos_temas(db, perfil_id))


def versions(db: Session, video_id: uuid.UUID) -> VersionsList:
    c = linha(db, video_id)
    return versions_out(db, ENTITY, c.id) if c is not None else VersionsList(items=[])


def reverter(db: Session, actor: Actor, video_id: uuid.UUID,
             body: RevertIn) -> schemas.AprendizadoClassificacao:
    video, perfil_id = _video_e_perfil(db, video_id)
    c = linha(db, video_id, lock=True)
    if c is None:
        raise ApiError(404, "not_found", "Versão não encontrada")
    history.check_version(c, body.version, LABEL)
    state = target_state(db, ENTITY, c, body.to_version)  # type: ignore[arg-type]
    tema_id = uuid.UUID(state["tema_id"]) if state.get("tema_id") else None
    ativos = set(db.scalars(select(Tema.id).where(Tema.perfil_id == perfil_id,
                                                  Tema.archived_at.is_(None))))
    before = history.snapshot(c)
    c.tema_id = tema_id if tema_id in ativos else None
    c.secundarios = [uuid.UUID(s) for s in state.get("secundarios") or []
                     if uuid.UUID(s) in ativos and uuid.UUID(s) != c.tema_id]
    c.estilo_gancho = EstiloGancho(state["estilo_gancho"]) if state.get("estilo_gancho") \
        else None
    c.origem = Origem(state.get("origem") or "dono")
    c.reclassificar = bool(state.get("reclassificar"))
    after = history.snapshot(c)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    c.updated_by = actor.user_id
    history.record(db, actor, ENTITY, c, "reverted", before, after,
                   {"from_version": body.to_version})
    db.flush()
    return out(c, video.id, _todos_temas(db, perfil_id))


def pedir_pendentes(db: Session, actor: Actor, perfil_id: uuid.UUID
                    ) -> schemas.AprendizadoClassificarOut:
    """"Classificar pendentes": marca o pedido; a trilha atende na próxima volta (limite)."""
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "conflict", "Este perfil está arquivado")
    if not tem_taxonomia(db, perfil_id):
        raise ApiError(409, "sem_taxonomia", "Salve os temas do perfil antes de classificar")
    row = prefs.travar_perfil(db, actor, perfil_id)
    row.pedido_classificacao_em = datetime.now(UTC)
    db.flush()
    return schemas.AprendizadoClassificarOut(
        pendentes=n_pendentes(db, perfil_id),
        restantes_hoje=max(0, K.LIMITE_DIARIO - usadas_hoje(db, perfil_id)))


# ---- IA ----

@dataclass(frozen=True)
class TemaRef:
    id: uuid.UUID
    nome: str
    descricao: str
    palavras: tuple[str, ...]


def taxonomia(db: Session, perfil_id: uuid.UUID) -> list[TemaRef]:
    return [TemaRef(t.id, t.nome, t.descricao, tuple(t.palavras_chave)) for t in db.scalars(
        select(Tema).where(Tema.perfil_id == perfil_id, Tema.archived_at.is_(None))
        .order_by(Tema.nome, Tema.id))]


def texto_taxonomia(temas: Sequence[TemaRef]) -> str:
    return "\n".join(f"- id: {t.id} | {t.nome}" + (f" | {t.descricao}" if t.descricao else "")
                     + (f" | palavras: {', '.join(t.palavras)}" if t.palavras else "")
                     for t in temas)


def montar_entrada(db: Session, video: VideoRede, temas: Sequence[TemaRef]
                   ) -> tuple[str, bool]:
    """(mensagem do usuário, evidência parcial)."""
    corte = _tem_corte(db, video)
    destino = db.get(Postagem, video.destino_id) if video.destino_id else None
    tags = base.hashtags(destino.hashtags if destino else None, video.legenda)
    post = [f"Legenda publicada: {(video.legenda or video.titulo or '').strip() or '(vazia)'}",
            f"Hashtags: {' '.join('#' + h for h in tags) or '(nenhuma)'}",
            f"Duração: {video.duracao_s} s"]
    partes = [chamada_mod.bloco("taxonomia", texto_taxonomia(temas)),
              chamada_mod.bloco("post", "\n".join(post), id=str(video.id))]
    if corte is not None:
        if corte.hook_text:
            partes.append(chamada_mod.bloco("dados_terceiros", corte.hook_text, tipo="gancho"))
        transcricao = (corte.transcript or "").strip()[:K.TRANSCRICAO_MAX] or "(sem fala)"
        partes.append(chamada_mod.bloco("dados_terceiros", transcricao, tipo="transcricao"))
    else:
        partes.append("O post não tem corte do SociMan: não há transcrição nem gancho; "
                      "classifique pela legenda e pelas hashtags.")
    partes.append(chamada_mod.bloco("instrucao", "Classifique este post."))
    return "\n\n".join(partes), corte is None


def pode_a_ia(c: Classificacao | None) -> bool:
    """A regra única: a IA só cria ou atualiza linhas que não são do dono (FR-005)."""
    return c is None or c.origem == Origem.ia


def classificar_um(db: Session, client: IaClient | None, video: VideoRede, perfil: Perfil,
                   temas: Sequence[TemaRef], versao: int) -> IaChamada | None:
    """Uma chamada e a gravação. Devolve a chamada (None se a linha é do dono)."""
    atual = linha(db, video.id, lock=True)
    if not pode_a_ia(atual):
        return None
    texto, parcial = montar_entrada(db, video, temas)
    actor = chamada_mod.SISTEMA
    row = chamada_mod.executar(db, actor, TIPO, perfil, entity_type=ENTITY, entity_id=video.id,
                               user=lambda erro: texto if not erro else
                               f"{texto}\n\nA resposta anterior foi recusada: {erro}.",
                               client=client)
    if row.erro_code is not None:
        return row
    p = chamada_mod.proposta(row)
    ids = {str(t.id): t.id for t in temas}
    tema_id = ids.get(p.get("temaId") or "")
    sugestao = p.get("sugestaoTema")
    if p.get("temaId") and tema_id is None and not sugestao:
        sugestao = str(p.get("temaId"))[:K.SUGESTAO_MAX]  # o "tema" inventado pela IA
    secundarios = [ids[s] for s in p.get("secundarios") or [] if s in ids and ids[s] != tema_id]
    estilo = EstiloGancho(p["estiloGancho"]) if p.get("estiloGancho") else None
    if atual is None:
        c = Classificacao(video_id=video.id, perfil_id=perfil.id, origem=Origem.ia,
                          evidencia_parcial=parcial, taxonomia_versao=versao)
        before = None
    else:
        c, before = atual, history.snapshot(atual)
    c.tema_id = tema_id
    c.secundarios = list(dict.fromkeys(secundarios))[:K.SECUNDARIOS_MAX]
    c.estilo_gancho, c.justificativa = estilo, p.get("justificativa")
    c.sugestao_tema = sugestao[:K.SUGESTAO_MAX] if sugestao and tema_id is None else None
    c.evidencia_parcial, c.reclassificar = parcial, False
    c.taxonomia_versao, c.chamada_id = versao, row.id
    if before is None:
        db.add(c)
        db.flush()
        history.record(db, actor, ENTITY, c, "created", None, history.snapshot(c),
                       {"chamadaId": str(row.id)})
    else:
        history.record(db, actor, ENTITY, c, "updated", before, history.snapshot(c),
                       {"chamadaId": str(row.id)})
    db.flush()
    return row


def pendentes_ids(db: Session, perfil_id: uuid.UUID, agora: datetime, limite: int
                  ) -> list[uuid.UUID]:
    if limite <= 0:
        return []
    return list(db.scalars(pendentes_stmt(perfil_id, agora).limit(limite)))


def dia_local(agora: datetime) -> date:
    return agora.astimezone(ZoneInfo(filtros.fuso())).date()

