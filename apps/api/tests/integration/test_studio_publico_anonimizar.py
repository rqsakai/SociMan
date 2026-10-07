"""Anonimização com o público (spec 022, US5, T046; FR-019, R11): depois de `anonimizar.serie`, as
3 tabelas ficam intactas e sem nenhum texto com o @, `nomes_arquivos = NULL`, e a aba Público
mostra "Conta anônima N"."""

from sqlalchemy import select, text

from integration.analytics_helpers import cena, local  # noqa: F401
from integration.studio_helpers import (
    seguidores_dias,
    st,  # noqa: F401
    viewers_dias,
    zip_seguidores,
    zip_viewers,
)
from sociman_api.auth.deps import Actor
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import Serie
from sociman_api.metricas.studio.models import Importacao

H = "atavernanerd"
TABELAS = ("metricas_studio_distribuicoes", "metricas_studio_atividade",
           "metricas_studio_espectadores")


def _linhas(db) -> list[list[tuple]]:
    db.expire_all()
    return [[tuple(r) for r in db.execute(text(f"SELECT * FROM {t} ORDER BY id"))]
            for t in TABELAS]


def test_anonimizar_mantem_o_publico_sem_o_arroba(st):  # noqa: F811
    ate = local(1).date()
    st.importar(zip_seguidores(seguidores_dias(ate, 3), H, publico=True),
                zip_viewers(viewers_dias(ate), H))
    antes = _linhas(st.db)
    assert all(antes)
    serie = st.db.get(Serie, st.serie())
    anonimizar.serie(st.db, serie, Actor(kind="user", user_id=st.dono.id))
    st.db.commit()
    depois = _linhas(st.db)
    assert depois == antes
    assert H not in repr(depois)
    [imp] = st.db.scalars(select(Importacao)).all()
    assert imp.nomes_arquivos is None
    corpo = st.ok("publico", de=str(local(7).date()), ate=str(local(0).date()))
    [c] = [c for c in corpo["contas"] if c["conta"]["contaId"] is None]
    assert c["conta"]["rotulo"].startswith("Conta anônima")
    assert H not in repr(corpo)
