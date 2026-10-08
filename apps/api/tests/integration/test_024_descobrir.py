"""Tema e motivo no Descobrir (spec 024, US4, T031; FR-015 a FR-017; research R9): os temas
casados de cada vídeo (o decisivo primeiro), o estado da afinidade da lista e a soma das parcelas
do "Por quê?" (as 4 da 006, × 0,3 de já cortado e a afinidade) igual ao `score` (± 1)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from integration.analytics_helpers import cena  # noqa: F401
from integration.aprendizado_helpers import ap, canal_do_perfil  # noqa: F401
from sociman_api.canais.models import VideoFonte
from sociman_api.canais.score import FATOR_JA_CORTADO, PESOS

# (título, notas v/e/r/d da 006)
VIDEOS = (("Marvel e os games da semana", (0.9, 0.5, 0.4, 0.8)),
          ("Vingadores: a cena pós-créditos", (0.7, 0.6, 0.3, 0.5)),
          ("Receita de bolo", (0.5, 0.2, 0.9, 0.1)),
          ("Jogo de tabuleiro", (0.2, 0.3, 0.2, 0.9)))


def _videos(ap, canal):  # noqa: F811
    out = {}
    for titulo, notas in VIDEOS:
        detalhe = dict(zip(("v", "e", "r", "d"), notas, strict=True))
        score = sum(100 * PESOS[k] * n for k, n in detalhe.items())
        v = VideoFonte(canal_id=canal.id, youtube_video_id=uuid.uuid4().hex[:11], title=titulo,
                       description="", published_at=datetime.now(UTC) - timedelta(days=1),
                       duration_s=600, next_metrics_at=datetime.now(UTC) + timedelta(hours=1),
                       score=Decimal(str(round(score, 1))), score_reason="Recente",
                       score_detail={**detalhe, "componente": "v"}, recomendavel=True,
                       views=1000, vph_recente=Decimal(10))
        ap.db.add(v)
        out[titulo] = v
    ap.db.commit()
    return out


def _lista(ap, **params) -> dict:  # noqa: F811
    r = ap.client.get("/api/videos-fonte", headers=ap.h,
                      params={"perfilId": ap.perfil_id, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _prefs(ap, **temas):  # noqa: F811
    v = ap.get("preferencias")["perfil"]["version"]
    r = ap.client.patch(f"{ap.url}/preferencias", headers=ap.h, json={
        "version": v, "temas": {ap.temas[n]["id"]: p for n, p in temas.items() if p}})
    assert r.status_code == 200, r.text


def _por(lista) -> dict[str, dict]:
    return {i["title"]: i for i in lista["items"]}


def _soma(item, perfil_id) -> float:
    """A composição do diálogo "Por quê?" (R9)."""
    d = item["scoreDetail"]
    base = sum(100 * peso * float(d[k]) for k, peso in PESOS.items())
    if any(j["perfilId"] == perfil_id for j in item["jaCortado"]):
        base *= float(FATOR_JA_CORTADO)
    pontos = item["afinidade"]["pontos"] if item["afinidade"] else 0
    return max(0.0, min(100.0, base + pontos))


def test_estado_sem_temas_desatualizada_e_neutra(ap):  # noqa: F811
    canal = canal_do_perfil(ap)
    _videos(ap, canal)
    sem = _lista(ap)
    assert sem["afinidadeEstado"] == {"ativa": False, "motivo": "sem_temas"}
    assert all(i["afinidade"] is None for i in sem["items"])

    ap.tema("Marvel", ["marvel", "vingadores"])
    _prefs(ap, Marvel="ampliar")
    assert _lista(ap)["afinidadeEstado"] == {"ativa": False, "motivo": "desatualizada"}

    ap.casar()
    _prefs(ap, Marvel=None)
    neutra = _lista(ap)
    assert neutra["afinidadeEstado"] == {"ativa": False, "motivo": "neutra"}
    assert neutra["items"] == sem["items"]  # FR-043: a 006 fica igual

    r = ap.client.get("/api/videos-fonte", headers=ap.h)
    assert r.status_code == 200 and r.json()["afinidadeEstado"] == {
        "ativa": False, "motivo": "sem_perfil"}


def test_temas_casados_decisivo_primeiro(ap):  # noqa: F811
    canal = canal_do_perfil(ap)
    _videos(ap, canal)
    marvel = ap.tema("Marvel", ["marvel", "vingadores"])
    games = ap.tema("Games", ["games", "jogo"])
    ap.casar()
    _prefs(ap, Marvel="ampliar")
    lista = _lista(ap)
    assert lista["afinidadeEstado"] == {"ativa": True, "motivo": None}
    por = _por(lista)

    dois = por["Marvel e os games da semana"]["afinidade"]
    # `ampliar` sem efeito estatístico: a = 0,5 → 10 pontos isolados; Games sem efeito: 0
    assert dois["temas"] == [
        {"temaId": marvel["id"], "nome": "Marvel", "pontos": 10.0, "acao": "ampliar",
         "decisivo": True},
        {"temaId": games["id"], "nome": "Games", "pontos": 0.0, "acao": None,
         "decisivo": False}]
    assert dois["temaId"] == marvel["id"]
    um = por["Jogo de tabuleiro"]["afinidade"]
    assert um["temas"] == [{"temaId": games["id"], "nome": "Games", "pontos": 0.0,
                            "acao": None, "decisivo": False}]
    assert por["Receita de bolo"]["afinidade"]["temas"] == []

    # `cortar` vence como decisivo (mesmo critério do `_ordem`)
    _prefs(ap, Marvel="ampliar", Games="cortar")
    por = _por(_lista(ap, mostrarCortados="true"))
    dois = por["Marvel e os games da semana"]["afinidade"]
    assert [(t["nome"], t["pontos"], t["acao"], t["decisivo"]) for t in dois["temas"]] == [
        ("Games", -20.0, "cortar", True), ("Marvel", 10.0, "ampliar", False)]
    assert dois["temaId"] == games["id"] and dois["cortado"] is True


def test_soma_das_parcelas_bate_com_o_score(ap):  # noqa: F811
    canal = canal_do_perfil(ap)
    videos = _videos(ap, canal)
    envio = ap.c.envio(ap.perfil_id, canal=canal)
    envio.video_fonte_id = videos["Vingadores: a cena pós-créditos"].id  # já cortado: × 0,3
    ap.db.commit()
    ap.tema("Marvel", ["marvel", "vingadores"])
    ap.tema("Games", ["games", "jogo"])
    ap.casar()
    _prefs(ap, Marvel="ampliar", Games="cortar")
    lista = _lista(ap, mostrarCortados="true")
    assert len(lista["items"]) == len(VIDEOS)
    por = _por(lista)
    assert por["Vingadores: a cena pós-créditos"]["jaCortado"]
    assert por["Vingadores: a cena pós-créditos"]["afinidade"]["pontos"] != 0
    for item in lista["items"]:
        assert abs(_soma(item, ap.perfil_id) - item["score"]) <= 1, item["title"]
