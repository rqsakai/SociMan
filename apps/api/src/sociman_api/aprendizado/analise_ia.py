"""Análise da IA dos melhores posts (spec 023, US2; FR-030 a FR-033; research R5).

- **Escolha:** os N melhores (padrão 8, até 15) pelo resíduo de rendimento do post, e N
  comparáveis (os piores entregues das mesmas contas, no mesmo período). Séries anônimas nunca
  entram (R11);
- **Estimativa:** com e sem quadros, pela tabela de preços da 008 (texto ≈ caracteres/4; imagem
  ≈ 512 × altura / 750 por quadro; saída no máximo);
- **Pedido:** só com `confirmoCusto` (409 `confirmar_custo` com as estimativas), um por perfil
  (409 `analise_em_andamento`); grava `pendente`;
- **Execução** (a trilha `aprendizado`): `processando` → quadros (se pedidos) → chamada pelo
  registro da 008 → hipóteses validadas (post fora do conjunto enviado = hipótese recusada) →
  `pronta` ou `erro`. Registro imutável depois disso (exceção do princípio VII);
- **Hipótese → recomendação:** uma decisão `aberta` de padrão (gancho, duração ou horário).

O custo só vai para o dono; o membro recebe `null`.
"""

import base64
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.analytics import base, filtros
from sociman_api.aprendizado import analise as an
from sociman_api.aprendizado import chamada as chamada_mod
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import fatores as fat
from sociman_api.aprendizado import preferencias as prefs
from sociman_api.aprendizado import quadros, recomendacoes, schemas
from sociman_api.aprendizado.models import Analise, AnaliseEstado, Decisao, DecisaoEstado
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.cortes.models import Corte
from sociman_api.errors import ApiError
from sociman_api.ia import custo
from sociman_api.ia import service as ia_service
from sociman_api.ia.cliente import MAX_TOKENS, IaClient
from sociman_api.ia.models import IaChamada
from sociman_api.ia.tipos import TIPOS
from sociman_api.metricas.models import VideoRede
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.perfis.service_perfis import get_perfil_or_404, user_refs

ENTITY = "aprendizado_analise"
TIPO = "aprendizado.analise"
TRANSCRICAO_ANALISE = 1500
ALTURA_PADRAO = 910  # 9:16 com 512 px de largura


@dataclass(frozen=True)
class Escolha:
    res: an.Resultado
    melhores: list[an.PostA]
    comparaveis: list[an.PostA]


def _conta(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None) -> None:
    if conta_id is None:
        return
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    if conta.perfil_id != perfil_id:
        raise ApiError(400, "conta_fora_do_perfil", "A conta não é do perfil escolhido")


def escolher(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None, n: int,
             medida: str, agora: datetime | None = None) -> Escolha:
    res = an.calcular(db, perfil_id, conta_id, medida, agora=agora)  # type: ignore[arg-type]
    entregues = sorted((p for p in res.posts if p.desvio_rendimento is not None),
                       key=lambda p: (-(p.desvio_rendimento or 0), -p.p.publicado_em.timestamp()))
    if not entregues:
        raise ApiError(409, "sem_posts", "Ainda não há posts entregues com medida neste escopo")
    melhores = entregues[:n]
    contas = {p.conta for p in melhores}
    resto = [p for p in entregues[n:] if p.conta in contas]
    comparaveis = list(reversed(resto[-n:])) if resto else []
    return Escolha(res, melhores, comparaveis)


def _resumo_estatistico(res: an.Resultado) -> list[dict[str, Any]]:
    return [{"fator": e.fator, "valor": e.valor, "rotulo": e.rotulo, "parte": e.parte,
             "efeito": e.efeito, "nPosts": e.n_posts, "confianca": e.confianca,
             "avisos": [a.tipo for a in e.avisos]}
            for e in res.efeitos
            if e.theta is not None and e.confianca in ("forte", "moderada", "fraca")]


def _texto_resumo(resumo: Sequence[dict[str, Any]]) -> str:
    if not resumo:
        return "(nenhum efeito com confiança ao menos fraca)"
    linhas = []
    for e in resumo:
        unidade = "p.p." if e["parte"] == "entrega" else "×"
        avisos = f"; avisos: {', '.join(e['avisos'])}" if e["avisos"] else ""
        linhas.append(f"- {fat.ROTULO_FATOR.get(e['fator'], e['fator'])} {e['rotulo']} "
                      f"({e['parte']}): {e['efeito']} {unidade} (n = {e['nPosts']}, "
                      f"{e['confianca']}{avisos})")
    return "\n".join(linhas)


