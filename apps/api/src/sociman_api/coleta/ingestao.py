"""Ingestão (FR-024, FR-027..FR-032): a única porta por onde o dado de mercado entra.

Por item, numa **transação própria** (SAVEPOINT; um inválido não derruba o lote, FR-028):
1. a tarefa existe, está `reservada` por este cliente e não venceu;
2. `data_local` e `turno` são do **servidor**, pelo `coletadoEm` no fuso do mercado (FR-027);
3. o adaptador da fonte valida e normaliza (`esquemaVersao` desconhecido → `invalido`);
4. o bruto é podado e recusado se ainda tiver dado pessoal (`bruto_pessoal`, FR-029);
5. `INSERT … ON CONFLICT DO NOTHING` em fotos, rankings, avaliações e vídeos → `gravado` ou
   `repetido` (FR-027); ficha nova só se o `hash_conteudo` mudou (FR-004);
6. o bruto gzip vai para o bucket `mercado` (HD); sem HD, a foto numérica fica e o item sai
   `brutoPendente` (FR-030);
7. `mercado_coleta_itens` ganha a linha (sempre), a tarefa fecha e o estado técnico do produto e
   os contadores da rodada são atualizados.

Nada aqui apaga nada, nada aqui fala com a rede. A autoria do dado é a rodada (`coleta_id`).
"""

import base64
import gzip
import hashlib
import io
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import urllib3
from minio.error import S3Error
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sociman_api import datadir, history, imaging, midia, storage
from sociman_api.auth.deps import Actor
from sociman_api.coleta import comum, privacidade, schemas
from sociman_api.coleta.models import (
    EVENTOS_QUE_NOTIFICAM,
    ColetaCliente,
    ColetaConfig,
    Evento,
    EventoTipo,
)
from sociman_api.config import get_settings
from sociman_api.errors import ApiError
from sociman_api.mercado import interesses, mercados
from sociman_api.mercado.constantes import (
    BRUTO_BYTES_MAX,
    CAPTCHA_ESFRIAR_MIN,
    CAPTCHA_ESPERA_MAX_H,
    FILA_TENTATIVAS_MAX,
    IMAGEM_BYTES_MAX,
    IMAGENS_POR_CHAMADA_MAX,
    LOTE_BYTES_MAX,
    RECUO_BLOQUEIO_H,
)
from sociman_api.mercado.fontes import registro
from sociman_api.mercado.fontes.base import CampoInvalido
from sociman_api.mercado.fontes.tiktok_shop import (
    AvaliacoesIn,
    CategoriaRef,
    CategoriasIn,
    Faixa,
    LojaIn,
    LojaRef,
    ProdutoIn,
    ProdutoVideosIn,
    RankingIn,
    VitrineIn,
)
from sociman_api.mercado.models import (
    COLETA_ABERTAS,
    COLETA_PAUSADAS,
    Avaliacao,
    Calor,
    Categoria,
    Coleta,
    ColetaEstado,
    ColetaItem,
    Ficha,
    FilaEstado,
    Fonte,
    FotoLoja,
    FotoProduto,
    FotoRanking,
    Imagem,
    InteresseOrigem,
    ItemRanking,
    ItemStatus,
    Loja,
    Produto,
    ProdutoImagem,
    RankingTipo,
    Tarefa,
    VideoProduto,
)
from sociman_api.notificacoes import service as notificacoes
from sociman_api.notificacoes.models import NotificacaoTipo
from sociman_api.perfis.models import Platform

log = logging.getLogger("sociman.coleta.ingestao")

COLETOR = Actor(kind="coletor")
NAO_ENCONTRADA = "Rodada não encontrada"
FECHADA = "Esta rodada já foi encerrada"
EM_ANDAMENTO = "Já existe uma rodada aberta para este token"
_NOTIFICACAO = {
    EventoTipo.captcha: (
        NotificacaoTipo.coleta_captcha, "Coleta pausada: verificação na rede",
        "A rede pediu uma verificação. Resolva na janela do Chrome e clique em Continuar."),
    EventoTipo.login_perdido: (
        NotificacaoTipo.coleta_login, "Coleta pausada: sessão caiu",
        ("A conta de afiliado foi deslogada. Entre de novo na janela do Chrome e clique em "
        "Continuar.")),
    EventoTipo.bloqueio_suspeito: (
        NotificacaoTipo.coleta_bloqueio, "Coleta recuou 24 h: bloqueio suspeito",
        "A rede recusou pedidos em série. A coleta volta sozinha em 24 h; confira a conta."),
    EventoTipo.layout_mudou: (
        NotificacaoTipo.coleta_layout, "Coleta recuou 24 h: layout mudou",
        ("As páginas vieram sem campos reconhecíveis. Atualize o coletor e rode o "
        "reprocessamento.")),
}
_IMAGEM_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


# ---- rodadas ----

def coleta_aberta_de(db: Session, cliente_id: uuid.UUID) -> Coleta | None:
    return db.scalar(select(Coleta).where(Coleta.cliente_id == cliente_id,
                                          Coleta.estado.in_(COLETA_ABERTAS)))


def abrir_rodada(db: Session, cliente: ColetaCliente, body: schemas.AbrirColetaIn) -> Coleta:
    aberta = coleta_aberta_de(db, cliente.id)
    if aberta is not None:
        raise ApiError(409, "coleta_em_andamento", EM_ANDAMENTO,
                       details={"coletaId": str(aberta.id),
                                "batimentoEm": aberta.batimento_em.isoformat()})
    agora = comum.agora()
    coleta = Coleta(id=uuid.uuid4(), cliente_id=cliente.id, rede=cliente.rede,
                    mercado=cliente.mercado, iniciada_em=body.iniciada_em or agora,
                    batimento_em=agora, estado=ColetaEstado.ativa,
                    versao_coletor=body.versao_coletor, chrome_versao=body.chrome_versao,
                    protocolo=body.protocolo,
                    resumo={"limitesLocais": body.limites_locais.model_dump(by_alias=True)
                            if body.limites_locais else {}})
    db.add(coleta)
    db.flush()
    return coleta


def _coleta(db: Session, cliente: ColetaCliente, coleta_id: uuid.UUID, lock: bool = True
            ) -> Coleta:
    coleta = db.get(Coleta, coleta_id, with_for_update=lock)
    if coleta is None or coleta.cliente_id != cliente.id:
        raise ApiError(404, "coleta_nao_encontrada", NAO_ENCONTRADA)
    return coleta


def _coleta_aberta(db: Session, cliente: ColetaCliente, coleta_id: uuid.UUID) -> Coleta:
    coleta = _coleta(db, cliente, coleta_id)
    if coleta.estado not in COLETA_ABERTAS:
        raise ApiError(409, "coleta_fechada", FECHADA)
    return coleta


