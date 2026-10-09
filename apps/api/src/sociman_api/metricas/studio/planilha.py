"""XLSX → linhas, com a biblioteca padrão e em memória (spec 022, research R2).

Lê só o subconjunto do `Viewers.xlsx` do Studio (1 aba, células de texto ou número) e recusa o
resto, antes de abrir qualquer parte que não seja necessária:
- **contêiner:** os limites da 020 (`arquivos.ZIP_ENTRADAS`, `ZIP_EXPANDIDO`, `ZIP_RAZAO`, sem
  cifrado, *stored*/*deflate*), com subpastas relativas aceitas (`xl/worksheets/…`), e recusa de
  caminho absoluto, `\\`, `..`, unidade e link (`studio_zip_inseguro`); um `.zip` ou `.xlsx`
  dentro também (não há 2º nível);
- **conteúdo** (`studio_planilha`): macro (`vbaProject.bin`, content-type `macroEnabled`), link
  externo (`xl/externalLinks/`, `xl/connections.xml`), `<!DOCTYPE`/`<!ENTITY` em qualquer parte
  aberta (verificado **antes** do parser: sem DTD não há XXE nem *billion laughs*), planilha
  protegida, fórmula (`<f>`), várias abas sem a `Viewers`;
- **partes abertas**, cada uma com teto: `[Content_Types].xml`, `xl/workbook.xml`,
  `xl/_rels/workbook.xml.rels`, a aba escolhida e `xl/sharedStrings.xml` (se houver). Estilos,
  tema, metadados e as outras abas nunca são abertos.

Células: `t="str"` (o real), `t="s"`, `t="inlineStr"`, `t="n"`/sem `t` e `t="b"`, com a posição
`r` ("B4"). Na coluna de data, um inteiro de 1 a 2.958.465 é o número de série do Excel (base
1899-12-30). Nada vai para o disco (guarda da spec 022).
"""

import io
import re
import stat
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta

from sociman_api.errors import ApiError
from sociman_api.ia.guia import normalizar

ENTRADAS = 20
EXPANDIDO = 20 * 1024 * 1024
RAZAO = 100
PARTE_TETO = 5 * 1024 * 1024
METODOS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
ABAS = ("viewers", "espectadores")  # pt-BR provisório
SERIE_MAX = 2_958_465  # 31/12/9999
SERIE_BASE = date(1899, 12, 30)
COLUNAS_DATA = ("date", "data")

_NS = re.compile(r"^\{[^}]*\}")
_REF = re.compile(r"^([A-Z]{1,3})(\d+)$")
_PROIBIDO = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_INTEIRO = re.compile(r"^\d+(?:\.0+)?$")
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


@dataclass(frozen=True)
class Planilha:
    cabecalho: list[str]
    linhas: list[list[str]]  # da 2ª linha da aba em diante, como texto
    celulas: list[list[str]]  # a posição de cada valor ("B4"), alinhada com `linhas`
    inicio: int  # o número da 1ª linha de dados


def _planilha(arquivo: str, motivo: str, celula: str | None = None) -> ApiError:
    details: dict = {"arquivo": arquivo, "motivo": motivo}
    texto = f"{arquivo}: a planilha foi recusada ({motivo}"
    if celula:
        details["celula"] = celula
        texto += f", célula {celula}"
    return ApiError(400, "studio_planilha",
                    texto + "). Envie o Viewers.xlsx como o Studio baixou, sem abrir e salvar.",
                    details=details)


recusa = _planilha  # para `arquivos` (o `.xls` antigo e o `.xlsx` que não é ZIP)


def _inseguro(arquivo: str, motivo: str) -> ApiError:
    return ApiError(400, "studio_zip_inseguro",
                    f"{arquivo}: o arquivo foi recusado sem ser lido ({motivo}). Envie o arquivo "
                    "como o Studio baixou.", details={"arquivo": arquivo, "motivo": motivo})


def _local(tag: str) -> str:
    return _NS.sub("", tag)


