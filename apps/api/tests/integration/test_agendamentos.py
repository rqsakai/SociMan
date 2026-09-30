"""Agendar, reagendar, cancelar, intervalo mínimo da conta e sequência (spec 014, US3 e US4;
R4, R6, R7). Só `lembrete` existe: nada é enviado a rede social."""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from integration.postagem_helpers import (  # noqa: F401
    acao,
    add_destino,
    agendar,
    aprovado,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api.cortes.models import CorteStatus
from sociman_api.history import EntityVersion
from sociman_api.postagem.models import Postagem

SP = ZoneInfo("America/Sao_Paulo")


def _amanha(hora: int = 19, minuto: int = 0, dias: int = 1) -> datetime:
    return (datetime.now(SP) + timedelta(days=dias)).replace(hour=hora, minute=minuto, second=0,
                                                            microsecond=0)


@pytest.fixture
def c(client, db, dono, membro):  # noqa: F811
    _, h = dono
    _, hm = membro
    perfil = criar_perfil(client, h)
    return {
        "h": h, "hm": hm, "dono": dono[0], "membro": membro[0], "perfil": perfil,
        "tiktok": criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd"),
        "youtube": criar_conta(client, h, perfil["id"], "youtube", "tavernanerdyt"),
        "corte": criar_corte(db, perfil["id"]),
    }


def _versoes(db, destino_id) -> list[EntityVersion]:
    db.expire_all()
    return list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "postagem",
        EntityVersion.entity_id == uuid.UUID(str(destino_id)),
    ).order_by(EntityVersion.version)))


def _err(r) -> str:
    return r.json()["error"]["code"]


# ---- agendar ----

def test_dono_agenda_direto_aprova_e_agenda(client, db, c):
    quando = _amanha()
    r = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], quando,
                textos={"titulo": "Atalho", "hashtags": ["dica"]})
    assert r.status_code == 201, r.text
    d = r.json()["destino"]
    assert d["estado"] == "agendado" and d["estadoEfetivo"] == "agendado"
    assert datetime.fromisoformat(d["plannedAt"]) == quando and d["plannedAt"].endswith("-03:00")
    assert d["modo"] == "lembrete" and d["titulo"] == "Atalho" and d["hashtags"] == ["#dica"]
    assert d["aprovacao"]["por"]["id"] == str(c["dono"].id)
    acoes = [v.details.get("acao") for v in _versoes(db, d["id"])]
    assert acoes == [None, "aprovado", "agendado"]


def test_agendar_existente_aprovado_devolve_200(client, c):
    aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = agendar(client, c["hm"], c["corte"].id, c["tiktok"]["id"], _amanha())
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "agendado"


def test_membro_sem_aprovacao_403(client, db, c):
    r = agendar(client, c["hm"], c["corte"].id, c["tiktok"]["id"], _amanha())
    assert r.status_code == 403 and _err(r) == "aprovacao_necessaria"
    assert db.query(Postagem).count() == 0  # nada gravado


def test_membro_agenda_reagenda_cancela_aprovado(client, db, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = agendar(client, c["hm"], c["corte"].id, c["tiktok"]["id"], _amanha(),
                destinoVersion=d["version"])
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    db.query(Postagem).filter_by(id=d["id"]).update({"lembrado_em": datetime.now(UTC)})
    db.commit()
    d = client.get(f"/api/destinos/{d['id']}", headers=c["hm"]).json()["destino"]
    assert d["lembrado"] is True
    novo = _amanha(20)
    r = client.patch(f"/api/destinos/{d['id']}/agendamento", headers=c["hm"],
                     json={"version": d["version"], "plannedAt": novo.isoformat()})
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert datetime.fromisoformat(d["plannedAt"]) == novo and d["lembrado"] is False
    r = acao(client, c["hm"], d, "agendamento/cancelar")
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["estado"] == "aprovado" and d["plannedAt"] is None
    acoes = [v.details.get("acao") for v in _versoes(db, d["id"])]
    assert acoes[-3:] == ["agendado", "reagendado", "agendamento_cancelado"]
    assert acao(client, c["hm"], d, "agendamento/cancelar").status_code == 409


def test_validacoes(client, db, c):
    passado = datetime.now(SP) - timedelta(minutes=5)
    r = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], passado)
    assert r.status_code == 400 and _err(r) == "planned_in_past"
    # tolerância de 1 min
    r = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"],
                datetime.now(SP) - timedelta(seconds=20))
    assert r.status_code == 201, r.text

    revisao = criar_corte(db, c["perfil"]["id"], status=CorteStatus.revisao)
    r = agendar(client, c["h"], revisao.id, c["tiktok"]["id"], _amanha())
    assert r.status_code == 409 and _err(r) == "conteudo_nao_pronto"


