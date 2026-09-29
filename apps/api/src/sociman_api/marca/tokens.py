"""Tokens do kit de marca (data-model.md "Tokens", FR-001–FR-006; princípio III).

Três camadas, todas puras (sem banco):
- **forma:** o schema `KitTokens` e as seções, com as faixas e opções fechadas da spec. As
  chaves das seções ficam em português e snake_case (`cor_texto`), como no JSONB e na
  exportação; só a raiz do kit segue o camelCase da API (`endCard`);
- **referências:** `check_refs` confere `paleta:<chave>` contra a paleta e o que depende do
  banco (fontes ativas, logo, contas, imagens) contra um `RefContext` montado pelo service.
  Erros saem como `KitInvalid(field, message)`, com `field` no formato `hook.cor_fundo`;
- **resolução:** `resolve_tokens` troca cores por hex e fontes pelo que o chamador quiser (a
  exportação usa links; o corte usa `object_key`).
"""

import math
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    WithJsonSchema,
    field_validator,
)
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError

HEX_PATTERN = r"^#[0-9A-Fa-f]{6}$"
CHAVE_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
_HEX_RE = re.compile(HEX_PATTERN)
_PALETTE_REF_RE = re.compile(r"^paleta:([a-z0-9]+(?:-[a-z0-9]+)*)$")
_UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

PALETTE_PREFIX = "paleta:"
DEFAULT_PREFIX = "padrao:"
PERFIL_PREFIX = "perfil:"


# ---- fontes padrão (R8) ----

@dataclass(frozen=True)
class DefaultFont:
    key: str
    name: str  # exibido nos seletores
    family: str  # nome da família no arquivo (e no gerador de cortes)
    style: str
    filename: str  # em sociman_api/marca/fonts/

    @property
    def ref(self) -> str:
        return f"{DEFAULT_PREFIX}{self.key}"


DEFAULT_FONTS: dict[str, DefaultFont] = {
    f.key: f for f in (
        DefaultFont("anton", "Anton", "Anton", "Regular", "Anton-Regular.ttf"),
        DefaultFont("noto-serif-bold", "Noto Serif Bold", "Noto Serif", "Bold",
                    "NotoSerif-Bold.ttf"),
        DefaultFont("liberation-sans", "Liberation Sans", "Liberation Sans", "Bold",
                    "LiberationSans-Bold.ttf"),
        DefaultFont("liberation-serif", "Liberation Serif", "Liberation Serif", "Bold",
                    "LiberationSerif-Bold.ttf"),
    )
}


# ---- tipos com validação ----

def _hex(value: str) -> str:
    if not _HEX_RE.match(value):
        raise PydanticCustomError("cor_invalida", "cor inválida: use #RRGGBB")
    return value.upper()


def _cor_ref(value: str) -> str:
    if _HEX_RE.match(value):
        return value.upper()
    if _PALETTE_REF_RE.match(value):
        return value
    raise PydanticCustomError("cor_invalida", "cor inválida: use #RRGGBB ou paleta:<chave>")


def _fonte_ref(value: str) -> str:
    if value.startswith(DEFAULT_PREFIX) and value[len(DEFAULT_PREFIX):] in DEFAULT_FONTS:
        return value
    if value.startswith(PERFIL_PREFIX):
        try:
            return f"{PERFIL_PREFIX}{uuid.UUID(value[len(PERFIL_PREFIX):])}"
        except ValueError:
            pass
    raise PydanticCustomError("fonte_invalida", "fonte inválida: use uma fonte padrão ou do perfil")


def _step(step: float) -> Callable[[float], float]:
    """Múltiplos de `step` (0,05 ou 0,5), já arredondados para não guardar 0.30000000000000004."""

    def check(value: float) -> float:
        n = value / step
        if not math.isclose(n, round(n), abs_tol=1e-6):
            label = f"{step:g}".replace(".", ",")
            raise PydanticCustomError("passo_invalido", "use múltiplos de {step}", {"step": label})
        return round(round(n) * step, 4)

    return check


Hex = Annotated[str, AfterValidator(_hex),
                WithJsonSchema({"type": "string", "pattern": HEX_PATTERN})]
