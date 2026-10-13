"""Aplicadores dos 6 passos do roteiro (research R1, R3, R5, R9, R11 e R13), registrados em
`geracao.aplicadores.APLICADORES` ao importar este módulo (o `main.py` e o gerador importam).

- `roteiro.plano` (Claude, sem escolha): as frases, as posições e as cenas novas (010, em
  `rascunho`, autor = quem pediu, `details.ia`); corta no `ROTEIRO_MAX_CENAS`, com aviso;
- `roteiro.narracao` (shop-tts, sem escolha): a `roteiro_narracoes` nova (o take já na
  velocidade final, R5) vira a ativa; a anterior ganha `desuso_em`;
- `cena.keyframe` (ComfyUI, 2 opções, **com escolha**): a opção escolhida (por um humano, ou a 1
  pelo `system:roteiro` em `roteiros/automatico.py`) vira o keyframe inicial da cena;
- `cena.clipe` (ComfyUI, sem escolha): o vídeo vira tomada `geracao_local` da cena, apontando o
  objeto do candidato (R3);
- `roteiro.montagem` (ffmpeg, sem escolha): a prévia; o trabalho é o `executar_video`;
- `roteiro.acabamento` (ComfyUI, sem escolha): o HD (SeedVR2 por posição + ffmpeg) e a entrega.

O gancho de todos é o `maquina.gancho` (sem rede). A seta é `roteiros → geracao`.
"""

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from PIL import ImageOps
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.cenas import schemas as cenas_schemas
from sociman_api.cenas import service as cenas_service
from sociman_api.cenas import tomadas as cenas_tomadas
from sociman_api.cenas.models import Cena, CenaMotor, CenaPlano, TomadaOrigem
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.geracao import aplicadores as base
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.models import Geracao, GeracaoCandidato, GeracaoStatus
from sociman_api.perfis.models import Image
from sociman_api.produtos.models import Produto
from sociman_api.roteiros import entrega, estado, maquina, montagem, plano
from sociman_api.roteiros.models import (
    ENTITY,
    Roteiro,
    RoteiroCena,
    RoteiroNarracao,
    RoteiroStatus,
)
from sociman_api.vozes.models import Voz

CENAS_PARA_REUSO = 40


def _agora() -> datetime:
    return datetime.now(UTC)


class _Base(base.Aplicador):
    def montar_params(self, db: Session, actor: Actor, alvo: Any, pedido: base.Pedido
                      ) -> dict[str, Any]:
        raise base.alvo_incompativel()  # os pedidos saem do roteiro (`roteiros/pedidos.py`)

    def conferir_referencias(self, db: Session, geracao: Geracao) -> None:
        for ref in geracao.params.get("referencias") or []:
            if db.get(Image, uuid.UUID(ref)) is None:
                raise MotorErro("entrada_invalida",
                                f"A referência {ref[:8]} foi removida; troque as referências")

    def ao_mudar_estado(self, db: Session, geracao: Geracao, de: GeracaoStatus | None,
                        para: GeracaoStatus) -> None:
        maquina.gancho(db, geracao, de, para)


class _DoRoteiro(_Base):
    def validar_alvo(self, db: Session, perfil_id: uuid.UUID | None, alvo_id: uuid.UUID, *,
                     lock: bool = False) -> Roteiro:
        r = db.get(Roteiro, alvo_id, with_for_update=lock)
        if r is None:
            raise base.alvo_nao_encontrado()
        if r.archived:
            raise base.alvo_arquivado()
        return r


class _DaCena(_Base):
    def validar_alvo(self, db: Session, perfil_id: uuid.UUID | None, alvo_id: uuid.UUID, *,
                     lock: bool = False) -> Cena:
        cena = db.get(Cena, alvo_id, with_for_update=lock)
        if cena is None:
            raise base.alvo_nao_encontrado()
        if cena.archived:
            raise base.alvo_arquivado()
        return cena

    def conferir_referencias(self, db: Session, geracao: Geracao) -> None:
        """No claim, também o consentimento do avatar (R16): revogado depois do pedido, a
        geração falha com "consentimento revogado" (o que já existe fica)."""
        super().conferir_referencias(db, geracao)
        cena = db.get(Cena, geracao.alvo_id)
        rid = estado.do_roteiro(geracao)
        r = db.get(Roteiro, rid) if rid else None
        avatar_id = (cena.avatar_id if cena is not None else None) or (r.avatar_id if r else None)
        problema = estado.problema_do_avatar(db.get(Asset, avatar_id) if avatar_id else None)
        if problema:
            raise MotorErro("entrada_invalida", problema[1])