@pytest.mark.parametrize("modo", ["criar_rascunho", "publicar", "rascunho_e_publicar"])
def test_modo_indisponivel(client, db, c, modo):
    r = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(), modo=modo)
    assert r.status_code == 409 and _err(r) == "modo_indisponivel"
    assert r.json()["error"]["details"]["motivo"]
    assert db.query(Postagem).count() == 0


def test_conta_em_atencao(client, db, c):
    r = client.patch(f"/api/contas/{c['tiktok']['id']}", headers=c["h"],
                     json={"version": c["tiktok"]["version"], "status": "pausada"})
    assert r.status_code == 200
    r = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha())
    assert r.status_code == 409 and _err(r) == "conta_em_atencao"


def test_conta_pausada_deixa_agendado_em_atencao(client, c):
    d = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha()).json()["destino"]
    r = client.patch(f"/api/contas/{c['tiktok']['id']}", headers=c["h"],
                     json={"version": c["tiktok"]["version"], "status": "pausada"})
    assert r.status_code == 200
    d = client.get(f"/api/destinos/{d['id']}", headers=c["h"]).json()["destino"]
    assert d["estado"] == "agendado" and d["estadoEfetivo"] == "atencao"
    assert d["motivoAtencao"] == "Conta pausada"


def test_version_conflict_e_postado(client, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(),
                destinoVersion=d["version"] + 5)
    assert r.status_code == 409 and _err(r) == "version_conflict"
    acao(client, c["h"], d, "postado")
    r = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha())
    assert r.status_code == 409 and _err(r) == "conflict"


def test_reagendar_fora_de_agendado(client, c):
    d = aprovado(client, c["h"], c["corte"].id, c["tiktok"]["id"])
    r = client.patch(f"/api/destinos/{d['id']}/agendamento", headers=c["h"],
                     json={"version": d["version"], "plannedAt": _amanha().isoformat()})
    assert r.status_code == 409 and _err(r) == "nao_aprovado"


def test_duas_contas_independentes(client, c):
    a = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(19)).json()["destino"]
    b = agendar(client, c["h"], c["corte"].id, c["youtube"]["id"], _amanha(20)).json()["destino"]
    assert a["id"] != b["id"] and a["plannedAt"] != b["plannedAt"]


def test_modos_da_conta(client, c):
    r = client.get(f"/api/contas/{c['tiktok']['id']}/modos", headers=c["hm"])
    assert r.status_code == 200
    modos = r.json()["modos"]
    assert [m["modo"] for m in modos] == ["lembrete", "criar_rascunho", "publicar",
                                          "rascunho_e_publicar"]
    assert [m["disponivel"] for m in modos] == [True, False, False, False]
    assert modos[3]["motivo"] == "O TikTok não permite publicar um rascunho pela API"
    assert client.get(f"/api/contas/{uuid.uuid4()}/modos", headers=c["h"]).status_code == 404


# ---- intervalo mínimo (Q3 = C) ----

