"""Desempenho da 020 (T049): a prévia e o confirmar de 366 dias em menos de 1 s, e as 8 abas do
analytics com 366 dias de Studio em 2 séries mais 10× o volume da 019 em menos de 2 s (SC-003 da
019), nos períodos de 7, 90 e 366 dias."""

import time
from datetime import timedelta

from sqlalchemy import text

from integration.analytics_helpers import cena, hoje_sp, local  # noqa: F401
from integration.studio_helpers import (
    overview_dias,
    seguidores_dias,
    st,  # noqa: F401
    zip_overview,
    zip_seguidores,
)
from integration.test_analytics_desempenho import ABAS, LIMITE_S, _semear_10x
from sociman_api.db import get_engine

H = "atavernanerd"


def test_previa_e_confirmar_de_366_dias_em_menos_de_1s(st):  # noqa: F811
    ate = local(1).date()
    arquivos = (zip_overview(overview_dias(ate, 366), H),
                zip_seguidores(seguidores_dias(ate, 366), H))
    st.previa_ok(*arquivos)  # aquece
    t0 = time.perf_counter()
    p = st.previa_ok(*arquivos)
    previa = time.perf_counter() - t0
    t0 = time.perf_counter()
    r = st.confirmar(p["previaId"])
    confirmar = time.perf_counter() - t0
    assert r.status_code == 201 and r.json()["gravados"] == 366
    print(f"\nprévia: {previa * 1000:.0f} ms; confirmar: {confirmar * 1000:.0f} ms")
    assert previa < 1.0 and confirmar < 1.0


def _studio_366(dono_id) -> None:
    """Uma importação ativa de 366 dias (até ontem) em cada série, por SQL em lote."""
    with get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO metricas_studio_importacoes (id, serie_id, secoes, sha_visao_geral,"
            " sha_seguidores, periodo_de, periodo_ate, ano_origem, contagens, criada_por)"
            " SELECT gen_random_uuid(), s.id, ARRAY['visao_geral','seguidores'],"
            " md5(s.id::text || 'vg'), md5(s.id::text || 'seg'), CAST(:de AS date),"
            " CAST(:ate AS date), 'nome_zip', '{}'::jsonb, :dono FROM metricas_series s"),
            {"de": hoje_sp() - timedelta(days=366), "ate": hoje_sp() - timedelta(days=1),
             "dono": dono_id})
        conn.execute(text(
            "INSERT INTO metricas_studio_dias (importacao_id, serie_id, dia, tem_visao_geral,"
            " views, visitas_perfil, likes, comments, shares, tem_seguidores, seguidores,"
            " seguidores_dif)"
            " SELECT i.id, i.serie_id, d::date, true, 100 + g, g % 7, 10 + g % 13, g % 3, g % 2,"
            " true, 1000 + g, 1 FROM metricas_studio_importacoes i"
            " CROSS JOIN generate_series(1, 366) g"
            " CROSS JOIN LATERAL (SELECT i.periodo_de + (g - 1) AS d) x"))
        conn.execute(text("ANALYZE metricas_studio_importacoes; ANALYZE metricas_studio_dias"))


def test_abas_com_366_dias_de_studio_e_10x_o_volume(cena):  # noqa: F811
    outra = cena.segunda_conta(outro_perfil=True)
    _semear_10x(cena.dono.id, [cena.perfil["id"], outra["perfilId"]],
                [cena.conta["id"], outra["id"]])
    _studio_366(cena.dono.id)
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM metricas_studio_dias")).scalar() == 732
    hoje = hoje_sp()
    periodos = {"7d": {}, "90d": {"de": str(hoje - timedelta(days=89)), "ate": str(hoje)},
                "366d": {"de": str(hoje - timedelta(days=365)), "ate": str(hoje)}}
    tempos: dict[str, float] = {}
    for rotulo, params in periodos.items():
        for aba in ABAS:
            cena.ok(aba, **params)  # aquece
            t0 = time.perf_counter()
            corpo = cena.ok(aba, **params)
            tempos[f"{aba} ({rotulo})"] = time.perf_counter() - t0
            if rotulo == "366d":  # a coleta começou há ~120 dias: antes dela vale o Studio
                assert corpo["contexto"]["studio"]["series"] == 2
    print("\n" + "\n".join(f"{k}: {v * 1000:.0f} ms" for k, v in tempos.items()))
    lentas = {k: round(v, 2) for k, v in tempos.items() if v >= LIMITE_S}
    assert not lentas, f"acima de {LIMITE_S} s: {lentas}"


# ---- spec 022 (T050): o público ----

