"""ia.aplicacao.marcar (research R10): desfecho das chamadas aplicadas num save, sem banco."""

import uuid
from types import SimpleNamespace

import pytest

from sociman_api.ia.aplicacao import IaAplicacao, marcar
from sociman_api.ia.models import IaDesfecho

PERFIL = uuid.uuid4()
OUTRO_PERFIL = uuid.uuid4()
USER = uuid.uuid4()
ACTOR = SimpleNamespace(kind="user", user_id=USER)


class FakeDb:
    def __init__(self, *chamadas):
        self.rows = {c.id: c for c in chamadas}

    def get(self, _model, ident, with_for_update=False):
        return self.rows.get(ident)


def chamada(tipo_campo, proposta, *, entity_type="asset", entity_id=None, perfil_id=PERFIL,
            desfecho=IaDesfecho.sem_acao, itens_aplicados=None, **extra):
    return SimpleNamespace(
        id=uuid.uuid4(), tipo_campo=tipo_campo, perfil_id=perfil_id, entity_type=entity_type,
        entity_id=entity_id, corte_id=extra.get("corte_id"), conta_id=extra.get("conta_id"),
        # Spec 014: na origem corte, o conteúdo tem o id do corte (a migration preenche).
        conteudo_id=extra.get("conteudo_id", extra.get("corte_id")),
        plataforma=extra.get("plataforma"), proposta=proposta, desfecho=desfecho,
        desfecho_em=None, desfecho_por=None, aplicada_versao=None,
        itens_aplicados=itens_aplicados,
    )


def avatar(version=3):
    return SimpleNamespace(id=uuid.uuid4(), perfil_id=PERFIL, tipo="avatar", version=version)


def ia(c, itens=None):
    return [IaAplicacao(tipo_campo=c.tipo_campo, chamada_id=c.id, itens=itens)]


# ---- texto ----

def test_texto_igual_a_proposta_fica_aplicada():
    a = avatar()
    c = chamada("avatar.descricao_prompt", {"texto": "A woman, 30s"}, entity_id=a.id)
    details = marcar(FakeDb(c), ACTOR, "asset", a, {"prompt": "velho"},
                     {"prompt": "A woman, 30s"}, ia(c))
    assert details == {"ia": [{"campo": "prompt", "tipoCampo": "avatar.descricao_prompt",
                               "chamadaId": str(c.id), "desfecho": "aplicada"}]}
    assert c.desfecho == IaDesfecho.aplicada
    assert c.aplicada_versao == 4
    assert c.desfecho_por == USER
    assert c.desfecho_em is not None


def test_texto_diferente_fica_editada_e_trim_segue_o_campo():
    a = avatar()
    tom = chamada("avatar.tom_de_voz", {"texto": "Leve e direto"}, entity_id=a.id)
    details = marcar(FakeDb(tom), ACTOR, "asset", a, {"voice_tone": ""},
                     {"voice_tone": "Leve e direto!"}, ia(tom))
    assert details["ia"][0]["desfecho"] == "editada"
    assert tom.desfecho == IaDesfecho.editada

    # tom_de_voz tem trim: espaço nas pontas da proposta não conta como edição
    tom2 = chamada("avatar.tom_de_voz", {"texto": "  Leve  "}, entity_id=a.id)
    marcar(FakeDb(tom2), ACTOR, "asset", a, {"voice_tone": ""}, {"voice_tone": "Leve"},
           ia(tom2))
    assert tom2.desfecho == IaDesfecho.aplicada

    # o prompt é sem trim: o espaço conta
    p = chamada("avatar.descricao_prompt", {"texto": "A woman "}, entity_id=a.id)
    marcar(FakeDb(p), ACTOR, "asset", a, {"prompt": ""}, {"prompt": "A woman"}, ia(p))
    assert p.desfecho == IaDesfecho.editada


