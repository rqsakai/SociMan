"""Gerar, descartar, registro e resumo (spec 008, US1 e US3; research R5, R8, R9).

- `gerar` valida tipo × alvo × perfil, o `valorAtual` e a seleção pelo formato, carrega as
  anteriores pelo id (mesmo autor, sessão, tipo e alvo), monta o contexto e o prompt, chama o
  Claude e **grava sempre** a chamada, inclusive com erro (commit antes de levantar, como o
  `_deny` da auth, porque o `get_db` faz rollback quando a rota levanta).
- Gerar **não muda nenhuma entidade** (princípio VII): quem salva é o save de cada tela, no
  clique humano, com o campo `ia` (`ia/aplicacao.py`).
- `executar` é a parte comum, usada também pelas rotas da 006 (`postagem.textos`).
"""

import base64
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.cortes.models import Corte
from sociman_api.errors import ApiError
from sociman_api.ia import contexto as ctx_mod
from sociman_api.ia import prompt, saida, schemas
from sociman_api.ia.cliente import IaClient, Resultado
from sociman_api.ia.custo import PRECOS_VERSAO
from sociman_api.ia.models import IaChamada, IaDesfecho, IaRegra
from sociman_api.ia.tipos import TIPOS, TipoCampo
from sociman_api.perfis.models import Conta, Perfil
from sociman_api.perfis.service_perfis import get_perfil_or_404, user_refs

MARGEM_VALOR_ATUAL = 1.5  # o texto colado que o usuário quer encurtar


def invalid(message: str) -> ApiError:
    return ApiError(400, "invalid_ia", message)


def tipo_or_404(tipo_campo: str) -> TipoCampo:
    tipo = TIPOS.get(tipo_campo)
    if tipo is None:
        raise ApiError(404, "ia_tipo_not_found", "Tipo de campo não encontrado")
    return tipo


# ---- alvo ----

@dataclass(frozen=True)
class AlvoResolvido:
    entity_type: str  # asset | perfil | kit | postagem | corte
    entity_id: uuid.UUID | None
    asset: Asset | None = None
    corte: Corte | None = None
    conta: Conta | None = None
    postagem: Any | None = None


def _arquivado(nome: str) -> ApiError:
    return ApiError(409, "conflict", f"{nome} está arquivad{'a' if nome.startswith('Esta') else 'o'}")


def _resolver_alvo(db: Session, tipo: TipoCampo, perfil: Perfil,
                   alvo: schemas.Alvo) -> AlvoResolvido:
    """Confere que o alvo existe, é do perfil e casa com o tipo (400 `invalid_ia` senão)."""
    et, eid = alvo.entity_type, alvo.entity_id
    if tipo.entidade == "asset":
        if et != "asset" or eid is None:
            raise invalid("Este campo é de um asset")
        asset = db.get(Asset, eid)
        if asset is None:
            raise ApiError(404, "not_found", "Asset não encontrado")
        if asset.perfil_id != perfil.id:
            raise invalid("O asset é de outro perfil")
        if tipo.tipos_asset is not None and asset.tipo.value not in tipo.tipos_asset:
            raise invalid(f"O campo {tipo.rotulo} não existe num asset do tipo "
                          f"{asset.tipo.value}")
        if asset.archived:
            raise _arquivado("Este asset")
        return AlvoResolvido("asset", asset.id, asset=asset)
    if tipo.entidade == "perfil":
        if et != "perfil" or eid != perfil.id:
            raise invalid("Este campo é do próprio perfil")
        return AlvoResolvido("perfil", perfil.id)
    if tipo.entidade == "kit":
        from sociman_api.marca.service_kit import current_tokens  # import tardio (ciclo)

        if et != "kit":
            raise invalid("Este campo é do kit de marca")
        _, row = current_tokens(db, perfil.id)
        kit_id = row.id if row is not None else None
        if eid is not None and eid != kit_id:
            raise invalid("O kit é de outro perfil")
        return AlvoResolvido("kit", kit_id)
    return _resolver_postagem(db, perfil, alvo)


