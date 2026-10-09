"""Domínio puro do cadastro padronizado (spec 025, T008; research R5–R8)."""

import pytest

from sociman_api.assets import padrao

TODOS = set(padrao.SLOTS_AVATAR)


def _notas(**sobre: int) -> dict:
    return {"notas": {s: {"nota": sobre.get(s, 8), "observacao": "ok"}
                      for s in padrao.SLOTS_NOTA}}


@pytest.mark.parametrize(("slots", "identidade", "esperado"), [
    (set(), None, "incompleto"),
    (TODOS - {"corpo_base"}, None, "incompleto"),
    (TODOS, None, "incompleto"),
    (TODOS, _notas(), "completo"),
    (TODOS, _notas(rosto_34_dir=7), "completo"),
    (TODOS, _notas(corpo_base=6), "atencao"),
    (TODOS - {"rosto_frontal"}, _notas(), "incompleto"),
])
def test_situacao_do_avatar(slots, identidade, esperado):
    assert padrao.situacao("avatar", slots, identidade) == esperado


def test_situacao_do_cenario():
    assert padrao.situacao("cenario", set(), None) == "incompleto"
    assert padrao.situacao("cenario", {"cena"}, None) == "completo"


def test_passos_abrem_em_ordem():
    def abertos(slots):
        return {p for p in padrao.PASSOS if padrao.passo_aberto(p, slots)[0]}

    assert abertos(set()) == {"avatar.rosto_origem", "cenario.cena"}
    assert "avatar.rosto_frontal" in abertos({"rosto_origem"})
    assert "avatar.rostos_34" not in abertos({"rosto_origem"})
    assert "avatar.corpo_base" in abertos({"rosto_origem", "rosto_frontal", "rosto_34_esq",
                                           "rosto_34_dir"})
    assert "avatar.identidade" in abertos(TODOS)
    assert {"avatar.look", "avatar.pose"} <= abertos({"rosto_frontal", "corpo_base"})
    assert "cenario.variacao" in abertos({"cena"})
    aberto, motivo = padrao.passo_aberto("avatar.rostos_34", {"rosto_origem"})
    assert not aberto and motivo == "Escolha o rosto frontal antes"


def test_origem_enviada_fecha_o_rosto_gerado():
    aberto, motivo = padrao.passo_aberto("avatar.rosto_origem", set(), "pessoa_real")
    assert not aberto and "enviada" in motivo
    assert padrao.passo_aberto("avatar.rosto_origem", set(), "sintetico")[0]


@pytest.mark.parametrize("texto", ["a teen girl", "uma criança sorrindo", "16 years old woman",
                                   "BABY face", "menina de vestido", "a kid"])
def test_menoridade_recusa(texto):
    assert padrao.checar_menoridade(texto)


@pytest.mark.parametrize("texto", ["modern kitchen", "teenage-style haircut on an adult",
                                   "woman in her 30s", "minority report poster", None, ""])
def test_menoridade_sem_falso_positivo(texto):
    assert padrao.checar_menoridade(texto) is None


def test_instrucoes_sem_o_prompt_do_avatar():
    """FR-016: as instruções de edição são fixas (nunca recebem a descrição do avatar)."""
    for instr in (padrao.KIT_FRONTAL, padrao.KIT_34_ESQ, padrao.KIT_34_DIR,
                  padrao.instrucao_corpo("rosto"), padrao.instrucao_corpo("tela")):
        assert "{" not in instr
    assert "left" in padrao.KIT_34_ESQ and "right" in padrao.KIT_34_DIR
    assert "light gray" in padrao.KIT_CORPO
