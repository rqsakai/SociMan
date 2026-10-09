"""Ficha técnica do produto pelo Claude (research R2 e R5), pura: o schema da saída, o texto do
pedido (o `SYSTEM` do pipeline, adaptado), a mensagem com as fotos e os limites.

As fotos vão numeradas ("PRODUCT PHOTO N") e reduzidas **em memória** a no máximo 1568 px no
lado maior, em JPEG 90: o original no MinIO não muda e nada é gravado. A observação do dono vai
na `<instrucao>` (é o pedido dele); o nome interno vai como dado.

Os campos em inglês vão literais para os prompts, então são guardados sem trim (R2).
"""

import base64
import io
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

PROMPT_VERSION = "produto/1"
LADO_MAX = 1568
JPEG_QUALIDADE = 90


class Cor(BaseModel):
    foto: int = Field(description="1-based photo number this color appears in")
    en: str = Field(description="precise English color name for prompts, e.g. 'navy blue', "
                                "'heather grey'")
    pt: str = Field(description="the same color in Brazilian Portuguese")


class FichaSaida(BaseModel):
    """O `Ficha` do pipeline, com os nomes das colunas do SociMan, mais o `explicacao` e os
    `avisos` que toda saída do assistente traz."""

    nome_comercial: str = Field(description="short commercial name in Brazilian Portuguese, "
                                            "e.g. 'Short canelado cintura alta'")
    categoria: str = Field(description="Brazilian Portuguese category, e.g. 'roupa > shorts'")
    material_en: str = Field(description="SHORT exact material/texture phrase for prompts "
                                         "(2-5 words), e.g. 'ribbed knit', 'smooth satin'; "
                                         "texture nuances go in detalhes_visiveis")
    material_pt: str = Field(description="the same material in Brazilian Portuguese")
    cores: list[Cor] = Field(description="one entry per photo (variant), in photo order")
    formato_corte: str = Field(description="English: shape and cut, e.g. 'high-waisted "
                                           "biker-style shorts, mid-thigh length'")
    detalhes_visiveis: list[str] = Field(description="English: every visible detail with "
                                                     "position: logo text/color/position, "
                                                     "waistband, seams, labels, hardware")
    tamanho_relativo: str = Field(description="English fact about relative size of the "
                                              "variants, e.g. 'all three variants are identical "
                                              "in size and cut'; for a single item, its "
                                              "real-life size")
    descricao_prompt: str = Field(description="ONE English sentence used verbatim in "
                                              "image/video prompts: names the item, material, "
                                              "cut and logo; no colors if variants differ")
    cuidados: list[str] = Field(description="Brazilian Portuguese: what image/video models "
                                            "tend to get wrong for THIS product (wrong "
                                            "material, logo drift, sizes, deformation...), as "
                                            "short checks")
    descricao_venda: str = Field(description="Brazilian Portuguese, 2-3 sentences, no claims "
                                             "beyond what is visible in the photos")
    precisa_flat: bool = Field(description="true if it is a garment/textile photographed in a "
                                           "worn or ghost-mannequin 3D shape that must be "
                                           "converted to a flat-lay for scenes where it lies "
                                           "on a surface")
    explicacao: str = Field(description="até 3 frases curtas em pt-BR")
    avisos: list[str] = Field(description="até 5 frases curtas em pt-BR")


SYSTEM = """\
You write the product registration sheet for a TikTok Shop video pipeline in Brazil. The sheet \
is the single source of truth that image and video models (Qwen-Image-Edit, MiniMax, Wan) will \
receive in their prompts, so every word must match what is VISIBLE in the photos: the exact \
material and texture (e.g. ribbed knit is not denim, not jersey), each photo's color, the logo \
text and where it is, the cut. When the owner's notes (<instrucao>) and the photos disagree, \
trust the photos and say so in 'cuidados'. When several photos are color variants of the same \
item, state that they are identical in size and cut. Never invent features (fabric composition, \
sizes, prices, benefits) that cannot be seen. English fields are for the models; Portuguese \
fields (Brazilian Portuguese) are for the owner. Give one entry in 'cores' per photo, in photo \
order."""

# Limites (R2): (campo, máximo de caracteres) dos textos e (campo, itens, caracteres) das listas.
TEXTOS = {"nome_comercial": 120, "categoria": 120, "material_en": 60, "material_pt": 60,
          "formato_corte": 300, "tamanho_relativo": 300, "descricao_prompt": 500,
          "descricao_venda": 600}
LISTAS = {"detalhes_visiveis": (12, 200), "cuidados": (12, 200)}
COR_MAX = 40
MATERIAL_PALAVRAS = (2, 5)


