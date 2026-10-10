"""O plano do roteiro pelo Claude (spec 011, FR-013 e FR-014), puro: o schema da saída, a mensagem
e a conferência da estrutura.

A mensagem leva, em tags de dado, os produtos (com a ficha da 012), a descrição fixa do avatar
(kit da 025) e as cenas que podem ser reaproveitadas (as do perfil do roteiro e as sem perfil
base, com aquele avatar e aqueles produtos). O brief vai na `<instrucao>` (é o pedido do
operador). As frases chegam numeradas a partir de 1 na resposta e viram índices 0-based aqui.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from sociman_api.roteiros.tempos import TemposInvalidos, validar_posicoes

PROMPT_VERSION = "roteiro/1"
FRASE_MAX = 300
NOME_MAX = 120
ACAO_MAX = 1000
CAMERA_MAX = 500
INSTRUCAO_MAX = 2000

Plano = Literal["close", "busto", "medio", "americano", "aberto", "detalhe_produto"]
Movimento = Literal["parada", "aproximacao", "afastamento", "panoramica", "camera_na_mao"]
Motor = Literal["minimax", "wan", "wan_qualidade", "ltx"]


class CenaNova(BaseModel):
    nome: str = Field(description="nome curto da cena em pt-BR, até 120 caracteres")
    acao: str = Field(description="English: ONE simple action of the shot (the final state "
                                  "matters), e.g. 'She slowly turns to the side, showing the "
                                  "dress'. No speech.")
    plano: Plano | None = Field(description="shot size")
    movimento: Movimento | None = Field(description="camera movement")
    camera: str | None = Field(description="English, optional camera detail")
    motor: Motor = Field(description="minimax (default); wan for a face close-up without "
                                     "speech; wan_qualidade for fabric or a turn where physics "
                                     "matters")
    keyframe_instrucao: str = Field(description="English instruction for the first frame image "
                                                "(the FINAL state of the scene); never ask for a "
                                                "lighting change; never say 'phone video'")
    produto: int | None = Field(description="1-based number of the product in <produtos> "
                                            "shown in this scene, or null")


class PosicaoPlano(BaseModel):
    cena_id: str | None = Field(description="id of a scene from <cenas> to reuse, or null to "
                                            "create a new one in 'nova'")
    nova: CenaNova | None = Field(description="the new scene, only when cena_id is null")
    frases: list[int] = Field(description="1-based numbers of the consecutive sentences "
                                          "narrated over this scene")


class PlanoSaida(BaseModel):
    frases: list[str] = Field(description="as frases de venda em pt-BR, na ordem, uma linha "
                                          "cada, curtas e faladas (voice over)")
    posicoes: list[PosicaoPlano] = Field(description="the scenes of the video in order; every "
                                                     "sentence in exactly one scene, in order")
    explicacao: str = Field(description="até 3 frases curtas em pt-BR")
    avisos: list[str] = Field(description="até 5 frases curtas em pt-BR")


REGRAS = """\
Escreva o roteiro de um vídeo vertical curto de TikTok Shop em formato voice over: a pessoa \
aparece sorrindo e mostrando o produto, sem falar; a narração é contínua.
- frases: de 3 a 8 frases de venda em pt-BR, curtas, faladas, uma linha cada (até 300 \
caracteres), sem hashtags nem emojis; só o que se vê nas fichas dos produtos.
- posicoes: as cenas do vídeo, na ordem. Cada frase em exatamente uma cena, frases seguidas na \
mesma cena, as cenas na ordem das frases. No máximo <limite_cenas> cenas.
- PREFIRA reaproveitar uma cena de <cenas> (cena_id) quando ela servir; só crie uma cena nova \
(nova) quando nenhuma servir.
- Cena nova: uma ação simples em inglês (o estado final importa); sem fala; o close de produto \
de lado, nunca centrado no decote; o motor wan para plano de rosto; a instrução do keyframe \
descreve o estado final, sem mudar a luz e sem "phone video".
- Sem avatar (<avatar> vazio), as cenas mostram só o produto."""


@dataclass(frozen=True)
class CenaParaReuso:
    id: str
    nome: str
    acao: str
    plano: str | None
    produto: int | None  # 1-based em <produtos>
    tem_keyframe: bool


@dataclass(frozen=True)
class ProdutoParaPlano:
    nome: str
    descricao_prompt: str | None
    descricao_venda: str | None
    material_pt: str | None
    cor_pt: str | None


def _limpo(texto: str | None) -> str:
    return " ".join((texto or "").replace("<", "‹").replace(">", "›").split())


def montar_mensagem(brief: str, produtos: Sequence[ProdutoParaPlano],
                    avatar_descricao: str | None, cenas: Sequence[CenaParaReuso],
                    limite_cenas: int) -> str:
    """O texto do usuário (tudo em tags de dado; só a `<instrucao>` é pedido)."""
    linhas = [f"<instrucao>{_limpo(brief) or 'Vídeo de venda dos produtos.'}</instrucao>",
              f"<limite_cenas>{limite_cenas}</limite_cenas>", "<produtos>"]
    for n, p in enumerate(produtos, start=1):
        linhas.append(f'<produto n="{n}">{_limpo(p.nome)} | prompt: {_limpo(p.descricao_prompt)}'
                      f" | venda: {_limpo(p.descricao_venda)} | material: "
                      f"{_limpo(p.material_pt)} | cor: {_limpo(p.cor_pt)}</produto>")
    linhas += ["</produtos>", f"<avatar>{_limpo(avatar_descricao)}</avatar>", "<cenas>"]
    for c in cenas:
        produto = f' produto="{c.produto}"' if c.produto else ""
        linhas.append(f'<cena id="{c.id}"{produto} plano="{c.plano or ""}" keyframe='
                      f'"{"sim" if c.tem_keyframe else "nao"}">{_limpo(c.nome)} | '
                      f"{_limpo(c.acao)}</cena>")
    linhas.append("</cenas>")
    return "\n".join(linhas)


def problemas(p: PlanoSaida) -> list[str]:
    """O que pede uma nova tentativa (estrutura e limites; os ids conferem no aplicador)."""
    erros: list[str] = []
    frases = [f.strip() for f in p.frases]
    if not frases or any(not f for f in frases):
        erros.append("as frases vieram vazias")
    if len(frases) > 60:
        erros.append("mais de 60 frases")
    if any(len(f) > FRASE_MAX or "\n" in f for f in frases):
        erros.append(f"cada frase em uma linha, até {FRASE_MAX} caracteres")
    if not p.posicoes:
        erros.append("o plano não tem cenas")
    for n, pos in enumerate(p.posicoes, start=1):
        if (pos.cena_id is None) == (pos.nova is None):
            erros.append(f"cena {n}: use cena_id (reaproveitar) ou nova (criar), um dos dois")
        if pos.nova is not None:
            if not pos.nova.acao.strip() or len(pos.nova.acao) > ACAO_MAX:
                erros.append(f"cena {n}: a ação vazia ou com mais de {ACAO_MAX} caracteres")
            if not pos.nova.nome.strip() or len(pos.nova.nome) > NOME_MAX:
                erros.append(f"cena {n}: o nome vazio ou com mais de {NOME_MAX} caracteres")
            if len(pos.nova.keyframe_instrucao) > INSTRUCAO_MAX:
                erros.append(f"cena {n}: a instrução do keyframe passou de {INSTRUCAO_MAX}")
    try:
        validar_posicoes([[f - 1 for f in pos.frases] for pos in p.posicoes],
                         list(range(len(frases))))
    except TemposInvalidos as exc:
        erros.append(f"frases × cenas: {exc}")
    return erros


def proposta(p: PlanoSaida) -> dict:
    """O que vai para `ia_chamadas.proposta` (frases 0-based)."""
    return {"plano": {
        "frases": [" ".join(f.split()) for f in p.frases],
        "posicoes": [{"cenaId": pos.cena_id,
                      "nova": pos.nova.model_dump() if pos.nova is not None else None,
                      "frases": [f - 1 for f in pos.frases]} for pos in p.posicoes]}}
