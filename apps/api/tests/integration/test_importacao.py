"""Importação dos clipes do OpenShorts como cortes em `revisao` (T055; R7, US4, SC-004).

ffmpeg real (clipes sintéticos servidos pelo OpenShorts falso), MinIO real do teste.
"""

import uuid

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
from sociman_api import history, storage
from sociman_api.canais.models import CanalDireito
from sociman_api.config import get_settings
from sociman_api.conteudos.models import Conteudo, ConteudoOrigem
from sociman_api.cortes.models import Corte, CorteOrigem, CorteStatus
from sociman_api.db import get_sessionmaker
from sociman_api.envios import acompanhamento, importacao
from sociman_api.envios.models import Envio, EnvioStatus
from sociman_api.notificacoes.models import Notificacao, NotificacaoTipo

# Fixtures compartilhadas (atribuídas, e não importadas, para o ruff não acusar F811).
_buckets = envios_helpers._buckets
member = envios_helpers.member
owner = envios_helpers.owner
perfil = envios_helpers.perfil
openshorts_clip = _osf.openshorts_clip
openshorts_fake = _osf.openshorts_fake

def _cortes(db, envio_id) -> list[Corte]:
    db.expire_all()
    return list(db.scalars(select(Corte).where(Corte.envio_id == uuid.UUID(str(envio_id)))
                           .order_by(Corte.clip_index)))


def _importar(db, fake) -> int:
    n = importacao.rodar(db, client=fake.client())
    db.commit()
    return n


def _liberar(db, envio_id) -> None:
    """Zera o backoff (no lugar de esperar)."""
    row = envio_row(db, envio_id)
    row.next_attempt_at = None
    db.commit()


@pytest.fixture
def fake(openshorts_fake):
    openshorts_fake.passos_fila = openshorts_fake.passos_processando = 0
    return openshorts_fake


def _ate_importando(client, h, perfil_id, db, fake, **padroes) -> dict:
    if padroes:
        body = {"version": 0, "clipMinS": 15, "clipMaxS": 60, "quantidade": None,
                "layout": "auto", "formato": "vertical", "legenda": "kit",
                "marcaAutomatica": False, "contaPadraoId": None} | padroes
        r = client.put(f"/api/perfis/{perfil_id}/padroes-corte", json=body, headers=h)
        assert r.status_code == 200, r.text
    e = enviado(client, h, perfil_id, criar_video(criar_canal(CanalDireito.proprio)))
    for _ in range(2):
        acompanhamento.rodar(db, client=fake.client())
        db.commit()
    assert envio_row(db, e["id"]).status == EnvioStatus.importando
    return e


def test_importa_todos_os_clipes_em_revisao(client, owner, member, perfil, db, fake):
    user, h = member
    e = _ate_importando(client, h, perfil["id"], db, fake)
    assert _importar(db, fake) == 1

    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.pronto and row.progress == 100
    assert (row.clips_total, row.clips_importados) == (3, 3)
    cortes = _cortes(db, e["id"])
    assert [c.clip_index for c in cortes] == [0, 1, 2]
    c = cortes[0]
    assert c.status == CorteStatus.revisao and c.origem == CorteOrigem.openshorts
    assert c.kit_version is None and c.kit_tokens is None
    assert (c.source_start_ms, c.source_end_ms) == (10_000, 35_500)
    assert c.hook_text == "Gancho do clipe 1" and c.openshorts_title == "Título 1"
    assert c.openshorts_description == "Descrição 1 #corte" and c.openshorts_score == 82
    assert c.transcript == "olá este é o clipe 1" and c.legenda == "kit"
    assert c.created_by == user.id and (c.width, c.height) == (360, 640)
    assert c.original_key == f"perfis/{perfil['id']}/cortes/{c.id}/original.mp4"
    assert storage.stat(c.original_key, bucket="videos").size == c.original_bytes

    (v,) = history.list_versions(db, "corte", c.id)
    assert v.action == "created" and v.actor_kind == "system:agendador"
    assert v.after["status"] == "revisao"

    # Spec 014 (invariante): cada corte importado tem o seu conteúdo, com o mesmo id.
    for corte in cortes:
        conteudo = db.get(Conteudo, corte.id)
        assert conteudo is not None and conteudo.corte_id == corte.id
        assert conteudo.origem == ConteudoOrigem.corte and conteudo.perfil_id == corte.perfil_id
    assert db.get(Conteudo, c.id).titulo == "Título 1"  # o título do OpenShorts vem primeiro
    (cv,) = history.list_versions(db, "conteudo", c.id)
    assert cv.action == "created" and cv.actor_kind == "system:agendador"

    # a legenda do kit foi pedida com a seção openshorts.subtitle do envio
    assert len(fake.subtitles) == 3
    sub = fake.subtitles[0]
    assert sub["job_id"] == fake.job().id and sub["clip_index"] == 0
    assert sub["input_filename"] == "fonte_clip_1.mp4"
    assert {k: sub[k] for k in row.config["subtitle"]} == row.config["subtitle"]

    ns = list(db.scalars(select(Notificacao).where(
        Notificacao.tipo == NotificacaoTipo.envio_pronto)))
    assert sorted(n.user_id for n in ns) == sorted([user.id, owner[0].id])
    assert ns[0].link == f"/app/envios/{e['id']}" and ns[0].corpo == "3 clipes para revisar"

    # a API mostra os clipes na revisão e na aba Cortes do perfil
    r = client.get(f"/api/envios/{e['id']}", headers=h)
    assert r.status_code == 200
    out = r.json()
    assert out["envio"]["status"] == "pronto" and len(out["cortes"]) == 3
    c0 = out["cortes"][0]
    assert c0["status"] == "revisao" and c0["kitVersion"] is None and c0["origem"] == "openshorts"
    assert c0["envioId"] == e["id"] and c0["clipIndex"] == 0 and c0["legenda"] == "kit"
    assert c0["canal"]["title"] == "Canal" and c0["direitoNoEnvio"] == "proprio"
    assert c0["openshortsScore"] == 82 and c0["archived"] is False and c0["destinos"] == []
    r = client.get(f"/api/perfis/{perfil['id']}/cortes", params={"origem": "openshorts"},
                   headers=h)
    assert len(r.json()["items"]) == 3
    assert _importar(db, fake) == 0


