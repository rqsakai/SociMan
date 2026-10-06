"""Fontes e direito (spec 013, US3, T031, SC-003), com o YouTube falso da 006: proposta
conservadora, troca pelo dono, divergência sem mudar nada, vínculo, duas linhas do mesmo canal,
sem YouTube e cota esgotada."""

from sqlalchemy import select

from integration.agencia_helpers import (  # noqa: F401
    UC,
    UC2,
    UC3,
    _buckets,
    agencia,
    confirmar,
    dono,
    importar,
    itens,
    previa,
    um,
    yt,
)
from sociman_api.canais.models import CanalDireito, CanalFonte
from sociman_api.history import EntityVersion


def _linha(criador, canal, status, ev="", regras="", conf="dono", data="2026-09-24"):
    return (criador, canal, f"`{status}`", ev, regras, conf, data)


def _canal_existente(client, h, yt, cid, titulo, handle, direito, perfis=()):  # noqa: F811
    yt.add_canal(cid, titulo, handle=handle)
    from sociman_api.agencia import aplicar
    from sociman_api.canais.youtube import get_youtube_client
    from sociman_api.main import app

    app.dependency_overrides[get_youtube_client] = lambda: yt.client()
    r = client.post("/api/canais", headers=h, json={"youtubeChannelId": cid,
                                                     "perfilIds": list(perfis)})
    assert r.status_code == 201, r.text
    c = r.json()["canal"]
    r = client.put(f"/api/canais/{c['id']}/direito", headers=h,
                   json={"version": c["version"], "direito": direito, "evidenciaNota": "à mão"})
    assert r.status_code == 200, r.text
    assert aplicar.fabrica_youtube in app.dependency_overrides
    return r.json()["canal"]


def test_canal_novo_proposto_e_trocado_para_parceiro(client, db, dono, agencia, yt):  # noqa: F811
    user, h = dono
    yt.add_canal(UC, "Canal Um", handle="canalum")
    yt.add_canal(UC2, "Canal Dois", handle="canaldois")
    agencia.perfil()
    agencia.fontes("taverna-teste",
                   _linha("Canal Um", "youtube.com/@canalum", "autorizado",
                          "Autorizado no direct https://exemplo.com/print"),
                   _linha("Canal Dois", "https://www.youtube.com/channel/" + UC2,
                          "programa-de-cortes", "https://exemplo.com/regras", "48h antes"))
    p = previa(client, h)
    um_ = next(i for i in itens(p, "canal") if i["origem"]["trecho"] == "Canal Um")
    assert um_["origem"] == {"arquivo": "shared:perfis/taverna-teste/fontes.md",
                             "trecho": "Canal Um", "linha": 7}
    dois = next(i for i in itens(p, "canal") if i["origem"]["trecho"] == "Canal Dois")
    assert um_["situacao"] == "novo" and um_["escolhaPadrao"]["direito"] == "sem_acordo"
    assert dois["escolhaPadrao"]["direito"] == "programa_de_cortes"

    imp = confirmar(client, h, p, [{"n": um_["n"], "direito": "parceiro"}])

    canais = {c.youtube_channel_id: c for c in db.scalars(select(CanalFonte))}
    assert canais[UC].direito == CanalDireito.parceiro
    assert canais[UC].direito_evidencia_url == "https://exemplo.com/print"
    assert "fontes.md de taverna-teste, linha 7: status autorizado" in \
        canais[UC].direito_evidencia_nota
    assert canais[UC2].direito == CanalDireito.programa_de_cortes
    assert "Regras: 48h antes." in canais[UC2].direito_evidencia_nota
    assert [str(link.perfil_id) for link in canais[UC].perfil_links]
    v = db.scalars(select(EntityVersion).where(EntityVersion.entity_id == canais[UC].id)
                   .order_by(EntityVersion.version)).all()[-1]
    assert v.after["direito"] == "parceiro" and v.actor_user_id == user.id
    assert v.details["importacao"]["id"] == imp["id"]


