"""Leitura das seções de público (spec 022, research R1, R4 e R14): funções puras, sem banco nem
rede.

- **% por arquivo** (`pcts`): o formato é decidido pelo arquivo inteiro. Com `%` em algum valor,
  todos têm de ter (`"52%"`); sem `%`, com o máximo ≤ 1 e a soma ≤ 1 + tolerância, é fração
  (`"0.52"`); senão, é % sem o sinal (`"52"`, `"52.3"`, `"52,3"`). Misturar `%` com valores sem `%`
  é recusado. `undefined` e vazio são "sem dado" (`None`).
- **Gênero:** `Male`/`Female`/`Other` e sinônimos → `masculino`/`feminino`/`outro`; o desconhecido
  é recusado. **Territórios:** o rótulo como veio (1 a 64 caracteres). Rótulo repetido é erro.
- **Somas:** gênero a 100 ± `TOLERANCIA_GENERO`; territórios até 100 + a tolerância (a TikTok
  lista só os 5 maiores). Com algum "sem dado", a soma não é conferida.
- **Hora:** `5`, `05`, `5:00`, `05:00` → 0 a 23 (`FUSO_ATIVIDADE = None`: como veio, R13).
- **Data da foto** (FR-012, resposta A): o dia seguinte ao último do `FollowerHistory.csv` do mesmo
  ZIP, limitado a hoje; sem ele, o dia da importação.

Tudo aqui é provisório até um arquivo real com dados (R14; `provisorios()` lista o quê).
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from sociman_api.ia.guia import normalizar
from sociman_api.metricas.studio.formato import (
    GENERO,
    NOMES,
    Leitura,
    Problema,
    eh_sem_dado,
)

TOLERANCIA_GENERO = 2.0  # p.p.
FUSO_ATIVIDADE: str | None = None  # None = a hora como veio no arquivo (R13)
ROTULO_MAX = 64

ROTULOS_GENERO: dict[str, str] = {
    "male": "masculino", "female": "feminino", "other": "outro", "others": "outro",
    "masculino": "masculino", "feminino": "feminino", "outro": "outro", "outros": "outro",
    "homem": "masculino", "mulher": "feminino",
}
EXIBICAO_GENERO = {"masculino": "Masculino", "feminino": "Feminino", "outro": "Outro"}

_PCT = re.compile(r"^(\d{1,3}(?:[.,]\d+)?)\s*(%?)$")
_HORA = re.compile(r"^(\d{1,2})(?::00)?$")


@dataclass(frozen=True)
class Item:
    rotulo: str
    pct: float | None
    linha: int


@dataclass(frozen=True)
class Atividade:
    linha: int
    dia_bruto: str
    hora: int
    ativos: int | None


def _celula(leitura_linha, campo: str) -> str | None:
    return leitura_linha.celulas.get(campo)


def pcts(brutos: list[str]) -> tuple[list[float | None], str | None]:
    """As % (0 a 100, ou None) e o motivo da recusa do arquivo (None se está ok)."""
    lidos: list[tuple[float, bool] | None] = []
    for bruto in brutos:
        if eh_sem_dado(bruto):
            lidos.append(None)
            continue
        m = _PCT.match(bruto.strip().replace(" ", ""))
        if m is None:
            return [], f"\"{bruto}\" não é uma porcentagem"
        lidos.append((float(m.group(1).replace(",", ".")), m.group(2) == "%"))
    com_sinal = {x[1] for x in lidos if x is not None}
    if len(com_sinal) > 1:
        return [], "formatos de porcentagem misturados (com e sem %)"
    valores = [x[0] for x in lidos if x is not None]
    fracao = com_sinal == {False} and valores and max(valores) <= 1 \
        and sum(valores) <= 1 + TOLERANCIA_GENERO / 100
    out = [None if x is None else round(x[0] * 100 if fracao else x[0], 3) for x in lidos]
    if any(v is not None and v > 100 for v in out):
        return [], "porcentagem acima de 100"
    return out, None


def rotulo_genero(bruto: str) -> str | None:
    return ROTULOS_GENERO.get(normalizar(bruto))


def hora(bruto: str) -> int | None:
    m = _HORA.match(bruto.strip())
    if m is None or int(m.group(1)) > 23:
        return None
    return int(m.group(1))


def ler_distribuicao(leitura: Leitura) -> tuple[list[Item], list[Problema]]:
    """Gênero ou territórios: os rótulos e as %, com os problemas (FR-008)."""
    campo = "genero" if leitura.secao == GENERO else "territorio"
    problemas: list[Problema] = []
    arq = leitura.arquivo
    col_rotulo, col_pct = NOMES[campo], NOMES["distribuicao"]
    for ln in leitura.linhas:  # % negativa: o regex não aceita o sinal; motivo próprio
        bruto = ln.textos.get("distribuicao", "")
        if bruto.strip().startswith("-"):
            problemas.append(Problema(arq, ln.numero, col_pct, bruto, "porcentagem negativa",
                                      _celula(ln, "distribuicao")))
    if problemas:
        return [], problemas
    valores, motivo = pcts([ln.textos.get("distribuicao", "") for ln in leitura.linhas])
    if motivo is not None:
        return [], [Problema(arq, None, col_pct, None, motivo)]
    itens: list[Item] = []
    vistos: dict[str, int] = {}
    for ln, pct in zip(leitura.linhas, valores, strict=True):
        bruto = ln.textos[campo]
        if campo == "genero":
            rotulo = rotulo_genero(bruto)
            if rotulo is None:
                problemas.append(Problema(arq, ln.numero, col_rotulo, bruto,
                                          "gênero desconhecido", _celula(ln, campo)))
                continue
        else:
            rotulo = bruto.strip()
            if len(rotulo) > ROTULO_MAX:
                problemas.append(Problema(arq, ln.numero, col_rotulo, bruto[:ROTULO_MAX],
                                          f"rótulo com mais de {ROTULO_MAX} caracteres",
                                          _celula(ln, campo)))
                continue
        chave = normalizar(rotulo)
        if chave in vistos:
            problemas.append(Problema(arq, ln.numero, col_rotulo, bruto,
                                      f"rótulo repetido (linha {vistos[chave]})",
                                      _celula(ln, campo)))
            continue
        vistos[chave] = ln.numero
        itens.append(Item(rotulo, pct, ln.numero))
    if problemas:
        return [], problemas
    if itens and all(i.pct is not None for i in itens):
        soma = round(sum(i.pct for i in itens), 3)  # type: ignore[misc]
        if leitura.secao == GENERO and abs(soma - 100) > TOLERANCIA_GENERO:
            problemas.append(Problema(arq, None, col_pct, f"{soma:g}",
                                      f"a soma do gênero dá {soma:g}%, e não 100%"))
        elif leitura.secao != GENERO and soma > 100 + TOLERANCIA_GENERO:
            problemas.append(Problema(arq, None, col_pct, f"{soma:g}",
                                      f"a soma dos territórios dá {soma:g}%, mais de 100%"))
    return ([] if problemas else itens), problemas


def ler_atividade(leitura: Leitura) -> tuple[list[Atividade], list[Problema]]:
    """As linhas (dia, hora, ativos); o mesmo (dia, hora) com o mesmo número conta uma vez, e com
    números diferentes é erro. As datas são resolvidas depois (`datas`)."""
    problemas: list[Problema] = []
    out: list[Atividade] = []
    vistos: dict[tuple[str, int], Atividade] = {}
    for ln in leitura.linhas:
        h = hora(ln.textos["hora"])
        if h is None:
            problemas.append(Problema(leitura.arquivo, ln.numero, NOMES["hora"],
                                      ln.textos["hora"], "hora fora de 0 a 23",
                                      _celula(ln, "hora")))
            continue
        chave = (normalizar(ln.dia_bruto), h)
        atual = Atividade(ln.numero, ln.dia_bruto, h, ln.valores["ativos"])
        anterior = vistos.get(chave)
        if anterior is not None:
            if anterior.ativos != atual.ativos:
                problemas.append(Problema(
                    leitura.arquivo, ln.numero, NOMES["hora"], ln.textos["hora"],
                    f"dia e hora repetidos (linha {anterior.linha}) com números diferentes",
                    _celula(ln, "hora")))
            continue
        vistos[chave] = atual
        out.append(atual)
    return out, problemas


def data_foto(historico_dias: list[date] | None, hoje: date) -> tuple[date, str]:
    """(data, origem) das fotos de gênero e territórios (FR-012, resposta A)."""
    if historico_dias:
        return min(max(historico_dias) + timedelta(days=1), hoje), "historico"
    return hoje, "importacao"


def rotulo_exibicao(tipo: str, rotulo: str) -> str:
    return EXIBICAO_GENERO.get(rotulo, rotulo) if tipo == GENERO else rotulo


def provisorios() -> list[str]:
    """O que ainda não foi conferido com um arquivo real de público (R14)."""
    return [
        "rótulos de gênero: " + ", ".join(sorted(ROTULOS_GENERO)),
        "formatos de %: 52%, 52, 52.3, 52,3 e a fração 0.52",
        "hora: 5, 05, 5:00 e 05:00",
        f"fuso da atividade: {FUSO_ATIVIDADE or 'como veio'}",
    ]
