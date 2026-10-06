"""Trilha `openshorts` do agendador com o OpenShorts falso (T047; R6, US3-5, SC-003)."""

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from functools import partial

import pytest
from fakes import openshorts_fake as _osf
from sqlalchemy import select

from integration import envios_helpers
from integration.envios_helpers import (
    criar_canal,
    criar_video,
    enviado,
    envio_row,
)
from sociman_api import storage
from sociman_api.agendador import Agendador, Trilha
from sociman_api.canais.models import CanalDireito
from sociman_api.db import get_engine, get_sessionmaker
from sociman_api.envios import acompanhamento
from sociman_api.envios.models import DireitoEnvio, Envio, EnvioOrigem, EnvioStatus
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo

# Fixtures compartilhadas (atribuídas, e não importadas, para o ruff não acusar F811).
_buckets = envios_helpers._buckets
member = envios_helpers.member
owner = envios_helpers.owner
perfil = envios_helpers.perfil
openshorts_clip = _osf.openshorts_clip
openshorts_fake = _osf.openshorts_fake

class Relogio:
    """`acompanhamento._agora` controlável (o backoff usa o relógio da trilha)."""

    def __init__(self, monkeypatch):
        self.t = datetime.now(UTC)
        monkeypatch.setattr(acompanhamento, "_agora", lambda: self.t)

    def avancar(self, segundos: float) -> None:
        self.t += timedelta(seconds=segundos)


@pytest.fixture
def relogio(monkeypatch) -> Relogio:
    return Relogio(monkeypatch)


def volta(db, fake) -> int:
    n = acompanhamento.rodar(db, client=fake.client())
    db.commit()
    return n


def _notificacoes(db, tipo: NotificacaoTipo) -> list[Notificacao]:
    db.expire_all()
    return list(db.scalars(select(Notificacao).where(Notificacao.tipo == tipo)))


@pytest.fixture
def envio(client, owner, perfil) -> dict:
    video = criar_video(criar_canal(CanalDireito.proprio))
    return enviado(client, owner[1], perfil["id"], video)


def test_submete_e_acompanha_ate_importando(client, owner, envio, db, openshorts_fake):
    fake = openshorts_fake
    assert volta(db, fake) == 1
    row = envio_row(db, envio["id"])
    assert row.status == EnvioStatus.processando and row.openshorts_job_id == fake.job().id
    (body,) = fake.processados
    assert body == {"url": row.source_url, "acknowledged": True, "auto_hook": False,
                    "captions": False, "layouts": ["auto"], "output_format": "vertical",
                    "clip_min_seconds": 15, "clip_max_seconds": 60}

    volta(db, fake)  # queued
    row = envio_row(db, envio["id"])
    assert row.status == EnvioStatus.processando and row.openshorts_queue_pos == 2
    r = client.get(f"/api/envios/{envio['id']}", headers=owner[1])
    assert r.json()["envio"]["queuePosition"] == 2

    volta(db, fake)  # processing: logs até o 1º clipe pronto de 3 (clipe 2 de 3)
    row = envio_row(db, envio["id"])
    assert row.openshorts_queue_pos is None and row.progress == 56
    assert (row.etapa, row.clipe_atual, row.clipes_previstos, row.etapa_mensagem) == (
        "processando_clipes", 2, 3, "Cortando clipe 2 de 3")
    assert row.started_at is not None

    volta(db, fake)  # completed
    row = envio_row(db, envio["id"])
    assert row.status == EnvioStatus.importando and row.clips_total == 3 and row.progress == 90
    assert volta(db, fake) == 0  # a trilha openshorts não mexe mais nele
    assert fake.pedidos().count(("POST", "/api/process")) == 1


