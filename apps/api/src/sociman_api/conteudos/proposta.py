"""Proposta do OpenShorts (emenda da spec 014, T074): o título, a descrição, o gancho e a nota
que o OpenShorts gravou no corte (`openshorts_title`, `openshorts_description`, `hook_text`,
`openshorts_score`).

Só existe no conteúdo de origem corte importado do OpenShorts; nas outras origens (e no corte
enviado à mão) é None. Todo destino novo nasce com o título e a descrição dela quando vierem
vazios, cortados nos limites do destino (100 e 2.000 caracteres): editáveis, o operador valida.
"""

from dataclasses import dataclass

from sociman_api.cortes.models import Corte, CorteOrigem
from sociman_api.postagem import textos


@dataclass(frozen=True)
class Proposta:
    titulo: str | None
    descricao: str | None
    gancho: str | None
    score: int | None


def _limpo(valor: str | None) -> str | None:
    valor = (valor or "").strip()
    return valor or None


def cortar(texto: str, limite: int) -> str:
    """Corta no limite sem partir palavra (quando há um espaço na segunda metade)."""
    texto = texto.strip()
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    espaco = corte.rfind(" ")
    if espaco >= limite // 2:
        corte = corte[:espaco]
    return corte.rstrip(" ,;:-–—")


def do_corte(corte: Corte | None) -> Proposta | None:
    if corte is None or corte.origem != CorteOrigem.openshorts:
        return None
    return Proposta(titulo=_limpo(corte.openshorts_title),
                    descricao=_limpo(corte.openshorts_description),
                    gancho=_limpo(corte.hook_text), score=corte.openshorts_score)


def textos_iniciais(corte: Corte | None) -> tuple[str, str]:
    """(título, descrição) para um destino novo, já nos limites; vazios sem proposta."""
    proposta = do_corte(corte)
    if proposta is None:
        return "", ""
    return (cortar(proposta.titulo or "", textos.TITULO_MAX),
            cortar(proposta.descricao or "", textos.DESCRICAO_MAX))
