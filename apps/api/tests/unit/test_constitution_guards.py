"""Guarda do princípio I da constitution: nenhum agente publica em rede social.

As próximas specs só ampliam as listas abaixo; nunca as reduzem.
O princípio II (direito primeiro) tem teste próprio desde a spec 006, que absorveu a 008
(`tests/integration/test_direito.py`).
"""

import ast
import re
import tomllib
from pathlib import Path

from sociman_api.main import app

PUBLISH_TERMS = ("publish", "post-to", "upload-to", "share", "tiktok", "youtube", "instagram")
SOCIAL_SDKS = ("tiktok", "google-api-python-client", "instagrapi", "facebook", "tweepy")
# Spec 006 (R12): endpoints de publicação que nenhum arquivo de `src/` pode citar.
PUBLISH_ENDPOINTS = ("/api/social", "upload-post", "open.tiktokapis.com", "upload/youtube",
                     "graph.facebook.com", "videos.insert")
# Clientes HTTP com lista fechada (R12).
YOUTUBE_RECURSOS = {"channels", "playlistItems", "videos", "search"}
OPENSHORTS_PROIBIDOS = ("/api/social", "/api/thumbnail/publish", "/api/saasshorts/post")

API_DIR = Path(__file__).resolve().parents[2]
PYPROJECT = API_DIR / "pyproject.toml"
SRC = API_DIR / "src" / "sociman_api"


def _norm(value: str) -> str:
    # post_to, postTo e post-to caem todos em "post-to".
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    return value.lower().replace("_", "-")


def test_nenhuma_rota_de_publicacao():
    offenders = []
    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            text = f"{_norm(path)} {_norm(op.get('operationId', ''))}"
            hits = [t for t in PUBLISH_TERMS if t in text]
            if hits:
                offenders.append(f"{method.upper()} {path}: {hits}")
    assert not offenders, f"rotas violam o princípio I: {offenders}"


def test_nenhum_sdk_de_rede_social():
    data = tomllib.loads(PYPROJECT.read_text())
    deps = list(data["project"].get("dependencies", []))
    for group in data["project"].get("optional-dependencies", {}).values():
        deps += group
    for group in data.get("dependency-groups", {}).values():
        deps += [d for d in group if isinstance(d, str)]
    offenders = [d for d in deps if any(sdk in d.lower() for sdk in SOCIAL_SDKS)]
    assert not offenders, f"dependências violam o princípio I: {offenders}"


# ---- spec 006 ----

def _fontes() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _strings_de_codigo(tree: ast.AST) -> list[str]:
    """Os literais de texto do módulo, menos as docstrings (que podem citar o que é proibido)."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = node.body[0] if node.body else None
            if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant):
                docstrings.add(id(doc.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


def test_codigo_fonte_sem_endpoint_de_publicacao():
    """Nenhum literal do código (fora docstrings e comentários) cita endpoint de publicação.
    Uma lista de proibidos, se houver, fica nos testes, nunca em `src/`."""
    offenders = []
    for path in _fontes():
        for texto in _strings_de_codigo(ast.parse(path.read_text())):
            offenders += [f"{path.relative_to(SRC)}: {t}" for t in PUBLISH_ENDPOINTS
                          if t in texto]
    assert not offenders, f"código cita endpoint de publicação (princípio I): {offenders}"


def test_varredura_pega_literal_e_ignora_docstring():
    codigo = '"""Nunca /api/social."""\nURL = "/api/social/post"\n'
    assert _strings_de_codigo(ast.parse(codigo)) == ["/api/social/post"]


def _entradas(allowed) -> list[str]:
    """`ALLOWED` como texto por entrada, seja ("GET", "channels"), "GET channels" ou dict."""
    items = allowed.items() if isinstance(allowed, dict) else allowed
    out = []
    for item in items:
        if isinstance(item, (tuple, list)):
            out.append(" ".join(str(p) for p in item))
        else:
            out.append(str(item))
    return out


def test_youtube_so_get_em_recursos_de_leitura():
    from sociman_api.canais import youtube

    entradas = _entradas(youtube.ALLOWED)
    assert entradas, "canais.youtube.ALLOWED vazio"
    for entrada in entradas:
        metodos = set(re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\b", entrada.upper()))
        assert metodos <= {"GET"}, f"YouTube só com GET (princípio I): {entrada}"
        recurso = re.findall(r"[A-Za-z]+", entrada.replace("GET", " "))
        assert recurso and recurso[-1] in YOUTUBE_RECURSOS, f"recurso fora da lista: {entrada}"


def test_openshorts_sem_rotas_de_publicacao():
    from sociman_api.envios import openshorts

    entradas = _entradas(openshorts.ALLOWED)
    assert entradas, "envios.openshorts.ALLOWED vazio"
    offenders = [e for e in entradas for p in OPENSHORTS_PROIBIDOS if p in e]
    assert not offenders, f"OpenShorts com rota de publicação (princípio I): {offenders}"


def _e_postado(node: ast.AST) -> bool:
    """`EstadoPostagem.postado` (ou `….postado` de qualquer import dele) ou "postado" literal."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "postado":
            base = sub.value
            nome = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            if nome == "EstadoPostagem":
                return True
        if isinstance(sub, ast.Constant) and sub.value == "postado":
            return True
    return False


