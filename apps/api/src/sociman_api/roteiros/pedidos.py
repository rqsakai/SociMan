"""Os pedidos de geração que o roteiro faz (research R1, R4, R5, R7, R9 e R11).

Todos saem por `geracao.service.criar_para_alvo(..., perfil_base=<perfil do roteiro>)` (029:
o perfil do roteiro é o perfil base de todas as gerações dele) e levam `extras.roteiroId`. O
autor do pedido é quem deu o comando: o humano da ação, ou `roteiros.comandado_por` quando a
máquina pede sozinha (R9). O `params` guarda tudo o que o motor precisa, já resolvido (o gerador
não volta ao roteiro); a assinatura (`extras.assinatura`) diz se a prévia e o acabamento ainda são
os de agora.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.cenas import prompt_local
from sociman_api.cenas.models import Cena, CenaTomada
from sociman_api.geracao import passos
from sociman_api.geracao import service as geracao_service
from sociman_api.geracao.models import Audio, Geracao, GeracaoAlvo
from sociman_api.produtos.models import Produto
from sociman_api.roteiros import estado, tempos
from sociman_api.roteiros.models import Roteiro
from sociman_api.vozes.models import Voz
from sociman_api.vozes.tts_id import tts_id

MAX_TENTATIVAS_TTS = 5
SIMILARIDADE_MIN = 0.95
IDIOMA = "Portuguese"
REFS_KEYFRAME_MAX = 3  # base_image, ref1 e ref2 (comfyui-blocos.md)
SLOTS_REF = ("corpo_base", "rosto_frontal")


def ator_da_maquina(r: Roteiro) -> Actor:
    """O autor dos pedidos que a máquina faz sozinha: o último humano que comandou (R9)."""
    return Actor(kind="user", user_id=r.comandado_por)


def _criar(db: Session, ator: Actor, r: Roteiro, passo: str, alvo_tipo: GeracaoAlvo,
           alvo_id: uuid.UUID, item_perfil: uuid.UUID | None, params: dict[str, Any]
           ) -> Geracao:
    params = {"instrucao": "", "referencias": [], "rotulo": None, "texto": None, **params}
    params["extras"] = {"roteiroId": str(r.id), **(params.get("extras") or {})}
    return geracao_service.criar_para_alvo(db, ator, item_perfil, passo, alvo_tipo, alvo_id,
                                           params, perfil_base=r.perfil_id)


def plano(db: Session, ator: Actor, r: Roteiro) -> Geracao:
    """A mensagem é montada na hora da chamada (`RoteiroPlano.mensagem_claude`)."""
    return _criar(db, ator, r, "roteiro.plano", GeracaoAlvo.roteiro, r.id, r.perfil_id,
                  {"instrucao": r.brief})


def narracao(db: Session, ator: Actor, r: Roteiro, voz: Voz, texto_hash: str) -> Geracao:
    corpo = {"sentences": list(r.frases), "voice": tts_id(voz.id),
             "max_attempts": MAX_TENTATIVAS_TTS, "min_similarity": SIMILARIDADE_MIN,
             "language": IDIOMA, "pronuncias": estado.pronuncias_do_perfil(db, r.perfil_id)}
    return _criar(db, ator, r, "roteiro.narracao", GeracaoAlvo.roteiro, r.id, r.perfil_id,
                  {"corpo": corpo, "velocidade": float(r.velocidade), "vozId": str(voz.id),
                   "refAudioId": str(voz.ref_audio_id) if voz.ref_audio_id else None,
                   "textoHash": texto_hash})


def refs_padrao(db: Session, r: Roteiro, cena: Cena) -> list[uuid.UUID]:
    """As referências do keyframe sem as da cena: o kit do avatar (corpo-base ou rosto) e o
    recorte (ou flat) da variante do produto da cena."""
    refs: list[uuid.UUID] = []
    avatar = db.get(Asset, cena.avatar_id or r.avatar_id) if (cena.avatar_id or r.avatar_id) \
        else None
    if avatar is not None:
        for slot in SLOTS_REF:
            f = avatar.slot_ativo(slot)
            if f is not None:
                refs.append(f.image_id)
                break
    produto = db.get(Produto, cena.produto_id) if cena.produto_id else None
    if produto is not None:
        variante = produto.variante(cena.produto_variante_id) if cena.produto_variante_id \
            else next(iter(produto.ativas()), None)
        if variante is not None:
            img = variante.flat_image_id or variante.recorte_image_id
            if img is not None:
                refs.append(img)
    return refs


def descricao_avatar(db: Session, r: Roteiro, cena: Cena) -> str | None:
    avatar_id = cena.avatar_id or r.avatar_id
    avatar = db.get(Asset, avatar_id) if avatar_id else None
    return (avatar.prompt or None) if avatar is not None else None


def instrucao_keyframe(db: Session, r: Roteiro, cena: Cena) -> str:
    if (cena.keyframe_instrucao or "").strip():
        return cena.keyframe_instrucao.strip()
    partes = [cena.acao.strip().rstrip(".") + "."]
    descricao = descricao_avatar(db, r, cena)
    if descricao:
        partes.append(descricao.strip())
    partes.append("Vertical photo, realistic, the product exactly as in the reference image.")
    return " ".join(partes)


def keyframe(db: Session, ator: Actor, r: Roteiro, cena: Cena, ordem: int,
             instrucao: str | None = None, referencias: list[uuid.UUID] | None = None
             ) -> Geracao:
    refs = list(referencias if referencias is not None else (cena.keyframe_refs or [])) \
        or refs_padrao(db, r, cena)
    texto = instrucao or instrucao_keyframe(db, r, cena)
    return _criar(db, ator, r, "cena.keyframe", GeracaoAlvo.cena, cena.id, cena.perfil_id,
                  {"bloco": "keyframe", "instrucao": texto, "prompt": texto,
                   "referencias": [str(i) for i in refs[:REFS_KEYFRAME_MAX]],
                   "largura": cena.largura, "altura": cena.altura,
                   "extras": {"ordem": ordem, "refsIgnoradas": max(0, len(refs) -
                                                                   REFS_KEYFRAME_MAX)}})


def duracao_max(cena: Cena) -> float:
    return float(cena.duracao_max_s) if cena.duracao_max_s is not None \
        else tempos.DURACAO_MAX_S[cena.motor.value]


def clipe(db: Session, ator: Actor, r: Roteiro, cena: Cena, ordem: int,
          duracao_s: Decimal | float, motor: str | None = None) -> Geracao:
    motor = motor or cena.motor.value
    quadros = tempos.quadros(motor, float(duracao_s))
    prompt = prompt_local.montar_clipe(cena, descricao_avatar(db, r, cena))
    refs = [cena.keyframe_inicial_id] + ([cena.keyframe_final_id] if cena.keyframe_final_id
                                         else [])
    return _criar(db, ator, r, "cena.clipe", GeracaoAlvo.cena, cena.id, cena.perfil_id,
                  {"bloco": passos.BLOCOS_CLIPE[motor], "prompt": prompt.texto,
                   "largura": cena.largura, "altura": cena.altura,
                   "referencias": [str(i) for i in refs],
                   "extras": {"ordem": ordem, "motor": motor, "quadros": quadros,
                              "fps": tempos.FPS[motor],
                              "duracaoS": round(float(duracao_s), 3),
                              "keyframeId": str(cena.keyframe_inicial_id)}})


def _posicoes_params(db: Session, r: Roteiro) -> list[dict[str, Any]]:
    out = []
    for p in estado.posicoes(r):
        t = db.get(CenaTomada, p.tomada_id) if p.tomada_id else None
        cena = db.get(Cena, p.cena_id)
        out.append({"ordem": p.ordem, "cenaId": str(p.cena_id), "tomadaId": str(p.tomada_id),
                    "videoKey": t.video_key if t else None,
                    "duracaoMs": t.duracao_ms if t else None,
                    "duracaoS": float(p.duracao_s or 0), "motor": t.motor.value if t and t.motor
                    else None, "keyframeImageId": str(t.keyframe_image_id)
                    if t and t.keyframe_image_id else None,
                    "largura": cena.largura, "altura": cena.altura})
    return out


def _video_params(db: Session, r: Roteiro, assinatura: str) -> dict[str, Any]:
    n = estado.narracao_ativa(db, r)
    audio = db.get(Audio, n.audio_id) if n is not None and n.audio_id else None
    pos = _posicoes_params(db, r)
    largura, altura = (pos[0]["largura"], pos[0]["altura"]) if pos else (736, 1280)
    return {"extras": {"assinatura": assinatura, "posicoes": pos,
                       "narracaoId": str(r.narracao_id),
                       "audioKey": audio.object_key if audio else None,
                       "largura": largura, "altura": altura}}


def montagem(db: Session, ator: Actor, r: Roteiro, assinatura: str) -> Geracao:
    return _criar(db, ator, r, "roteiro.montagem", GeracaoAlvo.roteiro, r.id, r.perfil_id,
                  _video_params(db, r, assinatura))


def acabamento(db: Session, ator: Actor, r: Roteiro, assinatura: str) -> Geracao:
    params = _video_params(db, r, assinatura)
    params["bloco"] = "upscale_video"
    params["extras"]["montagemGeracaoId"] = str(r.montagem_geracao_id)
    return _criar(db, ator, r, "roteiro.acabamento", GeracaoAlvo.roteiro, r.id, r.perfil_id,
                  params)
