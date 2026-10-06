"""Confirmar a importação (research R8): validar, registrar e gravar numa tarefa de fundo.

1. A rota valida as escolhas contra a prévia (sem consumir), consome (`GETDEL`), cria a
   importação `processando` (histórico `created`) e responde 202.
2. A tarefa de fundo (sessão própria) reconfere o dono, as impressões digitais dos arquivos e o HD
   para o total; depois aplica os itens marcados pelos services de domínio, **numa transação só**,
   sob `history.origem_importacao` (autor = o dono; `details.importacao` com a origem). Cada item
   roda num SAVEPOINT: um erro de regra do service (`ApiError`) vira `nao_gravado` com o motivo e o
   resto segue; um erro inesperado desfaz tudo e a importação fica `falhou`. Arquivos já gravados
   no MinIO ficam sem referência (o armazenamento não tem delete; Complexity Tracking).
3. Uma importação `processando` sem avanço há 10 min (a API reiniciou) vira `falhou` ao ser lida.
"""

import io
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sociman_api import datadir, history
from sociman_api.agencia import pastas, previa, schemas
from sociman_api.agencia.itens import Item, motivo_texto
from sociman_api.agencia.models import (
    ENTITY_TYPE,
    Importacao,
    ImportacaoEstado,
    ImportacaoItem,
    ItemResultado,
)
from sociman_api.anotacoes import schemas as anotacoes_schemas
from sociman_api.anotacoes import service as anotacoes
from sociman_api.anotacoes.models import Anotacao, AnotacaoAlvo, AnotacaoTipo
from sociman_api.assets import schemas as assets_schemas
from sociman_api.assets import service as assets
from sociman_api.assets.models import Asset, AssetTipo, FileRole
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User, UserRole
from sociman_api.canais import schemas as canais_schemas
from sociman_api.canais import service_canais
from sociman_api.canais.models import CanalDireito, CanalFonte
from sociman_api.conteudos import video_proprio
from sociman_api.db import get_sessionmaker
from sociman_api.errors import ApiError
from sociman_api.ia import guia as guia_dominio
from sociman_api.ia import schemas_guia, service_guia
from sociman_api.ia.models import IaGuia
from sociman_api.perfis import schemas as perfis_schemas
from sociman_api.perfis import service_contas, service_imagens, service_perfis
from sociman_api.perfis.models import Conta, ContaStatus, ImageKind, Perfil, Platform
from sociman_api.perfis.schemas import UserRef

log = logging.getLogger(__name__)

INTERROMPIDA_APOS = timedelta(minutes=10)
SISTEMA = Actor(kind="system:importacao")
INVALIDA = "Escolha inválida"
MODELOS: dict[str, Any] = {"perfil": Perfil, "canal": CanalFonte, "asset": Asset,
                           "ia_guia": IaGuia, "anotacao": Anotacao, "conta": Conta}


def fabrica_youtube() -> Callable[[], Any]:
    """Dependência: a fábrica do cliente do YouTube da 006 (os testes trocam por um fake)."""
    return service_canais.youtube.novo_cliente


# ---- leitura e interrompidas ----

def marcar_interrompidas(db: Session, agora: datetime | None = None) -> None:
    limite = (agora or datetime.now(UTC)) - INTERROMPIDA_APOS
    paradas = db.scalars(select(Importacao).where(
        Importacao.estado == ImportacaoEstado.processando, Importacao.progresso_em < limite)
        .with_for_update(skip_locked=True)).all()
    for imp in paradas:
        _fechar_falha(db, imp, SISTEMA, motivo_texto("interrompida") or "interrompida")
    if paradas:
        db.flush()


def processando(db: Session) -> Importacao | None:
    marcar_interrompidas(db)
    return db.scalar(select(Importacao).where(Importacao.estado == ImportacaoEstado.processando))


def _fechar_falha(db: Session, imp: Importacao, actor: Actor, erro: str) -> None:
    antes = history.snapshot(imp)
    imp.estado = ImportacaoEstado.falhou
    imp.erro = erro
    imp.progresso = {**(imp.progresso or {}), "etapa": "fim"}
    imp.updated_by = actor.user_id
    history.record(db, actor, ENTITY_TYPE, imp, "updated", antes, history.snapshot(imp),
                   {"acao": "falhou"})


# ---- validação das escolhas ----