def _post_texto(db: Session, p: an.PostA, grupo: str, temas: dict[uuid.UUID, str],
                classes: dict[uuid.UUID, Any]) -> list[str]:
    video = db.get(VideoRede, p.p.video_id)
    c = classes.get(p.p.video_id)
    linhas = [f"Grupo: {grupo}", f"Conta: {p.p.rotulo_conta}",
              f"Publicado: {fat.DIAS[p.p.dia_semana]} às {p.p.hora_local:02d}h",
              f"Duração: {p.p.duracao_s} s", f"Views no marco: {p.p.medida.valor:.0f}"]
    if p.tema_id is not None:
        linhas.append(f"Tema: {temas[p.tema_id]}")
    if c is not None and c.estilo_gancho:
        linhas.append(f"Estilo do gancho: {fat.ROTULO_ESTILO.get(c.estilo_gancho)}")
    legenda = ((video.legenda or video.titulo) if video else "") or ""
    linhas.append(f"Legenda: {legenda.strip()[:K.LEGENDA_ANALISE_MAX] or '(vazia)'}")
    if p.p.hashtags:
        linhas.append("Hashtags: " + " ".join(f"#{h}" for h in p.p.hashtags))
    partes = [chamada_mod.bloco("post", "\n".join(linhas), id=str(p.p.video_id))]
    corte = db.get(Corte, p.p.conteudo_id) if p.p.conteudo_id else None
    if corte is not None:
        if corte.hook_text:
            partes.append(chamada_mod.bloco("dados_terceiros", corte.hook_text, tipo="gancho",
                                            post=str(p.p.video_id)))
        if (corte.transcript or "").strip():
            partes.append(chamada_mod.bloco("dados_terceiros",
                                            corte.transcript.strip()[:TRANSCRICAO_ANALISE],
                                            tipo="transcricao", post=str(p.p.video_id)))
    return partes


def montar_texto(db: Session, perfil_id: uuid.UUID, melhores: Sequence[an.PostA],
                 comparaveis: Sequence[an.PostA], resumo: Sequence[dict[str, Any]]) -> str:
    temas = an.temas_ativos(db, perfil_id)
    classes, _ = an.classes_de(db, [p.p.video_id for p in [*melhores, *comparaveis]])
    partes = [chamada_mod.bloco("resumo_estatistico", _texto_resumo(resumo))]
    for p in melhores:
        partes.extend(_post_texto(db, p, "melhor", temas, classes))
    for p in comparaveis:
        partes.extend(_post_texto(db, p, "comparável", temas, classes))
    partes.append(chamada_mod.bloco(
        "instrucao", "Compare os posts do grupo \"melhor\" com os do grupo \"comparável\" e "
        "proponha hipóteses do que fez diferença."))
    return "\n\n".join(partes)


