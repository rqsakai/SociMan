"""Garantias do guia na saída (spec 017, T027; research R6 e R7): hashtags fixas sempre, primeiro
e dentro do máximo de 8; palavras proibidas pedem a 2ª tentativa e, se ficarem, viram aviso;
emoji com "não usar" só avisa. Sem guia, nada muda (a 008 em `test_ia_saida.py`)."""

import pytest

from sociman_api.ia import saida
from sociman_api.ia.guia import GuiaEfetivo, aviso_fixas
from sociman_api.ia.saida import (
    PropostaGuia,
    PropostaLista,
    PropostaTexto,
    PropostaTextosPostagem,
    PropostaVariacoes,
    VariacaoPostagem,
)
from sociman_api.ia.tipos import TIPOS

TEXTOS = TIPOS["postagem.textos"]
FIXAS = GuiaEfetivo(hashtags_fixas=("#taverna", "#rpg"))


def _post(titulo="Rolou um 20 natural", descricao="Uma mesa épica.", hashtags=None):
    return PropostaTextosPostagem(titulo=titulo, descricao=descricao,
                                  hashtags=hashtags or ["#dnd", "#mesa", "#dados"],
                                  explicacao="ok", avisos=[])


def test_fixas_entram_primeiro_com_ajuste():
    v = saida.finalizar(TEXTOS, _post(hashtags=["#dnd", "#RPG", "#mesa"]), efetivo=FIXAS)
    assert v.proposta["hashtags"] == ["#taverna", "#rpg", "#dnd", "#mesa"]
    assert "hashtags_fixas_incluidas" in v.ajustes


def test_fixas_ja_presentes_nao_marcam_ajuste():
    v = saida.finalizar(TEXTOS, _post(hashtags=["#rpg", "#taverna", "#dnd"]), efetivo=FIXAS)
    assert v.proposta["hashtags"] == ["#taverna", "#rpg", "#dnd"]
    assert "hashtags_fixas_incluidas" not in v.ajustes


def test_corte_em_8_preserva_as_fixas():
    cinco = GuiaEfetivo(hashtags_fixas=tuple(f"#fixa{i}" for i in range(5)))
    modelo = [f"#tag{i}" for i in range(6)]
    assert saida.problemas(TEXTOS, _post(hashtags=modelo), efetivo=cinco) == [
        "são 6 hashtags além das fixas; o pedido é de no máximo 3"]
    v = saida.finalizar(TEXTOS, _post(hashtags=modelo), efetivo=cinco)
    assert v.proposta["hashtags"] == [*cinco.hashtags_fixas, "#tag0", "#tag1", "#tag2"]
    assert "hashtags_truncadas" in v.ajustes


def test_oito_fixas_sem_vaga_nao_pede_minimo():
    oito = GuiaEfetivo(hashtags_fixas=tuple(f"#fixa{i}" for i in range(8)),
                       max_hashtags_fixas=8)
    p = _post(hashtags=[])
    assert saida.problemas(TEXTOS, p, efetivo=oito) == []
    v = saida.finalizar(TEXTOS, _post(hashtags=["#extra"]), efetivo=oito)
    assert v.proposta["hashtags"] == list(oito.hashtags_fixas)


def test_minimo_conta_com_as_fixas():
    p = _post(hashtags=["#dnd"])
    assert saida.problemas(TEXTOS, p) != []  # sem guia: 1 hashtag é pouco
    assert saida.problemas(TEXTOS, p, efetivo=FIXAS) == []  # 2 fixas + 1 = 3


def test_lista_de_hashtags_com_fixas():
    tipo = TIPOS["postagem.hashtags"]
    parsed = PropostaLista(itens=["#dnd", "#taverna"], explicacao="", avisos=[])
    v = saida.finalizar(tipo, parsed, efetivo=FIXAS)
    assert v.proposta["itens"] == ["#taverna", "#rpg", "#dnd"]
    assert "hashtags_fixas_incluidas" in v.ajustes


@pytest.mark.parametrize("campo", ["titulo", "descricao", "hashtags"])
def test_proibida_em_cada_campo_da_postagem(campo):
    efetivo = GuiaEfetivo(proibidas=("Clickbait",))
    valores = {"titulo": "O CLÍCKBAIT do ano", "descricao": "Veja o clickbait.",
               "hashtags": ["#dnd", "#clickbait", "#mesa"]}
    p = _post(**{campo: valores[campo]})
    assert "usou a palavra proibida Clickbait" in saida.problemas(TEXTOS, p, efetivo=efetivo)
    v = saida.finalizar(TEXTOS, p, efetivo=efetivo)
    assert v.proibidas == ["Clickbait"]
    assert ("A proposta usa uma palavra proibida pelo guia (Clickbait); edite antes de "
            "aplicar.") in v.avisos


def test_proibida_em_item_de_lista_e_por_palavra_inteira():
    tipo = TIPOS["kit.bordoes"]
    efetivo = GuiaEfetivo(proibidas=("pix",))
    parsed = saida.PropostaSugestoes(itens=["Manda o pix!", "Pixel art"], explicacao="",
                                     avisos=[])
    v = saida.finalizar(tipo, parsed, efetivo=efetivo)
    assert v.proibidas == ["pix"]
    limpa = saida.PropostaSugestoes(itens=["Pixel art"], explicacao="", avisos=[])
    assert saida.finalizar(tipo, limpa, efetivo=efetivo).proibidas == []


