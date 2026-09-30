"""Vínculo do post da rede com o destino do SociMan (spec 016, research R9 a R12; Q3 = A).

Três níveis:
1. **envio:** a busca do `publish_id` de um rascunho entregue (`metricas_buscas_post`, por até
   14 dias, com recuo) e o `rede_post_id` do post direto da 015 (`ao_descobrir`);
2. **casamento:** data (âncora), duração ±1 s e legenda, com candidato único nos dois sentidos
   (`metricas/casamento.py`). Um lembrete só liga sozinho depois de "Marcar como postado";
3. **link ou escolha:** o dono cola o link ou escolhe um candidato (rotas **H**).

Regras que valem em todo o módulo:
- o autor automático é `Actor(kind="system:metricas")`; `vinculado_por` fica nulo;
- a mudança de estado do destino é só `postagem.service.publicacao_pelo_vinculo` (e o
  `marcar_postado` humano, no lembrete antes do clique). **Nada aqui atribui estado**;
- o histórico do destino não leva id nem link da rede (R11);
- desfazer anula `destino_id`, `vinculo_metodo`, `vinculado_por` e `vinculado_em` juntos, e o
  destino fica **bloqueado** para o automático (`vinculo_desfeito` no histórico);
- só leitura na rede: `status/fetch` e `video/query`, pelo leitor do `registro`.
"""

import logging
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.conteudos.models import Modo
from sociman_api.errors import ApiError
from sociman_api.metricas import casamento, consulta, schemas
from sociman_api.metricas.casamento import Ancora, Par
from sociman_api.metricas.models import BuscaPost, Serie, VideoRede, VinculoMetodo
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo
from sociman_api.perfis.models import Conta
from sociman_api.perfis.service_perfis import user_refs
from sociman_api.postagem import service as postagem
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao import conexoes, limites, registro
from sociman_api.publicacao.legenda import legenda_tiktok
from sociman_api.publicacao.models import Conexao, Tentativa, TentativaFase
from sociman_api.publicacao.registro import (
    Contexto,
    Falhou,
    PedidoProibido,
    Pendente,
    RedeErro,
    SemPermissaoLeitura,
)

log = logging.getLogger("sociman.metricas.vinculos")

AUTOR = Actor(kind="system:metricas")
PRAZO_BUSCA = timedelta(days=14)
# (até quanto tempo depois da entrega, intervalo entre consultas) — R9.
AGENDA_BUSCA = (
    (timedelta(hours=2), timedelta(minutes=10)),
    (timedelta(hours=24), timedelta(minutes=30)),
    (timedelta(days=3), timedelta(hours=3)),
    (PRAZO_BUSCA, timedelta(hours=12)),
)
QUERY_A_CADA = timedelta(hours=12)  # post id conhecido, vídeo ainda não devolvido
RECUO_ERRO = timedelta(minutes=10)
BUSCAS_POR_VOLTA = 50
LEMBRETES_JANELA = timedelta(hours=25)  # varredura depois do clique (R10)
BUSCANDO_LEMBRETE = timedelta(hours=1)
CANDIDATOS_LEMBRETE = timedelta(days=14)  # lembrete antes do clique (R11)
FINS_SEM_ANCORA = ("falhou", "cancelada", "anonimizada")
PUBLICADO = "PUBLISH_COMPLETE"

LINK_INVALIDO = "Cole o link completo do post (tiktok.com/@conta/video/…)"
LINK_CURTO = "Abra o link e copie o endereço completo"
INDISPONIVEIS = "Conecte a conta e libere as métricas para ligar o post"
NAO_ENCONTRADO = "Não achamos este post em @{conta} (é de outra conta, privado ou foi apagado)"
JA_VINCULADO = "Este post já está ligado a outro conteúdo; desfaça lá primeiro"
DESTINO_JA = "Este destino já está ligado a um post; desfaça antes de trocar"
SEM_VINCULO = "Este destino não está ligado a nenhum post"
REDE_FORA = "A TikTok não respondeu; tente de novo em instantes"

