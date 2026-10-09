"""IA na cena (spec 010, T037, US4, R10) com o Claude falso: gerar, aplicar com o selo, ajustar a
cena sem tocar na descrição do avatar, só as proibidas do perfil no pedido, e a cena nova com o
`cenaContexto` do formulário."""

# ruff: noqa: F811 — fixtures importadas de `cenas_helpers`

import json
import uuid

from fakes.anthropic_fake import anthropic_fake, campos_cena, texto  # noqa: F401
from sqlalchemy import select

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    ACHADINHOS,
    _buckets,
    base,
    criar_cena,
    get,
    owner,
    patch,
)
from sociman_api.history import EntityVersion
from sociman_api.ia.cliente import get_ia_client
from sociman_api.main import app


def _fake(anthropic_fake):
    app.dependency_overrides[get_ia_client] = lambda: anthropic_fake.ia_client()
    return anthropic_fake


def gerar(client, h, perfil_id, tipo, alvo, status=200, **extra):
    body = {"tipoCampo": tipo, "perfilId": perfil_id, "alvo": alvo,
            "sessaoId": str(uuid.uuid4())} | extra
    r = client.post("/api/ia/gerar", headers=h, json=body)
    assert r.status_code == status, r.text
    return r.json()["chamada"] if status == 200 else r.json()


def test_gerar_acao_e_aplicar(client, db, base, anthropic_fake):
    fake = _fake(anthropic_fake)
    fake.responder(texto("opens the lid slowly and shows the steam", "Ação mais clara."))
    h, pid = base["h"], base["perfil"]["id"]
    cena = criar_cena(client, h, base)
    chamada = gerar(client, h, pid, "cena.acao", {"entityType": "cena", "entityId": cena["id"]},
                    valorAtual={"texto": cena["acao"]})
    assert chamada["proposta"]["texto"] == "opens the lid slowly and shows the steam"
    assert chamada["explicacao"] == "Ação mais clara."
    system = fake.systems[0]
    assert 'parte="proibidas">' in system and "milagre" in system
    assert ACHADINHOS[:40] in json.dumps(fake.bodies[0]["messages"], ensure_ascii=False)

    salva = patch(client, h, cena, acao=chamada["proposta"]["texto"],
                  ia=[{"tipoCampo": "cena.acao", "chamadaId": chamada["id"]}])
    v = db.scalars(select(EntityVersion).where(
        EntityVersion.entity_id == uuid.UUID(cena["id"])).order_by(
        EntityVersion.version.desc())).first()
    assert v.actor_kind == "user" and v.version == salva["version"]
    assert v.details["ia"][0]["desfecho"] == "aplicada"


def test_ajustar_so_os_quatro_campos(client, base, anthropic_fake):
    _fake(anthropic_fake)
    h, pid = base["h"], base["perfil"]["id"]
    cena = criar_cena(client, h, base)
    chamada = gerar(client, h, pid, "cena.ajustar",
                    {"entityType": "cena", "entityId": cena["id"]},
                    valorAtual={"cena": {"acao": cena["acao"]}}, instrucao="mais close")
    proposta = chamada["proposta"]["cena"]
    assert set(proposta) == {"acao", "camera", "estilo", "audio"}
    salva = patch(client, h, cena, **proposta,
                  ia=[{"tipoCampo": "cena.ajustar", "chamadaId": chamada["id"]}])
    assert salva["prompt"]["texto"].startswith(ACHADINHOS)
    assert salva["acao"] == proposta["acao"]


def test_proibida_marcada_e_aplicar_igual_recusado(client, base, anthropic_fake):
    fake = _fake(anthropic_fake)
    proposta = "shows the milagre pot"
    fake.responder(texto(proposta), texto(proposta))  # a 2ª tentativa continua com a proibida
    h, pid = base["h"], base["perfil"]["id"]
    cena = criar_cena(client, h, base)
    chamada = gerar(client, h, pid, "cena.acao", {"entityType": "cena", "entityId": cena["id"]})
    assert chamada["proibidas"] == ["milagre"]
    r = client.patch(f"/api/cenas/{cena['id']}", headers=h, json={
        "version": cena["version"], "acao": proposta,
        "ia": [{"tipoCampo": "cena.acao", "chamadaId": chamada["id"]}]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "ia_proibida"


def test_cena_nova_com_contexto(client, base, anthropic_fake):
    _fake(anthropic_fake)
    h, pid = base["h"], base["perfil"]["id"]
    ctx = {"avatarId": base["avatar"]["id"], "avatarArquivoId": base["look"]["id"],
           "cenarioId": base["cenario"]["id"], "produtoNome": "Panela", "fala": "Oi",
           "duracaoS": 8, "modo": "ingredientes"}
    chamada = gerar(client, h, pid, "cena.acao", {"entityType": "cena"}, cenaContexto=ctx)
    assert chamada["alvo"]["entityId"] is None
    # sem contexto, uma cena nova é recusada
    erro = gerar(client, h, pid, "cena.acao", {"entityType": "cena"}, status=400)
    assert erro["error"]["code"] == "invalid_ia"
    # contexto com asset do tipo errado (029: o de outro perfil base passa)
    erro = gerar(client, h, pid, "cena.acao", {"entityType": "cena"}, status=422,
                 cenaContexto=ctx | {"avatarId": base["cenario"]["id"], "avatarArquivoId": None})
    assert erro["error"]["code"] == "cena_invalida"
    # a chamada da cena nova é aplicada ao criar
    r = client.post(f"/api/perfis/{pid}/cenas", headers=h, json={
        "nome": "Nova", "acao": chamada["proposta"]["texto"],
        "ia": [{"tipoCampo": "cena.acao", "chamadaId": chamada["id"]}]})
    assert r.status_code == 201, r.text
