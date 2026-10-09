"""Pré-visualização (research R7): varrer → mapear → ler → conciliar → Redis.

Nada vai para o PostgreSQL, o MinIO ou a pasta da agência. O resultado (itens com os `dados`, as
impressões digitais dos arquivos usados e a `base` de versões) fica em `agencia:previa:<uuid>`
por 30 min, de uso único (o confirmar faz `GETDEL`). Os logs só têm contagens.
"""

import hashlib
import json
import logging
import re
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api import imaging
from sociman_api.agencia import conciliar, leitores, mapa, pastas, schemas
from sociman_api.agencia.conciliar import Ctx, _Linha
from sociman_api.agencia.itens import Item, cortar, impressao, motivo_texto
from sociman_api.agencia.leitores import NaoReconhecido
from sociman_api.assets import tipos as asset_tipos
from sociman_api.assets.models import Asset, AssetTipo
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User
from sociman_api.conteudos import video_proprio
from sociman_api.cortes.probe import InvalidVideo, probe
from sociman_api.errors import ApiError
from sociman_api.perfis.models import Image, Perfil
from sociman_api.redis import get_redis

log = logging.getLogger(__name__)

TTL = timedelta(minutes=30)
CHAVE = "agencia:previa:{}"
LOGO_MAX = imaging.MAX_BYTES  # o upload do logo (003) aceita até 5 MB
AVATAR_PADRAO = "Avatar do perfil"
EXPIRADA = "Esta pré-visualização já foi usada ou expirou; leia a pasta de novo"
_ORDEM = {t: i for i, t in enumerate(("perfil", "conta", "guia", "anotacao", "imagem_logo",
                                      "asset", "arquivo_asset", "canal", "vinculo_canal",
                                      "clipe", "sugestao_bordao", "arquivo"))}
_DATA_PASTA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _Leitura:
    """O acumulado de uma leitura: itens, arquivos usados e os não reconhecidos."""

    def __init__(self) -> None:
        self.itens: list[Item] = []
        self.usados: dict[str, str] = {}  # id do arquivo → sha256
        self.nao_reconhecidos: list[schemas.AgenciaNaoReconhecido] = []

    def fora(self, arquivo: str, motivo: str, tipo: str = "arquivo", **kw: Any) -> Item:
        item = Item(tipo, kw.pop("perfil_slug", None), arquivo, kw.pop("trecho", ""),
                    kw.pop("chave", f"arquivo:{arquivo}"), "fora", motivo=motivo, **kw)
        self.itens.append(item)
        return item

    def texto(self, arq: pastas.Arquivo, perfil_slug: str | None = None) -> str | None:
        data = pastas.ler_bytes(arq, pastas.MD_MAX)
        if data is None:
            self.fora(arq.id, "arquivo_grande", perfil_slug=perfil_slug)
            return None
        try:
            texto = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            self.nao_reconhecido(arq.id, ["texto em UTF-8"], perfil_slug)
            return None
        self.usados[arq.id] = hashlib.sha256(data).hexdigest()
        return texto

    def nao_reconhecido(self, arquivo: str, faltou: list[str], perfil_slug: str | None) -> None:
        self.usados.pop(arquivo, None)
        self.nao_reconhecidos.append(schemas.AgenciaNaoReconhecido(arquivo=arquivo, faltou=faltou))
        self.fora(arquivo, "nao_reconhecido", perfil_slug=perfil_slug,
                  proposto={"faltou": faltou})


def _pasta_perfil(rel: str) -> str | None:
    partes = rel.split("/")
    return partes[1] if len(partes) > 2 and partes[0] == "perfis" else None


# ---- imagens ----

def _validar(data: bytes, kind: str, max_bytes: int = pastas.IMG_MAX) -> imaging.ImageInfo:
    return imaging.validate_image(data, kind, max_bytes=max_bytes,  # type: ignore[arg-type]
                                  too_large_message=asset_tipos.TOO_LARGE)


