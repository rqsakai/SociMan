"""Contexto de cada geração, montado no servidor (research R5).

Três blocos, do mais estável ao mais variável:
1. **perfil** (com `cache_control` no prompt): nome, nicho, idioma, bio, bordões, séries, paleta
   com nomes, CTA do card final e contas (o `_perfil_contexto` da 006 com a paleta);
2. **persona**: até 2 avatares ativos do perfil (os mais recentes), com cada texto cortado em
   1.000 caracteres. O avatar que está sendo editado entra como entidade, não como persona;
3. **entidade**: depende do tipo (asset, kit, postagem). Textos de terceiros (transcrição,
   título do vídeo e do canal, textos do OpenShorts, gancho) ficam separados, para o prompt
   delimitar (R6).

O valor atual do campo e a instrução vêm do formulário (o service valida); o resto nunca vem do
cliente. `faltante` diz ao modelo e à tela o que não existe: `kit`, `persona`, `transcricao`,
`bio`, `nicho`.

Spec 029 (R4, R9): num item da biblioteca sem perfil base, não há bloco do perfil nem persona
(só a entidade); o `faltante` não acusa o que é do perfil.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.assets.models import Asset, AssetTipo
from sociman_api.cortes.models import Corte
from sociman_api.ia.tipos import TipoCampo
from sociman_api.perfis.models import Conta, ContaStatus, Perfil, Platform
from sociman_api.perfis.platforms import PLATFORMS

PERSONAS_MAX = 2
PERSONA_TEXTO_MAX = 1000
TRANSCRICAO_MAX = 4000
TERCEIRO_MAX = 1000

# Limites e costumes de cada plataforma, ditos ao modelo (os limites do SociMan valem para todas).
PLATAFORMAS: dict[str, str] = {
    "tiktok": "TikTok: título curto e chamativo; descrição de 1 a 3 frases; hashtags de nicho.",
    "youtube": "YouTube Shorts: título que funcione na busca (até 100 caracteres); descrição "
               "com 2 a 4 frases e o tema do vídeo no começo.",
    "instagram": "Instagram Reels: legenda com gancho na primeira linha; hashtags no fim.",
    "kwai": "Kwai: título direto e popular; descrição curta.",
    "facebook": "Facebook Reels: descrição conversada, de 1 a 3 frases.",
    "x": "X: texto curto (o título vira o post); poucas hashtags.",
    "outra": "Rede de vídeos curtos: título curto, descrição de 1 a 3 frases.",
}

_ROTULOS_ASSET = {"prompt": "Descrição para prompts", "voice_tone": "Tom de voz",
                  "image_rules": "Regras de imagem", "name": "Nome", "description": "Notas"}


@dataclass(frozen=True)
class PerfilBloco:
    nome: str
    idioma: str = "pt-BR"
    nicho: str = ""
    bio: str = ""
    bordoes: tuple[str, ...] = ()
    series: tuple[str, ...] = ()
    paleta: tuple[tuple[str, str], ...] = ()  # (nome, hex)
    cta: str = ""
    contas: tuple[str, ...] = ()  # "TikTok @handle"


@dataclass(frozen=True)
class Persona:
    nome: str
    descricao: str = ""
    tom: str = ""


@dataclass(frozen=True)
class Contexto:
    perfil: PerfilBloco | None  # None = sem perfil base (spec 029)
    personas: tuple[Persona, ...] = ()
    entidade: tuple[tuple[str, str], ...] = ()  # (rótulo, texto da equipe)
    terceiros: tuple[tuple[str, str], ...] = ()  # (tipo, texto de terceiros)
    faltante: tuple[str, ...] = ()


def _corta(texto: str | None, limite: int) -> str:
    return (texto or "").strip()[:limite]


def plataforma_label(platform: Platform, platform_name: str = "") -> str:
    return platform_name if platform == Platform.outra and platform_name \
        else PLATFORMS[platform].label


def perfil_bloco(db: Session, perfil: Perfil) -> tuple[PerfilBloco, bool]:
    """O bloco do perfil e se o kit já foi salvo."""
    from sociman_api.marca.service_kit import current_tokens  # import tardio (ciclo)

    tokens, row = current_tokens(db, perfil.id)
    contas = db.scalars(
        select(Conta).where(Conta.perfil_id == perfil.id, Conta.archived_at.is_(None),
                            Conta.status != ContaStatus.encerrada)
        .order_by(Conta.created_at, Conta.id)
    )
    bloco = PerfilBloco(
        nome=perfil.name, idioma=perfil.language, nicho=perfil.niche, bio=perfil.bio,
        bordoes=tuple(tokens.catchphrases), series=tuple(tokens.series),
        paleta=tuple((c.nome, c.valor) for c in tokens.palette),
        cta=tokens.end_card.cta if tokens.end_card.ligado else "",
        contas=tuple(f"{plataforma_label(c.platform, c.platform_name)} @{c.handle}"
                     for c in contas),
    )
    return bloco, row is not None


def _personas(db: Session, perfil_id: uuid.UUID, exceto: uuid.UUID | None
              ) -> tuple[Persona, ...]:
    query = (select(Asset)
             .where(Asset.perfil_id == perfil_id, Asset.tipo == AssetTipo.avatar,
                    Asset.archived_at.is_(None))
             .order_by(Asset.created_at.desc(), Asset.id).limit(PERSONAS_MAX + 1))
    avatares = [a for a in db.scalars(query) if a.id != exceto][:PERSONAS_MAX]
    return tuple(Persona(nome=a.name, descricao=_corta(a.prompt, PERSONA_TEXTO_MAX),
                         tom=_corta(a.voice_tone, PERSONA_TEXTO_MAX)) for a in avatares)


def _asset(tipo: TipoCampo, asset: Asset) -> list[tuple[str, str]]:
    linhas = [("Tipo do asset", asset.tipo.value)]
    for campo in ("name", "description", "prompt", "voice_tone", "image_rules"):
        if campo in tipo.campos:
            continue  # o valor atual vem do formulário
        valor = getattr(asset, campo)
        if valor:
            linhas.append((_ROTULOS_ASSET[campo], _corta(valor, 2000)))
    if asset.tags:
        linhas.append(("Tags", ", ".join(asset.tags)))
    return linhas


def _kit(tipo: TipoCampo, perfil: PerfilBloco) -> list[tuple[str, str]]:
    if tipo.id == "kit.bordoes":
        return [("Séries do kit (o outro campo)", "; ".join(perfil.series) or "(nenhuma)")]
    return [("Bordões do kit (o outro campo)", "; ".join(perfil.bordoes) or "(nenhum)")]


def _origem(db: Session, corte: Corte) -> tuple[str, str]:
    """(título do vídeo de origem, canal), quando o corte veio de um envio."""
    if corte.envio_id is None:
        return corte.original_filename, ""
    from sociman_api.canais.models import CanalFonte
    from sociman_api.envios.models import Envio

    envio = db.get(Envio, corte.envio_id)
    if envio is None:
        return "", ""
    canal = db.get(CanalFonte, envio.canal_fonte_id) if envio.canal_fonte_id else None
    return envio.source_title, canal.title if canal else ""


def _postagem(tipo: TipoCampo, db: Session, corte: Corte | None, conta: Conta,
              postagem: Any | None, conteudo: Any | None
              ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    entidade = [
        ("Plataforma alvo", PLATAFORMAS.get(conta.platform.value, PLATAFORMAS["outra"])),
        ("Conta", f"{plataforma_label(conta.platform, conta.platform_name)} @{conta.handle}"),
    ]
    if postagem is not None:  # os outros campos já salvos, para o texto combinar
        outros = {"titulo": ("Título atual da postagem", postagem.titulo),
                  "descricao": ("Descrição atual da postagem", postagem.descricao),
                  "hashtags": ("Hashtags atuais da postagem", " ".join(postagem.hashtags))}
        entidade += [v for k, v in outros.items() if k not in tipo.campos and v[1]]
    if corte is None:
        # Spec 014: vídeo próprio (sem corte): título, origem e duração; sem transcrição.
        if conteudo is not None:
            if conteudo.titulo:
                entidade.append(("Título do conteúdo", conteudo.titulo))
            entidade.append(("Origem", "vídeo próprio enviado pela equipe"))
            if conteudo.duration_ms:
                entidade.append(("Duração", f"{round(conteudo.duration_ms / 1000)} s"))
        return entidade, []
    video_titulo, canal = _origem(db, corte)
    terceiros = [(nome, _corta(valor, TERCEIRO_MAX)) for nome, valor in (
        ("titulo_do_video", video_titulo), ("canal", canal),
        ("titulo_do_gerador", corte.openshorts_title),
        ("descricao_do_gerador", corte.openshorts_description),
        ("gancho", corte.hook_text),
    ) if valor]
    terceiros.append(("transcricao", _corta(corte.transcript, TRANSCRICAO_MAX) or "(sem fala)"))
    return entidade, terceiros


@dataclass(frozen=True)
class CenaInfo:
    """Spec 010: o que a IA da cena recebe como contexto (da cena salva ou do formulário, com a
    posse conferida). A descrição do avatar e o cenário vão só como contexto: não são campos."""

    avatar: Asset | None = None
    arquivo_rotulo: str | None = None  # o look ou a pose escolhidos
    cenario: Asset | None = None
    produto_nome: str | None = None
    produto_com_foto: bool = False
    fala: str | None = None
    duracao_s: int | None = None
    modo: str | None = None
    atuais: tuple[tuple[str, str], ...] = ()  # (campo, valor salvo) dos 4 campos da IA


_ROTULOS_CENA = {"acao": "Ação atual", "camera": "Detalhe de câmera atual",
                 "estilo": "Iluminação e estilo atuais", "audio": "Áudio ambiente atual"}


def _cena(tipo: TipoCampo, cena: CenaInfo) -> list[tuple[str, str]]:
    linhas: list[tuple[str, str]] = []
    if cena.avatar is not None:
        linhas.append(("Avatar (descrição fixa; não muda)", _corta(cena.avatar.prompt, 2000)
                       or cena.avatar.name))
        if cena.avatar.image_rules:
            linhas.append(("Regras de imagem do avatar", _corta(cena.avatar.image_rules, 2000)))
        if cena.arquivo_rotulo:
            linhas.append(("Look ou pose da cena", cena.arquivo_rotulo))
    if cena.cenario is not None:
        linhas.append(("Cenário (prompt do ambiente; não muda)",
                       _corta(cena.cenario.prompt, 2000) or cena.cenario.name))
    if cena.produto_nome:
        foto = " (com foto de referência)" if cena.produto_com_foto else " (sem foto)"
        linhas.append(("Produto", cena.produto_nome + foto))
    if cena.duracao_s:
        linhas.append(("Duração", f"{cena.duracao_s} s"))
    if cena.modo:
        linhas.append(("Modo do Flow", cena.modo))
    if cena.fala:
        linhas.append(("Fala para a câmera (pt-BR)", cena.fala))
    linhas += [(_ROTULOS_CENA[c], v) for c, v in cena.atuais if c not in tipo.campos and v]
    return linhas


def montar(db: Session, tipo: TipoCampo, perfil: Perfil | None, *, asset: Asset | None = None,
           corte: Corte | None = None, conta: Conta | None = None,
           postagem: Any | None = None, conteudo: Any | None = None,
           cena: CenaInfo | None = None) -> Contexto:
    avatar = asset if asset is not None else (cena.avatar if cena is not None else None)
    if perfil is None:  # só os tipos de asset e de cena chegam aqui sem perfil
        sem_perfil: list[tuple[str, str]] = []
        if tipo.entidade == "cena" and cena is not None:
            sem_perfil = _cena(tipo, cena)
        elif tipo.entidade == "asset" and asset is not None:
            sem_perfil = _asset(tipo, asset)
        return Contexto(perfil=None, entidade=tuple(sem_perfil))
    bloco, kit_salvo = perfil_bloco(db, perfil)
    personas = _personas(db, perfil.id, avatar.id if avatar is not None else None)
    entidade: list[tuple[str, str]] = []
    terceiros: list[tuple[str, str]] = []
    if tipo.entidade == "cena" and cena is not None:
        entidade = _cena(tipo, cena)
    elif tipo.entidade == "asset" and asset is not None:
        entidade = _asset(tipo, asset)
    elif tipo.entidade == "kit":
        entidade = _kit(tipo, bloco)
    elif tipo.entidade == "postagem" and conta is not None and (
            corte is not None or conteudo is not None):
        entidade, terceiros = _postagem(tipo, db, corte, conta, postagem, conteudo)

    faltante = []
    if not kit_salvo:
        faltante.append("kit")
    if not personas and not (avatar is not None and avatar.tipo == AssetTipo.avatar):
        faltante.append("persona")
    if tipo.entidade == "postagem" and (corte is not None or conteudo is not None) \
            and not (corte is not None and (corte.transcript or "").strip()):
        faltante.append("transcricao")
    if not perfil.bio.strip() and tipo.id != "perfil.bio":
        faltante.append("bio")
    if not perfil.niche.strip():
        faltante.append("nicho")
    return Contexto(perfil=bloco, personas=personas, entidade=tuple(entidade),
                    terceiros=tuple(terceiros), faltante=tuple(faltante))