def devolver_reservas(db: Session, coleta: Coleta) -> int:
    """As tarefas ainda `reservada` desta rodada voltam a `pendente` na hora."""
    r = db.execute(update(Tarefa).where(Tarefa.coleta_id == coleta.id,
                                        Tarefa.estado == FilaEstado.reservada)
                   .values(estado=FilaEstado.pendente, reservada_ate=None, cliente_id=None,
                           coleta_id=None))
    r2 = db.execute(update(Tarefa).where(Tarefa.cliente_id == coleta.cliente_id,
                                         Tarefa.coleta_id.is_(None),
                                         Tarefa.estado == FilaEstado.reservada)
                    .values(estado=FilaEstado.pendente, reservada_ate=None, cliente_id=None))
    return (r.rowcount or 0) + (r2.rowcount or 0)


def _terminar(coleta: Coleta, estado: ColetaEstado, motivo: str,
              extra: dict[str, Any] | None = None) -> None:
    agora = comum.agora()
    coleta.estado = estado
    coleta.terminada_em = agora
    coleta.resumo = {**coleta.resumo, "motivo": motivo,
                     "duracaoS": int((agora - coleta.iniciada_em).total_seconds()),
                     **(extra or {})}


def fechar_rodada(db: Session, cliente: ColetaCliente, coleta_id: uuid.UUID,
                  body: schemas.FimIn) -> Coleta:
    coleta = _coleta(db, cliente, coleta_id)
    if coleta.estado not in COLETA_ABERTAS:
        return coleta  # idempotente: devolve a rodada como está
    estado = ColetaEstado.interrompida if body.motivo in ("parar_local", "servico_parado") \
        else ColetaEstado.encerrada
    _terminar(coleta, estado, body.motivo, {"porTipo": body.por_tipo})
    devolver_reservas(db, coleta)
    db.flush()
    return coleta


# ---- batimento ----

def _pausa_vencida(db: Session, coleta: Coleta, agora: datetime) -> bool:
    inicio = db.scalar(select(func.max(Evento.recebido_em)).where(
        Evento.coleta_id == coleta.id,
        Evento.tipo.in_((EventoTipo.captcha, EventoTipo.login_perdido))))
    inicio = inicio or coleta.batimento_em
    return agora - inicio >= timedelta(hours=CAPTCHA_ESPERA_MAX_H)


def _retomar_se_continuou(coleta: Coleta, cfg: ColetaConfig, agora: datetime) -> bool:
    """Depois do clique "Continuar" e do esfriamento, a rodada pausada volta a `ativa`."""
    if coleta.estado not in COLETA_PAUSADAS or cfg.continuar_em is None:
        return False
    if agora >= cfg.continuar_em + timedelta(minutes=CAPTCHA_ESFRIAR_MIN):
        coleta.estado = ColetaEstado.ativa
        return True
    return False


def batimento(db: Session, cliente: ColetaCliente, coleta_id: uuid.UUID,
              body: schemas.BatimentoIn) -> schemas.BatimentoOut:
    coleta = _coleta_aberta(db, cliente, coleta_id)
    cfg = comum.config_atual(db)
    agora = comum.agora()
    coleta.batimento_em = agora
    if body.tarefa_atual_id is not None:
        coleta.tarefa_atual_id = body.tarefa_atual_id
    motivo = None
    if coleta.estado in COLETA_PAUSADAS:
        if _retomar_se_continuou(coleta, cfg, agora):
            pass
        elif cfg.continuar_em is None and _pausa_vencida(db, coleta, agora):
            _terminar(coleta, ColetaEstado.encerrada, "pausa_vencida")
            devolver_reservas(db, coleta)
            motivo = "pausa_vencida"
    orc = comum.orcamento(db, cfg, cliente.mercado)
    parar = (motivo is not None or not comum.ligada(db, cfg) or comum.pausada(cfg, agora)
             or orc.paginas_restantes <= 0 or coleta.estado not in COLETA_ABERTAS)
    if parar and motivo is None:
        motivo = ("desligada" if not comum.ligada(db, cfg) else
                  "pausada" if comum.pausada(cfg, agora) else
                  "orcamento" if orc.paginas_restantes <= 0 else "fechada")
    db.flush()
    return schemas.BatimentoOut(parar=parar, motivo=motivo, pausada_ate=cfg.pausada_ate,
                                continuar_em=cfg.continuar_em, limites=comum.limites(cfg),
                                orcamento=orc)


# ---- eventos ----

def _notificar(db: Session, tipo: EventoTipo, mercado: str, agora: datetime
               ) -> tuple[str | None, bool]:
    """Uma notificação por tipo por dia local, para os donos ativos (FR-031). Devolve a
    `dedupe_key` (para auditoria no evento) e se alguma linha nasceu agora."""
    if tipo not in EVENTOS_QUE_NOTIFICAM:
        return None, False
    ntipo, titulo, corpo = _NOTIFICACAO[tipo]
    dedupe = f"coleta:{tipo.value}:{mercados.data_local(agora, mercado).isoformat()}"
    n = notificacoes.criar(db, ntipo, titulo, corpo, comum.LINK_CONFIG, None, dedupe,
                           notificacoes.donos_ativos(db))
    return dedupe, n > 0


def _recuar(db: Session, cfg: ColetaConfig, agora: datetime) -> None:
    """Bloqueio ou layout: `coleta_config.pausada_ate = agora + 24 h` (FR-017), com histórico."""
    if cfg.version == 0:  # linha ainda não existe: nasce com os padrões
        db.add(cfg)
        db.flush()
        history.record(db, COLETOR, comum.ENTITY_CONFIG, comum.ConfigEntidade(cfg), "created", None,
                       history.snapshot(cfg))
    before = history.snapshot(cfg)
    cfg.pausada_ate = agora + timedelta(hours=RECUO_BLOQUEIO_H)
    history.record(db, COLETOR, comum.ENTITY_CONFIG, comum.ConfigEntidade(cfg), "updated", before,
                   history.snapshot(cfg), {"acao": "recuo_bloqueio"})


def evento(db: Session, cliente: ColetaCliente, body: schemas.EventoIn) -> tuple[Evento, Coleta | None, bool]:
    agora = comum.agora()
    chave = privacidade.chave_pessoal(body.detalhe, chaves=privacidade.CHAVES_PESSOAIS_CAMPOS)
    if chave is not None:
        raise ApiError(400, "bruto_pessoal", f"O detalhe do evento traz dado pessoal: {chave}",
                       details={"field": chave})
    coleta = None
    if body.coleta_id is not None:
        coleta = _coleta(db, cliente, body.coleta_id)
    cfg = comum.config_atual(db)
    if coleta is not None and coleta.estado in COLETA_ABERTAS:
        if body.tipo == EventoTipo.captcha:
            coleta.estado = ColetaEstado.pausada_captcha
        elif body.tipo == EventoTipo.login_perdido:
            coleta.estado = ColetaEstado.pausada_login
        elif body.tipo in (EventoTipo.parar_local, EventoTipo.parado):
            _terminar(coleta, ColetaEstado.interrompida, body.tipo.value)
            devolver_reservas(db, coleta)
        elif body.tipo in (EventoTipo.bloqueio_suspeito, EventoTipo.layout_mudou):
            _terminar(coleta, ColetaEstado.abortada, body.tipo.value)
            devolver_reservas(db, coleta)
        elif body.tipo == EventoTipo.retomou and coleta.estado in COLETA_PAUSADAS:
            coleta.estado = ColetaEstado.ativa
    if body.tipo in (EventoTipo.bloqueio_suspeito, EventoTipo.layout_mudou):
        _recuar(db, cfg, agora)
    dedupe, notificado = _notificar(db, body.tipo, cliente.mercado, agora)
    ev = Evento(tipo=body.tipo, cliente_id=cliente.id, coleta_id=coleta.id if coleta else None,
                tarefa_id=body.tarefa_id, detalhe=privacidade.podar(body.detalhe),
                ocorreu_em=body.ocorreu_em or agora, recebido_em=agora,
                notificacao_dedupe=dedupe)
    db.add(ev)
    db.flush()
    return ev, coleta, notificado