def _bytes_imagem(lt: _Leitura, arq: pastas.Arquivo, slug: str | None,
                  limite: int = pastas.IMG_MAX) -> tuple[bytes, str] | None:
    data = pastas.ler_bytes(arq, limite)
    if data is None:
        lt.fora(arq.id, "arquivo_grande", tipo="asset", perfil_slug=slug,
                trecho=PurePosixPath(arq.rel).name)
        return None
    sha = hashlib.sha256(data).hexdigest()
    lt.usados[arq.id] = sha
    return data, sha


def _imagem_invalida(lt: _Leitura, item: Item, erro: ApiError) -> None:
    item.situacao, item.motivo = "fora", "imagem_invalida"
    item.proposto = {**(item.proposto or {}), "erro": erro.message}
    lt.usados.pop(item.arquivo, None)


def _imagens_perfil(ctx: Ctx, lt: _Leitura, slug: str, arqs: list[pastas.Arquivo]) -> None:
    perfil = ctx.alvo.get(slug)
    avatar: list[tuple[pastas.Arquivo, str, str, bytes]] = []  # (arq, papel, rótulo, bytes)
    for arq in arqs:
        dentro = arq.rel.split("/assets/", 1)[1]
        nome = PurePosixPath(dentro).stem
        if dentro.lower().startswith("logo."):
            lido = _bytes_imagem(lt, arq, slug, LOGO_MAX)
            if lido is None:
                continue
            data, sha = lido
            item = Item("imagem_logo", slug, arq.id, dentro, f"logo:{slug}:{sha}", "novo",
                        impressao=sha, bytes=len(data), dados={"arquivo": arq.id},
                        proposto={"arquivo": dentro, "sha256": sha[:12]})
            lt.itens.append(item)
            try:
                _validar(data, "logo", LOGO_MAX)
            except ApiError as e:
                _imagem_invalida(lt, item, e)
                continue
            if perfil is not None:
                item.base = conciliar._base("perfil", perfil)
                logo = ctx.db.get(Image, perfil.logo_image_id) if perfil.logo_image_id else None
                if logo is not None:
                    item.atual = {"sha256": logo.sha256[:12]}
                    item.situacao, item.motivo = ("igual", None) if logo.sha256 == sha \
                        else ("diverge", "valor")
            continue
        lido = _bytes_imagem(lt, arq, slug)
        if lido is None:
            continue
        data, sha = lido
        if dentro.startswith("avatar-poses/") or nome.lower().startswith("avatar"):
            papel = "pose" if dentro.startswith("avatar-poses/") else "referencia"
            rotulo = re.sub(r"^avatar-?\d*-?", "", nome).replace("-", " ").strip() or nome
            avatar.append((arq, papel, rotulo[:60], data))
            continue
        item = Item("asset", slug, arq.id, dentro, f"img:{slug}:{sha}", "novo", impressao=sha,
                    bytes=len(data))
        lt.itens.append(item)
        tipo = AssetTipo.imagem
        try:
            if dentro.startswith("stickers/"):
                try:
                    imaging.validate_image(data, "watermark", max_bytes=pastas.IMG_MAX,
                                           too_large_message=asset_tipos.TOO_LARGE)
                    tipo = AssetTipo.sticker
                except ApiError:
                    _validar(data, "imagem")
            else:
                _validar(data, "imagem")
        except ApiError as e:
            _imagem_invalida(lt, item, e)
            continue
        item.dados = {"tipo": tipo.value, "name": nome[:80], "arquivo": arq.id}
        item.proposto = {"tipo": tipo.value, "nome": nome[:80]}
        if conciliar.imagem_no_perfil(ctx.db, perfil, sha) is not None:
            item.situacao = "igual"
    if avatar:
        _avatar_do_perfil(ctx, lt, slug, perfil, avatar)