def test_etapas_reais_em_sequencia(client, owner, envio, db, openshorts_fake):
    """O fake revela os logs de um job real um bloco por consulta; a API mostra cada etapa, o %
    geral só sobe e o sino avisa uma vez, quando os momentos são escolhidos."""
    fake = openshorts_fake
    fake.passos_processando = 6
    volta(db, fake)  # submete
    vistos = []
    for _ in range(1 + 6):  # queued + 6 blocos
        volta(db, fake)
        e = client.get(f"/api/envios/{envio['id']}", headers=owner[1]).json()["envio"]
        vistos.append((e["etapa"], e["etapaPct"], e["etapaMensagem"], e["progress"],
                       e["clipeAtual"], e["clipesPrevistos"]))
    assert vistos == [
        ("fila", None, "Na fila do SociShorts (2º)", 0, None, None),
        ("baixando", 100, "Vídeo baixado, preparando", 5, None, None),
        ("transcrevendo", 0, "Aguardando a vez de transcrever", 5, None, None),
        ("transcrevendo", 50, "Transcrevendo o vídeo 50%", 20, None, None),
        ("escolhendo_momentos", None, "Escolhendo os momentos", 38, None, None),
        ("processando_clipes", 0, "Cortando clipe 1 de 3 (cenas 41%)", 40, 1, 3),
        ("processando_clipes", 33, "Cortando clipe 2 de 3", 56, 2, 3),
    ]
    avisos = _notificacoes(db, NotificacaoTipo.envio_momentos)
    assert len(avisos) == 1 and avisos[0].corpo == "3 clipes em produção no SociShorts"
    assert avisos[0].titulo.startswith("Momentos escolhidos: ")

    volta(db, fake)  # completed
    e = client.get(f"/api/envios/{envio['id']}", headers=owner[1]).json()["envio"]
    assert (e["status"], e["etapa"], e["progress"], e["clipesPrevistos"]) == (
        "importando", "importando", 90, 3)
    assert len(_notificacoes(db, NotificacaoTipo.envio_momentos)) == 1


def test_progresso_tem_teto_de_90(client, owner, perfil, db, openshorts_fake):
    fake = openshorts_fake
    fake.passos_fila = 0
    fake.n_clipes = 1  # "Found 1 clips!" e o clipe 1 pronto: a geração inteira, ainda processing
    video = criar_video(criar_canal(CanalDireito.proprio))
    e = enviado(client, owner[1], perfil["id"], video, )
    volta(db, fake)
    volta(db, fake)
    assert envio_row(db, e["id"]).progress == 90


def test_avulso_por_arquivo_sobe_do_minio(client, owner, perfil, db, openshorts_fake):
    user, _ = owner
    envio_id = uuid.uuid4()
    key = f"envios/{envio_id}/fonte.mp4"
    storage.put(key, b"conteudo-do-video" * 1000, "video/mp4", bucket="videos")
    db.add(Envio(id=envio_id, perfil_id=uuid.UUID(perfil["id"]),
                 origem=EnvioOrigem.avulso_arquivo, source_title="Live", upload_key=key,
                 upload_bytes=17000, status=EnvioStatus.na_fila,
                 direito_no_envio=DireitoEnvio.avulso, sent_at=datetime.now(UTC),
                 config={"clip_min_s": 15, "clip_max_s": 60, "quantidade": 3, "layout": "none",
                         "formato": "square", "legenda": "nenhuma", "marca_automatica": False,
                         "kit_version": 0},
                 created_by=user.id, updated_by=user.id))
    db.commit()

    volta(db, openshorts_fake)
    (upload_id, conteudo), = openshorts_fake.uploads.items()
    assert conteudo == b"conteudo-do-video" * 1000
    (body,) = openshorts_fake.processados
    assert body["upload_id"] == upload_id and "url" not in body
    assert body["target_clips"] == 3 and body["captions"] is False
    assert envio_row(db, envio_id).status == EnvioStatus.processando
    # o PUT foi para o OpenShorts configurado, não para o upload_url devolvido
    put = [r for r in openshorts_fake.requests if r.method == "PUT"]
    assert put[0].url.host == "openshorts.test"


