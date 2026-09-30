"""Regras da 015 na central (T043; contracts/http-api.md, "Mudanças nas rotas da 014"): modo
automático só por dono humano, `agendado_por` e snapshot, `falhou` de volta à fila com a
confirmação de Q4, 409 `envio_em_andamento`, arquivar e reverter, `Postado` de um rascunho."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from integration import publicacao_helpers as ph
from integration.postagem_helpers import PW, criar_corte
from sociman_api.auth.deps import Actor, current_user
from sociman_api.auth.models import SecurityEvent
from sociman_api.errors import ApiError
from sociman_api.main import app
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao import limites

# Fixtures do apoio (o pytest as acha pelo nome no módulo).
app_tiktok = ph.app_tiktok
cena = ph.cena


def _err(r) -> str:
    return r.json()["error"]["code"]


def _futuro(horas: int = 2) -> datetime:
    return datetime.now(UTC) + timedelta(hours=horas)


@pytest.fixture
def hm(cena, make_user, login):
    membro = make_user(role="membro", name="Membro")
    return login(cena.client, membro.email, PW)


@pytest.fixture
def mcp(cena):
    """O dono, mas por um cliente MCP (009): nunca humano."""
    app.dependency_overrides[current_user] = lambda: Actor(
        kind="mcp_client", user_id=cena.dono.id, user=cena.dono)
    yield {"Authorization": "Bearer qualquer"}
    app.dependency_overrides.pop(current_user, None)


def _get(cena, destino_id) -> dict:
    r = cena.client.get(f"/api/destinos/{destino_id}", headers=cena.h)
    assert r.status_code == 200, r.text
    return r.json()["destino"]


def _versoes(cena, destino_id) -> int:
    return len(cena.versoes(destino_id))


def _enviando(cena, monkeypatch) -> dict:
    """Um destino parado em `enviando` (tentativa `iniciando`, sem init: taxa local zerada)."""
    d = cena.agendado()
    monkeypatch.setitem(limites.TAXAS, "init", 0)
    cena.rodar()
    assert cena.destino(d["id"]).estado == DestinoEstado.enviando
    return _get(cena, d["id"])


def _falhou(cena, incerta: bool) -> dict:
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "timeout" if incerta else "invalid_params")
    cena.rodar()
    destino = cena.destino(d["id"])
    assert destino.estado == DestinoEstado.falhou and destino.falha_incerta == incerta
    return _get(cena, d["id"])


# ---- quem agenda em modo automático ----

def test_dono_agenda_rascunho_com_agendado_por_e_snapshot(cena):
    corte = cena.corte()
    r = cena.agendar(corte, _futuro())
    assert r.status_code == 201, r.text
    d = r.json()["destino"]
    assert d["modo"] == "criar_rascunho" and d["estado"] == "agendado"
    assert d["agendadoPor"]["id"] == str(cena.dono.id) and d["agendadoEm"]
    assert d["conta"]["conexao"] == "conectada" and d["avisosRede"] == []
    destino = cena.destino(d["id"])
    assert destino.envio_snapshot == {"videoRef": corte.result_key}
    assert destino.opcoes_rede is None
    assert cena.versoes(d["id"])[-1].details["acao"] == "agendado"


def test_avisos_de_video_fora_das_regras(cena):
    corte = criar_corte(cena.db, cena.perfil["id"], duration_ms=700_000, width=200)
    d = cena.agendar(corte, _futuro()).json()["destino"]
    assert len(d["avisosRede"]) == 2 and "10 minutos" in d["avisosRede"][0]


def test_membro_nao_agenda_automatico(cena, hm):
    corte = cena.corte()
    antes = cena.db.scalar(select(Postagem.id))
    r = cena.agendar(corte, _futuro(), h=hm)
    assert r.status_code == 403 and _err(r) == "somente_dono"
    assert cena.db.scalar(select(Postagem.id)) == antes  # nada gravado
    # O lembrete continua aberto ao membro (014, Q1), com o destino aprovado.
    d = cena.client.post(f"/api/conteudos/{corte.id}/destinos", headers=cena.h,
                         json={"contaId": cena.conta["id"]}).json()["destino"]
    d = cena.client.post(f"/api/destinos/{d['id']}/aprovar", headers=cena.h,
                         json={"version": d["version"]}).json()["destino"]
    r = cena.agendar(corte, _futuro(), h=hm, modo="lembrete")
    assert r.status_code == 200, r.text


def test_mcp_nao_agenda_e_fica_registrado(cena, mcp):
    corte = cena.corte()
    r = cena.agendar(corte, _futuro(), h=mcp)
    assert r.status_code == 403 and _err(r) == "somente_humano"
    assert cena.db.scalar(select(Postagem.id)) is None
    evento = cena.db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).one()
    assert evento.actor_kind == "mcp_client"


def test_reagendar_cancelar_e_lote_automatico_so_dono_humano(cena, hm):
    d = cena.agendado()
    n = _versoes(cena, d["id"])
    r = cena.client.patch(f"/api/destinos/{d['id']}/agendamento", headers=hm,
                          json={"version": d["version"], "plannedAt": _futuro(3).isoformat()})
    assert r.status_code == 403 and _err(r) == "somente_dono"
    r = cena.client.post(f"/api/destinos/{d['id']}/agendamento/cancelar", headers=hm,
                         json={"version": d["version"]})
    assert r.status_code == 403 and _err(r) == "somente_dono"
    r = cena.client.post("/api/agendamentos/lote/reagendar", headers=hm, json={"itens": [{
        "destinoId": d["id"], "version": d["version"], "plannedAt": _futuro(3).isoformat()}]})
    assert r.status_code == 200 and r.json()["falhas"][0]["code"] == "somente_dono"
    r = cena.client.post("/api/agendamentos/lote/cancelar", headers=hm, json={"itens": [{
        "destinoId": d["id"], "version": d["version"]}]})
    assert r.status_code == 200 and r.json()["falhas"][0]["code"] == "somente_dono"
    assert _versoes(cena, d["id"]) == n

    r = cena.client.patch(f"/api/destinos/{d['id']}/agendamento", headers=cena.h,
                          json={"version": d["version"], "plannedAt": _futuro(3).isoformat()})
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert cena.versoes(d["id"])[-1].details["acao"] == "reagendado"
    r = cena.client.post(f"/api/destinos/{d['id']}/agendamento/cancelar", headers=cena.h,
                         json={"version": d["version"]})
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["estado"] == "aprovado" and d["modo"] == "lembrete"
    assert cena.destino(d["id"]).envio_snapshot is None


def test_sequencia_rascunho_por_dono_e_publicar_recusado(cena, hm):
    cortes = [cena.corte(), cena.corte()]
    amanha = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    body = {"contaId": cena.conta["id"], "conteudoIds": [str(c.id) for c in cortes],
            "inicio": amanha, "horarios": ["10:00", "20:00"], "modo": "criar_rascunho",
            "gerarTextos": True}
    r = cena.client.post("/api/agendamentos/sequencia/previa", headers=hm, json=body)
    assert r.status_code == 403 and _err(r) == "somente_dono"
    previa = cena.client.post("/api/agendamentos/sequencia/previa", headers=cena.h,
                              json=body).json()
    r = cena.client.post("/api/agendamentos/sequencia", headers=cena.h,
                         json={**body, "esperado": previa["slots"]})
    assert r.status_code == 200 and len(r.json()["ok"]) == 2, r.text
    for d in r.json()["ok"]:
        assert d["agendadoPor"]["id"] == str(cena.dono.id)
        assert cena.destino(d["id"]).envio_snapshot["videoRef"]
    r = cena.client.post("/api/agendamentos/sequencia/previa", headers=cena.h,
                         json={**body, "modo": "publicar"})
    assert r.status_code == 409 and _err(r) == "modo_indisponivel"
    assert "cada vídeo" in r.json()["error"]["message"]


# ---- `falhou` de volta à fila (Q4) ----

def test_falhou_incerto_exige_confirmacao_em_todos_os_caminhos(cena):
    d = _falhou(cena, incerta=True)
    assert d["falhaIncerta"] is True
    quando = _futuro().isoformat()
    r = cena.client.patch(f"/api/destinos/{d['id']}/agendamento", headers=cena.h,
                          json={"version": d["version"], "plannedAt": quando})
    assert r.status_code == 409 and _err(r) == "confirmacao_necessaria"
    r = cena.client.post("/api/agendamentos/lote/reagendar", headers=cena.h, json={"itens": [{
        "destinoId": d["id"], "version": d["version"], "plannedAt": quando}]})
    assert r.json()["falhas"][0]["code"] == "confirmacao_necessaria"
    corte_id = d["conteudoId"]
    r = cena.client.post("/api/agendamentos", headers=cena.h, json={
        "conteudoId": corte_id, "contaId": cena.conta["id"], "plannedAt": quando,
        "modo": "criar_rascunho"})
    assert r.status_code == 409 and _err(r) == "confirmacao_necessaria"
    r = cena.client.post(f"/api/destinos/{d['id']}/tentar-de-novo", headers=cena.h,
                         json={"version": d["version"]})
    assert r.status_code == 409 and _err(r) == "confirmacao_necessaria"

    r = cena.client.patch(f"/api/destinos/{d['id']}/agendamento", headers=cena.h,
                          json={"version": d["version"], "plannedAt": quando,
                                "confirmoQueNaoChegou": True})
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["estado"] == "agendado" and d["falhaIncerta"] is False and d["falhaMotivo"] is None


def test_falhou_recusado_volta_sem_confirmacao_e_cancela(cena):
    d = _falhou(cena, incerta=False)
    r = cena.client.post("/api/agendamentos", headers=cena.h, json={
        "conteudoId": d["conteudoId"], "contaId": cena.conta["id"],
        "plannedAt": _futuro().isoformat(), "modo": "criar_rascunho"})
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "agendado"

    d2 = _falhou(cena, incerta=False)
    r = cena.client.patch(f"/api/destinos/{d2['id']}/agendamento", headers=cena.h,
                          json={"version": d2["version"]})
    assert r.status_code == 400  # falhou precisa de um horário novo
    r = cena.client.post(f"/api/destinos/{d2['id']}/agendamento/cancelar", headers=cena.h,
                         json={"version": d2["version"]})
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "aprovado"


# ---- `enviando`: nada sai por ação humana ----

def test_enviando_bloqueia_as_acoes_humanas(cena, monkeypatch):
    d = _enviando(cena, monkeypatch)
    v = {"version": d["version"]}
    base = f"/api/destinos/{d['id']}"
    chamadas = [
        cena.client.post(f"{base}/agendamento/cancelar", headers=cena.h, json=v),
        cena.client.patch(f"{base}/agendamento", headers=cena.h,
                          json={**v, "plannedAt": _futuro().isoformat()}),
        cena.client.post(f"{base}/archive", headers=cena.h, json=v),
        cena.client.post(f"{base}/revert", headers=cena.h, json={**v, "toVersion": 1}),
        cena.client.patch(base, headers=cena.h, json={**v, "titulo": "Outro"}),
        cena.client.post(f"{base}/postado", headers=cena.h, json=v),
    ]
    for r in chamadas:
        assert r.status_code == 409 and _err(r) == "envio_em_andamento", r.text
    corte = cena.client.get(f"/api/cortes/{d['conteudoId']}", headers=cena.h).json()["corte"]
    r = cena.client.post(f"/api/cortes/{d['conteudoId']}/archive", headers=cena.h,
                         json={"version": corte["version"]})
    assert r.status_code == 409 and _err(r) == "envio_em_andamento"
    conteudo = cena.client.get(f"/api/conteudos/{d['conteudoId']}",
                               headers=cena.h).json()["conteudo"]
    r = cena.client.post(f"/api/conteudos/{d['conteudoId']}/archive", headers=cena.h,
                         json={"version": conteudo["version"]})
    assert r.status_code == 409 and _err(r) == "envio_em_andamento"
    assert cena.destino(d["id"]).estado == DestinoEstado.enviando


def test_aplicar_marca_bloqueado_durante_o_envio(cena, monkeypatch):
    from sociman_api.cortes import service as cortes_service
    from sociman_api.cortes.models import Corte, CorteStatus

    d = _enviando(cena, monkeypatch)
    corte = cena.db.get(Corte, uuid.UUID(d["conteudoId"]))
    corte.status = CorteStatus.falhou  # o único caminho de volta para a fila de marca
    corte.error_code, corte.error_message = "teste", "falha de teste"
    cena.db.commit()
    with pytest.raises(ApiError) as exc:
        cortes_service.retry(cena.db, Actor(kind="user", user_id=cena.dono.id,
                                            user=cena.dono), corte.id, corte.version)
    assert exc.value.code == "envio_em_andamento"
    cena.db.rollback()


# ---- arquivar cancela: automático só por dono humano ----

def test_arquivar_com_automatico_agendado_exige_dono(cena, hm):
    d = cena.agendado()
    r = cena.client.post(f"/api/destinos/{d['id']}/archive", headers=hm,
                         json={"version": d["version"]})
    assert r.status_code == 403 and _err(r) == "somente_dono"
    corte = cena.client.get(f"/api/cortes/{d['conteudoId']}", headers=hm).json()["corte"]
    r = cena.client.post(f"/api/cortes/{d['conteudoId']}/archive", headers=hm,
                         json={"version": corte["version"]})
    assert r.status_code == 403 and _err(r) == "somente_dono"
    assert cena.destino(d["id"]).estado == DestinoEstado.agendado
    r = cena.client.post(f"/api/cortes/{d['conteudoId']}/archive", headers=cena.h,
                         json={"version": corte["version"]})
    assert r.status_code == 200, r.text
    destino = cena.destino(d["id"])
    assert destino.estado == DestinoEstado.aprovado and destino.planned_at is None


# ---- depois do envio ----

def test_postado_aceita_rascunho_criado_e_reversao_nao_restaura(cena):
    d = cena.agendado()
    cena.rodar(4)
    d = _get(cena, d["id"])
    assert d["estado"] == "rascunho_criado"
    r = cena.client.post(f"/api/destinos/{d['id']}/revert", headers=cena.h,
                         json={"version": d["version"], "toVersion": 1})
    # A versão 1 só tem textos vazios iguais aos atuais: nada a reverter além deles.
    assert r.status_code in (200, 400), r.text
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    d = _get(cena, d["id"])
    r = cena.client.post(f"/api/destinos/{d['id']}/postado", headers=cena.h,
                         json={"version": d["version"],
                               "postedUrl": "https://www.tiktok.com/@atavernanerd/video/1"})
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "postado"


def test_reagendar_rascunho_criado_e_recusado(cena):
    d = cena.agendado()
    cena.rodar(4)
    d = _get(cena, d["id"])
    r = cena.client.patch(f"/api/destinos/{d['id']}/agendamento", headers=cena.h,
                          json={"version": d["version"], "plannedAt": _futuro().isoformat()})
    assert r.status_code == 409
    r = cena.client.post("/api/agendamentos", headers=cena.h, json={
        "conteudoId": d["conteudoId"], "contaId": cena.conta["id"],
        "plannedAt": _futuro().isoformat(), "modo": "criar_rascunho"})
    assert r.status_code == 409 and _err(r) == "conflict"


def test_publicar_sem_a_tela_obrigatoria_e_recusado(cena):
    """US3: `publicar` disponível com a conta conectada; sem as opções da tela, 400."""
    r = cena.agendar(cena.corte(), _futuro(), modo="publicar")
    assert r.status_code == 400 and _err(r) == "opcoes_invalidas"