_LINK = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?tiktok\.com/@([A-Za-z0-9._]+)/video/(\d+)/?(?:[?#].*)?$",
    re.IGNORECASE)
_CURTO = re.compile(r"^(?:https?://)?(?:vm|vt)\.tiktok\.com(?:/|$)", re.IGNORECASE)


class _Taxa(Exception):
    """A taxa local da conexão estourou: a busca fica para a próxima volta."""


def _agora() -> datetime:
    return datetime.now(UTC)


# ---- link (nível 3) ----

def ler_link(link: str, handle: str) -> str:
    """O id do post de `https://www.tiktok.com/@<handle>/video/<id>` (com ou sem query), como
    texto. Encurtado, sem `/video/<id>` ou de outro `@` → erro com o motivo (R11). Resolver o
    encurtado pediria um GET fora da lista fechada (princípio I)."""
    texto = (link or "").strip()
    if _CURTO.match(texto):
        raise ApiError(400, "link_invalido", LINK_CURTO)
    m = _LINK.match(texto)
    if m is None:
        raise ApiError(400, "link_invalido", LINK_INVALIDO)
    do_link, conta = m.group(1).lower(), handle.lstrip("@").lower()
    if do_link != conta:
        raise ApiError(409, "link_outra_conta", f"O link é de @{m.group(1)}; este destino é de "
                       f"@{handle.lstrip('@')}",
                       details={"linkConta": m.group(1), "conta": handle.lstrip("@")})
    return m.group(2)


# ---- série ativa ----

def serie_ativa(db: Session, conta_id: uuid.UUID) -> tuple[Serie, Conexao] | None:
    """A série viva da conta e a conexão, se a série estiver **ativa** (as 5 condições do
    data-model, `consulta.serie_ativa`)."""
    serie = consulta.serie_viva(db, conta_id)
    conexao = conexoes.conexao_viva(db, conta_id)
    if serie is None or conexao is None \
            or not consulta.serie_ativa(serie, conexao, get_settings()):
        return None
    return serie, conexao


def _contexto(conexao_id: uuid.UUID, client: Any) -> Contexto:
    return Contexto(client=client,
                    token=lambda: conexoes.token_valido(conexao_id, client=client))


def _consumir(conexao_id: uuid.UUID, endpoint: str) -> None:
    if not limites.consumir(conexao_id, endpoint):
        raise _Taxa(endpoint)


def _garantir_video(db: Session, serie: Serie, lido: Any, agora: datetime) -> VideoRede:
    """O vídeo da série com o id lido (cria com a foto de descoberta e a agenda, como a coleta)."""
    from sociman_api.metricas import coleta  # import tardio: a coleta chama este módulo

    video = db.scalar(select(VideoRede).where(VideoRede.serie_id == serie.id,
                                              VideoRede.rede_video_id == str(lido.id)))
    if video is not None:
        return video
    coleta._descobrir(db, serie, lido, agora)
    db.flush()
    video = db.scalar(select(VideoRede).where(VideoRede.serie_id == serie.id,
                                              VideoRede.rede_video_id == str(lido.id)))
    assert video is not None
    return video


# ---- ligar e avisar ----

def _nome(db: Session, destino: Postagem) -> str:
    from sociman_api.conteudos.models import Conteudo

    conteudo = db.get(Conteudo, destino.conteudo_id)
    return destino.titulo or (conteudo.titulo if conteudo else "") or "seu conteúdo"


def _avisar(db: Session, tipo: NotificacaoTipo, destino: Postagem) -> None:
    conta = db.get(Conta, destino.conta_id)
    handle = f"@{conta.handle}" if conta is not None else ""
    if tipo == NotificacaoTipo.post_detectado:
        titulo = f"Post detectado: {_nome(db, destino)}"
        corpo = f"{handle}: o post foi ligado ao conteúdo"
    else:
        titulo = f"Escolha o post: {_nome(db, destino)}"
        corpo = f"{handle}: mais de um post combina com este destino"
    notificacoes.criar(
        db, tipo, titulo=titulo, corpo=corpo,
        link=f"/app/conteudos/{destino.conteudo_id}?conta={destino.conta_id}",
        entidade=(postagem.ENTITY, destino.id), dedupe_key=f"{tipo.value}:{destino.id}",
        destinatarios=notificacoes.donos_ativos(db))


def _encerrar(busca: BuscaPost, fim: str, agora: datetime) -> None:
    busca.fim = fim
    busca.encerrada_em = agora
    busca.proxima_em = None


def _ligar(db: Session, actor: Actor, destino: Postagem, video: VideoRede,
           metodo: VinculoMetodo, agora: datetime) -> None:
    """Grava o vínculo vivo, a transição do destino (R12) e encerra a busca aberta."""
    serie = db.get(Serie, video.serie_id)
    assert serie is not None and serie.conta_id is not None
    estado_antes = destino.estado
    video.destino_id = destino.id
    video.vinculo_metodo = metodo
    video.vinculado_por = actor.user_id if actor.kind == "user" else None
    video.vinculado_em = agora
    postagem.publicacao_pelo_vinculo(db, actor, destino, True, conta_do_video=serie.conta_id,
                                     metodo=metodo.value)
    busca = db.get(BuscaPost, destino.id)
    if busca is not None and busca.encerrada_em is None:
        _encerrar(busca, "vinculado", agora)
    db.flush()
    if actor.kind != "user" and destino.estado != estado_antes:
        _avisar(db, NotificacaoTipo.post_detectado, destino)


def _ligar_auto(db: Session, destino: Postagem, video: VideoRede, metodo: VinculoMetodo,
                agora: datetime) -> bool:
    """Vínculo automático num savepoint: corrida com o dono (índices únicos) ou destino num
    estado que não liga não derrubam a volta."""
    try:
        with db.begin_nested():
            db.refresh(destino, with_for_update=True)
            if destino.archived or _vinculado(db, destino.id) is not None:
                return False
            _ligar(db, AUTOR, destino, video, metodo, agora)
        return True
    except (IntegrityError, ApiError) as e:
        log.info("metricas: vínculo automático não feito (%s)", getattr(e, "code", "corrida"))
        return False


def _vinculado(db: Session, destino_id: uuid.UUID) -> VideoRede | None:
    return db.scalar(select(VideoRede).where(VideoRede.destino_id == destino_id))


video_do_destino = _vinculado  # o vídeo ligado ao destino (a curva do "Desempenho")


def _sem_video():
    return ~exists().where(VideoRede.destino_id == Postagem.id)


# ---- nível 2: casamento ----

def _ancorados(db: Session, conta_id: uuid.UUID) -> list[tuple[Postagem, Ancora]]:
    """Destinos da conta com âncora (tabela de R10), sem vínculo e sem bloqueio."""
    base = (Postagem.conta_id == conta_id, Postagem.archived_at.is_(None), _sem_video())
    rascunhos = db.execute(
        select(Postagem, BuscaPost.entregue_em)
        .join(BuscaPost, BuscaPost.destino_id == Postagem.id)
        .where(*base, Postagem.modo == Modo.criar_rascunho,
               (BuscaPost.fim.is_(None)) | (BuscaPost.fim.not_in(FINS_SEM_ANCORA)))
    ).all()
    lembretes = db.scalars(
        select(Postagem).where(*base, Postagem.modo == Modo.lembrete,
                               Postagem.estado == DestinoEstado.postado,
                               Postagem.posted_at.is_not(None))
    ).all()
    pares = [(d, casamento.ancora(d, entregue)) for d, entregue in rascunhos]
    pares += [(d, casamento.ancora(d, None)) for d in lembretes]
    pares = [(d, a) for d, a in pares if a is not None]
    fora = casamento.bloqueados(db, [d.id for d, _ in pares])
    return [(d, a) for d, a in pares if d.id not in fora]


def _livres(db: Session, serie_id: uuid.UUID, de: datetime, ate: datetime,
            so_automaticos: bool = True) -> list[VideoRede]:
    stmt = select(VideoRede).where(
        VideoRede.serie_id == serie_id, VideoRede.destino_id.is_(None),
        VideoRede.anonimizado_em.is_(None), VideoRede.publicado_em >= de,
        VideoRede.publicado_em <= ate)
    if so_automaticos:
        stmt = stmt.where(VideoRede.vinculo_automatico.is_(True))
    return list(db.scalars(stmt.order_by(VideoRede.publicado_em.desc(), VideoRede.id)))


def _pares(db: Session, ancorados: Sequence[tuple[Postagem, Ancora]],
           videos: Sequence[VideoRede]) -> list[Par]:
    duracoes = casamento.duracoes_s(db, [d.conteudo_id for d, _ in ancorados])
    pares = []
    for d, a in ancorados:
        legenda_d = legenda_tiktok(d)
        for v in videos:
            if a.contem(v.publicado_em) \
                    and casamento.duracao_compativel(v.duracao_s, duracoes.get(d.conteudo_id)):
                pares.append(Par(v.id, d.id, casamento.classificar_legenda(v.legenda, legenda_d)))
    return pares


def casar(db: Session, serie: Serie, agora: datetime) -> int:
    """Roda o casamento da conta da série: liga os pares únicos nos dois sentidos e avisa os
    destinos ambíguos (1 `vinculo_a_confirmar` por destino). Devolve quantos ligou."""
    if serie.conta_id is None or serie.anonimizada_em is not None:
        return 0
    ancorados = _ancorados(db, serie.conta_id)
    if not ancorados:
        return 0
    de = min(a.em - casamento.JANELAS[a.tipo][0] for _, a in ancorados)
    ate = max(a.em + casamento.JANELAS[a.tipo][1] for _, a in ancorados)
    videos = {v.id: v for v in _livres(db, serie.id, de, ate)}
    ligam, ambiguos = casamento.pares_unicos(_pares(db, ancorados, list(videos.values())))
    destinos = {d.id: d for d, _ in ancorados}
    n = 0
    for par in ligam:
        n += _ligar_auto(db, destinos[par.destino_id], videos[par.video_id],
                         VinculoMetodo.casamento, agora)
    for destino_id in ambiguos:
        _avisar(db, NotificacaoTipo.vinculo_a_confirmar, destinos[destino_id])
    return n


def ao_descobrir(db: Session, video: VideoRede, agora: datetime | None = None) -> None:
    """Chamado pela coleta para cada vídeo novo (sem rede, dentro da transação dela): liga o
    post direto da 015 (`rede_post_id`) ou o post id de uma busca (`envio`); senão, casamento."""
    agora = agora or _agora()
    if video.destino_id is not None or not video.vinculo_automatico \
            or video.rede_video_id is None:
        return
    serie = db.get(Serie, video.serie_id)
    if serie is None or serie.conta_id is None:
        return
    candidato = db.scalar(
        select(Postagem).where(Postagem.conta_id == serie.conta_id,
                               Postagem.archived_at.is_(None), _sem_video(),
                               Postagem.modo == Modo.publicar,
                               Postagem.rede_post_id == video.rede_video_id))
    if candidato is None:
        candidato = db.scalar(
            select(Postagem).join(BuscaPost, BuscaPost.destino_id == Postagem.id)
            .where(Postagem.conta_id == serie.conta_id, Postagem.archived_at.is_(None),
                   _sem_video(), BuscaPost.encerrada_em.is_(None),
                   BuscaPost.post_id == video.rede_video_id))
    if candidato is not None and candidato.id not in casamento.bloqueados(db, [candidato.id]):
        _ligar_auto(db, candidato, video, VinculoMetodo.envio, agora)
        return
    casar(db, serie, agora)


# ---- nível 1: buscas do post ----

def proxima_consulta(entregue_em: datetime, agora: datetime) -> datetime | None:
    """A próxima consulta pela agenda de R9, ou None depois do prazo de 14 dias."""
    passado = agora - entregue_em
    for limite, passo in AGENDA_BUSCA:
        if passado < limite:
            return min(agora + passo, entregue_em + PRAZO_BUSCA)
    return None


def _criar_buscas(db: Session, agora: datetime) -> set[uuid.UUID]:
    """Uma busca por destino `criar_rascunho` cuja última tentativa terminou `entregue`, sem
    vínculo e sem busca (a 1ª consulta sai nesta volta). Devolve as contas desses destinos."""
    ultima = select(func.max(Tentativa.numero)).where(
        Tentativa.destino_id == Postagem.id).correlate(Postagem).scalar_subquery()
    rows = db.execute(
        select(Postagem.id, Postagem.conta_id, Tentativa.id, Tentativa.concluida_em)
        .join(Tentativa, Tentativa.destino_id == Postagem.id)
        .where(Postagem.modo == Modo.criar_rascunho, Postagem.archived_at.is_(None),
               Tentativa.numero == ultima, Tentativa.fase == TentativaFase.entregue,
               Tentativa.concluida_em.is_not(None), _sem_video(),
               ~exists().where(BuscaPost.destino_id == Postagem.id))
    ).all()
    for destino_id, _conta_id, tentativa_id, entregue_em in rows:
        db.execute(insert(BuscaPost).values(
            destino_id=destino_id, tentativa_id=tentativa_id, entregue_em=entregue_em,
            proxima_em=agora).on_conflict_do_nothing(index_elements=[BuscaPost.destino_id]))
    return {conta_id for _, conta_id, _, _ in rows}


def _fechar_buscas(db: Session, agora: datetime) -> None:
    """Destino arquivado → `cancelada`; destino já ligado por outro nível → `vinculado`."""
    abertas = db.execute(
        select(BuscaPost, Postagem).join(Postagem, Postagem.id == BuscaPost.destino_id)
        .where(BuscaPost.encerrada_em.is_(None))
        .where((Postagem.archived_at.is_not(None)) | ~_sem_video())
    ).all()
    for busca, destino in abertas:
        _encerrar(busca, "cancelada" if destino.archived else "vinculado", agora)


def _consultar(db: Session, busca: BuscaPost, destino: Postagem, tentativa: Tentativa,
               serie: Serie, conexao: Conexao, client: Any, agora: datetime) -> None:
    leitor = registro.leitor_para(serie.rede)
    assert leitor is not None
    ctx = _contexto(conexao.id, client)
    prazo = busca.entregue_em + PRAZO_BUSCA
    if busca.post_id is None:
        _consumir(conexao.id, "status")
        r = leitor.post_publicado(ctx, tentativa.publish_id)
        busca.consultas += 1
        if isinstance(r, Falhou):
            busca.ultimo_status = "FAILED"
            _encerrar(busca, "falhou", agora)
            return
        if isinstance(r, Pendente):
            busca.ultimo_status = r.status
            proxima = proxima_consulta(busca.entregue_em, agora)
            if proxima is None:
                _encerrar(busca, "prazo", agora)
            else:
                busca.proxima_em = proxima
            return
        busca.ultimo_status = PUBLICADO
        busca.post_id = r.id
    _consumir(conexao.id, "video_query")
    lido = next((v for v in leitor.consultar(ctx, [busca.post_id]) if str(v.id) == busca.post_id),
                None)
    video = _garantir_video(db, serie, lido, agora) if lido is not None else None
    if video is not None and video.destino_id is None and video.vinculo_automatico \
            and destino.id not in casamento.bloqueados(db, [destino.id]) \
            and _ligar_auto(db, destino, video, VinculoMetodo.envio, agora):
        return
    # Privado, em moderação ou disputado: só o `video/query` a cada 12 h até o prazo (R9).
    if agora + QUERY_A_CADA >= prazo:
        busca.proxima_em = prazo if agora < prazo else None
        if busca.proxima_em is None:
            _encerrar(busca, "prazo", agora)
    else:
        busca.proxima_em = agora + QUERY_A_CADA


def rodar_buscas(db: Session, client: Any = None, agora: datetime | None = None) -> int:
    """Passo do vínculo na volta da trilha `metricas` (R3, passo 3): cria, encerra e consulta
    as buscas vencidas. Commit por busca; erro numa busca não derruba as outras."""
    agora = agora or _agora()
    contas = _criar_buscas(db, agora)
    _fechar_buscas(db, agora)
    db.commit()
    # O post pode ter sido descoberto antes de a busca existir (a âncora nasce com ela).
    for conta_id in contas:
        ativa = serie_ativa(db, conta_id)
        if ativa is not None:
            casar(db, ativa[0], agora)
            db.commit()
    vencidas = db.execute(
        select(BuscaPost.destino_id).where(BuscaPost.encerrada_em.is_(None),
                                           BuscaPost.proxima_em <= agora)
        .order_by(BuscaPost.proxima_em).limit(BUSCAS_POR_VOLTA)
    ).scalars().all()
    feitas = 0
    sem_taxa: set[uuid.UUID] = set()
    for destino_id in vencidas:
        busca = db.get(BuscaPost, destino_id, populate_existing=True)
        destino = db.get(Postagem, destino_id)
        if busca is None or destino is None or busca.encerrada_em is not None:
            continue
        if agora >= busca.entregue_em + PRAZO_BUSCA:
            _encerrar(busca, "prazo", agora)
            db.commit()
            continue
        ativa = serie_ativa(db, destino.conta_id)
        if ativa is None or destino.conta_id in sem_taxa:
            continue
        serie, conexao = ativa
        tentativa = db.get(Tentativa, busca.tentativa_id)
        assert tentativa is not None
        try:
            _consultar(db, busca, destino, tentativa, serie, conexao, client, agora)
            db.commit()
            feitas += 1
        except _Taxa:
            db.rollback()
            sem_taxa.add(destino.conta_id)
        except PedidoProibido:
            db.rollback()
            raise  # bug de código, nunca da rede
        except (RedeErro, SemPermissaoLeitura) as e:
            db.rollback()
            log.warning("metricas: busca adiada (%s)", getattr(e, "codigo", None)
                        or type(e).__name__)
            busca = db.get(BuscaPost, destino_id, populate_existing=True)
            if busca is not None and busca.encerrada_em is None:
                busca.proxima_em = agora + RECUO_ERRO
            db.commit()
    return feitas


def varrer_lembretes(db: Session, client: Any = None, agora: datetime | None = None) -> int:
    """Lembretes marcados como postados nas últimas 25 h, sem vínculo: casamento com a âncora
    no clique (R10, Q3 = A). Só banco; o `client` fica pela assinatura comum dos passos."""
    agora = agora or _agora()
    contas = db.scalars(
        select(Postagem.conta_id).distinct()
        .where(Postagem.modo == Modo.lembrete, Postagem.estado == DestinoEstado.postado,
               Postagem.posted_at >= agora - LEMBRETES_JANELA,
               Postagem.archived_at.is_(None), _sem_video())
    ).all()
    n = 0
    for conta_id in contas:
        ativa = serie_ativa(db, conta_id)
        if ativa is not None:
            n += casar(db, ativa[0], agora)
            db.commit()
    return n


# ---- o vínculo visto pelo destino (GET) ----

def _resumos(db: Session, videos: Sequence[VideoRede], agora: datetime
             ) -> list[schemas.VideoResumo]:
    return consulta.resumos(db, videos, agora)


def _pode_ligar(destino: Postagem) -> bool:
    """Estados de R12 em que o dono pode ligar um post."""
    if destino.archived:
        return False
    if destino.modo == Modo.lembrete:
        return destino.estado in (DestinoEstado.aprovado, DestinoEstado.agendado,
                                  DestinoEstado.postado)
    return destino.estado in (DestinoEstado.rascunho_criado, DestinoEstado.publicado,
                              DestinoEstado.postado) \
        or (destino.estado == DestinoEstado.falhou and destino.falha_incerta)


def _antes_do_clique(destino: Postagem) -> bool:
    return destino.modo == Modo.lembrete and destino.estado in (DestinoEstado.aprovado,
                                                                 DestinoEstado.agendado)


def _candidatos(db: Session, destino: Postagem, serie: Serie, ancora: Ancora | None,
                agora: datetime) -> list[tuple[VideoRede, float, str, int | None]]:
    """(vídeo, diferença de duração, legenda, minutos da âncora), da mais perto à mais longe.

    Com âncora: os vídeos sem vínculo na janela, com a duração a ±1 s (inclui os incompatíveis,
    que deixam o destino "a confirmar"). Lembrete antes do clique: os vídeos sem vínculo dos
    últimos 14 dias, duração ±1 s e legenda não incompatível, pela distância ao `planned_at`
    (ou ao `aprovado_em`)."""
    duracao = casamento.duracoes_s(db, [destino.conteudo_id]).get(destino.conteudo_id)
    legenda_d = legenda_tiktok(destino)
    if ancora is not None:
        antes, depois = casamento.JANELAS[ancora.tipo]
        videos = _livres(db, serie.id, ancora.em - antes, ancora.em + depois, False)
        referencia = ancora.em
    elif _antes_do_clique(destino):
        videos = _livres(db, serie.id, agora - CANDIDATOS_LEMBRETE, agora, False)
        referencia = destino.planned_at or destino.aprovado_em or agora
    else:
        return []
    out = []
    for v in videos:
        if not casamento.duracao_compativel(v.duracao_s, duracao):
            continue
        classe = casamento.classificar_legenda(v.legenda, legenda_d)
        if ancora is None and classe == "incompativel":
            continue
        minutos = round((v.publicado_em - referencia).total_seconds() / 60)
        out.append((v, abs(v.duracao_s - duracao), classe, minutos))
    out.sort(key=lambda c: (abs(c[3]), c[0].publicado_em, str(c[0].id)))
    return out


def vinculo(db: Session, destino: Postagem, agora: datetime | None = None) -> schemas.Vinculo:
    """O estado do vínculo do destino (data-model, "Vínculo visto pelo destino")."""
    agora = agora or _agora()
    video = _vinculado(db, destino.id)
    busca = db.get(BuscaPost, destino.id)
    bloqueado = bool(casamento.bloqueados(db, [destino.id]))
    entregue = busca.entregue_em if busca is not None and busca.fim not in FINS_SEM_ANCORA \
        else None
    ancora = casamento.ancora(destino, entregue)
    busca_out = schemas.Busca(entregue_em=busca.entregue_em, consultas=busca.consultas,
                              ate=busca.entregue_em + PRAZO_BUSCA, fim=busca.fim) \
        if busca is not None else None
    base: dict[str, Any] = {
        "busca": busca_out, "ancora": ancora.tipo if ancora else None,
        "ancora_em": ancora.em if ancora else None, "bloqueado": bloqueado,
        "automatico": not bloqueado,
    }
    if video is not None:
        users = user_refs(db, [video.vinculado_por]) if video.vinculado_por else {}
        return schemas.Vinculo(
            estado="vinculado", video=_resumos(db, [video], agora)[0],
            metodo=video.vinculo_metodo.value if video.vinculo_metodo else None,
            vinculado_por=users.get(video.vinculado_por), vinculado_em=video.vinculado_em,
            candidatos=[], pode_vincular=False, motivo=None, **base)
    ativa = serie_ativa(db, destino.conta_id)
    if ativa is None:
        return schemas.Vinculo(estado="indisponivel", video=None, metodo=None,
                               vinculado_por=None, vinculado_em=None, candidatos=[],
                               pode_vincular=False, motivo=INDISPONIVEIS, **base)
    cands = _candidatos(db, destino, ativa[0], ancora, agora)
    resumos = _resumos(db, [c[0] for c in cands], agora)
    candidatos = [schemas.Candidato(video=r, duracao_diferenca_s=c[1], legenda=c[2],
                                    minutos_da_ancora=c[3]) for r, c in zip(resumos, cands,
                                                                            strict=True)]
    validos = [c for c in cands if c[2] != "incompativel"]
    if ancora is not None and (len(validos) >= 2 or len(validos) < len(cands)):
        estado = "a_confirmar"
    elif (busca is not None and busca.encerrada_em is None) or (
            destino.modo == Modo.lembrete and destino.estado == DestinoEstado.postado
            and destino.posted_at is not None and agora - destino.posted_at < BUSCANDO_LEMBRETE
            and not bloqueado):
        estado = "buscando"
    else:
        estado = "sem_vinculo"
    pode = _pode_ligar(destino)
    return schemas.Vinculo(
        estado=estado, video=None, metodo=None, vinculado_por=None, vinculado_em=None,
        candidatos=candidatos, pode_vincular=pode,
        motivo=None if pode else postagem.SEM_POST, **base)


# ---- ações do dono (rotas H) ----

def _video_do_link(db: Session, serie: Serie, conexao: Conexao, conta: Conta, link: str,
                   client: Any, agora: datetime) -> VideoRede:
    """Valida o link (R11) e devolve o vídeo da série, consultando a rede se ele ainda não
    foi descoberto."""
    rede_id = ler_link(link, conta.handle)
    video = db.scalar(select(VideoRede).where(VideoRede.serie_id == serie.id,
                                              VideoRede.rede_video_id == rede_id))
    if video is not None:
        return video
    leitor = registro.leitor_para(serie.rede)
    if leitor is None:
        raise ApiError(409, "metricas_indisponiveis", INDISPONIVEIS)
    try:
        _consumir(conexao.id, "video_query")
        lidos = leitor.consultar(_contexto(conexao.id, client), [rede_id])
    except SemPermissaoLeitura as e:
        raise ApiError(409, "metricas_indisponiveis", INDISPONIVEIS) from e
    except PedidoProibido:
        raise
    except (RedeErro, _Taxa) as e:
        raise ApiError(502, "rede_indisponivel", REDE_FORA) from e
    lido = next((v for v in lidos if str(v.id) == rede_id), None)
    if lido is None:
        raise ApiError(404, "post_nao_encontrado", NAO_ENCONTRADO.format(conta=conta.handle))
    return _garantir_video(db, serie, lido, agora)


def ligar(db: Session, actor: Actor, destino_id: uuid.UUID, body: schemas.VinculoIn,
          client: Any = None) -> Postagem:
    """`POST /api/destinos/{id}/vinculo` (**H**): escolher (`videoId`) ou colar (`link`).
    Num lembrete antes do clique, marca o destino como `postado` pelo `marcar_postado` humano
    (com o link colado como `posted_url`, ou nulo na escolha; R12, Q3 = A)."""
    agora = _agora()
    destino = postagem.get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, body.version, postagem.DESTINO_LABEL)
    if _vinculado(db, destino.id) is not None:
        raise ApiError(409, "destino_ja_vinculado", DESTINO_JA)
    if not _pode_ligar(destino):
        raise ApiError(409, "destino_sem_post", postagem.SEM_POST)
    ativa = serie_ativa(db, destino.conta_id)
    if ativa is None:
        raise ApiError(409, "metricas_indisponiveis", INDISPONIVEIS)
    serie, conexao = ativa
    conta = db.get(Conta, destino.conta_id)
    assert conta is not None
    if body.video_id is not None:
        video = db.get(VideoRede, body.video_id)
        if video is None or video.serie_id != serie.id:
            raise ApiError(404, "post_nao_encontrado", NAO_ENCONTRADO.format(conta=conta.handle))
        metodo = VinculoMetodo.escolha
    else:
        video = _video_do_link(db, serie, conexao, conta, body.link or "", client, agora)
        metodo = VinculoMetodo.link
    db.refresh(video, with_for_update=True)
    if video.destino_id is not None:
        raise ApiError(409, "video_ja_vinculado", JA_VINCULADO,
                       details={"destinoId": str(video.destino_id)})
    if _antes_do_clique(destino):
        postado_url = body.link.strip() if metodo == VinculoMetodo.link and body.link else None
        destino = postagem.marcar_postado(db, actor, destino.id, destino.version, postado_url)
    try:
        _ligar(db, actor, destino, video, metodo, agora)
    except IntegrityError as e:
        db.rollback()
        raise ApiError(409, "video_ja_vinculado", JA_VINCULADO) from e
    return destino