def decisao(item: Item, escolha: dict[str, Any]) -> str | None:
    """`aplicar`, `manter` ou None (item sem escolha: igual, fora, sugestão)."""
    if item.situacao == "novo":
        return "aplicar" if escolha.get("marcado", True) is not False else "manter"
    if item.situacao == "diverge" and item.motivo != "arquivado":
        return "aplicar" if escolha.get("usar") == "markdown" else "manter"
    return None


def _invalida(n: int, motivo: str) -> ApiError:
    return ApiError(422, "escolha_invalida", f"{INVALIDA} no item {n}: {motivo}",
                    details={"n": n})


def validar(estado: dict[str, Any], body: schemas.AgenciaConfirmar
            ) -> tuple[list[Item], dict[int, dict[str, Any]], str | None]:
    itens = [Item.de_json(d) for d in estado["itens"]]
    por_n = {i.n: i for i in itens}
    escolhas: dict[int, dict[str, Any]] = {}
    for e in body.escolhas:
        item = por_n.get(e.n)
        if item is None:
            raise _invalida(e.n, "não existe na pré-visualização")
        dados = e.model_dump(exclude_none=True, exclude={"n"})
        if not dados:
            raise _invalida(e.n, "sem escolha")
        if e.marcado is not None and item.situacao != "novo":
            raise _invalida(e.n, "\"marcado\" só vale para item novo")
        if e.usar is not None and not (item.situacao == "diverge" and item.motivo != "arquivado"):
            raise _invalida(e.n, "\"usar\" só vale para item que diverge")
        if e.direito is not None and not (item.tipo == "canal" and (
                item.situacao == "novo" or (item.situacao == "diverge"
                                            and item.motivo == "direito"))):
            raise _invalida(e.n, "\"direito\" só vale para canal novo ou com direito diferente")
        escolhas[e.n] = dados
    persona = estado.get("persona") or {}
    perfil_persona = body.persona_perfil
    exige = [i for i in itens if i.exige_perfil and decisao(i, escolhas.get(i.n, {})) == "aplicar"]
    if exige:
        possiveis = {i.perfil_slug for i in itens if i.tipo == "perfil" and (
            i.situacao in ("igual", "diverge") and i.motivo != "arquivado"
            or i.situacao == "novo" and decisao(i, escolhas.get(i.n, {})) == "aplicar")}
        if perfil_persona is None or perfil_persona not in possiveis | _perfis_ativos(estado):
            raise _invalida(exige[0].n, "escolha o perfil da persona (personaPerfil)")
    elif perfil_persona is not None and perfil_persona != persona.get("perfil_padrao"):
        raise ApiError(422, "escolha_invalida",
                       f"{INVALIDA}: a persona já está no perfil {persona.get('perfil_padrao')}")
    return itens, escolhas, perfil_persona


def _perfis_ativos(estado: dict[str, Any]) -> set[str]:
    return set(estado.get("perfisAtivos") or [])


# ---- confirmar ----

def confirmar(db: Session, actor: Actor, body: schemas.AgenciaConfirmar) -> tuple[Importacao, dict]:
    """Cria a importação `processando`. Devolve (importação, plano da tarefa de fundo)."""
    estado = previa.ler_estado(body.previa_id, actor)
    estado["perfisAtivos"] = [p.slug for p in db.scalars(
        select(Perfil).where(Perfil.archived_at.is_(None)))]
    itens, escolhas, persona_perfil = validar(estado, body)
    previa.consumir(body.previa_id)
    if processando(db) is not None:
        raise ApiError(409, "importacao_em_andamento",
                       "Já há uma importação em andamento; espere ela terminar")
    imp = Importacao(raiz_shared=estado["raizes"]["shared"], raiz_clipes=estado["raizes"]["clipes"],
                     arquivos=estado["arquivos"], criada_por=actor.user_id,
                     progresso={"etapa": "conferindo", "feitos": 0, "total": 0, "bytes": 0},
                     created_by=actor.user_id, updated_by=actor.user_id)
    db.add(imp)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:  # outra confirmação ganhou a corrida (índice único parcial)
        raise ApiError(409, "importacao_em_andamento",
                       "Já há uma importação em andamento; espere ela terminar") from exc
    history.record(db, actor, ENTITY_TYPE, imp, "created", None, history.snapshot(imp),
                   {"previaId": str(body.previa_id), "itens": len(itens)})
    db.flush()
    db.refresh(imp)
    plano = {"importacao_id": str(imp.id), "user_id": str(actor.user_id),
             "itens": [i.json() for i in itens],
             "escolhas": {str(n): e for n, e in escolhas.items()},
             "persona_perfil": persona_perfil}
    return imp, plano


