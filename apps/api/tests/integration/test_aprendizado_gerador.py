"""Bloco `<desempenho>` no gerador (spec 023, T049/T050; SC-007; FR-044 a FR-047): a ordem dos
blocos e o `cache_control` só no último; 10 gerações com o bloco trazem as fixas, nenhuma
"evitar" e as versões no registro; os exemplos por regra fixa; desligado → NULL."""

import uuid
from datetime import timedelta

from fakes.anthropic_fake import anthropic_fake, mensagem  # noqa: F401
from sqlalchemy import select

from integration.analytics_helpers import local
from integration.guia_ia_helpers import alvo_corte, cena, fake, gerar, guia_conta  # noqa: F401
from integration.postagem_helpers import criar_corte, dono  # noqa: F401
from sociman_api.aprendizado import desempenho
from sociman_api.ia.models import IaChamada
from sociman_api.metricas.models import FotoVideo, Serie, VideoRede
from sociman_api.perfis.models import Platform
from sociman_api.postagem.models import DestinoEstado, Postagem

TEXTOS = {"titulo": "Um título", "descricao": "Uma descrição.",
          "hashtags": ["#fyp", "#dica", "#casa", "#geek"]}


def _prefs(client, c, **body):
    url = f"/api/perfis/{c['perfil']['id']}/aprendizado/preferencias"
    v = client.get(url, headers=c["h"]).json()["perfil"]["version"]
    r = client.patch(url, headers=c["h"], json={"version": v, **body})
    assert r.status_code == 200, r.text


def _system(fake) -> str:  # noqa: F811
    return fake.systems[-1]


def test_dez_geracoes_com_bloco_fixas_sem_evitar(client, db, cena, fake):  # noqa: F811
    c = cena
    guia_conta(client, c, hashtagsFixas=["#taverna"])
    _prefs(client, c, hashtagsEvitar=["#fyp"],
           padroes=[{"tipo": "gancho", "texto": "Abrir com uma pergunta"}])
    for _ in range(10):
        fake.responder(mensagem(TEXTOS | {"explicacao": "ok", "avisos": []}),
                       mensagem(TEXTOS | {"explicacao": "ok", "avisos": []}))
        ch = gerar(client, c, "postagem.textos", alvo_corte(c))
        tags = ch["proposta"]["hashtags"]
        assert tags[0] == "#taverna" and "#fyp" not in tags
        row = db.get(IaChamada, uuid.UUID(ch["id"]))
        assert "removida #fyp: marcada para evitar" in row.ajustes
        assert any("#fyp" in a for a in ch["avisos"])
        assert ch["desempenhoPerfilVersion"] == 2 and ch["desempenhoContaVersion"] == 0
    system = _system(fake)
    assert system.index("<guia_conta") < system.index("<desempenho") < system.index("<perfil>")
    assert '<desempenho versao_perfil="2" versao_conta="0">' in system
    assert "Hashtags a evitar (não use): #fyp" in system and "Abrir com uma pergunta" in system
    blocos = fake.system_blocos[-1]
    assert "cache_control" in blocos[-1] and all("cache_control" not in b for b in blocos[:-1])
    # a 1ª tentativa usou a evitada: o modelo foi avisado antes do corte pelo servidor
    assert "marcada para evitar" in fake.bodies[1]["messages"][0]["content"]
    rows = db.scalars(select(IaChamada).where(IaChamada.tipo_campo == "postagem.textos")).all()
    assert len(rows) == 10 and all(r.prompt_version == "ia/3" for r in rows)
    assert all(r.desempenho_perfil_version == 2 for r in rows)


def test_desligado_e_sem_nada_ficam_sem_bloco(client, db, cena, fake):  # noqa: F811
    c = cena
    ch = gerar(client, c, "postagem.textos", alvo_corte(c))  # sem preferências nem exemplos
    assert ch["desempenhoPerfilVersion"] is None and "<desempenho versao" not in _system(fake)
    _prefs(client, c, padroes=[{"tipo": "gancho", "texto": "Pergunta"}], usarDesempenho=False)
    ch = gerar(client, c, "postagem.textos", alvo_corte(c))
    assert ch["desempenhoPerfilVersion"] is None and ch["desempenhoExemplos"] == []
    assert "<desempenho versao" not in _system(fake)
    ch = gerar(client, c, "perfil.bio", {"entityType": "perfil", "entityId": c["perfil"]["id"]})
    assert ch["desempenhoPerfilVersion"] is None  # só `postagem.*` e `guia.testar`


def _post(db, conta_id, dias, views, legenda, corte=None, dono=None):  # noqa: F811
    sid = db.scalar(select(Serie.id).where(Serie.conta_id == uuid.UUID(conta_id)))
    if sid is None:
        s = Serie(rede=Platform.tiktok, conta_id=uuid.UUID(conta_id))
        db.add(s)
        db.flush()
        sid = s.id
    pub = local(dias, 12)
    v = VideoRede(serie_id=sid, rede_video_id=str(uuid.uuid4().int % 10**18), legenda=legenda,
                  duracao_s=30, publicado_em=pub, descoberto_em=pub)
    db.add(v)
    db.flush()
    for h in (1, 6, 24, 30):
        db.add(FotoVideo(video_id=v.id, coletado_em=pub + timedelta(hours=h), idade_s=h * 3600,
                         alvo_idade_min=h * 60, views=round(views * min(h, 24) / 24)))
    if corte is not None:
        d = Postagem(conteudo_id=corte.id, conta_id=uuid.UUID(conta_id),
                     estado=DestinoEstado.postado, version=1, aprovado_por=dono,
                     aprovado_em=pub - timedelta(hours=1), posted_at=pub)
        db.add(d)
        db.flush()
        v.destino_id, v.vinculo_metodo, v.vinculado_em = d.id, "escolha", pub
    db.commit()
    return v.id


def test_exemplos_por_regra_fixa(client, db, cena):  # noqa: F811
    c = cena
    conta = c["tiktok"]["id"]
    ids = [_post(db, conta, d, 100 * d, f"Legenda {d}") for d in range(2, 18)]
    corte = criar_corte(db, c["perfil"]["id"], hook_text="Você sabia?")
    melhor = _post(db, conta, 19, 50000, "A melhor legenda", corte=corte, dono=c["user"].id)
    proibido = _post(db, conta, 20, 40000, "Compre já este achado")
    velho = _post(db, conta, 95, 90000, "Fora dos 90 dias")
    perfil_id = uuid.UUID(c["perfil"]["id"])
    exs = desempenho.exemplos(db, perfil_id, uuid.UUID(conta), ("compre já",))
    assert exs[0].video_id == melhor and exs[0].gancho == "Você sabia?"
    assert proibido not in [e.video_id for e in exs] and velho not in [e.video_id for e in exs]
    assert len(exs) == 3 and {e.video_id for e in exs} <= {melhor, *ids}
