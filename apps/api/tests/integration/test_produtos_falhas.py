"""Falhas do cadastro (spec 012, T021 e T027): Claude sem chave, recusa e saída inválida; o
ComfyUI fora sem nova chamada de ficha (SC-002); GPU ocupada; falta de memória com a RAM de
volta a 12 GB; cancelar um flat; o gerador nunca escolhe o flat; o MCP não escolhe."""

# ruff: noqa: F811 — fixtures importadas dos helpers

import uuid

from fakes.dockerctl_fake import JOB, NORMAL
from sqlalchemy import select

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    motores,
    owner,
    rodar_gpu,
    sem_espera,
)
from integration.produtos_helpers import (  # noqa: F401 (fixtures)
    claude_fake,
    com_claude,
    criar,
    passos,
    perfil,
    rodar_tudo,
    ver,
)
from sociman_api.ia.models import IaChamada, IaDesfecho


def _acao(client, h, gid: str, nome: str, status: int = 200) -> dict:
    g = client.get(f"/api/geracoes/{gid}", headers=h).json()
    r = client.post(f"/api/geracoes/{gid}/{nome}", headers=h, json={"version": g["version"]})
    assert r.status_code == status, r.text
    return r.json()


def test_sem_chave_falha_e_libera_pedir_ficha_depois_de_cancelar(client, owner, motores):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    assert motores.ia_client is None  # sem ANTERIOR_API_KEY
    motores.linha_claude().volta()
    p = ver(client, h, p["id"])
    ficha = passos(p, "produto.ficha")[0]
    assert ficha["status"] == "falhou" and ficha["erro"]["code"] == "servico_fora"
    assert p["status"] == "gerando" and p["ficha"] is None
    # Com a falha pendente, pedir de novo é recusado; depois de cancelar, vale.
    r = client.post(f"/api/produtos/{p['id']}/ficha/pedir", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 409
    _acao(client, h, ficha["id"], "cancelar")
    p = ver(client, h, p["id"])
    r = client.post(f"/api/produtos/{p['id']}/ficha/pedir", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 201, r.text
    assert r.json()["passo"] == "produto.ficha"


def test_recusa_e_saida_invalida_nao_mexem_na_ficha(client, owner, motores, db):
    h = owner[1]
    pid = perfil(client, h)
    com_claude(motores)
    for obs in ("recusa", "ficha inválida"):
        p = criar(client, h, pid, n_fotos=1, obs=obs)
        motores.linha_claude().volta()
        p = ver(client, h, p["id"])
        ficha = passos(p, "produto.ficha")[0]
        assert ficha["status"] == "falhou" and ficha["erro"]["code"] == "entrada_invalida"
        assert p["ficha"] is None and p["fichaPor"] is None
        row = db.scalar(select(IaChamada).where(IaChamada.geracao_id == uuid.UUID(ficha["id"])))
        assert row.desfecho == IaDesfecho.erro


def test_comfyui_fora_nao_chama_o_claude_de_novo(client, owner, motores, claude_fake):
    """SC-002: a ficha fica gravada antes da GPU; tentar de novo o recorte não repete a ficha."""
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    motores.comfy.fora = True
    for _ in range(8):  # as esperas por serviço fora até o recorte falhar
        rodar_tudo(motores)
        sem_espera()
    p = ver(client, h, p["id"])
    assert p["fichaPor"] == "ia"
    recorte = passos(p, "produto.recorte")[0]
    assert recorte["status"] == "falhou"
    motores.comfy.fora = False
    _acao(client, h, recorte["id"], "tentar-de-novo")
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    assert p["variantes"][0]["recorte"] is not None
    assert claude_fake.fichas == 1


def test_gpu_ocupada_espera_e_comeca_sozinha(client, owner, motores, claude_fake):
    from fakes.comfyui_fake import GiB

    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    motores.linha_claude().volta()
    motores.comfy.vram_free = 1 * GiB
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    recorte = passos(p, "produto.recorte")[0]
    assert recorte["status"] == "na_fila"
    assert recorte["etapaMensagem"] == "Aguardando a GPU ficar livre"
    motores.comfy.vram_free = 15 * GiB
    sem_espera()
    rodar_tudo(motores)
    assert ver(client, h, p["id"])["variantes"][0]["recorte"] is not None


def test_sem_memoria_no_flat_devolve_a_ram(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    assert motores.linha_claude().volta() == "ok"  # a ficha
    assert rodar_gpu(motores, voltas=1) == ["ok"]  # o recorte
    motores.comfy.falhar_sempre = "oom"
    motores.dockerctl.historico.clear()
    for _ in range(8):
        rodar_tudo(motores)
        sem_espera()
    p = ver(client, h, p["id"])
    flat = passos(p, "produto.flat")[0]
    assert flat["status"] == "falhou" and flat["erro"]["code"] == "sem_memoria"
    assert JOB in motores.dockerctl.historico and motores.dockerctl.memoria == NORMAL


def test_cancelar_flat_deixa_o_passo_pendente(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    flat = passos(p, "produto.flat")[0]
    _acao(client, h, flat["id"], "cancelar")
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    assert p["status"] == "gerando"
    assert [f["status"] for f in passos(p, "produto.flat")] == ["cancelada"]
    assert motores.dockerctl.memoria == NORMAL
    # O passo pendente volta pelo "Refazer flat".
    r = client.post(f"/api/produtos/{p['id']}/variantes/{p['variantes'][0]['id']}/refazer-flat",
                    headers=h, json={"version": p["version"]})
    assert r.status_code == 201, r.text


def test_gerador_nunca_escolhe_o_flat(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    assert passos(p, "produto.flat")[0]["status"] == "revisao"
    assert p["variantes"][0]["flat"] is None


def test_mcp_nao_escolhe_o_flat(client, owner, motores, claude_fake, mcp_habilitado):
    from integration.mcp_helpers import bearer, criar_cliente, ligar

    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    flat = passos(p, "produto.flat")[0]
    g = client.get(f"/api/geracoes/{flat['id']}", headers=h).json()
    ligar(client, h, mcp_habilitado)
    _, token = criar_cliente(client, h, escopo="propostas")
    r = client.post(f"/api/geracoes/{flat['id']}/escolher", headers=bearer(token),
                    json={"candidatoId": g["candidatos"][0]["id"], "version": g["version"],
                          "alvoVersion": p["version"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "somente_humano"


def test_refazer_recorte_depois_de_cancelar(client, owner, motores, claude_fake):
    h = owner[1]
    p = criar(client, h, perfil(client, h), n_fotos=1)
    motores.linha_claude().volta()
    p = ver(client, h, p["id"])
    recorte = passos(p, "produto.recorte")[0]
    url = f"/api/produtos/{p['id']}/variantes/{p['variantes'][0]['id']}/refazer-recorte"
    r = client.post(url, headers=h, json={"version": p["version"]})
    assert r.status_code == 409  # o da fila ainda vale
    _acao(client, h, recorte["id"], "cancelar")
    p = ver(client, h, p["id"])
    r = client.post(url, headers=h, json={"version": p["version"]})
    assert r.status_code == 201, r.text
    rodar_tudo(motores)
    p = ver(client, h, p["id"])
    assert p["variantes"][0]["recorte"] is not None
    r = client.post(url, headers=h, json={"version": p["version"]})
    assert r.status_code == 409  # já tem recorte