def _resolver_postagem(db: Session, perfil: Perfil, alvo: schemas.Alvo) -> AlvoResolvido:
    from sociman_api.postagem.models import Postagem  # import tardio (ciclo)

    if alvo.entity_type == "postagem" and alvo.entity_id is not None:
        postagem = db.get(Postagem, alvo.entity_id)
        if postagem is None:
            raise ApiError(404, "not_found", "Postagem não encontrada")
        corte = db.get(Corte, postagem.corte_id)
        conta = db.get(Conta, postagem.conta_id)
        assert corte is not None and conta is not None
        if corte.perfil_id != perfil.id:
            raise invalid("A postagem é de outro perfil")
        if postagem.archived:
            raise _arquivado("Esta postagem")
        return AlvoResolvido("postagem", postagem.id, corte=corte, conta=conta,
                             postagem=postagem)
    if alvo.entity_type != "corte" or alvo.entity_id is None or alvo.conta_id is None:
        raise invalid("Este campo é de uma postagem (ou de um corte com a conta de destino)")
    corte = db.get(Corte, alvo.entity_id)
    if corte is None:
        raise ApiError(404, "not_found", "Corte não encontrado")
    conta = db.get(Conta, alvo.conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    if corte.perfil_id != perfil.id or conta.perfil_id != perfil.id:
        raise invalid("O corte e a conta precisam ser do perfil")
    if corte.archived:
        raise _arquivado("Este corte")
    if conta.archived:
        raise _arquivado("Esta conta")
    return AlvoResolvido("corte", corte.id, corte=corte, conta=conta)


# ---- valor atual e seleção ----

def _limite(valor: int | None) -> int | None:
    return int(valor * MARGEM_VALOR_ATUAL) if valor else None


def _valor_atual(tipo: TipoCampo, valor: schemas.Valor) -> dict[str, Any]:
    dados = valor.model_dump(exclude_none=True)
    lim = tipo.limites
    permitidos = {"texto": {"texto"}, "lista": {"itens"}, "sugestoes": {"itens"},
                  "textos_postagem": {"titulo", "descricao", "hashtags"}}[tipo.formato]
    if set(dados) - permitidos:
        raise invalid(f"valorAtual: este campo aceita só {', '.join(sorted(permitidos))}")
    maximo = _limite(lim.max_chars)
    for chave in ("texto", "titulo"):
        if maximo and len(dados.get(chave) or "") > maximo:
            raise invalid(f"valorAtual: o texto passa de {maximo} caracteres")
    if len(dados.get("descricao") or "") > 3000:
        raise invalid("valorAtual: a descrição passa de 3000 caracteres")
    max_itens, max_item = _limite(lim.max_itens), _limite(lim.max_chars_item)
    for chave in ("itens", "hashtags"):
        itens = dados.get(chave) or []
        if max_itens and len(itens) > max_itens:
            raise invalid(f"valorAtual: são mais de {max_itens} itens")
        if max_item and any(len(i) > max_item for i in itens):
            raise invalid(f"valorAtual: um item passa de {max_item} caracteres")
    return dados


def _selecao(tipo: TipoCampo, selecao: schemas.Selecao | None) -> tuple[list[str], list[str]]:
    if selecao is None:
        return [], []
    if tipo.formato != "sugestoes":
        if selecao.aceitos or selecao.rejeitados:
            raise invalid("A seleção só vale nos campos com sugestões (bordões e séries)")
        return [], []
    limite = tipo.limites.max_chars_item
    for item in (*selecao.aceitos, *selecao.rejeitados):
        if not item.strip() or (limite and len(item.strip()) > limite):
            raise invalid(f"Seleção: cada item precisa ter de 1 a {limite} caracteres")
    return [i.strip() for i in selecao.aceitos], [i.strip() for i in selecao.rejeitados]


def _anteriores(db: Session, actor: Actor, tipo: TipoCampo, perfil: Perfil,
                alvo: AlvoResolvido, sessao_id: uuid.UUID,
                ids: Sequence[uuid.UUID]) -> list[IaChamada]:
    if not ids:
        return []
    rows = {c.id: c for c in db.scalars(select(IaChamada).where(IaChamada.id.in_(set(ids))))}
    out = []
    for cid in dict.fromkeys(ids):
        c = rows.get(cid)
        mesmo_alvo = c is not None and c.entity_type == alvo.entity_type and (
            c.entity_id == alvo.entity_id or (alvo.entity_type == "kit" and c.entity_id is None))
        if (c is None or not mesmo_alvo or c.created_by != actor.user_id
                or c.sessao_id != sessao_id or c.tipo_campo != tipo.id
                or c.perfil_id != perfil.id
                or (alvo.conta is not None and c.conta_id != alvo.conta.id)):
            raise ApiError(400, "ia_anteriores_invalidas",
                           "As versões anteriores precisam ser desta sessão, deste campo e sua")
        out.append(c)
    return out


# ---- regras ----

@dataclass(frozen=True)
class RegrasEmVigor:
    texto: str
    version: int  # 0 = padrão (nunca editada)
    padrao_versao: int | None  # quando usou o padrão


def regras_em_vigor(db: Session, tipo: TipoCampo) -> RegrasEmVigor:
    row = db.scalar(select(IaRegra).where(IaRegra.tipo_campo == tipo.id))
    if row is None:
        return RegrasEmVigor(tipo.padrao, 0, tipo.padrao_versao)
    if row.texto is None:
        return RegrasEmVigor(tipo.padrao, row.version, tipo.padrao_versao)
    return RegrasEmVigor(row.texto, row.version, None)


# ---- gerar ----

_AVISOS_FALTANTE = {
    "kit": "O perfil não tem kit salvo; usei só o nome, o nicho e a bio.",
    "persona": "O perfil não tem avatar; escrevi sem a persona.",
}

_ERROS: dict[str, tuple[int, str, str]] = {
    "timeout": (504, "ia_timeout", "A IA demorou demais; tente de novo"),
    "refusal": (502, "ia_recusa", "A IA não fez uma proposta para este campo; escreva à mão"),
    "invalid": (502, "ia_invalida",
                "A IA devolveu uma resposta fora do formato; tente de novo ou escreva à mão"),
}


def _erro_api(status: int | None) -> ApiError:
    if status in (401, 403):
        msg = "A chave do Claude foi recusada; confira a ANTHROPIC_API_KEY"
    elif status == 429:
        msg = "O Claude está com muitas chamadas agora; tente em instantes"
    else:
        msg = "O Claude não respondeu; tente de novo"
    return ApiError(502, "claude_error", msg)


def executar(db: Session, actor: Actor, tipo: TipoCampo, perfil: Perfil, alvo: AlvoResolvido,
             valor_atual: dict[str, Any], instrucao: str, client: IaClient | None, *,
             sessao_id: uuid.UUID | None = None, anteriores: Sequence[IaChamada] = (),
             aceitos: Sequence[str] = (), rejeitados: Sequence[str] = ()) -> IaChamada:
    """Monta o contexto, chama o Claude e grava a chamada. Com erro, commita e levanta."""
    regras = regras_em_vigor(db, tipo)
    contexto = ctx_mod.montar(db, tipo, perfil, asset=alvo.asset, corte=alvo.corte,
                              conta=alvo.conta, postagem=alvo.postagem)
    row = IaChamada(
        id=uuid.uuid4(), tipo_campo=tipo.id, perfil_id=perfil.id,
        entity_type=alvo.entity_type, entity_id=alvo.entity_id,
        corte_id=alvo.corte.id if alvo.corte is not None else None,
        conta_id=alvo.conta.id if alvo.conta is not None else None,
        plataforma=alvo.conta.platform if alvo.conta is not None else None,
        sessao_id=sessao_id, anteriores=[a.id for a in anteriores], aceitos=list(aceitos),
        rejeitados=list(rejeitados), instrucao=instrucao, entrada=valor_atual or None,
        contexto_faltante=list(contexto.faltante), prompt_version=prompt.PROMPT_VERSION,
        regras_version=regras.version, padrao_versao=regras.padrao_versao,
        created_by=actor.user_id,
    )
    if client is None:
        row.model, row.duration_ms = get_settings().textos_model, 0
        row.erro_code, row.desfecho = "unconfigured", IaDesfecho.erro
        db.add(row)
        db.commit()
        raise ApiError(503, "claude_unconfigured",
                       "O Claude não está configurado (ANTHROPIC_API_KEY); escreva à mão")

    system = prompt.montar_system(tipo, regras.texto, contexto)
    propostas = [a.proposta for a in anteriores if a.proposta]
    excluir = saida.Excluir(atuais=tuple(valor_atual.get("itens") or ()),
                            aceitos=tuple(aceitos), rejeitados=tuple(rejeitados))
    res = client.gerar(tipo, system, lambda erro: prompt.montar_user(
        tipo, contexto, valor_atual, instrucao, propostas, aceitos, rejeitados, erro), excluir)
    _preencher(row, res, contexto.faltante)
    db.add(row)
    if res.erro_code is not None:
        db.commit()
        if res.erro_code in _ERROS:
            status, code, msg = _ERROS[res.erro_code]
            raise ApiError(status, code, msg)
        raise _erro_api(res.erro_status)
    db.flush()
    db.refresh(row)
    return row


def _preencher(row: IaChamada, res: Resultado, faltante: Sequence[str]) -> None:
    uso = res.uso
    row.model, row.model_servido, row.duration_ms = res.model, uso.model_servido, res.duration_ms
    row.input_tokens, row.output_tokens = uso.input_tokens, uso.output_tokens
    row.cache_read_tokens, row.cache_creation_tokens = uso.cache_read_tokens, \
        uso.cache_creation_tokens
    row.custo_usd = uso.custo_usd
    row.precos_versao = PRECOS_VERSAO if uso.custo_usd is not None else None
    if res.erro_code is not None:
        row.erro_code, row.erro_status, row.desfecho = res.erro_code, res.erro_status, \
            IaDesfecho.erro
        return
    v = res.validada
    assert v is not None
    row.proposta = v.proposta
    row.explicacao, row.excede, row.ajustes = v.explicacao, v.excede, v.ajustes
    row.avisos = [*v.avisos, *(_AVISOS_FALTANTE[f] for f in faltante if f in _AVISOS_FALTANTE)]


def gerar(db: Session, actor: Actor, body: schemas.GerarIn,
          client: IaClient | None) -> IaChamada:
    tipo = tipo_or_404(body.tipo_campo)
    perfil = get_perfil_or_404(db, body.perfil_id)
    if perfil.archived:
        raise _arquivado("Este perfil")
    alvo = _resolver_alvo(db, tipo, perfil, body.alvo)
    valor_atual = _valor_atual(tipo, body.valor_atual)
    aceitos, rejeitados = _selecao(tipo, body.selecao)
    anteriores = _anteriores(db, actor, tipo, perfil, alvo, body.sessao_id, body.anteriores)
    return executar(db, actor, tipo, perfil, alvo, valor_atual, body.instrucao.strip(), client,
                    sessao_id=body.sessao_id, anteriores=anteriores, aceitos=aceitos,
                    rejeitados=rejeitados)


def descartar(db: Session, actor: Actor, chamada_id: uuid.UUID) -> None:
    """Só o autor. Idempotente; `aplicada`, `editada` e `erro` ficam como estão."""
    chamada = db.get(IaChamada, chamada_id, with_for_update=True)
    if chamada is None:
        raise ApiError(404, "not_found", "Chamada não encontrada")
    if chamada.created_by != actor.user_id:
        raise ApiError(403, "forbidden", "Só quem gerou pode descartar esta proposta")
    if chamada.desfecho == IaDesfecho.sem_acao:
        chamada.desfecho = IaDesfecho.descartada
        chamada.desfecho_em = datetime.now(UTC)
        chamada.desfecho_por = actor.user_id
        db.flush()


# ---- saída ----

def _valor(dados: dict[str, Any] | None) -> schemas.Valor | None:
    # Sem validar: uma proposta marcada `excede` pode passar dos limites de entrada.
    return schemas.Valor.model_construct(**dados) if dados else None


def chamadas_out(db: Session, rows: Sequence[IaChamada]) -> list[schemas.IaChamada]:
    from sociman_api.canais.schemas import PerfilRef

    perfis = {p.id: p for p in db.scalars(
        select(Perfil).where(Perfil.id.in_({r.perfil_id for r in rows})))} if rows else {}
    users = user_refs(db, [u for r in rows for u in (r.created_by, r.desfecho_por)])
    out = []
    for r in rows:
        p = perfis[r.perfil_id]
        conta_id = r.conta_id if r.entity_type == "corte" else None
        out.append(schemas.IaChamada(
            id=r.id, tipo_campo=r.tipo_campo,
            perfil=PerfilRef(id=p.id, name=p.name, slug=p.slug),
            alvo=schemas.Alvo(entity_type=r.entity_type, entity_id=r.entity_id,
                              conta_id=conta_id),
            sessao_id=r.sessao_id, instrucao=r.instrucao, aceitos=list(r.aceitos),
            rejeitados=list(r.rejeitados),
            itens_aplicados=list(r.itens_aplicados) if r.itens_aplicados is not None else None,
            entrada=_valor(r.entrada), proposta=_valor(r.proposta), explicacao=r.explicacao,
            avisos=list(r.avisos), excede=r.excede, contexto_faltante=list(r.contexto_faltante),
            desfecho=r.desfecho, desfecho_em=r.desfecho_em,
            desfecho_por=users.get(r.desfecho_por) if r.desfecho_por else None,
            aplicada_versao=r.aplicada_versao, model=r.model, model_servido=r.model_servido,
            regras_version=r.regras_version, erro_code=r.erro_code,
            input_tokens=r.input_tokens, output_tokens=r.output_tokens,
            cache_read_tokens=r.cache_read_tokens, cache_creation_tokens=r.cache_creation_tokens,
            custo_usd=float(r.custo_usd) if r.custo_usd is not None else None,
            duration_ms=r.duration_ms, created_at=r.created_at,
            created_by=users.get(r.created_by) if r.created_by else None,
        ))
    return out


def chamada_out(db: Session, row: IaChamada) -> schemas.IaChamada:
    return chamadas_out(db, [row])[0]


# ---- registro e resumo (dono; US3) ----

LIMIT_PADRAO = 50
LIMIT_MAX = 100


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_tz)


