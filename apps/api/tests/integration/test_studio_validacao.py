"""Arquivo íntegro e conta certa (spec 020, US2, T023 a T025), pela rota (SC-003): cada defeito
recusado com o código, a linha e a coluna certos, 0 linhas no banco e nenhuma chave no Redis; o @
do ZIP conferido; o CSV solto pede a confirmação; os avisos que não bloqueiam."""

from datetime import timedelta

import pytest

from integration.analytics_helpers import cena, hoje_sp, local  # noqa: F401
from integration.postagem_helpers import criar_conta, criar_perfil
from integration.studio_helpers import (
    CAB_OVERVIEW,
    DiaOverview,
    csv_bytes,
    csv_overview,
    data_en,
    err,
    overview_dias,
    seguidores_dias,
    semear_coleta,
    st,  # noqa: F401
    zip_bytes,
    zip_conteudo,
    zip_overview,
    zip_seguidores,
)
from sociman_api.redis import get_redis

H = "atavernanerd"


def _nada(st):  # noqa: F811
    assert st.contar() == (0, 0)
    assert list(get_redis().scan_iter("studio:previa:*")) == []


def _recusa(st, codigo, *arquivos, status=400):  # noqa: F811
    r = st.previa(*arquivos)
    assert (r.status_code, err(r)) == (status, codigo), r.text
    _nada(st)
    return r.json()["error"]


def _csv(linhas, cab=CAB_OVERVIEW):
    return ("Overview.csv", csv_bytes(cab, linhas))


def _dia(k: int) -> str:
    return data_en(local(k).date())


# ---- studio_formato ----

@pytest.mark.parametrize("cab", [("Video Views", "Likes"), ("Date", "Likes"),
                                 ("Datum", "Videovisningar")])
def test_formato_sem_coluna_obrigatoria(st, cab):  # noqa: F811
    e = _recusa(st, "studio_formato", _csv([("1", "2")], cab))
    assert e["details"]["encontradas"] == list(cab) and e["details"]["esperadas"]


def test_formato_vazio_e_codificacao(st):  # noqa: F811
    _recusa(st, "studio_formato", ("Overview.csv", b""))
    _recusa(st, "studio_formato", ("Overview.csv", csv_bytes(CAB_OVERVIEW, [])))
    e = _recusa(st, "studio_formato",
                ("Overview.csv", '"Date","Video Views"\n"Março 1","3"'.encode("latin-1")))
    assert e["details"]["motivo"] == "codificacao"


# ---- studio_invalido ----

def test_problemas_por_linha_com_arquivo_linha_coluna_e_valor(st):  # noqa: F811
    linhas = [(_dia(5), "-1", "0", "0", "0", "0"), (_dia(4), "1.2K", "0", "0", "0", "0"),
              (_dia(3), "12.5", "0", "0", "0", "0")]
    e = _recusa(st, "studio_invalido", _csv(linhas))
    problemas = e["details"]["problemas"]
    assert [(p["linha"], p["coluna"], p["valor"]) for p in problemas] == [
        (2, "Video Views", "-1"), (3, "Video Views", "1.2K"), (4, "Video Views", "12.5")]
    assert all(p["arquivo"] == "Overview.csv" for p in problemas) and e["details"]["total"] == 3
    # data futura (com ano explícito: sem ano, a dedução nunca passa de hoje)
    futuro = (hoje_sp() + timedelta(days=1)).isoformat()
    e = _recusa(st, "studio_invalido", _csv([(futuro, "1", "0", "0", "0", "0")]))
    assert e["details"]["problemas"][0]["motivo"].startswith("data futura")
    # pelo nome do ZIP, o fim no futuro também é recusado
    adiante = [DiaOverview(hoje_sp() + timedelta(days=k), 1) for k in (0, 1)]
    _recusa(st, "studio_invalido", zip_overview(adiante, H))


def test_dia_repetido_diferente_e_lista_ate_50(st):  # noqa: F811
    e = _recusa(st, "studio_invalido",
                _csv([(_dia(3), "1", "0", "0", "0", "0"), (_dia(3), "2", "0", "0", "0", "0")]))
    assert "dia repetido" in e["details"]["problemas"][0]["motivo"]
    muitas = [(_dia(k), "-1", "0", "0", "0", "0") for k in range(70, 1, -1)]
    e = _recusa(st, "studio_invalido", _csv(muitas))
    assert len(e["details"]["problemas"]) == 50 and e["details"]["total"] == 69


def test_data_invalida(st):  # noqa: F811
    e = _recusa(st, "studio_invalido", _csv([("Smarch 3", "1", "0", "0", "0", "0")]))
    assert e["details"]["problemas"][0]["motivo"] == "data inválida"


# ---- studio_datas ----

def test_fora_de_ordem_e_nome_que_nao_bate(st):  # noqa: F811
    e = _recusa(st, "studio_datas", _csv([(_dia(3), "1", "0", "0", "0", "0"),
                                          (_dia(5), "1", "0", "0", "0", "0")]))
    assert e["details"]["arquivo"] == "Overview.csv"
    linhas = overview_dias(local(1).date(), 3)
    nome = f"Overview_{linhas[1].dia}_1790891174_{H}.zip"
    e = _recusa(st, "studio_datas", (nome, zip_bytes({"Overview.csv": csv_overview(linhas)})))
    assert "nome do ZIP" in e["message"]


# ---- seções, ZIP e tamanho ----

