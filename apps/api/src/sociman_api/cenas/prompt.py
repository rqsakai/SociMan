"""Montagem do prompt para o Flow/Veo (research R2): função pura, sem banco.

Ordem fixa, uma parte depois da outra separadas por espaço:
1. `avatar` — a descrição do avatar **sem nenhuma alteração** (nem trim: FR-009 da 007; o texto
   do prompt começa com ela, byte a byte);
2. `regras` — as regras de imagem do avatar, como estão;
3. `acao` — com foto do produto, "<produto> exactly as in the reference image" (regra do
   shop-diretor), só quando a ação ainda não fala em "reference image";
4. `cenario` — o prompt do ambiente do cenário;
5. `camera` — plano e movimento por tabela fixa, mais o detalhe livre;
6. `estilo` — o da cena ou, vazio, o padrão do perfil;
7. `fala` — `<Pronome> looks at the camera and says: "<fala em pt-BR>"`;
8. `audio` — o ambiente.

No modo `quadros`, `Start frame: …` e `End frame: …` vêm antes de tudo. O texto na tela nunca
entra (é guia de edição; o negative bloqueia texto no vídeo, R12). Nada é traduzido.
"""

import re
from dataclasses import dataclass, field

from sociman_api.cenas.models import CenaModo, CenaMovimento, CenaPlano

PLANOS: dict[CenaPlano, str] = {
    CenaPlano.close: "close-up shot",
    CenaPlano.busto: "medium close-up shot",
    CenaPlano.medio: "medium shot",
    CenaPlano.americano: "medium full shot",
    CenaPlano.aberto: "wide shot",
    CenaPlano.detalhe_produto: "extreme close-up of the product",
}
MOVIMENTOS: dict[CenaMovimento, str] = {
    CenaMovimento.parada: "static camera",
    CenaMovimento.aproximacao: "slow push-in",
    CenaMovimento.afastamento: "slow pull-out",
    CenaMovimento.panoramica: "slow pan",
    CenaMovimento.camera_na_mao: "handheld camera",
}
REFERENCIA = "exactly as in the reference image"

_FEMININO = re.compile(r"\b(woman|girl|lady|she|her)\b", re.IGNORECASE)
_MASCULINO = re.compile(r"\b(man|boy|guy|he|his)\b", re.IGNORECASE)


@dataclass(frozen=True)
class AvatarIn:
    prompt: str | None
    image_rules: str | None
    version: int


@dataclass(frozen=True)
class CenarioIn:
    prompt: str | None
    version: int


@dataclass(frozen=True)
class Entrada:
    acao: str
    estilo_padrao: str
    negative_padrao: str
    avatar: AvatarIn | None = None
    cenario: CenarioIn | None = None
    plano: CenaPlano | None = None
    movimento: CenaMovimento | None = None
    camera: str | None = None
    fala: str | None = None
    estilo: str | None = None
    audio: str | None = None
    modo: CenaModo = CenaModo.ingredientes
    quadro_inicial: str | None = None
    quadro_final: str | None = None
    produto_nome: str | None = None
    produto_com_foto: bool = False
    negative: str | None = None


@dataclass(frozen=True)
class Parte:
    parte: str
    texto: str


@dataclass(frozen=True)
class PromptMontado:
    texto: str
    negative: str
    partes: list[Parte] = field(default_factory=list)
    avatar_version: int | None = None
    cenario_version: int | None = None


def _vazio(texto: str | None) -> bool:
    return texto is None or not texto.strip()


def _frase(texto: str) -> str:
    """Sem espaços nas pontas e com pontuação final."""
    texto = texto.strip()
    return texto if texto[-1] in ".!?\"'" else f"{texto}."


def pronome(avatar: AvatarIn | None) -> str:
    """"She"/"He" pela descrição do avatar; sem avatar ou sem pista, "The person"."""
    descricao = avatar.prompt if avatar is not None else None
    if _vazio(descricao):
        return "The person"
    if _FEMININO.search(descricao):  # type: ignore[arg-type]
        return "She"
    if _MASCULINO.search(descricao):  # type: ignore[arg-type]
        return "He"
    return "The person"


def _acao(e: Entrada) -> str:
    acao = e.acao.strip()
    if e.produto_com_foto and not _vazio(e.produto_nome) and "reference image" not in acao.lower():
        acao = f"{acao.rstrip('.!? ')}, with the {e.produto_nome.strip()} {REFERENCIA}"  # type: ignore[union-attr]
    return _frase(acao)


def _camera(e: Entrada) -> str | None:
    itens = [PLANOS[e.plano] if e.plano is not None else None,
             MOVIMENTOS[e.movimento] if e.movimento is not None else None,
             e.camera.strip().rstrip(".") if not _vazio(e.camera) else None]
    itens = [i for i in itens if i]
    if not itens:
        return None
    texto = ", ".join(itens)
    return _frase(texto[0].upper() + texto[1:])


def montar(e: Entrada) -> PromptMontado:
    partes: list[Parte] = []
    if e.modo == CenaModo.quadros:
        if not _vazio(e.quadro_inicial):
            partes.append(Parte("quadro_inicial", _frase(f"Start frame: {e.quadro_inicial.strip()}")))  # type: ignore[union-attr]
        if not _vazio(e.quadro_final):
            partes.append(Parte("quadro_final", _frase(f"End frame: {e.quadro_final.strip()}")))  # type: ignore[union-attr]
    if e.avatar is not None and not _vazio(e.avatar.prompt):
        partes.append(Parte("avatar", e.avatar.prompt))  # type: ignore[arg-type]  # sem alteração
    if e.avatar is not None and not _vazio(e.avatar.image_rules):
        partes.append(Parte("regras", _frase(e.avatar.image_rules)))  # type: ignore[arg-type]
    partes.append(Parte("acao", _acao(e)))
    if e.cenario is not None and not _vazio(e.cenario.prompt):
        partes.append(Parte("cenario", _frase(e.cenario.prompt)))  # type: ignore[arg-type]
    camera = _camera(e)
    if camera is not None:
        partes.append(Parte("camera", camera))
    estilo = e.estilo if not _vazio(e.estilo) else e.estilo_padrao
    if not _vazio(estilo):
        partes.append(Parte("estilo", _frase(estilo)))  # type: ignore[arg-type]
    if not _vazio(e.fala):
        partes.append(Parte("fala", f'{pronome(e.avatar)} looks at the camera and says: '
                                    f'"{e.fala.strip()}"'))  # type: ignore[union-attr]
    if not _vazio(e.audio):
        partes.append(Parte("audio", _frase(f"Ambient sound: {e.audio.strip()}")))  # type: ignore[union-attr]

    texto = ""
    for p in partes:
        if texto and not texto[-1].isspace():
            texto += " "
        texto += p.texto
    negative = e.negative if not _vazio(e.negative) else e.negative_padrao
    return PromptMontado(
        texto=texto, negative=negative.strip(), partes=partes,
        avatar_version=e.avatar.version if e.avatar is not None else None,
        cenario_version=e.cenario.version if e.cenario is not None else None)
