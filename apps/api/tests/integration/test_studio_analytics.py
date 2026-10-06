"""O analytics com o histórico do Studio (spec 020, US3; T028 a T030).

**T028: regressão "sem Studio = números de hoje".** A referência foi gravada com o código da 019,
ANTES de qualquer mudança em `analytics/` (sem o arquivo
`tests/fixtures/studio/regressao_019.json`, ou com `STUDIO_GRAVAR_REFERENCIA=1`, o teste grava a
referência e é pulado; o arquivo fica no git). Sem importação, a visão geral (indicadores, série
diária e principais), o calendário de Quando postar e a tabela e o radar de Contas têm de sair
idênticos, em 3 períodos. As datas viram deslocamentos relativos a hoje, os ids viram rótulos
estáveis, e os campos novos da 020 (aditivos) ficam fora da comparação.
"""

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from integration.analytics_helpers import cena, hoje_sp, local  # noqa: F401
from integration.studio_helpers import st  # noqa: F401
from sociman_api.metricas.models import VideoRede
from sociman_api.perfis.models import Conta, Perfil

REFERENCIA = Path(__file__).resolve().parents[1] / "fixtures" / "studio" / "regressao_019.json"
CAMPOS_020 = {"diasStudio", "fonte", "comparacao", "visitasPerfil", "studio", "contasStudio"}
# Fora da comparação: os campos novos da 020 (aditivos) e o slug do perfil (contador do helper).
IGNORADOS = CAMPOS_020 | {"slug"}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INSTANTE = re.compile(r"^\d{4}-\d{2}-\d{2}T")


def cenario_019(c):
    """Duas contas em perfis diferentes, com a 1ª coleta dentro dos períodos (o "pico" do dia da
    1ª coleta continua igual sem Studio): A com 3 vídeos a cada 2 dias desde D−9, 40 fotos
    horárias; B com 2 vídeos desde D−5."""
    c.semear(videos=3, fotos=40, inicio=local(9, 10), intervalo_h=48)
    outra = c.segunda_conta("contab", outro_perfil=True)
    c.semear(outra, videos=2, fotos=40, inicio=local(5, 15), intervalo_h=30, views_por_h=30)
    return outra


def periodos() -> list[dict[str, str]]:
    return [{}, {"de": str(local(7).date()), "ate": str(local(7).date())},
            {"de": str(local(13).date()), "ate": str(local(0).date())}]


def _rotulos(db) -> dict[str, str]:
    out = {str(c.id): f"conta:@{c.handle}" for c in db.scalars(select(Conta))}
    out |= {str(p.id): f"perfil:{p.name}" for p in db.scalars(select(Perfil))}
    out |= {str(v.id): f"video:{v.rede_video_id}" for v in db.scalars(select(VideoRede))}
    return out


def normalizar(valor, rotulos: dict[str, str], hoje: date):
    if isinstance(valor, dict):
        return {k: normalizar(v, rotulos, hoje) for k, v in valor.items() if k not in IGNORADOS}
    if isinstance(valor, list):
        itens = [normalizar(v, rotulos, hoje) for v in valor]
        if itens and all(isinstance(i, dict) for i in itens):
            itens.sort(key=lambda i: json.dumps(i, sort_keys=True))
        return itens
    if isinstance(valor, str):
        if _DATA.match(valor):
            return f"D{(date.fromisoformat(valor) - hoje).days}"
        if _INSTANTE.match(valor):
            t = datetime.fromisoformat(valor)
            return f"D{(t.date() - hoje).days} {t:%H:%M:%S%z}"
        return _UUID.sub(lambda m: rotulos.get(m.group(0), "uuid"), valor)
    if isinstance(valor, float):
        return round(valor, 9)
    return valor


def saidas(c) -> dict:
    """As partes do analytics que a 020 mexe, normalizadas."""
    rotulos, hoje = _rotulos(c.db), hoje_sp()
    out = {}
    for i, params in enumerate(periodos()):
        vg = c.ok("visao-geral", **params)
        qp = c.ok("quando-postar", **params)
        ct = c.ok("contas", **params)
        out[f"p{i}"] = normalizar({
            "visaoGeral": {k: vg[k] for k in ("indicadores", "serieDiaria", "principais")},
            "calendario": qp["calendario"],
            "contas": {k: ct[k] for k in ("contas", "perfis", "radar", "radarMotivo")},
        }, rotulos, hoje)
    return out


