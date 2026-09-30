"""Publicar no horário (spec 015, US3; T080 e T081; research R13): a tela obrigatória validada
ao agendar, o snapshot do que o dono confirmou (Q2 = A), o init direto só com o snapshot, a
revalidação com o `creator_info` no horário e o `publicado` com o link."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from integration import publicacao_helpers as ph
from integration.postagem_helpers import PW, add_destino, criar_corte
from integration.publicacao_helpers import MARCA, MUSICA, opcoes
from sociman_api.auth.deps import Actor, current_user
from sociman_api.db import get_engine
from sociman_api.main import app
from sociman_api.notificacoes.models import Notificacao
from sociman_api.postagem.models import DestinoEstado
from sociman_api.publicacao.models import TentativaFase

# Fixtures do apoio (o pytest as acha pelo nome no módulo).
app_tiktok = ph.app_tiktok
cena = ph.cena

def _err(r) -> str:
    return r.json()["error"]["code"]


def _futuro() -> datetime:
    return datetime.now(UTC) + timedelta(hours=2)


def _publicar(cena, corte=None, quando=None, **body):
    return cena.agendar(corte or cena.corte(), quando or _futuro(), modo="publicar",
                        opcoes=body.pop("op", opcoes()), **body)


def _get(cena, destino_id) -> dict:
    return cena.client.get(f"/api/destinos/{destino_id}", headers=cena.h).json()["destino"]


def _textos(cena, d: dict, h=None, **textos):
    return cena.client.patch(f"/api/destinos/{d['id']}", headers=h or cena.h,
                             json={"version": d["version"], **textos})


# ---- capacidades (R12) ----

def test_publicar_disponivel_com_o_aviso_do_sandbox(cena):
    modos = cena.client.get(f"/api/contas/{cena.conta['id']}/modos",
                            headers=cena.h).json()["modos"]
    publicar = next(m for m in modos if m["modo"] == "publicar")
    assert publicar["disponivel"] is True
    assert "só para você" in publicar["aviso"]


# ---- tela obrigatória ao agendar (T080) ----

def test_sem_opcoes_e_recusado(cena):
    r = cena.agendar(cena.corte(), _futuro(), modo="publicar")
    assert r.status_code == 400 and _err(r) == "opcoes_invalidas"
    assert r.json()["error"]["details"]["problemas"][0]["campo"] == "opcoes"


def test_privacidade_e_toggles_sem_valor_padrao(cena):
    sem = opcoes()
    del sem["privacidade"]
    r = _publicar(cena, op=sem)
    assert r.status_code == 400 and _err(r) == "validation_error"
    sem = opcoes()
    del sem["permitirDueto"]
    assert _publicar(cena, op=sem).status_code == 400


@pytest.mark.parametrize(("op", "campo"), [
    ({"privacidade": "PUBLIC_TO_EVERYONE"}, "privacidade"),  # sandbox: só "só você"
    ({"comercial": "parceria_paga",
      "consentimento": {"texto": MARCA, "aceitoEm": "2026-09-29T10:00:00+00:00"}}, "comercial"),
    ({"consentimento": {"texto": "ok", "aceitoEm": "2026-09-29T10:00:00+00:00"}},
     "consentimento"),
])
def test_combinacoes_proibidas(cena, op, campo):
    r = _publicar(cena, op=opcoes(**op))
    assert r.status_code == 400 and _err(r) == "opcoes_invalidas", r.text
    assert campo in [p["campo"] for p in r.json()["error"]["details"]["problemas"]]


def test_agendar_grava_o_snapshot_do_que_o_dono_confirmou(cena):
    corte = cena.corte()
    r = _publicar(cena, corte, textos={"titulo": "Atalho", "descricao": "Veja isto",
                                       "hashtags": ["dica", "tech"]})  # sem título (T101)
    assert r.status_code == 201, r.text
    d = r.json()["destino"]
    assert d["modo"] == "publicar" and d["opcoesRede"]["privacidade"] == "SELF_ONLY"
    assert d["snapshotDesatualizado"] is False
    snap = cena.destino(d["id"]).envio_snapshot
    assert snap["legenda"] == "Veja isto\n\n#dica #tech"
    assert r.json()["destino"]["legendaFinal"] == snap["legenda"]
    assert snap["opcoes"]["permitirComentario"] is True
    assert snap["consentimento"]["texto"] == MUSICA
    assert snap["videoRef"] == corte.result_key


def test_sequencia_nao_publica(cena):
    amanha = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    r = cena.client.post("/api/agendamentos/sequencia/previa", headers=cena.h, json={
        "contaId": cena.conta["id"], "conteudoIds": [str(cena.corte().id)], "inicio": amanha,
        "horarios": ["10:00"], "modo": "publicar"})
    assert r.status_code == 409 and _err(r) == "modo_indisponivel"


# ---- Q2 = A: textos de um publicar agendado ----

@pytest.fixture
def hm(cena, make_user, login):
    membro = make_user(role="membro", name="Membro")
    return login(cena.client, membro.email, PW)


def test_dono_edita_textos_e_regrava_o_snapshot(cena, hm):
    d = _publicar(cena, textos={"descricao": "Antes"}).json()["destino"]
    r = _textos(cena, d, h=hm, descricao="Do membro")
    assert r.status_code == 403 and _err(r) == "somente_dono"
    app.dependency_overrides[current_user] = lambda: Actor(
        kind="mcp_client", user_id=cena.dono.id, user=cena.dono)
    try:
        r = _textos(cena, d, h={"Authorization": "Bearer x"}, descricao="Do MCP")
    finally:
        app.dependency_overrides.pop(current_user, None)
    assert r.status_code == 403 and _err(r) == "somente_humano"
    assert cena.destino(d["id"]).envio_snapshot["legenda"] == "Antes"

    r = _textos(cena, d, descricao="Depois")
    assert r.status_code == 200, r.text
    assert cena.destino(d["id"]).envio_snapshot["legenda"] == "Depois"
    ultima = cena.versoes(d["id"])[-1]
    assert ultima.details["acao"] == "snapshot_atualizado" and ultima.actor_kind == "user"
    assert r.json()["destino"]["snapshotDesatualizado"] is False


def test_reversao_de_textos_deixa_o_snapshot_desatualizado(cena):
    d = _publicar(cena, textos={"descricao": "Um"}).json()["destino"]
    v_um = d["version"]
    d = _textos(cena, d, descricao="Dois").json()["destino"]
    r = cena.client.post(f"/api/destinos/{d['id']}/revert", headers=cena.h,
                         json={"version": d["version"], "toVersion": v_um})
    assert r.status_code == 200, r.text
    d = r.json()["destino"]
    assert d["descricao"] == "Um" and d["estado"] == "agendado" and d["modo"] == "publicar"
    assert d["snapshotDesatualizado"] is True  # o snapshot só muda com uma nova confirmação
    assert cena.destino(d["id"]).envio_snapshot["legenda"] == "Dois"
    # "Salvar de novo" (dono): os mesmos textos regravam o snapshot.
    r = _textos(cena, d, descricao="Um")
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["snapshotDesatualizado"] is False
    assert cena.destino(d["id"]).envio_snapshot["legenda"] == "Um"
    assert cena.versoes(d["id"])[-1].details["acao"] == "snapshot_atualizado"


def test_reagendar_troca_as_opcoes(cena):
    d = _publicar(cena).json()["destino"]
    r = cena.client.patch(f"/api/destinos/{d['id']}/agendamento", headers=cena.h, json={
        "version": d["version"], "opcoes": opcoes(permitirComentario=False)})
    assert r.status_code == 200, r.text
    assert cena.destino(d["id"]).envio_snapshot["opcoes"]["permitirComentario"] is False
    assert cena.versoes(d["id"])[-1].details["acao"] == "reagendado"


# ---- no horário (T081) ----

def test_publica_so_o_snapshot_e_chega_a_publicado(cena):
    d = _publicar(cena, quando=datetime.now(UTC),
                  textos={"descricao": "Confirmado", "hashtags": ["dica"]}).json()["destino"]
    # Um texto mudado por fora do fluxo (sem nova confirmação) nunca vai para a rede.
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE postagens SET descricao = 'Vivo, não confirmado'"))
    cena.fake.requests.clear()
    cena.rodar(4)
    init = cena.fake.pedidos("video_init")
    assert len(init) == 1 and cena.fake.pedidos("inbox_init") == []
    post = init[0]["post_info"]
    assert post["title"] == "Confirmado\n\n#dica"
    assert post["privacy_level"] == "SELF_ONLY"
    assert (post["disable_comment"], post["disable_duet"], post["disable_stitch"]) == \
        (False, True, True)
    assert post["brand_content_toggle"] is False and post["is_aigc"] is False
    assert cena.fake.pedidos("creator_info")  # revalidado na hora
    destino = cena.destino(d["id"])
    t = cena.tentativas(d["id"])[0]
    assert destino.estado == DestinoEstado.publicado
    assert t.fase == TentativaFase.publicada and t.rede_post_id
    assert destino.rede_post_id == t.rede_post_id
    out = _get(cena, d["id"])
    assert out["estadoEfetivo"] == "publicado"
    assert out["redePostUrl"] == \
        f"https://www.tiktok.com/@atavernanerd/video/{destino.rede_post_id}"
    cena.db.expire_all()
    assert cena.db.scalars(select(Notificacao).where(
        Notificacao.tipo == "envio_publicado")).one().user_id == cena.dono.id


@pytest.mark.parametrize("mudanca", ["privacidade", "comentario", "duracao", "nao_pode"])
def test_revalidacao_no_horario_recusa_sem_trocar_a_escolha(cena, mudanca):
    corte = cena.corte() if mudanca != "duracao" else None
    if mudanca == "duracao":
        corte = criar_corte(cena.db, cena.perfil["id"], duration_ms=900_000)
        ph.video(cena.db, corte)
    d = _publicar(cena, corte, quando=datetime.now(UTC)).json()["destino"]
    escolha = dict(cena.destino(d["id"]).opcoes_rede)
    if mudanca == "privacidade":
        cena.fake.criador["privacy_level_options"] = ["PUBLIC_TO_EVERYONE"]
    elif mudanca == "comentario":
        cena.fake.criador["comment_disabled"] = True
    elif mudanca == "nao_pode":
        cena.fake.falhar_proximo("creator_info", "spam_risk_too_many_posts")
    cena.rodar()
    destino = cena.destino(d["id"])
    t = cena.tentativas(d["id"])[0]
    assert cena.fake.inits == 0
    assert t.fase == TentativaFase.recusada and t.init_enviado_em is None
    assert destino.estado == DestinoEstado.falhou and not destino.falha_incerta
    assert destino.opcoes_rede == escolha
    assert t.details["acao"] == "reagendar"


def test_conta_publica_no_sandbox_falha_com_a_acao(cena):
    d = _publicar(cena, quando=datetime.now(UTC)).json()["destino"]
    cena.fake.falhar_proximo("video_init", "unaudited_client_can_only_post_to_private_accounts")
    cena.rodar()
    destino = cena.destino(d["id"])
    assert destino.estado == DestinoEstado.falhou
    assert destino.falha_motivo == "Sem auditoria, a conta precisa estar privada para publicar"
    assert cena.tentativas(d["id"])[0].details["acao"] == "deixar_privada"


def test_limite_de_posts_recusa_sem_espera(cena):
    d = _publicar(cena, quando=datetime.now(UTC)).json()["destino"]
    cena.fake.falhar_proximo("video_init", "spam_risk_too_many_posts")
    cena.rodar(2)
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.recusada and t.details["acao"] == "reagendar"
    assert cena.destino(d["id"]).estado == DestinoEstado.falhou
    assert len(cena.tentativas(d["id"])) == 1


def test_enviar_agora_publicando(cena):
    d = add_destino(cena.client, cena.h, cena.corte().id, cena.conta["id"], descricao="Legenda")
    r = cena.client.post(f"/api/destinos/{d['id']}/enviar-agora", headers=cena.h, json={
        "version": d["version"], "modo": "publicar", "opcoes": opcoes()})
    assert r.status_code == 200, r.text
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.publicado
