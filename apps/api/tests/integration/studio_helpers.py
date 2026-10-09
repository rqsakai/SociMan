"""Gerador **sintético** dos arquivos do TikTok Studio (spec 020, research R13), no formato do
arquivo real (notas-pesquisa §0): CSV em UTF-8 com BOM, todos os campos entre aspas, sem quebra de
linha no fim, datas sem ano ("September 25"); ZIPs *stored* com as entradas na raiz,
`Overview_<início>_<epoch>_<handle>.zip` e `Followers_<handle>.zip` (com Activity, Gender e
Territories só com o cabeçalho), e um `Content_<handle>.zip` com título falso.

Spec 022: os 3 CSVs de público preenchidos (gênero, territórios, atividade), o `Viewers.xlsx`
montado em memória com `zipfile` (as mesmas partes do real, células `t="str"`, `undefined` no 1º
dia, sem `sharedStrings`) e o `Viewers_<handle>.zip`, mais as variantes com defeito
(`xlsx_viewers(defeito=...)`).

Os números são inventados. **Nenhum arquivo real do dono entra aqui.** Também é uma CLI para o
quickstart (§2):

    uv run python -m tests.integration.studio_helpers --handle H --saida DIR [--dias 7]
        [--publico | --publico-vazio] [--defeito formula|macro|doctype|protegido|abas|...]
"""

import argparse
import io
import uuid
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("America/Sao_Paulo")
HANDLE = "contateste"
MESES_EN = ("January", "February", "March", "April", "May", "June", "July", "August",
            "September", "October", "November", "December")
MESES_PT = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
            "setembro", "outubro", "novembro", "dezembro")
CAB_OVERVIEW = ("Date", "Video Views", "Profile Views", "Likes", "Comments", "Shares")
CAB_OVERVIEW_PT = ("Data", "Visualizações de vídeo", "Visualizações do perfil", "Curtidas",
                   "Comentários", "Compartilhamentos")
CAB_SEGUIDORES = ("Date", "Followers", "Difference in followers from previous day")
CAB_SEGUIDORES_PT = ("Data", "Seguidores", "Diferença de seguidores em relação ao dia anterior")
# Inventados, com picos e zeros como num arquivo real.
VIEWS = (97, 240, 0, 3, 11, 702, 1188, 45, 0, 310, 56, 9)
SEGUIDORES = (10, 10, 11, 11, 13, 16, 19, 19, 18, 22, 22, 23)


def hoje() -> date:
    return datetime.now(TZ).date()


def data_en(d: date) -> str:
    return f"{MESES_EN[d.month - 1]} {d.day}"


def data_pt(d: date) -> str:
    return f"{d.day} de {MESES_PT[d.month - 1]}"


def csv_bytes(cabecalho: Sequence[str], linhas: Sequence[Sequence[object]]) -> bytes:
    """Como o Studio: BOM, tudo entre aspas, `\\n` entre linhas e nenhum no fim."""
    todas = [cabecalho, *linhas]
    texto = "\n".join(",".join(f'"{c}"' for c in linha) for linha in todas)
    return texto.encode("utf-8-sig")


def dias(ate: date, n: int) -> list[date]:
    return [ate - timedelta(days=n - 1 - k) for k in range(n)]


@dataclass(frozen=True)
class DiaOverview:
    dia: date
    views: int
    visitas: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0


def overview_dias(ate: date | None = None, n: int = 7) -> list[DiaOverview]:
    ate = ate or hoje() - timedelta(days=1)
    return [DiaOverview(d, VIEWS[k % len(VIEWS)], k % 3, VIEWS[k % len(VIEWS)] // 10, k % 2,
                        int(k % 4 == 0)) for k, d in enumerate(dias(ate, n))]


def seguidores_dias(ate: date | None = None, n: int = 7) -> list[tuple[date, int, int]]:
    ate = ate or hoje() - timedelta(days=1)
    out, anterior = [], None
    for k, d in enumerate(dias(ate, n)):
        total = SEGUIDORES[k % len(SEGUIDORES)]
        out.append((d, total, 0 if anterior is None else total - anterior))
        anterior = total
    return out


