"""T014 (FR-025): o portão do token `scol_`, degrau a degrau, e o evento `coleta_recusada`."""

from sqlalchemy import select, text

from integration.coleta_helpers import (  # noqa: F401
    bearer,
    criar_cliente_coleta,
    dono,
    ligado,
    ligar_coleta,
)
from sociman_api.auth.models import SecurityEvent

SEM_PROTOCOLO = {"Authorization"}


def _h(token: str, **extra) -> dict:
    h = dict(bearer(token))
    h.update(extra)
    return h


def _recusas(db) -> list[dict]:
    rows = db.scalars(select(SecurityEvent).where(SecurityEvent.type == "coleta_recusada")
                      .order_by(SecurityEvent.id)).all()
    return [r.details for r in rows]


def test_credencial_invalida_401_e_evento_sem_token(client, db, ligado):  # noqa: F811
    _, token = criar_cliente_coleta(client, ligado)
    errado = token[:-1] + ("a" if token[-1] != "a" else "b")
    r = client.get("/api/coleta/fila", headers=_h(errado))
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    r = client.get("/api/coleta/fila", headers=_h("scol_curto"))
    assert r.status_code == 401
    recusas = _recusas(db)
    assert recusas and recusas[0]["motivo"] == "credencial"
    assert all("token" not in str(d).lower().replace("tokenid", "") for d in recusas)
    assert all(token[6:] not in str(d) for d in recusas)


def test_fila_passa_com_coleta_desligada_e_as_outras_rotas_503(client, db, dono,  # noqa: F811
                                                                coleta_habilitada):
    _, h = dono
    _, token = criar_cliente_coleta(client, h)
    coleta_habilitada(False)
    r = client.get("/api/coleta/fila", headers=_h(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["habilitada"] is False and body["tarefas"] == []
    assert body["desligadaNoServidor"] is True and body["motivoVazia"] == "desligada"
    r = client.post("/api/coleta/coletas", headers=_h(token),
                    json={"versaoColetor": "0.1.0", "protocolo": 1})
    assert r.status_code == 503 and r.json()["error"]["code"] == "coleta_desligada"
    # Só o .env ligado, botão desligado: a fila continua vazia.
    coleta_habilitada(True)
    body = client.get("/api/coleta/fila", headers=_h(token)).json()
    assert body["habilitada"] is False and body["desligadaNoServidor"] is False


def test_revogado_vencido_e_suspenso(client, db, ligado):  # noqa: F811
    cliente, token = criar_cliente_coleta(client, ligado, "A")
    r = client.post(f"/api/coleta/clientes/{cliente['id']}/revogar", headers=ligado,
                    json={"version": cliente["version"]})
    assert r.status_code == 200
    assert client.get("/api/coleta/fila", headers=_h(token)).status_code == 401
    cliente, token = criar_cliente_coleta(client, ligado, "B")
    db.execute(text("UPDATE coleta_clientes SET expira_em = now() - interval '1 minute' "
                    "WHERE id = :id"), {"id": cliente["id"]})
    db.commit()
    assert client.get("/api/coleta/fila", headers=_h(token)).status_code == 401
    cliente, token = criar_cliente_coleta(client, ligado, "C")
    client.post(f"/api/coleta/clientes/{cliente['id']}/suspender", headers=ligado,
                json={"version": cliente["version"]})
    r = client.get("/api/coleta/fila", headers=_h(token))
    assert r.status_code == 403 and r.json()["error"]["code"] == "coleta_suspensa"
    assert [d["motivo"] for d in _recusas(db)] == ["revogado_ou_vencido", "revogado_ou_vencido",
                                                   "suspenso"]


def test_origin_403(client, ligado):  # noqa: F811
    _, token = criar_cliente_coleta(client, ligado)
    r = client.get("/api/coleta/fila", headers=_h(token, Origin="http://localhost:8180"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "escopo_coleta"


def test_token_fora_da_ingestao_403(client, db, ligado):  # noqa: F811
    _, token = criar_cliente_coleta(client, ligado)
    for url in ("/api/perfis", "/api/coleta/clientes", "/api/coleta/estado",
                "/api/coleta/eventos", "/api/health"):
        r = client.get(url, headers=_h(token))
        assert r.status_code == 403, (url, r.status_code)
        assert r.json()["error"]["code"] == "escopo_coleta", url
    assert all(d["motivo"] == "escopo" for d in _recusas(db))


def test_protocolo_errado_426(client, ligado):  # noqa: F811
    _, token = criar_cliente_coleta(client, ligado)
    h = _h(token)
    h["X-Sociman-Coleta-Protocolo"] = "2"
    r = client.get("/api/coleta/fila", headers=h)
    assert r.status_code == 426 and r.json()["error"]["code"] == "protocolo_coleta"
    assert r.json()["error"]["details"]["esperado"] == 1
    del h["X-Sociman-Coleta-Protocolo"]
    assert client.get("/api/coleta/fila", headers=h).status_code == 426


def test_limite_por_minuto_429(client, ligado):  # noqa: F811
    _, token = criar_cliente_coleta(client, ligado, limitePorMinuto=3)
    for _ in range(3):
        assert client.get("/api/coleta/fila", headers=_h(token)).status_code == 200
    r = client.get("/api/coleta/fila", headers=_h(token))
    assert r.status_code == 429 and r.json()["error"]["code"] == "coleta_limite"
    assert "Retry-After" in r.headers


def test_jwt_e_mcp_nao_entram_na_ingestao(client, ligado, db):  # noqa: F811
    r = client.get("/api/coleta/fila", headers=ligado)
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_coletor"


def test_passagem_marca_ultimo_contato_e_versao(client, db, ligado):  # noqa: F811
    cliente, token = criar_cliente_coleta(client, ligado)
    h = _h(token)
    h["X-Sociman-Coletor-Versao"] = "0.3.1"
    h["X-Sociman-Chrome-Versao"] = "131.0"
    assert client.get("/api/coleta/fila", headers=h).status_code == 200
    detalhe = client.get(f"/api/coleta/clientes/{cliente['id']}", headers=ligado).json()
    assert detalhe["ultimoContatoEm"] is not None
    assert detalhe["versaoColetor"] == "0.3.1" and detalhe["chromeVersao"] == "131.0"
    corpo = client.get("/api/coleta/clientes", headers=ligado).text
    assert token not in corpo and token.split("_", 2)[2] not in corpo
