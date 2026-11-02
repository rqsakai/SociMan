"""Grade de duração do vídeo guiado (spec 031, US6, T049): com os serviços falsos e o ffmpeg real,
o vídeo final tem exatamente a duração-alvo (SC-004, ±0,5 s), cada posição tem trechos × base,
a fala de cada cena entra no slot dela (R4) e a mudança do `ROTEIRO_TRECHO_BASE_S` depois de
criado não mexe no roteiro (FR-033). A fala que não cabe vira o aviso `fala_nao_cabe` antes dos
keyframes (FR-032). O roteiro guiado é montado à mão (o "Novo vídeo" é de outra tarefa).

US7 (T051): no avançado, `regerar` de quadro com `nOpcoes = 2` faz a cadeia esperar a escolha
humana, e `regerar` de clipe com `nOpcoes = 2` dá 2 tomadas do trecho, com a escolha pelo
`PUT …/tomada` com o `trecho`."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import json
import os
import subprocess
import tempfile
import uuid

from sqlalchemy import select

from integration.padrao_helpers import cenario_com_cena
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    aprovar,
    controle,
    criar_roteiro,
    montar,
    motores,
    owner,
    rodar_ate,
    ver_roteiro,
)
from sociman_api import storage
from sociman_api.auth.deps import Actor
from sociman_api.cenas import quadros
from sociman_api.cenas.models import Cena
from sociman_api.config import get_settings
from sociman_api.conteudos.models import Conteudo
from sociman_api.geracao.models import Geracao, GeracaoCandidato
from sociman_api.roteiros.estado import S
from sociman_api.roteiros.models import (
    ConversaEstado,
    PosicaoReuso,
    Roteiro,
    RoteiroCena,
    RoteiroTipoVideo,
)

CURTA = "Gente, olha o caimento!"
LONGA = ("Gente, olha o caimento desse vestido, o tecido é levinho, não marca nada, tem bolso, "
         "forro e ainda vem em quatro cores lindas para o verão inteiro")


def _guiado(client, h, m, db, dono, frases: list[str], trechos: list[int]) -> dict:
    """Um roteiro guiado em `aguardando_texto`: uma posição por frase, com `trechos[i]` trechos
    no trecho-base da configuração de agora e a sequência de quadros vazia de cada cena."""
    b = montar(client, h, m, n_cenas=len(frases))
    b["cenario"] = cenario_com_cena(client, h, m, b["perfil_id"])
    rot = criar_roteiro(client, h, b)
    r = db.get(Roteiro, uuid.UUID(rot["id"]))
    base = get_settings().roteiro_trecho_base_s
    r.tipo_video = RoteiroTipoVideo.avatar_pov
    r.cenario_id = uuid.UUID(b["cenario"]["id"])
    r.duracao_alvo_s, r.trecho_base_s = sum(trechos) * base, base
    r.conversa_estado = ConversaEstado.respondida
    r.frases = list(frases)
    ator = Actor(kind="user", user_id=dono.id)
    for i, n in enumerate(trechos):
        cena_id = uuid.UUID(b["cenas"][i]["id"])
        r.posicoes_rel.append(RoteiroCena(roteiro_id=r.id, ordem=i, cena_id=cena_id,
                                          frases=[i], trechos=n, reuso=PosicaoReuso.nova))
        quadros.criar(db, ator, db.get(Cena, cena_id),
                      [f"She holds the dress, state {k}" for k in range(n + 1)])
    r.status = S.aguardando_texto
    r.comandado_por = dono.id
    db.commit()
    return ver_roteiro(client, h, rot["id"])


def _baixar(key: str) -> str:
    fd, nome = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    storage.get_to_file(key, nome, bucket="videos")
    return nome


def _duracoes(path: str) -> dict[str, float]:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,duration:format=duration", "-of", "json", path],
                       capture_output=True, check=True)
    info = json.loads(r.stdout)
    out = {s["codec_type"]: float(s["duration"]) for s in info["streams"] if "duration" in s}
    out["formato"] = float(info["format"]["duration"])
    return out


def _fala_por_slot(path: str, inicio_s: float, fim_s: float) -> float:
    """O volume máximo (dBFS) do áudio entre `inicio_s` e `fim_s`."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-ss", f"{inicio_s:.3f}", "-to", f"{fim_s:.3f}",
                        "-i", path, "-af", "volumedetect", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True, check=False)
    linha = next(x for x in r.stderr.splitlines() if "max_volume" in x)
    return float(linha.split("max_volume:")[1].split("dB")[0])