def _avatar_do_perfil(ctx: Ctx, lt: _Leitura, slug: str, perfil: Perfil | None,
                      avatar: list[tuple[pastas.Arquivo, str, str, bytes]]) -> None:
    asset: Asset | None = None
    novos: list[Item] = []
    for arq, papel, rotulo, data in avatar:
        sha = lt.usados[arq.id]
        dentro = arq.rel.split("/assets/", 1)[1]
        item = Item("arquivo_asset", slug, arq.id, dentro, f"img:{slug}:{sha}", "novo",
                    impressao=sha, bytes=len(data),
                    dados={"arquivo": arq.id, "role": papel,
                           **({"label": rotulo} if papel == "pose" else {})},
                    proposto={"papel": papel, **({"rotulo": rotulo} if papel == "pose" else {})})
        lt.itens.append(item)
        try:
            _validar(data, "avatar")
        except ApiError as e:
            _imagem_invalida(lt, item, e)
            continue
        img = conciliar.imagem_no_perfil(ctx.db, perfil, sha)
        if img is not None:
            item.situacao = "igual"
            achado = conciliar.asset_da_imagem(ctx.db, img.id)
            if asset is None and achado is not None and achado.tipo == AssetTipo.avatar:
                asset = achado
        else:
            novos.append(item)
    if not novos:
        return
    asset = asset or conciliar.asset_por_nome(ctx.db, perfil, AssetTipo.avatar, AVATAR_PADRAO)
    if asset is not None:
        for item in novos:
            item.dados["asset_id"] = str(asset.id)
            item.atual = {"asset": asset.name}
        return
    chave = f"asset:{slug}:avatar-perfil"
    lt.itens.append(Item("asset", slug, novos[0].arquivo, AVATAR_PADRAO, chave, "novo",
                         impressao=impressao(chave),
                         dados={"tipo": "avatar", "name": AVATAR_PADRAO},
                         proposto={"tipo": "avatar", "nome": AVATAR_PADRAO}))
    for item in novos:
        item.dados["asset_chave"] = chave


# ---- persona (R9) ----

