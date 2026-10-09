"""Aplicadores das vozes (spec 025, US2, contracts/passos.md, research R11–R13).

- `voz.gravacao`: exige a gravação enviada e o consentimento (400 `consentimento_ausente`); o
  shop-tts recebe o áudio original (`register`);
- `voz.design`: a voz sintética pela descrição em inglês (`design`);
- `voz.teste`: narra um texto com a voz sincronizada (409 `voz_nao_sincronizada`); não aplica no
  alvo (`aplica_alvo = False`, termina em `entregue`).
Escolher (gravação ou design) grava a referência, a transcrição e `aprovada`, com
`sincronizada_em = null` (a linha `vozes_sync` do gerador importa no shop-tts). O status da voz
segue a geração pelo gancho `ao_mudar_estado`, com uma versão da voz a cada mudança.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.assets import service_padrao
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.geracao import aplicadores as base
from sociman_api.geracao.models import (
    FINAIS,
    Geracao,
    GeracaoAlvo,
    GeracaoCandidato,
    GeracaoStatus,
)
from sociman_api.vozes import service as vozes_service
from sociman_api.vozes.models import Voz, VozOrigem
from sociman_api.vozes.tts_id import tts_id

PASSOS_REF = ("voz.gravacao", "voz.design")
TEXTO_DESIGN = ("Gente, olha que achadinho incrível! Esse é o produto que eu mais uso no dia a "
                "dia, e hoje ele está com um preço que vale muito a pena. Corre lá no link!")


def _abertas(db: Session, voz_id: uuid.UUID, passos: tuple[str, ...],
             exceto: uuid.UUID | None = None) -> list[Geracao]:
    stmt = select(Geracao).where(Geracao.alvo_tipo == GeracaoAlvo.voz,
                                 Geracao.alvo_id == voz_id, Geracao.passo.in_(list(passos)),
                                 Geracao.status.not_in(FINAIS))
    if exceto is not None:
        stmt = stmt.where(Geracao.id != exceto)
    return list(db.scalars(stmt))


class _VozBase(base.Aplicador):
    passo = ""

    def validar_alvo(self, db: Session, perfil_id: uuid.UUID | None, alvo_id: uuid.UUID, *,
                     lock: bool = False) -> Voz:
        voz = db.get(Voz, alvo_id, with_for_update=lock)
        if voz is None:
            raise base.alvo_nao_encontrado()
        if voz.revogada:
            raise service_padrao.consentimento_revogado()
        if voz.archived:
            raise base.alvo_arquivado()
        return voz

    def conferir_referencias(self, db: Session, geracao: Geracao) -> None:
        return None  # a entrada é a voz (gravação, descrição ou texto), não imagens

    def _sem_imagens(self, pedido: base.Pedido) -> None:
        if pedido.referencias:
            raise base.entrada_invalida("referencias", "não se aplica a vozes")


class _Referencia(_VozBase):
    def _comum(self, db: Session, voz: Voz, pedido: base.Pedido) -> None:
        self._sem_imagens(pedido)
        self.conferir_extras(pedido.extras)
        if pedido.texto is not None:
            raise base.entrada_invalida("texto", "não se aplica a este passo")
        if _abertas(db, voz.id, PASSOS_REF):
            raise ApiError(409, "geracao_em_andamento",
                           "Já existe uma geração deste passo em andamento")

    def aplicar(self, db: Session, actor: Actor, geracao: Geracao,
                candidato: GeracaoCandidato) -> None:
        voz = self.validar_alvo(db, geracao.perfil_id, geracao.alvo_id, lock=True)
        if candidato.audio_id is None:
            raise ApiError(400, "candidato_invalido", "Esta opção não tem mais o áudio")
        before = history.snapshot(voz)
        voz.ref_audio_id = candidato.audio_id
        voz.ref_texto = (candidato.metricas or {}).get("transcricao") or ""
        voz.status = vozes_service.VozStatus.aprovada
        voz.sincronizada_em = None
        vozes_service.gravar(db, actor, voz, "updated", before, details={
            "geracao_id": str(geracao.id), "candidato": {"id": str(candidato.id),
                                                         "numero": candidato.numero}})

    def ao_mudar_estado(self, db: Session, geracao: Geracao, de: GeracaoStatus | None,
                        para: GeracaoStatus) -> None:
        voz = db.get(Voz, geracao.alvo_id, with_for_update=True)
        if voz is None or para == GeracaoStatus.escolhido:
            return
        before = history.snapshot(voz)
        analise = None
        if para == GeracaoStatus.revisao:
            cands = list(db.scalars(select(GeracaoCandidato).where(
                GeracaoCandidato.geracao_id == geracao.id).order_by(GeracaoCandidato.numero)))
            analise = next(((c.metricas or {}).get("analise") for c in cands
                            if (c.metricas or {}).get("analise")), None)
        outra = bool(_abertas(db, voz.id, PASSOS_REF, exceto=geracao.id))
        vozes_service.status_pelo_gancho(db, voz, para, outra, analise)
        db.flush()
        if history.snapshot(voz) != before:
            ator = Actor(kind="user", user_id=geracao.created_by)
            voz.updated_by = geracao.created_by
            history.record(db, ator, "voz", voz, "updated", before, history.snapshot(voz),
                           {"geracao_id": str(geracao.id), "automatico": True})


class Gravacao(_Referencia):
    passo = "voz.gravacao"

    def montar_params(self, db: Session, actor: Actor, alvo: Voz, pedido: base.Pedido
                      ) -> dict[str, Any]:
        if alvo.origem != VozOrigem.gravacao:
            raise base.alvo_incompativel()
        self._comum(db, alvo, pedido)
        if alvo.gravacao_audio_id is None:
            raise base.entrada_invalida("gravacaoAudioId", "envie a gravação antes")
        if not (alvo.consentimento or {}).get("nome"):
            raise ApiError(400, "consentimento_ausente",
                           "Registre o consentimento da pessoa antes de usar a gravação")
        return {"instrucao": "", "referencias": [], "rotulo": pedido.rotulo, "texto": None,
                "extras": None, "gravacao_audio_id": str(alvo.gravacao_audio_id)}

    def pedido_tts(self, db: Session, geracao: Geracao) -> dict[str, Any]:
        voz = db.get(Voz, geracao.alvo_id)
        return {"op": "register", "audio_id": geracao.params["gravacao_audio_id"],
                "nome": tts_id(voz.id), "tom": voz.tom}


class Design(_Referencia):
    passo = "voz.design"

    def montar_params(self, db: Session, actor: Actor, alvo: Voz, pedido: base.Pedido
                      ) -> dict[str, Any]:
        if alvo.origem != VozOrigem.sintetica:
            raise base.alvo_incompativel()
        self._comum(db, alvo, pedido)
        service_padrao.checar_menoridade(pedido.instrucao, alvo.descricao)
        return {"instrucao": pedido.instrucao.strip(), "referencias": [], "rotulo": pedido.rotulo,
                "texto": None, "extras": None}

    def pedido_tts(self, db: Session, geracao: Geracao) -> dict[str, Any]:
        voz = db.get(Voz, geracao.alvo_id)
        return {"op": "design", "nome": tts_id(voz.id), "descricao": voz.descricao,
                "texto": geracao.params.get("instrucao") or TEXTO_DESIGN}


class Teste(_VozBase):
    passo = "voz.teste"

    def montar_params(self, db: Session, actor: Actor, alvo: Voz, pedido: base.Pedido
                      ) -> dict[str, Any]:
        self._sem_imagens(pedido)
        self.conferir_extras(pedido.extras)
        texto = (pedido.texto or "").strip()
        if not texto:
            raise base.entrada_invalida("texto", "escreva o texto do teste")
        if alvo.ref_audio_id is None or alvo.sincronizada_em is None:
            raise ApiError(409, "voz_nao_sincronizada",
                           "A voz ainda não foi enviada ao serviço de voz")
        if _abertas(db, alvo.id, ("voz.teste",)):
            raise ApiError(409, "geracao_em_andamento", "Já há um teste desta voz em andamento")
        return {"instrucao": "", "referencias": [], "rotulo": None, "texto": texto,
                "extras": None}

    def pedido_tts(self, db: Session, geracao: Geracao) -> dict[str, Any]:
        voz = db.get(Voz, geracao.alvo_id)
        return {"op": "tts", "corpo": {"voice": tts_id(voz.id),
                                        "sentences": [geracao.params["texto"]]}}


APLICADORES: dict[str, base.Aplicador] = {"voz.gravacao": Gravacao(), "voz.design": Design(),
                                          "voz.teste": Teste()}