def test_regressao_sem_studio_igual_a_019(cena):  # noqa: F811
    cenario_019(cena)
    atual = saidas(cena)
    if os.environ.get("STUDIO_GRAVAR_REFERENCIA") == "1" or not REFERENCIA.exists():
        REFERENCIA.parent.mkdir(parents=True, exist_ok=True)
        REFERENCIA.write_text(json.dumps(atual, ensure_ascii=False, indent=1, sort_keys=True))
        pytest.skip("referência gravada")
    # normalizar de novo é idempotente e tira da referência o que a comparação ignora
    referencia = normalizar(json.loads(REFERENCIA.read_text()), {}, hoje_sp())
    for chave in referencia:
        assert atual[chave] == referencia[chave], chave
    assert sorted(atual) == sorted(referencia)


# ---- T029 e T030: com Studio (referência = o analytics só com a coleta + os dias do Studio) ----

def _serie_conta(corpo: dict, rotulo: str) -> dict[str, dict]:
    return {d["dia"]: next(c for c in d["porConta"] if c["rotulo"] == rotulo)
            for d in corpo["serieDiaria"]}


def _ind(corpo: dict) -> dict[str, dict]:
    return {i["chave"]: i for i in corpo["indicadores"]}


def _cenario_studio(st):  # noqa: F811
    """A (@atavernanerd): 1ª coleta em D−3 09:00 (um vídeo com fotos horárias); Studio da Visão
    geral e de Seguidores de D−9 a D−2 (D−3 é o dia da 1ª coleta; D−2 já é coberto).
    B (@contab, outro perfil): coleta desde D−6. C (@contac, outro perfil): só Studio da Visão
    geral (D−6 a D−4), sem vídeo."""
    st.semear(videos=1, fotos=60, inicio=local(3, 9), serie_id=st.serie())
    b = st.segunda_conta("contab", outro_perfil=True)
    st.semear(b, videos=1, fotos=60, inicio=local(6, 9), views_por_h=10)
    c = st.segunda_conta("contac", outro_perfil=True)
    st.serie(c)
    return b, c


def _importar_a(st):  # noqa: F811
    from integration.studio_helpers import (
        overview_dias,
        seguidores_dias,
        zip_overview,
        zip_seguidores,
    )

    vg, seg = overview_dias(local(2).date(), 8), seguidores_dias(local(2).date(), 8)
    imp = st.importar(zip_overview(vg, HANDLE_A), zip_seguidores(seg, HANDLE_A))
    return imp, {str(x.dia): x for x in vg}, {str(d): (t, dif) for d, t, dif in seg}


def _importar_c(st, c):  # noqa: F811
    from integration.studio_helpers import DiaOverview, files, zip_overview

    vg = [DiaOverview(local(k).date(), 100 * k, likes=k) for k in (6, 5, 4)]
    r = st.client.post(f"/api/contas/{c['id']}/studio/previa", headers=st.h,
                       files=files(zip_overview(vg, "contac")))
    assert r.status_code == 201, r.text
    r = st.client.post(f"/api/contas/{c['id']}/studio/importacoes", headers=st.h,
                       json={"previaId": r.json()["previaId"]})
    assert r.status_code == 201, r.text
    return {str(x.dia): x for x in vg}


HANDLE_A = "atavernanerd"


def _partes(c, **params) -> dict:
    vg = c.ok("visao-geral", **params)
    qp = c.ok("quando-postar", **params)
    ct = c.ok("contas", **params)
    return {"vg": vg, "qp": qp, "ct": ct}


