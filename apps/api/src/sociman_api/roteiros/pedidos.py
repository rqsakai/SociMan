"""Os pedidos de geração que o roteiro faz (research R1, R4, R5, R7, R9 e R11).

Todos saem por `geracao.service.criar_para_alvo(..., perfil_base=<perfil do roteiro>)` (029:
o perfil do roteiro é o perfil base de todas as gerações dele) e levam `extras.roteiroId`. O
autor do pedido é quem deu o comando: o humano da ação, ou `roteiros.comandado_por` quando a
máquina pede sozinha (R9). O `params` guarda tudo o que o motor precisa, já resolvido (o gerador
não volta ao roteiro); a assinatura (`extras.assinatura`) diz se a prévia e o acabamento ainda são
os de agora.

Spec 031 (vídeo guiado): `quadro` pede o keyframe de um quadro da sequência (R3: o 0 nasce do
cenário do roteiro, com o corpo-base e o produto; os seguintes nascem do anterior, com o produto
e o rosto como âncoras), e `trecho` pede o clipe de um trecho com o par de quadros vizinhos
(`start_image`/`end_image`, R2), no trecho-base do roteiro.
"""

import dataclasses
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.cenas import prompt_local
from sociman_api.cenas import quadros as cenas_quadros
from sociman_api.cenas.models import Cena, CenaQuadro, CenaTomada
from sociman_api.geracao import passos
from sociman_api.geracao import service as geracao_service
from sociman_api.geracao.models import Audio, Geracao, GeracaoAlvo, GeracaoMotor
from sociman_api.produtos.models import Produto
from sociman_api.roteiros import estado, tempos
from sociman_api.roteiros.models import Roteiro, RoteiroAcabamento, RoteiroCena
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
           alvo_id: uuid.UUID, item_perfil: uuid.UUID | None, params: dict[str, Any],
           n: int | None = None, motor: GeracaoMotor | None = None) -> Geracao:
    params = {"instrucao": "", "referencias": [], "rotulo": None, "texto": None, **params}
    params["extras"] = {"roteiroId": str(r.id), **(params.get("extras") or {})}
    return geracao_service.criar_para_alvo(db, ator, item_perfil, passo, alvo_tipo, alvo_id,
                                           params, perfil_base=r.perfil_id, n=n, motor=motor)


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
    partes.append(REGRAS_QUADRO)
    return " ".join(partes)


def keyframe(db: Session, ator: Actor, r: Roteiro, cena: Cena, ordem: int,
             instrucao: str | None = None, referencias: list[uuid.UUID] | None = None,
             n: int | None = None) -> Geracao:
    refs = list(referencias if referencias is not None else (cena.keyframe_refs or [])) \
        or refs_padrao(db, r, cena)
    texto = instrucao or instrucao_keyframe(db, r, cena)
    return _criar(db, ator, r, "cena.keyframe", GeracaoAlvo.cena, cena.id, cena.perfil_id,
                  {"bloco": "keyframe", "instrucao": texto, "prompt": texto,
                   "referencias": [str(i) for i in refs[:REFS_KEYFRAME_MAX]],
                   "largura": cena.largura, "altura": cena.altura,
                   "extras": {"ordem": ordem, "refsIgnoradas": max(0, len(refs) -
                                                                   REFS_KEYFRAME_MAX)}}, n=n)


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


def _trechos_params(db: Session, p: RoteiroCena) -> list[dict[str, Any]]:
    """Spec 031: a tomada de cada trecho da posição do guiado, na ordem (a montagem cola)."""
    out = []
    for x in p.trechos_ordenados():
        t = db.get(CenaTomada, x.tomada_id) if x.tomada_id else None
        out.append({"trecho": x.trecho, "tomadaId": str(x.tomada_id),
                    "videoKey": t.video_key if t else None,
                    "duracaoMs": t.duracao_ms if t else None,
                    "motor": t.motor.value if t and t.motor else None})
    return out


def _posicoes_params(db: Session, r: Roteiro) -> list[dict[str, Any]]:
    out = []
    for p in estado.posicoes(r):
        t = db.get(CenaTomada, p.tomada_id) if p.tomada_id else None
        cena = db.get(Cena, p.cena_id)
        item = {"ordem": p.ordem, "cenaId": str(p.cena_id), "tomadaId": str(p.tomada_id),
                "videoKey": t.video_key if t else None,
                "duracaoMs": t.duracao_ms if t else None,
                "duracaoS": float(p.duracao_s or 0), "motor": t.motor.value if t and t.motor
                else None, "keyframeImageId": str(t.keyframe_image_id)
                if t and t.keyframe_image_id else None,
                "largura": cena.largura, "altura": cena.altura}
        if p.trechos is not None:  # 031: os trechos (as chaves da 011 ficam como estão)
            item["trechos"] = _trechos_params(db, p)
            item["trechoBaseS"] = r.trecho_base_s
        out.append(item)
    return out


