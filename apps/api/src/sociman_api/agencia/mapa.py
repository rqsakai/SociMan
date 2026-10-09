"""Mapeamento explícito arquivo → leitor (research R1, FR-005).

`MAPA` é uma lista ordenada de `(padrão, leitor | None, motivo de "fora")`; o primeiro padrão que
casa decide. Os padrões valem sobre o id do arquivo (`shared:<rel>` ou `clipes:<rel>`): `*` não
passa de uma pasta, `**/` casa zero ou mais pastas, `{a,b}` é alternativa; maiúsculas não
importam. Arquivo que não casa com nada fica "fora do mapeamento" e nunca é aberto.
"""

import re
from functools import cache

LEITORES = ("index", "perfil", "fontes", "pesquisa", "ideias", "registro", "imagem_perfil",
            "persona", "imagem_persona", "clipe")

_IMG = "{jpg,jpeg,png,webp}"

# Motivos de "fora" (código → texto da tela).
MOTIVOS: dict[str, str] = {
    "fora_do_mapeamento": "fora do mapeamento",
    "marcador": "marcador de pasta vazia",
    "molde": "molde vazio da agência",
    "operacional": "arquivo operacional da rodada de teste, sem entidade",
    "nao_usar_ainda": "o próprio nome diz para não usar ainda",
    "spec_012": "fica para a spec 012 (produtos)",
    "heygen": "HeyGen pausado",
    "specs_011_012": "fica para as specs 011 e 012 (roteiros e produtos)",
    "manual": "manual e moldes da agência",
    "link_para_fora": "link para fora da pasta",
}

MAPA: tuple[tuple[str, str | None, str | None], ...] = (
    ("shared:**/.gitkeep", None, "marcador"),
    ("shared:perfis/INDEX.md", "index", None),
    ("shared:perfis/_modelo/**", None, "molde"),
    ("shared:perfis/*/perfil.md", "perfil", None),
    ("shared:perfis/*/fontes.md", "fontes", None),
    ("shared:perfis/*/pesquisa.md", "pesquisa", None),
    ("shared:perfis/*/ideias-gravacao.md", "ideias", None),
    ("shared:perfis/*/registro-clipes.md", "registro", None),
    ("shared:perfis/*/{candidatos,semana,dia,clipes,revisoes}/**", None, "operacional"),
    ("shared:perfis/*/assets/**/*nao-usar-ainda*", None, "nao_usar_ainda"),
    (f"shared:perfis/*/assets/**/*.{_IMG}", "imagem_perfil", None),
    ("shared:shop/persona.md", "persona", None),
    (f"shared:shop/persona/*.{_IMG}", "imagem_persona", None),
    ("shared:shop/{nicho,fontes-dados,README}.md", None, "spec_012"),
    ("shared:shop/{avatares,avatares-candidatos,vozes-pt}.md", None, "heygen"),
    ("shared:shop/{produtos,roteiros,pacotes}/**", None, "specs_011_012"),
    ("shared:{agencia,aprendizados,custos}.md", None, "manual"),
    ("shared:modelos/**", None, "manual"),
    ("clipes:*/*/*.mp4", "clipe", None),
)


@cache
def _regex(padrao: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(padrao):
        c = padrao[i]
        if padrao.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if padrao.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "{":
            fim = padrao.index("}", i)
            out.append("(?:" + "|".join(re.escape(p) for p in padrao[i + 1:fim].split(","))
                       + ")")
            i = fim + 1
            continue
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


def classificar(arquivo_id: str) -> tuple[str | None, str | None]:
    """(leitor, None) ou (None, código do motivo de "fora")."""
    for padrao, leitor, motivo in MAPA:
        if _regex(padrao).match(arquivo_id):
            return leitor, motivo
    return None, "fora_do_mapeamento"
