"""Desempenho do analytics (spec 019, R13, SC-003): 10× o volume atual de métricas (220 vídeos,
~3.000 fotos, 400 destinos, 4.000 cortes) e 50 mil vídeos-fonte, semeados por SQL em lote, e
cada uma das 8 rotas `/api/analytics/*` responde em menos de 2 s, no período padrão (7 dias) e
num de 90 dias (tudo dentro)."""

import time
from datetime import timedelta

from sqlalchemy import text

from integration.analytics_helpers import cena, hoje_sp  # noqa: F401
from sociman_api.db import get_engine

ABAS = ("visao-geral", "quando-postar", "o-que-funciona", "curvas", "contas", "funil", "mercado",
        "alertas")
LIMITE_S = 2.0
IDADES_H = (1, 2, 3, 6, 12, 18, 24, 36, 48, 72, 96, 120, 168, 240, 336)  # até 15 fotos por vídeo
CONFIG = ('{"clip_min_s": 15, "clip_max_s": 60, "quantidade": null, "layout": "auto", '
          '"formato": "vertical", "legenda": "kit"}')


def _semear_10x(dono_id, perfis: list[str], contas: list[str]) -> None:
    """40 canais × 1.250 vídeos-fonte; 400 envios (200 por perfil) × 10 cortes (4.000 cortes e
    conteúdos); o 1º corte de cada envio vira destino postado na conta do perfil (400); 110
    vídeos por conta (100 vinculados) com até 15 fotos; foto diária da conta; custo de IA por
    destino."""
    p = {"dono": dono_id, "p1": perfis[0], "p2": perfis[1], "c1": contas[0], "c2": contas[1],
         "config": CONFIG, "idades": list(IDADES_H)}
    sqls = [
        ("INSERT INTO canais_fonte (id, youtube_channel_id, title, uploads_playlist_id, direito)"
         " SELECT gen_random_uuid(), 'UCperf' || lpad(g::text, 18, '0'), 'Canal ' || g,"
         " 'UUperf' || lpad(g::text, 18, '0'), (ARRAY['sem_acordo', 'proprio', 'parceiro',"
         " 'programa_de_cortes'])[g % 4 + 1]::canal_direito FROM generate_series(1, 40) g"),
        ("INSERT INTO videos_fonte (id, canal_id, youtube_video_id, title, published_at,"
         " duration_s, views, vph_recente, next_metrics_at, score, recomendavel)"
         " SELECT gen_random_uuid(), c.id, 'P' || lpad(g::text, 10, '0'), 'Vídeo ' || g,"
         " now() - ((g * 37) % 2880) * interval '1 hour', 600 + g % 3000, (g * 7919) % 500000,"
         " CASE WHEN g % 3 = 0 THEN (g % 1000)::numeric END, now(), g % 101, g % 7 = 0"
         " FROM generate_series(1, 50000) g JOIN (SELECT id, row_number() OVER"
         " (ORDER BY youtube_channel_id) - 1 AS i FROM canais_fonte) c ON c.i = g % 40"),
        ("INSERT INTO envios (id, perfil_id, origem, video_fonte_id, canal_fonte_id, source_url,"
         " source_title, status, config, direito_no_envio, aviso_confirmado, sent_at, started_at,"
         " finished_at, created_by)"
         " SELECT gen_random_uuid(), CASE WHEN v.i % 2 = 0 THEN CAST(:p1 AS uuid)"
         " ELSE CAST(:p2 AS uuid) END, 'canal', v.id, v.canal_id,"
         " 'https://www.youtube.com/watch?v=' || v.youtube_video_id, 'Perf ' || v.i, 'pronto',"
         " CAST(:config AS jsonb), c.direito::text::direito_envio, true,"
         " now() - (2 + v.i % 80) * interval '1 day', now() - (2 + v.i % 80) * interval '1 day',"
         " now() - (2 + v.i % 80) * interval '1 day' + interval '20 minutes', :dono"
         " FROM (SELECT id, canal_id, youtube_video_id, row_number() OVER"
         " (ORDER BY youtube_video_id) AS i FROM videos_fonte) v"
         " JOIN canais_fonte c ON c.id = v.canal_id WHERE v.i <= 400"),
        ("INSERT INTO cortes (id, perfil_id, hook_text, kit_version, kit_tokens, status,"
         " original_filename, original_key, original_content_type, original_bytes, duration_ms,"
         " width, height, fps, video_codec, original_sha256, result_key, finished_at, origem,"
         " envio_id, clip_index, openshorts_score, created_by)"
         " SELECT gen_random_uuid(), e.perfil_id, 'Gancho ' || k, 0, '{}', 'pronto', 'clipe.mp4',"
         " 'perf/' || e.id || '/' || k, 'video/mp4', 10, 15000 + k * 4000, 1080, 1920, 30,"
         " 'h264', repeat('0', 64), 'perf/' || e.id || '/' || k || '/r', e.finished_at,"
         " 'openshorts', e.id, k, k * 9, :dono"
         " FROM envios e CROSS JOIN generate_series(1, 10) k"),
        ("INSERT INTO conteudos (id, perfil_id, origem, corte_id, titulo, created_by)"
         " SELECT id, perfil_id, 'corte', id, hook_text, created_by FROM cortes"),
        ("INSERT INTO postagens (id, conta_id, conteudo_id, descricao, hashtags, estado, modo,"
         " aprovado_por, aprovado_em, posted_at, created_by)"
         " SELECT gen_random_uuid(), CASE WHEN c.perfil_id = CAST(:p1 AS uuid)"
         " THEN CAST(:c1 AS uuid) ELSE CAST(:c2 AS uuid) END, c.id, 'Legenda #fyp',"
         " ARRAY['#fyp', '#tag' || (e.clips % 6)], 'postado', 'lembrete', :dono,"
         " e.finished_at + interval '1 day', e.finished_at + interval '1 day 1 hour', :dono"
         " FROM cortes c JOIN (SELECT id, finished_at, row_number() OVER (ORDER BY id) AS clips"
         " FROM envios) e ON e.id = c.envio_id WHERE c.clip_index = 1"),
        ("INSERT INTO metricas_series (id, rede, conta_id) SELECT gen_random_uuid(), 'tiktok', c"
         " FROM unnest(ARRAY[CAST(:c1 AS uuid), CAST(:c2 AS uuid)]) c"),
        ("INSERT INTO metricas_videos (id, serie_id, rede_video_id, legenda, duracao_s,"
         " publicado_em, descoberto_em, destino_id, vinculo_metodo, vinculado_em)"
         " SELECT gen_random_uuid(), s.id, (7460000000000000000 + row_number() OVER ())::text,"
         " 'Legenda #fyp', 30, p.posted_at, p.posted_at, p.id, 'escolha', now()"
         " FROM (SELECT id, conta_id, posted_at, row_number() OVER (PARTITION BY conta_id"
         " ORDER BY posted_at DESC) AS n FROM postagens) p"
         " JOIN metricas_series s ON s.conta_id = p.conta_id WHERE p.n <= 100"),
        ("INSERT INTO metricas_videos (id, serie_id, rede_video_id, legenda, duracao_s,"
         " publicado_em, descoberto_em)"
         " SELECT gen_random_uuid(), s.id, (7470000000000000000 + row_number() OVER ())::text,"
         " 'Fora do SociMan', 25, now() - g * interval '3 days' - interval '5 hours',"
         " now() - g * interval '3 days' FROM metricas_series s"
         " CROSS JOIN generate_series(1, 10) g"),
        ("INSERT INTO metricas_video_fotos (video_id, coletado_em, idade_s, alvo_idade_min, views,"
         " likes, comments, shares)"
         " SELECT v.id, v.publicado_em + h * interval '1 hour', h * 3600, h * 60,"
         " h * (50 + abs(hashtext(v.id::text)) % 400), h * 5, h, h"
         " FROM metricas_videos v CROSS JOIN unnest(CAST(:idades AS int[])) h"
         " WHERE v.publicado_em + h * interval '1 hour' < now()"),
        ("INSERT INTO metricas_conta_fotos (serie_id, coletado_em, janela_em, seguidores, seguindo,"
         " curtidas, videos)"
         " SELECT s.id, date_trunc('hour', now()) - d * interval '1 day',"
         " date_trunc('hour', now()) - d * interval '1 day', 5000 - d * 10, 10, 90000 - d * 100,"
         " 110 FROM metricas_series s CROSS JOIN generate_series(0, 120) d"),
        ("INSERT INTO ia_chamadas (id, tipo_campo, perfil_id, entity_type, conteudo_id, model,"
         " prompt_version, duration_ms, custo_usd, created_at, created_by)"
         " SELECT gen_random_uuid(), 'postagem.textos', c.perfil_id, 'postagem', c.id,"
         " 'claude-fake', 'ia/2', 1, 0.012, p.aprovado_em - interval '1 hour', :dono"
         " FROM postagens p JOIN conteudos c ON c.id = p.conteudo_id"),
    ]
    with get_engine().begin() as conn:
        for sql in sqls:
            conn.execute(text(sql), p)
        conn.execute(text(
            "ANALYZE canais_fonte; ANALYZE videos_fonte; ANALYZE envios; ANALYZE cortes;"
            " ANALYZE conteudos; ANALYZE postagens; ANALYZE metricas_series;"
            " ANALYZE metricas_videos; ANALYZE metricas_video_fotos; ANALYZE metricas_conta_fotos;"
            " ANALYZE ia_chamadas"))


