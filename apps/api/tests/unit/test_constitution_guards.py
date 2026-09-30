"""Guarda do princípio I da constitution: publicação só com decisão humana.

As listas só crescem; exceções só por pasta de `publicacao/`, uma por rede, criada por spec
(a 015 criou a da TikTok: `PERMITIDO_EM`).
O princípio II (direito primeiro) tem teste próprio desde a spec 006, que absorveu a 008
(`tests/integration/test_direito.py`).
"""

import ast
import re
import tomllib
from collections.abc import Callable
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
# Spec 015 (R16.1): o único endpoint liberado, e só na pasta do executor da rede.
PERMITIDO_EM = {"open.tiktokapis.com": "publicacao/tiktok/"}

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


def _permitido(rel: str, endpoint: str) -> bool:
    pasta = PERMITIDO_EM.get(endpoint)
    return pasta is not None and rel.startswith(pasta)


def test_codigo_fonte_sem_endpoint_de_publicacao():
    """Nenhum literal do código (fora docstrings e comentários) cita endpoint de publicação,
    salvo a exceção por pasta de `PERMITIDO_EM` (spec 015, R16.1). Uma lista de proibidos, se
    houver, fica nos testes, nunca em `src/`."""
    offenders = []
    for path in _fontes():
        rel = str(path.relative_to(SRC))
        for texto in _strings_de_codigo(ast.parse(path.read_text())):
            offenders += [f"{rel}: {t}" for t in PUBLISH_ENDPOINTS
                          if t in texto and not _permitido(rel, t)]
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


# Enums de estado do destino (a `EstadoPostagem` da 006 virou `DestinoEstado` na 014).
ESTADO_ENUMS = ("EstadoPostagem", "DestinoEstado")


