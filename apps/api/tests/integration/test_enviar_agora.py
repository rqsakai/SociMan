""""Enviar agora" (spec 015, emenda do dono, T099): `POST /api/destinos/{id}/enviar-agora`
aprova se preciso, agenda com `planned_at = agora` e a trilha envia na volta seguinte; só dono
humano; as validações do agendar valem."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from integration import publicacao_helpers as ph
from integration.postagem_helpers import PW, add_destino
from sociman_api.auth.deps import Actor, current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.db import get_engine
from sociman_api.main import app
from sociman_api.postagem.models import DestinoEstado
from sociman_api.publicacao import limites

# Fixtures do apoio (o pytest as acha pelo nome no módulo).
app_tiktok = ph.app_tiktok
cena = ph.cena


def _err(r) -> str:
    return r.json()["error"]["code"]


def _enviar(cena, d, h=None, **body):
    return cena.client.post(f"/api/destinos/{d['id']}/enviar-agora", headers=h or cena.h,
                            json={"version": d["version"], **body})


def _pendente(cena) -> dict:
    return add_destino(cena.client, cena.h, cena.corte().id, cena.conta["id"],
                       descricao="Legenda")


def test_dono_envia_agora_e_a_trilha_pega_na_volta_seguinte(cena):
    d = _pendente(cena)
    r = _enviar(cena, d)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["aviso"] is None
    destino = out["destino"]
    assert destino["estado"] == "agendado" and destino["modo"] == "criar_rascunho"
    assert destino["aprovacao"]["por"]["id"] == str(cena.dono.id)
    assert abs(datetime.fromisoformat(destino["plannedAt"]) - datetime.now(UTC)) \
        < timedelta(minutes=1)
    ultima = cena.versoes(d["id"])[-1]
    assert ultima.details["acao"] == "agendado" and ultima.details["disparo"] == "agora"
    assert ultima.actor_kind == "user"
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    assert cena.fake.inits == 1


def test_reenvia_um_agendado_para_depois(cena):
    corte = cena.corte()
    d = cena.agendar(corte, datetime.now(UTC) + timedelta(days=2)).json()["destino"]
    r = _enviar(cena, d)
    assert r.status_code == 200, r.text
    cena.rodar()
    assert cena.destino(d["id"]).estado == DestinoEstado.enviando


def test_nao_cai_em_vencido(cena):
    """Um destino agendado há horas e mandado agora sai na hora (a data passa a ser agora)."""
    ph.ligar_botao(False)
    d = cena.agendado()
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE postagens SET planned_at = now() - interval '3 hours'"))
    ph.ligar_botao(True)
    d = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    assert d["estadoEfetivo"] == "vencido"
    assert _enviar(cena, d).status_code == 200
    cena.rodar()
    assert cena.fake.inits == 1


def test_interruptor_desligado_nao_bloqueia_so_avisa(cena):
    ph.ligar_botao(False)
    d = _pendente(cena)
    r = _enviar(cena, d)
    assert r.status_code == 200, r.text
    assert "pausado" in r.json()["aviso"]
    atual = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    assert atual["estadoEfetivo"] == "pausado"
    cena.rodar()
    assert cena.fake.inits == 0


@pytest.fixture
def hm(cena, make_user, login):
    membro = make_user(role="membro", name="Membro")
    return login(cena.client, membro.email, PW)


def test_membro_e_mcp_403(cena, hm):
    d = _pendente(cena)
    r = _enviar(cena, d, h=hm)
    assert r.status_code == 403 and _err(r) == "somente_dono"
    app.dependency_overrides[current_user] = lambda: Actor(
        kind="mcp_client", user_id=cena.dono.id, user=cena.dono)
    try:
        r = _enviar(cena, d, h={"Authorization": "Bearer qualquer"})
    finally:
        app.dependency_overrides.pop(current_user, None)
    assert r.status_code == 403 and _err(r) == "somente_humano"
    assert cena.db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).one().actor_kind == "mcp_client"
    assert cena.destino(d["id"]).estado == DestinoEstado.pendente


def test_sem_conexao_409(cena):
    d = _pendente(cena)
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE conexoes SET estado = 'precisa_reconectar'"))
    r = _enviar(cena, d)
    assert r.status_code == 409 and _err(r) == "conta_nao_conectada"
    assert cena.destino(d["id"]).estado == DestinoEstado.pendente


def test_enviando_409(cena, monkeypatch):
    d = cena.agendado()
    monkeypatch.setitem(limites.TAXAS, "init", 0)
    cena.rodar()
    d = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    r = _enviar(cena, d)
    assert r.status_code == 409 and _err(r) == "envio_em_andamento"


def test_incerta_exige_conferi_no_app(cena):
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "timeout")
    cena.rodar()
    d = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    assert d["falhaIncerta"] is True
    r = _enviar(cena, d)
    assert r.status_code == 409 and _err(r) == "confirmacao_necessaria"
    r = _enviar(cena, d, conferiNoApp=True)
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "agendado"


def test_modo_lembrete_e_publicar_sem_tela_recusados(cena):
    d = _pendente(cena)
    r = _enviar(cena, d, modo="lembrete")
    assert r.status_code == 400
    r = _enviar(cena, d, modo="publicar")
    assert r.status_code == 400 and _err(r) == "opcoes_invalidas"  # sem a tela obrigatória