def test_intervalo_conflito_e_manter(client, db, c):
    outro = criar_corte(db, c["perfil"]["id"])
    a = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(19)).json()["destino"]
    r = agendar(client, c["h"], outro.id, c["tiktok"]["id"], _amanha(19, 10))
    assert r.status_code == 409 and _err(r) == "intervalo_conflito"
    det = r.json()["error"]["details"]
    assert det["intervaloMin"] == 30
    assert [x["destinoId"] for x in det["conflitos"]] == [a["id"]]
    assert det["conflitos"][0]["conteudoId"] == str(c["corte"].id)
    assert db.query(Postagem).filter_by(conteudo_id=outro.id).count() == 0  # nada gravado

    r = agendar(client, c["h"], outro.id, c["tiktok"]["id"], _amanha(19, 10),
                ignorarIntervalo=True)
    assert r.status_code == 201, r.text
    v = _versoes(db, r.json()["destino"]["id"])[-1]
    assert v.details["acao"] == "agendado" and v.details["intervaloIgnorado"] is True
    # outra conta não conflita
    r = agendar(client, c["h"], outro.id, c["youtube"]["id"], _amanha(19, 5))
    assert r.status_code == 201, r.text


def test_intervalo_zero_so_mesmo_minuto(client, db, c):
    r = client.patch(f"/api/contas/{c['tiktok']['id']}", headers=c["h"],
                     json={"version": c["tiktok"]["version"], "intervaloMinMinutos": 0})
    assert r.status_code == 200
    outro, terceiro = criar_corte(db, c["perfil"]["id"]), criar_corte(db, c["perfil"]["id"])
    agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(19))
    assert agendar(client, c["h"], outro.id, c["tiktok"]["id"],
                   _amanha(19, 1)).status_code == 201
    r = agendar(client, c["h"], terceiro.id, c["tiktok"]["id"], _amanha(19))
    assert r.status_code == 409 and _err(r) == "intervalo_conflito"


def test_o_proprio_destino_nao_conflita(client, c):
    a = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(19)).json()["destino"]
    r = client.patch(f"/api/destinos/{a['id']}/agendamento", headers=c["h"],
                     json={"version": a["version"], "plannedAt": _amanha(19, 15).isoformat()})
    assert r.status_code == 200, r.text
    v = r.json()["destino"]
    assert datetime.fromisoformat(v["plannedAt"]) == _amanha(19, 15)


def test_mudar_intervalo_nao_altera_destinos(client, db, c):
    d = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha()).json()["destino"]
    client.patch(f"/api/contas/{c['tiktok']['id']}", headers=c["h"],
                 json={"version": c["tiktok"]["version"], "intervaloMinMinutos": 120})
    d2 = client.get(f"/api/destinos/{d['id']}", headers=c["h"]).json()["destino"]
    assert d2["version"] == d["version"] and d2["plannedAt"] == d["plannedAt"]


def test_lote_reagendar_troca_horarios_sem_conflito(client, db, c):
    outro = criar_corte(db, c["perfil"]["id"])
    a = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(19)).json()["destino"]
    b = agendar(client, c["h"], outro.id, c["tiktok"]["id"], _amanha(19, dias=2)).json()[
        "destino"]
    r = client.post("/api/agendamentos/lote/reagendar", headers=c["hm"], json={"itens": [
        {"destinoId": a["id"], "version": a["version"], "plannedAt": b["plannedAt"]},
        {"destinoId": b["id"], "version": b["version"], "plannedAt": a["plannedAt"]},
    ]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["falhas"] == []
    por_id = {d["id"]: d["plannedAt"] for d in out["ok"]}
    assert por_id == {a["id"]: b["plannedAt"], b["id"]: a["plannedAt"]}
    lotes = {_versoes(db, x)[-1].details.get("loteId") for x in (a["id"], b["id"])}
    assert len(lotes) == 1


def test_lote_reagendar_falha_por_item(client, db, c):
    outro = criar_corte(db, c["perfil"]["id"])
    a = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(19)).json()["destino"]
    b = agendar(client, c["h"], outro.id, c["tiktok"]["id"], _amanha(19, dias=2)).json()[
        "destino"]
    r = client.post("/api/agendamentos/lote/reagendar", headers=c["h"], json={"itens": [
        {"destinoId": b["id"], "version": b["version"],
         "plannedAt": _amanha(19, 10).isoformat()},
        {"destinoId": a["id"], "version": a["version"] + 3,
         "plannedAt": _amanha(8).isoformat()},
    ]})
    assert r.status_code == 200, r.text
    falhas = {f["destinoId"]: f["code"] for f in r.json()["falhas"]}
    assert falhas == {b["id"]: "intervalo_conflito", a["id"]: "version_conflict"}


def test_lote_cancelar(client, db, c):
    outro = criar_corte(db, c["perfil"]["id"])
    a = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(19)).json()["destino"]
    b = aprovado(client, c["h"], outro.id, c["tiktok"]["id"])
    r = client.post("/api/agendamentos/lote/cancelar", headers=c["hm"], json={"itens": [
        {"destinoId": a["id"], "version": a["version"]},
        {"destinoId": b["id"], "version": b["version"]},
    ]})
    assert r.status_code == 200, r.text
    assert [d["estado"] for d in r.json()["ok"]] == ["aprovado"]
    assert [f["destinoId"] for f in r.json()["falhas"]] == [b["id"]]


