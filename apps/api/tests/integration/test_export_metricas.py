"""Exportação do dataset (spec 016, R16; contrato, "Exportação"; FR-008, SC-005)."""

import csv
import io
import json
import time
import uuid
import zipfile
from datetime import timedelta

import pytest
from atores import ator_fake
from sqlalchemy import update

from integration.metricas_helpers import _agora, err, semear
from integration.postagem_helpers import (  # noqa: F401
    PW,
    criar_conta,
    criar_corte,
    criar_perfil,
    membro,
)
from sociman_api.auth.deps import Actor, current_user
from sociman_api.config import get_settings
from sociman_api.main import app
from sociman_api.metricas import anonimizar, dicionario, export
from sociman_api.metricas.models import Serie, VideoRede, VinculoMetodo
from sociman_api.postagem.models import DestinoEstado, Postagem

ARQUIVOS = {"fotos_videos", "videos", "fotos_conta"}  # studio_dias: test_studio_export (020)


@pytest.fixture
def base(client, db, make_user, login):
    dono = make_user(role="dono", name="Dono")
    h = login(client, dono.email, PW)
    perfil = criar_perfil(client, h)
    conta = criar_conta(client, h, perfil["id"], "tiktok", "atavernanerd")
    return {"dono": dono, "h": h, "perfil": perfil, "conta": conta}


def _periodo(dias_atras: int = 15, dias: int = 20) -> dict:
    de = (_agora() - timedelta(days=dias_atras)).date()
    return {"de": de.isoformat(), "ate": (de + timedelta(days=dias)).isoformat()}


def _exportar(client, h, **params):
    return client.get("/api/metricas/export", headers=h, params=params)


def _zip(r) -> zipfile.ZipFile:
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(r.content))


def _csv(zf: zipfile.ZipFile, nome: str) -> list[dict]:
    dados = zf.read(nome)
    assert dados.startswith(b"\xef\xbb\xbf")  # UTF-8 com BOM
    return list(csv.DictReader(io.StringIO(dados.decode("utf-8-sig"))))


def _cabecalho(zf: zipfile.ZipFile, nome: str) -> list[str]:
    return next(csv.reader(io.StringIO(zf.read(nome).decode("utf-8-sig"))))


def _ligar(db, video_id, conteudo_id, conta_id, dono) -> Postagem:
    """Um lembrete postado ligado ao vídeo (direto no banco)."""
    agora = _agora()
    destino = Postagem(conteudo_id=conteudo_id, conta_id=uuid.UUID(conta_id),
                       estado=DestinoEstado.postado, aprovado_por=dono.id, aprovado_em=agora,
                       posted_at=agora, hashtags=["#a", "#b", "#c"], version=1,
                       created_by=dono.id)
    db.add(destino)
    db.flush()
    db.execute(update(VideoRede).where(VideoRede.id == video_id).values(
        destino_id=destino.id, vinculo_metodo=VinculoMetodo.escolha, vinculado_por=dono.id,
        vinculado_em=agora))
    db.commit()
    return destino


def test_so_dono_humano_exporta(client, base, membro):  # noqa: F811
    r = _exportar(client, membro[1], formato="csv", **_periodo())
    assert r.status_code == 403
    app.dependency_overrides[current_user] = lambda: ator_fake("mcp_client", base["dono"])
    r = _exportar(client, base["h"], formato="csv", **_periodo())
    del app.dependency_overrides[current_user]
    assert r.status_code == 403


@pytest.mark.parametrize("params", [
    {},
    {"de": "2026-09-01"},
    {"ate": "2026-09-01"},
    {"de": "2026-09-10", "ate": "2026-09-01"},
    {"de": "2025-01-01", "ate": "2026-09-01"},  # mais de 400 dias
])
def test_periodo_invalido(client, base, params):
    r = _exportar(client, base["h"], formato="csv", **params)
    assert r.status_code == 400 and err(r) == "periodo_invalido"


