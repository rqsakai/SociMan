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
    """Guarda 6 (R16.6): as trilhas novas são a `publicacao` da 015, a `metricas` da 016, a
    `aprendizado` da 023, a `geracao_limpeza` da 021 (R12) e a `mercado` da 026 (a lista só
    cresce por spec)."""
    from sociman_api.agendador import trilhas_padrao

    assert {t.nome for t in trilhas_padrao()} == {"sync", "openshorts", "importacao",
                                                  "lembretes", "publicacao", "metricas",
                                                  "aprendizado", "geracao_limpeza", "mercado"}


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


# ---- spec 017 (guia de comunicação) ----

OPERATIONS_017 = {"guias_perfil_get", "guias_perfil_update", "guias_perfil_versions",
                  "guias_perfil_revert", "guias_conta_get", "guias_conta_update",
                  "guias_conta_versions", "guias_conta_revert", "ia_guia_montar",
                  "ia_guia_testar"}
FONTES_017 = ("ia/guia.py", "ia/service_guia.py", "ia/router_guia.py", "ia/schemas_guia.py")


def _rotas_017() -> dict[str, tuple[str, str]]:
    """operationId → (método, caminho) das rotas do guia e do montar/testar."""
    return {op["operationId"]: (m.upper(), path)
            for path, ops in app.openapi()["paths"].items() for m, op in ops.items()
            if op.get("operationId", "").startswith(("guias_", "ia_guia_"))}


def test_rotas_da_017_neutras_e_sem_delete():
    """Os caminhos e `operationId` do guia passam pelo guarda geral (sem `publish`, `tiktok`…),
    seguem os prefixos neutros e nenhum caminho com `guia` aceita DELETE (limpar = salvar
    vazio)."""
    rotas = _rotas_017()
    assert set(rotas) == OPERATIONS_017, set(rotas) ^ OPERATIONS_017
    for op, (_, path) in rotas.items():
        texto = f"{_norm(path)} {_norm(op)}"
        assert not [t for t in PUBLISH_TERMS if t in texto], (op, path)
        assert path.startswith(("/api/perfis/{", "/api/contas/{", "/api/ia/guia/")), path
    delete = [(m, p) for p, ops in app.openapi()["paths"].items() for m in ops
              if "guia" in p and m.upper() == "DELETE"]
    assert not delete, delete


def test_modulos_do_guia_nao_importam_a_publicacao():
    fontes = [SRC / f for f in FONTES_017]
    assert all(p.exists() for p in fontes), [str(p) for p in fontes if not p.exists()]
    achados = {str(p.relative_to(SRC)): mods for p in fontes
               if (mods := _modulos_de_publicacao(ast.parse(p.read_text())))}
    assert not achados, f"o guia importa a publicação (princípio I): {achados}"


# ---- spec 019 (analytics de decisão): só leitura ----

ANALYTICS = SRC / "analytics"
OPERATIONS_019 = {"analytics_visao_geral", "analytics_quando_postar", "analytics_o_que_funciona",
                  "analytics_curvas", "analytics_contas", "analytics_funil", "analytics_mercado",
                  "analytics_alertas"}
# R12: nada de rede, HTTP, serviços que mudam estado nem histórico.
IMPORTS_PROIBIDOS_019 = ("sociman_api.publicacao", "httpx", "sociman_api.postagem.service",
                         "sociman_api.envios.service_envios", "sociman_api.cortes.service",
                         "sociman_api.history")
# `.add(`/`.delete(` só contam na sessão (`db.add`, `session.delete`): `set.add` é leitura.
ESCRITAS_ORM = {"add_all", "flush", "commit", "merge", "bulk_save_objects"}
ESCRITAS_SESSAO = {"add", "delete"}
SESSOES = {"db", "session", "sessao", "s"}
ESCRITAS_SQL = {"update", "insert", "delete"}
_SQL_ESCRITA = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|TRUNCATE)\b",
                          re.IGNORECASE)


def _rotas_019() -> dict[str, tuple[str, str]]:
    return {op.get("operationId", ""): (m.upper(), path)
            for path, ops in app.openapi()["paths"].items() for m, op in ops.items()
            if path.startswith("/api/analytics")}


def test_rotas_de_analytics_so_get():
    rotas = _rotas_019()
    assert len(rotas) >= len(OPERATIONS_019)  # o guarda está vivo
    outros = [(m, p) for m, p in rotas.values() if m != "GET"]
    assert not outros, f"analytics com rota que não é GET (princípio I): {outros}"


def test_operation_ids_de_analytics():
    rotas = _rotas_019()
    assert all(op.startswith("analytics_") for op in rotas), sorted(rotas)
    assert OPERATIONS_019 <= set(rotas), OPERATIONS_019 - set(rotas)
    for op, (_, path) in rotas.items():
        texto = f"{_norm(path)} {_norm(op)}"
        assert not [t for t in PUBLISH_TERMS if t in texto], (op, path)


def _nome(node: ast.AST) -> str:
    """`db` em `db.add`, `self.db.add` ou `c.db.add`."""
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else ""


def _escritas(tree: ast.AST) -> list[tuple[int, str]]:
    """`.add(`, `.flush(`, `.commit(`, `.delete(`…, `update(`/`insert(`/`delete(` do SQLAlchemy
    (importados ou chamados) e SQL de escrita em literais (fora das docstrings)."""
    achados = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and (f.attr in ESCRITAS_ORM or (
                    f.attr in ESCRITAS_SESSAO and _nome(f.value) in SESSOES)):
                achados.append((node.lineno, f".{f.attr}("))
            elif isinstance(f, ast.Name) and f.id in ESCRITAS_SQL:
                achados.append((node.lineno, f"{f.id}("))
            elif isinstance(f, ast.Attribute) and f.attr in ESCRITAS_SQL \
                    and isinstance(f.value, ast.Name) and f.value.id in ("sa", "sqlalchemy"):
                achados.append((node.lineno, f"{f.value.id}.{f.attr}("))
        elif isinstance(node, ast.ImportFrom) and node.module and \
                node.module.split(".")[0] == "sqlalchemy":
            achados += [(node.lineno, f"import {a.name}") for a in node.names
                        if a.name in ESCRITAS_SQL]
    for texto in _strings_de_codigo(tree):
        if _SQL_ESCRITA.search(texto):
            achados.append((0, texto.strip()[:40]))
    return sorted(set(achados))


