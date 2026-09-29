"""Registro dos tipos de campo × schemas reais (spec 008, T008, R1): os limites do registro
nunca divergem dos limites da API."""

import typing
from typing import Annotated, get_args

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from sociman_api.assets.models import Asset
from sociman_api.assets.schemas import AssetPatch
from sociman_api.ia.regras_padrao import PADROES
from sociman_api.ia.tipos import TIPOS, TipoCampoId
from sociman_api.marca.tokens import KitTokens
from sociman_api.perfis.schemas import UpdatePerfilIn
from sociman_api.postagem import service as postagem_service
from sociman_api.postagem import textos
from sociman_api.postagem.schemas import CreatePostagemIn, UpdatePostagemIn

SCHEMAS: dict[str, type[BaseModel]] = {"asset": AssetPatch, "perfil": UpdatePerfilIn,
                                       "kit": KitTokens, "postagem": UpdatePostagemIn}


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


def test_os_13_ids_e_o_literal():
    assert len(TIPOS) == 13
    assert set(get_args(TipoCampoId)) == set(TIPOS) == set(PADROES)
    for tid, tipo in TIPOS.items():
        assert tipo.id == tid and tipo.padrao.strip() and tipo.padrao_versao >= 1


def test_so_os_prompts_de_imagem_sao_em_ingles():
    ingles = {t.id for t in TIPOS.values() if t.idioma == "en"}
    assert ingles == {"avatar.descricao_prompt", "cenario.prompt_ambiente"}
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
    for model in (UpdatePostagemIn, CreatePostagemIn):
        adapter = _adapter(model, "hashtags")
        assert _aceita(adapter, ["#a"] * 8) and not _aceita(adapter, ["#a"] * 9)
    assert postagem_service.HASHTAG_RE.match("#" + "a" * 50)
    assert not postagem_service.HASHTAG_RE.match("#" + "a" * 51)
    assert TIPOS["postagem.textos"].limites.max_chars == TIPOS["postagem.titulo"].limites.max_chars
    assert TIPOS["postagem.textos"].campos == ("titulo", "descricao", "hashtags")


def test_campos_existem_no_modelo_e_no_schema():
    from sociman_api.marca.models import BrandKit
    from sociman_api.perfis.models import Perfil
    from sociman_api.postagem.models import Postagem

    modelos = {"asset": Asset, "perfil": Perfil, "kit": BrandKit, "postagem": Postagem}
    for tipo in TIPOS.values():
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
        [campo] = tipo.campos
        if campo in permitidos:
            assert tipo.tipos_asset is not None
            assert tipo.tipos_asset <= permitidos[campo], tipo.id
        else:
            assert tipo.tipos_asset is None  # nome e notas: todos os tipos


def test_literal_e_tipo_do_typing():
    assert typing.get_origin(TipoCampoId) is typing.Literal
