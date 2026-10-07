"""A fila respeita a GPU (spec 021, T034, SC-002): um job de GPU por vez, só com a GPU livre;
a linha Claude roda mesmo assim; pouca VRAM espera sem contar tentativa; a ordem `/unload`
antes do ComfyUI e `/free` antes do shop-tts."""

# ruff: noqa: F811 — fixtures importadas de `geracao_helpers`

import uuid

from sqlalchemy import text

from integration.geracao_helpers import (  # noqa: F401 (fixtures)
    _buckets,
    detalhe,
    montar,
    motores,
    owner,
    pedir,
    rodar_gpu,
    sem_espera,
)
from sociman_api.db import get_engine
from sociman_api.geracao import aplicadores, passos
from sociman_api.geracao.fila import AGUARDANDO_GPU

GiB = 1024**3


def _sql(sql: str, **p):
    with get_engine().begin() as conn:
        return conn.execute(text(sql), p)


def _envio_processando(perfil_id: str) -> uuid.UUID:
    eid = uuid.uuid4()
    _sql("INSERT INTO envios (id, perfil_id, origem, source_url, source_title, status, config, "
         "direito_no_envio) VALUES (:i, :p, 'avulso_link', 'https://exemplo.test/v', 'x', "
         "'processando', '{}'::jsonb, 'avulso')", i=eid, p=perfil_id)
    return eid


class _Voz(aplicadores.Aplicador):
    """Aplicador injetado de `voz.design` (o real chega com a 025)."""

    def validar_alvo(self, db, perfil_id, alvo_id, *, lock=False):
        return type("Alvo", (), {"version": 1, "perfil_id": perfil_id})()

    def montar_params(self, db, actor, alvo, pedido):
        return {"instrucao": pedido.instrucao, "referencias": []}

    def conferir_referencias(self, db, geracao):
        return None

    def pedido_tts(self, db, geracao):
        return {"op": "design", "nome": "voz_teste", "descricao": "warm voice"}


def test_gpu_ocupada_pelo_openshorts_espera_e_depois_um_por_vez(client, owner, motores,
                                                                monkeypatch):
    h = owner[1]
    b = montar(client, h)
    monkeypatch.setitem(aplicadores.APLICADORES, "voz.design", _Voz())
    ids = [pedir(client, h, b)["id"] for _ in range(3)]
    voz = pedir(client, h, b, alvoTipo="voz", alvoId=str(uuid.uuid4()), passo="voz.design",
                instrucao="voz calma")
    envio = _envio_processando(b["perfil_id"])
    assert rodar_gpu(motores, voltas=1) == ["aguardando_gpu"]
    for gid in ids + [voz["id"]]:
        g = detalhe(client, h, gid)
        assert g["status"] == "na_fila" and g["etapaMensagem"] == AGUARDANDO_GPU
        assert g["attempts"] == 0 and g["nextAttemptAt"] is not None
    assert motores.comfy.prompts == {}
    _sql("UPDATE envios SET status = 'pronto' WHERE id = :i", i=envio)
    sem_espera()
    ordem = []
    for _ in range(4):
        rodar_gpu(motores, voltas=1)
        ordem.append([gid for gid in ids + [voz["id"]]
                      if detalhe(client, h, gid)["status"] == "revisao"])
    assert ordem == [ids[:1], ids[:2], ids, ids + [voz["id"]]]
    # FR-022: antes de cada job comfyui, /unload do shop-tts; antes do tts, /free com unload.
    tts_unloads = [p for p in motores.tts.requests if p.caminho == "/unload"]
    frees = [p.corpo for p in motores.comfy.requests if p.caminho == "/free"]
    assert len(tts_unloads) >= 3
    assert {"unload_models": True, "free_memory": True} in frees


def test_pouca_vram_espera_sem_contar(client, owner, motores):
    h = owner[1]
    b = montar(client, h)
    g = pedir(client, h, b)
    motores.comfy.vram_free = 4 * GiB
    motores.comfy.torch_vram_total = 2 * GiB
    assert rodar_gpu(motores, voltas=1) == ["aguardando_gpu"]
    g = detalhe(client, h, g["id"])
    assert g["status"] == "na_fila" and g["attempts"] == 0
    assert g["etapaMensagem"] == AGUARDANDO_GPU
    motores.comfy.torch_vram_total = 8 * GiB  # o cache do ComfyUI conta como dele (R3)
    sem_espera()
    rodar_gpu(motores, voltas=1)
    assert detalhe(client, h, g["id"])["status"] == "revisao"


def test_claude_roda_com_a_gpu_ocupada(client, owner, motores, monkeypatch):
    from fakes.anthropic_fake import AnthropicFake

    from sociman_api.ia import tipos

    h = owner[1]
    b = montar(client, h)
    pedir(client, h, b)  # um de GPU esperando
    _envio_processando(b["perfil_id"])
    motores.ia_client = AnthropicFake().ia_client()
    base = tipos.TIPOS["asset.descricao"]
    from dataclasses import replace

    monkeypatch.setitem(tipos.TIPOS, "avatar.identidade",
                        replace(base, id="avatar.identidade", regras_de="asset.descricao"))

    class _Identidade(_Voz):
        def mensagem_claude(self, db, geracao):
            return "<instrucao>confira</instrucao>"

        def aplicar(self, db, actor, geracao, candidato):
            return None

    monkeypatch.setitem(aplicadores.APLICADORES, "avatar.identidade", _Identidade())
    with passos.sobrescrever("avatar.identidade", alvo_tipo=passos.GeracaoAlvo.asset):
        g = pedir(client, h, b, passo="avatar.identidade", instrucao="confira")
        assert rodar_gpu(motores, voltas=1) == ["aguardando_gpu"]
        assert motores.linha_claude().volta() == "ok"
    assert detalhe(client, h, g["id"])["status"] == "escolhido"
