"""Datas, ano e @ dos arquivos do Studio (research R3 e R14): funções puras.

- **Datas aceitas:** "September 25", "Sep 25" (inglês); "25 de setembro", "setembro 25", "25 set"
  (pt-BR, provisório); `AAAA-MM-DD` e `DD/MM/AAAA` (com ano, sem dedução).
- **Nome do ZIP:** `Overview_<AAAA-MM-DD>_<epoch>_<handle>.zip`, `Followers_<handle>.zip` e,
  desde a 022, `Viewers_<handle>.zip` (espectadores), com o " (1)" do navegador. O início é o 1º dia, e o epoch (em `APP_TZ`) é o último.
- **Ano pelo nome do ZIP:** o 1º dia tem de bater com o início; os seguintes avançam o ano na
  virada (dez → jan), e o último tem de ser igual ao fim do nome.
- **Dedução:** o último dia é a ocorrência mais recente daquele dia e mês que não passa de hoje, e
  os anteriores recuam.
- **Ordem:** estritamente crescente. Sem ano, dois dias seguidos do arquivo não podem estar a mais
  de `SALTO_MAX_DIAS` (o Studio exporta todos os dias, inclusive os zerados): é o que separa a
  virada de ano de uma linha fora de ordem. Com ano, o salto máximo é de 365 dias.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from sociman_api.ia.guia import normalizar

SALTO_MAX_DIAS = 60

_MESES_EN = ("january", "february", "march", "april", "may", "june", "july", "august",
             "september", "october", "november", "december")
_MESES_PT = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
             "setembro", "outubro", "novembro", "dezembro")
_ABREV_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
MESES: dict[str, int] = {}
for _i, (_en, _pt, _ab) in enumerate(zip(_MESES_EN, _MESES_PT, _ABREV_PT, strict=True), start=1):
    MESES.update({_en: _i, _en[:3]: _i, _pt: _i, _ab: _i})
MESES["sept"] = 9

_HANDLE = r"([A-Za-z0-9._]{2,24})"
_COPIA = r"(?: \(\d+\))?"
_OVERVIEW = re.compile(rf"^Overview_(\d{{4}}-\d{{2}}-\d{{2}})_(\d{{9,11}})_{_HANDLE}{_COPIA}\.zip$",
                       re.IGNORECASE)
_FOLLOWERS = re.compile(rf"^Followers_{_HANDLE}{_COPIA}\.zip$", re.IGNORECASE)
_VIEWERS = re.compile(rf"^Viewers_{_HANDLE}{_COPIA}\.zip$", re.IGNORECASE)
_OUTRAS = re.compile(rf"^(Content)_{_HANDLE}{_COPIA}\.zip$", re.IGNORECASE)
# Âncora do ano entre as seções do mesmo envio (R4 da 022): cada uma usa a 1ª já resolvida.
ORDEM_ANCORA = ("visao_geral", "seguidores", "espectadores", "atividade")

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_BR = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_MES_DIA = re.compile(r"^([a-z]+)\.? (\d{1,2})$")  # september 25 / setembro 25
_DIA_MES = re.compile(r"^(\d{1,2}) (?:de )?([a-z]+)\.?$")  # 25 de setembro / 25 set


@dataclass(frozen=True)
class NomeZip:
    secao: str  # visao_geral | seguidores | espectadores | outra
    handle: str  # normalizado (sem @, sem caixa)
    inicio: date | None = None  # só na Visão geral
    fim: date | None = None
    outra: str | None = None  # Content


@dataclass(frozen=True)
class DataLida:
    mes: int
    dia: int
    ano: int | None = None


class DatasErro(Exception):
    """Ordem ou ano impossível (vira 400 `studio_datas` com o arquivo)."""


def normalizar_handle(handle: str) -> str:
    return handle.strip().lstrip("@").casefold()


def epoch_para_dia(epoch: int, tz: ZoneInfo) -> date:
    return datetime.fromtimestamp(epoch, tz).date()


def nome_zip(nome: str, tz: ZoneInfo) -> NomeZip | None:
    """O que o nome do ZIP diz (seção, @, início e fim), ou None se não é um nome do Studio."""
    base = nome.replace("\\", "/").rsplit("/", 1)[-1]
    if m := _OVERVIEW.match(base):
        try:
            inicio = date.fromisoformat(m.group(1))
        except ValueError:
            return None
        return NomeZip("visao_geral", normalizar_handle(m.group(3)), inicio,
                       epoch_para_dia(int(m.group(2)), tz))
    if m := _FOLLOWERS.match(base):
        return NomeZip("seguidores", normalizar_handle(m.group(1)))
    if m := _VIEWERS.match(base):
        return NomeZip("espectadores", normalizar_handle(m.group(1)))
    if m := _OUTRAS.match(base):
        return NomeZip("outra", normalizar_handle(m.group(2)), outra=m.group(1).capitalize())
    return None


def _valida(ano: int, mes: int, dia: int) -> bool:
    try:
        date(ano, mes, dia)
    except ValueError:
        return False
    return True


def ler_data(texto: str) -> DataLida | None:
    """A data como veio (com ou sem ano), ou None se o formato não é reconhecido ou o dia não
    existe."""
    t = normalizar(texto).replace(",", " ")
    t = " ".join(t.split())
    if m := _ISO.match(t):
        ano, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return DataLida(mes, dia, ano) if _valida(ano, mes, dia) else None
    if m := _BR.match(t):
        dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return DataLida(mes, dia, ano) if _valida(ano, mes, dia) else None
    if m := _MES_DIA.match(t):
        mes_txt, dia = m.group(1), int(m.group(2))
    elif m := _DIA_MES.match(t):
        dia, mes_txt = int(m.group(1)), m.group(2)
    else:
        return None
    mes = MESES.get(mes_txt)
    if mes is None or not _valida(2024, mes, dia):  # 2024 é bissexto: aceita 29/02
        return None
    return DataLida(mes, dia)


def _crescente(dias: list[date], salto_max: int) -> None:
    for a, b in pairwise(dias):
        if b <= a:
            raise DatasErro(f"as datas estão fora de ordem ({a:%d/%m/%Y} antes de "
                            f"{b:%d/%m/%Y})")
        if (b - a).days > salto_max:
            raise DatasErro(f"as datas estão fora de ordem ou com um salto grande demais "
                            f"({a:%d/%m/%Y} → {b:%d/%m/%Y})")


def _data(ano: int, d: DataLida) -> date:
    try:
        return date(ano, d.mes, d.dia)
    except ValueError:
        raise DatasErro(f"o dia {d.dia:02d}/{d.mes:02d} não existe em {ano}") from None


def pelo_nome(datas: list[DataLida], inicio: date, fim: date) -> list[date]:
    """Anos pelo nome do ZIP da Visão geral: começa no ano do início e avança na virada."""
    if not datas:
        return []
    if (datas[0].mes, datas[0].dia) != (inicio.month, inicio.day):
        raise DatasErro("o nome do ZIP não bate com as datas do arquivo (o 1º dia é outro)")
    ano, out = inicio.year, []
    for i, d in enumerate(datas):
        if i and (d.mes, d.dia) < (datas[i - 1].mes, datas[i - 1].dia):
            ano += 1
        out.append(_data(ano, d))
    _crescente(out, SALTO_MAX_DIAS)
    if out[-1] != fim:
        raise DatasErro("o nome do ZIP não bate com as datas do arquivo (o último dia é outro)")
    return out


def deduzir(datas: list[DataLida], hoje: date) -> list[date]:
    """O último dia é a ocorrência mais recente daquele dia e mês que não passa de hoje; os
    anteriores recuam e diminuem o ano quando o mês sobe."""
    if not datas:
        return []
    ultimo = datas[-1]
    ano = hoje.year
    while not _valida(ano, ultimo.mes, ultimo.dia) or date(ano, ultimo.mes, ultimo.dia) > hoje:
        ano -= 1
    out = [date(ano, ultimo.mes, ultimo.dia)]
    for i in range(len(datas) - 2, -1, -1):
        d, seguinte = datas[i], datas[i + 1]
        if (d.mes, d.dia) > (seguinte.mes, seguinte.dia):
            ano -= 1
        out.append(_data(ano, d))
    out.reverse()
    _crescente(out, SALTO_MAX_DIAS)
    return out


def com_ano(datas: list[DataLida]) -> list[date]:
    out = [date(d.ano, d.mes, d.dia) for d in datas]  # type: ignore[arg-type]
    _crescente(out, 365)
    return out


def mesmo_mapa(datas: list[DataLida], referencia: list[DataLida], anos: list[date]
               ) -> list[date] | None:
    """Os anos da outra seção do mesmo envio, quando os dias e meses estão todos nela."""
    mapa: dict[tuple[int, int], date] = {}
    for d, dia in zip(referencia, anos, strict=True):
        if (d.mes, d.dia) in mapa:
            return None  # o mesmo dia e mês duas vezes: ambíguo
        mapa[(d.mes, d.dia)] = dia
    if not all((d.mes, d.dia) in mapa for d in datas):
        return None
    out = [mapa[(d.mes, d.dia)] for d in datas]
    return out if all(a < b for a, b in pairwise(out)) else None


def dias_distintos(datas: list[DataLida]) -> list[DataLida]:
    """Os dias distintos na ordem da 1ª aparição (a atividade repete o dia, uma vez por hora)."""
    vistos: set[DataLida] = set()
    out = []
    for d in datas:
        if d not in vistos:
            vistos.add(d)
            out.append(d)
    return out


def hoje(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def ontem(tz: ZoneInfo) -> date:
    return hoje(tz) - timedelta(days=1)
