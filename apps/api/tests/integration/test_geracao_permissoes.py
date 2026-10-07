"""Permissões da geração (spec 021, T026, SC-004): pedir e escolher são de humano (dono ou
membro); MCP e `system:*` recebem 403 `somente_humano` com o evento; as leituras aceitam membro;
nenhum caminho escolhe sem humano."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import uuid

import pytest
from atores import ator_fake
from sqlalchemy import select, text

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    asset,
    detalhe,
    member,
    montar,
    motores,
    owner,
    pedir,
    rodar_gpu,
)
from sociman_api.auth.models import SecurityEvent
from sociman_api.db import get_engine
from sociman_api.errors import ApiError


def test_membro_pede_escolhe_e_le(client, owner, member, motores):
    b = montar(client, owner[1])
    hm = member[1]
    g = pedir(client, hm, b)
    rodar_gpu(motores)
    g = detalhe(client, hm, g["id"])
    assert client.get(f"/api/perfis/{b['perfil_id']}/geracoes", headers=hm).status_code == 200
    assert client.get(f"/api/geracoes/{g['id']}/versoes", headers=hm).status_code == 200
    alvo = asset(client, hm, b["cenario"]["id"])
    r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=hm,
                    json={"candidatoId": g["candidatos"][0]["id"], "version": g["version"],
                          "alvoVersion": alvo["version"]})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("rota", ["escolher", "cancelar", "tentar-de-novo", "gerar-outras"])
def test_token_mcp_recebe_somente_humano(client, owner, db, rota, mcp_habilitado):
    from integration.mcp_helpers import bearer, criar_cliente, ligar

    b = montar(client, owner[1])
    g = pedir(client, owner[1], b)
    ligar(client, owner[1], mcp_habilitado)
    _, token = criar_cliente(client, owner[1], escopo="propostas")
    hmcp = bearer(token)
    r = client.post(f"/api/geracoes/{g['id']}/{rota}", headers=hmcp,
                    json={"version": 1, "candidatoId": str(uuid.uuid4()), "alvoVersion": 1})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.post(f"/api/perfis/{b['perfil_id']}/geracoes", headers=hmcp,
                    json={"alvoTipo": "asset", "alvoId": b["cenario"]["id"],
                          "passo": "cenario.cena", "instrucao": "x"})
    assert r.status_code == 403
    db.expire_all()
    eventos = db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).all()
    assert len(eventos) >= 2


def test_service_recusa_ator_nao_humano_pelas_rotas_e_gerador_nao_escolhe(client, owner,
                                                                          motores):
    """O gerador nunca leva um passo com escolha a `escolhido`: só `revisao`."""
    b = montar(client, owner[1])
    g = pedir(client, owner[1], b)
    rodar_gpu(motores)
    assert detalhe(client, owner[1], g["id"])["status"] == "revisao"
    with get_engine().begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM geracoes WHERE status = 'escolhido'")
                            ).scalar() == 0
    # O ator `system:*` não passa pelas rotas Hu (o RequireHuman é a barreira).
    from starlette.requests import Request

    from sociman_api.auth.deps import require_human

    req = Request({"type": "http", "method": "POST", "path": "/x", "headers": [],
                   "path_params": {}, "query_string": b""})
    with pytest.raises(ApiError) as exc:
        require_human(req, ator_fake("system:gerador"))
    assert exc.value.code == "somente_humano"
