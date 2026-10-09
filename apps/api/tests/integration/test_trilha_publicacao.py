"""Trilha `publicacao` (spec 015, T041 e T061; research R6 a R11): rascunho de ponta a ponta na
TikTok falsa, partes, falhas traduzidas, limites, decisão humana, interruptor e vencidos."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from integration import publicacao_helpers as ph
from integration.conexao_helpers import conectar, destino_auto
from integration.postagem_helpers import criar_conta, criar_corte, criar_perfil
from integration.publicacao_helpers import ligar_botao, video
from sociman_api import storage
from sociman_api.auth.models import SecurityEvent
from sociman_api.cortes.models import Corte
from sociman_api.db import get_engine
from sociman_api.history import EntityVersion
from sociman_api.notificacoes.models import Notificacao
from sociman_api.postagem.models import DestinoEstado, Postagem
from sociman_api.publicacao import limites, trilha
from sociman_api.publicacao.models import Tentativa, TentativaFase

# Fixtures do apoio (o pytest as acha pelo nome no módulo).
app_tiktok = ph.app_tiktok
cena = ph.cena


def _sql(sql: str, **params) -> None:
    with get_engine().begin() as conn:
        conn.execute(text(sql), params)


def _notificacoes(db, tipo: str) -> list[Notificacao]:
    db.expire_all()
    return list(db.scalars(select(Notificacao).where(Notificacao.tipo == tipo)))


def _efetivo(cena, destino_id) -> str:
    r = cena.client.get(f"/api/destinos/{destino_id}", headers=cena.h)
    assert r.status_code == 200, r.text
    return r.json()["destino"]["estadoEfetivo"]


def _partes_pequenas(monkeypatch) -> None:
    """Partes de 1 KB (a regra de R9 com números pequenos)."""
    monkeypatch.setattr(trilha, "CHUNK", 1024)
    monkeypatch.setattr(trilha, "INTEIRO_ATE", 1024)


# ---- partes (R9) ----

def test_partes_16mb_e_arquivo_pequeno_inteiro():
    mb = 1024 * 1024
    # até 64 MB vai inteiro: com 1 parte a TikTok exige chunk_size == video_size
    # (o sandbox recusou 21,5 MB declarados como chunk de 16 MB com `invalid_params`, 2026-09-29)
    assert trilha.partes(5 * mb - 1) == (5 * mb - 1, 1)
    assert trilha.partes(22_540_575) == (22_540_575, 1)
    assert trilha.partes(64 * mb) == (64 * mb, 1)
    # acima de 64 MB: partes de 16 MB, total = floor(tamanho / 16 MB), a última absorve o resto
    assert trilha.partes(100 * mb) == (16 * mb, 6)
    t = Tentativa(chunk_size=16 * mb, total_partes=6, video_bytes=100 * mb)
    assert trilha.faixa(t, 0) == (0, 16 * mb)
    assert trilha.faixa(t, 5) == (80 * mb, 20 * mb)  # a última absorve o resto (< 32 MB)


# ---- rascunho de ponta a ponta ----

def test_rascunho_de_ponta_a_ponta(cena):
    corte = cena.corte()
    dados = storage.get(corte.result_key, bucket="videos")
    d = cena.agendar(corte).json()["destino"]
    cena.fake.requests.clear()

    cena.rodar()  # reivindica, init, parte única, processando
    t = cena.tentativas(d["id"])[0]
    assert cena.destino(d["id"]).estado == DestinoEstado.enviando
    assert t.fase == TentativaFase.processando and t.publish_id
    assert t.init_enviado_em is not None and t.upload_url_cifrado is None
    assert t.partes_enviadas == t.total_partes == 1 and t.chunk_size == len(dados)
    assert t.video_sha256 == hashlib.sha256(dados).hexdigest()
    assert t.disparo == "agendador" and t.video_ref == corte.result_key
    init = cena.fake.pedidos("inbox_init")
    assert len(init) == 1 and init[0]["post_info"] is None  # inbox nunca leva textos
    assert init[0]["source_info"] == {"source": "FILE_UPLOAD", "video_size": len(dados),
                                      "chunk_size": len(dados), "total_chunk_count": 1}
    assert cena.fake.pedidos("put") == [{"content_range": f"bytes 0-{len(dados) - 1}/"
                                                          f"{len(dados)}"}]

    cena.rodar(3)  # PROCESSING_UPLOAD, PROCESSING_UPLOAD, SEND_TO_USER_INBOX
    destino = cena.destino(d["id"])
    t = cena.tentativas(d["id"])[0]
    assert destino.estado == DestinoEstado.rascunho_criado
    assert t.fase == TentativaFase.entregue and t.status_rede == "SEND_TO_USER_INBOX"
    assert t.concluida_em is not None
    notif = _notificacoes(cena.db, "rascunho_criado")
    assert [n.user_id for n in notif] == [cena.dono.id]
    assert notif[0].dedupe_key == f"rascunho_criado:{t.id}"
    auto = [v for v in cena.versoes(d["id"]) if v.actor_kind == "system:publicacao"]
    assert [v.details["acao"] for v in auto] == ["envio_iniciado", "rascunho_criado"]
    assert all(v.details["tentativaId"] == str(t.id) for v in auto)

    r = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    assert r["estadoEfetivo"] == "rascunho_criado"
    assert r["ultimaTentativa"]["fase"] == "entregue"
    assert r["conta"]["conexao"] == "conectada"
    assert r["agendadoPor"]["id"] == str(cena.dono.id)

    # Final: mais voltas não mudam nada nem chamam de novo.
    cena.rodar(2)
    assert cena.fake.inits == 1
    assert cena.tentativas(d["id"])[0].concluida_em == t.concluida_em


def test_varias_partes_com_content_range(cena, monkeypatch):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=3500)
    cena.fake.requests.clear()
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert (t.chunk_size, t.total_partes, t.partes_enviadas) == (1024, 3, 3)
    assert [p["content_range"] for p in cena.fake.pedidos("put")] == [
        "bytes 0-1023/3500", "bytes 1024-2047/3500", "bytes 2048-3499/3500"]
    assert cena.fake.pedidos("inbox_init")[0]["source_info"]["total_chunk_count"] == 3


def test_parte_com_5xx_tenta_de_novo_sem_duplicar(cena, monkeypatch):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=2048)
    cena.fake.falhar_proximo("put", "5xx")
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    assert cena.fake.inits == 1
    assert len(cena.fake.pedidos("put")) == 3  # a parte 1 duas vezes


def test_parte_sempre_fora_espera_a_proxima_volta(cena, monkeypatch):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=2048)
    cena.fake.falhar_sempre["put"] = "5xx"
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.enviando_partes and t.partes_enviadas == 0
    del cena.fake.falhar_sempre["put"]
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    assert cena.fake.inits == 1


# ---- falhas traduzidas (R19) ----

def test_init_recusado_vira_falhou_com_motivo(cena):
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "spam_risk_user_banned_from_posting")
    cena.rodar()
    destino = cena.destino(d["id"])
    t = cena.tentativas(d["id"])[0]
    assert destino.estado == DestinoEstado.falhou and not destino.falha_incerta
    assert destino.falha_motivo == "A TikTok bloqueou postagens desta conta"
    assert t.fase == TentativaFase.recusada
    assert t.codigo_rede == "spam_risk_user_banned_from_posting"
    assert t.details["acao"] == "verificar_app"
    assert len(_notificacoes(cena.db, "envio_rede_falhou")) == 1
    r = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    assert r["estadoEfetivo"] == "falhou" and r["falhaMotivo"] == destino.falha_motivo
    assert r["ultimaTentativa"]["acao"] == "verificar_app"


def test_fail_reason_do_status(cena):
    d = cena.agendado()
    cena.fake.fail_reason_proximo = "duration_check_failed"
    cena.rodar(2)
    destino = cena.destino(d["id"])
    assert destino.estado == DestinoEstado.falhou
    assert "duração" in destino.falha_motivo
    assert cena.tentativas(d["id"])[0].codigo_rede == "duration_check_failed"


def test_codigo_desconhecido_tem_fallback(cena):
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "codigo_novo_da_tiktok")
    cena.rodar()
    assert cena.destino(d["id"]).falha_motivo == \
        "A TikTok recusou o envio (código codigo_novo_da_tiktok)"


# ---- limites (R10) ----

def test_sexto_rascunho_espera_vaga(cena):
    ds = [cena.agendado(ignorarIntervalo=True) for _ in range(6)]
    cena.rodar()  # reivindica 5 (LOTE)
    cena.rodar()  # o 6º: sem vaga local
    sexto = ds[-1]
    t = cena.tentativas(sexto["id"])[0]
    assert t.fase == TentativaFase.sem_vaga and t.init_enviado_em is None
    primeiro = min(x.init_enviado_em for d in ds[:5] for x in cena.tentativas(d["id"]))
    assert t.proxima_em == primeiro + timedelta(hours=24)
    assert cena.destino(sexto["id"]).estado == DestinoEstado.agendado
    assert _efetivo(cena, sexto["id"]) == "aguardando_vaga"
    assert cena.fake.inits == 5
    cena.rodar(2)  # não reivindica de novo enquanto espera, e avisa uma vez
    assert cena.fake.inits == 5 and len(cena.tentativas(sexto["id"])) == 1
    assert len(_notificacoes(cena.db, "envio_aguardando_vaga")) == 1
    acoes = [v.details.get("acao") for v in cena.versoes(sexto["id"])]
    assert acoes[-2:] == ["envio_iniciado", "envio_devolvido"]


def test_incerta_e_abertas_contam_recusada_nao(cena, db):
    agora = datetime.now(UTC)
    conexao_id = db.execute(text("SELECT id FROM conexoes")).scalar()
    ocupadas, _ = limites.vagas_rascunho(db, conexao_id, agora)
    assert ocupadas == 0
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "timeout")  # incerta
    cena.rodar()
    d2 = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "invalid_params")  # recusada
    cena.rodar()
    assert cena.tentativas(d["id"])[0].fase == TentativaFase.incerta
    assert cena.tentativas(d2["id"])[0].fase == TentativaFase.recusada
    assert limites.vagas_rascunho(db, conexao_id, datetime.now(UTC))[0] == 1


def test_spam_risk_pending_share_espera_1h(cena):
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "spam_risk_too_many_pending_share")
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.sem_vaga
    assert timedelta(minutes=59) < t.proxima_em - datetime.now(UTC) <= timedelta(hours=1)
    assert cena.destino(d["id"]).estado == DestinoEstado.agendado
    assert _efetivo(cena, d["id"]) == "aguardando_vaga"
    cena.rodar()
    assert cena.fake.inits == 1


def test_taxa_local_estourada_adia_sem_chamar(cena, monkeypatch):
    d = cena.agendado()
    monkeypatch.setitem(limites.TAXAS, "init", 0)
    cena.fake.requests.clear()
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.iniciando and t.init_enviado_em is None
    assert t.proxima_em is not None and cena.fake.inits == 0
    monkeypatch.setitem(limites.TAXAS, "init", 5)
    monkeypatch.setattr(trilha, "ADIAR", timedelta(0))
    _sql("UPDATE publicacao_tentativas SET proxima_em = now()")
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    assert cena.fake.inits == 1


def test_rate_limit_da_rede_adia_e_nao_gasta_a_tentativa(cena):
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "rate_limit_exceeded")
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.iniciando and t.init_enviado_em is None
    assert t.details["adiadoPor"] == "rate_limit_exceeded"
    _sql("UPDATE publicacao_tentativas SET proxima_em = now()")
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    assert len(cena.tentativas(d["id"])) == 1


# ---- conexão ----

def test_conta_nao_conectada_nao_e_reivindicada(cena):
    d = cena.agendado()
    _sql("UPDATE conexoes SET estado = 'precisa_reconectar'")
    cena.fake.requests.clear()
    cena.rodar()
    assert cena.fake.requests == [] and cena.tentativas(d["id"]) == []
    r = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    assert r["estadoEfetivo"] == "atencao"
    assert r["motivoAtencao"] == "Conta precisa reconectar"


def test_conexao_perdida_antes_do_init_devolve(cena, monkeypatch):
    d = cena.agendado()
    monkeypatch.setitem(limites.TAXAS, "init", 0)
    cena.rodar()  # tentativa iniciando, sem init
    monkeypatch.setitem(limites.TAXAS, "init", 5)
    _sql("UPDATE conexoes SET estado = 'precisa_reconectar'")
    _sql("UPDATE publicacao_tentativas SET proxima_em = now()")
    cena.fake.requests.clear()
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert cena.fake.requests == [] and t.init_enviado_em is None
    assert t.fase == TentativaFase.recusada and t.codigo_rede == "conta_nao_conectada"
    assert cena.destino(d["id"]).estado == DestinoEstado.agendado
    assert cena.versoes(d["id"])[-1].details["acao"] == "envio_devolvido"


# ---- vídeo ----

def test_video_mudou_no_meio_recusa(cena, monkeypatch):
    _partes_pequenas(monkeypatch)
    corte = cena.corte(tamanho=3000)
    d = cena.agendar(corte).json()["destino"]
    original = trilha._ler

    def ler_e_trocar(key, inicio, tamanho):
        dados = original(key, inicio, tamanho)
        storage.put(key, b"outro video" * 300, "video/mp4", bucket="videos")
        return dados

    monkeypatch.setattr(trilha, "_ler", ler_e_trocar)
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.recusada and t.codigo_rede == "video_mudou"
    assert t.partes_enviadas == 1
    assert cena.destino(d["id"]).falha_motivo == "O vídeo mudou durante o envio; tente de novo"


def test_video_ausente_recusa_sem_chamar(cena):
    corte = criar_corte(cena.db, cena.perfil["id"])  # sem o arquivo no MinIO
    d = cena.agendar(corte).json()["destino"]
    cena.fake.requests.clear()
    cena.rodar()
    assert cena.fake.inits == 0
    assert cena.tentativas(d["id"])[0].codigo_rede == "video_indisponivel"
    assert cena.destino(d["id"]).estado == DestinoEstado.falhou


def test_status_sem_final_em_2h_vira_incerta(cena):
    d = cena.agendado()
    cena.fake.passos_status = 1000
    cena.rodar(2)
    velho = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    _sql("UPDATE publicacao_tentativas SET details = jsonb_set(details, "
         "'{uploadConcluidoEm}', to_jsonb(CAST(:v AS text)))", v=velho)
    cena.rodar()
    destino = cena.destino(d["id"])
    assert destino.estado == DestinoEstado.falhou and destino.falha_incerta
    assert cena.tentativas(d["id"])[0].fase == TentativaFase.incerta


# ---- decisão humana (R15) ----

def test_agendamento_sem_decisao_humana_e_recusado(cena, db):
    conexao_conta = uuid.UUID(cena.conta["id"])
    destino = destino_auto(db, cena.perfil["id"], conexao_conta, cena.dono,
                           planned_at=datetime.now(UTC))
    video(db, db.get(Corte, destino.conteudo_id))
    # Uma versão de agendamento gravada por um ator de sistema (não humano).
    db.add(EntityVersion(entity_type="postagem", entity_id=destino.id, version=1,
                         action="updated", actor_kind="system:cli", after={},
                         changed_fields=[], details={"acao": "agendado"}))
    db.commit()
    cena.fake.requests.clear()
    cena.rodar()
    t = cena.tentativas(destino.id)[0]
    assert cena.fake.inits == 0
    assert t.fase == TentativaFase.recusada and t.codigo_rede == "sem_decisao_humana"
    assert cena.destino(destino.id).estado == DestinoEstado.falhou
    evento = db.scalars(select(SecurityEvent).where(
        SecurityEvent.type == "publicacao_recusada")).one()
    assert evento.details["destinoId"] == str(destino.id)
    assert evento.details["actorKind"] == "system:cli"


def test_duas_contas_no_mesmo_horario_sao_independentes(cena):
    perfil = criar_perfil(cena.client, cena.h, "Meus Queridinhos")
    outra = criar_conta(cena.client, cena.h, perfil["id"], "tiktok", "meusqueridinhos10")
    conectar(cena.client, cena.h, outra, cena.fake)
    corte_b = criar_corte(cena.db, perfil["id"])
    video(cena.db, corte_b)
    agora = datetime.now(UTC)
    a = cena.agendar(cena.corte(), agora).json()["destino"]
    b = cena.agendar(corte_b, agora, conta=outra).json()["destino"]
    cena.rodar(4)
    assert cena.destino(a["id"]).estado == DestinoEstado.rascunho_criado
    assert cena.destino(b["id"]).estado == DestinoEstado.rascunho_criado
    assert cena.fake.inits == 2
    assert {cena.tentativas(a["id"])[0].conexao_id} != {cena.tentativas(b["id"])[0].conexao_id}


# ---- interruptor e vencidos (T061, R11) ----

def test_servidor_desligado_nada_sai(cena, publicacao_habilitada):
    d = cena.agendado()
    publicacao_habilitada(False)
    cena.fake.requests.clear()
    antes = (cena.destino(d["id"]).version, cena.destino(d["id"]).estado)
    assert trilha.rodar(cena.db, client=cena.fake.client()) == 0
    assert cena.fake.requests == [] and cena.tentativas(d["id"]) == []
    assert (cena.destino(d["id"]).version, cena.destino(d["id"]).estado) == antes
    assert _efetivo(cena, d["id"]) == "pausado"


def test_botao_desligado_nada_sai(cena):
    d = cena.agendado()
    ligar_botao(False)
    cena.fake.requests.clear()
    cena.rodar(2)
    assert cena.fake.requests == [] and cena.tentativas(d["id"]) == []
    assert _efetivo(cena, d["id"]) == "pausado"
    ligar_botao(True)
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado


def _desligar_depois_da_primeira_parte(monkeypatch):
    original = trilha._ler
    chamadas = []

    def ler(key, inicio, tamanho):
        chamadas.append(inicio)
        if len(chamadas) == 2:  # a 2ª parte já foi lida; a próxima checagem para
            ligar_botao(False)
        return original(key, inicio, tamanho)

    monkeypatch.setattr(trilha, "_ler", ler)


def test_desligar_no_meio_para_os_puts_e_religar_retoma(cena, monkeypatch):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=4000)
    _desligar_depois_da_primeira_parte(monkeypatch)
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.enviando_partes and t.partes_enviadas == 2
    puts = len(cena.fake.pedidos("put"))
    cena.rodar(2)  # desligado: nenhum PUT a mais
    assert len(cena.fake.pedidos("put")) == puts
    assert cena.destino(d["id"]).estado == DestinoEstado.enviando
    assert _efetivo(cena, d["id"]) == "pausado"
    ligar_botao(True)
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    assert cena.fake.inits == 1 and len(cena.fake.pedidos("put")) == 3


def test_religar_com_o_link_vencido_recusa(cena, monkeypatch):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=4000)
    _desligar_depois_da_primeira_parte(monkeypatch)
    cena.rodar()
    _sql("UPDATE publicacao_tentativas SET upload_url_expira_em = now() - interval '1 minute'")
    ligar_botao(True)
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.recusada and t.upload_url_cifrado is None
    assert "interruptor" in t.motivo
    assert cena.destino(d["id"]).estado == DestinoEstado.falhou
    assert not cena.destino(d["id"]).falha_incerta
    assert cena.fake.inits == 1


def test_botao_desligado_ainda_consulta_o_status(cena):
    d = cena.agendado()
    cena.rodar()  # upload completo, processando
    ligar_botao(False)
    cena.rodar(3)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado


def test_vencido_so_sai_com_confirmar_envio(cena):
    d = cena.agendado()
    ligar_botao(False)
    _sql("UPDATE postagens SET planned_at = now() - interval '2 hours' WHERE id = :id",
         id=d["id"])
    ligar_botao(True)
    cena.fake.requests.clear()
    cena.rodar()
    assert cena.fake.requests == [] and cena.tentativas(d["id"]) == []
    atual = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    assert atual["estadoEfetivo"] == "vencido"
    r = cena.client.post(f"/api/destinos/{d['id']}/confirmar-envio", headers=cena.h,
                         json={"version": atual["version"]})
    assert r.status_code == 200, r.text
    cena.rodar(4)
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    t = cena.tentativas(d["id"])[0]
    assert t.disparo == "confirmado" and t.disparado_por == cena.dono.id


def test_vencido_aparece_no_atalho(cena):
    d = cena.agendado()
    _sql("UPDATE postagens SET planned_at = now() - interval '2 hours' WHERE id = :id",
         id=d["id"])
    r = cena.client.get("/api/conteudos", headers=cena.h, params={"atalho": "vencidos"})
    assert r.status_code == 200, r.text
    assert [c["id"] for c in r.json()["items"]] == [d["conteudoId"]]


def test_tentar_de_novo_depois_de_falhar(cena):
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "invalid_params")
    cena.rodar()
    atual = cena.client.get(f"/api/destinos/{d['id']}", headers=cena.h).json()["destino"]
    r = cena.client.post(f"/api/destinos/{d['id']}/tentar-de-novo", headers=cena.h,
                         json={"version": atual["version"]})
    assert r.status_code == 200, r.text
    cena.rodar(4)
    ts = cena.tentativas(d["id"])
    assert [t.numero for t in ts] == [1, 2]
    assert ts[1].disparo == "tentar_de_novo" and ts[1].disparado_por == cena.dono.id
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado


def test_nenhum_destino_de_lembrete_e_tocado(cena, db):
    r = cena.agendar(cena.corte(), modo="lembrete")
    assert r.status_code == 201, r.text
    cena.fake.requests.clear()
    cena.rodar()
    assert cena.fake.requests == []
    assert db.scalar(select(Postagem.estado)) == DestinoEstado.agendado