def _altura(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    rows = db.execute(select(VideoRede.id, VideoRede.largura, VideoRede.altura)
                      .where(VideoRede.id.in_(list(ids)))).all() if ids else []
    return {vid: round(K.QUADRO_LARGURA * a / w) if w and a else ALTURA_PADRAO
            for vid, w, a in rows}


def _custo(entrada: int, model: str) -> Decimal:
    p = custo.preco(model)
    return ((entrada * p.entrada + MAX_TOKENS * p.saida) / Decimal(1_000_000)).quantize(
        Decimal("0.000001"))


def estimar_escolha(db: Session, e: Escolha) -> tuple[Decimal, Decimal, int, str]:
    """(sem quadros, com quadros, vídeos sem arquivo, texto) em US$ (aproximado)."""
    model = get_settings().textos_model
    resumo = _resumo_estatistico(e.res)
    texto = montar_texto(db, e.res.perfil_id, e.melhores, e.comparaveis, resumo)
    perfil = get_perfil_or_404(db, e.res.perfil_id)
    regras = ia_service.regras_em_vigor(db, TIPOS[TIPO])
    system = chamada_mod.montar_system(db, TIPOS[TIPO], perfil, regras.texto)
    tokens_texto = math.ceil((len(texto) + sum(len(b["text"]) for b in system)) / 4)
    ids = [p.p.video_id for p in [*e.melhores, *e.comparaveis]]
    com_arquivo = quadros.chaves(db, ids)
    alturas = _altura(db, list(com_arquivo))
    tokens_img = sum(math.ceil(K.QUADRO_LARGURA * alturas.get(v, ALTURA_PADRAO) / 750)
                     * K.QUADROS_POR_VIDEO for v in com_arquivo)
    return (_custo(tokens_texto, model), _custo(tokens_texto + tokens_img, model),
            len(ids) - len(com_arquivo), texto)


def _resumos(db: Session, perfil_id: uuid.UUID, ps: Sequence[an.PostA]) -> list:
    return [base.resumo(p.p) for p in ps]


def estimativa(db: Session, perfil_id: uuid.UUID,
               body: schemas.AprendizadoEstimativaIn) -> schemas.AprendizadoEstimativa:
    get_perfil_or_404(db, perfil_id)
    _conta(db, perfil_id, body.conta_id)
    e = escolher(db, perfil_id, body.conta_id, body.n, body.medida)
    sem, com, sem_arquivo, _ = estimar_escolha(db, e)
    return schemas.AprendizadoEstimativa(
        melhores=_resumos(db, perfil_id, e.melhores),
        comparaveis=_resumos(db, perfil_id, e.comparaveis), sem_arquivo=sem_arquivo,
        custo_sem_quadros_usd=float(sem), custo_com_quadros_usd=float(com))


def _em_andamento(db: Session, perfil_id: uuid.UUID) -> bool:
    return db.scalar(select(Analise.id).where(
        Analise.perfil_id == perfil_id,
        Analise.estado.in_((AnaliseEstado.pendente, AnaliseEstado.processando))).limit(1)
        ) is not None


def pedir(db: Session, actor: Actor, perfil_id: uuid.UUID, body: schemas.AprendizadoAnaliseIaIn,
          client: IaClient | None) -> schemas.AprendizadoAnaliseIa:
    """`client` só diz se o Claude está configurado: quem chama é a trilha."""
    perfil = get_perfil_or_404(db, perfil_id, lock=True)  # serializa os pedidos do perfil
    if perfil.archived:
        raise ApiError(409, "conflict", "Este perfil está arquivado")
    _conta(db, perfil_id, body.conta_id)
    if client is None:
        raise ApiError(503, "claude_unconfigured",
                       "O Claude não está configurado (ANTHROPIC_API_KEY)")
    if _em_andamento(db, perfil_id):
        raise ApiError(409, "analise_em_andamento",
                       "Já há uma análise deste perfil na fila; espere ela terminar")
    e = escolher(db, perfil_id, body.conta_id, body.n, body.medida)
    sem, com, sem_arquivo, _ = estimar_escolha(db, e)
    if not body.confirmo_custo:
        raise ApiError(409, "confirmar_custo", "Confirme o custo estimado antes de pedir",
                       details={"custoSemQuadrosUsd": float(sem),
                                "custoComQuadrosUsd": float(com), "semArquivo": sem_arquivo})
    a = Analise(perfil_id=perfil_id, conta_id=body.conta_id, estado=AnaliseEstado.pendente,
                medida=body.medida, n=body.n, com_quadros=body.com_quadros,
                quadros_por_video=K.QUADROS_POR_VIDEO if body.com_quadros else 0,
                melhores=[p.p.video_id for p in e.melhores],
                comparaveis=[p.p.video_id for p in e.comparaveis],
                resumo_estatistico=_resumo_estatistico(e.res),
                custo_estimado_usd=com if body.com_quadros else sem,
                taxonomia_versao=prefs.taxonomia_versao(db, perfil_id), pedido_por=actor.user_id)
    db.add(a)
    db.flush()
    history.record(db, actor, ENTITY, a, "created", None, history.snapshot(a))
    db.flush()
    return out(db, a, com_custo=True)


# ---- leitura ----

def out(db: Session, a: Analise, com_custo: bool) -> schemas.AprendizadoAnaliseIa:
    custo_usd = None
    if com_custo and a.chamada_id is not None:
        valor = db.scalar(select(IaChamada.custo_usd).where(IaChamada.id == a.chamada_id))
        custo_usd = float(valor) if valor is not None else None
    users = user_refs(db, [a.pedido_por])
    ids = [*a.melhores, *a.comparaveis]
    filtro = filtros.montar(db, perfil_id=a.perfil_id, medida=a.medida)  # type: ignore[arg-type]
    posts = [base.resumo(p) for p in base.posts_por_id(db, filtro, ids) if not p.anonima]
    return schemas.AprendizadoAnaliseIa(
        id=a.id, estado=a.estado.value, conta_id=a.conta_id, n=a.n,  # type: ignore[arg-type]
        medida=a.medida, com_quadros=a.com_quadros,  # type: ignore[arg-type]
        videos_sem_arquivo=a.videos_sem_arquivo, melhores=list(a.melhores),
        comparaveis=list(a.comparaveis), posts=posts,
        hipoteses=[schemas.AprendizadoHipotese(**h) for h in a.hipoteses or []],
        custo_estimado_usd=float(a.custo_estimado_usd) if com_custo else None,
        custo_usd=custo_usd, chamada_id=a.chamada_id, erro_code=a.erro_code,
        taxonomia_versao=a.taxonomia_versao, pedido_por=users.get(a.pedido_por),
        created_at=a.created_at, concluida_em=a.concluida_em)


def listar(db: Session, perfil_id: uuid.UUID, com_custo: bool, cursor: str | None = None,
           limit: int = 20) -> schemas.AprendizadoAnalisesList:
    get_perfil_or_404(db, perfil_id)
    stmt = select(Analise).where(Analise.perfil_id == perfil_id)
    if cursor:
        try:
            antes = datetime.fromisoformat(base64.urlsafe_b64decode(cursor).decode())
        except ValueError as exc:
            raise ApiError(400, "validation_error", "Cursor inválido") from exc
        stmt = stmt.where(Analise.created_at < antes)
    rows = list(db.scalars(stmt.order_by(Analise.created_at.desc(), Analise.id)
                           .limit(limit + 1)))
    proximo = base64.urlsafe_b64encode(rows[limit - 1].created_at.isoformat().encode()).decode() \
        if len(rows) > limit else None
    return schemas.AprendizadoAnalisesList(items=[out(db, a, com_custo) for a in rows[:limit]],
                                           next_cursor=proximo)


def obter(db: Session, analise_id: uuid.UUID, com_custo: bool) -> schemas.AprendizadoAnaliseIa:
    a = db.get(Analise, analise_id)
    if a is None:
        raise ApiError(404, "not_found", "Análise não encontrada")
    return out(db, a, com_custo)


# ---- execução (trilha) ----

def recuperar_presas(db: Session, agora: datetime) -> None:
    """Uma `processando` há mais de 15 min volta a `pendente` uma vez; na 2ª, vira `erro`."""
    presas = db.scalars(select(Analise).where(
        Analise.estado == AnaliseEstado.processando,
        Analise.iniciada_em < agora - K.PROCESSANDO_MAX).with_for_update(skip_locked=True))
    for a in presas:
        before = history.snapshot(a)
        tentou = any(v.details.get("recuperada") for v in history.list_versions(db, ENTITY, a.id))
        if tentou:
            a.estado, a.erro_code, a.concluida_em = AnaliseEstado.erro, "interrompida", agora
        else:
            a.estado = AnaliseEstado.pendente
        history.record(db, chamada_mod.SISTEMA, ENTITY, a, "updated", before,
                       history.snapshot(a), {"recuperada": True})
    db.commit()


def _pegar(db: Session) -> Analise | None:
    return db.scalar(select(Analise).where(Analise.estado == AnaliseEstado.pendente)
                     .order_by(Analise.created_at, Analise.id).limit(1)
                     .with_for_update(skip_locked=True))


def _usuario(texto: str, imagens: dict[uuid.UUID, list[bytes]]):
    if not imagens:
        return texto
    blocos: list[dict[str, Any]] = [{"type": "text", "text": texto}]
    for vid, qs in imagens.items():
        blocos.append({"type": "text", "text": f"Quadros do post {vid} (abertura, 2 s, meio e "
                                               "fim):"})
        blocos.extend({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                   "data": base64.b64encode(q).decode()}}
                      for q in qs)
    return blocos


