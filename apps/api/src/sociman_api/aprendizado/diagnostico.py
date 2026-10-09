"""Diagnóstico de distribuição (spec 023, US5; FR-048 a FR-050; research R10).

Sinais calculados na leitura (nunca gravados), cada um com o número que o sustenta:
- **conta:** `conta_nova` (menos de 30 dias desde a 1ª coleta, ou menos de 15 posts) e
  `travada` (> 60% dos medidos estagnados, R4);
- **post:** `muitos_no_dia` (> 3 no mesmo dia local), `intervalo_curto` (menos que
  `contas.intervalo_min_minutos` do post anterior), `fora_da_audiencia` (fora das 6 horas de
  maior ganho do mapa da audiência da 019, só com ≥ 500 views atribuídas), `repostagem` (o mesmo
  vídeo-fonte em outra conta, canal `sem_acordo` ou envio avulso), `curto` (< 10 s),
  `legenda_vazia` e `hashtags_demais` (> 8).

O checklist do que conferir no app é fixo em código. Nada aqui cria tarefa, muda destino,
notifica ou republica: é só leitura (as marcações do dono ficam em `conferencias.py`).
"""

import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, filtros, quando_postar
from sociman_api.analytics.base import PostAnalisado
from sociman_api.aprendizado import analise as an
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import fatores as fat
from sociman_api.aprendizado import schemas
from sociman_api.aprendizado.models import CHECKLIST_ITENS, Conferencia
from sociman_api.canais.models import CanalDireito, CanalFonte
from sociman_api.conteudos.models import Conteudo
from sociman_api.cortes.models import Corte
from sociman_api.envios.models import Envio, EnvioOrigem
from sociman_api.errors import ApiError
from sociman_api.metricas.models import Serie, VideoRede
from sociman_api.perfis.models import Conta
from sociman_api.perfis.service_perfis import get_perfil_or_404, user_refs
from sociman_api.postagem.models import Postagem

CHECKLIST: dict[str, tuple[str, str]] = {
    "restrito": ("Post restrito", (
        "No app, abra o post e veja se aparece \"restrito\" ou \"visibilidade limitada\" nas "
        "análises do vídeo.")),
    "nao_elegivel_para_voce": ("Não elegível para o Para Você", (
        "Confira se o app avisa que o vídeo não é elegível para recomendação.")),
    "nao_original": ("Conteúdo não original", (
        "Veja se há aviso de conteúdo não original ou reutilizado no post.")),
    "privacidade": ("Privacidade", (
        "Confirme que o post está público e que a conta não está privada.")),
    "musica": ("Música", "Confira se o som foi silenciado ou bloqueado por direitos."),
    "diretrizes": ("Diretrizes", "Veja se há aviso de violação das diretrizes da comunidade."),
}
assert tuple(CHECKLIST) == CHECKLIST_ITENS


def checklist() -> list[schemas.AprendizadoItemChecklist]:
    return [schemas.AprendizadoItemChecklist(item=k, titulo=t, texto=x)
            for k, (t, x) in CHECKLIST.items()]


def _sinal(tipo: str, alvo: str, alvo_id: uuid.UUID, numero: float | None,
           texto: str) -> schemas.AprendizadoSinal:
    return schemas.AprendizadoSinal(tipo=tipo, alvo=alvo, alvo_id=alvo_id,  # type: ignore[arg-type]
                                    numero=numero, texto=texto)


