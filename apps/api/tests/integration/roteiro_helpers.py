"""Dados e voltas de teste dos roteiros com vídeo local (spec 011, T013, research R18): o perfil
com o produto do catálogo aprovado (012), o avatar com o kit completo e a voz aprovada e
sincronizada como voz padrão (025), e cenas da biblioteca com o perfil base do roteiro (010 e
029), tudo pelas rotas e pelos fakes (ComfyUI, shop-tts, Claude e `dockerctl`). Nada chama serviço
real.

Uso: `from integration.roteiro_helpers import _buckets, motores, owner  # noqa: F401` (fixtures)
e `b = montar(client, h, motores)`.
"""

from datetime import UTC, datetime

from fakes.shoptts_fake import wav_sintetico
from sqlalchemy import text

from integration.geracao_helpers import (  # noqa: F401 — fixtures reexportadas
    Motores,
    _buckets,
    member,
    motores,
    owner,
    rodar_gpu,
)
from integration.padrao_helpers import (
    avatar_com_slots,
    com_claude,
    consentimento,
    enviar_audio,
    escolher_opcao,
    pedir,
    ver,
    ver_voz,
    voz,
)
from integration.produtos_helpers import criar, rodar_tudo
from integration.produtos_helpers import ver as ver_produto
from sociman_api.db import get_engine

FRASES = ["Gente, achei o vestido perfeito pra quem tem curvas!",
          "Olha esse caimento: tecido levinho, transpassado, e a faixa marca a cintura.",
          "Verde esmeralda, decote V e manguinha soltinha: fica lindo no corpo.",
          "Corre no link aqui embaixo!"]
ACOES = ["She smiles at the camera and opens her arms, showing the dress",
         "She slowly turns her body to the side and back toward the camera",
         "Her hand slowly glides along the wide flutter sleeve",
         "She points down toward the bottom of the screen and gives a small happy nod"]


def perfil(client, h, slug: str = "bia") -> str:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]["id"]


def produto_aprovado(client, h, m: Motores, perfil_id: str, n_fotos: int = 1,
                     name: str = "vestido_transpassado") -> dict:
    """Produto do catálogo (012) com ficha, recorte e sem flat, aprovado."""
    p = criar(client, h, perfil_id, n_fotos=n_fotos, obs="sem flat", name=name)
    rodar_tudo(m)
    p = ver_produto(client, h, p["id"])
    r = client.post(f"/api/produtos/{p['id']}/aprovar", headers=h,
                    json={"version": p["version"]})
    assert r.status_code == 200, r.text
    return r.json()


def sincronizar_voz(m: Motores, v: dict) -> None:
    """O que a linha `vozes_sync` do gerador faria (025, R12): a voz no shop-tts falso e a marca
    de sincronizada no banco."""
    m.tts.vozes[v["ttsId"]] = {"file": f"/vozes/ref_{v['ttsId']}.wav", "text": v["refTexto"]
                               or "Olá.", "sha256": "0" * 64}
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE vozes SET sincronizada_em = :t WHERE id = :i"),
                     {"t": datetime.now(UTC), "i": v["id"]})


def voz_aprovada(client, h, m: Motores, perfil_id: str, name: str = "Roberta vendas",
                 sincronizada: bool = True) -> dict:
    """Voz gravada com consentimento, a referência escolhida e (padrão) já no shop-tts."""
    v = voz(client, h, perfil_id, name=name)
    audio = enviar_audio(client, h, perfil_id, wav_sintetico(20.0))
    r = client.patch(f"/api/vozes/{v['id']}", headers=h,
                     json={"version": v["version"], "gravacaoAudioId": audio["id"]})
    assert r.status_code == 200, r.text
    v = consentimento(client, h, v["id"], r.json()["version"], rota="vozes")
    g = pedir(client, h, perfil_id, v["id"], "voz.gravacao", alvo_tipo="voz")
    rodar_gpu(m)
    escolher_opcao(client, h, g["id"], 1, ver_voz(client, h, v["id"])["version"])
    v = ver_voz(client, h, v["id"])
    assert v["status"] == "aprovada", v
    if sincronizada:
        sincronizar_voz(m, v)
        v = ver_voz(client, h, v["id"])
    return v


