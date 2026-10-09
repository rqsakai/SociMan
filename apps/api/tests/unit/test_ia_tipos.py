"""Registro dos tipos de campo × schemas reais (spec 008, T008, R1): os limites do registro
nunca divergem dos limites da API."""

import typing
from typing import Annotated, get_args

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from sociman_api.assets.models import Asset
from sociman_api.assets.schemas import AssetPatch
from sociman_api.cenas.schemas import CenaPatch
from sociman_api.ia.regras_padrao import PADROES
from sociman_api.ia.tipos import TIPOS, TipoCampoId
from sociman_api.marca.tokens import KitTokens
from sociman_api.perfis.schemas import UpdatePerfilIn
from sociman_api.postagem import service as postagem_service
from sociman_api.postagem import textos
from sociman_api.postagem.schemas import CreateDestinoIn, UpdateDestinoIn

SCHEMAS: dict[str, type[BaseModel]] = {"asset": AssetPatch, "perfil": UpdatePerfilIn,
                                       "kit": KitTokens, "postagem": UpdateDestinoIn,
                                       "cena": CenaPatch}  # spec 010
CENA = {"cena.acao", "cena.camera", "cena.estilo", "cena.audio", "cena.ajustar"}


def _adapter(model: type[BaseModel], campo: str) -> TypeAdapter:
    fi = model.model_fields[campo]
    tipo = Annotated[(fi.annotation, *fi.metadata)] if fi.metadata else fi.annotation
    return TypeAdapter(tipo)


def _aceita(adapter: TypeAdapter, valor) -> bool:
    try:
        adapter.validate_python(valor)
    except ValidationError:
        return False
    return True


def test_os_25_ids_e_o_literal():
    # 13 da 008 + guia.montar e guia.testar (spec 017) + 5 da cena (spec 010) + 3 do aprendizado
    # (spec 023) + a ficha do produto (spec 012) + a identidade do avatar (spec 025).
    assert len(TIPOS) == 25
    assert set(get_args(TipoCampoId)) == set(TIPOS)
    assert set(PADROES) == set(TIPOS) - {"guia.testar"}
    for tid, tipo in TIPOS.items():
        assert tipo.id == tid and tipo.padrao.strip() and tipo.padrao_versao >= 1
    testar = TIPOS["guia.testar"]
    assert testar.regras_de == "postagem.textos" and not testar.listar_regras
    assert testar.padrao == TIPOS["postagem.textos"].padrao
    assert TIPOS["guia.montar"].listar_regras and TIPOS["guia.montar"].regras_de is None


def test_so_os_prompts_de_imagem_sao_em_ingles():
    ingles = {t.id for t in TIPOS.values() if t.idioma == "en"}
    assert ingles == {"avatar.descricao_prompt", "cenario.prompt_ambiente",
                      "produto.ficha", "avatar.identidade"} | CENA
    assert TIPOS["avatar.regras_imagem"].idioma == "perfil"  # Q2 = B


@pytest.mark.parametrize("tid", [t.id for t in TIPOS.values() if t.formato == "texto"])
def test_limites_de_texto_batem_com_o_schema(tid):
    tipo = TIPOS[tid]
    [campo] = tipo.campos
    adapter = _adapter(SCHEMAS[tipo.entidade], campo)
    lim = tipo.limites
    assert _aceita(adapter, "a" * lim.max_chars)
    assert not _aceita(adapter, "a" * (lim.max_chars + 1))
    assert _aceita(adapter, "") == (lim.min_chars is None)
    # trim do registro = strip do schema.
    assert (adapter.validate_python(" a ") == "a") == lim.trim


@pytest.mark.parametrize("tid", ["kit.bordoes", "kit.series"])
def test_limites_das_sugestoes_batem_com_o_kit(tid):
    tipo = TIPOS[tid]
    [campo] = tipo.campos
    adapter = _adapter(KitTokens, campo)
    lim = tipo.limites
    assert tipo.formato == "sugestoes" and lim.max_sugestoes == 10 and lim.unicos
    assert _aceita(adapter, [f"item {i}" for i in range(lim.max_itens)])
    assert not _aceita(adapter, [f"item {i}" for i in range(lim.max_itens + 1)])
    assert _aceita(adapter, ["a" * lim.max_chars_item])
    assert not _aceita(adapter, ["a" * (lim.max_chars_item + 1)])
    assert not _aceita(adapter, [""])


