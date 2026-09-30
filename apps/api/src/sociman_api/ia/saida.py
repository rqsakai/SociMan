"""Saída estruturada por formato e a validação depois do parse (research R4).

Um modelo Pydantic por formato vai ao `beta.messages.parse`; todos trazem `explicacao` e
`avisos`. Depois do parse:
- `problemas` lista o que merece **uma** nova tentativa (com a mensagem do erro);
- `finalizar` monta o que vai para `ia_chamadas.proposta` (`{"texto"}`, `{"itens"}` ou
  `{"titulo", "descricao", "hashtags"}`), com os avisos do servidor. Texto acima do limite
  volta **sem corte** com `excede = true`; sugestões repetidas saem com aviso; hashtags e
  `postagem.textos` mantêm o ajuste da 006. Sem como salvar, levanta `Invalida`.

Spec 017: os dois recebem o `GuiaEfetivo` (R6, R7). As hashtags fixas entram sempre, primeiro,
e contam no máximo de 8 (as do modelo saem, as fixas nunca); uma palavra proibida na proposta
pede a segunda tentativa e, se continuar, vai para `proibidas` com o aviso (o Aplicar sem editar
é recusado em `aplicacao.py`). Formatos novos: `guia` (o "montar guia", R9) e `variacoes` (o
"testar guia", 3 textos de postagem, R10).
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from sociman_api.ia import guia as guia_mod
from sociman_api.ia.tipos import TipoCampo
from sociman_api.postagem import textos  # normalizar_hashtags e os limites da postagem

EXPLICACAO_MAX = 400
AVISOS_MAX = 5
AVISO_MAX_CHARS = 300


class PropostaTexto(BaseModel):
    proposta: str
    explicacao: str
    avisos: list[str]


class PropostaLista(BaseModel):
    itens: list[str]
    explicacao: str
    avisos: list[str]


class PropostaSugestoes(BaseModel):
    itens: list[str]
    explicacao: str
    avisos: list[str]


class PropostaTextosPostagem(BaseModel):
    titulo: str
    descricao: str
    hashtags: list[str]
    explicacao: str
    avisos: list[str]


class PropostaGuia(BaseModel):
    """Sem hashtags fixas, máximo de fixas e exemplos: esses são do dono (R9)."""

    tom: str
    faca: list[str]
    nao_faca: list[str]
    vocabulario: list[str]
    proibidas: list[str]
    emojis: Literal["nao", "moderado", "livre"] | None
    emojis_preferidos: list[str]
    explicacao: str
    avisos: list[str]


class VariacaoPostagem(BaseModel):
    titulo: str
    descricao: str
    hashtags: list[str]


class PropostaVariacoes(BaseModel):
    variacoes: list[VariacaoPostagem]
    explicacao: str
    avisos: list[str]


SCHEMAS: dict[str, type[BaseModel]] = {
    "texto": PropostaTexto, "lista": PropostaLista, "sugestoes": PropostaSugestoes,
    "textos_postagem": PropostaTextosPostagem, "guia": PropostaGuia,
    "variacoes": PropostaVariacoes,
}
VARIACOES = 3


class Invalida(Exception):
    """A resposta veio fora do formato ou sem nada aproveitável."""


@dataclass(frozen=True)
class Excluir:
    """Nas sugestões: o que a proposta não pode repetir (lista atual, aceitos e rejeitados)."""

    atuais: tuple[str, ...] = ()
    aceitos: tuple[str, ...] = ()
    rejeitados: tuple[str, ...] = ()


NADA = Excluir()
SEM_GUIA = guia_mod.GuiaEfetivo()


@dataclass
class Validada:
    proposta: dict[str, Any]
    explicacao: str = ""
    avisos: list[str] = field(default_factory=list)
    excede: bool = False
    ajustes: list[str] = field(default_factory=list)
    proibidas: list[str] = field(default_factory=list)  # spec 017: as encontradas na proposta


def _chave(item: str) -> str:
    return item.strip().casefold()


def _texto(tipo: TipoCampo, valor: str) -> str:
    return valor.strip() if tipo.limites.trim else valor


def _sugestoes_validas(tipo: TipoCampo, itens: Iterable[str], excluir: Excluir
                       ) -> tuple[list[str], list[str]]:
    """(sugestões que ficam, avisos). Remove vazias, repetidas e as que repetem a lista atual,
    um aceito ou um rejeitado; corta no máximo por geração."""
    vistas = {_chave(i) for i in (*excluir.atuais, *excluir.aceitos, *excluir.rejeitados)}
    fora = {_chave(i) for i in excluir.atuais}
    ficam: list[str] = []
    vazias = repetidas = ja_vistas = 0
    for raw in itens:
        item = raw.strip()
        if not item:
            vazias += 1
            continue
        chave = _chave(item)
        if any(_chave(f) == chave for f in ficam):
            repetidas += 1
        elif chave in vistas:
            ja_vistas += 1
        else:
            ficam.append(item)
    avisos = []
    if vazias:
        avisos.append(f"Removi {vazias} sugestão(ões) vazia(s).")
    if repetidas:
        avisos.append(f"Removi {repetidas} sugestão(ões) repetida(s).")
    if ja_vistas:
        onde = "da lista ou das já vistas nesta sessão" if fora else "das já vistas nesta sessão"
        avisos.append(f"Removi {ja_vistas} sugestão(ões) igual(is) a itens {onde}.")
    maximo = tipo.limites.max_sugestoes or len(ficam)
    if len(ficam) > maximo:
        ficam = ficam[:maximo]
        avisos.append(f"Mostrei só as {maximo} primeiras sugestões.")
    return ficam, avisos


def problemas(tipo: TipoCampo, parsed: BaseModel, excluir: Excluir = NADA,
              efetivo: guia_mod.GuiaEfetivo = SEM_GUIA) -> list[str]:
    """O que pede uma nova tentativa (lista vazia = passou)."""
    lim = tipo.limites
    erros: list[str] = []
    fixas = _fixas(efetivo)
    if isinstance(parsed, PropostaTexto):
        texto = _texto(tipo, parsed.proposta)
        if not texto.strip():
            erros.append("a proposta veio vazia")
        if lim.max_chars is not None and len(texto) > lim.max_chars:
            erros.append(f"a proposta passou de {lim.max_chars} caracteres ({len(texto)})")
        if lim.uma_linha and "\n" in texto.strip():
            erros.append("a proposta precisa ser uma linha só")
    elif isinstance(parsed, PropostaSugestoes):
        ficam, _ = _sugestoes_validas(tipo, parsed.itens, excluir)
        if not ficam:
            erros.append("nenhuma sugestão nova e válida (todas vazias ou repetidas)")
        maior = [i for i in ficam if lim.max_chars_item and len(i) > lim.max_chars_item]
        if maior:
            erros.append(f"{len(maior)} sugestão(ões) passou(aram) de {lim.max_chars_item} "
                         "caracteres")
    elif isinstance(parsed, PropostaLista):
        erros.extend(_problemas_hashtags(parsed.itens, fixas, lim.min_itens or 0,
                                         lim.max_itens or textos.HASHTAGS_MAX))
    elif isinstance(parsed, PropostaTextosPostagem):
        erros.extend(_problemas_postagem(parsed, fixas))
    elif isinstance(parsed, PropostaVariacoes):
        if len(parsed.variacoes) != VARIACOES:
            erros.append(f"vieram {len(parsed.variacoes)} variações; o pedido é de {VARIACOES}")
        for n, v in enumerate(parsed.variacoes[:VARIACOES], start=1):
            erros.extend(f"variação {n}: {e}" for e in _problemas_postagem(v, fixas))
    elif isinstance(parsed, PropostaGuia):
        erros.extend(_problemas_guia(parsed))
    erros.extend(f"usou a palavra proibida {p}"
                 for p in guia_mod.achar_proibidas(_textos(parsed), efetivo.proibidas))
    return erros


def _textos(parsed: BaseModel) -> list[str]:
    """Todo texto da proposta em que uma palavra proibida conta (R7). O `guia` não entra: as
    proibidas propostas são a própria lista (a validação do save confere o resto)."""
    if isinstance(parsed, PropostaTexto):
        return [parsed.proposta]
    if isinstance(parsed, PropostaLista | PropostaSugestoes):
        return list(parsed.itens)
    if isinstance(parsed, PropostaTextosPostagem):
        return [parsed.titulo, parsed.descricao, *parsed.hashtags]
    if isinstance(parsed, PropostaVariacoes):
        return [t for v in parsed.variacoes for t in (v.titulo, v.descricao, *v.hashtags)]
    return []


# ---- hashtags fixas do guia (R6 da 017) ----

def _fixas(efetivo: guia_mod.GuiaEfetivo) -> list[str]:
    return textos.normalizar_hashtags(list(efetivo.hashtags_fixas))


def _com_fixas(modelo: Sequence[str], fixas: Sequence[str]) -> tuple[list[str], bool]:
    """(fixas primeiro, depois as do modelo sem repetir; se o servidor precisou acrescentar
    alguma fixa). `modelo` já normalizado; quem chama corta em 8 (as do modelo saem)."""
    resto = [h for h in modelo if h not in fixas]
    incluiu = any(f not in modelo for f in fixas)
    return [*fixas, *resto], incluiu


def _problemas_hashtags(brutas: Sequence[str], fixas: Sequence[str], minimo: int,
                        maximo: int) -> list[str]:
    hashtags = textos.normalizar_hashtags(list(brutas))
    if not fixas:
        if not minimo <= len(hashtags) <= maximo:
            return [f"são {len(hashtags)} hashtags válidas; o pedido é de {minimo} a {maximo}"]
        return []
    vagas = maximo - len(fixas)
    resto = [h for h in hashtags if h not in fixas]
    erros = []
    if vagas > 0 and len(resto) > vagas:
        erros.append(f"são {len(resto)} hashtags além das fixas; o pedido é de no máximo {vagas}")
    if len(fixas) + len(resto) < minimo:
        erros.append(f"são {len(resto)} hashtags válidas além das {len(fixas)} fixas; o pedido é "
                     f"de pelo menos {minimo - len(fixas)}")
    return erros


def _problemas_guia(p: PropostaGuia) -> list[str]:
    g = guia_mod
    erros = []
    if len(p.tom.strip()) > g.TOM_MAX:
        erros.append(f"o tom passou de {g.TOM_MAX} caracteres")
    for nome, itens, max_itens, max_item in _listas_guia(p):
        validos = [i.strip() for i in itens if i.strip()]
        if len(validos) > max_itens:
            erros.append(f"{nome}: são {len(validos)} itens; o máximo é {max_itens}")
        if any(len(i) > max_item for i in validos):
            erros.append(f"{nome}: um item passou de {max_item} caracteres")
    usadas = guia_mod.achar_proibidas([p.tom, *p.faca, *p.nao_faca, *p.vocabulario],
                                      [t for t in p.proibidas if t.strip()])
    erros.extend(f"a palavra proibida {x} aparece no próprio guia" for x in usadas)
    return erros


def _listas_guia(p: PropostaGuia) -> list[tuple[str, list[str], int, int]]:
    g = guia_mod
    return [("faca", p.faca, g.REGRAS_ITENS, g.REGRA_MAX),
            ("naoFaca", p.nao_faca, g.REGRAS_ITENS, g.REGRA_MAX),
            ("vocabulario", p.vocabulario, g.VOCABULARIO_ITENS, g.TERMO_MAX),
            ("proibidas", p.proibidas, g.PROIBIDAS_ITENS, g.TERMO_MAX),
            ("emojisPreferidos", p.emojis_preferidos, g.EMOJIS_ITENS, g.EMOJI_MAX)]


# ---- textos da postagem: o ajuste aprovado na 006 (research R9 da 006) ----

def _problemas_postagem(p: PropostaTextosPostagem | VariacaoPostagem,
                        fixas: Sequence[str] = ()) -> list[str]:
    erros = []
    if not p.titulo.strip():
        erros.append("o título veio vazio")
    if len(p.titulo.strip()) > textos.TITULO_MAX:
        erros.append(f"o título passou de {textos.TITULO_MAX} caracteres")
    if len(p.descricao.strip()) > textos.DESCRICAO_MAX:
        erros.append(f"a descrição passou de {textos.DESCRICAO_MAX} caracteres")
    erros.extend(_problemas_hashtags(p.hashtags, fixas, textos.HASHTAGS_MIN, textos.HASHTAGS_MAX))
    return erros


def _cortar_na_palavra(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    espaco = corte.rfind(" ")
    return (corte[:espaco] if espaco > limite // 2 else corte).rstrip(" ,;:-")


def _ajustar_postagem(p: PropostaTextosPostagem | VariacaoPostagem, fixas: Sequence[str] = ()
                      ) -> tuple[dict[str, Any], list[str]]:
    """Corta e completa (como a 006), com as fixas do guia primeiro (017). `Invalida` se não há
    como salvar."""
    ajustes: list[str] = []
    titulo, descricao = p.titulo.strip(), p.descricao.strip()
    hashtags = textos.normalizar_hashtags(p.hashtags)
    if not titulo:
        raise Invalida("o título veio vazio")
    if len(titulo) > textos.TITULO_MAX:
        titulo = _cortar_na_palavra(titulo, textos.TITULO_MAX)
        ajustes.append("titulo_cortado")
    if len(descricao) > textos.DESCRICAO_MAX:
        descricao = _cortar_na_palavra(descricao, textos.DESCRICAO_MAX)
        ajustes.append("descricao_cortada")
    if hashtags != [h.strip() for h in p.hashtags]:
        ajustes.append("hashtags_normalizadas")
    if fixas:
        hashtags, incluiu = _com_fixas(hashtags, fixas)
        if incluiu:
            ajustes.append("hashtags_fixas_incluidas")
    if len(hashtags) > textos.HASHTAGS_MAX:
        hashtags = hashtags[:textos.HASHTAGS_MAX]
        ajustes.append("hashtags_truncadas")
    if len(hashtags) < textos.HASHTAGS_MIN:
        raise Invalida(f"só {len(hashtags)} hashtags válidas")
    return {"titulo": titulo, "descricao": descricao, "hashtags": hashtags}, ajustes


def _cortar_na_frase(texto: str, limite: int) -> str:
    texto = texto.strip()
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
    return corte[:fim + 1] if fim > limite // 3 else corte.rstrip() + "…"


_ESPACOS = re.compile(r"\s*\n\s*")


def _avisos_do_modelo(avisos: Iterable[str]) -> list[str]:
    limpos = [a.strip()[:AVISO_MAX_CHARS] for a in avisos if a and a.strip()]
    return limpos[:AVISOS_MAX]


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")


def _avisos_do_guia(tipo: TipoCampo, parsed: BaseModel, out: Validada,
                    efetivo: guia_mod.GuiaEfetivo) -> None:
    out.proibidas = guia_mod.achar_proibidas(_textos(parsed), efetivo.proibidas)
    if out.proibidas:
        out.avisos.append("A proposta usa uma palavra proibida pelo guia "
                          f"({', '.join(out.proibidas)}); edite antes de aplicar.")
    if efetivo.emojis == "nao" and any(_EMOJI.search(t) for t in _textos(parsed)):
        out.avisos.append("A proposta usa emoji, mas o guia diz para não usar; edite se "
                          "precisar.")
    if efetivo.hashtags_fixas and (tipo.limites.normalizar == "hashtag"
                                   or tipo.formato == "variacoes"):
        out.avisos.extend(efetivo.avisos)


def finalizar(tipo: TipoCampo, parsed: BaseModel, excluir: Excluir = NADA,
              efetivo: guia_mod.GuiaEfetivo = SEM_GUIA) -> Validada:
    """A proposta que vai para a tela e para o registro. `Invalida` se não há o que mostrar."""
    lim = tipo.limites
    fixas = _fixas(efetivo)
    out = Validada(proposta={}, explicacao=_cortar_na_frase(parsed.explicacao, EXPLICACAO_MAX),
                   avisos=_avisos_do_modelo(parsed.avisos))
    if isinstance(parsed, PropostaTexto):
        texto = _texto(tipo, parsed.proposta)
        if not texto.strip():
            raise Invalida("a proposta veio vazia")
        if lim.uma_linha and "\n" in texto.strip():
            texto = _ESPACOS.sub(" ", texto.strip())
            out.ajustes.append("uma_linha")
        if lim.max_chars is not None and len(texto) > lim.max_chars:
            out.excede = True
            out.avisos.append(f"A proposta tem {len(texto)} caracteres e o limite é "
                              f"{lim.max_chars}; edite antes de aplicar.")
        out.proposta = {"texto": texto}
    elif isinstance(parsed, PropostaSugestoes):
        ficam, avisos = _sugestoes_validas(tipo, parsed.itens, excluir)
        if not ficam:
            raise Invalida("nenhuma sugestão nova e válida")
        out.avisos.extend(avisos)
        maior = [i for i in ficam if lim.max_chars_item and len(i) > lim.max_chars_item]
        if maior:
            out.excede = True
            out.avisos.append(f"{len(maior)} sugestão(ões) passa(m) de {lim.max_chars_item} "
                              "caracteres; edite antes de marcar.")
        out.proposta = {"itens": ficam}
    elif isinstance(parsed, PropostaLista):
        hashtags = textos.normalizar_hashtags(parsed.itens)
        if hashtags != [h.strip() for h in parsed.itens]:
            out.ajustes.append("hashtags_normalizadas")
        if fixas:
            hashtags, incluiu = _com_fixas(hashtags, fixas)
            if incluiu:
                out.ajustes.append("hashtags_fixas_incluidas")
        if lim.max_itens is not None and len(hashtags) > lim.max_itens:
            hashtags = hashtags[:lim.max_itens]
            out.ajustes.append("hashtags_truncadas")
            out.avisos.append(f"Fiquei só com as {lim.max_itens} primeiras hashtags.")
        if len(hashtags) < (lim.min_itens or 0):
            raise Invalida(f"só {len(hashtags)} hashtags válidas")
        out.proposta = {"itens": hashtags}
    elif isinstance(parsed, PropostaTextosPostagem):
        out.proposta, out.ajustes = _ajustar_postagem(parsed, fixas)
        if "titulo_cortado" in out.ajustes:
            out.avisos.append(f"Cortei o título para caber em {textos.TITULO_MAX} caracteres.")
    elif isinstance(parsed, PropostaVariacoes):
        out.proposta, out.ajustes, avisos = _ajustar_variacoes(parsed, fixas)
        out.avisos.extend(avisos)
    elif isinstance(parsed, PropostaGuia):
        out.proposta, avisos = _ajustar_guia(parsed)
        out.avisos.extend(avisos)
    else:  # pragma: no cover
        raise TypeError(type(parsed).__name__)
    _avisos_do_guia(tipo, parsed, out, efetivo)
    return out


def _ajustar_variacoes(p: PropostaVariacoes, fixas: Sequence[str]
                       ) -> tuple[dict[str, Any], list[str], list[str]]:
    """Cada variação pelo ajuste da 006 e pelas fixas do guia em teste (R10)."""
    variacoes: list[dict[str, Any]] = []
    ajustes: list[str] = []
    for v in p.variacoes[:VARIACOES]:
        try:
            valor, extra = _ajustar_postagem(v, fixas)
        except Invalida:
            continue
        variacoes.append(valor)
        ajustes.extend(a for a in extra if a not in ajustes)
    if not variacoes:
        raise Invalida("nenhuma variação aproveitável")
    avisos = []
    if len(variacoes) < VARIACOES:
        avisos.append(f"Só {len(variacoes)} variação(ões) veio(vieram) aproveitável(is).")
    if "titulo_cortado" in ajustes:
        avisos.append(f"Cortei títulos para caber em {textos.TITULO_MAX} caracteres.")
    return {"variacoes": variacoes}, ajustes, avisos


def _itens_guia(nome: str, itens: Iterable[str], max_itens: int, max_item: int
                ) -> tuple[list[str], list[str]]:
    ficam: list[str] = []
    vistas: set[str] = set()
    longos = 0
    for raw in itens:
        item = raw.strip()
        chave = guia_mod.normalizar(item)
        if not item or chave in vistas:
            continue
        if len(item) > max_item:
            longos += 1
            continue
        vistas.add(chave)
        ficam.append(item)
    avisos = []
    if longos:
        avisos.append(f"Tirei {longos} item(ns) longo(s) demais de {nome}.")
    if len(ficam) > max_itens:
        ficam = ficam[:max_itens]
        avisos.append(f"Fiquei só com os {max_itens} primeiros itens de {nome}.")
    return ficam, avisos


_NOMES_GUIA = {"faca": "Faça", "naoFaca": "Não faça", "vocabulario": "Vocabulário",
               "proibidas": "Palavras proibidas", "emojisPreferidos": "Emojis preferidos"}


def _ajustar_guia(p: PropostaGuia) -> tuple[dict[str, Any], list[str]]:
    """A proposta do "montar guia" dentro dos limites do R2 (cabe no formulário)."""
    avisos: list[str] = []
    tom = p.tom.strip()
    if len(tom) > guia_mod.TOM_MAX:
        tom = _cortar_na_frase(tom, guia_mod.TOM_MAX - 1)
        avisos.append(f"Cortei o tom para caber em {guia_mod.TOM_MAX} caracteres.")
    campos: dict[str, Any] = {"tom": tom}
    for nome, itens, max_itens, max_item in _listas_guia(p):
        campos[nome], extra = _itens_guia(_NOMES_GUIA[nome], itens, max_itens, max_item)
        avisos.extend(extra)
    campos["emojis"] = p.emojis
    if not any(v for v in campos.values()):
        raise Invalida("o guia veio vazio")
    return {"guia": campos}, avisos
