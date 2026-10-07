"""RAM do ComfyUI (spec 021, T035, SC-003): 28 GB só durante o job `comfyui` e 12 GB antes do
próximo job de GPU, em sucesso, falha, cancelamento e SIGTERM; o gerador reiniciado com 28 GB
devolve antes; "não volta" trava a linha; "não coube" chama `/free` e tenta de novo; sem o
token, nenhum job `comfyui`."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import threading
import uuid

from fakes.dockerctl_fake import JOB, NORMAL

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    Motores,
    _buckets,
    acao,
    detalhe,
    montar,
    motores,
    owner,
    pedir,
    rodar_gpu,
    sem_espera,
)
from sociman_api.geracao import fila
from sociman_api.geracao.gerador import SEM_MEMORIA_CFG


def _subiu_e_voltou(m: Motores) -> bool:
    return JOB in m.dockerctl.historico and m.dockerctl.memoria == NORMAL


def test_sucesso_e_falha_devolvem_12(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b)
    rodar_gpu(motores)
    assert detalhe(client, h, g["id"])["status"] == "revisao"
    assert _subiu_e_voltou(motores)
    motores.dockerctl.historico.clear()
    motores.comfy.falhar_sempre = "oom"
    g2 = pedir(client, h, b)
    rodar_gpu(motores, voltas=1)
    g2 = detalhe(client, h, g2["id"])
    assert g2["status"] == "na_fila" and g2["erro"]["code"] == "sem_memoria"
    assert _subiu_e_voltou(motores)


def test_cancelamento_devolve_12_e_interrompe(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b, nOpcoes=1)
    motores.comfy.voltas = 10_000  # fica "rodando" até cancelar
    linha = motores.linha_gpu()
    t = threading.Thread(target=linha.volta)
    t.start()
    for _ in range(200):
        if detalhe(client, h, g["id"])["status"] == "rodando" and motores.comfy.prompts:
            break
        threading.Event().wait(0.05)
    acao(client, h, detalhe(client, h, g["id"]), "cancelar")
    t.join(timeout=20)
    assert not t.is_alive()
    assert detalhe(client, h, g["id"])["status"] == "cancelada"
    assert motores.comfy.interrupcoes == 1 and motores.comfy.apagados
    assert _subiu_e_voltou(motores)


def test_sigterm_devolve_a_fila_sem_contar_e_12(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b, nOpcoes=1)
    motores.comfy.voltas = 10_000
    stop = threading.Event()
    linha = motores.linha_gpu(stop)
    t = threading.Thread(target=linha.volta)
    t.start()
    for _ in range(200):
        if motores.comfy.prompts:
            break
        threading.Event().wait(0.05)
    stop.set()
    t.join(timeout=20)
    g = detalhe(client, h, g["id"])
    assert g["status"] == "na_fila" and g["attempts"] == 0
    assert _subiu_e_voltou(motores)


def test_reiniciado_com_28_devolve_antes_e_nao_volta_trava(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    motores.dockerctl.memoria = JOB  # o gerador caiu no meio de um job
    linha = motores.linha_gpu()
    linha.conferir_ao_subir()
    assert motores.dockerctl.memoria == NORMAL and not linha.travada
    # "Não volta": a linha fica travada e não pega job de GPU.
    motores.dockerctl.memoria = JOB
    motores.dockerctl.nao_volta = True
    linha.conferir_ao_subir()
    assert linha.travada
    g = pedir(client, h, b)
    assert linha.volta() == "travada"
    assert detalhe(client, h, g["id"])["status"] == "na_fila"
    assert motores.comfy.prompts == {}
    motores.dockerctl.nao_volta = False
    assert linha.volta() == "destravada"
    rodar_gpu(motores, linha=linha)
    assert detalhe(client, h, g["id"])["status"] == "revisao"


def test_nao_coube_libera_vram_e_tenta_de_novo(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b, nOpcoes=1)
    motores.dockerctl.nao_coube = 1
    rodar_gpu(motores)
    assert detalhe(client, h, g["id"])["status"] == "revisao"
    assert motores.dockerctl.memoria == NORMAL
    assert {"unload_models": True, "free_memory": True} in \
        [p.corpo for p in motores.comfy.requests if p.caminho == "/free"]


def test_sem_token_nao_pega_job_comfyui(client, owner):
    h = owner[1]
    b = montar(client, h)
    m = Motores(memoria=False)
    g = pedir(client, h, b)
    assert rodar_gpu(m) == []
    g = detalhe(client, h, g["id"])
    assert g["status"] == "na_fila" and g["etapaMensagem"] == SEM_MEMORIA_CFG
    assert m.comfy.prompts == {}
    assert fila.proxima({__import__("sociman_api.geracao.models", fromlist=["x"])
                         .GeracaoMotor.comfyui}).id == uuid.UUID(g["id"])