# ---- itens ----

@dataclass
class _Gravacao:
    gravou: bool = False
    ficha_nova: bool = False
    imagens_pendentes: list[str] = field(default_factory=list)
    produto: Produto | None = None


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def _decodificar_bruto(bruto: str | None) -> tuple[bytes | None, dict | list | None]:
    """O bruto vem gzip + base64; devolve `(gzip, json)`; `bruto_grande` se passar do teto."""
    if not bruto:
        return None, None
    try:
        comprimido = base64.b64decode(bruto, validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(comprimido)) as g:
            dados = g.read(BRUTO_BYTES_MAX + 1)
    except (ValueError, OSError, EOFError) as exc:
        raise CampoInvalido("bruto", "bruto_invalido") from exc
    if len(dados) > BRUTO_BYTES_MAX:
        raise CampoInvalido("bruto", "bruto_grande")
    try:
        return comprimido, json.loads(dados)
    except ValueError as exc:
        raise CampoInvalido("bruto", "bruto_invalido") from exc


def _guardar_bruto(dados: dict | list, data_local: date, coleta_id: uuid.UUID,
                   tarefa_id: uuid.UUID) -> tuple[str | None, int | None]:
    """Grava o bruto podado em gzip no bucket `mercado`; sem HD devolve `(None, None)`."""
    corpo = gzip.compress(json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode())
    chave = f"bruto/{data_local.isoformat()}/{coleta_id}/{tarefa_id}.json.gz"
    try:
        storage.put(chave, corpo, "application/gzip", bucket="mercado")
    except ApiError as exc:
        if exc.status in (503, 507):
            return None, None
        raise
    except (S3Error, urllib3.exceptions.HTTPError, OSError):  # MinIO fora (FR-030)
        log.exception("bruto não gravado (MinIO indisponível); item segue como bruto pendente")
        return None, None
    return chave, len(corpo)


def _upsert_categoria(db: Session, rede: Platform, mercado: str, ref: CategoriaRef | None,
                      coleta_id: uuid.UUID, agora: datetime) -> Categoria | None:
    """A folha do caminho (criando os nós que faltam, com `nivel` pela posição)."""
    if ref is None:
        return None
    caminho = ref.caminho or []
    if not caminho:
        return None
    pai: Categoria | None = None
    nomes: list[str] = []
    atual: Categoria | None = None
    for nivel, no in enumerate(caminho[:3], start=1):
        nomes.append(no.nome)
        atual = db.scalar(select(Categoria).where(
            Categoria.rede == rede, Categoria.mercado == mercado,
            Categoria.rede_categoria_id == no.rede_categoria_id))
        if atual is None:
            atual = Categoria(id=uuid.uuid4(), rede=rede, mercado=mercado,
                              rede_categoria_id=no.rede_categoria_id, nome=no.nome, nivel=nivel,
                              pai_id=pai.id if pai else None, caminho=" > ".join(nomes),
                              ativa=True, primeira_vez_em=agora, ultimo_visto_em=agora,
                              coleta_id=coleta_id)
            db.add(atual)
            db.flush()
        else:
            atual.ultimo_visto_em = agora
            atual.coleta_id = coleta_id
        pai = atual
    return atual


def _upsert_loja(db: Session, rede: Platform, mercado: str, ref: LojaRef | None,
                 coleta_id: uuid.UUID, agora: datetime) -> Loja | None:
    if ref is None:
        return None
    loja = db.scalar(select(Loja).where(Loja.rede == rede, Loja.mercado == mercado,
                                        Loja.rede_loja_id == ref.rede_loja_id))
    url = privacidade.podar(ref.url) if ref.url else None
    if loja is None:
        loja = Loja(id=uuid.uuid4(), rede=rede, mercado=mercado, rede_loja_id=ref.rede_loja_id,
                    nome=ref.nome, oficial=ref.oficial, url=url, primeira_vez_em=agora,
                    ultimo_visto_em=agora, coleta_id=coleta_id)
        db.add(loja)
        db.flush()
    else:
        loja.nome, loja.oficial, loja.ultimo_visto_em, loja.coleta_id = (
            ref.nome, ref.oficial, agora, coleta_id)
        if url:
            loja.url = url
    return loja


def _upsert_produto(db: Session, rede: Platform, mercado: str, rede_produto_id: str,
                    url_canonica: str, fonte_descoberta: InteresseOrigem, coleta_id: uuid.UUID,
                    agora: datetime, titulo: str | None = None,
                    loja: Loja | None = None) -> Produto:
    """Cria o produto "pela cara" se não existe (identidade + título); senão só o último visto."""
    produto = db.scalar(select(Produto).where(
        Produto.rede == rede, Produto.mercado == mercado,
        Produto.rede_produto_id == rede_produto_id))
    if produto is None:
        produto = Produto(id=uuid.uuid4(), rede=rede, mercado=mercado,
                          rede_produto_id=rede_produto_id, url_canonica=url_canonica,
                          titulo_atual=titulo, loja_id=loja.id if loja else None,
                          primeira_vez_em=agora, ultimo_visto_em=agora, calor=Calor.quente,
                          fotos_por_dia=1, proxima_coleta_em=agora,
                          fonte_descoberta=fonte_descoberta, coleta_id=coleta_id)
        db.add(produto)
        db.flush()
    else:
        produto.ultimo_visto_em = agora
        produto.coleta_id = coleta_id
        if titulo and not produto.titulo_atual:
            produto.titulo_atual = titulo
        if loja is not None and produto.loja_id is None:
            produto.loja_id = loja.id
    return produto


def _imagens_existentes(db: Session, shas: list[str]) -> dict[str, uuid.UUID]:
    if not shas:
        return {}
    rows = db.execute(select(Imagem.sha256, Imagem.id).where(Imagem.sha256.in_(shas))).all()
    return dict(rows)


