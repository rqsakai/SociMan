"""Tokens do kit (T008): schema `KitTokens`, kit padrão, referências e resolução."""

import uuid

import pytest
from pydantic import ValidationError

from sociman_api.marca.tokens import (
    KitInvalid,
    KitTokens,
    RefContext,
    check_refs,
    default_kit,
    error_message,
    fields_using_font,
    font_refs,
    fundo_image_ids,
    resolve_color,
    resolve_tokens,
)

CONTA = uuid.uuid4()
FONT = uuid.uuid4()


def _kit(**changes) -> dict:
    """O kit padrão (com conta) como JSON da API, com `changes` por caminho `secao.campo`."""
    data = default_kit(CONTA).model_dump(mode="json", by_alias=True)
    for path, value in changes.items():
        section, _, field = path.partition("__")
        if field:
            data[section][field] = value
        else:
            data[section] = value
    return data


def _error(data: dict) -> str:
    with pytest.raises(ValidationError) as exc:
        KitTokens.model_validate(data)
    return error_message(exc.value.errors()[0])


def _ctx(**kw) -> RefContext:
    return RefContext(**({"conta_ids": frozenset({CONTA})} | kw))


# ---- kit padrão ----

def test_default_kit_matches_current_cut_style():
    kit = default_kit(CONTA)
    assert [c.valor for c in kit.palette] == ["#FFFFFF", "#000000", "#FFE500"]
    assert kit.caption.fonte == "padrao:anton" and kit.caption.tamanho == 44
    assert kit.caption.estilo == "karaoke" and kit.caption.efeito == "pop"
    assert kit.caption.opacidade_fundo == 0 and kit.caption.maiusculas
    assert kit.hook.fonte == "padrao:noto-serif-bold" and kit.hook.duracao_s == 5
    assert kit.hook.opacidade_fundo == 0.94 and kit.hook.ligado
    assert kit.watermark.tipo == "texto" and kit.watermark.ligado
    assert kit.watermark.conta_id == CONTA
    assert not kit.end_card.ligado and kit.end_card.cta == "Segue pra mais"
    assert kit.catchphrases == [] and kit.series == []
    check_refs(kit, _ctx())


def test_default_kit_without_conta_has_watermark_off_and_is_valid():
    kit = default_kit(None)
    assert not kit.watermark.ligado and kit.watermark.conta_id is None
    check_refs(kit, RefContext())


def test_sections_round_trip_and_api_aliases():
    kit = default_kit(CONTA)
    sections = kit.sections()
    assert set(sections) == {"palette", "caption", "hook", "watermark", "end_card",
                             "catchphrases", "series"}
    assert KitTokens.from_sections(sections) == kit
    api = kit.model_dump(mode="json", by_alias=True)
    assert "endCard" in api and "cor_texto" in api["caption"]  # só a raiz é camelCase
    assert KitTokens.model_validate(api) == kit


# ---- forma ----

def test_hex_is_normalized_to_upper():
    data = _kit(caption__cor_texto="#ff5fa2")
    data["palette"][0]["valor"] = "#abcdef"
    kit = KitTokens.model_validate(data)
    assert kit.caption.cor_texto == "#FF5FA2"
    assert kit.palette[0].valor == "#ABCDEF"