CorRef = Annotated[str, AfterValidator(_cor_ref), WithJsonSchema({
    "type": "string", "pattern": rf"^(#[0-9A-Fa-f]{{6}}|paleta:{CHAVE_PATTERN[1:-1]})$",
    "description": "#RRGGBB ou paleta:<chave>",
})]
FonteRef = Annotated[str, AfterValidator(_fonte_ref), WithJsonSchema({
    "type": "string",
    "pattern": rf"^(padrao:({'|'.join(DEFAULT_FONTS)})|perfil:{_UUID_RE})$",
    "description": "padrao:<chave> ou perfil:<uuid da fonte>",
})]
Chave = Annotated[str, StringConstraints(min_length=1, max_length=40, pattern=CHAVE_PATTERN)]
Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Espessura = Annotated[int, Field(ge=0, le=10)]
Opacidade = Annotated[float, Field(ge=0, le=1)]
FundoTipo = Literal["cor", "imagem"]
Catchphrase = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                               max_length=120)]
SerieName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Cta = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class _Section(BaseModel):
    # Nada fora do schema chega ao JSONB.
    model_config = ConfigDict(extra="forbid")


class Cor(_Section):
    chave: Chave  # única no kit, estável ao renomear
    nome: Nome
    valor: Hex


class Legenda(_Section):
    fonte: FonteRef
    tamanho: Annotated[int, Field(ge=10, le=200)]
    cor_texto: CorRef
    cor_contorno: CorRef
    espessura_contorno: Espessura
    cor_fundo: CorRef
    opacidade_fundo: Annotated[Opacidade, AfterValidator(_step(0.05))]
    estilo: Literal["classico", "karaoke"]
    cor_destaque: CorRef
    efeito: Literal["nenhum", "brilho", "pop", "caixa"]
    posicao: Literal["topo", "meio", "base"]
    maiusculas: bool


class Gancho(_Section):
    ligado: bool
    fonte: FonteRef
    cor_texto: CorRef
    cor_fundo: CorRef
    opacidade_fundo: Opacidade
    cor_contorno: CorRef
    espessura_contorno: Espessura
    posicao: Literal["topo", "centro", "base"]
    tamanho: Literal["P", "M", "G"]
    duracao_s: Annotated[float, Field(ge=1, le=10), AfterValidator(_step(0.5))]
    # FR-005a: com imagem, `cor_fundo` × `opacidade_fundo` vira a camada sobre a imagem.
    fundo_tipo: FundoTipo = "cor"
    fundo_imagem_id: uuid.UUID | None = None  # obrigatório com imagem (e ligado)


class MarcaDagua(_Section):
    ligado: bool
    tipo: Literal["logo", "imagem", "texto"]
    imagem_id: uuid.UUID | None = None  # obrigatório com tipo imagem (e ligado)
    conta_id: uuid.UUID | None = None  # obrigatório com tipo texto (e ligado)
    posicao: Literal["sup_esq", "sup_dir", "inf_esq", "inf_dir", "centro_inf", "centro_sup"]
    escala_pct: Annotated[int, Field(ge=5, le=40)]
    opacidade_pct: Annotated[int, Field(ge=10, le=100)]
    margem_pct: Annotated[int, Field(ge=0, le=10)]  # da largura
    fonte: FonteRef  # só no tipo texto
    cor_texto: CorRef  # só no tipo texto


class CardFinal(_Section):
    ligado: bool
    cta: Cta
    fonte: FonteRef
    cor_texto: CorRef
    cor_fundo: CorRef
    mostrar_logo: bool
    duracao_s: Annotated[float, Field(ge=1, le=5), AfterValidator(_step(0.5))]
    # FR-005a: sem imagem o fundo é opaco; com imagem, `cor_fundo` × `opacidade_fundo` é a
    # camada sobre ela.
    fundo_tipo: FundoTipo = "cor"
    fundo_imagem_id: uuid.UUID | None = None  # obrigatório com imagem (e ligado)
    opacidade_fundo: Opacidade = 0.45  # só usada com imagem


