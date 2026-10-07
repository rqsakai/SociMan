"""Regras das recomendações (spec 023, T037; SC-004; FR-035, FR-038): nenhuma nasce de amostra
pequena, de "não separável", de "puxado por 1" sem efeito restante nem de conta travada; a
rejeitada só volta com o n dobrado ou outra faixa."""

import uuid
from types import SimpleNamespace

from sociman_api.aprendizado import recomendacoes as rec
from unit.test_aprendizado_analise import GAMES, MARVEL, TEMAS, calc, classes, post


def _cena(n_marvel=10, views_marvel=3000, n_games=10):
    marvel = [post(dias=d, views=views_marvel, tags=("dica",) if d % 2 else ())
              for d in range(1, n_marvel + 1)]
    games = [post(dias=d, views=100, tags=("dica",) if d % 2 else ())
             for d in range(n_marvel + 1, n_marvel + n_games + 1)]
    return calc(marvel + games, classes=classes([(p, MARVEL) for p in marvel]
                                                + [(p, GAMES) for p in games]), temas=TEMAS)


def test_tema_que_rende_vira_ampliar_com_chave_estavel():
    res = _cena()
    candidatas = {c.tipo: c for c in rec.regras(res.efeitos, None)}
    amp = candidatas["tema_ampliar"]
    assert amp.chave == f"tema_ampliar:perfil:{MARVEL}" and amp.alvo.tema_id == MARVEL
    assert amp.efeito.confianca in ("forte", "moderada") and amp.efeito.efeito >= 1.5
    assert "Marvel" in amp.motivo
    conta = uuid.uuid4()
    assert {c.chave for c in rec.regras(res.efeitos, conta)} >= {
        f"tema_ampliar:conta:{conta}:{MARVEL}"}
    assert rec.regras(res.efeitos, None) == rec.regras(res.efeitos, None)  # determinístico


def test_amostra_pequena_nao_recomenda():
    res = _cena(n_marvel=4, n_games=12)
    assert not [c for c in rec.regras(res.efeitos, None) if c.alvo.tema_id == MARVEL]


def test_nao_separavel_nao_vira_fixar():
    marvel = [post(dias=d, views=3000, tags=("marvel",)) for d in range(1, 11)]
    games = [post(dias=d, views=100) for d in range(11, 21)]
    res = calc(marvel + games, classes=classes([(p, MARVEL) for p in marvel]
                                               + [(p, GAMES) for p in games]), temas=TEMAS)
    assert not [c for c in rec.regras(res.efeitos, None) if c.tipo.startswith("hashtag_")]


def test_conta_travada_nao_recomenda():
    assert rec.regras(_cena().efeitos, uuid.uuid4(), conta_travada=True) == []


def test_rejeitada_so_volta_com_n_dobrado_ou_outra_faixa():
    amp = next(c for c in rec.regras(_cena().efeitos, None) if c.tipo == "tema_ampliar")
    n, faixa = amp.efeito.n_posts, amp.efeito.confianca
    assert not rec.reaparece(amp, SimpleNamespace(n_decisao=n, faixa_decisao=faixa))
    assert rec.reaparece(amp, SimpleNamespace(n_decisao=n // 2, faixa_decisao=faixa))
    assert rec.reaparece(amp, SimpleNamespace(n_decisao=n, faixa_decisao="fraca"))
