"""Plano v2 do vídeo guiado (spec 031, T023, research R4 e R7): a estrutura (`problemas_v2`) e o
que depende do roteiro (`problemas_contexto`: a soma, o orçamento e o nível do reuso), mais os
formatos do chat (`perguntas_roteiro`, `ajuste_roteiro`). Puro."""

from sociman_api.ia import saida
from sociman_api.ia.tipos import TIPOS
from sociman_api.roteiros import formatos, plano

CENA = "11111111-1111-4111-8111-111111111111"
OUTRA = "22222222-2222-4222-8222-222222222222"


def _nova(trechos: int = 1, quadros: int | None = None) -> dict:
    n = trechos + 1 if quadros is None else quadros
    return {"nome": "Cena nova", "acao": "She shows the dress", "plano": "medio",
            "movimento": "parada", "camera": None, "motor": "minimax",
            "quadros": [f"state {i}" for i in range(n)]}


def _pos(frases: list[int], trechos: int = 1, cena_id: str | None = None,
         nivel: str | None = None, **nova) -> dict:
    return {"cena_id": cena_id, "nivel": nivel, "trechos": trechos, "frases": frases,
            "motivo": "Serve.", "nova": None if cena_id else _nova(trechos, **nova)}


def _plano(posicoes: list[dict], frases: list[str] | None = None) -> plano.PlanoSaidaV2:
    frases = frases or [f"Frase curta {i}." for i in range(len(posicoes))]
    return plano.PlanoSaidaV2.model_validate({"frases": frases, "posicoes": posicoes,
                                              "explicacao": "", "avisos": []})


CTX = plano.ContextoV2(base=5, alvo=10, candidatas=(
    plano.CandidataV2(id=CENA, nome="Cena total", acao="x", plano=None, nivel="total",
                      trechos=1),
    plano.CandidataV2(id=OUTRA, nome="Outro avatar", acao="x", plano=None, nivel="plano",
                      trechos=2),
))


def test_plano_valido_passa():
    p = _plano([_pos([1]), _pos([2], cena_id=CENA, nivel="total")])
    assert plano.problemas_v2(p) == [] and plano.problemas_contexto(p, CTX) == []
    prop = plano.proposta_v2(p)["plano"]
    assert prop["versao"] == 2 and prop["posicoes"][1]["frases"] == [1]
    assert prop["posicoes"][1]["nivel"] == "total"


def test_soma_diferente_da_duracao():
    p = _plano([_pos([1], trechos=1)])
    assert any("soma das cenas dá 5 s" in e for e in plano.problemas_contexto(p, CTX))


def test_posicao_acima_do_orcamento():
    p = _plano([_pos([1]), _pos([2])], frases=["x" * 60, "curta"])
    erros = plano.problemas_contexto(p, CTX)
    assert erros == ["cena 1: a fala tem 60 caracteres e cabem 59"]


def test_trechos_fora_de_1_a_3():
    p = _plano([_pos([1], trechos=4, quadros=5), _pos([2])])
    assert any("trechos vai de 1 a 3" in e for e in plano.problemas_v2(p))


def test_quadros_diferente_de_trechos_mais_um():
    p = _plano([_pos([1], trechos=2, quadros=2)])
    assert any("pedem 3 quadros, vieram 2" in e for e in plano.problemas_v2(p))


def test_reuso_total_de_cena_nao_candidata_total():
    p = _plano([_pos([1], trechos=2, cena_id=OUTRA, nivel="total")])
    assert any("reuso total só vale" in e for e in plano.problemas_contexto(p, CTX))


def test_cena_fora_das_candidatas_e_de_outro_produto():
    """A cena de outro produto nunca está em `<cenas>` (FR-024): reaproveitá-la é recusado."""
    p = _plano([_pos([1], trechos=2, cena_id="33333333-3333-4333-8333-333333333333",
                     nivel="plano")])
    assert any("não está em <cenas>" in e for e in plano.problemas_contexto(p, CTX))