def reduzir(data: bytes) -> bytes:
    """A foto em JPEG 90, com no máximo `LADO_MAX` px no lado maior (fundo branco no lugar da
    transparência). Só em memória."""
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            fundo = Image.new("RGB", rgba.size, (255, 255, 255))
            fundo.paste(rgba, mask=rgba.split()[-1])
            rgb = fundo
        else:
            rgb = im.convert("RGB")
    rgb.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=JPEG_QUALIDADE)
    return buf.getvalue()


def _bloco_imagem(data: bytes) -> dict[str, Any]:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(reduzir(data)).decode()}}


def montar_mensagem(fotos: list[bytes], nome: str, obs: str) -> list[dict[str, Any]]:
    """Os blocos da mensagem do usuário: cada foto numerada e, no fim, o nome e a observação."""
    blocos: list[dict[str, Any]] = []
    for i, foto in enumerate(fotos, start=1):
        blocos += [{"type": "text", "text": f"PRODUCT PHOTO {i}:"}, _bloco_imagem(foto)]
    blocos.append({"type": "text", "text": (
        f"<nome_interno>{nome}</nome_interno>\n"
        f"<instrucao>{obs.strip() or '(nenhuma observação)'}</instrucao>\n"
        f"<fotos>{len(fotos)}</fotos>\n"
        "Write the product sheet.")})
    return blocos


def _palavras(texto: str) -> int:
    return len(texto.split())


def problemas_campos(campos: dict[str, Any]) -> list[tuple[str, str]]:
    """Os limites dos campos da ficha (R2), em `(campo, mensagem)`. Campo ausente ou `None` não
    é conferido aqui (completo ou não é regra de `estados`)."""
    out: list[tuple[str, str]] = []
    for campo, maximo in TEXTOS.items():
        valor = campos.get(campo)
        if valor is None:
            continue
        if not str(valor).strip():
            out.append((campo, "não pode ficar vazio"))
        elif len(valor) > maximo:
            out.append((campo, f"até {maximo} caracteres"))
    material = campos.get("material_en")
    if material is not None and material.strip():
        minimo, maximo = MATERIAL_PALAVRAS
        if not minimo <= _palavras(material) <= maximo:
            out.append(("material_en", f"de {minimo} a {maximo} palavras"))
    for campo, (itens, maximo) in LISTAS.items():
        valor = campos.get(campo)
        if valor is None:
            continue
        if len(valor) > itens:
            out.append((campo, f"no máximo {itens} itens"))
        for i, item in enumerate(valor):
            if not item.strip():
                out.append((f"{campo}[{i}]", "item vazio"))
            elif len(item) > maximo:
                out.append((f"{campo}[{i}]", f"até {maximo} caracteres"))
    return out


def problemas_cor(en: str | None, pt: str | None) -> list[tuple[str, str]]:
    out = []
    for campo, valor in (("cor_en", en), ("cor_pt", pt)):
        if valor is not None and len(valor) > COR_MAX:
            out.append((campo, f"até {COR_MAX} caracteres"))
    return out


def validar_limites(ficha: FichaSaida, n_fotos: int | None = None) -> list[str]:
    """O que pede a 2ª tentativa ao Claude (vazio = passou)."""
    campos = ficha.model_dump(exclude={"cores", "explicacao", "avisos", "precisa_flat"})
    erros = [f"{c}: {m}" for c, m in problemas_campos(campos)]
    if not ficha.detalhes_visiveis:
        erros.append("detalhes_visiveis: pelo menos 1 item")
    if not ficha.cuidados:
        erros.append("cuidados: pelo menos 1 item")
    for cor in ficha.cores:
        erros.extend(f"cores[{cor.foto}].{c}: {m}" for c, m in problemas_cor(cor.en, cor.pt))
        if not cor.en.strip() or not cor.pt.strip():
            erros.append(f"cores[{cor.foto}]: a cor veio vazia")
    if n_fotos is not None:
        fotos = sorted(c.foto for c in ficha.cores)
        if fotos != list(range(1, n_fotos + 1)):
            erros.append(f"cores: uma por foto, de 1 a {n_fotos}")
    return erros


def campos_do_produto(ficha: FichaSaida) -> dict[str, Any]:
    """Os campos da ficha que vão para o produto (exatos, sem trim)."""
    return ficha.model_dump(exclude={"cores", "explicacao", "avisos"})


def cores_por_foto(ficha: FichaSaida) -> dict[int, Cor]:
    return {c.foto: c for c in ficha.cores}