def _vincular_imagens(db: Session, produto: Produto, ficha: Ficha) -> list[str]:
    """`mercado_produto_imagens` para os shas já recebidos; devolve os pendentes."""
    existentes = _imagens_existentes(db, list(ficha.imagens_sha))
    pendentes = []
    for pos, sha in enumerate(ficha.imagens_sha):
        iid = existentes.get(sha)
        if iid is None:
            pendentes.append(sha)
            continue
        db.execute(insert(ProdutoImagem).values(produto_id=produto.id, ficha_id=ficha.id,
                                                imagem_id=iid, posicao=pos)
                   .on_conflict_do_nothing())
    produto.imagens_pendentes = bool(pendentes)
    return pendentes


def _faixa(f: Faixa | None) -> dict[str, Any]:
    if f is None:
        return {"vendidos": None, "vendidos_min": None, "vendidos_max": None,
                "vendidos_exato": None}
    return {"vendidos": f.valor, "vendidos_min": f.min, "vendidos_max": f.max,
            "vendidos_exato": f.exato}


def _inserir(db: Session, modelo, valores: dict[str, Any], **conflito) -> bool:
    """`INSERT … ON CONFLICT DO NOTHING … RETURNING pk`; True se gravou (o `rowcount` do insert
    ORM não é confiável; o RETURNING é, como no `notificacoes/service.py`)."""
    pk = next(iter(modelo.__table__.primary_key.columns))
    stmt = insert(modelo).values(**valores).on_conflict_do_nothing(**conflito).returning(pk)
    return len(db.execute(stmt).all()) > 0


def _gravar_produto(db: Session, tarefa: Tarefa, dados: ProdutoIn, data_local: date, turno: str,
                    coleta: Coleta, esquema: str, bruto_ref: str | None,
                    coletado_em: datetime, agora: datetime) -> _Gravacao:
    g = _Gravacao()
    rede, mercado = tarefa.rede, tarefa.mercado
    loja = _upsert_loja(db, rede, mercado, dados.ficha.loja if dados.ficha else None,
                        coleta.id, agora)
    categoria = _upsert_categoria(db, rede, mercado,
                                  dados.ficha.categoria if dados.ficha else None, coleta.id, agora)
    produto = _upsert_produto(db, rede, mercado, dados.rede_produto_id, dados.url_canonica,
                              InteresseOrigem.manual, coleta.id, agora,
                              dados.ficha.titulo if dados.ficha else None, loja)
    g.produto = produto
    if dados.ficha is not None:
        f = dados.ficha
        conteudo = {"titulo": f.titulo, "descricao": f.descricao,
                    "atributos": [a.model_dump() for a in f.atributos],
                    "variantes": [v.model_dump() for v in f.variantes],
                    "argumentos": f.argumentos, "selos": f.selos,
                    "categoria_id": str(categoria.id) if categoria else None,
                    "loja_id": str(loja.id) if loja else None, "imagens_sha": f.imagens_sha}
        h = _hash(json.dumps(conteudo, sort_keys=True, ensure_ascii=False))
        ficha = db.scalar(select(Ficha).where(Ficha.produto_id == produto.id,
                                              Ficha.hash_conteudo == h))
        if ficha is None:
            ficha = Ficha(id=uuid.uuid4(), produto_id=produto.id, hash_conteudo=h,
                          titulo=f.titulo, descricao=f.descricao,
                          atributos=[a.model_dump(by_alias=True) for a in f.atributos],
                          variantes=[v.model_dump(by_alias=True, exclude_none=True)
                                     for v in f.variantes],
                          argumentos=list(f.argumentos), selos=list(f.selos),
                          categoria_id=categoria.id if categoria else None,
                          loja_id=loja.id if loja else None, imagens_sha=list(f.imagens_sha),
                          esquema_versao=esquema, bruto_ref=bruto_ref, coleta_id=coleta.id,
                          coletado_em=coletado_em, created_at=agora)
            db.add(ficha)
            db.flush()
            g.ficha_nova = g.gravou = True
        produto.ficha_atual_id = ficha.id
        produto.titulo_atual = f.titulo
        produto.loja_id = loja.id if loja else produto.loja_id
        produto.categoria_id = categoria.id if categoria else produto.categoria_id
        if f.lancado_em and not produto.lancado_em:
            produto.lancado_em = f.lancado_em
        g.imagens_pendentes = _vincular_imagens(db, produto, ficha)
    comum_foto = {"produto_id": produto.id, "data_local": data_local, "turno": turno,
                  "esquema_versao": esquema, "bruto_ref": bruto_ref, "coleta_id": coleta.id,
                  "coletado_em": coletado_em}
    if dados.pagina_publica is not None:
        pp = dados.pagina_publica
        if _inserir(db, FotoProduto, {
                **comum_foto, "fonte": Fonte.pagina_publica, **_faixa(pp.vendidos),
                "preco_min_centavos": pp.preco_min_centavos,
                "preco_max_centavos": pp.preco_max_centavos or pp.preco_min_centavos,
                "preco_original_centavos": pp.preco_original_centavos, "moeda": pp.moeda,
                "nota": pp.nota, "n_avaliacoes": pp.n_avaliacoes,
                "estoque_visivel": pp.estoque_visivel, "disponivel": pp.disponivel,
                "campos": privacidade.podar(pp.campos)},
                index_elements=["produto_id", "data_local", "turno", "fonte"]):
            g.gravou = True
            produto.ultima_foto_em = max(produto.ultima_foto_em or data_local, data_local)
            if not pp.disponivel and produto.indisponivel_desde is None:
                produto.indisponivel_desde = data_local
            elif pp.disponivel:
                produto.indisponivel_desde = None
    if dados.affiliate is not None:
        af = dados.affiliate
        if _inserir(db, FotoProduto, {
                **comum_foto, "fonte": Fonte.affiliate, **_faixa(None),
                "preco_min_centavos": af.preco_min_centavos,
                "preco_max_centavos": af.preco_max_centavos or af.preco_min_centavos,
                "moeda": af.moeda, "comissao_bp": af.comissao_bp, "n_criadores": af.n_criadores,
                "vendas_7d": af.vendas_7d, "vendas_30d": af.vendas_30d,
                "campos": privacidade.podar(af.campos)},
                index_elements=["produto_id", "data_local", "turno", "fonte"]):
            g.gravou = True
            produto.ultima_foto_em = max(produto.ultima_foto_em or data_local, data_local)
            produto.ultima_foto_affiliate_em = max(produto.ultima_foto_affiliate_em or data_local,
                                                   data_local)
    return g


