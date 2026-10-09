"""Valor efetivo do público (spec 022, T016; research R7): a ativa mais antiga vale por foto, por
(dia, hora) e por dia; a desfeita não vale e a próxima assume; a foto inteira não mistura rótulos;
a foto válida dentro, antes e sem foto; a comparação só com outra data; a regra "veio vazia"."""

from datetime import date, timedelta

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    csv_atividade,
    csv_genero,
    seguidores_dias,
    st,  # noqa: F401
    viewers_dias,
    zip_seguidores,
    zip_viewers,
)
from sociman_api.metricas.studio import efetivo

H = "atavernanerd"


def test_foto_inteira_da_mais_antiga_e_a_desfeita_sai(st):  # noqa: F811
    a = st.importar(("FollowerGender.csv", csv_genero()), confirmo=True)
    b = st.importar(("FollowerGender.csv", csv_genero((("Female", "50%"), ("Male", "49%"),
                                                        ("Other", "1%")))), confirmo=True)
    serie = st.serie()
    [foto] = efetivo.fotos(st.db, [serie], "genero")[serie]
    assert str(foto.importacao_id) == a["id"]
    assert foto.itens == {"feminino": 61.0, "masculino": 37.5, "outro": 1.5}
    st.desfazer(a)
    st.db.expire_all()
    [foto] = efetivo.fotos(st.db, [serie], "genero")[serie]
    assert str(foto.importacao_id) == b["id"] and foto.itens["feminino"] == 50.0


def test_atividade_e_espectadores_por_chave(st):  # noqa: F811
    d1, d2 = local(2).date(), local(1).date()
    a = st.importar(("FollowerActivity.csv", csv_atividade([d1], (5,))), confirmo=True)
    b = st.importar(("FollowerActivity.csv", csv_atividade([d1, d2], (5, 6))), confirmo=True)
    serie = st.serie()
    ef = efetivo.atividade(st.db, [serie])[serie]
    assert str(ef[(d1, 5)].importacao_id) == a["id"]
    assert str(ef[(d2, 6)].importacao_id) == b["id"]
    assert efetivo.ultimo_dia_atividade(st.db, [serie]) == {serie: d2}
    vw = viewers_dias(d2)
    c = st.importar(zip_viewers(vw[:4], H))
    st.importar(zip_viewers(vw, H))
    ev = efetivo.espectadores(st.db, [serie])[serie]
    assert str(ev[vw[0][0]].importacao_id) == c["id"] and len(ev) == 7
    assert len(efetivo.espectadores(st.db, [serie], vw[2][0], vw[3][0])[serie]) == 2


def _foto(d: date) -> efetivo.Foto:
    import uuid
    return efetivo.Foto("genero", d, uuid.uuid4(), {})


def test_foto_valida_e_comparacao():
    fotos = [_foto(date(2026, 9, 15)), _foto(date(2026, 10, 2))]
    assert efetivo.foto_valida(fotos, date(2026, 10, 5)) is fotos[1]  # dentro
    assert efetivo.foto_valida(fotos, date(2026, 9, 30)) is fotos[0]  # anterior ao período
    assert efetivo.foto_valida(fotos, date(2026, 9, 1)) is None  # sem foto
    valida = efetivo.foto_valida(fotos, date(2026, 10, 5))
    assert efetivo.comparacao(fotos, date(2026, 10, 1), valida) is fotos[0]
    # a válida no fim do anterior é a mesma data: sem comparação
    assert efetivo.comparacao(fotos, date(2026, 10, 4), valida) is None


def test_veio_vazia(st):  # noqa: F811
    serie = st.serie()
    e = efetivo.vazias(st.db, [serie])[serie]
    assert e["genero"].sem_importacao and not e["genero"].veio_vazia
    st.importar(("FollowerGender.csv", csv_genero()), confirmo=True)
    st.importar(zip_seguidores(seguidores_dias(local(1).date(), 3), H))  # as 3 vazias
    e = efetivo.vazias(st.db, [serie])[serie]
    assert e["genero"].veio_vazia and e["atividade"].veio_vazia
    assert not e["espectadores"].veio_vazia and e["espectadores"].sem_importacao
    st.importar(("FollowerGender.csv", csv_genero((("Female", "50%"), ("Male", "50%")))),
                confirmo=True)
    e = efetivo.vazias(st.db, [serie])[serie]
    assert not e["genero"].veio_vazia  # a última com dado é mais nova que a vazia
    assert e["territorios"].veio_vazia
    assert (local(0).date() - timedelta(days=0)) is not None