def _persona(ctx: Ctx, lt: _Leitura, md_arq: pastas.Arquivo | None,
             imgs: list[pastas.Arquivo]) -> schemas.AgenciaPersona | None:
    if md_arq is None:
        for arq in imgs:
            lt.fora(arq.id, "fora_do_mapeamento", tipo="arquivo_asset")
        return None
    texto = lt.texto(md_arq)
    if texto is None:
        return None
    try:
        p = leitores.ler_persona(texto)
    except NaoReconhecido as e:
        lt.nao_reconhecido(md_arq.id, e.faltou, None)
        return None
    por_nome = {PurePosixPath(a.rel).name.lower(): a for a in imgs}
    lidas: list[tuple[pastas.Arquivo, leitores.ImagemPersona, bytes, str]] = []
    for ip in p.imagens:
        arq = por_nome.pop(ip.arquivo.lower(), None)
        if arq is None:
            lt.fora(md_arq.id, "arquivo_citado_nao_encontrado", tipo="arquivo_asset",
                    trecho=ip.arquivo, linha=ip.linha, chave=f"persona:citada:{ip.arquivo}")
            continue
        lido = _bytes_imagem(lt, arq, None)
        if lido is not None:
            lidas.append((arq, ip, *lido))
    for arq in por_nome.values():  # imagem na pasta sem linha na tabela: referência sem look
        lido = _bytes_imagem(lt, arq, None)
        if lido is not None:
            lidas.append((arq, leitores.ImagemPersona(PurePosixPath(arq.rel).name, "", "", 0),
                          *lido))

    # O perfil padrão: o que já tem uma imagem da persona (pelo SHA-256).
    padrao: Perfil | None = None
    for _, _, _, sha in lidas:
        img = ctx.db.scalar(select(Image).join(Perfil, Perfil.id == Image.perfil_id).where(
            Image.sha256 == sha, Perfil.archived_at.is_(None)).limit(1))
        if img is not None:
            padrao = ctx.db.get(Perfil, img.perfil_id)
            break
    slug = padrao.slug if padrao is not None else None
    if padrao is not None:
        ctx.alvo.setdefault(padrao.slug, padrao)
    exige = padrao is None

    nome = p.nome[:80] or "Persona"
    campos = {"prompt": p.prompt[:2000], "voice_tone": p.voz[:500] or None,
              "image_rules": p.regras[:2000] or None}
    chave_avatar = f"persona:avatar:{conciliar.md.normalizar(nome)}"
    avatar = Item("asset", slug, md_arq.id, f"Persona: {nome}", chave_avatar, "novo",
                  linha=p.linha, impressao=impressao(campos), exige_perfil=exige,
                  dados={"tipo": "avatar", "name": nome, **campos, "persona": True},
                  proposto={"nome": nome, "prompt": cortar(p.prompt)[0],
                            "voiceTone": cortar(p.voz)[0], "imageRules": cortar(p.regras)[0]})
    lt.itens.append(avatar)
    asset: Asset | None = None
    if padrao is not None:
        for _, _, _, sha in lidas:
            img = conciliar.imagem_no_perfil(ctx.db, padrao, sha)
            achado = conciliar.asset_da_imagem(ctx.db, img.id) if img is not None else None
            if achado is not None and achado.tipo == AssetTipo.avatar:
                asset = achado
                break
        asset = asset or conciliar.asset_por_nome(ctx.db, padrao, AssetTipo.avatar, nome)
    if asset is not None:
        avatar.base = conciliar._base("asset", asset)
        avatar.dados["asset_id"] = str(asset.id)
        atual = {"prompt": asset.prompt, "voice_tone": asset.voice_tone,
                 "image_rules": asset.image_rules}
        a, b = conciliar.comparar_campos(atual, campos)
        avatar.situacao, avatar.motivo = ("igual", None) if not a else ("diverge", "valor")
        if a:
            avatar.atual, avatar.proposto = a, b

    for arq, ip, data, sha in lidas:
        item = Item("arquivo_asset", slug, arq.id, ip.look or ip.arquivo, f"img:persona:{sha}",
                    "novo", linha=ip.linha or None, impressao=sha, bytes=len(data),
                    exige_perfil=exige,
                    dados={"arquivo": arq.id, "role": "referencia", "look": ip.look[:60] or None,
                           "uso": ip.uso[:200] or None, "persona": True},
                    proposto={"papel": "referencia", "look": ip.look, "uso": ip.uso})
        lt.itens.append(item)
        try:
            _validar(data, "avatar")
        except ApiError as e:
            _imagem_invalida(lt, item, e)
            continue
        if conciliar.imagem_no_perfil(ctx.db, padrao, sha) is not None:
            item.situacao = "igual"
        elif asset is not None:
            item.dados["asset_id"] = str(asset.id)
        else:
            item.dados["asset_chave"] = chave_avatar

    for nome_c, prompt, linha in p.cenarios:
        chave = f"persona:cenario:{conciliar.md.normalizar(nome_c)}"
        item = Item("asset", slug, md_arq.id, f"Cenário: {nome_c}", chave, "novo", linha=linha,
                    impressao=impressao(prompt), exige_perfil=exige,
                    dados={"tipo": "cenario", "name": nome_c[:80], "prompt": prompt[:2000],
                           "persona": True},
                    proposto={"nome": nome_c, "prompt": cortar(prompt)[0]})
        lt.itens.append(item)
        existente = conciliar.asset_por_nome(ctx.db, padrao, AssetTipo.cenario, nome_c)
        if existente is not None:
            item.base = conciliar._base("asset", existente)
            item.dados["asset_id"] = str(existente.id)
            a, b = conciliar.comparar_campos({"prompt": existente.prompt}, {"prompt": prompt})
            item.situacao, item.motivo = ("igual", None) if not a else ("diverge", "valor")
            if a:
                item.atual, item.proposto = a, b
    return schemas.AgenciaPersona(perfil_padrao=slug, exige_perfil=exige)


# ---- clipes (Q2) ----