def test_analytics_so_le():
    """R12: `analytics/` não importa publicação, HTTP, serviços que escrevem nem o histórico, e
    não grava (nenhum add/flush/commit/delete nem SQL de escrita)."""
    fontes = sorted(ANALYTICS.rglob("*.py"))
    assert fontes and (ANALYTICS / "router.py") in fontes  # o guarda está vivo
    imports, escritas = [], []
    for path in fontes:
        tree = ast.parse(path.read_text())
        rel = str(path.relative_to(SRC))
        imports += [f"{rel}: {m}" for m in IMPORTS_PROIBIDOS_019 if _importa(tree, m)]
        escritas += [f"{rel}:{linha}: {o}" for linha, o in _escritas(tree)]
    assert not imports, f"analytics/ importa o que escreve ou publica (princípio I): {imports}"
    assert not escritas, f"analytics/ escreve no banco (princípio I): {escritas}"


def test_guarda_da_019_pega_os_jeitos_de_escrever():
    codigo = '''
from sqlalchemy import select, update
import sqlalchemy as sa
def f(db, x):
    db.add(x)
    db.flush()
    db.commit()
    db.delete(x)
    db.execute(update(X).values(a=1))
    db.execute(sa.insert(X))
    db.execute(text("DELETE FROM metricas_videos"))
    db.execute(select(X))
    self.db.add(x)
    vistas = set()
    vistas.add(1)
'''
    tree = ast.parse(codigo)
    assert {o for _, o in _escritas(tree)} == {
        "import update", ".add(", ".flush(", ".commit(", ".delete(", "update(", "sa.insert(",
        "DELETE FROM metricas_videos"}
    assert len([1 for _, o in _escritas(tree) if o == ".add("]) == 2  # `set.add` não conta
    for m, cod in (("sociman_api.publicacao", "from sociman_api.publicacao import conexoes"),
                   ("sociman_api.history", "from sociman_api import history"),
                   ("sociman_api.postagem.service", "from sociman_api.postagem import service"),
                   ("httpx", "import httpx")):
        assert _importa(ast.parse(cod), m), cod
    assert not _escritas(ast.parse('"""UPDATE x SET y: só na docstring."""\nselect(X)\n'))


# ---- spec 009 (servidor MCP) ----

MCP = SRC / "mcp"
ANOTACOES = SRC / "anotacoes"
# T011: o `mcp/` não tem regra de domínio (chama a API pela ponte, FR-011). De `sociman_api`, só
# a infraestrutura, a autoria e os tipos do contrato das versões (`perfis.schemas`).
IMPORTS_PERMITIDOS_009 = ("sociman_api.mcp", "sociman_api.history", "sociman_api.auth",
                          "sociman_api.db", "sociman_api.redis", "sociman_api.config",
                          "sociman_api.errors", "sociman_api.perfis.schemas")
MODELOS_PERMITIDOS_009 = {"sociman_api.mcp.models", "sociman_api.auth.models"}
_SQL_TABELA = re.compile(r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+([a-z_]+)", re.IGNORECASE)


def _imports_sociman(tree: ast.AST) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names if a.name.startswith("sociman_api")}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module \
                and node.module.startswith("sociman_api"):
            out |= {f"{node.module}.{a.name}" if node.module == "sociman_api" else node.module
                    for a in node.names}
    return out


def test_mcp_nao_importa_dominio_nem_publicacao():
    fontes = sorted(MCP.rglob("*.py"))
    assert (MCP / "portao.py") in fontes and (MCP / "servidor.py") in fontes  # vivo
    proibidos = {}
    for path in fontes:
        mods = _imports_sociman(ast.parse(path.read_text()))
        ruins = sorted(m for m in mods if not m.startswith(IMPORTS_PERMITIDOS_009))
        if ruins:
            proibidos[str(path.relative_to(SRC))] = ruins
    assert not proibidos, f"mcp/ importa domínio ou publicação (FR-011, princípio I): {proibidos}"


def test_mcp_so_toca_tabelas_mcp():
    """Modelos só de `mcp.models` (e `auth.models`, para nomes e eventos) e SQL literal só em
    tabelas `mcp_*`."""
    achados = []
    for path in sorted(MCP.rglob("*.py")):
        tree = ast.parse(path.read_text())
        rel = str(path.relative_to(SRC))
        achados += [f"{rel}: {m}" for m in _imports_sociman(tree)
                    if m.endswith(".models") and m not in MODELOS_PERMITIDOS_009]
        for texto in _strings_de_codigo(tree):
            achados += [f"{rel}: {t}" for t in _SQL_TABELA.findall(texto)
                        if not t.lower().startswith("mcp_")]
    assert not achados, f"mcp/ mexe em tabela de domínio: {achados}"


def test_anotacoes_e_mcp_nao_importam_a_publicacao():
    fontes = sorted(ANOTACOES.rglob("*.py")) + sorted(MCP.rglob("*.py"))
    assert (ANOTACOES / "service.py") in fontes
    achados = {str(p.relative_to(SRC)): mods for p in fontes
               if (mods := _modulos_de_publicacao(ast.parse(p.read_text())))}
    assert not achados, f"importa a publicação (princípio I): {achados}"


def test_rotas_da_009_sem_delete_e_nomes_neutros():
    rotas = {(m.upper(), path, op.get("operationId", ""))
             for path, ops in app.openapi()["paths"].items() for m, op in ops.items()
             if path.startswith(("/api/mcp", "/api/anotacoes"))}
    assert len(rotas) >= 22
    assert not [r for r in rotas if r[0] == "DELETE"]
    assert all(op.startswith(("mcp_", "anotacoes_")) for _, _, op in rotas)
    for _, path, op in rotas:
        texto = f"{_norm(path)} {_norm(op)}"
        assert not [t for t in PUBLISH_TERMS if t in texto], (op, path)
    # o endpoint MCP fica fora do OpenAPI (não é rota REST nem vira tool)
    assert "/mcp" not in app.openapi()["paths"]


# ---- spec 020 (histórico do TikTok Studio): só lê arquivos enviados pelo dono ----

STUDIO = SRC / "metricas" / "studio"
OPERATIONS_020 = {"studio_previa", "studio_confirmar", "studio_importacoes", "studio_cobertura",
                  "studio_desfazer"}
