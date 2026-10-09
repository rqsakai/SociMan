"""Regras de insight (spec 019, T024; research R6): faixa de 3 h, dia, duração, canal, hashtag e
destaque > 3×. Vencedor ≥ 1,3× com `MIN_GRUPO`; abaixo do mínimo, `pendente` com o que falta.
Puro: os posts são montados à mão."""

import uuid
from datetime import UTC, datetime

import pytest

from sociman_api.analytics.base import CanalFonteRef, MedidaPost, PostAnalisado
from sociman_api.analytics.insights import faixa_duracao, faixa_horario, regras, vezes
from sociman_api.canais.models import CanalDireito
from sociman_api.perfis.models import Platform

CANAL = CanalFonteRef(uuid.uuid4(), "Canal Bom", CanalDireito.parceiro)


def post(valor: float | None, *, hora: int = 9, dia: int = 0, duracao: int = 45,
         canal: CanalFonteRef | None = None, hashtags: tuple[str, ...] = (),
         aguardando: bool = False, titulo: str = "Post") -> PostAnalisado:
    return PostAnalisado(
        video_id=uuid.uuid4(), serie_id=uuid.uuid4(), conta_id=uuid.uuid4(), perfil_id=None,
        rotulo_conta="@x", rede=Platform.tiktok, anonima=False,
        publicado_em=datetime(2026, 9, 28, hora, tzinfo=UTC), hora_local=hora,
        dia_semana=dia, duracao_s=duracao, titulo_curto=titulo, link=None, thumb_url=None,
        medida=MedidaPost(None if aguardando else valor, False, aguardando),
        views_atual=None, engajamento=None, hashtags=hashtags, vinculado=canal is not None,
        canal_fonte=canal)


def _regra(insights, nome):
    [i] = [i for i in insights if i.regra == nome]
    return i


def test_seis_regras_na_ordem():
    assert [i.regra for i in regras([])] == ["horario", "dia", "duracao", "canal", "hashtag",
                                             "destaque"]
    assert all(i.pendente for i in regras([]))


def test_faixas_e_formato():
    assert [faixa_horario(h) for h in (0, 2, 18, 20, 23)] == [
        "0h–3h", "0h–3h", "18h–21h", "18h–21h", "21h–24h"]
    assert [faixa_duracao(s) for s in (5, 30, 31, 60, 61)] == [
        "até 30 s", "até 30 s", "31–60 s", "31–60 s", "mais de 60 s"]
    assert vezes(2.345) == "2,3×" and vezes(1.3) == "1,3×"


def test_melhor_faixa_de_horario():
    # 5 posts às 18–20 h com 300 e 5 às 9 h com 100: geral = 200, faixa 18h–21h = 1,5×
    posts = [post(300, hora=18 + k % 3) for k in range(5)] + [post(100, hora=9)] * 5
    i = _regra(regras(posts), "horario")
    assert not i.pendente and i.grupo == "18h–21h" and i.valor == pytest.approx(1.5)
    assert "entre 18h e 21h" in i.frase and "1,5×" in i.frase and "em 24 h" in i.frase
    assert (i.amostra.n, i.amostra.minimo, i.amostra.suficiente) == (5, 5, True)


def test_abaixo_do_minimo_diz_quanto_falta():
    i = _regra(regras([post(100)] * 4), "horario")
    assert i.pendente and i.valor is None and "falta 1 post" in i.frase
    assert (i.amostra.n, i.amostra.faltam, i.amostra.suficiente) == (4, 1, False)
    # geral suficiente, mas nenhum grupo com 5: o que falta é no maior grupo
    i = _regra(regras([post(100, hora=9)] * 3 + [post(300, hora=18)] * 3), "horario")
    assert i.pendente and "faltam 2 posts" in i.frase and i.amostra.n == 3


def test_razao_abaixo_de_1_3_nao_vira_insight():
    posts = [post(120, hora=18)] * 5 + [post(100, hora=9)] * 5  # 120 / 110 ≈ 1,09×
    i = _regra(regras(posts), "horario")
    assert i.pendente and i.amostra.suficiente and "Nenhum grupo se destacou" in i.frase
    assert i.valor == pytest.approx(120 / 110)


def test_melhor_dia_da_semana():
    posts = [post(500, dia=5)] * 5 + [post(100, dia=1)] * 5  # geral 300 → 1,7×
    i = _regra(regras(posts), "dia")
    assert not i.pendente and i.grupo == "sábado" and "no sábado" in i.frase
    posts = [post(500, dia=1)] * 5 + [post(100, dia=5)] * 5
    assert "na terça" in _regra(regras(posts), "dia").frase


def test_faixa_de_duracao():
    posts = [post(400, duracao=25)] * 5 + [post(100, duracao=90)] * 5  # geral 250 → 1,6×
    i = _regra(regras(posts), "duracao")
    assert not i.pendente and i.grupo == "até 30 s" and i.valor == pytest.approx(1.6)


def test_canal_fonte():
    posts = [post(400, canal=CANAL)] * 5 + [post(100)] * 5  # geral 250 → 1,6×
    i = _regra(regras(posts), "canal")
    assert not i.pendente and i.grupo == "Canal Bom" and "Canal Bom" in i.frase
    assert i.valor == pytest.approx(1.6)
    assert _regra(regras([post(400, canal=CANAL)] * 4 + [post(100)] * 6), "canal").pendente


def test_hashtag_com_maior_lift():
    posts = ([post(500, hashtags=("marvel", "fyp"))] * 5 + [post(100, hashtags=("fyp",))] * 5
             + [post(900, hashtags=("rara",))] * 2)
    # geral (12 posts) = 500; marvel = 500 (1,0×), fyp = 300, rara n = 2 → nenhum ≥ 1,3×
    i = _regra(regras(posts), "hashtag")
    assert i.pendente and i.grupo == "#marvel"
    posts = [post(600, hashtags=("marvel",))] * 5 + [post(100)] * 5  # geral 350 → 1,7×
    i = _regra(regras(posts), "hashtag")
    assert not i.pendente and i.grupo == "#marvel" and "#marvel" in i.frase
    assert i.valor == pytest.approx(600 / 350)


def test_destaque_acima_de_3x():
    posts = [post(100)] * 4 + [post(1000, titulo="O viral")]
    i = _regra(regras(posts), "destaque")
    assert not i.pendente and i.grupo == "O viral" and i.valor == pytest.approx(10)
    assert "“O viral”" in i.frase and "10,0×" in i.frase
    i = _regra(regras([post(100)] * 4 + [post(300)]), "destaque")  # 3× exato não passa
    assert i.pendente and i.amostra.suficiente
    i = _regra(regras([post(100)] * 3 + [post(1000)]), "destaque")
    assert i.pendente and "falta 1 post" in i.frase


def test_aguardando_fica_fora():
    posts = [post(300, hora=18)] * 5 + [post(100, hora=9)] * 5 + \
        [post(None, hora=3, aguardando=True)] * 10
    i = _regra(regras(posts, "h1"), "horario")
    assert not i.pendente and i.valor == pytest.approx(1.5) and "em 1 h" in i.frase