def avatar_com_voz(client, h, m: Motores, perfil_id: str, v: dict, name: str = "Bia") -> dict:
    """Avatar com o kit completo (025) e a voz padrão."""
    a = avatar_com_slots(client, h, m, perfil_id, n=5, name=name)
    assert a["kitStatus"] == "completo", a["kitStatus"]
    r = client.patch(f"/api/assets/{a['id']}", headers=h,
                     json={"version": a["version"], "vozId": v["id"]})
    assert r.status_code == 200, r.text
    return ver(client, h, a["id"])


def arquivo_do_slot(a: dict, slot: str = "corpo_base") -> dict:
    return next(f for f in a["files"] if f.get("slot") == slot and not f["archived"])


def criar_cena(client, h, b: dict, status: int = 201, **kw) -> dict:
    """Cena da biblioteca (`POST /api/cenas`, 029) com o perfil base do roteiro, o avatar e o
    produto do catálogo (variante 0). Sem `avatarArquivoId`: a cena da 010 só aceita arquivo
    `referencia`/`pose`, e os do kit (025) têm `slot`; o keyframe local usa o kit."""
    corpo = {"perfilId": b["perfil_id"], "nome": "Bia mostra o vestido", "acao": ACOES[0],
             "avatarId": b["avatar"]["id"], "plano": "medio",
             "movimento": "parada", "duracaoS": 8, "modo": "ingredientes",
             "produtoId": b["produto"]["id"],
             "produtoVarianteId": b["produto"]["variantes"][0]["id"]} | kw
    r = client.post("/api/cenas", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def montar(client, h, m: Motores, slug: str = "bia", n_cenas: int = 4) -> dict:
    """O perfil com tudo o que um roteiro pede: produto aprovado, voz aprovada e sincronizada,
    avatar com kit e voz padrão, e `n_cenas` cenas (uma ação por frase de `FRASES`)."""
    claude = com_claude(m)
    pid = perfil(client, h, slug)
    produto = produto_aprovado(client, h, m, pid)
    v = voz_aprovada(client, h, m, pid)
    a = avatar_com_voz(client, h, m, pid, v)
    b = {"perfil_id": pid, "produto": produto, "voz": v, "avatar": a, "claude": claude}
    b["cenas"] = [criar_cena(client, h, b, nome=f"Cena {i + 1}", acao=ACOES[i % len(ACOES)])
                  for i in range(n_cenas)]
    return b


# ---- voltas do roteiro ----

def ver_roteiro(client, h, roteiro_id: str) -> dict:
    r = client.get(f"/api/roteiros/{roteiro_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def linha_montagem(m: Motores):
    """A `LinhaMontagem` do gerador (motor `ffmpeg`, R2): `(clientes, stop)`, como a
    `LinhaClaude`."""
    import threading

    from sociman_api.geracao import gerador

    linha = gerador.LinhaMontagem(m.clientes, threading.Event())
    linha.executor.heartbeat_s = 0.05
    return linha


def rodar_ate(client, h, m: Motores, roteiro_id: str, status: str | tuple[str, ...],
              voltas: int = 40) -> dict:
    """Roda as linhas Claude, GPU e de montagem, uma volta de cada por vez, até o roteiro chegar
    a `status` (ou a um deles). Falha se a fila esvaziar antes. Os portões continuam com o teste
    (aprovar não é volta de linha)."""
    alvo = (status,) if isinstance(status, str) else status
    claude, gpu, montagem = m.linha_claude(), m.linha_gpu(), linha_montagem(m)
    r = ver_roteiro(client, h, roteiro_id)
    for _ in range(voltas):
        if r["status"] in alvo:
            return r
        feitas = [claude.volta(), *rodar_gpu(m, voltas=1, linha=gpu), montagem.volta()]
        r = ver_roteiro(client, h, roteiro_id)
        if not any(feitas) and r["status"] not in alvo:
            break
    assert r["status"] in alvo, f"roteiro parou em {r['status']} (esperado {alvo})"
    return r


def criar_roteiro(client, h, b: dict, status: int = 201, **kw) -> dict:
    corpo = {"nome": "Vestido verde", "brief": "Mostrar o caimento do vestido",
             "avatarId": b["avatar"]["id"], "produtos": [{"produtoId": b["produto"]["id"]}]} | kw
    r = client.post(f"/api/perfis/{b['perfil_id']}/roteiros", headers=h, json=corpo)
    assert r.status_code == status, r.text
    return r.json()


def acao(client, h, rot: dict, nome: str, status: int = 200, **body) -> dict:
    r = client.post(f"/api/roteiros/{rot['id']}/{nome}", headers=h,
                    json={"version": rot["version"], **body})
    assert r.status_code == status, r.text
    return r.json()


def editar(client, h, rot: dict, status: int = 200, **body) -> dict:
    r = client.patch(f"/api/roteiros/{rot['id']}", headers=h,
                     json={"version": rot["version"], **body})
    assert r.status_code == status, r.text
    return r.json()


def controle(client, h, rot: dict, modo: str = "revisar", status: int = 200, **portoes) -> dict:
    todos = {"texto": True, "narracao": True, "keyframes": True, "clipes": True,
             "final": True} | portoes
    r = client.put(f"/api/roteiros/{rot['id']}/controle", headers=h,
                   json={"version": rot["version"], "modo": modo, "portoes": todos})
    assert r.status_code == status, r.text
    return r.json()


def aprovar(client, h, rot: dict, portao: str, status: int = 200) -> dict:
    return acao(client, h, rot, "aprovar", status, portao=portao)


def escolher_keyframes(client, h, rot: dict, numero: int = 1) -> dict:
    """Escolhe a opção `numero` de cada geração de keyframe em revisão (a rota da 021)."""
    feitas = set()
    for p in rot["posicoes"]:
        for g in p["geracoesAbertas"]:
            if g["passo"] == "cena.keyframe" and g["status"] == "revisao" and \
                    g["id"] not in feitas:
                feitas.add(g["id"])
                det = client.get(f"/api/geracoes/{g['id']}", headers=h).json()
                cena = client.get(f"/api/cenas/{p['cena']['id']}", headers=h).json()
                cand = next(c for c in det["candidatos"] if c["numero"] == numero)
                r = client.post(f"/api/geracoes/{g['id']}/escolher", headers=h,
                                json={"version": det["version"], "candidatoId": cand["id"],
                                      "alvoVersion": cena["version"]})
                assert r.status_code == 200, r.text
    return ver_roteiro(client, h, rot["id"])


AGUARDANDO = ("aguardando_texto", "aguardando_narracao", "aguardando_keyframes",
              "aguardando_clipes", "aguardando_final")
PORTAO = {"aguardando_texto": "texto", "aguardando_narracao": "narracao",
          "aguardando_keyframes": "keyframes", "aguardando_clipes": "clipes",
          "aguardando_final": "final"}


def levar_ate(client, h, m: Motores, rot: dict, alvo: str | tuple[str, ...],
              voltas: int = 12) -> dict:
    """Roda as linhas e aprova cada portão no caminho (no de keyframes, a opção 1) até o
    roteiro chegar a `alvo`."""
    alvos = (alvo,) if isinstance(alvo, str) else alvo
    rot = ver_roteiro(client, h, rot["id"])
    for _ in range(voltas):
        if rot["status"] in alvos:
            return rot
        if rot["status"] in AGUARDANDO:
            if rot["status"] == "aguardando_keyframes":
                rot = escolher_keyframes(client, h, rot)
                if rot["status"] in alvos:
                    return rot
            rot = aprovar(client, h, rot, PORTAO[rot["status"]])
            continue
        rot = rodar_ate(client, h, m, rot["id"], (*alvos, *AGUARDANDO, "falhou", "pronto"))
        assert rot["status"] != "falhou" or "falhou" in alvos, rot["erro"]
    assert rot["status"] in alvos, f"roteiro parou em {rot['status']} (esperado {alvos})"
    return rot


def roteiro_planejado(client, h, m: Motores, b: dict, **kw) -> dict:
    """Cria e planeja (para em `aguardando_texto` com o portão ligado)."""
    rot = criar_roteiro(client, h, b, **kw)
    rot = acao(client, h, rot, "planejar")
    return rodar_ate(client, h, m, rot["id"], ("aguardando_texto", "narrando"))
