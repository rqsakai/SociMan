"""Os quadros (keyframes) da cena do vídeo guiado (spec 031, data-model `cena_quadros`, R3 e R8).

- a cena de `trechos` trechos tem `trechos + 1` quadros ativos, na ordem 0..trechos, com o papel
  de `roteiros.grade.papeis` (início, meio 1, meio 2, fim);
- o quadro não tem versão própria: toda mudança grava uma versão da **cena** com
  `details.quadro` = a ordem (como a variante do produto da 012);
- `keyframe_inicial_id`/`keyframe_final_id` são espelhos do quadro 0 e do último, gravados aqui
  na mesma transação (a 010, o `tomada_serve` da 011 e o prompt do Flow continuam lendo deles);
  o `keyframe_geracao_id` espelha a geração do quadro 0;
- nada é apagado: refazer arquiva o quadro (e os seguintes, FR-026/028) e recria a vaga na mesma
  ordem, com a mesma instrução (ou a nova do ajuste);
- mudar um quadro que já tinha imagem zera as aprovações (R9) de toda posição de roteiro com esta
  cena: a da sequência e a dos clipes (os trechos tocam os quadros refeitos). `confirmar` é a
  aprovação humana da sequência: os provisórios deixam de ser.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sociman_api.auth.deps import Actor
from sociman_api.cenas import service as cenas_service
from sociman_api.cenas.models import Cena, CenaQuadro, QuadroPapel
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Image, ImageKind
from sociman_api.roteiros import grade

_ESPELHOS = {"keyframe_inicial_id", "keyframe_final_id", "keyframe_geracao_id"}


def ativos(db: Session, cena_id: uuid.UUID) -> list[CenaQuadro]:
    """Os quadros não arquivados da cena, na ordem."""
    return list(db.scalars(select(CenaQuadro).where(CenaQuadro.cena_id == cena_id,
                                                    CenaQuadro.archived_at.is_(None))
                           .order_by(CenaQuadro.ordem)))


def por_ordem(db: Session, cena_id: uuid.UUID, ordem: int) -> CenaQuadro | None:
    return db.scalar(select(CenaQuadro).where(CenaQuadro.cena_id == cena_id,
                                              CenaQuadro.ordem == ordem,
                                              CenaQuadro.archived_at.is_(None)))


def completos(quadros: list[CenaQuadro]) -> bool:
    """Todos os quadros têm imagem (os provisórios contam: a aprovação é da posição)."""
    return bool(quadros) and all(q.image_id is not None for q in quadros)


def _registrar(db: Session, actor: Actor, cena: Cena, before: dict[str, Any],
               details: dict[str, Any]) -> None:
    cenas_service._record(db, actor, cena, "updated", before, details, sempre=True)


def _espelhar(db: Session, cena: Cena) -> None:
    """Quadro 0 → `keyframe_inicial_id` (e a geração), último → `keyframe_final_id`. Sem o
    inicial, o final fica nulo (`ck_cenas_keyframe`)."""
    qs = ativos(db, cena.id)
    inicial = qs[0].image_id if qs and qs[0].ordem == 0 else None
    final = qs[-1].image_id if inicial is not None and len(qs) > 1 else None
    geracao = qs[0].geracao_id if inicial is not None else None
    novos = {"keyframe_inicial_id": inicial, "keyframe_final_id": final,
             "keyframe_geracao_id": geracao}
    mudou = {c for c, v in novos.items() if getattr(cena, c) != v}
    if not mudou:
        return
    cenas_service.conferir_locais_em_usada(db, cena, mudou & _ESPELHOS)
    for campo in mudou:
        setattr(cena, campo, novos[campo])
    db.flush()


def criar(db: Session, actor: Actor, cena: Cena, instrucoes: list[str], *,
          details: dict[str, Any] | None = None) -> list[CenaQuadro]:
    """Cria as vagas da sequência (`len(instrucoes)` = trechos + 1, de 2 a 4) numa cena ainda sem
    quadros, e grava `cenas.trechos`."""
    papeis = grade.papeis(len(instrucoes))  # 2 a 4, senão GradeInvalida
    if ativos(db, cena.id):
        raise ApiError(409, "conflict", "Esta cena já tem a sequência de quadros")
    before = cenas_service.history.snapshot(cena)
    cena.trechos = len(instrucoes) - 1
    novos = [CenaQuadro(cena_id=cena.id, ordem=i, papel=QuadroPapel(papel),
                        instrucao=(texto or "").strip()[:2000], created_by=actor.user_id)
             for i, (papel, texto) in enumerate(zip(papeis, instrucoes, strict=True))]
    db.add_all(novos)
    db.flush()
    _registrar(db, actor, cena, before, {"acao": "quadros", "quadros": len(novos),
                                         **(details or {})})
    return novos


def copiar_imagens(db: Session, actor: Actor, cena: Cena, origem: Cena, ate: int, *,
                   details: dict[str, Any] | None = None) -> list[int]:
    """Na cena derivada (FR-022), os quadros 0..`ate`-1 ficam com a imagem do quadro da origem
    (a sequência já aprovada lá; não são provisórios). Para no 1º quadro da origem sem imagem
    (o seguinte nasce do anterior, R3). Devolve as ordens copiadas."""
    da_origem = {q.ordem: q for q in ativos(db, origem.id)}
    before = cenas_service.history.snapshot(cena)
    copiadas = []
    for q in ativos(db, cena.id):
        o = da_origem.get(q.ordem)
        if q.ordem >= ate or o is None or o.image_id is None:
            break
        q.image_id, q.provisorio = o.image_id, False
        copiadas.append(q.ordem)
    if not copiadas:
        return []
    db.flush()
    _espelhar(db, cena)
    _registrar(db, actor, cena, before, {"acao": "quadros_copiados", "quadros": copiadas,
                                         **(details or {})})
    return copiadas


def _imagem_keyframe(db: Session, image_id: uuid.UUID) -> None:
    img = db.get(Image, image_id)
    if img is None or img.kind != ImageKind.keyframe:
        raise cenas_service.invalida("quadro", "use uma imagem de keyframe da biblioteca")


def _zerar_aprovacoes(db: Session, cena_id: uuid.UUID) -> None:
    """R9 (FR-028): as aprovações das posições com esta cena deixam de valer (técnicas, fora do
    snapshot de versão própria; o roteiro as relê)."""
    from sociman_api.roteiros.models import RoteiroCena  # a seta é roteiros → cenas

    db.execute(update(RoteiroCena).where(RoteiroCena.cena_id == cena_id).values(
        aprovado_keyframes_em=None, aprovado_keyframes_por=None, aprovado_clipe_em=None,
        aprovado_clipe_por=None).execution_options(synchronize_session="fetch"))


def _arquivar_e_recriar(db: Session, actor: Actor, cena: Cena, desde: int,
                        instrucoes: dict[int, str] | None) -> list[int]:
    """Arquiva os quadros a partir de `desde` que já têm imagem, geração ou instrução nova, e
    recria cada vaga (mesma ordem e papel). Devolve as ordens refeitas."""
    instrucoes = instrucoes or {}
    agora = datetime.now(UTC)
    velhos = [q for q in ativos(db, cena.id) if q.ordem >= desde and (
        q.image_id is not None or q.geracao_id is not None or q.ordem in instrucoes)]
    for q in velhos:
        q.archived_at, q.archived_by = agora, actor.user_id
    db.flush()  # o UNIQUE parcial: a vaga nova só depois de arquivar a velha
    for q in velhos:
        texto = instrucoes.get(q.ordem, q.instrucao)
        db.add(CenaQuadro(cena_id=cena.id, ordem=q.ordem, papel=q.papel,
                          instrucao=(texto or "").strip()[:2000], created_by=actor.user_id))
    db.flush()
    return [q.ordem for q in velhos]


def arquivar_desde(db: Session, actor: Actor, cena: Cena, ordem: int, *,
                   instrucoes: dict[int, str] | None = None,
                   details: dict[str, Any] | None = None) -> list[int]:
    """Refazer o quadro `ordem` (FR-026/028): ele e os seguintes viram "a refazer" (arquivados e
    recriados com a mesma instrução, ou a de `instrucoes`), e os espelhos acompanham. Os trechos
    que tocam os refeitos deixam de servir pela chave do R8 (`tomada_serve_trecho`). Numa cena
    `usada` com keyframe, 409 `cena_usada` (duplique). Devolve as ordens refeitas."""
    if cena.archived:
        raise ApiError(409, "arquivada", "Restaure a cena antes de alterar")
    if any(q.image_id is not None for q in ativos(db, cena.id) if q.ordem >= ordem):
        cenas_service.conferir_locais_em_usada(db, cena, _ESPELHOS)
    before = cenas_service.history.snapshot(cena)
    refeitas = _arquivar_e_recriar(db, actor, cena, ordem, instrucoes)
    if not refeitas:
        return []
    _zerar_aprovacoes(db, cena.id)
    _espelhar(db, cena)
    _registrar(db, actor, cena, before, {"acao": "quadros_refazer", "quadro": ordem,
                                         "refeitos": refeitas, **(details or {})})
    return refeitas


def definir_imagem(db: Session, actor: Actor, quadro: CenaQuadro, image_id: uuid.UUID, *,
                   provisorio: bool = False, geracao_id: uuid.UUID | None = None,
                   details: dict[str, Any] | None = None) -> bool:
    """A imagem de um quadro ativo (a opção escolhida, ou a única aplicada provisoriamente pela
    máquina, R3). Trocar a imagem de um quadro que já tinha uma refaz os seguintes (nasceram do
    antigo). Grava a versão da cena com `details.quadro`. Devolve se mudou."""
    if quadro.archived:
        raise ApiError(409, "quadro_mudou", "Este quadro foi refeito; use o quadro atual")
    cena = db.get(Cena, quadro.cena_id, with_for_update=True)
    if cena is None or cena.archived:
        raise ApiError(409, "arquivada", "Restaure a cena antes de alterar")
    _imagem_keyframe(db, image_id)
    if quadro.image_id == image_id and quadro.provisorio == provisorio and \
            (geracao_id is None or quadro.geracao_id == geracao_id):
        return False
    if quadro.image_id is not None and quadro.image_id != image_id:
        cenas_service.conferir_locais_em_usada(db, cena, _ESPELHOS)
    before = cenas_service.history.snapshot(cena)
    refeitas: list[int] = []
    if quadro.image_id is not None and quadro.image_id != image_id:
        refeitas = _arquivar_e_recriar(db, actor, cena, quadro.ordem + 1, None)
        _zerar_aprovacoes(db, cena.id)
    quadro.image_id = image_id
    quadro.provisorio = provisorio
    if geracao_id is not None:
        quadro.geracao_id = geracao_id
    db.flush()
    _espelhar(db, cena)
    info: dict[str, Any] = {"acao": "quadro", "quadro": quadro.ordem, "imageId": str(image_id),
                            "provisorio": provisorio, **(details or {})}
    if geracao_id is not None:
        info.setdefault("geracaoId", str(geracao_id))
    if refeitas:
        info["refeitos"] = refeitas
    _registrar(db, actor, cena, before, info)
    return True


def confirmar(db: Session, actor: Actor, cena: Cena, details: dict[str, Any] | None = None
              ) -> bool:
    """A aprovação humana da sequência (R9): os quadros provisórios deixam de ser. Grava a versão
    da cena só se algum mudou."""
    provisorios = [q for q in ativos(db, cena.id) if q.provisorio]
    if not provisorios:
        return False
    before = cenas_service.history.snapshot(cena)
    for q in provisorios:
        q.provisorio = False
    db.flush()
    _registrar(db, actor, cena, before, {"acao": "quadros_confirmados",
                                         "quadros": [q.ordem for q in provisorios],
                                         **(details or {})})
    return True


def ligar_geracao(db: Session, quadro: CenaQuadro, geracao_id: uuid.UUID) -> None:
    """A geração aberta do quadro (técnico: o pedido não versiona a cena)."""
    quadro.geracao_id = geracao_id
    db.flush()