# Nada de rede, publicação nem armazenamento de arquivos (os ZIPs nunca são guardados).
IMPORTS_PROIBIDOS_020 = ("sociman_api.publicacao", "httpx", "requests", "urllib.request",
                         "minio", "sociman_api.storage", "sociman_api.datadir")
# Nada extraído nem gravado em disco.
CHAMADAS_DISCO_020 = {"extract", "extractall", "write_bytes", "write_text", "mkdir",
                      "NamedTemporaryFile", "SpooledTemporaryFile", "mkstemp", "TemporaryFile"}
ARQUIVOS_REAIS_020 = ("Overview_*.zip", "Followers_*.zip", "Content_*.zip", "Viewers_*.zip",
                      "Overview.csv", "FollowerHistory.csv", "Content.csv")


def _disco_020(tree: ast.AST) -> list[tuple[int, str]]:
    achados = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        nome = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) \
            else ""
        if nome in CHAMADAS_DISCO_020:
            achados.append((node.lineno, nome))
        elif nome == "open" and isinstance(f, ast.Name):  # o `open` embutido (disco)
            achados.append((node.lineno, "open"))
    return achados


def test_studio_nao_importa_rede_publicacao_nem_storage():
    fontes = sorted(STUDIO.rglob("*.py"))
    assert (STUDIO / "arquivos.py") in fontes and (STUDIO / "router.py") in fontes  # vivo
    achados = [f"{p.relative_to(SRC)}: {m}" for p in fontes
               for m in IMPORTS_PROIBIDOS_020 if _importa(ast.parse(p.read_text()), m)]
    assert not achados, f"metricas/studio/ importa rede, publicação ou storage: {achados}"


def test_studio_nao_extrai_nem_grava_em_disco():
    achados = [f"{p.relative_to(SRC)}:{linha}: {o}" for p in sorted(STUDIO.rglob("*.py"))
               for linha, o in _disco_020(ast.parse(p.read_text()))]
    assert not achados, f"metricas/studio/ toca o disco (R2): {achados}"


def test_guarda_da_020_pega_extract_e_open():
    codigo = "zf.extractall('/tmp')\nzf.extract('a')\nopen('x', 'wb')\nzf.open('Overview.csv')\n"
    assert {o for _, o in _disco_020(ast.parse(codigo))} == {"extractall", "extract", "open"}
    assert _importa(ast.parse("from sociman_api import storage"), "sociman_api.storage")


def test_rotas_do_studio():
    rotas = {op.get("operationId", ""): (m.upper(), path)
             for path, ops in app.openapi()["paths"].items() for m, op in ops.items()
             if "/studio" in path}
    assert set(rotas) == OPERATIONS_020
    assert not [r for r in rotas.values() if r[0] == "DELETE"]
    for op, (_, path) in rotas.items():
        texto = f"{_norm(path)} {_norm(op)}"
        assert not [t for t in PUBLISH_TERMS if t in texto], (op, path)


def test_escritas_do_studio_so_para_dono_humano():
    from sociman_api.auth.deps import require_human_owner, require_user
    from sociman_api.metricas.studio.router import router as studio_router

    def chamadas(dependant) -> set:
        out = set()
        for d in dependant.dependencies:
            out.add(d.call)
            out |= chamadas(d)
        return out

    rotas = [r for r in studio_router.routes if hasattr(r, "dependant")]
    assert len(rotas) == len(OPERATIONS_020)
    for r in rotas:
        deps = chamadas(r.dependant)
        if r.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            assert require_human_owner in deps, r.path
        else:
            assert require_user in deps, r.path


def test_nenhum_arquivo_real_do_studio_na_api():
    achados = [str(p.relative_to(API_DIR)) for padrao in ARQUIVOS_REAIS_020
               for p in API_DIR.rglob(padrao) if ".venv" not in p.parts]
    assert not achados, f"arquivo do TikTok Studio no repositório (privacidade): {achados}"


# ---- spec 010 (cenas): sem rede, sem publicação, reverts de dono humano, histórico ----

CENAS = SRC / "cenas"
IMPORTS_PROIBIDOS_010 = ("sociman_api.publicacao", "httpx", "httpx2", "requests", "urllib",
                         "anthropic")
# Mutações de domínio e o que cada uma usa para gravar o histórico (direto ou pelo `_record`
# do próprio módulo, que chama `history.record`).
MUTACOES_010 = {
    "service.py": ("criar", "editar", "marcar_pronta", "voltar_rascunho", "remontar", "duplicar",
                   "arquivar", "restaurar", "reverter"),
    "tomadas.py": ("registrar_tomada", "escolher", "editar_nota", "arquivar", "restaurar", "reverter"),
    "usos.py": ("definir",),
    "padroes.py": ("salvar", "reverter"),
}
_GRAVA_010 = {"record", "_record", "_record_cena", "_recalcula", "_solta_escolha"}


def _chamadas_010(fn: ast.AST) -> set[str]:
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            out.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return out


def test_cenas_nao_importa_rede_nem_publicacao():
    fontes = sorted(CENAS.rglob("*.py"))
    assert (CENAS / "service.py") in fontes and (CENAS / "tomadas.py") in fontes  # vivo
    achados = [f"{p.relative_to(SRC)}: {m}" for p in fontes
               for m in IMPORTS_PROIBIDOS_010 if _importa(ast.parse(p.read_text()), m)]
    assert not achados, f"cenas/ importa rede ou publicação: {achados}"


def test_rotas_das_cenas_sem_rede_social():
    rotas = [(m.upper(), path, op.get("operationId", ""))
             for path, ops in app.openapi()["paths"].items() for m, op in ops.items()
             if "/cenas" in path]
    assert len(rotas) >= 20 and not [r for r in rotas if r[0] == "DELETE"]
    for _, path, op in rotas:
        assert op.startswith(("cenas_", "conteudos_cenas_")), op
        texto = f"{_norm(path)} {_norm(op)}"
        assert not [t for t in PUBLISH_TERMS if t in texto], (op, path)


def test_reverts_das_cenas_so_dono_humano():
    from sociman_api.auth.deps import require_human_owner
    from sociman_api.cenas.router import router as cenas_router
    from sociman_api.cenas.router_perfil import router as perfil_router

    def chamadas(dependant) -> set:
        out = set()
        for d in dependant.dependencies:
            out.add(d.call)
            out |= chamadas(d)
        return out

    rotas = [r for rt in (cenas_router, perfil_router) for r in rt.routes
             if hasattr(r, "dependant")]
    reverts = [r for r in rotas if r.path.endswith("/revert")]
    assert len(reverts) == 3
    for r in rotas:
        assert (require_human_owner in chamadas(r.dependant)) == (r in reverts), r.path


