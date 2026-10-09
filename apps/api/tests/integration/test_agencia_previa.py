"""Pré-visualização (spec 013, US1, T017): situações, contagens, origem e nada gravado."""

import time

from sqlalchemy import text

from integration.agencia_helpers import (  # noqa: F401
    _buckets,
    agencia,
    dono,
    itens,
    previa,
    um,
    yt,
)
from sociman_api.agencia import previa as previa_mod
from sociman_api.db import get_engine

TABELAS = ("perfis", "contas", "canais_fonte", "assets", "images", "anotacoes", "ia_guias",
           "conteudos", "entity_versions", "agencia_importacoes", "agencia_importacao_itens")


def _contagens_banco() -> dict[str, int]:
    with get_engine().connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABELAS}


def _criar_perfil(client, h, slug, nome, **kw):
    r = client.post("/api/perfis", headers=h, json={"name": nome, "slug": slug, "status": "ativo",
                                                     "niche": "RPG e colecionáveis"} | kw)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]


def test_quatro_situacoes_sem_gravar(client, dono, agencia, yt):  # noqa: F811
    _, h = dono
    _criar_perfil(client, h, "igual-teste", "Igual Teste")
    _criar_perfil(client, h, "diverge-teste", "Diverge Teste", niche="Outro nicho")
    agencia.perfil("novo-teste", "Novo Teste")
    agencia.perfil("igual-teste", "Igual Teste")
    agencia.perfil("diverge-teste", "Diverge Teste")
    agencia.escrever("perfis/novo-teste/rascunho.txt", "segredo? nunca é aberto")
    antes = _contagens_banco()

    p = previa(client, h)

    assert _contagens_banco() == antes  # nada gravado no domínio
    assert um(p, "perfil", perfilSlug="novo-teste")["situacao"] == "novo"
    assert um(p, "perfil", perfilSlug="igual-teste")["situacao"] == "igual"
    d = um(p, "perfil", perfilSlug="diverge-teste")
    assert (d["situacao"], d["motivo"]) == ("diverge", "valor")
    assert d["atual"]["nicho"] == "Outro nicho" and d["proposto"]["nicho"] == "RPG e colecionáveis"
    assert d["escolhaPadrao"] == {"marcado": None, "usar": "sociman", "direito": None}
    fora = um(p, "arquivo", origem={"arquivo": "shared:perfis/novo-teste/rascunho.txt",
                                    "trecho": "", "linha": None})
    assert fora["motivo"] == "fora_do_mapeamento" and fora["motivoTexto"] == "fora do mapeamento"
    molde = [i for i in itens(p, "arquivo") if i["motivo"] == "molde"]
    assert molde and itens(p, "arquivo", motivo="manual")
    novo = um(p, "perfil", perfilSlug="novo-teste")
    assert novo["origem"]["arquivo"] == "shared:perfis/novo-teste/perfil.md"
    assert novo["escolhaPadrao"]["marcado"] is True
    soma = sum(v for k, v in p["contagens"].items() if k != "naoReconhecido")
    assert soma == len(p["itens"])
    # anotações do perfil novo: §3 público, §6 monetização e as 2 decisões (§7 só molde)
    anot = itens(p, "anotacao", perfilSlug="novo-teste")
    assert sorted(a["origem"]["trecho"].split(" ·")[0] for a in anot) == [
        "§3. Público", "§6. Monetização", "§8", "§8"]