def _contagens() -> dict[str, int]:
    with get_engine().connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
                for t in ("videos_fonte", "envios", "cortes", "postagens", "metricas_videos",
                          "metricas_video_fotos")}


def test_cada_aba_responde_em_menos_de_2s_com_10x_o_volume(cena):  # noqa: F811
    outra = cena.segunda_conta(outro_perfil=True)
    _semear_10x(cena.dono.id, [cena.perfil["id"], outra["perfilId"]],
                [cena.conta["id"], outra["id"]])
    n = _contagens()
    assert n["videos_fonte"] == 50_000 and n["cortes"] == 4_000 and n["postagens"] == 400
    assert n["metricas_videos"] == 220 and 2_800 <= n["metricas_video_fotos"] <= 3_300

    hoje = hoje_sp()
    periodos = {"7d": {}, "90d": {"de": (hoje - timedelta(days=89)).isoformat(),
                                  "ate": hoje.isoformat()}}
    tempos: dict[str, float] = {}
    for rotulo, params in periodos.items():
        for aba in ABAS:
            cena.ok(aba, **params)  # aquece
            t0 = time.perf_counter()
            cena.ok(aba, **params)
            tempos[f"{aba} ({rotulo})"] = time.perf_counter() - t0
    print("\n" + "\n".join(f"{k}: {v * 1000:.0f} ms" for k, v in tempos.items()))
    lentas = {k: round(v, 2) for k, v in tempos.items() if v >= LIMITE_S}
    assert not lentas, f"acima de {LIMITE_S} s: {lentas}"
