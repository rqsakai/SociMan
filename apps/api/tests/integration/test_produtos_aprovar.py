"""Revisar, editar e aprovar (spec 012, T032, US3, R9–R11): pendências, aprovar por dono ou
membro, voltar a revisão ao editar, a origem da ficha, o aviso `flat_desatualizado`, o controle
de versão e o limite de variantes."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from integration.geracao_helpers import _buckets, member, motores, owner  # noqa: F401
from integration.produtos_helpers import (  # noqa: F401 (fixtures)
    claude_fake,
    criar,
    escolher,
    foto,
    passos,
    perfil,
    rodar_tudo,
    ver,
)


def _aprovar(client, h, p, status=200) -> dict:
    r = client.post(f"/api/produtos/{p['id']}/aprovar", headers=h, json={"version": p["version"]})
    assert r.status_code == status, r.text
    return r.json()


def _ficha_corpo(p: dict, **mudancas) -> dict:
    ficha = dict(p["ficha"]) | mudancas
    cores = [{"varianteId": v["id"], "corEn": v["corEn"] or "", "corPt": v["corPt"] or ""}
             for v in p["variantes"] if not v["archivedAt"]]
    return {"version": p["version"], "ficha": ficha, "cores": cores}


def _salvar(client, h, p, status=200, cores=None, **mudancas) -> dict:
    corpo = _ficha_corpo(p, **mudancas)
    if cores is not None:
        corpo["cores"] = cores
    r = client.put(f"/api/produtos/{p['id']}/ficha", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def _em_revisao(client, h, motores, n_fotos=1, obs="") -> dict:
    p = criar(client, h, perfil(client, h), n_fotos=n_fotos, obs=obs)
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    for f in passos(p, "produto.flat"):
        escolher(client, h, p, f["id"])
        p = ver(client, h, p["id"])
    assert p["status"] == "revisao", p["pendencias"]
    return p


def test_aprovar_com_pendencias(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    # Gerando, com o flat em revisão: não aprova (fora de revisão) e mostra as pendências.
    erro = _aprovar(client, h, p, status=409)
    assert erro["error"]["code"] == "estado_invalido"
    v = p["variantes"][0]["id"]
    assert {"varianteId": v, "motivo": "sem_flat"} in p["pendencias"]
    assert {"varianteId": v, "motivo": "geracao_em_andamento"} in p["pendencias"]


def test_variante_sem_cor_bloqueia(client, owner, motores, claude_fake):
    h = owner[1]
    p = _em_revisao(client, h, motores, obs="sem flat")
    v = p["variantes"][0]
    r = client.patch(f"/api/produtos/{p['id']}/variantes/{v['id']}", headers=h,
                     json={"version": p["version"], "corEn": ""})
    p = r.json()
    assert {"varianteId": v["id"], "motivo": "sem_cor"} in p["pendencias"]
    assert "sem_cor" in p["variantes"][0]["avisos"]
    erro = _aprovar(client, h, p, status=409)
    assert erro["error"]["code"] == "produto_incompleto"
    assert {"varianteId": v["id"], "motivo": "sem_cor"} in erro["error"]["details"]["pendencias"]


def test_aprovar_e_voltar_a_revisao(client, owner, member, motores, claude_fake):
    h = owner[1]
    p = _em_revisao(client, h, motores)
    p = _aprovar(client, member[1], p)  # o membro também aprova (FR-021)
    assert p["status"] == "aprovado" and p["pendencias"] == []
    # Editar a ficha num aprovado → revisão; a origem vira `ia_editada`.
    p = _salvar(client, h, p, materialPt="malha canelada macia")
    assert p["status"] == "revisao" and p["fichaPor"] == "ia_editada"
    p = _aprovar(client, h, p)
    # A cor de uma variante → revisão.
    v = p["variantes"][0]
    r = client.patch(f"/api/produtos/{p['id']}/variantes/{v['id']}", headers=h,
                     json={"version": p["version"], "corPt": "preto fosco"})
    p = r.json()
    assert p["status"] == "revisao"
    p = _aprovar(client, h, p)
    # Refazer o flat → revisão (com a geração em andamento como pendência).
    r = client.post(f"/api/produtos/{p['id']}/variantes/{v['id']}/refazer-flat", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 201
    p = ver(client, h, p["id"])
    assert p["status"] == "revisao"
    assert {"varianteId": v["id"], "motivo": "geracao_em_andamento"} in p["pendencias"]
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    nova = next(f for f in passos(p, "produto.flat") if f["status"] == "revisao")
    escolher(client, h, p, nova["id"])
    p = _aprovar(client, h, ver(client, h, p["id"]))
    # Variante nova num aprovado → gerando (o recorte entra na fila).
    r = client.post(f"/api/produtos/{p['id']}/variantes", headers=h,
                    data={"version": str(p["version"])},
                    files={"foto": ("v.jpg", foto(cor=(200, 10, 10)), "image/jpeg")})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "gerando"


def test_ficha_a_mao_sem_ia_libera_os_recortes(client, owner, motores):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    motores.linha_claude().volta()  # sem chave: falha
    p = ver(client, h, p["id"])
    ficha = {"nomeComercial": "Short", "categoria": "roupa > shorts", "materialEn": "ribbed knit",
             "materialPt": "malha", "formatoCorte": "biker shorts", "detalhesVisiveis": ["logo"],
             "tamanhoRelativo": "single item", "descricaoPrompt": "Ribbed knit shorts.",
             "cuidados": ["não é jeans"], "descricaoVenda": "Confortável.", "precisaFlat": False}
    v = p["variantes"][0]["id"]
    r = client.put(f"/api/produtos/{p['id']}/ficha", headers=h,
                   json={"version": p["version"], "ficha": ficha,
                         "cores": [{"varianteId": v, "corEn": "black", "corPt": "preto"}]})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["fichaPor"] == "humano"
    assert [s["status"] for s in passos(p, "produto.ficha")] == ["cancelada"]
    assert passos(p, "produto.recorte")[0]["status"] == "na_fila"
    # Salvar de novo continua `humano`.
    assert _salvar(client, h, p, categoria="moda > shorts")["fichaPor"] == "humano"


def test_ligar_precisa_flat_pede_os_flats(client, owner, motores, claude_fake):
    h = owner[1]
    p = _em_revisao(client, h, motores, n_fotos=2, obs="sem flat")
    p = _salvar(client, h, p, precisaFlat=True)
    assert p["status"] == "gerando"
    assert len(passos(p, "produto.flat")) == 2


def test_flat_desatualizado_so_quando_a_instrucao_muda(client, owner, motores, claude_fake):
    h = owner[1]
    p = _em_revisao(client, h, motores)
    assert p["variantes"][0]["avisos"] == []
    p = _salvar(client, h, p, descricaoVenda="Outra descrição de venda.")
    assert p["variantes"][0]["avisos"] == []  # não entra na instrução do flat
    p = _salvar(client, h, p, materialEn="smooth satin")
    assert p["variantes"][0]["avisos"] == ["flat_desatualizado"]


def test_limites_e_conflito(client, owner, motores, claude_fake):
    h = owner[1]
    p = _em_revisao(client, h, motores, obs="sem flat")
    erro = _salvar(client, h, p, status=400, materialEn="soft stretchy ribbed cotton knit fabric")
    assert erro["error"]["code"] == "invalid_produto"
    assert erro["error"]["details"]["field"] == "materialEn"
    r = client.put(f"/api/produtos/{p['id']}/ficha", headers=h,
                   json=_ficha_corpo(p) | {"version": p["version"] - 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


def test_limite_de_variantes_e_ultima(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=6)
    r = client.post(f"/api/produtos/{p['id']}/variantes", headers=h,
                    data={"version": str(p["version"])},
                    files={"foto": ("v.jpg", foto(), "image/jpeg")})
    assert r.status_code == 409 and r.json()["error"]["code"] == "limite_variantes"
    um = criar(client, h, perfil(client, h, slug="outro"), n_fotos=1)
    r = client.post(f"/api/produtos/{um['id']}/variantes/{um['variantes'][0]['id']}/arquivar",
                    headers=h, json={"version": um["version"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_produto"
    # Ordenar exige exatamente as ativas.
    ids = [v["id"] for v in p["variantes"]]
    r = client.put(f"/api/produtos/{p['id']}/variantes/ordem", headers=h,
                   json={"version": p["version"], "ids": list(reversed(ids))})
    assert r.status_code == 200
    assert [v["id"] for v in r.json()["variantes"]] == list(reversed(ids))
    r = client.put(f"/api/produtos/{p['id']}/variantes/ordem", headers=h,
                   json={"version": r.json()["version"], "ids": ids[:2]})
    assert r.status_code == 400