def _inicio_do_dia(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=_tz())


def _cursor(row: IaChamada) -> str:
    bruto = f"{row.created_at.isoformat()}|{row.id}"
    return base64.urlsafe_b64encode(bruto.encode()).decode()


def _ler_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        quando, cid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(quando), uuid.UUID(cid)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(400, "validation_error", "Cursor inválido") from exc


def listar_chamadas(db: Session, *, perfil_id: uuid.UUID | None = None,
                    tipo_campo: str | None = None, desfecho: IaDesfecho | None = None,
                    de: date | None = None, ate: date | None = None,
                    sessao_id: uuid.UUID | None = None, cursor: str | None = None,
                    limit: int = LIMIT_PADRAO) -> schemas.ChamadasList:
    """Mais recentes primeiro, com cursor (`created_at desc, id`). Datas em APP_TZ, inclusive."""
    if de is not None and ate is not None and ate < de:
        raise ApiError(400, "validation_error", "A data final vem antes da inicial")
    query = select(IaChamada)
    if perfil_id is not None:
        query = query.where(IaChamada.perfil_id == perfil_id)
    if tipo_campo is not None:
        query = query.where(IaChamada.tipo_campo == tipo_campo)
    if desfecho is not None:
        query = query.where(IaChamada.desfecho == desfecho)
    if de is not None:
        query = query.where(IaChamada.created_at >= _inicio_do_dia(de))
    if ate is not None:
        query = query.where(IaChamada.created_at < _inicio_do_dia(ate + timedelta(days=1)))
    if sessao_id is not None:
        query = query.where(IaChamada.sessao_id == sessao_id)
    if cursor:
        quando, cid = _ler_cursor(cursor)
        query = query.where(or_(IaChamada.created_at < quando,
                                and_(IaChamada.created_at == quando, IaChamada.id > cid)))
    rows = list(db.scalars(query.order_by(IaChamada.created_at.desc(), IaChamada.id)
                           .limit(limit + 1)))
    proximo = _cursor(rows[limit - 1]) if len(rows) > limit else None
    return schemas.ChamadasList(items=chamadas_out(db, rows[:limit]), next_cursor=proximo)


