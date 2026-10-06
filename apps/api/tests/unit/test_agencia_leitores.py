"""Leitores (spec 013, T016): perfil (frontmatter, §1 a §8), contas do §1, "Nenhum", nicho
completo, guia, decisões, fontes, registro, persona e "não reconhecido" com o que faltou."""

import pytest

from sociman_api.agencia import leitores as L

PERFIL = """---
slug: x
status: aguardando-aprovacao
---
# Perfil: X

## 1. Identidade
- Nome do perfil: **Taverna**
- @ no YouTube: Nenhum (só TikTok)
- @ no TikTok: @Taverna.X (https://www.tiktok.com/@taverna.x) — criado pelo dono
- Idioma: pt-BR

## 2. Nicho
- Nicho principal: {nicho}

## 3. Público
- Quem é: Nerds
- Dores e desejos:

## 4. Posicionamento e tom
- Tom (ex.: polêmico, educativo, humor): Humor
- Expressões da casa: Família de frases — "Achei, amei" / "Vem comigo" (a evoluir)
- Proibido (temas, palavras, tipos de corte): NSFW, política (já cobre)

## 5. Estilo visual
- Marca: trocar por `shared/perfis/x/assets/watermark.png` quando existir

## 6. Monetização
- Modelo: A DEFINIR

## 7. Metas
- Clipes por dia: 3

## 8. Decisões e histórico
| Data | Decisão | Por quê |
|---|---|---|
| 2026-09-25 | Nome | Livre |
"""


def test_ler_perfil():
    p = L.ler_perfil(PERFIL.format(nicho="RPG " * 80), "x")
    assert (p.nome, p.idioma, p.status_md, p.status) == ("Taverna", "pt-BR",
                                                         "aguardando-aprovacao", "em_preparacao")
    assert len(p.nicho) > 200  # o corte é da conciliação (com a anotação do texto completo)
    assert [(c.plataforma, c.handle, c.url) for c in p.contas] == [
        ("tiktok", "taverna.x", "https://www.tiktok.com/@taverna.x")]  # "Nenhum" não cria
    assert p.tom == "Humor"
    assert p.vocabulario == ["Achei, amei", "Vem comigo"]
    assert p.nao_faca == ["NSFW", "política (já cobre)"]
    assert p.citadas == ["perfis/x/assets/watermark.png"]
    trechos = [a.trecho for a in p.anotacoes]
    assert trechos[:3] == ["§3. Público", "§7. Metas", "§8 · 2026-09-25"]  # §6 só molde
    assert "Dores e desejos" not in p.anotacoes[0].texto  # campo vazio sai
    assert p.anotacoes[2].texto.endswith("Decisão: Nome\nPor quê: Livre")
    assert p.anotacoes[2].chave.startswith("8:2026-09-25:")


def test_perfil_sem_secao_nao_reconhecido():
    sem = PERFIL.format(nicho="x").replace("## 4. Posicionamento e tom", "## Outra coisa")
    with pytest.raises(L.NaoReconhecido) as e:
        L.ler_perfil(sem, "x")
    assert e.value.faltou == ["seção 4. posicionamento e tom"]


def test_status_desconhecido_vira_none():
    assert L.ler_perfil(PERFIL.format(nicho="x").replace("aguardando-aprovacao", "sei la"),
                        "x").status is None


def test_fontes():
    texto = ("| Criador | Canal (ID ou link) | Status | Evidência | Confirmado por | Data |\n"
             "|---|---|---|---|---|---|\n"
             "| The IT Nerd (canal próprio do dono) | youtube.com/@x | `autorizado` | ok | dono"
             " | 2026-09-25 |\n"
             "| Y | — | **pendente** | — | — | — |\n")
    a, b = L.ler_fontes(texto)
    assert (a.propria, a.status_md, a.confirmado_por, a.regras) == (True, "autorizado", "dono", "")
    assert (b.propria, b.status_md, b.canal) == (False, "pendente", "")
    with pytest.raises(L.NaoReconhecido):
        L.ler_fontes("| Nome | Link |\n|---|---|\n| a | b |\n")


def test_registro_e_data():
    texto = ("| ID | Data | Fonte | Título | Produto/CTA | Status | Obs |\n|---|---|---|---|---|---|---|\n"
             "| x-1 | 2026-09-25 | https://y (1:00) | Título | CTA | pronto | o |\n"
             "| x-2 | 2026-02-30 | | T2 | | pronto | |\n")
    r = L.ler_registro(texto)
    assert r["x-1"].titulo == "Título" and r["x-1"].data == "2026-09-25"
    assert r["x-2"].data is None  # data inválida


def test_persona():
    texto = ("# Persona: Achadinha\n\n## Descrição para prompts (inglês)\n> A woman.\n\n"
             "## Cenários\n- **Diner:** retro diner.\n\n## Imagens de referência\n"
             "| Look | Arquivo / origem | Uso |\n|---|---|---|\n"
             "| Diner, busto | `shared/shop/persona/a-diner.jpg` (HeyGen) | close |\n\n"
             "## Voz\n- Tom: animado.\n\n## Regras de imagem\n- Sem texto.\n")
    p = L.ler_persona(texto)
    assert (p.nome, p.prompt, p.voz, p.regras) == ("Achadinha", "A woman.", "Tom: animado.",
                                                   "Sem texto.")
    assert p.cenarios[0][:2] == ("Diner", "retro diner.")
    assert (p.imagens[0].arquivo, p.imagens[0].look) == ("a-diner.jpg", "Diner, busto")
    with pytest.raises(L.NaoReconhecido):
        L.ler_persona("# Persona: X\n\n## Voz\n- a\n")


def test_pesquisa_e_ideias():
    pesq = L.ler_pesquisa("# Pesquisa\n\n## 1. Termos\n- PT: rpg\n\n## 2. Vazia\n| A | B |\n"
                          "|---|---|\n\n## 3. Hashtags\n#rpg\n")
    assert [t.trecho for t in pesq] == ["§1. Termos", "§3. Hashtags"]
    ideias = L.ler_ideias("## 1. RPG\n1. **Pauta um** — gancho\n   continuação\n2. Pauta dois\n\n"
                          "## Como usar\n- grave\n")
    assert [i.trecho for i in ideias] == ["§1. RPG · 1", "§1. RPG · 2"]
    assert "continuação" in ideias[0].texto