def test_toda_mutacao_de_cena_grava_historico():
    faltando = []
    for arquivo, funcoes in MUTACOES_010.items():
        tree = ast.parse((CENAS / arquivo).read_text())
        defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for nome in funcoes:
            assert nome in defs, f"{arquivo}:{nome} sumiu (atualize a guarda)"
            if not _chamadas_010(defs[nome]) & _GRAVA_010:
                faltando.append(f"{arquivo}:{nome}")
    assert not faltando, f"mutação sem histórico (princípio VII): {faltando}"


# ---- spec 013 (importação da agência): só lê a pasta da agência, nunca escreve nela ----

AGENCIA = SRC / "agencia"
OPERATIONS_013 = {"agencia_estado", "agencia_previa", "agencia_confirmar",
                  "agencia_importacoes_list", "agencia_importacoes_get", "agencia_desfazer"}
# Rede só pelo service de canais da 006 (resolver e cadastro, com a cota); nada de publicação.
IMPORTS_PROIBIDOS_013 = ("sociman_api.publicacao", "httpx", "requests", "urllib.request",
                         "sociman_api.canais.youtube")
ESCRITA_013 = {"write_text", "write_bytes", "unlink", "rename", "replace", "mkdir", "rmdir",
               "touch", "symlink_to", "chmod", "remove", "makedirs", "removedirs"}


def _escrita_013(tree: ast.AST) -> list[tuple[int, str]]:
    achados = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nomes = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
            if any(n == "shutil" or n.startswith("shutil.") for n in nomes):
                achados.append((node.lineno, "shutil"))
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        nome = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) \
            else ""
        if nome in ESCRITA_013 and not (nome == "replace" and not _e_path_replace(node)):
            achados.append((node.lineno, nome))
        elif nome == "open":
            modo = node.args[1] if len(node.args) > 1 else next(
                (k.value for k in node.keywords if k.arg == "mode"), None)
            if isinstance(f, ast.Attribute) and node.args:  # Path.open(modo)
                modo = node.args[0]
            if modo is None:  # sem modo: leitura
                continue
            texto = modo.value if isinstance(modo, ast.Constant) else None
            if not isinstance(texto, str) or any(c in texto for c in "wax+"):
                achados.append((node.lineno, f"open({texto!r})"))
    return achados


def _e_path_replace(node: ast.Call) -> bool:
    """`Path.replace(destino)`: um argumento posicional e nada mais (o `str.replace` tem dois;
    o `dataclasses.replace`, palavras-chave)."""
    return len(node.args) == 1 and not node.keywords


def test_agencia_nao_importa_rede_nem_publicacao():
    fontes = sorted(AGENCIA.rglob("*.py"))
    assert (AGENCIA / "pastas.py") in fontes and (AGENCIA / "router.py") in fontes  # vivo
    achados = [f"{p.relative_to(SRC)}: {m}" for p in fontes
               for m in IMPORTS_PROIBIDOS_013 if _importa(ast.parse(p.read_text()), m)]
    assert not achados, f"agencia/ importa rede, publicação ou o cliente do YouTube: {achados}"


def test_agencia_nao_escreve_arquivos():
    achados = [f"{p.relative_to(SRC)}:{linha}: {o}" for p in sorted(AGENCIA.rglob("*.py"))
               for linha, o in _escrita_013(ast.parse(p.read_text()))]
    assert not achados, f"agencia/ escreve em disco (FR-004): {achados}"


def test_guarda_da_013_pega_escrita():
    codigo = ("open('x', 'w')\np.open('ab')\np.write_text('x')\np.unlink()\nimport shutil\n"
              "p.open('rb')\nopen('y')\n'a'.replace('a', 'b')\np.replace(q)\n"
              "dataclasses.replace(c, tom='x')\n")
    assert {o for _, o in _escrita_013(ast.parse(codigo))} == {
        "open('w')", "open('ab')", "write_text", "unlink", "shutil", "replace"}


def test_rotas_da_agencia():
    rotas = {op.get("operationId", ""): (m.upper(), path)
             for path, ops in app.openapi()["paths"].items() for m, op in ops.items()
             if path.startswith("/api/agencia")}
    assert set(rotas) == OPERATIONS_013
    assert not [r for r in rotas.values() if r[0] == "DELETE"]
    for op, (_, path) in rotas.items():
        texto = f"{_norm(path)} {_norm(op)}"
        assert not [t for t in PUBLISH_TERMS if t in texto], (op, path)


def test_escritas_da_agencia_so_para_dono_humano():
    from sociman_api.agencia.router import router as agencia_router
    from sociman_api.auth.deps import require_human_owner, require_user

    def chamadas(dependant) -> set:
        out = set()
        for d in dependant.dependencies:
            out.add(d.call)
            out |= chamadas(d)
        return out

    rotas = [r for r in agencia_router.routes if hasattr(r, "dependant")]
    assert len(rotas) == len(OPERATIONS_013)
    for r in rotas:
        deps = chamadas(r.dependant)
        if r.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            assert require_human_owner in deps, r.path
        else:
            assert require_user in deps, r.path


# ---- spec 022 (público do Studio): XLSX pela stdlib, sem rede nem disco ----

IMPORTS_PROIBIDOS_022 = ("sociman_api.publicacao", "httpx", "minio", "openpyxl", "defusedxml",
                         "sociman_api.storage")
ARQUIVOS_REAIS_022 = ("Viewers*.xlsx", "FollowerGender.csv", "FollowerTopTerritories.csv",
                      "FollowerActivity.csv")


def test_planilha_e_publico_nao_importam_rede_nem_leitor_de_xlsx():
    achados = []
    for nome in ("planilha.py", "publico.py"):
        tree = ast.parse((STUDIO / nome).read_text())
        achados += [f"{nome}: {m}" for m in IMPORTS_PROIBIDOS_022 if _importa(tree, m)]
        achados += [f"{nome}:{linha}: {o}" for linha, o in _disco_020(tree)]
    assert not achados, f"spec 022: o XLSX é lido em memória pela stdlib (R2): {achados}"
    tree = ast.parse((SRC / "analytics" / "publico.py").read_text())
    assert not [m for m in IMPORTS_PROIBIDOS_022 if _importa(tree, m)]


