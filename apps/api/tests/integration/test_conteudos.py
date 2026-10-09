"""Central de conteúdos (spec 014, US1, T016): lista com filtros, atalhos, cursor e resumo;
estado efetivo igual no filtro e na saída; detalhe, título, arquivar/restaurar, histórico e
reversão. Os destinos entram direto pelo modelo (a US1 só lê)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from integration.postagem_helpers import (  # noqa: F401
    PW,
    criar_conta,
    criar_corte,
    criar_perfil,
    dono,
    membro,
)
from sociman_api import history
from sociman_api.auth.deps import CLI
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.cortes.models import CorteStatus
from sociman_api.perfis.models import Conta, ContaStatus
from sociman_api.postagem.models import APROVADOS, DestinoEstado, Postagem


def _destino(db, conteudo_id, conta_id, estado: DestinoEstado = DestinoEstado.pendente,
             planned_at: datetime | None = None, titulo: str = "", **extra) -> Postagem:
    agora = datetime.now(UTC)
    p = Postagem(
        conteudo_id=uuid.UUID(str(conteudo_id)), conta_id=uuid.UUID(str(conta_id)),
        titulo=titulo, estado=estado, planned_at=planned_at,
        aprovado_em=agora if estado in APROVADOS else None,
        pedido_em=agora if estado == DestinoEstado.aprovacao_pedida else None, **extra)
    db.add(p)
    db.commit()
    return p


def _video_proprio(db, perfil_id, titulo: str = "Meu vídeo") -> Conteudo:
    cid = uuid.uuid4()
    c = Conteudo(id=cid, perfil_id=uuid.UUID(perfil_id), origem=ConteudoOrigem.video_proprio,
                 titulo=titulo, video_key=f"conteudos/{cid}/video.mp4", poster_key="p.jpg",
                 duration_ms=5000, width=1920, height=1080)
    db.add(c)
    db.commit()
    return c


def _ids(r) -> list[str]:
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()["items"]]


@pytest.fixture
def cenario(client, db, dono):  # noqa: F811
    user, h = dono
    taverna = criar_perfil(client, h, "A Taverna Nerd")
    queridinhos = criar_perfil(client, h, "Queridinhos")
    tk = criar_conta(client, h, taverna["id"], "tiktok")
    yt = criar_conta(client, h, taverna["id"], "youtube")
    qtk = criar_conta(client, h, queridinhos["id"], "tiktok")
    return {"h": h, "user": user, "taverna": taverna, "queridinhos": queridinhos,
            "tk": tk, "yt": yt, "qtk": qtk}


def test_lista_recentes_com_cursor_sem_repetir_nem_pular(client, db, cenario):
    h, pid = cenario["h"], cenario["taverna"]["id"]
    cortes = [criar_corte(db, pid) for _ in range(5)]
    r = client.get("/api/conteudos", headers=h, params={"limit": 2})
    body = r.json()
    assert body["total"] == 5 and body["nextCursor"]
    primeira = _ids(r)
    assert primeira == [str(c.id) for c in reversed(cortes)][:2]
    # Entram cortes novos no meio da navegação: a página seguinte continua de onde parou.
    criar_corte(db, pid)
    criar_corte(db, pid)
    vistos = list(primeira)
    cursor = body["nextCursor"]
    while cursor:
        r = client.get("/api/conteudos", headers=h, params={"limit": 2, "cursor": cursor})
        vistos += _ids(r)
        cursor = r.json()["nextCursor"]
    assert vistos == [str(c.id) for c in reversed(cortes)]

    item = client.get("/api/conteudos", headers=h, params={"limit": 1}).json()["items"][0]
    assert item["origem"] == "corte" and item["corteId"] == item["id"]
    assert item["situacao"] == "pronto" and item["semConta"] is True and item["destinos"] == []
    assert item["perfil"]["name"] == "A Taverna Nerd" and item["durationMs"] == 30000
    assert item["archived"] is False and item["titulo"] == "Você usa isso?"


def test_cursor_invalido_e_periodo_invertido(client, cenario):
    h = cenario["h"]
    for params in ({"cursor": "nao-e-cursor"}, {"cursor": "WzEsMl0"},
                   {"criadoDe": "2026-10-02", "criadoAte": "2026-10-01"},
                   {"agendadoDe": "2026-10-02", "agendadoAte": "2026-10-01"}):
        r = client.get("/api/conteudos", headers=h, params=params)
        assert r.status_code == 400, params
        assert r.json()["error"]["code"] == "validation_error"
    assert client.get("/api/conteudos", headers=h,
                      params={"limit": 101}).status_code in (400, 422)


def test_filtros(client, db, cenario):
    h, tav, qu = cenario["h"], cenario["taverna"]["id"], cenario["queridinhos"]["id"]
    amanha = datetime.now(UTC) + timedelta(days=1)
    a = criar_corte(db, tav, openshorts_title="Dragões e masmorras")
    b = criar_corte(db, tav, status=CorteStatus.revisao, hook_text="Gancho secreto")
    c = criar_corte(db, qu)
    v = _video_proprio(db, qu, "Unboxing caseiro")
    _destino(db, a.id, cenario["tk"]["id"], DestinoEstado.agendado, amanha, titulo="Rolando d20")
    _destino(db, a.id, cenario["yt"]["id"], DestinoEstado.aprovado)
    _destino(db, c.id, cenario["qtk"]["id"], DestinoEstado.aprovacao_pedida)

    def ids(**params):
        return set(_ids(client.get("/api/conteudos", headers=h, params=params)))

    assert ids() == {str(x) for x in (a.id, b.id, c.id, v.id)}
    assert ids(perfilId=[tav]) == {str(a.id), str(b.id)}
    assert ids(perfilId=[tav, qu]) == {str(x) for x in (a.id, b.id, c.id, v.id)}
    assert ids(contaId=cenario["yt"]["id"]) == {str(a.id)}
    assert ids(plataforma="tiktok") == {str(a.id), str(c.id)}
    assert ids(estado=["agendado"]) == {str(a.id)}
    assert ids(estado=["aprovado", "aprovacao_pedida"]) == {str(a.id), str(c.id)}
    assert ids(estado=["sem_conta"]) == {str(b.id), str(v.id)}
    assert ids(estado=["sem_conta"], contaId=cenario["yt"]["id"]) == {
        str(b.id), str(c.id), str(v.id)}
    assert ids(origem="video_proprio") == {str(v.id)}
    hoje = datetime.now(UTC).date()
    assert ids(agendadoDe=str(hoje), agendadoAte=str(hoje + timedelta(days=2))) == {str(a.id)}
    assert ids(agendadoAte=str(hoje - timedelta(days=1))) == set()
    assert ids(criadoDe=str(hoje - timedelta(days=1))) == {
        str(x) for x in (a.id, b.id, c.id, v.id)}
    assert ids(criadoAte=str(hoje - timedelta(days=2))) == set()
    # Busca nos títulos do conteúdo, do destino, do gancho e do OpenShorts.
    assert ids(q="dragões") == {str(a.id)}  # título do conteúdo (veio do OpenShorts)
    assert ids(q="D20") == {str(a.id)}  # título do destino
    assert ids(q="secreto") == {str(b.id)}  # gancho
    assert ids(q="unboxing") == {str(v.id)}
    assert ids(q="100%") == set()  # o % é literal


def test_estado_efetivo_igual_no_filtro_e_na_saida(client, db, cenario):
    h, tav = cenario["h"], cenario["taverna"]["id"]
    agora = datetime.now(UTC)
    a_postar = criar_corte(db, tav)
    atrasado = criar_corte(db, tav)
    atencao = criar_corte(db, tav)
    revisao = criar_corte(db, tav, status=CorteStatus.revisao)
    pendente = criar_corte(db, tav)
    _destino(db, a_postar.id, cenario["tk"]["id"], DestinoEstado.agendado,
             agora - timedelta(minutes=5))
    _destino(db, atrasado.id, cenario["tk"]["id"], DestinoEstado.agendado,
             agora - timedelta(hours=25))
    _destino(db, atencao.id, cenario["yt"]["id"], DestinoEstado.agendado,
             agora + timedelta(days=1))
    _destino(db, revisao.id, cenario["tk"]["id"], DestinoEstado.pendente)
    _destino(db, pendente.id, cenario["tk"]["id"], DestinoEstado.pendente)
    conta = db.get(Conta, uuid.UUID(cenario["yt"]["id"]))
    conta.status = ContaStatus.pausada
    db.commit()

    esperado = {a_postar.id: "a_postar", atrasado.id: "atrasado", atencao.id: "atencao",
                revisao.id: "em_revisao", pendente.id: "pronto"}
    for cid, estado in esperado.items():
        r = client.get("/api/conteudos", headers=h, params={"estado": estado})
        assert _ids(r) == [str(cid)], estado
        (d,) = r.json()["items"][0]["destinos"]
        assert d["estadoEfetivo"] == estado
        assert d["motivoAtencao"] == ("Conta pausada" if estado == "atencao" else None)
    item = client.get("/api/conteudos", headers=h,
                      params={"estado": "em_revisao"}).json()["items"][0]
    assert item["situacao"] == "em_revisao"


def test_atalhos_ordem_agenda_e_resumo(client, db, cenario):
    h, tav = cenario["h"], cenario["taverna"]["id"]
    agora = datetime.now(UTC)
    sem_destino = criar_corte(db, tav)
    so_pendente = criar_corte(db, tav)
    aprovado = criar_corte(db, tav)
    pedido = criar_corte(db, tav)
    hoje = criar_corte(db, tav)
    depois = criar_corte(db, tav)
    atrasado = criar_corte(db, tav)
    postado = criar_corte(db, tav)
    criar_corte(db, tav, status=CorteStatus.revisao)  # em revisão: não é "pronto"
    tk, yt = cenario["tk"]["id"], cenario["yt"]["id"]
    _destino(db, so_pendente.id, tk)
    _destino(db, aprovado.id, tk, DestinoEstado.aprovado)
    _destino(db, pedido.id, yt, DestinoEstado.aprovacao_pedida)
    em_uma_hora = agora + timedelta(minutes=1)
    _destino(db, hoje.id, tk, DestinoEstado.agendado, em_uma_hora)
    _destino(db, depois.id, yt, DestinoEstado.agendado, agora + timedelta(days=40))
    _destino(db, atrasado.id, tk, DestinoEstado.agendado, agora - timedelta(days=2))
    _destino(db, postado.id, tk, DestinoEstado.postado, agora - timedelta(days=3))

    def ids(**params):
        return set(_ids(client.get("/api/conteudos", headers=h, params=params)))

    s = {str(x.id) for x in (sem_destino, so_pendente, aprovado, pedido)}
    assert ids(atalho="prontos_sem_agendamento") == s
    # Com a conta, "sem agendamento nesta conta": o agendado só no YouTube entra.
    assert ids(atalho="prontos_sem_agendamento", contaId=tk) == s | {str(depois.id)}
    assert ids(atalho="aprovados_sem_data") == {str(aprovado.id)}
    assert ids(atalho="aprovacao_pedida") == {str(pedido.id)}
    assert ids(atalho="a_postar") == set()
    assert ids(atalho="atrasados") == {str(atrasado.id)}
    assert ids(atalho="falharam") == set()
    assert str(depois.id) not in ids(atalho="esta_semana")
    assert str(atrasado.id) not in ids(atalho="agendados_hoje")

    r = client.get("/api/conteudos/resumo", headers=h, params={"perfilId": tav})
    assert r.status_code == 200, r.text
    resumo = r.json()
    nomes = {"prontosSemAgendamento": "prontos_sem_agendamento",
             "aprovadosSemData": "aprovados_sem_data", "aprovacaoPedida": "aprovacao_pedida",
             "agendadosHoje": "agendados_hoje", "estaSemana": "esta_semana",
             "aPostar": "a_postar", "atrasados": "atrasados", "falharam": "falharam",
             # spec 015
             "vencidos": "vencidos", "enviando": "enviando",
             "rascunhosCriados": "rascunhos_criados"}
    assert set(resumo) == set(nomes)
    for chave, atalho in nomes.items():
        assert resumo[chave] == len(ids(atalho=atalho, perfilId=tav)), chave
    assert resumo["prontosSemAgendamento"] == 4 and resumo["aprovacaoPedida"] == 1
    por_conta = client.get("/api/conteudos/resumo", headers=h,
                           params={"perfilId": tav, "contaId": yt}).json()
    assert por_conta["aprovacaoPedida"] == 1 and por_conta["atrasados"] == 0

    # Ordem da agenda: próximo agendamento primeiro; sem agendamento no fim; com cursor.
    vistos, cursor = [], None
    while True:
        params = {"ordem": "agenda", "limit": 3, "perfilId": tav}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/api/conteudos", headers=h, params=params).json()
        vistos += [i["id"] for i in body["items"]]
        cursor = body["nextCursor"]
        if not cursor:
            break
    assert vistos[:3] == [str(atrasado.id), str(hoje.id), str(depois.id)]
    assert len(vistos) == len(set(vistos)) == 9


def test_detalhe_titulo_versions_e_revert(client, db, cenario, membro):  # noqa: F811
    h, tav = cenario["h"], cenario["taverna"]["id"]
    _, hm = membro
    corte = criar_corte(db, tav)
    conteudo = db.get(Conteudo, corte.id)
    history.record(db, CLI, "conteudo", conteudo, "created", None, history.snapshot(conteudo))
    db.commit()
    _destino(db, corte.id, cenario["tk"]["id"], DestinoEstado.aprovado, titulo="Oi")
    r = client.get(f"/api/conteudos/{corte.id}", headers=hm)
    assert r.status_code == 200, r.text
    c = r.json()["conteudo"]
    assert c["version"] == 1 and c["width"] == 1080 and c["height"] == 1920
    assert c["naoVertical"] is False and c["originalFilename"] == "clipe.mp4"
    (d,) = c["destinos"]
    assert d["estado"] == "aprovado" and d["estadoEfetivo"] == "aprovado"
    assert d["conta"]["status"] == "ativa" and d["titulo"] == "Oi" and d["modo"] == "lembrete"
    assert client.get(f"/api/conteudos/{uuid.uuid4()}", headers=h).status_code == 404

    r = client.patch(f"/api/conteudos/{corte.id}", headers=hm,
                     json={"version": 1, "titulo": "  Novo título  "})
    assert r.status_code == 200, r.text
    assert r.json()["conteudo"]["titulo"] == "Novo título"
    assert r.json()["conteudo"]["version"] == 2
    r = client.patch(f"/api/conteudos/{corte.id}", headers=hm,
                     json={"version": 1, "titulo": "Outro"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    assert client.patch(f"/api/conteudos/{corte.id}", headers=hm,
                        json={"version": 2, "titulo": "x" * 101}).status_code in (400, 422)

    vs = client.get(f"/api/conteudos/{corte.id}/versions", headers=hm).json()["items"]
    assert [v["action"] for v in vs] == ["updated", "created"]
    assert vs[0]["before"]["titulo"] == "Você usa isso?"

    body = {"version": 2, "toVersion": 1}
    assert client.post(f"/api/conteudos/{corte.id}/revert", headers=hm,
                       json=body).status_code == 403
    r = client.post(f"/api/conteudos/{corte.id}/revert", headers=h, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["conteudo"]["titulo"] == "Você usa isso?"
    assert r.json()["conteudo"]["version"] == 3


def test_arquivar_na_origem_corte_segue_o_corte(client, db, cenario):
    h, tav = cenario["h"], cenario["taverna"]["id"]
    corte = criar_corte(db, tav)
    r = client.post(f"/api/conteudos/{corte.id}/archive", headers=h, json={"version": 1})
    assert r.status_code == 200, r.text
    assert r.json()["conteudo"]["archived"] is True
    corte_api = client.get(f"/api/cortes/{corte.id}", headers=h).json()["corte"]
    assert corte_api["archived"] is True
    # Arquivado: fora da lista padrão, dentro de `archived=true`; título não muda.
    assert _ids(client.get("/api/conteudos", headers=h)) == []
    assert _ids(client.get("/api/conteudos", headers=h,
                           params={"archived": "true"})) == [str(corte.id)]
    r = client.patch(f"/api/conteudos/{corte.id}", headers=h,
                     json={"version": 1, "titulo": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    r = client.post(f"/api/conteudos/{corte.id}/archive", headers=h, json={"version": 1})
    assert r.status_code == 409
    r = client.post(f"/api/conteudos/{corte.id}/restore", headers=h, json={"version": 1})
    assert r.status_code == 200 and r.json()["conteudo"]["archived"] is False
    # O corte processando não arquiva (a regra do corte).
    proc = criar_corte(db, tav, status=CorteStatus.processando)
    r = client.post(f"/api/conteudos/{proc.id}/archive", headers=h, json={"version": 1})
    assert r.status_code == 409


def test_video_proprio_arquiva_e_reverte_pelo_proprio_conteudo(client, db, cenario):
    h, qu = cenario["h"], cenario["queridinhos"]["id"]
    v = _video_proprio(db, qu)
    r = client.get(f"/api/conteudos/{v.id}", headers=h)
    c = r.json()["conteudo"]
    assert c["origem"] == "video_proprio" and c["situacao"] == "pronto"
    assert c["naoVertical"] is True and c["corteId"] is None and c["durationMs"] == 5000
    # Sem versão `created` (inserido direto): arquivar grava a 2.
    r = client.post(f"/api/conteudos/{v.id}/archive", headers=h, json={"version": 1})
    assert r.status_code == 200 and r.json()["conteudo"]["archived"] is True
    r = client.post(f"/api/conteudos/{v.id}/revert", headers=h,
                    json={"version": 2, "toVersion": 2})
    assert r.status_code == 400  # a versão atual
    r = client.post(f"/api/conteudos/{v.id}/restore", headers=h, json={"version": 2})
    assert r.status_code == 200 and r.json()["conteudo"]["archived"] is False
    r = client.post(f"/api/conteudos/{v.id}/revert", headers=h,
                    json={"version": 3, "toVersion": 2})
    assert r.status_code == 200 and r.json()["conteudo"]["archived"] is True


def test_arquivar_cancela_agendamentos_e_restaurar_nao_reagenda(client, db, cenario):
    """T041: pelo conteúdo, pela rota do corte (006) e no vídeo próprio."""
    h, tav, qu = cenario["h"], cenario["taverna"]["id"], cenario["queridinhos"]["id"]
    amanha = datetime.now(UTC) + timedelta(days=1)
    pelo_conteudo = criar_corte(db, tav)
    pelo_corte = criar_corte(db, tav)
    proprio = _video_proprio(db, qu)
    destinos = {
        "conteudo": _destino(db, pelo_conteudo.id, cenario["tk"]["id"],
                             DestinoEstado.agendado, amanha),
        "corte": _destino(db, pelo_corte.id, cenario["tk"]["id"], DestinoEstado.agendado,
                          amanha),
        "proprio": _destino(db, proprio.id, cenario["qtk"]["id"], DestinoEstado.agendado,
                            amanha),
    }
    outro = _destino(db, pelo_corte.id, cenario["yt"]["id"], DestinoEstado.aprovado)
    corte = client.get(f"/api/cortes/{pelo_corte.id}", headers=h).json()["corte"]
    assert {d["estado"] for d in corte["destinos"]} == {"agendado", "aprovado"}
    assert "postagens" not in corte

    for cid in (pelo_conteudo.id, proprio.id):
        r = client.post(f"/api/conteudos/{cid}/archive", headers=h, json={"version": 1})
        assert r.status_code == 200, r.text
    r = client.post(f"/api/cortes/{pelo_corte.id}/archive", headers=h,
                    json={"version": corte["version"]})
    assert r.status_code == 200, r.text

    db.expire_all()
    for nome, d in destinos.items():
        linha = db.get(Postagem, d.id)
        assert linha.estado == DestinoEstado.aprovado and linha.planned_at is None, nome
        (v,) = history.list_versions(db, "postagem", d.id)[:1]
        assert v.details.get("acao") == "cancelado_por_arquivo", nome
    assert db.get(Postagem, outro.id).estado == DestinoEstado.aprovado  # nada a cancelar

    r = client.post(f"/api/conteudos/{pelo_conteudo.id}/restore", headers=h, json={"version": 1})
    assert r.status_code == 200
    (d,) = r.json()["conteudo"]["destinos"]
    assert d["estado"] == "aprovado" and d["plannedAt"] is None  # restaurar não reagenda
