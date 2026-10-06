"""Anonimização da série ao desconectar (spec 016, research R13; FR-009; Q1 = A).

Só **UPDATE**, nunca DELETE, e irreversível (nenhum dado para desfazer é guardado). A ordem é
"congelar as características → cortar o elo": primeiro `features` recebe as características não
identificadoras de cada vídeo (lidas por join, como a exportação), depois os ids, links e textos
da rede e o elo com conta e destino viram nulos. As fotos não mudam (não têm identificador; o
trigger `metricas_so_insercao` recusaria).

Também daqui: as características do SociMan de cada vídeo (`caracteristicas`), usadas pela
exportação (vídeos vivos, por join na hora) e pela anonimização (congeladas em `features`).
"""

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from sociman_api.canais.models import CanalFonte
from sociman_api.config import get_settings
from sociman_api.conteudos.models import Conteudo
from sociman_api.cortes.models import Corte
from sociman_api.envios.models import Envio
from sociman_api.history import ActorLike
from sociman_api.metricas.models import (
    BuscaPost,
    FotoConta,
    FotoVideo,
    Serie,
    VideoRede,
    anonima_seq,
)
from sociman_api.metricas.studio.models import Importacao
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.postagem.models import Postagem

# As chaves de `features` (Q1 = A): nada de texto (gancho, legenda, hashtags, perfil, conta ou
# canal), só características.
FEATURES = ("origem", "modo_envio", "vinculo_metodo", "score", "canal_status_direito",
            "duracao_s", "hora_local", "dia_semana", "intervalo_post_anterior_h",
            "seguidores_na_publicacao", "gancho_caracteres", "hashtags_n")
ROTULO = "Conta anônima {n}"
_HASHTAG = re.compile(r"#\w+", re.UNICODE)


def hashtags_da_legenda(legenda: str | None) -> list[str]:
    return _HASHTAG.findall(legenda or "")


def caracteristicas(db: Session, videos: Sequence[VideoRede]) -> dict[uuid.UUID, dict[str, Any]]:
    """As colunas do SociMan de cada vídeo vivo (R16): as de `FEATURES` e as de texto que a
    exportação leva (`conta`, `perfil`, `gancho`, `canal_fonte`, `conteudo_id`, `destino_id`).
    Vídeo sem vínculo: só as características da rede, com `origem = fora`."""
    if not videos:
        return {}
    ids = [v.id for v in videos]
    series = {v.serie_id for v in videos}
    anterior = (
        select(VideoRede.id.label("id"),
               func.lag(VideoRede.publicado_em).over(
                   partition_by=VideoRede.serie_id,
                   order_by=(VideoRede.publicado_em, VideoRede.id)).label("anterior"))
        .where(VideoRede.serie_id.in_(series))
        .subquery())
    seguidores = (
        select(FotoConta.seguidores)
        .where(FotoConta.serie_id == VideoRede.serie_id,
               FotoConta.coletado_em <= VideoRede.publicado_em)
        .order_by(FotoConta.coletado_em.desc()).limit(1)
        .correlate(VideoRede).scalar_subquery())
    rows = db.execute(
        select(VideoRede, anterior.c.anterior, seguidores, Postagem, Conteudo, Corte,
               CanalFonte, Conta, Perfil)
        .join(anterior, anterior.c.id == VideoRede.id)
        .outerjoin(Postagem, Postagem.id == VideoRede.destino_id)
        .outerjoin(Conteudo, Conteudo.id == Postagem.conteudo_id)
        .outerjoin(Corte, Corte.id == Conteudo.corte_id)
        .outerjoin(Envio, Envio.id == Corte.envio_id)
        .outerjoin(CanalFonte, CanalFonte.id == Envio.canal_fonte_id)
        .join(Serie, Serie.id == VideoRede.serie_id)
        .outerjoin(Conta, Conta.id == Serie.conta_id)
        .outerjoin(Perfil, Perfil.id == Conta.perfil_id)
        .where(VideoRede.id.in_(ids))
    ).all()
    tz = ZoneInfo(get_settings().app_tz)
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for v, ant, seg, destino, conteudo, corte, canal, conta, perfil in rows:
        local = v.publicado_em.astimezone(tz)
        gancho = corte.hook_text if corte is not None else None
        hashtags = list(destino.hashtags or []) if destino is not None \
            else hashtags_da_legenda(v.legenda)
        out[v.id] = {
            "origem": conteudo.origem.value if conteudo is not None else "fora",
            "modo_envio": destino.modo.value if destino is not None else None,
            "vinculo_metodo": v.vinculo_metodo.value if v.vinculo_metodo else None,
            "score": corte.openshorts_score if corte is not None else None,
            "canal_status_direito": canal.direito.value if canal is not None else None,
            "duracao_s": v.duracao_s,
            "hora_local": local.hour,
            "dia_semana": local.weekday(),
            "intervalo_post_anterior_h": round((v.publicado_em - ant).total_seconds() / 3600, 3)
            if ant is not None else None,
            "seguidores_na_publicacao": seg,
            "gancho_caracteres": len(gancho) if gancho else None,
            "hashtags_n": len(hashtags),
            # texto: só a exportação de séries vivas (nunca em `features`)
            "conta": conta.handle if conta is not None else None,
            "perfil": perfil.name if perfil is not None else None,
            "gancho": gancho,
            "canal_fonte": canal.title if canal is not None else None,
            "conteudo_id": conteudo.id if conteudo is not None else None,
            "destino_id": destino.id if destino is not None else None,
        }
    return out