def _origens(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple]:
    """(vídeo-fonte, origem do envio, direito do canal) de cada post vinculado."""
    if not ids:
        return {}
    rows = db.execute(
        select(VideoRede.id, Envio.video_fonte_id, Envio.origem, CanalFonte.direito)
        .join(Postagem, Postagem.id == VideoRede.destino_id)
        .join(Conteudo, Conteudo.id == Postagem.conteudo_id)
        .join(Corte, Corte.id == Conteudo.corte_id)
        .join(Envio, Envio.id == Corte.envio_id)
        .outerjoin(CanalFonte, CanalFonte.id == Envio.canal_fonte_id)
        .where(VideoRede.id.in_(list(ids)))).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def _outras_contas(db: Session, fontes: set[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Por vídeo-fonte, as contas que já publicaram post dele."""
    if not fontes:
        return {}
    rows = db.execute(
        select(Envio.video_fonte_id, Serie.conta_id)
        .select_from(VideoRede).join(Serie, Serie.id == VideoRede.serie_id)
        .join(Postagem, Postagem.id == VideoRede.destino_id)
        .join(Conteudo, Conteudo.id == Postagem.conteudo_id)
        .join(Corte, Corte.id == Conteudo.corte_id)
        .join(Envio, Envio.id == Corte.envio_id)
        .where(Envio.video_fonte_id.in_(fontes), Serie.conta_id.is_not(None))).all()
    out: dict[uuid.UUID, set[uuid.UUID]] = {}
    for fonte, conta in rows:
        out.setdefault(fonte, set()).add(conta)
    return out


def _melhores_horas(db: Session, filtro: filtros.Filtro) -> set[int] | None:
    """As 6 horas locais de maior ganho da audiência (019); None sem 500 views atribuídas."""
    videos = base.videos_escopo(db, filtro)
    fotos = base.fotos_views(db, [v.video_id for v in videos], filtro.atual.fim)
    mapa = quando_postar.audiencia(videos, fotos, filtro.atual)
    por_hora: Counter[int] = Counter()
    for c in mapa.celulas:
        por_hora[c.hora] += c.valor or 0
    if sum(por_hora.values()) < K.AUDIENCIA_MIN_VIEWS:
        return None
    return {h for h, _ in por_hora.most_common(K.HORAS_AUDIENCIA)}


def sinais_dos_posts(db: Session, conta: Conta, posts: Sequence[PostAnalisado],
                     melhores: set[int] | None) -> list[schemas.AprendizadoSinal]:
    tz = ZoneInfo(filtros.fuso())
    out: list[schemas.AprendizadoSinal] = []
    por_dia = Counter(p.publicado_em.astimezone(tz).date() for p in posts)
    origens = _origens(db, [p.video_id for p in posts])
    outras = _outras_contas(db, {o[0] for o in origens.values() if o[0] is not None})
    anterior: PostAnalisado | None = None
    for p in sorted(posts, key=lambda x: x.publicado_em):
        vid = p.video_id
        dia = p.publicado_em.astimezone(tz).date()
        if por_dia[dia] > K.MUITOS_NO_DIA:
            out.append(_sinal("muitos_no_dia", "post", vid, por_dia[dia],
                              f"{por_dia[dia]} posts no mesmo dia (limite {K.MUITOS_NO_DIA})."))
        if anterior is not None and conta.intervalo_min_minutos:
            minutos = (p.publicado_em - anterior.publicado_em).total_seconds() / 60
            if minutos < conta.intervalo_min_minutos:
                out.append(_sinal("intervalo_curto", "post", vid, round(minutos),
                                  f"{round(minutos)} min do post anterior (mínimo da conta: "
                                  f"{conta.intervalo_min_minutos} min)."))
        anterior = p
        if melhores is not None and p.hora_local not in melhores:
            out.append(_sinal("fora_da_audiencia", "post", vid, p.hora_local,
                              f"Publicado às {p.hora_local:02d}h, fora das "
                              f"{K.HORAS_AUDIENCIA} horas de maior audiência da conta."))
        fonte, origem, direito = origens.get(vid, (None, None, None))
        repetido = fonte is not None and len(outras.get(fonte, set()) - {conta.id}) > 0
        avulso = origem in (EnvioOrigem.avulso_link, EnvioOrigem.avulso_arquivo)
        if repetido or avulso or direito == CanalDireito.sem_acordo:
            n = len(outras.get(fonte, set()) - {conta.id}) if fonte else 0
            motivo = ("o mesmo vídeo-fonte já foi postado em outra conta" if repetido
                      else "envio avulso" if avulso else "canal sem acordo")
            out.append(_sinal("repostagem", "post", vid, n,
                              f"Possível repostagem: {motivo}."))
        if p.duracao_s < K.CURTO_S:
            out.append(_sinal("curto", "post", vid, p.duracao_s,
                              f"{p.duracao_s} s: abaixo de {K.CURTO_S} s."))
        if p.titulo_curto == "Sem legenda":
            out.append(_sinal("legenda_vazia", "post", vid, 0, "Post sem legenda."))
        if len(p.hashtags) > K.HASHTAGS_DEMAIS:
            out.append(_sinal("hashtags_demais", "post", vid, len(p.hashtags),
                              f"{len(p.hashtags)} hashtags (mais de {K.HASHTAGS_DEMAIS})."))
    return out


def _conta_info(db: Session, conta: Conta, res: an.Resultado, agora: datetime
                ) -> tuple[list[schemas.AprendizadoSinal], an.ContaInfo | None]:
    info = next((c for c in res.contas if c.chave == conta.id), None)
    sinais: list[schemas.AprendizadoSinal] = []
    serie = db.scalar(select(Serie).where(Serie.conta_id == conta.id,
                                          Serie.anonimizada_em.is_(None)))
    dias = (agora - serie.criada_em).days if serie is not None else 0
    posts = info.medidos if info else 0
    if dias < K.CONTA_NOVA_DIAS or posts < K.CONTA_NOVA_POSTS:
        sinais.append(_sinal("conta_nova", "conta", conta.id, dias if dias < K.CONTA_NOVA_DIAS
                             else posts, f"Conta nova: {dias} dia(s) de coleta e {posts} "
                             "post(s) medidos; a rede ainda está testando a conta."))
    if info is not None and info.travada:
        sinais.append(_sinal("travada", "conta", conta.id,
                             round(100 * info.estagnados / info.medidos),
                             f"Distribuição travada: {info.estagnados} de {info.medidos} posts "
                             "estagnados."))
    return sinais, info


def calcular(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None = None,
             de=None, ate=None, agora: datetime | None = None) -> schemas.AprendizadoDiagnostico:
    get_perfil_or_404(db, perfil_id)
    agora = agora or datetime.now(UTC)
    res = an.calcular(db, perfil_id, conta_id, de=de, ate=ate, agora=agora)
    stmt = select(Conta).where(Conta.perfil_id == perfil_id, Conta.archived_at.is_(None))
    if conta_id is not None:
        stmt = stmt.where(Conta.id == conta_id)
    contas = []
    for conta in db.scalars(stmt.order_by(Conta.handle)):
        sinais, info = _conta_info(db, conta, res, agora)
        filtro = filtros.montar(db, de=res.de, ate=res.ate, perfil_id=perfil_id,
                                conta_id=conta.id, dia_atual=res.ate)
        posts = [p for p in base.posts(db, filtro, agora=agora) if not p.anonima]
        dos_posts = sinais_dos_posts(db, conta, posts, _melhores_horas(db, filtro))
        contas.append(schemas.AprendizadoDiagnosticoConta(
            conta=schemas.AprendizadoContaRef(id=conta.id, handle=conta.handle,
                                              rotulo=f"@{conta.handle}"),
            travada=bool(info and info.travada), estagnados=info.estagnados if info else 0,
            medidos=info.medidos if info else 0, sinais=[*sinais, *dos_posts],
            posts_com_sinais=len({s.alvo_id for s in dos_posts})))
    return schemas.AprendizadoDiagnostico(contas=contas, checklist=checklist())


def conferencias_out(db: Session, video_id: uuid.UUID) -> list[schemas.AprendizadoConferencia]:
    rows = {c.item: c for c in db.scalars(select(Conferencia).where(
        Conferencia.video_id == video_id))}
    users = user_refs(db, [c.updated_by for c in rows.values()])
    out = []
    for item in CHECKLIST:
        c = rows.get(item)
        out.append(schemas.AprendizadoConferencia(
            id=c.id if c else None, video_id=video_id, item=item,
            resultado=c.resultado.value if c else None,  # type: ignore[arg-type]
            nota=c.nota if c else None, updated_at=c.updated_at if c else None,
            updated_by=users.get(c.updated_by) if c and c.updated_by else None,
            version=c.version if c else 0))
    return out


def do_post(db: Session, video_id: uuid.UUID, agora: datetime | None = None
            ) -> schemas.AprendizadoPostDiagnostico:
    agora = agora or datetime.now(UTC)
    row = db.execute(select(VideoRede, Conta).join(Serie, Serie.id == VideoRede.serie_id)
                     .join(Conta, Conta.id == Serie.conta_id)
                     .where(VideoRede.id == video_id, Serie.anonimizada_em.is_(None))).first()
    if row is None:
        raise ApiError(404, "not_found", "Post não encontrado")
    video, conta = row
    tz = ZoneInfo(filtros.fuso())
    dia = video.publicado_em.astimezone(tz).date()
    filtro = filtros.montar(db, de=dia, ate=dia, perfil_id=conta.perfil_id, conta_id=conta.id,
                            dia_atual=max(dia, agora.astimezone(tz).date()))
    posts = [p for p in base.posts(db, filtro, agora=agora) if not p.anonima]
    alvo = next(p for p in posts if p.video_id == video.id)
    anteriores = base.posts(db, filtros.montar(db, perfil_id=conta.perfil_id, conta_id=conta.id,
                                               de=None, ate=dia, dia_atual=dia), agora=agora)
    contexto = [p for p in anteriores if not p.anonima and p.publicado_em <= alvo.publicado_em]
    janela = filtros.montar(db, perfil_id=conta.perfil_id, conta_id=conta.id,
                            de=None, ate=agora.astimezone(tz).date())
    sinais = [s for s in sinais_dos_posts(db, conta, contexto, _melhores_horas(db, janela))
              if s.alvo_id == video.id]
    estagnado = video.id in fat.estagnados(db, [alvo], agora)
    return schemas.AprendizadoPostDiagnostico(
        post=base.resumo(alvo), estagnado=estagnado, sinais=sinais,
        conferencias=conferencias_out(db, video.id), checklist=checklist())