def _gravar_ranking(db: Session, tarefa: Tarefa, dados: RankingIn, data_local: date,
                    coleta: Coleta, esquema: str, bruto_ref: str | None,
                    coletado_em: datetime, agora: datetime) -> _Gravacao:
    g = _Gravacao()
    rede, mercado = tarefa.rede, tarefa.mercado
    categoria = _upsert_categoria(db, rede, mercado, dados.categoria, coleta.id, agora)
    foto_id = uuid.uuid4()
    gravou = _inserir(db, FotoRanking, {
        "id": foto_id, "rede": rede, "mercado": mercado, "fonte": Fonte.affiliate,
        "categoria_id": categoria.id if categoria else None,
        "tipo": RankingTipo(dados.ranking_tipo), "janela": dados.janela,
        "data_local": data_local, "n_itens": len(dados.itens), "esquema_versao": esquema,
        "bruto_ref": bruto_ref, "coleta_id": coleta.id, "coletado_em": coletado_em})
    if not gravou:
        return g
    g.gravou = True
    for item in dados.itens:
        loja = _upsert_loja(db, rede, mercado, item.loja, coleta.id, agora)
        produto = _upsert_produto(db, rede, mercado, item.rede_produto_id, item.url_canonica,
                                  InteresseOrigem.ranking, coleta.id, agora, item.titulo, loja)
        produto.ultimo_ranking_em = max(produto.ultimo_ranking_em or data_local, data_local)
        if categoria is not None and produto.categoria_id is None:
            produto.categoria_id = categoria.id
        _inserir(db, ItemRanking, {
            "ranking_foto_id": foto_id, "posicao": item.posicao, "produto_id": produto.id,
            "valor_exibido": item.valor_exibido, "valor_num": item.valor_num,
            "campos": privacidade.podar({**item.campos, "imagemSha": item.imagem_sha})})
    return g


def _gravar_categorias(db: Session, tarefa: Tarefa, dados: CategoriasIn, coleta: Coleta,
                       agora: datetime) -> _Gravacao:
    g = _Gravacao()
    rede, mercado = tarefa.rede, tarefa.mercado
    vistos: set[str] = set()
    por_rede_id: dict[str, Categoria] = {}
    for c in sorted(dados.categorias, key=lambda c: c.nivel):
        vistos.add(c.rede_categoria_id)
        pai = por_rede_id.get(c.pai_rede_id) if c.pai_rede_id else None
        if pai is None and c.pai_rede_id:
            pai = db.scalar(select(Categoria).where(
                Categoria.rede == rede, Categoria.mercado == mercado,
                Categoria.rede_categoria_id == c.pai_rede_id))
        if c.nivel > 1 and pai is None:
            continue  # pai desconhecido: fica para a próxima semana
        caminho = f"{pai.caminho} > {c.nome}" if pai else c.nome
        atual = db.scalar(select(Categoria).where(
            Categoria.rede == rede, Categoria.mercado == mercado,
            Categoria.rede_categoria_id == c.rede_categoria_id))
        if atual is None:
            atual = Categoria(id=uuid.uuid4(), rede=rede, mercado=mercado,
                              rede_categoria_id=c.rede_categoria_id, nome=c.nome,
                              nivel=min(c.nivel, 3), pai_id=pai.id if pai else None,
                              caminho=caminho, ativa=True, primeira_vez_em=agora,
                              ultimo_visto_em=agora, coleta_id=coleta.id)
            db.add(atual)
            db.flush()
            g.gravou = True
        else:
            if (atual.nome, atual.caminho, atual.pai_id, atual.ativa) != (
                    c.nome, caminho, pai.id if pai else None, True):
                g.gravou = True
            atual.nome, atual.caminho, atual.ativa = c.nome, caminho, True
            atual.pai_id = pai.id if pai else None
            atual.ultimo_visto_em, atual.coleta_id = agora, coleta.id
        por_rede_id[c.rede_categoria_id] = atual
    if vistos:
        sumiram = db.scalars(select(Categoria).where(
            Categoria.rede == rede, Categoria.mercado == mercado, Categoria.ativa.is_(True),
            Categoria.rede_categoria_id.not_in(vistos))).all()
        for c in sumiram:
            c.ativa = False  # nunca apagada: continua nas fichas e rankings antigos
            g.gravou = True
    return g


def _gravar_vitrine(db: Session, tarefa: Tarefa, dados: VitrineIn, coleta: Coleta,
                    agora: datetime) -> _Gravacao:
    g = _Gravacao()
    rede, mercado = tarefa.rede, tarefa.mercado
    ids = []
    for item in dados.itens:
        produto = _upsert_produto(db, rede, mercado, item.rede_produto_id, item.url_canonica,
                                  InteresseOrigem.vitrine, coleta.id, agora, item.titulo)
        ids.append(produto.id)
    novos = interesses.vitrine_para_todos(db, ids, {"coletaId": str(coleta.id)})
    g.gravou = novos > 0 or not dados.itens
    return g


def _gravar_loja(db: Session, tarefa: Tarefa, dados: LojaIn, data_local: date, coleta: Coleta,
                 esquema: str, bruto_ref: str | None, coletado_em: datetime,
                 agora: datetime) -> _Gravacao:
    g = _Gravacao()
    rede, mercado = tarefa.rede, tarefa.mercado
    loja = _upsert_loja(db, rede, mercado,
                        LojaRef(rede_loja_id=dados.rede_loja_id, nome=dados.nome,
                                oficial=dados.oficial, url=dados.url), coleta.id, agora)
    if dados.foto is not None:
        fo = dados.foto
        vt = fo.vendidos_total
        if _inserir(db, FotoLoja, {
                "loja_id": loja.id, "data_local": data_local, "fonte": Fonte.pagina_publica,
                "nota": fo.nota, "seguidores": fo.seguidores,
                "envio_no_prazo_pct": fo.envio_no_prazo_pct,
                "tempo_resposta_pct": fo.tempo_resposta_pct, "n_produtos": fo.n_produtos,
                "vendidos_total": vt.valor if vt else None,
                "vendidos_total_min": vt.min if vt else None,
                "vendidos_total_max": vt.max if vt else None,
                "vendidos_total_exato": vt.exato if vt else None,
                "campos": privacidade.podar(fo.campos), "esquema_versao": esquema,
                "bruto_ref": bruto_ref, "coleta_id": coleta.id, "coletado_em": coletado_em},
                index_elements=["loja_id", "data_local", "fonte"]):
            g.gravou = True
            loja.ultima_foto_em = data_local
    for p in dados.produtos:
        _upsert_produto(db, rede, mercado, p.rede_produto_id, p.url_canonica,
                        InteresseOrigem.loja, coleta.id, agora, p.titulo, loja)
    return g


def _autor_hash(autor_ref: str | None, texto_hash: str) -> str | None:
    pepper = get_settings().mercado_hash_pepper.get_secret_value()
    if not pepper:
        return None
    base = autor_ref if autor_ref else f"anon:{texto_hash}"
    return _hash(f"{base}{pepper}")


