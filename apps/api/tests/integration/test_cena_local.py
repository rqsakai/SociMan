"""Extensões da 010 para o clipe local (spec 011, T014, FR-022 a FR-025, R3, R8 e R10): os campos
locais no PATCH e no detalhe, a regra da cena `usada` (só o primeiro preenchimento), o
`marcar_pronta` reutilizável, o `definir_keyframe`, o `duplicar` sem keyframe, a tomada
`geracao_local` apontando o objeto do candidato e o "keyframe antigo"/"limpa" derivados."""

# ruff: noqa: F811 — fixtures importadas de `cenas_helpers`

import uuid

import pytest
from sqlalchemy import select, text

from integration.cenas_helpers import (  # noqa: F401 — fixtures
    _buckets,
    acao,
    base,
    cena_pronta,
    criar_cena,
    get,
    owner,
    patch,
)
from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User
from sociman_api.cenas import service as cenas_service
from sociman_api.cenas import tomadas
from sociman_api.cenas.models import Cena, CenaMotor, CenaStatus, CenaTomada, TomadaOrigem
from sociman_api.errors import ApiError
from sociman_api.geracao.models import (
    Geracao,
    GeracaoAlvo,
    GeracaoCandidato,
    GeracaoMotor,
    GeracaoStatus,
)
from sociman_api.perfis.models import Image, ImageKind


def _err(r) -> str:
    return r.json()["error"]["code"]


def _keyframe(db, perfil_id=None) -> uuid.UUID:
    iid = uuid.uuid4()
    db.add(Image(id=iid, perfil_id=perfil_id, kind=ImageKind.keyframe,
                 object_key=f"agencia/{iid}.png", content_type="image/png", bytes=1, width=736,
                 height=1280, sha256="x"))
    db.commit()
    return iid


def _usada(db, cena_id) -> None:
    db.execute(text("UPDATE cenas SET status = 'usada' WHERE id = :c"), {"c": cena_id})
    db.commit()


def _ator(db, user) -> Actor:
    u = db.get(User, user.id)
    return Actor(kind="user", user_id=u.id, user=u)


def _clipe(db, cena_id, numero: int = 1, duracao_ms: int = 3000) -> GeracaoCandidato:
    g = Geracao(alvo_tipo=GeracaoAlvo.cena, alvo_id=cena_id, passo="cena.clipe",
                motor=GeracaoMotor.comfyui, params={"bloco": "clipe_minimax"}, n_opcoes=1,
                status=GeracaoStatus.rodando)
    db.add(g)
    db.flush()
    cand = GeracaoCandidato(
        geracao_id=g.id, numero=numero, video_key=f"geracoes/{g.id}/{numero}.mp4",
        video_miniatura_key=f"agencia/geracoes/{g.id}/{numero}.jpg", video_duracao_ms=duracao_ms,
        video_largura=736, video_altura=1280, video_fps=24, video_bytes=12345,
        metricas={"sha256": "b" * 64})
    db.add(cand)
    db.commit()
    return cand


def test_patch_e_detalhe_dos_campos_locais(client, db, base):
    h = base["h"]
    cena = criar_cena(client, h, base)
    assert (cena["motor"], cena["largura"], cena["altura"]) == ("minimax", 736, 1280)
    assert cena["keyframeInicial"] is None and cena["keyframeRefs"] == []
    kf = _keyframe(db)
    ref = _keyframe(db)
    removida = uuid.uuid4()
    pronta = acao(client, h, cena, "pronta")
    out = patch(client, h, pronta, motor="wan", largura=720, altura=1248,
                keyframeInicialId=str(kf), keyframeInstrucao="She holds the dress",
                keyframeRefs=[str(ref)], duracaoMaxS=4.5)
    # Os campos locais não mexem no status nem no prompt do Flow.
    assert out["status"] == "pronta" and out["prompt"]["texto"] == pronta["prompt"]["texto"]
    assert (out["motor"], out["largura"], out["altura"]) == ("wan", 720, 1248)
    assert out["keyframeInicial"]["id"] == str(kf) and out["duracaoMaxS"] == 4.5
    assert out["keyframeRefs"] == [{"imageId": str(ref), "removida": False,
                                    "thumbUrl": out["keyframeRefs"][0]["thumbUrl"]}]
    # Uma referência que sumiu (revogação) aparece como removida; no PATCH, é recusada.
    patch(client, h, out, 422, keyframeRefs=[str(removida)])
    db.execute(text("UPDATE cenas SET keyframe_refs = :r WHERE id = :c"),
               {"r": [ref, removida], "c": uuid.UUID(cena["id"])})
    db.commit()
    lida = get(client, h, cena["id"])
    assert [r["removida"] for r in lida["keyframeRefs"]] == [False, True]
    # Validações: resolução fora do múltiplo de 16, keyframe que não é keyframe, final sem inicial.
    patch(client, h, lida, 400, largura=730)  # schema: múltiplo de 16
    outra = criar_cena(client, h, base, nome="Outra")
    patch(client, h, outra, 422, keyframeInicialId=base["produto"]["id"])
    patch(client, h, outra, 422, keyframeFinalId=str(kf))
    # O histórico grava os campos locais.
    versao = history.list_versions(db, "cena", uuid.UUID(cena["id"]))[0]
    assert "motor" in versao.changed_fields and "keyframe_inicial_id" in versao.changed_fields