def _clipes(ctx: Ctx, lt: _Leitura, arqs: list[pastas.Arquivo],
            registros: dict[str, tuple[str, dict[str, leitores.RegistroLinha]]]) -> None:
    usados: set[tuple[str, str]] = set()
    for arq in arqs:
        pasta, data_pasta, nome = arq.rel.split("/")
        slug = conciliar.slug_de(pasta)
        stem = PurePosixPath(nome).stem
        if not _DATA_PASTA.match(data_pasta):
            lt.fora(arq.id, "caminho_de_clipe", tipo="clipe", perfil_slug=slug, trecho=stem)
            continue
        reg_arquivo, reg = registros.get(slug, ("", {}))
        linha = reg.get(stem)
        if linha is None:
            lt.fora(arq.id, "video_sem_linha", tipo="clipe", perfil_slug=slug, trecho=stem,
                    chave=f"clipe:{slug}:{stem}")
            continue
        usados.add((slug, stem))
        item = Item("clipe", slug, arq.id, stem, f"clipe:{slug}:{stem}", "novo",
                    linha=linha.linha, bytes=arq.bytes,
                    proposto={"titulo": (linha.titulo or stem)[:video_proprio.TITULO_MAX],
                              "data": linha.data})
        lt.itens.append(item)
        try:
            probe(arq.path, max_duration_s=video_proprio.MAX_DURATION_S,
                  min_duration_s=video_proprio.MIN_DURATION_S,
                  max_bytes=video_proprio.max_bytes(), too_long=video_proprio.TOO_LONG,
                  too_short=video_proprio.TOO_SHORT, too_big=video_proprio.TOO_BIG)
        except InvalidVideo as e:
            item.situacao, item.motivo = "fora", "video_invalido"
            item.proposto = {**(item.proposto or {}), "erro": e.message}
            continue
        sha = pastas.sha256_arquivo(arq.path)
        lt.usados[arq.id] = sha
        item.chave, item.impressao = f"clipe:{slug}:{sha}", sha
        nota = " · ".join(x for x in (
            f"registro-clipes.md · {linha.id}", linha.data or "",
            f"Fonte: {linha.fonte}" if linha.fonte else "", linha.produto, linha.obs) if x)
        item.dados = {"arquivo": arq.id, "titulo": item.proposto["titulo"],  # type: ignore[index]
                      "filename": nome, "size": arq.bytes, "sha256": sha, "nota": nota[:4000]}
        if conciliar.conteudo_por_sha(ctx.db, ctx.alvo.get(slug), sha) is not None:
            item.situacao = "igual"
    for slug, (reg_arquivo, reg) in registros.items():
        for ident, linha in reg.items():
            if (slug, ident) not in usados:
                lt.fora(reg_arquivo, "linha_sem_video", tipo="clipe", perfil_slug=slug,
                        trecho=ident, linha=linha.linha, chave=f"clipe:{slug}:{ident}")


# ---- montagem ----

