"""Saída estruturada por formato e a validação depois do parse (research R4).

Um modelo Pydantic por formato vai ao `beta.messages.parse`; todos trazem `explicacao` e
`avisos`. Depois do parse:
- `problemas` lista o que merece **uma** nova tentativa (com a mensagem do erro);
- `finalizar` monta o que vai para `ia_chamadas.proposta` (`{"texto"}`, `{"itens"}` ou
  `{"titulo", "descricao", "hashtags"}`), com os avisos do servidor. Texto acima do limite
  volta **sem corte** com `excede = true`; sugestões repetidas saem com aviso; hashtags e
  `postagem.textos` mantêm o ajuste da 006. Sem como salvar, levanta `Invalida`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

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


SCHEMAS: dict[str, type[BaseModel]] = {
    "texto": PropostaTexto, "lista": PropostaLista, "sugestoes": PropostaSugestoes,
    "textos_postagem": PropostaTextosPostagem,
}


class Invalida(Exception):
    """A resposta veio fora do formato ou sem nada aproveitável."""


@dataclass(frozen=True)
class Excluir:
    """Nas sugestões: o que a proposta não pode repetir (lista atual, aceitos e rejeitados)."""

    atuais: tuple[str, ...] = ()
    aceitos: tuple[str, ...] = ()
    rejeitados: tuple[str, ...] = ()


NADA = Excluir()


@dataclass
class Validada:
    proposta: dict[str, Any]
    explicacao: str = ""
    avisos: list[str] = field(default_factory=list)
    excede: bool = False
    ajustes: list[str] = field(default_factory=list)


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


def problemas(tipo: TipoCampo, parsed: BaseModel, excluir: Excluir = NADA) -> list[str]:
    """O que pede uma nova tentativa (lista vazia = passou)."""
    lim = tipo.limites
    erros: list[str] = []
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
        hashtags = textos.normalizar_hashtags(parsed.itens)
        if not (lim.min_itens or 0) <= len(hashtags) <= (lim.max_itens or len(hashtags)):
            erros.append(f"são {len(hashtags)} itens válidos; o pedido é de {lim.min_itens} a "
                         f"{lim.max_itens}")
    elif isinstance(parsed, PropostaTextosPostagem):
        erros.extend(_problemas_postagem(parsed))
    return erros


# ---- textos da postagem: o ajuste aprovado na 006 (research R9 da 006) ----

def _problemas_postagem(p: PropostaTextosPostagem) -> list[str]:
    erros = []
    hashtags = textos.normalizar_hashtags(p.hashtags)
    if not p.titulo.strip():
        erros.append("o título veio vazio")
    if len(p.titulo.strip()) > textos.TITULO_MAX:
        erros.append(f"o título passou de {textos.TITULO_MAX} caracteres")
    if len(p.descricao.strip()) > textos.DESCRICAO_MAX:
        erros.append(f"a descrição passou de {textos.DESCRICAO_MAX} caracteres")
    if not textos.HASHTAGS_MIN <= len(hashtags) <= textos.HASHTAGS_MAX:
        erros.append(f"são {len(hashtags)} hashtags válidas; o pedido é de "
                     f"{textos.HASHTAGS_MIN} a {textos.HASHTAGS_MAX}")
    return erros


def _cortar_na_palavra(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    espaco = corte.rfind(" ")
    return (corte[:espaco] if espaco > limite // 2 else corte).rstrip(" ,;:-")


def _ajustar_postagem(p: PropostaTextosPostagem) -> tuple[dict[str, Any], list[str]]:
    """Corta e completa (como a 006). `Invalida` se não há como salvar."""
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


def finalizar(tipo: TipoCampo, parsed: BaseModel, excluir: Excluir = NADA) -> Validada:
    """A proposta que vai para a tela e para o registro. `Invalida` se não há o que mostrar."""
    lim = tipo.limites
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
        if lim.max_itens is not None and len(hashtags) > lim.max_itens:
            hashtags = hashtags[:lim.max_itens]
            out.ajustes.append("hashtags_truncadas")
            out.avisos.append(f"Fiquei só com as {lim.max_itens} primeiras hashtags.")
        if len(hashtags) < (lim.min_itens or 0):
            raise Invalida(f"só {len(hashtags)} hashtags válidas")
        out.proposta = {"itens": hashtags}
    elif isinstance(parsed, PropostaTextosPostagem):
        out.proposta, out.ajustes = _ajustar_postagem(parsed)
        if "titulo_cortado" in out.ajustes:
            out.avisos.append(f"Cortei o título para caber em {textos.TITULO_MAX} caracteres.")
    else:  # pragma: no cover
        raise TypeError(type(parsed).__name__)
    return out