def test_csv_com_cabecalho_do_dicionario_bom_e_datas_de_sp(client, db, base):
    s = semear(db, base["conta"]["id"], videos=2, fotos=3)
    corte = criar_corte(db, base["perfil"]["id"])
    _ligar(db, s.videos[0], corte.id, base["conta"]["id"], base["dono"])
    p = _periodo()
    r = _exportar(client, base["h"], formato="csv", **p)
    de, ate = p["de"].replace("-", ""), p["ate"].replace("-", "")
    assert r.headers["content-disposition"] == \
        f'attachment; filename="sociman-metricas-{de}-{ate}.zip"'
    zf = _zip(r)
    # spec 022: + os 3 arquivos de público do Studio
    assert set(zf.namelist()) == {"fotos_videos.csv", "videos.csv", "fotos_conta.csv",
                                  "studio_dias.csv", "studio_distribuicoes.csv",
                                  "studio_atividade.csv", "studio_espectadores.csv",
                                  "dicionario.csv", "LEIAME.txt"}
    for arquivo in ARQUIVOS:
        assert _cabecalho(zf, f"{arquivo}.csv") == dicionario.colunas(arquivo)
    leiame = zf.read("LEIAME.txt").decode("utf-8-sig")
    assert f"Versão do dicionário: {dicionario.DICIONARIO_VERSAO}" in leiame
    assert "video_count conta só os vídeos públicos" in leiame
    dic = _csv(zf, "dicionario.csv")
    assert [(d["arquivo"], d["coluna"]) for d in dic] == \
        [(f"{c.arquivo}.csv", c.coluna) for c in dicionario.COLUNAS]

    fotos = _csv(zf, "fotos_videos.csv")
    assert len(fotos) == 6
    assert all(f["coletado_em"].endswith("-03:00") for f in fotos)
    assert fotos[0]["idade_h"] == "1.0" and fotos[0]["alvo_idade_h"] == "1.0"
    ids = {str(v) for v in s.videos}
    assert {f["video_ref"] for f in fotos} == ids  # uuid do SociMan, nunca o id da rede

    videos = {v["video_ref"]: v for v in _csv(zf, "videos.csv")}
    assert set(videos) == ids
    ligado, fora = videos[str(s.videos[0])], videos[str(s.videos[1])]
    assert ligado["origem"] == "corte" and ligado["vinculo_metodo"] == "escolha"
    assert ligado["conta"] == "@atavernanerd" and ligado["conteudo_id"] == str(corte.id)
    assert ligado["gancho"] == "Você usa isso?" and ligado["gancho_caracteres"] == "14"
    assert ligado["modo_envio"] == "lembrete" and ligado["hashtags_n"] == "3"
    assert ligado["serie"] == str(s.serie_id) and ligado["publicado_em"].endswith("-03:00")
    assert fora["origem"] == "fora"
    for coluna in ("conteudo_id", "destino_id", "modo_envio", "gancho", "canal_fonte",
                   "score", "vinculo_metodo"):
        assert fora[coluna] == ""
    assert fora["hashtags"] == "#fyp" and fora["url"].startswith("https://www.tiktok.com/")
    conta = _csv(zf, "fotos_conta.csv")
    assert conta and conta[0]["conta"] == "@atavernanerd" and conta[0]["janela"]


def test_jsonl_com_as_mesmas_chaves(client, db, base):
    semear(db, base["conta"]["id"], videos=1, fotos=2)
    zf = _zip(_exportar(client, base["h"], formato="jsonl", **_periodo()))
    assert "videos.jsonl" in zf.namelist() and "dicionario.csv" in zf.namelist()
    for arquivo in ARQUIVOS:
        linhas = zf.read(f"{arquivo}.jsonl").decode("utf-8").splitlines()
        assert linhas
        for linha in linhas:
            assert list(json.loads(linha)) == dicionario.colunas(arquivo)
    foto = json.loads(zf.read("fotos_videos.jsonl").decode().splitlines()[0])
    assert isinstance(foto["views"], int) and isinstance(foto["idade_h"], float)


