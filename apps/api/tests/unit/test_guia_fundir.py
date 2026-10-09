"""Fusão perfil × conta, conflitos, render, tamanho e validação pura do guia (spec 017, R2 e
R4 a R6)."""

from sociman_api.ia import guia
from sociman_api.ia.guia import GuiaBloco, GuiaCampos

PERFIL = GuiaCampos(tom="Nerd e acolhedor", faca=("Explique o termo",),
                    nao_faca=("Spoiler sem aviso",), vocabulario=("taverneiro", "rolar dado"),
                    proibidas=("clickbait", "Pix"), emojis="nao", emojis_preferidos=("🎲",),
                    hashtags_fixas=("#taverna", "#rpg"),
                    exemplos=({"tipo": "titulo", "texto": "Rolamos 20!"},))
CONTA = GuiaCampos(nao_faca=("explique o TERMO",), faca=("spoiler sem aviso",),
                   proibidas=("CLICKBAIT", "grátis"), emojis="livre",
                   hashtags_fixas=("#rpg", "#tiktokrpg"), max_hashtags_fixas=6)


def test_fundir_sem_conta_usa_o_perfil_e_maximo_padrao():
    ef = guia.fundir(PERFIL, None)
    assert ef.proibidas == ("clickbait", "Pix")
    assert ef.hashtags_fixas == ("#taverna", "#rpg")
    assert ef.max_hashtags_fixas == guia.FIXAS_PADRAO == 5
    assert ef.emojis == "nao" and ef.emojis_preferidos == ("🎲",)
    assert ef.avisos == ()
    assert guia.fundir(None, None) == guia.GuiaEfetivo()


def test_fundir_une_proibidas_ordena_fixas_e_herda_emojis():
    ef = guia.fundir(GuiaBloco(PERFIL, 3, "perfil"), GuiaBloco(CONTA, 2, "conta"))
    assert ef.proibidas == ("clickbait", "Pix", "grátis")  # a conta não libera; sem repetir
    assert ef.proibidas_normalizadas == ("clickbait", "pix", "gratis")
    assert ef.hashtags_fixas == ("#taverna", "#rpg", "#tiktokrpg")  # perfil primeiro
    assert ef.max_hashtags_fixas == 6
    assert ef.emojis == "livre"  # a conta vence
    assert ef.emojis_preferidos == ("🎲",)  # a conta não definiu: herda
    sem_emojis = guia.fundir(PERFIL, GuiaCampos(emojis_preferidos=("🔥",)))
    assert sem_emojis.emojis == "nao" and sem_emojis.emojis_preferidos == ("🔥",)


def test_fundir_estado_invalido_herdado_corta_com_aviso():
    conta = GuiaCampos(hashtags_fixas=("#a", "#b"), max_hashtags_fixas=3)
    ef = guia.fundir(PERFIL, conta)
    assert ef.hashtags_fixas == ("#taverna", "#rpg", "#a")
    assert ef.avisos == (guia.aviso_fixas(3),)
    assert "ficaram as 3 primeiras" in ef.avisos[0]
    zero = guia.fundir(PERFIL, GuiaCampos(max_hashtags_fixas=0))
    assert zero.hashtags_fixas == () and zero.avisos


def test_conflitos():
    cs = guia.conflitos(PERFIL, CONTA)
    assert [c.campo for c in cs] == ["emojis", "naoFaca", "faca"]
    assert "vale a conta" in cs[0].mensagem
    assert (cs[1].perfil, cs[1].conta) == ("Explique o termo", "explique o TERMO")
    assert guia.conflitos(PERFIL, None) == []
    assert guia.conflitos(PERFIL, GuiaCampos(emojis="nao")) == []
    fixas = guia.conflitos(PERFIL, GuiaCampos(hashtags_fixas=("#x",), max_hashtags_fixas=2))
    assert [c.campo for c in fixas] == ["hashtagsFixas"]
    assert "somam 3" in fixas[0].mensagem


def test_render_completo_e_so_proibidas():
    texto = guia.render(GuiaBloco(PERFIL, 1, "perfil"))
    assert texto.splitlines()[0] == "Tom de voz: Nerd e acolhedor"
    for rotulo in ("Faça:\n- Explique o termo", "Não faça:\n- Spoiler sem aviso",
                   "Vocabulário da casa: taverneiro, rolar dado",
                   "Palavras proibidas: clickbait, Pix", "Emojis: não usar (preferidos: 🎲)",
                   "Hashtags fixas: #taverna #rpg",
                   "Exemplos aprovados (imite o estilo, não copie):\n- [título] Rolamos 20!"):
        assert rotulo in texto
    so = guia.render(PERFIL, so_proibidas=True)
    assert so == "Palavras proibidas: clickbait, Pix"
    assert guia.render(GuiaCampos(tom="x"), so_proibidas=True) == ""