def _alvo_estado(target: ast.AST) -> bool:
    return (isinstance(target, ast.Attribute) and target.attr == "estado") or (
        isinstance(target, ast.Name) and target.id == "estado")


def _atribuicoes_de_postado(tree: ast.AST) -> list[tuple[int, str]]:
    """(linha, função) de cada lugar que ATRIBUI `postado` a um estado: `x.estado = …`,
    `estado=…` como argumento, `{"estado": …}` e `.values(estado=…)`. Comparar não conta."""
    achados: list[tuple[int, str]] = []

    def visitar(node: ast.AST, funcao: str) -> None:
        for filho in ast.iter_child_nodes(node):
            nome = filho.name if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                else funcao
            if isinstance(filho, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                alvos = filho.targets if isinstance(filho, ast.Assign) else [filho.target]
                if filho.value is not None and any(_alvo_estado(t) for t in alvos) \
                        and _e_postado(filho.value):
                    achados.append((filho.lineno, nome))
            if isinstance(filho, ast.keyword) and filho.arg == "estado" \
                    and _e_postado(filho.value):
                achados.append((filho.value.lineno, nome))
            if isinstance(filho, ast.Dict):
                for k, v in zip(filho.keys, filho.values, strict=True):
                    if isinstance(k, ast.Constant) and k.value == "estado" and _e_postado(v):
                        achados.append((v.lineno, nome))
            visitar(filho, nome)

    visitar(tree, "<módulo>")
    return achados


def test_postado_so_por_acao_humana():
    """Por AST: só `postagem/service.py::marcar_postado` atribui `postado` (princípio I)."""
    permitido = ("postagem/service.py", "marcar_postado")
    achados = []
    for path in _fontes():
        rel = str(path.relative_to(SRC))
        for linha, funcao in _atribuicoes_de_postado(ast.parse(path.read_text())):
            achados.append((rel, funcao, linha))
    fora = [a for a in achados if (a[0], a[1]) != permitido]
    assert not fora, f"`postado` atribuído fora da ação humana (princípio I): {fora}"
    # O guarda está vivo: a atribuição permitida existe e é encontrada.
    assert any((a[0], a[1]) == permitido for a in achados)


def test_guarda_do_postado_pega_os_jeitos_de_atribuir():
    codigo = """
def job(p, db):
    p.estado = EstadoPostagem.postado
    db.execute(update(Postagem).values(estado="postado"))
    Postagem(estado=m.EstadoPostagem.postado)
    x = {"estado": "postado"}
    if p.estado == EstadoPostagem.postado:
        pass
"""
    linhas = [linha for linha, _ in _atribuicoes_de_postado(ast.parse(codigo))]
    assert linhas == [3, 4, 5, 6]


def test_listas_do_guarda_nao_encolheram():
    """SC-007: as listas só crescem (valores da 001 e da 006)."""
    assert set(PUBLISH_TERMS) >= {"publish", "post-to", "upload-to", "share", "tiktok",
                                  "youtube", "instagram"}
    assert set(SOCIAL_SDKS) >= {"tiktok", "google-api-python-client", "instagrapi", "facebook",
                                "tweepy"}


# ---- spec 008 (assistente de IA) ----

def _rotas_ia() -> list[tuple[str, str, str]]:
    return [(method.upper(), path, op.get("operationId", ""))
            for path, ops in app.openapi()["paths"].items() if path.startswith("/api/ia/")
            for method, op in ops.items()]


def test_rotas_da_ia_sem_termos_de_publicacao_e_com_operation_id_ia():
    rotas = _rotas_ia()
    assert rotas, "nenhuma rota /api/ia/* no OpenAPI"
    for method, path, op_id in rotas:
        assert op_id.startswith("ia_"), f"{method} {path}: operationId {op_id!r}"
        texto = f"{_norm(path)} {_norm(op_id)}"
        assert not [t for t in PUBLISH_TERMS if t in texto], f"{method} {path} ({op_id})"


def test_rotas_da_ia_sem_delete():
    assert not [r for r in _rotas_ia() if r[0] == "DELETE"]


def test_cliente_da_ia_nao_envia_tools():
    """O assistente só devolve texto: a chamada ao Claude nunca leva `tools` (princípio I)."""
    from fakes.anthropic_fake import AnthropicFake

    from sociman_api.ia.contexto import Contexto, PerfilBloco
    from sociman_api.ia.prompt import montar_system, montar_user
    from sociman_api.ia.tipos import TIPOS

    fake = AnthropicFake()
    ctx = Contexto(perfil=PerfilBloco(nome="Perfil"))
    for tipo in TIPOS.values():
        fake.ia_client().gerar(tipo, montar_system(tipo, tipo.padrao, ctx),
                               lambda erro, t=tipo: montar_user(t, ctx, {}, "", erro_anterior=erro))
    assert len(fake.bodies) >= len(TIPOS)
    assert all("tools" not in b and "tool_choice" not in b for b in fake.bodies)
