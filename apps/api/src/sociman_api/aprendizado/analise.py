"""Análise estatística na leitura (spec 023, US2; FR-010 a FR-028; research R1 a R4).

Para o escopo (perfil ou conta) e a janela (180 dias com peso, ou `de`/`ate`):
1. os posts da 019 (`analytics.base.posts`), medidos pela medida escolhida, sem os aguardando e
   sem as séries anônimas;
2. por conta: medidos, estagnados (regra da 019), "travada" (> 60% estagnados), a base da
   entrega p_c e a do rendimento m_c (médias ponderadas). Conta com menos de 15 medidos não
   entra nos efeitos (FR-022);
3. por fator e valor, as duas partes: **entrega** (desvio e − p_c de todos) e **rendimento**
   (desvio y − m_c só dos entregues), encolhidas, com intervalo por reamostragem, confiança,
   n de posts e de dias, e os avisos (puxado por 1, não separável, quase só com, travada, em
   alta, em queda);
4. hashtags com o mesmo conjunto de posts viram um **bloco**; o efeito da hashtag é o de dentro
   do tema (estratificado) quando há temas, e "não separável do tema X" sem nenhum tema válido;
5. a matriz bloco × tema e o contador de comparações ("exploratório").

Só leitura: nada é gravado (guarda dos GETs).
"""

import math
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.analytics import base, filtros
from sociman_api.analytics.base import PostAnalisado
from sociman_api.analytics.estatistica import mediana
from sociman_api.analytics.filtros import Medida
from sociman_api.aprendizado import constantes as K
from sociman_api.aprendizado import estatistica as est
from sociman_api.aprendizado import fatores as fat
from sociman_api.aprendizado.estatistica import Confianca, Item, Parte
from sociman_api.aprendizado.models import Classificacao, Tema

PARTES: tuple[Parte, ...] = ("entrega", "rendimento")
# FR-026: os pares em que um fator pode "andar junto" com outro.
PARES_CONFUSAO = (("tema", "faixa_horario"), ("tema", "canal_fonte"), ("hashtag", "canal_fonte"))
RECOMENDAVEIS = set(K.CONFIANCAS_RECOMENDAVEIS)


@dataclass(frozen=True)
class Aviso:
    tipo: str  # puxado_por_1 | nao_separavel | quase_so_com | travada | em_alta | em_queda
    sem_maior: float | None = None
    tema_id: str | None = None
    tema_nome: str | None = None
    fator: str | None = None
    valor: str | None = None
    rotulo: str | None = None


@dataclass
class Efeito:
    fator: str
    valor: str
    rotulo: str
    parte: Parte
    theta: float | None  # escala interna (fração na entrega, log no rendimento)
    intervalo_theta: tuple[float, float] | None
    n_posts: int
    n_dias: int
    confianca: Confianca
    faltam: int | None
    mediana_bruta: float | None
    avisos: list[Aviso] = field(default_factory=list)
    contas: frozenset = frozenset()
    sem_maior_theta: float | None = None
    posts: tuple[uuid.UUID, ...] = ()

    @property
    def efeito(self) -> float | None:
        return est.exibir(self.theta, self.parte) if self.theta is not None else None

    @property
    def intervalo(self) -> tuple[float, float] | None:
        if self.intervalo_theta is None:
            return None
        lo, hi = self.intervalo_theta
        return est.exibir(lo, self.parte), est.exibir(hi, self.parte)

    def tem(self, tipo: str) -> bool:
        return any(a.tipo == tipo for a in self.avisos)


@dataclass(frozen=True)
class ContaInfo:
    chave: uuid.UUID  # conta (ou série, se anônima: nunca no escopo de perfil)
    rotulo: str
    medidos: int
    estagnados: int
    travada: bool
    suficiente: bool


@dataclass(frozen=True)
class PostA:
    p: PostAnalisado
    conta: uuid.UUID
    peso: float
    y: float
    entregue: bool
    desvio_entrega: float
    desvio_rendimento: float | None  # só nos entregues
    fatores: tuple[fat.Fator, ...]
    blocos: tuple[str, ...]
    tema_id: uuid.UUID | None
    dia: date
    idade_dias: float


@dataclass(frozen=True)
class Bloco:
    valor: str
    hashtags: tuple[str, ...]
    posts: frozenset[uuid.UUID]
    quase_com: tuple[str, ...] = ()  # outros blocos com Jaccard ≥ 0,8


