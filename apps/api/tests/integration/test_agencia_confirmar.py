"""Confirmar (spec 013, US2, T024): grava o marcado de uma vez, com o dono como autor e a origem
no histórico; escolhas inválidas, prévia usada, editado e arquivo alterado no meio, dono inativo,
erro inesperado e importação interrompida."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update

from integration.agencia_helpers import (  # noqa: F401
    _buckets,
    agencia,
    confirmar,
    dono,
    importar,
    itens,
    previa,
    um,
    yt,
)
from sociman_api.agencia import aplicar
from sociman_api.agencia.models import Importacao, ImportacaoEstado
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion
from sociman_api.perfis.models import Conta, Perfil


def _perfil(client, h, slug="taverna-teste", **kw):
    r = client.post("/api/perfis", headers=h, json={
        "name": "Taverna Teste", "slug": slug, "status": "ativo",
        "niche": "RPG e colecionáveis"} | kw)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def _versoes(db, tipo: str, entity_id) -> list[EntityVersion]:
    return list(db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == tipo, EntityVersion.entity_id == uuid.UUID(str(entity_id)))
        .order_by(EntityVersion.version)))


def test_novos_criados_divergente_mantido(client, db, dono, agencia, yt):  # noqa: F811
    user, h = dono
    _perfil(client, h, niche="Nicho editado à mão")
    agencia.perfil(publico="Nerds")
    p = previa(client, h)
    perfil_item = um(p, "perfil")
    assert perfil_item["situacao"] == "diverge"
    contas = itens(p, "conta", situacao="novo")
    assert len(contas) == 2

    imp = confirmar(client, h, p)

    assert imp["estado"] == "concluida", imp
    assert imp["criadaPor"]["id"] == str(user.id)
    resultados = {i["n"]: i["resultado"] for i in imp["itens"]}
    assert resultados[perfil_item["n"]] == "mantido"
    assert all(resultados[c["n"]] == "criado" for c in contas)
    assert db.scalar(select(Perfil.niche)) == "Nicho editado à mão"
    conta = db.scalars(select(Conta)).first()
    v = _versoes(db, "conta", conta.id)[0]
    assert v.actor_user_id == user.id and v.actor_kind == "user"
    assert v.details["importacao"]["id"] == imp["id"]
    assert v.details["importacao"]["arquivo"] == "shared:perfis/taverna-teste/perfil.md"
    assert imp["contagens"]["criado"] >= 2 and imp["contagens"]["mantido"] == 1
    # o registro da importação tem a impressão digital dos arquivos usados
    assert imp["arquivos"] >= 1


def test_usar_o_markdown_versao_nova_revertivel(client, db, dono, agencia, yt):  # noqa: F811
    user, h = dono
    criado = _perfil(client, h, niche="Nicho editado à mão")
    agencia.perfil()
    p = previa(client, h)
    n = um(p, "perfil")["n"]

    imp = confirmar(client, h, p, [{"n": n, "usar": "markdown"}])

    item = next(i for i in imp["itens"] if i["n"] == n)
    assert item["resultado"] == "atualizado" and item["entidade"]["tipo"] == "perfil"
    versoes = _versoes(db, "perfil", criado["id"])
    assert versoes[-1].before["niche"] == "Nicho editado à mão"
    assert versoes[-1].after["niche"] == "RPG e colecionáveis"
    assert versoes[-1].actor_user_id == user.id
    assert versoes[-1].details["importacao"]["trecho"] == "§1. Identidade e §2. Nicho"
    r = client.post(f"/api/perfis/{criado['id']}/revert", headers=h,
                    json={"version": versoes[-1].version, "toVersion": versoes[-2].version})
    assert r.status_code == 200, r.text
    assert r.json()["perfil"]["niche"] == "Nicho editado à mão"


@pytest.mark.parametrize(("escolha", "trecho"), [
    ({"n": 9999, "marcado": False}, "não existe"),
    ({"n": "PERFIL", "usar": "markdown"}, "\"usar\""),
    ({"n": "PERFIL"}, "sem escolha"),
    ({"n": "PERFIL", "direito": "parceiro"}, "\"direito\""),
])
def test_escolhas_invalidas_422_sem_consumir(client, dono, agencia, yt, escolha, trecho):  # noqa: F811
    _, h = dono
    agencia.perfil()
    p = previa(client, h)
    if escolha["n"] == "PERFIL":
        escolha = escolha | {"n": um(p, "perfil")["n"]}
    r = client.post("/api/agencia/importacoes", headers=h,
                    json={"previaId": p["previaId"], "escolhas": [escolha]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "escolha_invalida"
    assert trecho in r.json()["error"]["message"]
    assert confirmar(client, h, p)["estado"] == "concluida"  # a prévia continua valendo


def test_segunda_confirmacao_409_e_outro_usuario_404(client, dono, make_user, login, agencia,  # noqa: F811
                                                       yt):  # noqa: F811
    _, h = dono
    agencia.perfil()
    p = previa(client, h)
    outro = make_user(role="dono", name="Outro")
    h2 = login(client, outro.email, "senha-forte-123")
    r = client.post("/api/agencia/importacoes", headers=h2, json={"previaId": p["previaId"]})
    assert r.status_code == 404
    confirmar(client, h, p)
    r = client.post("/api/agencia/importacoes", headers=h, json={"previaId": p["previaId"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "previa_expirada"


def test_editado_entre_previa_e_confirmacao(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    criado = _perfil(client, h, niche="Nicho editado à mão")
    agencia.perfil()
    p = previa(client, h)
    n = um(p, "perfil")["n"]
    r = client.patch(f"/api/perfis/{criado['id']}", headers=h,
                     json={"version": criado["version"], "bio": "mudou"})
    assert r.status_code == 200, r.text

    imp = confirmar(client, h, p, [{"n": n, "usar": "markdown"}])

    item = next(i for i in imp["itens"] if i["n"] == n)
    assert (item["resultado"], item["resultadoMotivo"]) == ("nao_gravado",
                                                            "editado_desde_a_leitura")
    assert item["resultadoTexto"].startswith("mudou no SociMan")
    assert imp["contagens"]["criado"] >= 2  # as contas novas seguiram
    assert db.scalar(select(Perfil.niche)) == "Nicho editado à mão"


def test_arquivo_alterado_entre_previa_e_confirmacao(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil()
    agencia.pesquisa("taverna-teste", {"1. Termos": "- PT: rpg"})
    p = previa(client, h)
    agencia.pesquisa("taverna-teste", {"1. Termos": "- PT: rpg, d&d"})

    imp = confirmar(client, h, p)

    pesq = [i for i in imp["itens"] if i["origem"]["arquivo"].endswith("pesquisa.md")]
    assert pesq and all(i["resultadoMotivo"] == "mudou_desde_a_leitura" for i in pesq)
    assert any(i["resultado"] == "criado" for i in imp["itens"] if i["tipo"] == "perfil")


def test_dono_inativo_antes_da_tarefa(client, db, dono, agencia, yt, monkeypatch):  # noqa: F811
    user, h = dono
    agencia.perfil()
    p = previa(client, h)
    original = aplicar.executar

    def desativar_e_executar(plano, youtube):
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE users SET is_active = false WHERE id = :u"), {"u": user.id})
        original(plano, youtube)

    monkeypatch.setattr(aplicar, "executar", desativar_e_executar)
    r = client.post("/api/agencia/importacoes", headers=h, json={"previaId": p["previaId"]})
    assert r.status_code == 202
    imp = db.get(Importacao, uuid.UUID(r.json()["id"]))
    db.refresh(imp)
    assert imp.estado == ImportacaoEstado.falhou and "não está mais ativo" in imp.erro
    assert db.scalar(select(Perfil.id)) is None


def test_erro_no_meio_nada_gravado(client, db, dono, agencia, yt, monkeypatch):  # noqa: F811
    _, h = dono
    agencia.perfil()
    p = previa(client, h)

    def quebra(ap, item, escolha):
        raise RuntimeError("boom")

    monkeypatch.setitem(aplicar.APLICADORES, "conta", quebra)
    r = client.post("/api/agencia/importacoes", headers=h, json={"previaId": p["previaId"]})
    assert r.status_code == 202
    imp = client.get(f"/api/agencia/importacoes/{r.json()['id']}", headers=h).json()
    assert imp["estado"] == "falhou" and imp["erro"] and imp["itens"] == []
    assert db.scalar(select(Perfil.id)) is None  # o perfil criado antes do erro foi desfeito
    assert db.scalar(select(EntityVersion.id).where(EntityVersion.entity_type == "perfil")) is None


def test_processando_parada_vira_interrompida(client, db, dono, agencia):  # noqa: F811
    user, h = dono
    imp = Importacao(raiz_shared="/a", raiz_clipes="/b", arquivos={}, criada_por=user.id)
    db.add(imp)
    db.commit()
    db.execute(update(Importacao).values(
        progresso_em=datetime.now(UTC) - timedelta(minutes=11)))
    db.commit()
    lista = client.get("/api/agencia/importacoes", headers=h).json()["items"]
    assert lista[0]["estado"] == "falhou"
    assert "interrompida" in lista[0]["erro"]


def test_uma_processando_por_vez(client, db, dono, agencia, yt):  # noqa: F811
    user, h = dono
    agencia.perfil()
    db.add(Importacao(raiz_shared="/a", raiz_clipes="/b", arquivos={}, criada_por=user.id))
    db.commit()
    r = client.post("/api/agencia/previa", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "importacao_em_andamento"
    e = client.get("/api/agencia/estado", headers=h).json()
    assert e["emAndamento"]["estado"] == "processando"