def _e_valor(node: ast.AST, valores: tuple[str, ...]) -> bool:
    """`DestinoEstado.<valor>` (ou `….<valor>` de qualquer import dele) ou o literal."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr in valores:
            base = sub.value
            nome = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            if nome in ESTADO_ENUMS:
                return True
        if isinstance(sub, ast.Constant) and sub.value in valores:
            return True
    return False


def _e_postado(node: ast.AST) -> bool:
    """`EstadoPostagem.postado`/`DestinoEstado.postado` ou "postado" literal."""
    return _e_valor(node, ("postado",))


def _alvo_estado(target: ast.AST) -> bool:
    return (isinstance(target, ast.Attribute) and target.attr == "estado") or (
        isinstance(target, ast.Name) and target.id == "estado")


def _atribuicoes_de_postado(tree: ast.AST) -> list[tuple[int, str]]:
    """(linha, função) de cada lugar que ATRIBUI `postado` a um estado: `x.estado = …`,
    `estado=…` como argumento, `{"estado": …}` e `.values(estado=…)`. Comparar não conta."""
    return _atribuicoes(tree, _e_postado)


def _atribuicoes(tree: ast.AST, casa: Callable[[ast.AST], bool]) -> list[tuple[int, str]]:
    achados: list[tuple[int, str]] = []

    def visitar(node: ast.AST, funcao: str) -> None:
        for filho in ast.iter_child_nodes(node):
            nome = filho.name if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                else funcao
            if isinstance(filho, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                alvos = filho.targets if isinstance(filho, ast.Assign) else [filho.target]
                if filho.value is not None and any(_alvo_estado(t) for t in alvos) \
                        and casa(filho.value):
                    achados.append((filho.lineno, nome))
            if isinstance(filho, ast.keyword) and filho.arg == "estado" \
                    and casa(filho.value):
                achados.append((filho.value.lineno, nome))
            if isinstance(filho, ast.Dict):
                for k, v in zip(filho.keys, filho.values, strict=True):
                    if isinstance(k, ast.Constant) and k.value == "estado" and casa(v):
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
    assert set(PUBLISH_ENDPOINTS) >= {"/api/social", "upload-post", "open.tiktokapis.com",
                                      "upload/youtube", "graph.facebook.com", "videos.insert"}


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


# ---- spec 014 (central de conteúdos) ----

RECURSOS_014 = ("/api/conteudos", "/api/destinos", "/api/agendamentos")
OPERATION_PREFIXOS_014 = ("conteudos_", "destinos_", "agendamentos_")
# Estados que só a trilha da 015 grava (R16.4): o único lugar é `_concluir` da trilha.
ESTADOS_015 = ("rascunho_criado", "publicado", "falhou")
ESTADOS_015_PERMITIDOS = {("publicacao/trilha.py", "_concluir")}
# Spec 016 (guarda 4, R12): o vínculo com o post move `rascunho_criado ↔ publicado` e
# `falhou → publicado`, só por esta função.
ESTADOS_015_PERMITIDOS |= {("postagem/service.py", "publicacao_pelo_vinculo")}
# `enviando` só ao reivindicar (spec 015, R16.4).
ENVIANDO_PERMITIDO = {("publicacao/trilha.py", "_reivindicar")}


def _rotas_014() -> list[tuple[str, str, str]]:
    return [(method.upper(), path, op.get("operationId", ""))
            for path, ops in app.openapi()["paths"].items()
            if path.startswith(RECURSOS_014)
            for method, op in ops.items()]


def test_rotas_da_014_com_operation_id_do_recurso_e_sem_delete():
    """Guarda 1: `conteudos_*`, `destinos_*` ou `agendamentos_*`; nenhuma DELETE."""
    rotas = _rotas_014()
    assert rotas, "nenhuma rota /api/conteudos, /api/destinos ou /api/agendamentos no OpenAPI"
    for method, path, op_id in rotas:
        assert method != "DELETE", f"{method} {path}: não existe DELETE no domínio"
        assert op_id.startswith(OPERATION_PREFIXOS_014), f"{method} {path}: {op_id!r}"


def _e_estado_015(node: ast.AST) -> bool:
    return _e_valor(node, ESTADOS_015)


def _lugares(casa: Callable[[ast.AST], bool]) -> list[tuple[str, str, int]]:
    achados = []
    for path in _fontes():
        rel = str(path.relative_to(SRC))
        for linha, funcao in _atribuicoes(ast.parse(path.read_text()), casa):
            achados.append((rel, funcao, linha))
    return achados


def test_estados_da_015_nunca_atribuidos():
    """Guarda 5 (R16.4): por AST, só `publicacao/trilha.py::_concluir` atribui
    `rascunho_criado`, `publicado` ou `falhou` a um estado."""
    achados = _lugares(_e_estado_015)
    fora = [a for a in achados if (a[0], a[1]) not in ESTADOS_015_PERMITIDOS]
    assert not fora, f"estado da execução atribuído fora da trilha (princípio I): {fora}"
    # Guarda vivo: cada lugar permitido existe e é encontrado (a trilha e o vínculo da 016).
    assert {(a[0], a[1]) for a in achados} >= ESTADOS_015_PERMITIDOS


def test_enviando_so_ao_reivindicar():
    """R16.4: `enviando` só é atribuído em `publicacao/trilha.py::_reivindicar`."""
    achados = _lugares(lambda n: _e_valor(n, ("enviando",)))
    fora = [a for a in achados if (a[0], a[1]) not in ENVIANDO_PERMITIDO]
    assert not fora, f"`enviando` atribuído fora da reivindicação (princípio I): {fora}"
    assert any((a[0], a[1]) in ENVIANDO_PERMITIDO for a in achados)  # guarda vivo


def test_guarda_dos_estados_015_pega_os_jeitos_de_atribuir():
    codigo = """
def executor(p, db):
    p.estado = DestinoEstado.publicado
    db.execute(update(Postagem).values(estado="falhou"))
    Postagem(estado=m.DestinoEstado.rascunho_criado)
    corte.status = CorteStatus.falhou
    if p.estado == DestinoEstado.publicado:
        pass
