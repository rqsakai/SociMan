"""Valor efetivo, ganhos diários da coleta e cobertura (research R6; data-model "Regras
derivadas"). Só leitura: o `analytics/` importa daqui, nunca o contrário.

- **Dia coberto pela coleta:** `primeiro_dia_coberto(série) = dia_APP_TZ(1ª coleta) + 1`. O dia
  da 1ª coleta não é coberto (a conta da API soma nele as views da vida inteira dos vídeos
  antigos); sem coleta, nenhum dia é coberto.
- **Valor efetivo do Studio:** por (série, dia, seção), a linha da importação **ativa** mais
  antiga (`criada_em`, `id`) que tem a seção.
- **Fonte do dia:** coberto → `coletado`; não coberto com Studio efetivo → `studio`; senão
  `coletado` (o cálculo da 019).
- **Ganhos diários da coleta** (`api_por_dia`): por série e dia, a soma dos ganhos dos vídeos
  (última foto antes do fim do dia − última antes do início; 0 sem foto antes; nunca negativo;
  só fotos com o contador) e os seguidores ganhos (última foto da conta antes do fim − última
  antes do início, ou a 1ª do dia). Somar os dias dá o mesmo que o delta do período da 019.
"""

import bisect
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, union_all
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from sociman_api.config import get_settings
from sociman_api.metricas.models import FotoConta, FotoVideo, VideoRede
from sociman_api.metricas.studio.models import DiaStudio, Importacao, ImportacaoEstado

CONTADORES = ("views", "likes", "comments", "shares")
COLETADO, STUDIO = "coletado", "studio"


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


def inicio_do_dia(dia: date) -> datetime:
    return datetime.combine(dia, time.min, tz())


def intervalo(de: date, ate: date) -> list[date]:
    return [de + timedelta(days=k) for k in range((ate - de).days + 1)]


# ---- dia coberto ----