def desfazer(db: Session, actor: Actor, destino_id: uuid.UUID, version: int) -> Postagem:
    """`POST /api/destinos/{id}/vinculo/desfazer` (**H**, R11): anula o vínculo vivo (os 4
    campos juntos), tira o vídeo do automático, encerra a busca (`desfeito`) e volta o estado
    se foi o vínculo que o levou a `publicado`. O `postado` de um lembrete fica."""
    destino = postagem.get_destino_or_404(db, destino_id, lock=True)
    history.check_version(destino, version, postagem.DESTINO_LABEL)
    video = db.scalar(select(VideoRede).where(VideoRede.destino_id == destino.id)
                      .with_for_update())
    if video is None:
        raise ApiError(409, "sem_vinculo", SEM_VINCULO)
    serie = db.get(Serie, video.serie_id)
    assert serie is not None and serie.conta_id is not None
    metodo = video.vinculo_metodo.value if video.vinculo_metodo else None
    video.destino_id = None
    video.vinculo_metodo = None
    video.vinculado_por = None
    video.vinculado_em = None
    video.vinculo_automatico = False
    busca = db.get(BuscaPost, destino.id)
    agora = _agora()
    if busca is not None and busca.fim in (None, "vinculado"):
        _encerrar(busca, "desfeito", agora)
    db.flush()
    postagem.publicacao_pelo_vinculo(db, actor, destino, False, conta_do_video=serie.conta_id,
                                     metodo=metodo or "")
    return destino
