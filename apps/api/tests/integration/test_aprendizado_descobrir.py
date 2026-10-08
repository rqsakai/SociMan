"""Afinidade no Descobrir e no Mercado (spec 023, T047; SC-008; FR-040 a FR-043): neutra = a
ordem da 006; tema ampliado sobe; tema cortado oculto, com o contador e o filtro; paginação por
cursor estável; o `enviar` de um vídeo `sem_acordo` continua com o aviso de direito."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from integration.analytics_helpers import cena  # noqa: F401
from integration.aprendizado_helpers import ap, canal_do_perfil, estagnados  # noqa: F401
from sociman_api.canais.models import CanalDireito, CanalFonte, VideoFonte

TITULOS = (("Vingadores: a cena pós-créditos", "80.0"), ("Gameplay de games antigos", "75.0"),
           ("Receita de bolo", "70.0"), ("Unboxing da semana", "65.0"),
           ("Marvel e o multiverso", "60.0"), ("Jogo de tabuleiro", "35.0"))


def _videos(ap, canal):  # noqa: F811
    out = {}
    for titulo, score in TITULOS:
        v = VideoFonte(canal_id=canal.id, youtube_video_id=uuid.uuid4().hex[:11], title=titulo,
                       description="", published_at=datetime.now(UTC) - timedelta(days=1),
                       duration_s=600, next_metrics_at=datetime.now(UTC) + timedelta(hours=1),
                       score=Decimal(score), score_reason="Recente", recomendavel=True,
                       views=1000, vph_recente=Decimal(score))
        ap.db.add(v)
        out[titulo] = v
    ap.db.commit()
    return out


def _lista(ap, **params) -> dict:  # noqa: F811
    r = ap.client.get("/api/videos-fonte", headers=ap.h,
                      params={"perfilId": ap.perfil_id, **params})
    assert r.status_code == 200, r.text
    out = r.json()
    out.pop("afinidadeEstado")  # spec 024: o motivo da neutra muda (test_024_descobrir.py)
    return out


def _titulos(lista) -> list[str]:
    return [i["title"] for i in lista["items"]]


def _prefs(ap, **temas):  # noqa: F811
    v = ap.get("preferencias")["perfil"]["version"]
    r = ap.client.patch(f"{ap.url}/preferencias", headers=ap.h, json={
        "version": v, "temas": {ap.temas[n]["id"]: p for n, p in temas.items() if p}})
    assert r.status_code == 200, r.text


def test_neutra_igual_a_006_e_ampliar_sobe(ap):  # noqa: F811
    canal = canal_do_perfil(ap)
    _videos(ap, canal)
    antes = _lista(ap)
    assert _titulos(antes)[0] == "Vingadores: a cena pós-créditos"
    ap.tema("Marvel", ["marvel", "vingadores"])
    ap.tema("Games", ["games", "jogo"])
    _prefs(ap, Marvel="ampliar")
    assert _lista(ap) == antes  # ainda não casado com a taxonomia: neutra
    ap.casar()
    _prefs(ap, Marvel=None)
    neutra = _lista(ap)  # temas sem efeito e sem preferência: nada muda
    assert neutra == antes and all(i["afinidade"] is None for i in neutra["items"])

    _prefs(ap, Marvel="ampliar")
    depois = _lista(ap)
    por = {i["title"]: i for i in depois["items"]}
    multi = por["Marvel e o multiverso"]
    # R9: `ampliar` sem efeito estatístico = a 0,5 → 0,7 × 0,5 × 20 = 7 pontos (abaixo dos 10
    # que trocam o motivo)
    assert multi["afinidade"]["temaNome"] == "Marvel" and multi["afinidade"]["pontos"] == 7
    assert multi["score"] == 67.0 and multi["afinidade"]["motivo"] is None
    assert por["Receita de bolo"]["afinidade"]["pontos"] == 0
    assert por["Receita de bolo"]["scoreReason"] == "Recente"
    assert _titulos(depois).index("Marvel e o multiverso") < _titulos(antes).index(
        "Marvel e o multiverso")
    assert _lista(ap, ordem="data")["total"] == depois["total"]
    r = ap.client.get("/api/videos-fonte", headers=ap.h)  # sem perfil: nada muda
    assert all(i["afinidade"] is None for i in r.json()["items"])


def test_cortado_oculto_contador_filtro_e_cursor(ap):  # noqa: F811
    canal = canal_do_perfil(ap)
    _videos(ap, canal)
    ap.tema("Marvel", ["marvel", "vingadores"])
    ap.tema("Games", ["games", "jogo"])
    ap.casar()
    _prefs(ap, Games="cortar", Marvel="ampliar")
    lista = _lista(ap)
    assert "Gameplay de games antigos" not in _titulos(lista)
    assert "Jogo de tabuleiro" not in _titulos(lista)
    assert lista["ocultosPorTema"] == 2 and lista["total"] == 4
    todos = _lista(ap, mostrarCortados="true")
    cortados = [i for i in todos["items"] if i["afinidade"]["cortado"]]
    assert {i["title"] for i in cortados} == {"Gameplay de games antigos", "Jogo de tabuleiro"}
    assert all(i["afinidade"]["pontos"] == -14 for i in cortados)
    # a busca por texto também respeita o filtro
    assert _lista(ap, q="games")["items"] == []
    # cursor: página a página dá a mesma ordem
    paginas, cursor = [], None
    while True:
        params = {"limit": 1, "mostrarCortados": "true"} | ({"cursor": cursor} if cursor else {})
        p = _lista(ap, **params)
        paginas += _titulos(p)
        cursor = p["nextCursor"]
        if not cursor:
            break
    assert paginas == _titulos(todos)


def test_sem_acordo_com_afinidade_continua_com_aviso(ap):  # noqa: F811
    canal = canal_do_perfil(ap, CanalDireito.sem_acordo)
    videos = _videos(ap, canal)
    ap.tema("Marvel", ["marvel", "vingadores"])
    ap.casar()
    _prefs(ap, Marvel="ampliar")
    alvo = videos["Vingadores: a cena pós-créditos"]
    item = next(i for i in _lista(ap)["items"] if i["id"] == str(alvo.id))
    assert item["afinidade"]["pontos"] > 0 and item["canal"]["direito"] == "sem_acordo"
    r = ap.client.post(f"/api/perfis/{ap.perfil_id}/envios", headers=ap.h,
                       json={"videoFonteId": str(alvo.id)})
    assert r.status_code == 201, r.text
    envio = r.json()["envio"]
    r = ap.client.post("/api/envios/enviar", headers=ap.h, json={
        "items": [{"envioId": envio["id"], "version": envio["version"]}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "aviso_direito"
    ap.db.expire_all()
    assert ap.db.get(CanalFonte, canal.id).direito == CanalDireito.sem_acordo


def test_oportunidades_do_mercado(ap):  # noqa: F811
    canal = canal_do_perfil(ap)
    _videos(ap, canal)
    params = {"perfilId": ap.perfil_id}
    antes = ap.client.get("/api/analytics/mercado", headers=ap.h, params=params).json()
    assert all(o["afinidade"] is None for o in antes["oportunidades"])
    ap.tema("Games", ["games", "jogo"])
    ap.tema("Marvel", ["marvel", "vingadores"])
    ap.casar()
    _prefs(ap, Games="cortar")
    depois = ap.client.get("/api/analytics/mercado", headers=ap.h, params=params).json()
    titulos = {o["tituloCurto"] for o in depois["oportunidades"]}
    assert "Jogo de tabuleiro" not in titulos and depois["ocultosPorTema"] == 2
    com = ap.client.get("/api/analytics/mercado", headers=ap.h,
                        params=params | {"mostrarCortados": "true"}).json()
    assert len(com["oportunidades"]) == len(antes["oportunidades"])
    sem_perfil = ap.client.get("/api/analytics/mercado", headers=ap.h).json()
    assert all(o["afinidade"] is None for o in sem_perfil["oportunidades"])


def test_arquivar_tema_limpa_o_casamento(ap):  # noqa: F811
    from sqlalchemy import func, select

    from sociman_api.aprendizado.fonte_temas import FonteTema

    canal = canal_do_perfil(ap)
    _videos(ap, canal)
    t = ap.tema("Games", ["games", "jogo"])
    ap.casar()
    assert ap.db.scalar(select(func.count()).select_from(FonteTema)) == 2
    ap.casar()  # idempotente
    assert ap.db.scalar(select(func.count()).select_from(FonteTema)) == 2
    r = ap.client.post(f"/api/aprendizado/temas/{t['id']}/archive", headers=ap.h,
                       json={"version": 1})
    assert r.status_code == 200
    ap.db.expire_all()
    assert ap.db.scalar(select(func.count()).select_from(FonteTema)) == 0