def primeira_coleta(db: Session, serie_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    """O instante da 1ª foto (de conta ou de vídeo) de cada série que já teve coleta."""
    ids = list(serie_ids)
    if not ids:
        return {}
    contas = (select(FotoConta.serie_id.label("serie_id"),
                     func.min(FotoConta.coletado_em).label("em"))
              .where(FotoConta.serie_id.in_(ids)).group_by(FotoConta.serie_id))
    videos = (select(VideoRede.serie_id.label("serie_id"),
                     func.min(FotoVideo.coletado_em).label("em"))
              .join(VideoRede, VideoRede.id == FotoVideo.video_id)
              .where(VideoRede.serie_id.in_(ids)).group_by(VideoRede.serie_id))
    juntas = union_all(contas, videos).subquery()
    return {sid: em for sid, em in db.execute(
        select(juntas.c.serie_id, func.min(juntas.c.em)).group_by(juntas.c.serie_id))}


def primeiro_dia_coberto(db: Session, serie_ids: Iterable[uuid.UUID]
                         ) -> dict[uuid.UUID, date | None]:
    ids = list(serie_ids)
    primeiras = primeira_coleta(db, ids)
    fuso = tz()
    return {sid: (primeiras[sid].astimezone(fuso).date() + timedelta(days=1))
            if sid in primeiras else None for sid in ids}


def coberto(dia: date, primeiro: date | None) -> bool:
    return primeiro is not None and dia >= primeiro


# ---- valor efetivo do Studio ----

@dataclass(frozen=True)
class ValorVisaoGeral:
    importacao_id: uuid.UUID
    views: int
    visitas_perfil: int | None
    likes: int | None
    comments: int | None
    shares: int | None

    def numeros(self) -> tuple:
        return (self.views, self.visitas_perfil, self.likes, self.comments, self.shares)


@dataclass(frozen=True)
class ValorSeguidores:
    importacao_id: uuid.UUID
    seguidores: int
    seguidores_dif: int | None

    def numeros(self) -> tuple:
        return (self.seguidores, self.seguidores_dif)


@dataclass
class DiaEfetivo:
    visao_geral: ValorVisaoGeral | None = None
    seguidores: ValorSeguidores | None = None


def dias(db: Session, serie_ids: Iterable[uuid.UUID], de: date | None = None,
         ate: date | None = None) -> dict[uuid.UUID, dict[date, DiaEfetivo]]:
    """O valor efetivo de cada seção por série e dia (só importações ativas)."""
    ids = list(serie_ids)
    out: dict[uuid.UUID, dict[date, DiaEfetivo]] = {}
    if not ids:
        return out
    for tem in (DiaStudio.tem_visao_geral, DiaStudio.tem_seguidores):
        stmt = (select(DiaStudio)
                .join(Importacao, Importacao.id == DiaStudio.importacao_id)
                .where(Importacao.estado == ImportacaoEstado.ativa, tem.is_(True),
                       DiaStudio.serie_id.in_(ids))
                .order_by(DiaStudio.serie_id, DiaStudio.dia, Importacao.criada_em,
                          Importacao.id)
                .ext(distinct_on(DiaStudio.serie_id, DiaStudio.dia)))
        if de is not None:
            stmt = stmt.where(DiaStudio.dia >= de)
        if ate is not None:
            stmt = stmt.where(DiaStudio.dia <= ate)
        for d in db.scalars(stmt):
            alvo = out.setdefault(d.serie_id, {}).setdefault(d.dia, DiaEfetivo())
            if tem is DiaStudio.tem_visao_geral:
                alvo.visao_geral = ValorVisaoGeral(d.importacao_id, int(d.views),  # type: ignore[arg-type]
                                                   d.visitas_perfil, d.likes, d.comments,
                                                   d.shares)
            else:
                alvo.seguidores = ValorSeguidores(d.importacao_id, int(d.seguidores),  # type: ignore[arg-type]
                                                  d.seguidores_dif)
    return out


def ganho_seguidores(dia: date, dias_serie: dict[date, DiaEfetivo]) -> int | None:
    """Seguidores ganhos num dia do Studio: a diferença do arquivo; sem ela, o total do dia
    menos o do dia anterior (None se faltar)."""
    atual = dias_serie.get(dia)
    if atual is None or atual.seguidores is None:
        return None
    if atual.seguidores.seguidores_dif is not None:
        return atual.seguidores.seguidores_dif
    antes = dias_serie.get(dia - timedelta(days=1))
    if antes is None or antes.seguidores is None:
        return None
    return atual.seguidores.seguidores - antes.seguidores.seguidores


# ---- ganhos diários da coleta (API) ----

@dataclass
class DiaApi:
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    tem_dado: bool = False  # algum vídeo da série tinha foto até o fim do dia
    seguidores_dif: int | None = None  # None: nenhuma foto da conta até o fim do dia
    seguidores_fim: int | None = None


def _nos_limites(fotos: Sequence[tuple[datetime, int]], limites: Sequence[datetime]
                 ) -> list[int | None]:
    """O valor da última foto antes de cada limite (None sem foto antes), numa só passada."""
    out: list[int | None] = []
    i, ultimo = 0, None
    for limite in limites:
        while i < len(fotos) and fotos[i][0] < limite:
            ultimo = fotos[i][1]
            i += 1
        out.append(ultimo)
    return out


def api_por_dia(db: Session, serie_ids: Iterable[uuid.UUID], de: date, ate: date
                ) -> dict[uuid.UUID, dict[date, DiaApi]]:
    """Os ganhos da coleta por série e dia de `APP_TZ` (ver o docstring do módulo)."""
    ids = list(serie_ids)
    dias_ = intervalo(de, ate)
    out: dict[uuid.UUID, dict[date, DiaApi]] = {sid: {d: DiaApi() for d in dias_} for sid in ids}
    if not ids:
        return out
    fuso = tz()
    # o início de cada dia e o fim do último: o dia k vai de limites[k] a limites[k + 1]
    limites = [datetime.combine(d, time.min, fuso) for d in dias_]
    limites.append(datetime.combine(ate + timedelta(days=1), time.min, fuso))
    fotos: dict[tuple[uuid.UUID, uuid.UUID, str], list[tuple[datetime, int]]] = {}
    for sid, vid, quando, *valores in db.execute(
            select(VideoRede.serie_id, FotoVideo.video_id, FotoVideo.coletado_em,
                   FotoVideo.views, FotoVideo.likes, FotoVideo.comments, FotoVideo.shares)
            .join(VideoRede, VideoRede.id == FotoVideo.video_id)
            .where(VideoRede.serie_id.in_(ids), FotoVideo.coletado_em < limites[-1])
            .order_by(FotoVideo.video_id, FotoVideo.coletado_em, FotoVideo.id)):
        for nome, valor in zip(CONTADORES, valores, strict=True):
            if valor is not None:
                fotos.setdefault((sid, vid, nome), []).append((quando, int(valor)))
    for (sid, _, nome), fs in fotos.items():
        por_dia = out[sid]
        nos = _nos_limites(fs, limites)
        for k, dia in enumerate(dias_):
            depois = nos[k + 1]
            if depois is None:
                continue
            d = por_dia[dia]
            if nome == "views":
                d.tem_dado = True
            setattr(d, nome, getattr(d, nome) + max(0, depois - (nos[k] or 0)))

    contas: dict[uuid.UUID, list[tuple[datetime, int]]] = {sid: [] for sid in ids}
    for sid, quando, n in db.execute(
            select(FotoConta.serie_id, FotoConta.coletado_em, FotoConta.seguidores)
            .where(FotoConta.serie_id.in_(ids), FotoConta.coletado_em < limites[-1],
                   FotoConta.seguidores.is_not(None))
            .order_by(FotoConta.serie_id, FotoConta.coletado_em, FotoConta.id)):
        contas[sid].append((quando, int(n)))
    for sid, fs in contas.items():
        nos = _nos_limites(fs, limites)
        for k, dia in enumerate(dias_):
            fim_seg = nos[k + 1]
            if fim_seg is None:
                continue
            inicio = nos[k]
            if inicio is None:  # sem foto antes do dia: a 1ª do dia é a base
                inicio = fs[bisect.bisect_left(fs, limites[k], key=lambda f: f[0])][1]
            out[sid][dia].seguidores_dif = fim_seg - inicio
            out[sid][dia].seguidores_fim = fim_seg
    return out


# ---- cobertura (US5) ----

def faixas(dias_: Iterable[date]) -> list[tuple[date, date]]:
    """Dias → intervalos contínuos, em ordem."""
    out: list[list[date]] = []
    for d in sorted(set(dias_)):
        if out and d == out[-1][1] + timedelta(days=1):
            out[-1][1] = d
        else:
            out.append([d, d])
    return [(a, b) for a, b in out]