"""
    linhas = [linha for linha, _ in _atribuicoes(ast.parse(codigo), _e_estado_015)]
    assert linhas == [3, 4, 5]


def test_agendador_sem_trilha_nova():
    """Guarda 6 (R16.6): as trilhas novas são a `publicacao` da 015 e a `metricas` da 016 (a
    lista só cresce por spec; guarda 5 da 016)."""
    from sociman_api.agendador import trilhas_padrao

    assert {t.nome for t in trilhas_padrao()} == {"sync", "openshorts", "importacao",
                                                  "lembretes", "publicacao", "metricas"}


# ---- spec 015 (publicação no TikTok), parte 1: R16.1, R16.2, R16.3 e R16.8 ----

# Exatamente os pedidos de R21 (a lista do cliente não cresce sem spec).
TIKTOK_ALLOWED_R21 = {
    ("POST", "/v2/oauth/token/"),
    ("POST", "/v2/oauth/revoke/"),
    ("GET", "/v2/user/info/"),
    ("POST", "/v2/post/publish/creator_info/query/"),
    ("POST", "/v2/post/publish/inbox/video/init/"),
    ("POST", "/v2/post/publish/video/init/"),
    ("POST", "/v2/post/publish/status/fetch/"),
    ("PUT", "<upload_url>"),
    ("GET", "<avatar>"),
}
PUBLICACAO = SRC / "publicacao"
# Spec 016 (R2, guarda 1): só leitura, exatamente estes dois (a lista só cresce por spec).
LEITURA_016_ESPERADA = {
    ("POST", "/v2/video/list/"),
    ("POST", "/v2/video/query/"),
}


def test_permitido_em_so_libera_a_pasta_da_rede():
    """R16.1: a exceção é por pasta de `publicacao/` e só para o endpoint da própria rede."""
    assert all(pasta.startswith("publicacao/") and pasta.endswith("/")
               for pasta in PERMITIDO_EM.values())
    assert set(PERMITIDO_EM) <= set(PUBLISH_ENDPOINTS)  # a lista de proibidos não encolhe
    assert _permitido("publicacao/tiktok/cliente.py", "open.tiktokapis.com")
    assert not _permitido("publicacao/trilha.py", "open.tiktokapis.com")
    assert not _permitido("config.py", "open.tiktokapis.com")
    assert not _permitido("publicacao/tiktok/cliente.py", "graph.facebook.com")
    # O guarda está vivo: o endpoint aparece (só) no cliente da TikTok.
    usos = [str(p.relative_to(SRC)) for p in _fontes()
            if any("open.tiktokapis.com" in t
                   for t in _strings_de_codigo(ast.parse(p.read_text())))]
    assert usos == ["publicacao/tiktok/cliente.py"]


def _importa(tree: ast.AST, modulo: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == modulo or a.name.startswith(f"{modulo}.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == modulo or node.module.startswith(f"{modulo}."):
                return True
            if node.module == modulo.rsplit(".", 1)[0] and any(
                    a.name == modulo.rsplit(".", 1)[1] for a in node.names):
                return True
    return False


def test_so_o_registro_importa_o_executor_da_rede():
    """R16.2: nenhum módulo fora de `publicacao/` importa `publicacao.tiktok`, e dentro de
    `publicacao/` só `registro.py` (a pasta da própria rede se importa à vontade)."""
    permitidos = {PUBLICACAO / "registro.py"}
    fora = []
    for path in _fontes():
        if path.is_relative_to(PUBLICACAO / "tiktok") or path in permitidos:
            continue
        if _importa(ast.parse(path.read_text()), "sociman_api.publicacao.tiktok"):
            fora.append(str(path.relative_to(SRC)))
    assert not fora, f"importam publicacao.tiktok fora do registro (princípio I): {fora}"
    assert _importa(ast.parse((PUBLICACAO / "registro.py").read_text()),
                    "sociman_api.publicacao.tiktok")


def test_guarda_de_import_pega_os_jeitos_de_importar():
    m = "sociman_api.publicacao.tiktok"
    for codigo in ("import sociman_api.publicacao.tiktok.cliente",
                   "from sociman_api.publicacao.tiktok.cliente import ALLOWED",
                   "from sociman_api.publicacao import tiktok",
                   "from sociman_api.publicacao.tiktok import oauth"):
        assert _importa(ast.parse(codigo), m), codigo
    assert not _importa(ast.parse("from sociman_api.publicacao import registro"), m)


def test_cliente_da_tiktok_com_lista_fechada_do_r21():
    """R16.3: `ALLOWED` exatamente igual ao de R21 mais a leitura da 016 (guarda 1 da 016);
    nada fora dele sai do cliente."""
    from sociman_api.publicacao.tiktok import cliente

    assert set(cliente.ALLOWED) == TIKTOK_ALLOWED_R21 | LEITURA_016_ESPERADA
    assert set(cliente.LEITURA_016) == LEITURA_016_ESPERADA
    assert cliente.UPLOAD_SUFIXO == ".tiktokapis.com"
    assert set(cliente.CDN_SUFIXOS) == {".tiktokcdn.com", ".tiktokcdn-us.com"}


def test_config_sem_url_da_tiktok():
    """R16.1: o endereço padrão da API fica no cliente, não no `config.py`."""
    from sociman_api.config import Settings

    padroes = [str(f.default) for f in Settings.model_fields.values()]
    assert not [p for p in padroes if "tiktok" in p.lower() and "://" in p]


# ---- spec 015, parte 3: R16.5 (rotas) ----

# As rotas **H** do contrato (dono humano): nenhuma pode virar tool do MCP (009).
ROTAS_H_015 = {"conexoes_iniciar", "conexoes_retorno", "conexoes_desconectar",
               "conexoes_criador", "publicacao_config_update", "destinos_tentar_de_novo",
               "destinos_confirmar_envio", "destinos_enviar_agora"}
OPERATION_PREFIXOS_015 = ("conexoes_", "publicacao_config_", "destinos_")


def _rotas_resolvidas(rotas) -> list:
    """As `APIRoute` de verdade: o FastAPI 0.141 embrulha os routers incluídos em
    `_IncludedRouter` (armadilha 16), por isso a busca desce em `original_router`."""
    out = []
    for r in rotas:
        if hasattr(r, "original_router"):
            out += _rotas_resolvidas(r.original_router.routes)
        elif hasattr(r, "dependant"):
            out.append(r)
        elif hasattr(r, "routes"):
            out += _rotas_resolvidas(r.routes)
    return out


def _chamadas(dependant) -> set:
    calls = set()
    for d in dependant.dependencies:
        calls.add(d.call)
        calls |= _chamadas(d)
    return calls


def test_rotas_h_exigem_dono_humano():
    """R16.5: toda rota **H** tem `require_human_owner` na árvore de dependências, e as rotas
    da 015 seguem os prefixos neutros (sem `tiktok`/`publish`, que o guarda geral confere)."""
    from sociman_api.auth.deps import require_human_owner

    por_op = {r.operation_id: r for r in _rotas_resolvidas(app.routes)
              if getattr(r, "operation_id", None)}
    assert ROTAS_H_015 <= set(por_op), ROTAS_H_015 - set(por_op)
    sem = [op for op in sorted(ROTAS_H_015) if require_human_owner not in _chamadas(
        por_op[op].dependant)]
    assert not sem, f"rotas H sem RequireHumanOwner (princípio I): {sem}"
    assert all(op.startswith(OPERATION_PREFIXOS_015) for op in ROTAS_H_015)
    # O guarda está vivo: a leitura (User) não exige dono humano.
    assert require_human_owner not in _chamadas(por_op["publicacao_config_get"].dependant)


def test_rotas_da_015_sem_delete():
    metodos = {(m.upper(), path) for path, ops in app.openapi()["paths"].items()
               for m, op in ops.items()
               if op.get("operationId", "").startswith(("conexoes_", "publicacao_config_"))}
    assert metodos and not [m for m in metodos if m[0] == "DELETE"]


def test_httpx_na_publicacao_so_na_pasta_da_rede():
    """T092: dentro de `publicacao/`, só a pasta da rede fala HTTP; a parte genérica recebe o
    cliente pelo registro."""
    fora = [str(p.relative_to(SRC)) for p in sorted(PUBLICACAO.glob("*.py"))
            if _importa(ast.parse(p.read_text()), "httpx")]
    assert not fora, f"httpx fora de publicacao/<rede>/: {fora}"


# ---- spec 016 (métricas do TikTok): guardas 2 e 3 (o 1 está no teste da lista fechada) ----

METRICAS = SRC / "metricas"
LEITOR = PUBLICACAO / "tiktok" / "leitor.py"
# `metricas/` só chega a `publicacao/` por estes módulos (o `legenda` é texto puro: a legenda
# que o SociMan manda, usada no casamento, R10). Nunca a rede, a trilha, o service nem o executor.
PUBLICACAO_PARA_METRICAS = {"registro", "conexoes", "models", "limites", "legenda"}
PUBLICACAO_PROIBIDA_EM_METRICAS = {"tiktok", "trilha", "service", "executor"}
CHAMADAS_DE_ENVIO = {"put_parte", "iniciar", "enviar_parte"}
CAMINHOS_DO_LEITOR = {c for _, c in LEITURA_016_ESPERADA} | {
    "/v2/user/info/", "/v2/post/publish/status/fetch/"}


def _modulos_de_publicacao(tree: ast.AST) -> set[str]:
    """Os submódulos de `sociman_api.publicacao` que o código importa (`registro`, …)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("sociman_api.publicacao."):
                    out.add(a.name.split(".")[2])
                elif a.name == "sociman_api.publicacao":
                    out.add("")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "sociman_api.publicacao":
                out |= {a.name for a in node.names}
            elif node.module.startswith("sociman_api.publicacao."):
                out.add(node.module.split(".")[2])
    return out