def test_planilha_recusa_doctype_antes_do_parser(monkeypatch):
    import io
    import zipfile

    import pytest

    from sociman_api.errors import ApiError
    from sociman_api.metricas.studio import planilha

    vistos: list[bytes] = []
    original = planilha.ET.fromstring

    def espiao(dados):
        vistos.append(dados)
        return original(dados)

    monkeypatch.setattr(planilha.ET, "fromstring", espiao)
    bomba = (b'<?xml version="1.0"?><!DOCTYPE lol [<!ENTITY a "lol"><!ENTITY b "&a;&a;&a;">]>'
             b"<Types>&b;</Types>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", bomba)
        zf.writestr("xl/workbook.xml", b"<workbook/>")
    with pytest.raises(ApiError) as e:
        planilha.ler("x.xlsx", buf.getvalue())
    assert e.value.code == "studio_planilha"
    assert not any(b"<!DOCTYPE" in v for v in vistos)


def test_rota_de_publico_so_le_e_sem_tiktok():
    rotas = _rotas_019()
    assert "analytics_publico" in rotas
    metodo, path = rotas["analytics_publico"]
    assert metodo == "GET"
    assert not [t for t in PUBLISH_TERMS if t in f"{_norm(path)} {_norm('analytics_publico')}"]
    assert "tiktok" not in path.lower()


def test_nenhum_arquivo_real_de_publico_na_api():
    achados = [str(p.relative_to(API_DIR)) for padrao in ARQUIVOS_REAIS_022
               for p in API_DIR.rglob(padrao) if ".venv" not in p.parts]
    assert not achados, f"arquivo de público do TikTok Studio no repositório: {achados}"


# ---- spec 023 (aprendizado): R13 ----

APRENDIZADO = SRC / "aprendizado"
IMPORTS_PROIBIDOS_023 = ("sociman_api.publicacao", "httpx", "sociman_api.postagem.service",
                         "sociman_api.conteudos.agendamento", "sociman_api.envios.service_envios")
# Os módulos só de leitura (o cálculo na leitura) e as funções das rotas GET nos outros.
SO_LEITURA_023 = ("estatistica.py", "fatores.py", "analise.py", "recomendacoes.py",
                  "afinidade.py", "desempenho.py", "diagnostico.py", "constantes.py",
                  "schemas.py")
LEITURAS_023 = {"temas.py": ("listar", "outs", "out", "contagens", "versions"),
                "classificacao.py": ("listar", "out", "versions", "n_pendentes", "usadas_hoje",
                                     "pendentes_stmt", "_resumos"),
                "preferencias.py": ("obter", "efetivas", "out", "versions", "decisao_out",
                                    "linha", "taxonomia_versao"),
                "analise_ia.py": ("listar", "obter", "out", "estimativa", "escolher",
                                  "estimar_escolha")}


def _rotas_023() -> dict[str, tuple[str, str]]:
    return {op["operationId"]: (m.upper(), path)
            for path, ops in app.openapi()["paths"].items() for m, op in ops.items()
            if op.get("operationId", "").startswith("aprendizado_")}


def test_aprendizado_nao_importa_publicacao_nem_rede():
    """Guarda 1: `aprendizado/` não importa publicação, HTTP nem os serviços que mudam destino,
    agenda ou envio (princípio I)."""
    fontes = sorted(APRENDIZADO.rglob("*.py"))
    assert fontes and (APRENDIZADO / "router.py") in fontes  # o guarda está vivo
    achados = [f"{p.relative_to(SRC)}: {m}" for p in fontes for m in IMPORTS_PROIBIDOS_023
               if _importa(ast.parse(p.read_text()), m)]
    assert not achados, f"aprendizado/ importa o que publica ou agenda: {achados}"


def test_rotas_do_aprendizado_sem_delete_e_sem_rede():
    """Guarda 2: nenhuma rota `aprendizado_*` é DELETE nem cita a rede."""
    rotas = _rotas_023()
    assert len(rotas) >= 30  # o guarda está vivo
    assert not [r for r in rotas.values() if r[0] == "DELETE"]
    for op, (_, path) in rotas.items():
        texto = f"{_norm(path)} {_norm(op)}"
        assert not [t for t in PUBLISH_TERMS if t in texto], (op, path)


def test_escritas_do_aprendizado_exigem_dono_humano():
    """Guarda 3: toda rota que não é GET depende de `require_human_owner`; os GETs, não."""
    from sociman_api.auth.deps import require_human_owner

    por_op = {r.operation_id: r for r in _rotas_resolvidas(app.routes)
              if (getattr(r, "operation_id", None) or "").startswith("aprendizado_")}
    rotas = _rotas_023()
    assert set(por_op) == set(rotas)
    sem = [op for op, (m, _) in rotas.items()
           if m != "GET" and require_human_owner not in _chamadas(por_op[op].dependant)]
    assert not sem, f"escritas do aprendizado sem RequireHumanOwner: {sem}"
    com = [op for op, (m, _) in rotas.items()
           if m == "GET" and require_human_owner in _chamadas(por_op[op].dependant)]
    assert not com, f"leituras do aprendizado só para dono humano: {com}"


def _atribui_direito(tree: ast.AST) -> list[int]:
    """`x.direito = …` e `.values(direito=…)` (gravar); montar a resposta não conta."""
    achados = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            alvos = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Attribute) and t.attr == "direito" for t in alvos):
                achados.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "values" and any(k.arg == "direito" for k in node.keywords):
            achados.append(node.lineno)
    return achados


def test_afinidade_nao_toca_no_direito():
    """Guarda 4 (princípio II): nada em `aprendizado/` nem no Descobrir grava o direito."""
    fontes = [*sorted(APRENDIZADO.rglob("*.py")), SRC / "canais" / "service_videos.py",
              SRC / "analytics" / "mercado.py"]
    achados = [f"{p.relative_to(SRC)}:{linha}" for p in fontes
               for linha in _atribui_direito(ast.parse(p.read_text()))]
    assert not achados, f"o aprendizado grava o direito (princípio II): {achados}"
    vivo = ast.parse("def f(c):\n    c.direito = 'sem_acordo'\n    q.values(direito=1)\n")
    assert len(_atribui_direito(vivo)) == 2  # o guarda está vivo