# ---- roteiro.plano ----

def produtos_do(db: Session, r: Roteiro) -> list[tuple[Produto, uuid.UUID | None]]:
    out = []
    for rp in sorted(r.produtos_rel, key=lambda p: p.ordem):
        produto = db.get(Produto, rp.produto_id)
        if produto is not None:
            out.append((produto, rp.produto_variante_id))
    return out


def cenas_para_reuso(db: Session, r: Roteiro) -> list[Cena]:
    """FR-013 (Clarification 2026-10-09): as cenas com aquele avatar e aqueles produtos cujo
    perfil base é o do roteiro ou que não têm perfil base (os modelos públicos)."""
    produtos = [p.id for p, _ in produtos_do(db, r)]
    stmt = select(Cena).where(Cena.archived_at.is_(None),
                              or_(Cena.perfil_id == r.perfil_id, Cena.perfil_id.is_(None)),
                              Cena.produto_id.in_(produtos))
    stmt = stmt.where(Cena.avatar_id == r.avatar_id) if r.avatar_id \
        else stmt.where(Cena.avatar_id.is_(None))
    return list(db.scalars(stmt.order_by(Cena.updated_at.desc(), Cena.id)
                           .limit(CENAS_PARA_REUSO)))


class RoteiroPlano(_DoRoteiro):
    def mensagem_claude(self, db: Session, geracao: Geracao) -> str:
        r = db.get(Roteiro, geracao.alvo_id)
        produtos = produtos_do(db, r)
        indice = {p.id: n for n, (p, _) in enumerate(produtos, start=1)}
        itens = []
        for p, variante_id in produtos:
            v = p.variante(variante_id) if variante_id else next(iter(p.ativas()), None)
            itens.append(plano.ProdutoParaPlano(
                nome=p.nome_comercial or p.name, descricao_prompt=p.descricao_prompt,
                descricao_venda=p.descricao_venda, material_pt=p.material_pt,
                cor_pt=v.cor_pt if v else None))
        avatar = db.get(Asset, r.avatar_id) if r.avatar_id else None
        cenas = [plano.CenaParaReuso(id=str(c.id), nome=c.nome, acao=c.acao,
                                     plano=c.plano.value if c.plano else None,
                                     produto=indice.get(c.produto_id),
                                     tem_keyframe=c.keyframe_inicial_id is not None)
                 for c in cenas_para_reuso(db, r)]
        return plano.montar_mensagem(r.brief, itens, avatar.prompt if avatar else None, cenas,
                                     get_settings().roteiro_max_cenas)

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        r = db.get(Roteiro, geracao.alvo_id, with_for_update=True)
        if r is None or r.archived or r.status != RoteiroStatus.planejando:
            return  # o roteiro mudou no meio: o plano fica só no registro
        dados = (candidato.metricas or {}).get("plano")
        if not isinstance(dados, dict):
            raise MotorErro("internal", detalhe="candidato do plano sem o plano")
        frases = list(dados["frases"])
        posicoes = [dict(p) for p in dados["posicoes"]]
        maximo = get_settings().roteiro_max_cenas
        avisos = []
        if len(posicoes) > maximo:  # R14: corta e junta as frases que sobram na última
            avisos.append({"code": "limite_cenas",
                           "message": f"A IA propôs {len(posicoes)} cenas; o limite é {maximo}"})
            sobra = [f for p in posicoes[maximo:] for f in p["frases"]]
            posicoes = posicoes[:maximo]
            posicoes[-1]["frases"] = [*posicoes[-1]["frases"], *sobra]
        produtos = produtos_do(db, r)
        ia = {"chamadaId": (candidato.metricas or {}).get("chamada_id"),
              "passo": "roteiro.plano", "promptVersion": plano.PROMPT_VERSION}
        cenas_ids = []
        for n, p in enumerate(posicoes, start=1):
            if p.get("cenaId"):
                cena = db.get(Cena, _uuid(p["cenaId"]))
                if cena is None or cena.archived:
                    raise MotorErro("entrada_invalida",
                                    f"A IA propôs reaproveitar uma cena que não existe (cena {n})")
                cenas_ids.append(cena.id)
                continue
            cenas_ids.append(self._cena_nova(db, actor, r, produtos, p["nova"], ia).id)
        before = history.snapshot(r)
        r.frases = frases
        for velha in list(r.posicoes_rel):
            r.posicoes_rel.remove(velha)
        db.flush()
        for ordem, (p, cena_id) in enumerate(zip(posicoes, cenas_ids, strict=True)):
            r.posicoes_rel.append(RoteiroCena(roteiro_id=r.id, ordem=ordem, cena_id=cena_id,
                                              frases=list(p["frases"])))
        r.avisos = avisos
        db.flush()
        maquina.portao(db, r, "texto")
        r.updated_by = actor.user_id
        history.record(db, actor, ENTITY, r, "updated", before, history.snapshot(r),
                       {"acao": "plano", "geracaoId": str(geracao.id), "ia": ia,
                        "reaproveitadas": sum(1 for p in posicoes if p.get("cenaId"))})

    def _cena_nova(self, db: Session, actor: Actor, r: Roteiro,
                   produtos: list[tuple[Produto, uuid.UUID | None]], nova: dict[str, Any],
                   ia: dict[str, Any]) -> Cena:
        idx = nova.get("produto")
        produto, variante = (produtos[idx - 1] if isinstance(idx, int) and 1 <= idx
                             <= len(produtos) else (produtos[0] if produtos else (None, None)))
        if produto is not None and variante is None:
            v = next(iter(produto.ativas()), None)
            variante = v.id if v else None
        try:
            body = cenas_schemas.CenaIn(
                nome=nova["nome"][:120], acao=nova["acao"][:1000],
                plano=CenaPlano(nova["plano"]) if nova.get("plano") else None,
                movimento=nova.get("movimento"),
                camera=(nova.get("camera") or None) and nova["camera"][:500],
                avatar_id=r.avatar_id, produto_id=produto.id if produto else None,
                produto_variante_id=variante)
        except (ValidationError, ValueError) as exc:
            raise MotorErro("entrada_invalida", "A IA propôs uma cena fora do formato",
                            detalhe=str(exc)[:300]) from exc
        locais = {"motor": CenaMotor(nova.get("motor") or "minimax"),
                  "keyframe_instrucao": (nova.get("keyframe_instrucao") or "")[:2000] or None}
        return cenas_service.criar(db, actor, r.perfil_id, body, exige_ativo=False,
                                   locais=locais, details={"ia": ia, "roteiroId": str(r.id)})