# ---- arquivar cancela ----

def test_arquivar_corte_cancela_agendamentos(client, db, c):
    d = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha()).json()["destino"]
    corte = client.get(f"/api/cortes/{c['corte'].id}", headers=c["h"]).json()["corte"]
    r = client.post(f"/api/cortes/{c['corte'].id}/archive", headers=c["h"],
                    json={"version": corte["version"]})
    assert r.status_code == 200, r.text
    d = client.get(f"/api/destinos/{d['id']}", headers=c["h"]).json()["destino"]
    assert d["estado"] == "aprovado" and d["plannedAt"] is None
    assert _versoes(db, d["id"])[-1].details["acao"] == "cancelado_por_arquivo"
    corte = client.get(f"/api/cortes/{c['corte'].id}", headers=c["h"]).json()["corte"]
    client.post(f"/api/cortes/{c['corte'].id}/restore", headers=c["h"],
                json={"version": corte["version"]})
    d = client.get(f"/api/destinos/{d['id']}", headers=c["h"]).json()["destino"]
    assert d["estado"] == "aprovado"  # restaurar não reagenda


# ---- sequência (US4) ----

def _seq_body(c, ids, inicio, horarios=("19:00",), modo="lembrete"):
    return {"contaId": c["tiktok"]["id"], "conteudoIds": [str(i) for i in ids],
            "inicio": inicio.isoformat(), "horarios": list(horarios), "modo": modo,
            "gerarTextos": True}  # 015 (T101): a IA escreve a legenda depois