def _fontes_metricas() -> list[Path]:
    return sorted(METRICAS.rglob("*.py"))


def test_metricas_chega_a_publicacao_so_pelo_registro():
    """Guarda 2 (R2): `metricas/` não importa a rede, a trilha, o service nem o executor de
    publicação; só `registro`, `conexoes`, `models`, `limites` (e `legenda`). E não fala HTTP."""
    fontes = _fontes_metricas()
    assert fontes and (METRICAS / "models.py") in fontes  # o guarda está vivo
    fora, proibidos, http = [], [], []
    for path in fontes:
        tree = ast.parse(path.read_text())
        rel = str(path.relative_to(SRC))
        mods = _modulos_de_publicacao(tree)
        fora += [f"{rel}: publicacao.{m}" for m in mods - PUBLICACAO_PARA_METRICAS]
        proibidos += [f"{rel}: publicacao.{m}" for m in mods & PUBLICACAO_PROIBIDA_EM_METRICAS]
        if _importa(tree, "httpx"):
            http.append(rel)
    assert not proibidos, f"metricas/ importa a publicação (princípio I): {proibidos}"
    assert not fora, f"metricas/ importa publicação fora da lista: {fora}"
    assert not http, f"metricas/ fala HTTP (só o leitor da rede fala): {http}"
    assert not PUBLICACAO_PARA_METRICAS & PUBLICACAO_PROIBIDA_EM_METRICAS


