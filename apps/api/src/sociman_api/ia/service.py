"""Gerar, descartar, registro e resumo (spec 008, US1 e US3; research R5, R8, R9).

- `gerar` valida tipo × alvo × perfil, o `valorAtual` e a seleção pelo formato, carrega as
  anteriores pelo id (mesmo autor, sessão, tipo e alvo), monta o contexto e o prompt, chama o
  Claude e **grava sempre** a chamada, inclusive com erro (commit antes de levantar, como o
  `_deny` da auth, porque o `get_db` faz rollback quando a rota levanta).
- Gerar **não muda nenhuma entidade** (princípio VII): quem salva é o save de cada tela, no
  clique humano, com o campo `ia` (`ia/aplicacao.py`).
- `executar` é a parte comum, usada também pelas rotas da 006 (`postagem.textos`).
- Spec 017: `executar` carrega os guias em vigor (o do perfil sempre; o da conta só quando o
  alvo tem conta; nos tipos `so_proibidas`, só as proibidas do perfil), manda ao prompt e às
  garantias da saída e grava as versões usadas e as proibidas encontradas. `montar_guia` e
  `testar_guia` são os dois usos novos (R9, R10).
"""

import base64
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
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
from sociman_api.ia import guia as guia_mod
from sociman_api.ia import prompt, saida, schemas
from sociman_api.ia.cliente import IaClient, Resultado
from sociman_api.ia.custo import PRECOS_VERSAO
from sociman_api.ia.models import IaChamada, IaDesfecho, IaRegra
from sociman_api.ia.schemas_guia import GuiaCampos, MontarIn, TestarIn
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
    entity_type: str  # asset | perfil | kit | postagem | corte | conteudo
    entity_id: uuid.UUID | None
    asset: Asset | None = None
    corte: Corte | None = None  # só na origem corte (transcrição e gancho no contexto)
    conta: Conta | None = None
    postagem: Any | None = None
    conteudo: Any | None = None  # spec 014: toda chamada `postagem.*` grava o `conteudo_id`
    cena: ctx_mod.CenaInfo | None = None  # spec 010: o contexto da cena (salva ou formulário)


def _arquivado(nome: str) -> ApiError:
    return ApiError(409, "conflict", f"{nome} está arquivad{'a' if nome.startswith('Esta') else 'o'}")


def _resolver_cena(db: Session, perfil: Perfil, alvo: schemas.Alvo,
                   contexto: schemas.CenaContexto | None) -> AlvoResolvido:
    """Spec 010: a cena salva (do perfil, não arquivada) ou, numa cena nova, o `cenaContexto`
    do formulário. Os ids do formulário passam pela mesma conferência do save (422)."""
    from sociman_api.cenas import ingredientes  # import tardio (ciclo)
    from sociman_api.cenas import service as cenas
    from sociman_api.cenas.models import CAMPOS_EDITAVEIS, Cena
    from sociman_api.ia.tipos import CAMPOS_CENA_IA

    if alvo.entity_type != "cena":
        raise invalid("Este campo é de uma cena")
    valores: dict[str, Any] = {}
    cena = None
    if alvo.entity_id is not None:
        cena = db.get(Cena, alvo.entity_id)
        if cena is None:
            raise ApiError(404, "nao_encontrada", "Cena não encontrada")
        if cena.perfil_id != perfil.id:
            raise invalid("A cena é de outro perfil")
        if cena.archived:
            raise _arquivado("Esta cena")
        valores = {f: getattr(cena, f) for f in CAMPOS_EDITAVEIS}
    elif contexto is None:
        raise invalid("cenaContexto: obrigatório numa cena ainda não salva")
    novos: set[str] = set()
    if contexto is not None:
        form = contexto.model_dump(exclude_unset=True)
        novos = {k for k in form if k.endswith("_id")}
        valores |= form
        if "avatar_id" in form and "avatar_arquivo_id" not in form:
            valores["avatar_arquivo_id"] = None
    valores.setdefault("produto_nome", None)
    if valores.get("produto_imagem_id") is not None and not valores.get("produto_nome"):
        valores["produto_imagem_id"] = None  # o contexto não exige a foto
    cenas.validar_refs(db, perfil.id, valores, novos=novos)
    assets = cenas.assets_da(db, SimpleNamespace(
        avatar_id=valores.get("avatar_id"), cenario_id=valores.get("cenario_id"),
        produto_imagem_id=valores.get("produto_imagem_id")))
    f = ingredientes.arquivo(assets.avatar, valores.get("avatar_arquivo_id"))
    info = ctx_mod.CenaInfo(
        avatar=assets.avatar, arquivo_rotulo=(f.look or f.label) if f is not None else None,
        cenario=assets.cenario, produto_nome=valores.get("produto_nome"),
        produto_com_foto=assets.produto is not None, fala=valores.get("fala"),
        duracao_s=valores.get("duracao_s"),
        modo=getattr(valores.get("modo"), "value", valores.get("modo")),
        atuais=tuple((c, valores.get(c) or "") for c in CAMPOS_CENA_IA))
    return AlvoResolvido("cena", cena.id if cena is not None else None, cena=info)