def test_etapas_legendas_e_importando(client, owner, perfil, db, fake, monkeypatch):
    """FR-010a: cada passo lento fica visível (commit) com clipe N de M e o % geral 90..100."""
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake)
    vistos: list[tuple] = []

    def espiar(fn):
        def wrapper(*args, **kwargs):
            with get_sessionmaker()() as outra:  # o que a API vê: só o que foi commitado
                row = outra.get(Envio, uuid.UUID(e["id"]))
                vistos.append((row.etapa, row.etapa_mensagem, row.progress))
            return fn(*args, **kwargs)
        return wrapper

    monkeypatch.setattr(importacao, "_legendar", espiar(importacao._legendar))
    monkeypatch.setattr(importacao, "probe", espiar(importacao.probe))
    _importar(db, fake)
    assert vistos == [
        ("legendas", "Aplicando legendas do kit 1 de 3", 90),
        ("importando", "Importando 1 de 3", 90),
        ("legendas", "Aplicando legendas do kit 2 de 3", 93),
        ("importando", "Importando 2 de 3", 93),
        ("legendas", "Aplicando legendas do kit 3 de 3", 96),
        ("importando", "Importando 3 de 3", 96),
    ]
    out = client.get(f"/api/envios/{e['id']}", headers=h).json()["envio"]
    assert (out["etapa"], out["etapaMensagem"], out["progress"]) == (
        "concluido", "Pronto: 3 clipes", 100)


def test_clipe_sem_fala_e_legenda_do_gerador(client, owner, perfil, db, fake):
    _, h = owner
    fake.sem_fala = {1}
    e = _ate_importando(client, h, perfil["id"], db, fake)
    _importar(db, fake)
    c = _cortes(db, e["id"])
    assert [x.legenda for x in c] == ["kit", "sem_fala", "kit"]
    assert c[1].transcript is None
    assert envio_row(db, e["id"]).status == EnvioStatus.pronto


def test_legenda_do_gerador_nao_chama_subtitle(client, owner, perfil, db, fake):
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake, legenda="gerador")
    assert fake.processados[-1]["captions"] is True
    _importar(db, fake)
    assert fake.subtitles == []
    assert {c.legenda for c in _cortes(db, e["id"])} == {"gerador"}


class Queda(Exception):
    pass


def _cair_no_clipe(monkeypatch, pos_queda: int) -> None:
    original = importacao.importar_clipe

    def importar_clipe(db, client, envio, pos, clip, clip_index):
        if pos == pos_queda:
            raise Queda("agendador morreu no meio")
        return original(db, client, envio, pos, clip, clip_index)

    monkeypatch.setattr(importacao, "importar_clipe", importar_clipe)


def test_reinicio_no_meio_nao_duplica(client, owner, perfil, db, fake, monkeypatch):
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake)
    _cair_no_clipe(monkeypatch, 1)
    with pytest.raises(Queda):
        importacao.rodar(db, client=fake.client())
    db.rollback()  # o agendador faz rollback da volta; o clipe 0 já estava commitado
    assert [c.clip_index for c in _cortes(db, e["id"])] == [0]
    assert envio_row(db, e["id"]).status == EnvioStatus.importando

    monkeypatch.undo()
    _importar(db, fake)
    assert [c.clip_index for c in _cortes(db, e["id"])] == [0, 1, 2]
    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.pronto and row.clips_importados == 3


