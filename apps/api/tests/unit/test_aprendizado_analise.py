"""Análise do aprendizado sobre posts em memória (spec 023, T027; SC-003; R1 a R4): blocos de
hashtags, "não separável", "quase só com", conta travada, em alta e posts sem vínculo."""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sociman_api.analytics.base import CanalFonteRef, MedidaPost, PostAnalisado
from sociman_api.aprendizado import analise as an
from sociman_api.aprendizado import fatores as fat
from sociman_api.aprendizado import recomendacoes as rec
from sociman_api.canais.models import CanalDireito
from sociman_api.perfis.models import Platform

P = uuid.UUID("11111111-1111-4111-8111-111111111111")
A = uuid.UUID("22222222-2222-4222-8222-222222222222")
B = uuid.UUID("33333333-3333-4333-8333-333333333333")
MARVEL = uuid.UUID("44444444-4444-4444-8444-444444444444")
GAMES = uuid.UUID("55555555-5555-4555-8555-555555555555")
TEMAS = {MARVEL: "Marvel", GAMES: "Games"}
AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
TZ = ZoneInfo("America/Sao_Paulo")


def post(conta=A, dias=1, views=100, hora=12, tags=(), dur=30, vinc=False, gancho=None,
         modo=None, canal=None) -> PostAnalisado:
    local = (AGORA.astimezone(TZ) - timedelta(days=dias)).replace(hour=hora, minute=0)
    return PostAnalisado(
        video_id=uuid.uuid4(), serie_id=conta, conta_id=conta, perfil_id=P,
        rotulo_conta="@a" if conta == A else "@b", rede=Platform.tiktok, anonima=False,
        publicado_em=local, hora_local=hora, dia_semana=local.weekday(), duracao_s=dur,
        titulo_curto="Post", link=None, thumb_url=None,
        medida=MedidaPost(float(views), False, False), views_atual=views, engajamento=None,
        hashtags=tuple(tags), vinculado=vinc, modo=modo, gancho_caracteres=gancho,
        canal_fonte=canal)


def calc(medidos, estag=(), classes=None, temas=None) -> an.Resultado:
    return an.computar(P, None, "h24", date(2026, 4, 10), date(2026, 10, 6), None, medidos,
                       set(estag), temas if temas is not None else {}, classes or {}, set(),
                       AGORA)


def classes(posts_temas) -> dict:
    return {p.video_id: fat.ClassInfo(t, "pergunta") for p, t in posts_temas}


def efeito(res, fator, valor, parte="rendimento") -> an.Efeito:
    e = an.efeito_de(res, fator, valor, parte)
    assert e is not None, (fator, valor, parte, [(x.fator, x.valor) for x in res.efeitos])
    return e


def test_hashtags_sempre_juntas_viram_um_bloco():
    com = [post(dias=d, views=1000, tags=("multiversomarvel", "vingadoresdoomsday", "geek"))
           for d in range(1, 11)]
    sem = [post(dias=d, views=100) for d in range(11, 21)]
    res = calc(com + sem)
    [bloco] = res.blocos
    assert bloco.hashtags == ("multiversomarvel", "vingadoresdoomsday", "geek")
    assert len(bloco.posts) == 10
    hashtags = {e.valor for e in res.efeitos if e.fator == "hashtag"}
    assert hashtags == {"multiversomarvel+vingadoresdoomsday+geek"}  # contado uma vez
    e = efeito(res, "hashtag", bloco.valor)
    assert e.n_posts == 10 and e.n_dias == 10 and e.efeito > 1
    assert e.confianca in ("forte", "moderada")


def test_hashtag_so_no_tema_fica_nao_separavel():
    marvel = [post(dias=d, views=1000, tags=("marvel",)) for d in range(1, 11)]
    games = [post(dias=d, views=100) for d in range(11, 21)]
    res = calc(marvel + games, classes=classes([(p, MARVEL) for p in marvel]
                                               + [(p, GAMES) for p in games]), temas=TEMAS)
    e = efeito(res, "hashtag", "marvel")
    assert e.theta is None and e.efeito is None and e.confianca == "indicio"
    [aviso] = e.avisos
    assert aviso.tipo == "nao_separavel" and aviso.tema_nome == "Marvel"
    assert ("marvel", MARVEL, 10) in res.matriz
    assert rec.regras(res.efeitos, None) == [] or all(
        c.tipo != "hashtag_fixar" for c in rec.regras(res.efeitos, None))