def csv_overview(linhas: Sequence[DiaOverview], *, pt: bool = False,
                 cabecalho: Sequence[str] | None = None) -> bytes:
    fmt = data_pt if pt else data_en
    cab = cabecalho or (CAB_OVERVIEW_PT if pt else CAB_OVERVIEW)
    return csv_bytes(cab, [(fmt(x.dia), x.views, x.visitas, x.likes, x.comments, x.shares)
                           for x in linhas])


def csv_seguidores(linhas: Sequence[tuple[date, int, int]], *, pt: bool = False) -> bytes:
    fmt = data_pt if pt else data_en
    return csv_bytes(CAB_SEGUIDORES_PT if pt else CAB_SEGUIDORES,
                     [(fmt(d), total, dif) for d, total, dif in linhas])


def zip_bytes(entradas: dict[str, bytes], metodo: int = zipfile.ZIP_STORED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", metodo) as zf:
        for nome, dados in entradas.items():
            zf.writestr(nome, dados)
    return buf.getvalue()


def epoch_fim(ate: date) -> int:
    """O instante do fim no nome do ZIP (como o real: o fim do período às 18:46 locais)."""
    return int(datetime.combine(ate, time(18, 46, 14), TZ).timestamp())


def nome_overview(linhas: Sequence[DiaOverview], handle: str = HANDLE) -> str:
    return f"Overview_{linhas[0].dia.isoformat()}_{epoch_fim(linhas[-1].dia)}_{handle}.zip"


def zip_overview(linhas: Sequence[DiaOverview] | None = None, handle: str = HANDLE,
                 **kw) -> tuple[str, bytes]:
    linhas = linhas or overview_dias()
    return nome_overview(linhas, handle), zip_bytes({"Overview.csv": csv_overview(linhas, **kw)})


def zip_seguidores(linhas: Sequence[tuple[date, int, int]] | None = None,
                   handle: str = HANDLE, *, publico: bool = False, historico: bool = True,
                   **kw) -> tuple[str, bytes]:
    """Como o real: o `FollowerHistory.csv` e os 3 de público só com o cabeçalho; com
    `publico=True`, os 3 preenchidos (a atividade nos mesmos dias do histórico)."""
    linhas = linhas or seguidores_dias()
    entradas = {"FollowerHistory.csv": csv_seguidores(linhas, **kw)} if historico else {}
    if publico:
        entradas |= {"FollowerActivity.csv": csv_atividade([d for d, _, _ in linhas]),
                     "FollowerGender.csv": csv_genero(),
                     "FollowerTopTerritories.csv": csv_territorios()}
    else:
        entradas |= {"FollowerActivity.csv": csv_bytes(CAB_ATIVIDADE, []),
                     "FollowerGender.csv": csv_bytes(CAB_GENERO, []),
                     "FollowerTopTerritories.csv": csv_bytes(CAB_TERRITORIOS, [])}
    return f"Followers_{handle}.zip", zip_bytes(entradas)


# ---- spec 022: público ----

CAB_GENERO = ("Gender", "Distribution")
CAB_TERRITORIOS = ("Top territories", "Distribution")
CAB_ATIVIDADE = ("Date", "Hour", "Active followers")
CAB_VIEWERS = ("Date", "Total Viewers", "New Viewers", "Returning Viewers")
GENERO = (("Female", "61%"), ("Male", "37.5%"), ("Other", "1.5%"))
TERRITORIOS = (("BR", "92.5%"), ("PT", "3.1%"), ("US", "1.4%"))
# Inventados: (total, novos, recorrentes); o 1º como o real (total `undefined`, 0, 0).
VIEWERS = ((None, 0, 0), (104, 104, 0), (181, 181, 0), (1, 1, 0), (2, 2, 0), (3, 3, 0),
           (663, 622, 41))


def ativos(dia: date, hora: int) -> int:
    """Seguidores ativos inventados, com pico às 20 h."""
    return max(0, 40 - 2 * abs(20 - hora)) + dia.day % 3


def csv_genero(itens: Sequence[tuple[str, str]] = GENERO, *, pt: bool = False) -> bytes:
    return csv_bytes(("Gênero", "Distribuição") if pt else CAB_GENERO, itens)


def csv_territorios(itens: Sequence[tuple[str, str]] = TERRITORIOS) -> bytes:
    return csv_bytes(CAB_TERRITORIOS, itens)


def csv_atividade(dias_: Sequence[date], horas: Sequence[int] = range(24), *,
                  por_hora: bool = False) -> bytes:
    """Uma linha por (dia, hora); `por_hora` ordena pela hora (o formato com dados ainda não foi
    visto, R4)."""
    pares = [(d, h) for h in horas for d in dias_] if por_hora else \
        [(d, h) for d in dias_ for h in horas]
    return csv_bytes(CAB_ATIVIDADE, [(data_en(d), h, ativos(d, h)) for d, h in pares])


def viewers_dias(ate: date | None = None, valores=VIEWERS) -> list[tuple[date, tuple]]:
    ate = ate or hoje() - timedelta(days=1)
    return list(zip(dias(ate, len(valores)), valores, strict=True))


_CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
       'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
       '<Override PartName="/xl/workbook.xml" ContentType="{wb}"/>'
       '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.'
       'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>{extra}</Types>')