def ler(db: Session, youtube: Callable[[], Any] | None) -> tuple[_Leitura, schemas.AgenciaPersona | None]:
    """Lê as duas raízes e concilia tudo (sem gravar). 503/413 antes de qualquer item."""
    shared, clipes = pastas.varrer("shared"), pastas.varrer("clipes")
    ctx = Ctx(db, youtube, perfis={p.slug: p for p in db.scalars(select(Perfil))})
    lt = _Leitura()
    for link in shared.links_fora + clipes.links_fora:
        lt.fora(link, "link_para_fora")
    por_pasta: dict[str, dict[str, list[pastas.Arquivo]]] = defaultdict(lambda: defaultdict(list))
    index: pastas.Arquivo | None = None
    persona_md: pastas.Arquivo | None = None
    persona_imgs: list[pastas.Arquivo] = []
    videos: list[pastas.Arquivo] = []
    for arq in shared.arquivos + clipes.arquivos:
        leitor, motivo = mapa.classificar(arq.id)
        if leitor is None:
            lt.fora(arq.id, motivo or "fora_do_mapeamento")
        elif leitor == "index":
            index = arq
        elif leitor == "persona":
            persona_md = arq
        elif leitor == "imagem_persona":
            persona_imgs.append(arq)
        elif leitor == "clipe":
            videos.append(arq)
        else:
            por_pasta[_pasta_perfil(arq.rel)][leitor].append(arq)  # type: ignore[index]

    pastas_index: dict[str, leitores.IndexLinha] = {}
    if index is not None and (texto_index := lt.texto(index)) is not None:
        try:
            pastas_index = {ln.slug: ln for ln in leitores.ler_index(texto_index)}
        except NaoReconhecido as e:
            lt.nao_reconhecido(index.id, e.faltou, None)

    fontes: list[_Linha] = []
    registros: dict[str, tuple[str, dict[str, leitores.RegistroLinha]]] = {}
    vistos: set[str] = set()
    for pasta in sorted(por_pasta):
        grupo = por_pasta[pasta]
        slug = conciliar.slug_de(pasta)
        perfil_md = grupo.get("perfil", [None])[0]
        lido: leitores.PerfilLido | None = None
        if slug in vistos:  # duas pastas com o mesmo slug: a segunda fica fora inteira
            for arqs in grupo.values():
                for arq in arqs:
                    lt.fora(arq.id, "slug_em_uso", perfil_slug=None)
            continue
        vistos.add(slug)
        if perfil_md is not None and (texto := lt.texto(perfil_md, slug)) is not None:
            try:
                lido = leitores.ler_perfil(texto, pasta)
            except NaoReconhecido as e:
                lt.nao_reconhecido(perfil_md.id, e.faltou, slug)
        if lido is None:
            lt.itens.append(conciliar.perfil_sem_md(
                ctx, pasta, perfil_md.id if perfil_md else f"shared:perfis/{pasta}/"))
        else:
            arquivo = perfil_md.id  # type: ignore[union-attr]
            lt.itens += conciliar.perfil_item(ctx, lido, arquivo)
            lt.itens += conciliar.conta_items(ctx, slug, lido.contas, arquivo)
            lt.itens += conciliar.guia_item(ctx, slug, lido, arquivo)
            lt.itens += conciliar.sugestao_items(ctx, slug, lido, arquivo)
            lt.itens += conciliar.anotacao_items(ctx, slug, arquivo, lido.anotacoes)
            existentes = {a.rel for arqs in grupo.values() for a in arqs}
            for citada in lido.citadas:
                if citada not in existentes and "nao-usar-ainda" not in citada.lower():
                    lt.fora(arquivo, "arquivo_citado_nao_encontrado", tipo="asset",
                            perfil_slug=slug, trecho=citada.rsplit("/", 1)[-1],
                            chave=f"citada:{slug}:{citada}")
        for leitor, ler_fn in (("pesquisa", leitores.ler_pesquisa),
                               ("ideias", leitores.ler_ideias)):
            for arq in grupo.get(leitor, []):
                if (texto := lt.texto(arq, slug)) is not None:
                    lt.itens += conciliar.anotacao_items(ctx, slug, arq.id, ler_fn(texto))
        for arq in grupo.get("fontes", []):
            if (texto := lt.texto(arq, slug)) is not None:
                try:
                    fontes += [_Linha(slug, arq.id, f) for f in leitores.ler_fontes(texto)]
                except NaoReconhecido as e:
                    lt.nao_reconhecido(arq.id, e.faltou, slug)
        for arq in grupo.get("registro", []):
            if (texto := lt.texto(arq, slug)) is not None:
                try:
                    registros[slug] = (arq.id, leitores.ler_registro(texto))
                except NaoReconhecido as e:
                    lt.nao_reconhecido(arq.id, e.faltou, slug)
        _imagens_perfil(ctx, lt, slug, grupo.get("imagem_perfil", []))
    for slug_index, ln in pastas_index.items():
        if conciliar.slug_de(slug_index) not in vistos:
            lt.itens.append(Item("perfil", conciliar.slug_de(slug_index), index.id,  # type: ignore[union-attr]
                                 f"INDEX.md: {ln.nome or slug_index}",
                                 f"perfil:{conciliar.slug_de(slug_index)}", "fora",
                                 linha=ln.linha, motivo="sem_perfil_md"))

    persona = _persona(ctx, lt, persona_md, persona_imgs)
    _clipes(ctx, lt, videos, registros)
    try:
        lt.itens += conciliar.canal_items(ctx, fontes)
    finally:
        ctx.fechar()
    for item in lt.itens:
        conciliar.dependente_fora(ctx, item)
    lt.itens.sort(key=lambda i: _ORDEM.get(i.tipo, 99))
    for n, item in enumerate(lt.itens, 1):
        item.n = n
    return lt, persona