def _gravar_avaliacoes(db: Session, tarefa: Tarefa, dados: AvaliacoesIn, data_local: date,
                       coleta: Coleta, esquema: str, bruto_ref: str | None,
                       coletado_em: datetime, agora: datetime) -> _Gravacao:
    g = _Gravacao()
    produto = _upsert_produto(db, tarefa.rede, tarefa.mercado, dados.rede_produto_id,
                              tarefa.url, InteresseOrigem.manual, coleta.id, agora)
    g.produto = produto
    for a in dados.itens:
        texto = a.texto or ""
        texto_hash = _hash(" ".join(texto.lower().split()))
        autor_hash = _autor_hash(a.autor_ref, texto_hash)
        if autor_hash is None:
            raise CampoInvalido("autorRef", "pepper_ausente")
        if _inserir(db, Avaliacao, {
                "id": uuid.uuid4(), "produto_id": produto.id,
                "rede_avaliacao_id": a.rede_avaliacao_id, "autor_hash": autor_hash,
                "texto": a.texto, "texto_hash": texto_hash, "nota": a.nota,
                "data_avaliacao": a.data_avaliacao, "variante": a.variante,
                "imagens_sha": list(a.imagens_sha), "curtidas": a.curtidas,
                "campos": privacidade.anonimizar(privacidade.podar(a.campos)),
                "esquema_versao": esquema,
                "bruto_ref": bruto_ref, "coleta_id": coleta.id, "coletado_em": coletado_em}):
            g.gravou = True
            g.imagens_pendentes += [s for s in a.imagens_sha
                                    if s not in _imagens_existentes(db, list(a.imagens_sha))]
    produto.ultimas_avaliacoes_em = data_local
    return g


def _gravar_videos(db: Session, tarefa: Tarefa, dados: ProdutoVideosIn, data_local: date,
                   coleta: Coleta, esquema: str, bruto_ref: str | None, coletado_em: datetime,
                   agora: datetime) -> _Gravacao:
    g = _Gravacao()
    produto = _upsert_produto(db, tarefa.rede, tarefa.mercado, dados.rede_produto_id,
                              tarefa.url, InteresseOrigem.manual, coleta.id, agora)
    g.produto = produto
    for v in dados.itens:
        if _inserir(db, VideoProduto, {
                "id": uuid.uuid4(), "produto_id": produto.id, "rede": tarefa.rede,
                "mercado": tarefa.mercado, "rede_video_id": v.rede_video_id,
                "autor_handle": v.autor_handle.lstrip("@"), "views": v.views, "likes": v.likes,
                "comentarios": v.comentarios, "compartilhamentos": v.compartilhamentos,
                "legenda": v.legenda, "publicado_em": v.publicado_em, "data_local": data_local,
                "posicao": v.posicao, "campos": privacidade.podar(v.campos),
                "esquema_versao": esquema, "bruto_ref": bruto_ref, "coleta_id": coleta.id,
                "coletado_em": coletado_em},
                index_elements=["produto_id", "rede_video_id", "data_local"]):
            g.gravou = True
    produto.ultimos_videos_em = data_local
    return g


def _registrar_item(db: Session, coleta: Coleta, tarefa: Tarefa | None, item: schemas.ItemIn,
                    status: ItemStatus, data_local: date, turno: str | None,
                    erro: tuple[str, str | None] | None = None, bruto_ref: str | None = None,
                    bruto_bytes: int | None = None) -> ColetaItem:
    linha = ColetaItem(coleta_id=coleta.id, tarefa_id=tarefa.id if tarefa else None,
                       tipo=tarefa.tipo if tarefa else "produto",
                       fonte=Fonte(item.fonte) if item.fonte in ("pagina_publica", "affiliate")
                       else None, status=status, erro_codigo=erro[0] if erro else None,
                       erro_campo=erro[1] if erro else None, duracao_ms=item.duracao_ms,
                       coletado_em=item.coletado_em, data_local=data_local, turno=turno,
                       esquema_versao=item.esquema_versao, bruto_ref=bruto_ref,
                       bruto_bytes=bruto_bytes, reprocessado_de=item.reprocessado_de)
    db.add(linha)
    return linha


def _fechar_tarefa(tarefa: Tarefa, coleta: Coleta, status: ItemStatus, agora: datetime,
                   erro: str | None = None) -> tuple[int, bool]:
    """`recebida` quando gravou ou repetiu; senão volta à fila até `FILA_TENTATIVAS_MAX`."""
    if status in (ItemStatus.gravado, ItemStatus.repetido):
        tarefa.estado = FilaEstado.recebida
        tarefa.coleta_id = coleta.id
        tarefa.recebida_em = agora
        tarefa.resultado_status = status
        tarefa.reservada_ate = None
        return tarefa.tentativas, False
    tarefa.tentativas += 1
    tarefa.erro_codigo = erro
    tarefa.resultado_status = status
    if tarefa.tentativas >= FILA_TENTATIVAS_MAX:
        tarefa.estado = FilaEstado.falhou
        tarefa.coleta_id = coleta.id
        return tarefa.tentativas, False
    tarefa.estado = FilaEstado.pendente
    tarefa.reservada_ate = None
    tarefa.cliente_id = None
    tarefa.coleta_id = None
    return tarefa.tentativas, True