def _uuid(valor: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(valor))
    except ValueError:
        return None


# ---- roteiro.narracao ----

class RoteiroNarracaoAplicador(_DoRoteiro):
    def pedido_tts(self, db: Session, geracao: Geracao) -> dict[str, Any]:
        p = geracao.params
        voz = db.get(Voz, uuid.UUID(p["vozId"]))
        problema = estado.problema_da_voz(voz)
        if problema:  # R16: revogada entre o pedido e o motor
            raise MotorErro("entrada_invalida", problema[1])
        seeds = p.get("seeds") or [1]
        return {"op": "paragrafo", "velocidade": p["velocidade"],
                "corpo": {**p["corpo"], "seed": int(seeds[0])}}

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        r = db.get(Roteiro, geracao.alvo_id, with_for_update=True)
        if r is None:
            raise MotorErro("entrada_invalida", "O roteiro não existe mais")
        p, m = geracao.params, candidato.metricas or {}
        n = RoteiroNarracao(
            roteiro_id=r.id, geracao_id=geracao.id, audio_id=candidato.audio_id,
            voz_id=uuid.UUID(p["vozId"]), texto_hash=p["textoHash"],
            frases=list(p["corpo"]["sentences"]), tempos=m.get("tempos") or [],
            total_s=m.get("total_s") or m.get("segundos") or 0,
            similaridade=round(float(m.get("similaridade") or 0), 3),
            seed=int(candidato.seed if candidato.seed is not None else
                     (p.get("seeds") or [0])[0]),
            velocidade=p["velocidade"], created_by=geracao.created_by)
        db.add(n)
        db.flush()
        anterior = estado.narracao_ativa(db, r)
        if anterior is not None and anterior.desuso_em is None:
            anterior.desuso_em = _agora()
        r.narracao_id = n.id
        estado.recalcular_tempos(db, r)


