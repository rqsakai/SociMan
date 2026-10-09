"""T051 (SC-010): o revezamento puro da fila. Com 3 perfis e uma fila três vezes maior que o
orçamento, cada perfil leva ≥ ⌊n/3⌋ − 1 por nível, nenhum produto comum entra duas vezes e o
"perfil" nulo (tarefas sem perfil) entra como um perfil a mais, por último na ordem."""

import uuid

from sociman_api.mercado.fila import Candidato, revezar

P1, P2, P3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def cand(perfil, chave: str, nivel: int = 4) -> Candidato:
    return Candidato(tipo="produto", chave=f"produto:{chave}", url=f"https://x/{chave}",
                     nivel=nivel, fonte="ambas", perfil_id=perfil)


def test_um_de_cada_perfil_por_vez_na_ordem_fixa():
    grupos = {P1: [cand(P1, f"a{i}") for i in range(5)],
              P2: [cand(P2, f"b{i}") for i in range(5)],
              P3: [cand(P3, f"c{i}") for i in range(5)]}
    saida = revezar(grupos, [P1, P2, P3, None])
    assert [c.chave for c in saida[:6]] == ["produto:a0", "produto:b0", "produto:c0",
                                            "produto:a1", "produto:b1", "produto:c1"]
    assert len(saida) == 15
    # Cortada em n = 9 (fila 3× maior que a cota de 3 por perfil), cada perfil leva 3.
    corte = saida[:9]
    for p in (P1, P2, P3):
        assert sum(1 for c in corte if c.perfil_id == p) == 3


def test_produto_comum_entra_uma_vez_pelo_primeiro_perfil_e_o_outro_pula():
    comum = "z"
    grupos = {P1: [cand(P1, comum), cand(P1, "a1")],
              P2: [cand(P2, comum), cand(P2, "b1"), cand(P2, "b2")]}
    saida = revezar(grupos, [P1, P2, None])
    chaves = [c.chave for c in saida]
    assert chaves.count(f"produto:{comum}") == 1
    # P1 levou o comum; na vez de P2 o comum é pulado e P2 entrega o seu próximo.
    assert chaves == [f"produto:{comum}", "produto:b1", "produto:a1", "produto:b2"]
    assert saida[0].perfil_id == P1


def test_perfil_nulo_entra_por_ultimo_e_participa_do_rodizio():
    grupos = {P1: [cand(P1, "a0"), cand(P1, "a1")],
              None: [cand(None, "v0"), cand(None, "v1")]}
    saida = revezar(grupos, [P1, None])
    assert [c.chave for c in saida] == ["produto:a0", "produto:v0", "produto:a1", "produto:v1"]


def test_perfil_sem_candidatos_nao_quebra_e_grupos_desiguais_terminam():
    grupos = {P2: [cand(P2, "b0")], P3: [cand(P3, f"c{i}") for i in range(3)]}
    saida = revezar(grupos, [P1, P2, P3, None])
    assert [c.chave for c in saida] == ["produto:b0", "produto:c0", "produto:c1", "produto:c2"]


def test_sc_010_cada_perfil_leva_ao_menos_piso():
    # 3 perfis, cada um com 30 candidatos, orçamento 30 (fila 3×): piso ⌊30/3⌋ − 1 = 9.
    grupos = {p: [cand(p, f"{n}-{i}") for i in range(30)] for n, p in enumerate((P1, P2, P3))}
    corte = revezar(grupos, [P1, P2, P3, None])[:30]
    for p in (P1, P2, P3):
        assert sum(1 for c in corte if c.perfil_id == p) >= 30 // 3 - 1
    assert len({c.chave for c in corte}) == 30