def _video_params(db: Session, r: Roteiro, assinatura: str) -> dict[str, Any]:
    n = estado.narracao_ativa(db, r)
    audio = db.get(Audio, n.audio_id) if n is not None and n.audio_id else None
    pos = _posicoes_params(db, r)
    largura, altura = (pos[0]["largura"], pos[0]["altura"]) if pos else (736, 1280)
    extras = {"assinatura": assinatura, "posicoes": pos, "narracaoId": str(r.narracao_id),
              "audioKey": audio.object_key if audio else None,
              "largura": largura, "altura": altura}
    if r.guiado:  # 031 (R4): a fala já cortada por slot (o executor não volta ao banco)
        fala = estado.fala_guiada(db, r)
        extras["trechoBaseS"] = r.trecho_base_s
        extras["fala"] = [dataclasses.asdict(b) for b in fala[0]] if fala is not None else None
    return {"extras": extras}


# ---- spec 031: o quadro e o trecho do vídeo guiado ----

# As regras do quadro (T059, 2026-10-15): o "system prompt" fixo de toda imagem de quadro, com o que
# os testes já nos custaram. Quando virar regra editável (estudo da 030, §4.4), o padrão é este.
REGRAS_QUADRO = (
    "Vertical photo, realistic, the product exactly as in the reference image: same color, "
    "fabric, sheerness and details; under a sheer garment there is skin or the same base layer "
    "as in the reference, never another garment. No extra garment under or over the product "
    "(no undershirt, t-shirt, tank top or jacket). The whole product stays in frame, never "
    "cropped at the neckline. Same room, walls, floor, furniture and lighting; same face, hair, "
    "skin tone and body; no other person, no text, no watermark, no phone frame."
)
SUFIXO_QUADRO = REGRAS_QUADRO


def _avatar(db: Session, r: Roteiro, cena: Cena) -> Asset | None:
    avatar_id = cena.avatar_id or r.avatar_id
    return db.get(Asset, avatar_id) if avatar_id else None


def _slot(asset: Asset | None, slot: str) -> uuid.UUID | None:
    f = asset.slot_ativo(slot) if asset is not None else None
    return f.image_id if f is not None else None


def imagem_do_produto(db: Session, r: Roteiro, cena: Cena) -> uuid.UUID | None:
    """O flat (ou o recorte) da variante da cena; sem variante na cena, a do roteiro."""
    produto_id, variante_id = cena.produto_id, cena.produto_variante_id
    if produto_id is None and r.produtos_rel:
        rp = min(r.produtos_rel, key=lambda p: p.ordem)
        produto_id, variante_id = rp.produto_id, rp.produto_variante_id
    produto = db.get(Produto, produto_id) if produto_id else None
    if produto is None:
        return None
    variante = produto.variante(variante_id) if variante_id \
        else next(iter(produto.ativas()), None)
    if variante is None:
        return None
    return variante.flat_image_id or variante.recorte_image_id


def refs_do_quadro(db: Session, r: Roteiro, cena: Cena, q: CenaQuadro,
                   anterior: CenaQuadro | None) -> list[uuid.UUID | None]:
    """R3: `[base_image, ref1, ref2]`. Quadro 0: a imagem `cena` do cenário do roteiro, o
    corpo-base do avatar e o produto. Quadros 1+: o quadro anterior, o produto e o rosto frontal
    (as âncoras seguram o produto e o rosto e reduzem a deriva de edição sobre edição)."""
    avatar = _avatar(db, r, cena)
    produto = imagem_do_produto(db, r, cena)
    if q.ordem == 0:
        cenario = db.get(Asset, r.cenario_id or cena.cenario_id) \
            if (r.cenario_id or cena.cenario_id) else None
        return [_slot(cenario, "cena"), _slot(avatar, "corpo_base"), produto]
    return [anterior.image_id if anterior is not None else None, produto,
            _slot(avatar, "rosto_frontal")]


def composicao_do_quadro(ordem: int, refs: list[uuid.UUID | None]) -> str:
    """Diretiva fixa (como no pipeline de referência) que diz ao Qwen Edit o papel de cada imagem,
    numeradas pela posição real (as referências ausentes não entram na lista). Sem ela, o quadro 0
    saía com o fundo do corpo-base em vez do cenário (T059, 2026-10-14)."""
    num: list[int | None] = []
    n = 1
    for i in refs[1:]:
        n += i is not None
        num.append(n if i is not None else None)
    if ordem == 0:
        corpo, produto = num
        partes = [f"Place the person from image {corpo} into the scene of image 1"
                  if corpo else "Use the scene of image 1"]
        if produto:
            partes[0] += f", wearing the garment from image {produto} exactly as shown"
        partes.append("Keep the room, walls, furniture, floor and lighting of image 1 unchanged")
        if corpo:
            partes.append(f"Keep the exact facial identity, hair, skin tone and body shape of the "
                          f"person in image {corpo}")
    else:
        produto, rosto = num
        partes = [("Edit image 1: keep the same person, room, background, lighting and camera "
                   "framing of image 1")]
        if produto:
            partes.append(f"The garment stays exactly as in image {produto} (same color, fabric "
                          "and details)")
        if rosto:
            partes.append(f"Keep the face exactly like the person in image {rosto}")
    return ". ".join(partes) + ". New state:"


