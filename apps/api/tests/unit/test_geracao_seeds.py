"""Seeds (spec 021, T008, R7): base sorteada na 1ª, opção i = base + i - 1, e "Gerar outras"
nunca repete uma seed já usada."""

from sociman_api.geracao import seeds


def test_primeira_sorteia_a_base():
    assert seeds.proximas([], 3, sortear=lambda: 100) == [100, 101, 102]
    assert 1 <= seeds.sortear_base() <= seeds.BASE_MAX


def test_gerar_outras_nunca_repete():
    usadas: list[int] = []
    for _ in range(5):
        novas = seeds.proximas(usadas, 2, sortear=lambda: 7)
        assert not set(novas) & set(usadas)
        usadas += novas
    assert usadas == list(range(7, 17))