@pytest.mark.parametrize(("changes", "expected"), [
    ({"caption__tamanho": 201}, "caption.tamanho: deve ser no máximo 200"),
    ({"caption__tamanho": 9}, "caption.tamanho: deve ser no mínimo 10"),
    ({"caption__espessura_contorno": 11}, "caption.espessura_contorno: deve ser no máximo 10"),
    ({"caption__cor_texto": "red"}, "caption.cor_texto: cor inválida: use #RRGGBB ou paleta:<chave>"),
    ({"caption__cor_texto": "#FFF"}, "caption.cor_texto: cor inválida"),
    ({"caption__opacidade_fundo": 0.33}, "caption.opacidade_fundo: use múltiplos de 0,05"),
    ({"caption__opacidade_fundo": 1.05}, "caption.opacidade_fundo: deve ser no máximo 1"),
    ({"caption__posicao": "lado"}, "caption.posicao: opção inválida"),
    ({"caption__efeito": "neon"}, "caption.efeito: opção inválida"),
    ({"caption__fonte": "padrao:comic-sans"}, "caption.fonte: fonte inválida"),
    ({"caption__fonte": "perfil:nao-e-uuid"}, "caption.fonte: fonte inválida"),
    ({"caption__extra": 1}, "caption.extra: campo desconhecido"),
    ({"hook__duracao_s": 1.25}, "hook.duracao_s: use múltiplos de 0,5"),
    ({"hook__duracao_s": 10.5}, "hook.duracao_s: deve ser no máximo 10"),
    ({"hook__tamanho": "XL"}, "hook.tamanho: opção inválida"),
    ({"hook__posicao": "meio"}, "hook.posicao: opção inválida"),
    ({"watermark__escala_pct": 41}, "watermark.escala_pct: deve ser no máximo 40"),
    ({"watermark__opacidade_pct": 5}, "watermark.opacidade_pct: deve ser no mínimo 10"),
    ({"watermark__posicao": "meio"}, "watermark.posicao: opção inválida"),
    ({"watermark__imagem_id": "x"}, "watermark.imagem_id: identificador inválido"),
    ({"endCard__cta": "x" * 81}, "endCard.cta: no máximo 80 caracteres"),
    ({"endCard__cta": "   "}, "endCard.cta: não pode ficar vazio"),
    ({"endCard__duracao_s": 5.5}, "endCard.duracao_s: deve ser no máximo 5"),
    ({"catchphrases": ["a"] * 21}, "catchphrases: no máximo 20 itens"),
    ({"catchphrases": ["Olha isso", "olha isso"]}, "catchphrases: bordão repetido"),
    ({"series": ["x" * 61]}, "series.0: no máximo 60 caracteres"),
    ({"palette": []}, "palette: no mínimo 1 itens"),
])
def test_invalid_values_point_to_the_field(changes, expected):
    assert _error(_kit(**changes)).startswith(expected)


def test_palette_limits_and_unique_keys():
    base = {"chave": "c", "nome": "C", "valor": "#000000"}
    many = [base | {"chave": f"c{i}"} for i in range(13)]
    assert _error(_kit(palette=many)).startswith("palette: no máximo 12 itens")
    dup = [base, base | {"nome": "Outra"}]
    assert _error(_kit(palette=dup)).startswith("palette: chave de cor repetido")
    bad = [base | {"chave": "Rosa Forte"}]
    assert _error(_kit(palette=bad)).startswith("palette.0.chave: formato inválido")


def test_missing_section_and_unknown_root_field():
    data = _kit()
    del data["hook"]
    assert _error(data) == "hook: obrigatório"
    assert _error(_kit() | {"stickers": []}).startswith("stickers: campo desconhecido")


def test_steps_are_rounded():
    kit = KitTokens.model_validate(_kit(caption__opacidade_fundo=0.15, hook__duracao_s=2.5))
    assert kit.caption.opacidade_fundo == 0.15
    assert kit.hook.duracao_s == 2.5


def test_perfil_font_ref_is_normalized():
    ref = f"perfil:{str(FONT).upper()}"
    kit = KitTokens.model_validate(_kit(hook__fonte=ref))
    assert kit.hook.fonte == f"perfil:{FONT}"


# ---- referências ----

def test_palette_reference_must_exist():
    kit = KitTokens.model_validate(_kit(hook__cor_fundo="paleta:rosa"))
    with pytest.raises(KitInvalid) as exc:
        check_refs(kit, _ctx())
    assert exc.value.field == "hook.cor_fundo"
    assert "paleta:rosa" in exc.value.message


def test_removing_a_used_color_points_to_the_first_field():
    data = _kit()
    data["palette"] = [c for c in data["palette"] if c["chave"] != "preto"]
    with pytest.raises(KitInvalid) as exc:
        check_refs(KitTokens.model_validate(data), _ctx())
    assert exc.value.field == "caption.cor_contorno"  # a primeira cor que usa `preto`