def test_needs_confirmation_espera_o_usuario(client, owner, envio, db, openshorts_fake):
    fake = openshorts_fake
    fake.needs_confirmation = True
    volta(db, fake)
    row = envio_row(db, envio["id"])
    assert row.status == EnvioStatus.confirmar_qualidade
    assert "360p" in row.error_message
    (n,) = [x for x in _notificacoes(db, NotificacaoTipo.envio_confirmar_qualidade)]
    assert n.link == f"/app/envios/{envio['id']}"

    volta(db, fake)  # nunca reenvia sozinho
    assert fake.pedidos().count(("POST", "/api/process")) == 1

    r = client.post(f"/api/envios/{envio['id']}/confirmar-qualidade", headers=owner[1],
                    json={"version": row.version, "enviar": True})
    assert r.status_code == 200, r.text
    volta(db, fake)
    assert envio_row(db, envio["id"]).status == EnvioStatus.processando
    assert fake.processados[-1]["force_low_quality"] is True


def test_429_volta_para_a_fila_com_60s(envio, db, openshorts_fake, relogio):
    fake = openshorts_fake
    fake.ocupado = 1
    volta(db, fake)
    row = envio_row(db, envio["id"])
    assert row.status == EnvioStatus.na_fila
    assert row.next_attempt_at == relogio.t + timedelta(seconds=60)
    relogio.avancar(59)
    assert volta(db, fake) == 0
    relogio.avancar(2)
    volta(db, fake)
    assert envio_row(db, envio["id"]).status == EnvioStatus.processando


def test_recusa_vira_falhou_traduzido_e_notifica(client, owner, member, perfil, db,
                                                openshorts_fake):
    video = criar_video(criar_canal(CanalDireito.proprio))
    e = enviado(client, member[1], perfil["id"], video)
    detail = "This video is only 30s long — clip generation needs at least 45s of material."
    openshorts_fake.recusar = (400, detail)
    volta(db, openshorts_fake)
    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.falhou and row.error_code == "source_invalid"
    assert row.error_message == ("Vídeo curto demais: o SociShorts precisa de pelo menos "
                                 "45 segundos")
    ns = _notificacoes(db, NotificacaoTipo.envio_falhou)
    # autor (o membro) e o dono, uma para cada, notificados na mesma volta (SC-003)
    assert sorted(n.user_id for n in ns) == sorted([member[0].id, owner[0].id])

    openshorts_fake.recusar = (403, "YouTube URL ingest is disabled on this deployment.")
    e2 = enviado(client, member[1], perfil["id"], criar_video(criar_canal(CanalDireito.proprio)))
    volta(db, openshorts_fake)
    assert "não baixar links do YouTube" in envio_row(db, e2["id"]).error_message


def test_fora_do_ar_backoff_e_volta_sozinho(envio, db, openshorts_fake, relogio):
    fake = openshorts_fake
    fake.fora = True
    esperas = []
    for _ in range(5):
        volta(db, fake)
        row = envio_row(db, envio["id"])
        assert row.status == EnvioStatus.aguardando_openshorts
        esperas.append((row.next_attempt_at - relogio.t).total_seconds())
        relogio.avancar(esperas[-1])
    assert esperas == [30, 60, 120, 300, 300]
    assert _notificacoes(db, NotificacaoTipo.openshorts_fora) == []  # só 810 s fora

    fake.fora = False
    volta(db, fake)
    row = envio_row(db, envio["id"])
    assert row.status == EnvioStatus.processando and row.attempts == 0
    assert _notificacoes(db, NotificacaoTipo.envio_falhou) == []


def test_30_min_fora_notifica_uma_vez(owner, envio, db, openshorts_fake, relogio):
    fake = openshorts_fake
    fake.erro_5xx = True
    volta(db, fake)
    relogio.avancar(31 * 60)
    volta(db, fake)
    relogio.avancar(300)
    volta(db, fake)
    (n,) = _notificacoes(db, NotificacaoTipo.openshorts_fora)
    assert n.user_id == owner[0].id and n.link == "/app/envios"


def test_404_no_polling_vira_falhou(envio, db, openshorts_fake):
    fake = openshorts_fake
    volta(db, fake)
    fake.expirar(fake.job().id)
    volta(db, fake)
    row = envio_row(db, envio["id"])
    assert row.status == EnvioStatus.falhou and row.error_code == "openshorts_lost"
    assert row.error_message == "O SociShorts não tem mais este job; envie de novo"
    assert len(_notificacoes(db, NotificacaoTipo.envio_falhou)) == 1


