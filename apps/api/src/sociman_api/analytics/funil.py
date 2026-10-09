"""Funil de produção (spec 019, US6; FR-028/FR-029; research R7).

Coorte: os envios **enviados no período** (`sent_at`, sem `selecionado`/`descartado`) do escopo
(o perfil do filtro, ou o da conta filtrada). Etapas:

1. `enviados`: esses envios;
2. `cortes`: os cortes gerados por eles;
3. `aprovados`: os conteúdos desses cortes com ao menos um destino aprovado (`aprovado_em`, a
   decisão humana; o "Aplicar marca" pode ser automático e não serve);
4. `publicados`: os destinos deles em `postado`/`publicado` (posts; um conteúdo pode virar
   mais de um);
5. `acima_patamar`: os posts cujo vídeo ligado tem views em 24 h ≥ `patamar` (FR-028 fixa o
   marco de 24 h, independente da medida escolhida).

Os destinos respeitam conta e rede do filtro. `conversao_pct` = n ÷ n da etapa anterior (pode
passar de 1: um envio gera vários cortes). `perdas` de uma etapa = o que saiu dela sem chegar à
seguinte, por motivo. `tempo_mediano_h` = mediana do tempo para chegar à etapa: processamento do
envio (`started_at → finished_at`) nos cortes, criação do corte → 1ª aprovação nos aprovados,
aprovação → publicação nos publicados.

Custo de IA (só dono): soma de `ia_chamadas.custo_usd` dos conteúdos da coorte, e por mil views
das views atuais dos vídeos ligados a eles. Sem envio no período, `etapas = []`. Só leitura.
"""

import uuid
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, estatistica, schemas
from sociman_api.analytics.filtros import Filtro
from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.envios.models import Envio, EnvioStatus
from sociman_api.ia.models import IaChamada
from sociman_api.metricas import consulta
from sociman_api.metricas.models import VideoRede
from sociman_api.perfis.models import Conta
from sociman_api.postagem.models import DestinoEstado, Postagem

NAO_ENVIADOS = (EnvioStatus.selecionado, EnvioStatus.descartado)
PUBLICADOS = (DestinoEstado.postado, DestinoEstado.publicado)
MARCO_PATAMAR = "h24"


def _horas(segundos: Iterable[float]) -> float | None:
    m = estatistica.mediana([s / 3600 for s in segundos])
    return round(m, 4) if m is not None else None


def _perdas(motivos: Iterable[str]) -> list[schemas.Perda]:
    return [schemas.Perda(motivo=m, n=n) for m, n in Counter(motivos).most_common()]


def _perfil_do_escopo(db: Session, filtro: Filtro) -> uuid.UUID | None:
    if filtro.conta_id is not None:
        return db.scalar(select(Conta.perfil_id).where(Conta.id == filtro.conta_id))
    return filtro.perfil_id


def _destinos(db: Session, filtro: Filtro, conteudos: list[uuid.UUID]) -> list[Postagem]:
    if not conteudos:
        return []
    stmt = (select(Postagem).join(Conta, Conta.id == Postagem.conta_id)
            .where(Postagem.conteudo_id.in_(conteudos)))
    if filtro.conta_id is not None:
        stmt = stmt.where(Postagem.conta_id == filtro.conta_id)
    if filtro.rede is not None:
        stmt = stmt.where(Conta.platform == filtro.rede)
    return list(db.scalars(stmt.order_by(Postagem.created_at, Postagem.id)))


def _etapa(chave: str, n: int, anterior: int | None, perdas: list[schemas.Perda],
           tempo: float | None) -> schemas.EtapaFunil:
    conv = n / anterior if anterior else None
    return schemas.EtapaFunil(chave=chave, n=n, conversao_pct=conv, perdas=perdas,
                              tempo_mediano_h=tempo)


def _motivo_corte(corte: Corte, destinos: list[Postagem]) -> str:
    if corte.archived_at is not None:
        return "arquivado"
    if corte.status == CorteStatus.falhou:
        return "falhou"
    if any(d.recusado_em is not None for d in destinos):
        return "recusado"
    if corte.status == CorteStatus.revisao:
        return "em_revisao"
    return "sem_aprovacao"


def _motivo_aprovado(destinos: list[Postagem]) -> str:
    aprovados = [d for d in destinos if d.aprovado_em is not None]
    if any(d.estado == DestinoEstado.falhou for d in aprovados):
        return "falhou"
    if aprovados and all(d.archived_at is not None for d in aprovados):
        return "arquivado"
    return "aguardando_publicacao"