def test_sequencia_previa_e_confirmacao(client, db, c):
    cortes = [c["corte"]] + [criar_corte(db, c["perfil"]["id"]) for _ in range(2)]
    amanha = _amanha().date()
    ocupado = agendar(client, c["h"], criar_corte(db, c["perfil"]["id"]).id, c["tiktok"]["id"],
                      _amanha(19, 10)).json()["destino"]
    body = _seq_body(c, [x.id for x in cortes], amanha)
    r = client.post("/api/agendamentos/sequencia/previa", headers=c["h"], json=body)
    assert r.status_code == 200, r.text
    previa = r.json()
    assert previa["intervaloMin"] == 30
    assert [s["conteudoId"] for s in previa["slots"]] == [str(x.id) for x in cortes]
    datas = [datetime.fromisoformat(s["plannedAt"]).date() for s in previa["slots"]]
    assert datas == [amanha + timedelta(days=d) for d in (1, 2, 3)]  # o 1º dia pulado
    assert previa["pulados"][0]["motivo"] == "conflito"
    assert previa["pulados"][0]["destinoId"] == ocupado["id"]
    assert db.query(Postagem).count() == 1  # a prévia não grava

    # mudar o intervalo muda a prévia
    client.patch(f"/api/contas/{c['tiktok']['id']}", headers=c["h"],
                 json={"version": c["tiktok"]["version"], "intervaloMinMinutos": 0})
    p2 = client.post("/api/agendamentos/sequencia/previa", headers=c["h"], json=body).json()
    assert p2["intervaloMin"] == 0 and p2["pulados"] == []

    r = client.post("/api/agendamentos/sequencia", headers=c["h"],
                    json={**body, "esperado": previa["slots"]})
    assert r.status_code == 409 and _err(r) == "previa_desatualizada"
    assert r.json()["error"]["details"]["previa"]["slots"] == p2["slots"]

    r = client.post("/api/agendamentos/sequencia", headers=c["h"],
                    json={**body, "esperado": p2["slots"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["falhas"] == [] and [d["estado"] for d in out["ok"]] == ["agendado"] * 3


def test_sequencia_membro_so_aprovados(client, db, c):
    b = criar_corte(db, c["perfil"]["id"])
    aprovado(client, c["h"], b.id, c["tiktok"]["id"])
    body = _seq_body(c, [c["corte"].id, b.id], _amanha().date())
    previa = client.post("/api/agendamentos/sequencia/previa", headers=c["hm"],
                         json=body).json()
    assert [s["conteudoId"] for s in previa["slots"]] == [str(b.id)]
    assert [(i["conteudoId"], i["code"]) for i in previa["inelegiveis"]] == [
        (str(c["corte"].id), "aprovacao_necessaria")]


def test_sequencia_inelegiveis(client, db, c):
    revisao = criar_corte(db, c["perfil"]["id"], status=CorteStatus.revisao)
    arquivado = criar_corte(db, c["perfil"]["id"], archived_at=datetime.now(UTC))
    body = _seq_body(c, [revisao.id, arquivado.id, c["corte"].id], _amanha().date())
    previa = client.post("/api/agendamentos/sequencia/previa", headers=c["h"],
                         json=body).json()
    codes = {i["conteudoId"]: i["code"] for i in previa["inelegiveis"]}
    assert codes == {str(revisao.id): "conteudo_nao_pronto", str(arquivado.id): "conflict"}
    assert len(previa["slots"]) == 1


@pytest.mark.parametrize(("horarios", "dias"), [(("19:00", "19:00"), 1), (("19:00",), 200)])
def test_sequencia_validacao(client, c, horarios, dias):
    body = _seq_body(c, [c["corte"].id], _amanha(dias=dias).date(), horarios)
    r = client.post("/api/agendamentos/sequencia/previa", headers=c["h"], json=body)
    assert r.status_code == 400 and _err(r) == "validation_error"


def test_sequencia_modo_indisponivel(client, c):
    body = _seq_body(c, [c["corte"].id], _amanha().date(), modo="publicar")
    r = client.post("/api/agendamentos/sequencia/previa", headers=c["h"], json=body)
    assert r.status_code == 409 and _err(r) == "modo_indisponivel"
    r = client.post("/api/agendamentos/sequencia", headers=c["h"], json={**body, "esperado": []})
    assert r.status_code == 409 and _err(r) == "modo_indisponivel"


def test_hora_sem_offset_e_local(client, c):
    quando = _amanha(8).replace(tzinfo=None)
    r = client.post("/api/agendamentos", headers=c["h"], json={
        "conteudoId": str(c["corte"].id), "contaId": c["tiktok"]["id"],
        "plannedAt": quando.isoformat(), "modo": "lembrete",
        "textos": {"descricao": "Legenda"}})  # 015 (T101): obrigatória na TikTok
    assert r.status_code == 201, r.text
    assert datetime.fromisoformat(r.json()["destino"]["plannedAt"]) == quando.replace(tzinfo=SP)


def test_antecedencia_so_com_rascunho_e_publicar(client, c):
    r = agendar(client, c["h"], c["corte"].id, c["tiktok"]["id"], _amanha(), antecedenciaMin=30)
    assert r.status_code == 400 and _err(r) == "validation_error"
