"""Prompt do clipe local e avisos do keyframe (spec 011, research R7, FR-028 e FR-030): funções
puras, sem banco. O prompt do Flow (`cenas/prompt.py`) não muda.

Ordem do `montar_clipe`, em inglês, separado por espaço:
1. `acao` — a ação da cena, depois o plano, o movimento e o detalhe livre da câmera;
2. `avatar` — a descrição fixa do avatar (kit da 025), sem alteração, quando há avatar;
3. `boca` — `MOUTH_CLOSED`, quando há rosto (avatar e plano que não é `detalhe_produto`);
4. `ambiente` — `AMBIENTE_FIXO`, sempre (o MiniMax inventou fundo no giro);
5. `realismo` — o sufixo fixo.

A fala, o texto na tela e o áudio da 010 nunca entram: o formato é voice over, e o áudio do
modelo é descartado na montagem.
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

from sociman_api.cenas.avisos import Aviso
from sociman_api.cenas.models import CenaMovimento, CenaPlano
from sociman_api.cenas.prompt import MOVIMENTOS, PLANOS, AvatarIn, Parte, pronome

MOUTH_CLOSED = ("Her mouth stays closed in a gentle smile the whole time, she does not speak, her "
                "jaw does not move.")
_BOCA = {
    "She": MOUTH_CLOSED,
    "He": ("His mouth stays closed in a gentle smile the whole time, he does not speak, his jaw "
           "does not move."),
    "The person": ("The person's mouth stays closed in a gentle smile the whole time, they do not "
                   "speak, their jaw does not move."),
}
AMBIENTE_FIXO = ("The room, furniture, walls and lighting stay exactly the same for the whole "
                 "shot.")
REALISMO = "Natural real-time motion, realistic skin and fabric texture, sharp detail."

# FR-028: mudança de luz recolore o produto; "phone video" desenha a moldura do celular. Só avisam.
_LUZ = re.compile(
    r"\b(lighting|relight\w*|luz|luzes|ilumina\w*)\b"
    r"|\blights?\s+(change|changes|shift\w*|turns?)\b"
    r"|\bchang\w*\s+(the\s+)?light\w*\b",
    re.IGNORECASE)
_CELULAR = re.compile(r"\b(phone|smartphone|cell\s*phone|mobile)\s+(video|footage|recording)\b"
                      r"|\bv[ií]deo\s+de\s+celular\b", re.IGNORECASE)


class CenaClipe(Protocol):
    """O que o prompt do clipe lê da cena (o modelo `Cena` ou a `EntradaClipe`)."""

    acao: str
    plano: CenaPlano | None
    movimento: CenaMovimento | None
    camera: str | None


@dataclass(frozen=True)
class EntradaClipe:
    acao: str
    plano: CenaPlano | None = None
    movimento: CenaMovimento | None = None
    camera: str | None = None


@dataclass(frozen=True)
class PromptClipe:
    texto: str
    partes: list[Parte] = field(default_factory=list)


def _vazio(texto: str | None) -> bool:
    return texto is None or not texto.strip()


def _frase(texto: str) -> str:
    texto = texto.strip()
    return texto if texto[-1] in ".!?\"'" else f"{texto}."


def _acao(cena: CenaClipe) -> str:
    itens = [PLANOS[cena.plano] if cena.plano is not None else None,
             MOVIMENTOS[cena.movimento] if cena.movimento is not None else None,
             cena.camera.strip().rstrip(".") if not _vazio(cena.camera) else None]
    itens = [i for i in itens if i]
    acao = _frase(cena.acao)
    if not itens:
        return acao
    camera = ", ".join(itens)
    return f"{acao} {_frase(camera[0].upper() + camera[1:])}"


def montar_clipe(cena: CenaClipe, avatar_descricao: str | None,
                 tem_rosto: bool | None = None) -> PromptClipe:
    """`tem_rosto` ausente = há avatar e o plano não é `detalhe_produto`."""
    com_avatar = not _vazio(avatar_descricao)
    if tem_rosto is None:
        tem_rosto = com_avatar and cena.plano != CenaPlano.detalhe_produto
    partes = [Parte("acao", _acao(cena))]
    if com_avatar:
        partes.append(Parte("avatar", avatar_descricao))  # type: ignore[arg-type]  # sem alteração
    if tem_rosto:
        quem = pronome(AvatarIn(avatar_descricao, None, 0)) if com_avatar else "The person"
        partes.append(Parte("boca", _BOCA[quem]))
    partes.append(Parte("ambiente", AMBIENTE_FIXO))
    partes.append(Parte("realismo", REALISMO))
    texto = ""
    for p in partes:
        if texto and not texto[-1].isspace():
            texto += " "
        texto += p.texto
    return PromptClipe(texto=texto, partes=partes)


def avisos_keyframe(instrucao: str | None) -> list[Aviso]:
    """Avisos da instrução do keyframe (FR-028). Nenhum bloqueia."""
    if _vazio(instrucao):
        return []
    avisos: list[Aviso] = []
    if _LUZ.search(instrucao):  # type: ignore[arg-type]
        avisos.append(Aviso("keyframe_luz", "A instrução pede mudança de luz: isso costuma "
                            "recolorir o produto. Descreva o estado final sem mexer na luz.",
                            campo="keyframeInstrucao"))
    if _CELULAR.search(instrucao):  # type: ignore[arg-type]
        avisos.append(Aviso("keyframe_phone_video", 'A instrução cita "phone video": o modelo '
                            "desenha a moldura do celular. Tire essa expressão.",
                            campo="keyframeInstrucao"))
    return avisos