def test_limites_das_hashtags_batem_com_a_postagem():
    for tid in ("postagem.hashtags", "postagem.textos"):
        lim = TIPOS[tid].limites
        assert (lim.min_itens, lim.max_itens) == (textos.HASHTAGS_MIN, textos.HASHTAGS_MAX)
        assert lim.max_chars_item == textos.HASHTAG_MAX_CHARS and lim.normalizar == "hashtag"
    for model in (UpdateDestinoIn, CreateDestinoIn):
        adapter = _adapter(model, "hashtags")
        assert _aceita(adapter, ["#a"] * 8) and not _aceita(adapter, ["#a"] * 9)
    assert postagem_service.HASHTAG_RE.match("#" + "a" * 50)
    assert not postagem_service.HASHTAG_RE.match("#" + "a" * 51)
    assert TIPOS["postagem.textos"].limites.max_chars == TIPOS["postagem.titulo"].limites.max_chars
    assert TIPOS["postagem.textos"].campos == ("titulo", "descricao", "hashtags")


def test_campos_existem_no_modelo_e_no_schema():
    from sociman_api.cenas.models import Cena
    from sociman_api.marca.models import BrandKit
    from sociman_api.perfis.models import Perfil
    from sociman_api.postagem.models import Postagem

    modelos = {"asset": Asset, "perfil": Perfil, "kit": BrandKit, "postagem": Postagem,
               "cena": Cena}
    for tipo in TIPOS.values():
        if tipo.id.startswith("guia."):
            continue  # sem entidade salva com esses campos (spec 017; o montar é cruzado abaixo)
        if tipo.entidade == "aprendizado":
            continue  # spec 023: não aplica em formulário (o serviço do aprendizado grava)
        if tipo.entidade == "produto" or tipo.formato == "identidade":
            continue  # specs 012 e 025: o aplicador da 021 grava (não há formulário)
        for campo in tipo.campos:
            assert campo in modelos[tipo.entidade].__versioned_fields__, (tipo.id, campo)
            assert campo in SCHEMAS[tipo.entidade].model_fields, (tipo.id, campo)


def test_tipos_asset_batem_com_o_check_do_banco():
    [ck] = [c for c in Asset.__table__.constraints if c.name == "ck_assets_campos_por_tipo"]
    sql = str(ck.sqltext)
    assert "tipo IN ('avatar', 'cenario') OR prompt IS NULL" in sql
    assert "tipo = 'avatar' OR (voice_tone IS NULL AND image_rules IS NULL)" in sql
    permitidos = {"prompt": {"avatar", "cenario"}, "voice_tone": {"avatar"},
                  "image_rules": {"avatar"}}
    for tipo in TIPOS.values():
        if tipo.entidade != "asset":
            assert tipo.tipos_asset is None
            continue
        if tipo.formato == "identidade":  # spec 025: grava `prompt` e `identidade` do avatar
            assert tipo.tipos_asset == frozenset({"avatar"})
            continue
        [campo] = tipo.campos
        if campo in permitidos:
            assert tipo.tipos_asset is not None
            assert tipo.tipos_asset <= permitidos[campo], tipo.id
        else:
            assert tipo.tipos_asset is None  # nome e notas: todos os tipos


def test_literal_e_tipo_do_typing():
    assert typing.get_origin(TipoCampoId) is typing.Literal


def test_usa_guia_so_proibidas_nos_3_campos_visuais():
    """Spec 017 (Q1): a voz do guia não entra nos prompts de imagem nem nas regras visuais."""
    visuais = {"avatar.descricao_prompt", "cenario.prompt_ambiente", "avatar.regras_imagem"}
    visuais |= CENA  # spec 010: os campos da cena para o Flow também
    visuais |= {"avatar.identidade"}  # spec 025: a descrição para prompts do kit
    assert {t.id for t in TIPOS.values() if t.usa_guia == "so_proibidas"} == visuais
    assert all(t.usa_guia == "completo" for t in TIPOS.values() if t.id not in visuais)


