"""Ficha técnica pelo Claude (spec 012, T010; research R2 e R5): a redução das fotos em
memória, os limites e os campos em inglês guardados como vieram."""

import base64
import io

import pytest
from PIL import Image

from sociman_api.ia import saida
from sociman_api.ia.tipos import TIPOS
from sociman_api.produtos import ficha


def _png(size: tuple[int, int], modo: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(modo, size, (10, 120, 200, 128) if modo == "RGBA" else (10, 120, 200)).save(
        buf, format="PNG")
    return buf.getvalue()


def _saida(**campos) -> ficha.FichaSaida:
    base = {
        "nome_comercial": "Short canelado", "categoria": "roupa > shorts",
        "material_en": "ribbed knit", "material_pt": "malha canelada",
        "cores": [{"foto": 1, "en": "black", "pt": "preto"}],
        "formato_corte": "biker shorts", "detalhes_visiveis": ["LS logo"],
        "tamanho_relativo": "identical", "descricao_prompt": "Ribbed knit biker shorts.",
        "cuidados": ["não é jeans"], "descricao_venda": "Confortável.", "precisa_flat": True,
        "explicacao": "ok", "avisos": [],
    }
    return ficha.FichaSaida(**(base | campos))


def test_foto_grande_vira_1568_no_lado_maior_sem_gravar():
    original = _png((4000, 2000))
    jpeg = ficha.reduzir(original)
    with Image.open(io.BytesIO(jpeg)) as im:
        assert im.format == "JPEG" and im.size == (1568, 784)
    with Image.open(io.BytesIO(ficha.reduzir(_png((800, 600))))) as im:
        assert im.size == (800, 600)  # pequena não aumenta
    with Image.open(io.BytesIO(ficha.reduzir(_png((600, 600), "RGBA")))) as im:
        assert im.mode == "RGB"  # transparência vira fundo branco


def test_mensagem_numera_as_fotos_e_leva_a_observacao():
    blocos = ficha.montar_mensagem([_png((600, 600)), _png((700, 600))], "shorts", "3 cores")
    textos = [b["text"] for b in blocos if b["type"] == "text"]
    assert textos[:2] == ["PRODUCT PHOTO 1:", "PRODUCT PHOTO 2:"]
    assert "<instrucao>3 cores</instrucao>" in textos[-1]
    imagens = [b for b in blocos if b["type"] == "image"]
    assert len(imagens) == 2 and imagens[0]["source"]["media_type"] == "image/jpeg"
    base64.standard_b64decode(imagens[0]["source"]["data"])


def test_limites_dos_campos():
    assert ficha.validar_limites(_saida()) == []
    assert any("material_en" in e for e in ficha.validar_limites(
        _saida(material_en="soft stretchy ribbed cotton knit fabric")))  # 6 palavras
    assert any("material_en" in e for e in ficha.validar_limites(_saida(material_en="knit")))
    assert any("detalhes_visiveis" in e for e in ficha.validar_limites(
        _saida(detalhes_visiveis=[f"d{i}" for i in range(13)])))
    assert any("descricao_venda" in e for e in ficha.validar_limites(
        _saida(descricao_venda="x" * 601)))
    assert any("cuidados" in e for e in ficha.validar_limites(_saida(cuidados=[])))
    assert any("cores" in e for e in ficha.validar_limites(
        _saida(cores=[{"foto": 1, "en": "x" * 41, "pt": "preto"}])))
    assert any("uma por foto" in e for e in ficha.validar_limites(_saida(), n_fotos=2))


def test_campos_em_ingles_sem_trim():
    s = _saida(descricao_prompt=" Ribbed knit biker shorts. ")
    assert ficha.campos_do_produto(s)["descricao_prompt"] == " Ribbed knit biker shorts. "


def test_saida_do_assistente():
    tipo = TIPOS["produto.ficha"]
    assert saida.SCHEMAS[tipo.formato] is ficha.FichaSaida
    v = saida.finalizar(tipo, _saida())
    assert v.proposta["ficha"]["material_en"] == "ribbed knit"
    assert v.proposta["ficha"]["cores"] == [{"foto": 1, "en": "black", "pt": "preto"}]
    assert "explicacao" not in v.proposta["ficha"]
    ruim = _saida(material_en="soft stretchy ribbed cotton knit fabric")
    assert saida.problemas(tipo, ruim)
    with pytest.raises(saida.Invalida):
        saida.finalizar(tipo, ruim)