def test_guarda_de_import_da_016_pega_os_jeitos_de_importar():
    for codigo, esperado in (
        ("from sociman_api.publicacao import registro, trilha", {"registro", "trilha"}),
        ("import sociman_api.publicacao.executor", {"executor"}),
        ("from sociman_api.publicacao.tiktok.leitor import LeitorTikTok", {"tiktok"}),
        ("from sociman_api.publicacao.service import x", {"service"}),
        ("from sociman_api.metricas import models", set()),
    ):
        assert _modulos_de_publicacao(ast.parse(codigo)) == esperado, codigo


def _chamadas_de_envio(tree: ast.AST) -> list[tuple[int, str]]:
    """`x.iniciar(`, `x.enviar_parte(`, `x.put_parte(` e qualquer menção a `put_parte`."""
    achados = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in CHAMADAS_DE_ENVIO:
            achados.append((node.lineno, node.func.attr))
        elif isinstance(node, ast.Name) and node.id in CHAMADAS_DE_ENVIO:
            achados.append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute) and node.attr == "put_parte":
            achados.append((node.lineno, node.attr))
    return sorted(set(achados))


def test_metricas_e_leitor_sem_chamada_de_envio():
    """Guarda 3 (R2): nada de `iniciar`, `enviar_parte` nem `put_parte` em `metricas/` nem no
    leitor; o leitor só cita os caminhos de leitura."""
    alvos = [*_fontes_metricas(), LEITOR]
    assert LEITOR.exists()
    achados = [(str(p.relative_to(SRC)), *a) for p in alvos
               for a in _chamadas_de_envio(ast.parse(p.read_text()))]
    assert not achados, f"chamada de envio na leitura (princípio I): {achados}"
    caminhos = {t for t in _strings_de_codigo(ast.parse(LEITOR.read_text()))
                if t.startswith("/v2/")}
    assert caminhos, "o leitor não cita nenhum caminho (guarda morto)"
    assert caminhos <= CAMINHOS_DO_LEITOR, caminhos - CAMINHOS_DO_LEITOR
    assert "open.tiktokapis.com" not in LEITOR.read_text()  # o host fica só no cliente


def test_guarda_de_envio_da_016_pega_os_jeitos_de_chamar():
    codigo = """
def f(ex, c, ctx):
    ex.iniciar(ctx, t, None)
    ex.enviar_parte(ctx, t, "u", 0, 0, b"")
    c.put_parte("u", b"", 0, 1)
    g = c.put_parte
    ex.consultar(ctx, t)
"""
    assert [linha for linha, _ in _chamadas_de_envio(ast.parse(codigo))] == [3, 4, 5, 6]
