"""Análise da IA dos melhores (spec 023, T033; FR-030 a FR-033, Clarification 1): estimativa
sem chamada, `confirmar_custo`, execução sem e com quadros (MP4 sintético), vídeo sem arquivo
contado, HD fora → `hd_indisponivel`, hipótese com id de fora recusada, pasta temporária vazia
no fim, e o membro sem custo e sem pedir."""

import subprocess
import uuid
from pathlib import Path

from fakes.anthropic_fake import ID_INVALIDO, analise, anthropic_fake  # noqa: F401

from integration.analytics_helpers import agora, cena  # noqa: F401
from integration.aprendizado_helpers import (  # noqa: F401
    ap,
    err,
    estagnados,
    fake,
    membro,
    semear_aprendizado,
)
from integration.postagem_helpers import criar_corte
from sociman_api import storage
from sociman_api.aprendizado import analise_ia, quadros
from sociman_api.aprendizado.models import Analise, AnaliseEstado
from sociman_api.errors import ApiError
from sociman_api.ia.models import IaChamada


def _mp4(destino: Path) -> bytes:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=duration=6:size=320x568:rate=10", "-pix_fmt", "yuv420p",
                    str(destino)], check=True, timeout=60)
    return destino.read_bytes()


def _com_arquivo(ap, vid, tmp_path) -> None:  # noqa: F811
    corte = criar_corte(ap.db, ap.perfil_id, transcript="fala do corte", hook_text="Olha só")
    storage.ensure_buckets()
    storage.put(corte.result_key, _mp4(tmp_path / f"{vid}.mp4"), "video/mp4", bucket="videos")
    ap.c.vincular(vid, corte=corte)