def test_guia_montar_bate_com_o_guia_salvo():
    """Spec 017: os campos do `guia.montar` existem no modelo do guia e no `GuiaIn` (os do
    dono, fixas, máximo e exemplos, ficam de fora da proposta)."""
    from sociman_api.ia.models import IaGuia
    from sociman_api.ia.saida import PropostaGuia
    from sociman_api.ia.schemas_guia import GuiaCampos, GuiaIn

    tipo = TIPOS["guia.montar"]
    assert tipo.entidade == "guia" and tipo.formato == "guia" and "campos" in GuiaIn.model_fields
    for campo in tipo.campos:
        assert campo in IaGuia.__versioned_fields__, campo
        assert campo in GuiaCampos.model_fields, campo
        assert campo in PropostaGuia.model_fields, campo
    assert not {"hashtags_fixas", "max_hashtags_fixas", "exemplos"} & set(tipo.campos)


def test_tipos_da_cena():
    """Spec 010 (T035): só proibidas do guia; `campos_cena` só no ajustar, com os limites do
    `CenaPatch` em cada um dos 4 campos."""
    from sociman_api.ia.tipos import CAMPOS_CENA_IA, LIMITES_CENA

    for tid in CENA:
        assert TIPOS[tid].entidade == "cena" and TIPOS[tid].usa_guia == "so_proibidas"
    assert {t.id for t in TIPOS.values() if t.formato == "campos_cena"} == {"cena.ajustar"}
    assert TIPOS["cena.ajustar"].campos == CAMPOS_CENA_IA
    for campo, limite in LIMITES_CENA.items():
        adapter = _adapter(CenaPatch, campo)
        assert _aceita(adapter, "a" * limite) and not _aceita(adapter, "a" * (limite + 1))
        if campo != "acao":
            assert TIPOS[f"cena.{campo}"].limites.max_chars == limite


def test_os_3_tipos_do_aprendizado_tem_regra_editavel():
    """Spec 023 (T010, R5): taxonomia, classificação e análise, com regra padrão listada em
    "Assistente de IA › Regras" e fora do `gerar` (entidade `aprendizado`)."""
    ids = {"aprendizado.taxonomia", "aprendizado.classificacao", "aprendizado.analise"}
    assert ids <= set(TIPOS) and ids <= set(PADROES)
    for tid in ids:
        tipo = TIPOS[tid]
        assert tipo.entidade == "aprendizado" and tipo.listar_regras and tipo.regras_de is None
        assert tipo.padrao.strip() and tipo.padrao_versao == 1
    assert {TIPOS[t].formato for t in ids} == {"taxonomia", "classificacao", "analise"}
    assert TIPOS["aprendizado.taxonomia"].limites.max_itens == 15
    assert TIPOS["aprendizado.analise"].limites.max_itens == 6


def test_produto_ficha():
    """Spec 012 (T011): o tipo existe, fora das regras editáveis e do `gerar`, com os campos da
    ficha do produto e do `PUT …/ficha`, a regra padrão = o `SYSTEM` da ficha e mais tokens."""
    from sociman_api.produtos import ficha
    from sociman_api.produtos.models import CAMPOS_FICHA, Produto
    from sociman_api.produtos.schemas import FichaIn

    tipo = TIPOS["produto.ficha"]
    assert tipo.entidade == "produto" and tipo.formato == "ficha_produto"
    assert not tipo.listar_regras and tipo.regras_de is None
    assert tipo.padrao == ficha.SYSTEM
    assert tipo.campos == CAMPOS_FICHA
    for campo in tipo.campos:
        assert campo in Produto.__versioned_fields__
        assert campo in FichaIn.model_fields
    assert tipo.max_tokens == 8000 and tipo.timeout_s and tipo.timeout_s > 20

