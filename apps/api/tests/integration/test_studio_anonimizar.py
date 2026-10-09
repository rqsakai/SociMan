"""Anonimização com o Studio (spec 020, US5, T042; research R9): anonimizar a série apaga os
`nomes_arquivos` (têm o @), os dias ficam intactos (o trigger não dispara: não há UPDATE neles),
nenhum @ nas versões `studio_importacao`, `details.importacoes` na anonimização e a série nova
(reconectar) recebe as importações seguintes sem conflito com a anônima."""

import json

from sqlalchemy import select, text

from integration.analytics_helpers import cena  # noqa: F401
from integration.studio_helpers import (
    overview_dias,
    st,  # noqa: F401
    zip_overview,
)
from sociman_api.auth.deps import Actor
from sociman_api.history import EntityVersion
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import Serie
from sociman_api.metricas.studio.models import Importacao

H = "atavernanerd"


def _dias(db) -> list[tuple]:
    db.expire_all()
    return [tuple(r) for r in db.execute(text(
        "SELECT id, importacao_id, serie_id, dia, views, likes FROM metricas_studio_dias "
        "ORDER BY id"))]


def test_anonimizar_apaga_os_nomes_e_mantem_os_dias(st):  # noqa: F811
    arquivo = zip_overview(overview_dias(n=4), H)
    imp = st.importar(arquivo)
    assert imp["nomesArquivos"] == [arquivo[0]]
    dias = _dias(st.db)
    serie = st.db.get(Serie, st.serie())
    anonimizar.serie(st.db, serie, Actor(kind="user", user_id=st.dono.id))
    assert anonimizar.importacoes(st.db, serie.id) == 1
    st.db.commit()
    st.db.expire_all()
    [i] = st.db.scalars(select(Importacao)).all()
    assert i.nomes_arquivos is None and i.estado.value == "ativa"
    assert _dias(st.db) == dias
    versoes = st.db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "studio_importacao")).all()
    bruto = json.dumps([[v.before, v.after, v.details] for v in versoes])
    assert H not in bruto and ".zip" not in bruto
    # a lista da conta não mostra mais a importação da série anônima
    assert st.importacoes() == []
    # a série nova (reconectar) aceita o mesmo arquivo sem conflito com a anônima
    st.serie()
    p = st.previa_ok(arquivo)
    assert p["secoes"][0]["jaImportada"] is None and p["podeConfirmar"] is True