def get_chamada(db: Session, chamada_id: uuid.UUID) -> schemas.IaChamada:
    row = db.get(IaChamada, chamada_id)
    if row is None:
        raise ApiError(404, "not_found", "Chamada não encontrada")
    return chamada_out(db, row)


def _mes(mes: str | None) -> tuple[str, date, date]:
    """(YYYY-MM, primeiro dia, primeiro dia do mês seguinte), em APP_TZ."""
    if mes is None:
        hoje = datetime.now(_tz()).date()
        inicio = hoje.replace(day=1)
    else:
        try:
            ano, numero = (int(p) for p in mes.split("-"))
            inicio = date(ano, numero, 1)
        except ValueError as exc:
            raise ApiError(400, "validation_error", "Mês inválido (use AAAA-MM)") from exc
    fim = (inicio + timedelta(days=32)).replace(day=1)
    return inicio.strftime("%Y-%m"), inicio, fim


def _custo(valor: Any) -> float:
    return float(valor or 0)


def resumo(db: Session, mes: str | None) -> schemas.IaResumo:
    """Um `SUM`/`GROUP BY` sobre o mês (APP_TZ), com o custo gravado em cada chamada."""
    from sociman_api.canais.schemas import PerfilRef

    rotulo, inicio, fim = _mes(mes)
    no_mes = and_(IaChamada.created_at >= _inicio_do_dia(inicio),
                  IaChamada.created_at < _inicio_do_dia(fim))

    def conta(d: IaDesfecho) -> Any:
        return func.count(case((IaChamada.desfecho == d, 1)))

    total = db.execute(select(
        func.count(), conta(IaDesfecho.erro), conta(IaDesfecho.aplicada),
        conta(IaDesfecho.editada), conta(IaDesfecho.descartada),
        func.coalesce(func.sum(IaChamada.custo_usd), 0),
    ).where(no_mes)).one()
    por_tipo = db.execute(
        select(IaChamada.tipo_campo, func.count(), func.coalesce(func.sum(IaChamada.custo_usd), 0))
        .where(no_mes).group_by(IaChamada.tipo_campo)
        .order_by(func.coalesce(func.sum(IaChamada.custo_usd), 0).desc(), IaChamada.tipo_campo)
    ).all()
    por_perfil = db.execute(
        select(Perfil.id, Perfil.name, Perfil.slug, func.count(),
               func.coalesce(func.sum(IaChamada.custo_usd), 0))
        .join(Perfil, Perfil.id == IaChamada.perfil_id).where(no_mes)
        .group_by(Perfil.id, Perfil.name, Perfil.slug)
        .order_by(func.coalesce(func.sum(IaChamada.custo_usd), 0).desc(), Perfil.name)
    ).all()
    return schemas.IaResumo(
        mes=rotulo, de=inicio, ate=fim - timedelta(days=1), chamadas=total[0], erros=total[1],
        aplicadas=total[2], editadas=total[3], descartadas=total[4], custo_usd=_custo(total[5]),
        por_tipo=[schemas.ResumoTipo(tipo_campo=t, chamadas=n, custo_usd=_custo(c))
                  for t, n, c in por_tipo],
        por_perfil=[schemas.ResumoPerfil(perfil=PerfilRef(id=i, name=nome, slug=slug),
                                         chamadas=n, custo_usd=_custo(c))
                    for i, nome, slug, n, c in por_perfil],
        precos_versao=PRECOS_VERSAO,
    )
