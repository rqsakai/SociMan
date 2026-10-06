"""Mercado (spec 019, US7, T048): mapa de publicação dos canais-fonte em SP, velocidade por
horário (mediana de views ÷ idade_h, para 24 h–7 d) e oportunidades (com `vph_recente` ou views ÷
idade nas 72 h; sem envio ativo, não live, disponível; top 25; com direito), com cálculo de
referência sobre a semeadura (SC-002)."""

import uuid
from datetime import timedelta

import pytest

from integration.analytics_helpers import CONFIG, agora, cena, local  # noqa: F401
from sociman_api.analytics import mercado
from sociman_api.canais.models import CanalDireito, CanalPerfil, VideoLive
from sociman_api.envios.models import DireitoEnvio, Envio, EnvioOrigem, EnvioStatus

T1 = (2, 19)  # há 2 dias, 19:00 (SP)
T2 = (3, 8)


def _envio(c, video, status=EnvioStatus.pronto, perfil_id=None) -> Envio:
    e = Envio(perfil_id=uuid.UUID(str(perfil_id or c.perfil["id"])), origem=EnvioOrigem.canal,
              video_fonte_id=video.id, canal_fonte_id=video.canal_id,
              source_url=f"https://www.youtube.com/watch?v={video.youtube_video_id}",
              source_title="Vídeo de origem", status=status, config=dict(CONFIG),
              direito_no_envio=DireitoEnvio.sem_acordo, aviso_confirmado=True,
              sent_at=agora(), created_by=c.dono.id)
    c.db.add(e)
    c.db.commit()
    return e


@pytest.fixture
def m(cena):  # noqa: F811
    """Canal A (sem_acordo, ligado ao perfil): A1 e A2 em T1 (100/h e 200/h na janela; A2 já
    tem envio), A3 em T2 (20/h; envio descartado não conta), um antigo. Canal B (parceiro): B1
    em T1 (50/h, sem vph_recente). Canal C: uma live e um indisponível."""
    a = cena.canal(CanalDireito.sem_acordo, "Canal A")
    b = cena.canal(CanalDireito.parceiro, "Canal B")
    cc = cena.canal(titulo="Canal C")
    cena.db.add(CanalPerfil(canal_id=a.id, perfil_id=uuid.UUID(cena.perfil["id"])))
    cena.db.commit()
    t1, t2 = local(*T1), local(*T2)

    def um(canal, pub, views, lido_h=None, vph=None, **kw):
        [v] = cena.videos_fonte(1, canal=canal, publicado_em=pub, views=views, vph_recente=vph,
                                metrics_at=pub + timedelta(hours=lido_h) if lido_h else None,
                                **kw)
        return v

    v = {
        "A1": um(a, t1, 4800, 48, vph=500), "A2": um(a, t1, 9600, 48, vph=300),
        "A3": um(a, t2, 1000, 50, vph=30), "B1": um(b, t1, 2400, 48),
        "velho": um(a, local(20, 10), 999),
        "live": um(cc, local(5, 3), 10, vph=1000, live=VideoLive.agendado),
        "fora": um(cc, local(5, 3), 10, vph=900, disponivel=False),
    }
    _envio(cena, v["A2"])
    _envio(cena, v["A3"], status=EnvioStatus.descartado)
    cena.v = v
    return cena


def _celula(mapa, dia_hora) -> dict:
    d = local(*dia_hora)
    return next(c for c in mapa["celulas"] if (c["dia"], c["hora"]) == (d.weekday(), d.hour))


def test_mapa_de_publicacao(m):
    corpo = m.ok("mercado")
    pub = corpo["publicacao"]
    assert len(pub["celulas"]) == 7 * 24
    assert (_celula(pub, T1)["valor"], _celula(pub, T1)["n"]) == (3, 3)
    assert _celula(pub, T2)["n"] == 1
    assert _celula(pub, (5, 3))["n"] == 1  # o indisponível conta; a live não
    assert sum(c["n"] for c in pub["celulas"]) == 5  # o antigo está fora do período


def test_velocidade_por_horario(m):
    vel = m.ok("mercado")["velocidadePorHorario"]
    c1 = _celula(vel, T1)
    assert (c1["valor"], c1["n"], c1["amostraPequena"]) == (100, 3, True)  # 100, 200, 50
    assert _celula(vel, T2)["valor"] == pytest.approx(20)


def test_oportunidades(m):
    corpo = m.ok("mercado")
    ops = corpo["oportunidades"]
    ids = [o["videoFonteId"] for o in ops]
    v = m.v
    assert ids == [str(v["A1"].id), str(v["B1"].id), str(v["A3"].id)]
    a1, b1 = ops[0], ops[1]
    assert a1["velocidade"] == 500 and a1["views"] == 4800
    assert a1["canal"] == {"id": str(v["A1"].canal_id), "titulo": "Canal A",
                           "direito": "sem_acordo"}
    assert a1["linkGerarCortes"] == f"/app/descobrir?canal={v['A1'].canal_id}&video={v['A1'].id}"
    idade = (agora() - local(*T1)).total_seconds() / 3600
    assert b1["idadeH"] == pytest.approx(idade, abs=0.05)
    assert b1["velocidade"] == pytest.approx(2400 / idade, rel=1e-3)
    assert b1["canal"]["direito"] == "parceiro"


def test_top_25(m, monkeypatch):
    monkeypatch.setattr(mercado, "OPORTUNIDADES", 2)
    assert len(m.ok("mercado")["oportunidades"]) == 2


def test_canais(m):
    canais = {c["titulo"]: c for c in m.ok("mercado")["canais"]}
    assert (canais["Canal A"]["videos"], canais["Canal A"]["medianaVelocidade"]) == (3, 100)
    assert (canais["Canal B"]["videos"], canais["Canal B"]["medianaVelocidade"]) == (1, 50)
    assert canais["Canal A"]["direito"] == "sem_acordo"
    assert [c["titulo"] for c in m.ok("mercado")["canais"]][:2] == ["Canal A", "Canal B"]


def test_escopo_do_perfil(m):
    corpo = m.ok("mercado", perfilId=m.perfil["id"])
    assert [o["videoFonteId"] for o in corpo["oportunidades"]] == [str(m.v["A1"].id),
                                                                   str(m.v["A3"].id)]
    assert [c["titulo"] for c in corpo["canais"]] == ["Canal A"]
    # envio de outro perfil não tira a oportunidade deste
    outra = m.segunda_conta("outraconta", outro_perfil=True)
    _envio(m, m.v["A1"], perfil_id=outra["perfilId"])
    corpo = m.ok("mercado", perfilId=m.perfil["id"])
    assert str(m.v["A1"].id) in [o["videoFonteId"] for o in corpo["oportunidades"]]
    assert str(m.v["A1"].id) not in [o["videoFonteId"] for o in m.ok("mercado")["oportunidades"]]
