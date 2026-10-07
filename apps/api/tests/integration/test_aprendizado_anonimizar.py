"""Anonimização (spec 023, T062; R11): justificativa, sugestão e nota ficam NULL; as hipóteses
que usaram a série são trocadas; tema e estilo ficam; a série anônima não entra na análise nem
vira exemplo."""

import uuid

from sqlalchemy import select

from integration.analytics_helpers import cena  # noqa: F401
from integration.aprendizado_helpers import ap, estagnados  # noqa: F401
from sociman_api.aprendizado import analise, desempenho
from sociman_api.aprendizado.anonimizar import REMOVIDO
from sociman_api.aprendizado.models import (
    Analise,
    AnaliseEstado,
    Classificacao,
    Conferencia,
    ConferenciaResultado,
)
from sociman_api.auth.deps import Actor
from sociman_api.metricas import anonimizar
from sociman_api.metricas.models import Serie


def test_textos_saem_e_o_categorico_fica(ap, estagnados):  # noqa: F811
    ap.tema("Marvel")
    ids = [ap.post(dias=d, views=1000 + d) for d in range(2, 20)]
    vid = ids[0]
    ap.classificar(vid, "Marvel")
    c = ap.db.scalar(select(Classificacao).where(Classificacao.video_id == vid))
    c.justificativa, c.sugestao_tema = "Fala da Marvel", "MCU"
    ap.db.add(Conferencia(video_id=vid, item="restrito", resultado=ConferenciaResultado.ok,
                          nota="Conferi no app"))
    a = Analise(perfil_id=uuid.UUID(ap.perfil_id), estado=AnaliseEstado.pronta, medida="h24",
                n=1, com_quadros=False, melhores=[vid], comparaveis=[], resumo_estatistico=[],
                hipoteses=[{"texto": "A legenda X", "postsIds": [str(vid)], "contraste": "Y",
                            "n": 1, "grau": "a_conferir"}], custo_estimado_usd=0,
                taxonomia_versao=1, pedido_por=ap.c.dono.id)
    ap.db.add(a)
    ap.db.commit()
    perfil = uuid.UUID(ap.perfil_id)
    assert analise.calcular(ap.db, perfil).medidos
    serie = ap.db.scalar(select(Serie).where(Serie.conta_id == uuid.UUID(ap.c.conta["id"])))
    anonimizar.serie(ap.db, serie, Actor(kind="user", user_id=ap.c.dono.id))
    ap.db.commit()
    ap.db.expire_all()
    c = ap.db.scalar(select(Classificacao).where(Classificacao.video_id == vid))
    assert c.justificativa is None and c.sugestao_tema is None
    assert c.tema_id is not None and c.estilo_gancho is not None
    conf = ap.db.scalar(select(Conferencia))
    assert conf.nota is None and conf.resultado == ConferenciaResultado.ok
    [h] = ap.db.get(Analise, a.id).hipoteses
    assert h["texto"] == REMOVIDO and h["contraste"] == REMOVIDO and h["postsIds"] == [str(vid)]
    assert analise.calcular(ap.db, perfil).medidos == []
    assert desempenho.exemplos(ap.db, perfil, None, ()) == []
