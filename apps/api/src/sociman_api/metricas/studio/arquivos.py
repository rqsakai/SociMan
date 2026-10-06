"""Envio → CSVs, tudo em memória (research R2). Nada é extraído nem gravado em disco.

- A requisição tem no máximo `LIMITE_ENVIO` bytes no total (`read(limite + 1)` → 413
  `arquivo_grande`), com 1 ou 2 arquivos.
- ZIP pela **assinatura** (`PK\\x03\\x04`), não pela extensão, aberto com `ZipFile(BytesIO)`.
  Recusado (`studio_zip_inseguro`) com mais de `ZIP_ENTRADAS` entradas, mais de `ZIP_EXPANDIDO`
  expandidos, razão acima de `ZIP_RAZAO`, caminho absoluto, `\\`, `..`, unidade, pasta, link,
  ZIP dentro de ZIP, entrada cifrada ou método fora de *stored*/*deflate*.
- Só `Overview.csv` e `FollowerHistory.csv` são abertos (com teto na leitura). As outras entradas
  são listadas como ignoradas e **nunca abertas** (o `Content.csv` traz títulos e links).
- XLSX, o "Baixar seus dados" (JSON/TXT) e os ZIPs de outras seções: `studio_secao_nao_importada`.
"""

import hashlib
import io
import stat
import zipfile
from dataclasses import dataclass, field
from typing import BinaryIO, Protocol
from zoneinfo import ZoneInfo

from sociman_api.errors import ApiError
from sociman_api.metricas.studio import datas
from sociman_api.metricas.studio.formato import ORIENTACAO

LIMITE_ENVIO = 5 * 1024 * 1024
ZIP_ENTRADAS = 20
ZIP_EXPANDIDO = 20 * 1024 * 1024
ZIP_RAZAO = 100
CSV_TETO = LIMITE_ENVIO
ENTRADAS = ("Overview.csv", "FollowerHistory.csv")
METODOS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
ASSINATURAS_ZIP = (b"PK\x03\x04", b"PK\x05\x06")
OLE = b"\xd0\xcf\x11\xe0"  # .xls antigo
SECAO_DO_NOME = {"Content": "Conteúdo", "Viewers": "Espectadores"}


class Upload(Protocol):
    """O `UploadFile` do FastAPI (ou um equivalente nos testes): nome e arquivo binário."""

    filename: str | None
    file: BinaryIO


@dataclass(frozen=True)
class Enviado:
    nome: str
    dados: bytes


@dataclass(frozen=True)
class Csv:
    arquivo: str  # o nome enviado (ZIP ou CSV)
    entrada: str  # o nome do CSV
    dados: bytes
    sha: str


@dataclass
class Arquivo:
    nome: str
    tipo: str  # zip | csv
    handle: str | None
    nome_zip: datas.NomeZip | None
    csvs: list[Csv] = field(default_factory=list)
    ignorados: list[str] = field(default_factory=list)


def _grande() -> ApiError:
    return ApiError(413, "arquivo_grande",
                    f"O envio passa de {LIMITE_ENVIO // (1024 * 1024)} MB. Os arquivos do Studio "
                    "têm poucos KB: confira se escolheu os ZIPs certos.",
                    details={"limiteBytes": LIMITE_ENVIO})


def ler_envio(uploads: list[Upload]) -> list[Enviado]:
    """Os bytes de cada arquivo, com o teto do envio inteiro."""
    if not 1 <= len(uploads) <= 2:
        raise ApiError(400, "studio_arquivos",
                       "Envie 1 ou 2 arquivos: o ZIP da Visão geral e/ou o de Seguidores.",
                       details={"recebidos": len(uploads)})
    restante, out = LIMITE_ENVIO, []
    for up in uploads:
        dados = up.file.read(restante + 1)
        if len(dados) > restante:
            raise _grande()
        restante -= len(dados)
        out.append(Enviado(up.filename or "arquivo", dados))
    return out


def _inseguro(arquivo: str, motivo: str) -> ApiError:
    return ApiError(400, "studio_zip_inseguro",
                    f"{arquivo}: o ZIP foi recusado sem ser lido ({motivo}). Envie o ZIP como o "
                    "Studio baixou.", details={"arquivo": arquivo, "motivo": motivo})