def _unique(items: list[str], what: str) -> list[str]:
    seen: set[str] = set()
    for item in items:
        key = item.casefold()
        if key in seen:
            raise PydanticCustomError("repetido", "{what} repetido: {item}",
                                      {"what": what, "item": item})
        seen.add(key)
    return items


class KitTokens(BaseModel):
    """O kit inteiro. Só a raiz é camelCase (`endCard`); as seções seguem data-model.md."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    palette: Annotated[list[Cor], Field(min_length=1, max_length=12)]
    caption: Legenda
    hook: Gancho
    watermark: MarcaDagua
    end_card: CardFinal
    catchphrases: Annotated[list[Catchphrase], Field(max_length=20)] = Field(
        default_factory=list)
    series: Annotated[list[SerieName], Field(max_length=20)] = Field(default_factory=list)

    @field_validator("palette")
    @classmethod
    def _chaves_unicas(cls, palette: list[Cor]) -> list[Cor]:
        _unique([c.chave for c in palette], "chave de cor")
        return palette

    @field_validator("catchphrases")
    @classmethod
    def _bordoes_unicos(cls, items: list[str]) -> list[str]:
        return _unique(items, "bordão")

    @field_validator("series")
    @classmethod
    def _series_unicas(cls, items: list[str]) -> list[str]:
        return _unique(items, "série")

    def sections(self) -> dict[str, Any]:
        """As colunas JSONB de `brand_kits` (chaves snake_case: `end_card`)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_sections(cls, data: Mapping[str, Any]) -> "KitTokens":
        return cls.model_validate(dict(data))


# ---- kit padrão (data-model.md "Kit padrão") ----

def default_kit(conta_id: uuid.UUID | None = None) -> KitTokens:
    """As cores do padrão atual dos cortes (US1-1): legenda do `AUTO_CAPTION_STYLE` e gancho
    `classic` do OpenShorts. A marca d'água usa o @ de `conta_id` (a primeira conta ativa) e
    fica desligada sem conta."""
    return KitTokens(
        palette=[
            Cor(chave="branco", nome="Branco", valor="#FFFFFF"),
            Cor(chave="preto", nome="Preto", valor="#000000"),
            Cor(chave="amarelo-destaque", nome="Amarelo destaque", valor="#FFE500"),
        ],
        caption=Legenda(
            fonte="padrao:anton", tamanho=44, cor_texto="paleta:branco",
            cor_contorno="paleta:preto", espessura_contorno=4, cor_fundo="paleta:preto",
            opacidade_fundo=0, estilo="karaoke", cor_destaque="paleta:amarelo-destaque",
            efeito="pop", posicao="base", maiusculas=True,
        ),
        hook=Gancho(
            ligado=True, fonte="padrao:noto-serif-bold", cor_texto="paleta:preto",
            cor_fundo="paleta:branco", opacidade_fundo=0.94, cor_contorno="paleta:preto",
            espessura_contorno=0, posicao="topo", tamanho="M", duracao_s=5,
        ),
        watermark=MarcaDagua(
            ligado=conta_id is not None, tipo="texto", imagem_id=None, conta_id=conta_id,
            posicao="inf_dir", escala_pct=20, opacidade_pct=70, margem_pct=4,
            fonte="padrao:anton", cor_texto="paleta:branco",
        ),
        end_card=CardFinal(
            ligado=False, cta="Segue pra mais", fonte="padrao:anton", cor_texto="paleta:branco",
            cor_fundo="paleta:preto", mostrar_logo=False, duracao_s=2,
        ),
    )


# ---- referências ----

class KitInvalid(Exception):
    """400 `invalid_kit`: `field` no formato `hook.cor_fundo` (raiz em camelCase)."""

    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


@dataclass(frozen=True)
class RefContext:
    """O que as referências do kit precisam do banco (montado pelo service)."""

    active_font_ids: frozenset[uuid.UUID] = frozenset()  # fontes ativas do perfil
    has_logo: bool = False
    conta_ids: frozenset[uuid.UUID] = frozenset()  # contas não arquivadas do perfil
    watermark_image_ids: frozenset[uuid.UUID] = frozenset()  # images.kind = watermark
    fundo_image_ids: frozenset[uuid.UUID] = frozenset()  # images.kind = fundo


