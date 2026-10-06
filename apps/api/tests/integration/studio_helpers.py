"""Gerador **sintético** dos arquivos do TikTok Studio (spec 020, research R13), no formato do
arquivo real (notas-pesquisa §0): CSV em UTF-8 com BOM, todos os campos entre aspas, sem quebra de
linha no fim, datas sem ano ("September 25"); ZIPs *stored* com as entradas na raiz,
`Overview_<início>_<epoch>_<handle>.zip` e `Followers_<handle>.zip` (com Activity, Gender e
Territories só com o cabeçalho), e um `Content_<handle>.zip` com título falso.

Os números são inventados. **Nenhum arquivo real do dono entra aqui.** Também é uma CLI para o
quickstart (§2):

    uv run python -m tests.integration.studio_helpers --handle H --saida DIR [--dias 7]
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
                   handle: str = HANDLE, **kw) -> tuple[str, bytes]:
    linhas = linhas or seguidores_dias()
    return f"Followers_{handle}.zip", zip_bytes({
        "FollowerHistory.csv": csv_seguidores(linhas, **kw),
        "FollowerActivity.csv": csv_bytes(("Date", "Hour", "Active followers"), []),
        "FollowerGender.csv": csv_bytes(("Gender", "Distribution"), []),
        "FollowerTopTerritories.csv": csv_bytes(("Top territories", "Distribution"), []),
    })


def zip_conteudo(handle: str = HANDLE) -> tuple[str, bytes]:
    conteudo = csv_bytes(("Video title", "Video link", "Post time", "Video views"),
                         [("Título falso de teste", "https://example.invalid/v/1",
                           "2026-09-25 10:00", 10)])
    return f"Content_{handle}.zip", zip_bytes({"Content.csv": conteudo})


def files(*arquivos: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    """Para o `TestClient`: `files=files(zip_overview(), …)`."""
    out = []
    for nome, dados in arquivos:
        mime = "application/zip" if nome.endswith(".zip") else "text/csv"
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
    args = p.parse_args(argv)
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    for nome, dados in (zip_overview(overview_dias(n=args.dias), args.handle),
                        zip_seguidores(seguidores_dias(n=args.dias), args.handle),
                        zip_conteudo(args.handle)):
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