def test_anonimas_so_com_incluir_anonimas(client, db, base):
    s = semear(db, base["conta"]["id"], videos=2, fotos=2)
    serie = db.get(Serie, s.serie_id)
    anonimizar.serie(db, serie, Actor(kind="user", user_id=base["dono"].id))
    db.commit()
    zf = _zip(_exportar(client, base["h"], formato="csv", **_periodo()))
    assert _csv(zf, "videos.csv") == [] and _csv(zf, "fotos_videos.csv") == []
    zf = _zip(_exportar(client, base["h"], formato="csv", incluirAnonimas="true", **_periodo()))
    videos = _csv(zf, "videos.csv")
    assert len(videos) == 2
    rotulo = db.get(Serie, s.serie_id).rotulo
    for v in videos:
        assert v["serie"] == rotulo and rotulo.startswith("Conta anônima ")
        for coluna in ("conta", "perfil", "legenda", "url", "gancho", "canal_fonte",
                       "conteudo_id", "destino_id", "hashtags"):
            assert v[coluna] == ""
        assert v["origem"] == "fora" and v["duracao_s"] == "30" and v["hora_local"] != ""
        assert v["publicado_em"].endswith(":00:00-03:00")
    conta = _csv(zf, "fotos_conta.csv")
    assert conta and all(c["serie"] == rotulo and c["conta"] == "" for c in conta)
    # Com filtro de conta, a anônima não entra (não tem conta).
    zf = _zip(_exportar(client, base["h"], formato="csv", incluirAnonimas="true",
                        contaId=base["conta"]["id"], **_periodo()))
    assert _csv(zf, "videos.csv") == []


def test_filtro_por_perfil_e_conta(client, db, base):
    semear(db, base["conta"]["id"], videos=1, fotos=1)
    outro = criar_perfil(client, base["h"], "Outro perfil")
    conta2 = criar_conta(client, base["h"], outro["id"], "tiktok", "meusqueridinhos10")
    s2 = semear(db, conta2["id"], videos=2, fotos=1)
    zf = _zip(_exportar(client, base["h"], formato="csv", perfilId=outro["id"], **_periodo()))
    assert {v["video_ref"] for v in _csv(zf, "videos.csv")} == {str(i) for i in s2.videos}
    zf = _zip(_exportar(client, base["h"], formato="csv", contaId=conta2["id"], **_periodo()))
    assert len(_csv(zf, "videos.csv")) == 2
    zf = _zip(_exportar(client, base["h"], formato="csv", **_periodo()))
    assert len(_csv(zf, "videos.csv")) == 3


def test_grande_sem_hd_503_e_abaixo_do_piso_507(client, db, base, monkeypatch, tmp_path):
    semear(db, base["conta"]["id"], videos=1, fotos=2)
    monkeypatch.setattr(export, "BYTES_POR_FOTO", 64 * 1024 * 1024)  # passa de 32 MB
    s = get_settings()
    monkeypatch.setattr(s, "data_dir", str(tmp_path))  # sem o sentinela
    r = _exportar(client, base["h"], formato="csv", **_periodo())
    assert r.status_code == 503 and err(r) == "storage_unavailable"
    (tmp_path / ".sociman-volume").write_text("")
    monkeypatch.setattr(s, "data_min_free_gb", 10**9)
    r = _exportar(client, base["h"], formato="csv", **_periodo())
    assert r.status_code == 507 and err(r) == "storage_full"
    assert not (tmp_path / "work").exists()  # recusou antes de gravar
    monkeypatch.setattr(s, "data_min_free_gb", 0)
    zf = _zip(_exportar(client, base["h"], formato="csv", **_periodo()))
    assert len(_csv(zf, "fotos_videos.csv")) == 2
    assert list((tmp_path / "work" / "exports").iterdir()) == []  # temporário apagado


def test_um_mes_de_uma_conta_em_menos_de_2s(client, db, base):
    inicio = _agora() - timedelta(days=31)
    semear(db, base["conta"]["id"], videos=60, fotos=70, inicio=inicio, intervalo_h=12)
    de = (inicio - timedelta(days=1)).date()  # folga do fuso de São Paulo
    params = {"de": de.isoformat(), "ate": (de + timedelta(days=34)).isoformat()}
    t0 = time.perf_counter()
    zf = _zip(_exportar(client, base["h"], formato="csv", **params))
    assert time.perf_counter() - t0 < 2.0
    assert len(_csv(zf, "fotos_videos.csv")) == 60 * 70
    assert len(_csv(zf, "videos.csv")) == 60