def instrucao_do_quadro(q: CenaQuadro, refs: list[uuid.UUID | None] | None = None) -> str:
    texto = (q.instrucao or "").strip()
    if SUFIXO_QUADRO not in texto:
        texto = f"{texto.rstrip('.')}. {SUFIXO_QUADRO}" if texto else SUFIXO_QUADRO
    if refs is not None:
        texto = f"{composicao_do_quadro(q.ordem, refs)} {texto}"
    return texto


class QuadroSemBase(ValueError):
    """O quadro não tem de onde nascer (o anterior sem imagem, ou o cenário sem a imagem `cena`)."""


def quadro(db: Session, ator: Actor, r: Roteiro, posicao: RoteiroCena, ordem: int,
           n: int = 1) -> Geracao:
    """O keyframe do quadro `ordem` da cena da posição (`extras.quadro`), com `n` opções (1 no
    wizard). A geração fica ligada ao quadro (`cena_quadros.geracao_id`)."""
    cena = db.get(Cena, posicao.cena_id)
    qs = cenas_quadros.ativos(db, cena.id)
    q = next((x for x in qs if x.ordem == ordem), None)
    if q is None:
        raise QuadroSemBase(f"a cena não tem o quadro {ordem}")
    anterior = next((x for x in qs if x.ordem == ordem - 1), None) if ordem else None
    refs = refs_do_quadro(db, r, cena, q, anterior)
    if refs[0] is None:
        raise QuadroSemBase("o quadro anterior ainda não tem imagem" if ordem
                            else "o cenário não tem a imagem da cena")
    texto = instrucao_do_quadro(q, refs)
    g = _criar(db, ator, r, "cena.keyframe", GeracaoAlvo.cena, cena.id, cena.perfil_id,
               {"bloco": "keyframe", "instrucao": texto, "prompt": texto,
                "referencias": [str(i) for i in refs if i is not None],
                "largura": cena.largura, "altura": cena.altura,
                "extras": {"ordem": posicao.ordem, "quadro": ordem,
                           "baseImageId": str(refs[0]),
                           "refsIgnoradas": sum(1 for i in refs if i is None)}}, n=n)
    cenas_quadros.ligar_geracao(db, q, g.id)
    return g


def trecho(db: Session, ator: Actor, r: Roteiro, posicao: RoteiroCena, t: int,
           motor: str | None = None) -> Geracao:
    """O clipe do trecho `t` (R2): `start_image` = quadro[t], `end_image` = quadro[t+1], no
    trecho-base do roteiro (os quadros pela regra do motor, `tempos.quadros`)."""
    cena = db.get(Cena, posicao.cena_id)
    inicio, fim = estado.par_do_trecho(cenas_quadros.ativos(db, cena.id), t)
    if inicio is None or fim is None:
        raise QuadroSemBase(f"o trecho {t} ainda não tem os dois quadros")
    motor = motor or cena.motor.value
    base_s = float(r.trecho_base_s)
    prompt = prompt_local.montar_clipe(cena, descricao_avatar(db, r, cena))
    return _criar(db, ator, r, "cena.clipe", GeracaoAlvo.cena, cena.id, cena.perfil_id,
                  {"bloco": passos.BLOCOS_CLIPE[motor], "prompt": prompt.texto,
                   "largura": cena.largura, "altura": cena.altura,
                   "referencias": [str(inicio), str(fim)],
                   "extras": {"ordem": posicao.ordem, "trecho": t, "motor": motor,
                              "quadros": tempos.quadros(motor, base_s),
                              "fps": tempos.FPS[motor], "duracaoS": round(base_s, 3),
                              "keyframeId": str(inicio), "keyframeFimId": str(fim)}})


def montagem(db: Session, ator: Actor, r: Roteiro, assinatura: str) -> Geracao:
    return _criar(db, ator, r, "roteiro.montagem", GeracaoAlvo.roteiro, r.id, r.perfil_id,
                  _video_params(db, r, assinatura))


def acabamento(db: Session, ator: Actor, r: Roteiro, assinatura: str) -> Geracao:
    """T059 (2026-10-15): `leve` roda na linha ffmpeg (lanczos, sem GPU); `hd` é o `upscale_video`
    (SeedVR2) na linha da GPU. O modo vai em `extras.acabamento` (a entrega confere)."""
    params = _video_params(db, r, assinatura)
    hd = r.acabamento_modo == RoteiroAcabamento.hd
    if hd:
        params["bloco"] = "upscale_video"
    params["extras"]["montagemGeracaoId"] = str(r.montagem_geracao_id)
    params["extras"]["acabamento"] = r.acabamento_modo.value
    return _criar(db, ator, r, "roteiro.acabamento", GeracaoAlvo.roteiro, r.id, r.perfil_id,
                  params, motor=None if hd else GeracaoMotor.ffmpeg)