# ---- saída ----

def escolha_padrao(item: Item) -> schemas.AgenciaEscolhaPadrao | None:
    if item.situacao == "novo":
        return schemas.AgenciaEscolhaPadrao(marcado=True, direito=item.direito_proposto  # type: ignore[arg-type]
                                     if item.tipo == "canal" else None)
    if item.situacao == "diverge" and item.motivo != "arquivado":
        return schemas.AgenciaEscolhaPadrao(usar="sociman", direito=item.direito_proposto  # type: ignore[arg-type]
                                     if item.motivo == "direito" else None)
    return None


def item_out(item: Item) -> schemas.AgenciaItemPrevia:
    return schemas.AgenciaItemPrevia(
        n=item.n, tipo=item.tipo, perfil_slug=item.perfil_slug,  # type: ignore[arg-type]
        origem=schemas.AgenciaOrigem(arquivo=item.arquivo, trecho=item.trecho, linha=item.linha),
        origens=[schemas.AgenciaOrigem(**o) for o in item.origens],
        situacao=item.situacao, motivo=item.motivo,  # type: ignore[arg-type]
        motivo_texto=motivo_texto(item.motivo), atual=item.atual, proposto=item.proposto,
        bytes=item.bytes, escolha_padrao=escolha_padrao(item),
        direitos_aceitos=item.direitos_aceitos,  # type: ignore[arg-type]
        exige_perfil=item.exige_perfil)


def contagens(itens: list[Item], nao_reconhecidos: int = 0) -> schemas.AgenciaContagens:
    c = schemas.AgenciaContagens(nao_reconhecido=nao_reconhecidos)
    for item in itens:
        campo = item.situacao
        setattr(c, campo, getattr(c, campo) + 1)
    return c


def em_andamento(db: Session) -> None:
    from sociman_api.agencia import aplicar

    if aplicar.processando(db) is not None:
        raise ApiError(409, "importacao_em_andamento",
                       "Já há uma importação em andamento; espere ela terminar")


def montar(db: Session, actor: Actor, youtube: Callable[[], Any] | None,
           agora: datetime | None = None) -> schemas.AgenciaPrevia:
    agora = agora or datetime.now(UTC)
    em_andamento(db)
    lt, persona = ler(db, youtube)
    previa_id = uuid.uuid4()
    estado = {
        "autorId": str(actor.user_id), "criadaEm": agora.isoformat(),
        "raizes": {r: str(pastas.raiz_path(r)) for r in pastas.RAIZES},
        "arquivos": lt.usados, "itens": [i.json() for i in lt.itens],
        "persona": persona.model_dump() if persona else None,
    }
    get_redis().set(CHAVE.format(previa_id), json.dumps(estado), ex=int(TTL.total_seconds()))
    cont = contagens(lt.itens, len(lt.nao_reconhecidos))
    log.info("agencia previa: %d itens, %d arquivos usados, contagens=%s", len(lt.itens),
             len(lt.usados), cont.model_dump())
    novos = sum(i.bytes or 0 for i in lt.itens if i.situacao in ("novo", "diverge"))
    return schemas.AgenciaPrevia(previa_id=previa_id, expira_em=agora + TTL, contagens=cont,
                          bytes_novos=novos, arquivos_nao_reconhecidos=lt.nao_reconhecidos,
                          persona=persona, itens=[item_out(i) for i in lt.itens])


