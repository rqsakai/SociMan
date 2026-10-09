"""Fluxo completo com navegador real (`@pytest.mark.navegador`): `uma-vez --limite 3` contra o
servidor sintético e o SociMan falso. Pulado quando não há Chromium do Playwright instalado.

Usa o Chromium do **Playwright** (nunca o Chrome do dono) com a linha de comando do contrato mais
`--headless=new --no-sandbox` (só aqui, por `flags_extra`: sem janela, e o Chromium do
Playwright não tem o sandbox SUID do Chrome do sistema).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sociman_coletor import log
from sociman_coletor.navegador import Navegador
from sociman_coletor.redes.tiktok_shop import ESQUEMA
from sociman_coletor.rodada import Coletor

from .fakes import RelogioFalso, SocimanFalso, rede_teste, sha
from .sintetico.servidor import ServidorSintetico

pytestmark = pytest.mark.navegador


def _chromium_do_playwright() -> str | None:
    """Caminho do Chromium que o Playwright instalado espera, se existir no cache."""
    try:
        import playwright

        browsers = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
        revisao = next(
            b["revision"]
            for b in json.loads(browsers.read_text())["browsers"]
            if b["name"] == "chromium"
        )
    except Exception:  # noqa: BLE001
        return None
    cache = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache" / "ms-playwright")
    )
    for nome in ("chrome", "headless_shell"):
        for pasta in (
            cache / f"chromium-{revisao}" / "chrome-linux",
            cache / f"chromium-{revisao}" / "chrome-linux64",
        ):
            exe = pasta / nome
            if exe.exists():
                return str(exe)
    return None


CHROMIUM = _chromium_do_playwright()
if CHROMIUM is None:
    pytestmark = [pytest.mark.navegador, pytest.mark.skip(reason="sem Chromium do Playwright")]


@pytest.fixture
def servidor():
    with ServidorSintetico() as s:
        yield s


def _coletor(cfg, token, sociman: SocimanFalso, relogio: RelogioFalso, servidor: ServidorSintetico):
    rede = rede_teste()

    def fabrica(baixador):
        return Navegador(
            CHROMIUM, cfg.perfil_dir, rede, baixador, flags_extra=("--headless=new", "--no-sandbox")
        )

    def esperar_rapido(pagina, ms):
        pagina.wait_for_timeout(min(ms, 30))

    return Coletor(
        cfg,
        token,
        rede,
        transport=sociman.transport,
        relogio=relogio,
        dormir=relogio.dormir,
        esperar_pagina=esperar_rapido,
        fabrica_navegador=fabrica,
        semente=5,
        batimento_s=3600,
    )


def test_uma_vez_tres_paginas(cfg, token, sociman, relogio, servidor, capsys):
    base = servidor.base
    sociman.tarefa(
        "produto",
        f"{base}/product/7291001?src=t",
        "produto:7291001",
        "ambas",
        {"baixarImagens": True, "imagensMax": 9},
    )
    sociman.tarefa(
        "ranking",
        f"{base}/ranking/cat45",
        "ranking:cat45:mais_vendidos:7d",
        "affiliate",
        {"rankingTipo": "mais_vendidos", "janela": "7d", "categoriaRedeId": "cat45"},
    )
    sociman.tarefa(
        "avaliacoes",
        f"{base}/product/7291001/reviews",
        "avaliacoes:7291001:1",
        "pagina_publica",
        {"paginas": 1},
    )
    sociman.tarefa("produto", f"{base}/product/7291009", "produto:7291009")  # 4ª: fora do limite
    log.configurar("INFO", cfg.log.arquivo)
    col = _coletor(cfg, token, sociman, relogio, servidor)
    codigo = col.uma_vez(3)
    assert codigo == 0, sociman.lotes
    itens = [i for lote in sociman.lotes for i in lote]
    assert [i["status"] for i in itens] == ["ok", "ok", "ok"]
    assert all(i["esquemaVersao"] == ESQUEMA for i in itens)
    produto, ranking, avaliacoes = itens
    # produto: as duas fontes, imagens com sha conferido e citadas na ficha
    assert produto["fonte"] == "ambas"
    assert produto["campos"]["paginaPublica"]["vendidos"]["valor"] == 1200
    assert produto["campos"]["affiliate"]["comissaoBp"] == 1200
    assert len(produto["imagens"]) == 3
    assert (
        produto["campos"]["ficha"]["imagensSha"]
        and produto["campos"]["ficha"]["variantes"][0]["imagemSha"] in produto["imagens"]
    )
    manifesto, arquivos = sociman.imagens[0]
    assert [m["sha256"] for m in manifesto] == [sha(a) for a in arquivos]
    assert all(a.startswith(b"\x89PNG") for a in arquivos)
    # ranking: 3 itens com imagem; avaliações: autorRef só, foto do cliente como imagem
    assert len(ranking["campos"]["itens"]) == 3 and ranking["campos"]["itens"][0]["imagemSha"]
    assert avaliacoes["campos"]["itens"][0]["autorRef"] == "6812001"
    assert avaliacoes["campos"]["itens"][0]["imagensSha"]
    assert any(m["origem"] == "avaliacao" for mani, _ in sociman.imagens for m in mani)
    assert "nickname" not in json.dumps(avaliacoes["campos"])
    # imagens antes dos itens em cada página
    seq = [o for o in sociman.ordem if o in ("imagens", "itens")]
    assert seq == ["imagens", "itens"] * 3
    # ritmo: 3 pausas 5..40 s no relógio simulado; só as 3 URLs da fila foram abertas
    assert len([d for d in relogio.dormidas if 5 <= d <= 40]) == 3
    paginas = [
        a for a in servidor.acessos if not a.startswith(("/api-sintetica", "/img", "/favicon"))
    ]
    assert paginas == ["/product/7291001", "/ranking/cat45", "/product/7291001/reviews"]
    assert sociman.fins[-1]["motivo"] == "limite" and sociman.fins[-1]["paginas"] == 3
    assert sociman.fins[-1]["imagens"] >= 3
    # log sem dado pessoal
    for h in log.obter().handlers:
        h.flush()
    texto = cfg.log.arquivo.read_text() + capsys.readouterr().err
    assert "scol_" not in texto and "@fulana" not in texto
    assert "Tecido" not in texto and "Fulana" not in texto and "?src=" not in texto
    # perfil: a trava foi solta e o DevToolsActivePort ficou no perfil
    assert (cfg.perfil_dir / ".sociman.lock").exists()


def test_captcha_para_e_registra(cfg, token, sociman, relogio, servidor):
    base = servidor.base
    sociman.tarefa("produto", f"{base}/captcha-produto", "produto:7291001")
    sociman.tarefa("produto", f"{base}/product/7291002", "produto:7291002")
    sociman.batimento_parar = {"parar": True, "motivo": "pausa_vencida"}
    col = _coletor(cfg, token, sociman, relogio, servidor)
    col.uma_vez(2)
    assert [e["tipo"] for e in sociman.eventos] == ["iniciado", "captcha"]
    assert sociman.lotes[0][0]["status"] == "captcha"
    assert sociman.fins[-1]["motivo"] == "pausa_vencida"
    # não recarregou em laço: 1 acesso à página de verificação, e a 2ª tarefa não abriu
    assert servidor.acessos.count("/verify/abc") == 1
    assert "/product/7291002" not in servidor.acessos


def test_login_perdido_evento(cfg, token, sociman, relogio, servidor):
    base = servidor.base
    servidor.redireciona_login.add("7291005")
    sociman.tarefa("produto", f"{base}/product/7291005", "produto:7291005")
    sociman.batimento_parar = {"parar": True, "motivo": "pausa_vencida"}
    col = _coletor(cfg, token, sociman, relogio, servidor)
    col.uma_vez(1)
    assert [e["tipo"] for e in sociman.eventos] == ["iniciado", "login_perdido"]
    assert sociman.lotes[0][0]["erroCodigo"] == "redirecionada"
    assert "?" not in sociman.eventos[1]["detalhe"]["urlSemParametros"]


def test_cinco_vazios_layout_mudou(cfg, token, sociman, relogio, servidor):
    base = servidor.base
    for i in range(6):
        sociman.tarefa("produto", f"{base}/vazio/{i}", f"produto:vazio{i}")
    col = _coletor(cfg, token, sociman, relogio, servidor)
    col.uma_vez(6)
    assert [e["tipo"] for e in sociman.eventos] == ["iniciado", "layout_mudou"]
    assert len([a for a in servidor.acessos if a.startswith("/vazio/")]) == 5
    assert col.estado.recuo_ate is not None
    itens = [i for lote in sociman.lotes for i in lote]
    assert all(i["status"] == "erro" for i in itens)