def test_sem_sentinela_fica_importando(client, owner, perfil, db, fake, monkeypatch, tmp_path):
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake)
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))
    assert _importar(db, fake) == 0
    assert envio_row(db, e["id"]).status == EnvioStatus.importando
    assert fake.subtitles == []


def test_hd_cheio_espera_sem_contar_tentativa(client, owner, perfil, db, fake, monkeypatch):
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake, legenda="nenhuma")
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    _importar(db, fake)
    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.importando and row.attempts == 0
    assert row.next_attempt_at is not None and _cortes(db, e["id"]) == []


def test_clipes_expirados_mantem_os_importados(client, owner, perfil, db, fake, monkeypatch):
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake)
    _cair_no_clipe(monkeypatch, 1)
    with pytest.raises(Queda):
        importacao.rodar(db, client=fake.client())
    db.rollback()
    monkeypatch.undo()

    fake.expirar(fake.job().id)
    _importar(db, fake)
    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.falhou and row.error_code == "clips_expired"
    assert row.error_message == "Os clipes expiraram no SociShorts"
    assert row.clips_importados == 1
    assert [c.clip_index for c in _cortes(db, e["id"])] == [0]
    ns = list(db.scalars(select(Notificacao).where(
        Notificacao.tipo == NotificacaoTipo.envio_falhou)))
    assert len(ns) == 1

    # clipes expirados: "tentar de novo" pede um job novo
    r = client.post(f"/api/envios/{e['id']}/retry", json={"version": row.version}, headers=h)
    assert r.status_code == 200 and r.json()["envio"]["status"] == "na_fila"


def test_tres_erros_falham_e_importar_de_novo(client, owner, perfil, db, fake):
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake, legenda="nenhuma")
    fake.falhar_download = 3
    for tentativa in (1, 2):
        _importar(db, fake)
        row = envio_row(db, e["id"])
        assert row.status == EnvioStatus.importando and row.attempts == tentativa
        assert _importar(db, fake) == 0  # backoff
        _liberar(db, e["id"])
    _importar(db, fake)
    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.falhou and row.error_code == "import_failed"
    assert "Importar de novo" in row.error_message

    r = client.post(f"/api/envios/{e['id']}/retry", json={"version": row.version}, headers=h)
    assert r.status_code == 200 and r.json()["envio"]["status"] == "importando"
    _importar(db, fake)
    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.pronto and row.clips_importados == 3
    assert fake.pedidos().count(("POST", "/api/process")) == 1  # mesmo job


def test_marca_automatica_vai_para_a_fila(client, owner, perfil, db, fake):
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake, marcaAutomatica=True)
    _importar(db, fake)
    cortes = _cortes(db, e["id"])
    assert {c.status for c in cortes} == {CorteStatus.na_fila}
    c = cortes[0]
    assert c.kit_version == 0 and c.kit_tokens["hook"]["fonte"]["padrao"] == "noto-serif-bold"
    versions = history.list_versions(db, "corte", c.id)
    assert [v.action for v in versions] == ["updated", "created"]
    assert versions[0].actor_kind == "system:agendador"
    assert versions[0].details == {"acao": "aplicar_marca"}


def test_job_novo_em_outra_ordem_nao_duplica_pelo_trecho(client, owner, perfil, db, fake,
                                                         monkeypatch):
    """Importação parcial, clipes expirados, "tentar de novo" com job novo que devolve os
    clipes em ordem inversa e com o trecho deslocado em 0,4 s: só entram os trechos novos."""
    _, h = owner
    e = _ate_importando(client, h, perfil["id"], db, fake, legenda="nenhuma")
    _cair_no_clipe(monkeypatch, 1)
    with pytest.raises(Queda):
        importacao.rodar(db, client=fake.client())
    db.rollback()
    monkeypatch.undo()
    (primeiro,) = _cortes(db, e["id"])
    assert (primeiro.clip_index, primeiro.source_start_ms) == (0, 10_000)

    fake.expirar(fake.job().id)
    _importar(db, fake)
    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.falhou and row.error_code == "clips_expired"
    r = client.post(f"/api/envios/{e['id']}/retry", json={"version": row.version}, headers=h)
    assert r.status_code == 200 and r.json()["envio"]["status"] == "na_fila"

    fake.inverter_ordem, fake.desvio_s = True, 0.4
    for _ in range(2):
        acompanhamento.rodar(db, client=fake.client())
        db.commit()
    assert envio_row(db, e["id"]).status == EnvioStatus.importando
    _importar(db, fake)

    row = envio_row(db, e["id"])
    assert row.status == EnvioStatus.pronto and row.clips_importados == 3
    cortes = _cortes(db, e["id"])
    assert [c.clip_index for c in cortes] == [0, 1, 2]
    assert cortes[0].id == primeiro.id  # o já importado ficou, sem cópia
    assert sorted(c.source_start_ms for c in cortes) == [10_000, 40_400, 70_400]
