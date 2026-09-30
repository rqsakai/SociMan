"""Proposta do OpenShorts (emenda da spec 014, T074): o detalhe do conteúdo mostra o título, a
descrição, o gancho e a nota do OpenShorts, e todo destino novo nasce com o título e a
descrição dela quando vierem vazios, cortados nos limites do destino."""

import itertools
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from integration.postagem_helpers import (  # noqa: F401
    add_destino,
    agendar,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
)
from sociman_api.conteudos.proposta import cortar
from sociman_api.cortes.models import CorteOrigem
from sociman_api.envios.models import Envio, EnvioOrigem

SP = ZoneInfo("America/Sao_Paulo")
DESCRICAO = "Aprenda o atalho que ninguém usa no Chrome. " * 3


def _amanha(hora: int = 19) -> datetime:
    return (datetime.now(SP) + timedelta(days=1)).replace(hour=hora, minute=0, second=0,
                                                         microsecond=0)


@pytest.fixture
def c(client, db, dono):  # noqa: F811
    _, h = dono
    perfil = criar_perfil(client, h)
    envio = Envio(perfil_id=uuid.UUID(perfil["id"]), origem=EnvioOrigem.avulso_link,
                  source_url="https://vimeo.com/1", source_title="Palestra")
    db.add(envio)
    db.commit()

    indices = itertools.count()

    def _openshorts(**extra):
        campos = {"origem": CorteOrigem.openshorts, "envio_id": envio.id,
                  "clip_index": next(indices),
                  "openshorts_title": "Atalho secreto do Chrome",
                  "openshorts_description": DESCRICAO, "openshorts_score": 87,
                  "hook_text": "Você usa isso errado?"}
        return criar_corte(db, perfil["id"], **(campos | extra))

    return {"h": h, "perfil": perfil, "openshorts": _openshorts,
            "tiktok": criar_conta(client, h, perfil["id"], "tiktok", "tavernanerd"),
            "youtube": criar_conta(client, h, perfil["id"], "youtube", "tavernanerdyt")}


def test_detalhe_mostra_a_proposta(client, db, c):
    corte = c["openshorts"]()
    r = client.get(f"/api/conteudos/{corte.id}", headers=c["h"])
    assert r.status_code == 200, r.text
    assert r.json()["conteudo"]["propostaOpenshorts"] == {
        "titulo": "Atalho secreto do Chrome", "descricao": DESCRICAO.strip(),
        "gancho": "Você usa isso errado?", "score": 87}


def test_sem_proposta_no_corte_enviado_a_mao(client, db, c):
    corte = criar_corte(db, c["perfil"]["id"])  # origem upload
    r = client.get(f"/api/conteudos/{corte.id}", headers=c["h"])
    assert r.json()["conteudo"]["propostaOpenshorts"] is None
    d = add_destino(client, c["h"], corte.id, c["tiktok"]["id"])
    assert d["titulo"] == "" and d["descricao"] == ""


def test_adicionar_conta_preenche_os_vazios(client, c):
    corte = c["openshorts"]()
    d = add_destino(client, c["h"], corte.id, c["tiktok"]["id"])
    assert d["titulo"] == "Atalho secreto do Chrome" and d["descricao"] == DESCRICAO.strip()
    assert d["hashtags"] == []
    # o que o operador mandou prevalece
    d = add_destino(client, c["h"], corte.id, c["youtube"]["id"], titulo="Meu título")
    assert d["titulo"] == "Meu título" and d["descricao"] == DESCRICAO.strip()


def test_agendar_direto_preenche_e_respeita_textos(client, c):
    corte = c["openshorts"]()
    r = agendar(client, c["h"], corte.id, c["tiktok"]["id"], _amanha())
    assert r.status_code == 201, r.text
    assert r.json()["destino"]["titulo"] == "Atalho secreto do Chrome"
    r = agendar(client, c["h"], corte.id, c["youtube"]["id"], _amanha(20),
                textos={"titulo": "", "descricao": "Minha descrição"})
    assert r.status_code == 201, r.text
    d = r.json()["destino"]
    assert d["titulo"] == "Atalho secreto do Chrome" and d["descricao"] == "Minha descrição"


def test_lote_e_sequencia_preenchem(client, c):
    a, b = c["openshorts"](), c["openshorts"](openshorts_title="Outro título")
    r = client.post("/api/destinos/lote/aprovar", headers=c["h"], json={
        "contaId": c["tiktok"]["id"], "conteudoIds": [str(a.id)]})
    assert r.status_code == 200, r.text
    assert r.json()["ok"][0]["titulo"] == "Atalho secreto do Chrome"
    body = {"contaId": c["youtube"]["id"], "conteudoIds": [str(b.id)],
            "inicio": _amanha().date().isoformat(), "horarios": ["19:00"], "modo": "lembrete"}
    previa = client.post("/api/agendamentos/sequencia/previa", headers=c["h"], json=body).json()
    r = client.post("/api/agendamentos/sequencia", headers=c["h"],
                    json=body | {"esperado": previa["slots"]})
    assert r.status_code == 200, r.text
    assert r.json()["ok"][0]["titulo"] == "Outro título"


def test_limites_do_destino(client, c):
    longo = "palavra " * 40  # 320 caracteres
    corte = c["openshorts"](openshorts_title=longo, openshorts_description="x" * 2500)
    d = add_destino(client, c["h"], corte.id, c["tiktok"]["id"])
    assert len(d["titulo"]) <= 100 and d["titulo"].endswith("palavra")
    assert len(d["descricao"]) == 2000
    # a proposta no detalhe continua inteira
    r = client.get(f"/api/conteudos/{corte.id}", headers=c["h"])
    assert r.json()["conteudo"]["propostaOpenshorts"]["titulo"] == longo.strip()


@pytest.mark.parametrize(("texto", "limite", "esperado"), [
    ("curto", 100, "curto"),
    ("um dois três quatro", 10, "um dois"),
    ("abcdefghijklmnop", 10, "abcdefghij"),
    ("frase, com vírgula", 6, "frase"),
])
def test_cortar(texto, limite, esperado):
    assert cortar(texto, limite) == esperado
