"""`EstadoColeta` (spec 016, T022; research R1, data-model "Série ativa"): a parte sem banco."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from sociman_api.metricas import consulta
from sociman_api.publicacao.models import ConexaoEstado

AGORA = datetime(2026, 9, 30, 12, tzinfo=UTC)
TODOS = ["user.info.basic", "video.upload", "video.publish", "user.info.stats", "video.list"]


def _cx(estado=ConexaoEstado.conectada, escopos=TODOS):
    return SimpleNamespace(estado=estado, escopos=list(escopos))


def _serie(**campos):
    base = {"anonimizada_em": None, "sem_permissao_desde": None, "ultima_coleta_em": AGORA,
            "varredura_concluida_em": AGORA, "ultimo_erro_codigo": None,
            "ultimo_erro_motivo": None, "ultimo_erro_em": None}
    return SimpleNamespace(**{**base, **campos})


def _cfg(habilitada=True):
    return SimpleNamespace(metricas_coleta_habilitada=habilitada)


def test_permissao_ok_coletando():
    e = consulta.montar_estado(_cx(), _serie(), _cfg(), 3, 40, AGORA + timedelta(minutes=5))
    assert e.permissao == "ok" and e.escopos_faltando == []
    assert e.coletando and e.habilitada and e.varredura_concluida
    assert (e.videos, e.fotos) == (3, 40)
    assert e.proxima_coleta_em == AGORA + timedelta(minutes=5) and e.erro is None


def test_permissao_faltando():
    e = consulta.montar_estado(_cx(escopos=TODOS[:4]), _serie(), _cfg())
    assert e.permissao == "faltando" and e.escopos_faltando == ["video.list"]
    assert not e.coletando and e.proxima_coleta_em is None
    e = consulta.montar_estado(_cx(escopos=TODOS[:3]), None, _cfg())
    assert e.escopos_faltando == ["user.info.stats", "video.list"]


@pytest.mark.parametrize("cx", [None, _cx(estado=ConexaoEstado.precisa_reconectar),
                                _cx(estado=ConexaoEstado.desconectada)])
def test_sem_conexao(cx):
    e = consulta.montar_estado(cx, _serie(), _cfg())
    assert e.permissao == "sem_conexao" and e.escopos_faltando == [] and not e.coletando


def test_coletando_so_com_as_cinco_condicoes():
    assert consulta.serie_ativa(_serie(), _cx(), _cfg())
    assert not consulta.serie_ativa(None, _cx(), _cfg())  # sem série viva
    assert not consulta.serie_ativa(_serie(anonimizada_em=AGORA), _cx(), _cfg())
    assert not consulta.serie_ativa(_serie(), _cx(ConexaoEstado.precisa_reconectar), _cfg())
    assert not consulta.serie_ativa(_serie(), _cx(escopos=TODOS[:3]), _cfg())
    assert not consulta.serie_ativa(_serie(sem_permissao_desde=AGORA), _cx(), _cfg())
    assert not consulta.serie_ativa(_serie(), _cx(), _cfg(False))


def test_habilitada_espelha_o_interruptor():
    e = consulta.montar_estado(_cx(), _serie(), _cfg(False))
    assert not e.habilitada and not e.coletando and e.permissao == "ok"


def test_erro_em_pt_br():
    serie = _serie(ultimo_erro_codigo="rede_indisponivel",
                   ultimo_erro_motivo="A TikTok não respondeu; tentando de novo às 09:05",
                   ultimo_erro_em=AGORA)
    e = consulta.montar_estado(_cx(), serie, _cfg())
    assert e.erro is not None and e.erro.codigo == "rede_indisponivel"
    assert e.erro.motivo.startswith("A TikTok não respondeu")
    dados = e.model_dump(by_alias=True)
    assert set(dados) >= {"permissao", "escoposFaltando", "coletando", "habilitada",
                          "ultimaColetaEm", "proximaColetaEm", "erro", "varreduraConcluida",
                          "videos", "fotos"}