def ler_estado(previa_id: uuid.UUID, actor: Actor) -> dict[str, Any]:
    """O estado guardado, sem consumir: 409 se expirou ou já foi usada; 404 se é de outro
    usuário (sem apagar a prévia dele)."""
    bruto = get_redis().get(CHAVE.format(previa_id))
    if bruto is None:
        raise ApiError(409, "previa_expirada", EXPIRADA)
    estado = json.loads(bruto)
    if estado.get("autorId") != str(actor.user_id):
        raise ApiError(404, "not_found", "Pré-visualização não encontrada")
    return estado


def consumir(previa_id: uuid.UUID) -> None:
    """Uso único: só quem apaga a chave segue (o 2º clique recebe 409)."""
    if not get_redis().getdel(CHAVE.format(previa_id)):
        raise ApiError(409, "previa_expirada", EXPIRADA)


# ---- estado da tela (FR-028) ----

def estado(db: Session) -> schemas.AgenciaEstado:
    from sociman_api.agencia import aplicar
    from sociman_api.agencia.models import Importacao, ImportacaoEstado

    aplicar.marcar_interrompidas(db)
    raizes = {}
    for r in pastas.RAIZES:
        ok, motivo = pastas.disponivel(r)
        raizes[r] = schemas.AgenciaRaiz(disponivel=ok, motivo=motivo)

    def ref(imp: Importacao | None) -> schemas.AgenciaImportacaoRef | None:
        if imp is None:
            return None
        user = db.get(User, imp.criada_por)
        from sociman_api.perfis.schemas import UserRef

        return schemas.AgenciaImportacaoRef(
            id=imp.id, estado=imp.estado.value, criada_em=imp.criada_em,  # type: ignore[arg-type]
            criada_por=UserRef(id=user.id, name=user.name) if user else None)

    ultima = db.scalar(select(Importacao).order_by(Importacao.criada_em.desc(),
                                                   Importacao.id.desc()).limit(1))
    andamento = aplicar.processando(db)
    concluidas = db.scalars(select(Importacao).where(
        Importacao.estado == ImportacaoEstado.concluida)
        .order_by(Importacao.criada_em.desc())).all()
    perfis: dict[str, schemas.AgenciaPerfilEstado] = {}
    for imp in concluidas:
        por_slug: dict[str, dict[str, str]] = defaultdict(dict)
        for arquivo, sha in imp.arquivos.items():
            slug = _slug_do_arquivo(arquivo)
            if slug is not None:
                por_slug[slug][arquivo] = sha
        for slug, arquivos in por_slug.items():
            if slug not in perfis:
                perfis[slug] = schemas.AgenciaPerfilEstado(
                    slug=slug, ultima_importacao_em=imp.criada_em,
                    arquivos_mudaram=_mudaram(arquivos, raizes))
    return schemas.AgenciaEstado(raizes=schemas.AgenciaRaizes(**raizes), ultima=ref(ultima),
                          perfis=sorted(perfis.values(), key=lambda p: p.slug),
                          em_andamento=ref(andamento))


def _slug_do_arquivo(arquivo: str) -> str | None:
    raiz, _, rel = arquivo.partition(":")
    partes = rel.split("/")
    if raiz == "shared" and len(partes) > 2 and partes[0] == "perfis":
        return conciliar.slug_de(partes[1])
    if raiz == "clipes" and len(partes) == 3:
        return conciliar.slug_de(partes[0])
    return None


def _mudaram(arquivos: dict[str, str], raizes: dict[str, schemas.AgenciaRaiz]) -> bool:
    """Só lê os bytes dos arquivos usados na última importação (nada é montado)."""
    for arquivo, sha in arquivos.items():
        raiz, _, rel = arquivo.partition(":")
        if not raizes[raiz].disponivel:
            return True
        path = pastas.raiz_path(raiz) / rel  # type: ignore[arg-type]
        try:
            if not path.is_file() or pastas.sha256_cache(path) != sha:
                return True
        except OSError:
            return True
    return False