def test_asset_casa_com_chamada_de_outro_perfil_base_ou_sem_perfil():
    """Spec 029 (C1): no item da biblioteca, o perfil base pode ter sido trocado só na geração."""
    for perfil_id in (OUTRO_PERFIL, None):
        a = avatar()
        c = chamada("avatar.descricao_prompt", {"texto": "novo"}, entity_id=a.id,
                    perfil_id=perfil_id)
        details = marcar(FakeDb(c), ACTOR, "asset", a, {"prompt": "x"}, {"prompt": "novo"},
                         ia(c))
        assert details is not None and c.desfecho == IaDesfecho.aplicada


def test_perfil_continua_exigindo_o_mesmo_perfil():
    p = SimpleNamespace(id=PERFIL, version=2)
    c = chamada("perfil.bio", {"texto": "nova"}, entity_type="perfil", entity_id=PERFIL,
                perfil_id=OUTRO_PERFIL)
    assert marcar(FakeDb(c), ACTOR, "perfil", p, {"bio": "x"}, {"bio": "nova"}, ia(c)) is None


@pytest.mark.parametrize("caso", ["outro_alvo", "tipo_nao_casa", "sem_mudanca",
                                  "ja_aplicada", "descartada", "tipo_divergente", "inexistente"])
def test_itens_que_nao_casam_sao_ignorados(caso):
    a = avatar()
    kw = {"entity_id": a.id}
    tipo = "avatar.descricao_prompt"
    antes, depois = {"prompt": "x"}, {"prompt": "novo"}
    if caso == "outro_alvo":
        kw["entity_id"] = uuid.uuid4()
    elif caso == "sem_mudanca":
        antes = depois
    elif caso == "ja_aplicada":
        kw["desfecho"] = IaDesfecho.aplicada
    elif caso == "descartada":
        kw["desfecho"] = IaDesfecho.descartada
    c = chamada(tipo, {"texto": "novo"}, **kw)
    itens = ia(c)
    db = FakeDb(c)
    alvo = a
    if caso == "tipo_nao_casa":  # prompt do avatar num cenário
        alvo = SimpleNamespace(id=a.id, perfil_id=PERFIL, tipo="cenario", version=1)
    elif caso == "tipo_divergente":  # o corpo diz um tipo, a chamada é de outro
        itens = [IaAplicacao(tipo_campo="avatar.tom_de_voz", chamada_id=c.id)]
    elif caso == "inexistente":
        db = FakeDb()
    before = (c.desfecho, c.aplicada_versao)
    assert marcar(db, ACTOR, "asset", alvo, antes, depois, itens) is None
    assert (c.desfecho, c.aplicada_versao) == before


def test_sem_ia_devolve_none():
    a = avatar()
    assert marcar(FakeDb(), ACTOR, "asset", a, {"prompt": "a"}, {"prompt": "b"}, None) is None
    assert marcar(FakeDb(), ACTOR, "asset", a, {"prompt": "a"}, {"prompt": "b"}, []) is None


def test_asset_nome_vale_para_qualquer_tipo_e_perfil_bio():
    cen = SimpleNamespace(id=uuid.uuid4(), perfil_id=PERFIL, tipo="cenario", version=1)
    c = chamada("asset.nome", {"texto": "Cozinha"}, entity_id=cen.id)
    d = marcar(FakeDb(c), ACTOR, "asset", cen, {"name": "x"}, {"name": "Cozinha"}, ia(c))
    assert d["ia"][0]["campo"] == "name" and c.aplicada_versao == 2

    perfil = SimpleNamespace(id=PERFIL, version=5)
    b = chamada("perfil.bio", {"texto": "Bio nova"}, entity_type="perfil", entity_id=PERFIL)
    d = marcar(FakeDb(b), ACTOR, "perfil", perfil, {"bio": ""}, {"bio": "Bio nova"}, ia(b))
    assert d["ia"][0]["desfecho"] == "aplicada" and b.aplicada_versao == 6


