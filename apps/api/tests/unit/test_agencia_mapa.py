"""Mapeamento explícito (spec 013, T009, FR-005): cada um dos 71 caminhos do levantamento de
2026-10-06 (lista literal: nomes só, sem ler a pasta real) cai no leitor ou no motivo esperado;
caminho desconhecido fica "fora do mapeamento"."""

import pytest

from sociman_api.agencia import mapa

LEVANTAMENTO = {
    "agencia.md": "manual",
    "aprendizados.md": "manual",
    "custos.md": "manual",
    "modelos/candidatos.md": "manual",
    "modelos/pacote-clipes.md": "manual",
    "modelos/plano-dia.md": "manual",
    "modelos/plano-semana.md": "manual",
    "modelos/relatorio.md": "manual",
    "modelos/retro.md": "manual",
    "perfis/atavernanerd/assets/avatar-5poses.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/avatar-poses/avatar-1-itnerd-cortes.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/avatar-poses/avatar-2-rpg-dnd.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/avatar-poses/avatar-3-colecionaveis.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/avatar-poses/avatar-4-impressora3d.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/avatar-poses/avatar-5-leitura-fantasia.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/foto-perfil.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/logo.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/stickers-CHECKERBOARD-nao-usar-ainda.jpg": "nao_usar_ainda",
    "perfis/atavernanerd/assets/stickers/sticker-aprovando.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/stickers/sticker-choque.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/stickers/sticker-crit1.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/stickers/sticker-gargalhando.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/stickers/sticker-lendo.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/stickers/sticker-natural20.jpg": "imagem_perfil",
    "perfis/atavernanerd/assets/watermark-CHECKERBOARD-nao-usar-ainda.jpg": "nao_usar_ainda",
    "perfis/atavernanerd/candidatos/2026-09-25.md": "operacional",
    "perfis/atavernanerd/candidatos/.gitkeep": "marcador",
    "perfis/atavernanerd/clipes/2026-09-25.md": "operacional",
    "perfis/atavernanerd/clipes/.gitkeep": "marcador",
    "perfis/atavernanerd/dia/.gitkeep": "marcador",
    "perfis/atavernanerd/fontes.md": "fontes",
    "perfis/atavernanerd/ideias-gravacao.md": "ideias",
    "perfis/atavernanerd/perfil.md": "perfil",
    "perfis/atavernanerd/pesquisa.md": "pesquisa",
    "perfis/atavernanerd/registro-clipes.md": "registro",
    "perfis/atavernanerd/revisoes/.gitkeep": "marcador",
    "perfis/atavernanerd/semana/2026-W40.md": "operacional",
    "perfis/atavernanerd/semana/.gitkeep": "marcador",
    "perfis/INDEX.md": "index",
    "perfis/_modelo/fontes.md": "molde",
    "perfis/_modelo/perfil.md": "molde",
    "perfis/_modelo/pesquisa.md": "molde",
    "perfis/_modelo/registro-clipes.md": "molde",
    "perfis/queridinhos/candidatos/2026-09-25.md": "operacional",
    "perfis/queridinhos/candidatos/.gitkeep": "marcador",
    "perfis/queridinhos/clipes/2026-09-25.md": "operacional",
    "perfis/queridinhos/clipes/.gitkeep": "marcador",
    "perfis/queridinhos/dia/2026-09-25.md": "operacional",
    "perfis/queridinhos/dia/.gitkeep": "marcador",
    "perfis/queridinhos/fontes.md": "fontes",
    "perfis/queridinhos/perfil.md": "perfil",
    "perfis/queridinhos/pesquisa.md": "pesquisa",
    "perfis/queridinhos/registro-clipes.md": "registro",
    "perfis/queridinhos/revisoes/.gitkeep": "marcador",
    "perfis/queridinhos/semana/2026-W40.md": "operacional",
    "perfis/queridinhos/semana/.gitkeep": "marcador",
    "relatorios/.gitkeep": "marcador",
    "shop/avatares-candidatos.md": "heygen",
    "shop/avatares.md": "heygen",
    "shop/fontes-dados.md": "spec_012",
    "shop/nicho.md": "spec_012",
    "shop/pacotes/.gitkeep": "marcador",
    "shop/persona/achadinhos-cozinha.jpg": "imagem_persona",
    "shop/persona/achadinhos-diner.jpg": "imagem_persona",
    "shop/persona.md": "persona",
    "shop/produtos/.gitkeep": "marcador",
    "shop/propostas/.gitkeep": "marcador",
    "shop/README.md": "spec_012",
    "shop/relatorios/.gitkeep": "marcador",
    "shop/roteiros/.gitkeep": "marcador",
    "shop/vozes-pt.md": "heygen",
}


def test_os_71_caminhos_do_levantamento():
    assert len(LEVANTAMENTO) == 71
    for rel, esperado in LEVANTAMENTO.items():
        leitor, motivo = mapa.classificar(f"shared:{rel}")
        assert (leitor or motivo) == esperado, rel
        assert (leitor is None) != (motivo is None), rel


@pytest.mark.parametrize(("arquivo", "esperado"), [
    ("shared:perfis/x/notas.txt", (None, "fora_do_mapeamento")),
    ("shared:outra/coisa.md", (None, "fora_do_mapeamento")),
    ("shared:perfis/x/assets/LOGO.PNG", ("imagem_perfil", None)),
    ("shared:perfis/x/assets/a/b/c.webp", ("imagem_perfil", None)),
    ("shared:shop/roteiros/r1.md", (None, "specs_011_012")),
    ("shared:perfis/x/revisoes/r.md", (None, "operacional")),
    ("clipes:x/2026-09-25/x-1.mp4", ("clipe", None)),
    ("clipes:x/x-1.mp4", (None, "fora_do_mapeamento")),
    ("clipes:x/2026-09-25/x-1.mov", (None, "fora_do_mapeamento")),
])
def test_casos(arquivo, esperado):
    assert mapa.classificar(arquivo) == esperado


def test_todo_motivo_tem_texto():
    assert {m for _, leitor, m in mapa.MAPA if leitor is None} <= set(mapa.MOTIVOS)
    assert {leitor for _, leitor, _ in mapa.MAPA if leitor} <= set(mapa.LEITORES)