def _pedir(ap, h=None, status=202, **body):  # noqa: F811
    corpo = {"n": 3, "medida": "h24", "comQuadros": False, "confirmoCusto": True} | body
    r = ap.client.post(f"{ap.url}/analises", headers=h or ap.h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def _rodar(ap, fake) -> Analise:  # noqa: F811
    assert analise_ia.processar_uma(ap.db, fake.ia_client(), agora())
    ap.db.expire_all()
    return ap.db.query(Analise).one()


def test_estimativa_sem_chamada_e_confirmar_custo(ap, fake, estagnados):  # noqa: F811
    semear_aprendizado(ap, conta_b=False)
    r = ap.client.post(f"{ap.url}/analises/estimativa", headers=ap.h, json={"n": 3})
    assert r.status_code == 200, r.text
    est = r.json()
    assert len(est["melhores"]) == 3 and len(est["comparaveis"]) == 3
    assert est["semArquivo"] == 6 and est["custoComQuadrosUsd"] == est["custoSemQuadrosUsd"] > 0
    assert fake.requests == []
    erro = _pedir(ap, status=409, confirmoCusto=False)
    assert erro["error"]["code"] == "confirmar_custo"
    assert erro["error"]["details"]["custoSemQuadrosUsd"] > 0
    assert ap.db.query(Analise).count() == 0


def test_execucao_sem_quadros_ate_pronta(ap, fake, estagnados):  # noqa: F811
    semear_aprendizado(ap, conta_b=False)
    pedido = _pedir(ap)
    assert pedido["estado"] == "pendente" and pedido["custoEstimadoUsd"] > 0
    assert _pedir(ap, status=409)["error"]["code"] == "analise_em_andamento"
    a = _rodar(ap, fake)
    assert a.estado == AnaliseEstado.pronta and a.hipoteses and a.chamada_id
    assert all(h["grau"] == "a_conferir" for h in a.hipoteses)
    enviados = {str(i) for i in [*a.melhores, *a.comparaveis]}
    assert all(set(h["postsIds"]) <= enviados for h in a.hipoteses)
    assert fake.imagens == [0] and a.videos_sem_arquivo == 6
    texto = fake.bodies[0]["messages"][0]["content"]
    assert "<resumo_estatistico>" in texto and 'Grupo: melhor' in texto
    chamada = ap.db.get(IaChamada, a.chamada_id)
    assert chamada.tipo_campo == "aprendizado.analise" and chamada.created_by is None
    got = ap.client.get(f"/api/aprendizado/analises/{a.id}", headers=ap.h).json()
    assert got["estado"] == "pronta" and got["custoUsd"] is not None


def test_execucao_com_quadros_e_pasta_vazia(ap, fake, estagnados, tmp_path):  # noqa: F811
    semear_aprendizado(ap, conta_b=False)
    melhores = analise_ia.escolher(ap.db, uuid.UUID(ap.perfil_id), None, 3, "h24").melhores
    for p in melhores[:2]:
        _com_arquivo(ap, p.p.video_id, tmp_path)
    r = ap.client.post(f"{ap.url}/analises/estimativa", headers=ap.h, json={"n": 3}).json()
    assert r["semArquivo"] == 4 and r["custoComQuadrosUsd"] > r["custoSemQuadrosUsd"]
    _pedir(ap, comQuadros=True)
    a = _rodar(ap, fake)
    assert a.estado == AnaliseEstado.pronta, a.erro_code
    assert fake.imagens == [8] and a.videos_sem_arquivo == 4 and a.quadros_por_video == 4
    assert not quadros.pasta(a.id).exists()


def test_hd_fora_vira_hd_indisponivel(ap, fake, estagnados, monkeypatch):  # noqa: F811
    semear_aprendizado(ap, conta_b=False)

    def fora(*a, **k):
        raise ApiError(503, "storage_unavailable", "fora")

    monkeypatch.setattr(quadros.datadir, "ensure_writable", fora)
    _pedir(ap, comQuadros=True)
    a = _rodar(ap, fake)
    assert a.estado == AnaliseEstado.erro and a.erro_code == "hd_indisponivel"
    assert fake.requests == []


def test_hipotese_com_post_de_fora_recusada(ap, fake, estagnados):  # noqa: F811
    semear_aprendizado(ap, conta_b=False)
    _pedir(ap)
    a = ap.db.query(Analise).one()
    valido = str(a.melhores[0])
    fake.responder(analise(("Cita post de fora", [ID_INVALIDO]), ("Boa hipótese", [valido])))
    a = _rodar(ap, fake)
    assert [h["texto"] for h in a.hipoteses] == ["Boa hipótese"]
    assert any("fora do conjunto" in x for x in ap.db.get(IaChamada, a.chamada_id).avisos)


def test_todas_de_fora_vira_erro(ap, fake, estagnados):  # noqa: F811
    semear_aprendizado(ap, conta_b=False)
    _pedir(ap)
    fake.responder(analise(("Só de fora", [ID_INVALIDO])))
    a = _rodar(ap, fake)
    assert a.estado == AnaliseEstado.erro and a.erro_code == "ia_invalida"


def test_membro_ve_sem_custo_e_nao_pede(ap, fake, estagnados, membro):  # noqa: F811
    semear_aprendizado(ap, conta_b=False)
    _pedir(ap)
    _rodar(ap, fake)
    _, hm = membro
    assert _pedir(ap, h=hm, status=403)["error"]["code"] == "somente_dono"
    r = ap.client.post(f"{ap.url}/analises/estimativa", headers=hm, json={"n": 3})
    assert r.status_code == 403
    [item] = ap.get("analises", h=hm)["items"]
    assert item["custoUsd"] is None and item["custoEstimadoUsd"] is None
    assert item["hipoteses"]
    [dono] = ap.get("analises")["items"]
    assert dono["custoUsd"] is not None


def test_sem_chave_503_e_sem_posts_409(ap, estagnados):  # noqa: F811
    from sociman_api.ia.cliente import get_ia_client
    from sociman_api.main import app

    r = ap.client.post(f"{ap.url}/analises/estimativa", headers=ap.h, json={"n": 3})
    assert r.status_code == 409 and err(r) == "sem_posts"
    app.dependency_overrides[get_ia_client] = lambda: None
    semear_aprendizado(ap, conta_b=False)
    assert _pedir(ap, status=503)["error"]["code"] == "claude_unconfigured"


def test_hipotese_vira_recomendacao_aberta(ap, fake, estagnados):  # noqa: F811
    semear_aprendizado(ap, conta_b=False)
    _pedir(ap)
    a = _rodar(ap, fake)
    url = f"/api/aprendizado/analises/{a.id}/hipoteses/0/recomendar"
    r = ap.client.post(url, headers=ap.h,
                       json={"tipo": "padrao_gancho", "texto": "Abrir com uma pergunta"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["estado"] == "aberta" and d["origem"] == "hipotese" and d["analiseId"] == str(a.id)
    r = ap.client.post(url, headers=ap.h, json={"tipo": "padrao_gancho", "texto": "De novo"})
    assert r.status_code == 409
    abertas = ap.get("recomendacoes")["abertas"]
    hip = [x for x in abertas if x["origem"] == "hipotese"]
    assert hip and hip[0]["decisaoId"] == d["id"] and hip[0]["alvo"]["padrao"] == (
        "Abrir com uma pergunta")
    assert err(ap.client.post(f"/api/aprendizado/analises/{a.id}/hipoteses/9/recomendar",
                              headers=ap.h, json={"tipo": "padrao_gancho", "texto": "x"})
               ) == "not_found"
