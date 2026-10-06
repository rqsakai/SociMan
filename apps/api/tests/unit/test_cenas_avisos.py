"""Avisos da cena (spec 010, T009, research R4): função pura, com as bordas."""

from sociman_api.cenas.avisos import EntradaAvisos, Mudanca, calcular, limite_palavras
from sociman_api.cenas.models import CenaModo


def _codigos(**kw) -> list[str]:
    base = {"acao": "opens the box", "duracao_s": 8, "modo": CenaModo.ingredientes}
    return [a.codigo for a in calcular(EntradaAvisos(**{**base, **kw}))]


def test_fala_longa_proporcional():
    assert limite_palavras(8) == 15 and limite_palavras(4) == 8 and limite_palavras(6) == 12
    quinze, dezesseis = " ".join(["oi"] * 15), " ".join(["oi"] * 16)
    assert "fala_longa" not in _codigos(fala=quinze)
    assert "fala_longa" in _codigos(fala=dezesseis)
    oito, nove = " ".join(["oi"] * 8), " ".join(["oi"] * 9)
    assert "fala_longa" not in _codigos(fala=oito, duracao_s=4, modo=CenaModo.quadros)
    assert "fala_longa" in _codigos(fala=nove, duracao_s=4, modo=CenaModo.quadros)


def test_duracao_modo():
    assert "duracao_modo" in _codigos(duracao_s=6)
    assert "duracao_modo" not in _codigos(duracao_s=6, modo=CenaModo.quadros)
    assert "duracao_modo" not in _codigos()


def test_produto_sem_foto():
    assert "produto_sem_foto" in _codigos(produto_nome="Panela")
    assert "produto_sem_foto" not in _codigos(produto_nome="Panela", produto_com_foto=True)
    assert "produto_sem_foto" not in _codigos(produto_nome="  ")


def test_proibida_sem_acento_e_sem_caixa():
    avisos = calcular(EntradaAvisos(acao="x", duracao_s=8, modo=CenaModo.ingredientes,
                                    fala="Um MILAGRE na cozinha", texto_tela="milágre",
                                    proibidas=["milagre"]))
    proibidas = [a for a in avisos if a.codigo == "proibida"]
    assert [a.campo for a in proibidas] == ["fala", "textoTela"]
    assert proibidas[0].detalhe == {"palavras": ["milagre"]}
    assert "proibida" not in _codigos(fala="milagres", proibidas=["milagre"])


def test_assets_mudaram_e_arquivados():
    avisos = calcular(EntradaAvisos(
        acao="x", duracao_s=8, modo=CenaModo.ingredientes,
        mudancas=[Mudanca("avatar", "A woman.", "A woman smiling.")],
        arquivados=["cenario", "produto"]))
    mudou = [a for a in avisos if a.codigo == "assets_mudaram"]
    assert mudou[0].detalhe == {"parte": "avatar", "antes": "A woman.",
                                "depois": "A woman smiling."}
    assert [a.campo for a in avisos if a.codigo == "asset_arquivado"] == ["cenarioId",
                                                                          "produtoImagemId"]
    assert _codigos() == []
