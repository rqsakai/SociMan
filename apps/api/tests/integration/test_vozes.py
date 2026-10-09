"""Vozes do perfil (spec 025, T026, US2 e US3): criar, consentimento antes da gravação, os
candidatos e o status pelo gancho, escolher, trocar a referência, testar, voz padrão do avatar,
nome único e reverter."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from fakes.shoptts_fake import wav_sintetico

from integration.geracao_helpers import _buckets, motores, owner  # noqa: F401 (fixtures)
from integration.padrao_helpers import (
    avatar,
    consentimento,
    enviar_audio,
    escolher_opcao,
    geracao,
    pedir,
    perfil,
    rodar_gpu,
    ver,
    ver_voz,
    voz,
)


def _gravacao_pronta(client, h, pid) -> dict:
    v = voz(client, h, pid)
    audio = enviar_audio(client, h, pid, wav_sintetico(20.0))
    r = client.patch(f"/api/vozes/{v['id']}", headers=h,
                     json={"version": v["version"], "gravacaoAudioId": audio["id"]})
    assert r.status_code == 200, r.text
    v = r.json()
    return consentimento(client, h, v["id"], v["version"], rota="vozes")


def _aprovada(client, h, motores, pid) -> tuple[dict, dict]:
    v = _gravacao_pronta(client, h, pid)
    g = pedir(client, h, pid, v["id"], "voz.gravacao", alvo_tipo="voz")
    rodar_gpu(motores)
    escolher_opcao(client, h, g["id"], 2, ver_voz(client, h, v["id"])["version"])
    return ver_voz(client, h, v["id"]), g


def test_gravacao_exige_consentimento_e_gera_candidatos(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    v = voz(client, h, pid)
    assert v["status"] == "rascunho" and v["ttsId"].startswith("v_")
    erro = pedir(client, h, pid, v["id"], "voz.gravacao", alvo_tipo="voz", status=400)
    assert erro["error"]["details"]["field"] == "gravacaoAudioId"
    audio = enviar_audio(client, h, pid, wav_sintetico(20.0))
    v = client.patch(f"/api/vozes/{v['id']}", headers=h,
                     json={"version": v["version"], "gravacaoAudioId": audio["id"]}).json()
    erro = pedir(client, h, pid, v["id"], "voz.gravacao", alvo_tipo="voz", status=400)
    assert erro["error"]["code"] == "consentimento_ausente"
    v = consentimento(client, h, v["id"], v["version"], rota="vozes")
    assert v["consentimento"]["nome"] == "Ana Souza"
    assert v["consentimento"]["registradoPor"]["id"] == str(owner[0].id)
    g = pedir(client, h, pid, v["id"], "voz.gravacao", alvo_tipo="voz")
    assert ver_voz(client, h, v["id"])["status"] == "gerando"
    rodar_gpu(motores)
    v = ver_voz(client, h, v["id"])
    assert v["status"] == "revisao"
    g = geracao(client, h, g["id"])
    assert len(g["candidatos"]) == 3
    c = g["candidatos"][0]
    assert c["audio"] and c["testeAudio"] and c["metricas"]["transcricao"]
    # O shop-tts recebeu a gravação original com o `tts_id`, e a análise ficou na voz.
    register = next(p for p in motores.tts.requests if p.caminho == "/v2/voices/register")
    assert register.corpo["nome"] == v["ttsId"]
    assert v["analise"]["snrDb"] == 36.5 and v["analise"]["duracaoS"] == 21.4


def test_escolher_aprova_e_falha_volta_ao_anterior(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    v, _g = _aprovada(client, h, motores, pid)
    assert v["status"] == "aprovada" and v["referencia"] and v["refTexto"]
    assert v["sincronizacao"] == "pendente" and v["sincronizadaEm"] is None
    # Trocar a referência: a anterior continua valendo até a escolha.
    ref_antes = v["referencia"]["id"]
    g2 = pedir(client, h, pid, v["id"], "voz.gravacao", alvo_tipo="voz")
    v = ver_voz(client, h, v["id"])
    assert v["status"] == "gerando" and v["trocandoReferencia"] is True
    assert v["referencia"]["id"] == ref_antes
    # Cancelada sem outra aberta: volta a aprovada (tem referência).
    r = client.post(f"/api/geracoes/{g2['id']}/cancelar", headers=h,
                    json={"version": geracao(client, h, g2["id"])["version"]})
    assert r.status_code == 200
    v = ver_voz(client, h, v["id"])
    assert v["status"] == "aprovada" and v["referencia"]["id"] == ref_antes


def test_gerar_outras_mantem_gerando(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    v = _gravacao_pronta(client, h, pid)
    g = pedir(client, h, pid, v["id"], "voz.gravacao", alvo_tipo="voz")
    rodar_gpu(motores)
    r = client.post(f"/api/geracoes/{g['id']}/gerar-outras", headers=h,
                    json={"version": geracao(client, h, g["id"])["version"]})
    assert r.status_code == 201, r.text
    assert ver_voz(client, h, v["id"])["status"] == "gerando"


def test_sintetica_e_teste(client, owner, motores):
    from datetime import UTC, datetime

    from sqlalchemy import text

    from sociman_api.db import get_engine

    h = owner[1]
    pid = perfil(client, h)
    erro = voz(client, h, pid, origem="sintetica", status=400,
               descricao="a teen girl voice")
    assert erro["error"]["code"] == "menor_proibido"
    v = voz(client, h, pid, origem="sintetica", name="Sintética")
    g = pedir(client, h, pid, v["id"], "voz.design", alvo_tipo="voz")
    rodar_gpu(motores)
    escolher_opcao(client, h, g["id"], 1, ver_voz(client, h, v["id"])["version"])
    v = ver_voz(client, h, v["id"])
    assert v["status"] == "aprovada"
    erro = pedir(client, h, pid, v["id"], "voz.teste", alvo_tipo="voz", status=409,
                 texto="Olha que achadinho!")
    assert erro["error"]["code"] == "voz_nao_sincronizada"
    with get_engine().begin() as conn:  # a linha `vozes_sync` sincronizou
        conn.execute(text("UPDATE vozes SET sincronizada_em = :t WHERE id = :i"),
                     {"t": datetime.now(UTC), "i": v["id"]})
    motores.tts.vozes[v["ttsId"]] = {"file": "x", "text": "x"}
    t = pedir(client, h, pid, v["id"], "voz.teste", alvo_tipo="voz", texto="Olha que achadinho!")
    versao = ver_voz(client, h, v["id"])["version"]
    rodar_gpu(motores)
    t = geracao(client, h, t["id"])
    assert t["status"] == "entregue" and t["candidatos"][0]["audio"]
    assert ver_voz(client, h, v["id"])["version"] == versao  # o teste não versiona a voz
    assert ver_voz(client, h, v["id"])["ultimoTeste"]["id"] == t["id"]


def test_voz_padrao_e_usada_por(client, owner, motores):
    h = owner[1]
    pid = perfil(client, h)
    v, _ = _aprovada(client, h, motores, pid)
    a = avatar(client, h, pid)
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "vozId": v["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["asset"]["vozPadrao"]["id"] == v["id"]
    assert ver_voz(client, h, v["id"])["usadaPor"] == [{"id": a["id"], "name": "Ana"}]
    # Voz de outro perfil ou sem referência → 400 voz_invalida.
    outra = voz(client, h, perfil(client, h, slug="outro"), name="Outra")
    a = ver(client, h, a["id"])
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "vozId": outra["id"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "voz_invalida"
    # Arquivar a voz não é bloqueado; o avatar mostra "arquivada".
    v = ver_voz(client, h, v["id"])
    r = client.post(f"/api/vozes/{v['id']}/archive", headers=h, json={"version": v["version"]})
    assert r.status_code == 200
    assert ver(client, h, a["id"])["vozPadrao"]["arquivada"] is True


def test_nome_unico_entre_as_ativas(client, owner):
    h = owner[1]
    pid = perfil(client, h)
    v = voz(client, h, pid)
    erro = voz(client, h, pid, name="ana VENDAS", status=409)
    assert erro["error"]["code"] == "voz_nome_em_uso"
    r = client.post(f"/api/vozes/{v['id']}/archive", headers=h, json={"version": v["version"]})
    assert r.status_code == 200
    voz(client, h, pid, name="Ana vendas")  # arquivada libera o nome
    r = client.post(f"/api/vozes/{v['id']}/restore", headers=h,
                    json={"version": r.json()["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "voz_nome_em_uso"


def test_reverter_so_dono(client, owner, make_user, login, motores):
    h = owner[1]
    pid = perfil(client, h)
    v = voz(client, h, pid)
    r = client.patch(f"/api/vozes/{v['id']}", headers=h,
                     json={"version": v["version"], "tom": "calma"})
    v = r.json()
    membro = make_user(role="membro", name="Membro")
    hm = login(client, membro.email, "senha-forte-123")
    r = client.post(f"/api/vozes/{v['id']}/revert", headers=hm,
                    json={"version": v["version"], "toVersion": 1})
    assert r.status_code == 403
    r = client.post(f"/api/vozes/{v['id']}/revert", headers=h,
                    json={"version": v["version"], "toVersion": 1})
    assert r.status_code == 200 and r.json()["tom"] == "vendas animada"


# ---- spec 029 (T028a): voz, gravação e prova de qualquer perfil base ----

def test_voz_de_outro_perfil_como_padrao_e_gravacao_de_outro_perfil(client, owner, motores):
    h = owner[1]
    pa, pb = perfil(client, h, slug="perfil-a"), perfil(client, h, slug="perfil-b")
    v, _ = _aprovada(client, h, motores, pb)
    a = avatar(client, h, pa)
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "vozId": v["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["asset"]["vozPadrao"]["id"] == v["id"]
    # A gravação de uma voz pode ser um áudio enviado em outro perfil.
    outra = voz(client, h, pa, name="Outra")
    audio = enviar_audio(client, h, pb, wav_sintetico(20.0))
    r = client.patch(f"/api/vozes/{outra['id']}", headers=h,
                     json={"version": outra["version"], "gravacaoAudioId": audio["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["gravacao"]["id"] == audio["id"]
    # A prova do consentimento também pode vir de outro perfil.
    prova = enviar_audio(client, h, pb, wav_sintetico(5.0), nome="termo.wav")
    v2 = consentimento(client, h, outra["id"], r.json()["version"], rota="vozes",
                       prova={"audioId": prova["id"]})
    assert v2["consentimento"]["temProva"] is True
