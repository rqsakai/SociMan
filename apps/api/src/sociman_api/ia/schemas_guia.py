"""Modelos Pydantic do guia de comunicação (contracts/http-api.md da spec 017, "Tipos"). JSON em
camelCase.

Os limites do R2 **não** ficam aqui: o service confere cada item e devolve os erros campo a
campo (`details.fields`, US1-4), e o SPA lê os números de `limites`. Aqui só há tetos de
proteção do corpo, bem acima dos do guia.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.ia import guia
from sociman_api.ia.aplicacao import IaAplicacoes
from sociman_api.perfis.schemas import UserRef

# Tetos de proteção (o limite de verdade é o do R2, conferido no service).
_LISTA = 60
_ITEM = 1000
_TEXTO = 5000

GuiaEmojis = Literal["nao", "moderado", "livre"]
Item = Annotated[str, StringConstraints(max_length=_ITEM)]
Lista = Annotated[list[Item], Field(max_length=_LISTA)]


class Exemplo(CamelModel):
    tipo: Literal["titulo", "legenda", "bordao"]
    texto: Annotated[str, StringConstraints(max_length=_TEXTO)]


class GuiaCampos(CamelModel):
    tom: Annotated[str, StringConstraints(max_length=_TEXTO)] = ""
    faca: Lista = Field(default_factory=list)
    nao_faca: Lista = Field(default_factory=list)
    vocabulario: Lista = Field(default_factory=list)
    proibidas: Lista = Field(default_factory=list)
    emojis: GuiaEmojis | None = None  # null = não definido (na conta: herda do perfil)
    emojis_preferidos: Lista = Field(default_factory=list)
    hashtags_fixas: Lista = Field(default_factory=list)  # normalizadas na resposta
    max_hashtags_fixas: int | None = None  # só na conta: 0..8, null = 5 (Q3)
    exemplos: Annotated[list[Exemplo], Field(max_length=_LISTA)] = Field(default_factory=list)

    def dominio(self) -> guia.GuiaCampos:
        return guia.GuiaCampos(
            tom=self.tom, faca=tuple(self.faca), nao_faca=tuple(self.nao_faca),
            vocabulario=tuple(self.vocabulario), proibidas=tuple(self.proibidas),
            emojis=self.emojis, emojis_preferidos=tuple(self.emojis_preferidos),
            hashtags_fixas=tuple(self.hashtags_fixas),
            max_hashtags_fixas=self.max_hashtags_fixas,
            exemplos=tuple({"tipo": e.tipo, "texto": e.texto} for e in self.exemplos))

    @classmethod
    def de_dominio(cls, c: guia.GuiaCampos) -> "GuiaCampos":
        return cls(tom=c.tom, faca=list(c.faca), nao_faca=list(c.nao_faca),
                   vocabulario=list(c.vocabulario), proibidas=list(c.proibidas),
                   emojis=c.emojis, emojis_preferidos=list(c.emojis_preferidos),
                   hashtags_fixas=list(c.hashtags_fixas),
                   max_hashtags_fixas=c.max_hashtags_fixas,
                   exemplos=[Exemplo(tipo=e["tipo"], texto=e["texto"])  # type: ignore[arg-type]
                             for e in c.exemplos])


class GuiaLimites(CamelModel):
    tom_max: int = guia.TOM_MAX
    regras_itens: int = guia.REGRAS_ITENS
    regra_max: int = guia.REGRA_MAX
    vocabulario_itens: int = guia.VOCABULARIO_ITENS
    termo_max: int = guia.TERMO_MAX
    proibidas_itens: int = guia.PROIBIDAS_ITENS
    emojis_itens: int = guia.EMOJIS_ITENS
    emoji_max: int = guia.EMOJI_MAX
    hashtags_fixas_perfil: int = guia.FIXAS_PERFIL_MAX  # teto das fixas do perfil
    hashtags_fixas_padrao: int = guia.FIXAS_PADRAO  # máximo da conta quando é null
    hashtags_fixas_teto: int = guia.FIXAS_TETO  # limite de hashtags da postagem
    exemplos: int = guia.EXEMPLOS
    exemplo_max: int = guia.EXEMPLO_MAX
    total_max: int = guia.TOTAL_MAX


class Guia(CamelModel):
    id: UUID | None  # null = nunca editado
    perfil_id: UUID
    conta_id: UUID | None
    campos: GuiaCampos
    tamanho: int  # a soma de caracteres (R2)
    version: int  # 0 = nunca editado
    updated_at: datetime | None
    updated_by: UserRef | None
    limites: GuiaLimites = Field(default_factory=GuiaLimites)


class GuiaEfetivo(CamelModel):
    proibidas: list[str]
    hashtags_fixas: list[str]
    emojis: GuiaEmojis | None
    emojis_preferidos: list[str]
    max_hashtags_fixas: int  # conta.maxHashtagsFixas ?? 5


class Conflito(CamelModel):
    campo: Literal["emojis", "faca", "naoFaca", "hashtagsFixas"]
    perfil: str
    conta: str
    mensagem: str


class GuiaIn(CamelModel):
    version: Annotated[int, Field(ge=0)]  # 0 = nunca editado (cria a linha)
    campos: GuiaCampos
    ia: IaAplicacoes | None = None  # só { tipoCampo: "guia.montar", chamadaId } (008 R10)


class GuiaOut(CamelModel):
    guia: Guia


class GuiaContaOut(CamelModel):
    guia: Guia  # o da conta
    perfil: Guia  # o do perfil (só leitura nesta tela)
    efetivo: GuiaEfetivo  # o que o assistente usa de fato nas garantias
    conflitos: list[Conflito]  # avisos; não bloqueiam


# ---- montar e testar (assistente) ----

class MontarIn(CamelModel):
    perfil_id: UUID
    conta_id: UUID | None = None  # montar o guia da conta
    descricao: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                                max_length=1000)]
    guia_atual: GuiaCampos = Field(default_factory=GuiaCampos)
    sessao_id: UUID
    anteriores: Annotated[list[UUID], Field(max_length=5)] = Field(default_factory=list)


class AlvoTeste(CamelModel):
    entity_type: Literal["corte", "conteudo"]
    entity_id: UUID


class TestarIn(CamelModel):
    __test__ = False  # não é uma classe de teste do pytest

    perfil_id: UUID
    nivel: Literal["perfil", "conta"]  # qual nível vem do formulário
    conta_id: UUID  # obrigatório (texto de postagem é de uma plataforma)
    alvo: AlvoTeste
    guia: GuiaCampos