def test_perfil_font_must_be_active():
    kit = KitTokens.model_validate(_kit(endCard__fonte=f"perfil:{FONT}"))
    with pytest.raises(KitInvalid) as exc:
        check_refs(kit, _ctx())
    assert exc.value.field == "endCard.fonte"
    check_refs(kit, _ctx(active_font_ids=frozenset({FONT})))


@pytest.mark.parametrize(("changes", "ctx", "field"), [
    ({"watermark__conta_id": str(uuid.uuid4())}, {}, "watermark.conta_id"),
    ({"watermark__conta_id": None}, {}, "watermark.conta_id"),
    ({"watermark__tipo": "imagem"}, {}, "watermark.imagem_id"),
    ({"watermark__tipo": "imagem", "watermark__imagem_id": str(uuid.uuid4())}, {},
     "watermark.imagem_id"),
    ({"watermark__tipo": "logo"}, {}, "watermark.tipo"),
    ({"endCard__ligado": True, "endCard__mostrar_logo": True}, {}, "endCard.mostrar_logo"),
])
def test_watermark_and_end_card_refs(changes, ctx, field):
    kit = KitTokens.model_validate(_kit(**changes))
    with pytest.raises(KitInvalid) as exc:
        check_refs(kit, _ctx(**ctx))
    assert exc.value.field == field


def test_switched_off_sections_do_not_require_the_target():
    kit = KitTokens.model_validate(_kit(watermark__ligado=False, watermark__tipo="logo",
                                        watermark__conta_id=None))
    check_refs(kit, RefContext())
    image = uuid.uuid4()
    kit = KitTokens.model_validate(_kit(watermark__tipo="imagem", watermark__imagem_id=str(image)))
    check_refs(kit, _ctx(watermark_image_ids=frozenset({image})))
    kit = KitTokens.model_validate(_kit(watermark__tipo="logo"))
    check_refs(kit, _ctx(has_logo=True))


# ---- resolução ----

def test_resolve_tokens_uses_hex_and_caller_fonts():
    data = _kit(hook__fonte=f"perfil:{FONT}")
    data["palette"].append({"chave": "rosa", "nome": "Rosa", "valor": "#FF5FA2"})
    data["hook"]["cor_fundo"] = "paleta:rosa"
    kit = KitTokens.model_validate(data)
    assert font_refs(kit) == ["padrao:anton", f"perfil:{FONT}"]
    fonts = {ref: {"ref": ref, "key": ref.upper()} for ref in font_refs(kit)}
    out = resolve_tokens(kit, fonts)
    assert out["hook"]["cor_fundo"] == "#FF5FA2"
    assert out["hook"]["cor_texto"] == "#000000"
    assert out["caption"]["cor_destaque"] == "#FFE500"
    assert out["hook"]["fonte"] == {"ref": f"perfil:{FONT}", "key": f"PERFIL:{FONT}".upper()}
    assert out["end_card"]["fonte"]["ref"] == "padrao:anton"
    assert resolve_color("#123456", kit.palette) == "#123456"
    # o kit original não muda
    assert kit.hook.cor_fundo == "paleta:rosa"


def test_fields_using_font():
    kit = KitTokens.model_validate(_kit(hook__fonte=f"perfil:{FONT}",
                                        endCard__fonte=f"perfil:{FONT}"))
    assert fields_using_font(kit, f"perfil:{FONT}") == ["hook.fonte", "endCard.fonte"]
    assert fields_using_font(kit, "padrao:anton") == ["caption.fonte", "watermark.fonte"]


def test_error_message_without_field():
    assert error_message({"type": "json_invalid", "loc": ("body", 12), "msg": "x"}) == \
        "12: JSON inválido"
    assert error_message({"type": "missing", "loc": ("body",), "msg": "x"}) == "obrigatório"


# ---- fundo com imagem (FR-005a) ----

FUNDO = uuid.uuid4()


