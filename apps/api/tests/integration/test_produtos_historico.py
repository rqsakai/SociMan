"""Lista, arquivo e histórico (spec 012, T041, US5, R4 e R16): arquivar e restaurar mantêm o
estado, o produto arquivado sai do seletor, geração em andamento aplica no arquivado, reverter
(só o dono) sem gerar nada, e os filtros da lista."""

# ruff: noqa: F811 — fixtures importadas dos helpers

from sqlalchemy import func, select

from integration.geracao_helpers import _buckets, member, motores, owner  # noqa: F401
from integration.produtos_helpers import (  # noqa: F401 (fixtures)
    claude_fake,
    criar,
    passos,
    perfil,
    rodar_tudo,
    ver,
    versoes,
)
from sociman_api.geracao.models import Geracao


def _post(client, h, p, rota, status=200, **body) -> dict:
    r = client.post(f"/api/produtos/{p['id']}/{rota}", headers=h,
                    json={"version": p["version"], **body})
    assert r.status_code == status, r.text
    return r.json()


def _aprovado(client, h, pid, motores) -> dict:
    p = criar(client, h, pid, n_fotos=1, obs="sem flat")
    rodar_tudo(motores)
    return _post(client, h, ver(client, h, p["id"]), "aprovar")


def test_arquivar_e_restaurar_mantem_aprovado(client, owner, motores, claude_fake, db):
    h = owner[1]
    pid = perfil(client, h)
    p = _aprovado(client, h, pid, motores)
    n = db.scalar(select(func.count()).select_from(Geracao))
    p = _post(client, h, p, "arquivar")
    assert p["estado"] == "arquivado" and p["status"] == "aprovado"
    seletor = client.get(f"/api/perfis/{pid}/produtos", headers=h,
                         params={"status": "aprovado"}).json()["itens"]
    assert seletor == []  # fora do seletor das cenas
    p = _post(client, h, p, "restaurar")
    assert p["estado"] == "aprovado"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Geracao)) == n  # nada gerado
    assert [v["action"] for v in versoes(client, h, p["id"])][:2] == ["restored", "archived"]


def test_geracao_aberta_aplica_no_arquivado(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    p = _post(client, h, p, "arquivar")  # a ficha está na fila
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    assert p["estado"] == "arquivado" and p["fichaPor"] == "ia"
    assert p["variantes"][0]["recorte"] is not None  # o fluxo seguiu no arquivado
    # Arquivar com "cancelar gerações": as abertas são canceladas.
    q = criar(client, h, perfil(client, h, slug="dois"), n_fotos=1)
    q = _post(client, h, q, "arquivar", cancelarGeracoes=True)
    assert [s["status"] for s in passos(q, "produto.ficha")] == ["cancelada"]


def test_reverter_ficha_sem_gerar(client, owner, member, motores, claude_fake, db):
    h = owner[1]
    p = _aprovado(client, h, perfil(client, h), motores)
    ficha = dict(p["ficha"]) | {"materialEn": "smooth satin"}
    cores = [{"varianteId": v["id"], "corEn": v["corEn"], "corPt": v["corPt"]}
             for v in p["variantes"]]
    r = client.put(f"/api/produtos/{p['id']}/ficha", headers=h,
                   json={"version": p["version"], "ficha": ficha, "cores": cores})
    p = r.json()
    alvo = next(v["version"] for v in versoes(client, h, p["id"])
                if v["after"]["status"] == "aprovado")
    n = db.scalar(select(func.count()).select_from(Geracao))
    r = client.post(f"/api/produtos/{p['id']}/revert", headers=member[1],
                    json={"version": p["version"], "toVersion": alvo})
    assert r.status_code == 403
    r = client.post(f"/api/produtos/{p['id']}/revert", headers=h,
                    json={"version": p["version"], "toVersion": alvo})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["ficha"]["materialEn"] == "ribbed knit"
    assert p["status"] == "revisao"  # nunca volta a aprovado sozinho
    assert versoes(client, h, p["id"])[0]["action"] == "reverted"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Geracao)) == n


def test_filtros_da_lista(client, owner, motores, claude_fake):
    h = owner[1]
    pid = perfil(client, h)
    a = criar(client, h, pid, n_fotos=0, name="Garrafa térmica")
    criar(client, h, pid, n_fotos=0, name="Shorts")
    lista = client.get(f"/api/perfis/{pid}/produtos", headers=h,
                       params={"q": "TERMICA"}).json()["itens"]
    assert [i["id"] for i in lista] == [a["id"]]
    _post(client, h, a, "arquivar")
    assert [i["name"] for i in client.get(f"/api/perfis/{pid}/produtos", headers=h).json()[
        "itens"]] == ["Shorts"]
    so = client.get(f"/api/perfis/{pid}/produtos", headers=h,
                    params={"arquivados": "so"}).json()["itens"]
    assert [i["id"] for i in so] == [a["id"]] and so[0]["estado"] == "arquivado"
    por_estado = client.get(f"/api/perfis/{pid}/produtos", headers=h,
                            params={"status": "rascunho", "arquivados": "true"}).json()["itens"]
    assert len(por_estado) == 2
