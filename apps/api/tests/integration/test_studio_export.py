"""Exportação com o Studio (spec 020, US5, T041; research R10): `studio_dias.csv` e `.jsonl` só
das importações ativas, as colunas do dicionário, `efetivo_*` corretos, o `dicionario.csv` com a
versão 2 e uma série anônima como "Conta anônima N"."""

import csv
import io
import json
import zipfile
from datetime import timedelta

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    DiaOverview,
    overview_dias,
    seguidores_dias,
    semear_coleta,
    st,  # noqa: F401
    zip_overview,
    zip_seguidores,
)
from sociman_api.auth.deps import Actor
from sociman_api.metricas import anonimizar, dicionario
from sociman_api.metricas.models import Serie

H = "atavernanerd"


def _zip(st, formato="csv", **extra) -> zipfile.ZipFile:  # noqa: F811
    params = {"formato": formato, "de": str(local(15).date()), "ate": str(local(0).date()),
              **extra}
    r = st.client.get("/api/metricas/export", headers=st.h, params=params)
    assert r.status_code == 200, r.text
    return zipfile.ZipFile(io.BytesIO(r.content))


def _linhas(zf, nome="studio_dias.csv") -> list[dict]:
    dados = zf.read(nome)
    assert dados.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(dados.decode("utf-8-sig"))))


def test_studio_dias_com_efetivo_e_dicionario(st):  # noqa: F811
    serie = st.serie()
    semear_coleta(st.db, st.conta_id, local(2, 9), serie_id=serie)  # coberto desde D−1
    ate = local(1).date()
    a = st.importar(zip_overview(overview_dias(ate, 3), H),
                    zip_seguidores(seguidores_dias(ate, 3), H))
    outros = [DiaOverview(x.dia, x.views + 9) for x in overview_dias(ate, 4)]
    b = st.importar(zip_overview(outros, H))
    desfeita = st.importar(zip_overview(overview_dias(local(12).date(), 2), H))
    st.desfazer(desfeita)

    zf = _zip(st)
    assert "studio_dias.csv" in zf.namelist()
    cab = next(csv.reader(io.StringIO(zf.read("studio_dias.csv").decode("utf-8-sig"))))
    assert cab == dicionario.colunas("studio_dias")
    linhas = _linhas(zf)
    assert {r["importacao_id"] for r in linhas} == {a["id"], b["id"]}  # sem a desfeita
    assert len(linhas) == 3 + 4
    por = {(r["importacao_id"], r["dia"]): r for r in linhas}
    d2, d1 = str(ate - timedelta(days=1)), str(ate)
    # D−2 (dia da 1ª coleta, não coberto): vale a importação A, a mais antiga
    assert por[(a["id"], d2)]["efetivo_visao_geral"] == "true"
    assert por[(b["id"], d2)]["efetivo_visao_geral"] == "false"
    assert por[(a["id"], d2)]["efetivo_seguidores"] == "true"
    assert por[(b["id"], d2)]["efetivo_seguidores"] == ""  # B não trouxe seguidores
    # D−1 é coberto pela coleta: nenhum valor do Studio vale
    assert por[(a["id"], d1)]["efetivo_visao_geral"] == "false"
    # D−4 só existe em B
    assert por[(b["id"], str(ate - timedelta(days=3)))]["efetivo_visao_geral"] == "true"
    r = por[(a["id"], d1)]
    assert r["serie_ref"] == str(serie) and r["conta"] == f"@{H}"
    assert r["views"] == str(overview_dias(ate, 3)[-1].views) and r["importada_em"]
    dic = list(csv.DictReader(io.StringIO(zf.read("dicionario.csv").decode("utf-8-sig"))))
    assert {d["coluna"] for d in dic if d["arquivo"] == "studio_dias.csv"} == set(
        dicionario.colunas("studio_dias"))
    # spec 022: o dicionário vai para a versão 3 (o público do Studio); o studio_dias não muda
    assert dicionario.DICIONARIO_VERSAO >= 3
    assert f"Versão do dicionário: {dicionario.DICIONARIO_VERSAO}" in zf.read(
        "LEIAME.txt").decode("utf-8-sig")


def test_jsonl_e_serie_anonima(st):  # noqa: F811
    st.importar(zip_overview(overview_dias(n=3), H))
    jl = _zip(st, "jsonl")
    linhas = [json.loads(x) for x in jl.read("studio_dias.jsonl").decode().splitlines()]
    assert len(linhas) == 3 and all(list(x) == dicionario.colunas("studio_dias") for x in linhas)
    assert isinstance(linhas[0]["views"], int) and linhas[0]["efetivo_visao_geral"] is True
    serie = st.db.get(Serie, st.serie())
    anonimizar.serie(st.db, serie, Actor(kind="user", user_id=st.dono.id))
    st.db.commit()
    zf = _zip(st, incluirAnonimas="true")
    linhas = _linhas(zf)
    assert len(linhas) == 3
    assert all(r["serie_ref"].startswith("Conta anônima") and r["conta"] == r["serie_ref"]
               for r in linhas)
    assert _linhas(_zip(st)) == []  # sem as anônimas
