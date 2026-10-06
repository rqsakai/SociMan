"""Conciliação por tipo (research R4 a R6 e R9): procura no banco, compara e classifica.

Nada aqui grava. Cada função recebe o que o leitor montou e devolve `Item`s com a situação
(`novo`, `igual`, `diverge`, `fora`, `aguardando_cota`, `sugestao`), o valor proposto (`dados`) e
a `base` (versões lidas, para o confirmar recusar o que mudou no SociMan desde a leitura).
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sociman_api.agencia import itens
from sociman_api.agencia import markdown as md
from sociman_api.agencia.itens import Item, cortar, impressao
from sociman_api.agencia.leitores import ContaLida, FonteLida, PerfilLido, TrechoLido
from sociman_api.anotacoes.models import Anotacao, AnotacaoSituacao
from sociman_api.assets.models import Asset, AssetFile, AssetTipo
from sociman_api.canais import service_canais
from sociman_api.canais.models import CanalDireito, CanalFonte
from sociman_api.canais.resolve import resolver_entrada
from sociman_api.conteudos.models import Conteudo
from sociman_api.errors import ApiError
from sociman_api.ia import guia as guia_dominio
from sociman_api.marca import service_kit
from sociman_api.perfis.models import Conta, Image, Perfil
from sociman_api.perfis.platforms import normalize_handle, suggest_slug, url_for

NICHO_MAX = 200
NOTA_MAX = 2000
EVIDENCIA_URL_MAX = 500
_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
_CHANNEL_ID = re.compile(r"\bUC[0-9A-Za-z_-]{22}\b")
_HANDLE_SOLTO = re.compile(r"(?<![\w/.])@([A-Za-z0-9._-]{3,30})\b")


@dataclass
class Ctx:
    """O que a conciliação lê do banco, carregado uma vez por prévia."""

    db: Session
    youtube: Callable[[], Any] | None = None  # fábrica do cliente (só se houver canal novo)
    perfis: dict[str, Perfil] = field(default_factory=dict)  # por slug, inclusive arquivados
    # slug → perfil disponível para os itens dependentes: o existente ativo, ou None quando o
    # perfil é novo nesta importação. Slug fora daqui: os dependentes ficam "fora".
    alvo: dict[str, Perfil | None] = field(default_factory=dict)
    resolvidos: dict[str, str] = field(default_factory=dict)  # entrada → channel id | código
    cota_esgotada: bool = False
    _cliente: Any = None

    def cliente(self) -> Any:
        if self._cliente is None and self.youtube is not None:
            self._cliente = self.youtube()
        return self._cliente

    def fechar(self) -> None:
        if self._cliente is not None:
            self._cliente.close()


def _base(entity_type: str, obj: Any) -> dict[str, int]:
    return {f"{entity_type}:{obj.id}": int(obj.version)}


# ---- perfil ----

def slug_de(pasta: str) -> str:
    return suggest_slug(pasta)


def perfil_item(ctx: Ctx, lido: PerfilLido, arquivo: str) -> list[Item]:
    slug = slug_de(lido.slug_pasta)
    nicho, nicho_cortado = lido.nicho[:NICHO_MAX].rstrip(), len(lido.nicho) > NICHO_MAX
    dados = {"slug": slug, "name": lido.nome[:80], "language": lido.idioma,
             "niche": nicho, "status": lido.status}
    item = Item("perfil", slug, arquivo, "§1. Identidade e §2. Nicho", f"perfil:{slug}",
                "novo", linha=lido.linha_identidade, impressao=impressao(dados), dados=dados,
                proposto={"nome": dados["name"], "idioma": lido.idioma, "nicho": nicho,
                          "status": lido.status, "statusMarkdown": lido.status_md,
                          **({"nichoCortado": True} if nicho_cortado else {})})
    saida = [item]
    if len(slug) < 2:
        item.situacao, item.motivo = "fora", "slug_em_uso"
        return saida
    if lido.status is None:
        item.situacao, item.motivo = "fora", "status_desconhecido"
        return saida
    if not _LANGUAGE.match(lido.idioma):
        item.situacao, item.motivo = "fora", "idioma_invalido"
        return saida
    atual = ctx.perfis.get(slug)
    if atual is None:
        ctx.alvo[slug] = None
    else:
        item.base = _base("perfil", atual)
        item.atual = {"nome": atual.name, "idioma": atual.language, "nicho": atual.niche,
                      "status": atual.status.value}
        if atual.archived:
            item.situacao, item.motivo = "diverge", "arquivado"
        else:
            ctx.alvo[slug] = atual
            igual = (atual.name, atual.language, atual.niche, atual.status.value) == (
                dados["name"], dados["language"], nicho, lido.status)
            item.situacao, item.motivo = ("igual", None) if igual else ("diverge", "valor")
    if nicho_cortado:
        saida += anotacao_items(ctx, slug, arquivo, [TrechoLido(
            "§2. Nicho (completo)", "nicho",
            f"perfil.md §2. Nicho · nicho principal completo (o perfil guarda até {NICHO_MAX} "
            f"caracteres)\n\n{lido.nicho}", lido.linha_nicho)])
    return saida


def perfil_sem_md(ctx: Ctx, pasta: str, arquivo: str) -> Item:
    """Pasta de perfil sem `perfil.md`: fora, mas um perfil que já existe segue disponível."""
    slug = slug_de(pasta)
    atual = ctx.perfis.get(slug)
    if atual is not None and not atual.archived:
        ctx.alvo.setdefault(slug, atual)
    return Item("perfil", slug, arquivo, "pasta do perfil", f"perfil:{slug}", "fora",
                motivo="sem_perfil_md")


def dependente_fora(ctx: Ctx, item: Item) -> Item:
    """Itens de um perfil que não entra (fora, arquivado) ficam "fora"."""
    if item.tipo != "perfil" and item.perfil_slug is not None and item.perfil_slug not in ctx.alvo \
            and item.situacao != "fora":
        item.situacao, item.motivo = "fora", "perfil_fora"
    return item


# ---- contas ----

def conta_items(ctx: Ctx, slug: str, contas: list[ContaLida], arquivo: str) -> list[Item]:
    out = []
    perfil = ctx.alvo.get(slug)
    for c in contas:
        trecho = f"§1. @ no {'YouTube' if c.plataforma == 'youtube' else 'TikTok'}"
        item = Item("conta", slug, arquivo, trecho, f"conta:{c.plataforma}:{c.handle}", "novo",
                    linha=c.linha, proposto={"plataforma": c.plataforma, "handle": c.handle,
                                             "url": c.url})
        out.append(item)
        try:
            handle = normalize_handle(c.handle or "")
        except ValueError:
            item.situacao, item.motivo = "fora", "handle_invalido"
            item.proposto = {"texto": c.bruto}
            continue
        item.chave = f"conta:{c.plataforma}:{handle}"
        item.dados = {"platform": c.plataforma, "handle": handle,
                      "url": c.url or url_for(c.plataforma, handle)}  # type: ignore[arg-type]
        item.impressao = impressao(item.dados)
        existente = ctx.db.scalar(select(Conta).where(
            Conta.platform == c.plataforma, Conta.platform_name == "", Conta.handle == handle))
        if existente is None:
            continue
        item.atual = {"plataforma": existente.platform.value, "handle": existente.handle,
                      "url": existente.url}
        if perfil is None or existente.perfil_id != perfil.id:
            item.situacao, item.motivo = "fora", "conta_de_outro_perfil"
        elif existente.archived:
            item.situacao, item.motivo = "fora", "conta_arquivada"
        else:
            item.situacao = "igual"
    return out


# ---- guia e sugestões de bordão ----

def guia_item(ctx: Ctx, slug: str, lido: PerfilLido, arquivo: str) -> list[Item]:
    proposto = {"tom": lido.tom, "vocabulario": lido.vocabulario, "naoFaca": lido.nao_faca}
    if not any(proposto.values()):
        return []
    item = Item("guia", slug, arquivo, "§4. Posicionamento e tom", f"guia:{slug}", "novo",
                linha=lido.linha_guia, impressao=impressao(proposto), dados=proposto,
                proposto=proposto)
    perfil = ctx.alvo.get(slug)
    row = guia_dominio.linha(ctx.db, perfil.id, None) if perfil is not None else None
    if row is not None:
        item.base = _base("ia_guia", row)
        atual = {"tom": row.tom, "vocabulario": list(row.vocabulario),
                 "naoFaca": list(row.nao_faca)}
        item.atual = atual
        if not guia_dominio.GuiaCampos.de_linha(row).vazio:
            item.situacao, item.motivo = ("igual", None) if atual == proposto \
                else ("diverge", "editado")
    return [item]


def sugestao_items(ctx: Ctx, slug: str, lido: PerfilLido, arquivo: str) -> list[Item]:
    """Expressões da casa que não estão nos bordões do kit: só sugestão, nunca grava (FR-020)."""
    perfil = ctx.alvo.get(slug)
    kit = set()
    if perfil is not None:
        tokens, _ = service_kit.current_tokens(ctx.db, perfil.id)
        kit = {md.normalizar(b) for b in tokens.catchphrases}
    return [Item("sugestao_bordao", slug, arquivo, "§4. Expressões da casa",
                 f"bordao:{slug}:{md.normalizar(e)}", "sugestao", linha=lido.linha_guia,
                 proposto={"bordao": e})
            for e in lido.vocabulario if md.normalizar(e) not in kit]


# ---- anotações ----

def _partes(texto: str) -> list[str]:
    """Até 4.000 caracteres por anotação; maior que isso, "(1/2)" na 1ª linha de cada parte."""
    if len(texto) <= itens.TEXTO_MAX:
        return [texto]
    titulo, _, corpo = texto.partition("\n\n")
    tamanho = itens.TEXTO_MAX - len(titulo) - 16
    pedacos = [corpo[i:i + tamanho] for i in range(0, len(corpo), tamanho)]
    return [f"{titulo} ({i}/{len(pedacos)})\n\n{p}" for i, p in enumerate(pedacos, 1)]


def _anotacao_importada(db: Session, chave: str) -> tuple[Anotacao | None, str | None]:
    """A anotação viva da última importação concluída com esta chave, e a impressão gravada."""
    from sociman_api.agencia.models import Importacao, ImportacaoEstado, ImportacaoItem

    row = db.execute(
        select(ImportacaoItem.entity_id, ImportacaoItem.impressao)
        .join(Importacao, Importacao.id == ImportacaoItem.importacao_id)
        .where(ImportacaoItem.chave == chave,
               ImportacaoItem.resultado.in_(("criado", "atualizado")),
               ImportacaoItem.entity_type == "anotacao",
               ImportacaoItem.desfeito_em.is_(None),
               Importacao.estado == ImportacaoEstado.concluida)
        .order_by(ImportacaoItem.id.desc()).limit(1)).first()
    if row is None:
        return None, None
    anotacao = db.get(Anotacao, row.entity_id)
    if anotacao is None or anotacao.situacao == AnotacaoSituacao.arquivada:
        return None, None
    return anotacao, row.impressao


def anotacao_items(ctx: Ctx, slug: str, arquivo: str, trechos: list[TrechoLido]) -> list[Item]:
    nome = arquivo.rsplit("/", 1)[-1]
    out = []
    for t in trechos:
        partes = _partes(t.texto)
        for i, texto in enumerate(partes, 1):
            sufixo = f" ({i}/{len(partes)})" if len(partes) > 1 else ""
            chave = f"anotacao:{slug}:{nome}#{t.chave}{sufixo}"
            resumo, cortado = cortar(texto)
            item = Item("anotacao", slug, arquivo, t.trecho + sufixo, chave, "novo",
                        linha=t.linha, impressao=impressao(texto), dados={"texto": texto},
                        proposto={"texto": resumo, **({"cortado": True} if cortado else {})})
            anotacao, impressao_gravada = _anotacao_importada(ctx.db, chave)
            if anotacao is not None:
                item.base = _base("anotacao", anotacao)
                atual, cortado_atual = cortar(anotacao.texto)
                item.atual = {"texto": atual, **({"cortado": True} if cortado_atual else {})}
                item.dados["anotacao_id"] = str(anotacao.id)
                item.situacao, item.motivo = ("igual", None) \
                    if impressao_gravada == item.impressao else ("diverge", "valor")
            out.append(item)
    return out


# ---- canais-fonte e direito (R6, Q1) ----

DIREITO_PROPOSTO = {"programa-de-cortes": CanalDireito.programa_de_cortes,
                    "autorizado": CanalDireito.sem_acordo}
DIREITOS_ACEITOS = {"programa-de-cortes": [CanalDireito.programa_de_cortes],
                    "autorizado": [CanalDireito.sem_acordo, CanalDireito.parceiro]}


def status_fonte(status_md: str, propria: bool) -> str:
    return "proprio" if propria else status_md


def direito_proposto(status_md: str, propria: bool) -> CanalDireito:
    """Q1: `autorizado` → `sem_acordo` (o dono troca para `parceiro`); o resto, conservador."""
    if propria:
        return CanalDireito.proprio
    return DIREITO_PROPOSTO.get(status_md, CanalDireito.sem_acordo)


def direitos_aceitos(status_md: str, propria: bool) -> list[CanalDireito]:
    """FR-015a: o direito do canal existente que vale como "igual" ao status do markdown."""
    if propria:
        return [CanalDireito.proprio]
    return DIREITOS_ACEITOS.get(status_md, [CanalDireito.sem_acordo])


def identificar_canal(celula: str, linha_toda: str = "") -> tuple[str | None, str | None]:
    """(entrada para o `resolver` da 006, None) ou (None, motivo de "fora"). Vale o primeiro
    link do YouTube; TikTok, Twitch e sites ficam só na nota."""
    norm = md.normalizar(celula)
    if "nao confirmado" in norm or "a confirmar" in norm:
        return None, "sem_canal_youtube"
    for link in md.links(celula):
        if "youtube.com" in link.lower() or "youtu.be" in link.lower():
            return link, None
    if m := _CHANNEL_ID.search(celula):
        return m.group(0), None
    if not md.links(celula) and (m := _HANDLE_SOLTO.search(celula)) \
            and "tiktok" not in norm and "instagram" not in norm:
        return f"@{m.group(1)}", None
    tudo = md.normalizar(f"{celula} {linha_toda}")
    if "media/originais" in tudo or "material original" in tudo:
        return None, "conteudo_proprio"
    return None, "sem_canal_youtube"


def nota_evidencia(slug: str, f: FonteLida) -> str:
    """FR-016/FR-017: status original, evidência, regras, quem confirmou e quando."""
    partes = [f"fontes.md de {slug}, linha {f.linha}: status {f.status_md or 'sem status'}."]
    if f.status_md == "negado":
        partes.append(f"Negado no markdown em {f.data or 'data não informada'}.")
    if f.evidencia:
        partes.append(f.evidencia.rstrip(".") + ".")
    if f.regras:
        partes.append(f"Regras: {f.regras.rstrip('.')}.")
    if f.confirmado_por or f.data:
        partes.append(f"Confirmado por {f.confirmado_por or 'não informado'}"
                      + (f" em {f.data}" if f.data else "") + ".")
    nota = " ".join(partes)
    return nota if len(nota) <= NOTA_MAX else nota[:NOTA_MAX - 1] + "…"


def evidencia_url(f: FonteLida) -> str | None:
    return next((u for u in md.links(f.evidencia)
                 if u.lower().startswith("http") and len(u) <= EVIDENCIA_URL_MAX), None)


def _resolver(ctx: Ctx, entrada: str) -> str:
    """channel id, ou o código: `cota`, `canal_nao_encontrado`, `sem_canal_youtube`,
    `youtube_indisponivel`. Uma consulta por entrada na prévia."""
    if entrada in ctx.resolvidos:
        return ctx.resolvidos[entrada]
    try:
        consulta = resolver_entrada(entrada)
    except ApiError:
        ctx.resolvidos[entrada] = "sem_canal_youtube"
        return "sem_canal_youtube"
    if consulta.tipo == "id":
        ctx.resolvidos[entrada] = consulta.valor
        return consulta.valor
    if consulta.tipo in ("handle", "busca", "username"):  # já cadastrado pelo @: sem cota
        cid = ctx.db.scalar(select(CanalFonte.youtube_channel_id).where(
            func.lower(CanalFonte.handle) == consulta.valor.lower()))
        if cid is not None:
            ctx.resolvidos[entrada] = cid
            return cid
    if ctx.cota_esgotada:
        return "cota"
    from sociman_api.redis import get_redis

    cache = f"agencia:resolver:{entrada.lower()}"
    if cid := get_redis().get(cache):
        ctx.resolvidos[entrada] = cid
        return cid
    cliente = ctx.cliente()
    if cliente is None:
        return "youtube_indisponivel"
    try:
        out = service_canais.resolver(ctx.db, cliente, entrada)
    except ApiError as e:
        if e.status == 429:
            ctx.cota_esgotada = True
            return "cota"
        codigo = "canal_nao_encontrado" if e.status == 404 else \
            "sem_canal_youtube" if e.status == 400 else "youtube_indisponivel"
        ctx.resolvidos[entrada] = codigo
        return codigo
    cid = out.candidato.youtube_channel_id
    get_redis().set(cache, cid, ex=24 * 3600)
    ctx.resolvidos[entrada] = cid
    return cid


@dataclass
class _Linha:
    slug: str
    arquivo: str
    fonte: FonteLida


def canal_items(ctx: Ctx, linhas: list[_Linha]) -> list[Item]:
    """Um item `canal` por canal do YouTube (com todas as linhas que o citam) e um
    `vinculo_canal` por perfil ainda não ligado a um canal que já existe."""
    out: list[Item] = []
    por_canal: dict[str, list[_Linha]] = {}
    for ln in linhas:
        f = ln.fonte
        trecho = f.criador or f.canal or f"linha {f.linha}"
        entrada, motivo = identificar_canal(f.canal, f.criador)
        base_item = Item("canal", ln.slug, ln.arquivo, trecho, f"fonte:{ln.slug}:{f.linha}",
                         "fora", linha=f.linha, impressao=impressao(f.__dict__),
                         proposto={"canal": f.canal, "statusMarkdown": f.status_md,
                                   "criador": f.criador})
        if entrada is None:
            base_item.motivo = motivo
            out.append(base_item)
            continue
        cid = _resolver(ctx, entrada)
        if cid == "cota":
            base_item.situacao, base_item.motivo = "aguardando_cota", "cota"
            out.append(base_item)
        elif not cid.startswith("UC"):
            base_item.motivo = cid
            out.append(base_item)
        else:
            por_canal.setdefault(cid, []).append(ln)

    for cid, grupo in por_canal.items():
        out += _canal(ctx, cid, grupo)
    return out


def _canal(ctx: Ctx, cid: str, grupo: list[_Linha]) -> list[Item]:
    primeira = grupo[0]
    f0 = primeira.fonte
    propostos = {direito_proposto(g.fonte.status_md, g.fonte.propria) for g in grupo}
    aceitos_por_linha = [set(direitos_aceitos(g.fonte.status_md, g.fonte.propria))
                         for g in grupo]
    aceitos = set.intersection(*aceitos_por_linha)
    proposto = direito_proposto(f0.status_md, f0.propria)
    slugs = list(dict.fromkeys(g.slug for g in grupo))
    dados = {"youtube_channel_id": cid, "perfis": slugs,
             "evidencia_url": evidencia_url(f0), "evidencia_nota": nota_evidencia(primeira.slug, f0),
             "status_md": status_fonte(f0.status_md, f0.propria)}
    item = Item("canal", primeira.slug, primeira.arquivo, f0.criador or f0.canal,
                f"canal:{cid}", "novo", linha=f0.linha,
                impressao=impressao([g.fonte.__dict__ for g in grupo]), dados=dados,
                origens=[{"arquivo": g.arquivo, "trecho": g.fonte.criador or g.fonte.canal,
                          "linha": g.fonte.linha} for g in grupo[1:]],
                proposto={"direito": proposto.value,
                          "statusMarkdown": status_fonte(f0.status_md, f0.propria),
                          "evidenciaNota": cortar(dados["evidencia_nota"])[0],
                          **({"conflito": sorted(p.value for p in propostos)}
                             if len(propostos) > 1 else {})},
                direito_proposto=proposto.value,
                direitos_aceitos=sorted(a.value for a in aceitos) or None)
    canal = ctx.db.scalar(select(CanalFonte).where(CanalFonte.youtube_channel_id == cid))
    if canal is None:
        return [item]
    item.base = _base("canal", canal)
    item.dados["canal_id"] = str(canal.id)
    item.atual = {"direito": canal.direito.value, "titulo": canal.title,
                  "evidenciaNota": cortar(canal.direito_evidencia_nota)[0]}
    item.trecho = canal.title
    if canal.archived:
        item.situacao, item.motivo = "diverge", "arquivado"
        return [item]
    item.situacao, item.motivo = ("igual", None) if canal.direito in aceitos \
        else ("diverge", "direito")
    out = [item]
    ligados = {link.perfil_id for link in canal.perfil_links}
    for slug in slugs:
        perfil = ctx.alvo.get(slug)
        if slug in ctx.alvo and (perfil is None or perfil.id not in ligados):
            g = next(x for x in grupo if x.slug == slug)
            out.append(Item("vinculo_canal", slug, g.arquivo, canal.title,
                            f"vinculo:{cid}:{slug}", "novo", linha=g.fonte.linha,
                            impressao=impressao([cid, slug]), base=_base("canal", canal),
                            dados={"canal_id": str(canal.id)},
                            atual={"perfis": len(ligados)}, proposto={"perfil": slug}))
    return out


# ---- imagens do perfil, persona e clipes (R9) ----

def imagem_no_perfil(db: Session, perfil: Perfil | None, sha: str) -> Image | None:
    if perfil is None:
        return None
    return db.scalar(select(Image).where(Image.perfil_id == perfil.id, Image.sha256 == sha)
                     .order_by(Image.created_at).limit(1))


def asset_da_imagem(db: Session, image_id: uuid.UUID) -> Asset | None:
    return db.scalar(select(Asset).join(AssetFile, AssetFile.asset_id == Asset.id)
                     .where(AssetFile.image_id == image_id))


def asset_por_nome(db: Session, perfil: Perfil | None, tipo: AssetTipo,
                   nome: str) -> Asset | None:
    if perfil is None:
        return None
    return db.scalar(select(Asset).where(
        Asset.perfil_id == perfil.id, Asset.tipo == tipo,
        func.lower(Asset.name) == nome.strip().lower()).order_by(Asset.created_at).limit(1))


def conteudo_por_sha(db: Session, perfil: Perfil | None, sha: str) -> Conteudo | None:
    if perfil is None:
        return None
    return db.scalar(select(Conteudo).where(Conteudo.perfil_id == perfil.id,
                                            Conteudo.video_sha256 == sha).limit(1))


def comparar_campos(atual: dict[str, Any], proposto: dict[str, Any]
                    ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Só os campos diferentes, lado a lado (textos cortados para a tela)."""
    dif = [k for k in proposto if (atual.get(k) or "") != (proposto.get(k) or "")]
    return ({k: cortar(atual.get(k) or "")[0] for k in dif},
            {k: cortar(proposto.get(k) or "")[0] for k in dif})
