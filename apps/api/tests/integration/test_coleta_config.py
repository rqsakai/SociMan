"""T046 (US3): a gestão da coleta pelo dono humano: aceite de risco, interruptor em dois níveis,
tokens mostrados uma vez, rotação, revogação, pausar/continuar, membro e MCP recusados, versões."""

from sqlalchemy import select, text

from integration.coleta_helpers import (  # noqa: F401
    ColetorFake,
    bearer,
    coletor,
    criar_cliente_coleta,
    dono,
    ligado,
    ligar_coleta,
    membro,
)
from integration.mcp_helpers import bearer as bearer_mcp
from integration.mcp_helpers import criar_cliente, ligar
from sociman_api.auth.models import SecurityEvent

CORPO_CONFIG = {"janelaInicio": 0, "janelaFim": 23, "paginasDia": 300, "imagensDia": 1500,
                "imagensPorProduto": 9, "itensPorColeta": 40, "pausaMinS": 5, "pausaMaxS": 40}


def _eventos(db, tipo: str) -> list:
    return db.scalars(select(SecurityEvent).where(SecurityEvent.type == tipo)).all()


def test_ligar_sem_aceite_409_e_aceite_registra_quem_quando(client, db, dono,  # noqa: F811
                                                             coleta_habilitada):
    user, h = dono
    coleta_habilitada(True)
    cfg = client.get("/api/coleta/config", headers=h).json()
    assert cfg["riscoAceito"] is False and cfg["habilitada"] is False
    assert "conta de afiliado" in cfg["textoRisco"]
    r = client.put("/api/coleta/config", headers=h,
                   json={**CORPO_CONFIG, "habilitada": True, "version": cfg["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "risco_nao_aceito"
    # Sem a confirmação marcada, não aceita.
    r = client.post("/api/coleta/config/aceitar-risco", headers=h,
                    json={"version": cfg["version"], "textoVersao": "2026-10-08",
                          "confirmo": False})
    assert r.status_code == 400
    r = client.post("/api/coleta/config/aceitar-risco", headers=h,
                    json={"version": cfg["version"], "textoVersao": "2026-10-08",
                          "confirmo": True})
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["riscoAceito"] is True and cfg["riscoAceitoEm"]
    assert cfg["riscoAceitoPor"]["id"] == str(user.id)
    assert cfg["riscoTextoVersao"] == "2026-10-08"
    evs = _eventos(db, "coleta_aceite_risco")
    assert len(evs) == 1 and evs[0].details["textoVersao"] == "2026-10-08"
    # Agora liga.
    r = client.put("/api/coleta/config", headers=h,
                   json={**CORPO_CONFIG, "habilitada": True, "version": cfg["version"]})
    assert r.status_code == 200 and r.json()["habilitada"] is True
    # Versão velha → 409 version_conflict com a atual.
    r = client.put("/api/coleta/config", headers=h,
                   json={**CORPO_CONFIG, "habilitada": True, "version": cfg["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    # Janela e pausas validadas.
    atual = client.get("/api/coleta/config", headers=h).json()
    r = client.put("/api/coleta/config", headers=h,
                   json={**CORPO_CONFIG, "janelaInicio": 23, "janelaFim": 8, "habilitada": True,
                         "version": atual["version"]})
    assert r.status_code == 400 and r.json()["error"]["details"]["field"] == "janelaInicio"
    r = client.put("/api/coleta/config", headers=h,
                   json={**CORPO_CONFIG, "pausaMinS": 50, "pausaMaxS": 40, "habilitada": True,
                         "version": atual["version"]})
    assert r.status_code == 400 and r.json()["error"]["details"]["field"] == "pausaMinS"
    # Histórico: aceite e "ligada", com versões.
    vs = client.get("/api/coleta/config/versions", headers=h).json()["items"]
    assert [v["details"]["acao"] for v in vs][:2] == ["ligada", "aceite_risco"]


def test_token_uma_vez_lista_so_prefixo_rotacao_e_revogacao(client, db, ligado):  # noqa: F811
    r = client.post("/api/coleta/clientes", headers=ligado, json={"nome": "Desktop", "mercado": "BR"})
    assert r.status_code == 201, r.text
    assert r.headers.get("cache-control") == "no-store"
    body = r.json()
    token = body["token"]
    assert token.startswith("scol_") and "token" not in body["cliente"]
    assert body["cliente"]["tokenId"] == token.split("_")[1]
    # A lista e o detalhe só mostram o prefixo.
    lista = client.get("/api/coleta/clientes", headers=ligado).json()["itens"]
    assert [c["tokenId"] for c in lista] == [body["cliente"]["tokenId"]]
    assert token not in str(lista)
    det = client.get(f"/api/coleta/clientes/{body['cliente']['id']}", headers=ligado).json()
    assert token not in str(det)
    # O banco guarda só o hash.
    hashes = db.execute(text("SELECT token_hash FROM coleta_clientes")).scalars().all()
    assert hashes and all(len(x) in (32, 64) and token[6:].encode() not in bytes(x) for x in hashes)
    # O token funciona na fila.
    assert client.get("/api/coleta/fila", headers=bearer(token)).status_code == 200
    # Rotacionar: novo token_id; o antigo cai na hora.
    r = client.post(f"/api/coleta/clientes/{body['cliente']['id']}/rotacionar", headers=ligado,
                    json={"version": body["cliente"]["version"]})
    assert r.status_code == 200 and r.headers.get("cache-control") == "no-store"
    novo = r.json()
    assert novo["token"] != token and novo["cliente"]["tokenId"] != body["cliente"]["tokenId"]
    assert client.get("/api/coleta/fila", headers=bearer(token)).status_code == 401
    assert client.get("/api/coleta/fila", headers=bearer(novo["token"])).status_code == 200
    # Revogar é final: 401 no coletor e as ações seguintes recusadas.
    r = client.post(f"/api/coleta/clientes/{body['cliente']['id']}/revogar", headers=ligado,
                    json={"version": novo["cliente"]["version"]})
    assert r.status_code == 200 and r.json()["situacao"] == "revogado"
    assert client.get("/api/coleta/fila", headers=bearer(novo["token"])).status_code == 401
    r = client.post(f"/api/coleta/clientes/{body['cliente']['id']}/reativar", headers=ligado,
                    json={"version": r.json()["version"]})
    assert r.status_code == 409
    # O histórico do cliente nunca traz o segredo.
    vs = client.get(f"/api/coleta/clientes/{body['cliente']['id']}/versions", headers=ligado).json()
    assert token not in str(vs) and novo["token"] not in str(vs)


def test_servidor_desligado_pausar_e_continuar(client, db, dono, coleta_habilitada):  # noqa: F811
    _, h = dono
    ligar_coleta(client, h, coleta_habilitada)
    _, token = criar_cliente_coleta(client, h)
    fake = ColetorFake(client, token)
    # .env desligado: a fila vem vazia e a tela mostra "desligada no servidor".
    coleta_habilitada(False)
    fila = fake.fila()
    assert fila["tarefas"] == [] and fila["desligadaNoServidor"] is True
    estado = client.get("/api/coleta/estado", headers=h).json()
    assert estado["situacao"] == "desligada_no_servidor" and estado["servidorHabilitado"] is False
    cfg = client.get("/api/coleta/config", headers=h).json()
    assert cfg["servidorHabilitado"] is False
    coleta_habilitada(True)
    # Pausar N horas: a fila fica vazia até lá.
    cfg = client.get("/api/coleta/config", headers=h).json()
    r = client.post("/api/coleta/config/pausar", headers=h,
                    json={"version": cfg["version"], "horas": 2})
    assert r.status_code == 200 and r.json()["pausadaAte"]
    fila = fake.fila()
    assert fila["tarefas"] == [] and fila["motivoVazia"] == "pausada"
    assert client.get("/api/coleta/estado", headers=h).json()["situacao"] == "pausada"
    db.execute(text("UPDATE coleta_config SET pausada_ate = now() - interval '1 minute'"))
    db.commit()
    assert fake.fila()["motivoVazia"] != "pausada"
    # Continuar sem rodada pausada → 409; com captcha, grava continuarEm.
    cfg = client.get("/api/coleta/config", headers=h).json()
    r = client.post("/api/coleta/config/continuar", headers=h, json={"version": cfg["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "nada_a_continuar"
    fake.abrir()
    fake.evento("captcha")
    estado = client.get("/api/coleta/estado", headers=h).json()
    assert estado["situacao"] == "aguardando_continuar"
    assert estado["rodadaAtual"]["estado"] == "pausada_captcha"
    assert fake.fila()["motivoVazia"] == "aguardando_continuar"
    cfg = client.get("/api/coleta/config", headers=h).json()
    r = client.post("/api/coleta/config/continuar", headers=h, json={"version": cfg["version"]})
    assert r.status_code == 200 and r.json()["continuarEm"]
    assert client.get("/api/coleta/estado", headers=h).json()["situacao"] == "pausada_captcha"
    # Eventos e rodadas aparecem na leitura.
    evs = client.get("/api/coleta/eventos", headers=h).json()["itens"]
    assert any(e["tipo"] == "captcha" for e in evs)
    rodadas = client.get("/api/coleta/coletas", headers=h).json()["itens"]
    assert rodadas and rodadas[0]["estado"] in ("pausada_captcha", "ativa")
    det = client.get(f"/api/coleta/coletas/{rodadas[0]['id']}", headers=h).json()
    assert "itens" in det and "eventos" in det


def test_membro_so_le_e_mcp_recusado(client, db, ligado, membro, mcp_habilitado):  # noqa: F811
    _, hm = membro
    assert client.get("/api/coleta/estado", headers=hm).status_code == 200
    assert client.get("/api/coleta/coletas", headers=hm).status_code == 200
    assert client.get("/api/coleta/eventos", headers=hm).status_code == 200
    for metodo, url, corpo in [
        ("GET", "/api/coleta/config", None),
        ("GET", "/api/coleta/clientes", None),
        ("POST", "/api/coleta/clientes", {"nome": "x", "mercado": "BR"}),
        ("PUT", "/api/coleta/config", {**CORPO_CONFIG, "habilitada": True, "version": 1}),
        ("POST", "/api/coleta/config/aceitar-risco",
         {"version": 1, "textoVersao": "2026-10-08", "confirmo": True}),
        ("POST", "/api/coleta/config/pausar", {"version": 1, "horas": 1}),
        ("POST", "/api/coleta/config/revert", {"version": 1, "toVersion": 1}),
    ]:
        r = client.request(metodo, url, headers=hm, json=corpo)
        assert r.status_code == 403, (metodo, url, r.text)
    # MCP: o estado é tool de leitura; a gestão é PROIBIDA (somente_humano + publicacao_recusada).
    ligar(client, ligado, mcp_habilitado)
    _, tok = criar_cliente(client, ligado, "Analista", "propostas")
    assert client.get("/api/coleta/estado", headers=bearer_mcp(tok)).status_code == 200
    antes = len(_eventos(db, "publicacao_recusada"))
    r = client.post("/api/coleta/clientes", headers=bearer_mcp(tok),
                    json={"nome": "x", "mercado": "BR"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    r = client.put("/api/coleta/config", headers=bearer_mcp(tok),
                   json={**CORPO_CONFIG, "habilitada": False, "version": 1})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"
    assert len(_eventos(db, "publicacao_recusada")) == antes + 2
    # Revert da config: só o dono, e volta ao estado da versão.
    cfg = client.get("/api/coleta/config", headers=ligado).json()
    vs = client.get("/api/coleta/config/versions", headers=ligado).json()["items"]
    alvo = next(v for v in vs if v["details"].get("acao") == "aceite_risco")
    r = client.post("/api/coleta/config/revert", headers=ligado,
                    json={"version": cfg["version"], "toVersion": alvo["version"]})
    assert r.status_code == 200 and r.json()["habilitada"] is False
    assert r.json()["riscoAceito"] is True
