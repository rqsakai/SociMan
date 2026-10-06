"""Leitor de markdown (spec 013, T008, R3): variações reais de agente — negrito, crases, nota
antes da tabela, `|` escapado, valor em várias linhas, "A DEFINIR" e células a mais ou a menos."""

from sociman_api.agencia import markdown as md


def test_normalizar_e_vazio():
    assert md.normalizar("**Posicionamento** e `Tom`") == "posicionamento e tom"
    assert md.normalizar("Expressões  da   casa") == "expressoes da casa"
    assert md.vazio("A DEFINIR") and md.vazio("<Nome>") and md.vazio("") and md.vazio(" — ")
    assert not md.vazio("Mulheres (faixa etária A DEFINIR)")


def test_frontmatter_e_secoes():
    texto = "---\nslug: x\nstatus: ativo\n---\n> nota\n# Perfil: X\n\n## 1. Identidade\n- a: 1\n" \
            "### sub\ntexto\n## 2. Nicho\n```\n## não é título\n```\n"
    front, resto, desloc = md.frontmatter(texto)
    assert front == {"slug": "x", "status": "ativo"} and desloc == 4
    s = md.secoes(resto, desloc)
    assert [(x.nivel, x.titulo) for x in s] == [(1, "perfil: x"), (2, "1. identidade"),
                                                (3, "sub"), (2, "2. nicho")]
    assert s[1].linha == 8 and "### sub" in s[1].corpo  # o corpo inclui a subseção
    assert "## não é título" in s[3].corpo


def test_campos_com_parenteses_negrito_e_continuacao():
    corpo = ("- Tom (ex.: polêmico, educativo, humor): Humor descontraído\n"
             "- **Expressões da casa:** \"A\" · \"B\"\n"
             "  continua aqui\n"
             "- Proibido (temas, palavras, tipos de corte): NSFW\n"
             "texto solto\n"
             "- Tom: repetido não vale\n")
    c = md.campos(corpo)
    assert c["tom"] == "Humor descontraído"
    assert md.limpar(c["expressoes da casa"]) == "\"A\" · \"B\" continua aqui"
    assert c["proibido"] == "NSFW"


def test_tabelas_nota_antes_pipe_escapado_e_celulas_erradas():
    corpo = ("Nota antes da tabela.\n\n| **Criador** | Canal | Status |\n|---|:---:|---|\n"
             "| A \\| B | youtube.com/@a | `autorizado` |\n"
             "| C | youtube.com/@c |\n"
             "| D | x | `pendente` | extra |\n\ndepois\n")
    [t] = md.tabelas(corpo, 10)
    assert t.cabecalho == ["criador", "canal", "status"]
    assert t.linhas[0] == (15, ["A | B", "youtube.com/@a", "`autorizado`"])
    assert t.linhas[1][1] == ["C", "youtube.com/@c", ""]  # célula a menos: vazia
    assert t.linhas[2][1] == ["D", "x", "`pendente` | extra"]  # a mais: na última
    assert t.problemas == [16, 17]
    assert md.coluna(t.cabecalho, "status") == 2


def test_links():
    texto = "youtube.com/@a · https://www.tiktok.com/@b (ver https://x.com/y). www.youtube.com/c/z"
    assert md.links(texto) == ["youtube.com/@a", "https://www.tiktok.com/@b",
                               "https://x.com/y", "www.youtube.com/c/z"]
