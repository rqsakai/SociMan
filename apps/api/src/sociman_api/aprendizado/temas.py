"""Taxonomia de temas do perfil (spec 023, US1; FR-001, FR-007; data-model "Regras de
transição").

Só o dono humano escreve (as rotas usam `RequireHumanOwner`). Toda mutação faz
`check_version`, grava a versão em `entity_versions` (`aprendizado_tema`) e sobe
`preferencias.taxonomia_versao` do perfil na mesma transação. Nada é apagado:
- **arquivar** leva as classificações do tema a "Sem tema" (as da IA ficam para reclassificar;
  as do dono continuam do dono) e guarda a lista em `details.movidas`;
- **juntar** A → B arquiva A com `juntado_em_id = B` e move as classificações (principal e
  secundárias), com a lista em `details.juntar`;
- **restaurar** ou **reverter** devolve o que foi movido, desde que a classificação não tenha
  mudado depois.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import preferencias as prefs
from sociman_api.aprendizado import schemas
from sociman_api.aprendizado.models import Classificacao, Origem, Tema
from sociman_api.auth.deps import Actor
from sociman_api.errors import ApiError
from sociman_api.ia.guia import normalizar
from sociman_api.perfis.models import Perfil
from sociman_api.perfis.schemas import RevertIn, VersionsList
from sociman_api.perfis.service_perfis import get_perfil_or_404, target_state, versions_out

ENTITY = "aprendizado_tema"
ENTITY_CLASS = "aprendizado_classificacao"
LABEL = "Este tema"


# ---- validação ----

def _invalido(campo: str, mensagem: str) -> ApiError:
    return ApiError(400, "validation_error", mensagem, details={"fields": {campo: mensagem}})


def palavras(brutas: Sequence[str], campo: str = "palavrasChave") -> list[str]:
    """Normalizadas (sem acento, sem caixa), sem vazias e sem repetir; 2–30 caracteres."""
    out: list[str] = []
    for i, bruta in enumerate(brutas):
        p = normalizar(bruta)
        if not p:
            continue
        if not K.PALAVRA_MIN <= len(p) <= K.PALAVRA_MAX:
            raise _invalido(f"{campo}.{i}",
                            f"Cada palavra-chave tem de {K.PALAVRA_MIN} a {K.PALAVRA_MAX} "
                            "caracteres")
        if p not in out:
            out.append(p)
    if len(out) > K.PALAVRAS_MAX:
        raise _invalido(campo, f"No máximo {K.PALAVRAS_MAX} palavras-chave")
    return out


def _perfil_ativo(db: Session, perfil_id: uuid.UUID) -> Perfil:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise ApiError(409, "conflict", "Este perfil está arquivado")
    return perfil


def _ativos(db: Session, perfil_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Tema).where(
        Tema.perfil_id == perfil_id, Tema.archived_at.is_(None))) or 0


def _repetido(db: Session, perfil_id: uuid.UUID, nome_norm: str,
              exceto: uuid.UUID | None = None) -> bool:
    stmt = select(Tema.id).where(Tema.perfil_id == perfil_id, Tema.nome_norm == nome_norm,
                                 Tema.archived_at.is_(None))
    if exceto is not None:
        stmt = stmt.where(Tema.id != exceto)
    return db.scalar(stmt) is not None


def _erro_repetido(nome: str) -> ApiError:
    return ApiError(409, "tema_repetido", f"Já existe um tema ativo chamado \"{nome}\"")


def _erro_maximo() -> ApiError:
    return ApiError(409, "temas_no_maximo", f"O perfil já tem {K.MAX_TEMAS} temas ativos; "
                    "junte ou arquive algum antes")


def get_tema(db: Session, tema_id: uuid.UUID, lock: bool = False) -> Tema:
    tema = db.get(Tema, tema_id, with_for_update=lock)
    if tema is None:
        raise ApiError(404, "not_found", "Tema não encontrado")
    return tema


# ---- saída ----

def contagens(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    return dict(db.execute(select(Classificacao.tema_id, func.count())
                           .where(Classificacao.tema_id.in_(list(ids)))
                           .group_by(Classificacao.tema_id)).all())


def out(t: Tema, n: int = 0) -> schemas.AprendizadoTema:
    return schemas.AprendizadoTema(
        id=t.id, perfil_id=t.perfil_id, nome=t.nome, descricao=t.descricao,
        palavras_chave=list(t.palavras_chave), archived=t.archived,
        juntado_em_id=t.juntado_em_id, n_posts=n, version=t.version)


def outs(db: Session, temas: Sequence[Tema]) -> list[schemas.AprendizadoTema]:
    n = contagens(db, [t.id for t in temas])
    return [out(t, n.get(t.id, 0)) for t in temas]


def listar(db: Session, perfil_id: uuid.UUID, arquivados: bool = False
           ) -> schemas.AprendizadoTemasList:
    get_perfil_or_404(db, perfil_id)
    stmt = select(Tema).where(Tema.perfil_id == perfil_id)
    if not arquivados:
        stmt = stmt.where(Tema.archived_at.is_(None))
    temas = list(db.scalars(stmt.order_by(Tema.archived_at.is_not(None), Tema.nome, Tema.id)))
    return schemas.AprendizadoTemasList(items=outs(db, temas),
                                        taxonomia_versao=prefs.taxonomia_versao(db, perfil_id))


# ---- criar ----

def _novo(db: Session, actor: Actor, perfil_id: uuid.UUID, body: schemas.AprendizadoTemaIn,
          details: dict[str, Any] | None = None) -> Tema:
    tema = Tema(perfil_id=perfil_id, nome=body.nome, nome_norm=normalizar(body.nome),
                descricao=body.descricao, palavras_chave=palavras(body.palavras_chave),
                created_by=actor.user_id, updated_by=actor.user_id)
    db.add(tema)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise _erro_repetido(body.nome) from exc
    history.record(db, actor, ENTITY, tema, "created", None, history.snapshot(tema), details)
    return tema


def criar(db: Session, actor: Actor, perfil_id: uuid.UUID,
          body: schemas.AprendizadoTemaIn) -> schemas.AprendizadoTema:
    _perfil_ativo(db, perfil_id)
    prefs.travar_perfil(db, actor, perfil_id)  # serializa as mudanças de taxonomia do perfil
    if _ativos(db, perfil_id) >= K.MAX_TEMAS:
        raise _erro_maximo()
    if _repetido(db, perfil_id, normalizar(body.nome)):
        raise _erro_repetido(body.nome)
    tema = _novo(db, actor, perfil_id, body)
    prefs.incrementar_taxonomia(db, actor, perfil_id)
    db.flush()
    return out(tema)


def lote(db: Session, actor: Actor, perfil_id: uuid.UUID,
         body: schemas.AprendizadoTemasLoteIn) -> schemas.AprendizadoTemasLoteOut:
    """Salvar a proposta da IA (ou uma lista): tudo ou nada; marca a chamada (008)."""
    from sociman_api.aprendizado import chamada as chamada_mod  # import tardio (ciclo)

    _perfil_ativo(db, perfil_id)
    prefs.travar_perfil(db, actor, perfil_id)
    if _ativos(db, perfil_id) + len(body.temas) > K.MAX_TEMAS:
        raise _erro_maximo()
    vistos: set[str] = set()
    for t in body.temas:
        chave = normalizar(t.nome)
        if chave in vistos or _repetido(db, perfil_id, chave):
            raise _erro_repetido(t.nome)
        vistos.add(chave)
    details = chamada_mod.marcar_taxonomia(db, actor, perfil_id, body)
    temas = [_novo(db, actor, perfil_id, t, details) for t in body.temas]
    prefs.incrementar_taxonomia(db, actor, perfil_id)
    db.flush()
    return schemas.AprendizadoTemasLoteOut(items=[out(t) for t in temas])


# ---- editar ----

def editar(db: Session, actor: Actor, tema_id: uuid.UUID,
           body: schemas.AprendizadoTemaPatch) -> schemas.AprendizadoTema:
    tema = get_tema(db, tema_id, lock=True)
    _perfil_ativo(db, tema.perfil_id)
    history.check_version(tema, body.version, LABEL)
    if tema.archived:
        raise ApiError(409, "conflict", "Este tema está arquivado; restaure antes de editar")
    before = history.snapshot(tema)
    if body.nome is not None:
        if _repetido(db, tema.perfil_id, normalizar(body.nome), exceto=tema.id):
            raise _erro_repetido(body.nome)
        tema.nome, tema.nome_norm = body.nome, normalizar(body.nome)
    if body.descricao is not None:
        tema.descricao = body.descricao
    if body.palavras_chave is not None:
        tema.palavras_chave = palavras(body.palavras_chave)
    after = history.snapshot(tema)
    if after != before:
        tema.updated_by = actor.user_id
        history.record(db, actor, ENTITY, tema, "updated", before, after)
        prefs.incrementar_taxonomia(db, actor, tema.perfil_id)
    db.flush()
    return out(tema, contagens(db, [tema.id]).get(tema.id, 0))


# ---- mover classificações ----

def _classificacoes(db: Session, ids: Sequence[uuid.UUID]) -> list[Classificacao]:
    if not ids:
        return []
    return list(db.scalars(select(Classificacao).where(Classificacao.id.in_(list(ids)))
                           .with_for_update()))


def _gravar_class(db: Session, actor: Actor, c: Classificacao, before: dict[str, Any],
                  details: dict[str, Any]) -> None:
    after = history.snapshot(c)
    if after != before:
        c.updated_by = actor.user_id
        history.record(db, actor, ENTITY_CLASS, c, "updated", before, after, details)


def _sem_tema(db: Session, actor: Actor, tema: Tema) -> dict[str, list[str]]:
    """Arquivar: principal → "Sem tema" (a IA reclassifica as dela) e secundário removido."""
    principal = list(db.scalars(select(Classificacao).where(Classificacao.tema_id == tema.id)
                                .with_for_update()))
    secundario = list(db.scalars(select(Classificacao).where(
        Classificacao.secundarios.contains([tema.id])).with_for_update()))
    detalhe = {"arquivar": str(tema.id)}
    for c in principal:
        before = history.snapshot(c)
        c.tema_id = None
        c.reclassificar = c.origem == Origem.ia
        c.secundarios = [s for s in c.secundarios if s != tema.id]
        _gravar_class(db, actor, c, before, detalhe)
    for c in secundario:
        if c in principal:
            continue
        before = history.snapshot(c)
        c.secundarios = [s for s in c.secundarios if s != tema.id]
        _gravar_class(db, actor, c, before, detalhe)
    return {"movidas": [str(c.id) for c in principal],
            "secundarios": [str(c.id) for c in secundario if c not in principal]}


def _juntar_em(db: Session, actor: Actor, tema: Tema, destino: Tema) -> dict[str, Any]:
    from sociman_api.aprendizado import fonte_temas

    fonte_temas.limpar_tema(db, tema.id)
    principal = list(db.scalars(select(Classificacao).where(Classificacao.tema_id == tema.id)
                                .with_for_update()))
    secundario = list(db.scalars(select(Classificacao).where(
        Classificacao.secundarios.contains([tema.id])).with_for_update()))
    detalhe = {"juntar": {"origem": str(tema.id), "destino": str(destino.id)}}
    tocadas: dict[uuid.UUID, tuple[Classificacao, dict[str, Any]]] = {}
    for c in [*principal, *secundario]:
        tocadas.setdefault(c.id, (c, history.snapshot(c)))
    for c in principal:
        c.tema_id = destino.id
    for c, _ in tocadas.values():
        novos: list[uuid.UUID] = []
        for s in c.secundarios:
            s = destino.id if s == tema.id else s
            if s != c.tema_id and s not in novos:
                novos.append(s)
        c.secundarios = novos
    for c, before in tocadas.values():
        _gravar_class(db, actor, c, before, detalhe)
    return {"origem": str(tema.id), "destino": str(destino.id),
            "movidas": [str(c.id) for c in principal],
            "secundarios": [str(c.id) for c in secundario if c not in principal]}


def _ultimo_movimento(db: Session, tema: Tema) -> dict[str, Any] | None:
    """Os `details` da versão mais recente do tema que moveu classificações."""
    for v in history.list_versions(db, ENTITY, tema.id):
        if "movidas" in v.details or "juntar" in v.details:
            return v.details.get("juntar") or v.details
        if v.action in ("restored", "reverted") and not v.after.get("archived"):
            return None  # já devolvido
    return None


def _devolver(db: Session, actor: Actor, tema: Tema, mov: dict[str, Any] | None) -> int:
    """Restaurar: as classificações movidas voltam, se ninguém as mudou depois."""
    if not mov:
        return 0
    destino = uuid.UUID(mov["destino"]) if mov.get("destino") else None
    detalhe = {"restaurar": str(tema.id)}
    voltaram = 0
    for c in _classificacoes(db, [uuid.UUID(i) for i in mov.get("movidas", [])]):
        if c.tema_id != destino:
            continue
        before = history.snapshot(c)
        c.tema_id = tema.id
        c.secundarios = [s for s in c.secundarios if s != tema.id]
        if c.origem == Origem.ia:
            c.reclassificar = False
        _gravar_class(db, actor, c, before, detalhe)
        voltaram += 1
    for c in _classificacoes(db, [uuid.UUID(i) for i in mov.get("secundarios", [])]):
        before = history.snapshot(c)
        novos = [s for s in c.secundarios if s != destino] if destino else list(c.secundarios)
        if tema.id not in novos and c.tema_id != tema.id and len(novos) < K.SECUNDARIOS_MAX:
            novos.append(tema.id)
        c.secundarios = novos
        _gravar_class(db, actor, c, before, detalhe)
    return voltaram


# ---- arquivar, restaurar, juntar ----

def _arquivar(db: Session, actor: Actor, tema: Tema) -> dict[str, Any]:
    from sociman_api.aprendizado import fonte_temas  # o cache de casamento do tema sai na hora

    fonte_temas.limpar_tema(db, tema.id)
    mov = _sem_tema(db, actor, tema)
    tema.archived_at, tema.archived_by = datetime.now(UTC), actor.user_id
    return mov


def _restaurar(db: Session, actor: Actor, tema: Tema) -> int:
    if _ativos(db, tema.perfil_id) >= K.MAX_TEMAS:
        raise _erro_maximo()
    if _repetido(db, tema.perfil_id, tema.nome_norm, exceto=tema.id):
        raise _erro_repetido(tema.nome)
    mov = _ultimo_movimento(db, tema)
    tema.archived_at = tema.archived_by = None
    tema.juntado_em_id = None
    db.flush()
    return _devolver(db, actor, tema, mov)


def arquivar(db: Session, actor: Actor, tema_id: uuid.UUID,
             body: schemas.AprendizadoVersionIn) -> schemas.AprendizadoTema:
    tema = get_tema(db, tema_id, lock=True)
    _perfil_ativo(db, tema.perfil_id)
    history.check_version(tema, body.version, LABEL)
    if tema.archived:
        raise ApiError(409, "conflict", "Este tema já está arquivado")
    before = history.snapshot(tema)
    mov = _arquivar(db, actor, tema)
    tema.updated_by = actor.user_id
    history.record(db, actor, ENTITY, tema, "archived", before, history.snapshot(tema), mov)
    prefs.incrementar_taxonomia(db, actor, tema.perfil_id)
    db.flush()
    return out(tema)


def restaurar(db: Session, actor: Actor, tema_id: uuid.UUID,
              body: schemas.AprendizadoVersionIn) -> schemas.AprendizadoTema:
    tema = get_tema(db, tema_id, lock=True)
    _perfil_ativo(db, tema.perfil_id)
    prefs.travar_perfil(db, actor, tema.perfil_id)
    history.check_version(tema, body.version, LABEL)
    if not tema.archived:
        raise ApiError(409, "conflict", "Este tema não está arquivado")
    before = history.snapshot(tema)
    voltaram = _restaurar(db, actor, tema)
    tema.updated_by = actor.user_id
    history.record(db, actor, ENTITY, tema, "restored", before, history.snapshot(tema),
                   {"devolvidas": voltaram})
    prefs.incrementar_taxonomia(db, actor, tema.perfil_id)
    db.flush()
    return out(tema, contagens(db, [tema.id]).get(tema.id, 0))


def juntar(db: Session, actor: Actor, tema_id: uuid.UUID,
           body: schemas.AprendizadoJuntarIn) -> schemas.AprendizadoJuntarOut:
    tema = get_tema(db, tema_id, lock=True)
    _perfil_ativo(db, tema.perfil_id)
    history.check_version(tema, body.version, LABEL)
    destino = get_tema(db, body.destino_id, lock=True)
    if destino.id == tema.id or destino.perfil_id != tema.perfil_id:
        raise _invalido("destinoId", "Escolha outro tema ativo do mesmo perfil")
    if tema.archived or destino.archived:
        raise ApiError(409, "conflict", "Os dois temas precisam estar ativos")
    before = history.snapshot(tema)
    mov = _juntar_em(db, actor, tema, destino)
    tema.archived_at, tema.archived_by = datetime.now(UTC), actor.user_id
    tema.juntado_em_id = destino.id
    tema.updated_by = actor.user_id
    history.record(db, actor, ENTITY, tema, "archived", before, history.snapshot(tema),
                   {"juntar": mov})
    prefs.incrementar_taxonomia(db, actor, tema.perfil_id)
    db.flush()
    n = contagens(db, [destino.id])
    return schemas.AprendizadoJuntarOut(origem=out(tema), destino=out(destino, n.get(destino.id,
                                                                                    0)),
                                        movidas=len(mov["movidas"]))


# ---- histórico ----

def versions(db: Session, tema_id: uuid.UUID) -> VersionsList:
    tema = get_tema(db, tema_id)
    return versions_out(db, ENTITY, tema.id)


def reverter(db: Session, actor: Actor, tema_id: uuid.UUID,
             body: RevertIn) -> schemas.AprendizadoTema:
    """O snapshot da versão alvo; arquivar ou restaurar no caminho move as classificações."""
    tema = get_tema(db, tema_id, lock=True)
    _perfil_ativo(db, tema.perfil_id)
    prefs.travar_perfil(db, actor, tema.perfil_id)
    history.check_version(tema, body.version, LABEL)
    state = target_state(db, ENTITY, tema, body.to_version)  # type: ignore[arg-type]
    before = history.snapshot(tema)
    details: dict[str, Any] = {"from_version": body.to_version}
    alvo_arquivado = bool(state.get("archived"))
    if tema.archived and not alvo_arquivado:
        details["devolvidas"] = _restaurar(db, actor, tema)
    elif not tema.archived and alvo_arquivado:
        destino_id = state.get("juntado_em_id")
        destino = db.get(Tema, uuid.UUID(destino_id)) if destino_id else None
        if destino is not None and not destino.archived:
            details["juntar"] = _juntar_em(db, actor, tema, destino)
            tema.juntado_em_id = destino.id
        else:
            details |= _arquivar(db, actor, tema)
        tema.archived_at, tema.archived_by = datetime.now(UTC), actor.user_id
    nome = state.get("nome") or tema.nome
    if normalizar(nome) != tema.nome_norm and not tema.archived and _repetido(
            db, tema.perfil_id, normalizar(nome), exceto=tema.id):
        raise _erro_repetido(nome)
    tema.nome, tema.nome_norm = nome, normalizar(nome)
    tema.descricao = state.get("descricao") or ""
    tema.palavras_chave = list(state.get("palavras_chave") or [])
    after = history.snapshot(tema)
    if after == before:
        raise ApiError(400, "validation_error", "Essa versão é igual à atual")
    tema.updated_by = actor.user_id
    history.record(db, actor, ENTITY, tema, "reverted", before, after, details)
    prefs.incrementar_taxonomia(db, actor, tema.perfil_id)
    db.flush()
    return out(tema, contagens(db, [tema.id]).get(tema.id, 0))



# ---- proposta da IA (FR-002, R5) ----

def propor(db: Session, actor: Actor, perfil_id: uuid.UUID, body: schemas.AprendizadoProporIn,
           client: Any) -> schemas.AprendizadoProporOut:
    """Síncrona, como o "montar guia" da 017: até 40 posts recentes; nada é salvo além da
    chamada (com erro, commita a chamada e levanta como na 008)."""
    from sociman_api.aprendizado import chamada as chamada_mod
    from sociman_api.aprendizado import classificacao as cls
    from sociman_api.metricas.models import VideoRede

    perfil = _perfil_ativo(db, perfil_id)
    ids = list(db.scalars(cls._videos_do_perfil(perfil_id)
                          .order_by(VideoRede.publicado_em.desc(), VideoRede.id.desc())
                          .limit(K.TAXONOMIA_POSTS)))
    partes = []
    for vid in ids:
        video = db.get(VideoRede, vid)
        assert video is not None
        corte = cls._tem_corte(db, video)
        linhas = [f"Legenda: {(video.legenda or video.titulo or '').strip()[:300] or '(vazia)'}"]
        if corte is not None and corte.hook_text:
            linhas.append(f"Gancho: {corte.hook_text}")
        if corte is not None and (corte.transcript or "").strip():
            linhas.append("Começo da fala: "
                          + corte.transcript.strip()[:K.TAXONOMIA_TRANSCRICAO])
        partes.append(chamada_mod.bloco("post", "\n".join(linhas), id=str(vid)))
    atuais = cls.taxonomia(db, perfil_id)
    if atuais:
        partes.insert(0, chamada_mod.bloco("taxonomia", cls.texto_taxonomia(atuais)))
    if not ids:
        partes.append("O perfil ainda não tem posts publicados: proponha pelo nicho e pela bio.")
    instrucao = body.instrucao.strip()
    partes.append(chamada_mod.bloco("instrucao", instrucao or "Proponha os temas do perfil."))
    texto = "\n\n".join(partes)
    row = chamada_mod.executar(db, actor, "aprendizado.taxonomia", perfil,
                               entity_type="perfil", entity_id=perfil.id, instrucao=instrucao,
                               user=lambda erro: texto if not erro else
                               f"{texto}\n\nA resposta anterior foi recusada: {erro}.",
                               client=client)
    if row.erro_code is not None:
        db.commit()
        raise chamada_mod.erro_http(row)
    temas = [schemas.AprendizadoTemaIn(nome=t["nome"], descricao=t.get("descricao", ""),
                                       palavras_chave=t.get("palavrasChave", []))
             for t in chamada_mod.proposta(row).get("temas", [])]
    return schemas.AprendizadoProporOut(
        chamada_id=row.id, temas=temas,
        custo_usd=float(row.custo_usd) if row.custo_usd is not None else None)