def test_hashtag_separavel_dentro_do_tema():
    marvel = ([post(dias=d, views=3000, tags=("dica",)) for d in range(1, 5)]
              + [post(dias=d, views=1000) for d in range(5, 11)])
    games = ([post(dias=d, views=300, tags=("dica",)) for d in range(11, 15)]
             + [post(dias=d, views=100) for d in range(15, 21)])
    res = calc(marvel + games, classes=classes([(p, MARVEL) for p in marvel]
                                               + [(p, GAMES) for p in games]), temas=TEMAS)
    e = efeito(res, "hashtag", "dica")
    assert not e.tem("nao_separavel") and e.theta is not None and e.theta > 0


def test_tema_quase_so_num_horario():
    marvel = [post(dias=d, views=1000, hora=18) for d in range(1, 9)]
    games_18 = [post(dias=d, views=1000, hora=18) for d in range(9, 13)]
    games_9 = [post(dias=d, views=100, hora=9) for d in range(13, 21)]
    res = calc(marvel + games_18 + games_9,
               classes=classes([(p, MARVEL) for p in marvel]
                               + [(p, GAMES) for p in games_18 + games_9]), temas=TEMAS)
    faixa = efeito(res, "faixa_horario", "18")
    assert faixa.confianca in ("forte", "moderada")
    tema = efeito(res, "tema", str(MARVEL))
    quase = [a for a in tema.avisos if a.tipo == "quase_so_com"]
    assert quase and quase[0].fator == "faixa_horario" and quase[0].valor == "18"
    assert not [c for c in rec.regras(res.efeitos, None) if c.tipo == "tema_ampliar"]


def test_conta_travada_vira_indicio_e_sem_recomendacao():
    altos = [post(conta=B, dias=d, views=1000, tags=("geek",)) for d in range(1, 7)]
    baixos = [post(conta=B, dias=d, views=1, tags=("geek",) if d % 2 else ())
              for d in range(7, 21)]
    res = calc(altos + baixos, estag={p.video_id for p in baixos})
    [conta] = res.contas
    assert conta.travada and conta.estagnados == 14 and res.travadas == [B]
    rend = [e for e in res.efeitos if e.parte == "rendimento" and e.theta is not None]
    assert rend and all(e.confianca == "indicio" and e.tem("travada") for e in rend)
    entrega = [e for e in res.efeitos if e.parte == "entrega" and e.theta is not None]
    assert entrega and not any(e.tem("travada") for e in entrega)  # a parte A continua
    assert rec.regras(res.efeitos, B, conta_travada=True) == []


def test_tema_em_alta():
    recentes = [post(dias=d, views=3000) for d in range(1, 7)]
    antigos = [post(dias=d, views=300) for d in range(40, 46)]
    outros = [post(dias=d, views=300) for d in (*range(7, 13), *range(46, 52))]
    marvel = recentes + antigos
    res = calc(marvel + outros, classes=classes([(p, MARVEL) for p in marvel]
                                                + [(p, GAMES) for p in outros]), temas=TEMAS)
    e = efeito(res, "tema", str(MARVEL))
    assert e.tem("em_alta") and not e.tem("em_queda")


def test_puxado_por_1_post():
    anime = [post(dias=d, views=v) for d, v in zip(range(1, 6), (100, 100, 100, 100, 50000),
                                                   strict=True)]
    outros = [post(dias=d, views=100) for d in range(6, 21)]
    res = calc(anime + outros, classes=classes([(p, MARVEL) for p in anime]
                                               + [(p, GAMES) for p in outros]), temas=TEMAS)
    e = efeito(res, "tema", str(MARVEL))
    [aviso] = [a for a in e.avisos if a.tipo == "puxado_por_1"]
    # sem o viral, o tema fica abaixo do típico da conta (que o viral também puxou)
    assert aviso.sem_maior is not None and aviso.sem_maior < 1 < e.efeito
    assert not [c for c in rec.regras(res.efeitos, None) if c.tipo == "tema_ampliar"]


def test_post_sem_vinculo_fora_dos_fatores_de_corte():
    canal = CanalFonteRef(uuid.uuid4(), "Canal", CanalDireito.proprio)
    vinc = post(vinc=True, gancho=30, modo="lembrete", canal=canal)
    solto = post(vinc=False, gancho=30, modo="lembrete")
    nomes = {f.fator for f in fat.de_post(vinc, None, {})}
    assert {"gancho_tamanho", "modo", "canal_fonte", "duracao"} <= nomes
    nomes = {f.fator for f in fat.de_post(solto, None, {})}
    assert not {"gancho_tamanho", "modo", "canal_fonte"} & nomes
    assert {"duracao", "faixa_horario", "dia_semana"} <= nomes


def test_conta_com_poucos_posts_fora_dos_efeitos():
    res = calc([post(dias=d, views=100) for d in range(1, 10)])
    [conta] = res.contas
    assert not conta.suficiente and res.posts == [] and res.efeitos == []
