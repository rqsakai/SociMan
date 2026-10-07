"""ZIP malicioso e envio (spec 020, T009; research R2): bomb (razão e tamanho), slip, link,
cifrado, aninhado, entradas demais, método bzip2, `Content.csv` nunca aberto (espião em
`ZipFile.open`), CSV renomeado de ZIP e o envio de 5 MB + 1 byte. Tudo em memória."""

import io
import zipfile
from zoneinfo import ZoneInfo

import pytest
from integration.studio_helpers import (
    csv_overview,
    overview_dias,
    zip_bytes,
    zip_conteudo,
    zip_overview,
    zip_seguidores,
)

from sociman_api.errors import ApiError
from sociman_api.metricas.studio import arquivos

TZ = ZoneInfo("America/Sao_Paulo")
CSV = csv_overview(overview_dias(n=3))


def _ler(nome: str, dados: bytes) -> arquivos.Arquivo:
    return arquivos.ler_arquivo(arquivos.Enviado(nome, dados), TZ)


def _recusa(nome: str, dados: bytes, codigo: str = "studio_zip_inseguro") -> ApiError:
    with pytest.raises(ApiError) as e:
        _ler(nome, dados)
    assert e.value.code == codigo, e.value.message
    return e.value


def _zip_cru(infos: list[tuple[zipfile.ZipInfo, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for info, dados in infos:
            zf.writestr(info, dados)
    return buf.getvalue()


def test_zips_do_formato_real():
    nome, dados = zip_overview()
    a = _ler(nome, dados)
    assert (a.tipo, a.handle, a.ignorados) == ("zip", "contateste", [])
    assert [c.entrada for c in a.csvs] == ["Overview.csv"] and len(a.csvs[0].sha) == 64
    nome, dados = zip_seguidores()
    a = _ler(nome, dados)
    # spec 022 (FR-004): os 3 CSVs de público passam a ser lidos, não ignorados
    assert [c.entrada for c in a.csvs] == ["FollowerHistory.csv", "FollowerActivity.csv",
                                           "FollowerGender.csv", "FollowerTopTerritories.csv"]
    assert a.ignorados == []


def test_sha_e_do_csv_e_nao_do_zip():
    a = _ler("Overview_x.zip", zip_bytes({"Overview.csv": CSV}))
    b = _ler("Overview_y.zip", zip_bytes({"Overview.csv": CSV}, zipfile.ZIP_DEFLATED))
    c = _ler("Overview.csv", CSV)
    assert a.csvs[0].sha == b.csvs[0].sha == c.csvs[0].sha


def test_content_nunca_e_aberto(monkeypatch):
    nome, dados = zip_conteudo()
    misto = zip_bytes({"Overview.csv": CSV, "Content.csv": b"titulo"})
    abertos: list[str] = []
    original = zipfile.ZipFile.open

    def espiao(self, nome, *a, **kw):
        abertos.append(getattr(nome, "filename", nome))
        return original(self, nome, *a, **kw)

    monkeypatch.setattr(zipfile.ZipFile, "open", espiao)
    e = _recusa(nome, dados, "studio_secao_nao_importada")
    assert e.details["secaoReconhecida"] == "Conteúdo"
    a = _ler("Overview_x.zip", misto)
    assert a.ignorados == ["Content.csv"]
    assert "Content.csv" not in abertos and abertos == ["Overview.csv"]


@pytest.mark.parametrize("nome", ["../Overview.csv", "/etc/Overview.csv", "C:\\Overview.csv",
                                  "pasta/Overview.csv", "a\\b.csv"])
def test_slip_e_pastas(nome):
    _recusa("x.zip", zip_bytes({nome: CSV}))


def _cifrado(dados: bytes) -> bytes:
    """Liga o bit 0 ("cifrado") nos cabeçalhos local e central (o `zipfile` não escreve)."""
    b = bytearray(dados)
    local = b.find(b"PK\x03\x04")
    central = b.find(b"PK\x01\x02")
    b[local + 6] |= 0x1
    b[central + 8] |= 0x1
    return bytes(b)


def test_link_simbolico():
    info = zipfile.ZipInfo("Overview.csv")
    info.external_attr = (0o120777 << 16)
    _recusa("x.zip", _zip_cru([(info, b"/etc/passwd")]))


def test_viewers_xlsx_que_nao_e_planilha_vai_para_studio_planilha():
    _recusa("Viewers_conta.zip", zip_bytes({"Viewers.xlsx": b"PK"}), "studio_planilha")


def test_cifrado_aninhado_e_metodo():
    _recusa("x.zip", _cifrado(zip_bytes({"Overview.csv": CSV})))
    _recusa("x.zip", zip_bytes({"Overview.csv": CSV, "dentro.zip": zip_bytes({"a": b"1"})}))
    _recusa("x.zip", zip_bytes({"Overview.csv": CSV}, zipfile.ZIP_BZIP2))


def test_entradas_demais():
    _recusa("x.zip", zip_bytes({f"f{i}.csv": b"" for i in range(21)}))
    _ler("x.zip", zip_bytes({"Overview.csv": CSV} | {f"f{i}.csv": b"" for i in range(19)}))


def test_bomb_por_razao_e_por_tamanho():
    _recusa("x.zip", zip_bytes({"Overview.csv": b"0" * 200_000}, zipfile.ZIP_DEFLATED))
    grande = zip_bytes({f"f{i}.csv": b"1" * (1024 * 1024 + 1) for i in range(20)},
                       zipfile.ZIP_STORED)
    _recusa("x.zip", grande)


def test_csv_renomeado_de_zip_e_lido_pela_assinatura():
    a = _ler("Overview.csv", zip_bytes({"Overview.csv": CSV}))
    assert a.tipo == "zip"


# Spec 022 (FR-003, FR-005): XLSX, `.xls` e o ZIP de Espectadores saem daqui e viram casos de
# `test_studio_planilha.py` (`studio_planilha`); só o "Baixar seus dados" continua.
@pytest.mark.parametrize(("nome", "dados"), [
    ("user_data.json", b'{"Activity": {}}'),
])
def test_secoes_nao_importadas(nome, dados):
    _recusa(nome, dados, "studio_secao_nao_importada")


class _Up:
    def __init__(self, nome: str, dados: bytes):
        self.filename = nome
        self.file = io.BytesIO(dados)


def test_envio_de_5mb_mais_1_byte():
    with pytest.raises(ApiError) as e:
        arquivos.ler_envio([_Up("a.csv", b"1" * (arquivos.LIMITE_ENVIO + 1))])
    assert (e.value.status, e.value.code) == (413, "arquivo_grande")
    with pytest.raises(ApiError) as e:
        arquivos.ler_envio([_Up("a.csv", b"1" * arquivos.LIMITE_ENVIO), _Up("b.csv", b"1")])
    assert e.value.code == "arquivo_grande"
    assert len(arquivos.ler_envio([_Up("a.csv", b"1" * arquivos.LIMITE_ENVIO)])) == 1


@pytest.mark.parametrize("n", [0, 4])  # spec 022: até 3 arquivos
def test_numero_de_arquivos(n):
    with pytest.raises(ApiError) as e:
        arquivos.ler_envio([_Up(f"{i}.csv", b"1") for i in range(n)])
    assert e.value.code == "studio_arquivos" and e.value.details == {"recebidos": n}