def _processar_item(db: Session, cliente: ColetaCliente, coleta: Coleta,
                    item: schemas.ItemIn, agora: datetime) -> schemas.ResultadoItem:
    tarefa = db.get(Tarefa, item.tarefa_id, with_for_update=True)
    data_local, turno = mercados.data_local_e_turno(item.coletado_em, cliente.mercado)
    if tarefa is None:
        _registrar_item(db, coleta, None, item, ItemStatus.invalido, data_local, turno,
                        ("tarefa_desconhecida", None))
        return schemas.ResultadoItem(tarefa_id=item.tarefa_id, status=ItemStatus.invalido,
                                     erro_codigo="tarefa_desconhecida")
    data_local, turno = mercados.data_local_e_turno(item.coletado_em, tarefa.mercado)
    turno_tarefa = tarefa.turno.value if tarefa.turno else None
    turno_item = turno_tarefa or turno.value
    if tarefa.cliente_id != cliente.id and item.reprocessado_de is not None:
        _registrar_item(db, coleta, tarefa, item, ItemStatus.invalido, data_local, turno_item,
                        ("tarefa_de_outro_cliente", None))
        return schemas.ResultadoItem(tarefa_id=tarefa.id, status=ItemStatus.invalido,
                                     erro_codigo="tarefa_de_outro_cliente")
    if tarefa.estado == FilaEstado.recebida and item.reprocessado_de is None:
        _registrar_item(db, coleta, tarefa, item, ItemStatus.repetido, data_local, turno_item)
        return schemas.ResultadoItem(tarefa_id=tarefa.id, status=ItemStatus.repetido,
                                     data_local=data_local, turno=turno_item)
    if tarefa.cliente_id != cliente.id:
        motivo = "tarefa_de_outro_cliente" if tarefa.cliente_id else "reserva_vencida"
        _registrar_item(db, coleta, tarefa, item, ItemStatus.invalido, data_local, turno_item,
                        (motivo, None))
        return schemas.ResultadoItem(tarefa_id=tarefa.id, status=ItemStatus.invalido,
                                     erro_codigo=motivo)
    if item.status in ("erro", "captcha"):
        status = ItemStatus.captcha if item.status == "captcha" else ItemStatus.erro
        codigo = item.erro_codigo or item.status
        _registrar_item(db, coleta, tarefa, item, status, data_local, turno_item, (codigo, None))
        tentativas, volta = _fechar_tarefa(tarefa, coleta, status, agora, codigo)
        if tarefa.produto_id:
            produto = db.get(Produto, tarefa.produto_id)
            if produto is not None:
                produto.ultimo_erro_codigo, produto.ultimo_erro_em = codigo, agora
        if status == ItemStatus.captcha and coleta.estado == ColetaEstado.ativa:
            coleta.estado = ColetaEstado.pausada_captcha
            _notificar(db, EventoTipo.captcha, cliente.mercado, agora)
        return schemas.ResultadoItem(tarefa_id=tarefa.id, status=status, erro_codigo=codigo,
                                     tentativas=tentativas, volta_para_fila=volta)
    fonte = registro.fonte_para(tarefa.rede)
    try:
        if fonte is None or item.esquema_versao != fonte.esquema_versao:
            raise CampoInvalido("esquemaVersao", "esquema_desconhecido")
        if not item.campos:
            raise CampoInvalido("campos", "campos_invalidos")
        if (chave := privacidade.chave_pessoal(
                item.campos, chaves=privacidade.CHAVES_PESSOAIS_CAMPOS)) is not None:
            raise CampoInvalido(chave, "bruto_pessoal")
        dados = fonte.normalizar(tarefa.tipo, item.campos)
        if tarefa.tipo == "produto" and fonte.url_canonica(dados.url_canonica) != \
                fonte.url_canonica(tarefa.url):
            raise CampoInvalido("urlCanonica", "url_divergente")
        _, bruto_json = _decodificar_bruto(item.bruto)
        bruto_ref = bruto_bytes = None
        bruto_pendente = False
        if bruto_json is not None:
            # O coletor já podou (FR-029): sobrou chave pessoal com valor → recusa. Só depois a
            # poda do servidor (defensiva: URLs com query, chaves novas).
            if (chave := privacidade.chave_pessoal(bruto_json)) is not None:
                raise CampoInvalido(f"bruto.{chave}", "bruto_pessoal")
            bruto_json = privacidade.podar(bruto_json)
            bruto_ref, bruto_bytes = _guardar_bruto(privacidade.anonimizar(bruto_json), data_local,
                                                    coleta.id, tarefa.id)
            bruto_pendente = bruto_ref is None
    except CampoInvalido as exc:
        _registrar_item(db, coleta, tarefa, item, ItemStatus.invalido, data_local, turno_item,
                        (exc.motivo, exc.campo))
        tentativas, volta = _fechar_tarefa(tarefa, coleta, ItemStatus.invalido, agora, exc.motivo)
        return schemas.ResultadoItem(tarefa_id=tarefa.id, status=ItemStatus.invalido,
                                     erro_codigo=exc.motivo, erro_campo=exc.campo,
                                     tentativas=tentativas, volta_para_fila=volta)
    args = (db, tarefa, dados)
    esquema = fonte.esquema_versao
    try:
        if isinstance(dados, ProdutoIn):
            g = _gravar_produto(*args, data_local, turno_item, coleta, esquema, bruto_ref,
                                item.coletado_em, agora)
        elif isinstance(dados, RankingIn):
            g = _gravar_ranking(*args, data_local, coleta, esquema, bruto_ref, item.coletado_em,
                                agora)
        elif isinstance(dados, CategoriasIn):
            g = _gravar_categorias(*args, coleta, agora)
        elif isinstance(dados, VitrineIn):
            g = _gravar_vitrine(*args, coleta, agora)
        elif isinstance(dados, LojaIn):
            g = _gravar_loja(*args, data_local, coleta, esquema, bruto_ref, item.coletado_em, agora)
        elif isinstance(dados, AvaliacoesIn):
            g = _gravar_avaliacoes(*args, data_local, coleta, esquema, bruto_ref,
                                   item.coletado_em, agora)
        elif isinstance(dados, ProdutoVideosIn):
            g = _gravar_videos(*args, data_local, coleta, esquema, bruto_ref, item.coletado_em,
                               agora)
        else:  # pragma: no cover — o adaptador só devolve estes
            raise CampoInvalido("tipo", "tipo_desconhecido")
    except CampoInvalido as exc:
        _registrar_item(db, coleta, tarefa, item, ItemStatus.invalido, data_local, turno_item,
                        (exc.motivo, exc.campo))
        tentativas, volta = _fechar_tarefa(tarefa, coleta, ItemStatus.invalido, agora, exc.motivo)
        return schemas.ResultadoItem(tarefa_id=tarefa.id, status=ItemStatus.invalido,
                                     erro_codigo=exc.motivo, erro_campo=exc.campo,
                                     tentativas=tentativas, volta_para_fila=volta)
    status = ItemStatus.gravado if g.gravou else ItemStatus.repetido
    _registrar_item(db, coleta, tarefa, item, status, data_local, turno_item,
                    bruto_ref=bruto_ref, bruto_bytes=bruto_bytes)
    _fechar_tarefa(tarefa, coleta, status, agora)
    if g.produto is not None and tarefa.produto_id is None:
        tarefa.produto_id = g.produto.id
    if g.produto is not None:
        g.produto.ultimo_erro_codigo = None
    return schemas.ResultadoItem(tarefa_id=tarefa.id, status=status, data_local=data_local,
                                 turno=turno_item, imagens_pendentes=g.imagens_pendentes,
                                 bruto_pendente=bruto_pendente, ficha_nova=g.ficha_nova)


