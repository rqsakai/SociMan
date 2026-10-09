"""Guardas estáticas (AST) do pacote `sociman_coletor` (contracts/coletor.md, "Testes").

- `.click(` só em `navegacao.py`, dentro de `clicar`;
- nenhum método proibido (fill, type, press, keyboard, set_input_files, select_option, check,
  uncheck, drag_and_drop, dblclick, tap, route, unroute, expose_function, add_init_script,
  new_page, new_context, set_content);
- `request` só em `imagens.py`;
- `evaluate*` sem `fetch(`/`XMLHttpRequest`;
- nenhuma string com host da rede fora de `redes/tiktok_shop.py`;
- nenhuma reprodução de chamada assinada (`X-Gnarly`, `_signature`, `msToken`);
- flags do Chrome exatamente as do contrato e nenhuma de automação;
- `INTERCEPTAR` e `CLIQUES_PERMITIDOS` são constantes literais;
- `httpx` só em `api.py`; deps de runtime só `playwright`, `httpx`, `pydantic`.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

from sociman_coletor import navegacao, navegador
from sociman_coletor.navegador import FLAGS_CHROME, linha_de_comando
from sociman_coletor.redes import tiktok_shop

PACOTE = Path(navegacao.__file__).parent
ARQUIVOS = sorted(p for p in PACOTE.rglob("*.py"))

METODOS_PROIBIDOS = frozenset(
    {
        "fill",
        "type",
        "press",
        "set_input_files",
        "select_option",
        "check",
        "uncheck",
        "drag_and_drop",
        "dblclick",
        "tap",
        "route",
        "unroute",
        "expose_function",
        "expose_binding",
        "add_init_script",
        "new_page",
        "new_context",
        "set_content",
        "insert_text",
        "press_sequentially",
    }
)
ATRIBUTOS_PROIBIDOS = frozenset({"keyboard", "touchscreen"})
FLAGS_AUTOMACAO = re.compile(
    r"--headless|--disable-blink-features|--enable-automation|"
    r"--remote-allow-origins|--disable-web-security|--incognito"
)
HOST_REDE = re.compile(
    r"https?://[^\s\"']*(tiktok|affiliate|tiktokv|tiktokcdn|ibyteimg)|"
    r"(tiktok|tiktokcdn|tiktokv|ibyteimg)\.(com|net|org|us)",
    re.IGNORECASE,
)
ASSINATURA = re.compile(r"X-Gnarly|_signature|msToken", re.IGNORECASE)


def _arvores() -> dict[Path, ast.Module]:
    return {p: ast.parse(p.read_text(encoding="utf-8"), filename=str(p)) for p in ARQUIVOS}


def _funcao_de(arvore: ast.Module, no: ast.AST) -> str | None:
    """Nome da função que contém `no` (primeiro nível de aninhamento relevante)."""
    for f in ast.walk(arvore):
        if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef):
            for filho in ast.walk(f):
                if filho is no:
                    return f.name
    return None


def test_click_so_em_navegacao_clicar():
    for caminho, arvore in _arvores().items():
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr == "click"
            ):
                assert caminho.name == "navegacao.py", f"click fora de navegacao.py: {caminho}"
                assert _funcao_de(arvore, no) == "clicar", "click fora de navegacao.clicar"


def test_nenhum_metodo_proibido():
    for caminho, arvore in _arvores().items():
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute):
                assert no.attr not in METODOS_PROIBIDOS, f"{caminho}: .{no.attr}"
                assert no.attr not in ATRIBUTOS_PROIBIDOS, f"{caminho}: .{no.attr}"


def test_request_so_em_imagens():
    for caminho, arvore in _arvores().items():
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute) and no.attr == "request":
                assert caminho.name == "imagens.py", f"request fora de imagens.py: {caminho}"
            if isinstance(no, ast.Name) and no.id == "request":
                assert caminho.name == "imagens.py", f"request fora de imagens.py: {caminho}"


def test_evaluate_sem_fetch_nem_xhr():
    for caminho, arvore in _arvores().items():
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr.startswith("evaluate")
            ):
                for arg in no.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        assert "fetch(" not in arg.value and "XMLHttpRequest" not in arg.value, (
                            caminho
                        )


def test_host_da_rede_so_no_adaptador():
    for caminho, arvore in _arvores().items():
        if caminho.name == "tiktok_shop.py":
            continue
        for no in ast.walk(arvore):
            if isinstance(no, ast.Constant) and isinstance(no.value, str):
                assert not HOST_REDE.search(no.value), f"{caminho}: {no.value[:60]}"


def test_sem_reproducao_de_chamada_assinada():
    for caminho in ARQUIVOS:
        texto = caminho.read_text(encoding="utf-8")
        assert not ASSINATURA.search(texto), caminho


def test_flags_do_chrome_exatamente_as_do_contrato():
    linha = linha_de_comando("/usr/bin/google-chrome", Path("/p/chrome-profile"), cdp=True)
    assert linha == [
        "/usr/bin/google-chrome",
        "--user-data-dir=/p/chrome-profile",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        "--lang=pt-BR",
        "--window-size=1280,900",
    ]
    assert FLAGS_CHROME == (
        "--no-first-run",
        "--no-default-browser-check",
        "--lang=pt-BR",
        "--window-size=1280,900",
    )
    sem_cdp = linha_de_comando("c", Path("/p"), cdp=False, url="https://x/login")
    assert "--remote-debugging-port=0" not in sem_cdp and sem_cdp[-1] == "https://x/login"
    for flag in linha + sem_cdp:
        assert not FLAGS_AUTOMACAO.search(flag), flag
    texto = Path(navegador.__file__).read_text(encoding="utf-8")
    assert "--headless" not in texto.replace("sem janela", "") or "FLAGS_AUTOMACAO" in texto
    # `flags_extra` só existe para o teste de fluxo e nasce vazia
    import inspect

    assert inspect.signature(navegador.Navegador).parameters["flags_extra"].default == ()


def test_interceptar_e_cliques_permitidos_sao_constantes():
    arvore = ast.parse(Path(tiktok_shop.__file__).read_text(encoding="utf-8"))
    atribuicoes = [n for n in arvore.body if isinstance(n, ast.Assign | ast.AnnAssign)]
    inter = [
        n
        for n in atribuicoes
        if any(
            getattr(t, "id", None) == "INTERCEPTAR"
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        )
    ]
    assert len(inter) == 1
    assert isinstance(inter[0].value, ast.Tuple)
    assert all(
        isinstance(e, ast.Call) and getattr(e.func, "attr", "") == "compile"
        for e in inter[0].value.elts
    )
    arvore = ast.parse(Path(navegacao.__file__).read_text(encoding="utf-8"))
    cliques = [
        n
        for n in arvore.body
        if isinstance(n, ast.Assign)
        and any(getattr(t, "id", None) == "CLIQUES_PERMITIDOS" for t in n.targets)
    ]
    assert len(cliques) == 1
    valor = cliques[0].value
    assert isinstance(valor, ast.Call) and getattr(valor.func, "id", "") == "frozenset"
    assert isinstance(navegacao.CLIQUES_PERMITIDOS, frozenset)
    assert navegacao.CLIQUES_PERMITIDOS == {
        "fechar_aviso",
        "aba_categoria",
        "paginacao",
        "ver_mais",
        "fechar_modal",
    }
    assert isinstance(tiktok_shop.INTERCEPTAR, tuple)
    # ninguém reatribui ou altera as duas constantes fora da definição
    for caminho, arv in _arvores().items():
        for no in ast.walk(arv):
            if isinstance(no, ast.Attribute) and no.attr in ("INTERCEPTAR", "CLIQUES_PERMITIDOS"):
                pai_store = isinstance(no.ctx, ast.Store)
                assert not pai_store or caminho.name == "tiktok_shop.py", caminho


def test_acoes_proibidas_do_contrato():
    for palavra in (
        "Adicionar",
        "Promover",
        "Seguir",
        "Comprar",
        "Enviar",
        "Comentar",
        "Curtir",
        "Salvar",
        "Solicitar",
        "Amostra",
        "Compartilhar",
        "Denunciar",
        "Favoritar",
        "Pedir",
        "Entrar",
        "Sair",
        "Login",
        "Cadastr",
    ):
        assert navegacao.acao_proibida(palavra.lower())
    assert navegacao.acao_proibida("Adicionar à vitrine") and navegacao.acao_proibida("CURTIR")
    assert navegacao.acao_proibida("Solicitar amostra grátis")
    assert not navegacao.acao_proibida("Entendi") and not navegacao.acao_proibida("Ver mais")
    assert not navegacao.acao_proibida("Próxima página") and not navegacao.acao_proibida("")


def test_print_sem_cookie_nem_authorization():
    for caminho, arvore in _arvores().items():
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "print":
                for arg in no.args:
                    for c in ast.walk(arg):
                        if isinstance(c, ast.Constant) and isinstance(c.value, str):
                            assert not re.search(r"cookie|authorization|scol_", c.value, re.I), (
                                caminho
                            )


def test_httpx_so_em_api_e_dependencias_fechadas():
    for caminho, arvore in _arvores().items():
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                nomes = [no.module or ""]
            else:
                continue
            for nome in nomes:
                if nome.split(".")[0] in ("httpx", "requests", "urllib3", "aiohttp"):
                    assert caminho.name == "api.py", f"{caminho}: import {nome}"
                if nome.split(".")[0] == "playwright":
                    assert caminho.name == "navegador.py", f"{caminho}: import {nome}"
    pyproject = tomllib.loads((PACOTE.parent / "pyproject.toml").read_text(encoding="utf-8"))
    deps = {re.split(r"[<>=!~\[ ]", d)[0] for d in pyproject["project"]["dependencies"]}
    assert deps == {"playwright", "httpx", "pydantic"}
    assert pyproject["project"]["scripts"] == {"sociman-coletor": "sociman_coletor.main:main"}


def test_nenhum_segredo_em_argumento_ou_ambiente():
    """O token só sai do arquivo: nenhum `environ[...]`/`getenv` com TOKEN, nem argparse."""
    for caminho, arvore in _arvores().items():
        texto = caminho.read_text(encoding="utf-8")
        assert "SOCIMAN_COLETA_TOKEN" not in texto, caminho
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr == "add_argument"
            ):
                for arg in no.args:
                    if isinstance(arg, ast.Constant):
                        assert str(arg.value).lower() not in ("--token", "token"), caminho
