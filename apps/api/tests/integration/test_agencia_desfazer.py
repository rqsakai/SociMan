"""Desfazer (spec 013, US7, T045, SC-007): criado e intocado → arquivado; atualizado → revertido;
editado depois → não desfeito; em uso → não desfeito; nada apagado; desfazer de novo → 409."""

from sqlalchemy import select

from integration.agencia_helpers import (  # noqa: F401
    UC,
    _buckets,
    agencia,
    confirmar,
    dono,
    importar,
    jpg,
    membro,
    previa,
    um,
    yt,
)
from sociman_api.anotacoes.models import Anotacao, AnotacaoSituacao
from sociman_api.assets.models import Asset
from sociman_api.canais.models import CanalDireito, CanalFonte
from sociman_api.conteudos.models import Conteudo
from sociman_api.envios.models import Envio
from sociman_api.ia.models import IaGuia
from sociman_api.perfis.models import Conta, Perfil


def _desfazer(client, h, imp, status=200):
    r = client.post(f"/api/agencia/importacoes/{imp['id']}/desfazer", headers=h,
                    json={"version": imp["version"]})
    assert r.status_code == status, r.text
    return r.json()


def test_desfaz_tudo_que_ninguem_mexeu(client, db, dono, agencia, yt, s3):  # noqa: F811
    user, h = dono
    yt.add_canal(UC, "Canal Um", handle="canalum")
    agencia.perfil()
    agencia.fontes("taverna-teste", ("Canal Um", "youtube.com/@canalum", "`autorizado`", "", "",
                                     "dono", "2026-09-24"))
    agencia.pesquisa("taverna-teste", {"1. Termos": "- PT: rpg"})
    agencia.escrever("perfis/taverna-teste/assets/foto.jpg", jpg())
    agencia.escrever("perfis/taverna-teste/assets/avatar-poses/avatar-1-rpg.jpg", jpg((3, 3, 3)))
    agencia.registro("taverna-teste", "taverna-teste-1")
    agencia.clipe("taverna-teste", "taverna-teste-1")
    _, imp = importar(client, h)
    criados = sum(1 for i in imp["itens"] if i["resultado"] in ("criado", "atualizado"))

    out = _desfazer(client, h, imp)

    assert out["estado"] == "desfeita" and out["desfeitaPor"]["id"] == str(user.id)
    feitos = [i for i in out["itens"] if i["resultado"] in ("criado", "atualizado")]
    assert len(feitos) == criados
    assert [i for i in feitos if i["desfazerMotivo"]] == []
    assert all(i["desfeitoEm"] for i in feitos)
    assert all(p.archived for p in db.scalars(select(Perfil)))
    assert all(c.archived for c in db.scalars(select(Conta)))
    assert all(c.archived for c in db.scalars(select(CanalFonte)))
    assert all(a.archived for a in db.scalars(select(Asset)))
    assert all(c.archived for c in db.scalars(select(Conteudo)))
    assert all(a.situacao == AnotacaoSituacao.arquivada for a in db.scalars(select(Anotacao)))
    guia = db.scalars(select(IaGuia)).one()
    assert guia.tom == "" and guia.vocabulario == []  # "limpar" = salvo vazio
    _desfazer(client, h, out, status=409)


def test_editado_depois_e_em_uso(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    yt.add_canal(UC, "Canal Um", handle="canalum")
    agencia.perfil()
    agencia.fontes("taverna-teste", ("Canal Um", "youtube.com/@canalum", "`autorizado`", "", "",
                                     "dono", "2026-09-24"))
    _, imp = importar(client, h)
    conta = db.scalars(select(Conta)).first()
    r = client.patch(f"/api/contas/{conta.id}", headers=h,
                     json={"version": conta.version, "notes": "mexi depois"})
    assert r.status_code == 200, r.text
    canal = db.scalars(select(CanalFonte)).one()
    db.add(Envio(**_envio(canal, db)))
    db.commit()

    out = _desfazer(client, h, imp)

    motivos = {(i["tipo"], i["desfazerMotivo"]) for i in out["itens"] if i["desfazerMotivo"]}
    assert ("conta", "editado_depois") in motivos
    assert ("canal", "em_uso") in motivos
    db.refresh(canal)
    assert not canal.archived
    db.refresh(conta)
    assert not conta.archived and conta.notes == "mexi depois"


def test_atualizado_volta_e_canal_volta_direito(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    r = client.post("/api/perfis", headers=h, json={"name": "Taverna Teste",
                                                     "slug": "taverna-teste", "status": "ativo",
                                                     "niche": "Nicho à mão"})
    assert r.status_code == 201
    agencia.perfil()
    p = previa(client, h)
    _, imp = None, confirmar(client, h, p, [{"n": um(p, "perfil")["n"], "usar": "markdown"}])
    assert db.scalars(select(Perfil)).one().niche == "RPG e colecionáveis"
    _desfazer(client, h, imp)
    perfil = db.scalars(select(Perfil)).one()
    db.refresh(perfil)
    assert perfil.niche == "Nicho à mão" and not perfil.archived


def _envio(canal, db) -> dict:
    """Um envio mínimo do canal (só para o "em uso" do desfazer)."""
    from datetime import UTC, datetime

    from sociman_api.canais.models import VideoFonte
    from sociman_api.envios.models import DireitoEnvio, EnvioOrigem

    video = VideoFonte(canal_id=canal.id, youtube_video_id="abcdefghijk", title="V",
                       published_at=datetime.now(UTC), next_metrics_at=datetime.now(UTC))
    db.add(video)
    db.flush()
    perfil_id = canal.perfil_links[0].perfil_id
    return {"perfil_id": perfil_id, "video_fonte_id": video.id, "canal_fonte_id": canal.id,
            "origem": EnvioOrigem.canal,
            "source_url": "https://www.youtube.com/watch?v=abcdefghijk", "source_title": "V",
            "direito_no_envio": DireitoEnvio(CanalDireito.sem_acordo.value)}
