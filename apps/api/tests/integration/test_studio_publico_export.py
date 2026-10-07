"""Exportação do público (spec 022, US5, T044; FR-029, R10): os 3 CSVs (e `.jsonl`) só das
ativas, com `importacao_id` e `efetivo`; o período pelo `dia` e pela `data_foto`; o
`dicionario.csv` na versão 3 com as colunas novas no fim; o `studio_dias.csv` da 020 igual."""

import csv
import io
import json
import zipfile

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    csv_genero,
    overview_dias,
    seguidores_dias,
    st,  # noqa: F401
    viewers_dias,
    zip_overview,
    zip_seguidores,
    zip_viewers,
)
from sociman_api.metricas import dicionario

H = "atavernanerd"
ARQUIVOS = ("studio_distribuicoes", "studio_atividade", "studio_espectadores")


def _zip(st, formato="csv", de=15, ate=0) -> zipfile.ZipFile:  # noqa: F811
    r = st.client.get("/api/metricas/export", headers=st.h, params={
        "formato": formato, "de": str(local(de).date()), "ate": str(local(ate).date())})
    assert r.status_code == 200, r.text
    return zipfile.ZipFile(io.BytesIO(r.content))


def _linhas(zf, nome) -> list[dict]:
    return list(csv.DictReader(io.StringIO(zf.read(nome).decode("utf-8-sig"))))


def test_tres_arquivos_com_efetivo_e_dicionario(st):  # noqa: F811
    ate = local(1).date()
    st.importar(zip_overview(overview_dias(ate, 3), H),
                zip_seguidores(seguidores_dias(ate, 3), H))
    sem_publico = _zip(st).read("studio_dias.csv")
    # o mesmo FollowerHistory.csv (já importado): só as seções de público entram
    a = st.importar(zip_seguidores(seguidores_dias(ate, 3), H, publico=True),
                    zip_viewers(viewers_dias(ate), H))
    b = st.importar(("FollowerGender.csv", csv_genero((("Female", "50%"), ("Male", "50%")))),
                    confirmo=True)
    desfeita = st.importar(zip_viewers(viewers_dias(local(10).date()), H))
    st.desfazer(desfeita)

    zf = _zip(st)
    assert zf.read("studio_dias.csv") == sem_publico  # a 020 igual
    for nome in ARQUIVOS:
        cab = next(csv.reader(io.StringIO(zf.read(f"{nome}.csv").decode("utf-8-sig"))))
        assert cab == dicionario.colunas(nome)
    dist = _linhas(zf, "studio_distribuicoes.csv")
    assert {r["importacao_id"] for r in dist} == {a["id"], b["id"]}
    genero = [r for r in dist if r["tipo"] == "genero"]
    data_a, data_b = a["dataFoto"], b["dataFoto"]
    efetivos = {(r["importacao_id"], r["rotulo"]): r["efetivo"] for r in genero}
    if data_a == data_b:  # mesma data: vale a foto da mais antiga (A)
        assert efetivos[(a["id"], "feminino")] == "true"
        assert efetivos[(b["id"], "feminino")] == "false"
    assert {r["pct"] for r in genero if r["importacao_id"] == a["id"]} == {"61.0", "37.5", "1.5"}
    atv = _linhas(zf, "studio_atividade.csv")
    assert len(atv) == 72 and all(r["efetivo"] == "true" for r in atv)
    assert atv[0]["conta"] == f"@{H}" and atv[0]["hora"] == "0"
    esp = _linhas(zf, "studio_espectadores.csv")
    assert {r["importacao_id"] for r in esp} == {a["id"]}  # sem a desfeita
    assert esp[0]["total"] == "" and esp[0]["novos"] == "0"
    dic = list(csv.DictReader(io.StringIO(zf.read("dicionario.csv").decode("utf-8-sig"))))
    arquivos = [d["arquivo"].rsplit(".", 1)[0] for d in dic]
    ultimo_020 = max(i for i, x in enumerate(arquivos) if x == "studio_dias")
    assert all(i > ultimo_020 for i, x in enumerate(arquivos) if x in ARQUIVOS)
    assert dicionario.DICIONARIO_VERSAO >= 3


def test_periodo_pelo_dia_e_pela_data_foto_e_jsonl(st):  # noqa: F811
    st.importar(("FollowerGender.csv", csv_genero()), confirmo=True)  # foto de hoje
    st.importar(zip_viewers(viewers_dias(local(20).date()), H))
    zf = _zip(st, de=10, ate=0)
    assert len(_linhas(zf, "studio_distribuicoes.csv")) == 3
    assert _linhas(zf, "studio_espectadores.csv") == []
    zf = _zip(st, de=30, ate=1)
    assert _linhas(zf, "studio_distribuicoes.csv") == []
    assert len(_linhas(zf, "studio_espectadores.csv")) == 7
    jl = _zip(st, "jsonl", de=30, ate=0)
    linhas = [json.loads(x) for x in jl.read("studio_espectadores.jsonl").decode().splitlines()]
    assert all(list(x) == dicionario.colunas("studio_espectadores") for x in linhas)
    assert linhas[0]["total"] is None and linhas[0]["efetivo"] is True
    d = [json.loads(x) for x in jl.read("studio_distribuicoes.jsonl").decode().splitlines()]
    assert isinstance(d[0]["pct"], float)