_WB_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
         'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _coluna(i: int) -> str:
    return "ABCDEFGHIJ"[i]


def _celula(ref: str, valor, tipo: str = "str") -> str:
    if valor is None:
        return ""
    if tipo == "n":
        return f'<c r="{ref}"><v>{valor}</v></c>'
    if tipo == "inlineStr":
        return f'<c r="{ref}" t="inlineStr"><is><t>{valor}</t></is></c>'
    return f'<c r="{ref}" t="{tipo}"><v>{valor}</v></c>'


def xlsx_viewers(linhas: Sequence[tuple[date, tuple]] | None = None, *,
                 defeito: str | None = None, cabecalho: Sequence[str] = CAB_VIEWERS,
                 aba: str = "Viewers") -> bytes:
    """O `Viewers.xlsx` como o real: 1 aba, células `t="str"`, `undefined` no total do 1º dia,
    entradas *stored*. `defeito`: `formula`, `macro`, `doctype`, `entity`, `protegido`,
    `abas` (outra aba antes, sem a Viewers), `abas_com_viewers` (Viewers + outra), `externo`,
    `compartilhado` (sharedStrings), `serie` (data como número de série), `inline`,
    `letras` ("abc" em B4), `zip_dentro`, `soma` (total ≠ novos + recorrentes)."""
    linhas = list(viewers_dias() if linhas is None else linhas)
    if defeito == "soma":
        d, (t, n, r) = linhas[1]
        linhas[1] = (d, (t + 5, n, r))
    compartilhados: list[str] = []
    linhas_xml = ["".join(_celula(f"{_coluna(i)}1", c) for i, c in enumerate(cabecalho))]
    for k, (d, vals) in enumerate(linhas, start=2):
        if defeito == "serie":
            data = _celula(f"A{k}", (d - date(1899, 12, 30)).days, "n")
        elif defeito == "inline":
            data = _celula(f"A{k}", data_en(d), "inlineStr")
        elif defeito == "compartilhado":
            compartilhados.append(data_en(d))
            data = _celula(f"A{k}", len(compartilhados) - 1, "s")
        else:
            data = _celula(f"A{k}", data_en(d))
        cels = [data]
        for i, v in enumerate(vals, start=1):
            texto = "undefined" if v is None else str(v)
            if defeito == "letras" and (k, i) == (4, 1):
                texto = "abc"
            if defeito == "formula" and (k, i) == (3, 1):
                cels.append(f'<c r="B3"><f>SUM(C3:D3)</f><v>{texto}</v></c>')
                continue
            cels.append(_celula(f"{_coluna(i)}{k}", texto))
        linhas_xml.append("".join(cels))
    corpo = "".join(f'<row r="{n}">{c}</row>' for n, c in enumerate(linhas_xml, start=1))
    protecao = '<sheetProtection sheet="1"/>' if defeito == "protegido" else ""
    dtd = '<!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>' \
        if defeito == "doctype" else ""
    entidade = '<!ENTITY x SYSTEM "file:///etc/passwd">' if defeito == "entity" else ""
    sheet = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n{dtd}{entidade}'
             f'<worksheet xmlns="{_NS_MAIN}" xmlns:r="{_NS_REL}"><sheetData>{corpo}</sheetData>'
             f'{protecao}</worksheet>')
    abas = [(aba, "rId1", "worksheets/sheet1.xml")]
    if defeito == "abas":
        abas = [("Outra", "rId2", "worksheets/sheet2.xml"), ("Mais", "rId1",
                                                             "worksheets/sheet1.xml")]
    elif defeito == "abas_com_viewers":
        abas = [("Resumo", "rId2", "worksheets/sheet2.xml"), *abas]
    wb = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          f'<workbook xmlns="{_NS_MAIN}" xmlns:r="{_NS_REL}"><sheets>'
          + "".join(f'<sheet name="{n}" sheetId="{i}" r:id="{r}"/>'
                    for i, (n, r, _) in enumerate(abas, start=1))
          + "</sheets></workbook>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="{r}" Type="http://schemas.openxmlformats.org/'
                      f'officeDocument/2006/relationships/worksheet" Target="{t}"/>'
                      for _, r, t in abas) + "</Relationships>")
    wb_ct = "application/vnd.ms-excel.sheet.macroEnabled.main+xml" if defeito == "macro" \
        else _WB_CT
    entradas = {"[Content_Types].xml": _CT.format(wb=wb_ct, extra="").encode(),
                "_rels/.rels": _RELS.encode(), "xl/workbook.xml": wb.encode(),
                "xl/_rels/workbook.xml.rels": rels.encode(),
                "xl/worksheets/sheet1.xml": sheet.encode()}
    if defeito in ("abas", "abas_com_viewers"):
        entradas["xl/worksheets/sheet2.xml"] = (
            f'<worksheet xmlns="{_NS_MAIN}"><sheetData><row r="1">'
            '<c r="A1" t="str"><v>segredo</v></c></row></sheetData></worksheet>').encode()
    if compartilhados:
        entradas["xl/sharedStrings.xml"] = (
            f'<sst xmlns="{_NS_MAIN}">' + "".join(f"<si><t>{t}</t></si>" for t in compartilhados)
            + "</sst>").encode()
    if defeito == "macro":
        entradas["xl/vbaProject.bin"] = b"\x00macro"
    if defeito == "externo":
        entradas["xl/externalLinks/externalLink1.xml"] = b"<externalLink/>"
    if defeito == "zip_dentro":
        entradas["xl/embeddings/outro.zip"] = zip_bytes({"a.txt": b"1"})
    return zip_bytes(entradas)