def test_sem_clipes_e_falha_do_job(client, owner, perfil, db, openshorts_fake):
    fake = openshorts_fake
    fake.passos_fila = fake.passos_processando = 0
    fake.resultado = "sem_clipes"
    e1 = enviado(client, owner[1], perfil["id"], criar_video(criar_canal(CanalDireito.proprio)))
    volta(db, fake)
    volta(db, fake)
    row = envio_row(db, e1["id"])
    assert row.status == EnvioStatus.sem_clipes
    assert row.error_message == "O SociShorts não encontrou clipes neste vídeo"
    assert len(_notificacoes(db, NotificacaoTipo.envio_sem_clipes)) == 1

    fake.resultado = "falhou"
    e2 = enviado(client, owner[1], perfil["id"], criar_video(criar_canal(CanalDireito.proprio)))
    volta(db, fake)
    volta(db, fake)
    row = envio_row(db, e2["id"])
    assert row.status == EnvioStatus.falhou
    assert row.error_message == "O SociShorts falhou: Download failed: 403"


def test_reinicio_continua_o_polling(envio, openshorts_fake):
    fake = openshorts_fake
    with get_sessionmaker()() as s1:
        volta(s1, fake)
    # "reinício": outra sessão e outro cliente
    for _ in range(3):
        with get_sessionmaker()() as s:
            volta(s, fake)
    with get_sessionmaker()() as s:
        assert envio_row(s, envio["id"]).status == EnvioStatus.importando
    assert fake.pedidos().count(("POST", "/api/process")) == 1


def test_agendador_roda_a_trilha(envio, openshorts_fake):
    """O agendador de verdade (lock + thread), parado e religado no meio."""
    fake = openshorts_fake
    fake.passos_fila = 3

    def ligar() -> tuple[threading.Event, threading.Thread]:
        ag = Agendador(trilhas=[Trilha("openshorts", 0.05,
                                       partial(acompanhamento.rodar, client=fake.client()))],
                       engine=get_engine())
        stop = threading.Event()
        t = threading.Thread(target=ag.run, args=(stop,), daemon=True)
        t.start()
        return stop, t

    def status() -> EnvioStatus:
        with get_sessionmaker()() as s:
            return envio_row(s, envio["id"]).status

    stop, t = ligar()
    fim = time.monotonic() + 10
    while status() != EnvioStatus.processando and time.monotonic() < fim:
        time.sleep(0.05)
    stop.set()
    t.join(5)
    assert status() == EnvioStatus.processando

    stop, t = ligar()
    fim = time.monotonic() + 10
    while status() != EnvioStatus.importando and time.monotonic() < fim:
        time.sleep(0.05)
    stop.set()
    t.join(5)
    assert status() == EnvioStatus.importando
    assert fake.pedidos().count(("POST", "/api/process")) == 1


def test_polling_reveza_quando_ha_mais_envios_que_o_lote(client, owner, perfil, db,
                                                         openshorts_fake, relogio, monkeypatch):
    """Com mais envios em processamento que o lote, todos são consultados: a vez vai para quem
    foi consultado há mais tempo (antes, o lote ia sempre para os mais antigos por `sent_at` e o
    último ficava sem polling para sempre)."""
    fake = openshorts_fake
    fake.passos_fila = 100  # todos ficam `queued`
    monkeypatch.setattr(acompanhamento, "LOTE", 2)
    canal = criar_canal(CanalDireito.proprio)
    envios = [enviado(client, owner[1], perfil["id"], criar_video(canal)) for _ in range(3)]

    for _ in range(4):  # 2 voltas submetem os 3; as seguintes só acompanham
        volta(db, fake)
        relogio.avancar(5)

    for e in envios:
        row = envio_row(db, e["id"])
        assert row.status == EnvioStatus.processando
        assert fake.jobs[row.openshorts_job_id].polls >= 1, row.source_title
