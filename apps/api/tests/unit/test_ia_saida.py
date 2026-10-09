"""Validação da saída por formato (spec 008, T010, R4)."""

import pytest

from sociman_api.ia.saida import (
    EXPLICACAO_MAX,
    Excluir,
    Invalida,
    PropostaLista,
    PropostaSugestoes,
    PropostaTexto,
    PropostaTextosPostagem,
    finalizar,
    problemas,
)
from sociman_api.ia.tipos import TIPOS


def _texto(proposta, explicacao="Mudei o tom.", avisos=()):
    return PropostaTexto(proposta=proposta, explicacao=explicacao, avisos=list(avisos))


def test_texto_no_limite_passa():
    tipo = TIPOS["avatar.tom_de_voz"]
    p = _texto("  Fala animada e direta.  ", avisos=["  ", "Encurtei."])
    assert problemas(tipo, p) == []
    v = finalizar(tipo, p)
    assert v.proposta == {"texto": "Fala animada e direta."} and not v.excede
    assert v.avisos == ["Encurtei."] and v.explicacao == "Mudei o tom."


def test_texto_acima_do_limite_volta_sem_corte_e_marcado():
    tipo = TIPOS["postagem.titulo"]
    p = _texto("a" * 130)
    assert "passou de 100" in problemas(tipo, p)[0]
    v = finalizar(tipo, p)
    assert v.excede and v.proposta["texto"] == "a" * 130
    assert "limite é 100" in v.avisos[-1]


def test_prompt_de_imagem_sem_trim():
    tipo = TIPOS["avatar.descricao_prompt"]
    v = finalizar(tipo, _texto("  A woman in her 30s.\n"))
    assert v.proposta["texto"] == "  A woman in her 30s.\n"


def test_texto_vazio_e_uma_linha():
    with pytest.raises(Invalida):
        finalizar(TIPOS["perfil.bio"], _texto("   "))
    assert problemas(TIPOS["perfil.bio"], _texto(" ")) == ["a proposta veio vazia"]
    tipo = TIPOS["asset.nome"]
    assert problemas(tipo, _texto("Cozinha\nclara")) == ["a proposta precisa ser uma linha só"]
    v = finalizar(tipo, _texto("Cozinha\n clara"))
    assert v.proposta["texto"] == "Cozinha clara" and "uma_linha" in v.ajustes


def test_explicacao_cortada_na_frase_e_avisos_limitados():
    longa = "Frase curta. " * 60
    v = finalizar(TIPOS["perfil.bio"], _texto("Bio.", explicacao=longa, avisos=["x"] * 9))
    assert len(v.explicacao) <= EXPLICACAO_MAX and v.explicacao.endswith(".")
    assert len(v.avisos) == 5


def _sug(*itens):
    return PropostaSugestoes(itens=list(itens), explicacao="", avisos=[])


def test_sugestoes_removem_vazias_repetidas_e_as_ja_vistas():
    tipo = TIPOS["kit.bordoes"]
    excluir = Excluir(atuais=("Bora testar?",), aceitos=("Partiu!",), rejeitados=("Olha só",))
    p = _sug("Novo 1", " ", "novo 1", "BORA TESTAR? ", "partiu!", "olha só", "Novo 2")
    assert problemas(tipo, p, excluir) == []
    v = finalizar(tipo, p, excluir)
    assert v.proposta == {"itens": ["Novo 1", "Novo 2"]}
    texto = " ".join(v.avisos)
    assert "vazia" in texto and "repetida" in texto and "já vistas" in texto


def test_sugestoes_cortam_em_10_e_marcam_as_longas():
    tipo = TIPOS["kit.series"]
    v = finalizar(tipo, _sug(*[f"Série {i}" for i in range(12)]))
    assert len(v.proposta["itens"]) == 10 and "10 primeiras" in v.avisos[-1]
    p = _sug("Curta", "x" * 61)
    assert "60 caracteres" in problemas(tipo, p)[0]
    v = finalizar(tipo, p)
    assert v.excede and v.proposta["itens"] == ["Curta", "x" * 61]


def test_sugestoes_sem_nenhuma_valida_e_invalida():
    tipo = TIPOS["kit.bordoes"]
    p = _sug("Bora testar?", "")
    excluir = Excluir(atuais=("bora testar?",))
    assert problemas(tipo, p, excluir)
    with pytest.raises(Invalida):
        finalizar(tipo, p, excluir)


def test_hashtags_normalizadas_truncadas_e_invalidas():
    tipo = TIPOS["postagem.hashtags"]
    p = PropostaLista(itens=["Dica De Hoje!", "#dica", "#a", "#b", "#c", "#d", "#e", "#f",
                             "#g", "#h"], explicacao="", avisos=[])
    assert problemas(tipo, p)  # 10 > 8: pede outra tentativa
    v = finalizar(tipo, p)
    assert v.proposta["itens"][0] == "#dicadehoje" and len(v.proposta["itens"]) == 8
    assert {"hashtags_normalizadas", "hashtags_truncadas"} <= set(v.ajustes)
    with pytest.raises(Invalida):
        finalizar(tipo, PropostaLista(itens=["#a", "!!"], explicacao="", avisos=[]))


def test_textos_postagem_com_o_ajuste_da_006():
    tipo = TIPOS["postagem.textos"]
    p = PropostaTextosPostagem(titulo="palavra " * 20, descricao="Desc.",
                               hashtags=["#A", "b", "#c"], explicacao="Ok.", avisos=[])
    assert "título passou" in problemas(tipo, p)[0]
    v = finalizar(tipo, p)
    assert len(v.proposta["titulo"]) <= 100 and "titulo_cortado" in v.ajustes
    assert v.proposta["hashtags"] == ["#a", "#b", "#c"]
    with pytest.raises(Invalida):
        finalizar(tipo, PropostaTextosPostagem(titulo="T", descricao="", hashtags=["#a"],
                                               explicacao="", avisos=[]))