def test_proibida_num_tipo_so_proibidas():
    tipo = TIPOS["avatar.descricao_prompt"]
    efetivo = GuiaEfetivo(proibidas=("logo",))
    parsed = PropostaTexto(proposta="A woman wearing a shirt with a LOGO.", explicacao="",
                           avisos=[])
    assert saida.problemas(tipo, parsed, efetivo=efetivo) == ["usou a palavra proibida logo"]
    assert saida.finalizar(tipo, parsed, efetivo=efetivo).proibidas == ["logo"]


def test_emoji_com_nao_usar_so_avisa():
    efetivo = GuiaEfetivo(emojis="nao")
    parsed = PropostaTexto(proposta="Achados baratos ✨", explicacao="", avisos=[])
    tipo = TIPOS["perfil.bio"]
    assert saida.problemas(tipo, parsed, efetivo=efetivo) == []
    v = saida.finalizar(tipo, parsed, efetivo=efetivo)
    assert any("emoji" in a for a in v.avisos) and v.proibidas == []
    livre = saida.finalizar(tipo, parsed, efetivo=GuiaEfetivo(emojis="livre"))
    assert not any("emoji" in a for a in livre.avisos)


def test_aviso_do_estado_invalido_herdado_so_em_hashtags():
    efetivo = GuiaEfetivo(hashtags_fixas=("#a", "#b"), max_hashtags_fixas=2,
                          avisos=(aviso_fixas(2),))
    v = saida.finalizar(TEXTOS, _post(), efetivo=efetivo)
    assert efetivo.avisos[0] in v.avisos
    bio = PropostaTexto(proposta="Bio", explicacao="", avisos=[])
    assert efetivo.avisos[0] not in saida.finalizar(TIPOS["perfil.bio"], bio,
                                                    efetivo=efetivo).avisos


def test_sem_guia_nada_muda():
    p = _post()
    assert saida.finalizar(TEXTOS, p).proposta == saida.finalizar(
        TEXTOS, p, efetivo=GuiaEfetivo()).proposta
    v = saida.finalizar(TEXTOS, p)
    assert v.proibidas == [] and "hashtags_fixas_incluidas" not in v.ajustes


# ---- formatos novos (US3) ----

def _variacoes(n=3, **kw):
    return PropostaVariacoes(variacoes=[
        VariacaoPostagem(titulo=f"Título {i}", descricao="Descrição.",
                         hashtags=kw.get("hashtags", ["#dnd", "#mesa", "#dados"]))
        for i in range(n)], explicacao="ok", avisos=[])


def test_variacoes_com_fixas_e_proibidas():
    tipo = TIPOS["guia.testar"]
    efetivo = GuiaEfetivo(hashtags_fixas=("#taverna",), proibidas=("dados",))
    assert "usou a palavra proibida dados" in saida.problemas(tipo, _variacoes(), efetivo=efetivo)
    v = saida.finalizar(tipo, _variacoes(), efetivo=efetivo)
    assert len(v.proposta["variacoes"]) == 3
    assert all(x["hashtags"][0] == "#taverna" for x in v.proposta["variacoes"])
    assert v.proibidas == ["dados"]


def test_variacoes_pede_exatamente_3():
    tipo = TIPOS["guia.testar"]
    assert saida.problemas(tipo, _variacoes(2)) == ["vieram 2 variações; o pedido é de 3"]
    v = saida.finalizar(tipo, _variacoes(4))
    assert len(v.proposta["variacoes"]) == 3


def _guia(**kw):
    dados = {"tom": "Direto.", "faca": ["Fale de você"], "nao_faca": [], "vocabulario": [],
             "proibidas": ["clickbait"], "emojis": "moderado", "emojis_preferidos": ["✨"],
             "explicacao": "ok", "avisos": []} | kw
    return PropostaGuia(**dados)


def test_guia_dentro_dos_limites():
    tipo = TIPOS["guia.montar"]
    assert saida.problemas(tipo, _guia()) == []
    v = saida.finalizar(tipo, _guia(faca=[" Fale de você ", "fale de VOCÊ", ""]))
    assert v.proposta == {"guia": {"tom": "Direto.", "faca": ["Fale de você"], "naoFaca": [],
                                   "vocabulario": [], "proibidas": ["clickbait"],
                                   "emojisPreferidos": ["✨"], "emojis": "moderado"}}


def test_guia_fora_dos_limites_pede_de_novo_e_corta_com_aviso():
    tipo = TIPOS["guia.montar"]
    longo = _guia(faca=[f"Regra {i}" for i in range(12)], tom="a" * 600)
    erros = saida.problemas(tipo, longo)
    assert "o tom passou de 500 caracteres" in erros
    assert "faca: são 12 itens; o máximo é 10" in erros
    v = saida.finalizar(tipo, longo)
    assert len(v.proposta["guia"]["faca"]) == 10 and len(v.proposta["guia"]["tom"]) <= 500
    assert any("Faça" in a for a in v.avisos) and any("tom" in a for a in v.avisos)


def test_guia_com_proibida_no_proprio_vocabulario_pede_de_novo():
    erros = saida.problemas(TIPOS["guia.montar"], _guia(vocabulario=["sem clickbait"]))
    assert "a palavra proibida clickbait aparece no próprio guia" in erros
