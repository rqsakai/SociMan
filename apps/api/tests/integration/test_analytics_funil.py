"""Funil (spec 019, US6, T044): etapas enviados → cortes → aprovados (destino com
`aprovado_em`) → publicados → acima do patamar (padrão 100; `patamar` muda), perdas por motivo,
tempos medianos e custo de IA só para o dono, com cálculo de referência sobre a semeadura
(SC-002)."""

import uuid
from datetime import timedelta

import pytest

from integration.analytics_helpers import agora, cena, local, membro  # noqa: F401
from integration.postagem_helpers import criar_corte
from sociman_api.conteudos.models import Modo
from sociman_api.cortes.models import CorteStatus
from sociman_api.envios.models import EnvioStatus
from sociman_api.postagem.models import DestinoEstado, Postagem


def _destino(c, corte, **campos) -> Postagem:
    d = Postagem(conteudo_id=corte.id, conta_id=uuid.UUID(c.conta["id"]), modo=Modo.lembrete,
                 version=1, created_by=c.dono.id, **campos)
    c.db.add(d)
    c.db.commit()
    return d


@pytest.fixture
def funil(cena):  # noqa: F811
    """4 envios no período (pronto 20 min, sem_clipes, falhou, pronto 60 min) e 1 antigo; 7
    cortes: C1/C2 publicados (vídeos com 24 h = 2400 e 4800), C3 aprovado sem publicar,
    C4 em revisão, C5 arquivado, C6 falhou e C7 recusado. Custo de IA: 0,0123 + 0,0077 na
    coorte e 1,00 fora dela."""
    pid = cena.perfil["id"]
    sent = agora() - timedelta(days=1)
    e1 = cena.envio(pid, sent_at=sent)
    cena.envio(pid, status=EnvioStatus.sem_clipes, sent_at=sent)
    cena.envio(pid, status=EnvioStatus.falhou, sent_at=sent)
    e4 = cena.envio(pid, sent_at=sent, finished_at=sent + timedelta(minutes=60))
    antigo = cena.envio(pid, sent_at=agora() - timedelta(days=30))
    criado = local(6, 10)

    def corte(envio, **kw):
        return criar_corte(cena.db, pid, envio_id=envio.id, created_at=criado, **kw)

    c1, c2, c3 = corte(e1), corte(e1), corte(e1)
    corte(e1, status=CorteStatus.revisao)
    corte(e1, archived_at=agora())
    corte(e4, status=CorteStatus.falhou, error_message="Falhou")
    c7 = corte(e4)
    fora = criar_corte(cena.db, pid, envio_id=antigo.id)
    s = cena.semear(videos=2, fotos=30, inicio=local(4, 10))
    cena.vincular(s.videos[0], corte=c1, aprovado_em=local(6, 12))  # posted local(4, 10)
    cena.vincular(s.videos[1], corte=c2, aprovado_em=local(6, 14))  # posted local(3, 10)
    _destino(cena, c3, estado=DestinoEstado.aprovado, aprovado_em=local(6, 16),
             aprovado_por=cena.dono.id)
    _destino(cena, c7, estado=DestinoEstado.pendente, recusado_em=agora(),
             recusado_por=cena.dono.id, recusa_motivo="Não combina")
    cena.custo_ia(c1.id, "0.0123")
    cena.custo_ia(c2.id, "0.0077")
    cena.custo_ia(fora.id, "1.00")
    return cena


def _etapas(corpo) -> dict:
    return {e["chave"]: e for e in corpo["etapas"]}


def _perdas(etapa) -> dict:
    return {p["motivo"]: p["n"] for p in etapa["perdas"]}


def test_etapas_conversoes_e_perdas(funil):
    corpo = funil.ok("funil")
    assert corpo["patamar"] == 100
    e = _etapas(corpo)
    assert list(e) == ["enviados", "cortes", "aprovados", "publicados", "acima_patamar"]
    assert [e[k]["n"] for k in e] == [4, 7, 3, 2, 2]
    assert e["enviados"]["conversaoPct"] is None
    assert e["cortes"]["conversaoPct"] == pytest.approx(7 / 4)
    assert e["aprovados"]["conversaoPct"] == pytest.approx(3 / 7)
    assert e["publicados"]["conversaoPct"] == pytest.approx(2 / 3)
    assert e["acima_patamar"]["conversaoPct"] == pytest.approx(1)
    assert _perdas(e["enviados"]) == {"sem_clipes": 1, "falhou": 1}
    assert _perdas(e["cortes"]) == {"em_revisao": 1, "arquivado": 1, "falhou": 1,
                                    "recusado": 1}
    assert _perdas(e["aprovados"]) == {"aguardando_publicacao": 1}
    assert _perdas(e["publicados"]) == {}


def test_patamar_muda_a_ultima_etapa(funil):
    e = _etapas(funil.ok("funil", patamar=3000))
    assert e["acima_patamar"]["n"] == 1
    assert _perdas(e["publicados"]) == {"abaixo_do_patamar": 1}
    # a medida escolhida não muda o patamar (FR-028: views em 24 h)
    assert _etapas(funil.ok("funil", patamar=3000, medida="h1"))["acima_patamar"]["n"] == 1
    assert funil.get("funil", patamar=0).status_code == 400  # validação


def test_tempos_medianos(funil):
    e = _etapas(funil.ok("funil"))
    assert e["enviados"]["tempoMedianoH"] is None
    # processamento: 20, 20, 20 e 60 min → 20 min
    assert e["cortes"]["tempoMedianoH"] == pytest.approx(round(20 / 60, 4))
    # criação do corte (local(6, 10)) → aprovação: 2 h, 4 h e 6 h
    assert e["aprovados"]["tempoMedianoH"] == pytest.approx(4)
    # aprovação → publicação: local(6, 12) → local(4, 10) = 46 h; local(6, 14) → local(3, 10)
    # = 68 h
    assert e["publicados"]["tempoMedianoH"] == pytest.approx(57)


def test_custo_so_para_dono(funil, membro):  # noqa: F811
    corpo = funil.ok("funil")
    assert corpo["custoIaUsd"] == pytest.approx(0.02)
    # views atuais dos vídeos ligados: 3000 + 6000
    assert corpo["custoPorMilViewsUsd"] == pytest.approx(round(0.02 / 9000 * 1000, 4))
    _, h = membro
    corpo_m = funil.ok("funil", h)
    assert corpo_m["custoIaUsd"] is None and corpo_m["custoPorMilViewsUsd"] is None
    assert [e["n"] for e in corpo_m["etapas"]] == [4, 7, 3, 2, 2]


def test_filtro_de_perfil_conta_e_periodo(funil):
    outra = funil.segunda_conta("outraconta", outro_perfil=True)
    # outro perfil: nenhum envio
    assert funil.ok("funil", perfilId=outra["perfilId"])["etapas"] == []
    # filtrar pela outra conta: a coorte de envios é do perfil dela (vazia)
    assert funil.ok("funil", contaId=outra["id"])["etapas"] == []
    # filtrar pela conta principal: mesmos números
    e = _etapas(funil.ok("funil", contaId=funil.conta["id"]))
    assert [e[k]["n"] for k in e] == [4, 7, 3, 2, 2]
    longe = funil.ok("funil", de=str(local(60).date()), ate=str(local(50).date()))
    assert longe["etapas"] == [] and longe["custoIaUsd"] == 0
