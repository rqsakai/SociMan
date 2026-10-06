"""Rotas de leitura das métricas (spec 016, US4; contrato, "Métricas de conta" e "Vídeos,
ranking e curva"): ranking ordenável e filtrável com cursor, curva e marcos, conta, destino,
permissões e o tempo do ranking (SC-004)."""

import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text, update

from integration.metricas_helpers import _agora, semear
from integration.postagem_helpers import (  # noqa: F401
    PW,
    criar_conta,
    criar_corte,
    criar_perfil,
    membro,
)
from sociman_api.auth.deps import Actor
from sociman_api.db import get_engine
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import Serie, VideoRede, VinculoMetodo
from sociman_api.postagem.models import DestinoEstado, Postagem


@pytest.fixture
def base(client, db, make_user, login):
    dono = make_user(role="dono", name="Dono")
    h = login(client, dono.email, PW)
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], "tiktok", "atavernanerd")
    return {"dono": dono, "h": h, "perfil": perfil, "conta": conta}


def _get(client, h, url, **params):
    r = client.get(url, headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _ligar(db, video_id, perfil_id, conta_id, dono) -> Postagem:
    corte = criar_corte(db, perfil_id)
    agora = _agora()
    destino = Postagem(conteudo_id=corte.id, conta_id=uuid.UUID(conta_id),
                       estado=DestinoEstado.postado, aprovado_por=dono.id, aprovado_em=agora,
                       posted_at=agora, version=1, created_by=dono.id)
    db.add(destino)
    db.flush()
    db.execute(update(VideoRede).where(VideoRede.id == video_id).values(
        destino_id=destino.id, vinculo_metodo=VinculoMetodo.escolha, vinculado_em=agora))
    db.commit()
    return destino


def test_ranking_ordena_nas_duas_direcoes_com_cursor_estavel(client, db, base):
    # 3 vídeos com 30 fotos horárias: o i-ésimo tem views = 100·k·(i+1).
    s = semear(db, base["conta"]["id"], videos=3, fotos=30, inicio=_agora() - timedelta(days=5))
    ids = [str(i) for i in s.videos]
    for ordem in ("views", "views24h", "engajamento", "velocidade", "publicadoEm"):
        desc = [v["id"] for v in _get(client, base["h"], "/api/metricas/videos", ordem=ordem,
                                      direcao="desc")["items"]]
        asc = [v["id"] for v in _get(client, base["h"], "/api/metricas/videos", ordem=ordem,
                                     direcao="asc")["items"]]
        assert sorted(desc) == sorted(ids) and asc == list(reversed(desc)), ordem
    # Padrão: views total (a última foto), maior primeiro.
    padrao = _get(client, base["h"], "/api/metricas/videos")["items"]
    assert [v["id"] for v in padrao] == list(reversed(ids))
    assert [v["ultima"]["views"] for v in padrao] == [300 * 30, 200 * 30, 100 * 30]
    top = _get(client, base["h"], "/api/metricas/videos", ordem="views24h")["items"]
    assert [v["id"] for v in top] == list(reversed(ids))
    assert top[0]["views24h"]["valor"] == pytest.approx(300 * 24)
    assert top[0]["origem"] == "fora" and top[0]["conta"]["handle"] == "atavernanerd"
    assert top[0]["ultima"]["views"] == 300 * 30
    # Cursor: 2 por página, sem repetir nem pular.
    p1 = _get(client, base["h"], "/api/metricas/videos", ordem="publicadoEm", limite=2)
    assert p1["total"] == 3 and len(p1["items"]) == 2 and p1["nextCursor"]
    p2 = _get(client, base["h"], "/api/metricas/videos", ordem="publicadoEm", limite=2,
              cursor=p1["nextCursor"])
    assert len(p2["items"]) == 1 and p2["nextCursor"] is None
    assert [v["id"] for v in p1["items"] + p2["items"]] == list(reversed(ids))
    r = client.get("/api/metricas/videos", headers=base["h"], params={"limite": 101})
    assert r.status_code == 400


def test_ranking_filtra_por_conta_perfil_origem_e_periodo(client, db, base):
    s = semear(db, base["conta"]["id"], videos=2, fotos=2, inicio=_agora() - timedelta(days=4))
    _ligar(db, s.videos[0], base["perfil"]["id"], base["conta"]["id"], base["dono"])
    outro = criar_perfil(client, base["h"], "Outro")
    conta2 = criar_conta(client, base["h"], outro["id"], "tiktok", "meusqueridinhos10")
    s2 = semear(db, conta2["id"], videos=1, fotos=2, inicio=_agora() - timedelta(days=20))
    url = "/api/metricas/videos"
    assert _get(client, base["h"], url)["total"] == 3
    assert {v["id"] for v in _get(client, base["h"], url, contaId=conta2["id"])["items"]} == \
        {str(s2.videos[0])}
    assert _get(client, base["h"], url, perfilId=base["perfil"]["id"])["total"] == 2
    cortes = _get(client, base["h"], url, origem="corte")["items"]
    assert [v["id"] for v in cortes] == [str(s.videos[0])]
    assert cortes[0]["destinoId"] and cortes[0]["vinculoMetodo"] == "escolha"
    assert _get(client, base["h"], url, origem="fora,corte")["total"] == 3
    de = (_agora() - timedelta(days=10)).date().isoformat()
    assert _get(client, base["h"], url, de=de)["total"] == 2
    r = client.get(url, headers=base["h"], params={"origem": "outra"})
    assert r.status_code == 400


def test_curva_marcos_e_conta(client, db, base):
    s = semear(db, base["conta"]["id"], videos=1, fotos=30, inicio=_agora() - timedelta(days=3))
    d = _get(client, base["h"], f"/api/metricas/videos/{s.videos[0]}")
    assert len(d["fotos"]) == 30 and d["fotos"][0]["idadeS"] == 3600
    assert d["marcos"]["h1"]["views"] == {"valor": 100, "estimado": False, "motivo": None}
    assert d["marcos"]["d7"]["views"]["motivo"] == "ainda_nao"
    assert d["coletaParadaEm"] is None
    assert client.get(f"/api/metricas/videos/{uuid.uuid4()}",
                      headers=base["h"]).status_code == 404
    c = _get(client, base["h"], f"/api/contas/{base['conta']['id']}/metricas", resolucao="dia")
    assert c["fotos"] and c["fotos"][0]["seguidores"] >= 1000
    assert [p["videoId"] for p in c["publicacoes"]] == [str(s.videos[0])]
    assert "coletando" in c["coleta"]
    assert client.get(f"/api/contas/{uuid.uuid4()}/metricas",
                      headers=base["h"]).status_code == 404


def test_views_da_conta_somam_a_ultima_foto_de_cada_video(client, db, base):
    """A rede não dá views da conta: em cada foto da conta, a soma, por vídeo da série, da
    última foto com `coletado_em` até ali; vídeo sem foto até o corte não entra."""
    from sociman_api.metricas.models import FotoVideo

    t0 = (_agora() - timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
    # `semear` grava uma foto da conta por dia, em t0, t0 + 24 h, t0 + 48 h e t0 + 72 h.
    s = semear(db, base["conta"]["id"], videos=2, fotos=0, inicio=t0, intervalo_h=24)
    a, b = s.videos  # `a` publicado em t0, `b` em t0 + 24 h
    pub = {a: t0, b: t0 + timedelta(hours=24)}
    for vid, h, views in [(a, 1, 100), (a, 5, 500), (a, 24, 600), (b, 25, 70), (a, 30, 900)]:
        em = t0 + timedelta(hours=h)
        idade = int((em - pub[vid]).total_seconds())
        db.add(FotoVideo(video_id=vid, coletado_em=em, idade_s=idade, alvo_idade_min=idade // 60,
                         views=views, likes=0, comments=0, shares=0))
    db.commit()
    c = _get(client, base["h"], f"/api/contas/{base['conta']['id']}/metricas", resolucao="hora")
    # t0: nenhum vídeo com foto; t0 + 24 h: só `a` (a foto no limite entra; `b` ainda sem foto);
    # depois, a última de `a` (900) + a de `b` (70).
    assert [f["views"] for f in c["fotos"]] == [None, 600, 970, 970]
    assert c["viewsTotal"] == 970
    # Sem série viva: sem fotos e sem total.
    outra = criar_conta(client, base["h"], criar_perfil(client, base["h"], "Outro")["id"],
                        "tiktok", "semserie")
    vazio = _get(client, base["h"], f"/api/contas/{outra['id']}/metricas")
    assert vazio["fotos"] == [] and vazio["viewsTotal"] is None


def test_destino_traz_vinculo_e_curva(client, db, base):
    s = semear(db, base["conta"]["id"], videos=1, fotos=3)
    destino = _ligar(db, s.videos[0], base["perfil"]["id"], base["conta"]["id"], base["dono"])
    out = _get(client, base["h"], f"/api/destinos/{destino.id}/metricas")
    assert out["vinculo"]["estado"] == "vinculado"
    assert out["video"]["id"] == str(s.videos[0]) and len(out["video"]["fotos"]) == 3


def test_membro_ve_tudo_e_nada_da_cdn_da_rede(client, db, base, membro):  # noqa: F811
    s = semear(db, base["conta"]["id"], videos=2, fotos=2)
    h = membro[1]
    lista = client.get("/api/metricas/videos", headers=h)
    assert lista.status_code == 200
    assert client.get(f"/api/metricas/videos/{s.videos[0]}", headers=h).status_code == 200
    assert client.get(f"/api/contas/{base['conta']['id']}/metricas",
                      headers=h).status_code == 200
    assert "tiktokcdn" not in lista.text and "cover_image" not in lista.text
    assert all(v["miniaturaUrl"] is None or v["miniaturaUrl"].startswith("/img")
               for v in lista.json()["items"])


def test_anonimo_sem_conta_link_nem_legenda(client, db, base):
    s = semear(db, base["conta"]["id"], videos=1, fotos=2)
    anonimizar.serie(db, db.get(Serie, s.serie_id), Actor(kind="user", user_id=base["dono"].id))
    db.commit()
    items = _get(client, base["h"], "/api/metricas/videos", origem="anonima")["items"]
    assert len(items) == 1
    v = items[0]
    assert v["conta"] is None and v["contaId"] is None and v["url"] is None
    assert v["legenda"] is None and v["origem"] == "anonima"
    assert v["serieRotulo"].startswith("Conta anônima ")


def _semear_ano(conta_id: str) -> None:
    """1 ano de 1 conta por SQL: 2 posts/dia (730 vídeos) × 95 fotos."""
    with get_engine().begin() as conn:
        serie = conn.execute(text(
            "INSERT INTO metricas_series (id, rede, conta_id) VALUES (gen_random_uuid(), "
            "'tiktok', :c) RETURNING id"), {"c": conta_id}).scalar()
        conn.execute(text(
            "INSERT INTO metricas_videos (id, serie_id, rede_video_id, duracao_s, publicado_em)"
            " SELECT gen_random_uuid(), :s, (7460000000000000000 + g)::text, 30,"
            " now() - interval '366 days' + g * interval '12 hours'"
            " FROM generate_series(1, 730) g"), {"s": serie})
        conn.execute(text(
            "INSERT INTO metricas_video_fotos (video_id, coletado_em, idade_s, alvo_idade_min,"
            " views, likes, comments, shares)"
            " SELECT v.id, v.publicado_em + k * interval '1 hour', k * 3600, k * 60,"
            " k * 100, k * 10, k, k"
            " FROM metricas_videos v CROSS JOIN generate_series(1, 95) k"
            " WHERE v.serie_id = :s AND v.publicado_em + k * interval '1 hour' < now()"),
            {"s": serie})


def test_ranking_de_2_contas_por_1_ano_em_menos_de_300ms(client, db, base):
    outro = criar_perfil(client, base["h"], "Outro")
    conta2 = criar_conta(client, base["h"], outro["id"], "tiktok", "meusqueridinhos10")
    _semear_ano(base["conta"]["id"])
    _semear_ano(conta2["id"])
    with get_engine().begin() as conn:
        conn.execute(text("ANALYZE metricas_videos; ANALYZE metricas_video_fotos"))
    _get(client, base["h"], "/api/metricas/videos", ordem="views7d")  # aquece
    t0 = time.perf_counter()
    r = _get(client, base["h"], "/api/metricas/videos", ordem="views7d")
    assert time.perf_counter() - t0 < 0.3
    assert r["total"] == 1460 and len(r["items"]) == 50
    _get(client, base["h"], "/api/metricas/videos")  # padrão: views total
    t0 = time.perf_counter()
    r = _get(client, base["h"], "/api/metricas/videos")
    assert time.perf_counter() - t0 < 0.3
    assert r["total"] == 1460 and len(r["items"]) == 50