def calcular(db: Session, filtro: Filtro, patamar: int, com_custo: bool,
           agora: datetime | None = None) -> schemas.FunilOut:
    agora = agora or datetime.now(ZoneInfo("UTC"))
    contexto = base.contexto(filtro, base.posts(db, filtro, agora=agora))
    perfil_id = _perfil_do_escopo(db, filtro)
    stmt = select(Envio).where(Envio.sent_at >= filtro.atual.ini, Envio.sent_at < filtro.atual.fim,
                               Envio.status.not_in(NAO_ENVIADOS))
    if perfil_id is not None:
        stmt = stmt.where(Envio.perfil_id == perfil_id)
    envios = list(db.scalars(stmt))
    cortes = list(db.scalars(select(Corte).where(Corte.envio_id.in_([e.id for e in envios]))
                             .order_by(Corte.created_at, Corte.id))) if envios else []
    ids = [c.id for c in cortes]  # conteúdo de origem `corte`: mesmo id
    destinos = _destinos(db, filtro, ids)
    por_conteudo: dict[uuid.UUID, list[Postagem]] = {}
    for d in destinos:
        por_conteudo.setdefault(d.conteudo_id, []).append(d)

    aprovados = {cid: min(d.aprovado_em for d in ds if d.aprovado_em is not None)
                 for cid, ds in por_conteudo.items()
                 if any(d.aprovado_em is not None for d in ds)}
    publicados = [d for d in destinos if d.estado in PUBLICADOS]
    videos = {v.destino_id: v for v in db.scalars(select(VideoRede).where(
        VideoRede.destino_id.in_([d.id for d in destinos])))} if destinos else {}
    marcos = consulta.marcos(db, [videos[d.id] for d in publicados if d.id in videos], agora)

    acima, motivos_pub = 0, []
    for d in publicados:
        v = videos.get(d.id)
        if v is None:
            motivos_pub.append("sem_video")
            continue
        m = getattr(marcos[v.id], MARCO_PATAMAR).views
        if m.valor is not None and m.valor >= patamar:
            acima += 1
        elif m.motivo == "ainda_nao":
            motivos_pub.append("aguardando_24h")
        elif m.valor is None:
            motivos_pub.append("sem_dado")
        else:
            motivos_pub.append("abaixo_do_patamar")

    criado = {c.id: c.created_at for c in cortes}
    pub_por_conteudo = {d.conteudo_id for d in publicados}
    etapas = [] if not envios else [
        _etapa("enviados", len(envios), None,
               _perdas(e.status.value if e.status in (EnvioStatus.sem_clipes, EnvioStatus.falhou)
                       else "em_andamento" for e in envios
                       if e.status != EnvioStatus.pronto),
               None),
        _etapa("cortes", len(cortes), len(envios),
               _perdas(_motivo_corte(c, por_conteudo.get(c.id, [])) for c in cortes
                       if c.id not in aprovados),
               _horas((e.finished_at - e.started_at).total_seconds() for e in envios
                      if e.started_at is not None and e.finished_at is not None)),
        _etapa("aprovados", len(aprovados), len(cortes),
               _perdas(_motivo_aprovado(por_conteudo[cid]) for cid in aprovados
                       if cid not in pub_por_conteudo),
               _horas((em - criado[cid]).total_seconds() for cid, em in aprovados.items())),
        _etapa("publicados", len(publicados), len(aprovados), _perdas(motivos_pub),
               _horas((d.posted_at - d.aprovado_em).total_seconds() for d in publicados
                      if d.posted_at is not None and d.aprovado_em is not None)),
        _etapa("acima_patamar", acima, len(publicados), [], None),
    ]

    custo = por_mil = None
    if com_custo:
        custo = db.scalar(select(func.coalesce(func.sum(IaChamada.custo_usd), 0))
                          .where(IaChamada.conteudo_id.in_(ids))) if ids else Decimal(0)
        custo = Decimal(custo)
        ultimas = consulta._ultimas(db, [v.id for v in videos.values()])
        views = sum(f.views or 0 for f in ultimas.values())
        por_mil = custo / views * 1000 if views else None
    return schemas.FunilOut(contexto=contexto, etapas=etapas, patamar=patamar,
                            custo_ia_usd=custo, custo_por_mil_views_usd=por_mil)
