"""Cadastro padronizado (spec 025, research R5–R8): domínio puro, sem banco nem rede.

- os **slots** do kit do avatar (`rosto_origem` → `rosto_frontal` → par 3/4 → `corpo_base`) e do
  cenário (`cena`), na ordem de exibição;
- os **passos** da 021 que a 025 usa, com o que cada um preenche e o que precisa antes (a ordem do
  `pipeline/avatares.py kit`);
- a **situação** do kit (`incompleto`, `completo`, `atencao`; nota mínima 7, como no pipeline);
- a regex de **menoridade** do pipeline (pt-BR e inglês) e as **instruções fixas** dos passos,
  portadas do texto testado em `pipeline/avatares.py` e `pipeline/cenarios.py`. O `prompt` do
  avatar **nunca** entra nas instruções de edição (FR-016: no Qwen Edit, a descrição faz dar zoom e
  cortar o corpo).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

SLOTS_AVATAR = ("rosto_origem", "rosto_frontal", "rosto_34_esq", "rosto_34_dir", "corpo_base")
SLOTS_CENARIO = ("cena",)
SLOTS = SLOTS_AVATAR + SLOTS_CENARIO
# As notas da checagem de identidade (o `rosto_origem` é a referência, sem nota).
SLOTS_NOTA = ("rosto_frontal", "rosto_34_esq", "rosto_34_dir", "corpo_base")
NOTA_MINIMA = 7

ROTULO_SLOT = {"rosto_origem": "o rosto de origem", "rosto_frontal": "o rosto frontal",
               "rosto_34_esq": "o rosto 3/4 (esquerda)", "rosto_34_dir": "o rosto 3/4 (direita)",
               "corpo_base": "o corpo-base", "cena": "a cena"}

Situacao = Literal["incompleto", "completo", "atencao"]


@dataclass(frozen=True)
class PassoKit:
    id: str
    tipo: Literal["avatar", "cenario"]
    preenche: tuple[str, ...]  # slots que a escolha grava (look, pose e variação: nenhum)
    precisa: tuple[str, ...]  # slots ativos antes de abrir


PASSOS: dict[str, PassoKit] = {p.id: p for p in (
    PassoKit("avatar.rosto_origem", "avatar", ("rosto_origem",), ()),
    PassoKit("avatar.rosto_frontal", "avatar", ("rosto_frontal",), ("rosto_origem",)),
    PassoKit("avatar.rostos_34", "avatar", ("rosto_34_esq", "rosto_34_dir"), ("rosto_frontal",)),
    PassoKit("avatar.corpo_base", "avatar", ("corpo_base",), ("rosto_34_esq", "rosto_34_dir")),
    PassoKit("avatar.identidade", "avatar", (), SLOTS_AVATAR),
    PassoKit("avatar.look", "avatar", (), ("rosto_frontal", "corpo_base")),
    PassoKit("avatar.pose", "avatar", (), ("rosto_frontal", "corpo_base")),
    PassoKit("cenario.cena", "cenario", ("cena",), ()),
    PassoKit("cenario.variacao", "cenario", (), ("cena",)),
)}
# A ordem do kit na tela (os passos que preenchem slot).
PASSOS_KIT_AVATAR = ("avatar.rosto_origem", "avatar.rosto_frontal", "avatar.rostos_34",
                     "avatar.corpo_base", "avatar.identidade")


def passo_do_slot(slot: str) -> str:
    return next(p.id for p in PASSOS.values() if slot in p.preenche)


def passo_aberto(passo: str, slots_ativos: Iterable[str], origem: str | None = None
                 ) -> tuple[bool, str | None]:
    """Se o passo pode ser pedido agora e, se não, o motivo em pt-BR."""
    p = PASSOS[passo]
    ativos = set(slots_ativos)
    if passo == "avatar.rosto_origem" and origem in ("upload", "pessoa_real"):
        return False, "O rosto de origem deste avatar é uma foto enviada; troque pelo envio"
    faltam = [s for s in p.precisa if s not in ativos]
    if not faltam:
        return True, None
    return False, f"Escolha {ROTULO_SLOT[faltam[0]]} antes"


def slot_aberto(slot: str, slots_ativos: Iterable[str]) -> tuple[bool, str | None]:
    """O upload num slot segue a mesma ordem do passo que o preenche."""
    aberto, motivo = passo_aberto(passo_do_slot(slot), slots_ativos)
    return aberto, motivo


def situacao(tipo: str, slots_ativos: Iterable[str], identidade: Mapping[str, Any] | None
             ) -> Situacao:
    """R5: avatar completo = os 5 slots e todas as notas ≥ 7; alguma < 7 = atenção."""
    ativos = set(slots_ativos)
    if tipo == "cenario":
        return "completo" if "cena" in ativos else "incompleto"
    if not set(SLOTS_AVATAR) <= ativos or not identidade:
        return "incompleto"
    notas = identidade.get("notas") or {}
    if any(s not in notas for s in SLOTS_NOTA):
        return "incompleto"
    return "completo" if all(int(notas[s]["nota"]) >= NOTA_MINIMA for s in SLOTS_NOTA) \
        else "atencao"


# ---- menoridade (R8, porte do `PROIBIDO` do pipeline) ----

PROIBIDO = re.compile(
    r"\b(child|children|kid|kids|teen|teenager|minor|baby|toddler|schoolgirl|schoolboy|"
    r"crian[cç]a|adolescente|menin[ao]|beb[eê]|1[0-7] years? old|[1-9] years? old)\b", re.IGNORECASE)


def checar_menoridade(*textos: str | None) -> str | None:
    """O primeiro termo proibido encontrado, ou None."""
    for t in textos:
        if t:
            achou = PROIBIDO.search(t)
            if achou:
                return achou.group(0)
    return None


# ---- instruções fixas (porte de `avatares.py` e `cenarios.py`) ----

ROSTO = ("RAW photo, head and shoulders portrait of {p}, shoulders and upper chest visible, looking "
         "at the camera, natural skin texture with visible pores, soft natural daylight, 85mm lens, "
         "shallow depth of field, plain light neutral background, photorealistic, high detail")
KIT_FRONTAL = ("Turn this into a canonical studio reference portrait of this same person. Zoom out so "
               "the head, both shoulders and the upper chest are fully visible, with some space above "
               "the head. Facing the camera straight on, eyes looking into the lens, neutral relaxed "
               "expression with a light closed-mouth smile, wearing a plain light gray crew-neck "
               "t-shirt, plain seamless light gray studio background, soft even diffused front "
               "lighting without harsh shadows. Keep the exact facial identity, face shape, eyes, "
               "nose, mouth, skin tone, hair color and hairstyle. Photorealistic, natural skin "
               "texture.")
KIT_34 = ("Show this same person in a three-quarter view (not a profile): head and shoulders turned "
          "only about 35 degrees so the face points toward the {lado} side of the image, both eyes "
          "and the far cheek still clearly visible, eyes looking in the same direction as the face. "
          "Same plain light gray t-shirt, same plain light gray studio background, same soft even "
          "lighting, same framing, same neutral expression with a light smile. Keep the exact facial "
          "identity, face shape, skin tone, hair color and hairstyle. Photorealistic, natural skin "
          "texture.")
KIT_34_ESQ = KIT_34.format(lado="left")
KIT_34_DIR = KIT_34.format(lado="right")
KIT_CORPO = ("full-body vertical studio photo, standing in a relaxed neutral pose facing the camera, "
             "arms resting naturally at the sides, hands empty, feet slightly apart, the whole body "
             "visible from the top of the head to the feet with a small margin, wearing a plain "
             "fitted light gray t-shirt, dark gray leggings and plain white sneakers, plain seamless "
             "light gray studio background and floor, soft even studio lighting")
KIT_CORPO_ROSTO = ("Zoom out to a {p} of this same person. Keep the exact facial identity, face "
                   "shape, skin tone, hair color and hairstyle. Photorealistic, natural skin texture.")
KIT_CORPO_TELA = ("Place the person from image 2 into image 1 as a {p}. Keep the exact facial "
                  "identity, face shape, skin tone, hair color and hairstyle of the person in image "
                  "2. Photorealistic, natural skin texture.")
LOOK = ("Same person, same pose, same framing and same background, now wearing {d}. Do not zoom or "
        "crop: keep the camera distance of image 1 so the same body parts stay visible. Keep the face "
        "exactly like the person in image 2 and keep everything else unchanged. Photorealistic.")
POSE = ("Show this same person in a new vertical photo: {p}. The whole body is visible from head to "
        "feet. Keep the exact facial identity, hair and skin tone of the person in image 2. "
        "Photorealistic, natural light, natural skin texture.")
VARIACAO = ("{d}. Keep the same room, layout, furniture, materials and colors unless the "
            "instruction says otherwise. Photorealistic, no people, no text.")
W_CORPO, H_CORPO = 768, 1344
CINZA = (214, 214, 214)


def instrucao_corpo(estrategia: Literal["rosto", "tela"]) -> str:
    """As duas estratégias do corpo-base (opção ímpar: zoom out do frontal; par: tela cinza com o
    frontal como referência)."""
    return (KIT_CORPO_ROSTO if estrategia == "rosto" else KIT_CORPO_TELA).format(p=KIT_CORPO)