def zip_viewers(linhas: Sequence[tuple[date, tuple]] | None = None, handle: str = HANDLE,
                **kw) -> tuple[str, bytes]:
    return f"Viewers_{handle}.zip", zip_bytes({"Viewers.xlsx": xlsx_viewers(linhas, **kw)})


def zip_conteudo(handle: str = HANDLE) -> tuple[str, bytes]:
    conteudo = csv_bytes(("Video title", "Video link", "Post time", "Video views"),
                         [("Título falso de teste", "https://example.invalid/v/1",
                           "2026-09-25 10:00", 10)])
    return f"Content_{handle}.zip", zip_bytes({"Content.csv": conteudo})


def files(*arquivos: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    """Para o `TestClient`: `files=files(zip_overview(), …)`."""
    out = []
    for nome, dados in arquivos:
        mime = "application/zip" if nome.endswith(".zip") else (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if nome.endswith(".xlsx") else "text/csv")
        out.append(("arquivos", (nome, dados, mime)))
    return out


def semear_coleta(db, conta_id, primeira_em: datetime, *, videos: int = 1, fotos: int = 48,
                  views_por_h: int = 100, serie_id=None):
    """Coleta da 016 começando em `primeira_em` (reusa `metricas_helpers.semear`)."""
    from integration.metricas_helpers import semear

    return semear(db, conta_id, videos=videos, fotos=fotos, inicio=primeira_em,
                  views_por_h=views_por_h, serie_id=serie_id)


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Gera os ZIPs sintéticos do Studio (spec 020)")
    p.add_argument("--handle", default=HANDLE)
    p.add_argument("--saida", required=True)
    p.add_argument("--dias", type=int, default=7)
    p.add_argument("--publico", action="store_true",
                   help="os 3 CSVs de público preenchidos e o Viewers_<handle>.zip")
    p.add_argument("--publico-vazio", action="store_true",
                   help="os 3 CSVs de público só com o cabeçalho (como o real)")
    p.add_argument("--defeito", help="um Viewers_<handle>.zip com defeito (ver xlsx_viewers)")
    args = p.parse_args(argv)
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    gerados = [zip_overview(overview_dias(n=args.dias), args.handle),
               zip_seguidores(seguidores_dias(n=args.dias), args.handle,
                              publico=args.publico and not args.publico_vazio),
               zip_conteudo(args.handle)]
    if args.publico:
        gerados.append(zip_viewers(handle=args.handle))
    if args.defeito:
        nome, dados = zip_viewers(handle=args.handle, defeito=args.defeito)
        (saida / args.defeito).mkdir(exist_ok=True)  # o mesmo nome do Studio, noutra pasta
        gerados.append((f"{args.defeito}/{nome}", dados))
    for nome, dados in gerados:
        (saida / nome).write_bytes(dados)
        print(saida / nome)
    (saida / "Overview.csv").write_bytes(csv_overview(overview_dias(n=args.dias)))
    print(saida / "Overview.csv")


# ---- cena dos testes de integração ----

HANDLE_CENA = "atavernanerd"  # o @ da conta do `analytics_helpers.cena`


@dataclass
class Studio:
    """A `cena` da 019 (dono, perfil e @atavernanerd) com a série viva e as rotas da 020."""

    cena: object

    def __getattr__(self, nome):
        return getattr(self.cena, nome)

    @property
    def conta_id(self) -> str:
        return self.cena.conta["id"]

    def serie(self, conta: dict | None = None) -> uuid.UUID:
        """A série viva da conta (criada sem fotos se ainda não existe)."""
        from sqlalchemy import select

        from sociman_api.metricas.models import Serie
        from sociman_api.perfis.models import Platform

        conta_id = uuid.UUID((conta or self.cena.conta)["id"])
        db = self.cena.db
        db.expire_all()
        serie = db.scalar(select(Serie).where(Serie.conta_id == conta_id,
                                              Serie.anonimizada_em.is_(None)))
        if serie is None:
            serie = Serie(rede=Platform.tiktok, conta_id=conta_id)
            db.add(serie)
            db.commit()
        return serie.id

    def previa(self, *arquivos: tuple[str, bytes], h: dict | None = None,
               conta_id: str | None = None):
        return self.cena.client.post(f"/api/contas/{conta_id or self.conta_id}/studio/previa",
                                     headers=h or self.cena.h, files=files(*arquivos))

    def previa_ok(self, *arquivos: tuple[str, bytes], **kw) -> dict:
        r = self.previa(*arquivos, **kw)
        assert r.status_code == 201, r.text
        return r.json()

    def confirmar(self, previa_id: str, confirmo: bool = False, h: dict | None = None,
                  conta_id: str | None = None):
        return self.cena.client.post(
            f"/api/contas/{conta_id or self.conta_id}/studio/importacoes",
            headers=h or self.cena.h, json={"previaId": previa_id, "confirmoConta": confirmo})

    def importar(self, *arquivos: tuple[str, bytes], confirmo: bool = False) -> dict:
        p = self.previa_ok(*arquivos)
        r = self.confirmar(p["previaId"], confirmo)
        assert r.status_code == 201, r.text
        return r.json()

    def desfazer(self, imp: dict, h: dict | None = None, version: int | None = None):
        return self.cena.client.post(f"/api/studio/importacoes/{imp['id']}/desfazer",
                                     headers=h or self.cena.h,
                                     json={"version": version or imp["version"]})

    def importacoes(self, h: dict | None = None) -> list[dict]:
        r = self.cena.client.get(f"/api/contas/{self.conta_id}/studio/importacoes",
                                 headers=h or self.cena.h)
        assert r.status_code == 200, r.text
        return r.json()["items"]

    def cobertura(self, h: dict | None = None) -> dict:
        r = self.cena.client.get(f"/api/contas/{self.conta_id}/studio/cobertura",
                                 headers=h or self.cena.h)
        assert r.status_code == 200, r.text
        return r.json()

    def contar(self) -> tuple[int, int]:
        """(importações, dias) no banco."""
        from sqlalchemy import func, select

        from sociman_api.metricas.studio.models import DiaStudio, Importacao

        db = self.cena.db
        db.expire_all()
        return (db.scalar(select(func.count()).select_from(Importacao)),
                db.scalar(select(func.count()).select_from(DiaStudio)))


@pytest.fixture
def st(cena) -> Studio:
    """Dono, perfil, @atavernanerd e a série viva dela (sem coleta)."""
    s = Studio(cena)
    s.serie()
    return s


def err(r) -> str:
    return r.json()["error"]["code"]


if __name__ == "__main__":
    main()