def receber_itens(db: Session, cliente: ColetaCliente, coleta_id: uuid.UUID,
                  body: schemas.ItensIn, tamanho_corpo: int | None = None) -> schemas.ItensOut:
    if tamanho_corpo is not None and tamanho_corpo > LOTE_BYTES_MAX:
        raise ApiError(413, "lote_grande", "Lote grande demais (máximo 50 itens e 6 MB)")
    # `reprocessar --desde` (FR-012) reenvia para a rodada original, já fechada: só com
    # `reprocessadoDe` em todos os itens; senão a rodada precisa estar aberta.
    if all(i.reprocessado_de is not None for i in body.itens):
        coleta = _coleta(db, cliente, coleta_id)
    else:
        coleta = _coleta_aberta(db, cliente, coleta_id)
    agora = comum.agora()
    resultados: list[schemas.ResultadoItem] = []
    for item in body.itens:
        try:
            with db.begin_nested():
                resultado = _processar_item(db, cliente, coleta, item, agora)
        except Exception:  # um item quebrado não derruba o lote (FR-028)
            log.exception("item da coleta falhou; tarefa %s", item.tarefa_id)
            with db.begin_nested():
                data_local, turno = mercados.data_local_e_turno(item.coletado_em,
                                                                cliente.mercado)
                _registrar_item(db, coleta, None, item, ItemStatus.invalido, data_local,
                                turno.value, ("erro_interno", None))
            resultado = schemas.ResultadoItem(tarefa_id=item.tarefa_id,
                                              status=ItemStatus.invalido,
                                              erro_codigo="erro_interno")
        resultados.append(resultado)
    coleta.batimento_em = agora
    coleta.paginas += sum(1 for r in resultados if r.status in comum.PAGINAS_QUE_CONTAM)
    coleta.itens_ok += sum(1 for r in resultados if r.status == ItemStatus.gravado)
    coleta.itens_repetidos += sum(1 for r in resultados if r.status == ItemStatus.repetido)
    coleta.itens_erro += sum(1 for r in resultados
                             if r.status in (ItemStatus.erro, ItemStatus.invalido,
                                             ItemStatus.captcha))
    cfg = comum.config_atual(db)
    orc = comum.orcamento(db, cfg, cliente.mercado)
    parar = (not comum.ligada(db, cfg) or comum.pausada(cfg, agora)
             or orc.paginas_restantes <= 0 or coleta.estado not in COLETA_ABERTAS)
    db.flush()
    return schemas.ItensOut(coleta_id=coleta.id, resultados=resultados, orcamento=orc,
                            pausada_ate=cfg.pausada_ate, parar=parar)


# ---- imagens ----

def _materializar_vinculos(db: Session, sha: str, imagem_id: uuid.UUID) -> None:
    """Fichas que já citavam este sha ganham a linha de ordem que faltava (FR-005)."""
    fichas = db.scalars(select(Ficha).where(Ficha.imagens_sha.any(sha))).all()
    for ficha in fichas:
        pos = list(ficha.imagens_sha).index(sha)
        db.execute(insert(ProdutoImagem).values(produto_id=ficha.produto_id, ficha_id=ficha.id,
                                                imagem_id=imagem_id, posicao=pos)
                   .on_conflict_do_nothing())
        produto = db.get(Produto, ficha.produto_id)
        if produto is not None and produto.imagens_pendentes:
            faltam = set(ficha.imagens_sha) - set(_imagens_existentes(db, list(ficha.imagens_sha)))
            produto.imagens_pendentes = bool(faltam - {sha})


def receber_imagens(db: Session, cliente: ColetaCliente, coleta_id: uuid.UUID,
                    arquivos: list[tuple[str, bytes]], manifesto: list[schemas.ManifestoImagem]
                    ) -> schemas.ImagensOut:
    """`arquivos` = `(nome, bytes)` na ordem do multipart; o `manifesto` casa pelo sha256."""
    if len(arquivos) > IMAGENS_POR_CHAMADA_MAX:
        raise ApiError(413, "lote_grande", "Lote grande demais (máximo 10 imagens)")
    for _, dados in arquivos:
        if len(dados) > IMAGEM_BYTES_MAX:
            raise ApiError(413, "arquivo_grande", "Imagem grande demais (máximo 5 MB)")
    coleta = _coleta_aberta(db, cliente, coleta_id)
    cfg = comum.config_atual(db)
    datadir.ensure_writable(sum(len(d) for _, d in arquivos))
    por_sha = {m.sha256: m for m in manifesto}
    aceitas: list[str] = []
    repetidas: list[str] = []
    recusadas: list[schemas.ImagemRecusada] = []
    contagem = comum.contagem_hoje(db, cliente.mercado)
    restantes = max(0, cfg.imagens_dia - contagem.imagens)
    agora = comum.agora()
    for _nome, dados in arquivos:
        sha = hashlib.sha256(dados).hexdigest()
        meta = por_sha.get(sha)
        if meta is None:
            recusadas.append(schemas.ImagemRecusada(sha256=sha, motivo="sha_divergente"))
            continue
        if db.scalar(select(Imagem.id).where(Imagem.sha256 == sha)) is not None:
            repetidas.append(sha)
            continue
        if restantes <= 0:
            recusadas.append(schemas.ImagemRecusada(sha256=sha, motivo="orcamento"))
            continue
        try:
            info = imaging.validate_image(dados, "imagem", max_bytes=IMAGEM_BYTES_MAX)
        except ApiError:
            recusadas.append(schemas.ImagemRecusada(sha256=sha, motivo="imagem_invalida"))
            continue
        chave = f"mercado/{sha[:2]}/{sha}.{_IMAGEM_EXT.get(info.content_type, info.ext)}"
        storage.put(chave, dados, info.content_type, bucket="imagens")
        imagem_id = uuid.uuid4()
        gravou = _inserir(db, Imagem, {
            "id": imagem_id, "sha256": sha, "object_key": chave,
            "content_type": info.content_type, "bytes": len(dados), "width": info.width,
            "height": info.height, "origem": meta.origem, "coleta_id": coleta.id,
            "created_at": agora}, index_elements=["sha256"])
        if not gravou:
            repetidas.append(sha)
            continue
        _materializar_vinculos(db, sha, imagem_id)
        aceitas.append(sha)
        restantes -= 1
    coleta.imagens += len(aceitas)
    coleta.batimento_em = agora
    db.flush()
    contagem = comum.contagem_hoje(db, cliente.mercado)
    return schemas.ImagensOut(
        aceitas=aceitas, repetidas=repetidas, recusadas=recusadas,
        orcamento=schemas.OrcamentoImagens(imagens_hoje=contagem.imagens,
                                           imagens_restantes=max(0, cfg.imagens_dia
                                                                 - contagem.imagens)))


# ---- bruto ----

def link_bruto(db: Session, cliente: ColetaCliente, coleta_id: uuid.UUID,
               tarefa_id: uuid.UUID) -> schemas.BrutoLinkOut:
    _coleta(db, cliente, coleta_id, lock=False)
    item = db.scalar(select(ColetaItem).where(ColetaItem.coleta_id == coleta_id,
                                              ColetaItem.tarefa_id == tarefa_id,
                                              ColetaItem.bruto_ref.is_not(None))
                     .order_by(ColetaItem.id.desc()))
    if item is None:
        raise ApiError(404, "bruto_nao_encontrado", "Bruto pendente ou inexistente para esta tarefa")
    if datadir.status().reason == "sem_sentinela":
        raise ApiError(503, "hd_indisponivel", "O HD de dados não está montado")
    link = midia.link("mercado_bruto", comum.item_uuid(item.id), ttl=midia.LINK_TTL)
    return schemas.BrutoLinkOut(link=schemas.ColetaLinkOut(url=link.url, expires_at=link.expires_at),
                                bytes=item.bruto_bytes, esquema_versao=item.esquema_versao,
                                data_local=item.data_local,
                                turno=item.turno.value if item.turno else None)


def coleta_out(coleta: Coleta) -> schemas.ColetaOut:
    return schemas.ColetaOut.model_validate(coleta)


def _hoje(mercado: str) -> date:
    return mercados.hoje(mercado)