def test_duracao_exata(client, db, owner, motores, monkeypatch):
    h = owner[1]
    base = get_settings().roteiro_trecho_base_s
    rot = _guiado(client, h, motores, db, owner[0], [CURTA, CURTA], trechos=[1, 2])
    alvo = 3 * base
    rot = controle(client, h, rot, texto=False, narracao=False, keyframes=False, final=False)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes", voltas=80)
    # FR-033: a configuração muda no meio; o roteiro segue na grade com que nasceu.
    monkeypatch.setattr(get_settings(), "roteiro_trecho_base_s", base + 1)
    rot = aprovar(client, h, rot, "clipes")
    rot = rodar_ate(client, h, motores, rot["id"], "pronto", voltas=80)
    assert [p["duracaoS"] for p in rot["posicoes"]] == [base, 2 * base]
    db.expire_all()
    r = db.get(Roteiro, uuid.UUID(rot["id"]))
    assert (r.trecho_base_s, r.duracao_alvo_s) == (base, alvo)
    assert not [a for a in r.avisos or [] if a["code"] == "fala_nao_cabe"]

    # A prévia e o final têm exatamente a duração-alvo (SC-004).
    previa = db.get(Geracao, r.montagem_geracao_id)
    assert [len(p["trechos"]) for p in previa.params["extras"]["posicoes"]] == [1, 2]
    assert [b["indice"] for b in previa.params["extras"]["fala"]] == [0, 1]
    cand = db.get(GeracaoCandidato, previa.escolhido_id)
    d = _duracoes(_baixar(cand.video_key))
    assert abs(d["formato"] - alvo) <= 0.5 and abs(d["video"] - alvo) <= 0.5
    final = _baixar(db.get(Conteudo, uuid.UUID(rot["conteudoId"])).video_key)
    d = _duracoes(final)
    assert abs(d["formato"] - alvo) <= 0.5
    assert abs(d["video"] - alvo) <= 0.5 and abs(d["audio"] - alvo) <= 0.5

    # A fala de cada cena entra no slot dela (+0,15 s) e para antes do fim do slot.
    assert _fala_por_slot(final, 0.3, 1.0) > -40  # a fala da cena 1 no slot 1
    assert _fala_por_slot(final, base - 0.25, base + 0.1) < -60  # silêncio na virada
    assert _fala_por_slot(final, base + 0.3, base + 1.0) > -40  # a fala da cena 2 no slot 2
    assert _fala_por_slot(final, alvo - 1.0, alvo - 0.1) < -60  # o fim do slot 2 em silêncio


def test_fala_que_nao_cabe_avisa_antes_dos_keyframes(client, db, owner, motores):
    h = owner[1]
    rot = _guiado(client, h, motores, db, owner[0], [CURTA, LONGA], trechos=[1, 1])
    rot = controle(client, h, rot, texto=False)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_narracao")
    avisos = [a for a in rot["avisos"] if a["code"] == "fala_nao_cabe"]
    assert [a["ordem"] for a in avisos] == [1]
    assert "cena 2" in avisos[0]["message"]


# ---- US7: o modo avançado pede 2 ou mais versões (T051; FR-015, R8) ----

def _regerar(client, h, rot: dict, ordem: int, etapa: str, status: int = 200, **corpo) -> dict:
    r = client.post(f"/api/roteiros/{rot['id']}/posicoes/{ordem}/{etapa}/regerar", headers=h,
                    json={"version": rot["version"], **corpo})
    assert r.status_code == status, r.text
    return r.json()