@dataclass
class Resultado:
    perfil_id: uuid.UUID
    conta_id: uuid.UUID | None
    medida: Medida
    de: date
    ate: date
    contexto: base.schemas.Contexto
    contas: list[ContaInfo]
    efeitos: list[Efeito]
    blocos: list[Bloco]
    matriz: list[tuple[str, uuid.UUID, int]]  # (bloco, tema, n)
    temas: dict[uuid.UUID, str]
    posts: list[PostA]  # os que entram nos efeitos
    medidos: list[PostAnalisado]
    estagnados: set[uuid.UUID]
    sem_tema: int
    pendentes: int

    @property
    def comparacoes(self) -> int:
        return sum(e.confianca != "amostra_pequena" and e.theta is not None for e in self.efeitos)

    @property
    def travadas(self) -> list[uuid.UUID]:
        return [c.chave for c in self.contas if c.travada]


def janela(de: date | None, ate: date | None, hoje: date) -> tuple[date, date]:
    ate = ate or hoje
    return (de or ate - timedelta(days=K.JANELA_DIAS - 1)), ate


def _semente(perfil_id: uuid.UUID, conta_id: uuid.UUID | None, *partes: object) -> int:
    return est.semente(perfil_id, conta_id or "", *partes)


def _dias(posts: Iterable[PostA]) -> int:
    return len({p.dia for p in posts})


def _itens(posts: Sequence[PostA], parte: Parte, recente: bool | None = None,
           limite: float = K.RECENTE_DIAS) -> list[Item]:
    """Os itens da parte; com `recente`, só os da janela recente (ou do resto), sem peso."""
    out = []
    for p in posts:
        if parte == "rendimento" and p.desvio_rendimento is None:
            continue
        if recente is not None and (p.idade_dias <= limite) != recente:
            continue
        d = p.desvio_entrega if parte == "entrega" else p.desvio_rendimento
        w = 1.0 if recente is not None else p.peso
        out.append(Item(d, w, views=p.p.medida.valor or 0, chave=p.p.video_id))  # type: ignore[arg-type]
    return out


def _da_parte(posts: Sequence[PostA], parte: Parte) -> list[PostA]:
    return [p for p in posts if parte == "entrega" or p.desvio_rendimento is not None]