def test_um_item_ruim_nao_impede_os_outros():
    a = avatar()
    boa = chamada("avatar.descricao_prompt", {"texto": "ok"}, entity_id=a.id)
    ruim = chamada("avatar.tom_de_voz", None, entity_id=a.id)  # proposta nula (erro)
    itens = [*ia(ruim), *ia(boa)]
    d = marcar(FakeDb(boa, ruim), ACTOR, "asset", a, {"prompt": "", "voice_tone": ""},
               {"prompt": "ok", "voice_tone": "x"}, itens)
    assert [e["chamadaId"] for e in d["ia"]] == [str(boa.id)]


# ---- sugestões (kit) ----

def kit(version=2):
    return SimpleNamespace(id=uuid.uuid4(), perfil_id=PERFIL, version=version)


def test_sugestoes_itens_novos_aplicados_e_ja_existente_ignorado():
    k = kit()
    c = chamada("kit.bordoes", {"itens": ["Bora!", "Olha isso", "Achou?"]}, entity_type="kit",
                entity_id=k.id)
    antes = {"catchphrases": ["Oi gente", "olha isso"]}
    depois = {"catchphrases": ["Oi gente", "olha isso", "Bora!"]}
    d = marcar(FakeDb(c), ACTOR, "kit", k, antes, depois, ia(c, ["Bora!", "Olha isso"]))
    assert d["ia"][0]["itens"] == ["Bora!"]
    assert d["ia"][0]["desfecho"] == "aplicada"
    assert d["ia"][0]["campo"] == "catchphrases"
    assert c.itens_aplicados == ["Bora!"]
    assert c.aplicada_versao == 3


def test_sugestoes_item_editado_fica_editada():
    k = kit()
    c = chamada("kit.series", {"itens": ["Achado do dia"]}, entity_type="kit", entity_id=k.id)
    d = marcar(FakeDb(c), ACTOR, "kit", k, {"series": []}, {"series": ["Achado da semana"]},
               ia(c, ["Achado da semana"]))
    assert d["ia"][0]["desfecho"] == "editada"
    assert c.itens_aplicados == ["Achado da semana"]


def test_sugestoes_segunda_aplicacao_acumula_e_nao_volta_de_editada():
    k = kit()
    c = chamada("kit.bordoes", {"itens": ["A1", "B2", "C3"]}, entity_type="kit",
                entity_id=k.id)
    db = FakeDb(c)
    marcar(db, ACTOR, "kit", k, {"catchphrases": []}, {"catchphrases": ["A1 editado"]},
           ia(c, ["A1 editado"]))
    assert c.desfecho == IaDesfecho.editada
    k.version = 3
    d = marcar(db, ACTOR, "kit", k, {"catchphrases": ["A1 editado"]},
               {"catchphrases": ["A1 editado", "B2"]}, ia(c, ["B2"]))
    assert d["ia"][0]["itens"] == ["B2"]
    assert c.desfecho == IaDesfecho.editada
    assert c.itens_aplicados == ["A1 editado", "B2"]
    assert c.aplicada_versao == 4


def test_sugestoes_aplicada_continua_aplicada_na_segunda_vez():
    k = kit()
    c = chamada("kit.bordoes", {"itens": ["A1", "B2"]}, entity_type="kit", entity_id=k.id)
    db = FakeDb(c)
    marcar(db, ACTOR, "kit", k, {"catchphrases": []}, {"catchphrases": ["A1"]}, ia(c, ["A1"]))
    marcar(db, ACTOR, "kit", k, {"catchphrases": ["A1"]}, {"catchphrases": ["A1", "B2"]},
           ia(c, ["B2"]))
    assert c.desfecho == IaDesfecho.aplicada
    assert c.itens_aplicados == ["A1", "B2"]


def test_sugestoes_item_fora_da_lista_e_ignorado():
    k = kit()
    c = chamada("kit.bordoes", {"itens": ["A1"]}, entity_type="kit", entity_id=k.id)
    assert marcar(FakeDb(c), ACTOR, "kit", k, {"catchphrases": []}, {"catchphrases": ["Z"]},
                  ia(c, ["A1"])) is None
    assert c.desfecho == IaDesfecho.sem_acao