def test_render_omite_secoes_vazias():
    assert guia.render(GuiaCampos(tom="Sério")) == "Tom de voz: Sério"
    assert guia.render(GuiaCampos(max_hashtags_fixas=3)) == ""
    assert guia.render(GuiaCampos(emojis="moderado")) == "Emojis: com moderação"


def test_tamanho_soma_todos_os_textos():
    c = GuiaCampos(tom="abc", faca=("12",), vocabulario=("x",), hashtags_fixas=("#ab",),
                   exemplos=({"tipo": "bordao", "texto": "12345"},))
    assert guia.tamanho(c) == 3 + 2 + 1 + 3 + 5
    assert guia.tamanho(GuiaCampos()) == 0


def test_vazio_e_bloco():
    assert GuiaCampos().vazio
    assert not GuiaCampos(max_hashtags_fixas=0).vazio
    assert not GuiaCampos(emojis="nao").vazio


def test_validar_limites_apara_descarta_e_recusa():
    campos = GuiaCampos(tom="  oi  ", faca=(" a ", "", "A", "b" * 201),
                        hashtags_fixas=("Dica De Hoje", "!!", "#dicadehoje"),
                        exemplos=({"tipo": "titulo", "texto": "  "},
                                  {"tipo": "legenda", "texto": "x" * 501}))
    limpos, erros = guia.validar_limites(campos, "conta")
    assert limpos.tom == "oi" and limpos.faca == ("a",)
    assert limpos.hashtags_fixas == ("#dicadehoje",)
    assert erros == {"faca.2": "item repetido", "faca.3": "no máximo 200 caracteres",
                     "hashtagsFixas.1": "hashtag inválida",
                     "hashtagsFixas.2": "hashtag repetida",
                     "exemplos.1.texto": "no máximo 500 caracteres"}


def test_validar_limites_quantidades_maximo_e_total():
    _, erros = guia.validar_limites(GuiaCampos(
        faca=tuple(f"f{i}" for i in range(11)), hashtags_fixas=tuple(f"#h{i}" for i in range(6)),
        max_hashtags_fixas=5, exemplos=tuple({"tipo": "titulo", "texto": f"e{i}"}
                                             for i in range(6))), "perfil")
    assert erros["faca"] == "no máximo 10 itens"
    assert erros["hashtagsFixas"] == "no máximo 5 hashtags fixas"
    assert "maxHashtagsFixas" in erros  # só na conta
    assert erros["exemplos"] == "no máximo 5 exemplos"
    _, erros = guia.validar_limites(GuiaCampos(max_hashtags_fixas=9,
                                               hashtags_fixas=tuple(f"#h{i}" for i in range(9))),
                                    "conta")
    assert erros == {"hashtagsFixas": "no máximo 8 hashtags fixas",
                     "maxHashtagsFixas": "de 0 a 8"}
    grande = GuiaCampos(tom="x" * 500,
                        exemplos=tuple({"tipo": "legenda", "texto": f"{i}" + "y" * 499}
                                       for i in range(5)),
                        faca=tuple(f"{i}" + "z" * 199 for i in range(10)))
    _, erros = guia.validar_limites(grande, "perfil")
    assert list(erros) == ["total"]


def test_proibidas_nos_campos():
    campos = GuiaCampos(tom="Sem clickbait", vocabulario=("pixel", "pix"),
                        hashtags_fixas=("#pix",),
                        exemplos=({"tipo": "titulo", "texto": "ok"},
                                  {"tipo": "legenda", "texto": "CLICKBAIT!"}))
    erros = guia.proibidas_nos_campos(campos, ["clickbait", "pix"])
    assert erros == {"tom": "usa a palavra proibida 'clickbait'",
                     "vocabulario.1": "usa a palavra proibida 'pix'",
                     "hashtagsFixas.0": "usa a palavra proibida 'pix'",
                     "exemplos.1.texto": "usa a palavra proibida 'clickbait'"}
    assert guia.proibidas_nos_campos(campos, []) == {}
