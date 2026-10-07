"""T008 (R2, FR-009/FR-010/FR-012, SC-003): o mapa classifica toda operação do OpenAPI, nenhuma
PROIBIDA vira tool, toda rota de dono humano está em PROIBIDAS e as definições geradas são
válidas."""

import json
import re

from sociman_api.auth.deps import require_human, require_human_owner
from sociman_api.main import app
from sociman_api.mcp import ferramentas, mapa

NOME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def rotas_resolvidas(rotas) -> list:
    """As `APIRoute` de verdade (o FastAPI 0.141 embrulha em `_IncludedRouter`, armadilha 16)."""
    out = []
    for r in rotas:
        if hasattr(r, "original_router"):
            out += rotas_resolvidas(r.original_router.routes)
        elif hasattr(r, "dependant"):
            out.append(r)
        elif hasattr(r, "routes"):
            out += rotas_resolvidas(r.routes)
    return out


def _arvore(dependant) -> set:
    calls = set()
    for d in dependant.dependencies:
        calls.add(d.call)
        calls |= _arvore(d)
    return calls


def chamadas_da_rota(rota) -> set:
    return _arvore(rota.dependant)


def _ops() -> set[str]:
    return {op["operationId"] for p in app.openapi()["paths"].values() for op in p.values()}


def test_toda_operacao_em_exatamente_uma_lista():
    listas = (set(mapa.TOOLS), set(mapa.FORA), set(mapa.PROIBIDAS))
    sem = sorted(op for op in _ops() if sum(op in lista for lista in listas) != 1)
    assert not sem, f"operações sem classificação (ou em mais de uma lista): {sem}"


def test_nenhum_id_do_mapa_falta_no_openapi():
    sobra = sorted((set(mapa.TOOLS) | set(mapa.FORA) | set(mapa.PROIBIDAS)) - _ops())
    assert not sobra, f"operationIds do mapa que não existem mais: {sobra}"


def test_proibidas_fora_das_tools_e_rotas_humanas_proibidas():
    assert not set(mapa.PROIBIDAS) & set(mapa.TOOLS)
    humanas = {r.operation_id for r in rotas_resolvidas(app.routes)
               if getattr(r, "operation_id", None)
               and {require_human_owner, require_human} & chamadas_da_rota(r)}
    assert humanas, "o guarda está vivo"
    fora = sorted(humanas - set(mapa.PROIBIDAS))
    assert not fora, f"rotas de dono/humano fora de PROIBIDAS: {fora}"


def test_escrita_so_em_propostas():
    erradas = [n for n, t in mapa.TOOLS.items() if t.escrita and t.escopo != "propostas"]
    assert not erradas
    assert {n for n, t in mapa.TOOLS.items() if t.escrita} == {
        "anotacoes_create", "anotacoes_update", "anotacoes_archive", "envios_selecionar",
        "destinos_update"}


def test_definicoes_validas():
    defs = ferramentas.definicoes(app, "propostas")
    assert [d["name"] for d in defs] == sorted(mapa.TOOLS)
    for d in defs:
        assert NOME.match(d["name"])
        entrada = d["inputSchema"]
        assert entrada["type"] == "object" and entrada["additionalProperties"] is False
        texto = json.dumps(d)
        assert "#/components/" not in texto, d["name"]
        for ref in re.findall(r'"\$ref": "#/\$defs/([^"]+)"', json.dumps(entrada)):
            assert ref in entrada["$defs"], (d["name"], ref)
        if "outputSchema" in d:
            assert d["outputSchema"]["type"] == "object"
            for ref in re.findall(r'"\$ref": "#/\$defs/([^"]+)"', json.dumps(d["outputSchema"])):
                assert ref in d["outputSchema"]["$defs"], (d["name"], ref)


def test_descricoes_em_pt_br():
    for d in ferramentas.definicoes(app, "propostas"):
        tool = mapa.TOOLS[d["name"]]
        assert len(tool.descricao) >= 20, d["name"]
        assert d["description"].startswith(tool.descricao) and ferramentas.AVISO in d["description"]
        # nunca só o summary gerado do nome da função ("Perfis List")
        assert d["title"] != d["name"].replace("_", " ").title()


def test_campos_ocultos_fora_do_schema():
    cat = ferramentas.catalogo(app)
    entrada = cat["destinos_update"].definicao["inputSchema"]["properties"]
    assert "propostaId" not in entrada and "ia" not in entrada and "version" in entrada
    assert "download" not in cat["kit_export"].definicao["inputSchema"]["properties"]


def test_paginacao_padrao():
    cat = ferramentas.catalogo(app)
    for nome, op in cat.items():
        if op.tool.limite_padrao:
            assert op.limite_param, f"{nome}: limite_padrao sem parâmetro de página"


def test_escopos():
    leitura = {d["name"] for d in ferramentas.definicoes(app, "leitura")}
    propostas = {d["name"] for d in ferramentas.definicoes(app, "propostas")}
    # spec 010: +8 leituras de cena (lista, detalhe, histórico, tomadas, padrões, conteúdo)
    # spec 013: +2 leituras do registro de importações da agência (lista e detalhe)
    # spec 022: +1 leitura (analytics_publico)
    # spec 023: +7 leituras do aprendizado (temas, classificações, análise, recomendações,
    # preferências e os dois diagnósticos)
    assert len(leitura) == 80 and len(propostas) == 85 and leitura < propostas
    exportado = ferramentas.exportar_json(app)
    assert {d["name"] for d in exportado["leitura"]} == leitura
    assert {d["name"] for d in exportado["propostas"]} == propostas - leitura


def test_aprendizado_leituras_tools_analises_fora_e_escritas_proibidas():
    """Spec 023 (T061, R13): as leituras viram tools `leitura`; as análises da IA e os
    históricos ficam em `FORA`; toda escrita em `PROIBIDAS`."""
    ops = {op["operationId"]: (metodo, rota) for rota, item in app.openapi()["paths"].items()
           for metodo, op in item.items() if op["operationId"].startswith("aprendizado_")}
    leituras = {"aprendizado_temas_list", "aprendizado_classificacoes_list",
                "aprendizado_analise", "aprendizado_recomendacoes",
                "aprendizado_preferencias_get", "aprendizado_diagnostico",
                "aprendizado_post_diagnostico"}
    fora = {"aprendizado_analises_list", "aprendizado_analises_get",
            "aprendizado_temas_versions", "aprendizado_classificacoes_versions",
            "aprendizado_preferencias_versions"}
    assert {o for o in ops if mapa.classificar(o) == "tool"} == leituras
    assert all(mapa.TOOLS[o].escopo == "leitura" and not mapa.TOOLS[o].escrita for o in leituras)
    assert {o for o in ops if mapa.classificar(o) == "fora"} == fora
    escritas = {o for o, (metodo, _) in ops.items() if metodo != "get"}
    assert escritas and all(mapa.classificar(o) == "proibida" for o in escritas)
    assert all(metodo != "delete" for metodo, _ in ops.values())