def _conferir(arquivo: str, zi: zipfile.ZipInfo) -> None:
    nome = zi.filename
    partes = nome.split("/")
    if nome.startswith("/") or "\\" in nome or (len(nome) > 1 and nome[1] == ":"):
        raise _inseguro(arquivo, "caminho absoluto ou com barra invertida")
    if ".." in partes:
        raise _inseguro(arquivo, "caminho com '..'")
    if stat.S_ISLNK(zi.external_attr >> 16):
        raise _inseguro(arquivo, "link simbólico")
    if zi.flag_bits & 0x1:
        raise _inseguro(arquivo, "entrada cifrada")
    if zi.compress_type not in METODOS:
        raise _inseguro(arquivo, "método de compressão não aceito")
    if nome.lower().endswith((".zip", ".xlsx", ".xlsm", ".xls")):
        raise _inseguro(arquivo, "arquivo compactado dentro da planilha")
    if zi.file_size and zi.file_size / max(zi.compress_size, 1) > RAZAO:
        raise _inseguro(arquivo, "expande demais")


def _parte(arquivo: str, zf: zipfile.ZipFile, nome: str) -> ET.Element:
    with zf.open(nome) as f:
        dados = f.read(PARTE_TETO + 1)
    if len(dados) > PARTE_TETO:
        raise _inseguro(arquivo, "expande demais")
    if b"\x00" in dados:  # UTF-16/32 esconderia o DOCTYPE da busca abaixo
        raise _planilha(arquivo, "XML fora de UTF-8")
    if _PROIBIDO.search(dados):
        raise _planilha(arquivo, "DOCTYPE ou ENTITY no XML")
    try:
        return ET.fromstring(dados)
    except ET.ParseError:
        raise _planilha(arquivo, "XML inválido") from None


def _coluna(letras: str) -> int:
    n = 0
    for c in letras:
        n = n * 26 + (ord(c) - 64)
    return n - 1


def _letras(i: int) -> str:
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def _texto_de(el: ET.Element) -> str:
    """O texto de um `<is>`/`<si>` (com ou sem `<r>` de formatação)."""
    return "".join(t.text or "" for t in el.iter() if _local(t.tag) == "t")


def _aba(arquivo: str, zf: zipfile.ZipFile, nomes: set[str]) -> str:
    wb = _parte(arquivo, zf, "xl/workbook.xml")
    if any(_local(e.tag) == "workbookProtection" for e in wb.iter()):
        raise _planilha(arquivo, "planilha protegida")
    abas = [e for e in wb.iter() if _local(e.tag) == "sheet"]
    if not abas:
        raise _planilha(arquivo, "a planilha não tem aba")
    escolhida = next((a for a in abas if normalizar(a.get("name", "")) in ABAS), None)
    if escolhida is None:
        if len(abas) != 1:
            raise _planilha(arquivo, "a planilha não tem a aba Viewers")
        escolhida = abas[0]
    rid = escolhida.get(f"{{{_REL_NS}}}id")
    alvo = None
    if rid and "xl/_rels/workbook.xml.rels" in nomes:
        rels = _parte(arquivo, zf, "xl/_rels/workbook.xml.rels")
        rel = next((r for r in rels if r.get("Id") == rid), None)
        if rel is not None:
            if rel.get("TargetMode") == "External":
                raise _planilha(arquivo, "link externo")
            destino = rel.get("Target", "")
            alvo = destino.lstrip("/") if destino.startswith("/") else f"xl/{destino}"
    if alvo is None and len(abas) == 1:
        alvo = "xl/worksheets/sheet1.xml"
    if alvo is None or alvo not in nomes or ".." in alvo.split("/"):
        raise _planilha(arquivo, "a aba não foi encontrada")
    return alvo