# ---- tarefa de fundo ----

@dataclass
class Aplicador:
    db: Session
    actor: Actor
    importacao_id: uuid.UUID
    youtube: Callable[[], Any] | None
    persona_perfil: str | None
    perfis: dict[str, uuid.UUID] = field(default_factory=dict)  # slug → id
    assets: dict[str, uuid.UUID] = field(default_factory=dict)  # chave do item → asset criado
    esperado: dict[str, int] = field(default_factory=dict)  # "<tipo>:<id>" → versão atual
    _cliente: Any = None

    def cliente(self) -> Any:
        if self._cliente is None:
            if self.youtube is None:
                raise ApiError(503, "youtube_unconfigured", "YouTube indisponível")
            self._cliente = self.youtube()
        return self._cliente

    def perfil_id(self, slug: str | None) -> uuid.UUID:
        pid = self.perfis.get(slug or "")
        if pid is None:
            raise _Pular("perfil_nao_importado")
        return pid


class _Pular(Exception):
    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def _ler(arquivo: str) -> bytes:
    raiz, _, rel = arquivo.partition(":")
    path = pastas.raiz_path(raiz) / rel  # type: ignore[arg-type]
    with path.open("rb") as f:
        return f.read()


def _caminho(arquivo: str):
    raiz, _, rel = arquivo.partition(":")
    return pastas.raiz_path(raiz) / rel  # type: ignore[arg-type]


Entidade = tuple[str, uuid.UUID, int, str]  # (entity_type, id, versão, criado|atualizado)