def test_avancado_regerar_quadro_com_duas_opcoes(client, db, owner, motores):
    from integration.guiado_helpers import aprovar_posicao, ate_quadros, ativos, geracoes, guiado
    from integration.guiado_helpers import versoes as versoes_roteiro

    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[2])
    rot = ate_quadros(client, h, motores, rot)
    antes = ativos(db, c0)
    assert all(q.image_id and q.provisorio for q in antes)
    err = _regerar(client, h, rot, 0, "keyframe", 400, quadro=1, nOpcoes=5)
    assert err["error"]["code"] == "validation_error"

    # Refazer o quadro 1 com 2 opções: o 1 e o 2 voltam a vazio, o 0 fica.
    rot = _regerar(client, h, rot, 0, "keyframe", quadro=1, nOpcoes=2)
    q = ativos(db, c0)
    assert q[0].image_id == antes[0].image_id and q[1].image_id is None and q[2].image_id is None
    [v] = versoes_roteiro(client, h, rot)[:1]
    assert v["details"]["acao"] == "regerar_keyframe"
    assert (v["details"]["quadro"], v["details"]["nOpcoes"]) == (1, 2)
    assert v["autor"]["id"] == str(owner[0].id)

    # A cadeia espera a escolha humana: o quadro 2 não é pedido, e a posição não pode ser aprovada.
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")
    g = geracoes(db, "cena.keyframe", c0)[-1]
    assert (g.params["extras"]["quadro"], g.n_opcoes, g.status.value) == (1, 2, "revisao")
    assert g.params["referencias"][0] == str(antes[0].image_id)
    assert ativos(db, c0)[1].image_id is None
    assert aprovar_posicao(client, h, rot, 0, status=409)["error"]["code"] == "nada_a_aprovar"

    cand = db.scalar(select(GeracaoCandidato).where(GeracaoCandidato.geracao_id == g.id,
                                                    GeracaoCandidato.numero == 2))
    versao = client.get(f"/api/cenas/{c0}", headers=h).json()["version"]
    resp = client.post(f"/api/geracoes/{g.id}/escolher", headers=h,
                       json={"version": g.version, "candidatoId": str(cand.id),
                             "alvoVersion": versao})
    assert resp.status_code == 200, resp.text
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_keyframes")
    q = ativos(db, c0)
    assert q[1].image_id == cand.image_id and not q[1].provisorio
    assert q[2].image_id and q[2].provisorio  # o seguinte, com 1 opção, nasce do escolhido
    assert geracoes(db, "cena.keyframe", c0)[-1].params["referencias"][0] == str(cand.image_id)
    rot = aprovar_posicao(client, h, ver_roteiro(client, h, rot["id"]), 0)
    assert rot["status"] == "gerando_clipes"


def test_avancado_regerar_clipe_com_duas_opcoes(client, db, owner, motores):
    from integration.geracao_helpers import rodar_gpu
    from integration.guiado_helpers import aprovar_posicao, ate_quadros, geracoes, guiado
    from integration.guiado_helpers import versoes as versoes_roteiro
    from sociman_api.cenas.models import CenaTomada

    h = owner[1]
    _, rot, (c0,) = guiado(client, h, motores, db, owner[0], trechos=[2])
    rot = aprovar_posicao(client, h, ate_quadros(client, h, motores, rot), 0)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    db.expire_all()
    t0, t1 = (x.tomada_id for x in
              db.get(Roteiro, uuid.UUID(rot["id"])).posicoes_rel[0].trechos_ordenados())
    err = _regerar(client, h, rot, 0, "clipe", 400, trecho=1, nOpcoes=3)
    assert err["error"]["code"] == "validation_error"
    err = _regerar(client, h, rot, 0, "clipe", 400, trecho=2)
    assert err["error"]["details"]["field"] == "trecho"

    # 2 versões do trecho 1: duas gerações, duas tomadas, e a máquina espera a escolha.
    # O motor escolhido fica na cena (T059: senão a cadeia volta ao motor do plano).
    db.expire_all()
    assert db.get(Cena, c0).motor.value == "minimax"
    rot = _regerar(client, h, rot, 0, "clipe", trecho=1, nOpcoes=2, motor="wan")
    assert rot["status"] == "gerando_clipes"
    novas = [g for g in geracoes(db, "cena.clipe", c0) if g.params["extras"].get("regerar")]
    assert len(novas) == 2 and {g.params["extras"]["trecho"] for g in novas} == {1}
    assert len({g.params["extras"]["grupo"] for g in novas}) == 1
    assert {g.params["bloco"] for g in novas} == {"clipe_wan"}
    db.expire_all()
    assert db.get(Cena, c0).motor.value == "wan"
    rodar_gpu(motores, voltas=6)
    rot = ver_roteiro(client, h, rot["id"])
    assert rot["status"] == "gerando_clipes"
    db.expire_all()
    tomadas = [db.scalar(select(CenaTomada).where(CenaTomada.geracao_id == g.id))
               for g in novas]
    assert all(t is not None and t.trecho == 1 for t in tomadas)
    trechos = db.get(Roteiro, uuid.UUID(rot["id"])).posicoes_rel[0].trechos_ordenados()
    assert trechos[0].tomada_id == t0 and trechos[1].tomada_id is None
    assert db.get(CenaTomada, t1).desuso_em is not None

    # Escolher: a tomada de outro trecho é recusada; a do trecho 1 entra e o portão espera.
    r = client.put(f"/api/roteiros/{rot['id']}/posicoes/0/tomada", headers=h,
                   json={"version": rot["version"], "tomadaId": str(tomadas[1].id), "trecho": 0})
    assert r.status_code == 400 and r.json()["error"]["details"]["field"] == "trecho"
    r = client.put(f"/api/roteiros/{rot['id']}/posicoes/0/tomada", headers=h,
                   json={"version": rot["version"], "tomadaId": str(tomadas[1].id), "trecho": 1})
    assert r.status_code == 200, r.text
    rot = r.json()
    assert rot["status"] == "aguardando_clipes"
    db.expire_all()
    trechos = db.get(Roteiro, uuid.UUID(rot["id"])).posicoes_rel[0].trechos_ordenados()
    assert [x.tomada_id for x in trechos] == [t0, tomadas[1].id]
    [v] = versoes_roteiro(client, h, rot)[:1]
    assert v["details"] == {"acao": "escolher_tomada", "ordem": 0, "trecho": 1,
                            "tomadaId": str(tomadas[1].id)}