def test_cena_usada_aceita_so_o_primeiro_preenchimento(client, db, base, owner):
    h = base["h"]
    cena = cena_pronta(client, h, base)
    _usada(db, uuid.UUID(cena["id"]))
    cena = get(client, h, cena["id"])
    kf, kf2 = _keyframe(db), _keyframe(db)
    # A cena do Flow sem keyframe ganha o primeiro, com a resolução e o motor (FR-024).
    out = patch(client, h, cena, keyframeInicialId=str(kf), motor="ltx", largura=720,
                altura=1248)
    assert out["status"] == "usada" and out["keyframeInicial"]["id"] == str(kf)
    # Trocar um valor já definido é recusado.
    r = client.patch(f"/api/cenas/{cena['id']}", headers=h,
                     json={"version": out["version"], "keyframeInicialId": str(kf2)})
    assert r.status_code == 409 and _err(r) == "cena_usada"
    r = client.patch(f"/api/cenas/{cena['id']}", headers=h,
                     json={"version": out["version"], "motor": "wan"})
    assert r.status_code == 409 and _err(r) == "cena_usada"
    # Um campo ainda nulo continua aceito (o primeiro preenchimento dele).
    out = patch(client, h, out, duracaoMaxS=5)
    assert out["duracaoMaxS"] == 5.0
    # O `definir_keyframe` segue a mesma regra.
    db_cena = db.get(Cena, uuid.UUID(cena["id"]), with_for_update=True)
    with pytest.raises(ApiError) as exc:
        cenas_service.definir_keyframe(db, _ator(db, owner[0]), db_cena, kf2)
    assert exc.value.code == "cena_usada"
    db.rollback()


def test_definir_keyframe_e_marcar_pronta_reutilizaveis(client, db, base, owner):
    h = base["h"]
    cena = criar_cena(client, h, base)
    ator = _ator(db, owner[0])
    kf = _keyframe(db)
    linha = db.get(Cena, uuid.UUID(cena["id"]), with_for_update=True)
    assert cenas_service.definir_keyframe(db, ator, linha, kf, details={"upload": True})
    assert not cenas_service.definir_keyframe(db, ator, linha, kf)  # igual: não grava
    roteiro_id = str(uuid.uuid4())
    cenas_service.marcar_pronta(db, ator, linha,
                                {"acao": "pronta_pelo_roteiro", "roteiroId": roteiro_id})
    db.commit()
    versoes = history.list_versions(db, "cena", linha.id)
    assert versoes[0].details == {"acao": "pronta_pelo_roteiro", "roteiroId": roteiro_id}
    assert versoes[1].details == {"acao": "keyframe", "upload": True}
    assert linha.status == CenaStatus.pronta and linha.prompt_congelado
    with pytest.raises(ApiError):  # já pronta
        cenas_service.marcar_pronta(db, ator, db.get(Cena, linha.id))
    db.rollback()
    # Uma imagem que não é keyframe é recusada.
    fundo = uuid.uuid4()
    db.add(Image(id=fundo, kind=ImageKind.fundo, object_key=f"agencia/{fundo}.png",
                 content_type="image/png", bytes=1, width=768, height=1344, sha256="x"))
    db.commit()
    with pytest.raises(ApiError) as exc:
        cenas_service.definir_keyframe(db, ator, db.get(Cena, linha.id), fundo)
    assert exc.value.code == "cena_invalida"
    db.rollback()


