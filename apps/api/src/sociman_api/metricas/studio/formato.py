"""Leitura dos CSVs do Studio (research R1): funções puras, sem banco nem rede.

- **Seção pelo cabeçalho**, não pelo nome: cada cabeçalho passa por `ia.guia.normalizar` (sem
  acento, sem caixa) e é procurado em `SINONIMOS`. `dia` + `views` = visão geral; `dia` +
  `seguidores` = seguidores. Desde a 022 (R1), também as seções de público: `genero` +
  `distribuicao`, `territorio` + `distribuicao`, `dia` + `hora` + `ativos` (atividade) e `dia` +
  `espectadores`. Só o Conteúdo dá `studio_secao_nao_importada`; o resto, `studio_formato`.
- **Público (022):** `undefined` e a célula vazia viram `None` ("sem dado") nas colunas numéricas,
  mesmo nas obrigatórias; um arquivo só com o cabeçalho volta com `Leitura.vazia`. A % e os
  rótulos ficam como texto (`Linha.textos`) e são lidos em `publico`. O XLSX (`planilha`) usa a
  mesma `ler_linhas`, e os problemas citam a célula ("B4").
- **Texto:** `utf-8-sig` (tira o BOM); outra codificação é recusada, sem adivinhar.
- **Números:** inteiros sem espaço; milhar só no padrão `1,234`/`1.234`; nada de decimal, `K`/`M`
  nem negativo (exceto `seguidores_dif`). Vazio em coluna opcional = `None`.
- **Linhas:** linha toda vazia é ignorada; número de campos diferente do cabeçalho é erro. Um dia
  repetido (na linha seguinte) com os mesmos números conta uma vez; com números diferentes, é
  erro. Sem ano, o mesmo dia e mês pode voltar num arquivo de mais de um ano: aí são dias
  diferentes, e a ordem é conferida em `datas`.

Os problemas por linha voltam numa lista (`Problema`), e o chamador recusa o envio inteiro.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

from sociman_api.errors import ApiError
from sociman_api.ia.guia import normalizar

VISAO_GERAL = "visao_geral"
SEGUIDORES = "seguidores"
GENERO = "genero"
TERRITORIOS = "territorios"
ATIVIDADE = "atividade"
ESPECTADORES = "espectadores"
PUBLICO = (GENERO, TERRITORIOS, ATIVIDADE, ESPECTADORES)
FOTOS = (GENERO, TERRITORIOS)


@dataclass(frozen=True)
class Sinonimo:
    texto: str
    provisorio: bool = False  # pt-BR ainda não conferido com um arquivo real (R15)


def _en(*textos: str) -> tuple[Sinonimo, ...]:
    return tuple(Sinonimo(t) for t in textos)


def _pt(*textos: str) -> tuple[Sinonimo, ...]:
    return tuple(Sinonimo(t, provisorio=True) for t in textos)


# campo → aliases. Sinônimo novo é uma linha aqui (e o `provisorio` sai quando conferido).
SINONIMOS: dict[str, tuple[Sinonimo, ...]] = {
    "dia": _en("Date") + _pt("Data"),
    "views": _en("Video Views") + _pt("Visualizações de vídeo", "Visualizações do vídeo",
                                      "Visualizações de vídeos"),
    "visitas_perfil": _en("Profile Views") + _pt("Visualizações do perfil",
                                                 "Visitas ao perfil"),
    "likes": _en("Likes") + _pt("Curtidas"),
    "comments": _en("Comments") + _pt("Comentários"),
    "shares": _en("Shares") + _pt("Compartilhamentos"),
    "seguidores": _en("Followers") + _pt("Seguidores"),
    "seguidores_dif": _en("Difference in followers from previous day") + _pt(
        "Diferença de seguidores em relação ao dia anterior"),
    # spec 022 (R1): público
    "genero": _en("Gender") + _pt("Gênero"),
    "territorio": _en("Top territories") + _pt("Principais territórios", "Territórios"),
    "distribuicao": _en("Distribution") + _pt("Distribuição"),
    "hora": _en("Hour") + _pt("Hora"),
    "ativos": _en("Active followers") + _pt("Seguidores ativos"),
    "espectadores": _en("Total Viewers") + _pt("Total de espectadores", "Espectadores"),
    "espectadores_novos": _en("New Viewers") + _pt("Novos espectadores"),
    "espectadores_recorrentes": _en("Returning Viewers") + _pt("Espectadores recorrentes"),
}

# Nome de exibição de cada campo (o cabeçalho em inglês do arquivo real).
NOMES = {campo: aliases[0].texto for campo, aliases in SINONIMOS.items()}

OBRIGATORIAS = {VISAO_GERAL: ("dia", "views"), SEGUIDORES: ("dia", "seguidores"),
                GENERO: ("genero", "distribuicao"), TERRITORIOS: ("territorio", "distribuicao"),
                ATIVIDADE: ("dia", "hora", "ativos"), ESPECTADORES: ("dia", "espectadores")}
OPCIONAIS = {VISAO_GERAL: ("visitas_perfil", "likes", "comments", "shares"),
             SEGUIDORES: ("seguidores_dif",), GENERO: (), TERRITORIOS: (), ATIVIDADE: (),
             ESPECTADORES: ("espectadores_novos", "espectadores_recorrentes")}
# Colunas de texto (a % e os rótulos), lidas em `publico`; o resto (fora `dia`) é número.
TEXTOS = ("genero", "territorio", "distribuicao", "hora")
NUMEROS = {s: tuple(c for c in OBRIGATORIAS[s] + OPCIONAIS[s] if c != "dia" and c not in TEXTOS)
           for s in OBRIGATORIAS}
PODE_NEGATIVO = ("seguidores_dif",)
SEM_DADO = ("undefined",)  # normalizado; só nas seções de público (R1)

# Cabeçalhos das seções não importadas (normalizados) → nome da seção para a mensagem.
OUTRAS_SECOES = (
    (("video title", "post time", "video link", "titulo do video", "link do video"),
     "Conteúdo"),
)

ORIENTACAO = ("Esta seção não é importada. No TikTok Studio, em Analytics, baixe os dados da "
              "Visão geral, de Seguidores e de Espectadores e envie esses ZIPs.")
MOTIVO_NUMERO = "não é um número inteiro"

_ALIAS = {normalizar(s.texto): (campo, s.provisorio)
          for campo, aliases in SINONIMOS.items() for s in aliases}
_INTEIRO = re.compile(r"^\d+$")
_MILHAR = re.compile(r"^\d{1,3}(?:([.,])\d{3})(?:\1\d{3})*$")
_ABREVIADO = re.compile(r"^-?\d+(?:[.,]\d+)?\s*[kKmMbB]$")


@dataclass(frozen=True)
class Problema:
    arquivo: str
    linha: int | None
    coluna: str | None
    valor: str | None
    motivo: str
    celula: str | None = None  # só na planilha (ex.: "B4")

    def json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"arquivo": self.arquivo, "linha": self.linha,
                               "coluna": self.coluna, "valor": self.valor,
                               "motivo": self.motivo}
        if self.celula is not None:
            out["celula"] = self.celula
        return out


@dataclass(frozen=True)
class Linha:
    numero: int  # linha do arquivo (o cabeçalho é a 1)
    dia_bruto: str  # "" nas fotos (gênero, territórios)
    valores: dict[str, int | None]
    textos: dict[str, str] = field(default_factory=dict)  # as colunas de `TEXTOS`, como vieram
    celulas: dict[str, str] = field(default_factory=dict)  # campo → célula (só na planilha)


@dataclass
class Leitura:
    arquivo: str
    secao: str
    linhas: list[Linha]
    reconhecidas: list[str]  # cabeçalhos como vieram
    ausentes: list[str]  # opcionais que faltam (nome de exibição)
    ignoradas: list[str]  # cabeçalhos desconhecidos
    provisorio: bool  # algum cabeçalho veio de um sinônimo pt-BR provisório
    problemas: list[Problema] = field(default_factory=list)
    vazia: bool = False  # seção de público só com o cabeçalho (R5)
    sem_dado: int = 0  # células numéricas de público "sem dado" (`undefined` ou vazio)


def secao_de(cabecalho: list[str]) -> tuple[str | None, str | None]:
    """(seção importada, nome da seção não importada) pelo cabeçalho."""
    campos = {_ALIAS[n][0] for n in map(normalizar, cabecalho) if n in _ALIAS}
    normalizados = {normalizar(c) for c in cabecalho}
    for marcas, nome in OUTRAS_SECOES:
        if normalizados & set(marcas):
            return None, nome
    for secao, obrigatorias in OBRIGATORIAS.items():
        if set(obrigatorias) <= campos:
            return secao, None
    return None, None


def numero(bruto: str, pode_negativo: bool = False) -> int | str:
    """O inteiro, ou o motivo da recusa (texto)."""
    texto = bruto.strip().replace(" ", "").replace(" ", "")
    sinal = 1
    if texto.startswith("-"):
        if not pode_negativo:
            return "negativo" if _INTEIRO.match(texto[1:]) or _MILHAR.match(texto[1:]) \
                else MOTIVO_NUMERO
        sinal, texto = -1, texto[1:]
    if _INTEIRO.match(texto):
        return sinal * int(texto)
    if _MILHAR.match(texto):
        return sinal * int(re.sub(r"[.,]", "", texto))
    if _ABREVIADO.match(bruto.strip()):
        return "abreviado (use o número exato, sem K ou M)"
    return MOTIVO_NUMERO


def _texto(arquivo: str, dados: bytes) -> str:
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiError(400, "studio_formato",
                       f"{arquivo}: o arquivo não está em UTF-8. Envie o arquivo como o Studio "
                       "baixou, sem abrir e salvar em outro programa.",
                       details={"arquivo": arquivo, "esperadas": [], "encontradas": [],
                                "motivo": "codificacao"}) from None


def _esperadas() -> list[str]:
    return [NOMES[c] for s in OBRIGATORIAS for c in OBRIGATORIAS[s] + OPCIONAIS[s]
            if c != "dia" or s == VISAO_GERAL]


def eh_sem_dado(bruto: str) -> bool:
    return not bruto.strip() or normalizar(bruto) in SEM_DADO


def ler(arquivo: str, dados: bytes) -> Leitura:
    """Lê um CSV do Studio. Recusa por `ApiError` o que impede ler (formato, seção); os problemas
    de linha voltam em `Leitura.problemas`."""
    linhas_csv = list(csv.reader(io.StringIO(_texto(arquivo, dados), newline="")))
    while linhas_csv and not any(c.strip() for c in linhas_csv[0]):
        linhas_csv.pop(0)
    if not linhas_csv:
        raise ApiError(400, "studio_formato", f"{arquivo}: o arquivo está vazio",
                       details={"arquivo": arquivo, "esperadas": _esperadas(),
                                "encontradas": [], "motivo": "vazio"})
    return ler_linhas(arquivo, linhas_csv[0], linhas_csv[1:])


def ler_linhas(arquivo: str, cabecalho: list[str], linhas: list[list[str]],
               celulas: list[list[str]] | None = None, inicio: int = 2) -> Leitura:
    """O cabeçalho e as linhas (CSV ou planilha) → `Leitura`. `celulas`, quando vem, dá a posição
    de cada valor ("B4") para os problemas; `inicio` é o número da 1ª linha de dados."""
    cabecalho = [c.strip() for c in cabecalho]
    secao, outra = secao_de(cabecalho)
    if outra is not None:
        raise ApiError(400, "studio_secao_nao_importada", f"{arquivo}: {ORIENTACAO}",
                       details={"arquivo": arquivo, "secaoReconhecida": outra,
                                "orientacao": ORIENTACAO})
    if secao is None:
        raise ApiError(400, "studio_formato",
                       f"{arquivo}: formato não reconhecido. Esperado o cabeçalho da Visão "
                       "geral (Date, Video Views…), de Seguidores (Date, Followers…) ou de "
                       "público (Gender, Top territories, Active followers, Total Viewers), em "
                       "português ou inglês; se o Studio estiver em outro idioma, mude para um "
                       "desses e baixe de novo.",
                       details={"arquivo": arquivo, "esperadas": _esperadas(),
                                "encontradas": cabecalho, "motivo": "cabecalho"})
    publico = secao in PUBLICO
    posicoes: dict[str, int] = {}
    reconhecidas, ignoradas, provisorio = [], [], False
    validos = OBRIGATORIAS[secao] + OPCIONAIS[secao]
    for i, nome in enumerate(cabecalho):
        achado = _ALIAS.get(normalizar(nome))
        if achado is None or achado[0] not in validos or achado[0] in posicoes:
            ignoradas.append(nome)
            continue
        posicoes[achado[0]] = i
        reconhecidas.append(nome)
        provisorio = provisorio or achado[1]
    ausentes = [NOMES[c] for c in OPCIONAIS[secao] if c not in posicoes]

    leitura = Leitura(arquivo, secao, [], reconhecidas, ausentes, ignoradas, provisorio)
    for k, campos in enumerate(linhas):
        numero_linha = inicio + k
        refs = celulas[k] if celulas is not None else None

        def ref(campo: str, refs=refs) -> str | None:
            return refs[posicoes[campo]] if refs is not None else None

        if not any(c.strip() for c in campos):
            continue
        if len(campos) != len(cabecalho):
            leitura.problemas.append(Problema(
                arquivo, numero_linha, None, None,
                f"a linha tem {len(campos)} campos, e o cabeçalho tem {len(cabecalho)}"))
            continue
        dia = campos[posicoes["dia"]].strip() if "dia" in posicoes else ""
        if "dia" in posicoes and not dia:
            leitura.problemas.append(Problema(arquivo, numero_linha, NOMES["dia"], "",
                                              "data vazia", ref("dia")))
            continue
        ok = True
        textos: dict[str, str] = {}
        for campo in TEXTOS:
            if campo not in posicoes:
                continue
            bruto = campos[posicoes[campo]].strip()
            if campo != "distribuicao" and not bruto:
                leitura.problemas.append(Problema(arquivo, numero_linha,
                                                  cabecalho[posicoes[campo]], "",
                                                  "vazio numa coluna obrigatória", ref(campo)))
                ok = False
            textos[campo] = bruto
        valores: dict[str, int | None] = {}
        for campo in NUMEROS[secao]:
            if campo not in posicoes:
                valores[campo] = None
                continue
            bruto = campos[posicoes[campo]]
            coluna = cabecalho[posicoes[campo]]
            if publico and eh_sem_dado(bruto):
                valores[campo] = None
                leitura.sem_dado += 1
                continue
            if not bruto.strip():
                if campo in OBRIGATORIAS[secao]:
                    leitura.problemas.append(Problema(arquivo, numero_linha, coluna, bruto,
                                                      "vazio numa coluna obrigatória",
                                                      ref(campo)))
                    ok = False
                valores[campo] = None
                continue
            lido = numero(bruto, campo in PODE_NEGATIVO)
            if isinstance(lido, str):
                leitura.problemas.append(Problema(arquivo, numero_linha, coluna, bruto, lido,
                                                  ref(campo)))
                ok = False
            else:
                valores[campo] = lido
        if not ok:
            continue
        linha = Linha(numero_linha, dia, valores, textos,
                      {c: refs[i] for c, i in posicoes.items()} if refs is not None else {})
        anterior = leitura.linhas[-1] if leitura.linhas else None
        if dia and secao != ATIVIDADE and anterior is not None \
                and normalizar(anterior.dia_bruto) == normalizar(dia):
            if anterior.valores != valores:
                leitura.problemas.append(Problema(
                    arquivo, numero_linha, NOMES["dia"], dia,
                    f"dia repetido (linha {anterior.numero}) com números diferentes",
                    ref("dia")))
            continue  # igual: conta uma vez
        leitura.linhas.append(linha)
    if not leitura.linhas and not leitura.problemas:
        if publico:
            leitura.vazia = True  # "ainda sem dados de público" (FR-006)
            return leitura
        raise ApiError(400, "studio_formato", f"{arquivo}: o arquivo não tem nenhum dia",
                       details={"arquivo": arquivo, "esperadas": _esperadas(),
                                "encontradas": cabecalho, "motivo": "vazio"})
    return leitura


def provisorios() -> list[str]:
    """Os sinônimos pt-BR ainda não conferidos (R15; o teste lista quais são)."""
    return [s.texto for aliases in SINONIMOS.values() for s in aliases if s.provisorio]