def _funcoes(tree: ast.AST, nomes: tuple[str, ...]) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in nomes]


def _grava_historico(tree: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "record" for n in ast.walk(tree))


def test_gets_do_aprendizado_nao_gravam():
    """Guarda 6: o cálculo na leitura (análise, recomendações, afinidade, desempenho,
    diagnóstico) e as funções das rotas GET não chamam `db.add`, `flush`, `commit`, SQL de
    escrita nem `history.record`."""
    achados = []
    for nome in SO_LEITURA_023:
        tree = ast.parse((APRENDIZADO / nome).read_text())
        achados += [f"{nome}:{linha}: {o}" for linha, o in _escritas(tree)]
        if _grava_historico(tree):
            achados.append(f"{nome}: history.record")
    for nome, funcoes in LEITURAS_023.items():
        tree = ast.parse((APRENDIZADO / nome).read_text())
        achadas = _funcoes(tree, funcoes)
        assert {f.name for f in achadas} == set(funcoes), (nome, funcoes)  # o guarda está vivo
        for f in achadas:
            achados += [f"{nome}:{linha}: {o} ({f.name})" for linha, o in _escritas(f)]
            if _grava_historico(f):
                achados.append(f"{nome}: history.record ({f.name})")
    assert not achados, f"leituras do aprendizado gravam: {achados}"


def test_analytics_e_canais_so_importam_a_afinidade_do_aprendizado():
    """Guarda 7: `analytics/` e `canais/` leem só `aprendizado.afinidade` (só leitura)."""
    achados = []
    for path in [*sorted((SRC / "analytics").rglob("*.py")), *sorted((SRC / "canais").rglob(
            "*.py"))]:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and \
                    node.module.startswith("sociman_api.aprendizado"):
                nomes = {a.name for a in node.names}
                if node.module == "sociman_api.aprendizado" and nomes <= {"afinidade"}:
                    continue
                if node.module == "sociman_api.aprendizado.afinidade":
                    continue
                achados.append(f"{path.relative_to(SRC)}: {node.module} {sorted(nomes)}")
    assert not achados, f"leitura do aprendizado fora da afinidade: {achados}"


# ---- spec 021 (geração local): princípios I e VII e o delete restrito da 4.3.0 ----

GERACAO = SRC / "geracao"
# Quem pode chamar o único delete do `storage.py` (exceções de eliminação da 4.3.0). A 025
# acrescenta o módulo da revogação LGPD aqui, quando existir.
DELETE_PERMITIDO = {SRC / "storage.py", GERACAO / "limpeza.py"}
COMFYUI_ALLOWED_021 = {("GET", "/system_stats"), ("POST", "/upload/image"), ("POST", "/prompt"),
                       ("GET", "/history/"), ("GET", "/view"), ("GET", "/queue"),
                       ("POST", "/queue"), ("POST", "/interrupt"), ("POST", "/free")}
SHOPTTS_ALLOWED_021 = {("GET", "/health"), ("GET", "/voices"), ("POST", "/unload"),
                       ("POST", "/v2/voices/register"), ("POST", "/v2/voices/design"),
                       ("POST", "/v2/voices/import"), ("POST", "/v2/tts"),
                       ("POST", "/v2/tts_paragraph"), ("GET", "/v2/lotes/"),
                       ("DELETE", "/v2/lotes/"), ("DELETE", "/v2/voices/")}
MEMORIA_ALLOWED_021 = {("GET", "/comfyui/memoria"), ("POST", "/comfyui/memoria/subir"),
                       ("POST", "/comfyui/memoria/devolver")}


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
    return out


def test_geracao_nao_fala_com_rede_social():
    """Princípio I (FR-027): o pacote `geracao/` só fala com o ComfyUI, o shop-tts, o
    `dockerctl` e o Claude; não importa `publicacao` nem `mcp` e não cita host de rede social."""
    for path in GERACAO.rglob("*.py"):
        mods = _imports(path)
        ruins = [m for m in mods if m.startswith(("sociman_api.publicacao", "sociman_api.mcp"))]
        assert not ruins, f"{path.name} importa {ruins}"
        texto = path.read_text().lower()
        hosts = [h for h in PUBLISH_ENDPOINTS + ("tiktok", "youtube") if h in texto]
        assert not hosts, f"{path.name} cita {hosts}"


def test_rotas_da_021_neutras_humanas_e_sem_delete():
    paths = app.openapi()["paths"]
    ops = {(m, p): op for p, v in paths.items() for m, op in v.items()
           if op.get("operationId", "").startswith(("geracoes_", "audios_"))}
    assert len(ops) == 10, sorted(op["operationId"] for op in ops.values())
    for (metodo, path), op in ops.items():
        texto = f"{path} {op['operationId']}".lower()
        assert "tiktok" not in texto and "youtube" not in texto, texto
        assert metodo != "delete", path


def _referencias(path: Path, nome: str) -> bool:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Name) and node.id == nome:
            return True
        if isinstance(node, ast.Attribute) and node.attr == nome:
            return True
        if isinstance(node, ast.ImportFrom) and any(a.name == nome for a in node.names):
            return True
        if isinstance(node, ast.FunctionDef) and node.name == nome:
            return True
    return False


def test_delete_so_nas_excecoes():
    """Constitution 4.3.0 (princípio VII): só a limpeza de 90 dias (e, na 025, a revogação LGPD)
    alcança o `storage.apagar_por_excecao`; nada de `mcp/` nem de `ia/` importa a limpeza; nenhum
    router a chama; e nenhum outro módulo apaga objeto do MinIO."""
    for path in SRC.rglob("*.py"):
        if path in DELETE_PERMITIDO:
            continue
        assert not _referencias(path, "apagar_por_excecao"), f"{path} chama o delete restrito"
        texto = path.read_text()
        assert "remove_object" not in texto, f"{path} apaga objeto do MinIO"
        if path.name.startswith("router") or path.parent.name in ("mcp", "ia"):
            mods = _imports(path)
            assert not any(m.startswith("sociman_api.geracao.limpeza") or
                           m == "sociman_api.geracao.limpeza" for m in mods), path
    storage_src = (SRC / "storage.py").read_text()
    assert storage_src.count("remove_object") == 1


