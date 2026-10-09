"""Desempenho do aprendizado (spec 023, T063; R14): análise e recomendações < 2 s com 10× o
volume (400 posts, 4.000 fotos, 30 temas, 400 classificações); o Descobrir com afinidade custa
no máximo +300 ms sobre o mesmo pedido sem afinidade, com 50 mil vídeos-fonte e 30 temas × 20
palavras-chave."""

import time
import uuid

from sqlalchemy import text

from integration.analytics_helpers import cena  # noqa: F401
from integration.aprendizado_helpers import ap, canal_do_perfil, estagnados  # noqa: F401
from sociman_api.aprendizado import analise, recomendacoes
from sociman_api.aprendizado.models import Tema
from sociman_api.ia.guia import normalizar

TEMAS = 30
PALAVRAS = 20


def _temas(ap) -> list[uuid.UUID]:  # noqa: F811
    perfil = uuid.UUID(ap.perfil_id)
    ids = []
    for i in range(TEMAS):
        nome = f"Tema {i}"
        t = Tema(perfil_id=perfil, nome=nome, nome_norm=normalizar(nome),
                 palavras_chave=[f"palavra{i}x{k}" for k in range(PALAVRAS)])
        ap.db.add(t)
        ap.db.flush()
        ids.append(t.id)
    ap.db.commit()
    return ids


def _medir(fn, vezes: int = 3) -> float:
    fn()  # aquecimento
    melhor = float("inf")
    for _ in range(vezes):
        t0 = time.perf_counter()
        fn()
        melhor = min(melhor, time.perf_counter() - t0)
    return melhor


def test_analise_e_recomendacoes_com_10x_o_volume(ap, estagnados):  # noqa: F811
    temas = _temas(ap)
    conta = uuid.UUID(ap.c.conta["id"])
    sid = ap.serie(ap.c.conta)
    ap.db.commit()
    perfil = uuid.UUID(ap.perfil_id)
    ap.db.execute(text("""
        INSERT INTO metricas_videos (id, serie_id, rede_video_id, legenda, duracao_s,
                                     publicado_em, descoberto_em)
        SELECT gen_random_uuid(), :s, (7470000000000000000 + g)::text,
               'Post ' || g || ' #tag' || (g % 7) || ' #extra' || (g % 3), 15 + (g % 60),
               now() - make_interval(days => 2 + (g % 170), hours => g % 24),
               now() - make_interval(days => 2 + (g % 170))
        FROM generate_series(1, 400) g"""), {"s": sid})
    ap.db.execute(text("""
        INSERT INTO metricas_video_fotos (video_id, coletado_em, idade_s, alvo_idade_min, views)
        SELECT v.id, v.publicado_em + make_interval(hours => h), h * 3600, h * 60,
               ((abs(hashtext(v.id::text)) % 5000) * least(h, 24) / 24)
        FROM metricas_videos v, unnest(ARRAY[1, 3, 6, 9, 12, 18, 24, 30, 36, 48]) h
        WHERE v.serie_id = :s"""), {"s": sid})
    ap.db.execute(text("""
        INSERT INTO aprendizado_classificacoes (id, video_id, perfil_id, tema_id, origem,
                                                evidencia_parcial, taxonomia_versao,
                                                estilo_gancho)
        SELECT gen_random_uuid(), v.id, :p, (:temas)[1 + (row_number() OVER ()) % 30],
               'ia', true, 1, 'pergunta'
        FROM metricas_videos v WHERE v.serie_id = :s"""),
        {"p": perfil, "s": sid, "temas": temas})
    ap.db.commit()
    assert conta

    res = analise.calcular(ap.db, perfil)
    assert len(res.medidos) == 400 and len(res.efeitos) > 60
    t_analise = _medir(lambda: analise.calcular(ap.db, perfil))
    t_recs = _medir(lambda: recomendacoes.calcular(ap.db, perfil))
    assert t_analise < 2.0, t_analise
    assert t_recs < 2.0, t_recs


def test_descobrir_com_afinidade_ate_mais_300_ms(ap):  # noqa: F811
    canal = canal_do_perfil(ap)
    _temas(ap)
    ap.db.execute(text("""
        INSERT INTO videos_fonte (id, canal_id, youtube_video_id, title, description,
                                  published_at, duration_s, next_metrics_at, score,
                                  score_reason, recomendavel, views)
        SELECT gen_random_uuid(), :c, 'y' || lpad(g::text, 10, '0'),
               'Vídeo ' || g || ' sobre palavra' || (g % 30) || 'x' || (g % 20),
               'Descrição com acentuação: ação, coração ' || g, now() - interval '2 days', 600,
               now() + interval '1 hour', (g % 1000) / 10.0, 'Recente', true, 1000
        FROM generate_series(1, 50000) g"""), {"c": canal.id})
    ap.db.commit()
    params = {"perfilId": ap.perfil_id, "limit": 50}

    def pedir():
        r = ap.client.get("/api/videos-fonte", headers=ap.h, params=params)
        assert r.status_code == 200, r.text
        return r.json()

    sem = _medir(pedir)
    v = ap.get("preferencias")["perfil"]["version"]
    tema = ap.get("temas")["items"][0]["id"]
    ap.client.patch(f"{ap.url}/preferencias", headers=ap.h,
                    json={"version": v, "temas": {tema: "ampliar"}})
    assert pedir()["items"][0]["afinidade"] is None  # ainda não casado: neutra
    t0 = time.perf_counter()
    ap.casar()  # a trilha casa os 50 mil uma vez (fora da requisição)
    print(f"casamento de 50 mil × {TEMAS} temas: {time.perf_counter() - t0:.1f} s")
    assert pedir()["items"][0]["afinidade"] is not None
    com = _medir(pedir)
    assert com - sem <= 0.3, (sem, com)