# ---- cena.keyframe ----

class CenaKeyframe(_DaCena):
    def alvo_version(self, alvo: Cena) -> int:
        return alvo.version

    def normalizar_da(self, geracao: Geracao, png: bytes) -> bytes:
        """O keyframe na resolução da cena, com o recorte central (como o `cenario.cena`)."""
        largura = int(geracao.params.get("largura") or 736)
        altura = int(geracao.params.get("altura") or 1280)
        return ajustar(png, largura, altura)

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        cena = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        if candidato.image_id is None:
            raise ApiError(400, "candidato_invalido", "Esta opção não tem mais o arquivo")
        details: dict[str, Any] = {"candidato": {"id": str(candidato.id),
                                                 "numero": candidato.numero}}
        if actor.kind == "system:roteiro":
            details["automatico"] = True
        rid = estado.do_roteiro(geracao)
        if rid:
            details["roteiroId"] = str(rid)
        cenas_service.definir_keyframe(db, actor, cena, candidato.image_id,
                                       geracao_id=geracao.id, details=details)


def ajustar(dados: bytes, largura: int, altura: int) -> bytes:
    try:
        with PILImage.open(io.BytesIO(dados)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            out = ImageOps.fit(im, (largura, altura), PILImage.LANCZOS)
    except Exception as exc:  # imagem ilegível
        raise MotorErro("entrada_invalida", "A imagem do keyframe é inválida",
                        detalhe=repr(exc)) from exc
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


# ---- cena.clipe ----

class CenaClipe(_DaCena):
    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        cena = db.get(Cena, geracao.alvo_id, with_for_update=True)
        if cena is None:
            raise MotorErro("entrada_invalida", "A cena não existe mais")
        refs = geracao.params.get("referencias") or []
        ex = estado.extras(geracao)
        tomada = cenas_tomadas.registrar_tomada(
            db, actor, cena, None, TomadaOrigem.geracao_local,
            prompt_usado=geracao.params.get("prompt") or "", geracao_id=geracao.id,
            keyframe_image_id=uuid.UUID(refs[0]), motor=CenaMotor(ex.get("motor") or "minimax"),
            objeto_existente=candidato)
        # A posição que pediu passa a usar a tomada nova, se ela serve (do keyframe atual e com
        # a duração da posição); as outras escolhem pela ordem do R10 no `avancar`.
        rid, ordem = estado.do_roteiro(geracao), ex.get("ordem")
        r = db.get(Roteiro, rid, with_for_update=True) if rid else None
        p = next((p for p in r.posicoes_rel if p.ordem == ordem), None) if r else None
        if p is not None and p.cena_id == cena.id and p.duracao_s is not None and \
                estado.tomada_serve(tomada, cena, p.duracao_s, aceita_flow=False):
            maquina._definir_tomada(db, p, tomada)
            p.aviso = None


# ---- roteiro.montagem e roteiro.acabamento ----

def _baixar_posicoes(ctx: Any, ex: dict[str, Any]) -> list[tuple[Path, float]]:
    saida = []
    for i, p in enumerate(ex.get("posicoes") or []):
        if not p.get("videoKey"):
            raise MotorErro("entrada_invalida", f"A posição {i + 1} está sem tomada")
        if montagem.tomada_curta(int(p.get("duracaoMs") or 0), float(p["duracaoS"])):
            raise MotorErro("entrada_invalida",
                            f"A tomada da posição {i + 1} é mais curta que a cena")
        saida.append((ctx.baixar(p["videoKey"], "videos", f"tomada_{i:02d}.mp4"),
                      float(p["duracaoS"])))
    return saida


def _narracao(ctx: Any, ex: dict[str, Any]) -> Path:
    if not ex.get("audioKey"):
        raise MotorErro("entrada_invalida", "A narração não tem mais o arquivo")
    return ctx.baixar(ex["audioKey"], "audios", "narracao.wav")


def _definir_ponteiro(db: Session, r: Roteiro, campo: str, geracao: Geracao) -> bool:
    """Aponta a prévia (ou o acabamento) atual; a de outra assinatura fica em desuso."""
    if estado.extras(geracao).get("assinatura") != estado.assinatura(r):
        geracao.desuso_em = _agora()
        return False
    anterior = db.get(Geracao, getattr(r, campo)) if getattr(r, campo) else None
    if anterior is not None and anterior.id != geracao.id and anterior.desuso_em is None:
        anterior.desuso_em = _agora()
    setattr(r, campo, geracao.id)
    return True


class RoteiroMontagem(_DoRoteiro):
    def executar_video(self, geracao: Geracao, ctx: Any) -> Path:
        ex = estado.extras(geracao)
        tomadas = _baixar_posicoes(ctx, ex)
        narr = _narracao(ctx, ex)
        ctx.andamento(40, "Montando a prévia")
        return montagem.montar_previa(ctx.pasta, tomadas, narr, largura=int(ex["largura"]),
                                      altura=int(ex["altura"]))

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        r = db.get(Roteiro, geracao.alvo_id, with_for_update=True)
        if r is not None:
            _definir_ponteiro(db, r, "montagem_geracao_id", geracao)


class RoteiroAcabamento(_DoRoteiro):
    def executar_video(self, geracao: Geracao, ctx: Any) -> Path:
        ex = estado.extras(geracao)
        largura, altura = int(ex["largura"]), int(ex["altura"])
        seeds = geracao.params.get("seeds") or [1]
        tomadas = _baixar_posicoes(ctx, ex)
        narr = _narracao(ctx, ex)
        ampliadas = []
        for i, (src, duracao_s) in enumerate(tomadas):
            ctx.checar()
            ctx.andamento(i * 80 // max(1, len(tomadas)),
                          f"Ampliando a cena {i + 1} de {len(tomadas)}")
            corte = ctx.pasta / f"corte_{i:02d}.mp4"
            montagem.executar(montagem.cmd_cortar(src, corte, duracao_s=duracao_s,
                                                  largura=largura, altura=altura))
            dados = ctx.rodar_bloco("upscale_video", {
                "video": corte.read_bytes(), "width": largura, "height": altura,
                "seed": int(seeds[0]), "prefix": f"sociman/{geracao.id}"}, f"pos{i}")
            bruto = ctx.pasta / f"seedvr_{i:02d}.mp4"
            bruto.write_bytes(dados)
            ampliadas.append(bruto)
        ctx.andamento(85, "Juntando e finalizando em HD")
        hds = montagem.tirar_cintilacao(ctx.pasta, ampliadas)
        final = montagem.acabar(ctx.pasta, hds, narr, largura=largura, altura=altura)
        ctx.liberar_gpu()
        return final

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        r = db.get(Roteiro, geracao.alvo_id, with_for_update=True)
        if r is None or r.archived:
            geracao.desuso_em = _agora()
            return
        if _definir_ponteiro(db, r, "acabamento_geracao_id", geracao):
            entrega.entregar(db, r, geracao, candidato)


APLICADORES: dict[str, base.Aplicador] = {
    "roteiro.plano": RoteiroPlano(), "roteiro.narracao": RoteiroNarracaoAplicador(),
    "cena.keyframe": CenaKeyframe(), "cena.clipe": CenaClipe(),
    "roteiro.montagem": RoteiroMontagem(), "roteiro.acabamento": RoteiroAcabamento(),
}


def registrar() -> None:
    base.APLICADORES.update(APLICADORES)


registrar()
