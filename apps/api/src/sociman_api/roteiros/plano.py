"""O plano do roteiro pelo Claude (spec 011, FR-013 e FR-014), puro: o schema da saída, a mensagem
e a conferência da estrutura.

A mensagem leva, em tags de dado, os produtos (com a ficha da 012), a descrição fixa do avatar
(kit da 025) e as cenas que podem ser reaproveitadas (as do perfil do roteiro e as sem perfil
base, com aquele avatar e aqueles produtos). O brief vai na `<instrucao>` (é o pedido do
operador). As frases chegam numeradas a partir de 1 na resposta e viram índices 0-based aqui.

Spec 031 (plano v2, só no vídeo guiado, research R4 e R7): cada posição ocupa de 1 a 3
trechos-base, a cena nova traz uma instrução por quadro (`trechos + 1`, o estado final de cada
ponto), o reuso diz o nível (`total` = a cena como está, `plano` = só o plano dela, numa
derivada) e a fala de cada posição cabe no orçamento de caracteres (`grade.orcamento_chars`).
As respostas do chat vão em `<respostas>`, a grade em `<grade>`. `problemas_v2` confere a
estrutura; `problemas_contexto` confere o que depende do roteiro (a soma, o orçamento e as
candidatas), dentro das duas tentativas do cliente.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from sociman_api.roteiros import grade
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
# Decisão do dono (T059, 2026-10-15): o plano usa SEMPRE o MiniMax (o Wan qualidade levou 1 h 39
# por trecho de 5 s nesta GPU e deslizou a caminhada). Os outros motores só à mão, no avançado.
MOTOR_DO_PLANO = "minimax"


class CenaNova(BaseModel):
    nome: str = Field(description="nome curto da cena em pt-BR, até 120 caracteres")
    acao: str = Field(description="English: ONE simple action of the shot (the final state "
                                  "matters), e.g. 'She slowly turns to the side, showing the "
                                  "dress'. No speech.")
    plano: Plano | None = Field(description="shot size")
    movimento: Movimento | None = Field(description="camera movement")
    camera: str | None = Field(description="English, optional camera detail")
    motor: Motor = Field(description="always minimax")
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


# ---- spec 031: o plano v2 do vídeo guiado ----

PROMPT_VERSION_V2 = "roteiro/2"
MOTIVO_MAX = 300
Nivel = Literal["total", "plano"]


class CenaNovaV2(BaseModel):
    nome: str = Field(description="nome curto da cena em pt-BR, até 120 caracteres")
    acao: str = Field(description="English: ONE simple action across the whole shot, e.g. 'She "
                                  "slowly turns to the side, showing the dress'. No speech.")
    plano: Plano | None = Field(description="shot size")
    movimento: Movimento | None = Field(description="camera movement")
    camera: str | None = Field(description="English, optional camera detail")
    motor: Motor = Field(description="always minimax")
    quadros: list[str] = Field(description="English, exactly trechos + 1 instructions, one per "
                                           "keyframe (start, middles, end), each the FINAL "
                                           "state of that keyframe; never a lighting change")


class PosicaoPlanoV2(BaseModel):
    cena_id: str | None = Field(description="id of a scene from <cenas> to reuse, or null to "
                                            "create a new one in 'nova'")
    nivel: Nivel | None = Field(description="only with cena_id: 'total' (the scene as it is; "
                                            "only when <cena nivel=\"total\">) or 'plano' (the "
                                            "plan of the scene, redone with this avatar)")
    nova: CenaNovaV2 | None = Field(description="the new scene, only when cena_id is null")
    trechos: int = Field(description="1 to 3 base segments for this scene (1 for a simple "
                                     "movement; 2 or 3 for a turn, a walk or hands on the "
                                     "product); a reused 'total' scene keeps its trechos")
    frases: list[int] = Field(description="1-based numbers of the consecutive sentences "
                                          "narrated over this scene")
    motivo: str = Field(description="uma frase curta em pt-BR: por que reaproveitar ou criar")


class PlanoSaidaV2(BaseModel):
    frases: list[str] = Field(description="as frases de venda em pt-BR, na ordem, curtas e "
                                          "faladas; a fala de cada cena cabe no orçamento dela")
    posicoes: list[PosicaoPlanoV2] = Field(description="the scenes in order; the sum of 'trechos' "
                                                       "over ALL positions is EXACTLY the number "
                                                       "of trechos in <grade> (2 trechos = at "
                                                       "most 2 scenes); check the sum before "
                                                       "answering")
    explicacao: str = Field(description="até 3 frases curtas em pt-BR")
    avisos: list[str] = Field(description="até 5 frases curtas em pt-BR")


REGRAS_V2 = """\
Escreva o roteiro de um vídeo vertical curto de TikTok Shop em formato voice over (a pessoa \
aparece mostrando o produto, sem falar; a narração é contínua), a partir das <respostas> do \
operador às perguntas do chat.
- A duração é fechada: <grade> diz quantos trechos o vídeo tem, e a soma dos "trechos" de TODAS \
as posições tem de ser EXATAMENTE esse número (não é o número de cenas: um vídeo de 2 trechos \
tem 1 cena com trechos=2 ou 2 cenas com trechos=1, nunca 3 cenas). Cada cena ocupa de 1 a 3 \
trechos: 1 para um movimento simples, 2 ou 3 para giro, caminhada ou mão no produto. Um \
movimento maior que 3 trechos vira duas cenas seguidas (o fim de uma é o início da outra). \
Antes de responder, some os trechos das posições; se não bater com a <grade>, junte ou corte \
cenas até fechar.
- frases: frases de venda em pt-BR, curtas e faladas, sem hashtags nem emojis; só o que se vê na \
ficha do produto. As frases de cada cena somam no máximo o orçamento da cena: <orcamento> diz \
quantos caracteres cabem por trecho.
- PREFIRA reaproveitar uma cena de <cenas> (cena_id) quando ela servir: nivel "total" só nas \
marcadas nivel="total" (e com os trechos dela), "plano" nas outras. Crie cena nova só quando \
nenhuma servir ou quando o operador pediu cenas novas nas <respostas>. motivo: uma frase.
- Cena nova: quadros = trechos + 1 instruções em inglês, cada uma o ESTADO FINAL daquele \
quadro (o 1º é o início, o último é o fim; o vídeo vai de um quadro ao seguinte); nunca mude a \
luz, o quarto ou as paredes; o close de produto de lado, nunca centrado no decote; sem "phone \
video"; o motor wan para plano de rosto.
- Siga o <guia_perfil> (tom, faça e não faça) e nunca use as palavras proibidas dele."""


@dataclass(frozen=True)
class CandidataV2:
    """Uma cena que pode ser reaproveitada no guiado (R7), com o nível que ela permite."""

    id: str
    nome: str
    acao: str
    plano: str | None
    nivel: Nivel
    trechos: int | None  # None = cena da 010/011 (sem a sequência de quadros)
    motivo_plano: str | None = None  # por que não é total (outro avatar, cenário ou variante)


@dataclass(frozen=True)
class ContextoV2:
    base: int
    alvo: int
    candidatas: tuple[CandidataV2, ...] = ()

    def candidata(self, cena_id: str | None) -> CandidataV2 | None:
        return next((c for c in self.candidatas if c.id == cena_id), None)


def _regra_da_grade(total: int) -> str:
    """A conta explícita da grade, na própria tag (T059: com "2 trechos" o modelo propunha 3
    cenas de 1 trecho). Lista as combinações até 3 trechos; acima disso, só o intervalo."""
    minimo = -(-total // grade.MAX_TRECHOS)
    if total <= 1:
        return 'uma só cena com trechos=1; a soma dos "trechos" das posições tem de ser 1'
    if total == 2:
        exemplos = "1 cena com trechos=2, ou 2 cenas com trechos=1"
    elif total == 3:
        exemplos = "1 cena com trechos=3, 2 cenas (2+1 ou 1+2), ou 3 cenas com trechos=1"
    else:
        exemplos = f"de {minimo} a {total} cenas"
    return (f'a soma dos "trechos" de todas as posições tem de ser exatamente {total} '
            f"({exemplos}); nunca mais de {total} cenas")


def montar_mensagem_v2(respostas: Sequence[tuple[str, str]], produto: ProdutoParaPlano,
                       avatar_descricao: str | None, cenario: str | None,
                       cenas: Sequence[CandidataV2], ctx: ContextoV2,
                       guia: str | None = None) -> str:
    """O texto do usuário do plano v2 (tudo em tags de dado). `respostas` = (pergunta, resposta)
    já sem as palavras proibidas; `guia` = o conteúdo do guia do perfil base (017)."""
    linhas = ["<instrucao>Monte o vídeo a partir das respostas do operador.</instrucao>",
              (f'<grade base="{ctx.base}" alvo="{ctx.alvo}">{ctx.alvo // ctx.base} trechos de '
               f"{ctx.base} s: {_regra_da_grade(ctx.alvo // ctx.base)}</grade>"),
              (f"<orcamento>{grade.orcamento_chars(ctx.base)} caracteres de fala por trecho de "
               f"{ctx.base} s</orcamento>"), "<respostas>"]
    for pergunta, resposta in respostas:
        linhas.append(f"<resposta pergunta=\"{_limpo(pergunta)}\">{_limpo(resposta)}</resposta>")
    linhas += ["</respostas>",
               (f"<produto>{_limpo(produto.nome)} | prompt: {_limpo(produto.descricao_prompt)} | "
                f"venda: {_limpo(produto.descricao_venda)} | material: "
                f"{_limpo(produto.material_pt)} | cor: {_limpo(produto.cor_pt)}</produto>"),
               f"<avatar>{_limpo(avatar_descricao)}</avatar>",
               f"<cenario>{_limpo(cenario)}</cenario>"]
    if guia:
        linhas.append(f"<guia_perfil>{_limpo(guia)}</guia_perfil>")
    linhas.append("<cenas>")
    for c in cenas:
        trechos = f' trechos="{c.trechos}"' if c.trechos else ""
        linhas.append(f'<cena id="{c.id}" nivel="{c.nivel}"{trechos} plano="{c.plano or ""}">'
                      f"{_limpo(c.nome)} | {_limpo(c.acao)}</cena>")
    linhas.append("</cenas>")
    return "\n".join(linhas)


def problemas_v2(p: PlanoSaidaV2) -> list[str]:
    """A estrutura do plano v2 (o que depende do roteiro fica em `problemas_contexto`)."""
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
        if pos.cena_id is not None and pos.nivel is None:
            erros.append(f"cena {n}: diga o nivel do reuso (total ou plano)")
        if not 1 <= pos.trechos <= grade.MAX_TRECHOS:
            erros.append(f"cena {n}: trechos vai de 1 a {grade.MAX_TRECHOS}")
        if not pos.motivo.strip() or len(pos.motivo) > MOTIVO_MAX:
            erros.append(f"cena {n}: o motivo vazio ou com mais de {MOTIVO_MAX} caracteres")
        if pos.nova is not None:
            nova = pos.nova
            if not nova.acao.strip() or len(nova.acao) > ACAO_MAX:
                erros.append(f"cena {n}: a ação vazia ou com mais de {ACAO_MAX} caracteres")
            if not nova.nome.strip() or len(nova.nome) > NOME_MAX:
                erros.append(f"cena {n}: o nome vazio ou com mais de {NOME_MAX} caracteres")
            if len(nova.quadros) != pos.trechos + 1:
                erros.append(f"cena {n}: {pos.trechos} trecho(s) pedem {pos.trechos + 1} "
                             f"quadros, vieram {len(nova.quadros)}")
            if any(not q.strip() or len(q) > INSTRUCAO_MAX for q in nova.quadros):
                erros.append(f"cena {n}: cada quadro com uma instrução de até {INSTRUCAO_MAX}")
    try:
        validar_posicoes([[f - 1 for f in pos.frases] for pos in p.posicoes],
                         list(range(len(frases))))
    except TemposInvalidos as exc:
        erros.append(f"frases × cenas: {exc}")
    return erros


def problemas_contexto(p: PlanoSaidaV2, ctx: ContextoV2) -> list[str]:
    """O que depende do roteiro: a soma fecha na duração, a fala de cada cena cabe no orçamento,
    o reuso é de uma candidata e o `total` só numa candidata `total` (com os trechos dela)."""
    erros: list[str] = []
    soma = sum(pos.trechos for pos in p.posicoes) * ctx.base
    if soma != ctx.alvo:
        erros.append(f"a soma das cenas dá {soma} s; a duração é {ctx.alvo} s "
                     f"({ctx.alvo // ctx.base} trechos de {ctx.base} s)")
    frases = [f.strip() for f in p.frases]
    for n, pos in enumerate(p.posicoes, start=1):
        fala = sum(len(frases[f - 1]) for f in pos.frases if 1 <= f <= len(frases))
        teto = grade.orcamento_chars(pos.trechos * ctx.base)
        if fala > teto:
            erros.append(f"cena {n}: a fala tem {fala} caracteres e cabem {teto}")
        if pos.cena_id is None:
            continue
        c = ctx.candidata(pos.cena_id)
        if c is None:
            erros.append(f"cena {n}: a cena {pos.cena_id} não está em <cenas>")
        elif pos.nivel == "total" and (c.nivel != "total" or c.trechos != pos.trechos):
            erros.append(f"cena {n}: o reuso total só vale para uma cena nivel=\"total\", com os "
                         "trechos dela; use nivel \"plano\"")
    return erros


def proposta_v2(p: PlanoSaidaV2) -> dict:
    """O que vai para `ia_chamadas.proposta` (frases 0-based; `versao: 2`)."""
    return {"plano": {
        "versao": 2,
        "frases": [" ".join(f.split()) for f in p.frases],
        "posicoes": [{"cenaId": pos.cena_id, "nivel": pos.nivel,
                      "nova": pos.nova.model_dump() if pos.nova is not None else None,
                      "trechos": pos.trechos, "frases": [f - 1 for f in pos.frases],
                      "motivo": " ".join(pos.motivo.split())[:MOTIVO_MAX]}
                     for pos in p.posicoes]}}
