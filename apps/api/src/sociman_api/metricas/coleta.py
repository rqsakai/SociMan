"""Trilha `metricas` do agendador (spec 016, research R3 a R7): só **lê** a rede.

Uma volta (`rodar`):
1. cria a série das contas com conexão `conectada` e os escopos de métricas, sem série viva;
2. para cada série ativa (sem `adiar_ate` no futuro e sem `sem_permissao_desde`):
   descoberta pelo `video/list` (varredura completa na 1ª vez, 1ª página de hora em hora),
   fila de vídeos vencidos pelo `video/query` (lotes de 20) e foto da conta (`user/info`);
3. buscas de post e lembretes marcados como postados (vínculo, `metricas/vinculos.py`).

Regras:
- **commit por passo**, na ordem pedido → INSERT das fotos + UPDATE da agenda → commit (R7). Uma
  queda antes do commit refaz o pedido na próxima volta; `ON CONFLICT DO NOTHING` na janela
  impede foto dupla. As fotos são só de inserção (trigger no banco);
- erro numa série não atrasa a outra (rollback do passo, erro gravado na série);
- nada daqui conhece a rede: o leitor vem de `registro.leitor_para` e o token de
  `conexoes.token_valido`. Não depende de `PUBLICACAO_HABILITADA` nem do botão (princípio I:
  não há envio aqui), só de `METRICAS_COLETA_HABILITADA`;
- logs sem legenda, link, id da rede nem token.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sociman_api.config import get_settings
from sociman_api.metricas import agenda
from sociman_api.metricas.models import FotoConta, FotoVideo, Serie, VideoRede
from sociman_api.perfis.models import Conta
from sociman_api.publicacao import conexoes, limites, registro
from sociman_api.publicacao.models import Conexao, ConexaoEstado
from sociman_api.publicacao.registro import (
    ConexaoIndisponivel,
    ConexaoPerdida,
    Contexto,
    PedidoProibido,
    RecusaRede,
    RedeErro,
    SemPermissaoLeitura,
    SemResposta,
)

log = logging.getLogger("sociman.metricas.coleta")

LOTE = 20  # ids por `video/query` (limite da rede)
PAGINAS_POR_VOLTA = 10  # varredura inicial (R5)
LOTES_POR_VOLTA = 10  # fila de vídeos
LISTA_A_CADA = timedelta(hours=1)
ADIAR_TAXA = timedelta(seconds=60)
ADIAR_REDE = timedelta(minutes=5)

MOTIVO_REDE = "A TikTok não respondeu; tentando de novo às {hora}"
MOTIVO_ESCOPO = "Reconecte a conta para liberar as métricas"
MOTIVO_RECUSA = "A TikTok recusou (código {codigo})"


class _Taxa(Exception):
    """A taxa local de leitura estourou: adiar a série sem erro visível (R18)."""


def _agora() -> datetime:
    return datetime.now(UTC)


def _tz() -> str:
    return get_settings().app_tz


# ---- séries ----

def _criar_series(db: Session) -> int:
    """Uma série viva por conta com conexão `conectada` e escopos (R1); `ON CONFLICT` cobre a
    corrida com o `uq_metricas_series_conta_viva`."""
    rows = db.execute(
        select(Conexao, Conta.platform)
        .join(Conta, Conta.id == Conexao.conta_id)
        .where(Conexao.estado == ConexaoEstado.conectada,
               ~select(Serie.id).where(Serie.conta_id == Conexao.conta_id,
                                       Serie.anonimizada_em.is_(None)).exists())
    ).all()
    n = 0
    for conexao, platform in rows:
        if not conexoes.metricas_liberadas(conexao) or registro.leitor_para(platform) is None:
            continue
        r = db.execute(
            insert(Serie).values(id=uuid.uuid4(), rede=platform, conta_id=conexao.conta_id)
            .on_conflict_do_nothing(index_elements=[Serie.conta_id],
                                    index_where=Serie.anonimizada_em.is_(None)))
        n += r.rowcount or 0
    db.commit()
    return n


def series_ativas(db: Session, agora: datetime) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """`(serie_id, conexao_id)` das séries ativas e não adiadas (a 5ª condição, o
    `METRICAS_COLETA_HABILITADA`, é conferida em `rodar`)."""
    rows = db.execute(
        select(Serie.id, Conexao)
        .join(Conexao, Conexao.conta_id == Serie.conta_id)
        .where(Serie.anonimizada_em.is_(None), Serie.sem_permissao_desde.is_(None),
               Conexao.estado == ConexaoEstado.conectada)
        .where((Serie.adiar_ate.is_(None)) | (Serie.adiar_ate <= agora))
        .order_by(Serie.criada_em, Serie.id)
    ).all()
    return [(sid, cx.id) for sid, cx in rows if conexoes.metricas_liberadas(cx)]


def _serie(db: Session, serie_id: uuid.UUID) -> Serie:
    serie = db.get(Serie, serie_id, populate_existing=True)
    assert serie is not None
    return serie


# ---- vídeos ----

def _contadores(v: Any) -> dict[str, int | None]:
    return {"views": v.views, "likes": v.likes, "comments": v.comments, "shares": v.shares}


def _metadado(video: VideoRede, v: Any) -> None:
    video.share_url = v.url
    video.legenda = v.legenda
    video.titulo = v.titulo
    if v.duracao_s is not None:
        video.duracao_s = int(v.duracao_s)
    video.largura, video.altura = v.largura, v.altura
    video.disponivel = True
    video.indisponivel_desde = None


def _foto(db: Session, video: VideoRede, v: Any, alvo: int, agora: datetime) -> None:
    """INSERT … ON CONFLICT DO NOTHING (uma foto por vídeo por janela, R7)."""
    idade_s = max(0, int((agora - video.publicado_em).total_seconds()))
    db.execute(
        insert(FotoVideo).values(video_id=video.id, coletado_em=agora, idade_s=idade_s,
                                 alvo_idade_min=alvo, **_contadores(v))
        .on_conflict_do_nothing(index_elements=[FotoVideo.video_id, FotoVideo.alvo_idade_min]))
    video.ultima_foto_em = agora


def _descobrir(db: Session, serie: Serie, v: Any, agora: datetime) -> VideoRede | None:
    """Um vídeo da lista: novo → linha, foto de descoberta e agenda (R5); conhecido → só o
    metadado. Devolve o vídeo quando é novo (para o casamento)."""
    novo_id = db.execute(
        insert(VideoRede).values(
            id=uuid.uuid4(), serie_id=serie.id, rede_video_id=str(v.id), share_url=v.url,
            legenda=v.legenda, titulo=v.titulo, duracao_s=int(v.duracao_s or 0),
            largura=v.largura, altura=v.altura, publicado_em=v.criado_em, descoberto_em=agora)
        .on_conflict_do_nothing(index_elements=[VideoRede.serie_id, VideoRede.rede_video_id],
                                index_where=VideoRede.rede_video_id.is_not(None))
        .returning(VideoRede.id)).scalar()
    if novo_id is None:
        video = db.scalar(select(VideoRede).where(VideoRede.serie_id == serie.id,
                                                  VideoRede.rede_video_id == str(v.id)))
        if video is not None:
            _metadado(video, v)
        return None
    video = db.get(VideoRede, novo_id)
    idade = agenda.idade_min(video.publicado_em, agora)
    _foto(db, video, v, agenda.alvo_descoberta(idade), agora)
    # Mais de 365 d: só a foto da descoberta (Q2 = A).
    video.proxima_coleta_em = agenda.proxima_coleta(video.publicado_em, idade)
    return video


def _ao_descobrir(db: Session, videos: list[VideoRede], agora: datetime) -> None:
    vinculos = _vinculos()
    if vinculos is None:
        return
    for video in videos:
        vinculos.ao_descobrir(db, video, agora)


def _pagina(db: Session, serie: Serie, leitor: Any, ctx: Contexto, conexao_id: uuid.UUID,
            cursor: int | None, agora: datetime) -> tuple[int | None, bool]:
    _taxa(conexao_id, "video_list")
    videos, proximo, has_more = leitor.listar(ctx, cursor, LOTE)
    novos = [n for n in (_descobrir(db, serie, v, agora) for v in videos) if n is not None]
    db.flush()
    _ao_descobrir(db, novos, agora)
    serie.ultima_coleta_em = agora
    return proximo, has_more


def _descoberta(db: Session, serie: Serie, leitor: Any, ctx: Contexto,
                conexao_id: uuid.UUID, agora: datetime) -> None:
    """Varredura completa na 1ª vez (até 10 páginas por volta, retomada pelo cursor) e a 1ª
    página de hora em hora (R5)."""
    if serie.varredura_concluida_em is None:
        for _ in range(PAGINAS_POR_VOLTA):
            if serie.varredura_cursor is None:
                serie.lista_proxima_em = agora + LISTA_A_CADA
            cursor, has_more = _pagina(db, serie, leitor, ctx, conexao_id,
                                       serie.varredura_cursor, agora)
            if has_more and cursor is not None:
                serie.varredura_cursor = int(cursor)
            else:
                serie.varredura_cursor = None
                serie.varredura_concluida_em = agora
            db.commit()
            if serie.varredura_concluida_em is not None:
                break
    if serie.lista_proxima_em is None or serie.lista_proxima_em <= agora:
        _pagina(db, serie, leitor, ctx, conexao_id, None, agora)
        serie.lista_proxima_em = agora + LISTA_A_CADA
        db.commit()


def _fila(db: Session, serie: Serie, leitor: Any, ctx: Contexto, conexao_id: uuid.UUID,
          agora: datetime) -> None:
    """Vídeos com `proxima_coleta_em ≤ agora`, 20 por `video/query` (R4, R5)."""
    for _ in range(LOTES_POR_VOLTA):
        lote = list(db.scalars(
            select(VideoRede).where(VideoRede.serie_id == serie.id,
                                    VideoRede.proxima_coleta_em.is_not(None),
                                    VideoRede.proxima_coleta_em <= agora,
                                    VideoRede.rede_video_id.is_not(None))
            .order_by(VideoRede.proxima_coleta_em, VideoRede.id).limit(LOTE)))
        if not lote:
            return
        _taxa(conexao_id, "video_query")
        lidos = {str(v.id): v for v in leitor.consultar(ctx, [x.rede_video_id for x in lote])}
        for video in lote:
            idade = agenda.idade_min(video.publicado_em, agora)
            v = lidos.get(video.rede_video_id)
            if v is None:  # privado ou apagado: segue na fila, fotos antigas intactas
                video.disponivel = False
                video.indisponivel_desde = video.indisponivel_desde or agora
            else:
                _metadado(video, v)
                alvo = agenda.alvo_vencido(idade)
                if alvo is not None:
                    _foto(db, video, v, alvo, agora)
            video.proxima_coleta_em = agenda.proxima_coleta(video.publicado_em, idade)
        serie.ultima_coleta_em = agora
        db.commit()


def _horaria(db: Session, serie: Serie, agora: datetime) -> bool:
    return db.scalar(select(func.count()).select_from(VideoRede).where(
        VideoRede.serie_id == serie.id,
        VideoRede.publicado_em > agora - agenda.CONTA_HORARIA)) > 0


def _conta(db: Session, serie: Serie, leitor: Any, ctx: Contexto, conexao_id: uuid.UUID,
           agora: datetime) -> None:
    """Foto da conta na janela horária ou diária (R6)."""
    horaria = _horaria(db, serie, agora)
    if not agenda.conta_vencida(serie.conta_proxima_em, agora, horaria):
        return
    _taxa(conexao_id, "user_info")
    stats = leitor.stats_conta(ctx)
    db.execute(
        insert(FotoConta).values(
            serie_id=serie.id, coletado_em=agora,
            janela_em=agenda.janela_conta(agora, horaria, _tz()),
            seguidores=stats.seguidores, seguindo=stats.seguindo, curtidas=stats.curtidas,
            videos=stats.videos)
        .on_conflict_do_nothing(index_elements=[FotoConta.serie_id, FotoConta.janela_em]))
    serie.conta_proxima_em = agenda.proxima_janela_conta(agora, horaria, _tz())
    serie.ultima_coleta_em = agora
    db.commit()


# ---- erros (R3) ----

def _taxa(conexao_id: uuid.UUID, recurso: str) -> None:
    if not limites.consumir(conexao_id, recurso):
        raise _Taxa(recurso)


def _erro(serie: Serie, codigo: str, motivo: str, agora: datetime) -> None:
    serie.ultimo_erro_codigo = codigo
    serie.ultimo_erro_motivo = motivo
    serie.ultimo_erro_em = agora


def _registrar_falha(db: Session, serie_id: uuid.UUID, e: Exception, agora: datetime) -> None:
    """Depois do rollback do passo: grava o efeito do erro na série (tabela de R3)."""
    serie = _serie(db, serie_id)
    if isinstance(e, _Taxa) or (isinstance(e, RecusaRede)
                                and e.codigo == "rate_limit_exceeded"):
        serie.adiar_ate = agora + ADIAR_TAXA
    elif isinstance(e, SemPermissaoLeitura):
        serie.sem_permissao_desde = agora
        _erro(serie, "scope_not_authorized", MOTIVO_ESCOPO, agora)
    elif isinstance(e, (ConexaoIndisponivel, SemResposta)):
        serie.adiar_ate = agora + ADIAR_REDE
        hora = serie.adiar_ate.astimezone(ZoneInfo(_tz())).strftime("%H:%M")
        _erro(serie, "rede_indisponivel", MOTIVO_REDE.format(hora=hora), agora)
    elif isinstance(e, RecusaRede):
        _erro(serie, e.codigo, MOTIVO_RECUSA.format(codigo=e.codigo), agora)
    # ConexaoPerdida: nada na série (a 015 já levou a conexão a `precisa_reconectar`).
    db.commit()


def _coletar_serie(db: Session, serie_id: uuid.UUID, conexao_id: uuid.UUID, client: Any,
                   agora: datetime) -> None:
    serie = _serie(db, serie_id)
    leitor = registro.leitor_para(serie.rede)
    if leitor is None:
        return
    ctx = Contexto(client=client,
                   token=lambda: conexoes.token_valido(conexao_id, client=client))
    try:
        _descoberta(db, serie, leitor, ctx, conexao_id, agora)
        _fila(db, serie, leitor, ctx, conexao_id, agora)
        _conta(db, serie, leitor, ctx, conexao_id, agora)
    except PedidoProibido:
        db.rollback()
        raise  # bug de código, nunca da rede: vai para o log do agendador
    except (_Taxa, RedeErro) as e:
        db.rollback()
        if not isinstance(e, ConexaoPerdida):
            log.warning("metricas: série %s adiada (%s)", serie_id,
                        getattr(e, "codigo", None) or type(e).__name__)
        _registrar_falha(db, serie_id, e, agora)
        return
    serie = _serie(db, serie_id)
    if serie.ultimo_erro_codigo is not None or serie.adiar_ate is not None:
        serie.ultimo_erro_codigo = serie.ultimo_erro_motivo = serie.ultimo_erro_em = None
        serie.adiar_ate = None
        db.commit()


# ---- vínculo (US3): a trilha C preenche `metricas/vinculos.py` ----

def _vinculos() -> Any:
    try:
        from sociman_api.metricas import vinculos
    except ImportError:
        return None
    return vinculos


def _vinculo(db: Session, clientes: "_Clientes", agora: datetime) -> None:
    vinculos = _vinculos()
    if vinculos is None:
        return
    client = clientes.get()
    for passo in ("rodar_buscas", "varrer_lembretes"):
        funcao = getattr(vinculos, passo, None)
        if funcao is None:
            continue
        try:
            funcao(db, client=client, agora=agora)
            db.commit()
        except Exception:  # um passo do vínculo não derruba a coleta
            db.rollback()
            log.exception("metricas: falha em %s", passo)


# ---- volta ----

class _Clientes:
    """Um cliente HTTP por volta (ou o injetado pelos testes)."""

    def __init__(self, injetado: Any = None):
        self.injetado = injetado
        self._aberto: Any = None

    def get(self) -> Any:
        if self.injetado is not None:
            return self.injetado
        if self._aberto is None:
            self._aberto = registro.get_cliente()
        return self._aberto

    def fechar(self) -> None:
        if self._aberto is not None:
            self._aberto.close()


def rodar(db: Session, client: Any = None, agora: datetime | None = None) -> int:
    """Uma volta da trilha; devolve quantas séries foram visitadas. `client` injeta o cliente
    HTTP da rede e `agora` o relógio (testes, sem sleep)."""
    if not get_settings().metricas_coleta_habilitada:
        return 0  # o agendador já deixa a trilha ociosa; defesa redundante
    agora = agora or _agora()
    clientes = _Clientes(client)
    try:
        _criar_series(db)
        ativas = series_ativas(db, agora)
        for serie_id, conexao_id in ativas:
            _coletar_serie(db, serie_id, conexao_id, clientes.get(), agora)
        _vinculo(db, clientes, agora)
    finally:
        clientes.fechar()
    return len(ativas)

