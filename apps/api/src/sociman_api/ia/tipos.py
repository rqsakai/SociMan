"""Registro dos tipos de campo do assistente (research R1): código, não tabela.

O tipo decide o contexto carregado, o schema de saída pedido ao Claude, a validação e onde a
aplicação é marcada. Os limites repetem os schemas reais dos campos (`AssetPatch`,
`UpdatePerfilIn`, `KitTokens`, `UpdatePostagemIn`); o `tests/unit/test_ia_tipos.py` cruza os dois.
O dono só ajusta o texto das regras (`ia_regras`); o padrão fica em `regras_padrao.py`.
"""

from dataclasses import dataclass
from typing import Literal

from sociman_api.ia.regras_padrao import PADROES

Entidade = Literal["asset", "perfil", "kit", "postagem", "guia"]
Idioma = Literal["en", "perfil"]
UsaGuia = Literal["completo", "so_proibidas"]
Formato = Literal["texto", "lista", "sugestoes", "textos_postagem", "guia", "variacoes"]
TipoCampoId = Literal[
    "avatar.descricao_prompt", "avatar.tom_de_voz", "avatar.regras_imagem",
    "cenario.prompt_ambiente", "asset.nome", "asset.descricao", "perfil.bio", "kit.bordoes",
    "kit.series", "postagem.titulo", "postagem.descricao", "postagem.hashtags",
    "postagem.textos", "guia.montar", "guia.testar",
]

MAX_SUGESTOES = 10


@dataclass(frozen=True)
class Limites:
    max_chars: int | None = None
    min_chars: int | None = None
    uma_linha: bool = False
    trim: bool = True  # False: o prompt do avatar e do cenário é guardado como veio (FR-009 da 007)
    max_itens: int | None = None
    min_itens: int | None = None
    max_chars_item: int | None = None
    unicos: bool = False  # sem repetir, sem diferenciar maiúsculas
    normalizar: Literal["hashtag"] | None = None
    max_sugestoes: int | None = None  # só no formato `sugestoes`


@dataclass(frozen=True)
class TipoCampo:
    id: str
    rotulo: str
    entidade: Entidade
    campos: tuple[str, ...]  # atributos do modelo (e chaves do snapshot do histórico)
    onde: str
    idioma: Idioma
    formato: Formato
    limites: Limites
    tipos_asset: frozenset[str] | None = None  # só quando a entidade é asset
    # Spec 017 (Q1): "so_proibidas" recebe só as palavras proibidas do guia do perfil.
    usa_guia: UsaGuia = "completo"
    regras_de: str | None = None  # usa as regras de outro tipo (não tem regra própria)
    listar_regras: bool = True  # False: não aparece em "Assistente de IA › Regras"

    @property
    def padrao(self) -> str:
        return PADROES[self.regras_de or self.id][1]

    @property
    def padrao_versao(self) -> int:
        return PADROES[self.regras_de or self.id][0]


_TEXTO_2000 = Limites(max_chars=2000)
_PROMPT = Limites(max_chars=2000, trim=False)

_LISTA: tuple[TipoCampo, ...] = (
    TipoCampo("avatar.descricao_prompt", "Descrição para prompts do avatar", "asset", ("prompt",),
              "Assets › Avatar › Descrição para prompts", "en", "texto", _PROMPT,
              frozenset({"avatar"}), usa_guia="so_proibidas"),
    TipoCampo("avatar.tom_de_voz", "Tom de voz do avatar", "asset", ("voice_tone",),
              "Assets › Avatar › Tom de voz", "perfil", "texto", Limites(max_chars=500),
              frozenset({"avatar"})),
    TipoCampo("avatar.regras_imagem", "Regras de imagem do avatar", "asset", ("image_rules",),
              "Assets › Avatar › Regras de imagem", "perfil", "texto", _TEXTO_2000,
              frozenset({"avatar"}), usa_guia="so_proibidas"),
    TipoCampo("cenario.prompt_ambiente", "Prompt do ambiente do cenário", "asset", ("prompt",),
              "Assets › Cenário › Prompt do ambiente", "en", "texto", _PROMPT,
              frozenset({"cenario"}), usa_guia="so_proibidas"),
    TipoCampo("asset.nome", "Nome do asset", "asset", ("name",), "Assets › Dados › Nome",
              "perfil", "texto", Limites(max_chars=80, min_chars=1, uma_linha=True)),
    TipoCampo("asset.descricao", "Notas do asset", "asset", ("description",),
              "Assets › Dados › Notas", "perfil", "texto", _TEXTO_2000),
    TipoCampo("perfil.bio", "Descrição do perfil", "perfil", ("bio",),
              "Perfis › Editar › Descrição", "perfil", "texto", _TEXTO_2000),
    TipoCampo("kit.bordoes", "Bordões", "kit", ("catchphrases",),
              "Perfis › Marca › Bordões", "perfil", "sugestoes",
              Limites(max_itens=20, max_chars_item=120, unicos=True,
                      max_sugestoes=MAX_SUGESTOES)),
    TipoCampo("kit.series", "Séries", "kit", ("series",), "Perfis › Marca › Séries", "perfil",
              "sugestoes", Limites(max_itens=20, max_chars_item=60, unicos=True,
                                   max_sugestoes=MAX_SUGESTOES)),
    TipoCampo("postagem.titulo", "Título da postagem", "postagem", ("titulo",),
              "Cortes › Postagem › Título", "perfil", "texto",
              Limites(max_chars=100, uma_linha=True)),
    TipoCampo("postagem.descricao", "Descrição da postagem", "postagem", ("descricao",),
              "Cortes › Postagem › Descrição", "perfil", "texto", _TEXTO_2000),
    TipoCampo("postagem.hashtags", "Hashtags da postagem", "postagem", ("hashtags",),
              "Cortes › Postagem › Hashtags", "perfil", "lista",
              Limites(max_itens=8, min_itens=3, max_chars_item=50, unicos=True,
                      normalizar="hashtag")),
    TipoCampo("postagem.textos", "Textos da postagem (título, descrição e hashtags)",
              "postagem", ("titulo", "descricao", "hashtags"),
              "Cortes › Postagem › Sugerir textos", "perfil", "textos_postagem",
              Limites(max_chars=100, max_itens=8, min_itens=3, max_chars_item=50, unicos=True,
                      normalizar="hashtag")),
    # Spec 017 (R9, R10): montar o guia (proposta que preenche o formulário, só vale ao salvar)
    # e testar o guia (3 textos de postagem com as regras de `postagem.textos`).
    TipoCampo("guia.montar", "Guia de comunicação (montar com IA)", "guia",
              ("tom", "faca", "nao_faca", "vocabulario", "proibidas", "emojis",
               "emojis_preferidos"),
              "Perfis › Guia › Montar com IA", "perfil", "guia", Limites()),
    TipoCampo("guia.testar", "Teste do guia de comunicação (3 textos de postagem)", "postagem",
              ("titulo", "descricao", "hashtags"), "Perfis › Guia › Testar guia", "perfil",
              "variacoes",
              Limites(max_chars=100, max_itens=8, min_itens=3, max_chars_item=50, unicos=True,
                      normalizar="hashtag"),
              regras_de="postagem.textos", listar_regras=False),
)

TIPOS: dict[str, TipoCampo] = {t.id: t for t in _LISTA}