def test_previa_expira_e_e_de_uso_unico(client, dono, agencia, yt, monkeypatch):  # noqa: F811
    _, h = dono
    agencia.perfil()
    monkeypatch.setattr(previa_mod, "TTL", previa_mod.timedelta(seconds=1))
    p = previa(client, h)
    time.sleep(1.5)
    r = client.post("/api/agencia/importacoes", headers=h, json={"previaId": p["previaId"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "previa_expirada"


def test_pasta_indisponivel(client, dono, agencia, monkeypatch):  # noqa: F811
    _, h = dono
    from sociman_api.config import get_settings

    monkeypatch.setattr(get_settings(), "agencia_shared_dir", "/nao/existe")
    r = client.post("/api/agencia/previa", headers=h)
    assert r.status_code == 503 and r.json()["error"]["code"] == "agencia_pasta_indisponivel"
    e = client.get("/api/agencia/estado", headers=h).json()
    assert e["raizes"]["shared"]["disponivel"] is False
    assert e["raizes"]["clipes"]["disponivel"] is True


def test_pasta_grande(client, dono, agencia, monkeypatch):  # noqa: F811
    _, h = dono
    from sociman_api.agencia import pastas

    monkeypatch.setattr(pastas, "ENTRADAS_MAX", 2)
    agencia.perfil()
    r = client.post("/api/agencia/previa", headers=h)
    assert r.status_code == 413 and r.json()["error"]["code"] == "agencia_pasta_grande"


def test_arquivado_slug_e_sem_perfil_md(client, dono, agencia, yt):  # noqa: F811
    _, h = dono
    perfil = _criar_perfil(client, h, "velho-teste", "Velho Teste")
    r = client.post(f"/api/perfis/{perfil['id']}/archive", headers=h,
                    json={"version": perfil["version"]})
    assert r.status_code == 200, r.text
    agencia.perfil("velho-teste", "Velho Teste")
    agencia.fontes("velho-teste", ("Canal", "youtube.com/@x", "`autorizado`", "", "", "", ""))
    agencia.perfil("Taverna_Teste", "Outra")  # vira taverna-teste
    agencia.perfil("taverna-teste", "Taverna")  # colide com a pasta acima
    agencia.escrever("perfis/sem-md/fontes.md", "# Fontes\n")

    p = previa(client, h)

    velho = um(p, "perfil", perfilSlug="velho-teste")
    assert (velho["situacao"], velho["motivo"]) == ("diverge", "arquivado")
    assert velho["escolhaPadrao"] is None
    assert all(i["situacao"] == "fora" for i in itens(p, perfilSlug="velho-teste")
               if i["tipo"] != "perfil")
    assert itens(p, "arquivo", motivo="slug_em_uso")
    assert um(p, "perfil", perfilSlug="sem-md")["motivo"] == "sem_perfil_md"


def test_arquivo_nao_reconhecido_nao_para_o_resto(client, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil()
    agencia.escrever("perfis/taverna-teste/fontes.md", "# Fontes\n\n| Nome | Link |\n|---|---|\n"
                     "| x | y |\n")
    agencia.escrever("perfis/outro-teste/perfil.md", "# Perfil: Outro\n\n## 1. Identidade\n"
                     "- Nome do perfil: Outro\n")
    p = previa(client, h)
    faltas = {n["arquivo"]: n["faltou"] for n in p["arquivosNaoReconhecidos"]}
    assert faltas["shared:perfis/taverna-teste/fontes.md"] == [
        "tabela com as colunas criador, canal e status"]
    assert "seção 2. nicho" in faltas["shared:perfis/outro-teste/perfil.md"]
    assert p["contagens"]["naoReconhecido"] == 2
    assert um(p, "perfil", perfilSlug="taverna-teste")["situacao"] == "novo"


def test_link_para_fora_nao_e_lido(client, dono, agencia, yt, tmp_path):  # noqa: F811
    _, h = dono
    agencia.perfil()
    fora = tmp_path / "segredo.md"
    fora.write_text("não leia")
    (agencia.shared / "perfis" / "taverna-teste" / "pesquisa.md").symlink_to(fora)
    p = previa(client, h)
    link = um(p, "arquivo", motivo="link_para_fora")
    assert link["origem"]["arquivo"] == "shared:perfis/taverna-teste/pesquisa.md"


def test_estado_mostra_ultima_importacao_e_arquivos_mudados(client, dono, agencia, yt):  # noqa: F811
    _, h = dono
    agencia.perfil()
    from integration.agencia_helpers import importar

    importar(client, h)
    e = client.get("/api/agencia/estado", headers=h).json()
    assert e["ultima"]["estado"] == "concluida" and e["emAndamento"] is None
    assert [(p["slug"], p["arquivosMudaram"]) for p in e["perfis"]] == [("taverna-teste", False)]
    agencia.perfil(tom="Outro tom")
    e = client.get("/api/agencia/estado", headers=h).json()
    assert e["perfis"][0]["arquivosMudaram"] is True