def test_kit_nunca_salvo_casa_chamada_sem_entity_id():
    k = kit(version=1)
    c = chamada("kit.bordoes", {"itens": ["A1"]}, entity_type="kit", entity_id=None)
    d = marcar(FakeDb(c), ACTOR, "kit", k, None, {"catchphrases": ["A1"]}, ia(c, ["A1"]))
    assert d["ia"][0]["desfecho"] == "aplicada"
    assert c.aplicada_versao == 1


# ---- postagem ----

def test_postagem_textos_e_hashtags():
    corte, conta = uuid.uuid4(), uuid.uuid4()
    p = SimpleNamespace(id=uuid.uuid4(), conteudo_id=corte, conta_id=conta, version=1)
    t = chamada("postagem.textos", {"titulo": "T", "descricao": "D",
                                    "hashtags": ["#a", "#b", "#c"]},
                entity_type="corte", entity_id=corte, corte_id=corte, conta_id=conta)
    d = marcar(FakeDb(t), ACTOR, "postagem", p, None,
               {"titulo": "T", "descricao": "D", "hashtags": ["#A", "#b", "#c"]}, ia(t),
               perfil_id=PERFIL, plataforma="youtube")
    assert d["ia"][0]["desfecho"] == "aplicada" and t.aplicada_versao == 1

    h = chamada("postagem.hashtags", {"itens": ["#x", "#y", "#z"]}, entity_type="postagem",
                entity_id=p.id)
    d = marcar(FakeDb(h), ACTOR, "postagem", p, {"hashtags": []},
               {"hashtags": ["#x", "#y"]}, ia(h), perfil_id=PERFIL, plataforma="youtube")
    assert d["ia"][0]["desfecho"] == "editada" and h.aplicada_versao == 2


def test_postagem_alvo_de_outra_conta_ignorado_e_linha_da_006_pela_plataforma():
    corte = uuid.uuid4()
    p = SimpleNamespace(id=uuid.uuid4(), conteudo_id=corte, conta_id=uuid.uuid4(), version=1)
    outra = chamada("postagem.titulo", {"texto": "T"}, entity_type="corte", entity_id=corte,
                    corte_id=corte, conta_id=uuid.uuid4())
    assert marcar(FakeDb(outra), ACTOR, "postagem", p, {"titulo": ""}, {"titulo": "T"},
                  ia(outra), perfil_id=PERFIL, plataforma="youtube") is None

    antiga = chamada("postagem.textos", {"titulo": "T", "descricao": "", "hashtags": []},
                     entity_type="corte", entity_id=corte, corte_id=corte,
                     plataforma=SimpleNamespace(value="youtube"))
    d = marcar(FakeDb(antiga), ACTOR, "postagem", p, {"titulo": ""},
               {"titulo": "T", "descricao": "", "hashtags": []}, ia(antiga),
               perfil_id=PERFIL, plataforma="youtube")
    assert d["ia"][0]["desfecho"] == "aplicada"


def test_postagem_alvo_conteudo_da_014():
    """Spec 014: a chamada feita com o alvo `conteudo` (antes de o destino existir) casa com o
    destino do mesmo conteúdo e conta; de outro conteúdo, não."""
    conteudo, conta = uuid.uuid4(), uuid.uuid4()
    p = SimpleNamespace(id=uuid.uuid4(), conteudo_id=conteudo, conta_id=conta, version=1)
    c = chamada("postagem.titulo", {"texto": "T"}, entity_type="conteudo", entity_id=conteudo,
                conteudo_id=conteudo, conta_id=conta)
    d = marcar(FakeDb(c), ACTOR, "postagem", p, None, {"titulo": "T"}, ia(c),
               perfil_id=PERFIL, plataforma="tiktok")
    assert d["ia"][0]["desfecho"] == "aplicada"
    outro = chamada("postagem.titulo", {"texto": "T"}, entity_type="conteudo",
                    entity_id=uuid.uuid4(), conta_id=conta)
    assert marcar(FakeDb(outro), ACTOR, "postagem", p, None, {"titulo": "T"}, ia(outro),
                  perfil_id=PERFIL, plataforma="tiktok") is None