def _nao_importada(arquivo: str, secao: str | None) -> ApiError:
    texto = f"{arquivo}: {ORIENTACAO}"
    details: dict = {"arquivo": arquivo, "orientacao": ORIENTACAO}
    if secao:
        details["secaoReconhecida"] = secao
    return ApiError(400, "studio_secao_nao_importada", texto, details=details)


def _base(nome: str) -> str:
    return nome.rsplit("/", 1)[-1]


def _conferir_entrada(arquivo: str, zi: zipfile.ZipInfo) -> None:
    nome = zi.filename
    partes = nome.split("/")
    if nome.startswith("/") or "\\" in nome or (len(nome) > 1 and nome[1] == ":"):
        raise _inseguro(arquivo, "caminho absoluto ou com barra invertida")
    if ".." in partes:
        raise _inseguro(arquivo, "caminho com '..'")
    if zi.is_dir() or len(partes) > 1:
        raise _inseguro(arquivo, "pasta dentro do ZIP")
    if stat.S_ISLNK(zi.external_attr >> 16):
        raise _inseguro(arquivo, "link simbólico")
    if zi.flag_bits & 0x1:
        raise _inseguro(arquivo, "entrada cifrada")
    if zi.compress_type not in METODOS:
        raise _inseguro(arquivo, "método de compressão não aceito")
    if nome.lower().endswith(".zip"):
        raise _inseguro(arquivo, "ZIP dentro do ZIP")
    if zi.file_size and zi.file_size / max(zi.compress_size, 1) > ZIP_RAZAO:
        raise _inseguro(arquivo, "expande demais")


def _ler_zip(env: Enviado, tz: ZoneInfo) -> Arquivo:
    try:
        zf = zipfile.ZipFile(io.BytesIO(env.dados))
    except (zipfile.BadZipFile, ValueError):
        raise _inseguro(env.nome, "ZIP corrompido") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > ZIP_ENTRADAS:
            raise _inseguro(env.nome, f"mais de {ZIP_ENTRADAS} entradas")
        nomes = {i.filename for i in infos}
        if "[Content_Types].xml" in nomes or env.nome.lower().endswith((".xlsx", ".xls")):
            raise _nao_importada(env.nome, "Planilha XLSX")
        if sum(i.file_size for i in infos) > ZIP_EXPANDIDO:
            raise _inseguro(env.nome, "expande demais")
        for zi in infos:
            _conferir_entrada(env.nome, zi)
        nome = datas.nome_zip(env.nome, tz)
        arquivo = Arquivo(env.nome, "zip", nome.handle if nome else None,
                          nome if nome and nome.secao != "outra" else None)
        for zi in infos:
            if zi.filename not in ENTRADAS:
                arquivo.ignorados.append(zi.filename)  # nunca aberta
                continue
            with zf.open(zi) as f:
                dados = f.read(CSV_TETO + 1)
            if len(dados) > CSV_TETO:
                raise _inseguro(env.nome, "expande demais")
            arquivo.csvs.append(Csv(env.nome, zi.filename, dados,
                                    hashlib.sha256(dados).hexdigest()))
    if not arquivo.csvs:
        outra = SECAO_DO_NOME.get(nome.outra or "") if nome else None
        raise _nao_importada(env.nome, outra)
    return arquivo


def ler_arquivo(env: Enviado, tz: ZoneInfo) -> Arquivo:
    """Um arquivo do envio: ZIP (pela assinatura) ou CSV solto."""
    if env.dados.startswith(ASSINATURAS_ZIP):
        return _ler_zip(env, tz)
    inicio = env.dados.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
    if env.dados.startswith(OLE) or env.nome.lower().endswith((".xlsx", ".xls")):
        raise _nao_importada(env.nome, "Planilha XLSX")
    if inicio in (b"{", b"[") or env.nome.lower().endswith((".json", ".txt")):
        raise _nao_importada(env.nome, "Baixar seus dados")
    return Arquivo(env.nome, "csv", None, None,
                   [Csv(env.nome, _base(env.nome), env.dados,
                        hashlib.sha256(env.dados).hexdigest())])
