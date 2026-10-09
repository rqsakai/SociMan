"""Filtro comum de todas as abas (spec 019, data-model "Filtro"; contracts/http-api.md).

- **Período:** dias de `APP_TZ` (America/Sao_Paulo), `[de 00:00, ate+1 00:00)`; padrão hoje − 6
  … hoje; até 400 dias (`validar_periodo` da 016 → 400 `periodo_invalido`). O anterior tem a
  mesma duração e termina na véspera de `de`.
- **Escopo:** `contaId` tem precedência e precisa ser do `perfilId` informado (400
  `conta_fora_do_perfil`); perfil ou conta inexistente → 404. `rede` sem dados → listas vazias.
- **Medida do post:** `h1`, `h24` (padrão) ou `d7` (Clarification 5).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.metricas import consulta, export
from sociman_api.perfis.models import Conta, Perfil, Platform

Medida = Literal["h1", "h24", "d7"]
MEDIDA_PADRAO: Medida = "h24"
DIAS_PADRAO = 7


@dataclass(frozen=True)
class Periodo:
    de: date
    ate: date
    ini: datetime  # de 00:00 em APP_TZ
    fim: datetime  # ate + 1 dia 00:00 em APP_TZ (exclusivo)

    @property
    def dias(self) -> int:
        return (self.ate - self.de).days + 1


@dataclass(frozen=True)
class Filtro:
    atual: Periodo
    anterior: Periodo
    perfil_id: uuid.UUID | None
    conta_id: uuid.UUID | None
    rede: Platform | None
    medida: Medida

    @property
    def medida_s(self) -> int:
        """O marco da medida em segundos de idade."""
        return consulta.MARCOS[self.medida]


def fuso() -> str:
    return get_settings().app_tz


def hoje() -> date:
    return datetime.now(ZoneInfo(fuso())).date()


def _periodo(de: date, ate: date) -> Periodo:
    ini, fim = consulta._periodo(de, ate)
    return Periodo(de, ate, ini, fim)  # type: ignore[arg-type] — com as duas datas, nunca None


def periodos(de: date | None, ate: date | None, dia_atual: date | None = None
             ) -> tuple[Periodo, Periodo]:
    """(atual, anterior). Sem datas, os últimos 7 dias; só `de`, até hoje; só `ate`, os 7 dias
    que terminam nele."""
    dia_atual = dia_atual or hoje()
    ate = ate or dia_atual
    if de is None:
        de = ate - timedelta(days=DIAS_PADRAO - 1)
    de, ate = export.validar_periodo(de, ate)
    dias = (ate - de).days + 1
    anterior_ate = de - timedelta(days=1)
    return _periodo(de, ate), _periodo(anterior_ate - timedelta(days=dias - 1), anterior_ate)


def montar(db: Session, *, de: date | None = None, ate: date | None = None,
           perfil_id: uuid.UUID | None = None, conta_id: uuid.UUID | None = None,
           rede: Platform | None = None, medida: Medida = MEDIDA_PADRAO,
           dia_atual: date | None = None) -> Filtro:
    atual, anterior = periodos(de, ate, dia_atual)
    if perfil_id is not None and db.get(Perfil, perfil_id) is None:
        raise ApiError(404, "not_found", "Perfil não encontrado")
    if conta_id is not None:
        conta = db.get(Conta, conta_id)
        if conta is None:
            raise ApiError(404, "not_found", "Conta não encontrada")
        if perfil_id is not None and conta.perfil_id != perfil_id:
            raise ApiError(400, "conta_fora_do_perfil", "A conta não é do perfil escolhido")
    return Filtro(atual=atual, anterior=anterior, perfil_id=perfil_id, conta_id=conta_id,
                  rede=rede, medida=medida)
