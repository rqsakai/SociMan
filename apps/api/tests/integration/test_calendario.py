"""Calendário (T064 da 006, R10; spec 014, R11): destinos agendados por dia local, com modo e
estado efetivo, filtros de perfil, plataforma e conta, e a coluna "sem data" com os aprovados
primeiro. Nada é publicado."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from integration.postagem_helpers import (  # noqa: F401
    agendar,
    aprovado,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
)
from sociman_api.cortes.models import CorteStatus
from sociman_api.marca.models import BrandKit

SP = ZoneInfo("America/Sao_Paulo")


def _amanha(hora: int = 19) -> datetime:
    return (datetime.now(SP) + timedelta(days=1)).replace(hour=hora, minute=0, second=0,
                                                         microsecond=0)


@pytest.fixture
def c(client, db, dono):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    return {"h": h, "perfil": perfil,
            "tiktok": criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd"),
            "youtube": criar_conta(client, h, perfil["id"], "youtube", "tavernanerdyt"),
            "corte": criar_corte(db, perfil["id"])}


def _agendar(client, c, conta, quando, corte=None, **extra) -> dict:
    corte = corte or c["corte"]
    r = agendar(client, c["h"], corte.id, c[conta]["id"] if isinstance(conta, str) else conta,
                quando, **extra)
    assert r.status_code in (200, 201), r.text
    return r.json()["destino"]


def test_por_dia_local_perfil_plataforma_e_conta(client, db, c):
    amanha = _amanha(23)  # 23:00 em SP = 02:00 UTC do dia seguinte: tem de cair no dia local
    _agendar(client, c, "tiktok", amanha, textos={"titulo": "Tarde da noite"})
    _agendar(client, c, "youtube", amanha + timedelta(days=3))
    outro = criar_perfil(client, c["h"], "Outro")
    conta2 = criar_conta(client, c["h"], outro["id"])
    corte2 = criar_corte(db, outro["id"])
    r = agendar(client, c["h"], corte2.id, conta2["id"], amanha)
    assert r.status_code == 201, r.text

    dia = amanha.date().isoformat()
    r = client.get("/api/calendario", headers=c["h"], params={"de": dia, "ate": dia})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 2
    it = next(i for i in items if i["titulo"] == "Tarde da noite")
    assert it["conteudo"]["id"] == str(c["corte"].id) and it["conteudo"]["situacao"] == "pronto"
    assert it["conteudo"]["origem"] == "corte" and it["conteudo"]["durationMs"] == 30000
    assert it["perfil"]["name"] == "A Taverna Nerd" and it["conta"]["platform"] == "tiktok"
    assert it["modo"] == "lembrete" and it["estadoEfetivo"] == "agendado"

    r = client.get("/api/calendario", headers=c["h"],
                   params={"de": dia, "ate": dia, "perfilId": c["perfil"]["id"]})
    assert [i["titulo"] for i in r.json()["items"]] == ["Tarde da noite"]
    fim = (amanha + timedelta(days=5)).date().isoformat()
    r = client.get("/api/calendario", headers=c["h"],
                   params={"de": dia, "ate": fim, "plataforma": "youtube"})
    assert [i["conta"]["platform"] for i in r.json()["items"]] == ["youtube"]
    r = client.get("/api/calendario", headers=c["h"],
                   params={"de": dia, "ate": fim, "contaId": c["tiktok"]["id"]})
    assert [i["conta"]["id"] for i in r.json()["items"]] == [c["tiktok"]["id"]]


def test_sem_data_aprovados_primeiro(client, db, c):
    livre = criar_corte(db, c["perfil"]["id"], openshorts_title="Clipe livre")
    criar_corte(db, c["perfil"]["id"], CorteStatus.revisao, hook_text="")  # não está pronto
    aprovado_sem_data = criar_corte(db, c["perfil"]["id"], openshorts_title="Aprovado")
    d = aprovado(client, c["h"], aprovado_sem_data.id, c["tiktok"]["id"], titulo="Já aprovado")
    _agendar(client, c, "tiktok", _amanha())  # c["corte"] tem agendamento
    dia = datetime.now(SP).date().isoformat()
    r = client.get("/api/calendario", headers=c["h"], params={"de": dia, "ate": dia})
    sem = r.json()["semData"]
    assert [(s["conteudoId"], s["aprovado"]) for s in sem] == [
        (str(aprovado_sem_data.id), True), (str(livre.id), False)]
    assert sem[0]["destinoId"] == d["id"] and sem[0]["contaId"] == c["tiktok"]["id"]
    assert sem[0]["titulo"] == "Já aprovado"
    assert sem[1]["titulo"] == "Clipe livre" and sem[1]["destinoId"] is None


def test_cor_do_perfil_pela_paleta(client, db, c):
    """R14: a cor do perfil é a 1ª cor da paleta do kit; sem kit salvo, `cor` vem null."""
    livre = criar_corte(db, c["perfil"]["id"], openshorts_title="Clipe livre")
    _agendar(client, c, "tiktok", _amanha())
    dia = _amanha().date().isoformat()
    hoje = datetime.now(SP).date().isoformat()

    r = client.get("/api/calendario", headers=c["h"], params={"de": hoje, "ate": dia})
    assert r.json()["items"][0]["perfil"]["cor"] is None
    assert r.json()["semData"][0]["perfilCor"] is None

    db.add(BrandKit(perfil_id=uuid.UUID(c["perfil"]["id"]),
                    palette=[{"chave": "rosa", "nome": "Rosa", "valor": "#ff5fa2"},
                             {"chave": "preto", "nome": "Preto", "valor": "#000000"}],
                    caption={}, hook={}, watermark={}, end_card={}))
    db.commit()
    r = client.get("/api/calendario", headers=c["h"], params={"de": hoje, "ate": dia})
    assert r.json()["items"][0]["perfil"]["cor"] == "#FF5FA2"
    sem = r.json()["semData"]
    assert [s["conteudoId"] for s in sem] == [str(livre.id)] and sem[0]["perfilCor"] == "#FF5FA2"


@pytest.mark.parametrize("params", [
    {"de": "2026-10-10", "ate": "2026-10-01"},
    {"de": "2026-10-01", "ate": "2026-12-15"},
    {"de": "2026-10-01"},
])
def test_intervalo_invalido(client, c, params):
    r = client.get("/api/calendario", headers=c["h"], params=params)
    assert r.status_code == 400
