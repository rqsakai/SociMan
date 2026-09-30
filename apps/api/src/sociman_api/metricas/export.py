"""Exportação do dataset de métricas (spec 016, research R16; FR-008, SC-005).

Um ZIP com `fotos_videos`, `videos`, `fotos_conta` (CSV ou JSON Lines), `dicionario.csv` e
`LEIAME.txt`. Cabeçalhos e ordem vêm de `metricas/dicionario.py` (fonte única).

- CSV em UTF-8 **com BOM**, vírgula, ponto decimal e datas ISO 8601 com o offset de São Paulo;
  JSON Lines com as mesmas chaves;
- `video_ref` é o uuid do SociMan, nunca o id da rede;
- vídeo sem vínculo: colunas do SociMan vazias e `origem = fora`; série anônima (só com
  `incluir_anonimas`): `serie = "Conta anônima N"`, colunas identificadoras vazias e as
  características de `features`;
- montagem por streaming do banco (`yield_per`). Acima de 32 MB estimados (~120 B por foto), o
  temporário vai para o HD (`<data_dir>/work/exports`), e o `datadir` recusa antes de gravar
  (503 `storage_unavailable`, 507 `storage_full`). Abaixo disso, tudo fica na memória.
"""

import csv
import io
import json
import uuid
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import IO, Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api import datadir
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.metricas import anonimizar, consulta, dicionario
from sociman_api.metricas.models import FotoConta, FotoVideo, Serie, VideoRede
from sociman_api.perfis.models import Conta

Formato = Literal["csv", "jsonl"]

PERIODO_MAX_DIAS = 400
PERIODO_INVALIDO = "Escolha um período de até 400 dias"
LIMITE_MEMORIA = 32 * 1024 * 1024
BYTES_POR_FOTO = 120
LOTE = 2000
LOTE_MARCOS = 500
MARCOS = (("1h", "h1"), ("24h", "h24"), ("7d", "d7"), ("30d", "d30"))


@dataclass(frozen=True)
class Filtro:
    formato: Formato
    de: date
    ate: date
    perfil_id: uuid.UUID | None = None
    conta_id: uuid.UUID | None = None
    incluir_anonimas: bool = False


def validar_periodo(de: date | None, ate: date | None) -> tuple[date, date]:
    if de is None or ate is None or de > ate or (ate - de).days + 1 > PERIODO_MAX_DIAS:
        raise ApiError(400, "periodo_invalido", PERIODO_INVALIDO)
    return de, ate


def nome_arquivo(de: date, ate: date) -> str:
    return f"sociman-metricas-{de:%Y%m%d}-{ate:%Y%m%d}.zip"


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


def _intervalo(filtro: Filtro) -> tuple[datetime, datetime]:
    """[de 00:00, ate + 1 dia 00:00) em São Paulo."""
    tz = _tz()
    inicio = datetime.combine(filtro.de, time(0), tz)
    fim = datetime.combine(filtro.ate + timedelta(days=1), time(0), tz)
    return inicio.astimezone(UTC), fim.astimezone(UTC)


def _series(filtro: Filtro):
    """Condições das séries do filtro (perfil, conta e anônimas)."""
    conds = []
    if filtro.conta_id is not None:
        conds.append(Serie.conta_id == filtro.conta_id)
    if filtro.perfil_id is not None:
        conds.append(Serie.conta_id.in_(select(Conta.id).where(
            Conta.perfil_id == filtro.perfil_id)))
    if not filtro.incluir_anonimas:
        conds.append(Serie.anonimizada_em.is_(None))
    return conds


# ---- valores ----

def _valor(v: Any, tz: ZoneInfo) -> Any:
    """Tipos do JSON Lines (e base do CSV)."""
    if isinstance(v, datetime):
        return v.astimezone(tz).isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, Decimal):
        return float(v)
    return v