def test_gerador_nunca_escolhe_sozinho():
    """FR-008: o gerador só chama `Aplicador.aplicar` dentro de um `if` que testa
    `sem_escolha` (passos de texto e `produto.recorte`); os outros vão para revisão humana."""
    arvore = ast.parse((GERACAO / "gerador.py").read_text())
    pais: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(arvore):
        for filho in ast.iter_child_nodes(node):
            pais[filho] = node
    chamadas = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "aplicar"]
    assert chamadas, "o gerador deveria aplicar os passos sem escolha"
    for chamada in chamadas:
        node, guardada = chamada, False
        while node in pais:
            node = pais[node]
            if isinstance(node, ast.If) and "sem_escolha" in ast.unparse(node.test):
                guardada = True
                break
        assert guardada, f"aplicar sem guarda de sem_escolha na linha {chamada.lineno}"


def test_clientes_da_geracao_com_lista_fechada():
    from sociman_api.geracao import comfyui, memoria, shoptts

    assert set(comfyui.ALLOWED) == COMFYUI_ALLOWED_021
    assert set(shoptts.ALLOWED) == SHOPTTS_ALLOWED_021
    assert set(memoria.ALLOWED) == MEMORIA_ALLOWED_021


def test_docker_sock_so_no_dockerctl():
    """R4 (D1 = A): o `docker.sock` dá poder total no host; só o `dockerctl` o monta."""
    import yaml

    candidatos = [Path("/repo/docker-compose.yml")]  # montado só leitura na stack de teste
    if len(API_DIR.parents) > 1:
        candidatos.append(API_DIR.parents[1] / "docker-compose.yml")
    compose = next((p for p in candidatos if p.is_file()), None)
    assert compose is not None, "docker-compose.yml não encontrado (montagem da stack de teste)"
    servicos = yaml.safe_load(compose.read_text())["services"]
    com_sock = sorted(nome for nome, svc in servicos.items()
                      if "docker.sock" in str(svc.get("volumes", [])))
    assert com_sock == ["dockerctl"], com_sock
    assert servicos["dockerctl"].get("read_only") is True
    assert servicos["dockerctl"].get("cap_drop") == ["ALL"]
    assert "ports" not in servicos["dockerctl"]


# ---- spec 026 (coleta de mercado): princípio IX, sem rede, sem perfil no lago, sem delete ----

MERCADO = SRC / "mercado"
COLETA = SRC / "coleta"
COLETOR_DIR = API_DIR.parents[0] / "coletor"  # apps/coletor (fora da API)
# Nada de HTTP de saída, automação de navegador nem publicação nos dois pacotes (FR-057).
IMPORTS_PROIBIDOS_026 = ("httpx", "requests", "urllib.request", "playwright", "selenium",
                         "pyppeteer", "sociman_api.publicacao")
AUTOMACAO_NAVEGADOR = ("playwright", "selenium", "pyppeteer", "undetected-chromedriver")
# Um endereço da rede num literal: só o coletor (host) conhece URLs do TikTok Shop.
_HOST_DA_REDE = re.compile(r"https?://[^\s\"']*(tiktok|affiliate|tiktokv|tiktokcdn)",
                           re.IGNORECASE)
# Colunas que dariam dono ao dado (FR-001); as exceções nominais do data-model.
COLUNAS_DE_DONO_026 = {"perfil_id", "conta_id", "tenant_id", "created_by", "user_id",
                       "updated_by"}
TABELAS_COM_DONO_026 = {"mercado_interesses", "mercado_perfil_config", "coleta_clientes",
                        "coleta_config"}
EXCECOES_026 = {("mercado_fila", "perfil_id")}
SO_INSERCAO_026 = {"mercado_loja_fotos", "mercado_produto_fichas", "mercado_imagens",
                   "mercado_produto_imagens", "mercado_produto_fotos", "mercado_ranking_fotos",
                   "mercado_ranking_foto_itens", "mercado_avaliacoes", "mercado_produto_videos",
                   "mercado_coleta_itens", "coleta_eventos"}
ROTAS_C_026 = {"coleta_fila", "coleta_coletas_abrir", "coleta_itens_enviar",
               "coleta_imagens_enviar", "coleta_batimento", "coleta_coletas_fechar",
               "coleta_eventos_enviar", "coleta_bruto_link"}
# Leituras **U** que o token do coletor também alcança (`reprocessar --desde`, FR-012): o ator
# `coletor` passa por `require_user_ou_coletor` e o service o restringe às próprias rodadas.
ROTAS_C_LEITURA_026 = {"coleta_coletas_listar", "coleta_coletas_detalhe"}


def _fontes_026() -> list[Path]:
    return sorted(MERCADO.rglob("*.py")) + sorted(COLETA.rglob("*.py"))


def test_api_sem_automacao_de_navegador():
    """Princípio IX: a API nunca contém Playwright, Selenium nem parente; só o `apps/coletor/`
    (fora do Docker) automatiza o navegador."""
    data = tomllib.loads(PYPROJECT.read_text())
    deps = list(data["project"].get("dependencies", []))
    for group in data.get("dependency-groups", {}).values():
        deps += [d for d in group if isinstance(d, str)]
    ruins = [d for d in deps if any(a in d.lower() for a in AUTOMACAO_NAVEGADOR)]
    assert not ruins, f"a API ganhou automação de navegador (princípio IX): {ruins}"
    for path in _fontes():
        mods = _imports(path)
        ruins = [m for m in mods if m.split(".")[0] in ("playwright", "selenium", "pyppeteer")]
        assert not ruins, f"{path.relative_to(SRC)} importa {ruins}"


def test_mercado_e_coleta_sem_rede_nem_publicacao():
    """FR-057: `mercado/` e `coleta/` não têm HTTP de saída, não importam a publicação e não
    citam endereço da rede em literal (isso vive só em `apps/coletor/`)."""
    fontes = _fontes_026()
    assert (COLETA / "ingestao.py") in fontes and (MERCADO / "models.py") in fontes  # vivo
    achados = []
    for path in fontes:
        rel = str(path.relative_to(SRC))
        mods = _imports(path)
        achados += [f"{rel}: import {m}" for m in mods if m.startswith(IMPORTS_PROIBIDOS_026)]
        for texto in _strings_de_codigo(ast.parse(path.read_text())):
            if _HOST_DA_REDE.search(texto):
                achados.append(f"{rel}: {texto[:50]}")
    assert not achados, f"mercado/coleta falam com a rede (princípio IX): {achados}"


