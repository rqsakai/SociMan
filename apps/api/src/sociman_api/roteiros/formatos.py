"""As saídas do Claude no chat do vídeo guiado (spec 031, research R5 e R6, contracts/http-api.md),
puras: o schema, a conferência da estrutura e o que vai para `ia_chamadas.proposta`.

- `perguntas_roteiro` (passo `roteiro.perguntas`): de 1 a 5 perguntas fechadas, numa chamada só,
  cada uma com 2 a 6 opções (rótulo ≤ 60), escolha única ou múltipla e exemplos de pedidos
  prontos;
- `ajuste_roteiro` (passo `roteiro.ajuste`): um esclarecimento (`pergunta`, nada é gerado) ou
  a mudança do alvo recusado (`mudanca`). Quem confere que só os campos do alvo mudam é o
  aplicador do ajuste.

Os ids das perguntas e das opções viram slugs curtos (`[a-z0-9_]`, ≤ 40) e únicos: a resposta do
operador se refere a eles.
"""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

PERGUNTAS_MAX = 5
OPCOES_MIN, OPCOES_MAX = 2, 6
ROTULO_MAX = 60
TEXTO_MAX = 200
EXEMPLOS_MAX = 6
EXEMPLO_MAX = 80
ID_MAX = 40
RESUMO_MAX = 300


class OpcaoIA(BaseModel):
    id: str = Field(description="id curto da opção, minúsculas e _ (ex.: 'caimento')")
    rotulo: str = Field(description="o texto do botão em pt-BR, até 60 caracteres")


class PerguntaIA(BaseModel):
    id: str = Field(description="id curto da pergunta, minúsculas e _ (ex.: 'foco')")
    texto: str = Field(description="a pergunta em pt-BR, até 200 caracteres")
    multipla: bool = Field(description="true = o operador pode marcar mais de uma opção")
    opcoes: list[OpcaoIA] = Field(description="de 2 a 6 opções clicáveis")
    exemplos: list[str] = Field(description="até 6 pedidos prontos para clicar, curtos")


class PerguntasSaida(BaseModel):
    perguntas: list[PerguntaIA] = Field(description="de 1 a 5 perguntas fechadas, na ordem")
    explicacao: str
    avisos: list[str]


class AlvoAjuste(BaseModel):
    tipo: Literal["narracao", "quadros", "trecho", "posicao", "final"]
    ordem: int | None = Field(description="a posição (0-based), quando o alvo é de uma posição")
    quadro: int | None = Field(description="o quadro (0-based) a partir do qual refazer")
    trecho: int | None = Field(description="o trecho (0-based)")


class QuadroAjuste(BaseModel):
    ordem: int = Field(description="o quadro (0-based)")
    instrucao: str = Field(description="English: the FINAL state of the keyframe")


class FraseAjuste(BaseModel):
    indice: int = Field(description="o número da frase (0-based)")
    texto: str = Field(description="a frase nova em pt-BR")


Motor = Literal["minimax", "wan", "wan_qualidade", "ltx"]


class MudancaIA(BaseModel):
    alvo: AlvoAjuste
    quadros: list[QuadroAjuste] = Field(description="as instruções novas dos quadros do alvo")
    acao: str | None = Field(description="English: a nova ação da cena (alvo trecho/posição)")
    motor: Motor | None
    velocidade: float | None = Field(description="a velocidade da narração, de 0.90 a 1.20")
    frases: list[FraseAjuste] = Field(description="as frases que mudam (alvo narração)")
    trechos: int | None = Field(description="1 a 3, só quando a cena fica mais curta ou longa")


class AjusteSaida(BaseModel):
    tipo: Literal["pergunta", "mudanca"] = Field(description="'pergunta' quando o pedido é "
                                                           "ambíguo; senão 'mudanca'")
    pergunta: PerguntaIA | None
    mudanca: MudancaIA | None
    resumo: str = Field(description="uma frase em pt-BR do que muda (sem prompt)")
    explicacao: str
    avisos: list[str]


def slug(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_marcas = "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", "_", sem_marcas).strip("_")[:ID_MAX]