def test_reuso_sem_nivel_e_os_dois_ao_mesmo_tempo():
    pos = _pos([1], trechos=2, cena_id=CENA)
    pos["nova"] = _nova(2)
    erros = plano.problemas_v2(_plano([pos]))
    assert any("um dos dois" in e for e in erros) and any("nivel do reuso" in e for e in erros)


def test_saida_do_formato_v2_pede_a_segunda_tentativa():
    tipo = TIPOS["roteiro.plano_guiado"]
    assert tipo.formato == "plano_roteiro_v2" and saida.SCHEMAS[tipo.formato] is plano.PlanoSaidaV2
    ruim = _plano([_pos([1], trechos=2, quadros=2)])
    assert saida.problemas(tipo, ruim)
    ok = saida.finalizar(tipo, _plano([_pos([1], trechos=2)]))
    assert ok.proposta["plano"]["versao"] == 2


def test_perguntas_limites_e_slugs():
    tipo = TIPOS["roteiro.perguntas"]
    p = formatos.PerguntasSaida.model_validate({"perguntas": [
        {"id": "Foco Principal", "texto": "Qual foco?", "multipla": True,
         "opcoes": [{"id": "Caimento", "rotulo": "Caimento"}, {"id": "preço", "rotulo": "Preço"}],
         "exemplos": ["mostrar o caimento"]}], "explicacao": "", "avisos": []})
    assert saida.problemas(tipo, p) == []
    q = saida.finalizar(tipo, p).proposta["perguntas"][0]
    assert q["id"] == "foco_principal" and [o["id"] for o in q["opcoes"]] == ["caimento", "preco"]
    uma = formatos.PerguntasSaida.model_validate({"perguntas": [
        {"id": "a", "texto": "?", "multipla": False, "opcoes": [{"id": "x", "rotulo": "X"}],
         "exemplos": []}] * 6, "explicacao": "", "avisos": []})
    erros = formatos.problemas_perguntas(uma)
    assert any("de 1 a 5 perguntas" in e for e in erros)
    assert any("de 2 a 6 opções" in e for e in erros)


def test_ajuste_pergunta_ou_mudanca():
    tipo = TIPOS["roteiro.ajuste"]
    perg = formatos.AjusteSaida.model_validate({
        "tipo": "pergunta", "mudanca": None, "resumo": "?", "explicacao": "", "avisos": [],
        "pergunta": {"id": "x", "texto": "O quê?", "multipla": False, "exemplos": [],
                     "opcoes": [{"id": "a", "rotulo": "A"}, {"id": "b", "rotulo": "B"}]}})
    assert saida.finalizar(tipo, perg).proposta["ajuste"]["tipo"] == "pergunta"
    rapida = formatos.AjusteSaida.model_validate({
        "tipo": "mudanca", "pergunta": None, "resumo": "Mais animada", "explicacao": "",
        "avisos": [], "mudanca": {"alvo": {"tipo": "narracao", "ordem": None, "quadro": None,
                                           "trecho": None},
                                  "quadros": [], "acao": None, "motor": None,
                                  "velocidade": 1.5, "frases": [], "trechos": None}})
    assert "a velocidade vai de 0.90 a 1.20" in saida.problemas(tipo, rapida)


def test_regra_da_grade_faz_a_conta_na_tag():
    """T059 (2026-10-16): com "2 trechos" o modelo propunha 3 cenas de 1 trecho (15 s para um
    vídeo de 10 s), duas vezes seguidas. A tag <grade> e as regras passam a dizer a soma."""
    assert plano._regra_da_grade(1).startswith("uma só cena")
    r2 = plano._regra_da_grade(2)
    assert "exatamente 2" in r2 and "2 cenas com trechos=1" in r2 and "nunca mais de 2 cenas" in r2
    assert "2+1 ou 1+2" in plano._regra_da_grade(3)
    assert "de 2 a 6 cenas" in plano._regra_da_grade(6)
    assert "some os trechos" in plano.REGRAS_V2 and "nunca 3 cenas" in plano.REGRAS_V2
    assert TIPOS["roteiro.plano_guiado"].padrao_versao == 2