def test_mercado_lago_sem_perfil_conta_ou_tenant():
    """FR-001: nenhuma tabela do lago nem da operação tem dono; a exceção nominal é
    `mercado_fila.perfil_id` (operacional, revezamento). As camadas de interesse e de infra do
    dono são as únicas com `perfil_id`/auditoria."""
    from sociman_api.db import Base
    from sociman_api.mercado import models as mm

    assert set(mm.SO_INSERCAO) == SO_INSERCAO_026
    ruins = []
    for tabela in Base.metadata.sorted_tables:
        if not tabela.name.startswith(("mercado_", "coleta_")):
            continue
        if tabela.name in TABELAS_COM_DONO_026:
            continue
        for col in tabela.columns:
            if col.name in COLUNAS_DE_DONO_026 and (tabela.name, col.name) not in EXCECOES_026:
                ruins.append(f"{tabela.name}.{col.name}")
    assert not ruins, f"o lago ganhou dono (FR-001): {ruins}"
    nomes = {t.name for t in Base.metadata.sorted_tables}
    assert set(mm.LAGO) <= nomes and "mercado_fila" in nomes and "coleta_eventos" in nomes


def test_mercado_e_coleta_sem_delete():
    """FR-002 (lago permanente): nenhum `.delete(`, `delete(`/`DELETE`/`TRUNCATE` nem
    `apagar_por_excecao` em `mercado/` e `coleta/`. A limpeza de 90 dias da 021 não se aplica."""
    achados = []
    for path in _fontes_026():
        rel = str(path.relative_to(SRC))
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Attribute) and f.attr in ("delete", "apagar_por_excecao",
                                                               "remove_object", "truncate"):
                    achados.append(f"{rel}:{node.lineno} .{f.attr}(")
                elif isinstance(f, ast.Name) and f.id in ("delete", "apagar_por_excecao"):
                    achados.append(f"{rel}:{node.lineno} {f.id}(")
            elif isinstance(node, ast.ImportFrom) and node.module and \
                    node.module.split(".")[0] == "sqlalchemy":
                achados += [f"{rel}: import {a.name}" for a in node.names if a.name == "delete"]
        for texto in _strings_de_codigo(tree):
            if re.search(r"\b(DELETE\s+FROM|TRUNCATE)\b", texto, re.IGNORECASE):
                achados.append(f"{rel}: {texto.strip()[:40]}")
    assert not achados, f"mercado/coleta apagam (FR-002): {achados}"
    # O único delete do storage continua restrito (4.3.0): a 026 não entrou na lista.
    assert not any(p.parent.name in ("mercado", "coleta") for p in DELETE_PERMITIDO)


def test_coleta_portao_global_e_rotas_c():
    """FR-025: o portão do `scol_` é dependência global do app e as rotas C existem com o
    `RequireColetor`; as de gestão são de dono humano (ficam em PROIBIDAS no MCP)."""
    from sociman_api.auth.deps import require_coletor, require_human_owner
    from sociman_api.coleta import portao
    from sociman_api.mcp import mapa

    deps = {d.dependency for d in app.router.dependencies}
    assert portao.dependencia in deps
    assert set(portao.ROTAS_C) == ROTAS_C_026 | ROTAS_C_LEITURA_026
    rotas = {r.operation_id: r for r in _rotas_026(app.routes)
             if getattr(r, "operation_id", None)}
    for op in ROTAS_C_026:
        assert op in rotas, op
        assert require_coletor in _deps_026(rotas[op]), op
        assert op in mapa.FORA, op
    from sociman_api.auth.deps import require_user_ou_coletor

    for op in ROTAS_C_LEITURA_026:
        assert require_user_ou_coletor in _deps_026(rotas[op]), op
        assert op in mapa.FORA, op
    for op in mapa.PROIBIDAS:
        if op.startswith("coleta_"):
            assert require_human_owner in _deps_026(rotas[op]), op


def _rotas_026(rotas) -> list:
    out = []
    for r in rotas:
        if hasattr(r, "original_router"):
            out += _rotas_026(r.original_router.routes)
        elif hasattr(r, "dependant"):
            out.append(r)
        elif hasattr(r, "routes"):
            out += _rotas_026(r.routes)
    return out


def _deps_026(rota) -> set:
    def arvore(dependant) -> set:
        calls = set()
        for d in dependant.dependencies:
            calls.add(d.call)
            calls |= arvore(d)
        return calls
    return arvore(rota.dependant)


def test_coleta_token_so_hash():
    """FR-024: o token do coletor só existe como SHA-256 no banco; nunca entra no histórico nem
    numa saída da API."""
    from sociman_api.coleta import schemas
    from sociman_api.coleta.models import ColetaCliente

    colunas = {c.name for c in ColetaCliente.__table__.columns}
    assert "token_hash" in colunas and "token" not in colunas
    assert "token_hash" not in ColetaCliente.__versioned_fields__
    assert "token" not in schemas.ColetaCliente.model_fields
    assert set(schemas.ColetaClienteComToken.model_fields) == {"cliente", "token"}
    texto = (COLETA / "credenciais.py").read_text()
    assert "sha256" in texto and "compare_digest" in texto


def test_mercado_leitura_so_get_e_sem_escrita():
    """FR-042: as leituras do mercado são GET e os módulos de leitura não gravam (reuso do guarda
    da 019). Os módulos entram na US1; até lá a lista pode estar vazia."""
    leitura = [MERCADO / n for n in ("consulta.py", "consulta_detalhe.py", "calculo.py", "filtros.py")
               if (MERCADO / n).is_file()]
    for path in leitura:
        tree = ast.parse(path.read_text())
        assert not _escritas(tree), f"{path.name} escreve: {_escritas(tree)}"
        mods = _imports(path)
        assert not [m for m in mods if m.startswith("sociman_api.history")], path.name
    rotas = {op.get("operationId", ""): m.upper()
             for path, ops in app.openapi()["paths"].items() for m, op in ops.items()
             if path.startswith("/api/mercado") or "/mercado/" in path}
    escritas = {"mercado_interesses_criar", "mercado_interesses_editar",
                "mercado_interesses_revert", "mercado_perfil_config_put",
                "mercado_perfil_config_revert", "mercado_lojas_seguir",
                "mercado_lojas_deixar_de_seguir", "mercado_produtos_adotar"}
    outras = {op for op, m in rotas.items() if m != "GET"} - escritas
    assert not outras, f"rota de mercado que escreve fora da lista (FR-042): {outras}"