def ler(arquivo: str, dados: bytes) -> Planilha:
    """O XLSX (bytes) → cabeçalho e linhas como texto. Recusa por `ApiError`."""
    if dados.startswith(b"\xd0\xcf\x11\xe0"):
        raise _planilha(arquivo, "planilha antiga (.xls) ou cifrada")
    try:
        zf = zipfile.ZipFile(io.BytesIO(dados))
    except (zipfile.BadZipFile, ValueError):
        raise _planilha(arquivo, "não é uma planilha XLSX") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > ENTRADAS:
            raise _inseguro(arquivo, f"mais de {ENTRADAS} entradas")
        if sum(i.file_size for i in infos) > EXPANDIDO:
            raise _inseguro(arquivo, "expande demais")
        for zi in infos:
            _conferir(arquivo, zi)
        nomes = {i.filename for i in infos}
        if "[Content_Types].xml" not in nomes or "xl/workbook.xml" not in nomes:
            raise _planilha(arquivo, "não é uma planilha XLSX")
        if any(n.lower().endswith("vbaproject.bin") for n in nomes):
            raise _planilha(arquivo, "macro")
        if any(n.startswith("xl/externalLinks/") or n == "xl/connections.xml" for n in nomes):
            raise _planilha(arquivo, "link externo")
        tipos = _parte(arquivo, zf, "[Content_Types].xml")
        if any("macroenabled" in (e.get("ContentType") or "").lower() for e in tipos.iter()):
            raise _planilha(arquivo, "macro")
        alvo = _aba(arquivo, zf, nomes)
        compartilhados: list[str] = []
        if "xl/sharedStrings.xml" in nomes:
            sst = _parte(arquivo, zf, "xl/sharedStrings.xml")
            compartilhados = [_texto_de(si) for si in sst if _local(si.tag) == "si"]
        aba = _parte(arquivo, zf, alvo)
    if any(_local(e.tag) == "sheetProtection" for e in aba.iter()):
        raise _planilha(arquivo, "planilha protegida")

    grade: dict[int, dict[int, tuple[str, str, bool]]] = {}  # linha → coluna → (texto, ref, num)
    for c in aba.iter():
        if _local(c.tag) != "c":
            continue
        ref = c.get("r", "")
        m = _REF.match(ref)
        if m is None:
            raise _planilha(arquivo, "célula sem posição")
        filhos = {_local(f.tag): f for f in c}
        if "f" in filhos:
            raise _planilha(arquivo, "fórmula", ref)
        tipo = c.get("t", "n")
        v = filhos.get("v")
        bruto = (v.text or "") if v is not None else ""
        if tipo == "s":
            try:
                texto = compartilhados[int(bruto)]
            except (ValueError, IndexError):
                raise _planilha(arquivo, "texto compartilhado inválido", ref) from None
        elif tipo == "inlineStr":
            texto = _texto_de(filhos["is"]) if "is" in filhos else ""
        elif tipo in ("str", "n", "b"):
            texto = bruto
        else:
            raise _planilha(arquivo, f"tipo de célula não aceito ({tipo})", ref)
        linha, coluna = int(m.group(2)), _coluna(m.group(1))
        grade.setdefault(linha, {})[coluna] = (texto, ref, tipo == "n")

    if not grade:
        raise _planilha(arquivo, "a aba está vazia")
    primeira = min(grade)
    largura = max(max(cs) for cs in grade.values()) + 1
    cab = grade[primeira]
    cabecalho = [cab.get(i, ("", "", False))[0].strip() for i in range(largura)]
    datas_col = {i for i, n in enumerate(cabecalho) if normalizar(n) in COLUNAS_DATA}
    linhas, celulas = [], []
    for n in range(primeira + 1, max(grade) + 1):
        cs = grade.get(n, {})
        valores = []
        for i in range(largura):
            texto, _, numerico = cs.get(i, ("", "", False))
            if i in datas_col and numerico and _INTEIRO.match(texto.strip()):
                serie = int(float(texto))
                if 1 <= serie <= SERIE_MAX:
                    texto = (SERIE_BASE + timedelta(days=serie)).isoformat()
            valores.append(texto)
        linhas.append(valores)
        celulas.append([f"{_letras(i)}{n}" for i in range(largura)])
    return Planilha(cabecalho, linhas, celulas, primeira + 1)


def eh_xlsx(dados: bytes) -> bool:
    """A assinatura de ZIP com um `[Content_Types].xml` (sem abrir nenhuma parte)."""
    if not dados.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as zf:
            return "[Content_Types].xml" in zf.namelist()
    except (zipfile.BadZipFile, ValueError):
        return False