def _ate_o_final(client, h, db, owner, motores, acabamento: str | None) -> dict:
    """T059 (2026-10-15): até `pronto`, aprovando a prévia com o `acabamentoModo` dado (ou sem)."""
    from integration.guiado_helpers import aprovar_posicao, ate_quadros, guiado

    _, rot, _ = guiado(client, h, motores, db, owner[0], trechos=[1])
    assert rot["acabamentoModo"] == "leve"
    rot = aprovar_posicao(client, h, ate_quadros(client, h, motores, rot), 0)
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_clipes")
    rot = aprovar(client, h, rot, "clipes")
    rot = rodar_ate(client, h, motores, rot["id"], "aguardando_final")
    corpo = {"version": rot["version"], "portao": "final"}
    if acabamento:
        corpo["acabamentoModo"] = acabamento
    r = client.post(f"/api/roteiros/{rot['id']}/aprovar", headers=h, json=corpo)
    assert r.status_code == 200, r.text
    return rodar_ate(client, h, motores, rot["id"], "pronto", voltas=80)


def _acabamento_de(db, rot: dict) -> Geracao:
    db.expire_all()
    return db.get(Geracao, db.get(Roteiro, uuid.UUID(rot["id"])).acabamento_geracao_id)


def test_acabamento_leve_e_o_padrao(client, db, owner, motores):
    """O acabamento padrão é `leve`: linha ffmpeg, sem `upscale_video`, 1080×1920. O modo só entra
    com o portão final e não muda depois de pronto."""
    from sociman_api.geracao.models import GeracaoMotor

    h = owner[1]
    rot = _ate_o_final(client, h, db, owner, motores, None)
    g = _acabamento_de(db, rot)
    assert (g.motor, g.params["extras"]["acabamento"]) == (GeracaoMotor.ffmpeg, "leve")
    assert "bloco" not in g.params
    assert "upscale_video" not in {p.bloco for p in motores.comfy.prompts.values()}
    cand = db.get(GeracaoCandidato, g.escolhido_id)
    assert (cand.video_largura, cand.video_altura) == (1080, 1920)
    assert rot["acabamentoModo"] == "leve" and rot["conteudoId"]

    r = client.post(f"/api/roteiros/{rot['id']}/aprovar", headers=h,
                    json={"version": rot["version"], "portao": "clipes", "acabamentoModo": "hd"})
    assert r.status_code in (400, 409)
    r = client.put(f"/api/roteiros/{rot['id']}/controle", headers=h,
                   json={"version": rot["version"], "modo": rot["modo"], "portoes": rot["portoes"],
                         "acabamentoModo": "hd"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "estado_invalido"


def test_acabamento_hd_opcional(client, db, owner, motores):
    """`hd` escolhido ao aprovar a prévia: `upscale_video` na linha da GPU."""
    from sociman_api.geracao.models import GeracaoMotor

    h = owner[1]
    rot = _ate_o_final(client, h, db, owner, motores, "hd")
    g = _acabamento_de(db, rot)
    assert (g.motor, g.params["extras"]["acabamento"]) == (GeracaoMotor.comfyui, "hd")
    assert g.params["bloco"] == "upscale_video"
    assert "upscale_video" in {p.bloco for p in motores.comfy.prompts.values()}
    cand = db.get(GeracaoCandidato, g.escolhido_id)
    assert (cand.video_largura, cand.video_altura) == (1080, 1920)
    assert rot["acabamentoModo"] == "hd"