def validar_hipoteses(brutas: Sequence[dict[str, Any]], permitidos: set[str]
                      ) -> tuple[list[dict[str, Any]], int]:
    """(hipóteses válidas, recusadas): nenhum id fora do conjunto enviado (FR-032)."""
    ok: list[dict[str, Any]] = []
    recusadas = 0
    for h in brutas:
        ids = list(dict.fromkeys(h.get("postsIds") or []))
        if not ids or any(i not in permitidos for i in ids):
            recusadas += 1
            continue
        ok.append({"texto": h["texto"], "postsIds": ids, "contraste": h.get("contraste") or "",
                   "n": min(max(int(h.get("n") or len(ids)), 1), len(ids)),
                   "grau": "a_conferir"})
    return ok, recusadas


def _concluir(db: Session, a: Analise, before: dict[str, Any], agora: datetime,
              erro: str | None = None) -> None:
    a.concluida_em = agora
    if erro is not None:
        a.estado, a.erro_code = AnaliseEstado.erro, erro
    else:
        a.estado = AnaliseEstado.pronta
    history.record(db, chamada_mod.SISTEMA, ENTITY, a, "updated", before, history.snapshot(a))
    db.commit()


def processar_uma(db: Session, client: IaClient | None, agora: datetime) -> bool:
    """Pega 1 pedido (`SKIP LOCKED`) e o executa até `pronta` ou `erro`. True se havia um."""
    a = _pegar(db)
    if a is None:
        return False
    before = history.snapshot(a)
    a.estado, a.iniciada_em = AnaliseEstado.processando, agora
    history.record(db, chamada_mod.SISTEMA, ENTITY, a, "updated", before, history.snapshot(a))
    db.commit()
    before = history.snapshot(a)
    perfil = db.get(Perfil, a.perfil_id)
    assert perfil is not None
    filtro_posts = an.calcular(db, a.perfil_id, a.conta_id, a.medida, agora=agora)  # type: ignore[arg-type]
    por_id = {p.p.video_id: p for p in filtro_posts.posts}
    melhores = [por_id[v] for v in a.melhores if v in por_id]
    comparaveis = [por_id[v] for v in a.comparaveis if v in por_id]
    if not melhores:
        _concluir(db, a, before, agora, "sem_posts")
        return True
    texto = montar_texto(db, a.perfil_id, melhores, comparaveis, a.resumo_estatistico)
    imagens: dict[uuid.UUID, list[bytes]] = {}
    ids = [p.p.video_id for p in [*melhores, *comparaveis]]
    if a.com_quadros:
        chaves = quadros.chaves(db, ids)
        duracoes = {p.p.video_id: p.p.duracao_s for p in [*melhores, *comparaveis]}
        try:
            imagens = quadros.extrair(a.id, [(v, k, float(duracoes[v])) for v, k in
                                             chaves.items()])
        except quadros.HdIndisponivel:
            _concluir(db, a, before, agora, "hd_indisponivel")
            return True
        a.videos_sem_arquivo = len(ids) - len(imagens)
    else:
        a.videos_sem_arquivo = len(ids) - len(quadros.chaves(db, ids))
    row = chamada_mod.executar(
        db, chamada_mod.SISTEMA, TIPO, perfil, entity_type=ENTITY, entity_id=a.id,
        user=lambda erro: _usuario(texto if not erro else
                                   f"{texto}\n\nA resposta anterior foi recusada: {erro}.",
                                   imagens),
        client=client, conta_id=a.conta_id)
    a.chamada_id = row.id
    if row.erro_code is not None:
        _concluir(db, a, before, agora, f"ia_{row.erro_code}")
        return True
    validas, recusadas = validar_hipoteses(chamada_mod.proposta(row).get("hipoteses") or [],
                                           {str(i) for i in ids})
    if not validas:
        _concluir(db, a, before, agora, "ia_invalida")
        return True
    a.hipoteses = validas
    if recusadas:
        aviso = (f"{recusadas} hipótese(s) citava(m) post fora do conjunto enviado e "
                 "foi(ram) recusada(s).")
        row.avisos = [*row.avisos, aviso]
    _concluir(db, a, before, agora)
    return True


