"""Legenda da TikTok (spec 015, T101): sem título, legenda = descrição + "\\n\\n" + hashtags, até
2.200 caracteres; descrição obrigatória para agendar em conta TikTok (qualquer modo), no aprovar
e agendar, no Enviar agora, no lote e na sequência; o Direct Post leva a legenda composta."""

from datetime import UTC, datetime, timedelta

import pytest

from integration import publicacao_helpers as ph
from integration.postagem_helpers import add_destino, criar_conta
from integration.publicacao_helpers import opcoes
from sociman_api.postagem.models import DestinoEstado
from sociman_api.publicacao.legenda import legenda_tiktok

# Fixtures do apoio (o pytest as acha pelo nome no módulo).
app_tiktok = ph.app_tiktok
cena = ph.cena

SEM = {"descricao": ""}


def _err(r) -> str:
    return r.json()["error"]["code"]


def _futuro() -> datetime:
    return datetime.now(UTC) + timedelta(hours=2)


class _T:
    def __init__(self, descricao, hashtags):
        self.descricao, self.hashtags = descricao, hashtags


def test_legenda_composta_sem_titulo():
    assert legenda_tiktok(_T("Veja isto", ["#dica", "#tech"])) == "Veja isto\n\n#dica #tech"
    assert legenda_tiktok(_T("  Só texto ", [])) == "Só texto"
    assert legenda_tiktok(_T("", ["#dica"])) == "#dica"


@pytest.mark.parametrize("modo", ["lembrete", "criar_rascunho"])
def test_agendar_sem_descricao_e_recusado(cena, modo):
    r = cena.agendar(cena.corte(), _futuro(), modo=modo, textos={"titulo": "Só título",
                                                                 **SEM})
    assert r.status_code == 400 and _err(r) == "legenda_obrigatoria"
    assert "legenda" in r.json()["error"]["message"]


def test_aprovar_e_agendar_usa_os_textos_do_pedido(cena):
    d = add_destino(cena.client, cena.h, cena.corte().id, cena.conta["id"])  # sem descrição
    r = cena.client.post("/api/agendamentos", headers=cena.h, json={
        "conteudoId": d["conteudoId"], "contaId": cena.conta["id"],
        "plannedAt": _futuro().isoformat(), "modo": "lembrete"})
    assert r.status_code == 400 and _err(r) == "legenda_obrigatoria"
    assert cena.destino(d["id"]).estado == DestinoEstado.pendente  # nada aprovado
    r = cena.client.post("/api/agendamentos", headers=cena.h, json={
        "conteudoId": d["conteudoId"], "contaId": cena.conta["id"],
        "plannedAt": _futuro().isoformat(), "modo": "lembrete",
        "textos": {"descricao": "Agora sim", "hashtags": ["dica"]}})
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["legendaFinal"] == "Agora sim\n\n#dica"


def test_legenda_longa(cena):
    r = cena.agendar(cena.corte(), _futuro(), textos={
        "descricao": "x" * 2000, "hashtags": [f"tag{i}{'y' * 40}" for i in range(8)]})
    assert r.status_code == 400 and _err(r) == "legenda_longa"
    assert r.json()["error"]["details"]["limite"] == 2200


def test_outra_rede_nao_exige(cena):
    yt = criar_conta(cena.client, cena.h, cena.perfil["id"], "youtube", "canal")
    r = cena.agendar(cena.corte(), _futuro(), conta=yt, modo="lembrete", textos=SEM)
    assert r.status_code == 201, r.text
    assert r.json()["destino"]["legendaFinal"] is None


def test_enviar_agora_sem_descricao(cena):
    d = add_destino(cena.client, cena.h, cena.corte().id, cena.conta["id"])
    r = cena.client.post(f"/api/destinos/{d['id']}/enviar-agora", headers=cena.h,
                         json={"version": d["version"]})
    assert r.status_code == 400 and _err(r) == "legenda_obrigatoria"


def test_lote_reagendar_e_textos_de_agendado(cena):
    d = cena.agendado()
    r = cena.client.patch(f"/api/destinos/{d['id']}", headers=cena.h,
                          json={"version": d["version"], "descricao": ""})
    assert r.status_code == 400 and _err(r) == "legenda_obrigatoria"
    # Um agendado que perdeu a legenda por fora (dado antigo) não é reagendado em lote.
    destino = cena.destino(d["id"])
    destino.descricao = ""
    cena.db.commit()
    r = cena.client.post("/api/agendamentos/lote/reagendar", headers=cena.h, json={"itens": [{
        "destinoId": d["id"], "version": d["version"], "plannedAt": _futuro().isoformat()}]})
    assert r.json()["falhas"][0]["code"] == "legenda_obrigatoria"


def test_sequencia_pula_sem_descricao_salvo_com_ia(cena):
    com = add_destino(cena.client, cena.h, cena.corte().id, cena.conta["id"],
                      descricao="Tem legenda")
    sem = cena.corte()
    amanha = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    body = {"contaId": cena.conta["id"], "conteudoIds": [com["conteudoId"], str(sem.id)],
            "inicio": amanha, "horarios": ["10:00", "20:00"], "modo": "lembrete"}
    previa = cena.client.post("/api/agendamentos/sequencia/previa", headers=cena.h,
                              json=body).json()
    assert [s["conteudoId"] for s in previa["slots"]] == [com["conteudoId"]]
    assert [(i["conteudoId"], i["code"]) for i in previa["inelegiveis"]] == \
        [(str(sem.id), "legenda_obrigatoria")]
    previa = cena.client.post("/api/agendamentos/sequencia/previa", headers=cena.h,
                              json={**body, "gerarTextos": True}).json()
    assert len(previa["slots"]) == 2 and previa["inelegiveis"] == []


def test_direct_post_leva_a_legenda_composta(cena):
    r = cena.agendar(cena.corte(), datetime.now(UTC), modo="publicar", opcoes=opcoes(),
                     textos={"titulo": "Título não vai", "descricao": "Legenda do post",
                             "hashtags": ["dica"]})
    assert r.status_code == 201, r.text
    cena.rodar(4)
    post = cena.fake.pedidos("video_init")[0]["post_info"]
    assert post["title"] == "Legenda do post\n\n#dica"