def test_duplicar_copia_os_locais_sem_keyframe(client, db, base):
    h = base["h"]
    cena = criar_cena(client, h, base)
    kf, ref = _keyframe(db), _keyframe(db)
    cena = patch(client, h, cena, motor="wan_qualidade", keyframeInicialId=str(kf),
                 keyframeFinalId=str(kf), keyframeInstrucao="Final state", keyframeRefs=[str(ref)],
                 duracaoMaxS=6)
    copia = acao(client, h, cena, "duplicar", status=201)
    assert copia["motor"] == "wan_qualidade" and copia["keyframeInstrucao"] == "Final state"
    assert [r["imageId"] for r in copia["keyframeRefs"]] == [str(ref)]
    assert copia["duracaoMaxS"] == 6.0
    assert copia["keyframeInicial"] is None and copia["keyframeFinal"] is None
    assert copia["keyframeGeracaoId"] is None


def test_tomada_local_aponta_o_candidato(client, db, base, owner):
    h = base["h"]
    cena = cena_pronta(client, h, base)
    kf, kf2 = _keyframe(db), _keyframe(db)
    cena = patch(client, h, cena, keyframeInicialId=str(kf))
    cand = _clipe(db, uuid.UUID(cena["id"]))
    linha = db.get(Cena, uuid.UUID(cena["id"]), with_for_update=True)
    t = tomadas.registrar_tomada(
        db, _ator(db, owner[0]), linha, None, TomadaOrigem.geracao_local,
        prompt_usado="She smiles. The room stays the same.", geracao_id=cand.geracao_id,
        keyframe_image_id=kf, motor=CenaMotor.minimax, objeto_existente=cand)
    db.commit()
    assert t.video_key == cand.video_key and t.miniatura_key == cand.video_miniatura_key
    assert (t.origem, t.motor, t.fps, t.bytes) == (TomadaOrigem.geracao_local, CenaMotor.minimax,
                                                   24, 12345)
    assert t.prompt_usado.startswith("She smiles") and t.negative_usado == ""
    assert db.scalar(select(Cena.tomada_escolhida_id).where(Cena.id == linha.id)) == t.id
    versao = history.list_versions(db, "cena_tomada", t.id)[0]
    assert versao.details["geracaoId"] == str(cand.geracao_id)

    r = client.get(f"/api/cenas/{cena['id']}/tomadas", headers=h)
    item = r.json()["items"][0]
    assert item["origem"] == "geracao_local" and item["keyframeAntigo"] is False
    assert item["motor"] == "minimax" and item["limpa"] is False and item["videoUrl"]
    # Trocar o keyframe deixa a tomada "keyframe antigo" (derivado; a tomada fica).
    lida = get(client, h, cena["id"])
    patch(client, h, lida, keyframeInicialId=str(kf2))
    item = client.get(f"/api/cenas/{cena['id']}/tomadas", headers=h).json()["items"][0]
    assert item["keyframeAntigo"] is True
    # Limpa (R12): sem vídeo e sem miniatura, a tela mostra "arquivo removido".
    db.execute(text("UPDATE cena_tomadas SET video_key = NULL, miniatura_key = NULL, "
                    "bytes = NULL, limpa_em = now() WHERE id = :t"), {"t": t.id})
    db.commit()
    item = client.get(f"/api/cenas/{cena['id']}/tomadas", headers=h).json()["items"][0]
    assert item["limpa"] is True and item["videoUrl"] is None and item["thumbUrl"] is None
    r = client.post("/api/midia/links", headers=h,
                    json={"items": [{"kind": "cena_tomada", "id": str(t.id)}]})
    assert r.status_code == 404


def test_tomada_local_exige_geracao_keyframe_e_motor(client, db, base, owner):
    cena = cena_pronta(client, base["h"], base)
    linha = db.get(Cena, uuid.UUID(cena["id"]))
    cand = _clipe(db, linha.id)
    with pytest.raises(ValueError):
        tomadas.registrar_tomada(db, _ator(db, owner[0]), linha, None,
                                 TomadaOrigem.geracao_local, geracao_id=cand.geracao_id,
                                 objeto_existente=cand)
    rascunho = db.get(Cena, uuid.UUID(criar_cena(client, base["h"], base)["id"]))
    with pytest.raises(ApiError) as exc:  # só cena pronta ou usada recebe tomada (010)
        tomadas.registrar_tomada(db, _ator(db, owner[0]), rascunho, None,
                                 TomadaOrigem.geracao_local, geracao_id=cand.geracao_id,
                                 keyframe_image_id=_keyframe(db), motor=CenaMotor.wan,
                                 objeto_existente=cand)
    assert exc.value.code == "cena_nao_pronta"
    db.rollback()
    assert db.scalar(select(CenaTomada.id).where(CenaTomada.cena_id == linha.id)) is None
