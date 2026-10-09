"""Registro dos passos de geração (research R15, FR-002 e FR-003), em código como `ia/tipos.py`.

Cada passo diz o motor, o tipo de alvo, o tipo de resultado, o número padrão e máximo de opções
(o pedido pode reduzir, nunca aumentar), se vai direto ao alvo sem escolha humana
(`sem_escolha`: só os passos de texto e o `produto.recorte`, FR-010 e FR-031; o `voz.teste` é
entregue sem mudar o alvo), o bloco do ComfyUI e o `kind` da imagem gerada. O CHECK
`ck_geracoes_passo` da migration 0020 repete a lista (o teste cruzado confere).

Os sufixos `REALISMO` e `MANTER` vêm do `cenarios.py` do pipeline (R6): a cena sai sem pessoas,
sem texto e com área livre embaixo para os produtos.

`sobrescrever` troca o registro **só em teste** (a 021 testa os motores `claude` e `tts` com passos
injetados; os reais chegam com a 012 e a 025).
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Literal

from sociman_api.geracao.models import GeracaoAlvo, GeracaoMotor

Resultado = Literal["imagem", "par_imagem", "audio", "texto"]
Bloco = Literal["cena", "keyframe", "retrato", "cutout"]

REALISMO = ("vertical candid photograph, natural light, photorealistic, realistic textures, "
            "an empty clean surface in the lower part of the frame with free space to place "
            "products, no people, no text, no watermark")
MANTER = ("Keep the same room, layout, furniture, materials and colors unless the instruction "
          "says otherwise. Photorealistic, no people, no text.")


@dataclass(frozen=True)
class Passo:
    id: str
    motor: GeracaoMotor
    alvo_tipo: GeracaoAlvo
    resultado: Resultado
    n_padrao: int
    n_max: int
    sem_escolha: bool = False
    aplica_alvo: bool = True
    bloco: Bloco | None = None
    image_kind: str | None = None  # `images.kind` dos candidatos; o de produto chega com a 012


_C, _T, _CL = GeracaoMotor.comfyui, GeracaoMotor.tts, GeracaoMotor.claude
_A, _V, _P = GeracaoAlvo.asset, GeracaoAlvo.voz, GeracaoAlvo.produto

_PASSOS: tuple[Passo, ...] = (
    Passo("avatar.rosto_origem", _C, _A, "imagem", 4, 4, bloco="retrato", image_kind="avatar"),
    Passo("avatar.rosto_frontal", _C, _A, "imagem", 2, 2, bloco="keyframe", image_kind="avatar"),
    Passo("avatar.rostos_34", _C, _A, "par_imagem", 2, 2, bloco="keyframe",
          image_kind="avatar"),
    Passo("avatar.corpo_base", _C, _A, "imagem", 2, 2, bloco="keyframe", image_kind="avatar"),
    Passo("avatar.look", _C, _A, "imagem", 2, 2, bloco="keyframe", image_kind="avatar"),
    Passo("avatar.pose", _C, _A, "imagem", 2, 2, bloco="keyframe", image_kind="avatar"),
    Passo("avatar.identidade", _CL, _A, "texto", 1, 1, sem_escolha=True),
    Passo("voz.gravacao", _T, _V, "audio", 3, 3),
    Passo("voz.design", _T, _V, "audio", 3, 3),
    Passo("voz.teste", _T, _V, "audio", 1, 1, sem_escolha=True, aplica_alvo=False),
    Passo("produto.ficha", _CL, _P, "texto", 1, 1, sem_escolha=True),
    Passo("produto.recorte", _C, _P, "imagem", 1, 1, sem_escolha=True, bloco="cutout"),
    Passo("produto.flat", _C, _P, "imagem", 2, 2, bloco="keyframe"),
    Passo("cenario.cena", _C, _A, "imagem", 2, 2, bloco="cena", image_kind="fundo"),
    Passo("cenario.variacao", _C, _A, "imagem", 2, 2, bloco="keyframe", image_kind="fundo"),
)

PASSOS: dict[str, Passo] = {p.id: p for p in _PASSOS}
IDS: tuple[str, ...] = tuple(PASSOS)


def get(passo_id: str) -> Passo | None:
    return PASSOS.get(passo_id)


@contextmanager
def sobrescrever(passo_id: str, **campos) -> Iterator[Passo]:
    """Troca (ou acrescenta, com `id` novo) um passo do registro enquanto durar o bloco. Só em
    teste: fora do pytest levanta, para nenhum código de produção mudar a regra "nunca auto"."""
    if "PYTEST_CURRENT_TEST" not in os.environ:
        raise RuntimeError("passos.sobrescrever só vale nos testes")
    antigo = PASSOS.get(passo_id)
    novo = replace(antigo, **campos) if antigo else Passo(id=passo_id, **campos)
    PASSOS[passo_id] = novo
    try:
        yield novo
    finally:
        if antigo is None:
            PASSOS.pop(passo_id, None)
        else:
            PASSOS[passo_id] = antigo