def _resolver_alvo(db: Session, tipo: TipoCampo, perfil: Perfil,
                   alvo: schemas.Alvo,
                   cena_contexto: schemas.CenaContexto | None = None) -> AlvoResolvido:
    """Confere que o alvo existe, é do perfil e casa com o tipo (400 `invalid_ia` senão)."""
    et, eid = alvo.entity_type, alvo.entity_id
    if tipo.entidade == "cena":
        return _resolver_cena(db, perfil, alvo, cena_contexto)
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


def _conteudo_arquivado(conteudo: Any, corte: Corte | None) -> bool:
    return corte.archived if corte is not None else conteudo.archived


def _resolver_postagem(db: Session, perfil: Perfil, alvo: schemas.Alvo) -> AlvoResolvido:
    """Destino existente (`postagem`) ou conteúdo + conta antes de o destino existir
    (`conteudo`, ou `corte` com o mesmo id, spec 014 R12). Na origem corte, o corte entra no
    contexto (transcrição, gancho); no vídeo próprio, não há transcrição."""
    from sociman_api.conteudos.models import Conteudo  # import tardio (ciclo)
    from sociman_api.postagem.models import Postagem

    if alvo.entity_type == "postagem" and alvo.entity_id is not None:
        postagem = db.get(Postagem, alvo.entity_id)
        if postagem is None:
            raise ApiError(404, "not_found", "Destino não encontrado")
        conteudo = db.get(Conteudo, postagem.conteudo_id)
        conta = db.get(Conta, postagem.conta_id)
        assert conteudo is not None and conta is not None
        corte = db.get(Corte, conteudo.corte_id) if conteudo.corte_id is not None else None
        if conteudo.perfil_id != perfil.id:
            raise invalid("O destino é de outro perfil")
        if postagem.archived:
            raise _arquivado("Este destino")
        return AlvoResolvido("postagem", postagem.id, corte=corte, conta=conta,
                             postagem=postagem, conteudo=conteudo)
    if alvo.entity_type not in ("corte", "conteudo") or alvo.entity_id is None \
            or alvo.conta_id is None:
        raise invalid("Este campo é de um destino (ou de um conteúdo com a conta de destino)")
    conteudo = db.get(Conteudo, alvo.entity_id)
    if conteudo is None:
        nome = "Corte" if alvo.entity_type == "corte" else "Conteúdo"
        raise ApiError(404, "not_found", f"{nome} não encontrado")
    corte = db.get(Corte, conteudo.corte_id) if conteudo.corte_id is not None else None
    if alvo.entity_type == "corte" and corte is None:
        raise ApiError(404, "not_found", "Corte não encontrado")
    conta = db.get(Conta, alvo.conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    if conteudo.perfil_id != perfil.id or conta.perfil_id != perfil.id:
        raise invalid("O conteúdo e a conta precisam ser do perfil")
    if _conteudo_arquivado(conteudo, corte):
        raise _arquivado("Este corte" if alvo.entity_type == "corte" else "Este conteúdo")
    if conta.archived:
        raise _arquivado("Esta conta")
    return AlvoResolvido(alvo.entity_type, conteudo.id, corte=corte, conta=conta,
                         conteudo=conteudo)


# ---- valor atual e seleção ----

def _limite(valor: int | None) -> int | None:
    return int(valor * MARGEM_VALOR_ATUAL) if valor else None


def _valor_atual(tipo: TipoCampo, valor: schemas.Valor) -> dict[str, Any]:
    dados = valor.model_dump(exclude_none=True)
    lim = tipo.limites
    permitidos = {"texto": {"texto"}, "lista": {"itens"}, "sugestoes": {"itens"},
                  "textos_postagem": {"titulo", "descricao", "hashtags"},
                  "campos_cena": {"cena"}}[tipo.formato]
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
        # Spec 014: a sessão sobrevive à criação do destino (conteúdo + conta → destino).
        mesmo_alvo = mesmo_alvo or (
            c is not None and alvo.conteudo is not None
            and c.entity_type in ("corte", "conteudo", "postagem")
            and c.conteudo_id == alvo.conteudo.id)
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


def _efetivo(tipo: TipoCampo, guias: guia_mod.GuiasEmVigor) -> guia_mod.GuiaEfetivo:
    """O guia das garantias: nos `so_proibidas`, só as proibidas do perfil (Q1)."""
    if tipo.usa_guia == "so_proibidas":
        perfil = guias.perfil
        return guia_mod.GuiaEfetivo(
            proibidas=tuple(perfil.campos.proibidas) if perfil is not None else ())
    return guia_mod.fundir(guias.perfil, guias.conta)


def _desempenho(db: Session, tipo: TipoCampo, perfil: Perfil, alvo: AlvoResolvido,
                efetivo: guia_mod.GuiaEfetivo) -> tuple[Any, guia_mod.GuiaEfetivo]:
    """Spec 023 (R8): o bloco `<desempenho>` (só `postagem.*` e `guia.testar`, com o uso ligado)
    e as hashtags "evitar" aceitas, que o servidor tira da proposta."""
    from sociman_api.aprendizado import desempenho as desempenho_mod  # import tardio (ciclo)
    from sociman_api.aprendizado import preferencias as prefs_mod

    if tipo.id not in desempenho_mod.TIPOS or alvo.conta is None:
        return None, efetivo
    ef = prefs_mod.efetivas(db, perfil.id, alvo.conta.id)
    if ef.hashtags_evitar:
        efetivo = replace(efetivo, hashtags_evitar=tuple(ef.hashtags_evitar))
    return desempenho_mod.bloco(db, perfil.id, alvo.conta.id, efetivo.proibidas), efetivo


def executar(db: Session, actor: Actor, tipo: TipoCampo, perfil: Perfil, alvo: AlvoResolvido,
             valor_atual: dict[str, Any], instrucao: str, client: IaClient | None, *,
             sessao_id: uuid.UUID | None = None, anteriores: Sequence[IaChamada] = (),
             aceitos: Sequence[str] = (), rejeitados: Sequence[str] = (),
             guias: guia_mod.GuiasEmVigor | None = None,
             guia_rascunho: str | None = None) -> IaChamada:
    """Monta o contexto, chama o Claude e grava a chamada. Com erro, commita e levanta.

    `guias`: só no montar e no testar (spec 017); nos outros, os em vigor do perfil e da conta
    do alvo."""
    regras = regras_em_vigor(db, TIPOS[tipo.regras_de] if tipo.regras_de else tipo)
    if guias is None:
        guias = guia_mod.em_vigor(db, perfil.id, alvo.conta.id if alvo.conta is not None
                                  else None)
    efetivo = _efetivo(tipo, guias)
    desempenho, efetivo = _desempenho(db, tipo, perfil, alvo, efetivo)
    enviado_perfil, enviado_conta = prompt.guias_enviados(tipo, guias)
    contexto = ctx_mod.montar(db, tipo, perfil, asset=alvo.asset, corte=alvo.corte,
                              conta=alvo.conta, postagem=alvo.postagem, conteudo=alvo.conteudo,
                              cena=alvo.cena)
    if tipo.entidade == "guia":  # spec 017: de quem é o guia que está sendo montado
        dono = "o perfil inteiro (vale para todas as contas)" if alvo.conta is None else (
            "a conta " + ctx_mod.plataforma_label(alvo.conta.platform, alvo.conta.platform_name)
            + f" @{alvo.conta.handle}")
        contexto = replace(contexto, entidade=(("Guia de comunicação de", dono),))
    row = IaChamada(
        id=uuid.uuid4(), tipo_campo=tipo.id, perfil_id=perfil.id,
        entity_type=alvo.entity_type, entity_id=alvo.entity_id,
        corte_id=alvo.corte.id if alvo.corte is not None else None,
        conteudo_id=alvo.conteudo.id if alvo.conteudo is not None else None,
        conta_id=alvo.conta.id if alvo.conta is not None else None,
        plataforma=alvo.conta.platform if alvo.conta is not None else None,
        sessao_id=sessao_id, anteriores=[a.id for a in anteriores], aceitos=list(aceitos),
        rejeitados=list(rejeitados), instrucao=instrucao, entrada=valor_atual or None,
        contexto_faltante=list(contexto.faltante), prompt_version=prompt.PROMPT_VERSION,
        regras_version=regras.version, padrao_versao=regras.padrao_versao,
        guia_perfil_version=enviado_perfil.version if enviado_perfil is not None else None,
        guia_conta_version=enviado_conta.version if enviado_conta is not None else None,
        guia_rascunho=guia_rascunho, created_by=actor.user_id,
        desempenho_perfil_version=desempenho.perfil_version if desempenho else None,
        desempenho_conta_version=desempenho.conta_version if desempenho else None,
        desempenho_exemplos=[e.video_id for e in desempenho.exemplos] if desempenho else [],
    )
    if client is None:
        row.model, row.duration_ms = get_settings().textos_model, 0
        row.erro_code, row.desfecho = "unconfigured", IaDesfecho.erro
        db.add(row)
        db.commit()
        raise ApiError(503, "claude_unconfigured",
                       "O Claude não está configurado (ANTHROPIC_API_KEY); escreva à mão")

    system = prompt.montar_system(
        tipo, regras.texto, contexto, guias, fixas=len(efetivo.hashtags_fixas),
        desempenho=(desempenho.render(), desempenho.perfil_version, desempenho.conta_version)
        if desempenho else None)
    propostas = [a.proposta for a in anteriores if a.proposta]
    excluir = saida.Excluir(atuais=tuple(valor_atual.get("itens") or ()),
                            aceitos=tuple(aceitos), rejeitados=tuple(rejeitados))
    res = client.gerar(tipo, system, lambda erro: prompt.montar_user(
        tipo, contexto, valor_atual, instrucao, propostas, aceitos, rejeitados, erro), excluir,
        efetivo)
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
    row.proibidas = list(v.proibidas)
    row.avisos = [*v.avisos, *(_AVISOS_FALTANTE[f] for f in faltante if f in _AVISOS_FALTANTE)]


def gerar(db: Session, actor: Actor, body: schemas.GerarIn,
          client: IaClient | None) -> IaChamada:
    tipo = tipo_or_404(body.tipo_campo)
    if tipo.entidade == "guia" or tipo.formato == "variacoes":
        raise invalid("Use as rotas do guia de comunicação (montar e testar)")
    if tipo.entidade == "aprendizado":  # spec 023: pedidos montados pelo aprendizado
        raise invalid("Use as rotas do aprendizado")
    perfil = get_perfil_or_404(db, body.perfil_id)
    if perfil.archived:
        raise _arquivado("Este perfil")
    if body.cena_contexto is not None and tipo.entidade != "cena":
        raise invalid("cenaContexto: só nos campos da cena")
    alvo = _resolver_alvo(db, tipo, perfil, body.alvo, body.cena_contexto)
    valor_atual = _valor_atual(tipo, body.valor_atual)
    aceitos, rejeitados = _selecao(tipo, body.selecao)
    anteriores = _anteriores(db, actor, tipo, perfil, alvo, body.sessao_id, body.anteriores)
    return executar(db, actor, tipo, perfil, alvo, valor_atual, body.instrucao.strip(), client,
                    sessao_id=body.sessao_id, anteriores=anteriores, aceitos=aceitos,
                    rejeitados=rejeitados)


# ---- montar e testar o guia de comunicação (spec 017, R9 e R10; só o dono) ----

def _perfil_e_conta(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None
                    ) -> tuple[Perfil, Conta | None]:
    perfil = get_perfil_or_404(db, perfil_id)
    if perfil.archived:
        raise _arquivado("Este perfil")
    if conta_id is None:
        return perfil, None
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    if conta.perfil_id != perfil.id:
        raise invalid("A conta é de outro perfil")
    if conta.archived:
        raise _arquivado("Esta conta")
    return perfil, conta


def montar_guia(db: Session, actor: Actor, body: MontarIn, client: IaClient | None
                ) -> IaChamada:
    """Proposta de guia que só preenche o formulário: nada é salvo além da chamada. No guia
    da conta, o do perfil salvo vai como `<guia_perfil>` (a regra pede só o que a conta
    acrescenta)."""
    tipo = TIPOS["guia.montar"]
    perfil, conta = _perfil_e_conta(db, body.perfil_id, body.conta_id)
    row = guia_mod.linha(db, perfil.id, conta.id if conta is not None else None)
    alvo = AlvoResolvido("guia", row.id if row is not None else None, conta=conta)
    guias = guia_mod.GuiasEmVigor(
        perfil=guia_mod.em_vigor(db, perfil.id, None).perfil if conta is not None else None,
        conta=None)
    anteriores = _anteriores(db, actor, tipo, perfil, alvo, body.sessao_id, body.anteriores)
    if conta is None and any(a.conta_id is not None for a in anteriores):
        raise ApiError(400, "ia_anteriores_invalidas",
                       "As versões anteriores precisam ser desta sessão, deste campo e sua")
    valor_atual = {"guia": body.guia_atual.model_dump(by_alias=True, mode="json")}
    return executar(db, actor, tipo, perfil, alvo, valor_atual, body.descricao.strip(), client,
                    sessao_id=body.sessao_id, anteriores=anteriores, guias=guias)


INSTRUCAO_TESTAR = ("Escreva 3 versões diferentes dos textos da postagem deste conteúdo, "
                    "seguindo o guia de comunicação.")


def testar_guia(db: Session, actor: Actor, body: TestarIn, client: IaClient | None
                ) -> IaChamada:
    """3 textos de postagem com o guia do formulário (o nível em teste) e o salvo do outro
    nível. Valida o formulário como o PUT **antes** de chamar o Claude; grava só a chamada
    (`sem_acao`), sem versão e sem mudar conteúdo."""
    from sociman_api.ia import service_guia  # import tardio (ciclo)

    tipo = TIPOS["guia.testar"]
    perfil, conta = _perfil_e_conta(db, body.perfil_id, body.conta_id)
    assert conta is not None
    campos = service_guia.validar_campos(db, perfil, conta if body.nivel == "conta" else None,
                                         body.guia.dominio())
    alvo = _resolver_postagem(db, perfil, schemas.Alvo(
        entity_type=body.alvo.entity_type, entity_id=body.alvo.entity_id, conta_id=conta.id))
    base = guia_mod.linha(db, perfil.id, conta.id if body.nivel == "conta" else None)
    rascunho = guia_mod.como_rascunho(campos, body.nivel, base.version if base else 0)
    salvos = guia_mod.em_vigor(db, perfil.id, conta.id)
    guias = guia_mod.GuiasEmVigor(
        perfil=rascunho if body.nivel == "perfil" else salvos.perfil,
        conta=rascunho if body.nivel == "conta" else salvos.conta)
    valor_atual = {"guia": body.guia.model_dump(by_alias=True, mode="json")}
    return executar(db, actor, tipo, perfil, alvo, valor_atual, INSTRUCAO_TESTAR, client,
                    guias=guias, guia_rascunho=body.nivel)


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
    if not dados:
        return None
    dados = dict(dados)
    if dados.get("guia") is not None:  # spec 017: os submodelos, para serializar sem aviso
        dados["guia"] = GuiaCampos.model_construct(**{
            _SNAKE.get(k, k): v for k, v in dados["guia"].items()})
    if dados.get("variacoes") is not None:
        dados["variacoes"] = [schemas.Variacao.model_construct(**v) for v in dados["variacoes"]]
    return schemas.Valor.model_construct(**dados)


_SNAKE = {"naoFaca": "nao_faca", "emojisPreferidos": "emojis_preferidos",
          "hashtagsFixas": "hashtags_fixas", "maxHashtagsFixas": "max_hashtags_fixas"}


def chamadas_out(db: Session, rows: Sequence[IaChamada]) -> list[schemas.IaChamada]:
    from sociman_api.canais.schemas import PerfilRef

    perfis = {p.id: p for p in db.scalars(
        select(Perfil).where(Perfil.id.in_({r.perfil_id for r in rows})))} if rows else {}
    users = user_refs(db, [u for r in rows for u in (r.created_by, r.desfecho_por)])
    out = []
    for r in rows:
        p = perfis[r.perfil_id]
        conta_id = r.conta_id if r.entity_type in ("corte", "conteudo") else None
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
            guia_perfil_version=r.guia_perfil_version, guia_conta_version=r.guia_conta_version,
            guia_rascunho=r.guia_rascunho, proibidas=list(r.proibidas or []),
            desempenho_perfil_version=r.desempenho_perfil_version,
            desempenho_conta_version=r.desempenho_conta_version,
            desempenho_exemplos=list(r.desempenho_exemplos or []),
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