def test_previa_e_confirmar_do_publico_em_menos_de_1s(st):  # noqa: F811
    from integration.studio_helpers import csv_atividade, viewers_dias, zip_bytes, zip_viewers

    # 365 dias: sem ano, o mesmo dia e mês um ano depois seria o mesmo (dia, hora) repetido
    ate = local(1).date()
    dias_ = [ate - timedelta(days=364 - k) for k in range(365)]
    vw = viewers_dias(ate, [(100 + k % 50, 90, 10 + k % 50) for k in range(366)])
    arquivos = (("Followers_atavernanerd.zip",
                 zip_bytes({"FollowerActivity.csv": csv_atividade(dias_)})),
                zip_viewers(vw, H))
    st.previa_ok(*arquivos)  # aquece
    t0 = time.perf_counter()
    p = st.previa_ok(*arquivos)
    previa = time.perf_counter() - t0
    t0 = time.perf_counter()
    r = st.confirmar(p["previaId"])
    confirmar = time.perf_counter() - t0
    assert r.status_code == 201 and r.json()["gravados"] == 365 * 24 + 366
    print(f"\nprévia (público): {previa * 1000:.0f} ms; confirmar: {confirmar * 1000:.0f} ms")
    assert previa < 1.0 and confirmar < 1.0


def _publico_366(dono_id) -> None:
    """Um ano de atividade (24 h) e de espectadores e uma foto em cada série, por SQL."""
    with get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO metricas_studio_importacoes (id, serie_id, secoes, sha_atividade,"
            " sha_espectadores, sha_genero, data_foto, data_foto_origem, periodo_de,"
            " periodo_ate, ano_origem, contagens, criada_por)"
            " SELECT gen_random_uuid(), s.id, ARRAY['genero','atividade','espectadores'],"
            " md5(s.id::text || 'a'), md5(s.id::text || 'e'), md5(s.id::text || 'g'),"
            " CAST(:ate AS date), 'historico', CAST(:de AS date), CAST(:ate AS date),"
            " 'deduzido', '{}'::jsonb, :dono FROM metricas_series s"),
            {"de": hoje_sp() - timedelta(days=366), "ate": hoje_sp() - timedelta(days=1),
             "dono": dono_id})
        conn.execute(text(
            "INSERT INTO metricas_studio_atividade (importacao_id, serie_id, dia, hora, ativos)"
            " SELECT i.id, i.serie_id, i.periodo_de + (g - 1), h, (g * h) % 97"
            " FROM metricas_studio_importacoes i CROSS JOIN generate_series(1, 366) g"
            " CROSS JOIN generate_series(0, 23) h WHERE i.sha_atividade IS NOT NULL"))
        conn.execute(text(
            "INSERT INTO metricas_studio_espectadores (importacao_id, serie_id, dia, total,"
            " novos, recorrentes) SELECT i.id, i.serie_id, i.periodo_de + (g - 1), 100 + g,"
            " 90 + g, 10 FROM metricas_studio_importacoes i CROSS JOIN generate_series(1, 366) g"
            " WHERE i.sha_espectadores IS NOT NULL"))
        conn.execute(text(
            "INSERT INTO metricas_studio_distribuicoes (importacao_id, serie_id, tipo,"
            " data_foto, rotulo, pct) SELECT i.id, i.serie_id, 'genero', i.data_foto, r, 50"
            " FROM metricas_studio_importacoes i CROSS JOIN unnest(ARRAY['feminino',"
            " 'masculino']) r WHERE i.sha_genero IS NOT NULL"))
        conn.execute(text("ANALYZE metricas_studio_atividade; ANALYZE metricas_studio_espectadores"))


def test_publico_e_quando_postar_com_1_ano_e_10x_o_volume(cena):  # noqa: F811
    outra = cena.segunda_conta(outro_perfil=True)
    _semear_10x(cena.dono.id, [cena.perfil["id"], outra["perfilId"]],
                [cena.conta["id"], outra["id"]])
    _publico_366(cena.dono.id)
    hoje = hoje_sp()
    periodos = {"7d": {}, "366d": {"de": str(hoje - timedelta(days=365)), "ate": str(hoje)}}
    tempos: dict[str, float] = {}
    for rotulo, params in periodos.items():
        for aba in ("publico", "quando-postar"):
            cena.ok(aba, **params)  # aquece
            t0 = time.perf_counter()
            corpo = cena.ok(aba, **params)
            tempos[f"{aba} ({rotulo})"] = time.perf_counter() - t0
            if aba == "publico" and rotulo == "366d":
                assert all(c["atividade"]["diasComDado"] >= 365 for c in corpo["contas"])
    print("\n" + "\n".join(f"{k}: {v * 1000:.0f} ms" for k, v in tempos.items()))
    lentas = {k: round(v, 2) for k, v in tempos.items() if v >= LIMITE_S}
    assert not lentas, f"acima de {LIMITE_S} s: {lentas}"