_TOKEN_SECTIONS = ("caption", "hook", "watermark", "end_card")
_FUNDO_SECTIONS = ("hook", "end_card")


def _field_name(section: str) -> str:
    return to_camel(section)


def color_fields(kit: KitTokens) -> Iterator[tuple[str, str]]:
    """(campo, CorRef) de todas as cores das seções, na ordem do schema."""
    for section in _TOKEN_SECTIONS:
        for name, value in getattr(kit, section):
            if name.startswith("cor_"):
                yield f"{_field_name(section)}.{name}", value


def font_fields(kit: KitTokens) -> Iterator[tuple[str, str]]:
    """(campo, FonteRef) de todas as fontes das seções, na ordem do schema."""
    for section in _TOKEN_SECTIONS:
        yield f"{_field_name(section)}.fonte", getattr(kit, section).fonte


def fields_using_font(kit: KitTokens, ref: str) -> list[str]:
    """Campos que usam a fonte (409 `font_in_use` ao arquivar, US2-3)."""
    return [field for field, value in font_fields(kit) if value == ref]


def font_refs(kit: KitTokens) -> list[str]:
    """Fontes usadas no kit, sem repetição, na ordem do schema."""
    return list(dict.fromkeys(value for _, value in font_fields(kit)))


def fundo_image_ids(kit: KitTokens) -> list[uuid.UUID]:
    """Imagens de fundo do gancho e do card final com `fundo_tipo = imagem`, sem repetição."""
    ids = (getattr(kit, s).fundo_imagem_id for s in _FUNDO_SECTIONS
           if getattr(kit, s).fundo_tipo == "imagem")
    return list(dict.fromkeys(i for i in ids if i is not None))


def perfil_font_id(ref: str) -> uuid.UUID | None:
    """O id da `brand_fonts` de um `perfil:<uuid>`; None para fonte padrão."""
    if ref.startswith(PERFIL_PREFIX):
        return uuid.UUID(ref[len(PERFIL_PREFIX):])
    return None


def check_refs(kit: KitTokens, ctx: RefContext) -> None:
    """Regras cruzadas do data-model. Com `ligado = false` a seção continua validada, mas a
    ausência da imagem, da conta ou do logo só é erro com a seção ligada (o padrão de um perfil
    sem conta é marca d'água em texto, desligada e sem conta)."""
    keys = {c.chave for c in kit.palette}
    for field, ref in color_fields(kit):
        if ref.startswith(PALETTE_PREFIX) and ref[len(PALETTE_PREFIX):] not in keys:
            raise KitInvalid(field, f"a cor {ref} não está na paleta")
    for field, ref in font_fields(kit):
        font_id = perfil_font_id(ref)
        if font_id is not None and font_id not in ctx.active_font_ids:
            raise KitInvalid(field, "fonte não encontrada ou arquivada")

    wm = kit.watermark
    if wm.imagem_id is not None and wm.imagem_id not in ctx.watermark_image_ids:
        raise KitInvalid("watermark.imagem_id", "imagem de marca d'água não encontrada")
    if wm.conta_id is not None and wm.conta_id not in ctx.conta_ids:
        raise KitInvalid("watermark.conta_id", "conta não encontrada ou arquivada")
    if wm.ligado:
        if wm.tipo == "imagem" and wm.imagem_id is None:
            raise KitInvalid("watermark.imagem_id", "escolha a imagem da marca d'água")
        if wm.tipo == "texto" and wm.conta_id is None:
            raise KitInvalid("watermark.conta_id", "escolha a conta do @")
        if wm.tipo == "logo" and not ctx.has_logo:
            raise KitInvalid("watermark.tipo", "o perfil não tem logo")
    if kit.end_card.ligado and kit.end_card.mostrar_logo and not ctx.has_logo:
        raise KitInvalid("endCard.mostrar_logo", "o perfil não tem logo")
    for section in _FUNDO_SECTIONS:
        sec, field = getattr(kit, section), f"{_field_name(section)}.fundo_imagem_id"
        if sec.fundo_imagem_id is not None and sec.fundo_imagem_id not in ctx.fundo_image_ids:
            raise KitInvalid(field, "imagem de fundo não encontrada")
        if sec.ligado and sec.fundo_tipo == "imagem" and sec.fundo_imagem_id is None:
            raise KitInvalid(field, "escolha a imagem de fundo")


