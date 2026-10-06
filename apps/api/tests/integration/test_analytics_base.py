"""Base do analytics (spec 019, T008): os posts do período (medida, características, vínculo,
hashtags, escopo, anônimas) e os ganhos no período, com cálculo de referência sobre a
semeadura."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from integration.analytics_helpers import cena, local  # noqa: F401
from sociman_api.analytics import base, filtros
from sociman_api.auth.deps import Actor
from sociman_api.canais.models import CanalDireito
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import FotoVideo, Serie, VideoRede
from sociman_api.perfis.models import Platform


def _filtro(c, **kw) -> filtros.Filtro:
    return filtros.montar(c.db, **kw)


def test_posts_com_a_medida_escolhida(cena):  # noqa: F811
    # 3 vídeos, um por dia a partir de 4 dias atrás às 10:00 (SP), 30 fotos horárias (todas no
    # passado): o i-ésimo tem views = 100·k·(i+1) na foto k (idade k h).
    s = cena.semear(videos=3, fotos=30, inicio=local(4, 10))
    h1 = base.posts(cena.db, _filtro(cena, medida="h1"))
    assert [p.video_id for p in h1] == s.videos
    assert [p.medida.valor for p in h1] == [100, 200, 300]
    assert not any(p.medida.aguardando or p.medida.estimado for p in h1)
    h24 = base.posts(cena.db, _filtro(cena, medida="h24"))
    assert [p.medida.valor for p in h24] == [2400, 4800, 7200]
    d7 = base.posts(cena.db, _filtro(cena, medida="d7"))
    assert all(p.medida.aguardando and p.medida.valor is None and not p.medido for p in d7)
    p = h1[0]
    assert (p.hora_local, p.dia_semana) == (10, local(4, 10).weekday())
    assert p.publicado_em.utcoffset() == timedelta(hours=-3)
    assert p.views_atual == 3000 and p.engajamento == pytest.approx((300 + 30 + 30) / 3000)
    assert (p.rotulo_conta, str(p.conta_id), p.anonima) == ("@atavernanerd", cena.conta["id"],
                                                            False)
    assert str(p.perfil_id) == cena.perfil["id"] and p.rede == Platform.tiktok
    assert p.titulo_curto == "Post de teste #fyp" and p.hashtags == ("fyp",)
    assert not p.vinculado and p.canal_fonte is None and p.padrao is None
    assert p.link and p.thumb_url is None
    ctx = base.contexto(_filtro(cena, medida="d7"), d7)
    assert (ctx.posts_no_periodo, ctx.aguardando, ctx.fora_do_sociman) == (3, 3, 3)


def test_sem_dado_nao_e_aguardando(cena):  # noqa: F811
    # 5 fotos horárias e vídeo com 3 dias: sem foto perto de 24 h → "sem dado"
    cena.semear(videos=1, fotos=5, inicio=local(3, 10))
    [p] = base.posts(cena.db, _filtro(cena))
    assert p.medida.valor is None and not p.medida.aguardando and not p.medido


def test_post_vinculado_traz_a_cadeia_do_sociman(cena):  # noqa: F811
    s = cena.semear(videos=2, fotos=30, inicio=local(2, 18),
                    legenda="Olha isso #Marvel #ação")
    canal = cena.canal(CanalDireito.parceiro, "Canal Parceiro")
    destino = cena.vincular(s.videos[0], canal=canal, hashtags=["#marvel", "Heróis"], score=88,
                            gancho="Ninguém esperava isso")
    a, b = base.posts(cena.db, _filtro(cena))
    assert a.vinculado and a.destino_id == destino.id and a.conteudo_id == destino.conteudo_id
    assert a.canal_fonte == base.CanalFonteRef(canal.id, "Canal Parceiro",
                                               CanalDireito.parceiro)
    assert a.padrao == {"clip_min_s": 15, "clip_max_s": 60, "layout": "auto"}
    assert (a.modo, a.score, a.gancho_caracteres) == ("lembrete", 88, len("Ninguém esperava isso"))
    # destino ∪ legenda, normalizadas e sem repetir
    assert a.hashtags == ("marvel", "herois", "acao")
    assert a.titulo_curto == "Olha isso #Marvel #ação"
    assert not b.vinculado and b.hashtags == ("marvel", "acao")
    ctx = base.contexto(_filtro(cena), [a, b])
    assert ctx.fora_do_sociman == 1


def test_escopo_por_perfil_conta_e_rede(cena):  # noqa: F811
    cena.semear(videos=2, fotos=3, inicio=local(2, 9))
    outra = cena.segunda_conta("outraconta", outro_perfil=True)
    cena.semear(outra, videos=1, fotos=3, inicio=local(1, 9))
    assert len(base.posts(cena.db, _filtro(cena))) == 3
    so_perfil = base.posts(cena.db, _filtro(cena, perfil_id=uuid.UUID(cena.perfil["id"])))
    assert {p.rotulo_conta for p in so_perfil} == {"@atavernanerd"} and len(so_perfil) == 2
    so_conta = base.posts(cena.db, _filtro(cena, conta_id=uuid.UUID(outra["id"])))
    assert [p.rotulo_conta for p in so_conta] == ["@outraconta"]
    assert base.posts(cena.db, _filtro(cena, rede=Platform.youtube)) == []
    assert len(base.posts(cena.db, _filtro(cena, rede=Platform.tiktok))) == 3
    # fora do período: nada
    assert base.posts(cena.db, _filtro(cena, de=local(30).date(), ate=local(20).date())) == []


def test_anonima_entra_rotulada_e_sem_identificador(cena):  # noqa: F811
    s = cena.semear(videos=1, fotos=30, inicio=local(2, 15))
    serie = cena.db.get(Serie, s.serie_id)
    anonimizar.serie(cena.db, serie, Actor(kind="user", user_id=cena.dono.id))
    cena.db.commit()
    [p] = base.posts(cena.db, _filtro(cena))
    assert p.anonima and p.conta_id is None and p.perfil_id is None
    assert p.rotulo_conta.startswith("Conta anônima ")
    assert p.link is None and p.hashtags == () and p.titulo_curto == "Vídeo anônimo"
    assert p.hora_local == 15 and p.medida.valor == 2400
    # filtrar por conta ou perfil tira a anônima
    assert base.posts(cena.db, _filtro(cena, conta_id=uuid.UUID(cena.conta["id"]))) == []
    assert base.posts(cena.db, _filtro(cena, perfil_id=uuid.UUID(cena.perfil["id"]))) == []
    ctx = base.contexto(_filtro(cena), [p])
    assert ctx.fora_do_sociman == 0  # anônima não conta como "fora do SociMan"


def test_ganhos_no_periodo(cena):  # noqa: F811
    # Publicado há 5 dias às 10:00 (SP), 30 fotos horárias (11:00 do dia até 16:00 do seguinte):
    # antes da meia-noite, a última foto é a k = 13 (23:00); a última de todas é a k = 30.
    s = cena.semear(videos=1, fotos=30, inicio=local(5, 10))
    [vid] = s.videos
    dia4 = local(4).date()
    f = _filtro(cena, de=dia4, ate=dia4)
    g = base.ganhos(cena.db, f)[vid]
    assert (g.views, g.likes, g.comments, g.shares) == (3000 - 1300, 300 - 130, 30 - 13, 17)
    # o anterior (dia 5) começa sem foto: ganho = a última foto do dia
    g5 = base.ganhos(cena.db, f, f.anterior)[vid]
    assert (g5.views, g5.likes) == (1300, 130)
    # depois da última foto: ganho 0; antes da primeira: o vídeo nem aparece
    hoje = local(0).date()
    assert base.ganhos(cena.db, _filtro(cena, de=hoje, ate=hoje))[vid].views == 0
    antes = local(6).date()
    assert vid not in base.ganhos(cena.db, _filtro(cena, de=antes, ate=antes))


def test_base_so_le(cena):  # noqa: F811
    cena.semear(videos=2, fotos=30, inicio=local(2, 10))
    contar = (lambda: (cena.db.scalar(select(func.count()).select_from(VideoRede)),
                       cena.db.scalar(select(func.count()).select_from(FotoVideo))))
    antes = contar()
    f = _filtro(cena)
    base.posts(cena.db, f)
    base.ganhos(cena.db, f)
    assert not cena.db.new and not cena.db.dirty and contar() == antes