def contagem(db: Session, serie: Serie) -> tuple[int, int]:
    """(vídeos, fotos) da série; fotos = de vídeo + de conta (o texto da confirmação)."""
    videos = db.scalar(select(func.count()).select_from(VideoRede)
                       .where(VideoRede.serie_id == serie.id)) or 0
    fotos = db.scalar(select(func.count()).select_from(FotoVideo)
                      .join(VideoRede, VideoRede.id == FotoVideo.video_id)
                      .where(VideoRede.serie_id == serie.id)) or 0
    fotos += db.scalar(select(func.count()).select_from(FotoConta)
                       .where(FotoConta.serie_id == serie.id)) or 0
    return int(videos), int(fotos)


def serie(db: Session, alvo: Serie, actor: ActorLike, agora: datetime | None = None
          ) -> tuple[int, int]:
    """Anonimiza a série (R13), na transação de quem chama (o `desconectar`). Devolve
    `(vídeos, fotos)` para a versão da conexão. Só UPDATE; as contagens de linhas não mudam."""
    agora = agora or datetime.now(UTC)
    if alvo.anonimizada_em is not None:
        return contagem(db, alvo)
    conta_id = alvo.conta_id
    videos = list(db.scalars(select(VideoRede).where(VideoRede.serie_id == alvo.id,
                                                     VideoRede.anonimizado_em.is_(None))))
    # 1. congelar as características (antes de cortar o elo)
    dados = caracteristicas(db, videos)
    if videos:
        db.execute(update(VideoRede), [
            {"id": v.id, "features": {k: dados[v.id][k] for k in FEATURES}} for v in videos])
    # 2. cortar o elo: ids, links, textos, vínculo e fila
    db.execute(
        update(VideoRede).where(VideoRede.serie_id == alvo.id,
                                VideoRede.anonimizado_em.is_(None))
        .values(rede_video_id=None, share_url=None, legenda=None, titulo=None, destino_id=None,
                vinculo_metodo=None, vinculado_por=None, vinculado_em=None,
                proxima_coleta_em=None, anonimizado_em=agora,
                publicado_em=func.date_trunc("hour", VideoRede.publicado_em))
        .execution_options(synchronize_session=False))
    # 3. buscas dos destinos da conta: sem o post id; as abertas se encerram
    if conta_id is not None:
        destinos = select(Postagem.id).where(Postagem.conta_id == conta_id)
        db.execute(update(BuscaPost).where(BuscaPost.destino_id.in_(destinos))
                   .values(post_id=None).execution_options(synchronize_session=False))
        db.execute(update(BuscaPost).where(BuscaPost.destino_id.in_(destinos),
                                           BuscaPost.encerrada_em.is_(None))
                   .values(fim="anonimizada", encerrada_em=agora, proxima_em=None)
                   .execution_options(synchronize_session=False))
    # 4. a série: sem conta, com o rótulo da sequência global
    n = int(db.scalar(select(anonima_seq.next_value())))
    alvo.conta_id = None
    alvo.rotulo = ROTULO.format(n=n)
    alvo.anonima_n = n
    alvo.anonimizada_em = agora
    alvo.anonimizada_por = actor.user_id
    alvo.varredura_cursor = None
    alvo.lista_proxima_em = alvo.conta_proxima_em = None
    alvo.ultimo_erro_codigo = alvo.ultimo_erro_motivo = alvo.ultimo_erro_em = None
    alvo.adiar_ate = None
    # 5. spec 020 (R9): as importações do Studio perdem os nomes dos arquivos (têm o @); os dias
    # importados ficam (só números e dia; o trigger só de inserção não dispara)
    db.execute(update(Importacao).where(Importacao.serie_id == alvo.id)
               .values(nomes_arquivos=None).execution_options(synchronize_session=False))
    db.flush()
    db.expire_all()
    return contagem(db, alvo)


def importacoes(db: Session, serie_id: uuid.UUID) -> int:
    """Quantas importações do Studio a série tem (o `details.importacoes` da anonimização)."""
    return int(db.scalar(select(func.count()).select_from(Importacao)
                         .where(Importacao.serie_id == serie_id)) or 0)