# ---- hipótese → recomendação ----

def recomendar(db: Session, actor: Actor, analise_id: uuid.UUID, indice: int,
               body: schemas.AprendizadoHipoteseRecomendarIn) -> schemas.AprendizadoDecisao:
    a = db.get(Analise, analise_id, with_for_update=True)
    if a is None:
        raise ApiError(404, "not_found", "Análise não encontrada")
    if a.estado != AnaliseEstado.pronta or not a.hipoteses or not 0 <= indice < len(a.hipoteses):
        raise ApiError(404, "not_found", "Hipótese não encontrada")
    h = a.hipoteses[indice]
    chave = (f"{body.tipo}:{recomendacoes.escopo_chave(a.conta_id)}:hipotese:{a.id}:{indice}")
    existe = db.scalar(select(Decisao.id).where(Decisao.perfil_id == a.perfil_id,
                                                Decisao.chave == chave))
    if existe is not None:
        raise ApiError(409, "conflict", "Esta hipótese já virou recomendação")
    d = Decisao(perfil_id=a.perfil_id, conta_id=a.conta_id, chave=chave, tipo=body.tipo,
                origem="hipotese", analise_id=a.id, estado=DecisaoEstado.aberta,
                evidencia={"alvo": {"padrao": body.texto}, "hipotese": h,
                           "motivo": f"Hipótese da análise da IA: {h['texto']}"},
                n_decisao=int(h.get("n") or 0), faixa_decisao="a_conferir", texto=body.texto,
                created_by=actor.user_id, updated_by=actor.user_id)
    db.add(d)
    db.flush()
    history.record(db, actor, prefs.ENTITY_DECISAO, d, "created", None, history.snapshot(d),
                   {"analiseId": str(a.id), "indice": indice})
    db.flush()
    return prefs.decisao_out(db, d)