def test_existente_aceito_igual_e_divergente_so_com_escolha(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    _canal_existente(client, h, yt, UC, "Canal Um", "canalum", "parceiro")
    pend = _canal_existente(client, h, yt, UC2, "Canal Dois", "canaldois", "parceiro")
    agencia.perfil()
    agencia.fontes("taverna-teste",
                   _linha("Canal Um", "youtube.com/@canalum", "autorizado"),
                   _linha("Canal Dois", "youtube.com/@canaldois", "pendente", conf="pesquisador"))
    p = previa(client, h)
    assert next(i for i in itens(p, "canal") if i["origem"]["trecho"] == "Canal Um"
                )["situacao"] == "igual"
    d = next(i for i in itens(p, "canal") if i["origem"]["trecho"] == "Canal Dois")
    assert (d["situacao"], d["motivo"]) == ("diverge", "direito")
    assert d["atual"]["direito"] == "parceiro" and d["proposto"]["direito"] == "sem_acordo"
    assert d["escolhaPadrao"] == {"marcado": None, "usar": "sociman", "direito": "sem_acordo"}

    confirmar(client, h, p)  # padrão: manter
    assert db.get(CanalFonte, pend["id"]).direito == CanalDireito.parceiro  # SC-003

    p = previa(client, h)
    d = next(i for i in itens(p, "canal") if i["origem"]["trecho"] == "Canal Dois")
    confirmar(client, h, p, [{"n": d["n"], "usar": "markdown"}])
    canal = db.get(CanalFonte, pend["id"])
    db.refresh(canal)
    assert canal.direito == CanalDireito.sem_acordo
    v = db.scalars(select(EntityVersion).where(EntityVersion.entity_id == canal.id)
                   .order_by(EntityVersion.version)).all()[-1]
    assert v.before["direito"] == "parceiro" and v.after["direito"] == "sem_acordo"


def test_canal_de_outro_perfil_ganha_so_o_vinculo(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    r = client.post("/api/perfis", headers=h, json={"name": "Outro", "slug": "outro-teste"})
    outro = r.json()["perfil"]
    canal = _canal_existente(client, h, yt, UC, "Canal Um", "canalum", "parceiro",
                             perfis=[outro["id"]])
    agencia.perfil()
    agencia.fontes("taverna-teste", _linha("Canal Um", "youtube.com/@canalum", "autorizado"))
    p, _ = importar(client, h)
    assert um(p, "canal")["situacao"] == "igual"
    v = um(p, "vinculo_canal")
    assert v["situacao"] == "novo"
    c = db.get(CanalFonte, canal["id"])
    db.refresh(c)
    assert len(c.perfil_links) == 2 and c.direito == CanalDireito.parceiro
    assert previa(client, h)["contagens"]["novo"] == 0


def test_duas_linhas_mesmo_canal_status_diferentes(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    _canal_existente(client, h, yt, UC, "Canal Um", "canalum", "parceiro")
    agencia.perfil()
    agencia.perfil("outro-teste", "Outro Teste")
    agencia.fontes("taverna-teste", _linha("Canal Um", "youtube.com/@canalum", "autorizado"))
    agencia.fontes("outro-teste", _linha("Canal Um", "youtube.com/channel/" + UC, "pendente"))
    p = previa(client, h)
    c = um(p, "canal")
    assert (c["situacao"], c["motivo"]) == ("diverge", "direito")
    assert len(c["origens"]) == 1


def test_sem_youtube_e_cota(client, db, dono, agencia, yt):  # noqa: F811
    _, h = dono
    yt.add_canal(UC3, "Canal Três", handle="canaltres")
    agencia.perfil()
    agencia.fontes("taverna-teste",
                   _linha("Sem link", "handle exato não confirmado nesta pesquisa", "autorizado"),
                   _linha("Twitch", "twitch.tv/alguem · tiktok.com/@alguem", "autorizado"),
                   _linha("A confirmar", "canal(is) de cortes a confirmar", "programa-de-cortes"),
                   _linha("Material original próprio", "arquivos em media/originais/x/",
                          "autorizado"),
                   _linha("Busca", "youtube.com/c/AlgumCanal", "autorizado"),
                   _linha("Canal Três", "youtube.com/channel/" + UC3, "negado",
                          data="2026-09-20"))
    yt.erro_proximo("quotaExceeded")
    p = previa(client, h)
    por_trecho = {i["origem"]["trecho"]: i for i in itens(p, "canal")}
    assert por_trecho["Sem link"]["motivo"] == "sem_canal_youtube"
    assert por_trecho["Twitch"]["motivo"] == "sem_canal_youtube"
    assert por_trecho["A confirmar"]["motivo"] == "sem_canal_youtube"
    assert por_trecho["Material original próprio"]["motivo"] == "conteudo_proprio"
    assert por_trecho["Sem link"]["proposto"]["canal"].startswith("handle exato")
    assert por_trecho["Busca"]["situacao"] == "aguardando_cota"
    # o id direto não precisa do YouTube na prévia: segue normal
    tres = por_trecho["Canal Três"]
    assert tres["situacao"] == "novo" and tres["escolhaPadrao"]["direito"] == "sem_acordo"
    assert "Negado no markdown em 2026-09-20." in tres["proposto"]["evidenciaNota"]
    assert p["contagens"]["aguardandoCota"] == 1
