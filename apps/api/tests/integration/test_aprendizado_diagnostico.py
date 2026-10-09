"""Diagnóstico de distribuição (spec 023, T055; FR-048 a FR-050): conta nova com 8 posts num
dia, repostagem entre contas, sinal que some quando a condição deixa de valer, conferência com
histórico e nada criado em destinos nem em notificações."""

from datetime import timedelta

from sqlalchemy import func, select, update

from integration.analytics_helpers import cena, hoje_sp, local  # noqa: F401
from integration.aprendizado_helpers import ap, err, estagnados, membro  # noqa: F401
from sociman_api.envios.models import Envio
from sociman_api.history import EntityVersion
from sociman_api.notificacoes.models import Notificacao
from sociman_api.postagem.models import Postagem


def _contar(db) -> tuple[int, int]:
    db.expire_all()
    return (db.scalar(select(func.count()).select_from(Postagem)),
            db.scalar(select(func.count()).select_from(Notificacao)))


def _sinais(diag, conta_id) -> list[dict]:
    return next(c for c in diag["contas"] if c["conta"]["id"] == conta_id)["sinais"]


def test_conta_nova_muitos_no_dia_e_post_curto(ap, estagnados):  # noqa: F811
    conta = ap.c.conta["id"]
    ids = [ap.post(publicado=local(3, 8 + i), duracao=5 if i == 0 else 30,
                   legenda="" if i == 1 else "Post " + " ".join(f"#h{k}" for k in range(9 * (i == 2))))
           for i in range(8)]
    antes = _contar(ap.db)
    diag = ap.get("diagnostico")
    sinais = _sinais(diag, conta)
    tipos = {s["tipo"] for s in sinais}
    assert {"conta_nova", "muitos_no_dia", "curto", "legenda_vazia", "hashtags_demais"} <= tipos
    nova = next(s for s in sinais if s["tipo"] == "conta_nova")
    assert nova["alvo"] == "conta" and nova["numero"] == 8
    muitos = [s for s in sinais if s["tipo"] == "muitos_no_dia"]
    assert len(muitos) == 8 and muitos[0]["numero"] == 8
    assert next(s for s in sinais if s["tipo"] == "curto")["alvoId"] == str(ids[0])
    assert diag["checklist"][0]["item"] == "restrito"
    # a condição deixa de valer (outro período): o sinal some, sem nada gravado
    sem = ap.get("diagnostico", de=str(hoje_sp() - timedelta(days=1)), ate=str(hoje_sp()))
    assert not [s for s in _sinais(sem, conta) if s["tipo"] == "muitos_no_dia"]
    assert _contar(ap.db) == antes


def test_repostagem_entre_contas(ap, estagnados):  # noqa: F811
    b = ap.c.segunda_conta(platform="youtube")
    canal = ap.c.canal()
    va, vb = ap.post(dias=3), ap.post(b, dias=2)
    ap.c.vincular(va, canal=canal)
    ap.c.vincular(vb, canal=canal)
    fonte = ap.db.scalars(select(Envio.video_fonte_id)).first()  # o mesmo vídeo-fonte nas duas
    ap.db.execute(update(Envio).values(video_fonte_id=fonte))
    ap.db.commit()
    diag = ap.get("diagnostico")
    rep = [s for s in _sinais(diag, b["id"]) if s["tipo"] == "repostagem"]
    assert rep and rep[0]["alvoId"] == str(vb) and rep[0]["numero"] == 1
    post = ap.client.get(f"/api/aprendizado/posts/{vb}/diagnostico", headers=ap.h).json()
    assert "repostagem" in {s["tipo"] for s in post["sinais"]}
    assert len(post["conferencias"]) == 6 and post["conferencias"][0]["version"] == 0


def test_conferencia_com_historico(ap, estagnados, membro):  # noqa: F811
    vid = ap.post(dias=3)
    url = f"/api/aprendizado/posts/{vid}/conferencias/restrito"
    r = ap.client.put(url, headers=ap.h, json={"version": 0, "resultado": "ok",
                                               "nota": "Não estava restrito"})
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "ok" and r.json()["version"] == 1
    r = ap.client.put(url, headers=ap.h, json={"version": 0, "resultado": "problema"})
    assert r.status_code == 409 and err(r) == "version_conflict"
    r = ap.client.put(url, headers=ap.h, json={"version": 1, "resultado": "problema"})
    assert r.status_code == 200 and r.json()["version"] == 2
    vs = ap.db.scalars(select(EntityVersion).where(
        EntityVersion.entity_type == "aprendizado_conferencia")
        .order_by(EntityVersion.version)).all()
    assert [v.action for v in vs] == ["created", "updated"]
    assert vs[1].before["resultado"] == "ok" and vs[1].after["resultado"] == "problema"
    r = ap.client.put(f"/api/aprendizado/posts/{vid}/conferencias/outro", headers=ap.h,
                      json={"version": 0, "resultado": "ok"})
    assert r.status_code == 400 and err(r) == "item_invalido"
    _, hm = membro
    r = ap.client.put(url, headers=hm, json={"version": 2, "resultado": "ok"})
    assert r.status_code == 403 and err(r) == "somente_dono"
    post = ap.client.get(f"/api/aprendizado/posts/{vid}/diagnostico", headers=hm).json()
    restrito = next(c for c in post["conferencias"] if c["item"] == "restrito")
    assert restrito["resultado"] == "problema" and restrito["updatedBy"]["name"] == "Dono"