def _perfil(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    d = item.dados
    if item.situacao == "novo":
        p = service_perfis.create_perfil(ap.db, ap.actor, perfis_schemas.CreatePerfilIn(
            name=d["name"], slug=d["slug"], niche=d["niche"], language=d["language"],
            status=d["status"]))
        ap.perfis[d["slug"]] = p.id
        return "perfil", p.id, p.version, "criado"
    atual = ap.db.get(Perfil, ap.perfil_id(item.perfil_slug))
    p = service_perfis.update_perfil(ap.db, ap.actor, atual.id, perfis_schemas.UpdatePerfilIn(  # type: ignore[union-attr]
        version=atual.version, name=d["name"], niche=d["niche"], language=d["language"],  # type: ignore[union-attr]
        status=d["status"]))
    return "perfil", p.id, p.version, "atualizado"


def _conta(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    d = item.dados
    pid = ap.perfil_id(item.perfil_slug)
    if ap.db.scalar(select(Conta.id).where(Conta.platform == d["platform"],
                                           Conta.platform_name == "",
                                           Conta.handle == d["handle"])) is not None:
        raise ApiError(409, "handle_in_use", "Esse @ já está cadastrado")
    ativa = ap.db.scalar(select(Conta.id).where(
        Conta.perfil_id == pid, Conta.platform == d["platform"], Conta.platform_name == "",
        Conta.status == ContaStatus.ativa, Conta.archived_at.is_(None)))
    c = service_contas.create_conta(ap.db, ap.actor, pid, perfis_schemas.CreateContaIn(
        platform=Platform(d["platform"]), handle=d["handle"], url=d["url"],
        status=ContaStatus.planejada if ativa else ContaStatus.ativa))
    return "conta", c.id, c.version, "criado"


def _guia(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    pid = ap.perfil_id(item.perfil_slug)
    row = guia_dominio.linha(ap.db, pid, None)
    atual = guia_dominio.GuiaCampos.de_linha(row) if row is not None else guia_dominio.GuiaCampos()
    criado = row is None or atual.vazio
    d = item.dados
    from dataclasses import replace

    novo = replace(atual, tom=d["tom"], vocabulario=tuple(d["vocabulario"]),
                   nao_faca=tuple(d["naoFaca"]))
    service_guia.put_perfil(ap.db, ap.actor, pid, schemas_guia.GuiaIn(
        version=row.version if row is not None else 0,
        campos=schemas_guia.GuiaCampos.de_dominio(novo)))
    row = guia_dominio.linha(ap.db, pid, None)
    if row is None:
        raise ApiError(400, "validation_error", "O guia ficou vazio")
    return "ia_guia", row.id, row.version, "criado" if criado else "atualizado"


def _anotacao(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    if item.situacao == "diverge":
        a = ap.db.get(Anotacao, uuid.UUID(item.dados["anotacao_id"]))
        a = anotacoes.editar(ap.db, ap.actor, a.id, anotacoes_schemas.UpdateAnotacaoIn(  # type: ignore[union-attr]
            version=a.version, texto=item.dados["texto"]))  # type: ignore[union-attr]
        return "anotacao", a.id, a.version, "atualizado"
    a = anotacoes.criar(ap.db, ap.actor, anotacoes_schemas.CreateAnotacaoIn(
        alvo_tipo=AnotacaoAlvo.perfil, alvo_id=ap.perfil_id(item.perfil_slug),
        tipo=AnotacaoTipo.observacao, texto=item.dados["texto"]))
    return "anotacao", a.id, a.version, "criado"


def _logo(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    perfil = ap.db.get(Perfil, ap.perfil_id(item.perfil_slug))
    p = service_imagens.upload_image(ap.db, ap.actor, perfil.id, ImageKind.logo,  # type: ignore[union-attr]
                                     perfil.version, io.BytesIO(_ler(item.dados["arquivo"])))  # type: ignore[union-attr]
    return "perfil", p.id, p.version, "atualizado"


def _slug_asset(ap: Aplicador, item: Item) -> str | None:
    return item.perfil_slug if item.perfil_slug is not None else ap.persona_perfil


def _asset(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    d = item.dados
    if item.situacao == "diverge":
        atual = ap.db.get(Asset, uuid.UUID(d["asset_id"]))
        campos = {k: d.get(k) for k in ("prompt", "voice_tone", "image_rules")
                  if k in d and (k == "prompt" or atual.tipo == AssetTipo.avatar)}  # type: ignore[union-attr]
        a = assets.update_asset(ap.db, ap.actor, atual.id, assets_schemas.AssetPatch(  # type: ignore[union-attr]
            version=atual.version, **campos))  # type: ignore[union-attr]
        return "asset", a.id, a.version, "atualizado"
    pid = ap.perfil_id(_slug_asset(ap, item))
    if "arquivo" in d:  # sticker ou imagem: um arquivo = um asset
        a, _ = assets.upload_asset(ap.db, ap.actor, pid, io.BytesIO(_ler(d["arquivo"])),
                                   AssetTipo(d["tipo"]), d["name"], [])
    else:
        a = assets.create_asset(ap.db, ap.actor, pid, assets_schemas.AssetCreate(
            tipo=AssetTipo(d["tipo"]), name=d["name"], prompt=d.get("prompt"),
            voice_tone=d.get("voice_tone"), image_rules=d.get("image_rules")))
    ap.assets[item.chave] = a.id
    return "asset", a.id, a.version, "criado"


def _arquivo_asset(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    d = item.dados
    asset_id = uuid.UUID(d["asset_id"]) if d.get("asset_id") else ap.assets.get(
        d.get("asset_chave", ""))
    if asset_id is None:
        raise _Pular("perfil_nao_importado" if _slug_asset(ap, item) not in ap.perfis
                     else "asset_nao_criado")
    meta = {k: d[k] for k in ("label", "look", "uso") if d.get(k)}
    a, f = assets.upload_file(ap.db, ap.actor, asset_id, io.BytesIO(_ler(d["arquivo"])),
                              FileRole(d["role"]), meta)
    ap.esperado[f"asset:{a.id}"] = a.version
    return "asset_file", f.id, a.version, "criado"


def _canal(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    d = item.dados
    direito = CanalDireito(escolha.get("direito") or item.direito_proposto)
    if item.situacao == "novo":
        perfil_ids = [ap.perfis[s] for s in d["perfis"] if s in ap.perfis]
        c = service_canais.create_canal(ap.db, ap.actor, ap.cliente(),
                                        canais_schemas.CreateCanalIn(
                                            youtube_channel_id=d["youtube_channel_id"],
                                            perfil_ids=perfil_ids))
        resultado = "criado"
    else:
        c = ap.db.get(CanalFonte, uuid.UUID(d["canal_id"]))
        resultado = "atualizado"
    c = service_canais.mudar_direito(ap.db, ap.actor, c.id, canais_schemas.DireitoIn(  # type: ignore[union-attr]
        version=c.version, direito=direito, evidencia_url=d.get("evidencia_url"),  # type: ignore[union-attr]
        evidencia_nota=d["evidencia_nota"]))
    return "canal", c.id, c.version, resultado


def _vinculo(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    pid = ap.perfil_id(item.perfil_slug)
    c = ap.db.get(CanalFonte, uuid.UUID(item.dados["canal_id"]))
    ligados = [link.perfil_id for link in c.perfil_links]  # type: ignore[union-attr]
    c = service_canais.update_canal(ap.db, ap.actor, c.id, canais_schemas.UpdateCanalIn(  # type: ignore[union-attr]
        version=c.version, perfil_ids=[*ligados, pid]))  # type: ignore[union-attr]
    return "canal", c.id, c.version, "atualizado"


def _clipe(ap: Aplicador, item: Item, escolha: dict) -> Entidade:
    d = item.dados
    pid = ap.perfil_id(item.perfil_slug)
    c = video_proprio.create_de_arquivo(ap.db, ap.actor, pid, _caminho(d["arquivo"]),
                                        d["filename"], d["titulo"], d["size"], d["sha256"])
    anotacoes.criar(ap.db, ap.actor, anotacoes_schemas.CreateAnotacaoIn(
        alvo_tipo=AnotacaoAlvo.conteudo, alvo_id=c.id, tipo=AnotacaoTipo.observacao,
        texto=d["nota"]))
    return "conteudo", c.id, c.version, "criado"


APLICADORES: dict[str, Callable[[Aplicador, Item, dict], Entidade]] = {
    "perfil": _perfil, "conta": _conta, "guia": _guia, "anotacao": _anotacao,
    "imagem_logo": _logo, "asset": _asset, "arquivo_asset": _arquivo_asset, "canal": _canal,
    "vinculo_canal": _vinculo, "clipe": _clipe,
}


def _versao_atual(db: Session, chave: str) -> int | None:
    tipo, _, ident = chave.partition(":")
    obj = db.get(MODELOS[tipo], uuid.UUID(ident)) if tipo in MODELOS else None
    if obj is not None:
        db.refresh(obj)
    return obj.version if obj is not None else None


def _aplicar_item(ap: Aplicador, item: Item, escolha: dict, mudaram: set[str]
                  ) -> tuple[str, str | None, tuple[str, uuid.UUID, int] | None]:
    """(resultado, resultado_motivo, entidade)."""
    if item.situacao == "igual":
        return "igual", None, None
    if item.situacao == "sugestao":
        return "sugestao", None, None
    if item.situacao in ("fora", "aguardando_cota"):
        return "fora", None, None
    if decisao(item, escolha) != "aplicar":
        return "mantido", None, None
    if item.arquivo in mudaram or any(o["arquivo"] in mudaram for o in item.origens):
        return "nao_gravado", "mudou_desde_a_leitura", None
    for chave, lida in item.base.items():
        if _versao_atual(ap.db, chave) != ap.esperado.get(chave, lida):
            return "nao_gravado", "editado_desde_a_leitura", None
    origem = {"id": str(ap.importacao_id), "arquivo": item.arquivo, "trecho": item.trecho}
    try:
        with ap.db.begin_nested(), history.origem_importacao(origem):
            etype, eid, versao, resultado = APLICADORES[item.tipo](ap, item, escolha)
    except _Pular as p:
        return "nao_gravado", p.motivo, None
    except ApiError as e:
        if not ap.db.in_transaction():  # um service fez rollback da transação inteira
            raise RuntimeError("a transação da importação foi desfeita no meio") from e
        return "nao_gravado", e.message[:500], None
    if etype != "asset_file":
        ap.esperado[f"{etype}:{eid}"] = versao
    return resultado, None, (etype, eid, versao)


def _progresso(importacao_id: uuid.UUID, **valores: Any) -> None:
    """Commit curto, numa sessão própria (a transação do domínio continua aberta)."""
    s = get_sessionmaker()()
    try:
        s.execute(update(Importacao).where(Importacao.id == importacao_id).values(
            progresso=valores, progresso_em=datetime.now(UTC)))
        s.commit()
    finally:
        s.close()


def _falhar(importacao_id: uuid.UUID, actor: Actor, erro: str) -> None:
    s = get_sessionmaker()()
    try:
        imp = s.get(Importacao, importacao_id, with_for_update=True)
        if imp is not None and imp.estado == ImportacaoEstado.processando:
            _fechar_falha(s, imp, actor, erro)
            s.commit()
    finally:
        s.close()


def _mudaram(arquivos: dict[str, str]) -> set[str]:
    out = set()
    for arquivo, sha in arquivos.items():
        try:
            if pastas.sha256_arquivo(_caminho(arquivo)) != sha:
                out.add(arquivo)
        except OSError:
            out.add(arquivo)
    return out


def executar(plano: dict[str, Any], youtube: Callable[[], Any] | None) -> None:
    """A tarefa de fundo da confirmação (BackgroundTasks)."""
    imp_id = uuid.UUID(plano["importacao_id"])
    db = get_sessionmaker()()
    ator_falha = SISTEMA
    ap: Aplicador | None = None
    try:
        user = db.get(User, uuid.UUID(plano["user_id"]))
        if user is None or not user.is_active or user.role != UserRole.dono:
            _falhar(imp_id, SISTEMA, motivo_texto("dono_inativo") or "dono_inativo")
            return
        actor = Actor(kind="user", user_id=user.id, user=user)
        ator_falha = actor
        itens = [Item.de_json(d) for d in plano["itens"]]
        escolhas = {int(n): e for n, e in plano["escolhas"].items()}
        imp = db.get(Importacao, imp_id)
        _progresso(imp_id, etapa="conferindo", feitos=0, total=len(imp.arquivos), bytes=0)  # type: ignore[union-attr]
        mudaram = _mudaram(imp.arquivos)  # type: ignore[union-attr]
        aplicar = [i for i in itens if decisao(i, escolhas.get(i.n, {})) == "aplicar"]
        a_aplicar = {i.n for i in aplicar}
        total_bytes = sum(i.bytes or 0 for i in aplicar if i.arquivo not in mudaram)
        if total_bytes:
            try:
                datadir.ensure_writable(total_bytes)
            except ApiError as e:
                _falhar(imp_id, actor, e.message)
                return
        ap = Aplicador(db, actor, imp_id, youtube, plano.get("persona_perfil"),
                       perfis={p.slug: p.id for p in db.scalars(
                           select(Perfil).where(Perfil.archived_at.is_(None)))})
        feitos = gravados = 0
        _progresso(imp_id, etapa="gravando", feitos=0, total=len(aplicar), bytes=0)
        for ordem, item in enumerate(itens, 1):
            escolha = escolhas.get(item.n, {})
            resultado, motivo, entidade = _aplicar_item(ap, item, escolha, mudaram)
            db.add(ImportacaoItem(
                importacao_id=imp_id, ordem=ordem, tipo=item.tipo, perfil_slug=item.perfil_slug,
                arquivo=item.arquivo, trecho=item.trecho[:500], linha=item.linha,
                chave=item.chave, impressao=item.impressao, situacao=item.situacao,
                motivo=item.motivo, escolha=escolha, resultado=ItemResultado(resultado),
                resultado_motivo=motivo, entity_type=entidade[0] if entidade else None,
                entity_id=entidade[1] if entidade else None,
                entity_version=entidade[2] if entidade else None))
            if item.n in a_aplicar:
                feitos += 1
                if resultado in ("criado", "atualizado"):
                    gravados += item.bytes or 0
                if item.bytes or feitos % 20 == 0:
                    _progresso(imp_id, etapa="gravando", feitos=feitos, total=len(aplicar),
                               bytes=gravados)
        db.flush()
        imp = db.get(Importacao, imp_id, with_for_update=True)
        db.refresh(imp)
        antes = history.snapshot(imp)
        imp.estado = ImportacaoEstado.concluida  # type: ignore[union-attr]
        imp.contagens = _contagens(db, imp_id)  # type: ignore[union-attr]
        imp.concluida_em = datetime.now(UTC)  # type: ignore[union-attr]
        imp.progresso = {"etapa": "fim", "feitos": feitos, "total": len(aplicar),  # type: ignore[union-attr]
                         "bytes": gravados}
        imp.updated_by = actor.user_id  # type: ignore[union-attr]
        history.record(db, actor, ENTITY_TYPE, imp, "updated", antes, history.snapshot(imp),
                       {"acao": "concluida"})
        db.commit()
        log.info("agencia importacao %s concluida: %s", imp_id, imp.contagens)  # type: ignore[union-attr]
    except Exception:
        db.rollback()
        log.exception("agencia importacao %s falhou", imp_id)
        _falhar(imp_id, ator_falha, "Erro inesperado ao gravar; nada foi gravado no SociMan")
    finally:
        if ap is not None and ap._cliente is not None:
            ap._cliente.close()
        db.close()


def _contagens(db: Session, imp_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(select(ImportacaoItem.resultado).where(
        ImportacaoItem.importacao_id == imp_id)).scalars().all()
    out = schemas.AgenciaContagensImportacao()
    for r in rows:
        setattr(out, r.value, getattr(out, r.value) + 1)
    return out.model_dump()


# ---- saída ----

def importacao_or_404(db: Session, importacao_id: uuid.UUID, lock: bool = False) -> Importacao:
    imp = db.get(Importacao, importacao_id, with_for_update=lock)
    if imp is None:
        raise ApiError(404, "not_found", "Importação não encontrada")
    return imp


def _refs(db: Session, ids: list[uuid.UUID | None]) -> dict[uuid.UUID, UserRef]:
    return service_perfis.user_refs(db, ids)


def resumo_out(db: Session, imp: Importacao, users: dict[uuid.UUID, UserRef] | None = None
               ) -> schemas.AgenciaImportacaoResumo:
    users = users if users is not None else _refs(db, [imp.criada_por, imp.desfeita_por])
    return schemas.AgenciaImportacaoResumo(
        id=imp.id, version=imp.version, estado=imp.estado.value,  # type: ignore[arg-type]
        criada_em=imp.criada_em, criada_por=users.get(imp.criada_por),
        concluida_em=imp.concluida_em, desfeita_em=imp.desfeita_em,
        desfeita_por=users.get(imp.desfeita_por) if imp.desfeita_por else None, erro=imp.erro,
        progresso=schemas.AgenciaProgresso(**(imp.progresso or {})),
        contagens=schemas.AgenciaContagensImportacao(**(imp.contagens or {})),
        arquivos=len(imp.arquivos or {}))


def importacao_out(db: Session, imp: Importacao, situacao: str | None = None,
                   tipo: str | None = None, perfil: str | None = None) -> schemas.AgenciaImportacao:
    stmt = select(ImportacaoItem).where(ImportacaoItem.importacao_id == imp.id)
    if situacao:
        stmt = stmt.where(ImportacaoItem.situacao == situacao)
    if tipo:
        stmt = stmt.where(ImportacaoItem.tipo == tipo)
    if perfil:
        stmt = stmt.where(ImportacaoItem.perfil_slug == perfil)
    rows = db.scalars(stmt.order_by(ImportacaoItem.ordem)).all()
    return schemas.AgenciaImportacao(**resumo_out(db, imp).model_dump(), itens=[
        schemas.AgenciaItemImportacao(
            n=r.ordem, tipo=r.tipo, perfil_slug=r.perfil_slug,  # type: ignore[arg-type]
            origem=schemas.AgenciaOrigem(arquivo=r.arquivo, trecho=r.trecho, linha=r.linha),
            situacao=r.situacao, motivo=r.motivo, motivo_texto=motivo_texto(r.motivo),  # type: ignore[arg-type]
            escolha=r.escolha, resultado=r.resultado.value,  # type: ignore[arg-type]
            resultado_motivo=r.resultado_motivo,
            resultado_texto=motivo_texto(r.resultado_motivo),
            entidade=schemas.AgenciaEntidade(tipo=r.entity_type, id=r.entity_id,
                                      version=r.entity_version)
            if r.entity_type and r.entity_id else None,
            desfeito_em=r.desfeito_em, desfazer_motivo=r.desfazer_motivo,
            desfazer_texto=motivo_texto(r.desfazer_motivo))
        for r in rows])


def listar(db: Session) -> schemas.AgenciaImportacoesList:
    marcar_interrompidas(db)
    imps = db.scalars(select(Importacao).order_by(Importacao.criada_em.desc(),
                                                  Importacao.id.desc())).all()
    users = _refs(db, [u for i in imps for u in (i.criada_por, i.desfeita_por)])
    return schemas.AgenciaImportacoesList(items=[resumo_out(db, i, users) for i in imps])


def obter(db: Session, importacao_id: uuid.UUID, situacao: str | None, tipo: str | None,
          perfil: str | None) -> schemas.AgenciaImportacao:
    marcar_interrompidas(db)
    return importacao_out(db, importacao_or_404(db, importacao_id), situacao, tipo, perfil)
