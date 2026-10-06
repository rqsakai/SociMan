"""Leitor de markdown determinístico, só com a biblioteca padrão (research R3).

O texto é dado, nunca instrução: nada daqui vai para um modelo. Os leitores de cada arquivo
(`leitores.py`) procuram as seções e os rótulos do molde comparando com `normalizar` (sem
acento, sem caixa, sem `**`, crases e `_` de ênfase).
"""

import re
from dataclasses import dataclass

from sociman_api.ia.guia import normalizar as _sem_acento

_ENFASE = re.compile(r"\*\*|__|`|(?<!\w)_(?=\S)|(?<=\S)_(?!\w)")
_TITULO = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ITEM = re.compile(r"^[-*]\s+(.*)$")
SEPARADOR = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_URL = re.compile(r"(?:https?://|(?<![\w/.@-])(?:www\.|m\.)?youtube\.com/|(?<![\w/.@-])youtu\.be/)"
                  r"[^\s|)\]>\"'`,;·]+", re.IGNORECASE)
MOLDE_VAZIO = re.compile(r"^(?:<[^>]*>|a definir|-|—|n/?a|\.\.\.|…)?$")


def normalizar(texto: str) -> str:
    """Sem ênfase markdown, sem acento, `casefold` e espaços colapsados."""
    return _sem_acento(_ENFASE.sub("", texto)).strip()


def limpar(texto: str) -> str:
    """O valor para gravar: sem `**`/crases de ênfase e espaços colapsados (acentos ficam)."""
    return re.sub(r"[ \t]+", " ", texto.replace("**", "").replace("`", "")).strip()


def vazio(valor: str) -> bool:
    """Valor do molde (`<Nome>`, vazio, "A DEFINIR") conta como vazio."""
    return bool(MOLDE_VAZIO.match(normalizar(valor)))


@dataclass(frozen=True)
class Secao:
    nivel: int
    titulo: str  # normalizado
    titulo_original: str
    corpo: str  # sem o título; inclui as subseções de nível maior
    linha: int  # 1-based, a do título


def frontmatter(texto: str) -> tuple[dict[str, str], str, int]:
    """(chaves, resto do texto, linhas consumidas). Só `chave: valor` simples."""
    linhas = texto.splitlines()
    if not linhas or linhas[0].strip() != "---":
        return {}, texto, 0
    for i in range(1, len(linhas)):
        if linhas[i].strip() == "---":
            dados = {}
            for ln in linhas[1:i]:
                if ":" in ln:
                    k, _, v = ln.partition(":")
                    dados[normalizar(k)] = v.strip()
            return dados, "\n".join(linhas[i + 1:]), i + 1
    return {}, texto, 0


def secoes(texto: str, deslocamento: int = 0) -> list[Secao]:
    """Títulos `#` a `######` (fora de blocos de código), cada um com o corpo até o próximo
    título de nível igual ou menor."""
    linhas = texto.splitlines()
    titulos: list[tuple[int, int, str]] = []
    em_codigo = False
    for i, ln in enumerate(linhas):
        if ln.lstrip().startswith("```"):
            em_codigo = not em_codigo
            continue
        m = None if em_codigo else _TITULO.match(ln)
        if m:
            titulos.append((i, len(m.group(1)), m.group(2)))
    out = []
    for k, (i, nivel, titulo) in enumerate(titulos):
        fim = next((j for j, n, _ in titulos[k + 1:] if n <= nivel), len(linhas))
        out.append(Secao(nivel, normalizar(titulo), titulo.strip(),
                         "\n".join(linhas[i + 1:fim]).strip("\n"), i + 1 + deslocamento))
    return out


def rotulo_valor(item: str) -> tuple[str, str] | None:
    """`Rótulo (ex.: a, b): valor` → (rótulo, valor): o `:` dentro de parênteses não conta."""
    nivel = 0
    for i, c in enumerate(item):
        if c == "(":
            nivel += 1
        elif c == ")":
            nivel = max(0, nivel - 1)
        elif c == ":" and nivel == 0:
            rotulo = item[:i].strip()
            return (rotulo, item[i + 1:].strip()) if 0 < len(rotulo) <= 120 else None
    return None


def rotulo(texto: str) -> str:
    """Rótulo normalizado e sem os parênteses explicativos do molde."""
    return normalizar(re.sub(r"\([^)]*\)", " ", texto))


def campos(corpo: str) -> dict[str, str]:
    """`- Rótulo: valor` → `{rótulo normalizado: valor}`. O valor continua nas linhas seguintes
    indentadas (sem novo item). Rótulo repetido: vale o primeiro."""
    out: dict[str, str] = {}
    atual: str | None = None
    for ln in corpo.splitlines():
        m = None if ln.startswith(("  ", "\t")) else _ITEM.match(ln)
        par = rotulo_valor(m.group(1)) if m else None
        if par is not None:
            chave = rotulo(par[0])
            atual = None if chave in out else chave
            if atual is not None:
                out[atual] = par[1]
        elif atual is not None and ln.startswith(("  ", "\t")) and ln.strip():
            out[atual] = f"{out[atual]} {ln.strip()}".strip()
        elif ln.strip():
            atual = None
    return out


@dataclass(frozen=True)
class Tabela:
    cabecalho: list[str]  # normalizado
    linhas: list[tuple[int, list[str]]]  # (nº da linha no arquivo, células)
    problemas: list[int]  # linhas com nº de células diferente do cabeçalho (ajustadas)


def _celulas(ln: str) -> list[str]:
    s = ln.strip()
    s = s.removeprefix("|")
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    partes = re.split(r"(?<!\\)\|", s)
    return [p.replace("\\|", "|").strip() for p in partes]


def tabelas(corpo: str, deslocamento: int = 0) -> list[Tabela]:
    """Tabelas `|…|` com a linha separadora `|---|`. Texto antes ou depois é ignorado."""
    linhas = corpo.splitlines()
    out: list[Tabela] = []
    i = 0
    while i < len(linhas) - 1:
        ln = linhas[i]
        if ln.strip().startswith("|") and SEPARADOR.match(linhas[i + 1].strip()):
            cab = [normalizar(c) for c in _celulas(ln)]
            dados: list[tuple[int, list[str]]] = []
            problemas: list[int] = []
            j = i + 2
            while j < len(linhas) and linhas[j].strip().startswith("|"):
                cel = _celulas(linhas[j])
                if len(cel) != len(cab):
                    # Agente escreveu células a mais ou a menos: a linha entra ajustada (as
                    # sobras vão para a última coluna; as que faltam ficam vazias) e é marcada.
                    problemas.append(j + 1 + deslocamento)
                    cel = (cel[:len(cab) - 1] + [" | ".join(cel[len(cab) - 1:])]
                           if len(cel) > len(cab) else cel + [""] * (len(cab) - len(cel)))
                dados.append((j + 1 + deslocamento, cel))
                j += 1
            out.append(Tabela(cab, dados, problemas))
            i = j
            continue
        i += 1
    return out


def coluna(cabecalho: list[str], *prefixos: str) -> int | None:
    """O índice da primeira coluna cujo nome normalizado começa com um dos prefixos."""
    for i, nome in enumerate(cabecalho):
        if any(nome.startswith(p) for p in prefixos):
            return i
    return None


def links(texto: str) -> list[str]:
    """URLs (`https?://…`) e links do YouTube sem esquema, na ordem do texto."""
    return [m.group(0).rstrip(".") for m in _URL.finditer(texto)]