def test_analytics_usa_o_studio_nos_dias_sem_coleta(st):  # noqa: F811
    _, c = _cenario_studio(st)
    params = {"de": str(local(13).date()), "ate": str(local(0).date())}
    antes = _partes(st, **params)
    api_a = {d: v["views"] for d, v in _serie_conta(antes["vg"], "@atavernanerd").items()}
    _, vg_a, seg_a = _importar_a(st)
    vg_c = _importar_c(st, c)
    depois = _partes(st, **params)
    corpo = depois["vg"]

    studio_a = [str(local(k).date()) for k in range(9, 2, -1)]  # D−9..D−3 (não cobertos)
    serie = _serie_conta(corpo, "@atavernanerd")
    for dia, linha in serie.items():
        if dia in studio_a:
            assert linha["fonte"] == "studio" and linha["views"] == vg_a[dia].views, dia
            assert linha["visitasPerfil"] == vg_a[dia].visitas
        else:
            assert linha["fonte"] == "coletado" and linha["views"] == api_a[dia], dia
    # o dia da 1ª coleta usa o Studio, e a coleta (o "pico") vira a comparação
    d3 = str(local(3).date())
    assert serie[d3]["comparacao"] == api_a[d3] and api_a[d3] > 0
    # D−2 é coberto: vale a coleta, e o Studio vem como comparação
    d2 = str(local(2).date())
    assert serie[d2]["comparacao"] == vg_a[d2].views and serie[d2]["visitasPerfil"] is not None
    # a conta sem vídeo, só com Studio, aparece
    serie_c = _serie_conta(corpo, "@contac")
    assert serie_c[str(local(5).date())] == {
        "contaId": c["id"], "rotulo": "@contac", "views": 500, "fonte": "studio",
        "comparacao": None, "visitasPerfil": 0}

    # indicadores = a referência (só coleta) com os dias do Studio trocados
    ind, ref = _ind(corpo), _ind(antes["vg"])
    api_c = {d: 0 for d in vg_c}
    esperado_views = (ref["views"]["valor"] - sum(api_a[d] for d in studio_a)
                      + sum(vg_a[d].views for d in studio_a)
                      + sum(x.views for x in vg_c.values()) - sum(api_c.values()))
    assert ind["views"]["valor"] == esperado_views
    assert ind["views"]["diasStudio"] == 7 and ind["posts"]["diasStudio"] == 0
    assert ind["seguidores"]["diasStudio"] == 7
    assert depois["vg"]["contexto"]["studio"] == {"dias": 7, "series": 2}
    # seguidores: a coleta de A só vale de D−2 em diante; antes, a diferença do arquivo
    seg_ref = ref["seguidores"]["valor"]
    assert ind["seguidores"]["valor"] == pytest.approx(
        seg_ref - _seg_api(st, studio_a) + sum(seg_a[d][1] for d in studio_a))

    # calendário: studio, coletado e misto (B coletou em D−5, A e C vieram do Studio)
    cal = {d["dia"]: d for d in depois["qp"]["calendario"]}
    d5 = str(local(5).date())
    assert (cal[d5]["fonte"], cal[d5]["contasStudio"]) == ("misto", 2)
    assert cal[str(local(9).date())]["fonte"] == "studio"
    assert cal[str(local(1).date())]["fonte"] == "coletado"
    assert sum(d["views"] for d in cal.values()) == ind["views"]["valor"]
    # abas por vídeo ou hora: nada muda
    assert depois["qp"]["porPublicacao"] == antes["qp"]["porPublicacao"]
    assert depois["qp"]["audiencia"] == antes["qp"]["audiencia"]

    # contas: C aparece só com o Studio; sem Seguidores importados, fica sem dado
    linhas = {x["rotulo"]: _ind(x) for x in depois["ct"]["contas"]}
    assert linhas["@contac"]["views"]["valor"] == 1500
    assert linhas["@contac"]["views"]["diasStudio"] == 3
    assert linhas["@contac"]["seguidores"]["valor"] is None
    assert linhas["@atavernanerd"]["views"]["valor"] == ind["views"]["valor"] - 1500 - \
        sum(v["views"] for v in _serie_conta(corpo, "@contab").values())


def _seg_api(st, dias: list[str]) -> int:  # noqa: F811
    """Os seguidores ganhos de A pela coleta nos dias dados (a referência sem Studio)."""
    from sociman_api.metricas.studio import efetivo

    serie = st.serie()
    api = efetivo.api_por_dia(st.db, [serie], date.fromisoformat(min(dias)),
                              date.fromisoformat(max(dias)))[serie]
    return sum(api[date.fromisoformat(d)].seguidores_dif or 0 for d in dias)


def test_periodo_anterior_so_com_studio_tem_variacao(st):  # noqa: F811
    _cenario_studio(st)
    _, vg_a, _ = _importar_a(st)
    corpo = st.ok("visao-geral", de=str(local(6).date()), ate=str(local(0).date()),
                  contaId=st.conta_id)
    views = _ind(corpo)["views"]
    anterior = sum(vg_a[str(local(k).date())].views for k in (9, 8, 7))
    assert views["anterior"] == anterior and views["variacaoPct"] is not None


def test_desfazer_volta_aos_numeros_de_antes(st):  # noqa: F811
    _cenario_studio(st)
    params = {"de": str(local(13).date()), "ate": str(local(0).date())}
    antes = _partes(st, **params)
    imp, _, _ = _importar_a(st)
    assert _partes(st, **params)["vg"]["indicadores"] != antes["vg"]["indicadores"]
    assert st.desfazer(imp).status_code == 200
    depois = _partes(st, **params)
    for chave in ("indicadores", "serieDiaria", "contexto"):
        assert depois["vg"][chave] == antes["vg"][chave], chave
    assert depois["qp"]["calendario"] == antes["qp"]["calendario"]
    assert depois["ct"]["contas"] == antes["ct"]["contas"]