@pytest.mark.parametrize("arquivo", [
    zip_conteudo(H),
    ("Viewers_atavernanerd.zip", zip_bytes({"Viewers.xlsx": b"PK"})),
    ("Viewers.xlsx", zip_bytes({"[Content_Types].xml": b"<x/>"})),
    ("planilha.xlsx", b"qualquer"),
    ("user_data.json", b'{"Profile": {}}'),
])
def test_secao_nao_importada(st, arquivo):  # noqa: F811
    e = _recusa(st, "studio_secao_nao_importada", arquivo)
    assert "Visão geral" in e["message"] and e["details"]["orientacao"]


@pytest.mark.parametrize("arquivo", [
    ("x.zip", zip_bytes({"../Overview.csv": b"1"})),
    ("x.zip", zip_bytes({f"f{i}.csv": b"" for i in range(21)})),
    ("x.zip", zip_bytes({"Overview.csv": b"1", "dentro.zip": b"PK"})),
])
def test_zip_inseguro(st, arquivo):  # noqa: F811
    e = _recusa(st, "studio_zip_inseguro", arquivo)
    assert e["details"]["arquivo"] == "x.zip" and e["details"]["motivo"]


def test_arquivo_grande(st):  # noqa: F811
    e = _recusa(st, "arquivo_grande", ("Overview.csv", b"1" * (5 * 1024 * 1024 + 1)),
                status=413)
    assert e["details"] == {"limiteBytes": 5 * 1024 * 1024}


def test_numero_de_arquivos_e_secao_repetida(st):  # noqa: F811
    r = st.client.post(f"/api/contas/{st.conta_id}/studio/previa", headers=st.h)
    assert (r.status_code, err(r)) == (400, "studio_arquivos")
    a = zip_overview(overview_dias(n=3), H)
    _recusa(st, "studio_arquivos", a, a, a)
    _recusa(st, "studio_arquivos", a, ("Overview.csv", csv_overview(overview_dias(n=3))))


# ---- conta e @ (T024) ----

def test_zip_de_outra_conta(st):  # noqa: F811
    e = _recusa(st, "studio_conta_diferente", zip_overview(overview_dias(n=3), "outraconta"))
    assert e["message"] == "O arquivo é de @outraconta, não de @atavernanerd."
    assert e["details"]["handleArquivo"] == "outraconta"
    _recusa(st, "studio_conta_diferente", zip_overview(overview_dias(n=3), H),
            zip_seguidores(seguidores_dias(n=3), "outraconta"))


def test_handle_com_caixa_diferente_passa(st):  # noqa: F811
    p = st.previa_ok(zip_overview(overview_dias(n=3), "AtavernaNerd"))
    assert p["exigeConfirmacaoConta"] is False


def test_csv_solto_exige_a_confirmacao(st):  # noqa: F811
    p = st.previa_ok(("Overview.csv", csv_overview(overview_dias(n=3))))
    assert p["exigeConfirmacaoConta"] is True and p["arquivos"][0]["handle"] is None
    r = st.confirmar(p["previaId"])
    assert (r.status_code, err(r)) == (400, "confirmar_conta")
    assert st.contar() == (0, 0)
    r = st.confirmar(p["previaId"], confirmo=True)  # a prévia não foi consumida
    assert r.status_code == 201, r.text


def test_serie_indisponivel(st):  # noqa: F811
    perfil = criar_perfil(st.client, st.h, "Sem série")
    sem = criar_conta(st.client, st.h, perfil["id"], "tiktok", "semserie")
    r = st.previa(zip_overview(overview_dias(n=3), "semserie"), conta_id=sem["id"])
    assert (r.status_code, err(r)) == (409, "serie_indisponivel")
    yt = criar_conta(st.client, st.h, st.perfil["id"], "youtube", H)
    r = st.previa(zip_overview(overview_dias(n=3), H), conta_id=yt["id"])
    assert (r.status_code, err(r)) == (409, "serie_indisponivel")
    _nada(st)


def test_serie_anonimizada_nao_aceita(st):  # noqa: F811
    from sociman_api.auth.deps import Actor
    from sociman_api.metricas import anonimizar
    from sociman_api.metricas.models import Serie

    serie = st.db.get(Serie, st.serie())
    anonimizar.serie(st.db, serie, Actor(kind="user", user_id=st.dono.id))
    st.db.commit()
    r = st.previa(zip_overview(overview_dias(n=3), H))
    assert (r.status_code, err(r)) == (409, "serie_indisponivel")


# ---- avisos (T025) ----

def test_avisos_que_nao_bloqueiam(st):  # noqa: F811
    serie = st.serie()
    semear_coleta(st.db, st.conta_id, local(4, 9), views_por_h=100, serie_id=serie)
    # D−3 e D−2 cobertos pela coleta com views bem diferentes das do arquivo
    linhas = [DiaOverview(local(k).date(), 1) for k in (5, 4, 3, 2)]
    linhas.append(DiaOverview(hoje_sp(), 7))
    p = st.previa_ok(("Overview.csv", csv_overview(linhas)))
    avisos = {a["codigo"]: a for a in p["avisos"]}
    assert {"diverge_da_coleta", "dia_incompleto", "ano_deduzido"} <= set(avisos)
    assert avisos["diverge_da_coleta"]["detalhes"]["diferencaPct"] > 0.30
    assert p["podeConfirmar"] is True
    pt = st.previa_ok(("Overview.csv", csv_overview(overview_dias(n=3), pt=True)))
    assert "cabecalho_provisorio" in {a["codigo"] for a in pt["avisos"]}
    assert _secao_amostra(pt)[0]["views"] == overview_dias(n=3)[0].views


def _secao_amostra(p):
    return p["secoes"][0]["amostra"]