def test_fundo_defaults_keep_saved_kits_valid():
    kit = default_kit(CONTA)
    assert (kit.hook.fundo_tipo, kit.hook.fundo_imagem_id) == ("cor", None)
    assert (kit.end_card.fundo_tipo, kit.end_card.fundo_imagem_id) == ("cor", None)
    assert kit.end_card.opacidade_fundo == 0.45
    # JSONB salvo antes dos campos novos: vale com os padrões.
    sections = kit.sections()
    for section in ("hook", "end_card"):
        for field in ("fundo_tipo", "fundo_imagem_id"):
            del sections[section][field]
    del sections["end_card"]["opacidade_fundo"]  # a do gancho já existia
    old = KitTokens.from_sections(sections)
    assert old == kit
    check_refs(old, _ctx())


@pytest.mark.parametrize(("changes", "expected"), [
    ({"hook__fundo_tipo": "foto"}, "hook.fundo_tipo: opção inválida"),
    ({"endCard__opacidade_fundo": 1.5}, "endCard.opacidade_fundo: deve ser no máximo 1"),
    ({"endCard__fundo_imagem_id": "x"}, "endCard.fundo_imagem_id: identificador inválido"),
])
def test_fundo_invalid_values(changes, expected):
    assert _error(_kit(**changes)).startswith(expected)


@pytest.mark.parametrize(("changes", "field"), [
    ({"hook__fundo_tipo": "imagem"}, "hook.fundo_imagem_id"),
    ({"hook__fundo_imagem_id": str(uuid.uuid4())}, "hook.fundo_imagem_id"),
    ({"endCard__ligado": True, "endCard__fundo_tipo": "imagem"}, "endCard.fundo_imagem_id"),
    ({"endCard__fundo_tipo": "imagem", "endCard__fundo_imagem_id": str(uuid.uuid4())},
     "endCard.fundo_imagem_id"),
])
def test_fundo_image_refs(changes, field):
    kit = KitTokens.model_validate(_kit(**changes))
    with pytest.raises(KitInvalid) as exc:
        check_refs(kit, _ctx(fundo_image_ids=frozenset({FUNDO})))
    assert exc.value.field == field


def test_fundo_image_ok_and_switched_off_section():
    kit = KitTokens.model_validate(_kit(
        hook__fundo_tipo="imagem", hook__fundo_imagem_id=str(FUNDO),
        endCard__ligado=True, endCard__fundo_tipo="imagem",
        endCard__fundo_imagem_id=str(FUNDO)))
    check_refs(kit, _ctx(fundo_image_ids=frozenset({FUNDO})))
    # Uma imagem de marca d'água não serve de fundo.
    with pytest.raises(KitInvalid):
        check_refs(kit, _ctx(watermark_image_ids=frozenset({FUNDO})))
    # Card desligado: imagem sem id não é erro.
    kit = KitTokens.model_validate(_kit(endCard__fundo_tipo="imagem"))
    check_refs(kit, _ctx())


def test_resolve_tokens_with_fundos():
    other = uuid.uuid4()
    kit = KitTokens.model_validate(_kit(
        hook__fundo_tipo="imagem", hook__fundo_imagem_id=str(FUNDO),
        endCard__fundo_tipo="imagem", endCard__fundo_imagem_id=str(other)))
    assert fundo_image_ids(kit) == [FUNDO, other]
    fonts = {ref: ref for ref in font_refs(kit)}
    out = resolve_tokens(kit, fonts, {FUNDO: {"fundo_imagem_url": "/a"},
                                      other: {"fundo_imagem_url": "/b"}})
    assert out["hook"]["fundo_imagem_url"] == "/a"
    assert out["end_card"]["fundo_imagem_url"] == "/b"
    assert out["end_card"]["opacidade_fundo"] == 0.45
    # Com fundo de cor, o id guardado não entra na resolução.
    kit = KitTokens.model_validate(_kit(hook__fundo_imagem_id=str(FUNDO)))
    assert fundo_image_ids(kit) == []
    assert "fundo_imagem_url" not in resolve_tokens(kit, fonts, {})["hook"]