def _csv(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


class _Escritor:
    """Um arquivo do ZIP, em CSV ou JSON Lines, com as colunas do dicionário."""

    def __init__(self, zf: zipfile.ZipFile, arquivo: str, formato: Formato):
        self.colunas = dicionario.colunas(arquivo)
        self.formato = formato
        self.tz = _tz()
        bruto = zf.open(f"{arquivo}.{formato}", "w", force_zip64=True)
        encoding = "utf-8-sig" if formato == "csv" else "utf-8"
        self.texto = io.TextIOWrapper(bruto, encoding=encoding, newline="")
        if formato == "csv":
            self.csv = csv.writer(self.texto, lineterminator="\r\n")
            self.csv.writerow(self.colunas)

    def linha(self, dados: dict[str, Any]) -> None:
        valores = [_valor(dados.get(c), self.tz) for c in self.colunas]
        if self.formato == "csv":
            self.csv.writerow([_csv(v) for v in valores])
        else:
            self.texto.write(json.dumps(dict(zip(self.colunas, valores, strict=True)),
                                        ensure_ascii=False) + "\n")

    def fechar(self) -> None:
        self.texto.close()


# ---- linhas ----

def _fotos_videos(db: Session, filtro: Filtro) -> Iterator[dict[str, Any]]:
    inicio, fim = _intervalo(filtro)
    stmt = (select(FotoVideo)
            .join(VideoRede, VideoRede.id == FotoVideo.video_id)
            .join(Serie, Serie.id == VideoRede.serie_id)
            .where(FotoVideo.coletado_em >= inicio, FotoVideo.coletado_em < fim,
                   *_series(filtro))
            .order_by(FotoVideo.video_id, FotoVideo.coletado_em, FotoVideo.id)
            .execution_options(yield_per=LOTE))
    for f in db.scalars(stmt):
        yield {"video_ref": f.video_id, "coletado_em": f.coletado_em,
               "idade_h": round(f.idade_s / 3600, 3), "alvo_idade_h": round(f.alvo_idade_min / 60, 3),
               "views": f.views, "likes": f.likes, "comments": f.comments, "shares": f.shares}


def _marcos_colunas(marcos: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if marcos is None:
        return out
    for rotulo, campo in MARCOS:
        mv = getattr(marcos, campo).views
        out[f"views_{rotulo}"] = mv.valor
        out[f"views_{rotulo}_estimado"] = mv.estimado if mv.valor is not None else None
    d7 = marcos.d7
    partes = (d7.views, d7.likes, d7.comments, d7.shares)
    if all(p.valor is not None for p in partes):
        views = d7.views.valor
        out["engajamento_7d"] = round((d7.likes.valor + d7.comments.valor + d7.shares.valor)
                                      / views, 6) if views else 0.0
        out["engajamento_7d_estimado"] = any(p.estimado for p in partes)
    return out


def _linha_video(v: VideoRede, serie: Serie, carac: dict[str, Any] | None,
                 marcos: Any) -> dict[str, Any]:
    anonimo = v.anonimizado_em is not None
    base = dict(v.features or {}) if anonimo else dict(carac or {})
    linha: dict[str, Any] = {k: base.get(k) for k in anonimizar.FEATURES}
    linha.update({
        "video_ref": v.id,
        "serie": serie.rotulo if serie.anonimizada_em is not None else str(serie.id),
        "rede": serie.rede.value,
        "publicado_em": v.publicado_em,
        "duracao_s": v.duracao_s,
        "disponivel": v.disponivel,
        "vinculo_metodo": base.get("vinculo_metodo"),
    })
    if not anonimo:
        conta = base.get("conta")
        linha.update({
            "conta": f"@{conta}" if conta else None, "perfil": base.get("perfil"),
            "legenda": v.legenda, "url": v.share_url,
            "hashtags": " ".join(anonimizar.hashtags_da_legenda(v.legenda)) or None,
            "gancho": base.get("gancho"), "canal_fonte": base.get("canal_fonte"),
            "conteudo_id": base.get("conteudo_id"), "destino_id": base.get("destino_id"),
        })
    linha.update(_marcos_colunas(marcos))
    return linha


def _lotes(itens: Iterable[Any], n: int) -> Iterator[list[Any]]:
    lote: list[Any] = []
    for item in itens:
        lote.append(item)
        if len(lote) >= n:
            yield lote
            lote = []
    if lote:
        yield lote


def _videos(db: Session, filtro: Filtro, agora: datetime) -> Iterator[dict[str, Any]]:
    """Os vídeos com ao menos uma foto no período (os mesmos `video_ref` de `fotos_videos`)."""
    inicio, fim = _intervalo(filtro)
    com_foto = select(FotoVideo.video_id).where(FotoVideo.coletado_em >= inicio,
                                                FotoVideo.coletado_em < fim)
    ids = db.scalars(
        select(VideoRede.id).join(Serie, Serie.id == VideoRede.serie_id)
        .where(VideoRede.id.in_(com_foto), *_series(filtro))
        .order_by(VideoRede.publicado_em, VideoRede.id)).all()
    # Em lotes, sem cursor aberto: as características e os marcos consultam no meio.
    for pedaco in _lotes(ids, LOTE_MARCOS):
        lote = db.execute(select(VideoRede, Serie).join(Serie, Serie.id == VideoRede.serie_id)
                          .where(VideoRede.id.in_(pedaco))
                          .order_by(VideoRede.publicado_em, VideoRede.id)).all()
        videos = [v for v, _ in lote]
        vivos = [v for v in videos if v.anonimizado_em is None]
        carac = anonimizar.caracteristicas(db, vivos)
        marcos = consulta.marcos(db, videos, agora)
        for v, serie in lote:
            yield _linha_video(v, serie, carac.get(v.id), marcos.get(v.id))


def _fotos_conta(db: Session, filtro: Filtro) -> Iterator[dict[str, Any]]:
    inicio, fim = _intervalo(filtro)
    stmt = (select(FotoConta, Serie, Conta.handle)
            .join(Serie, Serie.id == FotoConta.serie_id)
            .outerjoin(Conta, Conta.id == Serie.conta_id)
            .where(FotoConta.coletado_em >= inicio, FotoConta.coletado_em < fim,
                   *_series(filtro))
            .order_by(FotoConta.serie_id, FotoConta.janela_em, FotoConta.id)
            .execution_options(yield_per=LOTE))
    for f, serie, handle in db.execute(stmt):
        anonima = serie.anonimizada_em is not None
        yield {"serie": serie.rotulo if anonima else str(serie.id),
               "conta": None if anonima or not handle else f"@{handle}",
               "coletado_em": f.coletado_em, "janela": f.janela_em,
               "seguidores": f.seguidores, "seguindo": f.seguindo, "curtidas": f.curtidas,
               "videos": f.videos}


# ---- montagem ----

def estimativa(db: Session, filtro: Filtro) -> int:
    """Bytes estimados pela contagem de fotos (R16)."""
    inicio, fim = _intervalo(filtro)
    fotos = db.scalar(
        select(func.count()).select_from(FotoVideo)
        .join(VideoRede, VideoRede.id == FotoVideo.video_id)
        .join(Serie, Serie.id == VideoRede.serie_id)
        .where(FotoVideo.coletado_em >= inicio, FotoVideo.coletado_em < fim, *_series(filtro)))
    return int(fotos or 0) * BYTES_POR_FOTO


def _destino(tamanho: int) -> IO[bytes]:
    """Memória até 32 MB; acima disso, o HD (conferido antes de gravar)."""
    if tamanho <= LIMITE_MEMORIA:
        return io.BytesIO()
    datadir.ensure_writable(tamanho)
    pasta = Path(get_settings().data_dir) / "work" / "exports"
    pasta.mkdir(parents=True, exist_ok=True)
    return SpooledTemporaryFile(max_size=LIMITE_MEMORIA, dir=pasta)


def _leiame(filtro: Filtro, agora: datetime) -> str:
    tz = _tz()
    linhas = [
        "SociMan: métricas das redes (dataset)",
        "",
        f"Gerado em: {agora.astimezone(tz).isoformat()}",
        f"Versão do dicionário: {dicionario.DICIONARIO_VERSAO}",
        f"Período das fotos: {filtro.de.isoformat()} a {filtro.ate.isoformat()} (São Paulo)",
        f"Formato: {filtro.formato}",
        f"Perfil: {filtro.perfil_id or 'todos'}",
        f"Conta: {filtro.conta_id or 'todas'}",
        f"Contas anônimas: {'incluídas' if filtro.incluir_anonimas else 'não incluídas'}",
        "",
        "Arquivos:",
        f"- fotos_videos.{filtro.formato}: uma linha por foto de vídeo",
        f"- videos.{filtro.formato}: uma linha por vídeo (características e rótulos)",
        f"- fotos_conta.{filtro.formato}: uma linha por foto da conta",
        "- dicionario.csv: o significado de cada coluna",
        "",
        "Avisos:",
        *[f"- {a}" for a in dicionario.AVISOS],
    ]
    return "\r\n".join(linhas) + "\r\n"


def exportar(db: Session, filtro: Filtro, agora: datetime | None = None) -> IO[bytes]:
    """O ZIP pronto, com o cursor no início. Recusa pelo `datadir` antes de gravar no HD."""
    agora = agora or datetime.now(UTC)
    saida = _destino(estimativa(db, filtro))
    try:
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
            for arquivo, linhas in (("fotos_videos", _fotos_videos(db, filtro)),
                                    ("videos", _videos(db, filtro, agora)),
                                    ("fotos_conta", _fotos_conta(db, filtro))):
                escritor = _Escritor(zf, arquivo, filtro.formato)
                for linha in linhas:
                    escritor.linha(linha)
                escritor.fechar()
            with zf.open("dicionario.csv", "w") as bruto, \
                    io.TextIOWrapper(bruto, encoding="utf-8-sig", newline="") as texto:
                w = csv.writer(texto, lineterminator="\r\n")
                w.writerow(["arquivo", "coluna", "tipo", "unidade", "significado", "origem"])
                for c in dicionario.COLUNAS:
                    w.writerow([f"{c.arquivo}.{filtro.formato}", c.coluna, c.tipo, c.unidade,
                                c.significado, c.origem])
            zf.writestr("LEIAME.txt", _leiame(filtro, agora).encode("utf-8-sig"))
    except BaseException:
        saida.close()
        raise
    saida.seek(0)
    return saida


def pedacos(arquivo: IO[bytes], tamanho: int = 1024 * 1024) -> Iterator[bytes]:
    """O ZIP em pedaços para a resposta; fecha (e apaga, no HD) no fim."""
    try:
        while bloco := arquivo.read(tamanho):
            yield bloco
    finally:
        arquivo.close()