def _problemas_pergunta(n: int, p: PerguntaIA) -> list[str]:
    erros: list[str] = []
    if not p.texto.strip() or len(p.texto) > TEXTO_MAX:
        erros.append(f"pergunta {n}: o texto vazio ou com mais de {TEXTO_MAX} caracteres")
    if not OPCOES_MIN <= len(p.opcoes) <= OPCOES_MAX:
        erros.append(f"pergunta {n}: de {OPCOES_MIN} a {OPCOES_MAX} opções, vieram "
                     f"{len(p.opcoes)}")
    if any(not o.rotulo.strip() or len(o.rotulo) > ROTULO_MAX for o in p.opcoes):
        erros.append(f"pergunta {n}: cada opção com um rótulo de até {ROTULO_MAX} caracteres")
    ids = [slug(o.id) or slug(o.rotulo) for o in p.opcoes]
    if len(set(ids)) != len(ids) or not all(ids):
        erros.append(f"pergunta {n}: as opções precisam de ids diferentes")
    return erros


def problemas_perguntas(p: PerguntasSaida) -> list[str]:
    erros: list[str] = []
    if not 1 <= len(p.perguntas) <= PERGUNTAS_MAX:
        erros.append(f"de 1 a {PERGUNTAS_MAX} perguntas, vieram {len(p.perguntas)}")
    ids = [slug(q.id) or slug(q.texto) for q in p.perguntas]
    if len(set(ids)) != len(ids) or not all(ids):
        erros.append("as perguntas precisam de ids diferentes")
    for n, q in enumerate(p.perguntas, start=1):
        erros.extend(_problemas_pergunta(n, q))
    return erros


def pergunta_proposta(q: PerguntaIA) -> dict:
    """A pergunta como vai para o banco (`roteiro_conversa.conteudo`): ids em slug, textos
    limpos, exemplos cortados."""
    exemplos = [" ".join(e.split())[:EXEMPLO_MAX] for e in q.exemplos if e.strip()]
    return {"id": slug(q.id) or slug(q.texto), "texto": " ".join(q.texto.split()),
            "multipla": bool(q.multipla),
            "opcoes": [{"id": slug(o.id) or slug(o.rotulo), "rotulo": " ".join(o.rotulo.split())}
                       for o in q.opcoes],
            "exemplos": exemplos[:EXEMPLOS_MAX]}


def proposta_perguntas(p: PerguntasSaida) -> dict:
    return {"perguntas": [pergunta_proposta(q) for q in p.perguntas[:PERGUNTAS_MAX]]}


def problemas_ajuste(p: AjusteSaida) -> list[str]:
    erros: list[str] = []
    if p.tipo == "pergunta":
        if p.pergunta is None:
            erros.append("o tipo 'pergunta' precisa da pergunta")
        else:
            erros.extend(_problemas_pergunta(1, p.pergunta))
    elif p.mudanca is None:
        erros.append("o tipo 'mudanca' precisa da mudança")
    else:
        m = p.mudanca
        if m.velocidade is not None and not 0.90 <= m.velocidade <= 1.20:
            erros.append("a velocidade vai de 0.90 a 1.20")
        if m.trechos is not None and not 1 <= m.trechos <= 3:
            erros.append("trechos vai de 1 a 3")
        if any(not q.instrucao.strip() or len(q.instrucao) > 2000 for q in m.quadros):
            erros.append("cada quadro com uma instrução de até 2000 caracteres")
        if any(not f.texto.strip() or len(f.texto) > 300 or "\n" in f.texto for f in m.frases):
            erros.append("cada frase em uma linha, até 300 caracteres")
    if len(p.resumo) > RESUMO_MAX:
        erros.append(f"o resumo passou de {RESUMO_MAX} caracteres")
    return erros


def proposta_ajuste(p: AjusteSaida) -> dict:
    resumo = " ".join(p.resumo.split())[:RESUMO_MAX]
    if p.tipo == "pergunta" and p.pergunta is not None:
        return {"ajuste": {"tipo": "pergunta", "pergunta": pergunta_proposta(p.pergunta),
                           "resumo": resumo}}
    return {"ajuste": {"tipo": "mudanca", "mudanca": p.mudanca.model_dump() if p.mudanca
                       else None, "resumo": resumo}}


def textos_perguntas(p: PerguntasSaida) -> list[str]:
    """Todo texto em que uma palavra proibida do guia conta (017)."""
    return [t for q in p.perguntas for t in (q.texto, *(o.rotulo for o in q.opcoes),
                                             *q.exemplos)]


def textos_ajuste(p: AjusteSaida) -> list[str]:
    out = [p.resumo]
    if p.pergunta is not None:
        out += [p.pergunta.texto, *(o.rotulo for o in p.pergunta.opcoes)]
    if p.mudanca is not None:
        out += [f.texto for f in p.mudanca.frases]
    return out