def _tendencia(posts: Sequence[PostA], parte: Parte, sem: int) -> Aviso | None:
    """FR-014: compara os últimos 30 dias (sem peso) com o resto da janela; a marca aparece
    quando a faixa de confiança muda ou o sinal se inverte (alta se o recente é maior, queda se
    é menor)."""
    recentes = [p for p in posts if p.idade_dias <= K.RECENTE_DIAS]
    antigos = [p for p in posts if p.idade_dias > K.RECENTE_DIAS]
    faixas: list[Confianca] = []
    efeitos: list[float] = []
    for ps, s, recente in ((recentes, sem + 1, True), (antigos, sem + 2, False)):
        itens = _itens(ps, parte, recente)
        if len(itens) < K.MIN_GRUPO:
            return None
        theta = est.encolhido(itens)
        iv = est.intervalo(itens, s, K.REAMOSTRAS // 4)
        faixas.append(est.confianca(len(itens), _dias(ps), iv, theta, parte))
        efeitos.append(theta)
    if faixas[0] == faixas[1] and (efeitos[0] > 0) == (efeitos[1] > 0):
        return None
    return Aviso("em_alta" if efeitos[0] > efeitos[1] else "em_queda")


def _efeito_simples(fator: str, valor: str, rotulo: str, parte: Parte, posts: Sequence[PostA],
                    contas: Mapping[uuid.UUID, ContaInfo], sem: int) -> Efeito:
    grupo = _da_parte(posts, parte)
    itens = _itens(grupo, parte)
    n, dias = len(itens), _dias(grupo)
    med = mediana([p.p.medida.valor for p in grupo]) if grupo else None  # type: ignore[misc]
    e = Efeito(fator, valor, rotulo, parte, None, None, n, dias, "amostra_pequena",
               est.faltam(n, dias), med, contas=frozenset(p.conta for p in grupo),
               posts=tuple(p.p.video_id for p in grupo))
    if n < K.MIN_GRUPO or dias < K.MIN_DIAS:
        return e
    e.theta = est.encolhido(itens)
    e.intervalo_theta = est.intervalo(itens, sem)
    e.confianca = est.confianca(n, dias, e.intervalo_theta, e.theta, parte)
    if est.concentracao(itens):
        e.sem_maior_theta = est.encolhido(est.sem_maior(itens))
        e.avisos.append(Aviso("puxado_por_1", sem_maior=est.exibir(e.sem_maior_theta, parte)))
    _marcar_travada(e, grupo, contas)
    if (t := _tendencia(grupo, parte, sem)) is not None:
        e.avisos.append(t)
    return e


def _marcar_travada(e: Efeito, grupo: Sequence[PostA],
                    contas: Mapping[uuid.UUID, ContaInfo]) -> None:
    """R4: no rendimento, a evidência que vem sobretudo de contas travadas é só indício."""
    if e.parte != "rendimento" or not grupo:
        return
    travados = sum(contas[p.conta].travada for p in grupo)
    if travados / len(grupo) > 0.5:
        e.avisos.append(Aviso("travada"))
        if e.confianca != "amostra_pequena":
            e.confianca = "indicio"


def _separavel(bloco: Bloco, parte: Parte, posts: Sequence[PostA],
               temas: Mapping[uuid.UUID, str], contas: Mapping[uuid.UUID, ContaInfo],
               sem: int) -> Efeito:
    """FR-024: o efeito da hashtag dentro do tema (média ponderada por n das diferenças entre os
    encolhidos com e sem ela em cada tema com ≥ 3 e ≥ 3 posts)."""
    rotulo = " + ".join(f"#{h}" for h in bloco.hashtags)
    com = [p for p in posts if p.p.video_id in bloco.posts]
    simples = _efeito_simples("hashtag", bloco.valor, rotulo, parte, com, contas, sem)
    if simples.confianca == "amostra_pequena":
        return simples
    da_parte = _da_parte(posts, parte)
    estratos: list[tuple[list[Item], list[Item]]] = []
    for t in temas:
        do_tema = [p for p in da_parte if p.tema_id == t]
        a = _itens([p for p in do_tema if p.p.video_id in bloco.posts], parte)
        b = _itens([p for p in do_tema if p.p.video_id not in bloco.posts], parte)
        if len(a) >= K.MIN_SEPARAVEL and len(b) >= K.MIN_SEPARAVEL:
            estratos.append((a, b))
    if not estratos:
        contagem = Counter(p.tema_id for p in _da_parte(com, parte) if p.tema_id is not None)
        if not contagem:  # sem nenhum tema nos posts: não há como separar; fica o simples
            return simples
        tema = contagem.most_common(1)[0][0]
        simples.theta = simples.intervalo_theta = None
        simples.confianca = "indicio"
        simples.sem_maior_theta = None
        simples.avisos = [Aviso("nao_separavel", tema_id=str(tema), tema_nome=temas[tema])]
        return simples

    def dentro(*grupos: list[Item]) -> float:
        total = num = 0.0
        for i in range(0, len(grupos), 2):
            a, b = grupos[i], grupos[i + 1]
            peso = len(a) + len(b)
            num += peso * (est.encolhido(a) - est.encolhido(b))
            total += peso
        return num / total if total else 0.0

    planos = [g for par in estratos for g in par]
    simples.theta = dentro(*planos)
    simples.intervalo_theta = est.reamostrar(planos, dentro, sem)
    simples.confianca = est.confianca(simples.n_posts, simples.n_dias, simples.intervalo_theta,
                                      simples.theta, parte)
    _marcar_travada(simples, _da_parte(com, parte), contas)
    return simples


def _blocos(posts: Sequence[PostA]) -> list[Bloco]:
    """Hashtags com o mesmo conjunto exato de posts viram um bloco (R3), na ordem de 1ª
    aparição; pares de blocos com Jaccard ≥ 0,8 ficam como "quase sempre juntas"."""
    conjuntos: dict[str, set[uuid.UUID]] = {}
    for p in posts:
        for h in p.p.hashtags:
            conjuntos.setdefault(h, set()).add(p.p.video_id)
    por_conjunto: dict[frozenset[uuid.UUID], list[str]] = {}
    for h, ids in conjuntos.items():
        por_conjunto.setdefault(frozenset(ids), []).append(h)
    blocos = [Bloco("+".join(tags), tuple(tags), ids) for ids, tags in por_conjunto.items()]
    out = []
    for b in blocos:
        quase = tuple(o.valor for o in blocos if o is not b
                      and est.jaccard(set(b.posts), set(o.posts)) >= K.JACCARD_QUASE)
        out.append(Bloco(b.valor, b.hashtags, b.posts, quase))
    return out


def _confusao(efeitos: list[Efeito], posts: Sequence[PostA]) -> None:
    """FR-026: "quase só com X = valor" quando ≥ 80% do grupo tem o mesmo valor de outro fator
    e esse valor tem efeito próprio de confiança ≥ moderada (na mesma parte)."""
    por_id = {p.p.video_id: p for p in posts}
    indice = {(e.fator, e.valor, e.parte): e for e in efeitos}

    def valores(p: PostA, fator: str) -> list[str]:
        if fator == "hashtag":
            return list(p.blocos)
        return [f.valor for f in p.fatores if f.fator == fator]

    for a, b in PARES_CONFUSAO:
        for origem, destino in ((a, b), (b, a)):
            for e in efeitos:
                if e.fator != origem or e.theta is None or not e.posts:
                    continue
                contagem = Counter(v for vid in e.posts for v in valores(por_id[vid], destino))
                if not contagem:
                    continue
                valor, n = contagem.most_common(1)[0]
                outro = indice.get((destino, valor, e.parte))
                if (n / len(e.posts) >= K.CONFUSAO and outro is not None
                        and outro.confianca in RECOMENDAVEIS
                        and not (outro.fator == e.fator and outro.valor == e.valor)):
                    e.avisos.append(Aviso("quase_so_com", fator=destino, valor=valor,
                                          rotulo=outro.rotulo))


def montar_posts(medidos: Sequence[PostAnalisado], estag: set[uuid.UUID],
                 classes: Mapping[uuid.UUID, fat.ClassInfo], temas: Mapping[uuid.UUID, str],
                 agora: datetime) -> tuple[list[PostA], list[ContaInfo]]:
    """Base de cada conta e os posts que entram nos efeitos (das contas com amostra)."""
    tz = ZoneInfo(filtros.fuso())
    por_conta: dict[uuid.UUID, list[PostAnalisado]] = {}
    for p in medidos:
        por_conta.setdefault(p.conta_id or p.serie_id, []).append(p)
    contas: list[ContaInfo] = []
    out: list[PostA] = []
    for chave, ps in por_conta.items():
        n_est = sum(p.video_id in estag for p in ps)
        info = ContaInfo(chave, ps[0].rotulo_conta, len(ps), n_est,
                         travada=bool(ps) and n_est / len(ps) > K.TRAVADA,
                         suficiente=len(ps) >= K.MIN_CONTA)
        contas.append(info)
        if not info.suficiente:
            continue
        idades = {p.video_id: max(0.0, (agora - p.publicado_em).total_seconds() / 86400)
                  for p in ps}
        pesos = {vid: est.peso(i) for vid, i in idades.items()}
        ys = {p.video_id: est.medida_log(p.medida.valor) for p in ps}
        entregue = {p.video_id: p.video_id not in estag for p in ps}
        p_c = est.media_ponderada([(1.0 if entregue[p.video_id] else 0.0, pesos[p.video_id])
                                   for p in ps]) or 0.0
        m_c = est.media_ponderada([(ys[p.video_id], pesos[p.video_id]) for p in ps
                                   if entregue[p.video_id]])
        for p in ps:
            vid = p.video_id
            c = classes.get(vid)
            out.append(PostA(
                p=p, conta=chave, peso=pesos[vid], y=ys[vid], entregue=entregue[vid],
                desvio_entrega=(1.0 if entregue[vid] else 0.0) - p_c,
                desvio_rendimento=ys[vid] - m_c if entregue[vid] and m_c is not None else None,
                fatores=tuple(fat.de_post(p, c, temas)), blocos=(),
                tema_id=c.tema_id if c is not None and c.tema_id in temas else None,
                dia=p.publicado_em.astimezone(tz).date(), idade_dias=idades[vid]))
    return out, contas


def classes_de(db: Session, ids: Sequence[uuid.UUID]
               ) -> tuple[dict[uuid.UUID, fat.ClassInfo], set[uuid.UUID]]:
    """(classificações por vídeo, vídeos a reclassificar)."""
    if not ids:
        return {}, set()
    rows = db.execute(select(Classificacao.video_id, Classificacao.tema_id,
                             Classificacao.estilo_gancho, Classificacao.reclassificar)
                      .where(Classificacao.video_id.in_(list(ids)))).all()
    classes = {r.video_id: fat.ClassInfo(r.tema_id, r.estilo_gancho.value
                                         if r.estilo_gancho is not None else None) for r in rows}
    return classes, {r.video_id for r in rows if r.reclassificar}


def temas_ativos(db: Session, perfil_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict(db.execute(select(Tema.id, Tema.nome).where(
        Tema.perfil_id == perfil_id, Tema.archived_at.is_(None)).order_by(Tema.nome)).all())


def _ordem(e: Efeito) -> tuple:
    return (fat.FATORES.index(e.fator), PARTES.index(e.parte), e.theta is None,
            -(e.theta or 0), e.rotulo)


def calcular(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None = None,
             medida: Medida = filtros.MEDIDA_PADRAO, de: date | None = None,
             ate: date | None = None, agora: datetime | None = None,
             so: frozenset[str] | None = None) -> Resultado:
    """`so`: calcula só os efeitos destes fatores (a afinidade usa tema e canal; os exemplos
    do `<desempenho>`, nenhum). Sem `so`, todos."""
    agora = agora or datetime.now(ZoneInfo("UTC"))
    hoje = agora.astimezone(ZoneInfo(filtros.fuso())).date()
    de, ate = janela(de, ate, hoje)
    filtro = filtros.montar(db, de=de, ate=ate, perfil_id=perfil_id, conta_id=conta_id,
                            medida=medida, dia_atual=hoje)
    todos = base.posts(db, filtro, agora=agora)
    medidos = [p for p in todos if p.medido and not p.anonima]
    estag = fat.estagnados(db, medidos, agora)
    temas = temas_ativos(db, perfil_id)
    classes, reclass = classes_de(db, [p.video_id for p in medidos])
    return computar(perfil_id, conta_id, medida, de, ate, base.contexto(filtro, todos), medidos,
                    estag, temas, classes, reclass, agora, so)


def computar(perfil_id: uuid.UUID, conta_id: uuid.UUID | None, medida: Medida, de: date,
             ate: date, contexto: base.schemas.Contexto | None,
             medidos: Sequence[PostAnalisado], estag: set[uuid.UUID],
             temas: dict[uuid.UUID, str], classes: Mapping[uuid.UUID, fat.ClassInfo],
             reclass: set[uuid.UUID], agora: datetime,
             so: frozenset[str] | None = None) -> Resultado:
    """A parte pura do cálculo (sem banco): os testes de referência (SC-003) chamam direto."""
    medidos = list(medidos)
    posts, contas = montar_posts(medidos, estag, classes, temas, agora)
    blocos = _blocos(posts)
    por_hashtag = {h: b.valor for b in blocos for h in b.hashtags}
    posts = [replace(p, blocos=tuple(dict.fromkeys(por_hashtag[h] for h in p.p.hashtags
                                                   if h in por_hashtag))) for p in posts]
    info = {c.chave: c for c in contas}

    grupos: dict[tuple[str, str], tuple[str, list[PostA]]] = {}
    for p in posts:
        for f in p.fatores:
            grupos.setdefault((f.fator, f.valor), (f.rotulo, []))[1].append(p)
    efeitos: list[Efeito] = []
    for (fator, valor), (rotulo, ps) in grupos.items():
        if so is not None and fator not in so:
            continue
        for parte in PARTES:
            efeitos.append(_efeito_simples(fator, valor, rotulo, parte, ps, info,
                                           _semente(perfil_id, conta_id, fator, valor, parte)))
    for b in blocos if so is None or "hashtag" in so else ():
        for parte in PARTES:
            efeitos.append(_separavel(b, parte, posts, temas, info,
                                      _semente(perfil_id, conta_id, "hashtag", b.valor, parte)))
    _confusao(efeitos, posts)
    efeitos.sort(key=_ordem)

    matriz = sorted(Counter((b.valor, p.tema_id) for p in posts if p.tema_id is not None
                            for b in blocos if p.p.video_id in b.posts).items(),
                    key=lambda kv: (-kv[1], kv[0][0]))
    sem_tema = sum(1 for p in medidos if p.video_id in classes
                   and classes[p.video_id].tema_id is None)
    pendentes = sum(1 for p in medidos if p.video_id not in classes or p.video_id in reclass)
    return Resultado(
        perfil_id=perfil_id, conta_id=conta_id, medida=medida, de=de, ate=ate,
        contexto=contexto, contas=contas, efeitos=efeitos, blocos=blocos,  # type: ignore[arg-type]
        matriz=[(bv, t, n) for (bv, t), n in matriz], temas=temas, posts=posts,
        medidos=medidos, estagnados=estag, sem_tema=sem_tema, pendentes=pendentes)


def efeito_de(res: Resultado, fator: str, valor: str, parte: Parte) -> Efeito | None:
    return next((e for e in res.efeitos
                 if e.fator == fator and e.valor == valor and e.parte == parte), None)


def residuos(res: Resultado) -> dict[uuid.UUID, float]:
    """O resíduo de rendimento de cada post entregue (para os melhores, R5 e R8)."""
    return {p.p.video_id: p.desvio_rendimento for p in res.posts
            if p.desvio_rendimento is not None and not math.isnan(p.desvio_rendimento)}