# ---- resolução ----

def resolve_color(ref: str, palette: list[Cor]) -> str:
    """Hex de uma `CorRef` (a referência já foi conferida por `check_refs`)."""
    if ref.startswith(PALETTE_PREFIX):
        key = ref[len(PALETTE_PREFIX):]
        return next(c.valor for c in palette if c.chave == key)
    return ref


def resolve_tokens(kit: KitTokens, fonts: Mapping[str, Any],
                   fundos: Mapping[uuid.UUID, Mapping[str, Any]] | None = None
                   ) -> dict[str, Any]:
    """As seções com as cores em hex e cada `fonte` trocada por `fonts[ref]`.

    `fonts` precisa ter todas as `font_refs(kit)`; o valor é o que o consumidor precisa
    (exportação: nome, família e link; corte: `object_key`). Chaves em snake_case (`end_card`).
    `fundos` faz o mesmo com as `fundo_image_ids(kit)`: o gancho e o card final com
    `fundo_tipo = imagem` recebem as chaves de `fundos[id]` (exportação: `fundo_imagem_url`;
    corte: `fundo_imagem_key`).
    """
    out = kit.sections()
    for section in _TOKEN_SECTIONS:
        data = out[section]
        for name, value in data.items():
            if name.startswith("cor_"):
                data[name] = resolve_color(value, kit.palette)
        data["fonte"] = fonts[data["fonte"]]
    for section in _FUNDO_SECTIONS:
        sec = getattr(kit, section)
        if fundos is not None and sec.fundo_tipo == "imagem" and sec.fundo_imagem_id is not None:
            out[section].update(fundos[sec.fundo_imagem_id])
    return out


# ---- mensagens de validação em pt-BR ----

_MESSAGES: dict[str, str] = {
    "missing": "obrigatório",
    "extra_forbidden": "campo desconhecido",
    "less_than_equal": "deve ser no máximo {le}",
    "less_than": "deve ser menor que {lt}",
    "greater_than_equal": "deve ser no mínimo {ge}",
    "greater_than": "deve ser maior que {gt}",
    "string_too_long": "no máximo {max_length} caracteres",
    "too_long": "no máximo {max_length} itens",
    "too_short": "no mínimo {min_length} itens",
    "literal_error": "opção inválida (aceitas: {expected})",
    "string_pattern_mismatch": "formato inválido",
    "json_invalid": "JSON inválido",
    "uuid_parsing": "identificador inválido",
    "uuid_type": "identificador inválido",
}
_TYPE_ERRORS = ("string_type", "int_type", "int_parsing", "int_from_float", "float_type",
                "float_parsing", "bool_type", "bool_parsing", "list_type", "model_type",
                "dict_type", "model_attributes_type")


def error_message(error: Mapping[str, Any]) -> str:
    """`campo: mensagem` de um erro do Pydantic (ou do FastAPI), sem o prefixo `body`."""
    loc = [str(p) for p in error.get("loc", ()) if p not in ("body", "query", "path")]
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}
    if kind == "string_too_short":
        msg = ("não pode ficar vazio" if ctx.get("min_length") == 1
               else f"no mínimo {ctx.get('min_length')} caracteres")
    elif kind in _MESSAGES:
        try:
            msg = _MESSAGES[kind].format(**ctx)
        except (KeyError, IndexError):
            msg = error.get("msg", "inválido")
    elif kind in _TYPE_ERRORS:
        msg = "tipo inválido"
    else:  # erros próprios (PydanticCustomError) já vêm em pt-BR
        msg = error.get("msg", "inválido")
    field = ".".join(loc)
    return f"{field}: {msg}" if field else msg
