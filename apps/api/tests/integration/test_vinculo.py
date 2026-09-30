"""Vínculo do post com o destino (spec 016, R9 a R12; Q3 = A; contrato, "Métricas e vínculo do
destino"): os três níveis, lembrete antes e depois do clique, desfazer, bloqueio e histórico.

Tudo contra a TikTok falsa, com as voltas da trilha `metricas` chamadas à mão. Nenhum teste chama
a TikTok real.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from integration.conexao_helpers import app_tiktok, destino_auto  # noqa: F401
from integration.metricas_helpers import HANDLE, OUTRA, POST_ID, _agora, err, m  # noqa: F401
from integration.postagem_helpers import LEGENDA, criar_corte, membro  # noqa: F401
from sociman_api.auth.deps import Actor, current_user
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion
from sociman_api.main import app
from sociman_api.metricas import vinculos
from sociman_api.metricas.models import VideoRede, VinculoMetodo
from sociman_api.postagem.models import DestinoEstado
from sociman_api.publicacao.models import Tentativa


def _sem_ids_da_rede(versoes: list[EntityVersion], *ids: str) -> None:
    for v in versoes:
        texto = f"{v.details} {v.before} {v.after}"
        for i in ids:
            assert i not in texto
        assert "tiktok.com" not in texto


# ---- nível 1: busca do post ----

def test_nivel_1_rascunho_publicado_vira_publicado_pelo_envio(m):  # noqa: F811
    d = m.rascunho(legenda=LEGENDA)
    t_antes = m.db.scalars(select(Tentativa).where(
        Tentativa.destino_id == uuid.UUID(d["id"]))).one()
    fase, concluida = t_antes.fase, t_antes.concluida_em
    m.coletar()  # a busca nasce e a 1ª consulta sai: ainda na caixa do app
    busca = m.busca(d["id"])
    assert busca is not None and busca.encerrada_em is None and busca.consultas == 1
    assert busca.ultimo_status == "SEND_TO_USER_INBOX"
    assert busca.entregue_em == concluida
    assert timedelta(minutes=9) < busca.proxima_em - _agora() <= timedelta(minutes=10)
    assert m.vinculo(d["id"])["estado"] == "buscando"

    # O dono finaliza no app com uma legenda diferente (o casamento não liga; o envio liga).
    m.post(POST_ID, legenda=OUTRA)
    m.fake.publicar_rascunho(m.publish_id(d), POST_ID)
    m.coletar(_agora() + timedelta(minutes=11))
    destino = m.destino(d["id"])
    v = m.video_de(POST_ID)
    assert destino.estado == DestinoEstado.publicado
    assert v.destino_id == destino.id and v.vinculo_metodo == VinculoMetodo.envio
    assert v.vinculado_por is None and v.vinculado_em is not None
    busca = m.busca(d["id"])
    assert busca.fim == "vinculado" and busca.post_id == POST_ID and busca.proxima_em is None
    # A tentativa da 015 não muda.
    t = m.db.scalars(select(Tentativa).where(Tentativa.destino_id == destino.id)).one()
    assert (t.fase, t.concluida_em) == (fase, concluida)
    assert len(m.avisos("post_detectado")) == 1
    m.coletar(_agora() + timedelta(minutes=30))
    assert len(m.avisos("post_detectado")) == 1  # dedupe por destino
    ultima = m.versoes(d["id"])[-1]
    assert ultima.details == {"acao": "vinculo_feito", "metodo": "envio", "automatico": True}
    assert ultima.actor_kind == "system:metricas" and ultima.actor_user_id is None
    assert (ultima.before["estado"], ultima.after["estado"]) == ("rascunho_criado", "publicado")
    _sem_ids_da_rede(m.versoes(d["id"]), POST_ID)
    vin = m.vinculo(d["id"])
    assert vin["estado"] == "vinculado" and vin["metodo"] == "envio"
    assert vin["vinculadoPor"] is None and vin["video"]["url"]


def test_agenda_das_consultas_do_nivel_1():
    e = datetime(2026, 9, 30, 12, tzinfo=UTC)
    assert vinculos.proxima_consulta(e, e) == e + timedelta(minutes=10)
    assert vinculos.proxima_consulta(e, e + timedelta(hours=3)) == \
        e + timedelta(hours=3, minutes=30)
    assert vinculos.proxima_consulta(e, e + timedelta(days=2)) == e + timedelta(days=2, hours=3)
    assert vinculos.proxima_consulta(e, e + timedelta(days=5)) == e + timedelta(days=5, hours=12)
    assert vinculos.proxima_consulta(e, e + timedelta(days=13, hours=20)) == \
        e + timedelta(days=14)
    assert vinculos.proxima_consulta(e, e + timedelta(days=14)) is None


def test_nivel_1_falhou_e_prazo_encerram_a_busca(m):  # noqa: F811
    d1 = m.rascunho(legenda=OUTRA)
    m.fake.envios[m.publish_id(d1)].fail_reason = "file_format_check_failed"
    m.coletar()
    assert m.busca(d1["id"]).fim == "falhou"

    d2 = m.rascunho(legenda=OUTRA)
    m.coletar()
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE metricas_buscas_post SET entregue_em = now() - interval "
                          "'15 days', proxima_em = now() WHERE destino_id = :d"), {"d": d2["id"]})
    m.coletar()
    busca = m.busca(d2["id"])
    assert busca.fim == "prazo" and busca.proxima_em is None
    assert m.destino(d2["id"]).estado == DestinoEstado.rascunho_criado
    assert m.vinculo(d2["id"])["estado"] == "sem_vinculo"


def test_nivel_1_video_nao_devolvido_so_consulta_a_cada_12h(m):  # noqa: F811
    d = m.rascunho(legenda=OUTRA)
    m.fake.publicar_rascunho(m.publish_id(d), POST_ID)  # o post id existe, o vídeo não
    m.coletar()
    busca = m.busca(d["id"])
    assert busca.post_id == POST_ID and busca.fim is None
    assert timedelta(hours=11) < busca.proxima_em - _agora() <= timedelta(hours=12)
    status = len(m.fake.pedidos("status"))
    m.post(POST_ID, legenda=OUTRA)
    m.coletar(_agora() + timedelta(hours=12, minutes=1))
    assert len(m.fake.pedidos("status")) == status  # só o video/query agora
    assert m.video_de(POST_ID).destino_id == uuid.UUID(d["id"])


def test_modo_publicar_liga_pelo_rede_post_id_sem_busca(m):  # noqa: F811
    destino = destino_auto(m.db, m.perfil["id"], m.conta["id"], m.dono, estado="publicado",
                           modo="publicar", rede_post_id=POST_ID, planned_at=_agora())
    m.post(POST_ID, legenda=OUTRA)
    m.coletar(_agora() + timedelta(hours=2))  # a 1ª página da lista de hora em hora
    v = m.video_de(POST_ID)
    assert v.destino_id == destino.id and v.vinculo_metodo == VinculoMetodo.envio
    assert m.destino(destino.id).estado == DestinoEstado.publicado
    assert m.busca(destino.id) is None


def test_destino_arquivado_cancela_a_busca(m):  # noqa: F811
    d = m.rascunho(legenda=OUTRA)
    m.coletar()
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE postagens SET archived_at = now() WHERE id = :d"),
                     {"d": d["id"]})
    m.coletar()
    assert m.busca(d["id"]).fim == "cancelada"


# ---- nível 2: casamento ----

def test_nivel_2_candidato_unico_liga_pelo_casamento(m):  # noqa: F811
    d = m.rascunho(legenda=LEGENDA)
    pid = m.post(legenda=f"{LEGENDA} #fyp 🔥")
    m.coletar(_agora() + timedelta(hours=2))
    v = m.video_de(pid)
    assert v.destino_id == uuid.UUID(d["id"]) and v.vinculo_metodo == VinculoMetodo.casamento
    assert v.vinculado_por is None
    assert m.destino(d["id"]).estado == DestinoEstado.publicado
    ultima = m.versoes(d["id"])[-1]
    assert ultima.details == {"acao": "vinculo_feito", "metodo": "casamento", "automatico": True}


def test_nivel_2_ambiguo_nao_liga_e_avisa_uma_vez(m):  # noqa: F811
    d = m.rascunho(legenda=LEGENDA)
    p1 = m.post(minutos=0)
    p2 = m.post(minutos=1)
    m.coletar(_agora() + timedelta(hours=2))
    assert m.video_de(p1).destino_id is None and m.video_de(p2).destino_id is None
    assert m.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    avisos = m.avisos("vinculo_a_confirmar")
    assert len(avisos) == 1 and avisos[0].entity_id == uuid.UUID(d["id"])
    m.coletar(_agora() + timedelta(hours=3))
    assert len(m.avisos("vinculo_a_confirmar")) == 1
    vin = m.vinculo(d["id"])
    assert vin["estado"] == "a_confirmar" and vin["ancora"] == "entrega"
    assert {c["video"]["id"] for c in vin["candidatos"]} == \
        {str(m.video_de(p1).id), str(m.video_de(p2).id)}
    # O dono escolhe um em 1 clique.
    r = m.ligar(d, videoId=str(m.video_de(p2).id))
    assert r.status_code == 200, r.text
    assert r.json()["vinculo"]["metodo"] == "escolha"
    assert r.json()["destino"]["estado"] == "publicado"
    assert m.video_de(p2).vinculado_por == m.dono.id


def test_duracao_fora_de_1s_nao_casa(m):  # noqa: F811
    d = m.rascunho(legenda=LEGENDA)
    pid = m.post(duracao=32)
    m.coletar(_agora() + timedelta(hours=2))
    assert m.video_de(pid).destino_id is None
    assert m.vinculo(d["id"])["candidatos"] == []


# ---- lembrete (Q3 = A) ----

def test_lembrete_antes_do_clique_so_lista_candidatos_e_a_escolha_marca_postado(m):  # noqa: F811
    d = m.lembrete()
    pid = m.post(minutos=30)
    m.post(duracao=50)  # duração fora: não é candidato
    m.coletar(_agora() + timedelta(hours=2))
    assert m.video_de(pid).destino_id is None  # nunca liga sozinho antes do clique
    assert m.avisos("vinculo_a_confirmar") == []
    vin = m.vinculo(d["id"])
    assert vin["estado"] == "sem_vinculo" and vin["ancora"] is None and vin["podeVincular"]
    assert [c["video"]["id"] for c in vin["candidatos"]] == [str(m.video_de(pid).id)]
    r = m.ligar(d, videoId=str(m.video_de(pid).id))
    assert r.status_code == 200, r.text
    destino = m.destino(d["id"])
    assert destino.estado == DestinoEstado.postado and destino.posted_url is None
    assert m.video_de(pid).vinculo_metodo == VinculoMetodo.escolha
    acoes = [v.details.get("acao") for v in m.versoes(d["id"])]
    assert acoes[-2:] == ["postado", "vinculo_feito"]


def test_lembrete_depois_do_clique_liga_sozinho_e_continua_postado(m):  # noqa: F811
    d = m.postado(m.lembrete())
    pid = m.post(minutos=20)
    m.coletar(_agora() + timedelta(hours=1, minutes=5))
    v = m.video_de(pid)
    assert v.destino_id == uuid.UUID(d["id"]) and v.vinculo_metodo == VinculoMetodo.casamento
    assert m.destino(d["id"]).estado == DestinoEstado.postado
    assert m.avisos("post_detectado") == []  # o estado não mudou


def test_lembrete_postado_fora_da_janela_nao_liga(m):  # noqa: F811
    pid = m.post(minutos=60 * 25)  # 25 h antes do clique
    m.coletar(_agora() + timedelta(hours=1, minutes=5))
    d = m.postado(m.lembrete())
    m.coletar(_agora() + timedelta(minutes=5))
    assert m.video_de(pid).destino_id is None
    assert m.vinculo(d["id"])["ancora"] == "postado"


def test_lembrete_postado_sem_video_fica_buscando(m):  # noqa: F811
    d = m.postado(m.lembrete())
    assert m.vinculo(d["id"])["estado"] == "buscando"


# ---- nível 3: link ----

def _link(pid: str, handle: str = HANDLE) -> str:
    return f"https://www.tiktok.com/@{handle}/video/{pid}?is_from_webapp=1"


def test_link_valido_liga_e_no_lembrete_marca_postado_com_o_link(m):  # noqa: F811
    d = m.lembrete()
    pid = m.post(POST_ID, minutos=10)  # ainda não descoberto: a rota consulta a rede
    r = m.ligar(d, link=_link(pid))
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["vinculo"]["estado"] == "vinculado" and corpo["vinculo"]["metodo"] == "link"
    assert corpo["destino"]["estado"] == "postado"
    assert corpo["destino"]["postedUrl"] == _link(pid)
    v = m.video_de(pid)
    assert v.vinculado_por == m.dono.id and v.rede_video_id == POST_ID
    assert m.db.execute(text("SELECT count(*) FROM metricas_video_fotos WHERE video_id = :v"),
                        {"v": v.id}).scalar() == 1  # a foto de descoberta


def test_link_de_rascunho_leva_a_publicado(m):  # noqa: F811
    d = m.rascunho(legenda=OUTRA)
    pid = m.post(minutos=1, legenda=OUTRA)
    r = m.ligar(d, link=_link(pid))
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "publicado"
    ultima = m.versoes(d["id"])[-1]
    assert ultima.details == {"acao": "vinculo_feito", "metodo": "link", "automatico": False}
    _sem_ids_da_rede(m.versoes(d["id"]), pid)


def test_link_recusado_com_o_motivo(m):  # noqa: F811
    d = m.lembrete()
    r = m.ligar(d, link=_link(POST_ID, "meusqueridinhos10"))
    assert r.status_code == 409 and err(r) == "link_outra_conta"
    assert "@meusqueridinhos10" in r.json()["error"]["message"]
    r = m.ligar(d, link="https://vm.tiktok.com/ZMabc/")
    assert r.status_code == 400 and err(r) == "link_invalido"
    # O vídeo é de outra conta (o `video/query` com o token desta não o devolve).
    m.post("7412345678901234999", handle="meusqueridinhos10")
    r = m.ligar(d, link=_link("7412345678901234999"))
    assert r.status_code == 404 and err(r) == "post_nao_encontrado"
    m.fake.falhar_proximo("video_query", "5xx")
    r = m.ligar(d, link=_link("7412345678901234888"))
    assert r.status_code == 502 and err(r) == "rede_indisponivel"
    assert m.destino(d["id"]).estado == DestinoEstado.aprovado  # nada mudou


def test_erros_de_conflito(m):  # noqa: F811
    d1 = m.lembrete()
    d2 = m.lembrete()
    pid = m.post(minutos=5)
    m.coletar(_agora() + timedelta(hours=1, minutes=5))
    vid = str(m.video_de(pid).id)
    assert m.ligar(d1, videoId=vid).status_code == 200
    r = m.ligar(d2, videoId=vid)
    assert r.status_code == 409 and err(r) == "video_ja_vinculado"
    assert r.json()["error"]["details"]["destinoId"] == d1["id"]
    outro = m.post(minutos=6)
    m.coletar(_agora() + timedelta(hours=3))
    r = m.ligar(d1, videoId=str(m.video_de(outro).id))
    assert r.status_code == 409 and err(r) == "destino_ja_vinculado"
    # Destino pendente (fora de R12).
    corte = criar_corte(m.db, m.perfil["id"])
    r = m.client.post(f"/api/conteudos/{corte.id}/destinos", headers=m.h,
                      json={"contaId": m.conta["id"]})
    pendente = r.json()["destino"]
    r = m.ligar(pendente, videoId=str(m.video_de(outro).id))
    assert r.status_code == 409 and err(r) == "destino_sem_post"
    # Versão velha.
    r = m.client.post(f"/api/destinos/{d2['id']}/vinculo", headers=m.h,
                      json={"version": 1, "videoId": str(m.video_de(outro).id)})
    assert r.status_code == 409 and err(r) == "version_conflict"
    # Vídeo de outra série (id qualquer) → não encontrado.
    r = m.ligar(d2, videoId=str(uuid.uuid4()))
    assert r.status_code == 404 and err(r) == "post_nao_encontrado"
    # Corpo com os dois (ou nenhum) → 400.
    r = m.ligar(d2, videoId=vid, link=_link(pid))
    assert r.status_code == 400


def test_conta_sem_serie_ativa_nao_liga(m, monkeypatch):  # noqa: F811
    from sociman_api.config import get_settings

    d = m.lembrete()
    monkeypatch.setattr(get_settings(), "metricas_coleta_habilitada", False)
    vin = m.vinculo(d["id"])
    assert vin["estado"] == "indisponivel" and not vin["podeVincular"]
    r = m.ligar(d, link=_link(POST_ID))
    assert r.status_code == 409 and err(r) == "metricas_indisponiveis"


# ---- desfazer ----

def test_desfazer_volta_o_estado_bloqueia_o_automatico_e_refaz_pelo_post(m):  # noqa: F811
    d = m.rascunho(legenda=LEGENDA)
    pid = m.post()
    m.coletar(_agora() + timedelta(hours=2))
    assert m.destino(d["id"]).estado == DestinoEstado.publicado
    r = m.desfazer(d)
    assert r.status_code == 200, r.text
    assert r.json()["destino"]["estado"] == "rascunho_criado"
    assert r.json()["vinculo"]["bloqueado"] is True
    v = m.video_de(pid)
    assert (v.destino_id, v.vinculo_metodo, v.vinculado_por, v.vinculado_em) == \
        (None, None, None, None)
    assert v.vinculo_automatico is False
    assert m.busca(d["id"]).fim == "desfeito"
    ultima = m.versoes(d["id"])[-1]
    assert ultima.details == {"acao": "vinculo_desfeito", "metodo_anterior": "casamento"}
    assert ultima.actor_user_id == m.dono.id
    _sem_ids_da_rede(m.versoes(d["id"]), pid)
    # Não volta sozinho, nem com outro vídeo compatível.
    m.post(minutos=2)
    m.coletar(_agora() + timedelta(hours=4))
    assert m.db.scalar(select(VideoRede).where(
        VideoRede.destino_id == uuid.UUID(d["id"]))) is None
    # Refazer é o mesmo POST.
    r = m.ligar(d, videoId=str(v.id))
    assert r.status_code == 200 and r.json()["destino"]["estado"] == "publicado"
    r = m.desfazer(d)
    assert r.status_code == 200
    r = m.desfazer(d)
    assert r.status_code == 409 and err(r) == "sem_vinculo"


def test_desfazer_nao_volta_publicado_da_015_nem_postado_do_lembrete(m):  # noqa: F811
    destino = destino_auto(m.db, m.perfil["id"], m.conta["id"], m.dono, estado="publicado",
                           modo="publicar", rede_post_id=POST_ID, planned_at=_agora())
    m.post(POST_ID, legenda=OUTRA)
    m.coletar(_agora() + timedelta(hours=2))
    r = m.desfazer({"id": str(destino.id)})
    assert r.status_code == 200 and r.json()["destino"]["estado"] == "publicado"

    d = m.postado(m.lembrete())
    m.post(minutos=10)
    m.coletar(_agora() + timedelta(hours=3, minutes=5))
    assert m.vinculo(d["id"])["estado"] == "vinculado"
    r = m.desfazer(d)
    assert r.status_code == 200 and r.json()["destino"]["estado"] == "postado"
    # O lembrete fica bloqueado pelo `vinculo_desfeito` no histórico.
    m.coletar(_agora() + timedelta(hours=3, minutes=20))
    assert m.vinculo(d["id"])["estado"] != "vinculado"
    assert m.vinculo(d["id"])["bloqueado"] is True


def test_publicacao_pelo_vinculo_so_com_video_da_mesma_conta(m):  # noqa: F811
    from sociman_api.errors import ApiError
    from sociman_api.postagem.service import publicacao_pelo_vinculo

    d = m.rascunho(legenda=OUTRA)
    destino = m.destino(d["id"])
    with pytest.raises(ApiError):
        publicacao_pelo_vinculo(m.db, vinculos.AUTOR, destino, True,
                                conta_do_video=uuid.uuid4(), metodo="casamento")
    m.db.rollback()
    assert m.destino(d["id"]).estado == DestinoEstado.rascunho_criado


# ---- permissões ----

def test_membro_e_mcp_nao_ligam_nem_desfazem(m, membro):  # noqa: F811
    d = m.lembrete()
    pid = m.post(minutos=5)
    m.coletar(_agora() + timedelta(hours=1, minutes=5))
    vid = str(m.video_de(pid).id)
    assert m.client.get(f"/api/destinos/{d['id']}/vinculo", headers=membro[1]).status_code \
        == 200
    r = m.ligar(d, h=membro[1], videoId=vid)
    assert r.status_code == 403 and err(r) == "somente_dono"
    app.dependency_overrides[current_user] = lambda: Actor(kind="mcp_client",
                                                           user_id=m.dono.id, user=m.dono)
    r = m.ligar(d, videoId=vid)
    assert r.status_code == 403 and err(r) == "somente_humano"
    r = m.desfazer(d)
    assert r.status_code == 403 and err(r) == "somente_humano"
    del app.dependency_overrides[current_user]
    assert m.video_de(pid).destino_id is None
    assert m.destino(d["id"]).estado == DestinoEstado.aprovado
    assert m.db.execute(text("SELECT count(*) FROM security_events WHERE type = "
                             "'publicacao_recusada'")).scalar() >= 2
